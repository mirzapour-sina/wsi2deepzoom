import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
DIST_ROOT = ROOT / "dist"
BUILD_ROOT = ROOT / "build" / "executables"
APPS = {
    "tkinter": {
        "script": "dzsave-v4-tkinter.py",
        "name": "DzSave-Tkinter",
        "binding": None,
    },
    "pyqt6": {
        "script": "dzsave-v4-pyqt6.py",
        "name": "DzSave-PyQt6",
        "binding": "PyQt6",
    },
    "pyside6": {
        "script": "dzsave-v4-pyside6.py",
        "name": "DzSave-PySide6",
        "binding": "PySide6",
    },
    "qml": {
        "script": "dzsave-v4-qml.py",
        "name": "DzSave-QML",
        "binding": "PySide6",
        "qml": "dzsave-v4.qml",
    },
}
METHODS = ("pyinstaller", "nuitka", "cx-freeze")
LAYOUTS = ("onedir", "onefile")


def find_vips_bin(requested):
    candidates = []
    if requested:
        candidates.append(Path(requested).expanduser())
    if os.environ.get("VIPS_HOME"):
        candidates.append(Path(os.environ["VIPS_HOME"]) / "bin")
    candidates.extend(
        Path(entry)
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and "vips" in entry.lower()
    )

    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("libvips-*.dll")):
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not locate libvips DLLs. Use --vips-bin PATH_TO_VIPS_BIN."
    )


def run(command, cwd=ROOT, env=None):
    print("\n>", subprocess.list2cmdline([str(part) for part in command]), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def copy_runtime_files(destination, vips_bin):
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "dzsave-v4.py", destination / "dzsave-v4.py")
    vips_destination = destination / "vips"
    vips_destination.mkdir(exist_ok=True)
    for dll in vips_bin.glob("*.dll"):
        shutil.copy2(dll, vips_destination / dll.name)


def prepare_app_directory(path, vips_bin):
    path.mkdir(parents=True, exist_ok=True)
    copy_runtime_files(path, vips_bin)


def smoke_test(executable, app_name):
    environment = os.environ.copy()
    if app_name != "tkinter":
        environment["QT_QPA_PLATFORM"] = "offscreen"
    run([str(executable), "--self-test"], env=environment)


def _layout_paths(method, app, onefile):
    layout_name = "OneFile" if onefile else "Onedir"
    output = DIST_ROOT / method / layout_name / app["name"]
    work = BUILD_ROOT / method / layout_name / app["name"]
    return output, work


def _runtime_data_args(vips_bin):
    args = []
    for dll in sorted(vips_bin.glob("*.dll")):
        args.extend(["--add-binary", f"{dll};vips"])
    return args


def build_pyinstaller(app_key, app, vips_bin, onefile=False):
    output, work = _layout_paths("PyInstaller", app, onefile)
    work.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile" if onefile else "--onedir",
        "--windowed",
        "--name",
        app["name"],
        "--distpath",
        str(output.parent),
        "--workpath",
        str(work),
        "--specpath",
        str(work),
        "--paths",
        str(ROOT),
        "--hidden-import",
        "dzsave_v4_gui_common",
        "--hidden-import",
        "pyvips",
        "--collect-all",
        "pyvips",
        "--collect-all",
        "cffi",
        "--add-data",
        f"{ROOT / 'dzsave-v4.py'};.",
    ]
    if app.get("qml"):
        command.extend(
            [
                "--collect-all",
                "PySide6",
                "--add-data",
                f"{ROOT / app['qml']};.",
            ]
        )
    command.extend(_runtime_data_args(vips_bin))
    if app["binding"] == "PyQt6":
        command.extend(["--exclude-module", "PySide6"])
    elif app["binding"] == "PySide6":
        command.extend(["--exclude-module", "PyQt6"])
    else:
        command.extend(["--exclude-module", "PyQt6", "--exclude-module", "PySide6"])
    command.append(str(ROOT / app["script"]))
    run(command)

    target = output if not onefile else output.parent
    if not onefile:
        prepare_app_directory(target, vips_bin)
    executable = target / f"{app['name']}.exe"
    smoke_test(executable, app_key)
    return executable


