"""Thin, safe wrapper around pycreate2."""

import time
from typing import Optional

from pycreate2 import Create2

from roomba.drive import clamp_velocity
from roomba.auto import _Sensors


class RoombaInterface:
    """Owns the serial connection and guards against duplicate writes."""

    def __init__(self, port: str = "/dev/ttyUSB0") -> None:
        self._port = port
        self._bot: Optional[Create2] = None
        self.passivo = False
        self._sent_left: Optional[int] = None
        self._sent_right: Optional[int] = None

    # -- lifecycle -------------------------------------------------------------

    def connect(self) -> None:
        """Open serial, start OI, enter Safe mode."""
        try:
            self._bot = Create2(self._port)
            self._bot.start()
            self._bot.safe()
            time.sleep(0.2)
        except Exception:
            self._bot = None
            Create2.__del__ = lambda self: None

    def shutdown(self) -> None:
        """Stop movement, return to Passive, close serial."""
        if self._bot is None:
            return
        try:
            self.set_clean_motors(False)
            self._bot.drive_stop()
            self._bot.start()
            self._bot.close()
        except Exception:
            pass
        Create2.__del__ = lambda self: None

    # -- mode helpers ----------------------------------------------------------

    def ensure_safe(self) -> None:
        """Re-enter Safe mode after a Passive event (e.g. Dock)."""
        if not self.passivo or self._bot is None:
            return
        try:
            self._bot.safe()
        except Exception:
            pass
        self.passivo = False

    def get_sensors(self) -> Optional[_Sensors]:
        """Read raw sensor packet; None when robot is unavailable."""
        if self._bot is None:
            return None
        try:
            # pycreate2 sensor object structurally matches _Sensors.
            return self._bot.get_sensors()  # type: ignore[return-value]
        except Exception:
            return None

    def set_passive(self) -> None:
        """Mark that the robot has dropped into Passive mode."""
        self.passivo = True

    # -- movement --------------------------------------------------------------

    def drive(self, left: int, right: int) -> None:
        """Send velocities if they differ from the last sent ones."""
        if self._bot is None:
            return

        left = clamp_velocity(left)
        right = clamp_velocity(right)

        if left == self._sent_left and right == self._sent_right:
            return

        try:
            if left == 0 and right == 0:
                self._bot.drive_stop()
            else:
                self.ensure_safe()
                self._bot.drive_direct(left, right)
        except Exception:
            return

        self._sent_left = left
        self._sent_right = right

    def drive_stop(self) -> None:
        """Convenience wrapper that zeros velocities."""
        self.drive(0, 0)

    def seek_dock(self) -> None:
        """Opcode 143: start seeking the charging dock."""
        if self._bot is None:
            self.passivo = True
            return
        try:
            self._bot.drive_stop()
            self._bot.start()
            time.sleep(0.2)
            self._bot.SCI.write(143)
            self.passivo = True
        except Exception:
            pass
        self._sent_left = None
        self._sent_right = None

    # -- cleaning motors -------------------------------------------------------

    def set_clean_motors(self, on: bool) -> None:
        """Opcode 138: toggle side brush, vacuum, main brush."""
        if self._bot is None or self.passivo:
            return
        try:
            bits = 0x07 if on else 0x00
            self._bot.SCI.write(138, (bits,))
        except Exception:
            pass
