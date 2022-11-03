#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import string
import gtk
import glib
import time
from constants import *
import os
import glob
from datetime import datetime
import tzlocal
import pango
import thread
import ppglobals
import inspect
import threading
import fsutil


LOGCOLOR_ENABLED = 0

import colorama
colorama.init(autoreset=True)


# TODO: excise log file rotation - needs to be done outside the UI


# error_handler_base objects can be created without any dependencies on other init state.
# one of these is created immediately and all code can still use write() method to log messages
# in a consistent fashion (timestamp prefixes, formatting, translation)
#
# eventually, enough of the machine is initialized to replace the error_handler_base object with
# a full error_handler object, but because of the inheritance providing the same API,
# callers don't know any difference.

_datetime_mutex = threading.RLock()
_local_timezone = tzlocal.get_localzone()
_previous_datetime = _local_timezone.localize(datetime.now())
_previous_datetime_instance = None

class error_handler_base():
    def __init__(self):
        # pylint: disable=no-member
        self.alarmcolormap = { ALARM_LEVEL_NONE   : colorama.Fore.WHITE  + colorama.Back.BLACK,
                               ALARM_LEVEL_DEBUG  : colorama.Fore.WHITE  + colorama.Back.BLACK,
                               ALARM_LEVEL_QUIET  : colorama.Fore.WHITE  + colorama.Back.BLACK,
                               ALARM_LEVEL_LOW    : colorama.Fore.GREEN  + colorama.Back.BLACK,
                               ALARM_LEVEL_MEDIUM : colorama.Fore.YELLOW + colorama.Back.BLACK,
                               ALARM_LEVEL_HIGH   : colorama.Fore.RED    + colorama.Style.BRIGHT + colorama.Back.BLACK }

    def _get_timestamp_prefixes(self):
        # the re-entrant lock protects the previous datetime global vars from
        # modification by worker and GUI threads.
        # rest of the code here is concurrent friendly as only local vars are used.
        _datetime_mutex.acquire()
        try:
            global _previous_datetime
            global _previous_datetime_instance
            global _local_timezone
            dt = _local_timezone.localize(datetime.now())

            short_timestamp = dt.strftime("%H:%M:%S | ")

            # There can end up being more than one instance of error_handler_base.
            # Only calculate delta time from last log call if we know it makes sense to.
            if _previous_datetime_instance == self:
                long_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f %Z") + (" (+%s) | " % str(dt - _previous_datetime))
            else:
                long_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.%f | ")

            _previous_datetime = dt
            _previous_datetime_instance = self

            return short_timestamp, long_timestamp
        finally:
            _datetime_mutex.release()

    def _get_source_location(self, stack_depth_walkback=2):
        '''
        Stack depth walkback is how many stack frames back to get the source filename and line location.
        A value of 1 would simply get you "errors.py line 43" right below this comment which
        isn't useful.
        '''
        framelist = inspect.stack(context=stack_depth_walkback)
        try:
            frame = framelist[stack_depth_walkback - 1]
            # frame is a tuple where frame[1] is the filename and frame[2] is the line number.
            trimmed_filename = string.replace(frame[1], "/home/operator/tmc/python/", "")  # most code
            trimmed_filename = string.replace(trimmed_filename, "/home/operator/tmc/", "") # code living over in configs dirs
            srclocation = " [%s:%d]" % (trimmed_filename, frame[2])
            return srclocation
        finally:
            # deterministically destroy these stack frame references as advised in the python docs to avoid
            # any possibility of a reference cycle that fills the heap.
            for x in framelist:
                del x

    def set_loaded_gcode_file_path(self, filepath):
        self._loaded_file_path = filepath

    def log(self, log_msg):
        # !!!! NOTE !!!!
        # This can get called from the GUI or worker threads. Cannot introduce any
        # Gtk dependencies.

        # log() is a shortcut for debug log messages.
        # Equivalent to write('blah', ALARM_LEVEL_DEBUG) but much more concise.
        short_timestamp, long_timestamp = self._get_timestamp_prefixes()
        srclocation = self._get_source_location(3)
        self._write(log_msg, ALARM_LEVEL_DEBUG, srclocation, short_timestamp, long_timestamp)

    def write(self, error_msg, alarm_level=ALARM_LEVEL_MEDIUM):
        # !!!! NOTE !!!!
        # This can get called from the GUI or worker threads. Cannot introduce any
        # Gtk dependencies.
        short_timestamp, long_timestamp = self._get_timestamp_prefixes()
        srclocation = self._get_source_location(3)
        self._write(error_msg, alarm_level, srclocation, short_timestamp, long_timestamp)

    def _write(self, error_msg, alarm_level, srclocation, short_timestamp, long_timestamp):
        # always dump untranslated message provided to terminal, not the status window
        if LOGCOLOR_ENABLED:
            print >> sys.stderr, self.alarmcolormap[alarm_level] + long_timestamp + error_msg + srclocation
        else:
            print >> sys.stderr, long_timestamp + error_msg + srclocation

        # translate to a more human readable form than 'joint 0 following error'
        translated_error_msg = self.translate(error_msg)
        if translated_error_msg != None and translated_error_msg != '' and translated_error_msg != error_msg:
            if LOGCOLOR_ENABLED:
                print >> sys.stderr, self.alarmcolormap[alarm_level] + long_timestamp + translated_error_msg + " [translated]"
            else:
                print >> sys.stderr, long_timestamp + translated_error_msg + " [translated]"

    def clear_alarm(self):
        pass

    def clear_history(self):
        pass

    def get_alarm_active(self):
        return False

    def set_image_1(self, file_name):
        pass

    def set_image_2(self, file_name):
        pass

    def set_error_image_1_text(self, text):
        pass

    def set_error_image_2_text(self, text):
        pass

    def translate(self, msg):
        # !!!! NOTE !!!!
        # This can get called from the GUI or worker threads. Cannot introduce any
        # Gtk dependencies.

        # Linuxcnc is always told to read the same file.  When a file is loaded in the UI,
        # we copy the entire file to a non-user accessible location and then tell linuxcnc to use
        # that file.  This prevents any possibility that it might get updated during program execution.
        # But if any linuxcnc error message contains the gcode file name, it must be translated back
        # to the file name that makes sense to the user.

        if LINUXCNC_GCODE_FILE_PATH in msg:
            userpath = fsutil.sanitize_path_for_user_display(self._loaded_file_path)
            msg = msg.replace(LINUXCNC_GCODE_FILE_PATH, userpath)

        if LINUXCNC_GCODE_FILE_NAME in msg:
            msg = msg.replace(LINUXCNC_GCODE_FILE_NAME, os.path.basename(self._loaded_file_path))

        ''' LCNC has a number of cryptic error messages that we don't want to expose to the users.
        This method just does text search and replace to make theses messages more user-friendly.
        In the case where we don't want to show a message at all, just return none '''
        if 'Linear move on line' in msg:
            if 'joint 0' in msg: msg = msg.replace('joint 0', 'the x axis')
            if 'joint 1' in msg: msg =  msg.replace('joint 1', 'the y axis')
            if 'joint 2' in msg: msg =  msg.replace('joint 2', 'the z axis')
            if 'joint 3' in msg: msg =  msg.replace('joint 3', 'the a axis')
            return msg + "\nPlease reference the machine or check that the gcode doesn't travel outside of the machine's limits"

        if 'Cannot unhome while moving, ' in msg:
            if 'joint 0' in msg: msg = msg.replace('joint 0', 'the x axis')
            if 'joint 1' in msg: msg =  msg.replace('joint 1', 'the y axis')
            if 'joint 2' in msg: msg =  msg.replace('joint 2', 'the z axis')
            if 'joint 3' in msg: msg =  msg.replace('joint 3', 'the a axis')
            return msg.replace('Cannot unhome while moving, ', 'The limit switch failed to activate on ')

        if 'move on line' in msg and 'would exceed joint' in msg:
            if 'joint 0' in msg: msg = msg.replace('joint 0', 'the x axis')
            if 'joint 1' in msg: msg =  msg.replace('joint 1', 'the y axis')
            if 'joint 2' in msg: msg =  msg.replace('joint 2', 'the z axis')
            if 'joint 3' in msg: msg =  msg.replace('joint 3', 'the a axis')
            return msg + "\nPlease reference the machine or check that the gcode doesn't travel outside of the machine's limits"

        # all orient fault messages are already in log via raw linuxcnc print albeit without timestamps and cryptic
        # error codes from m200.orient-fault pin. The errors are duplicated via m200 spindle-fault pin and recorded
        # with timestamp
        if 'during orient in progress' in msg: return None #swallow these messages because they have cryptic error codes
        # we allow wait for orient complete time out to reach  user because it is human readable

        # screen these out now that we have the mesa watchdog logic enabled for tracking
        # ethernet packet errors.
        if 'hm2_' in msg and 'error finishing' in msg and 'iter' in msg: return None

        if 'quadrature count error' in msg: return None
        if "line can't have zero length!" in msg: return None
        if 'Unknown word where unary' in msg: return msg.replace('Unknown word where unary operation could be', INVALID_GCODE_USED)
        if 'command (EMC_TASK_PLAN_EXECUTE) cannot be executed until' in msg: return CANNOT_EXECUTE_COMMAND_UNLESS_MACHINE_OUT_OF_ESTOP
        if ': check dmesg for details' in msg: return msg.replace(': check dmesg for details', '')
        if 'in manual mode' in msg: msg = msg.replace('in manual mode', 'while jogging')
        if "can't do that" in msg: msg = msg.replace("can't do that", 'Unable to execute command: ')
        if 'EMC_TASK_PLAN_STEP' in msg: msg = msg.replace('EMC_TASK_PLAN_STEP', 'Cycle Start')
        if 'EMC_TASK_PLAN_RUN' in msg: msg = msg.replace('EMC_TASK_PLAN_RUN', 'Cycle Start')
        if 'Cannot use g53 incremental' in msg: msg = 'Cannot use g53 in g91 incremental.  Change from g91 to g90 before g53 move.'
        if 'end of move in home state' in msg: msg = 'Reference switch was not seen within timeout period'

        return msg



