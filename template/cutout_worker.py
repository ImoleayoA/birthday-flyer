"""
Usage: python3 template/cutout_worker.py <in-image> <out-png>

Reads any image format. If the file already carries real transparency (a PNG/WEBP
cut-out, for instance) the alpha is used as-is — no needless re-processing.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imaging import load_any, has_alpha
from cutout import remove_background, MODEL

src, dst = sys.argv[1], sys.argv[2]

img = load_any(src, max_side=1600, keep_alpha=True)

if has_alpha(img):
    img.convert('RGBA').save(dst)
    print('alpha reused')
    sys.exit(0)

if img.mode != 'RGB':
    img = img.convert('RGB')
remove_background(img).save(dst)
print(f'background removed ({MODEL})')
