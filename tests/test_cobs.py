"""COBS encoder/decoder round-trip tests."""
from r10_bridge import cobs


def test_roundtrip_simple():
    cases = [
        b"hello",
        b"\x01\x02\x03",
        b"\x00",
        b"\x00\x00",
        b"\x00abc\x00def\x00",
        bytes(range(256)),
        b"\xff" * 300,
    ]
    for data in cases:
        encoded = cobs.encode(data)
        assert b"\x00" not in encoded, f"encoded contains zero for {data!r}"
        decoded = cobs.decode(encoded)
        assert decoded == data, f"roundtrip failed for {data!r}: got {decoded!r}"


def test_split_frames():
    a = cobs.encode(b"frame one")
    b = cobs.encode(b"frame two")
    stream = a + b"\x00" + b + b"\x00"
    parts = cobs.split_frames(stream)
    assert len(parts) == 2
    assert cobs.decode(parts[0]) == b"frame one"
    assert cobs.decode(parts[1]) == b"frame two"


def test_empty():
    assert cobs.decode(b"") == b""
    assert cobs.encode(b"") == b"\x01"
