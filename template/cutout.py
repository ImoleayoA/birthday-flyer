"""Subject cut-out (background removal) — kept in its own module so it can run
in a short-lived subprocess and keep the web app's memory footprint small.

Model choice (best first, all measured on this machine):

    isnet-general-use   default — solid on dark clothing, keeps curly hair.  ~4 s, ~500 MB
    u2net               old default — loses hair and makes dark clothes see-through
    bria-rmbg           excellent quality but ~1.5 GB → OOM-killed on a 2 GB box
    birefnet-*          900 MB / 224 MB, but >10 min per photo on 2 CPU cores

Override with the FLYER_MODEL env var, e.g.  FLYER_MODEL=u2net python3 app.py
"""
import os

import numpy as np
import scipy.ndimage as ndi
from PIL import Image

MODEL = os.environ.get('FLYER_MODEL', 'isnet-general-use')
FALLBACK_MODEL = 'u2net'
_SESSION = None
_SESSION_NAME = None


def _load_session():
    global _SESSION, _SESSION_NAME
    if _SESSION is not None:
        return _SESSION
    from rembg import new_session
    try:
        _SESSION = new_session(MODEL)
        _SESSION_NAME = MODEL
    except Exception:                       # missing weights / not enough RAM
        _SESSION = new_session(FALLBACK_MODEL)
        _SESSION_NAME = FALLBACK_MODEL
    return _SESSION


def model_name() -> str:
    return _SESSION_NAME or MODEL


def remove_background(img: Image.Image, max_side: int = 1600) -> Image.Image:
    """Return an RGBA cut-out of the main subject (with cleaned-up edges)."""
    import scipy.ndimage as ndi
    from rembg import remove
    session = _load_session()
    img = img.convert('RGB')
    small = img.copy()
    small.thumbnail((max_side, max_side), Image.LANCZOS)
    out = remove(small, session=session, post_process_mask=False)
    alpha = out.getchannel('A').resize(img.size, Image.LANCZOS)

    a = np.array(alpha).astype(np.float32) / 255.0
    core = a > 0.6
    if core.any():                                  # keep the main subject only
        lbl, n = ndi.label(core)
        sizes = ndi.sum(core, lbl, range(1, n + 1))
        core = lbl == (np.argmax(sizes) + 1)
        core = ndi.binary_fill_holes(core)
        keep = ndi.binary_dilation(core, np.ones((25, 25)))
        a = a * keep
    a[a < 0.05] = 0
    # trim the one-pixel rim that still carries background colour — this is what
    # used to leave a pale halo around hair and shoulders
    a = ndi.grey_erosion(a, size=(3, 3))
    # S-curve: kills the faint "veil" of half-transparent background that otherwise
    # shows up as a pale rectangle, while keeping real hair wisps
    a = np.clip((a - 0.30) / 0.50, 0, 1)
    a = ndi.median_filter(a, 3)
    a = ndi.gaussian_filter(a, 0.7)

    rgb = np.array(img).astype(np.float32)
    # colour decontamination: pull semi-transparent edge pixels towards the
    # colour of the solid interior so no background halo survives
    w = (a ** 3)[..., None]
    num = ndi.gaussian_filter(rgb * w, (6, 6, 0))
    den = ndi.gaussian_filter(a ** 3, 6)[..., None]
    core_col = np.where(den > 1e-3, num / np.maximum(den, 1e-6), rgb)
    mix = np.clip((1.0 - a) * 2.0, 0, 1)[..., None]
    rgb = rgb * (1 - mix) + core_col * mix

    # kill background spill in small gaps of hair/fur: recolour pixels that sit
    # right next to transparent holes with the subject's own colour
    holes = a < 0.25
    edge_zone = ndi.binary_dilation(holes, np.ones((9, 9))) & (a > 0.02)
    m2 = (edge_zone.astype(np.float32) * 0.75)[..., None]
    rgb = rgb * (1 - m2) + core_col * m2

    # green/cyan spill (foliage etc.) inside hair edges -> recolour to subject tone
    g_ = rgb[:, :, 1]
    greenish = (g_ > rgb[:, :, 0] + 6) & (g_ > rgb[:, :, 2] + 6)
    core_green = (core_col[:, :, 1] > np.maximum(core_col[:, :, 0], core_col[:, :, 2]) + 6)
    spill = greenish & (~core_green) & (a > 0.02)
    if spill.any():
        rgb[spill] = core_col[spill]

    rgba = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), a * 255]).astype(np.uint8))
    return rgba


