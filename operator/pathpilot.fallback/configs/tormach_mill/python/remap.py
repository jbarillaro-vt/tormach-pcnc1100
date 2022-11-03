# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


#  zbot atc prolog for ngc tool change programming

#pylint: disable=import-error

#--------------------------------------------------------------------------
# define these BEFORE importing them from interpreter
# so that pylint doesn't false positive on undefined variable
# they will get overwritten by the interpreter from import syntax
INTERP_ERROR = 0
INTERP_OK = 0
INTERP_EXECUTE_FINISH = 0
TOLERANCE_EQUAL = 0
INVERSE_TIME = 0
#--------------------------------------------------------------------------


import commands
import time
import redis
import traceback
import emccanon
import datetime
import math
from alphanum import *
from copy import deepcopy
from interpreter import *
from stdglue import *
from constants import *  #goody bag of values from Tormach
import errors
import linuxcnc

from contextlib import contextmanager

_error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

throw_exceptions = 1 # raises InterpreterException if execute() or read() fail


@contextmanager
def disable_feed_override(interp_handle, exec_wrapper):
    """
    Save the current feed override setting and restore it after we're done a block of moves
    """
    last_p = interp_handle.params["_feed_override"]
    exec_wrapper("M50 P0")
    yield None
    exec_wrapper("M50 P{:d}".format(int(last_p)))


@contextmanager
def disable_speed_override(interp_handle, exec_wrapper):
    """
    Save the current speed override setting and restore it after we're done a block of moves
    """
    last_p = interp_handle.speed_override
    exec_wrapper("M51 P0")
    yield None
    exec_wrapper("M51 P{:d}".format(int(last_p)))


@contextmanager
def absolute_distance_mode(interp_handle, exec_wrapper):
    """
    Save the current speed override setting and restore it after we're done a block of moves
    """
    # Need the original mode, not the current mode with overrides
    prev_mode = interp_handle.distance_mode
    exec_wrapper("G90")
    yield None

    # DISTANCE_MODE gets defined by interpmodule.cc about line 808 using Boost from C++.
    #pylint: disable=undefined-variable
    if prev_mode == DISTANCE_MODE.MODE_INCREMENTAL:
        exec_wrapper("G91")


def zbotatc_utility_prolog(self, **words):
    pass


def save_user_modals_M80 (self, **words):
    #----------------------------------------------------------------------------------
    #  various Tormach procedures change the motion mode, feed rate, and override status
    #   this custom save M code save important user context globally.  M70, and M72, normally
    #   used for this function, do not preserve values globally, and therefore cannot be used
    #   restore state before a low level subroutine aborts execution
    #-------------------------------------------------------------------------------------
    if self.task == 0:
        return INTERP_OK

    if not self.M80_state:
        self.params["_global_saved_user_G91"]        = self.params["_incremental"]   #1 for G1, 0 for G90
        self.params["_global_saved_user_feed"]       = self.params["_feed"]          #F value
        self.params["_global_saved_feed_enable"]     = self.params["_feed_override"] #enabled or disabled
        self.params["_global_saved_metric"]          = self.params["_metric"]        #imperial or metric
        self.params["_global_saved_speed_enable"]    = self.params["_speed_override"]
        self.params["_global_saved_tool_offset_applied"] = self.params["_tool_offset"]

        _error_handler.log("M80 save : I({}) F({}) FO({}) M({}) SO({})".format(self.params["_incremental"], \
                                                                       self.params["_feed"], \
                                                                       self.params["_feed_override"], \
                                                                       self.params["_metric"],\
                                                                       self.params["_speed_override"]))
        self.M80_state = True
    else:
        _error_handler.log("M80 context save, but already have saved context that hasn't been restored yet with M81 that would be lost so ignoring...")

    return INTERP_OK


def restore_user_modals_M81 (self, **words):
    #----------------------------------------------------------------------------------
    #  ham and eggs -
    #   restore user state saved in a prior M80  - note this is for INTERNAL USEby Tormach.
    #   Failure to set valid values in M80 results in defaults settings . See top level
    #   Not to be release to the public
    #-------------------------------------------------------------------------------------

    if self.task == 0:
        return INTERP_OK

    if self.M80_state:
        #restore users prior motion type
        if self.params["_global_saved_user_G91"] == 1.0 :
            self.execute ("G91")
        else:
            self.execute ("G90")

        #restore users prior feed rate
        self.execute ("F "+ str(self.params["_global_saved_user_feed"]) )

        #restore users feed override enablement
        if self.params["_global_saved_feed_enable"] == 1.0 :
            self.execute ("M50 P1")
        else:
            self.execute ("M50 P0")

        #restore users speed override enablement

        if self.params["_global_saved_speed_enable"] == 1.0 :
            self.execute ("M51 P1")
        else:
            self.execute ("M51 P0")

        #restore users metric/imperial thing
        if  self.params["_global_saved_metric"] == 1.0:
            self.execute ("G21")
        else:
            self.execute ("G20")

        if self.params["_global_saved_tool_offset_applied"] != 0.0:
            self.execute("G43")

        self.M80_state = False
        _error_handler.log("M81 restore : I({}) F({}) FO({}) M({}) SO({})".format(self.params["_incremental"], \
                                                                           self.params["_feed"], \
                                                                           self.params["_feed_override"], \
                                                                           self.params["_metric"],\
                                                                           self.params["_speed_override"]))
    else:
        _error_handler.log("User context restore requested without prior M80, ignoring......")

    return INTERP_OK



