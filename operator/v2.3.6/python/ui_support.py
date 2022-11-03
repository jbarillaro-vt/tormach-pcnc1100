#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

try:
    import wingdbstub
except ImportError:
    pass

import os
import sys
import gtk
import math
import pango
import re
import glib
import copy
import constants as const
import conversational as conv
import btn
import popupdlg
import traceback
import tooltipmgr
import ui_common

####################################################################################################
# ValidationError - an excpetion class for validation issues.
#
####################################################################################################

class ValidationError(Exception):
    def __init__(self, message, errors=None):
        super(ValidationError, self).__init__(message)
        self.errors = errors

####################################################################################################
# FSProxy - empty feeds an speeds
####################################################################################################

class FSProxy:
    def __init__(self, uiobject, real_fsbaseobj):
        self.ui = uiobject
        self.fs = real_fsbaseobj
        self.fs_proxy = self

    def update_feeds_speeds(self,var=''): return (True,'')
    def clr_calced_dros(self): self.fs.clr_calced_dros()
    def tool_column_width(self): return self.fs.tool_column_width()
    def tool_description_parse_data(self): return self.fs.tool_description_parse_data()

    def current_chipload(self, typ=None):
        error_ret = (FSBase.NA,FSBase.NA,None)
        try:
            dros = self.ui.get_current_dro_info()
            tool_dro = dros['tool']
            tool_text = tool_dro.get_text()
            rpm_dro = dros['rpm']
            feed_dro = dros['r_feed']
            if not feed_dro.get_sensitive(): feed_dro = dros['z_feed'] if 'z_feed' in dros else None
            if not feed_dro: raise Exception('Can not resolve feed DRO.')
            step_dro = dros['stepover'] if 'stepover' in dros else None
            stepover = None
            tool = int(tool_text)
            valid, rpm =  conv.cparse.is_number_or_expression(rpm_dro)
            if not valid: return error_ret
            valid,feed = conv.cparse.is_number_or_expression(feed_dro)
            if not valid: return error_ret
            if step_dro:
                valid, stepover = conv.cparse.is_number_or_expression(step_dro)
                if not valid: return error_ret
            return self.fs.__class__.calc_all_chipload(self.ui, tool, feed, rpm, stepover)
        except ValueError:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.ui.error_handler.log('[Proxy]current_chipload raised ValueError - tool {} - exception {}'.format(tool_text, traceback_txt))
        except:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.ui.error_handler.log('[Proxy]current_chipload raised exception - tool {} - exception {}'.format(tool_text, traceback_txt))
        return error_ret




####################################################################################################
# FSBase - base class for machine specific speeds and feeds
#
####################################################################################################

