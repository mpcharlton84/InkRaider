#!/usr/bin/env python3
"""
img_convert.py - Trivial PCX <-> PNG converter for the 2D menu background
(e.g. DATA/TITLE.PCX). No TR-specific parsing needed here; PCX is a plain
image format Pillow reads/writes natively. This just exists so you don't
need a separate image tool to get TITLE.PCX into something every editor can
open, and back again.

IMPORTANT: classic TR-era PCX loaders (including the one your OpenLara build
uses for the menu background) only understand old-school 8-bit *indexed*
(palettized, 256-color) PCX files - the same format the original TITLE.PCX
ships as. A 24-bit truecolor PCX is technically a valid PCX file, but such
loaders will misread its pixel bytes as palette indices and render garbage
(exactly the scanline noise you get if you save straight from an RGB/RGBA
PNG). So: this script ALWAYS writes 8-bit indexed PCX, quantizing down to
256 colors first if needed. PNG output is unrestricted (any mode).

ALSO IMPORTANT: this particular loader reads the image's width/height from
the PCX header's HDpi/VDpi fields (bytes 12-15) rather than computing it
from Xmax/Ymax like a standards-compliant PCX reader would. Pillow's PCX
writer always hardcodes HDpi=VDpi=100 regardless of the actual image size,
which this loader misreads as "the image is 100x100" and fails to launch
entirely. So after Pillow writes the file, this script patches those two
header fields to the real pixel width/height (confirmed by isolation
testing against a real OpenLara.exe launch).

Usage:
    python img_convert.py DATA/TITLE.PCX DATA/TITLE.png
    python img_convert.py edited/TITLE.png DATA/TITLE.PCX
    python img_convert.py edited/TITLE.png DATA/TITLE.PCX --dither
"""
import argparse

from PIL import Image


def to_indexed_256(im: Image.Image, dither: bool) -> Image.Image:
    if im.mode == 'P' and len(im.getpalette() or []) <= 768:
        return im
    if im.mode in ('RGBA', 'LA', 'PA') or (im.mode == 'P' and 'transparency' in im.info):
        im = im.convert('RGB')  # PCX has no alpha channel
    if im.mode != 'RGB':
        im = im.convert('RGB')
    dith = Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE
    return im.quantize(colors=256, dither=dith)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src')
    ap.add_argument('dst')
    ap.add_argument('--dither', action='store_true', help='Allow dithering when quantizing down to 256 colors for PCX output')
    args = ap.parse_args()

    im = Image.open(args.src)
    dst_lower = args.dst.lower()
    if dst_lower.endswith('.pcx'):
        before_mode = im.mode
        im = to_indexed_256(im, args.dither)
        if before_mode != 'P':
            print(f"  (quantized {before_mode} -> 256-color indexed for PCX compatibility)")
        im.save(args.dst)
        fix_pcx_dpi_header(args.dst, im.size[0], im.size[1])
    else:
        im.save(args.dst)
    print(f"{args.src} ({im.mode}, {im.size[0]}x{im.size[1]}) -> {args.dst}")


def fix_pcx_dpi_header(path: str, width: int, height: int) -> None:
    """Patch the HDpi/VDpi fields (header bytes 12-15) to the real pixel
    width/height. This game's PCX loader reads image dimensions from these
    fields instead of Xmax/Ymax, but Pillow always writes a dummy 100 DPI
    here, which makes the loader think the image is 100x100 and fail to
    launch. See module docstring for details."""
    with open(path, 'r+b') as f:
        f.seek(12)
        f.write(width.to_bytes(2, 'little') + height.to_bytes(2, 'little'))


if __name__ == '__main__':
    main()
