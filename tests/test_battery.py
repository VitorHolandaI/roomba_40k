"""Battery formatting tests — no serial needed."""

from roomba.battery import read_battery
from roomba.types import BatteryInfo


class _FakeSensor:
    battery_charge = 1500
    battery_capacity = 3000
    charger_state = 2
    voltage = 12000
    current = 500


class _FakeBot:
    def get_sensors(self) -> object:
        return _FakeSensor()


class _BadBot:
    def get_sensors(self) -> object:
        raise RuntimeError("no hardware")


class _MissingSensorBot:
    def get_sensors(self) -> None:
        return None


def test_read_battery_success() -> None:
    info = read_battery(_FakeBot())
    assert info is not None
    assert info.percent == 50.0
    assert info.state == "Carregando"
    assert info.voltage == 12.0
    assert info.current == 500


def test_read_battery_failure() -> None:
    assert read_battery(_BadBot()) is None


def test_read_battery_missing_sensor_packet() -> None:
    assert read_battery(_MissingSensorBot()) is None
