"""JPEG frame-splitting tests — no camera or ffmpeg needed."""

import os

from vision_server.config import CameraConfig
from vision_server.mjpeg_source import _pop_frame

_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"


def _jpeg(payload: bytes) -> bytes:
    return _SOI + payload + _EOI


def test_pop_frame_returns_none_without_full_frame() -> None:
    buffer = bytearray(_SOI + b"partial")
    assert _pop_frame(buffer) is None
    # Incomplete data stays buffered for the next read.
    assert bytes(buffer) == _SOI + b"partial"


def test_pop_frame_extracts_one_frame_and_consumes_it() -> None:
    frame = _jpeg(b"abc")
    buffer = bytearray(frame)
    assert _pop_frame(buffer) == frame
    assert bytes(buffer) == b""


def test_pop_frame_drops_leading_garbage_before_soi() -> None:
    frame = _jpeg(b"x")
    buffer = bytearray(b"junk" + frame)
    assert _pop_frame(buffer) == frame


def test_pop_frame_splits_two_back_to_back_frames() -> None:
    first, second = _jpeg(b"one"), _jpeg(b"two")
    buffer = bytearray(first + second)
    assert _pop_frame(buffer) == first
    assert _pop_frame(buffer) == second
    assert _pop_frame(buffer) is None


def test_config_from_env_reads_overrides() -> None:
    os.environ["CAM_DEVICE"] = "/dev/video9"
    os.environ["CAM_FPS"] = "30"
    try:
        config = CameraConfig.from_env()
    finally:
        del os.environ["CAM_DEVICE"]
        del os.environ["CAM_FPS"]
    assert config.device == "/dev/video9"
    assert config.fps == 30


def test_config_from_env_defaults() -> None:
    config = CameraConfig.from_env()
    assert config.device == "/dev/video0"
    assert (config.width, config.height) == (640, 480)
