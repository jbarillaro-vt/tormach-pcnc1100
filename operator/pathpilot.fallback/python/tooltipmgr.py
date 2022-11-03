# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


try:
    import wingdbstub
except ImportError:
    pass

from locsupport import *
# This is a temp definition of _ to make it visible to pylint without complaint.
# At runtime below it is deleted right away and the _ alias that the gettext module import creates takes over
def _(msgid):
    return msgid
del _

import os
import sys
import gtk
import pango
import glib
import json
import copy
import constants
import errors
import timer
import time
import cairo
import math
import re
import traceback

###################################################################################################
# factory - singleton pattern
###################################################################################################
_tool_tip_manager = None

_W = 0  # constants for handy indexing into width x height lists
_H = 1

def TTMgr():
    # Pure singleton accessor.  Since construction of a ToolTipManager requires arguments and state,
    # explicit construction and control over the timing of that is easiest to maintain.
    return _tool_tip_manager


def TTMgrInitialize(ui, window, builder_list):
    '''
    Explicit construction of ToolTipMgr singleton once the code can provide the required arguments.
        ui = TormachUIBase derived object
        window = Top level main window of the app, used for determining bounding edges for tool tip placement
        builder = Builder object used to retrieve widget using id from tooltip json file
    '''
    global _tool_tip_manager
    assert not _tool_tip_manager, "Re-init of ToolTipManager singleton"
    _tool_tip_manager = ToolTipManager(ui, window, builder_list)


###################################################################################################
# class ToolTipManager
###################################################################################################

