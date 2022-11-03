# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import pygtk
pygtk.require("2.0")
import gtk
import unittest
import sys
import os
import btn

global g_win

GLADE_DIR = os.path.join(os.path.abspath(sys.path[0]), 'images')

class TestImageButton(unittest.TestCase):

    def test_button(self):
        global g_win

        fixed = gtk.Fixed()
        fixed.set_size_request(250, 250)

        b = btn.ImageButton()
        b.load_image('ok-button.png', GLADE_DIR)

        fixed.put(b, 50, 50)

        b = btn.ImageButton()
        b.load_image('Exit_Smaller.png', GLADE_DIR)
        b.connect("button-release-event", self.on_button_release_event)
        fixed.put(b, 200, 50)

        g_win.add(fixed)
        g_win.show_all()
        gtk.main()

    def on_button_release_event(self, widget, data=None):
        gtk.main_quit()


if __name__ == '__main__':
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    global g_win
    g_win = gtk.Window(gtk.WINDOW_TOPLEVEL)
    g_win.set_decorated(False)
    g_win.set_default_size(1024, 768)
    g_win.set_position(gtk.WIN_POS_CENTER_ALWAYS)
    g_win.show_all()

    suite = unittest.TestLoader().loadTestsFromTestCase(TestImageButton)
    unittest.TextTestRunner(verbosity=2).run(suite)
