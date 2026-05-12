"""Decode R10 BLE frames and E6 Connect TCP messages into canonical Shot objects.

This module is intentionally **lenient**. The R10's protobuf schema isn't
fully published — we publish what we know, attempt the decode, and on failure
still emit a CaptureFrame with the raw hex so we can iterate from real
captures without losing data.
"""
from __future__ import annotations

import binascii
import json
import logging
import struct
import zlib
from typing import Optional

from . import constants, cobs
from .models import (
    BallData,
    CaptureFrame,
    ClubData,
    Shot,
    ShotResult,
    ShotSource,
    DeviceState,
)

log = logging.getLogger("r10_bridge.protocol")


# ---------------------------------------------------------------------------
# BLE frame parsing
# ---------------------------------------------------------------------------

def parse_ble_notification(payload: bytes, char_uuid: str) -> tuple[Optional[Shot], CaptureFrame]:
    """Parse one BLE notification.

    Returns (Shot or None, CaptureFrame). The frame is ALWAYS returned so
    every byte is captured to disk even when decode fails.
    """
    raw_hex = payload.hex()
    frame = CaptureFrame(source=ShotSource.BLE_DIRECT, char_uuid=char_uuid, raw_hex=raw_hex)

    # Step 1: COBS-decode
    try:
        decoded = cobs.decode(payload.rstrip(b"\x00"))
        frame.decoded_hex = decoded.hex()
    except ValueError as e:
        frame.parse_status = "cobs_decode_failed"
        frame.parse_error = str(e)
        return None, frame

    # Step 2: Strip length prefix + CRC suffix
    try:
        stripped, crc_ok = _strip_length_and_crc(decoded)
    except ValueError as e:
        frame.parse_status = "framing_failed"
        frame.parse_error = str(e)
        return None, frame
    if not crc_ok:
        frame.parse_status = "bad_crc"
        return None, frame

    # Step 3: Protobuf decode (best-effort)
    fields = _naive_proto_decode(stripped)
    frame.parse_status = "proto_decoded" if fields else "empty"

    # Step 4: Field-tag heuristic → Shot
    shot = _shot_from_proto_fields(fields, char_uuid)
    if shot is not None:
        shot.raw_hex = raw_hex
        frame.shot_id = shot.shot_id
    return shot, frame


def _strip_length_and_crc(buf: bytes) -> tuple[bytes, bool]:
    """Strip 4-byte LE length prefix and 4-byte CRC32 suffix. Return (payload, crc_ok)."""
    if len(buf) < constants.LENGTH_PREFIX_BYTES + constants.CRC_SUFFIX_BYTES:
        raise ValueError(f"frame too short ({len(buf)} bytes)")

    declared_len = struct.unpack_from("<I", buf, 0)[0]
    payload_end = constants.LENGTH_PREFIX_BYTES + declared_len
    if payload_end + constants.CRC_SUFFIX_BYTES > len(buf):
        raise ValueError(
            f"declared length {declared_len} overflows buffer of {len(buf)} bytes"
        )

    payload = buf[constants.LENGTH_PREFIX_BYTES:payload_end]
    declared_crc = struct.unpack_from("<I", buf, payload_end)[0]
    computed_crc = zlib.crc32(payload) & 0xFFFFFFFF
    return payload, declared_crc == computed_crc


