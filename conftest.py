"""Make the nested ``vision/`` packages importable as top-level modules.

``vision/vision_server`` lives one level down so vision experiments stay
grouped, but it should import as ``vision_server`` like the repo-root
packages (``web``, ``roomba``). Adding ``vision/`` to the path keeps both
the tests and ``python -m vision_server.server`` working from repo root.
"""

import os
import sys

_VISION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vision")
if _VISION_DIR not in sys.path:
    sys.path.insert(0, _VISION_DIR)
