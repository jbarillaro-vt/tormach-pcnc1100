#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import os
import sys
import zipfile
import zlib
import time
import fsutil
import tormach_file_util
import plexiglass
import errors
import gtk
from constants import *
import errors
import btn
import popupdlg
import glob

# this utility walks the list of files and directories and puts
# them in a zip file in the GCODE_BASE_PATH directory

class settings_backup():

    def __init__(self, error_handler):
        self.error_handler = error_handler
        self.standalone = False
        self.compression = zipfile.ZIP_DEFLATED
        self.error_msg = ''

        if 'GCODE_BASE_PATH' in globals():
            self.base_path = GCODE_BASE_PATH
        else:
            # base path to user's gcode file on disk
            self.error_handler.log('GCODE_BASE_PATH not defined. Assuming $HOME/gcode')
            self.base_path = os.path.join(os.getenv('HOME'), 'gcode')

        self.zip_name = ''
        try:
            # list of files and directories to backup
            import backup_file_list
        except:
            self.error_msg = 'failed to find backup list: backup_file_list.py'
            self.error_handler.log(self.error_msg)

        self.zip_name = backup_file_list.file_name
        file_list = backup_file_list.file_list
        self.dir_list = backup_file_list.dir_list

        # the file list can contain shell wild cards so we need to evaluate them
        expanded_file_list = []
        for item in file_list:
            pattern = os.path.join(os.environ['HOME'], item)
            itemlist = glob.glob(pattern)
            for ix in itemlist:
                if os.path.isfile(ix):
                    expanded_file_list.append(ix)

        self.file_list = expanded_file_list

    def get_error_message(self):
        return self.error_msg

    def get_backup_filename(self):
        return self.zip_name

    def set_backup_filename(self, new_name):
        self.zip_name = new_name

    def add_files(self, zf, file_list, dir_path=''):
        for f in file_list:
            try:
                if f[0] == os.sep:
                    f_path = f   # already a full path
                    f = f_path.replace(os.environ['HOME'] + os.sep, '')
                else:
                    f_path = os.path.join(os.environ['HOME'], dir_path, f)
                self.error_handler.log("        " + os.path.join(dir_path, f))
                zf.write(f_path, arcname=os.path.join(dir_path, f), compress_type=self.compression)
            except Exception, e:
                self.error_msg = "error '%s' adding file to backup" % str(e)
                self.error_handler.log(self.error_msg)
                # continue on adding remaining files

    def backup_files(self):
        self.error_handler.log('-------Backing up PathPilot files: {}'.format(self.zip_name))
        if self.zip_name == '':
            self.error_msg = "backup filename not set"
            self.error_handler.log(self.error_msg)
            return 1

        # must delete .zip file in order to overwrite files already in it
        try:
            os.remove(self.zip_name)
        except OSError:
            pass

        zf = zipfile.ZipFile(self.zip_name, mode='w')

        self.error_handler.log('Files:')
        self.add_files(zf, self.file_list)

        self.error_handler.log('Directories:')
        for d in self.dir_list:
            self.error_handler.log('        Storing directory: ' + d)
            d_path = os.path.join(os.environ['HOME'], d)

            # don't assume it exists - the user may have accidentally or purposely deleted it.
            if os.path.isdir(d_path):
                # make a list of all files in this directory
                d_file_list = [ f for f in os.listdir(d_path) if os.path.isfile(os.path.join(d_path, f)) ]
                if len(d_file_list) != 0:
                    self.add_files(zf, d_file_list, d)

        zf.close()
        self.error_handler.log('-------Backup complete')
        return 0


    def perform_automatic_settings_backup(self, netbios_name, existing_dir, parent, touchscreen_enabled):
        # insert a YYYY-jan-08 type of date into the filename
        # the netbios name is used in the file name to make it more unique and meaningful.
        # that way you can take a single USB drive and run around an entire classroom of machines for updating and end up with proper settings backups
        # for each on the one stick vs. having each one overwrite the last.
        if len(netbios_name) > 0 and netbios_name != 'TORMACHPCNC':
            suffix = '-{}-{}'.format(netbios_name, time.strftime('%Y-%b-%d', time.localtime()))
        else:
            suffix = '-{}'.format(time.strftime('%Y-%b-%d', time.localtime()))

        fileroot, ext = os.path.splitext(os.path.basename(self.get_backup_filename()))
        path = os.path.join(existing_dir, fileroot + suffix + ext)

        # check to see if we're going to overwrite an existing file
        if os.path.exists(path):
            with popupdlg.confirm_file_overwrite_popup(parent, path, touchscreen_enabled) as popup:
                response = popup.response
                if response != gtk.RESPONSE_OK:
                    return
                path = popup.path

        self.set_backup_filename(path)

        # This can take a long time so toss up the plexiglass
        validfile = False
        with plexiglass.PlexiglassInstance(parent) as p:
            if self.backup_files():
                # error of some sort
                self.error_handler.write("%s" % self.get_error_message())

            tormach_file_util.filesystem_sync(self.error_handler)

            # now go back and test that it got created correctly
            validfile = self.verify_settings_zipfile()

        if not validfile:
            path,name = os.path.split(self.zip_name)
            with popupdlg.ok_cancel_popup(parent, 'Settings backup file is corrupt:\n%s\n\nSwitch to a different USB drive and try again.' % name,
                                          cancel=False, checkbox=False) as dialog:
                pass


    def perform_settings_backup(self, parent, touchscreen_enabled):
        path = os.path.join(GCODE_BASE_PATH, os.path.basename(self.get_backup_filename()))

        with tormach_file_util.file_save_as_popup(parent, 'Choose a name for the settings zip file.',
                                                  path, '.zip', touchscreen_enabled,
                                                  usbbutton=True, closewithoutsavebutton=False) as dialog:
            # Get information from dialog popup
            response = dialog.response
            path = dialog.path

        if response != gtk.RESPONSE_OK:
            return

        # we FORCE a .zip extension if the user didn't
        if os.path.splitext(path)[1].upper() != ".ZIP":
            path = path + ".zip"

        # check to see if we're going to overwrite an existing file
        if os.path.exists(path):
            with popupdlg.confirm_file_overwrite_popup(parent, path, touchscreen_enabled) as popup:
                response = popup.response
                if response != gtk.RESPONSE_OK:
                    return
                path = popup.path

        self.set_backup_filename(path)

        # This can take a long time so toss up the plexiglass
        validfile = False
        with plexiglass.PlexiglassInstance(parent) as p:
            if self.backup_files():
                # error of some sort
                self.error_handler.write("%s" % self.get_error_message())

            tormach_file_util.filesystem_sync(self.error_handler)

            # now go back and test that it got created correctly
            validfile = self.verify_settings_zipfile()

        if not validfile:
            path,name = os.path.split(self.zip_name)
            with popupdlg.ok_cancel_popup(parent, 'Settings backup file is corrupt:\n%s\n\nSwitch to a different USB drive and try again.' % name, cancel=False, checkbox=False) as dialog:
                pass

        # do a little dance, celebrate.
        sanitized_path = fsutil.sanitize_path_for_user_display(path)
        self.error_handler.write("Settings backed up successfully to file: {}".format(sanitized_path), ALARM_LEVEL_LOW)


    def verify_settings_zipfile(self):
        # flush and free all file system cache so that the test zip below is really reading the bits
        # from the media (typically a USB flash drive).
        tormach_file_util.filesystem_dump_caches(self.error_handler)

        validfile = False
        try:
            if zipfile.is_zipfile(self.zip_name):
                # now test it more throughly
                zip = zipfile.ZipFile(self.zip_name)
                validfile = (zip.testzip() == None)
                zip.close()
        except:
            validfile = False
        return validfile


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    error_handler = errors.error_handler_base()
    sb = settings_backup(error_handler)
    sb.standalone = True

    # See if we have a version cutoff argument. If a version is listed,
    # then we only do the backup if the version is less than v1.9.11
    targetdir = os.path.join(os.environ['HOME'], 'gcode')   # default standalone backup location
    backup_needed = True

    for arg in sys.argv[1:]:
        if arg.startswith("v"):
            # check the version - we only need to do this if the version is less than v1.9.11
            # because v1.9.11 does automatic settings backup within the app as part
            # of the software update process
            arg = arg[1:]  # slice off the v
            vernumbers = arg.split('.')   # a.b.c
            if int(vernumbers[0]) > 1 or int(vernumbers[1]) > 9 or int(vernumbers[2]) > 10:
                error_handler.log("Skipping settings backup because current version is %s which is newer than v1.9.10" % arg)
                backup_needed = False

        elif arg.startswith(os.sep) and os.path.exists(arg):
            # caller gave us a full path as an argument. They want to use that as the targetdir.
            targetdir = arg

    if backup_needed:
        if "usb" in sys.argv[1:]:
            # caller wants us to put the backup file on the mounted usb stick
            # if looking in /media and only one directory is there assume it's
            # the USB stick and change to it (and hope they don't have more than one)
            directory_entries = os.listdir(USB_MEDIA_MOUNT_POINT)
            if len(directory_entries) == 1 and os.path.isdir(os.path.join(USB_MEDIA_MOUNT_POINT, directory_entries[0])):
                targetdir = os.path.join(USB_MEDIA_MOUNT_POINT, directory_entries[0])

        # insert a YYYY-jan-08 type of date into the filename
        suffix = time.strftime('-%Y-%b-%d', time.localtime())
        fileroot, ext = os.path.splitext(os.path.basename(sb.get_backup_filename()))
        path = os.path.join(targetdir, fileroot + suffix + ext)
        sb.set_backup_filename(path)

        validfile = False
        if sb.backup_files():
            # error of some sort
            error_handler.log(sb.get_error_message())

        tormach_file_util.filesystem_sync(error_handler)

        # now go back and test that it got created correctly
        validfile = sb.verify_settings_zipfile()
        if validfile:
            print "Settings backup file %s verified successfully!" % sb.zip_name
        else:
            path,name = os.path.split(sb.zip_name)
            with popupdlg.ok_cancel_popup(None, 'Settings backup file is corrupt:\n%s\n\nSwitch to a different USB drive and try again.' % name,
                                          cancel=False, checkbox=False) as dialog:
                pass
            sys.exit(1)

    sys.exit(0)
