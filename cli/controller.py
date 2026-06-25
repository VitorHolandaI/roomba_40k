"""Local keyboard controller for the Roomba."""

import time
from typing import Optional

from cli.terminal import CYAN, GREEN, YELLOW, TerminalCbreak, color, controls_text
from cli.terminal import get_key, status_line
from roomba.battery import read_battery
from roomba.drive import MAX_VEL, MIN_VEL
from roomba.interface import RoombaInterface
from roomba.types import BatteryInfo

TIMEOUT = 0.15
BATTERY_UPDATE = 2.0
SPEED_STEP = 25


class CliController:
    """Runs the local keyboard loop using the shared robot interface."""

    def __init__(self, robot: RoombaInterface) -> None:
        self.robot = robot
        self.speed = 150
        self.moving = False
        self.last_action = time.time()
        self.battery_info: Optional[BatteryInfo] = None
        self.last_battery_read = 0.0

    def run(self) -> None:
        print(color("\n🤖 Conectando ao Roomba...\n", CYAN))
        self.robot.connect()
        try:
            with TerminalCbreak():
                print(controls_text())
                self._show_status("Parado")
                self._run_loop()
        finally:
            self._shutdown()

    def _run_loop(self) -> None:
        while True:
            now = time.time()
            self._refresh_battery(now)
            key = get_key()
            if key is not None and self._handle_key(key.lower(), now):
                break
            self._stop_if_stale(now)
            time.sleep(0.01)

    def _handle_key(self, key: str, now: float) -> bool:
        self.last_action = now
        movement = {
            "w": (self.speed, self.speed, "Frente"),
            "s": (-self.speed, -self.speed, "Ré"),
            "a": (-self.speed, self.speed, "Esquerda"),
            "d": (self.speed, -self.speed, "Direita"),
        }
        if key in movement:
            left, right, action = movement[key]
            self._drive(left, right, action)
        elif key == "+":
            self._change_speed(SPEED_STEP)
        elif key == "-":
            self._change_speed(-SPEED_STEP)
        elif key == " ":
            self._stop()
        elif key == "b":
            self._dock()
        return key == "q"

    def _drive(self, left: int, right: int, action: str) -> None:
        self.robot.drive(left, right)
        self.moving = True
        self._show_status(action)

    def _change_speed(self, delta: int) -> None:
        self.speed = max(MIN_VEL, min(MAX_VEL, self.speed + delta))
        self._show_status("Movendo" if self.moving else "Parado")

    def _stop(self) -> None:
        self.robot.drive_stop()
        self.moving = False
        self._show_status("Parado")

    def _dock(self) -> None:
        self.moving = False
        self.robot.seek_dock()
        self._show_status("Dock")

    def _refresh_battery(self, now: float) -> None:
        if now - self.last_battery_read < BATTERY_UPDATE:
            return
        self.battery_info = read_battery(self.robot)
        self.last_battery_read = now
        self._show_status("Movendo" if self.moving else "Parado")

    def _stop_if_stale(self, now: float) -> None:
        if not self.moving or now - self.last_action <= TIMEOUT:
            return
        self.robot.drive_stop()
        self.moving = False
        self._show_status("Parado")

    def _show_status(self, action: str) -> None:
        print(status_line(action, self.speed, self.battery_info), end="", flush=True)

    def _shutdown(self) -> None:
        print("\n")
        print(color("Parando o robô...", YELLOW))
        self.robot.shutdown()
        print(color("Conexão encerrada.", GREEN))
