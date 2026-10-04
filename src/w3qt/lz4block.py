"""Pure-Python LZ4 block decompressor (fallback when python-lz4 is missing)."""


def decompress(src: bytes, uncompressed_size: int) -> bytes:
    try:
        import lz4.block
    except ImportError:
        return _decompress_py(src, uncompressed_size)
    return lz4.block.decompress(src, uncompressed_size=uncompressed_size)


def _decompress_py(src: bytes, uncompressed_size: int) -> bytes:
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        dst += src[i:i + lit]
        i += lit
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("invalid LZ4 offset 0")
        mlen = token & 15
        if mlen == 15:
            while True:
                b = src[i]
                i += 1
                mlen += b
                if b != 255:
                    break
        mlen += 4
        start = len(dst) - offset
        if start < 0:
            raise ValueError("LZ4 offset out of range")
        if offset >= mlen:
            dst += dst[start:start + mlen]
        else:
            for k in range(mlen):
                dst.append(dst[start + k])
    if len(dst) != uncompressed_size:
        raise ValueError(f"LZ4 size mismatch: got {len(dst)}, expected {uncompressed_size}")
    return bytes(dst)
