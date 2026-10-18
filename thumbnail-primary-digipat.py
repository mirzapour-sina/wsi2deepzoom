from pathlib import Path
import pyvips
import time


# =========================================================
# CONFIGURATION
# =========================================================

# Directory containing the original WSI TIFF files
BASE_DIR = Path(r"D:\Edupat Data")

INPUT_DIR = BASE_DIR / "Van"


# ---------------------------------------------------------
# Existing primary DeepZoom directory
# ---------------------------------------------------------
# Laravel / Edupat storage

PRIMARY_OUTPUT_DIR = Path(
    r"D:\Edupat Data\storage"
)


# ---------------------------------------------------------
# Thumbnail settings
# ---------------------------------------------------------

# Maximum width/height.
#
# The original aspect ratio is preserved.
#
# Examples:
#
# 10000 x 5000 -> 600 x 300
# 5000 x 5000  -> 600 x 600
# 3000 x 10000 -> 180 x 600
#
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
    Create a gallery thumbnail directly from the WSI.

    Maximum dimensions:

        THUMBNAIL_SIZE x THUMBNAIL_SIZE

    Original aspect ratio is preserved.

    The image will never be upscaled.
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

    # -----------------------------------------------------
    # The WSI folder name is the parent directory name.
    #
    # Example:
    #
    # D:\Edupat Data\new\123\slide.tif
    #
    # -> folder_name = "123"
    # -----------------------------------------------------

    folder_name = input_file.parent.name

    primary_folder = (
        PRIMARY_OUTPUT_DIR
        / folder_name
    )

    thumbnail_path = (
        primary_folder
        / "thumbnail.jpg"
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
        f"Thumbnail:"
        f"\n  {thumbnail_path}"
    )

    try:

        # =================================================
        # Check existing thumbnail
        # =================================================

        if thumbnail_path.exists():

            print()
            print(
                "Thumbnail already exists."
            )

            print(
                "Skipping."
            )

        else:

            print()
            print(
                "Creating thumbnail..."
            )

            thumbnail_start = (
                time.perf_counter()
            )

            create_thumbnail(
                input_file,
                thumbnail_path,
            )

            thumbnail_elapsed = (
                time.perf_counter()
                - thumbnail_start
            )

            print()
            print(
                "Thumbnail created successfully."
            )

            print(
                f"Thumbnail time: "
                f"{format_time(thumbnail_elapsed)}"
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
            f"  Total time: "
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
        f"Thumbnail maximum size:"
        f" {THUMBNAIL_SIZE} x "
        f"{THUMBNAIL_SIZE}"
    )

    print()
    print(
        f"Thumbnail JPEG quality:"
        f" {THUMBNAIL_QUALITY}"
    )

    # =====================================================
    # Find TIFF files
    # =====================================================

    print()
    print(
        "Searching for WSI files..."
    )

    wsi_files = sorted(
        file
        for file in INPUT_DIR.rglob("*")
        if file.is_file()
        and file.suffix.lower() in {
            ".tif",
            ".tiff",
            ".svs",
        }
    )

    total = len(wsi_files)

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
    skipped = 0

    processing_times = []

    # =====================================================
    # Process files
    # =====================================================

    for current, input_file in enumerate(
        wsi_files,
        start=1,
    ):

        # Check whether thumbnail already exists
        folder_name = input_file.parent.name

        thumbnail_path = (
            PRIMARY_OUTPUT_DIR
            / folder_name
            / "thumbnail.jpg"
        )

        already_exists = (
            thumbnail_path.exists()
        )

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

            if already_exists:
                skipped += 1

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
        f"Skipped         : {skipped}"
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