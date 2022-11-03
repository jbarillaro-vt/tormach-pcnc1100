# Common definition of 1100 pre-M axis with clearpath servo motors
# These have the shorter Y travel
# And this is RapidTurn so AXIS_0 and AXIS_2 are swapped logically from mill

[TRAJ]
# square root of the sum of the squares for XYZ max velocities
MAX_VELOCITY = 8.04327


[AXIS_0]
# lathe X, mill hardware Z

#230 in/min
MAX_VELOCITY = 3.8333
MAX_ACCELERATION = 19.167

# 20 % higher
STEPGEN_MAX_VEL = 4.600

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 47.9175

# PID tuning params
P = 1000

SCALE = -16000.0

FERROR = 0.050
MIN_FERROR = 0.010

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

MAX_JOG_VELOCITY_UPS = 3.0

HOME_OFFSET = -0.050
HOME = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO

MIN_LIMIT = -16.250
MAX_LIMIT = 0.000001


[AXIS_1]
# 300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30.0

# 20 % higher
STEPGEN_MAX_VEL = 6.0

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75.0

# PID tuning params
P = 1000

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

#was SCALE = 10000.0 now steps are 3200/rev verses 2000/rev
SCALE = 16000.0
MIN_LIMIT = -9.500
MAX_LIMIT = 0.000001
HOME_OFFSET = 0.025
HOME = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO

FERROR = 0.050
MIN_FERROR = 0.010

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

[AXIS_2]
# lathe Z, mill hardware X
# 300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30.0

# 20 % higher than max
STEPGEN_MAX_VEL = 6.0

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75

# PID tuning params
P = 1000

#was SCALE = 10000.0 now steps are 3200/rev verses 2000/rev
SCALE = 16000.0

FERROR = 0.050
MIN_FERROR = 0.010

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

HOME_OFFSET = -18.0
HOME = -18.0
HOME_SEARCH_VEL = -0.750
HOME_LATCH_VEL = 0.050
HOME_HSTOP = NO

MAX_LIMIT = 0.000001
MIN_LIMIT = -18.000
