#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import os
import sys

# look for the .glade file and the resources in a 'images' subdirectory below
# this source file.
GLADE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')

ENGRAVING_FONTS_DIR = os.path.join(os.environ['HOME'], 'gcode', 'engraving_fonts')

USER_FS_TABLES_DIR = os.path.join(os.environ['HOME'], 'gcode', 'fs_tables')

# EMC2_HOME should have been prepared already but just in case it has not assume $HOME/tmc
try:
    LINUXCNC_HOME_DIR = os.environ['EMC2_HOME']
except KeyError:
    os.environ['EMC2_HOME'] = os.path.join(os.environ['HOME'], 'tmc')

LINUXCNC_HOME_DIR = os.environ['EMC2_HOME']

# config file
PATHPILOTJSON_FILEPATH = os.path.join(os.environ['HOME'], 'pathpilot.json')

# eula agreed marker file
# be sure to update eula.py and Makefile if you change the name of this.
EULA_AGREED_FILEPATH = os.path.join(LINUXCNC_HOME_DIR, 'eula_agreed.txt')

# test automation file
PATHPILOT_TEST_AUTOMATION_JSON_FILEPATH = os.path.join(os.environ['HOME'], 'pathpilot_testautomation.json')

# localized string resources directory
RES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'res')

# NetBIOS name configuration file
netbios_name_conf_file = os.path.join(os.environ['HOME'], 'smb.conf.netbios-name')

# base path to user's gcode file on disk
GCODE_BASE_PATH = os.path.join(os.environ['HOME'], 'gcode')

# where release note pdfs are located
# if you modify this path, you must look at postinstall.sh for string/name dependencies (and maybe Makefile)
RELEASE_NOTE_PDFS_PATH =  os.path.join(GCODE_BASE_PATH, 'ReleaseNotes')

# where log files are located
LOGFILE_BASE_PATH = os.path.join(GCODE_BASE_PATH, 'logfiles')
GCODELOGFILE_BASE_PATH = os.path.join(LOGFILE_BASE_PATH, 'gcode_log.txt')
STATSFILE_BASE_PATH = os.path.join(LOGFILE_BASE_PATH, 'gcode_stats_cache.json')

# where screen captures are located
SCREENSHOT_BASE_PATH = os.path.join(GCODE_BASE_PATH, 'logfiles')

# where images are located
IMAGES_BASE_PATH = os.path.join(GCODE_BASE_PATH, 'images')

# where is touchscreen calibration data located
TOUCHSCREEN_CALIBRATION_FILE = os.path.join(GCODE_BASE_PATH, 'pointercal.xinput')

# where to look for USB stick mount point
USB_MEDIA_MOUNT_POINT = '/media'
# automount puts it at /media in Lucid 10.04 and /media/$USER for 14.04 or newer
# if /etc/debian_version == 'squeeze/sid' then it's Lucid
# otherwise it's Mint 17.3 (14.04 based) or newer and the mount is point is /media/$USER
DEBIAN_VERSION = 'unknown'
with open('/etc/debian_version', 'r') as f:
    DEBIAN_VERSION = f.readline().strip()
if DEBIAN_VERSION != 'squeeze/sid':
    USB_MEDIA_MOUNT_POINT += '/' + os.getenv('USER')

PATHPILOT_UPDATE_EXTENSION = 'tgp'

# where to look for CAM Toollib updates
CAM_TOOLIB_BASE_PATH = USB_MEDIA_MOUNT_POINT
CAM_TOOLIB_EXTENSION = 'json'

# where to look for software updates
SOFTWARE_UPDATE_BASE_PATH = USB_MEDIA_MOUNT_POINT
SOFTWARE_UPDATES_ON_HD_PATH = os.path.join(os.environ['HOME'], 'updates')

# where we download update checking data from the internet
SOFTWARE_UPDATE_CHECK_PATH = os.path.join(os.environ['HOME'], 'updatecheck')

LINUXCNC_GCODE_FILE_NAME = 'very-unlikely-pathpilot-gcode.file'
LINUXCNC_GCODE_FILE_PATH = os.path.join('/tmp', LINUXCNC_GCODE_FILE_NAME)

# remote screen sharing program
# make uppercase foe MDI
REMOTE_SCREEN_PROGRAM = 'teamviewer'
MDI_REMOTE_SCREEN_PROGRAM = str.upper(REMOTE_SCREEN_PROGRAM)

