from pathlib import Path
import copy
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import dzsave_v4_gui_common as common

try:
    import pyvips
except ImportError as error:
    raise ImportError(
        "pyvips is required to run the WSI converter. "
        "Install it with: pip install pyvips (and install libvips separately)."
    ) from error


# =========================================================
# CONFIGURATION
# =========================================================

# Base directory containing the "new" folder
BASE_DIR = Path(r"D:\Edupat")

# Input WSI directory
INPUT_DIR = BASE_DIR / "Urmia-Medical-University" / "WSI"


# ---------------------------------------------------------
# Primary DeepZoom destination
# ---------------------------------------------------------
# Laravel / Edupat storage

PRIMARY_OUTPUT_DIR = Path(
    r"D:\Edupat\Deepzoom"
)


# ---------------------------------------------------------
# Secondary DeepZoom destination
# ---------------------------------------------------------

SECONDARY_OUTPUT_DIR = Path(
    r"D:\Edupat\Urmia-Medical-University\Deepzoom"
)


# ---------------------------------------------------------
# DeepZoom settings
# ---------------------------------------------------------

JPEG_QUALITY = 85


# ---------------------------------------------------------
# Thumbnail settings
# ---------------------------------------------------------

# Maximum width/height of the thumbnail.
#
# The image keeps its original aspect ratio.
#
# Examples:
#
# 10000 x 5000 -> 600 x 300
# 5000 x 5000  -> 600 x 600
# 3000 x 10000 -> 180 x 600
#
THUMBNAIL_SIZE = 600

THUMBNAIL_QUALITY = 85


# ---------------------------------------------------------
# Robocopy settings
# ---------------------------------------------------------

ROBOCOPY_THREADS = 16

ROBOCOPY_RETRIES = 2

ROBOCOPY_WAIT = 1


# ---------------------------------------------------------
# Conversion threading
# ---------------------------------------------------------

CONVERSION_THREADS = 4

WSI_EXTENSIONS = (
    ".tif",
    ".tiff",
    ".svs",
    ".ndpi",
    ".mrxs",
    ".scn",
    ".vms",
    ".vmu",
    ".bif",
    ".svslide",
    ".vsi",
    ".isyntax",
    ".qptiff",
    ".ome.tif",
    ".ome.tiff",
)
DEEPZOOM_FORMAT = "dzi"
SELECTED_FILES = None
DESTINATION_DIRS = None
PROGRESS_CALLBACK = None
PROGRESS_FILE_INDEX = 0
PROGRESS_FILE_TOTAL = 0
LAST_CONVERSION_ERROR = None
LAST_CONVERSION_DURATION = None
LAST_CONVERSION_METRICS = {}
RUN_START_PERF = None
_SCAN_CACHE = {}


def report_progress(
    stage,
    current,
    total,
    input_file=None,
    message="",
    metrics=None,
    file_index=None,
    files_total=None,
):
    if PROGRESS_CALLBACK is not None:
        file_index = (
            file_index if file_index is not None else PROGRESS_FILE_INDEX
        )
        files_total = (
            files_total if files_total is not None else PROGRESS_FILE_TOTAL
        )
        PROGRESS_CALLBACK(
            {
                "stage": stage,
                "stage_value": current,
                "current": current,
                "total": total,
                "file": str(input_file) if input_file is not None else "",
                "message": message,
                "file_index": file_index,
                "files_total": files_total,
                "completed_files": (
                    file_index
                    if stage in {"complete", "error", "finished"}
                    else max(0, file_index - 1)
                ),
                "metrics": copy.deepcopy(metrics or {}),
                "run_elapsed_seconds": (
                    time.perf_counter() - RUN_START_PERF
                    if RUN_START_PERF is not None
                    else None
                ),
            }
        )


# =========================================================
# FORMAT TIME
# =========================================================

def format_time(seconds):
    """
    Convert seconds to:

        00:12.34
        02:05.50
        01:02:05.20
    """

    hours = int(seconds // 3600)

    minutes = int(
        (seconds % 3600) // 60
    )

    seconds = seconds % 60

    if hours > 0:
        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:05.2f}"
        )

    return (
        f"{minutes:02d}:"
        f"{seconds:05.2f}"
    )


