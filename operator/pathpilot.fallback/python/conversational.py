# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# conversational base class

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import sys
import gtk
import math
import re
import uuid
import copy
from constants import *
from errors import *
from math import *
import time
import operator
import string
import traceback
import linuxcnc

####################################################################################################
# nc_file - basic class to preserve extensions
#
####################################################################################################

class nc_file():
    _std_ext = '.nc'

    @staticmethod
    def create_default_filename(title_text):
        if not title_text: return title_text
        # replace disallowed characters with '-'
        # disallowed characters are '/', ':', '\'
        # these cause trouble because they are not allowed in file names
        # '/' is Linux, '\' is Windows as is ':' (drive letter separater)
        processed_filename = title_text.replace('/', '-')
        processed_filename = processed_filename.replace('\\', '-')
        processed_filename = processed_filename.replace(':', '-')
        # filename as title-year-month-day-hour-minutes-seconds.ngc
        # e.g. odturn-2013-12-05-14-57-59.ngc
        #dt = datetime.datetime.now()
        # processed_filename += dt.strftime-%Y-%m-%d-%H-%M-%S")
        return processed_filename

    def __init__(self,fname):
        self.__filename = ''
        self.__ext = nc_file._std_ext
        fname = nc_file.create_default_filename(fname)
        if not fname: return
        ext_pos = fname.rfind('.')
        self.__ext = nc_file._std_ext if ext_pos<0 else fname[ext_pos:]
        self.__filename = fname if ext_pos<0 else fname[:ext_pos]

    def filename(self): return self.__filename
    def extension(self): return self.__ext
    def ce_copy(self,other):
        self.__filename = other.__filename+'-copy'
        self.__ext = other.__ext

    def __str__(self): return self.__filename+self.__ext
    def __bool__(self): return bool(self.__filename)

####################################################################################################
# conversational_base
#
####################################################################################################

class conversational_base(object):

    code_name_map = dict()                  # code_name : ConversationalInterface()
    shared_routine_map = dict()             # conv_page_num : ConversationalSharedInterface
    routine_names = {}                      # Map routine_name ('Face') : object
    conversational_type = None
    start_of_gcode = '\n\n(----- Start of G-code -----)\n(<cv1>)'
    end_of_step_prefix = '(----- End of'    # the following end strings are broken up for pattern recognition
    end_of_step_suffix = ' {} -----)\n'     # on 'end_of_step_prefix' - to support legacy conversational files.
    M30_line = 'M30 (End of Program)'
    end_of_gcode = '(</cv1>)'
    pp_version = ''
    _NA_ = 'N/A'
    m1 = 'M1 (Optional Stop <m1>)\n'
    m1_text = 'M1 (Optional Stop <m1>)'
    m1_multi_tool_step = 'M1 (Optional Stop - multi tool<m1>)'
    style_types = ['Style','Thread Direction']
    _g20_data = { 'gcode' : 'G20', 'dro_fmt': '%2.4f', 'feed_fmt': '%.1f', 'units': 'inches', 'round_off': 1e-5, 'ttable_conv':1.0,  'mrr_units': 'cu-in/min', 'mrr_conv': 1.0}
    _g21_data = { 'gcode' : 'G21', 'dro_fmt': '%3.3f', 'feed_fmt': '%.1f', 'units': 'mm'    , 'round_off': 1e-4, 'ttable_conv':25.4, 'mrr_units': 'cu-cm/min', 'mrr_conv': 16.3871 }


    def __init__(self, ui_base, status, myerror_handler, redis, hal):
        self.ui = ui_base
        self.redis = redis
        self.hal = hal
        self.status = status
        self.error_handler = myerror_handler
        self.wo_re = re.compile(r'^G?(\d+\.?\d?) *(?:P(\d+))?$', re.IGNORECASE)


    def get_conv_title(self, conv_dro_list):
        title = conv_dro_list['conv_title_dro'].get_text()
        # replace disallowed characters with '-'
        # disallowed characters are '/', ':', '\'
        # these cause trouble because they are not allowed in file names
        # '/' is Linux, '\' is Windows as is ':' (drive letter separater)
        # Toss away wildcards also as that will lead to mystery pain I'm sure
        title = title.replace('/', '-')
        title = title.replace('\\', '-')
        title = title.replace(':', '-')
        title = title.replace('*', '-')
        title = title.replace('?', '-')
        return title

    def is_metric(self, action=''):
        is_metric = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210
        dat = conversational_base._g21_data if is_metric else conversational_base._g20_data
        feed_units = 'meters/minute' if is_metric else 'feet/minute'
        if action == 'as_dictionary': return (is_metric,dat)
        return (is_metric, dat['gcode'], dat['dro_fmt'], dat['feed_fmt'], dat['units'], dat['round_off'] ,dat['ttable_conv'])

    def get_dro_format(self):
        return '%3.3f' if self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210 else '%2.4f'

    @classmethod
    def conv_version_string(cls):
        return '(PathPilot Version: %s)' % (cls.pp_version)

    @classmethod
    def set_pp_version(cls,version):
        cls.pp_version = version

    @classmethod
    def write_ending_G30(cls, code, comment, newline=True, m1=True, end_tag=True):
        newline = '\n' if newline else ''
        code.append(newline+'G30 '+comment)
        if end_tag: code.append(conversational_base.end_of_gcode)

    @staticmethod
    def insert_conversational_end_tag(code, step_type='Step'):
        if not isinstance(code,list): return
        line_no = len(code)
        while line_no > 0:
            line_no -= 1
            if 'G30' in code[line_no]: break
        if line_no >= 0:
            code.insert(line_no+1, conversational_base.end_of_gcode)
            end_str = (conversational_base.end_of_step_prefix+conversational_base.end_of_step_suffix).format(step_type)
            code.insert(line_no+2, end_str)

    @staticmethod
    def std_end_conversational_step(code, step_type='Step'):
        end_str = (conversational_base.end_of_step_prefix+conversational_base.end_of_step_suffix).format(step_type)
        code.append(end_str)
        code.append(conversational_base.M30_line)

# ------------------------------------------------------------------------------------
# Common - strings
# ------------------------------------------------------------------------------------
    def _coolant_on(self, tool_number): return 'M8'

    def _coolant_off(self, tool_number): return 'M9'