CLEAR_CURRENT_PROGRAM = 'Clear Current Program'
EMPTY_GCODE_FILENAME = 'empty.ngc'

LOG_CPU_USAGE_THRESHOLD_NOISEFLOOR = 18
LOG_CPU_USAGE_THRESHOLD_ALWAYS = 70

# thread data
THREAD_BASE_PATH = os.path.join(GCODE_BASE_PATH, 'thread_data')
THREAD_DATA_SAE = os.path.join(THREAD_BASE_PATH, 'threads_sae.txt')
THREAD_DATA_METRIC = os.path.join(THREAD_BASE_PATH, 'threads_metric.txt')
THREAD_DATA_SAE_CUSTOM = os.path.join(THREAD_BASE_PATH, 'custom_threads_sae.txt')
THREAD_DATA_METRIC_CUSTOM = os.path.join(THREAD_BASE_PATH, 'custom_threads_metric.txt')


# material data
# For now, read out of the ~/tmc directory instead of the user facing gcode directory
# until we have a better feel of how we want users customizing the data
MATERIAL_BASE_PATH = os.path.join(LINUXCNC_HOME_DIR, 'material_data')

THREAD_CUSTOM_DELIMITER = 'USER'
THREAD_TORMACH_DELIMITER = 'TORMACH'
THREAD_MAX_PASSES = 99

# Constants
ALARM_LEVEL_NONE = -1
ALARM_LEVEL_DEBUG = 0
ALARM_LEVEL_QUIET = 1
ALARM_LEVEL_LOW = 2
ALARM_LEVEL_MEDIUM = 3
ALARM_LEVEL_HIGH = 4

# normal exit
EXITCODE_SHUTDOWN = 0
# 1 and 2 used by python
EXITCODE_RESERVED_1 = 1
EXITCODE_RESERVED_2 = 2
# used to tell operator login to change something
EXITCODE_CONFIG_CHOOSER = 11
EXITCODE_MILL2RAPIDTURN = 12
EXITCODE_RAPIDTURN2MILL = 13
EXITCODE_SETTINGSRESTORE = 14
EXITCODE_REBOOTAFTERUPDATE = 15
EXITCODE_RESOLUTIONCHANGE = 16
EXITCODE_CONFIG_FAILED = 17
EXITCODE_UPDATE_ATC_FIRMWARE = 18
EXITCODE_ATC_FIRMWARE_INIT = 19

# 137 used by python when process gets kill signal
EXITCODE_PROCESS_WAS_KILLED = 137

# *BASIC* MACHINE Type used by self.machine_type
# used when sharing code between lathe & mill, e.g. when
# code is conditionally executed based on machine type
MACHINE_TYPE_UNDEF = 0  # not yet defined
MACHINE_TYPE_MILL = 1
MACHINE_TYPE_LATHE = 2

# these must match in the tool changer HAL component
TOOL_CHANGER_TYPE_MANUAL = 0
TOOL_CHANGER_TYPE_GANG = 1
TOOL_CHANGER_TYPE_TURRET = 2
TOOL_CHANGER_TYPE_ZBOT = 3

#To fully define a TURRET type, see hal and specific.ini files
#must set the following:
#[TURRET]POSITION_FB_TYPE
#[TURRET]POSITIONS
#[TURRET]HAS_LOCKING_FB

# not used in python code, but keep in sync for use in specific.ini's and hals.  Values are for POSITION_FB_TYPE
#POSITION_FEEDBACK_BINARY  =  0
#POSITION_FEEDBACK_1HOT    =  1

# redis string for machine_prefs, toolchanger_type
MILL_TOOLCHANGE_TYPE_REDIS_ZBOT = 'zbot'
MILL_TOOLCHANGE_TYPE_REDIS_MANUAL = 'manual'

# tool table
MAX_LATHE_TOOL_NUM = 99
MAX_NUM_MILL_TOOL_NUM = 1000
NOSE_RADIUS_STANDARD = 0.0315/2
MILL_PROBE_TOOL_NUM = 99
MILL_PROBE_TOOL_DESCRIPTION = "Mill Probe (diameter is effective, not actual)"
#MILL_PROBE_POCKET_NUM = 55
MILL_PROBE_POCKET_NUM = 99

# this is number of 50mS period poll loops, (time in secs)*20 = COOLANT_LOCK_OUT_PERIOD
COOLANT_LOCK_OUT_PERIOD = 20

