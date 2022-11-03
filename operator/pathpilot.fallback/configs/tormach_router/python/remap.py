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


_error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

throw_exceptions = 1 # raises InterpreterException if execute() or read() fail


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
        _error_handler.log("M80 context save  without prior M81, ignoring......")

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

_repetitive_data = dict()

def g840(self, **words):
    # G84 is typically called like so:
    # G84 x0 y0 z-.5 r.1
    # x1
    # y1
    # g80 (cancel cycle)

    # The Z and R words are repetitive, the x and Y can be changed on subsequent blocks.
    # This requires a 'global' to store the repetitive data between recursive calls

    global _repetitive_data

    # determine whether this is the first or a subsequent call
    interp_block = self.blocks[self.remap_level]
    remap_object = interp_block.executing_remap
    if interp_block.g_modes[1] == remap_object.motion_code:
        # this was the first call - clear the dict to forget any previous repetitive data
        _repetitive_data[remap_object.name] = dict()
        # get initial z location in case of G99 retract mode
        _repetitive_data[remap_object.name]['initial_z'] = self.current_z

    # merge in new parameters
    _repetitive_data[remap_object.name].update(words)
    words = _repetitive_data[remap_object.name]

    # Check preconditions - F and S must be non-zero
    #FIXME is this redundant with the prolog?
    if self.feed_rate == 0.0:
        self.set_errormsg("Cannot use G84 tapping cycle with zero feed rate.")
        return INTERP_ERROR
    if self.speed == 0.0:
        self.set_errormsg("Cannot use G84 tapping cycle with zero spindle speed")
        return INTERP_ERROR


    # Allow the user to override the dwell calculation with a P word on the G84 block
    if 'p' in words:
        dwell = 'P%.2f' % words['p']
    else:
        dwell = 'P%.2f' % (self.speed * 0.001) # half a second per thousand rpm

    # Go to the X/Y location of the hole to be tapped
    # There can be an x, y, or both x and y words on the block

    position = ''
    if 'x' in words:
        position += ' X%.4f' % words['x']

    if 'y' in words:
        position += ' Y%.4f' % words['y']

    if len(position):
        # then X and Y
        _error_handler.log('G0 {}'.format(position))
        self.execute('G0' + position)

    # Z and R should be 'sticky' positions, specified by the Z word and R word on the G84 line
    z_depth = ' Z%.4f' % words['z']
    r_level = 'Z%.4f' % words['r']

    # disable overrides
    self.execute('M49')
    # rapid move to r level
    self.execute('G0 ' + r_level)
    self.execute('G1 ' + z_depth)
    self.execute('M4')
    self.execute('G4 ' + dwell)
    self.execute('G1 ' + r_level)
    self.execute('M3')

    # if we're in G99 (retract to R plane), the work is done
    # but if we're in G99, need to retract further to the initial Z level
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
    initial_z = ' Z%.4f' % words['initial_z']
    if g98 and (words['initial_z'] > words['r']):
        self.execute('G0 ' + initial_z)

    # re-enable overrides
    self.execute('M48')
    # retain the current motion mode
    self.motion_mode = interp_block.executing_remap.motion_code

    return INTERP_OK


# router uses this for the spindle power drawbar
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


# router uses this for the spindle power drawbar
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
