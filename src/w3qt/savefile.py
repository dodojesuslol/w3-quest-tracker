"""Read-only parser for The Witcher 3 (REDengine 3) .sav files.

Layout as reverse-engineered from real saves (save version 66, game 5.0):

Container (on disk)
    "SNFHFZLC"                  magic
    u32 chunk_count
    u32 header_size             offset of first compressed chunk (3084 so far)
    chunk_count * (u32 compressed_size, u32 decompressed_size, u32 end_offset)
    LZ4 block-compressed chunks, back to back

Decompressed stream
    "SAV3" u32 save_version u32 game_version u32 unknown
    tree of BS (block) / VL (value) / SS / OP records
    "MANU" string table, "ENOD", then "SC" variable table
    footer: u32 string_table_offset, u32 unknown, u32 variable_table_offset, "SE"

All offsets stored in the stream count from the start of the *on-disk*
file, i.e. they include header_size.

Records
    BS <u16 name>                       block; extent comes from the variable table
    VL <u16 name> <u16 type> <value>    value; size from the variable table
    SS <u32 size> <payload>             opaque stream (facts DB lives here)
Name/type u16s are 1-based indices into the string table.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from .lz4block import decompress

CONTAINER_MAGIC = b"SNFHFZLC"
STREAM_MAGIC = b"SAV3"
STRING_TABLE_MAGIC = b"MANU"
FOOTER_MAGIC = b"SE"
STRUCTURED_TAGS = (b"BS", b"VL", b"SS", b"OP")
# Only the current next-gen/REDkit format (game 4.04+/5.0) is supported.
SUPPORTED_SAVE_VERSIONS = (66,)


class SaveFormatError(Exception):
    """File is not a Witcher 3 save, or it is truncated (e.g. still being written)."""


class UnsupportedSaveVersion(SaveFormatError):
    """Valid save, but from a game version this parser does not support."""


@dataclass
class Node:
    tag: str
    offset: int  # into decompressed stream
    end: int
    name: str | None = None
    type: str | None = None
    raw: bytes = b""
    children: list[Node] = field(default_factory=list)

    def child(self, name: str) -> Node | None:
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name: str) -> list[Node]:
        return [c for c in self.children if c.name == name]


@dataclass
class SaveFile:
    path: Path
    save_version: int
    game_version: int
    header_size: int
    data: bytes
    names: list[str]
    root: Node

    def name(self, index: int) -> str | None:
        if index == 0 or index > len(self.names):
            return None
        return self.names[index - 1]

    def block(self, name: str) -> Node | None:
        return self.root.child(name)


def read_container(raw: bytes) -> tuple[int, bytes]:
    """Return (header_size, decompressed stream)."""
    if len(raw) < 16 or raw[:8] != CONTAINER_MAGIC:
        raise SaveFormatError("missing SNFHFZLC magic")
    count, header_size = struct.unpack_from("<II", raw, 8)
    if not 0 < count < 1024 or 16 + 12 * count > header_size:
        raise SaveFormatError(f"implausible chunk table (count={count}, header={header_size})")
    out = bytearray()
    pos = header_size
    for i in range(count):
        csize, usize, _end = struct.unpack_from("<III", raw, 16 + 12 * i)
        if pos + csize > len(raw):
            raise SaveFormatError(f"chunk {i} truncated (file still being written?)")
        try:
            out += decompress(raw[pos:pos + csize], usize)
        except Exception as e:  # lz4 raises various types
            raise SaveFormatError(f"chunk {i} failed to decompress: {e}") from e
        pos += csize
    return header_size, bytes(out)


def read_cstring(buf: bytes, p: int) -> tuple[str, int]:
    """REDengine length-prefixed string. Returns (text, new_offset).

    Prefix byte: bit 0x80 = 8-bit chars (else UTF-16LE), bit 0x40 = one more
    length byte follows (length = low6 | next << 6).
    """
    b = buf[p]
    p += 1
    narrow = b & 0x80
    length = b & 0x3F
    if b & 0x40:
        length |= buf[p] << 6
        p += 1
    if narrow:
        return buf[p:p + length].decode("latin-1"), p + length
    return buf[p:p + 2 * length].decode("utf-16-le", "replace"), p + 2 * length


def _read_string_table(data: bytes, p: int) -> list[str]:
    if data[p:p + 4] != STRING_TABLE_MAGIC:
        raise SaveFormatError("string table magic MANU not found")
    count, _unknown = struct.unpack_from("<II", data, p + 4)
    p += 12
    names = []
    for _ in range(count):
        # String-table entries use the same prefix, without the 0x80 flag.
        b = data[p]
        p += 1
        length = b & 0x3F
        if b & 0x40:
            length |= data[p] << 6
            p += 1
        names.append(data[p:p + length].decode("latin-1"))
        p += length
    return names


def _build_tree(data: bytes, entries: list[tuple[int, int]], name_of) -> Node:
    recs = []
    for off, size in entries:
        tag = data[off:off + 2]
        if tag in STRUCTURED_TAGS:
            recs.append((off, size, tag))
    recs.sort(key=lambda r: (r[0], -r[1]))
    root = Node("ROOT", -1, len(data))
    stack = [root]
    for off, size, tag in recs:
        while off >= stack[-1].end:
            stack.pop()
        node = Node(tag.decode(), off, off + size)
        if tag in (b"BS", b"VL"):
            node.name = name_of(struct.unpack_from("<H", data, off + 2)[0])
        if tag == b"VL":
            node.type = name_of(struct.unpack_from("<H", data, off + 4)[0])
            node.raw = data[off + 6:off + size]
        stack[-1].children.append(node)
        stack.append(node)
    return root


def parse_bytes(raw: bytes, path: Path | str = "<memory>") -> SaveFile:
    header_size, data = read_container(raw)
    if data[:4] != STREAM_MAGIC:
        raise SaveFormatError("decompressed stream does not start with SAV3")
    if data[-2:] != FOOTER_MAGIC:
        raise SaveFormatError("footer magic SE missing (truncated?)")
    save_version, game_version = struct.unpack_from("<II", data, 4)
    if save_version not in SUPPORTED_SAVE_VERSIONS:
        raise UnsupportedSaveVersion(f"unsupported save version {save_version} (supported: {SUPPORTED_SAVE_VERSIONS})")
    str_off, _unk, var_off = struct.unpack_from("<III", data, len(data) - 14)
    str_off -= header_size
    var_off -= header_size
    if not (0 <= str_off < len(data) and 0 <= var_off < len(data)):
        raise SaveFormatError("footer offsets out of range")
    names = _read_string_table(data, str_off)

    def name_of(i: int) -> str | None:
        return names[i - 1] if 0 < i <= len(names) else None

    count = struct.unpack_from("<I", data, var_off)[0]
    entries = [
        (o - header_size, s)
        for o, s in struct.iter_unpack("<II", data[var_off + 4:var_off + 4 + 8 * count])
    ]
    root = _build_tree(data, entries, name_of)
    return SaveFile(Path(path), save_version, game_version, header_size, data, names, root)


def open_save(path: Path | str) -> SaveFile:
    """Open strictly read-only and parse."""
    path = Path(path)
    with open(path, "rb") as f:
        raw = f.read()
    return parse_bytes(raw, path)


# --- value decoding -------------------------------------------------------

def decode_value(save: SaveFile, node: Node):
    """Decode common scalar VL types; returns raw hex for anything else."""
    t, raw = node.type or "", node.raw
    try:
        if t == "Bool":
            return bool(raw[0])
        if t in ("Uint8", "Int8"):
            return struct.unpack("<B" if t == "Uint8" else "<b", raw[:1])[0]
        if t in ("Uint16", "Int16"):
            return struct.unpack("<H" if t == "Uint16" else "<h", raw[:2])[0]
        if t in ("Uint32", "Int32"):
            return struct.unpack("<I" if t == "Uint32" else "<i", raw[:4])[0]
        if t in ("Uint64", "Int64"):
            return struct.unpack("<Q" if t == "Uint64" else "<q", raw[:8])[0]
        if t == "Float":
            return struct.unpack("<f", raw[:4])[0]
        if t == "String":
            return read_cstring(raw, 0)[0]
        if t == "StringAnsi":
            # u8 length incl. trailing NUL
            return raw[1:raw[0]].decode("latin-1")
        if t == "CGUID":
            return raw[:16].hex()
        if t == "CName" or t.startswith("E"):  # enums are stored as name indices
            return save.name(struct.unpack("<H", raw[:2])[0])
    except (struct.error, IndexError):
        pass
    return {"type": t, "hex": raw.hex()}
