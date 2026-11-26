"""
Read *any* image a phone, camera or design tool is likely to hand us.

    load_any(data, max_side=2400) -> PIL.Image  (RGB, EXIF-rotated, downscaled)

Handles: JPG · JPEG · PNG · HEIC · HEIF · AVIF · WebP · TIFF (multi-page) · BMP · GIF
         (animated / first frame) · JPEG 2000 · PSD (flattened) · ICO · and camera RAW
         (.dng .cr2 .cr3 .nef .arw .orf .rw2 .raf .srw .pef .x3f) via the embedded preview.

It also copes with the things that usually break a naive `Image.open`:
* HEIC/HEIF from iPhones (via pillow-heif, registered automatically)
* EXIF orientation — portrait phone shots are rotated upright instead of sideways
* transparency — optionally preserved (so a PNG cut-out goes straight through)
* 16-bit / CMYK / palette / grey images → 8-bit RGB
* huge files (48 MP phones, camera RAW) → downscaled before anything else touches them
* slightly truncated files — decoded as far as possible instead of failing outright
"""
import io
import os

from PIL import Image, ImageFile, ImageOps

# tolerate mildly damaged phone files, and allow big camera images (we downscale right away)
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 300_000_000

# --- optional decoders ------------------------------------------------------- #
HEIF_OK = False
try:                                     # iPhone / Samsung HEIC + HEIF
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except Exception:                        # pragma: no cover
    pass

AVIF_OK = False
try:                                     # Pillow ≥ 11.2 reads AVIF itself; older needs the plugin
    from PIL import features
    AVIF_OK = bool(features.check('avif'))
except Exception:                        # pragma: no cover
    AVIF_OK = False
if not AVIF_OK:                          # pragma: no cover
    try:
        import pillow_avif  # noqa: F401
        AVIF_OK = True
    except Exception:
        pass

RAW_EXT = {'.dng', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.srf', '.sr2', '.orf', '.rw2',
           '.raf', '.srw', '.pef', '.x3f', '.3fr', '.erf', '.mef', '.mos', '.iiq', '.k25'}

SUPPORTED_HELP = ('JPG · PNG · HEIC/HEIF · AVIF · WebP · TIFF · BMP · GIF · JPEG 2000 · PSD '
                  '· RAW (DNG/CR2/CR3/NEF/ARW/ORF/RW2/RAF …)')


class UnreadableImage(Exception):
    """The bytes are not an image anything here can decode."""


# --------------------------------------------------------------------------- #
def _as_bytes(src) -> bytes:
    if isinstance(src, (bytes, bytearray, memoryview)):
        return bytes(src)
    if isinstance(src, Image.Image):
        return None
    if hasattr(src, 'read'):
        src.seek(0)
        return src.read()
    with open(src, 'rb') as fh:                      # path
        return fh.read()


def _embedded_preview(data: bytes) -> Image.Image | None:
    """
    Camera RAW files almost always carry a full-size JPEG preview.
    Scan for JPEG SOI…EOI runs and return the largest one that decodes.
    """
    best, best_area = None, 0
    start = 0
    for _ in range(200):
        i = data.find(b'\xff\xd8\xff', start)
        if i < 0:
            break
        j = data.find(b'\xff\xd9', i + 3)
        while j > 0:
            chunk = data[i:j + 2]
            if len(chunk) > 20_000:
                try:
                    im = Image.open(io.BytesIO(chunk))
                    im.load()
                    if im.width * im.height > best_area:
                        best, best_area = im, im.width * im.height
                    break
                except Exception:
                    pass
            j = data.find(b'\xff\xd9', j + 2)
            if j - i > 60_000_000:
                break
        start = i + 3
        if best_area > 9_000_000:                     # big enough, stop hunting
            break
    return best


