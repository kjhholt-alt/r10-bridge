# Partners

Two of us. Both own a Garmin R10. Both vibe-code with Claude (Max-sub).

## Who does what

There are no assigned areas. We both touch everything. Whoever sees
the bug fixes the bug.

The one thing we both bring to this project that nobody else has: two
real R10 units on different firmware revisions. **The single highest-
leverage thing either of us can do is capture sessions** — see
[CONTRIBUTING.md](../CONTRIBUTING.md).

## How we work

- Push to `main` for small stuff. Read the room.
- PR for protocol-decoder changes, schema migrations, new transports.
- Tests stay green. Don't push red.
- Never force-push `main`.

## How to ask for help

- DM. Don't open an issue to ask a question.
- If you've been stuck > 30 min, share the symptom — usually the
  other person knows the trick.
- For protocol mysteries: post the raw bytes + your hypothesis.

## What we're NOT doing

This is the data layer, not the coaching layer. Resist the urge to
add miss-pattern logic, drill recommendations, or any product opinion
here. That belongs in `break-100-os`.

If a feature ends up only useful via a higher-level app, build it there.
`r10-bridge` stays a clean "R10 in, structured events out" pipe.
