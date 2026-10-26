"""Capture each GUI window's rendered content via Win32 PrintWindow.

PrintWindow renders a window's content directly into a device context, so it
works regardless of whether the window is occluded by other desktop windows.
This is far more reliable than ImageGrab on a busy desktop.

Usage:
    python capture_windows.py
"""

import ctypes
from ctypes import wintypes
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PROJECT_ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

WAIT_SECONDS = 15      # max time to wait for the window to appear
POLL_INTERVAL = 0.5
RENDER_DELAY = 1.0     # seconds to wait after the window appears before capturing

PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint * 3)]


ENUMWINDOWPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def enumerate_visible_windows():
    found = []

    def proc(hwnd, lParam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        found.append((hwnd, title, (rect.left, rect.top, rect.right, rect.bottom)))
        return True

    user32.EnumWindows(ENUMWINDOWPROC(proc), 0)
    return found


def find_windows(fragment):
    fragment = fragment.lower()
    return [
        (hwnd, title, rect)
        for hwnd, title, rect in enumerate_visible_windows()
        if fragment in title.lower()
        and (rect[2] - rect[0]) > 50
        and (rect[3] - rect[1]) > 50
    ]


def print_window_to_image(hwnd):
    """Capture *hwnd*'s rendered content via PrintWindow and return a PIL Image."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None

    hdc_window = user32.GetWindowDC(hwnd)
    if not hdc_window:
        return None

    # Top-down 32bpp DIB so we can read the bits straight into PIL.
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    bits = ctypes.POINTER(ctypes.c_uint)()
    hbm = gdi32.CreateDIBSection(hdc_window, ctypes.byref(bmi), 0,
                                 ctypes.byref(bits), None, 0)
    if not hbm:
        user32.ReleaseDC(hwnd, hdc_window)
        return None

    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    gdi32.SelectObject(hdc_mem, hbm)

    user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    stride = width * 4
    buf = ctypes.string_at(bits, stride * height)

    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)

    # Bytes are BGRA; PIL wants RGBA -> use "raw" BGRA decoder then convert.
    img = Image.frombytes("RGBA", (width, height), buf, "raw", "BGRA", stride, 1)
    return img


def capture(gui_name, script, title_fragment, wait=WAIT_SECONDS):
    print(f"\n=== {gui_name} ===")
    print(f"Launching: {script}")

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=str(PROJECT_ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    matches = []
    try:
        deadline = time.time() + wait
        while time.time() < deadline:
            matches = find_windows(title_fragment)
            if matches:
                break
            time.sleep(POLL_INTERVAL)

        if not matches:
            print(f"  No matching window found for '{title_fragment}'")
            return False

        print(f"  Found {len(matches)} matching window(s):")
        time.sleep(RENDER_DELAY)
        ok = False
        for i, (hwnd, title, rect) in enumerate(matches):
            left, top, right, bottom = rect
            size = (right - left, bottom - top)
            print(f"    [{i}] hwnd={hwnd} title={title!r} rect={rect} size={size}")
            try:
                img = print_window_to_image(hwnd)
                if img is None:
                    print(f"    FAILED PrintWindow for window {i}")
                    continue
                out_path = SCREENSHOT_DIR / f"{gui_name}_{i}.png"
                img.convert("RGB").save(str(out_path))
                print(f"    Saved: {out_path} ({img.size[0]}x{img.size[1]})")
                ok = True
            except Exception as exc:
                print(f"    FAILED to capture window {i}: {exc}")
        return ok
    finally:
        print(f"  Terminating process (PID {proc.pid})...")
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main():
    results = {}

    results["tkinter"] = capture(
        "tkinter",
        PROJECT_ROOT / "dzsave-v4-tkinter.py",
        "WSI DeepZoom Converter - Tkinter",
    )

    results["pyside6"] = capture(
        "pyside6",
        PROJECT_ROOT / "dzsave-v4-pyside6.py",
        "WSI DeepZoom Converter - PySide6",
    )

    # QML - dzsave-v4-qml.py sets its own QML import paths internally
    results["qml"] = capture(
        "qml",
        PROJECT_ROOT / "dzsave-v4-qml.py",
        "WSI DeepZoom Converter - QML",
        wait=20,
    )

    print("\n=== pyqt6 ===")
    print("  SKIPPED: PyQt6 is not installed in this Python environment.")

    print("\n" + "=" * 50)
    print("SCREENSHOT SUMMARY")
    print("=" * 50)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name:10s}: {status}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
