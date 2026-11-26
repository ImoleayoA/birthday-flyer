"""
Rest-Place birthday flyer — template renderer.

Only two things change per flyer:  the celebrant's photo  and  the name.

Layers (built once by build_template.py):
    base.png      the flyer with the photo area empty and the placeholder name removed
    overlay.png   everything outside the photo disc (orange ring, balloons, band, logo,
                  confetti) with a soft hole where the photo goes — used in "frame" mode
    band_mask.png soft mask of the orange brush band, so a cut-out subject can be
                  tucked behind it
"""
import io, json, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from scipy import ndimage as ndi

from imaging import load_any, flatten

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, 'template.json')))
W, H = CFG['canvas']


def _p(rel):
    return os.path.join(HERE, rel)


BASE = Image.open(_p(CFG['assets']['base'])).convert('RGB')
OVERLAY = Image.open(_p(CFG['assets']['overlay'])).convert('RGBA')
BAND = np.array(Image.open(_p(CFG['assets']['band_mask'])).convert('L')).astype(np.float32) / 255.0

BG_ARR = np.array(BASE).astype(np.float32)          # cached, reused for cut-out mode


# --------------------------------------------------------------------------- #
#  background removal (opt-in)
# --------------------------------------------------------------------------- #
def remove_background(img, max_side: int = 1600):
    """In-process background removal (small images only — prefer the worker)."""
    from cutout import remove_background as _rm
    return _rm(img, max_side)


def remove_background_safe(src) -> Image.Image:
    """
    Background removal in a throw-away subprocess.

    rembg peaks around 500-700 MB; on a small box that is enough to get the caller
    OOM-killed, so every path (CLI, library, web app) goes through the worker.
    """
    import subprocess, sys, tempfile
    worker = os.path.join(HERE, 'cutout_worker.py')
    tmp = tempfile.mkdtemp(prefix='cut-')
    inp, out = os.path.join(tmp, 'in.png'), os.path.join(tmp, 'out.png')
    own_input = True
    try:
        if isinstance(src, (str, os.PathLike)):
            inp, own_input = str(src), False
        else:
            if isinstance(src, (bytes, bytearray, memoryview)):
                im = load_any(bytes(src), max_side=2400)     # any format, from memory
            else:
                im = src if isinstance(src, Image.Image) else Image.open(src)
            im.convert('RGB').save(inp)
        proc = subprocess.run([sys.executable, worker, inp, out],
                              capture_output=True, text=True, timeout=300)
        if proc.returncode != 0 or not os.path.exists(out):
            raise RuntimeError('background removal failed: ' + (proc.stderr or '')[-400:])
        return Image.open(out).convert('RGBA')
    finally:
        for f in ([inp] if own_input else []) + [out]:
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def _trim(rgba: Image.Image, thr: int = 8) -> Image.Image:
    a = np.array(rgba)[:, :, 3]
    ys, xs = np.where(a > thr)
    if len(xs) == 0:
        return rgba
    return rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


# --------------------------------------------------------------------------- #
#  photo layers
# --------------------------------------------------------------------------- #
def _frame_layer(photo: Image.Image) -> Image.Image:
    """Photo cropped into the round frame (background kept)."""
    d = CFG['disc']
    size = int(2 * d['r'])
    photo = flatten(photo)
    scale = max(size / photo.width, size / photo.height)
    p = photo.resize((max(1, round(photo.width * scale)), max(1, round(photo.height * scale))),
                     Image.LANCZOS)
    left = (p.width - size) // 2
    # keep a little more of the top of the photo (heads are usually high in the frame)
    top = int((p.height - size) * 0.35)
    p = p.crop((left, top, left + size, top + size)).convert('RGBA')

    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.2))
    p.putalpha(mask)

    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    layer.paste(p, (int(d['cx'] - d['r']), int(d['cy'] - d['r'])), mask)
    return layer


def _fade_borders(cut: Image.Image, frac: float = 0.13) -> Image.Image:
    """
    Tight phone portraits often have the subject touching (or leaving through) the
    edge of the photo, which would otherwise print a hard straight cut on the flyer.
    Any border the subject runs into gets a soft fade so it dissolves into the design.
    """
    arr = np.array(cut).astype(np.float32)
    a = arr[:, :, 3] / 255.0
    h, w = a.shape
    n = max(8, int(frac * min(h, w)))
    ramp = (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))).astype(np.float32)  # 0 → 1
    for side in ('top', 'bottom', 'left', 'right'):
        edge = {'top': a[:6, :], 'bottom': a[-6:, :], 'left': a[:, :6], 'right': a[:, -6:]}[side]
        if edge.mean() < 0.25:                 # subject doesn't reach this edge
            continue
        if side == 'top':
            a[:n, :] *= ramp[:, None]
        elif side == 'bottom':
            a[-n:, :] *= ramp[::-1][:, None]
        elif side == 'left':
            a[:, :n] *= ramp[None, :]
        else:
            a[:, -n:] *= ramp[::-1][None, :]
    arr[:, :, 3] = np.clip(a, 0, 1) * 255.0
    return Image.fromarray(arr.astype(np.uint8))


