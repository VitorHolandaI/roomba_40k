#!/usr/bin/env python3
"""Create and run the aiohttp server for the Roomba web controller."""

import asyncio
import os

from aiohttp import web

from media.music import MusicPlayer
from web.broadcast import battery_broadcaster, broadcast_music
from web.control_thread import ControlThread
from web.registry import WebRegistry
from web.shared_state import SharedState
from web.ws_router import handle_ws

# Runtime knobs are kept here so deploys can swap serial/audio settings
# without touching the application factory below.
PORT = os.environ.get("ROOMBA_PORT", "/dev/ttyUSB0")
HTTP_PORT = int(os.environ.get("ROOMBA_HTTP_PORT", "8080"))
MUSIC_DIR = os.environ.get("MUSIC_DIR", "~/Music")
MUSIC_ALSA_DEV = os.environ.get("MUSIC_ALSA_DEV", "hw:1,0")
MUSIC_AUTOPLAY = os.environ.get("MUSIC_AUTOPLAY", "1") != "0"
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


async def handle_index(request: web.Request) -> web.FileResponse:
    """Serve the browser controller entrypoint.

    Example: ``app.router.add_get("/", handle_index)``.
    """
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


def _on_music_change(app: web.Application) -> None:
    registry: WebRegistry = app["registry"]
    if registry.loop is None or registry._music_bcast_pending:
        return

    # MusicPlayer can report changes from its own worker context, so schedule
    # the websocket broadcast back onto aiohttp's event loop.
    registry._music_bcast_pending = True
    registry.loop.call_soon_threadsafe(
        lambda: asyncio.ensure_future(broadcast_music(registry))
    )


async def on_startup(app: web.Application) -> None:
    """Start hardware, battery, and music background services.

    Example: ``app.on_startup.append(on_startup)``.
    """
    registry: WebRegistry = app["registry"]
    registry.loop = asyncio.get_running_loop()

    # Long-running hardware polling lives off the event loop; lightweight
    # websocket status pushes stay as asyncio tasks.
    app["control"] = ControlThread(app["state"], port=PORT)
    app["control"].start()
    app["broadcaster"] = asyncio.create_task(
        battery_broadcaster(registry, app["state"])
    )

    # The player is registered after the loop is known so callbacks can safely
    # fan out song-state updates to connected clients.
    registry.player = MusicPlayer(
        MUSIC_DIR,
        alsa_dev=MUSIC_ALSA_DEV,
        on_change=lambda: _on_music_change(app),
        autoplay=MUSIC_AUTOPLAY,
    )
    registry.player.start()


async def on_cleanup(app: web.Application) -> None:
    """Close clients and stop background services during aiohttp shutdown.

    Example: ``app.on_cleanup.append(on_cleanup)``.
    """
    # Close clients first so shutdown does not leave browsers waiting for more
    # telemetry or music updates.
    for ws in list(app["registry"].clients):
        try:
            await ws.close()
        except Exception:
            pass

    # Stop background work before tearing down the thread-backed controller.
    task = app.get("broadcaster")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    ctrl = app.get("control")
    if ctrl:
        ctrl.stop()
        ctrl.join(timeout=2.0)

    if app["registry"].player is not None:
        app["registry"].player.stop_proc()


def build_app() -> web.Application:
    """Build the Roomba web application with routes and lifecycle hooks.

    Example: ``web.run_app(build_app(), host="0.0.0.0", port=HTTP_PORT)``.
    """
    app = web.Application()
    app["state"] = SharedState()
    app["registry"] = WebRegistry()

    # HTTP serves the static controller UI; websocket traffic carries live
    # commands and telemetry.
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def main() -> None:
    """Run the Roomba web server from the command line.

    Example: ``python -m web.server``.
    """
    app = build_app()
    print(f"[http] servindo em http://0.0.0.0:{HTTP_PORT}  (serial: {PORT})")
    web.run_app(app, host="0.0.0.0", port=HTTP_PORT, print=None)


if __name__ == "__main__":
    main()
