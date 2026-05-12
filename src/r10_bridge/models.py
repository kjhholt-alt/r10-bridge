"""Pydantic models for everything the R10 reports.

These mirror the field shapes inside the LaunchMonitor.proto schema and the
E6 Connect JSON message types, normalized to one canonical Shot record so the
rest of the bridge doesn't care which transport produced it.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ShotSource(str, Enum):
    BLE_DIRECT = "ble_direct"
    E6_CONNECT = "e6_connect"
    CSV_INGEST = "csv_ingest"


class DeviceState(str, Enum):
    STANDBY = "STANDBY"
    INTERFERENCE_TEST = "INTERFERENCE_TEST"
    WAITING = "WAITING"
    RECORDING = "RECORDING"
    PROCESSING = "PROCESSING"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class BallData(BaseModel):
    """Ball flight measurements from the R10 Doppler radar.

    All optional — older firmware / certain lies may omit fields.
    """
    speed_mph:          Optional[float] = Field(None, description="Ball speed in mph")
    launch_angle_deg:   Optional[float] = Field(None, description="Vertical launch angle, degrees")
    launch_direction_deg: Optional[float] = Field(None, description="Horizontal launch angle vs target line")
    total_spin_rpm:     Optional[float] = Field(None, description="Total spin in RPM")
    back_spin_rpm:      Optional[float] = Field(None)
    side_spin_rpm:      Optional[float] = Field(None, description="Positive = right curving spin")
    spin_axis_deg:      Optional[float] = Field(None, description="Spin axis tilt; + = slice axis")


class ClubData(BaseModel):
    """Club-side measurements derived from ball flight."""
    head_speed_mph:     Optional[float] = Field(None)
    club_path_deg:      Optional[float] = Field(None, description="+ = in-to-out")
    face_angle_deg:     Optional[float] = Field(None, description="+ = open at impact")
    attack_angle_deg:   Optional[float] = Field(None, description="+ = up, - = down")


class ShotResult(BaseModel):
    """Computed flight outcome."""
    apex_height_yd:     Optional[float] = Field(None)
    carry_distance_yd:  Optional[float] = Field(None)
    total_distance_yd:  Optional[float] = Field(None)
    deviation_angle_deg: Optional[float] = Field(None)
    deviation_distance_yd: Optional[float] = Field(None, description="Lateral offline at landing")
    hang_time_sec:      Optional[float] = Field(None)
    smash_factor:       Optional[float] = Field(None, description="ball_speed / club_head_speed")


class Shot(BaseModel):
    """One canonical shot record. Persisted and broadcast."""
    model_config = ConfigDict(populate_by_name=True)

    shot_id:        str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    captured_at:    datetime = Field(default_factory=datetime.now)
    source:         ShotSource = ShotSource.BLE_DIRECT
    device_state:   DeviceState = DeviceState.UNKNOWN

    club:           Optional[str] = Field(None, description="Club hint, e.g. 'Driver', '7 Iron'")
    session_id:     Optional[str] = Field(None)

    ball:           BallData = Field(default_factory=BallData)
    swing:          ClubData = Field(default_factory=ClubData)
    result:         ShotResult = Field(default_factory=ShotResult)

    raw_hex:        Optional[str] = Field(None, description="Hex dump of raw frame; useful for protocol iteration")
    raw_json:       Optional[str] = Field(None, description="If source was JSON (E6 mode), the original payload")

    notes:          Optional[str] = Field(None)

    def headline(self) -> str:
        """One-line summary for log lines / WebSocket previews."""
        speed = self.swing.head_speed_mph or 0
        carry = self.result.carry_distance_yd or 0
        smash = self.result.smash_factor or 0
        return f"{speed:5.1f} mph → {carry:5.1f} yd  (smash {smash:4.2f})"


class DeviceInfo(BaseModel):
    """Static device metadata captured once at connect time."""
    name:           str
    serial:         Optional[str] = None
    firmware:       Optional[str] = None
    model:          Optional[str] = None
    battery_pct:    Optional[int] = None
    captured_at:    datetime = Field(default_factory=datetime.now)


class CaptureFrame(BaseModel):
    """Raw frame log entry — written every notification regardless of parse success."""
    ts:             datetime = Field(default_factory=datetime.now)
    source:         ShotSource
    char_uuid:      Optional[str] = None
    raw_hex:        str
    decoded_hex:    Optional[str] = Field(None, description="After COBS-decode + frame-strip")
    parse_status:   str = "unparsed"
    parse_error:    Optional[str] = None
    shot_id:        Optional[str] = None