def find_nuitka_bundle(work_dir):
    candidates = sorted(work_dir.glob("*.dist"), key=lambda item: item.name.lower())
    if not candidates:
        return None
    return candidates[0]


def build_nuitka(app_key, app, vips_bin, onefile=False):
    output, work = _layout_paths("Nuitka", app, onefile)
    work.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "nuitka",
        "--mode=onefile" if onefile else "--mode=standalone",
        "--windows-console-mode=disable",
        "--assume-yes-for-downloads",
        "--jobs=4",
        f"--output-dir={work}",
        f"--output-filename={app['name']}.exe",
        "--include-module=dzsave_v4_gui_common",
        "--include-package=pyvips",
        "--include-package=cffi",
        "--include-module=_cffi_backend",
        f"--include-data-files={ROOT / 'dzsave-v4.py'}=dzsave-v4.py",
    ]
    for dll in sorted(vips_bin.glob("*.dll")):
        command.append(f"--include-data-files={dll}=vips/{dll.name}")
    if app.get("qml"):
        command.append(f"--include-data-files={ROOT / app['qml']}={app['qml']}")
        qml_modules = Path(sys.prefix) / "Lib" / "site-packages" / "PySide6" / "qml"
        if not qml_modules.is_dir():
            qml_modules = Path(sys.prefix) / "lib" / "site-packages" / "PySide6" / "qml"
        if not qml_modules.is_dir():
            raise FileNotFoundError(f"PySide6 QML modules were not found: {qml_modules}")
        command.append(f"--include-data-dir={qml_modules}=PySide6/qml")
    if app_key == "tkinter":
        command.append("--enable-plugin=tk-inter")
    elif app_key == "pyqt6":
        command.extend(["--enable-plugin=pyqt6", "--nofollow-import-to=PySide6"])
    else:
        command.extend(["--enable-plugin=pyside6", "--nofollow-import-to=PyQt6"])
    command.append(str(ROOT / app["script"]))
    run(command)

    if onefile:
        executable = work / f"{app['name']}.exe"
        if not executable.exists():
            executable = next(work.glob("*.exe"), None)
        if executable is None or not executable.exists():
            raise FileNotFoundError(f"Nuitka one-file executable was not created under: {work}")
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(executable, output.parent / executable.name)
        executable = output.parent / executable.name
    else:
        bundle = find_nuitka_bundle(work)
        if bundle is None or not bundle.is_dir():
            raise FileNotFoundError(f"Nuitka bundle was not created under: {work}")
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(bundle, output)
        prepare_app_directory(output, vips_bin)
        executable = output / f"{app['name']}.exe"
        if not executable.exists():
            executable = next(output.glob("*.exe"), None)
    if executable is None or not executable.exists():
        raise FileNotFoundError(f"Nuitka executable was not created: {output}")
    smoke_test(executable, app_key)
    return executable


def build_cx_freeze(app_key, app, vips_bin, onefile=False):
    if onefile:
        raise ValueError("cx_Freeze does not support one-file executable builds.")
    output, work = _layout_paths("cx_Freeze", app, onefile)
    setup_file = work / "setup_cxfreeze.py"
    work.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    excludes = []
    if app["binding"] == "PyQt6":
        excludes.append("PySide6")
    elif app["binding"] == "PySide6":
        excludes.append("PyQt6")
    else:
        excludes.extend(["PyQt6", "PySide6"])

    build_options = {
        "build_exe": str(output),
        "path": [str(ROOT), *sys.path],
        "includes": ["dzsave_v4_gui_common"],
        "packages": ["pyvips", "cffi"],
        "excludes": excludes,
        "include_files": [(str(ROOT / "dzsave-v4.py"), "dzsave-v4.py")],
        "include_msvcr": True,
    }
    if app.get("qml"):
        qml_modules = Path(sys.prefix) / "Lib" / "site-packages" / "PySide6" / "qml"
        if not qml_modules.is_dir():
            qml_modules = Path(sys.prefix) / "lib" / "site-packages" / "PySide6" / "qml"
        if not qml_modules.is_dir():
            raise FileNotFoundError(f"PySide6 QML modules were not found: {qml_modules}")
        build_options["include_files"].extend(
            [
                (str(ROOT / app["qml"]), app["qml"]),
                (str(qml_modules), "PySide6/qml"),
            ]
        )
    setup_file.write_text(
        "from cx_Freeze import Executable, setup\n"
        f"setup(name={app['name']!r}, version='1.0', "
        f"options={{'build_exe': {build_options!r}}}, "
        f"executables=[Executable({str(ROOT / app['script'])!r}, "
        f"base='gui', target_name={app['name']!r})])\n",
        encoding="utf-8",
    )
    run(
        [sys.executable, str(setup_file), "build_exe", "--build-exe", str(output)],
        cwd=work,
    )
    prepare_app_directory(output, vips_bin)
    executable = output / f"{app['name']}.exe"
    smoke_test(executable, app_key)
    return executable


