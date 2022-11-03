# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for G-code generator and parameter validation for conversational routines
#

# for debugging within Wing IDE
from collections import namedtuple

try:
    import wingdbstub
except ImportError:
    pass

import time
import sys
import gtk
import math
import copy
import subprocess
from constants import *
from math import *
#from alphanum import *
import operator
import os
import ftesy
import itertools
import tempfile
import shutil
import traceback
import ast
import linuxcnc
import geoutil
from mill_conv_support import *
from conversational import *


class conversational(conversational_base):

    #routine names are dictionary of conversational routines mapped to
    #routine data 'factories'
    routine_names = {
        'conversational': 'Mill',
        'routines': {
            'ExternalCode': {
                'pack': 'gen_external_code_dict',
                'conv': None,
                'edit': None,
                'restore': 'ja_revert_to_was'
            },
            'Face': {
                'pack': 'gen_face_dro_dict',
                'conv': list(('conv_face_fixed', )),
                'edit': 'ja_edit_face',
                'restore': 'ja_revert_to_was'
            },
            'Spiral Face': {
                'pack': 'gen_face_dro_dict',
                'conv': list(('conv_face_fixed', )),
                'edit': 'ja_edit_face',
                'restore': 'ja_revert_to_was'
            },
            'Rectangular Face': {
                'pack': 'gen_face_rect_dro_dict',
                'conv': list(('conv_face_fixed', )),
                'edit': 'ja_edit_face',
                'restore': 'ja_revert_to_was'
            },
            'Profile': {
                'pack': 'gen_profile_dro_dict',
                'conv': list(('conv_profile_fixed', )),
                'edit': 'ja_edit_profile',
                'restore': 'ja_revert_to_was'
            },
            'Rectangular Profile': {
                'pack': 'gen_profile_dro_dict',
                'conv': list(('conv_profile_fixed', )),
                'edit': 'ja_edit_profile',
                'restore': 'ja_revert_to_was'
            },
            'Circular Profile': {
                'pack': 'gen_profile_circ_dro_dict',
                'conv': list(('conv_profile_fixed', )),
                'edit': 'ja_edit_profile',
                'restore': 'ja_revert_to_was'
            },
            'Rectangular Pocket': {
                'pack': 'gen_pocket_rect_dro_dict',
                'conv': list(('conv_pocket_fixed', )),
                'edit': 'ja_edit_pocket',
                'restore': 'ja_revert_to_was'
            },
            'Circular Pocket': {
                'pack': 'gen_pocket_circ_dro_dict',
                'conv': list(('conv_pocket_fixed', 'conv_drill_tap_fixed')),
                'edit': 'ja_edit_pocket_circ',
                'restore': 'ja_revert_to_was'
            },
            'Drill': {
                'pack': 'gen_drill_patt_dro_dict',
                'conv': list(('conv_drill_tap_fixed', )),
                'edit': 'ja_edit_drill',
                'restore': 'ja_revert_to_was'
            },
            'Pattern Drill': {
                'pack': 'gen_drill_patt_dro_dict',
                'conv': list(('conv_drill_tap_fixed', )),
                'edit': 'ja_edit_drill',
                'restore': 'ja_revert_to_was'
            },
            'Circular Drill': {
                'pack': 'gen_drill_circ_dro_dict',
                'conv': list(('conv_drill_tap_fixed', )),
                'edit': 'ja_edit_drill',
                'restore': 'ja_revert_to_was'
            },
            'Pattern Tap': {
                'pack': 'gen_tap_patt_dro_dict',
                'conv': list(('conv_drill_tap_fixed', )),
                'edit': 'ja_edit_drill',
                'restore': 'ja_revert_to_was'
            },
            'Circular Tap': {
                'pack': 'gen_tap_circ_dro_dict',
                'conv': list(('conv_drill_tap_fixed', )),
                'edit': 'ja_edit_drill',
                'restore': 'ja_revert_to_was'
            },
            'External Thread Mill': {
                'pack': 'gen_thread_mill_ext_dro_dict',
                'conv': list(('conv_thread_mill_fixed', 'conv_drill_tap_fixed')),
                'edit': 'ja_edit_thread_mill',
                'restore': 'ja_revert_to_was'
            },
            'Internal Thread Mill': {
                'pack': 'gen_thread_mill_int_dro_dict',
                'conv': list(('conv_thread_mill_fixed', 'conv_drill_tap_fixed')),
                'edit': 'ja_edit_thread_mill',
                'restore': 'ja_revert_to_was'
            },
            'Engrave': {
                'pack': 'gen_engrave_dro_dict',
                'conv': list(('conv_engrave_fixed', )),
                'edit': 'ja_edit_engrave',
                'restore': 'ja_revert_to_was'
            },
            'Engrave Text': {
                'pack': 'gen_engrave_dro_dict',
                'conv': list(('conv_engrave_fixed', )),
                'edit': 'ja_edit_engrave',
                'restore': 'ja_revert_to_was'
            },
            'DXF': {
                'pack': 'gen_dxf_dro_dict',
                'conv': list(('conv_dxf_fixed', )),
                'edit': 'ja_edit_dxf',
                'restore': 'ja_revert_to_was'
            }
        },
        'parsing': {
            'CAM': 'parse_non_conversational_mill_gcode'
        }
    }

    icon_data = dict(
        drill_icon =  dict(icon_file = 'icon_drill_norm.31.png',     icon = None),
        face_icon =   dict(icon_file = 'icon_face_mill.31.png',      icon = None),
        thread_icon = dict(icon_file = 'icon_thread_mill.31.png',    icon = None),
        tap_icon =    dict(icon_file = 'icon_tap_head.31.png',       icon = None),
        mill_icon =   dict(icon_file = 'icon_end_mill.31.png',       icon = None),
        engrave_icon =dict(icon_file = 'icon_engrave.31.png',        icon = None),
        dxf_icon     =dict(icon_file = 'icon_dxf.31.png',            icon = None),
        )

    title_data = { 'conv_face_fixed'       : {'ref0':'conv_face_spiral_rect',   'spiral'   :('mill_face_spiral_title','spiralFacing'),           'rect'    :('mill_face_rect_title','rectangularFacing')},
                   'conv_profile_fixed'    : {'ref0':'conv_profile_rect_circ',  'rect'     :('mill_rect_profile_title','rectangularProfile'),    'circ'    :('mill_circ_profile_title','circularProfile')},
                   'conv_pocket_fixed'     : {'ref0':'conv_pocket_rect_circ',   'rect'     :('mill_rect_pocket_title','rectangularPocket'),      'circ'    :('mill_circ_pocket_title','circularPocket')},
                   'conv_drill_tap_fixed'  : {'ref0':'conv_drill_tap',          'drill'    :('mill_drill_title','drill'),                        'tap'     :('mill_tap_title','tap')},
                   'conv_thread_mill_fixed': {'ref0':'conv_thread_mill_ext_int','external' :('mill_external_thread_title','externalThread-Mill'),'internal':('mill_internal_thread_title','internalThread-Mill')},
                   'conv_engrave_fixed'    : {'ref0':'conv_engrave_flat_circ',  'flat'     :('mill_engrave_flat_title','engrave'),               'circ'    :('mill_engrave_circ_title','circularEngrave')},
                   'conv_dxf_fixed'        : {'ref0':'conv_dxf_flat_circ',      'flat'     :('mill_dxf_flat_title','dxf'),                       'circ'    :('mill_dxf_circ_title','dxf')}
                 }

    G20_data = { 'rate_units': 'inches/minute', 'blend_tol': 0.005, 'naive_tol': 0.000 }
    G21_data = { 'rate_units': 'mm/minute',     'blend_tol': 0.13,  'naive_tol': 0.000 }

    float_err = 1e-8
    def __init__(self, ui_base, status, error_handler, redis, hal):
        super(conversational, self).__init__(ui_base, status, error_handler, redis, hal)
        conversational_base.routine_names = conversational.routine_names
        conversational_base.conversational_type = "Mill"



    # ------------------------------------------------------------------------------------
    # Common - DRO set
    # ------------------------------------------------------------------------------------
    def gen_common_dro_dict(self, specific, title, swaps=None, rm=None):
       # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        mat_packer = getattr(self.ui.material_data,'conversational_text')
        dro_to_text_data = { 'title'             : ({ 'proc': 'unpack_title',        'ref':'(Mill - %s' % title,         'orig' : None , 'mod' : None }),
                             'Description'       : ({ 'proc': 'unpack_cmt',          'ref':cdl['conv_title_dro'],        'orig' : None , 'mod' : None }),
                             'Units'             : ({ 'proc': 'unpack_units',        'ref':('mm','inches'),              'orig' : None , 'mod' : None }),
                             'Work Offset'       : ({ 'proc': 'unpack_wo',           'ref':cdl['conv_work_offset_dro'],  'orig' : None , 'mod' : None }),
                             'Tool Number'       : ({ 'proc': 'unpack_fp',           'ref':cdl['conv_tool_number_dro'],  'orig' : None , 'mod' : None }),
                             'Tool Description'  : ({ 'proc': 'unpack_tool_descrip', 'ref':None,                         'orig' : None , 'mod' : None }),
                             'Tool Diameter'     : ({ 'proc': 'unpack_tool_diam',    'ref':None,                         'orig' : None , 'mod' : None }),
                             'Spindle RPM'       : ({ 'proc': 'unpack_fp',           'ref':cdl['conv_rpm_dro'],          'orig' : None , 'mod' : None }),
                             'Z Feed Rate'       : ({ 'proc': 'unpack_fp',           'ref':cdl['conv_z_feed_dro'],       'orig' : None , 'mod' : None }),
                             'Feed'              : ({ 'proc': 'unpack_fp',           'ref':cdl['conv_feed_dro'],         'orig' : None , 'mod' : None }),
                             'Z Clear Location'  : ({ 'proc': 'unpack_fp',           'ref':cdl['conv_z_clear_dro'],      'orig' : None , 'mod' : None }),
                             'Number of Z Passes': ({ 'proc': 'unpack_str',          'ref':None,                         'orig' : None , 'mod' : None }),
                             'Material'          : ({ 'proc': 'unpack_clean_str',    'ref':mat_packer,                   'orig' : None , 'mod' : None })
                            }
        rv = dro_to_text_data.copy()
        # do fixups for minor variations in keys
        # swap replaces tup[0], tup[1]
        if swaps is not None and isinstance(swaps,tuple):
            l = len(swaps)
            for n in range(0,l,2):
                rv[swaps[n+1]] = rv.pop(swaps[n])
        if rm is not None:
            for item in rm:
                rv.pop(item)
        rv.update(specific.copy())
        return rv



    def __write_std_info(self, code, title, g20_g21, units, work_offset, tn, diam, rpm):
        tool_description = self.ui.get_tool_description(tn)
        code.append('(Mill - %s G-code generated: %s )' % (title, time.asctime(time.localtime(time.time()))))
        code.append(conversational.conv_version_string())
        code.append('(Description = %s)' % self.ui.conv_dro_list['conv_title_dro'].get_text())
        code.append('(Material = %s)' % self.ui.material_data.get_conversational_text())

        # list all parameters in output comments
        code.append('\n(Units = %s %s)' % (g20_g21, units))
        code.append('(Work Offset = %s)' % work_offset)
        code.append('(Tool Number = %2d)' % tn)
        code.append('(Tool Description = %s)' % tool_description)
        code.append('(Tool Diameter = %s %s)' % (diam, units))
        code.append('(Spindle RPM = %d)' % rpm)

    def conv_data_common(self, tool_number=None, report = 'all'):
        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210
        dat_comm = conversational_base._g21_data if is_metric else conversational_base._g20_data
        dat_tool = conversational.G21_data       if is_metric else conversational.G20_data
        if report == 'metric': return is_metric
        if report == 'formats' : return (dat_comm['dro_fmt'], dat_comm['feed_fmt'])
        if report == 'convert' : return (is_metric, dat_comm['units'], dat_tool['rate_units'], dat_comm['ttable_conv'])
        if report == 'convert_dimension' : return (is_metric, dat_comm['dro_fmt'], dat_comm['units'], dat_comm['ttable_conv'])
        return (is_metric, \
                dat_comm['gcode'], \
                dat_comm['dro_fmt'], \
                dat_comm['feed_fmt'], \
                dat_comm['units'], \
                dat_tool['rate_units'], \
                dat_comm['round_off'], \
                dat_tool['blend_tol'], \
                dat_tool['naive_tol'], \
                dat_comm['ttable_conv'])

    # ------------------------------------------------------------------------------------
    # Face
    # ------------------------------------------------------------------------------------
    def ja_edit_face(self, routine_data):
        # using this following will NOT allow users to JA edit and switch
        # facing styles, in this case styles share the same DROs so it should be
        # allowed
        restore_data = dict(
            spir_rect = 'rect' if self.ui.conv_face_spiral_rect == 'rect' else 'spiral',
            restore_proc = getattr(self, 'ja_restore_edit_face_page')
        )
        self.ui.conv_face_spiral_rect = 'spiral' if routine_data['segment data']['Style']['mod'] == 'Rectangular' else 'rect'

        self.ui.on_face_spiral_rect_set_state()
        self.ja_edit_general(routine_data)
        self.ui._update_stepover_hints(page_id='conv_face_fixed')
        return restore_data

    def ja_restore_edit_face_page(self, restore_data):
        self.ui.conv_face_spiral_rect = 'rect' if restore_data['spir_rect'] == 'spiral' else 'spiral'
        self.ui.on_face_spiral_rect_set_state()

    def gen_face_dro_dict(self):
        # ui is a base class attribute
        fdl = self.ui.face_dro_list
        dro_to_text_data = { # specific DROs
                             'Style'             : ({ 'proc': 'unpack_stl','ref':'face_spirial_rect_to_str',   'orig' : None , 'mod' : None }),
                             'Stepover'          : ({ 'proc': 'unpack_fp', 'ref':fdl['face_stepover_dro'],     'orig' : None , 'mod' : None }),
                             'Z Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_z_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'    : ({ 'proc': 'unpack_fp', 'ref':fdl['face_z_doc_dro'],        'orig' : None , 'mod' : None }),
                             'X Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_x_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_x_end_dro'],        'orig' : None , 'mod' : None }),
                             'Y Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_y_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_y_end_dro'],        'orig' : None , 'mod' : None }),
                             'revert'            : ({ 'attr': 'conv_face_spiral_rect', 'ref':'spiral',         'orig' : None ,  'ja_diff' : 'no'},),
                             'focus'             : ({ 'proc': None,        'ref':fdl['face_x_start_dro']})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Spiral Face',('Feed','Feed Rate'))

    def gen_face_rect_dro_dict(self):
        # ui is a base class attribute
        fdl = self.ui.face_dro_list
        dro_to_text_data = { # specific DROs
                             'Style'             : ({ 'proc': 'unpack_stl','ref':'face_spirial_rect_to_str',   'orig' : None , 'mod' : None }),
                             'Stepover'          : ({ 'proc': 'unpack_fp', 'ref':fdl['face_stepover_dro'],     'orig' : None , 'mod' : None }),
                             'Z Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_z_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'    : ({ 'proc': 'unpack_fp', 'ref':fdl['face_z_doc_dro'],        'orig' : None , 'mod' : None }),
                             'X Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_x_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_x_end_dro'],        'orig' : None , 'mod' : None }),
                             'Y Start Location'  : ({ 'proc': 'unpack_fp', 'ref':fdl['face_y_start_dro'],      'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':fdl['face_y_end_dro'],        'orig' : None , 'mod' : None }),
                             'revert'            : ({ 'attr': 'conv_face_spiral_rect', 'ref':'rect',           'orig' : None , 'ja_diff' : 'no'},),
                             'focus'             : ({ 'proc': None,        'ref':fdl['face_x_start_dro'],      'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Rectangular Face',('Feed','Feed Rate'))

    def generate_face_gcode(self, conv_dro_list, face_dro_list, face_spirial_rect):
        def __adjust_tool_path_bounds(_tpb):
            width_step_count = float(_tpb.width())/stepover
            width_ceiling = math.ceil(width_step_count)
            height_step_count = float(_tpb.height())/stepover
            height_ceiling = math.ceil(height_step_count)
            if width_step_count < height_step_count and width_ceiling > width_step_count:
                width_diff = width_ceiling*stepover - _tpb.width()
                _tpb.expand_width(width_diff/2.0)
            elif height_ceiling > height_step_count:
                height_diff = height_ceiling*stepover - _tpb.height()
                _tpb.expand_height(height_diff/2.0)

        __dro_format = lambda _item: dro_fmt%_item
        __newline = lambda _code: code.append('\n')
        '''Facing routine'''
        # empty python list for g code
        code = []

        # boolean to indicate errors present
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed, error  =  self.validate_param(conv_dro_list['conv_feed_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_feed, error  =  self.validate_param(conv_dro_list['conv_z_feed_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error  =  self.validate_param(conv_dro_list['conv_z_clear_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''


        # Face specific DRO variables

        valid, x_start, error =  self.validate_param(face_dro_list['face_x_start_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, x_end, error =  self.validate_param(face_dro_list['face_x_end_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, y_start, error =  self.validate_param(face_dro_list['face_y_start_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, y_end, error =  self.validate_param(face_dro_list['face_y_end_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_start, error  =  self.validate_param(face_dro_list['face_z_start_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error  =  self.validate_param(face_dro_list['face_z_end_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, raw_z_doc, error  =  self.validate_param(face_dro_list['face_z_doc_dro'], '')
        z_doc = math.fabs(raw_z_doc)
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        valid, stepover, error  =  self.validate_param(face_dro_list['face_stepover_dro'], '')
        if not valid:
            self.error_handler.write('Conversational Facing entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places

        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
                                 # equal except for float value rounding

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv
        tool_radius = tool_dia / 2.0
        xy_tool_clr = tool_radius * 1.2
        x_dro_start = x_start
        x_dro_end = x_end
        y_dro_start = y_start
        y_dro_end = y_end

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Facing error - Z Start must be larger than Z End'
            cparse.raise_alarm(face_dro_list['face_z_start_dro'], error_msg)
            cparse.raise_alarm(face_dro_list['face_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Facing error - Z range too small or bad Z entry value'
            cparse.raise_alarm(face_dro_list['face_z_start_dro'], error_msg)
            cparse.raise_alarm(face_dro_list['face_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = 'Conversational Facing error - Z Clear must be larger than Z Start'
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(face_dro_list['face_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(z_end - z_start)
        if z_doc > z_range + conversational.float_err:
            ok = False
            error_msg = "Conversational Facing error - Z Depth of Cut can not be bigger than the Z range of cut"
            cparse.raise_alarm(face_dro_list['face_z_start_dro'], error_msg)
            cparse.raise_alarm(face_dro_list['face_z_end_dro'], error_msg)
            cparse.raise_alarm(face_dro_list['face_z_doc_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_doc == 0:
            num_z_passes = 1
        else:
            num_z_passes = int((z_range / z_doc) + .99)
            if num_z_passes == 0:  # on the rare occasion that num_z_passes is between 0.99 and 1.0
                num_z_passes = 1
        z_doc_adj = z_range / num_z_passes

        work_bounds = geoutil._rect([x_start, y_start, x_end-x_start, y_start-y_end])
        if work_bounds.width() < stepover or work_bounds.height() < stepover: stepover = 0.0
        center_only = stepover == 0.0 or work_bounds.width()< tool_dia*0.7 or work_bounds.height()<tool_dia*0.7

        # ---------------------------------------------------------------------
        # generation details, g-code header
        # ---------------------------------------------------------------------
        type_string = 'Spiral' if face_spirial_rect == 'spiral' else 'Rectangular'
        facing_op_string = '{} Face'.format(type_string)
        self.__write_std_info(code, facing_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)
        code.append('(Style = %s)' % type_string)

        code.append('\n(X Start Location = %s , X End Location = %s)' % (dro_fmt, dro_fmt) % (x_dro_start, x_dro_end))
        code.append('(Y Start Location = %s , Y End Location = %s)' % (dro_fmt, dro_fmt) % (y_dro_start, y_dro_end))
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed)
        code.append('(Stepover = %s)' % dro_fmt % stepover)

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s , Z End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))
        code.append('(Z Depth of Cut = %s , Adjusted = %s)' % (dro_fmt, dro_fmt) % (raw_z_doc, z_doc_adj))
        code.append('(Number of Z Passes = %d, direction = %d)' % (num_z_passes, z_dir))
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % z_feed)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('G30 (Go to preset G30 location)\n')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))
        code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
        code.append('S %d (RPM)' % rpm)
        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        if face_spirial_rect == 'spiral' or center_only:
            if center_only:
                work_bounds = geoutil._rect([x_start, y_start, x_end-x_start, y_start-y_end])
                tool_path_bounds = work_bounds.offset(tool_radius*1.2)
                is_vertical = tool_path_bounds.height()>tool_path_bounds.width()
                cx, cy = tool_path_bounds.center_point()
                sx, sy = cx if is_vertical else tool_path_bounds.left(), tool_path_bounds.top() if is_vertical else cy
                ex, ey = cx if is_vertical else tool_path_bounds.right(), tool_path_bounds.bottom() if is_vertical else cy
                # go to start location
                __newline(code)
                code.append('G0 X {} Y {}'.format(__dro_format(sx), __dro_format(sy)));
                code.append('G0 Z {}'.format(__dro_format(z_clear)))

                for z_cnt in range(num_z_passes):
                    __newline(code)
                    code.append('(Pass {:d})'.format(z_cnt+1))
                    code.append('F {} (Z Feed, {})'.format(feed_fmt%z_feed, rate_units))
                    code.append('G1 Z {}'.format(__dro_format(z_start - ((z_cnt+1) * z_doc_adj))))
                    code.append('F {} (Feed, {})'.format(feed_fmt%feed, rate_units))
                    code.append('G1 X {} Y {}'.format(__dro_format(ex), __dro_format(ey)));
                    code.append('G0 Z {}'.format(__dro_format(z_clear)))
                    # swap start nd end points...
                    _tx, _ty = ex, ey
                    ex, ey = sx, sy
                    sx, sy = _tx, _ty

            else: # spiral facing...
                corner_adjustment = .33*tool_radius #.33 = (1.0-math.sin(math.pi/4.0))*1.1
                tool_path_bounds = work_bounds.offset(tool_radius-stepover)
                tool_path_bounds = tool_path_bounds.offset((0.0,corner_adjustment, corner_adjustment, -corner_adjustment))
                __adjust_tool_path_bounds(tool_path_bounds)
                # test that the first the initial tool_path_bounds.left less tool_radius, i,e.,
                # the first cut on the left is not greater than the workbounds plus one stepover...
                # Note: '0.0-stepover' keeps pylint happy
                if tool_path_bounds.left()+tool_radius>work_bounds.left()+stepover: tool_path_bounds.move_left(0.0-stepover)
                # go to start location
                _sx, _sy = work_bounds.left()-tool_radius*1.1, tool_path_bounds.top()
                __newline(code)
                code.append('G0 X {} Y {}'.format(__dro_format(_sx), __dro_format(_sy)));
                code.append('G0 Z {}'.format(__dro_format(z_clear)))

                for z_cnt in range(num_z_passes):
                    # 'material_left is a rectangle that represents the material left as the cutter
                    # spirals in.
                    material_left = work_bounds.copy()
                    _tpb_copy = tool_path_bounds.copy()
                    _lx, _ly = _sx, _sy
                    current_z = z_start - ((z_cnt+1) * z_doc_adj)
                    # infinite loop guard
                    if len(code) > CONVERSATIONAL_MAX_LINES:
                        raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                    __newline(code)
                    code.append('(Pass {:d})'.format(z_cnt+1))
                    code.append('F {} (Z Feed, {})'.format(feed_fmt%z_feed, rate_units))
                    code.append('G1 Z {}'.format(__dro_format(current_z)))
                    code.append('F {} (Feed, {})'.format(feed_fmt%feed, rate_units))

                    __newline(code)
                    while len(code) < CONVERSATIONAL_MAX_LINES:
                        # 'material_left' get whittled down by every pass
                        # until here is nothing left..at which point the
                        #'_tpb_copy' (tool_path_bounds) may contract one more time
                        # until '_material_left.has_dimension' fails.
                        # NOTE: if the last cut, then the 'corner_adjustment' is added
                        # to make sure there is no 'tab' left on the material due to the
                        # difference between the cutter_radius * sin(45°) and cutter_radius
                        if not material_left.has_dimension(): break;
                        _lx = _tpb_copy.right()
                        material_left.set_top(_ly-tool_radius)
                        if not material_left.has_dimension(): _lx += corner_adjustment
                        code.append('G1 X {}'.format(__dro_format(_lx)));

                        if not material_left.has_dimension(): break;
                        _ly = _tpb_copy.bottom()
                        material_left.set_right(_lx-tool_radius)
                        if not material_left.has_dimension(): _ly -= corner_adjustment
                        code.append('G1 Y {}'.format(__dro_format(_ly)));

                        if not material_left.has_dimension(): break;
                        _lx = _tpb_copy.left()
                        material_left.set_bottom(_ly+tool_radius)
                        if not material_left.has_dimension(): _lx -= corner_adjustment
                        code.append('G1 X {}'.format(__dro_format(_lx)));

                         # shrink the tool path bounds by stepover...
                         # Note: '0.0-stepover' keeps pylint happy
                        _tpb_copy = _tpb_copy.offset(0.0-stepover)
                        if not material_left.has_dimension(): break;
                        _ly = _tpb_copy.top()
                        material_left.set_left(_lx+tool_radius)
                        if not material_left.has_dimension(): _ly += corner_adjustment
                        code.append('G1 Y {}'.format(__dro_format(_ly)));

                    code.append('G0 Z {}'.format(__dro_format(current_z + (2.54 if is_metric else .1))))
                    if z_cnt < num_z_passes-1:
                        __newline(code)
                        code.append('G0 X {} Y {}'.format(__dro_format(_sx), __dro_format(_sy)));

        else: # rectangular
            tool_radius_plus = tool_radius + ( tool_radius * .15 )
            x_left = x_start - tool_radius_plus
            x_right = x_end + tool_radius_plus
            y_range = y_start-y_end
            y_range_plus = y_range + (stepover * .2)
            y_center = y_start-y_range/2.0
            y_rem,y_steps = math.modf(y_range_plus / stepover)
            if (y_steps * stepover) < y_range_plus:
                y_steps += 1
            y_steps = int(y_steps)
            half_swath = (y_steps / 2) * stepover
            if y_steps % 2 == 0:
                half_swath -= (stepover / 2)

            y_path = y_center - half_swath

            code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_right, y_path))
            code.append('G0 Z %s' % dro_fmt % z_clear)

            for z_cnt in range(1,num_z_passes+1 ):
                code.append('\n(Pass %d)' % z_cnt)
                direction = 'left'
                if z_cnt>1: code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_right, y_path))
                code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s' % dro_fmt % (z_start - (z_cnt * z_doc_adj)))
                passes = y_steps
                y_new = y_path

                while passes > 0:
                    # infinite loop guard
                    if len(code) > CONVERSATIONAL_MAX_LINES:
                        raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                    passes -= 1
                    x_end_pos = x_left if direction == 'left' else x_right
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_end_pos, y_new))
                    if passes > 0:
                        y_new = y_new + stepover
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_end_pos, y_new))
                        direction = 'left' if direction == 'right' else 'right'
                code.append('\nG0 Z %s' % dro_fmt % z_clear)



        code.append('\nG0 Z %s' % dro_fmt % z_clear)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, facing_op_string)

        return ok, code


    # ------------------------------------------------------------------------------------
    # Profile
    # ------------------------------------------------------------------------------------
    def ja_edit_profile(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            rect_circ = 'rect' if self.ui.conv_profile_rect_circ == 'rect' else 'circ',
            disable_button = self.ui.button_list['profile_rect_circ'],
            restore_proc = getattr(self, 'ja_restore_edit_profile_page')
        )
        if routine_data['segment data'].has_key('Profile Circle Diameter'):
            self.ui.conv_profile_rect_circ = 'rect'
        else:
            self.ui.conv_profile_rect_circ = 'circ'

        self.ui.on_profile_rect_circ_set_state()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        self.ui._update_stepover_hints(page_id='conv_profile_fixed')
        return restore_data

    def ja_restore_edit_profile_page(self, restore_data):
        self.ui.conv_profile_rect_circ = 'rect' if restore_data['rect_circ'] == 'circ' else 'circ'
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.on_profile_rect_circ_set_state()


    def get_profile_dims(self): pass

    def gen_profile_dro_dict(self):
        pdl = self.ui.profile_dro_list

        dro_to_text_data = { # specific DROs
                             'Stepover'          : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_stepover_dro'],       'orig' : None , 'mod' : None }),
                             'Z Start Location'  : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_z_start_dro'],        'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':pdl['profile_z_end_dro'],          'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'    : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_z_doc_dro'],          'orig' : None , 'mod' : None }),
                             'X Start Location'  : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_x_start_dro'],        'orig' : None , 'mod' : None },
                                                    { 'proc': 'unpack_fp', 'ref':pdl['profile_x_end_dro'],          'orig' : None , 'mod' : None }),
                             'Y Start Location'  : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_y_start_dro'],        'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':pdl['profile_y_end_dro'],          'orig' : None , 'mod' : None }),
                             'X Profile Start'   : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_x_prfl_start_dro'],   'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':pdl['profile_x_prfl_end_dro'],     'orig' : None , 'mod' : None }),
                             'Y Profile Start'   : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_y_prfl_start_dro'],   'orig' : None , 'mod' : None },
                                                    { 'proc': None,        'ref':pdl['profile_y_prfl_end_dro'],     'orig' : None , 'mod' : None }),
                             'Corner Radius'     : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_radius_dro'],         'orig' : None , 'mod' : None }),
                             'revert'            : ({ 'attr': 'conv_profile_rect_circ', 'ref':'rect',               'orig' : None , 'ja_diff' : 'no'},),
                             'focus'             : ({ 'proc': None,        'ref':pdl['profile_x_start_dro'],       'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Rectangular Profile')


    def gen_profile_circ_dro_dict(self):
        pdl = self.ui.profile_dro_list

        dro_to_text_data = { # specific DROs
                             'Stepover'               : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_stepover_dro'],'orig' : None , 'mod' : None }),
                             'Z Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_z_start_dro'], 'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['profile_circ_z_end_dro'],   'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'         : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_z_doc_dro'],   'orig' : None , 'mod' : None }),
                             'X Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_x_start_dro'], 'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['profile_circ_x_end_dro'],   'orig' : None , 'mod' : None }),
                             'Y Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_y_start_dro'], 'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['profile_circ_y_end_dro'],   'orig' : None , 'mod' : None }),
                             'Profile Circle Diameter': ({ 'proc': 'unpack_fp', 'ref':pdl['profile_circ_diameter_dro'],'orig' : None , 'mod' : None }),
                             'Profile X Center'       : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_x_center_dro'],     'orig' : None , 'mod' : None }),
                             'Profile Y Center'       : ({ 'proc': 'unpack_fp', 'ref':pdl['profile_y_center_dro'],     'orig' : None , 'mod' : None }),
                             'revert'                 : ({ 'attr': 'conv_profile_rect_circ', 'ref':'circ',             'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                  : ({ 'proc': None,        'ref':pdl['profile_circ_x_start_dro'], 'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Circular Profile')

    def generate_profile_gcode(self, conv_dro_list, profile_dro_list, profile_type):

        # empty python list for g code
        code = []

        # boolean to indicate errors present
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)
        error_header = 'Conversational Profile entry error - '

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''

        valid, rpm, error = self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''

        valid, feed, error = self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''

        valid, z_feed, error = self.validate_param(conv_dro_list['conv_z_feed_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write(error_header + error)
            ok = False
            return ok, ''


        # Profile specific DRO variables

        if profile_type == 'rect':
            valid, stepover, error = self.validate_param(profile_dro_list['profile_stepover_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_start, error  =  self.validate_param(profile_dro_list['profile_x_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_end, error  =  self.validate_param(profile_dro_list['profile_x_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_start, error  =  self.validate_param(profile_dro_list['profile_y_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_end, error  =  self.validate_param(profile_dro_list['profile_y_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, z_start, error  =  self.validate_param(profile_dro_list['profile_z_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, z_end, error  =  self.validate_param( profile_dro_list['profile_z_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, raw_z_doc, error =  self.validate_param(profile_dro_list['profile_z_doc_dro'])
            z_doc = math.fabs(raw_z_doc)
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_pf_start, error  =  self.validate_param(profile_dro_list['profile_x_prfl_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_pf_end, error  =  self.validate_param(profile_dro_list['profile_x_prfl_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_pf_start, error  =  self.validate_param(profile_dro_list['profile_y_prfl_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_pf_end, error  =  self.validate_param(profile_dro_list['profile_y_prfl_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, corner_radius, error =  self.validate_param(profile_dro_list['profile_radius_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''
        else: # 'circ'
            valid, stepover, error = self.validate_param(profile_dro_list['profile_circ_stepover_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_start, error  =  self.validate_param(profile_dro_list['profile_circ_x_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_end, error  =  self.validate_param(profile_dro_list['profile_circ_x_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_start, error  =  self.validate_param(profile_dro_list['profile_circ_y_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_end, error  =  self.validate_param(profile_dro_list['profile_circ_y_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, z_start, error  =  self.validate_param(profile_dro_list['profile_circ_z_start_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, z_end, error  =  self.validate_param( profile_dro_list['profile_circ_z_end_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, raw_z_doc, error =  self.validate_param(profile_dro_list['profile_circ_z_doc_dro'])
            z_doc = math.fabs(raw_z_doc)
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, circ_diameter, error  =  self.validate_param(profile_dro_list['profile_circ_diameter_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, x_center, error  =  self.validate_param(profile_dro_list['profile_x_center_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            valid, y_center, error  =  self.validate_param(profile_dro_list['profile_y_center_dro'])
            if not valid:
                self.error_handler.write(error_header + error)
                ok = False
                return ok, ''

            corner_radius = circ_diameter / 2
            x_pf_start = x_center - corner_radius
            x_pf_end = x_center + corner_radius
            y_pf_start = y_center + corner_radius
            y_pf_end = y_center - corner_radius


        perimeter_only = False
        if stepover == 0:
            perimeter_only = True

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv
        tool_radius = tool_dia / 2

        xy_tool_clr = tool_dia * (1.2 / 2)

        feed_adj = feed

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Profile error - Z Start must be larger than Z End'
            cparse.raise_alarm(profile_dro_list['profile_z_start_dro'], error_msg)
            cparse.raise_alarm(profile_dro_list['profile_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Profile error - Z range too small or bad Z entry value'
            cparse.raise_alarm(profile_dro_list['profile_z_start_dro'], error_msg)
            cparse.raise_alarm(profile_dro_list['profile_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = "Conversational Profile error - Z Clear must be larger than Z Start"
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(profile_dro_list['profile_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(z_end - z_start)

        if z_doc > z_range + conversational.float_err:
            ok = False
            error_msg = 'Conversational Profile error - Z Depth of Cut can not be bigger than the Z range of cut'
            cparse.raise_alarm(profile_dro_list['profile_z_start_dro'], error_msg)
            cparse.raise_alarm(profile_dro_list['profile_z_end_dro'], error_msg)
            cparse.raise_alarm(profile_dro_list['profile_z_doc_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_doc == 0:
            num_z_passes = 1
        else:
            num_z_passes = int((z_range / z_doc) + .99)
            if num_z_passes == 0:  # on the rare occasion that num_z_passes is between 0.99 and 1.0
                num_z_passes = 1
        z_doc_adj = z_range / num_z_passes

        if tool_radius == 0:
            ok = False
            error_msg = 'Conversational Profile error - Check tool. Cannot profile with zero tool diameter'
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok,''

        if stepover > 0:
            # check tool diameter...
            if stepover > (tool_radius * 2):
                ok = False
                error_msg = 'Conversational Profile error - Check tool. Can not profile with stepover greater than tool diameter'
                cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
                cparse.raise_alarm(profile_dro_list['profile_stepover_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok,''

            # North Range

            if y_start < y_pf_start:
                ok = False
                if profile_type == 'rect':
                    error_msg = 'Conversational Profile error - Y Start must be larger than Y Profile Start'
                    cparse.raise_alarm(profile_dro_list['profile_y_start_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_y_prfl_start_dro'], error_msg)
                else:
                    error_msg = 'Conversational Profile error - Y Start must be larger than Y Center plus half the Diameter'
                    cparse.raise_alarm(profile_dro_list['profile_y_start_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_y_center_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_circ_diameter_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

            north_range = (y_start - y_pf_start)
            num_north_cuts = int(north_range / stepover)
            if north_range <= 0:
                num_north_cuts = 0
            north_base = y_pf_start + tool_radius + (num_north_cuts * stepover)
            num_north_cuts += 1

            # East Range
            if x_end < x_pf_end:
                ok = False
                if profile_type == 'rect':
                    error_msg = "Conversational Profile error - X End must be larger than X Profile End"
                    cparse.raise_alarm(profile_dro_list['profile_x_end_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_x_prfl_end_dro'], error_msg)
                else:
                    error_msg = "Conversational Profile error - X End must be larger than X Center plus half the Diameter"
                    cparse.raise_alarm(profile_dro_list['profile_x_end_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_x_center_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_circ_diameter_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

            east_range = (x_end - x_pf_end)
            num_east_cuts = int(east_range / stepover)
            if east_range <= 0:
                num_east_cuts = 0
            east_base = x_pf_end + tool_radius + (num_east_cuts * stepover)
            num_east_cuts += 1

            # South Range
            if y_end > y_pf_end:
                ok = False
                if profile_type == 'rect':
                    error_msg = "Conversational Profile error - Y End must be smaller than Y Profile End"
                    cparse.raise_alarm(profile_dro_list['profile_y_end_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_y_prfl_end_dro'], error_msg)
                else:
                    error_msg = "Conversational Profile error - Y End must be smaller than Y Center minus half the Diameter"
                    cparse.raise_alarm(profile_dro_list['profile_y_end_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_y_center_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_circ_diameter_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

            south_range = (y_pf_end - y_end)
            num_south_cuts = int(south_range / stepover)
            if south_range <= 0:
                num_south_cuts = 0
            south_base = y_pf_end - tool_radius - (num_south_cuts * stepover)
            num_south_cuts += 1

            # West Range
            if x_start > x_pf_start:
                ok = False
                if profile_type == 'rect':
                    error_msg = "Conversational Profile error - X Start must be smaller than X Profile Start"
                    cparse.raise_alarm(profile_dro_list['profile_x_start_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_x_prfl_start_dro'], error_msg)
                else:
                    error_msg = "Conversational Profile error - X Start must be smaller than X Center minus half the Diameter"
                    cparse.raise_alarm(profile_dro_list['profile_x_start_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_x_center_dro'], error_msg)
                    cparse.raise_alarm(profile_dro_list['profile_circ_diameter_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

            west_range = (x_pf_start - x_start)
            num_west_cuts = int(west_range / stepover)
            if west_range <= 0:
                num_west_cuts = 0
            west_base = x_pf_start - tool_radius - (num_west_cuts * stepover)
            num_west_cuts += 1

            if corner_radius > 0:
                corner_diagonal = math.sqrt(2 * corner_radius**2)
                corner_range = corner_diagonal - corner_radius
                corner_passes = int(corner_range / stepover) + 1

        x_pf_width = math.fabs(x_pf_end - x_pf_start)
        y_pf_width = math.fabs(y_pf_end - y_pf_start)

        if (corner_radius * 2) > x_pf_width:
            if (x_pf_width + round_off) >= (corner_radius * 2):
                corner_radius = x_pf_width / 2
            else:
                ok = False
                entry_type = 0  # bad entry
                error_msg = "Conversational Profile error - corner radius too big or profile width too small"
                cparse.raise_alarm(profile_dro_list['profile_x_prfl_start_dro'], error_msg)
                cparse.raise_alarm(profile_dro_list['profile_x_prfl_end_dro'], error_msg)
                cparse.raise_alarm(profile_dro_list['profile_radius_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

        if (corner_radius * 2) > y_pf_width:
            if (y_pf_width + round_off) >= (corner_radius * 2):
                corner_radius = y_pf_width / 2
            else:
                ok = False
                entry_type = 0  # bad entry
                error_msg = "Conversational Profile error - corner radius too big or profile width too small"
                cparse.raise_alarm(profile_dro_list['profile_y_prfl_start_dro'], error_msg)
                cparse.raise_alarm(profile_dro_list['profile_y_prfl_end_dro'], error_msg)
                cparse.raise_alarm(profile_dro_list['profile_radius_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

        self.profile_gen = profile_path_generator( code,
                                                   x_pf_start, x_pf_end, y_pf_start, y_pf_end,
                                                   x_start, x_end, y_start,y_end,
                                                   tool_radius, stepover, corner_radius,
                                                   is_metric, z_clear, feed, z_feed )

        # generation details
        profile_op_string = '{} Profile'.format('Rectangular' if profile_type == 'rect' else 'Circular')
        self.__write_std_info(code, profile_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)
        # list all parameters in comments

        code.append('\n(Feed = %s %s)' % (feed_fmt, rate_units) % feed)
        code.append('(Stepover = %s)' % dro_fmt % stepover)

        code.append('\n(--- Perimeter Locations ---)')
        code.append('(X Start Location = %s, X End Location = %s)' % (dro_fmt, dro_fmt) % (x_start, x_end))
        code.append('(Y Start Location = %s, Y End Location = %s)' % (dro_fmt, dro_fmt) % (y_start, y_end))

        if profile_type == 'rect':
            code.append('\n(--- Rectangular Profile Locations ---)')
            code.append('(X Profile Start Location = %s, End Location = %s)' % (dro_fmt, dro_fmt) % (x_pf_start, x_pf_end))
            code.append('(Y Profile Start Location = %s, End Location = %s)' % (dro_fmt, dro_fmt) % (y_pf_start, y_pf_end))
            code.append('(Corner Radius = %s)' % corner_radius)
        else:
            code.append('\n(--- Circular Profile Locations ---)')
            code.append('(Profile X Center Location = %s)' % (dro_fmt) % (x_center))
            code.append('(Profile Y Center Location = %s)' % (dro_fmt) % (y_center))
            code.append('(Profile Circle Diameter = %s)' % circ_diameter)

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s , End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))
        code.append('(Z Depth of Cut = %s , Adjusted = %s)' % (dro_fmt, dro_fmt) % (raw_z_doc, z_doc_adj))
        code.append('(Number of Z Passes = %d, direction = %d)' % (num_z_passes, z_dir))
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % z_feed)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nF %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
        code.append('S %d (RPM)' % rpm)
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # generate code ..
        z_curr_depth = z_start
        for i in range(num_z_passes):
            z_curr_depth -= z_doc_adj
            if z_curr_depth < z_end:
                z_curr_depth = z_end
            self.profile_gen.run(z_curr_depth, i+1)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, profile_op_string)

        return ok, code


    # ------------------------------------------------------------------------------------
    # Pocket - Rectangular
    # ------------------------------------------------------------------------------------
    def ja_edit_pocket(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            rect_circ = 'rect' if self.ui.conv_pocket_rect_circ == 'rect' else 'circ',
            disable_button = self.ui.button_list['pocket_rect_circ'],
            restore_proc = getattr(self, 'ja_restore_edit_pocket_page')
        )
        if routine_data['segment data'].has_key('Pocket Diameter'):
            self.ui.conv_pocket_rect_circ = 'rect'
        else:
            self.ui.conv_pocket_rect_circ = 'circ'

        self.ui.on_pocket_rect_circ_set_state()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        self.ui._update_stepover_hints(page_id='conv_pocket_fixed')
        return restore_data

    def ja_restore_edit_pocket_page(self, restore_data):
        self.ui.conv_pocket_rect_circ = 'rect' if restore_data['rect_circ'] == 'circ' else 'circ'
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.on_pocket_rect_circ_set_state()

    def gen_pocket_rect_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.pocket_rect_dro_list
        dro_to_text_data = { # specific DROs
                             'Stepover'               : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_stepover_dro'],  'orig' : None , 'mod' : None }),
                             'Z Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_z_start_dro'],   'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['pocket_rect_z_end_dro'],     'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'         : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_z_doc_dro'],     'orig' : None , 'mod' : None }),
                             'X Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_x_start_dro'],   'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['pocket_rect_x_end_dro'],     'orig' : None , 'mod' : None }),
                             'Y Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_y_start_dro'],   'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['pocket_rect_y_end_dro'],     'orig' : None , 'mod' : None }),
                             'Corner Radius'          : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_rect_corner_radius_dro'],  'orig' : None , 'mod' : None }),
                             'revert'                 : ({ 'attr': 'conv_pocket_rect_circ', 'ref':'rect',               'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                  : ({ 'proc': None,        'ref':pdl['pocket_rect_x_start_dro'],   'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Rectangular Pocket')

    def get_pocket_dims(self): pass

    def generate_pocket_rect_gcode(self, conv_dro_list, pocket_rect_dro_list):
        """
        Pocket has two operations: entry to each Z DoC step, stepover cuts from the
        pocket center to the perimeter.

        Entries and stepover cuts vary for each pocket configuration:
            Major axis on X or Y
                Pocket width too small to fit tool diameter - Fails
                Pocket width only fits tool; entry and final perimeter cut at each Z DoC
                Pocket width allows entry and stepover cuts
                    Odd number of stepover cuts start on pocket center
                    Even number of stepover cuts start on 1/2 offset from center
            Major axis length too short for 2 degree ramp-in (path at least one tool
                diameter long), therefore straight Z plunge

        Ramping description here:
        http://www.sandvik.coromant.com/en-gb/knowledge/milling/application_overview/holes_and_cavities/two_axes_ramping_linear/Pages/default.aspx
        See "Progressive Ramping"

        A zero corner radius, or a value less than the tool radius creates arc cuts with
        negligible radius to prevent an arc command error. We could conditionally
        include the arc commands rather than fudge the radius.

        Arc cuts have feed rate compensation since the feed rate at the tool
        radius plus the arc radius is higher than the programed linear feed
        rate (feed at tool control point). Feed reduction is alowed but not
        increase since cutting sweep can start at the tool center where the
        normal feed would be appropriate.

        Stepover values:
            0 = perimeter slot mode, for when the center of the stock does
            not need to be cleared first, such as for cutting through the
            stock and having the center fall out.

            80% of tool diameter or less = enough overlap to cut rectagular
            corners.

        Z DoC values:
            0 = Plunge cut to z_end and make one z pass
            value of full range = non plunge entry to z_end and make one z pass
            less than full range = 2 or more adjusted z passes with non plunge
            entry
        """

        # empty python list for g code
        code = []

        # boolean to indicate errors present
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error = self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed, error = self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_feed, error = self.validate_param(conv_dro_list['conv_z_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        # Pocket Rectangular specific DRO variables

        valid, x_start, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_x_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, x_end, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_x_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, y_start, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_y_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, y_end, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_y_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_start, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, raw_z_doc, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_z_doc_dro'])
        z_doc = math.fabs(raw_z_doc)
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, stepover, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_stepover_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, corner_radius, error =  self.validate_param(pocket_rect_dro_list['pocket_rect_corner_radius_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        feed_min = 2.54 if is_metric else 0.1
        angle_fmt  = '%3.1f'

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv
        if tool_dia <= 0:
            error_msg = "Conversational Pocket entry error - tool diameter needs to be greater than 0"
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            ok = False
            return ok, ' '

        tool_radius = tool_dia / 2

        x_width = math.fabs(x_end - x_start)
        y_width = math.fabs(y_end - y_start)
        x_pocket_center = (x_end + x_start) / 2
        y_pocket_center = (y_end + y_start) / 2

        # distance from the pocket center to a major axis endpoint
        major_center_offset = math.fabs((x_width - y_width) / 2)

        # which is the major axis?
        if x_width >= y_width :
            major = 0  # X
            pocket_width = y_width
            pocket_length = x_width
        else :
            major = 1  # Y
            pocket_width = x_width
            pocket_length = y_width

        if corner_radius >= tool_radius:
            corner_radius_true = corner_radius
        else:
            corner_radius_true = tool_radius

        y_crnr_rad_os = (pocket_width / 2) - corner_radius

        # is the pocket wide enough to fit the tool?
        if pocket_width < tool_dia :  # No - oops, we can't go any further
            ok = False
            entry_type = 0  # bad entry
            if major == 0:  # X
                error_msg = "Conversational Pocket entry error - tool diameter too big or pocket width too small"
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_start_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_end_dro'], error_msg)
                cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''
            else:           # Y
                error_msg = "Conversational Pocket entry error - tool diameter too big or pocket width too small"
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_start_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_end_dro'], error_msg)
                cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

        elif pocket_width < (2 * corner_radius_true) :
            ok = False
            entry_type = 0  # bad entry
            if major == 0:  # X
                error_msg = "Conversational Pocket entry error - corner radius too big or pocket width too small"
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_start_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_end_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_corner_radius_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''
            else:           # Y
                error_msg = "Conversational Pocket entry error - corner radius too big or pocket width too small"
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_start_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_end_dro'], error_msg)
                cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_corner_radius_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

        if stepover >= tool_dia :  # This produces a bad path calculation, so weed it out for now
            ok = False
            entry_type = 0  # bad entry
            error_msg = "Conversational Pocket entry error - tool diameter too small or stepover too big"
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_stepover_dro'], error_msg)
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        path_width_range = pocket_width - tool_dia
        if stepover > 0:
            rows = int(path_width_range / stepover) + 1
            stepover_adj = path_width_range / rows
        else:  # stepover = 0 = single perimeter pass
            rows = 0
            stepover_adj = 0.0

        stepover2 = stepover_adj / 2
        num_xy_passes = int(rows / 2)

        path_radius = corner_radius_true - tool_radius  # used for feed rate compensation for arced tool paths
        if path_radius == 0:
            path_radius = .0001

        if x_end > x_start:
            x_dir = 1
        #elif x_end < x_start:
        #    x_dir = -1
        else:
            ok = False
            x_dir = 0
            error_msg = "Conversational Pocket error - X range too small or bad X entry value, X End needs to be > X Start"
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_start_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_x_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if y_end < y_start:
            y_dir = 1
        #elif y_end < y_start:
        #    y_dir = -1
        else:
            ok = False
            y_dir = 0
            error_msg = "Conversational Pocket error - Y range too small or bad Y entry value, Y End needs to be > Y Start"
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_start_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_y_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        y_range = math.fabs(y_end - y_start)

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Pocket error - Z Start must be larger than Z End'
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Pocket error - Z range too small or bad Z entry value'
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = "Conversational Pocket error - Z Start must be smaller than Z Clear"
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(z_end - z_start)
        if z_doc > z_range + conversational.float_err:
            ok = False
            error_msg = "Conversational Pocket error - Z Depth of Cut cannot be bigger than the Z range of cut"
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_end_dro'], error_msg)
            cparse.raise_alarm(pocket_rect_dro_list['pocket_rect_z_doc_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_end_only = False
        if z_doc == 0 or z_doc >= z_range - conversational.float_err:
            num_z_passes = 1
            z_end_only = True
        else:
            num_z_passes = int((z_range / z_doc) + 0.99)
            if num_z_passes == 0:  # on the rare occasion that num_z_passes between 0.99 and 1.0
                num_z_passes = 1
        z_doc_adj = z_range / num_z_passes
        z_doc = z_doc_adj

        z_doc_list = [z_start]
        for z_cnt in range(1, num_z_passes):
            z_doc_list.append(z_start + (z_dir * z_cnt * z_doc_adj))
        z_doc_list.append(z_end)
        #print "--kw pocket rect z_doc_list =", z_doc_list

        # determine type of entry path
        if pocket_width > 2 * tool_dia:
            entry_type = 1  # helical, then call square, wings, and perimeter
        elif major_center_offset > (1.5 * tool_radius):  # is pocket length long enough for ramp?
            # technically, ramping could fit in major_center_offset > tool_radius but produces too
            # many ramp passes. 1.5 * tool_radius seems like a more reasonable compromise
            entry_type = 2  # linear ramp, then call perimeter
        else:
            entry_type = 3  # straight Z plunge, then call perimeter

        if stepover == 0:
            if z_end_only is True:
                entry_type = 5  # perimeter slot only, simple z plunge entry
            else:
                entry_type = 4

        #print "--kw entry type =", entry_type

        # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
        feed_adj = (feed * path_radius / corner_radius_true) if corner_radius_true > 0 else feed
        feed_adj = max(feed_adj,feed_min)

        total_major_offset = major_center_offset + stepover2
        total_minor_offset = stepover2

        twodeginrad = math.radians(2.0)
        if entry_type == 4 or entry_type == 5:
            if corner_radius <= tool_radius:  # four straight legs
                leg1_dist = math.fabs(y_start - y_end  ) - tool_dia
                leg2_dist = math.fabs(x_end   - x_start) - tool_dia
                loop_len = (leg1_dist + leg2_dist) * 2.0
                loop_dz = z_doc  # z depth allowed, which happens to correspond to one loop, unless this goes over 2 degrees
                z_angle = math.atan(z_doc / loop_len)
                if z_angle > twodeginrad:
                    z_angle = twodeginrad
                    loop_dz = loop_len * math.tan(twodeginrad)

                #print "--kw angle =", z_angle, "radians    degrees =", math.degrees(z_angle)
                #print "--kw z_doc =", z_doc, "    loop_z =", loop_dz

                num_loops = int((z_range / loop_dz) + 2)  # make enough or a little more

                dz1 = leg1_dist * math.tan(z_angle)
                dz2 = leg2_dist * math.tan(z_angle)

                wp = []  # waypoint list
                for li in range(num_loops):
                    wpi = li * 4
                    lidz = li * loop_dz
                    wp.append([x_start + tool_radius, y_start - tool_radius, z_start - lidz])
                    if wp[wpi    ][2] <= z_end:
                        break
                    wp.append([x_start + tool_radius, y_end   + tool_radius, z_start - lidz - dz1])
                    if wp[wpi + 1][2] <= z_end:
                        break
                    wp.append([x_end   - tool_radius, y_end   + tool_radius, z_start - lidz - dz1 - dz2])
                    if wp[wpi + 2][2] <= z_end:
                        break
                    wp.append([x_end   - tool_radius, y_start - tool_radius, z_start - lidz - dz1 - dz2 - dz1])
                    if wp[wpi + 3][2] <= z_end:
                        break

                    z_doc_adj = loop_dz

            else:  # four legs with corner radii
                cornerpr = (corner_radius - tool_radius)
                cornerpd = 2 * cornerpr
                leg1_dist = math.fabs(y_start - y_end  ) - tool_dia - cornerpd  # straight y leg
                leg2_dist = math.pi * cornerpd / 4.0  # corner arc length
                leg3_dist = math.fabs(x_end   - x_start) - tool_dia - cornerpd  # straight x leg
                loop_len = ((leg1_dist + leg3_dist) * 2.0) + (leg2_dist * 4.0)
                loop_dz = z_doc  # z depth allowed, which happens to correspond to one loop, unless this goes over 2 degrees
                z_angle = math.atan(z_doc / loop_len)
                if z_angle > twodeginrad:
                    z_angle = twodeginrad
                    loop_dz = loop_len * math.tan(twodeginrad)

                #print "--kw angle =", z_angle, "radians    degrees =", math.degrees(z_angle)
                #print "--kw z_doc =", z_doc, "    loop_z =", loop_dz

                num_loops = int((z_range / loop_dz) + 2)  # make enough or a little more

                dz1 = leg1_dist * math.tan(z_angle)
                dz2 = leg2_dist * math.tan(z_angle)
                dz3 = leg3_dist * math.tan(z_angle)

                wp = []  # waypoint list
                for li in range(num_loops):
                    wpi = li * 8  # one loop has 8 waypoints
                    lidz = li * loop_dz

                    wp.append([x_start + tool_radius,
                               y_start - corner_radius,
                               z_start - lidz])
                    if wp[wpi    ][2] <= z_end:
                        break

                    wp.append([x_start + tool_radius,
                               y_end   + corner_radius,
                               z_start - lidz - dz1])
                    if wp[wpi + 1][2] <= z_end:
                        break

                    wp.append([x_start + corner_radius,
                               y_end   + tool_radius,
                               z_start - lidz - dz1 - dz2])
                    if wp[wpi + 2][2] <= z_end:
                        break

                    wp.append([x_end   - corner_radius,
                               y_end   + tool_radius,
                               z_start - lidz - dz1 - dz2 - dz3])
                    if wp[wpi + 3][2] <= z_end:
                        break

                    wp.append([x_end   - tool_radius,
                               y_end   + corner_radius,
                               z_start - lidz - dz1 - dz2 - dz3 - dz2])
                    if wp[wpi + 4][2] <= z_end:
                        break

                    wp.append([x_end   - tool_radius,
                               y_start - corner_radius,
                               z_start - lidz - dz1 - dz2 - dz3 - dz2 - dz1])
                    if wp[wpi + 5][2] <= z_end:
                        break

                    wp.append([x_end   - corner_radius,
                               y_start - tool_radius,
                               z_start - lidz - dz1 - dz2 - dz3 - dz2 - dz1 - dz2])
                    if wp[wpi + 6][2] <= z_end:
                        break

                    wp.append([x_start + corner_radius,
                               y_start - tool_radius,
                               z_start - lidz - dz1 - dz2 - dz3 - dz2 - dz1 - dz2 - dz3])
                    if wp[wpi + 7][2] <= z_end:
                        break

                    z_doc_adj = loop_dz


        # generation details
        pocket_op_string = 'Rectangular Pocket'
        self.__write_std_info(code, pocket_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('\n(X Start Location = %s, End Location = %s)' % (dro_fmt, dro_fmt) % (x_start, x_end))
        code.append('(Y Start Location = %s, End Location = %s)' % (dro_fmt, dro_fmt) % (y_start, y_end))
        code.append('(Corner Radius = %s)' % dro_fmt % corner_radius)
        code.append('(Corner Radius True = %s)' % dro_fmt % corner_radius_true)
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed)
        code.append('(Stepover = %s, Stepover Adjusted = %s)' % (dro_fmt, dro_fmt) % (stepover, stepover_adj))

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s, Z End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))
        code.append('(Z Depth of Cut = %s , Adjusted = %s)' % (dro_fmt, dro_fmt) % (raw_z_doc, z_doc_adj))
        if entry_type == 4:
            code.append('(Helix Angle = %s degrees)' % angle_fmt % math.degrees(z_angle))
        code.append('(Number of Z Passes = %d)' % num_z_passes)
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % z_feed)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nF %s (%s)' % (feed_fmt, rate_units) % feed)
        code.append('S %d (RPM)' % rpm)
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')


        if entry_type == 4:  # run along the perimeter while 2 degree ramping in z
            # TODO - For extra credit generate all waypoints first instead of
            # breaking them up into z ramp, transition leg, and z_end circuit

            # 2 degree ramp to (almost) z_end
            # except if one loop goes deeper than z doc, then adjust angle to match
            #print "--kw entry type 4"
            if corner_radius <= tool_radius:  # path set = four straight lines

                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (wp[0][0], wp[0][1]))

                code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 X %s Y %s Z %s' %
                            (dro_fmt, dro_fmt, dro_fmt) %
                            (wp[0][0], wp[0][1], wp[0][2]))
                code.append('\n(Rectangular Helix)')
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                for i in range(1, len(wp) - 1):
                    code.append('G1 X %s Y %s Z %s' % (dro_fmt, dro_fmt, dro_fmt) % (wp[i][0], wp[i][1], wp[i][2]))

                # transition leg to z_end
                i = i + 1
                code.append('\n(Transition Leg)')
                code.append('G1 X %s Y %s Z %s' % (dro_fmt, dro_fmt, dro_fmt) % (wp[i][0], wp[i][1], z_end))

                z_end_wp = []
                z_end_wp.append([x_start + tool_radius, y_start - tool_radius])
                z_end_wp.append([x_start + tool_radius, y_end   + tool_radius])
                z_end_wp.append([x_end   - tool_radius, y_end   + tool_radius])
                z_end_wp.append([x_end   - tool_radius, y_start - tool_radius])

                zewpc = divmod(i, 4)      # get circuit count and last cut leg, 1 circuit = 4 legs
                zewpstart = zewpc[1] + 1  # start from after the last cut leg
                zewpseq = range(4)        # set the leg sequence 0, 1, 2, 3
                zewpwrapped = zewpseq[zewpstart:] + zewpseq[:zewpstart]  # rearrange the sequence to start with start leg with wrap
                #print "--kw divmod =", zewpc, "  start =", zewpstart, "  seq =", zewpseq, "  wrapped =", zewpwrapped

                code.append('\n(Bottom)')
                for zewpi in zewpwrapped:
                    x_value = z_end_wp[zewpi][0]
                    y_value = z_end_wp[zewpi][1]
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_value, y_value))

            else:  # path set = four straight lines with corner arcs

                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (wp[0][0], wp[0][1]))

                code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 X %s Y %s Z %s' %
                            (dro_fmt, dro_fmt, dro_fmt) %
                            (wp[0][0], wp[0][1], wp[0][2]))
                code.append('\n(Rectangular Helix)')
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                for i in range(1, len(wp) - 1):
                    if i % 2:  # odd leg = corner arc
                        code.append('G1 X %s Y %s Z %s' %
                                    (dro_fmt, dro_fmt, dro_fmt) %
                                    (wp[i][0], wp[i][1], wp[i][2]))

                    else:           # even leg = straight leg

                        if   wp[i][0] > wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                            g3i = cornerpr
                            g3j = 0
                        elif wp[i][0] > wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                            g3i = 0
                            g3j = cornerpr
                        elif wp[i][0] < wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                            g3i = -cornerpr
                            g3j = 0
                        else:  # wp[i][0] < wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                            g3i = 0
                            g3j = -cornerpr

                        code.append('G3 X %s Y %s Z %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (wp[i][0], wp[i][1], wp[i][2], g3i, g3j))

                # transition leg to z_end
                i = i + 1
                if i % 2:  # odd leg = corner arc
                    code.append('\n(Transition Leg)')
                    code.append('G1 X %s Y %s Z %s' %
                                (dro_fmt, dro_fmt, dro_fmt) %
                                (wp[i][0], wp[i][1], z_end))

                else:      # even leg = straight leg

                    if   wp[i][0] > wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                        g3i = cornerpr
                        g3j = 0
                    elif wp[i][0] > wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                        g3i = 0
                        g3j = cornerpr
                    elif wp[i][0] < wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                        g3i = -cornerpr
                        g3j = 0
                    else:  # wp[i][0] < wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                        g3i = 0
                        g3j = -cornerpr

                    code.append('\n(Transition Leg)')
                    code.append('G3 X %s Y %s Z %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (wp[i][0], wp[i][1], z_end, g3i, g3j))

                # one circuit starting from last leg

                # the sequence of z_end waypoints for a circuit
                z_end_wp = []
                z_end_wp.append([x_start + tool_radius  , y_start - corner_radius])
                z_end_wp.append([x_start + tool_radius  , y_end   + corner_radius])
                z_end_wp.append([x_start + corner_radius, y_end   + tool_radius  ])
                z_end_wp.append([x_end   - corner_radius, y_end   + tool_radius  ])
                z_end_wp.append([x_end   - tool_radius  , y_end   + corner_radius])
                z_end_wp.append([x_end   - tool_radius  , y_start - corner_radius])
                z_end_wp.append([x_end   - corner_radius, y_start - tool_radius  ])
                z_end_wp.append([x_start + corner_radius, y_start - tool_radius  ])

                zewpc = divmod(i, 8)      # get circuit count and last cut leg, 1 circuit = 8 legs
                zewpstart = zewpc[1] + 1  # start from after the last cut leg
                zewpseq = range(8)        # set the leg sequence 0, 1, 2, 3, 4, 5, 6, 7
                zewpwrapped = zewpseq[zewpstart:] + zewpseq[:zewpstart]  # rearrange the sequence to start with start leg with wrap
                #print "--kw divmod =", zewpc, "  start =", zewpstart, "  seq =", zewpseq, "  wrapped =", zewpwrapped

                code.append('\n(Bottom)')

                for zewpi in zewpwrapped:
                    x_value = z_end_wp[zewpi][0]
                    y_value = z_end_wp[zewpi][1]

                    if zewpi % 2:  # odd leg = corner arc
                        code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_value, y_value))

                    else:          # even leg = straight leg
                        if   z_end_wp[zewpi][0] > z_end_wp[zewpi - 1][0] and z_end_wp[zewpi][1] < z_end_wp[zewpi - 1][1]:
                            g3i = cornerpr
                            g3j = 0
                        elif z_end_wp[zewpi][0] > z_end_wp[zewpi - 1][0] and z_end_wp[zewpi][1] > z_end_wp[zewpi - 1][1]:
                            g3i = 0
                            g3j = cornerpr
                        elif z_end_wp[zewpi][0] < z_end_wp[zewpi - 1][0] and z_end_wp[zewpi][1] > z_end_wp[zewpi - 1][1]:
                            g3i = -cornerpr
                            g3j = 0
                        else:  # z_end_wp[zewpi][0] < z_end_wp[zewpi - 1][0] and z_end_wp[zewpi][1] < z_end_wp[zewpi - 1][1]:
                            g3i = 0
                            g3j = -cornerpr

                        code.append('G3 X %s Y %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_value, y_value, g3i, g3j))

            code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

        elif entry_type == 5:  # just like type 4 but with simple z plunge entry right to z_end
            if corner_radius <= tool_radius:  # path set = four straight lines
                code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (wp[0][0], wp[0][1]))

                code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                code.append('G0 Z %s (Z Start)' % dro_fmt % z_start)

                code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s (Z End)' % dro_fmt % z_end)

                code.append('\n(Rectangular Slot)')
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                for i in range(1, len(wp)):
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (wp[i][0], wp[i][1]))

            else:  # corner_radius > tool_radius:  # path set = four straight lines with corner radius arcs
#               print "--kaw gen g-code from wp, perimeter only with corner radii, plunge entry"
                code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (wp[0][0], wp[0][1]))

                code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                code.append('G0 Z %s (Z Start)' % dro_fmt % z_start)

                code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s (Z End)' % dro_fmt % z_end)

                code.append('\n(Rectangular Slot with corner radii)')
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                for i in range(1, len(wp)):  # cycle through waypoints
                    if i % 2:  # odd leg = corner arc
                        code.append('G1 X %s Y %s Z %s' %
                                    (dro_fmt, dro_fmt, dro_fmt) %
                                    (wp[i][0], wp[i][1], z_end))

                    else:           # even leg = straight leg

                        if   wp[i][0] > wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                            g3i = cornerpr
                            g3j = 0
                        elif wp[i][0] > wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                            g3i = 0
                            g3j = cornerpr
                        elif wp[i][0] < wp[i - 1][0] and wp[i][1] > wp[i - 1][1]:
                            g3i = -cornerpr
                            g3j = 0
                        else:  # wp[i][0] < wp[i - 1][0] and wp[i][1] < wp[i - 1][1]:
                            g3i = 0
                            g3j = -cornerpr

                        code.append('G3 X %s Y %s Z %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (wp[i][0], wp[i][1], z_end, g3i, g3j))

            code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

        else:  # entry types other than type 4 or 5
            zdllen = len(z_doc_list)
            for zdoci in range(1, zdllen):  # repeat entry, pocket and perimeter cuts for each DoC
                z_doc_start = z_doc_list[zdoci - 1]
                z_doc_end   = z_doc_list[zdoci]
                z_doc_range = z_doc_start - z_doc_end
                #print "--kw z stuff =",zdoci , z_doc_range, z_doc_end, z_doc_start

                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # entry

                if entry_type == 1:  # helical entry
                    code.append('\n(Helical Entry, Z Pass %d)' % zdoci)
                    helix_length = z_doc_range / math.sin(math.radians(2.0))
                    helix_circumference = math.pi * tool_dia
                    num_turns, end_arc_lg = divmod(helix_length, helix_circumference)
                    end_arc_rdn = (end_arc_lg * math.pi * tool_dia) / helix_circumference
                    end_arc_dx = tool_radius * math.cos(end_arc_rdn)
                    end_arc_dy = tool_radius * math.sin(end_arc_rdn)

                    feed_adj = max(feed * .5 ,feed_min)

                    # go to helix start
                    x_pos = x_pocket_center
                    y_pos = y_pocket_center + tool_radius
                    code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                    code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                    code.append('G1 Z %s' % dro_fmt % z_doc_start)

                    # cut helix to z DoC end
                    x_pos = x_pocket_center + end_arc_dx
                    y_pos = y_pocket_center + end_arc_dy
                    z_pos = z_doc_end
                    center_os_x = 0
                    center_os_y = -tool_radius
                    code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                    if num_turns < 1:
                        code.append('G3 X %s Y %s Z %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_pos, y_pos, z_pos, center_os_x, center_os_y))
                    else:
                        code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_pos, y_pos, z_pos, num_turns, center_os_x, center_os_y))

                    # clean up bottom of hole
                    x_pos = x_pocket_center + end_arc_dx
                    y_pos = y_pocket_center + end_arc_dy
                    z_pos = z_doc_end
                    center_os_x = -end_arc_dx
                    center_os_y = -end_arc_dy
                    code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, z_pos, 1.0, center_os_x, center_os_y))

                    # retract to hole center then z clear
                    x_pos = x_pocket_center
                    y_pos = y_pocket_center
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))
                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                elif entry_type == 2:  # linear ramp
                    code.append('\n(Linear Ramp Entry, Z Pass %d)' % zdoci)
                    ramp_angle = math.radians(2.0)
                    ramp_dz = math.fabs(x_width - y_width) * math.tan(ramp_angle)  # delta Z from 2 degree path to far end
                    ramp_dcz = math.fabs(tool_dia) * math.tan(ramp_angle)  # Z retract to allow direction change
                    ramp_cycle_z = 2 * (ramp_dz - ramp_dcz)  # abs(+ Z dir ch - Z ramp + Z dir ch - Z ramp)
                    #print "--kw rz, rxdc, rcz", ramp_z, ramp_dcz, ramp_cycle_z

                    num_rz = int((z_doc_range / ramp_cycle_z) + 1)
                    ramp_cycle_z_adj = z_doc_range / num_rz
                    ramp_adj_factor = ramp_cycle_z_adj / ramp_cycle_z  # scale factor to adjust cycles to fit Z range evenly
                    ramp_z_adj = ramp_dz * ramp_adj_factor
                    ramp_dcz_adj = ramp_dcz * ramp_adj_factor
                    ramp_cycle_z_adj = ramp_cycle_z * ramp_adj_factor
                    #print "--kw numz, rcza, raf, rza, rdcza", num_rz, ramp_cycle_z_adj, ramp_adj_factor, ramp_z_adj, ramp_dcz_adj

                    ramp_z_list = [z_doc_start]
                    for rz_cnt in range(1, num_rz):
                        ramp_z_list.append(z_doc_start + (z_dir * rz_cnt * ramp_cycle_z_adj))
                    ramp_z_list.append(z_doc_end)
                    #print "--kw pocket rect ramp_z_list =", ramp_z_list

                    if major == 0:  # X
                        x_offset = major_center_offset
                        y_offset = 0.0
                    else:           # Y
                        x_offset = 0.0
                        y_offset = major_center_offset

                    if zdoci == 1:
                        x_pos = x_pocket_center + x_offset
                        y_pos = y_pocket_center + y_offset
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                        code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                        code.append('G1 Z %s' % dro_fmt % z_doc_start)


                    for i in range(len(ramp_z_list) - 1):
                        code.append('\n(Ramp Cycle %s)' % i)

                        x_pos = x_pocket_center + x_offset
                        y_pos = y_pocket_center + y_offset
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % ramp_z_list[i])

                        # one ramp cycle  =  + Z dir ch - Z ramp + Z dir ch - Z ramp
                        ramp_start_z = ramp_z_list[i]
                        ramp_leg_1_z = ramp_z_list[i] + ramp_dcz_adj
                        ramp_leg_2_z = ramp_leg_1_z - ramp_z_adj
                        ramp_leg_3_z = ramp_leg_2_z + ramp_dcz_adj
                        #ramp_leg_4_z = ramp_leg_3_z - ramp_z_adj
                        ramp_leg_4_z = ramp_z_list[i + 1]

                        code.append('G0 Z %s' % dro_fmt % ramp_leg_1_z)

                        x_pos = x_pocket_center - x_offset
                        y_pos = y_pocket_center - y_offset
                        z_pos = ramp_leg_2_z
                        code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                        code.append('G1 X %s Y %s Z %s' % (dro_fmt, dro_fmt, dro_fmt) % (x_pos, y_pos, z_pos))

                        code.append('G0 Z %s' % dro_fmt % ramp_leg_3_z)

                        x_pos = x_pocket_center + x_offset
                        y_pos = y_pocket_center + y_offset
                        z_pos = ramp_leg_4_z
                        code.append('G1 X %s Y %s Z %s' % (dro_fmt, dro_fmt, dro_fmt) % (x_pos, y_pos, z_pos))

                    x_pos = x_pocket_center - x_offset
                    y_pos = y_pocket_center - y_offset
                    z_pos = ramp_leg_4_z
                    code.append('G1 X %s Y %s Z %s' % (dro_fmt, dro_fmt, dro_fmt) % (x_pos, y_pos, z_pos))

                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                elif entry_type == 3:  # straight plunge
                    # assuming drilling method with peck depth at 25% of tool dia.
                    code.append('\n(Z Plunge Entry, Z Pass %d)' % zdoci)
                    peck_dz = .25 * tool_dia
                    num_pecks = int((z_doc_range / peck_dz) + .99)
                    if num_pecks == 0: num_pecks = 1
                    peck_dz_adj = z_doc_range / num_pecks
                    code.append('\n(Peck Length = %s)' % dro_fmt % peck_dz_adj)
                    peck_z_list = [z_doc_start]
                    for peck_cnt in range(1, num_pecks):
                        peck_z_list.append(z_doc_start - (peck_cnt * peck_dz_adj))
                    peck_z_list.append(z_doc_end)
                    #print "--kw pocket rect peck_z_list =", peck_z_list

                    x_value = x_pocket_center
                    y_value = y_pocket_center
                    code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_value, y_value))
                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                    code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)

                    for i in range(len(peck_z_list) - 1):
                        code.append('\n(Peck Cycle %s)' % i)
                        code.append('G0 Z %s' % dro_fmt % peck_z_list[i])
                        code.append('G1 Z %s' % dro_fmt % peck_z_list[i + 1])
                        code.append('G0 Z %s' % dro_fmt % peck_z_list[0])

                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                elif entry_type == 4:  # do only a cut around the perimeter
                    pass
                else: entry_type = 0   # no entry

                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # pocket - only for type 1 helical entry, others go right to perimeter cut

                if entry_type == 1:  # helical entry has been done
                    # square up or expand center hole to perimeter routine start,
                    # pocket width - (2 * stepover) or hole dia.
                    code.append('\n( *** Square up helical entry, Z Pass %d ***)' % zdoci)
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                    sqrup_range = (pocket_width / 2) - tool_dia  # distance between helix hole dia. and perimeter
                    if sqrup_range <= stepover:  # square up current entry dia, then call wings, and perimeter
                        step_adj = stepover  # fudge for wings
                        sq_step_adj = stepover  # fudge for wings
                        path_radius = corner_radius_true - tool_radius - sqrup_range

                        code.append('\n(~~~ Square Z Pass %d )' % zdoci)

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center + tool_radius
                        code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G1 Z %s' % dro_fmt % z_doc_list[zdoci])

                        if path_radius > 0:  # include corner radius
                            # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                            feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                            x_pos = x_pocket_center
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center - tool_radius + path_radius
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center - tool_radius
                            y_pos = y_pocket_center + tool_radius - path_radius
                            x_radius_os = 0
                            y_radius_os = -path_radius
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G3 X %s Y %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, x_radius_os, y_radius_os))

                            x_pos = x_pocket_center - tool_radius
                            y_pos = y_pocket_center - tool_radius + path_radius
                            code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center - tool_radius + path_radius
                            y_pos = y_pocket_center - tool_radius
                            x_radius_os = path_radius
                            y_radius_os = 0
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G3 X %s Y %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, x_radius_os, y_radius_os))

                            x_pos = x_pocket_center + tool_radius - path_radius
                            y_pos = y_pocket_center - tool_radius
                            code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center + tool_radius
                            y_pos = y_pocket_center - tool_radius + path_radius
                            x_radius_os = 0
                            y_radius_os = path_radius
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G3 X %s Y %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, x_radius_os, y_radius_os))

                            x_pos = x_pocket_center + tool_radius
                            y_pos = y_pocket_center + tool_radius - path_radius
                            code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center + tool_radius - path_radius
                            y_pos = y_pocket_center + tool_radius
                            x_radius_os = -path_radius
                            y_radius_os = 0
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G3 X %s Y %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, x_radius_os, y_radius_os))

                            x_pos = x_pocket_center
                            y_pos = y_pocket_center + tool_radius
                            code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        else:  # do square corners
                            x_pos = x_pocket_center
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s (1)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center - tool_radius
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s (2)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center - tool_radius
                            y_pos = y_pocket_center - tool_radius
                            code.append('G1 X %s Y %s (3)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center + tool_radius
                            y_pos = y_pocket_center - tool_radius
                            code.append('G1 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center + tool_radius
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s (5)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            x_pos = x_pocket_center
                            y_pos = y_pocket_center + tool_radius
                            code.append('G1 X %s Y %s (6)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                    else:  # at least one stepover to do
                        num_hole_p = int((sqrup_range / stepover) + .99)
                        sq_step_adj = (sqrup_range / num_hole_p)
                        step_adj = sq_step_adj
                        #print "--kw sqr sq step_adj =", sq_step_adj

                        center_os_list = [tool_radius]  # first offset from pocket center
                        for cos_cnt in range(1, num_hole_p):
                            center_os_list.append(tool_radius + (cos_cnt * sq_step_adj))
                        center_os_list.append((pocket_width / 2) - tool_radius - sq_step_adj)
                        #print "--kw pocket rect hole_cos_list =", center_os_list

                        code.append('\n(~~~ Square Z Pass %d, with step )' % zdoci)

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center + center_os_list[0]
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                        for hi in range((len(center_os_list) - 1)):
                            code.append('\n(Square %d)' % hi)

                            cr_os_w = (pocket_width / 2) - corner_radius_true
                            path_radius = center_os_list[hi] - cr_os_w

                            if path_radius <= 0:  # do square corners until full radius can fit
                                x_pos = x_pocket_center
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s (1)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - center_os_list[hi]
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s (2)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - center_os_list[hi]
                                y_pos = y_pocket_center - center_os_list[hi]
                                code.append('G1 X %s Y %s (3)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + center_os_list[hi]
                                y_pos = y_pocket_center - center_os_list[hi]
                                code.append('G1 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + center_os_list[hi]
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s (5)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s (6)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            else:  # start using corner radius
                                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                                feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                                x_pos = x_pocket_center
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - center_os_list[hi] + path_radius
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - center_os_list[hi]
                                y_pos = y_pocket_center + center_os_list[hi] - path_radius
                                x_radius_os = 0
                                y_radius_os = -path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center - center_os_list[hi]
                                y_pos = y_pocket_center - center_os_list[hi] + path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - center_os_list[hi] + path_radius
                                y_pos = y_pocket_center - center_os_list[hi]
                                x_radius_os = path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + center_os_list[hi] - path_radius
                                y_pos = y_pocket_center - center_os_list[hi]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + center_os_list[hi]
                                y_pos = y_pocket_center - center_os_list[hi] + path_radius
                                x_radius_os = 0
                                y_radius_os = path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + center_os_list[hi]
                                y_pos = y_pocket_center + center_os_list[hi] - path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + center_os_list[hi] - path_radius
                                y_pos = y_pocket_center + center_os_list[hi]
                                x_radius_os = -path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center
                                y_pos = y_pocket_center + center_os_list[hi]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                    # wings
                    start3 = (pocket_width / 2) - tool_radius - step_adj

                    w_start = (pocket_width / 2)  - tool_radius - step_adj  # offset from pocket center to tool center on pocket width
                    w_end   = (pocket_length / 2) - tool_radius - step_adj

                    w_range    = (pocket_length - pocket_width) / 2
                    w_num_step = int((w_range / sq_step_adj) + .99)
                    if w_num_step == 0:
                        w_num_step = 1
                    w_step_adj = w_range / w_num_step
                    w_center_os_list = [w_start]
                    for wi in range(1, w_num_step):
                        w_center_os_list.append(w_start + (w_step_adj * wi))
                    w_center_os_list.append(w_end)
                    #print "--kw pocket rect w_center_os_list =", w_center_os_list

                    if major == 0:  # major = X
                        #print "--kw crnr_rad_os"
                        code.append('\n( *** Wings, major = X ***)')
                        # wing 1
                        code.append('(~~~ Wing 1)')

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center + w_center_os_list[0]
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                        for i3 in range(1, len(w_center_os_list)):
                            #print "--kw i3 =", i3, "  lg =", len(w_center_os_list), "  val =", w_center_os_list[i3]

                            cr_os_w = (pocket_width / 2) - corner_radius_true
                            path_radius = w_start - cr_os_w
                            #print "--kw wing 1 x path rad =", path_radius, " =", w_center_os_list[i3], " -", cr_os_w

                            if path_radius <= 0:  # do square corners until radius can fit

                                code.append('\n(Wing 1 Pass %d)' % i3)
                                x_pos = x_pocket_center - w_center_os_list[i3 - 1]
                                y_pos = y_pocket_center + start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s (1)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3]
                                y_pos = y_pocket_center + start3
                                code.append('G1 X %s Y %s (2)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3]
                                y_pos = y_pocket_center - start3
                                code.append('G1 X %s Y %s (3)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3 - 1]
                                y_pos = y_pocket_center - start3
                                code.append('G1 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center - w_center_os_list[i3]
                                    y_pos = y_pocket_center + start3
                                    code.append('\nG0 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            else:
                                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                                feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                                code.append('\n(Wing 1 Pass %d)' % i3)
                                x_pos = x_pocket_center - w_center_os_list[i3 - 1] + path_radius
                                y_pos = y_pocket_center + start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3] + path_radius
                                y_pos = y_pocket_center + start3
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3]
                                y_pos = y_pocket_center + start3 - path_radius
                                x_radius_os = 0
                                y_radius_os = -path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center - w_center_os_list[i3]
                                y_pos = y_pocket_center - start3 + path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - w_center_os_list[i3] + path_radius
                                y_pos = y_pocket_center - start3
                                x_radius_os = path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center - w_center_os_list[i3 - 1] + path_radius
                                y_pos = y_pocket_center - start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center - w_center_os_list[i3] + path_radius
                                    y_pos = y_pocket_center + start3
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        # wing 2
                        code.append('\n( *** Wing 2 Z Pass %d *** major = X)' % zdoci)

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center - w_center_os_list[0]
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                        for i3 in range(1, len(w_center_os_list)):
                            cr_os_w = (pocket_width / 2) - corner_radius_true
                            path_radius = w_start - cr_os_w

                            if path_radius <= 0:  # do square corners until radius can fit

                                code.append('\n(Wing 2 Pass %d)' % i3)
                                x_pos = x_pocket_center + w_center_os_list[i3 - 1]
                                y_pos = y_pocket_center - start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s (1)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3]
                                y_pos = y_pocket_center - start3
                                code.append('G1 X %s Y %s (2)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3]
                                y_pos = y_pocket_center + start3
                                code.append('G1 X %s Y %s (3)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3 - 1]
                                y_pos = y_pocket_center + start3
                                code.append('G1 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center + w_center_os_list[i3]
                                    y_pos = y_pocket_center - start3
                                    code.append('\nG0 X %s Y %s (4)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            else:
                                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                                feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                                code.append('\n(Wing 2 Pass %d)' % i3)
                                x_pos = x_pocket_center + w_center_os_list[i3 - 1] - path_radius
                                y_pos = y_pocket_center - start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3] - path_radius
                                y_pos = y_pocket_center - start3
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3]
                                y_pos = y_pocket_center - start3 + path_radius
                                x_radius_os = 0
                                y_radius_os = path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + w_center_os_list[i3]
                                y_pos = y_pocket_center + start3 - path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + w_center_os_list[i3] - path_radius
                                y_pos = y_pocket_center + start3
                                x_radius_os = -path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + w_center_os_list[i3 - 1] - path_radius
                                y_pos = y_pocket_center + start3
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center + w_center_os_list[i3] - path_radius
                                    y_pos = y_pocket_center - start3
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    else:  # major = Y
                        # wing 1
                        code.append('\n( *** Wing 1, major = Y ***)')

                        x_pos = x_pocket_center + w_center_os_list[0]
                        y_pos = y_pocket_center
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                        for i3 in range(1, len(w_center_os_list)):
                            code.append('\n( ~~~ Wing 1)')

                            cr_os_w = (pocket_width / 2) - corner_radius_true
                            path_radius = w_start - cr_os_w

                            if path_radius <= 0:  # do square corners until radius can fit
                                code.append('\n(Wing 1 Pass %d)' % i3)
                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center + w_center_os_list[i3 - 1]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center + w_center_os_list[i3]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center + w_center_os_list[i3]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center + w_center_os_list[i3 - 1]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center + start3
                                    y_pos = y_pocket_center + w_center_os_list[i3]
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            else:
                                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                                feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                                code.append('\n(Wing 1 Pass %d)' % i3)
                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center + w_center_os_list[i3 - 1] - path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center + w_center_os_list[i3] - path_radius
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3 - path_radius
                                y_pos = y_pocket_center + w_center_os_list[i3]
                                x_radius_os = -path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center - start3 + path_radius
                                y_pos = y_pocket_center + w_center_os_list[i3]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center + w_center_os_list[i3] - path_radius
                                x_radius_os = 0
                                y_radius_os = -path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center + w_center_os_list[i3 - 1] - path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center + start3
                                    y_pos = y_pocket_center + w_center_os_list[i3] - path_radius
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        # wing 2
                        code.append('\n( *** Wing 2 Z Pass %d *** major = Y)' % zdoci)

                        x_pos = x_pocket_center - w_center_os_list[0]
                        y_pos = y_pocket_center
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                        for i3 in range(1, len(w_center_os_list)):
                            code.append('\n( ~~~ Wing 2, Wing Pass %d)' % i3)
                            cr_os_w = (pocket_width / 2) - corner_radius_true
                            path_radius = w_start - cr_os_w

                            if path_radius <= 0:  # do square corners until radius can fit
                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center - w_center_os_list[i3 - 1]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center - w_center_os_list[i3]
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center - w_center_os_list[i3]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center - w_center_os_list[i3 - 1]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center - start3
                                    y_pos = y_pocket_center - w_center_os_list[i3]
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            else:
                                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                                feed_adj = max(feed * path_radius / (path_radius + tool_radius) ,feed_min)

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center - w_center_os_list[i3 - 1] + path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3
                                y_pos = y_pocket_center - w_center_os_list[i3] + path_radius
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center - start3 + path_radius
                                y_pos = y_pocket_center - w_center_os_list[i3]
                                x_radius_os = path_radius
                                y_radius_os = 0
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + start3 - path_radius
                                y_pos = y_pocket_center - w_center_os_list[i3]
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center - w_center_os_list[i3] + path_radius
                                x_radius_os = 0
                                y_radius_os = path_radius
                                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                                code.append('G3 X %s Y %s I %s J %s' %
                                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                            (x_pos, y_pos, x_radius_os, y_radius_os))

                                x_pos = x_pocket_center + start3
                                y_pos = y_pocket_center - w_center_os_list[i3 - 1] + path_radius
                                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                                code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                                if i3 < (len(w_center_os_list) - 1):
                                    x_pos = x_pocket_center - start3
                                    y_pos = y_pocket_center - w_center_os_list[i3] + path_radius
                                    code.append('\nG0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                # perimeter, for types other than type 4
                code.append('\n(Perimeter Cut, Z Pass %d)' % zdoci)
                path_radius      = corner_radius_true - tool_radius
                path_radius_str  = '%s' % dro_fmt % path_radius
                path_radius_fmtd = float(path_radius_str)
                #print "--kw pocket, path radius =", path_radius, " pr_str =", path_radius_str, " pr_fmtd =", path_radius_fmtd,"   corner =", corner_radius_true, "   tool =", tool_radius
                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                feed_adj = max(feed * path_radius / corner_radius_true ,feed_min)

                cp_x_start = x_start + tool_radius
                cp_x_end   = x_end   - tool_radius
                cp_y_start = y_start - tool_radius
                cp_y_end   = y_end   + tool_radius

                if path_radius_fmtd > 0:
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                    x_pos = x_pocket_center
                    y_pos = y_pocket_center
                    code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))
                    code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                    code.append('G1 Z %s' % dro_fmt % z_doc_list[zdoci])
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                    # ramp out to perimeter start
                    x_pos = cp_x_start + path_radius
                    y_pos = cp_y_start
                    code.append('\nG1 X %s Y %s (to perimeter start)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    # cut perimeter
                    x_pos = cp_x_start
                    y_pos = cp_y_start - path_radius
                    x_radius_os = 0
                    y_radius_os = -path_radius
                    code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                    code.append('G3 X %s Y %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, x_radius_os, y_radius_os))

                    x_pos = cp_x_start
                    y_pos = cp_y_end + path_radius
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_start + path_radius
                    y_pos = cp_y_end
                    x_radius_os = path_radius
                    y_radius_os = 0
                    code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                    code.append('G3 X %s Y %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, x_radius_os, y_radius_os))

                    x_pos = cp_x_end - path_radius
                    y_pos = cp_y_end
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_end
                    y_pos = cp_y_end + path_radius
                    x_radius_os = 0
                    y_radius_os = path_radius
                    code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                    code.append('G3 X %s Y %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, x_radius_os, y_radius_os))

                    x_pos = cp_x_end
                    y_pos = cp_y_start - path_radius
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_end - path_radius
                    y_pos = cp_y_start
                    x_radius_os = -path_radius
                    y_radius_os = 0
                    code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                    code.append('G3 X %s Y %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, x_radius_os, y_radius_os))

                    x_pos = cp_x_start + path_radius
                    y_pos = cp_y_start
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    # lead-out
                    lo_adj = stepover2 * 0.02
                    x_pos = cp_x_start + lo_adj
                    y_pos = cp_y_start - path_radius + lo_adj
                    x_radius_os = 0
                    y_radius_os = -path_radius + lo_adj
                    code.append('\n(Lead-out)')
                    code.append('F %s (Arc Feed Rate, %s)' % (feed_fmt, rate_units) % feed_adj)
                    code.append('G3 X %s Y %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, x_radius_os, y_radius_os))

                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                else:
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                    x_pos = x_pocket_center
                    y_pos = y_pocket_center
                    code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    code.append('G0 Z %s' % dro_fmt % z_doc_list[zdoci])

                    # ramp out to perimeter start
                    x_pos = cp_x_start
                    y_pos = cp_y_start
                    code.append('\nG1 X %s Y %s (to perimeter start)' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_start
                    y_pos = cp_y_end
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_end
                    y_pos = cp_y_end
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_end
                    y_pos = cp_y_start - path_radius
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    x_pos = cp_x_start + path_radius
                    y_pos = cp_y_start
                    code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                    code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                    code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                # go back for next z DoC

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, pocket_op_string)

        return ok, code

    # ------------------------------------------------------------------------------------
    # Pocket - Circular
    # ------------------------------------------------------------------------------------

    def ja_parse_pocket_circ_centers(self, routine_data):
#       print "--- kaw - ja_parse_pc_centers - routine data =", routine_data
        centers_list = []
        try:
            text = routine_data['segment text']
            is_metric = routine_data['segment data']['Units']['orig'] == 'mm'
            format_spec = '%.3f' if is_metric else '%.4f'
            segment_lines = text.split('\n')
            parsing = False
            line_number = 1
            for line in segment_lines:
                if parsing:
                    xy = re.findall(r'\s?\-?\d*\.\d+', line)
                    if not any(xy):
                        break
                    if 'X' in line and 'Y' in line:
                        centers_list.append((str(line_number),
                                             (format_spec % float(xy[0])),
                                             (format_spec % float(xy[1]))))
                        line_number += 1
                    else:
                        break
                elif '(Pocket Centers' in line:
                    parsing = True

            for n in range(line_number,self.ui.DRILL_LIST_BASIC_SIZE + 1):
                centers_list.append((str(n),'',''))

            ref = routine_data['segment data']['Post Parse']['ref']
            routine_data['segment data'][ref]['orig'] = centers_list
            routine_data['segment data'][ref]['mod'] = copy.deepcopy(centers_list)

        except:
            print 'Exception ocurred in ja_parse_pocket_circ_centers'
            pass
        return


    def ja_edit_pocket_circ(self, routine_data):
#       print "--- kaw - ja_edit_pc - routine data =", routine_data
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            rect_circ = 'rect' if self.ui.conv_pocket_rect_circ == 'rect' else 'circ',
            disable_button = [self.ui.button_list['pocket_rect_circ']],
            drill_tap_button_state = self.ui.button_list['drill_tap'].get_visible(),
            drill_tap = 'drill' if self.ui.conv_drill_tap == 'tap' else 'tap',
            patt_circ = self.ui.drill_pattern_notebook_page,
            restore_proc = getattr(self, 'ja_restore_edit_pocket_circ_page')
        )

        #title = routine_data['segment data']['title']['ref']
        #print "--- kaw - ja_edit_pc- title =", title
        #self.ui.conv_pocket_rect_circ = 'circ' if 'Circular' in title else 'rect'
        #print "--- kaw - ja_edit_pc - rect_circ =", self.ui.conv_pocket_rect_circ
        #if restore_data['drill_tap_button_state']: restore_data['disable_button'].append(self.ui.button_list['drill_tap'])

        self.ui.conv_pocket_rect_circ = 'rect'

        self.ui.on_pocket_rect_circ_set_state()
        conversational.ja_toggle_buttons(restore_data['disable_button'])

        # deal with the drill stuff
        self.ui.drill_pattern_notebook_page = 'pattern'
        self.ui.conv_drill_tap_pattern_notebook.set_current_page(0)
        self.ui.show_hide_dros(False)

        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_edit_pocket_circ_page(self, restore_data):
        print "--- kaw - ja_restore_pc_page - restore_data =", restore_data
        self.ui.conv_pocket_rect_circ = 'circ' if restore_data['rect_circ'] == 'circ' else 'rect'
        conversational.ja_toggle_buttons(restore_data['disable_button'],'on')
        self.ui.on_pocket_rect_circ_set_state()
        self.ui.show_hide_dros()
        self.ja_restore_edit_drill_page(restore_data)




    def gen_pocket_circ_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.pocket_circ_dro_list
        dro_to_text_data = { # specific DROs
                             'Stepover'               : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_circ_stepover_dro'], 'orig' : None , 'mod' : None }),
                             'Z Start Location'       : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_circ_z_start_dro'],  'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':pdl['pocket_circ_z_end_dro'],    'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'         : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_circ_z_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Pocket Diameter'        : ({ 'proc': 'unpack_fp', 'ref':pdl['pocket_circ_diameter_dro'], 'orig' : None , 'mod' : None }),
                             'Pocket Centers'         : ({ 'proc': None,        'ref':'drill_liststore',                   'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_pocket_circ_centers, 'ref':'Pocket Centers','orig' : None , 'mod' : None, 'ja_diff' : 'no' }),
                             'revert'                 : ({ 'attr': 'conv_pocket_rect_circ', 'ref':'circ',              'orig' : None,  'ja_diff' : 'no' },),
                             'focus'                  : ({ 'proc': None,        'ref':pdl['pocket_circ_diameter_dro'], 'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Circular Pocket')

    def generate_pocket_circ_gcode(self, conv_dro_list, pocket_circ_dro_list, drill_liststore):

        # empty python list for g code
        code = []

        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error = self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed, error = self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_feed, error = self.validate_param(conv_dro_list['conv_z_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        # Pocket Circular specific DROs

        valid, z_start, error =  self.validate_param(pocket_circ_dro_list['pocket_circ_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error =  self.validate_param(pocket_circ_dro_list['pocket_circ_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, raw_z_doc, error =  self.validate_param(pocket_circ_dro_list['pocket_circ_z_doc_dro'])
        z_doc = math.fabs(raw_z_doc)
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, stepover, error =  self.validate_param(pocket_circ_dro_list['pocket_circ_stepover_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        valid, pocket_dia, error =  self.validate_param(pocket_circ_dro_list['pocket_circ_diameter_dro'])
        if not valid:
            self.error_handler.write('Conversational Pocket entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        feed_min = 2.54 if is_metric else 0.1
        angle_fmt  = '%3.1f'
        # get tool information from linuxcnc.stat
        tool_dia = self.status.tool_table[tool_number].diameter * ttable_conv
        if tool_dia <= 0:
            error_msg = "Conversational Pocket entry error - tool diameter needs to be greater than 0"
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            ok = False
            return ok, ' '

        tool_radius = tool_dia / 2

        # get X and Y locations from drill table
        id_cnt = 0
        for row in drill_liststore:
            if row[0] == '':
                break
            if row[1] == '':
                break
            id_cnt += 1

        x_loc_list = []
        y_loc_list = []
        x_retract_loc_list = []
        y_retract_loc_list = []
        for i in range(id_cnt):
            drill_iter = drill_liststore.get_iter(i,)
            x_value = float(drill_liststore.get_value(drill_iter, 1))
            y_value = float(drill_liststore.get_value(drill_iter, 2))
            x_loc_list.append(x_value)
            y_loc_list.append(y_value)
            x_retract_loc_list.append(x_value)
            y_retract_loc_list.append(y_value)

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Pocket error - Z Start must be larger than Z End'
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Pocket error - Z range too small or bad Z entry value'
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = "Conversational Pocket error - Z Start must be smaller than Z Clear"
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(z_end - z_start)

        if z_doc > z_range + conversational.float_err:
            ok = False
            error_msg = "Conversational Pocket error - Z Depth of Cut cannot be bigger than the Z range of cut"
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_start_dro'], error_msg)
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_end_dro'], error_msg)
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_z_doc_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_end_only = False
        if z_doc == 0 or z_doc >= z_range - conversational.float_err:
            num_z_passes = 1
            z_end_only = True
        else:
            num_z_passes = int((z_range / z_doc) + .99)
            if num_z_passes == 0:
                num_z_passes = 1
        z_doc_adj = z_range / num_z_passes
        z_doc_list = [z_start]
        for z_cnt in range(1, num_z_passes):
            z_doc_list.append(z_start + (z_dir * z_cnt * z_doc_adj))
        z_doc_list.append(z_end)
        #print "--kw pocket rect z_doc_list =", z_doc_list

        # is the pocket wide enough to fit the tool?
        if pocket_dia < tool_dia :  # No - oops, we can't go any further
            ok = False
            entry_type = 0  # bad entry
            error_msg = "Conversational Pocket error - tool diameter too big or pocket diameter too small"
            cparse.raise_alarm(pocket_circ_dro_list['pocket_circ_diameter_dro'], error_msg)
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif pocket_dia > 2 * tool_dia:
            entry_type = 1  # helical
        else:
            entry_type = 3  # straight Z plunge, then call perimeter

        if stepover == 0:
            if z_end_only is True:
                entry_type = 5  # perimeter slot only, simple z plunge entry
            else:
                entry_type = 4

        #print "--kw entry type =", entry_type

        pocket_radius = pocket_dia / 2
        path_dia = pocket_dia - tool_dia
        path_radius = path_dia / 2
        degrees_per_segment = 5.0
        delta_radius = (stepover * degrees_per_segment) / 360

        twodeginrad = math.radians(2.0)
        if entry_type == 4:  # Helical cut around the perimeter down to z end, then we're done
            loop_len = math.pi * path_dia  # circumference of tool path
            loop_dz = z_doc  # unless this goes over 2 degrees
            z_angle_rad = math.atan(z_doc / loop_len)
            if z_angle_rad > twodeginrad:
                z_angle_rad = twodeginrad
                loop_dz = loop_len * math.tan(twodeginrad)
                z_doc_adj = loop_dz

            num_turns, end_dz = divmod(z_range, loop_dz)
            if end_dz > 0:
                num_turns += 1  # G3's P needs +1, full turns + 1 for end arc
            end_arc_lg = end_dz / math.tan(z_angle_rad)
            end_arc_rad = 2 * math.pi * (end_dz / z_doc_adj)
            end_arc_dx = path_radius * math.cos(end_arc_rad)
            end_arc_dy = path_radius * math.sin(end_arc_rad)
            num_z_passes = num_turns
        # generation details
        pocket_op_string = 'Circular Pocket'
        self.__write_std_info(code, pocket_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('\n(Pocket Centers)')
        for i in range(id_cnt):
            code.append('(    %d  X = %s   Y = %s)' %
                        (i + 1, dro_fmt, dro_fmt) %
                        (x_loc_list[i], y_loc_list[i]))

        code.append('\n(Pocket Diameter = %s)' % dro_fmt % pocket_dia)
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed)
        code.append('(Stepover = %s)' % dro_fmt % stepover)

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s , End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))
        code.append('(Z Depth of Cut = %s , Adjusted = %s)' % (dro_fmt, dro_fmt) % (raw_z_doc, z_doc_adj))
        if entry_type == 4:
            code.append('(Helix Angle = %s degrees)' % angle_fmt % math.degrees(z_angle_rad))
        code.append('(Number of Z Passes = %d)' % num_z_passes)
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % z_feed)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        code.append('\nG30 (Go to preset G30 location)')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nF %s (Feed Rate, %s)' % (feed_fmt, rate_units) % feed)
        code.append('S %d (RPM)' % rpm)
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        for i in range(id_cnt):
            code.append('\n(*** Pocket %d ***)' % (i + 1))
            x_pocket_center = x_loc_list[i]
            y_pocket_center = y_loc_list[i]

            if entry_type == 4:  # Helical cut around the perimeter down to z end, then we're done

                code.append('\n(Perimeter Only, Helix in Z)')

                # feed
                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                feed_adj = max(feed * path_radius / pocket_radius, feed_min)

                # go to start xy, 0 rad or degrees
                x_pos = x_pocket_center + path_radius
                y_pos = y_pocket_center
                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                # go to z clear
                code.append('G0 Z %s' % dro_fmt % z_clear)

                # feed to z start
                code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s' % dro_fmt % z_start)

                # helix to z end
                x_pos = x_pocket_center + end_arc_dx
                y_pos = y_pocket_center + end_arc_dy
                z_pos = z_end
                center_os_x = -path_radius
                center_os_y = 0
                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                if num_turns < 1:
                    code.append('G3 X %s Y %s Z %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, z_pos, center_os_x, center_os_y))
                else:
                    code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                                (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                (x_pos, y_pos, z_pos, num_turns, center_os_x, center_os_y))

                # orbit once
                x_pos = x_pocket_center + end_arc_dx
                y_pos = y_pocket_center + end_arc_dy
                z_pos = z_end
                center_os_x = -end_arc_dx
                center_os_y = -end_arc_dy
                code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            (x_pos, y_pos, z_pos, 1.0, center_os_x, center_os_y))

                # ciao
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

            elif entry_type == 5:  # just like type 4 but with simple z plunge entry right to z_end
                code.append('\n(Perimeter Only, Plunge in Z entry)')

                # feed
                # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                feed_adj = max(feed * path_radius / pocket_radius, feed_min)

                # go to start xy, 0 rad or degrees
                x_pos = x_pocket_center + path_radius
                y_pos = y_pocket_center
                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                code.append('\nG0 Z %s (Z Clear)' % dro_fmt % z_clear)
                code.append('G0 Z %s (Z Start)' % dro_fmt % z_start)

                code.append('\nF %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s (Z End)' % dro_fmt % z_end)

                # orbit once
                x_pos = x_pocket_center + path_radius
                y_pos = y_pocket_center
                center_os_x = -path_radius
                center_os_y = 0
                code.append('\nF %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                code.append('G3 X %s Y %s P %s I %s J %s' %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            (x_pos, y_pos, 1.0, center_os_x, center_os_y))

            else:  # entry types other than type 4 or 5
                zdllen = len(z_doc_list)
                for zdoci in range(1, zdllen):  # repeat entry, pocket and perimeter cuts for each DoC
                    z_doc_start = z_doc_list[zdoci - 1]
                    z_doc_end   = z_doc_list[zdoci]
                    z_doc_range = z_doc_start - z_doc_end
                    #print "--kw z stuff =",zdoci , z_doc_range, z_doc_end, z_doc_start

                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # entry

                    if entry_type == 1:  # 2 degree helix to each z DoC at minimum radius ( = tool_radius)
                        code.append('\n(Helical Entry, Z Pass %d)' % zdoci)
                        helix_length = z_doc_range / math.sin(math.radians(2.0))  # 2 degree ramp angle
                        helix_circumference = math.pi * tool_dia  # circumference of path for one revolution
                        num_turns, end_arc_lg = divmod(helix_length, helix_circumference)
                        end_arc_rad = (end_arc_lg * math.pi * tool_dia) / helix_circumference
                        end_arc_dx = tool_radius * math.cos(end_arc_rad)
                        end_arc_dy = tool_radius * math.sin(end_arc_rad)

                        # 0 feed does not play well, feed DRO format rounds to .xx, so .004 = 0
                        feed_adj = max(feed * .5, feed_min)

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center + tool_radius
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s' % dro_fmt % z_clear)

                        # rapid to z start
                        code.append('G0 Z %s' % dro_fmt % z_doc_start)

                        x_pos = x_pocket_center + end_arc_dx
                        y_pos = y_pocket_center + end_arc_dy
                        z_pos = z_doc_end
                        center_os_x = 0
                        center_os_y = -tool_radius
                        code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                        if num_turns < 1:
                            code.append('G3 X %s Y %s Z %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, z_pos, center_os_x, center_os_y))
                        else:
                            code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                        (x_pos, y_pos, z_pos, num_turns, center_os_x, center_os_y))
                        x_pos = x_pocket_center + end_arc_dx
                        y_pos = y_pocket_center + end_arc_dy
                        z_pos = z_doc_end
                        center_os_x = -end_arc_dx
                        center_os_y = -end_arc_dy
                        code.append('G3 X %s Y %s Z %s P %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_pos, y_pos, z_pos, 1.0, center_os_x, center_os_y))

                        x_pos = x_pocket_center
                        y_pos = y_pocket_center
                        code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                        code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

                    elif entry_type == 3:  # straight Z plunge, then call perimeter
                        # assuming drilling method with peck depth at 25% of tool dia.
                        code.append('\n(Z Plunge Entry)')
                        peck_dz = .25 * tool_dia
                        num_pecks = int((z_range / peck_dz) + .99)
                        if num_pecks == 0: num_pecks = 1
                        peck_dz_adj = z_doc_range / num_pecks
                        code.append('\n(Peck Length = %s)' % dro_fmt % peck_dz_adj)
                        peck_z_list = [z_doc_start]
                        for peck_cnt in range(1, num_pecks):
                            peck_z_list.append(z_doc_start - (peck_cnt * peck_dz_adj))
                        peck_z_list.append(z_doc_end)
                        #print "--kw pocket rect peck_z_list =", peck_z_list

                        x_value = x_pocket_center
                        y_value = y_pocket_center
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_value, y_value))
                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                        code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)

                        for i in range(len(peck_z_list) - 1):
                            code.append('\n(Peck Cycle %s)' % i)
                            code.append('G0 Z %s' % dro_fmt % peck_z_list[i])
                            code.append('G1 Z %s' % dro_fmt % peck_z_list[i + 1])
                            code.append('G0 Z %s' % dro_fmt % peck_z_list[0])

                        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
                        code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

                    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
                    # pocket - spiral out from entry area to perimeter

                    if entry_type == 1:  # spiral from helical entry to perimeter
                        number_of_segments = int((path_radius - tool_radius) / delta_radius)

                        code.append('\n(Spiral, Z Pass %d)' % zdoci)

                        x_value = x_pocket_center
                        y_value = y_pocket_center
                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_value, y_value))
                        code.append('G0 Z %s' % dro_fmt % z_clear)

                        code.append('G0 Z %s' % dro_fmt % z_doc_end)

                        code.append('\n(Spiral)')
                        segment_count = 0
                        while segment_count <= number_of_segments:
                            # infinite loop guard
                            if len(code) > CONVERSATIONAL_MAX_LINES:
                                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                            radius = (segment_count * delta_radius) + tool_radius
                            angle = math.radians(segment_count * degrees_per_segment)
                            #print "--kw radius =", radius, angle, segment_count
                            x_pos = x_pocket_center + (radius * math.cos(angle))
                            y_pos = y_pocket_center + (radius * math.sin(angle))
                            # while cutting an arc, the feed rate at the cut is higher than at the tool center
                            feed_adj = max((feed * radius) / (tool_radius + radius), feed_min)
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            segment_count += 1

                        radius = path_radius
                        angle = math.radians(segment_count * degrees_per_segment)
                        x_pos = x_pocket_center + (radius * math.cos(angle))
                        y_pos = y_pocket_center + (radius * math.sin(angle))
                        code.append('\nG1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        x_radius = -radius * math.cos(angle)
                        y_radius = -radius * math.sin(angle)
                        # reuse arc feed rate from the last move
                        code.append('\n(Bottom)')
                        code.append('G3 X %s Y %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_pos, y_pos, x_radius, y_radius))

                        code.append('\nG0 Z %s' % dro_fmt % z_clear)

                    elif entry_type == 3:  # spiral out from the plunged hole to the perimeter
                        number_of_segments = int(path_radius / delta_radius)

                        code.append('\n(Spiral, Z Pass %d)' % zdoci)

                        code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pocket_center, y_pocket_center))
                        code.append('G0 Z %s' % dro_fmt % z_clear)

                        code.append('G0 Z %s' % dro_fmt % z_doc_end)

                        code.append('\n(Spiral)')
                        segment_count = 0
                        while segment_count <= number_of_segments:
                            # infinite loop guard
                            if len(code) > CONVERSATIONAL_MAX_LINES:
                                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                            radius = segment_count * delta_radius
                            angle = math.radians(segment_count * degrees_per_segment)
                            x_pos = x_pocket_center + (radius * math.cos(angle))
                            y_pos = y_pocket_center + (radius * math.sin(angle))
                            # while cutting an arc, the feed rate at the cut is higher than at the tool center
                            feed_adj = max((feed * radius) / (tool_radius + radius), feed_min)
                            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_adj)
                            code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                            segment_count += 1

                        radius = path_radius
                        angle = math.radians(segment_count * degrees_per_segment)
                        x_pos = x_pocket_center + (radius * math.cos(angle))
                        y_pos = y_pocket_center + (radius * math.sin(angle))
                        code.append('G1 X %s Y %s' % (dro_fmt, dro_fmt) % (x_pos, y_pos))

                        x_radius = -radius * math.cos(angle)
                        y_radius = -radius * math.sin(angle)
                        # reuse arc feed rate from the last move
                        code.append('\n(Bottom)')
                        code.append('G3 X %s Y %s I %s J %s' %
                                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                                    (x_pos, y_pos, x_radius, y_radius))

                        code.append('\nG0 Z %s' % dro_fmt % z_clear)

            code.append('\nF %s (Feed Rate, %s)' % (feed_fmt, rate_units) % feed)
            code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, pocket_op_string)

        return ok, code

    def gen_hole_list( self, hole_list, drill_pattern_type, drill_circular_dro_list ):
        list_store = list()
        number_holes, start_angle, diameter, center_x, center_y = 0, 0, 0, 0, 0
        hole_list_size = len(hole_list)
        if drill_pattern_type != 'circular':
            for row in hole_list:
                if row[1] == '' or row[2] == '':
                    break
                x_value = float(row[1])
                y_value = float(row[2])
                number_holes += 1
#               print 'gen: X %2.4f Y %2.4f  (Hole %d of %d)' % (x_value, y_value, number_holes, hole_list_size)
                list_store.append((x_value,y_value))
        else:
            # check to see if on the circular notebook page...
            valid, number_holes, error = self.validate_param(drill_circular_dro_list['drill_tap_pattern_circular_holes_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return (ok, 'Conversational Drilling entry error - ' + error, False, False, False, False)

            valid, start_angle, error = self.validate_param(drill_circular_dro_list['drill_tap_pattern_circular_start_angle_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return (ok, 'Conversational Drilling entry error - ' + error, False, False, False, False)


            valid, diameter, error = self.validate_param(drill_circular_dro_list['drill_tap_pattern_circular_diameter_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return (ok, 'Conversational Drilling entry error - ' + error, False, False, False, False)


            valid, center_x, error = self.validate_param(drill_circular_dro_list['drill_tap_pattern_circular_center_x_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return (ok, 'Conversational Drilling entry error - ' + error, False, False, False, False)


            valid, center_y, error = self.validate_param(drill_circular_dro_list['drill_tap_pattern_circular_center_y_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return (ok, 'Conversational Drilling entry error - ' + error, False, False, False, False)


            # generate the 'new drill liststore'
            radius = float(diameter / float(2))
            nh = number_holes
            hole_degrees = float(360 / float(nh))
            angle = start_angle
            hole_number = 1
            while nh > 0:
                # infinite loop guard
                if len(list_store) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                x_value = center_x + (radius * math.cos(math.radians(angle)))
                y_value = center_y + (radius * math.sin(math.radians(angle)))
                list_store.append((x_value,y_value))
                print 'gen: X %2.4f Y %2.4f  angle %.4f (Hole %d of %d)' % (x_value, y_value, angle, hole_number, hole_number+nh-1)
                nh -= 1
                hole_number += 1
                angle += hole_degrees
        # shim to generate list of X,Y values along the circular hole pattern if 'circular' is selected.
        return list_store, number_holes, start_angle, diameter, center_x, center_y


    # ------------------------------------------------------------------------------------
    # Drill
    # ------------------------------------------------------------------------------------

    def ja_parse_drill_holes(self, routine_data):
        centers_list = []
        try:
            text = routine_data['segment text']
            is_metric = routine_data['segment data']['Units']['orig'] == 'mm'
            format_spec = '%.3f' if is_metric else '%.4f'
            segment_lines = text.split('\n')
            parsing = False
            line_number = 1
            for line in segment_lines:
                if parsing:
                    if 'G80' in line:
                        break
                elif any(re.findall(r'\(Hole\s?[0-9]+', line)):
                    parsing = True
                if parsing:
                    xy = re.findall(r'\s?\-?\d*\.\d+', line)
                    if not any(xy):
                        continue
                    if 'X' in line and 'Y' in line:
                        centers_list.append((str(line_number),
                                             (format_spec % float(xy[0])),
                                             (format_spec % float(xy[1]))))
                        line_number += 1

            for n in range(line_number,self.ui.DRILL_LIST_BASIC_SIZE + 1):
                centers_list.append((str(n),'',''))

            ref = routine_data['segment data']['Post Parse']['ref']
            routine_data['segment data'][ref]['orig'] = centers_list
            routine_data['segment data'][ref]['mod'] = copy.deepcopy(centers_list)
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('Exception ocurred in _ja_parse_centers. Traceback: %s' % traceback_txt)


    def ja_edit_drill(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            drill_tap = 'drill' if self.ui.conv_drill_tap == 'tap' else 'tap',
            disable_button = self.ui.button_list['drill_tap'],
            button_state = self.ui.button_list['drill_tap'].get_visible(),
            patt_circ = self.ui.drill_pattern_notebook_page,
            spot_tool = self.ui.drill_dro_list['drill_spot_tool_number_dro'].get_text(),
            restore_proc = getattr(self, 'ja_restore_edit_drill_page')
        )

        if routine_data['segment data'].has_key('Pitch'):
            self.ui.conv_drill_tap = 'drill'
        else:
            self.ui.conv_drill_tap = 'tap'
        self.ui.on_drill_tap_set_state()

        if routine_data['segment data'].has_key('Circular Diameter'):
            self.ui.drill_pattern_notebook_page = 'circular'
            self.ui.conv_drill_tap_pattern_notebook.set_current_page(1)
            self.ui.conv_drill_tap_pattern_notebook.get_nth_page(0).hide()
        else:
            self.ui.drill_pattern_notebook_page = 'pattern'
            self.ui.conv_drill_tap_pattern_notebook.set_current_page(0)
            self.ui.conv_drill_tap_pattern_notebook.get_nth_page(1).hide()
        if restore_data['button_state']: conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        self.ui.update_drill_through_hole_hint()
        self.ui.update_chip_load_hint('conv_drill_tap_fixed')
        return restore_data

    def ja_restore_edit_drill_page(self, restore_data):
        self.ui.drill_pattern_notebook_page = restore_data['patt_circ']
        self.ui.conv_drill_tap_pattern_notebook.get_nth_page(0).show()
        self.ui.conv_drill_tap_pattern_notebook.get_nth_page(1).show()
        if restore_data['patt_circ'] == 'pattern':
            self.ui.conv_drill_tap_pattern_notebook.set_current_page(0)
        else:
            self.ui.conv_drill_tap_pattern_notebook.set_current_page(1)
        self.ui.conv_drill_tap = restore_data['drill_tap']
        self.ui.on_drill_tap_set_state()
        if restore_data.has_key('button_state') and restore_data['button_state']: conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.update_drill_through_hole_hint()
        self.ui.update_chip_load_hint('conv_drill_tap_fixed')



    def gen_drill_patt_dro_dict(self):
        # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        ddl = self.ui.drill_dro_list
        dro_to_text_data = { # specific DROs
                             'Z Start Location'       : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_z_start_dro'],         'orig' : None , 'mod' : None },
                                                         { 'proc': None,                          'ref':ddl['drill_z_end_dro'],           'orig' : None , 'mod' : None }),
                             'Peck Depth'             : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_peck_dro'],            'orig' : None , 'mod' : None }),
                             'Hole Bottom Dwell'      : ({ 'proc': 'unpack_fp',                   'ref':None,                             'orig' : None , 'mod' : None }),
                             'Number of Pecks'        : ({ 'proc': 'unpack_fp',                   'ref':None,                             'orig' : None , 'mod' : None }),
                             'Adjusted Peck Depth'    : ({ 'proc': 'unpack_fp',                   'ref':None,                             'orig' : None , 'mod' : None }),
                             'Spot With Tool'         : ({ 'proc': 'unpack_fp_na',                'ref':ddl['drill_spot_tool_number_dro'],'orig' : None , 'mod' : None }),
                             'Spot Tool Description'  : ({ 'proc': 'unpack_tool_descrip',         'ref':None,                             'orig' : None , 'mod' : None }),
                             'Spot Tool Diameter'     : ({ 'proc': 'unpack_tool_diam',            'ref':None,                             'orig' : None , 'mod' : None }),
                             'Spot Depth'             : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_spot_tool_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Hole Centers'           : ({ 'proc': None,                          'ref':'drill_liststore',                'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_drill_holes,     'ref':'Hole Centers',                   'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'revert'                 : ({ 'attr': 'conv_drill_tap',              'ref':'drill',                          'orig' : None , 'ja_diff' : 'no' },
                                                         { 'attr': 'drill_pattern_notebook_page', 'ref':'pattern',                        'orig' : None , 'ja_diff' : 'no' }),
                             'focus'                  : ({ 'proc': None,                          'ref':ddl['drill_peck_dro'] ,                           'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Pattern Drill',('Z Feed Rate','Z Feed','Z Clear Location','Z Clear'),('Feed',))

    def gen_drill_circ_dro_dict(self):
        # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        ddl = self.ui.drill_dro_list
        rdl = self.ui.drill_circular_dro_list
        dro_to_text_data = { # specific DROs
                             'Z Start Location'       : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_z_start_dro'],                          'orig' : None , 'mod' : None },
                                                         { 'proc': None,                          'ref':ddl['drill_z_end_dro'],                            'orig' : None , 'mod' : None }),
                             'Peck Depth'             : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_peck_dro'],                             'orig' : None , 'mod' : None }),
                             'Hole Bottom Dwell'      : ({ 'proc': 'unpack_fp',                   'ref':None,                                              'orig' : None , 'mod' : None }),
                             'Number of Pecks'        : ({ 'proc': 'unpack_fp',                   'ref':None,                                              'orig' : None , 'mod' : None }),
                             'Adjusted Peck Depth'    : ({ 'proc': 'unpack_fp',                   'ref':None,                                              'orig' : None , 'mod' : None }),
                             'Spot With Tool'         : ({ 'proc': 'unpack_fp_na',                'ref':ddl['drill_spot_tool_number_dro'],                 'orig' : None , 'mod' : None }),
                             'Spot Tool Description'  : ({ 'proc': 'unpack_tool_descrip',         'ref':None,                                              'orig' : None , 'mod' : None }),
                             'Spot Tool Diameter'     : ({ 'proc': 'unpack_tool_diam',            'ref':None,                                              'orig' : None , 'mod' : None }),
                             'Spot Depth'             : ({ 'proc': 'unpack_fp',                   'ref':ddl['drill_spot_tool_doc_dro'],                    'orig' : None , 'mod' : None }),
                             'Circular Number of Holes':({ 'proc': 'unpack_fp',                   'ref':rdl['drill_tap_pattern_circular_holes_dro'],       'orig' : None , 'mod' : None }),
                             'Circular Start Angle'   : ({ 'proc': 'unpack_fp',                   'ref':rdl['drill_tap_pattern_circular_start_angle_dro'], 'orig' : None , 'mod' : None }),
                             'Circular Diameter'      : ({ 'proc': 'unpack_fp',                   'ref':rdl['drill_tap_pattern_circular_diameter_dro'],    'orig' : None , 'mod' : None }),
                             'Circular Center X'      : ({ 'proc': 'unpack_fp',                   'ref':rdl['drill_tap_pattern_circular_center_x_dro'],    'orig' : None , 'mod' : None }),
                             'Circular Center Y'      : ({ 'proc': 'unpack_fp',                   'ref':rdl['drill_tap_pattern_circular_center_y_dro'],    'orig' : None , 'mod' : None }),
                             'Hole Centers'           : ({ 'proc': None,                          'ref':'drill_liststore',                                 'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_drill_holes,     'ref':'Hole Centers',                                    'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'revert'                 : ({ 'attr': 'conv_drill_tap',              'ref':'drill',                                           'orig' : None , 'ja_diff' : 'no' },
                                                         { 'attr': 'drill_pattern_notebook_page', 'ref':'circular',                                        'orig' : None , 'ja_diff' : 'no' }),
                             'focus'                  : ({ 'proc': None,                          'ref':ddl['drill_peck_dro'] ,                                            'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Circular Drill',('Z Feed Rate','Z Feed','Z Clear Location','Z Clear'),('Feed',))

    def generate_drill_gcode(self, conv_dro_list, drill_dro_list, drill_circular_dro_list, drill_pattern_notebook_page, drill_liststore):

        # empty python list for g code
        code = []

        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_feed, error =  self.validate_param(conv_dro_list['conv_z_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, peck_depth, error = self.validate_param(drill_dro_list['drill_peck_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''


        # Drill-tap specific DRO variables
        valid, z_start, error = self.validate_param(drill_dro_list['drill_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error = self.validate_param(drill_dro_list['drill_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        valid, peck_depth, error = self.validate_param(drill_dro_list['drill_peck_dro'])
        if not valid:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        # Spot drill DRO variables
        spot_drill_number_text = drill_dro_list['drill_spot_tool_number_dro'].get_text()
        spot_drill_number = 0
        raw_spot_doc = 0
        cparse.clr_alarm(drill_dro_list['drill_spot_tool_number_dro'])
        cparse.clr_alarm(drill_dro_list['drill_spot_tool_doc_dro'])
        if len(spot_drill_number_text) > 0:
            valid, spot_drill_number, error = self.validate_param(drill_dro_list['drill_spot_tool_number_dro'])
            if not valid:
                self.error_handler.write('Conversational Drilling entry error - ' + error)
                ok = False
                return ok, ''

        valid, raw_spot_doc, error = self.validate_param(drill_dro_list['drill_spot_tool_doc_dro'])
        if not valid and spot_drill_number != 0:
            self.error_handler.write('Conversational Drilling entry error - ' + error)
            ok = False
            return ok, ''

        spot_doc = math.fabs(raw_spot_doc)
        abs_spot_doc = z_start - spot_doc
        # shim to insert circular drill list if there, if not convert to simple array of tuples
        drill_list, number_holes, start_angle, diameter, center_x, center_y = self.gen_hole_list(drill_liststore,
                                                                                                 drill_pattern_notebook_page,
                                                                                                 drill_circular_dro_list)
        if isinstance(drill_list,bool) and not drill_list:
            self.error_handler.write(number_holes)  # this is now a string :)
            return False, ''



        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Drill error - Z Start must be larger than Z End'
            cparse.raise_alarm(drill_dro_list['drill_z_start_dro'], error_msg)
            cparse.raise_alarm(drill_dro_list['drill_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Drill error - Z range too small or bad Z entry value'
            cparse.raise_alarm(drill_dro_list['drill_z_start_dro'], error_msg)
            cparse.raise_alarm(drill_dro_list['drill_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = 'Conversational Drill error - Z Start must be smaller than Z Clear '
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(drill_dro_list['drill_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(z_end - z_start)

        if peck_depth > z_range:
            ok = False
            error_msg = 'Conversational Drill error - Peck depth needs to be smaller than Z depth'
            cparse.raise_alarm(drill_dro_list['drill_z_start_dro'], error_msg)
            cparse.raise_alarm(drill_dro_list['drill_z_end_dro'], error_msg)
            cparse.raise_alarm(drill_dro_list['drill_peck_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if spot_drill_number > 0:
            if abs_spot_doc < z_end:
                ok = False
                error_msg = 'Conversational Drill error - Spot depth needs to be higher than Z depth'
                cparse.raise_alarm(drill_dro_list['drill_z_end_dro'], error_msg)
                cparse.raise_alarm(drill_dro_list['drill_spot_tool_doc_dro'], error_msg)
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                return ok, ''

        if peck_depth == 0: # TODO - this block may not be needed with canned drill commands
            num_pecks = 0
            peck_adjusted = z_range
        else:
            num_pecks = int((z_range / peck_depth) + .99)
            peck_adjusted = math.fabs(z_range / num_pecks)

        spot_drill_different_tools = spot_drill_number != tool_number



        id_cnt = len(drill_list)

        # dwell is dummied to keep the file format - is no longer part of drill
        dwell = 0
        # generation details
        drill_op_string = '{} Drill'.format('Circular' if drill_pattern_notebook_page == 'circular' else 'Pattern')
        self.__write_std_info(code, drill_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)
        code.append('\n(Z Clear = %s)' % dro_fmt % z_clear)
        if spot_drill_number > 0:
            code.append('(Spot With Tool = %d)' % spot_drill_number)
            code.append('(Spot Tool Diameter = %s)' % dro_fmt % self.ui.get_tool_diameter(spot_drill_number))
            code.append('(Spot Tool Description = %s)' % self.ui.get_tool_description(spot_drill_number))
        else:
            code.append('(Spot With Tool = %s)' % conversational_base._NA_)
            code.append('(Spot Tool Diameter = %s)' % conversational_base._NA_)
            code.append('(Spot Tool Description = %s)' % conversational_base._NA_)
        code.append('(Spot Depth = %s)' % (dro_fmt) % raw_spot_doc)
        code.append('(Z Start Location = %s , End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % z_feed)
        code.append('(Peck Depth = %s)' % (dro_fmt) % (peck_depth))
        code.append('(Number of Pecks = %d)' % num_pecks)
        code.append('(Adjusted Peck Depth = %s)' % dro_fmt % peck_adjusted)
        code.append('(Hole Bottom Dwell = %.2f)' % dwell)
        if drill_pattern_notebook_page == 'circular':
            code.append('(Circular Number of Holes = %d)' % number_holes)
            code.append('(Circular Start Angle = %s)' % dro_fmt % start_angle)
            code.append('(Circular Diameter = %s)' % dro_fmt % diameter)
            code.append('(Circular Center X = %s)' % dro_fmt % center_x)
            code.append('(Circular Center Y = %s)' % dro_fmt % center_y)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)
        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)\n')

        # if a spotting tool is valid the following drill code get's done
        # twice...
        looping = 0 if spot_drill_number > 0 else 1
        spotting = True if spot_drill_number > 0 else False
        while looping < 2:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            current_tool_number = tool_number if looping > 0 else spot_drill_number
            current_z_end = z_end if looping > 0 else abs_spot_doc
            current_peck = peck_depth if looping > 0 else 0
            code.append('')
            drill_comment = '(Spot drilling)' if looping == 0 else '(Drilling)'
            looping += 1

            code.append( drill_comment )
            code.append('T%2d M6 G43 H%2d' % (current_tool_number, current_tool_number))

            code.append('\nS %d (RPM)' % (rpm))
            code.append(self._coolant_on(tool_number)+' (Coolant ON)')
            code.append('M3 (Spindle ON, Forward)')

            code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)

            hole_num = 0
            id_cnt = len(drill_list)
            x_value, y_value = drill_list[hole_num]
            hole_num += 1
            code.append('\nG0 X %s Y %s  (Hole 1 of %s)' %(dro_fmt, dro_fmt, '%d') % (x_value, y_value, id_cnt))
            code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)
            code.append('G90 G98  (Absolute Distance Mode, Canned return to Z or R)')
            if current_peck > 0:
                code.append('G83 Z %s R %s Q %s  (Canned Peck Drill)' %
                            (dro_fmt, dro_fmt, dro_fmt) %
                            (current_z_end, z_start, peck_adjusted))
            elif dwell > 0:
                code.append('G82 Z %s R %s P %s  (Canned Dwell Drill)' %
                            (dro_fmt, dro_fmt, feed_fmt) %
                            (current_z_end, z_start, dwell))
            else:
                code.append('G81 Z %s R %s  (Canned Drill)' %
                            (dro_fmt, dro_fmt) %
                            (current_z_end, z_start))
            while hole_num < id_cnt:
                # infinite loop guard
                if len(code) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                x_value, y_value = drill_list[hole_num]
                hole_num += 1
                code.append('X %s Y %s  (Hole %s)' %
                            (dro_fmt, dro_fmt, '%d') %
                            (x_value, y_value, hole_num))

            code.append('\nG80 (Cancel canned cycle)')
            code.append('\nG0 Z %s' % dro_fmt % z_clear)

            code.append('\nM9 (Coolant OFF)')
            code.append('M5 (Spindle OFF)')

            code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
            if spotting is True and looping == 1:
                conversational_base.write_ending_G30(code, '(Go to preset G30 location)',end_tag=False)
                if spot_drill_different_tools: code.append('\n'+conversational_base.m1_multi_tool_step)
            else:
                conversational_base.write_ending_G30(code, '(Go to preset G30 location)')

        conversational_base.std_end_conversational_step(code, drill_op_string)

        return ok, code


    # ------------------------------------------------------------------------------------
    # Tap
    # ------------------------------------------------------------------------------------
    def gen_tap_patt_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.tap_dro_list
        dro_to_text_data = { # specific DROs
                             'Z End Location'         : ({ 'proc': 'unpack_fp',           'ref':tdl['tap_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Hole Bottom Dwell'      : ({ 'proc': 'unpack_fp',           'ref':tdl['tap_dwell_dro'],        'orig' : None , 'mod' : None }),
                             'Pitch'                  : ({ 'proc': 'unpack_fp',           'ref':tdl['tap_pitch_dro'],        'orig' : None , 'mod' : None }),
                             'Threads per'            : ({ 'proc': 'unpack_fp',           'ref':tdl['tap_tpu_dro'],          'orig' : None , 'mod' : None }),
                             'Hole Centers'           : ({ 'proc': None,                  'ref':'drill_liststore',           'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_drill_holes, 'ref':'Hole Centers',          'orig' : None , 'mod' : None , 'ja_diff' : 'no'}),
                             'revert'                 : ({ 'attr': 'conv_drill_tap',      'ref':'tap',                       'orig' : None , 'ja_diff' : 'no'},
                                                         { 'attr': 'drill_pattern_notebook_page', 'ref':'pattern',           'orig' : None , 'ja_diff' : 'no'}),
                             'focus'                  : ({ 'proc': None,                  'ref':tdl['tap_pitch_dro'] ,       'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Pattern Tap',('Z Feed Rate','Z Feed','Z Clear Location','Z Clear'),('Feed',))

    def gen_tap_circ_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.tap_dro_list
        rdl = self.ui.drill_circular_dro_list
        dro_to_text_data = { # specific DROs
                             'Z End Location'         : ({ 'proc': 'unpack_fp', 'ref':tdl['tap_z_end_dro'],                  'orig' : None , 'mod' : None }),
                             'Hole Bottom Dwell'      : ({ 'proc': 'unpack_fp', 'ref':tdl['tap_dwell_dro'],                  'orig' : None , 'mod' : None }),
                             'Pitch'                  : ({ 'proc': 'unpack_fp', 'ref':tdl['tap_pitch_dro'],                  'orig' : None , 'mod' : None }),
                             'Threads per'            : ({ 'proc': 'unpack_fp', 'ref':tdl['tap_tpu_dro'],                    'orig' : None , 'mod' : None }),

                             'Circular Number of Holes':({ 'proc': 'unpack_fp', 'ref':rdl['drill_tap_pattern_circular_holes_dro'],   'orig' : None , 'mod' : None }),
                             'Circular Start Angle'   : ({ 'proc': 'unpack_fp', 'ref':rdl['drill_tap_pattern_circular_start_angle_dro'], 'orig' : None , 'mod' : None }),
                             'Circular Diameter'      : ({ 'proc': 'unpack_fp', 'ref':rdl['drill_tap_pattern_circular_diameter_dro'], 'orig' : None , 'mod' : None }),
                             'Circular Center X'      : ({ 'proc': 'unpack_fp', 'ref':rdl['drill_tap_pattern_circular_center_x_dro'], 'orig' : None , 'mod' : None }),
                             'Circular Center Y'      : ({ 'proc': 'unpack_fp', 'ref':rdl['drill_tap_pattern_circular_center_y_dro'], 'orig' : None , 'mod' : None }),
                             'Hole Centers'           : ({ 'proc': None,                  'ref':'drill_liststore',           'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_drill_holes, 'ref':'Hole Centers',          'orig' : None , 'mod' : None , 'ja_diff' : 'no'}),
                             'revert'                 : ({ 'attr': 'conv_drill_tap', 'ref':'tap',                            'orig' : None , 'ja_diff' : 'no'},
                                                         { 'attr': 'drill_pattern_notebook_page', 'ref':'circular',          'orig' : None , 'ja_diff' : 'no'}),
                             'focus'                  : ({ 'proc': None,        'ref':tdl['tap_pitch_dro'] ,                 'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Circular Tap',('Z Feed Rate','Z Feed','Z Clear Location','Z Clear'),('Feed',))

    def generate_tap_gcode(self, conv_dro_list, tap_dro_list, drill_circular_dro_list, drill_pattern_notebook_page, drill_liststore, tap_2x):

        # empty python list for g code
        code = []

        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_feed, error =  self.validate_param(conv_dro_list['conv_z_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        # shim to insert circular drill list if there, if not convert to simple array of tuples
        drill_list, number_holes, start_angle, diameter, center_x, center_y = self.gen_hole_list(drill_liststore,
                                                                                                 drill_pattern_notebook_page,
                                                                                                 drill_circular_dro_list)
        if isinstance(drill_list,bool) and not drill_list:
            self.error_handler.write(number_holes)  # this is now a string :)
            return False, ''



        # Drill-tap specific DRO variables
        valid, z_end, error = self.validate_param(tap_dro_list['tap_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, dwell, error = self.validate_param(tap_dro_list['tap_dwell_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, pitch, error = self.validate_param(tap_dro_list['tap_pitch_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        valid, tpu, error = self.validate_param(tap_dro_list['tap_tpu_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        unit = 'mm' if g20_g21 == 'G21' else 'inch'
        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv

        if z_end > z_clear:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Tap error - Z Clear must be larger than Z End'
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(tap_dro_list['tap_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_clear:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Tap error - Z range too small or bad Z entry value'
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(tap_dro_list['tap_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        id_cnt = len(drill_list)
        # generation details
        tap_op_string = '{} Tap'.format('Circular' if drill_pattern_notebook_page == 'circular' else 'Pattern')
        self.__write_std_info(code, tap_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('\n(Z Clear = %s)' % dro_fmt % z_clear)
        code.append('(Z End Location = %s)' % dro_fmt % z_end)
        code.append('(Z Feed = %s %s)' % (self.ui.dro_medium_format, rate_units) % z_feed)
        code.append('(Hole Bottom Dwell = %.2f)' % dwell)
        code.append('(Pitch = %s)' % dro_fmt % pitch)
        code.append('(Threads per %s = %s)' % (unit, dro_fmt) % tpu)
        if drill_pattern_notebook_page == 'circular':
            code.append('(Circular Number of Holes = %d)' % number_holes)
            code.append('(Circular Start Angle = %s)' % dro_fmt % start_angle)
            code.append('(Circular Start Angle = %s)' % dro_fmt % start_angle)
            code.append('(Circular Diameter = %s)' % dro_fmt % diameter)
            code.append('(Circular Center X = %s)' % dro_fmt % center_x)
            code.append('(Circular Center Y = %s)' % dro_fmt % center_y)

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s Q %s (Path Blending)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nS %d (RPM)' % (rpm))
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('\nM3 (Spindle ON, Forward)')
        code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)

        hole_num = 0
        x_value, y_value = drill_list[hole_num]
        hole_num += 1
        code.append('\nG0 X %s Y %s  (Hole 1 of %s)' %
                    (dro_fmt, dro_fmt, '%d') %
                    (x_value, y_value, id_cnt))
        code.append('G0 Z %s (Z Clear)' % dro_fmt % z_clear)

        if tap_2x is True:
            code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
            code.append('G1 Z %s (Z End)' % dro_fmt % z_end)
            code.append('F %s (2 x Z Feed, %s)' % (feed_fmt, rate_units) % (z_feed * 2.0))
            code.append('G1 Z %s (Z Clear)' % dro_fmt % z_clear)
            while hole_num < id_cnt:
                # infinite loop guard
                if len(code) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                x_value, y_value = drill_list[hole_num]
                hole_num += 1
                code.append('X %s Y %s  (Hole %s)' %
                            (dro_fmt, dro_fmt, '%d') %
                            (x_value, y_value, hole_num))
                code.append('F %s (Z Feed, %s)' % (feed_fmt, rate_units) % z_feed)
                code.append('G1 Z %s (Z End)' % dro_fmt % z_end)
                code.append('F %s (2 x Z Feed, %s)' % (feed_fmt, rate_units) % (z_feed * 2.0))
                code.append('G1 Z %s (Z Clear)' % dro_fmt % z_clear)

        else: # G84 tapping cycle
            if dwell > 0:
                code.append('G84 Z %s R %s P %s  (Canned Dwell Tap)' %
                            (dro_fmt, dro_fmt, feed_fmt) %
                            (z_end, z_clear, dwell))
            else:
                code.append('G84 Z %s R %s  (Canned Tap)' %
                            (dro_fmt, dro_fmt) %
                            (z_end, z_clear))

            while hole_num < id_cnt:
                x_value, y_value = drill_list[hole_num]
                hole_num += 1
                code.append('X %s Y %s  (Hole %s)' %
                            (dro_fmt, dro_fmt, '%d') %
                            (x_value, y_value, hole_num))
            # all holes completed
            # end G84 tapping cycle
            code.append('\nG80 G0 Z %s' % dro_fmt % z_clear)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, tap_op_string)

        return ok, code


    # ------------------------------------------------------------------------------------
    # Thread Mill
    # ------------------------------------------------------------------------------------
    def ja_parse_thread_mill_centers(self, routine_data):
        centers_list = []
        pattern = re.compile(r'\s?\-?\d*\.\d+')
        try:
            text = routine_data['segment text']
            is_metric = routine_data['segment data']['Units']['orig'] == 'mm'
            format_spec = '%.3f' if is_metric else '%.4f'
            segment_lines = text.split('\n')
            parsing = False
            line_number = 1
            for line in segment_lines:
                if parsing:
                    xy = pattern.findall(line)
                    if not any(xy):
                        break
                    if 'X' in line and 'Y' in line:
                        centers_list.append((str(line_number),
                                             (format_spec % float(xy[0])),
                                             (format_spec % float(xy[1]))))
                        line_number += 1
                    else:
                        break
                elif '(Thread Centers' in line:
                    parsing = True

            for n in range(line_number,self.ui.DRILL_LIST_BASIC_SIZE + 1):
                centers_list.append((str(n),'',''))

            ref = routine_data['segment data']['Post Parse']['ref']
            routine_data['segment data'][ref]['orig'] = centers_list
            routine_data['segment data'][ref]['mod'] = copy.deepcopy(centers_list)

        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('Exception ocurred in ja_parse_thread_mill_centers.  Traceback: %s' % traceback_txt)


    def ja_edit_thread_mill(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            ext_int = 'external' if self.ui.conv_thread_mill_ext_int == 'external' else 'internal',
            disable_button = [self.ui.button_list['thread_mill_ext_int']],
            drill_tap_button_state = self.ui.button_list['drill_tap'].get_visible(),
            drill_tap = 'drill' if self.ui.conv_drill_tap == 'tap' else 'tap',
            patt_circ = self.ui.drill_pattern_notebook_page,
            restore_proc = getattr(self, 'ja_restore_edit_thread_mill_page')
        )
        title = routine_data['segment data']['title']['ref']
        self.ui.conv_thread_mill_ext_int = 'internal' if 'External' in title else 'external'
        if restore_data['drill_tap_button_state']: restore_data['disable_button'].append(self.ui.button_list['drill_tap'])


        self.ui.on_thread_mill_ext_int_set_state()
        conversational.ja_toggle_buttons(restore_data['disable_button'])

        # deal with the drill stuff
        self.ui.drill_pattern_notebook_page = 'pattern'
        self.ui.conv_drill_tap_pattern_notebook.set_current_page(0)
        self.ui.show_hide_dros(False)

        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_edit_thread_mill_page(self, restore_data):
        self.ui.conv_thread_mill_ext_int = 'external' if restore_data['ext_int'] == 'internal' else 'internal'
        conversational.ja_toggle_buttons(restore_data['disable_button'],'on')
        self.ui.on_thread_mill_ext_int_set_state()
        self.ui.show_hide_dros()
        self.ja_restore_edit_drill_page(restore_data)


    def gen_thread_mill_ext_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.thread_mill_ext_dro_list
        dro_to_text_data = { # specific DROs
                             'Handed'                 : ({ 'proc': 'unpack_fp', 'ref':None,                                   'orig' : None , 'mod' : None }),
                             'Z Start Location'       : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_z_start_dro'],     'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':tdl['thread_mill_ext_z_end_dro'],       'orig' : None , 'mod' : None }),
                             'Thread Specification'   : ({ 'proc': 'unpack_cmt','ref':getattr(self.ui,'thread_combo_spec'),   'orig' : None , 'mod' : None }),
                             'Minor Dia.'             : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_minor_dia_dro'],   'orig' : None , 'mod' : None }),
                             'Major Dia.'             : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_major_dia_dro'],   'orig' : None , 'mod' : None }),
                             'Number of Passes'       : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_passes_dro'],      'orig' : None , 'mod' : None }),
                             'Initial Depth of Cut'   : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_doc_dro'],         'orig' : None , 'mod' : None }),
                             'Pitch'                  : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_pitch_dro'],       'orig' : None , 'mod' : None }),
                             'Threads per'            : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_ext_tpu_dro'],         'orig' : None , 'mod' : None }),
                             'Thread Centers'         : ({ 'proc': None,        'ref':'drill_liststore',                      'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_thread_mill_centers, 'ref':'Thread Centers', 'orig' : None , 'mod' : None, 'ja_diff' : 'no' }),
                             'revert'                 : ({ 'attr': 'conv_thread_mill_ext_int','ref':'external',               'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                  : ({ 'proc': None,        'ref':tdl['thread_mill_ext_doc_dro'],         'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'External Thread Mill',('Feed','Feed Rate','Z Clear Location','Z Clear'),('Z Feed Rate',))

    # External
    def generate_thread_mill_ext_gcode(self, conv_dro_list, thread_mill_ext_dro_list, drill_liststore, rhlh):

        # empty python list for g code
        code = []

        ok = True

        # validate params, assign to local variables, record error if validation fails
        title = self.get_conv_title(conv_dro_list)

        valid, work_offset, error = self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error = self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed, error = self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''


        # thread mill specific DRO variables

        valid, z_start, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, major_dia, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_major_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, minor_dia, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_minor_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, num_passes, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_passes_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, doc, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, pitch, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_pitch_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, tpu, error = self.validate_param(thread_mill_ext_dro_list['thread_mill_ext_tpu_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, rounding_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        unit = 'mm' if g20_g21 == 'G21' else 'inch'
        rounding_value = 0.001 if is_metric else 0.0001

        # no blending on threadmilling!  some users found no helix generated on small threads!
        blend_tol = 0.0
        naive_tol = 0.0

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Thread Mill error - Z Start must be larger than Z End'
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_z_start_dro'], error_msg)
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Thread Mill error - Z range too small or bad Z entry value'
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_z_start_dro'], error_msg)
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = 'Conversational Thread Mill error - Z Start must be smaller than Z Clear '
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        # ***** calculated parameters  ***** #
        z_range = math.fabs(z_end - z_start)
        helix_revs = z_range / pitch  # number of turns incuding partial turns
        modf_revs = math.modf(helix_revs)
        helix_remainder = (2 * math.pi * modf_revs[0])  # in radians
        tool_radius = tool_dia / 2
        major_radius = major_dia / 2
        minor_radius = minor_dia / 2

        # param_p is an integer number of helix revs, any partial revs count as 1, so 3.9999 turns = P 4, 4.0 turns = P 4, 4.0001 = P 5
        if modf_revs[0] != 0:
            param_p = modf_revs[1] + 1  # an integer number of helix revs, any partial revs count as 1, so 3.9999 turns = P 4, 4.0 turns = P 4, 4.0001 = P 5
        else:
            param_p = modf_revs[1]

        if doc > math.fabs(major_radius - minor_radius) + rounding_value:
            ok = False
            error_msg = "Conversational Thread Mill error - Z Depth of Cut cannot be bigger than the Z range of cut"
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_major_dia_dro'], error_msg)
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_minor_dia_dro'], error_msg)
            cparse.raise_alarm(thread_mill_ext_dro_list['thread_mill_ext_doc_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if rhlh == 'left':
            arc = 'G3'
            hand = "Left"
            yk = -1
        else:
            arc = 'G2'
            hand = "Right"
            yk = 1

        retract_radius = (1.1 * major_radius) + tool_radius
        x_retract_delta = retract_radius * math.cos(helix_remainder)
        y_retract_delta = retract_radius * math.sin(helix_remainder) * yk

        z_start_offset = (major_radius - minor_radius) * math.tan(math.pi / 6)

        degression = 2  # 1 = each cut depth is incremented by DoC, 2 = constant cutting area

        id_cnt = 0
        for row in drill_liststore:
            if row[0] == '':
                break
            if row[1] == '':
                break
            id_cnt += 1

        x_loc_list = []
        y_loc_list = []
        x_retract_loc_list = []
        y_retract_loc_list = []
        for i in range(id_cnt):
            drill_iter = drill_liststore.get_iter(i,)
            x_value = float(drill_liststore.get_value(drill_iter, 1))
            y_value = float(drill_liststore.get_value(drill_iter, 2))
            x_loc_list.append(x_value)
            y_loc_list.append(y_value)
            x_retract_loc_list.append(x_value + x_retract_delta)
            y_retract_loc_list.append(y_value - y_retract_delta)

        active_thread_text = self.ui.builder.get_object('thread_combobox').get_active_text()
        # ---------------------------------------------------------------------
        # generation details, g-code header
        # ---------------------------------------------------------------------
        external_thread_op_string = 'External Thread Mill'
        self.__write_std_info(code, external_thread_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('\n(Thread Centers)')

        for i in range(id_cnt):
            code.append('(    %d  X = %s   Y = %s)' %
                        (i + 1, dro_fmt, dro_fmt) %
                        (x_loc_list[i], y_loc_list[i]))

        code.append('(Thread Specification = %s)' % active_thread_text)
        code.append('(Minor Dia. = %s)' %dro_fmt % minor_dia)
        code.append('(Major Dia. = %s)' %  dro_fmt %  major_dia)
        code.append('(Initial Depth of Cut = %s)' % dro_fmt % doc)
        code.append('(Number of Passes = %s)' % dro_fmt % num_passes)
        code.append('(Pitch = %s)' % dro_fmt % pitch)
        code.append('(Threads per %s = %s)' % (unit, dro_fmt) % tpu)
        code.append('(%s Handed)' % hand)

        code.append('\n(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed)

        code.append('\n(Z Clear = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s , Z End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s (Path Blending)' % dro_fmt % blend_tol)
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)\n')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nS %d (RPM)' % rpm)
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')


        for i in range(id_cnt):
            code.append('\n(*** Thread %d ***)' % (i + 1))
            # go to start and Z safe
            code.append('\nG0 X %s Y %s' %
                        (dro_fmt, dro_fmt) %
                        ((x_loc_list[i] + (1.1 * major_radius) + tool_radius), y_loc_list[i]))
            code.append('G0 Z %s' % dro_fmt % z_clear)
            code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)

            tpass_cnt = 1
            current_radius = major_radius + tool_radius - doc
            while current_radius > ((minor_radius * 1.001) + tool_radius):  # 1.001 prevents calculating the last pass that comes close to minor_radius but not quite
                # infinite loop guard
                if len(code) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                code.append('\n(Pass %d)' % (tpass_cnt))

                x_doc_delta = major_radius - (current_radius - tool_radius)
                z_doc_offset = x_doc_delta * math.tan(math.pi / 6)

                code.append('G0 Z %s' % dro_fmt % (z_start + z_start_offset - z_doc_offset))
                # move to helix start
                code.append('G1 X %s' % dro_fmt % (x_loc_list[i] + current_radius))

                # cut helix to z_end, target is the partial arc end, then add the
                # number of full revolutions
                x_delta = current_radius * math.cos(helix_remainder)
                y_delta = current_radius * math.sin(helix_remainder) * yk
                x_arc_end = x_loc_list[i] + x_delta
                y_arc_end = y_loc_list[i] - y_delta
                x_center_offset = current_radius * -1
                y_center_offset = 0
                # While cutting an arc the feed rate of the tool center and tool's
                # cutting location are not the same.
                feed_at_cut = feed + ((feed * tool_radius) / (current_radius))
                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_at_cut)
                code.append('%s X %s Y %s Z %s I %s J %s P %d' %
                            (arc, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, param_p) %
                            (x_arc_end, y_arc_end, (z_end + z_start_offset - z_doc_offset), x_center_offset, y_center_offset))
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                code.append('G0 X %s Y %s' %
                            (dro_fmt, dro_fmt) %
                            (x_retract_loc_list[i], y_retract_loc_list[i]))
                code.append('G0 Z %s' % dro_fmt % z_clear)
                code.append('G0 X %s Y %s' %
                            (dro_fmt, dro_fmt) %
                            (x_loc_list[i] + (1.1 * major_radius) + tool_radius, y_loc_list[i]))
                tpass_cnt += 1
                current_radius = major_radius + tool_radius - (doc * math.pow(tpass_cnt, 1.0 / degression))
                ##area_doc = (doc ** 2) * math.tan(math.pi / 6)
                ##current_doc = math.sqrt((tpass_cnt * area_doc) / (math.tan (math.pi / 6)))
                ###current_doc = math.sqrt(tpass_cnt * (doc ** 2))
                ###current_radius = major_radius + tool_radius - current_doc

            code.append('\n(Pass %d)' % (tpass_cnt))
            code.append('G0 Z %s' % dro_fmt % z_start)

            current_radius = minor_radius + tool_radius
            x_current = x_loc_list[i] + current_radius
            code.append('G1 X %s' % dro_fmt % x_current)

            x_delta = current_radius * math.cos(helix_remainder)
            y_delta = current_radius * math.sin(helix_remainder) * yk
            x_arc_end = x_loc_list[i] + x_delta
            y_arc_end = y_loc_list[i] - y_delta
            x_center_offset = current_radius * -1
            y_center_offset = 0

            feed_at_cut = feed + ((feed * tool_radius) / current_radius)
            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_at_cut)
            code.append('%s X %s Y %s Z %s I %s J %s P %d' %
                        (arc, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, param_p) %
                        (x_arc_end, y_arc_end, z_end, x_center_offset, y_center_offset))

            code.append('G0 X %s Y %s' %
                        (dro_fmt, dro_fmt) %
                        (x_retract_loc_list[i], y_retract_loc_list[i]))

            code.append('G0 Z %s' % dro_fmt % z_clear)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, external_thread_op_string)

        return ok, code



    # Internal
    def gen_thread_mill_int_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.thread_mill_int_dro_list
        dro_to_text_data = { # specific DROs
                             'Handed'                 : ({ 'proc': 'unpack_fp', 'ref':None,                                       'orig' : None , 'mod' : None }),
                             'Z Start Location'       : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_z_start_dro'],         'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':tdl['thread_mill_int_z_end_dro'],           'orig' : None , 'mod' : None }),
                             'Thread Specification'   : ({ 'proc': 'unpack_cmt','ref':getattr(self.ui,'thread_combo_spec'),       'orig' : None , 'mod' : None }),
                             'Retract Policy'         : ({ 'proc': 'unpack_cmt','ref':getattr(self.ui,'thread_internal_retract'), 'orig' : None , 'mod' : None }),
                             'Minor Dia.'             : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_minor_dia_dro'],       'orig' : None , 'mod' : None }),
                             'Major Dia.'             : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_major_dia_dro'],       'orig' : None , 'mod' : None }),
                             'Number of Passes'       : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_passes_dro'],          'orig' : None , 'mod' : None }),
                             'Initial Depth of Cut'   : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_doc_dro'],             'orig' : None , 'mod' : None }),
                             'Pitch'                  : ({ 'proc': 'unpack_fp', 'ref':tdl['thread_mill_int_pitch_dro'],           'orig' : None , 'mod' : None },
                                                         { 'proc': None,        'ref':tdl['thread_mill_int_tpu_dro'],             'orig' : None , 'mod' : None }),
                             'Thread Centers'         : ({ 'proc': None,        'ref':'drill_liststore',                          'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_parse_thread_mill_centers, 'ref':'Thread Centers',     'orig' : None , 'mod' : None, 'ja_diff' : 'no' }),
                             'revert'                 : ({ 'attr': 'conv_thread_mill_ext_int','ref':'external',                   'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                  : ({ 'proc': None,        'ref':tdl['thread_mill_int_doc_dro'],             'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Internal Thread Mill',('Feed','Feed Rate','Z Clear Location','Z Clear'),('Z Feed Rate',))

    def generate_thread_mill_int_gcode(self, conv_dro_list, thread_mill_int_dro_list, drill_liststore, rhlh):
        def __retract_pos(x_in, y_in, x_last, y_last, _rr):
            # calculates a retract position according to the retract policy
            # dictated by [ui]conv_thread_mill_retract. If 'minimal' the retract
            # is to the 'retract radius' (_rr - here) along the vector from the last
            # x,y position to the center of the thread circle.
            if self.ui.conv_thread_mill_retract != 'minimal': return (x_in, y_in)
            __dx = x_last - x_in
            __dy = y_last - y_in
            __retract_angle = math.atan2(__dy,__dx)
            return (x_in + _rr*math.cos(__retract_angle), y_in + _rr*math.sin(__retract_angle))

        # empty python list for g code
        code = []

        ok = True

        # validate params, assign to local variables, record error if validation fails
        title = self.get_conv_title(conv_dro_list)


        valid, work_offset, error = self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error = self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed, error = self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''


        # thread mill specific DRO variables

        valid, z_start, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_end, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, major_dia, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_major_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, minor_dia, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_minor_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, num_passes, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_passes_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, doc, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, pitch, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_pitch_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        valid, tpu, error = self.validate_param(thread_mill_int_dro_list['thread_mill_int_tpu_dro'])
        if not valid:
            self.error_handler.write('Conversational Thread Mill entry error - ' + error)
            ok = False
            return ok, ''

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, rounding_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        blend_tol = 0.
        tpud = 'Threads/mm' if is_metric else 'Threads/inch'

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv
        tool_dia_clearance_factor = 1.0/1.05

        if z_end > z_start:
            z_dir = 1
            ok = False
            error_msg = 'Conversational Thread Mill error - Z Start must be larger than Z End'
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_z_start_dro'], error_msg)
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif z_end < z_start:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational Thread Mill error - Z range too small or bad Z entry value'
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_z_start_dro'], error_msg)
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_z_end_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if z_clear < z_start:
            ok = False
            error_msg = 'Conversational Thread Mill error - Z Start must be smaller than Z Clear '
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if tool_dia > minor_dia * tool_dia_clearance_factor:
            ok = False
            error_msg = 'Conversational Thread Mill error - The tool dia. must be smaller than the hole dia. including a retract distance'
            cparse.raise_alarm(conv_dro_list['conv_tool_number_dro'], error_msg)
            cparse.raise_alarm(thread_mill_int_dro_list['thread_mill_int_minor_dia_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        # ***** Calculated Variables ***** #
        z_range = math.fabs(z_end - z_start)
        helix_revs = z_range / pitch  # number of turns incuding partial turns
        modf_revs = math.modf(helix_revs)
        helix_remainder = (2 * math.pi * modf_revs[0])  # in radians
        tool_radius = tool_dia / 2
        major_radius = major_dia / 2
        minor_radius = minor_dia / 2
        retract_radius = minor_radius - tool_radius - tool_radius*((1.0-tool_dia_clearance_factor)/2.0)
        if retract_radius < 0.0: retract_radius = 0.0

        # param_p is an integer number of helix revs, any partial revs count as 1, so 3.9999 turns = P 4, 4.0 turns = P 4, 4.0001 = P 5
        if modf_revs[0] != 0:
            param_p = modf_revs[1] + 1  # an integer number of helix revs, any partial revs count as 1, so 3.9999 turns = P 4, 4.0 turns = P 4, 4.0001 = P 5
        else:
            param_p = modf_revs[1]

        z_start_offset = (major_radius - minor_radius) * math.tan(math.pi / 6)

        degression = 2  # 1 = each cut depth is incremented by DoC, 2 = constant cutting area

        x_loc_list = []
        y_loc_list = []
        x_retract_loc_list = []
        y_retract_loc_list = []
        id_cnt = 0
        for _,x,y in drill_liststore:
            if x == '' or y == '': break
            x_loc_list.append(float(x))
            y_loc_list.append(float(y))
            x_retract_loc_list.append(float(x))
            y_retract_loc_list.append(float(y))
            id_cnt += 1

        if rhlh == 'left':
            arc = 'G3'
            hand = "Left"
            yk = -1
        else:
            arc = 'G2'
            hand = "Right"
            yk = 1

        active_thread_text = self.ui.builder.get_object('thread_combobox').get_active_text()
        # generation details
        internal_thread_op_string = 'Internal Thread Mill'
        self.__write_std_info(code, internal_thread_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('\n(Thread Centers)')
        for i in range(id_cnt):
            code.append('(    %d  X = %s   Y = %s)' %
                        (i + 1, dro_fmt, dro_fmt) %
                        (x_loc_list[i], y_loc_list[i]))

        code.append('(Thread Specification = %s)' % active_thread_text)
        code.append('(Retract Policy = %s)' % self.ui.conv_thread_mill_retract)
        code.append('(Minor Dia. = %s)' % dro_fmt % minor_dia)
        code.append('(Major Dia. = %s)' % dro_fmt % major_dia)
        code.append('(Initial Depth of Cut = %s)' % dro_fmt % doc)
        code.append('(Number of Passes = %s)' % dro_fmt % num_passes)
        code.append('(Pitch = %s, %s = %s )' % (dro_fmt, tpud, dro_fmt) % (pitch, tpu))
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed)
        code.append('(%s Handed)' % hand)

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s , End Location = %s)' % (dro_fmt, dro_fmt) % (z_start, z_end))

        code.append(conversational.start_of_gcode)

        # Start up code
        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('G64 P %s (Path Blending)' %  dro_fmt % blend_tol)
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Set Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 (Go to preset G30 location)')
        code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

        code.append('\nF %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
        code.append('S %d (RPM)' % rpm)
        code.append(self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        for i in range(id_cnt):
            code.append('\n(*** Thread %d ***)' % (i + 1))
            # go to start and Z safe
            code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % ((x_loc_list[i], y_loc_list[i])))
            code.append('G0 Z %s' % dro_fmt % z_clear)

            tpass_cnt = 1
            current_radius = minor_radius - tool_radius + doc
            while current_radius <= (major_radius - tool_radius):
                # infinite loop guard
                if len(code) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                code.append('\n(Pass %d)' % (tpass_cnt))

                x_doc_delta = (current_radius + tool_radius) - minor_radius
                z_doc_offset = x_doc_delta * math.tan(math.pi / 6)

                code.append('G0 Z %s' % dro_fmt % (z_start + z_start_offset - z_doc_offset))
                # move to helix start
                x_start_pos = x_retract_loc_list[i] if self.ui.conv_thread_mill_retract != 'minimal' else x_loc_list[i] + retract_radius
                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_start_pos, y_retract_loc_list[i]))
                code.append('G1 X %s' % dro_fmt % (x_loc_list[i] + current_radius))

                # cut helix to z_end, target is the partial arc end, then add the
                # number of full revolutions
                x_delta = current_radius * math.cos(helix_remainder)
                y_delta = current_radius * math.sin(helix_remainder) * yk
                x_arc_end = x_loc_list[i] + x_delta
                y_arc_end = y_loc_list[i] - y_delta
                x_center_offset = current_radius * -1
                y_center_offset = 0
                # While cutting an arc the feed rate of the tool center and tool's
                # cutting location are not the same.
                feed_at_cut = feed * (current_radius / (current_radius + tool_radius))
                code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_at_cut)
                code.append('%s X %s Y %s Z %s I %s J %s P %d' %
                            (arc, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, param_p) %
                            (x_arc_end,
                             y_arc_end,
                             (z_end + z_start_offset - z_doc_offset),
                             x_center_offset,
                             y_center_offset))
                # go to the retract point ...
                code.append('F %s (Feed, %s)' % (feed_fmt, rate_units) % feed)
                cx, cy = __retract_pos(x_retract_loc_list[i], y_retract_loc_list[i], x_arc_end, y_arc_end, retract_radius)
                code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (cx, cy))
                tpass_cnt += 1
                current_radius = minor_radius - tool_radius + (doc * math.pow(tpass_cnt, 1.0 / degression))

            code.append('\n(Pass %d)' % (tpass_cnt))
            code.append('G0 Z %s' % dro_fmt % z_start)
            x_start_pos = x_retract_loc_list[i] if self.ui.conv_thread_mill_retract != 'minimal' else x_loc_list[i] + retract_radius
            code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (x_start_pos, y_retract_loc_list[i]))

            current_radius = major_radius - tool_radius
            x_current = x_loc_list[i] + current_radius
            code.append('G1 X %s' % dro_fmt % x_current)

            x_delta = current_radius * math.cos(helix_remainder)
            y_delta = current_radius * math.sin(helix_remainder) * yk
            x_arc_end = x_loc_list[i] + x_delta
            y_arc_end = y_loc_list[i] - y_delta
            x_center_offset = current_radius * -1
            y_center_offset = 0

            feed_at_cut = feed * (current_radius / (current_radius + tool_radius))
            code.append('F %s (Arc Feed, %s)' % (feed_fmt, rate_units) % feed_at_cut)
            code.append('%s X %s Y %s Z %s I %s J %s P %d' %
                        (arc, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, param_p) %
                        (x_arc_end,
                         y_arc_end,
                         z_end,
                         x_center_offset,
                         y_center_offset))

            cx, cy = __retract_pos(x_retract_loc_list[i], y_retract_loc_list[i], x_arc_end, y_arc_end, retract_radius)
            code.append('G0 X %s Y %s' % (dro_fmt, dro_fmt) % (cx, cy))
            code.append('G0 Z %s' % dro_fmt % z_clear)

        code.append('\nM9 (Coolant OFF)')
        code.append('M5 (Spindle OFF)')

        code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
        conversational_base.write_ending_G30(code, '(Go to preset G30 location)')
        conversational_base.std_end_conversational_step(code, internal_thread_op_string)

        return ok, code


    # ------------------------------------------------------------------------------------
    # Engrave
    # ------------------------------------------------------------------------------------
    def ja_set_sn(self, routine_data):
        if routine_data['segment data']['Ammend Serial Number']['mod'] != 'no':
            current_sn = self.redis.hget('machine_prefs', 'current_engraving_sn')
            self.ui.engrave_dro_list['engrave_sn_start_dro'].set_text(current_sn)
            routine_data['segment data']['Last SN']['orig'] = current_sn
            routine_data['segment data']['Last SN']['mod'] = current_sn

    def ja_edit_engrave(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc whihc knows how to return
        # the conv page to state in whihc is was found...
        restore_data = dict(
            font_file = self.ui.engrave_font_pf,
            just = self.ui.engrave_just,
            restore_proc = getattr(self, 'ja_restore_edit_engrave_page')
        )
        self.ja_edit_general(routine_data)
        self.ui.on_engrave_set_font(routine_data['segment data']['Font']['mod'])
        self.ui.set_active_engrave_justification(routine_data['segment data']['Justification Setting']['mod'])
        self.ja_set_sn(routine_data)
        return restore_data

    def ja_restore_edit_engrave_page(self, restore_data):
        self.ui.engrave_font_pf = restore_data['font_file']
        self.ui.set_active_engrave_justification(restore_data['just'])
        return

    def ja_post_parse_z_depth(self, routine_data):
        z_start = routine_data['segment data']['Z Start Location']['mod']
        z_doc = routine_data['segment data']['Z Depth of Cut']['mod']
        min_z = float(z_start) - math.fabs(float(z_doc))
        routine_data['tool data'][0]['min_z'] = min_z

    def gen_engrave_dro_dict(self):
        # ui is a base class attribute
        edl = self.ui.engrave_dro_list
        dro_to_text_data = { # specific DROs
                             'Z Start Location'       : ({ 'proc': 'unpack_fp',    'ref':edl['engrave_z_start_dro'],  'orig' : None , 'mod' : None }),
                             'Z Depth of Cut'         : ({ 'proc': 'unpack_fp',    'ref':edl['engrave_z_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Text to engrave'        : ({ 'proc': 'unpack_cmt',   'ref':edl['engrave_text_dro'],     'orig' : None , 'mod' : None }),
                             'Scale'                  : ({ 'proc': 'unpack_cmt',   'ref':None,                        'orig' : None , 'mod' : None }),
                             'X Base Location'        : ({ 'proc': 'unpack_fp',    'ref':edl['engrave_x_base_dro'],   'orig' : None , 'mod' : None }),
                             'Y Base Location'        : ({ 'proc': 'unpack_fp',    'ref':edl['engrave_y_base_dro'],   'orig' : None , 'mod' : None }),
                             'Font height'            : ({ 'proc': 'unpack_fp',    'ref':edl['engrave_height_dro'],   'orig' : None , 'mod' : None }),
                             'Font'                   : ({ 'proc': 'unpack_font',  'ref':None,                        'orig' : None , 'mod' : None }),
                             'Ammend Serial Number'   : ({ 'proc': 'unpack_cmt',   'ref':None,                        'orig' : None , 'mod' : None }),
                             'Justification Setting'  : ({ 'proc': 'unpack_cmt',   'ref':None,                        'orig' : None , 'mod' : None }),
                             'Last SN'                : ({ 'proc': None,           'ref':edl['engrave_sn_start_dro'], 'orig' : None , 'mod' : None }),
                             'Post Parse'             : ({ 'proc': self.ja_post_parse_z_depth, 'ref':None,            'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'pre_gen'                : ({ 'proc': self.ja_set_sn, 'ref':None,            'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'focus'                  : ({ 'proc': None,           'ref':edl['engrave_text_dro'],     'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Engrave Text',('Feed','Feed Rate'),('Z Feed Rate',))

    def generate_engrave_gcode(self, conv_dro_list, engrave_dro_list, font_file, just):

        # empty python list for g code
        code = []

        ok = True

        # string variables
        title  = self.get_conv_title(conv_dro_list)

        valid, serial_number_start, error =  self.validate_param(engrave_dro_list['engrave_sn_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        if serial_number_start is None:
            valid, engrave_text, error = self.validate_text(engrave_dro_list['engrave_text_dro'])

            if not valid:
                error = '%s: Enter either Text and/or a Serial Number' % error
                self.error_handler.write('Conversational Engraving entry error - ' + error)
                ok = False
                return False, ' '
        else:
            (valid, engrave_text) = cparse.is_text(engrave_dro_list['engrave_text_dro'].get_text())

        # validate params (converts to float), assign to local variables, record error if validation fails
        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, rpm, error =  self.validate_param(conv_dro_list['conv_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, feed_rate, error =  self.validate_param(conv_dro_list['conv_feed_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, tool_number, error =  self.validate_param(conv_dro_list['conv_tool_number_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_clear, error = self.validate_param(conv_dro_list['conv_z_clear_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''


        valid, x_base, error =  self.validate_param(engrave_dro_list['engrave_x_base_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, y_base, error =  self.validate_param(engrave_dro_list['engrave_y_base_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, z_start, error =  self.validate_param(engrave_dro_list['engrave_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, raw_z_doc, error =  self.validate_param(engrave_dro_list['engrave_z_doc_dro'])
        z_doc = math.fabs(raw_z_doc)
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''

        valid, str_hght, error =  self.validate_param(engrave_dro_list['engrave_height_dro'])
        if not valid:
            self.error_handler.write('Conversational Engraving entry error - ' + error)
            ok = False
            return ok, ''


        cut_fill = 0  # disabled fill cutting, not reliable enough

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, rounding_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()
        scale_fmt = '%3.2f' if is_metric else '%2.3f'
        ttt_units = 0 if is_metric else 1
        sn_kern_extra = 0.508 if is_metric else 0.18

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[tool_number].diameter) * ttable_conv

        if z_clear < z_start:
            ok = False
            error_msg = 'Conversational Engrave error - Z Start must be smaller than Z Clear '
            cparse.raise_alarm(conv_dro_list['conv_z_clear_dro'], error_msg)
            cparse.raise_alarm(engrave_dro_list['engrave_z_start_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_clearance = z_clear - z_start

        # keep track of engrave text. if empty use a test string
        # of numbers only
        engrave_text_empty = True if engrave_text == '' or engrave_text == None else False
        if engrave_text_empty is True:
            engrave_text = '0123456789'
            just = 'left'

        str_y_max, str_y_min, x_end = ftesy.freetype_y_range(engrave_text, font_file)
        str_y_range = str_y_max - str_y_min
        if str_y_range == 0:
            char_scale = 0
        else:
            char_scale = str_hght / str_y_range

        if just == 'right':
            x_start = x_base - (x_end * char_scale)
        elif just == 'center':
            x_start = x_base - (x_end * char_scale / 2.0)
        else:
            x_start = x_base

        ammend_serial_number = 'no' if serial_number_start is None else 'yes'
#       print ' str_y_max: %.3f str_y_min: %.3f x_end: %.3f ' % (str_y_max, str_y_min, x_end)
#       print ' str_hght: %.3f  char_scale: %.8f str_y_range: %.3f ' % (str_hght, char_scale, str_y_range)
        # generation details
        engraving_op_string = 'Engrave Text'
        self.__write_std_info(code, engraving_op_string, g20_g21, units, work_offset, tool_number, dro_fmt % tool_dia, rpm)

        code.append('(Text to engrave = %s)' % engrave_text)
        code.append('(Font = %s)' % font_file)
        code.append('(Font height = %s)' % dro_fmt % str_hght)
        code.append('(Scale = %s)' % char_scale)

        code.append('(X Base Location = %s)' % dro_fmt % x_base)
        code.append('(Justification Setting = %s)' % just)
        code.append('(Y Base Location = %s)' % dro_fmt % y_base)
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % feed_rate)

        code.append('\n(Z Clear Location = %s)' % dro_fmt % z_clear)
        code.append('(Z Start Location = %s)\n' % dro_fmt % z_start)
        code.append('(Z Depth of Cut = %s)' % dro_fmt % raw_z_doc)
        code.append('(Ammend Serial Number = %s)' % ammend_serial_number)

        code.append(conversational.start_of_gcode)

        code.append('\nG17 G90  (XY Plane, Absolute Distance Mode)')
        code.append('\nG64 P %s Q %s (Path Blending)\n' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol))

        if work_offset[0] == 'G' or work_offset[0] == 'g':
            work_offset = work_offset[1:]
        work_offset_num = int(work_offset)

        #engrave_font = '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'
        #engrave_font = '/usr/share/fonts/truetype/ttf-dejavu/DejaVuSans-Bold.ttf'
        #[-?] [-s subdiv] [-u] [-c xy_scale] [-l fill_linescale] [-f /some/file.ttf] [-x x_offset]
        #[-y y_offset] [-e safe_height] [-g depth_o_cut] [-r feed_rate] [-d] 'The Text'
        print "---> Command = truetype-tracer -f", font_file, "-c", str(char_scale), '-l', str(cut_fill), '-x', str(x_start), '-y', str(y_base), '-z', str(z_start), '-e', str(z_clear), '-g', str(z_doc), '-t', str(tool_number), '-r', str(feed_rate), '-h', str(rpm), '-i', str(ttt_units), '-w', str(work_offset_num), '  ', engrave_text

        # if there's serial number text in the SN START dro
        # generate the G47

        g47_code = None
        if serial_number_start is not None:
            if int(serial_number_start) >= 0:
                x_g47_start = x_start
                if not engrave_text_empty:
                    x_g47_start += x_end * char_scale
                    x_kern_space = ((x_end * char_scale) / len(engrave_text)) * sn_kern_extra
                    x_g47_start += x_kern_space
                y_g47_start = y_base
                x_width = x_end * char_scale / len(engrave_text)
                z_doc_actual = z_start-z_doc
                g47_code = '\nG47 X%.4f Y%.4f Z%.4f P%s Q%s R%.4f\n' % (x_g47_start, y_g47_start, z_doc_actual, scale_fmt, scale_fmt, z_clear ) % (x_width, str_hght)

        # no engrave text...
        if engrave_text_empty is True:
            if g47_code is not None:
                # Startup code...
                code.append('%s (units in %s)' % (g20_g21, units))
                code.append('G%s (Set Work Offset)' % work_offset)

                # Go to safe place for tool change
                code.append('\nG30 (Go to preset G30 location)')
                code.append('T%2d M6 G43 H%2d' % (tool_number, tool_number))

                code.append('\nF %s (Feed, %s)' % (feed_fmt, rate_units) % feed_rate)
                code.append('S %d (RPM)' % rpm)
                code.append(self._coolant_on(tool_number)+' (Coolant ON)')
                if rpm == 0:
                    code.append('M5 (Spindle OFF)')
                else:
                    code.append('M3 (Spindle ON, Forward)')

                code.append('\n(Serial Number Start @: %s)' % serial_number_start)
                code.append(g47_code)

                code.append('\nM9 (Coolant OFF)')
                code.append('M5 (Spindle OFF)')

                code.append('\nG30 Z %s (Go in Z only to preset G30 location)' % z_clear)
                conversational_base.write_ending_G30(code, '(Go to preset G30 location)')

                code.append('\nM30 (End of Program)')

        # yes engrave text...
        else:
            # TODO - Check for errors, exceptions?
            args = ['truetype-tracer',
                 '-f', font_file,
                 '-c', str(char_scale),
                 '-l', str(cut_fill),
                 '-x', str(x_start),
                 '-y', str(y_base),
                 '-z', str(z_start),
                 '-e', str(z_clearance),
                 '-g', str(z_doc),
                 '-t', str(tool_number),
                 '-r', str(feed_rate),
                 '-h', str(rpm),
                 '-i', str(ttt_units),
                 '-w', str(work_offset_num),
                 engrave_text]
            ttt_code = subprocess.Popen(args, stdout=subprocess.PIPE).communicate()[0]

            if g47_code is None:
                code_list = ttt_code.split('\n')
            else:
                insert_G47_position = ttt_code.find('\nM9')
                tttG47_code = ttt_code[:insert_G47_position] + g47_code + ttt_code[insert_G47_position:]
                code_list = tttG47_code.split('\n')
                # update redis:
                try:
                    if any(serial_number_start):
                        self.redis.hset('machine_prefs', 'current_engraving_sn', serial_number_start)
                except:
                    pass

                if ttt_code == '':
                    ok = False
                    self.error_handler.write('TrueType-Tracer did not run properly \nCommand = %s' % str(args))
                    return ok, ''
            code.extend(code_list)
            conversational_base.insert_conversational_end_tag(code, engraving_op_string)

        return ok, code

    # ------------------------------------------------------------------------------------
    # DXF
    # ------------------------------------------------------------------------------------
    def ja_edit_dxf(self, routine_data):
        # this gets called from JA to setup the conversational page for
        # editing a specific type of pocket. The 'restore' proc gets packed in the
        # data, so JA just calls the restore proc which knows how to return
        # the conv page to the state in which it was found...
        self.ja_edit_general(routine_data)
        self.ja_dxf_set_cutter_compensation(routine_data)
        self.ja_dxf_set_file_path(routine_data)
        self.ja_dxf_set_enabled_layers(routine_data)
        self.ui.dxf_panel._plot()

    def ja_dxf_set_cutter_compensation(self, routine_data):
        cutter_comp_dict = {'On': 40, 'Right': 41, 'Left': 42}
        cutter_comp_text = routine_data['segment data']['Cutter Compensation']['mod']
        cutter_comp = cutter_comp_dict[cutter_comp_text]
        self.ui.dxf_panel.cutter_compensation = cutter_comp

    def ja_dxf_set_file_path(self, routine_data):
        file_path = routine_data['segment data']['DXF File Path']['mod']
        self.ui.load_dxf_file(file_path, plot=False)

    def ja_dxf_set_enabled_layers(self, routine_data):
        layer_string = self.ja_dxf_convert_code_to_layers(routine_data['segment text'])
        routine_data['segment data']['Layers']['mod'] = layer_string
        routine_data['segment data']['Layers']['orig'] = layer_string
        enabled_layers = ast.literal_eval(routine_data['segment data']['Layers']['mod'])

        self.ui.dxf_panel.enabled_layers = enabled_layers

    def ja_dxf_get_file_path(self, data=None):
        if data is None:
            return self.ui.dxf_panel.dxf_file_path
        else:
            pass  # TODO: restore cutter comp

    def ja_dxf_get_enabled_layers(self, data=None):
        if data is None:
            return str(self.ui.dxf_panel.enabled_layers)
        else:
            pass  # TODO: restore cutter comp

    def ja_dxf_get_cutter_compensation(self, data=None):
        if data is None:
            cutter_comp_dict = {40: 'On', 41: 'Right', 42: 'Right'}
            cutter_comp = cutter_comp_dict[self.ui.dxf_panel.cutter_compensation]
            return cutter_comp
        else:
            pass  # TODO: restore cutter comp

    def ja_dxf_post_parse_z_depth(self, routine_data):
        z_end = routine_data['segment data']['Z End Location']['mod']
        routine_data['tool data'][0]['min_z'] = float(z_end)

    def ja_dxf_convert_layers_to_code(self, layers):
        code = []
        layer_string = str(layers)
        chunk_size = 240  # max line length = 255
        chunks = []
        pos = 0
        while (pos+chunk_size) < len(layer_string):
            chunk = layer_string[pos:pos+chunk_size]
            length = chunk_size
            open_pos = chunk.rfind('[')
            close_pos = chunk.rfind(']')
            if close_pos > -1 and open_pos > close_pos:  # open brackets
                length -= chunk_size - open_pos
            chunks.append(layer_string[pos:pos+length])
            pos += length
        chunks.append(layer_string[pos:])

        for chunk in chunks:
            code.append('(Layers = %s)' % chunk)
        return code

    def ja_dxf_convert_code_to_layers(self, code):
        layer_string = ''
        for match in re.finditer('\(Layers = (.*)\)', code):
            layer_string += match.group(1)
        return layer_string

    def gen_dxf_dro_dict(self):
        dros = self.ui.dxf_panel.dro_list
        dro_to_text_data = {# specific DROs
            'Z Start Location'       : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_z_start_mill_depth_dro'],  'orig' : None , 'mod' : None },
                                        { 'proc': 'unpack_fp',    'ref':dros['dxf_z_mill_depth_dro'],        'orig' : None , 'mod' : None }),
            'Z Depth of Cut'         : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_z_slice_depth_dro'],       'orig' : None , 'mod' : None }),
            'X Offset'               : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_x_offset_dro'],            'orig' : None , 'mod' : None }),
            'Y Offset'               : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_y_offset_dro'],            'orig' : None , 'mod' : None }),
            'Scale'                  : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_scale_dro'],               'orig' : None , 'mod' : None }),
            'Rotation'               : ({ 'proc': 'unpack_fp',    'ref':dros['dxf_rotation_angle_dro'],      'orig' : None , 'mod' : None }),
            'Cutter Compensation'    : ({ 'proc': 'unpack_cmt',   'ref':self.ja_dxf_get_cutter_compensation, 'orig' : None , 'mod' : None }),
            'Layers'                 : ({ 'proc': 'unpack_cmt',   'ref':self.ja_dxf_get_enabled_layers,      'orig' : None , 'mod' : None }),
            'DXF File Path'          : ({ 'proc': 'unpack_cmt',   'ref':self.ja_dxf_get_file_path,           'orig' : None , 'mod' : None }),
            'Post Parse'             : ({ 'proc': self.ja_dxf_post_parse_z_depth, 'ref':None,                'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
            'focus'                  : ({ 'proc': None,           'ref':dros['dxf_z_start_mill_depth_dro'],     'ja_diff' : 'no' })
        }
        return self.gen_common_dro_dict(dro_to_text_data, 'DXF', ('Feed', 'Feed Rate'), ('Number of Z Passes', ))

    def generate_dxf_gcode(self, conv_dro_list, dxf_dro_list, dxf_panel):
        # empty python list for g code
        code = []

        ok = True

        if not dxf_panel.file_loaded:
            self.error_handler.write('Conversational DXF entry error - No DXF file loaded.')
            return False, ''

        # string variables
        title  = self.get_conv_title(conv_dro_list)

        # validate params (converts to float), assign to local variables, record error if validation fails
        def read_and_check(self, dro):
            valid, output, error =  self.validate_param(dro)
            if not valid:
                self.error_handler.write('Conversational DXF entry error - ' + error)
            return valid, output

        dros = {
            'work_offset': conv_dro_list['conv_work_offset_dro'],
            'tool_number': conv_dro_list['conv_tool_number_dro'],
            'rpm': conv_dro_list['conv_rpm_dro'],
            'feed': conv_dro_list['conv_feed_dro'],
            'z_feed': conv_dro_list['conv_z_feed_dro'],
            'z_clear': conv_dro_list['conv_z_clear_dro'],
            'z_start': dxf_dro_list['dxf_z_start_mill_depth_dro'],
            'z_doc': dxf_dro_list['dxf_z_slice_depth_dro'],
            'z_end': dxf_dro_list['dxf_z_mill_depth_dro'],
            'x_offset': dxf_dro_list['dxf_x_offset_dro'],
            'y_offset': dxf_dro_list['dxf_y_offset_dro'],
            'scale': dxf_dro_list['dxf_scale_dro'],
            'rotation': dxf_dro_list['dxf_rotation_angle_dro'],
        }
        data = {}

        for key in dros:
            valid, data[key] = read_and_check(self, dros[key])
            if not valid:
                return False, ''

        # g4x - from buttons
        cut_comp = dxf_panel.cutter_compensation
        cut_comp_text = {40: 'On', 41: 'Right', 42: 'Left'}
        # layer order and enabled - from treeview or layers
        enabled_layers = dxf_panel.enabled_layers
        dxf_file_path = dxf_panel.dxf_file_path

        is_metric, g20_g21, dro_fmt, feed_fmt, units, rate_units, round_off, blend_tol, naive_tol, ttable_conv = self.conv_data_common()

        # get tool information from linuxcnc.stat
        tool_dia = (self.status.tool_table[data['tool_number']].diameter) * ttable_conv

        # do logic validity checks here
        if data['z_end'] > data['z_start']:
            z_dir = 1
            ok = False
            error_msg = 'Conversational DXF error - Z Start must be larger than Z End'
            cparse.raise_alarm(dros['z_end'], error_msg)
            cparse.raise_alarm(dros['z_start'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''
        elif data['z_end'] < data['z_start']:
            z_dir = -1
        else:
            z_dir = 0
            ok = False
            error_msg = 'Conversational DXF error - Z range too small or bad Z entry value'
            cparse.raise_alarm(dros['z_end'], error_msg)
            cparse.raise_alarm(dros['z_start'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        if data['z_clear'] < data['z_start']:
            ok = False
            error_msg = 'Conversational DXF error - Z Start must be smaller than Z Clear '
            cparse.raise_alarm(dros['z_clear'], error_msg)
            cparse.raise_alarm(dros['z_start'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        z_range = math.fabs(data['z_end'] - data['z_start'])

        if data['z_doc'] > z_range + conversational.float_err:
            ok = False
            error_msg = "Conversational DXF error - Z Depth of Cut can not be bigger than the Z range of cut"
            cparse.raise_alarm(dros['z_start'], error_msg)
            cparse.raise_alarm(dros['z_end'], error_msg)
            cparse.raise_alarm(dros['z_doc'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return ok, ''

        # generation details
        dxf_op_string = 'DXF'
        self.__write_std_info(code, dxf_op_string, g20_g21, units, data['work_offset'],data['tool_number'], dro_fmt % tool_dia, data['rpm'])

        code.append('\n(DXF File Path = %s)' % dxf_file_path)
        code.append('(Cutter Compensation = %s)' % cut_comp_text[cut_comp])
        code += self.ja_dxf_convert_layers_to_code(enabled_layers)

        code.append('\n(Scale = %s)' % dro_fmt % data['scale'])
        code.append('(Rotation = %s)' % dro_fmt % data['rotation'])
        code.append('(X Offset = %s)' % dro_fmt % data['x_offset'])
        code.append('(Y Offset = %s)' % dro_fmt % data['y_offset'])

        code.append('\n(Z Clear Location = %s)' % dro_fmt % data['z_clear'])
        code.append('(Z Start Location = %s , End Location = %s)' % (dro_fmt, dro_fmt) % (data['z_start'], data['z_end']))
        code.append('(Z Depth of Cut = %s)' % dro_fmt % data['z_doc'])
        code.append('(Feed Rate = %s %s)' % (feed_fmt, rate_units) % data['feed'])
        code.append('(Z Feed Rate = %s %s)' % (feed_fmt, rate_units) % data['z_feed'])

        code.append(conversational.start_of_gcode)

        # prepare postprocessor configuration
        values = {}
        values['General/code_begin_header'] = '\n' # empty would insert default header
        values['General/code_begin_g5x'] = '%s (Set Work Offset)' % data['work_offset']
#        values['Program/feed_change'] = 'F%feed ' + '(Feed %s)' % rate_units + '%nl'

        values['General/code_begin'] = self.dxf_code_begin_block(dro_fmt, blend_tol, naive_tol)

        # note: we could set the fitting tolerance for dxf2gcode here

        # convert dxf file
        tempdir = tempfile.mkdtemp()
        output_filename = os.path.join(tempdir, '%s.nc' % title)
        path = dxf_panel.convert_dxf_file(output_filename, values)

        # read gcode
        with open(path, 'rt') as f:
            code += f.read().split('\n')
        os.remove(path)
        shutil.rmtree(tempdir)
        conversational_base.insert_conversational_end_tag(code, dxf_op_string)

        return ok, code

    def dxf_code_begin_block(self, dro_fmt, blend_tol, naive_tol):
        code_begin = 'G64 P %s Q %s (PathBleding)' % (dro_fmt, dro_fmt) % (blend_tol, naive_tol) + '%nl'
        code_begin += 'G17 (XY Plane)'
        return code_begin

    # ------------------------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------------------------
    def generate_scope_gcode(self, scope_liststore, conv_dro_list):
        print "gen scope g-code, ls = ", scope_liststore
        # empty python list for g code
        code = []

        ok = True

        # set the correct number of decimal places
        is_metric = self.status.gcodes[5] == 210

        if is_metric:
            g20_g21 = 'G21'
            dro_fmt = '%3.3f'
            feed_fmt = '%4.1f'
            units = 'mm'
            rate_units = 'mm/minute'
            ttt_units = 0
        else:
            g20_g21 = 'G20'
            dro_fmt = '%2.4f'
            feed_fmt = '%3.2f'
            units = 'inches'
            rate_units = 'inches/minute'
            ttt_units = 1

        # generation details
        code.append('(Mill - Scope G-code generated: %s)' % (time.asctime(time.localtime(time.time()))))
        code.append(conversational.conv_version_string())
        code.append('(Description = %s)' % conv_dro_list['conv_title_dro'].get_text())

        # list all parameters in output comments
        code.append('\n(Units = %s %s)' % (g20_g21, units))
        #code.append('(Work Offset = %s)' % work_offset)

        code.append('\nM30 (End of Program)\n')

        num_rows = len(scope_liststore)
        for i in range(num_rows):
            try:
                x_pos = float(scope_liststore[i][1])
            except:
                break
            try:
                y_pos = float(scope_liststore[i][2])
            except:
                break

            code.append('X %s Y %s' %
                        (dro_fmt, dro_fmt) %
                        (x_pos, y_pos))

        return ok, code


    # -------------------------------------------------------------------------------
    # End of g code generation routines
    # -------------------------------------------------------------------------------

    def validate_param(self, widget, is_metric=False, update_alarms=True):
        """ validate_param function provides a wrapper around the individual validate functions.
        This allows a single call to validate the contents of a gtk.entry widget, regardless of that
        widget's data type. """

        name = gtk.Buildable.get_name(widget)
        result = None
        if 'work_offset' in name:
            result = self.validate_work_offset(widget, is_metric)
        elif 'feed' in name:
            result = self.validate_feedrate(widget, is_metric)
        elif 'tool' in name:
            if 'spot_tool_doc' in name:
                result = self.validate_expr_no_zero_doc(widget, is_metric, 'Spot Tool Depth of Cut')
            else:
                result = self.validate_tool_number(widget)
        elif 'spindle_rpm' in name:
            result = self.validate_max_spindle_rpm(widget, is_metric)
        elif 'rpm' in name:
            result = self.validate_max_spindle_rpm(widget, is_metric)
        elif 'pattern_circular_dia' in name:
            result = self.validate_gt0(widget, is_metric, 'Diameter')
        elif 'circ_diameter' in name:
            result = self.validate_gt0(widget, is_metric, 'Diameter')
        elif 'dia' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Diameter')
        elif 'doc' in name:
            if 'thread_mill' in name:
                result = self.validate_expr_no_zero_doc(widget, is_metric, 'Thread Mill Depth of Cut')
            elif 'engrave_z_doc' in name:
                result = self.validate_expr_no_zero_doc(widget, is_metric, 'Engrave Z Depth of Cut')
            else:
                msg = 'Z DOC (Depth Of Cut)' if 'z_doc' in name else 'Depth Of Cut'
                result = self.validate_expr_doc(widget, is_metric, msg)
        elif '_clear_' in name:
            result = self.validate_doc(widget, is_metric)
        elif '_z_' in name:
            result = self.validate_z_point(widget)
        elif '_y_' in name:
            result = self.validate_y_point(widget)
        elif '_x_' in name:
            result = self.validate_x_point(widget)
        elif 'holes' in name:
            result = self.validate_num_passes(widget, is_metric)
        elif 'pattern_circular_start_angle' in name:
            result = self.validate_90_90_angle(widget)
        elif 'rotation_angle' in name:
            result = self.validate_any_angle(widget)
        elif 'angle' in name:
            result = self.validate_0_90_angle(widget)
        elif 'peck' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Peck')
        elif 'dwell' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Dwell')
        elif 'pitch' in name:
            result = self.validate_gt0(widget, is_metric, 'Pitch')
        elif 'tpu' in name:
            if is_metric:
                result = self.validate_gt0(widget, is_metric, 'Threads/mm')
            else:
                result = self.validate_gt0(widget, is_metric, 'Threads/inch')
        elif 'full_depth' in name:
            result = self.validate_gt0(widget, is_metric, 'Depth')
        elif 'radius' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Radius')
        elif 'num_holes' in name:
            result = self.validate_gt0(widget, is_metric, 'Number of Holes')
        elif 'scale' in name:
            result = self.validate_gt0(widget, is_metric, 'Scale')
        elif 'cut_fill' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Cut Fill')
        elif 'passes' in name:
            result = self.validate_gt0(widget, is_metric, 'Number of Passes')
        elif 'tolerance' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Tolerance')
        elif 'feature' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Feature')
        elif 'fov' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Field of View')
        elif 'stepover' in name:
            result = self.validate_gt_or_eq0(widget, is_metric, 'Stepover')
        elif 'height' in name:
            result = self.validate_gt0(widget, is_metric, 'Height')
        elif 'engrave_text' in name:
            result = self.accept_any_text(widget, is_metric)
        elif 'text' in name:
            result = self.validate_text(widget, is_metric)
        elif 'title' in name:
            result = self.validate_text(widget, is_metric)
        elif 'sn_start' in name:
            result = self.validate_serial_number(widget)

        if result is None or not update_alarms:
            #This seems really dangerous because most functions that call this method expect a 3-tuple back.
            # I'm hesitant to change it because something somewhere might rely on getting None back
            return result
        valid, value, error_msg = result
        if valid:
            cparse.clr_alarm(widget)
        else:
            cparse.raise_alarm(widget, error_msg)
        return result

    def validate_tool_number(self, widget, param=None):
        try:
            widget_text = widget.get_text()
            # the tool DRO is uninitialized during startup and tooltip validation
            if widget_text == '':
                return True, 0, ''
            tool_number = int(widget_text)
            if (0 <= tool_number <= MAX_NUM_MILL_TOOL_NUM):
                return True, tool_number, ''
            else:
                msg = 'Invalid tool number, must be within 1 to {:d}. Use tool 0 to indicate empty spindle.'.format(MAX_NUM_MILL_TOOL_NUM)
                return False, '', msg
        except ValueError:
            msg = 'Invalid tool number'
            return False, 0, msg

    def validate_surface_speed(self, widget, is_metric):
        (is_valid_number, surface_speed) = cparse.is_number_or_expression(widget)
        # TODO - range check.  Should incorporate g20/21 setting
        if (is_valid_number and (surface_speed > 0)):
            return True, surface_speed, ''
        else:
            msg = 'Invalid surface speed'
            return False, 0, msg

    def validate_feedrate(self, widget, is_metric):
        (is_valid_number, feedrate) = cparse.is_number_or_expression(widget)
        # TODO - range check, should incorporate g20/21 setting
        if (is_valid_number and (feedrate > 0)):
            return True, feedrate, ''
        else:
            msg = 'Invalid feedrate'
            return False, 0, msg

    def validate_max_spindle_rpm(self, widget,param=None):
        # use HAL to get current spindle comp status
        min_rpm = int(self.hal['spindle-min-speed'])
        max_rpm = int(self.hal['spindle-max-speed'])

        (is_valid_number, rpm) = cparse.is_number_or_expression(widget)
        if is_valid_number and (min_rpm <= rpm <= max_rpm or rpm == 0.0):
            return True, rpm, ''
        else:
            msg = 'Invalid RPM setting.  RPM must be between %d and %d in the current belt position.' % (min_rpm, max_rpm)
            return False, 0, msg

    def validate_dia_val(self, widget):
        (is_valid_number, diameter) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            return True, diameter, ''
        else:
            msg = 'Invalid diameter value'
            return False, 0, msg

    def validate_x_point(self, widget):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            return True, point, ''
        else:
            msg = 'Invalid X value'
            return False, 0, msg

    def validate_y_point(self, widget):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            return True, point, ''
        else:
            msg = 'Invalid Y value'
            return False, 0, msg

    def validate_z_point(self, widget):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            return True, point, ''
        else:
            msg = 'Invalid Z value'
            return False, 0, msg

    def validate_z_touch_val(self, widget):
        val = widget.get_text()
        (is_valid_number, z_point) = cparse.is_number(val)
        if (is_valid_number) or (val == ""):
            return True, z_point, ''
        else:
            msg = 'Invalid Z value'
            return False, 0, msg

    def validate_doc(self, widget, is_metric, msg = None):
        (is_valid_number, doc) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            return True, doc, ''
        else:
            msg = 'Invalid Z value'
            return False, 0, msg

    def validate_any_angle(self, widget, is_metric=False):
        (is_valid_number, angle) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            return True, angle, ''
        msg = 'Invalid angle'
        # if we fall through the above, raise an alarm.
        return False, 0, msg

    def validate_90_90_angle(self, widget, is_metric=False):
        (is_valid_number, angle) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            if (-90 < angle < 90):
                return True, angle, ''
        # if we fall through the above, raise an alarm.
        msg = 'Invalid angle, must be between to -90 and smaller than 90'
        return False, 0, msg

    def validate_0_90_angle(self, widget, is_metric=False):
        (is_valid_number, angle) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            if (0 < angle < 90):
                return True, angle, ''
        # if we fall through the above, raise an alarm.
        msg = 'Invalid angle, must be bigger than 0 and smaller than 90'
        return False, 0, msg

    def validate_peck(self, widget, is_metric=False):
        (is_valid_number, peck) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            if peck >= 0:
                return True, peck, ''
        # if we fall through the above, raise an alarm.
        msg = "Peck needs to be greater than or equal to 0"
        return False, 0, msg

    def validate_dwell(self, widget, is_metric=False):
        (is_valid_number, dwell) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            if dwell >= 0:
                return True, dwell, ''
        # if we fall through the above, raise an alarm.
        msg = "Dwell needs to be greater than or equal to 0"
        return False, 0, msg

    def validate_pitch(self, widget, is_metric=False):
        (is_valid_number, pitch) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            return True, pitch, ''
        # if we fall through the above, raise an alarm.
        else:
            msg = 'Invalid thread pitch'
            return False, 0, msg

    def validate_wear_offset(self, value, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number:
            return True, value, ''
        else:
            return False, 0, 'Invalid wear offset entry'

    def validate_tool_offset(self, value, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number:
            return True, value, ''
        else:
            return False, 0, 'Invalid tool offset entry'

    def validate_offset(self, value, offset, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if (is_valid_number):
            return True, value, ''
        else:
            return False, 0, 'Invalid %s offset entry' % offset

    def validate_drill_pos(self, value, col, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number:
            return True, value, ''
        else:
            return False, '', 'Invalid drill table %s entry' % col

    def validate_num_passes(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        value = int(value)
        if is_valid_number:
            if value > 0:
                return True, value, ''
        msg = "Number needs to be > 0"
        return False, 0, msg

    def validate_expr_doc(self, widget, is_metric=False, name = 'Z DOC'):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if is_valid_number:
            return True, value, ''
        msg = "%s does not evaluate to a valid number" % name
        return False, 0, msg

    def validate_expr_no_zero_doc(self, widget, is_metric=False, name = 'Z DOC'):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if is_valid_number and value != 0:
            return True, value, ''
        if is_valid_number:
            msg = "Zero depth of cut not allowed in this context"
        else:
            msg = "%s does not evaluate to a valid number" % name
        return False, 0, msg


    def validate_gt0(self, widget, is_metric=False, name = 'Number'):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if is_valid_number:
            if value > 0:
                return True, value, ''
        msg = "%s needs to be greater than 0" % name
        return False, 0, msg

    def validate_gt_or_eq0(self, widget, is_metric=False, name = 'Number'):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if is_valid_number:
            if value >= 0:
                return True, value, ''
        msg = "%s needs to be greater than or equal to 0" % name
        return False, 0, msg

    def validate_serial_number(self, widget):
        # serial number is kept as a string to preserve leading zeros
        # It is evaluated as an int, however returned as a string
        if widget.get_text() == '':
            return True, None, ''

        try:
            sn_text = widget.get_text()
            serial_number = int(sn_text)
            if serial_number >= 0:
                return True, sn_text, ''
            else:
                msg = 'Invalid serial number - serial number must be positive'
                return False, None, msg
        except ValueError:
            msg = 'Invalid serial number'
            return False, None, msg

    def validate_text(self, widget, is_metric = False):
        (is_valid_text, text) = cparse.is_text(widget.get_text())
        if is_valid_text:
            return True, text, ''
        msg = "No text was entered"
        return False, 0, msg

    def accept_any_text(self, widget, is_metric = False):
        text = widget.get_text()
        if len(text) == 0:
            return True, None, ''
        else:
            return self.validate_text(widget)
#---------------------------------------------------------------------------------------------------
# Parse conventional gcode
#---------------------------------------------------------------------------------------------------

    def parse_non_conversational_mill_gcode(self, conv_decomp, gcode):
        return self.parse_non_conversational_gcode('Mill', conv_decomp, gcode)

