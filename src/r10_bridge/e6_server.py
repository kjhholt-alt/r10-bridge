"""E6 Connect-compatible TCP server.

The Garmin Golf app, when set to "Play E6 Connect → Play on PC", opens a TCP
connection to a host/port the user specifies. It then sends JSON messages
for handshake, ping, shot data, etc. This module emulates the server side.

Wire format observed in the wild:
  - Newline-delimited JSON ("application/x-ndjson" style) most commonly
  - Some implementations length-prefix; we try both

This is intentionally minimal — just enough to keep the Garmin app happy
and dispatch shots into our common pipeline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Optional

from .models import CaptureFrame, Shot
from .protocol import parse_e6_message

log = logging.getLogger("r10_bridge.e6")

ShotCallback = Callable[[Shot], Awaitable[None]]
FrameCallback = Callable[[CaptureFrame], Awaitable[None]]


async def serve(
    on_shot: ShotCallback,
    on_frame: FrameCallback,
    host: str = "0.0.0.0",
    port: int = 6868,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Start the E6 Connect TCP server and run until stop_event is set."""
    stop = stop_event or asyncio.Event()

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("E6 client connected: %s", peer)
        try:
            buf = b""
            while not stop.is_set():
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf += chunk

                # Try newline-delimited framing first
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    await _dispatch_one(line, writer, on_shot, on_frame)

                # If buffer still has bytes and no newline, try to decode it as a single message
                if buf and len(buf) > 4 and buf.startswith(b"{"):
                    # Best-effort JSON-object boundary detection
                    try:
                        json.loads(buf.decode("utf-8"))
                        await _dispatch_one(buf, writer, on_shot, on_frame)
                        buf = b""
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        pass
        except (ConnectionResetError, asyncio.IncompleteReadError):
            pass
        finally:
            log.info("E6 client disconnected: %s", peer)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(handle, host, port)
    addrs = ", ".join(str(s.getsockname()) for s in server.sockets)
    log.info("E6 Connect server listening on %s", addrs)

    async with server:
        wait_task = asyncio.create_task(stop.wait())
        serve_task = asyncio.create_task(server.serve_forever())
        done, pending = await asyncio.wait(
            {wait_task, serve_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()


async def _dispatch_one(
    raw: bytes,
    writer: asyncio.StreamWriter,
    on_shot: ShotCallback,
    on_frame: FrameCallback,
) -> None:
    shot, frame, response = parse_e6_message(raw)
    await on_frame(frame)
    if shot is not None:
        log.info("E6 shot: %s", shot.headline())
        await on_shot(shot)
    if response is not None:
        try:
            writer.write((json.dumps(response) + "\n").encode("utf-8"))
            await writer.drain()
        except Exception as e:
            log.warning("E6 response write failed: %s", e)


def new_session_id() -> str:
    return f"e6_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def local_advertise_address(port: int) -> str:
    """Best-guess LAN IP for the user to plug into the Garmin app."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    return f"{ip}:{port}"
