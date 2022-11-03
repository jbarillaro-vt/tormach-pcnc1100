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
import ui_settings
import ui_misc



class common_mill_settings(ui_settings.common_settings):

    def __init__(self, UIobj, redis, gladefilename):

        ui_settings.common_settings.__init__(self, UIobj, redis, gladefilename)

        # ------------------------------------------------
        # Check buttons
        # ------------------------------------------------

        checkbutton_ids = ['use_manual_toolchange_checkbutton',
                           'use_atc_checkbutton',
                           'enable_scanner_checkbutton',
                           'g30m998_move_z_only_checkbutton',
                           'fourth_axis_type_combobox',
                           'enable_feeds_speeds_checkbutton']

        for cb in checkbutton_ids:
            assert cb not in self.checkbutton_list, "Duplicate id found in common class"
            self.checkbutton_list[cb] = self.builder.get_object(cb)
            self.checkbutton_list[cb].modify_bg(gtk.STATE_PRELIGHT, UIobj._check_button_hilight_color)
        self.checkbutton_ids.extend(checkbutton_ids)

        # spindle type and min/max for high speed spindle type
        spindle_type = self.UIobj.machineconfig.supported_spindle_list()[0]   # default to first in the list
        spindle_type_str = self.redis.hget('machine_prefs', 'spindle_type')
        if spindle_type_str:
            if int(spindle_type_str) in self.UIobj.machineconfig.supported_spindle_list():
                spindle_type = int(spindle_type_str)
            else:
                self.UIobj.error_handler.write('Spindle type found in redis {:s} is not supported on this model. Defaulting to {:d}.'.format(spindle_type_str, spindle_type), ALARM_LEVEL_DEBUG)

        self.spindle_type = spindle_type
        self.UIobj.error_handler.write('Spindle type: %d' % self.spindle_type, ALARM_LEVEL_DEBUG)

        self.g30m998_move_z_only = True
        self.feeds_speeds_checkbutton_masked = False
        self.door_sw_enabled = False

        self.checkbutton_list['fourth_axis_type_combobox'].set_property("has-tooltip", True)
        self.checkbutton_list['fourth_axis_type_combobox'].connect("query-tooltip", self.on_combobox_querytooltip)

        # 4th axis type combobox
        self.fourth_axis_type_liststore = gtk.ListStore(str, str)
        # pull current configuration from A_Axisconfig().selected() and use to set combobox
        self.checkbutton_list['fourth_axis_type_combobox'].set_model(self.fourth_axis_type_liststore)
        cell = gtk.CellRendererText()
        self.checkbutton_list['fourth_axis_type_combobox'].pack_start(cell, True)
        self.checkbutton_list['fourth_axis_type_combobox'].add_attribute(cell, 'text', 0)

        #fetch all 4th axis devices from machineconfig in human string form and use to populate combobox
        for axis_key in self.UIobj.machineconfig.a_axis._accessory_list:
            value = self.UIobj.machineconfig.a_axis.redis_to_human(axis_key)
            row_iter = self.fourth_axis_type_liststore.append([value, axis_key])
            # If this is the item that should be selected
            if axis_key == self.UIobj.machineconfig.a_axis.selected():
                self.checkbutton_list['fourth_axis_type_combobox'].set_active_iter(row_iter)

        # this next call to set the appropriate active state of the scanner checkbutton SHOULD be in init,
        # but for some unknown reason if the argument to set_active was False, the realize event of the
        # notebook would fail to connect to the show_enabled_notebook_tabs method.  This workaround is a band aid
        # for this problem.
        self.injector_enabled = False
        self.scanner_enabled = (self.redis.hget('machine_prefs', 'scanner_enabled') == 'True')
        self.checkbutton_list['enable_scanner_checkbutton'].set_active(self.scanner_enabled)

        self.feeds_speeds_checkbutton_masked = True
        active = self.redis.hget('uistate', ui_settings.common_settings._FS_ENABLED_REDIS_KEY)
        if active is None:
            active = 'True'
            self.redis.hset('uistate', ui_settings.common_settings._FS_ENABLED_REDIS_KEY, active)  # default F&S to enabled
        self.checkbutton_list['enable_feeds_speeds_checkbutton'].set_active(active == 'True') # the toggled signal will be fired by this action for us
        self.feeds_speeds_checkbutton_masked = False

        self.UIobj.door_lock_led_evtbox = None

        builder = self.UIobj.builder  # the primary UI builder that has the Status tab widgets
        builder.get_object('limits_text').set_no_show_all(True)
        builder.get_object('limits_text_doorsw_enabled').set_no_show_all(True)
        builder.get_object('x_limit_led').set_no_show_all(True)
        builder.get_object('y_limit_led').set_no_show_all(True)
        builder.get_object('z_limit_led').set_no_show_all(True)
        builder.get_object('x_limit_text').set_no_show_all(True)
        builder.get_object('y_limit_text').set_no_show_all(True)
        builder.get_object('z_limit_text').set_no_show_all(True)
        builder.get_object('door_sw_text').set_no_show_all(True)
        builder.get_object('door_sw_led_evtbox').set_no_show_all(True)
        builder.get_object('door_sw_led').set_no_show_all(True)
        builder.get_object('door_sw_text_evtbox').set_no_show_all(True)


    def on_4th_axis_type_combobox_changed(self,widget, data=None):
        if tooltipmgr.TTMgr():
            tooltipmgr.TTMgr().on_mouse_leave(widget)
        axis_index = widget.get_active_iter()
        if axis_index != None:
            axis_redis_value = self.fourth_axis_type_liststore.get_value(axis_index, 1)
            self.UIobj.machineconfig.a_axis.select(axis_redis_value)


    def on_use_atc_checkbutton_toggled(self, widget, data=None):
        if widget.get_active():
            if self.spindle_type == SPINDLE_TYPE_HISPEED:
                self.checkbutton_list['use_manual_toolchange_checkbutton'].set_active(True)
                self.UIobj.error_handler.write('Cannot use high speed spindle and ATC. Disabling ATC.')
            else:
                self.UIobj.error_handler.log("Tool change type changed to ATC")
                page = self.UIobj.builder.get_object('atc_fixed')
                page.show()
                self.UIobj.atc.enable()
                self.UIobj.atc_hardware_check_stopwatch.restart()
                self.UIobj.only_one_cable_warning = True  #re-notify bad  cable connections
                self.UIobj.show_atc_diagnostics()


    def on_use_manual_toolchange_checkbutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.UIobj.error_handler.log("Tool change type changed to Manual")
            page = self.UIobj.builder.get_object('atc_fixed')
            page.hide()
            self.UIobj.atc.disable()
            self.UIobj.hide_atc_diagnostics()


    def on_g30m998_move_z_only_checkbutton_toggled(self, widget, data=None):
        self.g30m998_move_z_only = widget.get_active()
        self.redis.hset('machine_prefs', 'g30m998_move_z_only', self.g30m998_move_z_only)
        self.UIobj.window.set_focus(None)


    def configure_g30_settings(self):
        # g30/m998 move in Z only
        self.g30m998_move_z_only = True
        try:
            redis_response = self.redis.hget('machine_prefs', 'g30m998_move_z_only')
            if redis_response == 'True' or redis_response == None:
                self.g30m998_move_z_only = True
            else:
                self.g30m998_move_z_only = False
        except:
            self.UIobj.error_handler.write("exception looking for 'machine_prefs', 'g30m998_move_z_only' in redis, defaulting to True", ALARM_LEVEL_LOW)
            # write to redis to avoid future messages
            self.redis.hset('machine_prefs', 'g30m998_move_z_only', 'True')

        self.checkbutton_list['g30m998_move_z_only_checkbutton'].set_active(self.g30m998_move_z_only)


    def show_or_hide_door_sw_led(self):
        if self.door_sw_enabled:
            self.UIobj.builder.get_object('door_sw_led_evtbox').show()
            self.UIobj.image_list['door_sw_led'].show()
            if self.UIobj.machineconfig.has_door_lock():
                if self.UIobj.door_lock_led_evtbox:
                    self.UIobj.door_lock_led_evtbox.show()
                self.UIobj.image_list['door_lock_led'].show()
            self.UIobj.builder.get_object('door_sw_text_evtbox').show()
            self.UIobj.builder.get_object('door_sw_text').show()
        else:
            self.UIobj.builder.get_object('door_sw_led_evtbox').hide()
            self.UIobj.image_list['door_sw_led'].hide()
            if self.UIobj.machineconfig.has_door_lock():
                if self.UIobj.door_lock_led_evtbox:
                    self.UIobj.door_lock_led_evtbox.hide()
                self.UIobj.image_list['door_lock_led'].hide()
            self.UIobj.builder.get_object('door_sw_text_evtbox').hide()
            self.UIobj.builder.get_object('door_sw_text').hide()


    def show_or_hide_limit_leds(self):
        builder = self.UIobj.builder  # the primary UI builder that has the Status tab widgets

        if self.UIobj.machineconfig.has_limit_switches():
            # Machines with ECM1 boards with plenty of inputs so we don't need to
            # multiplex x and y limit switches anymore.
            if self.door_sw_enabled and self.UIobj.machineconfig.shared_xy_limit_input():
                # hide X limit LED on status screen, change label for Y to show the two are netted together
                builder.get_object('limits_text').hide()
                builder.get_object('limits_text_doorsw_enabled').show()
                builder.get_object('x_limit_led').hide()
                builder.get_object('x_limit_text').hide()
                builder.get_object('y_limit_text').set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >x/y:</span>')
            else:
                builder.get_object('limits_text').show()
                builder.get_object('limits_text_doorsw_enabled').hide()
                builder.get_object('x_limit_led').show()
                builder.get_object('x_limit_text').show()
                builder.get_object('y_limit_text').set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >y:</span>')

        else:
            builder.get_object('limits_text').hide()
            builder.get_object('limits_text_doorsw_enabled').hide()
            builder.get_object('x_limit_led').hide()
            builder.get_object('y_limit_led').hide()
            builder.get_object('z_limit_led').hide()
            builder.get_object('x_limit_text').hide()
            builder.get_object('y_limit_text').hide()
            builder.get_object('z_limit_text').hide()


    def on_feeds_speeds_checkbutton_toggled(self, widget, data=None):
        if not self.feeds_speeds_checkbutton_masked:
            is_active = widget.get_active()

            # this is a hack on top of a hack.  really the proxy object should wrap the true fs object and just pass through
            # calls when enabled and do nothing when disabled.  but looking at the code, that looks fragile and it could
            # introduce a bunch of subtle bugs so we just stick with the game of swapping out fs_mgr object references
            if is_active:
                self.UIobj.fs_mgr = self.UIobj.fs_mgr.fs
            else:
                self.UIobj.fs_mgr = self.UIobj.fs_mgr.fs_proxy

            self.redis.hset('uistate', ui_settings.common_settings._FS_ENABLED_REDIS_KEY, str(is_active))
            self.UIobj.material_data.enable(is_active)
            self.UIobj.window.set_focus(None)


    def on_combobox_querytooltip(self, widget, x, y, keyboard_mode, tooltip, data=None):
        ev = gtk.gdk.Event(gtk.gdk.ENTER_NOTIFY)
        display = gtk.gdk.display_get_default()
        screen, xroot, yroot, mod = display.get_pointer()
        ev.x_root = float(xroot)
        ev.y_root = float(yroot)
        if tooltipmgr.TTMgr():
            tooltipmgr.TTMgr().on_mouse_enter(widget, ev)
        return False


    def on_scanner_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        self.scanner_enabled = widget.get_active()
        self.redis.hset('machine_prefs', 'scanner_enabled', self.scanner_enabled)
        self.UIobj.show_hide_scanner_page(show=self.scanner_enabled)





