
# commander SK spindle based mills with RapidTurn use this

[SPINDLE]
# chucker spindle config is the same for all mills
#
# spindle large  pulley 118.10 mm
#         small         98.40 mm
# motor   large         57.25 mm
# motor   small         31.75 mm
#
# slow position: 31.75 / 118.1 = 0.269
# fast position: 57.25 / 98.4  = 0.582
# high/low belt ratio 0.582 / 0.269 = 2.163
#
# MCB input 5450 Hz -> VFD 60 Hz -> motor 3360 RPM -> slow pulley ratio 0.269 -> spindle  903.84 RPM
# 5450 / 903.84 = 6.030 MCB input Hz per spindle RPM slow position
LO_RANGE_MIN = 175
LO_RANGE_MAX = 2000
HI_RANGE_MIN = 350
HI_RANGE_MAX = 3500

# spindle acceleration to control motion.spindle-at-apeed
#
# seconds between spindle start command, contactor closure, and start of acceleration
STARTUP_DELAY = 1.0

# Multiply VFD_RUNNING from m200 VFD by this ratio to get RPM of spindle motor
# So far everything is "3.0" except 770, which is 2.  RapidTurn has 770 spindle motor
VFD_RUNNING_FEEDBACK_RATIO = 2.0

# MCB input 5450 Hz -> VFD 60 Hz
# VFD is set to 1.5 sec/100 Hz
# For 770 VFD reads 120 Hz at max pulse stream from HAL of 10,000 pulses/sec
# At 1.5 sec/100 Hz that works out to 1.8 sec to reach 120 Hz - full speed
# Max speed 10200 RPM in high belt -> 5666.7 RPM/s^2
# Max speed  3250 RPM in low  belt -> 1805.6 RPM/s^2
SECONDS_TO_MAX_RPM = 1.8