#--------------------------------------------------------------------------------------------------
# common validation
#--------------------------------------------------------------------------------------------------

    def validate_work_offset(self, widget, param=None):
        work_offset = widget.get_text().strip().upper()

        # pythex.org for the win!  Wow has this turned ugly, but it works.  I tested it against these
        # success cases:
        #
        #    G53
        #    G54
        #    G54.1P100
        #    G54.1 P200
        #    54.1 P500
        #    G59
        #    G59.1
        #    G59.2
        #    G59.3
        #    G59.4
        # and made sure it regects these:
        #    G59.23
        #    G54.1P
        #
        # best part is that match 1 and match 2 becomes the numbers and we can easily validate them
        # once they match.

        success = False  # assume failure
        msg = 'Work offset not valid (G54-G59, G59.1, G59.2, G59.3, or G54.1 Pnnn where nnn is 1-500)'

        match = self.wo_re.match(work_offset)
        if match:
            groups = match.groups()
            value = int(float(groups[0]) * 10)  # Should be 540, 550, 593
            if 540 <= value <= 593:
                if value == 541:
                    if len(groups) == 2 and groups[1] != None:
                        # validate extended work offset parameter
                        value2 = int(groups[1])
                        if 1 <= value2 <= 500:
                            success = True  # valid extended work offset parameter
                else:
                    # not using ext work offsets so make sure they didn't add a P word
                    if len(groups) == 1 or (len(groups) == 2 and groups[1] == None):
                        # and make sure the work offset is an integer (except for 591 592 or 593)
                        if value in (591, 592, 593) or (value % 10 == 0):
                            success = True

        if success:
            # work offset OK
            # patch up the string as the regex treats the G prefix as option as its used for work offset DRO validation
            if work_offset[0] != 'G':
                work_offset = 'G' + work_offset

            # work offset OK
            cparse.clr_alarm(widget)   # mill doesn't need these, but lathe does until they align
            return True, work_offset, ''
        else:
            cparse.raise_alarm(widget, msg)  # mill doesn't need these, but lathe does until they align
            return False, '', msg


    def validate_range_float_exclusive(self, widget, is_metric, rng):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget)
        if is_valid_number and (rng[0] < any_num < rng[1]):
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be a number over %.4f and under %.4f\n' % rng
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an number\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_range_float_gtlower(self, widget, is_metric, rng):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget)
        if is_valid_number and (rng[0] < any_num <= rng[1]):
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be an number over %.4f up to, including %.4f\n' % rng
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an number\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_range_float(self, widget, is_metric, rng):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget)
        lr,hr = rng
        if hr is None: hr = 1e10
        if lr is None: lr = -1e10
        if is_valid_number and (lr <= any_num <= hr):
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be a number from %.4f to %.4f\n' % rng
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an number\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_any_num_gt0(self, widget, is_metric):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget.get_text())
        if is_valid_number and any_num > 0.0:
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be greater than or equal to zero\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an integer\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_any_num_gte0(self, widget, is_metric):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget.get_text())
        if is_valid_number and any_num >= 0.0:
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be an number greater than or equal to zero\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be a number\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_any_int_gte0(self, widget, is_metric):
        (is_valid_number, any_num) = cparse.is_int(widget.get_text())
        if is_valid_number and any_num >= 0:
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif is_valid_number:
            msg = 'Entry must be an integer greater than or equal to zero\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        msg = 'Entry must be an integer\n'
        cparse.raise_alarm(widget, msg)
        return False, 0, msg

    def validate_any_int(self, widget, is_metric,rng=None):
        (is_valid_number, any_num) = cparse.is_int(widget.get_text())
        if is_valid_number:
            if rng:
                l,h = rng
                if l is None: l = -sys.maxsize
                if h is None: l = sys.maxsize
                if not l<=any_num<=h:
                    msg = 'Entry must be an integer less than %d\n'%(h+1) if l == -sys.maxsize else 'Entry must be an integer greater than %d\n'%(l-1)
                    cparse.raise_alarm(widget, msg)
                    return False, 0, msg
            cparse.clr_alarm(widget)
            return True, any_num, ''
        else:
            if isinstance(rng,str):
                if rng == 'allow_empty':
                    if not any(widget.get_text()):
                        cparse.clr_alarm(widget)
                        return True, '', ''
            msg = 'Entry must be an integer\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_any_num(self, widget, is_metric):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget)
        if is_valid_number:
            cparse.clr_alarm(widget)
            return True, any_num, ''
        else:
            msg = 'Entry error\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_in_set(self, widget, is_metric, valid_set):
        assert(isinstance(valid_set,tuple) or isinstance(valid_set,list))
        txt = widget.get_text()
        if not txt in valid_set:
            msg = 'Entry error\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        cparse.clr_alarm(widget)
        return True,txt,''

    def validate_any_num_not_zero(self, widget, is_metric):
        (is_valid_number, any_num) = cparse.is_number_or_expression(widget)
        if is_valid_number and any_num != 0.:
            cparse.clr_alarm(widget)
            return True, any_num, ''
        elif not is_valid_number:
            msg = 'Invalid number\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg
        else:
            msg = 'Number may not be zero\n'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def validate_comment(self, widget, dummy):
        return True, widget.get_text(), ''

    def val_empty_range_float(self, widget, is_metric, rng):
        if not any(widget.get_text()): return True, 0.0, ''
        return self.validate_range_float(widget, is_metric, rng)

    def std_validate_dro(self, widget, specific_validate, fmt, pre_msg, next_dro=None, params=None):
        if params is not None:
            valid, value, error_msg = (getattr(self,specific_validate))(widget,False, params)
        else:
            valid, value, error_msg = (getattr(self,specific_validate))(widget,False)
        if not valid:
            self.ui.error_handler.write(pre_msg + error_msg, ALARM_LEVEL_LOW)
            widget.select_region(0, -1)
            return valid
        if fmt is None: fmt = self.get_dro_format()
        widget.set_text(fmt % value)
        if next_dro is not None: next_dro.grab_focus()
        return valid

    def std_validate_param(self, widget, specific_validate, pre_msg, params=None):
        if params is not None:
            valid, value, error_msg = (getattr(self,specific_validate))(widget,False, params)
        else:
            valid, value, error_msg = (getattr(self,specific_validate))(widget,False)
        if not valid: self.error_handler.write(pre_msg + error_msg, ALARM_LEVEL_LOW)
        return (valid, value, error_msg)

#---------------------------------------------------------------------------------------------------
# Job Assignement
#---------------------------------------------------------------------------------------------------
    @staticmethod
    def ja_toggle_buttons(button_list,state='off'):
        for button in button_list:
            button.set_visible(state != 'off')
