"""Web-layer constants."""

# Seconds without a WS command before the robot auto-stops.
TIMEOUT = 0.3

# Seconds between battery reads / broadcasts.
BATTERY_INTERVAL = 2.0

# Control loop period (~50 Hz).
LOOP_PERIOD = 0.02

# Autonomous decision cadence.
AUTO_DECISION = 0.1

# Bump sensor poll cadence for sound effects (both manual and auto modes).
BUMP_AUDIO_POLL = 0.1