# error message
class error_handler(error_handler_base):

    # Do NOT add a hal dependency into such a simple class. This is supposed to just log the error and that's it.
    # The caller should do whatever it needs to with hal - NOT this object.
    def __init__(self, builder, runningmethod):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()

        # Call ctor for base class
        error_handler_base.__init__(self)

        # TODO - helper functions like set_image that are common to lathe and mill
        # should be split off into a separate module and imported from that module,
        # not passed into classes like this

        self.alarm_level = ALARM_LEVEL_NONE

        # Note - this is a function pointer basically
        self.runningmethod = runningmethod

        self.notebook = builder.get_object("notebook")
        self.diagnostics_textview = builder.get_object("diagnostics_textview")
        self.buffer = self.diagnostics_textview.get_buffer()

        font_description = pango.FontDescription('Roboto Condensed 10')
        self.diagnostics_textview.modify_font(font_description)

        # alarms tab label superimposed on eventbox so we can change background color
        self.alarms_eventbox = builder.get_object("alarm_eventbox")
        self.alarms_eventbox.modify_bg(gtk.STATE_ACTIVE, gtk.gdk.Color('yellow'))
        self.alarms_eventbox.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color('yellow'))
        self.alarms_tab_label = builder.get_object("alarms_tab_label")

        # ALARMS_PAGE number can change depending on lathe versus mill, or on number of accessories displayed in mill
        # but it's always the last one.  NB - notebook page numbers start at 0, not 1.
        # Note that, in the future, it would be better to have this page accessed by ID
        self.alarms_page_num = self.notebook.get_n_pages() - 1
        self.alarms_page = self.notebook.get_nth_page(self.alarms_page_num)

        self.error_image_1 = builder.get_object('error_image_1')
        self.error_image_1_text = builder.get_object('error_image_1_text')
        self.error_image_1_text.modify_font(pango.FontDescription('helvetica 12 '))
        self.error_image_2 = builder.get_object('error_image_2')
        self.error_image_2_text = builder.get_object('error_image_2_text')
        self.error_image_2_text.modify_font(pango.FontDescription('helvetica 12 '))

        self.diag_scrolledwindow = builder.get_object('diag_scrolledwindow')
        self.diag_scrolledwindow_initialsize = self.diag_scrolledwindow.get_size_request()
        self._grow_diag_window()


    def write(self, error_msg, alarm_level=ALARM_LEVEL_MEDIUM):
        # !!!! NOTE !!!!
        # This can get called from the GUI or worker threads.
        # The zbot atc worker thread is one example of a non-GUI thread calling this.

        short_timestamp, long_timestamp = error_handler_base._get_timestamp_prefixes(self)
        srclocation = self._get_source_location(3)
        self._write(error_msg, alarm_level, srclocation, short_timestamp, long_timestamp)


    def _write(self, error_msg, alarm_level, srclocation, short_timestamp, long_timestamp):
        # always dump untranslated message provided to terminal, not the status window
        if LOGCOLOR_ENABLED:
            print >> sys.stderr, self.alarmcolormap[alarm_level] + long_timestamp + error_msg + srclocation
        else:
            print >> sys.stderr, long_timestamp + error_msg + srclocation

        # translate to a more human readable form than 'joint 0 following error'
        translated_error_msg = error_handler_base.translate(self, error_msg)
        if translated_error_msg != None and translated_error_msg != '':
            if translated_error_msg != error_msg:
                if LOGCOLOR_ENABLED:
                    print >> sys.stderr, self.alarmcolormap[alarm_level] + long_timestamp + translated_error_msg + " [translated]"
                else:
                    print >> sys.stderr, long_timestamp + translated_error_msg + " [translated]"

            # stderr redirection will catch and log this if it is ALARM_LEVEL_DEBUG
            if alarm_level != ALARM_LEVEL_DEBUG:

                # we want this to show up in the console/logs but not the UI Status tab
                # since this comes from LinuxCNC itself we cannot control 'alarm_level'
                # and catch it above
                if 'Unexpected realtime delay' not in translated_error_msg:

                    # Now we need to mess with Gtk objects but need to ensure thread safety.
                    if ppglobals.GUI_THREAD_ID == thread.get_ident():
                        # we're safe, just call it directly.
                        self._write_gui_callback(translated_error_msg, alarm_level, short_timestamp)
                    else:
                        # do it real soon now on the GUI thread.  note the timestamp will still be accurate
                        # because we already snapped the time above.
                        glib.idle_add(self._write_gui_callback, translated_error_msg, alarm_level, short_timestamp)


    def _write_gui_callback(self, translated_error_msg, alarm_level, short_timestamp):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()

        # latch to the highest level since we've last been cleared
        self.alarm_level = max(self.alarm_level, alarm_level)

        self.alarms_eventbox.set_tooltip_text(translated_error_msg)

        if self.alarm_level >= ALARM_LEVEL_LOW:
            self.alarms_eventbox.set_visible_window(True)
            self.alarms_tab_label.set_markup("<span foreground='black'>Status (F1)</span>")

        if self.alarm_level >= ALARM_LEVEL_MEDIUM:
            self.notebook.set_current_page(self.alarms_page_num)

        # show the alarms page if it's currently hidden
        if self.runningmethod():
            self.alarms_page.show()

        self.buffer.insert(self.buffer.get_start_iter(), "%s\n" % (short_timestamp + translated_error_msg))

        # trim line count to something
        delete_count = self.buffer.get_line_count() - 1000
        if delete_count > 0:
            start_iter = self.buffer.get_iter_at_line(1000)
            end_iter = self.buffer.get_iter_at_line(self.buffer.get_line_count())
            self.buffer.delete(start_iter, end_iter)


    def clear_alarm(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()

        self.alarm_level = ALARM_LEVEL_NONE
        self.alarms_eventbox.set_visible_window(False)
        self.alarms_tab_label.set_markup("<span foreground='black'>Status (F1)</span>")
        self.error_image_1.hide()
        self.error_image_2.hide()
        self.error_image_1_text.set_text('')
        self.error_image_2_text.set_text('')

        # now that we are clearly not showing any additional info,
        # make the diagnostics scrolled window bigger again.
        self._grow_diag_window()

        # clear tool tip
        self.alarms_eventbox.set_tooltip_text('')

        # scroll to end
        self.diagnostics_textview.scroll_to_iter(self.buffer.get_start_iter(), 0)


    def clear_history(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.clear_alarm()
        # clear textview
        start_iter = self.buffer.get_start_iter()
        end_iter = self.buffer.get_end_iter()
        self.buffer.delete(start_iter, end_iter)
        # scroll to end
        self.diagnostics_textview.scroll_to_iter(self.buffer.get_end_iter(), 0)
        self.log("error_handler history cleared.")


    def translate(self, msg):
        return error_handler_base.translate(self, msg)


    def get_alarm_active(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        return (self.alarm_level >= ALARM_LEVEL_LOW)


    def _shrink_diag_window(self):
        self.diag_scrolledwindow.set_size_request(self.diag_scrolledwindow_initialsize[0], self.diag_scrolledwindow_initialsize[1])


    def _grow_diag_window(self):
        self.diag_scrolledwindow.set_size_request(670, self.diag_scrolledwindow_initialsize[1])


    def set_image_1(self, file_name):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.error_image_1.show()
        self.error_image_1.set_from_file(os.path.join(GLADE_DIR, file_name))
        self._shrink_diag_window()


    def set_image_2(self, file_name):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.error_image_2.show()
        self.error_image_2.set_from_file(os.path.join(GLADE_DIR, file_name))
        self._shrink_diag_window()


    def set_error_image_1_text(self, text):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.error_image_1_text.set_text(text)
        self._shrink_diag_window()


    def set_error_image_2_text(self, text):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.error_image_2_text.set_text(text)
        self._shrink_diag_window()


# Error Message Constants
INVALID_GCODE_USED = 'Invalid G code command issued'
CANNOT_EXECUTE_COMMAND_UNLESS_MACHINE_OUT_OF_ESTOP  = 'Command cannot be executed unless machine is powered on and the control software is out of RESET condition'

NO_HSTOP_WARNING_MSG = 'Hard stop referencing is disabled.\n\nClicking the axis reference buttons will not perform a normal referencing operation (moving the axis to the hard stop).  Instead, the reference position will be set to the current machine position for the axis.\n\nTo restore automatic referencing, check the Hard Stop Referencing setting.'
LIMIT_SWITCH_WARNING_MSG = 'Limit switches are disabled.\n\nClicking the axis reference buttons will not perform a normal referencing operation (moving the axis to toggle a limit switch).  Instead, the reference position will be set to the current machine position for the axis.\n\nTemporarily disabling limit switches allows you to move an axis off a limit switch in order to restore normal referencing operation.\n\nTo restore automatic referencing, check the Limit Switches setting.'