# Mill spindle types - do not change values. These are stored in redis as
# the user chosen setting - but also used in linuxcnc tormach spindle components.
SPINDLE_TYPE_STANDARD = 0
SPINDLE_TYPE_SPEEDER = 1
SPINDLE_TYPE_HISPEED = 2
SPINDLE_TYPE_RAPID_TURN = 3

# DRO 'has focus' color
HIGHLIGHT = '#24F7ED'
ORANGE = "#F57F0A"
BLUE = "#40AFFF"
GREY = '#918C8E'
BLACK = '#000000'
RED = '#C53232'
WHITE = '#F3F5EB'
ROW_HIGHLIGHT = '#F0ED99'


# Button permisions
#
# First we define mutually exclusive states of the machine (STATE_xxx)
# Then each button has permitted_states attribute which is a bit mask built
# from the STATE_xxx constants. If the machine is in a state that corresponds
# to one of the permitted ones, then the widget action is allowed.
#
# Checking valid state is easy - just bitwise AND the current state of the machine
# with the button mask.  If the result is non-zero, the button is allowed.
#
# This also enables easy common error messaging where the permitted states for the
# widget can be described.

STATE_ESTOP                 = 0x00000001
STATE_IDLE                  = 0x00000002
STATE_IDLE_AND_REFERENCED   = 0x00000004
STATE_HOMING                = 0x00000008
STATE_MOVING                = 0x00000010
STATE_PAUSED_PROGRAM        = 0x00000020
STATE_RUNNING_PROGRAM       = 0x00000040
STATE_RUNNING_PROGRAM_TOOL_CHANGE_WAITING_ON_OPERATOR = 0x00000080

# handy sets of the above bitfields can easily be defined also
STATE_ANY                   = 0xFFFFFFFF



# -------------------------------------------
# Zbot ATC
# -------------------------------------------

ATCFIRMWARE_PATH = os.path.join(LINUXCNC_HOME_DIR, 'firmware/atc')
ATCFIRMWARE_FILENAME = 'atcfirmware-2.13.9.zip'
ATCFIRMWARE_VERSION = '2.13.9'
ATCFIRMWARE_VERSION_SPECIALCASE = '2.11.5'

# -------------------------------------------
# ATC/TTS DIMENSIONS
# -------------------------------------------
ATC_TRAY_TOOLS       =     10
ATC_COMPRESSION  =          .015  #squish constant
ATC_BLAST_DISTANCE =        .75   #distance from tool holder rim
ATC_SHANK_JOG_TTS   =      1.575 # a bit over shank length
ATC_SHANK_JOG_BT30   =     2.85  # BT30
ATC_SHANK_JOG_ISO20   =    2.175 # ISO20 High speed
ATC_JOG_SPEED   =          120   # Straight Shank Tooling
ATC_TAPER_TOOLING_SPEED  = 300   # Taper Tooling w pullstuds
ATC_UP_A_BIT             = .010  # small amount to jog to clear tool tip

#HAL pin commands - for request pin
ATC_SOLENOID  =     1
ATC_DRAW_BAR =      2
ATC_INDEX_TRAY =    3
ATC_QUERY_SENSOR =  4
ATC_FIND_HOME =     5
ATC_OFFSET_HOME =   6
ATC_REPORT_STATUS = 7
ATC_SPINDLE_LOCK =  8


#Special command
ATC_KILL_SPINDLE    = 0


# ATC Data map  - for NGC request_data pin
ATC_TRAY_SOLENOID     = 1
ATC_BLAST_SOLENOID    = 2
ATC_DRAW_BAR_SOLENOID = 3
ATC_SPDL_LK_SOLENOID  = 4

ATC_PRESSURE_SENSOR  = 1
ATC_TRAY_IN_SENSOR   = 3
ATC_TRAY_OUT_SENSOR  = 5  #deprecated

ATC_VFD_SENSOR       = 6
ATC_DRAW_SENSOR      = 7
ATC_LOCK_SENSOR      = 8
ATC_TRAYREF_SENSOR   = 9

ATC_ALL_SENSORS      = 0
ATC_ALL_SENSORS_LIST = [ ATC_PRESSURE_SENSOR,
                         ATC_TRAY_IN_SENSOR,
                         ATC_VFD_SENSOR,
                         ATC_DRAW_SENSOR,
                         ATC_LOCK_SENSOR,
                         ATC_TRAYREF_SENSOR ]
ATC_ACTIVATE  =  ATC_SET_UP = 1
ATC_DEACTIVATE = ATC_SET_DOWN  =  0
ATC_ON = True
ATC_OFF = False


