"""WebSocket command router — translates JSON messages into SharedState updates."""

import json
from typing import Awaitable, Callable, Optional, cast

from aiohttp import web, WSMsgType

from roomba.drive import clamp_velocity
from web.broadcast import (
    broadcast_auto,
    broadcast_clean_motors,
    notify_roles,
)
from web.registry import WebRegistry
from web.shared_state import SharedState

Payload = dict[str, object]
_CommandHandler = Callable[
    [web.WebSocketResponse, WebRegistry, SharedState, Payload], Awaitable[None]
]


def _coerce_int(value: object, default: int) -> int:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp_vel(value: object) -> int:
    return clamp_velocity(_coerce_int(value, default=0))


async def _cmd_drive(
    _ws: web.WebSocketResponse,
    _registry: WebRegistry,
    state: SharedState,
    data: Payload,
) -> None:
    left = _clamp_vel(data.get("left", 0))
    right = _clamp_vel(data.get("right", 0))
    state.set_drive(left, right)


async def _cmd_stop(
    _ws: web.WebSocketResponse,
    registry: WebRegistry,
    state: SharedState,
    _data: Payload,
) -> None:
    state.request_stop()
    await broadcast_auto(registry, state)


async def _cmd_dock(
    _ws: web.WebSocketResponse,
    registry: WebRegistry,
    state: SharedState,
    _data: Payload,
) -> None:
    state.request_dock()
    await broadcast_auto(registry, state)


async def _cmd_auto(
    _ws: web.WebSocketResponse,
    registry: WebRegistry,
    state: SharedState,
    data: Payload,
) -> None:
    state.set_auto(bool(data.get("on")))
    await broadcast_auto(registry, state)


async def _cmd_clean(
    _ws: web.WebSocketResponse,
    registry: WebRegistry,
    state: SharedState,
    data: Payload,
) -> None:
    state.set_clean_motors(bool(data.get("on")))
    await broadcast_clean_motors(registry, state)


async def _cmd_vel(
    _ws: web.WebSocketResponse,
    _registry: WebRegistry,
    state: SharedState,
    data: Payload,
) -> None:
    state.set_speed(_coerce_int(data.get("value", 150), default=150))


_COMMANDS: dict[str, _CommandHandler] = {
    "drive": _cmd_drive,
    "stop": _cmd_stop,
    "dock": _cmd_dock,
    "auto": _cmd_auto,
    "clean_motors": _cmd_clean,
    "vel": _cmd_vel,
}


def _handle_music(registry: WebRegistry, data: Payload) -> None:
    player = registry.player
    if player is None:
        return
    action = data.get("action")
    if not isinstance(action, str):
        return
    if action == "play":
        player.play(data.get("index"))
        return
    if action == "volume":
        player.set_volume(data.get("value", 80))
        return

    no_arg_actions: dict[str, Callable[[], None]] = {
        "pause": player.pause,
        "stop": player.stop,
        "next": player.next,
        "prev": player.prev,
        "rescan": player.rescan,
    }
    handler = no_arg_actions.get(action)
    if handler is not None:
        handler()


def _parse_payload(raw: str) -> Optional[Payload]:
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    return cast(Payload, payload)


async def dispatch_message(
    ws: web.WebSocketResponse,
    registry: WebRegistry,
    state: SharedState,
    data: Payload,
) -> None:
    command_type = data.get("type")
    if not isinstance(command_type, str):
        return

    if command_type == "claim":
        if ws is not registry.driver:
            registry.driver = ws
            state.request_stop()
            await notify_roles(registry)
        return

    if command_type == "music":
        _handle_music(registry, data)
        return

    if ws is not registry.driver:
        return

    handler = _COMMANDS.get(command_type)
    if handler is not None:
        await handler(ws, registry, state, data)


async def handle_ws(request: web.Request) -> web.WebSocketResponse:
    registry: WebRegistry = request.app["registry"]
    state: SharedState = request.app["state"]

    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    registry.clients.add(ws)
    if registry.driver is None:
        registry.driver = ws

    try:
        await ws.send_json(state.get_battery())
        await ws.send_json({"type": "auto", "on": state.get_auto()})
        await ws.send_json({"type": "clean_motors", "on": state.get_clean_motors()})
        if registry.player is not None:
            await ws.send_json(registry.player.state())
    except Exception:
        pass
    await notify_roles(registry)

    try:
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                if msg.type == WSMsgType.ERROR:
                    break
                continue

            if not isinstance(msg.data, str):
                continue
            data = _parse_payload(msg.data)
            if data is None:
                continue

            await dispatch_message(ws, registry, state, data)

    finally:
        registry.clients.discard(ws)
        state.request_stop()
        if ws is registry.driver:
            registry.driver = next(iter(registry.clients), None)
            await notify_roles(registry)

    return ws
