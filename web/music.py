#!/usr/bin/env python3
"""Player de música para o boombox-roomba.

Toca MP3s de uma pasta no alto-falante ligado ao Raspberry Pi, usando o
mpg123 em modo remoto (`-R`): um único processo persistente que recebe
comandos por stdin (LOAD/PAUSE/STOP) e avisa o fim da faixa pelo stdout
(`@P 0`), o que usamos para avançar sozinho (reprodução sequencial).

Leve o suficiente para o RPi 3B+. Toda a I/O de subprocesso fica numa
thread dedicada; a camada web apenas chama os métodos (play/pause/...).
"""

import os
import glob
import shutil
import threading
import subprocess


class MusicPlayer:
    """Controla o mpg123 em modo remoto e a playlist sequencial."""

    def __init__(self, music_dir, alsa_dev=None, on_change=None):
        self.music_dir = os.path.expanduser(music_dir)
        self.alsa_dev = alsa_dev
        # Callback chamado (sem args) sempre que o estado muda, para broadcast.
        self.on_change = on_change

        self.lock = threading.Lock()
        self.proc = None

        # Playlist (caminhos absolutos) e índice da faixa atual.
        self.playlist = []
        self.index = -1

        self.playing = False
        self.paused = False

        # Suprime o auto-avanço no @P 0 disparado por LOAD/STOP (não é fim
        # natural de faixa).
        self._suppress_advance = False

        self.available = shutil.which("mpg123") is not None

        self._scan()

    # ── playlist ────────────────────────────────────────────────────────────

    def _scan(self):
        """(Re)varre a pasta por .mp3 (recursivo), ordenado por nome."""
        files = []
        if os.path.isdir(self.music_dir):
            for pat in ("*.mp3", "*.MP3"):
                files += glob.glob(
                    os.path.join(self.music_dir, "**", pat), recursive=True
                )
        self.playlist = sorted(set(files))

    # ── ciclo de vida do processo ─────────────────────────────────────────────

    def start(self):
        """Sobe o mpg123 em modo remoto e a thread leitora de stdout."""
        if not self.available:
            print("[music] AVISO: mpg123 não encontrado; player desabilitado.")
            return
        cmd = ["mpg123", "-R"]
        if self.alsa_dev == "dummy":
            # Saída nula para dev/teste (sem hardware de áudio).
            cmd += ["-o", "dummy"]
        elif self.alsa_dev:
            cmd += ["-a", self.alsa_dev]
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            print(f"[music] falha ao iniciar mpg123: {e}")
            self.available = False
            return
        # Silencia as linhas de frame (@F ...) para não inundar o pipe.
        self._send("SILENCE")
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()
        print(
            f"[music] mpg123 pronto | {len(self.playlist)} faixa(s) em "
            f"{self.music_dir} | saída: {self.alsa_dev or 'padrão'}"
        )

    def stop_proc(self):
        if self.proc is not None:
            try:
                self._send("QUIT")
                self.proc.terminate()
            except Exception:
                pass

    def _send(self, cmd):
        """Escreve um comando no stdin do mpg123 (thread-safe)."""
        p = self.proc
        if p is None or p.stdin is None:
            return
        try:
            p.stdin.write(cmd + "\n")
            p.stdin.flush()
        except Exception:
            pass

    # ── thread leitora: detecta fim de faixa para avançar ─────────────────────

    def _reader(self):
        p = self.proc
        for line in p.stdout:
            line = line.strip()
            if not line.startswith("@P"):
                continue
            # @P 0 = parado/terminado, @P 1 = pausado, @P 2 = tocando.
            code = line[2:].strip()
            advance = False
            with self.lock:
                if code == "0":
                    if self._suppress_advance:
                        self._suppress_advance = False
                    elif self.playing:
                        # Fim natural da faixa -> próxima (sequencial).
                        advance = True
                    else:
                        self.playing = False
                        self.paused = False
                elif code == "1":
                    self.paused = True
                elif code == "2":
                    self.playing = True
                    self.paused = False
            if advance:
                self.next()
            else:
                self._notify()
        # Processo terminou.
        with self.lock:
            self.playing = False
            self.paused = False
        self._notify()

    # ── comandos (chamados pela camada web) ───────────────────────────────────

    def _load_index(self, idx):
        """Carrega e toca a faixa idx. Deve ser chamado COM o lock fora."""
        if not self.playlist:
            return
        idx = idx % len(self.playlist)
        with self.lock:
            self.index = idx
            self.playing = True
            self.paused = False
            self._suppress_advance = True
            path = self.playlist[idx]
        self._send("LOAD " + path)
        self._notify()

    def play(self, idx=None):
        if not self.available or not self.playlist:
            return
        if idx is None:
            with self.lock:
                paused = self.paused
                cur = self.index
            if paused:
                self._send("PAUSE")   # retoma
                return
            idx = cur if cur >= 0 else 0
        self._load_index(idx)

    def pause(self):
        """Alterna pausa/retomada (mpg123 PAUSE é toggle)."""
        if not self.available:
            return
        with self.lock:
            if not self.playing:
                return
        self._send("PAUSE")

    def stop(self):
        if not self.available:
            return
        with self.lock:
            self.playing = False
            self.paused = False
            self._suppress_advance = True
        self._send("STOP")
        self._notify()

    def next(self):
        if not self.available or not self.playlist:
            return
        with self.lock:
            nxt = (self.index + 1) % len(self.playlist)
        self._load_index(nxt)

    def prev(self):
        if not self.available or not self.playlist:
            return
        with self.lock:
            prv = (self.index - 1) % len(self.playlist)
        self._load_index(prv)

    def rescan(self):
        with self.lock:
            self._scan()
        self._notify()

    # ── estado p/ broadcast ────────────────────────────────────────────────────

    def state(self):
        with self.lock:
            track = (
                os.path.basename(self.playlist[self.index])
                if 0 <= self.index < len(self.playlist)
                else None
            )
            return {
                "type": "music",
                "available": self.available,
                "playing": self.playing,
                "paused": self.paused,
                "index": self.index,
                "total": len(self.playlist),
                "track": track,
                "files": [os.path.basename(p) for p in self.playlist],
            }

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass
