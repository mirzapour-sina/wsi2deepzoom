from pathlib import Path
import pyvips
import shutil
import time


# =========================================================
# CONFIGURATION
# =========================================================

# Directory containing the original WSI TIFF files
BASE_DIR = Path(r"D:\Edupat Data")

INPUT_DIR = BASE_DIR / "new"


# ---------------------------------------------------------
# Existing primary DeepZoom directory
# ---------------------------------------------------------

PRIMARY_OUTPUT_DIR = Path(
    r"C:\Users\Sina\Herd\edupat\storage\app\private\wsi"
)


# ---------------------------------------------------------
# Existing secondary DeepZoom directory
# ---------------------------------------------------------

SECONDARY_OUTPUT_DIR = Path(
    r"D:\Edupat Data\deepzoom"
)


# ---------------------------------------------------------
# Thumbnail settings
# ---------------------------------------------------------

THUMBNAIL_SIZE = 600

THUMBNAIL_QUALITY = 85


# =========================================================
# FORMAT TIME
# =========================================================

def format_time(seconds):

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
# CREATE THUMBNAIL
# =========================================================

def create_thumbnail(
    input_file: Path,
    output_path: Path,
):
    """
    Create a thumbnail directly from the WSI.

    The thumbnail fits inside:

        THUMBNAIL_SIZE x THUMBNAIL_SIZE

    while preserving aspect ratio.

    The original image is never upscaled.
    """

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image = pyvips.Image.thumbnail(
        str(input_file),
        THUMBNAIL_SIZE,
        height=THUMBNAIL_SIZE,
        size="down",
    )

    image.write_to_file(
        str(output_path),
        Q=THUMBNAIL_QUALITY,
    )


# =========================================================
# PROCESS ONE WSI
# =========================================================

def process_wsi(
    input_file: Path,
    current: int,
    total: int,
):
    start = time.perf_counter()

    folder_name = input_file.parent.name

    # -----------------------------------------------------
    # Output folders
    # -----------------------------------------------------

    primary_folder = (
        PRIMARY_OUTPUT_DIR
        / folder_name
    )

    secondary_folder = (
        SECONDARY_OUTPUT_DIR
        / folder_name
    )

    primary_thumbnail = (
        primary_folder
        / "thumbnail.jpg"
    )

    secondary_thumbnail = (
        secondary_folder
        / "thumbnail.jpg"
    )

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
        f"Primary thumbnail:"
        f"\n  {primary_thumbnail}"
    )

    print()
    print(
        f"Secondary thumbnail:"
        f"\n  {secondary_thumbnail}"
    )

    try:

        # =================================================
        # Primary thumbnail
        # =================================================

        if primary_thumbnail.exists():

            print()
            print(
                "Primary thumbnail already exists."
            )

            print(
                "Skipping."
            )

        else:

            print()
            print(
                "Creating primary thumbnail..."
            )

            thumbnail_start = (
                time.perf_counter()
            )

            create_thumbnail(
                input_file,
                primary_thumbnail,
            )

            thumbnail_elapsed = (
                time.perf_counter()
                - thumbnail_start
            )

            print(
                f"Primary thumbnail created "
                f"in {format_time(thumbnail_elapsed)}"
            )

        # =================================================
        # Secondary thumbnail
        # =================================================

        if secondary_thumbnail.exists():

            print()
            print(
                "Secondary thumbnail already exists."
            )

            print(
                "Skipping."
            )

        else:

            print()
            print(
                "Copying thumbnail to "
                "secondary location..."
            )

            secondary_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            copy_start = (
                time.perf_counter()
            )

            shutil.copy2(
                primary_thumbnail,
                secondary_thumbnail,
            )

            copy_elapsed = (
                time.perf_counter()
                - copy_start
            )

            print(
                f"Thumbnail copied "
                f"in {format_time(copy_elapsed)}"
            )

        # =================================================
        # Done
        # =================================================

        elapsed = (
            time.perf_counter()
            - start
        )

        print()
        print(
            f"[{current}/{total}] COMPLETE"
        )

        print(
            f"  Total time : "
            f"{format_time(elapsed)}"
        )

        return elapsed

    except Exception as e:

        elapsed = (
            time.perf_counter()
            - start
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
            f"{format_time(elapsed)}"
        )

        return None


# =========================================================
# MAIN
# =========================================================

def main():

    total_start = time.perf_counter()

    print()
    print("=" * 80)
    print("WSI Thumbnail Generator")
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
        f"Thumbnail size:"
        f" {THUMBNAIL_SIZE} x "
        f"{THUMBNAIL_SIZE} maximum"
    )

    print()
    print(
        f"JPEG quality:"
        f" {THUMBNAIL_QUALITY}"
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
    # Process
    # =====================================================

    for current, input_file in enumerate(
        tiff_files,
        start=1,
    ):

        elapsed = process_wsi(
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
    print("ALL THUMBNAILS FINISHED")
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