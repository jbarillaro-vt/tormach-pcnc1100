# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------

# stdglue - canned prolog and epilog functions for the remappable builtin codes (T,M6,M61,S,F)
#
# we dont use argspec to avoid the generic error message of the argspec prolog and give more
# concise ones here


#pylint: disable=import-error


# cycle_prolog,cycle_epilog: generic code-independent support glue for oword sub cycles
#
# these are provided as starting point - for more concise error message you would better
# write a prolog specific for the code
#
# Usage:
#REMAP=G84.3  modalgroup=1 argspec=xyzqp prolog=cycle_prolog ngc=g843 epilog=cycle_epilog


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


import emccanon
from interpreter import *
throw_exceptions = 1

# REMAP=S   prolog=setspeed_prolog  ngc=setspeed epilog=setspeed_epilog
# exposed parameter: #<speed>

def setspeed_prolog(self,**words):
    try:
        c = self.blocks[self.remap_level]
        if not c.s_flag:
            self.set_errormsg("S requires a value")
            return INTERP_ERROR
        self.params["speed"] = c.s_number
    except Exception as e:
        self.set_errormsg("S/setspeed_prolog: %s)" % (e))
        return INTERP_ERROR
    return INTERP_OK

def setspeed_epilog(self,**words):
    try:
        if not self.value_returned:
            r = self.blocks[self.remap_level].executing_remap
            self.set_errormsg("the %s remap procedure %s did not return a value"
                             % (r.name,r.remap_ngc if r.remap_ngc else r.remap_py))
            return INTERP_ERROR
        if self.return_value < -TOLERANCE_EQUAL: # 'less than 0 within interp's precision'
            self.set_errormsg("S: remap procedure returned %f" % (self.return_value))
            return INTERP_ERROR
        if self.blocks[self.remap_level].builtin_used:
            pass
            #print "---------- S builtin recursion, nothing to do"
        else:
            self.speed = self.params["speed"]
            emccanon.enqueue_SET_SPINDLE_SPEED(self.speed)
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("S/setspeed_epilog: %s)" % (e))
        return INTERP_ERROR
    return INTERP_OK

# REMAP=F   prolog=setfeed_prolog  ngc=setfeed epilog=setfeed_epilog
# exposed parameter: #<feed>

def setfeed_prolog(self,**words):
    try:
        c = self.blocks[self.remap_level]
        if not c.f_flag:
            self.set_errormsg("F requires a value")
            return INTERP_ERROR
        self.params["feed"] = c.f_number
    except Exception as e:
        self.set_errormsg("F/setfeed_prolog: %s)" % (e))
        return INTERP_ERROR
    return INTERP_OK

def setfeed_epilog(self,**words):
    try:
        if not self.value_returned:
            r = self.blocks[self.remap_level].executing_remap
            self.set_errormsg("the %s remap procedure %s did not return a value"
                             % (r.name,r.remap_ngc if r.remap_ngc else r.remap_py))
            return INTERP_ERROR
        if self.blocks[self.remap_level].builtin_used:
            pass
            #print "---------- F builtin recursion, nothing to do"
        else:
            self.feed_rate = self.params["feed"]
            emccanon.enqueue_SET_FEED_RATE(self.feed_rate)
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("F/setfeed_epilog: %s)" % (e))
        return INTERP_ERROR
    return INTERP_OK


# REMAP=T   prolog=prepare_prolog ngc=prepare epilog=prepare_epilog
# exposed parameters: #<tool> #<pocket>

def prepare_prolog(self,**words):
    print("prepare prolog")
    try:
        cblock = self.blocks[self.remap_level]
        if not cblock.t_flag:
            self.set_errormsg("T requires a tool number")
            return INTERP_ERROR
        tool  = cblock.t_number
        if tool:
            (status, pocket) = self.find_tool_pocket(tool)
            if status != INTERP_OK:
                self.set_errormsg("T%d: pocket not found" % (tool))
                return status
        else:
            pocket = -1 # this is a T0 - tool unload
        self.params["tool"] = tool
        self.params["pocket"] = pocket
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("T%d/prepare_prolog: %s" % (int(words['t']), e))
        return INTERP_ERROR

