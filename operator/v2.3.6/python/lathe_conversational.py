# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

#
# Module for G-code generator and parameter validation for conversational routines
#

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import time
import sys
import gtk
import math
import json
from constants import *
from errors import *
from math import *
from conversational import *
import operator
import traceback
import linuxcnc
import lathe_conv_support
import os

#---------------------------------------------------------------------------------------------------
# global
#---------------------------------------------------------------------------------------------------
def get_tool_orientation_image(orientation): return 'orientation_'+str(orientation)+'.png'

#---------------------------------------------------------------------------------------------------
# class MCodes - allows for the substitution of Mcodes by extended MCodes
# example: M8 -> M8 M64 Px
#---------------------------------------------------------------------------------------------------
class MCodes():
    def __init__(self, ui):
        self.ui = ui
        self.codes = None
        path = os.path.join(RES_DIR, 'GMCodes.json')
        if os.path.exists(path) and os.path.isfile(path):
            try:
                with open(path) as datafile:
                    self.codes = json.load(datafile)['lathe']
            except:
                self.ui.error_handler.log('I/O error: {0}'.format(sys.exc_info()[0]))

    def __get_string(self, code, tn):
        if self.codes:
            items =  self.codes['MCodes'][code]
            _tn = 'T{:d}'.format(tn)
            if _tn in items:
                return items[_tn]
        return code

    def M8(self, tn):
        return self.__get_string('M8',tn)

    def M9(self, tn):
        return self.__get_string('M9',tn)


#---------------------------------------------------------------------------------------------------
# class conversational
#---------------------------------------------------------------------------------------------------

