"""Minimal CR2W resource reader: names table, exports and their properties.

Header: "CR2W" u32 version u32 flags u64 timestamp u32 build u32 file_size
        u32 buffer_size u32 crc u32 num_chunks, then 10 × (u32 offset, u32 count, u32 crc)
Tables used: 0 = string buffer, 1 = names (u32 string offset, u32 hash),
             4 = exports (u16 class, u16 flags, u32 parent, u32 size, u32 offset, u32 template, u32 crc)
Export data: optional 0x00 byte, then properties
             (u16 name, u16 type, u32 size incl. itself, value) until name == 0.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class Export:
    index: int  # 1-based, as used by ptr: properties
    cls: str
    parent: int
    props: dict[str, tuple[str, bytes]] = field(default_factory=dict)


@dataclass
class CR2W:
    names: list[str]
    exports: list[Export]

    def by_class(self, cls: str) -> list[Export]:
        return [e for e in self.exports if e.cls == cls]


def parse(data: bytes) -> CR2W:
    if data[:4] != b"CR2W":
        raise ValueError("not a CR2W file")
    tables = [struct.unpack_from("<III", data, 40 + 12 * i) for i in range(10)]
    s_off, s_size, _ = tables[0]
    strings = data[s_off:s_off + s_size]
    n_off, n_count, _ = tables[1]
    names = []
    for i in range(n_count):
        o = struct.unpack_from("<I", data, n_off + 8 * i)[0]
        names.append(strings[o:strings.index(b"\0", o)].decode("latin-1"))
    e_off, e_count, _ = tables[4]
    exports = []
    for i in range(e_count):
        cls, _flags, parent, size, off = struct.unpack_from("<HHIII", data, e_off + 24 * i)
        exp = Export(i + 1, names[cls], parent)
        blob = data[off:off + size]
        p = 1 if blob[:1] == b"\0" else 0
        while p + 8 <= len(blob):
            name_i, type_i, psize = struct.unpack_from("<HHI", blob, p)
            if name_i == 0:
                break
            exp.props[names[name_i]] = (names[type_i], blob[p + 8:p + 4 + psize])
            p += 4 + psize
        exports.append(exp)
    return CR2W(names, exports)


def prop_string(e: Export, name: str) -> str | None:
    """String property (REDengine length prefix, see savefile.read_cstring)."""
    from ..savefile import read_cstring
    v = e.props.get(name)
    return read_cstring(v[1], 0)[0] if v else None


def prop_u32(e: Export, name: str) -> int | None:
    v = e.props.get(name)
    return struct.unpack_from("<I", v[1])[0] if v else None


def prop_guid(e: Export, name: str = "guid") -> str | None:
    v = e.props.get(name)
    return v[1][:16].hex() if v else None


def prop_enum(doc: CR2W, e: Export, name: str) -> str | None:
    """Enums are stored as u16 name indices."""
    v = e.props.get(name)
    return doc.names[struct.unpack_from("<H", v[1])[0]] if v else None
