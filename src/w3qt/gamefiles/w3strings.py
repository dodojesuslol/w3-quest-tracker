"""Decoder for next-gen .w3strings localisation files.

Reverse-engineered from en/de files of game build 5.0:
    "RTSW" u32 version u16 key1
    cint n1, n1 × (u32 id ^ lang_key, u32 offset, u32 length)    offsets/lengths in bytes
    cint n2, n2 × (u32 key_hash, u32 id ^ lang_key)
    u16 key2, …
    string data = last (max(offset+length) + 3) bytes of the file, UTF-8, each
    string NUL-terminated and XOR-encrypted:
        byte[i] ^= ((length + 1) * hi8(rotl16(C, i % 16))) & 0xFF
    with C = byteswap16((lang_key >> 8) & 0xFFFF).
lang_key is not stored in the file. find_lang_key() recovers it from known
string ids (e.g. journal titles); for en it is 0x79321793.
"""

from __future__ import annotations

import struct
from pathlib import Path


def _cint(d: bytes, p: int) -> tuple[int, int]:
    b = d[p]
    p += 1
    v = b & 0x3F
    if b & 0x40:
        shift = 6
        while True:
            b = d[p]
            p += 1
            v |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                break
    return v, p


def _rotl16(v: int, n: int) -> int:
    return ((v << n) | (v >> (16 - n))) & 0xFFFF


class W3Strings:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        d = self.path.read_bytes()
        if d[:4] != b"RTSW":
            raise ValueError(f"{self.path}: not a w3strings file")
        n, p = _cint(d, 10)
        self._table = [struct.unpack_from("<III", d, p + 12 * i) for i in range(n)]
        end = max(o + ln for _, o, ln in self._table)
        self._data = d[len(d) - (end + 3):]
        self._key: int | None = None
        self._by_id: dict[int, tuple[int, int]] = {}

    @property
    def raw_ids(self) -> set[int]:
        return {i for i, _, _ in self._table}

    def find_lang_key(self, known_ids: set[int], min_hits: float = 0.95) -> int:
        """Solve the per-language id XOR key from string ids known to exist."""
        known = sorted(i for i in known_ids if i)
        if len(known) < 20:
            raise ValueError("need at least 20 known string ids")
        raw = self.raw_ids
        cands = {r ^ known[0] for r in raw}
        for k in known[1:200]:
            nxt = {c for c in cands if (k ^ c) in raw}
            if not nxt:  # tolerate a few ids missing from this language
                continue
            cands = nxt
            if len(cands) == 1:
                break
        best = max(cands, key=lambda c: sum((k ^ c) in raw for k in known))
        hits = sum((k ^ best) in raw for k in known) / len(known)
        if hits < min_hits:
            raise ValueError(f"no consistent language key (best hit rate {hits:.2%})")
        return best

    def set_key(self, lang_key: int) -> None:
        self._key = lang_key
        self._by_id = {i ^ lang_key: (o, ln) for i, o, ln in self._table}
        c = lang_key >> 8 & 0xFFFF
        self._c = ((c & 0xFF) << 8) | (c >> 8)
        # sanity check: a sample must decode as UTF-8
        for sid in list(self._by_id)[:200]:
            self.get(sid)

    def get(self, string_id: int) -> str | None:
        if self._key is None:
            raise RuntimeError("call set_key() first")
        hit = self._by_id.get(string_id)
        if hit is None:
            return None
        o, ln = hit
        mult = ln + 1
        out = bytes(
            b ^ ((mult * (_rotl16(self._c, i % 16) >> 8)) & 0xFF)
            for i, b in enumerate(self._data[o:o + ln])
        )
        return out.decode("utf-8")