class ToolTipManager():

    # class data
    _EMPTY,_PENDING,_INVOKE_PENDING,_LOOKUP,_SHORT,_EXPAND_PENDING,_EXPANDED = range(7)
    _invoke_timeout_ms = 1200
    _max_displaytime_sec = 30
    _main_window = None
    _builder_list = None
    _is_active = True #global switch
    _temp_activate0 = gtk.keysyms.Shift_L
    _temp_activate1 = gtk.keysyms.Shift_R


    @staticmethod
    def set_timeouts(delay_ms, max_displaytime_sec):
        ToolTipManager._invoke_timeout_ms = delay_ms
        ToolTipManager._max_displaytime_sec = max_displaytime_sec


    @staticmethod
    def get_screen_rect(widget):
        if widget is None: return gtk.gdk.Rectangle()
        rct = gtk.gdk.Rectangle()
        w_rct = gtk.gdk.Rectangle()
        while widget:
            if not (isinstance(widget,gtk.Notebook) or isinstance(widget,gtk.Fixed)):
                _r = widget.get_allocation()
                w_rct[0] += _r[0]
                w_rct[1] += _r[1]
                if not w_rct[2]: w_rct[2] = _r[2]
                if not w_rct[3]: w_rct[3] = _r[3]
            _w = widget.get_parent()
            if not _w or isinstance(_w,gtk.Window): break
            widget = _w
        window = widget.get_parent_window()
        rct[0],rct[1] = window.get_position()
        ewl = eht = ewr = ehb = 0
        if hasattr(window, 'get_frame_dimensions'): ewl,eht,ewr,ehb = window.get_frame_dimensions()
        rct[0] += ewl+w_rct[0]
        rct[1] += eht+w_rct[1]
        rct[2] = w_rct[2]
        rct[3] = w_rct[3]
        return rct

    @staticmethod
    def __prep_label(label):
        # 4 spaces and a colon at the end in some cases. The 'title'
        # method at the end puts caps on the first letters of all
        # words.
        text = label.get_text()
        if not any(text): return ''
        words = text.split()
        word_total = len(words)
        if word_total>0 and words[word_total-1] == ':':
            words.pop()
            word_total -= 1
        rt = ''
        for n,word in enumerate(words):
            rt += word
            if n<word_total: rt += ' '
        return rt.title()

    def __print(self, method_name, item=''):
        def __str_state():
            if self.state is ToolTipManager._EMPTY: return 'EMPTY'
            if self.state is ToolTipManager._PENDING: return 'PENDING'
            if self.state is ToolTipManager._INVOKE_PENDING: return '_INVOKE_PENDING'
            if self.state is ToolTipManager._LOOKUP: return '_LOOKUP'
            if self.state is ToolTipManager._SHORT: return '_SHORT'
            if self.state is ToolTipManager._EXPAND_PENDING: return '_EXPAND_PENDING'
            if self.state is ToolTipManager._EXPANDED: return '_EXPANDED'
            assert False       # alert developer in debug builds that state is corrupt/unknown
            return '?!?!?!?'

        # uncomment below to quickly debug tool tip issues
        #self.error_handler.log('ToolTipManager.{} - in {} state --  {}'.format(method_name,__str_state(), item))

    def __init__(self, ui, window, builder_list):
        '''
        Required arguments:
            ui = TormachUIBase derived object
            window = Top level main window of the app, used for determining bounding edges for tool tip placement
            builder = Builder object used to retrieve widget using id from tooltip json file
        '''
        self._active = True
        self.ui = ui
        ToolTipManager._main_window = window
        ToolTipManager._builder_list = builder_list
        self.error_handler = errors.error_handler_base()
        self.state = ToolTipManager._EMPTY
        self.popups = ToolTipManager._ttpopup(self.error_handler)
        self.curr_widget = None
        self.timer_ms = 0
        self.tooltips_data = dict()
        self.header_font = None
        self.body_font = None
        self.long_width = None
        self.bk_color = None
        self.tooltip_json_check_time = time.time()
        self.common_tooltip_json_mtime = None
        self.machine_tooltip_json_mtime = None
        # there's a common json tool tip file for all types of machines
        # and then a machine class specific file
        self.common_tooltip_filepath = os.path.join(constants.RES_DIR, 'tooltips.json')
        # if we are a mill, but running in rapidturn mode, then for the purposes of machine specific tooltips, we
        # are a lathe.
        machine_class = self.ui.machineconfig.machine_class()
        if self.ui.machineconfig.in_rapidturn_mode():
            machine_class = 'lathe'
        self.machine_tooltip_filepath = os.path.join(constants.RES_DIR, 'tooltips_{:s}.json'.format(machine_class))
        self.__load_json_file()
        self._timeprevious = time.time()
        self.max_display_stopwatch = timer.Stopwatch()

    def __reset(self):
        self.state = ToolTipManager._EMPTY
        self.popups.hide()
        self.curr_widget = None
        self.timer_ms = 0
        self.__print('__reset')

    def __place(self):
        _root_window = gtk.gdk.get_default_root_window()
        x,y,_ = _root_window.get_pointer()
        _sml,_lrg = range(2)
        _left,_top,_right,_bottom = range(4)
        _border = 5
        _tooltip_offset_extra = 16
        _side = False
        short_wh, long_wh = self.popups.get_size()
        mx, my = ToolTipManager._main_window.get_size()
        px, py = ToolTipManager._main_window.get_position()
        screen_bound_rect = (px+_border, py+_border, mx+px-_border, my+py-_border)
        screen_mid_y = screen_bound_rect[_top]+((screen_bound_rect[_bottom]-screen_bound_rect[_top])/2+1)
        # get the 'Y' value first...
        # can the tooltip go directly below?
        if y+long_wh[_H]+_tooltip_offset_extra<screen_bound_rect[_bottom]:
            sy = ly = y + _tooltip_offset_extra
        # how 'bout above?
        elif y-long_wh[_H]-_tooltip_offset_extra>screen_bound_rect[_top]:
            sy = y - short_wh[_H] - _tooltip_offset_extra
            ly = y - long_wh[_H] - _tooltip_offset_extra
        # neither - so try to the side of the mouse point..
        elif y<screen_mid_y:
            _side = True
            sy = max(y,screen_bound_rect[_top])
            ly = screen_bound_rect[_top]
        else:
            _side = True
            sy = min(y,screen_bound_rect[_bottom]-short_wh[_H])
            ly = screen_bound_rect[_bottom]-long_wh[_H]

        # determine the 'X' position...
        # try to the right...
        short_half_width = short_wh[_W]/2+1
        long_half_width = long_wh[_W]/2+1
        # try to the right of the mouse...
        if _side:
            if x+long_wh[_W]+_tooltip_offset_extra<screen_bound_rect[_right]:
                sx = x+_tooltip_offset_extra
                lx = x+_tooltip_offset_extra
            else:
                sx = x-short_wh[_W]-_tooltip_offset_extra
                lx = x-long_wh[_W]-_tooltip_offset_extra
        elif x+long_half_width<screen_bound_rect[_right]:
            sx = min(x-short_half_width, screen_bound_rect[_right]-short_wh[_W])
            lx = min(x-long_half_width, screen_bound_rect[_right]-long_wh[_W])
            sx = max(sx, screen_bound_rect[_left])
            lx = max(lx, screen_bound_rect[_left])
        elif x-long_half_width>screen_bound_rect[_left]:
            sx = max(x-short_half_width, screen_bound_rect[_left])
            lx = max(x-long_half_width, screen_bound_rect[_left])
            sx = min(sx, screen_bound_rect[_right]-short_wh[_W])
            lx = min(lx, screen_bound_rect[_right]-long_wh[_W])
        else:
            raise Exception('ToolTipManager.__place: Could not place Tooltip x: {:d} - y: {:d}'.format(int(x), int(y)))
        self.__print('__place lx: {:d}  ly {:d}'.format(int(lx), int(ly)))
        self.popups.place_short(int(sx), int(sy))
        self.popups.place_long(int(lx), int(ly))

    def __pending(self, widget):
        self.__reset()
        self.curr_widget = widget
        self.state = ToolTipManager._PENDING
        self.__print('__pending')

    def __invoke(self):
        if self.state is ToolTipManager._INVOKE_PENDING and not self.ui.program_running():
            if hasattr(self.curr_widget,'_tool_tip_name'):
                name = self.curr_widget._tool_tip_name
            else:
                name = gtk.Buildable.get_name(self.curr_widget)
                if not name:
                    # if Buildable can't get a name, this is probably a btn.ImageButton() that was created dynamically
                    # so fallback to trying to use that name.
                    name = self.curr_widget.get_name()
            tt_info = self.__lookup(name)
            if tt_info is not None:
                self.popups.set_data(tt_info)
                try:
                    self.__place()
                    self.__show_short()
                except Exception as e:
                    traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                    self.error_handler.log('ToolTipManager.__invoke: {}'.format(traceback_txt))
                    self.__reset()
        self.__print('__invoke')
        return False    # must return False or glib.idle_add() calls continue forever

    def __revoke(self):
        if self.state is not ToolTipManager._EMPTY:
            self.__reset()
        self.__print('__revoke')
        return False    # must return False or glib.idle_add() calls continue forever

    def __dynamic(self, dat, rt):
        if 'dynamic' in dat:
            procs = dat['dynamic']
            strs = []
            for proc in procs:
                ref_path = proc.split(':')
                if not any(ref_path):
                    assert False, 'ToolTipManager.__dynamic: ref_path is empty for {}'.format(rt)

                #strip out ui if there
                if ref_path[0].lower() == 'ui': ref_path = ref_path[1:]

                # start with the ui as the base reference..
                # walk the attribute path to the target object
                method = ref_path[len(ref_path)-1]
                obj_ref = self.ui
                for ref in ref_path:
                    # 'is' is correct here because it's a comparison on references
                    if ref is method:
                        method = getattr(obj_ref, method)
                        dynamic_output = method(rt)
                        if isinstance(dynamic_output, str):
                            strs.append(dynamic_output)
                        elif isinstance(dynamic_output, tuple):
                            for output in dynamic_output:
                                strs.append(output)
                        else:
                            assert False, "Unsupported object type returned from dynamic tool tip method: {}".format(str(dynamic_output))
                        break
                    obj_ref = getattr(obj_ref, ref)

            # The strings this pull from the UI widget are already localized so just use them directly.
            # Note: using 'any' on this 'iterable' with empty strings will be 'False' leaving format
            # specifiers such as '{}' in th initial string.
            if len(strs)>0:
                rt['longtext'] = rt['longtext'].format(*strs)

        self.__print('__dynamic')


    def __cook_tt_json_item(self, tooltipid, jsontt):
        self.__print('__cook_tt_json_item for {}'.format(tooltipid))

        rt = copy.deepcopy(jsontt)
        if 'shorttext_id' in rt:
            # cook the short text by looking up the localized string and using it
            rt['shorttext'] = '<span ' + self.header_font + '>' + self.get_local_string(rt['shorttext_id']) + '</span>'
        elif 'label_id' in rt:
            # pull the shorttext from the UI widget - and that text is already localized so
            # don't worry about it
            for builder in ToolTipManager._builder_list:
                label_obj = builder.get_object(jsontt['label_id'])
                if label_obj != None:
                    break
            assert label_obj, "Tooltip definition for '{}' has invalid label_id of {:s}.".format(tooltipid, jsontt['label_id'])
            label_text = ToolTipManager.__prep_label(label_obj)
            rt['shorttext'] = '<span ' + self.header_font + '>' + label_text + '</span>'
        else:
            assert False, "Tooltip definition for '{}' must have either shorttext_id or label_id.".format(tooltipid)

        # If a long text is defined for this tool tip, cook it
        if 'longtext_id' in jsontt and any(jsontt['longtext_id']):
            longtext = self.get_local_string(jsontt['longtext_id'])   # look up localized text using the id

            # Perform token replacement as necessary on the localized text, carefully using the localized shorttext
            pos = longtext.find('@@')
            if pos >= 0:
                longtext = longtext[:pos] + '<b>' + rt['shorttext'] + '</b>' + longtext[pos+2:]

            # Now add the cooked longtext to the json cooked data
            rt['longtext'] = '<span ' + self.body_font + '>' + longtext + '</span>'
            self.__dynamic(jsontt, rt)

        if 'long_width' not in rt:
            rt['long_width'] = self.long_width

        if 'bk_color' not in rt:
            rt['bk_color'] = self.bk_color

        if 'images' in rt:
            for filename in rt['images']:
                # make sure the file exists
                filepath = os.path.join(constants.GLADE_DIR, filename)
                if not os.path.exists(filepath):
                    assert False, "Tooltip definition for id {} uses image filename {} that doesn't exist!".format(tooltipid, filepath)

        return rt

    def validate_all_tooltips(self):
        # this slows down every launch and its only purpose is to alert developers via an assert
        # so only do this if assertion debug checks are enabled.
        if __debug__:
            # sanity check the data
            for tip in self.tooltips_data:
                if not self.__lookup(tip):
                    assert False, "Tooltip definition is broken for id {}".format(tip)
                self.__reset()
            self.error_handler.log("Tooltips validated successfully.")

    def __load_json_file(self):
        json_data = None

        # Tooltip json files are located in the res subdirectory ('res == localized resources')
        json_data = {}
        self.tooltips_data = {}
        if os.path.isfile(self.common_tooltip_filepath):
            with open(self.common_tooltip_filepath) as datafile:
                self.common_tooltip_json_mtime = os.stat(self.common_tooltip_filepath).st_mtime
                json_data.update(json.load(datafile))
                self.tooltips_data.update(json_data['common'])

        if os.path.isfile(self.machine_tooltip_filepath):
            with open(self.machine_tooltip_filepath) as datafile:
                self.machine_tooltip_json_mtime = os.stat(self.machine_tooltip_filepath).st_mtime
                json_data.update(json.load(datafile))
                machine_class = self.ui.machineconfig.machine_class()
                if self.ui.machineconfig.in_rapidturn_mode():
                    machine_class = 'lathe'
                self.tooltips_data.update(json_data[machine_class])

        self.header_font = json_data['std_header_font']
        self.body_font = json_data['std_body_font']
        self.long_width = json_data['std_long_width']
        self.bk_color = json_data['std_bk_color']

        self.error_handler.log('Tooltips successfully loaded.')
        return False    # must return False or glib.idle_add() calls continue forever

    def __lookup(self, id):
        self.state = ToolTipManager._LOOKUP
        self.__print('__lookup')
        if id in self.tooltips_data:
            return self.__cook_tt_json_item(id, self.tooltips_data[id])
        else:
            self.error_handler.log('ToolTipMgr.__lookup: no tooltip defined for id: {}'.format(id))
            self.__reset()
        return None

    def __show_short(self):
        self.__print('__show_short')
        self.popups.show_short()
        self.state = ToolTipManager._SHORT

    def __expand(self):
        if self.state is ToolTipManager._EXPAND_PENDING:
            self.__print('__expand')
            self.popups.show_long()
            self.state = ToolTipManager._EXPANDED
            self.timer_ms = 0
            self.max_display_stopwatch.restart()
        else:
            self.__reset()

        return False    # must return False or glib.idle_add() calls continue forever


    # 'public' methods.........................

    def get_local_string(self, str_id):
        rv = _(str_id)
        assert rv != str_id, "String id for '{}' is missing from strings resource file as we got back the same key.".format(str_id)
        return rv.replace('**', '"')

    def get_current_widget(self):
        return self.curr_widget if isinstance(self.curr_widget, gtk.Widget) else None

    def global_activate(self, activate):
        #globally turn this feature on or off
        ToolTipManager._is_active = self._active = activate

    def temporary_activate(self, kv):
        if ToolTipManager._is_active: return
        if kv != ToolTipManager._temp_activate0 and kv != ToolTipManager._temp_activate1: return
        self.activate()

    def temporary_deactivate(self, kv):
        if ToolTipManager._is_active: return
        if kv != ToolTipManager._temp_activate0 and kv != ToolTipManager._temp_activate1: return
        self.de_activate()

    def activate(self, activate=True):
        if activate and self._active: return
        self._active = activate
        self.__reset()

    def de_activate(self):
        self._active = False
        self.__reset()

    def on_esc_key(self):
        self.__reset()

    def on_mouse_enter(self, widget, event, data=None):
        self.__print('on_mouse_enter', widget._tool_tip_name if hasattr(widget, '_tool_tip_name') else gtk.Buildable.get_name(widget) if widget else 'None')
        if self._active: return self.__pending(widget)
        return True

    def on_adjustment_value_changed(self, adjustment):
        return self.__revoke()

    def on_button_press(self, widget, event, data=None):
        return self.__revoke()

    def on_button_release(self, widget, data=None):
        return self.__revoke()

    def on_mouse_leave(self, widget=None, data=None):
        self.__print('on_mouse_leave', self.curr_widget._tool_tip_name if hasattr(self.curr_widget, '_tool_tip_name') else gtk.Buildable.get_name(self.curr_widget) if self.curr_widget else 'None')
        return self.__revoke()

    def update(self, widget=None):
        # called when a DRO value gets changed
        # an updated tooltip will be generated...
        if not widget: widget = self.curr_widget
        if widget is not self.curr_widget: return
        self.__revoke()
        self.__pending(widget)
        self.timer_ms = ToolTipManager._invoke_timeout_ms

    def on_periodic_timer(self):
        # we figure out how long its been since the last call since these periodic timer calls
        # aren't always exactly at 50 ms intervals.
        timenow = time.time()
        delta_ms = int((timenow - self._timeprevious) * 1000)
        self._timeprevious = timenow

        if __debug__:
            # check at most every 2 seconds with the file system to detect a change to the tooltips file
            # this makes for a faster feedback cycle when authoring new tooltips as you don't need to constantly
            # restart PathPilot all the time to pick up the changes.
            if (timenow - self.tooltip_json_check_time) > 2.0:
                self.tooltip_json_check_time = timenow
                trigger = False
                if self.common_tooltip_json_mtime and (self.common_tooltip_json_mtime != os.stat(self.common_tooltip_filepath).st_mtime):
                    trigger = True
                if self.machine_tooltip_json_mtime and (self.machine_tooltip_json_mtime != os.stat(self.machine_tooltip_filepath).st_mtime):
                    trigger = True
                if trigger:
                    self.error_handler.log("tooltips json file(s) changed, reloading them")
                    glib.idle_add(self.__load_json_file)

        if self.state is ToolTipManager._PENDING:
            self.timer_ms += delta_ms
            self.__print('on_periodic_timer state', str(self.timer_ms))
            if self.timer_ms >= ToolTipManager._invoke_timeout_ms:
                self.state = ToolTipManager._INVOKE_PENDING
                glib.idle_add(self.__invoke)
                self.timer_ms = 0
        elif self.state is ToolTipManager._SHORT:
            self.timer_ms += delta_ms
