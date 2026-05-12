"""Live WebSocket subscriber — prints every shot as it lands.

Run while `r10-bridge listen` is going. Each shot prints headline +
selected metrics. Modify to push into your own training app.
"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets


URL = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8787/ws"


async def main() -> None:
    print(f"connecting to {URL} ... (Ctrl-C to quit)")
    async with websockets.connect(URL) as ws:
        print("connected — waiting for shots")
        async for raw in ws:
            try:
                shot = json.loads(raw)
            except json.JSONDecodeError:
                print("[ws] non-json:", raw[:80])
                continue
            head = shot.get("head_speed_mph") or 0
            ball = shot.get("ball_speed_mph") or 0
            carry = shot.get("carry_distance_yd") or 0
            smash = shot.get("smash_factor") or 0
            launch = shot.get("launch_angle_deg") or 0
            spin = shot.get("total_spin_rpm") or 0
            club = shot.get("club") or "?"
            print(f"{shot.get('captured_at','')[:19]}  {club:8}  "
                  f"club {head:5.1f}  ball {ball:5.1f}  smash {smash:4.2f}  "
                  f"launch {launch:5.1f}°  spin {spin:5.0f}  → {carry:5.1f} yd")


if __name__ == "__main__":
    asyncio.run(main())