class mill_settings(common_mill_settings):

    def __init__(self, UIobj, redis, gladefilename):

        common_mill_settings.__init__(self, UIobj, redis, gladefilename)

        self.button_list = ('switch_to_lathe',)
        # create dictionary of glade names, eventbox objects
        self.button_list = dict(((ix, self.builder.get_object(ix))) for ix in self.button_list)

        # get initial x/y locations for eventboxes
        for name, eventbox in self.button_list.iteritems():
            eventbox.x = ui_misc.get_x_pos(eventbox)
            eventbox.y = ui_misc.get_y_pos(eventbox)

        # ------------------------------------------------
        # Check buttons
        # ------------------------------------------------

        checkbutton_ids = ['passive_probe_radiobutton',
                           'active_probe_radiobutton',
                           'enable_injector_checkbutton',
                           'enable_door_sw_checkbutton',
                           'fourth_axis_homing_checkbutton',
                           'spindle_type_combobox']

        for cb in checkbutton_ids:
            assert cb not in self.checkbutton_list, "Duplicate id found in common class"
            self.checkbutton_list[cb] = self.builder.get_object(cb)
            self.checkbutton_list[cb].modify_bg(gtk.STATE_PRELIGHT, UIobj._check_button_hilight_color)
        self.checkbutton_ids.extend(checkbutton_ids)


        self.checkbutton_list['spindle_type_combobox'].set_property("has-tooltip", True)
        self.checkbutton_list['spindle_type_combobox'].connect("query-tooltip", self.on_combobox_querytooltip)


        speed_str = self.redis.hget('machine_prefs', 'spindle_hispeed_min')
        if speed_str:
            self.spindle_hispeed_min = int(speed_str)
        else:
            self.spindle_hispeed_min = self.UIobj.ini_int('SPINDLE', 'HISPEED_MIN', 1000)
        self.spindle_hispeed_min_entry = self.builder.get_object('spindle_hispeed_min_entry')
        self.spindle_hispeed_min_entry.set_text('%d' % self.spindle_hispeed_min)

        speed_str = self.redis.hget('machine_prefs', 'spindle_hispeed_max')
        if speed_str:
            self.spindle_hispeed_max = int(speed_str)
        else:
            self.spindle_hispeed_max = self.UIobj.ini_int('SPINDLE', 'HISPEED_MAX', 24000)
        self.spindle_hispeed_max_entry = self.builder.get_object('spindle_hispeed_max_entry')
        self.spindle_hispeed_max_entry.set_text('%s' % self.spindle_hispeed_max)

        # spindle type combobox
        self.spindle_type_liststore = gtk.ListStore(str, int)
        self.spindle_type_combobox = self.builder.get_object("spindle_type_combobox")
        self.spindle_type_combobox.set_model(self.spindle_type_liststore)
        cell = gtk.CellRendererText()
        self.spindle_type_combobox.pack_start(cell, True)
        self.spindle_type_combobox.add_attribute(cell, 'text', 0)

        spindle_list = self.UIobj.machineconfig.supported_spindle_list()
        if SPINDLE_TYPE_STANDARD in spindle_list:
            self.spindle_type_liststore.append(['Standard', SPINDLE_TYPE_STANDARD])
        if SPINDLE_TYPE_SPEEDER in spindle_list:
            self.spindle_type_liststore.append(['Speeder', SPINDLE_TYPE_SPEEDER])
        if SPINDLE_TYPE_HISPEED in spindle_list:
            self.spindle_type_liststore.append(['High-speed', SPINDLE_TYPE_HISPEED])

        self.spindle_type_combobox.set_property("has-tooltip", True)
        ix = 0
        for row in self.spindle_type_liststore:
            if row[1] == self.spindle_type:
                self.spindle_type_combobox.set_active(ix)
            ix +=1

        self.make_hispeed_min_max_visible(self.spindle_type)

        self.probe_active_high = (self.redis.hget('machine_prefs', 'probe_active_high') == 'True')
        if self.probe_active_high:
            self.checkbutton_list['active_probe_radiobutton'].set_active(True)
        else:
            self.checkbutton_list['passive_probe_radiobutton'].set_active(True)

        # TODO:  IS there a todo here with new A/4th axis config?
        # 4th axis homing
        self.fourth_axis_homing_enabled = self.redis.hget('machine_prefs', 'fourth_axis_homing_enabled') == "True"
        # set 4th axis homing parameters
        self.UIobj.set_4th_axis_homing_parameters(self.fourth_axis_homing_enabled)
        # set the checkbutton status
        self.checkbutton_list['fourth_axis_homing_checkbutton'].set_active(self.fourth_axis_homing_enabled)

        try:
            self.injector_enabled = self.redis.hget('machine_prefs', 'injector_enabled') == 'True'
        except:
            self.UIobj.error_handler.write("exception looking for 'machine_prefs', 'injector_enabled' in redis, defaulting to False", ALARM_LEVEL_LOW)
            # write to redis to avoid future messages
            self.redis.hset('machine_prefs', 'injector_enabled', 'False')
        self.checkbutton_list['enable_injector_checkbutton'].set_active(self.injector_enabled)

        self.door_sw_enabled = self.redis.hget('machine_prefs', 'door_sw_enabled')
        if self.door_sw_enabled is None:
            self.door_sw_enabled = 'False'
            self.redis.hset('machine_prefs', 'door_sw_enabled', self.door_sw_enabled)
        self.door_sw_enabled = (self.door_sw_enabled == 'True')
        self.checkbutton_list['enable_door_sw_checkbutton'].set_active(self.door_sw_enabled)

        try:
            disable_door_sw_checkbutton = self.redis.hget('machine_prefs', 'door_sw_hard_enabled') == 'True'
        except:
            self.UIobj.error_handler.write("exception looking for 'machine_prefs', 'door_sw_hard_enabled' in redis, defaulting to False", ALARM_LEVEL_LOW)
            # write to redis to avoid future messages
            self.redis.hset('machine_prefs', 'door_sw_hard_enabled', 'False')

        if disable_door_sw_checkbutton:
            self.UIobj.error_handler.write("door_sw_hard_enabled is True in redis so forcing the switch enabled and removing settings option.", ALARM_LEVEL_DEBUG)
            self.door_sw_enabled = True
            self.checkbutton_list['enable_door_sw_checkbutton'].set_visible(False)
            # this makes sure that later show_all() methods don't end up overriding our state and revealing the checkbox
            self.checkbutton_list['enable_door_sw_checkbutton'].set_no_show_all(True)

        # force enclosure door switch enabled True and hide check box on Settings tab
        # for machines that always have the door switch wired even if not present
        # e.g. 440 and others
        if self.UIobj.machineconfig.always_has_door_switch_wired():
            self.door_sw_enabled = True
            self.UIobj.hal['enc-door-switch-enabled'] = 1
            self.checkbutton_list['enable_door_sw_checkbutton'].set_no_show_all(True)
            self.checkbutton_list['enable_door_sw_checkbutton'].hide()
            self.builder.get_object('enable_door_sw_text').set_no_show_all(True)
            self.builder.get_object('enable_door_sw_text').hide()


    def make_hispeed_min_max_visible(self, spindle_type):
        # if hispeed spindle selected - make min/max fields visible
        # ALWAYS HIDE THESE
        if False and spindle_type == SPINDLE_TYPE_HISPEED:
            self.builder.get_object("hispeed_min_label").set_visible(True)
            self.builder.get_object("hispeed_max_label").set_visible(True)
            self.builder.get_object("spindle_hispeed_min_entry").set_visible(True)
            self.builder.get_object("spindle_hispeed_max_entry").set_visible(True)
        else:
            self.builder.get_object("hispeed_min_label").set_visible(False)
            self.builder.get_object("hispeed_max_label").set_visible(False)
            self.builder.get_object("spindle_hispeed_min_entry").set_visible(False)
            self.builder.get_object("spindle_hispeed_max_entry").set_visible(False)


    def on_injector_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        self.injector_enabled = widget.get_active()
        self.redis.hset('machine_prefs', 'injector_enabled', self.injector_enabled)
        self.UIobj.show_hide_injector_page(show=self.injector_enabled)


    def on_door_sw_checkbutton_toggled(self, widget, data=None):
        self.door_sw_enabled = widget.get_active()

        if self.door_sw_enabled and (self.redis.hget('machine_prefs', 'door_sw_enabled') == 'False'):
            if self.UIobj.machineconfig.shared_xy_limit_input():
                # we've just gone from disabled to enabled, so show a warning next time we ref x
                # BUT these machines have plenty of IO so don't have the overlapped wiring warning
                # need so don't enable it here.
                self.redis.hset('machine_prefs', 'display_door_sw_x_ref_warning', 'True')

        self.UIobj.hal['enc-door-switch-enabled'] = self.door_sw_enabled
        self.redis.hset('machine_prefs', 'door_sw_enabled', self.door_sw_enabled)

        # create the extra Status LED for the door lock if we have one for easy troubleshooting.
        if self.UIobj.machineconfig.has_door_lock():
            # only create the lock led if we haven't already
            create_lock_led = True
            fixed = self.UIobj.builder.get_object('alarms_fixed')
            for child in fixed.get_children():
                if child.get_name() == 'door_lock_led_evtbox':
                    create_lock_led = False
                    break
            if create_lock_led:
                # slide text label evt box to the left to make room for the lock text and led
                fixed.move(self.UIobj.builder.get_object('door_sw_text_evtbox'), 760, 135)
                self.UIobj.builder.get_object('door_sw_text').set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >door    locked  /  open :</span>')

                # create the second lock led and evt box for tool tip - line it up with Y limits LED - that is at 920,15
                box = gtk.EventBox()
                self.UIobj.set_indicator_led('door_lock_led', False)
                led_image = self.UIobj.image_list['door_lock_led']
                w = led_image.get_pixbuf().get_width()
                h = led_image.get_pixbuf().get_height()
                box.set_size_request(w, h)
                box.add(led_image)
                # an "invisible" window means that the eventbox only traps events, and does not appear to the user directly.
                box.set_visible_window(False)
                box.set_name('door_lock_led_evtbox')
                box.connect("enter-notify-event", self.UIobj.on_mouse_enter)
                box.connect("leave-notify-event", self.UIobj.on_mouse_leave)
                fixed.put(box, 930, 142)
                self.UIobj.door_lock_led_evtbox = box
                box.set_no_show_all(True)
                box.show()

        self.UIobj.window.set_focus(None)
        self.show_or_hide_limit_leds()
        self.show_or_hide_door_sw_led()


    def on_fourth_axis_homing_checkbutton_toggled(self, widget, data=None):
        self.fourth_axis_homing_enabled = widget.get_active()
        self.UIobj.set_4th_axis_homing_parameters(self.fourth_axis_homing_enabled)
        self.redis.hset('machine_prefs', 'fourth_axis_homing_enabled', self.fourth_axis_homing_enabled)
        self.UIobj.window.set_focus(None)


    def on_switch_to_lathe_button_release_event(self, widget, data=None):
        if not self.UIobj.is_button_permitted(widget): return
        self.UIobj.switch_to_lathe()


    # these two radio buttons are a group
    def on_passive_probe_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.probe_active_high = False
            self.redis.hset('machine_prefs', 'probe_active_high', self.probe_active_high)
            self.UIobj.hal['probe-active-high'] = self.probe_active_high
            self.UIobj.window.set_focus(None)


    def on_active_probe_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.probe_active_high = True
            self.redis.hset('machine_prefs', 'probe_active_high', self.probe_active_high)
            self.UIobj.hal['probe-active-high'] = self.probe_active_high
            self.UIobj.window.set_focus(None)
    ## end group ##


    def on_spindle_type_combobox_changed(self, widget, data=None):
        if tooltipmgr.TTMgr():
            tooltipmgr.TTMgr().on_mouse_leave(widget)

        ix = widget.get_active()

        # each row in the list store is a string and the int constant for the spindle
        # so the [1] below plucks out the spindle type constant from the row.
        self.spindle_type = self.spindle_type_liststore[ix][1]
        self.UIobj.error_handler.log("Spindle type changed to: {}".format(self.spindle_type_liststore[ix][0]))
        self.UIobj.hal['spindle-type'] = self.spindle_type
        # make persistent
        self.redis.hset('machine_prefs', 'spindle_type', '%d' % self.spindle_type)
        self.make_hispeed_min_max_visible(self.spindle_type)

        if (self.spindle_type == SPINDLE_TYPE_HISPEED and self.checkbutton_list['use_atc_checkbutton'].get_active()):
            self.checkbutton_list['use_manual_toolchange_checkbutton'].set_active(True)
            self.UIobj.error_handler.write('Cannot use high speed spindle and ATC. Disabling ATC.')


    def on_spindle_hispeed_min_entry_activate(self, widget, data=None):
        (is_valid, value) = ui_misc.is_number(widget.get_text())
        if (not is_valid):
            # clear entry
            widget.set_text('%d' % self.spindle_hispeed_min)
        else:
            self.spindle_hispeed_min = abs(value)
            widget.set_text('%d' % self.spindle_hispeed_min)

        self.UIobj.hal['spindle-hispeed-min'] = self.spindle_hispeed_min
        self.redis.hset('machine_prefs', 'spindle_hispeed_min', '%d' % self.spindle_hispeed_min)
        self.UIobj.window.set_focus(None)


    def on_spindle_hispeed_max_entry_activate(self, widget, data=None):
        (is_valid, value) = ui_misc.is_number(widget.get_text())
        if (not is_valid):
            # clear entry
            widget.set_text('%d' % self.spindle_hispeed_max)
        else:
            self.spindle_hispeed_max = abs(value)
            widget.set_text('%d' % self.spindle_hispeed_max)

        self.UIobj.hal['spindle-hispeed-max'] = self.spindle_hispeed_max
        self.redis.hset('machine_prefs', 'spindle_hispeed_max', '%d' % self.spindle_hispeed_max)
        self.UIobj.window.set_focus(None)




class mill_440_settings(common_mill_settings):

    def __init__(self, UIobj, redis, gladefilename):

        common_mill_settings.__init__(self, UIobj, redis, gladefilename)

        self.button_list = ()
        # create dictionary of glade names, eventbox objects
        self.button_list = dict(((ix, self.builder.get_object(ix))) for ix in self.button_list)

        # get initial x/y locations for eventboxes
        for name, eventbox in self.button_list.iteritems():
            eventbox.x = ui_misc.get_x_pos(eventbox)
            eventbox.y = ui_misc.get_y_pos(eventbox)

        # has to exist just to keep other code common
        self.spindle_hispeed_min = 0
        self.spindle_hispeed_max = 0

        # hard coded to passive probe only due to leadshine mx board input
        self.probe_active_high = False
        self.UIobj.hal['probe-active-high'] = self.probe_active_high

        self.door_sw_enabled = True
        self.UIobj.hal['enc-door-switch-enabled'] = 1

        self.show_or_hide_door_sw_led()
        self.show_or_hide_limit_leds()