#HAL pins for ATC
#broadcast we are in a change
ATC_HAL_IS_CHANGING = 16  #digital output pin

#from Motion Control
ATC_REQUEST_SPINDLE_LOCK = "0.din.0.request_lock"
ATC_READ_ORIENT_EXECUTE =  "0.din.1.orient_execute"

#from TormachSpindle Component
ATC_READ_ORIENT_STATUS =   "0.ain.8.read_orient_stat"

#from NGC
ATC_HAL_REQUEST_NGC = "0.ain.0.request"
ATC_HAL_REQUEST_DATA_NGC ="0.ain.1.request_data"

#from GUI
ATC_HAL_REQUEST_GUI = "0.ain.2.request"
ATC_HAL_REQUEST_DATA_GUI ="0.ain.3.request_data"



#from either GUI or NGC (this is a motion control analog output pin no to send sequence)
ATC_HAL_SEQ_NO_OUT_PIN_NO= 6
ATC_HAL_COMMAND_OUT_PIN_NO= 7
ATC_HAL_DATA_OUT_PIN_NO= 8

# to either GUI or NGC (this it the motion control analog input put for echo sequence - mapped in post gui hal to )
#                        ATC_HAL_REQUEST_ACK )
ATC_HAL_SEQ_NO_IN_PIN_NO = 7

#hal outputs
ATC_HAL_BUSY = "0.dout.5.exec_status"            # busy?
ATC_HAL_RC = "0.aout.0.request_rc"               # return code from last operation
ATC_HAL_TRAY_POS = "0.aout.1.tray_position"      # current tool tray index position
ATC_PRESSURE_STAT = "0.dout.3.pressure_status"   # current pressure switch status
ATC_HAL_TRAY_STAT = "0.dout.0.tray_status"       # current tray actuator status - in or out?
ATC_HAL_VFD_STAT = "0.dout.1.vfd_status"         # actual spindle feedback from VFD - running?
ATC_HAL_DRAW_STAT = "0.dout.2.draw_status"       # draw bar solenoid - on or off?
ATC_HAL_LOCK_STAT = "0.dout.6.lock_status"       # spindle lock solenoid
ATC_HAL_DEVICE_STAT = "0.dout.4.device_status"   # USB communications channel status
ATC_HAL_TRAYREF_STAT = "0.dout.9.trayref_status" # tray referenced or not?
ATC_HAL_REQUEST_ACK = "0.aout.2.request_ack"     # sequence number echo for last command

#USB commands

USB_VERSION  =  "VE\r"            #used to get firmware version, tools, and VFD detection
USB_VERSION_LONG = "VL\r"         #used to retrieve all other data, BT30, etc...
USB_TRAY_IN  =  str(ATC_TRAY_SOLENOID) +  "+\r"
USB_TRAY_OUT =  str(ATC_TRAY_SOLENOID) +  "-\r"
USB_BLAST_ON =  str(ATC_BLAST_SOLENOID) + "+\r"
USB_BLAST_OFF = str(ATC_BLAST_SOLENOID) + "-\r"
USB_DRAW_HIGH_PRESS = str(ATC_SPDL_LK_SOLENOID) + "+\r"  #active high pressure
USB_DRAW_LOW_PRESS = str(ATC_SPDL_LK_SOLENOID) + "-\r"  #default is low pressure (in case of failure)
#------------------------------------------------------------------------------------------
#  In version 1 boards, the draw bar is operated by a signal to the PDB control board
#  In version 2 boards and higher, the PDB control board is deprecated and the ATC board controls]
#     the draw bar directly
#  So there is a little asymmetry between solenoid operations. Tray, Blast, and Lock are explicitly
#     commanded, whereas solenoid 3 is implicit in the D+ and D- commands.
#-------------------------------------------------------------------------------------------

USB_DB_ACTIVATE  =   "D+\r"         #solenoid 3 in Version 2 board and above
USB_DB_DEACTIVATE =  "D-\r"         #solenoid 3 in Version 2 board and above
USB_INDEX_TRAY =     "T"
USB_QUERY =          "Q"
USB_STATUS =         "ST\r"
USB_FIND_HOME =      "FH\r"
USB_OFFSET_UP =      "H+\r"
USB_OFFSET_DOWN =    "H-\r"

#USB response
USB_OK = '.'
USB_ON = '+'
USB_OFF = '-'
USB_REJECT = 'X'
USB_UNKNOWN = '?'