def zbotatc_M61 (self, **words):
    if self.task == 0:
        return INTERP_OK
    #-------------------------------------------------------------------
    #  This will recurse on the interpreter and execute the stock M61 code
    #   but it will also record changes in REDIS.  Every single active tool change
    #   in Tormach's implementation uses the M61 command,  Remap enforces Q param is passed
    #
    #--------------------------------------------------------------------

    tool_num = int (words['q'])
    if tool_num < 0:
        self.set_errormsg("Need non-negative Q-word to specify tool number with M61")
        return INTERP_ERROR

    self.current_pocket = tool_num
    emccanon.CHANGE_TOOL_NUMBER(tool_num)  #tool number always = pocket number in Tormach land

    self.tool_change_flag = True
    # instead of throwing a queue buster here to get the new tool info into the spindle
    # we do it here -- if we do not then the G43 issued immediately after M61 Qtool_num
    # on Reset button callback does not fetch the new tool length etc. into the spindle pocket
    self.current_tool = tool_num
    if tool_num > 0:
        self.tool_table[0] = self.tool_table[tool_num]
    self.set_tool_parameters()

    # I once saw in the log the redis.save() method toss an exception
    # of redis.exceptions.ResponseError: Background save already in progress
    # RedisError is the base class of all/most of everything redis can raise
    # so use that.
    try:
        self.redis.hset('machine_prefs', 'active_tool', tool_num)
        self.redis.save()   #force all data out
        _error_handler.log("M6: Active Tool Saved in DB: T{}".format(tool_num))

    except redis.exceptions.RedisError as e:
        msg = "{0} occured, these were the arguments:\n{1!r}".format(type(e).__name__, e.args)
        _error_handler.log("ATC: caught a RedisError during save attempt: {:s}".format(msg))


