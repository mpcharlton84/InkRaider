"""
tr2lib.py - Minimal, dependency-light reader for Tomb Raider II (.TR2) level files.

This module knows just enough about the TR2 binary format to:
  1. Read/write the texture tile blocks (8-bit palettized + 16-bit ARGB) without
     needing to understand anything else in the file (they sit right after the
     palettes, near the start of the file, and are fixed-size, so patching them
     back in place never changes the file's length or breaks any offsets).
  2. Walk the rest of the file (rooms, meshes, models, object textures) far
     enough to figure out which texture tiles / regions belong to Lara's mesh,
     so texture edits for "the Lara model" can be targeted precisely.

Format reference: TRosettaStone 3 (community format docs) cross-checked against
OpenLara's src/format.h (the actual engine you're using) to confirm exact byte
sizes. Only TR2 (version 0x0000002D) PC-format files are supported; this is
what ASSAULT.TR2 / TITLE.tr2 / your custom level files are.

No third-party dependencies (stdlib only). Image conversion helpers that need
Pillow/numpy live in the CLI scripts, not here.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import BinaryIO, List

TILE_SIZE = 256  # texture tiles are always 256x256 px
TILE8_BYTES = TILE_SIZE * TILE_SIZE          # 65536
TILE16_BYTES = TILE_SIZE * TILE_SIZE * 2     # 131072

TR2_VERSION = 0x0000002D


class Tr2Error(Exception):
    pass


def _read(f: BinaryIO, n: int) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise Tr2Error(f"Unexpected EOF: wanted {n} bytes, got {len(data)} at offset {f.tell()}")
    return data


def _u8(f):  return struct.unpack('<B', _read(f, 1))[0]
def _u16(f): return struct.unpack('<H', _read(f, 2))[0]
def _i16(f): return struct.unpack('<h', _read(f, 2))[0]
def _u32(f): return struct.unpack('<I', _read(f, 4))[0]


@dataclass
class TextureHeader:
    """Everything before the room list: version, palettes, and tile blocks."""
    version: int
    palette: bytes          # 256*3 bytes, RGB 0..255 (already up-scaled from 6-bit VGA)
    palette16: bytes         # 256*4 bytes, RGBA (A byte unused)
    num_textiles: int
    textiles8_offset: int     # absolute file offset where Textile8[] begins
    textiles16_offset: int    # absolute file offset where Textile16[] begins
    after_tiles_offset: int   # absolute file offset right after Textile16[] (start of "Unused" u32)


@dataclass
class ObjectTexture:
    attribute: int
    tile: int                # 0..num_textiles-1
    # 4 corners in *pixel* coordinates within the tile (whole-part only; the
    # fractional byte that TR stores alongside each coordinate is discarded,
    # it's always ~0 in levels built by the original tools)
    coords: List[tuple]      # [(x,y), (x,y), (x,y), (x,y)] ; 4th is (0,0) for triangles


@dataclass
class Model:
    type_id: int
    num_meshes: int
    starting_mesh: int
    mesh_tree_offset: int
    frame_offset: int
    animation: int


def read_texture_header(f: BinaryIO) -> TextureHeader:
    f.seek(0)
    version = _u32(f)
    if version != TR2_VERSION:
        raise Tr2Error(
            f"Unexpected version 0x{version:08X} (expected TR2 0x{TR2_VERSION:08X}). "
            "This tool only supports classic PC TR2 level files."
        )
    palette = _read(f, 256 * 3)
    palette16 = _read(f, 256 * 4)
    num_textiles = _u32(f)
    textiles8_offset = f.tell()
    f.seek(num_textiles * TILE8_BYTES, 1)
    textiles16_offset = f.tell()
    f.seek(num_textiles * TILE16_BYTES, 1)
    after_tiles_offset = f.tell()
    return TextureHeader(
        version=version,
        palette=palette,
        palette16=palette16,
        num_textiles=num_textiles,
        textiles8_offset=textiles8_offset,
        textiles16_offset=textiles16_offset,
        after_tiles_offset=after_tiles_offset,
    )


def read_textile8(f: BinaryIO, hdr: TextureHeader, index: int) -> bytes:
    if not (0 <= index < hdr.num_textiles):
        raise Tr2Error(f"Tile index {index} out of range (0..{hdr.num_textiles - 1})")
    f.seek(hdr.textiles8_offset + index * TILE8_BYTES)
    return _read(f, TILE8_BYTES)


def read_textile16(f: BinaryIO, hdr: TextureHeader, index: int) -> bytes:
    if not (0 <= index < hdr.num_textiles):
        raise Tr2Error(f"Tile index {index} out of range (0..{hdr.num_textiles - 1})")
    f.seek(hdr.textiles16_offset + index * TILE16_BYTES)
    return _read(f, TILE16_BYTES)


def write_textile8(f: BinaryIO, hdr: TextureHeader, index: int, data: bytes) -> None:
    if len(data) != TILE8_BYTES:
        raise Tr2Error(f"8-bit tile must be exactly {TILE8_BYTES} bytes, got {len(data)}")
    f.seek(hdr.textiles8_offset + index * TILE8_BYTES)
    f.write(data)


def write_textile16(f: BinaryIO, hdr: TextureHeader, index: int, data: bytes) -> None:
    if len(data) != TILE16_BYTES:
        raise Tr2Error(f"16-bit tile must be exactly {TILE16_BYTES} bytes, got {len(data)}")
    f.seek(hdr.textiles16_offset + index * TILE16_BYTES)
    f.write(data)


# ---------------------------------------------------------------------------
# Deep parsing (rooms -> meshes -> models -> object textures), needed only to
# figure out which tiles/regions belong to Lara's model.
# ---------------------------------------------------------------------------

def _skip_room(f: BinaryIO) -> None:
    f.seek(16, 1)                       # tr_room_info
    num_data_words = _u32(f)
    f.seek(num_data_words * 2, 1)       # raw room mesh data (vertices/quads/tris/sprites)
    num_portals = _u16(f)
    f.seek(num_portals * 32, 1)
    num_z = _u16(f)
    num_x = _u16(f)
    f.seek(num_z * num_x * 8, 1)        # sector list
    f.seek(6, 1)                        # AmbientIntensity, AmbientIntensity2, LightMode
    num_lights = _u16(f)
    f.seek(num_lights * 24, 1)          # tr2_room_light
    num_static = _u16(f)
    f.seek(num_static * 20, 1)          # tr2_room_staticmesh
    f.seek(4, 1)                        # AlternateRoom, Flags


@dataclass
class ParsedLevel:
    header: TextureHeader
    mesh_data: bytes
    mesh_pointers: List[int]
    models: List[Model]
    object_textures: List[ObjectTexture]


def parse_level(f: BinaryIO) -> ParsedLevel:
    """Parse far enough into the file to recover Models[], MeshPointers[],
    the raw mesh-data blob, and ObjectTextures[]. Does not parse anything
    after ObjectTextures (sprites, entities, sound, etc.) since we don't
    need it."""
    hdr = read_texture_header(f)
    f.seek(hdr.after_tiles_offset)
    _u32(f)  # Unused

    num_rooms = _u16(f)
    for _ in range(num_rooms):
        _skip_room(f)

    num_floor_data = _u32(f)
    f.seek(num_floor_data * 2, 1)

    num_mesh_data = _u32(f)   # count of uint16 words
    mesh_data = _read(f, num_mesh_data * 2)

    num_mesh_pointers = _u32(f)
    mesh_pointers = list(struct.unpack(f'<{num_mesh_pointers}I', _read(f, num_mesh_pointers * 4)))

    num_animations = _u32(f)
    f.seek(num_animations * 32, 1)

    num_state_changes = _u32(f)
    f.seek(num_state_changes * 6, 1)

    num_anim_dispatches = _u32(f)
    f.seek(num_anim_dispatches * 8, 1)

    num_anim_commands = _u32(f)
    f.seek(num_anim_commands * 2, 1)

    num_mesh_trees = _u32(f)  # word count (each node = 4 words); skip in bytes
    f.seek(num_mesh_trees * 4, 1)

    num_frames = _u32(f)      # word count
    f.seek(num_frames * 2, 1)

    num_models = _u32(f)
    models = []
    for _ in range(num_models):
        type_id = _u16(f)
        f.seek(2, 1)  # high 16 bits of the file's uint32 ID, always 0 for PC TR2
        num_meshes = _u16(f)
        starting_mesh = _u16(f)
        mesh_tree_offset = _u32(f)
        frame_offset = _u32(f)
        animation = _u16(f)
        models.append(Model(type_id, num_meshes, starting_mesh, mesh_tree_offset, frame_offset, animation))

    num_static_meshes = _u32(f)
    f.seek(num_static_meshes * 32, 1)

    num_object_textures = _u32(f)
    object_textures = []
    for _ in range(num_object_textures):
        attribute = _u16(f)
        tile_and_flag = _u16(f)
        tile = tile_and_flag & 0x3FFF
        coords = []
        for _c in range(4):
            xh, x, yh, y = struct.unpack('<BBBB', _read(f, 4))
            coords.append((x, y))
        object_textures.append(ObjectTexture(attribute, tile, coords))

    return ParsedLevel(hdr, mesh_data, mesh_pointers, models, object_textures)


def _parse_mesh_texture_indices(mesh_data: bytes, offset: int) -> List[int]:
    """Parse one tr_mesh at byte `offset` in mesh_data and return the list of
    ObjectTexture indices used by its textured rectangles/triangles."""
    pos = offset
    def read_i16():
        nonlocal pos
        v = struct.unpack_from('<h', mesh_data, pos)[0]
        pos += 2
        return v
    def read_u16():
        nonlocal pos
        v = struct.unpack_from('<H', mesh_data, pos)[0]
        pos += 2
        return v

    pos += 6      # Centre (3x int16)
    pos += 4      # CollRadius (int32)
    num_vertices = read_i16()
    pos += num_vertices * 6
    num_normals = read_i16()
    if num_normals > 0:
        pos += num_normals * 6
    else:
        pos += abs(num_normals) * 2

    tex_indices = []

    num_tex_rect = read_i16()
    for _ in range(num_tex_rect):
        pos += 8  # 4x uint16 vertex indices
        tex_indices.append(read_u16())

    num_tex_tri = read_i16()
    for _ in range(num_tex_tri):
        pos += 6  # 3x uint16 vertex indices
        tex_indices.append(read_u16())

    num_col_rect = read_i16()
    pos += num_col_rect * 10
    num_col_tri = read_i16()
    pos += num_col_tri * 8

    return tex_indices


def find_lara_tile_usage(level: ParsedLevel, model_type_id: int = 0) -> dict:
    """Returns {tile_index: [(x,y),(x,y),...]} listing the object-texture
    corner points (as pixel coords within that tile) used anywhere in the
    given model's meshes (default type_id=0 == Lara in TR1/TR2)."""
    model = next((m for m in level.models if m.type_id == model_type_id), None)
    if model is None:
        raise Tr2Error(f"No model with type id {model_type_id} found in this file")

    usage: dict = {}
    for mesh_slot in range(model.starting_mesh, model.starting_mesh + model.num_meshes):
        if mesh_slot >= len(level.mesh_pointers):
            continue
        mesh_offset = level.mesh_pointers[mesh_slot]
        tex_indices = _parse_mesh_texture_indices(level.mesh_data, mesh_offset)
        for ti in tex_indices:
            if ti >= len(level.object_textures):
                continue
            ot = level.object_textures[ti]
            usage.setdefault(ot.tile, []).append(ot.coords)
    return usage