def prepare_epilog(self, **words):
    tool = "?"
    try:
        if self.blocks[self.remap_level].builtin_used:
            print "---------- T builtin recursion, nothing to do"
            return INTERP_OK
        else:
            self.selected_tool = int(self.params["tool"])
            tool = str(self.selected_tool)
            self.selected_pocket = int(self.params["pocket"])
            emccanon.SELECT_POCKET(self.selected_pocket, self.selected_tool)
            return INTERP_OK
    except Exception as e:
        self.set_errormsg("T%d/prepare_epilog: %s" % (tool,e))
        return INTERP_ERROR

# REMAP=M6  modalgroup=6 prolog=change_prolog ngc=change epilog=change_epilog
# exposed parameters:
#    #<tool_in_spindle>
#    #<selected_tool>
#    #<current_pocket>
#    #<selected_pocket>

def change_prolog(self, **words):
    print("change_prolog")
    try:
        # this is relevant only when using iocontrol-v2.
        if self.params[5600] > 0.0:
            if self.params[5601] < 0.0:
                self.set_errormsg("Toolchanger hard fault %d" % (int(self.params[5601])))
                return INTERP_ERROR
            print "change_prolog: Toolchanger soft fault %d" % int(self.params[5601])

        print("prolog selected pocket",self.selected_pocket)
        #if ((self.selected_pocket < 0) and (self.current_tool<=0)):
            #self.set_errormsg("M6: no tool prepared")
            #return INTERP_ERROR
        if self.cutter_comp_side:
            self.set_errormsg("Cannot change tools with cutter radius compensation on")
            return INTERP_ERROR
        self.params["tool_in_spindle"] = self.current_tool
        self.params["selected_tool"] = self.selected_tool
        self.params["current_pocket"] = self.current_pocket # this is probably nonsense
        self.params["selected_pocket"] = self.selected_pocket
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("M6/change_prolog: %s" % (e))
        return INTERP_ERROR

def change_epilog(self, **words):

    try:
        # this is relevant only when using iocontrol-v2.
        if self.params[5600] > 0.0:
            if self.params[5601] < 0.0:
                self.set_errormsg("Toolchanger hard fault %d" % (int(self.params[5601])))
                return INTERP_ERROR
            print "change_epilog: Toolchanger soft fault %d" % int(self.params[5601])

        if self.blocks[self.remap_level].builtin_used:
            #print "---------- M6 builtin recursion, nothing to do"
            return INTERP_OK
        else:
            # commit change
            self.selected_pocket =  int(self.params["selected_pocket"])
            emccanon.CHANGE_TOOL(self.selected_pocket)
            self.current_pocket = self.selected_pocket
            self.current_tool=self.selected_tool
            self.selected_pocket = -1
            self.selected_tool = -1
            # cause a sync()
            self.set_tool_parameters()
            self.toolchange_flag = True
            return INTERP_EXECUTE_FINISH
    except Exception as e:
        self.set_errormsg("M6/change_epilog: %s" % (e))
        return INTERP_ERROR

# REMAP=M61  modalgroup=6 prolog=settool_prolog ngc=settool epilog=settool_epilog
# exposed parameters: #<tool> #<pocket>

def settool_prolog(self,**words):
    try:
        c = self.blocks[self.remap_level]
        if not c.q_flag:
            self.set_errormsg("M61 requires a Q parameter")
            return INTERP_ERROR
        tool = int(c.q_number)
        if tool < -TOLERANCE_EQUAL: # 'less than 0 within interp's precision'
            self.set_errormsg("M61: Q value < 0")
            return INTERP_ERROR
        (status,pocket) = self.find_tool_pocket(tool)
        if status != INTERP_OK:
            self.set_errormsg("M61 failed: requested tool %d not in table" % (tool))
            return status
        self.params["tool"] = tool
        self.params["pocket"] = pocket
        return INTERP_OK
    except Exception as e:
        self.set_errormsg("M61/settool_prolog: %s)" % (e))
        return INTERP_ERROR

