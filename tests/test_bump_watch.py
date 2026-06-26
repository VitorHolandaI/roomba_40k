"""Rising-edge bump detection tests — pure logic, no hardware."""

from roomba.bump_watch import BumpWatcher


class _FakeBumps:
    def __init__(self, left: bool, right: bool) -> None:
        self.bump_left = left
        self.bump_right = right
        self.wheeldrop_left = False
        self.wheeldrop_right = False


class _FakeSensors:
    def __init__(self, left: bool, right: bool) -> None:
        self.bumps_wheeldrops = _FakeBumps(left, right)


def test_first_bump_is_rising_edge() -> None:
    watcher = BumpWatcher()
    assert watcher.bumped(_FakeSensors(True, False)) is True


def test_held_bump_fires_only_once() -> None:
    watcher = BumpWatcher()
    watcher.bumped(_FakeSensors(False, True))
    # Still pressed on the next poll: no new trigger.
    assert watcher.bumped(_FakeSensors(False, True)) is False


def test_release_then_press_fires_again() -> None:
    watcher = BumpWatcher()
    watcher.bumped(_FakeSensors(True, False))
    watcher.bumped(_FakeSensors(False, False))  # released
    assert watcher.bumped(_FakeSensors(True, False)) is True


def test_no_sensors_never_bumps() -> None:
    watcher = BumpWatcher()
    assert watcher.bumped(None) is False
