"""BLE UUIDs, message types, and protocol constants for the Garmin R10.

Sources:
  - mholow/gsp-r10-adapter (C# reference implementation)
  - Garmin community forum threads on R10 GATT discovery
  - Local capture sessions logged into captures/*.jsonl

DO NOT GUESS at UUIDs. If you find a new one, add it here with a citation.
"""

# ---------------------------------------------------------------------------
# Standard SIG services (Bluetooth-defined, identical across devices)
# ---------------------------------------------------------------------------

BATTERY_SERVICE_UUID            = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHAR_UUID         = "00002a19-0000-1000-8000-00805f9b34fb"

DEVICE_INFO_SERVICE_UUID        = "0000180a-0000-1000-8000-00805f9b34fb"
FIRMWARE_REV_CHAR_UUID          = "00002a28-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_CHAR_UUID          = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID         = "00002a25-0000-1000-8000-00805f9b34fb"

# ---------------------------------------------------------------------------
# Garmin proprietary services (the interesting bits)
# ---------------------------------------------------------------------------

# Generic device interface — protobuf messages flow through this one (auth, ping, sim commands)
DEVICE_INTERFACE_SERVICE_UUID   = "6a4e2800-667b-11e3-949a-0800200c9a66"
DEVICE_INTERFACE_NOTIFIER_UUID  = "6a4e2812-667b-11e3-949a-0800200c9a66"   # notify
DEVICE_INTERFACE_WRITER_UUID    = "6a4e2822-667b-11e3-949a-0800200c9a66"   # write

# R10-specific measurement service — shot data lives here
MEASUREMENT_SERVICE_UUID        = "6a4e3400-667b-11e3-949a-0800200c9a66"
MEASUREMENT_CHAR_UUID           = "6a4e3401-667b-11e3-949a-0800200c9a66"   # notify
CONTROL_POINT_CHAR_UUID         = "6a4e3402-667b-11e3-949a-0800200c9a66"   # write
STATUS_CHAR_UUID                = "6a4e3403-667b-11e3-949a-0800200c9a66"   # notify

CHARACTERISTICS_TO_SUBSCRIBE = [
    DEVICE_INTERFACE_NOTIFIER_UUID,
    MEASUREMENT_CHAR_UUID,
    STATUS_CHAR_UUID,
    BATTERY_LEVEL_CHAR_UUID,
]

# ---------------------------------------------------------------------------
# Device discovery
# ---------------------------------------------------------------------------

DEFAULT_DEVICE_NAME_MATCH = "Approach R10"

# ---------------------------------------------------------------------------
# E6 Connect message types (TCP JSON path)
# Source: mholow/gsp-r10-adapter src/api/R10Api.cs message enum
# ---------------------------------------------------------------------------

class E6MessageType:
    HANDSHAKE       = "Handshake"
    CHALLENGE       = "Challenge"
    AUTHENTICATION  = "Authentication"
    SIM_COMMAND     = "SimCommand"
    PING            = "Ping"
    PONG            = "Pong"
    SET_BALL_DATA   = "SetBallData"
    SET_CLUB_DATA   = "SetClubData"
    SEND_SHOT       = "SendShot"
    SHOT_COMPLETE   = "ShotComplete"
    ARM             = "Arm"
    DISARM          = "Disarm"
    DISCONNECT      = "Disconnect"

# ---------------------------------------------------------------------------
# Protobuf wire format notes
# ---------------------------------------------------------------------------

# BLE notification payload framing (from mholow's BaseDevice.cs):
#   1. COBS-encoded outer frame (Consistent Overhead Byte Stuffing)
#   2. Inside: 4-byte little-endian length, then payload, then 4-byte CRC32
#   3. Payload: protobuf root message `WrapperProto` with fields:
#        - EventSharing event = 30
#        - LaunchMonitorService svc = 38
COBS_TERMINATOR = b"\x00"
LENGTH_PREFIX_BYTES = 4
CRC_SUFFIX_BYTES = 4

# Protobuf root field tags (from LaunchMonitor.proto)
PROTO_TAG_EVENT_SHARING = 30
PROTO_TAG_LM_SERVICE    = 38

# Device State enum (from .proto)
DEVICE_STATES = [
    "STANDBY", "INTERFERENCE_TEST", "WAITING",
    "RECORDING", "PROCESSING", "ERROR",
]
