from pathlib import Path
import importlib.util
import os
import queue
import sys
import threading
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime


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
_VIPS_DLL_PATHS = set()
DEFAULTS = {
    "input_dir": r"D:\Edupat\Urmia-Medical-University\WSI",
    "wsi_extensions": ".tif, .tiff, .svs, .ndpi, .mrxs, .scn, .vms, .vmu, .bif, .svslide, .vsi, .isyntax, .qptiff, .ome.tif, .ome.tiff",
    "deepzoom_format": "dzi",
    "jpeg_quality": "85",
    "thumbnail_size": "600",
    "thumbnail_quality": "85",
    "robocopy_threads": "16",
    "robocopy_retries": "2",
    "robocopy_wait": "1",
    "conversion_threads": "4",
}
DEFAULT_DESTINATIONS = [r"D:\Edupat\Deepzoom"]
DEEPZOOM_FORMATS = {
    "dzi": {"label": "DZI (descriptor + tile folder)", "layout": "dz"},
    "szi": {"label": "SZI archive", "layout": "dz"},
    "zip": {"label": "ZIP archive", "layout": "dz"},
    "zoomify": {"label": "Zoomify", "layout": "zoomify"},
    "google": {"label": "Google Maps", "layout": "google"},
    "iiif": {"label": "IIIF v2", "layout": "iiif"},
    "iiif3": {"label": "IIIF v3", "layout": "iiif3"},
}


def parse_wsi_extensions(value):
    extensions = []
    for raw_extension in str(value).replace(";", ",").split(","):
        extension = raw_extension.strip().lower().removeprefix("*")
        if not extension:
            continue
        if not extension.startswith("."):
            extension = "." + extension
        if len(extension) < 2 or any(
            character in extension for character in ("/", "\\", ":", " ")
        ):
            raise ValueError(f"Invalid WSI file extension: {raw_extension.strip()}")
        if extension not in extensions:
            extensions.append(extension)
    if not extensions:
        raise ValueError("Enter at least one WSI file extension.")
    return tuple(extensions)


