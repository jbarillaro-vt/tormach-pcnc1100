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
import redis
import gc
import linuxcnc
import hal
import gtk, glib
import math
import glob
import errors
import errno
from constants import *
import ppglobals
import datetime
import subprocess
import signal
import collections
import shutil
import psutil
import resource
import pyudev
import pyudev.glib
from distutils import dir_util
import zipfile
import tempfile
import pango
import re
import gcode
import time
import locale
import stat
import string
import ui_support
import gtksourceview2
import tormach_file_util
import btn
import popupdlg
import conversational
import settings_backup
import job_assignment
import versioning
import numpad
import json
import copy
import gobject
import inspect
import fsclipboard
import fsutil
import sms
import timer
import swupdate
import debugpage
import plexiglass
import singletons
import memory
import gremlin_options
import thread
import threading
import stats
import tooltipmgr
import mill_fs
import lathe_fs
import ui_misc
import csv
import video


###################################################################################################
# global 'functions'
###################################################################################################

def isequal(x, y, tolerance=1e-8): return abs(x - y) < tolerance

def iszero(x): return math.fabs(float(x)) < 1e-8

def is_tuple_equal(x, y, tolerance=1e-8):
    assert len(x) == len(y), "Tuples are not same length"
    for ix in xrange(len(x)):
        if not isequal(x[ix], y[ix], tolerance):
            return False
    return True

def _add_tuple_to_dict(d, t):
    if len(t) == 2:
        if t[0]:
            d[t[0]] = t[1]

# code common to lathe, mill, etc.

def get_notebook_page_id(notebook, pagenum):
    # Careful will robinson.  Many gtk object have multiple get_name() methods.
    # One from the gtk.Buildable interface and one from the gtk.Widget inheiratance.
    # We have to use the gtk.Buildable one.
    # This will return the value of the id="" attribute that is used in the glade file.
    #
    #         <object class="GtkFixed" id="notebook_main_fixed">
    #            <property name="visible">True</property>
    #            <property name="can_focus">False</property>
    #
    # In the above example it returns "notebook_main_fixed".
    # If you just call childwidget.get_name(), then you end up getting the type string
    # which isn't very helpful.
    childwidget = notebook.get_nth_page(pagenum)
    return gtk.Buildable.get_name(childwidget)

def get_current_notebook_page_id(notebook):
    pagenum = notebook.get_current_page()
    return get_notebook_page_id(notebook, pagenum)

def set_current_notebook_page_by_id(notebook, page_id):
    for ix in range(notebook.get_n_pages()):
        if get_notebook_page_id(notebook, ix) == page_id:
            # found the index for it
            notebook.set_current_page(ix)
            break

def get_notebook_page_by_id(notebook, page_id):
    for ix in range(notebook.get_n_pages()):
        if get_notebook_page_id(notebook, ix) == page_id:
            return notebook.get_nth_page(ix)


def make_gtk_customizations():
    # this covers all the sliders, overrides and jog speed
    # override sliders get changed dynamically when console is present
    rc_string = 'style "large-slider" { GtkRange::slider-width = 35 GtkScale::slider-length = 45 bg[NORMAL] = "#808080" bg[PRELIGHT] = "#808080" } class "GtkHScale" style "large-slider"'
    gtk.rc_parse_string(rc_string)


def sort_file_history(store, remove_path, protect_path):
    for row in store:
        iter_path = store.get_path(row.iter)
        # get rid of duplicates (or files that have been deleted from internal drive)
        if row[1] == remove_path or row[1] == '' or row[1] == CLEAR_CURRENT_PROGRAM or not os.path.exists(row[1]):
            # don't remove currently loaded program gcode file path even if the file doesn't exist on disk anymore
            if row[1] != protect_path:
                store.remove(row.iter)

        # don't allow a file history longer than 6 files
        elif iter_path[0] >= 6:
            store.remove(row.iter)

    store.append([CLEAR_CURRENT_PROGRAM, CLEAR_CURRENT_PROGRAM])

def widget_in_alarm_state(widget):
    if widget.get_style().base[gtk.STATE_NORMAL] == gtk.gdk.Color('red'):
        return True
    else:
        return False

def set_packet_read_timeout(inifile):
    # only for configurations using hm2_eth
    # reduce hm2_BOARD.0.packet-read-timeout to 50% from default 80%
    hm2drivername = inifile.find("HOSTMOT2", "DRIVER")
    if hm2drivername != None and hm2drivername.startswith('hm2_eth'):
        hm2boardname = inifile.find("HOSTMOT2", "BOARD")
        if hm2boardname:
            # halcmd setp hm2_[HOSTMOT2](BOARD).0.packet-read-timeout 50
            param_cmd = 'setp'
            param_name = 'hm2_' + hm2boardname + '.0.packet-read-timeout'
            param_val = '50'
            if subprocess.call(['halcmd', param_cmd, param_name, param_val]):
                print 'Warning: failure running halcmd %s %s %s' % (param_cmd, param_name, param_val)


def clear_hostmot2_board_io_error(inifile):
    # only for configurations using hm2_eth
    # set property hm2_BOARD.0.io_error to 0
    hm2drivername = inifile.find("HOSTMOT2", "DRIVER")
    if hm2drivername != None and hm2drivername.startswith('hm2_eth'):
        hm2boardname = inifile.find("HOSTMOT2", "BOARD")
        if hm2boardname:
            # halcmd setp hm2_[HOSTMOT2](BOARD).0.io_error 0
            param_cmd = 'setp'
            param_name = 'hm2_' + hm2boardname + '.0.io_error'
            param_val = '0'
            if subprocess.call(['halcmd', param_cmd, param_name, param_val]):
                print 'Warning: failure running halcmd %s %s %s' % (param_cmd, param_name, param_val)


 ####################################################################################################
 # active_codes_display - class for the Gcode list on the Settings page
 #
 ####################################################################################################

class active_codes_display():

    def __init__(self, ui):
        # create the scroll window first...
        self.ui = ui
        self.sw = gtk.ScrolledWindow()
        self.sw.set_size_request(400, 380)
        self.sw.set_policy(gtk.POLICY_NEVER, gtk.POLICY_ALWAYS)
        self.sw.set_can_focus(False)
        # create list store
        self.store = gtk.ListStore(str, str, str, str)
        for i in self.ui.__class__.G_CODES:
            self.store.append([i['Name'], i['Function'], GREY, WHITE])
        # get a 'tooltip' aware treeview...
        self.treeview = tooltipmgr.TT_TreeView(self.store, self.sw, self.ui)

        # define columns
        font = pango.FontDescription('Roboto Condensed 10')
        crt = gtk.CellRendererText()
        crt.set_property('font-desc', font)
        name_col = gtk.TreeViewColumn('', crt, text=0, foreground=2, background=3)
        self.treeview.append_column(name_col)

        crt = gtk.CellRendererText()
        crt.set_property('font-desc', font)
        func_col = gtk.TreeViewColumn('', crt, text=1, foreground=2, background=3)
        self.treeview.append_column(func_col)
        self.treeview.set_headers_visible(False)


    def highlight_active_codes(self, active_codes):
        self.store.clear()
        for ii in self.ui.__class__.G_CODES :
            self.store.append([ii['Name'], ii['Function'], GREY,WHITE])

        for ii in active_codes:
            for row in self.store:
                if ii == row[0]:
                    row[2] = BLACK
                    row[3] = ROW_HIGHLIGHT

####################################################################################################
# gcode_pattern_searcher - pattern search in loaded gcode file
#
####################################################################################################

class gcode_pattern_searcher:

    mark_color = gtk.gdk.Color('#FFFC1A') #Yellow
    test_re_type = type(re.compile('some_pattern'))

    def __init__(self, ui):
        #class objects
        self.gcode_view = ui.sourceview
        self.gcode_view_buffer = ui.gcodelisting_buffer
        self.gcode_line_count = self.gcode_view_buffer.get_line_count()
        self.gcode_view.set_mark_category_background('find', self.mark_color)
        self.find_mark = None
        self.gcode_view.connect("button-release-event", self.on_button_release_in_sourceview)
        self.clear()


    def get_line_text(self, lineno):
        start_line_iter = self.gcode_view_buffer.get_iter_at_line(lineno-1)
        end_line_iter = start_line_iter.copy()
        end_line_iter.forward_to_line_end()
        text = start_line_iter.get_visible_text(end_line_iter)
        return text

    # callbacks .....
    def on_button_release_in_sourceview(self, widget, data = None):
        self.current_line_number = self._line_at_insert_mark()
        self._clear_mark()

    # 'private' methods .....

    def _create_mark(self):
        if self.find_mark is None:
            self.find_mark = self.gcode_view_buffer.create_source_mark('find', 'find', self.gcode_view_buffer.get_iter_at_line(0))
        return

    def _next_line(self):
        # Note: line numbers are zero based...
        current_line = self.current_line_number
        if self.direction == 'forward':
            self.current_line_number += 1
            if self.current_line_number >= self.gcode_line_count:
                self.current_line_number = 0
        else:
            self.current_line_number -= 1
            if self.current_line_number <= 0:
                self.current_line_number = self.gcode_line_count - 1
        return current_line

    def _find_pattern(self):
        start_line_iter = self.gcode_view_buffer.get_iter_at_line(self.current_line_number)
        chars_in_line = start_line_iter.get_chars_in_line() - 1
        if chars_in_line <= 1:
            return False
        end_line_iter = self.gcode_view_buffer.get_iter_at_line_offset(self.current_line_number,chars_in_line)
        text = start_line_iter.get_visible_text(end_line_iter)
        if isinstance(self.current_search_object, self.test_re_type):
            return self.current_search_object.search(text) is not None
        text = start_line_iter.get_visible_text(end_line_iter).upper()
        return True if text.find(self.current_search_object) >= 0 else False

    def _find(self):
        if not self.current_search_object:
            return False
        start_line_number = self.current_line_number
        while self._find_pattern() == False:
            self._next_line()
            if start_line_number == self.current_line_number:
                self.found_line_number = None
                self._update_mark()
                return False
        self.found_line_number = self._next_line() # this returns curr line and then increments
        self._update_view()
        return True

    def _line_at_insert_mark(self):
        try:
            insert_mark = self.gcode_view_buffer.get_insert()
            line_iter = self.gcode_view_buffer.get_iter_at_mark(insert_mark)
            return line_iter.get_line()
        except:
            pass
        return self.current_line_number

    def _delete_mark(self):
        if not self.find_mark:
            return
        line_iter = self.gcode_view_buffer.get_iter_at_line(-1)
        self.gcode_view_buffer.move_mark(self.find_mark, line_iter)
        self.gcode_view_buffer.delete_mark(self.find_mark)
        self.find_mark = None

    def _clear_mark(self):
        if self.find_mark is None:
            return
        old_line = self.gcode_view_buffer.get_iter_at_mark(self.find_mark).get_line()
        start_mark = self.gcode_view_buffer.get_mark('start')
        if start_mark:
            start_iter = self.gcode_view_buffer.get_iter_at_mark(start_mark)
            start_line = start_iter.get_line()
            if start_line == old_line:
                self.gcode_view.set_mark_category_background('start', gtk.gdk.Color('#00F700')) # green
            elif old_line:
                self.gcode_view.set_mark_category_background('find', gtk.gdk.Color('#FFFFFF'))  # white
        self._delete_mark()
        return

    def _update_mark(self):
        if self.found_line_number is None:
            self._clear_mark()
            return False
        self._create_mark()
        old_line = self.gcode_view_buffer.get_iter_at_mark(self.find_mark).get_line()
        if old_line != self.found_line_number:
            line_iter = self.gcode_view_buffer.get_iter_at_line(self.found_line_number)
            self.gcode_view_buffer.move_mark(self.find_mark, line_iter)
            self.gcode_view_buffer.place_cursor(line_iter) # here so user does not have to reclick the line to set start line
        return True

    def _update_view(self):
        if self._update_mark() == False:
            return False
        line_iter = self.gcode_view_buffer.get_iter_at_line(self.found_line_number)
        self.gcode_view.scroll_to_iter(line_iter, 0, True)
        self.gcode_view.set_mark_category_background('find', self.mark_color)
        return True

    def _find_next(self):
        if self.direction != 'forward':
            self.direction = 'forward'
            self._next_line()
            self._next_line()
        return self._find()

    def _find_last(self):
        if self.direction != 'backward':
            self.direction = 'backward'
            self._next_line()
            self._next_line()
        return self._find()

    # 'public' interface to the UI...
    def clear(self):
        self.direction = 'forward'
        self.current_line_number = 0
        self.found_line_number = None
        self.line_start_iter = None
        self.line_end_iter = None
        self.current_search_object = None
        self._delete_mark()

    def on_load_gcode(self):
        self.clear()
        self.gcode_line_count = self.gcode_view_buffer.get_line_count()


    def find_last(self, event):
        if event.state & gtk.gdk.SHIFT_MASK == True:
            return self._find_last()
        return False

    def find(self, raw_command):
        command_list = raw_command.split()
        if len(command_list) > 1:
            self.current_search_object = command_list[1]
            if self.current_search_object == 'TOOL':
                self.current_search_object = re.compile('TOOL|Tool|tool|^T\s?[0-9]+|^N\s?[0-9]+\s?T\s?[0-9]+')
            elif self.current_search_object == 'SPEED':
                self.current_search_object = re.compile('SPEED|Speed|S\s?[0-9]+')
            elif self.current_search_object == 'FEED':
                self.current_search_object = re.compile('FEED|Feed|F\s?[0-9]+')
            return self._find_next()
        return False


##################################

