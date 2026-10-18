from pathlib import Path
import pyvips
import time


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

BASE_DIR = Path(r"D:\Edupat Data")

INPUT_DIR = BASE_DIR / "new"

OUTPUT_DIRS = [
    Path(r"C:\Users\Sina\Herd\edupat\storage\app\private\wsi"),
    Path(r"D:\Edupat Data\deepzoom"),
]

JPEG_QUALITY = 85


# ---------------------------------------------------------
# Format elapsed time
# ---------------------------------------------------------

def format_time(seconds):
    """Convert seconds to HH:MM:SS."""

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"

    return f"{minutes:02d}:{seconds:05.2f}"


# ---------------------------------------------------------
# Convert one WSI
# ---------------------------------------------------------

def convert_wsi(input_file: Path, current: int, total: int):

    wsi_start = time.perf_counter()

    folder_name = input_file.parent.name
    wsi_name = input_file.stem

    print()
    print("=" * 80)
    print(
        f"[{current}/{total}] "
        f"Converting: {folder_name}/{input_file.name}"
    )
    print("=" * 80)

    try:

        # -------------------------------------------------
        # Load WSI
        # -------------------------------------------------

        image = pyvips.Image.new_from_file(
            str(input_file),
            access="sequential",
        )

        print(
            f"Image size: "
            f"{image.width:,} x {image.height:,}"
        )

        # -------------------------------------------------
        # Convert to every output directory
        # -------------------------------------------------

        for output_number, output_base in enumerate(
            OUTPUT_DIRS,
            start=1,
        ):

            output_start = time.perf_counter()

            output_folder = output_base / folder_name
            output_path = output_folder / wsi_name

            output_folder.mkdir(
                parents=True,
                exist_ok=True,
            )

            dzi_file = output_path.with_suffix(".dzi")
            tiles_folder = Path(str(output_path) + "_files")

            # ---------------------------------------------
            # Skip already converted
            # ---------------------------------------------

            if dzi_file.exists() and tiles_folder.exists():

                print(
                    f"\n  [{output_number}/{len(OUTPUT_DIRS)}] "
                    f"SKIP"
                )

                print(
                    f"       {output_path}"
                )

                continue

            # ---------------------------------------------
            # Convert
            # ---------------------------------------------

            print(
                f"\n  [{output_number}/{len(OUTPUT_DIRS)}] "
                f"Converting..."
            )

            print(
                f"       Output: {output_path}"
            )

            image.dzsave(
                str(output_path),
                suffix=f".jpeg[Q={JPEG_QUALITY}]",
            )

            output_elapsed = time.perf_counter() - output_start

            print(
                f"       DONE "
                f"({format_time(output_elapsed)})"
            )

        # -------------------------------------------------
        # WSI total time
        # -------------------------------------------------

        wsi_elapsed = time.perf_counter() - wsi_start

        print()
        print(
            f"[{current}/{total}] COMPLETE"
        )
        print(
            f"WSI time: {format_time(wsi_elapsed)}"
        )

        return wsi_elapsed

    except Exception as e:

        wsi_elapsed = time.perf_counter() - wsi_start

        print()
        print(
            f"[{current}/{total}] ERROR"
        )
        print(f"File: {input_file}")
        print(f"Error: {e}")
        print(
            f"Time before error: "
            f"{format_time(wsi_elapsed)}"
        )

        return 0


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------

def main():

    total_start = time.perf_counter()

    print()
    print("WSI → DeepZoom Converter")
    print("=" * 80)

    print(f"Input directory : {INPUT_DIR}")

    print("Output locations:")
    for output_dir in OUTPUT_DIRS:
        print(f"  - {output_dir}")

    # -----------------------------------------------------
    # Find TIFF files
    # -----------------------------------------------------

    tiff_files = [
        *INPUT_DIR.rglob("*.tif"),
        *INPUT_DIR.rglob("*.tiff"),
    ]

    total = len(tiff_files)

    print()
    print(f"WSI files found: {total}")

    if total == 0:
        print("No TIFF files found.")
        return

    # -----------------------------------------------------
    # Process
    # -----------------------------------------------------

    completed_times = []

    for current, input_file in enumerate(
        tiff_files,
        start=1,
    ):

        elapsed = convert_wsi(
            input_file,
            current,
            total,
        )

        if elapsed > 0:
            completed_times.append(elapsed)

        # ---------------------------------------------
        # Overall progress
        # ---------------------------------------------

        overall_elapsed = time.perf_counter() - total_start

        percentage = (current / total) * 100

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

    # -----------------------------------------------------
    # Final statistics
    # -----------------------------------------------------

    total_elapsed = time.perf_counter() - total_start

    print()
    print("=" * 80)
    print("ALL CONVERSIONS FINISHED")
    print("=" * 80)

    print(
        f"WSIs processed : {total}"
    )

    print(
        f"Total time     : "
        f"{format_time(total_elapsed)}"
    )

    if completed_times:

        average_time = (
            sum(completed_times)
            / len(completed_times)
        )

        print(
            f"Average / WSI  : "
            f"{format_time(average_time)}"
        )

    print("=" * 80)


if __name__ == "__main__":
    main()