class FSBase:

    _template = {'op'           : None,
                 'action'       : '',
                 'RPM DRO'      : None,
                 'tool_type'    : '',
                 'tool_radius'  : 0.0,
                 'tool_number'  : None,
                 'tool_descript': None,
                 'tool_width'   : 0.0,
                 'material'     : 'hss',
                 'coating'      : None,
                 'holder'       : '',
                 'ISO'          : '',
                 'BRN'          : 10.,
                 'Kc'           : 0.0,
                 'sfm_lo'       : 30.0,
                 'sfm_hi'       : 1500.0,
                 'sfm_range'    : 0.0,
                 'sfm_tryrate'  : 0.65,
                 'ipr_min'      : 0.0,
                 'ipr_mid'      : 0.0,
                 'ipr_max'      : 0.0,
                 'hp_lo'        : 0.1,
                 'hp_hi'        : 1.5,
                 'hp_rng'       : 1.4,
                 'rpm'          : 1,
                 'mrr_pr'       : 0.0,
                 'is_metric'    : False,
                 'dro_format'   : None,
                 'feed_format'  : None,
                 'in_mm_conv'   : None,
                 'tdr'          : None,
                 'weighting'    : 0.,
                 'coat_factor'  : 1.,
                 'diameter'     : 0.,
                 'sfm_pr'       : 0.0,
                 'is_axial'     : False,
                 'is_plastic'   : False,
                 'spec_data'    : None,
                 'flutes'       : 2,
                 'Peck DRO'     : None,
                 'Zdepth'       : 0.0,
                }

    tooling_keywords = [('comment'         , re.compile(r'^(?!\[\d{5}\])\[(\w|-|#|_|%|\*|@|\s|/|\.|:|,|\+|=|\?)+\]',re.IGNORECASE)),
                        ('flutes'          , re.compile(r'^\d{1,2}\s*?(FLUTE|FL)',re.IGNORECASE)),
                        ('length'          , re.compile(r'^loc:\s*?(\d*\.\d+|\d+)',re.IGNORECASE)),
                        ('tool_material'   , re.compile(r'^(carbide|HSS|CoHSS|CRB|carb|diamond|DMND)',re.IGNORECASE)),
                        ('tool_coating'    , re.compile(r'^(TiN|AlTiN|TiAlN|CNB|ZrN|TiB2|TiB|TiCN|DLC|uncoated|nACo)',re.IGNORECASE)),
                        ('tool_radius'     , re.compile(r'^(radius|r):\s?(\.\d{1,12}|\d{1,2}(\.\d{0,12})?)',re.IGNORECASE)),
                        ('tool_chamfer'    , re.compile(r'^(chamfer|c):\s?(\.\d{1,3}|\d{1,2}(\.\d{0,3})?)',re.IGNORECASE)),
                        ('tool_diameter'   , re.compile(r'^(diameter|dia):\s?(\.\d{1,12}|\d{1,2}(\.\d{0,12})?)',re.IGNORECASE)),
                       ]

    descriptor_data = {'comment'          : ({'ref' : '',         'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0, }, '#015701' ), #grey green
                       'flutes'           : ({'ref' : 2,          'conv': False, 'op' : '_match_number_zero', 'start' : 0, 'end' : 0, }, '#f5007e' ), #rose color
                       'tool_material'    : ({'ref' : 'hss',      'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0, }, '#0043e0' ), #royal blue
                       'tool_coating'     : ({'ref' : 'uncoated', 'conv': False, 'op' : '_match_std',         'start' : 0, 'end' : 0, }, '#346429' ), #dk green
                       'tool_radius'      : ({'ref' : 0.0,        'conv': True,  'op' : '_match_lable_float', 'start' : 0, 'end' : 0, }, '#307c9a' ), #grey blue
                       'tool_chamfer'     : ({'ref' : 0.0,        'conv': False, 'op' : '_match_lable_float', 'start' : 0, 'end' : 0, }, '#307c9a' ), #grey blue
                       'tool_diameter'    : ({'ref' : None,       'conv': True,  'op' : '_match_lable_float', 'start' : 0, 'end' : 0, }, '#0043e0' ), #royal blue
                       'length'           : ({'ref' : 0.0,        'conv': True,  'op' : '_match_lable_float', 'start' : 0, 'end' : 0, }, '#9a0e0e' ), #dark red
                      }

    dro_calc_color = '#c5fbc7'   # this is a light tint of green to the dro background
    NA = 'N/A'
    Kc_constant = 396000.0                  #(in terms of hp)
    _max_Kc = 750000                        # Kc for 'hardest' steel
    _machine_efficiency_factor = .8
    _dull_tool_factor = 1.35                 # higher values increase calculated spiindle HP used per MRR.
    _min_rpm = 0
    _max_rpm = 0
    _max_hp_rpm = 0
    _max_hp = 0.
    _mach_data = None
    _rpm_round = -1


    def __init__(self, ui, derived_tooling_keywords, derived_descriptor_data):
        self.ui = ui
        FSBase._mach_data = self.ui.mach_data
        # Note the active tooling_keywords keyword list resides in the derived class. FSBase prepends the
        # list to create precedence. i.e., 'loc:nnn' will take precedence over c:nnn. Where the
        # later might get recognised in the 'loc' part of the string
        for n,item in enumerate(FSBase.tooling_keywords):
            derived_tooling_keywords.insert(n,item)
        derived_descriptor_data.update(FSBase.descriptor_data)
        self.calced_dros = []

        # this is a hack setup for the real FS object vs. the proxy.
        self.fs = self
        self.fs_proxy = FSProxy(ui, self)

    @staticmethod
    def find_tooling_keyword_index(kw, lst, tup_item=0):
        for n,item in enumerate(lst):
            if item[tup_item] == kw: return n
        return -1

    @staticmethod
    def iso_rpm_data(fsdata, rpm):
        sfm = rpm*fsdata['sfm_pr']
        sfm_pct_of_range = (sfm-fsdata['sfm_lo'])/fsdata['sfm_range']
        return (sfm,sfm_pct_of_range)

    @classmethod
    def _best_kc_sfm(cls, fsdata, test_sfm, test_rpm):
        # this logic favors a best power rpr as
        # material's specific cutting force goes up ...
        test_kc = min(cls._max_Kc,fsdata['Kc'])
        pct_above_max_testsfm = 1.0+((1.0 - (float(test_kc)**2/float(cls._max_Kc**2)))/3.0)
        if fsdata['sfm_pr'] <= 0.0: return 0.0
        rpm = test_sfm/fsdata['sfm_pr']
        r_sfm = fsdata['sfm_pr']*test_rpm
        while test_sfm/r_sfm>pct_above_max_testsfm:
            rpm *= .95
            test_sfm = fsdata['sfm_pr']*rpm
        return test_sfm

    @classmethod
    def best_iso_rpm(cls, fsdata):
        _kc_threshold = 80000
        test_rpm = cls._max_rpm if fsdata['Kc']<_kc_threshold else cls._max_hp_rpm
        r_sfm = fsdata['sfm_pr']*test_rpm
        _theo_sfm = fsdata['sfm_lo']+(fsdata['sfm_range']*fsdata['weighting']*fsdata['coat_factor'])
        _best_sfm = _theo_sfm
        if r_sfm <= 0.0: return 0.0
        # if material specific cutting force (Kc) > _kc_threshold we need to reduce sfm
        # if the 'r_sfm' and '_theo_sfm' have a wide enough separation...
        if fsdata['Kc']>_kc_threshold: _best_sfm = FSBase._best_kc_sfm(fsdata,_best_sfm,test_rpm)
        lim_hi,lim_lo = (1.1,.9)
        while r_sfm/_best_sfm>lim_hi: r_sfm*=.95
        while r_sfm/_best_sfm<lim_lo: r_sfm*=1.05
        if r_sfm>_best_sfm: r_sfm = _best_sfm
        return max(min(FSBase._max_rpm,round(r_sfm/fsdata['sfm_pr'],FSBase._rpm_round)),FSBase._min_rpm)

    @classmethod
    def find_rpm_bin(cls,rpm):
        data = cls._mach_data['motor_curve']
        l = len(data)-1
        for n in range(l):
            # 0 of data[n][0] is rpm, data[n][1] is hp
            if data[n][0]<=rpm< data[n+1][0]: break
        return (data[n],data[n+1])

    @classmethod
    def hp_rpm(cls, rpm):
        revs,hp = range(2)
        data = cls._mach_data['motor_curve']
        if rpm >= cls._max_rpm: return data[len(data)-1][hp]
        lo, hi = cls.find_rpm_bin(rpm)
        _rpm_rng = (hi[revs]-lo[revs])
        _rpm = rpm-lo[revs]
        _hpl = lo[hp]
        _hp_rng = float(hi[hp]-lo[hp])
        _vec = float(_rpm)/float(_rpm_rng)
        _hp = _hpl+_vec*_hp_rng
        return _hp*cls._machine_efficiency_factor

    @classmethod
    def _hp_pct_of_max(cls, rpm):
        return cls.hp_rpm(rpm)/(cls._max_hp*cls._machine_efficiency_factor)

    @classmethod
    def update_spindle_range(cls):
        data = cls._mach_data['motor_curve']
        # the motor curve for this machine may be an empty tuple if it hasn't been
        # characterized or is in development so careful.
        if len(data) > 0:
            srpm,shp = range(2)
            cls._min_rpm = data[0][0]
            cls._max_rpm = data[len(data) - 1][0]
            _rpm = 0
            _hp = 0
            for n in range(len(data) - 1):
                h = data[n][shp]
                if data[n][shp] > _hp:
                    _hp = data[n][shp]
                    _rpm = data[n][srpm]
            cls._max_hp_rpm = _rpm
            cls._max_hp = _hp

    @staticmethod
    def new_fsdata(specific):
        fsdata = FSBase._template.copy()
        fsdata.update(specific.copy())
        return fsdata

    def _init_fsdata(self, fsdata, ui, tool, is_axial, action):
        try:
            fsdata['tool_number'] = int(tool)
            fsdata['action'] = action
            fsdata['is_axial'] = is_axial
            fsdata['spec_data'] = self.ui.material_data.get_current_spec_data()
            is_metric, g20_g21, dro_fmt, feed_fmt, units, round_off, in_mm_conv  = ui.conversational.is_metric()
            fsdata['is_metric'] = is_metric
            fsdata['dro_format'] = dro_fmt
            fsdata['feed_format'] = feed_fmt
            fsdata['in_mm_conv'] = in_mm_conv
            fsdata['tool_descript'] = ui.get_tool_description(fsdata['tool_number'])
            fsdata['tdr'] = ToolDescript.parse_text(fsdata['tool_descript'])
            cutter_material = fsdata['tdr'].data['tool_material'][0]['ref'].lower()
            fsdata['coating'] = fsdata['tdr'].data['tool_coating'][0]['ref'].lower()
            if 'crb' in cutter_material or 'carbide' in cutter_material : fsdata['material'] = 'crb'
            elif 'cobalt' in cutter_material or 'cohss' in cutter_material: fsdata['material'] = 'cob'
            elif 'diamond' in cutter_material or 'dmnd' in cutter_material: fsdata['material'] = 'dmd'
            fsdata['tool_type'] = fsdata['tdr'].data['type'][0]['ref'].lower()
            #if not self.ui.material_data: return None
            spec_data = ui.material_data.get_current_spec_data()
            fsdata['Kc'] = spec_data['Kc']
            fsdata['BRN'] =  max(min(MaterialData.max_brinell, float(spec_data['BRN'])), 0.025)
            fsdata['ISO'] = spec_data['ISO'].upper()
            # further common calculations
            fsdata['coat_factor'] = FSBase._calc_coating_factor(fsdata)
            fsdata['weighting'] = FSBase._weighting(fsdata)
            fsdata['is_plastic'] = fsdata['Kc'] < 25000
            fsdata['flutes'] = fsdata['tdr'].data['flutes'][0]['ref']
        except ValueError:
            if tool is None or tool == "":
                raise ValueError('Tool number is required.')
            else:
                raise ValueError('%s is an invalid tool number.'%tool)
        return True

    @staticmethod
    def _weighting(fsdata):
        if fsdata['ISO'] in 'K':  _fac = .9
        elif fsdata['ISO'] in 'P': _fac = .85
        elif fsdata['ISO'] in 'M': _fac = .8
        elif fsdata['ISO'] in 'N': _fac = .95
        elif fsdata['ISO'] in 'S': _fac = .75
        elif fsdata['ISO'] in 'H': _fac = .65
        return _fac

    @staticmethod
    def dro_in_calc_state(dro):
        return dro.get_style().base[gtk.STATE_NORMAL] == gtk.gdk.Color(FSBase.dro_calc_color)

    @staticmethod
    def _get_n_dro_val(fsdata, dro_name=None):
        dro = fsdata[dro_name] if isinstance(dro_name,str) else dro_name # allow for either direct dro or fsdata reference
        valid, n = (False, 0.) if dro is None else conv.cparse.is_number_or_expression(dro)
        return n/fsdata['in_mm_conv'] if valid else 0.

    @staticmethod
    def dro_on_activate(dro, text):
        dro.set_text(text)
        if not hasattr(dro,'user_data'): return
        if dro.user_data['fs_value'] != text:
            conv.cparse.clr_alarm(dro)
            return
        dro.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color(FSBase.dro_calc_color))

    @staticmethod
    def clr_dro_user_data(dro):
        if not hasattr(dro,'user_data'): return
        dro.user_data['fs_value'] = ''
        conv.cparse.clr_alarm(dro)

    @classmethod
    def _clamp_rpm(cls, rpm):
        return int(max(min(rpm, cls._max_rpm),cls._min_rpm))

    @staticmethod
    def _calc_mrr_per_minute(feed, stepover, doc):
        return feed*stepover*doc

    @staticmethod
    def _calc_mrr_per_rev(feed, stepover, doc, rpm):
        if rpm<=0: return 0.0
        return FSBase._calc_mrr_per_minute(feed, stepover, doc)/rpm

    @staticmethod
    def _calc_coating_factor(fsdata):
        r = 1.0
        if fsdata['ISO'] == 'P':     #Steel
            if fsdata['coating'] in ['altin','tialn']: r = 1.08
            elif fsdata['coating'] == 'ticn': r = 1.06
            elif fsdata['coating'] == 'tin': r = 1.03
            elif fsdata['coating'] == 'naco': r = 1.1
        elif fsdata['ISO'] == 'S':   #Hi Alloy Steel, Titanium, Iconel
            if fsdata['coating'] in ['altin','tialn']: r = 1.1
            elif fsdata['coating'] == 'ticn': r = 1.06
            elif fsdata['coating'] == 'tin': r = 1.03
            elif fsdata['coating'] == 'naco': r = 1.1
        elif fsdata['ISO'] == 'M':   #Stainless
            if fsdata['coating'] in ['altin','tialn']: r = 1.05
            elif fsdata['coating'] == 'ticn': r = 1.06
            elif fsdata['coating'] == 'tin': r = 1.09
        elif fsdata['ISO'] == 'K':   #Cast Iron
            if fsdata['coating'] in ['altin','tialn']: r = 1.1
            elif fsdata['coating'] == 'ticn': r = 1.06
            elif fsdata['coating'] == 'tin': r = 1.09
        elif fsdata['ISO'] == 'N':   #Aluminum, Brass, BRonze, Copper, Plastic
            if fsdata['coating'] == 'zrn' : r = 1.1
            elif fsdata['coating'] == 'tib': r = 1.06
            elif fsdata['coating'] == 'tib2': r = 1.09
            elif fsdata['coating'] == 'uncoated': r = .95
            elif fsdata['coating'] == 'dlc': r = 1.12
        elif fsdata['ISO'] == 'H':   #Hardenned Steel
            if fsdata['coating'] in ['altin','tialn']: r = 1.05
            elif fsdata['coating'] == 'naco': r = 1.1
        return r

    @staticmethod
    def stepover_chip_load(cutter_diam, flutes, ipm, rpm, stepover, action=''):
        if stepover is None: return None
        if stepover <= 0.0: return FSBase.NA if action == 'NA_on_zero' else 0.0
        if cutter_diam <= 0.0: return FSBase.NA if action == 'NA_on_zero' else 0.0
        cl = FSBase._calc_chip_load(rpm,flutes,ipm)
        if stepover>=round(cutter_diam/2.,4): return cl
        return cl*(2*math.sqrt(stepover*cutter_diam-(stepover**2)))/cutter_diam

    @staticmethod
    def _calc_chip_load(rpm,flutes,ipm):
        if rpm == 0 or flutes == 0: return 0.
        return ipm/rpm/flutes

    @staticmethod
    def _calc_rpm_from_sfm(fsdata,diam=None):
        #rpm .....
        sfm_lo = fsdata['sfm_lo']
        sfm_hi = fsdata['sfm_hi']*.9
        sfm_c = .88*FSBase._calc_coating_factor(fsdata)
        sfm = sfm_lo + (sfm_hi-sfm_lo)*sfm_c
        if diam is None: diam = fsdata['diameter']
        return int(round((12*sfm)/(diam*math.pi),FSBase._rpm_round)) if diam>0.0 else 0

    def _calc_clamp_rpm(self, fsdata):
        rpm = 0.0
        if fsdata['sfm_pr'] > 0.0:
            rpm = (int)((fsdata['sfm_hi']*fsdata['coat_factor']*fsdata['weighting'])/fsdata['sfm_pr'])
            rpm = max(min(rpm, FSBase._max_rpm),FSBase._min_rpm)
        fsdata['rpm'] = int(round(rpm,FSBase._rpm_round))
        return fsdata['rpm']

    @classmethod
    def mrr_spindle_hp(cls, Kc, mrr):
        raw_material_hp_consumption = (mrr*Kc/cls.Kc_constant)
        machine_hp_used = raw_material_hp_consumption/cls._machine_efficiency_factor
        return machine_hp_used*cls._dull_tool_factor

    @classmethod
    def _spindle_hp(cls, Kc, feed, doc, stepover=1.0):
        return cls.mrr_spindle_hp(Kc,FSBase._calc_mrr_per_minute(feed, stepover, doc))

    @classmethod
    def thread_mrr(cls, t_maj, t_min, rpm):
        try:
            if isinstance(t_maj,str): t_maj = float(t_maj)
            if isinstance(t_min,str): t_min = float(t_min)
            if isinstance(rpm,str): rpm = float(rpm)
            doc = math.fabs(t_maj-t_min)/2.0
            area = doc*(doc*math.tan(math.radians(30)))
            circ = math.pi*(math.fabs(t_min)+doc/2.0)
        except:
            area = circ = rpm = 0.0
            print 'exception in FSBase.thread_mrr'
        return area*circ*rpm

    @staticmethod
    def _curve(style,x,rng,skew):
        norm = 0.0 if rng[0]>=0. else 0.-rng[0]
        l=rng[0]+norm; h=rng[1]+norm; x=(min(max(x+norm,l),h))
        if style == 'sigmoid':
            # returns the value in the range as a percentage on the
            # sigmoid curve.. skew=5 is normal, 10 steeper, 3 wider
            x = (x/float(h)*2.0)-1.0
            return 1.0/(1.0+math.exp(-skew*x))
        if style == 'exp_decay':
            # NOTE: skews that are less than 10% of the range steepen the curve
            #       more that 10% flatten the curve
            return 1.0-math.exp(-(float(x)/float(skew)))


    @staticmethod
    def _true_drill_area(diam):
        return (diam**2)*(math.pi/4)
#       r = diam/2.
#       h = r/math.tan(math.radians(62))          # nominal 124 degree point drill
#       return (math.pi*r*(r+math.hypot(h,r)))    #(area of cone)*rpm

    def log_horsepower(self, op, Kc, rpm, feed, doc, stepover=1.0):
        hp_rpm = FSBase.hp_rpm(rpm)
        mrr = FSBase._calc_mrr_per_minute(feed, stepover, doc)
        hp_consumed = FSBase.mrr_spindle_hp(Kc, mrr)
        self.ui.error_handler.log('F&S{:>10}  MRR: {:2.3}cu/in. HP@{:d}rpm={:1.2}  HP-consumed:{:1.2}  HP-spare:{:1.2}'.format(op,mrr,int(rpm),hp_rpm,hp_consumed,hp_rpm-hp_consumed))

    def _set_dro_val(self, fsdata, dro_name, val, fmt='dro_format'):
        if not dro_name in fsdata: print '_set_dro_val: %s not found in fsdata' % dro_name; return
        dro = fsdata[dro_name]
        if dro is None: return
        calced_text = fsdata[fmt]%(val*fsdata['in_mm_conv']) if fmt in fsdata else fmt%val
        dro.set_text(calced_text)
        dro_data = dro.user_data if hasattr(dro,'user_data') else None
        if dro_data is None:
            dro_data = dict(fs_value=None)
            setattr(dro,'user_data',dro_data)
            if dro not in self.calced_dros: self.calced_dros.append(dro)
        dro_data['fs_value'] = calced_text
        self.ui.exec_modify_callback(dro)
        dro.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color(FSBase.dro_calc_color))

    def clr_calced_dros(self):
        calc_color = gtk.gdk.color_parse(FSBase.dro_calc_color)
        for dro in self.calced_dros:
            assert (hasattr(dro,'user_data'))
            if dro.get_style().base[gtk.STATE_NORMAL] == calc_color:
                dro.user_data['fs_value'] = ''
                conv.cparse.clr_alarm(dro)

    def _calc_drill_peck(self, fsdata, diam, rpm, ipr):
        # generate parabola for determing peck depth relative to
        # diameter
        if fsdata['tool_type'] in ['spot','centerdrill']: return 0.0
        # check to see if the Z-depth is many factors of the drill diameter
        # need to calculate at what point the chips pack into the flutes and cuase scuffing.
        # here is a case where peck needs to be reduced.
        if math.fabs(fsdata['Zdepth'])>diam*2.2:
            dl = .04; dh = 1.0
            _d = min(max(.04,diam),1.0) # peg _dia to .04 to 1.0
            _dpct = (_d-dl)/(dh-dl)
            pl = .38; ph = .7
            peck_pct = ph-_dpct*(ph-pl)
            return round(_d*peck_pct,3)
        max_d_to_peck = .9
        exageration = -2.
        max_peck_diam = .375
        peck_pct = ((diam-max_peck_diam)**2)*exageration+max_d_to_peck
        #adjust up or down based on hardness of material
        _brn = min(fsdata['BRN'],500)
        _sgn = -1. if _brn>250 else 1.
        peck_pct += float((_brn-250)**2)/float(250**2)*.2*_sgn
        peck = round(peck_pct*diam,2 if diam > 0.1 else 3)
        # peck rate is adjusted to horsepower, if the drill begins to bog down
        # the chipload increases causing more bog down, etc.
        shp = FSBase._spindle_hp(fsdata['Kc'], ipr, FSBase._true_drill_area(diam)*rpm)
        avail_hp = FSBase.hp_rpm(rpm)
        hp_margin_pct = (avail_hp-shp)/avail_hp
        pct_break = .26
        if hp_margin_pct < pct_break:
            peck *= 1.0-hp_margin_pct
            peck = max(min(peck,diam*(1.-pct_break)),.02)
        # this calulates a percentage of distance of the full Z depth based on
        # drill diameter. E.g. a small drill (.125) would allow for peck == 90pct
        # of full depth to equal full depth (why even do a peck). A .400 diameter drill would
        # have a larger allowance.
        a_hi = .95
        a_lo = .8
        a_rng = a_hi-a_lo
        d = max(.01,min(diam,.42)) # cap the diameter to a value between .01 and .420
        b = ((d/2.)**2)*22.675736  # converts the area of the diameter -constrained to .01 to .42 (rises by R**2) to a value between 0 and 1.0
        break_pct = a_lo+a_rng*b
        break_depth = break_pct*math.fabs(fsdata['Zdepth'])
        if math.fabs(peck) >= break_depth: peck = 0.0 # no peck just go for it
        if peck>math.fabs(fsdata['Zdepth']): peck = 0.0
        return round(peck,3)

    def _iterate_stepover_to_horsepower(self, Kc, diam, rpm, ipr, doc):
        hp_at_rpm = FSBase.hp_rpm(rpm)
        stepover = diam*.85
        for n in xrange(100):
            if FSBase._spindle_hp(Kc, ipr, doc, stepover) < hp_at_rpm: return stepover
            stepover *= .9
        return stepover

    def _iterate_ipr_to_horsepower(self, Kc, diam, rpm, ipr):
        hp_at_rpm = FSBase.hp_rpm(rpm)
        vc = FSBase._true_drill_area(diam)*rpm
        for n in xrange(100):
            if FSBase._spindle_hp(Kc, ipr, vc) < hp_at_rpm: return ipr
            ipr *= .9
        return ipr

    def _iterate_doc_to_horsepower(self, Kc, rpm, feed, doc, stepover=1.0):
        hp_at_rpm = FSBase.hp_rpm(rpm)
        for n in xrange(100):
            if FSBase._spindle_hp(Kc, feed, doc, stepover) < hp_at_rpm: return doc
            doc *= .9
        return doc

    def _check_tool_description(self, fsdata, extra=''):
        if not any(fsdata['tool_descript']):
            self.ui.error_handler.write('Feeds and Speeds: there is no description for tool: {:d}.{:s}'.format(int(fsdata['tool_number']),extra),const.ALARM_LEVEL_LOW)

####################################################################################################
# ToolDescript - general info class for parsing tool description in the offsets page
#
####################################################################################################

class ToolDescript:
    _MAT_MIN, _MAT_MAX = range(2)
    candidate = None
    cutter_params = None
    _data = None
    _part_number = re.compile(r'^\[\d{5}\]')
    _number_pat = re.compile(r'(\d*\.\d+|\d+)')
    # https://stackoverflow.com/questions/44111169/remove-trailing-zeros-after-the-decimal-point-in-python
    _trailing_zeros = re.compile(r'(?:(\.)|(\.\d*?[1-9]\d*?))0+(?=\b|[^0-9])')

    @classmethod
    def set_class_data(cls, data):
        cls._data = data

    @classmethod
    def set_tool_parse_data(cls,data):
        cls.candidate = data['candidates']
        cls.cutter_params = data['tooling_keywords']

    # -class ToolDescriptRec : inner class for parse data -------------------------------------------
    class ToolDescriptRec:
        _INFO, _COLOR = range(2)
        _data = None
        _float = re.compile(r'([-\+]?(\d{0,3}\.\d{1,9}|\d{1,3}\.?))')

        def __init__(self, text, text_buffer=None):
            self.index = []
            self.data = copy.deepcopy(ToolDescript._data)
            self.text_buffer = text_buffer
            if  text_buffer:
                tag_table = text_buffer.get_tag_table()
                if not tag_table.get_size():
                    for key, data in self.data.iteritems():
                        color_spec = self.data[key][ToolDescript.ToolDescriptRec._COLOR]
                        tag = self.text_buffer.create_tag(key, foreground=color_spec)
            self.text = text

        def _match_std(self, tdr, match_str):
            tdr['ref'] = match_str

        def _match_number_zero(self, tdr, match_str):
            tdr['ref'] = int(match_str[0]) if isinstance(tdr['ref'],int) else float(match_str[0]) if isinstance(tdr['ref'],float) else match_str[0]

        def _match_number_one(self, tdr, match_str):
            tdr['ref'] = int(match_str[1:]) if isinstance(tdr['ref'],int) else float(match_str[1:]) if isinstance(tdr['ref'],float) else match_str[1:]

        def _match_set_false(self, tdr, match_str):
            tdr['ref'] = False

        def _match_set_true(self, tdr, match_str):
            tdr['ref'] = True

        def _match_lable_float(self, tdr, match_str):
                f = ToolDescript.ToolDescriptRec._float.search(match_str)
                if f: tdr['ref'] = float(f.group())

        def add_key_data(self, key, match_str, start, end):
            tdr = self.data[key][ToolDescript.ToolDescriptRec._INFO]
            getattr(self, tdr['op'])(tdr, match_str)
            self.index.append(key)
            tdr['start'] = start
            tdr['end'] = end
            if self.text_buffer:
                self.text_buffer.apply_tag_by_name(key,
                                                   self.text_buffer.get_iter_at_offset(start),
                                                   self.text_buffer.get_iter_at_offset(end))

        def eq_data(self, _tdr):
            # '==' operator will work, python dos a recursive
            # '==' drill down through the data structures.
            return self.data == _tdr.data

        def differences(self, _tdr):
            # looks at the 'raf' values of the more important
            # tool attributes.
            def __has_item_changed(item, _diff_level):
                if item in self.data:
                    if item not in _tdr.data or self.data[item][0]['ref'] != _tdr.data[item][0]['ref'] : _diff_level += 1
                return _diff_level

            difference_level = 0;
            difference_level = __has_item_changed('flutes', difference_level)
            difference_level = __has_item_changed('type', difference_level)
            difference_level = __has_item_changed('tool_material', difference_level)
            difference_level = __has_item_changed('tool_diameter', difference_level)
            return difference_level


#       def to_pango(self):
#           _normal, _alt = range(2)
#           _end_span = '</span>'
#           pango_str = ''
#           last_pos = 0
#           base_color = '#000000' #black
#           tl = len(self.text)
#           for key in self.index:
#               tdr = self.data[key][ToolDescript.ToolDescriptRec._INFO]
#               color = self.data[key][ToolDescript.ToolDescriptRec._COLOR]
#               if tdr['start'] > last_pos:
#                   pango_str += '<span forecolor=' + base_color + '>' + self.text[last_pos:tdr['start']] + _end_span
#               pango_str += '<span forecolor=' + color + '>' + self.text[tdr['start']:tdr['end']] + _end_span
#               last_pos = tdr['end']
#           if tl > last_pos:
#               pango_str += '<span forecolor=' + base_color + '>' + self.text[last_pos:] + _end_span
#           return pango_str


    # -class ToolDescript---------------------------------------------------------------------------
    def __init__(self, text_buffer):
        self.text_buffer = text_buffer
        self.text = ''
        self.pango_string = ''
        self.ininhibit_auto_advance = False

    @staticmethod
    def parse_text(text, text_buffer=None):
        if text is None: text = ''
        tdr = ToolDescript.ToolDescriptRec(text, text_buffer)
        tl = len(text)
        t_start = ind = 0
        while ind < tl:
            incr = 1
            test = text[ind:]
            if ToolDescript.candidate.match(test):
                for try_match in ToolDescript.cutter_params:
                    match = try_match[1].match(test)
                    if match:
                        match_str = match.group(0)
                        if not any(match_str): continue
                        incr = len(match_str)
                        tdr.add_key_data(try_match[0], match_str, t_start, t_start + incr + (ind-t_start))
                        break
            ind += incr
            if ord(test[0])<128: t_start += incr
        return tdr

    @staticmethod
    def differences(descript0, descript1):
        tdr0 = ToolDescript.parse_text(descript0)
        tdr1 = ToolDescript.parse_text(descript1)
        return tdr0.differences(tdr1)

    def parse(self):
        start_iter, end_iter = self.text_buffer.get_bounds()
        self.text_buffer.remove_all_tags(start_iter, end_iter)
        self.text = self.text_buffer.get_text(start_iter, end_iter, False)
        return ToolDescript.parse_text(self.text, self.text_buffer)

    def _parse_pn(self, text_buffer, ui):
        start_iter, end_iter = self.text_buffer.get_bounds()
        text = self.text_buffer.get_text(start_iter, end_iter, False)
        if len(text) not in (5,7): return
        if text.startswith('[') and not text.endswith(']'): return
        text = text.strip('[]')
        if len(text) != 5 or PNParse.part_number.match(text) is None: return
        try:
            descript, diam, typ = ui.pn_data.pns[text]
            if ui.g21:
                descript = ToolDescript.convert_text(descript,('metric',))
                diam = str(float(diam)*25.4)
            descript += ' ['+text+']'
            self.text_buffer.set_text(descript)
            model, sel_iter = ui.tool_treeview.get_selection().get_selected()
            path = model.get_path(sel_iter)
            dat = dict()
            if diam is not None and any(diam): dat['diameter'] = diam
            if typ is not None: dat['type'] = typ
            dat['cmd'] = ['no-refresh','no_g10']
            if ui.set_tool_table_data(model, path[0], dat):
                self.ininhibit_auto_advance = True
        except KeyError:
            print 'ToolDescript:_parse_pn not finding pn:%s' % (text)

    @staticmethod
    def convert_text(text, action=('')):
        # Change convertable data in a tool description
        # between metric and imperial ..
        if not text: return ''
        # Note: a 'ToolDescriptRec' (tdr) contains the start and end poition of the
        # item of interest fomr parsing - this is used for syntax high-lighting
        # but also very useful here...
        tdr = ToolDescript.parse_text(text)
        # first create a sorted stack of key entries that qualify:
        # The key's that qualify have their 'conv' values as True.
        # Note: the items to be changed that are closer to the beginning
        # of the string are at the bottom of the stack - the stack is sorted by position
        # in the string from first to last..
        _start,_end,_ref = range(3)
        conv_stack = list()
        for k in tdr.data:
            v = tdr.data[k]
            if 'conv' not in v[0]: continue
            if not v[0]['conv']: continue
            if v[0]['start'] == 0 and v[0]['end'] == 0: continue
            index = 0
            if conv_stack:
                for n in range(len(conv_stack)):
                    index = n+1
                    if v[0]['start']<conv_stack[n][_start]:
                        index = n
                        break
            conv_stack.insert(index,  (v[0]['start'], v[0]['end'], v[0]['ref']))
        factor = 25.4 if 'metric' in action else 1.0 if 'imperial' in action else 0.039370079
        while conv_stack:
            # stack is 'popped' with the last items in the string
            # done first. This way as the length of the 'new' insertion changes the
            # length of the string, the position of the items closer to the beginning
            # of the string isn;t changed.
            grp = conv_stack.pop()
            new_value = grp[_ref]*factor
            _t1 = text[:grp[_start]]
            _t2 = text[grp[_end]:]
            _target = text[grp[_start]:grp[_end]]
            _num = ToolDescript._number_pat.findall(_target)
            if not _num: continue
            num_pos = _target.find(_num[0])
            fmt_str = '{}{:.3f}' if 'metric' in action else '{}{}' if 'full_precision' in action else '{}{:.4f}'
            if 'high_precision' in action:
                assert 'full_precision' not in action
                fmt_str = '{}{:.4f}' if 'metric' in action else '{}{:.6f}'
            _new = fmt_str.format(_target[:num_pos],new_value)
            # remove trailing zeros...
            if 'full_precision' not in action:
                remove_count = 2 if 'metric' in action else 3
                while remove_count > 0:
                    if _new[len(_new)-1] != '0': break
                    _new = _new[:-1]
                    remove_count -= 1
            # stick it all back together...
            text = _t1+_new+_t2
        return text

    def toggle_auto_advance(self, state=False):
        self.ininhibit_auto_advance = state

    def on_changed(self, text_buffer, ui):
        self._parse_pn(text_buffer, ui)
        tool_descript_rec = self.parse()
#       pango_str = tool_descript_rec.to_pango()

####################################################################################################
# -class ToolDescriptorEntry
#
####################################################################################################
class ToolDescriptorEntry(gtk.TextView):

    def __init__(self, ui, number_tools, tool_parse_data):
        super(ToolDescriptorEntry, self).__init__()
        ToolDescript.set_tool_parse_data(tool_parse_data)
        self.overlay_params = tool_parse_data['tv_overlay_params']
        self.add_y_offset = tool_parse_data['tv_overlay_params']['height_offset']
        self._active = False
        self.ui = ui
        self.editable = None
        self.set_wrap_mode(gtk.WRAP_NONE)
        self.set_editable(True)
        self.number_tools = number_tools
        self.connect('visibility-notify-event', self.on_text_view_visibility)

        # Hack!  We can't reliably get any signal if a user covers up the GtkEntry that we're associated
        # with.  Tried lots of stuff - horribly frustrating.  One obvious thing users may do is switch
        # notebook tabs.  So we tie into both of those signals and dismiss everything.
        self.ui.notebook.connect('switch-page', self.on_notebook_switch_page)
        self.ui.offsets_notebook.connect('switch-page', self.on_notebook_switch_page)

        text_view_buffer = self.get_buffer()
        self.tool_descript = ToolDescript(text_view_buffer)
        text_view_buffer.connect_after('changed', self.tool_descript.on_changed, ui)
        self.tree_view = ui.tool_treeview
        self.tree_selection = ui.tool_treeview.get_selection()
        self.tree_store = ui.tool_liststore
        self.tree_selection.connect('changed',self.on_tree_row_changed)
        # we don't want to be visible just because later somebody calls a .show_all() on the offsets notebook tab.
        # we manage our own visibility based on events and state.
        self.set_no_show_all(True)
        self.fixed = ui.tool_offsets_fixed
        self.fixed.add(self)
        self.row_width = 0
        self.sel_path = None
        self.row_height = 0
        self.scroll_adjustment = ui.scrolled_window_tool_table.get_vscrollbar().get_adjustment()
        self.scroll_adjustment.connect('value_changed', self.on_vscroll_change_value)
        self.description_column = self.overlay_params['descript_column']
        self.tool_description_column = self.tree_view.get_column(self.description_column)
        cell_renderers = self.tool_description_column.get_cell_renderers()
        cell_renderers[0].connect('editing-started', self.on_tool_description_column_editing_started)
        # if an editing started event happens in any other 'cell' then shut down the textview.
        cols = len(self.tree_view.get_columns())
        for n in range(self.description_column+1,cols):
            cell_renderers = self.tree_view.get_column(n).get_cell_renderers()
            if cell_renderers is None: continue
            cell_renderers[0].connect('editing-started', self.on_non_tool_description_column_editing_started)

        self.tip_window = None

        # Do this to match the exact text positioning of the gtk.Entry that is normally used for table cell editing.
        # This way the text doesn't "bounce" up and to the left when you move in/out of cell editing mode.
        self.set_border_window_size(gtk.TEXT_WINDOW_TOP, 2)
        self.set_border_window_size(gtk.TEXT_WINDOW_LEFT, 2)

    def on_vscroll_change_value(self, adjustment):
        self.shutdown_view()

    def on_deferred_grab_focus(self, widget):
        widget.grab_focus()
        # Note: '_active' is set here in a deferred action after the signal storm has
        # settled. If done during 'allocation' time the 'on_deferred_grab_focus' might be
        # invoked with a scroll change causing a 'shutdown_view' immediatley. 'shutdown_view'
        # is gated with '_active', so it will have no effect as long as '_actve' is off.
        self._active = True

    def on_notebook_switch_page(self,  notebook, page, page_num):
        self.shutdown_view()

    def on_non_tool_description_column_editing_started(self, cell_renderer, editable, path):
        self.shutdown_view()

    def on_tool_description_column_editing_started(self, cell_renderer, editable, path):
        self.editable = editable
        if isinstance(editable, gtk.Entry):
            self.editable.connect('size-allocate',self.on_allocate_editable)

    def on_text_view_visibility(self, widget, event):
        glib.idle_add(self.on_text_view_deferred_visibility)

    def on_text_view_deferred_visibility(self):
        self.grab_focus()

    def on_tree_row_changed(self, tree_selection):
        self.shutdown_view()

    def on_text_view_key_press(self, text_view, event, data=None):
        if event.keyval == gtk.keysyms.Escape: self.shutdown_view()
        elif event.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            start_iter, end_iter = self.get_buffer().get_bounds()
            text = self.get_buffer().get_text(start_iter, end_iter, False)
            self.set_visible(False)
            row = self.sel_path[0]
            dat = {'proc':getattr(self.ui, '_parse_pn_text')}
            glib.idle_add(self.ui.on_tool_description_column_edited, None, row, text, self.tree_view.get_model(),dat)
            if hasattr(self.ui, 'tool_diameter_column') and not self.tool_descript.ininhibit_auto_advance:
                glib.idle_add(self.ui.tool_table_update_focus, row, self.ui.tool_diameter_column, True)
            elif hasattr(self.ui, 'x_geo_offset_column') and not self.tool_descript.ininhibit_auto_advance:
                glib.idle_add(self.ui.tool_table_update_focus, row, self.ui.x_geo_offset_column, True)
            else:
                self.shutdown_view()
            self.tool_descript.toggle_auto_advance()
            glib.idle_add(self.ui.tool_table_update_observer, row)
            return True

    def on_allocate_editable(self, widget, allocation):
        if not isinstance(widget, gtk.Entry): return
        tree_selection = self.tree_view.get_selection()
        model, sel_iter = tree_selection.get_selected()
        text = ''
        # it is possible there is no current selection.
        # you can get into this state by just typing which kicks in the treeview search behavior.  then just press Enter twice.
        # first dismisses the search box and the second starts to edit the cell.
        self.ui.error_handler.log('ON-ALLOCATE:  widget {}:  Allocation: {}'.format(widget.__class__, allocation))
        if sel_iter:
            add_y_offset = self.add_y_offset
            text = self.tree_store.get_value(sel_iter,1)
            if text is None: text = ''
            self.sel_path = model.get_path(sel_iter)
            rh = int(round(self.row_height))
            rp = rh*self.sel_path[0]
            x_offset, y_offset = (0,0)
            parent = widget.get_parent()
            r = parent.get_allocation()
            fixed_alloc = self.fixed.get_allocation()
            x_offset, y_offset = (x_offset+r[0],y_offset+fixed_alloc[1])
            self.set_size_request(allocation[2], allocation[3])
            self.fixed.move(self, x_offset+allocation[0]-fixed_alloc[0], y_offset+allocation[1]+add_y_offset)
            self.key_press_handler_id = self.connect('key-press-event', self.on_text_view_key_press)
            self.get_buffer().set_text(text)

        # confirm we're on the tool notebook page before showing description editing tip window.
        # in some error handling situations, we may have auto-flipped to the Status tab already.
        # and then the tool description window pops up and covers up all the notebook tabs
        # and this is overly complicated because of the different noteboook page numbering across machine types.
        if self.ui.current_notebook_page_id == 'notebook_offsets_fixed':
            # the reason for a factory method is to de-couple this object from any UI knowledge.
            # is it a 'mill' , is it a 'lathe', etc. 'ui' is a pass through and 'GetTipWindow'
            # decides the correct object to create. This is not a memory leak as GetTipWindow
            # returns a singleton.
            self.tip_window = GetTipWindow(self, self.sel_path[0], text, 'show,sync')

        self.set_visible(True)
        glib.idle_add(self.on_deferred_grab_focus, self)

    def active(self): return self._active

    def shutdown_view(self):
        if not self._active: return
        self.set_visible(False)
        if self.editable: self.editable.remove_widget()
        self.editable = None
        self._active = False
#       if self.touchscreen_enabled:
#           pass
        if self.tip_window: self.tip_window.hide()

####################################################################################################
# class MaterialData, MaterialDataCombo
#
####################################################################################################
class MaterialDataCombo(gtk.ComboBox):

    def __init__(self, owner, name, width, height):
        super(MaterialDataCombo,self).__init__()
        gtk.Buildable.set_name(self,name)
        self.set_size_request(width, height)
        self.set_visible(True)
        self.owner = owner
        child = self.get_child()

        # Please don't change this point size back to 12.  Its 10 so that it matches the look of the text when
        # the combobox is open and the user is making a selection.  It feels off if the text appearance changes
        # after the user makes a selection.  This is how all the other combo boxes within PP work.
        child.modify_font(pango.FontDescription('Roboto Condensed 10'))

        self.set_model(gtk.ListStore(str))
        cell = gtk.CellRendererText()
        self.pack_start(cell, True)
        self.add_attribute(cell, 'text', 0)
        setattr(self,'evtbox',gtk.EventBox())
        self.evtbox.set_size_request(width,height)
        self.evtbox.add(self)
        self.evtbox.show_all()
        self.evtbox.connect('enter-notify-event',owner.ui.on_mouse_enter)
        self.evtbox.connect('leave-notify-event',owner.ui.on_mouse_leave)
        gtk.Buildable.set_name(self.evtbox, name)

    def get_text(self):
        return self.get_active_text()

    def select_text(self, text, action=None):
        model = self.get_model()
        for n, k in enumerate(model):
            iter_n = model.get_iter(n)
            value = model.get_value(iter_n,0)
            if value == text:
                if action == 'set_combo': self.set_active(n)
                return n
        return -1

    def set_text(self, text):
        return self.owner.set_from_text(text, 'set_combo')


class MaterialData:
    MATERIAL_DATA_CSV = os.path.join(const.MATERIAL_BASE_PATH, 'material-data.csv')
    max_brinell = 739
    combo_bounding_box = gtk.gdk.Rectangle(10,50,120+95,30)

    def __init__(self,ui,fixed):
        self.ui = ui
        self.fixed = fixed
        # provide a 'no selection' entry
        self.conv_material_combobox = MaterialDataCombo(self, 'material_type', 105, MaterialData.combo_bounding_box.height)
        self.conv_material_spec_combobox = MaterialDataCombo(self, 'material_subtype', 95, MaterialData.combo_bounding_box.height)
        self.fixed.put(self.conv_material_combobox.evtbox, MaterialData.combo_bounding_box.x, MaterialData.combo_bounding_box.y)
        self.fixed.put(self.conv_material_spec_combobox.evtbox, MaterialData.combo_bounding_box.width-95, MaterialData.combo_bounding_box.y)
        self.conv_material_combobox.connect('changed',self.__on_conv_material_changed)
        self.conv_material_spec_combobox.connect('changed',self.__on_conv_material_spec_changed)
        #build a list of material spec liststores in a dictionary
        self.material_specs = dict()
        self.current_catagory = ''
        self.catagory_list = []
        self.valid = True

        material_info = MaterialData.MATERIAL_DATA_CSV
        try:
            last_catagory = ''
            with open(material_info, 'r') as materials:
                for line in materials:
                    # remove leading and trailing whitespace from line
                    line = line.strip()
                    if line.startswith('#') or not any(line): continue
                    catagory, spec, fs_data = line.split(',', 2)
                    catagory = catagory.strip()
                    spec = spec.strip()
                    fs_data = fs_data.split(',')
                    catagory = last_catagory if not any(catagory) else catagory
                    spec_data = {'ISO' : fs_data[0], 'BRN' : fs_data[1], 'Kc' : float(fs_data[2]), 'Tensil_Yield' : fs_data[12], 'Tensil_Ultimate' : fs_data[13] }
                    for n in [(3,'SFM-HSS-Mill'),(4,'SFM-CRB-Mill'),(5,'SFM-HSS-Drill'),\
                              (6,'SFM-CRB-Drill'),(7,'SFM-HSS-Lathe'),(8,'SFM-CRB-Lathe'),\
                              (9,'Mill-Chipload'),(10,'Drill-IPR-Range'),(11,'Lathe-IPR-Range')]:
                        MaterialData.__unpack_range_data(fs_data[n[0]], spec_data, n[1])
#                   spec_data['descrip_id'] = fs_data[12]  - not implimented yet will be used by tool-tips.
                    if catagory in self.catagory_list:
                        list_store = self.material_specs[catagory]['store']
                        list_store.append([spec,spec_data.copy()])
                        continue
                    self.catagory_list.append(catagory)
                    last_catagory = catagory
                    list_store = gtk.ListStore(str,object)
                    list_store.append([spec,spec_data])
                    self.material_specs[catagory] = dict(store = list_store, sub_catagory = 0)
                    self.conv_material_combobox.get_model().append([catagory])
            self.conv_material_combobox.set_active(0)
            self.ui.error_handler.log('Material data imported')
        except:
            self.ui.error_handler.write("Failed to import material data: %s" % (material_info), const.ALARM_LEVEL_DEBUG)
            self.valid = False

        self.refreshidle = self.__create_update_button('RefreshIdle',  vis_state=True)
        self.refreshon = self.__create_update_button('RefreshOn', vis_state=False)

    def __create_update_button(self, btn_name, vis_state):
        updatebtn = btn.ImageButton(btn_name+'.png', btn_name+'_fs')
        gtk.Buildable.set_name(updatebtn, btn_name)
        updatebtn.set_size_request(32, 32)
        updatebtn.set_tooltip_text("Refresh feeds and speeds suggestions")
        updatebtn.connect('button-release-event', self.__on_update_button_release_event)
        self.fixed.put(updatebtn, 220, 49)
        updatebtn.show_all() if vis_state else updatebtn.hide_all()
        # hook up events for tool tip mgr
        updatebtn.connect('enter-notify-event', self.ui.on_mouse_enter)
        updatebtn.connect('leave-notify-event', self.ui.on_mouse_leave)
        return updatebtn

    @staticmethod
    def __unpack_range_data(indata, d , key):
        key0 = key + 'min'
        key1 = key + 'mid'
        key2 = key + 'max'
        for ch in '-:|':
            if ch in indata:
                tmp = indata.split(ch)
                break
        ltmp = len(tmp)
        for n in range(ltmp):
            tmp[n] = tmp[n].strip()
            try:
                tval = float(tmp[n])
            except:
                tval = tmp[n]
            if n == 0: d[key0] = tval
            elif n == 1 : d[key2 if ltmp == 2 else key1] = tval
            else: d[key2] = tval

    def __on_conv_material_changed(self, widget, data=None):
        model = widget.get_model()
        self.current_catagory = widget.get_active_text()
        try:
            new_model = self.material_specs[self.current_catagory]['store']
            self.conv_material_spec_combobox.set_model(new_model)
            current_cell = self.conv_material_spec_combobox.get_cells()
            if not current_cell:
                cell = gtk.CellRendererText()
                self.conv_material_spec_combobox.pack_start(cell, True)
                self.conv_material_spec_combobox.add_attribute(cell, 'text', 0)
            self.conv_material_spec_combobox.set_active(self.material_specs[self.current_catagory]['sub_catagory'])
            self.update_btn_on()
        except:
            self.ui.error_handler.log('MaterialData.__on_conv_material_changed: - error in material type as key')

    def __on_conv_material_spec_changed(self, widget, data=None):
        active_oridinal = widget.get_active()
        self.material_specs[self.current_catagory]['sub_catagory'] = active_oridinal
        self.update_btn_on()

    def __set_combo_active(self, combo, item):
        model = combo.get_model()
        iter_n = model.get_iter_first()
        index = 0
        while iter_n is not None:
            value = model.get_value(iter_n, 0)
            if value.upper() == item.upper():
                combo.set_active_iter(iter_n)
                combo.set_active(index)
                break
            iter_n = model.iter_next(iter_n)
            index += 1

    def __set_active(self, cat, sub_cat):
        self.__set_combo_active(self.conv_material_combobox, cat)
        self.__set_combo_active(self.conv_material_spec_combobox, sub_cat)

    def __get_spec_data(self, cat):
        catagory, sub_cat = cat
        if catagory not in self.catagory_list:
            raise LookupError('MaterialData: %s catagory not found' % (catagory))
        list_store = self.material_specs[catagory]['store']
        for n, k in enumerate(list_store):
            iter_n = list_store.get_iter(n)
            value = list_store.get_value(iter_n,0)
            if value == sub_cat: return list_store.get_value(iter_n,1)
        raise LookupError('MaterialData: %s sub-catagory not found' % (sub_cat))

    def __get_text(self):
        return (self.conv_material_combobox.get_active_text(), self.conv_material_spec_combobox.get_active_text())

    def __on_button_press_release(self, widget, event, data=None):
        return False

    def __set_from_conversational_text(self, text):
        _text = text.strip()
        _text = _text.split(' :')
        if len(_text) == 2:
            self.__set_from_text(_text[0],'set_combo')
            self.__set_from_text(_text[1],'set_combo')
        else:
            self.ui.error_handler.log('MaterialData.set_from_conv_edit_text: failed on text: %s' % text)

    def __set_from_text(self, text, action=None):
        text = text.strip()
        if text in self.catagory_list:
            n = self.conv_material_combobox.select_text(text, action)
            self.current_catagory = text if n >=0 else ''
            return n
        else:
            n = self.conv_material_spec_combobox.select_text(text, action)
            if n >= 0:
                try:
                    new_model = self.material_specs[self.current_catagory]['store']
                    self.conv_material_spec_combobox.set_model(new_model)
                    self.material_specs[self.current_catagory]['sub_catagory'] = n
                    self.conv_material_spec_combobox.set_active(n)
                except:
                    self.ui.error_handler.log( 'MaterialData.set_from_text: - error in setting conv_material_spec_combobox')
            return n
        return -1

    def __on_update_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)

        if widget is self.refreshon:
            if self.ui.redis.hget('uistate', 'show_feeds_speeds_warning') == 'True':
                # the green button that actually changes DROs was clicked, not the idle button
                dialog = popupdlg.ok_cancel_popup(self.ui.window,
                                                  "These feed and speed suggestions are a starting point for your convenience.  Your individual machine, tooling, and stock material will have variability which may require you to adjust the values to achieve desired results.\n\nTormach is not responsible for any problems that may occur using these values.",
                                                  cancel=False,
                                                  checkbox=True)
                dialog.run()
                # remember if they no longer want to be annoyed...
                self.ui.redis.hset('uistate', 'show_feeds_speeds_warning', str(dialog.checkbox.get_active()))
                dialog.destroy()

        # These are buttons in same location z order wise.
        # The "look" change is just hiding one and not the other.
        self.refreshon.hide_all()
        self.refreshidle.show_all()
        self.ui.update_feeds_speeds()

    #-----------------------------------------------------------------------------------------------
    # public methods (interface)
    #-----------------------------------------------------------------------------------------------
    @staticmethod
    def tri_range_resolver(diam,crossover,mn,md,mx,diam_lo=.01,diam_hi=1.0):
        # a tri range is two ranges in 3 positive numbers: e.g., .01-.13-.75
        # as in 'material-data.csv'. This finds whihc range to look in and
        # returns where the 'diam' is in that range as a percentage.
        l,h = (mn,md) if diam < crossover else (md,mx)
        min_diam = diam_lo if diam<crossover else crossover
        diam_rng = (crossover-diam_lo) if diam<crossover else (diam_hi-crossover)
        ipr_rng= h-l
        return max(min(l+(ipr_rng*((diam-min_diam)/diam_rng)),mx),mn)

    def set_active(self, cat, sub_cat):
        self.__set_active(cat, sub_cat)

    def conversational_text(self, text=None):
        if text is None:
            return self.get_conversational_text()
        else:
            self.__set_from_conversational_text(text)
            return None

    def get_conversational_text(self):
        mat,sub = self.__get_text()
        return mat+' : '+sub

    def get_current_spec_data(self):
        return self.__get_spec_data(self.__get_text())

    """
    Update the apply button for conversational feeds and speeds
    (either make it active or not)
    """
    def update_btn_on(self):
        if self.ui.fs_mgr:
            self.ui.fs_mgr.clr_calced_dros()

        if hasattr(self, 'refreshidle'): self.refreshidle.hide_all()
        if hasattr(self, 'refreshon'): self.refreshon.show_all()

    def enable(self, active_state=True):
        self.refreshidle.enable() if active_state else self.refreshidle.disable()
        self.refreshon.enable() if active_state else self.refreshon.disable()
        self.conv_material_combobox.set_sensitive(active_state)
        self.conv_material_spec_combobox.set_sensitive(active_state)

# This in theory might be a way to support localization of material descriptions
# if/when we get that far.  Commented out for now to avoid pylint error flagging.
#
    def get_material_description(self, param):
        spec_data = self.get_current_spec_data()
        cat, sub_cat = self.__get_text()
        material_str  = ' {} - {}'.format(cat, sub_cat)
        spec_str = '<span font_desc="Droid Sans Mono Bold 10">'
        spec_str += '\n'+'{:>18} : <span color="#0000ff">{}</span>'.format('ISO catagory',spec_data['ISO'])
        spec_str += '\n'+'{:>18} : <span color="#0000ff">{}</span>'.format('Brinell',spec_data['BRN'])
        spec_str += '\n'+'{:>18} : <span color="#0000ff">{}</span>'.format('Tensile-yield',spec_data['Tensil_Yield'])
        spec_str += '\n'+'{:>18} : <span color="#0000ff">{}</span>'.format('Tensile-ultimate',spec_data['Tensil_Ultimate'])
        spec_str += '</span>'
        return (material_str,spec_str)

####################################################################################################
# class PNParse - parse and create dictionary from parts number data
#
####################################################################################################

class PNParse:

    _type_index = None
    _number = re.compile(r'\d*\.\d+|\d+\.?|')
    part_number = re.compile(r'^\d{5}')
    axial_arrangement = ['type','comment','flutes','radius','chamfer','length','coating','material','diameter'] #,'helix']
    radial_arrangement = ['type','comment','holder','insert','width','coating','material','length','min-bore','front-angle','back-angle']

    def __init__(self, ui):
        self.ui = ui
        self.path = os.path.join(const.MATERIAL_BASE_PATH,'tooling-part-numbers.csv')
#       last_line = None
        self.pns = {}
        self.mach = ''    # present in base class to avoid pylint error flagging otherwise

    @classmethod
    def _format_axial_parse_data(cls, vals):
        if 'type' in vals and 'drill' in  vals['type'].lower():
            if 'radius' in vals: vals['radius'] = ''
        val = ''
        for item in PNParse.axial_arrangement:
            if item in vals and vals[item]: val = val + ' ' + vals[item] if val else vals[item]
        return val

    @classmethod
    def _format_radial_parse_data(cls, vals):
        val = ''
        for item in PNParse.radial_arrangement:
            if item in vals and vals[item]: val = val + ' ' + vals[item] if val else vals[item]
        return val

    def _get_num(self, diam, fmt='%.4f'):
        num = None
        if 'mm' in diam:           num = float(PNParse._number.findall(diam)[0])/25.4
        elif diam.startswith('m'): num = float(diam.strip('m'))/25.4
        elif '/' in diam:
            frac = PNParse._number.findall(diam)
            numbers = []
            for f in frac:
                if not any(f): continue
                if f[0] in '1234567890': numbers.append(f)
            n = len(numbers)
            if n == 2: num = float(numbers[0])/float(numbers[1])
            elif n == 3: num = float(numbers[0]) + (float(numbers[1])/float(numbers[2]))
        else: num = float(PNParse._number.findall(diam)[0])
        return PNParse._trim_trailing_zeros(fmt%(num)) if num else ''

    @staticmethod
    def _trim_trailing_zeros(s):
        l = len(s)
        for n in range(l-1,-1,-1):
            if s[n] == '0': s = s[:-1]; continue
            if s[n] == '.': break
            if s[n].isdigit(): break
        if not s: s = '0'
        return s

    @staticmethod
    def coating(f):
        if not any(f): return ''
        f = f.lower()
        return  'TiCN' if 'ticn' in f else\
                'uncoated' if 'uncoated' in f else\
                'AlTiN' if 'altin' in f else\
                'AlTiN' if 'tialn' in f else\
                'TiN' if 'tin' in f else\
                'CrN' if 'crn' in f else ''

    @staticmethod
    def cutter_material(f):
        if not any(f): return ''
        f = f.lower()
        return 'carbide' if 'carbide' in f else 'CoHSS' if 'hss' in f and 'co' in f else 'HSS'

    @staticmethod
    def _find_tool_type(regx, descript):
        words = descript.split()
        for w in words:
            typs = regx.findall(w)
            if any(typs): return typs[0].lower()
        return None


    def _parse_type(self, descript):
        # Base class method has to be present to avoid pylint error false positives (and is good general coding practice)
        assert False

    def format_parse_data(self, vals):
        # Base class method has to be present to avoid pylint error false positives (and is good general coding practice)
        assert False

    def _read_data(self):
        try:
            pn_count = 0
            with open(self.path, 'r') as pns:
                for line in pns:
                    vals = dict()
                    typ = diam = ''
                    if not any(line): continue
#                   last_line = line               # for debugging
                    # remove leading and trailing whitespace from line
                    fields = line.strip().split(',')
                    if 'PN' in fields[0]: continue  # title line - first line, so ignore
                    for n,f in enumerate(fields):
                        f = f.strip()
                        if n > 1: f = f.lower()
                        if n is 0:
                            key = f.strip()
                            continue
                        elif n is 1 and f:                                                       # designation
                            vals['type'] = f
                            vals['fs_type'] = self._parse_type(f)
                        elif n is 2 and f: vals['material'] = PNParse.cutter_material(f)    # cutting material
                        elif n is 3: vals['coating'] =  PNParse.coating(f)                       # coating
                        elif n is 4 and f:vals['flutes'] = '%dFL'%int(f)                         # flutes
                        elif n is 5 and f:                                                       # tool diameter
                            if not f: continue
                            diam = self._get_num(f)
                            vals['diameter'] = 'dia:%s'%diam
                        elif n is 6 and f: vals['helix'] = f                                     # helix
                        elif n is 7:                                                             # radius end
                            rad = PNParse._number.findall(f)
                            rad = PNParse._trim_trailing_zeros(rad[0])
                            vals['radius'] = 'R:0.' if not any(rad) else 'R:' + rad
                        elif n is 8 and f:                                                       #chamfer end
                            chmf = PNParse._number.findall(f)
                            chmf = PNParse._trim_trailing_zeros(chmf[0])
                            vals['chamfer'] = '' if not any(chmf) else 'C:' + chmf
                        elif n is 9 and f:  vals['length'] = 'loc:%s'%self._get_num(f)              # loc
                        elif n is 10 and f: vals['insert'] = f.upper()                           # insert
                        elif n is 11 and f: vals['angle'] = '%.2f'%float(f)                      # insert angle
                        elif n is 12 and f: vals['width'] =  'W:%.4f'%float(f)                   # width
                        elif n is 13 and f: vals['FA'] = 'FA:%.2f'%float(f)                      # FA
                        elif n is 14 and f: vals['BA'] = 'BA:%.2f'%float(f)                      # BA
                        elif n is 15 and f: vals['min-bore'] = 'min-bore:%.4f'%float(f)          # min-bore
                        elif n is 16 and f: vals['gen_type'] = f.upper()                         # gen_type (RA-type(radial-axial))
                        elif n is 17 and f: vals['mach_type'] = f.upper()                        # machine type L, M, LM

                    # add the key only if the machine is in the part number's 'mach_type' list.
                    if self.mach.upper() in vals['mach_type']: self.pns[key] = (self.format_parse_data(vals),diam,vals['fs_type'])
                    pn_count += 1
            self.ui.error_handler.log('Part number data imported from file {:s}, count = {:d}'.format(self.path, pn_count))
        except:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.ui.error_handler.log("Failed to import part number data from file: %s   Exception: %s" % (self.path, traceback_txt))



####################################################################################################
# class TableData - retrieve and pack into dictionary, csv files
#
####################################################################################################

class TableData:

    def __init__(self, path, ui):
        self.header = None
        self.ui = ui
        self.data = []
        self.max_V = 0.
        self.valid = False
        count = False
        try:
            with open(path, 'r') as table:
                for line in table:
                    items = line.split(',')
                    l = []
                    for val in items: l.append(float(val))
                    if count:
                        self.data.append(tuple(l))
                        self.max_V = max(self.max_V,l[0])
                    else: self.header = tuple(l)
                    count = True
            self.valid = True
        except:
            self.ui.error_handler.write("Failed to import stepover data: %s" % (path), const.ALARM_LEVEL_DEBUG)

    def lookup(self, _H, _V):
        if _V > self.max_V: _V = self.max_V
        for i,item in enumerate(self.header):
            if _H <= item: break
        for n,item in enumerate(self.data):
            if _V <= item[0]:
                return (True,self.data[n][i])
        return (False,_V)


####################################################################################################
# _DTWBase - base class for tool description tip window
#
####################################################################################################
__dtw_object=None
def GetTipWindow(tool_descriptor_entry, row, text, action=''):
    global __dtw_object
    assert isinstance(tool_descriptor_entry.ui, ui_common.TormachUIBase), 'GetTipWindow can not resolve UI object.'
    if not __dtw_object:
        if tool_descriptor_entry.ui.machine_type == const.MACHINE_TYPE_MILL:
            __dtw_object = DTWMill(tool_descriptor_entry.ui)
        elif tool_descriptor_entry.ui.machine_type == const.MACHINE_TYPE_LATHE:
            __dtw_object = DTWLathe(tool_descriptor_entry.ui)
        else:
            assert False, "Unsupported value for machine_type: {:d}".format(tool_descriptor_entry.ui.machine_type)
    actions = action.split(',')
    if 'show' in actions: __dtw_object.show()
    return __dtw_object

class _DTWBase(object):
    def __init__(self, ui, color, list_store, pos_x, pos_y):
        super(_DTWBase, self).__init__()
        self.ui = ui
        self.height = 350
        self.padding = 10
        self.parent = ui.fixed
        self.pos_x = pos_x
        self.pos_y = pos_y
        self.event_box = gtk.EventBox()
        self.fixed = gtk.Fixed()
        self.label = gtk.Label()
        self.event_box.add(self.fixed)
        # label is filled in by subclasses
        self.std_markup = markup = '<span weight="regular" font_desc="Roboto Condensed 10" foreground="black">{}</span>'
        self.fixed.put(self.label, self.padding, self.padding)

        # init tool description tips table
        self.description_tips_liststore = list_store
        self.description_tips_treeview = gtk.TreeView(self.description_tips_liststore)
        # create columns
        # add columns to treeview
        for n,name in enumerate(['Attribute','Pattern']):
            self.description_tips_treeview.append_column(self.__add_col(name,n))
        self.event_box.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(color))
        self.event_box.connect("button-release-event", self.__on_button_release)

    def __on_button_release(self, widget, data=None):
        # button click anywhere on the window dismisses it by hiding.
        self.hide()

    def __add_col(self, col_name, pos):
        col = gtk.TreeViewColumn(col_name)
        tips_font = pango.FontDescription('Roboto Condensed 10')
        render = gtk.CellRendererText()
        render.set_property('editable', False)
        render.set_property('cell-background', '#FFFFFF')
        render.set_property('font-desc', tips_font)
        col.pack_start(render, True)
        col.set_attributes(render, text=pos)
        return col

    def show(self):
        if not self.event_box.get_parent():
            self.parent.put(self.event_box, self.pos_x, self.pos_y)
        else:
            self.parent.move(self.event_box, self.pos_x, self.pos_y)
        self.event_box.show_all()

    def hide(self):
        self.event_box.hide_all()

    def destroy(self):
        self.event_box.destroy()


