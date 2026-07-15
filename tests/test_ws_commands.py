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


def _dispatch(ws: object, registry: WebRegistry, state: SharedState, msg: dict) -> None:
    asyncio.run(
        dispatch_message(ws, registry, state, msg)  # type: ignore[arg-type]
    )


def test_roomba_song_queues_request_even_for_spectator() -> None:
    registry = WebRegistry()
    state = SharedState()
    registry.driver = object()  # type: ignore[assignment]
    spectator = object()

    _dispatch(spectator, registry, state, {"type": "roomba_song", "index": 3})

    assert state.take_song_request() == 3


def test_roomba_song_ignores_non_numeric_index() -> None:
    registry = WebRegistry()
    state = SharedState()

    _dispatch(object(), registry, state, {"type": "roomba_song", "index": "x"})

    assert state.take_song_request() is None


def test_wake_from_driver_queues_request() -> None:
    registry = WebRegistry()
    state = SharedState()
    driver = object()
    registry.driver = driver  # type: ignore[assignment]

    _dispatch(driver, registry, state, {"type": "wake"})

    assert state.take_wake_request() is True


def test_wake_from_spectator_is_ignored() -> None:
    registry = WebRegistry()
    state = SharedState()
    registry.driver = object()  # type: ignore[assignment]

    _dispatch(object(), registry, state, {"type": "wake"})

    assert state.take_wake_request() is False
