"""SQLite persistence for shots + raw capture frames.

Schema is intentionally generous: every wire byte is stored as hex, so even
unparsed frames can be revisited later when the protocol decoder improves.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Iterator, Optional

from .models import CaptureFrame, Shot


SCHEMA = """
CREATE TABLE IF NOT EXISTS shots (
    shot_id              TEXT PRIMARY KEY,
    captured_at          TEXT NOT NULL,
    source               TEXT NOT NULL,
    device_state         TEXT,
    club                 TEXT,
    session_id           TEXT,
    -- ball
    ball_speed_mph       REAL,
    launch_angle_deg     REAL,
    launch_direction_deg REAL,
    total_spin_rpm       REAL,
    back_spin_rpm        REAL,
    side_spin_rpm        REAL,
    spin_axis_deg        REAL,
    -- club
    head_speed_mph       REAL,
    club_path_deg        REAL,
    face_angle_deg       REAL,
    attack_angle_deg     REAL,
    -- result
    apex_height_yd       REAL,
    carry_distance_yd    REAL,
    total_distance_yd    REAL,
    deviation_angle_deg  REAL,
    deviation_distance_yd REAL,
    hang_time_sec        REAL,
    smash_factor         REAL,
    -- raw
    raw_hex              TEXT,
    raw_json             TEXT,
    notes                TEXT
);

CREATE INDEX IF NOT EXISTS idx_shots_captured_at ON shots (captured_at);
CREATE INDEX IF NOT EXISTS idx_shots_session     ON shots (session_id);
CREATE INDEX IF NOT EXISTS idx_shots_club        ON shots (club);

CREATE TABLE IF NOT EXISTS frames (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    source       TEXT NOT NULL,
    char_uuid    TEXT,
    raw_hex      TEXT NOT NULL,
    decoded_hex  TEXT,
    parse_status TEXT,
    parse_error  TEXT,
    shot_id      TEXT
);

