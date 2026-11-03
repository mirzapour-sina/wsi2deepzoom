"""Launch each GUI, capture a screenshot, and save it.

Usage:
    python screenshot_gui.py

This script launches each available GUI variant, waits for its window to
appear, captures the screen with PIL ImageGrab, terminates the app, and saves
the screenshot as a PNG file.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

PROJECT_ROOT = Path(__file__).resolve().parent
SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Windows-style path for PySide6 QML modules (needed by dzsave-v4-qml.py)
PYSIDE6_QML_DIR = (
    r"C:\Users\Sina\AppData\Local\Python\pythoncore-3.14-64"
    r"\Lib\site-packages\PySide6\qml"
)

WAIT_SECONDS = 4  # seconds to wait for the window to appear before capturing


def capture(gui_name, script, env=None, wait=WAIT_SECONDS):
    """Launch *script*, wait, screenshot, terminate, save PNG."""
    print(f"\n=== {gui_name} ===")
    print(f"Launching: {script}")

    proc_env = os.environ.copy()
    if env:
        proc_env.update(env)

    try:
        proc = subprocess.Popen(
            [sys.executable, str(script)],
            cwd=str(PROJECT_ROOT),
            env=proc_env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except Exception as exc:
        print(f"  FAILED to launch: {exc}")
        return False

    try:
        print(f"  Waiting {wait}s for window...")
        time.sleep(wait)

        # Check if process is still running
        if proc.poll() is not None:
            print(f"  Process exited early with code {proc.returncode}")
            return False

        print(f"  Capturing screenshot...")
        img = ImageGrab.grab()
        out_path = SCREENSHOT_DIR / f"{gui_name}.png"
        img.save(str(out_path))
        print(f"  Saved: {out_path} ({img.size[0]}x{img.size[1]})")
        return True
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

    # Tkinter
    results["tkinter"] = capture(
        "tkinter",
        PROJECT_ROOT / "dzsave-v4-tkinter.py",
    )

    # PySide6
    results["pyside6"] = capture(
        "pyside6",
        PROJECT_ROOT / "dzsave-v4-pyside6.py",
    )

    # QML - needs QML2_IMPORT_PATH to find QtQuick modules
    results["qml"] = capture(
        "qml",
        PROJECT_ROOT / "dzsave-v4-qml.py",
        env={"QML2_IMPORT_PATH": PYSIDE6_QML_DIR},
        wait=6,  # QML may need a bit longer to load
    )

    # PyQt6 - not installed in this environment
    print("\n=== pyqt6 ===")
    print("  SKIPPED: PyQt6 is not installed in this Python environment.")

    # Summary
    print("\n" + "=" * 50)
    print("SCREENSHOT SUMMARY")
    print("=" * 50)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  {name:10s}: {status}")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
