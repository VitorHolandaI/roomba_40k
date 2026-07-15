"""ControlThread routes song + wake requests to the robot interface."""

from roomba.songbook import SONGBOOK, notes_for
from tests.fakes import FakeRoomba
from web.control_thread import ControlThread
from web.shared_state import SharedState


def _control(state: SharedState, bot: FakeRoomba) -> ControlThread:
    control = ControlThread(state)
    control.bot = bot  # type: ignore[assignment]
    return control


def test_song_request_plays_flattened_notes() -> None:
    state = SharedState()
    bot = FakeRoomba()
    control = _control(state, bot)
    state.request_song(2)

    control._play_requested_song()

    assert bot.calls == [("play_song", (2, notes_for(2)))]


def test_no_song_request_is_silent() -> None:
    bot = FakeRoomba()
    control = _control(SharedState(), bot)

    control._play_requested_song()

    assert bot.calls == []


def test_out_of_range_song_is_dropped() -> None:
    state = SharedState()
    bot = FakeRoomba()
    control = _control(state, bot)
    state.request_song(len(SONGBOOK))  # one past the last valid index

    control._play_requested_song()  # must not raise

    assert bot.calls == []
