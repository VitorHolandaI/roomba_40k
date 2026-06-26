"""Detecta a *borda de subida* do sensor de toque (bump) do Create2.

O bump fica fechado enquanto o robô continua encostado. Para tocar o efeito
sonoro UMA vez por batida (e não repetir a cada leitura enquanto pressionado),
guardamos o estado anterior e só sinalizamos na transição solto -> pressionado.
"""

from typing import Optional

from roomba.auto import _Sensors


class BumpWatcher:
    """Sinaliza cada nova batida via borda de subida do bump esquerdo/direito.

    Exemplo::

        watcher = BumpWatcher()
        if watcher.bumped(bot.get_sensors()):
            effects.trigger()
    """

    def __init__(self) -> None:
        self._was_pressed = False

    def bumped(self, sensors: Optional[_Sensors]) -> bool:
        """True só na transição solto -> pressionado; atualiza o estado."""
        pressed = self._is_pressed(sensors)
        rising = pressed and not self._was_pressed
        self._was_pressed = pressed
        return rising

    @staticmethod
    def _is_pressed(sensors: Optional[_Sensors]) -> bool:
        if sensors is None:
            return False
        bumps = sensors.bumps_wheeldrops
        return bool(bumps.bump_left or bumps.bump_right)
