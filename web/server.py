#!/usr/bin/env python3
"""Create and run the aiohttp server for the Roomba web controller."""

import asyncio
import os
import ssl
from typing import Optional

from aiohttp import web

from config import BUMP_AUDIO_DIR, BUMP_AUDIO_ALSA_DEV
from media.bump_audio import BumpAudioPlayer
from media.live_voice import LiveVoicePlayer
from media.music import MusicPlayer
from web.broadcast import battery_broadcaster, bump_broadcaster, broadcast_music
from web.control_thread import ControlThread
from web.registry import WebRegistry
from web.shared_state import SharedState
from web.voice_stream import handle_voice_ws
from web.ws_router import handle_ws

# Runtime knobs are kept here so deploys can swap serial/audio settings
# without touching the application factory below.
PORT = os.environ.get("ROOMBA_PORT", "/dev/ttyUSB0")
HTTP_PORT = int(os.environ.get("ROOMBA_HTTP_PORT", "8080"))
MUSIC_DIR = os.environ.get("MUSIC_DIR", "~/Music")
MUSIC_ALSA_DEV = os.environ.get("MUSIC_ALSA_DEV", "hw:1,0")
MUSIC_AUTOPLAY = os.environ.get("MUSIC_AUTOPLAY", "0") == "1"
VOICE_ALSA_DEV = os.environ.get(
    "VOICE_ALSA_DEV", MUSIC_ALSA_DEV.replace("hw:", "plughw:", 1)
)
TLS_CERT = os.environ.get("ROOMBA_TLS_CERT")
TLS_KEY = os.environ.get("ROOMBA_TLS_KEY")
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
    # websocket status pushes stay as asyncio tasks. The bump sound effects
    # are owned by the control thread so a hit fires audio without the loop.
    app["effects"] = BumpAudioPlayer(BUMP_AUDIO_DIR, alsa_dev=BUMP_AUDIO_ALSA_DEV)
    app["control"] = ControlThread(app["state"], port=PORT, effects=app["effects"])
    app["control"].start()
    app["broadcaster"] = asyncio.create_task(
        battery_broadcaster(registry, app["state"])
    )
    app["bump_broadcaster"] = asyncio.create_task(
        bump_broadcaster(registry, app["state"])
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
    app["shutting_down"] = True
    # Close clients first so shutdown does not leave browsers waiting for more
    # telemetry or music updates.
    for ws in list(app["registry"].clients):
        try:
            await ws.close()
        except Exception:
            pass
    voice_ws = app.get("voice_ws")
    if voice_ws is not None:
        await voice_ws.close()
    await app["live_voice"].stop()

    # Stop background work before tearing down the thread-backed controller.
    for key in ("broadcaster", "bump_broadcaster"):
        task = app.get(key)
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
    app["live_voice"] = LiveVoicePlayer(VOICE_ALSA_DEV)
    app["voice_lock"] = asyncio.Lock()
    app["voice_ws"] = None
    app["shutting_down"] = False

    # HTTP serves the static controller UI; websocket traffic carries live
    # commands and telemetry.
    app.router.add_get("/", handle_index)
    app.router.add_get("/ws", handle_ws)
    app.router.add_get("/voice-ws", handle_voice_ws)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


def build_ssl_context(
    certificate: Optional[str], key: Optional[str]
) -> Optional[ssl.SSLContext]:
    """Build optional TLS from a certificate/key pair.

    Example: ``build_ssl_context('server.crt', 'server.key')``.
    """
    if bool(certificate) != bool(key):
        raise ValueError(
            f"TLS certificate={certificate!r}, key={key!r}; expected both paths"
        )
    if certificate is None or key is None:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    return context


def main() -> None:
    """Run the Roomba web server from the command line.

    Example: ``python -m web.server``.
    """
    app = build_app()
    ssl_context = build_ssl_context(TLS_CERT, TLS_KEY)
    scheme = "https" if ssl_context is not None else "http"
    print(f"[http] servindo em {scheme}://0.0.0.0:{HTTP_PORT}  (serial: {PORT})")
    web.run_app(
        app,
        host="0.0.0.0",
        port=HTTP_PORT,
        print=None,
        ssl_context=ssl_context,
    )


if __name__ == "__main__":
    main()
