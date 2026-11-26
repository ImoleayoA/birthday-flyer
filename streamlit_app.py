"""
Rest-Place birthday flyer — Streamlit version.

Same design, same renderer as the Flask app: only the photo and the name change.

Run locally:      streamlit run streamlit_app.py
Deploy free:      push this repo to GitHub → share.streamlit.io → main file `streamlit_app.py`

The flyer logic lives in `template/` (shared with app.py / make_flyer.py); this file is
only the user interface.
"""
import io
import os
import sys

import streamlit as st
from PIL import Image

# let the hosting dashboard tune it without touching code, e.g. FLYER_MODEL = "u2net"
try:
    for _k in ('FLYER_MODEL', 'CUTOUT_SLOTS'):
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'template'))

from imaging import load_any, has_alpha, UnreadableImage, describe   # noqa: E402
from render import render, CFG, remove_background_safe              # noqa: E402

W, H = CFG['canvas']

st.set_page_config(page_title='Rest-Place Birthday Flyer', page_icon='🎈', layout='wide')

st.markdown(
    """
    <style>
      .block-container{padding-top:2rem;max-width:1150px}
      h1{font-size:1.9rem;margin-bottom:.2rem}
      .sub{color:#8a7a72;margin-bottom:1.4rem}
      div[data-testid="stDownloadButton"] button{border-radius:10px}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title('🎈 Rest-Place Birthday Flyer')
st.markdown('<div class="sub">Upload a photo, type the name — everything else stays the same.</div>',
            unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
def build(data: bytes, name: str, mode: str) -> Image.Image:
    """photo bytes + name → finished flyer (1060 × 1489)."""
    im = load_any(data, max_side=2400, keep_alpha=True)
    if mode == 'cutout':
        if has_alpha(im):
            cut = im.convert('RGBA')                 # already cut out — use as-is
        else:
            buf = io.BytesIO()
            im.convert('RGB').save(buf, 'PNG')
            cut = remove_background_safe(buf.getvalue())
        return render(im, name, 'cutout', cutout=cut)
    return render(im, name, 'frame')


@st.cache_data(show_spinner=False, max_entries=8)
def cached_render(data: bytes, name: str, mode: str):
    """→ (png bytes, jpg bytes)"""
    img = build(data, name, mode)
    png, jpg = io.BytesIO(), io.BytesIO()
    img.save(png, format='PNG', optimize=True)
    img.save(jpg, format='JPEG', quality=95, subsampling=0)
    return png.getvalue(), jpg.getvalue()


# --------------------------------------------------------------------------- #
left, right = st.columns([1, 1.15], gap='large')

with left:
    up = st.file_uploader(
        'Celebrant photo',
        type=None,
        accept_multiple_files=False,
        help='JPG · PNG · HEIC/HEIF · AVIF · WebP · TIFF · BMP · GIF · RAW — any image works.',
    )
    name = st.text_input('Name on the flyer', placeholder='ENTER NAME', max_chars=42)

    mode_label = st.radio(
        'Photo style',
        ['Remove background', 'Keep background'],
        index=0,
        help='Remove background cuts the person out and blends them into the design. '
             'Keep background places the photo inside the orange ring.',
    )
    mode = 'cutout' if mode_label == 'Remove background' else 'frame'

    go = st.button('Create flyer', type='primary', use_container_width=True)
    st.caption(f'{W} × {H} px · ready for WhatsApp, print or social')

with right:
    if not go:
        st.info('The finished flyer appears here.\n\n'
                f'Accepted formats: {describe()}')
    elif not up:
        st.error('Please choose a photo first.')
    elif not name.strip():
        st.error('Please type the name.')
    else:
        data = up.getvalue()
        with st.spinner('Building your flyer — cutting out and blending…'):
            try:
                png, jpg = cached_render(data, name.strip(), mode)
            except UnreadableImage as exc:
                st.error(str(exc))
                png = jpg = None
            except RuntimeError as exc:
                st.error(f'Background removal failed on this photo — try "Keep background". '
                         f'({exc})')
                png = jpg = None
            except Exception as exc:                                  # pragma: no cover
                st.error(f'Could not create the flyer: {exc}')
                png = jpg = None

        if png:
            st.image(png, use_container_width=True)
            fname = name.strip().upper().replace(' ', '-') + '-flyer'
            c1, c2 = st.columns(2)
            with c1:
                st.download_button('⬇ Download PNG', png, file_name=fname + '.png',
                                   mime='image/png', use_container_width=True)
            with c2:
                st.download_button('⬇ Download JPG', jpg, file_name=fname + '.jpg',
                                   mime='image/jpeg', use_container_width=True,
                                   help='PNG is lossless — use JPG for smaller files.')

st.divider()
with st.expander('How it works'):
    st.write(
        'One design, two variables: the **photo** and the **name**.\n\n'
        '* Background removal runs locally with rembg + ISNet — nothing is sent to a third party.\n'
        '* Nothing is stored: each flyer is built in memory and deleted.\n'
        '* Names are uppercased automatically and shrink to fit the orange band.\n'
        '* A photo that already has a transparent background skips removal entirely.'
    )
st.caption('Rest-Place Christian Centre · the word at work, giving life to nations…')
