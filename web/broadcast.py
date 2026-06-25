"""Async broadcast helpers for WebSocket clients."""

import asyncio
from typing import Set

from aiohttp import web

from web.registry import WebRegistry
from web.shared_state import SharedState


async def broadcast_battery(registry: WebRegistry, state: SharedState) -> None:
    info = state.get_battery()
    await _send_json_to_all(registry.clients, info)


async def broadcast_auto(registry: WebRegistry, state: SharedState) -> None:
    msg = {"type": "auto", "on": state.get_auto()}
    await _send_json_to_all(registry.clients, msg)


async def broadcast_clean_motors(registry: WebRegistry, state: SharedState) -> None:
    msg = {"type": "clean_motors", "on": state.get_clean_motors()}
    await _send_json_to_all(registry.clients, msg)


async def broadcast_music(registry: WebRegistry) -> None:
    registry._music_bcast_pending = False
    if registry.player is None:
        return
    info = registry.player.state()
    await _send_json_to_all(registry.clients, info)


async def notify_roles(registry: WebRegistry) -> None:
    for ws in list(registry.clients):
        try:
            await ws.send_json({"type": "role", "driver": ws is registry.driver})
        except Exception:
            registry.clients.discard(ws)


async def battery_broadcaster(registry: WebRegistry, state: SharedState) -> None:
    try:
        while True:
            await asyncio.sleep(2.0)
            if not registry.clients:
                continue
            await broadcast_battery(registry, state)
    except asyncio.CancelledError:
        pass


async def _send_json_to_all(
    clients: Set[web.WebSocketResponse],
    payload: dict,
) -> None:
    for ws in list(clients):
        try:
            await ws.send_json(payload)
        except Exception:
            clients.discard(ws)