def settool_epilog(self,**words):
    try:
        if not self.value_returned:
            r = self.blocks[self.remap_level].executing_remap
            self.set_errormsg("the %s remap procedure %s did not return a value"
                             % (r.name,r.remap_ngc if r.remap_ngc else r.remap_py))
            return INTERP_ERROR

        if self.blocks[self.remap_level].builtin_used:
            #print "---------- M61 builtin recursion, nothing to do"
            return INTERP_OK
        else:
            if self.return_value > 0.0:
                self.current_tool = int(self.params["tool"])
                self.current_pocket = int(self.params["pocket"])
                emccanon.CHANGE_TOOL_NUMBER(self.current_pocket)
                # cause a sync()
                self.tool_change_flag = True
                self.set_tool_parameters()
            else:
                self.set_errormsg("M61 aborted (return code %.1f)" % (self.return_value))
                return INTERP_ERROR
    except Exception as e:
        self.set_errormsg("M61/settool_epilog: %s)" % (e))
        return INTERP_ERROR

# educational alternative: M61 remapped to an all-Python handler
# demo - this really does the same thing as the builtin (non-remapped) M61
#
# REMAP=M61 modalgroup=6 python=set_tool_number

def set_tool_number(self, **words):
    try:
        c = self.blocks[self.remap_level]
        if c.q_flag:
            toolno = int(c.q_number)
        else:
            self.set_errormsg("M61 requires a Q parameter")
            return INTERP_ERROR
        (status,pocket) = self.find_tool_pocket(toolno)
        if status != INTERP_OK:
            self.set_errormsg("M61 failed: requested tool %d not in table" % (toolno))
            return status
        if words['q'] > -TOLERANCE_EQUAL: # 'greater equal 0 within interp's precision'
            self.current_pocket = pocket
            self.current_tool = toolno
            emccanon.CHANGE_TOOL_NUMBER(pocket)
            # cause a sync()
            self.tool_change_flag = True
            self.set_tool_parameters()
            return INTERP_OK
        else:
            self.set_errormsg("M61 failed: Q=%d" % toolno)
            return INTERP_ERROR
    except Exception as e:
        self.set_errormsg("M61/set_tool_number: %s" % (e))
        return INTERP_ERROR


_uvw = ("u", "v", "w", "a", "b", "c")
_xyz = ("x", "y", "z", "a", "b", "c")
# given a plane, return  sticky words, incompatible axis words and plane name
# sticky[0] is also the movement axis
_mill_canned_cycle_compat = {
    emccanon.CANON_PLANE_XY: ("z", _uvw, "XY"),
    emccanon.CANON_PLANE_YZ: ("x", _uvw, "YZ"),
    emccanon.CANON_PLANE_XZ: ("y", _uvw, "XZ"),
    emccanon.CANON_PLANE_UV: ("w", _xyz, "UV"),
    emccanon.CANON_PLANE_VW: ("u", _xyz, "VW"),
    emccanon.CANON_PLANE_UW: ("v", _xyz, "UW"),
}


