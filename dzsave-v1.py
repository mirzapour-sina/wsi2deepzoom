from pathlib import Path
import pyvips

INPUT_DIR = Path(r"D:\wsi")
OUTPUT_DIR = Path(r"D:\wsi_deepzoom")

JPEG_QUALITY = 85


def convert_wsi(input_path: Path):
    # Preserve the input folder structure
    relative_path = input_path.relative_to(INPUT_DIR)

    # Example:
    # D:\wsi\patient1\1.tif
    #
    # becomes:
    # D:\wsi_deepzoom\patient1\1
    output_path = OUTPUT_DIR / relative_path.parent / input_path.stem

    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Converting:")
    print(f"  Input : {input_path}")
    print(f"  Output: {output_path}")

    image = pyvips.Image.new_from_file(
        str(input_path),
        access="sequential",
    )

    image.dzsave(
        str(output_path),
        suffix=".jpeg[Q=85]",
    )

    print("  Done\n")


def main():
    tiff_files = list(INPUT_DIR.rglob("*.tif"))
    tiff_files += list(INPUT_DIR.rglob("*.tiff"))

    print(f"Found {len(tiff_files)} TIFF files.\n")

    for input_path in tiff_files:
        try:
            convert_wsi(input_path)
        except Exception as e:
            print(f"ERROR processing {input_path}: {e}")


if __name__ == "__main__":
    main()