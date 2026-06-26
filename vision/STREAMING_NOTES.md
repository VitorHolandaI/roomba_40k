# Webcam Streaming on Raspberry Pi 3B+ — Findings

Goal: stream a USB webcam to a browser to check camera placement on the
Roomba, with the lowest possible latency on a Raspberry Pi 3B+.

Hardware under test:
- Raspberry Pi 3B+ (1.4 GHz quad-core ARM Cortex-A53, USB 2.0 shared bus)
- USB camera at `/dev/video0` (`usb-3f980000.usb-1.2`)
- Camera output format: **`JPEG` (JFIF JPEG, compressed)**
- Supported resolutions only: `160x120`, `320x240`, `640x480`

---

## 1. `JPEG` vs `MJPEG` — they are effectively the same

The camera advertises V4L2 pixel format `JPEG`, not `MJPG`. This caused
confusion, so it was investigated.

**Conclusion: at the byte level they are identical — both are JPEG frames.**

- **MJPEG** ("Motion JPEG") = a stream of standalone JPEG frames
  concatenated: `[JPEG][JPEG][JPEG]...`. Each frame *is* a full JPEG.
- **V4L2 `JPEG`** (`V4L2_PIX_FMT_JPEG`) = *intended* for a single JPEG
  still, but UVC webcams stream it the same way — one JPEG per frame.

Per the V4L2 spec and libcamera source, the two fourccs are
**"under-specified and are used interchangeably by kernel drivers."**
libcamera maps `V4L2_PIX_FMT_JPEG` → `formats::MJPEG`. ffmpeg decodes both
as the same `AV_CODEC_ID_MJPEG`.

Theoretical-only difference: true MJPEG *may* strip repeated JPEG header
tables (DHT/DQT) per frame to save bytes; a pure `JPEG` frame carries full
JFIF headers each time. In practice this camera sends full self-contained
JPEGs regardless of the label.

Mental model:

```
MJPEG:  [JPEG][JPEG][JPEG][JPEG]...   built for streaming
JPEG:   [JPEG]                        built for one snapshot
                                      (webcam streams many anyway)
```

Video = JPEG photos pushed fast in a row. The JPEG *inside* both is the
same thing.

ustreamer confirmed this live:

```
ERROR -- Could not obtain the requested format=MJPEG; driver gave us JPEG
INFO  -- Falling back to format=JPEG
INFO  -- Switching to HW encoder: the input is (M)JPEG ...
```

It treats the `JPEG` driver format as (M)JPEG and uses the hardware path.

**Sources**
- libcamera: Map V4L2_PIX_FMT_JPEG to formats::MJPEG —
  https://patchwork.libcamera.org/patch/16916/
- V4L2 MJPEG decoding (Raspberry Pi forums) —
  https://forums.raspberrypi.com/viewtopic.php?t=356791

---

## 2. The Python streamer worked but was too slow

A custom aiohttp server was built (`vision/vision_server/`): ffmpeg reads
the camera with `-c copy` (no re-encode), Python splits the byte stream on
JPEG markers (`FF D8` … `FF D9`) and relays each frame to the browser as
`multipart/x-mixed-replace`. It functioned but the feed was very laggy on
the Pi 3B+.

Root causes:

1. **ffmpeg subprocess overhead.** A full ffmpeg process per stream, bytes
   piped through an OS pipe into Python — extra copies and context
   switches on every frame.
2. **Python per-frame hot loop.** Each frame does: read chunk →
   `bytearray.find()` scan for SOI/EOI → slice → build multipart header →
   `await response.write()`. On a 1.4 GHz ARM core, interpreted Python
   makes every step expensive; multiplied by 15–30 fps it chokes.
3. **Single-threaded asyncio.** One event loop handled both frame-splitting
   and HTTP writing — no parallelism.
4. **No frame dropping.** Every frame was queued. When the browser fell
   behind, latency accumulated and the delay grew over time.
5. **Wasteful byte scanning.** `buffer.find()` re-scans 64 KB chunks each
   read; the JPEG boundaries are already known to the V4L2 driver.

**Rule learned:** the per-frame video hot loop does not belong in Python on
a weak Pi. Python is fine for control/logic; a C tool should own the pixels.

---

## 3. ustreamer — the right tool

[µStreamer / ustreamer](https://github.com/pikvm/ustreamer) is a C MJPEG
HTTP streamer built for the Raspberry Pi. It is dramatically faster than
the Python relay because it:

- is C with **no per-frame Python cost**,
- reads V4L2 directly via **MMAP** (no ffmpeg subprocess, no pipe copy),
- uses a **hardware JPEG encoder** and **multi-threaded** worker pool,
- **drops stale frames** so latency never piles up,
- exposes a built-in viewer, `/stream`, and `/snapshot`.

Install + run:

```bash
sudo apt install ustreamer

ustreamer --device=/dev/video0 --resolution=320x240 --format=JPEG \
          --host=0.0.0.0 --port=8081 --desired-fps=10 \
          --drop-same-frames=30
```

Open `http://<pi-ip>:8081`. Use `--format=JPEG` (not MJPEG) to match the
driver and silence the fallback warning.

Endpoints:
- `http://<pi-ip>:8081/`        built-in viewer
- `http://<pi-ip>:8081/stream`  raw MJPEG (drop into an `<img>`)
- `http://<pi-ip>:8081/snapshot` single JPEG

Older alternative `mjpg-streamer` works but ustreamer is better.

---

## 4. The Pi crashed — USB power brownout

During a 640x480 stream the Pi **hard-crashed/froze**. This is almost
certainly a **USB power brownout**, not software: a USB webcam draws a
current spike when streaming, and a Pi 3B+ on an under-spec PSU dips below
voltage and resets/freezes.

Diagnose after reboot:

```bash
vcgencmd get_throttled      # 0x0 = healthy; non-zero = under-voltage seen
dmesg | grep -i -E "voltage|under-voltage|usb|brownout"
```

A lightning-bolt icon on screen or a non-zero `get_throttled` (e.g.
`0x50005`) confirms under-voltage.

Fixes, most → least likely:

1. **Use the official 5V 2.5A PSU.** Phone chargers brown out under camera
   load. This is the most common fix.
2. **Use a short, thick USB power cable.** Thin cables drop voltage.
3. **Put the camera on a powered USB hub** to offload current from the Pi.
4. **Lower resolution / fps** to cut the current draw (see below).

Software cannot fix a brownout — if it still crashes at the lowest setting,
the power supply must be addressed.

---

## 5. Recommended settings for this camera

Start conservative for the position test, then raise if stable:

```bash
# Balanced: good for checking camera placement
ustreamer --device=/dev/video0 --resolution=320x240 --format=JPEG \
          --host=0.0.0.0 --port=8081 --desired-fps=10 --drop-same-frames=30

# Lightest: if 320x240 still browns out / crashes
ustreamer --device=/dev/video0 --resolution=160x120 --format=JPEG \
          --host=0.0.0.0 --port=8081 --desired-fps=10
```

Camera supports only `160x120`, `320x240`, `640x480`. Reach for 640x480
only once power is confirmed stable.

---

## 6. Status of `vision/vision_server/` (the Python streamer)

Kept for reference / possible reuse. It is correct and tested
(`tests/test_mjpeg_source.py`) but **not recommended for live streaming on
the Pi 3B+** — ustreamer replaces it for that job.

Open decision: either delete `vision_server/`, or repurpose it to *launch
and supervise ustreamer* and embed the feed into the main Roomba web app
(battery + drive controls + camera in one server).

**Division of labor that works:** Python for Roomba control/logic,
ustreamer (C) for the video pixels.
