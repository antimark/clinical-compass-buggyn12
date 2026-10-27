"""Linux still-image codec worker; private temporary paths supplied by parent only."""
import resource
import sys
import warnings


def main():
    # Apply hard limits before loading third-party codecs or image pixels.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (8, 8))
    from PIL import Image, ImageOps, ImageFile
    from .profile_photos import MAX_BYTES, MAX_DIMENSION, MAX_PIXELS
    from pathlib import Path
    if len(sys.argv) != 5:
        return 1
    source, destination = Path(sys.argv[1]), Path(sys.argv[2])
    expected = (int(sys.argv[3]), int(sys.argv[4]))
    if not (0 < source.stat().st_size <= MAX_BYTES
            and all(1 <= value <= MAX_DIMENSION for value in expected)
            and expected[0] * expected[1] <= MAX_PIXELS):
        return 1
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    formats = ('JPEG', 'PNG', 'WEBP')
    with Image.open(source, formats=formats) as image:
        if image.size != expected or getattr(image, 'is_animated', False) or getattr(image, 'n_frames', 1) != 1:
            return 1
        image.verify()
    with Image.open(source, formats=formats) as image:
        image.load()
        oriented = ImageOps.exif_transpose(image)
        mode = 'RGBA' if 'A' in oriented.getbands() or 'transparency' in oriented.info else 'RGB'
        # A fresh raster discards EXIF, ICC, textual and source filename metadata.
        raster = Image.new(mode, oriented.size)
        raster.paste(oriented.convert(mode))
        raster.thumbnail((512, 512), Image.Resampling.LANCZOS)
        raster.save(destination, format='PNG', compress_level=6)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1) from None
