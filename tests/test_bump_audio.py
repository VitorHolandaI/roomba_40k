"""Bump sound-effect player tests — no audio hardware dependency."""

import threading
from pathlib import Path

from pytest import MonkeyPatch

from media import bump_audio as bump_module
from media.bump_audio import BumpAudioPlayer


class FakeEffectProcess:
    """Fake mpg123 process; `done` drives poll() to simulate end of audio."""

    def __init__(self, argv: list[str], done: bool = False) -> None:
        self.argv = argv
        self._done = done
        self.terminated = False

    def poll(self) -> object:
        return 0 if self._done else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        self._done = True
        return 0


def _player_with_spawn_capture(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    spawns: list[list[str]],
    done: bool = False,
) -> BumpAudioPlayer:
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "b.mp3").write_bytes(b"x")
    monkeypatch.setattr(bump_module.shutil, "which", lambda _n: "/usr/bin/mpg123")

    def fake_popen(argv: list[str], **_kwargs: object) -> FakeEffectProcess:
        spawns.append(argv)
        return FakeEffectProcess(argv, done=done)

    monkeypatch.setattr(bump_module.subprocess, "Popen", fake_popen)
    return BumpAudioPlayer(str(tmp_path), alsa_dev="dummy")


def test_trigger_plays_whole_folder_in_sequence(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    player = _player_with_spawn_capture(monkeypatch, tmp_path, spawns)

    player.trigger()

    assert len(spawns) == 1
    argv = spawns[0]
    assert argv[0] == "mpg123"
    assert argv[-2].endswith("a.mp3")
    assert argv[-1].endswith("b.mp3")


def test_trigger_ignored_while_already_playing(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    player = _player_with_spawn_capture(monkeypatch, tmp_path, spawns, done=False)

    player.trigger()
    player.trigger()  # sequence still playing -> debounced

    assert len(spawns) == 1


def test_trigger_plays_again_after_sequence_ends(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    player = _player_with_spawn_capture(monkeypatch, tmp_path, spawns, done=True)

    player.trigger()
    player.trigger()  # previous proc finished -> plays again

    assert len(spawns) == 2


def test_trigger_noop_without_audio_files(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    monkeypatch.setattr(bump_module.shutil, "which", lambda _n: "/usr/bin/mpg123")
    monkeypatch.setattr(
        bump_module.subprocess, "Popen", lambda argv, **_k: spawns.append(argv)
    )
    BumpAudioPlayer(str(tmp_path / "empty"), alsa_dev="dummy").trigger()

    assert spawns == []


def test_suspend_stops_effects_and_blocks_new_triggers(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    player = _player_with_spawn_capture(monkeypatch, tmp_path, spawns)
    player.trigger()

    player.suspend()
    player.trigger()

    assert player._proc is None
    assert len(spawns) == 1
    player.resume()
    player.trigger()
    assert len(spawns) == 2


def test_suspend_waits_for_trigger_spawn_race(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    spawns: list[list[str]] = []
    player = _player_with_spawn_capture(monkeypatch, tmp_path, spawns)
    original_spawn = player._spawn
    spawn_started = threading.Event()
    release_spawn = threading.Event()

    def delayed_spawn(files: list[str]):
        spawn_started.set()
        release_spawn.wait(timeout=1.0)
        return original_spawn(files)

    monkeypatch.setattr(player, "_spawn", delayed_spawn)
    trigger_thread = threading.Thread(target=player.trigger)
    trigger_thread.start()
    assert spawn_started.wait(timeout=1.0)
    suspend_thread = threading.Thread(target=player.suspend)
    suspend_thread.start()
    release_spawn.set()
    trigger_thread.join(timeout=1.0)
    suspend_thread.join(timeout=1.0)

    assert player.suspended is True
    assert player._proc is None
