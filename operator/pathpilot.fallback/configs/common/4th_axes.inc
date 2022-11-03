# This comment applies to all A_AXIS_x 4th axis mill accessories,
# that is section names beginning with "A_AXIS_"
# See machine.py A_AxisConfig() and keep new sections in sync
# The paradigm here is that one of these new "A_AXIS_" sections will
# be dynamically chosen in PP and will over ride the above "AXIS_3" settings
# There are currently 7 dynamically setable defines/keys in these "AXIS_A" settings.
# You are wasting your time if you put anything else in the "AXIS_A_" sections
# see A_AxisConfig._a_axis_set()
#   MAX_VELOCITY
#   MAX_ACCELERATION
#   STEPGEN_MAX_VEL
#   STEPGEN_MAXACCEL
#   MAX_JOG_VELOCITY_UPS
#   MIN_JOG_VELOCITY_UPS
#   SCALE
# You are wasting your time if you put anything else in the "AXIS_A_" sections
# or you must add to A_AxisConfig._a_axis_set()

# 4" rotary table, a.k.a. "harmonic
[A_AXIS_4_INCH]
MAX_VELOCITY = 120.0
MAX_ACCELERATION = 80.0

# 20 % higher
STEPGEN_MAX_VEL = 150.0
STEPGEN_MAXACCEL = 100.0

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 120.0
MIN_JOG_VELOCITY_UPS = 0.15

SCALE = 283.333333


# All 6" and 8" rotary tables
[A_AXIS_6_8_INCH]
MAX_VELOCITY = 22.0
MAX_ACCELERATION = 69.0

# 20 % higher
STEPGEN_MAX_VEL = 26.4
STEPGEN_MAXACCEL = 82.8

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 22.0
MIN_JOG_VELOCITY_UPS = 0.15

SCALE = 500.0


[A_AXIS_440_RT]
MAX_VELOCITY = 600.0
MAX_ACCELERATION = 400.0

STEPGEN_MAX_VEL = 720.0
STEPGEN_MAXACCEL = 480.0

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 120.0
MIN_JOG_VELOCITY_UPS = 0.15

# 2000/360
SCALE = 5.55555
