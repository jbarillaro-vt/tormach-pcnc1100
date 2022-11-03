# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import pango
import os
import numpad
from constants import *
import errors
import btn
import fsutil
import ui_misc

'''
Popup modal dialog classes that should handle most of our needs with dynamic layout rules for
properly sizing all text, button, entry, and checkbox widgets and the touchscreen keyboards added
to the bottom of the dialog or not.

Independent from other code so it can be easily used in both primary PP UI as well as pathpilotmanager.py
startup code.
'''

#
# fixed container that holds a file chooser widget and related buttons and behavior
# this object can be added to the popup object easily and the dynamic layout rules account for it
#

class file_chooser_fixed(gtk.Fixed):

    def __init__(self, home_button=True, usb_button=False, oldversion_button=False, newdir_button=False, file_filter = '*', min_width = 0):

        gtk.Fixed.__init__(self)

        # no easy access to the mill/lathe error handler instance.  Just create a basic one for debug logging.
        self.error_handler = errors.error_handler_base()

        self.filter = gtk.FileFilter()
        self.filter.add_pattern(file_filter)

        self.home_button = btn.ImageButton('home-button.png', 'file-home-button')
        self.usb_button = btn.ImageButton('usb-home-button.png', 'file-usb-button')
        self.back_button = btn.ImageButton('back-button.png', 'file-back-button')
        self.oldversion_button = btn.ImageButton("prevversions-button.png", 'oldversions')
        self.new_dir_button = btn.ImageButton('New-Folder-Tall.png', 'file-new-folder-button')

        self.back_button.set_size_request(35, 37)
        self.home_button.set_size_request(99, 37)
        self.usb_button.set_size_request(99, 37)
        self.oldversion_button.set_size_request(92, 37)
        self.new_dir_button.set_size_request(99, 37)

        self.buttonlist = [self.back_button,
                           self.home_button,
                           self.usb_button,
                           self.oldversion_button,
                           self.new_dir_button]

        self.back_button.connect("button-release-event", self.on_up_button_release_event)
        self.home_button.connect("button-release-event", self.on_home_button_release_event)
        self.usb_button.connect("button-release-event", self.on_usb_button_release_event)
        self.oldversion_button.connect("button-release-event", self.on_oldversion_button_release_event)
        self.new_dir_button.connect("button-release-event", self.on_new_dir_button_release_event)

        # add widgets to fixed container all in a row.
        self.put(self.back_button, 0, 0)
        next_x = 35 + 10

        if home_button:
            self.put(self.home_button, next_x, 0)
            next_x += 99 + 10
        if usb_button:
            self.put(self.usb_button, next_x, 0)
            next_x += 99 + 10
        if oldversion_button:
            self.put(self.oldversion_button, next_x, 0)
            next_x += 92 + 10
        if newdir_button:
            self.put(self.new_dir_button, next_x, 0)
            next_x += 99 + 10

        # retain the width given the mix of buttons to use for our size request to the parent widget
        self.min_width = max(next_x, min_width)
        self.min_width = max(self.min_width, 1024/4)

        self.file_chooser = gtk.FileChooserWidget()
        self.file_chooser.set_select_multiple(True)
        self.file_chooser.set_local_only(True)
        self.file_chooser.set_filter(self.filter)

        self.set_restricted_directory(GCODE_BASE_PATH)

        self.put(self.file_chooser, 0, 32)

        self.file_chooser.connect("current-folder-changed", self.on_current_folder_changed)
        # NB - use update-preview signal here because selection-changed signal is called 3 or four times on widget creation
        self.file_chooser.connect("update-preview", self.on_selection_changed)
        # kludge to fix issue #1106
        self.ignore_selection_changed = True

        self.touchscreen = False  # will be set by owner dialog when this component is added to it

        self.set_size_request(self.min_width, 350)  # good default height

        self.entry = None


    def set_size_request(self, x, y):
        gtk.Fixed.set_size_request(self, x, y)
        assert x >= self.min_width, "Min width of file chooser is {:d} - caller tried to use {:d}".format(self.min_width, x)
        self.file_chooser.set_size_request(x, y - 37)


    def on_current_folder_changed(self, widget):
        directory = self.file_chooser.get_current_folder()
        self.ignore_selection_changed = True
        self.error_handler.log('popup current folder changed has changed to: %s' % directory)
        if directory.startswith(self.restricted_directory):
            pass
        else:
            self.error_handler.log('caught attempt to change outside restricted directory: %s' % directory)
            self.file_chooser.set_current_folder(self.restricted_directory)


    def set_entry_widget_for_selected_file(self, entry):
        self.entry = entry


    def on_selection_changed(self, widget, data=None):
        # this gets called on widget creation too, not just on the user's click events
        # hence the kludge about ignore_selection_changed. See issue #1106
        filename = self.selected
        if self.ignore_selection_changed == True:
            # set to false for the next time 'round, which will be a legitimate click
            self.ignore_selection_changed = False
            # and return without setting the entry
            return

        if self.entry and os.path.isfile(filename):
            try:
                self.entry.set_text(os.path.split(filename)[1])
                # also store a "previous path" so that the user can cancel
                self.entry.prev_text = self.entry.get_text()
            except AttributeError:
                pass

    def connect(self, signal_name, callback_name):
        self.file_chooser.connect(signal_name, callback_name)

    def get_restricted_directory(self):
        return self.restricted_directory

    def set_restricted_directory(self, directory):
        self.error_handler.log('setting restricted directory to: %s' % directory)
        self.restricted_directory = directory
        self.set_current_directory(directory)

    def set_current_directory(self, directory):
        self.error_handler.log('set_current_directory(): %s' % directory)
        self.file_chooser.set_current_folder(directory)

    def get_current_directory(self):
        return self.file_chooser.get_current_folder()

    def on_home_button_release_event(self, widget, data=None):
        widget.unshift()
        self.set_restricted_directory(GCODE_BASE_PATH)
        self.set_current_directory(self.restricted_directory)

    def on_usb_button_release_event(self, widget, data=None):
        widget.unshift()
        self.set_restricted_directory(USB_MEDIA_MOUNT_POINT)
        self.set_current_directory(self.restricted_directory)

        # if moving to USB_MEDIA_MOUNT_POINT and only one directory is there assume it's
        # the USB stick and change into it (difference with the way mount points for removable
        # media area handled with Mint 17.3)
        fsutil.adjust_media_directory_if_necessary(self, self.restricted_directory)

    def on_up_button_release_event(self, widget, data=None):
        widget.unshift()
        if self.get_current_directory() == self.restricted_directory:
            return
        self.set_current_directory(os.path.dirname(self.get_current_directory()))

    def on_oldversion_button_release_event(self, widget, data=None):
        widget.unshift()

    def set_touchscreen(self, touchscreen):
        self.touchscreen = touchscreen

    def on_new_dir_button_release_event(self, widget, data=None):
        widget.unshift()

        parent_container = self.get_parent()
        parent_window = parent_container.get_parent()
        with new_filename_popup(parent_window, '', self.touchscreen) as dialog:
            if dialog.response == gtk.RESPONSE_CANCEL:
                # no action on cancel
                return
            new_dir_name = dialog.get_filename()
            if len(new_dir_name) > 0:
                path = os.path.join(self.file_chooser.get_current_folder(), new_dir_name)
                if os.path.isdir(path):
                    self.error_handler.write("Directory already exists: %s" % new_dir_name, ALARM_LEVEL_LOW)
                    return
                try:
                    os.mkdir(path)
                except OSError, msg:
                    self.error_handler.log("Directory creation error %s" % msg)

    @property
    def selected_path(self):
        """ Similar to the selected property, this returns a file path if a single file is selected."""
        path = self.selected
        if not os.path.isdir(path):
            return path
        return ''

    @property
    def selected(self):
        """ Returns the path of the current item (file or directory) selected
        if only one item is selected. Otherwise, it returns an empty string.
        """
        item_list = self.file_chooser.get_filenames()
        if self.has_single_selection():
            name = item_list[0]
            return name
        return ''

    def has_single_selection(self):
        """Test if only a single item is selected"""
        return True if len(self.file_chooser.get_filenames()) == 1 else False

    def has_selection(self):
        """Test if the iconview has any items selected"""
        return True if len(self.file_chooser.get_filenames()) else False



