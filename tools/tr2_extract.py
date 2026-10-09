#!/usr/bin/env python3
"""
tr2_extract.py - Dump every texture tile out of a TR2 level file as PNGs.

Usage:
    python tr2_extract.py <level.tr2> <output_dir> [options]

Options:
    --no-8bit             Skip exporting the 8-bit (palettized) tiles
    --no-16bit             Skip exporting the 16-bit (truecolor) tiles
    --no-contact-sheet      Skip generating the labeled overview sheet(s)

Output layout:
    <output_dir>/
        manifest.json           - basic info (version, tile count, source file)
        palette.png             - 16x16 swatch of the 8-bit palette (16px cells)
        tiles_8bit/tile_###.png  - indexed PNGs, one per tile, using the level's
                                   real palette (edit in an indexed-aware editor
                                   to keep pixel-perfect round trips)
        tiles_16bit/tile_###.png - RGBA truecolor PNGs, one per tile (this is
                                   what actually gets displayed by OpenLara)
        contact_sheet_8bit.png  - numbered overview grid of all 8-bit tiles
        contact_sheet_16bit.png - numbered overview grid of all 16-bit tiles

Tile numbers in the filenames match the tile index used inside the level file
(the same index tr2_lara_map.py reports, and the same index you pass back into
tr2_import.py).
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tr2lib


def unpack_argb1555(raw: bytes) -> Image.Image:
    arr = np.frombuffer(raw, dtype='<u2').reshape(tr2lib.TILE_SIZE, tr2lib.TILE_SIZE)
    a = (arr >> 15) & 1
    r5 = (arr >> 10) & 0x1F
    g5 = (arr >> 5) & 0x1F
    b5 = arr & 0x1F
    r8 = ((r5 << 3) | (r5 >> 2)).astype(np.uint8)
    g8 = ((g5 << 3) | (g5 >> 2)).astype(np.uint8)
    b8 = ((b5 << 3) | (b5 >> 2)).astype(np.uint8)
    a8 = (a * 255).astype(np.uint8)
    rgba = np.dstack([r8, g8, b8, a8])
    return Image.fromarray(rgba, 'RGBA')


def make_indexed(raw8: bytes, palette_rgb: bytes) -> Image.Image:
    im = Image.frombytes('P', (tr2lib.TILE_SIZE, tr2lib.TILE_SIZE), raw8)
    im.putpalette(palette_rgb)
    return im


def make_contact_sheet(tile_images, cols=8, cell=132, label_h=18) -> Image.Image:
    n = len(tile_images)
    if n == 0:
        return Image.new('RGB', (1, 1))
    rows = (n + cols - 1) // cols
    sheet = Image.new('RGB', (cols * cell, rows * (cell + label_h)), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    thumb_size = cell - 8
    for i, img in enumerate(tile_images):
        col = i % cols
        row = i // cols
        x = col * cell
        y = row * (cell + label_h)
        thumb = img.convert('RGB').resize((thumb_size, thumb_size), Image.NEAREST)
        sheet.paste(thumb, (x + 4, y + 4))
        draw.rectangle([x + 4, y + 4, x + 4 + thumb_size - 1, y + 4 + thumb_size - 1], outline=(90, 90, 90))
        draw.text((x + 4, y + 4 + thumb_size + 1), f"#{i}", fill=(255, 255, 0), font=font)
    return sheet


def make_palette_preview(palette_rgb: bytes, cell=20) -> Image.Image:
    img = Image.new('RGB', (16 * cell, 16 * cell))
    draw = ImageDraw.Draw(img)
    for i in range(256):
        r, g, b = palette_rgb[i * 3], palette_rgb[i * 3 + 1], palette_rgb[i * 3 + 2]
        col = i % 16
        row = i // 16
        draw.rectangle([col * cell, row * cell, col * cell + cell - 1, row * cell + cell - 1], fill=(r, g, b))
    return img


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('level', help='Path to the .TR2 file (e.g. DATA/ASSAULT.TR2 or DATA/TITLE.tr2)')
    ap.add_argument('outdir', help='Directory to write extracted PNGs into')
    ap.add_argument('--no-8bit', action='store_true')
    ap.add_argument('--no-16bit', action='store_true')
    ap.add_argument('--no-contact-sheet', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    with open(args.level, 'rb') as f:
        hdr = tr2lib.read_texture_header(f)
        print(f"{args.level}: version=0x{hdr.version:08X}  tiles={hdr.num_textiles}")

        palette_preview = make_palette_preview(hdr.palette)
        palette_preview.save(os.path.join(args.outdir, 'palette.png'))

        tiles8 = []
        tiles16 = []

        if not args.no_8bit:
            dir8 = os.path.join(args.outdir, 'tiles_8bit')
            os.makedirs(dir8, exist_ok=True)
            for i in range(hdr.num_textiles):
                raw = tr2lib.read_textile8(f, hdr, i)
                im = make_indexed(raw, hdr.palette)
                im.save(os.path.join(dir8, f'tile_{i:03d}.png'))
                tiles8.append(im)
            print(f"  wrote {hdr.num_textiles} 8-bit tiles -> {dir8}")

        if not args.no_16bit:
            dir16 = os.path.join(args.outdir, 'tiles_16bit')
            os.makedirs(dir16, exist_ok=True)
            for i in range(hdr.num_textiles):
                raw = tr2lib.read_textile16(f, hdr, i)
                im = unpack_argb1555(raw)
                im.save(os.path.join(dir16, f'tile_{i:03d}.png'))
                tiles16.append(im)
            print(f"  wrote {hdr.num_textiles} 16-bit tiles -> {dir16}")

        if not args.no_contact_sheet:
            if tiles8:
                make_contact_sheet(tiles8).save(os.path.join(args.outdir, 'contact_sheet_8bit.png'))
            if tiles16:
                make_contact_sheet(tiles16).save(os.path.join(args.outdir, 'contact_sheet_16bit.png'))
            print("  wrote contact sheet(s)")

    manifest = {
        'source_file': os.path.abspath(args.level),
        'version': hdr.version,
        'num_textiles': hdr.num_textiles,
    }
    with open(os.path.join(args.outdir, 'manifest.json'), 'w') as mf:
        json.dump(manifest, mf, indent=2)

    print("Done.")


if __name__ == '__main__':
    main()
