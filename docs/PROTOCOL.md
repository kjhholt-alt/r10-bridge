# Garmin Approach R10 — Protocol Reference

What we know about the R10's wire formats, compiled from public reverse-engineering work plus our own captures. **Pull requests welcome.**

## Connection modes

The R10 supports two distinct PC-facing modes that are useful to us:

| Mode | Transport | Pairing required | Status |
|------|-----------|-------------------|--------|
| **BLE direct** | Bluetooth Low Energy from R10 to PC | Yes (Windows pair) | Partially documented |
| **E6 Connect** | Garmin Golf app → TCP/JSON → emulated E6 server | No (over WiFi) | Better documented |

The Garmin Golf app itself ALSO uses BLE (mode 1) to talk to the R10, then forwards data over TCP to a simulator (mode 2). Both modes are usable from a custom bridge.

## BLE — Services and Characteristics

### Standard Bluetooth SIG services

| Service | UUID |
|---------|------|
| Battery Service | `0000180f-0000-1000-8000-00805f9b34fb` |
| Device Information | `0000180a-0000-1000-8000-00805f9b34fb` |

Battery characteristics:
- `00002a19-...` — Battery Level (read + notify, 0-100)

Device Info characteristics:
- `00002a28-...` — Firmware Revision String
- `00002a24-...` — Model Number String
- `00002a25-...` — Serial Number String

### Garmin proprietary — Device Interface

| UUID | Role | Properties |
|------|------|------------|
| `6a4e2800-667b-11e3-949a-0800200c9a66` | Service | — |
| `6a4e2812-667b-11e3-949a-0800200c9a66` | Notifier | notify |
| `6a4e2822-667b-11e3-949a-0800200c9a66` | Writer | write |

This is the channel where authentication, ping/pong, and generic device commands flow as protobuf-encoded frames.

### Garmin proprietary — Measurement Service (R10-specific)

| UUID | Role | Properties |
|------|------|------------|
| `6a4e3400-667b-11e3-949a-0800200c9a66` | Service | — |
| `6a4e3401-667b-11e3-949a-0800200c9a66` | Measurement | notify |
| `6a4e3402-667b-11e3-949a-0800200c9a66` | Control Point | write |
| `6a4e3403-667b-11e3-949a-0800200c9a66` | Status | notify |

**Shot data flows through the Measurement characteristic** as a notification. The Control Point is used to arm/disarm the radar and configure shot detection. Status notifies state transitions (waiting → recording → processing → standby).

## BLE frame format

Each notification payload is wrapped in three layers:

```
┌─ COBS encoding (Consistent Overhead Byte Stuffing) ─────────┐
│  ┌─ 4-byte LE length ──┐  ┌─ payload ──┐  ┌─ 4-byte CRC32 ─┐│
│  │                     │  │            │  │                ││
│  └─────────────────────┘  └────────────┘  └────────────────┘│
└──────────────────────────────────────────────────────────────┘
```

1. Strip terminator(s) and COBS-decode (`cobs.decode` in this repo)
2. Read 4-byte little-endian length prefix
3. Read `length` bytes of payload
4. Read 4-byte little-endian CRC32; verify matches `zlib.crc32(payload)`
5. Decode payload as protobuf using `LaunchMonitor.proto`

## Protobuf — `LaunchMonitor.proto` (summary)

Source: `mholow/gsp-r10-adapter/src/bluetooth/proto/LaunchMonitor.proto`

```proto
message WrapperProto {
  optional EventSharing          event = 30;
  optional LaunchMonitorService  svc   = 38;
}
```

### EventSharing (tag 30)
Subscription/alert channel. Notifies on:
- `ACTIVITY_START` / `ACTIVITY_STOP`
- `LAUNCH_MONITOR` state transitions

### LaunchMonitorService (tag 38)
Request/response service with paired messages:

| Operation | Purpose |
|-----------|---------|
| StatusRequest / StatusResponse | Query current device state |
| WakeUpRequest / WakeUpResponse | Wake from standby |
| TiltRequest / TiltResponse | Read accelerometer tilt |
| StartTiltCalibrationRequest / Response | Begin tilt cal |
| ResetTiltCalibrationRequest / Response | Clear tilt cal |
| ShotConfigRequest / ShotConfigResponse | Configure shot detection thresholds |

### Data messages

`State` enum: STANDBY, INTERFERENCE_TEST, WAITING, RECORDING, PROCESSING, ERROR

`Metrics` message — the shot data we want. Contains nested ball, club, and swing measurements. (Exact field tags pending an updated capture sample with a clean shot.)

`Error` — severity WARNING / SERIOUS / FATAL

## E6 Connect — TCP/JSON message types

From `mholow/gsp-r10-adapter/src/api/R10Api.cs`:

| Message | Direction | Purpose |
|---------|-----------|---------|
| Handshake | app → server | Initiate session |
| Challenge | server → app | Auth challenge |
| Authentication | app → server | Auth response |
| SimCommand | server → app | Run a sim action (e.g., set lie) |
| Ping / Pong | bidirectional | Keepalive |
| SetBallData | app → server | Per-shot ball data |
| SetClubData | app → server | Per-shot club data |
| SendShot | app → server | Combined shot data |
| ShotComplete | app → server | Final shot result |
| Arm / Disarm | server → app | Toggle shot recording |
| Disconnect | bidirectional | Tear down |

### Example JSON shapes

The exact field naming varies; this bridge accepts multiple variants. Observed:

```json
{
  "Type": "ShotComplete",
  "BallData": {
    "BallSpeed": 145.2,
    "LaunchAngle": 12.5,
    "LaunchDirection": -1.2,
    "TotalSpin": 2800,
    "BackSpin": 2600,
    "SideSpin": 400,
    "SpinAxis": 8.5
  },
  "ClubData": {
    "ClubHeadSpeed": 98.6,
    "ClubPath": -0.8,
    "FaceAngle": 0.5,
    "AttackAngle": -1.5
  },
  "ShotDetails": {
    "Carry": 232.5,
    "Total": 248.0,
    "ApexHeight": 28.0,
    "DeviationAngle": 2.1,
    "DeviationDistance": 8.5
  }
}
```

## CSV — Garmin Golf app export

The Garmin Golf app exports per-shot CSVs via Share Session. Column names observed:

```
Club Type, Club Head Speed, Ball Speed, Smash Factor, Launch Angle,
Launch Direction, Spin Rate, Back Spin, Side Spin, Spin Axis,
Club Path, Face Angle, Attack Angle, Apex Height,
Carry Distance, Total Distance, Deviation Angle, Deviation Distance
```

`cli.py` `ingest` command parses these with multiple column-name variants for robustness across app versions.

## Open questions / TODO

- Exact field-tag mapping inside the `Metrics` protobuf message (currently inferred from order)
- Putting-mode protocol (separate measurement path?)
- Shot type enum (full swing vs chip vs putt)
- Multi-target mode messaging
- Bluetooth pairing-key exchange (if any)

## Citations

- [mholow/gsp-r10-adapter](https://github.com/mholow/gsp-r10-adapter) — primary C# reference
- [travislang/gspro-garmin-connect-v2](https://github.com/travislang/gspro-garmin-connect-v2) — JS/Electron approach, E6 server
- [thraizz/r10progress](https://github.com/thraizz/r10progress) — CSV-based analysis tool
- Garmin community forum threads on R10 GATT discovery (multiple, unindexed)