# =========================================================
# CHECK DEEPZOOM
# =========================================================

def deepzoom_storage_path(output_path: Path, output_format=None):
    output_format = output_format or DEEPZOOM_FORMAT
    if output_format in {"dzi", "szi", "zip"}:
        return Path(f"{output_path}.{output_format}")
    return output_path


def deepzoom_save_path(output_path: Path, output_format=None):
    output_format = output_format or DEEPZOOM_FORMAT
    if output_format == "dzi":
        return output_path
    return deepzoom_storage_path(output_path, output_format)


def deepzoom_exists(output_path: Path, output_format=None):
    output_format = output_format or DEEPZOOM_FORMAT
    storage_path = deepzoom_storage_path(output_path, output_format)
    if output_format == "dzi":
        tiles_folder = Path(str(output_path) + "_files")
        return (
            storage_path.is_file()
            and tiles_folder.exists()
            and tiles_folder.is_dir()
        )
    if output_format in {"szi", "zip"}:
        return storage_path.is_file()
    return (
        storage_path.is_dir()
        and any(storage_path.iterdir())
    )


# =========================================================
# CHECK THUMBNAIL
# =========================================================

def thumbnail_exists(output_folder: Path):
    """
    Check whether the thumbnail exists.
    """

    thumbnail_path = (
        output_folder / "thumbnail.jpg"
    )

    return (
        thumbnail_path.exists()
        and thumbnail_path.is_file()
    )


# =========================================================
# CREATE THUMBNAIL
# =========================================================