#           button.hide_all() if state is 'off' else button.show_all()

    # _ja_load_dro is called from 'ja_edit_general', this
    # takes the current value and keeps a copy in 'was'
    # so it can be reverted when editing is done.
    def _ja_load_dro(self, map_obj,is_metric):
        dro = map_obj['ref']
        was_value = None
        if isinstance(dro,str):
            if 'liststore' in dro:
                to_list = dro + '_to_list'
                if hasattr(self.ui,to_list):
                    liststore_to_list = getattr(self.ui,to_list)
                    was_value = liststore_to_list()
                list_to = 'list_to_' + dro
                if hasattr(self.ui,list_to):
                    list_to_liststore = getattr(self.ui,list_to)
                    list_to_liststore(map_obj['mod'])
        elif isinstance(dro,gtk.Entry):
            was_value = dro.get_text()
            modified_value = map_obj['mod']
            modified_value = '' if modified_value is None else modified_value
            dro.set_text(modified_value)
        elif callable(dro):
            was_value = dro()
            modified_value = map_obj['mod']
            modified_value = '' if modified_value is None else modified_value
            dro(modified_value)
        was = { 'was' : was_value }
        map_obj.update(was)
        return

    def _ja_load_dro_no_was(self, map_obj,is_metric):
        dro = map_obj['ref']
        if isinstance(dro,str):
            if 'liststore' in dro:
                list_to = 'list_to_' + dro
                if hasattr(self.ui,list_to):
                    list_to_liststore = getattr(self.ui,list_to)
                    list_to_liststore(map_obj['mod'])
        elif isinstance(dro,gtk.Entry):
            modified_value = map_obj['mod']
            modified_value = '' if modified_value is None else modified_value
            dro.set_text(modified_value)
        elif callable(dro):
            modified_value = map_obj['mod']
            modified_value = '' if modified_value is None else modified_value
            dro(modified_value)

    def _ja_swap(self,map_obj, source, dest, is_metric):
        dro = map_obj['ref']
        if isinstance(dro,str) and 'liststore' in dro:
            map_obj[dest] = copy.deepcopy(map_obj[source])
        else:
            map_obj[dest] = map_obj[source]

    def _ja_orig_to_mod(self, map_obj,is_metric):
        self._ja_swap(map_obj, 'orig', 'mod', is_metric)

    def _ja_mod_to_orig(self, map_obj,is_metric):
        self._ja_swap(map_obj, 'mod', 'orig', is_metric)

    def _ja_restore_dro_value(self, map_obj, is_metric):
        try:
            dro = map_obj['ref']
            if isinstance(dro,str):
                if 'liststore' in dro:
                    list_to = 'list_to_' + dro
                    if hasattr(self.ui,list_to):
                        list_to_liststore = getattr(self.ui,list_to)
                        list_to_liststore(map_obj['was'])
            elif isinstance(dro,gtk.Entry):
                modified_value = map_obj['was']
                dro.set_text(modified_value)
            elif callable(dro):
                modified_value = map_obj['was']
                dro(modified_value)
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('_ja_restore_dro_value: not finding \'was\' value.  Traceback: %s' % traceback_txt)

    # _ja_loop is a general looper which
    # applies a proc to each data member
    def _ja_loop(self, routine_data, proc):
        dro_map = routine_data['segment data']
        is_metric = dro_map['Units']['orig'] == 'mm'
        proc = getattr(self, proc)

        for key in dro_map:
            if key == 'focus':
                continue
            try:
                inner_obj = dro_map[key]
                if isinstance(inner_obj,dict):
                    proc(inner_obj, is_metric)
                elif isinstance(inner_obj,tuple):
                    for inner_inner_obj in inner_obj:
                        proc(inner_inner_obj, is_metric)
            except Exception:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.error_handler.log('_ja_loop: exception on loading %s.  Traceback: %s' % (key, traceback_txt))

    @staticmethod
    def _diff_and_update(item, update, deepcopy=False):
        diff = item['orig'] != item['mod']
        if diff and update:
            item['orig'] = copy.deepcopy(item['mod']) if deepcopy else item['mod']
        return diff


    def ja_difference(self, routine_data, update=False):
        dro_map = routine_data['segment data']
        ret_val = False
        for key in dro_map:
            try:
                inner_obj = dro_map[key]
                if isinstance(inner_obj,dict):
                    if inner_obj.has_key('ja_diff') and \
                       inner_obj['ja_diff'] == 'no':
                        continue
                    dro = inner_obj['ref']
                    if isinstance(dro,str):
                        if key == 'title' or key == 'Tool Description':
                            continue
                        elif key == 'Units':
                            continue
                        elif key in conversational_base.style_types: # ['Style','Thread Direction']
                            inner_obj['mod'] = getattr(self.ui,dro)()
                            ret_val = conversational_base._diff_and_update(inner_obj,update) or ret_val
                            continue
                        elif 'liststore' in dro:
                            to_list = dro + '_to_list'
                            if hasattr(self.ui,to_list):
                                liststore_to_list = getattr(self.ui,to_list)
                                inner_obj['mod'] = liststore_to_list()
                                ret_val = conversational_base._diff_and_update(inner_obj,update,True) or ret_val
                            continue
                        raise Exception('ja_difference - invalid DRO object')
                    elif isinstance(dro,gtk.Entry):
                        if not dro.get_sensitive() or not dro.get_visible():
                            continue
                        inner_obj['mod'] = dro.get_text()
                        ret_val = conversational_base._diff_and_update(inner_obj,update) or ret_val
                    elif callable(dro):
                        inner_obj['mod'] = dro()
                        ret_val = conversational_base._diff_and_update(inner_obj,update) or ret_val
                elif isinstance(inner_obj,tuple):
                    for inner_inner_obj in inner_obj:
                        if inner_inner_obj.has_key('ja_diff') and \
                           inner_inner_obj['ja_diff'] == 'no':
                            break
                        dro = inner_inner_obj['ref']
                        if isinstance(dro,str):
                            raise Exception('ja_difference - invalid DRO object')
                        inner_inner_obj['mod'] = dro.get_text()
                        ret_val = conversational_base._diff_and_update(inner_inner_obj,update) or ret_val
            except Exception:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.error_handler.log('ja_difference: exception on loading %s.  Traceback: %s' % (key, traceback_txt))

        routine_data['changed'] = ret_val
        return ret_val

    def ja_gen_update_gcode(self, routine_data, o_to_m=False):
        # if this key exitst ui state variables need to set correctly
        # then restored after the gcode is generated.
        # such variables are things like 'rect / citc' 'drill  tap', 'internal external', etc
        segment_data = routine_data['segment data']
        revert_data = None if not segment_data.has_key('revert') else segment_data['revert']
        if revert_data is not None:
            for n,item in enumerate(revert_data):
                if item.has_key('attr'):
                    ui_state = getattr(self.ui, item['attr'])
                    item['orig'] = ui_state
                    setattr(self.ui, item['attr'],item['ref'])

        # copy all the 'orig' data to 'mod' if called
        # to revert...
        if o_to_m:
            self._ja_loop(routine_data, '_ja_orig_to_mod')
        self._ja_loop(routine_data, '_ja_load_dro')
        page_id = routine_data['segment conv'][0]
        if routine_data['segment data'].has_key('pre_gen'): routine_data['segment data']['pre_gen']['proc'](routine_data)
        valid, new_gcode = self.ui.generate_gcode(page_id)

        # copy all the 'was' data to the DROs
        self._ja_loop(routine_data, '_ja_restore_dro_value')

        # put the ui back in the state it was found at the
        # start of this method
        if revert_data is not None:
            for n,item in enumerate(revert_data):
                if item.has_key('attr'):
                    ui_state = getattr(self.ui, item['attr'])
                    setattr(self.ui, item['attr'],item['orig'])
        return (valid, new_gcode)

    def ja_gen_revert_gcode(self, routine_data):
        if not routine_data['changed']:
            return (False, None)
        routine_data['changed'] = False
        return self.ja_gen_update_gcode(routine_data, True)

    def ja_gen_make_orig_gcode(self, routine_data):
        if not routine_data['changed']:
            return False
        routine_data['changed'] = False
        self._ja_loop(routine_data, '_ja_mod_to_orig')
        return True

    def ja_edit_general(self, routine_data):
        self._ja_loop(routine_data, '_ja_load_dro')
        try:
            focus_item = routine_data['segment data']['focus']
            dro = focus_item['ref']
            dro.grab_focus()
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            # just let it fail if the keys aren't there...
            self.error_handler.log('ja_edit_general: focus key nor found, or DRO invalid.  Traceback: %s' % traceback_txt)

        return None

    def ja_revert_to_was(self, routine_data):
        self._ja_loop(routine_data, '_ja_restore_dro_value')

    def parse_non_conversational_gcode(self, tool_type, conv_decomp, gcode):
        START, \
        GOTO_M30, \
        FINISH = range(0,3)
        routine_data = None
        data_wrapper = None
        ret_val = None
        good_gcode = False
        state = START
        tool_match = tool_type.lower()
        text = ''

        # scan the file for the first
        # sign of a lathe tool call
        # no longer requiring a tool call in the gcode or
        # whatever gets imbedded in the conversational file...
#       for line in gcode:
#           tool_call = ConvDecompiler._is_tool_line(line)
#           if tool_call == tool_match:
#               good_gcode = True
#               break
#       if not good_gcode:
#           return ret_val

        for line in gcode:
            if line.startswith('%'):
                continue

            if state is GOTO_M30:
                if 'M30' in line:
                    if data_wrapper is not None:
                        data_wrapper['segment text'] += text
                        data_wrapper = conv_decomp._close_data_wrapper(True, data_wrapper,'(End ExternalCode)')
                    state = FINISH
                elif conversational_base.m1_text in line:
                    if data_wrapper is None: continue
                    data_wrapper['segment text'] += text
                    data_wrapper = conv_decomp._close_data_wrapper(True, data_wrapper,'(End ExternalCode)')
                else:
                    text += line
                continue

            elif state is START:
                if data_wrapper is None:
                    data_wrapper = conv_decomp._new_non_conv_data_wrapper(conv_decomp.ncfile.filename(), tool_type)
                    text += line
                    state = GOTO_M30
                continue

            elif state is FINISH:
                continue

        if state is GOTO_M30: #no M30 in the code
            data_wrapper['segment text'] += text
            conv_decomp._close_data_wrapper(True, data_wrapper,'(End ExternalCode)')

    def tool_radius_adjustment(self, tool_number, segment_tool_data, metric):
        # LCNC internally stores diameter info as a radius
        # at the 'pocket' level it stores it as a diameter
        # this puts it in the correct terms based on the
        # tool orientation isf that is present
        tool_diameter = self.ui.get_tool_diameter(tool_number)*self.ui.get_linear_scale()
        _round_to = 3 if self.ui.g21 else 4
        if self.ui.machine_type == MACHINE_TYPE_LATHE:
            self.ui.status.poll()
            tool_orientation = self.ui.status.tool_table[int(tool_number)].orientation
