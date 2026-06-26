#!/usr/bin/env python3
"""aiohttp MJPEG webcam server — quick camera-position check on a Pi 3B+.

Run: ``python -m vision_server.server`` then open the printed URL and drag
the camera around while watching the live feed.
"""

import asyncio
import os

from aiohttp import web

from vision_server.config import CameraConfig
from vision_server.stream_handler import handle_stream

HTTP_PORT = int(os.environ.get("CAM_HTTP_PORT", "8081"))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")


async def handle_index(request: web.Request) -> web.FileResponse:
    """Serve the single-page live viewer.

    Example: ``app.router.add_get("/", handle_index)``.
    """
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))


def build_app() -> web.Application:
    """Build the camera app with the viewer page and stream route.

    Example: ``web.run_app(build_app(), host="0.0.0.0", port=8081)``.
    """
    app = web.Application()
    app["camera_cfg"] = CameraConfig.from_env()
    app["camera_lock"] = asyncio.Lock()
    app.router.add_get("/", handle_index)
    app.router.add_get("/stream", handle_stream)
    app.router.add_static("/static/", STATIC_DIR, name="static")
    return app


def main() -> None:
    """Run the camera server from the command line.

    Example: ``CAM_FPS=20 python -m vision_server.server``.
    """
    config: CameraConfig = build_app()["camera_cfg"]
    print(
        f"[cam] http://0.0.0.0:{HTTP_PORT}  "
        f"({config.device} {config.width}x{config.height}@{config.fps})"
    )
    web.run_app(build_app(), host="0.0.0.0", port=HTTP_PORT, print=None)


if __name__ == "__main__":
    main()