CREATE INDEX IF NOT EXISTS idx_frames_ts        ON frames (ts);
CREATE INDEX IF NOT EXISTS idx_frames_status    ON frames (parse_status);
CREATE INDEX IF NOT EXISTS idx_frames_shot      ON frames (shot_id);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    device_name  TEXT,
    firmware     TEXT,
    serial       TEXT,
    notes        TEXT
);
"""


class ShotStore:
    """Thin SQLite wrapper. Open per-process; safe for single-writer usage."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def _cur(self) -> Iterator[sqlite3.Cursor]:
        c = self._conn.cursor()
        try:
            yield c
        finally:
            c.close()

    # --- writes -------------------------------------------------------------

    def save_shot(self, shot: Shot) -> None:
        with self._cur() as c:
            c.execute(
                """INSERT OR REPLACE INTO shots VALUES (
                    :shot_id, :captured_at, :source, :device_state, :club, :session_id,
                    :ball_speed_mph, :launch_angle_deg, :launch_direction_deg,
                    :total_spin_rpm, :back_spin_rpm, :side_spin_rpm, :spin_axis_deg,
                    :head_speed_mph, :club_path_deg, :face_angle_deg, :attack_angle_deg,
                    :apex_height_yd, :carry_distance_yd, :total_distance_yd,
                    :deviation_angle_deg, :deviation_distance_yd, :hang_time_sec, :smash_factor,
                    :raw_hex, :raw_json, :notes
                )""",
                {
                    "shot_id":              shot.shot_id,
                    "captured_at":          shot.captured_at.isoformat(),
                    "source":               shot.source.value,
                    "device_state":         shot.device_state.value,
                    "club":                 shot.club,
                    "session_id":           shot.session_id,
                    "ball_speed_mph":       shot.ball.speed_mph,
                    "launch_angle_deg":     shot.ball.launch_angle_deg,
                    "launch_direction_deg": shot.ball.launch_direction_deg,
                    "total_spin_rpm":       shot.ball.total_spin_rpm,
                    "back_spin_rpm":        shot.ball.back_spin_rpm,
                    "side_spin_rpm":        shot.ball.side_spin_rpm,
                    "spin_axis_deg":        shot.ball.spin_axis_deg,
                    "head_speed_mph":       shot.swing.head_speed_mph,
                    "club_path_deg":        shot.swing.club_path_deg,
                    "face_angle_deg":       shot.swing.face_angle_deg,
                    "attack_angle_deg":     shot.swing.attack_angle_deg,
                    "apex_height_yd":       shot.result.apex_height_yd,
                    "carry_distance_yd":    shot.result.carry_distance_yd,
                    "total_distance_yd":    shot.result.total_distance_yd,
                    "deviation_angle_deg":  shot.result.deviation_angle_deg,
                    "deviation_distance_yd": shot.result.deviation_distance_yd,
                    "hang_time_sec":        shot.result.hang_time_sec,
                    "smash_factor":         shot.result.smash_factor,
                    "raw_hex":              shot.raw_hex,
                    "raw_json":             shot.raw_json,
                    "notes":                shot.notes,
                },
            )

    def save_frame(self, frame: CaptureFrame) -> None:
        with self._cur() as c:
            c.execute(
                """INSERT INTO frames
                   (ts, source, char_uuid, raw_hex, decoded_hex, parse_status, parse_error, shot_id)
                   VALUES (:ts, :source, :char_uuid, :raw_hex, :decoded_hex,
                           :parse_status, :parse_error, :shot_id)""",
                {
                    "ts":           frame.ts.isoformat(),
                    "source":       frame.source.value,
                    "char_uuid":    frame.char_uuid,
                    "raw_hex":      frame.raw_hex,
                    "decoded_hex":  frame.decoded_hex,
                    "parse_status": frame.parse_status,
                    "parse_error":  frame.parse_error,
                    "shot_id":      frame.shot_id,
                },
            )

    def open_session(self, session_id: str, device_name: str = "",
                     firmware: str = "", serial: str = "", notes: str = "") -> None:
        with self._cur() as c:
            c.execute(
                """INSERT OR REPLACE INTO sessions
                   (session_id, started_at, device_name, firmware, serial, notes)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, datetime.now().isoformat(),
                 device_name, firmware, serial, notes),
            )

    def close_session(self, session_id: str) -> None:
        with self._cur() as c:
            c.execute("UPDATE sessions SET ended_at = ? WHERE session_id = ?",
                      (datetime.now().isoformat(), session_id))

    # --- reads --------------------------------------------------------------

    def latest_shot(self) -> Optional[dict]:
        with self._cur() as c:
            c.execute("SELECT * FROM shots ORDER BY captured_at DESC LIMIT 1")
            row = c.fetchone()
            if not row:
                return None
            cols = [d[0] for d in c.description]
            return dict(zip(cols, row))

    def shots_since(self, since_iso: str, limit: int = 500) -> list[dict]:
        with self._cur() as c:
            c.execute(
                "SELECT * FROM shots WHERE captured_at >= ? ORDER BY captured_at DESC LIMIT ?",
                (since_iso, limit),
            )
            cols = [d[0] for d in c.description]
            return [dict(zip(cols, r)) for r in c.fetchall()]

    def count_shots(self) -> int:
        with self._cur() as c:
            c.execute("SELECT COUNT(*) FROM shots")
            return c.fetchone()[0]

    def prune_old_frames(self, keep_days: int) -> int:
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._cur() as c:
            c.execute("DELETE FROM frames WHERE ts < ?", (cutoff,))
            return c.rowcount


def write_capture_jsonl(path: Path, frame: CaptureFrame) -> None:
    """Append-only line-delimited JSON for human inspection. One frame per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts":           frame.ts.isoformat(),
            "source":       frame.source.value,
            "char_uuid":    frame.char_uuid,
            "raw_hex":      frame.raw_hex,
            "decoded_hex":  frame.decoded_hex,
            "parse_status": frame.parse_status,
            "parse_error":  frame.parse_error,
            "shot_id":      frame.shot_id,
        }) + "\n")
