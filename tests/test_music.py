"""Music player tests — no audio hardware dependency."""

import importlib
import ssl
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
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float) -> int:
        return 0

    def kill(self) -> None:
        self.terminated = True


class FakeMusicThread:
    """Avoid starting a real reader thread in startup tests."""

    def __init__(self, target: Callable[[], None], daemon: bool) -> None:
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        pass

    def join(self, timeout: float) -> None:
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


def test_music_player_suspend_releases_and_restores_process(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    processes: list[FakeMusicProcess] = []
    monkeypatch.setattr(music_module.shutil, "which", lambda _name: "/usr/bin/mpg123")
    monkeypatch.setattr(music_module.threading, "Thread", FakeMusicThread)

    def fake_popen(*_args: object, **_kwargs: object) -> FakeMusicProcess:
        process = FakeMusicProcess([])
        processes.append(process)
        return process

    monkeypatch.setattr(music_module.subprocess, "Popen", fake_popen)
    player = MusicPlayer(str(tmp_path), alsa_dev="dummy")
    player.start()

    player.suspend()
    assert processes[0].terminated is True
    assert player.proc is None
    player.resume()

    assert len(processes) == 2
    assert player.proc is processes[1]


def _player_with_fake_events(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    events: list[bytes],
) -> tuple[MusicPlayer, list[bytes]]:
    """Two-track player whose mpg123 stdout replays `events` in order."""
    commands: list[bytes] = []
    for name in ("a.mp3", "b.mp3"):
        (tmp_path / name).write_bytes(b"fake mp3")
    monkeypatch.setattr(music_module.shutil, "which", lambda _name: "/usr/bin/mpg123")
    player = MusicPlayer(str(tmp_path), alsa_dev="dummy")
    fake = FakeMusicProcess(commands)
    fake.stdout = events
    player.proc = fake  # type: ignore[assignment]
    return player, commands


def _loaded_names(commands: list[bytes]) -> list[str]:
    return [
        Path(c.removeprefix(b"LOAD ").strip().decode()).name
        for c in commands
        if c.startswith(b"LOAD ")
    ]


def test_track_end_advances_to_next_when_load_started_from_idle(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    # mpg123 emits only "@P 2" on LOAD (no "@P 0"), then "@P 0" at the
    # natural end. The old suppress flag swallowed that end and stalled.
    player, commands = _player_with_fake_events(
        monkeypatch, tmp_path, [b"@P 2\n", b"@P 0\n"]
    )

    player.play(0)
    player._reader()

    assert _loaded_names(commands) == ["a.mp3", "b.mp3"]


def test_track_end_advances_once_when_load_also_emits_stop_event(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Some mpg123 builds emit "@P 0" for the replaced track before "@P 2".
    player, commands = _player_with_fake_events(
        monkeypatch, tmp_path, [b"@P 0\n", b"@P 2\n", b"@P 0\n"]
    )

    player.play(0)
    player._reader()

    assert _loaded_names(commands) == ["a.mp3", "b.mp3"]


def test_stop_event_after_user_stop_does_not_advance(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    player, commands = _player_with_fake_events(
        monkeypatch, tmp_path, [b"@P 2\n", b"@P 0\n"]
    )

    player.play(0)
    player.stop()
    player._reader()

    assert _loaded_names(commands) == ["a.mp3"]


def test_server_music_autoplay_is_opt_in(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("MUSIC_AUTOPLAY", raising=False)
    assert importlib.reload(server_module).MUSIC_AUTOPLAY is False

    monkeypatch.setenv("MUSIC_AUTOPLAY", "1")
    assert importlib.reload(server_module).MUSIC_AUTOPLAY is True

    monkeypatch.delenv("MUSIC_AUTOPLAY", raising=False)
    importlib.reload(server_module)


def test_server_tls_is_optional() -> None:
    assert server_module.build_ssl_context(None, None) is None


def test_server_tls_requires_certificate_and_key() -> None:
    try:
        server_module.build_ssl_context("server.crt", None)
    except ValueError as exc:
        assert "server.crt" in str(exc)
    else:
        raise AssertionError("expected incomplete TLS configuration to fail")


def test_server_tls_loads_certificate_chain(monkeypatch: MonkeyPatch) -> None:
    loaded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ssl.SSLContext,
        "load_cert_chain",
        lambda _self, cert, key: loaded.append((cert, key)),
    )

    context = server_module.build_ssl_context("server.crt", "server.key")

    assert isinstance(context, ssl.SSLContext)
    assert loaded == [("server.crt", "server.key")]


def test_server_registers_live_voice_websocket() -> None:
    routes = {
        (route.method, getattr(route.resource, "canonical", None))
        for route in server_module.build_app().router.routes()
    }

    assert ("GET", "/voice-ws") in routes
