# M200 VFD when tuned for 1100 with BT30 spindle

[SPINDLE]
#units are RPM
LO_RANGE_MIN = 70
LO_RANGE_MAX = 2000
LO_RANGE_STEP_RPM = 70
#units are %  (of RPM)
LO_RANGE_TOL_BELOW = 10
LO_RANGE_TOL_ABOVE = 10

HI_RANGE_MIN = 250
HI_RANGE_MAX = 10000
HI_RANGE_STEP_RPM = 1000
HI_RANGE_TOL_BELOW = 25
HI_RANGE_TOL_ABOVE = 10

#High Speed Spindle
HISPEED_MIN = 1000
HISPEED_MAX = 24000
HISPEED_STEP_RPM = 8000
HISPEED_TOL_BELOW = 25
HISPEED_TOL_ABOVE = 10

COLLET_TYPE = BT30_WITH_DOGS

# motor to spindle pulley ratios
HI_RANGE_PULLEY_RATIO = 2.9
LO_RANGE_PULLEY_RATIO = .57143

#spindle encoder, not to be confused with vfd_running which is another encoder, though that one is velocity mode only, not position as this one has
#NOT defining #ENCODER_SCALE here means "no encoder" installed, warning can't set to 0 or 1 here
ENCODER_SCALE = 2048

# SPINDLE orienting PID tuning params

DEADBAND = 0
P = -0.9
P2 = -1.8
I = 0.0
I2 = 0.0
D = 0.0
D2 = -0.032
FF0 = 0.0
FF1 = 0.0
FF2 = 0.0
BIAS = 0
MAX_OUTPUT = 0
#set MAX_ERROR 1/2 ENCODER_SCALE
MAX_ERROR = 1024
P2_TRANSITION = 65
ORIENT_BOOST_STEP = 5.0
ORIENT_BOOST_MIN = 18.0
#end of spindle encoder