def tapping_cycle_prolog(self, **words):
    """
    Do preparatory checks for G74 / G84 tapping cycles.

    Note that the "sticky" params recorded here are

    """
    # self.sticky_params is assumed to have been initialized by the
    # init_stgdlue() method below
    global _mill_canned_cycle_compat
    try:

        # determine whether this is the first or a subsequent call
        c = self.blocks[self.remap_level]
        r = c.executing_remap
        tap_axis, incompat, plane_name = _mill_canned_cycle_compat[self.plane]

        cur_pos_map = {
            'x': self.current_x,
            'y': self.current_y,
            'z': self.current_z,
            'u': self.u_current,
            'v': self.v_current,
            'w': self.w_current,
        }

        if c.g_modes[1] == r.motion_code:
            # new G74/G84 block - clear repetitive parameters and store initial position / cut plane
            if self.debugmask & 0x00008000:
                print("%s: clear stickies" % r.name)
            self.sticky_params[r.name] = {
                "tap_axis": tap_axis,
                "cut_plane": self.plane,
                "initial_height": cur_pos_map[tap_axis],
            }
            if self.debugmask & 0x00008000:
                print("Tap axis {} for plane {}, initial height {}".format(
                    tap_axis, plane_name, self.sticky_params[r.name]["initial_height"]))

        for bad_word in incompat:
            if bad_word in words:
                self.set_errormsg("%s: Cannot put a %s in a canned cycle in the %s plane" % (r.name, bad_word.upper(), plane_name))
                return INTERP_ERROR

        populate_tapping_sticky_params(self.sticky_params[r.name], words, cur_pos_map, tap_axis, self.distance_mode)

        initial_height = self.sticky_params[r.name]["initial_height"]

        if self.plane != self.sticky_params[r.name]["cut_plane"]:
            self.set_errormsg("{}: Need a new block to switch cut planes".format(r.name))
            return INTERP_ERROR

        for req_word in ("r", tap_axis):
            if req_word not in self.sticky_params[r.name]:
                self.set_errormsg("{}: cycle requires {} word".format(r.name, req_word.upper()))
                return INTERP_ERROR

        r_word = self.sticky_params[r.name]["r"]
        tap_depth = self.sticky_params[r.name][tap_axis]
        if r_word < tap_depth:
            self.set_errormsg("{}: R word {:.4f} must be greater than tap depth of {:.4f}".format(
                r.name, r_word, tap_depth))
            return INTERP_ERROR
        if initial_height < tap_depth:
            self.set_errormsg("{}: Initial height {:.4f} must be greater than tap depth of {:.4f}".format(
                r.name, initial_height, tap_depth))
            return INTERP_ERROR

        if "p" in self.sticky_params[r.name]:
            p = self.sticky_params[r.name]["p"]
            if p < 0.0:
                self.set_errormsg("%s: P word must be >= 0 if used (%.4f)" % (r.name, p))
                return INTERP_ERROR

        if self.speed == 0.0:
            self.set_errormsg("%s: Cannot use tap cycle with zero spindle speed" % r.name)
            return INTERP_ERROR
        if self.feed_rate == 0.0 and (self.sticky_params[r.name].get("k", 0.0) <= 0.0):
            self.set_errormsg("%s: tap cycle requires an explicit feed rate, or thread pitch specified with K word" % r.name)
            return INTERP_ERROR
        if self.feed_mode == INVERSE_TIME:
            self.set_errormsg("%s: Cannot use inverse time feed with canned cycles" % r.name)
            return INTERP_ERROR
        if self.cutter_comp_side:
            self.set_errormsg("%s: Cannot use canned cycles with cutter compensation on" % r.name)
            return INTERP_ERROR

        return INTERP_OK

    except Exception as e:
        self.set_errormsg("tapping_cycle_prolog failed: %s" % e)
        return INTERP_ERROR


def populate_tapping_sticky_params(tapping_sticky_params, words, cur_pos_map, tap_axis, distance_mode):
    # Populate sticky parameters
    positioning_axes = {'x', 'y', 'z', 'u', 'v', 'w'} - {tap_axis}
    # DISTANCE_MODE gets defined by interpmodule.cc about line 808 using Boost from C++.
    #pylint: disable=undefined-variable
    if distance_mode == DISTANCE_MODE.MODE_INCREMENTAL:
        # Convert to absolute coordinates based on canned cycle standard:
        # Do this conversion before storing in sticky params to ensure that stickies are always absolute
        # Retract height is relative to initial height (regardless of G98 / G99 mode)
        if 'r' in words:
            tapping_sticky_params['r'] = tapping_sticky_params['initial_height'] + words['r']

        # tap depth is relative to retract height (regardless of G98 / G99 mode)
        if tap_axis in words:
            tapping_sticky_params[tap_axis] = tapping_sticky_params['r'] + words[tap_axis]

        # Remaining position moves are relative to the current position (so an L word specifies repeated increments)
        for ax in positioning_axes:
            if ax in words:
                tapping_sticky_params[ax] = words[ax] + cur_pos_map[ax]
        for misc_word in 'k', 'p':
            if misc_word in words:
                tapping_sticky_params[misc_word] = words[misc_word]

    else:
        for (word, value) in words.items():
            # record sticky words and position commands
            if word not in (tap_axis, 'r', 'k', 'p') and word not in positioning_axes:
                continue
            tapping_sticky_params[word] = value


# this should be called from TOPLEVEL __init__()
def init_stdglue(self):
    self.sticky_params = dict()
