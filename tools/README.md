# TR2 Texture Tools

Small, dependency-light Python scripts to extract and re-import textures for
your custom TR2 build (level, Lara model, and menu). They edit `.TR2` level
files directly — no separate "model" files exist in TR2, everything (rooms,
Lara's mesh, weapons, pickups) lives inside the level file and shares one
texture-tile atlas per file.

Requires: Python 3 + `Pillow` + `numpy` (`pip install Pillow numpy`).

## What maps to what in this project

| File | What it is | Tool to use |
|---|---|---|
| `DATA/ASSAULT.TR2` | The level itself (your Manor level; this is TR2's "Lara's Home" slot) — room textures **and** Lara's mesh/skin textures, packed into the same tile atlas | `tr2_extract.py`, `tr2_lara_map.py`, `tr2_import.py` |
| `DATA/TITLE.tr2` | The 3D background level rendered behind the main menu | `tr2_extract.py`, `tr2_import.py` |
| `DATA/TITLE.PCX` / `TITLE.png` | The flat 2D menu artwork (title picture) | `img_convert.py` (already a plain image — edit directly in any editor) |

Any other `.TR2` level you add later works the same way as `ASSAULT.TR2`.

## 1. Extract textures

```
python tools/tr2_extract.py DATA/ASSAULT.TR2 work/assault
python tools/tr2_extract.py DATA/TITLE.tr2 work/title
```

This writes, per file:

- `tiles_8bit/tile_###.png` — indexed PNGs using the level's real 256-color
  palette (edit in an indexed-aware editor like GIMP/Aseprite for pixel-exact
  round trips)
- `tiles_16bit/tile_###.png` — RGBA truecolor PNGs. **This is what actually
  gets displayed** in a modern renderer like OpenLara, so for real art edits,
  paint these.
- `contact_sheet_8bit.png` / `contact_sheet_16bit.png` — numbered overview
  grids so you can spot which tile number is which without opening every file
- `palette.png` — the 8-bit palette laid out as a 16x16 swatch
- `manifest.json` — source file, version, tile count

Tile numbers are stable and match what `tr2_lara_map.py` reports.

## 2. Find Lara's textures specifically

Room scenery and Lara's skin/hair/weapons often land on different tiles, but
they can share a tile. Run this to know exactly which pixels are Lara's:

```
python tools/tr2_lara_map.py DATA/ASSAULT.TR2 work/assault_lara_map
```

This writes `lara_tiles.txt` (tile index + how many faces reference it) and
a `tile_###_highlight.png` per tile Lara uses, with her UV regions painted in
translucent red over the real tile art, so you can see at a glance what to
touch and what to leave alone. Pass `--model-id N` to inspect a different
model (e.g. a specific weapon-holding Lara variant); see the script's
docstring for common ids.

## 3. Edit

Open the PNGs in `tiles_16bit/` (and/or `tiles_8bit/`) in any image editor.
Keep each file exactly 256x256 — that's a hard tile-size requirement of the
format. Menu artwork (`TITLE.PCX`) is a plain 2D image, not a tile atlas —
convert and edit it directly:

```
python tools/img_convert.py DATA/TITLE.PCX work/title_menu.png
# ... edit work/title_menu.png in any editor ...
python tools/img_convert.py work/title_menu.png DATA/TITLE.PCX
```

## 4. Import edits back into the level

```
python tools/tr2_import.py DATA/ASSAULT.TR2 work/assault DATA/ASSAULT.TR2.new
```

- The original file is never modified in place; review/rename
  `ASSAULT.TR2.new` over `ASSAULT.TR2` yourself once you're happy with it.
- Missing tile files are simply left untouched — you only need to keep the
  ones you actually changed.
- `--which 8|16|both` (default `both`) picks which tile set(s) to write back.
- `--sync-8bit-from-16` regenerates every 8-bit tile by re-quantizing your
  edited 16-bit tile down to the level's palette, so you only ever have to
  paint the truecolor version and both stay consistent.
- 8-bit tiles are copied back byte-for-byte if you kept them in indexed mode
  with the same palette; otherwise they're re-quantized to the level's
  existing 256 colors (no new colors can be added to the 8-bit path — for
  free color choice, edit the 16-bit tiles instead).

Then point your `OpenLara.exe` at the new file (rename it into place, back up
the original first) and check it in-game.

## Sanity-checked

Round-tripping a file through `tr2_extract.py` → `tr2_import.py` with no
edits reproduces the original file byte-for-byte (verified against
`ASSAULT.TR2`). Editing a tile produces a diff localized to exactly that
tile's bytes in the file — nothing else is touched.
