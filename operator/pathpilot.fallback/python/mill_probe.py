# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import glib
import os
import sys
import pango

from constants import *
import errors
from conversational import cparse

import probing

class mill_probe():
    def __init__(self, UIobj, redis, linuxcnc_status, issue_mdi, gladefilename):

        self.UIobj = UIobj
        self.redis = redis
        self.status = linuxcnc_status
        self.issue_mdi = issue_mdi
        self.gladefilename = gladefilename

        # no easy access to the mill/lathe error handler instance this early, UI sets it later

        # Always use gtk.WINDOW_TOPLEVEL. The gtk.DIALOG_MODAL flag is only for use with gtk.Dialog objects, not gtk.Window objects!
        # If used by accident here, it causes the blinking text editing insert caret/cursor to be invisible.
        # That's a fun bug to track down...
        # And don't use WINDOW_POPUP, that's for GTK menus and tool tips, not dialogs.

        self.builder = gtk.Builder()

        gladefile = os.path.join(GLADE_DIR, self.gladefilename)

        if self.builder.add_objects_from_file(gladefile, ['probe_tab_label', 'probe_fixed']) == 0:
            raise RuntimeError("GtkBuilder failed")

        missingSignals = self.builder.connect_signals(self)
        if missingSignals is not None:
            raise RuntimeError("Cannot connect signals: ", missingSignals)

        self.fixed = self.builder.get_object("probe_fixed")
        if self.fixed == None:
            raise RuntimeError("Cannot find object: ", "probe_fixed")

        self.tab_label = self.builder.get_object("probe_tab_label")
        if self.tab_label == None:
            raise RuntimeError("Cannot find object: ", "probe_tab_label")

        self.notebook = self.builder.get_object("probe_notebook")
        if self.notebook == None:
            raise RuntimeError("Cannot find object: ", "probe_notebook")

        self.probe_active_corner = 'nw'
        self.probe_active_inner_corner = 'nw'
        self.measured_probe_ring_gauge_diameter = self.prev_measured_probe_ring_gauge_diameter = -1.0
        self.prev_probe_tip_effective_diameter = -99999.0

        # gtk.eventboxes
        self.button_list = (
                            'probe_find_corner', 'probe_find_inner_corner',
                            'probe_x_plus', 'probe_x_minus',
                            'probe_y_plus', 'probe_y_minus',
                            'probe_z_minus',
                            'probe_y_plus_a', 'probe_y_plus_b', 'probe_y_plus_c',
                            'probe_find_rect_boss_center', 'probe_find_circ_boss_center',
                            'probe_find_pocket_center', 'probe_find_pocket_x_center', 'probe_find_pocket_y_center',
                            'probe_set_probe_length', 'probe_a_axis_center', 'probe_change_corner', 'probe_change_inner_corner',
                            'probe_set_gauge_ref',
                            'probe_origin_x_plus', 'probe_origin_x_minus',
                            'probe_origin_y_plus', 'probe_origin_y_minus',
                            'probe_origin_z_minus',
                            'move_and_set_probe_tip_diameter'
            )

        self.dro_list = (
                            'probe_fine_feedrate_dro',
                            'probe_rough_feedrate_dro',
                            'probe_rapid_feedrate_dro',
                            'probe_tip_effective_dia_dro',
                            'probe_ring_gauge_dia_dro',
                            'ets_height_dro',
            )

        self.dro_list = dict(((i, self.builder.get_object(i))) for i in self.dro_list)

        self.dro_font  = pango.FontDescription('helvetica ultra-condensed 22')
        for name, dro in self.dro_list.iteritems():
            dro.modify_font(self.dro_font)
            dro.masked = False

        self.probe_x_plus_label  = self.builder.get_object('probe_x_plus_label')
        self.probe_x_minus_label = self.builder.get_object('probe_x_minus_label')
        self.probe_y_plus_label  = self.builder.get_object('probe_y_plus_label')
        self.probe_y_minus_label = self.builder.get_object('probe_y_minus_label')
        self.probe_z_minus_label = self.builder.get_object('probe_z_minus_label')
        self.probe_y_plus_a_label = self.builder.get_object('probe_y_plus_a_label')
        self.probe_y_plus_b_label = self.builder.get_object('probe_y_plus_b_label')
        self.probe_y_plus_c_label = self.builder.get_object('probe_y_plus_c_label')

        self.probe_x_plus_label.modify_font(self.dro_font)
        self.probe_x_minus_label.modify_font(self.dro_font)
        self.probe_y_plus_label.modify_font(self.dro_font)
        self.probe_y_minus_label.modify_font(self.dro_font)
        self.probe_z_minus_label.modify_font(self.dro_font)
        self.probe_y_plus_a_label.modify_font(self.dro_font)
        self.probe_y_plus_b_label.modify_font(self.dro_font)
        self.probe_y_plus_c_label.modify_font(self.dro_font)

        self.button_list = dict(((i, self.builder.get_object(i))) for i in self.button_list)

        # persistent settings

        # probe feedrates and ring gauge diameter
        self.max_probe_fine_feedrate = MAX_PROBE_FINE_FEEDRATE
        self.max_probe_rough_feedrate = MAX_PROBE_ROUGH_FEEDRATE
        self.max_probe_rapid_feedrate = MAX_PROBE_RAPID_FEEDRATE
        self.probe_fine_feedrate = DEFAULT_PROBE_FINE_FEEDRATE
        self.probe_rough_feedrate = DEFAULT_PROBE_ROUGH_FEEDRATE
        self.probe_ring_gauge_diameter = DEFAULT_PROBE_RING_GAUGE_DIAMETER

        self.probing = probing.probing(self, self.status, self.issue_mdi)

    def set_error_handler(self, error_handler):
        self.error_handler = error_handler
        self.probing.error_handler = error_handler

    def read_persistent_storage(self):
        try:
            self.ets_height = float(self.redis.hget('machine_prefs', 'setter_height'))
        except:
            # default 80 mm
            # TODO: default should be different dependent on machine ETS model
            self.ets_height = 80.0 / 25.4
            self.redis.hset('machine_prefs', 'setter_height', self.ets_height)

        # probe fine feedrate
        if self.redis.hexists('machine_prefs', 'probe_fine_feed_per_minute'):
            self.probe_fine_feedrate = float(self.redis.hget('machine_prefs', 'probe_fine_feed_per_minute'))
        else:
            self.probe_fine_feedrate = DEFAULT_PROBE_FINE_FEEDRATE
            self.error_handler.write("No probe fine feedrate stored in redis.", ALARM_LEVEL_DEBUG)
        self.error_handler.write("Setting probe fine feedrate to: %f" % self.probe_fine_feedrate, ALARM_LEVEL_DEBUG)

        # probe rough feedrate
        if self.redis.hexists('machine_prefs', 'probe_rough_feed_per_minute'):
            self.probe_rough_feedrate = float(self.redis.hget('machine_prefs', 'probe_rough_feed_per_minute'))
        else:
            self.probe_rough_feedrate = DEFAULT_PROBE_ROUGH_FEEDRATE
            self.error_handler.write("No probe rough feedrate stored in redis.", ALARM_LEVEL_DEBUG)
        self.error_handler.write("Setting probe rough feedrate to: %f" % self.probe_rough_feedrate, ALARM_LEVEL_DEBUG)

        # probe rapid feedrate
        if self.redis.hexists('machine_prefs', 'probe_rapid_feed_per_minute'):
            self.probe_rapid_feedrate = float(self.redis.hget('machine_prefs', 'probe_rapid_feed_per_minute'))
        else:
            self.probe_rapid_feedrate = DEFAULT_PROBE_RAPID_FEEDRATE
            self.error_handler.write("No probe rapid feedrate stored in redis.", ALARM_LEVEL_DEBUG)
        self.error_handler.write("Setting probe rapid feedrate to: %f" % self.probe_rapid_feedrate, ALARM_LEVEL_DEBUG)

        # probe ring gauge diameter
        if self.redis.hexists('machine_prefs', 'probe_ring_gauge_diameter'):
            self.probe_ring_gauge_diameter = float(self.redis.hget('machine_prefs', 'probe_ring_gauge_diameter'))
        else:
            self.probe_ring_gauge_diameter = DEFAULT_PROBE_RING_GAUGE_DIAMETER
            self.error_handler.write("No probe ring gauge diameter stored in redis.", ALARM_LEVEL_DEBUG)
        self.error_handler.write("Setting probe ring gauge diameter to: %f" % self.probe_ring_gauge_diameter, ALARM_LEVEL_DEBUG)

    def set_button_permitted_states(self):
        self.UIobj.button_list['move_and_set_probe_tip_diameter'].permitted_states = STATE_IDLE_AND_REFERENCED
        self.UIobj.button_list['probe_change_corner'].permitted_states = STATE_ANY
        self.UIobj.button_list['probe_change_inner_corner'].permitted_states = STATE_ANY

    def set_indicator_led(self, led_name, state):
        if state:
            self.set_image(led_name,'LED-Green.png')
        else:
            self.set_image(led_name,'LED-Black.png')

    def set_probe_input_leds(self, state):
        for nnn in ['1', '2', '3', '4']:
            self.set_indicator_led('acc_input_led' + nnn, state)

    def update_dros(self):
        aout = self.status.aout

        # probe type is set by 'find_whatever' functions, 1 = find_x_plus, 2 = X-, 3 = Y+, 4 = Y-, 5 = ?
        self.probe_x_plus_label.set_markup('<span foreground="white">%s</span>'   % self.dro_long_format % aout[PROBE_X_PLUS_AOUT])
        self.probe_x_minus_label.set_markup('<span foreground="white">%s</span>'  % self.dro_long_format % aout[PROBE_X_MINUS_AOUT])
        self.probe_y_plus_label.set_markup('<span foreground="white">%s</span>'   % self.dro_long_format % aout[PROBE_Y_PLUS_AOUT])
        self.probe_y_minus_label.set_markup('<span foreground="white">%s</span>'  % self.dro_long_format % aout[PROBE_Y_MINUS_AOUT])
        self.probe_z_minus_label.set_markup('<span foreground="white">%s</span>'  % self.dro_long_format % aout[PROBE_Z_MINUS_AOUT])
        self.probe_y_plus_a_label.set_markup('<span foreground="white">%s</span>' % self.dro_long_format % aout[PROBE_Y_PLUS_A_AOUT])
        self.probe_y_plus_b_label.set_markup('<span foreground="white">%s</span>' % self.dro_long_format % aout[PROBE_Y_PLUS_B_AOUT])
        self.probe_y_plus_c_label.set_markup('<span foreground="white">%s</span>' % self.dro_long_format % aout[PROBE_Y_PLUS_C_AOUT])
        if not self.dro_list['ets_height_dro'].masked:
            self.dro_list['ets_height_dro'].set_text(self.dro_long_format % (self.get_linear_scale() * self.ets_height))
        if not self.dro_list['probe_ring_gauge_dia_dro'].masked:
            self.dro_list['probe_ring_gauge_dia_dro'].set_text( "%s" % (self.dro_long_format % (self.probe_ring_gauge_diameter * self.get_linear_scale())))
        if not self.dro_list['probe_rapid_feedrate_dro'].masked:
            self.dro_list['probe_rapid_feedrate_dro'].set_text( "%s" % (self.dro_medium_format % (self.probe_rapid_feedrate * self.get_linear_scale())))
        if not self.dro_list['probe_rough_feedrate_dro'].masked:
            self.dro_list['probe_rough_feedrate_dro'].set_text( "%s" % (self.dro_medium_format % (self.probe_rough_feedrate * self.get_linear_scale())))
        if not self.dro_list['probe_fine_feedrate_dro'].masked:
            self.dro_list['probe_fine_feedrate_dro'].set_text( "%s" % (self.dro_medium_format % (self.probe_fine_feedrate * self.get_linear_scale())))
        if not self.dro_list['probe_tip_effective_dia_dro'].masked:
            self.dro_list['probe_tip_effective_dia_dro'].set_text( "%s" % (self.dro_long_format % (self.probe_tip_effective_diameter * self.get_linear_scale())))

    def update_ring_gauge_diameter(self):
        # look for rising edge on status.aout[PROBE_POCKET_DIAMETER_AOUT]
        # it means that the diameter of the ring gauge has been set by the g code subroutine
        self.measured_probe_ring_gauge_diameter = self.status.aout[PROBE_POCKET_DIAMETER_AOUT]/self.get_linear_scale()
        if self.prev_measured_probe_ring_gauge_diameter < 0.0 and self.measured_probe_ring_gauge_diameter > 0.0:
            self.error_handler.write("Probe ring gauge diameter measured: %s" % (self.measured_probe_ring_gauge_diameter), ALARM_LEVEL_DEBUG)
            self.error_handler.write("Probe ring gauge diameter actual:   %s" % (self.probe_ring_gauge_diameter), ALARM_LEVEL_DEBUG)
            self.error_handler.write("Rising edge on PROBE_POCKET_DIAMETER_AOUT", ALARM_LEVEL_DEBUG)
            # difference between actual ring gauge diameter and this probed diameter is the effective probe tip diameter
            # units are in inches
            tip_error = self.probe_ring_gauge_diameter - self.measured_probe_ring_gauge_diameter
            if tip_error < 0.0:
                # cannot be negative
                self.error_handler.write("Measured probe ring gauge diameter cannot be greater than the actual gauge", ALARM_LEVEL_DEBUG)
            if tip_error != 0.0:
                prev_tip_diameter = self.probe_tip_effective_diameter
                new_probe_tip_effective_diameter = tip_error
                self.dro_list['probe_tip_effective_dia_dro'].set_text( "%s" % (self.dro_long_format % (new_probe_tip_effective_diameter * self.get_linear_scale())))
                self.error_handler.write("Probe tip effective diameter changed from %s to: %s" % 
                    (self.dro_long_format % (prev_tip_diameter * self.get_linear_scale()), 
                        self.dro_long_format % (new_probe_tip_effective_diameter * self.get_linear_scale())), 
                        ALARM_LEVEL_DEBUG)

                # store this value in the tool table in machine setup units (inches)
                self.UIobj.issue_tool_offset_command('R', MILL_PROBE_TOOL_NUM, float(new_probe_tip_effective_diameter * self.get_linear_scale())/2.0)
        self.prev_measured_probe_ring_gauge_diameter = self.status.aout[PROBE_POCKET_DIAMETER_AOUT]

    def update_probe_tip_diameter(self):
        # if probe diameter has changed in tool table then update its DRO
        if not self.dro_list['probe_tip_effective_dia_dro'].masked:
            probe_tip_diameter_now = self.probe_tip_effective_diameter
            if probe_tip_diameter_now != self.prev_probe_tip_effective_diameter:
                self.prev_probe_tip_effective_diameter = probe_tip_diameter_now
                self.dro_list['probe_tip_effective_dia_dro'].set_text( "%s" % (self.dro_long_format % (probe_tip_diameter_now * self.get_linear_scale())))

    def periodic_500ms(self):
        # update probe position DROs
        self.update_dros()
        self.update_probe_tip_diameter()

    #-----------------------------------------------------------------------
    # callback handlers that call the main UI handlers
    #-----------------------------------------------------------------------

    def on_button_press_event(self, widget, event, data=None):
        self.UIobj.on_button_press_event(widget, event, data)

    def on_mouse_enter(self, widget, event, data=None):
        self.UIobj.on_mouse_enter(widget, event, data)

    def on_mouse_leave(self, widget, event, data=None):
        self.UIobj.on_mouse_leave(widget, event, data)

    def on_dro_gets_focus(self, widget, event):
        self.UIobj.on_dro_gets_focus(widget, event)

    def on_dro_loses_focus(self, widget, data=None):
        self.UIobj.on_dro_loses_focus(widget, data)

    def on_dro_key_press_event(self, widget, event, data=None):
        self.UIobj.on_dro_key_press_event(widget, event, data)

    # -------------------------------------------------------------------------------------------------
    # wrappers around UI objects
    # -------------------------------------------------------------------------------------------------

    def is_button_permitted(self, widget):
        return self.UIobj.is_button_permitted(widget)

    def validate_param(self, widget):
        (valid, value, error_msg) = self.UIobj.conversational.validate_param(widget)
        return (valid, value, error_msg)

    def get_linear_scale(self):
        return self.UIobj.get_linear_scale()

    def set_image(self, image_name, file_name):
        # if the image_name is not in the image_list then add an entry for it
        # with the widget from our own local builder
        try:
            self.UIobj.image_list[image_name].set_from_pixbuf(self.UIobj.pixbuf_dict[file_name])
        except KeyError:
            self.UIobj.image_list[image_name] = self.builder.get_object(image_name)
            if not self.UIobj.image_list[image_name]:
                self.UIobj.image_list[image_name] = gtk.Image()

        self.UIobj.set_image(image_name, file_name)
        return

    @property
    def current_z_position(self):
        return self.status.position[2]

    @property
    def tool_in_spindle(self):
        return self.status.tool_in_spindle

    @property
    def dro_long_format(self):
        return self.UIobj.dro_long_format

    @property
    def dro_medium_format(self):
        return self.UIobj.dro_medium_format

    @property
    def probe_tip_effective_diameter(self):
        probe_tip_effective_diameter = self.UIobj.get_tool_diameter(MILL_PROBE_TOOL_NUM)
        return probe_tip_effective_diameter

    # -------------------------------------------------------------------------------------------------
    # setup callbacks
    # -------------------------------------------------------------------------------------------------

    def on_probe_set_gauge_ref_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        if self.tool_in_spindle < 1:
            self.probe_setup_reference_surface = self.current_z_position
            self.error_handler.write("spindle nose reference height set to: %s" % self.dro_long_format % self.probe_setup_reference_surface, ALARM_LEVEL_DEBUG)

        else:
            self.error_handler.write("Tool 0 (empty spindle) must be active before setting the reference surface height.  Remove tool %d from spindle and change active tool to tool 0 before continuing" % self.tool_in_spindle, ALARM_LEVEL_MEDIUM)

    def on_ets_height_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        # store this value in machine setup units (inches) at all times.
        self.ets_height = value/self.get_linear_scale()
        self.redis.hset('machine_prefs', 'setter_height', self.ets_height)
        widget.masked = False
        self.UIobj.window.set_focus(None)

    def on_move_and_set_probe_tip_diameter_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        if self.tool_in_spindle != MILL_PROBE_TOOL_NUM:
            self.error_handler.write("Tool %d (probe tool) must be active before setting the reference surface height.  Change active tool to tool %d before continuing" % (MILL_PROBE_TOOL_NUM, MILL_PROBE_TOOL_NUM), ALARM_LEVEL_MEDIUM)
            return
        self.probing.move_and_set_tip_probe_diameter()

    def on_probe_set_probe_length_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        if self.tool_in_spindle != MILL_PROBE_TOOL_NUM:
            self.error_handler.write("Tool %d (probe tool) must be active before setting the reference surface height.  Change active tool to tool %d before continuing" % (MILL_PROBE_TOOL_NUM, MILL_PROBE_TOOL_NUM), ALARM_LEVEL_MEDIUM)
            return
        try:
            float(self.probe_setup_reference_surface)
            ref_surface = self.probe_setup_reference_surface
        except:
            ref_surface = self.current_z_position
            self.error_handler.write('Reference surface height not set - using work offset Z zero for reference surface: %s' % (self.dro_long_format % (ref_surface)), ALARM_LEVEL_MEDIUM)
            return
        self.probing.move_and_set_probe_length(ref_surface)

    def validate_probe_ring_gauge_dia(self, widget):
        (is_valid_number, diameter) = cparse.is_number_or_expression(widget)
        max_diameter = float(MAX_PROBE_RING_GAUGE_DIAMETER * self.get_linear_scale())
        if (is_valid_number and (diameter >= 0.0) and (diameter <= max_diameter)):
            cparse.clr_alarm(widget)
            return True, diameter, ''
        else:
            msg = 'Invalid probe ring gauge diameter. Diameter must be between 0.0 and %s' % self.dro_long_format % max_diameter
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def on_probe_ring_gauge_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_probe_ring_gauge_dia(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        # track in machine units
        self.probe_ring_gauge_diameter = value / self.get_linear_scale()
        self.error_handler.write("Probe ring gauge diameter changed to: %s" % self.dro_long_format % (value), ALARM_LEVEL_DEBUG)
        # store this value in machine setup units (inches) at all times.
        widget.set_text(self.dro_long_format % (self.get_linear_scale() * self.probe_ring_gauge_diameter))
        self.redis.hset('machine_prefs', 'probe_ring_gauge_diameter', self.probe_ring_gauge_diameter/self.get_linear_scale())
        widget.masked = False
        self.UIobj.window.set_focus(None)

    def validate_probe_tip_dia(self, widget):
        (is_valid_number, diameter) = cparse.is_number_or_expression(widget)
        max_diameter = float(MAX_PROBE_TIP_DIAMETER * self.get_linear_scale())
        if (is_valid_number and (diameter >= 0.0) and (diameter <= max_diameter)):
            cparse.clr_alarm(widget)
            return True, diameter, ''
        else:
            msg = 'Invalid probe tip diameter. Diameter must be between 0.0 and %s' % self.dro_long_format % max_diameter
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def on_probe_tip_effective_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_probe_tip_dia(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        # track in machine units
        new_probe_tip_effective_diameter = value / self.get_linear_scale()
        self.error_handler.write("Probe tip effective diameter changed to: %s" % self.dro_long_format % (value), ALARM_LEVEL_DEBUG)
        # store in MILL_PROBE_TOOL_NUM diameter column
        widget.set_text(self.dro_long_format % (self.get_linear_scale() * new_probe_tip_effective_diameter))
        self.UIobj.issue_tool_offset_command('R', MILL_PROBE_TOOL_NUM, float(new_probe_tip_effective_diameter * self.get_linear_scale())/2.0)
        widget.masked = False
        self.UIobj.window.set_focus(None)

    def validate_probe_rapid_feedrate(self, widget):
        (is_valid_number, feedrate) = cparse.is_number_or_expression(widget)
        if (is_valid_number and feedrate > 0.0):
            cparse.clr_alarm(widget)
            return True, feedrate, ''
        else:
            msg = 'Invalid probe rapid feedrate'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def on_probe_rapid_feedrate_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_probe_rapid_feedrate(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        probe_rapid_feedrate = abs(value)
        if probe_rapid_feedrate > self.max_probe_rapid_feedrate * self.get_linear_scale():
            probe_rapid_feedrate = self.max_probe_rapid_feedrate * self.get_linear_scale()
            self.error_handler.write("Limiting probe rapid feedrate to maximum allowed. %s" % self.dro_medium_format % (self.max_probe_rapid_feedrate), ALARM_LEVEL_LOW)

        self.error_handler.write("Probe rapid feed DRO changed to: %s" % self.dro_medium_format % (probe_rapid_feedrate), ALARM_LEVEL_DEBUG)
        self.probe_rapid_feedrate = probe_rapid_feedrate/self.get_linear_scale()
        widget.set_text(self.dro_medium_format % (self.get_linear_scale() * self.probe_rapid_feedrate))

        # store this value in machine setup units (inches) at all times.
        self.redis.hset('machine_prefs', 'probe_rapid_feed_per_minute', self.probe_rapid_feedrate)
        widget.masked = False
        self.UIobj.window.set_focus(None)

    def validate_probe_feedrate(self, widget):
        (is_valid_number, feedrate) = cparse.is_number_or_expression(widget)
        if (is_valid_number and feedrate > 0.0):
            cparse.clr_alarm(widget)
            return True, feedrate, ''
        else:
            msg = 'Invalid probe rough feedrate'
            cparse.raise_alarm(widget, msg)
            return False, 0, msg

    def on_probe_rough_feedrate_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_probe_feedrate(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        probe_rough_feedrate = abs(value)
        if probe_rough_feedrate > self.max_probe_rough_feedrate * self.get_linear_scale():
            probe_rough_feedrate = self.max_probe_rough_feedrate * self.get_linear_scale()
            self.error_handler.write("Limiting rough probe feedrate to maximum allowed. %.0f /min" % (probe_rough_feedrate), ALARM_LEVEL_LOW)

        self.error_handler.write("Probe rough feed DRO changed to: %s" % self.dro_medium_format % (probe_rough_feedrate), ALARM_LEVEL_DEBUG)
        self.probe_rough_feedrate = probe_rough_feedrate/self.get_linear_scale()
        widget.set_text(self.dro_medium_format % (self.get_linear_scale() * self.probe_rough_feedrate))

        # store this value in machine setup units (inches) at all times.
        self.redis.hset('machine_prefs', 'probe_rough_feed_per_minute', self.probe_rough_feedrate)
        widget.masked = False
        self.UIobj.window.set_focus(None)

    def on_probe_fine_feedrate_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.validate_probe_feedrate(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        probe_fine_feedrate = abs(value)
        if probe_fine_feedrate > self.max_probe_fine_feedrate * self.get_linear_scale():
            probe_fine_feedrate = self.max_probe_fine_feedrate * self.get_linear_scale()
            self.error_handler.write("Limiting fine probe feedrate to maximum allowed. %.0f /min" % (probe_fine_feedrate), ALARM_LEVEL_LOW)

        self.error_handler.write("Probe fine feed DRO changed to: %s" % self.dro_medium_format % (probe_fine_feedrate), ALARM_LEVEL_DEBUG)
        self.probe_fine_feedrate = probe_fine_feedrate/self.get_linear_scale()
        widget.set_text(self.dro_medium_format % (self.get_linear_scale() * self.probe_fine_feedrate))

        # store this value in machine setup units (inches) at all times.
        self.redis.hset('machine_prefs', 'probe_fine_feed_per_minute', self.probe_fine_feedrate)
        widget.masked = False
        self.UIobj.window.set_focus(None)

    # -------------------------------------------------------------------------------------------------
    # x/y corner probing
    # -------------------------------------------------------------------------------------------------

    def on_probe_change_corner_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        # toggle state between nw, ne, se, and sw

        if self.probe_active_corner == 'nw':
            self.set_image('probe_vise_image', 'probe_corner_ne.svg')
            self.probe_active_corner = 'ne'
        elif self.probe_active_corner == 'ne':
            self.set_image('probe_vise_image', 'probe_corner_se.svg')
            self.probe_active_corner = 'se'
        elif self.probe_active_corner == 'se':
            self.set_image('probe_vise_image', 'probe_corner_sw.svg')
            self.probe_active_corner = 'sw'
        elif self.probe_active_corner == 'sw':
            self.set_image('probe_vise_image', 'probe_corner_nw.svg')
            self.probe_active_corner = 'nw'
        else:  # should be an error, but for now reset to defualt
            self.set_image('probe_vise_image', 'probe_corner_nw.svg')
            self.probe_active_corner = 'nw'

    def on_probe_find_corner_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_corner(True, self.probe_active_corner)

    def on_probe_change_inner_corner_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        # toggle button state between nw, ne, se, and sw

        if self.probe_active_inner_corner == 'nw':
            self.set_image('probe_inner_corner_image', 'probe_corner_in_ne.svg')
            self.probe_active_inner_corner = 'ne'
        elif self.probe_active_inner_corner == 'ne':
            self.set_image('probe_inner_corner_image', 'probe_corner_in_se.svg')
            self.probe_active_inner_corner = 'se'
        elif self.probe_active_inner_corner == 'se':
            self.set_image('probe_inner_corner_image', 'probe_corner_in_sw.svg')
            self.probe_active_inner_corner = 'sw'
        elif self.probe_active_inner_corner == 'sw':
            self.set_image('probe_inner_corner_image', 'probe_corner_in_nw.svg')
            self.probe_active_inner_corner = 'nw'
        else:  # should be an error, but for now reset to defualt
            self.set_image('probe_inner_corner_image', 'probe_corner_in_nw.svg')
            self.probe_active_inner_corner = 'nw'

    def on_probe_find_inner_corner_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_corner(False, self.probe_active_inner_corner)

    # -------------------------------------------------------------------------------------------------
    # simple one axis probing
    # -------------------------------------------------------------------------------------------------

    def on_probe_x_plus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_x(0, 1)

    def on_probe_origin_x_plus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_x(1, 1)

    def on_probe_x_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_x(0, -1)

    def on_probe_origin_x_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_x(1, -1)

    def on_probe_y_plus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y(0, 1)

    def on_probe_origin_y_plus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y(1, 1)

    def on_probe_y_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y(0, -1)

    def on_probe_origin_y_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y(1, -1)

    def on_probe_z_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_z(0, -1)

    def on_probe_origin_z_minus_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_z(1, -1)

    def on_probe_y_plus_a_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y_plus_abc(PROBE_Y_PLUS_A_AOUT)

    def on_probe_y_plus_b_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y_plus_abc(PROBE_Y_PLUS_B_AOUT)

    def on_probe_y_plus_c_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_y_plus_abc(PROBE_Y_PLUS_C_AOUT)

    # -------------------------------------------------------------------------------------------------
    # Rect/Circ Boss probing
    # -------------------------------------------------------------------------------------------------

    def on_probe_find_rect_boss_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_rect_boss_center()

    def on_probe_find_circ_boss_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_circ_boss_center()

    # -------------------------------------------------------------------------------------------------
    # Rect/Circ Pocket probing
    # -------------------------------------------------------------------------------------------------

    def on_probe_find_pocket_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_pocket_xy_center(2)

    def on_probe_find_pocket_x_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_pocket_xy_center(0)

    def on_probe_find_pocket_y_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_pocket_xy_center(1)

    # -------------------------------------------------------------------------------------------------
    # A axis Circ Boss probing
    # -------------------------------------------------------------------------------------------------

    def on_probe_a_axis_center_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.probing.find_a_axis_center()

    # -------------------------------------------------------------------------------------------------
    # Z probing
    # -------------------------------------------------------------------------------------------------

    # -- called from Offsets/Tool tab and ATC touch off tray
    def probe_move_and_set_tool_length(self):
        self.probing.move_and_set_tool_length(self.ets_height)

    # -- called from Offsets/Work tab
    def probe_find_work_z_with_ets(self):
        self.probing.find_work_z_with_ets(self.ets_height)