def _cutout_layer(cut: Image.Image):
    """Free-standing subject blended onto the flyer (background removed)."""
    c = CFG['cutout']
    cut = _fade_borders(_trim(cut))
    scale = c['height'] / cut.height
    nw, nh = max(1, round(cut.width * scale)), max(1, round(cut.height * scale))
    max_w = 2.6 * CFG['disc']['r']
    if nw > max_w:                                    # very wide subject
        scale = max_w / cut.width
        nw, nh = max(1, round(cut.width * scale)), max(1, round(cut.height * scale))
    cut = cut.resize((nw, nh), Image.LANCZOS)

    x, y = int(CFG['cutout']['center_x'] - nw / 2), int(CFG['cutout']['bottom'] - nh)
    alpha = np.zeros((H, W), np.float32)
    ca = np.array(cut)[:, :, 3].astype(np.float32) / 255.0
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + nw, W), min(y + nh, H)
    alpha[y0:y1, x0:x1] = ca[y0 - y:y1 - y, x0 - x:x1 - x]

    def shift(a, dy):
        out = np.zeros_like(a)
        if dy >= 0:
            out[dy:, :] = a[:a.shape[0] - dy, :]
        return out

    s = H / 1489.0                                     # keep effects canvas-relative
    front = 1.0 - BAND                                 # the brush band always wins
    # effects are derived from the *solid body* only: blurring the raw alpha of a
    # tight portrait would just shadow the whole photo rectangle
    solid = (alpha > 0.5).astype(np.float32)
    solid = ndi.binary_erosion(solid > 0.5, np.ones((25, 25), bool)).astype(np.float32)
    shadow = (0.30 * ndi.gaussian_filter(shift(solid, int(80 * s)), 44 * s, mode='nearest') +
              0.22 * ndi.gaussian_filter(shift(solid, int(22 * s)), 12 * s, mode='nearest')) * front
    glow = np.clip(ndi.gaussian_filter(solid, 120 * s, mode='nearest') * 1.6, 0, 1) * 0.16 * front

    canvas = BG_ARR.copy()
    sh = np.clip(shadow, 0, 0.58)[..., None]
    canvas = canvas * (1 - sh) + np.array([124, 58, 64], np.float32) * sh
    canvas = canvas * (1 - glow[..., None]) + np.array([255, 240, 226], np.float32) * glow[..., None]

    a3 = alpha[y0:y1, x0:x1] * front[y0:y1, x0:x1]
    sub = np.array(cut).astype(np.float32)[y0 - y:y1 - y, x0 - x:x1 - x, :3]
    canvas[y0:y1, x0:x1] = canvas[y0:y1, x0:x1] * (1 - a3[..., None]) + sub * a3[..., None]
    return Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).convert('RGB')


# --------------------------------------------------------------------------- #
#  name on the band
# --------------------------------------------------------------------------- #
def _draw_name(img: Image.Image, name: str) -> Image.Image:
    if not name.strip():
        return img
    b = CFG['band']
    cx, cy = b['name_center']
    text = name.strip().upper()

    size = b['name_size']
    font_path = _p(b['font'])
    while size > 22:
        font = ImageFont.truetype(font_path, size)
        try:
            font.set_variation_by_name('ExtraBold')
        except Exception:
            pass
        draw = ImageDraw.Draw(img)
        track = max(0, int(size * 0.012))
        w = sum(draw.textlength(ch, font=font) for ch in text) + track * (len(text) - 1)
        if w <= b['name_max_width']:
            break
        size -= 2

    asc, desc = font.getmetrics()
    draw = ImageDraw.Draw(img)
    x = cx - w / 2
    y = cy - (asc + desc) / 2 + desc * 0.18          # optical centring on cap height
    for ch in text:
        draw.text((x, y), ch, font=font, fill=tuple(b['name_color']))
        x += draw.textlength(ch, font=font) + track
    return img


# --------------------------------------------------------------------------- #
#  public API
# --------------------------------------------------------------------------- #
def render(photo_path_or_img, name: str = '', mode: str = 'cutout', cutout=None) -> Image.Image:
    """mode 'cutout' = background removed & blended; 'frame' = photo inside the ring."""
    src_ref = photo_path_or_img
    src = photo_path_or_img if isinstance(photo_path_or_img, Image.Image) \
        else load_any(photo_path_or_img, max_side=2400)

    if mode == 'frame':
        base = BASE.convert('RGBA')
        base.alpha_composite(_frame_layer(src))
        base.alpha_composite(OVERLAY)
        out = base.convert('RGB')
    else:
        cut = cutout if cutout is not None else remove_background_safe(src_ref)
        out = _cutout_layer(cut)

    return _draw_name(out, name)


def render_bytes(photo_file, name: str, mode: str, fmt: str = 'PNG', **kw) -> bytes:
    buf = io.BytesIO()
    render(photo_file, name, mode).save(buf, format=fmt, **kw)
    return buf.getvalue()