#           print '**------------>Tool Orientation ',tool_orientation
            segment_tool_data['tool_orientation'] = str(tool_orientation)
            if tool_orientation != 7:
                tool_diameter = round(tool_diameter/2.0, _round_to)
        elif self.ui.machine_type == MACHINE_TYPE_MILL:
            tool_diameter = round(tool_diameter,_round_to)
        segment_tool_data['tool_rd'] = str(tool_diameter)


    def gen_external_code_dict(self):
        # ui is a base class attribute
        external_code_data = { 'title'              : ({ 'proc': 'unpack_title', 'ref':'(OD Turn',                      'orig' : None , 'mod' : None }),
                             'Description'          : ({ 'proc': 'unpack_cmt',   'ref':None,                            'orig' : None , 'mod' : None })
                             }
        return external_code_data.copy()

    def reparse_parse_tool_updates_gcode(self, gcode, data_wrapper):
        current_tool_data = None
        data_wrapper['tool data'] = []
        for line in gcode:
            #blow off comment lines...
            if line.startswith('(') or line.startswith(';'): continue

            # check if it's a new routine...
            tool_type = ConvDecompiler._is_tool_line(line)
            if tool_type:
                tool = ConvDecompiler.tool_number_line.findall(line)
                if any(tool):
                    try:
                        tool_number = ConvDecompiler.tool_number_stripper(tool_type, tool[0])
                        description = self.ui.get_tool_description(tool_number)
                        tool_diameter = self.ui.get_tool_diameter(tool_number)
                        current_tool_data = copy.deepcopy(ConvDecompiler.tool_data)
                        data_wrapper['tool data'].append(current_tool_data)
                        current_tool_data['tool_number'] = tool_number
                        current_tool_data['tool_description'] = description if description else '<none>'
                        self.tool_radius_adjustment(tool_number, current_tool_data, data_wrapper['metric'])
                    except Exception:
                        traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                        self.error_handler.log('exception: conversational.reparse_parse_tool_updatesgcode.  Traceback: %s' % traceback_txt)

                continue
            xz = ConvDecompiler.z_move.findall(line)
            if any(xz) and current_tool_data:
                for move in xz:
                    number = float(move.strip('Z '))
                    current_tool_data['min_z'] = min(number, current_tool_data['min_z'])



####################################################################################################
# ConvDecompiler
# instances are initied with the actual file. This is parsed on open and divided up into
# routines...
####################################################################################################