def _naive_proto_decode(buf: bytes) -> dict:
    """Walk protobuf wire format and return {tag: [value, ...]} dict.

    This is intentionally a partial decoder. We don't need the full schema to
    extract numeric metrics — we just need (tag, wire_type) → value and we
    treat known tags semantically downstream.
    """
    fields: dict[int, list] = {}
    i = 0
    n = len(buf)
    while i < n:
        try:
            tag_byte, i = _read_varint(buf, i)
        except (IndexError, ValueError):
            break
        tag = tag_byte >> 3
        wire_type = tag_byte & 0x07

        try:
            if wire_type == 0:  # varint
                v, i = _read_varint(buf, i)
            elif wire_type == 1:  # 64-bit fixed
                v = struct.unpack_from("<d", buf, i)[0]
                i += 8
            elif wire_type == 2:  # length-delimited (string / bytes / embedded msg)
                ln, i = _read_varint(buf, i)
                v = buf[i:i + ln]
                i += ln
            elif wire_type == 5:  # 32-bit fixed
                v = struct.unpack_from("<f", buf, i)[0]
                i += 4
            else:
                # group types (3,4) are deprecated and shouldn't appear in proto3
                break
        except (struct.error, IndexError):
            break

        fields.setdefault(tag, []).append(v)
    return fields


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    """Decode one varint starting at index i. Returns (value, next_index)."""
    result = 0
    shift = 0
    while True:
        if i >= len(buf):
            raise IndexError("varint runs past end of buffer")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def _shot_from_proto_fields(fields: dict, char_uuid: str) -> Optional[Shot]:
    """Build a Shot from naive proto fields if it looks like measurement data.

    Heuristic: the Metrics message contains many wire_type=5 (float) values
    once decoded. If we see a length-delimited field at the LaunchMonitorService
    tag (38) and it contains floats, treat it as a shot.

    This is intentionally optimistic. After we have real captures, this
    function should be replaced with `betterproto` or `protobuf` library decoding
    using the real schema.
    """
    if 38 not in fields:
        return None

    embedded_msgs = [v for v in fields[38] if isinstance(v, bytes)]
    if not embedded_msgs:
        return None

    floats: list[float] = []
    for msg in embedded_msgs:
        sub = _naive_proto_decode(msg)
        for vs in sub.values():
            for v in vs:
                if isinstance(v, float):
                    floats.append(v)

    if len(floats) < 3:
        return None

    # Best-effort mapping: order is well-defined within proto messages but
    # we don't know the exact ordering of the unpublished Metrics message.
    # The first capture session will let us pin these to specific tags.
    shot = Shot(source=ShotSource.BLE_DIRECT)
    shot.swing.head_speed_mph     = _pick(floats, 0)
    shot.ball.speed_mph           = _pick(floats, 1)
    shot.ball.launch_angle_deg    = _pick(floats, 2)
    shot.ball.launch_direction_deg= _pick(floats, 3)
    shot.ball.total_spin_rpm      = _pick(floats, 4)
    shot.ball.back_spin_rpm       = _pick(floats, 5)
    shot.ball.side_spin_rpm       = _pick(floats, 6)
    shot.ball.spin_axis_deg       = _pick(floats, 7)
    shot.swing.club_path_deg      = _pick(floats, 8)
    shot.swing.face_angle_deg     = _pick(floats, 9)
    shot.swing.attack_angle_deg   = _pick(floats, 10)
    shot.result.apex_height_yd    = _pick(floats, 11)
    shot.result.carry_distance_yd = _pick(floats, 12)
    shot.result.total_distance_yd = _pick(floats, 13)
    shot.result.deviation_angle_deg = _pick(floats, 14)
    shot.result.deviation_distance_yd = _pick(floats, 15)
    shot.result.hang_time_sec     = _pick(floats, 16)

    # Smash factor: prefer reported; else compute from speeds
    if (shot.swing.head_speed_mph and shot.swing.head_speed_mph > 0
            and shot.ball.speed_mph):
        shot.result.smash_factor = round(shot.ball.speed_mph / shot.swing.head_speed_mph, 3)

    return shot


def _pick(seq: list, idx: int):
    return seq[idx] if 0 <= idx < len(seq) else None


# ---------------------------------------------------------------------------
# E6 Connect TCP JSON parsing
# ---------------------------------------------------------------------------

