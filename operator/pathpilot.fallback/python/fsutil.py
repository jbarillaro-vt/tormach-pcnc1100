# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import os
import stat
import string

import constants


def file_exists(path):
    if os.path.exists(path):
        try:
            if stat.S_ISREG(os.stat(path).st_mode):
                return True
        except OSError:
            pass
    return False


def dir_exists(path):
    if os.path.exists(path):
        try:
            if stat.S_ISDIR(os.stat(path).st_mode):
                return True
        except OSError:
            pass
    return False


def adjust_media_directory_if_necessary(filechooser, path):
    # if only one directory present switch to it
    directory_entries = os.listdir(path)

    # filter out files from the dir list
    # not sure this ever really happens, but just in case.
    for ix in reversed(xrange(len(directory_entries))):
        directory_entries[ix] = os.path.join(path, directory_entries[ix])
        if os.path.isfile(directory_entries[ix]):
            del directory_entries[ix]

    # automatically move down into the USB media's root dir
    if len(directory_entries) == 1 and os.path.isdir(directory_entries[0]):
        filechooser.set_current_directory(directory_entries[0])

        # the filechooser might be a few different objects - sort of ugly.
        # class file_choooser_base or the two derived hd and usb subclasses
        # file_chooser_fixed as used in popupdlg
        # only refresh free space in possible
        if hasattr(filechooser, 'refresh_free_space_label'):
            filechooser.refresh_free_space_label(directory_entries[0])

    return False  # Must return False as this is called from glib.idle_add() sometimes


def sanitize_path_for_user_display(path):
    '''
    This takes any path and examines it for the /home/operator/gcode stuff
    and removes that as necessary so that the returned path can be displayed to the user in
    a message and not cause confusion.
    '''
    sanitized_path = path
    ix = string.find(path, constants.GCODE_BASE_PATH)
    if ix != -1:
        sanitized_path = path[ix + len(constants.GCODE_BASE_PATH) + 1:]

    # for files on the USB drive, change the string to be more informative
    ix = string.find(path, constants.USB_MEDIA_MOUNT_POINT)
    if ix != -1:
        sanitized_path = 'USB Drive - ' + path[ix + len(constants.USB_MEDIA_MOUNT_POINT) + 1:]

    return sanitized_path

