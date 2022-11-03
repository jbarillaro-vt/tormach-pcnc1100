# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import gtk
import glib
import gobject
import sys
import os
import math
import time
import csv
import re
import conversational as conv
import ui_support as uis
import ui_common as uic
import traceback
import tooltipmgr


####################################################################################################
# LatheFS - class for lathe specific speeds and feeds
#
####################################################################################################

class LatheFS(uis.FSBase):

    _template = {'Roughing FPR DRO' : None,
                 'Finish FPR DRO'   : None,
                 'Roughing SFM DRO' : None,
                 'Finish SFM DRO'   : None,
                 'Roughing DOC DRO' : None,
                 'Finish DOC DRO'   : None,
                 'Roughing SFM'     : None,
                 'Finish SFM'       : None,
                 'Roughing FPR'     : None,
                 'Finish FPR'       : None,
                 'Roughing DOC'     : None,
                 'Finish DOC'       : None,
                 'Retract DOC'      : None,
                 'Diameter DRO'     : None,
                 'Min Diameter DRO' : None,
                 'Thread Major DRO' : None,
                 'Thread Minor DRO' : None,
                 'Thread TPU DRO'   : None,
                 'Thread DOC DRO'   : None,
                 'Passes DRO'       : None,
                 'Tool Width DRO'   : None,
                 'ID'               : False,
                 'min_diameter'     : 0.0,
                 'front_angle'      : 0.,
                 'back_angle'       : 0.
               }

    tool_parse_data = dict(candidates = re.compile(r'^[A|B|C|D|F|H|L|M|N|O|P|R|S|T|U|V|W|Z|\d]',re.IGNORECASE),
                           tooling_keywords = [('type'          , re.compile(r'^(drill|tap|face-turn|facing|turning|profiling|chamfer|spot|centerdrill|boring|parting|threading|reamer)',re.IGNORECASE)),
                                               ('front_angle'   , re.compile(r'^FA:\s*?-?(\d*\.\d+|\d+)',re.IGNORECASE)),
                                               ('back_angle'    , re.compile(r'^BA:\s*?-?(\d*\.\d+|\d+)',re.IGNORECASE)),
                                               ('tool_width'    , re.compile(r'^(width|w):\s*?(\d*\.\d+|\d+)',re.IGNORECASE)),
                                               ('min_bore'      , re.compile(r'^(min-bore|mb):?\s*?(\d*\.\d+|\d+\.\d*|\d+)',re.IGNORECASE)),
#                                              ('holder'        ,: re.compile(r'^[CDMPS][CDKLRSTVW][ABCDFGJKLMNRSTUVY][NABCPDEFG]-[RLN]')),
#                                              ('insert'        , re.compile(r'^[CDKRSTVW][BCENPO][GMUE][ABCDEFGHJKLMNU_](-|\s)?(\d{3}|\d{1,2}\.\d{1,2})')),
                                              ],
                           tv_overlay_params = {'descript_column' : 1, 'width' : 320, 'height_offset' : -11}
                           )

    descriptor_data = {'tool_width'       : ({'ref' : 0.0, 'conv': True,  'op' : '_match_lable_float', 'start' : 0, 'end' : 0 }, '#307c9a' ), #grey blue
                       'front_angle'      : ({'ref' : 0.0, 'conv': False, 'op' : '_match_lable_float', 'start' : 0, 'end' : 0 }, '#9a0e9a' ), #purple
                       'back_angle'       : ({'ref' : 0.0, 'conv': False, 'op' : '_match_lable_float', 'start' : 0, 'end' : 0 }, '#9a0e9a' ), #purple
                       'min_bore'         : ({'ref' : 0.0, 'conv': True,  'op' : '_match_lable_float', 'start' : 0, 'end' : 0 }, '#307c9a' ), #grey blue
                       'type'             : ({'ref' : '',  'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0,}, '#5d309a' ), #dk purple
#                      'holder'           : ({'ref' : '',  'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0 }, '#f5007e' ), #rose color
#                      'insert'           : ({'ref' : '',  'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0 }, '#307c9a' ), #grey blue
                      }
    _redis_key = 'lathe_feeds_speeds_enabled'
    _min_drill_dia = 0.01
    _max_drill_dia = 1.125
    _max_ipr_ratio = 0.75

    def __init__(self, uiobject):
        uis.FSBase.__init__(self, uiobject, LatheFS.tool_parse_data['tooling_keywords'], LatheFS.descriptor_data)
        uis.ToolDescript.set_class_data(LatheFS.descriptor_data)

    @classmethod
    def tool_description_parse_data(cls):
        return cls.tool_parse_data

    @classmethod
    def tool_column_width(cls):
        return cls.tool_parse_data['tv_overlay_params']['width']

    def _get_active_conv_fs_info(self, action):
        fsdata = uis.FSBase.new_fsdata(self.__class__._template)
        cp = self.ui.get_current_conv_notebook_page_id()

        tnum = self._tool_number_op(fsdata, cp)
        self._init_fsdata(fsdata, self.ui, tnum, cp == 'drill_tap_fixed', action)
        fsdata['RPM DRO']          = self.ui.conv_dro_list['conv_max_spindle_rpm_dro']
        fsdata['Roughing SFM DRO'] = self.ui.conv_dro_list['conv_rough_sfm_dro']
        fsdata['Finish SFM DRO']   = self.ui.conv_dro_list['conv_finish_sfm_dro']
        fsdata['Roughing FPR DRO'] = self.ui.conv_dro_list['conv_rough_fpr_dro']
        fsdata['Finish FPR DRO']   = self.ui.conv_dro_list['conv_finish_fpr_dro']
        fsdata['rpm']              = uis.FSBase._get_n_dro_val(fsdata,'RPM DRO')
        fsdata['Roughing SFM']     = uis.FSBase._get_n_dro_val(fsdata,'Roughing SFM DRO')
        fsdata['Finish SFM']       = uis.FSBase._get_n_dro_val(fsdata,'Finish SFM DRO')
        fsdata['Roughing FPR']     = uis.FSBase._get_n_dro_val(fsdata,'Roughing FPR DRO')
        fsdata['Finish FPR']       = uis.FSBase._get_n_dro_val(fsdata,'Finish FPR DRO')
        if fsdata['Roughing SFM'] == 0.: fsdata['Roughing SFM'] = fsdata['Finish SFM']
        if fsdata['Roughing FPR'] == 0.: fsdata['Roughing FPR'] = fsdata['Finish FPR']
        if cp == 'od_turn_fixed':
            fsdata['Roughing DOC DRO'] = self.ui.od_turn_dro_list['od_turn_rough_doc_dro']
            fsdata['Finish DOC DRO']   = self.ui.od_turn_dro_list['od_turn_finish_doc_dro']

        elif cp == 'id_turn_fixed':
            fsdata['ID'] = True
            basic = self.ui.conv_id_basic_ext == 'basic'
            fsdata['Roughing DOC DRO'] = self.ui.id_basic_dro_list['id_basic_rough_doc_dro'] if basic else self.ui.id_turn_dro_list['id_turn_rough_doc_dro']
            fsdata['Finish DOC DRO']   = self.ui.id_basic_dro_list['id_basic_finish_doc_dro'] if basic else self.ui.id_turn_dro_list['id_turn_finish_doc_dro']
            fsdata['Min Diameter DRO'] = self.ui.id_basic_dro_list['id_basic_pilot_dia_dro'] if basic else self.ui.id_turn_dro_list['id_turn_pilot_dro']

        elif cp == 'profile_fixed':
            fsdata['ID'] = self.ui.conv_profile_ext != 'external'
            fsdata['Roughing DOC DRO'] = self.ui.profile_dro_list['profile_roughing_doc_dro']
            fsdata['Finish DOC DRO']   = self.ui.profile_dro_list['profile_finish_doc_dro']
            if fsdata['ID']: fsdata['Min Diameter DRO'] = self.ui.profile_dro_list['profile_stock_x_dro']

        elif cp == 'face_fixed':
            fsdata['Roughing DOC DRO'] = self.ui.face_dro_list['face_rough_doc_dro']
            fsdata['Finish DOC DRO']   = self.ui.face_dro_list['face_finish_doc_dro']

        elif cp == 'chamfer_fixed':
            od = self.ui.conv_chamfer_od_id == 'od'
            fsdata['ID'] = not od
            if self.ui.conv_chamfer_radius == 'chamfer':
                fsdata['Roughing DOC DRO'] = self.ui.corner_chamfer_od_dro_list['corner_chamfer_od_rough_doc_dro'] if od else self.ui.corner_chamfer_id_dro_list['corner_chamfer_id_rough_doc_dro']
                fsdata['Finish DOC DRO']   = self.ui.corner_chamfer_od_dro_list['corner_chamfer_od_finish_doc_dro'] if od else self.ui.corner_chamfer_id_dro_list['corner_chamfer_id_finish_doc_dro']
                if fsdata['ID']: fsdata['Min Diameter DRO'] = self.ui.corner_chamfer_id_dro_list['corner_chamfer_id_id_dro']
            else:
                fsdata['Roughing DOC DRO'] = self.ui.corner_radius_od_dro_list['corner_radius_od_rough_doc_dro'] if od else self.ui.corner_radius_id_dro_list['corner_radius_id_rough_doc_dro']
                fsdata['Finish DOC DRO']   = self.ui.corner_radius_od_dro_list['corner_radius_od_finish_doc_dro'] if od else self.ui.corner_radius_id_dro_list['corner_radius_id_finish_doc_dro']
                if fsdata['ID']: fsdata['Min Diameter DRO'] = self.ui.corner_radius_id_dro_list['corner_radius_id_id_dro']

        elif cp == 'groove_part_fixed':
            if self.ui.conv_groove_part == 'groove':
                fsdata['Roughing DOC DRO'] = self.ui.groove_dro_list['groove_rough_doc_dro']
                fsdata['Finish DOC DRO']   = self.ui.groove_dro_list['groove_finish_doc_dro']
                fsdata['Tool Width DRO']   = self.ui.groove_dro_list['groove_tw_dro']
            else:
                fsdata['Tool Width DRO']   = self.ui.part_dro_list['part_tw_dro']
                fsdata['Peck DRO']         = self.ui.part_dro_list['part_peck_dro']
                fsdata['Min Diameter DRO'] = self.ui.part_dro_list['part_final_dia_dro']


        elif cp == 'drill_tap_fixed':
            fsdata['ID'] = True
            if self.ui.conv_drill_tap == 'drill':
                fsdata['Peck DRO']             = self.ui.drill_dro_list['drill_peck_dro']
                fsdata['RPM DRO']              = self.ui.drill_dro_list['drill_spindle_rpm_dro']
                fsdata['Zdepth']               = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.drill_dro_list['drill_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.drill_dro_list['drill_z_start_dro']))
            else:
                fsdata['Peck DRO']             = self.ui.tap_dro_list['tap_peck_dro']
                fsdata['RPM DRO']              = self.ui.tap_dro_list['tap_spindle_rpm_dro']
                fsdata['Zdepth']               = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.tap_dro_list['tap_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.tap_dro_list['tap_z_start_dro']))

        elif cp == 'thread_fixed':
            fsdata['RPM DRO']              = self.ui.thread_dro_list['thread_spindle_rpm_dro']
            fsdata['Passes DRO']           = self.ui.thread_dro_list['thread_pass_dro']
            fsdata['Thread Minor DRO']     = self.ui.thread_dro_list['thread_minor_dia_dro']
            fsdata['Thread TPU DRO']       = self.ui.thread_dro_list['thread_tpu_dro']
            fsdata['Thread DOC DRO']       = self.ui.thread_dro_list['thread_doc_dro']

        # convert all DRO data to 'inches'
        fsdata['Roughing DOC'] = uis.FSBase._get_n_dro_val(fsdata,'Roughing DOC DRO')
        fsdata['Finish DOC']   = uis.FSBase._get_n_dro_val(fsdata,'Finish DOC DRO')
        if fsdata['Min Diameter DRO'] is not None: fsdata['min_diameter'] = uis.FSBase._get_n_dro_val(fsdata,'Min Diameter DRO')

        # get all tool data in one place..
        fsdata['diameter'] = fsdata['tdr'].data['tool_diameter'][0]['ref'] if fsdata['Diameter DRO'] is None else uis.FSBase._get_n_dro_val(fsdata,'Diameter DRO')
        if fsdata['diameter'] is None: fsdata['diameter'] = 0.0 if fsdata['tool_radius'] is None else fsdata['tool_radius']*2.0
        if uic.iszero(fsdata['diameter']) and fsdata['is_axial']: fsdata['diameter'] = self.ui.get_tool_diameter(tnum)
        fsdata['diameter'] = math.fabs(fsdata['diameter'])
        fsdata['sfm_pr'] = fsdata['diameter']*math.pi/12.
        fsdata['tool_width'] = fsdata['tdr'].data['tool_width'][0]['ref']
        if fsdata['Finish DOC'] is not None: fsdata['mrr_pr'] = LatheFS._calc_mrr_pr(fsdata)
        sfm_minstr = 'SFM-%s%smin'%('CRB' if fsdata['material'] == 'crb' or fsdata['material'] == 'dmd' else 'HSS', "-Drill" if fsdata['is_axial'] else '-Lathe')
        sfm_maxstr = 'SFM-%s%smax'%('CRB' if fsdata['material'] == 'crb' or fsdata['material'] == 'dmd' else 'HSS', "-Drill" if fsdata['is_axial'] else '-Lathe')
        fsdata['tool_radius'] = self.ui.get_tool_diameter(tnum)/2.
        fsdata['front_angle'],fsdata['back_angle'] = self.ui.get_tool_angles(tnum)
        # do a tool check for a valid defined tool
        if fsdata['is_axial']:
            if fsdata['tool_radius'] == 0.0:
                raise uis.ValidationError('Tool %d has zero diameter. Refer to tool %d in the Offsets tab'%(fsdata['tool_number'], fsdata['tool_number']))
        else:
            if (fsdata['front_angle'] == 0.0 and fsdata['back_angle'] == 0.0):
                if not fsdata['tool_descript']:
                    raise uis.ValidationError('Tool %d is not fully defined for conversational feeds and speeds: no description, no cutting angles. Refer to tool %d on the Offsets tab.'%(fsdata['tool_number'], fsdata['tool_number']))
                raise uis.ValidationError('Tool %d is not fully defined for conversational feeds and speeds: zero cutting angles. Refer to tool %d on the Offsets tab.'%(fsdata['tool_number'], fsdata['tool_number']))
        fsdata['sfm_lo'] = fsdata['spec_data'][sfm_minstr]
        fsdata['sfm_hi'] = fsdata['spec_data'][sfm_maxstr]
        fsdata['sfm_range'] = math.fabs(fsdata['sfm_hi']-fsdata['sfm_lo'])
        fsdata['ipr_min'] = fsdata['spec_data']['Drill-IPR-Rangemin' if fsdata['is_axial'] else 'Lathe-IPR-Rangemin']
        fsdata['ipr_mid'] = fsdata['spec_data']['Drill-IPR-Rangemid' if fsdata['is_axial'] else 'Lathe-IPR-Rangemid']
        fsdata['ipr_max'] = fsdata['spec_data']['Drill-IPR-Rangemax' if fsdata['is_axial'] else 'Lathe-IPR-Rangemax']
        return fsdata

    def _tool_number_op(self, fsdata, cp):
        fsdata['op'] = getattr(self, '_update_feeds_speeds_turn')
        if cp == 'od_turn_fixed':
            tool_dro           = self.ui.od_turn_dro_list['od_turn_tool_num_dro']
            fsdata['Diameter DRO'] = self.ui.od_turn_dro_list['od_turn_stock_dia_dro']
        elif cp == 'id_turn_fixed':
            basic = self.ui.conv_id_basic_ext == 'basic'
            fsdata['Diameter DRO'] = self.ui.id_basic_dro_list['id_basic_final_dia_dro'] if basic else self.ui.id_turn_dro_list['id_turn_final_dia_dro']
            tool_dro           = self.ui.id_basic_dro_list['id_basic_tool_num_dro'] if basic else self.ui.id_turn_dro_list['id_turn_tool_num_dro']
        elif cp == 'profile_fixed':
            fsdata['Diameter DRO'] = self.ui.profile_dro_list['profile_stock_x_dro']
            tool_dro           = self.ui.profile_dro_list['profile_tool_num_dro']
        elif cp == 'face_fixed':
            fsdata['Diameter DRO'] = self.ui.face_dro_list['face_stock_dia_dro']
            tool_dro           = self.ui.face_dro_list['face_tool_num_dro']
        elif cp == 'chamfer_fixed':
            od = self.ui.conv_chamfer_od_id == 'od'
            if self.ui.conv_chamfer_radius == 'chamfer':
                fsdata['Diameter DRO'] = self.ui.corner_chamfer_od_dro_list['corner_chamfer_od_od_dro'] if od else self.ui.corner_chamfer_id_dro_list['corner_chamfer_id_id_dro']
                tool_dro               = self.ui.corner_chamfer_od_dro_list['corner_chamfer_od_tool_num_dro'] if od else self.ui.corner_chamfer_id_dro_list['corner_chamfer_id_tool_num_dro']
            else:
                fsdata['Diameter DRO'] = self.ui.corner_radius_od_dro_list['corner_radius_od_od_dro'] if od else self.ui.corner_radius_id_dro_list['corner_radius_id_id_dro']
                tool_dro               = self.ui.corner_radius_od_dro_list['corner_radius_od_tool_num_dro'] if od else self.ui.corner_radius_id_dro_list['corner_radius_id_tool_num_dro']
        elif cp == 'groove_part_fixed':
            if self.ui.conv_groove_part == 'groove':
                fsdata['Diameter DRO'] = self.ui.groove_dro_list['groove_stock_dia_dro']
                tool_dro               = self.ui.groove_dro_list['groove_tool_num_dro']
            else:
                fsdata['Diameter DRO'] = self.ui.part_dro_list['part_stock_dia_dro']
                tool_dro               = self.ui.part_dro_list['part_tool_num_dro']
            fsdata['op'] = getattr(self, '_update_feeds_speeds_part')

        elif cp == 'drill_tap_fixed':
            drill = self.ui.conv_drill_tap == 'drill'
            tool_dro = self.ui.drill_dro_list['drill_tool_num_dro'] if drill else self.ui.tap_dro_list['tap_tool_num_dro']
            fsdata['op'] = getattr(self, '_update_feeds_speeds_drill' if drill else '_update_feeds_speeds_tap')

        elif cp == 'thread_fixed':
            fsdata['Diameter DRO'] = self.ui.thread_dro_list['thread_major_dia_dro']
            tool_dro  = self.ui.thread_dro_list['thread_tool_num_dro']
            fsdata['op'] = getattr(self, '_update_feeds_speeds_thread')
        return tool_dro.get_text()

    @staticmethod
    def _calc_mrr_pr(fsdata):
        r = fsdata['diameter']/2.
        return (math.pi*(r**2))-(math.pi*((r-fsdata['Roughing DOC'])**2))

    @staticmethod
    def _id_min_bore_reduction(fsdata,max_offset=.2,max_id=.95):
        # make an adjustment for ID operation that have low min bore..
        # this reduction is based on area of the minium m=bore of the
        # boring bar .. so a skinny boring bar can't be subjected to too
        # much horsepower.
        if not fsdata['ID']: return 1.
        mb = fsdata['tdr'].data['min_bore'][0]['ref']
        if mb==0.0 and fsdata['min_diameter']>0.: mb = fsdata['min_diameter']
        mb = min(max(mb+max_offset,.2),max_id)
        _mx_calc = math.pi*((max_id/2.)**2)+max_offset
        return min(max((math.pi*(mb/2.)**2+max_offset)/_mx_calc,.1),.95)

    @staticmethod
    def calc_all_chipload(ui, tool, ipr, rpm, dummy=None):
        tool_description = ui.get_tool_description(tool)
        tdr = uis.ToolDescript.parse_text(tool_description)
        flutes = tdr.data['flutes'][0]['ref']
        tool_diam = ui.get_tool_diameter(tool)
        return (flutes,ipr/flutes,0.0)

    def current_chipload(self):
        tool = None
        tool_description = None
        try:
            error_ret = (0,0.0,None)
            valid, ipr =  conv.cparse.is_number_or_expression(self.ui.conv_dro_list['conv_rough_fpr_dro'])
            if not valid: return error_ret
            valid, rpm =  conv.cparse.is_number_or_expression(self.ui.drill_dro_list['drill_spindle_rpm_dro'])
            if not valid: return error_ret
            try:
                tool = int(self.ui.drill_dro_list['drill_tool_num_dro'].get_text())
            except ValueError:
                return error_ret
            return LatheFS.calc_all_chipload(self.ui, tool, ipr, rpm)
        except Exception as e:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.ui.error_handler.log('current_chipload raised exception - tool {} - exception {}'.format(tool, traceback_txt))
        return error_ret

    def _iterate_doc_ipr_to_horsepower(self, fsdata, rpm, ipr, doc, mx):
        if rpm<=0: return (0.,0.)
        real_hp = uis.FSBase.hp_rpm(rpm)
        max_doc, max_ipr = mx
        if max_doc <= 0.0 or max_ipr <= 0.0:
            raise ValueError('Attemp to calulate Spindle Horsepower with zero tool radius')
        # limit horsepower by the diameter of material being cut. This in turn
        # limits doc and ipr
        diam = max(min(fsdata['diameter'],6.0),.05)
        hp_pct = min(((math.log(diam)+5)/((math.log(6.0)+5.0)))+.15,1.0)
        hp_pct *= LatheFS._id_min_bore_reduction(fsdata)
        limit_hp = real_hp*hp_pct
        _od = fsdata['diameter']*math.pi
        # increase doc untill near hp limit;
        while True:
            _sh = uis.FSBase._spindle_hp(fsdata['Kc'], ipr, doc, _od)*rpm
            if _sh > limit_hp: break
            doc = min(max_doc,doc*1.05)
            _sh = uis.FSBase._spindle_hp(fsdata['Kc'], ipr, doc, _od)*rpm
            if _sh > limit_hp: break
            ipr = min(max_ipr,ipr*1.02)
            if doc >= max_doc and ipr >= max_ipr: break
            if ipr == 0.0:
                raise ValueError('Attemp to calulate Spindle Horsepower with zero IPR')
            if doc == 0.0:
                raise ValueError('Attemp to calulate Spindle Horsepower with zero DOC')
        #decrease until in hp limits
        limit_hp = real_hp*hp_pct
        while True:
            _sh = uis.FSBase._spindle_hp(fsdata['Kc'], ipr, doc, _od)*rpm
            if _sh < limit_hp: break
            doc *= .935
            _sh = uis.FSBase._spindle_hp(fsdata['Kc'], ipr, doc, _od)*rpm
            if _sh < limit_hp: break
            ipr *= .935
 #       print 'spindle hp %.1f' % spindle_hp
        return (round(ipr,3),round(doc,3))

    def _finish_doc(self, fsdata):
        f_doc = .0025
        if fsdata['ISO'] in 'N': f_doc = 0.002
        return f_doc

    def _rf_sfm(self, fsdata, sfm):
        fac = 1.0 if fsdata['ISO'] in 'SH' else 1.1
        return (round(sfm,0 if sfm<100 else -1),round(sfm*fac,0 if sfm*fac<100 else -1))

    def __turn(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0,0.0,0.0,0.0,0.0,0.0,0.0)
        rpm = uis.FSBase.best_iso_rpm(fsdata)

        # DOC is tool_radius based, however if there is a forward leaning angle
        # on the cutting edge, this could be more aggressive.
        _doc = fsdata['tool_radius']*.7
        if math.fabs(fsdata['front_angle']) > 90.: _doc = fsdata['tool_radius']*2.5

        # ipr - try to activate the chip breaker, which unfortunatly there is
        # no info on.
        # ipr is initially table based
        r_ipr= uis.MaterialData.tri_range_resolver(fsdata['diameter'], \
                                                 .13,fsdata['ipr_min'], \
                                                 fsdata['ipr_mid'], \
                                                 fsdata['ipr_max'], \
                                                 LatheFS._min_drill_dia, \
                                                 LatheFS._max_drill_dia)
        if fsdata['tool_radius'] <= 0.0:
            raise ValueError('Attempt to calulate Turn feed & speed with zero tool radius - see Offsets tab')
        mx_doc_ipr = (.05, fsdata['tool_radius']*LatheFS._max_ipr_ratio)
        r_ipr *= LatheFS._id_min_bore_reduction(fsdata)
        r_ipr, r_doc = self._iterate_doc_ipr_to_horsepower(fsdata, rpm, r_ipr, _doc, mx_doc_ipr)


        mn_fipr = .001 if fsdata['ISO'] in 'M' else 0.0025
        f_ipr = max(fsdata['tool_radius']*.2,mn_fipr)
        r_sfm = fsdata['diameter']*math.pi*float(rpm)/12.0
        r_sfm, f_sfm = self._rf_sfm(fsdata, r_sfm)
        f_doc = self._finish_doc(fsdata)
        return (rpm,r_sfm,f_sfm,r_doc,f_doc,r_ipr,f_ipr)

    def _update_feeds_speeds_turn(self, fsdata):
        rpm, r_sfm, f_sfm, r_doc, f_doc, r_ipr, f_ipr = self.__turn(fsdata)
        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'Roughing SFM DRO',r_sfm,'%d')
        self._set_dro_val(fsdata,'Finish SFM DRO',f_sfm,'%d')
        self._set_dro_val(fsdata,'Roughing DOC DRO',r_doc)
        self._set_dro_val(fsdata,'Finish DOC DRO',f_doc)
        self._set_dro_val(fsdata,'Roughing FPR DRO',r_ipr)
        self._set_dro_val(fsdata,'Finish FPR DRO',f_ipr)

    def __part(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0,0.0,0.0,0.0,0.0,0.0,0.0,0.0)
        tw = fsdata['tool_width']
        if tw == 0.0: tw = uis.FSBase._get_n_dro_val(fsdata,'Tool Width DRO')
        if tw == 0.0: tw = uis.FSBase._get_n_dro_val(fsdata,'Tool Width DRO')

        r_doc = tw*.8
        ipr_range = (.005,.007) if fsdata['is_plastic'] else\
                (.0015,.0035) if fsdata['ISO'] in 'N' else\
                        (.0006,.0025) if fsdata['ISO'] in 'P' else\
                        (.0007,.0020) if fsdata['ISO'] in 'M' else\
                        (.0006,.0018) if fsdata['ISO'] in 'S' else\
                        (.0008,.005) if fsdata['ISO'] in 'K' else (.0008,.0012)

        r_ipr = 0.0
        if fsdata['is_plastic']: r_ipr = ipr_range[0]+((ipr_range[1]-ipr_range[0]))
        elif rpm>0:
            kc = float(min(max(fsdata['Kc'],50000),400000))
            ipr_fac = 1.0-((kc-50000.0)/350000.0)
            while True:
                r_ipr = ipr_range[0]+((ipr_range[1]-ipr_range[0])*ipr_fac)
                hp_at_rpm = uis.FSBase.hp_rpm(rpm)
                mrr = r_ipr*rpm*tw*math.pi*fsdata['diameter']
                hp = uis.FSBase.mrr_spindle_hp(fsdata['Kc'],mrr)
                if hp_at_rpm*.9>=hp: break
                ipr_fac *= .9
                if ipr_fac<.05: break


        f_ipr = max(min(r_ipr*.66,.002),.0007)
        r_sfm = (fsdata['diameter']*math.pi*rpm/12.)*.8
        r_sfm, f_sfm = self._rf_sfm(fsdata, r_sfm)

        # peck...
        if fsdata['Peck DRO'] is not None: # this is a parting op
            plunge = math.fabs((fsdata['diameter'] - fsdata['min_diameter'])/2.)
            min_plunge = .5 if fsdata['is_plastic'] else\
                    .2 if fsdata['ISO'] in 'NK' else\
                             .18 if fsdata['ISO'] in 'PM' else\
                             .15 if fsdata['ISO'] in 'S' else .08
            self._set_dro_val(fsdata,'Peck DRO',0. if plunge<min_plunge else min_plunge)
        f_doc = self._finish_doc(fsdata)
        return (rpm,r_sfm,f_sfm,r_doc,f_doc,r_ipr,f_ipr,tw)

    def _update_feeds_speeds_part(self, fsdata):
        rpm, r_sfm, f_sfm, r_doc, f_doc, r_ipr, f_ipr, tw = self.__part(fsdata)

        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'Roughing SFM DRO',r_sfm,'%d')
        self._set_dro_val(fsdata,'Finish SFM DRO',f_sfm,'%d')
        self._set_dro_val(fsdata,'Roughing DOC DRO',r_doc)
        self._set_dro_val(fsdata,'Finish DOC DRO',f_doc)
        self._set_dro_val(fsdata,'Roughing FPR DRO',r_ipr)
        self._set_dro_val(fsdata,'Finish FPR DRO',f_ipr)
        self._set_dro_val(fsdata,'Tool Width DRO',tw)

    def __drill(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0, 0.0,0.0)
        brn = fsdata['BRN']
        depth = fsdata['Zdepth']

        # generate parabola for determing peck depth relative to
        # diameter
        diam = max(min(LatheFS._max_drill_dia,fsdata['diameter']),LatheFS._min_drill_dia)

        cl = uis.MaterialData.tri_range_resolver(diam,.13,fsdata['ipr_min'],fsdata['ipr_mid'],fsdata['ipr_max'],LatheFS._min_drill_dia,LatheFS._max_drill_dia)
        rpm = uis.FSBase._clamp_rpm(uis.FSBase._calc_rpm_from_sfm(fsdata))
        r_ipr = self._iterate_ipr_to_horsepower(fsdata['Kc'], diam, rpm, cl*fsdata['flutes'])
        peck = self._calc_drill_peck(fsdata, diam, rpm, r_ipr)
        return (rpm,peck,r_ipr)

    def _update_feeds_speeds_drill (self, fsdata):
        rpm, peck, feed = self.__drill(fsdata)

        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
#       self._set_dro_val(fsdata,'Peck DRO',peck) **PP-2064 - this is disabled for now
        self._set_dro_val(fsdata,'Roughing FPR DRO',feed)


    def _update_feeds_speeds_tap (self, fsdata):
        self._set_dro_val(fsdata,'RPM DRO',450,'%d')

    def __thread(self, fsdata):
        rpm = min(450,uis.FSBase.best_iso_rpm(fsdata))
        if rpm<=0: return (0,0,0.0)
        tpu = uis.FSBase._get_n_dro_val(fsdata, 'Thread TPU DRO')
        tc = uis.FSBase._get_n_dro_val(fsdata, 'Thread DOC DRO')
        t_major = uis.FSBase._get_n_dro_val(fsdata, 'Diameter DRO')
        t_minor = uis.FSBase._get_n_dro_val(fsdata, 'Thread Minor DRO')
        thread_depth = math.fabs(t_major-t_minor)/2.

        # adjust rpm downward if too fast for Z travel
        # on the tool.
        pitch = 1./tpu if tpu != 0. else 0.
        max_vel = self.ui.get_max_vel()
        z_velocity_ips = rpm * pitch/60.0
        if z_velocity_ips>max_vel: rpm = (60.0*max_vel)/pitch


        _Kc = min(fsdata['Kc'],400000)
        _r = max(min(thread_depth,.075),.005)
        _rng = .14 # .15-.01
        # calc a 'parabolic' increase as 'K c' get larger (material harder to machine)
        p_fac = 1.0+((float(_Kc)**2/(400000.0**2))/.9-.2)
        # calc thread depth as percentage of a range
        p_vec = (_r-.01)/_rng

        passes = int(round((3+(22.*p_vec))*p_fac,0))

        while True:
            tpass, doc = self.ui._calc_thread_doc(tc, thread_depth*2., passes)
            curr_rpm_hp = uis.FSBase.hp_rpm(rpm)
            thread_mrr = uis.FSBase.thread_mrr(t_major, t_minor, rpm) / tpass
            hp = uis.FSBase.mrr_spindle_hp(fsdata['Kc'], thread_mrr)
            if hp<curr_rpm_hp*.9: break
            passes += 1
            rpm = min(650,rpm+50)
        return (rpm,tpass,doc)

    def _update_feeds_speeds_thread (self, fsdata):
        rpm, tpass, doc = self.__thread(fsdata)
        # set DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'Passes DRO',tpass,'%d')
        self._set_dro_val(fsdata,'Thread DOC DRO',doc)

    def update_feeds_speeds(self, action=''):
        try:
            fsdata = self._get_active_conv_fs_info(action)
            if fsdata['action'] == 'validate_only': return (True,'')
            fsdata['op'](fsdata)
            self._check_tool_description(fsdata)
            return (True,'')
        except uis.ValidationError as e:
            return (False,str(e))
        except FloatingPointError as e:
            err_msg = tooltipmgr.TTMgr().get_local_string('err_update_fs_fp')
            return (False,err_msg.format('[LatheFS]'))
        except ValueError as e:
            return (False,str(e))
        except LookupError as e:
            return (False,str(e))
        except Exception as e:
            # these are damn hard to debug without more stack trace so log it.
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            err_msg = tooltipmgr.TTMgr().get_local_string('err_exception_fs')
            self.ui.error_handler.log(err_msg.format('[LatheFS]',traceback_txt))
            return (False,err_msg.format('[LatheFS]',str(e)))

####################################################################################################
# LathePnData - get specific 'StepOver' brinell/diameter data from file
#
####################################################################################################
class LathePnData(uis.PNParse):

    def __init__(self,ui):
        uis.PNParse.__init__(self, ui)
        self.mach = 'lathe'
        self._read_data()

    def format_parse_data(self, vals):
        arrangement = ['type','insert','width','coating','tool_material','min_bore','FA','BA']
        if vals['gen_type'] == 'A': return self._format_axial_parse_data(vals)
        val = ''
        for item in arrangement:
            if item in vals and vals[item]: val = val + ' ' + vals[item] if val else vals[item]
        return val

    def _parse_type(self, descript):
        if uis.PNParse._type_index is None: uis.PNParse._type_index = uis.FSBase.find_tooling_keyword_index( 'type', LatheFS.tool_description_parse_data()['tooling_keywords'])
        return uis.PNParse._find_tool_type(LatheFS.tool_description_parse_data()['tooling_keywords'][uis.PNParse._type_index][1], descript)