class DTWMill(_DTWBase):
    def __init__(self, ui , pos_x=383, pos_y=408):
        self.ui = ui
        self.width = 605
        self.text_height = 95
        ls = gtk.ListStore(str, str)
        ls.append(["Flutes", "2FL 2FLUTE (default: 2flute)"])
        ls.append(["Material", "carbide HSS CoHSS CRB carb diamond DMND (default: HSS)"])
        ls.append(["Type", "drill centerdrill tap ball chamfer spot flat taper bullnose lollypop flycut shearhog drag\nsaw indexable threadmill engraver"])
        ls.append(["Coating", "TiN AlTiN TiAlN CNB ZrN TiB2 TiB TiCN DLC uncoated nACo (default: uncoated)"])
        ls.append(["Radius", "R:.02 radius:0.02"])
        ls.append(["Diameter", "dia:2.6 diameter:2.6"])
        ls.append(["Comment", "any text in square brackets other than a part number: [1/4] [#I] [#19]"])
#       ls.append(["Helix", "variable:30 var:30 high:30 hi30"])
        ls.append(["Length of Cut", "loc:0.875 LOC:0.75"])
#       ls.append(["Holder", "ER Solid Chuck Modular"])
        super(DTWMill, self).__init__(ui, '#D5E1B3',ls, pos_x, pos_y)
        self.event_box.set_size_request(self.width, self.height)

        msg = """Rich tooling descriptions are used for conversational feeds and speeds suggestions.\n
For Tormach tooling, enter the 5 digit part number to autofill description (e.g. 35571).
For others, use the attributes below to characterize the tool. (ex: "endmill 3FL R:0 loc:1.0 carbide TiN")"""
        self.label.set_markup(self.std_markup.format(msg))
        self.description_tips_treeview.set_size_request(self.width-self.padding*2, self.height - self.text_height - self.padding)
        self.fixed.put(self.description_tips_treeview, self.padding, self.text_height)