class popup():
    def __init__(self, parentwindow, popup_message, touchscreen_enabled, checkbox_enabled, entry_enabled):
        '''
        base class for all popup dialogs with text and a few widgets.
        design intent is for subclasses to set the list of buttons that should be arranged in a single row
        along the bottom of the dialog, set the text, and then perform a new layout prior to showing.
        this makes it trivial to add new variants of buttons or additional widgets without any
        risk of text clipping.
        '''

        while not isinstance(parentwindow,gtk.Window):
            # walk the widget hierarchy until a parent is found
            # or None. Since self.parentwindow is checked, a None value
            # is ok.
            if parentwindow is None: break
            parentwindow = parentwindow.get_parent()
        self.parentwindow = parentwindow
        self.touchscreen_enabled = touchscreen_enabled
        self.popup_message = popup_message
        self.checkbox_enabled = checkbox_enabled
        self.entry_enabled = entry_enabled

        # no easy access to the mill/lathe error handler instance.  Just create a basic one for debug logging.
        self.error_handler = errors.error_handler_base()

        # some constants we use to influence the dynamic layout rules
        self.VERT_GAP_BETWEEN_LABEL_AND_BUTTON_ROW = 30
        self.TEXT_PADDING_HORIZ = 10
        self.TEXT_PADDING_VERT= 8

        # Always use gtk.WINDOW_TOPLEVEL. The gtk.DIALOG_MODAL flag is only for use with gtk.Dialog objects, not gtk.Window objects!
        # If used by accident here, it causes the blinking text editing insert caret/cursor to be invisible.
        # That's a fun bug to track down...
        # And don't use WINDOW_POPUP, that's for GTK menus and tool tips, not dialogs.
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        # setting the hint type to dialog keeps this window in front of the main UI screen (Z order)
        self.window.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.window.set_transient_for(parentwindow)
        self.window.set_destroy_with_parent(True)
        self.window.set_modal(True)

        self.fixed = gtk.Fixed()

        self.background = gtk.Image()
        self.background.set_from_file(os.path.join(GLADE_DIR, 'dark_background.jpg'))
        self.fixed.put(self.background, 0, 0)

        self.label = gtk.Label()
        self.label.set_justify(gtk.JUSTIFY_LEFT)
        self.label.set_line_wrap(True)

        self.entry_label = gtk.Label()
        self.entry_label_message = ""

        self.entry = gtk.Entry()
        self.entry.connect("activate", self.on_entry_activate)
        self.entry.prev_text = ''

        # common buttons.  The subclasse will only use some of these and informs us which ones
        # through the _init_and_arrange_buttons() method after construction.  we hook up signals
        # to all of them just to be easy code maintenance even though some will not be on the dialog.
        self.ok_button = btn.ImageButton('OK-Highlighted.png', 'popup-ok-button')
        self.cancel_button = btn.ImageButton('cancel-button.png', 'popup-cancel-button')
        self.save_button = btn.ImageButton('save-button.png', 'popup-save-button')
        self.overwrite_button = btn.ImageButton('overwrite-button.png', 'popup-overwrite-button')
        self.yes_button = btn.ImageButton('Yes.png', 'popup-yes-button')
        self.no_button = btn.ImageButton('No.png', 'popup-no-button')
        self.update_button = btn.ImageButton('Update.png','update')
        self.append_button = btn.ImageButton('append-to-file.png', 'append')

        # initially at least the button list to use is all of them. subclasses will change this
        # prior to calling _perform_layout()
        self.buttonlist = [ self.ok_button,
                            self.cancel_button,
                            self.save_button,
                            self.overwrite_button,
                            self.yes_button,
                            self.no_button,
                            self.update_button,
                            self.append_button ]

        for bb in self.buttonlist:
            bb.disable()
            bb.set_size_request(100, 37)

        self.ok_button.connect("button-release-event", self.on_ok_button_release_event)
        self.cancel_button.connect("button-release-event", self.on_cancel_button_release_event)
        self.save_button.connect("button-release-event", self.on_save_button_release_event)
        self.overwrite_button.connect("button-release-event", self.on_overwrite_button_release_event)
        self.yes_button.connect("button-release-event", self.on_yes_button_release_event)
        self.no_button.connect("button-release-event", self.on_no_button_release_event)
        self.update_button.connect("button-release-event", self.on_update_button_release_event)
        self.append_button.connect("button-release-event", self.on_append_button_release_event)

        self.checkbox = gtk.CheckButton("")
        cbmarkup = '<span weight="bold" font_desc="Roboto Condensed 11" foreground="white">{}</span>'
        self.checkbox.get_child().set_markup(cbmarkup.format("Show warning"))
        self.checkbox.set_active(True)
        self.checkbox.modify_bg(gtk.STATE_PRELIGHT,gtk.gdk.Color('#444444'))

        # window
        self.window.add(self.fixed)
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_position(gtk.WIN_POS_CENTER_ON_PARENT)

        if self.touchscreen_enabled:
            self.pad = numpad.numpad(self.entry, True)
            self.pad.set_popup_window(self.window)

        self._optional_fixed_child = None

        # Default to cancellation
        self.response = gtk.RESPONSE_CANCEL

        # Tie in key presses on popup
        # switched to press event instead of release event
        # when popup called via MDI line ADMIN command
        # the release of Enter from the MDI line gets caught
        # here and the dialog instantly goes away as if
        # Enter had been pressed
        self.entry.connect("key-press-event", self.on_entry_key_press)

        self.path = ''
        self.filename = ''

        self._layout_called = False


    def _set_entry_label_message(self, msg):
        # msg should be plain text - do not wrap it with all sorts of markup, we use standard markup templates
        # already for consistency in the popups.
        self.entry_label_message = msg


    def _add_optional_fixed_child(self, fixed):
        self._optional_fixed_child = fixed
        if hasattr(self._optional_fixed_child, "set_touchscreen"):
            self._optional_fixed_child.set_touchscreen(self.touchscreen_enabled)


    def _set_entry(self, entrytext):
        self.entry.set_text(entrytext)
        self.entry.prev_text = ''


    def _set_entry_to_path(self, path):
        assert self.entry_enabled, "Can't set entry path if we're not using the entry widget"

        self.path = path
        if len(self.path) > 0:
            self.entry.set_text(os.path.split(self.path)[1])
            #Also store a "previous path" so that the user can cancel
            self.entry.prev_text = self.entry.get_text()

        self.entry.grab_focus()
        # the intention here is place the cursor just left of the '.nc' or '.ngc'
        dot_index = self.entry.get_text().rfind('.')
        # rfind() returns -1 if not found
        self.entry.set_position(dot_index)


    def _perform_layout(self):
        '''
        Based on the buttonlist and current attributes, run the layout logic to resize and arrange widgets so that
        no text is clipped.
        '''
        # This is only designed to be called once - after all init work has been done.
        assert not self._layout_called
        self._layout_called = True

        max_btn_w = 0
        max_btn_h = 0
        total_btn_w = 0
        if len(self.buttonlist) > 0:
            max_btn_w, max_btn_h = self.buttonlist[0].size_request()
            total_btn_w = max_btn_w
            for bb in self.buttonlist[1:]:
                w, h = bb.size_request()
                max_btn_h = max(max_btn_h, h)
                max_btn_w = max(max_btn_w, w)
                total_btn_w += w

        # Dynamically figure out how big we need to make the dialog to not clip the text
        # This markup is used for the label and the entry_label in a common fashion.
        markup_template = '<span weight="bold" font_desc="Roboto Condensed 11" foreground="white">{}</span>'

        escaped_popup_message = ui_misc.escape_markup(self.popup_message)
        markup = markup_template.format(escaped_popup_message)
        self.label.set_markup(markup)
        pango_layout = self.label.get_layout()

        # this is the size of the drawn-in dialog border for one side.
        self.BORDER_PIXELS = 4
        self.INNER_PIXELS = 2

        ##############################################
        # Decide how wide the dialog is going to be.  Pango layout will tell us the height needed.
        width_needed = self.BORDER_PIXELS*2 + self.INNER_PIXELS*2 + self.TEXT_PADDING_HORIZ + (len(self.buttonlist) * self.TEXT_PADDING_HORIZ) + total_btn_w

        # Grow to about 1/3rd the width of the screen as a minimum.
        width_needed = max(width_needed, 1024/3)

        # If the text is long, consider going even wider to about 1/2 the screen or whatever the buttons need.
        if len(self.popup_message) > 120:
            width_needed = max(width_needed, 1024/2)

        # If the touchscreen is enabled, make sure we're wide enough for it
        if self.touchscreen_enabled:
            w, h = self.pad.size_request()
            width_needed = max(width_needed, w)

        # If we have the optional fixed container child, make sure we're wide enough for it
        if self._optional_fixed_child:
            # ask the file chooser what its minimum size is
            w, h = self._optional_fixed_child.get_size_request()
            w += (self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ)*2
            width_needed = max(width_needed, w)

        # we don't let the label use the entire width of the gtk fixed container so adjust it to remove the padding on each side
        pango_width = width_needed - (self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ)*2
        pango_layout.set_width(pango_width * pango.SCALE)
        pango_layout.set_markup(markup)
        textwidth = 0
        textheight = 0
        if len(self.popup_message) > 0:
            textwidth, textheight = pango_layout.get_pixel_size()


        ############################################
        # Now figure out height needed
        height_needed = self.BORDER_PIXELS*2 + self.INNER_PIXELS*2 + self.TEXT_PADDING_VERT + textheight + max_btn_h + self.TEXT_PADDING_VERT

        if len(self.popup_message) > 0:
            height_needed += self.VERT_GAP_BETWEEN_LABEL_AND_BUTTON_ROW

        if self.entry_enabled:
            height_needed += max_btn_h + self.TEXT_PADDING_VERT  # the button height is about right

        if self.checkbox_enabled:
            height_needed += max_btn_h/2 + self.TEXT_PADDING_VERT  # half a button height is a good approximation of the vertical room needed for the checkbox

        if self.touchscreen_enabled:
            w, h = self.pad.size_request()
            height_needed += h

        if self._optional_fixed_child:
            # ask the optional fixed container child what its minimum size is
            w, h = self._optional_fixed_child.get_size_request()
            height_needed += h + self.TEXT_PADDING_VERT
            assert w <= width_needed, "Someone changed min width needed and goofed"

        # Sanity check for devs
        assert width_needed <= 1024, "Clip warning as width needed {:d} is larger than screen".format(width_needed)
        assert height_needed <= 768, "Clip warning as height needed {:d} is larger than screen".format(height_needed)

        # The background texture image doesn't have any black border to make it
        # appear as a top level dialog window very well.
        # Intead of hard coding many sizes of this in .jpg files, just draw
        # a black border exactly where we need it.

        pixbuf = self.background.get_pixbuf()
        pixmap, mask = pixbuf.render_pixmap_and_mask()
        cm = pixmap.get_colormap()
        gray = cm.alloc_color('lightgray')
        gc = pixmap.new_gc(foreground=gray)
        gc.set_line_attributes(self.BORDER_PIXELS, gtk.gdk.LINE_SOLID, gtk.gdk.CAP_BUTT, gtk.gdk.JOIN_MITER)
        pixmap.draw_rectangle(gc, gtk.FALSE, 1, 1, width_needed-1, height_needed-1)

        black = cm.alloc_color('black')
        gc = pixmap.new_gc(foreground=black)
        gc.set_line_attributes(self.INNER_PIXELS, gtk.gdk.LINE_SOLID, gtk.gdk.CAP_BUTT, gtk.gdk.JOIN_MITER)
        pixmap.draw_rectangle(gc, gtk.FALSE, self.BORDER_PIXELS, self.BORDER_PIXELS, \
                              width_needed - self.BORDER_PIXELS*2, height_needed - self.BORDER_PIXELS*2)

        self.background.set_from_pixmap(pixmap, mask)

        self.fixed.set_size_request(width_needed, height_needed)

        # make the label large enough so it doesn't clip any of the text
        # really should be just textheight, but I saw magic situations where every once in awhile
        # the last line of text would be clipped.  Must be something buggy or some other padding or
        # that I'm not grasping.  Just slop it a little taller since we know we have the space.
        # same for width where word wrapping was just a little off.  maybe its some font interaction bug
        # with roboto or something?  or just a gtk 2.x bug.

        next_widget_y = self.BORDER_PIXELS + self.INNER_PIXELS

        if len(self.popup_message) > 0:
            self.label.set_size_request(textwidth+4, textheight + self.VERT_GAP_BETWEEN_LABEL_AND_BUTTON_ROW)
            self.fixed.put(self.label, self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ, next_widget_y)
            next_widget_y += textheight + self.VERT_GAP_BETWEEN_LABEL_AND_BUTTON_ROW
        else:
            next_widget_y += self.TEXT_PADDING_VERT

        # position the buttons below the text
        # first take some measurements...
        fixed_width, fixed_height = self.fixed.size_request()

        # position the entry label and entry widget below the text
        if self.entry_enabled:
            entry_y = next_widget_y
            entry_x = self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ
            self.fixed.put(self.entry_label, entry_x, entry_y + 3)  # a little fudge so that the label seems better aligned to the entry widget

            # Need to figure out how wide the label wants to be. Set it up and simply ask it.
            self.entry_label.set_max_width_chars(-1)
            markup = markup_template.format(self.entry_label_message)
            self.entry_label.set_markup(markup)
            x, y = self.entry_label.size_request()
            entry_x += x + self.TEXT_PADDING_HORIZ
            self.fixed.put(self.entry, entry_x, entry_y)

            # Figure out how much width of the dialog is left and size the entry widget appropriately.
            entry_width = fixed_width - self.BORDER_PIXELS - self.INNER_PIXELS - self.TEXT_PADDING_HORIZ - entry_x
            self.entry.set_size_request(entry_width, int(max_btn_h*.75))

            next_widget_y += max_btn_h + self.TEXT_PADDING_VERT  # above we approximated the extra height needed for the entry as button height so be consistent here
        else:
            # still need the entry on the fixed to receive the button press event to trigger the ok button.
            # but want to hide it on the ok/cancel popup, so set to zero size (entry.hide or entry.set_visible didn't work)
            self.entry.set_size_request(0, 0)
            self.entry_label.set_size_request(0, 0)
            # some damn rendering bug still shows a white dot from the entry controls so move them way in the corner.
            self.fixed.put(self.entry, width_needed, height_needed)
            self.fixed.put(self.entry_label, width_needed, height_needed)

        # stick the optional fixed container child in if we have one
        if self._optional_fixed_child:
            w, h = self._optional_fixed_child.get_size_request()
            w = width_needed - ((self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ) * 2)
            self._optional_fixed_child.set_size_request(w, h)
            self.fixed.put(self._optional_fixed_child, self.BORDER_PIXELS + self.INNER_PIXELS + self.TEXT_PADDING_HORIZ, next_widget_y)
            next_widget_y += h + self.TEXT_PADDING_VERT

        # button row is right justified so build from that edge
        # y coordinate is constant for all buttons
        btn_y = next_widget_y
        btn_x = fixed_width - self.BORDER_PIXELS - self.INNER_PIXELS - self.TEXT_PADDING_HORIZ
        for bb in reversed(self.buttonlist):
            w, h = bb.size_request()
            btn_x -= w
            self.fixed.put(bb, btn_x, btn_y)
            btn_x -= self.TEXT_PADDING_HORIZ
            bb.enable()
        next_widget_y = btn_y + max_btn_h + self.TEXT_PADDING_VERT

        if self.checkbox_enabled:
            self.fixed.put(self.checkbox, self.TEXT_PADDING_HORIZ, next_widget_y)
            next_widget_y += max_btn_h/2

        # show the touchscreen pad
        if self.touchscreen_enabled:
            self.fixed.put(self.pad.fixed, self.TEXT_PADDING_HORIZ, next_widget_y)

        if len(self.buttonlist) > 0:
            # button to the far right is default and has focus, unless the entry widget is shown
            if self.entry_enabled:
                self.entry.grab_focus()
            else:
                self.buttonlist[-1].grab_focus()
                if self.buttonlist[-1] == self.yes_button:
                    self.yes_button.load_image('Yes_Highlight.png')
                elif self.buttonlist[-1] == self.no_button:
                    self.no_button.load_image('No_Highlight.png')


    def handle_enter_key(self):
        """Default function to handle an enter keypress.
        This is designed to be overridden by a child class if need be.
        """
        # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
        self.ok_button.emit('button-press-event', None)
        self.ok_button.emit('button-release-event', None)


    def on_entry_key_press(self, widget, event, data=None):
        kv = event.keyval
        if kv == gtk.keysyms.Escape:
            widget.set_text(widget.prev_text)
            self.window.grab_focus()
            return True

        if kv in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            self.handle_enter_key()
            return True
        return False

    def set_entry_filepath(self, path):
        self.path = path
        self.entry.set_text((os.path.split(self.path)[1]))

    def on_ok_button_release_event(self, widget, data=None):
        widget.unshift()
        if self.entry_enabled:
            self.filename = self.entry.get_text()
            if len(self.filename) > 0:
                self.path = os.path.join(os.path.split(self.path)[0], self.filename)
            else:
                self.path = ''
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

    def on_cancel_button_release_event(self, widget, data=None):
        widget.unshift()
        self.filename = ''
        self.path = ''
        self.response = gtk.RESPONSE_CANCEL
        gtk.main_quit()

    def on_yes_button_release_event(self, widget, data=None):
        widget.unshift()
        self.response = gtk.RESPONSE_YES
        gtk.main_quit()

    def on_no_button_release_event(self, widget, data=None):
        widget.unshift()
        self.response = gtk.RESPONSE_NO
        gtk.main_quit()

    def on_save_button_release_event(self, widget, data=None):
        widget.unshift()
        if self.entry_enabled:
            self.filename = self.entry.get_text()
            self.path = os.path.join(os.path.split(self.path)[0], self.filename)
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

    def on_overwrite_button_release_event(self, widget, data=None):
        widget.unshift()
        self.filename = self.path
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

    def on_update_button_release_event(self, widget, data=None):
        widget.unshift()
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

    def on_append_button_release_event(self, widget, data=None):
        widget.unshift()
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

    def on_entry_activate(self, widget, data=None):
        # TODO - prelight the OK button and give it focus so you can just press enter to confirm.
        widget.prev_text = widget.get_text()

    def set_label_text(self, markup):
        self.label.set_markup(markup)

    def get_filename(self):
        return self.filename

    def get_path(self):
        return self.path

    def show_all(self):
        self.window.show_all()

    def present(self):
        self.window.present()

    def run(self):
        assert self._layout_called
        self.window.show_all()
        # make sure it is top of z-order stack so user can see it, sometimes this is a problem
        # if no parent window was provided and we're running non-full screen in a dev env (can get
        # hidden by a terminal pretty easily)
        self.window.present()
        gtk.main()

    def destroy(self):
        self.window.destroy()

        # Smack Gtk 2 in order to clue it in which window should be at the top of the z-order.
        # This is not needed by default if you create your top level modal window decorated (with a title bar).
        # But the title bar leaks access out to the window manager menu.
        if self.parentwindow:
            self.parentwindow.present()

    def __enter__(self):
        """ Enter function returns a popup object when using the with statement. Ex:

            with popup(...) as dialog:
                if dialog.response == gtk.RESPONSE_OK:
                    ...
                else:
                    ...
                ...

            This will automatically call the "__exit__" method and clean up the
            dialog, no matter what happens in the with block
        """
        self.run()
        return self

    def __exit__(self, type, value, traceback):
        """ Automatically called at the end of a with statement."""
        self.destroy()

        # Force necessary window repainting to make sure message dialog is fully removed from screen
        ui_misc.force_window_painting()