#           self.__print('on_periodic_timer state', str(self.timer_ms))
            if self.timer_ms >= ToolTipManager._invoke_timeout_ms:
                self.state = ToolTipManager._EXPAND_PENDING
                glib.idle_add(self.__expand)
        elif self.state is ToolTipManager._EXPANDED:
            # if you haven't read the tool tip within 30 seconds, then bring it down because
            # its just annoying or covering up other screen widgets while the program is running and you
            # 'parked' the mouse somewhere where the DROs are getting covered up.
            if self.max_display_stopwatch.get_elapsed_seconds() > ToolTipManager._max_displaytime_sec:
                glib.idle_add(self.__revoke)
        else:
            self.timer_ms = 0

        return False   # must return False from glib.idle_add() or we get called again right away


    #######################################################################################################################
    class _ttpopup():
        BORDER_PIXELS = 4
        INNER_PIXELS = 2
        _std_padding = (INNER_PIXELS + BORDER_PIXELS)*2

        @staticmethod
        def _rounded_rect_path(cr, x, y, width, height, radius):
            degrees = math.pi / 180.0
            cr.arc(x + width - radius, y + radius, radius, -90 * degrees, 0 * degrees)
            cr.arc(x + width - radius, y + height - radius, radius, 0 * degrees, 90 * degrees)
            cr.arc(x + radius, y + height - radius, radius, 90 * degrees, 180 * degrees)
            cr.arc(x + radius, y + radius, radius, 180 * degrees, 270 * degrees)
            cr.close_path()

        @staticmethod
        def _create_rounded_window(window, allocation):
            if not window: return
            mask = gtk.gdk.Pixmap(None, allocation.width, allocation.height, 1)  # basically a black and white mask

            # clear the mask
            fg = gtk.gdk.Color(pixel=0)
            bg = gtk.gdk.Color(pixel=-1)
            gc = mask.new_gc(foreground=fg, background=bg)
            mask.draw_rectangle(gc, True, 0, 0, allocation.width, allocation.height)

            cr = mask.cairo_create()
            cr.set_source_rgb(0, 0, 0)
            ToolTipManager._ttpopup._rounded_rect_path(cr, 0, 0, allocation.width, allocation.height, 10.0)
            cr.fill()   # fill the rounded rect path with 1's
            window.shape_combine_mask(mask, 0, 0)

        @staticmethod
        def _draw_border(window, sz):
            if not window: return
            cr = window.cairo_create()
            cr.set_source_rgb(85/256.0, 85/256.0, 85/256.0)
            cr.set_line_width(3.0)
            ToolTipManager._ttpopup._rounded_rect_path(cr, 0, 0, sz[_W], sz[_H], 10.0)
            cr.stroke()


        # - label_fixed ----------------------------------------------------------------------------------------------------
        class label_fixed(gtk.Fixed):

            def __init__(self):
                super(ToolTipManager._ttpopup.label_fixed, self).__init__()
                # this is the size of the drawn-in dialog border for one side.
                self.label = gtk.Label('')
                self.add(self.label)
                self.label.show()
                self.show()

            def layout(self, text, bk_color):
                self.label.set_markup(text)
                layout = self.label.get_layout()
                layout.set_alignment(pango.ALIGN_LEFT)
                sz = list(layout.get_pixel_size())
                sz[_W] += ToolTipManager._ttpopup._std_padding
                sz[_H] += ToolTipManager._ttpopup._std_padding
                self.set_size_request(sz[_W], sz[_H])
                self.label.set_size_request(sz[_W], sz[_H])
                self.move(self.label, 0, 0)
                self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(bk_color))
                return sz

        # - ttshort --------------------------------------------------------------------------------------------------------
        class _ttshort(gtk.Window):
            _tag = 'short'

            def __init__(self, error_handler):
                super(ToolTipManager._ttpopup._ttshort, self).__init__(gtk.WINDOW_POPUP)
                self.error_handler = error_handler
                self.set_app_paintable(True)
                self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
                self.show()
                self.set_visible(False)

                # wrap each short tooltip label inside an event box so we can capture mouse actions over the label
                # this is needed because comboboxes are tied into the tooltipmgr such that a fake mouse-enter event is driven
                # to the tooltipmgr for the combobox from inside the standard gtk query-tooltip signal.
                # but then there is no way to easily 'dismiss' the resulting tooltip and it can be really annoying.
                # this lets the tooltip window itself figure out that it can self dismiss
                eb = gtk.EventBox()
                eb.set_visible_window(False)
                eb.connect("enter-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("leave-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("motion-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("button-release-event", lambda widget, event: TTMgr().on_button_release(widget, event))
                self.label_fixed = ToolTipManager._ttpopup.label_fixed()
                eb.add(self.label_fixed)
                self.add(eb)
                self.data = None
                self.connect("size-allocate", self._on_size_allocate)
                self.connect("expose-event", self._on_expose_event)

            def _on_expose_event(self, widget, event):
                ToolTipManager._ttpopup._draw_border(self.window, self.get_size())

            def _on_size_allocate(self, widget, allocation):
                ToolTipManager._ttpopup._create_rounded_window(self.window, allocation)

            def set_info(self, info):
                self.data = info

            def _layout(self):
                return self.label_fixed.layout(self.data['shorttext'], self.data['bk_color'])

            def pack(self):
                wh = self._layout()
                self.resize(wh[_W], wh[_H])
                self.label_fixed.set_visible(True)

            def size(self):
                return self.get_size()


        # - _ttlong ---------------------------------------------------------------------------------------------------------
        class _ttlong(gtk.Window):
            _tag = 'long'

            def __init__(self, error_handler):
                super(ToolTipManager._ttpopup._ttlong, self).__init__(gtk.WINDOW_POPUP)
                # this is the size of the drawn-in dialog border for one side.
                self.error_handler = error_handler
                self.set_app_paintable(True)
                self.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
                self.set_gravity(gtk.gdk.GRAVITY_NORTH)
                self.width = self.height = 0
                self.show()
                self.fixed = gtk.Fixed()
                self.add(self.fixed)
                self.cells = None
                self.data = None
                self.y_offset = 0
                self.set_visible(False)
                self.connect("size-allocate", self._on_size_allocate)
                self.connect("expose-event", self._on_expose_event)

            def __purge(self):
                self.y_offset = 0
                if self.cells is not None: self.cells.purge()
                fixed_children = self.fixed.get_children()
                for child in fixed_children: self.fixed.remove(child)

            def __center_in_fixed(self, cell):
                # wrap each cell inside an event box so we can capture mouse actions over the cell
                # this is needed because comboboxes are tied into the tooltipmgr such that a fake mouse-enter event is driven
                # to the tooltipmgr for the combobox from inside the standard gtk query-tooltip signal.
                # but then there is no way to easily 'dismiss' the resulting tooltip and it can be really annoying.
                # this lets the tooltip window itself figure out that it can self dismiss
                eb = gtk.EventBox()
                eb.set_visible_window(False)
                eb.connect("enter-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("leave-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("motion-notify-event", lambda widget, event: TTMgr().on_mouse_leave(widget, event))
                eb.connect("button-release-event", lambda widget, event: TTMgr().on_button_release(widget, event))
                eb.add(cell._item)
                self.fixed.add(eb)
                self.fixed.move(eb, int((self.width-cell._width)/2), int(self.y_offset))
                self.y_offset += cell._height


            def __img_fixup(self):
                if not self.data: return
                if 'images' not in self.data: return
                # if 'longtext' is new style then return...
                img_pos = self.data['longtext'].find('<img>')
                if img_pos>=0: return
                # this will create a 'new'style longtext if images are
                # present  by prepending the longtext with <img>1</img> if one image
                # <img>1,2</img> - if two images, etc.
                img_count = len(self.data['images'])
                img_str = ''
                for n in range(img_count):
                    img_str += str(n+1)
                    if n+1<img_count: img_str += ','
                self.data['longtext'] = '<img>'+img_str+'</img>'+self.data['longtext']

            def __new_cell(self, item):
                if not self.cells: self.cells = ToolTipManager._ttpopup._ttlong._ttcells(self, self.data['bk_color'])
                ToolTipManager._ttpopup._ttlong._ttcells._ttcell(self.cells, item, self.error_handler)

            def __parse_data(self):
                def __find_img(text, start=0):
                    _open, _close = range(2)
                    img_toks = ('<img>','</img>')
                    img_pos = text.find(img_toks[_open])
                    if img_pos<0: return None
                    img_end_pos = text.find(img_toks[_close],img_pos+len(img_toks[_open]))
                    if img_end_pos<0:
                        raise SyntaxError('from position {:d}:losing </img> not found'.format(img_pos))
                    image_nums = text[img_pos+len(img_toks[_open]):img_end_pos].split(',')
                    if not image_nums: return None
                    image_list = []
                    num_images = len(self.data['images'])
                    for image_num in image_nums:
                        try:
                            n = int(image_num)
                            if n<=num_images: image_list.append(self.data['images'][n-1])
                        except ValueError:
                            del image_list[:]
                            image_list.append('TT.image-error.png')
                            self.error_handler.log('ToolTipManager._ttpopup._ttlong.__parse_data - image index incorrect: {}'.format(image_num))
                            break
                    if not image_list: return None
                    return (img_pos,img_end_pos+len(img_toks[_close]), image_list)
                    # end __find_img.............................................
                self.__img_fixup()
                if not self.data: return
                text = self.data['longtext']
                text_pos = text_accum_pos = 0
                text_length = len(text)
                _img_pos_start,_img_pos_end, _img_name = range(3)
                try:
                    for n in range(100):
                        if text_accum_pos >= text_length: break
                        im = __find_img(text)
                        if not im:
                            self.__new_cell(text)
                            break
                        if im[_img_pos_start]>0: self.__new_cell(text[:im[_img_pos_start]])
                        self.__new_cell(im[_img_name])
                        text_pos = im[_img_pos_end]
                        text_accum_pos += text_pos
                        text = text[text_pos:]
                except Exception as e:
                    traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                    self.error_handler.log('ToolTipManager._ttpopup._ttlong.__parse_data: {}'.format(traceback_txt))

            #---------------------------------------------------------------------------------------
            # 'handler' methods
            #---------------------------------------------------------------------------------------
            def _on_expose_event(self, widget, event):
                ToolTipManager._ttpopup._draw_border(self.window, self.get_size())

            def _on_size_allocate(self, widget, allocation):
                ToolTipManager._ttpopup._create_rounded_window(self.window, allocation)

            #---------------------------------------------------------------------------------------
            # 'public' methods
            #---------------------------------------------------------------------------------------
            def set_info(self, info):
                self.data = info

            def pack(self):
                self.__purge()
                self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(self.data['bk_color']))
                self.fixed.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(self.data['bk_color']))
                _uplabel = ToolTipManager._ttpopup.label_fixed()
                self.width, self.height = _uplabel.layout(self.data['shorttext'], self.data['bk_color'])
                self.__new_cell(_uplabel)
                self.__parse_data()
                self.height = self.cells.pack()
                self.width = max(self.cells._width, self.width)
                self.width += (ToolTipManager._ttpopup.INNER_PIXELS + ToolTipManager._ttpopup.BORDER_PIXELS)*2
                self.fixed.set_size_request(self.width-20,self.height-20)
                self.resize(self.width, self.height)
                for cell in self.cells: self.__center_in_fixed(cell)

            def size(self):
                return (self.width,self.height)
            #---------------------------------------------------------------------------------------
            # _ttcells - a collection of vertically stacked '_ttcell' objects that house either text or images.
            #---------------------------------------------------------------------------------------
            class _ttcells(list):
                __mu_pattern = re.compile(r'^<.+?>')

                def __init__(self, ttlong, bk_color):
                    super(ToolTipManager._ttpopup._ttlong._ttcells, self).__init__()
                    self.ttlong = ttlong
                    self.bk_color = bk_color
                    self.__markup_stack = list()
                    self.__width = self.ttlong.data['long_width']
                    self._last_height = 0

                @property
                def _width(self):
                    return self.__width
                @_width.setter
                def _width(self, width):
                    self.__width = width

                def purge(self):
                    del self[:]
                    del self.__markup_stack[:]

                def pack(self):
                    height = 0
                    for cell in self:
                        if self.__width > cell._width: cell._repack(self.__width)
                        height += cell._height
                    return height

                def markup_fix(self, text):
                    # prepend the text with any markup items
                    # on the stack. These are closed markup items
                    # from the last text cell...
                    num_items = len(self.__markup_stack)
                    while num_items>0:
                        num_items -= 1
                        text = self.__markup_stack.pop() + text
                    tl = len(text)
                    ind = 0
                    while ind < tl:
                        incr = 1
                        test = text[ind:]
                        mk_items = ToolTipManager._ttpopup._ttlong._ttcells.__mu_pattern.findall(test)
                        if any(mk_items):
                            item = mk_items[0]
                            if item[1] == '/':
                                self.__markup_stack.pop()
                            else:
                                self.__markup_stack.append(item)
                            incr = len(item)
                        ind += incr
                    # close out the open markup tags for this
                    # text block
                    num_items = len(self.__markup_stack)
                    while num_items>0:
                        num_items -= 1
                        item = self.__markup_stack[num_items]
                        first_item = item.split()[0][1:]
                        closing_item = '</'+first_item+'>'
                        text += closing_item
                    return text


                #---------------------------------------------------------------------------------------
                # _ttcell - a 'cell' object that hold a 'row' of either text or images.
                #---------------------------------------------------------------------------------------
                class _ttcell:

                    def __init__(self, container, items, error_handler, bk_color=None):
                        self.container = container
                        self.error_handler = error_handler
                        self.__item = None
                        self.__data = None
                        self.__width = 0
                        self.__height = 0
                        self.__bk_color = bk_color if bk_color is not None else self.container.bk_color
                        self.__padding = ToolTipManager._ttpopup._std_padding
                        if isinstance(items, ToolTipManager._ttpopup.label_fixed):
                            # item is the header label...
                            self.__width, self.__height = items.get_size_request()
                            self.__item = items
                        elif isinstance(items,list):
                            # item is a list of images...
                            self.__height = 0
                            self.__item = gtk.Fixed()
                            self.__data = list()
                            for im in items:
                                fname = os.path.join(constants.GLADE_DIR,im)
                                try:
                                    image = gtk.Image()
                                    image.set_from_file(fname)
                                    image.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(self.__bk_color))
                                    # Note: an exception will get raised on the
                                    # next line if the image or file was bogus
                                    self.__width += image.get_pixbuf().get_width()
                                    self.__height = max(image.get_pixbuf().get_height(), self.__height)
                                    self.__data.append(image)
                                except:
                                    self.error_handler.log('ToolTipManager._ttpopup._ttcells._ttcell.__init__ - file not found: {}'.format(im))
                            start_x = 0
                            #lay out images
                            for im in self.__data:
                                self.__item.put(im, start_x, 0)
                                start_x += im.get_pixbuf().get_width()
                                im.set_visible(True)
                        else:
                            # the item is a markup string...
                            try:
                                self.__width = self.container._width
                                items = self.container.markup_fix(items)
                                lbl = gtk.Label()
                                lbl.set_size_request(self.__width-self.__padding, 2000)
                                lbl.set_markup(items)
                                lbl.set_line_wrap(True)
                                layout = lbl.get_layout()
                                layout.set_alignment(pango.ALIGN_LEFT)
                                te = layout.get_pixel_size()
                                # if images are spec'd to be the first cell after the title
                                # there can be text but it is all markup control text and
                                # hence will have a pixel width of zero. In this case
                                # height is set to zero.
                                self.__height = te[_H] + int(self.__padding/2) if te[_W] > 0 else 0
                                lbl.set_size_request(self.__width-self.__padding, self.__height)
                                self.__item = lbl
                                self.__item.set_size_request(self.__width, self.__height)
                            except:
                                self.error_handler.log('ToolTipManager._ttpopup._ttcells._ttcell.__init__ - error in markup string: {}'.format(items))
                        self.__item.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(self.__bk_color))
                        self.container._width = max(self.container._width, self.__width)
                        self.container.append(self)

                    def _repack(self, width):
                        # this is called during a pack operation in case the overall
                        # width has been increased by images.
                        if width == self.__width: return
                        if not isinstance(self.__item, gtk.Label): return
                        self.__width = width
                        _w, _h = self.__item.get_size_request()
                        self.__item.set_size_request(width-self.__padding, 2000)
                        layout = self.__item.get_layout()
                        layout.set_alignment(pango.ALIGN_LEFT)
                        te = layout.get_pixel_size()
                        self.__height = te[_H] + self.__padding
                        self.__item.set_size_request(self.__width-self.__padding, self.__height)

                    @property
                    def _width(self):
                        return self.__width
                    @_width.setter
                    def _width(self, width):
                        self.__width = width

                    @property
                    def _height(self):
                        return self.__height
                    @_height.setter
                    def _height(self, height):
                        self.__height = height

                    @property
                    def _item(self):
                        return self.__item


        # - _ttpopup--------------------------------------------------------------------------------------------------------
        # public methods ...
        #-------------------------------------------------------------------------------------------------------------------

        def __init__(self, error_handler):
            self.error_handler = error_handler
            self.ttshort = ToolTipManager._ttpopup._ttshort(error_handler)
            self.ttlong = ToolTipManager._ttpopup._ttlong(error_handler)

        def set_data(self, data):
            self.ttshort.set_info(data)
            self.ttlong.set_info(data)
            self.ttshort.pack()
            self.ttlong.pack()

        def place_short(self, x, y):
            self.ttshort.move(x, y)

        def place_long(self, x, y):
            self.ttlong.move(x, y)

        def show_short(self):
            self.ttlong.set_visible(False)
            self.ttshort.show_all()

        def show_long(self):
            self.ttshort.set_visible(False)
            self.ttlong.show_all()

        def get_size(self):
            return (self.ttshort.size(), self.ttlong.size())

        def hide(self):
            self.ttshort.set_visible(False)
            self.ttlong.set_visible(False)

