# Contributing — r10-bridge

> Two-person project, vibe-coded. We don't run tickets. We run "I noticed
> X, fixing it" → push to `main`.

## Setup

```bash
git clone https://github.com/kjhholt-alt/r10-bridge.git
cd r10-bridge
py -m pip install --user -e .
py -m pip install --user pytest pytest-cov
pytest -q   # should be all green
```

Python 3.10+. Windows 11 is the primary target (where BLE pairing has
been proven); macOS/Linux should work for BLE + E6 TCP.

## What needs a real R10 vs. what doesn't

| Layer | Needs R10? | How to develop without one |
|---|---|---|
| Protocol parsing | No | `captures/` has raw byte logs we replay through `protocol.py` |
| Persistence | No | SQLite, tests cover everything |
| WebSocket broadcast | No | `examples/ws_consumer.py` reads the feed |
| BLE direct pairing | **Yes** | Mock isn't worth it — pair against your unit |
| E6 Connect intercept | **Yes** | Garmin Golf app on phone has to forward to our TCP server |
| CSV ingest | No | Drop a sample CSV in `inbox/` |

If you can do everything without your R10, then your R10 isn't pulling
its weight — go capture a session and add the raw bytes to `captures/`.

## Capture a session

The single highest-leverage thing a second R10 owner can do:

1. Run `python -m r10_bridge.capture --out captures/$(date +%Y%m%d_%H%M)_<your_initials>.bin`
2. Pair your R10, hit 10-20 shots of varied clubs (driver / 7i / wedge / putter)
3. Commit the raw `.bin` + a one-line `captures/README.md` entry: club + ball + notes
4. Run `pytest tests/test_protocol.py -v` — your capture is now a fixture

Every new capture refines the remaining ~20% of unknown fields. Two
people with two R10s on different firmware revisions = the protocol gets
to 95% faster than either of us alone.

## Workflow

- **Push to `main` for anything under ~100 lines.** Vibe coding, small
  scope, can't break anything irrecoverable. Push and move.
- **Open a PR for anything bigger.** New decoder for a metric, schema
  migration, packaging changes, new transport mode.
- **Never force-push `main`.** That's the only hard rule.
- **Tests stay green.** If a test breaks, fix the test or fix the code
  before pushing — don't push with red CI.
- **Commit messages**: short imperative line. Examples in `git log`.

## Where things live

```
src/r10_bridge/
  __init__.py
  capture.py        # raw byte logger + replay harness
  protocol.py       # decoder (the 80/20 layer)
  persist.py        # SQLite writer
  ws.py             # WebSocket broadcaster
  cobs.py           # framing
tests/              # pytest, all green
docs/PROTOCOL.md    # what we know about the GATT service
captures/           # raw bytes per session — the corpus
```

## When in doubt

If you're not sure whether something should be a PR or a push, push it
and DM. We optimize for flow, not formality.

For protocol/decoder changes touching `protocol.py`: prefer PR — these
are the hardest to undo if wrong.
