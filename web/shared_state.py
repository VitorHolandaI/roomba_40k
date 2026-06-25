"""Thread-safe state shared between asyncio WS handlers and the control thread."""

import time
import threading
from typing import Optional

from roomba.drive import MIN_VEL, MAX_VEL
from roomba.types import BatteryInfo


class SharedState:
    """Desired target + telemetry, protected by a lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._target_left = 0
        self._target_right = 0
        self._last_update = 0.0
        self._dock_requested = False
        self._auto_mode = False
        self._speed = 150
        self._clean_motors_on = False
        self._battery: Optional[BatteryInfo] = None

    # -- web layer writes -------------------------------------------------------

    def set_drive(self, left: int, right: int) -> None:
        with self._lock:
            self._target_left = int(left)
            self._target_right = int(right)
            self._last_update = time.time()
            self._auto_mode = False

    def request_stop(self) -> None:
        with self._lock:
            self._target_left = 0
            self._target_right = 0
            self._last_update = time.time()
            self._auto_mode = False

    def request_dock(self) -> None:
        with self._lock:
            self._target_left = 0
            self._target_right = 0
            self._dock_requested = True
            self._auto_mode = False

    def set_auto(self, on: bool) -> None:
        with self._lock:
            self._auto_mode = bool(on)
            if not on:
                self._target_left = 0
                self._target_right = 0

    def get_auto(self) -> bool:
        with self._lock:
            return self._auto_mode

    def set_speed(self, v: int) -> None:
        with self._lock:
            self._speed = max(MIN_VEL, min(MAX_VEL, int(v)))

    def get_speed(self) -> int:
        with self._lock:
            return self._speed

    def set_clean_motors(self, on: bool) -> None:
        with self._lock:
            self._clean_motors_on = bool(on)

    def get_clean_motors(self) -> bool:
        with self._lock:
            return self._clean_motors_on

    # -- control thread reads ---------------------------------------------------

    def snapshot_target(self) -> tuple[int, int, float]:
        with self._lock:
            return self._target_left, self._target_right, self._last_update

    def take_dock_request(self) -> bool:
        with self._lock:
            req = self._dock_requested
            self._dock_requested = False
            return req

    def set_battery(self, info: Optional[BatteryInfo]) -> None:
        with self._lock:
            self._battery = info

    def get_battery(self) -> dict[str, object]:
        with self._lock:
            if self._battery is None:
                return {"type": "battery", "ok": False}
            return self._battery.to_dict()
