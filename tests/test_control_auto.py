"""ControlThread autonomous safety-flow tests."""

from roomba.auto import AutoDecision
from tests.fakes import FakeRoomba
from web.control_thread import ControlThread
from web.shared_state import SharedState


class _SensorRoomba(FakeRoomba):
    def get_sensors(self) -> object:
        return object()


class _CollisionAutoPilot:
    def decide(self, sensors: object, base_speed: int, now: float) -> AutoDecision:
        return AutoDecision(100, 100, collision=True)


def test_collision_does_not_resend_previous_forward_motion() -> None:
    robot = _SensorRoomba()
    control = ControlThread(SharedState())
    control.bot = robot  # type: ignore[assignment]
    control.auto = _CollisionAutoPilot()  # type: ignore[assignment]

    control._auto_step(1.0)

    assert robot.passivo is True
    assert robot.calls == []
