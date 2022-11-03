#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


# This generates LinuxCNC INI files for Tormach mills and lathes
# See "__main__" for use examples

import sys
import errno
import os

class tormach_ini_file():
    # INI file revision
    ini_revision = '# INI file Revison 1.0\n\n'

    # machine type
    (TYPE_NONE, TYPE_MILL_1100, TYPE_MILL_770, TYPE_LATHE) = range(0, 4)
    # machine series
    (SERIES_ANY, SERIES_1, SERIES_2, SERIES_3) = range(0, 4)

    # mill common INI section
    mill_ini_common = ("[EMC]\n"
                       "MACHINE = tormach_mill\n"
                       "DEBUG = 0\n"
                       "\n"
                       "[DISPLAY]\n"
                       "DISPLAY = tormach_mill_ui.py\n"
                       "POSITION_OFFSET = RELATIVE\n"
                       "POSITION_FEEDBACK = ACTUAL\n"
                       "MAX_FEED_OVERRIDE = 1.2\n"
                       "INTRO_GRAPHIC = tormach_mill_splash.gif\n"
                       "INTRO_TIME = 2\n"
                       "PROGRAM_PREFIX = ~/nc_files\n"
                       "INCREMENTS = .1in .05in .01in .005in .001in .0005in .0001in\n"
                       "DEFAULT_LINEAR_VELOCITY = 1.83\n"
                       "DEFAULT_ANGULAR_VELOCITY = 0.6\n"
                       "\n"
                       "[REDIS]\n"
                       "# IMPORTANT: redis-server has a bad side effect where if *any* arguments are provided\n"
                       "#            it clears the default save parameters and then *never* saves changes.\n"
                       "#            The default save parameters must be restored by including them as args.\n"
                       "#    appendServerSaveParams(60*60,1);  /* save after 1 hour and 1 change */\n"
                       "#    appendServerSaveParams(300,100);  /* save after 5 minutes and 100 changes */\n"
                       "#    appendServerSaveParams(60,10000); /* save after 1 minute and 10000 changes */\n"
                       "SERVER_ARGS = --dir ~/mill_data --dbfilename dump.rdb --save 3600 1 --save 300 100 --save 60 10000\n"
                       "\n"
                       "[TASK]\n"
                       "TASK = milltask\n"
                       "CYCLE_TIME = 0.010\n"
                       "\n"
                       "[RS274NGC]\n"
                       "PARAMETER_FILE = ~/mill_data/emc.var\n"
                       "RS274NGC_STARTUP_CODE = G8 G17 G20 G90\n"
                       "\n"
                       "[EMCMOT]\n"
                       "EMCMOT = motmod\n"
                       "COMM_TIMEOUT = 1.0\n"
                       "COMM_WAIT = 0.010\n"
                       "SERVO_PERIOD = 1000000\n"
                       "\n"
                       "[HOSTMOT2]\n"
                       "# **** This is for info only ****\n"
                       "# DRIVER0=hm2_pci\n"
                       "# BOARD0=5i25\n"
                       "# BITFILE0 used by scripts\n"
                       "BITFILE0=mesa/tormach_mill2.bit\n"
                       "\n"
                       "[HAL]\n"
                       "HALUI = halui\n"
                       "HALFILE = tormach_mill_5i25.hal\n"
                       "POSTGUI_SHUTTLEXPRESS_HALFILE = shuttlexpress.hal\n"
                       "POSTGUI_HALFILE = postgui_tormach_mill_5i25.hal\n"
                       "\n"
                       "[TRAJ]\n"
                       "AXES = 4\n"
                       "COORDINATES = X Y Z A\n"
                       "MAX_ANGULAR_VELOCITY = 30.00\n"
                       "DEFAULT_ANGULAR_VELOCITY = 3.00\n"
                       "LINEAR_UNITS = inch\n"
                       "ANGULAR_UNITS = degree\n"
                       "CYCLE_TIME = 0.010\n"
                       "DEFAULT_VELOCITY = 1.5\n"
                       "MAX_LINEAR_VELOCITY = 4.0\n"
                       "NO_FORCE_HOMING = 1\n"
                       "\n"
                       "[EMCIO]\n"
                       "EMCIO = io\n"
                       "CYCLE_TIME = 0.100\n"
                       "TOOL_TABLE = ~/mill_data/tool.tbl\n"
                       "\n")

    mill_spindle = ("[SPINDLE]\n"
                    "LO_RANGE_MIN = %d\n"
                    "LO_RANGE_MAX = %d\n"
                    "LO_SCALE = %1.3f\n"
                    "HI_RANGE_MIN = %d\n"
                    "HI_RANGE_MAX = %d\n"
                    "HI_RANGE_SCALE = %1.3f\n"
                    "\n")
    # lo_min, lo_max, hi_min, hi_max, hi_range_scale, lo_scale
    # LO_SCALE converts RPM to Hz sent to control board where
    # maximum RPM is reached at 10900 Hz
    # low belt for 770 3250 RPM requires 10900 Hz to control board
    # needing 3.354 (10900/3250) for position-scale
    # low bet for 1100 at 2000 RPM requires 10900 Hz to control board
    # needing 5.450 (10900/2000) for position-scale
    # high belt settings are handled by the gearchange component
    # which scales down the RPM by the high to low ratio HI_RANGE_SCALE
    spindle_1100_s3 = (100, 2000, 5.450, 250, 5140,  2.575)
    spindle_1100_s2 = (100, 2000, 5.450, 250, 5140,  2.575)
    spindle_1100_s1 = (300, 1750, 5.450, 800, 4500,  2.575)
    spindle_770 =     (175, 3250, 3.354, 525, 10200, 3.140)
    #
    # LinuxCNC (rpm) => gearchange (reduces RPM in high gear) => (stepgen-freq) => VFD => spindle
    #
    # 1100:
    # low gear:  100-2000 rpm, 10900 Hz => 2000 rpm, 5.450 Hz/rpm
    # high gear: 250-5140 rpm, 10900 Hz => 5140 rpm
    #
    # 770:
    # low gear:  175-3250 rpm, 10900 Hz => 3250 rpm, 3.354 Hz/rpm
    # high gear: 525-10200 rpm, 10900 Hz => 10200 rpm
    #

    mill_axis_xyz = ("[AXIS_%d]\n"
                     "TYPE = LINEAR\n"
                     "HOME = %1.3f\n"
                     "MAX_VELOCITY = %1.3f\n"
                     "MAX_ACCELERATION = %2.1f\n"
                     "STEPGEN_MAXACCEL = %2.1f\n"
                     "SCALE = %5.1f\n"
                     "FERROR = %1.1f\n"
                     "MIN_FERROR = %1.3f\n"
                     "MIN_LIMIT = %1.3f\n"
                     "MAX_LIMIT = %1.6f\n"
                     "HOME_OFFSET = %1.3f\n"
                     "HOME_SEARCH_VEL = %1.3f\n"
                     "HOME_LATCH_VEL = %1.3f\n"
                     "HOME_IGNORE_LIMITS = YES\n"
                     "HOME_SEQUENCE = %d\n"
                     "\n")
    #                  type/home/maxv/maxa/stpgn/scale/ferr/mferr/minlim/maxlim/home_off/
    mill_axis_1100_s3_x = (0, 0.0, 1.833, 15.0, 18.0, 10000.0, 5.0, 2.5, 0.000001,   18.0, 0.0, -0.750, 0.050, 1)
    mill_axis_1100_s3_y = (1, 0.0, 1.833, 15.0, 18.0, 10000.0, 5.0, 2.5, -9.5,   0.000001, 0.0, 0.750, -0.050, 1)
    mill_axis_1100_s3_z = (2, 0.0, 1.500, 15.0, 18.0, -10000.0, 5.0, 2.5, -16.25, 0.000001, 0.0, 0.750, -0.050, 0)
    mill_axis_1100_s2_x = (0, 0.0, 1.500, 15.0, 18.0, 10000.0, 5.0, 2.5, 0.000001,   18.0, 0.0, -0.750, 0.050, 1)
    mill_axis_1100_s2_y = (1, 0.0, 1.500, 15.0, 18.0, 10000.0, 5.0, 2.5, -9.5,   0.000001, 0.0, 0.750, -0.050, 1)
    mill_axis_1100_s2_z = (2, 0.0, 1.083, 15.0, 18.0, -10000.0, 5.0, 2.5, -16.25, 0.000001, 0.0, 0.750, -0.050, 0)
    mill_axis_1100_s1_x = (0, 0.0, 1.083, 15.0, 18.0, 10000.0, 5.0, 2.5, 0.000001,   18.0, 0.0, -0.750, 0.050, 1)
    mill_axis_1100_s1_y = (1, 0.0, 1.083, 15.0, 18.0, 10000.0, 5.0, 2.5, -9.5,   0.000001, 0.0, 0.750, -0.050, 1)
    mill_axis_1100_s1_z = (2, 0.0, 1.083, 15.0, 18.0, -10000.0, 5.0, 2.5, -16.25, 0.000001, 0.0, 0.750, -0.050, 0)

    mill_axis_770_x =     (0, 0.0, 2.250, 15.0, 18.0, 10160.0, 5.0, 2.5, 0.000001,   14.0, 0.0, -0.750, 0.050, 1)
    mill_axis_770_y =     (1, 0.0, 2.250, 15.0, 18.0, 10160.0, 5.0, 2.5, -7.5,   0.000001, 0.0, 0.750, -0.050, 1)
    mill_axis_770_z =     (2, 0.0, 1.833, 15.0, 18.0, -10160.0, 5.0, 2.5, -13.25, 0.000001, 0.0, 0.750, -0.050, 0)

    mill_axis_a = ("[AXIS_%d]\n"
                   "TYPE = ANGULAR\n"
                   "WRAPPED_ROTARY = 1"
                   "HOME = %1.3f\n"
                   "MAX_VELOCITY = %1.3f\n"
                   "MAX_ACCELERATION = %2.1f\n"
                   "STEPGEN_MAXACCEL = %2.1f\n"
                   "SCALE = %5.1f\n"
                   "FERROR = %1.1f\n"
                   "MIN_FERROR = %1.3f\n"
                   "MIN_LIMIT = %1.3f\n"
                   "MAX_LIMIT = %1.6f\n"
                   "HOME_OFFSET = %1.3f\n"
                   "HOME_SEARCH_VEL = %1.3f\n"
                   "HOME_LATCH_VEL = %1.3f\n"
                   "HOME_IGNORE_LIMITS = YES\n"
                   "HOME_SEQUENCE = %d\n"
                   "\n")
    mill_axis_a_all = (3, 0.0, 30.0, 21.667, 1.08, 500.0, 1.0, 0.25, -99999.0, 99999.0, 0.0, 0.0, 0.0, 1)

    # lathe common INI section
    lathe_ini_common = ("[EMC]\n"
                        "MACHINE = tormach_lathe\n"
                        "DEBUG = 0\n"
                        "\n"
                        "[DISPLAY]\n"
                        "DISPLAY = tormach_lathe_ui.py\n"
                        "EDITOR = gedit\n"
                        "POSITION_OFFSET = RELATIVE\n"
                        "POSITION_FEEDBACK = ACTUAL\n"
                        "MAX_FEED_OVERRIDE = 1.2\n"
                        "INTRO_GRAPHIC = tormach_lathe_splash.gif\n"
                        "INTRO_TIME = 2\n"
                        "PROGRAM_PREFIX = ~/nc_files\n"
                        "INCREMENTS = .1in .05in .01in .005in .001in .0005in .0001in\n"
                        "LATHE = 1\n"
                        "GEOMETRY = -XZ\n"
                        "\n"
                        "[REDIS]\n"
                        "# IMPORTANT: redis-server has a bad side effect where if *any* arguments are provided\n"
                        "#            it clears the default save parameters and then *never* saves changes.\n"
                        "#            The default save parameters must be restored by including them as args.\n"
                        "#    appendServerSaveParams(60*60,1);  /* save after 1 hour and 1 change */\n"
                        "#    appendServerSaveParams(300,100);  /* save after 5 minutes and 100 changes */\n"
                        "#    appendServerSaveParams(60,10000); /* save after 1 minute and 10000 changes */\n"
                        "SERVER_ARGS = --dir ~/lathe_data --dbfilename dump.rdb --save 3600 1 --save 300 100 --save 60 10000\n"
                        "\n"
                        "[TASK]\n"
                        "TASK = milltask\n"
                        "CYCLE_TIME = 0.010\n"
                        "\n"
                        "[RS274NGC]\n"
                        "PARAMETER_FILE = ~/lathe_data/emc.var\n"
                        "RS274NGC_STARTUP_CODE = G7 G18 G20 G90\n"
                        "FEATURES = 64\n"
                        "\n"
                        "[EMCMOT]\n"
                        "EMCMOT = motmod\n"
                        "COMM_TIMEOUT = 1.0\n"
                        "COMM_WAIT = 0.010\n"
                        "SERVO_PERIOD = 1000000\n"
                        "\n"
                        "[HOSTMOT2]\n"
                        "# **** This is for info only ****\n"
                        "# DRIVER0=hm2_pci\n"
                        "# BOARD0=5i25\n"
                        "# BITFILE0 used by scripts\n"
                        "BITFILE0=mesa/tormach_lathe.bit\n"
                        "\n"
                        "[HAL]\n"
                        "HALUI = halui\n"
                        "HALFILE = load-shared-modules.hal\n"
                        "HALFILE = tormach_lathe_5i25.hal\n"
                        "POSTGUI_SHUTTLEXPRESS_HALFILE = shuttlexpress.hal\n"
                        "POSTGUI_HALFILE = postgui_tormach_lathe_5i25.hal\n"
                        "\n"
                        "[TRAJ]\n"
                        "AXES = 3\n"
                        "COORDINATES = X Z\n"
                        "LINEAR_UNITS = inch\n"
                        "ANGULAR_UNITS = degree\n"
                        "CYCLE_TIME = 0.010\n"
                        "DEFAULT_VELOCITY = 1.5\n"
                        "MAX_LINEAR_VELOCITY = 1.50\n"
                        "NO_FORCE_HOMING = 1\n"
                        "\n"
                        "[EMCIO]\n"
                        "EMCIO = io\n"
                        "CYCLE_TIME = 0.100\n"
                        "TOOL_TABLE = ~/lathe_data/tool.tbl\n"
                        "TOOL_CHANGE_WITH_SPINDLE_ON = 1\n"
                        "\n"
                        "[AXIS_0]\n"
                        "TYPE = LINEAR\n"
                        "MAX_VELOCITY = 1.5\n"
                        "MAX_ACCELERATION = 15.0\n"
                        "STEPGEN_MAXACCEL = 18.75\n"
                        "SCALE = 16933.333\n"
                        "FERROR = 1.0\n"
                        "MIN_FERROR = 0.1\n"
                        "MIN_LIMIT = -10.0\n"
                        "MAX_LIMIT = 10.0\n"
                        "\n"
                        "[AXIS_2]\n"
                        "TYPE = LINEAR\n"
                        "MAX_VELOCITY = 1.5\n"
                        "MAX_ACCELERATION = 15.0\n"
                        "STEPGEN_MAXACCEL = 18.75\n"
                        "SCALE = -16933.333\n"
                        "FERROR = 1.0\n"
                        "MIN_FERROR = 0.1\n"
                        "MIN_LIMIT = -14.0\n"
                        "MAX_LIMIT = 14.0\n"
                        "\n")

    def __init__(self):
        pass


    def generate_file(self, ini_filename, machine_type, machine_series):
        try:
            with open(ini_filename, 'w') as ini_file:
                # output the file contents
                ini_file.write(self.ini_revision)

                if machine_type == self.TYPE_LATHE:
                    # one lathe at the moment
                    ini_file.write('# Tormach Slant Bed Lathe\n\n')
                    ini_file.write(self.lathe_ini_common)

                else:
                    if machine_type == self.TYPE_MILL_770:
                        # 770 all series
                        ini_file.write('# Tormach PCNC 770 Series All\n\n')
                        spindle = self.mill_spindle % self.spindle_770
                        x_axis = self.mill_axis_xyz % self.mill_axis_770_x
                        y_axis = self.mill_axis_xyz % self.mill_axis_770_y
                        z_axis = self.mill_axis_xyz % self.mill_axis_770_z
                        a_axis = self.mill_axis_a % self.mill_axis_a_all

                    if machine_type == self.TYPE_MILL_1100:

                        if machine_series == self.SERIES_3:
                            ini_file.write('# Tormach PCNC 1100 Series 3\n\n')
                            spindle = self.mill_spindle % self.spindle_1100_s3
                            x_axis = self.mill_axis_xyz % self.mill_axis_1100_s3_x
                            y_axis = self.mill_axis_xyz % self.mill_axis_1100_s3_y
                            z_axis = self.mill_axis_xyz % self.mill_axis_1100_s3_z
                            a_axis = self.mill_axis_a % self.mill_axis_a_all

                        if machine_series == self.SERIES_2:
                            ini_file.write('# Tormach PCNC 1100 Series 2\n\n')
                            spindle = self.mill_spindle % self.spindle_1100_s2
                            x_axis = self.mill_axis_xyz % self.mill_axis_1100_s2_x
                            y_axis = self.mill_axis_xyz % self.mill_axis_1100_s2_y
                            z_axis = self.mill_axis_xyz % self.mill_axis_1100_s2_z
                            a_axis = self.mill_axis_a % self.mill_axis_a_all

                        if machine_series == self.SERIES_1:
                            ini_file.write('# TormachPCNC 1100 Series 1\n\n')
                            spindle = self.mill_spindle % self.spindle_1100_s1
                            x_axis = self.mill_axis_xyz % self.mill_axis_1100_s1_x
                            y_axis = self.mill_axis_xyz % self.mill_axis_1100_s1_y
                            z_axis = self.mill_axis_xyz % self.mill_axis_1100_s1_z
                            a_axis = self.mill_axis_a % self.mill_axis_a_all

                    ini_file.write(self.mill_ini_common)
                    ini_file.write(spindle)
                    ini_file.write(x_axis)
                    ini_file.write(y_axis)
                    ini_file.write(z_axis)
                    ini_file.write(a_axis)

        except IOError, ioex:
            print 'errno:', ioex.errno
            print 'err code:', errno.errorcode[ioex.errno]
            print 'err message:', os.strerror(ioex.errno)


