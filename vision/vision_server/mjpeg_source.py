"""Zero-recompress MJPEG frames from a V4L2 webcam via ffmpeg.

ffmpeg reads the camera in its native MJPEG mode and copies the JPEG
stream verbatim (``-c copy``), so a Raspberry Pi 3B+ never burns CPU
re-encoding. That keeps latency low enough to eyeball webcam placement.

Example::

    source = MjpegSource("/dev/video0", 640, 480, 15, "mjpeg")
    await source.start()
    async for jpeg in source.frames():
        ...  # raw JPEG bytes, ready to push to a browser <img>
    await source.stop()
"""

import asyncio
from typing import AsyncIterator, List, Optional

_SOI = b"\xff\xd8"  # JPEG start-of-image marker
_EOI = b"\xff\xd9"  # JPEG end-of-image marker
_READ_SIZE = 65536


def _pop_frame(buffer: bytearray) -> Optional[bytes]:
    """Remove and return the first complete JPEG in ``buffer``.

    Returns ``None`` when no whole SOI..EOI frame is buffered yet.

    Example: ``_pop_frame(bytearray(b"\\xff\\xd8x\\xff\\xd9")) ==
    b"\\xff\\xd8x\\xff\\xd9"``.
    """
    start = buffer.find(_SOI)
    if start < 0:
        return None
    end = buffer.find(_EOI, start + 2)
    if end < 0:
        return None
    end += len(_EOI)
    frame = bytes(buffer[start:end])
    del buffer[:end]
    return frame


class MjpegSource:
    """Owns one ffmpeg capture process and yields its JPEG frames."""

    def __init__(
        self, device: str, width: int, height: int, fps: int, input_format: str
    ) -> None:
        self._device = device
        self._width = width
        self._height = height
        self._fps = fps
        self._input_format = input_format
        self._proc: Optional[asyncio.subprocess.Process] = None

    def _ffmpeg_args(self) -> List[str]:
        return [
            "ffmpeg",
            "-loglevel", "error",
            "-f", "v4l2",
            "-input_format", self._input_format,
            "-video_size", f"{self._width}x{self._height}",
            "-framerate", str(self._fps),
            "-i", self._device,
            "-c", "copy",
            "-f", "mjpeg",
            "pipe:1",
        ]

    async def start(self) -> None:
        """Spawn ffmpeg; raises if the binary or camera is missing."""
        self._proc = await asyncio.create_subprocess_exec(
            *self._ffmpeg_args(),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def frames(self) -> AsyncIterator[bytes]:
        """Yield each complete JPEG frame until ffmpeg's stdout closes."""
        reader = self._require_stdout()
        buffer = bytearray()
        while True:
            chunk = await reader.read(_READ_SIZE)
            if not chunk:
                return
            buffer.extend(chunk)
            frame = _pop_frame(buffer)
            while frame is not None:
                yield frame
                frame = _pop_frame(buffer)

    def _require_stdout(self) -> asyncio.StreamReader:
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError(
                f"MjpegSource for {self._device!r} not started; call start() first"
            )
        return self._proc.stdout

    async def stop(self) -> None:
        """Terminate ffmpeg and reap it; safe to call when not started."""
        proc = self._proc
        if proc is None:
            return
        if proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._proc = None
