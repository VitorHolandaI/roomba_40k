"""Frontend-to-backend command routing tests."""

import asyncio

from web.registry import WebRegistry
from web.shared_state import SharedState
from web.ws_router import dispatch_message


def test_driver_drive_payload_updates_shared_state() -> None:
    registry = WebRegistry()
    state = SharedState()
    websocket = object()
    registry.driver = websocket  # type: ignore[assignment]

    asyncio.run(
        dispatch_message(
            websocket,  # type: ignore[arg-type]
            registry,
            state,
            {"type": "drive", "left": 900, "right": -900},
        )
    )

    assert state.snapshot_target()[:2] == (500, -500)


def test_spectator_drive_payload_is_ignored() -> None:
    registry = WebRegistry()
    state = SharedState()
    registry.driver = object()  # type: ignore[assignment]
    spectator = object()

    asyncio.run(
        dispatch_message(
            spectator,  # type: ignore[arg-type]
            registry,
            state,
            {"type": "drive", "left": 100, "right": 100},
        )
    )

    assert state.snapshot_target()[:2] == (0, 0)
