"""Dedicated thread that owns the serial connection and the auto-pilot."""

import time
import threading

from roomba.interface import RoombaInterface
from roomba.auto import AutoPilot
from roomba.battery import read_battery
from roomba.drive import is_drive_stale
from web.constants import TIMEOUT, BATTERY_INTERVAL, LOOP_PERIOD
from web.shared_state import SharedState


class ControlThread(threading.Thread):
    """Blocking control loop running in a dedicated thread."""

    def __init__(self, state: SharedState, port: str = "/dev/ttyUSB0") -> None:
        super().__init__(daemon=True)
        self.state = state
        self.port = port
        self.bot = RoombaInterface(port)
        self.auto = AutoPilot()
        self._running = threading.Event()
        self._running.set()
        self._sent_clean = False

    def run(self) -> None:
        self.bot.connect()
        last_battery = 0.0

        while self._running.is_set():
            now = time.time()

            if self.state.take_dock_request():
                self.bot.seek_dock()
                continue

            self._sync_clean_motors()

            if self.state.get_auto():
                self._auto_step(now)
            else:
                self._manual_step(now)

            if now - last_battery >= BATTERY_INTERVAL:
                self.state.set_battery(read_battery(self.bot))
                last_battery = now

            time.sleep(LOOP_PERIOD)

        self._shutdown()

    def _sync_clean_motors(self) -> None:
        desired = self.state.get_clean_motors()
        if desired != self._sent_clean:
            self.bot.set_clean_motors(desired)
            self._sent_clean = desired

    def _manual_step(self, now: float) -> None:
        left, right, last_update = self.state.snapshot_target()
        if is_drive_stale(last_update, now, timeout=TIMEOUT):
            left = 0
            right = 0
        self.bot.drive(left, right)

    def _auto_step(self, now: float) -> None:
        sensors = self.bot.get_sensors()
        decision = self.auto.decide(sensors, self.state.get_speed(), now)
        if decision.collision:
            self.bot.set_passive()
        self.bot.drive(decision.left, decision.right)

    def stop(self) -> None:
        self._running.clear()

    def _shutdown(self) -> None:
        self.bot.shutdown()