def zbotatc_M6_prolog(self, **words):
    if self.task == 0:
        # this is the preview that is run when the file is loaded
        # because we remapped M6, the python GLCanon.change_tool() method is never called.
        # but we want to use that to easily build a list of all tools that are used within a program
        # at preview time.  So drive this callback manually during preview and let that side of things keep track
        # of it since it will know when the preview is complete after the load (and we don't).
        emccanon.CHANGE_TOOL(self.selected_tool)
        return INTERP_OK

    if not self.ini:
        # we can't do this in toplevel.py because the UI sets this key in redis and it hasn't done that
        # yet when it runs, but don't need to do this every time.
        inifilepath = self.redis.hget('machine_prefs', 'linuxcnc_inifilepath')
        self.ini = linuxcnc.ini(inifilepath)
        # what type of collet do we have?
        # known values are None and "BT30_WITH_DOGS"
        self.collettype = self.ini.find("SPINDLE", "COLLET_TYPE")
        if self.collettype == "BT30_WITH_DOGS":
            self.params["_spindle_orient_needed"] = 1.0
        else:
            self.params["_spindle_orient_needed"] = 0.0

    if self.cutter_comp_side > 0:
        self.set_errormsg('Cannot change tools with cutter compensation enabled')
        return INTERP_ERROR

    # Save off machine stats on orienting from last tool change as we have redis access
    self.redis.hset('machine_stats', 'orient_success_count', str(self.params["_orient_success_count"]))
    self.redis.hset('machine_stats', 'orient_fail_count', str(self.params["_orient_fail_count"]))
    self.redis.hset('machine_stats', 'orient_retry_count', str(self.params["_orient_retry_count"]))

    try:
        #get old tool and new tools set up
        self.params["_old_tool"] = self.params["_current_tool"]
        self.params["_new_tool"] = self.selected_tool
        if self.params["_old_tool"] == -1:
            self.params["_old_tool"] = 0   #little quirk of lcnc at startup

        #for slot dictionary lookups - interp keeps these as floats, redis as strings- don't want any decimal points
        stringed_old_tool = '{:d}'.format(int(self.params["_old_tool"]))
        stringed_new_tool = '{:d}'.format(int(self.params["_new_tool"]))

        #OK lets see if tray load positon requested - always M6 T0 Q-1
        if 'q' in words and words['q']== -1.0 and self.params["_new_tool"] == 0.0:
            self.params ["_go_to_tray_load"] = 1.0
            _error_handler.log("Tool Change - Go To Tray Load Requested")
        else:
            self.params ["_go_to_tray_load"] = 0.0


        #for testing and debugging
        _error_handler.log("Tool Change - New Tool {} Old Tool {}".format(self.params["_new_tool"], self.params["_old_tool"]))


        if self.params["_new_tool"] == self.params["_old_tool"]\
        and self.params ["_go_to_tray_load"] != 1.0:    #just exit - do nothing in NGC , just M5
            #print ("remap - manual tool change initiated")
            self.params["_mode"] = -1.0    #set mode to exit NGC procedure which REMAP will now call
            return INTERP_OK              #will now pass control to NGC, which will exit

        # retrieve tool change type, and tool changer data items for redis

        try:
            toolchange_type = self.redis.hget("machine_prefs", "toolchange_type")
            self.pocket_dict = self.redis.hgetall('zbot_slot_table')
        except:
            self.pocket_dict = dict()
            toolchange_type = MILL_TOOLCHANGE_TYPE_REDIS_MANUAL

        #print ('remap - toolchange type :', toolchange_type )

        if toolchange_type == MILL_TOOLCHANGE_TYPE_REDIS_MANUAL:
            for i in range (self.atc_tray_tools):
                self.pocket_dict[str(i)] = '0'

        #---------------------------------------------------------
        #        find pockets from imported redis data
        #---------------------------------------------------------
        self.atc_tray_tools = self.hal["atc-tools-in-tray"]
        #print self.hal["atc-tools-in-tray"],"TOOLS IN TRAY FROM REMAP"
        self.params["_old_slot"] = -1.0  #not found default
        self.params["_new_slot"] = -1.0  #not found defalut

        for ix in range(self.atc_tray_tools):  #run the tray
            if self.params["_new_tool"] != 0.0 and self.pocket_dict[str(ix)] == stringed_new_tool:
                self.params["_new_slot"] = float(ix)
            if self.params["_old_tool"] != 0.0 and self.pocket_dict[str(ix)] == stringed_old_tool:
                self.params["_old_slot"] = float(ix)

       # no one really cares about this value.  Commented out
       # _error_handler.log("Tool Change - New Slot {}  Old Slot {}".format(self.params["_new_slot"], self.params["_old_slot"]))

        #Manual changes have no slots for new or old, even if atc is active - it's the same
        #Go to tray load when T0 is active comes here too because there is no stow or fetch
        #operation needed. In this case we force it through the auto change anyway
        if (self.params["_old_slot"] == -1 and self.params["_new_slot"] == -1)\
           and (self.params ["_go_to_tray_load"] != 1.0):

            self.params["_mode"] = -1.0    #set mode for NGC procedure to only prompt in
            #print ("remap - manual tool change initiated")

            return INTERP_OK                #pop right out since no automation is required


        #Some internal housekeeping for ATC
        #see if Z axis is homed, and tool change location reasonable


        if toolchange_type == MILL_TOOLCHANGE_TYPE_REDIS_ZBOT:

            # make sure Z axis is referenced
            if not self.hal['axis.2.homed']:
                self.set_errormsg('ATC - Z axis not referenced')
                return INTERP_ERROR

            # scale move locations for G53s in NGC routines
            #see if change z was set by user - GUI stores this data
            try:
                self.change_z = float(self.redis.hget('zbot_slot_table', 'tool_change_z'))
                zmin = -4.5
                zmax = -1.4
                if (self.change_z > zmax or self.change_z < zmin):   # gotta be in the zone, man
                    self.set_errormsg('ATC tool change Z ({:f}) is out of range, must be between {:f} and {:f}'.format(self.change_z, zmin, zmax))
                    return INTERP_ERROR
            except:
                self.set_errormsg('ATC tool change Z location not set')
                return INTERP_ERROR




            #setup units are defined in inches, but need conversion to program mode G20/21

            self.compression =     ATC_COMPRESSION      #squish constant SET TO 0 for IMTS BT30
            self.blast_distance =  ATC_BLAST_DISTANCE      #distance from tool holder rim
            self.tool_shank_jog =  ATC_SHANK_JOG_TTS           #tool shank height
            self.jog_speed =       ATC_JOG_SPEED           #default slow speed for TTS straight shank
            self.up_a_bit  =       ATC_UP_A_BIT            # short distance to get tool tip off work

            #Spindle specific stuff

            if int(self.redis.hget('machine_prefs', 'spindle_type')) == SPINDLE_TYPE_HISPEED:
                self.tool_shank_jog = ATC_SHANK_JOG_ISO20     #give it some more room for ISO 20

            # what type of spindle do we have?
            if self.params["_spindle_orient_needed"] == 1.0:

                self.tool_shank_jog = ATC_SHANK_JOG_BT30     #Set BT30 distance
                self.compression = 0.0                       #Zero compression distance
                self.jog_speed = ATC_TAPER_TOOLING_SPEED     #Let's push it a bit
                self.params["_tool_change_Z_setup"] = self.change_z #set up units
            # now scale whatever tooling relative to metric

            scale_factor = get_linear_scale(self)
            self.params["_tool_change_Z"] =  self.change_z * scale_factor #in user units
            self.params["_blast_distance"] = self.blast_distance* scale_factor
            self.params["_compression"]=     self.compression * scale_factor
            self.params["_shank_height"]=    self.tool_shank_jog * scale_factor
            self.params["_jog_speed"] =      self.jog_speed * scale_factor
            self.params["_shank_height"]=    self.tool_shank_jog * scale_factor
            self.params["_up_a_bit"] =       self.up_a_bit * scale_factor

            # tells NGC to execute full auto procedure
            self.params["_mode"] = 0

            #print ("remap - auto change initiated")

        return INTERP_OK

    except Exception as e:
        traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
        _error_handler.log("Exception in M6 prolog.  {}".format(traceback_txt))
        self.set_errormsg("M6/change_prolog: %s" % (e))
        return INTERP_ERROR