class delete_files_popup(popup):
    def __init__(self, parentwindow, dircount, filecount):
        """
        Prompt the user for confirmation if they intend to delete files or folders.
        """
        popup.__init__(self, parentwindow,
                       "Deleting {:d} files and {:d} folders, are you sure?".format(filecount, dircount),
                       touchscreen_enabled=False,
                       checkbox_enabled=False,
                       entry_enabled=False)
        self.buttonlist = [self.cancel_button, self.ok_button]
        self._perform_layout()


class new_filename_popup(popup):
    def __init__(self, parentwindow, popup_message, touchscreen_enabled):
        popup.__init__(self, parentwindow, popup_message,
                       touchscreen_enabled=touchscreen_enabled,
                       checkbox_enabled=False,
                       entry_enabled=True)
        self.buttonlist = [self.cancel_button, self.ok_button]
        self._set_entry_label_message("Name:")
        self._perform_layout()


class confirm_file_overwrite_popup(popup):
    def __init__(self, parentwindow, path, touchscreen_enabled):
        popup.__init__(self, parentwindow,
                       "File with same name already exists in this location.  Rename, overwrite, or cancel?",
                       touchscreen_enabled=touchscreen_enabled,
                       checkbox_enabled=False,
                       entry_enabled=True)
        self.buttonlist = [self.cancel_button, self.overwrite_button, self.save_button]
        self._set_entry_label_message("Name:")
        self._set_entry_to_path(path)
        self._perform_layout()

        # Don't allow the user to save unless the file name is changed
        self.save_button.disable()
        self.entry.connect('changed', self.check_filename)

    def check_filename(self,widget):
        directory, name = os.path.split(self.path)

        if name != widget.get_text():
            self.save_button.enable()
        else:
            self.save_button.disable()

    def handle_enter_key(self):
        # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
        self.save_button.emit('button-press-event', None)
        self.save_button.emit('button-release-event', None)


