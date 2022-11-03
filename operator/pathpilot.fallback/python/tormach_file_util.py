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

import gtk
import pango
import os
import numpad
import shutil
import fnmatch
import subprocess
import time
import glib
#
# This style of import makes clear where the constants used come from, rather
# than a blanket import
import constants as const
import plexiglass
import singletons
import errors
import re
import thread
import ppglobals
import fswatch
import popupdlg
import btn
import string
import fsutil
import tooltipmgr
import ui_misc

ITEM_WIDTH = 140
PADDING = 10
BUTTON_WIDTH = 100
ARROW_WIDTH = 35
BUTTON_HEIGHT = 37
DEFAULT_RESTRICTED_DIR = os.path.join(os.getenv('HOME'), 'gcode')


def get_disk_free_space_bytes(path):
    try:
        result = subprocess.check_output("df --output=avail '%s'" % path, shell=True)
        freebytestr = result.splitlines()[1].strip()
        freebytes = int(freebytestr) * 1024   # df reports in 1K blocks
        return freebytes
    except subprocess.CalledProcessError:
        return 0

def connect_tooltip_signals(widget):
    ttmgr = tooltipmgr.TTMgr()
    if ttmgr:
        widget.connect("enter-notify-event", ttmgr.on_mouse_enter)
        widget.connect("leave-notify-event", ttmgr.on_mouse_leave)


def count_dirs_and_files(selected_list):
    '''
    Counts files and dirs in a list of file and dir names
    Handy for advising user on how much the delete operation they're about to do is going to impact
    Might be handy for copy operations also
    Returns a tuple of (directory count, file count)
    '''
    fc = 0
    dc = 0
    for ii in selected_list:
        if os.path.isdir(ii):
            dc += 1
            for root, dirs, files in os.walk(ii):
                fc += len(files)
                dc += len(dirs)
        elif os.path.isfile(ii):
            fc += 1
    return (dc, fc)


def filesystem_sync(errorhandler=None):
    # Force a file system sync because we're paranoid.
    p = subprocess.Popen(['sync'])
    p.wait()
    if p.returncode != 0 and errorhandler is not None:
        errorhandler.write('File system sync failed.', const.ALARM_LEVEL_LOW)

def filesystem_dump_caches(errorhandler=None):
    # now force the linux vm to give up any cached pages
    # this is commonly used to make sure that if we read something from a USB drive
    # that we are actually testing the media and not just pulling the bits back out of
    # the ram cache that got filled when we copied a file on to the USB drive
    p = subprocess.Popen(['drop_caches_once.sh'])
    p.wait()
    if p.returncode != 0 and errorhandler is not None:
        errorhandler.write('Unable to flush file system cache and return memory to system.', const.ALARM_LEVEL_LOW)

def return_empty_string():
    return ''

