#!/usr/bin/env python3
"""Sensor de distância da caveira (clearance frontal/superior).

Motivo: a caveira no topo do robô aumenta a altura. Os sensores nativos do
Create2 (bump/cliff) ficam na BASE e não detectam móveis baixos (cama, sofá,
mesa) — o robô entra e a caveira trava/cai. Este sensor aponta para frente na
altura da caveira e detecta o obstáculo ANTES da batida, para mandar recuar.

Roda numa thread própria na Pi (I2C ou GPIO), independente da serial do
Create2. Degrada sem hardware: backend "none" (default) nunca bloqueia, então
o resto do sistema funciona igual até o sensor ser plugado.

Backends:
  - "none"     : stub, sem leitura (default em dev / sem hardware).
  - "vl53l0x"  : ToF I2C (recomendado). lib: adafruit-circuitpython-vl53l0x.
  - "hcsr04"   : ultrassom GPIO. lib: gpiozero (echo precisa divisor p/ 3.3V).
"""

import time
import threading


class CaveiraSensor(threading.Thread):
    """Lê a distância frontal em cm numa thread; expõe leitura em cache."""

    def __init__(self, backend="none", min_cm=20.0, poll=0.1,
                 trig_pin=23, echo_pin=24, max_cm=200.0):
        super().__init__(daemon=True)
        self.backend = (backend or "none").lower()
        self.min_cm = float(min_cm)
        self.poll = poll
        self.max_cm = max_cm
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin

        self._lock = threading.Lock()
        self._cm = None              # última distância (cm) ou None
        self._running = threading.Event()
        self._running.set()

        self._read_raw = None        # função de leitura do backend
        self.available = False
        self._setup()

    # ── inicialização do backend ──────────────────────────────────────────────

    def _setup(self):
        if self.backend == "vl53l0x":
            self._setup_vl53l0x()
        elif self.backend == "hcsr04":
            self._setup_hcsr04()
        else:
            print("[caveira] backend 'none' — sensor desabilitado (stub).")

    def _setup_vl53l0x(self):
        """ToF I2C. Mede em mm; convertemos p/ cm."""
        try:
            import board
            import busio
            import adafruit_vl53l0x
            i2c = busio.I2C(board.SCL, board.SDA)
            dev = adafruit_vl53l0x.VL53L0X(i2c)

            def read():
                mm = dev.range          # mm
                return mm / 10.0 if mm else None

            self._read_raw = read
            self.available = True
            print("[caveira] VL53L0X (I2C) pronto.")
        except Exception as e:
            print(f"[caveira] AVISO: VL53L0X indisponível ({e}); desabilitado.")

    def _setup_hcsr04(self):
        """Ultrassom GPIO via gpiozero (trigger/echo)."""
        try:
            from gpiozero import DistanceSensor
            # max_distance em metros; gpiozero já faz o timing do echo.
            dev = DistanceSensor(
                echo=self.echo_pin, trigger=self.trig_pin,
                max_distance=self.max_cm / 100.0,
            )

            def read():
                return dev.distance * 100.0   # m -> cm

            self._read_raw = read
            self.available = True
            print(
                f"[caveira] HC-SR04 (GPIO trig={self.trig_pin} "
                f"echo={self.echo_pin}) pronto."
            )
        except Exception as e:
            print(f"[caveira] AVISO: HC-SR04 indisponível ({e}); desabilitado.")

    # ── loop de leitura ────────────────────────────────────────────────────────

    def run(self):
        if not self.available:
            return
        while self._running.is_set():
            try:
                cm = self._read_raw()
            except Exception:
                cm = None
            with self._lock:
                self._cm = cm
            time.sleep(self.poll)

    def stop(self):
        self._running.clear()

    # ── consulta (rápida, do cache) ─────────────────────────────────────────────

    def distance_cm(self):
        with self._lock:
            return self._cm

    def blocked(self):
        """True se há obstáculo dentro do limiar à frente da caveira."""
        if not self.available:
            return False
        with self._lock:
            cm = self._cm
        return cm is not None and cm < self.min_cm
