#!/usr/bin/env python3
"""
Rest-Place birthday flyer generator.

Examples
--------
  python3 make_flyer.py --photo me.jpg --name "SIS HELEN"
  python3 make_flyer.py --photo me.jpg --name "Bro. Tunde" --mode frame
  python3 make_flyer.py --photo me.jpg --name "SIS HELEN" --no-remove-bg -o out.jpg
"""
import argparse, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'template'))
from render import render          # noqa: E402


def main():
    ap = argparse.ArgumentParser(description='Generate a Rest-Place birthday flyer.')
    ap.add_argument('--photo', required=True, help='the celebrant photo (jpg/png)')
    ap.add_argument('--name', required=True, help='name printed on the orange band')
    ap.add_argument('--mode', choices=['cutout', 'frame'], default='cutout',
                    help="cutout = background removed (default); frame = photo inside the circle")
    ap.add_argument('--no-remove-bg', action='store_true', help='same as --mode frame')
    ap.add_argument('-o', '--out', default=None, help='output file (default: NAME-flyer.png)')
    a = ap.parse_args()

    mode = 'frame' if a.no_remove_bg else a.mode
    out = a.out or f"{a.name.strip().upper().replace(' ', '-')}-flyer.png"

    print(f'· photo : {a.photo}')
    print(f'· name  : {a.name}')
    print(f'· mode  : {"remove background" if mode == "cutout" else "photo in circle"}')
    img = render(a.photo, a.name, mode)
    if out.lower().endswith(('.jpg', '.jpeg')):
        img.save(out, quality=96, subsampling=0)
    else:
        img.save(out, optimize=True)
    print(f'✓ saved {out}  ({img.width}×{img.height})')


if __name__ == '__main__':
    main()
