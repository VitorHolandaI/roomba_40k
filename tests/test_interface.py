"""Roomba serial wrapper state-recovery tests."""

from roomba.interface import RoombaInterface


class _FakeCreate2:
    """Record only the Open Interface calls used while recovering Safe mode."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[int, ...]]] = []

    def drive_direct(self, left: int, right: int) -> None:
        self.calls.append(("drive_direct", (left, right)))

    def start(self) -> None:
        self.calls.append(("start", ()))

    def safe(self) -> None:
        self.calls.append(("safe", ()))


def test_same_drive_command_recovers_after_robot_becomes_passive() -> None:
    create = _FakeCreate2()
    robot = RoombaInterface()
    robot._bot = create  # type: ignore[assignment]
    robot.passivo = False
    robot.drive(100, 100)

    robot.set_passive()
    robot.drive(100, 100)

    assert create.calls == [
        ("drive_direct", (100, 100)),
        ("start", ()),
        ("safe", ()),
        ("drive_direct", (100, 100)),
    ]