#DIO AIO PIN NUMBERS
DEVICE_PIN =       21   #atc is communicating
EXEC_PIN =         16   #busy pin (0 executing, 1 working)
REQUEST_PIN =       4   #command (solenoid, draw bar, tray index, etc..)
REQUEST_DATA_PIN =  5   #data qualifier for command (slot number, solenoid number, etc...)
HAL_RETURN_PIN =    5   #return code from last commmand
PROMPT_REPLY_PIN = 10   #analog reply pin for NGC M6 prompts
PROMPT_SET_PIN =   10   #looped back to the above to allow setting
SPDL_ORNT_STATUS_PIN = 8   #used to detect BT30 orientation state from NGC - must be read with
                        #  M66 to be current state
SPDL_IS_LOCKED =   55  #spindle is locked DIO pin

#HAL COMPONENT RC VALUES

ATC_OK = ATC_SENSOR_OFF =        0
ATC_SENSOR_ON =                  1
ATC_COMMAND_REJECTED_ERROR =    -1
ATC_USB_HOMING_ERROR =          -2
ATC_TIMEOUT_ERROR =             -3
ATC_UNKNOWN_USB_RESP_ERROR =    -4
ATC_UNKNOWN_USB_COMMAND_ERROR=  -5
ATC_TRAY_ERROR             =    -6
ATC_USB_IO_ERROR           =    -7
ATC_UNKNOWN_REQUESTED_PIN  =    -8
ATC_PRESSURE_FAULT         =    -9
ATC_NOT_FOUND              =   -10
ATC_GENERAL_TRAP           =   -11
ATC_REF_FIRST              =   -12
ATC_USER_CANCEL            =   -13   #appropriate number
ATC_GENERAL_ERROR          =   -14
ATC_INTERFACE_BUSY         =   -16  # set in NGC hal interface only
ATC_INTERFACE_ERROR        =   -17  # set in NGC hal interface only
ATC_SPINDLE_RUNNING        =   -18  # set in NGC hal interface only
ATC_SPINDLE_ORIENT_ERROR   =   -19  # BT 30 orientation error
ATC_SPINDLE_LOCK_ERROR     =   -20  # BT 30 spindle lock malfunction
ATC_INTERNAL_CODE_ERROR    =   -21   # bad internal logic somewhere, see log

#ATC HAL ERROR MESSAGES - the text key matches the rc values above


ATC_HAL_MESSAGES = {ATC_COMMAND_REJECTED_ERROR : 'ATC - Device, command rejected',
                    ATC_USB_HOMING_ERROR : 'ATC - Device, homing error',
                    ATC_TIMEOUT_ERROR : 'ATC - USB, comms timeout error',
                    ATC_UNKNOWN_USB_RESP_ERROR : 'ATC - Device, issued invalid USB response',
                    ATC_UNKNOWN_USB_COMMAND_ERROR : 'ATC - Device, issued command unknown',
                    ATC_TRAY_ERROR : 'ATC - Device, tray sensor not detecting arrival',
                    ATC_USB_IO_ERROR : 'ATC - USB I/O error',
                    ATC_UNKNOWN_REQUESTED_PIN : 'ATC - HAL command unknown',
                    ATC_PRESSURE_FAULT : 'ATC - Insufficient air pressure',
                    ATC_NOT_FOUND : 'ATC - Cannot find USB device',
                    ATC_REF_FIRST : 'ATC - Cannot offset - reference tool tray first',
                    ATC_USER_CANCEL : 'ATC - Action cancelled by STOP/RESET',
                    ATC_GENERAL_ERROR : 'ATC - Action cancelled due to error',
                    ATC_SPINDLE_ORIENT_ERROR : 'ATC - Spindle orientation error',
                    ATC_SPINDLE_LOCK_ERROR : 'ATC - Spindle lock error'}


EMC_OPERATOR_ERROR_TYPE    =11
EMC_OPERATOR_TEXT_TYPE     =12
EMC_OPERATOR_DISPLAY_TYPE  =13

# G0 rapid moves changed to G1 feedrate moves to limit speed
MAX_PROBE_RAPID_FEEDRATE = 200.0
DEFAULT_PROBE_RAPID_FEEDRATE = 135.0

# values for UEV checking - in imperial (machine setup) units
MAX_PROBE_FINE_FEEDRATE = 60.0
MAX_PROBE_ROUGH_FEEDRATE = 60.0
DEFAULT_PROBE_ROUGH_FEEDRATE = 25.0
DEFAULT_PROBE_FINE_FEEDRATE = 1.5

