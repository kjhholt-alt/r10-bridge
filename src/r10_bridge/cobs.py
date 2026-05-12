"""Consistent Overhead Byte Stuffing (COBS) encoder/decoder.

The R10 frames BLE messages with COBS so that 0x00 can serve as an
unambiguous frame delimiter inside the otherwise-binary stream.

Reference: RFC equivalent; see Wikipedia "Consistent Overhead Byte Stuffing".

Encoded frames end with a single 0x00 byte. Decode strips that and substitutes
the stuffed zero positions back to actual zeros.
"""
from __future__ import annotations


def encode(data: bytes) -> bytes:
    """COBS-encode `data`. Output never contains 0x00 except as terminator (not appended here)."""
    if not data:
        return b"\x01"
    out = bytearray()
    out.append(0)  # placeholder for first code byte
    code_idx = 0
    code = 1
    for b in data:
        if b == 0:
            out[code_idx] = code
            code_idx = len(out)
            out.append(0)
            code = 1
        else:
            out.append(b)
            code += 1
            if code == 0xFF:
                out[code_idx] = code
                code_idx = len(out)
                out.append(0)
                code = 1
    out[code_idx] = code
    return bytes(out)


def decode(data: bytes) -> bytes:
    """Inverse of encode. Raises ValueError on malformed input."""
    if not data:
        return b""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        code = data[i]
        if code == 0:
            raise ValueError("Unexpected 0x00 in COBS-encoded data")
        i += 1
        end = i + code - 1
        if end > n:
            raise ValueError("COBS code points past end of buffer")
        out.extend(data[i:end])
        i = end
        if code < 0xFF and i < n:
            out.append(0)
    return bytes(out)


def split_frames(stream: bytes) -> list[bytes]:
    """Split a stream of COBS-encoded frames separated by 0x00 terminators."""
    return [chunk for chunk in stream.split(b"\x00") if chunk]
