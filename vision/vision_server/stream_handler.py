"""Relay webcam JPEG frames as an HTTP multipart stream for a browser <img>.

The camera is a single hardware pipe, so only one viewer streams at a
time; a second request gets ``409`` instead of corrupting the feed.
ffmpeg is started on connect and stopped on disconnect, so the webcam
LED tells you exactly when something is watching.

Example: ``app.router.add_get("/stream", handle_stream)``.
"""

import asyncio

from aiohttp import web

from vision_server.config import CameraConfig
from vision_server.mjpeg_source import MjpegSource

_BOUNDARY = "roombacam"


async def handle_stream(request: web.Request) -> web.StreamResponse:
    """Stream live MJPEG to one viewer; reject overlapping requests."""
    lock: asyncio.Lock = request.app["camera_lock"]
    if lock.locked():
        raise web.HTTPConflict(text="camera already streaming to another viewer")
    async with lock:
        return await _stream_to(request)


async def _stream_to(request: web.Request) -> web.StreamResponse:
    config: CameraConfig = request.app["camera_cfg"]
    source = MjpegSource(config.device, config.width, config.height, config.fps)
    await source.start()
    response = _open_response()
    try:
        await response.prepare(request)
        async for frame in source.frames():
            await _write_part(response, frame)
    except (ConnectionResetError, asyncio.CancelledError):
        pass  # viewer closed the tab; nothing left to send
    finally:
        await source.stop()
    return response


def _open_response() -> web.StreamResponse:
    return web.StreamResponse(
        status=200,
        headers={
            "Content-Type": f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Connection": "close",
        },
    )


async def _write_part(response: web.StreamResponse, frame: bytes) -> None:
    header = (
        f"--{_BOUNDARY}\r\n"
        f"Content-Type: image/jpeg\r\n"
        f"Content-Length: {len(frame)}\r\n\r\n"
    ).encode("ascii")
    await response.write(header + frame + b"\r\n")
