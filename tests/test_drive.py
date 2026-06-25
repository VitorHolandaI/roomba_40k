"""Pure drive-math tests — zero hardware dependency."""

from roomba.drive import clamp_velocity, is_drive_stale


def test_clamp_velocity_limits() -> None:
    assert clamp_velocity(600) == 500
    assert clamp_velocity(-600) == -500
    assert clamp_velocity(0) == 0
    assert clamp_velocity(250) == 250


def test_is_drive_stale() -> None:
    assert is_drive_stale(last_update=0.0, now=0.5, timeout=0.3) is True
    assert is_drive_stale(last_update=0.0, now=0.2, timeout=0.3) is False
