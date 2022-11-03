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


class lathe_settings(ui_settings.common_settings):

    def __init__(self, UIobj, redis, gladefilename):

        ui_settings.common_settings.__init__(self, UIobj, redis, gladefilename)

        self.button_list = ('switch_to_mill',)
        # create dictionary of glade names, eventbox objects
        self.button_list = dict(((ix, self.builder.get_object(ix))) for ix in self.button_list)

        # get initial x/y locations for eventboxes
        for name, eventbox in self.button_list.iteritems():
            eventbox.x = ui_misc.get_x_pos(eventbox)
            eventbox.y = ui_misc.get_y_pos(eventbox)

        # ------------------------------------------------
        # Check buttons
        # ------------------------------------------------

        # checkbuttons on settings screen
        checkbutton_ids = ['use_atc_checkbutton',
                           'use_gang_tooling_checkbutton',
                           'use_manual_toolchange_checkbutton',
                           'use_5c_pulley_ratio_checkbutton',
                           'use_d1_4_chuck_pulley_checkbutton',
                           'g30m998_move_z_only_checkbutton',
                           'use_od_clamping_checkbutton',
                           'use_id_clamping_checkbutton',
                           'enable_feeds_speeds_checkbutton',
                           'enable_rapidturn_door_sw_checkbutton']

        for cb in checkbutton_ids:
            assert cb not in self.checkbutton_list, "Duplicate id found in common class"
            self.checkbutton_list[cb] = self.builder.get_object(cb)
            self.checkbutton_list[cb].modify_bg(gtk.STATE_PRELIGHT, UIobj._check_button_hilight_color)
        self.checkbutton_ids.extend(checkbutton_ids)

        # tool change type
        toolchange_type = self.redis.hget('machine_prefs', 'toolchange_type')
        if toolchange_type is None:
            toolchange_type = 'manual'

        self.tooling_checkbuttons_masked = True
        if 'atc' in toolchange_type:
            self.tool_changer_type = TOOL_CHANGER_TYPE_TURRET
            self.checkbutton_list['use_atc_checkbutton'].set_active(True)
        elif 'gang' in toolchange_type:
            self.tool_changer_type = TOOL_CHANGER_TYPE_GANG
            self.checkbutton_list['use_gang_tooling_checkbutton'].set_active(True)
        else:
            self.tool_changer_type = TOOL_CHANGER_TYPE_MANUAL
            self.checkbutton_list['use_manual_toolchange_checkbutton'].set_active(True)
        self.tooling_checkbuttons_masked = False

        # spindle range - high is pulleys with 5C, low is pulleys for D1-4 chuck
        # default to slower actual spindle speed if belt is not really in the low
        # position
        spindle_range = self.redis.hget('machine_prefs', 'spindle_range')
        if spindle_range is None:
            spindle_range = 'low'
            self.redis.hset('machine_prefs', 'spindle_range', spindle_range)
        if spindle_range not in ('low', 'high'):
            self.UIobj.error_handler.log("Unsupported lathe spindle type {:s}. Changing to low.".format(spindle_range))
            spindle_range = 'low'
        self.spindle_range_checkbuttons_masked = True
        if 'low' == spindle_range:
            self.spindle_range = 0
            self.checkbutton_list['use_d1_4_chuck_pulley_checkbutton'].set_active(True)
        else:
            self.spindle_range = 1
            self.checkbutton_list['use_5c_pulley_ratio_checkbutton'].set_active(True)
        self.spindle_range_checkbuttons_masked = False

        # Auto collet closer clamping style
        clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
        if clamping_style == None:
            # default to OD and write it to redis so it works next time
            # and remap for M10 and M11 knows what to do!
            clamping_style = 'OD'
            self.redis.hset('machine_prefs', 'auto_collet_closer_clamping_style', clamping_style)
        if clamping_style == 'OD':
            self.checkbutton_list['use_od_clamping_checkbutton'].set_active(True)
        else:
            self.checkbutton_list['use_id_clamping_checkbutton'].set_active(True)

        # lathe always has a door switch, rapidturn door switch is optional
        self.rapidturn_door_sw_enabled = self.redis.hget('machine_prefs', 'rapidturn_door_sw_enabled')
        if self.rapidturn_door_sw_enabled is None:
            self.rapidturn_door_sw_enabled = 'False'
            self.redis.hset('machine_prefs', 'rapidturn_door_sw_enabled', self.rapidturn_door_sw_enabled)
        self.rapidturn_door_sw_enabled = (self.rapidturn_door_sw_enabled == 'True')  # convert str to bool
        self.checkbutton_list['enable_rapidturn_door_sw_checkbutton'].set_active(self.rapidturn_door_sw_enabled)

        # hide rapidturn enclosure door switch checkbutton, show later in adjust_settings_for_rapidturn()
        self.checkbutton_list['enable_rapidturn_door_sw_checkbutton'].hide()
        self.checkbutton_list['enable_rapidturn_door_sw_checkbutton'].set_no_show_all(True)

        if self.UIobj.machineconfig.in_rapidturn_mode():
            self.checkbutton_list['use_manual_toolchange_checkbutton'].set_active(True)

        self.feeds_speeds_checkbutton_masked = True
        active = self.redis.hget('uistate', ui_settings.common_settings._FS_ENABLED_REDIS_KEY)
        if active is None:
            active = 'True'
            self.redis.hset('uistate', ui_settings.common_settings._FS_ENABLED_REDIS_KEY, active)  # default F&S to enabled
        self.checkbutton_list['enable_feeds_speeds_checkbutton'].set_active(active == 'True') # the toggled signal will be fired by this action for us
        self.feeds_speeds_checkbutton_masked = False


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


    def on_use_atc_checkbutton_toggled(self, widget, data=None):
        if not self.tooling_checkbuttons_masked:
            self.UIobj.window.set_focus(None)
            if widget.get_active():
                self.redis.hset('machine_prefs', 'toolchange_type', 'atc')
                self.tool_changer_type = TOOL_CHANGER_TYPE_TURRET
                self.UIobj.set_lathe_toolchange_type()


    def on_use_gang_tooling_checkbutton_toggled(self, widget, data=None):
        if not self.tooling_checkbuttons_masked:
            self.UIobj.window.set_focus(None)
            if widget.get_active():
                self.redis.hset('machine_prefs', 'toolchange_type', 'gang')
                self.tool_changer_type = TOOL_CHANGER_TYPE_GANG
                self.UIobj.set_lathe_toolchange_type()


    def on_use_manual_toolchange_checkbutton_toggled(self, widget, data=None):
        if not self.tooling_checkbuttons_masked:
            self.UIobj.window.set_focus(None)
            if widget.get_active():
                self.redis.hset('machine_prefs', 'toolchange_type', 'manual')
                self.tool_changer_type = TOOL_CHANGER_TYPE_MANUAL
                self.UIobj.set_lathe_toolchange_type()


    def on_use_5c_pulley_ratio_checkbutton_toggled(self, widget, data=None):
        if not self.spindle_range_checkbuttons_masked:
            self.UIobj.window.set_focus(None)
            if not self.UIobj.is_button_permitted(widget): return
            # we know we're already in a permitted state.  but only one that can't be captured there
            # is if the spindle is actually spinning right now.
            if self.UIobj.spindle_running():
                self.UIobj.error_handler.write("Cannot change spindle range while spindle is on", ALARM_LEVEL_MEDIUM)
                return

            if widget.get_active():
                self.spindle_range = 1
                self.redis.hset('machine_prefs', 'spindle_range', 'high')
                self.UIobj.set_lathe_spindle_range()


    def on_use_d1_4_chuck_pulley_checkbutton_toggled(self, widget, data=None):
        if not self.spindle_range_checkbuttons_masked:
            self.UIobj.window.set_focus(None)
            if not self.UIobj.is_button_permitted(widget): return
            # we know we're already in a permitted state.  but only one that can't be captured there
            # is if the spindle is actually spinning right now.
            if self.UIobj.spindle_running():
                self.UIobj.error_handler.write("Cannot change spindle range while spindle is on", ALARM_LEVEL_MEDIUM)
                return

            if widget.get_active():
                self.spindle_range = 0
                self.redis.hset('machine_prefs', 'spindle_range', 'low')
                self.UIobj.set_lathe_spindle_range()


    def on_switch_to_mill_button_release_event(self, widget, data=None):
        if not self.UIobj.is_button_permitted(widget): return
        self.UIobj.switch_to_mill()


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
            fixed = self.builder.get_object('alarms_fixed')
            for child in fixed.get_children():
                if child.get_name() == 'door_lock_led_evtbox':
                    create_lock_led = False
                    break
            if create_lock_led:
                # slide text label evt box to the left to make room for the lock text and led
                fixed.move(self.builder.get_object('door_sw_text_evtbox'), 760, 135)
                self.builder.get_object('door_sw_text').set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >door    locked  /  open :</span>')

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
                box.show()

        self.UIobj.window.set_focus(None)
        self.UIobj.show_or_hide_limit_leds()
        self.UIobj.show_or_hide_door_sw_led()


    def on_g30m998_move_z_only_checkbutton_toggled(self, widget, data=None):
        self.g30m998_move_z_only = widget.get_active()
        self.redis.hset('machine_prefs', 'g30m998_move_z_only', self.g30m998_move_z_only)
        self.UIobj.window.set_focus(None)


    def on_use_od_clamping_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        if widget.get_active():
            self.UIobj.error_handler.log("Changing auto collet closer clamping style to OD")
            self.redis.hset('machine_prefs', 'auto_collet_closer_clamping_style', 'OD')
            # clear this so that the next periodic run sets the visual appearance
            # of the collet clamped button correctly.
            self.UIobj.prev_collet_closer_status = 2  # can't possibly match the hal bit pin value of 0 or 1


    def on_use_id_clamping_checkbutton_toggled(self, widget, data=None):
        self.UIobj.window.set_focus(None)
        if widget.get_active():
            self.UIobj.error_handler.log("Changing auto collet closer clamping style to ID")
            self.redis.hset('machine_prefs', 'auto_collet_closer_clamping_style', 'ID')
            # clear this so that the next periodic run sets the visual appearance
            # of the collet clamped button correctly.
            self.UIobj.prev_collet_closer_status = 2 # can't possibly match the hal bit pin value of 0 or 1


    def on_rapidturn_door_sw_checkbutton_toggled(self, widget, data=None):
        self.rapidturn_door_sw_enabled = widget.get_active()
        self.UIobj.hal['rapidturn-door-switch-enabled'] = self.rapidturn_door_sw_enabled
        self.redis.hset('machine_prefs', 'rapidturn_door_sw_enabled', self.rapidturn_door_sw_enabled)
        self.UIobj.window.set_focus(None)


    def adjust_settings_for_rapidturn(self):
        # switch to mill button
        self.button_list['switch_to_mill'].show()
        self.button_list['switch_to_mill'].set_sensitive(True)
        self.builder.get_object("switch_to_mill_image").set_visible(True)

        # hide the turret choice on the settings screen (which hides the turret button too)
        self.builder.get_object('use_atc_checkbutton').hide()

        # show rapidturn enclosure door switch checkbutton
        self.checkbutton_list['enable_rapidturn_door_sw_checkbutton'].show()

        # change labels on lo/hi spindle checkboxes
        self.builder.get_object('use_5c_pulley_ratio_text').set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="white" >High Speed</span>')
        self.builder.get_object('use_d1_4_pulley_ratio_text').set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="white" >Low Speed</span>')

        # rapidturn is always fixed to OD clamping.  This way the hal files can
        # force digital P21 to always be the correct value so that M3 and M4 remaps
        # always believe the collet is clamped so they don't block spindle starts.
        self.redis.hset('machine_prefs', 'auto_collet_closer_clamping_style', 'OD')

        # hide the collet clamping style options on the Settings tab.
        self.builder.get_object('settings_collet_clamper_text').hide()
        # this makes sure that later show_all() methods don't end up overriding our state and revealing it
        self.builder.get_object('settings_collet_clamper_text').set_no_show_all(True)

        self.checkbutton_list['use_od_clamping_checkbutton'].hide()
        self.checkbutton_list['use_od_clamping_checkbutton'].set_no_show_all(True)
        self.checkbutton_list['use_id_clamping_checkbutton'].hide()
        self.checkbutton_list['use_id_clamping_checkbutton'].set_no_show_all(True)