###################################################################################################
# class TT_TreeView
###################################################################################################

class TT_TreeView(gtk.TreeView):

    __v_offset = 20

    def __init__(self, lst_store, scroller, ui, tt_column=0, static_name=''):
        super(TT_TreeView, self).__init__(lst_store)
        self.ui = ui
        self.scroll_window = scroller
        self.connect('enter-notify-event', self.__on_mouse_enter)
        self.connect('leave-notify-event', self.__on_mouse_leave)
        self.row_width = 0
        self.row_x = 0
        self.scroll_value = 0.0
        self.cell_height = 0.0
        self.curr_path = None
        self.tt_column = tt_column
        self.static_name = static_name
        self.__motion_id_handler = None
        self.scroll_window.add(self)

    def __cell_height(self):
        if self.cell_height > 0.0: return self.cell_height
        cell_dimensions = self.get_column(1).cell_get_size()
        cell_renderers = self.get_column(1).get_cell_renderers()
        self.cell_height = float(cell_dimensions[4])
        ypad = cell_renderers[0].get_property('ypad')
        self.cell_height += ypad
        return self.cell_height

    def __on_mouse_enter(self, widget, event, data=None):
        self.__motion_id_handler = widget.connect('motion-notify-event', self.__on_mouse_move)

    def __on_mouse_leave(self, widget, event, data=None):
        if self.__motion_id_handler is not None: widget.disconnect(self.__motion_id_handler)
        self.__motion_id_handler = None
        self.curr_path = None
