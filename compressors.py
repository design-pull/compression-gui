# compressors.py
import os, shutil, subprocess, tempfile
from PIL import Image

def get_size(path):
    return os.path.getsize(path)

def compress_jpeg_pillow(src, dst, quality=85):
    try:
        img = Image.open(src)
        img.save(dst, "JPEG", quality=quality, optimize=True)
        return get_size(src), get_size(dst), f"Pillow(JPEG q={quality})", None
    except Exception as e:
        return None, None, None, str(e)

def compress_png_pngquant(src, dst, quality=(65,90), pngquant_path="pngquant"):
    # pngquant outputs to stdout when using --output -, so write to temp then save
    try:
        out_temp = dst + ".tmp"
        cmd = [pngquant_path, "--quality", f"{quality[0]}-{quality[1]}", "--output", out_temp, "--force", src]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.move(out_temp, dst)
        return get_size(src), get_size(dst), "pngquant", None
    except Exception as e:
        return None, None, None, str(e)

def compress_png_pillow(src, dst, optimize=True, compress_level=9):
    try:
        img = Image.open(src)
        img.save(dst, "PNG", optimize=optimize, compress_level=compress_level)
        return get_size(src), get_size(dst), f"Pillow(PNG lvl={compress_level})", None
    except Exception as e:
        return None, None, None, str(e)

def smart_compress(src_path, dst_path, prefer_pngquant=True, jpeg_quality=85):
    ext = os.path.splitext(src_path)[1].lower()
    if ext in (".jpg", ".jpeg"):
        res = compress_jpeg_pillow(src_path, dst_path, quality=jpeg_quality)
        if res[3] is None:
            return res
        return None, None, None, f"Pillow JPEG failed: {res[3]}"
    if ext == ".png":
        if prefer_pngquant:
            res = compress_png_pngquant(src_path, dst_path)
            if res[3] is None:
                return res
        # fallback to Pillow
        res = compress_png_pillow(src_path, dst_path)
        if res[3] is None:
            return res
        return None, None, None, f"Both pngquant and Pillow failed: {res[3]}"
    # other formats: copy or re-encode to PNG
    shutil.copy2(src_path, dst_path)
    return get_size(src_path), get_size(dst_path), "copy", None
