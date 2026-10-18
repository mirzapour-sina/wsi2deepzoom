from pathlib import Path
import xml.etree.ElementTree as ET
import math
import csv
import time

from PIL import Image


# =========================================================
# CONFIGURATION
# =========================================================

# Original WSI directory
SOURCE_DIR = Path(
    r"D:\Edupat\Urmia-Medical-University\WSI"
)

# DeepZoom destination
DESTINATION_DIR = Path(
    r"D:\Edupat\Urmia-Medical-University\Deepzoom"
)

# Output CSV report
REPORT_FILE = Path(
    r"D:\Edupat\Urmia-Medical-University\deepzoom_verification_report.csv"
)


# =========================================================
# HELPERS
# =========================================================

def format_time(seconds):
    minutes = int(seconds // 60)
    seconds = seconds % 60

    if minutes:
        return f"{minutes:02d}:{seconds:05.2f}"

    return f"{seconds:05.2f}s"


def get_deepzoom_paths(destination):
    """
    Return:

        slide.dzi
        slide_files/
    """

    dzi_file = destination.with_suffix(".dzi")

    tiles_dir = Path(
        str(destination) + "_files"
    )

    return dzi_file, tiles_dir


# =========================================================
# READ DZI
# =========================================================

def read_dzi(dzi_file):
    """
    Read and validate the DeepZoom XML.

    Returns:

        {
            "width": ...,
            "height": ...,
            "tile_size": ...,
            "overlap": ...,
            "format": ...
        }

    or raises an exception.
    """

    try:
        tree = ET.parse(dzi_file)

    except Exception as e:
        raise RuntimeError(
            f"Invalid DZI XML: {e}"
        )

    root = tree.getroot()

    # Handle namespace
    namespace = ""

    if root.tag.startswith("{"):
        namespace = root.tag.split("}")[0] + "}"

    # -----------------------------------------------------
    # Image attributes
    # -----------------------------------------------------

    if root.tag != f"{namespace}Image":
        raise RuntimeError(
            "DZI root element is not <Image>"
        )

    tile_size = root.attrib.get(
        "TileSize"
    )

    overlap = root.attrib.get(
        "Overlap"
    )

    image_format = root.attrib.get(
        "Format"
    )

    if not tile_size:
        raise RuntimeError(
            "Missing TileSize"
        )

    if not image_format:
        raise RuntimeError(
            "Missing Format"
        )

    # -----------------------------------------------------
    # Size
    # -----------------------------------------------------

    size_element = root.find(
        f"{namespace}Size"
    )

    if size_element is None:
        raise RuntimeError(
            "Missing <Size>"
        )

    width = size_element.attrib.get(
        "Width"
    )

    height = size_element.attrib.get(
        "Height"
    )

    if not width or not height:
        raise RuntimeError(
            "Missing Width or Height"
        )

    return {
        "width": int(width),
        "height": int(height),
        "tile_size": int(tile_size),
        "overlap": int(overlap or 0),
        "format": image_format.lower(),
    }


# =========================================================
# EXPECTED DEEPZOOM LEVELS
# =========================================================

def expected_levels(width, height):
    """
    DeepZoom levels run from:

        0

    to:

        ceil(log2(max(width, height)))

    """

    max_dimension = max(
        width,
        height,
    )

    if max_dimension <= 1:
        return 1

    return (
        math.ceil(
            math.log2(max_dimension)
        )
        + 1
    )


# =========================================================
# VERIFY TILE
# =========================================================

def verify_tile(tile_file):
    """
    Verify that a JPEG tile is actually readable.

    verify() detects truncated/corrupt files.
    open/load actually decodes the image.
    """

    try:

        # First check file isn't empty
        if tile_file.stat().st_size == 0:
            return False, "Empty file"

        # Verify JPEG structure
        with Image.open(tile_file) as image:
            image.verify()

        # Actually decode the image
        with Image.open(tile_file) as image:
            image.load()

        return True, None

    except Exception as e:

        return False, str(e)


# =========================================================
# VERIFY ONE DEEPZOOM
# =========================================================

def verify_deepzoom(
    source_file,
    destination,
):
    """
    Verify one WSI's DeepZoom.

    Returns:

        status
        message
        statistics
    """

    dzi_file, tiles_dir = get_deepzoom_paths(
        destination
    )

    # -----------------------------------------------------
    # Check DZI
    # -----------------------------------------------------

    if not dzi_file.exists():

        return (
            "MISSING_DZI",
            f"Missing DZI: {dzi_file}",
            {}
        )

    if dzi_file.stat().st_size == 0:

        return (
            "BROKEN_DZI",
            "DZI file is empty",
            {}
        )

    # -----------------------------------------------------
    # Check tiles directory
    # -----------------------------------------------------

    if not tiles_dir.exists():

        return (
            "MISSING_TILES",
            f"Missing tiles directory: {tiles_dir}",
            {}
        )

    if not tiles_dir.is_dir():

        return (
            "BROKEN_TILES",
            "Tiles path is not a directory",
            {}
        )

    # -----------------------------------------------------
    # Read DZI
    # -----------------------------------------------------

    try:

        dzi = read_dzi(
            dzi_file
        )

    except Exception as e:

        return (
            "BROKEN_DZI",
            str(e),
            {}
        )

    width = dzi["width"]
    height = dzi["height"]
    tile_size = dzi["tile_size"]
    image_format = dzi["format"]

    # -----------------------------------------------------
    # Validate basic DZI values
    # -----------------------------------------------------

    if width <= 0 or height <= 0:

        return (
            "BROKEN_DZI",
            f"Invalid dimensions: {width}x{height}",
            {}
        )

    if tile_size <= 0:

        return (
            "BROKEN_DZI",
            f"Invalid tile size: {tile_size}",
            {}
        )

    if image_format not in (
        "jpeg",
        "jpg",
        "png",
        "webp",
    ):

        return (
            "BROKEN_DZI",
            f"Unsupported format: {image_format}",
            {}
        )

    # -----------------------------------------------------
    # Expected levels
    # -----------------------------------------------------

    level_count = expected_levels(
        width,
        height,
    )

    # -----------------------------------------------------
    # Verify every level
    # -----------------------------------------------------

    total_tiles = 0
    corrupt_tiles = 0
    missing_tiles = 0

    level_results = []

    for level in range(level_count):

        level_dir = (
            tiles_dir / str(level)
        )

        if not level_dir.exists():

            return (
                "MISSING_LEVEL",
                f"Missing level directory: {level}",
                {
                    "width": width,
                    "height": height,
                    "levels": level_count,
                },
            )

        # -------------------------------------------------
        # Expected dimensions at this level
        # -------------------------------------------------

        scale = 2 ** (
            level_count
            - level
            - 1
        )

        level_width = math.ceil(
            width / scale
        )

        level_height = math.ceil(
            height / scale
        )

        expected_columns = math.ceil(
            level_width / tile_size
        )

        expected_rows = math.ceil(
            level_height / tile_size
        )

        expected_tile_count = (
            expected_columns
            * expected_rows
        )

        level_tile_count = 0

        # -------------------------------------------------
        # Check every expected tile
        # -------------------------------------------------

        for row in range(
            expected_rows
        ):

            for column in range(
                expected_columns
            ):

                tile_file = (
                    level_dir
                    / f"{column}_{row}.{image_format}"
                )

                # -----------------------------------------
                # Missing tile
                # -----------------------------------------

                if not tile_file.exists():

                    missing_tiles += 1

                    continue

                # -----------------------------------------
                # Verify tile
                # -----------------------------------------

                ok, error = verify_tile(
                    tile_file
                )

                if not ok:

                    corrupt_tiles += 1

                    continue

                level_tile_count += 1

        total_tiles += level_tile_count

        level_results.append({
            "level": level,
            "expected": expected_tile_count,
            "valid": level_tile_count,
            "missing": (
                expected_tile_count
                - level_tile_count
            ),
        })

    # -----------------------------------------------------
    # Determine final status
    # -----------------------------------------------------

    if missing_tiles > 0:

        return (
            "INCOMPLETE",
            (
                f"Missing {missing_tiles} "
                f"tile(s)"
            ),
            {
                "width": width,
                "height": height,
                "tile_size": tile_size,
                "levels": level_count,
                "tiles": total_tiles,
                "missing": missing_tiles,
                "corrupt": corrupt_tiles,
            },
        )

    if corrupt_tiles > 0:

        return (
            "CORRUPT",
            (
                f"Found {corrupt_tiles} "
                f"corrupt tile(s)"
            ),
            {
                "width": width,
                "height": height,
                "tile_size": tile_size,
                "levels": level_count,
                "tiles": total_tiles,
                "missing": missing_tiles,
                "corrupt": corrupt_tiles,
            },
        )

    return (
        "OK",
        (
            f"{total_tiles:,} valid tiles, "
            f"{level_count} levels"
        ),
        {
            "width": width,
            "height": height,
            "tile_size": tile_size,
            "levels": level_count,
            "tiles": total_tiles,
            "missing": 0,
            "corrupt": 0,
        },
    )


# =========================================================
# FIND WSIs
# =========================================================

def find_wsis():

    return sorted(
        [
            *SOURCE_DIR.rglob("*.tif"),
            *SOURCE_DIR.rglob("*.tiff"),
        ]
    )


# =========================================================
# MAIN
# =========================================================

def main():

    start_time = time.perf_counter()

    print()
    print("=" * 80)
    print("WSI → DeepZoom Integrity Checker")
    print("=" * 80)

    print()
    print(
        f"Source:"
        f"\n  {SOURCE_DIR}"
    )

    print()
    print(
        f"Destination:"
        f"\n  {DESTINATION_DIR}"
    )

    # -----------------------------------------------------
    # Find source WSIs
    # -----------------------------------------------------

    wsis = find_wsis()

    total = len(wsis)

    print()
    print(
        f"Found {total} WSI files."
    )

    if total == 0:

        print(
            "\nNo WSI files found."
        )

        return

    # -----------------------------------------------------
    # Statistics
    # -----------------------------------------------------

    results = []

    ok_count = 0
    missing_count = 0
    incomplete_count = 0
    corrupt_count = 0
    error_count = 0

    # -----------------------------------------------------
    # Process
    # -----------------------------------------------------

    for current, source_file in enumerate(
        wsis,
        start=1,
    ):

        # Relative path from source
        relative_path = (
            source_file.relative_to(
                SOURCE_DIR
            )
        )

        # -------------------------------------------------
        # Determine destination
        #
        # Example:
        #
        # source:
        # new/patient1/slide.tif
        #
        # destination:
        # wsi/patient1/slide
        # -------------------------------------------------

        destination = (
            DESTINATION_DIR
            / relative_path.parent
            / source_file.stem
        )

        print()
        print(
            f"[{current}/{total}] "
            f"{relative_path}"
        )

        print(
            f"  Destination:"
            f"\n    {destination}.dzi"
        )

        file_start = time.perf_counter()

        try:

            status, message, stats = (
                verify_deepzoom(
                    source_file,
                    destination,
                )
            )

        except Exception as e:

            status = "ERROR"
            message = str(e)
            stats = {}

        elapsed = (
            time.perf_counter()
            - file_start
        )

        # -------------------------------------------------
        # Count status
        # -------------------------------------------------

        if status == "OK":
            ok_count += 1

        elif status == "INCOMPLETE":
            incomplete_count += 1

        elif status in (
            "MISSING_DZI",
            "MISSING_TILES",
            "MISSING_LEVEL",
        ):
            missing_count += 1

        elif status in (
            "CORRUPT",
            "BROKEN_DZI",
            "BROKEN_TILES",
        ):
            corrupt_count += 1

        else:
            error_count += 1

        # -------------------------------------------------
        # Display
        # -------------------------------------------------

        print(
            f"  Status: {status}"
        )

        print(
            f"  {message}"
        )

        if stats:

            print(
                f"  Dimensions: "
                f"{stats.get('width', '-')}"
                f" x "
                f"{stats.get('height', '-')}"
            )

            print(
                f"  Levels: "
                f"{stats.get('levels', '-')}"
            )

            print(
                f"  Valid tiles: "
                f"{stats.get('tiles', 0):,}"
            )

            print(
                f"  Missing tiles: "
                f"{stats.get('missing', 0):,}"
            )

            print(
                f"  Corrupt tiles: "
                f"{stats.get('corrupt', 0):,}"
            )

        print(
            f"  Time: "
            f"{format_time(elapsed)}"
        )

        # -------------------------------------------------
        # Save result
        # -------------------------------------------------

        results.append({
            "source": str(source_file),
            "destination": str(destination),
            "status": status,
            "message": message,
            "width": stats.get(
                "width",
                "",
            ),
            "height": stats.get(
                "height",
                "",
            ),
            "levels": stats.get(
                "levels",
                "",
            ),
            "tiles": stats.get(
                "tiles",
                "",
            ),
            "missing_tiles": stats.get(
                "missing",
                "",
            ),
            "corrupt_tiles": stats.get(
                "corrupt",
                "",
            ),
            "time_seconds": round(
                elapsed,
                2,
            ),
        })

        # -------------------------------------------------
        # Overall progress
        # -------------------------------------------------

        percentage = (
            current / total
        ) * 100

        total_elapsed = (
            time.perf_counter()
            - start_time
        )

        print(
            f"  Progress: "
            f"{current}/{total} "
            f"({percentage:.1f}%)"
        )

        print(
            f"  Total elapsed: "
            f"{format_time(total_elapsed)}"
        )

    # =====================================================
    # CSV REPORT
    # =====================================================

    print()
    print(
        "Writing CSV report..."
    )

    REPORT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "source",
        "destination",
        "status",
        "message",
        "width",
        "height",
        "levels",
        "tiles",
        "missing_tiles",
        "corrupt_tiles",
        "time_seconds",
    ]

    with REPORT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            results
        )

    # =====================================================
    # FINAL SUMMARY
    # =====================================================

    total_elapsed = (
        time.perf_counter()
        - start_time
    )

    print()
    print()
    print("=" * 80)
    print("VERIFICATION COMPLETE")
    print("=" * 80)

    print()
    print(
        f"Total WSIs       : {total}"
    )

    print(
        f"OK               : {ok_count}"
    )

    print(
        f"Missing          : {missing_count}"
    )

    print(
        f"Incomplete       : {incomplete_count}"
    )

    print(
        f"Corrupt          : {corrupt_count}"
    )

    print(
        f"Errors           : {error_count}"
    )

    print()
    print(
        f"Total time       : "
        f"{format_time(total_elapsed)}"
    )

    print()
    print(
        f"Report:"
        f"\n  {REPORT_FILE}"
    )

    print()
    print("=" * 80)

    # -----------------------------------------------------
    # Failed files summary
    # -----------------------------------------------------

    failed_results = [
        result
        for result in results
        if result["status"] != "OK"
    ]

    if failed_results:

        print()
        print("=" * 80)
        print("FILES REQUIRING ATTENTION")
        print("=" * 80)

        for result in failed_results:

            print()
            print(
                f"[{result['status']}] "
                f"{result['source']}"
            )

            print(
                f"    {result['message']}"
            )

        print()
        print("=" * 80)


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()