class ok_cancel_popup(popup):
    def __init__(self, parentwindow, message, cancel=True, checkbox=False):
        popup.__init__(self, parentwindow, message,
                       touchscreen_enabled=False,
                       checkbox_enabled=checkbox,
                       entry_enabled=False)
        if cancel:
            self.buttonlist = [self.cancel_button, self.ok_button]
        else:
            self.buttonlist = [self.ok_button]

        self._perform_layout()


class shutdown_confirmation_popup(popup):
    def __init__(self, parentwindow):
        popup.__init__(self, parentwindow,
                       "E-stop the machine tool before proceeding.\n\nClick OK to shut down the control computer.",
                       touchscreen_enabled=False,
                       checkbox_enabled=False,
                       entry_enabled=False)
        self.buttonlist = [self.cancel_button, self.ok_button]
        self._perform_layout()


class software_update_confirmation_popup(popup):
    def __init__(self, parentwindow):
        popup.__init__(self, parentwindow, "E-stop the machine tool before proceeding.\n\nClick OK to update the control software.", False, False, False)
        self.buttonlist = [self.ok_button]
        self._perform_layout()


class yes_no_cancel_popup(popup):
    def __init__(self, parentwindow, message):
        popup.__init__(self, parentwindow, message, False, False, False)
        self.buttonlist = [self.cancel_button, self.no_button, self.yes_button]
        self._perform_layout()

    def handle_enter_key(self):
        # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
        self.yes_button.emit('button-press-event', None)
        self.yes_button.emit('button-release-event', None)


class yes_no_popup(popup):
    def __init__(self, parentwindow, message):
        popup.__init__(self, parentwindow, message, False, False, False)
        self.buttonlist = [self.yes_button, self.no_button]
        self._perform_layout()

    def handle_enter_key(self):
        # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
        self.no_button.emit('button-press-event', None)
        self.no_button.emit('button-release-event', None)


class generic_entry_popup(popup):
    def __init__(self, parentwindow, entry_label_message, entry_default, touchscreen_enabled):
        popup.__init__(self, parentwindow, '',
                       touchscreen_enabled=touchscreen_enabled,
                       checkbox_enabled=False,
                       entry_enabled=True)
        self.buttonlist = [self.cancel_button, self.ok_button]
        self._set_entry_label_message(entry_label_message)
        self._set_entry(entry_default)
        self._perform_layout()


class status_popup(popup):
    '''
    Popup with just message and no buttons. Useful for UI feedback during a blocking process
    like programming the mesa flash.
    '''
    def __init__(self, parentwindow, message):
        popup.__init__(self, parentwindow, message,
                       touchscreen_enabled=False,
                       checkbox_enabled=False,
                       entry_enabled=False)
        self.buttonlist = [ ]
        self._perform_layout()
