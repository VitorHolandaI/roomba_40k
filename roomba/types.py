"""Shared dataclasses for the roomba package."""

from dataclasses import dataclass


@dataclass
class BatteryInfo:
    """Structured battery reading with UI-friendly formatting."""

    percent: float
    voltage: float
    current: int
    state: str

    def to_dict(self) -> dict[str, object]:
        """Serialize for WebSocket broadcast."""
        return {
            "type": "battery",
            "ok": True,
            "percent": round(self.percent, 1),
            "voltage": round(self.voltage, 2),
            "current": self.current,
            "state": self.state,
        }
