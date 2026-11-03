import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
from pathlib import Path

user32 = ctypes.windll.user32

WINDOWS = []


def enum_proc(hwnd, lParam):
    length = user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    title = buff.value
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    visible = user32.IsWindowVisible(hwnd)
    WINDOWS.append((hwnd, title, (rect.left, rect.top, rect.right, rect.bottom), visible))
    return True


ENUMWINDOWPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

PROJECT_ROOT = Path(__file__).resolve().parent
script = PROJECT_ROOT / "dzsave-v4-tkinter.py"
title_fragment = "DeepZoom"

proc = subprocess.Popen(
    [sys.executable, str(script)],
    cwd=str(PROJECT_ROOT),
    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
)
print("launched", proc.pid)
time.sleep(10)
user32.EnumWindows(ENUMWINDOWPROC(enum_proc), 0)
print("all top-level windows:")
for hwnd, title, rect, visible in WINDOWS:
    safe_title = title.encode("cp1252", errors="replace").decode("cp1252")
    mark = "VIS" if visible else "hid"
    hit = "  <-- MATCH" if title_fragment.lower() in title.lower() else ""
    print(f"  hwnd={hwnd} [{mark}] title={safe_title!r} rect={rect}{hit}")
proc.terminate()
try:
    proc.wait(timeout=5)
except Exception:
    proc.kill()
