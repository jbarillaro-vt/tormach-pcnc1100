#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import glib
import os
import sys
import pango
import time

from constants import *
from errors import *
from conversational import cparse
import samba
import plexiglass
import popupdlg
import tooltipmgr
import singletons
import ui_support
import ui_misc


class common_settings():

    _FS_ENABLED_REDIS_KEY = 'feeds_speeds_enabled'


    def __init__(self, UIobj, redis, gladefilename):
        self.UIobj = UIobj
        self.redis = redis
        self.gladefilename = gladefilename
        self.builder = gtk.Builder()

        gladefile = os.path.join(GLADE_DIR, self.gladefilename)

        if self.builder.add_objects_from_file(gladefile, ['notebook_settings_fixed']) == 0:
            raise RuntimeError("GtkBuilder failed")

        missingSignals = self.builder.connect_signals(self)
        if missingSignals is not None:
            raise RuntimeError("Cannot connect signals: ", missingSignals)

        self.fixed = self.builder.get_object("notebook_settings_fixed")
        if self.fixed == None:
            raise RuntimeError("Cannot find object: ", "notebook_settings_fixed")

        # NetBIOS name
        self.netbios_name = self.get_netbios_name(netbios_name_conf_file)
        self.netbios_name_widget = self.builder.get_object('netbios_name')
        self.netbios_name_widget.set_text(self.netbios_name)

        self.checkbutton_ids = ['enable_soft_keyboard_checkbutton',
                                'enable_home_switches_checkbutton',
                                'enable_usbio_checkbutton',
                                'enable_tooltips_checkbutton']
        self.checkbutton_list = {}
        for cb in self.checkbutton_ids:
            assert cb not in self.checkbutton_list, "Duplicate id found"
            self.checkbutton_list[cb] = self.builder.get_object(cb)
            self.checkbutton_list[cb].modify_bg(gtk.STATE_PRELIGHT, UIobj._check_button_hilight_color)

        # touchscreen
        self.touchscreen_enabled = self.redis.hget('machine_prefs', 'touchscreen')
        if self.touchscreen_enabled is None:
            self.touchscreen_enabled = 'False'
            self.redis.hset('machine_prefs', 'touchscreen', self.touchscreen_enabled)
        self.touchscreen_enabled = (self.touchscreen_enabled == 'True') # convert str to boolean
        self.checkbutton_list['enable_soft_keyboard_checkbutton'].set_active(self.touchscreen_enabled)

        # usbio
        self.enable_usbio_checkbutton_masked = True
        self.usbio_enabled = self.redis.hget('machine_prefs', 'usbio_enabled')
        if self.usbio_enabled is None:
            self.usbio_enabled = 'False'
            self.redis.hset('machine_prefs', 'usbio_enabled', self.usbio_enabled)
        self.usbio_enabled = (self.usbio_enabled == 'True') # convert str to boolean
        self.UIobj.hal["usbio-enabled"] = self.usbio_enabled
        self.UIobj.usbio_e_message = True         # reset error message filter flag
        self.checkbutton_list['enable_usbio_checkbutton'].set_active(self.usbio_enabled)
        self.enable_usbio_checkbutton_masked = False

        # limit switches
        # sync the state of the UI checkbox widget, but don't have it take any action as a result or we could get the
        # popup warning before the main UI screen is even displayed at startup
        self.enable_home_switches_checkbutton_masked = True
        self.home_switches_enabled = self.redis.hget('machine_prefs', 'home_switches_enabled')
        if self.home_switches_enabled is None:
            self.home_switches_enabled = 'True'
            self.redis.hset('machine_prefs', 'home_switches_enabled', self.home_switches_enabled)
        self.home_switches_enabled = (self.home_switches_enabled == 'True') # convert str to boolean
        self.checkbutton_list['enable_home_switches_checkbutton'].set_active(self.home_switches_enabled)
        if not self.home_switches_enabled:
            if self.UIobj.machineconfig.has_hard_stop_homing():
                self.UIobj.error_handler.write(NO_HSTOP_WARNING_MSG, ALARM_LEVEL_LOW)
            else:
                self.UIobj.builder.get_object("limits_text").set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits    (disabled)</span>')
                lbl = self.UIobj.builder.get_object('limits_text_doorsw_enabled')
                if lbl:
                    lbl.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits    (disabled)</span>')
                self.UIobj.error_handler.write(LIMIT_SWITCH_WARNING_MSG, ALARM_LEVEL_LOW)
        self.enable_home_switches_checkbutton_masked = False

        # Change "Limit Switches" checkbox on settings tab to "Hard Stop Referencing"
        if self.UIobj.machineconfig.has_hard_stop_homing():
            limit_switch_object = self.builder.get_object('enable_home_switches_text')
            limit_switch_object.set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="white">Hard Stop Referencing</span>')

        self.extended_tooltips_enabled = self.redis.hget('uistate', 'extended_tooltips_enabled')
        if self.extended_tooltips_enabled is None:
            self.extended_tooltips_enabled = 'True'
            self.redis.hset('uistate', 'extended_tooltips_enabled', self.extended_tooltips_enabled)
        self.extended_tooltips_enabled = (self.extended_tooltips_enabled == 'True')  # convert str to boolean
        self.checkbutton_list['enable_tooltips_checkbutton'].set_active(self.extended_tooltips_enabled)


    ##################################
    # NetBIOS related

    def save_netbios_name_if_changed(self, widget):
        nbentry_text = self.validate_netbios_name(widget.get_text())
        # if empty, fill in existing name
        if nbentry_text == '':
            nbentry_text = self.netbios_name
        # stuff the result back into the text entry
        widget.set_text(nbentry_text)
        # if changed, set the new NetBIOS name
        if nbentry_text != self.netbios_name:
            self.netbios_name = nbentry_text
            self.set_netbios_name(netbios_name_conf_file, nbentry_text)

    def on_netbios_name_focus_in_event(self, widget, event):
        # temporarily disable this until we can
        # debug notebook tab switching and which widget gets focus
        # otherwise can be super annoying that every time you display the settings tab,
        # the netbiox name entry gets focus and the modal touchscreen pops up demanding attention.  Sigh.
        #if self.touchscreen_enabled:
        #    np = numpad.numpad_popup(self.UIobj.window, widget, qwerty=True, y=180, enter_takedown=True)
        #    np.run()
        #    widget.select_region(0, 0)
        #    self.UIobj.window.set_focus(None)
        pass

    def on_netbios_name_focus_out_event(self, widget, event):
        # this event happens if the user switches tabs or moves the input focus to some other
        # control
        self.save_netbios_name_if_changed(widget)

    def on_netbios_name_activate(self, widget, data=None):
        # this event only happens if the user remembers to press Enter key after editing the network name
        self.save_netbios_name_if_changed(widget)

    def get_netbios_name(self, filename):
        # NetBIOS name configuration file
        # default to hostname
        netbios_name = os.uname()[1]
        try:
            with open(filename) as inf:
                nblines = inf.readlines()
                for line in nblines:
                    words = line.split()
                    if len(words) > 0 and words[0] == 'netbios' and words[1] == 'name' and words[2] == '=':
                        netbios_name = words[3]
        except:
            self.UIobj.error_handler.log("Exception parsing %s for netbios name." % filename)

        return netbios_name


    def set_netbios_name(self, filename, name):
        # ~/smb.conf.netbios-name
        # simplistically overwrites file rather than find section and edit
        try:
            with open(filename, 'w') as nbfile:
                nbfile.write("[global]\n\n# NetBIOS name\n\tnetbios name = %s\n\n" % name)
        except:
            self.UIobj.error_handler.log("Exception writing %s with new netbios name %s" % (filename, name))

        samba.restart_samba()

        self.UIobj.error_handler.write("Network name changed to {}.  Controller does not need to be restarted, new network name is now in effect.".format(name), ALARM_LEVEL_LOW)


    def validate_netbios_name(self, name):
        # can't have "*./\[]:|<>+=;' and must be 13 characters or less in length
        # strip invalid characters
        nbentry_text = name.translate(None, "*./\[]:|<>+=;'")
        nbentry_text = nbentry_text.translate(None, '"')
        # truncate to 13 characters
        nbentry_text = nbentry_text[:12:]
        return nbentry_text


    def on_soft_keyboard_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        self.touchscreen_enabled = widget.get_active()
        self.redis.hset('machine_prefs', 'touchscreen', self.touchscreen_enabled)
        self.UIobj.keyboard_checkbutton_toggled()


    def on_mouse_enter(self, widget, event, data=None):
        self.UIobj.on_mouse_enter(widget, event, data)


    def on_mouse_leave(self, widget, event, data=None):
        self.UIobj.on_mouse_leave(widget, event, data)


    def on_button_press_event(self, widget, event, data=None):
        self.UIobj.on_button_press_event(widget, event, data)


    def on_home_switches_checkbutton_toggled(self, widget, data=None):
        if not self.enable_home_switches_checkbutton_masked:
            self.home_switches_enabled = widget.get_active()
            self.UIobj.window.set_focus(None)
            if self.home_switches_enabled:
                if not self.UIobj.machineconfig.has_hard_stop_homing():
                    self.UIobj.builder.get_object("limits_text").set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits</span>')
                    lbl = self.UIobj.builder.get_object('limits_text_doorsw_enabled')
                    if lbl:
                        lbl.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits</span>')
            else:
                if self.UIobj.machineconfig.has_hard_stop_homing():
                    dialog = popupdlg.ok_cancel_popup(self.UIobj.window, NO_HSTOP_WARNING_MSG, cancel=False)
                else:
                    self.UIobj.builder.get_object("limits_text").set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits    (disabled)</span>')
                    lbl = self.UIobj.builder.get_object('limits_text_doorsw_enabled')
                    if lbl:
                        lbl.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >limits    (disabled)</span>')
                    dialog = popupdlg.ok_cancel_popup(self.UIobj.window, LIMIT_SWITCH_WARNING_MSG, cancel=False)
                dialog.run()
                dialog.destroy()
            self.UIobj.set_home_switches()


    def on_usbio_checkbutton_toggled(self, widget, data=None):
        if not self.enable_usbio_checkbutton_masked:
            self.UIobj.window.set_focus(None)
            self.usbio_enabled = widget.get_active()
            self.redis.hset('machine_prefs', 'usbio_enabled', self.usbio_enabled)
            self.UIobj.hal["usbio-enabled"] = self.usbio_enabled
            self.UIobj.usbio_e_message = True         # reset error message filter flag

            if self.usbio_enabled:
                # when enabling usbio, we need to give the hal user component some time to enumerate and update the
                # hal pins which let us know which boards are present.
                # only pop the plexy if we have made it through the full constructor and are up onscreen; else we are
                # still in constructor init phase so skip it.
                if singletons.g_Machine:
                    with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
                        time.sleep(1.0)
                else:
                    time.sleep(1.0)
                self.UIobj.show_usbio_interface()
            else:
                self.UIobj.hide_usbio_interface()


    def on_enable_tooltips_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        active = widget.get_active()
        self.redis.hset('uistate', 'extended_tooltips_enabled', active)
        if tooltipmgr.TTMgr():
            tooltipmgr.TTMgr().global_activate(active)



