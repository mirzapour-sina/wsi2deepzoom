from pathlib import Path
import pyvips
import shutil
import subprocess
import time


# =========================================================
# CONFIGURATION
# =========================================================

# Base directory containing the "new" folder
BASE_DIR = Path(r"D:\Edupat Data")

# Input WSI directory
INPUT_DIR = BASE_DIR / "new"


# ---------------------------------------------------------
# Primary DeepZoom destination
# ---------------------------------------------------------
# Laravel / Edupat storage

PRIMARY_OUTPUT_DIR = Path(
    r"C:\Users\Sina\Herd\edupat\storage\app\private\wsi"
)


# ---------------------------------------------------------
# Secondary DeepZoom destination
# ---------------------------------------------------------
# CHANGE THIS TO YOUR ACTUAL SECOND PATH

SECONDARY_OUTPUT_DIR = Path(
    r"D:\Edupat Data\deepzoom"
)


# ---------------------------------------------------------
# DeepZoom settings
# ---------------------------------------------------------

JPEG_QUALITY = 85


# ---------------------------------------------------------
# Robocopy settings
# ---------------------------------------------------------

# Number of parallel copy threads
ROBOCOPY_THREADS = 16

# Number of retries
ROBOCOPY_RETRIES = 2

# Wait between retries, in seconds
ROBOCOPY_WAIT = 1


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
# COPY DEEPZOOM USING ROBOCOPY
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

    Robocopy is used for the tile directory because
    DeepZoom can contain a very large number of small
    JPEG files.
    """

    copy_start = time.perf_counter()

    source_dzi = source_path.with_suffix(
        ".dzi"
    )

    source_tiles = Path(
        str(source_path) + "_files"
    )

    destination_dzi = destination_path.with_suffix(
        ".dzi"
    )

    destination_tiles = Path(
        str(destination_path) + "_files"
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

        # /E = copy all subdirectories including empty ones
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

        # Don't show progress for every file
        "/NP",

        # Don't show extra headers
        "/NJH",

        # Don't show summary
        # Remove this if you want robocopy statistics
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
    # 0-7 = success / successful with differences
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

    Then copy the DeepZoom to the second location.
    """

    wsi_start = time.perf_counter()

    folder_name = input_file.parent.name

    wsi_name = input_file.stem

    # -----------------------------------------------------
    # Primary output
    # -----------------------------------------------------

    primary_folder = (
        PRIMARY_OUTPUT_DIR
        / folder_name
    )

    primary_output = (
        primary_folder
        / wsi_name
    )

    # -----------------------------------------------------
    # Secondary output
    # -----------------------------------------------------

    secondary_folder = (
        SECONDARY_OUTPUT_DIR
        / folder_name
    )

    secondary_output = (
        secondary_folder
        / wsi_name
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
        f"\n  {primary_output}.dzi"
    )

    print()
    print(
        f"Secondary:"
        f"\n  {secondary_output}.dzi"
    )

    try:

        # =================================================
        # STEP 1
        # Convert to primary location
        # =================================================

        if deepzoom_exists(
            primary_output
        ):

            print()
            print(
                "Primary DeepZoom already exists."
            )

            print(
                "Skipping conversion."
            )

            conversion_elapsed = 0

        else:

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
            # Convert
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

            # Release image reference
            image = None

        # =================================================
        # STEP 2
        # Copy to secondary location
        # =================================================

        print()

        if deepzoom_exists(
            secondary_output
        ):

            print(
                "Secondary DeepZoom already exists."
            )

            print(
                "Skipping copy."
            )

            copy_elapsed = 0

        else:

            copy_elapsed = copy_deepzoom(
                primary_output,
                secondary_output,
            )

            print()
            print(
                "DeepZoom copy complete."
            )

            print(
                f"Copy time: "
                f"{format_time(copy_elapsed)}"
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

        print(
            f"  Conversion : "
            f"{format_time(conversion_elapsed)}"
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

    total_start = time.perf_counter()

    print()
    print("=" * 80)
    print("WSI → DeepZoom Converter")
    print("=" * 80)

    print()
    print(
        f"Input directory:"
        f"\n  {INPUT_DIR}"
    )

    print()
    print(
        f"Primary output:"
        f"\n  {PRIMARY_OUTPUT_DIR}"
    )

    print()
    print(
        f"Secondary output:"
        f"\n  {SECONDARY_OUTPUT_DIR}"
    )

    print()
    print(
        f"JPEG quality:"
        f" {JPEG_QUALITY}"
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

    tiff_files = sorted(
        [
            *INPUT_DIR.rglob("*.tif"),
            *INPUT_DIR.rglob("*.tiff"),
        ]
    )

    total = len(tiff_files)

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