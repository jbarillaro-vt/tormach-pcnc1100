#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

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


from interpreter import *
import emccanon

from stdglue import cycle_prolog, cycle_epilog, init_stdglue

import inspect
import re
import math
import rs274
from remap_classes import _g7x
from pdb import set_trace as bp

import errors

_error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements



def g71(self, **words):
    obj = _g7x(self, 710, **words)
    return obj.run()

def g711(self, **words):
    obj = _g7x(self, 711, **words)
    return obj.run()

def g72(self, **words):
    obj = _g7x(self, 720, **words)
    return obj.run()

def g721(self, **words):
    obj = _g7x(self, 721, **words)
    return obj.run()

def g740(self, **words):
    # G74 is typically called like so:
    # G74 x ? z ? k ? (x = diameter, usually 0; z = hole endpoint; k = peck length)

    # get position
    if (self.params['_lathe_diameter_mode']):  # if is_lathe_mode
        x_mode = 2
    else:
        x_mode = 1

    x_start = self.params[5420] * x_mode
    z_start = self.params[5422]

    if 'x' in words:
        x_end = words['x'] * x_mode
    else:
        x_end = x_start * x_mode

    if 'z' in words:
        z_end = words['z']
        if z_end > z_start:
            return "G74 error - Z cannot be larger than the starting Z position"
    else:
        z_end = z_start

    if 'k' in words:
        peck_length = words['k']
        if peck_length < 0:
            return "G74 error - K cannot be negative"
    else:
        peck_length = 0

    if (self.params['_metric']):  # if is_metric
        backoff_length = 0.50  # mm
        rounding_fudge = 0.0001
    else:
        backoff_length = 0.020  # inch
        rounding_fudge = 0.00001

    z_range = math.fabs(z_end - z_start) - rounding_fudge  # rounding_fudge prevents extra peck
    if peck_length > 0:
        num_pecks = int(z_range / peck_length)
    else:
        num_pecks = 0

    z_list = []
    for i in range(num_pecks + 1):
        z_list.append(z_start - (i * peck_length))
    z_list.append(z_end)

    print "--kaw - z_list =", z_list

    if math.fabs(x_end - x_start) > rounding_fudge:  # We're groove'n
        for i in range(num_pecks + 1):
            self.execute("G0 Z %s" % z_list[i])
            self.execute("G1 Z %s" % z_list[i + 1])
            self.execute("G1 X %s" % x_end)
            self.execute("G1 Z %s" % (z_list[i] + backoff_length))
            self.execute("G0 X %s" % x_start)

    else:  # We're drilling
        for i in range(num_pecks + 1):
            self.execute("G1 Z %s" % z_list[i + 1])
            self.execute("G0 Z %s" % (z_list[i + 1] + backoff_length))

    self.execute("G0 Z %s" % z_start)

    return INTERP_OK

def g300(self, **words):
    if self.task == 0: return INTERP_OK
    words_str = ''
    for key in words:
        words_str += "word '%s' = %f  " % (key, words[key])
    _error_handler.log("remapped g30: {}".format(words_str))

    # get machine G30 position in current G20/21 units
    # for lathe X is stored in #5181 as radius so convert to diameter
    # because it will get divided by 2 by the interpreter as we
    # only work in G7 and don't allow G8 mode
    x = self.params[5181] * get_linear_scale(self) * 2
    z = self.params[5183] * get_linear_scale(self)

    # an axis must be referenced only if that axis is to be moved
    g30m998_move_z_only = self.redis.hget('machine_prefs', 'g30m998_move_z_only')

    # unconditionally change motion mode to G90 to prevent stack underrun error
    self.execute('G90')

    if g30m998_move_z_only == 'True':
        # other words on this line are ignored because we're doing Z only, per settings screen
        position = ' Z%.6f' % z
        _error_handler.log('remapped g30: G53 G0' + position)
        self.execute('G53 G0' + position)
        # done

    else:
        # handle easy case - no words on line
        if len(words) == 0:
            # move Z, then X as discrete moves in G53
            position = 'Z%.6f' % (z)
            _error_handler.log('remapped g30: G53 G0' + position)
            self.execute('G53 G0' + position)
            position = 'X%.6f' % (x)
            _error_handler.log('remapped g30: G53 G0' + position)
            self.execute('G53 G0' + position)

        else:
            # there are coordinates supplied on the G30 line.
            # G0 to supplied coordinates in the current G5x system, then G53 G0 to G30 position(s)
            position = ''
            if 'x' in words:
                position += ' X%.6f' % words['x']

            if 'z' in words:
                position += ' Z%.6f' % words['z']

            _error_handler.log('remapped g30: G0' + position)
            self.execute('G0' + position)

            # Now go to the G30 positions stored in #5181 and #5183
            # move Z, then X as discrete moves
            position = 'Z%.6f' % (z)
            _error_handler.log('remapped g30: G53 G0' + position)
            self.execute('G53 G0' + position)
            position = 'X%.6f' % (x)
            _error_handler.log('remapped g30: G53 G0' + position)
            self.execute('G53 G0' + position)

    return INTERP_OK


