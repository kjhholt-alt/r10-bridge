"""Direct BLE listener for the Garmin R10.

Pairs/connects via `bleak`, reads device info, subscribes to the four
notify-capable characteristics, and dispatches every frame to the on_event
callback after running it through protocol.parse_ble_notification.

This module is **import-cheap** — `bleak` only imports when listen() runs,
so the rest of the CLI works on machines without BlueZ / WinRT permissions.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Awaitable, Callable, Optional

from . import constants
from .models import CaptureFrame, DeviceInfo, Shot
from .protocol import parse_ble_notification

log = logging.getLogger("r10_bridge.ble")

# Type aliases
ShotCallback = Callable[[Shot], Awaitable[None]]
FrameCallback = Callable[[CaptureFrame], Awaitable[None]]
DeviceCallback = Callable[[DeviceInfo], Awaitable[None]]


async def listen(
    on_shot: ShotCallback,
    on_frame: FrameCallback,
    on_device: Optional[DeviceCallback] = None,
    device_name_match: str = constants.DEFAULT_DEVICE_NAME_MATCH,
    scan_timeout_sec: float = 30.0,
    auto_reconnect: bool = True,
    stop_event: Optional[asyncio.Event] = None,
) -> None:
    """Scan for the R10, connect, and dispatch frames until stop_event is set.

    Reconnects on disconnect if auto_reconnect=True.
    """
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as e:
        raise RuntimeError(
            "bleak is not installed. `pip install bleak` to enable BLE mode."
        ) from e

    stop = stop_event or asyncio.Event()

    while not stop.is_set():
        log.info("scanning for '%s' (timeout %.0fs)...", device_name_match, scan_timeout_sec)
        device = await BleakScanner.find_device_by_filter(
            lambda d, _ad: d.name and device_name_match.lower() in d.name.lower(),
            timeout=scan_timeout_sec,
        )
        if device is None:
            log.warning("no R10 found in scan window")
            if not auto_reconnect:
                break
            await asyncio.sleep(2)
            continue

        log.info("found %s @ %s — connecting", device.name, device.address)
        try:
            async with BleakClient(device) as client:
                await _on_connected(client, on_shot, on_frame, on_device, stop)
        except Exception as e:
            log.exception("BLE session error: %s", e)
        if not auto_reconnect:
            break
        await asyncio.sleep(1.0)


async def _on_connected(
    client,
    on_shot: ShotCallback,
    on_frame: FrameCallback,
    on_device: Optional[DeviceCallback],
    stop: asyncio.Event,
) -> None:
    """Subscribe to all interesting characteristics; dispatch on notifications."""
    info = await _read_device_info(client)
    log.info("connected: %s", info.model_dump())
    if on_device:
        await on_device(info)

    async def handler(char_uuid: str, data: bytes) -> None:
        shot, frame = parse_ble_notification(bytes(data), char_uuid)
        await on_frame(frame)
        if shot is not None:
            log.info("shot: %s", shot.headline())
            await on_shot(shot)

    # Subscribe to all notify-capable characteristics we know about
    subscribed: list[str] = []
    for char_uuid in constants.CHARACTERISTICS_TO_SUBSCRIBE:
        try:
            await client.start_notify(
                char_uuid,
                lambda _sender, data, u=char_uuid: asyncio.create_task(handler(u, data)),
            )
            subscribed.append(char_uuid)
            log.info("subscribed to %s", char_uuid)
        except Exception as e:
            log.warning("could not subscribe to %s: %s", char_uuid, e)

    if not subscribed:
        raise RuntimeError("Failed to subscribe to any R10 characteristics")

    # Stay connected until stop_event is set or client disconnects
    while not stop.is_set() and client.is_connected:
        await asyncio.sleep(0.5)

    for char_uuid in subscribed:
        try:
            await client.stop_notify(char_uuid)
        except Exception:
            pass


async def _read_device_info(client) -> DeviceInfo:
    """Try to read all the static device-info characteristics. Best-effort."""
    async def _read(char_uuid: str) -> Optional[str]:
        try:
            data = await client.read_gatt_char(char_uuid)
            return data.decode("utf-8", errors="replace").strip("\x00").strip()
        except Exception:
            return None

    name = "Approach R10"
    try:
        # bleak >= 0.22 exposes client.device.name
        name = client.device.name or name
    except Exception:
        pass

    info = DeviceInfo(name=name)
    info.firmware = await _read(constants.FIRMWARE_REV_CHAR_UUID)
    info.model    = await _read(constants.MODEL_NUMBER_CHAR_UUID)
    info.serial   = await _read(constants.SERIAL_NUMBER_CHAR_UUID)

    try:
        bat = await client.read_gatt_char(constants.BATTERY_LEVEL_CHAR_UUID)
        info.battery_pct = bat[0] if bat else None
    except Exception:
        pass

    return info


def new_session_id() -> str:
    return f"ble_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
