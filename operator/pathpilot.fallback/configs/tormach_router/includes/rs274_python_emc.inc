[RS274NGC]
RS274NGC_STARTUP_CODE = G8 G17 G20 G90 G64
# set bit 2 to fetch ini file values in g-code, #<_ini[section]name>
FEATURES = 12
SINGLE_BLOCK_LOCAL_SUB = YES
SINGLE_BLOCK_EXTERNAL_SUB = NO

USER_M_PATH = nc_subs
DEBUG = 0

[PYTHON]
TOPLEVEL= python/toplevel.py
PATH_PREPEND= python
LOG_LEVEL=0

[EMCMOT]
EMCMOT = motmod
COMM_TIMEOUT = 1.0
COMM_WAIT = 0.010
SERVO_PERIOD = 1000000

[EMCIO]
EMCIO = io
CYCLE_TIME = 0.100

