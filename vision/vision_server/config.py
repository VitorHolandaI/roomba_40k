"""Camera runtime knobs, read from the environment at startup.

Kept separate from the app factory so deploys can retune resolution and
fps for the Pi 3B+ without touching server wiring.

Example: ``CameraConfig.from_env().device  # "/dev/video0"``.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraConfig:
    device: str
    width: int
    height: int
    fps: int

    @staticmethod
    def from_env() -> "CameraConfig":
        return CameraConfig(
            device=os.environ.get("CAM_DEVICE", "/dev/video0"),
            width=int(os.environ.get("CAM_WIDTH", "640")),
            height=int(os.environ.get("CAM_HEIGHT", "480")),
            fps=int(os.environ.get("CAM_FPS", "15")),
        )