class DTWLathe(_DTWBase):
    def __init__(self, ui, pos_x=24, pos_y=410):
        self.width = 654
        ls = gtk.ListStore(str, str)
#       ls.append(["ANSI Holder", "MVLN-R SDJC-R STFC-L"])
#       ls.append(["Insert", "SC_T-21.51 VNMG-431"])
        ls.append(["Type", "drill tap face-turn facing turning profiling chamfer spot centerdrill boring parting threading\nreamer"])
        ls.append(["Radius", "R:.02 radius:0.02"])
        ls.append(["Front Angle", "FA:90"])
        ls.append(["Back Angle", "BA:90"])
        ls.append(["Material", "carbide HSS CoHSS CRB carb diamond DMND (default: HSS)"])
        ls.append(["Diameter", "dia:0.625 diameter:.309"])
        ls.append(["Coating", "TiN AlTiN TiAlN CNB ZrN TiB2 TiB TiCN DLC uncoated nACo (default: uncoated)"])
        ls.append(["Length of Cut", "loc:0.857 LOC:0.875"])
        ls.append(["Width", "width:.118 W:.118"])
        ls.append(["Min Bore", "min-bore:.522"])
        ls.append(["Flutes", "2FL 2Flute (default: 2Flute)"])
        ls.append(["Comment", "any text in square brackets other than a part number: [1/4] [SGGT-R]"])
        super(DTWLathe, self).__init__(ui, '#B3E1D7', ls, pos_x, pos_y)
        self.event_box.set_size_request(self.width, self.height)

        msg = """Rich tooling descriptions are used for conversational feeds and speeds suggestions.\n
For Tormach tooling, enter the 5 digit part number to autofill description (e.g. 35650).
For others, use the attributes below to characterize the tool. (ex: "Face-turn carbide FA:83.00 BA:3.00 TiN")"""
        self.label.set_markup(self.std_markup.format(msg))

        # create a scrolled window to hold the treeview
        self.scrolled_window = gtk.ScrolledWindow()
        self.scrolled_window.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.scrolled_window.add(self.description_tips_treeview)
        self.scrolled_window.set_size_request(self.width-self.padding*2, self.height - 85 - self.padding)
        self.fixed.put(self.scrolled_window, self.padding, 85)

