from pathlib import Path
import pyvips
import shutil
import subprocess
import time


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
SELECTED_FILES = None
DESTINATION_DIRS = None
PROGRESS_CALLBACK = None
PROGRESS_FILE_INDEX = 0
PROGRESS_FILE_TOTAL = 0


def report_progress(stage, current, total, input_file=None, message=""):
    if PROGRESS_CALLBACK is not None:
        PROGRESS_CALLBACK(
            {
                "stage": stage,
                "stage_value": current,
                "current": current,
                "total": total,
                "file": str(input_file) if input_file is not None else "",
                "message": message,
                "file_index": PROGRESS_FILE_INDEX,
                "files_total": PROGRESS_FILE_TOTAL,
                "completed_files": (
                    PROGRESS_FILE_INDEX
                    if stage in {"complete", "error", "finished"}
                    else max(0, PROGRESS_FILE_INDEX - 1)
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

def deepzoom_exists(output_path: Path):
    """
    Check whether a DeepZoom output exists.

    Expected:

        slide.dzi
        slide_files/
    """

    dzi_file = output_path.with_suffix(
        ".dzi"
    )

    tiles_folder = Path(
        str(output_path) + "_files"
    )

    return (
        dzi_file.exists()
        and tiles_folder.exists()
        and tiles_folder.is_dir()
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
):
    """
    Copy a DeepZoom using Windows robocopy.

    Copies:

        slide.dzi
        slide_files/
        thumbnail.jpg
    """

    copy_start = time.perf_counter()

    source_dzi = source_path.with_suffix(
        ".dzi"
    )

    source_tiles = Path(
        str(source_path) + "_files"
    )

    source_thumbnail = (
        source_path.parent / "thumbnail.jpg"
    )

    destination_dzi = destination_path.with_suffix(
        ".dzi"
    )

    destination_tiles = Path(
        str(destination_path) + "_files"
    )

    destination_thumbnail = (
        destination_path.parent / "thumbnail.jpg"
    )

    # -----------------------------------------------------
    # Validate source
    # -----------------------------------------------------

    if not source_dzi.exists():
        raise FileNotFoundError(
            f"Source DZI not found:\n"
            f"{source_dzi}"
        )

    if not source_tiles.exists():
        raise FileNotFoundError(
            f"Source tiles directory not found:\n"
            f"{source_tiles}"
        )

    # -----------------------------------------------------
    # Create destination directory
    # -----------------------------------------------------

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination_tiles.mkdir(
        parents=True,
        exist_ok=True,
    )

    # -----------------------------------------------------
    # Copy .dzi
    # -----------------------------------------------------

    print(
        "       Copying .dzi..."
    )

    shutil.copy2(
        source_dzi,
        destination_dzi,
    )

    # -----------------------------------------------------
    # Copy thumbnail
    # -----------------------------------------------------

    if source_thumbnail.exists():

        print(
            "       Copying thumbnail..."
        )

        shutil.copy2(
            source_thumbnail,
            destination_thumbnail,
        )

    else:

        print(
            "       WARNING: "
            "thumbnail.jpg not found."
        )

    # -----------------------------------------------------
    # Copy tiles using robocopy
    # -----------------------------------------------------

    print(
        f"       Copying tiles "
        f"using robocopy "
        f"(/MT:{ROBOCOPY_THREADS})..."
    )

    command = [
        "robocopy",

        # Source
        str(source_tiles),

        # Destination
        str(destination_tiles),

        # Copy all subdirectories
        "/E",

        # Multi-threaded copy
        f"/MT:{ROBOCOPY_THREADS}",

        # Retry count
        f"/R:{ROBOCOPY_RETRIES}",

        # Wait between retries
        f"/W:{ROBOCOPY_WAIT}",

        # Don't list file names
        "/NFL",

        # Don't list directory names
        "/NDL",

        # Don't show progress
        "/NP",

        # Don't show headers
        "/NJH",

        # Don't show summary
        "/NJS",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    # -----------------------------------------------------
    # Robocopy exit codes
    #
    # 0-7 = success
    # 8+  = failure
    # -----------------------------------------------------

    if result.returncode >= 8:

        raise RuntimeError(
            "Robocopy failed.\n\n"
            f"Exit code: {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    copy_elapsed = (
        time.perf_counter()
        - copy_start
    )

    return copy_elapsed


# =========================================================
# CONVERT ONE WSI
# =========================================================

def convert_wsi(
    input_file: Path,
    current: int,
    total: int,
):
    """
    Convert one WSI to DeepZoom once.

    Also generates a separate gallery thumbnail.

    Then copies the DeepZoom and thumbnail
    to any additional destinations.
    """

    wsi_start = time.perf_counter()
    report_progress("preparing", 0, 4, input_file, "Preparing slide")

    folder_name = input_file.parent.name

    wsi_name = input_file.stem

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

    primary_thumbnail = (
        primary_folder
        / "thumbnail.jpg"
    )

    additional_outputs = [
        (destination_dir / folder_name, destination_dir / folder_name / wsi_name)
        for destination_dir in destination_dirs[1:]
    ]

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
        f"\n  {primary_output}.dzi"
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
            f"\n  {destination_output}.dzi"
        )

    try:

        conversion_elapsed = 0
        thumbnail_elapsed = 0

        # =================================================
        # Check what already exists
        # =================================================

        dz_exists = deepzoom_exists(
            primary_output
        )

        thumb_exists = thumbnail_exists(
            primary_folder
        )

        # =================================================
        # STEP 1
        # DeepZoom conversion
        # =================================================

        if dz_exists:
            report_progress("deepzoom", 1, 4, input_file, "DeepZoom already exists")

            print()
            print(
                "Primary DeepZoom already exists."
            )

            print(
                "Skipping conversion."
            )

        else:
            report_progress("deepzoom", 1, 4, input_file, "Converting to DeepZoom")

            print()
            print(
                "Loading WSI..."
            )

            load_start = time.perf_counter()

            image = pyvips.Image.new_from_file(
                str(input_file),
                access="sequential",
            )

            load_elapsed = (
                time.perf_counter()
                - load_start
            )

            print(
                f"Image size: "
                f"{image.width:,} x "
                f"{image.height:,}"
            )

            print(
                f"Load time: "
                f"{format_time(load_elapsed)}"
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

            image.dzsave(
                str(primary_output),
                suffix=(
                    f".jpeg[Q={JPEG_QUALITY}]"
                ),
            )

            conversion_elapsed = (
                time.perf_counter()
                - conversion_start
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
            report_progress("thumbnail", 2, 4, input_file, "Thumbnail already exists")

            print()
            print(
                "Thumbnail already exists."
            )

            print(
                "Skipping thumbnail generation."
            )

        else:
            report_progress("thumbnail", 2, 4, input_file, "Creating thumbnail")

            print()
            print(
                "Creating gallery thumbnail..."
            )

            thumbnail_start = (
                time.perf_counter()
            )

            # Load WSI if we skipped the
            # DeepZoom conversion above.
            if dz_exists:

                print(
                    "       Loading WSI for thumbnail..."
                )

                image = pyvips.Image.new_from_file(
                    str(input_file),
                    access="sequential",
                )

                print(
                    f"       Image size: "
                    f"{image.width:,} x "
                    f"{image.height:,}"
                )

            create_thumbnail(
                image,
                primary_thumbnail,
            )

            thumbnail_elapsed = (
                time.perf_counter()
                - thumbnail_start
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
        for index, (destination_folder, destination_output) in enumerate(
            additional_outputs, start=1
        ):
            report_progress(
                "copy",
                2 + index / max(1, len(additional_outputs)),
                4,
                input_file,
                f"Copying to destination {index} of {len(additional_outputs)}",
            )
            secondary_exists = deepzoom_exists(destination_output)
            secondary_thumbnail_exists = (
                destination_folder / "thumbnail.jpg"
            ).exists()

            if secondary_exists and secondary_thumbnail_exists:
                print(
                    f"DeepZoom and thumbnail already exist at "
                    f"{destination_folder}. Skipping copy."
                )
                continue

            copy_elapsed += copy_deepzoom(primary_output, destination_output)
            print()
            print(f"DeepZoom copy complete: {destination_output}.dzi")
            print(f"Copy time: {format_time(copy_elapsed)}")
        if not additional_outputs:
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

        print()
        print(
            f"[{current}/{total}] COMPLETE"
        )
        report_progress("complete", 4, 4, input_file, "Slide complete")

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
        report_progress("error", 4, 4, input_file, "Slide failed")

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
    global PROGRESS_FILE_INDEX, PROGRESS_FILE_TOTAL

    total_start = time.perf_counter()

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
    # Find TIFF files
    # =====================================================

    print()
    print(
        "Searching for WSI files..."
    )

    if SELECTED_FILES is None:
        tiff_files = sorted(
            [
                *INPUT_DIR.rglob("*.tif"),
                *INPUT_DIR.rglob("*.tiff"),
            ]
        )
    else:
        tiff_files = sorted(Path(path) for path in SELECTED_FILES)

    total = len(tiff_files)
    report_progress("ready", 0, 4, message=f"Found {total} slide(s)")

    print()
    print(
        f"Found {total} WSI files."
    )

    if total == 0:

        print()
        print(
            "No TIFF files found."
        )

        return

    # =====================================================
    # Statistics
    # =====================================================

    completed = 0
    failed = 0

    processing_times = []

    # =====================================================
    # Process files
    # =====================================================

    for current, input_file in enumerate(
        tiff_files,
        start=1,
    ):
        PROGRESS_FILE_INDEX = current
        PROGRESS_FILE_TOTAL = total
        report_progress(
            "preparing",
            0,
            4,
            input_file,
            f"Starting slide {current} of {total}",
        )

        elapsed = convert_wsi(
            input_file,
            current,
            total,
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


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()