# Rest-Place Birthday Flyer — template

One design, many celebrants. Only **two things change** per flyer:

1. the celebrant's **photo**, and
2. the **name** printed on the orange brush band.

Everything else — Rest-Place logo, “HAPPY Birthday”, the orange brush ring, the three
balloons on each side, the confetti — is baked into the template.
Background removal is **optional**: either cut the subject out of the photo, or keep the
original photo inside the round frame.

The template artwork is `uploads/the word at work, giving life to nations….png`
(1056 × 1489). Samples: `output/sample-cutout-mode.png`, `output/sample-frame-mode.jpg`.

---

## Quick start

### 1. Web app (easiest)

```bash
pip install -r requirements.txt
python3 app.py          # → http://localhost:8000
```

Upload a photo → type the name → pick *Remove background* or *Keep background* →
**Create flyer** → download PNG or JPG.

### Image formats accepted

Anything a phone or camera produces — no conversion needed:

`JPG · JPEG · PNG · HEIC/HEIF (iPhone, Samsung) · AVIF · WebP · TIFF · BMP · GIF ·
JPEG 2000 · PSD (flattened) · camera RAW (.dng .cr2 .cr3 .nef .arw .orf .rw2 .raf .srw .pef)`

* iPhone **HEIC/HEIF** works out of the box (via `pillow-heif`).
* **RAW** files are read through the full-size JPEG preview they embed — no rawpy needed.
* **EXIF orientation** is honoured, so portrait phone shots no longer come out sideways.
* **Transparency** is preserved: upload a PNG/WEBP cut-out and it goes straight through —
  background removal is skipped because it's already done.
* 16-bit, CMYK, greyscale, palette and animated files are normalised (first frame, 8-bit RGB).
* Files up to **64 MB**; huge images are downscaled to 2400 px before anything else runs.

### 2. Command line (batch / automation)

```bash
python3 make_flyer.py --photo sister-helen.jpg --name "SIS HELEN"
python3 make_flyer.py --photo team.jpg --name "Bro. Tunde" --mode frame -o tunde.jpg
python3 make_flyer.py --photo cut.png --name "SIS ADA" --no-remove-bg
```

| flag | meaning |
|---|---|
| `--photo` | the celebrant's picture (jpg / png / webp) |
| `--name` | name shown on the band (auto-uppercased, auto-fitted to the band) |
| `--mode cutout` | **default** – background removed, subject blended into the flyer |
| `--mode frame` | photo cropped into the orange ring (original background kept) |
| `--no-remove-bg` | shortcut for `--mode frame` |
| `-o out.png` | output file (`.jpg` writes a high-quality JPEG) |

### 3. From Python

```python
import sys; sys.path.insert(0, 'template')
from render import render

render('helen.jpg', 'SIS HELEN', mode='cutout').save('helen.png')
render('helen.jpg', 'SIS HELEN', mode='frame').save('helen-frame.png')
```

---

## How the template works

`template/build_template.py` reads the artwork in `uploads/`, erases the placeholder
“NAME” from the band, and writes three layers to `template/assets/`:

| asset | what it is |
|---|---|
| `base.png` | the whole flyer **with the placeholder name erased** (inpainted) — logo, “HAPPY Birthday”, ring, balloons, band, confetti |
| `overlay.png` | everything **outside** the photo disc (ring, balloons, band …) with a soft hole where the photo goes — used in *frame* mode |
| `band_mask.png` | soft mask of the orange brush band — a cut-out subject is multiplied by `1 − band_mask` so it is tucked *behind* the band and the bottom edge is never visibly cut |

Render order (see `template/render.py`):

```
frame  mode:  base.png → photo cropped into the ring (soft-edged circle) → overlay.png → name
cutout mode:  base.png → cut-out subject (+ soft shadow & warm glow, hidden behind the band) → name
```

### Knobs in `template/template.json`

```json
{
  "canvas": [1056, 1489],
  "disc":   { "cx": 521, "cy": 877, "r": 316 },          // orange ring geometry
  "band":   { "bbox": [94, 1121, 899, 1303],
              "name_center": [521, 1223], "name_size": 64,
              "name_max_width": 500, "name_color": [12, 12, 12],
              "font": "fonts/ArchivoBlack-Regular.ttf" },
  "cutout": { "height": 620, "bottom": 1222, "center_x": 521 }
}
```