# ETS fine probe feed rate is fixed for consistency
# units are inches per minute
ETS_FINE_FEEDRATE = 2.5

MAX_PROBE_RING_GAUGE_DIAMETER = 6.0
DEFAULT_PROBE_RING_GAUGE_DIAMETER = 1.0
DEFAULT_PROBE_TIP_ACTUAL_DIAMETER = 0.118

# used to validate DRO entry
MAX_PROBE_TIP_DIAMETER = 0.750

# analog pins used by probe tab DROs
PROBE_X_PLUS_AOUT   = 11
PROBE_X_MINUS_AOUT  = 12
PROBE_Y_PLUS_AOUT   = 13
PROBE_Y_MINUS_AOUT  = 14
PROBE_Z_MINUS_AOUT  = 15
PROBE_Y_PLUS_A_AOUT = 16
PROBE_Y_PLUS_B_AOUT = 17
PROBE_Y_PLUS_C_AOUT = 18
PROBE_POCKET_DIAMETER_AOUT = 19

ESTOP_ERROR_MESSAGE = 'Machine has been estopped.  Restore power to machine and click Reset button to continue.'

# " - " added to prevent message from getting filtered
X_LIMIT_ERROR_MESSAGE = 'X axis limit switch active'
Y_LIMIT_ERROR_MESSAGE = 'Y axis limit switch active'
Z_LIMIT_ERROR_MESSAGE = 'Z axis limit switch active'
X_Y_LIMIT_ERROR_MESSAGE = 'X/Y axis limit switch(es) active'

# this is used for lathe where they are in serial
X_Z_LIMIT_ERROR_MESSAGE = 'X/Z axis limit switch(es) active'


########## keep these in sync with usage in motor components
#"Status" codes returned from component usually as result of motor command (MFB_POSITION is the exception)
# MFB = Motor Feed Back
MFB_OK                         = 0   #motor component understood and acted on last command and so far has no error executing it.
MFB_NO_HOMING                  = 1   #this axis motor has no inherent homing function
MFB_CMD_INVALID                = 2   #unexpected command, i.e. comp is in invalid state to accept it now ; we ignored it
MFB_POSITION                   = 3   #axis motor reported temporary position error. PP UI is expected to clear this error with MOTOR_CMD_ACK_POS command
MFB_CMD_UNKNOWN                = 4   #unknown command; we ignored it
MFB_FAULT                      = 5   #axis motor has faulted.  Could be a fault or no power to motor axis.  We don't know
#note MFB_FAULT must be highest constant as code invalidates codes > MFB_FAULT

#axis motor linuxcnc States keep in sync with linuxcnc motor comps
MS_DISABLED        = 0 #axis motor has been commanded disabled
MS_WAIT            = 1 #motor comp is initializing motor; please wait
MS_HOME_SEARCHING  = 2 #motor comp is expecting PP UI to be executing homing; we haven't detected home yet
MS_HOME_WAITING    = 3 #linuxcnc motor component has detected home and PP must wait until for MS_HOME_COMPLETE state before stopping motion command
MS_HOME_COMPLETE   = 4 #linuxcnc motor component has completed homing detection  We expect Linuxcnc is still finishing backoff, ect.
MS_NORMAL          = 5 #linuxcnc motor component is active and is not in any hardstop mode
MS_FAULT           = 6 #linuxcnc motor component is inactive. We've detected a fault or via ESTOP has been powered off, this comp can't really tell. (but UI can infer)

#Commands to linuxcnc motor components  -- KEEP THESE in sync!
MOTOR_CMD_NONE      = 0 #there is no command, or cleared/did/acknowledge last command.  We use this on the bi-directional i/o to "edge detect" commands and signal to UI, if it cares to look (it doesn't presently)
MOTOR_CMD_DISABLE   = 1 #Disable motor.  The motor is immediately so it will no longer move or actively hold position.  Brake will be automatically applied for Z axis
MOTOR_CMD_NORMAL    = 2 #Enable the axis motor for normal operation.  The comp may  pass through "MS_WAIT" state before assuming "MS_NORMAL" state
MOTOR_CMD_HOME      = 3 #Enable the axis motor for internal homing.  After "MS_WAIT", we enter "MS_HOME_WAITING" state.
                        #Then this comp assumes PP will issue homing commands and movements to linuxcnc.  Eventually, we transistion through "MS_HOME_WAITING" and then "MS_HOME_COMPLETE"
