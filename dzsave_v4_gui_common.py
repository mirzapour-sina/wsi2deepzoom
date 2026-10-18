from pathlib import Path
import importlib.util
import os
import queue
import sys
import threading
from contextlib import redirect_stdout


def _get_app_dir():
    pyinstaller_dir = getattr(sys, "_MEIPASS", None)
    if pyinstaller_dir:
        return Path(pyinstaller_dir)

    main_module = sys.modules.get("__main__")
    main_file = getattr(main_module, "__file__", None)
    if main_file:
        main_dir = Path(main_file).resolve().parent
        if (main_dir / "dzsave-v4.py").is_file():
            return main_dir

    compiled = globals().get("__compiled__")
    containing_dir = getattr(compiled, "containing_dir", None)
    if containing_dir:
        return Path(containing_dir)

    if getattr(sys, "frozen", False) or Path(sys.argv[0]).suffix.lower() == ".exe":
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _get_app_dir()

CONVERTER_PATH = APP_DIR / "dzsave-v4.py"
_VIPS_DLL_HANDLES = []
DEFAULTS = {
    "input_dir": r"D:\Edupat\Urmia-Medical-University\WSI",
    "jpeg_quality": "85",
    "thumbnail_size": "600",
    "thumbnail_quality": "85",
    "robocopy_threads": "16",
    "robocopy_retries": "2",
    "robocopy_wait": "1",
}
DEFAULT_DESTINATIONS = [r"D:\Edupat\Deepzoom"]

def find_wsi_files(input_dir):
    input_dir = Path(input_dir).expanduser()
    if not input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {input_dir}")
    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".tif", ".tiff"}
    )


def validate_settings(values, selected_files=None, destinations=None):
    input_dir = Path(values["input_dir"]).expanduser()
    if not input_dir.is_dir():
        raise ValueError("Select an existing input folder.")

    if destinations is None:
        destinations = DEFAULT_DESTINATIONS
    output_dirs = []
    normalized_destinations = set()
    for raw_path in destinations:
        raw_path = str(raw_path).strip()
        if not raw_path:
            raise ValueError("Remove empty destination folders or select a folder.")
        output_dir = Path(raw_path).expanduser()
        normalized_path = os.path.normcase(os.path.abspath(output_dir))
        if normalized_path in normalized_destinations:
            raise ValueError(f"Destination folder is listed more than once: {output_dir}")
        normalized_destinations.add(normalized_path)
        output_dirs.append(output_dir)
    if not output_dirs:
        raise ValueError("Add at least one destination folder.")

    try:
        settings = {
            "jpeg_quality": int(values["jpeg_quality"]),
            "thumbnail_size": int(values["thumbnail_size"]),
            "thumbnail_quality": int(values["thumbnail_quality"]),
            "robocopy_threads": int(values["robocopy_threads"]),
            "robocopy_retries": int(values["robocopy_retries"]),
            "robocopy_wait": int(values["robocopy_wait"]),
        }
    except (TypeError, ValueError) as error:
        raise ValueError("All conversion settings must be whole numbers.") from error

    if not 1 <= settings["jpeg_quality"] <= 100:
        raise ValueError("JPEG quality must be between 1 and 100.")
    if settings["thumbnail_size"] < 1:
        raise ValueError("Thumbnail size must be at least 1 pixel.")
    if not 1 <= settings["thumbnail_quality"] <= 100:
        raise ValueError("Thumbnail quality must be between 1 and 100.")
    if not 1 <= settings["robocopy_threads"] <= 128:
        raise ValueError("Copy threads must be between 1 and 128.")
    if settings["robocopy_retries"] < 0 or settings["robocopy_wait"] < 0:
        raise ValueError("Copy retries and retry wait cannot be negative.")

    settings["input_dir"] = input_dir
    settings["destinations"] = output_dirs
    if selected_files is not None:
        normalized_files = []
        for file_path in selected_files:
            path = Path(file_path).expanduser().resolve()
            try:
                path.relative_to(input_dir.resolve())
            except ValueError as error:
                raise ValueError(
                    f"Selected file is outside the source folder: {path}"
                ) from error
            if not path.is_file() or path.suffix.lower() not in {".tif", ".tiff"}:
                raise ValueError(f"Selected TIFF file is no longer available: {path}")
            normalized_files.append(path)
        if not normalized_files:
            raise ValueError("Select at least one TIFF file to convert.")
        settings["selected_files"] = normalized_files
    return settings


class QueueWriter:
    def __init__(self, events):
        self.events = events
        self.buffer = ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._send_line(line + "\n")
        return len(text)

    def flush(self):
        if self.buffer:
            self._send_line(self.buffer)
            self.buffer = ""

    def _send_line(self, line):
        if line.startswith("Overall progress:"):
            return
        self.events.put(("log", line))


def run_conversion(settings, events):
    def worker():
        try:
            vips_dir = APP_DIR / "vips"
            if vips_dir.is_dir():
                os.environ["PATH"] = str(vips_dir) + os.pathsep + os.environ.get("PATH", "")
                if os.name == "nt" and hasattr(os, "add_dll_directory"):
                    _VIPS_DLL_HANDLES.append(os.add_dll_directory(str(vips_dir)))

            spec = importlib.util.spec_from_file_location(
                "dzsave_v4_converter", CONVERTER_PATH
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not load converter: {CONVERTER_PATH}")
            converter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(converter)

            converter.INPUT_DIR = settings["input_dir"]
            converter.DESTINATION_DIRS = settings["destinations"]
            converter.JPEG_QUALITY = settings["jpeg_quality"]
            converter.THUMBNAIL_SIZE = settings["thumbnail_size"]
            converter.THUMBNAIL_QUALITY = settings["thumbnail_quality"]
            converter.ROBOCOPY_THREADS = settings["robocopy_threads"]
            converter.ROBOCOPY_RETRIES = settings["robocopy_retries"]
            converter.ROBOCOPY_WAIT = settings["robocopy_wait"]
            converter.SELECTED_FILES = settings.get("selected_files")
            converter.PROGRESS_CALLBACK = lambda progress: events.put(
                ("progress", progress)
            )

            with redirect_stdout(QueueWriter(events)):
                converter.main()
        except Exception as error:
            events.put(("error", str(error)))
        finally:
            events.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()