def smart_cool_M8 (self,**words):


    if self.task == 0: return INTERP_OK


    remember_radius = self.cutter_comp_radius
    remember_comp = self.cutter_comp_side

    if self.cutter_comp_side > 0:
        self.execute ('G40')

    #pulse analog out for .5 seconds - .3 sec added in at end

    self.execute ('M68 E29 Q1.0')   #1.0 is M8

    if 'p' in words:
        self.execute ('M68 E30 Q' + str(words['p']))  #set tip offset
    else  :
        self.execute ('M68 E30 Q583.9')               #easter egg for Z0

    if 'q' in words:
        self.execute ('M68 E27 Q' + str(words['q']))  #pulsing interval
    else  :
        self.execute ('M68 E27 Q0.0')               #no pulsing

    if 'r' in words:
        self.execute ('M68 E28 Q' + str(words['r']))  #set oscillation 0= off, + or - oscillate
    else :
        self.execute ('M68 E28 Q0' )

    if 'e' in words:
        self.execute ('M68 E26 Q' + str(words['e']))  #set z0 offset 0= off
    else :
        self.execute ('M68 E26 Q0' )


    emccanon.DWELL(.3)     #hold the pulse to make sure it's seen by GUI
    self.execute ('M68 E29 Q0.0')

    if remember_comp == 2:
        self.execute ('G41')
        self.cutter_comp_radius = remember_radius
    if remember_comp == 1:
        self.execute ('G42')
        self.cutter_comp_radius = remember_radius


    #open flood gates
    emccanon.FLOOD_OFF() #make sure gui picks up transition
    emccanon.DWELL(.1)
    emccanon.FLOOD_ON()

    return INTERP_OK


def smart_cool_M9 (self,**words):
    if self.task == 0: return INTERP_OK

    # pulse closed flood gates
    emccanon.FLOOD_ON()   #make sure gui picks up transition
    emccanon.DWELL(.1)
    emccanon.FLOOD_OFF()

    #pulse closed air gates
    emccanon.MIST_ON()   #make sure gui picks up transition here too
    emccanon.DWELL(.1)
    emccanon.MIST_OFF()



    remember_radius = self.cutter_comp_radius
    remember_comp = self.cutter_comp_side

    if self.cutter_comp_side > 0:
        self.execute ('G40')

    # pulse pin 29 so we know that a coolant M word was hit - checked by hal schnozz loop


    self.execute ('M68 E29 Q3.0')   #3.0 is M9
    emccanon.DWELL(.3)            #make sure hal sees this M
    self.execute ('M68 E29 Q0.0')   #3.0 is M9


    #reset coolant modes for Q,pulsing R,reciprocating, P,zero mode, E z offset

    self.execute ('M68 E26 Q0.0')           #reset z offset.   E  word
    self.execute ('M68 E27 Q0.0')           #reset reciprocation.   Q  word
    self.execute ('M68 E28 Q0.0')           #reset recip. R  word
    self.execute ('M68 E30 Q583.9')         #reest to Z0 mode.P  word

    if remember_comp == 2:
        self.execute ('G41')  #restore user's settings
        self.cutter_comp_radius = remember_radius

    if remember_comp == 1:
        self.execute ('G42')   #restore user's settings
        self.cutter_comp_radius = remember_radius

    return INTERP_OK