def _to_rgb(im: Image.Image) -> Image.Image:
    """16-bit / grey / CMYK / palette / float → plain 8-bit RGB."""
    if im.mode in ('I;16', 'I;16B', 'I;16L', 'I'):
        try:
            import numpy as np
            a = np.array(im, dtype='float32')
            a = (a / max(1.0, a.max()) * 255.0) if a.max() > 255 else a
            return Image.fromarray(a.clip(0, 255).astype('uint8')).convert('RGB')
        except Exception:
            return im.convert('L').convert('RGB')
    if im.mode == 'F':
        import numpy as np
        a = np.array(im, dtype='float32')
        a = (a - a.min()) / max(1e-6, a.max() - a.min()) * 255.0
        return Image.fromarray(a.astype('uint8')).convert('RGB')
    if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
        return flatten(im)
    return im.convert('RGB')


def flatten(im: Image.Image, bg=(255, 255, 255)) -> Image.Image:
    """Composite a transparent image onto a solid background → RGB."""
    if im.mode not in ('RGBA', 'LA', 'PA') and not (im.mode == 'P' and 'transparency' in im.info):
        return im.convert('RGB')
    im = im.convert('RGBA')
    canvas = Image.new('RGB', im.size, bg)
    canvas.paste(im, mask=im.getchannel('A'))
    return canvas


def has_alpha(im: Image.Image, thr: int = 250, min_frac: float = 0.01) -> bool:
    """True when a meaningful part of the image is actually transparent."""
    if im.mode not in ('RGBA', 'LA', 'PA') and not (im.mode == 'P' and 'transparency' in im.info):
        return False
    a = im.convert('RGBA').getchannel('A')
    small = a.resize((min(200, a.width), min(200, a.height)), Image.BILINEAR)
    hist = small.histogram()
    clear = sum(hist[:thr])
    return clear > min_frac * (small.width * small.height)


# --------------------------------------------------------------------------- #
def load_any(src, max_side: int = 2400, keep_alpha: bool = False) -> Image.Image:
    """
    Decode anything image-ish into a clean PIL image.

    keep_alpha=False → RGB (transparency flattened onto white).
    keep_alpha=True  → RGBA when the file really has transparency, else RGB.
    """
    if isinstance(src, Image.Image):
        im = src
    else:
        data = _as_bytes(src)
        if not data:
            raise UnreadableImage('The file is empty.')
        try:
            im = Image.open(io.BytesIO(data))
            im.seek(0)                                   # first frame of GIF/TIFF/WebP
        except Exception:
            im = _embedded_preview(data)
            if im is None:
                raise UnreadableImage(
                    f'That file is not an image we can read. Supported: {SUPPORTED_HELP}.')

    try:
        im.load()
    except Exception:
        pass

    # multi-frame containers → first frame
    try:
        if getattr(im, 'n_frames', 1) > 1:
            im.seek(0)
    except Exception:
        pass

    # portrait phone shots
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    if keep_alpha and has_alpha(im):
        im = im.convert('RGBA')
    else:
        im = _to_rgb(im)

    if max_side and max(im.size) > max_side:
        r = max_side / max(im.size)
        im = im.resize((max(1, round(im.width * r)), max(1, round(im.height * r))), Image.LANCZOS)
    return im


def describe() -> str:
    """Human-readable list of what this install can actually open."""
    bits = ['JPEG', 'PNG']
    if HEIF_OK:
        bits.append('HEIC/HEIF')
    if AVIF_OK:
        bits.append('AVIF')
    bits += ['WebP', 'TIFF', 'BMP', 'GIF', 'JPEG 2000', 'PSD', 'RAW (embedded preview)']
    return ' · '.join(bits)


OPEN_EXT = ('.jpg', '.jpeg', '.jpe', '.jfif', '.png', '.heic', '.heif', '.hif', '.avif',
            '.webp', '.tif', '.tiff', '.bmp', '.gif', '.jp2', '.j2k', '.psd', '.ico') + tuple(RAW_EXT)
