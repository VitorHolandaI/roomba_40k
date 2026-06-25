"""Named fake classes for hardware-free tests."""

from typing import Any, List, Tuple


class FakeRoomba:
    """Stub RoombaInterface for command-flow tests."""

    def __init__(self) -> None:
        self.calls: List[Tuple[str, Tuple[Any, ...]]] = []
        self.passivo = False

    def drive(self, left: int, right: int) -> None:
        self.calls.append(("drive", (left, right)))

    def drive_stop(self) -> None:
        self.calls.append(("drive_stop", ()))

    def ensure_safe(self) -> None:
        self.calls.append(("ensure_safe", ()))

    def set_passive(self) -> None:
        self.passivo = True

    def seek_dock(self) -> None:
        self.calls.append(("seek_dock", ()))

    def set_clean_motors(self, on: bool) -> None:
        self.calls.append(("clean_motors", (on,)))

    def shutdown(self) -> None:
        self.calls.append(("shutdown", ()))
