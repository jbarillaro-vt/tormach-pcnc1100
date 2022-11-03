# Commander SK VFD when tuned for 770 with TTS/R8 spindle

[SPINDLE]
LO_RANGE_MIN = 175
LO_RANGE_MAX = 3250
HI_RANGE_MIN = 525
HI_RANGE_MAX = 10200

# low and high range min/max frequency sent to VFD
LO_RANGE_MIN_VFD_FREQUENCY = 175.0
LO_RANGE_MAX_VFD_FREQUENCY = 3250.0
HI_RANGE_MIN_VFD_FREQUENCY = 525.0
HI_RANGE_MAX_VFD_FREQUENCY = 10200.0

# MCB input 5450 Hz -> VFD 60 Hz
# VFD is set to 1.5 sec/100 Hz
# For 770 VFD reads 120 Hz at max pulse stream from HAL of 10,000 pulses/sec
# At 1.5 sec/100 Hz that works out to 1.8 sec to reach 120 Hz - full speed
# Max speed 10200 RPM in high belt -> 5666.7 RPM/s^2
# Max speed  3250 RPM in low  belt -> 1805.6 RPM/s^2
# So 1.8 seconds should be enough but in practice 3.0 seconds to 10200 RPM was observed
SECONDS_TO_MAX_RPM = 3.0

# feeds and speeds power curve (rpm to hp)
LO_POWER_CURVE = (%(LO_RANGE_MIN)s, 0.1), (800, 1.08), (3000, 0.92), (%(LO_RANGE_MAX)s, 0.75)
HI_POWER_CURVE = (%(HI_RANGE_MIN)s, 0.25), (3000, 1.0), (3600, 1.0), (%(HI_RANGE_MAX)s, 0.4)