def _prompt_selection(title, options):
    print(f"\n{title}")
    print("  0. All")
    for index, option in enumerate(options, start=1):
        print(f"  {index}. {option}")

    while True:
        answer = input("Choose numbers separated by commas (default: all): ").strip()
        if not answer or answer == "0":
            return tuple(options)
        try:
            indices = {int(value.strip()) for value in answer.split(",")}
        except ValueError:
            indices = set()
        if indices and 0 not in indices and all(1 <= i <= len(options) for i in indices):
            return tuple(options[index - 1] for index in sorted(indices))
        print("Enter 0 for all or valid option numbers separated by commas.")


BUILDERS = {
    "pyinstaller": build_pyinstaller,
    "nuitka": build_nuitka,
    "cx-freeze": build_cx_freeze,
}


def main():
    parser = argparse.ArgumentParser(
        description="Build standalone Windows executables for each dzsave-v4 GUI."
    )
    parser.add_argument(
        "--method",
        choices=("all", *METHODS),
        default="all",
        help="Packager to use (default: all three).",
    )
    parser.add_argument(
        "--gui",
        choices=("all", *APPS),
        default="all",
        help="GUI frontend to build (default: all four).",
    )
    parser.add_argument(
        "--layout",
        choices=("all", *LAYOUTS),
        default="all",
        help="Build onedir, onefile, or both where supported (default: both).",
    )
    parser.add_argument(
        "--vips-bin",
        help="Directory containing libvips DLLs; otherwise detected from PATH/VIPS_HOME.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Choose GUI frontends, packagers, and layouts with an interactive menu.",
    )
    args = parser.parse_args()

    vips_bin = find_vips_bin(args.vips_bin)
    print(f"Using libvips DLLs from: {vips_bin}", flush=True)
    if args.interactive:
        methods = _prompt_selection("Choose compiler / packager", METHODS)
        app_keys = _prompt_selection("Choose GUI frontend", tuple(APPS))
        layouts = _prompt_selection("Choose package layout", LAYOUTS)
    else:
        methods = METHODS if args.method == "all" else (args.method,)
        app_keys = tuple(APPS) if args.gui == "all" else (args.gui,)
        layouts = LAYOUTS if args.layout == "all" else (args.layout,)
    failures = []
    successes = []

    for method in methods:
        for app_key in app_keys:
            app = APPS[app_key]
            for layout in layouts:
                onefile = layout == "onefile"
                if onefile and method == "cx-freeze":
                    print(f"SKIPPED cx_Freeze one-file layout (unsupported): {app['name']}")
                    continue
                print(
                    f"\n=== Building {app['name']} with {method} ({layout}) ===",
                    flush=True,
                )
                try:
                    executable = BUILDERS[method](
                        app_key, app, vips_bin, onefile=onefile
                    )
                    successes.append(executable)
                    print(f"Verified executable: {executable}", flush=True)
                except (OSError, ValueError, subprocess.CalledProcessError) as error:
                    failures.append((method, app_key, layout, error))
                    print(
                        f"BUILD FAILED ({method}, {app_key}, {layout}): {error}",
                        flush=True,
                    )

    print("\n=== Build summary ===")
    for executable in successes:
        print(f"OK      {executable}")
    for method, app_key, layout, error in failures:
        print(f"FAILED  {method}/{app_key}/{layout}: {error}")
    if failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
