"""Mutable runtime registry for the web layer (injected into aiohttp app)."""

import asyncio
from typing import Optional, Set

from aiohttp import web

from media.music import MusicPlayer


class WebRegistry:
    """Holds ephemeral web runtime objects: clients, driver, player, event loop."""

    def __init__(self) -> None:
        self.clients: Set[web.WebSocketResponse] = set()
        self.driver: Optional[web.WebSocketResponse] = None
        self.player: Optional[MusicPlayer] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._music_bcast_pending = False