def is_plain_text_file(self, path):
    # check if plain text file
    try:
        # Note: be sure to quote the path in case it contains spaces
        p = subprocess.Popen(['file -b --mime-type "%s"' % path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out, err = p.communicate()
    except:
        self.error_handler.write("Exception running 'file' on %s" % path, const.ALARM_LEVEL_LOW)
        return False

    # we've had enough false-positives on random text strings inside gcode comments
    # triggering all sorts of "language" types that we now just look for text/ as the major
    # indication that its ok to try to load.

    find_index = out.find('text/')
    if find_index == 0:
        return True

    # not plain text
    return False

def open_text_file(self, path, buffer, bytes_desired = 0):
    if bytes_desired == 0:
        fileobj = open(path)
    else:
        fileobj = open(path, buffering=bytes_desired)

    try:
        if bytes_desired == 0:
            raw_str = fileobj.read()
        else:
            raw_str = fileobj.read(bytes_desired)

        try:
            raw_str.decode('utf-8') #try to decode as utf-8, which is what we want
            #this passes either utf-8 (unicode) or straight 7 bit ascii unchanged.
            #But python nominal file open() or read() will translate 8 bit input files
            #thinking they are utf-8, which causes issues.
            #For us, causes Gcode viewer pane to display blank code lines.
        except UnicodeDecodeError:
            self.error_handler.log("Gcode file %s contains extended ascii. Converting file." % path)
            final_str = unicode(raw_str, encoding='latin_1', errors='replace')
        else:
            final_str = raw_str

        # count number of lines so we can easily tell if we executed the last line or not.
        self.gcode_last_line = final_str.rstrip().count("\n") + 1

        buffer.set_text(final_str)
    finally:
        fileobj.close()


def verify_file_extension(filename, default_extension):
    name, ext = os.path.splitext(filename)
    if ext == '':
        filename = name + default_extension
    return filename


def overwrite_check(source, dest):
    filename = os.path.split(source)[1]
    if os.path.exists(dest + os.path.sep + filename):
        return True
    else:
        return False

def get_gcode_directory():
    return DEFAULT_RESTRICTED_DIR

#
# File tab
#

class file_chooser_base():
    def __init__(self,
                 parentwindow,
                 fixed,
                 preview_buffer,
                 touchscreen_enabled,
                 load_gcode_file,
                 load_gcode_button,
                 edit_gcode_button,
                 conv_edit_button,
                 error_handler,
                 transfer_button,
                 get_current_gcode_path,
                 clipboard_mgr):

        self.parentwindow = parentwindow    # for modal dialog z-order enforcement
        self.fixed = fixed
        self.load_gcode_file = load_gcode_file
        self.load_gcode_button = load_gcode_button
        self.edit_gcode_button = edit_gcode_button
        self.conv_edit_button = conv_edit_button
        self.error_handler = error_handler
        self.transfer_button = transfer_button
        self.preview_buffer = preview_buffer
        self.touchscreen_enabled = touchscreen_enabled
        self.clipboard_mgr = clipboard_mgr

        self.eject_button = None

        self.home_button = btn.ImageButton('home-button.png', 'file_home_button')
        self.back_button = btn.ImageButton('back-button.png', 'file_back_button')

        self.clipboard_button = btn.ImageButton('hamburger-menu.png', 'clipboard_button')
        self.clipboard_button.set_size_request(34, 31)

        self.freespace_label = gtk.Label()
        self.freespace_label.set_alignment(0.0, 0.5)   # left align and center vertically
        self.freespace_label.set_size_request(250, 25)

        self.home_button.set_size_request(99, 37)
        self.back_button.set_size_request(35, 37)

        connect_tooltip_signals(self.home_button)
        self.home_button.connect("button-release-event", self.on_home_button_release_event)

        connect_tooltip_signals(self.back_button)
        self.back_button.connect("button-release-event", self.on_up_button_release_event)

        connect_tooltip_signals(self.clipboard_button)
        self.clipboard_button.connect("button-press-event", self.on_clipboard_button_press_event)

        # locations set intially, but likely changed via set_location method
        self.home_button.x = 55
        self.home_button.y = 10
        self.back_button.x = 10
        self.back_button.y = 10

        # add widgets to fixed container
        self.fixed.put(self.home_button, self.home_button.x, self.home_button.y)
        self.fixed.put(self.back_button, self.back_button.x, self.back_button.y)

        # function passed in to retrieve the currently loaded gcode filename
        self.get_current_gcode_path = get_current_gcode_path

        self.file_chooser = gtk.FileChooserWidget()
        self.file_chooser.connect('event', self.on_filechooser_click_event)

        # This is critical as it lets the library code know that we are not doing a save or save-as type of operation,
        # so the custom gtk+ C code hides more widgets to enforce the file system sandbox.
        self.file_chooser.set_action(gtk.FILE_CHOOSER_ACTION_OPEN)

        self.file_chooser.set_size_request(330, 302)
        self.file_chooser.set_select_multiple(True)
        self.file_chooser.set_local_only(True)
        self.file_chooser.set_current_folder(const.GCODE_BASE_PATH)
        font = pango.FontDescription('Roboto Condensed 10')
        self.file_chooser.modify_font(font)
        self.fixed = fixed
        self.fixed.put(self.file_chooser, 10, 42)

        # this effectively disables drag and drop by making the threshold larger than the screen
        # TODO: fix drag and drop
        settings = gtk.settings_get_default()
        settings.set_property('gtk-dnd-drag-threshold', 2048)

        self.file_chooser.connect("current-folder-changed", self.on_current_folder_changed)

    def refresh_free_space_label(self, path=None):
        if not path:
            path = self.file_chooser.get_current_folder()
        freebytes = get_disk_free_space_bytes(path)
        freebytes_string = ui_misc.humanbytes(freebytes)
        self.freespace_label.set_markup('<span weight="regular" font_desc="Roboto Condensed 10" foreground="white">Free space: {:s}</span>'.format(freebytes_string))

    def destroy(self):
        self.file_chooser.destroy()

    def on_filechooser_click_event(self, widget, event):
        if event.type == gtk.gdk.BUTTON_RELEASE:
            # Trigger the tooltip for this selected file.
            # This is the only way touch screen users can see tooltips easily!
            display = gtk.gdk.display_get_default()
            gtk.tooltip_trigger_tooltip_query(display)

    def on_clipboard_button_press_event(self, widget, event, data=None):
        self.clipboard_mgr.on_clipboard_button_press_event(self.file_chooser, self.refresh_free_space_label, widget, event, data)
        glib.idle_add(widget.unshift)  # this makes the button appear to dip in just briefly

    # drag and dropping changes the current folder but doesn't appear to do anything else
    # set it back to the restricted directory if outside
    def on_current_folder_changed(self, widget):
        directory = self.file_chooser.get_current_folder()
        if not directory.startswith(self.restricted_directory):
            self.file_chooser.set_current_folder(self.restricted_directory)

    def set_location(self, x, y):
        self.home_button.x = x + 45
        self.home_button.y = y
        self.eject_button.x = x + 160
        self.eject_button.y = y
        self.back_button.x = x
        self.back_button.y = y

        self.fixed.move(self.home_button, x + 45, y )
        self.fixed.move(self.back_button, x, y  )

    def connect(self, signal_name, callback_name):
        self.file_chooser.connect(signal_name, callback_name)

    def set_restricted_directory(self, directory):
        self.restricted_directory = directory
        self.set_current_directory(directory)

    def set_current_directory(self, directory):
        self.file_chooser.set_current_folder(directory)

    def get_current_directory(self):
        return self.file_chooser.get_current_folder()

    def on_home_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        self.set_current_directory(self.restricted_directory)

        # if moving to USB_MEDIA_MOUNT_POINT and only one directory is there assume it's
        # the USB stick and change into it (difference with the way mount points for removable
        # media area handled with Mint 17.3)
        if self.restricted_directory == const.USB_MEDIA_MOUNT_POINT:
            fsutil.adjust_media_directory_if_necessary(self, self.restricted_directory)

    def on_up_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        if self.get_current_directory() == self.restricted_directory:
            return
        self.set_current_directory(os.path.dirname(self.get_current_directory()))

    def on_new_dir_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        self.new_directory(widget)

    def on_rename_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        if self.selected:
            self.rename_item(widget)

    def on_delete_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        self.delete_selected_items()

    def rename_item(self, widget):
        """ Unified rename function for files and directories.
        Since the OS treats renaming the same way for both files and
        directories, it's easy to have a unified rename method here.
        """
        old_path = self.selected
        if len(old_path) == 0:
            return
        dialog = popupdlg.new_filename_popup(self.parentwindow, '', self.touchscreen_enabled)
        dialog.set_entry_filepath(old_path)
        dialog.run()
        dialog.destroy()
        if dialog.response != gtk.RESPONSE_OK:
            return
        path, name = os.path.split(dialog.get_path())

        if old_path == self.get_current_gcode_path():
            res_dir = self.restricted_directory
            if res_dir[-1] != '/':
                res_dir += '/'
            file_name_for_display = old_path.replace(res_dir, '')
            self.error_handler.write("Cannot rename currently loaded gcode program: %s" % file_name_for_display, const.ALARM_LEVEL_LOW)
            return

        fullpath = os.path.join(path, name)
        if fullpath != old_path and len(fullpath) > 0:
            try:
                self.error_handler.log("renaming  %s  -->   %s" % (old_path, fullpath))
                os.rename(old_path, fullpath)
            except OSError, msg:
                self.error_handler.log("Rename file error: %s" % msg)

        # now change the selection in the file chooser to select the item we just renamed.
        self.file_chooser.unselect_all()
        # we need to 'kick' the file chooser to see all the new items we just created
        # otherwise we can't 'select' them for the user.
        self.file_chooser.set_current_folder(path)
        self.file_chooser.select_filename(fullpath)

    def new_directory(self, widget):
        with popupdlg.new_filename_popup(self.parentwindow, '', self.touchscreen_enabled) as dialog:
            if dialog.response == gtk.RESPONSE_CANCEL:
                # no action on cancel
                return
            new_dir_name = dialog.get_filename()
            if len(new_dir_name) > 0:
                path = os.path.join(self.file_chooser.get_current_folder(), new_dir_name)
                if os.path.isdir(path):
                    self.error_handler.write("Directory already exists: %s" % new_dir_name, const.ALARM_LEVEL_LOW)
                    return
                try:
                    os.mkdir(path)
                except OSError, msg:
                    self.error_handler.log("Directory creation error %s" % msg)


    def delete_selected_items(self):
        # this is broken up a little bit so that the delete confirmation dialog is
        # destroyed before we go off to do the possibly time consuming delete work.
        # this lets the plexiglass look better on the screen.

        # get counts to give them feedback on the magnitude of what they are about to do...
        selected_list = self.file_chooser.get_filenames()
        dircount, filecount = count_dirs_and_files(selected_list)
        doit = False
        with popupdlg.delete_files_popup(self.parentwindow, dircount, filecount) as dialog:
            doit = (dialog.response == gtk.RESPONSE_OK)

        if doit:
            # This can take a long time so toss up the plexiglass
            with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:
                for name in selected_list:
                    try:
                        if os.path.isdir(name):
                            self.remove_directory(name)
                        else:
                            self.remove_file(name)
                    except OSError as e:
                        # warn about this, but keep going because of the multi-selection
                        self.error_handler.write(str(e), const.ALARM_LEVEL_LOW)

                    except IOError as e:
                        # warn about this, but keep going because of the multi-selection
                        self.error_handler.write(str(e), const.ALARM_LEVEL_LOW)

            self.refresh_free_space_label()


    def remove_file(self, path):
        res_dir = self.restricted_directory
        if res_dir[-1] != '/':
            res_dir += '/'
        file_name_for_display = path.replace(res_dir, '')

        if os.path.exists(path):
            if path == self.get_current_gcode_path():
                self.error_handler.write("Cannot delete currently loaded gcode program: %s" % file_name_for_display, const.ALARM_LEVEL_LOW)
                return
            self.error_handler.log("deleting: %s" % file_name_for_display)
            os.remove(path)

            self.refresh_free_space_label()


    def remove_directory(self, path):
        # this might be a symbolic link...such as Dropbox
        # and shutil.rmtree() pukes and throws exceptions on symbolic links
        res_dir = self.restricted_directory
        if res_dir[-1] != '/':
            res_dir += '/'
        path_for_display = path.replace(res_dir, '')
        if os.path.exists(path):
            if os.path.islink(path):
                # the combo of the two calls below achieves the equivalent of shutil.rmtree()
                # which is what we want.
                self.error_handler.log("Deleting: %s using rm -rf via shell because its a symlink." % path_for_display)
                subprocess.call("rm -rf '%s/'" % path, shell=True)  # this removes everything inside the symlink
                subprocess.call("rm -rf '%s'" % path, shell=True)   # this removes the symlink itself
            else:
                self.error_handler.log("Deleting: %s" % path_for_display)
                shutil.rmtree(path)

            filesystem_sync(self.error_handler)

            self.refresh_free_space_label()


    @property
    def selected_list(self):
        return self.file_chooser.get_filenames()

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

    def set_selection(self, path):
        self.file_chooser.unselect_all()
        self.file_chooser.select_filename(path)


class hd_file_chooser(file_chooser_base):
    def __init__(self,
                 parentwindow,
                 fixed,
                 preview_buffer,
                 touchscreen_enabled,
                 load_gcode_file,
                 load_gcode_button,
                 edit_gcode_button,
                 conv_edit_button,
                 error_handler,
                 transfer_button,
                 get_current_gcode_path,
                 clipboard_mgr,
                 restricted_dir,
                 on_selection_callback=None):

        file_chooser_base.__init__(self,
                                   parentwindow,
                                   fixed,
                                   preview_buffer,
                                   touchscreen_enabled,
                                   load_gcode_file,
                                   load_gcode_button,
                                   edit_gcode_button,
                                   conv_edit_button,
                                   error_handler,
                                   transfer_button,
                                   get_current_gcode_path,
                                   clipboard_mgr)

        self.load_gcode_button = load_gcode_button
        self.edit_gcode_button = edit_gcode_button
        self.conv_edit_button = conv_edit_button
        self.restricted_directory = restricted_dir
        self.on_selection_callback = on_selection_callback

        # ------------------------------------
        # buttons
        # ------------------------------------
        self.new_dir_button = btn.ImageButton('new-folder.png', 'file_new_folder_button')
        self.rename_button = btn.ImageButton('rename.png', 'file_rename_button')
        self.delete_button = btn.ImageButton('delete.png', 'file_delete_button')

        # TODO: get size from .png dimesions?
        self.new_dir_button.set_size_request(88, 37)
        self.rename_button.set_size_request(88, 37)
        self.delete_button.set_size_request(88, 37)

        # Connect button signals to appropriate callbacks
        connect_tooltip_signals(self.new_dir_button)
        connect_tooltip_signals(self.rename_button)
        connect_tooltip_signals(self.delete_button)
        self.new_dir_button.connect("button-release-event", self.on_new_dir_button_release_event)
        self.rename_button.connect("button-release-event", self.on_rename_button_release_event)
        self.delete_button.connect("button-release-event", self.on_delete_button_release_event)

        # Set button locations within the GUI
        x = 10
        self.clipboard_button.x = x
        x += self.clipboard_button.width + 5
        self.new_dir_button.x = x
        x += self.new_dir_button.width + 5
        self.rename_button.x = x
        x += self.rename_button.width + 5
        self.delete_button.x = x
        x += self.delete_button.width + 5

        self.clipboard_button.y = 353
        self.new_dir_button.y = 350
        self.rename_button.y = 350
        self.delete_button.y = 350

        # Add new buttons to fixed window
        self.fixed.put(self.clipboard_button, self.clipboard_button.x, self.clipboard_button.y)
        self.fixed.put(self.new_dir_button, self.new_dir_button.x, self.new_dir_button.y)
        self.fixed.put(self.rename_button, self.rename_button.x, self.rename_button.y)
        self.fixed.put(self.delete_button, self.delete_button.x, self.delete_button.y)

        # Add free space label
        self.fixed.put(self.freespace_label, 12, 385)

        # selection-changed
        self.file_chooser.connect("selection-changed", self.on_selection_changed)
        self.file_chooser.connect("file-activated", self.on_load_gcode_file)

    # --------------------------
    # Callbacks
    # --------------------------

    def on_load_gcode_file(self, widget, data=None):
        if self.has_single_selection != '':
            self.load_gcode_file()

    def on_selection_changed(self, widget, data=None):
        selected_list = self.file_chooser.get_filenames()

        if len(selected_list) != 0:
            self.transfer_button.enable()
        else:
            self.transfer_button.disable()

        # preview
        if os.path.exists(self.selected_path):
            if is_plain_text_file(self, self.selected_path):
                # Then, load the preview and enable editing
                open_text_file(self, self.selected_path, self.preview_buffer, 10000)
                self.edit_gcode_button.enable()
                self.conv_edit_button.disable()
                self.load_gcode_button.enable()
                if self.on_selection_callback is not None:
                    if callable(self.on_selection_callback):
                        self.on_selection_callback()
            else:
                self.preview_buffer.set_text('')
                self.edit_gcode_button.disable()
                self.conv_edit_button.disable()

                # If its an image file, enable the load button so we open the image viewer - enables
                # easy troubleshooting on the machine.
                root,ext = os.path.splitext(self.selected_path)
                if ext.upper() in (".PNG", ".JPG", ".JPEG", ".PDF", ".MP4", ".MOV", ".M4V"):
                    self.load_gcode_button.enable()
                else:
                    self.load_gcode_button.disable()
        else:
            self.preview_buffer.set_text('')
            self.edit_gcode_button.enable()
            self.conv_edit_button.disable()
            self.load_gcode_button.disable()


# global needed because static event callback method has no other data to go on unfortunately.
_usb_file_chooser = None

class USBFSHandler(fswatch.FileSystemEventHandler):
    @staticmethod
    def on_modified(event):
        # This is called anytime the contents of the path that the Watcher is monitoring is modified (files or dirs come or go - but not recursively).
        # NOTE!
        # This callback is NOT on the GUI thread so you can't
        # manipulate any Gtk objects.  The only thing we can really do is schedule a callback to
        # the GUI thread using glib.idle_add.
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        global _usb_file_chooser
        glib.idle_add(fsutil.adjust_media_directory_if_necessary, _usb_file_chooser, _usb_file_chooser.restricted_directory)
        glib.idle_add(usb_file_chooser_event_wrapper, _usb_file_chooser)


def usb_file_chooser_event_wrapper(usb_file_chooser):
    usb_file_chooser.mount_unmount_event_callback()
    return False  # Must return False as this is called from glib.idle_add() or it will get called again right away


class usb_file_chooser(file_chooser_base):
    def __init__(self,
                 parentwindow,
                 fixed,
                 preview_buffer,
                 touchscreen_enabled,
                 load_gcode_file,
                 load_gcode_button,
                 edit_gcode_button,
                 conv_edit_button,
                 error_handler,
                 transfer_button,
                 get_current_gcode_path,
                 clipboard_mgr,
                 restricted_dir,
                 mount_unmount_event_callback):

        file_chooser_base.__init__(self,
                                   parentwindow,
                                   fixed,
                                   preview_buffer,
                                   touchscreen_enabled,
                                   load_gcode_file,
                                   load_gcode_button,
                                   edit_gcode_button,
                                   conv_edit_button,
                                   error_handler,
                                   transfer_button,
                                   get_current_gcode_path,
                                   clipboard_mgr)

        self.mount_unmount_event_callback = mount_unmount_event_callback

        # replace HOME button image with USB button image
        self.home_button.load_image('usb-home-button.png')

        self.load_gcode_button = load_gcode_button
        self.edit_gcode_button = edit_gcode_button
        self.conv_edit_button = conv_edit_button
        self.restricted_directory = restricted_dir

        # X offset by 400 from hd chooser widgets
        self.fixed.move(self.file_chooser, 410, 42)

        # ------------------------------------
        # buttons
        # ------------------------------------
        self.new_dir_button = btn.ImageButton('new-folder.png', 'file_new_folder_button')
        self.rename_button = btn.ImageButton('rename.png', 'file_rename_button')
        self.delete_button = btn.ImageButton('delete.png', 'file_delete_button')

        self.new_dir_button.set_size_request(88, 37)
        self.rename_button.set_size_request(88, 37)
        self.delete_button.set_size_request(88, 37)

        # Connect button signals to appropriate callbacks
        connect_tooltip_signals(self.new_dir_button)
        connect_tooltip_signals(self.rename_button)
        connect_tooltip_signals(self.delete_button)
        self.new_dir_button.connect("button-release-event", self.on_new_dir_button_release_event)
        self.rename_button.connect("button-release-event", self.on_rename_button_release_event)
        self.delete_button.connect("button-release-event", self.on_delete_button_release_event)

        # Set button locations within the GUI
        x = 410
        self.clipboard_button.x = x
        x += self.clipboard_button.width + 5
        self.new_dir_button.x = x
        x += self.new_dir_button.width + 5
        self.rename_button.x = x
        x += self.rename_button.width + 5
        self.delete_button.x = x
        x += self.delete_button.width + 5

        self.clipboard_button.y = 353
        self.new_dir_button.y = 350
        self.rename_button.y = 350
        self.delete_button.y = 350

        # Add new buttons to fixed window
        self.fixed.put(self.clipboard_button, self.clipboard_button.x, self.clipboard_button.y)
        self.fixed.put(self.new_dir_button, self.new_dir_button.x, self.new_dir_button.y)
        self.fixed.put(self.rename_button, self.rename_button.x, self.rename_button.y)
        self.fixed.put(self.delete_button, self.delete_button.x, self.delete_button.y)

        # Add free space label
        self.fixed.put(self.freespace_label, 412, 385)

        # eject button
        self.eject_button = btn.ImageButton('eject-button.jpg', 'file_eject_button')
        self.eject_button.set_size_request(99, 37)
        connect_tooltip_signals(self.eject_button)
        self.eject_button.connect("button-release-event", self.on_eject_button_release_event)
        self.eject_button.x = 565
        self.eject_button.y = 10

        self.fixed.put(self.eject_button, self.eject_button.x, self.eject_button.y)

        # selection-changed
        self.file_chooser.connect("selection-changed", self.on_selection_changed)

        # if only one directory present switch to it
        fsutil.adjust_media_directory_if_necessary(self, self.restricted_directory)

        # USB chooser need to shift the buttons to the right from where the base class puts them
        self.set_location(410, 10)

        # start an efficient inotify based file system watcher on the USB
        # mount point directory so we can tell when the user plugs in a USB drive.
        global _usb_file_chooser
        _usb_file_chooser = self
        self.watcher = fswatch.Watcher(const.USB_MEDIA_MOUNT_POINT)
        self.watcher.start(USBFSHandler())


    def destroy(self):
        file_chooser_base.destroy(self)
        self.watcher.stop()


    def set_location(self, x, y):
        self.home_button.x = x + 45
        self.home_button.y = y
        self.eject_button.x = x + 160
        self.eject_button.y = y
        self.back_button.x = x
        self.back_button.y = y
        self.fixed.move(self.home_button, x + 45, y)
        self.fixed.move(self.eject_button, x + 160, y)
        self.fixed.move(self.back_button, x, y)

        self.clipboard_button.x = x
        x += self.clipboard_button.width + 5
        self.new_dir_button.x = x
        x += self.new_dir_button.width + 5
        self.rename_button.x = x
        x += self.rename_button.width + 5
        self.delete_button.x = x
        x += self.delete_button.width + 5

        self.clipboard_button.y = y + 345
        self.new_dir_button.y = y + 342
        self.rename_button.y = y + 342
        self.delete_button.y = y + 342

        self.fixed.move(self.clipboard_button, self.clipboard_button.x, self.clipboard_button.y)
        self.fixed.move(self.new_dir_button, self.new_dir_button.x, self.new_dir_button.y)
        self.fixed.move(self.rename_button, self.rename_button.x, self.rename_button.y)
        self.fixed.move(self.delete_button, self.delete_button.x, self.delete_button.y)

    # --------------------------
    # Callbacks
    # --------------------------

    def on_selection_changed(self, widget, data=None):
        selected_list = self.file_chooser.get_filenames()

        # enforce directory restriction
        current_folder = self.file_chooser.get_current_folder()
        if not current_folder.startswith(self.restricted_directory):
            self.error_handler.log('caught attempt to change outside restricted directory: %s' % current_folder)
            self.error_handler.log('forcing current directory to %s' % self.restricted_directory)
            self.file_chooser.set_current_folder(self.restricted_directory)
            return

        if len(selected_list) != 0:
            self.transfer_button.enable()
        else:
            self.transfer_button.disable()

        # preview
        if os.path.exists(self.selected_path):
            if is_plain_text_file(self, self.selected_path):
                # Then, load the preview and enable editing
                open_text_file(self, self.selected_path, self.preview_buffer, 10000)
            self.edit_gcode_button.disable()  # don't let them edit any files on the stick, they have to transfer it first
        else:
            self.preview_buffer.set_text('')
            self.edit_gcode_button.enable()  # they can start a new file this way

        # never load or edit USB selection
        self.conv_edit_button.disable()
        self.load_gcode_button.disable()

    def get_usb_disk_name(self):
        for item in os.listdir(self.restricted_directory):
            # no hidden folders
            if item[0] != '.':
                # if it's a directory, return the dir name
                if os.path.isdir(os.path.join(self.restricted_directory, item)):
                    # TODO - handle more than one mounted disk
                    return os.path.join(self.restricted_directory, item)
        # nothing mounted
        return ''

    def on_eject_button_release_event(self, widget, data=None):
        self.fixed.move(widget, widget.x, widget.y)
        # clear the liststore
        self.set_current_directory(self.restricted_directory)
        disk_name = self.get_usb_disk_name()
        if disk_name != '':
            # this will unmount without root privs
            self.error_handler.write("Unmounting filesystem: %s" % disk_name, const.ALARM_LEVEL_DEBUG)
            retcode = subprocess.call(['gvfs-mount', '-u', disk_name])
            if retcode != 0:
                self.error_handler.write("Error unmounting filesystem - gvfs-mount returned %d" % retcode, const.ALARM_LEVEL_DEBUG)

        self.mount_unmount_event_callback()


# software update picker

class update_filechooser_popup(popupdlg.popup):

    def __init__(self, parentwindow, block_previous_versions, filter = '*'):
        """
        Subclass of popup, this class returns an object that allows the user to choose an update package.  The popup consists of a
        file chooser with associated up and home buttons, as well as an update and cancel button.
        """
        popupdlg.popup.__init__(self, parentwindow,
                                'Choose update package and click Update.',
                                touchscreen_enabled=False, checkbox_enabled=False, entry_enabled=False)

        assert const.USB_MEDIA_MOUNT_POINT == const.SOFTWARE_UPDATE_BASE_PATH, "Need to override usb button release logic of file chooser component"

        self.block_previous_versions = block_previous_versions

        # create and add a file chooser fixed object to the popup dialog
        # must do this prior to calling _perform_layout() so that it gets taken into account.
        self.filechooser = popupdlg.file_chooser_fixed(home_button=False, usb_button=True, oldversion_button=True, newdir_button=False, file_filter=filter, min_width=int(1024/3))
        self._add_optional_fixed_child(self.filechooser)

        path = const.SOFTWARE_UPDATE_BASE_PATH
        self.filechooser.set_restricted_directory(path)

        # if only one directory present switch to it
        directory_entries = os.listdir(path)
        if len(directory_entries) == 1 and os.path.isdir(os.path.join(path, directory_entries[0])):
            self.filechooser.set_current_directory(os.path.join(path, directory_entries[0]))

        self.buttonlist = [self.cancel_button, self.update_button]

        # handle double clicks of files within the chooser
        self.filechooser.file_chooser.connect("file-activated", self._on_file_activated)

        connect_tooltip_signals(self.filechooser.oldversion_button)
        self.filechooser.oldversion_button.connect("button-release-event", self.on_oldversion_button_release_event)

        self._perform_layout()

    def get_filename_and_exit(self):
        name, ext = os.path.splitext(self.filechooser.selected_path)
        if const.PATHPILOT_UPDATE_EXTENSION in ext:
            self.response = gtk.RESPONSE_OK
            gtk.main_quit()
        else:
            with popupdlg.ok_cancel_popup(self.window, 'Update Error\n\nYou must select a valid update package file.  Update file must end with .%s extension.' % const.PATHPILOT_UPDATE_EXTENSION, cancel=False) as dlg:
                # show warning popup and then do nothing
                pass

    def _on_file_activated(self, widget, data=None):
        self.get_filename_and_exit()

    def on_update_button_release_event(self, widget, data=None):
        widget.unshift()
        self.get_filename_and_exit()

    def on_oldversion_button_release_event(self, widget, data=None):
        widget.unshift()
        # If we are a mill with an ATC that has ATCFIRMWARE_VERSION_SPECIALCASE, then that firmware is
        # incompatible with older versions of PathPilot for now.
        if self.block_previous_versions:
            with popupdlg.ok_cancel_popup(self.window, "The running ATC firmware version is incompatible with previous versions of PathPilot.", cancel=False, checkbox=False) as dlg:
                pass
        else:
            # change the area the chooser is pointing at to the $HOME/updates folder.
            self.filechooser.set_restricted_directory(const.SOFTWARE_UPDATES_ON_HD_PATH)
            self.filechooser.set_current_directory(const.SOFTWARE_UPDATES_ON_HD_PATH)

    def get_path(self):
        return self.filechooser.selected_path


class restore_filechooser_popup(popupdlg.popup):

    def __init__(self, parentwindow, path, filter = '*'):
        """
        Subclass of popup, this class returns an object that allows the user to choose a settings backup restore file.  The popup consists of a
        file chooser with associated up and home buttons, as well as an update and cancel button.
        """

        popupdlg.popup.__init__(self, parentwindow,
                                'Choose settings backup file to restore and click OK:',
                                touchscreen_enabled=False, checkbox_enabled=False, entry_enabled=False)

        # create and add a file chooser fixed object to the popup dialog
        # must do this prior to calling _perform_layout() so that it gets taken into account.
        self.filechooser = popupdlg.file_chooser_fixed(home_button=True, usb_button=True, oldversion_button=False, newdir_button=False, file_filter=filter)
        self._add_optional_fixed_child(self.filechooser)

        # 'path' points to gcode folder probably
        self.filechooser.set_restricted_directory(path)

        self.buttonlist = [self.cancel_button, self.ok_button]

        # if looking in USB_MEDIA_MOUNT_POINT and only one directory is there assume it's
        # the USB stick and change into it (difference with the way mount points for removable
        # media area handled with Mint 17.3)
        if path == const.USB_MEDIA_MOUNT_POINT:
            fsutil.adjust_media_directory_if_necessary(self.filechooser, path)

        # override ok button button release event
        self.ok_button.connect("button-release-event", self.on_ok_button_release_event)

        # this drives double clicks of a file in the chooser
        self.filechooser.file_chooser.connect("file-activated", self._on_file_activated)

        self._perform_layout()


    def _on_file_activated(self, widget, data=None):
        self.ok_button.emit("button-press-event", None)
        self.ok_button.emit("button-release-event", None)


    def on_ok_button_release_event(self, widget, data=None):
        widget.unshift()
        name, ext = os.path.splitext(self.filechooser.selected_path)
        if 'zip' in ext:
            self.response = gtk.RESPONSE_OK
            gtk.main_quit()
        else:
            with popupdlg.ok_cancel_popup(self.window, 'Settings Restore Error\n\nYou must select a valid settings backup file, which end with a .zip extension.', cancel=False) as dlg:
                #Show warning popup and then do nothing
                pass

    def get_path(self):
        return self.filechooser.selected_path


class file_open_popup(popupdlg.popup):
    def __init__(self, parentwindow, path, filter, popup_message = '', usb_button=False):
        popupdlg.popup.__init__(self, parentwindow,
                                popup_message,
                                touchscreen_enabled=False, checkbox_enabled=False, entry_enabled=False)

        self._set_entry_label_message("Name:")

        # create and add a file chooser fixed object to the popup dialog
        # must do this prior to calling _perform_layout() so that it gets taken into account.
        self.filechooser = popupdlg.file_chooser_fixed(home_button=True, usb_button=usb_button, oldversion_button=False, newdir_button=False, file_filter=filter)
        self._add_optional_fixed_child(self.filechooser)

        self.filechooser.set_restricted_directory(const.GCODE_BASE_PATH)
        self.filechooser.set_current_directory(os.path.dirname(path))

        self.buttonlist = [self.cancel_button, self.ok_button]

        # drives the double click of a file name
        self.filechooser.file_chooser.connect("file-activated", self._on_file_activated)
        self.filechooser.file_chooser.connect("selection-changed", self.on_selection_changed)

        self._perform_layout()


    def _on_file_activated(self, widget, data=None):
        # Enter key within the file chooser is same as clicking the ok button so drive
        # the same signals which shifts the button.
        self.ok_button.emit("button-press-event", None)
        self.ok_button.emit("button-release-event", None)


    def on_selection_changed(self, widget):
        name = self.filechooser.selected_path
        if name != '':
            self.ok_button.enable()
        else:
            self.ok_button.disable()


    def get_path(self):
        return self.filechooser.selected_path

    @property
    def current_directory(self):
        return self.filechooser.get_current_directory()


    def set_current_directory(self, dir):
        self.filechooser.set_current_directory(dir)



class file_save_as_popup(popupdlg.popup):

    def __init__(self, parentwindow, message, path, default_extension, touchscreen_enabled, usbbutton=False, closewithoutsavebutton=False):
        """
        Subclass of popup, this class returns an object that includes a file chooser display that allows the user to
        navigate through a directory before saving a file.  The current directory in the fileviewer is the one that
        is used when the file is named and saved.  The default file name is set when the path is past into the init fuction.
        TODO: This would be better done with a separate call (e.g. set_default_filename).
        It is currently only used on the conversational screen behind the "post to file" button.
        """

        popupdlg.popup.__init__(self, parentwindow,
                                message,
                                touchscreen_enabled=touchscreen_enabled, checkbox_enabled=False, entry_enabled=True)

        self.default_extension = default_extension

        # create and add a file chooser fixed object to the popup dialog
        # must do this prior to calling _perform_layout() so that it gets taken into account.
        self.filechooser = popupdlg.file_chooser_fixed(home_button=True, usb_button=usbbutton, oldversion_button=False, newdir_button=True)
        self._add_optional_fixed_child(self.filechooser)
        self._set_entry_label_message("Name:")

        dirname, filename = os.path.split(path)
        self.filechooser.set_entry_widget_for_selected_file(self.entry)
        self.filechooser.set_restricted_directory(const.GCODE_BASE_PATH)
        self.filechooser.set_current_directory(dirname)

        # set the entry to the filename default
        self.entry.set_text(filename)

        if touchscreen_enabled:
            # the soft keyboard takes a ton of vertical room so we need to shorten the
            # chooser to make room.
            w, h = self.filechooser.get_size_request()
            self.filechooser.set_size_request(w, 300)

        self.buttonlist = [self.cancel_button, self.save_button]

        # drives the double click of a file name
        self.filechooser.file_chooser.connect("file-activated", self._file_activated)

        if closewithoutsavebutton:
            # Add another option to get through the dialog successfully, but indicate that we don't want to save or cancel.
            self.close_without_save_button = btn.ImageButton('button_close_without_save.png', 'close-without-save-button')
            self.close_without_save_button.connect("button-release-event", self.on_close_without_save_release_event)
            self.buttonlist = [self.close_without_save_button, self.cancel_button, self.save_button]

        self._perform_layout()

    def _file_activated(self, widget, data=None):
        self.save_button.emit("button-press-event", None)
        self.save_button.emit("button-release-event", None)


    @property
    def current_directory(self):
        return self.filechooser.get_current_directory()


    def set_current_directory(self, dir):
        self.filechooser.set_current_directory(dir)


    def handle_enter_key(self):
        # need both as the press usually shifts the image and the release unshifts it and is dependent on shift being done once before)
        self.save_button.emit('button-press-event', None)
        self.save_button.emit('button-release-event', None)


    def on_save_button_release_event(self, widget, data=None):
        widget.unshift()
        name = self.entry.get_text()
        if len(name) > 0:
            self.filename = verify_file_extension(name, self.default_extension)
            self.path = os.path.join(self.filechooser.get_current_directory(), self.filename)
            self.response = gtk.RESPONSE_OK
            gtk.main_quit()


    def on_close_without_save_release_event(self, widget, data=None):
        self.response = gtk.RESPONSE_CLOSE
        self.filename = None
        self.path = None
        gtk.main_quit()



class append_to_file_popup(popupdlg.popup):
    def __init__(self, parentwindow, path):
        """
        Subclass of popup, this class returns an object that includes a file chooser display that allows the user to
        navigate through a directory before saving a file.  The current directory in the file chooser is the one that
        is used when the file is named and saved.  The default file name is set when the path is past into the init fuction.
        TODO: This would be better done with a separate call (e.g. set_default_filename).
        It is currently only used on the conversational screen behind the "post to file" button.
        """

        popupdlg.popup.__init__(self, parentwindow,
                                '',
                                touchscreen_enabled=False, checkbox_enabled=False, entry_enabled=False)

        # create and add a file chooser fixed object to the popup dialog
        # must do this prior to calling _perform_layout() so that it gets taken into account.
        self.filechooser = popupdlg.file_chooser_fixed(home_button=True, usb_button=False, oldversion_button=False, newdir_button=False)
        self._add_optional_fixed_child(self.filechooser)

        self.filechooser.set_restricted_directory(const.GCODE_BASE_PATH)
        self.filechooser.set_current_directory(os.path.dirname(path))

        self.buttonlist = [self.cancel_button, self.append_button]

        # drives the double click of a file name
        self.filechooser.file_chooser.connect("file-activated", self._on_file_activated)
        self.filechooser.file_chooser.connect("selection-changed", self.on_selection_changed)

        self._perform_layout()


    def _on_file_activated(self, widget, data=None):
        # Enter key within the file chooser is same as clicking the append button so drive
        # the same signals which shifts the button.
        self.append_button.emit("button-press-event", None)
        self.append_button.emit("button-release-event", None)


    def on_selection_changed(self, widget):
        name = self.filechooser.selected_path
        if name != '':
            self.append_button.enable()
        else:
            self.append_button.disable()

    def get_path(self):
        return self.filechooser.selected_path

    @property
    def current_directory(self):
        return self.filechooser.get_current_directory()

    def set_current_directory(self, dir):
        self.filechooser.set_current_directory(dir)

    def on_append_button_release_event(self, widget, data=None):
        widget.unshift()
        name = self.entry.get_text()
        self.filename = verify_file_extension(name, '.nc')
        self.path = os.path.join(os.path.split(self.path)[0], self.filename)
        self.response = gtk.RESPONSE_OK
        gtk.main_quit()

