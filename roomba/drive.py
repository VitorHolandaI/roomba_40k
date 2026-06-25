"""Pure drive math — no hardware, no I/O."""

MIN_VEL = 50
MAX_VEL = 500


def clamp_velocity(value: int) -> int:
    """Clamp wheel velocity to the safe [-MAX_VEL, MAX_VEL] range."""
    if value > MAX_VEL:
        return MAX_VEL
    if value < -MAX_VEL:
        return -MAX_VEL
    return value


def is_drive_stale(last_update: float, now: float, timeout: float = 0.3) -> bool:
    """Return True when the drive command is older than ``timeout`` seconds."""
    return (now - last_update) > timeout