def create_thumbnail(
    image,
    output_path: Path,
):
    """
    Create a gallery thumbnail from an already
    loaded pyvips image.

    The thumbnail will fit inside:

        THUMBNAIL_SIZE x THUMBNAIL_SIZE

    while preserving the original aspect ratio.

    The image will never be upscaled.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    thumbnail = image.thumbnail_image(
        THUMBNAIL_SIZE,
        height=THUMBNAIL_SIZE,
        size="down",
    )

    thumbnail.write_to_file(
        str(output_path),
        Q=THUMBNAIL_QUALITY,
    )

    # Release thumbnail reference
    thumbnail = None


# =========================================================
# COPY DEEPZOOM
# =========================================================

def copy_deepzoom(
    source_path: Path,
    destination_path: Path,
    output_format=None,
):
    output_format = output_format or DEEPZOOM_FORMAT
    copy_start = time.perf_counter()
    source_storage = deepzoom_storage_path(source_path, output_format)
    destination_storage = deepzoom_storage_path(destination_path, output_format)
    source_thumbnail = (
        source_path.parent / "thumbnail.jpg"
    )
    destination_thumbnail = (
        destination_path.parent / "thumbnail.jpg"
    )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if output_format in {"dzi", "szi", "zip"}:
        if not source_storage.is_file():
            raise FileNotFoundError(f"DeepZoom output not found:\n{source_storage}")
        if output_format == "dzi":
            source_tiles = Path(str(source_path) + "_files")
            destination_tiles = Path(str(destination_path) + "_files")
            if not source_tiles.is_dir():
                raise FileNotFoundError(
                    f"Source tiles directory not found:\n{source_tiles}"
                )
            print("       Copying .dzi descriptor...")
            shutil.copy2(source_storage, destination_storage)
            print(
                f"       Copying tiles using robocopy "
                f"(/MT:{ROBOCOPY_THREADS})..."
            )
            _robocopy_copy_tree(source_tiles, destination_tiles)
        else:
            print(f"       Copying {output_format.upper()} archive...")
            shutil.copy2(source_storage, destination_storage)
    else:
        if not source_storage.is_dir():
            raise FileNotFoundError(
                f"DeepZoom output directory not found:\n{source_storage}"
            )
        print(
            f"       Copying {output_format} tiles using robocopy "
            f"(/MT:{ROBOCOPY_THREADS})..."
        )
        _robocopy_copy_tree(source_storage, destination_storage)
        source_properties = source_path.parent / "vips-properties.xml"
        if source_properties.is_file():
            shutil.copy2(
                source_properties,
                destination_path.parent / "vips-properties.xml",
            )

    if source_thumbnail.is_file():
        print("       Copying thumbnail...")
        shutil.copy2(source_thumbnail, destination_thumbnail)
    else:
        print("       WARNING: thumbnail.jpg not found.")

    copy_elapsed = (
        time.perf_counter()
        - copy_start
    )

    return copy_elapsed


def _robocopy_copy_tree(source_dir: Path, destination_dir: Path):
    destination_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "robocopy",
        str(source_dir),
        str(destination_dir),
        "/E",
        f"/MT:{ROBOCOPY_THREADS}",
        f"/R:{ROBOCOPY_RETRIES}",
        f"/W:{ROBOCOPY_WAIT}",
        "/NFL",
        "/NDL",
        "/NP",
        "/NJH",
        "/NJS",
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode >= 8:
        raise RuntimeError(
            "Robocopy failed.\n\n"
            f"Exit code: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )


# =========================================================
# CONVERT ONE WSI
# =========================================================

def convert_wsi(
    input_file: Path,
    current: int,
    total: int,
    _output=None,
):
    """
    Convert one WSI to DeepZoom once.

    Also generates a separate gallery thumbnail.

    Then copies the DeepZoom and thumbnail
    to any additional destinations.

    When _output is a dict, the per-slide metrics are written into it
    (instead of the module-level LAST_CONVERSION_METRICS) so that
    concurrent conversions do not clobber each other's results.
    """

    if _output is None:
        global LAST_CONVERSION_METRICS, LAST_CONVERSION_DURATION, LAST_CONVERSION_ERROR
    wsi_start = time.perf_counter()
    metrics = {
        "resolution": "",
        "load_seconds": None,
        "deepzoom_seconds": None,
        "thumbnail_seconds": None,
        "copy_seconds": None,
        "slide_seconds": None,
        "deepzoom_status": "Pending",
        "thumbnail_status": "Pending",
        "copy_destinations": [],
    }
    if _output is not None:
        _output.clear()
        _output.update(metrics)
    LAST_CONVERSION_METRICS = metrics
    report_progress("preparing", 0, 4, input_file, "Preparing slide", metrics)

    wsi_name = input_file.stem

    try:
        rel_path = input_file.relative_to(INPUT_DIR)
    except ValueError:
        rel_path = Path(input_file.name)
    rel_folder = rel_path.parent
    folder_name = str(rel_folder) if str(rel_folder) != "." else wsi_name

    # -----------------------------------------------------
    # Primary output
    # -----------------------------------------------------

    destination_dirs = (
        DESTINATION_DIRS
        if DESTINATION_DIRS is not None
        else [PRIMARY_OUTPUT_DIR, SECONDARY_OUTPUT_DIR]
    )
    primary_folder = destination_dirs[0] / folder_name

    primary_output = (
        primary_folder
        / wsi_name
    )
    primary_storage = deepzoom_storage_path(primary_output)

    primary_thumbnail = (
        primary_folder
        / "thumbnail.jpg"
    )

    additional_outputs = [
        (destination_dir / folder_name, destination_dir / folder_name / wsi_name)
        for destination_dir in destination_dirs[1:]
    ]
    metrics.update(
        {
            "input_file": str(input_file),
            "deepzoom_output": str(primary_storage),
            "thumbnail_output": str(primary_thumbnail),
            "copy_outputs": [
                str(deepzoom_storage_path(output))
                for _, output in additional_outputs
            ],
        }
    )

    # -----------------------------------------------------
    # Header
    # -----------------------------------------------------

    print()
    print("=" * 80)
    print(
        f"[{current}/{total}] "
        f"{folder_name}/{input_file.name}"
    )

    print("=" * 80)

    print()
    print(
        f"Input:"
        f"\n  {input_file}"
    )

    print()
    print(
        f"Primary:"
        f"\n  {primary_storage}"
    )

    print()
    print(
        f"Thumbnail:"
        f"\n  {primary_thumbnail}"
    )

    for destination_folder, destination_output in additional_outputs:
        print()
        print(
            f"Additional destination:"
            f"\n  {deepzoom_storage_path(destination_output)}"
        )

    try:

        image = None
        conversion_elapsed = 0
        thumbnail_elapsed = 0

        # =================================================
        # Check what already exists
        # =================================================

        dz_exists = deepzoom_exists(primary_output)

        thumb_exists = thumbnail_exists(
            primary_folder
        )

        if dz_exists and thumb_exists:
            metrics["deepzoom_status"] = "Skipped (already exists)"
            metrics["thumbnail_status"] = "Skipped (already exists)"
            report_progress(
                "preparing",
                0,
                4,
                input_file,
                "Already converted",
                metrics,
                file_index=current, files_total=total,
            )
            print()
            print("DeepZoom and thumbnail already exist. Skipping image load.")
            image = None
            load_elapsed = 0
            metrics["load_seconds"] = load_elapsed
        else:
            load_start = time.perf_counter()
            image = pyvips.Image.new_from_file(
                str(input_file),
                access="random",
            )
            load_elapsed = time.perf_counter() - load_start
            metrics["resolution"] = f"{image.width:,} x {image.height:,}"
            metrics["load_seconds"] = load_elapsed
            report_progress(
                "preparing",
                0,
                4,
                input_file,
                "Source image loaded",
                metrics,
                file_index=current, files_total=total,
            )
            print(f"Image size: {image.width:,} x {image.height:,}")
            print(f"Load time: {format_time(load_elapsed)}")

        # =================================================
        # STEP 1
        # DeepZoom conversion
        # =================================================

        if dz_exists:
            metrics["deepzoom_status"] = "Skipped (already exists)"

            report_progress(
                "deepzoom", 1, 4, input_file, "DeepZoom already exists", metrics,
                file_index=current, files_total=total,
            )

            print()
            print(
                "Primary DeepZoom already exists."
            )

            print(
                "Skipping conversion."
            )

        else:
            metrics["deepzoom_status"] = "Converting"
            report_progress(
                "deepzoom", 1, 4, input_file, "Converting to DeepZoom", metrics,
                file_index=current, files_total=total,
            )

            # ---------------------------------------------
            # Convert DeepZoom
            # ---------------------------------------------

            print()
            print(
                "Converting WSI → DeepZoom..."
            )

            conversion_start = (
                time.perf_counter()
            )

            primary_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            dzsave_options = {
                "layout": (
                    "dz"
                    if DEEPZOOM_FORMAT in {"dzi", "szi", "zip"}
                    else DEEPZOOM_FORMAT
                ),
                "suffix": f".jpeg[Q={JPEG_QUALITY}]",
            }
            if DEEPZOOM_FORMAT in {"szi", "zip"}:
                dzsave_options["container"] = DEEPZOOM_FORMAT
            image.dzsave(
                str(deepzoom_save_path(primary_output)),
                **dzsave_options,
            )

            conversion_elapsed = (
                time.perf_counter()
                - conversion_start
            )
            metrics["deepzoom_seconds"] = conversion_elapsed
            metrics["deepzoom_status"] = "Complete"
            report_progress(
                "deepzoom",
                2,
                4,
                input_file,
                "DeepZoom conversion complete",
                metrics,
                file_index=current, files_total=total,
            )

            print()
            print(
                "DeepZoom conversion complete."
            )

            print(
                f"Conversion time: "
                f"{format_time(conversion_elapsed)}"
            )

        # =================================================
        # STEP 2
        # Create thumbnail
        # =================================================

        if thumb_exists:
            metrics["thumbnail_status"] = "Skipped (already exists)"
            report_progress(
                "thumbnail", 2, 4, input_file, "Thumbnail already exists", metrics,
                file_index=current, files_total=total,
            )

            print()
            print(
                "Thumbnail already exists."
            )

            print(
                "Skipping thumbnail generation."
            )

        else:
            metrics["thumbnail_status"] = "Creating"
            report_progress(
                "thumbnail", 2, 4, input_file, "Creating thumbnail", metrics,
                file_index=current, files_total=total,
            )

            print()
            print(
                "Creating gallery thumbnail..."
            )

            thumbnail_start = (
                time.perf_counter()
            )

            create_thumbnail(
                image,
                primary_thumbnail,
            )

            thumbnail_elapsed = (
                time.perf_counter()
                - thumbnail_start
            )
            metrics["thumbnail_seconds"] = thumbnail_elapsed
            metrics["thumbnail_status"] = "Complete"
            report_progress(
                "thumbnail",
                2,
                4,
                input_file,
                "Thumbnail creation complete",
                metrics,
                file_index=current, files_total=total,
            )

            print()
            print(
                "Thumbnail creation complete."
            )

            print(
                f"Thumbnail time: "
                f"{format_time(thumbnail_elapsed)}"
            )

        # -------------------------------------------------
        # Release image
        # -------------------------------------------------

        image = None

        # =================================================
        # STEP 3
        # Copy to additional destinations
        # =================================================

        print()

        copy_elapsed = 0
        copy_results = []
        _copy_lock = threading.Lock()

        if additional_outputs:
            def copy_one_destination(index, destination_folder, destination_output):
                report_progress(
                    "copy",
                    2 + index / max(1, len(additional_outputs)),
                    4,
                    input_file,
                    f"Copying to destination {index} of {len(additional_outputs)}",
                    metrics,
                )
                secondary_exists = deepzoom_exists(destination_output)
                secondary_thumbnail_exists = (
                    destination_folder / "thumbnail.jpg"
                ).exists()

                if secondary_exists and secondary_thumbnail_exists:
                    result = {
                        "destination": str(destination_folder),
                        "status": "Skipped (already exists)",
                        "duration_seconds": 0,
                    }
                    with _copy_lock:
                        copy_results.append(result)
                        metrics["copy_destinations"] = list(copy_results)
                    print(
                        f"DeepZoom and thumbnail already exist at "
                        f"{destination_folder}. Skipping copy."
                    )
                    return index, result, 0, destination_output

                try:
                    destination_copy_elapsed = copy_deepzoom(
                        primary_output, destination_output
                    )
                except Exception as copy_error:
                    result = {
                        "destination": str(destination_folder),
                        "status": f"Failed: {copy_error}",
                        "duration_seconds": 0,
                    }
                    with _copy_lock:
                        copy_results.append(result)
                        metrics["copy_destinations"] = list(copy_results)
                    print(f"Copy to {destination_folder} failed: {copy_error}")
                    return index, result, 0, destination_output

                result = {
                    "destination": str(destination_folder),
                    "status": "Complete",
                    "duration_seconds": destination_copy_elapsed,
                }
                with _copy_lock:
                    copy_results.append(result)
                    metrics["copy_destinations"] = list(copy_results)
                return index, result, destination_copy_elapsed, destination_output

            with ThreadPoolExecutor(max_workers=CONVERSION_THREADS) as copy_executor:
                futures = [
                    copy_executor.submit(
                        copy_one_destination, index, folder, output
                    )
                    for index, (folder, output) in enumerate(
                        additional_outputs, start=1
                    )
                ]
                for future in as_completed(futures):
                    index, result, duration, dest_output = future.result()
                    copy_elapsed += duration
                    metrics["copy_seconds"] = copy_elapsed
                    report_progress(
                        "copy",
                        3,
                        4,
                        input_file,
                        f"Destination {index} copy complete",
                        metrics,
                    )
                    print()
                    print(
                        "DeepZoom copy complete: "
                        f"{deepzoom_storage_path(dest_output)}"
                    )
                    print(f"Copy time: {format_time(copy_elapsed)}")
        else:
            report_progress(
                "copy", 3, 4, input_file, "No additional destinations to copy"
            )

        # =================================================
        # TOTAL TIME FOR THIS WSI
        # =================================================

        wsi_elapsed = (
            time.perf_counter()
            - wsi_start
        )
        metrics["copy_seconds"] = copy_elapsed
        metrics["slide_seconds"] = wsi_elapsed
        if not additional_outputs:
            metrics["copy_destinations"] = []
        if metrics["deepzoom_status"] == "Pending":
            metrics["deepzoom_status"] = "Skipped"
        if metrics["thumbnail_status"] == "Pending":
            metrics["thumbnail_status"] = "Skipped"

        print()
        print(
            f"[{current}/{total}] COMPLETE"
        )
        report_progress(
            "complete", 4, 4, input_file, "Slide complete", metrics,
            file_index=current, files_total=total,
        )

        print(
            f"  Conversion : "
            f"{format_time(conversion_elapsed)}"
        )

        print(
            f"  Thumbnail  : "
            f"{format_time(thumbnail_elapsed)}"
        )

        print(
            f"  Copy       : "
            f"{format_time(copy_elapsed)}"
        )

        print(
            f"  WSI total  : "
            f"{format_time(wsi_elapsed)}"
        )

        return wsi_elapsed

    except Exception as e:
        if _output is None:
            global LAST_CONVERSION_DURATION, LAST_CONVERSION_ERROR
            LAST_CONVERSION_ERROR = str(e)
            LAST_CONVERSION_DURATION = time.perf_counter() - wsi_start
        metrics["slide_seconds"] = time.perf_counter() - wsi_start
        metrics["error"] = str(e)
        report_progress("error", 4, 4, input_file, "Slide failed", metrics,
                        file_index=current, files_total=total)

        wsi_elapsed = (
            time.perf_counter()
            - wsi_start
        )

        print()
        print(
            f"[{current}/{total}] ERROR"
        )

        print()
        print(
            f"File:"
            f"\n  {input_file}"
        )

        print()
        print(
            f"Error:"
            f"\n  {e}"
        )

        print()
        print(
            f"Time before error: "
            f"{format_time(wsi_elapsed)}"
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():
    global LAST_CONVERSION_DURATION, LAST_CONVERSION_ERROR
    global LAST_CONVERSION_METRICS, RUN_START_PERF
    global PROGRESS_FILE_INDEX, PROGRESS_FILE_TOTAL

    # -----------------------------------------------------
    # Validate configuration before doing any work
    # -----------------------------------------------------

    if DEEPZOOM_FORMAT not in {
        "dzi", "szi", "zip", "zoomify", "google", "iiif", "iiif3",
    }:
        raise ValueError(
            f"Unsupported DeepZoom output format: {DEEPZOOM_FORMAT!r}. "
            "Supported formats: dzi, szi, zip, zoomify, google, iiif, iiif3."
        )

    if not INPUT_DIR.is_dir():
        print()
        print("=" * 80)
        print("WSI → DeepZoom + Thumbnail Converter")
        print("=" * 80)
        print()
        print(
            f"Input directory:"
            f"\n  {INPUT_DIR}"
        )
        print()
        print(
            "ERROR: Input directory does not exist or is not accessible: "
            f"{INPUT_DIR}"
        )
        print()
        print(
            "Please set INPUT_DIR to an existing folder containing WSI files."
        )
        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "duration_seconds": 0,
            "results": [],
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "average_seconds": None,
            "error": f"Input directory does not exist: {INPUT_DIR}",
        }

    total_start = time.perf_counter()
    RUN_START_PERF = total_start
    run_started = time.strftime("%Y-%m-%d %H:%M:%S")

    print()
    print("=" * 80)
    print("WSI → DeepZoom + Thumbnail Converter")
    print("=" * 80)

    print()
    print(
        f"Input directory:"
        f"\n  {INPUT_DIR}"
    )

    print()
    print("Output destinations:")
    output_destinations = (
        DESTINATION_DIRS
        if DESTINATION_DIRS is not None
        else [PRIMARY_OUTPUT_DIR, SECONDARY_OUTPUT_DIR]
    )
    for destination_dir in output_destinations:
        print(f"  {destination_dir}")

    print()
    print(
        f"JPEG quality:"
        f" {JPEG_QUALITY}"
    )

    print(f"DeepZoom output format: {DEEPZOOM_FORMAT}")
    print(f"Input extensions: {', '.join(WSI_EXTENSIONS)}")

    print()
    print(
        f"Thumbnail max size:"
        f" {THUMBNAIL_SIZE} x "
        f"{THUMBNAIL_SIZE}"
    )

    print()
    print(
        f"Thumbnail quality:"
        f" {THUMBNAIL_QUALITY}"
    )

    print()
    print(
        f"Robocopy threads:"
        f" {ROBOCOPY_THREADS}"
    )

    # =====================================================
    # Find files with enabled WSI extensions
    # =====================================================

    print()
    print(
        "Searching for WSI files..."
    )

    if SELECTED_FILES is None:
        scan_key = str(INPUT_DIR.resolve())
        if scan_key not in _SCAN_CACHE:
            _SCAN_CACHE[scan_key] = common.find_wsi_files(INPUT_DIR, WSI_EXTENSIONS)
        wsi_files = _SCAN_CACHE[scan_key]
    else:
        wsi_files = sorted(Path(path) for path in SELECTED_FILES)

    total = len(wsi_files)
    report_progress("ready", 0, 4, message=f"Found {total} slide(s)")
    completed = 0
    failed = 0
    results = []
    processing_times = []

    print()
    print(
        f"Found {total} WSI files."
    )

    if total == 0:

        print()
        print("No WSI files with the enabled extensions were found.")

        return {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "duration_seconds": time.perf_counter() - total_start,
            "results": results,
            "started_at": run_started,
            "average_seconds": None,
        }

    # =====================================================
    # Statistics
    # =====================================================

    # =====================================================
    # Process files
    # =====================================================

    def _process_one(current, input_file):
        global PROGRESS_FILE_INDEX, PROGRESS_FILE_TOTAL
        global LAST_CONVERSION_ERROR, LAST_CONVERSION_DURATION, LAST_CONVERSION_METRICS
        PROGRESS_FILE_INDEX = current
        PROGRESS_FILE_TOTAL = total
        report_progress(
            "preparing",
            0,
            4,
            input_file,
            f"Starting slide {current} of {total}",
        )

        LAST_CONVERSION_ERROR = None
        LAST_CONVERSION_DURATION = None
        LAST_CONVERSION_METRICS = {}
        output = {}
        elapsed = convert_wsi(
            input_file,
            current,
            total,
            _output=output,
        )
        return {
            "current": current,
            "input_file": input_file,
            "elapsed": elapsed,
            "output": output,
            "error": LAST_CONVERSION_ERROR or "",
            "duration": LAST_CONVERSION_DURATION,
        }

    with ThreadPoolExecutor(max_workers=CONVERSION_THREADS) as executor:
        futures = [
            executor.submit(
                _process_one, current, input_file
            )
            for current, input_file in enumerate(wsi_files, start=1)
        ]
        for future in as_completed(futures):
            item = future.result()
            current = item["current"]
            input_file = item["input_file"]
            elapsed = item["elapsed"]
            output = item["output"]
            PROGRESS_FILE_INDEX = current
            PROGRESS_FILE_TOTAL = total
            results.append(
                {
                    "file": str(input_file),
                    "status": "complete" if elapsed is not None else "failed",
                    "duration_seconds": (
                        elapsed
                        if elapsed is not None
                        else item["duration"]
                    ),
                    "error": item["error"],
                    **output,
                }
            )

            if elapsed is None:

                failed += 1

            else:

                completed += 1

                processing_times.append(
                    elapsed
                )

            # -------------------------------------------------
            # Overall progress
            # -------------------------------------------------

            overall_elapsed = (
                time.perf_counter()
                - total_start
            )

            percentage = (
                current / total
            ) * 100
            report_progress(
                "complete" if elapsed is not None else "error",
                4,
                4,
                input_file,
                f"Completed {current} of {total} slides",
            )

            print()
            print(
                f"Overall progress: "
                f"{current}/{total} "
                f"({percentage:.1f}%)"
            )

            print(
                f"Total elapsed: "
                f"{format_time(overall_elapsed)}"
            )

    # =====================================================
    # Final statistics
    # =====================================================

    total_elapsed = (
        time.perf_counter()
        - total_start
    )

    print()
    print()
    print("=" * 80)
    report_progress("finished", 4, 4, message="All selected slides processed")
    print("ALL CONVERSIONS FINISHED")
    print("=" * 80)

    print()
    print(
        f"Total WSI files : {total}"
    )

    print(
        f"Completed       : {completed}"
    )

    print(
        f"Failed          : {failed}"
    )

    print(
        f"Total time      : "
        f"{format_time(total_elapsed)}"
    )

    if processing_times:

        average_time = (
            sum(processing_times)
            / len(processing_times)
        )

        print(
            f"Average / WSI   : "
            f"{format_time(average_time)}"
        )

    print()
    print("=" * 80)
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "duration_seconds": total_elapsed,
        "average_seconds": (
            sum(processing_times) / len(processing_times)
            if processing_times
            else None
        ),
        "results": results,
        "started_at": run_started,
    }


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()