* `band.name_center` / `name_max_width` – where the name sits and how wide it may grow;
  the font size (Archivo Black, the same face the artwork uses) shrinks automatically for
  long names and expands to fit the band for short ones.
* `cutout.height` – how tall the cut-out subject is drawn; `bottom` is where the subject
  ends (behind the band); `center_x` for horizontal placement.
* Swap `fonts/ArchivoBlack-Regular.ttf` for any bold font you like.

### Rebuilding the template (new artwork, same system)

1. Put the new blank flyer in `uploads/` and point `SRC` at it in `template/build_template.py`.
2. Set `DISC` (centre + radius of the photo circle) in the same file.
3. Run `python3 template/build_template.py` → new `base.png`, `overlay.png`, `band_mask.png`.
4. Adjust `template/template.json` (name position, subject height) if the layout moved.

---

## Background removal

The cut-out model is **isnet-general-use** (rembg), run at up to 1600 px in a separate
process, followed by this project's own edge clean-up.

| model | verdict on this machine (2 GB RAM, 2 CPU) |
|---|---|
| **isnet-general-use** | **default** — dark clothing stays solid, curly hair survives, ~3–5 s, ~1.1 GB peak |
| u2net | old default — made dark jackets see-through (only 52 % opaque) and lost hair; ~2 s |
| bria-rmbg | best-looking masks, but ~1.5 GB → **OOM-killed** here |
| birefnet-lite / -general | 224 MB / 900 MB weights, but **>10 min** per photo on 2 cores |

Switch models without touching the code:

```bash
FLYER_MODEL=u2net python3 app.py        # or isnet-general-use (default)
```

Edge clean-up (all in `template/cutout.py`, after the model):

* **single-subject isolation** — largest connected blob only, holes filled
* **rim erosion** — trims the 1-px fringe that carries background colour, the main
  cause of pale halos around hair and shoulders
* **S-curve alpha** — `clip((a − 0.30) / 0.50)`; kills the faint half-transparent
  "veil" of background that otherwise washes over the flyer, while keeping hair wisps
* **colour decontamination** — semi-transparent edge pixels are pulled towards the
  colour of the solid interior, so no light fringe survives
* **green-spill suppression** — foliage/cyan bounce inside curly hair is recoloured
* **border fade** (`render.py`) — a tight photo whose subject runs off the edge of the
  frame fades out instead of printing a hard straight cut

Photos that give the model a clean silhouette (subject fully inside the frame, some
space around the hair) come out perfect; a face cropped tight to the hairline is the
hard case for every model, since there is no background left to key against.

---

## Files

```
app.py                     web UI (Flask)
make_flyer.py              command-line generator
template/
  build_template.py        builds the layered assets (run once)
  render.py                the renderer (photo + name → flyer)
  template.json            geometry & typography settings
  assets/                  base.png · overlay.png · band_mask.png
  imaging.py               opens any image format (HEIC · AVIF · RAW · TIFF · EXIF …)
  cutout.py                background removal (rembg + edge clean-up)
  cutout_worker.py         CLI wrapper used by the web app
  fonts/                   Archivo Black (name), Montserrat / Poppins ExtraBold (spares)
output/                    sample flyers
uploads/                   the original flyer artwork (never modified)
```

## Deploying

Free hosting (no card): **`streamlit_app.py`** runs the same design on
[Streamlit Community Cloud](DEPLOY-FREE-STREAMLIT.md) — push the repo to GitHub, point
share.streamlit.io at `streamlit_app.py`.

Full container/hosting options: **[DEPLOY.md](DEPLOY.md)** — what it needs (2 GB RAM), free vs paid options, and
step-by-step instructions for a laptop, Hugging Face Spaces, Google Cloud Run, Oracle
Always Free, a cheap VPS, or Fly/Render/Railway. `Dockerfile`, `Procfile` and a
`/healthz` endpoint are included.

```bash
docker build -t flyer . && docker run -p 8000:8000 -e PORT=8000 flyer
```

## Requirements

```bash
pip install -r requirements.txt
# Flask · pillow · pillow-heif · numpy · scipy · opencv-python-headless · rembg · onnxruntime
```
