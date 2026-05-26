# r10-bridge — Roadmap

> Open work, grouped by skill so either of us can pick up what looks fun
> on a given session. Not a Gantt chart. Items move freely.

## Now (v0.2 — protocol completion)

The big one. Get the remaining ~20% of unknown R10 fields decoded.

- [ ] **Capture more sessions.** Goal: 50 raw `.bin` files across 2 units,
      3 firmware revisions, all 14 club types. Currently ~5.
- [ ] **Spin axis sign** — we know magnitude, sign flips between captures
      for the same club. Either firmware quirk or our parse is wrong.
- [ ] **Strike location offset** — toe/heel is decoded, vertical
      (high/low face) isn't.
- [ ] **Club path vs face angle delta** — we get both individually,
      the relationship is what golfers actually care about.
- [ ] **Pre-shot/post-shot states** — "ready to hit" vs "shot recorded"
      transitions visible in the byte stream but unmodeled.

## Next (v0.3 — make it boring/robust)

- [ ] **Reconnection** — currently the BLE link dies and the bridge
      exits. Add exponential backoff + auto-reconnect.
- [ ] **Health endpoint** — `GET /health` returns last-seen-shot-ts,
      connection state, queue depth. So apps consuming the WS feed
      can show a connection indicator.
- [ ] **Replay mode** — `r10-bridge --replay captures/<file>.bin`
      streams a recorded session through the WS at real-time pace,
      for downstream-app dev without a live R10.
- [ ] **macOS BLE** — test the BLE path on macOS. Likely works (bleak
      is cross-platform) but unproven.
- [ ] **Docker image** — `docker run -p 7878:7878 r10-bridge`,
      mounts a captures volume.

## Later (v0.4+ — distribution + integrations)

- [ ] **PyPI release** once protocol is stable enough that breaking
      changes are rare.
- [ ] **TypeScript / Node WS consumer SDK** so `break-100-os` (and
      anyone else building on the bridge) can `npm install r10-bridge-js`
      and get typed events.
- [ ] **OBS overlay** — drop-in browser source URL that renders the
      last shot as a stream graphic (club / ball speed / smash).
- [ ] **OpenAPI spec** for the HTTP/WS surface so 3rd-party apps can
      generate clients.

## Backlog (whoever wants it)

- [ ] Bluetooth pairing diagnostics CLI — `r10-bridge diagnose` walks
      you through pairing if it failed.
- [ ] Garmin Connect CSV importer — pull existing range history into
      the same SQLite for back-testing.
- [ ] Web UI for browsing captured sessions (separate from break-100-os
      which is the higher-level coaching app).
- [ ] Mock R10 server — synthesizes shot byte streams so CI can
      integration-test the whole pipeline without hardware.

---

## How to pick something

1. Look at "Now" first — protocol completion is the v0.2 critical path.
2. If "Now" feels hard for the session you have, take anything from
   "Next" or "Backlog". No priority hierarchy below v0.2 — just pick
   what's fun.
3. Drop a 👀 reaction on the line or DM "taking X" so we don't dupe.
4. New idea not on this list? Add it under Backlog and start.
