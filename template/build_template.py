"""
Build the reusable layer assets for the Rest-Place birthday flyer template
from the blank template artwork.

Run once:  python3 template/build_template.py
Outputs:   template/assets/base.png · overlay.png · band_mask.png   +  template.json
"""
import json, os
import numpy as np, cv2
from PIL import Image
from scipy import ndimage as ndi

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, 'assets')
os.makedirs(ASSETS, exist_ok=True)

SRC = os.path.join(ROOT, 'uploads', 'the word at work, giving life to nations….png')

img = np.array(Image.open(SRC).convert('RGB')).astype(np.float32)
H, W, _ = img.shape
r, g, b = img[:, :, 0], img[:, :, 1], img[:, :, 2]
mx = img.max(2); sat = mx - img.min(2)
yy, xx = np.mgrid[0:H, 0:W]

# ---- geometry ---------------------------------------------------------------
DISC = dict(cx=521, cy=877, r=316)        # inner edge of the orange ring

# ---- 1. band (orange brush) -------------------------------------------------
band = ((r > 225) & (sat > 90) & (yy > 1120) & (xx > 60) & (xx < 990))
band = ndi.binary_closing(band, np.ones((25, 25)))
band = ndi.binary_fill_holes(band)
lbl, n = ndi.label(band)
sz = ndi.sum(band, lbl, range(1, n + 1))
band = lbl == (np.argmax(sz) + 1)
band_soft = cv2.GaussianBlur(band.astype(np.float32), (0, 0), 2.0)
Image.fromarray((band_soft * 255).astype(np.uint8)).save(os.path.join(ASSETS, 'band_mask.png'))

# ---- 2. erase the placeholder "NAME" from the band -------------------------
text = (mx < 130) & ndi.binary_erosion(ndi.binary_dilation(band, np.ones((13, 13))), np.ones((3, 3)))
text = cv2.dilate(text.astype(np.uint8), np.ones((7, 7))).astype(bool)
base = cv2.inpaint(img.astype(np.uint8), (text * 255).astype(np.uint8), 7, cv2.INPAINT_TELEA)
base = cv2.GaussianBlur(base, (0, 0), 0.4)
Image.fromarray(base).save(os.path.join(ASSETS, 'base.png'), optimize=True)

# ---- 3. overlay: everything outside the photo disc (ring, balloons, band…) --
dist = np.hypot(xx - DISC['cx'], yy - DISC['cy'])
hole = (dist <= DISC['r']).astype(np.float32)
hole = cv2.GaussianBlur(hole, (0, 0), 1.2)
overlay = np.dstack([base, (1.0 - hole) * 255]).astype(np.uint8)
Image.fromarray(overlay, 'RGBA').save(os.path.join(ASSETS, 'overlay.png'), optimize=True)

# ---- 4. template.json ------------------------------------------------------
ys, xs = np.where(band)
band_bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
meta = dict(
    canvas=[W, H],
    disc=DISC,
    band=dict(bbox=band_bbox,
              name_center=[521, 1223],
              name_size=64,
              name_max_width=500,
              name_color=[12, 12, 12],
              font='fonts/ArchivoBlack-Regular.ttf'),
    cutout=dict(height=650, bottom=1215, center_x=521),
    assets=dict(base='assets/base.png', overlay='assets/overlay.png',
                band_mask='assets/band_mask.png'),
)
with open(os.path.join(HERE, 'template.json'), 'w') as f:
    json.dump(meta, f, indent=2)
print('template built  |  band bbox', band_bbox, '| canvas', W, 'x', H)
