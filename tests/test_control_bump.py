"""ControlThread reacts to bumps by triggering sound effects."""

import time

from tests.fakes import FakeRoomba
from web.control_thread import ControlThread
from web.shared_state import SharedState


class _FakeBumps:
    def __init__(self, left: bool, right: bool) -> None:
        self.bump_left = left
        self.bump_right = right
        self.wheeldrop_left = False
        self.wheeldrop_right = False


class _FakeSensors:
    def __init__(
        self,
        left: bool,
        right: bool,
        cliff_front_left: bool = False,
        open_interface_mode: int = 2,
    ) -> None:
        self.bumps_wheeldrops = _FakeBumps(left, right)
        self.cliff_left = False
        self.cliff_front_left = cliff_front_left
        self.cliff_front_right = False
        self.cliff_right = False
        self.open_interface_mode = open_interface_mode


class _SequenceBot:
    """Returns a scripted list of sensor packets, one per get_sensors call."""

    def __init__(self, packets: list[object]) -> None:
        self._packets = packets
        self._i = 0
        self.passive_marks = 0

    def get_sensors(self) -> object:
        packet = self._packets[min(self._i, len(self._packets) - 1)]
        self._i += 1
        return packet

    def set_passive(self) -> None:
        self.passive_marks += 1


class _CountingEffects:
    def __init__(self) -> None:
        self.triggers = 0

    def trigger(self) -> None:
        self.triggers += 1


def _control(bot: object, effects: object) -> ControlThread:
    control = ControlThread(SharedState(), effects=effects)  # type: ignore[arg-type]
    control.bot = bot  # type: ignore[assignment]
    return control


def test_bump_triggers_effect_once_per_hit() -> None:
    effects = _CountingEffects()
    bot = _SequenceBot([_FakeSensors(True, False), _FakeSensors(True, False)])
    control = _control(bot, effects)

    control._poll_bump_audio()
    control._poll_bump_audio()  # still held -> no second trigger

    assert effects.triggers == 1


def test_no_bump_no_effect() -> None:
    effects = _CountingEffects()
    bot = _SequenceBot([_FakeSensors(False, False)])
    control = _control(bot, effects)

    control._poll_bump_audio()

    assert effects.triggers == 0


def test_missing_effects_is_safe() -> None:
    bot = _SequenceBot([_FakeSensors(True, False)])
    control = _control(bot, None)

    control._poll_bump_audio()  # must not raise


def test_bump_state_published_to_shared_state() -> None:
    control = _control(_SequenceBot([_FakeSensors(True, False)]), None)

    control._poll_bump_audio()

    bumps = control.state.get_bumps()
    assert (bumps["left"], bumps["right"]) == (True, False)


def test_no_sensors_publishes_off() -> None:
    control = _control(_SequenceBot([None]), None)

    control._poll_bump_audio()

    assert control.state.get_bumps()["left"] is False


def test_cliff_state_published() -> None:
    bot = _SequenceBot([_FakeSensors(False, False, cliff_front_left=True)])
    control = _control(bot, None)

    control._poll_bump_audio()

    assert control.state.get_bumps()["cliff_front_left"] is True


def test_passive_sensor_mode_marks_robot_for_recovery() -> None:
    bot = _SequenceBot([_FakeSensors(False, False, open_interface_mode=1)])
    control = _control(bot, None)

    control._poll_bump_audio()

    assert bot.passive_marks == 1


def test_manual_cliff_blocks_forward_but_allows_reverse() -> None:
    robot = FakeRoomba()
    control = ControlThread(SharedState())
    control.bot = robot  # type: ignore[assignment]
    control._publish_bumps(_FakeSensors(False, False, cliff_front_left=True))

    control.state.set_drive(100, 100)
    control._manual_step(time.time())
    control.state.set_drive(-100, -100)
    control._manual_step(time.time())

    assert robot.calls == [
        ("drive", (0, 0)),
        ("drive", (-100, -100)),
    ]
