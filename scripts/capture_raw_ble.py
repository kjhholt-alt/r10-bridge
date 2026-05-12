"""Standalone raw BLE capture script — for protocol research.

Connects to the R10, subscribes to every notify-capable characteristic,
and appends raw bytes to captures/raw_<timestamp>.jsonl. No parsing,
no SQLite. Pure data acquisition for offline reverse engineering.

Use this when:
  - You want a clean sample of BLE traffic without bridge overhead
  - You're testing a new firmware version and want to compare
  - You're contributing protocol findings back to the project
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Make src/ importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r10_bridge import constants


async def main() -> None:
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("Install bleak first: pip install bleak", file=sys.stderr)
        sys.exit(1)

    out = Path("captures") / f"raw_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"raw capture → {out}")

    print(f"scanning for '{constants.DEFAULT_DEVICE_NAME_MATCH}' ...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, _ad: d.name and constants.DEFAULT_DEVICE_NAME_MATCH.lower() in d.name.lower(),
        timeout=30.0,
    )
    if device is None:
        print("no R10 found", file=sys.stderr)
        sys.exit(2)

    print(f"connecting to {device.name} @ {device.address}")
    async with BleakClient(device) as client:
        services = client.services
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "event": "connected",
                "ts": datetime.now().isoformat(),
                "device_name": device.name,
                "device_address": device.address,
                "services": [
                    {
                        "uuid": str(svc.uuid),
                        "chars": [
                            {"uuid": str(c.uuid), "properties": list(c.properties)}
                            for c in svc.characteristics
                        ],
                    }
                    for svc in services
                ],
            }) + "\n")

        def make_handler(uuid: str):
            def _h(_sender, data: bytearray) -> None:
                with out.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "event": "notify",
                        "ts": datetime.now().isoformat(),
                        "char": uuid,
                        "hex": bytes(data).hex(),
                        "len": len(data),
                    }) + "\n")
                print(f"  {uuid[:8]}  {len(data):3d}B  {bytes(data).hex()[:64]}")
            return _h

        for char_uuid in constants.CHARACTERISTICS_TO_SUBSCRIBE:
            try:
                await client.start_notify(char_uuid, make_handler(char_uuid))
                print(f"subscribed: {char_uuid}")
            except Exception as e:
                print(f"  (skip {char_uuid}: {e})")

        print("\n>>> Hit shots now. Ctrl-C to stop. <<<\n")
        try:
            while client.is_connected:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    asyncio.run(main())
