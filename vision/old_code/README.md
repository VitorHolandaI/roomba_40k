# old_code — retired experiments

Code kept for reference, **not used in production**.

## `vision_server/` — Python aiohttp MJPEG streamer (RETIRED)

A custom webcam-to-browser streamer: ffmpeg reads the camera with
`-c copy`, Python splits the JPEG byte stream on `FF D8`/`FF D9` markers
and relays frames as `multipart/x-mixed-replace`.

**Why retired:** too slow on a Raspberry Pi 3B+. The per-frame work in
interpreted Python (byte scanning, multipart framing, single-threaded
asyncio, no frame dropping) can't keep up on a 1.4 GHz ARM core.

**Replaced by:** [ustreamer](https://github.com/pikvm/ustreamer) — a C
streamer with V4L2 mmap, a hardware JPEG encoder, multi-threaded workers,
and stale-frame dropping. See `vision/STREAMING_NOTES.md` for the full
findings (JPEG vs MJPEG, the Python-slowness analysis, the Pi USB power
brownout, and recommended ustreamer settings).

The code is correct and still tested (`vision_server/test_mjpeg_source.py`)
— it's kept in case the frame-splitting logic is reused, e.g. to embed the
ustreamer feed into the main Roomba web app.
