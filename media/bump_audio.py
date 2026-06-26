"""Toca efeitos sonoros engraçados quando o robô bate em algo.

Cada batida dispara a sequência de áudios da pasta configurada em
``config.py``: um único ``mpg123`` toca todos os arquivos em ordem e sai.
Enquanto a sequência toca, novas batidas são ignoradas (debounce) para não
picotar o som. Leve o suficiente para o RPi 3B+ — sem processo persistente.
"""

import os
import glob
import shutil
import subprocess
from typing import List, Optional

# Extensões varridas na pasta de efeitos.
AUDIO_GLOBS = ("*.mp3", "*.MP3")


class BumpAudioPlayer:
    """Dispara a playlist de batida via um mpg123 descartável por sequência.

    Exemplo::

        effects = BumpAudioPlayer("~/roomba_sounds", alsa_dev="hw:1,0")
        effects.trigger()  # toca a pasta inteira em ordem
    """

    def __init__(self, audio_dir: str, alsa_dev: Optional[str] = None) -> None:
        self.audio_dir = os.path.expanduser(audio_dir)
        self.alsa_dev = alsa_dev
        self.available = shutil.which("mpg123") is not None
        self._proc: Optional[subprocess.Popen] = None
        self.playlist: List[str] = self._scan()
        if self.available and not self.playlist:
            print(f"[bump-audio] AVISO: nenhum .mp3 em {self.audio_dir!r}.")

    def _scan(self) -> List[str]:
        """Varre a pasta por áudios (recursivo), ordenado por nome."""
        files: List[str] = []
        if os.path.isdir(self.audio_dir):
            for pat in AUDIO_GLOBS:
                files += glob.glob(
                    os.path.join(self.audio_dir, "**", pat), recursive=True
                )
        return sorted(set(files))

    def is_playing(self) -> bool:
        """True enquanto a sequência atual ainda não terminou."""
        return self._proc is not None and self._proc.poll() is None

    def trigger(self) -> None:
        """Toca a pasta inteira; ignora se a sequência anterior ainda toca."""
        if not self.available or not self.playlist or self.is_playing():
            return
        self._proc = self._spawn(self.playlist)

    def _spawn(self, files: List[str]) -> Optional[subprocess.Popen]:
        """Sobe um mpg123 que toca todos os arquivos e sai."""
        cmd = ["mpg123", "-q"]
        if self.alsa_dev == "dummy":
            cmd += ["-o", "dummy"]  # saída nula p/ dev/teste (sem hardware)
        elif self.alsa_dev:
            cmd += ["-a", self.alsa_dev]
        cmd += files
        try:
            return subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as exc:
            print(f"[bump-audio] falha ao iniciar mpg123 ({cmd!r}): {exc}")
            self.available = False
            return None

    def stop(self) -> None:
        """Corta a sequência em andamento (ex.: no shutdown do servidor)."""
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
