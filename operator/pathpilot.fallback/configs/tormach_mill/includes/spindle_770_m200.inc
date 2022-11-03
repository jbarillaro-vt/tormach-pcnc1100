# M200 VFD when tuned for 770 with TTS/R8 spindle

[SPINDLE]
#units are RPM
LO_RANGE_MIN = 175
LO_RANGE_MAX = 3250
LO_RANGE_STEP_RPM = 500
#units are %  (of RPM)
LO_RANGE_TOL_BELOW = 10
LO_RANGE_TOL_ABOVE = 5

HI_RANGE_MIN = 525
HI_RANGE_MAX = 10200
HI_RANGE_STEP_RPM = 1500
HI_RANGE_TOL_BELOW = 10
HI_RANGE_TOL_ABOVE = 5

# motor to spindle pulley ratios
HI_RANGE_PULLEY_RATIO = 1.5
LO_RANGE_PULLEY_RATIO = 0.477941

# Multiply m200 VFD_RUNNING feedback by this ratio to get RPM of spindle motor
# 770 is non-standard verses other products, so we override default 3.0
VFD_RUNNING_FEEDBACK_RATIO = 2.0

# feeds and speeds power curve (rpm to hp)
LO_POWER_CURVE = (%(LO_RANGE_MIN)s, 0.2), (1100, 1.0), (2200, 0.8), (%(LO_RANGE_MAX)s, 0.35)
HI_POWER_CURVE = (%(HI_RANGE_MIN)s, 0.2), (3000, 1.0), (6700, 0.8), (%(HI_RANGE_MAX)s, 0.35)
