# r10-bridge

Live Bluetooth bridge for the **Garmin Approach R10** launch monitor. Pairs to your R10 (or intercepts the Garmin Golf app's TCP traffic), captures every shot, persists to SQLite, and broadcasts events over WebSocket so your own training apps can subscribe in real time.

> Status: **v0.1 — capture-first**. The bridge connects, logs raw bytes for protocol research, and decodes what we already know (~80% of the metrics R10 emits). The remaining 20% is parsed naively and refined as more capture files accumulate.

## Why this exists

The R10 produces excellent shot data — club speed, ball speed, smash, launch angles, spin axis, club path, attack angle — but Garmin's official mobile app keeps it locked behind their UI. Several community projects have shown the data CAN be intercepted; this is a Python implementation that you can host yourself, embed in your own training tools, and extend.

## Three ways to capture shots

| Mode | What happens | Setup difficulty |
|------|--------------|------------------|
| **BLE direct** | PC pairs with R10 over Bluetooth; bridge subscribes to the proprietary GATT measurement service | Medium (Windows BT pairing) |
| **E6 Connect intercept** | Bridge runs a TCP server emulating E6 Connect; Garmin Golf app forwards shots to it | Easy (works on phone) |
| **CSV ingest** | After a session, export from the Garmin Golf app and drop the CSV into `inbox/` | Trivial (no live data) |

Use any combination. Persistence and the WebSocket feed are the same regardless of source.

## Install

```bash
git clone https://github.com/kjhholt-alt/r10-bridge.git
cd r10-bridge
py -m pip install --user -e .
```

Requires Python 3.10+. Tested on Windows 11. Mac/Linux should work for BLE+TCP but Windows is the proven platform.

## Quick start

### BLE direct mode

```bash
# 1. Put your R10 in pairing mode (hold power until LED blinks blue)
# 2. Pair from Windows Bluetooth settings (one-time)
# 3. Run the bridge
r10-bridge listen --mode ble
```

Output:
```
[r10-bridge] scanning for "Approach R10"...
[r10-bridge] connected to R10 — serial GVZRxxxxxx, fw 7.20
[r10-bridge] subscribed to Measurement + Status characteristics
[r10-bridge] capture log: captures/ble_20260512_153012.jsonl
[r10-bridge] HTTP+WS server: http://localhost:8787
```

Every notification gets:
- raw bytes appended to `captures/<timestamp>.jsonl`
- parsed (where possible) and stored in `data/shots.db`
- broadcast to every WebSocket subscriber

### E6 Connect mode

```bash
r10-bridge listen --mode e6
```

Output:
```
[r10-bridge] E6 server listening on 192.168.1.42:6868
[r10-bridge] open Garmin Golf app → Play E6 Connect → set host to 192.168.1.42:6868
[r10-bridge] HTTP+WS server: http://localhost:8787
```

In the Garmin Golf app, choose **Golf Sim → TruGolf E6 Connect → Play on PC**, then enter the IP/port the bridge printed. Hit a shot; you'll see it in `data/shots.db` and on the WebSocket feed.

### Consume the feed

```python
# examples/ws_client.py
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://localhost:8787/ws") as ws:
        async for msg in ws:
            shot = json.loads(msg)
            print(f"{shot['club_head_speed']:.1f} mph → "
                  f"{shot['carry_distance']:.0f} yd "
                  f"({shot['smash_factor']:.2f} smash)")

asyncio.run(main())
```

Or poll the HTTP endpoint:
```
GET http://localhost:8787/shots/latest
GET http://localhost:8787/shots?since=2026-05-12T00:00:00
```

## The protocol — what we know

See [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for the full reference. Quick version:

### BLE services
- **Measurement** `6A4E3400-667B-11E3-949A-0800200C9A66` — R10-specific shot data
  - Measurement char `6A4E3401-...`
  - Control point `6A4E3402-...`
  - Status `6A4E3403-...`
- **Device Interface** `6A4E2800-...` — protobuf message channel
  - Notifier `6A4E2812-...` (notify)
  - Writer `6A4E2822-...` (write)
- **Battery** + **Device Info** — standard SIG services for battery %, firmware, serial

### Wire format
1. BLE notification payload is a **COBS-encoded** frame
2. Inside the frame: 4-byte length + payload + 4-byte CRC32
3. Payload is **Protocol Buffers** (proto3)
4. Root message is `WrapperProto { EventSharing event = 30; LaunchMonitorService svc = 38; }`

### Shot data fields (the prize)
- **Ball:** speed, launch_angle (vertical), launch_direction (horizontal), total_spin, back_spin, side_spin, spin_axis
- **Club:** head_speed, swing_path, face_angle
- **Result:** apex_height, carry_distance, total_distance, deviation_angle, deviation_distance, ball_location, smash_factor (computed)

## Roadmap

- [x] BLE pairing + characteristic discovery
- [x] COBS decoder, length+CRC stripper
- [x] Pydantic models for every documented field
- [x] SQLite persistence with raw + parsed columns
- [x] FastAPI HTTP + WebSocket bridge
- [x] CLI (`r10-bridge listen`, `serve`, `ingest`, `analyze`)
- [x] Raw capture mode for protocol iteration
- [ ] Full protobuf decode from `.proto` schema (need community schema)
- [ ] E6 Connect TCP/JSON parser (stub in place)
- [ ] CSV ingest from Garmin Golf app exports
- [ ] Putting webcam companion (out of scope for v1)
- [ ] Dispersion + strike-quality analytics module
- [ ] Discord / Slack webhook emitter

## Credits

Reverse engineering: [mholow/gsp-r10-adapter](https://github.com/mholow/gsp-r10-adapter), [travislang/gspro-garmin-connect-v2](https://github.com/travislang/gspro-garmin-connect-v2). Public Garmin forum discussion of GATT UUIDs.

This project is independent of and not endorsed by Garmin Ltd.

## License

MIT. See `LICENSE`.

## Caveats

- The R10's protocol is undocumented. Garmin can break it with any firmware update. **Pin your R10 firmware once a session works** (record the version printed at connect time).
- BLE direct mode requires the R10 to be unpaired from your phone first. Re-pairing later restores the phone connection.
- E6 Connect mode requires the Garmin Golf app to be in active simulator mode.