class conversational(conversational_base):

    #rountine names are dictionary of conversational routines mapped to
    #routine data 'factories'
    routine_names = { 'conversational' : 'Lathe',
                      'routines' :      {'ExternalCode'           : {'pack':'gen_external_code_dict',       'conv':None,                         'edit':None,                  'restore':'ja_revert_to_was'},
                                         'OD Turn'                : {'pack':'gen_od_turn_dro_dict',         'conv':list(('od_turn_fixed',)),     'edit':'ja_edit_od_turn',     'restore':'ja_revert_to_was'},
                                         'ID Basic'               : {'pack':'gen_id_basic_dro_dict',        'conv':list(('id_turn_fixed',)),     'edit':'ja_edit_id',          'restore':'ja_revert_to_was'},
                                         'ID Extended'            : {'pack':'gen_id_turn_dro_dict',         'conv':list(('id_turn_fixed',)),     'edit':'ja_edit_id',          'restore':'ja_revert_to_was'},
                                         'External Profiling'     : {'pack':'gen_external_profile_dro_dict','conv':list(('profile_fixed',)),     'edit':'ja_edit_profile',     'restore':'ja_revert_to_was'},
                                         'Internal Profiling'     : {'pack':'gen_internal_profile_dro_dict','conv':list(('profile_fixed',)),     'edit':'ja_edit_profile',     'restore':'ja_revert_to_was'},
                                         'Facing'                 : {'pack':'gen_face_dro_dict',            'conv':list(('face_fixed',)),        'edit':'ja_edit_face',        'restore':'ja_revert_to_was'},
                                         'Chamfer'                : {'pack':'gen_chamfer_dro_dict',         'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'External Chamfer'       : {'pack':'gen_chamfer_dro_dict',         'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'Internal Chamfer'       : {'pack':'gen_chamfer_interal_dro_dict', 'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'Corner Radius'          : {'pack':'gen_radius_dro_dict',          'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'External Corner Radius' : {'pack':'gen_radius_dro_dict',          'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'Internal Corner Radius' : {'pack':'gen_radius_internal_dro_dict', 'conv':list(('chamfer_fixed',)),     'edit':'ja_edit_chamfer',     'restore':'ja_revert_to_was'},
                                         'Parting'                : {'pack':'gen_parting_dro_dict',         'conv':list(('groove_part_fixed',)), 'edit':'ja_edit_groove_part', 'restore':'ja_revert_to_was'},
                                         'Groove'                 : {'pack':'gen_grooving_dro_dict',        'conv':list(('groove_part_fixed',)), 'edit':'ja_edit_groove_part', 'restore':'ja_revert_to_was'},
                                         'Drilling'               : {'pack':'gen_drilling_dro_dict',        'conv':list(('drill_tap_fixed',)),   'edit':'ja_edit_drilltap',    'restore':'ja_revert_to_was'},
                                         'Tapping'                : {'pack':'gen_tap_dro_dict',             'conv':list(('drill_tap_fixed',)),   'edit':'ja_edit_drilltap',    'restore':'ja_revert_to_was'},
                                         'Threading'              : {'pack':'gen_external_thread_dro_dict', 'conv':list(('thread_fixed',)),      'edit':'ja_edit_thread',      'restore':'ja_revert_to_was'},
                                         'External Threading'     : {'pack':'gen_external_thread_dro_dict', 'conv':list(('thread_fixed',)),      'edit':'ja_edit_thread',      'restore':'ja_revert_to_was'},
                                         'Internal Threading'     : {'pack':'gen_internal_thread_dro_dict', 'conv':list(('thread_fixed',)),      'edit':'ja_edit_thread',      'restore':'ja_revert_to_was'}
                                        },
                      'parsing' :       { 'CAM' : 'parse_non_conversational_lathe_gcode'}
                    }
    icon_data = dict(
        drill_icon =       dict(icon_file = 'icon_lathe_drill_norm.31.png', icon = None),
        face_icon =        dict(icon_file = 'icon_face.31.png',             icon = None),
        odturn_icon =      dict(icon_file = 'icon_od_turn.31.png',          icon = None),
        parting_icon =     dict(icon_file = 'icon_parting.31.png',          icon = None),
        boring_icon =      dict(icon_file = 'icon_boring.31.png',           icon = None),
        int_thread_icon =  dict(icon_file = 'icon_int_thread.31.png',       icon = None),
        ext_thread_icon =  dict(icon_file = 'icon_ext_thread.31.png',       icon = None),
        tapping_icon =     dict(icon_file = 'icon_tapping.31.png',          icon = None),
        )

    title_data = { 'od_turn_fixed'     :{'ref0':'conv_od_basic_ext',       'basic'    :('lathe_od_basic_title','odTurning'),                'extended':('lathe_od_extended_title','odExtendedTurning')},
                   'id_turn_fixed'     :{'ref0':'conv_id_basic_ext',       'basic'    :('lathe_id_basic_title','idBasicTurning'),           'extended':('lathe_id_extended_title','idExtendedTurning')},
                   'profile_fixed'     :{'ref0':'conv_profile_ext',        'external' :('lathe_external_profile_title','externalProfile'),  'internal':('lathe_internal_profile_title','internalProfile')},
                   'face_fixed'        :{'ref0':'conv_face_basic_ext',     'basic'    :('lathe_face_basic_title','facing'),                 'extended':('lathe_face_extended_title','facingExtended')},
                   'chamfer_fixed'     :{'ref0':'conv_chamfer_radius',     'chamfer'  :('lathe_chamfer_','chamfer'),                        'radius'  :('lathe_radius_','radius'),
                                         'ref1':'conv_chamfer_od_id',      'od'       :('od_title','Od'),                                   'id'      :('id_title','Id')},
                   'groove_part_fixed' :{'ref0':'conv_groove_part',        'groove'   :('lathe_groove_title','grooving'),                   'part'    :('lathe_parting_title','parting')},
                   'drill_tap_fixed'   :{'ref0':'conv_drill_tap',          'drill'    :('lathe_drill_title','drill'),                       'tap'     :('lathe_tapping_title','tap')},
                   'thread_fixed'      :{'ref0':'conv_thread_ext_int',     'external' :('lathe_external_thread_title','externalThreading'), 'internal':('lathe_internal_thread_title','internalThreading')}
                 }

    G20_data = { 'css_units': 'feet/minute' }
    G21_data = { 'css_units': 'meters/minute' }

    _mcodes = None

    # used for validate_spindle_rpm
    local_min_rpm = 0
    local_max_rpm = 0

    def __init__(self, ui_base, status, error_handler, redis, hal):
        super(conversational, self).__init__(ui_base, status, error_handler, redis, hal)
        conversational_base.routine_names = conversational.routine_names
        conversational_base.conversational_type = "Lathe"

    # ------------------------------------------------------------------------------------
    # Common - DRO set
    # ------------------------------------------------------------------------------------
    def gen_common_dro_dict(self, specific, title, swaps=None, rm=None):
       # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        mat_packer = getattr(self.ui.material_data,'conversational_text')
        dro_to_text_data = { 'title'                : ({ 'proc': 'unpack_title',     'ref':'(%s' % title,                      'orig' : None , 'mod' : None }),
                             'Description'          : ({ 'proc': 'unpack_cmt',       'ref':cdl['conv_title_dro'],           'orig' : None , 'mod' : None }),
                             'Units'                : ({ 'proc': 'unpack_units',     'ref':('mm','inches'),                 'orig' : None , 'mod' : None }),
                             'CSS Max. Spindle RPM' : ({ 'proc': 'unpack_fp',        'ref':cdl['conv_max_spindle_rpm_dro'], 'orig' : None , 'mod' : None }),
                             'Work Offset'          : ({ 'proc': 'unpack_wo',        'ref':cdl['conv_work_offset_dro'],     'orig' : None , 'mod' : None }),
                             'Tool Type'            : ({ 'proc': 'unpack_str',       'ref':None,                            'orig' : None , 'mod' : None }),
                             'Tool Orientation'     : ({ 'proc': 'unpack_to',        'ref':None,                            'orig' : None , 'mod' : None }),
                             'Tool Radius'          : ({ 'proc': 'unpack_fp',        'ref':None,                            'orig' : None , 'mod' : None }),
                             'Rough CSS'            : ({ 'proc': 'unpack_fp',        'ref':cdl['conv_rough_sfm_dro'],       'orig' : None , 'mod' : None }),
                             'Rough Feed'           : ({ 'proc': 'unpack_fp',        'ref':cdl['conv_rough_fpr_dro'],       'orig' : None , 'mod' : None }),
                             'Finish CSS'           : ({ 'proc': 'unpack_fp',        'ref':cdl['conv_finish_sfm_dro'],      'orig' : None , 'mod' : None }),
                             'Finish Feed'          : ({ 'proc': 'unpack_fp',        'ref':cdl['conv_finish_fpr_dro'],      'orig' : None , 'mod' : None }),
                             'Material'             : ({ 'proc': 'unpack_clean_str', 'ref':mat_packer,                      'orig' : None , 'mod' : None })
                            }
        rv = dro_to_text_data.copy()
        # do fixups for minor variations in keys
        # swap replaces tup[0], tup[1] .. or tup[0]<-tup[1]
        if swaps is not None and isinstance(swaps,tuple):
            l = len(swaps)
            for n in range(0,l,2):
                rv[swaps[n+1]] = rv.pop(swaps[n])
        if rm is not None:
            for item in rm:
                rv.pop(item)
        rv.update(specific.copy())
        return rv



    def __write_std_info(self, code, title, g20_g21, units, work_offset, tn, tr=None, rpm=None, axial=False):
        # this method is intended to be 'private' this derived 'conversaitonal' class -and- NOT
        # be used outside of the 'lathe' context.
        tool_description = self.ui.get_tool_description(tn)
        code.append('(%s G-code generated: %s )' % (title, time.asctime(time.localtime(time.time()))))
        code.append(conversational.conv_version_string())
        code.append('(Description = %s)' % self.ui.conv_dro_list['conv_title_dro'].get_text())
        code.append('(Material = %s)' % self.ui.material_data.get_conversational_text())

        # list all parameters in output comments
        code.append('\n(Units = %s %s)' % (g20_g21, units))
        code.append('(Work Offset = %s)' % work_offset)
        if rpm is not None: code.append('\n(CSS Max. Spindle RPM = %d)' % rpm)
        code.append('(Tool Number = %d)' % tn)
        code.append('(Tool Description = %s)'%tool_description)
        code.append('(Tool Type = ' + self.get_tool_type(tn) + ')')
        code.append('(Tool Orientation = %d)' % self.status.tool_table[tn].orientation)
        if tr is not None:
            if not axial:
                code.append('(Tool Radius = %.4f)' % tr)
            else:
                code.append('(Tool Diameter = %.4f)' % (tr*2.0))

    def conv_data_common(self, tool_number=None, report='all'):
        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210
        if report == 'metric': return is_metric
        dat_comm = conversational_base._g21_data if is_metric else conversational_base._g20_data
        dat_tool = conversational.G21_data       if is_metric else conversational.G20_data
        if report == 'formats' : return (dat_comm['dro_fmt'], dat_comm['feed_fmt'])
        if report == 'convert' : return (is_metric, dat_comm['units'], dat_tool['css_units'], dat_comm['ttable_conv'])
        if report == 'convert_dimension' : return (is_metric, dat_comm['dro_fmt'], dat_comm['units'], dat_comm['ttable_conv'])
        tool_radius = ((self.status.tool_table[tool_number].diameter * dat_comm['ttable_conv']) / 2.0) if tool_number else 0.0
        return (is_metric, \
            dat_comm['gcode'], \
            dat_comm['dro_fmt'],
            dat_comm['feed_fmt'], \
            dat_comm['units'], \
            dat_tool['css_units'], \
            dat_comm['round_off'], \
            tool_radius)

    def _tool_side_msg(self, dir):
        return '(Tool on X%s side)' % ('-' if dir < 0 else '+')
    # ------------------------------------------------------------------------------------
    # Common - strings
    # ------------------------------------------------------------------------------------
    def _coolant_on(self, tool_number):
        if not self.__class__._mcodes: self.__class__._mcodes = MCodes(self.ui)
        return self.__class__._mcodes.M8(tool_number)

    def _coolant_off(self, tool_number):
        if not self.__class__._mcodes: self.__class__._mcodes = MCodes(self.ui)
        return self.__class__._mcodes.M9(tool_number)

    # ------------------------------------------------------------------------------------
    # OD Turning code
    # ------------------------------------------------------------------------------------

    def ja_edit_od_turn(self, routine_data):
        return self.ja_edit_general(routine_data)


    def gen_od_turn_dro_dict(self):
        # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        odl = self.ui.od_turn_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'          : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_tool_num_dro'],     'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'   : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_rough_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'  : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_finish_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Initial Diameter'     : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_stock_dia_dro'],    'orig' : None , 'mod' : None }),
                             'Final Diameter'       : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_final_dia_dro'],    'orig' : None , 'mod' : None }),
                             'Z Start Location'     : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_z_start_dro'],      'orig' : None , 'mod' : None }),
                             'Z End Location'       : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Fillet Radius'        : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_fillet_dro'],       'orig' : None , 'mod' : None }),
                             'Tool Clearance'       : ({ 'proc': 'unpack_fp',    'ref':odl['od_turn_tc_dro'],           'orig' : None , 'mod' : None }),
                             'focus'                : ({ 'proc': None,           'ref':odl['od_turn_tool_num_dro'],     'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'OD Turn')


    def generate_od_turn_code(self, conv_dro_list, od_turn_dro_list):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        od_turn_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # boolean to indicate errors present
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)


        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, tool_number, error =  self.validate_param(od_turn_dro_list['od_turn_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, initial_diameter, error =  self.validate_param(od_turn_dro_list['od_turn_stock_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, final_diameter, error =  self.validate_param(od_turn_dro_list['od_turn_final_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, z_start, error =  self.validate_param(od_turn_dro_list['od_turn_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, z_end, error =  self.validate_param(od_turn_dro_list['od_turn_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, rough_doc, error  =  self.validate_param(od_turn_dro_list['od_turn_rough_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, finish_doc, error  =  self.validate_param(od_turn_dro_list['od_turn_finish_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, tool_clearance, error  =  self.validate_param(od_turn_dro_list['od_turn_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False
        valid, fillet_radius, error  =  self.validate_param(od_turn_dro_list['od_turn_fillet_dro'])
        if not valid:
            self.error_handler.write('Conversational OD entry error - ' + error)
            ok = False

        # negative allowed .. make these positive
        rough_doc = math.fabs(rough_doc)
        finish_doc = math.fabs(finish_doc)

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius  = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # generation details
        self.__write_std_info(code, 'OD Turn', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(Rough Depth of Cut = %.4f)' % rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Initial Diameter = %.4f)' % initial_diameter)
        code.append('(Final Diameter = %.4f)' % final_diameter)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End  Location = %.4f)' % z_end)
        code.append('(Fillet Radius = %.4f)' % fillet_radius)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        x_start = initial_diameter / 2
        x_finish = final_diameter / 2
        x_range = x_start - x_finish

        if x_start > x_finish and x_finish > 0:
            x_side = 1
            g2 = 'G2'
            g3 = 'G3'
            code.append(self._tool_side_msg(x_side))
        elif x_start < x_finish and x_finish < 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
            g2 = 'G3'
            g3 = 'G2'
        else:
            g2 = 'G?'
            g3 = g2
            x_side = 0
            msg = 'Conversational OD entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_stock_dia_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_final_dia_dro'], msg)
            return False, ''

        z_range = z_start - z_end
        # Feeds cut and places fillet and face towards spindle
        if z_start > z_end:
            z_side = 1
        # Feeds cut and fillet and face away from spindle
        # Should we allow it?
        #elif z_start < z_finish:
        #    z_side = -1
        else:
            z_side = 0
            msg = 'Conversational OD entry error - Z start not larger than Z end'
            self.error_handler.write(msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_z_start_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_z_end_dro'], msg)
            return False, ''

        if x_side > 0 and z_side > 0:  # tool orientation should be 2
            expected_tool_orientation = 2
        elif x_side > 0 and z_side < 0:  # tool orientation should be 1
            expected_tool_orientation = 1
        elif x_side < 0 and z_side > 0:  # tool orientation should be 3
            expected_tool_orientation = 3
        elif x_side < 0 and z_side < 0:  # tool orientation should be 4
            expected_tool_orientation = 4
        else :
            expected_tool_orientation = 0

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            error_msg = 'The X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(od_turn_dro_list['od_turn_final_dia_dro'], error_msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_stock_dia_dro'], error_msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_tool_num_dro'], error_msg)
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational OD entry error - Tool Orientation')
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the OD turn conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        # check that corner radius fits fully within x_range and z_range
        if fillet_radius > math.fabs(x_range):
            msg = 'Conversational OD entry error - Fillet radius must fit within Initial X and Final X'
            self.error_handler.write(msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_final_dia_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_stock_dia_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_fillet_dro'], msg)
            return False, ''

        if fillet_radius > math.fabs(z_range):
            msg = 'Conversational OD entry error - Fillet radius must fit within Z Start and Z End'
            self.error_handler.write(msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_z_start_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_z_end_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_fillet_dro'], msg)
            return False, ''


        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        xr_range = round(math.fabs(x_start - x_finish) - finish_doc, 4)
        if rough_doc == 0:
            num_rcuts = 0
            rough_DoC_adjusted = 0
        elif xr_range >= 0:
            num_rcuts = int(xr_range / rough_doc) + 1
            rough_DoC_adjusted = (xr_range / num_rcuts)
        else:
            num_rcuts = 0
            rough_DoC_adjusted = 0
            msg = 'Conversational OD entry error - Finish DoC too big or X dia. range too small'
            self.error_handler.write(msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_finish_doc_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_stock_dia_dro'], msg)
            cparse.raise_alarm(od_turn_dro_list['od_turn_final_dia_dro'], msg)
            return False, ''

        code.append('\n(Number of roughing passes = %d)' % num_rcuts)
        code.append('(Adjusted roughing DoC = %s)' % dro_fmt % rough_DoC_adjusted)

        x_fillet_center = x_finish + (x_side * fillet_radius)
        z_fillet_center = z_end + (z_side * fillet_radius)
        z_rough = z_end + finish_doc
        fillet_radius_rough = fillet_radius - finish_doc

        # Rapid to Start, first in X ,then Z
        code.append('\nG0 X %s' % dro_fmt % (2 * (x_start + (x_side * tool_clearance))))
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        x_previous = x_start
        z_previous = z_rough
        z_current = z_rough
        lcnt = 1
        while lcnt <= num_rcuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(Pass %d)' % lcnt)
            # Rapid to next X (tool should be at start of Z = at face + tc)
            x_current = (x_start - (x_side * rough_DoC_adjusted * lcnt))
            code.append('G0 X %s' % dro_fmt % (2 * x_current))
            # Run Z to z_end face and accounting for the finish doc
            if math.fabs(x_current) >= math.fabs(x_finish + (x_side * fillet_radius)):
                # We haven't gotten to the fillet yet so go to full rough width
                code.append('G1 Z %s' % dro_fmt % z_rough)
                # Retract
                code.append('G1 X %s' % dro_fmt % (2 * x_previous))

            else:
                # Run Z to intersection of Z move and fillet arc, then up the arc
                # r^2 = x^2 + y^2, z = sqrt(x^2 - r^2)
                z_delta = math.sqrt(math.fabs((fillet_radius_rough ** 2) - ((x_fillet_center - x_current) ** 2)))
                z_current = z_fillet_center - z_delta
                code.append('G1 Z %s' % dro_fmt % z_current)
                # Retract (temp, should follow rough fillet but this is close)
                code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) % ((2 * x_previous), (z_previous)))

            # Rapid to starting Z
            code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

            x_previous = x_current
            z_previous = z_current
            lcnt += 1

        # feed finish cut
        code.append('\n(Set Finishing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\n(Finish Pass %d)' % lcnt)
        code.append('G0 X %s' % dro_fmt % final_diameter)

        if fillet_radius > tool_radius:
            code.append('G1 Z %s' % dro_fmt % z_fillet_center)
            x_mid_delta = math.sqrt((fillet_radius ** 2) / 2)
            code.append((g2 + ' X %s Z %s I %s K %s') %
                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                        ((2 * (x_fillet_center - (x_side * x_mid_delta))),
                         (z_fillet_center - x_mid_delta),
                         (x_side * fillet_radius),
                         0))
        else:
            code.append('G1 Z %s' % dro_fmt % z_end)
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((2 * (x_finish + (x_side * tool_clearance))) ,z_end + (z_side * tool_clearance)))

        code.append('G0 X %s' % dro_fmt % (2 * (x_start + (x_side * tool_clearance))))
        code.append('G0 Z %s' % dro_fmt % z_end)

        if fillet_radius > tool_radius:
            code.append('G1 X %s' % dro_fmt % (2 * x_fillet_center))
            code.append((g3 + ' X %s Z %s I %s K %s') %
                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                        (final_diameter,      # destination X
                         z_fillet_center,     # destination Z
                         0,          # offset of center from starting location
                         fillet_radius))
        else:
            code.append('G1 X %s' % dro_fmt % (2 * x_finish))

        # rapid to starting position - including clearance
        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) % (2 * (x_start + (x_side * tool_clearance)), (z_start + tool_clearance)))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'OD Turn')

        return ok, code

    # ------------------------------------------------------------------------------------
    # ID Turning code
    # ------------------------------------------------------------------------------------
    def ja_edit_id(self, routine_data):
        restore_data = dict(
            basic_extended = 'basic' if self.ui.conv_id_basic_ext == 'basic' else 'extended',
            disable_button = self.ui.button_list['id_basic_extended'],
            toggle_proc = getattr(self.ui,'toggle_id_basic_extended_button'),
            restore_proc = getattr(self, 'ja_restore_id_page')
        )
        self.ui.conv_id_basic_ext = 'basic' if 'Fillet Radius' in routine_data['segment data'] else 'extended'
        restore_data['toggle_proc']()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_id_page(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.conv_id_basic_ext = 'extended' if restore_data['basic_extended'] == 'basic' else 'basic'
        restore_data['toggle_proc']()

    def gen_id_basic_dro_dict(self):
        # ui is a base class attribute
        idl = self.ui.id_basic_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'             : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_tool_num_dro'],    'orig' : None , 'mod' : None }),
                             'ID roughing depth of cut': ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_rough_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'     : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_finish_doc_dro'],  'orig' : None , 'mod' : None }),
                             'Initial Diameter'        : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_pilot_dia_dro'],   'orig' : None , 'mod' : None }),
                             'Final Diameter'          : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_final_dia_dro'],   'orig' : None , 'mod' : None }),
                             'Z Start Location'        : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_z_start_dro'],     'orig' : None , 'mod' : None }),
                             'Z End Location'          : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_z_end_dro'],       'orig' : None , 'mod' : None }),
                             'Tool Clearance'          : ({ 'proc': 'unpack_fp',    'ref':idl['id_basic_tc_dro'],          'orig' : None , 'mod' : None }),
                             'revert'                  : ({ 'attr': 'conv_id_basic_ext','ref':'basic',                     'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                   : ({ 'proc': None,           'ref':idl['id_basic_tool_num_dro'],    'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'ID Basic')

    # ID Basic
    def generate_id_basic_code(self, conv_dro_list, id_basic_dro_list):
        """generate_id_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        id_turn_dro_list is a list of gtk.entry widgets that contain values specific to id turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(id_basic_dro_list['id_basic_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(id_basic_dro_list['id_basic_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, z_end, error =  self.validate_param(id_basic_dro_list['id_basic_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, final_diameter, error =  self.validate_param(id_basic_dro_list['id_basic_final_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, initial_diameter, error =  self.validate_param(id_basic_dro_list['id_basic_pilot_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, id_rough_doc, error  =  self.validate_param(id_basic_dro_list['id_basic_rough_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, finish_doc, error  =  self.validate_param(id_basic_dro_list['id_basic_finish_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(id_basic_dro_list['id_basic_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Basic entry error - ' + error)
            ok = False

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # generation details
        self.__write_std_info(code, 'ID Basic', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(ID roughing depth of cut = %.4f)' % id_rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Initial Diameter = %.4f)' % initial_diameter)
        code.append('(Final Diameter = %.4f)' % final_diameter)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End  Location = %.4f)' % z_end)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)


        # Convert diameters to radii
        x_start = initial_diameter / 2
        x_finish = final_diameter / 2

        # Set tool working side context
        if x_start < x_finish and x_start > 0:
            x_side = 1
            g2 = 'G2'
            g3 = 'G3'
            code.append(self._tool_side_msg(x_side))
        elif x_start > x_finish and x_start < 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
            g2 = 'G3'
            g3 = 'G2'
        else:
            g2 = 'G?'
            g3 = g2
            x_side = 0
            msg = 'Conversational ID Basic entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_pilot_dia_dro'], msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_final_dia_dro'], msg)
            return False, ''

        if z_start > z_end:
            z_side = 1
        #elif z_start < z_finish:
        #    z_side = -1
        else:
            z_side = 0
            msg = 'Conversational ID Basic entry error - Z start not larger than Z end'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_z_start_dro'], msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_z_end_dro'], msg)
            return False, ''

        if x_side > 0 and z_side > 0:  # tool orientation should be 3
            expected_tool_orientation = 3
        elif x_side > 0 and z_side < 0:  # tool orientation should be 4
            expected_tool_orientation = 4
        elif x_side < 0 and z_side > 0:  # tool orientation should be 2
            expected_tool_orientation = 2
        elif x_side < 0 and z_side < 0:  # tool orientation should be 1
            expected_tool_orientation = 1
        else :
            expected_tool_orientation = 0

        if tool_orientation != expected_tool_orientation:
            error_msg = "The X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s" % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(id_basic_dro_list['id_basic_pilot_dia_dro'], error_msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_final_dia_dro'], error_msg)
            cparse.raise_alarm(id_basic_dro_list['id_basic_tool_num_dro'], error_msg)
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write("Conversational ID Basic entry error - Tool Orientation")
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the ID turn conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # ID range
        id_range = round(math.fabs(x_finish - x_start) - finish_doc, 4)
        if id_rough_doc == 0:
            num_id_cuts = 0
            id_rough_doc_adjusted = 0
        elif id_range >= 0:
            num_id_cuts = int(id_range / id_rough_doc) + 1
            id_rough_doc_adjusted = (id_range / num_id_cuts)
        else:
            num_id_cuts = 0
            id_rough_doc_adjusted = 0
            self.error_handler.write('Conversational ID entry error - Finish DoC too big or X dia. range too small')
            return False, ''

        code.append('\n(ID Range = %s)' % dro_fmt % id_range)
        code.append('(Number of roughing passes = %d)' % (num_id_cuts))
        code.append('(Adjusted ID roughing DoC = %s)' % dro_fmt % id_rough_doc_adjusted)

        # Rapid to start
        code.append('\nG0 X %s' % dro_fmt % (2 * (x_start - (x_side * tool_clearance))))
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        x_previous = x_start
        x_current = x_start
        z_previous = 0
        z_current = 0

        # ##### ID Roughing

        id_count = 1
        while id_count <= num_id_cuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(ID %d)' % id_count)
            x_previous = (x_start + (x_side * id_rough_doc_adjusted * (id_count - 1)))
            x_current = (x_start + (x_side * id_rough_doc_adjusted * id_count))
            # rapid X one DoC increment
            code.append('G0 X %s' % dro_fmt % (2 * x_current))
            # feed Z to Z_End
            code.append('G1 Z %s' % dro_fmt % z_end)
            # feed X back to previous X
            code.append('G1 X %s' % dro_fmt % (2 * x_previous))
            # Rapid to starting Z
            code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

            id_count += 1
            # ID roughing loop return


        # ##### Finish Pass
        code.append('\n(Set Finishing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    (2 * (x_finish - (x_side * finish_doc)), z_start + tool_clearance))
        code.append('G1 X %s' % dro_fmt % final_diameter)
        code.append('G1 Z %s' % dro_fmt % z_end)
        code.append('G1 X %s' % dro_fmt % (2 * (x_finish - (x_side * finish_doc))))
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        # rapid to starting position - including clearance
        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    (initial_diameter - (x_side * tool_clearance), z_start + tool_clearance))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'ID Turn')

        return ok, code

#---------------------------------------------------------------------------------------------------
# ID Turn
#---------------------------------------------------------------------------------------------------

    def gen_id_turn_dro_dict(self):
        # ui is a base class attribute
        idl = self.ui.id_turn_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_tool_num_dro'],     'orig' : None , 'mod' : None }),
                             'ID roughing depth of cut' : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_rough_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_finish_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Initial Diameter'         : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_pilot_dia_dro'],    'orig' : None , 'mod' : None }),
                             'Final Diameter'           : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_final_dia_dro'],    'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_z_start_dro'],      'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Pilot End Location'       : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_pilot_dro'],        'orig' : None , 'mod' : None }),
                             'Fillet Radius'            : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_fillet_dro'],       'orig' : None , 'mod' : None }),
                             'Facing rough depth of cut': ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_face_doc_dro'],     'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':idl['id_turn_tc_dro'],           'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_id_basic_ext','ref':'extended',                  'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                    : ({ 'proc': None,           'ref':idl['id_turn_tool_num_dro'],     'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'ID Extended')

    # ID turn with extended features
    def generate_id_turn_code(self, conv_dro_list, id_turn_dro_list):
        """generate_id_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        id_turn_dro_list is a list of gtk.entry widgets that contain values specific to id turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True


        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)


        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(id_turn_dro_list['id_turn_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, initial_diameter, error =  self.validate_param(id_turn_dro_list['id_turn_pilot_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, final_diameter, error =  self.validate_param(id_turn_dro_list['id_turn_final_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(id_turn_dro_list['id_turn_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, z_end, error =  self.validate_param(id_turn_dro_list['id_turn_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, id_rough_doc, error  =  self.validate_param(id_turn_dro_list['id_turn_rough_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, finish_doc, error  =  self.validate_param(id_turn_dro_list['id_turn_finish_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(id_turn_dro_list['id_turn_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, fillet_radius, error  =  self.validate_param(id_turn_dro_list['id_turn_fillet_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, face_rough_doc, error  =  self.validate_param(id_turn_dro_list['id_turn_face_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        valid, pilot_end, error  =  self.validate_param(id_turn_dro_list['id_turn_pilot_dro'])
        if not valid:
            self.error_handler.write('Conversational ID Extended entry error - ' + error)
            ok = False

        # negative allowed .. make these positive
        face_rough_doc = math.fabs(face_rough_doc)
        id_rough_doc = math.fabs(id_rough_doc)
        finish_doc = math.fabs(finish_doc)

        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # generation details
        self.__write_std_info(code, 'ID Extended', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(ID roughing depth of cut = %.4f)' % id_rough_doc)
        code.append('(Facing rough depth of cut = %.4f)' % face_rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Initial Diameter = %.4f)' % initial_diameter)
        code.append('(Final Diameter = %.4f)' % final_diameter)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End  Location = %.4f)' % z_end)
        code.append('(Pilot End Location = %.4f)' % pilot_end)
        code.append('(Fillet Radius = %.4f)' % fillet_radius)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)


        # Convert diameters to radii
        x_start = initial_diameter / 2
        x_finish = final_diameter / 2

        # Set tool working side context
        if x_start < x_finish and x_start > 0:
            x_side = 1
            g2 = 'G2'
            g3 = 'G3'
            code.append(self._tool_side_msg(x_side))
        elif x_start > x_finish and x_start < 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
            g2 = 'G3'
            g3 = 'G2'
        else:
            g2 = 'G?'
            g3 = g2
            x_side = 0
            msg = 'Conversational ID Extended entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_pilot_dia_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_final_dia_dro'], msg)
            return False, ''

        if z_start > z_end:
            z_side = 1
        #elif z_start < z_finish:
        #    z_side = -1
        else:
            z_side = 0
            msg = 'Conversational ID Extended entry error - Z start not larger than Z end'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_z_start_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_z_end_dro'], msg)
            return False, ''

        if x_side > 0 and z_side > 0:  # tool orientation should be 3
            expected_tool_orientation = 3
        elif x_side > 0 and z_side < 0:  # tool orientation should be 4
            expected_tool_orientation = 4
        elif x_side < 0 and z_side > 0:  # tool orientation should be 2
            expected_tool_orientation = 2
        elif x_side < 0 and z_side < 0:  # tool orientation should be 1
            expected_tool_orientation = 1
        else :
            expected_tool_orientation = 0

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            error_msg = 'The X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(id_turn_dro_list['id_turn_final_dia_dro'], error_msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_pilot_dia_dro'], error_msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_tool_num_dro'], error_msg)
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational ID Extended entry error - Tool Orientation')
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the ID turn conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''


        # check that the fillet radius fits fully within x_range and z_range
        x_range = math.fabs(x_finish)
        if fillet_radius > x_range:
            msg = 'Conversational ID Extended entry error - Fillet radius must fit within Final X radius'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_final_dia_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_fillet_dro'], msg)
            return False, ''

        z_range = math.fabs(z_start - z_end)
        if fillet_radius > z_range:
            msg = 'Conversational ID Extended entry error - Fillet radius must fit within Z Start and Z End'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_z_start_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_z_end_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_fillet_dro'], msg)
            return False, ''

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # ID range
        id_range = round(math.fabs(x_finish - x_start) - finish_doc, 4)
        if id_rough_doc == 0:
            num_id_cuts = 0
            id_rough_doc_adjusted = 0
        elif id_range >= 0:
            num_id_cuts = int(id_range / id_rough_doc) + 1
            id_rough_doc_adjusted = (id_range / num_id_cuts)
        else:
            num_id_cuts = 0
            id_rough_doc_adjusted = 0
            msg = 'Conversational ID Extended entry error - Finish DoC too big or X dia. range too small'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_pilot_dia_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_final_dia_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_finish_doc_dro'], msg)
            return False, ''


        # face range
        face_range = round(math.fabs(z_end - pilot_end) - finish_doc, 4)
        if face_rough_doc == 0:
            num_face_cuts = 0
            face_doc_adjusted = 0
        elif face_range >= 0:
            num_face_cuts = int(face_range / face_rough_doc) + 1
            face_doc_adjusted = (face_range / num_face_cuts)
        else:
            num_face_cuts = 0
            face_doc_adjusted = 0
            msg = 'Conversational ID Extended entry error - Finish DoC too big or facing range too small'
            self.error_handler.write(msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_z_end_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_pilot_dro'], msg)
            cparse.raise_alarm(id_turn_dro_list['id_turn_finish_doc_dro'], msg)
            return False, ''

        x_fillet_center = x_finish - (x_side * fillet_radius)
        z_fillet_center = z_end + fillet_radius
        z_end_rough = z_end + finish_doc
        fillet_radius_rough = fillet_radius - finish_doc

        code.append('\n(ID Range = %s)' % dro_fmt % id_range)
        code.append('(Number of roughing passes = %d)' % num_id_cuts)
        code.append('(Adjusted ID roughing DoC = %s)' % dro_fmt % id_rough_doc_adjusted)

        # Rapid to start
        code.append('\nG0 X %s' % dro_fmt % (2 * (x_start - (x_side * tool_clearance))))
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        x_previous = x_start
        z_previous = pilot_end
        z_current = pilot_end
        z_fillet = pilot_end
        zf_previous = z_fillet

        # ##### ID Roughing

        id_count = 1
        while id_count <= num_id_cuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(ID %d)' % id_count)
            x_current = (x_start + (x_side * id_rough_doc_adjusted * id_count))
            code.append('G0 X %s' % dro_fmt % (2 * x_current))
            if math.fabs(x_current) <= math.fabs(x_finish - (x_side * fillet_radius)):
                # x_current hasn't reached the fillet zone yet
                code.append('G1 Z %s' % dro_fmt % pilot_end)
                # Retract
                code.append('G1 X %s' % dro_fmt % (2 * x_previous))

            else:
                # x_current is in the fillet zone, so calculate the intersection
                # point
                z_delta = math.sqrt(math.fabs((fillet_radius_rough ** 2) -
                                              ((x_fillet_center - x_current) ** 2)))
                z_fillet = z_fillet_center - z_delta
                if z_fillet < pilot_end:  # choose the shorter end point
                    z_current = pilot_end  # fillet intersection is beyond the ID zone
                    code.append('G1 Z %s' % dro_fmt % z_current)
                else:
                    # go to rough fillet intersection then to
                    # previous x or pilot end
                    z_current = z_fillet
                    code.append('G1 Z %s' % dro_fmt % z_current)
                    if zf_previous < pilot_end:
                        x_waypnt = math.sqrt(math.fabs((fillet_radius_rough ** 2) -
                                                       ((pilot_end - z_fillet_center) ** 2)))
                        code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) %
                                    ((2 * (x_fillet_center + (x_side * x_waypnt))), pilot_end))

                # Retract (temp, should follow rough fillet but this is close)
                code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) % (2 * x_previous, z_previous))

            if id_count < num_id_cuts:
                # Rapid to starting Z
                code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

            x_previous = x_current
            z_previous = z_current
            zf_previous = z_fillet
            id_count += 1
            # ID roughing loop return

        # ##### Face Roughing
        code.append('\n(Facing Range = %s)' % dro_fmt % face_range)
        code.append('(Number of roughing passes = %d)' % num_face_cuts)
        code.append('(Adjusted face roughing DoC = %s)' % dro_fmt % face_doc_adjusted)

        z_previous = pilot_end + face_rough_doc
        z_current = pilot_end
        if z_current - (z_end + finish_doc) <= 0:  # z_current is on or in the finish cut zone, start x at the fillet end
            x_current = x_fillet_center
        elif z_current >= z_fillet_center:  # z_current hasn't reached the fillet center, start x at rough ID
            x_current = x_finish - (x_side * finish_doc)
        elif z_current < z_fillet_center:  # z_current is inside the fillet zone so start x on rough fillet radius
            x_delta = math.sqrt(math.fabs((fillet_radius_rough ** 2) -
                                          ((z_fillet_center - z_current) ** 2)))
            x_current = (x_fillet_center + (x_side * x_delta))

        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    (2 * x_current, z_current))

        face_count = 1
        while face_count <= num_face_cuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(Face %d)' % face_count)
            z_current = pilot_end - (face_count * face_doc_adjusted)

            if z_current - (z_end + finish_doc) <= 0:
                # z_current is on or in the finish cut zone, start x at the fillet end
                x_current = x_fillet_center
            elif z_current >= z_fillet_center:
                # z_current hasn't reached the fillet center, start x at rough ID
                x_current = x_finish - (x_side * finish_doc)
            elif z_current < z_fillet_center:
                # z_current is inside the fillet zone so start x on rough fillet radius
                x_delta = math.sqrt(math.fabs((fillet_radius_rough ** 2) -
                                              ((z_fillet_center - z_current) ** 2)))
                x_current = (x_fillet_center + (x_side * x_delta))

            code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((2 * x_current), z_current))
            code.append('G1 X %s' % dro_fmt % (-2 * x_side * tool_clearance))
            code.append('G0 Z %s' % dro_fmt % z_previous)
            code.append('G0 X %s' % dro_fmt % (2 * x_current))

            if face_count < num_face_cuts:
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_current), z_current))

            x_previous = x_current
            z_previous = z_current
            face_count += 1
            # face roughing loop return

        # ##### Finish Pass
        code.append('\n(Set Finishing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    ((2 * (x_finish - (x_side * finish_doc))), (z_start + tool_clearance)))
        code.append('G1 X %s' % dro_fmt % final_diameter)
        code.append('G1 Z %s' % dro_fmt % z_fillet_center)
        x_mid_delta = math.sqrt((fillet_radius ** 2) / 2)
        code.append((g3 + ' X %s Z %s I %s K %s')
                    % (dro_fmt, dro_fmt, dro_fmt, dro_fmt)
                    % ((2 * x_fillet_center),
                       z_end,
                       (x_side * (-1.0 * fillet_radius)),
                       0))
        code.append('G1 X %s' % dro_fmt % (-2 * x_side * tool_clearance))

        # rapid to starting position - including clearance
        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    ((initial_diameter - (x_side * tool_clearance)), (z_start + tool_clearance)))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'ID Extended')

        return ok, code
    # ---------------------------------------------------------------------------------
    # Profiling turn code
    # ---------------------------------------------------------------------------------
    def ja_parse_profile(self, routine_data):
        gcode = routine_data['segment text']
        is_metric = routine_data['segment data']['Units']['orig'] == 'mm'
        tool_orientation = int(routine_data['segment data']['Tool Orientation']['orig'])
        is_external = 'External' in routine_data['segment data']['title']['ref']
        x_sign = -1. if is_external and tool_orientation in [3,4,8] else -1. if not is_external and tool_orientation in [1,2,6] else 1.
        format_spec = '%.3f' if is_metric else '%.4f'
        points_list = lathe_conv_support.ListToGcode.to_true_list(gcode, self.ui.PROFILE_ROWS, x_sign, format_spec)
        ref = routine_data['segment data']['Post Parse']['ref']
        routine_data['segment data'][ref]['orig'] = points_list
        routine_data['segment data'][ref]['mod'] = copy.deepcopy(points_list)

    def ja_edit_profile(self, routine_data):
        restore_data = dict(
            ext_int = 'external' if self.ui.conv_profile_ext == 'external' else 'internal',
            current_notepage = self.ui.profile_notebook.get_current_page(),
            disable_button = self.ui.button_list['profile_ext_int'],
            toggle_proc = getattr(self.ui,'toggle_profile_external_internal_button'),
            restore_proc = getattr(self, 'ja_restore_profile')
        )
        try:
            type_str = routine_data['segment data']['title']['ref']
            if 'External' in type_str or 'Internal' in type_str:
                self.ui.conv_profile_ext = 'external' if 'Internal' in type_str else 'internal'
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('ja_edit_profile: could not determine internal or external profile.  Traceback: %s' % traceback_txt)

        restore_data['toggle_proc']()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        self.ui.profile_set_tool_data(int(self.ui.profile_dro_list['profile_tool_num_dro'].get_text()))
        self.ui.profile_notebook.set_current_page(0)
        self.ui.profile_set_finish_image()
        return restore_data

    def ja_restore_profile(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.conv_profile_ext = 'internal' if restore_data['ext_int'] == 'external' else 'external'
        restore_data['toggle_proc']()
        txt = self.ui.profile_dro_list['profile_tool_num_dro'].get_text()
        tool_num = int(txt)
        self.ui.profile_set_tool_data(tool_num)
        self.ui.profile_notebook.set_current_page(restore_data['current_notepage'])
        self.ui.profile_set_finish_image()

    def gen_external_profile_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.profile_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_num_dro'],        'orig' : None , 'mod' : None }),
                             'Stock Diameter'           : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_stock_x_dro'],         'orig' : None , 'mod' : None }),
                             'Stock Z Start'            : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_stock_z_dro'],         'orig' : None , 'mod' : None }),
                             'Tool Front Angle'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_front_angle_dro'],'orig' : None , 'mod' : None }),
                             'Tool Rear Angle'          : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_rear_angle_dro'], 'orig' : None , 'mod' : None }),
                             'Tool Clearance X'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_roughing_tool_clear_x_dro'], 'orig' : None , 'mod' : None }),
                             'Tool Clearance Z'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_roughing_tool_clear_z_dro'], 'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp_na',        'ref':pdl['profile_roughing_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_finish_doc_dro'],      'orig' : None , 'mod' : None , 'rm_key' : 'Material to Leave' }),
                             'Material to Leave'        : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_finish_doc_dro'],      'orig' : None , 'mod' : None , 'rm_key' : 'Finish Depth of Cut'}),
                             'Finish Passes'            : ({ 'proc': 'unpack_fp_na',        'ref':pdl['profile_finish_passes_dro'],   'orig' : None , 'mod' : None }),
                             'X Mode'                   : ({ 'proc': 'unpack_str',          'ref':None,                               'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_profile_ext',    'ref':'external',                         'orig' : None, 'ja_diff' : 'no' },),
                             'Profile Points'           : ({ 'proc': None,                  'ref':'profile_liststore',                'orig' : None , 'mod' : None }),
                             'Post Parse'               : ({ 'proc': self.ja_parse_profile, 'ref':'Profile Points',                   'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,                  'ref':pdl['profile_tool_num_dro'],        'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'External Profiling')

    def gen_internal_profile_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.profile_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_num_dro'],        'orig' : None , 'mod' : None }),
                             'Stock Diameter'           : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_stock_x_dro'],         'orig' : None , 'mod' : None }),
                             'Stock Z Start'            : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_stock_z_dro'],         'orig' : None , 'mod' : None }),
                             'Tool Front Angle'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_front_angle_dro'],'orig' : None , 'mod' : None }),
                             'Tool Rear Angle'          : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_tool_rear_angle_dro'], 'orig' : None , 'mod' : None }),
                             'Tool Clearance X'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_roughing_tool_clear_x_dro'], 'orig' : None , 'mod' : None }),
                             'Tool Clearance Z'         : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_roughing_tool_clear_z_dro'], 'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp_na',        'ref':pdl['profile_roughing_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_finish_doc_dro'],      'orig' : None , 'mod' : None , 'rm_key' : 'Material to Leave' }),
                             'Material to Leave'        : ({ 'proc': 'unpack_fp',           'ref':pdl['profile_finish_doc_dro'],      'orig' : None , 'mod' : None , 'rm_key' : 'Finish Depth of Cut'}),
                             'Finish Passes'            : ({ 'proc': 'unpack_fp_na',        'ref':pdl['profile_finish_passes_dro'],   'orig' : None , 'mod' : None }),
                             'X Mode'                   : ({ 'proc': 'unpack_str',          'ref':None,                               'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_profile_ext',    'ref':'internal',                         'orig' : None, 'ja_diff' : 'no' },),
                             'Profile Points'           : ({ 'proc': None,                  'ref':'profile_liststore',                'orig' : None , 'mod' : None }),
                             'Post Parse'               : ({ 'proc': self.ja_parse_profile, 'ref':'Profile Points',                   'orig' : None , 'mod' : None , 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,                  'ref':pdl['profile_tool_num_dro'],        'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Internal Profiling')

    def generate_profile_code(self):
        cdl = self.ui.conv_dro_list
        pdl = self.ui.profile_dro_list
        profile_list = self.ui.profile_liststore
        err_msg = 'Conversational Profile entry error - '
        code = []
        ok = True
        rdp = (0.0,2.54) if self.ui.g21 else (0.0,0.10)
        fdp = (0.0,0.508) if self.ui.g21 else (0.0,0.02)
        title  = self.get_conv_title(self.ui.conv_dro_list)
        vl =  {'work_offset'   : {'dro': cdl['conv_work_offset_dro'],              'validation_routine': 'validate_work_offset'      , 'params': None            , 'value':  None },
               'roughing_sfm'  : {'dro': cdl['conv_rough_sfm_dro'],                'validation_routine': 'validate_surface_speed'    , 'params': None            , 'value':  None },
               'finish_sfm'    : {'dro': cdl['conv_finish_sfm_dro'],               'validation_routine': 'validate_surface_speed'    , 'params': None            , 'value':  None },
               'max_rpm'       : {'dro': cdl['conv_max_spindle_rpm_dro'],          'validation_routine': 'validate_spindle_rpm'      , 'params': None            , 'value':  None },
               'roughing_fpr'  : {'dro': cdl['conv_rough_fpr_dro'],                'validation_routine': 'validate_fpr'              , 'params': None            , 'value':  None },
               'finish_fpr'    : {'dro': cdl['conv_finish_fpr_dro'],               'validation_routine': 'validate_fpr'              , 'params': None            , 'value':  None },

               'tool_number'   : {'dro': pdl['profile_tool_num_dro'],              'validation_routine': 'validate_tool_number'      , 'params': None            , 'value':  None },
               'stock_z'       : {'dro': pdl['profile_stock_z_dro'],               'validation_routine': 'validate_any_num'          , 'params': None            , 'value':  None },
               'stock_x'       : {'dro': pdl['profile_stock_x_dro'],               'validation_routine': 'validate_gt0'              , 'params': None            , 'value':  None },
               'tool_fr_angle' : {'dro': pdl['profile_tool_front_angle_dro'],      'validation_routine': 'validate_tool_angle'       , 'params': None            , 'value':  None },
               'tool_rr_angle' : {'dro': pdl['profile_tool_rear_angle_dro'],       'validation_routine': 'validate_tool_angle'       , 'params': None            , 'value':  None },
               'tool_clear_z'  : {'dro': pdl['profile_roughing_tool_clear_z_dro'], 'validation_routine': 'validate_any_num'          , 'params': None            , 'value':  None },
               'tool_clear_x'  : {'dro': pdl['profile_roughing_tool_clear_x_dro'], 'validation_routine': 'validate_any_num_not_zero' , 'params': None            , 'value':  None },
               'roughing_doc'  : {'dro': pdl['profile_roughing_doc_dro'],          'validation_routine': 'val_empty_range_float'     , 'params': rdp             , 'value':  None },
               'finish_passes' : {'dro': pdl['profile_finish_passes_dro'],         'validation_routine': 'validate_in_set'           , 'params': ('','0','1','2'), 'value':  None },
               'finish_doc'    : {'dro': pdl['profile_finish_doc_dro'],            'validation_routine': 'validate_range_float'      , 'params': fdp             , 'value':  None }
              }
        list_model = self.ui.profile_treeview.get_model()
        list_model = self.ui.profile_liststore_to_list('compress')

        # validate DROs...
        if not any(list_model):
            self.error_handler.write('Conversational Profile entry error - Profile Points is empty')
            return False,''

        for k,validation in vl.iteritems():
            valid, validation['value'], error = self.std_validate_param(validation['dro'], validation['validation_routine'], err_msg, validation['params'])
            if not valid: ok = False


        is_external = self.ui.conv_profile_ext == 'external'
        is_metric, g20_g21, dro_fmt, feed_units, units, round_off, scale = self.is_metric()
        tool_number = vl['tool_number']['value']
        tool_radius = (self.status.tool_table[tool_number].diameter * scale) / 2
        tool_orientation = self.status.tool_table[tool_number].orientation
        if tool_orientation in [5,7,9]:
            error_msg = 'Tools must be one of the following tool orientations.'
            msg1 = 'Profiling call for orientation %s:' % '1, 2, 3, 4, 6, or 8'
            msg2 = 'The tool table orientation for T%s is %d:' % (tool_number, tool_orientation)
            cparse.raise_alarm(vl['tool_number']['dro'], error_msg + '\n' + msg1 + '\n' + msg2)
            expected_tool_orientation_image = get_tool_orientation_image(18)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational Profile entry error - Tool Orientation')
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text(msg1)
            self.error_handler.set_error_image_2_text(msg2)
            return False, ''


        angular_error = self.ui.profile_renderer.check_angular_error()
        if angular_error['count'] > 0:
            self.error_handler.write('Conversational ID Basic entry error - ' + angular_error['error'])
            return False,''

        # fixup DOC values...
        vl['roughing_doc']['value'] = math.fabs(vl['roughing_doc']['value'])
        vl['finish_doc']['value'] = math.fabs(vl['finish_doc']['value'])
        # fixup finish part_tw_dro values...
        finish_passes = int( vl['finish_passes']['value']) if any( vl['finish_passes']['value']) else 0
        finish_doc_str = 'Material to Leave' if not finish_passes else 'Finish Depth of Cut'
        roughing_doc = vl['roughing_doc']['value']
        empty_r_doc = not any(vl['roughing_doc']['dro'].get_text())

        if roughing_doc == 0.0 and not finish_passes:
            err = 'Conversational Profile entry error - Roughing DOC and Finishing Passes can not both be zero'
            self.ui.profile_notebook.set_current_page(1)
            self.error_handler.write(err)
            cparse.raise_alarm(vl['finish_passes']['dro'], err)
            cparse.raise_alarm(vl['roughing_doc']['dro'], err)
            return False, ''

        tool_type = self.get_tool_type(tool_number)
        cutting_toward_spindle = tool_orientation in [3,8,6,2]
        tool_angle1 = math.fabs(vl['tool_fr_angle']['value']) if cutting_toward_spindle else math.fabs(vl['tool_rr_angle']['value'])
        tool_angle2 = math.fabs(vl['tool_rr_angle']['value']) if cutting_toward_spindle else math.fabs(vl['tool_fr_angle']['value'])
        x_sign = -1. if is_external and tool_orientation in [3,4,8] else -1. if not is_external and tool_orientation in [1,2,6] else 1.
        tool_clear_x = math.fabs(vl['tool_clear_x']['value'])
        tool_x_start = float(list_model[0][1]) if any(list_model[0][1]) else tool_clear_x
        if is_external: expected_orientation = [1,6,2] if x_sign > 0. else [4,8,3]
        else: expected_orientation = [1,6,2] if x_sign < 0. else [4,8,3]

        #inter-dependant DRO validation...

        if is_external:
            if tool_clear_x <= vl['stock_x']['value']:
                msg = 'Conversational Profile entry error - Tool Clear Dia X must be greater than Stock X'
                self.error_handler.write(msg)
                cparse.raise_alarm(vl['tool_clear_x']['dro'], msg)
                cparse.raise_alarm(vl['stock_x']['dro'], msg)
                return False, ''

        #internal case
        elif tool_clear_x > float(list_model[0][1])*(lathe_conv_support.LatheProfileRenderer.x_fac*2.):
            msg = 'Conversational Profile entry error - Tool Clear Dia X must be less than minimal internal diameter'
            self.error_handler.write(msg)
            cparse.raise_alarm(vl['tool_clear_x']['dro'], msg)
            return False, ''

        if tool_angle1 < tool_angle2:
            rel = 'less' if cutting_toward_spindle else 'greater'
            err = 'Conversational Profile entry error - Front tool angle must be %s than rear tool angle' % (rel)
            self.ui.profile_notebook.set_current_page(2)
            self.error_handler.write(err)
            cparse.raise_alarm(vl['tool_fr_angle']['dro'], err)
            cparse.raise_alarm(vl['tool_rr_angle']['dro'], err)
            return False, ''

        # cutter comp error...
        if  math.fabs(vl['tool_clear_z']['value']-vl['stock_z']['value'])<=tool_radius:
            msg = 'Conversational Profile entry error - distance from Tool Clearance Z {:s} to Stock Z {:s} must be greater than tool radius {:s}'.format(dro_fmt%vl['tool_clear_z']['value'], dro_fmt%vl['stock_z']['value'], dro_fmt%tool_radius)
            self.error_handler.write(msg)
            cparse.raise_alarm(vl['tool_clear_z']['dro'], msg)
            return False, ''

        if not is_external:
            # get the minimum bore dimension. This will be the lowest feature excluding if the last feature goes to zero.
            min_dia = 1e10
            last_dia = 0.0
            for row in list_model:
                if not row[1]: continue
                last_dia = float(row[1])
                if last_dia > 0.00: min_dia = min(last_dia,min_dia)
            if tool_clear_x<vl['stock_x']['value']:
                suggested_tool_clearance = min_dia-tool_radius*2.0
                if tool_clear_x>suggested_tool_clearance:
                    msg = 'Conversational Profile entry error - Tool Clearance X {:s} must be less than the minimum feature diameter plus the tool_radius {:s}. Tool Clearance X should be set to less than {:s}.'.format(dro_fmt%vl['tool_clear_x']['value'], dro_fmt%tool_radius, dro_fmt%suggested_tool_clearance)
                    self.error_handler.write(msg)
                    cparse.raise_alarm(vl['tool_clear_x']['dro'], msg)
                    return False, ''

        if math.fabs(tool_clear_x - tool_x_start)<tool_radius*2.0:
            if is_external:
                min_tool_clearance = tool_x_start+tool_radius*2.0
                msg = 'Conversational Profile entry error - Tool Clearance X {:s} to the first X move must be greater than tool radius {:s}. Tool Clearance X should be set to greater than {:s}.'.format(dro_fmt%vl['tool_clear_x']['value'], dro_fmt%tool_radius, dro_fmt%min_tool_clearance)
            else:
                min_tool_clearance = tool_x_start-tool_radius*2.0
                msg = 'Conversational Profile entry error - Tool Clearance X {:s} to the first X move must be greater than tool radius {:s}. Tool Clearance X should be set to less than {:s}.'.format(dro_fmt%vl['tool_clear_x']['value'], dro_fmt%tool_radius, dro_fmt%min_tool_clearance)
            self.error_handler.write(msg)
            cparse.raise_alarm(vl['tool_clear_x']['dro'], msg)
            return False, ''

        # generate subroutine details in separate list..............................................
        try:
            tg_return = lathe_conv_support.ListToGcode.to_gcode(is_metric,
                                                                is_external,
                                                                list_model,
                                                                x_sign,
                                                                dro_fmt,
                                                                vl['stock_x']['value'],
                                                                vl['stock_z']['value'],
                                                                vl['tool_clear_z']['value'],
                                                                tool_clear_x)
        except ValueError as e:
            self.error_handler.write('Conversational Profile entry error - '+str(e))
            return False,''
        profile_list, subroutine_list, min_x, approach, len_line_prefix, last_x = tg_return
        e_val = 1 if approach >= vl['stock_z']['value'] else 0
        subroutine_number = int(self.ui.update_subroutine_number())
        if subroutine_number is None: return False,''
        # generation details -----------------------------------------------------------------------
        profile_type = 'External' if is_external else 'Internal'
        if is_external: cutter_comp = 'G42' if x_sign>0. else 'G41'
        else: cutter_comp = 'G42' if x_sign<0. else 'G41'
        message = '(%s Profiling G-code generated:)\n(   %s)' % (profile_type, time.asctime(time.localtime(time.time())))
        code.append(message)
        code.append(conversational.conv_version_string())
        code.append('(Description = %s)' % cdl['conv_title_dro'].get_text())

        rough_x_material_to_leave = vl['finish_doc']['value'] if finish_passes < 1 else math.fabs((float(finish_passes) * vl['finish_doc']['value']))
        rough_z_material_to_leave = vl['finish_doc']['value'] if finish_passes < 1 else math.fabs((float(finish_passes) * vl['finish_doc']['value']))

        pre_finish_x_material = 0.0 if finish_passes < 2 else vl['finish_doc']['value']
        pre_finish_z_material = 0.0 if finish_passes < 2 else vl['finish_doc']['value']
        if not is_external: rough_x_material_to_leave *= -1.


        # list all parameters in output comments
        profile_type = 'External' if is_external else 'Internal'
        self.__write_std_info(code, '%s Profiling' % profile_type, g20_g21, units, vl['work_offset']['value'], tool_number, tool_radius, vl['max_rpm']['value'])
        code.append('(Tool Front Angle = %.1f)' % vl['tool_fr_angle']['value'])
        code.append('(Tool Rear Angle = %.1f)' % vl['tool_rr_angle']['value'])
        code.append('(Tool Clearance Z = %s)' % dro_fmt % vl['tool_clear_z']['value'])
        code.append('(Tool Clearance X = %s)' % dro_fmt % vl['tool_clear_x']['value'])

        code.append('\n(Rough CSS = %.0f %s)' % (vl['roughing_sfm']['value'], units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % vl['roughing_fpr']['value'])
        code.append('(Rough Depth of Cut = %s)' % (conversational_base._NA_ if empty_r_doc else (dro_fmt % vl['roughing_doc']['value'])))

        code.append('\n(Finish CSS = %.0f %s)' % (vl['finish_sfm']['value'], units))
        code.append('(Finish Passes = %s)' % (vl['finish_passes']['value'] if any(vl['finish_passes']['value']) else conversational_base._NA_))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' %  vl['finish_fpr']['value'])
        code.append('(%s = %s)' % (finish_doc_str,dro_fmt% vl['finish_doc']['value']))

        code.append('\n(Stock Diameter = %s)' % dro_fmt % vl['stock_x']['value'])
        code.append('(Stock Z Start = %s)' % dro_fmt % vl['stock_z']['value'])
        code.append('(X Mode = %s)' % ('Diameter' if self.ui.conv_profile_x_mode == 'diameter' else 'Radius'))
        code.append(self._tool_side_msg(x_sign))
        code.extend(profile_list)

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('G91.1 (Arc Incremental IJK)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % vl['work_offset']['value'])

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number,tool_number))
        code.append('G96 S %.0f D %.0f' % (vl['roughing_sfm']['value'], vl['max_rpm']['value']))
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % vl['roughing_fpr']['value'])

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # go to safe Z,X value
        code.append('G0 X%s ( go to safe X, then start Z before issuing G71)' % (dro_fmt) % (math.fabs(vl['tool_clear_x']['value'])*x_sign))
        code.append('G0 Z%s' % (dro_fmt) % (vl['tool_clear_z']['value']))
        if e_val == 0: code.append('G0 Z%s' % (dro_fmt) % (approach))
        # generate the G71 command
        code.append('G71 P%04d D%.4f F%1.4f J%1.4f L%d I%1.4f K%1.4f R%1.4f E%d' % (subroutine_number,                                            #P
                                                                                    vl['roughing_doc']['value'],                                  #D
                                                                                    vl['roughing_fpr']['value'],                                  #F
                                                                                    rough_x_material_to_leave,                                    #J
                                                                                    int(round(math.fabs(rough_x_material_to_leave) * 1000.0,0)),  #L
                                                                                    pre_finish_x_material,                                        #I
                                                                                    pre_finish_z_material,                                        #K
                                                                                    vl['roughing_doc']['value'],                                  #R
                                                                                    e_val                                                         #E
                                                                                   ))
        # call the subroutine as explicit gcode (sub call would be nice but needs to be 'special' directory)
        if finish_passes > 0:
            code.append('\n(Finish Pass)')
            if vl['finish_sfm']['value']!= vl['roughing_sfm']['value']: code.append('G96 S %.0f D %.0f' % (vl['roughing_sfm']['value'], vl['max_rpm']['value']))
            if vl['finish_fpr']['value']!= vl['roughing_fpr']['value']: code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % vl['finish_fpr']['value'])
            code.append('G0 X%s ( go to safe X)' % (dro_fmt) % (math.fabs(vl['tool_clear_x']['value'])*x_sign))
            code.append('G0 Z%s ( go to start Z)' % (dro_fmt) % (vl['tool_clear_z']['value']))
            if e_val == 0: code.append('G0 Z%s' % (dro_fmt) % (approach))
            code.append('%s (Cutter compensation - on)' % cutter_comp)
            for line in subroutine_list: code.append(line[len_line_prefix:])
            code.append('G40 (cutter compensation - off)')
            if is_external:
                safe_x = max(math.fabs(vl['tool_clear_x']['value']),math.fabs(last_x))
                code.append('G1 X%s ( go to safe X)' % (dro_fmt) % (safe_x*x_sign))
                code.append('G0 Z%s ( go to safe Z)' % (dro_fmt) % (vl['tool_clear_z']['value']))
            else:
                code.append('G0 Z%s ( go to safe Z)' % (dro_fmt) % (vl['tool_clear_z']['value']))
                code.append('G0 X%s ( go to safe X)' % (dro_fmt) % (math.fabs(vl['tool_clear_x']['value'])*x_sign))
        else: code.append('\n(No Finish Passes)')
        # generate the o-code subroutine
        code.append('\n("o-code subroutine for profile")')
        code.append('(Note: all profile subroutine code is in parenthesis)')
        code.append(lathe_conv_support.make_gcode_comment('o%04d SUB' % (subroutine_number)))
        for line in subroutine_list: code.append(lathe_conv_support.make_gcode_comment(line))
        code.append(lathe_conv_support.make_gcode_comment('o%04d ENDSUB' % (subroutine_number)))
        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Profiling')

        return ok, code


    # ---------------------------------------------------------------------------------
    # Facing turn code
    # ---------------------------------------------------------------------------------

    def ja_edit_face(self, routine_data):
        return self.ja_edit_general(routine_data)

    def gen_face_dro_dict(self):
        # ui is a base class attribute
        fdl = self.ui.face_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':fdl['face_tool_num_dro'],        'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':fdl['face_rough_doc_dro'],       'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':fdl['face_finish_doc_dro'],      'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':fdl['face_stock_dia_dro'],       'orig' : None , 'mod' : None }),
                             'Inside Diameter'          : ({ 'proc': 'unpack_fp',    'ref':fdl['face_x_end_dro'],           'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':fdl['face_z_start_dro'],         'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':fdl['face_z_end_dro'],           'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':fdl['face_tc_dro'],              'orig' : None , 'mod' : None }),
                             'focus'                    : ({ 'proc': None,           'ref':fdl['face_tool_num_dro'],        'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Facing')

    def generate_face_code(self, conv_dro_list, face_dro_list):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        face_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)


        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(face_dro_list['face_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, rough_doc, error  =  self.validate_param(face_dro_list['face_rough_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, finish_doc, error  =  self.validate_param(face_dro_list['face_finish_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(face_dro_list['face_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, d_start, error =  self.validate_param(face_dro_list['face_stock_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, d_end, error  =  self.validate_param(face_dro_list['face_x_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(face_dro_list['face_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        valid, z_end, error =  self.validate_param(face_dro_list['face_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Face entry error - ' + error)
            ok = False

        rough_doc = math.fabs(rough_doc)
        finish_doc = math.fabs(finish_doc)

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # generation details
        self.__write_std_info(code, 'Facing', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(Rough Depth of Cut = %.4f)' % rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Outside Diameter = %.4f)' % d_start)
        code.append('(Inside Diameter = %.4f)' % d_end)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End  Location = %.4f)' % z_end)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        x_start = d_start / 2
        x_end = d_end / 2
        x_overrun = (tool_radius + (tool_radius*0.1)) / 2

        if x_start > x_end and x_end >= 0:
            x_side = 1
            code.append(self._tool_side_msg(x_side))
        elif x_start < x_end and x_end <= 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
        else:
            x_side = 0
            msg = 'Conversational Face entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(face_dro_list['face_stock_dia_dro'], msg)
            cparse.raise_alarm(face_dro_list['face_x_end_dro'], msg)
            return False, ''


        z_range = z_start - z_end

        # Face is away from spindle
        if z_start > z_end:
            z_side = 1

        # Face is towards spindle
        # Should we allow it? error?
        elif z_start < z_end:
        #    z_side = -1
            z_side = 0
            msg = 'Conversational Face entry error - Z start not larger than Z end'
            self.error_handler.write(msg)
            cparse.raise_alarm(face_dro_list['face_z_start_dro'], msg)
            cparse.raise_alarm(face_dro_list['face_z_end_dro'], msg)
            return False, ''

        else: # z_start == z_end
            num_rcuts = 0
            rough_doc_adjusted = 0
            z_side = 1

        if x_side > 0 and z_side > 0:  # tool orientation should be 2, 3, or 7
            expected_tool_orientation = [2, 3, 7]
            expected_tool_orientation_group = 10
        elif x_side > 0 and z_side < 0:  # tool orientation should be 1, 4, or 5
            expected_tool_orientation = [1, 4, 5]
            expected_tool_orientation_group = 11
        elif x_side < 0 and z_side > 0:  # tool orientation should be 2, 3, or 7
            expected_tool_orientation = [2, 3, 7]
            expected_tool_orientation_group = 10
        elif x_side < 0 and z_side < 0:  # tool orientation should be 1, 4, or 5
            expected_tool_orientation = [1, 4, 5]
            expected_tool_orientation_group = 11
        else :
            expected_tool_orientation = [0]
            expected_tool_orientation_group = 0

        for index in range(len(expected_tool_orientation)):
            if expected_tool_orientation[index] == tool_orientation:
                break
            if index == len(expected_tool_orientation) -1:
                # raise alarms on the offending widgets
                error_msg = 'The X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
                cparse.raise_alarm(face_dro_list['face_x_end_dro'], error_msg)
                cparse.raise_alarm(face_dro_list['face_stock_dia_dro'], error_msg)
                cparse.raise_alarm(face_dro_list['face_tool_num_dro'], error_msg)
                expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation_group)
                tool_orientation_image = get_tool_orientation_image(tool_orientation)
                self.error_handler.write('Conversational Face entry error - Tool Orientation')
                self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                self.error_handler.set_image_1(expected_tool_orientation_image)
                self.error_handler.set_image_2(tool_orientation_image)
                self.error_handler.set_error_image_1_text('The X and Z inputs in the Face conversational call for orientation %s:' % expected_tool_orientation)
                self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
                return False, ''


        zr_range = round(math.fabs(z_range) - finish_doc, 4)
        if rough_doc == 0:
            num_rcuts = 0
            rough_doc_adjusted = 0
        elif zr_range >= 0:
            num_rcuts = int(zr_range / rough_doc) + 1
            rough_doc_adjusted = (zr_range / num_rcuts)
        else:
            num_rcuts = 0
            rough_doc_adjusted = 0
            self.error_handler.write('Conversational Face entry error - Finish DoC too big or Z range too small')

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # Set up loop
        code.append('\n(Number of roughing passes = %d)' % num_rcuts)
        code.append('(Adjusted roughing DoC = %.4f)' % rough_doc_adjusted)

        # rapid to starting position
        code.append('\nG0 X %s' % dro_fmt % (2 * (x_start + (x_side * tool_clearance))))
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        count = 1
        while count <= num_rcuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(Pass %d)' % count)
            # Rapid Z DoC
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) % ((2 * (x_start + (x_side * tool_clearance))), (z_start - (rough_doc_adjusted * count))))
            # Face to center plus the tool clearance
            code.append('G1 X %s' % dro_fmt % (2 * (x_end - (x_side * x_overrun))))
            # Rapid Z retract to previous Z
            code.append('G0 Z %s' % dro_fmt % ((z_start - (rough_doc_adjusted * count)) + rough_doc_adjusted))
            # Rapid to start diameter + clearance
            code.append('G0 X %s' % dro_fmt % (2 * (x_start + (x_side * tool_clearance))))
            # Do it again
            count += 1

        # ##### Finish Pass
        code.append('\n(Set Finishing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\n(Finish Pass %d)' % count)
        # Rapid to z_end
        code.append('G0 Z %s' % dro_fmt % z_end)
        # Feed to inside diameter - clearance
        code.append('G1 X %s' % dro_fmt % (2 * (x_end - (x_side * x_overrun))))
        # Rapid to facing start
        code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                    ((2 * (x_start + (x_side * tool_clearance))), (z_start + tool_clearance)))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Facing')

        return ok, code


    # ---------------------------------------------------------------------------------
    # Chamfer
    # ---------------------------------------------------------------------------------
    def ja_edit_chamfer(self, routine_data):
        restore_data = dict(
            chamfer_radius = 'chamfer' if self.ui.conv_chamfer_radius == 'chamfer' else 'radius',
            cr_toggle_proc = getattr(self.ui,'toggle_chamfer_radius_button'),
            id_od = 'id' if self.ui.conv_chamfer_od_id == 'id' else 'od',
            disable_button = self.ui.button_list['corner_chamfer_radius'],
            disable_button_2 = self.ui.button_list['corner_id_od'],
            id_od_toggle_proc = getattr(self.ui,'toggle_id_od_button'),
            restore_proc = getattr(self, 'ja_restore_chamfer_page')
        )

        self.ui.conv_chamfer_od_id = 'id' if 'External' in routine_data['segment data']['title']['ref'] else 'od'
        restore_data['id_od_toggle_proc']()

        self.ui.conv_chamfer_radius = 'radius' if routine_data['segment data'].has_key('Chamfer Angle') else 'chamfer'
        restore_data['cr_toggle_proc']()

        conversational.ja_toggle_buttons([restore_data['disable_button'],restore_data['disable_button_2']])
        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_chamfer_page(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button'],restore_data['disable_button_2']],'on')
        self.ui.conv_chamfer_od_id = 'od' if restore_data['id_od'] == 'id' else 'id'
        restore_data['id_od_toggle_proc']()
        self.ui.conv_chamfer_radius = 'radius' if restore_data['chamfer_radius'] == 'chamfer' else 'chamfer'
        restore_data['cr_toggle_proc']()

    def gen_chamfer_dro_dict(self):
        # ui is a base class attribute
        edl = self.ui.corner_chamfer_od_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_tool_num_dro'],   'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_rough_doc_dro'],  'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_finish_doc_dro'], 'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_od_dro'],         'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_z_start_dro'],    'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_z_end_dro'],      'orig' : None , 'mod' : None }),
                             'Z Chamfer Width'          : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_od_dro'],         'orig' : None , 'mod' : None }),
                             'Chamfer Angle'            : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_angle_dro'],      'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':edl['corner_chamfer_od_tc_dro'],         'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_chamfer_radius','ref':'chamfer',                         'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_chamfer_od_id', 'ref':'od',                              'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                    : ({ 'proc': None,           'ref':edl['corner_chamfer_od_tool_num_dro'],   'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'External Chamfer')

    def gen_chamfer_interal_dro_dict(self):
        # ui is a base class attribute
        idl = self.ui.corner_chamfer_id_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_tool_num_dro'],   'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_rough_doc_dro'],  'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_finish_doc_dro'], 'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_id_dro'],         'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_z_start_dro'],    'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_z_end_dro'],      'orig' : None , 'mod' : None }),
                             'Z Chamfer Width'          : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_id_dro'],         'orig' : None , 'mod' : None }),
                             'Chamfer Angle'            : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_angle_dro'],      'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':idl['corner_chamfer_id_tc_dro'],         'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_chamfer_radius','ref':'chamfer',                         'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_chamfer_od_id', 'ref':'id',                              'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                    : ({ 'proc': None,           'ref':idl['corner_chamfer_id_tool_num_dro'],   'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Internal Chamfer')

    def generate_chamfer_code(self, conv_dro_list, corner_dro_list, od_id):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        chamfer_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Chamfer entry error - ' + error)
            ok = False

        # Chamfer DRO list
        if od_id == 'od':
            valid, tool_number, error =  self.validate_param(corner_dro_list['corner_chamfer_od_tool_num_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, z_start, error =  self.validate_param(corner_dro_list['corner_chamfer_od_z_start_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, initial_diameter, error =  self.validate_param(corner_dro_list['corner_chamfer_od_od_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, chamfer_angle, error =  self.validate_param(corner_dro_list['corner_chamfer_od_angle_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, z_end, error =  self.validate_param(corner_dro_list['corner_chamfer_od_z_end_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, rough_doc, error  =  self.validate_param(corner_dro_list['corner_chamfer_od_rough_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, finish_doc, error  =  self.validate_param(corner_dro_list['corner_chamfer_od_finish_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, tool_clearance, error  =  self.validate_param(corner_dro_list['corner_chamfer_od_tc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

        else:  # od_id == 'id'
            valid, tool_number, error =  self.validate_param(corner_dro_list['corner_chamfer_id_tool_num_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, z_start, error =  self.validate_param(corner_dro_list['corner_chamfer_id_z_start_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, initial_diameter, error =  self.validate_param(corner_dro_list['corner_chamfer_id_id_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, chamfer_angle, error =  self.validate_param(corner_dro_list['corner_chamfer_id_angle_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, z_end, error =  self.validate_param(corner_dro_list['corner_chamfer_id_z_end_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, rough_doc, error  =  self.validate_param(corner_dro_list['corner_chamfer_id_rough_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, finish_doc, error  =  self.validate_param(corner_dro_list['corner_chamfer_id_finish_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

            valid, tool_clearance, error  =  self.validate_param(corner_dro_list['corner_chamfer_id_tc_dro'])
            if not valid:
                self.error_handler.write('Conversational Chamfer entry error - ' + error)
                ok = False

        rough_doc = math.fabs(rough_doc)
        finish_doc = math.fabs(finish_doc)

        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # Set tool working side
        if initial_diameter > 0:
            x_side = 1
            code.append(self._tool_side_msg(x_side))
        elif initial_diameter < 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
        else:
            x_side = 0
            if od_id == 'od':
                msg = 'Conversational Chamfer entry error - OD can not be 0'
                self.error_handler.write(msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_od_dro'], msg)
            else:  # 'id'
                msg = 'Conversational Chamfer entry error - ID can not be 0'
                self.error_handler.write(msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_od_dro'], msg)
            return False, ''

        # Set chamfer face direction
        if z_end < z_start:
            z_side = 1
            msg_chamfer_dir = 'Chamfer faces away from spindle, Z+'
        elif z_end > z_start:
            z_side = -1
            msg_chamfer_dir = 'Chamfer faces toward spindle, Z-'
        else:
            z_side = 0
            msg = 'Conversational Chamfer entry error - Chamfer width can not be 0'
            self.error_handler.write(msg)
            if od_id == 'od':
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_z_start_dro'], msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_z_end_dro'], msg)
            else:  # 'id'
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_z_start_dro'], msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_z_end_dro'], msg)
            return False, ''

        if od_id == 'od':
            if x_side > 0 and z_side > 0:  # tool orientation should be 2, 6, or 7
                expected_tool_orientation = [2, 6, 7]
                expected_tool_orientation_group = 12
            elif x_side > 0 and z_side < 0:  # tool orientation should be 1, 5, or 6
                expected_tool_orientation = [1, 5, 6]
                expected_tool_orientation_group = 13
            elif x_side < 0 and z_side > 0:  # tool orientation should be 3, 7, or 8
                expected_tool_orientation = [3, 7, 8]
                expected_tool_orientation_group = 14
            elif x_side < 0 and z_side < 0:  # tool orientation should be 4, 5, or 8
                expected_tool_orientation = [4, 5, 8]
                expected_tool_orientation_group = 15
            else :
                expected_tool_orientation = 0
                expected_tool_orientation_group = 0
        else:  # 'id'
            if x_side < 0 and z_side > 0:  # tool orientation should be 2, 6, or 7
                expected_tool_orientation = [2, 6, 7]
                expected_tool_orientation_group = 12
            elif x_side < 0 and z_side < 0:  # tool orientation should be 1, 5, or 6
                expected_tool_orientation = [1, 5, 6]
                expected_tool_orientation_group = 13
            elif x_side > 0 and z_side > 0:  # tool orientation should be 3, 7, or 8
                expected_tool_orientation = [3, 7, 8]
                expected_tool_orientation_group = 14
            elif x_side > 0 and z_side < 0:  # tool orientation should be 4, 5, or 8
                expected_tool_orientation = [4, 5, 8]
                expected_tool_orientation_group = 15
            else :
                expected_tool_orientation = 0
                expected_tool_orientation_group = 0

        tool_okay = 0
        for etoi in expected_tool_orientation:
            if etoi == tool_orientation:
                tool_okay = 1
                break

        if tool_okay == 0:
            ok = False
            # raise alarms on the offending widgets
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation_group)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            error_msg = 'Conversational Chamfer entry error - Tool Orientation\nThe X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the Chamfer conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))

            if od_id == 'od':
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_od_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_z_start_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_z_end_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_od_tool_num_dro'], error_msg)
            else:  # 'id'
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_id_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_z_start_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_z_end_dro'], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_chamfer_id_tool_num_dro'], error_msg)
            return False, ''

        angle = math.radians(chamfer_angle)

        # tool radius offsets
        trdz = trdx = trzos = trxos = 0.0

        if tool_radius > 0:
            trdz = math.fabs(tool_radius * math.sin(angle))  # z distance from tool radius center
            trdx = math.fabs(tool_radius * math.cos(angle))  # x distance from tool radius center

            if tool_orientation == 1:
                trzos =  (tool_radius - trdz)
                trxos = -(tool_radius - trdx)
            if tool_orientation == 2:
                trzos = -(tool_radius - trdz)
                trxos = -(tool_radius - trdx)
            if tool_orientation == 3:
                trzos = -(tool_radius - trdz)
                trxos =  (tool_radius - trdx)
            if tool_orientation == 4:
                trzos =  (tool_radius - trdz)
                trxos =  (tool_radius - trdx)

            if od_id == 'od':
                if tool_orientation == 5:
                    trzos =  (tool_radius - trdz)
                    trxos =  trdx * x_side
                if tool_orientation == 6:
                    trzos =  trdz * z_side
                    trxos = -(tool_radius - trdx)
                if tool_orientation == 7:
                    trzos = -(tool_radius - trdz)
                    trxos =  trdx * x_side
                if tool_orientation == 8:
                    trzos =  trdz * z_side
                    trxos =  (tool_radius - trdx)

            else:  # 'id'
                if tool_orientation == 5:
                    trzos =  (tool_radius - trdz)
                    trxos = -trdx * x_side
                if tool_orientation == 6:
                    trzos =  trdz * z_side
                    trxos = -(tool_radius - trdx)
                if tool_orientation == 7:
                    trzos = -(tool_radius - trdz)
                    trxos = -trdx * x_side
                if tool_orientation == 8:
                    trzos =  trdz * z_side
                    trxos =  (tool_radius - trdx)

        # calculate base points, which are on a line perpendicular to the
        # chamfer angle, starting at the start location, and ending on
        # the chamfer. The roughing points are offset by the adjusted rough
        # DoC. The final offset is the finish DoC.

        # base_line_len = hyp_len * sin(angle)
        z_chamfer_len = math.fabs(z_end - z_start)
        base_line_len = z_chamfer_len * math.sin(angle)
        base_line_len_ruf = base_line_len - finish_doc

        if rough_doc == 0:  # only finish cut
            num_rcuts = 0
            rough_DoC_adjusted = 0
        elif base_line_len_ruf < 0:  # only finish cut
            num_rcuts = 0
            rough_DoC_adjusted = 0
        else:
            num_rcuts = int((base_line_len_ruf / rough_doc) + .99)
            rough_DoC_adjusted = (base_line_len_ruf / num_rcuts)

        # calculate base line points for each rear tool mode
        # there are four modes covering od_id and z side +_-
        # another four modes are for front tools which change
        # the sign of x and is easy to apply in the g-code
        # section

        angle = math.radians(chamfer_angle)
        slope = math.tan(angle)

        # all points are based on the start position
        x_start = math.fabs(initial_diameter) / 2
        #z_start = use as is

        base_pnt_list  = [(x_start, z_start)]
        start_pnt_list = [(x_start, z_start)]
        end_pnt_list   = [(x_start, z_start)]

        dx = rough_DoC_adjusted * math.cos(angle)  # x component of range of roughing passes
        dz = rough_DoC_adjusted * math.sin(angle)  # z component

        # select mode for calulating base, cut start, and end points
        if od_id == 'od' and z_side == 1:
            start_xlim = x_start + tool_clearance
            start_zlim = z_end - tool_clearance
            end_xlim = x_start - (slope * z_chamfer_len) - tool_clearance
            end_zlim = z_start + tool_clearance
            park_x = x_start + tool_clearance
            park_z = z_start + tool_clearance

            for i in range(1, num_rcuts + 1):  # the first base point is at (x_start, z_start)
                ibpx = x_start - (i * dx)  # current x base point
                ibpz = z_start - (i * dz)  # current z base point
                base_pnt_list.append((ibpx, ibpz))
            # set final base point
            base_pnt_list.append((x_start - (base_line_len * math.cos(angle)), z_start - (base_line_len * math.sin(angle))))

            for i in range(1, num_rcuts + 2):  # the first start and end points at (x_start, z_start) are ignored
                start_dx = start_xlim - base_pnt_list[i][0]  # start point limited to x tool clearance boundry
                start_dz = start_dx / slope
                ispx = start_xlim
                ispz = base_pnt_list[i][1] - start_dz

                if ispz < start_zlim:
                    ispz = start_zlim
                    start_dz = base_pnt_list[i][1] - start_zlim
                    start_dx = start_dz * slope
                    ispx = base_pnt_list[i][0] + start_dx

                start_pnt_list.append((ispx, ispz))

                end_dz = end_zlim - base_pnt_list[i][1]
                end_dx = end_dz * slope
                iepz = end_zlim
                iepx = base_pnt_list[i][0] - end_dx

                if iepx < end_xlim:
                    iepx = end_xlim
                    end_dx = base_pnt_list[i][0] - iepx
                    end_dz = end_dx / slope
                    iepz = base_pnt_list[i][1] + end_dz

                end_pnt_list.append((iepx, iepz))

        elif od_id == 'od' and z_side == -1:
            start_xlim = x_start + tool_clearance
            start_zlim = z_end + tool_clearance
            end_xlim = x_start - (slope * z_chamfer_len) - tool_clearance
            end_zlim = z_start - tool_clearance
            park_x = x_start + tool_clearance
            park_z = z_start - tool_clearance

            for i in range(1, num_rcuts + 1):  # the first base point is at (x_start, z_start)
                ibpx = x_start - (i * dx)  # current x base point
                ibpz = z_start + (i * dz)  # current z base point
                base_pnt_list.append((ibpx, ibpz))
            # set final base point
            base_pnt_list.append((x_start - (base_line_len * math.cos(angle)), z_start + (base_line_len * math.sin(angle))))

            for i in range(1, num_rcuts + 2):  # the first start and end points at (x_start, z_start) are ignored
                start_dx = start_xlim - base_pnt_list[i][0]  # start point limited to x tool clearance boundry
                start_dz = start_dx / slope
                ispx = start_xlim
                ispz = base_pnt_list[i][1] + start_dz

                if ispz > start_zlim:
                    ispz = start_zlim
                    start_dz = start_zlim - base_pnt_list[i][1]
                    start_dx = start_dz * slope
                    ispx = base_pnt_list[i][0] + start_dx

                start_pnt_list.append((ispx, ispz))

                end_dz = base_pnt_list[i][1] - end_zlim
                end_dx = end_dz * slope
                iepz = end_zlim
                iepx = base_pnt_list[i][0] - end_dx
                if iepx < end_xlim:
                    iepx = end_xlim
                    end_dx = base_pnt_list[i][0] - iepx
                    end_dz = end_dx / slope
                    iepz = base_pnt_list[i][1] - end_dz
                end_pnt_list.append((iepx, iepz))

        elif od_id == 'id' and z_side == 1:
            start_xlim = x_start - tool_clearance
            start_zlim = z_end - tool_clearance
            end_xlim = x_start + (slope * z_chamfer_len) + tool_clearance
            end_zlim = z_start + tool_clearance
            park_x = x_start - tool_clearance
            park_z = z_start + tool_clearance

            for i in range(1, num_rcuts + 1):  # the starting base point is at (x_start, z_start)
                ibpx = x_start + (i * dx)  # current x base point
                ibpz = z_start - (i * dz)  # current z base point
                base_pnt_list.append((ibpx, ibpz))
            # set final base point
            base_pnt_list.append((x_start + (base_line_len * math.cos(angle)), z_start - (base_line_len * math.sin(angle))))

            for i in range(1, num_rcuts + 2):  # the first start and end points at (x_start, z_start) are ignored
                start_dx = base_pnt_list[i][0] - start_xlim  # start point limited to x tool clearance boundry
                start_dz = start_dx / slope
                ispx = start_xlim
                ispz = base_pnt_list[i][1] - start_dz

                if ispz < start_zlim:
                    ispz = start_zlim
                    start_dz = base_pnt_list[i][1] - start_zlim
                    start_dx = start_dz * slope
                    ispx = base_pnt_list[i][0] - start_dx

                start_pnt_list.append((ispx, ispz))

                end_dz = end_zlim - base_pnt_list[i][1]
                end_dx = end_dz * slope
                iepz = end_zlim
                iepx = base_pnt_list[i][0] + end_dx

                if iepx > end_xlim:
                    iepx = end_xlim
                    end_dx = iepx - base_pnt_list[i][0]
                    end_dz = end_dx / slope
                    iepz = base_pnt_list[i][1] + end_dz

                end_pnt_list.append((iepx, iepz))

        else:  # od_id == 'id' and z_side == -1
            start_xlim = x_start - tool_clearance
            start_zlim = z_end + tool_clearance
            end_xlim = x_start + (slope * z_chamfer_len) + tool_clearance
            end_zlim = z_start - tool_clearance
            park_x = x_start - tool_clearance
            park_z = z_start - tool_clearance

            for i in range(1, num_rcuts + 1):  # the starting base point is at (x_start, z_start)
                ibpx = x_start + (i * dx)  # current x base point
                ibpz = z_start + (i * dz)  # current z base point
                base_pnt_list.append((ibpx, ibpz))
            # set final base point
            base_pnt_list.append((x_start + (base_line_len * math.cos(angle)), z_start + (base_line_len * math.sin(angle))))

            for i in range(1, num_rcuts + 2):  # the first start and end points at (x_start, z_start) are ignored
                start_dx = base_pnt_list[i][0] - start_xlim  # start point limited to x tool clearance boundry
                start_dz = start_dx / slope
                ispx = start_xlim
                ispz = base_pnt_list[i][1] + start_dz

                if ispz > start_zlim:
                    ispz = start_zlim
                    start_dz = start_zlim - base_pnt_list[i][1]
                    start_dx = start_dz * slope
                    ispx = base_pnt_list[i][0] - start_dx

                start_pnt_list.append((ispx, ispz))

                end_dz = base_pnt_list[i][1] - end_zlim
                end_dx = end_dz * slope
                iepz = end_zlim
                iepx = base_pnt_list[i][0] + end_dx

                if iepx > end_xlim:
                    iepx = end_xlim
                    end_dx = iepx - base_pnt_list[i][0]
                    end_dz = end_dx / slope
                    iepz = base_pnt_list[i][1] - end_dz

                end_pnt_list.append((iepx, iepz))


        # generation details
        chamfer_type = 'External' if od_id == 'od' else 'Internal'
        self.__write_std_info(code, '%s Chamfer' % chamfer_type, g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)
        code.append('(Chamfer is on the %s)' % od_id.upper())
        code.append('(%s)' % msg_chamfer_dir)

        # msg_tool_dir is totally undefined.  pylint caught this.  looks to be a comment in the g-code so just removing it for now to
        # avoid a runtime error.
        #code.append('(%s)' % msg_tool_dir)

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(Rough Depth of Cut = %.4f)' % rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Outside Diameter = %.4f)' % initial_diameter)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End Location = %.4f)' % z_end)
        code.append('(Z Chamfer Width = %.4f)' % z_chamfer_len)
        code.append('(Chamfer Angle = %.2f)' % chamfer_angle)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        # Start of motion commands - x values get converted to diameters and
        # x side

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        ## Rapid to start
        #code.append('\nG0 X %s' % dro_fmt % (2 * x_side * park_x))
        #code.append('G0 Z %s' % dro_fmt % park_z)

        for i in range(1, num_rcuts + 2):


            if i == num_rcuts + 1:
                # ##### Finish Pass
                code.append('\n(Set Finishing Parameters)')
                if is_metric:
                    code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
                else:
                    code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
                code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
                if is_metric:
                    code.append('(Feed Rate - mm/revolution)')
                else:
                    code.append('(Feed Rate - inches/revolution)')
                code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

                code.append('\n(Finish Pass %d)' % i)
            else:
                code.append('\n(Pass %d)' % i)

            # go to chamfer park position
            x_value = 2 * ((x_side * park_x) + trxos)
            code.append('G0 X %s  (chamfer park x)' % dro_fmt % x_value)
            z_value = park_z + trzos
            code.append('G0 Z %s  (chamfer park z)' % dro_fmt % z_value)

            ## go to start base
            #x_value = 2 * ((x_side * start_xlim) + trxos)
            #z_value = start_zlim + trzos
            #code.append('G0 X %s Z %s  (go to base)' % (dro_fmt, dro_fmt) % (x_value, z_value))


            # DoC pass start
            x_value = 2 * ((x_side * start_pnt_list[i][0]) + trxos)
            z_value = start_pnt_list[i][1] + trzos
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) % (x_value, z_value))

            #x_value = 2 * x_side * base_pnt_list[i][0]
            #z_value = base_pnt_list[i][1]
            #code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) % (x_value, z_value))

            x_value = 2 * ((x_side * end_pnt_list[i][0]) + trxos)
            z_value = end_pnt_list[i][1] + trzos
            code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) % (x_value, z_value))

            # go to end base
            ##x_value = 2 * x_side * end_xlim
            z_value = end_zlim + trzos
            #code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) % (x_value, z_value))
            code.append('G0 Z %s' % dro_fmt % z_value)

            x_value = 2 * ((x_side * park_x) + trxos)
            z_value = park_z + trzos
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) % (x_value, z_value))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Chamfer')

        return ok, code

    # ---------------------------------------------------------------------------------
    # Corner Radius
    # ---------------------------------------------------------------------------------
    def ja_edit_radius(self, routine_data):
        return self.ja_edit_general(routine_data)

    def gen_radius_dro_dict(self):
        # ui is a base class attribute
        odl = self.ui.corner_radius_od_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_tool_num_dro'],    'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_rough_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_finish_doc_dro'],  'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_z_start_dro'],     'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_z_end_dro'],       'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_od_dro'],          'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':odl['corner_radius_od_tc_dro'],          'orig' : None , 'mod' : None }),
                             'Corner Radius'            : ({ 'proc': 'unpack_fp',    'ref':None,                                    'orig' : None , 'mod' : None }),
                             'Start Radius'             : ({ 'proc': 'unpack_fp',    'ref':None,                                    'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_chamfer_radius','ref':'radius',                          'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_chamfer_od_id', 'ref':'od',                              'orig' : None, 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,           'ref':odl['corner_radius_od_tool_num_dro'],    'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'External Corner Radius')

    def gen_radius_internal_dro_dict(self):
        # ui is a base class attribute
        idl = self.ui.corner_radius_id_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_tool_num_dro'],    'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_rough_doc_dro'],   'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_finish_doc_dro'],  'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_z_start_dro'],     'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_z_end_dro'],       'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_id_dro'],          'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':idl['corner_radius_id_tc_dro'],          'orig' : None , 'mod' : None }),
                             'Corner Radius'            : ({ 'proc': 'unpack_fp',    'ref':None,                                    'orig' : None , 'mod' : None }),
                             'Start Radius'             : ({ 'proc': 'unpack_fp',    'ref':None,                                    'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_chamfer_radius','ref':'radius',                          'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_chamfer_od_id', 'ref':'id',                              'orig' : None, 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,           'ref':idl['corner_radius_id_tool_num_dro'],    'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Internal Corner Radius')

    def generate_radius_code(self, conv_dro_list, corner_dro_list, od_id):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        chamfer_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True


        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Radius entry error - ' + error)
            ok = False

        # Corner Radius
        if od_id == 'od':
            valid, tool_number, error =  self.validate_param(corner_dro_list['corner_radius_od_tool_num_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, initial_diameter, error =  self.validate_param(corner_dro_list['corner_radius_od_od_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, z_start, error =  self.validate_param(corner_dro_list['corner_radius_od_z_start_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, z_end, error =  self.validate_param(corner_dro_list['corner_radius_od_z_end_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, rough_doc, error  =  self.validate_param(corner_dro_list['corner_radius_od_rough_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, finish_doc, error  =  self.validate_param(corner_dro_list['corner_radius_od_finish_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, tool_clearance, error  =  self.validate_param(corner_dro_list['corner_radius_od_tc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

        else:  # 'id'
            valid, tool_number, error =  self.validate_param(corner_dro_list['corner_radius_id_tool_num_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, initial_diameter, error =  self.validate_param(corner_dro_list['corner_radius_id_id_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, z_start, error =  self.validate_param(corner_dro_list['corner_radius_id_z_start_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, z_end, error =  self.validate_param(corner_dro_list['corner_radius_id_z_end_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, rough_doc, error  =  self.validate_param(corner_dro_list['corner_radius_id_rough_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, finish_doc, error  =  self.validate_param(corner_dro_list['corner_radius_id_finish_doc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

            valid, tool_clearance, error  =  self.validate_param(corner_dro_list['corner_radius_id_tc_dro'])
            if not valid:
                self.error_handler.write('Conversational Radius entry error - ' + error)
                ok = False

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # range_rough = (math.fabs(z_width) * math.sin(angle)) - finish_doc
        # num_rcuts = int(range_rough / rough_doc) + 1
        # rough_DoC_adjusted = (range_rough / num_rcuts)
        z_width = z_end - z_start
        x_base = math.fabs(initial_diameter / 2)
        corner_radius = math.fabs(z_width)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # Set tool working side
        if initial_diameter > 0:
            x_side = 1
            code.append(self._tool_side_msg(x_side))
        elif initial_diameter < 0:
            x_side = -1
            code.append(self._tool_side_msg(x_side))
        else:
            x_side = 0
            msg = 'Conv. Corner Radius entry error - OD can not be 0'
            self.error_handler.write(msg)
            cparse.raise_alarm(corner_dro_list['corner_od_dro'], msg)
            return False, ''

        # Set corner face direction
        if z_width < 0:
            z_side = 1
            face_direction = '(Corner faces away from spindle, Z-)'
        elif z_width > 0:
            z_side = -1
            face_direction = '(Corner faces toward spindle, Z+)'
        else:
            z_side = 0
            msg = 'Conv. Corner Radius entry error - corner radius can not be 0'
            self.error_handler.write(msg)
            cparse.raise_alarm(corner_dro_list['corner_z_start_dro'], msg)
            cparse.raise_alarm(corner_dro_list['corner_z_end_dro'], msg)
            return False, ''

        if od_id == 'od':
            if x_side > 0 and z_side > 0:  # tool orientation should be 2
                expected_tool_orientation = 2
            elif x_side > 0 and z_side < 0:  # tool orientation should be 1
                expected_tool_orientation = 1
            elif x_side < 0 and z_side > 0:  # tool orientation should be 3
                expected_tool_orientation = 3
            elif x_side < 0 and z_side < 0:  # tool orientation should be 4
                expected_tool_orientation = 4
            else :
                expected_tool_orientation = 0
        else:  # 'id'
            if x_side < 0 and z_side > 0:  # tool orientation should be 2
                expected_tool_orientation = 2
            elif x_side < 0 and z_side < 0:  # tool orientation should be 1
                expected_tool_orientation = 1
            elif x_side > 0 and z_side > 0:  # tool orientation should be 3
                expected_tool_orientation = 3
            elif x_side > 0 and z_side < 0:  # tool orientation should be 4
                expected_tool_orientation = 4
            else :
                expected_tool_orientation = 0

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            error_msg = 'Conv. Corner Radius entry error - Tool Orientation\nThe X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the Radius conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))

            if od_id == 'od':
                cparse.raise_alarm(corner_dro_list['corner_radius_od_od_dro'      ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_od_z_start_dro' ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_od_z_end_dro'   ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_od_tool_num_dro'], error_msg)
            else:  # 'id'
                cparse.raise_alarm(corner_dro_list['corner_radius_id_id_dro'      ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_id_z_start_dro' ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_id_z_end_dro'   ], error_msg)
                cparse.raise_alarm(corner_dro_list['corner_radius_id_tool_num_dro'], error_msg)

            return False, ''

        # Set arc direction
        xz_side = x_side * z_side
        if xz_side > 0:
            g2 = 'G2'
            g3 = 'G3'
            g41 = 'G41 (Cutter Compensation Left)'
        elif xz_side < 0:
            g2 = 'G3'
            g3 = 'G2'
            g41 = 'G42 (Cutter Compensation Right)'
        else :
            g2 = '0'
            g3 = '0'
            g41 = '0'

        start_radius = math.sqrt(2 * corner_radius**2)
        end_radius = corner_radius + finish_doc
        radius_range = start_radius - end_radius
        if rough_doc == 0:
            num_rcuts = 0
            doc_adj = 0
        elif end_radius >= start_radius:
            num_rcuts = 0
            doc_adj = 0
        else:
            num_rcuts = int(radius_range / rough_doc) + 1
            doc_adj = (radius_range / num_rcuts)

        # generation details
        radius_type = 'External' if od_id == 'od' else 'Internal'
        self.__write_std_info(code, '%s Corner Radius' % radius_type, g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)
        # list all parameters in output comments
        code.append('(Radius on %s)' % od_id.upper())
        code.append(self._tool_side_msg(x_side))

        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(Rough Depth of Cut = %.4f)' % rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Outside Diameter = %.4f)' % initial_diameter)
        code.append(face_direction)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End Location = %.4f)' % z_end)
        code.append('(Corner Radius = %.4f)' % corner_radius)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        code.append('\n(Start Radius = %.4f)' % start_radius)

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        code.append('\n(Number of roughing passes = %d)' % num_rcuts)
        code.append('(Adjusted roughing DoC = %s)' % dro_fmt % doc_adj)
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        if od_id == 'od':
            x_radius_center = x_base - corner_radius
            z_radius_center = z_start - (z_side * corner_radius)

            # Rapid to start
            code.append('\nG0 X %s' % dro_fmt % (2 * x_side * (x_base + tool_clearance)))
            code.append('G0 Z %s' % dro_fmt % (z_start + (z_side * tool_clearance)))

            for i in range(1, num_rcuts + 1):
                code.append('\n(Pass %d)' % i)
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_radius_center + start_radius - (i * doc_adj)) ,
                              (z_radius_center - (z_side * 2 * tool_radius)))))
                code.append(g41)
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_radius_center + start_radius - (i * doc_adj)) ,
                              (z_radius_center))))
                code.append((g2 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_radius_center),  # destination X
                             (z_radius_center + (z_side * (start_radius - (i * doc_adj)))),  # destination Z
                             (-x_side * (start_radius - (i * doc_adj))),  # offset of center from starting location
                             0))
                code.append('G40 (Turn Cutter Compensation Off)')
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base + tool_clearance)),
                             (z_start + (z_side * tool_clearance))))

            # ##### Finish Pass
            code.append('\n(Set Finishing Parameters)')
            if is_metric:
                code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
            else:
                code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
            code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
            if is_metric:
                code.append('(Feed Rate - mm/revolution)')
            else:
                code.append('(Feed Rate - inches/revolution)')
            code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)
            # Do finish pass
            code.append('\n(Finish Pass)')


            # makes a g-code error if the tool radius is zero so make the lead-in some
            # factor of the part radius
            if tool_radius > 0 :  # normal start and lead-in
                # rapid to finish pass starting position
                code.append('G0 X %s Z %s' %
                            (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base + (2 * tool_radius))),
                             (z_start - (z_side * (corner_radius + (2 * tool_radius))))))
                code.append(g41)
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_base),      # destination X
                             (z_start - (z_side * corner_radius)),     # destination Z
                             (0),          # offset of center from starting location
                             (z_side * (2 * tool_radius))))
            else :  # zero tool radius start and lead-in
                # rapid to finish pass starting position
                code.append('G0 X %s Z %s' %
                            (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base + (.1 * corner_radius))),
                             (z_start - (z_side * (corner_radius + (.1 * corner_radius))))))
                code.append(g41)
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_base),      # destination X
                             (z_start - (z_side * corner_radius)),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (.1 * corner_radius))))

            code.append((g2 + ' X %s Z %s I %s K %s') %
                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                        ((2 * x_side * (x_base - corner_radius)),      # destination X
                         (z_start),     # destination Z
                         (x_side * -corner_radius),          # offset of center from starting location
                         0))

            if tool_radius > 0 :  # normal lead-out
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base - corner_radius - (2 * tool_radius))),      # destination X
                             (z_start + (z_side * (2 * tool_radius))),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (2 * tool_radius))))
            else :  # zero tool radius lead-out
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base - corner_radius - (.1 * corner_radius))),      # destination X
                             (z_start + (z_side * (.1 * corner_radius))),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (.1 * corner_radius))))

            code.append('\nG40 (Turn Cutter Compensation Off)')
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((2 * x_side * (x_base + tool_clearance)),
                         (z_start + (z_side * tool_clearance))))

        else:  # 'id'
            # Set arc direction
            if xz_side < 0:
                g2 = 'G2'
                g3 = 'G3'
                g41 = 'G41 (Cutter Compensation Left)'
            elif xz_side > 0:
                g2 = 'G3'
                g3 = 'G2'
                g41 = 'G42 (Cutter Compensation Right)'
            else :
                g2 = '0'
                g3 = '0'
                g41 = '0'

            x_radius_center = x_base + corner_radius
            z_radius_center = z_start - (z_side * corner_radius)

            # Rapid to start
            code.append('\nG0 X %s' % dro_fmt % (2 * x_side * (x_base - tool_clearance)))
            code.append('G0 Z %s' % dro_fmt % (z_start + (z_side * tool_clearance)))

            for i in range(1, num_rcuts + 1):
                code.append('\n(Pass %d)' % i)
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_radius_center - start_radius + (i * doc_adj)) ,
                              (z_radius_center - (z_side * 2 * tool_radius)))))
                code.append(g41)
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_radius_center - start_radius + (i * doc_adj)) ,
                              (z_radius_center))))
                code.append((g2 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_radius_center),  # destination X
                             (z_radius_center + (z_side * (start_radius - (i * doc_adj)))),  # destination Z
                             (x_side * (start_radius - (i * doc_adj))),  # offset of center from starting location
                             0))
                code.append('G40 (Turn Cutter Compensation Off)')
                code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base - tool_clearance)),
                             (z_start + (z_side * tool_clearance))))

            # ##### Finish Pass
            code.append('\n(Set Finishing Parameters)')
            if is_metric:
                code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
            else:
                code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
            code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))
            if is_metric:
                code.append('(Feed Rate - mm/revolution)')
            else:
                code.append('(Feed Rate - inches/revolution)')
            code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)
            # Do finish pass
            code.append('\n(Finish Pass)')

            # makes a g-code error if the tool radius is zero so make the lead-in some
            # factor of the part radius
            if tool_radius > 0 :  # normal start and lead-in
                # rapid to finish pass starting position
                code.append('G0 X %s Z %s' %
                            (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base - (2 * tool_radius))),
                             (z_start - (z_side * (corner_radius + (2 * tool_radius))))))
                code.append(g41)
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_base),      # destination X
                             (z_start - (z_side * corner_radius)),     # destination Z
                             (0),          # offset of center from starting location
                             (z_side * (2 * tool_radius))))
            else :  # zero tool radius start and lead-in
                # rapid to finish pass starting position
                code.append('G0 X %s Z %s' %
                            (dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base - (.1 * corner_radius))),
                             (z_start - (z_side * (corner_radius + (.1 * corner_radius))))))
                code.append(g41)
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * x_base),      # destination X
                             (z_start - (z_side * corner_radius)),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (.1 * corner_radius))))

            code.append((g2 + ' X %s Z %s I %s K %s') %
                        (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                        ((2 * x_side * (x_base + corner_radius)),      # destination X
                         (z_start),     # destination Z
                         (x_side * corner_radius),          # offset of center from starting location
                         0))

            if tool_radius > 0 :  # normal lead-out
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base + corner_radius + (2 * tool_radius))),      # destination X
                             (z_start + (z_side * (2 * tool_radius))),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (2 * tool_radius))))
            else :  # zero tool radius lead-out
                code.append((g3 + ' X %s Z %s I %s K %s') %
                            (dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                            ((2 * x_side * (x_base + corner_radius + (.1 * corner_radius))),      # destination X
                             (z_start + (z_side * (.1 * corner_radius))),     # destination Z
                             0,          # offset of center from starting location
                             (z_side * (.1 * corner_radius))))

            code.append('\nG40 (Turn Cutter Compensation Off)')
            code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((2 * x_side * (x_base - tool_clearance)),
                         (z_start + (z_side * tool_clearance))))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Corner Radius')

        return ok, code


    # -------------------------------------------------------------------------------
    # Groove Code
    # -------------------------------------------------------------------------------

    def ja_edit_groove_part(self, routine_data):
        restore_data = dict(
            groove_part = 'groove' if self.ui.conv_groove_part == 'groove' else 'part',
            disable_button = self.ui.button_list['groove_part'],
            toggle_proc = getattr(self.ui,'toogle_groove_part_dros'),
            restore_proc = getattr(self, 'ja_restore_groove_page')
        )
        self.ui.conv_groove_part = 'groove' if 'Retract' in routine_data['segment data'] else 'part'
        restore_data['toggle_proc']()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_groove_page(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.conv_groove_part = 'groove' if restore_data['groove_part'] == 'part' else 'part'
        restore_data['toggle_proc']()

    def gen_grooving_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.groove_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_tool_num_dro'],      'orig' : None , 'mod' : None }),
                             'Tool Width'               : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_tw_dro'],            'orig' : None , 'mod' : None }),
                             'Initial Diameter'         : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_stock_dia_dro'],     'orig' : None , 'mod' : None }),
                             'Final Diameter'           : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_final_dia_dro'],     'orig' : None , 'mod' : None }),
                             'Rough Depth of Cut'       : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_rough_doc_dro'],     'orig' : None , 'mod' : None }),
                             'Finish Depth of Cut'      : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_finish_doc_dro'],    'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_z_start_dro'],       'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_z_end_dro'],         'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':pdl['groove_tc_dro'],            'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_groove_part','ref':'groove',                     'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                    : ({ 'proc': None,           'ref':pdl['groove_tool_num_dro'],      'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Groove')

    def generate_groove_code(self, conv_dro_list, groove_dro_list, inifile):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        groove_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, rough_css, error =  self.validate_param(conv_dro_list['conv_rough_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, rough_upr, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(groove_dro_list['groove_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, initial_diameter, error =  self.validate_param(groove_dro_list['groove_stock_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, final_diameter, error =  self.validate_param(groove_dro_list['groove_final_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(groove_dro_list['groove_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, z_end, error =  self.validate_param(groove_dro_list['groove_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, rough_doc, error  =  self.validate_param(groove_dro_list['groove_rough_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, finish_doc, error  =  self.validate_param(groove_dro_list['groove_finish_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(groove_dro_list['groove_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        valid, tool_width, error  =  self.validate_param(groove_dro_list['groove_tw_dro'])
        if not valid:
            self.error_handler.write('Conversational Groove entry error - ' + error)
            ok = False

        rough_doc = math.fabs(rough_doc)
        finish_doc = math.fabs(finish_doc)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # Convert diametric variables to normalized radial
        x_start = math.fabs(initial_diameter / 2)
        x_end = math.fabs(final_diameter / 2)

        # Set tool working side
        if 0 <= final_diameter < initial_diameter:
            x_side = 1
        elif 0 >= final_diameter > initial_diameter:
            x_side = -1
        else:
            x_side = 0
            msg = 'Conversational Groove entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(groove_dro_list['groove_stock_dia_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_final_dia_dro'], msg)
            return False, ''

        groove_width = math.fabs(z_start - z_end)
        gruf_width = groove_width - (2 * finish_doc) - tool_width

        if gruf_width < 0:
            msg = 'Conversational Groove entry error - Finish DOC is too large. Finish DOC can not greater than half the groove width minus the tool width'
            self.error_handler.write(msg)
            cparse.raise_alarm(groove_dro_list['groove_tw_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_finish_doc_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_z_start_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_z_end_dro'], msg)
            return False, ''

        if rough_doc == 0 and finish_doc == 0:
            msg = 'Conversational Groove entry error - Rough DOC and Finish DOC can not both be zero'
            self.error_handler.write(msg)
            cparse.raise_alarm(groove_dro_list['groove_rough_doc_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_finish_doc_dro'], msg)
            return False, ''

        # Feeds cut towards spindle
        if z_start > z_end:
            z_side = 1
        # Feeds cut  away from spindle
        elif z_start < z_end:
            z_side = -1
        else:
            z_side = 0
            msg = 'Conversational Groove entry error - Z values can not be equal'
            self.error_handler.write(msg)
            cparse.raise_alarm(groove_dro_list['groove_z_start_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_z_end_dro'], msg)
            return False, ''

        if rough_doc == 0:
            num_rcuts = 0
            step_width_adjusted = 0
        else:
            num_rcuts = int(abs(gruf_width / rough_doc)) + 1
            step_width_adjusted = (gruf_width / num_rcuts)

        # get the expected tool orientation set basd on the x side of cutting
        expected_tool_orientation = (1,2) if x_side > 0 else (3,4)


        if tool_orientation not in expected_tool_orientation:
            # raise alarms on the offending widgets
            correct_img_orientation = '1_2' if 1 in expected_tool_orientation else '3_4'
            correct_img_orientation = 'orientation_' + correct_img_orientation + '.png'
            correct_str_orientation = '1 or 2' if 1 in expected_tool_orientation else '3 or 4'
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            error_msg = 'The X inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (correct_str_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(groove_dro_list['groove_stock_dia_dro'], error_msg)
            cparse.raise_alarm(groove_dro_list['groove_final_dia_dro'], error_msg)
            cparse.raise_alarm(groove_dro_list['groove_tool_num_dro'], error_msg)
            self.error_handler.write('Conversational Groove entry error - Tool Orientation')
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(correct_img_orientation)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X inputs in the Groove conversational call for orientation %s:' % correct_str_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        g53_x_max = 2 * float(inifile.find('AXIS_0', 'MAX_LIMIT'))
        g53_x_min = 2 * float(inifile.find('AXIS_0', 'MIN_LIMIT'))


        # generation details
        self.__write_std_info(code, 'Groove', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)
        code.append('(Tool Width = %s)' % dro_fmt % tool_width)
        code.append('\n(Rough CSS = %.0f %s)' % (rough_css, css_units))
        code.append('(Rough Feed ' + units + '/revolution = %.4f)' % rough_upr)
        code.append('(Rough Depth of Cut = %.4f)' % rough_doc)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)
        code.append('(Finish Depth of Cut = %.4f)' % finish_doc)

        code.append('\n(Initial Diameter = %.4f)' % initial_diameter)
        code.append('(Final Diameter = %.4f)' % final_diameter)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Z End  Location = %.4f)' % z_end)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        # List tool working side

        if x_side == 0:  # already checked above
            self.error_handler.write('Conversational Groove entry error - X axis working side unknown')
            return False, ''
        code.append(self._tool_side_msg(x_side))

        if gruf_width < 0:
            msg = 'Conversational Groove entry error - Groove is too narrow to fit tool and finish cuts'
            self.error_handler.write(msg)
            cparse.raise_alarm(groove_dro_list['groove_z_start_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_z_end_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_finish_doc_dro'], msg)
            cparse.raise_alarm(groove_dro_list['groove_tw_dro'], msg)
            return False, ''

        # List groove cut direction
        if z_side == 1:
            code.append('(Cuts progress toward spindle, Z-)')
        elif z_side == -1:
            code.append('(Cuts progress away from spindle, Z+)')
        else:  # already checked above
            self.error_handler.write('Conversational Groove entry error - Width can not be 0')
            return False, ''

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')
        code.append('\n(Step Width = %.4f)' % (step_width_adjusted))
        code.append('(Number of Cuts = %d)' % (num_rcuts))
        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (rough_css, max_spindle_rpm))
        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % rough_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        z_range_finish = math.fabs(z_end - z_start) - tool_width
        # just shift over the whole groove by the width of the tool
        # if the zero point is on the other side...
        if tool_orientation in (2,3):
            z_start -= tool_width*z_side
            z_end -= tool_width*z_side

        #Move tool to safe starting position
        code.append('\nG0 X %s' % dro_fmt % (2 * x_side* (x_start + tool_clearance)))
        code.append('G0 Z %s' % dro_fmt % (z_start - (z_side * finish_doc)))

        # First Cut
        code.append('G1 X %s' % dro_fmt % (2 * x_side * (x_end + finish_doc)))
        # Retract
        code.append('G0 X %s' % dro_fmt %
                    (2 * x_side* (x_start + tool_clearance)))

        lcnt = 1
        while lcnt <= num_rcuts:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(Pass %d)' % lcnt)
            code.append('G0 Z %s' % dro_fmt %
                        (z_start - (z_side * finish_doc) - (z_side * lcnt * step_width_adjusted)))
            code.append('G1 X %s' % dro_fmt % (2 * x_side * (x_end + finish_doc)))
            code.append('G0 X %s' % dro_fmt % (2 * x_side* (x_start + tool_clearance)))

            # Do it again
            lcnt += 1

        # feed finish cut
        code.append('\n(Set Finishing Parameters)')

        if is_metric:
            code.append('\n(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))

        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\n(Finish Pass)')

        z_middle = z_start - (z_side * z_range_finish / 2)
        code.append('(Z Mid = %s)' % dro_fmt % z_middle)

        code.append('G0 X %s Z %s' % (dro_fmt, dro_fmt) %  # top, first side
                    ((2 * x_side * (x_start + tool_clearance)), (z_end + (z_side * tool_width))))
        code.append('G1 X %s' % dro_fmt % (2 * x_side * x_end))  #bottom
        code.append('G1 Z %s' % dro_fmt % z_middle)  #across 1/2
        code.append('G0 X %s' % dro_fmt % (2 * x_side * (x_start + tool_clearance))) #top, middle

        code.append('G0 Z %s' % dro_fmt % z_start)  #top, other side
        code.append('G1 X %s' % dro_fmt % (2 * x_side * x_end))  #bottom
        code.append('G1 Z %s' % dro_fmt % z_middle)  #across 1/2

        code.append('\nG0 X %s' % dro_fmt % (2 * x_side * (x_start + tool_clearance))) #top, middle

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Groove')

        return ok, code


    # -------------------------------------------------------------------------------
    # Parting Code
    # -------------------------------------------------------------------------------

    def ja_edit_parting(self, routine_data):
        return self.ja_edit_general(routine_data)

    def gen_parting_dro_dict(self):
        # ui is a base class attribute
        pdl = self.ui.part_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':pdl['part_tool_num_dro'],        'orig' : None , 'mod' : None }),
                             'Initial Diameter'         : ({ 'proc': 'unpack_fp',    'ref':pdl['part_stock_dia_dro'],       'orig' : None , 'mod' : None }),
                             'Final Diameter'           : ({ 'proc': 'unpack_fp',    'ref':pdl['part_final_dia_dro'],       'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':pdl['part_z_start_dro'],         'orig' : None , 'mod' : None }),
                             'Edge Breaking Width'      : ({ 'proc': 'unpack_fp',    'ref':pdl['part_ebw_dro'],             'orig' : None , 'mod' : None }),
                             'Retract'                  : ({ 'proc': 'unpack_fp',    'ref':pdl['part_retract_dro'],         'orig' : None , 'mod' : None }),
                             'Peck'                     : ({ 'proc': 'unpack_fp',    'ref':pdl['part_peck_dro'],            'orig' : None , 'mod' : None }),
                             'Tool Width'               : ({ 'proc': 'unpack_fp',    'ref':pdl['part_tw_dro'],              'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':pdl['part_tc_dro'],              'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_groove_part','ref':'part',                       'orig' : None, 'ja_diff' : 'no' },),
                             'focus'                    : ({ 'proc': None,           'ref':pdl['part_tool_num_dro'],        'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Parting')

    def generate_part_code(self, conv_dro_list, part_dro_list, inifile):
        """generate_od_turn function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        groove_dro_list is a list of gtk.entry widgets that contain values specific to od turning.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, max_spindle_rpm, error =  self.validate_param(conv_dro_list['conv_max_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, finish_css, error  =  self.validate_param(conv_dro_list['conv_finish_sfm_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, finish_upr, error  =  self.validate_param(conv_dro_list['conv_finish_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(part_dro_list['part_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, initial_diameter, error =  self.validate_param(part_dro_list['part_stock_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, final_diameter, error =  self.validate_param(part_dro_list['part_final_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(part_dro_list['part_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(part_dro_list['part_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, peck, error  =  self.validate_param(part_dro_list['part_peck_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, retract, error  =  self.validate_param(part_dro_list['part_retract_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, break_width, error  =  self.validate_param(part_dro_list['part_ebw_dro'], is_metric)
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False

        valid, tool_width, error  =  self.validate_param(part_dro_list['part_tw_dro'])
        if not valid:
            self.error_handler.write('Conversational Parting entry error - ' + error)
            ok = False



        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)
        break_width_max = min(tool_width * .4,.07)
        if is_metric: break_width_max *= 25.4

        # Convert diametric variables to normalized radial
        x_start = math.fabs(initial_diameter / 2)
        x_end = math.fabs(final_diameter / 2)
        x_overrun = math.fabs((tool_radius + (tool_radius*0.1)) / 2)

        cp_tail = (1,4)
        # Set tool working side
        if 0 <= final_diameter < initial_diameter:
            x_side = 1
            expected_tool_orientation = (1,2)
        elif 0 >= final_diameter > initial_diameter:
            x_side = -1
            expected_tool_orientation = (3,4)
        else:
            x_side = 0
            expected_tool_orientation = 0
            msg = 'Conversational Parting entry error - Start dia. must be larger than end dia. and both positive or both negative'
            self.error_handler.write(msg)
            cparse.raise_alarm(part_dro_list['part_stock_dia_dro'], msg)
            cparse.raise_alarm(part_dro_list['part_final_dia_dro'], msg)
            return False, ''

        if tool_orientation not in expected_tool_orientation:
            # raise alarms on the offending widgets
            correct_img_orientation = '1_2' if 1 in expected_tool_orientation else '3_4'
            correct_str_orientation = '1 or 2' if 1 in expected_tool_orientation else '3 or 4'
            error_msg = 'The X inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (correct_str_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(part_dro_list['part_stock_dia_dro'], error_msg)
            cparse.raise_alarm(part_dro_list['part_final_dia_dro'], error_msg)
            cparse.raise_alarm(part_dro_list['part_tool_num_dro'], error_msg)
            expected_tool_orientation_image = get_tool_orientation_image(correct_img_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational Parting entry error - Tool Orientation')
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X inputs in the Part conversational call for orientation %s:' % correct_str_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        x_range = math.fabs(x_end - x_start)

        if peck == 0:
            num_pecks = 0
            peck_adjusted = 0
        else:
            num_pecks = int(x_range / peck) + 1
            peck_adjusted = math.fabs((x_range + x_overrun) / num_pecks)


        # break_width checks already done in validation section. these may never get triggered
        if break_width > break_width_max:  # If the chamfer is wider than the tool width, cutting will happen on the tool's side and can not be allowed
            msg = 'Conversational Parting entry error - Edge breaking width is too large, consider using Chamfer'
            self.error_handler.write(msg)
            cparse.raise_alarm(part_dro_list['part_ebw_dro'], msg)
            return False, ''
        if break_width < 0:
            msg = 'Conversational Parting entry error - Edge breaking width cannot be negitive'
            self.error_handler.write(msg)
            cparse.raise_alarm(part_dro_list['part_ebw_dro'], msg)
            return False, ''

        # Maybe leave this out, the worst that could happen is the part gets parted without an edge break
        # if (x_range * .3) < ((2 * break_width) + tool_radius):
        #    self.error_handler.write('Conversational Parting entry error - There may not enough material left to allow cutting the edge break, make break width smaller or consider using Chamfer')

        do_break = True if 0 < break_width <= break_width_max else False

        g53_x_max = 2 * float(inifile.find('AXIS_0', 'MAX_LIMIT'))
        g53_x_min = 2 * float(inifile.find('AXIS_0', 'MIN_LIMIT'))


        # generation details
        self.__write_std_info(code, 'Parting', g20_g21, units, work_offset, tool_number, tool_radius, max_spindle_rpm)
        code.append('(Tool Width = %s)' % dro_fmt % tool_width)

        code.append('\n(Finish CSS = %.0f %s)' % (finish_css, css_units))
        code.append('(Finish Feed ' + units + '/revolution = %.4f)' % finish_upr)

        code.append('\n(Initial Diameter = %.4f)' % initial_diameter)
        code.append('(Final Diameter = %.4f)' % final_diameter)
        code.append('(Retract = %.4f)' % retract)
        code.append('(Peck = %.4f)' % peck)
        code.append('(Z Start Location = %.4f)' % z_start)
        code.append('(Edge Breaking Width = %.4f)' % break_width)

        code.append('(Tool Clearance = %.4f)' % tool_clearance)

        # adjust z by the tool_width
        z_start -= 0 if tool_orientation in cp_tail else tool_width

        # List tool working side
        if x_side == 0:  # already checked above
            self.error_handler.write('Conversational Parting entry error - X axis working side unknown')
            return False, ''
        code.append(self._tool_side_msg(x_side))

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Set spindle and feed rate
        code.append('\n(Set Roughing Parameters)')

        if is_metric:
            code.append('(CSS, Spindle - meters/minute, Maximum RPM)')
        else:
            code.append('(CSS, Spindle - feet/minute, Maximum RPM)')
        code.append('G96 S %.0f D %.0f' % (finish_css, max_spindle_rpm))

        if is_metric:
            code.append('(Feed Rate - mm/revolution)')
        else:
            code.append('(Feed Rate - inches/revolution)')
        code.append('G95 F %s (Units per Revolution Mode)' % dro_fmt % finish_upr)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        #Move tool to safe starting position
        code.append('\nG0 X %s' % dro_fmt % (2 * x_side* (x_start + tool_clearance)))
        code.append('G0 Z %s' % dro_fmt % (z_start))

        if do_break:
            tool_comp_xz = 2 * (tool_radius - (tool_radius * (math.sqrt(2) / 2)))
            x_pos = x_start - break_width - tool_comp_xz
            code.append('G1 X %s' % dro_fmt % (2 * x_side * x_pos))
            x_pos = x_start + tool_clearance
            code.append('G0 X %s' % dro_fmt % (2 * x_side * x_pos))
            code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance + break_width + tool_comp_xz))
            x_pos = x_start - break_width - tool_comp_xz
            code.append('G1 X %s Z %s' % (dro_fmt, dro_fmt) % ((2 * x_side * x_pos), z_start))
            code.append('G0 X %s' % dro_fmt % (2 * x_side* (x_start + tool_clearance)))

        if peck == 0:  # ~~~~~~ No peck, cut in one pass ~~~~~~
            code.append('G1 X %s' % dro_fmt % (2 * x_side * (x_end + x_overrun)))
            code.append('G0 X %s' % dro_fmt % (2 * x_side* (x_start + tool_clearance)))
        else:  #  ~~~~~~ Yes, do pecking ~~~~~~
            lcnt = 1
            while lcnt < num_pecks:
                # infinite loop guard
                if len(code) > CONVERSATIONAL_MAX_LINES:
                    raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

                code.append('\n(Peck %d)' % lcnt)
                code.append('G1 X %s' % dro_fmt % (2 * x_side * (x_start - (peck_adjusted * lcnt))))
                code.append('G0 X %s' % dro_fmt % (2 * x_side * (x_start - (peck_adjusted * lcnt) + retract)))
                lcnt += 1

            code.append('\n(Peck %d)' % lcnt)
            code.append('G1 X %s' % dro_fmt % (2 * x_side * (x_start - (peck_adjusted * lcnt))))
            code.append('G0 X %s' % dro_fmt % (2 * x_side * (x_start + tool_clearance)))
        # ~~~~~~ end o pecking, or not

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Parting')

        return ok, code


    # -------------------------------------------------------------------------------
    # Drill code
    # -------------------------------------------------------------------------------

    def ja_edit_drilltap(self, routine_data):
        restore_data = dict(
            drill_tap = 'drill' if self.ui.conv_drill_tap == 'drill' else 'tap',
            disable_button = self.ui.button_list['drill_tap'],
            toggle_proc = getattr(self.ui,'toggle_drill_tap_button'),
            restore_proc = getattr(self, 'ja_restore_drilltap_page')
        )
        self.ui.conv_drill_tap = 'drill' if 'Pitch' in routine_data['segment data'] else 'tap'
        restore_data['toggle_proc']()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_drilltap_page(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.conv_drill_tap = 'drill' if restore_data['drill_tap'] == 'tap' else 'tap'
        restore_data['toggle_proc']()

    def gen_drilling_dro_dict(self):
        # ui is a base class attribute
        ddl = self.ui.drill_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_tool_num_dro'],       'orig' : None , 'mod' : None }),
                             'Spindle RPM'              : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_spindle_rpm_dro'],    'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_z_start_dro'],        'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_z_end_dro'],          'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_tc_dro'],             'orig' : None , 'mod' : None }),
                             'Hole Depth'               : ({ 'proc': 'unpack_fp',    'ref':None,                            'orig' : None , 'mod' : None }),
                             'Peck Depth'               : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_peck_dro'],           'orig' : None , 'mod' : None }),
                             'Hole Bottom Dwell'        : ({ 'proc': 'unpack_fp',    'ref':ddl['drill_dwell_dro'],          'orig' : None , 'mod' : None }),
                             'focus'                    : ({ 'proc': None,           'ref':ddl['drill_tool_num_dro'],       'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Drilling',('Rough Feed','Feed'),('CSS Max. Spindle RPM','Tool Radius','Rough CSS','Finish CSS','Finish Feed'))


    def generate_drill_code(self, conv_dro_list, drill_dro_list):
        """generate_drill_code function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        drill_tap_dro_list is a list of gtk.entry widgets that contain values specific to drilling.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, feed_per_rev, error =  self.validate_param(conv_dro_list['conv_rough_fpr_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(drill_dro_list['drill_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(drill_dro_list['drill_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, rpm, error  =  self.validate_param(drill_dro_list['drill_spindle_rpm_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, peck_depth, error  =  self.validate_param(drill_dro_list['drill_peck_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, dwell, error  =  self.validate_param(drill_dro_list['drill_dwell_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(drill_dro_list['drill_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        valid, z_end, error  =  self.validate_param(drill_dro_list['drill_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Drill entry error - ' + error)
            ok = False

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # tool orientation should be 7
        expected_tool_orientation = 7

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational Drill entry error - Tool Orientation')
            error_msg = 'The Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(drill_dro_list['drill_tool_num_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the Drill conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        if z_start <= z_end:
            msg = 'Conversational Drill entry error - Z Start should be larger than Z End'
            cparse.raise_alarm(drill_dro_list['drill_z_start_dro'], msg)
            cparse.raise_alarm(drill_dro_list['drill_z_end_dro'], msg)
            self.error_handler.write(msg, ALARM_LEVEL_MEDIUM)
            return False, ''

        hole_depth = math.fabs(z_end - z_start)
        peck_depth = math.fabs(peck_depth)

        # generation details
        self.__write_std_info(code, 'Drilling', g20_g21, units, work_offset, tool_number, tool_radius, axial=True)

        code.append('\n(Spindle RPM = %.1f)' % rpm)
        code.append('(Feed is' + units + '/revolution = %.4f)' % feed_per_rev)

        code.append('\n(Z Start Location = %.4f)' % z_start)
        code.append('(Z End Location = %.4f)' % z_end)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)
        code.append('(Hole Depth = %.4f)' % hole_depth)
        code.append('(Peck Depth = %.4f)' % peck_depth)
        code.append('(Hole Bottom Dwell = %.2f)' % dwell)

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # feed rate
        code.append('\nG95 F %s (Units per Revolution Mode)' % dro_fmt % feed_per_rev)

        code.append('G97 (RPM Mode On, CSS Off)')
        code.append('S %d (RPM)' % rpm)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        if peck_depth == 0:
            num_pecks = 0  # bypasses loop
            peck_adjusted = 0
        else:
            num_pecks = int(hole_depth / peck_depth) + 1
            peck_adjusted = math.fabs(hole_depth / num_pecks)

        code.append('\n(Number of pecks = %d)' % num_pecks)
        code.append('(Adjusted peck depth = %s)' % dro_fmt % peck_adjusted)

        # Move tool to start of hole plus clearance
        code.append('\nG0 X %s' % dro_fmt % 0)
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        lcnt = 1
        while lcnt < num_pecks:
            # infinite loop guard
            if len(code) > CONVERSATIONAL_MAX_LINES:
                raise RuntimeError("Max g-code program lines of %d reached, most likely due to a PathPilot defect in conversational parameter processing." % CONVERSATIONAL_MAX_LINES)

            code.append('\n(Peck - Pass %d)' % lcnt)
            code.append('G1 Z %s' % dro_fmt % (z_start - (peck_adjusted * lcnt)))
            code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))
            code.append('G0 Z %s' % dro_fmt % (z_start - (peck_adjusted * lcnt) + .01))
            lcnt += 1

        code.append('\n(Finish - Pass %d)' % lcnt)
        #code.append(('G1 Z %s' % (dro_fmt)) % (z_start - (peck_adjusted * lcnt)))
        code.append('G1 Z %s' % dro_fmt % z_end)
        code.append('G4 P %s' % dro_fmt % dwell)

        code.append('\nG0 Z %s' % dro_fmt % (z_start + tool_clearance))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Drill')

        return ok, code


    # -------------------------------------------------------------------------------
    # Tap code
    # -------------------------------------------------------------------------------


    def ja_edit_tap(self, routine_data):
        return self.ja_edit_general(routine_data)

    def gen_tap_dro_dict(self):
        # ui is a base class attribute
        cdl = self.ui.conv_dro_list
        tdl = self.ui.tap_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_tool_num_dro'],     'orig' : None , 'mod' : None }),
                             'Spindle RPM'              : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_spindle_rpm_dro'],  'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_z_start_dro'],      'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_z_end_dro'],        'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_tc_dro'],           'orig' : None , 'mod' : None }),
                             'Peck Depth'               : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_peck_dro'],         'orig' : None , 'mod' : None }),
                             'Threads per'              : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_tpu_dro'],          'orig' : None , 'mod' : None }),
                             'Pitch'                    : ({ 'proc': 'unpack_fp',    'ref':tdl['tap_pitch_dro'],        'orig' : None , 'mod' : None }),
                             'Thread Depth'             : ({ 'proc': 'unpack_fp',    'ref':None,                        'orig' : None , 'mod' : None }),
                             'focus'                    : ({ 'proc': None,           'ref':tdl['tap_tool_num_dro'],     'ja_diff' : 'no' })
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Tapping',None,('CSS Max. Spindle RPM','Tool Radius','Rough CSS','Rough Feed','Finish CSS','Finish Feed'))

    def generate_tap_code(self, conv_dro_list, tap_dro_list, pitch, max_vel):
        """generate_tap_code function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        drill_tap_dro_list is a list of gtk.entry widgets that contain values specific to drilling/tapping.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        # empty python list for g code
        code = []

        # errors
        ok = True

        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(tap_dro_list['tap_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(tap_dro_list['tap_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, rpm, error  =  self.validate_param(tap_dro_list['tap_spindle_rpm_dro'], is_metric, pitch, max_vel)
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, pitch, error  =  self.validate_param(tap_dro_list['tap_pitch_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, tpu, error  =  self.validate_param(tap_dro_list['tap_tpu_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(tap_dro_list['tap_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, z_end, error  =  self.validate_param(tap_dro_list['tap_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        valid, peck_depth, error  =  self.validate_param(tap_dro_list['tap_peck_dro'])
        if not valid:
            self.error_handler.write('Conversational Tap entry error - ' + error)
            ok = False

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)
        unit = 'mm' if is_metric else 'inch'

        if tpu == 0:  # divide by zero protection
            pitch = 1000000
        else:
            pitch = 1 / tpu

        if z_start <= z_end:
            msg = 'Conversational Tap entry error - Z Start should be larger than Z End'
            cparse.raise_alarm(tap_dro_list['tap_z_start_dro'], msg)
            cparse.raise_alarm(tap_dro_list['tap_z_end_dro'], msg)
            self.error_handler.write(msg, ALARM_LEVEL_MEDIUM)
            return False, ''

        thread_depth = math.fabs(z_end - z_start)

        # tool orientation should be 7
        expected_tool_orientation = 7

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational Tap entry error - Tool Orientation')
            error_msg = 'The X and Z inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(tap_dro_list['tap_tool_num_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the Tap conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        z_list = []
        num_pecks = 0.0
        peck_adjusted = 0.0
        if peck_depth > 0:
            num_pecks = int((thread_depth / peck_depth) + .99)
            peck_adjusted = math.fabs(thread_depth / num_pecks)
            for zi in range(1, num_pecks):
                z_list.append(z_start - (zi * peck_adjusted))
        z_list.append(z_end)

        # generation details
        self.__write_std_info(code, 'Tapping', g20_g21, units, work_offset, tool_number, tool_radius, axial=True)
        message = '(Tapping G-code generated:)\n(   %s)' % (time.asctime(time.localtime(time.time())))

        code.append('\n(Spindle RPM =  %.1f)' % rpm)

        code.append('\n(Z Start Location = %.4f)' % z_start)
        code.append('(Z End Location = %.4f)' % z_end)
        code.append('(Tool Clearance = %.4f)' % tool_clearance)
        code.append('(Thread Depth = %.4f)' % thread_depth)
        code.append('(Pitch = %.4f %s/thread)' % (pitch, units))
        code.append('(Threads per %s = %.2f)' % (unit, tpu))
        code.append('(Peck Depth = %.4f)' % peck_depth)
        code.append('(%d Pecks at Depth = %.4f)' % (num_pecks, peck_adjusted))
        # code.append('(Thread Direction = %s hand)' % right_left_thread)

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Note: turn CSS Off, RPM mode On
        # This is similar to the Drill method except the spindle and Z axis have
        # coordinated motion.
        # The Peck feature may be used to clear chips from the tap before reaching
        # the end of the threaded section.

        # Set spindle to RPM mode
        code.append('G97 (RPM Mode On, CSS Off)')
        code.append('S %d' % rpm)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        code.append('M3 (Spindle ON, Forward)')

        # Move tool to start of hole plus clearance
        code.append('\nG0 X %s' % dro_fmt % 0)
        code.append('G0 Z %s' % dro_fmt % (z_start + tool_clearance))

        for zi in z_list:
            code.append('G33.1 Z %s K %s' % (dro_fmt, dro_fmt) % (zi, pitch))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Tap')

        return ok, code


    # -------------------------------------------------------------------------------
    # Thread code
    # -------------------------------------------------------------------------------

    def ja_edit_thread(self, routine_data):
        restore_data = dict(
            ext_int = self.ui.conv_thread_ext_int,
            rh_lh = self.ui.conv_thread_rh_lh,
            disable_button = self.ui.button_list['thread_ext_int'],
            toggle_proc = (getattr(self.ui,'toggle_thread_external_internal_button'),getattr(self.ui,'toggle_thread_rh_lh_button')),
            restore_proc = getattr(self, 'ja_restore_thread_page')
        )
        try:
            type_str = routine_data['segment data']['title']['ref']
            if 'External' in type_str or 'Internal' in type_str:
                self.ui.conv_thread_ext_int = 'external' if 'Internal' in type_str else 'internal'
            else:
                tool_orientation = int(routine_data['segment data']['Tool Orientation']['orig'])
                minor_diameter = int(routine_data['segment data']['Inside Diameter']['orig'])
                major_diameter = int(routine_data['segment data']['Outside Diameter']['orig'])
                if minor_diameter < 0 and major_diameter < 0:
                    self.ui.conv_thread_ext_int = 'external' if tool_orientation == 6 else 'internal'
                if minor_diameter > 0 and major_diameter > 0:
                    self.ui.conv_thread_ext_int = 'external' if tool_orientation == 8 else 'internal'
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('ja_edit_thread: counld not determine internal or external thread.  Traceback: %s' % traceback_txt)

        thread_dir = routine_data['segment data']['Thread Direction']['mod']
        # load 'revert'
        segment_data = routine_data['segment data']
        revert_data = None if not routine_data['segment data'].has_key('revert') else routine_data['segment data']['revert']
        if revert_data is not None:
            for n,item in enumerate(revert_data):
                if item.has_key('attr'):
                    if item['attr'] == 'conv_thread_rh_lh' and item['ref'] is None: item['ref'] = 'lh' if 'left' in thread_dir.lower() else 'rh'
        self.ui.conv_thread_rh_lh = 'rh' if 'left' in thread_dir.lower() else 'lh'
        for n in range(len(restore_data['toggle_proc'])): restore_data['toggle_proc'][n]()
        conversational.ja_toggle_buttons([restore_data['disable_button']])
        self.ja_edit_general(routine_data)
        return restore_data

    def ja_restore_thread_page(self, restore_data):
        conversational.ja_toggle_buttons([restore_data['disable_button']],'on')
        self.ui.conv_thread_ext_int = 'internal' if restore_data['ext_int'] == 'external' else 'external'
        self.ui.conv_thread_rh_lh = 'lh' if restore_data['rh_lh'] == 'rh' else 'rh'
        for n in range(len(restore_data['toggle_proc'])): restore_data['toggle_proc'][n]()

    def gen_external_thread_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.thread_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tool_num_dro'],           'orig' : None , 'mod' : None }),
                             'Spindle RPM'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_spindle_rpm_dro'],        'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_z_start_dro'],            'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_z_end_dro'],              'orig' : None , 'mod' : None }),
                             'Thread Direction'         : ({ 'proc': 'unpack_stl',   'ref':'thread_rh_lh_to_str',                'orig' : None , 'mod' : None }),
                             'Thread Specification'     : ({ 'proc': 'unpack_cmt',   'ref':getattr(self.ui,'thread_combo_spec'), 'orig' : None , 'mod' : None }),
                             'Inside Diameter'          : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_minor_dia_dro'],          'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_major_dia_dro'],          'orig' : None , 'mod' : None }),
                             'Taper'                    : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_taper_dro'],              'orig' : None , 'mod' : None }),
                             'Pitch'                    : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_pitch_dro'],              'orig' : None , 'mod' : None }),
                             'Threads per'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tpu_dro'],                'orig' : None , 'mod' : None }),
                             'Depth of Cut'             : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_doc_dro'],                'orig' : None , 'mod' : None }),
                             'Thread Lead'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_lead_dro'],               'orig' : None , 'mod' : None }),
                             'Thread Length'            : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Number of passes'         : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Effective Thread Length'  : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tc_dro'],                 'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_thread_ext_int','ref':'external',                     'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_thread_rh_lh',  'ref':None,                           'orig' : None, 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,           'ref':tdl['thread_tool_num_dro'],           'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'External Threading',None,('CSS Max. Spindle RPM','Tool Radius','Rough CSS','Rough Feed','Finish CSS','Finish Feed'))

    def gen_internal_thread_dro_dict(self):
        # ui is a base class attribute
        tdl = self.ui.thread_dro_list
        dro_to_text_data = { # specific DROs
                             'Tool Number'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tool_num_dro'],           'orig' : None , 'mod' : None }),
                             'Spindle RPM'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_spindle_rpm_dro'],        'orig' : None , 'mod' : None }),
                             'Z Start Location'         : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_z_start_dro'],            'orig' : None , 'mod' : None }),
                             'Z End Location'           : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_z_end_dro'],              'orig' : None , 'mod' : None }),
                             'Thread Direction'         : ({ 'proc': 'unpack_stl',   'ref':'thread_rh_lh_to_str',                'orig' : None , 'mod' : None }),
                             'Thread Specification'     : ({ 'proc': 'unpack_cmt',   'ref':getattr(self.ui,'thread_combo_spec'), 'orig' : None , 'mod' : None }),
                             'Inside Diameter'          : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_minor_dia_dro'],          'orig' : None , 'mod' : None }),
                             'Outside Diameter'         : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_major_dia_dro'],          'orig' : None , 'mod' : None }),
                             'Taper'                    : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_taper_dro'],              'orig' : None , 'mod' : None }),
                             'Pitch'                    : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_pitch_dro'],              'orig' : None , 'mod' : None }),
                             'Threads per'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tpu_dro'],                'orig' : None , 'mod' : None }),
                             'Depth of Cut'             : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_doc_dro'],                'orig' : None , 'mod' : None }),
                             'Thread Lead'              : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_lead_dro'],               'orig' : None , 'mod' : None }),
                             'Thread Length'            : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Number of passes'         : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Effective Thread Length'  : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Hole ID'                  : ({ 'proc': 'unpack_fp',    'ref':None,                                 'orig' : None , 'mod' : None }),
                             'Tool Clearance'           : ({ 'proc': 'unpack_fp',    'ref':tdl['thread_tc_dro'],                 'orig' : None , 'mod' : None }),
                             'revert'                   : ({ 'attr': 'conv_thread_ext_int','ref':'internal',                     'orig' : None, 'ja_diff' : 'no' },
                                                           { 'attr': 'conv_thread_rh_lh',  'ref':None,                           'orig' : None, 'ja_diff' : 'no' }),
                             'focus'                    : ({ 'proc': None,           'ref':tdl['thread_tool_num_dro'],           'ja_diff' : 'no'})
                           }
        return self.gen_common_dro_dict(dro_to_text_data,'Internal Threading',None,('CSS Max. Spindle RPM','Tool Radius','Rough CSS','Rough Feed','Finish CSS','Finish Feed'))


    def generate_thread_code(self, conv_dro_list, thread_dro_list, ext_int_thread, inifile, sup_note, pitch, max_vel):
        """generate_thread_code function takes two lists of gtk.entry objects as arguments:
        conv_dro_list is a list of gtk.entry widgets that contain values common to all turning routines.
        thread_dro_list is a list of gtk.entry widgets that contain values specific to threading.
        On suscessful execution this function returns True with a list object that makes up the g code output.
        On failure this function returns false with a list object containing the error message(s)."""

        using_M4_lhthread = False
        # empty python list for g code
        code = []

        # errors
        ok = True

        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210

        # validate params, assign to local variables, record error if validation fails
        title  = self.get_conv_title(conv_dro_list)

        valid, work_offset, error =  self.validate_param(conv_dro_list['conv_work_offset_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, tool_number, error =  self.validate_param(thread_dro_list['thread_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, z_start, error =  self.validate_param(thread_dro_list['thread_z_start_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, z_end, error =  self.validate_param(thread_dro_list['thread_z_end_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, rpm, error  =  self.validate_param(thread_dro_list['thread_spindle_rpm_dro'], is_metric, pitch, max_vel)
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, minor_dia, error  =  self.validate_param(thread_dro_list['thread_minor_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, major_dia, error  =  self.validate_param(thread_dro_list['thread_major_dia_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, pitch, error  =  self.validate_param(thread_dro_list['thread_pitch_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, doc, error  =  self.validate_param(thread_dro_list['thread_doc_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, tool_clearance, error  =  self.validate_param(thread_dro_list['thread_tc_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, tpu, error  =  self.validate_param(thread_dro_list['thread_tpu_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, lead, error  =  self.validate_param(thread_dro_list['thread_lead_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        valid, taper, error  =  self.validate_param(thread_dro_list['thread_taper_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
            ok = False

        active_thread_text = self.ui.thread_chart_combobox.get_active_text()

        thread_length = math.fabs(z_end - z_start)
        if z_start < z_end:
            # raise alarms on the offending widgets
            msg = 'Conversational Thread entry error - Z Start must be greater than Z End'
            cparse.raise_alarm(thread_dro_list['thread_z_start_dro'], msg)
            cparse.raise_alarm(thread_dro_list['thread_z_end_dro'], msg)
            self.error_handler.write(msg, ALARM_LEVEL_MEDIUM)
            return False,''

        z_start_report = z_start
        z_end_report = z_end
        if self.ui.conv_thread_rh_lh == 'lh' and not using_M4_lhthread:
            z_tmp = z_end
            z_end = z_start
            z_start = z_tmp

        # get tool information
        tool_orientation = self.status.tool_table[tool_number].orientation
        tool_type = self.get_tool_type(tool_number)

        # set the correct number of decimal places
        is_metric, g20_g21, dro_fmt, feed_fmt, units, css_units, round_off, tool_radius = self.conv_data_common(tool_number)
        unit = 'mm' if is_metric else 'inch'

        # G76 parameters follow the lathe radius or diameter setting
        i_offset = 2 * tool_clearance

        depth = math.fabs(tool_clearance) + math.fabs(doc)
        full_dia_depth = math.fabs(tool_clearance)
        cut_increment = math.fabs(doc)
        k_number = math.fabs(major_dia - minor_dia)
        end_depth = math.fabs(k_number) + math.fabs(tool_clearance)
        degression = 2

        tpass = self.calc_num_threading_passes(depth, end_depth, full_dia_depth, cut_increment, degression)
        if tpass > THREAD_MAX_PASSES:
            msg = "Number of passes must be less than {}".format(THREAD_MAX_PASSES)
            self.error_handler.write(msg, ALARM_LEVEL_LOW)
            cparse.raise_alarm(thread_dro_list['thread_pass_dro'], msg)
            cparse.raise_alarm(thread_dro_list['thread_doc_dro'], msg)
            return False,''

        g53_x_max = 2 * float(inifile.find('AXIS_0', 'MAX_LIMIT'))
        g53_x_min = 2 * float(inifile.find('AXIS_0', 'MIN_LIMIT'))


        # generation details
        type_str = 'External' if ext_int_thread == 'external' else 'Internal'
        self.__write_std_info(code, '%s Threading' % type_str, g20_g21, units, work_offset, tool_number, tool_radius)
        code.append('\n(Spindle RPM =  %.1f)' % rpm)

        code.append('\n(Z Start Location = %.4f)' % z_start_report)
        code.append('(Z End Location = %.4f)' % z_end_report)
        code.append('(Thread Specification = %s)' % active_thread_text)
        code.append('(Thread Direction = %s)' % (self.ui.thread_rh_lh_to_str()))
        code.append('(Inside Diameter = %.4f)' % minor_dia)
        code.append('(Outside Diameter = %.4f)' % major_dia)
        code.append('(Taper [incl. lead in/out] = %.4f)' % taper)

        code.append('\n(Thread Length = %.4f)' % thread_length)
        code.append('(Pitch = %.4f %s/thread)' % (pitch, units))
        code.append('(Threads per %s = %.2f)' % (unit, tpu))
        code.append('(Depth of Cut = %.4f)' % doc)
        code.append('(Thread Lead = %s)' % lead)
        code.append('(Tool Clearance = %s)' % tool_clearance)
        code.append('(Number of passes = %s)' % tpass)

        # Set tool working side
        i_value_sign = -1
        if minor_dia > 0 and major_dia > 0 and major_dia > minor_dia:
            x_side = 1
            code.append(self._tool_side_msg(x_side))
        elif minor_dia < 0 and major_dia < 0 and major_dia < minor_dia:
            x_side = -1
#           i_value_sign = 1
            code.append(self._tool_side_msg(x_side))
        else:
            x_side = 0
            if ext_int_thread == 'external':
                msg = 'Conversational Threading entry error - Both diameters should be positive or both negative, with X Start larger than X End'
            else:
                msg = 'Conversational Threading entry error - Both diameters should be positive or both negative, with X End larger than X Start'
            self.error_handler.write(msg)
            cparse.raise_alarm(thread_dro_list['thread_major_dia_dro'], msg)
            cparse.raise_alarm(thread_dro_list['thread_minor_dia_dro'], msg)
            return False, ''

        code.append('\n%s' % sup_note)

        if ext_int_thread == 'external':
            thread_side = 1
        elif ext_int_thread == 'internal':
            thread_side = -1
        else:
            thread_side = 0
            self.error_handler.write('Conversational Threading entry error - Thread type not interal or external')
            return False, ''

        # Feeds cut towards spindle, right hand threads
        if thread_length < 0.0000001:
            z_side = 0
            msg = 'Conversational Threading entry error - Thread length must be larger than 0, - feeds toward spindle, + feeds away'
            self.error_handler.write(msg)
            cparse.raise_alarm(thread_dro_list['thread_z_start_dro'], msg)
            cparse.raise_alarm(thread_dro_list['thread_z_end_dro'], msg)
            return False, ''
        z_side = 1 if self.ui.conv_thread_rh_lh == 'rh' else -1

        if x_side > 0 and thread_side > 0:  # tool orientation should be 6
            expected_tool_orientation = 6
        elif x_side > 0 and thread_side < 0:  # tool orientation should be 8
            expected_tool_orientation = 8
        elif x_side < 0 and thread_side > 0:  # tool orientation should be 8
            expected_tool_orientation = 8
        elif x_side < 0 and thread_side < 0:  # tool orientation should be 6
            expected_tool_orientation = 6
        else :
            expected_tool_orientation = 0

        if tool_orientation != expected_tool_orientation:
            # raise alarms on the offending widgets
            expected_tool_orientation_image = get_tool_orientation_image(expected_tool_orientation)
            tool_orientation_image = get_tool_orientation_image(tool_orientation)
            self.error_handler.write('Conversational Thread entry error - Tool Orientation')
            error_msg = 'The X inputs call for orientation %s\nThe tool table orientation for T%s is %s' % (expected_tool_orientation, tool_number, tool_orientation)
            cparse.raise_alarm(thread_dro_list['thread_major_dia_dro'], error_msg)
            cparse.raise_alarm(thread_dro_list['thread_minor_dia_dro'], error_msg)
            cparse.raise_alarm(thread_dro_list['thread_tool_num_dro'], error_msg)
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            self.error_handler.set_image_1(expected_tool_orientation_image)
            self.error_handler.set_image_2(tool_orientation_image)
            self.error_handler.set_error_image_1_text('The X and Z inputs in the Thread conversational call for orientation %s:' % expected_tool_orientation)
            self.error_handler.set_error_image_2_text('The tool table orientation for T%s is %s:' % (tool_number, tool_orientation))
            return False, ''

        code.append(conversational.start_of_gcode)   # End of parameter statement

        # Start up code
        code.append('\nG7 (Dia. Mode)')
        code.append('G18 (XZ Plane)')
        code.append('G90 (Absolute Distance Mode)')
        code.append('G40 (Turn Cutter Compensation Off)')
        code.append('%s (units in %s)' % (g20_g21, units))
        code.append('%s (Work Offset)' % work_offset)

        # Go to safe place for tool change
        code.append('\nG30 Z #5422 (Park Tool)')  # Move first to Z current at 5422[not really a move], then move to Z location of G30
        code.append('T%02d%02d' % (tool_number, tool_number))

        # Check Z variables for RH or LH threads?
        # Check for cross slide angle? 29, 29.5, 30 degrees?
        # Set up dynamic DoC?
        # Set lead in, lead out profile?
        # Set spring passes?

        # Set spindle to RPM mode
        code.append('\nG97 (RPM Mode On, CSS Off)')

        code.append('S %d' % rpm)

        code.append('\n'+self._coolant_on(tool_number)+' (Coolant ON)')
        spindle_dir = 'M3 (Spindle ON, Forward)'
        if self.ui.conv_thread_rh_lh == 'lh':
            if using_M4_lhthread:
                spindle_dir = 'M4 (Spindle ON, Reverse)'
        code.append(spindle_dir)
        # Go to x_start,z_start, sets where the thread starts, G76 includes X tool clearance
        if ext_int_thread == 'external':
            code.append('G0 X %s' % dro_fmt % (major_dia + (x_side * i_offset)))
            code.append('G0 Z %s' % dro_fmt % (z_start + (z_side * lead)))

        elif ext_int_thread == 'internal':
            code.append('G0 X %s' % dro_fmt % (minor_dia - (x_side * i_offset)))
            code.append('G0 Z %s' % dro_fmt % (z_start + (z_side * lead)))


        # G76, P distance per thread, Z z_end, I x_start offset,
        #     J depth of cut, R regression, K thread depth, Q compound angle
        code.append('G76 P %s Z %s I %s J %s R 2 K %s Q 30 D %s' %
                    (dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt, dro_fmt) %
                    (pitch,  # P
                     z_start - (z_side * thread_length),  # Z
                     i_offset * i_value_sign * x_side * thread_side,  # I
                     doc ,  # J
                     math.fabs(major_dia - minor_dia),  # K
                     taper))  # D

        # Go to x_start,z_start
        if ext_int_thread == 'external':
            code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((major_dia + (x_side * i_offset)), (z_start + (z_side * lead))))

        elif ext_int_thread == 'internal':
            code.append('\nG0 X %s Z %s' % (dro_fmt, dro_fmt) %
                        ((minor_dia - (x_side * i_offset)), (z_start + (z_side * lead))))

        code.append('\n'+self._coolant_off(tool_number)+' (Coolant OFF)')
        code.append('M5 (Spindle OFF)')
        conversational_base.write_ending_G30(code, 'Z #5422 (Park Tool)')
        conversational_base.std_end_conversational_step(code, 'Thread')

        return ok, code

    # -------------------------------------------------------------------------------
    # End of g code generation routines
    # -------------------------------------------------------------------------------

    def get_tool_type(self, tool_number):
        # LCNC 2.6 pocket to tool mapping is poor, we use pockets 1-(MAX_LATHE_TOOL_NUM) for wear offsets, MAX_LATHE_TOOL_NUM+1 - (MAX_LATHE_TOOL_NUM*2) for geo offsets
        pocket = tool_number + MAX_LATHE_TOOL_NUM
        front_angle_val = self.status.tool_table[pocket].frontangle
        for tool_type_string, tool_type in self.ui.tool_type_dic.iteritems():
            if tool_type == front_angle_val:
                return tool_type_string
        return 'none'


    def validate_param(self, widget, is_metric=False, pitch = '', max_vel = ''):
        """ self.validate_param function provides a wrapper around the individual validate functions.
        This allows a single call to validate the contents of a gtk.entry widget, regardless of that
        widget's data type. """

        name = gtk.Buildable.get_name(widget)
        if 'work_offset' in name:
            (valid, value, error_msg) = self.validate_work_offset(widget)
            return valid, value, error_msg
        if 'sfm' in name:
            (valid, value, error_msg) = self.validate_surface_speed(widget, is_metric)
            return valid, value, error_msg
        if 'feed' in name:
            (valid, value, error_msg) = self.validate_feedrate(widget, is_metric)
            return valid, value, error_msg
        if 'tool' in name:
            (valid, value, error_msg) = self.validate_tool_number(widget, False)
            return valid, value, error_msg
        if 'thread_spindle_rpm' in name:
            (valid, value, error_msg) = self.validate_spindle_rpm(widget)
            if valid is False:
                return valid, value, error_msg
            (valid, value, error_msg) = self.validate_pitch_spindle_rpm(widget, is_metric, pitch, max_vel)
            return valid, value, error_msg
        if 'tap_spindle_rpm' in name:
            (valid, value, error_msg) = self.validate_spindle_rpm(widget)
            if valid is False:
                return valid, value, error_msg
            (valid, value, error_msg) = self.validate_pitch_spindle_rpm(widget, is_metric, pitch, max_vel)
            return valid, value, error_msg
        if 'spindle_rpm' in name:
            (valid, value, error_msg) = self.validate_spindle_rpm(widget)
            return valid, value, error_msg
        if 'dia' in name:
            (valid, value, error_msg) = self.validate_dia_val(widget)
            return valid, value, error_msg
        if '_z_' in name:
            (valid, value, error_msg) = self.validate_z_point(widget)
            return valid, value, error_msg
        if '_x_' in name:
            (valid, value, error_msg) = self.validate_x_point(widget)
            return valid, value, error_msg
        if 'doc' in name:
            (valid, value, error_msg) = self.validate_doc(widget, is_metric)
            return valid, value, error_msg
        if 'angle' in name:
            (valid, value, error_msg) = self.validate_angle(widget)
            return valid, value, error_msg
        if 'hole_depth' in name:
            (valid, value, error_msg) = self.validate_lt0(widget, is_metric)
            return valid, value, error_msg
        if 'thread_length' in name:
            (valid, value, error_msg) = self.validate_dia_val(widget)
            return valid, value, error_msg
        if 'peck' in name:
            (valid, value, error_msg) = self.validate_gte0(widget, is_metric)
            return valid, value, error_msg
        if 'dwell' in name:
            (valid, value, error_msg) = self.validate_gte0(widget, is_metric)
            return valid, value, error_msg
        if 'pitch' in name:
            (valid, value, error_msg) = self.validate_pitch(widget, is_metric)
            return valid, value, error_msg
        if 'tc' in name:
            (valid, value, error_msg) = self.validate_gte0(widget, is_metric)
            return valid, value, error_msg
        if 'fillet' in name:
            (valid, value, error_msg) = self.validate_doc(widget, is_metric)
            return valid, value, error_msg
        if 'doc_rough_face' in name:
            (valid, value, error_msg) = self.validate_doc(widget, is_metric)
            return valid, value, error_msg
        if 'pilot' in name:
            (valid, value, error_msg) = self.validate_any_num(widget, is_metric)
            return valid, value, error_msg
        if 'od_dro' in name:
            (valid, value, error_msg) = self.validate_any_num(widget, is_metric)
            return valid, value, error_msg
        if 'id_dro' in name:
            (valid, value, error_msg) = self.validate_any_num(widget, is_metric)
            return valid, value, error_msg
        if 'tw' in name:
            (valid, value, error_msg) = self.validate_tw(widget, is_metric)
            return valid, value, error_msg
        if 'tpu' in name:
            (valid, value, error_msg) = self.validate_gt0(widget, is_metric)
            return valid, value, error_msg
        if 'lead' in name:
            (valid, value, error_msg) = self.validate_doc(widget, is_metric)
            return valid, value, error_msg
        if 'fpr' in name:
            (valid, value, error_msg) = self.validate_fpr(widget, is_metric)
            return valid, value, error_msg
        if 'radius' in name:
            (valid, value, error_msg) = self.validate_any_num(widget, is_metric)
            return valid, value, error_msg
        if 'thread_pass' in name:
            (valid, value, error_msg) = self.validate_any_int(widget, is_metric)
            return valid, value, error_msg
        if 'thread_depth' in name:
            (valid, value, error_msg) = self.validate_lt0(widget, is_metric)
            return valid, value, error_msg
        if 'part_css' in name:
            (valid, value, error_msg) = self.validate_gt0(widget, is_metric)
            return valid, value, error_msg
        if 'part_fpr' in name:
            (valid, value, error_msg) = self.validate_gt0(widget, is_metric)
            return valid, value, error_msg
        if 'retract' in name:
            (valid, value, error_msg) = self.validate_gte0(widget, is_metric)
            return valid, value, error_msg
        if 'finish_rpm' in name:
            (valid, value, error_msg) = self.validate_gte0(widget, is_metric)
            return valid, value, error_msg
        if 'ebw' in name:
            (valid, value, error_msg) = self.validate_ebw(widget, is_metric)
            return valid, value, error_msg
        if 'taper' in name:
            (valid, value, error_msg) = self.validate_any_num(widget, is_metric)
            return valid, value, error_msg

        return False, 0.0, 'Validation Error, no match for name %s' % name


    def validate_tool_number(self, widget, is_metric=False):
        try:
            tool_number = int(widget.get_text())
            #if (0 < tool_number < 9999):
            if (0 < tool_number <= MAX_LATHE_TOOL_NUM):
                cparse.clr_alarm(widget)
                return True, tool_number, ''
            else:
                msg = 'Invalid tool number - only tools 1 - '+str(MAX_LATHE_TOOL_NUM)+' allowed'
                cparse.raise_alarm(widget, msg)
                return False, '', msg
        except ValueError:
            msg = 'Invalid tool number'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_surface_speed(self, widget, is_metric):
        (is_valid_number, surface_speed) = cparse.is_number_or_expression(widget)
        # TODO - range check.  Should incorporate g20/21 setting
        if (is_valid_number and (surface_speed > 0)):
            cparse.clr_alarm(widget)
            return True, surface_speed, ''
        else:
            msg = 'Invalid surface speed'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_feedrate(self, widget, is_metric):
        (is_valid_number, feedrate) = cparse.is_number_or_expression(widget)
        # TODO - range check, should incorporate g20/21 setting
        if (is_valid_number and (feedrate >= 0)):
            cparse.clr_alarm(widget)
            return True, feedrate, ''
        else:
            msg = 'Invalid feedrate'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def set_valid_spindle_rpm_range(self, min_rpm, max_rpm):
        self.local_min_rpm = min_rpm
        self.local_max_rpm = max_rpm

    def validate_spindle_rpm(self, widget, is_metric=False):
        (is_valid_number, requested_spindle_rpm) = cparse.is_number_or_expression(widget)
        #note max_rpm and min_rpm track spindle configuration
        if (is_valid_number and (self.local_max_rpm >= requested_spindle_rpm >= self.local_min_rpm)):
            cparse.clr_alarm(widget)
            return True, requested_spindle_rpm, ''
        else:
            msg = 'Invalid RPM setting %d.  \nRPM must be between %d and %d in present spindle config' % (requested_spindle_rpm, self.local_min_rpm, self.local_max_rpm)
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_pitch_spindle_rpm(self, widget, is_metric, pitch, max_vel):
        #print "--kaw validate thread RPM, pitch =", pitch, "    max_vel =", max_vel
        (is_valid_number, pitch_spindle_rpm) = cparse.is_number_or_expression(widget)
        if is_metric:
            unit_conv = 25.4
        else:
            unit_conv = 1.0
        # in = inches, ips = inches/second
        pitch_in = float(pitch) / unit_conv
        z_velocity_ips = pitch_spindle_rpm * pitch_in / 60.0
        max_velocity_ips = float(max_vel)
        #print "--kaw  rpm =", pitch_spindle_rpm, "    pitch =", pitch_in, "    z_velocity =", z_velocity_ips, "    max_velocity =", max_velocity_ips
        if z_velocity_ips <= max_velocity_ips:
            cparse.clr_alarm(widget)
            return True, pitch_spindle_rpm, ''
        else:
            max_rpm = 60 * max_velocity_ips / pitch_in
            error_msg = "Spindle RPM too high for selected pitch, set to %s RPM or lower" % '%d' % max_rpm
            cparse.raise_alarm(widget, error_msg)
            return False, 0, error_msg

    def validate_dia_val(self, widget, is_metric=False):
        (is_valid_number, diameter) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, diameter, ''
        else:
            msg = 'Invalid diameter value'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_x_point(self, widget, is_metric=False):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, point, ''
        else:
            msg = 'Invalid X value'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_y_point(self, widget, is_metric=False):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, point, ''
        else:
            msg = 'Invalid Y value'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_z_point(self, widget, is_metric=False):
        (is_valid_number, point) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, point, ''
        else:
            msg = 'Invalid Z value'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_fpr(self, widget, is_metric):
        (is_valid_number, fpr) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            if fpr >= 0:
                cparse.clr_alarm(widget)
                return True, fpr, ''
        msg = 'Invalid feed number'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg


    def validate_doc(self, widget, is_metric):
        (is_valid_number, doc) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, doc, ''
        msg = 'Invalid DOC number'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_tw(self, widget, is_metric):
        (is_valid_number, doc) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            if doc > 0:
                cparse.clr_alarm(widget)
                return True, doc, ''
        err_str = 'Invalid number, tool width must be greater than zero\n' if is_valid_number else 'Invalid number'
        cparse.raise_alarm(widget, err_str)
        return False, 0, err_str

    def validate_gt0(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            if value > 0:
                cparse.clr_alarm(widget)
                return True, value, ''
        err_str = 'Invalid number, must be greater than zero\n' if is_valid_number else 'Invalid number'
        cparse.raise_alarm(widget, err_str)
        return False, 0, err_str

    def validate_gte0(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            if value >= 0:
                cparse.clr_alarm(widget)
                return True, value, ''
        err_str = 'Invalid number, must be greater than or equal to zero\n' if is_valid_number else 'Invalid number'
        cparse.raise_alarm(widget, err_str)
        return False, 0, err_str

    def validate_lt0(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range change for depth of cut based on G20/21 setting
        if (is_valid_number):
            if value < 0:
                cparse.clr_alarm(widget)
                return True, value, ''
        err_str = 'Invalid number, needs to be less than zero\n' if is_valid_number else 'Invalid number'
        cparse.raise_alarm(widget, err_str)
        return False, 0, err_str

    def validate_lte0(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)
        if (is_valid_number):
            if value <= 0:
                cparse.clr_alarm(widget)
                return True, value, ''
        err_str = 'Invalid number, needs to be a number less than or equal to zero\n' if is_valid_number else 'Invalid number'
        cparse.raise_alarm(widget, err_str)
        return False, 0, err_str

    def validate_angle(self, widget, is_metric=False):
        (is_valid_number, angle) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            if (0 < angle < 90):
                cparse.clr_alarm(widget)
                return True, angle, ''
        # if we fall through the above, raise an alarm.
        msg = 'Invalid chamfer angle'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_peck_depth(self, widget, is_metric=False):
        (is_valid_number, peck_depth) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, peck_depth, ''
        # if we fall through the above, raise an alarm.
        else:
            msg = 'Invalid peck depth'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_dwell(self, widget, is_metric=False):
        (is_valid_number, dwell) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number):
            cparse.clr_alarm(widget)
            return True, dwell, ''
        # if we fall through the above, raise an alarm.
        else:
            msg = 'Invalid dwell'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_pitch(self, widget, is_metric=False):
        (is_valid_number, pitch) = cparse.is_number_or_expression(widget)
        # TODO - appropriate range check
        if (is_valid_number) and (pitch > 0):
            cparse.clr_alarm(widget)
            return True, pitch, ''
        # if we fall through the above, raise an alarm.
        else:
            msg = 'Invalid thread pitch'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_wear_offset(self, value, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number: return True, value, ''
        return False, 0, 'Invalid wear offset entry\n'

    def validate_nose_radius(self, value, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number: return True, value, ''
        return False, 0, 'Invalid nose radius entry\n'

    def validate_tip_orientation(self, value, is_metric=False):
        (is_valid_number, value) = cparse.is_number(value)
        if is_valid_number and (value > 0) and (value < 10): return True, value, ''
        return False, 0, 'Invalid tip orientation entry\n'

    def validate_tool_angle(self, widget, is_metric):
        (is_valid_number, number) = cparse.is_number(widget.get_text())
        angle = math.fabs(number)
        if is_valid_number and 180.0 >= angle >= 0:
            cparse.clr_alarm(widget)
            return True, number, ''
        elif not is_valid_number:
            msg = 'Invalid number'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = u'Number must be between 0.0\u00b0 and %s180.0\u00b0' % ('' if number >= 0.0 else '-')
        cparse.raise_alarm(widget, msg)
        return (False, 0, msg)

    def validate_range_integer(self, widget, is_metric, rng):
        (is_valid_number, any_num) = cparse.is_int(widget.get_text())
        if is_valid_number and (rng[0] <= any_num <= rng[1]):
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be an integer from %d to %d\n' % rng
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an integer'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_ebw(self, widget, is_metric):
        (is_valid_number, value) = cparse.is_number_or_expression(widget)

        if is_metric:
            max_val = 1.5 # mm
            dro_fmt = '%3.3f'
        else:
            max_val = .065 # inches
            dro_fmt = '%2.4f'

        if (is_valid_number and (0 <= value <= max_val)):
            cparse.clr_alarm(widget)
            return True, value, ''
        else:
            msg = ('Invalid number, edge break width needs to be greater than or equal to zero and less than %s\n' % dro_fmt % max_val)
            cparse.raise_alarm(widget, msg)
            return False, 0, msg


    def calc_num_threading_passes(self, depth, end_depth, full_dia_depth, cut_increment, degression):
        tpass  = 0; last_depth = 0
        while depth < end_depth:
            tpass += 1
            depth = full_dia_depth + cut_increment * math.pow(tpass, 1.0/degression)
#           print tpass,(depth-last_depth)/2.
            last_depth=depth
            if tpass >= 999:
                break
        return tpass

#---------------------------------------------------------------------------------------------------
# Parse conventional gcode
#---------------------------------------------------------------------------------------------------


    def parse_non_conversational_lathe_gcode(self, conv_decomp, gcode):
        return self.parse_non_conversational_gcode('Lathe', conv_decomp, gcode)

