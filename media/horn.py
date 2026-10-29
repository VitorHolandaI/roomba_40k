"""Buzina do boombox-roomba: sintetiza o som e toca via ``aplay``.

O áudio é gerado em memória (nenhum arquivo para versionar) e enviado ao
stdin de um ``aplay`` descartável por buzinada. Enquanto uma buzinada toca,
novos pedidos são ignorados para não empilhar processos no RPi 3B+.
"""

import math
import shutil
import struct
import subprocess
import threading
from typing import Optional

SAMPLE_RATE = 22050
HORN_SECONDS = 0.9
# Par de tons separados por ~terça menor, como as buzinas de carro.
HORN_TONES_HZ = (400.0, 500.0)
# A saturação eleva o RMS sem passar do fundo de escala: soa mais alto que
# um seno puro no mesmo pico, que é o único "ganho" possível em PCM de 16 bits.
CLIP_DRIVE = 3.0
PEAK = 0.95 * 32767
FADE_SECONDS = 0.02


def _horn_sample(t: float) -> float:
    """Um instante da buzina: tons + 3º harmônico, saturados em [-1, 1]."""
    mix = 0.0
    for tone in HORN_TONES_HZ:
        mix += math.sin(2 * math.pi * tone * t)
        mix += 0.5 * math.sin(2 * math.pi * 3 * tone * t)
    return math.tanh(CLIP_DRIVE * mix / len(HORN_TONES_HZ))


def _envelope(index: int, total: int, fade: int) -> float:
    """Rampa linear de entrada/saída para evitar estalo no começo e no fim."""
    return min(1.0, index / fade, (total - 1 - index) / fade)


def synthesize_horn_pcm(
    seconds: float = HORN_SECONDS, rate: int = SAMPLE_RATE
) -> bytes:
    """PCM mono S16_LE da buzina. Ex.: ``len(synthesize_horn_pcm(1.0, 8000))``."""
    total = int(seconds * rate)
    fade = max(1, int(FADE_SECONDS * rate))
    if total < 2 * fade:
        raise ValueError(
            f"buzina curta demais: {seconds!r}s a {rate!r}Hz, "
            f"esperado >= {2 * FADE_SECONDS}s"
        )
    samples = [
        int(PEAK * _horn_sample(i / rate) * _envelope(i, total, fade))
        for i in range(total)
    ]
    return struct.pack(f"<{total}h", *samples)


class HornPlayer:
    """Buzina sob demanda no alto-falante ligado ao Pi.

    Exemplo::

        horn = HornPlayer("plughw:1,0")
        horn.honk()  # False se já está buzinando ou sem aplay
    """

    def __init__(self, alsa_dev: str | None, pcm: bytes | None = None) -> None:
        self.alsa_dev = alsa_dev
        self.available = shutil.which("aplay") is not None
        self._pcm = synthesize_horn_pcm() if pcm is None else pcm
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None

    def honk(self) -> bool:
        """Dispara a buzina; devolve False se ignorada ou se o aplay falhou."""
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            if not self.available or running:
                return False
            self._proc = self._spawn()
            return self._proc is not None

    def _command(self) -> list[str]:
        cmd = ["aplay", "-q"]
        if self.alsa_dev == "dummy":
            cmd += ["-D", "null"]  # saída nula p/ dev/teste (sem hardware)
        elif self.alsa_dev:
            cmd += ["-D", self.alsa_dev]
        return cmd + ["-t", "raw", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1"]

    def _spawn(self) -> Optional["subprocess.Popen[bytes]"]:
        cmd = self._command()
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            print(f"[horn] falha ao iniciar aplay ({cmd!r}): {exc}")
            self.available = False
            return None
        return self._feed(proc, cmd)

    def _feed(
        self, proc: "subprocess.Popen[bytes]", cmd: list[str]
    ) -> Optional["subprocess.Popen[bytes]"]:
        # ~40 KB cabem no buffer do pipe, então o write não bloqueia.
        if proc.stdin is None:
            raise RuntimeError(f"aplay sem stdin apesar de PIPE: {cmd!r}")
        try:
            proc.stdin.write(self._pcm)
            proc.stdin.close()
        except OSError as exc:
            print(f"[horn] aplay saiu antes de receber o som ({cmd!r}): {exc}")
            return None
        return proc