def parse_e6_message(raw: bytes) -> tuple[Optional[Shot], CaptureFrame, Optional[dict]]:
    """Decode one E6 Connect TCP JSON message.

    Returns (Shot or None, CaptureFrame, response_payload or None).
    response_payload is what the bridge should send back to keep the Garmin
    app happy (usually a generic acknowledgment).
    """
    frame = CaptureFrame(source=ShotSource.E6_CONNECT, raw_hex=raw.hex())

    try:
        # Some E6 implementations newline-delimit; some length-prefix. Try both.
        text = raw.decode("utf-8", errors="replace").strip()
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        frame.parse_status = "json_decode_failed"
        frame.parse_error = str(e)
        return None, frame, None

    msg_type = payload.get("Type") or payload.get("type") or payload.get("MessageType")
    frame.parse_status = f"json:{msg_type}" if msg_type else "json:unknown"

    response: Optional[dict] = None
    shot: Optional[Shot] = None

    if msg_type in (constants.E6MessageType.HANDSHAKE, "Handshake"):
        response = {"Type": "Handshake", "Status": "Accepted"}
    elif msg_type in (constants.E6MessageType.PING, "Ping"):
        response = {"Type": "Pong"}
    elif msg_type in (constants.E6MessageType.CHALLENGE, "Challenge"):
        response = {"Type": "Authentication", "Status": "Accepted"}
    elif msg_type in (constants.E6MessageType.SET_BALL_DATA, "SetBallData",
                      constants.E6MessageType.SET_CLUB_DATA, "SetClubData",
                      constants.E6MessageType.SEND_SHOT, "SendShot",
                      constants.E6MessageType.SHOT_COMPLETE, "ShotComplete"):
        shot = _shot_from_e6_payload(payload)
        if shot:
            shot.raw_json = json.dumps(payload)
            frame.shot_id = shot.shot_id
        response = {"Type": "ShotAcknowledged"}

    return shot, frame, response


def _shot_from_e6_payload(payload: dict) -> Optional[Shot]:
    """Build a Shot from a SetBallData / SetClubData / SendShot E6 message."""
    ball_raw = payload.get("BallData") or payload.get("Ball") or {}
    club_raw = payload.get("ClubData") or payload.get("Club") or {}
    result_raw = payload.get("ShotDetails") or payload.get("Details") or {}

    def _f(d: dict, *keys):
        for k in keys:
            if k in d and d[k] is not None:
                try:
                    return float(d[k])
                except (TypeError, ValueError):
                    pass
        return None

    shot = Shot(source=ShotSource.E6_CONNECT)
    shot.ball.speed_mph             = _f(ball_raw, "BallSpeed", "Speed")
    shot.ball.launch_angle_deg      = _f(ball_raw, "LaunchAngle", "VLA")
    shot.ball.launch_direction_deg  = _f(ball_raw, "LaunchDirection", "HLA")
    shot.ball.total_spin_rpm        = _f(ball_raw, "TotalSpin", "Spin")
    shot.ball.back_spin_rpm         = _f(ball_raw, "BackSpin")
    shot.ball.side_spin_rpm         = _f(ball_raw, "SideSpin")
    shot.ball.spin_axis_deg         = _f(ball_raw, "SpinAxis")

    shot.swing.head_speed_mph       = _f(club_raw, "ClubHeadSpeed", "HeadSpeed", "Speed")
    shot.swing.club_path_deg        = _f(club_raw, "ClubPath", "Path", "SwingPath")
    shot.swing.face_angle_deg       = _f(club_raw, "FaceAngle", "Face")
    shot.swing.attack_angle_deg     = _f(club_raw, "AttackAngle")

    shot.result.apex_height_yd      = _f(result_raw, "ApexHeight", "Apex")
    shot.result.carry_distance_yd   = _f(result_raw, "Carry", "CarryDistance")
    shot.result.total_distance_yd   = _f(result_raw, "Total", "TotalDistance")
    shot.result.deviation_angle_deg = _f(result_raw, "DeviationAngle")
    shot.result.deviation_distance_yd = _f(result_raw, "DeviationDistance")
    shot.result.hang_time_sec       = _f(result_raw, "HangTime")

    if (shot.swing.head_speed_mph and shot.swing.head_speed_mph > 0
            and shot.ball.speed_mph):
        shot.result.smash_factor = round(shot.ball.speed_mph / shot.swing.head_speed_mph, 3)

    # If nothing was filled, this wasn't a shot message
    populated = (shot.ball.speed_mph is not None or
                 shot.swing.head_speed_mph is not None or
                 shot.result.carry_distance_yd is not None)
    return shot if populated else None
