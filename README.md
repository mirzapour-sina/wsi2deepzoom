# WSI to DeepZoom

This project converts TIFF/WSI slides into DeepZoom output and thumbnails. The
converter can be run from the command line or from one of four GUI frontends:

- Tkinter: `dzsave-v4-tkinter.py`
- PyQt6: `dzsave-v4-pyqt6.py`
- PySide6 Widgets: `dzsave-v4-pyside6.py`
- PySide6/QML: `dzsave-v4-qml.py`

All GUIs share settings and conversion logic through
`dzsave_v4_gui_common.py`; the original command-line converter remains
`dzsave-v4.py`.

## GUI usage

Use Python 3.10 and run a frontend from the project directory:

```powershell
py -3.10 .\dzsave-v4-tkinter.py
py -3.10 .\dzsave-v4-pyqt6.py
py -3.10 .\dzsave-v4-pyside6.py
py -3.10 .\dzsave-v4-qml.py
```

In the GUI:

1. Set the source WSI folder and both output destinations.
2. Set JPEG, thumbnail, and Robocopy options as needed.
3. Click **Scan files**. The TIFF list is populated with all files checked.
4. Check or uncheck individual files, or use **Select all / Select none**.
5. Click **Start conversion**. Only checked files from the most recent scan
   are processed.

Selecting no files is rejected. A new scan replaces the file list and selects
all discovered TIFFs. Scanning and conversion run in the background while the
GUI remains responsive.

The command-line converter can still be started independently:

```powershell
py -3.10 .\dzsave-v4.py
```

## Build executables

The build script supports PyInstaller, Nuitka, and cx_Freeze, with four GUI
choices. The interactive menu lets you choose one or more packagers, GUIs, and
layouts:

```powershell
py -3.10 .\build_executables.py --interactive
```

Menu choices are entered as comma-separated numbers; `0` or Enter selects all.
The build script also accepts non-interactive options:

```powershell
# One-file PyInstaller builds for all GUIs
py -3.10 .\build_executables.py --method pyinstaller --gui all --layout onefile

# One-file Nuitka QML executable
py -3.10 .\build_executables.py --method nuitka --gui qml --layout onefile

# Onedir PySide6 Widgets with cx_Freeze
py -3.10 .\build_executables.py --method cx-freeze --gui pyside6 --layout onedir

# Build a specific frontend with every supported method and layout
py -3.10 .\build_executables.py --method all --gui tkinter --layout all
```

Available GUI names are `tkinter`, `pyqt6`, `pyside6`, and `qml`. Available
methods are `pyinstaller`, `nuitka`, and `cx-freeze`; layouts are `onedir` and
`onefile`. cx_Freeze supports onedir only, so a requested cx_Freeze one-file
build is explicitly skipped.

Executables are written below:

```text
dist/
  PyInstaller/{OneFile,Onedir}/
  Nuitka/{OneFile,Onedir}/
  cx_Freeze/Onedir/
```

Each build is smoke-tested with `--self-test`. For one-file builds the `.exe`
is directly in its layout directory; onedir builds include a per-GUI folder
containing the executable and runtime files.
Re-run the build command after changing source files to refresh the packaged
executables.

### Build prerequisites

Use the same Python environment that has the GUI bindings and converter
dependencies installed. For an existing Python 3.10 installation, the Python
packages can be installed with:

```powershell
py -3.10 -m pip install pyvips PyQt6 PySide6 PyInstaller Nuitka cx-Freeze
```

Tkinter must be present in the Python installation. libvips is a native
runtime dependency and needs to be installed separately; the build script
bundles its DLLs from the vips `bin` directory. Packaging tools are selected
by the build method:

- PyInstaller: `pyinstaller`
- Nuitka: `nuitka` and its supported C compiler toolchain
- cx_Freeze: `cx-Freeze`

The build script bundles the libvips DLLs from the detected vips `bin`
directory. If autodetection does not find them, pass the directory explicitly:

```powershell
py -3.10 .\build_executables.py --method pyinstaller --gui all --layout onedir `
  --vips-bin "D:\programs\vips-dev-8.18\bin"
```

QML builds also include PySide6's QML runtime modules. Because native image
libraries and Qt are bundled, one-file executables can be large and may take
longer to start while their runtime files are extracted.
