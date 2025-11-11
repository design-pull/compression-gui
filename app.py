# app.py
import os
import threading
import queue
import time
import sys

import tkinter as tk
import tkinter.messagebox as messagebox

from ui import AppUI
from workers import CompressorWorker
from compressors import get_size

ROOT_DIR = r"C:\Users\user\compression"
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

class AppController:
    def __init__(self, root):
        self.root = root
        # create UI and wire callbacks
        self.ui = AppUI(
            master=root,
            output_dir_default=OUTPUT_DIR,
            on_start_callback=self.start_run,
            on_start_dry_callback=self.start_dry_run,
            on_stop_callback=self.stop,
            on_clear_callback=self.on_clear
        )
        # Worker control
        self.task_queue = None
        self.workers = []
        self.stop_event = threading.Event()
        self._lock = threading.Lock()

    # ---------- Callbacks invoked by UI ----------
    def start_run(self, files, outdir, thread_count):
        self._start_workers(files, outdir, thread_count, dry_run=False)

    def start_dry_run(self, files, outdir, thread_count):
        self._start_workers(files, outdir, thread_count, dry_run=True)

    def stop(self):
        with self._lock:
            if not self.workers:
                self.ui.set_log("停止: 実行中の作業がありません")
                return
            self.ui.set_log("停止: ワーカーに停止フラグを送ります")
            self.stop_event.set()
            # workers will stop shortly; we also join in background thread to avoid blocking UI
            threading.Thread(target=self._join_workers, daemon=True).start()

    def on_clear(self):
        # optional: cleanup temp / reset state
        with self._lock:
            self.task_queue = None
            self.workers = []
            self.stop_event.clear()

    # ---------- Internal worker management ----------
    def _start_workers(self, files, outdir, thread_count, dry_run=False):
        with self._lock:
            if self.workers:
                self.ui.set_log("既に実行中のワーカーがあります。先に停止してください")
                return
            # prepare queue and event
            self.task_queue = queue.Queue()
            for f in files:
                self.task_queue.put(f)
            self.stop_event.clear()
            # create output dir
            os.makedirs(outdir, exist_ok=True)
            # spawn workers
            self.workers = []
            for i in range(thread_count):
                w = CompressorWorker(
                    task_queue=self.task_queue,
                    log_callback=self._log_callback,
                    update_callback=self._update_callback_via_ui,
                    stop_event=self.stop_event,
                    output_dir=outdir,
                    dry_run=dry_run
                )
                w.name = f"CompressorWorker-{i+1}"
                self.workers.append(w)
                w.start()
            self.ui.set_log(f"開始: {len(self.workers)} ワーカーを起動しました (dry_run={dry_run})")
            # monitor thread to detect completion
            threading.Thread(target=self._monitor_workers, daemon=True).start()

    def _join_workers(self, timeout=10):
        # wait for workers to finish stopping
        start = time.time()
        for w in list(self.workers):
            try:
                w.join(timeout=max(0, timeout - (time.time() - start)))
            except Exception:
                pass
        with self._lock:
            self.workers = []
            self.task_queue = None
            self.stop_event.clear()
        self.root.after(0, lambda: self.ui.set_log("停止完了"))

    def _monitor_workers(self):
        # block until queue empty and all workers idle
        if not self.task_queue:
            return
        self.task_queue.join()  # wait until all tasks are marked done
        # allow workers to exit naturally (they check queue empty or stop_event)
        # join each worker briefly
        for w in list(self.workers):
            try:
                w.join(timeout=0.2)
            except Exception:
                pass
        with self._lock:
            self.workers = []
            self.task_queue = None
            self.stop_event.clear()
        self.root.after(0, lambda: self.ui.set_log("全てのタスクが完了しました"))

    # ---------- Callbacks used by workers ----------
    def _log_callback(self, src, orig, new, method, dry, err):
        # This may be called from worker thread; marshal to main thread
        def job():
            if orig is None:
                self.ui.set_log(f"{src}\n→ Error: {err}")
            else:
                saved = max(0, orig - (new or 0))
                pct = (saved / orig * 100) if orig else 0
                self.ui.set_log(f"{src}\noriginal: {orig/1024:.0f} KB, compressed: {(new or 0)/1024:.0f} KB, reduced: {saved/1024:.0f} KB ({pct:.0f}%), method: {method}")
        self.root.after(0, job)

    def _update_callback_via_ui(self, src, orig, new):
        # called by worker, marshal result into UI's update_file_result
        def job():
            # find method by heuristic? workers already passed method via log callback; here pass None
            self.ui.update_file_result(src, new, "unknown")
        self.root.after(0, job)

# ---------- Entry point ----------
def main():
    # ensure working directory is project root for relative imports / resources
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    try:
        import ttkbootstrap as tb
    except Exception:
        messagebox.showerror("Error", "ttkbootstrap がインストールされていません。pip install ttkbootstrap pillow を実行してください。")
        return

    root = tb.Window(themename="litera")
    controller = AppController(root)
    root.protocol("WM_DELETE_WINDOW", lambda: on_closing(root, controller))
    root.mainloop()

def on_closing(root, controller):
    if controller.workers:
        if not messagebox.askyesno("確認", "ワーカーが実行中です。終了してもよいですか？"):
            return
        controller.stop()
        # allow a short window for workers to end
        time.sleep(0.2)
    root.destroy()

if __name__ == "__main__":
    main()
