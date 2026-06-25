"""Battery reading helpers."""

from typing import Optional

from roomba.types import BatteryInfo

_CHARGER_STATES = {
    0: "Não carregando",
    1: "Recuperação",
    2: "Carregando",
    3: "Carga lenta",
    4: "Completa",
    5: "Falha",
}


def read_battery(bot: object) -> Optional[BatteryInfo]:
    """Read battery from a Create2-compatible robot object."""
    try:
        sensors = bot.get_sensors()  # type: ignore[attr-defined]
    except Exception:
        return None
    if sensors is None:
        return None

    capacity = sensors.battery_capacity  # type: ignore[attr-defined]
    if capacity == 0:
        return None

    charge = sensors.battery_charge  # type: ignore[attr-defined]
    percentual = (charge / capacity) * 100
    estado = _CHARGER_STATES.get(
        sensors.charger_state,  # type: ignore[attr-defined]
        "Desconhecido",
    )

    return BatteryInfo(
        percent=percentual,
        voltage=sensors.voltage / 1000,  # type: ignore[attr-defined]
        current=sensors.current,  # type: ignore[attr-defined]
        state=estado,
    )
