"""ControlThread reacts to bumps by triggering sound effects."""

from web.control_thread import ControlThread
from web.shared_state import SharedState


class _FakeBumps:
    def __init__(self, left: bool, right: bool) -> None:
        self.bump_left = left
        self.bump_right = right
        self.wheeldrop_left = False
        self.wheeldrop_right = False


class _FakeSensors:
    def __init__(self, left: bool, right: bool) -> None:
        self.bumps_wheeldrops = _FakeBumps(left, right)


class _SequenceBot:
    """Returns a scripted list of sensor packets, one per get_sensors call."""

    def __init__(self, packets: list[object]) -> None:
        self._packets = packets
        self._i = 0

    def get_sensors(self) -> object:
        packet = self._packets[min(self._i, len(self._packets) - 1)]
        self._i += 1
        return packet


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
