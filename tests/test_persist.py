"""SQLite persistence round-trip."""
from datetime import datetime
from pathlib import Path

from r10_bridge.models import BallData, ClubData, Shot, ShotResult, CaptureFrame, ShotSource
from r10_bridge.persist import ShotStore


def test_save_and_fetch_shot(tmp_path: Path):
    store = ShotStore(tmp_path / "shots.db")
    shot = Shot(
        ball=BallData(speed_mph=130.0),
        swing=ClubData(head_speed_mph=88.0),
        result=ShotResult(carry_distance_yd=210.0, smash_factor=1.48),
        club="7 Iron",
    )
    store.save_shot(shot)
    latest = store.latest_shot()
    assert latest is not None
    assert latest["ball_speed_mph"] == 130.0
    assert latest["head_speed_mph"] == 88.0
    assert latest["club"] == "7 Iron"
    assert store.count_shots() == 1
    store.close()


def test_save_frame(tmp_path: Path):
    store = ShotStore(tmp_path / "shots.db")
    frame = CaptureFrame(source=ShotSource.BLE_DIRECT, raw_hex="deadbeef",
                         parse_status="cobs_decode_failed")
    store.save_frame(frame)
    # No assertion on shape — just confirm it didn't raise
    store.close()
