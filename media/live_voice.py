"""Play low-latency browser PCM directly through ALSA."""

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from typing import Protocol, cast


VOICE_SAMPLE_RATE = 16000
VOICE_BUFFER_US = 80000
VOICE_PERIOD_US = 20000


class VoiceInput(Protocol):
    """Writable stdin exposed by an asyncio subprocess."""

    def write(self, chunk: bytes) -> None: ...

    async def drain(self) -> None: ...

    def close(self) -> None: ...


class VoiceProcess(Protocol):
    """Subset of asyncio.subprocess.Process used by the player."""

    @property
    def stdin(self) -> VoiceInput | None: ...

    returncode: int | None

    async def wait(self) -> int: ...

    def kill(self) -> None: ...


ProcessFactory = Callable[..., Awaitable[VoiceProcess]]
DEFAULT_PROCESS_FACTORY = cast(ProcessFactory, asyncio.create_subprocess_exec)


class LiveVoicePlayer:
    """Own one exclusive ``aplay`` process for live mono PCM.

    Example: ``await LiveVoicePlayer('plughw:1,0').start()``.
    """

    def __init__(
        self,
        alsa_dev: str,
        process_factory: ProcessFactory = DEFAULT_PROCESS_FACTORY,
    ) -> None:
        self.alsa_dev = alsa_dev
        self.process_factory = process_factory
        self.process: VoiceProcess | None = None
        self._starting = False
        self._stopping = False
        self._lifecycle_lock = asyncio.Lock()
        self.available = shutil.which("aplay") is not None

    @property
    def playing(self) -> bool:
        """Return whether a live voice stream currently owns ALSA."""
        process_running = self.process is not None and self.process.returncode is None
        return self._starting or self._stopping or process_running

    async def start(self) -> bool:
        """Start aplay, returning false when unavailable or already busy."""
        async with self._lifecycle_lock:
            return await self._start_process()

    async def _start_process(self) -> bool:
        if not self.available or self.playing:
            return False
        self._starting = True
        try:
            process = await self.process_factory(
                *self.command(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self.process = process
            await asyncio.sleep(0.02)
            if process.returncode is not None:
                self.process = None
                return False
        except OSError as exc:
            print(f"[voice] falha ao iniciar aplay em {self.alsa_dev!r}: {exc}")
            return False
        finally:
            self._starting = False
        return True

    async def write(self, chunk: bytes) -> bool:
        """Write one PCM chunk, applying subprocess backpressure."""
        process = self.process
        if process is None or process.returncode is not None or process.stdin is None:
            return False
        try:
            process.stdin.write(chunk)
            await process.stdin.drain()
        except (ConnectionError, OSError):
            return False
        return True

    async def stop(self) -> None:
        """Close stdin and guarantee that the current aplay exits."""
        async with self._lifecycle_lock:
            process = self.process
            if process is None:
                return
            self._stopping = True
            cleanup = asyncio.create_task(self._finish_process(process))
            cleanup.add_done_callback(lambda _task: self._clear_process(process))
            await asyncio.shield(cleanup)

    async def _finish_process(self, process: VoiceProcess) -> None:
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            process.kill()
            try:
                await asyncio.wait_for(process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                print("[voice] aplay não encerrou após kill", flush=True)

    def _clear_process(self, process: VoiceProcess) -> None:
        if self.process is process:
            self.process = None
        self._stopping = False

    def command(self) -> list[str]:
        """Build the raw PCM aplay command for the configured ALSA device."""
        return [
            "aplay",
            "-q",
            "-N",
            "-D",
            self.alsa_dev,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(VOICE_SAMPLE_RATE),
            "-B",
            str(VOICE_BUFFER_US),
            "-F",
            str(VOICE_PERIOD_US),
            "-c",
            "1",
        ]
