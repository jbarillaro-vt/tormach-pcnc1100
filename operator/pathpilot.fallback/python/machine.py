# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import redis
import errors
import linuxcnc
import subprocess
from constants import *


class MachineConfig():

    # The .ini file within the [SPINDLE] section can optionally have a COLLET_TYPE key. Only currently
    # defined value is BT30_WITH_DOGS which when read through an ini object becomes that string.
    # Only define more values and add them to .ini file as actually needed rather than trying to guess
    # the future today.
    COLLET_BT30_WITH_DOGS = 'BT30_WITH_DOGS'
    COLLET_TTS            = 'TTS'
    COLLET_UNSPECIFIED    = 'Unspecified'


    _REDIS_KEY_4TH_AXIS = 'fourth_axis'

    def __init__(self, machineobj, configdict, redis_db, error_handler, inifile):
        # Model name is always pulled from the pathpilot.json values loaded up in the configdict
        self._machineobj = machineobj
        self._model_name = configdict['machine']['model']
        self._machine_class = configdict['machine']['class']
        self._sim = configdict['machine']['sim']
        self._spindle_collet_type = MachineConfig.COLLET_UNSPECIFIED
        self._in_rapidturn_mode = False
        self._supports_rapidturn = False
        self._error_handler = error_handler
        self._ecm1 = False
        self._door_lock = False
        self._supports_rapidturn = False
        self._has_limit_switches = True
        self._has_hard_stop_homing = False
        self._torstep = False
        self._spindle_reverse = True
        self._always_has_door_switch_wired = False
        self._supported_spindle_list = [ ]

        self.a_axis = None

        # The idea here is to get away from hard coding all over the place model numbers with specific attributes.
        # We do this in one place going forward - this MachineConfig class or future subclasses of it.
        # Then all the other code calls methods on this class to determine specific component variations that
        # a machine might have.  That makes it trivial to find all the places that look at spindle_type
        # for varying behavior for example.  Otherwise you're trying to search the entire code for
        # strange model number comparisons that are fragile to find.
        #
        # And try to create an attribute that captures the essence of the varying behavior that you need.
        # For example, the has_ecm1() method (vs. is model in (770M, 770MX, 1100M, 1100MX) type of logic)

        # Are we simulating this machine?
        redis_db.hset('machine_config', 'sim', str(self._sim))  # True or False in string form

        # Setup the collet type
        self._spindle_collet_type = inifile.find("SPINDLE", "COLLET_TYPE")
        if not self._spindle_collet_type:
            self._spindle_collet_type = MachineConfig.COLLET_UNSPECIFIED
        else:
            # there is a value - see if its in the range of what we know and support.
            if self._spindle_collet_type not in (MachineConfig.COLLET_BT30_WITH_DOGS, MachineConfig.COLLET_TTS):
                raise ValueError('Invalid [SPINDLE] COLLET_TYPE in ini file: {:s}'.format(self._spindle_collet_type))

        # Type of collet
        redis_db.hset('machine_config', 'spindle_collet_type', self._spindle_collet_type)

        # Does the spindle reverse?
        value = inifile.find("SPINDLE", "REVERSE_SUPPORTED")
        if value and value.upper() in ('NO', 'FALSE'):
            self._spindle_reverse = False

        # Hard stop homing or limit switches on this machine?  Its possible that a machine has both installed.
        # Currently, if that is the case, we always use hard stop homing for referencing.
        hardstop = inifile.find("AXIS_0", "HOME_HSTOP")
        if hardstop != None and hardstop.upper() == 'YES':
            self._has_limit_switches = False
            self._has_hard_stop_homing = True

        # The proper way to check for whether we are a mill, but running in RapidTurn mode is to
        # check the rapidturn key boolean value from pathpilot.json.
        self._in_rapidturn_mode = configdict['machine']['rapidturn']

        # The pathpilot.json model key value doesn't get whacked on when switching between mills and rapidturn lathe mode.
        # It is always accurate for what model of mill or lathe or whatever you have regardless of operation mode.

        if configdict['machine']['model'] in ('770M', '770M+', '1100M', '1100M+'):
            self._ecm1 = True
            self._door_lock = True
            self._supports_rapidturn = True

        elif configdict['machine']['model'] in ('770MX', '1100MX'):
            self._ecm1 = True
            self._door_lock = True
            self._supports_rapidturn = True

        elif configdict['machine']['model'] in ('1100-3+', '1100-3', '1100-2', '1100-1', '1100', '770+', '770'):
            self._ecm1 = False
            self._door_lock = False
            if configdict['machine']['rapidturn_generate_from']:
                self._supports_rapidturn = True

        elif configdict['machine']['model'] in ('440'):
            self._ecm1 = False
            self._door_lock = False
            self._supports_rapidturn = False  # not yet anyway
            self._always_has_door_switch_wired = True

        elif configdict['machine']['model'] in ('MysteryMachine'):
            self._ecm1 = False
            self._torstep = True
            self._door_lock = False
            self._supports_rapidturn = False  # not yet anyway
            self._always_has_door_switch_wired = True

        elif configdict['machine']['model'] in ('xsTECH Router'):
            self._ecm1 = False
            self._torstep = True
            self._door_lock = False
            self._supports_rapidturn = False
            self._always_has_door_switch_wired = True

        else:
            # Use the ini config file to decide
            line = inifile.find("HOSTMOT2", "BOARD")
            if line:
                self._ecm1 = (line.strip().upper() == 'ECM1')
            self._door_lock = False


        # Newer ini files specifically list the spindle types they support
        line = inifile.find("MACHINE_CONFIG", "SPINDLE_TYPE_SUPPORT")
        if line:
            options = line.split()  # white space separates options, the default is the first opion if there is more than one
            for option in options:
                if int(option) not in (SPINDLE_TYPE_STANDARD, SPINDLE_TYPE_SPEEDER, SPINDLE_TYPE_HISPEED, SPINDLE_TYPE_RAPID_TURN):
                    raise ValueError('Invalid [MACHINE_CONFIG] SPINDLE_TYPE_SUPPORT value in ini file: {:s}'.format(option))
                else:
                    self._supported_spindle_list.append(int(option))
        else:
            # Must be an older ini file - use the old logic.
            self._supported_spindle_list.append(SPINDLE_TYPE_STANDARD)
            if self._machine_class == 'mill':
                if self._model_name in ('1100M+', '1100M', '770M+', '770M', '1100-3', '1100-2', '1100-1', '1100', '770'):
                    self._supported_spindle_list.append(SPINDLE_TYPE_SPEEDER)

            if '1100' in self._model_name:
                # high speed spindle is supported in all variants of 1100
                self._supported_spindle_list.append(SPINDLE_TYPE_HISPEED)


        # A Axis support
        axislist = []
        line = inifile.find("MACHINE_CONFIG", "A_AXIS_SUPPORT")
        if line:
            options = line.split()   # white space separates the options, the default is the first option if there is more than one
            for option in options:
                if option not in A_AxisConfig.ALLOWED_REDIS_KEYS:
                    raise ValueError('Invalid [MACHINE_CONFIG] A_AXIS_SUPPORT value in ini file: {:s}'.format(option))
                else:
                    axislist.append(option)

        if len(axislist) > 0:
            self.a_axis = A_AxisConfig(self._machineobj.configure_a_axis, self._model_name, axislist, axislist[0], redis_db, self._error_handler, inifile)


        # ATC tray slot count
        slotcount = inifile.find("MACHINE_CONFIG", "ATC_GEN2_TRAY_SLOTS")
        if slotcount:
            try:
                value = int(slotcount)  # sanity check the value
            except ValueError:
                raise ValueError('Non-integer invalid [MACHINE_CONFIG] ATC_GEN2_TRAY_SLOTS in ini file: {:s}'.format(slotcount))
        else:
            slotcount = '?'
        redis_db.hset('machine_config', 'atc_gen2_tray_slots', slotcount)

        # ATC vfd reporting method
        vfdmethod = inifile.find("MACHINE_CONFIG", "ATC_GEN2_VFD_REPORTING")
        if vfdmethod:
            if vfdmethod not in ('LEVEL', 'PULSE', 'NONE'):
                raise ValueError('Invalid [MACHINE_CONFIG] ATC_GEN2_VFD_REPORTING in ini file: {:s}'.format(vfdmethod))
        else:
            vfdmethod = 'NONE'
        redis_db.hset('machine_config', 'atc_gen2_vfd_reporting', vfdmethod)


        # SmartCool hmount and vmount distances
        distance = inifile.find("MACHINE_CONFIG", "SMARTCOOL_VMOUNT_DISTANCE")
        if distance:
            try:
                value = float(distance)  # sanity check the value
            except ValueError:
                raise ValueError('Non-float invalid [MACHINE_CONFIG] SMARTCOOL_VMOUNT_DISTANCE in ini file: {:s}'.format(distance))
        else:
            distance = '?'
        redis_db.hset('machine_config', 'smartcool_vmount_distance', distance)

        distance = inifile.find("MACHINE_CONFIG", "SMARTCOOL_HMOUNT_DISTANCE")
        if distance:
            try:
                value = float(distance)  # sanity check the value
            except ValueError:
                raise ValueError('Non-float invalid [MACHINE_CONFIG] SMARTCOOL_HMOUNT_DISTANCE in ini file: {:s}'.format(distance))
        else:
            distance = '?'
        redis_db.hset('machine_config', 'smartcool_hmount_distance', distance)

        # which generation of ATC should we simulate?
        # this is convenient for simulated testing of firmware upgrades or other misconfiguration situations
        if self._sim:
            if self._ecm1 or self._model_name == '440':
                # The Z-Bot firmware only knows Pulse or Level for vfdmethod so map it
                vfd_firmware = 'Pulse'
                if vfdmethod in ('LEVEL', 'NONE'):
                    vfd_firmware = 'Level'
                version = 'Z-Bot Automatic Tool Changer II {} - VFD: {} - TOOLS: {}'.format(ATCFIRMWARE_VERSION, vfd_firmware, slotcount)
                redis_db.hset('machine_config', 'atc_board_sim_version', version)
                if self._spindle_collet_type == MachineConfig.COLLET_BT30_WITH_DOGS:
                    redis_db.hset('machine_config', 'atc_board_sim_version_long', 'BT30')
                else:
                    redis_db.hset('machine_config', 'atc_board_sim_version_long', '')
            else:
                redis_db.hset('machine_config', 'atc_board_sim_version', 'Z-Bot Automatic Tool Changer V3.3')
        else:
            redis_db.hdel('machine_config', 'atc_board_sim_version')
            redis_db.hdel('machine_config', 'atc_board_sim_version_long')

        # Jog step increments for g20 and g21 modes vary between machine classes
        if self._machine_class == 'router':
            self._jog_step_increments_g20 = (0.00025, 0.001, 0.01, 0.1)
            self._jog_step_increments_g21 = (0.010, 0.100, 1.0, 2.0)
        else:
            self._jog_step_increments_g20 = (0.0001, 0.001, 0.01, 0.1)
            self._jog_step_increments_g21 = (0.0025, 0.010, 0.1, 1.0)

        # Debug sanity checks...
        if self.in_rapidturn_mode():
            if self.a_axis:
                self._error_handler.write("Impossible 4th axis defined for RapidTurn!", ALARM_LEVEL_HIGH)


    def machine_class(self):
        return self._machine_class

    def has_limit_switches(self):
        return self._has_limit_switches

    def has_hard_stop_homing(self):
        return self._has_hard_stop_homing

    def has_ecm1(self):
        return self._ecm1

    def is_sim(self):
        return self._sim

    def in_rapidturn_mode(self):
        # are we a mill, but running in rapidturn mode currently?
        return self._in_rapidturn_mode

    def supports_rapidturn(self):
        # does this machine support having a rapidturn mounted on it?
        return self._supports_rapidturn

    def has_door_lock(self):
        return self._door_lock

    def spindle_collet_type(self):
        return self._spindle_collet_type

    def model_name(self):
        return self._model_name

    def has_torstep(self):
        return self._torstep

    def has_spindle_reverse(self):
        return self._spindle_reverse

    def shared_xy_limit_input(self):
        # these never have shared X/Y limit inputs
        # anything not an ecm1 or torstep
        return (not (self._ecm1 or self._torstep))

    def always_has_door_switch_wired(self):
        # 440 with MX3660 or Torstep has a jumper wire if it does not
        # have the enclosure door switch installed
        return self._always_has_door_switch_wired

    def supported_spindle_list(self):
        return self._supported_spindle_list

    def jog_step_increments_g20(self):
        assert len(self._jog_step_increments_g20) == 4, "UI expects 4 jog step levels"
        return self._jog_step_increments_g20

    def jog_step_increments_g21(self):
        assert len(self._jog_step_increments_g21) == 4, "UI expects 4 jog step levels"
        return self._jog_step_increments_g21


