"""Horn tests — no audio hardware dependency."""

import asyncio
import struct

import pytest
from pytest import MonkeyPatch

from media import horn as horn_module
from media.horn import PEAK, HornPlayer, synthesize_horn_pcm
from web.registry import WebRegistry
from web.shared_state import SharedState
from web.ws_router import dispatch_message


class FakeAplayStdin:
    """Capture the PCM bytes written to aplay."""

    def __init__(self, written: list[bytes], fail: bool = False) -> None:
        self.written = written
        self.fail = fail
        self.closed = False

    def write(self, raw: bytes) -> None:
        if self.fail:
            raise BrokenPipeError("aplay morreu")
        self.written.append(raw)

    def close(self) -> None:
        self.closed = True


class FakeAplayProcess:
    """Fake aplay: still running until `finish()` is called."""

    def __init__(self, written: list[bytes], fail: bool = False) -> None:
        self.stdin = FakeAplayStdin(written, fail)
        self.running = True

    def poll(self) -> int | None:
        return None if self.running else 0

    def finish(self) -> None:
        self.running = False


class FakeAplayLauncher:
    """Replace subprocess.Popen and remember every launch."""

    def __init__(self, fail_write: bool = False) -> None:
        self.commands: list[list[str]] = []
        self.written: list[bytes] = []
        self.processes: list[FakeAplayProcess] = []
        self.fail_write = fail_write

    def __call__(self, cmd: list[str], **_kwargs: object) -> FakeAplayProcess:
        self.commands.append(cmd)
        process = FakeAplayProcess(self.written, self.fail_write)
        self.processes.append(process)
        return process


def _player(
    monkeypatch: MonkeyPatch, launcher: FakeAplayLauncher, alsa_dev: str | None
) -> HornPlayer:
    monkeypatch.setattr(horn_module.shutil, "which", lambda _name: "/usr/bin/aplay")
    monkeypatch.setattr(horn_module.subprocess, "Popen", launcher)
    return HornPlayer(alsa_dev, pcm=b"\x01\x00" * 4)


def test_synthesized_horn_is_loud_mono_s16_without_overflow() -> None:
    pcm = synthesize_horn_pcm(seconds=0.2, rate=8000)

    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert len(samples) == 1600
    assert max(abs(s) for s in samples) > 0.8 * PEAK
    assert max(abs(s) for s in samples) <= 32767


def test_synthesized_horn_fades_in_and_out() -> None:
    pcm = synthesize_horn_pcm(seconds=0.2, rate=8000)

    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    assert samples[0] == 0
    assert abs(samples[-1]) < 0.05 * PEAK


def test_synthesize_rejects_horn_shorter_than_fade() -> None:
    with pytest.raises(ValueError, match="0.01"):
        synthesize_horn_pcm(seconds=0.01, rate=8000)


def test_honk_streams_pcm_to_aplay_on_configured_device(
    monkeypatch: MonkeyPatch,
) -> None:
    launcher = FakeAplayLauncher()
    player = _player(monkeypatch, launcher, "plughw:1,0")

    assert player.honk() is True

    assert launcher.commands[0][:4] == ["aplay", "-q", "-D", "plughw:1,0"]
    assert launcher.written == [b"\x01\x00" * 4]
    assert launcher.processes[0].stdin.closed is True


def test_honk_dummy_device_uses_alsa_null(monkeypatch: MonkeyPatch) -> None:
    launcher = FakeAplayLauncher()
    player = _player(monkeypatch, launcher, "dummy")

    player.honk()

    assert launcher.commands[0][2:4] == ["-D", "null"]


def test_honk_is_ignored_while_previous_honk_plays(
    monkeypatch: MonkeyPatch,
) -> None:
    launcher = FakeAplayLauncher()
    player = _player(monkeypatch, launcher, "dummy")
    player.honk()

    assert player.honk() is False
    launcher.processes[0].finish()
    assert player.honk() is True
    assert len(launcher.commands) == 2


def test_honk_without_aplay_returns_false(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(horn_module.shutil, "which", lambda _name: None)

    assert HornPlayer("dummy", pcm=b"").honk() is False


def test_honk_reports_false_when_aplay_dies_before_receiving_pcm(
    monkeypatch: MonkeyPatch,
) -> None:
    launcher = FakeAplayLauncher(fail_write=True)
    player = _player(monkeypatch, launcher, "dummy")

    assert player.honk() is False


class FakeHornPlayer:
    """Count honks requested through the websocket router."""

    def __init__(self) -> None:
        self.honks = 0

    def honk(self) -> bool:
        self.honks += 1
        return True


def _dispatch_horn(ws: object, registry: WebRegistry) -> None:
    asyncio.run(
        dispatch_message(
            ws,  # type: ignore[arg-type]
            registry,
            SharedState(),
            {"type": "horn"},
        )
    )


def test_driver_horn_command_triggers_honk() -> None:
    registry = WebRegistry()
    fake = FakeHornPlayer()
    registry.horn = fake  # type: ignore[assignment]
    driver = object()
    registry.driver = driver  # type: ignore[assignment]

    _dispatch_horn(driver, registry)

    assert fake.honks == 1


def test_spectator_horn_command_is_ignored() -> None:
    registry = WebRegistry()
    fake = FakeHornPlayer()
    registry.horn = fake  # type: ignore[assignment]
    registry.driver = object()  # type: ignore[assignment]

    _dispatch_horn(object(), registry)

    assert fake.honks == 0


def test_horn_command_without_horn_player_is_a_noop() -> None:
    registry = WebRegistry()
    driver = object()
    registry.driver = driver  # type: ignore[assignment]

    _dispatch_horn(driver, registry)
