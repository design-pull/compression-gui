# workers.py
import threading
import queue
import os
import tempfile
from compressors import smart_compress, get_size, compress_jpeg_pillow, compress_png_pillow

class CompressorWorker(threading.Thread):
    def __init__(self, task_queue, log_callback, update_callback, stop_event, output_dir, dry_run=False):
        super().__init__(daemon=True)
        self.q = task_queue
        self.log = log_callback
        self.update = update_callback
        self.stop_event = stop_event
        self.outdir = output_dir
        self.dry_run = dry_run

    def run(self):
        while not self.stop_event.is_set():
            try:
                src = self.q.get(timeout=0.5)
            except queue.Empty:
                break
            try:
                if self.dry_run:
                    # estimate by compressing to temp file then removing
                    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(src)[1])
                    os.close(fd)
                    ext = os.path.splitext(src)[1].lower()
                    method_name = "estimate"
                    newsz = None
                    err = None
                    try:
                        if ext in (".jpg", ".jpeg"):
                            _, newsz, method_name, err = compress_jpeg_pillow(src, tmp, quality=85)
                        elif ext == ".png":
                            _, newsz, method_name, err = compress_png_pillow(src, tmp)
                        else:
                            newsz = get_size(src)
                            method_name = "copy"
                            err = None
                    finally:
                        if os.path.exists(tmp):
                            try:
                                os.remove(tmp)
                            except Exception:
                                pass
                    orig = get_size(src)
                    # append output path info into method string so log includes dst
                    method_str = f"{method_name} | dst: (dry-run no write)"
                    self.log(src, orig, newsz, method_str, self.dry_run, err)
                    self.update(src, orig, newsz)
                else:
                    dst = os.path.join(self.outdir, os.path.basename(src))
                    orig, newsz, method_name, err = smart_compress(src, dst)
                    # include actual dst and method in the method field for logging
                    method_str = f"{method_name} | dst: {dst}"
                    self.log(src, orig, newsz, method_str, self.dry_run, err)
                    self.update(src, orig, newsz)
            finally:
                self.q.task_done()