def smart_cool_M7 (self,**words):
    if self.task == 0: return INTERP_OK

    remember_radius = self.cutter_comp_radius
    remember_comp = self.cutter_comp_side

    if self.cutter_comp_side > 0:
        self.execute ('G40')

    #pulse analog out for .2 seconds

    self.execute ('M68 E29 Q2.0')   #2.0 is M7
    emccanon.DWELL(.2)
    self.execute ('M68 E29 Q0.0')

    if 'p' in words:
        self.execute ('M68 E30 Q' + str(words['p']))  #set tip offset
    else  :
        self.execute ('M68 E30 Q583.9')               #easter egg for Z0

    if 'q' in words:
        self.execute ('M68 E27 Q' + str(words['q']))  #set pulsing interval
    else  :
        self.execute ('M68 E27 Q0.0')               #no pulsing

    if 'r' in words:
        self.execute ('M68 E28 Q' + str(words['r']))  #set oscillation 0= off, + or - oscillate
    else :
        self.execute ('M68 E28 Q0' )

    if 'e' in words:
        self.execute ('M68 E26 Q' + str(words['e']))  #set z0 offset 0= off
    else :
        self.execute ('M68 E26 Q0' )

    if remember_comp == 2:
        self.execute ('G41')
        self.cutter_comp_radius = remember_radius
    if remember_comp == 1:
        self.execute ('G42')
        self.cutter_comp_radius = remember_radius

    #open air gates
    emccanon.MIST_OFF() #make sure gui picks up transition
    emccanon.DWELL(.1)
    emccanon.MIST_ON()

    return INTERP_OK



def digital_io_output_on_synched_M62 (self,**words):
    emccanon.SET_MOTION_OUTPUT_BIT(int(words['p']))
    return INTERP_OK

def digital_io_output_off_synched_M63 (self,**words):
    emccanon.CLEAR_MOTION_OUTPUT_BIT(int(words['p']))
    return INTERP_OK

def digital_io_output_on_immediate_M64 (self,**words):
    emccanon.SET_AUX_OUTPUT_BIT(int(words['p']))
    return INTERP_OK

def digital_io_output_off_immediate_M65 (self,**words):
    emccanon.CLEAR_AUX_OUTPUT_BIT(int(words['p']))
    return INTERP_OK

def io_input_M66(self,**words):

    wait_type = 0 #default to type immediate

    if 'q' in words :
        wait_time = (words['q'])

    if 'l' in words:
        if int(words['l']) >= 0 and int(words['l']) < 5:
            wait_type = int(words['l'])   #if user specifies one
        else :
            return 'M66 wait type invalid, must be positive integer between 0 and 4'

    pin_type = 2     #default to no pin type

    if 'p' in words and int(words['p']) >= 0:
        pin_number = int(words['p'])
        pin_type = 1       #set pin type to digital

    if 'e' in words and  int(words['e']) >= 0:
        pin_number = int(words['e'])
        pin_type = 0       #set pin type to analog
        wait_type = 0      #force wait type to immediate for analog

    if pin_type == 2:
        return 'M66 requires pin number in either P or E word'

    wait_time = 0.0
    ret = emccanon.WAIT(pin_number,pin_type,wait_type,wait_time)


    if ret == 0 :

        self.input_flag  = True
        self.input_index = pin_number
        if pin_type == 1 :
            self.input_digital = True
        else :
            self.input_digital = False


    return INTERP_OK


def g300(self, **words):
    if self.task == 0: return INTERP_OK

    text = ''
    for key in words:
        text += "word '%s' = %f   " % (key, words[key])
    _error_handler.log('remapped g30: {}'.format(text))

    # get machine G30 position in current G20/21 units
    x = self.params[5181] * get_linear_scale(self)
    y = self.params[5182] * get_linear_scale(self)
    z = self.params[5183] * get_linear_scale(self)

    # an axis must be referenced only if that axis is to be moved
    g30m998_move_z_only = self.redis.hget('machine_prefs', 'g30m998_move_z_only')

    # unconditionally change motion mode to G90 to prevent stack underrun error
    self.execute('G90')

    if g30m998_move_z_only == 'True':
        # other words on this line are ignored because we're doing Z only, per settings screen
        position = ' Z%.4f' % z
        _error_handler.log('G53 G0 {}'.format(position))
        self.execute('G53 G0' + position)
        # done

    else:
        # handle easy case - no words on line
        if len(words) == 0:
            position = 'X%.4f Y%.4f Z%.4f' % (x, y, z)
            self.execute('G53 G0' + position)

        else:
            # there are coordinates supplied on the G30 line.
            # G0 to these coordinates, then G0 to G30 position
            position = ''
            if 'x' in words:
                position += ' X%.4f' % words['x']

            if 'y' in words:
                position += ' Y%.4f' % words['y']

            if 'z' in words:
                position += ' Z%.4f' % words['z']

            _error_handler.log('G0 {}'.format(position))
            self.execute('G0' + position)

            # Now go to the G30 (absolute) position
            position = 'X%.4f Y%.4f Z%.4f' % (x, y, z)
            self.execute('G53 G0' + position)

    return INTERP_OK

