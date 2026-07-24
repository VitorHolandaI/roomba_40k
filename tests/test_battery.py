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


class _WaitingSensor(_FakeSensor):
    charger_state = 4


class _OverfullSensor(_FakeSensor):
    battery_charge = 4000  # > capacity: leitura descalibrada do Roomba
    battery_capacity = 3000


class _BotWith:
    def __init__(self, sensor: object) -> None:
        self._sensor = sensor

    def get_sensors(self) -> object:
        return self._sensor


def test_charger_state_4_is_waiting_not_complete() -> None:
    info = read_battery(_BotWith(_WaitingSensor()))
    assert info is not None
    assert info.state == "Aguardando"


def test_percent_clamped_to_100() -> None:
    info = read_battery(_BotWith(_OverfullSensor()))
    assert info is not None
    assert info.percent == 100.0


def test_read_battery_failure() -> None:
    assert read_battery(_BadBot()) is None


def test_read_battery_missing_sensor_packet() -> None:
    assert read_battery(_MissingSensorBot()) is None