MOTOR_CMD_ACK_HOME  = 4 #When homing is finished, use this command to transistion from "MS_HOME_COMPLETE" to "MS_NORMAL"
MOTOR_CMD_ACK_POS   = 5 #UI uses this command to acknowledge temporary MFB_POSITION "errors".  Motor comp will clear <ACK> this command by changing from MFB_POSTION to MFB_OK and doesn't change motor state
MOTOR_CMD_ACK_ERR   = 6 #UI use this command to acknowlege all other error.  This comp will clear previous UI command errors to MFB_OK if axis motor hasn't faulted.
############## end of defines that need to be kept in sync in all linuxcnc motor comps
POLL_ALL_AXES       = 255 # used with axis_motor_poll routine and is default

# axis max unhomed velocity percent for jog speed clamping on machines with servo axis motors (1 = 100%)
AXIS_SERVOS_CLAMP_VEL_PERCENT = .05

# This "magic number" is the index into digit into usbio_output_#_led labels
# if ever anyone changes the labels for usbio_output_#_led and/or usbio_output_#_led_button, watch this!
USBIO_STR_DIGIT_INDEX = 13
#The mapping for the USBIO M64 and M65 commands
USBIO_LATHE_HAL_OFFSET = 5

# This protects against coding bugs that send conversational gcode generation into
# infinite loops. Those are hard to get details on from a customer as memory is rapidly exhausted and
# the controller goes into swap seizure and the mouse even becomes completely unresponsive.
CONVERSATIONAL_MAX_LINES = 750000

UPDATE_PTR_FILE = os.path.join(os.environ['HOME'], 'update_file.txt')

# Bitfield constants for hal debug-level pin from gui
DEBUG_LEVEL_ATC         = 0x00000001
DEBUG_LEVEL_ATC_VERBOSE = 0x00000002
DEBUG_LEVEL_SMARTCOOL   = 0x00000004

# spindle orienting -- keep in sync with tormachspindlem200.comp!
ISTATE_DONE = 0x2
ISTATE_PAST = 0x10
ORIENT_ERR_MULTIPLE_COMMANDS = -1
ORIENT_ERR_NO_ZINDEX = -2

BT30_OFFSET_INVALID = 0x0BAD0BAD          #Invalid BT30 offset.  Nominally ranges from +/- (Encoder Counts Per Rev/2)

#KEEP in sync with m200.comp
SPINDLE_NO_FAULT = (0)                    #M200 VFD is powered and has no detected faults.  Non m200 VFDs will always return this "OK"
SPINDLE_OK_POSSIBLE_WIRING_ISSUE = (1)    #expected temporary VFD Fault signal not seen during VFD power up.  Error effectivity is ignored.  VFD has power however you may have T41 and T42 wiring issue.
SPINDLE_FAULT_NO_K2 = (2)                 #24VDC from VFD is not present.  K2 has not been activated yet
SPINDLE_FAULT_VFD_FAULT_M5 = (3)          #VFD signaled fault while not being commanded to move; may be spindle door opening
SPINDLE_FAULT_LOST_PWR = (4)              #VFD lost power. It had it; may be spindle door opening
SPINDLE_FAULT_LOG_ONLY = (SPINDLE_FAULT_LOST_PWR)  # spindle faults at or below this are only logged. above this point user will get indication

