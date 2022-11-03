# Common definition of 770 axes pre-M with clearpath servo motors

[TRAJ]
# square root of the sum of the squares for XYZ max velocities
MAX_VELOCITY = 8.20


[AXIS_0]
# lathe X, mill hardware Z
#250 in/min
MAX_VELOCITY = 4.1667
MAX_ACCELERATION = 30.0

# 20 % higher
STEPGEN_MAX_VEL = 5.1

# needs to be 2.5 axis max accel
STEPGEN_MAXACCEL = 75.0

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.00

# NOTE: the 770M Z motor direction is wired backwards from Series 3 770/1100 and 1100M so the scale is the other sign here
SCALE = 10160.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -13.250

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

HOME_OFFSET = -0.050
HOME = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO


[AXIS_1]
#300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30

# 20 % higher
STEPGEN_MAX_VEL = 6.0
# needs to be 2.5x axis max accel
STEPGEN_MAXACCEL = 75

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

SCALE = 10160.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -7.500

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

HOME_OFFSET = 0.025
HOME = 0.0
HOME_SEARCH_VEL = 0.750
HOME_LATCH_VEL = -0.050
HOME_HSTOP = NO


[AXIS_2]
# lathe Z, mill hardware X
#300 in/min
MAX_VELOCITY = 5.0
MAX_ACCELERATION = 30

# 20 % higher
STEPGEN_MAX_VEL = 6.0
# 2.5x higher
STEPGEN_MAXACCEL = 75

# jog shuttle ring speed
MAX_JOG_VELOCITY_UPS = 3.333

SCALE = 20320.0

FERROR = 0.050
MIN_FERROR = 0.010

MIN_LIMIT = -14.000
MAX_LIMIT = 0.000001

#nanosecs .. for ClearPath
DIRSETUP = 2000
DIRHOLD = 2000
STEPLEN = 2000
STEPSPACE = 2000

HOME = -14.0
HOME_HSTOP = NO
