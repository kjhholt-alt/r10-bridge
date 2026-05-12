"""FastAPI HTTP + WebSocket bridge.

Clients subscribe via WebSocket (`/ws`) to receive shots as they happen.
Polling clients can hit:
  GET  /healthz            → { "ok": true, "version": ..., "shots": N }
  GET  /shots/latest       → most recent shot or 404
  GET  /shots?since=ISO    → shots captured since the given timestamp
  GET  /device             → static device info (set when BLE/E6 connects)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect

from . import __version__
from .models import DeviceInfo, Shot
from .persist import ShotStore

log = logging.getLogger("r10_bridge.bridge")


class BridgeApp:
    """Glues the listener (BLE/E6) → SQLite store → FastAPI broadcasters."""

    def __init__(self, store: ShotStore):
        self.store = store
        self.subscribers: set[WebSocket] = set()
        self.device: Optional[DeviceInfo] = None
        self.api = self._build_api()

    def _build_api(self) -> FastAPI:
        api = FastAPI(title="r10-bridge", version=__version__)

        @api.get("/healthz")
        async def healthz():
            return {
                "ok": True,
                "version": __version__,
                "shots": self.store.count_shots(),
                "subscribers": len(self.subscribers),
                "device": self.device.model_dump(mode="json") if self.device else None,
            }

        @api.get("/shots/latest")
        async def latest():
            row = self.store.latest_shot()
            if row is None:
                raise HTTPException(404, "no shots captured yet")
            return row

        @api.get("/shots")
        async def shots(since: Optional[str] = None, limit: int = 500):
            if since is None:
                since = "1970-01-01T00:00:00"
            return {"shots": self.store.shots_since(since, limit=min(limit, 5000))}

        @api.get("/device")
        async def device():
            if self.device is None:
                raise HTTPException(404, "no device connected")
            return self.device.model_dump(mode="json")

        @api.websocket("/ws")
        async def ws(ws: WebSocket) -> None:
            await ws.accept()
            self.subscribers.add(ws)
            log.info("ws subscriber connected (total %d)", len(self.subscribers))
            try:
                # Send the latest shot on connect for immediate context
                latest = self.store.latest_shot()
                if latest is not None:
                    await ws.send_text(json.dumps(latest, default=str))
                # Idle loop — clients are pushed-to, not polled-from
                while True:
                    msg = await ws.receive_text()
                    if msg.lower() == "ping":
                        await ws.send_text(json.dumps({"type": "pong"}))
            except WebSocketDisconnect:
                pass
            finally:
                self.subscribers.discard(ws)
                log.info("ws subscriber disconnected (total %d)", len(self.subscribers))

        return api

    async def on_shot(self, shot: Shot) -> None:
        self.store.save_shot(shot)
        await self._broadcast(shot.model_dump(mode="json"))

    async def on_frame(self, frame) -> None:
        self.store.save_frame(frame)

    async def on_device(self, info: DeviceInfo) -> None:
        self.device = info

    async def _broadcast(self, payload: dict) -> None:
        if not self.subscribers:
            return
        msg = json.dumps(payload, default=str)
        dead = []
        for ws in list(self.subscribers):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.subscribers.discard(ws)


async def run_uvicorn(app, host: str, port: int, stop_event: asyncio.Event) -> None:
    """Run uvicorn inside our existing event loop so we can co-host the listener."""
    import uvicorn
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    stop_task = asyncio.create_task(stop_event.wait())
    await asyncio.wait({serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
    server.should_exit = True
    await serve_task