def find_wsi_files(input_dir, extensions=None):
    input_dir = Path(input_dir).expanduser()
    if not input_dir.is_dir():
        raise ValueError(f"Input folder does not exist: {input_dir}")
    if extensions is None:
        extensions = parse_wsi_extensions(DEFAULTS["wsi_extensions"])
    elif isinstance(extensions, str):
        extensions = parse_wsi_extensions(extensions)
    try:
        all_files = list(input_dir.rglob("*"))
    except PermissionError as error:
        raise ValueError(
            f"Permission denied while scanning input folder: {input_dir}"
        ) from error
    return sorted(
        path
        for path in all_files
        if path.is_file()
        and path.name.lower().endswith(
            tuple(extension.lower() for extension in extensions)
        )
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

    deepzoom_format = str(values.get("deepzoom_format", "dzi")).strip().lower()
    if deepzoom_format not in DEEPZOOM_FORMATS:
        raise ValueError(
            "Select a supported DeepZoom format: "
            + ", ".join(DEEPZOOM_FORMATS)
            + "."
        )
    wsi_extensions = parse_wsi_extensions(values.get("wsi_extensions", ""))

    try:
        settings = {
            "deepzoom_format": deepzoom_format,
            "wsi_extensions": wsi_extensions,
            "jpeg_quality": int(values["jpeg_quality"]),
            "thumbnail_size": int(values["thumbnail_size"]),
            "thumbnail_quality": int(values["thumbnail_quality"]),
            "robocopy_threads": int(values["robocopy_threads"]),
            "robocopy_retries": int(values["robocopy_retries"]),
            "robocopy_wait": int(values["robocopy_wait"]),
            "conversion_threads": int(values.get("conversion_threads", DEFAULTS["conversion_threads"])),
        }
    except (TypeError, ValueError) as error:
        raise ValueError("All numeric conversion settings must be whole numbers.") from error

    if not 1 <= settings["jpeg_quality"] <= 100:
        raise ValueError("JPEG quality must be between 1 and 100.")
    if settings["thumbnail_size"] < 1:
        raise ValueError("Thumbnail size must be at least 1 pixel.")
    if not 1 <= settings["thumbnail_quality"] <= 100:
        raise ValueError("Thumbnail quality must be between 1 and 100.")
    if not 1 <= settings["robocopy_threads"] <= 128:
        raise ValueError("Copy threads must be between 1 and 128.")
    if not 1 <= settings["conversion_threads"] <= 128:
        raise ValueError("Conversion threads must be between 1 and 128.")
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
            if not path.is_file() or not path.name.lower().endswith(
                settings["wsi_extensions"]
            ):
                raise ValueError(
                    "Selected WSI file is no longer available or its extension "
                    f"is not enabled: {path}"
                )
            normalized_files.append(path)
        if not normalized_files:
            raise ValueError("Select at least one WSI file to convert.")
        settings["selected_files"] = normalized_files
    return settings


class QueueWriter:
    def __init__(self, events, log_file):
        self.events = events
        self.log_file = log_file
        self.buffer = ""

    def write(self, text):
        self.log_file.write(text)
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            self._send_line(line + "\n")
        return len(text)

    def flush(self):
        if self.buffer:
            self._send_line(self.buffer)
            self.buffer = ""
        self.log_file.flush()

    def _send_line(self, line):
        if line.startswith("Overall progress:"):
            return
        self.events.put(("log", line))


def run_conversion(settings, events):
    def worker():
        log_path = None
        report_path = None
        summary = None
        conversion_error = None
        try:
            report_dir = settings["destinations"][0] / "dzsave_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            log_path = report_dir / f"conversion_{run_stamp}.log"
            report_path = report_dir / f"conversion_{run_stamp}.md"
            started_at = datetime.now().astimezone().isoformat(timespec="seconds")
            events.put(
                (
                    "run_started",
                    {
                        "log_path": str(log_path),
                        "report_path": str(report_path),
                        "started_at": started_at,
                    },
                )
            )

            with log_path.open("w", encoding="utf-8", buffering=1) as log_file:
                with redirect_stdout(QueueWriter(events, log_file)), redirect_stderr(
                    QueueWriter(events, log_file)
                ):
                    vips_dir = APP_DIR / "vips"
                    if vips_dir.is_dir():
                        vips_dir_str = str(vips_dir)
                        if vips_dir_str not in _VIPS_DLL_PATHS:
                            _VIPS_DLL_PATHS.add(vips_dir_str)
                            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                                _VIPS_DLL_HANDLES.append(
                                    os.add_dll_directory(vips_dir_str)
                                )

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
                    converter.CONVERSION_THREADS = settings["conversion_threads"]
                    converter.SELECTED_FILES = settings.get("selected_files")
                    converter.WSI_EXTENSIONS = settings["wsi_extensions"]
                    converter.DEEPZOOM_FORMAT = settings["deepzoom_format"]
                    converter.PROGRESS_CALLBACK = lambda progress: events.put(
                        ("progress", progress)
                    )
                    summary = converter.main()
        except Exception as error:
            conversion_error = str(error)
            if log_path is not None and log_path.is_file():
                try:
                    with log_path.open("a", encoding="utf-8") as log_file:
                        log_file.write(f"\nRun error: {error}\n")
                except OSError as log_error:
                    events.put(("error", f"Could not append error to text log: {log_error}"))
            events.put(("error", str(error)))
        finally:
            if report_path is not None and log_path is not None:
                try:
                    _write_markdown_report(
                        report_path,
                        log_path,
                        settings,
                        summary,
                        conversion_error,
                    )
                    events.put(
                        (
                            "run_report",
                            {
                                "log_path": str(log_path),
                                "report_path": str(report_path),
                                "summary": summary or {},
                                "error": conversion_error or "",
                                "finished_at": datetime.now()
                                .astimezone()
                                .isoformat(timespec="seconds"),
                            },
                        )
                    )
                except OSError as error:
                    events.put(("error", f"Could not save Markdown report: {error}"))
            events.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()


def _markdown_cell(value):
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def format_duration(seconds):
    return f"{seconds:.2f} s" if seconds is not None else "—"


def _write_markdown_report(path, log_path, settings, summary, conversion_error):
    summary = summary or {}
    result_rows = [
        "| File | Resolution | Status | Load (s) | DeepZoom (s) | Thumbnail (s) | Copy (s) | Total (s) | Copy destinations | Output paths | Error |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for item in summary.get("results", []):
        duration = item.get("duration_seconds")
        result_rows.append(
            "| "
            + " | ".join(
                (
                    _markdown_cell(item.get("file", "")),
                    _markdown_cell(item.get("resolution", "")),
                    _markdown_cell(item.get("status", "unknown")),
                    _markdown_cell(item.get("load_seconds")),
                    _markdown_cell(item.get("deepzoom_seconds")),
                    _markdown_cell(item.get("thumbnail_seconds")),
                    _markdown_cell(item.get("copy_seconds")),
                    _markdown_cell(f"{duration:.2f}" if duration is not None else ""),
                    _markdown_cell(
                        "; ".join(
                            f"{copy.get('destination')}: {copy.get('status')} "
                            f"({copy.get('duration_seconds', 0):.2f}s)"
                            for copy in item.get("copy_destinations", [])
                        )
                    ),
                    _markdown_cell(
                        "; ".join(
                            path
                            for path in (
                                item.get("deepzoom_output", ""),
                                item.get("thumbnail_output", ""),
                                *item.get("copy_outputs", []),
                            )
                            if path
                        )
                    ),
                    _markdown_cell(item.get("error", "")),
                )
            )
            + " |"
        )
    if len(result_rows) == 2:
        result_rows.append("| No files processed | - | - | - | - | - | - | - | - | - | - |")

    duration = summary.get("duration_seconds")
    average = summary.get("average_seconds")
    lines = [
        "# WSI to DeepZoom Conversion Report",
        "",
        f"- **Started:** {summary.get('started_at', 'unavailable')}",
        f"- **Finished:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- **Input folder:** `{settings['input_dir']}`",
        f"- **Input extensions:** {', '.join(settings['wsi_extensions'])}",
        f"- **DeepZoom output format:** {DEEPZOOM_FORMATS[settings['deepzoom_format']]['label']}",
        f"- **Selected files:** {summary.get('total', 0)}",
        f"- **Completed:** {summary.get('completed', 0)}",
        f"- **Failed:** {summary.get('failed', 0)}",
        f"- **Total duration:** {duration:.2f} seconds" if duration is not None else "- **Total duration:** unavailable",
        f"- **Average per completed file:** {average:.2f} seconds" if average is not None else "- **Average per completed file:** unavailable",
        f"- **JPEG quality:** {settings['jpeg_quality']}",
        f"- **Thumbnail size:** {settings['thumbnail_size']} px",
        f"- **Thumbnail quality:** {settings['thumbnail_quality']}",
        f"- **Robocopy:** {settings['robocopy_threads']} threads, {settings['robocopy_retries']} retries, {settings['robocopy_wait']} second wait",
        "",
        "## Destinations",
        "",
    ]
    lines.extend(f"- `{destination}`" for destination in settings["destinations"])
    lines.extend(["", "## Per-file results", "", *result_rows])
    if conversion_error:
        lines.extend(["", "## Run error", "", conversion_error])
    lines.extend(["", "## Detailed text log", "", f"`{log_path}`", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def open_report(path):
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(f"Report file was not found: {report_path}")
    if not webbrowser.open(report_path.resolve().as_uri()):
        raise RuntimeError(f"Could not open report: {report_path}")
