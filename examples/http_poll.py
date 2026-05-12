"""HTTP polling example for clients that can't use WebSockets."""
from __future__ import annotations

import json
import sys
import time
import urllib.request


BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"


def _get(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[http] error: {e}")
        return None


def main() -> None:
    print(f"polling {BASE}/shots/latest every 2s — Ctrl-C to quit")
    seen: set[str] = set()
    while True:
        shot = _get(f"{BASE}/shots/latest")
        if shot and shot.get("shot_id") and shot["shot_id"] not in seen:
            seen.add(shot["shot_id"])
            print(f"new: {shot.get('captured_at','')[:19]}  "
                  f"club {shot.get('head_speed_mph','—')}  "
                  f"carry {shot.get('carry_distance_yd','—')} yd")
        time.sleep(2)


if __name__ == "__main__":
    main()
