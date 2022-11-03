# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for probing routines
#

import time
import sys
import gtk
import math
from constants import *
import linuxcnc

class probing():

    def __init__(self, probeobj, status, issue_mdi):
        self.probeobj = probeobj
        self.status = status
        self.issue_mdi = issue_mdi
        # error_handler will get set later
        self.error_handler = None

    def get_tip_diameter(self):
        return (self.probeobj.probe_tip_effective_diameter * self.probeobj.get_linear_scale())

    def get_rapid_feedrate(self):
        # check for appropriate feedrate
        rapid_feedrate = self.probeobj.probe_rapid_feedrate * self.probeobj.get_linear_scale()
        return rapid_feedrate

    def get_rough_feedrate(self):
        # check for appropriate feedrate
        rough_feedrate = self.probeobj.probe_rough_feedrate * self.probeobj.get_linear_scale()

        if rough_feedrate > self.probeobj.max_probe_rough_feedrate * self.probeobj.get_linear_scale():
            # should never happen if feed rate DRO validation is working correctly
            self.error_handler.write("Rough probing feedrate too high - rough feedrate must be less than %.1f to use probing buttons.  Setting feedrate to %.1f." %
                (self.probeobj.max_probe_rough_feedrate * self.probeobj.get_linear_scale(),
                    self.probeobj.max_probe_rough_feedrate * self.probeobj.get_linear_scale()),
                ALARM_LEVEL_LOW)
            rough_feedrate = DEFAULT_PROBE_ROUGH_FEEDRATE * self.probeobj.get_linear_scale()

        return rough_feedrate

    def get_fine_feedrate(self):
        fine_feedrate = self.probeobj.probe_fine_feedrate * self.probeobj.get_linear_scale()
        if fine_feedrate <= 0.0:
            # should never happen if feed rate DRO validation is working correctly
            self.error_handler.write("Fine probing feedrate must be greater than 0.0 to use probing buttons.  Setting feedrate to %.1f." %
                (DEFAULT_PROBE_FINE_FEEDRATE * self.probeobj.get_linear_scale()),
                ALARM_LEVEL_LOW)
            fine_feedrate = DEFAULT_PROBE_FINE_FEEDRATE * self.probeobj.get_linear_scale()
        return fine_feedrate

    def get_z_min_limit(self):
        return (self.status.axis[2]['min_position_limit'] * self.probeobj.get_linear_scale())

    def check_probe_toolnum(self):
        if self.status.probe_val:
            self.error_handler.write("Cannot start probe move with probe tripped.  Please check probe polarity on Settings page before continuing.")
            return False
        if (self.status.tool_in_spindle != MILL_PROBE_TOOL_NUM):
            self.error_handler.write("Must change tools to tool %s before probing." % MILL_PROBE_TOOL_NUM)
            return False
        return True

    def check_probe_diameter(self):
        if self.status.tool_table[MILL_PROBE_TOOL_NUM].diameter <= 0.001:
            self.error_handler.write("This probe routine requires a valid tip diameter for the probe tool.  Please enter a valid probe tip diameter in the diameter column of the tool table for tool %s." % MILL_PROBE_TOOL_NUM)
            return False
        return True

    def check_probe_length(self):
        if self.status.tool_table[MILL_PROBE_TOOL_NUM].zoffset <= 0.001:
            self.error_handler.write("This probe routine requires a valid length for the probe tool.  Please enter a valid probe length in the length column of the tool table for tool %s." % MILL_PROBE_TOOL_NUM)
            return False
        return True

    def check_probe_toolnum_diameter(self):
        if not self.check_probe_toolnum():
            return False
        if not self.check_probe_diameter():
            return False
        if not self.check_probe_length():
            return False

        return True

    def get_probe_corner_parameters(self, outside_flag, corner):
        if not self.check_probe_toolnum_diameter():
            return (False, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        tip_diameter = self.get_tip_diameter()
        (x_wcs_offset, y_wcs_offset) = self.get_xy_wcs_offsets()

        # assume inside corner and set directions
        if corner == 'nw':
            x_dir = -1
            y_dir = 1
        elif corner == 'ne':
            x_dir = 1
            y_dir = 1
        elif corner == 'se':
            x_dir = 1
            y_dir = -1
        elif corner == 'sw':
            x_dir = -1
            y_dir = -1

        if outside_flag > 0.0:
            # opposite directions for outside corner
            x_dir = x_dir * -1
            y_dir = y_dir * -1

        # set limits based on direction
        if x_dir > 0:
            x_limit = self.status.axis[0]['max_position_limit'] * self.probeobj.get_linear_scale()
        else:
            x_limit = self.status.axis[0]['min_position_limit'] * self.probeobj.get_linear_scale()
        if y_dir > 0:
            y_limit = self.status.axis[1]['max_position_limit'] * self.probeobj.get_linear_scale()
        else:
            y_limit = self.status.axis[1]['min_position_limit'] * self.probeobj.get_linear_scale()

        return (True, rapid_feedrate, rough_feedrate, fine_feedrate, tip_diameter, x_wcs_offset, y_wcs_offset, x_limit, y_limit, x_dir, y_dir)


    def find_corner(self, outside_flag, compass_corner):
        # inside == 0, outside == 1
        # corner in ('nw', 'ne', 'se', 'sw')
        corner = compass_corner.lower()
        if outside_flag:
            outside_corner = 1.0
        else:
            outside_corner = 0.0

        (params_ok, rapid_feedrate, rough_feedrate, fine_feedrate, tip_diameter, x_wcs_offset, y_wcs_offset, x_limit, y_limit, x_dir, y_dir) = self.get_probe_corner_parameters(outside_corner, corner)

        if params_ok:
            self.issue_mdi('o<probe_corner_xy> call [%.1f] [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.6f] [%.6f] [%.1f] [%.1f] [%.6f]'
                % (outside_corner, rapid_feedrate, rough_feedrate, fine_feedrate, x_limit, y_limit, x_wcs_offset, y_wcs_offset, x_dir, y_dir, tip_diameter))


    def get_probe_xyz_parameters(self, axis_index, direction):
        if not self.check_probe_toolnum_diameter():
            return (False, 1, 2, 3, 4, 5, 6)

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        if direction > 0:
            limit = self.status.axis[axis_index]['max_position_limit']
        else:
            limit = self.status.axis[axis_index]['min_position_limit']
        limit = limit * self.probeobj.get_linear_scale()

        wcs_offset = self.status.g5x_offsets[0][axis_index] * self.probeobj.get_linear_scale()
        tip_diameter = self.get_tip_diameter()
        return (True, rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, tip_diameter)

    def find_x(self, set_origin, direction):
        (params_ok, rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, tip_diameter) = self.get_probe_xyz_parameters(0, direction)
        if params_ok:
            if direction > 0:
                analog_pin = PROBE_X_PLUS_AOUT
            else:
                analog_pin = PROBE_X_MINUS_AOUT
            self.issue_mdi('o<probe_xyz> call [0] [%f] [%f] [%f] [%f] [%f] [%d] [%d] [%f] [%f] [1]'
                % (rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, set_origin, direction, tip_diameter, analog_pin))

    def find_y(self, set_origin, direction):
        (params_ok, rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, tip_diameter) = self.get_probe_xyz_parameters(1, direction)
        if params_ok:
            if direction > 0:
                analog_pin = PROBE_Y_PLUS_AOUT
            else:
                analog_pin = PROBE_Y_MINUS_AOUT
            self.issue_mdi('o<probe_xyz> call [1] [%f] [%f] [%f] [%f] [%f] [%d] [%d] [%f] [%f] [1]'
                % (rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, set_origin, direction, tip_diameter, analog_pin))

    def find_z(self, set_origin, direction):
        (params_ok, rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, tip_diameter) = self.get_probe_xyz_parameters(2, direction)
        if params_ok:
            if direction > 0:
                self.error_handler.write("Probing +Z not supported", ALARM_LEVEL_LOW)
                return
            else:
                analog_pin = PROBE_Z_MINUS_AOUT
            tip_diameter = 0.0

            tool_offset_z = self.status.tool_offset[2] * self.probeobj.get_linear_scale()
            self.issue_mdi('o<probe_xyz> call [2] [%f] [%f] [%f] [%f] [%f] [%d] [%d] [%f] [%f] [1] [%f]'
            % (rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, set_origin, direction, tip_diameter, analog_pin, tool_offset_z))

    def find_y_plus_abc(self, analog_pin):
        set_origin = 0
        direction = 1
        (params_ok, rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, tip_diameter) = self.get_probe_xyz_parameters(1, 1)
        if params_ok:
            self.issue_mdi('o<probe_xyz> call [1] [%f] [%f] [%f] [%f] [%f] [%d] [%d] [%f] [%f] [1]'
                % (rapid_feedrate, rough_feedrate, fine_feedrate, limit, wcs_offset, set_origin, direction, tip_diameter, analog_pin))

    def get_xy_limits(self):
        return (self.status.axis[0]['min_position_limit'] * self.probeobj.get_linear_scale(),
                self.status.axis[0]['max_position_limit'] * self.probeobj.get_linear_scale(),
                self.status.axis[1]['min_position_limit'] * self.probeobj.get_linear_scale(),
                self.status.axis[1]['max_position_limit'] * self.probeobj.get_linear_scale())

    def get_xy_wcs_offsets(self):
        return (self.status.g5x_offsets[0][0] * self.probeobj.get_linear_scale(),
                self.status.g5x_offsets[0][1] * self.probeobj.get_linear_scale())

    def find_pocket_xy_center(self, x_y_or_both):
        # 0 == center X, 1 == center Y, 2 == center X then center Y
        if not self.check_probe_toolnum_diameter():
            return

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        tip_diameter = self.get_tip_diameter()
        (x_wcs_offset, y_wcs_offset) = self.get_xy_wcs_offsets()

        (x_limit_min, x_limit_max, y_limit_min, y_limit_max) = self.get_xy_limits()

        self.issue_mdi('o<probe_pocket_xy> call [%.1f] [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.4f] [%.4f] [%.6f] [%.6f] [%.6f]'
            % (x_y_or_both, rapid_feedrate, rough_feedrate, fine_feedrate, x_limit_min, x_limit_max, y_limit_min, y_limit_max, x_wcs_offset, y_wcs_offset, tip_diameter))

    def find_rect_boss_center(self):
        if not self.check_probe_toolnum_diameter():
            return

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        tip_diameter = self.get_tip_diameter()
        (x_wcs_offset, y_wcs_offset) = self.get_xy_wcs_offsets()

        (x_limit_min, x_limit_max, y_limit_min, y_limit_max) = self.get_xy_limits()
        self.issue_mdi('o<probe_rect_boss> call [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.4f] [%.4f] [%.6f] [%.6f] [%.6f]'
            % (rapid_feedrate, rough_feedrate, fine_feedrate, x_limit_min, x_limit_max, y_limit_min, y_limit_max, x_wcs_offset, y_wcs_offset, tip_diameter))

    def find_circ_boss_center(self):
        if not self.check_probe_toolnum_diameter():
            return

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        tip_diameter = self.get_tip_diameter()
        (x_wcs_offset, y_wcs_offset) = self.get_xy_wcs_offsets()

        (x_limit_min, x_limit_max, y_limit_min, y_limit_max) = self.get_xy_limits()

        # Y distance between the three circumferential probe points
        y_stepover = 0.025 * self.probeobj.get_linear_scale()

        self.issue_mdi('o<probe_circ_boss> call [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.4f] [%.4f] [%.6f] [%.6f] [%.6f] [%.6f]'
            % (rapid_feedrate, rough_feedrate, fine_feedrate, x_limit_min, x_limit_max, y_limit_min, y_limit_max, x_wcs_offset, y_wcs_offset, tip_diameter, y_stepover))

    def find_a_axis_center(self):
        if not self.check_probe_toolnum_diameter():
            return

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        tip_diameter = self.get_tip_diameter()
        y_wcs_offset = (self.status.g5x_offsets[0][1] * self.probeobj.get_linear_scale())
        z_wcs_offset = (self.status.g5x_offsets[0][2] * self.probeobj.get_linear_scale())

        y_limit_min = self.status.axis[1]['min_position_limit'] * self.probeobj.get_linear_scale()
        y_limit_max = self.status.axis[1]['max_position_limit'] * self.probeobj.get_linear_scale()
        z_limit_min = self.status.axis[2]['min_position_limit'] * self.probeobj.get_linear_scale()
        z_limit_max = self.status.axis[2]['max_position_limit'] * self.probeobj.get_linear_scale()

        # Z distance between the three circumferential probe points
        z_stepover = 0.025 * self.probeobj.get_linear_scale()

        self.issue_mdi('o<probe_a_axis_boss> call [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.4f] [%.4f] [%.6f] [%.6f] [%.6f] [%.6f]'
            % (rapid_feedrate, rough_feedrate, fine_feedrate, y_limit_min, y_limit_max, z_limit_min, z_limit_max, y_wcs_offset, z_wcs_offset, tip_diameter, z_stepover))

    def move_and_set_tip_probe_diameter(self):
        # find the diameter of a ring gauge and set effective tip diameter
        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()
        fine_feedrate = self.get_fine_feedrate()
        # use 0.0 tip diameter and ring gauge probed vs. actual diameter
        # to determine effective tip diameter
        tip_diameter = 0.0
        (x_wcs_offset, y_wcs_offset) = self.get_xy_wcs_offsets()
        (x_limit_min, x_limit_max, y_limit_min, y_limit_max) = self.get_xy_limits()

        # clear analog pin that will be set to pocket diameter
        # TODO: maybe this next line should go into o<probe_pocket_diameter>
        self.issue_mdi("M68 E%d Q-1.0" % PROBE_POCKET_DIAMETER_AOUT)

        self.issue_mdi('o<probe_pocket_diameter> call [%.2f] [%.2f] [%.2f] [%.4f] [%.4f] [%.4f] [%.4f] [%.6f] [%.6f] [%.6f] [%.1f]'
            % (rapid_feedrate, rough_feedrate, fine_feedrate, x_limit_min, x_limit_max, y_limit_min, y_limit_max, x_wcs_offset, y_wcs_offset, tip_diameter, PROBE_POCKET_DIAMETER_AOUT))

    def move_and_set_probe_length(self, ref_surface):
        # NOTE: the ref_surface parameter is in G53 and not the current WCS
        # it is also in machine units
        wcs_surface = (ref_surface - self.status.g5x_offsets[0][2]) * self.probeobj.get_linear_scale()
        # calls ETS tool length function to set probe length
        # use probe fine feed rate
        fine_feedrate = self.get_fine_feedrate()
        self.execute_ets_oword('o<probe_move_and_set_tool_length>', wcs_surface, fine_feedrate)

    # ETS functions

    def execute_ets_oword(self, oword, ref_height, fine_feedrate):
        if self.status.probe_val:
            self.error_handler.write("Cannot start probe or ETS move with probe tripped.  Please check probe polarity on Settings page before continuing.")
            return

        rapid_feedrate = self.get_rapid_feedrate()
        rough_feedrate = self.get_rough_feedrate()

        z_limit_min = self.get_z_min_limit()
        z_wcs_offset = (self.status.g5x_offsets[0][2] * self.probeobj.get_linear_scale())

        self.issue_mdi(oword + 'call [%.2f] [%.2f] [%.2f] [%.6f] [%.6f] [%.6f]' % (rapid_feedrate, rough_feedrate, fine_feedrate, z_limit_min, z_wcs_offset, ref_height))

    def move_and_set_tool_length(self, ets_height):
        # fine feed rate is fixed to maintain consistent ETS results
        fine_feedrate = ETS_FINE_FEEDRATE * self.probeobj.get_linear_scale()
        ets_height = ets_height * self.probeobj.get_linear_scale()
        self.execute_ets_oword('o<probe_move_and_set_tool_length>', ets_height, fine_feedrate)

    def find_work_z_with_ets(self, ets_height):
        # fine feed rate is fixed to maintain consistent ETS results
        fine_feedrate = ETS_FINE_FEEDRATE * self.probeobj.get_linear_scale()
        ets_height = ets_height * self.probeobj.get_linear_scale()
        self.execute_ets_oword('o<probe_find_work_z_with_ets>', ets_height, fine_feedrate)