def g470(self, **words):
#   if self.task == 0: return INTERP_OK
    _error_handler.log('....remapped g47: self.task is: %d' % (self.task))

#   #sn_call = 'o<byname> call [456]'
#   self.execute(sn_call)
#   self.execute('o<byname> call [456]')
    decimals = 4
    try:
        if not hasattr(self,'redis'): self.redis = redis.Redis()
        current_sn = self.redis.hget('machine_prefs', 'current_engraving_sn')
        current_sn_length = len(current_sn)
        decimals = decimals if current_sn_length == 0 else current_sn_length
        current_sn = int(current_sn)
    except:
        current_sn = 1

    # setup default values x,y,Z,q,d
    position_nX = self.params[5420]
    position_nY = self.params[5421]
    position_nZ = self.params[5422]
    alphanum._metric_factor = 25.4 if self.params['_metric'] == True else 1.0
    _error_handler.log('alphanum._metric_factor = %.1f' % (alphanum._metric_factor))
    x_size_min, y_size_min = alphanum.minimum_size()
    x_nSize, y_nSize = alphanum.extents()

    # init from required params
    position_nCutting_Z = words['z']
    position_nRetract = words['r']
    position_retract = 'G0 Z%.4f' % (position_nRetract)


    # get all the params...
    if 'x' in words:
        position_nX = words['x']
    if 'y' in words:
        position_nY = words['y']
    if 'd' in words:
        decimals = int(words['d'])
    if 'p' in words:
        x_nSize = words['p']
    if 'q' in words:
        y_nSize = words['q']

    # validation...
    if position_nCutting_Z >= position_nRetract:
        self.set_errormsg("G47 retract 'R' must be greater than 'Z'")
        return INTERP_ERROR

    if x_nSize < x_size_min:
        scale_err = "G47 'p' x size must be greater than %.3f" % (x_size_min)
        self.set_errormsg(scale_err)
        return INTERP_ERROR
    if y_nSize < y_size_min:
        scale_err = "G47 'q' y size must be greater than %.3f" % (y_size_min)
        self.set_errormsg(scale_err)
        return INTERP_ERROR

    # decimal check ....
    sn_decimals = int(math.log10(current_sn)) + 1
    decimals = decimals if sn_decimals <= decimals else sn_decimals

    _error_handler.log('g47 current_sn: %d' % current_sn)
    _error_handler.log('g47 sn_decimals: %d' % sn_decimals)
    _error_handler.log('g47 decimals: %d' % decimals)

    # decompose the number into array with leading '0's
    tmp_sn = current_sn
    digits = [0] * decimals
    current_text_length = decimals
    while tmp_sn:
        decimals -= 1
        digits[decimals] = int(tmp_sn % 10)
        tmp_sn //= 10

    # do not issue an X,Y move unless above or equal to
    # the retract position
    positionXY = 'G0 X%.4f Y%.4f' % (position_nX, position_nY)
    if position_nZ < position_nRetract:
        _error_handler.log(position_retract)
        self.execute(position_retract)
        _error_handler.log(positionXY)
        self.execute(positionXY)
    else:
        _error_handler.log(positionXY)
        self.execute(positionXY)
        _error_handler.log(position_retract)
        self.execute(position_retract)

    gcode_generator = alphanum(self,
                               x_nSize, y_nSize,
                               position_nCutting_Z, position_nRetract )

    # render the digits...
    for n,i in enumerate(digits):
        kerning_nX = gcode_generator.generate(i, position_nX, position_nY)
        position_nX += kerning_nX

    if self.task != 0: current_sn += 1
    self.params['_current_engraving_sn'] = current_sn
    current_sn_length = len(str(current_sn))
    while current_sn_length < current_text_length:
        current_sn = "0%s" % current_sn
        current_sn_length += 1

    self.redis.hset('machine_prefs', 'current_engraving_sn', current_sn)
    return INTERP_OK


def m998(self, **words):
    if self.task == 0: return INTERP_OK
    _error_handler.log('remapped m998: calls remapped G30 with no words')

    save_dict = deepcopy(words)
    words.clear()
    ret_val =  g300(self)
    words = deepcopy(save_dict)
    return ret_val

    # much existing Mach3 g-code has G50 to reset scaling
    # implement G50 here to prevent error and also cancel rotation