#       print 'TT_TreeView.__on_mouse_leave'
        TTMgr().on_mouse_leave()

    def __on_mouse_move(self, widget, event, data=None):
        _tree_xy = self.convert_widget_to_tree_coords(int(event.x), int(event.y))
        _path = self.get_path_at_pos(int(event.x),int(event.y))
#       print 'path ---> ',_path, ' tree_x,y', _tree_xy[0], '  ,', _tree_xy[1]
#       row = int(_tree_xy[_H]/self.__cell_height())
#       print 'TT_TreeView.__on_mouse_move event.x: {:d} event.y: {:d} -- event.x_root: {:d} event.y_root: {:d}'.format(int(event.x), int(event.y), int(event.x_root), int(event.y_root))
        if _path == self.curr_path: return
        self.curr_path = _path
        TTMgr().on_mouse_leave()
        if not _path: return
        row = _path[0][0]
#       sub_row = _path[0][len(_path[0])-1]
#       print 'mouse-leave'
        # setup the iterface items for
        # the ToolTipManager queries...
        model = self.get_model()
        _tt_str_index =   self.static_name if  self.static_name else model[row][self.tt_column]
        _tt_str_index += '_tooltip'
        setattr(widget, '_tool_tip_rect', gtk.gdk.Rectangle(self.row_x, int(event.y_root), self.row_width, 25))
        setattr(widget, '_tool_tip_path', _path[0])
        setattr(widget, '_tool_tip_name', _tt_str_index)
        TTMgr().on_mouse_enter(self, event)
#       print 'active_codes_display.__on_mouse_move  _y {:.1f}   event.y_root {:.1f}'.format(_y, event.y_root)

    def get_allocation(self):
        # override 'get_allocation' so ToolTipManager can get a source
        # rectangle for tooltip placement...
        rct = super(TT_TreeView, self).get_allocation()
        rct[3] = self.__cell_height()
        rct[1] += self.curr_path[0]*self.cell_height
        adjustment = self.scroll_window.get_vadjustment()
        scroll_value = min(max(adjustment.get_lower(),adjustment.get_value()),adjustment.get_upper())
        rct[1] -= int(scroll_value)
#       print 'TT_TreeView.get_allocation - cell-height: {:.2f}'.format(float(self.__cell_height()))
        return rct

