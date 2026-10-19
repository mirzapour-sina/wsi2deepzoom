from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "WSI-DeepZoom-Builder.exe"
WORK = ROOT / "build" / "builder-gui"


def main():
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "WSI-DeepZoom-Builder",
        "--distpath",
        str(ROOT),
        "--workpath",
        str(WORK),
        "--specpath",
        str(WORK),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "build_executables",
        str(ROOT / "build_executables_gui.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([str(OUTPUT), "--self-test"], cwd=ROOT, check=True)
    print(f"Builder GUI executable is ready: {OUTPUT}")


if __name__ == "__main__":
    main()
