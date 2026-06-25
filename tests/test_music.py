"""Music player tests — no audio hardware dependency."""

import importlib
from pathlib import Path
from typing import Callable

from pytest import MonkeyPatch

from media import music as music_module
from media.music import MusicPlayer
from web import server as server_module


class FakeMusicStdin:
    """Capture mpg123 remote commands written by MusicPlayer."""

    def __init__(self, commands: list[bytes]) -> None:
        self.commands = commands

    def write(self, raw: bytes) -> None:
        self.commands.append(raw)

    def flush(self) -> None:
        pass


class FakeMusicProcess:
    """Fake process for mpg123 remote mode."""

    def __init__(self, commands: list[bytes]) -> None:
        self.stdin = FakeMusicStdin(commands)
        self.stdout: list[bytes] = []

    def terminate(self) -> None:
        pass


class FakeMusicThread:
    """Avoid starting a real reader thread in startup tests."""

    def __init__(self, target: Callable[[], None], daemon: bool) -> None:
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        pass


def _started_music_commands(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    autoplay: bool,
) -> list[bytes]:
    commands: list[bytes] = []
    (tmp_path / "intro.mp3").write_bytes(b"fake mp3")
    monkeypatch.setattr(music_module.shutil, "which", lambda _name: "/usr/bin/mpg123")
    monkeypatch.setattr(music_module.threading, "Thread", FakeMusicThread)
    monkeypatch.setattr(
        music_module.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FakeMusicProcess(commands),
    )
    MusicPlayer(str(tmp_path), alsa_dev="dummy", autoplay=autoplay).start()
    return commands


def test_music_player_start_does_not_load_song_without_autoplay(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands = _started_music_commands(monkeypatch, tmp_path, autoplay=False)

    assert not any(command.startswith(b"LOAD ") for command in commands)


def test_music_player_start_loads_song_with_autoplay(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands = _started_music_commands(monkeypatch, tmp_path, autoplay=True)

    assert any(command.startswith(b"LOAD ") for command in commands)


def test_server_music_autoplay_is_opt_in(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MUSIC_AUTOPLAY", raising=False)
    assert importlib.reload(server_module).MUSIC_AUTOPLAY is False

    monkeypatch.setenv("MUSIC_AUTOPLAY", "1")
    assert importlib.reload(server_module).MUSIC_AUTOPLAY is True

    monkeypatch.delenv("MUSIC_AUTOPLAY", raising=False)
    importlib.reload(server_module)
