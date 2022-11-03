#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import pygtk
pygtk.require("2.0")
import gtk

import popupdlg
import ui_misc

statusdlg = popupdlg.status_popup(None, 'Installing PathPilot software update...')
statusdlg.show_all()
statusdlg.present()  # make sure it is top of z-order stack so user can see it since there's no parent window
ui_misc.force_window_painting()

gtk.main()