class ConvDecompiler(object):

    fastscan_limit = 32768
    conversational_segment = 'conversational_segment'
    outside_code_segment = 'outside_code_segment'
    cv_marker = re.compile(r'\(<cv\d+[\.\d]*>\)')
    tool_number_line = re.compile(r'T\s*[0-9]{1,4}', re.IGNORECASE)
    mill_tool_line = re.compile(r'T\s*[0-9]{1,3}', re.IGNORECASE)
    lathe_tool_line = re.compile(r'T\s?[0-9]{4}', re.IGNORECASE)
    lathe_diameter_line = re.compile(r'G0?7', re.IGNORECASE)
    mill_height_line = re.compile(r'H\s*[0-9]{1,3}', re.IGNORECASE)
    g_movement_line = re.compile(r'^G(00|01|2|3|5\.1)', re.IGNORECASE)
    xyza_move = re.compile(r'[XYZA]\s?([-+]?\d*\.\d+|\d+)', re.IGNORECASE)
    real_number = re.compile(r'[-+]?\d*\.\d+|\d+')
    tool_number = re.compile(r'\d{1,3}[^\.\d]?')
    z_move = re.compile(r'Z\s?([-+]?\d*\.\d+|\d+)', re.IGNORECASE)
    tool_call_line = re.compile(r'(T\s*?\d{4})|(T\s*?\d{1,3}\s*?M\s*?\d{1,2}\s*?G43\s*?H\s*?\d{1,3})',re.IGNORECASE)
    tool_pattern = re.compile(r'(T\s*?\d{4})|(T\s*?\d{1,3})')
    tool_orientations = 0
    tool_data = dict( tool_number = '0', tool_description = '', tool_rd = '', tool_orientation = '', min_z = 100000.0, min_x = 100000.0, tool_time = 0.0 )
    tool_data_recorded = dict( tool_number = '', tool_description = '', tool_rd = '', tool_orientation = '')
    preview_data = dict( path = '', comment = '')
    _NOT_IN_GCODE, _IN_GCODE = range(2)


    def __init__(self, conv, path, eh, action='parse'):
        self.conversational = conv
        self.path = os.path.dirname(path) if action == 'parse' else ''
        self.error_handler = eh
        self.segments = []
        self.preview_data = copy.deepcopy(ConvDecompiler.preview_data)
        self._current_tool_data = None
        self.line_count = 0
        self.ncfile = None
        self.removed = False
        self.state = ''
        self._tool_type = None

        if action == 'parse' or action == 'fastscan':
            try:
                with open(path) as gcode_file:
                    # the goal here is to just try to figure out if the file that got selected
                    # is editable as a conversational gcode file or not.
                    # this is a quick hack because clicking on a 1M line, 35 MB g-code file
                    # took forever for the above 'parse' logic to run.
                    gcode_list = gcode_file.read(ConvDecompiler.fastscan_limit) if action == 'fastscan' else gcode_file.readlines()
                    if action == 'fastscan': gcode_list = gcode_list.split('\n')
                    self.preview_data['path'] = path
                    self.ncfile = nc_file(os.path.split(path)[1])
                    self._parse(gcode_list)
                    if not any(self.segments):
                        try:
                            proc_name = self.conversational.routine_names['parsing']['CAM']
                            non_conv_parse_proc = getattr(self.conversational, proc_name)
                            non_conv_parse_proc(self, gcode_list)

                        except Exception:
                            ex = sys.exc_info()
                            self.error_handler.log("Exception during gcode parsing to detect conversational attributes: %s" % ex[1].message)
                            self.error_handler.log("".join(traceback.format_exception(*ex)))

            except Exception:
                ex = sys.exc_info()
                self.error_handler.log("Exception during gcode parsing: %s" % ex[1].message)
                self.error_handler.log("".join(traceback.format_exception(*ex)))

        elif action == 'parse list':
            self._parse(path)

        elif action == '-copy':
            self.ncfile = nc_file(None)

    @staticmethod
    def tool_number_stripper(tool_type, tool_num):
        if tool_num.startswith('T'): tool_num = tool_num[1:]
        tool_num = tool_num.strip()
        tool_num = tool_num if tool_type == 'mill' else tool_num[0:2]
        if tool_num[0] == '0':
            tool_num = tool_num[1:]
        return tool_num

    @property
    def empty(self):
        return not any(self.segments)

    @classmethod
    def copy(cls, other):
        ret_val = None
        if isinstance(other, ConvDecompiler):
            assert(bool(other.ncfile))
            other_full_path = other.path + os.path.sep + str(other.ncfile)
            ret_val = ConvDecompiler(other.conversational, other_full_path, other.error_handler, '-copy')
            ret_val.ncfile.ce_copy(other.ncfile)
            for segment in other.segments:
                seg_copy = ret_val.copy(segment)
                seg_copy['parent'] = ret_val
                ret_val.segments.append(seg_copy)
        elif isinstance(other, dict):
            ret_val = {}
            for key,value in other.iteritems():
                if isinstance(value,dict):
                    ret_val.update({key:ConvDecompiler.copy(value)})
                elif isinstance(value, tuple):
                    temp_list = []
                    for item in value:
                        temp_list.append(cls.copy(item))
                    new_item = {key:tuple(temp_list)}
                    ret_val.update(new_item)
                else:
                    if key == 'copy':
                        value = True
                    elif key == 'segment uuid':
                        value = str(uuid.uuid1())
                    new_item = {key:value}
                    ret_val.update(new_item)
        return ret_val

    @classmethod
    def unpack_font(cls, data_map, line):
        tmp = line.strip('\n')
        tmp = tmp.strip('\r')
        tmp = tmp.strip('()')
        pat = ' = '
        data_pos = tmp.find(pat)
        if data_pos < 0:
            print 'Error in unpacking font file name'
            return
        data_pos += len(pat)
        # Map the old odd Bebas font name over to the new one so that you could still load and
        # conversatonally edit existing files.
        data_map['orig'] = data_map['mod'] = string.replace(tmp[data_pos:], "BEBAS___.ttf", "Bebas.ttf")

    @classmethod
    def unpack_tool_descrip(cls, data_map, line):
        return

    @classmethod
    def unpack_title(cls, data_map, line):
        return

    @classmethod
    def unpack_units(cls, data_map, line):
        possible_choices = data_map['ref']
        data_range = len(possible_choices)
        for n in range(data_range):
            if line.find(possible_choices[n]) > 0:
                data_map['orig'] = data_map['mod'] = possible_choices[n]
                break

    @classmethod
    def unpack_wo(cls, data_map, line):
        # in this version of the work offset regex, the G is not optional
        success = False  # assume failure
        wo_re = re.compile(r'G(\d+\.?\d?) *(?:P(\d+))?', re.IGNORECASE)
        matches = wo_re.findall(line)
        if len(matches) == 1:
            value = int(float(matches[0][0]) * 10)  # Should be 540, 550, 593
            if 540 <= value <= 593:
                if value == 541:
                    # extended work offset, must have p word with valid value
                    if len(matches[0]) == 2 and len(matches[0][1]) > 0:
                        # validate extended work offset parameter
                        value2 = int(matches[0][1])
                        if 1 <= value2 <= 500:
                            success = True  # valid extended work offset parameter
                            work_offset = 'G{:s} P{:s}'.format(matches[0][0], matches[0][1])
                else:
                    # not using ext work offsets so make sure they didn't add a P word
                    if len(matches[0]) == 2 and len(matches[0][1]) == 0:
                        # and make sure the work offset is an integer (except for 591 592 or 593)
                        if value in (591, 592, 593) or (value % 10 == 0):
                            success = True
                            work_offset = 'G{:s}'.format(matches[0][0])

        if success:
            data_map['orig'] = data_map['mod'] = work_offset
        else:
            raise Exception('Invalid work coordinate system')


    @classmethod
    def unpack_str(cls, data_map, line):
        str_pos = line.find('=')
        if str_pos < 0:
            raise Exception('unpack_str: string data not parsable')
        test_str = line[str_pos+1:]
        data_map['orig'] = data_map['mod'] = test_str.strip()

    @classmethod
    def unpack_clean_str(cls, data_map, line):
        str_pos = line.find('=')
        if str_pos < 0:
            raise Exception('unpack_clean_str: string data not parsable')
        test_str = line[str_pos+1:]
        test_str = test_str.replace(')','')
        data_map['orig'] = data_map['mod'] = test_str.strip()

    @classmethod
    def unpack_stl(cls, data_map, line):
        cls.unpack_cmt(data_map, line)

    @classmethod
    def unpack_cmt(cls, data_map, line):
        str_pos = line.find('=')
        end_comment = line.find(')')
        if str_pos < 0:
            raise Exception('unpack_cmt: string data not parsable')
        if end_comment < 0:
            raise Exception('unpack_cmt: string data not a gcode comment')
        test_str = line[str_pos+2:end_comment]
        data_map['orig'] = data_map['mod'] = test_str

    @classmethod
    def unpack_to(cls, data_map, line):
        fps = re.findall(r'\d+', line)
        if len(fps) > 1:
            raise Exception('too many tool orientations found')
        data_map['orig'] = data_map['mod'] = fps[0]

    @classmethod
    def unpack_fp(cls, data_map, line):
        fps = re.findall(r'[-+]?\d*\.\d+|\d+', line)
        data_map_size = len(data_map)
        if isinstance(data_map,dict):
            data_map['orig'] = data_map['mod'] = fps[0]
        elif isinstance(data_map,tuple):
            if data_map_size != len(fps):
                raise Exception('unpack_fp: data_map does not match floating point entries')
            for n in range(data_map_size):
                data_map[n]['orig'] = data_map[n]['mod'] = fps[n]

    @classmethod
    def unpack_fp_na(cls, data_map, line):
        fps = re.findall(r'[-+]?\d*\.\d+|\d+', line)
        if isinstance(data_map,dict):
            if any(fps):
                data_map['orig'] = data_map['mod'] = fps[0]
            elif conversational_base._NA_ not in line:
                raise Exception('unpack_tool_diam does not match floating point entries')

    @classmethod
    def unpack_tool_diam(cls, data_map, line):
        fps = re.findall(r'[-+]?\d*\.\d+|\d+', line)
        # this can raise an exception if the diameter is 'N/A'
        # in this case just let it raise...
        if not any(fps):
            if conversational_base._NA_ in line: return
            raise Exception('unpack_tool_diam does not match floating point entries')
        data_map['orig'] = data_map['mod'] = fps[0]

    @classmethod
    def _is_start_of_gcode(cls, line):
        if line.startswith('(<cv') : return True
        if line.find('Start of G-code') > 0: return True               # mill...
        if line.startswith('(-------------------------'): return True  # lathe...
        gcode = re.findall(r'^G[0-9]+', line)
        return any(gcode)

    @classmethod
    def _is_optimise_comment_line(cls,line):
        if not line.startswith(';'): return False
        if 'M9' in line or 'M8' in line: return True
        if 'M3' in line or 'M5' in line: return True
        if 'G30' in line: return True
        if cls.tool_number_line.match(line, 1): return True
        return False

    @classmethod
    def _is_marker_line(cls, line):
        marker = cls.cv_marker.findall(line)
        return any(marker)

    @classmethod
    def _is_tool_line(cls, line):
        if any(ConvDecompiler.lathe_tool_line.findall(line)):
            return 'lathe'
        if 'G43' in line and 'M6' in line:
            if any(ConvDecompiler.mill_tool_line.findall(line)) and \
               any(ConvDecompiler.mill_height_line.findall(line)):
                return 'mill'
        return None

    @classmethod
    def _is_movement_line(cls, line):
        g_movement = ConvDecompiler.g_movement_line.findall(line)
        if any(g_movement):
            return True
        movement = ConvDecompiler.xyza_move.findall(line)
        return any(movement)

    def _conversational_header_line(self, line):
        conv_type = conversational_base.routine_names['conversational']
        external_code = '(' + conv_type + ' - ExternalCode G-code generated'
        if line.startswith(external_code):
            return dict(name='ExternalCode',code_type='external')
        conv_tag = '(' if conv_type == 'Lathe' else '(' + conv_type + ' - '
        gcode_generated_pos = line.find(' G-code generated')
        if gcode_generated_pos < 0:
            gcode_generated_pos = line.find(' G-code')
        if line.startswith(conv_tag) and gcode_generated_pos > 0:
            try:
                name_line = line[len(conv_tag):gcode_generated_pos]
                return dict(name=name_line,code_type='conversational')
            except:
                pass
        return None


    def _get_routine_data_packet(self, routine_name):
        # this gets the name of an 'empty' data packet factory
        # the factory produces an empty data packet for the particular
        # routine named by 'routine_name'
        # each data packet maps conversational gcode 'tags' to DROs on a particular
        # page in the conversational notebook.
        # this will work for both mill and lathe as each one maps a different
        # data set to 'conversational_base.routine_names' after initiaization
        if routine_name is None:
            return None
        try:
            routines = conversational_base.routine_names['routines']
            conv_link = routines[routine_name]['conv']
            data_factory_name = routines[routine_name]['pack']
            data_factory_method = getattr(self.conversational, data_factory_name)
            data_glob = data_factory_method()
            return (data_glob, conv_link)
        except Exception as e:
            self.error_handler.log('exception: ConvDecompiler._get_routine_data_packet.  failed: {}'.format(str(e)))
        return None

    def _match_key(self,routine_data,line):
        if line.startswith('\n'):
            line = line[1:]
        if not line.startswith('('):
            return False
        eq_pos = line.find(' =')
        if eq_pos > 0: # must start with pos 1 or better
            try:
                # suck the key string out
                # then get the ref to the
                # proc to handle this type of data
                key_str = line[1:eq_pos]
                # normalize the string in case any extra
                # spaces
                ks_list = key_str.split()
                ks_len = len(ks_list)
                key_str = ''
                for i in range(ks_len):
                    key_str += ks_list[i]
                    if i + 1 < ks_len:
                        key_str += ' '
                if key_str not in routine_data:
                    # this is pretty kludgy:
                    # pair the key string down by one word
                    # widen the search...
                    if ks_len >= 2:
                        while ks_len >= 1:
                            last_space_pos = key_str.rfind(' ')
                            key_str = key_str[:last_space_pos]
                            ks_len -= 1
                            if key_str in routine_data:
                                break

                data_map = routine_data[key_str]
                if isinstance(data_map,dict):
                    unpack_proc = data_map['proc']
                elif isinstance(data_map,tuple):
                    unpack_proc = data_map[0]['proc']
                unpack_method = getattr(self, unpack_proc)
                unpack_method(data_map, line)
                if 'rm_key' in data_map: routine_data.pop(data_map['rm_key'], None)
                return True
            except Exception:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.error_handler.log('conversational._match_key: key not found from %s.  Traceback: %s' % (line, traceback_txt))
        return False

    def _parse_tool_description_line(self, data_wrapper, line):
        l_line = line.lower();
        if 'units' in l_line:
            data_wrapper['metric'] = 'g21' in l_line
            return
        if not line.startswith('(Tool'): return
        # This parses a description line in the conversational 'step's
        # header of tagged data.
        # E.g.: (Tool Number = 58)
        #       (Tool Description = .250 CoHSS jobber drill)
        # This method will capture the data recoded in the step when it
        # posted. This is used to compare with current tool data during
        # Conv-Edit.
        if not data_wrapper['tool data recorded']:
            data_wrapper['tool data recorded'].append(copy.deepcopy(ConvDecompiler.tool_data_recorded))
        if '=' not in line: return
        _key = 'tool_description' if 'description' in l_line\
               else 'tool_rd' if 'diameter' in l_line or 'radius' in l_line\
               else 'tool_orientation' if 'orientation' in l_line\
               else 'tool_number' if 'number' in l_line\
               else 'tool_number' if 'spot with' in l_line\
               else None
        if not _key: return
        current_tool_data = data_wrapper['tool data recorded'][len(data_wrapper['tool data recorded'])-1]
        # check to see if the current _key spot is already full. If so append a new
        # dictionary, becuase this is 'another' tool for this 'step'. Example: drilling
        # may also have a spotting tool.
        if any(current_tool_data[_key]):
            data_wrapper['tool data recorded'].append(copy.deepcopy(ConvDecompiler.tool_data_recorded))
        current_tool_data = data_wrapper['tool data recorded'][len(data_wrapper['tool data recorded'])-1]
        _line = line.split('=')[1]
        _line = _line.strip()
        _line = _line.strip('\r')
        if _line.endswith(')'): _line = _line[:-1]
        if _key == 'tool_description':
            if conversational_base._NA_ not in _line: current_tool_data[_key] = _line
        elif _key == 'tool_rd':
            _pat = ConvDecompiler.real_number.search(_line)
            if _pat and _pat.group():
                str_val = _pat.group()
