# ui.py
import os
import sys
import threading
import tempfile
import subprocess
import logging
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import ttkbootstrap as tb
from typing import List, Optional, Sequence, Tuple

# -----------------------
# Logging
# -----------------------
logging.basicConfig(filename='app_run.log', level=logging.INFO, encoding='utf-8')
logger = logging.getLogger(__name__)

def log_exception(exc: Exception) -> None:
    logger.error("Unhandled exception:\n%s", traceback.format_exc())

# -----------------------
# resource_path (onefile 対応)
# -----------------------
def resource_path(relative_path: str) -> str:
    """
    PyInstaller onefile に対応したリソース参照。
    """
    try:
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS  # type: ignore
        else:
            base = os.path.abspath(".")
    except Exception:
        base = os.path.abspath(".")
    return os.path.join(base, relative_path)

# -----------------------
# run_no_window: try import from utils.process, fallback to local implementation
# -----------------------
try:
    from utils.process import run_no_window  # type: ignore
except Exception:
    # local fallback (compatible with previous examples)
    CREATE_NO_WINDOW = 0x08000000

    def run_no_window(cmd_args: Sequence[str],
                      cwd: Optional[str] = None,
                      timeout: Optional[float] = None) -> Tuple[int, str, str]:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = CREATE_NO_WINDOW

        proc = subprocess.Popen(
            list(cmd_args),
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
            shell=False,
            text=True
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
            logger.warning("Process timeout: %s", cmd_args)
            return proc.returncode, out or "", err or ""
        return proc.returncode, out or "", err or ""

# -----------------------
# Pillow helper for JPEG
# -----------------------
def pillow_save_jpeg(src: str, dst: str, quality: int) -> None:
    img = Image.open(src)
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert("RGB")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    img.save(dst, format="JPEG", quality=quality, optimize=True)

# -----------------------
# UI Constants (kept from your code)
# -----------------------
PREVIEW_FRAME_WIDTH = 590
THUMB_SIZE = (185, 185)
GRID_COLUMNS = 3  # サムネイル横列数

# -----------------------
# FileItem and ScrollCanvas
# -----------------------
class FileItem:
    def __init__(self, path):
        self.path = path
        self.basename = os.path.basename(path)
        self.orig_size = os.path.getsize(path)
        self.new_size = None
        self.method = None
        self.status = "待機"
        self._frame = None
        self._thumb_img = None

class ScrollCanvas(tb.Frame):
    """Canvas + inner Frame の垂直スクロール領域（Windows マウスホイール対応）"""
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.vsb = tb.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.inner = tb.Frame(self.canvas)
        self.window = self.canvas.create_window((0,0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        # Windows の標準ホイールイベントをキャッチ
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        try:
            self.canvas.itemconfig(self.window, width=event.width)
        except Exception:
            pass

    def _on_mousewheel(self, event):
        try:
            self.canvas.yview_scroll(-1 * int(event.delta / 120), "units")
        except Exception:
            pass

# -----------------------
# Main AppUI
# -----------------------
class AppUI:
    def __init__(self, master,
                 output_dir_default,
                 on_start_callback=None,
                 on_start_dry_callback=None,
                 on_stop_callback=None,
                 on_clear_callback=None):
        """
        Callbacks optional. If not provided, AppUI uses internal worker logic.
        """
        self.master = master
        self.on_start = on_start_callback
        self.on_start_dry = on_start_dry_callback
        self.on_stop = on_stop_callback
        self.on_clear = on_clear_callback

        self.style = tb.Style(theme="litera")
        self.master.title("Image Compressor GUI")
        self._center_window(1200, 760)

        self.files: List[FileItem] = []
        self.output_folder = output_dir_default or os.path.abspath("output")
        os.makedirs(self.output_folder, exist_ok=True)

        self._completion_emitted = False
        self._stop_requested = False
        self._worker_thread: Optional[threading.Thread] = None

        self._build_topbar(self.output_folder)
        self._build_main_pane()
        self._build_statusbar()
        self._set_shortcuts()

    # ---- window helpers ----
    def _center_window(self, width, height):
        self.master.geometry(f"{width}x{height}")
        self.master.update_idletasks()
        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()
        x = (sw // 2) - (width // 2)
        y = (sh // 2) - (height // 2)
        self.master.geometry(f"+{x}+{y}")

    # ---- build UI ----
    def _build_topbar(self, output_dir_default):
        top = tb.Frame(self.master, padding=8)
        top.pack(side=tk.TOP, fill=tk.X)

        self.add_btn = tb.Button(top, text="ファイル追加", bootstyle="primary", command=self._on_add_files)
        self.add_btn.pack(side=tk.LEFT, padx=4)
        try:
            self.add_btn.configure(background="#51f0c9", activebackground="#47e6bd")
        except Exception:
            pass

        tb.Button(top, text="実行（書き出し）", bootstyle="primary", command=self._on_run).pack(side=tk.LEFT, padx=8)
        tb.Label(top, text="画質 (Quality)", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(12,4))
        self.quality_var = tk.IntVar(value=70)
        tb.Spinbox(top, from_=10, to=100, textvariable=self.quality_var, width=5).pack(side=tk.LEFT, padx=4)

        tb.Label(top, text="出力フォルダ", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(12,6))
        self.output_var = tk.StringVar(value=output_dir_default)
        tb.Entry(top, textvariable=self.output_var, width=40).pack(side=tk.LEFT, padx=4)
        tb.Button(top, text="変更", bootstyle="success", command=self._choose_output).pack(side=tk.LEFT, padx=4)

        tb.Button(top, text="ドライ実行（書き出しなし）", bootstyle="warning", command=self._on_dry_run).pack(side=tk.RIGHT, padx=4)
        tb.Button(top, text="停止", bootstyle="danger", command=self._on_stop).pack(side=tk.RIGHT, padx=4)
        tb.Button(top, text="クリア", bootstyle="secondary", command=self._on_clear).pack(side=tk.RIGHT, padx=4)

    def _build_main_pane(self):
        pane = tb.Panedwindow(self.master, orient=tk.HORIZONTAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left_frame = tb.Frame(pane)
        pane.add(left_frame, weight=3)

        self.preview_frame = tb.Frame(left_frame, width=PREVIEW_FRAME_WIDTH, height=280)
        self.preview_frame.pack(fill=tk.X, padx=6, pady=(0,8))
        self.preview_frame.pack_propagate(False)
        self.preview_image_label = tb.Label(self.preview_frame, text="プレビュー領域（ここに選択画像表示）", anchor="center", bootstyle="light")
        self.preview_image_label.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.thumb_scroller = ScrollCanvas(left_frame)
        self.thumb_scroller.pack(fill=tk.BOTH, expand=True)
        self.thumb_container = self.thumb_scroller.inner

        right_frame = tb.Frame(pane)
        pane.add(right_frame, weight=1)
        tb.Label(right_frame, text="ログ", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=6, pady=(0,6))
        self.log_text = tb.Text(right_frame, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))

    def _build_statusbar(self):
        status = tb.Frame(self.master, padding=6)
        status.pack(side=tk.BOTTOM, fill=tk.X)
        self.count_var = tk.StringVar(value="Files: 0")
        self.stats_var = tk.StringVar(value="Total saved: 0 KB | Avg reduction: 0%")
        tb.Label(status, textvariable=self.count_var).pack(side=tk.LEFT, padx=6)
        tb.Label(status, textvariable=self.stats_var).pack(side=tk.RIGHT, padx=6)

    def _set_shortcuts(self):
        self.master.bind("<Control-o>", lambda e: self._on_add_files())
        self.master.bind("<Delete>", lambda e: self._on_remove_selected())

    # -------------------------
    # Logging and public actions
    # -------------------------
    def set_log(self, text: str) -> None:
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        logger.info(text)

    def update_file_result(self, path, new_size, method, error=None):
        item = next((f for f in self.files if f.path == path), None)
        if not item:
            return
        item.new_size = new_size
        item.method = method
        item.status = "エラー" if error else "完了"
        self._update_thumbnail_badge_with_stats(item)
        self._refresh_stats()
        if error:
            self.set_log(f"{path}\n→ Error: {error}")
        else:
            saved = max(0, item.orig_size - item.new_size)
            saved_pct = (saved / item.orig_size * 100) if item.orig_size else 0
            self.set_log(f"{path}\noriginal: {item.orig_size//1024} KB, compressed: {item.new_size//1024} KB, reduced: {saved//1024} KB ({saved_pct:.0f}%), method: {method}")
        self._maybe_emit_completion_summary()

    # -------------------------
    # Internal helpers
    # -------------------------
    def _choose_output(self):
        d = filedialog.askdirectory(initialdir=self.output_var.get() or os.getcwd())
        if d:
            self.output_var.set(d)

    def _on_add_files(self):
        files = filedialog.askopenfilenames(title="画像を選択", filetypes=[("Images","*.png *.jpg *.jpeg *.gif *.bmp *.svg")])
        if not files:
            return
        added = 0
        for f in files:
            if any(fi.path == f for fi in self.files):
                continue
            try:
                fi = FileItem(f)
            except Exception as e:
                self.set_log(f"スキップ: {f} -> {e}")
                continue
            self.files.append(fi)
            self._add_thumbnail(fi)
            added += 1
        if added and self.preview_image_label and self.files:
            first = self.files[0]
            self._display_in_preview(first.path)
        self._refresh_stats()
        self.set_log(f"追加: {added} files")

    def _add_thumbnail(self, fileitem):
        total = len([c for c in self.thumb_container.winfo_children() if isinstance(c, tb.Frame)])
        r = total // GRID_COLUMNS
        c = total % GRID_COLUMNS
        frame = tb.Frame(self.thumb_container, width=THUMB_SIZE[0]+12, padding=6, relief="flat")
        frame.grid_propagate(False)
        frame.grid(row=r, column=c, padx=6, pady=6, sticky="n")
        try:
            img = Image.open(fileitem.path)
            img.thumbnail(THUMB_SIZE)
            tkimg = ImageTk.PhotoImage(img)
        except Exception:
            tkimg = ImageTk.PhotoImage(Image.new("RGBA", THUMB_SIZE, (240,240,240,255)))
        lbl_img = tb.Label(frame, image=tkimg)
        lbl_img.image = tkimg
        lbl_img.pack()
        lbl_img.bind("<Button-1>", lambda e, p=fileitem.path: self._on_thumb_click(p))
        lbl_text = tb.Label(frame, text=fileitem.basename, wraplength=THUMB_SIZE[0])
        lbl_text.pack(fill=tk.X, pady=(6,0))
        badge = tb.Label(frame, text=fileitem.status, bootstyle="info")
        badge.pack(pady=(4,0))
        frame._badge = badge
        fileitem._frame = frame

    def _on_thumb_click(self, path):
        self._display_in_preview(path)
        for f in self.files:
            if f.path == path and hasattr(f, "_frame"):
                try:
                    widget = f._frame
                    self.thumb_scroller.canvas.update_idletasks()
                    bbox_all = self.thumb_scroller.canvas.bbox("all")
                    if bbox_all:
                        y1 = widget.winfo_rooty() - self.thumb_scroller.canvas.winfo_rooty()
                        self.thumb_scroller.canvas.yview_moveto(max(0, y1 / max(1, bbox_all[3])))
                except Exception:
                    pass
                widget.configure(relief="solid")
                self.master.after(600, lambda w=widget: w.configure(relief="flat"))
                break

    def _display_in_preview(self, path):
        try:
            img = Image.open(path)
            max_w = PREVIEW_FRAME_WIDTH - 20
            max_h = 260
            img.thumbnail((max_w, max_h))
            tkimg = ImageTk.PhotoImage(img)
            self.preview_image_label.config(image=tkimg, text="")
            self.preview_image_label.image = tkimg
        except Exception as e:
            self.set_log(f"プレビュー表示エラー: {e}")

    def _update_thumbnail_badge_with_stats(self, fileitem):
        try:
            frame = fileitem._frame
            badge = frame._badge
            if fileitem.status == "完了" and fileitem.new_size is not None:
                saved = max(0, fileitem.orig_size - fileitem.new_size)
                pct = (saved / fileitem.orig_size * 100) if fileitem.orig_size else 0
                badge_text = f"{pct:.0f}% / {fileitem.new_size//1024} KB"
                badge.configure(text=badge_text, bootstyle="success")
            elif fileitem.status == "処理中":
                badge.configure(text="処理中", bootstyle="warning")
            elif fileitem.status == "エラー":
                badge.configure(text="エラー", bootstyle="danger")
            else:
                badge.configure(text=fileitem.status, bootstyle="info")
        except Exception:
            pass

    def _refresh_stats(self):
        self.count_var.set(f"Files: {len(self.files)}")
        total_saved = 0
        pct_list = []
        processed_any = False
        for f in self.files:
            if f.new_size is not None:
                processed_any = True
                total_saved += max(0, f.orig_size - f.new_size)
                pct = ((f.orig_size - f.new_size) / f.orig_size * 100) if f.orig_size else 0
                pct_list.append(pct)
        avg_pct = (sum(pct_list) / len(pct_list)) if pct_list else 0
        if processed_any:
            self.stats_var.set(f"Total saved: {total_saved//1024} KB | Avg reduction: {avg_pct:.0f}%")
        else:
            self.stats_var.set("Total saved: 0 KB | Avg reduction: 0%")

    def _on_remove_selected(self):
        if not self.files:
            return
        removed = self.files.pop()
        if hasattr(removed, "_frame"):
            removed._frame.destroy()
        self._reflow_grid()
        self._refresh_stats()
        self.set_log(f"Removed: {removed.basename}")

    def _reflow_grid(self):
        children = list(self.thumb_container.winfo_children())
        for i, child in enumerate(children):
            r = i // GRID_COLUMNS
            c = i % GRID_COLUMNS
            child.grid_configure(row=r, column=c)

    def _maybe_emit_completion_summary(self):
        if not self.files:
            return
        all_done = all(f.status in ("完了", "エラー") for f in self.files)
        if not all_done:
            return
        if getattr(self, "_completion_emitted", False):
            return
        self._completion_emitted = True
        total_src = sum(f.orig_size for f in self.files)
        total_dst = sum((f.new_size or f.orig_size) for f in self.files)
        outdir = self.output_var.get()
        self.set_log(f"出力フォルダ: {outdir}")
        self.set_log(f"全体の圧縮後合計: {total_dst//1024} KB")

    # -------------------------
    # Button callbacks (call controller)
    # -------------------------
    def _on_run(self):
        if not self.files:
            messagebox.showinfo("Info", "ファイルが選択されていません")
            return
        self._completion_emitted = False
        quality = max(10, min(100, int(self.quality_var.get())))
        outdir = self.output_var.get()
        os.makedirs(outdir, exist_ok=True)
        files_paths = [f.path for f in self.files]
        for f in self.files:
            f.status = "処理中"
            self._update_thumbnail_badge_with_stats(f)
        self.set_log("開始: 実行（書き出し）")
        try:
            if self.on_start:
                self.on_start(files_paths, outdir, quality)
            else:
                # use internal worker if no controller provided
                self._start_worker(files_paths, outdir, quality, dry=False)
        except Exception as e:
            self.set_log(f"開始エラー: {e}")

    def _on_dry_run(self):
        if not self.files:
            messagebox.showinfo("Info", "ファイルが選択されていません")
            return
        self._completion_emitted = False
        quality = max(10, min(100, int(self.quality_var.get())))
        outdir = self.output_var.get()
        files_paths = [f.path for f in self.files]
        for f in self.files:
            f.status = "処理中"
            self._update_thumbnail_badge_with_stats(f)
        self.set_log("開始: ドライ実行（書き出しなし）")
        try:
            if self.on_start_dry:
                self.on_start_dry(files_paths, outdir, quality)
            else:
                self._start_worker(files_paths, outdir, quality, dry=True)
        except Exception as e:
            self.set_log(f"開始エラー: {e}")

    def _on_stop(self):
        self.set_log("停止要求を送信しました")
        try:
            if self.on_stop:
                self.on_stop()
            else:
                self._stop_requested = True
        except Exception as e:
            self.set_log(f"停止エラー: {e}")

    def _on_clear(self):
        if messagebox.askyesno("確認", "一覧とログをクリアしますか？"):
            for c in list(self.thumb_container.winfo_children()):
                c.destroy()
            self.files.clear()
            self.log_text.delete("1.0", "end")
            self.preview_image_label.config(image="", text="プレビュー領域（ここに選択画像表示）")
            self._completion_emitted = False
            self._refresh_stats()
            try:
                if self.on_clear:
                    self.on_clear()
            except Exception:
                pass

    # -------------------------
    # Worker management and compression
    # -------------------------
    def _start_worker(self, files_paths: List[str], outdir: str, quality: int, dry: bool = False) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            self.set_log("既にワーカーが実行中です")
            return
        self._stop_requested = False
        self._worker_thread = threading.Thread(target=self._worker, args=(files_paths, outdir, quality, dry), daemon=True)
        self._worker_thread.start()

    def _compress_one(self, src: str, dst: str, quality: int, dry: bool=False) -> Tuple[bool, Optional[int], str]:
        """
        Try bundled pngquant first (no-console). If not available or fails, use Pillow.
        Returns: (success, new_size_bytes or None, method_desc)
        """
        try:
            pngquant_path = resource_path("tools/pngquant.exe")
            if os.path.exists(pngquant_path):
                # pngquant parameters: adjust as needed; pngquant writes to stdout or to --output
                args = [pngquant_path, f"--quality={quality}", "--output", dst, src]
                # run_no_window prevents console flashing on Windows
                rc, out, err = run_no_window(args, timeout=30)
                if rc == 0 and os.path.exists(dst):
                    return True, os.path.getsize(dst), "pngquant"
                else:
                    logger.warning("pngquant failed rc=%s err=%s", rc, err)
            # fallback: Pillow
            if dry:
                # don't write file, but simulate size change by estimating (here halve)
                est_size = max(1, os.path.getsize(src) // 2)
                return True, est_size, "pillow-dry"
            _, ext = os.path.splitext(src)
            ext = ext.lower()
            if ext in (".jpg", ".jpeg"):
                pillow_save_jpeg(src, dst, quality)
            elif ext in (".png",):
                img = Image.open(src)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                img.save(dst, optimize=True)
            else:
                # convert others to jpeg for compression
                pillow_save_jpeg(src, dst, quality)
            return True, os.path.getsize(dst) if os.path.exists(dst) else None, "pillow"
        except Exception:
            logger.exception("compress error for %s", src)
            return False, None, traceback.format_exc()

    def _worker(self, files_paths: List[str], outdir: str, quality: int, dry: bool=False) -> None:
        for src in files_paths:
            if self._stop_requested:
                self.set_log("Processing stopped by user.")
                break
            # find FileItem
            item = next((f for f in self.files if f.path == src), None)
            if item:
                item.status = "処理中"
                self._update_thumbnail_badge_with_stats(item)
            dst_name = os.path.basename(src)
            dst = os.path.join(outdir, dst_name)
            self.set_log(f"Processing: {src}")
            success, new_size, method = self._compress_one(src, dst, quality, dry=dry)
            if success:
                # update FileItem in UI thread
                if item:
                    item.new_size = new_size or os.path.getsize(src)
                    item.method = method
                self.master.after(0, lambda p=src, n=new_size, m=method: self.update_file_result(p, n, m, None))
            else:
                if item:
                    item.status = "エラー"
                self.master.after(0, lambda p=src, n=None, m=None, e="compress failed": self.update_file_result(p, n, m, e))
        self.master.after(0, lambda: self.set_log("処理完了"))

# -------------------------
# Minimal test harness
# -------------------------
if __name__ == "__main__":
    def stub_start(files, outdir, quality):
        def simulate():
            import time
            for p in files:
                time.sleep(0.5)
                root.after(0, ui.update_file_result, p, os.path.getsize(p)//2, f"stub-method q={quality} | dst: {os.path.join(outdir, os.path.basename(p))}", None)
        threading.Thread(target=simulate, daemon=True).start()

    def stub_start_dry(files, outdir, quality):
        def simulate():
            import time
            for p in files:
                time.sleep(0.4)
                root.after(0, ui.update_file_result, p, os.path.getsize(p)//2, f"stub-dry q={quality} | dst: (dry-run no write)", None)
        threading.Thread(target=simulate, daemon=True).start()

    def stub_stop():
        print("Stop requested")
    def stub_clear():
        print("Cleared")

    root = tb.Window(themename="litera")
    ui = AppUI(root, output_dir_default=os.path.join(os.getcwd(), "output"),
               on_start_callback=None,
               on_start_dry_callback=None,
               on_stop_callback=None,
               on_clear_callback=None)
    root.mainloop()
