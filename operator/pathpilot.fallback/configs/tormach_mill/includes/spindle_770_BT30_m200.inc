# M200 VFD when tuned for 770 with BT30 spindle

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

COLLET_TYPE = BT30_WITH_DOGS

# motor to spindle pulley ratios
HI_RANGE_PULLEY_RATIO = 1.5
LO_RANGE_PULLEY_RATIO = 0.477941

# Multiply m200 VFD_RUNNING feedback by this ratio to get RPM of spindle motor
# 770 is non-standard verses other products, so we override default 3.0
VFD_RUNNING_FEEDBACK_RATIO = 2.0

#spindle encoder, not to be confused with vfd_running which is another encoder, though that one is velocity mode only, not position as this one has
#NOT defining #ENCODER_SCALE here means "no encoder" installed, warning can't set to 0 or 1 here
ENCODER_SCALE = 2048

# SPINDLE orienting PID tuning params
DEADBAND = 0
P = -0.6
P2 = -1.2
I = 0.0
I2 = 0.0
D = -0.02
D2 = -0.02
FF0 = 0.0
FF1 = 0.0
FF2 = 0.0
BIAS = 0
MAX_OUTPUT = 0
#set MAX_ERROR 1/2 ENCODER_SCALE
MAX_ERROR = 1024
P2_TRANSITION = 95
ORIENT_BOOST_STEP = 10.0 
ORIENT_BOOST_MIN = 15.0
#end of spindle encoder