def g500(self, **words):
    if self.task == 0: return INTERP_OK
    _error_handler.log('remapped g50: G10 L2 P0 R0 to cancel current coordinate system rotation')

    self.execute('G10 L2 P0 R0')
    return INTERP_OK


def get_initial_position_string(words, tap_axis):
    positions = []
    for ax in ('x', 'y', 'z', 'u', 'v', 'w'):
        if ax is not tap_axis and ax in words:
            positions.append('{axis_name}{pos:.4f}'.format(
                axis_name=ax.upper(),
                pos=words[ax]
            ))

    pos_cmd = ('G0 ' + ' '.join(positions)) if positions else ''

    return pos_cmd


def wraps_interp_execute_with_log(interp_handle, caller):
    def execute(cmd):
        if interp_handle.debugmask & 0x00008000:
            print(' {}: {}'.format(caller, cmd))
        return interp_handle.execute(cmd)
    return execute


def soft_tapping_cycle(self, words, tap_axis, left_hand=False):
    """
    Executes a "soft" tapping cycle (for machines without a spindle encoder). This requires a
    tension-compression tap holder.

    :param self: The interpreter handle (called "self" for historical reasons)
    :param words: G-code words for this tap cycle (augmented with "sticky" words)
    :param tap_axis: The axis along which the tapped hole is oriented (one of XYZUVW)
    :param left_hand: Flag indicating if threads are left-handed
    """
    if self.debugmask & 0x00008000:
        _error_handler.log('Soft tapping cycle')

    # Determine feed rate based on thread pitch
    tap_feed = words.get('k', 0.0) * self.speed or self.feed_rate

    # Allow the user to override the dwell calculation with a P word on the G84 block
    dwell_time = words.get('p', self.speed * 0.001)  # default is half a second per thousand rpm

    forward_spindle_cmd = 'M4' if left_hand else 'M3'
    retract_spindle_cmd = 'M3' if left_hand else 'M4'

    # Go to the X/Y location of the hole to be tapped
    # There can be an x, y, or both x and y words on the block

    pos_cmd = get_initial_position_string(words, tap_axis)

    # tap depth and R should be 'sticky' positions, specified in the first G74/G84 line that starts the block
    z_depth_word = '{tap_axis}{depth:.4f}'.format(
        tap_axis=tap_axis,
        depth=words[tap_axis],
    )
    r_level_word = '{tap_axis}{retract_height:4f}'.format(
        tap_axis=tap_axis,
        retract_height=words['r'],
    )

    # if we're in G99 (retract to R plane), the work is done
    # but if we're in G98, need to retract further to the initial Z level
    # as long as it is higher than R
    #
    # retract_mode is an enum from interp_internal.hh
    #
    # typedef enum
    # { R_PLANE, OLD_Z }
    # RETRACT_MODE
    #
    # therefore R_PLANE == 0 and OLD_Z == 1
    g98 = self.retract_mode == 1

    execute = wraps_interp_execute_with_log(self, 'G74' if left_hand else 'G84')
    with absolute_distance_mode(self, execute), disable_feed_override(self, execute), disable_speed_override(self, execute):
        if pos_cmd:
            execute(pos_cmd)
        execute(forward_spindle_cmd)
        execute('G0 ' + r_level_word)  # Rapid to retract height level
        execute('G1 F%0.4f %s' % (tap_feed, z_depth_word))
        execute(retract_spindle_cmd)
        execute('G4 P%.2f' % dwell_time)
        execute('G1 F%0.4f %s' % (tap_feed, r_level_word))
        execute(forward_spindle_cmd)
        if g98 and (words['initial_height'] > words['r']):
            execute('G0 {tap_axis}{initial_height:.4f}'.format(
                tap_axis=tap_axis,
                initial_height=words['initial_height'],
            ))

    return INTERP_OK


