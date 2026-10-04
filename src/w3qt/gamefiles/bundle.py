"""POTATO70 bundle reader (read-only).

Header: "POTATO70" u32 bundle_size u32 dummy u32 toc_size ...  (32 bytes)
TOC entries (0x130 bytes each):
    char[0x100] path, u8[16] hash, u32 offset, u32 unknown,
    u32 size, u32 compressed_size, u32 crc, u32 compressed(1)/stored(0), u8[8] zero
Compressed entries seen so far are all zlib.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

MAGIC = b"POTATO70"
ENTRY_SIZE = 0x130


@dataclass(frozen=True)
class BundleEntry:
    path: str
    offset: int
    size: int
    compressed_size: int


class Bundle:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        with open(self.path, "rb") as f:
            head = f.read(32)
            if head[:8] != MAGIC:
                raise ValueError(f"{self.path}: not a POTATO70 bundle")
            toc_size = struct.unpack_from("<I", head, 16)[0]
            toc = f.read(toc_size)
        self.entries: dict[str, BundleEntry] = {}
        for i in range(0, len(toc) - ENTRY_SIZE + 1, ENTRY_SIZE):
            raw = toc[i:i + ENTRY_SIZE]
            name = raw[:0x100].split(b"\0", 1)[0].decode("latin-1")
            if not name:
                continue
            offset, _unk, size, csize = struct.unpack_from("<4I", raw, 0x110)
            self.entries[name] = BundleEntry(name, offset, size, csize)

    def read(self, name: str) -> bytes:
        e = self.entries[name]
        with open(self.path, "rb") as f:
            f.seek(e.offset)
            data = f.read(e.compressed_size)
        if e.size == e.compressed_size:
            return data
        out = zlib.decompress(data)
        if len(out) != e.size:
            raise ValueError(f"{name}: size mismatch after zlib")
        return out
