"""Pydantic model round-trip tests."""
from r10_bridge.models import BallData, ClubData, Shot, ShotResult, ShotSource


def test_shot_defaults():
    shot = Shot()
    assert shot.shot_id
    assert shot.source == ShotSource.BLE_DIRECT
    assert shot.ball.speed_mph is None
    assert shot.swing.head_speed_mph is None
    assert shot.result.carry_distance_yd is None


def test_shot_roundtrip():
    shot = Shot(
        ball=BallData(speed_mph=145.0, launch_angle_deg=12.5, total_spin_rpm=2800),
        swing=ClubData(head_speed_mph=98.6, club_path_deg=-1.2, face_angle_deg=0.4),
        result=ShotResult(carry_distance_yd=232.0, smash_factor=1.47),
        club="Driver",
    )
    dumped = shot.model_dump(mode="json")
    again = Shot.model_validate(dumped)
    assert again.ball.speed_mph == 145.0
    assert again.swing.head_speed_mph == 98.6
    assert again.result.carry_distance_yd == 232.0
    assert again.club == "Driver"
    assert "232" in shot.headline()


def test_headline_safe_with_missing_data():
    # Shouldn't crash when fields are None
    shot = Shot()
    text = shot.headline()
    assert "mph" in text
    assert "yd" in text
