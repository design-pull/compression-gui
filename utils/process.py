# utils/process.py
import subprocess
import sys
import logging
from typing import Sequence, Tuple, Optional

# Windows 固有フラグ（無ければ 0）
CREATE_NO_WINDOW = 0x08000000

def run_no_window(cmd_args: Sequence[str],
                  cwd: Optional[str] = None,
                  timeout: Optional[float] = None
                 ) -> Tuple[int, str, str]:
    """
    Windows でコンソールを表示させないで子プロセスを実行するラッパ。
    - cmd_args: コマンドを list で渡す (shell=False 前提)
    - 戻り値: (returncode, stdout, stderr)
    """
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
        logging.warning("Process timeout: %s", cmd_args)
        return proc.returncode, out or "", err or ""
    return proc.returncode, out or "", err or ""