#               if 'radius' in l_line: str_val = str(float(str_val)*2.0)
                current_tool_data[_key] = str_val
        elif _key == 'tool_number':
            _pat = ConvDecompiler.tool_number.search(_line)
            if _pat and _pat.group(): current_tool_data[_key] = _pat.group()
        elif _key == 'tool_orientation':
            _pat = ConvDecompiler.tool_number.search(_line)
            if _pat and _pat.group(): current_tool_data[_key] = _pat.group()
        if not current_tool_data['tool_description'] and \
           not current_tool_data['tool_rd'] and          \
           not current_tool_data['tool_number'] and      \
           not current_tool_data['tool_orientation']:
            data_wrapper['tool data recorded'].pop()

    def _parse_tool_line(self, tool_type, data_wrapper, line):
        if not data_wrapper: return
        tool = ConvDecompiler.tool_number_line.findall(line)
        if not any(tool): return
        if data_wrapper['segment parse state'] is self.__class__._NOT_IN_GCODE: return
        try:
            tool_number = ConvDecompiler.tool_number_stripper(tool_type, tool[0])
            description = self.conversational.ui.get_tool_description(tool_number)
            if self._current_tool_data is None or tool_number != self._current_tool_data['tool_number']:
                self._current_tool_data = copy.deepcopy(ConvDecompiler.tool_data)
                data_wrapper['tool data'].append(self._current_tool_data)
            self._current_tool_data['tool_number'] = tool_number
            self._current_tool_data['tool_description'] = description if description is not None else '<none>'
            self.conversational.tool_radius_adjustment(tool_number, self._current_tool_data, data_wrapper['metric'])
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('exception: ConvDecompiler._parse_tool_line.  Traceback: %s' % traceback_txt)

    def _parse_movement_line(self, line):
        xz = ConvDecompiler.z_move.findall(line)
        if not any(xz):
            return
        if self._current_tool_data is None:
            return
        try:
            for move in xz:
                number = float(move.strip('Z '))
                self._current_tool_data['min_z'] = min(number, self._current_tool_data['min_z'])
        except Exception:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.log('exception in ConvDecompiler._parse_movement_line.  Traceback: %s' % traceback_txt)


    def _new_non_conv_data_wrapper(self, name='', machine=''):
        segment_data = {'Description' : {'orig' : None , 'mod' : None }}
        segment_data['Description']['mod'] = segment_data['Description']['orig'] = name
        data_wrapper = self._new_data_wrapper(copy.deepcopy(segment_data), 'ExternalCode')
        data_wrapper['segment text'] = '(%s - ExternalCode G-code generated)\n' % machine
        data_wrapper['segment text'] += (conversational_base.conv_version_string() + '\n')
        data_wrapper['segment text'] += '(Description = %s)\n' % (name)
        data_wrapper['external code'] = True
        self._current_tool_data = copy.deepcopy(ConvDecompiler.tool_data)
        data_wrapper['tool data'].append(self._current_tool_data)
        self._current_tool_data['tool_number'] = conversational_base._NA_
        self._current_tool_data['tool_description'] = '<external gcode>'
        return data_wrapper

    def _new_data_wrapper(self, routine_data, routine_name, conv_link=None, line=''):
        data_wrapper_template = {'path': None, 'title': None, 'ext': None, 'removed': False, 'changed': False, 'copy': False, 'new_step': False,
                                 'start line':0 , 'end line':0, 'segment data' : None, 'segment type': None,
                                 'segment name': None, 'segment conv':None, 'segment text':None, 'segment uuid': None}
        self._current_tool_data = None
        data_wrapper = data_wrapper_template.copy()
        data_wrapper['path'] = self.path
        data_wrapper['title'] = self.ncfile.filename() if self.ncfile else ''
        data_wrapper['ext'] = self.ncfile.extension() if self.ncfile else ''
        data_wrapper['removed'] = False
        data_wrapper['editable'] = True
        data_wrapper['changed'] = False
        data_wrapper['copy'] = False
        data_wrapper['new_step'] = False
        data_wrapper['parent'] = self
        data_wrapper['external code'] = False
        data_wrapper['can update'] = False
        data_wrapper['start line'] = self.line_count
        data_wrapper['segment data'] = routine_data
        data_wrapper['segment type'] = ConvDecompiler.conversational_segment
        data_wrapper['segment name'] = routine_name
        data_wrapper['segment conv'] = conv_link
        data_wrapper['segment text'] = line
        data_wrapper['segment parse state'] = self.__class__._NOT_IN_GCODE
        data_wrapper['segment uuid'] = str(uuid.uuid1())
        data_wrapper['tool data'] = []
        data_wrapper['tool data recorded'] = []
        data_wrapper['metric'] = False
        return data_wrapper


    def _close_data_wrapper(self, marker_found, data_wrapper, line=None):
        def __trim_to_last_G30(_data_wrapper):
            trim_amount = 0
            for char in reversed(_data_wrapper['segment text']):
                if char != '\n' and char != '\r':
                    break
                trim_amount -= 1
            if trim_amount != 0: _data_wrapper['segment text'] = _data_wrapper['segment text'][:trim_amount]
            _data_wrapper['segment text'] += '\n'

        def __insert_end_of_gcode(_data_wrapper):
            if _data_wrapper['segment text'].rfind(conversational_base.end_of_gcode) >= 0: return
            g30_pos = _data_wrapper['segment text'].rfind('G30')
            if g30_pos < 0: return
            g30_insert_pos = min(_data_wrapper['segment text'].find('\n',g30_pos), _data_wrapper['segment text'].find('\r',g30_pos))
            if g30_insert_pos < 0:
                new_line = '' if _data_wrapper['segment text'][g30_insert_pos] == '\n' else '\n'
                _data_wrapper['segment text'] += new_line + conversational_base.end_of_gcode
                return
            limit = len(_data_wrapper['segment text'])
            while _data_wrapper['segment text'][g30_insert_pos] in '\n\r' and g30_insert_pos < limit:
                g30_insert_pos += 1
            _data_wrapper['segment text'] = _data_wrapper['segment text'][:g30_insert_pos] + conversational_base.end_of_gcode + '\n' + _data_wrapper['segment text'][g30_insert_pos:]

        #packup the old routine and copy a ref into
        # the 'segments' list. Then release the original
        # data_wrapper ref.
        if marker_found and data_wrapper is not None:
            data_wrapper['end line'] = self.line_count - 1
            if line is not None:
                data_wrapper['segment text'] += line
            __trim_to_last_G30(data_wrapper)
            __insert_end_of_gcode(data_wrapper)
            self._post_parse(data_wrapper)
            self.segments.append(data_wrapper)
            routine_name = data_wrapper['segment name']
            routines = self.conversational.routine_names['routines']
            data_wrapper['editable'] = routines[routine_name]['edit'] is not None
        return None # intentional

    def _post_parse(self, data_wrapper):
        segment_data = data_wrapper['segment data']
        try:
            map_obj = segment_data['Description']
            if map_obj['orig'] is None:
                default_comment = data_wrapper['segment name']
                map_obj['orig'] = map_obj['mod'] = default_comment
            map_obj = segment_data['Post Parse']
            proc = map_obj['proc']
            proc(data_wrapper)
        except:
            pass

    def _parse(self, gcode):
        # pylint gets confused about data_wrapper typing below and this is messy to fix the false positive so just
        # disable it for now at this block level only.
        #
        #pylint: disable=unsupported-assignment-operation

        GOTO_END, \
        GOTO_MOVEMENT, \
        START_ROUTINE, \
        START_EXTERNAL, \
        FINAL = range(5)

        self.line_count = 0
        state = GOTO_END
        routine_data = None
        data_wrapper = None
        tool_type = None
        cv_marker_found = False
        text = ''

        for line in gcode:
            self.line_count += 1