class A_AxisConfig():  # a.k.a. "4th axis", but we often cant use variables and constants starting with a numeral
                       # AND NOT TO BE CONFUSED with linuxcnc axis 4, as linuxcnc refers to 4th axis as axis 3

    #These constants are the strings used within redis to store user selected A axis (a.k.a "4th axis") accessories
    #AND within tormach_mill_base.ini
    ALLOWED_REDIS_KEYS = {'A_AXIS_4_INCH': '4\" 4th Axis',    #4th axis 4" harmonic drive (all mills)
        'A_AXIS_6_8_INCH': '6" or 8" 4th Axis',     #4th axis either 6" or 8" table (not for 440)
        'A_AXIS_440_RT' : '440 RapidTurn'}    #440_RT can be used as a 4th axis in plain mill mode, so far only on 440 mills


    def __init__(self, configure_a_axis_callback, machine_model, accessory_list, default_accessory, redis_obj, error_handler, inifile_obj):
        self._configure_a_axis_callback = configure_a_axis_callback
        self._machine_model = machine_model
        self._selected_4th_axis = None
        self._accessory_list = accessory_list
        self._4th_axis_default = default_accessory
        self._error_handler = error_handler
        self._redis = redis_obj
        self._inifile = inifile_obj

        self._selected_4th_axis = self._4th_axis_default
        if self._redis.hexists('machine_prefs', MachineConfig._REDIS_KEY_4TH_AXIS):
            self._selected_4th_axis = self._redis.hget('machine_prefs', MachineConfig._REDIS_KEY_4TH_AXIS)

        if self._selected_4th_axis not in self._accessory_list:
            msg = "invalid 4th axis %s for machine, setting to None" % self._selected_4th_axis
            self._error_handler.log(msg)
            self._selected_4th_axis = None


    def redis_to_human(self,redis_value):
        try:
            return A_AxisConfig.ALLOWED_REDIS_KEYS[redis_value]
        except:
            return None

    #select() selects the A axis (4 th axis) and returns None if error
    #     new_axis: The redis value of the selected 4th axis
    #
    #if passed a new_axis
        #returns the given selection if successful, and configures HAL to selection
        #returns None if error
    def select(self, new_axis):

        if len(self._accessory_list) == 0:
            return None

        if new_axis not in self._accessory_list:
            msg = "attempt to select invalid 4th axis %d for machine! attempting to use default" % new_axis
            self._error_handler.log(msg)
            new_axis = self._4th_axis_default

        self._redis.hset('machine_prefs', MachineConfig._REDIS_KEY_4TH_AXIS, new_axis)

        if new_axis != None: # we have a validated new_axis to configure/set
            if new_axis != self._selected_4th_axis:
                msg = "selecting 4th axis %s" % self.redis_to_human(new_axis)
                self._error_handler.log(msg)
                self._selected_4th_axis = new_axis #as far as PP GUI is concerned, we've setup this new_axis

                # do whatever needs to be done in hal or other stuff to configure the new chosen axis
                self._configure_a_axis_callback(new_axis)

        else:  # we only get here if no default has been defined for machine and invalid or no value is in redis. We do nothing
            self._error_handler.log("invalid 4th axis selection attempt!")

        return self._selected_4th_axis

    #returns the presently selected A axis (4th axis) redis value
    def selected(self):
        return self._selected_4th_axis

    def set_error_handler(self, error_handler):
        self._error_handler = error_handler

