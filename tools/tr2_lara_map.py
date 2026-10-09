#!/usr/bin/env python3
"""
tr2_lara_map.py - Find out which texture tiles/regions belong to Lara's model.

In TR2, Lara's mesh and textures are embedded in every level file (there's no
separate "Lara model" file) and they share the same texture tile atlas as the
room geometry. This script parses the level far enough (rooms -> meshes ->
models -> object textures) to find every tile region actually used by Lara's
skeleton meshes, so you know exactly which pixels to touch when you want to
reskin her without accidentally editing level scenery packed into the same
tile.

Usage:
    python tr2_lara_map.py <level.tr2> <output_dir> [--model-id 0]

Output:
    <output_dir>/lara_tiles.txt       - tile index -> list of used UV boxes
    <output_dir>/tile_###_highlight.png
                                        - each tile that Lara uses, rendered
                                          at full res with a red translucent
                                          overlay on the regions her meshes
                                          reference (everything else on that
                                          tile is level/other-object texture)

--model-id defaults to 0, which is Lara in both TR1 and TR2. Other useful
ids for TR2 (see OpenLara's format.h TR_TYPES table, TR2 block): 1 = Lara
pistols mesh swap, 3 = Lara autopistols, 6 = Lara M16, etc. -- pass those if
you want to isolate a specific weapon-holding variant instead of the base
skin.
"""
import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tr2lib
from tr2_extract import unpack_argb1555


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('level')
    ap.add_argument('outdir')
    ap.add_argument('--model-id', type=int, default=0, help='Raw model type id to inspect (default 0 = Lara)')
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    with open(args.level, 'rb') as f:
        level = tr2lib.parse_level(f)
        print(f"{args.level}: {len(level.models)} models, {len(level.object_textures)} object textures, {level.header.num_textiles} tiles")

        usage = tr2lib.find_lara_tile_usage(level, args.model_id)
        if not usage:
            print(f"No mesh faces found referencing model id {args.model_id}.")
            return

        lines = [f"Model id {args.model_id} uses {len(usage)} tile(s):", ""]
        for tile_index in sorted(usage):
            boxes = usage[tile_index]
            lines.append(f"tile {tile_index:03d}: {len(boxes)} face(s)")
            xs = [c[0] for box in boxes for c in box]
            ys = [c[1] for box in boxes for c in box]
            lines.append(f"    bounding area on tile: x[{min(xs)}..{max(xs)}] y[{min(ys)}..{max(ys)}]")

            raw16 = tr2lib.read_textile16(f, level.header, tile_index)
            base = unpack_argb1555(raw16).convert('RGBA')
            overlay = Image.new('RGBA', base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            for box in boxes:
                pts = [c for c in box if not (c == (0, 0) and box.index(c) == 3)]
                if len(pts) >= 3:
                    draw.polygon(pts, fill=(255, 0, 0, 110), outline=(255, 0, 0, 255))
            out = Image.alpha_composite(base, overlay)
            out.save(os.path.join(args.outdir, f'tile_{tile_index:03d}_highlight.png'))

        with open(os.path.join(args.outdir, 'lara_tiles.txt'), 'w') as tf:
            tf.write('\n'.join(lines) + '\n')

        print(f"Wrote lara_tiles.txt and {len(usage)} highlight image(s) -> {args.outdir}")


if __name__ == '__main__':
    main()
