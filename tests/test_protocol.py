"""Protocol parser tests — focused on the lenient paths.

We don't have real captured BLE bytes yet, so these tests verify the
parser is defensive: malformed input becomes a CaptureFrame with a
parse_status set, never a crash.
"""
from r10_bridge.protocol import parse_ble_notification, parse_e6_message


def test_ble_garbage_input_doesnt_crash():
    shot, frame = parse_ble_notification(b"\x01\x02\x03\x04", char_uuid="test")
    assert shot is None
    assert frame.parse_status != "proto_decoded"
    assert frame.raw_hex == "01020304"


def test_ble_empty_input():
    shot, frame = parse_ble_notification(b"", char_uuid="test")
    assert shot is None
    assert frame.raw_hex == ""


def test_e6_handshake_response():
    shot, frame, response = parse_e6_message(b'{"Type":"Handshake"}')
    assert response is not None
    assert response["Status"] == "Accepted"
    assert shot is None
    assert frame.parse_status.startswith("json:")


def test_e6_ping_pong():
    shot, frame, response = parse_e6_message(b'{"Type":"Ping"}')
    assert response is not None
    assert response["Type"] == "Pong"


def test_e6_shot_message():
    payload = b'''{
        "Type": "ShotComplete",
        "BallData": {"BallSpeed": 145.2, "LaunchAngle": 12.5, "TotalSpin": 2800,
                     "BackSpin": 2600, "SideSpin": 400, "SpinAxis": 8.5,
                     "LaunchDirection": -1.2},
        "ClubData": {"ClubHeadSpeed": 98.6, "ClubPath": -0.8, "FaceAngle": 0.5,
                     "AttackAngle": -1.5},
        "ShotDetails": {"Carry": 232.5, "Total": 248.0, "ApexHeight": 28.0,
                        "DeviationAngle": 2.1, "DeviationDistance": 8.5}
    }'''
    shot, frame, response = parse_e6_message(payload)
    assert shot is not None
    assert shot.ball.speed_mph == 145.2
    assert shot.swing.head_speed_mph == 98.6
    assert shot.result.carry_distance_yd == 232.5
    assert shot.result.smash_factor == round(145.2 / 98.6, 3)
    assert response is not None
    assert response["Type"] == "ShotAcknowledged"


def test_e6_malformed_json():
    shot, frame, response = parse_e6_message(b"{not json")
    assert shot is None
    assert frame.parse_status == "json_decode_failed"
