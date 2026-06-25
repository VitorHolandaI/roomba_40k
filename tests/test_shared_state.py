"""SharedState command tests — no hardware dependency."""

from web.shared_state import SharedState


def test_drive_command_overwrites_target_and_disables_auto() -> None:
    state = SharedState()
    state.set_auto(True)

    state.set_drive(120, -80)

    left, right, last_update = state.snapshot_target()
    assert (left, right) == (120, -80)
    assert last_update > 0
    assert state.get_auto() is False


def test_dock_request_is_single_use_and_stops_robot() -> None:
    state = SharedState()
    state.set_drive(100, 100)

    state.request_dock()

    assert state.snapshot_target()[:2] == (0, 0)
    assert state.take_dock_request() is True
    assert state.take_dock_request() is False