def m10remap(self, **words):
    # M10 remap code.  This is for "unclamp" collet according to Simd book.
    # if its the initial toolpath display run, we're good.
    if self.task == 0:
        return INTERP_OK

    elif self.params["_spindle_on"] != 0:
        # spindle is running
        _error_handler.log("M10 UNCLAMP remap invoked, ignoring because spindle is running!")

    else:
        clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
        if clamping_style == 'OD':
            _error_handler.log("M10 UNCLAMP remap invoked with clamping style {} = setting collet-output = 1".format(clamping_style))
            emccanon.SET_AUX_OUTPUT_BIT(63)

        elif clamping_style == 'ID':
            _error_handler.log("M10 UNCLAMP remap invoked with clamping style {} = setting collet-output = 0".format(clamping_style))
            emccanon.CLEAR_AUX_OUTPUT_BIT(63)

        # Toggle the request pin so the tormachcolletcomp sees the request
        request_value = int(self.params['_collet_interp_request'])
        if request_value:
            emccanon.CLEAR_AUX_OUTPUT_BIT(62)
            request_value = 0
        else:
            emccanon.SET_AUX_OUTPUT_BIT(62)
            request_value = 1
        self.params['_collet_interp_request'] = request_value

        # Hold for a bit to make sure the tormachcolletcomp sees the request, acts on it, and the
        # closer has some reaction time.
        emccanon.DWELL(0.25)

    return INTERP_OK


def m11remap(self, **words):
    # M11 remap code.  This is for "clamp" collet according to Simd book.
    # if its the initial toolpath display run, we're good.
    if self.task == 0:
        return INTERP_OK

    elif self.params["_spindle_on"] != 0:
        # spindle is running
        _error_handler.log("M11 UNCLAMP remap invoked, ignoring because spindle is running!")

    else:
        # spindle not running
        clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
        if clamping_style == 'OD':
            _error_handler.log("M11 CLAMP remap invoked with clamping style {} = setting collet-output = 0".format(clamping_style))
            emccanon.CLEAR_AUX_OUTPUT_BIT(63)

        elif clamping_style == 'ID':
            _error_handler.log("M11 CLAMP remap invoked with clamping style {} = setting collet-output = 1".format(clamping_style))
            emccanon.SET_AUX_OUTPUT_BIT(63)

        # Toggle the request pin so the tormachcolletcomp sees the request
        request_value = int(self.params['_collet_interp_request'])
        if request_value:
            emccanon.CLEAR_AUX_OUTPUT_BIT(62)
            request_value = 0
        else:
            emccanon.SET_AUX_OUTPUT_BIT(62)
            request_value = 1
        self.params['_collet_interp_request'] = request_value

        # Hold for a bit to make sure the tormachcolletcomp sees the request, acts on it, and the
        # closer has some reaction time.
        emccanon.DWELL(0.25)

    return INTERP_OK


def get_linear_scale(self):
    scale = 1.0
    if self.params["_metric"] == 1:
        scale = 25.4
    return scale


def spindle_prolog(self, **words):
    # read the redis pref on clamping style and setup a parameter that the ngc code
    # can simply compare P21 against to see if it should block M3 or M4.
    # have to do it this way so the ngc code can easily force a queue buster
    # to align interp time with real time so that we are checking the collet status
    # at the right time!!

    clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
    if clamping_style == 'OD':
        self.params['_collet_status_block_spindle_value'] = 1

    elif clamping_style == 'ID':
        self.params['_collet_status_block_spindle_value'] = 0

    else:
        self.set_errormsg("Unsupported clamping style {}.".format(clamping_style))
        return INTERP_ERROR

    return INTERP_OK


def digital_io_output_on_immediate_M64(self,**words):
    pin = int(words['p'])
    if pin != 2:
        emccanon.SET_AUX_OUTPUT_BIT(pin)
        return INTERP_OK
    else:
        self.set_errormsg("M64 P2 is no longer supported for collet clamping control.  Replace with either M10 for 'unclamp' or M11 for 'clamp' as these properly use the OD/ID clamp setting and perform a spindle safety check.")
        return INTERP_ERROR


def digital_io_output_off_immediate_M65(self,**words):
    pin = int(words['p'])
    if pin != 2:
        emccanon.CLEAR_AUX_OUTPUT_BIT(pin)
        return INTERP_OK
    else:
        self.set_errormsg("M65 P2 is no longer supported for collet clamping control.  Replace with either M10 for 'unclamp' or M11 for 'clamp' as these properly use the OD/ID clamp setting and perform a spindle safety check.")
        return INTERP_ERROR