#           print 'line: {:60}    State = {}'.format(line,'GOTO_END' if state is GOTO_END else 'GOTO_MOVEMENT' if state is GOTO_MOVEMENT else 'START_ROUTINE' if state is START_ROUTINE else 'START_EXTERNAL' if state is START_EXTERNAL else 'FINAL')

            # check if it's a new routine...
            if state is GOTO_END:
                tool_type = ConvDecompiler._is_tool_line(line)
                if tool_type:
                    # the data_wrapper test goes waaay back to 6b9c36515c2c334b64e65695bc34389f7114e5d2 (11/19/2016)
                    # if data_wrapper is None: return
                    self._parse_tool_line(tool_type, data_wrapper, line)
                elif self._parse_movement_line(line):
                    pass
                elif conversational_base.m1_multi_tool_step in line:
                    # check this first!:...
                    # if an 'M1' is detected that has a multipstep pattern then just capture and
                    # continue on. This is for operations such as drilling that have other operations
                    # associated with it and use more than one tool.
                    text += line
                    continue
                elif conversational_base.end_of_gcode in line:
                    # '</cv1>' end conversational step marker will
                    # will transition to the END_STEP state.
                    if data_wrapper:
                        data_wrapper['segment parse state'] = self.__class__._NOT_IN_GCODE
                    text += line
                    continue
                elif conversational_base.end_of_step_prefix in line:
                    # '(----- End of' end conversational comment
                    # will transition to the END_STEP state.
                    text += line
                    continue
                elif conversational_base.m1_text in line:
                    # A 'normal' M1 or a '</cv1>' end conversational step marker will trigger
                    # the end of a conversational step.
                    if data_wrapper is None: continue
                    data_wrapper['segment text'] += text
                    data_wrapper = self._close_data_wrapper(cv_marker_found, data_wrapper, '')
                    continue
                elif 'M30' in line:
                    if data_wrapper is not None:
                        data_wrapper['segment text'] += text
                        data_wrapper = self._close_data_wrapper(cv_marker_found, data_wrapper, '')
                    state = FINAL
                    continue

                routine_name = self._conversational_header_line(line)
                try:
                    if routine_name is None:
                        if ConvDecompiler._is_optimise_comment_line(line) : line = line[1:]
                        text += line
                    routine_data, conv_link = (None,None) if not routine_name else self._get_routine_data_packet(routine_name['name'])
                    if routine_data is not None:
                        if data_wrapper is not None: data_wrapper['segment text'] += text
                        text = ''
                        data_wrapper = self._close_data_wrapper(cv_marker_found, data_wrapper, '')
                        data_wrapper = self._new_data_wrapper(routine_data, routine_name['name'], conv_link, line)
                        state = START_ROUTINE
                        cv_marker_found = False
                        if routine_name['code_type'] == 'external':
                            data_wrapper['external code'] = True
                            self._current_tool_data = copy.deepcopy(ConvDecompiler.tool_data)
                            data_wrapper['tool data'].append(self._current_tool_data)
                            self._current_tool_data['tool_number'] = conversational_base._NA_
                            self._current_tool_data['tool_description'] = '<external gcode>'
                            state = START_EXTERNAL
                except TypeError as te: # caused when data_wrapper is None
                    self.error_handler.log('TypeError %s found on line: %d (first line is 1)'%(str(te),self.line_count))
                except KeyError as ke:
                    self.error_handler.log('KeyError %s found creating %s - line: %d (first line is 1)'%(str(ke),routine_name,self.line_count))
                except Exception as e:
                    self.error_handler.log('Error %s found creating %s - line: %d (first line is 1)'%(str(e),routine_name,self.line_count))

            elif state is START_ROUTINE:
                self._parse_tool_description_line(data_wrapper, line)
                if ConvDecompiler._is_start_of_gcode(line):
                    state = GOTO_MOVEMENT
                    cv_marker_found = cv_marker_found or ConvDecompiler._is_marker_line(line)
                    # set the state variable in the data_wrapper
                    if data_wrapper and cv_marker_found: data_wrapper['segment parse state'] = self.__class__._IN_GCODE
                else:
                    self._match_key(routine_data, line)
                text += line

            elif state is START_EXTERNAL:
                if 'End ExternalCode' in line:
                    cv_marker_found = True
                    state = GOTO_END
                else:
                    self._match_key(routine_data, line)
                text += line

            elif state is GOTO_MOVEMENT:
                cv_marker_found = cv_marker_found or ConvDecompiler._is_marker_line(line)
                # set the state variable in the data_wrapper
                if data_wrapper and cv_marker_found: data_wrapper['segment parse state'] = self.__class__._IN_GCODE
                tool_type = ConvDecompiler._is_tool_line(line)
                if tool_type:
                    self._parse_tool_line(tool_type, data_wrapper, line)
                elif ConvDecompiler._is_movement_line(line):
                    state = GOTO_END
                if ConvDecompiler._is_optimise_comment_line(line): line = line[1:]