if __name__ == "__main__":
    ini = tormach_ini_file()
    # dump one of everything for testing
    #ini.generate_file('tormach_mill_5i25_s3.ini', ini.TYPE_MILL_1100, ini.SERIES_3)
    #ini.generate_file('tormach_mill_5i25_s2.ini', ini.TYPE_MILL_1100, ini.SERIES_2)
    #ini.generate_file('tormach_mill_5i25_s1.ini', ini.TYPE_MILL_1100, ini.SERIES_1)
    #ini.generate_file('tormach_mill_5i25.ini', ini.TYPE_MILL_770,  ini.SERIES_ANY)
    #ini.generate_file('tormach_lathe_5i25.ini', ini.TYPE_LATHE,  ini.SERIES_ANY)

    # look at command line args for filename, machine type, and machine series
    if len(sys.argv) < 4:
        print("usage: %s filename 1100|770|LATHE 2|3" % sys.argv[0])
    else:
        if sys.argv[3] != '2' and sys.argv[3] != '3':
            print("usage: %s filename 1100|770|LATHE 2|3" % sys.argv[0])
            exit(1)
        if sys.argv[2] == '1100':
            machine_type = ini.TYPE_MILL_1100
        elif sys.argv[2] == '770':
            machine_type = ini.TYPE_MILL_770
        elif sys.argv[2] == 'LATHE':
            machine_type = ini.TYPE_LATHE
        else:
            print("usage: %s filename 1100|770|LATHE 2|3" % sys.argv[0])
            exit(1)

        machine_series = int(sys.argv[3])
        ini.generate_file(sys.argv[1], machine_type, machine_series)
        exit(0)
