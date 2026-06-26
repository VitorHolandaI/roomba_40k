"""Make the retired ``vision_server`` package importable for its tests.

The Python MJPEG streamer was shelved (too slow on a Pi 3B+; ustreamer
replaced it — see ``vision/STREAMING_NOTES.md``). It now lives under
``vision/old_code/vision_server`` but still imports as ``vision_server``
so its regression tests keep running. Adding ``vision/old_code`` to the
path preserves that import without polluting the active codebase.
"""

import os
import sys

_OLD_CODE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "vision", "old_code"
)
if _OLD_CODE_DIR not in sys.path:
    sys.path.insert(0, _OLD_CODE_DIR)
