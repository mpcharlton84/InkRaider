#!/usr/bin/env python3
"""
tr2_import.py - Write edited tile PNGs back into a copy of a TR2 level file.

Usage:
    python tr2_import.py <level.tr2> <edited_dir> <output.tr2> [options]

<edited_dir> is a folder produced by tr2_extract.py (optionally with the PNGs
inside tiles_8bit/ and/or tiles_16bit/ edited). Any tile file that is missing
is simply left untouched in the output. <output.tr2> is written fresh; the
original file is never modified in place.

Options:
    --which {8,16,both}   Which tile set(s) to import (default: both)
    --dither              Allow dithering when re-quantizing 8-bit tiles that
                           were edited as truecolor/RGBA (default: off, since
                           dithering usually looks wrong on hard-edged game
                           textures)
    --sync-8bit-from-16   Ignore tiles_8bit/ entirely and instead regenerate
                           every 8-bit tile by re-quantizing the (possibly
                           edited) 16-bit tile down to the level's palette.
                           Use this if you only want to edit the true-color
                           16-bit tiles and keep the legacy 8-bit ones in sync.

Notes on 8-bit tiles:
    If a tile_###.png is still in indexed ("P") mode AND its embedded palette
    is byte-identical to the level's palette, its raw index bytes are copied
    back verbatim (perfectly lossless). Otherwise (you painted in RGB/RGBA,
    or your editor re-ordered the palette) the image is re-quantized to the
    level's existing 256-color palette - no new colors can be introduced this
    way, only re-mapped to the closest existing palette entry.

Notes on 16-bit tiles:
    Expected to be RGBA. Each pixel is requantized to 5-bit R/G/B + 1-bit
    alpha (alpha >= 128 -> opaque). This is a true-color tile so any colors
    you paint are preserved (just reduced from 8-bit to 5-bit per channel).
"""
import argparse
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tr2lib


def load_tile8(path: str, level_palette_rgb: bytes, allow_dither: bool) -> bytes:
    im = Image.open(path)
    if im.size != (tr2lib.TILE_SIZE, tr2lib.TILE_SIZE):
        raise tr2lib.Tr2Error(f"{path}: must be exactly {tr2lib.TILE_SIZE}x{tr2lib.TILE_SIZE}, got {im.size}")

    if im.mode == 'P':
        pal = (im.getpalette() or [])[:768]
        pal = bytes(pal + [0] * (768 - len(pal)))
        if pal == level_palette_rgb:
            return im.tobytes()  # lossless: indices already match the level palette

    if im.mode != 'RGB':
        im = im.convert('RGB')
    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(level_palette_rgb)
    dither = Image.Dither.FLOYDSTEINBERG if allow_dither else Image.Dither.NONE
    quantized = im.quantize(palette=pal_img, dither=dither)
    return quantized.tobytes()


def load_tile16(path: str) -> bytes:
    im = Image.open(path)
    if im.size != (tr2lib.TILE_SIZE, tr2lib.TILE_SIZE):
        raise tr2lib.Tr2Error(f"{path}: must be exactly {tr2lib.TILE_SIZE}x{tr2lib.TILE_SIZE}, got {im.size}")
    im = im.convert('RGBA')
    arr = np.array(im, dtype=np.uint32)
    r = (arr[..., 0] * 31 + 127) // 255
    g = (arr[..., 1] * 31 + 127) // 255
    b = (arr[..., 2] * 31 + 127) // 255
    a = (arr[..., 3] >= 128).astype(np.uint32)
    packed = (a << 15) | (r << 10) | (g << 5) | b
    return packed.astype('<u2').tobytes()


def tile16_to_tile8_bytes(tile16_raw: bytes, level_palette_rgb: bytes, allow_dither: bool) -> bytes:
    arr = np.frombuffer(tile16_raw, dtype='<u2').reshape(tr2lib.TILE_SIZE, tr2lib.TILE_SIZE)
    r5 = (arr >> 10) & 0x1F
    g5 = (arr >> 5) & 0x1F
    b5 = arr & 0x1F
    r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
    g8 = ((g5 << 3) | (g5 >> 2)).astype(np.uint8)
    b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)
    im = Image.fromarray(np.dstack([r8, g8, b8]), 'RGB')
    pal_img = Image.new('P', (1, 1))
    pal_img.putpalette(level_palette_rgb)
    dither = Image.Dither.FLOYDSTEINBERG if allow_dither else Image.Dither.NONE
    return im.quantize(palette=pal_img, dither=dither).tobytes()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('level', help='Original .TR2 file to patch (read-only, never modified)')
    ap.add_argument('edited_dir', help='Folder containing tiles_8bit/ and/or tiles_16bit/')
    ap.add_argument('output', help='Path to write the new, patched .TR2 file to')
    ap.add_argument('--which', choices=['8', '16', 'both'], default='both')
    ap.add_argument('--dither', action='store_true')
    ap.add_argument('--sync-8bit-from-16', action='store_true')
    args = ap.parse_args()

    if os.path.abspath(args.output) == os.path.abspath(args.level):
        raise SystemExit("Refusing to overwrite the source file; choose a different --output path.")

    shutil.copyfile(args.level, args.output)

    with open(args.output, 'r+b') as f:
        hdr = tr2lib.read_texture_header(f)
        print(f"{args.level}: version=0x{hdr.version:08X} tiles={hdr.num_textiles}")

        do8 = args.which in ('8', 'both') and not args.sync_8bit_from_16
        do16 = args.which in ('16', 'both') or args.sync_8bit_from_16

        n16 = 0
        if do16:
            dir16 = os.path.join(args.edited_dir, 'tiles_16bit')
            for i in range(hdr.num_textiles):
                p = os.path.join(dir16, f'tile_{i:03d}.png')
                if not os.path.isfile(p):
                    continue
                raw16 = load_tile16(p)
                tr2lib.write_textile16(f, hdr, i, raw16)
                n16 += 1
                if args.sync_8bit_from_16:
                    raw8 = tile16_to_tile8_bytes(raw16, hdr.palette, args.dither)
                    tr2lib.write_textile8(f, hdr, i, raw8)
            print(f"  patched {n16} 16-bit tiles" + (" (and re-synced matching 8-bit tiles)" if args.sync_8bit_from_16 else ""))

        n8 = 0
        if do8:
            dir8 = os.path.join(args.edited_dir, 'tiles_8bit')
            for i in range(hdr.num_textiles):
                p = os.path.join(dir8, f'tile_{i:03d}.png')
                if not os.path.isfile(p):
                    continue
                raw8 = load_tile8(p, hdr.palette, args.dither)
                tr2lib.write_textile8(f, hdr, i, raw8)
                n8 += 1
            print(f"  patched {n8} 8-bit tiles")

    print(f"Wrote {args.output}")


if __name__ == '__main__':
    main()
