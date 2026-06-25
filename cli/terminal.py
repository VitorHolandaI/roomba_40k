"""Terminal helpers for local keyboard control."""

import select
import sys
import termios
import tty
from types import TracebackType
from typing import Optional

from roomba.types import BatteryInfo

RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"
GRAY = "\033[90m"


class TerminalCbreak:
    """Temporarily put stdin in cbreak mode."""

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._old_settings: list[object] | None = None

    def __enter__(self) -> "TerminalCbreak":
        self._old_settings = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        if self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)


def color(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


def get_key() -> Optional[str]:
    """Read one key without blocking."""
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if ready:
        return sys.stdin.read(1)
    return None


def format_battery(info: Optional[BatteryInfo]) -> str:
    if info is None:
        return color("N/D", RED)
    if info.percent >= 60:
        code = GREEN
    elif info.percent >= 25:
        code = YELLOW
    else:
        code = RED
    return color(f"{info.percent:5.1f}%", code)


def _colored_action(action: str) -> str:
    if action == "Parado":
        return color(f"{action:<10}", WHITE)
    if action == "Dock":
        return color(f"{action:<10}", CYAN)
    return color(f"{action:<10}", GREEN)


def _battery_extra(info: Optional[BatteryInfo]) -> str:
    if info is None:
        return ""
    return f" | {GRAY}{info.voltage:.1f}V{RESET} | {GRAY}{info.current}mA{RESET}"


def status_line(action: str, speed: int, battery: Optional[BatteryInfo]) -> str:
    battery_text = format_battery(battery)
    speed_text = color(f"{speed:>3} mm/s", BLUE)
    return (
        f"\r{BOLD}[{_colored_action(action)}]{RESET} "
        f"Vel: {speed_text} | Bat: {battery_text}{_battery_extra(battery)}"
    )


def controls_text() -> str:
    return f"""{BOLD}
Controles
──────────
{color("W", GREEN)} = frente      {color("S", GREEN)} = ré
{color("A", GREEN)} = esquerda    {color("D", GREEN)} = direita

{color("+", BLUE)} = aumentar velocidade
{color("-", BLUE)} = diminuir velocidade

{color("B", CYAN)} = voltar para a base

{color("ESPAÇO", YELLOW)} = parar
{color("Q", RED)} = sair
{RESET}
"""