SPINDLE_FAULT_BT30 = (5)                  #spindle not stationary or not in correct mode for setting BT30A
SPINDLE_FAULT_BT30_Z_INDEX = (6)          #set BT30 attempted before z index was seen
SPINDLE_FAULT_ORIENT_TO  = (7)            #orient time out detected.  Linuxcnc already notified user about T.O., so only log it
SPINDLE_FAULT_ORIENT_MAX_ROTATION = (8)   #orient failed due to excessive number of revolutions.  Check encoder
SPINDLE_FAULT_NO_ZINDEX = (9)             #orient attempted and Z index not found.  Check encoder
SPINDLE_FAULT_INVALID_BT30_OFFSET = (10)  #BT30 orientation zero offset has not been set. Read user manual.
SPINDLE_FAULT_NO_ENCODER = (11)           #M19 or spindle sync mode was requested yet machine has no encoder or incorrect machine type selected
SPINDLE_FAULT_VFD_DOESNT_SUPPORT = (12)   #This machine's VFD does not support M19 or automatic VFD mode switching.
SPINDLE_FAULT_SPINDLE_TYPE = (13)         #Orient mode requested with spindle type that doesnt support it
SPINDLE_FAULT_VFD_RPM  = (14)             #VFD motor speed feedback absent. Check VFD wiring.
SPINDLE_FAULT_NO_PWR = (15)               #24VDC from VFD is still not present after K2 presumably activated.  Check spindle door switch, mill circuit breakers, or VFD wiring
SPINDLE_FAULT_VFD_PRIOR_FAULT = (16)      #spindle commanded to start but VFD is faulted. Look at VFD for error code and press VFD orange button to clear fault. Or ESTOP to power cycle VFD before continuing.
SPINDLE_FAULT_MODE_SWITCH  = (17)         #expected VFD Mode switch acknowledgment did not occur.  Is machine configured right, do you have VFDmx, wiring errors
SPINDLE_FAULT_CRITICAL = (SPINDLE_FAULT_MODE_SWITCH)  #vfd faults that are this level and above cause software ESTOP
SPINDLE_FAULT_VFD = (18)                  #VFD reported a fault during rotation.  Check spindle door switch and Look for error code on VFD.
SPINDLE_FAULT_LOCK_WITHOUT_PRIOR_ORIENT = (19) #This shouldn't happen. Linuxcnc state seems confused


SPINDLE_ERR_MSGS = {
SPINDLE_NO_FAULT : 'Spindle: M200 OK',
SPINDLE_OK_POSSIBLE_WIRING_ISSUE : 'Spindle: Possible VFD wiring issue. Check T41 and T42',
SPINDLE_FAULT_NO_K2 : 'Spindle: VFD off as K2 not yet latched',
SPINDLE_FAULT_BT30 : 'Spindle: Not stationary or in correct spindle mode for setting BT30A',
SPINDLE_FAULT_BT30_Z_INDEX : 'Spindle: BT30 offset attempted before z index',
SPINDLE_FAULT_ORIENT_TO : 'Spindle: Orient time out detected.  Linuxcnc already notified user about T.O. right?',
SPINDLE_FAULT_ORIENT_MAX_ROTATION : 'Spindle: Orient moved more than 2 revs.  Check encoder',
SPINDLE_FAULT_NO_ZINDEX : 'Spindle: Z index not found during orient attempt.  Check encoder',
SPINDLE_FAULT_INVALID_BT30_OFFSET : 'Spindle: Refusing to orient as M19 R=0 position has not yet been set. Please read user manual.',
SPINDLE_FAULT_NO_ENCODER : 'Spindle: M19 or spindle sync mode requested yet machine has no encoder. Possible incorrect machine type selected',
SPINDLE_FAULT_VFD_DOESNT_SUPPORT : 'Spindle: VFD does not support M19 or automatic VFD mode switching.',
SPINDLE_FAULT_SPINDLE_TYPE : 'Spindle: Orient requested with spindle type that doesnt support it',
SPINDLE_FAULT_VFD_RPM : 'Spindle: VFD motor speed feedback absent. Check VFD wiring.',
SPINDLE_FAULT_MODE_SWITCH : 'Spindle: Expected VFD Mode switch fault. Is machine configured right? Do you have VFDmx? Check for wiring errors',
SPINDLE_FAULT_VFD : 'Spindle: VFD faulted while rotation commanded. Check spindle door switch then look for error code on VFD',
SPINDLE_FAULT_NO_PWR : 'Spindle: VFD has no power after K2 activated. Check spindle door switch, mill circuit breakers, VFD wiring, or K2',
SPINDLE_FAULT_VFD_PRIOR_FAULT : 'Spindle: VFD in fault state prior to spindle start. Check VFD for error code. Press VFD orange button to clear fault or ESTOP to power cycle VFD before continuing.',
SPINDLE_FAULT_LOST_PWR : 'Spindle: VFD lost power. It had it. Check spindle door switch',
SPINDLE_FAULT_LOCK_WITHOUT_PRIOR_ORIENT : 'Spindle: This should not happen. Linuxcnc state seems confused',
SPINDLE_FAULT_VFD_FAULT_M5: 'Spindle: VFD faulted while stopped. User possibly opened spindle door. Check spindle door switch'}

# ADMIN SET_AXIS_SCALE_FACTOR X 1.0001
AXIS_SCALE_FACTOR_MIN = 0.995
AXIS_SCALE_FACTOR_MAX = 1.005

# ADMIN SET_AXIS_BACKLASH X 0.0015
# this is inches
AXIS_BACKLASH_MAX = 0.005
