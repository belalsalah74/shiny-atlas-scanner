"""Small, dependency-free Protocol Buffers wire codec for the POGO messages used here.

This codec does not guess schemas: callers must know the field numbers they use.
"""
from __future__ import annotations

from collections import defaultdict
import struct
from typing import Any


def varint(value: int) -> bytes:
    if not isinstance(value, int) or value < 0 or value > (1 << 64) - 1:
        raise ValueError("protobuf varint must be an unsigned 64-bit integer")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def int_field(number: int, value: int) -> bytes:
    if number < 1:
        raise ValueError("protobuf field numbers start at 1")
    return varint(number << 3) + varint(value)


def bytes_field(number: int, value: bytes | bytearray | memoryview | str) -> bytes:
    if number < 1:
        raise ValueError("protobuf field numbers start at 1")
    if isinstance(value, str):
        value = value.encode("utf-8")
    payload = bytes(value)
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def double_field(number: int, value: float) -> bytes:
    if number < 1:
        raise ValueError("protobuf field numbers start at 1")
    return varint((number << 3) | 1) + struct.pack("<d", float(value))


def decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while shift < 70:
        if offset >= len(data):
            raise ValueError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            if value > (1 << 64) - 1:
                raise ValueError("protobuf varint exceeds uint64")
            return value, offset
        shift += 7
    raise ValueError("oversized protobuf varint")


def fields(data: bytes, *, max_size: int = 4_000_000) -> dict[int, list[Any]]:
    """Decode one protobuf message into field-number -> values.

    Lengths are bounded so malformed responses cannot allocate unbounded memory.
    Wire types 0, 1, 2 and 5 are supported; group wire types are rejected.
    """
    if not isinstance(data, bytes):
        raise TypeError("protobuf input must be bytes")
    if len(data) > max_size:
        raise ValueError("protobuf message exceeds configured size limit")
    out: dict[int, list[Any]] = defaultdict(list)
    offset = 0
    while offset < len(data):
        tag, offset = decode_varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if number < 1:
            raise ValueError("invalid protobuf field number 0")
        if wire == 0:
            value, offset = decode_varint(data, offset)
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            end = offset + length
            if end > len(data):
                raise ValueError("truncated fixed-width protobuf field")
            value = data[offset:end]
            offset = end
        elif wire == 2:
            length, offset = decode_varint(data, offset)
            if length > max_size or offset + length > len(data):
                raise ValueError("invalid or truncated length-delimited protobuf field")
            value = data[offset:offset + length]
            offset += length
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")
        out[number].append(value)
    return dict(out)


def one(message: dict[int, list[Any]], number: int, default: Any = None) -> Any:
    values = message.get(number)
    return values[-1] if values else default


def text(message: dict[int, list[Any]], number: int, default: str = "") -> str:
    value = one(message, number)
    if not isinstance(value, bytes):
        return default
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return default


def packed_ints(message: dict[int, list[Any]], number: int) -> list[int]:
    result: list[int] = []
    for value in message.get(number, []):
        if isinstance(value, int):
            result.append(value)
            continue
        if not isinstance(value, bytes):
            raise ValueError("unexpected packed integer field value")
        offset = 0
        while offset < len(value):
            item, offset = decode_varint(value, offset)
            result.append(item)
    return result


def double(message: dict[int, list[Any]], number: int, default: float = 0.0) -> float:
    value = one(message, number)
    if isinstance(value, bytes) and len(value) == 8:
        return struct.unpack("<d", value)[0]
    return default
