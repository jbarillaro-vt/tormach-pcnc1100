# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import sys

import linuxcnc

# example how to access redis
#import redis
#def _ini_x_max_limit(self, *args):
    #red = redis.Redis()
    #inifilepath = red.hget('machine_prefs', 'linuxcnc_inifilepath')
    #print inifilepath
    #ini = linuxcnc.ini(inifilepath)
    #val_str = ini.find("AXIS_0", "MAX_LIMIT")
    #print val_str
    #return float(val_str)

# the Python equivalent of '#<_motion_mode> :
# return the currently active motion code (times 10)
#def _py_motion_mode(self, *args):
#    return self.active_g_codes[1]
#
#def _pi(self, *args):
#    return 3.1415926535

# only need this one instance
_np_status = linuxcnc.stat()

#
# DANGER DANGER WILL ROBINSON
# DANGER DANGER WILL ROBINSON
# DANGER DANGER WILL ROBINSON
#
# Be very aware of what you're reading through _np_status
# because all of this runs at interp time, not real time so
# the status is usually NOT accurate except for stuff below
# that never changes like axis min/max in machine coordinates.
#
# Use of linuxcnc stat is generally a bad idea in any remap context
# because of this unless very carefully joined up with queue busters
#

# G53 axis limits in machine units (inches)
def _x_axis_min_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[0]['min_position_limit']

def _x_axis_max_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[0]['max_position_limit']

def _y_axis_min_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[1]['min_position_limit']

def _y_axis_max_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[1]['max_position_limit']

def _z_axis_min_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[2]['min_position_limit']

def _z_axis_max_limit(self, *args):
    _np_status.poll()
    return _np_status.axis[2]['max_position_limit']
