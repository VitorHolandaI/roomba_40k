"""Autonomous wandering logic — decides wheel targets based on sensor readings."""

import random
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from roomba.drive import MIN_VEL


class _BumpData(Protocol):  # pylint: disable=too-few-public-methods
    wheeldrop_left: bool
    wheeldrop_right: bool
    bump_left: bool
    bump_right: bool


class _Sensors(Protocol):  # pylint: disable=too-few-public-methods
    bumps_wheeldrops: _BumpData
    cliff_left: bool
    cliff_front_left: bool
    cliff_front_right: bool
    cliff_right: bool


@dataclass
class AutoDecision:
    """Result of an autopilot step: velocities + collision flag."""

    left: int
    right: int
    collision: bool


class AutoPilot:  # pylint: disable=too-few-public-methods
    """State-machine-like queue for evasion maneuvers."""

    def __init__(self) -> None:
        self._queue: List[Tuple[int, int, float]] = []
        self._until = 0.0
        self._next_decision = 0.0
        self._left = 0
        self._right = 0

    # -- internal helpers -------------------------------------------------------

    def _velocities(self, base_speed: int) -> Tuple[int, int, int]:
        """Compute forward / turn / back speeds from the user slider."""
        turn = max(MIN_VEL, int(base_speed * 0.8))
        back = -max(MIN_VEL, int(base_speed * 0.8))
        return base_speed, turn, back

    def _enqueue_evasion(
        self,
        back_dur: float,
        turn_dur: float,
        turn_right: bool,
        base_speed: int,
    ) -> None:
        """Queue a backing-up + turn maneuver."""
        _, turn, back = self._velocities(base_speed)
        if turn_right:
            giro = (turn, -turn)
        else:
            giro = (-turn, turn)
        self._queue = [(back, back, back_dur), (giro[0], giro[1], turn_dur)]
        self._until = 0.0

    def _hazard_reaction(
        self,
        sensors: _Sensors,
        base_speed: int,
    ) -> Optional[AutoDecision]:
        """Check for cliffs, wheeldrops and bumps; queue evasion if found."""
        bw = sensors.bumps_wheeldrops
        cliff = (
            sensors.cliff_left
            or sensors.cliff_front_left
            or sensors.cliff_front_right
            or sensors.cliff_right
        )
        wheeldrop = bw.wheeldrop_left or bw.wheeldrop_right

        if cliff or wheeldrop:
            left_side = (
                sensors.cliff_left or sensors.cliff_front_left or bw.wheeldrop_left
            )
            self._enqueue_evasion(0.6, 0.7, turn_right=left_side, base_speed=base_speed)
            return AutoDecision(self._left, self._right, True)

        if bw.bump_left and bw.bump_right:
            self._enqueue_evasion(0.4, 0.8, turn_right=True, base_speed=base_speed)
            return AutoDecision(self._left, self._right, True)

        if bw.bump_left:
            self._enqueue_evasion(0.3, 0.5, turn_right=True, base_speed=base_speed)
            return AutoDecision(self._left, self._right, True)

        if bw.bump_right:
            self._enqueue_evasion(0.3, 0.5, turn_right=False, base_speed=base_speed)
            return AutoDecision(self._left, self._right, True)

        return None

    # -- decision entry point ---------------------------------------------------

    def decide(
        self,
        sensors: Optional[_Sensors],
        base_speed: int,
        now: float,
    ) -> AutoDecision:
        """Return velocities for the current moment."""
        if sensors is None:
            return AutoDecision(0, 0, False)

        if now < self._until:
            return AutoDecision(self._left, self._right, False)

        if self._queue:
            left, right, duration = self._queue.pop(0)
            self._left, self._right = left, right
            self._until = now + duration
            return AutoDecision(left, right, False)

        if now < self._next_decision:
            return AutoDecision(self._left, self._right, False)

        self._next_decision = now + 0.1

        reaction = self._hazard_reaction(sensors, base_speed)
        if reaction is not None:
            return reaction

        fwd, turn, _ = self._velocities(base_speed)

        if random.random() < 0.04:
            d = turn if random.random() < 0.5 else -turn
            self._queue = [(d, -d, random.uniform(0.2, 0.5))]
            self._until = 0.0
            return AutoDecision(self._left, self._right, False)

        self._left = self._right = fwd
        return AutoDecision(fwd, fwd, False)
