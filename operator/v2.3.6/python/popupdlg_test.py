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


import pygtk
pygtk.require("2.0")
import gtk
import popupdlg
import unittest
import sys
import os
import errors
import constants as const
import btn
import tormach_file_util
import time
import ui_misc

global g_win


class TestPopups(unittest.TestCase):


    def test_file_as(self):
        global g_win
        with tormach_file_util.file_save_as_popup(g_win, 'Long message text', 'SamplePath', '.zip', touchscreen_enabled=False, usbbutton=False, closewithoutsavebutton=False) as dialog:
            pass

        with tormach_file_util.file_save_as_popup(g_win, 'Long message text', 'SamplePath', '.zip', touchscreen_enabled=True, usbbutton=True, closewithoutsavebutton=True) as dialog:
            pass


    def test_status_popup(self):
        global g_win
        popup = popupdlg.status_popup(g_win, "Status message while something is in progress...")
        popup.show_all()
        popup.present()

        # Force necessary window repainting to make sure message dialog is fully removed from screen
        ui_misc.force_window_painting()

        time.sleep(3)
        popup.destroy()

        # Force necessary window repainting to make sure message dialog is fully removed from screen
        ui_misc.force_window_painting()

    def test_entry_only_popup(self):
        global g_win
        with popupdlg.generic_entry_popup(g_win, 'New Name', 'Default name', touchscreen_enabled=False) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

    def test_delete(self):
        global g_win
        with popupdlg.delete_files_popup(g_win, 5, 5) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

    def test_new_filename(self):
        global g_win
        with popupdlg.new_filename_popup(g_win, "Message", False) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

    def test_new_filename_touchscreen(self):
        global g_win
        with popupdlg.new_filename_popup(g_win, "Enter the new name for the file or folder.", True) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

    def test_confirm_overwrite(self):
        global g_win
        with popupdlg.confirm_file_overwrite_popup(g_win, "This is a long file name.ngc", True) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

        with popupdlg.confirm_file_overwrite_popup(g_win, "This is a long file name.ngc", False) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"


    def test_ok_cancel_popup(self):
        global g_win
        with popupdlg.ok_cancel_popup(g_win, "Message", True, True) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

        with popupdlg.ok_cancel_popup(g_win, errors.LIMIT_SWITCH_WARNING_MSG, False, True) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

        with popupdlg.ok_cancel_popup(g_win, "Message", False, False) as dialog:
            if dialog.response == gtk.RESPONSE_OK:
                print "Blammo"

    def test_shutdown(self):
        global g_win
        with popupdlg.shutdown_confirmation_popup(g_win) as dialog:
            print "Blammo"

    def test_update(self):
        global g_win
        with popupdlg.software_update_confirmation_popup(g_win) as dialog:
            print "Blammo"

    def test_file_chooser(self):
        global g_win
        with tormach_file_util.update_filechooser_popup(g_win, False) as dialog:
            print "Blammo"


if __name__ == '__main__':

    global g_win
    g_win = gtk.Window(gtk.WINDOW_TOPLEVEL)
    g_win.set_decorated(False)
    g_win.set_default_size(1024, 768)
    g_win.set_position(gtk.WIN_POS_CENTER_ALWAYS)
    g_win.show_all()

    suite = unittest.TestLoader().loadTestsFromTestCase(TestPopups)
    unittest.TextTestRunner(verbosity=2).run(suite)
