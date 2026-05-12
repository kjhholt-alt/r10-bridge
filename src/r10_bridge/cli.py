"""r10-bridge CLI."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from . import __version__
from . import ble_listener, e6_server
from .bridge import BridgeApp, run_uvicorn
from .persist import ShotStore, write_capture_jsonl

console = Console()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

DEFAULT_SETTINGS = {
    "mode": "ble",
    "ble": {
        "device_name_match": "Approach R10",
        "auto_reconnect": True,
        "scan_timeout_sec": 30,
    },
    "e6": {
        "host": "0.0.0.0",
        "port": 6868,
    },
    "bridge": {
        "http_host": "localhost",
        "http_port": 8787,
    },
    "persist": {
        "sqlite_path": "data/shots.db",
        "capture_dir": "captures",
        "keep_captures_days": 30,
    },
}


def _load_settings(path: Optional[Path]) -> dict:
    """Load settings.json if it exists, else use defaults."""
    if path is None:
        path = Path("settings.json")
    if not path.exists():
        return DEFAULT_SETTINGS
    user = json.loads(path.read_text(encoding="utf-8"))
    # Shallow-merge user over defaults
    merged = {**DEFAULT_SETTINGS, **user}
    for k in ("ble", "e6", "bridge", "persist"):
        merged[k] = {**DEFAULT_SETTINGS[k], **(user.get(k) or {})}
    return merged


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        handlers=[RichHandler(console=console, show_path=False, markup=True)],
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="r10-bridge")
@click.option("--settings", type=click.Path(path_type=Path),
              help="Path to settings.json (default: ./settings.json)")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False))
@click.pass_context
def cli(ctx: click.Context, settings: Optional[Path], log_level: str) -> None:
    """Live Bluetooth bridge for the Garmin Approach R10."""
    _setup_logging(log_level)
    ctx.obj = _load_settings(settings)


# ---------------------------------------------------------------------------
# listen — main entry: BLE or E6 mode + HTTP/WS bridge
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--mode", type=click.Choice(["ble", "e6"]), default=None,
              help="Override settings.mode")
@click.pass_obj
def listen(s: dict, mode: Optional[str]) -> None:
    """Start the BLE or E6 listener AND the HTTP/WebSocket bridge."""
    mode = (mode or s["mode"]).lower()
    if mode not in ("ble", "e6"):
        click.echo(f"unknown mode: {mode}", err=True)
        sys.exit(2)

    asyncio.run(_run_listen(s, mode))


async def _run_listen(s: dict, mode: str) -> None:
    store = ShotStore(Path(s["persist"]["sqlite_path"]))
    capture_dir = Path(s["persist"]["capture_dir"])
    capture_path = capture_dir / f"{mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    console.print(f"[green]Capture log:[/green] {capture_path}")

    bridge = BridgeApp(store)

    async def on_frame(frame):
        write_capture_jsonl(capture_path, frame)
        await bridge.on_frame(frame)

    stop_event = asyncio.Event()

    def _handle_signal(*_):
        console.print("\n[yellow]stopping...[/yellow]")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except (ValueError, AttributeError):
            # Windows + non-main thread can hit either
            pass

    listener_task: asyncio.Task
    if mode == "ble":
        listener_task = asyncio.create_task(
            ble_listener.listen(
                on_shot=bridge.on_shot,
                on_frame=on_frame,
                on_device=bridge.on_device,
                device_name_match=s["ble"]["device_name_match"],
                scan_timeout_sec=float(s["ble"]["scan_timeout_sec"]),
                auto_reconnect=bool(s["ble"]["auto_reconnect"]),
                stop_event=stop_event,
            ),
            name="ble_listener",
        )
        console.print(
            f"[bold green]BLE mode[/bold green] · listening for "
            f"'{s['ble']['device_name_match']}'..."
        )
    else:
        listener_task = asyncio.create_task(
            e6_server.serve(
                on_shot=bridge.on_shot,
                on_frame=on_frame,
                host=s["e6"]["host"],
                port=int(s["e6"]["port"]),
                stop_event=stop_event,
            ),
            name="e6_server",
        )
        advert = e6_server.local_advertise_address(int(s["e6"]["port"]))
        console.print(
            f"[bold green]E6 mode[/bold green] · point the Garmin Golf app at "
            f"[bold]{advert}[/bold]\n"
            f"  Garmin Golf → [italic]Play E6 Connect → Play on PC[/italic] → "
            f"set host to the address above"
        )

    http = asyncio.create_task(
        run_uvicorn(
            bridge.api,
            host=s["bridge"]["http_host"],
            port=int(s["bridge"]["http_port"]),
            stop_event=stop_event,
        ),
        name="http_bridge",
    )
    console.print(
        f"[green]HTTP+WS bridge:[/green] "
        f"http://{s['bridge']['http_host']}:{s['bridge']['http_port']}  "
        f"(WS at /ws)"
    )

    await asyncio.gather(listener_task, http)
    store.close()


# ---------------------------------------------------------------------------
# stats — print SQLite summary
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--limit", default=10, type=int)
@click.pass_obj
def stats(s: dict, limit: int) -> None:
    """Show a quick summary of captured shots."""
    store = ShotStore(Path(s["persist"]["sqlite_path"]))
    total = store.count_shots()
    latest = store.latest_shot()
    console.print(f"[bold]r10-bridge stats[/bold] · {total} shots in {s['persist']['sqlite_path']}")
    if latest is None:
        console.print("[dim]no shots yet[/dim]")
        return
    console.print(f"latest: [green]{latest['captured_at']}[/green]")

    recent = store.shots_since("1970-01-01T00:00:00", limit=limit)
    table = Table(show_header=True, header_style="bold green")
    for col in ("When", "Club", "Head spd", "Ball spd", "Smash", "Launch", "Carry", "Spin"):
        table.add_column(col, justify="right" if col not in ("When", "Club") else "left")
    for r in recent:
        table.add_row(
            (r.get("captured_at") or "")[:19],
            r.get("club") or "—",
            f"{r.get('head_speed_mph') or 0:.1f}",
            f"{r.get('ball_speed_mph') or 0:.1f}",
            f"{r.get('smash_factor') or 0:.2f}",
            f"{r.get('launch_angle_deg') or 0:.1f}°",
            f"{r.get('carry_distance_yd') or 0:.0f}",
            f"{r.get('total_spin_rpm') or 0:.0f}",
        )
    console.print(table)
    store.close()


# ---------------------------------------------------------------------------
# ingest — load Garmin Golf CSV export
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("csv_path", type=click.Path(exists=True, path_type=Path))
@click.option("--session-id", default=None)
@click.pass_obj
def ingest(s: dict, csv_path: Path, session_id: Optional[str]) -> None:
    """Import a Garmin Golf app CSV export of shot data."""
    import csv as csv_mod
    from .models import Shot, ShotSource

    store = ShotStore(Path(s["persist"]["sqlite_path"]))
    sess = session_id or f"csv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    store.open_session(sess, device_name="csv_import", notes=str(csv_path))

    def _f(row: dict, *keys) -> Optional[float]:
        for k in keys:
            if k in row and row[k] not in (None, ""):
                try:
                    return float(row[k])
                except (TypeError, ValueError):
                    continue
        return None

    n = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv_mod.DictReader(f)
        for row in reader:
            shot = Shot(source=ShotSource.CSV_INGEST, session_id=sess)
            shot.club = row.get("Club Type") or row.get("Club") or row.get("club")
            shot.ball.speed_mph             = _f(row, "Ball Speed", "Ball Speed (mph)")
            shot.swing.head_speed_mph       = _f(row, "Club Head Speed", "Club Speed", "Club Head Speed (mph)")
            shot.ball.launch_angle_deg      = _f(row, "Launch Angle", "Launch Angle (°)")
            shot.ball.launch_direction_deg  = _f(row, "Launch Direction", "Launch Direction (°)")
            shot.ball.total_spin_rpm        = _f(row, "Spin Rate", "Total Spin", "Total Spin (rpm)")
            shot.ball.back_spin_rpm         = _f(row, "Back Spin")
            shot.ball.side_spin_rpm         = _f(row, "Side Spin")
            shot.ball.spin_axis_deg         = _f(row, "Spin Axis", "Spin Axis (°)")
            shot.swing.club_path_deg        = _f(row, "Club Path")
            shot.swing.face_angle_deg       = _f(row, "Face Angle", "Club Face")
            shot.swing.attack_angle_deg     = _f(row, "Attack Angle", "Angle of Attack")
            shot.result.apex_height_yd      = _f(row, "Apex Height", "Apex")
            shot.result.carry_distance_yd   = _f(row, "Carry Distance", "Carry", "Carry Distance (yds)")
            shot.result.total_distance_yd   = _f(row, "Total Distance", "Total", "Total Distance (yds)")
            shot.result.deviation_angle_deg = _f(row, "Deviation Angle")
            shot.result.deviation_distance_yd = _f(row, "Deviation Distance")
            shot.result.smash_factor        = _f(row, "Smash Factor", "Smash")
            if (shot.result.smash_factor is None
                    and shot.swing.head_speed_mph and shot.swing.head_speed_mph > 0
                    and shot.ball.speed_mph):
                shot.result.smash_factor = round(
                    shot.ball.speed_mph / shot.swing.head_speed_mph, 3)
            store.save_shot(shot)
            n += 1
    store.close_session(sess)
    store.close()
    console.print(f"[green]imported {n} shots[/green] from {csv_path} → session {sess}")


# ---------------------------------------------------------------------------
# bridge-only — useful for testing the HTTP layer without a device
# ---------------------------------------------------------------------------

@cli.command(name="serve-bridge")
@click.pass_obj
def serve_bridge(s: dict) -> None:
    """Start ONLY the HTTP/WS bridge (no BLE/E6 listener)."""
    asyncio.run(_run_bridge_only(s))


async def _run_bridge_only(s: dict) -> None:
    store = ShotStore(Path(s["persist"]["sqlite_path"]))
    bridge = BridgeApp(store)
    stop_event = asyncio.Event()
    console.print(
        f"[green]HTTP+WS bridge only:[/green] "
        f"http://{s['bridge']['http_host']}:{s['bridge']['http_port']}"
    )
    await run_uvicorn(
        bridge.api,
        host=s["bridge"]["http_host"],
        port=int(s["bridge"]["http_port"]),
        stop_event=stop_event,
    )
    store.close()


if __name__ == "__main__":
    cli()