#               if line.startswith(';') : line = line[1:]
                text += line
    ################################################################################################
    # public methods
    ################################################################################################
    def check_update_fixup(self, segment, gcode_segment_list):
        # the data_wrapper['segment parse state'] will be in the '_IN_GCODE' if no
        # ending marker was found. If the ending marker has been detected it is on the
        # '_NOT_IN_GCODE' state.
        if segment['segment parse state'] == self.__class__._NOT_IN_GCODE: return
        # destroy the previous tool data and reparse in a very minimal
        # way to detect 'new' tool data...
        del segment['tool data'][:]
        state = ConvDecompiler._NOT_IN_GCODE
        current_tool_data = None
        for line in gcode_segment_list:
            if line.startswith('(<cv'):
                state = ConvDecompiler._IN_GCODE
                continue
            if conversational_base.end_of_gcode in line:
                state = ConvDecompiler._NOT_IN_GCODE
                continue
            line = line.strip()
            if not line: continue
            if line.startswith('('): continue
            tool_sre = ConvDecompiler.tool_call_line.search(line)
            if not tool_sre: continue
            # found a 'tool' line so if _NOT_IN_GCODE continue...
            if state is ConvDecompiler._NOT_IN_GCODE: continue
            try:
                for _tool in tool_sre.groups():
                    if not _tool: continue
                    _tools_sre = ConvDecompiler.tool_pattern.search(_tool)
                    for tool in _tools_sre.groups():
                        if tool: break
                    break
                tool_type = ConvDecompiler._is_tool_line(line)
                tool_number = ConvDecompiler.tool_number_stripper(tool_type, tool)
                description = self.conversational.ui.get_tool_description(tool_number)
                if current_tool_data is None or tool_number != current_tool_data['tool_number']:
                    current_tool_data = copy.deepcopy(ConvDecompiler.tool_data)
                    current_tool_data['tool_number'] = tool_number
                    current_tool_data['tool_description'] = description if description else '<none>'
                    segment['tool data'].append(current_tool_data)
            except Exception:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.error_handler.log('exception: ConvDecompiler._parse_tool_line.  Traceback: %s' % traceback_txt)

    def can_update(self):
        def __tool_dia_not_equal(_seg_is_metric, _mach_f_tool_dia, _seg_f_tool_dia):
            # This matches the incomming tool diameter data ('tool_data_recorded['tool_number']')
            # to the current machine units. If metric, the comparison is done with a
            # precision 1e-3(.001), if imperial 1e-4(.0001).
            # Note: raw lcnc tool diameter data is always imperial. 'tool_data['tool_rd']' is
            # converted upstream to metric in 'conversational_base.tool_radius_adjustment' - if
            # the machine is in metric units.
            if mach_in_metric:
                if _seg_is_metric: return math.fabs(_mach_f_tool_dia-_seg_f_tool_dia)>1e-3
                return math.fabs(_mach_f_tool_dia-_seg_f_tool_dia*25.4)>1e-3
            else:
                if _seg_is_metric: return math.fabs(_mach_f_tool_dia-_seg_f_tool_dia/25.4)>1e-4
                return math.fabs(_mach_f_tool_dia-_seg_f_tool_dia)>1e-4
            return False
        # loop the segments see if any are still in the '_IN_GCODE' state
        # older conversational gcode won't have the '(</cv1>)' delimeter.
        mach_in_metric = self.conversational.conv_data_common(self, report='metric')
        rval = False
        for seg in self.segments:
            # if this is an older gcode file the 'segment parse state' will be in '_IN_GCODE'
            # becuase a closing tag hasn't been found
            seg['can update'] = seg['segment parse state'] == ConvDecompiler._IN_GCODE
            # 'tool_data'           : the info in the current tool table
            # 'tool_data_recorded'  : the tool info recorded in the conversational segment when it was created.
            # tool info in 'tool_data' and 'tool_data_recorded' may not be in 'sync' so
            # from the first entry in 'tool_data' find the entry with the same tool
            # number in 'tool_data_recorded'.
            # a difference in tool dimension (radius or diameter) -or- a difference
            # in tool description will cause this to return True (meaning Can Update).
            # this is a hint to job assignment to effect it's update policy.
            for tool_data in seg['tool data']:
                for tool_data_recorded in seg['tool data recorded']:
                    if tool_data['tool_number'] != tool_data_recorded['tool_number']: continue
                    try:
                        _str = tool_data['tool_rd']
                        _fl_tool_dim = float(_str) if _str else 0.0
                        _str = tool_data_recorded['tool_rd']
                        _fl_tool_rec_dim = float(_str) if _str else 0.0
                        adjusted_recorded_tool_description = self.conversational.ui.tool_descript_conversion(seg['metric'], tool_data_recorded['tool_description'])
                    except ValueError:
                        self.error_handler.log('exception: ConvDecompiler.can_update. Could not convert %s to float' % (_str if isinstance(_str,str) else '??'))
                        seg['can update'] = True
                    seg['can update'] = seg['can update'] or __tool_dia_not_equal(seg['metric'], _fl_tool_dim, _fl_tool_rec_dim)
                    seg['can update'] = seg['can update'] or not self.conversational.ui.compare_tool_description(tool_data['tool_description'], adjusted_recorded_tool_description)
                    seg['can update'] = seg['can update'] or tool_data['tool_orientation'] != tool_data_recorded['tool_orientation']
                    rval = rval or seg['can update']
                    break
        return rval

####################################################################################################
# cparse - common routines for parsing DRO text
#
####################################################################################################
class cparse:
# code for supporting math in DROs from Stackoverflow question/answer
# http://stackoverflow.com/questions/13055884/parsing-math-expression-in-python-and-solving-to-find-an-answer
# http://stackoverflow.com/users/748858/mgilson
    @staticmethod
    def _parse(x):
        operators = set('+-*/')
        op_out = []    #This holds the operators that are found in the string (left to right)
        num_out = []   #this holds the non-operators that are found in the string (left to right)
        buff = []
        # if first char is '+' or '-', stuff '0' into `buff`
        if len(x) > 0 and (x[0] == '+' or x[0] == '-'):
            buff.append('0')
        for c in x:  #examine 1 character at a time
            if c in operators:
                #found an operator.  Everything we've accumulated in `buff` is
                #a single "number". Join it together and put it in `num_out`.
                num_out.append(''.join(buff))
                buff = []
                op_out.append(c)
            else:
                #not an operator.  Just accumulate this character in buff.
                buff.append(c)
        num_out.append(''.join(buff))
        return num_out,op_out

    @staticmethod
    def _my_eval(nums,ops):

        nums = list(nums)
        ops = list(ops)
        operator_order = ('*/','+-')  #precedence from left to right.  operators at same index have same precendece.
        #map operators to functions.
        op_dict = {'*':operator.mul,
                   '/':operator.div,
                   '+':operator.add,
                   '-':operator.sub}
        Value = None
        for op in operator_order:                   #Loop over precedence levels
            while any(o in ops for o in op):        #Operator with this precedence level exists
                idx,oo = next((i,o) for i,o in enumerate(ops) if o in op) #Next operator with this precedence
                ops.pop(idx)                        #remove this operator from the operator list
                values = map(float,nums[idx:idx+2]) #here I just assume float for everything
                value = op_dict[oo](*values)
                nums[idx:idx+2] = [value]           #clear out those indices

        return nums[0]

    # return (True, float) if the passed string can be successfuly cast to float
    # and False, 0.0 if not
    @staticmethod
    def is_number(s):
        try:
            val = float(cparse._my_eval(*cparse._parse(s)))
            return (True, val)
        except ValueError:
            return (False, 0.0)

    @staticmethod
    def is_number_or_expression(item):
        # items can be strings or gtk.Entry widgets
        if isinstance(item, str):
            s = item
        else:
            try:
                s = item.get_text()
                # entry widget only has a previous val if the user has highlighted it
                # so this won't work on post to file, for instance, unless all widgets have had focus
                for prefix in ['/', '*', '+']:
                    if s.startswith(prefix):
                        s = item.prev_val + s
                        break
            except:
                pass
        try:
            val = float(cparse._my_eval(*cparse._parse(s)))
            return (True, val)
        except ValueError:
            return (False, 0.0)

    @staticmethod
    def is_int(s):
        try:
            val = int(cparse._my_eval(*cparse._parse(s)))
            return (True, val)
        except ValueError:
            return (False, 0.0)

    @staticmethod
    def is_text(s):
        if s == '':
            return (False, s)
        else:
            return (True, s)

    @staticmethod
    def raise_alarm(widget, tooltip=None):
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('yellow'))
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('red'))
        if tooltip: widget.set_tooltip_text(tooltip)

    @staticmethod
    def clr_alarm(widget):
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        widget.set_tooltip_text(None)