def rigid_tapping_cycle(self, words, tap_axis, left_hand=False):
    """
    Executes a rigid tapping cycle (for machines with a spindle encoder). Can use rigidly-mounted taps, though
     some compliance in the holder may reduce the risk of tap breakage.
    """
    if self.debugmask & 0x00008000:
        _error_handler.log('Rigid tapping cycle')

    # Determine tap pitch based on user-provided pitch, or implicitly from feed / speed
    tap_pitch = words.get('k', 0.0) or self.feed_rate / self.speed

    forward_spindle_cmd = 'M4' if left_hand else 'M3'
    # Retract is automatic for rigid tapping

    # if we're in G99 (retract to R plane), the work is done
    # but if we're in G98, need to retract further to the initial height
    # as long as it is higher than R
    #
    # retract_mode is an enum from interp_internal.hh
    #
    # typedef enum
    # { R_PLANE, OLD_Z }
    # RETRACT_MODE
    #
    # therefore R_PLANE == 0 and OLD_Z == 1
    g98 = self.retract_mode == 1

    # The X/Y location of the hole to be tapped
    # There can be an x, y, or both x and y words on the block
    pos_cmd = get_initial_position_string(words, tap_axis)

    execute = wraps_interp_execute_with_log(self, 'G74' if left_hand else 'G84')
    # Incremental moves are converted to absolute coordinates in the prolog
    with absolute_distance_mode(self, execute), disable_speed_override(self, execute):
        if pos_cmd:
            execute(pos_cmd)
        execute('G0 {tap_axis}{retract_height:f}'.format(
            tap_axis=tap_axis.upper(),
            retract_height=words['r']))  # Rapid to retract height level (specified by R word)
        execute(forward_spindle_cmd)
        execute('G33.1 {tap_axis}{z_depth:f} K{thread_pitch:f}'.format(
            tap_axis=tap_axis.upper(),
            z_depth=words[tap_axis],
            thread_pitch=tap_pitch,
        ))
        if g98 and (words['initial_height'] > words['r']):
            execute('G0 {tap_axis}{initial_height:.4f}'.format(
                tap_axis=tap_axis,
                initial_height=words['initial_height'],
            ))

    return INTERP_OK


def has_encoder(self):
    if not self.task:
        return False

    if not self.ini:
        # we can't do this in toplevel.py because the UI sets this key in redis and it hasn't done that
        # yet when it runs, but don't need to do this every time.
        inifilepath = self.redis.hget('machine_prefs', 'linuxcnc_inifilepath')
        self.ini = linuxcnc.ini(inifilepath)
    encoder_scale = int(self.ini.find("SPINDLE", "ENCODER_SCALE")) or 0

    # KLUDGE Tormach uses 1 PPR to indicate a not-present encoder, even though this is technically a valid configuration
    if abs(encoder_scale) > 1:
        return True
    else:
        return False


def g740840_common(self, words, left_hand):
    """
    Execute the remapped G74 / G84 commands using a modified Fanuc approach

    G20 S600
    G84 X1 Y2 Z-1.2 R0.1 K.1 (Tap cycle starting at Z0.1, bottoming at Z-1.2, 10 threads per inch)
    X2                       (Tap at X2, Y2, same depth, retract height and thread pitch as previous line)
    X3 K.2                   (Tap at X3, Y2 with new thread pitch (probably a bad idea without a tool change!)

    In theory, this can be done on all cut planes (like the other canned cycles), but it's not very useful
    because mill / lathe spindles are oriented along the Z axis.

    NOTE: the Fanuc standard does not provide a way to specify thread pitch. We added the K word because manually
    calculating feed for a given spindle speed / pitch is error-prone.

    :param self: Linuxnc interpreter handle (has methods to execute G-code and introspect state)
    :param words: words from G-code block
    :param left_hand: thread direction (default is right-hand threads)
    """
    interp_block = self.blocks[self.remap_level]

    # WARNING: overwrite words with pre-modified sticky params from prolog
    # The prolog already updated sticky params with the updated values
    # This step combines sticky params with any new non-sticky words
    words.update(self.sticky_params[interp_block.executing_remap.name])
    tap_axis = words["tap_axis"]

    if has_encoder(self):
        rigid_tapping_cycle(self, words, tap_axis, left_hand=left_hand)
    else:
        soft_tapping_cycle(self, words, tap_axis, left_hand=left_hand)

    # retain the current motion mode
    self.motion_mode = interp_block.executing_remap.motion_code

    return INTERP_OK


def g740(self, **words):
    return g740840_common(self, words, left_hand=True)


def g840(self, **words):
    return g740840_common(self, words, left_hand=False)


def m100(self, **words):
    # M10 remap code.  This is for "unclamp" collet according to Simd book.
    # if its the initial toolpath display run, we're good.
    if self.task == 0: return INTERP_OK

    if self.params["_spindle_on"] == 0:
        # spindle not running
        _error_handler.log("M10 drawbar open remap invoked = running M64 P21 behind the curtain")
        self.execute('M64 P21')

    else:
        _error_handler.log("M10 drawbar open remap invoked, ignoring because spindle is running!")

    return INTERP_OK


def m110(self, **words):
    # M11 remap code.  This is for "clamp" collet according to Simd book.
    # if its the initial toolpath display run, we're good.
    if self.task == 0: return INTERP_OK

    if self.params["_spindle_on"] == 0:
        # spindle not running
        _error_handler.log("M11 drawbar close remap invoked = running M65 P21 behind the curtain")
        self.execute('M65 P21')

    else:
        _error_handler.log("M11 drawbar close remap invoked, ignoring because spindle is running!")

    return INTERP_OK


def get_linear_scale(self):
    scale = 1.0
    if self.params["_metric"] == 1:
        scale = 25.4
    return scale