class TormachUIBase:

    _ja_tmp_filepath = None
    _check_button_hilight_color = gtk.gdk.Color('#444444')

    def __init__(self, gladefile, ini_file_name):

        self.inifile = linuxcnc.ini(ini_file_name)

        # GTK theme customizations - larger override sliders
        make_gtk_customizations()

        plexiglass.PlexiglassInitialize(self.stop_all_jogging)

        self.builder = gtk.Builder()

        self.termination_in_progress = False

        # we don't know what type of machine we are yet
        # please stop adding machine specific behavior to this *common* base class. If its machine specific,
        # it doesn't belong here.
        self.machine_type = MACHINE_TYPE_UNDEF

        # get the contents of pathpilot.json
        with open(PATHPILOTJSON_FILEPATH, "r") as f:
            self.configdict = json.load(f)

        #Add a shortcut to the get_object function here
        self.get_obj = self.builder.get_object
        self.builder.add_from_file(gladefile)

        # redis db for persistent storage.  File location set in redis.conf, currently in config dir (rdb.dump)
        self.redis = redis.Redis()

        # slam this into redis so that other processes are on the same page.  remap code is one example
        self.redis.hset('machine_prefs', 'linuxcnc_inifilepath', ini_file_name)

        # This is just the basic one that can do structured debug logging.  Later it will get replaced
        # with one that is wired into the status tab, but has same API.
        self.error_handler = errors.error_handler_base()
        ppglobals.GUI_THREAD_ID = thread.get_ident()
        self.error_handler.write("GUI thread id is %d" % ppglobals.GUI_THREAD_ID, ALARM_LEVEL_DEBUG)

        #conv DRO font description to be used across all machine types
        self.conv_dro_font_description  = pango.FontDescription('helvetica ultra-condensed 22')

        # Active Gcodes display handler
        self.gcodes_display = active_codes_display(self)

        # Turn on gc stats output to stdout so we can tell when GC is occurring
        #gc.set_debug(gc.DEBUG_STATS)

        #-----------------------------------------------------------------
        # All of these attributes are later used by mill and/or lathe, but they are also referenced
        # by methods on TormachUIBase.  Init them here so that pylint sees them to avoid false positives
        # on the no-member checker.
        self.machineconfig = None
        self.command = None
        self.status = None
        self.hal = None
        self.maxvel_lin = 0.0
        self.maxvel_ang = 0.0
        self.checkbutton_list = {}
        self.button_list = {}
        self.image_list = {}
        self.pixbuf_dict = {}
        self.conv_dro_list = {}
        self.dro_list = {}
        self.fixed = None
        self.gremlin = None
        self.conversational = None
        self.thread_chart_g20_liststore = None
        self.thread_chart_g21_liststore = None
        self.thread_chart_combobox = None
        self.scrolled_window_tool_table = None
        self.sfm_mrr_hint = None
        self.usbio_combobox_id_to_index = {}
        self.usbio_boardid_selected = 0
        self.gremlin_options = None
        self.enc_open_door_max_rpm = None
        self.estop_alarm = False
        self.fs_mgr = None
        self.tool_liststore = None
        self.atc = None
        self.jog_increment_scaled = 0
        self.jog_image_names = ()
        self.jogging_stopped = False
        self.jog_ring_axis = self.prev_jog_ring_axis = -1
        self.prev_jog_ring_speed = 0.0
        self.jog_step_button_was_pressed = 0
        self.prev_hal_jog_counts = 0
        self.prev_console_jog_counts = 0
        self.jog_speed = 0.0
        self.spindle_fault_mask = 0x0
        self.vfd_status_by_atc = False

        self.togglefullscreen_button = None
        self.togglefullscreen_button_orig_pos = None

        self.playstop_button = None
        self.playstop_button_orig_pos = None

        self.cycle_start_led_color = 'dark'

        # axis_motor_poll message flag
        self.messageFault = {0:False, 1:False, 2: False, 3:False }
        #halt_world() flag
        self.halt_world_flag = False
        #-------------------------------------------------------------------

        # Common
        self.mdi_keypad = None
        self.gcode_file_mtime = None
        self.g21 = self.prev_g21 = False
        self.gcode_last_line = 0
        self.gcode_program_tools_used = []
        self.warn_cycle_start_with_zero_length_tools = True

        self.f_word = 0
        self.s_word = 0

        # Latched flags use for forcing redraws and other poor-man's signaling behavior based on a state change
        # NOTE: these are mostly one-to-one with the active g-codes read in gremlin's get_active_g_code_string()
        self._modal_change_redraw_flags = {
            linuxcnc.G_CODE_UNITS: LatchedFlag(),
            linuxcnc.G_CODE_PLANE: LatchedFlag(),
            linuxcnc.G_CODE_CUTTER_SIDE: LatchedFlag(),
            linuxcnc.G_CODE_LATHE_DIAMETER_MODE: LatchedFlag(),
            linuxcnc.G_CODE_RETRACT_MODE: LatchedFlag(),
            linuxcnc.G_CODE_DISTANCE_MODE: LatchedFlag(),
            linuxcnc.G_CODE_DISTANCE_MODE_IJK: LatchedFlag(),
        }

        # Common UI objects
        self.window = self.builder.get_object("main_window")
        self.notebook = self.builder.get_object("notebook")
        self.gcode_options_notebook = self.builder.get_object("gcode_options_notebook")
        self.gcode_page_fixed = self.builder.get_object("gcode_page_fixed")
        self.conv_notebook = self.builder.get_object("conversational_notebook")
        self.notebook_main_fixed = self.builder.get_object("notebook_main_fixed")
        self.notebook_file_util_fixed = self.builder.get_object("notebook_file_util_fixed")
        self.file_preview_scrolled_window = self.builder.get_object("file_preview_scrolled_window")
        self.gcode_file_preview_label = self.builder.get_object("gcode_file_preview_label")
        self.feedrate_override_label = self.builder.get_object("feedrate_override_label")
        self.spindle_override_label = self.builder.get_object("spindle_override_label")
        self.maxvel_override_label = self.builder.get_object("maxvel_override_label")
        self.mdi_line = self.builder.get_object("mdi_line")
        self.preview_image_overlay = self.builder.get_object("preview_image_overlay")
        self.loaded_gcode_filename_combobox = self.builder.get_object("loaded_gcode_combobox")
        self.loaded_gcode_filename_evtbox = self.builder.get_object("loaded_gcode_combobox_evtbox")

        self.video_fullscreen = False
        self.video_toolbar_fixed = None
        self.conv_page_dros = {}

        self.machine_ok_display = False

        # TODO - format will need to change for imperial versus metric (which is why they can't be constants)
        self.dro_medium_format = "%.1f"
        self.dro_short_format = "%.0F"
        self.dro_dwell_format = "%.2f"

        # editor is called from a wrapper script
        # this script changes the directory to ~/gcode
        # then runs the editor with an LD_PRELOAD
        # for a custom libgtk with locked down file chooser dialog
        # and execs the editor (gedit)
        self.gcode_edit_program_to_run = "editscript"

         # process object to monitor CPU utilization
        self.proc = psutil.Process(os.getpid())
        self.last_vms = 0
        self.vmslog_stopwatch = timer.Stopwatch()

        # USB enumeration events
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context)
        monitor.filter_by(subsystem='usb')
        observer = pyudev.glib.MonitorObserver(monitor)
        observer.connect('device-event', self.usb_device_event)
        monitor.start()

        # FIFO of UI button events to fake from alt-key events
        # alt-key handler writes to FIFO
        # the 50ms periodic reads the FIFO and emits the press/release events
        # it is implemented this way so the user can see the on screen button
        # bitmap shift and return to normal
        self.button_deque = collections.deque()

        # USBIO hal io and images
        self.usbio_input_image_list = ['usbio_input_0_led', 'usbio_input_1_led', 'usbio_input_2_led', 'usbio_input_3_led']
        #The USB I/O LEDs are now "LED Buttons" which are clickable event boxes, not just an image,
        #so we must track the image contained inside the event box with self.usbio_output_image_list
        self.usbio_output_image_list = ['usbio_output_0_led', 'usbio_output_1_led', 'usbio_output_2_led', 'usbio_output_3_led']
        #AND the event box itself with to manipulate showing, hiding, and refreshing
        self.usbio_output_eventbox_list = ['usbio_output_0_led_button', 'usbio_output_1_led_button', 'usbio_output_2_led_button', 'usbio_output_3_led_button']

        # grab time stamps of current custom thread files to reset update
        # of thread_combobox from 500ms ... the combobox gets filled at creation anyway
        # no matter timestamps and we don't want period 500ms to call it possibly before
        # combobox exists

        # these files are exposed to the user and they might accidentally delete them
        # or rename them.
        self.restore_thread_template_files_if_needed()
        self.thread_custom_metric_file_mtime = os.stat(THREAD_DATA_METRIC_CUSTOM).st_mtime
        self.thread_custom_sae_file_mtime = os.stat(THREAD_DATA_SAE_CUSTOM).st_mtime

        # recreate the fonts directory if the user accidentally deleted it
        if not os.path.isdir(ENGRAVING_FONTS_DIR):
            os.mkdir(ENGRAVING_FONTS_DIR)

        # recreate the release notes directory if the user accidentally deleted it
        if not os.path.isdir(RELEASE_NOTE_PDFS_PATH):
            os.mkdir(RELEASE_NOTE_PDFS_PATH)

        self.current_gcode_file_path = ''

        # elapsed time label
        self.elapsed_time_label = gtk.Entry()
        self.elapsed_time_label.set_has_frame(False)
        self.elapsed_time_label.set_editable(False)
        self.elapsed_time_label.set_can_focus(False)
        self.elapsed_time_label.set_alignment(1.0)   # right align the text
        self.elapsed_time_label.set_size_request(74, 20)
        self.elapsed_time_label.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        self.elapsed_time_label.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        font_description = pango.FontDescription('Roboto Condensed 12')
        self.elapsed_time_label.modify_font(font_description)
        self.elapsed_time_label.set_no_show_all(True)

        # remaining time label
        self.remaining_time_label = gtk.Entry()
        self.remaining_time_label.set_has_frame(False)
        self.remaining_time_label.set_editable(False)
        self.remaining_time_label.set_can_focus(False)
        self.remaining_time_label.set_alignment(1.0)   # right align the text
        self.remaining_time_label.set_size_request(74, 20)
        self.remaining_time_label.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        self.remaining_time_label.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        font_description = pango.FontDescription('Roboto Condensed 12')
        self.remaining_time_label.modify_font(font_description)
        self.remaining_time_label.set_no_show_all(True)

        self.preview_clipped_label = gtk.Entry()
        self.preview_clipped_label.set_has_frame(False)
        self.preview_clipped_label.set_editable(False)
        self.preview_clipped_label.set_can_focus(False)
        self.preview_clipped_label.set_alignment(1.0)   # right align the text
        self.preview_clipped_label.set_size_request(96, 20)
        self.preview_clipped_label.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        self.preview_clipped_label.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        font_description = pango.FontDescription('Roboto Condensed 10')
        self.preview_clipped_label.modify_font(font_description)
        self.preview_clipped_label.set_no_show_all(True)
        self.preview_clipped_label.set_text("Preview Limited")

        # message line that overlays the lower portion of the gremlin window
        self.message_line = gtk.Entry()
        self.message_line.set_has_frame(False)
        self.message_line.set_editable(False)
        self.message_line.set_can_focus(False)
        self.message_line.set_alignment(0.5)    # center the text
        # doesn't really matter as we don't know the size of the gremlin yet so
        # this will be adjusted later
        self.message_line.set_size_request(0, 35)
        self.message_line.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        self.message_line.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        message_line_font_description = pango.FontDescription('Roboto Condensed 18')
        self.message_line.modify_font(message_line_font_description)
        self.message_line.set_no_show_all(True)

        self.use_hal_gcode_timers = False

        self.job_assignment = None
        self.in_JA_edit_mode = False
        self.gremlin_reset = False
        self.tool_treeview = None
        self.current_tool = 0
        self.pn_data = None

        self.usbio_e_message = True         #don't pollute the log  with extra messages

        # init the object that in the background continuously checks internet connectivity status
        self.internet_checker = internet_checker()

        self.gcode_options_button = self.builder.get_object("gcode_options_button")
        self.expandview_button = self.builder.get_object("expandview_button")

        # used for toggling the gcode source view and mdi entry
        # controls larger/smaller using the expandview_button or by double clicking gcode window
        self.origsize_gremlin = None
        self.origpos_gremlin = None
        self.origsize_scrolled_window = None
        self.origsize_mdi_line = None
        self.origsize_loaded_gcode_filename_evtbox = None
        self.origpos_expandview_button = None
        self.origsize_preview_image_overlay = None
        self.origpos_preview_image_overlay = None

        # default gcode window size on main tab is not expanded
        if not self.redis.hexists('uistate', 'main_tab_gcodewindow_state'):
            # values are either 'Normal' or 'Expanded'
            self.redis.hset('uistate', 'main_tab_gcodewindow_state', 'Normal')

        # default to showing feeds and speeds warning
        if not self.redis.hexists('uistate', 'show_feeds_speeds_warning'):
            self.redis.hset('uistate', 'show_feeds_speeds_warning', 'True')

        # default tooltip timers
        if not self.redis.hexists('uistate', 'tooltip_delay_ms'):
            self.redis.hset('uistate', 'tooltip_delay_ms', '1200')
        if not self.redis.hexists('uistate', 'tooltip_max_display_sec'):
            self.redis.hset('uistate', 'tooltip_max_display_sec', '25')


        self.work_offset_label = self.builder.get_object("work_offset_label")
        self.prev_work_offset_name = self.current_work_offset_name = None

        # ---------------------------------------------
        # overrides sliders (gtk.scale and gtk.adjustment)
        # and associated labels
        # ---------------------------------------------

        # the 'adjustment' object(value, lower bound, upper bound, step inc, page inc, page size)
        # is pre-set in the glade file.
        # Page inc and size should be zero to prevent accidental motion
        # mouse wheel events thrown out to prevent default gtk behavior
        # key press events thrown away to prevent HOME and END from moving slider
        self.feedrate_override_adjustment = self.builder.get_object("feedrate_override_adjustment")
        self.feedrate_override_scale = self.builder.get_object("feedrate_override_scale")
        self.feedrate_override_scale.connect("key-press-event", self.throw_away_key_press_event)
        self.spindle_override_adjustment = self.builder.get_object("spindle_override_adjustment")
        self.spindle_override_scale = self.builder.get_object("spindle_override_scale")
        self.spindle_override_scale.connect("key-press-event", self.throw_away_key_press_event)
        self.maxvel_override_adjustment = self.builder.get_object("maxvel_override_adjustment")
        self.maxvel_override_scale = self.builder.get_object("maxvel_override_scale")
        self.maxvel_override_scale.connect("key-press-event", self.throw_away_key_press_event)
        self.jog_speed_adjustment = self.builder.get_object("jog_speed_adjustment")
        self.jog_speed_scale = self.builder.get_object("jog_speed_scale")
        self.jog_speed_scale.connect("key-press-event", self.throw_away_key_press_event)
        self.jog_speed_label = self.builder.get_object('jog_speed_label')
        self.active_gcodes_label = self.builder.get_object("active_gcodes_label")

        # used to manage override sliders is VMC console present
        self.console_connected = False
        self.prev_console_connected = False
        self.first_set_slider_readonly = True
        self.feedrate_override_prefix = ''
        self.spindle_override_prefix = ''
        self.maxvel_override_prefix = ''
        self.override_slider_width_normal, self.override_slider_height = self.feedrate_override_scale.size_request()
        self.feedrate_override_scale.set_name('feedrate_override_scale')
        self.spindle_override_scale.set_name('spindle_override_scale')
        self.maxvel_override_scale.set_name('maxvel_override_scale')

        self.jog_speed_scale.set_name('jog_speed_scale')

        make_gtk_customizations()

        self.set_feedrate_override(100)
        self.set_spindle_override(100)
        self.set_maxvel_override(100)

        self.m01image_pixbuf = None
        self.gremlin_load_needs_plexiglass = False
        self.maxvel_adjustment_current = -100
        self.maxvel_adjustment_newest = 100
        self.spindle_adjustment_current = -100
        self.spindle_adjustment_newest = 100
        self.feedrate_adjustment_current = -100
        self.feedrate_adjustment_newest = 100

        # Careful - the line may have an N23 line number, but note that the regex will match anywhere on the line, not just at the start
        self.m1_image_with_comment_re = re.compile(r'm0?[01]\s*\(([^)]*)\)', re.I)
        self.lineno_for_last_m1_image_attempt = 0

        self.combobox_masked = False

        # g code file history combo box
        self.file_history_liststore = gtk.ListStore(str, str)
        self.loaded_gcode_filename_combobox.set_model(self.file_history_liststore)
        cell = gtk.CellRendererText()
        self.loaded_gcode_filename_combobox.pack_start(cell, True)
        self.loaded_gcode_filename_combobox.add_attribute(cell, 'text', 0)
        try:
            for ix in range(0, self.redis.llen('recent_file_history')):
                # file history liststore is in form of ['filename', 'path'], but redis only stores the path
                path = self.redis.lindex('recent_file_history', ix)

                # don't load any files that don't exist anymore - that's just confusing to the user.
                if os.path.exists(path):
                    # don't load duplicates if they somehow got saved (self-cleaning)
                    dupe = False
                    for row in self.file_history_liststore:
                        if path == row[1]:
                            dupe = True
                            break
                    if not dupe:
                        self.file_history_liststore.append([os.path.basename(path), path])
        except:
            self.error_handler.write("Retrieval of recent file history failed.", ALARM_LEVEL_DEBUG)
            pass

        self.file_history_liststore.append([CLEAR_CURRENT_PROGRAM, CLEAR_CURRENT_PROGRAM])

        # get user's home directory
        self.home_dir = os.getenv('HOME')

        self.update_mgr = swupdate.SoftwareUpdateMgr(self.error_handler, self.redis)

        self.error_handler.log("Ini file is: {}".format(self.inifile))
        self.stats_mgr = stats.StatsMgr(self.inifile, self)

        # initialize mesa watchdog status
        self.mesa_watchdog_has_bit_seen = False

        # these counters are used to call the slower periodic functions
        self.periodic_loopcount = 0
        self.periodic_loopcount_60s = 0

        if self.redis.hexists('uistate', 'last_expiration_warning'):
            self.last_expiration_warning_sec = float(self.redis.hget('uistate', 'last_expiration_warning'))
        else:
            self.last_expiration_warning_sec = time.time()
            self.redis.hset('uistate', 'last_expiration_warning', self.last_expiration_warning_sec)

        self.disk_space_check_stopwatch = None

        self.clock_eventbox = self.builder.get_object("clock_eventbox")
        self.clock_label = self.builder.get_object("clock_label")
        self.clock_eventbox.modify_bg(gtk.STATE_ACTIVE, gtk.gdk.Color('#6A6A6A'))
        self.clock_eventbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color('#6A6A6A'))
        self.clock_visible = False

        # ---------------------------------------------------
        # MDI line (gtk.entry)
        # ---------------------------------------------------

        # global MDI history list of typed in commands
        # arrow up/down inside edit displays
        self.mdi_history = []
        self.mdi_history_index = -1
        try:
            hist_length = self.redis.llen('mdi_history')
            for ix in range(0, hist_length):
                self.mdi_history.append(self.redis.lindex('mdi_history', ix))
            self.mdi_history_index = int(self.redis.hget('machine_prefs', 'mdi_history_index'))
        except:
            self.error_handler.write("Retrieval of MDI history failed.", ALARM_LEVEL_DEBUG)
            pass
        self.mdi_history_max_entry_count = 100
        self.mdi_line_masked = 0
        mdi_font_description = pango.FontDescription('Roboto Condensed 18')
        self.mdi_line.modify_font(mdi_font_description)
        self.mdi_line.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('#C3C9CA'))

        self.ttable_conv = 1.0
        self.mach_data = {}

        # usbio module selector combobox
        self.usbio_module_liststore = gtk.ListStore(str)
        self.usbio_board_selector_combobox = self.builder.get_object("usbio_board_selector_combobox")
        self.usbio_board_selector_combobox.set_model(self.usbio_module_liststore)
        cell = gtk.CellRendererText()
        fd = pango.FontDescription('Roboto Condensed 9')
        cell.set_property('font-desc', fd)
        self.usbio_board_selector_combobox.pack_start(cell, True)
        self.usbio_board_selector_combobox.add_attribute(cell, 'text', 0)

        self.last_runtime_sec = 0

        self.debugpage = None

        self.reset_image_color = 'blue'

        # Gtk drawing area widget we use for video playback
        self.vlcwidget = None

        self.settings = None

        # -------------------------------------------------------------
        # HAL setup.  Pins/signals must be connected in POSTGUI halfile
        # -------------------------------------------------------------
        self.hal = hal.component('tormach')
        self.hal.newpin('debug-level', hal.HAL_U32, hal.HAL_OUT)

        self.setup_console_halpins()

        # -------------------------------------------------------
        # PostGUI HAL common to all machines
        # -------------------------------------------------------

        # configure the operator console (if preset)
        postgui_vmc_console_halfile = self.inifile.find("HAL", "POSTGUI_VMC_CONSOLE_HALFILE")
        if postgui_vmc_console_halfile:
            if subprocess.call(["halcmd", "-i", sys.argv[2], "-f", postgui_vmc_console_halfile]):
                self.error_handler.write("Warning: something failed running halcmd on '" + postgui_vmc_console_halfile + "'", ALARM_LEVEL_DEBUG)
        else:
            # complain about missing POSTGUI_VMC_CONSOLE_HALFILE
            self.error_handler.write("Warning: missing POSTGUI_VMC_CONSOLE_HALFILE in .INI file.", ALARM_LEVEL_DEBUG)

        # -------------------------------------------------------
        # Done with PostGUI
        # -------------------------------------------------------

        self.gcode_file_clipped_load = False
        self.suppress_active_gcode_display = True

        self.halpin_callbacks = {}

        self.default_max_glcanon_lines = gcode.max_glcanon_lines()

        # connect timer to status poll periodic function
        glib.timeout_add(50, self.periodic_status)

        self.spindlespeed_log_timer = None
        self.prev_spindle_on_pin = 0

    def setup_console_halpins(self):
        # VMC console controls
        self.hal.newpin("console-jog-counts", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("console-feedhold", hal.HAL_BIT, hal.HAL_IO)
        self.hal.newpin("console-cycle-start", hal.HAL_BIT, hal.HAL_IO)
        self.hal.newpin("console-device-connected", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("console-led-green", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("console-led-red", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("console-led-blue", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("console-led-ready", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("console-rpm-override", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("console-feed-override", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("console-rapid-override", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("console-mode-select", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("console-defeatured-mode", hal.HAL_BIT, hal.HAL_IN)

    def setup_jog_stepping_images(self):
        self.jog_image_names = ('jog_zero_image', 'jog_one_image', 'jog_two_image', 'jog_three_image')

        # Default jog step images for g20 and g21
        self.jog_step_images_g20_black = ('0001-Pressed-Black.jpg', '0010-Pressed-Black.jpg', '0100-Pressed-Black.jpg', '1000-Pressed-Black.jpg')
        self.jog_step_images_g20_green = ('0001-Pressed-Green.jpg', '0010-Pressed-Green.jpg', '0100-Pressed-Green.jpg', '1000-Pressed-Green.jpg')
        self.jog_step_images_g21_black = ('Metric-0025-Black.jpg', 'Metric-010-Black.jpg', 'Metric-100-Black.jpg', 'Metric-1.00-Black.jpg')
        self.jog_step_images_g21_green = ('Metric-0025-Green.jpg', 'Metric-010-Green.jpg', 'Metric-100-Green.jpg', 'Metric-1.00-Green.jpg')

        if self.machineconfig.jog_step_increments_g20() == (0.00025, 0.001, 0.01, 0.1):
            self.jog_step_images_g20_black = ('00025-Pressed-Black.jpg', '0010-Pressed-Black.jpg', '0100-Pressed-Black.jpg', '1000-Pressed-Black.jpg')
            self.jog_step_images_g20_green = ('00025-Pressed-Green.jpg', '0010-Pressed-Green.jpg', '0100-Pressed-Green.jpg', '1000-Pressed-Green.jpg')

        if self.machineconfig.jog_step_increments_g21() == (0.010, 0.100, 1.0, 2.0):
            self.jog_step_images_g21_black = ('Metric-010-Black.jpg', 'Metric-100-Black.jpg', 'Metric-1.00-Black.jpg', 'Metric-2.00-Black.jpg')
            self.jog_step_images_g21_green = ('Metric-010-Green.jpg', 'Metric-100-Green.jpg', 'Metric-1.00-Green.jpg', 'Metric-2.00-Green.jpg')

        self.prev_hal_jog_counts = self.hal['jog-counts']

        # now redraw the jog step buttons as they probably changed from what is in the glade file.
        self.clear_jog_LEDs()
        self.set_jog_LEDs()


    def clear_jog_LEDs(self):
        # turn all the JOG button LEDs "off"
        if self.g21:
            for ix in range(4):
                self.set_image(self.jog_image_names[ix], self.jog_step_images_g21_black[ix])
        else:
            for ix in range(4):
                self.set_image(self.jog_image_names[ix], self.jog_step_images_g20_black[ix])


    def set_jog_LEDs(self):
        ix = self.hal['jog-gui-step-index']
        if self.g21:
            self.set_image(self.jog_image_names[ix], self.jog_step_images_g21_green[ix])
        else:
            self.set_image(self.jog_image_names[ix], self.jog_step_images_g20_green[ix])


    def set_jog_mode(self, mode):
        """Wrapper function to ensure that jog mode is cleanly switched from continous to stepping.
            This prevents the jog mode from being changed in the middle of a
            move, which can lead to runaway jogging.
        """
        if self.jog_mode == mode:
            return True
        if not self.moving():
            #Ok to switch since we're not moving
            self.jog_mode = mode
            return True
        elif self.jog_mode == linuxcnc.JOG_INCREMENT:
            #Safe to switch since step mode is limited distance
            self.jog_mode = mode
            return True

        return False

    def set_keyboard_jog_mode(self, mode):
        """Wrapper function to ensure that jog mode is cleanly switched from continous to stepping.
            This prevents the jog mode from being changed in the middle of a
            move, which can lead to runaway jogging.
        """
        # keep track of keyboard mode with separate variable so we can force it in keyboard jog handler
        self.keyboard_jog_mode = mode
        if self.jog_mode == mode:
            return True
        if not self.moving():
            # button art
            if mode == linuxcnc.JOG_CONTINUOUS:
                self.set_image('jog_inc_cont_image', 'jog_cont_green.png')
            else:
                self.set_image('jog_inc_cont_image', 'jog_step_green.png')
            #Ok to switch since we're not moving
            self.jog_mode = mode
            return True
        elif self.jog_mode == linuxcnc.JOG_INCREMENT:
            #Safe to switch since step mode is limited distance
            self.jog_mode = mode
            return True

        return False

    def handle_step_jog(self):
        """Inner wheel step jogging"""
        jog_step_counts = self.hal['jog-counts']
        # if in a continuous jog do not do a step jog

        if self.jogging_stopped == False and jog_step_counts != self.prev_hal_jog_counts:
            count_delta = jog_step_counts - self.prev_hal_jog_counts

            # Choose jogging direction
            jog_dir = -1.0 if count_delta < 0 else 1.0

            if self.set_jog_mode(linuxcnc.JOG_INCREMENT):
                self.error_handler.write("Jog inner wheel: %d" % jog_dir, ALARM_LEVEL_DEBUG)
                # set UI LEDs to indicate step jog distance
                self.clear_jog_LEDs()
                self.set_jog_LEDs()
                self.jog(self.jog_ring_axis, jog_dir, self.jog_speed, apply_pct_override=False)


    def handle_ring_jog(self):
        """Jog ring handling"""
        ring_speed = self.hal['jog-ring-speed-signed']
        self.jog_ring_axis = self.hal['jog-ring-selected-axis']
        jog_ring_axis_changed = False
        if self.jog_ring_axis != self.prev_jog_ring_axis:
            self.error_handler.write("Jog ring axis: %d" % self.jog_ring_axis, ALARM_LEVEL_DEBUG)
            # NB - must ensure mode here, as it can't be handled in the stop_jog method for race condition reasons (see issue 827)
            self.ensure_mode(linuxcnc.MODE_MANUAL)
            self.stop_jog(self.prev_jog_ring_axis)
            self.prev_jog_ring_axis = self.jog_ring_axis
            jog_ring_axis_changed = True

        if self.jog_ring_axis >= 0 and (ring_speed != self.prev_jog_ring_speed or jog_ring_axis_changed):
            self.error_handler.write("Jog ring speed: %f" % ring_speed, ALARM_LEVEL_DEBUG)
            self.prev_jog_ring_speed = ring_speed

            jog_dir = -1.0 if ring_speed < 0.0 else 1.0

            # need new jog command
            # FIXME account for jog axis minimum speed here?
            if ring_speed == 0:
                self.error_handler.write("Ring jogging stopped on axis %d" % self.jog_ring_axis, ALARM_LEVEL_DEBUG)
                self.stop_jog(self.jog_ring_axis)
            else:
                self.error_handler.write("Ring jogging axis %d at speed %f" % (self.jog_ring_axis, ring_speed), ALARM_LEVEL_DEBUG)
                #Pass in extra argument to override stock jog mode
                self.set_jog_mode(linuxcnc.JOG_CONTINUOUS)
                self.jog(self.jog_ring_axis, jog_dir, abs(ring_speed), False, jog_mode = linuxcnc.JOG_CONTINUOUS)


    def handle_step_button(self):
        """step button - upon release advance or wrap to the next increment"""
        if self.hal['jog-step-button'] == 1:
            self.jog_step_button_was_pressed = 1
        elif self.hal['jog-step-button'] == 0 and self.jog_step_button_was_pressed:
            self.jog_step_button_was_pressed = 0
            if not self.set_jog_mode(linuxcnc.JOG_INCREMENT):
                #failed to change to step mode, so we can't update the increment
                return
            self.hal['jog-gui-step-index'] = (self.hal['jog-gui-step-index'] + 1) % 4
            if self.g21:
                self.jog_increment_scaled = self.machineconfig.jog_step_increments_g21()[self.hal['jog-gui-step-index']]
            else:
                self.jog_increment_scaled = self.machineconfig.jog_step_increments_g20()[self.hal['jog-gui-step-index']]
            self.clear_jog_LEDs()
            self.set_jog_LEDs()
            self.error_handler.write("Jog step size: %f" % self.jog_increment_scaled, ALARM_LEVEL_DEBUG)


    def update_jogging(self):
        """During fast update loop, handle jogging keypresses"""
        if self.program_running() or plexiglass.is_plexiglass_up():
            # ignore jogging during program run
            # but also whenever a plexiglass is up since that clearly means
            # something is happening and we don't want to be reacting to input events
            # theory is that sometimes when plexi is up, the main GUI thread dispatches
            # gtk main loop iterations while it is waiting for something else to complete and
            # you might snag a jog action just once right in a bad spot and result in
            # jogging starting that you cannot easily stop without e-stopping the machine
            pass

        else:
            # Shuttle
            # force mode switch - needs MODE_MANUAL for jogging to function
            if ((self.hal['console-jog-counts'] != self.prev_console_jog_counts) or
                (self.hal['jog-axis-x-enabled'] or self.hal['jog-axis-y-enabled']
                 or self.hal['jog-axis-z-enabled'] or self.hal['jog-axis-a-enabled']) and
                ((self.hal['jog-counts'] != self.prev_hal_jog_counts) or
                 (self.hal['jog-ring-speed-signed'] != 0.0))):
                self.ensure_mode(linuxcnc.MODE_MANUAL)

            self.handle_step_jog()

            self.handle_ring_jog()

            self.handle_step_button()

        # Always reset previous jog counts
        self.prev_hal_jog_counts = self.hal['jog-counts']
        self.prev_console_jog_counts = self.hal['console-jog-counts']


    # periodic updates to LEDs, DROs, more . . .
    def periodic_status(self):
        if not self.termination_in_progress:
            # 50 ms functions is always called
            self.status_periodic_50ms()
            # increment loop counter and call slow period function as needed
            self.periodic_loopcount += 1
            if self.periodic_loopcount >= 10:
                self.status_periodic_500ms()
                self.periodic_loopcount = 0

                self.periodic_loopcount_60s += 1
                if self.periodic_loopcount_60s >= 2:
                    self.update_clock()
                if self.periodic_loopcount_60s >= 120:
                    self.status_periodic_60s()
                    self.periodic_loopcount_60s = 0
            return True   # call us again
        else:
            return False  # cancel periodic

    @property
    def dro_long_format(self):
        """Return the python format string for DROs showing a floating point number

        Returns:
            String: Python format string which varies depending on whether the
            interface is in G21 (metric) mode or G20 (imperial)
        """
        if self.g21:
            return "%3.3f"
        else:
            return "%2.4f"

    @property
    def current_notebook_page_id(self):
        page_id = get_current_notebook_page_id(self.notebook)
        return page_id

    def get_main_notebook_page_by_id(self, page_id):
        return get_notebook_page_by_id(self.notebook, page_id)

    def gcodeoptions_switch_page(self, notebook, page, page_num):
        self.gremlin_options.refresh()


    def check_tool_table_for_warnings(self, unique_tool_list):
        '''
        Return True if warnings were issued, False otherwise
        '''
        # This will be overriden in subclasses
        return False


    def save_persistent_data(self):
        tool_num = self.status.tool_in_spindle
        self.redis.hset('machine_prefs', 'active_tool', tool_num)
        try:
            self.redis.delete('mdi_history')
            for item in self.mdi_history:
                self.redis.rpush('mdi_history', item)
                self.redis.hset('machine_prefs', 'mdi_history_index', self.mdi_history_index)
        except:
            self.error_handler.write("Failed to save MDI history.", ALARM_LEVEL_DEBUG)

        try:
            # delete old redis values to prevent this list from growing ad infinitum
            self.redis.delete('recent_file_history')
            for row in self.file_history_liststore:
                path = row[1]
                if path != CLEAR_CURRENT_PROGRAM and os.path.exists(path):
                    self.redis.rpush('recent_file_history', path)
        except:
            self.error_handler.write("Failed to save recent file history.", ALARM_LEVEL_DEBUG)

        if self.f_word != 0:
            self.redis.hset('machine_prefs', 'feedrate', str(self.f_word))
        if self.s_word != 0:
            self.redis.hset('machine_prefs', 'spindle_speed', str(self.s_word))

        # I once saw in the log the redis.save() method toss an exception
        # of redis.exceptions.ResponseError: Background save already in progress
        # RedisError is the base class of all/most of everything redis can raise
        # so use that.
        st = timer.Stopwatch()
        saved = False
        while not saved and st.get_elapsed_seconds < 10:
            try:
                self.redis.save()   #force all data out
                saved = True
            except redis.exceptions.RedisError:
                self.error_handler.log("Caught a RedisError during save attempt on exit. Waiting and trying again.")
                time.sleep(0.5)   # sigh...trying to be patient

    """
        Set up a callback to be called when the value of a HAL pin changes between calls to process_halpin_callbacks
        (usually called from the 50ms event loop)

        pinname: The name of a pin accessible through self.hal (needs to be already set up using postgui)
        callback: The function to call when the value on pinnname has changed
        initial_call: Call the callback function immediately with the current value of the halpin

        Callback signature:
            value: current value of the hal pin
    """
    def add_halpin_changed_callback(self, pinname, callback, inital_call=True):
        if pinname not in self.halpin_callbacks:
            self.halpin_callbacks[pinname] = {}
            self.halpin_callbacks[pinname]['prev_value'] = self.hal[pinname]
            self.halpin_callbacks[pinname]['callbacks'] = []

        self.halpin_callbacks[pinname]['callbacks'].append(callback)
        # Call the function an initial time
        if(inital_call):
            callback(self.hal[pinname])

    """
        Perform callbacks for any hal pins that have changed
        Should be called from the 50ms periodic loop of PP
    """
    def process_halpin_callbacks(self):
        for pinname, callback_data in self.halpin_callbacks.iteritems():
            if self.hal[pinname] != callback_data['prev_value']:
                for cb in callback_data['callbacks']:
                    cb(self.hal[pinname])
                callback_data['prev_value'] = self.hal[pinname]


    def pause_for_user_space_comps(self, comp_list):
        for comp in comp_list:
            watch = timer.Stopwatch()
            while not hal.component_exists(comp):
                if watch.get_elapsed_seconds() > 10:
                    # give up and abort
                    self.error_handler.log("Waiting for user comp {} to exist took over 10 seconds - aborting.".format(comp))
                    return False
                time.sleep(0.1)

            watch.restart()
            while not hal.component_is_ready(comp):
                if watch.get_elapsed_seconds() > 10:
                    # give up and abort
                    self.error_handler.log("Waiting for user comp {} to become ready took over 10 seconds - aborting.".format(comp))
                    return False
                time.sleep(0.1)

        return True

    def load_cs_image(self, color):
        if color == 'green' and self.cycle_start_led_color != 'green':
            self.set_image('cycle_start_image', 'Cycle-Start-Green.jpg')
            self.cycle_start_led_color = 'green'
            self.hal['console-led-green'] = True
            return
        if color == 'dark' and self.cycle_start_led_color != 'dark':
            self.set_image('cycle_start_image', 'Cycle-Start-Black.jpg')
            self.cycle_start_led_color = 'dark'
            self.hal['console-led-green'] = False
            return
        if color == 'blink':
            self.hal['console-led-green'] = not self.hal['console-led-green']
            if self.cycle_start_led_color == 'green':
                self.set_image('cycle_start_image', 'Cycle-Start-Black.jpg')
                self.cycle_start_led_color = 'dark'
                return
            else:
                self.set_image('cycle_start_image', 'Cycle-Start-Green.jpg')
                self.cycle_start_led_color = 'green'
                return

    def on_cycle_start_button(self):
        '''
        Return True if action should be aborted, False otherwise
        '''
        self.clear_message_line_text() # Always do this in case of left over crap

        abort_action = False

        if self.is_gcode_program_loaded and self.warn_cycle_start_with_zero_length_tools:
            # scan tool table
            tool_list = self.gremlin.get_tools_used()

            # the tool list is in the order the program uses them and duplicates are possible.
            # build a new list without duplicates and sort it so it easier for the user to go through the tool table.
            # we do it reverse so that the order of the warnings on the status page becomes low number tool to high number
            # as you look down the page.
            unique_tool_list = []
            for tool in tool_list:
                if tool not in unique_tool_list:
                    unique_tool_list.append(tool)
            unique_tool_list.sort(reverse=True)

            abort_action = self.check_tool_table_for_warnings(unique_tool_list)
            if abort_action:
                # Let them know they are on their own at this point.
                self.error_handler.write("Cycle Start will no longer warn about tooling parameters for this g-code file.", ALARM_LEVEL_HIGH)

            # Scan, warn, and ignore Cycle Start once per file
            self.warn_cycle_start_with_zero_length_tools = False

        return abort_action


    def composite_png_button_images(self):
        # the Reset button images are png with an alpha channel and need to be
        # composited with the fixed widget background color.
        self.load_reset_image('blink')    # blink


    def refresh_machine_ok_led(self):
        # machine ok LED
        if bool(self.hal['machine-ok']) != self.machine_ok_display:
            self.machine_ok_display = bool(self.hal['machine-ok'])
            if self.machine_ok_display:
                self.set_image('machine_ok_led', 'LED-Green.png')
            else:
                self.set_image('machine_ok_led', 'LED-Yellow.png')


    def load_reset_image(self, image_color):
        # for 'white' load white image if not already loaded
        # for 'blink': if now 'blue' load 'non-blue' else load 'blue'
        if image_color == 'white' and self.reset_image_color != 'white':
            self.set_image('reset_image', 'Reset-White.png')
            self.reset_image_color = 'white'
        elif image_color == 'blink':
            # blink between blue and non-blue
            if self.reset_image_color == 'blue':
                # load non-blue
                self.set_image('reset_image', 'Reset-White.png')
                self.reset_image_color = 'non-blue'
            else:
                # load blue
                self.set_image('reset_image', 'Reset-Blue.png')
                self.reset_image_color = 'blue'


    def add_debug_page(self):
        if not self.debugpage:
            self.debugpage = debugpage.DebugPage(self)
            label = gtk.Label()
            label.set_text("Debug")
            self.notebook.append_page(self.debugpage, tab_label=label)
            self.debugpage.show_all()


    def on_usbio_board_selector_combobox_changed(self, widget, data=None):
        comboindex = widget.get_active()
        self.usbio_boardid_selected = 0
        for id in iter(self.usbio_combobox_id_to_index):
            if self.usbio_combobox_id_to_index[id] == comboindex:
                self.usbio_boardid_selected = id
                break

        # the board selected redis state is the board ID, not the index into the comboxbox.
        self.redis.hset('uistate', 'usbio_boardid_selected', self.usbio_boardid_selected)
        self.error_handler.log("USBIO selector set to: {:d}".format(self.usbio_boardid_selected))


    def get_work_offset_name_from_index(self, ix):
        '''
        Return the name of the work offset from the status.g5x_offsets index value.
        e.g.  index 0 name is G53, index 9 name is G59.3
        '''
        assert ix >= 0 and ix <= 500
        if ix <= 6:
            # G53 to G59
            name = "G5{:d}".format(ix+3)
        elif ix <= 9:
            # G59.1 to G59.3
            name = "G59.{:d}".format(ix-6)
        else:
            name = "G54.1 P{:d}".format(ix)
        return name


    def warn_if_low_disk_space(self):
        # has it been at least 1 hour since the last space check?  (or we've never checked yet)
        if self.disk_space_check_stopwatch == None or self.disk_space_check_stopwatch.get_elapsed_seconds() > (60 * 60):
            self.disk_space_check_stopwatch = timer.Stopwatch()

            # check for a decent amount of free disk space and warn if we're low
            freebytes = tormach_file_util.get_disk_free_space_bytes(GCODE_BASE_PATH)
            self.error_handler.write("Low disk space check reveals %s of free disk space" % ui_misc.humanbytes(freebytes), ALARM_LEVEL_DEBUG)

            # warn if below 500 MB of free disk space
            if freebytes < (500 * 1024 * 1024):
                self.error_handler.write("Low disk space check reveals only %s of free disk space. Use the File tab to delete unneeded files." % ui_misc.humanbytes(freebytes), ALARM_LEVEL_LOW)


    def update_clock(self):
        # update the clock
        if self.clock_visible:
            now = datetime.datetime.now()
            locale_timeformat_str = locale.nl_langinfo(locale.T_FMT)
            self.clock_label.set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="white">{}</span>'.format(now.strftime(locale_timeformat_str)))


    def status_periodic_500ms(self):
        # Enable or disable the sliders to match the state of overrides
        if self.status.feed_override_enabled != self.feedrate_override_scale.get_sensitive():
            self.feedrate_override_scale.set_sensitive(self.status.feed_override_enabled)
        if self.status.spindle_override_enabled != self.spindle_override_scale.get_sensitive():
            self.spindle_override_scale.set_sensitive(self.status.spindle_override_enabled)

        # proxy for "does this machine have an M200 component?"
        if self.machineconfig.has_ecm1() and self.machineconfig.machine_class() == 'mill':
            self.check_spindle_fault()

        if self.machineconfig.machine_class() == 'mill' and not self.machineconfig.in_rapidturn_mode():
            # if we are stuck waiting for spindle-at-speed, start logging this if it is starting to take awhile.
            # helps diagnostics in the log analysis.
            # TODO: why not call this in rapidturn mode???
            if self.prev_spindle_on_pin != self.hal['spindle-on']:
                if self.hal['spindle-on']:
                    # start timer in case it takes awhile to reach at speed
                    self.spindlespeed_log_timer = timer.Stopwatch()
                else:
                    # spindle turned off
                    self.spindlespeed_log_timer = None

            if self.spindlespeed_log_timer:
                if self.hal['spindle-at-speed']:
                    self.spindlespeed_log_timer = None
                else:
                    # target rpm / 2800 is about how many seconds we expect it to take to reach speed
                    # 10K / 2800 = 3.57 seconds on a 770MX for example.
                    # 5K / 2800 = 1.78 seconds which seems reasonable to reduce log spam
                    #
                    # log every 500ms while we're waiting unless we just created the timer above...
                    if self.prev_spindle_on_pin == self.hal['spindle-on']:
                        expected_delay_secs = self.status.settings[2] / 2800.0
                        elapsed_secs = self.spindlespeed_log_timer.get_elapsed_seconds()
                        if elapsed_secs > expected_delay_secs:
                            # use detailed logging on m200 vfd with ecm1 and generic logging on others...
                            if self.machineconfig.has_ecm1():
                                self.error_handler.log("Waiting {:f} secs for spindle at speed: m200-vfd-rpm-feedback {:f} spindle-speed-out {:f} s word target {:f}".format(
                                    elapsed_secs,
                                    abs(self.hal['m200-vfd-rpm-feedback']),
                                    abs(self.hal['spindle-speed-out']),
                                    self.status.settings[2]))
                            else:
                                self.error_handler.log("Waiting {:f} secs for spindle at speed: spindle-speed-out {:f} s word target {:f}".format(
                                    elapsed_secs,
                                    abs(self.hal['spindle-speed-out']),
                                    self.status.settings[2]))

            self.prev_spindle_on_pin = self.hal['spindle-on']



    def check_spindle_fault(self):
        if not self.machineconfig.has_ecm1():
            return

        fault_id = self.hal['spindle-fault']
        if fault_id > 31:  #assuming "just" 32 bits in our bit mask, bits numbered 0 to 31
            bit_mask = 0x80000000; #clamp bit mask at highest bit
        else:
            bit_mask = 0x01 << fault_id

        if not (bit_mask & self.spindle_fault_mask): #if we haven't already logged (and possibly acted on) this fault
            self.spindle_fault_mask = self.spindle_fault_mask | bit_mask #flag_bit to not duplicate message in log

            if fault_id >= SPINDLE_FAULT_CRITICAL:
                self.halt_world(True) #do ASAP, not that the 500mS loop rate here is fast enough anyway. Also spits message to user

            err_msg = SPINDLE_ERR_MSGS[fault_id];

            if err_msg != None:
                if fault_id >= SPINDLE_FAULT_CRITICAL:
                    self.error_handler.write("%s" % err_msg, ALARM_LEVEL_HIGH) #but we scream to users
                else:
                    if fault_id <= SPINDLE_FAULT_LOG_ONLY: #noise user doesn't care about
                        self.error_handler.log(err_msg)
                    else:
                        self.error_handler.write("%s" % err_msg, ALARM_LEVEL_MEDIUM) #give user a yellow status tab
            else:
                self.error_handler.write("Unknown spindle fault ID %d" % fault_id, ALARM_LEVEL_MEDIUM) #but we flag up to user

        #house keep bit mask.  Clear all other past errors if spindle is OK.  Also clear all others while waiting for K2 to close,
        #which handles case of user leaving spindle door open and repeatedly trying to start spindle -- we never get to OK, yet a
        #new SPINDLE_FAULT_NO_PWR will repeat every time user tries to start spindle
        if fault_id == SPINDLE_FAULT_NO_K2 or fault_id == SPINDLE_NO_FAULT:
            self.spindle_fault_mask = bit_mask; #only leave current bit mask active


    def status_periodic_60s(self):
        # get machine state
        machine_executing_gcode = self.program_running()
        if machine_executing_gcode:
            machine_busy = True
        else:
            # moving under MDI, probing, ATC ops, jogging, etc
            machine_busy = self.moving()

        # log virtual memory growth if we blew up by more than 1 MB over the last 60 seconds.
        current_vms = self.proc.memory_info().vms
        growth_bytes = current_vms - self.last_vms
        if growth_bytes > (1024*1024):
            self.error_handler.log("Virtual memory size grew by {} in 60 sec, total vms={}".format(ui_misc.humanbytes(growth_bytes), ui_misc.humanbytes(current_vms)))
        self.last_vms = current_vms

        # log vms size and number of open file handles vs. limit every 60 minutes
        if self.vmslog_stopwatch.get_elapsed_seconds() > 60*60:
            self.error_handler.log("total vms={}  ({:,d} bytes)".format(ui_misc.humanbytes(current_vms), current_vms))

            filelist = psutil.Process().open_files()
            limit = resource.getrlimit(resource.RLIMIT_NOFILE)  # returns tuple of soft and hard limit - soft is [0]
            self.error_handler.log("total open file handles={:d} out of a limit of {:d}".format(len(filelist), limit[0]))

            self.vmslog_stopwatch.restart()

        if not machine_busy:
            # call this every once in a while when we aren't executing
            # code or moving around.
            #
            # in some cases if we have a network, but the DNS system can't resolve pathpilotapi.com
            # then this can block for a long time and it feels like the UI is locked up while trying to
            # check the servers.  rather than add additional threading/process complexity, we simply
            # only check for possible updates when we know the internet is reachable.
            if self.internet_checker.internet_reachable:
                self.update_mgr.possible_update_check()

            # check for expired build
            warning_msg = versioning.GetVersionMgr().get_expiration_warning()
            if warning_msg != None:
                # we could be running for days and cross the deadline.
                # so we can't just check on boot alone.
                if versioning.GetVersionMgr().is_build_expired():
                    # bummer.  stop the presses.
                    self.stop_motion_safely()
                    md = popupdlg.ok_cancel_popup(self.window, warning_msg, cancel=False, checkbox=False)
                    self.window.set_sensitive(False)
                    md.run()
                    md.destroy()
                    self.quit()

                else:
                    # has it been at least 3 days since the last update check?
                    now_sec = time.time()
                    timedelta_sec = now_sec - self.last_expiration_warning_sec
                    if timedelta_sec > (3 * 24 * 60 * 60):
                        # warn them when it will die.
                        self.error_handler.write(warning_msg, ALARM_LEVEL_LOW)
                        self.redis.hset('uistate', 'last_expiration_warning', now_sec)
                        self.last_expiration_warning_sec = float(self.redis.hget('uistate', 'last_expiration_warning'))

            self.warn_if_low_disk_space()


    def on_clock_eventbox_button_press_event(self, widget, event, data=None):
        tooltipmgr.TTMgr().on_button_press(widget, event, data)


    def on_clock_eventbox_button_release_event(self, widget, event, data=None):
        # if the clock is visible, treat a right click as a request to adjust the date or time.
        if self.clock_visible and event.button == 3:
            self._run_mdi_admin_program(['sudo', 'time-admin'])

        elif event.button == 1:
            # toggle the state
            if self.clock_eventbox.get_visible_window():
                self.clock_visible = False
                self.clock_label.set_markup('')
                self.clock_eventbox.set_visible_window(False)
            else:
                self.clock_visible = True
                self.update_clock()
                self.clock_eventbox.set_visible_window(True)

        # this is needed because adjust eventbox visibility above puts pending mouse enter and mouse leave events in
        # the queue - which then promptly restarts the tooltip pending state, defeating our ability to
        # suppress tool tips for things you've just clicked
        while gtk.events_pending():
            gtk.main_iteration(False)

        tooltipmgr.TTMgr().on_button_release(widget, data)

    def usb_IO_periodic(self):
        # users who depend on the IO board could have critical requirements. If USB is enabled, all
        # boards connected to the system must be up and running.
        # all boards are enumerated enmasse when radio button is enabled.
        if self.hal['usbio-status'] == 0 :
            self.usbio_e_message = True      #okay to print messages if going bad

        if self.hal['usbio-status'] < 0 and self.settings.usbio_enabled:
            if self.usbio_e_message == True :  #we transitioned to bad from good
                self.usbio_e_message = False   #don't print until we are good again
                if self.hal['usbio-status'] == -1:
                    self.error_handler.write('USBIO : Board malfunction. Cannot connect to board.')
                elif self.hal['usbio-status'] == -2:
                    self.error_handler.write('USBIO : Board malfunction. Unrecoverable IO error.')
                elif self.hal['usbio-status'] == -3:
                    self.error_handler.write('USBIO : Board malfunction. Duplicate board IDs. Unplug and power off board, then rotate SW1 dial on one of the boards to change ID.')
                elif self.hal['usbio-status'] == -4:
                    self.error_handler.write('USBIO : Board malfunction. All boards not communicating. If the USBIO kit is not installed, turn off the checkbox on the Settings tab.')

            if self.program_running():
                self.stop_motion_safely()         #end this show
                self.error_handler.write('Program run stopped due to USBIO error for safety reasons.', ALARM_LEVEL_MEDIUM)


    def on_mdi_line_changed(self, widget, data=None):
        # catch all typing, convert to uppercase
        widget.set_text(widget.get_text().upper())

    def on_mdi_line_gets_focus(self, widget, event):
        # prevent access to MDI line when running a program.
        if self.program_running():
            self.window.set_focus(None)
            return True
        self.mdi_line.set_text('')
        self.mdi_line.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        self.mdi_line.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color(HIGHLIGHT))
        self.mdi_line_masked = 1
        if self.settings.touchscreen_enabled:
            self.mdi_keypad = numpad.numpad_popup(self.window, widget, True, enter_takedown=False)
            self.mdi_keypad.run()
            # don't call destroy here - it either dismisses itself or other spots do it
            self.mdi_keypad = None
            self.mdi_line_masked = 0
            self.window.set_focus(None)
            return True

    def on_mdi_line_loses_focus(self, widget, event):
        self.mdi_line.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        self.mdi_line.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('#C3C9CA'))
        self.mdi_line.set_text('MDI')
        self.mdi_line.select_region(0, 0)
        if not self.settings.touchscreen_enabled:
            self.mdi_line_masked = 0
        self.window.set_focus(None)

    def on_mdi_line_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Escape:
            self.window.set_focus(None)
            if self.settings.touchscreen_enabled:
                self.on_mdi_line_loses_focus(self, widget)
            return True

        if event.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            if self.gcode_pattern_search.find_last(event):
                return True

        if event.keyval == gtk.keysyms.Down:
#           if self.gcode_pattern_search.mdi_key_command(event):
#               return True
            self.mdi_history_index -= 1
            # range check history index
            if self.mdi_history_index < -1:
                self.mdi_history_index = -1
            if self.mdi_history_index >= 0:
                history_len = len(self.mdi_history)
                if history_len > 0:
                    # place historic text in the display
                    self.mdi_line.set_text(self.mdi_history[self.mdi_history_index])
                    # place cursor at end of line
                    self.mdi_line.set_position(-1)
            else:
                self.mdi_line.set_text("")
            # indicate key has been processed
            return True
        elif event.keyval == gtk.keysyms.Up:
#           if self.gcode_pattern_search.mdi_key_command(event):
#               return True
            self.mdi_history_index += 1
            # range check history index
            history_len = len(self.mdi_history)
            if self.mdi_history_index >= history_len:
                self.mdi_history_index = history_len - 1
            if history_len > 0:
                # place the historic text in the display
                self.mdi_line.set_text(self.mdi_history[self.mdi_history_index])
                # place cursor at end of line
                self.mdi_line.set_position(-1)
            # indicate key has been processed
            return True

        # indicate key not processed
        return False


    def update_gcode_time_labels(self):
        if self.use_hal_gcode_timers:
            self.elapsed_time_label.set_text('%02d:%02d:%02d' % (self.hal['cycle-time-hours'], self.hal['cycle-time-minutes'], self.hal['cycle-time-seconds']))
        else:
            # after a run, if the user loads a completely different program, we stop using the hal timers and show 00:00:00.  This way
            # we can display the estimated time for the new file above the clock and it makes sense.
            self.elapsed_time_label.set_text('00:00:00')

        if self.last_runtime_sec > 0:
            if self.use_hal_gcode_timers:
                current_run_sec = self.hal['run-time-hours']*60*60 + self.hal['run-time-minutes']*60 + self.hal['run-time-seconds']
            else:
                current_run_sec = 0

            remaining_sec = self.last_runtime_sec - current_run_sec
            if remaining_sec >= 0:
                hours = remaining_sec / (60*60)
                remaining_sec -= hours*60*60
                minutes = remaining_sec / 60
                remaining_sec -= minutes*60
                self.remaining_time_label.set_text('%02d:%02d:%02d' % (hours, minutes, remaining_sec))
        else:
            self.remaining_time_label.set_text('')

    def jog(self, jog_axis, jog_direction, jog_speed, apply_pct_override=True, jog_mode = None):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def gcode_status_codes(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def refresh_tool_liststore(self, forced_refresh=False):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def refresh_tool_liststore_for_used_tools(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def tool_table_notebook_page(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def ensure_mode(self, mode):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def issue_mdi(self, mdi_command):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def is_button_permitted(self, widget):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def load_gcode_file(self, path):
        # see if we're simply reloading the same file after somebody tweaked it
        # (conversational workflow will hit this all the time).
        same_file_reload = (self.get_current_gcode_path() == path)
        if not same_file_reload:
            # Operator has loaded a new file.
            # Re-enable the warning on first cycle start for zero length tools.
            self.warn_cycle_start_with_zero_length_tools = True
            # Restore default for max gremlin lines since its a new file
            gcode.max_glcanon_lines(self.default_max_glcanon_lines)

        # reset flag for indicating clipped file load
        self.gcode_file_clipped_load = False
        self.preview_clipped_label.hide()
        self.error_handler.set_loaded_gcode_file_path(path)

    def on_thread_tab(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def program_running(self, do_poll=False):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def mdi_running(self):
        return (self.status.task_mode == linuxcnc.MODE_MDI) and (self.status.interp_state != linuxcnc.INTERP_IDLE)

    def mdi_running_but_paused(self):
        # example would be a G1 slow feed rate that takes awhile to finish and the user pressed
        # feedhold during execution of the command
        return (self.status.task_mode == linuxcnc.MODE_MDI) and (self.status.interp_state == linuxcnc.INTERP_PAUSED)

    def stop_all_jogging(self):
        self.ensure_mode(linuxcnc.MODE_MANUAL)
        axis_count = self.ini_int('TRAJ','AXES')
        for jog_axis in range(axis_count):
            self.stop_jog(jog_axis)

    def stop_jog(self, jog_axis):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def stop_motion_safely(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def status_periodic_50ms(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def quit(self):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def _conversational_notebook_switch_page(self, conv_page_num):
        # Present in base class to avoid false positive pylint no-member errors.
        assert False, "Implemented in Derived .. should never be called"

    def load_dxf_file(self, path, plot=True):
        # Present in base class to avoid false positive pylint no-member errors
        # and to preserve expected arguments.
        assert False, "Implemented in Derived .. should never be called"

    def set_tool_table_data(self,model,row, data):
        # Base class method definition to avoid pylint error flagging and to show desired common arguments
        # for any subclass.
        assert False, "Implemented in Derived .. should never be called"

    def tool_table_rows(self):
        # Base class method definition to avoid pylint error flagging and to show desired common arguments
        # for any subclass.
        assert False, "Implemented in Derived .. should never be called"

    def _get_current_tool_dro(self):
        assert False, "Implemented in Derived .. should never be called"

    def _get_tool_tip_tool_description(self, tool_number, description):
        assert False, "Implemented in Derived .. should never be called"

    def get_G0_tooltip(self, param):
        return ''

    def get_G1_tooltip(self, param):
        return ''

    def get_G2_tooltip(self, param):
        return ''

    def get_G3_tooltip(self, param):
        return ''

    def get_G41_tooltip(self, param):
        return ''

    def get_G41_1_tooltip(self, param):
        return ''

    def get_G42_tooltip(self, param):
        return ''

    def get_G42_1_tooltip(self, param):
        return ''

    def get_G54_59_tooltip(self, param):
        return ''

    def _get_current_spindle_range_image(self, param):
        # this may be called ofr now in lathe case until
        # images are available...
        pass

    def _get_min_max_tool_numbers(self):
        assert False, "Implemented in Derived .. should never be called"

    def on_gcode_scrollbar_button_press(self, vscrollbar, event, data=None):
        # mask the motion line update so user can scroll through code without periodic update stepping on his scrolling
        self.sourceview.masked = True

    def on_gcode_scrollbar_button_release(self, scroll_window, event, data=None):
        self.sourceview.masked = False

    # button press event for all widgets simply moves the eventbox to simulate a 'regular' gtk button motion
    def on_button_press_event(self, widget, event, data=None):
        # gtk.buildable.get_name returns glade object names
        # wigdet.get_name gets imagebutton names
        name = gtk.Buildable.get_name(widget) or widget.get_name()
        msg = name + " button was pressed."
        # the error handler automatically time stamps all log messages with even greater granularity now so no longer needed here.
        self.error_handler.write(msg, ALARM_LEVEL_DEBUG)
        btn.ImageButton.shift_button(widget)

        tooltipmgr.TTMgr().on_button_press(widget, event, data)

    # ----------------------------------------------------
    # load item named in self.image_list with file
    # used for most if not all gtk.Images
    # ----------------------------------------------------
    def set_image(self, image_name, file_name):
        # look for pixbuf with this filename's image in it
        try:
            self.image_list[image_name].set_from_pixbuf(self.pixbuf_dict[file_name])
        except KeyError:
            # not yet loaded, attempt to load it then add to pixbuf dictionary
            try:
                self.image_list[image_name].set_from_file(os.path.join(GLADE_DIR, file_name))
                pixbuf = self.image_list[image_name].get_pixbuf()

                # We don't need to manually composite the alpha channel anymore.  Discoved that for buttons, if you
                # set the visibility property of the gtk.EventBox to False, then the alpha of the image is composited correctly
                # on top of the background image.
                #
                #if pixbuf.get_has_alpha():
                #    # composite the pixbuf into a new pixbuf with the solid gray background
                #    # using the alpha channel - this is because gtk.Image objects don't respect alpha channels (sigh)
                #    new_pixbuf = pixbuf.composite_color_simple(pixbuf.get_width(),
                #                                               pixbuf.get_height(),
                #                                               gtk.gdk.INTERP_BILINEAR, 255, 2, 0x6a6a6a, 0x6a6a6a)
                #    self.pixbuf_dict[file_name] = new_pixbuf
                #    self.image_list[image_name].set_from_pixbuf(new_pixbuf)

                self.pixbuf_dict[file_name] = pixbuf
            except:
                e = sys.exc_info() [0]
                self.error_handler.write('failed to load image %s with file %s.  Error: %s' % (image_name, file_name, e), ALARM_LEVEL_DEBUG)

    def ini_flag(self, ini_section, ini_var, def_val):
        # return True for YES in INI file, def_val for anything else
        val = def_val
        val_str =  self.inifile.find(ini_section, ini_var)
        if val_str != None:
            if val_str.upper() == "YES":
                val = True
        return val

    def ini_float(self, ini_section, ini_var, def_val):
        val = def_val
        try:
            val =  float(self.inifile.find(ini_section, ini_var))
        except TypeError:
            pass
        return val

    def ini_int(self, ini_section, ini_var, def_val=0):
        val = def_val
        try:
            val =  int(self.inifile.find(ini_section, ini_var))
        except TypeError:
            pass
        return val

    def ini_str(self, ini_section, ini_var):
        try:
            ini_str = self.inifile.find(ini_section, ini_var)
        except:
            pass
        return ini_str

    def get_conv_notebook_page_id(self, page_num):
        return get_notebook_page_id(self.conv_notebook, page_num)

    def get_current_conv_notebook_page_id(self):
        return get_current_notebook_page_id(self.conv_notebook)

    def current_conv_notebook_page_id_is(self, name):
        return get_current_notebook_page_id(self.conv_notebook) == name

    def set_conv_page_from_id(self, page_id):
        page_count = self.conv_notebook.get_n_pages()
        for n in range(page_count):
            if page_id == get_notebook_page_id(self.conv_notebook, n):
                self.conv_notebook.set_current_page(n)
                break

    def get_conv_page_num(self, page_id):
        page_count = self.conv_notebook.get_n_pages()
        for n in range(page_count):
            if page_id == get_notebook_page_id(self.conv_notebook, n): return n
        self.error_handler.write('get_conv_page_num - could not find page for %s'%page_id, ALARM_LEVEL_LOW)
        return -1


    def on_feedrate_override_adjustment_value_changed(self, adjustment):
        # stash the most recent value we see from the UI.
        # the value is only acted upon during the 50ms periodic
        # this way the slider dragging stays much more responsive
        self.feedrate_adjustment_newest = adjustment.value
        if not self.console_connected:
            # console knob changes steal focus from MDI line
            self.window.set_focus(None)
        tooltipmgr.TTMgr().on_adjustment_value_changed(adjustment)

    def on_spindle_override_adjustment_value_changed(self, adjustment):
        # stash the most recent value we see from the UI.
        # the value is only acted upon during the 50ms periodic
        # this way the slider dragging stays much more responsive
        self.spindle_adjustment_newest = adjustment.value
        if not self.console_connected:
            # console knob changes steal focus from MDI line
            self.window.set_focus(None)
        tooltipmgr.TTMgr().on_adjustment_value_changed(adjustment)

    def on_maxvel_override_adjustment_value_changed(self, adjustment):
        # stash the most recent value we see from the UI.
        # the value is only acted upon during the 50ms periodic
        # this way the slider dragging stays much more responsive
        self.maxvel_adjustment_newest = adjustment.value
        if not self.console_connected:
            # console knob changes steal focus from MDI line
            self.window.set_focus(None)
        tooltipmgr.TTMgr().on_adjustment_value_changed(adjustment)


    def safely_reset_override_slider_values(self):
        # carefully 'reset' override sliders - don't ever raise them, but restore them to 100% if they are
        # above that.  we just capture the desired value and let the common code kicked off from the
        # periodic actually make the change.
        if self.feedrate_adjustment_current > 100:
            self.error_handler.write("Resetting feedrate override from {:d}% to 100%.".format(int(self.feedrate_adjustment_current)), ALARM_LEVEL_LOW)
            self.set_feedrate_override(100)

        if self.spindle_adjustment_current > 100:
            self.error_handler.write("Resetting spindle RPM override from {:d}% to 100%.".format(int(self.spindle_adjustment_current)), ALARM_LEVEL_LOW)
            self.set_spindle_override(100)

        # we don't touch maxvel since it ranges from 0 to 100 anyway

    # these get called as often as every 50 ms so wait until it changes before updating the widget
    def set_feedrate_override(self, value):
        #if value != self.feedrate_adjustment_newest:
        self.feedrate_override_adjustment.set_value(value)

    def set_spindle_override(self, value):
        #if value != self.spindle_adjustment_newest:
        self.spindle_override_adjustment.set_value(value)

    def set_maxvel_override(self, value):
        #if value != self.maxvel_adjustment_newest:
        self.maxvel_override_adjustment.set_value(value)

    def set_slider_color(self, slider, percent):
        # for percentages over 100% make brighter yellow

        # make color bright yellow for 0%
        if percent < 1.0:
            percent = 102.0;

        if percent >= 101.0:
            # brighter yellow the closer to 200%
            newcolor = (0xff - 100) + (int(percent - 100.0))
            rgb = '#%02x%02x20' % (newcolor, newcolor)
            #self.error_handler.write("%s" % rgb, ALARM_LEVEL_DEBUG)
            slider.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse(rgb))
            slider.modify_bg(gtk.STATE_PRELIGHT, gtk.gdk.color_parse(rgb))
            # not certain what to do with the yellow shade in read-only insensitive state
            # dimmer yellow
            #newcolor = newcolor / 2
            #rgb = '#%02x%02x20' % (newcolor, newcolor)
            slider.modify_bg(gtk.STATE_INSENSITIVE, gtk.gdk.color_parse(rgb))
        else:
            # normal gray
            rgb = '#808080'
            slider.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse(rgb))
            slider.modify_bg(gtk.STATE_PRELIGHT, gtk.gdk.color_parse(rgb))
            # light gray in read-only insensitive state
            rgb = '#c0c0c0'
            slider.modify_bg(gtk.STATE_INSENSITIVE, gtk.gdk.color_parse(rgb))

    def set_slider_readonly(self, hscale, override_label, button_100):
        hscale.set_sensitive(False)
        button_100.hide()
        self.feedrate_override_prefix = 'F '
        self.spindle_override_prefix = 'S '
        self.maxvel_override_prefix = 'V '

        # use feedrate slider X and width for all three override slider sizes
        # same for 100% button
        self.override_100_width, self.override_100_height = self.button_list['feedrate_override_100'].size_request()

        # wide slider size is normal width plus width of button plus space between label and button plus 10
        hscale_x = self.feedrate_override_scale.get_allocation().x
        #print '                                                              hscale_x: %d' % hscale_x
        button_x = self.button_list['feedrate_override_100'].get_allocation().x
        #print '                                                              button_x: %d' % button_x
        button_y = self.button_list['feedrate_override_100'].get_allocation().y
        #print '                                                              button_y: %d' % button_y

        self.override_label_y = override_label.get_allocation().y
        #print '                                                 self.override_label_y: %d' % self.override_label_y

        if self.first_set_slider_readonly:
            # have to get these here - not available at time of contructor
            self.first_set_slider_readonly = False
            self.override_label_x = override_label.get_allocation().x
            #print '                                                 self.override_label_x: %d' % self.override_label_x

        override_label_width, override_label_height = override_label.size_request()
        space_between = button_x - (self.override_label_x + override_label_width) + 10
        #print '                                                         space_between: %d' % space_between
        self.override_slider_width_wide = (self.override_slider_width_normal + self.override_100_width) + space_between
        #print '                                       self.override_slider_width_wide: %d' % self.override_slider_width_wide

        # don't allow focus or override changes will steal the focus away from the MDI line (or anywhere)
        hscale.set_can_focus(False)
        hscale.set_can_default(False)
        hscale.set_size_request(self.override_slider_width_wide, self.override_slider_height)
        # pylint complains if self.fixed from the mill or lathe UI is used here
        # rather than move self.fixed to TormachUIBase we'll do it the longer way through builder
        self.builder.get_object("fixed").move(override_label, button_x - 20, self.override_label_y)

    def set_slider_normal(self, hscale, override_label, button_100):
        hscale.set_can_focus(True)
        hscale.set_sensitive(True)
        button_100.show()
        self.feedrate_override_prefix = ''
        self.spindle_override_prefix = ''
        self.maxvel_override_prefix = ''
        hscale.set_size_request(self.override_slider_width_normal, self.override_slider_height)
        self.override_label_y = override_label.get_allocation().y
        # pylint complains if self.fixed from the mill or lathe UI is used here
        # rather than move self.fixed to TormachUIBase we'll do it the longer way through builder
        self.builder.get_object("fixed").move(override_label, self.override_label_x, self.override_label_y)

    def check_console_presence(self):
        # if the console appears or disappears change the sliders such that
        # they are "read only", wider, and hide the 100% buttons
        self.console_connected = self.hal['console-device-connected']
        # use the coolant button to test without console hardware present
        #self.console_connected = self.hal['coolant']
        if self.prev_console_connected != self.console_connected:
            self.prev_console_connected = self.console_connected

            if self.console_connected:
                # console present
                self.set_slider_readonly(self.feedrate_override_scale, self.feedrate_override_label, self.button_list['feedrate_override_100'])
                self.feedrate_override_label.set_can_focus(False)
                self.set_slider_readonly(self.spindle_override_scale, self.spindle_override_label, self.button_list['rpm_override_100'])
                self.spindle_override_label.set_can_focus(False)
                self.set_slider_readonly(self.maxvel_override_scale, self.maxvel_override_label, self.button_list['maxvel_override_100'])
                self.maxvel_override_label.set_can_focus(False)
                rc_string =  'style "small-slider" { GtkScale::slider-length = 15 } widget "*_override_scale" style "small-slider"'
            else:
                # no console
                self.set_slider_normal(self.feedrate_override_scale, self.feedrate_override_label, self.button_list['feedrate_override_100'])
                self.feedrate_override_label.set_can_focus(True)
                self.set_slider_normal(self.spindle_override_scale, self.spindle_override_label, self.button_list['rpm_override_100'])
                self.spindle_override_label.set_can_focus(True)
                self.set_slider_normal(self.maxvel_override_scale, self.maxvel_override_label, self.button_list['maxvel_override_100'])
                self.maxvel_override_label.set_can_focus(True)
                rc_string = 'style "large-slider" { GtkScale::slider-length = 45 } widget "*_override_scale" style "large-slider"'

            # apply new style for all the override sliders
            gtk.rc_parse_string(rc_string)

            # force redraw with new colors and sizes
            return True
        # no change, no force refresh needed
        return False

    def apply_newest_override_slider_values(self):
        # Apply the most recent value we've seen from dragging any override sliders
        # The most recent value from the UI callbacks is stored and only acted upon
        # during this 50ms periodic.

        force = self.check_console_presence()
        if force:
            # console has appeared or disappeared
            self.error_handler.write("Forcing refresh of override sliders", ALARM_LEVEL_DEBUG)

        if self.feedrate_adjustment_current != self.feedrate_adjustment_newest or force:
            # important to not display 0% when value is > 0.0 and < 1.0
            percentage = self.feedrate_adjustment_newest
            if percentage > 0.0 and percentage < 1.0:
                percentage = 1.0
            self.feedrate_override_label.set_text(self.feedrate_override_prefix+str(int(percentage))+"%")
            self.set_slider_color(self.feedrate_override_scale, percentage)
            self.error_handler.log("Applying feedrate slider override {:.2f}%".format(self.feedrate_adjustment_newest))
            self.command.feedrate(self.feedrate_adjustment_newest / 100.0)
            self.feedrate_adjustment_current = self.feedrate_adjustment_newest

        if self.spindle_adjustment_current != self.spindle_adjustment_newest or force:
            self.spindle_override_label.set_text(self.spindle_override_prefix+str(int(self.spindle_adjustment_newest))+"%")
            self.set_slider_color(self.spindle_override_scale, self.spindle_adjustment_newest)
            self.error_handler.log("Applying spindle slider override {:.2f}%".format(self.spindle_adjustment_newest))
            self.command.spindleoverride(self.spindle_adjustment_newest / 100.0)
            self.spindle_adjustment_current = self.spindle_adjustment_newest

        if self.maxvel_adjustment_current != self.maxvel_adjustment_newest or force:
            self.maxvel_override_label.set_text(self.maxvel_override_prefix+str(int(self.maxvel_adjustment_newest))+"%")
            self.set_slider_color(self.maxvel_override_scale, self.maxvel_adjustment_newest)
            # scale this to a percentage of the traj setting
            scaled_val_lin = self.maxvel_adjustment_newest * self.maxvel_lin / 100
            scaled_val_ang = self.maxvel_adjustment_newest * self.maxvel_ang / 100
            self.error_handler.log("Applying velocity slider override {:.2f} lin:{:.2f} ang:{:.2f}".format(self.maxvel_adjustment_newest, scaled_val_lin, scaled_val_ang))
            self.command.maxvel(scaled_val_lin, scaled_val_ang)
            self.maxvel_adjustment_current = self.maxvel_adjustment_newest

    def _set_preview_limit(self, command, additional_args):
        try:
            limit = additional_args.split()[0]
        except IndexError:
            self.error_handler.write("SET_PREVIEW_LIMIT requires the number of preview lines to limit.  Acceptable values are 10,000 - 999,999,999", ALARM_LEVEL_LOW)
            return 1
        # get rid of user-entered comma separators
        limit = limit.replace(',','')
        is_valid_number, new_preview_limit = ui_misc.is_number(limit)
        if is_valid_number and (new_preview_limit > 9999):
            if (new_preview_limit > 50000):
                    self.error_handler.write("Progams exceeding 50,000 lines can take significant time to generate tool path preview on program load or to redraw the tool path when changing work offsets.")

            self.error_handler.write("Previous number of lines to preview was "
                                     + locale.format('%.0f', gcode.max_glcanon_lines(), grouping=True), ALARM_LEVEL_LOW)
            # change the limit
            self.default_max_glcanon_lines = int(new_preview_limit)
            gcode.max_glcanon_lines(self.default_max_glcanon_lines)
            self.error_handler.write("New number of lines to preview is "
                                     + locale.format('%.0f', gcode.max_glcanon_lines(), grouping=True), ALARM_LEVEL_LOW)
        else:
            self.error_handler.write("SET_PREVIEW_LIMIT requires a number of preview lines to limit.  Acceptable values are 10,000 - 999,999,999", ALARM_LEVEL_LOW)


    def mdi_find_command(self, command):
        command_list = command.split()
        if command.startswith('FIND'):
            self.gcode_pattern_search.find(command)
            return 1
        self.gcode_pattern_search.clear()
        return 0


    def _run_mdi_admin_program(self, run_list):
        # run program
        try:
            p = subprocess.Popen(run_list)
            return p
        except OSError:
            self.error_handler.write("OSError exception raised. Could not run program: %s" % run_list[0], ALARM_LEVEL_LOW)
            return None


    def _get_axis_scale_from_HAL(self, axis_letter):
        axis_letter = axis_letter.lower()
        # read back scale from HAL
        run_list = ['halcmd', '-s', 'getp', '%s_axis_scale' % axis_letter]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        try:
            hal_scale = subprocess.check_output(run_list)
            hal_scale =  float(hal_scale.strip())
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not read back axis scale from HAL. Is this a sim config? %s" % e.cmd, ALARM_LEVEL_DEBUG)
            hal_scale = 0.0
        return hal_scale


    def _get_axis_scale_from_INI(self, axis_letter):
        # read current scale from INI
        axis_letter = axis_letter.lower()
        ini_section = 'AXIS_'
        if axis_letter == 'x':
            ini_section += '0'
        elif axis_letter == 'y':
            ini_section += '1'
        elif axis_letter == 'z':
            ini_section += '2'

        ini_scale = self.ini_float(ini_section, 'SCALE', -1.0)
        if ini_scale == -1.0:
            self.error_handler.write('failed to find %s axis SCALE in INI file' % (axis_letter.upper()), ALARM_LEVEL_LOW)
            ini_scale = 0.0
        return ini_scale


    def _get_axis_scale_factor_from_settings(self, axis_letter):
        # read current scale from INI
        axis_letter = axis_letter.lower()
        ini_section = 'AXIS_'
        if axis_letter == 'x':
            ini_section += '0'
        elif axis_letter == 'y':
            ini_section += '1'
        elif axis_letter == 'z':
            ini_section += '2'

        redis_key = '%s_axis_scale_factor' % axis_letter
        if self.redis.hexists('machine_prefs', redis_key):
            axis_scale_factor = float(self.redis.hget('machine_prefs', redis_key))
        else:
            axis_scale_factor = 0.0

        return axis_scale_factor


    def _set_axis_scale(self, axis_letter, factor):
        # read current scale from INI
        axis_letter = axis_letter.lower()
        ini_section = 'AXIS_'
        if axis_letter == 'x':
            ini_section += '0'
        elif axis_letter == 'y':
            ini_section += '1'
        elif axis_letter == 'z':
            ini_section += '2'

        #print ini_section
        ini_scale = self.ini_float(ini_section, 'SCALE', -1.0)
        #print 'ini_scale: %f' % ini_scale
        if ini_scale == -1.0:
            self.error_handler.write('failed to find %s axis SCALE in INI file' % (axis_letter.upper()), ALARM_LEVEL_LOW)
            return
        new_scale = ini_scale * factor
        #print 'new_scale: %f' % new_scale
        # set new scale in HAL
        run_list = ['halcmd', 'setp', '%s_axis_scale' % axis_letter, '%f' % new_scale]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        try:
            subprocess.check_output(run_list)
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not set axis scale in HAL. Is this a sim config? %s" % e.cmd, ALARM_LEVEL_DEBUG)
        # read back scale from HAL to verify
        run_list = ['halcmd', '-s', 'getp', '%s_axis_scale' % axis_letter]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        hal_scale = '0.0'
        try:
            hal_scale = subprocess.check_output(run_list)
            hal_scale =  float(hal_scale.strip())
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not read back axis scale from HAL. Is this a sim config? %s" % e.cmd, ALARM_LEVEL_DEBUG)
            hal_scale = new_scale

        # do not compare two floats directly for equality
        if abs(new_scale - hal_scale) > 0.01:
            self.error_handler.write('failed to change %s axis scale from %f to %f in HAL' % (axis_letter.upper(), ini_scale, new_scale), ALARM_LEVEL_LOW)
            self.error_handler.write('new_scale: %8.8f,  hal_scale: %8.8f, abs(diff): %8.8f' % (axis_letter.upper(), ini_scale, new_scale), ALARM_LEVEL_LOW)
            return
        else:
            self.error_handler.write('changed %s axis scale from %f to %f in HAL' % (axis_letter.upper(), ini_scale, new_scale), ALARM_LEVEL_DEBUG)
            if abs(factor == 1.0):
                # delete redis key
                self.error_handler.write('%s axis scale factor set to 1.0, deleting redis entry' % axis_letter.upper(), ALARM_LEVEL_DEBUG)
                self.redis.hdel('machine_prefs', '%s_axis_scale_factor' % axis_letter)
            else:
                # save in redis
                self.error_handler.write('saving to redis [machine_prefs]%s_axis_scale_factor %f' % (axis_letter, factor), ALARM_LEVEL_DEBUG)
                self.redis.hset('machine_prefs', '%s_axis_scale_factor' % axis_letter, factor)


    def _get_axis_backlash_from_HAL(self, axis_letter):
        # set backlash in INI/HAL
        axis_letter = axis_letter.lower()
        ini_section = 'AXIS_'
        ini_pin = 'ini.'
        if axis_letter == 'x':
            ini_section += '0'
            ini_pin += '0'
        elif axis_letter == 'y':
            ini_section += '1'
            ini_pin += '1'
        elif axis_letter == 'z':
            ini_section += '2'
            ini_pin += '2'
        ini_pin += '.backlash'

        # read back backlash from HAL
        run_list = ['halcmd', '-s', 'getp', ini_pin]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        hal_backlash = 0.0
        try:
            hal_backlash_str = subprocess.check_output(run_list)
            hal_backlash = float(hal_backlash_str.strip())
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not read %s axis backlash from HAL. %s" % (axis_letter.upper(), e.cmd), ALARM_LEVEL_LOW)

        return hal_backlash


    def _get_axis_backlash_from_settings(self, axis_letter):
        axis_letter = axis_letter.lower()
        redis_key = '%s_axis_backlash' % axis_letter
        if self.redis.hexists('machine_prefs', redis_key):
            axis_backlash = float(self.redis.hget('machine_prefs', redis_key))
            self.error_handler.write("Found %s axis backlash %f in settings" % (axis_letter.upper(), axis_backlash), ALARM_LEVEL_DEBUG)
        else:
            self.error_handler.write("No %s axis backlash stored in redis. This is not an error." % axis_letter.upper(), ALARM_LEVEL_DEBUG)
            axis_backlash = 0.0

        return axis_backlash


    def _set_axis_backlash(self, axis_letter, new_backlash):
        # set backlash in INI/HAL
        axis_letter = axis_letter.lower()
        ini_section = 'AXIS_'
        ini_pin = 'ini.'
        if axis_letter == 'x':
            ini_section += '0'
            ini_pin += '0'
        elif axis_letter == 'y':
            ini_section += '1'
            ini_pin += '1'
        elif axis_letter == 'z':
            ini_section += '2'
            ini_pin += '2'
        ini_pin += '.backlash'

        # set new backlash in HAL
        run_list = ['halcmd', 'setp', ini_pin, '%f' % new_backlash]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        try:
            subprocess.check_output(run_list)
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not set axis backlash in HAL. %s" % e.cmd, ALARM_LEVEL_LOW)
        # read back backlash from HAL to verify
        run_list = ['halcmd', '-s', 'getp', ini_pin]
        self.error_handler.write("halcmd: %s" % run_list, ALARM_LEVEL_DEBUG)
        try:
            hal_backlash = subprocess.check_output(run_list)
            hal_backlash =  float(hal_backlash.strip())
        except subprocess.CalledProcessError, e:
            self.error_handler.write("Could not read back axis backlash from HAL. %s" % e.cmd, ALARM_LEVEL_LOW)
            hal_backlash = new_backlash

        # do not compare two floats directly for equality
        if abs(new_backlash - hal_backlash) > 0.01:
            self.error_handler.write('failed to change %s axis backlash to %f in HAL' % (axis_letter.upper(), new_backlash), ALARM_LEVEL_LOW)
            self.error_handler.write('new_backlash: %8.8f,  hal_backlash: %8.8f, abs(diff): %8.8f inches' % (axis_letter.upper(), new_backlash, hal_backlash), ALARM_LEVEL_LOW)
            return
        else:
            self.error_handler.write('changed %s axis backlash to %f in HAL' % (axis_letter.upper(), new_backlash), ALARM_LEVEL_DEBUG)
            if abs(new_backlash == 0.0):
                # delete redis key
                self.error_handler.write('%s axis backlash set to 0.0, deleting redis entry' % axis_letter.upper(), ALARM_LEVEL_DEBUG)
                self.redis.hdel('machine_prefs', '%s_axis_backlash' % axis_letter)
            else:
                # save in redis
                self.error_handler.write('saving to redis [machine_prefs]%s_axis_backlash %f inches' % (axis_letter, new_backlash), ALARM_LEVEL_DEBUG)
                self.redis.hset('machine_prefs', '%s_axis_backlash' % axis_letter, new_backlash)


    def _glib_idle_mdi_admin_wrapper_callback(self, command):
        # this just wraps the admin handler and always returns False so
        # that there is no risk of the glib.idle_add() mechanism calling us again right away, which happens
        # if you return anything except False.
        self.mdi_admin_commands(command)
        return False


    def gather_logdata(self):
        # automatically do an 'admin settings backup' and include that zip into the log data zip.
        # makes reproducing issues a lot faster in support incidents.

        # create the temp directory where we gather all the log data into first.
        # then give that directory to the gatherdata script as an argument so it continues to
        # add to it.
        tmpdir = os.path.join(os.environ['HOME'], 'tmp')
        if not os.path.isdir(tmpdir):
            os.mkdir(tmpdir)
        logdata_tmpdir = tempfile.mkdtemp(prefix='logdata_', dir=tmpdir)

        sb = settings_backup.settings_backup(self.error_handler)
        sb.perform_automatic_settings_backup(self.settings.netbios_name, logdata_tmpdir, singletons.g_Machine.window, touchscreen_enabled=False)

        # run lots of diagnostic gathering tools and produce a single file in
        # gcode which the customer can provide by email easily.
        # This can take 10-20 seconds so toss up the plexiglass.
        # The automatic settings backup above already uses its own plexiglass so don't nest them.

        with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
            proc = subprocess.Popen(['gatherdata', logdata_tmpdir], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (stdouttxt, stderrtxt) = proc.communicate()
            # The first line of stdout is the filename of the tarball that gatherdata writes.
            filenames = string.split(stdouttxt, '\n', 1)
            self.error_handler.write("Log data written to file %s." % filenames[0], ALARM_LEVEL_LOW)
            # dump the log info from the gatherdata script into our log file
            self.error_handler.log('gatherdata stdout:\n' + stdouttxt)
            self.error_handler.log('gatherdata stderr:\n' + stderrtxt)

            # we don't need to clean up the logdata_tmpdir as the gatherdata script does that for us.


    def validate_and_adjust_soft_limit(self, axis_index, new_limit_inches):
        axisheader = "AXIS_{:d}".format(axis_index)
        axismin = self.ini_float(axisheader, "MIN_LIMIT", 0.0)
        axismax = self.ini_float(axisheader, "MAX_LIMIT", 0.0)

        # first adjust the sign of the new_limit_inches value to make things easier for the user
        new_limit_inches = abs(new_limit_inches)
        if (abs(axismax) - abs(axismin)) < 0.0:
            # axis range is negative
            new_limit_inches *= -1

        # allow extra 2 inches to extend axes
        # in particular modified 1100s with longer Y screws
        axismax += 2.0
        axismin -= 2.0
        # now range check it to be within sanity
        if new_limit_inches > axismax:
            new_limit_inches = axismax
            outputval = new_limit_inches
            if self.g21:
                outputval *= 25.4
            self.error_handler.write("Soft limit is out of range for axis, capping at {:f}".format(outputval), ALARM_LEVEL_MEDIUM)
        if new_limit_inches < axismin:
            new_limit_inches = axismin
            outputval = new_limit_inches
            if self.g21:
                outputval *= 25.4
            self.error_handler.write("Soft limit is out of range for axis, capping at {:f}".format(outputval), ALARM_LEVEL_MEDIUM)
        return new_limit_inches


    def set_axis_minmax_limit(self, axis_index, limit_inches = None):
        '''
        If limit_inches is not passed, the axis is reset to the value from the ini files.
        '''
        axisheader = "AXIS_{:d}".format(axis_index)
        axismin = self.ini_float(axisheader, "MIN_LIMIT", 0.0)
        axismax = self.ini_float(axisheader, "MAX_LIMIT", 0.0)
        axishome_offset = self.ini_float(axisheader, "HOME_OFFSET", 0.0)

        # we are setting the limit opposite the location of the HOME_OFFSET.
        # sometimes this is set_min_limit and sometimes it is set_max_limit.
        # very confusing across all the various configurations.

        # so we just figure it out by looking to see whether HOME_OFFSET is
        # closer to MIN_LIMIT or closer to MAX_LIMIT and then set the limit on the
        # opposite end.

        if abs(abs(axishome_offset) - abs(axismax)) < abs(abs(axishome_offset) - abs(axismin)):
            # we are homing on the max side of the axis so limit the other side.
            if limit_inches is None:
                limit_inches = axismin
            self.command.set_min_limit(axis_index, limit_inches)

        else:
            # we are homing on the min side of the axis so limit the other side.
            if limit_inches is None:
                limit_inches = axismax
            self.command.set_max_limit(axis_index, limit_inches)

        if axis_index == 0: self.x_soft_limit = limit_inches
        if axis_index == 1: self.y_soft_limit = limit_inches
        if axis_index == 2: self.z_soft_limit = limit_inches


    def show_current_limits(self):
        msg = 'Current limits for each axis are:\n'
        minlim = self.status.axis[0]['min_position_limit']
        maxlim = self.status.axis[0]['max_position_limit']
        if self.g21:
            minlim *= 25.4
            maxlim *= 25.4
        msg += '    X {:f} to {:f}\n'.format(minlim, maxlim)
        if self.machineconfig.machine_class() != 'lathe':
            minlim = self.status.axis[1]['min_position_limit']
            maxlim = self.status.axis[1]['max_position_limit']
            if self.g21:
                minlim *= 25.4
                maxlim *= 25.4
            msg += '    Y {:f} to {:f}\n'.format(minlim, maxlim)
        minlim = self.status.axis[2]['min_position_limit']
        maxlim = self.status.axis[2]['max_position_limit']
        if self.g21:
            minlim *= 25.4
            maxlim *= 25.4
        msg += '    Z {:f} to {:f}'.format(minlim, maxlim)
        self.error_handler.write(msg, ALARM_LEVEL_LOW)


    def mdi_admin_commands(self, command):
        command_list = command.split()

        # Keep the list of commands alphabetical!
        helpmsg = "Available ADMIN commands:\n   BOOTMENU ON | OFF\n   CONFIG\n   DATE\n   DROPBOX\n   GET_AXIS_BACKLASH\n   GET_AXIS_SCALE_FACTOR\n   KEYBOARD\n   LOGDATA\n   OPENDOORMAXRPM\n   MEMORY\n   MOUSE\n   NETTOOL\n   NETWORK\n   RESET_SOFT_LIMITS\n   SET_AXIS_BACKLASH\n   SET_AXIS_SCALE_FACTOR\n   SET_PREVIEW_LIMIT\n   SET_X_LIMIT\n   SET_Y_LIMIT\n   SET_Z_LIMIT\n   SETTINGS BACKUP | RESTORE\n   SHOW_SOFT_LIMITS\n   SMARTCOOL_OFFSET\n   SMBPASSWORD ENABLE | DISABLE | SET\n   TIME\n   TOOLTIP DELAYMS | MAXDISPLAYSEC\n   TOUCHSCREEN"

        if command.startswith('PY'):
            '''toss, cmd = command.lower().split(' ', 1)
            self.error_handler.log('py cmd: %s" % cmd)
            try:
                eval(cmd)
            except Exception as e:
                msg = "eval(%s): An exception of type {0} occured, these were the arguments:\n{1!r}" % cmd
                #print msg.format(type(e).__name__, e.args)
                self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)
            '''
            return 1

        elif command.startswith('ADMIN'):
            # get rid of MDI focus - only with ADMIN commands, not with regular G code
            self.window.set_focus(None)

            # if we have the softkeyboard up on the MDI window, be sure to auto-dismiss it also.
            # otherwise other popup dialogs can show up underneath it.  Classic case is typing ADMIN CONFIG
            # with soft keyboard up.
            if self.mdi_keypad:
                self.mdi_keypad.destroy()
                self.mdi_keypad = None
                # some of the below admin commands may end up popping up some modal dialogs
                # and we're already inside the numpad.numad_popup() gtk pump still.
                # unwind all this mess and call us back again "real soon now" once the gtk modal
                # stack has unwound.
                glib.idle_add(self._glib_idle_mdi_admin_wrapper_callback, command)
                return 1

            admin_command = ''
            if len(command_list) > 1:
                admin_command = command_list[1]
                additional_args = ''
                if len(command_list) > 2:
                    additional_args = ' '.join(command_list[2:])
                self.error_handler.write('ADMIN %s %s' % (admin_command, additional_args), ALARM_LEVEL_DEBUG)

            if admin_command == '':
                # User entered just 'ADMIN', probably to get a help list
                self.error_handler.write(helpmsg, ALARM_LEVEL_MEDIUM)
            elif admin_command == 'CONFIG':
                if 'RESET' in additional_args:
                    os.unlink(PATHPILOTJSON_FILEPATH)
                    # final testing of controller uses ADMIN CONFIG RESET to restore it to 'out of box' state
                    # be sure to remove the EULA agreed file so that the customer is shown the EULA again.
                    os.unlink(EULA_AGREED_FILEPATH)
                    self.error_handler.write("Machine configuration reset, next power up will run configuration utility automatically.", ALARM_LEVEL_LOW)
                else:
                    # exit and run config_chooser.py
                    self.switch_configuration()
                    # may or may not return to here
            elif admin_command == 'LOGLEVEL':
                if len(command_list) == 2:   # ADMIN LOGLEVEL
                    self.error_handler.write('Current ADMIN LOGLEVEL for linuxcnc = 0x%x' % self.status.debug, ALARM_LEVEL_MEDIUM)
                    self.error_handler.write('Current ADMIN LOGLEVEL for hal = 0x%x' % self.hal['debug-level'], ALARM_LEVEL_MEDIUM)
                elif len(command_list) == 4:
                    try:
                        lcncnewlevel = int(command_list[2], 16)  # levels are always specified in hexadecimal
                        halnewlevel = int(command_list[3], 16)   # levels are always specified in hexadecimal
                    except ValueError:
                        self.error_handler.write("Unrecognized ADMIN LOGLEVEL command. Try\n    ADMIN LOGLEVEL [value] [value]\nwhere [value] is a hexadecimal value.", ALARM_LEVEL_MEDIUM)
                    else:
                        lcncoldlevel = self.status.debug
                        haloldlevel = self.hal['debug-level']
                        # stupidly this is somehow a signed 32-bit int through the python layers even though it is a bitflag.
                        # just special case 0xFFFFFFFF to be 0x7FFFFFFF on input at least so its easy to "turn every debug flag on".
                        if lcncnewlevel == 0xffffffff:
                            lcncnewlevel = 0x7fffffff
                        if halnewlevel == 0xffffffff:
                            halnewlevel = 0x7fffffff
                        self.command.debug(lcncnewlevel)
                        # set pin so that other hal components move into max debug mode
                        self.hal['debug-level'] = halnewlevel
                        self.error_handler.write('ADMIN LOGLEVEL changed linuxcnc level from 0x%x to 0x%x' % (lcncoldlevel, lcncnewlevel), ALARM_LEVEL_MEDIUM)
                        self.error_handler.write('ADMIN LOGLEVEL changed hal level from 0x%x to 0x%x' % (haloldlevel, halnewlevel), ALARM_LEVEL_MEDIUM)
                else:
                    self.error_handler.write("Unrecognized ADMIN LOGLEVEL command. Try\n    ADMIN LOGLEVEL [value] [value]\nwhere [value] is a hexadecimal value.", ALARM_LEVEL_MEDIUM)
            elif admin_command == 'NETWORK':
                netconfigpath = os.path.join(LINUXCNC_HOME_DIR, 'python/netconfig/netconfig.py')
                self._run_mdi_admin_program([netconfigpath])
            elif admin_command == 'DATE' or admin_command == 'TIME':
                self._run_mdi_admin_program(['sudo', 'time-admin'])
            elif admin_command == 'KEYBOARD':
                self._run_mdi_admin_program([os.environ['DESKTOP_SESSION'] + '-keyboard-properties'])
            elif admin_command == 'DISPLAY':
                self._run_mdi_admin_program([os.environ['DESKTOP_SESSION'] + '-display-properties'])
            elif admin_command in ('TOUCHSCREEN', 'TOUCHPANEL'):
                if additional_args.startswith('SETCAL') or additional_args.startswith('APPLYCAL'):
                    command_line = ['xinput_calibrator_pointercal.sh']
                    if len(additional_args) > 1:
                        arg_list = additional_args.split()[1:]
                        for arg in arg_list:
                            command_line.append(arg)
                    self._run_mdi_admin_program(command_line)
                else:
                    perform_calibration = True
                    rc = subprocess.call('detect_touchscreen.py', shell=True)
                    if rc != 0:
                        dlg = popupdlg.yes_no_popup(self.window, 'Supported and tested touch screen not detected.\n\nDo you want to try to run the calibration utility anyway?')
                        dlg.run()
                        dlg.destroy()
                        if dlg.response == gtk.RESPONSE_NO:
                            perform_calibration = False

                    if perform_calibration:
                        p = self._run_mdi_admin_program(['touchscreen_calibrate.sh'])
                        p.communicate()
                        if p.returncode != 0:
                            dlg = popupdlg.ok_cancel_popup(self.window, 'Could not find any touch screen device to calibrate.', cancel=False, checkbox=False)
                            dlg.run()
                            dlg.destroy()

            elif admin_command == MDI_REMOTE_SCREEN_PROGRAM:
                self._run_mdi_admin_program([REMOTE_SCREEN_PROGRAM])
            elif admin_command == "RECORDMYDESKTOP":
                self._run_mdi_admin_program(["gtk-recordmydesktop"])
            elif admin_command == 'HALMETER':
                halmeter_list = ['halmeter']
                # halmeter can takes pin/sig/param args - pass them along
                if len(command_list) > 2:
                    for cmd_arg in command_list[2:]:
                        halmeter_list.append(cmd_arg.lower())
                self._run_mdi_admin_program(halmeter_list)
            elif admin_command == 'HALCMD':
                halcmd_list = ['halcmd']
                # halmeter can takes pin/sig/param args - pass them along
                if len(command_list) > 2:
                    for cmd_arg in command_list[2:]:
                        halcmd_list.append(cmd_arg.lower())
                self._run_mdi_admin_program(halcmd_list)
            elif admin_command == 'HALSCOPE':
                self._run_mdi_admin_program(['halscope'])
            elif admin_command == 'HALSHOW':
                self._run_mdi_admin_program(['halshow'])
            elif admin_command == 'OPENDOORMAXRPM':
                self.do_open_door_max_rpm(additional_args)
            elif admin_command == 'NETTOOL':
                self._run_mdi_admin_program(['gnome-nettool', '--info=eth0'])
            elif admin_command == 'SET_PREVIEW_LIMIT':
                self._set_preview_limit(command, additional_args)
            elif admin_command == 'SETTINGSBACKUP':
                sb = settings_backup.settings_backup(self.error_handler)
                sb.perform_settings_backup(self.window, self.settings.touchscreen_enabled)
            elif admin_command == 'SETTINGSRESTORE':
                self.do_settings_restore()
            elif admin_command == 'SETTINGS':
                if additional_args.startswith('BACKUP'):
                    sb = settings_backup.settings_backup(self.error_handler)
                    sb.perform_settings_backup(self.window, self.settings.touchscreen_enabled)
                elif additional_args.startswith('RESTORE'):
                    self.do_settings_restore()
                else:
                    self.error_handler.write('Expected BACKUP or RESTORE after SETTINGS command', ALARM_LEVEL_LOW)
            elif admin_command == 'RESET_SOFT_LIMITS':
                # delete redis keys and set to INI values
                # hdel() returns 1 for success and 0 for failure (no such key)
                # so no need for try/except wrapper
                self.ensure_mode(linuxcnc.MODE_MANUAL)

                self.set_axis_minmax_limit(0)
                self.set_axis_minmax_limit(1)
                self.set_axis_minmax_limit(2)
                self.redis.hdel('machine_prefs', 'x_soft_limit')
                self.redis.hdel('machine_prefs', 'y_soft_limit')
                self.redis.hdel('machine_prefs', 'z_soft_limit')

                self.error_handler.write("Soft limits reset", ALARM_LEVEL_LOW)
                self.status.poll()  # get new values due to above
                self.show_current_limits()

            elif admin_command in ('SHOW_SOFT_LIMITS', 'SHOW_LIMITS'):
                self.show_current_limits()

            elif admin_command == 'SET_X_LIMIT' or admin_command == 'SET_Y_LIMIT' or admin_command == 'SET_Z_LIMIT':
                try:
                    limit = additional_args.split()[0]
                except IndexError:
                    self.error_handler.write("Command '%s' requires a distance" % (command), ALARM_LEVEL_LOW)
                    self.show_current_limits()
                    return 1

                is_valid_number, new_limit = ui_misc.is_number(limit)
                if is_valid_number:
                    self.error_handler.write('setting soft limit to: %f' % new_limit, ALARM_LEVEL_DEBUG)
                    self.ensure_mode(linuxcnc.MODE_MANUAL)
                    if self.g21:
                        new_limit = new_limit / 25.4
                    if admin_command == 'SET_X_LIMIT':
                        self.x_soft_limit = self.validate_and_adjust_soft_limit(0, new_limit)
                        self.redis.hset('machine_prefs', 'x_soft_limit', self.x_soft_limit)
                        self.set_axis_minmax_limit(0, self.x_soft_limit)
                    elif admin_command == 'SET_Y_LIMIT':
                        self.y_soft_limit = self.validate_and_adjust_soft_limit(1, new_limit)
                        self.redis.hset('machine_prefs', 'y_soft_limit', self.y_soft_limit)
                        self.set_axis_minmax_limit(1, self.y_soft_limit)
                    elif admin_command == 'SET_Z_LIMIT':
                        self.z_soft_limit = self.validate_and_adjust_soft_limit(2, new_limit)
                        self.redis.hset('machine_prefs', 'z_soft_limit', self.z_soft_limit)
                        self.set_axis_minmax_limit(2, self.z_soft_limit)

                    self.status.poll()   # pick up new values set above
                else:
                    self.error_handler.write("Command '%s' requires a distance" % (command), ALARM_LEVEL_LOW)

                self.show_current_limits()


            elif admin_command == 'SMARTCOOL_OFFSET':
                try:
                    adjustment = additional_args.split()[0]
                except IndexError:
                    self.error_handler.write("Command '%s' requires a distance" % (command), ALARM_LEVEL_LOW)
                    return 1

                is_valid_number, new_limit = ui_misc.is_number(adjustment)
                if is_valid_number:
                    self.redis.hset('machine_prefs', 'smart_cool_offset', adjustment)
                    self.error_handler.write("Smart Cool - Vertical offset set to : %s" % str(adjustment), ALARM_LEVEL_DEBUG)
                    dialog = popupdlg.ok_cancel_popup(self.window, 'Test coolant stream adjustment: ' + str(adjustment) + ' with M8 P0?', cancel=True, checkbox=False)
                    dialog.run()
                    ok_cancel_response = dialog.response
                    dialog.destroy()
                    if ok_cancel_response == gtk.RESPONSE_OK :
                        self.issue_mdi ('M8 P0')

            elif admin_command == 'SMBPASSWORD' and len(additional_args) > 0:
                arg = additional_args.split()[0]
                if arg == 'ENABLE':
                    self._run_mdi_admin_program(['smb_password_on_off.py', 'enable'])
                elif arg == 'DISABLE':
                    self._run_mdi_admin_program(['smb_password_on_off.py', 'disable'])
                elif arg == 'SET':
                    # sudo smbpasswd -a operator
                    terminal_prog = os.environ['COLORTERM']
                    self._run_mdi_admin_program([terminal_prog, '-x', 'bash', '-c', 'sudo smbpasswd -a operator'])
                    self._run_mdi_admin_program(['smb_password_on_off.py', 'enable'])

            elif admin_command == 'DROPBOX':
                self.mdi_line.set_text("")
                self.window.set_focus(None)
                dbhelperpath = os.path.join(LINUXCNC_HOME_DIR, 'python/dropbox/dropbox_helper.py')
                self._run_mdi_admin_program([dbhelperpath])

            elif admin_command == 'MEMORY':
                # show them how much physical RAM the controller has. They may want to upgrade it
                # for dropbox performance.
                totalmb = memory.get_total_ram_mb()
                self.error_handler.write("Total RAM: %d MB" % totalmb, ALARM_LEVEL_LOW)

            elif admin_command == 'HARD_ENABLE_DOOR_SWITCH':
                self.redis.hset('machine_prefs', 'door_sw_enabled', 'True')
                self.redis.hset('machine_prefs', 'door_sw_hard_enabled', 'True')
                self.door_switch_enabled = True
                self.checkbutton_list['enable_door_sw_checkbutton'].set_visible(False)

            elif admin_command == 'VERSION':
                # dump the version.json file to the status page
                debugverstr = versioning.GetVersionMgr().get_debug_version()
                if hasattr(self, 'atc') and self.atc:
                    debugverstr += self.atc.get_atc_firmware_version_description()
                self.error_handler.write(debugverstr, ALARM_LEVEL_QUIET)

            elif admin_command == 'LOGDATA' or (admin_command == 'LOG' and additional_args == 'DATA'):
                self.gather_logdata()

            elif admin_command == 'BOOTMENU':
                arg = additional_args.split()[0]
                if arg in ('SHOW', 'TRUE', 'ON'):
                    # This can take a few seconds so toss up the plexiglass
                    with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
                        proc = subprocess.Popen(['grub_turn_menu_on.sh'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        (stdouttxt, stderrtxt) = proc.communicate()
                        self.error_handler.write("ADMIN BOOTMENU ON ran.  grub_turn_menu_on.sh output:\n%s" % stderrtxt, ALARM_LEVEL_DEBUG)
                        self.error_handler.write("Boot menu ON.", ALARM_LEVEL_LOW)
                elif arg in ('HIDE', 'FALSE', 'OFF'):
                    # This can take a few seconds so toss up the plexiglass
                    with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
                        proc = subprocess.Popen(['grub_turn_menu_off.sh'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        (stdouttxt, stderrtxt) = proc.communicate()
                        self.error_handler.write("ADMIN BOOTMENU OFF ran.  grub_turn_menu_off.sh output:\n%s" % stderrtxt, ALARM_LEVEL_DEBUG)
                        self.error_handler.write("Boot menu OFF.", ALARM_LEVEL_LOW)
                else:
                    self.error_handler.write("ADMIN BOOTMENU '%s' not recognized.  ADMIN BOOTMENU ON and ADMIN BOOTMENU OFF are supported." % arg, ALARM_LEVEL_LOW)

            elif admin_command in ('BROWSER', 'WEBBROWSER'):
                self._run_mdi_admin_program(['x-www-browser'])

            elif admin_command == 'CHROME':
                self._run_mdi_admin_program(['google-chrome'])

            elif admin_command == 'MOUSE':
                self._run_mdi_admin_program(['mate-mouse-properties'])

            elif admin_command == 'TOOLTIP':
                try:
                    arglist = additional_args.split()
                    if arglist[0] == 'DELAYMS':
                        value = int(arglist[1])
                        if value > 0:
                            self.redis.hset('uistate', 'tooltip_delay_ms', str(value))
                            self.error_handler.write("Tooltip delay set to {:d} milliseconds.".format(value), ALARM_LEVEL_QUIET)

                    elif arglist[0] == 'MAXDISPLAYSEC':
                        value = int(arglist[1])
                        if value > 0:
                            self.redis.hset('uistate', 'tooltip_max_display_sec', str(value))
                            self.error_handler.write("Tooltip maximum display time set to {:d} seconds.".format(value), ALARM_LEVEL_QUIET)

                    self.update_tooltipmgr_timers()
                except:
                    self.error_handler.write("Command '{}' not recognized. {}".format(command, helpmsg), ALARM_LEVEL_MEDIUM)

            elif 'GET_AXIS_SCALE_FACTOR' in admin_command:
                axis_list = ['X', 'Y', 'Z']
                if len(additional_args) != 0:
                    arglist = additional_args.split()
                    axis_letter = arglist[0].upper()
                    if axis_letter in axis_list:
                        axis_list = []
                        axis_list.append(axis_letter)
                    # else list them all
                for axis_letter in axis_list:
                    # take abs() to not display negative scales
                    hal_scale = abs(self._get_axis_scale_from_HAL(axis_letter))
                    ini_scale = abs(self._get_axis_scale_from_INI(axis_letter))
                    settings_scale_factor = self._get_axis_scale_factor_from_settings(axis_letter)
                    scale_factor = hal_scale / ini_scale
                    self.error_handler.write("%s axis INI scale: %.1f, currently applied scale: %.1f, scale factor: %.8f" %
                        (axis_letter.upper(), ini_scale, hal_scale, scale_factor), ALARM_LEVEL_MEDIUM)
                    # warn if scale_factor does not match settings
                    # should never happen unless someone used halcmd setp behind our back
                    # settings scale of 0.0 means no setting in redis so scale is 1.0 by default
                    if (settings_scale_factor != 0.0 and abs(settings_scale_factor - scale_factor) > 0.00000001):
                        self.error_handler.write("Warning: %s axis Settings scale factor (%1.8f) does not match currently applied scale factor" %
                            (axis_letter, scale_factor), ALARM_LEVEL_MEDIUM)

            elif 'SET_AXIS_SCALE_FACTOR' in admin_command:
                # SET_AXIS_SCALE_FACTOR X 0.999125
                try:
                    arglist = additional_args.split()
                except IndexError:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z and a scale factor between %.3f and %.3f" %
                        (command, AXIS_SCALE_FACTOR_MIN, AXIS_SCALE_FACTOR_MAX), ALARM_LEVEL_LOW)
                    return 1

                if len(arglist) >= 2:
                    axis, new_factor = arglist[0:2]
                else:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z and a scale factor between %.3f and %.3f" %
                        (command, AXIS_SCALE_FACTOR_MIN, AXIS_SCALE_FACTOR_MAX), ALARM_LEVEL_LOW)
                    return 1

                axis = axis.upper()
                if not axis in ['X', 'Y', 'Z']:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z" % (command), ALARM_LEVEL_LOW)
                    return 1

                is_valid_number, factor = ui_misc.is_number(new_factor)
                if not is_valid_number or factor < AXIS_SCALE_FACTOR_MIN or factor > AXIS_SCALE_FACTOR_MAX:
                    self.error_handler.write("Command '%s' requires a scale factor between %.3f and %.3f" %
                        (command, AXIS_SCALE_FACTOR_MIN, AXIS_SCALE_FACTOR_MAX), ALARM_LEVEL_LOW)
                    return 1
                else:
                    self.error_handler.write("Setting %s axis scale factor to %.8f" %
                        (axis, factor), ALARM_LEVEL_MEDIUM)
                    # set it and check it
                    self._set_axis_scale(axis, factor)
                    return 1

            elif 'GET_AXIS_BACKLASH' in admin_command:
                if self.g21:
                    units = 'mm'
                    linear_scale = 25.4
                else:
                    units = 'inch'
                    linear_scale = 1.0
                axis_list = ['X', 'Y', 'Z']
                if len(additional_args) != 0:
                    arglist = additional_args.split()
                    axis_letter = arglist[0].upper()
                    if axis_letter in axis_list:
                        axis_list = []
                        axis_list.append(axis_letter)
                    # else list them all
                for axis_letter in axis_list:
                    hal_backlash   = self._get_axis_backlash_from_HAL(axis_letter) * linear_scale
                    settings_backlash = self._get_axis_backlash_from_settings(axis_letter) * linear_scale
                    self.error_handler.write("%s axis Settings backlash: %.5f %s, currently applied backlash: %.5f %s" %
                        (axis_letter.upper(), settings_backlash, units, hal_backlash, units), ALARM_LEVEL_MEDIUM)
                    # warn if backlash does not match redis
                    # should never happen unless someone used halcmd setp behind our back
                    # redis backlash of 0.0 means no setting in redis so backlash is INI value (0.0) by default
                    if (settings_backlash != 0.0 and abs(settings_backlash - hal_backlash) > 0.000001):
                        self.error_handler.write("Warning: %s axis Settings backlash (%0.8f %s) does not match currently applied backlash" %
                            (axis_letter, settings_backlash, units), ALARM_LEVEL_MEDIUM)

            elif 'SET_AXIS_BACKLASH' in admin_command:
                # SET_AXIS_BACKLASH X 0.001
                if self.g21:
                    max_backlash = AXIS_BACKLASH_MAX * 25.4
                    max_backlash_label = '%.4f mm' % (AXIS_BACKLASH_MAX * 25.4)
                    units = 'mm'
                else:
                    max_backlash = AXIS_BACKLASH_MAX
                    max_backlash_label = '%.5f inches' % AXIS_BACKLASH_MAX
                    units = 'inch'

                try:
                    arglist = additional_args.split()
                except IndexError:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z and a backlash under %s" %
                        (command, max_backlash_label), ALARM_LEVEL_LOW)
                    return 1

                if len(arglist) >= 2:
                    axis, new_backlash = arglist[0:2]
                else:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z and a backlash under %s" %
                        (command, max_backlash_label), ALARM_LEVEL_LOW)
                    return 1

                if not axis in ['X', 'Y', 'Z']:
                    self.error_handler.write("Command '%s' requires an axis of X, Y, or Z" % (command), ALARM_LEVEL_LOW)
                    return 1

                is_valid_number, backlash = ui_misc.is_number(new_backlash)
                if not is_valid_number or backlash > max_backlash:
                    self.error_handler.write("Command '%s' requires a backlash greater than %.3f and less than or equal to %s" %
                        (command, 0.0, max_backlash_label), ALARM_LEVEL_LOW)
                    return 1
                else:
                    self.error_handler.write("Setting %s axis backlash to %.5f %s" %
                        (axis.upper(), backlash, units), ALARM_LEVEL_MEDIUM)
                    # set it and check it
                    if self.g21:
                        backlash = backlash / 25.4
                    self._set_axis_backlash(axis, backlash)
                    return 1

            elif 'ATC' in admin_command:
                try:
                    arglist = additional_args.split()
                    if arglist[0].startswith('INIT'):
                        dlg = popupdlg.yes_no_popup(self.window, 'Confirm that the ATC USB adapter cable is connected to the ATC control board, and that the machine is on and out of E-stop.\n\nInitialize the ATC for firmware loading?')
                        dlg.run()
                        dlg.destroy()
                        if dlg.response == gtk.RESPONSE_YES:
                            # tell pathpilotmanager to run the atc firmware update utility after all of lcnc is torn down
                            self.program_exit_code = EXITCODE_ATC_FIRMWARE_INIT
                            self.quit()
                        return 1
                except:
                    pass
                self.error_handler.write("Command '{}' not recognized. {}".format(command, helpmsg), ALARM_LEVEL_MEDIUM)

            # debug only
            elif admin_command == 'DOOR_SWITCH_SET_VISIBLE':
                self.redis.hset('machine_prefs', 'door_sw_hard_enabled', 'False')
                self.checkbutton_list['enable_door_sw_checkbutton'].set_visible(True)

            else:
                self.error_handler.write("Command '{}' not recognized. {}".format(command, helpmsg), ALARM_LEVEL_MEDIUM)

            # command was processed
            return 1
        else:
            # command not processed
            return 0


    def update_tooltipmgr_timers(self):
        tooltipmgr.TTMgr().set_timeouts(int(self.redis.hget('uistate', 'tooltip_delay_ms')),
                                        int(self.redis.hget('uistate', 'tooltip_max_display_sec')))


    def on_clear_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.error_handler.clear_history()
        self.usbio_e_message = True    #okay to print messages if going bad


    def on_update_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.software_update()


    def on_logdata_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.gather_logdata()


    def export_tooltable(self):
        # account for mill vs. lathe in filename
        # insert a YYYY-jan-08 type of date into the filename
        timestamp = time.strftime('-%Y-%b-%d', time.localtime())
        machine_type_str = ''
        machine_type = self.machine_type
        if machine_type == MACHINE_TYPE_MILL:
            machine_type_str = '-mill'
        if machine_type == MACHINE_TYPE_LATHE:
            machine_type_str = '-lathe'
        #fileroot, ext = os.path.splitext(os.path.join(GCODE_BASE_PATH, 'tooltable.csv'))
        csv_path = os.path.join('tooltable' + machine_type_str + timestamp + '.csv')

        with tormach_file_util.file_save_as_popup(self.window, 'Choose a CSV file name for the exported tool table.', csv_path, '.csv', self.settings.touchscreen_enabled, usbbutton=True, closewithoutsavebutton=False) as dialog:
            # Get information from dialog popup
            response = dialog.response
            csv_path = dialog.path

        if response != gtk.RESPONSE_OK:
            return

        # check to see if we're going to overwrite an existing file
        if os.path.exists(csv_path):
            with popupdlg.confirm_file_overwrite_popup(self.window, csv_path, self.settings.touchscreen_enabled) as popup:
                response = popup.response
                if response != gtk.RESPONSE_OK:
                    return
                csv_path = popup.path

        try:
            f = open(csv_path, 'wt')
        except Exception as e:
            self.error_handler.write('Exception opening CVS file', ALARM_LEVEL_LOW)
            msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
            self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)
            return

        try:
            writer = csv.writer(f, dialect='excel', quoting=csv.QUOTE_MINIMAL)
            # leave a hint as to the tool table's machine type
            dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
            units_mode = ' (metric)' if self.g21 else ''
            version_tag = ' - v1'
            factor = 25.4 if self.g21 else 1.0
            dt += version_tag
            if machine_type == MACHINE_TYPE_MILL:
                max_tools = MAX_NUM_MILL_TOOL_NUM
                table_type = 'Mill Tool Table' + units_mode
                writer.writerow( (table_type, dt,'This must be the first row - do not edit' ) )
                writer.writerow( ('Tool number', 'Description', 'Z offset', 'Diameter') )
            elif machine_type == MACHINE_TYPE_LATHE:
                # two entries for each tool - T and T + 10000
                max_tools = MAX_LATHE_TOOL_NUM * 2
                table_type = 'Lathe Tool Table' + units_mode
                writer.writerow( (table_type, dt, 'This must be the first line - do not edit' ) )
                writer.writerow( ('Tool number', 'Description', 'X offset', 'Y offset', 'Z offset', 'Nose Tip Radius', 'Front angle', 'Back angle', 'Orientation') )
            else:
                self.error_handler.write('Unable to export tool table - unrecognized machine type: %d' % machine_type, ALARM_LEVEL_LOW)
                return

            # only pull tool_table across status channel once and then examine python object locally
            tool_table = self.status.tool_table
            precision_spec = '%.6f' if self.g21 else '%.7f'

            # write out tool table as CSV file
            for pocket in xrange(1, max_tools + 1):
                tool_num    = '%d' % tool_table[pocket].id
                description = self.get_tool_description(tool_num,'high_precision,report_error')
    #           if in metric mode convert to imperial with standard formating...
    #           if self.g21: description = ui_support.ToolDescript.convert_text(description)
                if machine_type == MACHINE_TYPE_MILL:
                    zoffset     = precision_spec % (tool_table[pocket].zoffset*factor)
                    diameter    = precision_spec % (tool_table[pocket].diameter*factor)
                elif machine_type == MACHINE_TYPE_LATHE:
                    xoffset     = precision_spec % (tool_table[pocket].xoffset*factor)
                    yoffset     = precision_spec % (tool_table[pocket].yoffset*factor)
                    zoffset     = precision_spec % (tool_table[pocket].zoffset*factor)
                    diameter    = precision_spec % (tool_table[pocket].diameter*factor/2.0)
                    frontangle  = precision_spec % tool_table[pocket].frontangle
                    backangle   = precision_spec % tool_table[pocket].backangle
                    orientation = '%d'   % tool_table[pocket].orientation

                try:
                    if machine_type == MACHINE_TYPE_MILL:
                        writer.writerow( (tool_num, description, zoffset, diameter) )
                    if machine_type == MACHINE_TYPE_LATHE:
                        writer.writerow( (tool_num, description, xoffset, yoffset, zoffset, diameter, frontangle, backangle, orientation) )
                except Exception as e:
                    self.error_handler.write('Exception exporting tool table CVS file', ALARM_LEVEL_LOW)
                    msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                    self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)
        finally:
            f.close()

    def import_tooltable(self):
        with tormach_file_util.file_open_popup(self.window, GCODE_BASE_PATH, '*.csv',
                                               'Choose a CSV file for importing the tool table.\n\nWARNING: This action overwrites the entire tool table. Exporting the tool table first to create a backup file is recommended.',
                                               usb_button=True) as dialog:
            if dialog.response != gtk.RESPONSE_OK:
                return
            # Extract dialog information for later use
            csv_path = dialog.get_path()

        # a lot of time may have passed between selection and "OK"
        # in which time the USB stick may have been removed
        if not os.path.isfile(csv_path):
            self.error_handler.write("Selected tool table file not found: %s" % csv_path, ALARM_LEVEL_LOW)
            return

        # copy file to ~/ $HOME directory
        path_only, name_only = os.path.split(csv_path)
        destination = os.path.join('/tmp', name_only)
        try:
            shutil.copy2(csv_path, destination)
            tormach_file_util.filesystem_sync(self.error_handler)
        except:
            pass

        # tmp file in case something fails - replace tool.tbl at the very end
        tmpfile = '/tmp/tool.tbl'
        try:
            tt = open(tmpfile, 'wt')
        except Exception as e:
            self.error_handler.write('Exception opening temporry file for CVS import: %s' % tmpfile, ALARM_LEVEL_LOW)
            msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
            self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)

        try:   # outer try/finally for closing the tt file above
            try:
                f = open(csv_path, 'rt')
                try:
                    reader = csv.reader(f)
                    tt_list = list()
                    for row in reader:
                        tt_list.append(row)
                except Exception as e:
                    self.error_handler.write('Exception reading tool table CVS file', ALARM_LEVEL_LOW)
                    msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                    self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)
                finally:
                    f.close()
            except Exception as e:
                self.error_handler.write('Exception opening tool table CVS file: %s' % csv_path, ALARM_LEVEL_LOW)
                msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                self.error_handler.write(msg.format(type(e).__name__, e.args), ALARM_LEVEL_LOW)

            # tt_list has each row of the CSV data
            # tt_list[0][0] indicates lathe or mill tool table data
            machine_type = self.machine_type
            if machine_type == MACHINE_TYPE_LATHE and not tt_list[0][0].startswith('Lathe'):
                self.error_handler.write('Wrong tool table for lathe: "%s" found in first cell' % tt_list[0][0], ALARM_LEVEL_LOW)
                return
            elif machine_type == MACHINE_TYPE_MILL and  not tt_list[0][0].startswith('Mill'):
                self.error_handler.write('Wrong tool table for mill "%s" found in first cell' % tt_list[0][0], ALARM_LEVEL_LOW)
                return
            elif machine_type != MACHINE_TYPE_MILL and machine_type != MACHINE_TYPE_LATHE:
                self.error_handler.write('Unable to import tool table - unrecognized machine type: %d' % machine_type, ALARM_LEVEL_LOW)
                return
            # correct format for this machine type verified

            # conversaion logic if going from a G21 saved table to a G20 environment or visa versa...
            version_tag = re.findall(r'v\d{1}\.?\d?', tt_list[0][1], re.IGNORECASE)
            version = version_tag[0] if any(version_tag) else ''
            lathe_diameter_factor = 2.0 if version == 'v1' else 1.0
            table_is_metric = 'metric' in tt_list[0][0]
            currently_metric = self.g21
            metric_to_imperial = table_is_metric and not currently_metric
            imperial_to_metric = not table_is_metric and currently_metric
            factor = 0.039370079 if table_is_metric else 1.0
            description_dict = {}

            for row in tt_list[1:]:
                if len(row) == 0:
                    # skip blank lines
                    continue
                #print row
                tool_num = row[0]
                try:
                    tool_integer = int(row[0])
                except ValueError:
                    # exception - skip to next row
                    # probably still reading the header lines of the CSV file
                    # log it anyway in case it is a real problem
                    self.error_handler.write('Import tool table: row ignored - tool number not recognized: "%s"' % ', '.join(row), ALARM_LEVEL_DEBUG)
                    continue

                description = row[1]
                description_dict[tool_num] = description

                if machine_type == MACHINE_TYPE_MILL:
                    if tool_integer < 1 or tool_integer > MAX_NUM_MILL_TOOL_NUM:
                        self.error_handler.write('Import tool table: row ignored - tool number too large: "%s"' % ', '.join(row), ALARM_LEVEL_LOW)
                    try:
                        zoffset  = (float(row[2]))*factor
                        diameter = (float(row[3]))*factor
                    except:
                        self.error_handler.write('Import tool table: row ignored - error interpreting row data: "%s"' % ', '.join(row), ALARM_LEVEL_LOW)
                    # write line to tool.tbl file
                    # mill format: 'T1 P1 D0.249000 Z+1.500000 ;'
                    tt.write("T%s P%s D%.6f Z%.6f ;\n" % (tool_num, tool_num, diameter, zoffset))

                if machine_type == MACHINE_TYPE_LATHE:
                    # there are two range of tool table entries (1 - 99) and (10001 - 10099) where the geometry offsets are stashed
                    if not ((tool_integer >= 1 and tool_integer <= MAX_LATHE_TOOL_NUM) or (tool_integer >= 10001 and tool_integer <= (10000 + MAX_LATHE_TOOL_NUM))):
                        self.error_handler.write('Import tool table: row ignored - tool number out of range: "%s"' % ', '.join(row), ALARM_LEVEL_LOW)
                    try:
                        xoffset     = (float(row[2]))*factor
                        yoffset     = (float(row[3]))*factor
                        zoffset     = (float(row[4]))*factor
                        diameter    = (float(row[5]))*factor*lathe_diameter_factor
                        frontangle  = (float(row[6]))
                        backangle   = (float(row[7]))
                        orientation = (  int(row[8]))

                        tt_entry = 'T%d P%d D%.6f' % (tool_integer, tool_integer, diameter)
                        if xoffset != 0.0:
                            tt_entry += ' X%.6f' % xoffset
                        # include Y for RapidTurn gang tooling offsets
                        if yoffset != 0.0:
                            tt_entry += ' Y%.6f' % yoffset
                        if zoffset != 0.0:
                            tt_entry += ' Z%.6f' % zoffset
                        if frontangle != 0.0:
                            tt_entry += ' I%.6f' % frontangle
                        if backangle != 0.0:
                            tt_entry += ' J%.6f' % backangle

                        tt_entry += ' Q%d' % orientation
                        tt_entry += ' ;'

                    except:
                        self.error_handler.write('Import tool table: row ignored - error interpreting row data: %s' % ', '.join(row), ALARM_LEVEL_LOW)
                    # write line to tool.tbl file
                    # lathe format: 'T1 P1 D0.0 X0.000000 Z0.000000 I-85.000000 J-5.000000 Q2 ;'
                    #print tt_entry
                    tt.write(tt_entry + '\n')

        finally:
            # close file, replace existing tool.tbl with tmp file
            tt.close()

        # get tool table name from INI file [EMCIO]TOOL_TABLE
        # do tilde expansion
        dst = os.path.expanduser(self.ini_str('EMCIO', 'TOOL_TABLE'))
        # move tmp file into place over existing file
        shutil.move(tmpfile, dst)
        # tell LinuxCNC to reread tool table
        self.command.load_tool_table()

        # set descriptions
        if machine_type == MACHINE_TYPE_MILL:
            max_tools = MAX_NUM_MILL_TOOL_NUM
        elif machine_type == MACHINE_TYPE_LATHE:
            max_tools = MAX_LATHE_TOOL_NUM

        for tool, desc in description_dict.iteritems():
            tool = int(tool)
            if tool > max_tools: continue

            # Note: 'set_tool_description' is the methods that sets the entry
            # in Redis .. these entries are always in imperial units..
            # if incoming tool description is metric, but PP is G20.
            # if the incomming descripion is in imperial units then force the 'no_convert' .. so
            # if metric_to_imperial -> action includes 'full_precision'
            # if imperial_to_metric -> action inlcudes 'no_convert'
            action = 'report_error'
            action += 'full_precision' if table_is_metric else 'no_convert' if imperial_to_metric else ''
            self.set_tool_description(tool, desc, action)

        # apply offsets to current tool if there is one and we're out of reset
        if self.status.tool_in_spindle > 0 and self.status.task_state == linuxcnc.STATE_ON:
            if machine_type == MACHINE_TYPE_MILL:
                self.issue_mdi("G43")
            # lathe does not support G43 - issue warning to verify correct offsets are applied
            if machine_type == MACHINE_TYPE_LATHE:
                self.error_handler.write('Verify that tool %d offsets are applied' % self.status.tool_in_spindle, ALARM_LEVEL_LOW)

        # get fresh tool table status from LinuxCNC
        self.status.poll()
        # this refreshes the Offsets tab information
        self.refresh_tool_liststore(forced_refresh=True)


    def on_internet_led_button_release_event(self, widget, data=None):
        if self.is_button_permitted(widget):
            # do the same thing as ADMIN NETWORK
            self.mdi_admin_commands("ADMIN NETWORK")


    def usb_device_event(self, observer, device):
        event_time = datetime.datetime.now().strftime(" %Y-%m-%d %H:%M:%S")
        # two events with every plug, only one has the ID_MODEL
        if device.get('ID_MODEL') == None: return
        action = device.action
        if 'add' in action:
            action = 'plugged in'
        elif 'remove' in device.action:
            action = 'unplugged'

        device_name = device.get('ID_MODEL')
        message = 'USB device (%s) was %s. %s'  % (device_name, action, event_time)
        self.error_handler.write(message , ALARM_LEVEL_QUIET)

        # reinstate touchscreen calibration, which is lost on enumeration
        if 'ouch' in device_name:
            if 'plugged in' in action:
                self.error_handler.write('Reinstating touchscreen calibration due to touchscreen USB communication loss. %s' % (event_time), ALARM_LEVEL_DEBUG)
                # spurious usb enumeration kills the exisitng calibration
                # need sleep statement to give touchscreen some time to init before re-applying cal file
                time.sleep(1)
                subprocess.call('xinput_calibrator_pointercal.sh')

        # the following call always returns None on my USB stick
        #print 'Manufacturer: %s' % device.get('MANUFACTURER')

        # this look gets the Manufaturer, but doesn't seem worth the hassle as most devices are identifiable to
        # the user by the ID_MODEL
        '''try:
            for attrName, attrValue in device.attributes.iteritems():
                if 'manufacturer' in attrName:
                    print attrName + ": " + str(attrValue)
        except:
            pass'''

    # alt-key handler calls this to stuff the FIFO of button press/release events
    # to emit to UI
    def enqueue_button_press_release(self, widget):
        ev = gtk.gdk.Event(gtk.gdk.BUTTON_PRESS)
        ev.time = 0
        ev.window = widget.get_window()
        ev.send_event = True
        # 1 == left mouse button
        ev.button = 1
        self.button_deque.append([widget, 'button_press_event', ev])
        self.button_deque.append([widget, 'button_release_event', ev])

    def check_keyboard_shortcut_fifo(self):
        try:
            (widget, press_or_release, event) = self.button_deque.popleft()
            widget.emit(press_or_release, event)
        except IndexError:
            pass

    #
    # Init supporting functions
    #
    def setup_gcode_buttons(self):
        """ Create G code buttons manually (Load and Edit G Code)
        This is done here because we're using the ImageButton class instead of an EventBox / Image pair.
        """

        # Create and size button
        load_gcode_button = btn.ImageButton('load-gcode.png','load_gcode')
        load_gcode_button.set_size_request(100,38)

        # Copied X / Y coords from old glade file
        load_gcode_button.x = 160
        load_gcode_button.y = 10
        self.notebook_file_util_fixed.put(load_gcode_button, load_gcode_button.x,load_gcode_button.y)

        #Add button to list
        self.button_list.setdefault('load_gcode',load_gcode_button)

        #Store it as a class member to preserve the object
        self.load_gcode_button = load_gcode_button

        # Create and size button
        edit_gcode_button = btn.ImageButton('edit-gcode-button.png','edit_gcode')

        # Copied X / Y coords from old glade file
        edit_gcode_button.x = 882
        edit_gcode_button.y = 355
        self.notebook_file_util_fixed.put(edit_gcode_button, edit_gcode_button.x,edit_gcode_button.y)

        self.button_list.setdefault('edit_gcode',edit_gcode_button)
        self.edit_gcode_button = edit_gcode_button
        gtk.Buildable.set_name(self.edit_gcode_button,'gcode_edit_button')

        #setup the con-edit button
        conv_edit_gcode_button = btn.ImageButton('conv-edit-button.png','conv_edit')
        gtk.Buildable.set_name(conv_edit_gcode_button,'conv_edit_button')

        # Copied X / Y coords from old glade file
        conv_edit_gcode_button.x = 772
        conv_edit_gcode_button.y = 355
        self.notebook_file_util_fixed.put(conv_edit_gcode_button, conv_edit_gcode_button.x,conv_edit_gcode_button.y)

        self.conv_edit_gcode_button = conv_edit_gcode_button

        # Connect button signals to class functions
        self.load_gcode_button.connect("button_press_event",self.on_button_press_event)
        self.load_gcode_button.connect("button_release_event",self.on_load_gcode_button_release_event)

        self.edit_gcode_button.connect("button_press_event",self.on_button_press_event)
        self.edit_gcode_button.connect("button_release_event",self.on_edit_gcode_button_release_event)
        self.edit_gcode_button.connect("enter-notify-event",self.on_mouse_enter)
        self.edit_gcode_button.connect("leave-notify-event",self.on_mouse_leave)
        self.edit_gcode_button.permitted_states = STATE_IDLE | STATE_IDLE_AND_REFERENCED

        self.conv_edit_gcode_button.connect("button_press_event",self.on_button_press_event)
        self.conv_edit_gcode_button.connect("button_release_event",self.on_conv_edit_gcode_button_release_event)
        self.conv_edit_gcode_button.connect("enter-notify-event",self.on_mouse_enter)
        self.conv_edit_gcode_button.connect("leave-notify-event",self.on_mouse_leave)
        self.conv_edit_gcode_button.permitted_states = STATE_IDLE | STATE_IDLE_AND_REFERENCED
        self.button_list.setdefault('conv_edit',self.conv_edit_gcode_button)


    def edit_gcode_file(self, path):
        file_name_for_display = path.replace(GCODE_BASE_PATH + '/', '')
        self.error_handler.write('Editing G code file: %s' % file_name_for_display, ALARM_LEVEL_DEBUG)
        try:
            # run the editor, store the pid somewhere in case of crash
            self.editor_pid = subprocess.Popen([self.gcode_edit_program_to_run, path]).pid
        except OSError:
            self.error_handler.write("OSError exception raised. Could not run edit program: %s" % self.gcode_edit_program_to_run, ALARM_LEVEL_LOW)
        except IOError:
            self.error_handler.write("path %s is not a valid G code file" % path, ALARM_LEVEL_DEBUG)


    # edit selected or else currently loaded gcode file
    def on_edit_gcode_button_release_event(self, widget, data=None):
        if self.is_button_permitted(widget):
            path = self.hd_file_chooser.selected_path
            if path:
                self.error_handler.write("Editing file on HD: %s" % path, ALARM_LEVEL_DEBUG)
                self.edit_gcode_file(path)
            else:
                path = self.current_gcode_file_path
                if path:
                    self.error_handler.write("Editing loaded G code file: %s" % path, ALARM_LEVEL_DEBUG)
                    self.edit_gcode_file(path)
                else:
                    self.edit_new_gcode_file()


    def edit_new_gcode_file(self):
        # Alt-E shortcut handling uses this also for consistency...
        path = os.path.join(GCODE_BASE_PATH, 'Untitled.nc')
        if os.path.exists(path):
            path = self.fsclipboard_mgr.generate_non_conflicting_filename(GCODE_BASE_PATH, 'Untitled.nc')
        self.error_handler.write("Editing new G code file: %s" % path, ALARM_LEVEL_DEBUG)
        self.edit_gcode_file(path)


    def on_gcode_options_button_press(self, widget, event, data=None):
        btn.ImageButton.shift_button(widget)
        glib.idle_add(btn.ImageButton.unshift_button, widget)  # this makes the button appear to dip in just briefly

        '''
        p = gremlin_options.gremlin_popup(self.window, self.gcode_program_tools_used, self)
        p.window.move(0, 0)
        p.run()
        p.destroy()
        print "                Gremlin tools", p.visible_tools
        self.gremlin.set_visible_tools(p.visible_tools)
        self.gremlin._redraw()
        '''

        # this is really to make touchscreen users happy since they have no right click button options
        # we re-use the exact same context menu logic
        menu = gtk.Menu()
        self.on_gcode_sourceview_populate_popup(self.sourceview, menu)
        menu.popup(None, None, None, event.button, event.time)


    # this has to create then append our menu item then call show()
    def on_gcode_sourceview_populate_popup(self, textview, menu):
       # get rid of all default gtk.sourceview menu options
        for child in menu.get_children():
            menu.remove(child)

        set_start_line_item = gtk.MenuItem("Set start line")
        set_start_line_item.connect("activate", self.set_start_line_callback)
        menu.append(set_start_line_item)
        set_start_line_item.show()

        if self.sourceview.get_show_line_numbers():
            show_line_numbers_item = gtk.MenuItem("Hide line numbers")
        else:
            show_line_numbers_item = gtk.MenuItem("Show line numbers")
        show_line_numbers_item.connect("activate", self.toggle_line_numbers_callback)
        menu.append(show_line_numbers_item)
        show_line_numbers_item.show()

        if self.redis.hget('uistate', 'main_tab_gcodewindow_syntaxcoloring') == 'True':
            gcode_syntaxcoloring_item = gtk.MenuItem("Disable g-code colors")
        else:
            gcode_syntaxcoloring_item = gtk.MenuItem("Enable g-code colors")
        gcode_syntaxcoloring_item.connect("activate", self.toggle_gcode_syntaxcoloring_callback)
        menu.append(gcode_syntaxcoloring_item)
        gcode_syntaxcoloring_item.show()

        show_in_file_tab_item = gtk.MenuItem("Show in File tab")
        show_in_file_tab_item.connect("activate", self.show_in_file_tab_callback)
        menu.append(show_in_file_tab_item)
        show_in_file_tab_item.show()

        # was the g-code file clipped due to admin set_preview_limit line count?
        if self.is_gcode_program_loaded and self.gcode_file_clipped_load:
            load_all_preview_lines_item = gtk.MenuItem("Load all preview lines")
            load_all_preview_lines_item.connect("activate", self.load_all_preview_lines_callback)
            menu.append(load_all_preview_lines_item)
            load_all_preview_lines_item.show()


    def load_all_preview_lines_callback(self, widget):
        # we don't care about overwriting the max lines here.
        # if the user loads a different file, that's when we flip back to the default.
        # this is needed because through other actions (mdi line, changing work offsets),
        # the gremlin will load the tool path again and it should be using the same
        # values (not restoring to clipped behavior).
        gcode.max_glcanon_lines(999999999)
        self.reload_gcode_file()


    def show_in_file_tab_callback(self, widget):
        # take current path of file loaded, change to File tab, and change
        # HD file chooser selection to highlight the file (and scroll ideally...)
        self.notebook.set_current_page(self.notebook.page_num(self.notebook_file_util_fixed))
        self.hd_file_chooser.set_selection(self.get_current_gcode_path())


    def keyboard_checkbutton_toggled(self):
        # change fileview objects flag so that the right click menu obeys the current touchscreen setting,
        # not the setting used when the objects were created.
        self.hd_file_chooser.touchscreen_enabled = self.settings.touchscreen_enabled
        self.usb_file_chooser.touchscreen_enabled = self.settings.touchscreen_enabled


    def toggle_gcode_syntaxcoloring_callback(self, widget):
        if self.redis.hget('uistate', 'main_tab_gcodewindow_syntaxcoloring') == 'True':
            self.set_gcode_syntaxcoloring(False)
        else:
            self.set_gcode_syntaxcoloring(True)

    def toggle_line_numbers_callback(self, widget):
        if self.sourceview.get_show_line_numbers():
            self.sourceview.set_show_line_numbers(False)
            self.redis.hset('uistate', 'main_tab_gcodewindow_linenumbers', 'False')
        else:
            self.sourceview.set_show_line_numbers(True)
            self.redis.hset('uistate', 'main_tab_gcodewindow_linenumbers', 'True')

    def set_start_line_callback(self, widget):
        self.set_start_line()

    def set_gcode_syntaxcoloring(self, enabled):
        # set the language for syntax highlighting manually for the buffer
        ui_misc.set_sourceview_gcode_syntaxcoloring(self.gcodelisting_buffer, enabled)
        ui_misc.set_sourceview_gcode_syntaxcoloring(self.file_preview_buffer, enabled)
        if enabled:
            self.redis.hset('uistate', 'main_tab_gcodewindow_syntaxcoloring', 'True')
        else:
            self.redis.hset('uistate', 'main_tab_gcodewindow_syntaxcoloring', 'False')

    ### Setup functions called by init
    def setup_gcode_marks(self):
        """
        g code preview on main tab
        """

        # full name of file with path
        self.gcode_filename = ""
        self.sourceview = self.builder.get_object("gcode_sourceview")
        self.gcodelisting_buffer = gtksourceview2.Buffer()
        self.sourceview.set_buffer(self.gcodelisting_buffer)

        font_description = pango.FontDescription('Roboto Condensed 10')
        self.sourceview.modify_font(font_description)

        # restore the state of showing or hiding line numbers from the last run
        if self.redis.hexists('uistate', 'main_tab_gcodewindow_linenumbers'):
            if self.redis.hget('uistate', 'main_tab_gcodewindow_linenumbers') == 'True':
                self.sourceview.set_show_line_numbers(True)
            else:
                self.sourceview.set_show_line_numbers(False)
        else:
            # default is to hide the line numbers
            self.redis.hset('uistate', 'main_tab_gcodewindow_linenumbers', 'False')
            self.sourceview.set_show_line_numbers(False)

        # restore the state of g-code syntax coloring from the last run
        if self.redis.hexists('uistate', 'main_tab_gcodewindow_syntaxcoloring'):
            if self.redis.hget('uistate', 'main_tab_gcodewindow_syntaxcoloring') == 'True':
                self.set_gcode_syntaxcoloring(True)
            else:
                self.set_gcode_syntaxcoloring(False)
        else:
            # default is to enable syntax coloring (this also creates the redis key)
            self.set_gcode_syntaxcoloring(True)

        self.gcode_pattern_search = gcode_pattern_searcher(self)

        # Define colors for different mark types
        self.mark_colors = {'start':gtk.gdk.Color('#00F700'), #Green
                            'current':gtk.gdk.Color('#E7A700'), #Orange
                            'blank':gtk.gdk.Color('#FFFFFF')} # Background color

        self.sourceview.set_mark_category_background('current', self.mark_colors['current'])
        self.sourceview.set_mark_category_background('start', self.mark_colors['start'])
        self.sourceview.masked = False

        self.scrolled_window = self.builder.get_object("scrolledwindow")
        gcode_vscrollbar = self.scrolled_window.get_vscrollbar()
        gcode_hscrollbar = self.scrolled_window.get_hscrollbar()
        gcode_vscrollbar.connect("button-press-event", self.on_gcode_scrollbar_button_press)
        gcode_vscrollbar.connect("button-release-event", self.on_gcode_scrollbar_button_release)
        gcode_hscrollbar.connect("button-press-event", self.on_gcode_scrollbar_button_press)
        gcode_hscrollbar.connect("button-release-event", self.on_gcode_scrollbar_button_release)

        # set starting line
        self.gcode_start_line = 1
        line_iter = self.gcodelisting_buffer.get_iter_at_line(self.gcode_start_line-1)

        self.gcodelisting_current_mark = self.gcodelisting_buffer.create_source_mark('current', 'current', line_iter)
        self.gcodelisting_start_mark = self.gcodelisting_buffer.create_source_mark('start', 'start', line_iter)



    def setup_copy_buttons(self):
        """ Create transfer to and from HD / USB buttons from ImageButton class.
        """

        # Create and size button
        transfer_to_hd_button = btn.ImageButton('left-arrow.png','transfer_to_hd')
        transfer_to_hd_button.set_size_request(38,69)

        # Copied X / Y coords from old glade file
        transfer_to_hd_button.x = 355
        transfer_to_hd_button.y = 136
        self.notebook_file_util_fixed.put(transfer_to_hd_button, transfer_to_hd_button.x,transfer_to_hd_button.y)

        #Add button to list
        self.button_list.setdefault('transfer_to_hd',transfer_to_hd_button)

        #Store it as a class member to preserve the object
        self.transfer_to_hd_button = transfer_to_hd_button

        # Create and size button
        transfer_to_usb_button = btn.ImageButton('right-arrow.png','transfer_to_usb')
        transfer_to_usb_button.set_size_request(38,69)

        # Copied X / Y coords from old glade file
        transfer_to_usb_button.x = 355
        transfer_to_usb_button.y = 214
        transfer_to_usb_button.disable(1)

        self.notebook_file_util_fixed.put(transfer_to_usb_button, transfer_to_usb_button.x,transfer_to_usb_button.y)

        self.button_list.setdefault('transfer_to_usb',transfer_to_usb_button)
        self.transfer_to_usb_button = transfer_to_usb_button

        # Connect button signals to class functions
        self.transfer_to_hd_button.connect("button_press_event",self.on_button_press_event)
        self.transfer_to_hd_button.connect("button_release_event",self.on_transfer_to_hd_button_release_event)

        self.transfer_to_usb_button.connect("button_press_event",self.on_button_press_event)
        self.transfer_to_usb_button.connect("button_release_event",self.on_transfer_to_usb_button_release_event)

        self.transfer_to_hd_button.disable()
        self.transfer_to_usb_button.disable()

    def reload_gcode_file(self):
        path = self.get_current_gcode_path()
        if not path: return
        self.load_gcode_file(path)
        self.gremlin.set_current_ui_view()
        return False   # must do this as this is scheduled sometimes with glib.idle_add() and without this is will call again


    def add_conversational_page(self, fixed_panel, title):
        """
        Add a page to the conversational notebook with the specified title

        :param fixed_panel: A GTK fixed object containing the conversational page (usually created with its own builder from a seperate file)
        :param title: String title of the conversational tab
        """
        label = gtk.Label()
        label.set_text(title)
        self.conv_notebook.append_page(fixed_panel, label)

    def on_conv_edit_gcode_button_release_event(self, widget, data=None):
        gc = conversational.ConvDecompiler(self.conversational, self.hd_file_chooser.selected_path, self.error_handler)
        job_assignment.JAObj().set_gc(gc)
        job_assignment.JAObj().job_assignment_conv_edit()
        #fixes a problem if return from job assignment
        #then switch to 'notebook_main_fixed', gremlin was not
        # oriented properly...
        self.gremlin_reset = True

    def on_load_gcode_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.chooser_load_gcode()

    def on_hd_file_selection_change(self):
        gc = conversational.ConvDecompiler(self.conversational, self.hd_file_chooser.selected_path, self.error_handler, action='fastscan')
        job_assignment.JAObj().set_gc()
        if any(gc.segments):
            self.button_list['conv_edit'].enable()


    def toggle_gcodewindow_size(self):
        state = self.redis.hget('uistate', 'main_tab_gcodewindow_state')
        if state == 'Expanded':
            self.redis.hset('uistate', 'main_tab_gcodewindow_state', 'Normal')
        else:
            self.redis.hset('uistate', 'main_tab_gcodewindow_state', 'Expanded')

        self._update_size_of_gremlin()


    def on_gcode_sourceview_button_press_event(self, widget, event):
        if event.type == gtk.gdk._2BUTTON_PRESS:
            # double click in the source view toggles the size
            self.toggle_gcodewindow_size()


    def _update_size_of_gremlin(self):

        SHIFT_CX = 278

        state = self.redis.hget('uistate', 'main_tab_gcodewindow_state')

        # if first time in here, the sizes must be the "normal" view from the glade builder so just grab all the
        # original sizes and positions as those for the expanded=False look
        if self.origsize_gremlin == None:
            self.origpos_gremlin = ui_misc.get_xy_pos(self.gremlin)
            sztuple = self.gremlin.get_size_request()
            self.origsize_gremlin = ui_misc.size(sztuple[0], sztuple[1])
            sztuple = self.scrolled_window.get_size_request()
            self.origsize_scrolled_window = ui_misc.size(sztuple[0], sztuple[1])
            sztuple = self.mdi_line.get_size_request()
            self.origsize_mdi_line = ui_misc.size(sztuple[0], sztuple[1])
            sztuple = self.loaded_gcode_filename_evtbox.get_size_request()
            self.origsize_loaded_gcode_filename_evtbox = ui_misc.size(sztuple[0], sztuple[1])
            self.origpos_expandview_button = ui_misc.get_xy_pos(self.expandview_button)
            self.origpos_gcode_options_button = ui_misc.get_xy_pos(self.gcode_options_button)
            sztuple = self.preview_image_overlay.get_size_request()
            self.origsize_preview_image_overlay = ui_misc.size(sztuple[0], sztuple[1])
            self.origpos_preview_image_overlay = ui_misc.get_xy_pos(self.preview_image_overlay)
            sztuple = self.gcode_options_notebook.get_size_request()
            self.origsize_gcode_options_notebook = ui_misc.size(sztuple[0], sztuple[1])

        assert state in ('Expanded', 'Normal')

        if state == 'Expanded':
            # we should expand the view
            # grow, shrink, or just shift over everything relevant by SHIFT_CX
            self.gremlin.set_size_request(self.origsize_gremlin.cx - SHIFT_CX, self.origsize_gremlin.cy)
            self.notebook_main_fixed.move(self.gremlin, self.origpos_gremlin.x + SHIFT_CX, self.origpos_gremlin.y)

            # resize the message line so that it matches the width of the gremlin and position
            self.message_line.set_size_request(self.origsize_gremlin.cx - SHIFT_CX, 35)
            self.notebook_main_fixed.move(self.message_line, self.origpos_gremlin.x + SHIFT_CX, 375)

            self.scrolled_window.set_size_request(self.origsize_scrolled_window.cx + SHIFT_CX, self.origsize_scrolled_window.cy)
            self.loaded_gcode_filename_evtbox.set_size_request(self.origsize_loaded_gcode_filename_evtbox.cx + SHIFT_CX, self.origsize_loaded_gcode_filename_evtbox.cy)

            self.gcode_page_fixed.move(self.gcode_options_button, self.origpos_gcode_options_button.x + SHIFT_CX, self.origpos_gcode_options_button.y)
            self.gcode_options_button.x = self.origpos_gcode_options_button.x + SHIFT_CX
            self.gcode_options_button.y = self.origpos_gcode_options_button.y

            self.gcode_page_fixed.move(self.expandview_button, self.origpos_expandview_button.x + SHIFT_CX, self.origpos_expandview_button.y)
            self.expandview_button.x = self.origpos_expandview_button.x + SHIFT_CX
            self.expandview_button.y = self.origpos_expandview_button.y

            self.preview_image_overlay.set_size_request(self.origsize_preview_image_overlay.cx - SHIFT_CX, self.origsize_preview_image_overlay.cy)
            self.notebook_main_fixed.move(self.preview_image_overlay, self.origpos_preview_image_overlay.x + SHIFT_CX, self.origpos_preview_image_overlay.y)
            # size the video player if it exists to match the preview image overlay widget
            if self.vlcwidget:
                self.vlcwidget.set_size_request(self.origsize_preview_image_overlay.cx - SHIFT_CX, self.origsize_preview_image_overlay.cy)
                self.notebook_main_fixed.move(self.vlcwidget, self.origpos_preview_image_overlay.x + SHIFT_CX, self.origpos_preview_image_overlay.y)

            self.mdi_line.set_size_request(self.origsize_mdi_line.cx + SHIFT_CX, self.origsize_mdi_line.cy)
            self.set_image('expandview_button_image', 'left-chevron.png')

            self.gcode_options_notebook.set_size_request(self.origsize_gcode_options_notebook.cx + SHIFT_CX, self.origsize_gcode_options_notebook.cy)
            self.gremlin_options.set_view_state(state, SHIFT_CX)

        else:
            # we are shrinking the view back to original size
            # we just set everything back to the original locations
            self.gremlin.set_size_request(self.origsize_gremlin.cx, self.origsize_gremlin.cy)
            self.notebook_main_fixed.move(self.gremlin, self.origpos_gremlin.x, self.origpos_gremlin.y)

            # resize the message line so that it matches the width of the gremlin and position
            self.message_line.set_size_request(self.origsize_gremlin.cx, 35)
            self.notebook_main_fixed.move(self.message_line, self.origpos_gremlin.x, 375)

            self.scrolled_window.set_size_request(self.origsize_scrolled_window.cx, self.origsize_scrolled_window.cy)
            self.loaded_gcode_filename_evtbox.set_size_request(self.origsize_loaded_gcode_filename_evtbox.cx, self.origsize_loaded_gcode_filename_evtbox.cy)

            self.gcode_page_fixed.move(self.gcode_options_button, self.origpos_gcode_options_button.x, self.origpos_gcode_options_button.y)
            self.gcode_options_button.x = self.origpos_gcode_options_button.x
            self.gcode_options_button.y = self.origpos_gcode_options_button.y

            self.gcode_page_fixed.move(self.expandview_button, self.origpos_expandview_button.x, self.origpos_expandview_button.y)
            self.expandview_button.x = self.origpos_expandview_button.x
            self.expandview_button.y = self.origpos_expandview_button.y

            self.preview_image_overlay.set_size_request(self.origsize_preview_image_overlay.cx, self.origsize_preview_image_overlay.cy)
            self.notebook_main_fixed.move(self.preview_image_overlay, self.origpos_preview_image_overlay.x, self.origpos_preview_image_overlay.y)
            # size the video player if it exists to match the preview image overlay widget
            if self.vlcwidget:
                self.vlcwidget.set_size_request(self.origsize_preview_image_overlay.cx, self.origsize_preview_image_overlay.cy)
                self.notebook_main_fixed.move(self.vlcwidget, self.origpos_preview_image_overlay.x, self.origpos_preview_image_overlay.y)

            self.mdi_line.set_size_request(self.origsize_mdi_line.cx, self.origsize_mdi_line.cy)
            self.set_image('expandview_button_image', 'right-chevron.png')

            self.gcode_options_notebook.set_size_request(self.origsize_gcode_options_notebook.cx, self.origsize_gcode_options_notebook.cy)
            self.gremlin_options.set_view_state(state, SHIFT_CX)

        # Are we stopped at an M01 break?
        # If so the user may toggle the size while at the break and we need to rescale the image
        # and reload it
        if self.preview_image_overlay.get_visible():
            self.load_and_set_m1_image(self.m01image_pixbuf)


    def on_expandview_button_released(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_gcodewindow_size()


    # called from hd_file_chooser double-click and on_load_gcode_button_release_event
    def chooser_load_gcode(self):
        path = self.hd_file_chooser.selected_path
        if len(path) > 0:
            try:
                basepath, ext = os.path.splitext(path)
                if ext.upper() == ".PDF":
                    self.error_handler.log("File has PDF extension, opening pdf viewer: %s" % path)
                    subprocess.Popen(['openpdf', path])

                elif ext.upper() in (".PNG", ".JPG", ".JPEG"):
                    self.error_handler.log("Image file found based on extension, opening image viewer: %s" % path)
                    subprocess.Popen(['openimage', path])

                elif ext.upper() in (".MP4", ".MOV", ".M4V"):
                    self.error_handler.log("Image file found based on extension, opening image viewer: %s" % path)
                    subprocess.Popen(['openvideo', path])

                elif ext.upper() == ".DXF":
                    self.error_handler.log("File has DXF extension %s" % path)
                    self.load_dxf_file(path)

                elif path.find('/gcode/logfiles/') != -1:   # assume all files in logfiles are text
                    self.error_handler.write("file exists in logfiles path %s" % path, ALARM_LEVEL_DEBUG)
                    subprocess.Popen(['editscript', path])

                elif path.find('/gcode/thread_data/') != -1:   # assume all files in thread_data are text
                    self.error_handler.write("file exists in logfiles path %s" % path, ALARM_LEVEL_DEBUG)
                    subprocess.Popen(['editscript', path])

                # must scan path for '/gcode/media/' and not allow loading from USB stick
                elif path.find('/gcode/media/') != -1:
                    self.error_handler.write('Cannot load G code file from external media - must copy to controller before loading.', ALARM_LEVEL_LOW)

                elif not tormach_file_util.is_plain_text_file(self, path):
                    self.error_handler.write('File %s is not a valid G code text file format' % path, ALARM_LEVEL_LOW)

                else:
                    self.error_handler.write("Loading G code: %s" % path, ALARM_LEVEL_DEBUG)
                    self.last_gcode_program_path = path
                    self.load_gcode_file(self.last_gcode_program_path)

            except OSError:
                self.error_handler.write("OSError exception raised. Could not load or edit file: %s" % path, ALARM_LEVEL_LOW)

            except IOError:
                self.error_handler.write("Path %s is not a valid file" % path, ALARM_LEVEL_DEBUG)


    def on_transfer_to_hd_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.copy_selected_between_choosers(self.usb_file_chooser, self.hd_file_chooser)

    def on_transfer_to_usb_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.copy_selected_between_choosers(self.hd_file_chooser, self.usb_file_chooser)

    # edit selected or else currently loaded gcode file

    def copy_selected_between_choosers(self, src_chooser, dest_chooser):
        """ Copy selection from a source file chooser (typically HDD or USB) to the destination file chooser.
        """
        selected = src_chooser.selected_list

        with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as plexi:
            #Handle file / directory differently for multiple selection
            for p in selected:
                try:
                    if os.path.isfile(p):
                        self.copy_file(plexi.plexiglass, p, dest_chooser.get_current_directory())
                    elif os.path.isdir(p):
                        self.copy_directory(plexi.plexiglass, p, dest_chooser.get_current_directory())
                except OSError as e:
                    # warn about this, but keep going because of the multi-selection
                    self.error_handler.write(str(e), ALARM_LEVEL_LOW)
                except IOError as e:
                    # warn about this, but keep going because of the multi-selection
                    self.error_handler.write(str(e), ALARM_LEVEL_LOW)

            dest_chooser.refresh_free_space_label()


    def setup_filechooser(self):
        """ Create file viewers for HS and USB and associated settings."""

        self.fsclipboard_mgr = fsclipboard.fsclipboard_mgr(self.error_handler)

        # File preview window
        self.file_preview_textview = self.builder.get_object("file_preview_textview")
        self.file_preview_buffer = gtksourceview2.Buffer()
        self.file_preview_textview.set_buffer(self.file_preview_buffer)

        font_description = pango.FontDescription('Roboto Condensed 10')
        self.file_preview_textview.modify_font(font_description)

        # The restricted directory is the highest level the user is allowed to
        # browse to.
        restricted_dir = os.path.join(os.getenv('HOME')) + os.path.sep + 'gcode'
        self.hd_file_chooser = tormach_file_util.hd_file_chooser(
            self.window,
            self.notebook_file_util_fixed,
            self.file_preview_buffer,
            self.settings.touchscreen_enabled,
            self.chooser_load_gcode,
            self.button_list['load_gcode'],
            self.button_list['edit_gcode'],
            self.button_list['conv_edit'],
            self.error_handler,
            self.transfer_to_usb_button,
            self.get_current_gcode_path,
            self.fsclipboard_mgr,
            restricted_dir,
            getattr(self, 'on_hd_file_selection_change', None))

        # Remember where files were last saved to so the user doesn't have to
        # browse every time
        self.last_used_save_as_path = restricted_dir

        self.usb_file_chooser = tormach_file_util.usb_file_chooser(
            self.window,
            self.notebook_file_util_fixed,
            self.file_preview_buffer,
            self.settings.touchscreen_enabled,
            self.load_gcode_file,
            self.button_list['load_gcode'],
            self.button_list['edit_gcode'],
            self.button_list['conv_edit'],
            self.error_handler,
            self.transfer_to_hd_button,
            self.get_current_gcode_path,
            self.fsclipboard_mgr,
            USB_MEDIA_MOUNT_POINT,
            self.usb_mount_unmount_event_callback)


    def usb_mount_unmount_event_callback(self):
        # a usb drive was either mounted or unmounted
        # adjust usb file chooser visibility and hd file chooser size as necessary

        # if there are no USB drives mounted, then don't bother showing us
        disk_name = self.usb_file_chooser.get_usb_disk_name()
        if disk_name == '':
            # there are no usb drives mounted so hide the usb chooser
            self.usb_file_chooser.file_chooser.hide()
            self.usb_file_chooser.clipboard_button.hide()
            self.usb_file_chooser.new_dir_button.hide()
            self.usb_file_chooser.rename_button.hide()
            self.usb_file_chooser.delete_button.hide()
            self.usb_file_chooser.home_button.hide()
            self.usb_file_chooser.back_button.hide()
            self.usb_file_chooser.eject_button.hide()
            self.usb_file_chooser.freespace_label.hide()

            self.transfer_to_hd_button.hide()
            self.transfer_to_usb_button.hide()

            DELTA = 240
            self.file_preview_scrolled_window.set_size_request(220+DELTA, 290)
            self.notebook_file_util_fixed.move(self.file_preview_scrolled_window, 771-DELTA, 55)
            self.notebook_file_util_fixed.move(self.gcode_file_preview_label, 771-DELTA, 20)

            self.hd_file_chooser.file_chooser.set_size_request(330+180, 302)

        else:
            self.usb_file_chooser.file_chooser.show()
            self.usb_file_chooser.clipboard_button.show()
            self.usb_file_chooser.new_dir_button.show()
            self.usb_file_chooser.rename_button.show()
            self.usb_file_chooser.delete_button.show()
            self.usb_file_chooser.home_button.show()
            self.usb_file_chooser.back_button.show()
            self.usb_file_chooser.eject_button.show()
            self.usb_file_chooser.freespace_label.show()

            self.transfer_to_hd_button.show()
            self.transfer_to_usb_button.show()

            self.file_preview_scrolled_window.set_size_request(220, 290)
            self.notebook_file_util_fixed.move(self.file_preview_scrolled_window, 771, 55)
            self.notebook_file_util_fixed.move(self.gcode_file_preview_label, 771, 20)

            self.hd_file_chooser.file_chooser.set_size_request(330, 302)


    def on_loaded_gcode_combobox_changed(self, widget, data=None):
        # gtk sends the 'changed' signal whether the user changes the combo box or the program changes it
        # and the program changes it every time you load a new program
        # prevent loading repeatedly
        if self.combobox_masked:
            return

        model = widget.get_model()
        active_text = widget.get_active()
        path = model[active_text][1]

        # we can't load a new program or clear the current program if we have one running already
        if self.moving():
            self.error_handler.write("Cannot load a g code program while machine is not stopped.")

            self.combobox_masked = True
            current_path = self.get_current_gcode_path()

            # we want to restore the combox box selection to what was previously active, but if
            # there was no program loaded, we need to special case that similiar to clearing the current
            # program
            if current_path is None or current_path == '':
                # sort of a hack here - add a '' name to the top
                # of the list store.  The previous way of doing this
                # caused some wonky gtk behavior.  See issue #660
                sort_file_history(self.file_history_liststore, current_path, None)
                self.file_history_liststore.prepend(['', ''])
                self.is_gcode_program_loaded = False

            self.loaded_gcode_filename_combobox.set_active(0)  # set previous selection in combobox
            self.combobox_masked = False
            return

        self.error_handler.write(('Loading file from recent file drop down: ' + path), ALARM_LEVEL_DEBUG)
        if path == CLEAR_CURRENT_PROGRAM:

            self.use_hal_gcode_timers = False
            self.last_runtime_sec = 0   # we never have an estimate for the empty program

            self.ensure_mode(linuxcnc.MODE_AUTO)
            # <workaround>  #1197:  work around bug where closing
            # program while in metric breaks TLO
            self.status.poll() # need fresh self.status for ensure_mode()
            self.ensure_mode(linuxcnc.MODE_MDI)
            metric = True if self.g21 else False
            self.issue_mdi('G20')
            # </workaround>
            self.command.program_close()
            self.is_gcode_program_loaded = False
            # clean up the temporary copy that we always create and have linuxcnc load
            if os.path.exists(LINUXCNC_GCODE_FILE_PATH):
                os.unlink(LINUXCNC_GCODE_FILE_PATH)

            if metric:
                self.issue_mdi('G21')

            self.gcodelisting_buffer.set_text('')
            self.set_current_gcode_path('')
            # load the empty gcode file from the same directory as the program is running from
            program_dir = os.path.dirname(os.path.abspath(inspect.getsourcefile(self.__class__)))
            emptyfile_fullpath =  os.path.join(program_dir, EMPTY_GCODE_FILENAME)
            self.gremlin.load(emptyfile_fullpath)

            # must set a view to remove the old tool path
            # but default view for mill and lathe is different
            if 'Y' in self.gremlin.get_geometry():
                self.gremlin.set_view_p()
            else:
                self.gremlin.set_view_y()
            self.combobox_masked = True
            # sort of a hack here - add a '' name to the top
            # of the list store.  The previous way of doing this
            # caused some wonky gtk behavior.  See issue #660
            sort_file_history(self.file_history_liststore, path, None)
            self.file_history_liststore.prepend(['', ''])
            self.combobox_masked = False
            self.is_gcode_program_loaded = False

            # force refresh the tool list store as we color code it based on if the tools are used by the program or not
            self.gcode_program_tools_used = []
            self.refresh_tool_liststore(forced_refresh=True)
            self.gremlin_options.show_all_tools()
            self.gremlin.clear_live_plotter()

        else:
            self.load_gcode_file(path)


    def set_current_gcode_path(self, path):
        self.current_gcode_file_path = path
        if path:
            self.conv_edit_gcode_button.enable()
        else:
            self.conv_edit_gcode_button.disable()

    def get_current_gcode_path(self):
        return self.current_gcode_file_path


    def restore_thread_template_files_if_needed(self):
        # the custom files are exposed to the user. while PP is running, they might have deleted them
        # so check for that before trying to get last modified time.
        #
        # at one point in time if these files didn't exist, we created new empty ones. so the files might exist,
        # but 0 bytes.  in that case, restore the templates also.
        if not os.path.isdir(THREAD_BASE_PATH):
            # if this directory doesn't exist shutil.copy2 will fail with an exception
            self.error_handler.write("Creating non-existent directory %s." % THREAD_BASE_PATH, ALARM_LEVEL_LOW)
            os.mkdir(THREAD_BASE_PATH)

        files = (THREAD_DATA_SAE, THREAD_DATA_METRIC, THREAD_DATA_SAE_CUSTOM, THREAD_DATA_METRIC_CUSTOM)
        for ff in files:
            if not os.path.exists(ff) or os.path.getsize(ff) == 0:
                # restore template file
                name = os.path.split(ff)[1]
                template = os.path.join(LINUXCNC_HOME_DIR, name)
                shutil.copy2(template, ff)
                self.error_handler.write("Restoring template file for thread data file {}".format(ff), ALARM_LEVEL_LOW)


    #called from 500ms periodic and reloads customer thread files
    #if we're on "thread tab" and file timestamps changed
    def thread_custom_file_reload_if_changed(self):
        if self.on_thread_tab():
            self.restore_thread_template_files_if_needed()

            if (self.thread_custom_metric_file_mtime != os.stat(THREAD_DATA_METRIC_CUSTOM).st_mtime) or \
               (self.thread_custom_sae_file_mtime != os.stat(THREAD_DATA_SAE_CUSTOM).st_mtime):
                # time stamps are updated by refresh_thread_data_liststores()
                self.refresh_thread_data_liststores()

    # note: this is called from the 500 ms periodic
    def check_for_gcode_program_reload(self):
        if not job_assignment.JobAssignment.is_active:
            try:
                gcode_file_timestamp = os.stat(self.current_gcode_file_path).st_mtime
                if (gcode_file_timestamp != self.gcode_file_mtime) and self.window.has_toplevel_focus():
                    # file has changed on disk, ask user to confirm reload
                    dialog = popupdlg.ok_cancel_popup(self.window, 'File changed on disk.  Reload?', cancel=True, checkbox=False)
                    dialog.run()
                    ok_cancel_response = dialog.response
                    dialog.destroy()
                    # always set old to equal new timestamp
                    self.gcode_file_mtime = gcode_file_timestamp
                    if ok_cancel_response == gtk.RESPONSE_OK :
                        self.load_gcode_file(self.current_gcode_file_path)
                    return True
            except OSError as exception:
                if exception.errno == errno.ENOENT:
                    # don't do anything in this case.  The file is more than likely getting updated over the network by another computer
                    # and it is in the delete/rename time window.  It will probably suddenly appear 'real soon now'.
                    pass
                else:
                    # exception not one expected
                    userpath = fsutil.sanitize_path_for_user_display(self.current_gcode_file_path)
                    self.error_handler.write('gcode file "%s" exception OSError.errno: %d' % (userpath, exception.errno), ALARM_LEVEL_LOW)
                    raise

        return False

    def setup_key_sets(self):
        #MISC stuff to be refactored in the future
        # Crude way to "Mask" keys for jogging based on what's active:
        # Define a master list of jogging keys here, and a mask for each
        # component type that we want to pass through.
        self.jogging_keys = set([gtk.keysyms.Down,
                             gtk.keysyms.Up,
                             gtk.keysyms.Left,
                             gtk.keysyms.Right,
                             gtk.keysyms.Page_Up,
                             gtk.keysyms.Page_Down,
                             gtk.keysyms.period,
                             gtk.keysyms.comma])

        # Masked keys are "passed through", i.e the GUI-level keypress handler will
        # return False if the pressed key is in this list
        self.dro_mask_keys = set([gtk.keysyms.Left,
                                  gtk.keysyms.Right,
                                  gtk.keysyms.period,
                                  gtk.keysyms.comma])

        #Start with basic DRO keys and add history navigation keys
        self.mdi_mask_keys = set([gtk.keysyms.Left,
                                  gtk.keysyms.Right,
                                  gtk.keysyms.Up,
                                  gtk.keysyms.Down,
                                  gtk.keysyms.period,
                                  gtk.keysyms.comma])

        self.tool_descript_keys = set([gtk.keysyms.Right,
                                       gtk.keysyms.Left,
                                       gtk.keysyms.Up,
                                       gtk.keysyms.Down,
                                       gtk.keysyms.period,
                                       gtk.keysyms.comma,
                                       gtk.keysyms.Escape])

        #Need to be able to navigate file viewer naturally
        self.file_viewer_mask_keys = set([
            gtk.keysyms.Down,
            gtk.keysyms.Up,
            gtk.keysyms.Left,
            gtk.keysyms.Right,
            gtk.keysyms.Page_Up,
            gtk.keysyms.Page_Down,
        ])

        #Jogging is disallowed on any page in this set.
        # However, keys in this dict are passed through
        self.disable_jog_page_ids = set([
            'notebook_file_util_fixed',
            "notebook_settings_fixed",
            "conversational_fixed",
            "alarms_fixed",
        ])

        # Define mask keys for various generic types like Entry boxes (DROs)
        # and Icon viewer boxes
        self.key_mask = {
            type(gtk.Entry()):      self.dro_mask_keys,
            type(gtk.IconView()):   self.file_viewer_mask_keys,
            type(gtk.TreeView()):   self.file_viewer_mask_keys,
        }



        # Store a local state for each jogging key, so that we know if the key
        # is currently pressed or released
        self.jogging_key_pressed = dict((key,False) for key in self.jogging_keys)
        self.jogging_rapid = False


    def screen_grab(self):
        """ capture UI screen.
        screen shot PNG files are put in ~gcode/logfiles directory
        Important! For the Print Screen key stroke to make it here to the app
        it must first be ignored by the system handler
        For Ubuntu, go to Systems->Preferences->Keyboard Shortcuts
        Under Desktop change "Take a screenshot" from "Print" to disabled
        """
        # get gdk window of main gtk window
        window = self.window.window
        window_size = window.get_size()
        pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, window_size[0], window_size[1])
        pixbuf = pixbuf.get_from_drawable(window, window.get_colormap(), 0, 0, 0, 0, window_size[0], window_size[1])
        if (pixbuf != None):
            # put file in ~/gcode/logfiles directory
            screenshot_max = 0
            # find the highest numbered file and use the next in sequence
            for name in glob.glob(SCREENSHOT_BASE_PATH + os.path.sep + 'screenshot-*.png'):
                # find highest numbered screenshot file name
                (ignore, rest) = name.split('-', 1)
                (numstr, ignore) = rest.split('.', 1)
                try:
                    num = int(numstr)
                    if num > screenshot_max:
                        screenshot_max = num
                except:
                    pass
            ss_filename = SCREENSHOT_BASE_PATH + os.path.sep + 'screenshot-' + str(screenshot_max + 1) + '.png'
            pixbuf.save(ss_filename, "png")
            sanitized_path = fsutil.sanitize_path_for_user_display(ss_filename)
            self.error_handler.write("Screen shot saved to %s" % sanitized_path, errors.ALARM_LEVEL_QUIET)
        else:
            self.error_handler.write("Unable to make screen shot.", errors.ALARM_LEVEL_LOW)

        return True


    def refresh_usbio_interface(self):
        # attempting to refresh the usbio interface when the machine is not ok
        # will hang.  usually this bites you at exit time because you've punched
        # the big red e-stop button, which takes you to the alarm page, and then
        # you click exit ==> GORK
        if self.hal['machine-ok'] and self.settings.usbio_enabled:
            # which inputs and outputs we query depends on which USBIO board is selected.
            usbio_input_list = []
            usbio_output_list = []
            for ii in range(4):
                halpin = "usbio-input-{:d}".format(self.usbio_boardid_selected * 4 + ii)
                usbio_input_list.append(self.hal[halpin])
                halpin = "usbio-output-{:d}".format(self.usbio_boardid_selected * 4 + ii)
                usbio_output_list.append(self.hal[halpin])

            usbio_output_on_image_list = ['USBOUT1Green.png','USBOUT2Green.png','USBOUT3Green.png','USBOUT4Green.png']
            usbio_output_off_image_list = ['USBOUT1.png','USBOUT2.png','USBOUT3.png','USBOUT4.png']

            for index, usb_input in enumerate(usbio_input_list):
                self.set_indicator_led(self.usbio_input_image_list[index],usb_input)

            for index, usb_output in enumerate(usbio_output_list):
                if usb_output:
                    self.set_image(self.usbio_output_image_list[index],usbio_output_on_image_list[index])
                else:
                    self.set_image(self.usbio_output_image_list[index],usbio_output_off_image_list[index])


    def show_usbio_interface(self):
        for led in self.usbio_input_image_list:
            self.image_list[led].show()

        for button in self.usbio_output_eventbox_list:
            self.button_list[button].show()

        self.builder.get_object('usbio_selector_text').show()
        self.builder.get_object('usbio_board_selector_combobox').show()
        self.builder.get_object('usbio_board_selector_combobox_evtbox').show()
        self.builder.get_object('usbio_inputs_text').show()
        self.builder.get_object('usbio_outputs_text').show()


    def hide_usbio_interface(self):
        for led in self.usbio_input_image_list:
            self.image_list[led].hide()
            # this makes sure that later show_all() methods don't end up overriding our state and revealing the checkbox
            self.image_list[led].set_no_show_all(True)

        for led in self.usbio_output_eventbox_list:
            self.button_list[led].hide()
            # this makes sure that later show_all() methods don't end up overriding our state and revealing the checkbox
            self.button_list[led].set_no_show_all(True)

        self.builder.get_object('usbio_inputs_text').hide()
        # this makes sure that later show_all() methods don't end up overriding our state and revealing the checkbox
        self.builder.get_object('usbio_inputs_text').set_no_show_all(True)

        self.builder.get_object('usbio_outputs_text').hide()
        # this makes sure that later show_all() methods don't end up overriding our state and revealing the checkbox
        self.builder.get_object('usbio_outputs_text').set_no_show_all(True)

        self.builder.get_object('usbio_selector_text').hide()
        self.builder.get_object('usbio_selector_text').set_no_show_all(True)
        self.builder.get_object('usbio_board_selector_combobox').hide()
        self.builder.get_object('usbio_board_selector_combobox').set_no_show_all(True)
        self.builder.get_object('usbio_board_selector_combobox_evtbox').hide()
        self.builder.get_object('usbio_board_selector_combobox_evtbox').set_no_show_all(True)


    def set_indicator_led(self,led_name,state):
        if state:
            self.set_image(led_name,'LED-Green.png')
        else:
            self.set_image(led_name,'LED-Black.png')


    def set_warning_led(self,led_name,state):
        if state:
            self.set_image(led_name,'LED-Yellow.png')
        else:
            self.set_image(led_name,'LED-Black.png')


    def set_error_led(self,led_name,state):
        if state:
            self.set_image(led_name,'LED-Red.png')
        else:
            self.set_image(led_name,'LED-Black.png')


    """
        color: black, green, blue, yellow
    """
    def set_color_led(self,led_name,color):
        if color=='yellow':
            self.set_image(led_name,'LED-Yellow.png')
        elif color=='black':
            self.set_image(led_name,'LED-Black.png')
        elif color=='blue':
            self.set_image(led_name,'LED-Blue.png')
        elif color=='green':
            self.set_image(led_name,'LED-Green.png')
        else:
            self.error_handler.log("Tried to set a LED ({}) to a color that is not available ({}).".format(led_name, color))



    # Standard file handling functions
    def generate_gcode(self):
        """ Placeholder for functions in mill / lathe that create G code for conversational programs"""
        pass

    def post_to_file(self, parentwindow, title, gcode_output_list, query=True, load_file=True, closewithoutsavebutton=False, overwrite_ok=False):
        ncfile = conversational.nc_file(title)
        ret_file_name = str(ncfile)
        path = os.path.join(self.last_used_save_as_path, ret_file_name)
        user_nc_file = conversational.nc_file(os.path.split(path)[1])
        response = gtk.RESPONSE_OK
        ret_path = path
        if query:
            with tormach_file_util.file_save_as_popup(parentwindow, 'Choose a g-code file name.', path, '.nc', self.settings.touchscreen_enabled,
                                                      usbbutton=False, closewithoutsavebutton=closewithoutsavebutton) as dialog:
                # Get information from dialog popup
                response = dialog.response
                if response == gtk.RESPONSE_OK:
                    path = dialog.path
                    user_nc_file = conversational.nc_file(os.path.split(path)[1])
                    self.last_used_save_as_path = ret_path = dialog.current_directory

        if response != gtk.RESPONSE_OK:
            return (response,None,None)

        # check to see if we're going to overwrite an existing file
        if not overwrite_ok and os.path.exists(path):
            with popupdlg.confirm_file_overwrite_popup(parentwindow, path, self.settings.touchscreen_enabled) as popup:
                new_path = popup.path
                response = popup.response

            if new_path == '':
                return (response,None,None)
            if new_path != path: user_nc_file = conversational.nc_file(os.path.split(path)[1])
            path = new_path

        # open/create file, write g code, close file
        with open(path, "w") as ngc_file:
            if ngc_file:
                for ngc_line in gcode_output_list:
                    #FIXME this should probably be unix-style line ends instead of windows
                    ngc_file.write(ngc_line + '\r\n')
                # Add a final line to terminate the program
                ngc_file.write('\r\n')
            else:
                return (gtk.RESPONSE_OK,ret_path,str(user_nc_file))
        if load_file: self.load_gcode_file(path)
        return (gtk.RESPONSE_OK,ret_path,str(user_nc_file))


    # Helper functions for G code lines

    @classmethod
    def gcode_list_to_tmp_file(cls, gcode_list=['']):
        if cls._ja_tmp_filepath:
            os.remove(cls._ja_tmp_filepath)
            cls._ja_tmp_filepath = None

        tmpfile = tempfile.NamedTemporaryFile(mode='w', prefix='ja_', delete=False)
        cls._ja_tmp_filepath = tmpfile.name
        try:
            for ngc_line in gcode_list:
                tmpfile.write(ngc_line + '\r\n')
            tmpfile.write('\r\n')
            # we leave the temp file object open so it doesn't get auto-deleted.
            # caller can open the file using the path.  it gets closed above on a new file
            # or in quit() and automatically cleaned up.
            return tmpfile.name
        except IOError:
            print 'TormachUIBase.gcode_list_to_tmp_file: IOError has occured'
        except:
            print 'TormachUIBase.gcode_list_to_tmp_file: error has occured'
        finally:
            tmpfile.close()

        return None

    def set_start_line(self, start_line = None):
        """the popup calls this if it's selected from the popup via the 'activate' signal
        """
        inserted_mark = self.gcodelisting_buffer.get_insert()
        text_iter = self.gcodelisting_buffer.get_iter_at_mark(inserted_mark)

        if start_line is None:
            self.gcode_start_line = text_iter.get_line() + 1
        else:
            self.gcode_start_line = start_line

        if self.gcode_start_line <= 1:
            # we're starting from the beginning so any estimated run time we have is valid
            self.last_runtime_sec = self.stats_mgr.get_last_runtime_sec()
        else:
            # not possible to estimate the remaining runtime so set it to 0 which ends up hiding the clock
            self.last_runtime_sec = 0

        self.error_handler.log("Start line set to {:d}".format(self.gcode_start_line))

        # starting line should be marked
        self.update_mark(self.gcodelisting_start_mark, self.gcode_start_line, True)

    def update_gcode_display(self):
        """ Periodic update function for the g code window. The highlighting
        marks are advanced as needed to keep up with the program."""

        current_line = self.status.current_line
        if not self.program_running() and self.current_gcode_file_path:
            # Shows the user's selected line in the gremlin toolpath when the program is
            # not running.
            if self.gremlin.get_highlight_line():
                current_line = self.gremlin.get_highlight_line()

        self.gcodelisting_mark_start_line()

        line_changed = self.gcodelisting_mark_current_line(current_line)

        stopped = self.status.current_vel < 1e-9 and \
                  not self.status.exec_state == linuxcnc.EXEC_WAITING_FOR_DELAY

        # Only scroll if sourceview events are not masked
        if line_changed and not self.sourceview.masked:
            if stopped or not self.scrolled_window.get_vscrollbar().has_focus():
                self.sourceview.scroll_to_mark(self.gcodelisting_current_mark, 0, True, 0, 0.5)


    def update_mark(self, mark, line, always=False):
        """Update the position of a given marker in the G code window.
         Giving 0 for the line argument hides the marker.
         NOTE: the line argument is 1-indexed, so the first line in a program is line #1
         """
        old_line = self.gcodelisting_buffer.get_iter_at_mark(mark).get_line()
        newline = max(line - 1, 0)
        if old_line != newline or always:
            #Line is different, do an update
            line_iter = self.gcodelisting_buffer.get_iter_at_line(newline)
            self.gcodelisting_buffer.move_mark(mark, line_iter)
            return True
        return False

    def gcodelisting_mark_start_line(self, start_line=None, blank=False):
        """ In the G Code window, set the starting line."""
        if start_line:
            self.gcode_start_line = start_line
        line_changed = self.update_mark(self.gcodelisting_start_mark, self.gcode_start_line, always=True)
        if blank or (self.gcode_start_line == 0) or not self.current_gcode_file_path:
            self.sourceview.set_mark_category_background('start', self.mark_colors['blank'])
        else:
            self.sourceview.set_mark_category_background('start', self.mark_colors['start'])
        return line_changed

    def gcodelisting_mark_current_line(self, current_line, blank=False):
        """ In the G Code window, set the mark indicating the currently executing line, or the next line if the current one is done and
            we are single blocking. """
        line_changed = self.update_mark(self.gcodelisting_current_mark, current_line)
        if blank or current_line == 0:
            self.sourceview.set_mark_category_background('current', self.mark_colors['blank'])
        else:
            self.sourceview.set_mark_category_background('current', self.mark_colors['current'])
        return line_changed

    def enable_home_switch(self, axis_index, enable_flag):
        self.error_handler.write('enable home axis %d, flag %d' % (axis_index, enable_flag), ALARM_LEVEL_DEBUG)
        # if enable_flag is False sets home_offset, search velocity and latch velocity to 0.0
        # else sets all to INI file values
        # 0 for X, 1 for Y, 2 for Z
        axis_N = 'AXIS_{:d}'.format(axis_index)
        if axis_index > 2:
            self.error_handler.write("invalid axis index '%d' for enable_home_switch()" % axis_index, ALARM_LEVEL_LOW)
            return

        if enable_flag:
            home = self.ini_float(axis_N, "HOME", 0.0)
            home_offset = self.ini_float(axis_N, "HOME_OFFSET", 0.0)
            home_search_vel = self.ini_float(axis_N, "HOME_SEARCH_VEL", 0.0)
            home_latch_vel = self.ini_float(axis_N, "HOME_LATCH_VEL", 0.0)
        else:
            home = 0.0
            home_offset = 0.0
            home_search_vel = 0.0
            home_latch_vel = 0.0
        home_final_vel = self.ini_float(axis_N, "HOME_FINAL_VEL", -1)
        home_use_index = self.ini_flag(axis_N, "HOME_USE_INDEX", False)
        home_ignore_limits = self.ini_flag(axis_N, "HOME_IGNORE_LIMITS", False)
        home_home_is_shared = self.ini_flag(axis_N, "HOME_IS_SHARED", 0)
        home_sequence = self.ini_flag(axis_N, "HOME_SEQUENCE", 0)
        volatile_home = self.ini_flag(axis_N, "VOLATILE_HOME", 0)
        locking_indexer = self.ini_flag(axis_N, "LOCKING_INDEXER", 0)

        self.command.set_homing_params(axis_index, home, home_offset, home_final_vel, home_search_vel,
                                       home_latch_vel, home_use_index, home_ignore_limits,
                                       home_home_is_shared, home_sequence, volatile_home,
                                       locking_indexer)


    # Motor commands shared between machines
    def axis_motor_command(self, axis_index, command):
        if axis_index > 2:
            # we don't need any motor commands to reference the 4th axis
            return

        self.ensure_mode(linuxcnc.MODE_MANUAL)

        axis_dict = {0:'x', 1:'y', 2:'z'}
        axis_letter = axis_dict[axis_index]

        self.hal[axis_letter + '-motor-command'] = command

        # only need to wait for these two commands, otherwise axis_motor_poll will pick up errors
        if command == MOTOR_CMD_NORMAL or command == MOTOR_CMD_HOME:
            self.messageFault[axis_index] = False #clear possible existing message error flag

            timeout = time.clock() + .15 #monotonic() would be better, but that's version 3 python

            while True:  #loop until timeout or motor leaves MS_WAIT state
                time.sleep(.01) #CPM motors require toggle of enable in the 10mS range
                motorState = self.hal[axis_letter + '-motor-state']
                mfb = self.hal[axis_letter + '-status-code']
                if motorState != MS_WAIT:
                    break
                if timeout < time.clock(): # if we timed out
                    break

            self.axis_motor_poll(axis_index) #This handles error conditions, if any

        mfb = self.hal[axis_letter + '-status-code']

        axis_N = "AXIS_{}".format(axis_index)

        # bounce MX axis motor out of homing mode with a few steps each direction
        # unfortunately there's no "do one step" option available from linuxcnc
        if self.machineconfig.has_hard_stop_homing() and (mfb == MFB_OK and command == MOTOR_CMD_NORMAL):
            self.ensure_mode(linuxcnc.MODE_MANUAL)
            self.command.jog(linuxcnc.JOG_INCREMENT, axis_index, 1.5, .0001)
            self.command.jog(linuxcnc.JOG_INCREMENT, axis_index, -1.5, .0001)

    def axis_motor_error_msg(self, axis_name, error_code):
        axis_lib = {'x':0, 'y':1, 'z':2}
        axis_index = axis_lib[axis_name]
        msglevel = ALARM_LEVEL_MEDIUM
        msg = None
        if error_code == MFB_CMD_INVALID:
            msg = "motor axis %s received unexpected command. It was ignored." % (axis_name)
        elif error_code == MFB_POSITION:
            if not self.estop_alarm:
                # 0: none, 1: rapid, 2: feed, 3: arc, 4: tool change, 5: probing, 6: rotary unlock
                msglevel = ALARM_LEVEL_DEBUG
                motion_type = self.hal['motion-motion-type']
                msg = "info: motor axis %s reports temporary MFB condition, motion type: %d" % (axis_name, motion_type)
        elif error_code == MFB_CMD_UNKNOWN:
            msg = "motor axis %s received unknown command. It was ignored." % (axis_name)
        elif error_code == MFB_FAULT: #as this fault "sticks" we need to prevent repeated calling from 50 ms loop
            if not self.messageFault[axis_index] and not self.estop_alarm and self.hal['machine-ok'] == True: # with the messageFault flag.  Is cleared on user RESET
                msg = "motor axis %s has faulted" % (axis_name)
                self.messageFault[axis_index] = True
        else:
            msg = "unknown error axis %s code %d" % (axis_name, error_code)
        if msg != None:
            self.error_handler.write(msg, msglevel)

    def not_homed(self,axis_index):
        if axis_index == 0 and not self.x_referenced:
            return True
        elif axis_index == 1 and not self.y_referenced:
            return True
        elif axis_index == 2 and not self.z_referenced:
            return True
        elif axis_index == 3 and not self.a_referenced:
            return True
        return False


#estop_alarm that means someone pressed estop this is not necessary
    def halt_world(self, called_from_vfd = False):

        if (not self.halt_world_flag and called_from_vfd == True) or (not self.halt_world_flag and not self.estop_alarm and self.hal['machine-ok'] == True):
        #  depending on timing, estop_alarm() and machine-ok may prevent unhoming of machine when called by check_spindle_fault()
        # we should prevent halt_world() from being called from the caller, not devine what's really goin on here
        # we call halt_world from SLP
        #another estop indicator.  Prevents bogus halt_world if user didn't hit "RESET" button (GO) on physical EStop, then pressed PP softare "Reset" button
            self.halt_world_flag = True #do this only once per reset button press -- gets called repeatedly from 50mS loop when axis faults
            self.hal['pp-estop-fault'] = 1
            self.command.state(linuxcnc.STATE_ESTOP) #halt the world - put machine into ESTOP state, abort all motion, etc.
            self.command.wait_complete()  #prevents firing multiple STATE_ESTOPS
            self.command.unhome(0)
            self.command.unhome(1)
            self.command.unhome(2)
            self.x_referenced = self.y_referenced = self.z_referenced = self.a_referenced = False
            self.status.poll() #refresh status info
            self.error_handler.write("software ESTOP triggered", ALARM_LEVEL_MEDIUM)

    #called from the 50mS periodic loop with no specific_axis parameter.  this will force scan of all 3 axes
    #when called from axis_motor_command() with specific axis it will only look at the given axis
    def axis_motor_poll(self, specific_axis = POLL_ALL_AXES):
        axes = ['x','y','z'] # presently we're not doing CPM on 4th axis (see 'z' below to exit loop)

        if specific_axis == POLL_ALL_AXES:
            next_axis = 0;  #start looping all from 0
        else:
            next_axis = specific_axis

        while True: # a do-while loop that python lacks would help here

            axis_index = next_axis
            axis_letter = axes[axis_index]
            #for axis in axes:
            status_code = self.hal[axis_letter + '-status-code']
            motor_state = self.hal[axis_letter + '-motor-state']

            if motor_state == MS_FAULT:
                # TODO: fix this call!  See notes in halt_world()
                self.halt_world()
                self.axis_motor_error_msg(axis_letter, MFB_FAULT)
            elif motor_state == MS_HOME_COMPLETE:
                self.axis_motor_command(axis_index, MOTOR_CMD_ACK_HOME)
            #we don't care about these motor states, but included here as future reminder in case
            #MS_DISABLED MS_NORMAL MS_WAIT MS_HOME_WAITING MS_HOME_SEARCHING

            #check motor_status status_codes (aka "error codes")
            #and also deal with some hand shaking (acknowledgements) to motor component messages
            #note we took care of MFB_FAULT above with MS_FAULT above no need to repeat below
            #we also don't need to keep track of acknowledgements as they are cleared at the motor comp level

            #MFB_POSITION only happens from MX series machines, so no need to check "MX" here
            if status_code == MFB_POSITION:
                #if not homed yet and we're not in process of homing, promote position errors to halt machine
                #this is because the user is likely running the axis into end of travel, and position errors
                #are very unlikely at the limited speed available prior to homing, so this promotion prevents
                #sticking of axis, as it reduces time to halting motion
                if self.not_homed(axis_index) and not self.status.axis[axis_index]['homing']:
                    self.halt_world()
                self.axis_motor_error_msg(axis_letter, status_code) #report position errors
                self.axis_motor_command(axis_index,MOTOR_CMD_ACK_POS) #<ACK> motor comp we saw position error
            elif status_code == MFB_CMD_INVALID or status_code == MFB_CMD_UNKNOWN or status_code > MFB_FAULT:
                self.axis_motor_error_msg(axis_letter, status_code)
                self.axis_motor_command(axis_index,MOTOR_CMD_ACK_ERR)
            if axis_letter == 'z' or specific_axis != POLL_ALL_AXES:  #completed looping at last axis or did we just finish a single given axis?
                break; #leave do while loop
            next_axis += 1 #check next





    # Common functions for machine status

    def moving(self):
        # is machine moving (could be MDI, program executing, etc.)
        if self.status.state == linuxcnc.RCS_EXEC:
            return True
        else:
            return self.status.task_mode == linuxcnc.MODE_AUTO and self.status.interp_state != linuxcnc.INTERP_IDLE

    def wait_interp_idle(self):
        for loop_count in xrange(0, 99):
            self.status.poll()
            if self.status.interp_state == linuxcnc.INTERP_IDLE:
                return
            time.sleep(0.050)

        # timeout expired
        self.error_handler.write("Timeout waiting for interpreter to be idle", ALARM_LEVEL_LOW)

    def _get_title_data(self,page_id):
        key = ''
        value = ''
        try:
            kv_data = self.conversational.title_data[page_id]
            for n in range(9):
                ref = 'ref' + str(n)
                if ref in kv_data:
                    k,v = kv_data[getattr(self,kv_data[ref])]
                    key +=   k if k is not None else key
                    value += v if v is not None else ''
                else:
                    break
        except Exception as e:
            self.error_handler.write('ui._get_title_data failed: {}'.format(str(e)), ALARM_LEVEL_LOW)
        return (key,value)

    def save_title_dro(self):
        page_id = self.get_current_conv_notebook_page_id()
        key,value = self._get_title_data(page_id)
        dro_text = self.conv_dro_list['conv_title_dro'].get_text()
        if not dro_text: dro_text = value
        if key: self.redis.hset('machine_prefs',key,dro_text)
        return (key,value)

    def load_title_dro(self, page_id=None):
        if not page_id: page_id = self.get_current_conv_notebook_page_id()
        key,value = self._get_title_data(page_id)
        if not self.redis.hexists('machine_prefs',key):
            self.redis.hset('machine_prefs',key,value)
        else:
            value = self.redis.hget('machine_prefs',key)
        self.conv_dro_list['conv_title_dro'].set_text(value)
        return (key,value)


    def locate_m1_image(self, maybe_fname, lineno):
        # Look in `.`, `./images` and `gcode/images` for an image file
        # named `maybe_fname`
        # return a list of candidate file paths that exist

        search_path = [ os.path.dirname(self.current_gcode_file_path),
                        os.path.join(os.path.dirname(self.current_gcode_file_path), 'images'),
                        IMAGES_BASE_PATH ]

        search_paths_for_user = ['Home']

        candidates = []

        for path in search_path:
            # Compute file path and check if it exists
            fpath = os.path.join(path, maybe_fname)

            # Trim off the complete path so not to confuse the user when this is shown to them.
            trimmedpath = path[len(GCODE_BASE_PATH):]
            if len(trimmedpath) > 0 and trimmedpath not in search_paths_for_user:
                search_paths_for_user.append(trimmedpath)

            if not os.path.exists(fpath):
                continue

            candidates.append(fpath)

        if len(candidates) == 0:
            # The user probably is struggling with lowercase / uppercase issues.
            # Help them out by giving them info on the Status tab.  But for others it apparently
            # is annoying so try to suppress it unless we match.
            extensions = [ '.PNG', '.JPG', '.JPEG', '.MP4', '.MOV' ]
            maybe_fname_upper = maybe_fname.upper()
            for ext in extensions:
                if string.find(maybe_fname_upper, ext) != -1:
                    warning = "Warning: line {} M00/M01 comment '{}' did not match any image filename in the following folders (careful for case sensitivity); displaying comment over the tool path preview of main tab instead.".format(lineno, maybe_fname)
                    for p in search_paths_for_user:
                        warning += "\n        " + p
                    self.error_handler.write(warning, ALARM_LEVEL_QUIET)
                    break

        return candidates


    def get_pixbuf_for_m1_image(self, fname):
        try:
            p = gtk.gdk.pixbuf_new_from_file(fname)
            self.error_handler.log("Showing M00/M01 image: '%s'" % fname)
            return p
        except glib.GError as e:
            # Give the user a clue we really tried, but something horrible happened with the file.
            self.error_handler.write("Error loading image file %s : %s" % (fname, str(e)), ALARM_LEVEL_LOW)
            return None


    def load_and_set_m1_image(self, pixbuf):
        p = pixbuf
        if p is not None:
            sz = self.gremlin.get_size_request()
            gremlinsize = ui_misc.size(sz[0], sz[1])

            # Resulting pixbuf is the size of gremlin and filled with black
            scaled_p = gtk.gdk.Pixbuf(
                gtk.gdk.COLORSPACE_RGB, False, 8,
                gremlinsize.cx, gremlinsize.cy)
            scaled_p.fill(0x00000000)

            # Scale image proportionally into resulting pixbuf,
            # centered left/right
            scale = min(gremlinsize.cx / float(p.get_width()),
                        gremlinsize.cy / float(p.get_height()))
            scaled_width = int(p.get_width() * scale)
            scaled_height = int(p.get_height() * scale)
            offset = int((gremlinsize.cx - p.get_width()*scale)/2)

            # I created some png files with various options in gimp and could easily create
            # files that would throw an exception inside the scale() method because the source pixbuf
            # has an alpha channel and the dest pixbuf did not.  Seems like the composite() method gets
            # around this and the dest pixbuf is already filled with black anyway.
            # Might be able to use composite() method all the time, but this is more conservative.

            try:
                if p.get_has_alpha():
                    p.composite(
                        scaled_p,
                        offset, 0, scaled_width, scaled_height,
                        offset, 0, scale, scale,
                        gtk.gdk.INTERP_BILINEAR, 255)
                else:
                    p.scale(
                        scaled_p,
                        offset, 0, scaled_width, scaled_height,
                        offset, 0, scale, scale,
                        gtk.gdk.INTERP_BILINEAR)

                # Stick the pixbuf into the image, and make the image visible
                self.preview_image_overlay.set_from_pixbuf(scaled_p)

            except Exception as ex:
                # Give the user a clue we really tried, but something horrible happened with the file.
                self.error_handler.write("Unxpected error attemping to display image file: %s" % str(ex), ALARM_LEVEL_LOW)


    def on_video_togglefullscreen_button_release(self, widget, data=None):
        if self.vlcwidget:

            # save current position in milliseconds in the video
            # and state of transport (play/pause)
            position_ms = self.vlcwidget.player.get_time()
            was_playing = self.vlcwidget.player.is_playing()

            self.vlcwidget.player.stop()
            self.vlcwidget.hide()

            if self.video_fullscreen:
                # restore to just over the toolpath
                self.fixed.remove(self.vlcwidget)
                self.fixed.remove(self.video_toolbar_fixed)
                self.video_toolbar_fixed.remove(self.togglefullscreen_button)
                self.video_toolbar_fixed.remove(self.playstop_button)
                self.video_toolbar_fixed.destroy()
                self.video_toolbar_fixed = None

                # size the player to match the preview image overlay widget.
                sztuple = self.preview_image_overlay.get_size_request()
                self.vlcwidget.set_size_request(sztuple[0], sztuple[1])
                pt = ui_misc.get_xy_pos(self.preview_image_overlay)
                self.notebook_main_fixed.put(self.vlcwidget, pt.x, pt.y)

                self.togglefullscreen_button.x = self.togglefullscreen_button._orig_x = self.togglefullscreen_button_orig_pos.x
                self.togglefullscreen_button.y = self.togglefullscreen_button._orig_y = self.togglefullscreen_button_orig_pos.y
                self.playstop_button.x = self.playstop_button._orig_x = self.playstop_button_orig_pos.x
                self.playstop_button.y = self.playstop_button._orig_y = self.playstop_button_orig_pos.y

                self.togglefullscreen_button.load_image('video-fullscreen.png')
                self.togglefullscreen_button.show_all()

                self.fixed.put(self.togglefullscreen_button, self.togglefullscreen_button.x, self.togglefullscreen_button.y)
                self.fixed.put(self.playstop_button, self.playstop_button.x, self.playstop_button.y)

                # Argggg - I can't get the gtk.fixed to respect z-order even with my workaround of removing widgets and
                # adding them with 'last wins'.  So here's a hack for lathe to stop these two dros from leaking into
                # the toolbar area.
                if 'spindle_rpm_dro' in self.dro_list:
                    self.dro_list['spindle_rpm_dro'].show()
                if 'spindle_css_dro' in self.dro_list:
                    self.dro_list['spindle_css_dro'].show()

            else:
                # switch to full screen
                self.video_toolbar_fixed = gtk.Fixed()
                self.video_toolbar_fixed.set_size_request(1024, 768)
                background = gtk.Image()
                background.set_from_file(os.path.join(GLADE_DIR, 'dark_background.jpg'))
                self.video_toolbar_fixed.put(background, 0, 0)

                # save button pos for restoring from full screen
                self.togglefullscreen_button_orig_pos = ui_misc.get_xy_pos(self.togglefullscreen_button)
                self.playstop_button_orig_pos = ui_misc.get_xy_pos(self.playstop_button)
                self.fixed.remove(self.togglefullscreen_button)
                self.fixed.remove(self.playstop_button)

                self.notebook_main_fixed.remove(self.vlcwidget)
                self.vlcwidget.set_size_request(1024, 768 - 29)

                self.video_toolbar_fixed.show_all()

                lastX = (1024/2) - ((29+10+29)/2)
                self.togglefullscreen_button.x = self.togglefullscreen_button._orig_x = lastX
                self.togglefullscreen_button.y = self.togglefullscreen_button._orig_y = 768-29
                self.playstop_button.x = self.playstop_button._orig_x = lastX + 29 + 10
                self.playstop_button.y = self.playstop_button._orig_y = self.togglefullscreen_button.y

                self.togglefullscreen_button.load_image('video-normalscreen.png')
                self.togglefullscreen_button.show_all()

                self.video_toolbar_fixed.put(self.togglefullscreen_button, self.togglefullscreen_button.x, self.togglefullscreen_button.y)
                self.video_toolbar_fixed.put(self.playstop_button, self.playstop_button.x, self.playstop_button.y)

                # Argggg - I can't get the gtk.fixed to respect z-order even with my workaround of removing widgets and
                # adding them with 'last wins'.  So here's a hack for lathe to stop these two dros from leaking into
                # the toolbar area.
                if 'spindle_rpm_dro' in self.dro_list:
                    self.dro_list['spindle_rpm_dro'].hide()
                if 'spindle_css_dro' in self.dro_list:
                    self.dro_list['spindle_css_dro'].hide()

                # order is important for z-order
                self.fixed.put(self.video_toolbar_fixed, 0, 0)
                self.fixed.put(self.vlcwidget, 0, 0)

            self.vlcwidget.show_all()

            # we have to start playback so that we can restore the time position
            # regardless of previous state
            self.vlcwidget.player.play()

            # now seek back to where the video was, but back up just a smidge for continuity
            # because you can probably only seek to an I frame in the video gop sequence
            # and 50 milliseconds will definitely have an I frame in it.
            # Tried simply pausing during this switch and using set_time, but it doesn't work.
            position_ms = max(0, position_ms - 50)
            self.vlcwidget.player.set_time(position_ms)

            # now we can restore the state
            if not was_playing:
                # sigh - can't pause immediately here or its ignored
                # theory is it has to be greater than the 50ms above - this worked fine
                # in testing.
                time.sleep(0.1)
                self.vlcwidget.player.pause()

            self.video_fullscreen = not self.video_fullscreen


    def on_playstop_button_release(self, widget, data=None):
        if self.vlcwidget:
            if self.vlcwidget.player.is_playing():
                # we are transitioning from play -> pause so the button needs to be the play button
                self.playstop_button.load_image('video-play.png')
            else:
                # we are transitioning from pause -> play so the button needs to be the pause button
                self.playstop_button.load_image('video-pause.png')

            self.vlcwidget.player.pause()  # despite the name this actually toggles pause/play behavior
            self.playstop_button.show_all()


    def on_vlcwidget_button_release(self, widget, data=None):
        if self.vlcwidget:
            self.vlcwidget.player.stop()
        self.hide_m1_image()


    def show_m1_image(self):
        # If program pauses at a block like `M01 (myimg.jpg)`, if that
        # file exists in the `gcode/images` directory, scale and
        # temporarily display it in place of gremlin

        # Detect and parse block like `M01 (myimg.jpg)`
        lineno = self.status.current_line
        line = self.gcode_pattern_search.get_line_text(lineno).strip()
        m = self.m1_image_with_comment_re.search(line)
        if not m:
            return

        # just cuz we have a match doesn't mean the text within the comment is actually an image or movie file name or exists or is
        # a compatible image format.  don't change any UI appearance until we know we have a valid pixbuf to display.
        maybe_image_filename = m.group(1).strip()

        candidate_paths = self.locate_m1_image(maybe_image_filename, lineno)
        show_as_text = True

        # Try each candidate file and see if they work
        for cc in candidate_paths:
            ccupper = cc.upper()
            if ccupper.endswith('.MOV') or ccupper.endswith('.MP4'):
                # Try to load the filename as a video
                media = video.VLCSingleton().media_new(cc)

                self.video_fullscreen = False  # M01 videos always start just over the toolpath

                #media.parse()
                #for track in media.tracks_get():
                #    if track.type == vlc.TrackType.video:

                self.vlcwidget = video.VLCWidget()
                self.vlcwidget.player.set_media(media)

                #w, h = self.vlcwidget.player.video_get_size()
                #aspectratio = self.vlcwidget.player.video_get_aspect_ratio()

                # size the player to match the preview image overlay widget.
                sztuple = self.preview_image_overlay.get_size_request()
                self.vlcwidget.set_size_request(sztuple[0], sztuple[1])

                #framerate = self.vlcwidget.player.get_rate()

                self.vlcwidget.connect("button-release-event", self.on_video_togglefullscreen_button_release)

                pt = ui_misc.get_xy_pos(self.preview_image_overlay)
                self.notebook_main_fixed.put(self.vlcwidget, pt.x, pt.y)

                togglefullscreen_button = btn.ImageButton('video-fullscreen.png','togglefullscreen')  # video-normalscreen.png is other image to swap
                # we start playback right away so the action button needs to be the pause variant
                playstop_button = btn.ImageButton('video-pause.png','play')  # video-play.png is other image to swap

                # maybe someday...
                #rotatevideo_button = btn.ImageButton('rotatevideo.png', 'rotate')

                lastX = 620
                togglefullscreen_button.set_size_request(29, 29)
                togglefullscreen_button.x = lastX
                lastX = lastX + 29 + 10
                togglefullscreen_button.y = 425
                togglefullscreen_button.connect("button-release-event", self.on_video_togglefullscreen_button_release)
                self.fixed.put(togglefullscreen_button, togglefullscreen_button.x, togglefullscreen_button.y)
                self.togglefullscreen_button = togglefullscreen_button

                playstop_button.set_size_request(29, 29)
                playstop_button.x = lastX
                lastX = lastX + 29 + 10
                playstop_button.y = 425
                playstop_button.connect("button-release-event", self.on_playstop_button_release)
                self.fixed.put(playstop_button, playstop_button.x, playstop_button.y)
                self.playstop_button = playstop_button

                self.vlcwidget.show_all()

                togglefullscreen_button.show_all()
                playstop_button.show_all()

                self.vlcwidget.play()

                show_as_text = False

            else:
                # Try to load the filename as an image and get a pixbuf.
                self.m01image_pixbuf = self.get_pixbuf_for_m1_image(cc)
                if self.m01image_pixbuf is not None:
                    # the fixed container has no control over z-order for overlapping widgets
                    # such as the elapsed time label. basically its arbitrary.
                    # workaround is to remove it from the container, show/hide all the other widgets
                    # and then re-add to the container.  fixed behaves where "last added = top of z-order"
                    self.notebook_main_fixed.remove(self.elapsed_time_label)
                    self.notebook_main_fixed.remove(self.remaining_time_label)
                    self.notebook_main_fixed.remove(self.preview_clipped_label)

                    self.load_and_set_m1_image(self.m01image_pixbuf)

                    self.preview_image_overlay.show()
                    self.gremlin.hide_all()

                    # shove elapsed time label back into container so its on top of z-order
                    self.notebook_main_fixed.put(self.elapsed_time_label, 928, 390)
                    self.elapsed_time_label.show()
                    self.notebook_main_fixed.put(self.remaining_time_label, 928, 370)
                    self.remaining_time_label.show()
                    self.notebook_main_fixed.put(self.preview_clipped_label, 904, 0)
                    if self.gcode_file_clipped_load:
                        self.preview_clipped_label.show()
                    else:
                        self.preview_clipped_label.hide()

                    show_as_text = False

            if not show_as_text: break

        if show_as_text:
            # None of the candidate files worked.
            # Put the contents of the comment into the message line that is overlayed across bottom of the toolpath
            self.set_message_line_text(maybe_image_filename)


    def hide_m1_image(self):
        if self.preview_image_overlay.get_visible():
            # the fixed container has no control over z-order for overlapping widgets
            # such as the elapsed time label. basically its arbitrary.
            # workaround is to remove it from the container, show/hide all the other widgets
            # and then re-add to the container.  fixed behaves where "last added = top of z-order"
            self.notebook_main_fixed.remove(self.elapsed_time_label)
            self.notebook_main_fixed.remove(self.remaining_time_label)
            self.notebook_main_fixed.remove(self.preview_clipped_label)

            self.error_handler.write("Hiding image specified with M01", ALARM_LEVEL_DEBUG)
            self.preview_image_overlay.hide()
            self.preview_image_overlay.clear()  # eliminate any possibility of showing stale image

            # this is sometimes called from the 500ms periodic and timing variances can cause gremlin to
            # be None in here occasionally, esp. in CI testing.
            if self.gremlin:
                self.gremlin.show_all()

            # shove elapsed time label back into container so its on top of z-order
            self.notebook_main_fixed.put(self.elapsed_time_label, 928, 390)
            self.elapsed_time_label.show()
            self.notebook_main_fixed.put(self.remaining_time_label, 928, 370)
            self.remaining_time_label.show()
            self.notebook_main_fixed.put(self.preview_clipped_label, 904, 0)
            if self.gcode_file_clipped_load:
                self.preview_clipped_label.show()
            else:
                self.preview_clipped_label.hide()

        if self.vlcwidget:
            self.fixed.remove(self.togglefullscreen_button)
            self.fixed.remove(self.playstop_button)
            if self.video_toolbar_fixed:
                self.fixed.remove(self.video_toolbar_fixed)
                self.video_toolbar_fixed.destroy()
                self.video_toolbar_fixed = None
            self.notebook_main_fixed.remove(self.vlcwidget)
            self.vlcwidget.player.stop()
            self.vlcwidget.player.release()
            self.vlcwidget.destroy()
            self.vlcwidget = None

        # do this always because we aren't tracking if the last m01/m00 break had comment text to display or not
        self.clear_message_line_text()


    def send_m1_alert(self):
        # Detect and parse block like:
        #  M01 (alert="sms" to="+15555555555" msg="Tormach 1100-3 Test")

        lineno = self.status.current_line or 1 # Work around for img on line 2
        line = self.gcode_pattern_search.get_line_text(lineno)

        m1_comment_re = re.compile(r'm0?[01]\s*\(([^)]*)\)', re.I)
        match = m1_comment_re.search(line)
        if match is not None:
            comment = match.group(1).strip()

            # Use the web site regexr.com to make heads or tails of these re patterns
            # and for super handy interactive testing.
            pattern = r"""(\w+)\s*=\s*["]([\w\s+#%!\.]*)["]|(\w+)\s*=\s*[']([\w\s+#%!\.]*)[']|(\w+)\s*=\s*([\w+#%!\.]*)"""
            tagvalue_re = re.compile(pattern, re.I)
            argdict = {}
            for match in tagvalue_re.finditer(comment):
                _add_tuple_to_dict(argdict, match.group(1, 2))
                _add_tuple_to_dict(argdict, match.group(3, 4))
                _add_tuple_to_dict(argdict, match.group(5, 6))

            if argdict.get("alert") == "sms":
                # make sure we have all the required tags
                if "msg" in argdict and "to" in argdict:
                    # Update any tokens that may be in the msg tag value
                    argdict["msg"] = string.replace(argdict["msg"], r"%line", str(lineno))
                    path, filename = os.path.split(self.current_gcode_file_path)
                    argdict["msg"] = string.replace(argdict["msg"], r"%filename", filename)
                    argdict["msg"] = string.replace(argdict["msg"], r"%elapsedtime", self.elapsed_time_label.get_text())
                    sms.send_sms_alert(**argdict)
                    self.error_handler.write("SMS alert to %s: %s" % (argdict["to"], argdict["msg"]), ALARM_LEVEL_LOW)
                else:
                    self.error_handler.write("SMS alert requires tags 'to' and 'msg'", ALARM_LEVEL_LOW)

    def get_from_json(self, section, item):
      with open(PATHPILOTJSON_FILEPATH, "r") as f:
        configdict = json.load(f)

      value = ''
      if configdict["fileversion"] == 2:
        try:
          value = configdict[section][item]
        except:
          self.error_handler.write("[%s][%s] not found in %s file" % (section, item, PATHPILOTJSON_FILEPATH), ALARM_LEVEL_LOW)

      return value


    def switch_to_lathe(self):
        """ Switch between the two GUIs to allow a RapidTurn user to have the lathe GUI on his mill."""
        # ~/pathpilot.json has the current mill ini filepath.  To switch to the lathe config we need
        # to adjust the .json file machine.rapidturn key.

        if self.machineconfig.supports_rapidturn():

            # stop machine and give user confirmation that we'll be switching to lathe
            self.stop_motion_safely()
            conf_dialog = popupdlg.ok_cancel_popup(self.window, "OK to switch to lathe interface?", cancel=True, checkbox=False)
            self.window.set_sensitive(False)
            conf_dialog.run()
            response = conf_dialog.response
            if response == gtk.RESPONSE_CANCEL:
                self.window.set_sensitive(True)
                conf_dialog.destroy()
            else:
                # get the contents of pathpilot.json and change value of machine.rapidturn
                with open(PATHPILOTJSON_FILEPATH, "r") as f:
                    configdict = json.load(f)

                if configdict["fileversion"] == 2:
                    configdict["machine"]["rapidturn"] = True

                with open(PATHPILOTJSON_FILEPATH, "w") as f:
                    json.dump(configdict, f, indent=4, sort_keys=True)
                    f.write("\n")

                self.program_exit_code = EXITCODE_MILL2RAPIDTURN

                conf_dialog.destroy()
                self.quit()

        else:
            self.error_handler.write("RapidTurn accessory not supported on this machine.", ALARM_LEVEL_LOW)



    def switch_to_mill(self):
        """ Switch between the two GUIs to allow a rapidturn user to go back to the mill GUI."""

        # stop machine and give user confirmation that we'll be switching to lathe
        self.stop_motion_safely()

        conf_dialog = popupdlg.ok_cancel_popup(self.window, "OK to switch to mill interface?", cancel=True, checkbox=False)
        self.window.set_sensitive(False)
        conf_dialog.run()
        response = conf_dialog.response
        if response == gtk.RESPONSE_CANCEL:
            self.window.set_sensitive(True)
            conf_dialog.destroy()

        else:
            # get the contents of pathpilot.json and change value of machine.rapidturn
            with open(PATHPILOTJSON_FILEPATH, "r") as f:
                configdict = json.load(f)

            if configdict["fileversion"] == 2:
                configdict["machine"]["rapidturn"] = False

            with open(PATHPILOTJSON_FILEPATH, "w") as f:
                json.dump(configdict, f, indent=4, sort_keys=True)
                f.write("\n")

            self.program_exit_code = EXITCODE_RAPIDTURN2MILL

            conf_dialog.destroy()
            self.quit()


    def switch_configuration(self):
        """ Restart and run config chooser """

        # stop machine and give user confirmation that we'll be switching to something else
        self.stop_motion_safely()

        conf_dialog = popupdlg.ok_cancel_popup(self.window, "OK to switch configuration?", cancel=True, checkbox=False)
        if not self.settings.touchscreen_enabled: self.window.set_sensitive(False)
        conf_dialog.run()
        conf_dialog.destroy()
        if conf_dialog.response == gtk.RESPONSE_CANCEL:
            self.window.set_sensitive(True)
            return

        self.program_exit_code = EXITCODE_CONFIG_CHOOSER
        self.quit()


    def set_numlock(self, turn_on):
        if turn_on:
            subprocess.Popen(['numlockx', 'on'])
        else:
            subprocess.Popen(['numlockx', 'off'])

    def copy_file(self, parentwindow, source, dest_dir):
        """ Copy a file from the specified source path to the destination directory.
            Notifies user of error if the following conditions fail:
                1) Source path is not an existing file
                2) Destination is not a directory
        """

        # Check for obvious errors and send an appropriate message to the user
        if not os.path.isfile(source):
            self.error_handler.write('File copy error - make sure that a file is highlighted', ALARM_LEVEL_LOW)
            return

        if not os.path.isdir(dest_dir):
            #FIXME This shouldn't really be possible by user action if the rest of the code is working
            self.error_handler.write('File copy error - make sure that the destination directory is valid', ALARM_LEVEL_LOW)
            return

        # path.split returns a tuple consisting of the path (including separators, up to the filename) and the filename
        filename = os.path.split(source)[1]
        # check to see if we're going to overwrite an existing file
        dest_path_in = dest_dir + os.path.sep + filename
        if os.path.exists(dest_path_in):
            with popupdlg.confirm_file_overwrite_popup(parentwindow, filename, self.settings.touchscreen_enabled) as confirm_overwrite:
                file_name_final = confirm_overwrite.filename
                # cancel button
                if file_name_final == '':
                    return
        else:
            file_name_final = filename

        dest_path_final = dest_dir + os.path.sep + file_name_final
        # Removed catch-all exception handling (testing will find exceptions to
        # catch
        # shutil.copy2 retains attributes such as date/time
        shutil.copy2(source, dest_path_final)
        tormach_file_util.filesystem_sync(self.error_handler)


    def copy_directory(self, parentwindow, source, dest_dir):
        """ Copy a directory recursively from the specified source path to the destination directory.
            Notifies user of error if the following conditions fail:
                1) Source path is not an existing directory
                2) Destination is not a directory
        """

        # Check for obvious errors and send an appropriate message to the user
        #FIXME these really aren't messages the user should ever get. The GUI should do the right thing based on context
        if not os.path.isdir(source):
            self.error_handler.write('Copy error - make sure that a directory is highlighted', ALARM_LEVEL_LOW)
            return

        if not os.path.isdir(dest_dir):
            #FIXME This shouldn't really be possible by user action if the rest of the code is working
            self.error_handler.write('File copy error - make sure that the destination directory is valid', ALARM_LEVEL_LOW)
            return

        # path.split returns a tuple consisting of the path (including
        # separators, up to the filename) and the filename
        dirname = os.path.split(source)[1]

        # check to see if we're going to overwrite a directory of the same name
        dest_path_in = dest_dir + os.path.sep + dirname
        if os.path.exists(dest_path_in):
            with popupdlg.confirm_file_overwrite_popup(parentwindow, dirname, self.settings.touchscreen_enabled) as confirm_overwrite:
                dir_name_final = confirm_overwrite.filename
                # cancel button
                if dir_name_final == '':
                    return
        else:
            dir_name_final = dirname

        # Use the sanitized name to create a new path
        dest_path_final = dest_dir + os.path.sep + dir_name_final

        dir_util.copy_tree(source, dest_path_final)


    def kill_splash_screen(self):
        # kill the splash screen
        # the --cols is needed because when ps output is captured to a pipe, it can't tell how
        # wide the tty is and it ended up clipping the path and this never found the splash screen
        # to kill.
        p = subprocess.Popen(['ps', '-x', '--cols=1024'], stdout=subprocess.PIPE)
        out, err = p.communicate()

        for line in out.splitlines():
            if 'tormach_splash.py' in line:
                pid = int(line.split(None, 6)[0])
                os.kill(pid, signal.SIGKILL)
                break


    def software_update(self):
        # check for a decent amount of free disk space before attempting an update
        try:
            freebytes = tormach_file_util.get_disk_free_space_bytes(GCODE_BASE_PATH)
            self.error_handler.write("Update checking reveals %f GB of free disk space" % (freebytes / (1024.0 * 1024.0 * 1024.0)), ALARM_LEVEL_DEBUG)

            # require 750 MB of free disk space
            if freebytes < (750 * 1024 * 1024):
                with popupdlg.ok_cancel_popup(self.window, 'Software update requires at least 750 MB of free disk space.', cancel=False, checkbox=False) as dialog:
                    pass
                return
        except subprocess.CalledProcessError:
            pass

        block_previous_versions = False
        if hasattr(self, 'atc') and self.atc:
            block_previous_versions = self.atc.is_atc_firmware_incompatible_with_previous_versions()

        if self.update_mgr.display_update_dialog(self.window, block_previous_versions, self.settings.touchscreen_enabled, self.settings.netbios_name):
            # show the e-stop warning (but only if we aren't already in e-stop state)
            self.status.poll()
            if self.status.task_state not in (linuxcnc.STATE_ESTOP, linuxcnc.STATE_ESTOP_RESET, linuxcnc.STATE_OFF):
                with popupdlg.software_update_confirmation_popup(self.window) as conf_dialog:
                    pass

            # exit UI
            self.quit()


    def do_settings_restore(self):
        with tormach_file_util.restore_filechooser_popup(self.window, GCODE_BASE_PATH, '*.zip') as dialog:
            if dialog.response != gtk.RESPONSE_OK:
                return
            # Extract dialog information for later use
            path = dialog.get_path()

        with popupdlg.software_update_confirmation_popup(self.window) as conf_dialog:
            if conf_dialog.response != gtk.RESPONSE_OK:
                return

        # a lot of time may have passed between selection and "OK"
        # in which time the USB stick may have been removed
        if not os.path.isfile(path):
            self.error_handler.write("Selected backup file not found: %s" % path, ALARM_LEVEL_LOW)
            return

        # verify selected file is a .zip file
        if not zipfile.is_zipfile(path):
            self.error_handler.write("Selected backup file is not a .zip file: %s" % path, ALARM_LEVEL_LOW)
            return

        # copy file to ~/ $HOME directory
        path_only , name_only = os.path.split(path)
        destination = os.path.join(self.home_dir, name_only)
        try:
            shutil.copy2(path, destination)
            tormach_file_util.filesystem_sync(self.error_handler)
        except Exception as ex:
            self.error_handler.write("Error trying to copy file {} to home directory prior to settings restore: {}".format(name_only, str(ex)))
            return

        # write path to ~/settings_restore_file.txt
        # then shutdown the UI and LCNC
        #FIXME: potential exceptions here
        with open(os.path.join(self.home_dir, 'settings_restore_file.txt'), "w") as text_file:
            text_file.write(destination)
        # exit UI
        self.program_exit_code = EXITCODE_SETTINGSRESTORE
        self.quit()


    def do_open_door_max_rpm(self, open_door_max_rpm):
        # clear MDI line and get rid of focus
        self.mdi_line.set_text("")
        self.window.set_focus(None)

        if len(open_door_max_rpm) == 0:
            self.error_handler.write("Door open max rpm is %d" % self.enc_open_door_max_rpm, ALARM_LEVEL_LOW)
            return

        # range check value
        # use HAL to get current spindle comp min max rpms
        min_rpm = int(self.hal['spindle-min-speed'])
        max_rpm = int(self.hal['spindle-max-speed'])

        is_valid_number = False
        try:
            rpm = int(open_door_max_rpm)
            is_valid_number = True
        except ValueError:
            pass

        if is_valid_number and ((rpm >= min_rpm and rpm <= max_rpm) or rpm == 0):
            # set HAL pin, store in redis
            self.enc_open_door_max_rpm = rpm
            self.error_handler.write('enclosure door open max rpm: %d' % self.enc_open_door_max_rpm, ALARM_LEVEL_DEBUG)
            self.hal['enc-door-open-max-rpm'] = self.enc_open_door_max_rpm
            self.redis.hset('machine_prefs', 'enc_door_open_max_rpm', self.enc_open_door_max_rpm)
            self.error_handler.write("Door open max rpm is now %d" % self.enc_open_door_max_rpm, ALARM_LEVEL_LOW)
        else:
            error_string = 'Invalid rpm setting.  RPM must be 0 or between %d and %d in the current belt position.' % (min_rpm, max_rpm)
            self.error_handler.write(error_string, ALARM_LEVEL_LOW)


    # message line
    def set_message_line_text(self, text):
        if self.message_line.get_text() != text or not self.message_line.get_visible():
            # the fixed container has no control over z-order for overlapping widgets
            # such as the elapsed time label. basically its arbitrary.
            # workaround is to remove it from the container, show/hide all the other widgets
            # and then re-add to the container.  fixed behaves where "last added = top of z-order"
            self.notebook_main_fixed.remove(self.elapsed_time_label)
            self.notebook_main_fixed.remove(self.remaining_time_label)

            self.message_line.set_text(text)
            self.message_line.show()
            self.error_handler.log("Set message line text to: {}".format(text))

            # shove elapsed time label back into container so its on top of z-order
            self.notebook_main_fixed.put(self.elapsed_time_label, 928, 390)
            self.elapsed_time_label.show()
            self.notebook_main_fixed.put(self.remaining_time_label, 928, 370)
            self.remaining_time_label.show()


    def _make_conversational_version_string(self, version_text):
        major_pat = re.findall(r'\d\.\d\.\d', version_text)
        major_abc = re.findall(r'\d\.\d\.\d[a-z]{1}', version_text)
        non_release_version = re.findall(r'\.[0-9]{1}[a-z]?-([0-9]|[a-z])+-([0-9]|[a-z])', version_text)
        version = str(int(major_pat[0][0]+major_pat[0][2]+major_pat[0][4]))
        if any(non_release_version): version = str(int(version)+1)
        version = version[0] + '.' + version[1] + '.' + version[2]
        if any(major_abc): version = version_text
        self.conversational.set_pp_version(version)

    def get_version_string(self):
        # version label shows major version + hash associated with most recent commit past version tag.
        version_label = self.builder.get_object('version_label')
        version_label.modify_font(pango.FontDescription('Bebas ultra-condensed 8'))
        try:
            ver = versioning.GetVersionMgr().get_display_version()
            version_label.set_text(ver)
            self._make_conversational_version_string(ver)
            self.error_handler.write('UI version: ' + ver, ALARM_LEVEL_DEBUG)
        except:
            self.error_handler.write('Failed to retrieve version information!', ALARM_LEVEL_MEDIUM)
            pass

    def clear_message_line_text(self):
        self.message_line.set_text('')
        self.message_line.hide()


    def _quit(self):
        # clue in the periodic timers to stop assuming the state of the world is good and just wrap it up and
        # go home.
        self.termination_in_progress = True

        self.save_persistent_data()

        try:
            if TormachUIBase._ja_tmp_filepath:
                os.remove(TormachUIBase._ja_tmp_filepath)
                TormachUIBase._ja_tmp_filepath = None
        except OSError:
            pass

        # Order of destruction here matters because its the order the file chooser settings
        # are saved (and there's only one set of settings for both choosers).  The user interacts
        # with the HD file chooser a lot more often so we save those settings last so they are
        # the ones that will be restored on next launch.
        self.usb_file_chooser.destroy()
        self.hd_file_chooser.destroy()

        # Force necessary window repainting to make sure message dialog is fully removed from screen
        ui_misc.force_window_painting()

        # Fire some GTK signals if needed to process destruction above
        while gtk.events_pending():
            gtk.main_iteration()

        self.gremlin.stop_live_plotter()
        self.gremlin = None

        # Force some final stats logging.
        self.stats_mgr.maybe_log_stats(force=True)


    #-------------------------------------------------------------------------------
    # common actions..
    #-------------------------------------------------------------------------------

    def on_mouse_enter(self, widget, event, data=None):
#       print 'TormachUIbase.on mouse enter'
        tooltipmgr.TTMgr().on_mouse_enter(widget, event)

    def on_mouse_leave(self, widget, event, data=None):
#       print 'TormachUIbase.on mouse leave'
        tooltipmgr.TTMgr().on_mouse_leave()

    def throw_away_key_press_event(self, widget, event):
        return True

    def on_mouse_wheel_event(self, widget, event):
        return True

    def dt_scroll_adjust_one(self, scroll_window, number_rows, row):
        # get var list from vertical scroll bar
        if isinstance(row, tuple): row = row[0]
        adj = scroll_window.get_vadjustment()
        adj_range = adj.upper - adj.lower
        page_upper = adj.value
        page_lower = page_upper + adj.page_size
        row_height = adj_range/number_rows
        row_top = row * row_height
        scroll_value = None
        if row_top<page_upper:
            scroll_value = max(adj.lower,row_top)
        elif row_top+row_height>page_lower:
            scroll_value = min(adj.upper,row_top+row_height-adj.page_size)
        if scroll_value is not None: adj.set_value(scroll_value)

    def on_notebook_switch_page(self, notebook, page, page_num):
        page = notebook.get_nth_page(page_num)
        page_id = gtk.Buildable.get_name(page)
        if page_id:
            self.error_handler.write('Switched to notebook page: ' + page_id, ALARM_LEVEL_DEBUG)

        # If we're switching away from the conversational page, save the title DRO
        if self.current_notebook_page_id == 'conversational_fixed':
            self.save_title_dro()

        if page_id == 'notebook_main_fixed':
            if self.gremlin_reset:
                self.gremlin_reset = False
                glib.idle_add(self.reload_gcode_file)

             # pass through the recent used combo box of gcode programs and make sure
            # they actually exist. could have been deleted.

            # prevent changes to the combo box from causing file loads
            self.combobox_masked = True
            sort_file_history(self.file_history_liststore, None, self.current_gcode_file_path)
            self.combobox_masked = False

        if page_id == 'notebook_file_util_fixed':
            # refresh free disk space
            self.hd_file_chooser.refresh_free_space_label()
            self.usb_file_chooser.refresh_free_space_label()

        if page_id != 'alarms_fixed':
            # we're leaving the alarm page, so clear interp_alarm and conv_param_alarm flags as we've already seen the alarm
            # and this is the only mechanism for "clearing" these alarms.
            # the estop alarm is ONLY cleared on RESET button press.
            self.interp_alarm = False
            self.error_handler.clear_alarm()
        else:
            # switching to Status tab
            # hide/unhide USB I/O Interface
            if not self.settings.usbio_enabled:
                self.hide_usbio_interface()

        if page_id == 'notebook_settings_fixed':
            # refresh active codes display
            if not self.suppress_active_gcode_display:
                self.gcodes_display.highlight_active_codes(self.active_gcodes())

        if self.mdi_keypad:
            self.mdi_keypad.destroy()
            self.mdi_keypad = None

    def _update_drill_through_hole_hint_label(self, tn_str, zend_str, label):
        try:
            tool_number = int(tn_str)
            full_z = float(zend_str)
            tool_dia = self.status.tool_table[tool_number].diameter * self.ttable_conv
        except:
            return
        tool_radius = tool_dia / 2
        full_hole_118 = full_z + (tool_radius * math.tan(math.radians(31)))
        full_hole_135 = full_z + (tool_radius * math.tan(math.radians(22.5)))
        markup_str = '<span weight="light" font_desc="Bebas 8" font_stretch="ultracondensed" foreground="white">(tool    diameter    %s    full    hole    118' + u'\u00b0' + ':    %s            135' + u'\u00b0' + ':    %s)</span>'
        label.set_markup(markup_str % (self.dro_long_format, self.dro_long_format, self.dro_long_format) % (tool_dia, full_hole_118, full_hole_135))

    def _update_append_file(self, path, gcode_output_list):
        # add the code to an existing file.
        with open(path, "r") as old_file:
            if not old_file: return False
            # strip out old M30
            old_code = old_file.readlines()
            stripped_code = [i if ('M30' not in i.upper()) else 'M1 (Optional Stop <m1>)\n' for i in old_code]

        with open(path, "w") as ngc_file:
            #Open file for writing and dump code back
            ngc_file.writelines(stripped_code)
            for ngc_line in gcode_output_list:
                ngc_file.write(ngc_line + '\r\n')

        self.load_gcode_file(path)
        return True

    def active_gcodes(self):
        active_codes = []
        # pylint is unaware of inheritance so, i.e., 'self' is a derived
        # class so '_report_status' needs to be gotten through a method.
        for ii in self.gcode_status_codes():
            code = self.status.gcodes[ii]
            if code % 10 == 0:
                active_codes.append("G%d" % (code/10))
            else:
                active_codes.append("G%(ones)d.%(tenths)d" % {'ones': code/10, 'tenths': code%10})
        return active_codes

    def tool_descript_conversion(self, td_is_metric, tool_descripion):
        if td_is_metric == self.g21: return tool_descripion                    # tool description and machine are in the same units
        if td_is_metric: return ui_support.ToolDescript.convert_text(tool_descripion)      # tool description is metric machine is imperial
        return ui_support.ToolDescript.convert_text(tool_descripion, ('metric',))          # tool description is imperial machine is metric

    def compare_tool_description(self, descrip1, descrip2):
        if descrip1 == descrip2: return True
        try:
            _tdr = ui_support.ToolDescript.parse_text(descrip1)
            _tdr_rec = ui_support.ToolDescript.parse_text(descrip2)
            if _tdr == _tdr_rec: return True
        except:
            self.error_handler.log('exception: ConvDecompiler.can_update. Error in parsing tool description.')
        return False

    def _parse_pn_text(self, text, data=None):
        def __parse_tool_description_text(_text, pn, _data):
            try:
                if not _data: _data = dict()
                if pn:
                    pn = pn[1:]
                    pn = pn[:5]
                    descript, diam, typ = self.pn_data.pns[pn]
                    tdr = ui_support.ToolDescript.parse_text(_text)
                else:
                    tdr = ui_support.ToolDescript.parse_text(_text)
                    diam = tdr.data['tool_diameter'][0]['ref']
                    typ =  tdr.data['type'][0]['ref']
                model, sel_iter = self.tool_treeview.get_selection().get_selected()
                path = model.get_path(sel_iter)
                _data['tdr'] = tdr
                if pn: _data['pn'] = pn
                if diam is not None and diam != '': _data['diameter'] = str(diam)
                if typ is not None: _data['type'] = typ
                if 'cmd' in _data:
                    if 'g10' not in _data['cmd']: _data['cmd'] += ['g10']
                else:
                    _data['cmd'] = ['refresh','g10']
                self.set_tool_table_data(model, path[0], _data)
            except TypeError:
                # this gets hit in 'lathe' due to multiple signals being emitted on the
                # treeview all others after the first produce a 'None' sel_iter from the selection object
                self.error_handler.log('TormachUIBase:_parse_tool_description_text selected row error')
            except KeyError:
                self.error_handler.log('TormachUIBase:_parse_tool_description_text not finding pn:%s' % (_text))
            except FloatingPointError:
                self.error_handler.log('TormachUIBase:_parse_tool_description_text badly formed diameter')

        pn = text[:7]
        if ui_support.ToolDescript._part_number.match(text[:7]): return __parse_tool_description_text(text[7:],text[:7], data)
        __parse_tool_description_text(text, None, data)

    def tool_table_update_observer(self, tool_table_row):
        # central point for diseminate tool attribute
        # changes ..
        try:
            # update the numbers ...
            self.status.poll()

            # the tool number is NOT necessarily the row number + 1 because the tool tree view may be filtered
            # to just be showing tools used by the current program.

            target_iter = self.tool_liststore.get_iter(tool_table_row)
            pocket = self.tool_liststore.get(target_iter, 0)[0]
            tool_number = self.status.tool_table[pocket].id
            job_assignment.JAObj().tool_change_listener(tool_number)
        except Exception as e:
            self.error_handler.log('TormachUIBase:tool_table_update_observer selected row error: {}'.format(str(e)))

    def zero_tool_diameter(self, tool_number):
        return iszero(self.get_tool_diameter(tool_number))

    def get_tool_diameter(self, tool_number):
        # tool table is common to both lathe and mill
        return self.status.tool_table[int(tool_number)].diameter

    def get_tool_description(self, tool_number, action ='report_error'):
        if tool_number == MILL_PROBE_TOOL_NUM:
            self.error_handler.write('get_tool_description(): Tool %d description reserved for Probe.' % MILL_PROBE_TOOL_NUM, ALARM_LEVEL_DEBUG)
            return MILL_PROBE_TOOL_DESCRIPTION
        tool_number = str(int(tool_number))
        rv = None
        try:
            rv = self.redis.hget('tool_descriptions', tool_number)
            # the description may rich info with keyword:value elements for the conversational feeds and speeds
            # redis always stores the tool description in imperial units, but convert these as necessary
            # on the fly.
            # if not in metric mode th 'imperial' keyword is needed to reduce the data from
            # full precision to a 4 decimal places if needed...
            action += 'metric' if self.g21 else 'imperial'
            rv = ui_support.ToolDescript.convert_text(rv, action)
        except:
            if 'report_error' in action:
                self.error_handler.log('TormachUIBase:get_tool_description failed to get description for tool:%s' % tool_number)
        return rv

    def set_tool_description(self, tool_number, description, action = ''):
        if tool_number == MILL_PROBE_TOOL_NUM:
            return
        try:
            # Note: redis storage of descriptions *always* in imerial units at full precision
            # so they can come back correctly into metric otherwise if stored only to 4 digits
            # of precision ther will be drif in conversion to metric...
            if 'no_convert' not in action:
                if self.g21 or 'full_precision' in action: description = ui_support.ToolDescript.convert_text(description, action)
            return self.redis.hset('tool_descriptions', str(tool_number), description)
        except:
            self.error_handler.log('TormachUIBase:set_tool_description failed to set description for tool:%s %s' % (str(tool_number), description))

    def get_tool_type(self, tool_number):
        description = self.get_tool_description(tool_number)
        if not description: return ''
        tdr = ui_support.ToolDescript.parse_text(description)
        return tdr.data['type'][0]['ref'].lower()

    def tool_table_update_focus(self,row,column,start_editing):
        """Wrapper for set_cursor"""
        self.tool_treeview.set_cursor(row, column, start_editing)
        self.tt_scroll_adjust(row)

    def tt_scroll_adjust(self, row):
        # when moving to an out of view lower tool number than current it scrolls
        # one line too few and highlights row + 1
        # scroll to one row before then scrool to row and it does the right thing
        if row > 0:
            self.tool_treeview.scroll_to_cell(row - 1)
        self.tool_treeview.scroll_to_cell(row)

    def create_page_DRO_attributes(self, page_id, attr='dros', **kwargs):
        if page_id not in self.conv_page_dros:
            self.conv_page_dros[page_id] = dict()
        page_obj = self.conv_page_dros[page_id]
        page_obj[attr] = kwargs.copy()

    @staticmethod
    def add_modify_callback(obj, callback, prepend=False):
        cb_list = obj.modify_actions if hasattr(obj,'modify_actions') else list()
        if callback in cb_list: return
        cb_list.insert(0,callback) if prepend else cb_list.append(callback)
        if hasattr(obj,'modify_actions'): return
        setattr(obj,'modify_actions',cb_list)

    @staticmethod
    def exec_modify_callback(obj):
        if not hasattr(obj,'modify_actions'): return
        for cb in obj.modify_actions: cb()

#-------------------------------------------------------------------------------
# conv edit...
#-------------------------------------------------------------------------------

    def conv_edit_prep_edit_mode(self, routine):
        # this is called from job_assignment_object.enter_edit_mode()
        # it come here here to be in 'UI' scope...
        job_assignment.JAObj().current_ui_page = self.notebook.get_current_page()
        job_assignment.JAObj().current_conversational_page = self.conv_notebook.get_current_page()
        page_count = self.conv_notebook.get_n_pages()
        conv_page_ids = copy.copy(routine['segment conv'])
        select_page_number = None
        for n in range(page_count):
            page = self.conv_notebook.get_nth_page(n)
            page_id = get_notebook_page_id(self.conv_notebook, n)
            if page_id not in conv_page_ids:
                page.hide()
            elif page_id == conv_page_ids[0]: # the 'main' page..
                select_page_number = n

        job_assignment.JAObj().current_ui_page = self.notebook.get_current_page()
        job_assignment.JAObj().main_notebook_policy(action='disable')
        set_current_notebook_page_by_id(self.notebook, 'conversational_fixed')
        if select_page_number is not None:
            self._conversational_notebook_switch_page(select_page_number)
#           self.conv_notebook.set_current_page(select_page_number)

        # Relabel 'post to file' button as 'finish editing' and hide
        # the 'append to file' button
#       self.image_store.set_image('post_to_file_image','finish-editing-button.png')
        self.builder.get_object('post_to_file').hide_all()
        self.builder.get_object('append_to_file').hide_all()
        self.in_JA_edit_mode = True

    def conv_edit_exit_edit_mode(self):
        # this is called from job_assignment_object.exit_edit_mode()
        # this is to undo all the changes 'conv_edit_prep_edit_mode' did
        # in the UI scope...
        page_count = self.conv_notebook.get_n_pages()
        for n in range(page_count):
            page = self.conv_notebook.get_nth_page(n)
            page.show()
        self.conv_notebook.set_current_page(job_assignment.JAObj().current_conversational_page)
        self.notebook.set_current_page(job_assignment.JAObj().current_ui_page)
        job_assignment.JAObj().current_ui_page = None


        self.builder.get_object('post_to_file').show_all()
        self.builder.get_object('append_to_file').show_all()
        job_assignment.JAObj().main_notebook_policy(action='enable')
        self.in_JA_edit_mode = False


    def conv_edit_prep_new_mode(self):
        job_assignment.JAObj().current_ui_page = self.notebook.get_current_page()
        job_assignment.JAObj().main_notebook_policy(action='disable')
        set_current_notebook_page_by_id(self.notebook, 'conversational_fixed')
        self.builder.get_object('post_to_file').hide_all()
        self.builder.get_object('append_to_file').hide_all()

    def conv_edit_exit_new_mode(self):
        job_assignment.JAObj().main_notebook_policy(action='enable')
        self.builder.get_object('post_to_file').show_all()
        self.builder.get_object('append_to_file').show_all()
        self.notebook.set_current_page(job_assignment.JAObj().current_ui_page)

    def refresh_thread_data_liststores(self):
        assert self.machine_type in (MACHINE_TYPE_MILL, MACHINE_TYPE_LATHE)

        #SAE Thread files first
        self.thread_chart_g20_liststore.clear()
        self.thread_chart_g20_liststore.append([THREAD_CUSTOM_DELIMITER, ' '])

        thread_filename = THREAD_DATA_SAE_CUSTOM
        custom_success = False

        try:
            with open(thread_filename, 'r') as thread_file:
                for line in thread_file:
                    # remove leading and trailing whitespace from line
                    line = line.strip()
                    if line != '' and line[0] != '#':
                        thread_size, thread_params = line.split(',', 1)
                        thread_size = thread_size.strip()
                        thread_params = thread_params.strip()
                        thread_size_up = thread_size.upper() #make an upper case copy of thread size for "NPT" compare
                        #so far we handle ONLY lathe or mill machines.  else this WILL cause new machine types to have empty liststore
                        if self.machine_type == MACHINE_TYPE_LATHE or (self.machine_type == MACHINE_TYPE_MILL and thread_size_up.find('NPT') == -1):
                            self.thread_chart_g20_liststore.append([thread_size, thread_params])
                            custom_success = True
        except:
            self.error_handler.write("Failed to import user thread data: %s" % (thread_filename), ALARM_LEVEL_DEBUG)
            custom_sucess = False  #not necessarially redunant (was set False above) with exceptions

        if custom_success == True:  # Add "Tormach" delimiter below user's data
            self.thread_chart_g20_liststore.append([ THREAD_TORMACH_DELIMITER , ' '])
        else:  #Custom user data either bad or not there. clear out liststore, remove "USER" heading
            self.thread_chart_g20_liststore.clear()

        #record timestamp.  This is used by thread_custom_file_reload()
        self.thread_custom_sae_file_mtime = os.stat(THREAD_DATA_SAE_CUSTOM).st_mtime

        thread_filename = THREAD_DATA_SAE
        try:
            with open(thread_filename, 'r') as thread_file:
                for line in thread_file:
                    # remove leading and trailing whitespace from line
                    line = line.strip()
                    if line != '' and line[0] != '#':
                        thread_size, thread_params = line.split(',', 1)
                        thread_size = thread_size.strip()
                        thread_params = thread_params.strip()
                        thread_size_up = thread_size.upper() #make an upper case copy of thread size for "NPT" compare
                        #so far we handle ONLY lathe or mill machines.  else this WILL cause new machine types to have empty liststore
                        if self.machine_type == MACHINE_TYPE_LATHE or (self.machine_type == MACHINE_TYPE_MILL and thread_size_up.find('NPT') == -1):
                            self.thread_chart_g20_liststore.append([thread_size, thread_params])
        except:
            self.error_handler.write("Failed to import thread data: %s" % (thread_filename), ALARM_LEVEL_DEBUG)

        # metric threads
        self.thread_chart_g21_liststore.clear()
        self.thread_chart_g21_liststore.append([ THREAD_CUSTOM_DELIMITER , ' '])

        thread_filename = THREAD_DATA_METRIC_CUSTOM
        custom_success = False

        try:
            with open(thread_filename, 'r') as thread_file:
                for line in thread_file:
                    # remove leading and trailing whitespace from line
                    line = line.strip()
                    if line != '' and line[0] != '#':
                        thread_size, thread_params = line.split(',', 1)
                        thread_size = thread_size.strip()
                        thread_params = thread_params.strip()
                        self.thread_chart_g21_liststore.append([thread_size, thread_params])
                        custom_success = True
        except:
            self.error_handler.write("Failed to import user thread data: %s" % (thread_filename), ALARM_LEVEL_DEBUG)
            custom_success = False

        #record timestamp.  This is used by thread_custom_file_reload().
        self.thread_custom_metric_file_mtime = os.stat(THREAD_DATA_METRIC_CUSTOM).st_mtime

        if custom_success == True: #Put "Tormach" delimiter below user's data
            self.thread_chart_g21_liststore.append([ THREAD_TORMACH_DELIMITER , ' '])
        else: #Custom user data either bad or not there. clear out liststore, remove "USER" heading
            self.thread_chart_g21_liststore.clear()

        thread_filename = THREAD_DATA_METRIC

        try:
            with open(thread_filename, 'r') as thread_file:
                for line in thread_file:
                    # remove leading and trailing whitespace from line
                    line = line.strip()
                    if line != '' and line[0] != '#':
                        thread_size, thread_params = line.split(',', 1)
                        thread_size = thread_size.strip()
                        thread_params = thread_params.strip()
                        self.thread_chart_g21_liststore.append([thread_size, thread_params])
        except:
            self.error_handler.write("Failed to import thread data: %s" % (thread_filename), ALARM_LEVEL_DEBUG)

        if self.g21:
            self.thread_chart_combobox.set_model(self.thread_chart_g21_liststore)
        else:
            self.thread_chart_combobox.set_model(self.thread_chart_g20_liststore)


    def on_set_g30_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.set_image('set_g30_image', 'set_g30_green_led.png')
        # stores current position in parameters in g30 home variables 5181, etc
        self.issue_mdi('G30.1')
        # force mode switch to synch interp and write out var file
        self.ensure_mode(linuxcnc.MODE_MANUAL)

        # Large files can take a long time so give some feedback with busy cursor
        # (but only if we know this file causes gremlin.load to be slow - otherwise
        # the flashing related to the plexiglass is annoying)
        #
        #The commit comment from 2013:
        # set_g28 button forces a gremlin.load() to reload the TP display.
        # This fixes an issue where, if you load a g code program before setting g28,
        # the interp error triggered by the unset g28 position prevents the toolpath from being drawn.
        #
        with plexiglass.ConditionalPlexiglassInstance(self.gremlin_load_needs_plexiglass, singletons.g_Machine.window) as p:
            self.gremlin.load()


    def on_goto_g30_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        # including Z at the current location results in a null Z move then
        # a move in Z only to the Z G30 location
        # this makes the G30 button always a move in Z only
        self.issue_mdi('G30 Z#5422')


    def set_widget_last_value(self, widget, value):
        if not hasattr(widget,'_last_widget_value'):
            setattr(widget, '_last_widget_value', value)
        rt = value != widget._last_widget_value
        widget._last_widget_value = value
        return rt

    def test_valid_tool(self, tool, actions):
        # one stop shopping for tool validation
        # options:
        #    allow_empty : allows for an empty tool DRO
        #    report_error: reports the error to the Status page, sets the DRO red.
        #    validate_fs : will perform an 'F&S' validation which checks to tool is
        #                  ok for F&S.
        #    zero_diameter : check for zero tool diameter if it's a axial tool
        #    description_check : validates the rest of the description field
        def __set_last_value(self, rval, dro, value):
            if self.set_widget_last_value(dro,value): tooltipmgr.TTMgr().update(dro)
            return rval

        tool_text = ''
        tool_dro = None if tool else self._get_current_tool_dro()
        tool_text = tool_dro.get_text() if tool_dro else ''
        if isinstance(tool, gtk.Entry):
            tool_text = tool.get_text()
            tool_dro = tool
        elif isinstance(tool, int): tool_text = str(tool)
        elif isinstance(tool, str): tool_text = tool
        valid = True
        if not tool_dro: tool_dro = self._get_current_tool_dro()
        # do basic tool number validation...
        try:
            tool_number = int(tool_text)
            tool_mn,tool_mx = self._get_min_max_tool_numbers()
            valid = tool_mn<=tool_number<=tool_mx
            error_msg = tooltipmgr.TTMgr().get_local_string('err_tool_number_range')
            error_msg = error_msg.format(tool_text,tool_mn,tool_mx)
        except ValueError:
            valid = False
            error_msg = tooltipmgr.TTMgr().get_local_string('err_tool_number_bad_text')
            error_msg = error_msg.format(tool_text)
        if not valid:
            if 'allow_empty' in actions and not tool_text:
                conversational.cparse.clr_alarm(tool_dro)
                error_msg = ''
            elif 'report_error' in actions:
                self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
                conversational.cparse.raise_alarm(tool_dro)
            return __set_last_value(self,(0,error_msg),tool_dro,tool_text)
        # it's an ok tool number ..do more sophisticated validation
        if 'validate_fs' in actions:
            valid, error_msg = self.fs_mgr.update_feeds_speeds('validate_only')
            if not valid:
                description = self.get_tool_description(tool_number)
                tdr = ui_support.ToolDescript.parse_text(description)
                typ = tdr.data['type'][0]['ref'].lower()
                axial = typ in ('endmill','drill','centerdrill','tap','ball','chamfer',\
                                'spot','flat','taper','bullnose','reamer','lollypop',\
                                'flycutter','shearhog','indexable','saw','threadmill')
                if axial and 'zero_diameter' in actions:
                    if self.zero_tool_diameter(tool_number):
                        tooltipmgr.TTMgr().get_local_string('err_zero_diameter_tool')
                        error_msg = error_msg.format(tool_number)
                        if 'report_error' in actions:
                            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
                            conversational.cparse.raise_alarm(tool_dro)
                        glib.idle_add(self.exec_modify_callback,tool_dro)
                        return __set_last_value(self,(0,error_msg),tool_dro,tool_text)
                elif 'description_check' in actions:
                    if 'report_error' in actions:
                        self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
                        conversational.cparse.raise_alarm(tool_dro)
                        glib.idle_add(self.exec_modify_callback,tool_dro)
                        return  __set_last_value(self,(0,error_msg),tool_dro,tool_text)
        if valid: conversational.cparse.clr_alarm(tool_dro)
        return  __set_last_value(self,(tool_number,''),tool_dro,tool_text)


    @staticmethod
    def get_set_combo_literal(combo, text=None):
        model = combo.get_model()
        active_text = combo.get_active()
        if text is None:
            return '' if active_text < 0 else model[active_text][0]
        elif not any(text):
            combo.set_active(-1)
        else:
            for n,item in enumerate(model):
                if text == item[0]:
                    combo.set_active(n)
                    break
        return None

    # ----------------------------------------------------------------------------------------------
    # dynamic tooltip methods
    # ----------------------------------------------------------------------------------------------

    def _get_tool_tip_axial_tool_description(self, tool_number, description, tool_length):
        # common code lathe and mill
        is_metric,_,_,tt_conv = self.conversational.conv_data_common(report='convert')
        local_str = tooltipmgr.TTMgr().get_local_string('axial_tool_description_metric' if is_metric else 'axial_tool_description_imperial')
        local_str = local_str.format(tt_conv*self.get_tool_diameter(tool_number), tt_conv*tool_length)
        description += '<span color="#0012da">\n{}</span>'.format(local_str)
        return description

    def _test_tooltip_description(self, tool_txt):
        tool_number = 0
        # test empty or non number case...
        if not tool_txt: tool_txt = '-blank-'
        try:
            tool_number = int(tool_txt)
        except ValueError, TypeError:
            description = tooltipmgr.TTMgr().get_local_string('err_tool_number_bad_text').format(tool_txt)
            return (tool_txt,description)
        # test for tool range...
        tool_mn,tool_mx = self._get_min_max_tool_numbers()
        if tool_mx<tool_number<tool_mn:
            description = tooltipmgr.TTMgr().get_local_string('err_tool_number_range').format(tool_txt,tool_mn,tool_mx)
            return (tool_txt,description)
        # now get to the actual description and test for an empty
        # description...
        description = self.get_tool_description(tool_number,'')
        if not description: return (tool_txt,tooltipmgr.TTMgr().get_local_string('msg_tool_info_na').format(str(tool_number)))
        description = self._get_tool_tip_tool_description(tool_number, description)
        return  (tool_txt,description)

    def get_tool_tip_tool_description(self, param):
        tool_dro = self._get_current_tool_dro()
        tool_txt = tool_dro.get_text()
        return self._test_tooltip_description(tool_txt)

    def get_current_spindle_range_numbers(self, param):
        motor_data = self.mach_data['motor_curve']
        last = len(motor_data)-1
        l,h = (motor_data[0][0],motor_data[last][0])
        rt = tooltipmgr.TTMgr().get_local_string('msg_spindle_ranges')
        return rt.format(l,h)

    def get_current_spindle_range(self, param):
        self._get_current_spindle_range_image(param)
        return self.get_current_spindle_range_numbers(param)

    def get_jog_rate(self, param):
        is_metric, units, _a, _b  = self.conversational.conv_data_common(report='convert')
        curr_widget = tooltipmgr.TTMgr().get_current_widget()
        if not curr_widget: return ''
        name = gtk.Buildable.get_name(curr_widget)
        if   name == 'jog_0001': ji = ('{:.4f}',0.0025) if is_metric else ('{:.4f}',0.0001)
        elif name == 'jog_0010': ji = ('{:.3f}',0.0100) if is_metric else ('{:.4f}',0.0010)
        elif name == 'jog_0100': ji = ('{:.3f}',0.1000) if is_metric else ('{:.4f}',0.0100)
        elif name == 'jog_1000': ji = ('{:.2f}',1.0000) if is_metric else ('{:.4f}',0.1000)
        return ji[0].format(ji[1])+' '+units

    def get_feed_rate_units(self, param):
        is_metric = self.conversational.conv_data_common(report='metric')
        local_str = 'feed_rate_text_metric' if is_metric else 'feed_rate_text_imperial'
        return tooltipmgr.TTMgr().get_local_string(local_str)

    def get_sfm_type(self, param):
        is_metric = self.conversational.conv_data_common(report='metric')
        local_str = 'smm_text_metric' if is_metric else 'sfm_text_imperial'
        sfm_str = tooltipmgr.TTMgr().get_local_string(local_str)
        local_str = 'mrr_volume_text_metric' if is_metric else 'mrr_volume_text_imperial'
        vol_str = tooltipmgr.TTMgr().get_local_string(local_str)
        return (sfm_str,vol_str)

    def get_usbio_p_value(self, param):
        sel_usbio_board = self.usbio_boardid_selected
        base = 1 if self.machine_type == MACHINE_TYPE_MILL else 5
        btn_number = 0 if '0' in param['shorttext_id'] else 1 if '1' in param['shorttext_id'] else 2 if '2' in param['shorttext_id'] else 3
        pstr = str(int(base + sel_usbio_board*4 + btn_number))
        return pstr

    def get_ja_treeview_data(self, param):
        return job_assignment.JAObj().get_treeview_data(param)

    def test_active_g_code_changed(self, g_code_index):
        f = self._modal_change_redraw_flags[g_code_index]
        return f.test_and_set(self.status.gcodes[g_code_index])

    def test_changed_active_g_codes(self, check_list):
        return {
            k: self.test_active_g_code_changed(k) for k in check_list
        }

#---------------------------------------------------------------------------------------------------
# END TormachUIBase
#---------------------------------------------------------------------------------------------------


class internet_checker():
    def __init__(self):
        self.pingproc = None
        self.internet_reachable = False     # initially we don't know, assume failure.

        # setup a timer every 5 seconds
        # start a timer to check background pinging
        glib.timeout_add(5000, self._on_timer_expire, priority=glib.PRIORITY_DEFAULT_IDLE)

    def _on_timer_expire(self):
        self._try_ping_ip("www.tormach.com")
        return True   # continue timer

    def _try_ping_ip(self, hostname):
        '''
        "Give me a ping, Vasili. One ping only, please."
        '''
        if self.pingproc is None:
            self.nullwritablefile = open("/dev/null", "w", 0)
            self.nullreadablefile = open("/dev/null", "r", 0)

            # this waits a little less than the timer period so that we should have a definitive answer every time
            # through here, even on failure.
            self.pingproc = subprocess.Popen(["/bin/ping",
                                              "-W4",
                                              "-c1",
                                              hostname], stdin=self.nullreadablefile, stdout=self.nullwritablefile, stderr=self.nullwritablefile)

        if self.pingproc.poll() != None:
            # we have a definitive answer
            self.internet_reachable = (self.pingproc.returncode == 0)
            self.nullreadablefile.close()  # don't leak file handles...
            self.nullwritablefile.close()
            self.pingproc = None   # on next method call we will kick off another ping


class LatchedFlag:
    def __init__(self, value=None):
        self.__value = value

    def test_and_set(self, new_value):
        changed = (new_value != self.__value)
        self.__value = new_value
        return changed


