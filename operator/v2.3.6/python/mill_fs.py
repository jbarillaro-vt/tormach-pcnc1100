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
import ui_support as uis
import constants as const
import conversational as conv
import traceback
import tooltipmgr

####################################################################################################
# MillFS - class for mill specific speeds and feeds
#
####################################################################################################

class MillFS(uis.FSBase):

    _template = {'ZFeed DRO'    : None,
                 'Feed DRO'     : None,
                 'Feed'         : None,
                 'DOC DRO'      : None,
                 'DOC'          : None,
                 'Stepover DRO' : None,
                 'Stepover'     : None,
                 'Pitch DRO'    : None,
                 'Pitch'        : None,
                 'Passes DRO'   : None,
                 'Extra DRO'    : None,
                 'Extra'        : None,
                 'loc'          : None,
                 'drag'         : False,
                 'helix'        : 'normal'
               }
    tool_parse_data = dict(candidates = re.compile(r'^[\[|A|B|C|D|E|F|H|I|J|L|M|N|P|R|S|T|U|V|Z|\d]',re.IGNORECASE),
                           tooling_keywords = [('type'            , re.compile(r'^(endmill|drill|centerdrill|tap|ball|chamfer|spot|flat|taper|bullnose|reamer|lollypop|flycutter|shearhog|indexable|drag|saw|threadmill|engraver)',re.IGNORECASE)),
# -not used yet                                ('helix'           , re.compile(r'^(variable|var|high|hi):?\s?(\d*\.\d+|\d+\.\d*|\d+)))',re.IGNORECASE)),
# -not used yet                                ('holder'          , re.compile(r'^(ER|SOLID|CHUCK|MODULAR)',re.IGNORECASE)),
                                              ],
                           tv_overlay_params = {'descript_column' : 1, 'width' : 400, 'height_offset' : 11}
                           )

    descriptor_data = {'helix'            : ({'ref' : 'normal', 'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0, }, '#0ca5b0' ), #green blue
                       'type'             : ({'ref' : '',       'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0 ,}, '#5d309a' ), #dk purple
# -not used yet        'holder'           : ({'ref' : 'ER',     'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0 ,}, '#07484d' ), #dk grey blue
                      }

    _find_rpm_to_pct = .7                    # used in _calc_pct_horsepower_left lowr number will cause convergence earlier.
    _drill_spot = ((.01,.005),(.02,.01),(.03,.015),(.04,.02),(.125,0.04),(.25,.06),(.312,.07),(.375,.08),(.42,.09))
    _min_drill_dia = 0.01
    _max_drill_dia = 0.89
    _min_em_dia = 0.01
    _max_em_dia = 0.75
    _min_cl = 0.0004

    def __init__(self, uiobject):
        uis.FSBase.__init__(self, uiobject, MillFS.tool_parse_data['tooling_keywords'], MillFS.descriptor_data)
        # put in the default type as this field is in the base class.
        MillFS.descriptor_data['type'][0]['ref'] = 'endmill'
        self.stepover_data = StepOverData(uiobject)
        uis.ToolDescript.set_class_data(MillFS.descriptor_data)

    @classmethod
    def tool_description_parse_data(cls):
        return cls.tool_parse_data

    @classmethod
    def tool_column_width(cls):
        return cls.tool_parse_data['tv_overlay_params']['width']

    @staticmethod
    def calc_all_chipload(ui, tool, ipm, rpm, stepover,typ):
        tool_description = ui.get_tool_description(tool)
        tdr = uis.ToolDescript.parse_text(tool_description)
        flutes = tdr.data['flutes'][0]['ref']
        tool_diam = ui.get_tool_diameter(tool)
        if tool_diam == 0.0: return (flutes,uis.FSBase.NA,None) if typ == 'drill' else (flutes,uis.FSBase.NA,uis.FSBase.NA)
        step_chip_load = uis.FSBase.stepover_chip_load(tool_diam,flutes,ipm,rpm,stepover,'NA_on_zero')
        return (flutes, uis.FSBase._calc_chip_load(rpm,flutes,ipm), step_chip_load)

    def current_chipload(self, typ=None):
        tool = None
        tool_description = None
        try:
            error_ret = (0,0.0,None)
            feed_dro = self.ui.conv_dro_list['conv_feed_dro']
            stepover = None
            if typ is not None:
                if typ == 'drill': feed_dro = self.ui.conv_dro_list['conv_z_feed_dro']
                elif isinstance(typ,gtk.Entry):
                    valid, stepover = conv.cparse.is_number_or_expression(typ)
                    if not valid: return error_ret
            valid,ipm = conv.cparse.is_number_or_expression(feed_dro)
            if not valid: return error_ret
            valid, rpm =  conv.cparse.is_number_or_expression(self.ui.conv_dro_list['conv_rpm_dro'])
            if not valid: return error_ret
            try:
                tool = int(self.ui.conv_dro_list['conv_tool_number_dro'].get_text())
            except ValueError:
                return error_ret
            return MillFS.calc_all_chipload(self.ui, tool, ipm, rpm, stepover, typ)
        except:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.ui.error_handler.log('current_chipload raised exception - tool {} - exception {}'.format(tool, traceback_txt))
        return error_ret

    def _get_active_conv_fs_info(self, action):
        fsdata = uis.FSBase.new_fsdata(self.__class__._template)
        cp = self.ui.get_current_conv_notebook_page_id()
        tnum = self.ui.conv_dro_list['conv_tool_number_dro'].get_text()
        self._init_fsdata(fsdata, self.ui, tnum, cp == 'conv_drill_tap_fixed', action)
        fsdata['Feed DRO'] = self.ui.conv_dro_list['conv_feed_dro']
        fsdata['Feed'] = uis.FSBase._get_n_dro_val(fsdata,'Feed DRO')
        fsdata['RPM DRO'] = self.ui.conv_dro_list['conv_rpm_dro']
        fsdata['ZFeed DRO'] = self.ui.conv_dro_list['conv_z_feed_dro']
        if cp == 'conv_face_fixed':
            fsdata['DOC DRO']      = self.ui.face_dro_list['face_z_doc_dro']
            fsdata['DOC']          = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            fsdata['Stepover DRO'] = self.ui.face_dro_list['face_stepover_dro']
            fsdata['Stepover']     = uis.FSBase._get_n_dro_val(fsdata,'Stepover DRO')
            fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.face_dro_list['face_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.face_dro_list['face_z_start_dro']))
            fsdata['op']           = getattr(self, '_update_feeds_speeds_facing')

        elif cp == 'conv_profile_fixed':
            rct = self.ui.conv_profile_rect_circ == 'rect'
            fsdata['DOC DRO']      = self.ui.profile_dro_list['profile_z_doc_dro'] if rct else self.ui.profile_dro_list['profile_circ_z_doc_dro']
            fsdata['DOC']          = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            fsdata['Stepover DRO'] = self.ui.profile_dro_list['profile_stepover_dro'] if rct else self.ui.profile_dro_list['profile_circ_stepover_dro']
            fsdata['Stepover']     = uis.FSBase._get_n_dro_val(fsdata,'Stepover DRO')
            fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.profile_dro_list['profile_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.profile_dro_list['profile_z_start_dro'])) if rct else\
                                     math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.profile_dro_list['profile_circ_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.profile_dro_list['profile_circ_z_start_dro']))
            fsdata['op']           = getattr(self, '_update_feeds_speeds_profile')

        elif cp == 'conv_pocket_fixed':
            if self.ui.conv_pocket_rect_circ == 'rect':
                fsdata['DOC DRO']      = self.ui.pocket_rect_dro_list['pocket_rect_z_doc_dro']
                fsdata['Stepover DRO'] = self.ui.pocket_rect_dro_list['pocket_rect_stepover_dro']
                fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.pocket_rect_dro_list['pocket_rect_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.pocket_rect_dro_list['pocket_rect_z_start_dro']))
            else:
                fsdata['DOC DRO']      = self.ui.pocket_circ_dro_list['pocket_circ_z_doc_dro']
                fsdata['Stepover DRO'] = self.ui.pocket_circ_dro_list['pocket_circ_stepover_dro']
                fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.pocket_circ_dro_list['pocket_circ_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.pocket_circ_dro_list['pocket_circ_z_start_dro']))
            fsdata['DOC']              = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            fsdata['Stepover']         = uis.FSBase._get_n_dro_val(fsdata,'Stepover DRO')
            fsdata['op']               = getattr(self, '_update_feeds_speeds_pocket')

        elif cp == 'conv_drill_tap_fixed':
            drill = self.ui.conv_drill_tap ==  'drill'
            fsdata['DOC DRO']      = self.ui.drill_dro_list['drill_peck_dro']
            fsdata['DOC']          = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            zs                     = uis.FSBase._get_n_dro_val(fsdata,self.ui.drill_dro_list['drill_z_start_dro']) if drill else uis.FSBase._get_n_dro_val(fsdata,self.ui.conv_dro_list['conv_z_clear_dro'])
            ze                     = uis.FSBase._get_n_dro_val(fsdata,self.ui.drill_dro_list['drill_z_end_dro']) if drill else uis.FSBase._get_n_dro_val(fsdata,self.ui.tap_dro_list['tap_z_end_dro'])
            fsdata['Zdepth']       = math.fabs(ze-zs)
            fsdata['Extra DRO']    = self.ui.drill_dro_list['drill_spot_tool_doc_dro'] if drill else None
            fsdata['Extra']        = uis.FSBase._get_n_dro_val(fsdata,'Extra DRO') if drill else 0.
            fsdata['op']           = getattr(self, '_update_feeds_speeds_drill') if drill else getattr(self, '_update_feeds_speeds_tap')

        elif cp == 'conv_thread_mill_fixed':
            if self.ui.conv_thread_mill_ext_int == 'external':
                fsdata['DOC DRO']      = self.ui.thread_mill_ext_dro_list['thread_mill_ext_doc_dro']
                fsdata['Extra']        = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_ext_dro_list['thread_mill_ext_major_dia_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_ext_dro_list['thread_mill_ext_minor_dia_dro']))
                fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_ext_dro_list['thread_mill_ext_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_ext_dro_list['thread_mill_ext_z_start_dro']))
                fsdata['Pitch DRO']    = self.ui.thread_mill_ext_dro_list['thread_mill_ext_pitch_dro']
                fsdata['Passes DRO']   = self.ui.thread_mill_ext_dro_list['thread_mill_ext_passes_dro']
            else:
                fsdata['DOC DRO']      = self.ui.thread_mill_int_dro_list['thread_mill_int_doc_dro']
                fsdata['Extra']        = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_int_dro_list['thread_mill_int_major_dia_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_int_dro_list['thread_mill_int_minor_dia_dro']))
                fsdata['Zdepth']       = math.fabs(uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_int_dro_list['thread_mill_int_z_end_dro'])-uis.FSBase._get_n_dro_val(fsdata,self.ui.thread_mill_int_dro_list['thread_mill_int_z_start_dro']))
                fsdata['Pitch DRO']    = self.ui.thread_mill_int_dro_list['thread_mill_int_pitch_dro']
                fsdata['Passes DRO']   = self.ui.thread_mill_int_dro_list['thread_mill_int_passes_dro']
            fsdata['Pitch']        = uis.FSBase._get_n_dro_val(fsdata,'Pitch DRO')
            fsdata['op']           = getattr(self, '_update_feeds_speeds_thread')

        elif cp == 'conv_engrave_fixed':
            fsdata['DOC DRO']      = self.ui.engrave_dro_list['engrave_z_doc_dro']
            fsdata['DOC']          = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            fsdata['op'] = getattr(self, '_update_feeds_speeds_engrave')

        elif cp == 'conv_dxf_fixed':
            fsdata['DOC DRO']      = self.ui.dxf_panel.dro_list['dxf_z_slice_depth_dro']
            fsdata['DOC']          = uis.FSBase._get_n_dro_val(fsdata,'DOC DRO')
            fsdata['op'] = getattr(self, '_update_feeds_speeds_dxf')

        # get all tool data in one place..
        sfm_minstr = 'SFM-%s%smin'%('CRB' if fsdata['material'] == 'crb' or fsdata['material'] == 'dmd' else 'HSS', "-Drill" if fsdata['is_axial'] else '-Mill')
        sfm_maxstr = 'SFM-%s%smax'%('CRB' if fsdata['material'] == 'crb' or fsdata['material'] == 'dmd' else 'HSS', "-Drill" if fsdata['is_axial'] else '-Mill')
        fsdata['sfm_lo'] = fsdata['spec_data'][sfm_minstr]
        fsdata['sfm_hi'] = fsdata['spec_data'][sfm_maxstr]
        fsdata['sfm_range'] = math.fabs(fsdata['sfm_hi']-fsdata['sfm_lo'])
        fsdata['ipr_min'] = fsdata['spec_data']['Drill-IPR-Rangemin' if fsdata['is_axial'] else 'Mill-Chiploadmin']
        fsdata['ipr_mid'] = fsdata['spec_data']['Drill-IPR-Rangemid' if fsdata['is_axial'] else 'Mill-Chiploadmid']
        fsdata['ipr_max'] = fsdata['spec_data']['Drill-IPR-Rangemax' if fsdata['is_axial'] else 'Mill-Chiploadmax']
        fsdata['diameter'] = self.ui.get_tool_diameter(fsdata['tool_number'])
        if fsdata['diameter'] == 0.0:
            raise uis.ValidationError('Tool %d is not fully defined for feeds and speeds due to zero diameter. Refer to tool %d in the Offsets tab.'%(fsdata['tool_number'], fsdata['tool_number']))
        fsdata['sfm_pr'] = fsdata['diameter']*math.pi/12.
        fsdata['loc'] = length = fsdata['tdr'].data['length'][0]['ref']
        if length == 0.: fsdata['loc'] = round(2.*fsdata['diameter']+max(fsdata['diameter']*.1,0.015),2)
        helix = fsdata['tdr'].data['helix'][0]['ref']
        if 'var' in helix: fsdata['helix'] = 'var'
        elif 'hi' in helix: fsdata['helix'] = 'hi'
        fsdata['tool_radius'] = fsdata['tdr'].data['tool_radius'][0]['ref']
        fsdata['drag'] = fsdata['tool_type'] == 'drag'
        # get the material data in one place
        if fsdata['Stepover'] is not None: fsdata['mrr_pr'] = MillFS._calc_mrr_pr(fsdata)
        if fsdata['drag']: fsdata['weighting'] = 0.
        self._calc_clamp_rpm(fsdata)
        return fsdata

    @staticmethod
    def _calc_mrr_pr(fsdata):
        return uis.FSBase._calc_mrr_per_rev(fsdata['Feed'], fsdata['Stepover'], fsdata['DOC'], fsdata['rpm'])

    @staticmethod
    def _calc_initial_stepover_pct(brn,factor=.45):
        step_over_pct = 1.0/(math.sqrt(float(brn))*.45)
        return min(max(step_over_pct,0.075),0.8)

    @staticmethod
    def _calc_pct_horsepower_left(rpm,feed,stepover,doc,Kc):
        real_hp = uis.FSBase.hp_rpm(rpm)
        spindle_hp = uis.FSBase._spindle_hp(Kc,feed,doc,stepover)
        return spindle_hp/real_hp

    def _iterate_adjust_horsepower(self, fsdata, cl, rpm, feed, stepover, doc):
        # is there horsepower left on the table? If so increase rpms and feed
        # until at spindle hp and rpm hp get closer to each other...
        _theo_sfm = fsdata['sfm_lo']+(fsdata['sfm_range']*fsdata['weighting']*fsdata['coat_factor'])
        shp_rhp_pct_difference = MillFS._calc_pct_horsepower_left(rpm, feed, stepover, doc, fsdata['Kc'])
        for n in xrange(100):
            # if the percentage of the difference between spindle_hp and
            # real_hp at the current rpm is less that _find_rpm_to_pct' (75 percent) .. then break
            if shp_rhp_pct_difference<MillFS._find_rpm_to_pct:
                test_rpm = rpm*1.05
            else:
                # need more horsepower but which way to go?
                fac = .9 if rpm>uis.FSBase._max_hp_rpm else 1.05
                test_rpm = rpm*fac

            # limit this available SFM...
            test_rpm = min(test_rpm, uis.FSBase._max_rpm)
            sfm,sfm_pct_of_range = uis.FSBase.iso_rpm_data(fsdata, test_rpm)
            if sfm_pct_of_range>.75: break
#           test_rpm = min(test_rpm,uis.FSBase._max_hp_rpm)
            # check new sfm not past thoeretical SFM
            if (test_rpm*fsdata['diameter']*math.pi)/12.0 > _theo_sfm*.90: break
            rpm, feed = (test_rpm, cl*test_rpm*fsdata['flutes'])
            shp_rhp_pct_difference = MillFS._calc_pct_horsepower_left(rpm, feed, stepover, doc, fsdata['Kc'])
            # if percentage difference between spindle hp and hp at rpm is within
            # five percent of target then quit the loop.
            if math.fabs(shp_rhp_pct_difference-MillFS._find_rpm_to_pct)<.05: break
            if test_rpm == uis.FSBase._max_hp_rpm: break
            if test_rpm >= uis.FSBase._max_rpm: break
        return (rpm,feed)

    def _iterate_stepover_pct_to_horsepower(self, fsdata, rpm, feed, doc):
        if rpm<=0: return 0.0
        brn = max(min(uis.MaterialData.max_brinell, float(fsdata['BRN'])), 0.025)
        step_over_pct = MillFS._calc_initial_stepover_pct(brn)
        stepover = fsdata['diameter']*step_over_pct
        hp_at_rpm = uis.FSBase.hp_rpm(rpm)
        for n in xrange(100):
            stepover = fsdata['diameter']*step_over_pct
            spindle_hp = uis.FSBase._spindle_hp(fsdata['Kc'],feed,doc,stepover)
            if spindle_hp < hp_at_rpm: break
            step_over_pct *= .9
        # max stepover needs to to be be a sqrt(2) of cutter diameter based on the
        # way profiling is done
        max_step = (fsdata['diameter']-2.*fsdata['tool_radius'])/math.sqrt(2.)
        return (rpm,min(stepover,max_step))

    def _check_initial_rpm_hp(self, fsdata, cl, iso_rpm, doc):
        brn = max(min(uis.MaterialData.max_brinell, float(fsdata['BRN'])), 0.025)
        step_over_pct = MillFS._calc_initial_stepover_pct(brn)
        stepover = fsdata['diameter']*step_over_pct
        hp_at_rpm = uis.FSBase.hp_rpm(iso_rpm)
        feed = cl*iso_rpm*fsdata['flutes']
        scl = uis.FSBase.stepover_chip_load(fsdata['diameter'],fsdata['flutes'],feed,iso_rpm,stepover)
        spindle_hp = uis.FSBase._spindle_hp(fsdata['Kc'],feed,doc,stepover)
        # if needed spindle_hp is above hp_at_rpm go to max_hp_rpm
        # if max_hp_rpm is lower that current iso_rpm. Current iso_rpm is 'best_iso_rpm' so increasing
        # it will exceed SFM. This will find a better rpm later...
        if spindle_hp>hp_at_rpm and  uis.FSBase._max_hp_rpm<iso_rpm: iso_rpm = uis.FSBase._max_hp_rpm
        feed = cl*iso_rpm*fsdata['flutes']
        return (iso_rpm, feed)

    def _iterate_chipload(self, fsdata, feed, rpm, doc, limit=0.00045):
        if rpm<=0: return (0.0,0.0,0.0,0.0,0.0)
        #chip load ...
        #get progressive chip load based on diameter...
        cl = uis.MaterialData.tri_range_resolver(fsdata['diameter'],.13,fsdata['ipr_min'],fsdata['ipr_mid'],fsdata['ipr_max'],MillFS._min_em_dia,MillFS._max_em_dia)
        cl_lo,cl_hi = (max(cl*.85,0.0005),cl*1.2)
        rpm, feed = self._check_initial_rpm_hp(fsdata, cl, rpm, doc)
        rpm,stepover = self._iterate_stepover_pct_to_horsepower(fsdata, rpm, feed, doc)
        for n in xrange(100):
            # stepover...
            scl = uis.FSBase.stepover_chip_load(fsdata['diameter'],fsdata['flutes'],feed,rpm,stepover)
            if not cl_lo<scl<cl_hi: break
            if rpm > uis.FSBase._max_hp_rpm:
                # reduce rpm but increase stepover
                # has the effect of increasing 'scl' or actual chipload
                rpm = max(int(round(float(rpm)*.95,uis.FSBase._rpm_round)),uis.FSBase._max_hp_rpm) #reduce rpm
                # these are for very samll stepovers
                if stepover/cl<=.3 or fsdata['is_plastic']: stepover *= 1.05
            else:
                if stepover/cl>.3 and not fsdata['is_plastic']: stepover *= .95
                feed *= 1.05
        # is there horsepower left on the table? If so increase rpms and feed
        # until at spindle hp and rpm hp get closer to each other...
        rpm, feed = self._iterate_adjust_horsepower(fsdata, cl, rpm, feed, stepover, doc)

        if feed>uis.FSBase._mach_data['max_ipm']:
            feed = uis.FSBase._mach_data['max_ipm']
            rpm,stepover = self._iterate_stepover_pct_to_horsepower(fsdata, rpm, feed, doc)
            scl = uis.FSBase.stepover_chip_load(fsdata['diameter'],fsdata['flutes'],feed,rpm,stepover)
        return (rpm, feed, stepover, cl, scl)


    def __facing(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0, 0.0,0.0,0.0)
        feed = fsdata['Feed']
        flycut = (fsdata['diameter']>1. and fsdata['flutes'] == 1) or fsdata['tool_type'] == 'flycutter'
        indexable = fsdata['tool_type'] == 'indexable'
        brn = fsdata['BRN']
        Kc = fsdata['Kc']


        #rpm .....
        if flycut:
            if fsdata['ISO'] in 'N': rpm = 1800 if brn > 170 else 2500
            elif fsdata['ISO'] in 'MKP': rpm=int(round(float(rpm)*1.1,uis.FSBase._rpm_round)) if brn > 250 else int(round(float(rpm)*1.35,uis.FSBase._rpm_round))

        #chip load ...
        cl = uis.FSBase._calc_chip_load(rpm,fsdata['flutes'],feed)
        if fsdata['ISO'] in 'N': cl = .0035 if flycut else .0025
        elif fsdata['ISO'] in 'M': cl = .001 if flycut else .0011
        elif fsdata['ISO'] in 'KP':  cl = .0012 if flycut else .0010
        else: cl = .0008 # 'S'
        feed = min(round(cl*rpm*fsdata['flutes'],1), uis.FSBase._mach_data['max_ipm'])

        if flycut: limit = .2
        elif indexable: limit = .045
        else: limit = fsdata['diameter'] if fsdata['diameter'] < fsdata['loc']*.85 else fsdata['loc']*.85
        # facing favors stepover get an initial DOC that is based on tool, or
        # minimum DOC. the 'equation gives a nice hyperbolic curve highest percent
        # at lowest Kc, visa versa...
        adj_Kc = (fsdata['Kc']/uis.FSBase._max_Kc)*1000.0
        pct_doc = .85 if indexable else (1.0/(math.sqrt(adj_Kc)*.25))-.01
        doc = min(max(limit*pct_doc,0.002),fsdata['Zdepth'])
        doc = min(doc,fsdata['Zdepth'])

        # get ideal stepover which is the tool diameter lles any bull nose radius
        # ball end mills (though not a good candidate for facing) rsult in a minium diam of .002
        corner_radius =  2.*fsdata['tool_radius']
        diam = fsdata['diameter'] if fsdata['tool_radius'] == 0.0 else fsdata['diameter'] - corner_radius if corner_radius < fsdata['diameter'] else 0.002
        # just to be safe set stepover at 95% of diameter
        stepover = diam*.87

        # since facing favors stepover .. adjust the DOC to accomodate horsepower for this stepover
        # so this is 'stepover' centric
        doc = self._iterate_doc_to_horsepower(fsdata['Kc'], rpm, feed, doc, stepover)

        #stepover ...
        stepover = self._iterate_stepover_to_horsepower(fsdata['Kc'], diam, rpm, feed, doc)

        # is there horsepower left on the table? If so increase rpms and feed
        # until at spindle hp and rpm hp get closer to each other...
        rpm, feed = self._iterate_adjust_horsepower(fsdata, cl, rpm, feed, stepover, doc)
        self.log_horsepower('Facing', fsdata['Kc'], rpm, feed, doc, stepover)
        return (round(rpm,-1), round(doc,3), feed, stepover)

    def _update_feeds_speeds_facing(self, fsdata):
        rpm, doc, feed, stepover = self.__facing(fsdata)
        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'DOC DRO',doc,)
        self._set_dro_val(fsdata,'Feed DRO',feed,'feed_format')
        self._set_dro_val(fsdata,'ZFeed DRO',feed*.32,'feed_format')
        self._set_dro_val(fsdata,'Stepover DRO',stepover)
        self.ui.update_chip_load_hint(fsdata['Stepover DRO'])

    def __profile(self, fsdata):
        if fsdata['drag']: return (0, 40.0, 0.01, 0.0)
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0, 0.0,0.0,0.0)
        feed = fsdata['Feed']
        shearhog = fsdata['tool_type'] == 'shearhog' and fsdata['flutes'] == 1
        indexable = fsdata['tool_type'] == 'indexable'
        brn = fsdata['BRN']
        loc = fsdata['loc']
        z_depth = fsdata['Zdepth']
        _c = 1.84
        # doc .8 cutter diam on harder material, min(loc,doc) on softer material
        min_doc = min(z_depth,fsdata['diameter']*.8)
        max_doc = min(z_depth, loc)
        if max_doc <= min_doc: doc = max_doc
        else:
            doc_pct = round((1.-(math.cosh(brn/uis.MaterialData.max_brinell)*_c-_c)),2)
            doc = doc_pct*max_doc
            if doc_pct >=.855: doc = max_doc
        # special cases...
        if indexable:
            if doc>.045: doc = .045
        elif shearhog and fsdata['ISO'] == 'N':
            if doc>.2: doc=.2
            feed = .01*float(rpm)

        rpm, feed, stepover, cl, scl = self._iterate_chipload(fsdata, feed, rpm, doc)
        return (round(rpm,-1), doc, feed, stepover)

    def _update_feeds_speeds_profile(self, fsdata, op='Profile'):
        rpm, doc, feed, stepover = self.__profile(fsdata)
        self.log_horsepower(op, fsdata['Kc'], rpm, feed, doc, stepover)

        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'DOC DRO',doc,)
        self._set_dro_val(fsdata,'Feed DRO',feed,'feed_format')
        self._set_dro_val(fsdata,'ZFeed DRO',feed*.32,'feed_format')
        self._set_dro_val(fsdata,'Stepover DRO',stepover)
        self.ui.update_chip_load_hint(fsdata['Stepover DRO'])

    def _update_feeds_speeds_pocket(self, fsdata):
        self._update_feeds_speeds_profile(fsdata, 'Pocket')

    def __drill(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0, 0.0, 0.0, 0.0)
        feed = fsdata['Feed']
        brn = fsdata['BRN']
        loc = fsdata['loc']
        depth = fsdata['Zdepth']
        spot = .08

        diam = max(min(MillFS._max_drill_dia,fsdata['diameter']),MillFS._min_drill_dia)

        # determine the spot depth, regardless of spot drill entry
        # based on 90 degree spot drill
        for rd in MillFS._drill_spot:
            if diam < rd[0]: spot = rd[1]; break
        # for small diameter drill where the upper spot diameter (calculated as 2*depth)
        # is larger than the drill diameter
        if diam<spot*2.0: spot = diam*.38


        cl= uis.MaterialData.tri_range_resolver(diam,.13,fsdata['ipr_min'],fsdata['ipr_mid'],fsdata['ipr_max'],MillFS._min_drill_dia,MillFS._max_drill_dia)
        rpm = uis.FSBase._clamp_rpm(uis.FSBase._calc_rpm_from_sfm(fsdata))
        r_ipr = self._iterate_ipr_to_horsepower(fsdata['Kc'], diam, rpm, cl*fsdata['flutes'])
        peck = self._calc_drill_peck(fsdata, diam, rpm, r_ipr)
        if peck>depth: peck = depth
        return (round(rpm,-1), peck, r_ipr, spot, diam)

    def _update_feeds_speeds_drill (self, fsdata):
        rpm, peck, r_ipr, spot, diam = self.__drill(fsdata)
        self.log_horsepower('Drill', fsdata['Kc'], rpm, r_ipr, uis.FSBase._true_drill_area(diam)*rpm)

        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
#       self._set_dro_val(fsdata,'DOC DRO',peck) **PP-2064 - this is disabled for now
        self._set_dro_val(fsdata,'ZFeed DRO',r_ipr*rpm,'feed_format')
        self._set_dro_val(fsdata,'Extra DRO',spot)
        self.ui.update_chip_load_hint('conv_drill_tap_fixed')

    def _update_feeds_speeds_tap(self, fsdata):
        self._set_dro_val(fsdata,'RPM DRO',750,'%d')


    def __thread(self, fsdata):
        rpm = uis.FSBase.best_iso_rpm(fsdata)
        if rpm<=0: return (0, 0.0, 0.0, 0)
        feed = fsdata['Feed']
        loc = fsdata['loc']
        pitch = fsdata['Pitch']
        pitch_depth = fsdata['Extra']
        # determine if it's a 'single point' thread mill
        # or longer...
        passes = 1 if loc >= fsdata['Zdepth'] else 4 if pitch>.08 else 3

        doc = self.ui.thread_mill_doc(pitch_depth, passes)
        cl = uis.MaterialData.tri_range_resolver(fsdata['diameter'],.125,0.00015,0.00035,0.003,MillFS._min_em_dia,MillFS._max_em_dia)
        feed = cl*rpm*fsdata['flutes']
        return (rpm, doc,feed, passes)

    def _update_feeds_speeds_thread (self, fsdata):
        rpm, doc,feed, passes = self.__thread(fsdata)
        # set DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'DOC DRO',doc)
        self._set_dro_val(fsdata,'Feed DRO',feed,'feed_format')
        self._set_dro_val(fsdata,'Passes DRO',passes,'%d')
        self.ui.update_chip_load_hint(fsdata['DOC DRO'])

    def __engrave(self, fsdata):
        if fsdata['drag']: return (0, 0.01, 30.0)
        rpm = fsdata['rpm'] # will be zero if drag tool
        feed = fsdata['Feed']
        brn = fsdata['BRN']
        loc = fsdata['loc']
        doc = min(math.fabs(fsdata['DOC']),loc)
        #assume a 90 degree engraver to calc diameter at DOC
        if doc>0.01: doc = 0.01
        diameter = 2*doc
        rpm = uis.FSBase._clamp_rpm(uis.FSBase._calc_rpm_from_sfm(fsdata, diameter))
        feed = .00075*rpm*fsdata['flutes']
        return (round(rpm,-1), doc, feed)

    def _update_feeds_speeds_engrave (self, fsdata):
        rpm, doc, feed = self.__engrave(fsdata)
        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'DOC DRO',doc)
        self._set_dro_val(fsdata,'Feed DRO',feed,'feed_format')
        self.ui.update_chip_load_hint()

    def _update_feeds_speeds_dxf (self, fsdata):
        rpm, doc, feed = self.__engrave(fsdata)
        #setting DROs
        self._set_dro_val(fsdata,'RPM DRO',rpm,'%d')
        self._set_dro_val(fsdata,'DOC DRO',doc)
        self._set_dro_val(fsdata,'Feed DRO',feed,'feed_format')
        self._set_dro_val(fsdata,'ZFeed DRO',feed*.32,'feed_format')
        self.ui.update_chip_load_hint()

    def update_feeds_speeds(self, action=''):
        try:
            fsdata = self._get_active_conv_fs_info(action)
            if fsdata['action'] == 'validate_only': return (True,'')
            fsdata['op'](fsdata)
            self._check_tool_description(fsdata,'\nDefaulting to a 2-flute HSS tool.')
            return (True,'')
        except uis.ValidationError as e:
            return (False,str(e))
        except FloatingPointError as e:
            err_msg = tooltipmgr.TTMgr().get_local_string('err_update_fs_fp')
            return (False,err_msg.format('[MillFS]'))
        except ValueError as e:
            return (False,str(e))
        except LookupError as e:
            return (False,str(e))
        except Exception as e:
            # these are damn hard to debug without more stack trace so log it.
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            err_msg = tooltipmgr.TTMgr().get_local_string('err_exception_fs')
            self.ui.error_handler.log(err_msg.format('[MillFS]',traceback_txt))
            return (False,err_msg.format('[MillFS]',str(e)))

####################################################################################################
# diam_brinell_data - get general brinell/diameter data from file
#
####################################################################################################

class diam_brinell_data(uis.TableData):

    def __init__(self,data,ui):
        uis.TableData.__init__(self,os.path.join(const.MATERIAL_BASE_PATH,data),ui)


####################################################################################################
# StepOverData - get specific 'StepOver' brinell/diameter data fomr file
#
####################################################################################################
class StepOverData(diam_brinell_data):

    def __init__(self, ui):
        diam_brinell_data.__init__(self,'mill-stepover.csv',ui)
        if self.valid: self.ui.error_handler.log('Stepover data imported')

    def lookup_stepover(self, tool_diam, brinell):
        b,val = self.lookup(brinell, tool_diam)
        return val if b else tool_diam*.2

####################################################################################################
# MillPnData - get specific 'StepOver' brinell/diameter data fomr file
#
####################################################################################################
class MillPnData(uis.PNParse):

    def __init__(self, ui):
        uis.PNParse.__init__(self, ui)
        self.mach = 'mill'
        self._read_data()

    @classmethod
    def format_parse_data(cls, vals):
        return uis.PNParse._format_axial_parse_data(vals)

    def _parse_type(self, descript):
        if uis.PNParse._type_index is None: uis.PNParse._type_index = uis.FSBase.find_tooling_keyword_index( 'type', MillFS.tool_description_parse_data()['tooling_keywords'])
        return uis.PNParse._find_tool_type(MillFS.tool_description_parse_data()['tooling_keywords'][uis.PNParse._type_index][1], descript)


