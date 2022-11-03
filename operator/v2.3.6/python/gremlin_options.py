# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import glib
import pango
import os
from constants import *
import errors
import btn

class gremlin_options(object):
    def __init__(self, machineobj, gladefilename):

        self.machineobj = machineobj
        self.gremlin = machineobj.gremlin

        # no easy access to the mill/lathe error handler instance.  Just create a basic one for debug logging.
        self.error_handler = errors.error_handler_base()

        # Always use gtk.WINDOW_TOPLEVEL. The gtk.DIALOG_MODAL flag is only for use with gtk.Dialog objects, not gtk.Window objects!
        # If used by accident here, it causes the blinking text editing insert caret/cursor to be invisible.
        # That's a fun bug to track down...
        # And don't use WINDOW_POPUP, that's for GTK menus and tool tips, not dialogs.

        self.builder = gtk.Builder()

        gladefile = os.path.join(GLADE_DIR, gladefilename)

        if self.builder.add_objects_from_file(gladefile, ['fixed', 'zoom_adjustment']) == 0:
            raise RuntimeError("GtkBuilder failed")

        self.show_current_tool_checkbutton = self.builder.get_object('show_current_tool_checkbutton')

        missingSignals = self.builder.connect_signals(self)
        if missingSignals is not None:
            raise RuntimeError("Cannot connect signals: ", missingSignals)

        self.fixed = self.builder.get_object("fixed")

        # background cell color based on if tool is used by current program or not
        self.tool_liststore = gtk.ListStore(bool, int, str)

        # Create a TreeView and let it know about the model we created above
        self.tool_treeview = gtk.TreeView(self.tool_liststore)

        # create columns
        self.tool_cb_column            = gtk.TreeViewColumn('Show')
        self.tool_num_column           = gtk.TreeViewColumn('Tool')
        self.tool_description_column   = gtk.TreeViewColumn('Description')

        # add columns to treeview
        self.tool_treeview.append_column(self.tool_cb_column)
        self.tool_treeview.append_column(self.tool_num_column)
        self.tool_treeview.append_column(self.tool_description_column)

        tool_font = pango.FontDescription('Roboto Condensed 10')

        tool_cb_renderer = gtk.CellRendererToggle()
        tool_cb_renderer.set_property('activatable', True)
        tool_cb_renderer.connect("toggled", self.on_tool_cb_toggled)
        self.tool_cb_column.pack_start(tool_cb_renderer, True)
        self.tool_cb_column.set_attributes(tool_cb_renderer, active=0)

        tool_col_renderer = gtk.CellRendererText()
        tool_col_renderer.set_property('editable', False)
        #tool_col_renderer.set_property('cell-background', '#D5E1B3')
        tool_col_renderer.set_property('font-desc', tool_font)
        self.tool_num_column.pack_start(tool_col_renderer, True)
        self.tool_num_column.set_attributes(tool_col_renderer, text=1)
        self.tool_num_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.tool_num_column.set_fixed_width(50)

        tool_description_renderer = gtk.CellRendererText()
        tool_description_renderer.set_property('editable', False)
        #tool_description_renderer.set_property('cell-background', '#D5E1B3')
        tool_description_renderer.set_property('font-desc', tool_font)
        self.tool_description_column.pack_start(tool_description_renderer, True)
        self.tool_description_column.set_attributes(tool_description_renderer, text=2)
        self.tool_description_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.tool_description_column.set_fixed_width(120)

        self.tool_treeview.set_can_focus(True)
        self.treeselection = self.tool_treeview.get_selection()
        self.treeselection.set_mode(gtk.SELECTION_MULTIPLE)

        # create a scrolled window to hold the treeview
        self.scrolled_window_tool_table = gtk.ScrolledWindow()
        self.scrolled_window_tool_table.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.scrolled_window_tool_table.add(self.tool_treeview)
        self.fixed.put(self.scrolled_window_tool_table, 10, 10)

        # this attempts to catch double clicks to toggle the size of the left side pane
        # just like the G-Code notetab does.  but its not perfect and I can't figure out
        # how to catch clicks anywhere on the background fixed/image, just doesn't seem to work.
        # I tried setting or adding to the event mask of the fixed widget also to no avail.
        self.fixed.connect("button-press-event", self.on_button_press_event)
        self.tool_treeview.connect("button-press-event", self.on_button_press_event)

        self.builder.get_object("zoom_scale").connect("button-release-event", self.on_zoom_scale_button_release)

        self.zoom_adjustment = self.builder.get_object("zoom_adjustment")
        self.zoom_adjustment.set_value(50)
        self.prev_zoom_value = 50
        self.ignore_adjustment = False
        self.show_only_current_tool = False
        self.view_state = 'Normal'
        self.view_state_shift_cx = 0


    def on_button_press_event(self, widget, event):
        if event.type == gtk.gdk._2BUTTON_PRESS:
            # double click in the fixed area toggles the current width of the left pane
            self.machineobj.toggle_gcodewindow_size()


    def on_show_current_tool_checkbutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.show_only_current_tool = True
            self.tool_treeview.set_sensitive(False)
        else:
            self.show_only_current_tool = False
            self.tool_treeview.set_sensitive(True)

        self._update_visible_tools()


    def on_tool_cb_toggled(self, cellrenderer, path, data=None):
        # the behavior is a little tricky here to make it feel natural to the user.
        # if the row they clicked the checkbox on is not part of the current selection, then
        # only change the checkbox they clicked on.
        #
        # but if they have a selection and the checkbox they clicked is in the selection, then
        # toggle the state of the checkbox, but then use that final bool result to force the rest of
        # the selection to that state.  this makes it easy to multi-select a bunch of rows with
        # inconsistent t/f states and conform them all to either t or f.

        path = (int(path),)  # conform the path arg to be the same as those returned from selection
        model, paths = self.treeselection.get_selected_rows()
        if path not in paths:
            # checkbox they toggled is NOT in the selection so just act only on it
            pos = self.tool_liststore.get_iter(path)
            # reverse the bool in column 0 representing tool visibility
            self.tool_liststore.set_value(pos, 0, not self.tool_liststore.get_value(pos, 0))

        else:
            pos = self.tool_liststore.get_iter(path)
            desired_value = not self.tool_liststore.get_value(pos, 0)
            for path in paths:
                pos = self.tool_liststore.get_iter(path)
                # reverse the bool in column 0 representing tool visibility
                self.tool_liststore.set_value(pos, 0, desired_value)

        self._update_visible_tools()


    def _update_visible_tools(self):
        # set visible tools on gremlin based on treeview liststore status
        visible_tools = []
        if self.show_only_current_tool:
            visible_tools.append(self.machineobj.status.tool_in_spindle)
        else:
            ix = 0
            pos = self.tool_liststore.get_iter_first()
            while pos != None:
                if self.tool_liststore.get_value(pos, 0):
                    visible_tools.append(self.unique_tool_list[ix])
                pos = self.tool_liststore.iter_next(pos)
                ix += 1
            if ix == 0:
                # there are no tools at all in the list, probably no gcode file loaded
                visible_tools = None

        self.gremlin.set_visible_tools(visible_tools)
        self.gremlin._redraw()


    def periodic_500ms(self):
        # we only need to do something on the 500ms periodic if we are only showing the current tool
        if self.show_only_current_tool:
            visible_tools = self.gremlin.get_visible_tools()
            if visible_tools and self.machineobj.status.tool_in_spindle not in visible_tools:
                self._update_visible_tools()


    def set_view_state(self, state, SHIFT_CX):
        assert state in ('Expanded', 'Normal')
        self.view_state = state
        self.view_state_shift_cx = SHIFT_CX

        if state == 'Expanded':
            self.builder.get_object("gremlin_options_background_image").set_size_request(314 + SHIFT_CX, 382)
            self.scrolled_window_tool_table.set_size_request(294 + SHIFT_CX, 176)
            self.builder.get_object("zoom_scale").set_size_request(292 + SHIFT_CX, 40)
            self.tool_description_column.set_fixed_width(120 + SHIFT_CX)
        else:
            self.builder.get_object("gremlin_options_background_image").set_size_request(314, 382)
            self.scrolled_window_tool_table.set_size_request(294, 176)
            self.builder.get_object("zoom_scale").set_size_request(292, 40)
            self.tool_description_column.set_fixed_width(120)


    def on_zoom_scale_button_release(self, widget, event, data=None):
        glib.idle_add(self._idle_zoom_snapback, widget)


    def _idle_zoom_snapback(self, widget):
        # rubber snap the adjuster back to center to support infinite zoom in either direction
        self.ignore_adjustment = True
        self.prev_zoom_value = 50
        self.zoom_adjustment.set_value(50)
        self.builder.get_object("zoom_scale").set_value(50)
        self.builder.get_object("zoom_scale").queue_draw()
        self.ignore_adjustment = False
        return False


    def show_all_tools(self):
        # turn off the filter of showing only the current tool and any subset list of tools
        # this is typically done when you load a new gcode file so that by default, you're seeing
        # everything.
        self.gremlin.set_visible_tools(None)
        self.refresh()
        self.show_current_tool_checkbutton.set_active(False)


    def refresh(self):
        # load up the table with the tool used by the current program

        # the tool list is in the order the program uses them and duplicates are possible.
        # build a new list without duplicates and sort it so it easier for the user to go through the tool table.
        # we do it reverse so that the order of the warnings on the status page becomes low number tool to high number
        # as you look down the page.
        self.unique_tool_list = []
        for tool in self.machineobj.gcode_program_tools_used:
            if tool not in self.unique_tool_list:
                self.unique_tool_list.append(tool)
        self.unique_tool_list.sort()

        # the tool_liststore may have some state already about which tools should be visible or not
        self.tool_liststore.clear()
        visible_tools = self.gremlin.get_visible_tools()
        for tool in self.unique_tool_list:
            visibility = (visible_tools is None or tool in visible_tools)
            self.tool_liststore.append((visibility, tool, self.machineobj.get_tool_description(tool)))

        self.update_unit_state()

        self.fixed.show_all()

        # this won't work when placed in the constructor - the parent widgets/containers need to be shown at least once
        # before the layout sizing logic is done.
        if self.view_state == 'Expanded':
            self.scrolled_window_tool_table.set_size_request(294 + self.view_state_shift_cx, 176)
        else:
            self.scrolled_window_tool_table.set_size_request(294, 176)


    def update_unit_state(self):
        markup_template = '<span weight="bold" font_desc="Roboto Condensed 11" foreground="white">{}</span>'
        if self.machineobj.g21:
            self.builder.get_object("gridsize_small_text").set_markup(markup_template.format('5 mm'))
            self.builder.get_object("gridsize_med_text").set_markup(markup_template.format('10 mm'))
            self.builder.get_object("gridsize_large_text").set_markup(markup_template.format('25 mm'))
        else:
            self.builder.get_object("gridsize_small_text").set_markup(markup_template.format('0.1 inch'))
            self.builder.get_object("gridsize_med_text").set_markup(markup_template.format('0.5 inch'))
            self.builder.get_object("gridsize_large_text").set_markup(markup_template.format('1.0 inch'))


    def update_grid_size(self, size_name):
        assert size_name in ('none', 'small', 'med', 'large')

        self.builder.get_object("grid_small_rb").set_active(False)
        self.builder.get_object("grid_med_rb").set_active(False)
        self.builder.get_object("grid_large_rb").set_active(False)

        if size_name == 'small':
            self.builder.get_object("grid_small_rb").set_active(True)
        elif size_name == 'med':
            self.builder.get_object("grid_med_rb").set_active(True)
        elif size_name == 'large':
            self.builder.get_object("grid_large_rb").set_active(True)


    def update_ui_view(self):
        if self.gremlin.ui_view == 'y':
            self.builder.get_object("view_front_rb").set_active(True)
        elif self.gremlin.ui_view == 'x':
            self.builder.get_object("view_side_rb").set_active(True)
        elif self.gremlin.ui_view == 'z':
            self.builder.get_object("view_top_rb").set_active(True)
        elif self.gremlin.ui_view == 'p':
            self.builder.get_object("view_iso_rb").set_active(True)


    def update_a_axis(self, is_enabled):
        self.builder.get_object("display_a_axis_checkbutton").set_active(is_enabled)


    def on_zoom_adjustment_changed(self, adjustment):
        if not self.ignore_adjustment:
            if adjustment.value > self.prev_zoom_value:
                self.gremlin.zoom_in(1.03)   # default is 1.1 for 10% but that's way too fast for touch screen use
            else:
                self.gremlin.zoom_out(1.03)
            self.prev_zoom_value = adjustment.value


    def on_view_iso_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_iso_view()

    def on_view_top_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_top_view()

    def on_view_front_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_front_view()

    def on_view_side_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_side_view()

    def on_gridsize_small_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_grid_size_small(None)

    def on_gridsize_med_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_grid_size_med(None)

    def on_gridsize_large_radiobutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.set_grid_size_large(None)

    def on_display_a_axis_checkbutton_toggled(self, widget, data=None):
        if widget.get_active():
            self.gremlin.enable_fourth_axis_toolpath_display(widget)
        else:
            self.gremlin.disable_fourth_axis_toolpath_display(widget)
