"""Live voice player tests without ALSA hardware."""

import asyncio
from typing import Any

from pytest import MonkeyPatch

from media import live_voice
from media.live_voice import LiveVoicePlayer


class FakeVoiceStdin:
    """Capture PCM writes sent to aplay."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.closed = False

    def write(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class FakeVoiceProcess:
    """Represent one running aplay process."""

    def __init__(self) -> None:
        self.stdin = FakeVoiceStdin()
        self.returncode: int | None = None
        self.killed = False

    async def wait(self) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


class FakeVoiceProcessFactory:
    """Capture the aplay command and return a named fake process."""

    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.processes: list[FakeVoiceProcess] = []

    async def __call__(self, *command: str, **_kwargs: Any) -> FakeVoiceProcess:
        await asyncio.sleep(0)
        process = FakeVoiceProcess()
        self.commands.append(command)
        self.processes.append(process)
        return process


class DelayedVoiceProcessFactory(FakeVoiceProcessFactory):
    """Hold process creation so start/stop lifecycle races are reproducible."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, *command: str, **kwargs: Any) -> FakeVoiceProcess:
        self.started.set()
        await self.release.wait()
        return await super().__call__(*command, **kwargs)


def test_live_voice_streams_pcm_and_closes_aplay(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(live_voice.shutil, "which", lambda _name: "/usr/bin/aplay")
    factory = FakeVoiceProcessFactory()
    player = LiveVoicePlayer("plughw:1,0", process_factory=factory)

    async def exercise() -> None:
        assert await player.start() is True
        assert await player.start() is False
        assert await player.write(b"\x01\x02") is True
        await player.stop()

    asyncio.run(exercise())

    assert factory.commands[0][:2] == ("aplay", "-q")
    assert "-D" in factory.commands[0]
    assert "-N" in factory.commands[0]
    assert factory.commands[0][factory.commands[0].index("-B") + 1] == "80000"
    assert "16000" in factory.commands[0]
    assert factory.processes[0].stdin.chunks == [b"\x01\x02"]
    assert factory.processes[0].stdin.closed is True
    assert player.playing is False


def test_live_voice_is_unavailable_without_aplay(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(live_voice.shutil, "which", lambda _name: None)
    player = LiveVoicePlayer("plughw:1,0", process_factory=FakeVoiceProcessFactory())

    assert player.available is False
    assert asyncio.run(player.start()) is False


def test_live_voice_reserves_aplay_during_concurrent_start(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_voice.shutil, "which", lambda _name: "/usr/bin/aplay")
    factory = FakeVoiceProcessFactory()
    player = LiveVoicePlayer("plughw:1,0", process_factory=factory)

    async def start_twice() -> list[bool]:
        return list(await asyncio.gather(player.start(), player.start()))

    assert asyncio.run(start_twice()) == [True, False]
    assert len(factory.processes) == 1


def test_live_voice_stop_waits_for_start_in_progress(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_voice.shutil, "which", lambda _name: "/usr/bin/aplay")
    factory = DelayedVoiceProcessFactory()
    player = LiveVoicePlayer("plughw:1,0", process_factory=factory)

    async def start_then_stop() -> None:
        start_task = asyncio.create_task(player.start())
        await factory.started.wait()
        stop_task = asyncio.create_task(player.stop())
        factory.release.set()
        assert await start_task is True
        await stop_task

    asyncio.run(start_then_stop())

    assert player.playing is False
    assert factory.processes[0].stdin.closed is True
