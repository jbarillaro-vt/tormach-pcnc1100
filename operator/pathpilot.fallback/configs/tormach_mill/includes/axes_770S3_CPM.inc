# Common definition of 770 axis with clearpath servo motors
# on per-M machines which use limit switches for referencing

[AXIS_0]
#300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30

# 20 % higher
STEPGEN_MAX_VEL = 6.0

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75.0

# nanoseconds
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

# PID tuning params
P = 1000

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

SCALE = 20320.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -0.000001
MAX_LIMIT = 14.000000

HOME = 0.0
HOME_OFFSET = 0.0
HOME_SEARCH_VEL = -0.750
HOME_LATCH_VEL = 0.050
HOME_HSTOP = NO


[AXIS_1]
#300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30

# 20 % higher
STEPGEN_MAX_VEL = 6.0

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75.0

# nanoseconds
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE  = 2000

# PID tuning params
P = 1000

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

SCALE = 20320.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -7.500
MAX_LIMIT = 0.000001

HOME = 0.0
HOME_OFFSET = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO


[AXIS_2]
#250 in/min
MAX_VELOCITY = 4.1667
MAX_ACCELERATION = 30.0

# 20 % higher
STEPGEN_MAX_VEL = 5.1

# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75.0

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE  = 2000

# PID tuning params
P = 1000

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.00

SCALE = 20320.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -13.250
MAX_LIMIT = 0.000001

HOME = 0.000
HOME_OFFSET = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO
