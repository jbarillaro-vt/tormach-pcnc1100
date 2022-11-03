# MX3660 VFD when tuned for 440 with TTS/R8 spindle

[SPINDLE]
REVERSE_SUPPORTED = NO
LO_RANGE_MIN = 300
LO_RANGE_MAX = 4500
HI_RANGE_MIN = 650
HI_RANGE_MAX = 10000

# seconds between spindle start command, contactor closure, and start of acceleration
STARTUP_DELAY = 1.0
SECONDS_TO_MAX_RPM = 5.0

# feeds and speeds power curve (rpm to hp)
LO_POWER_CURVE = (%(LO_RANGE_MIN)s, 0.2), (2500, 0.8), (4000, 1.2), (%(LO_RANGE_MAX)s, 1.0)
HI_POWER_CURVE = (%(HI_RANGE_MIN)s, 0.1), (4000, 0.6), (8000, 0.8), (%(HI_RANGE_MAX)s, 0.68)

