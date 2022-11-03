#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import os
import sys
import subprocess
import inspect
import pygtk
pygtk.require("2.0")
import gtk
import gobject
import glib
import time
import versioning
import json
import re
from constants import *
import tormach_file_util
import singletons
import plexiglass
import shutil
import hashlib
import settings_backup
import errors

CHECK_UPDATE_URL_TEMPLATE="http://pathpilotapi.com/pp-v%d.%d.%d%s.json"
CHECK_UPDATE_FILENAME_TEMPLATE="pp-v%d.%d.%d%s.json"


class point():
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y

    def __str__(self):
        return "x %d y %d" % (self.x, self.y)

def get_xy_pos(widget):
    # returns a point object
    container = widget.get_parent()
    pt = point()
    pt.x = container.child_get_property(widget, "x")
    pt.y = container.child_get_property(widget, "y")
    return pt


class DownloadStatus():
    def __init__(self):
        self.result = None      # will become True or False when download is complete
        self.filepath = None
        self.size_kb = 0        # int
        self.percentdone = 0    # float


class SoftwareUpdateMgr():
    '''
    Manages everything related to checking online for available updates and downloading them.
    The manager is completely independent of any UI by design.
    Any persistent state related to online checking is also contained within the manager.
    '''

    UPDATE_AVAILABLE = 0
    UPDATE_NOTAVAILABLE = 1
    UPDATE_COMMERROR = 2
    UPDATE_SYSTEMERROR = 3


    def __init__(self, error_handler = None, redis = None):
        self.redis = redis
        self.error_handler = error_handler
        if self.error_handler == None:
            self.error_handler = errors.error_handler_base()
        self._dlprocess = None
        self.versionlist = [0, 0, 0]
        self.newestversionlist = [0, 0, 0]
        self._updatedata = None
        self._filepath = None
        self._updatecheck_result = self.UPDATE_NOTAVAILABLE

        if self.redis:
            if not self.redis.hexists('uistate', 'daily_online_updatecheck'):
                self.redis.hset('uistate', 'daily_online_updatecheck', 'True')

            if not self.redis.hexists('uistate', 'last_online_updatecheck'):
                self.redis.hset('uistate', 'last_online_updatecheck', 0)

            self.daily_online_updatecheck = (self.redis.hget('uistate', 'daily_online_updatecheck') == 'True')
            self.last_updatecheck_sec = float(self.redis.hget('uistate', 'last_online_updatecheck'))

        else:
            self.daily_online_updatecheck = False
            self.last_updatecheck_sec = 0.0


    def possible_update_check(self):
        # keep this very fast if there isn't anything to do as it gets called frequently
        # from the 0.5 second periodic function whenever the machine isn't busy running
        #  a program or moving around.
        if self.daily_online_updatecheck:
            now_sec = time.time()

            # has it been at least 24 hours since the last update check?
            timedelta_sec = now_sec - self.last_updatecheck_sec
            if timedelta_sec > (24 * 60 * 60):
                self.error_handler.log("Performing online update check - time since last check %f hours" % (timedelta_sec / (60.0 * 60.0)))
                self._updatedata = None   # clear out any previously cached update check results
                if self.checkonline_for_update() == self.UPDATE_AVAILABLE:
                    msg = 'A newer PathPilot v%d.%d.%d is now available.  Click the Update button for more details.' % (self.newestversionlist[0], self.newestversionlist[1], self.newestversionlist[2])
                    self.error_handler.write(msg, ALARM_LEVEL_LOW)

                if self.redis:
                    self.redis.hset('uistate', 'last_online_updatecheck', now_sec)
                    self.last_updatecheck_sec = float(self.redis.hget('uistate', 'last_online_updatecheck'))


    def _parse_updatejson_file(self, filepath):
        # read contents of the version specific json file for update info
        result = True
        try:
            jsonfile = open(filepath, 'r')
        except IOError:
            # file not present or unreadable
            result = False

        if result:
            try:
                self._updatedata = json.load(jsonfile)
                if self._updatedata["fileVersion"] in [1, 2]:
                    self.error_handler.log("Received successful json data from online update check.")

                else:
                    self.error_handler.log("Unexpected update json file version %d" % (self._updatedata["fileVersion"]))
                    self._updatedata = None
                    result = False

            except:
                self.error_handler.log("Corrupted update json file (syntax broken - missing quotes or commas? missing or mis-spelled keys?)")
                result = False

            finally:
                jsonfile.close()

        return result


    def checkonline_for_update(self, plexiglass_dialog_target=None):
        '''
        Checks online for an update package.
        Returns cached results from the last update if available.
        Return codes:
            UPDATE_AVAILABLE = checked with server and update is available
            UPDATE_NOTAVAILABLE = checked with server and update not available
            UPDATE_COMMERROR = signals user that some network troubleshooting may fix the issue
            UPDATE_SYSTEMERROR = not a user fixable problem
        '''

        # return results from last cached update check if available
        if self._updatedata is None:

            # if the machine is networked, but it cannot resolve pathpilotapi.com, wget can
            # block for many seconds and things feel hung, hence the need for plexy vs.
            # additional complexity of threads or async breakup.
            plexifull = False
            if not plexiglass_dialog_target:
                plexifull = True
                plexiglass_dialog_target = singletons.g_Machine.window

            with plexiglass.PlexiglassInstance(plexiglass_dialog_target, full_screen=plexifull) as p:

                self._updatecheck_result = self.UPDATE_NOTAVAILABLE
                self.versionlist = versioning.GetVersionMgr().get_version_list()

                # create the version specific URL
                url = CHECK_UPDATE_URL_TEMPLATE % (self.versionlist[0], self.versionlist[1], self.versionlist[2], self.versionlist[3])
                filename = CHECK_UPDATE_FILENAME_TEMPLATE % (self.versionlist[0], self.versionlist[1], self.versionlist[2], self.versionlist[3])

                # make sure dir exists
                try:
                    os.makedirs(SOFTWARE_UPDATE_CHECK_PATH)
                except OSError:
                    pass

                # remove any leftover file from last version check so that wget downloads a fresh one
                filepath = os.path.join(SOFTWARE_UPDATE_CHECK_PATH, filename)
                try:
                    os.remove(filepath)
                except:
                    pass

                cmd = "wget --no-verbose --progress=dot --directory-prefix=%s %s" % (SOFTWARE_UPDATE_CHECK_PATH, url)
                self.error_handler.log(cmd)
                result = subprocess.call(cmd, shell=True)

                # TODO does wget respect system configured proxies?  ugh.
                # 0 is good
                # 4 is network failure
                # 6 is authenticaion failure
                # 8 is server error (http 404 or other)

                if result == 0:
                    # read the json file to figure out what update is appropriate for us
                    success = self._parse_updatejson_file(filepath)
                    if success:
                        self.newestversionlist = versioning.GetVersionMgr().parse_legacy_version_string(self._updatedata["newestVersion"])
                        self.error_handler.log("Current version = {}".format(self.versionlist))
                        if self._updatedata["fileVersion"] == 1:
                            self.error_handler.log("Newest available version = {}".format(self.newestversionlist))
                        else:
                            self.error_handler.log("Newest available version = %s %s %d" % (self.newestversionlist, self._updatedata["newestVersionStatus"], self._updatedata["newestVersionBuild"]))

                        # when comparing for "newer" we initially ignore any version suffix and just look at the marketing driven 'a.b.c' numbers.
                        if self.versionlist[0] < self.newestversionlist[0] or self.versionlist[1] < self.newestversionlist[1] or self.versionlist[2] < self.newestversionlist[2]:
                            # The newest version available is newer than we are!
                            self.error_handler.log("Available version is newer than we are so offering update to the user")
                            self._updatecheck_result = self.UPDATE_AVAILABLE

                        elif self._updatedata["fileVersion"] == 2 and self.versionlist[0] == self.newestversionlist[0] and self.versionlist[1] == self.newestversionlist[1] and self.versionlist[2] == self.newestversionlist[2]:
                            # fileVersion 2 added the status and build json fields which mirror the version.json fields of the same name.
                            # 'a.b.c' numbers are exactly the same.
                            # now let's check build 'status' and internal build number.

                            if versioning.GetVersionMgr().get_status() != self._updatedata["newestVersionStatus"]:
                                # this means we are both the same a.b.c, but we are being offered a different type of build/status (final release, BETA, ALPHA, etc.).
                                # typical case is moving from a.b.c-BETA-nn to a.b.c
                                # offer this update to the user regardless of internal build number
                                self.error_handler.log("Available version is newer than we are so offering update to the user")
                                self._updatecheck_result = self.UPDATE_AVAILABLE
                            else:
                                # this means we are both the same a.b.c and status (BETA, DEV, ALPHA)
                                # now compare internal build numbers
                                if versioning.GetVersionMgr().get_internal_build_number() < self._updatedata["newestVersionBuild"]:
                                    self.error_handler.log("Available version is newer than we are so offering update to the user")
                                    self._updatecheck_result = self.UPDATE_AVAILABLE
                                else:
                                    self.error_handler.log("Available version is not any newer than we are so we're done.")
                                    self._updatecheck_result = self.UPDATE_NOTAVAILABLE
                        else:
                            self.error_handler.log("Available version is not any newer than we are so we're done.")
                            self._updatecheck_result = self.UPDATE_NOTAVAILABLE
                    else:
                        self.error_handler.log("Error parsing update json file")
                        self._updatecheck_result = self.UPDATE_SYSTEMERROR

                elif result == 4:
                    self.error_handler.log("Network failure trying to check for update.")
                    self._updatecheck_result = self.UPDATE_COMMERROR

                elif result == 8:
                    # Hard to get exact http status code from wget without tons of extra work processing the stderr
                    # output and the user can't do anything about it anyway.
                    # Just assume its a 404 for missing resource and call that no update available.
                    self.error_handler.log("Server error trying to check for update. Most likely just a 404 as the file doesn't exist yet.")
                    self._updatecheck_result = self.UPDATE_NOTAVAILABLE

                else:
                    self.error_handler.log("Error from wget trying to check for update - return code was %d" % result)
                    self._updatecheck_result = self.UPDATE_SYSTEMERROR

        return self._updatecheck_result


    def start_update_download(self):
        assert self._dlprocess is None

        url = self._updatedata["newestVersionUrl"]

        # make sure ~/updates exists
        try:
            os.makedirs(SOFTWARE_UPDATES_ON_HD_PATH)
        except OSError:
            # ignore the exception if it already exists
            pass

        # remove any leftover file so that wget downloads a fresh one
        filename = self._updatedata["newestVersionFilename"]
        self._filepath = os.path.join(SOFTWARE_UPDATES_ON_HD_PATH, filename)
        try:
            os.remove(self._filepath)
        except:
            pass

        cmd = "wget --progress=dot --directory-prefix=%s %s" % (SOFTWARE_UPDATES_ON_HD_PATH, url)
        self.error_handler.log(cmd)
        self._dlprocess = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=True)


    def poll_download_status(self):
        assert self._dlprocess != None

        status = DownloadStatus()

        # check if async work is done, but don't block waiting for it
        if self._dlprocess.poll() != None:
            if self._dlprocess.returncode == 0:
                status.result = True
                status.filepath = self._filepath
            else:
                status.result = False
        else:
            status.result = None   # signals in progress still

            # pull on dlprocess.stdout and parse for dots
            line = self._dlprocess.stderr.readline().strip()

            # amongst other status lines, the ones we really care about look like this:
            # 15850K .......... .......... .......... .......... .......... 97% 6.40M 0s

            matchlist = re.findall(r'(\d+)K[ \.]+(\d+)\%', line)
            if len(matchlist) == 1 and len(matchlist[0]) == 2:
                # Bingo - we got status.
                status.percentdone = float(matchlist[0][1]) / 100.0
                status.size_kb = int(matchlist[0][0])

        return status


    def set_daily_updatecheck(self, enabled):
        if self.redis:
            if enabled:
                self.redis.hset('uistate', 'daily_online_updatecheck', 'True')
            else:
                self.redis.hset('uistate', 'daily_online_updatecheck', 'False')

            self.daily_online_updatecheck = (self.redis.hget('uistate', 'daily_online_updatecheck') == 'True')
        else:
            self.daily_online_updatecheck = enabled


    def is_daily_updatecheck_enabled(self):
        if self.redis:
            return (self.redis.hget('uistate', 'daily_online_updatecheck') == 'True')
        else:
            return self.daily_online_updatecheck


    def get_update_description(self):
        return self._updatedata["description"]


    def display_update_dialog(self, parent, block_previous_versions, touchscreen_enabled, netbios_name = ""):
        '''
        Returns True if a software update was put in place.
                False otherwise.
        '''

        # netbios_name is appended to the automatic settings backup file name to make it more unique.
        # that way you can take a single USB drive and run around an entire classroom of machines and end up with proper settings backups
        # for each vs. having each one overwrite the last.

        # make sure ~/updates exists
        try:
            os.makedirs(SOFTWARE_UPDATES_ON_HD_PATH)
        except OSError:
            # ignore the exception if it already exists
            pass

        dlg = SoftwareUpdateDialog(self, parent, block_previous_versions, touchscreen_enabled)
        gtk.main()
        dlg.destroy()
        # pump the GTK event loop for awhile to make sure message dialog is fully removed from screen
        # vs. a ghost
        while gtk.events_pending():
            gtk.main_iteration(False)

        if dlg.update_filepath != None:
            path = dlg.update_filepath

            # TODO if it was an online download than try to put the settings
            # backup on a stick or the gcode folder

            # before we do anything, we automatically do an 'admin settings backup' to the USB stick since
            # we KNOW it exists...and we put the backup file right alongside where the .tgp file is.
            sb = settings_backup.settings_backup(self.error_handler)
            sb.perform_automatic_settings_backup(netbios_name, os.path.dirname(dlg.update_filepath), parent, touchscreen_enabled)

            # copy file to ~/updates directory
            destination = os.path.join(SOFTWARE_UPDATES_ON_HD_PATH, dlg.update_filename)

            # if we downloaded the update file, it already exists so no need to copy it from the usb stick.
            if not os.path.exists(destination):
                # This can take a long time so toss up the plexiglass
                with plexiglass.PlexiglassInstance(parent) as p:
                    try:
                        self.error_handler.write('copying %s to %s' % (path, destination), ALARM_LEVEL_DEBUG)
                        shutil.copy2(path, destination)
                        tormach_file_util.filesystem_sync(self.error_handler)
                    except Exception as e:
                        msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                        self.error_handler.write('copying software update file raised exception: %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)

                    # verify update file copied correctly
                    # there have been odd update failures later traced to defective USB
                    # cables and defective USB sticks
                    self.error_handler.write('source md5sum: %s' % path, ALARM_LEVEL_DEBUG)
                    with open(path, 'rb') as file_to_read:
                        file_data = file_to_read.read()
                        src_md5 = hashlib.md5(file_data).hexdigest()
                        self.error_handler.write("%s md5sum: %s" % (path, src_md5), ALARM_LEVEL_DEBUG)

                    self.error_handler.write('destination md5sum: %s' % destination, ALARM_LEVEL_DEBUG)

                    with open(destination, 'rb') as file_to_read:
                        file_data = file_to_read.read()
                        dst_md5 = hashlib.md5(file_data).hexdigest()
                        self.error_handler.write("%s md5sum: %s" % (destination, dst_md5), ALARM_LEVEL_DEBUG)

                    if src_md5 != dst_md5:
                        self.error_handler.write("Checksum mismatch after copying update file: %s" % path, ALARM_LEVEL_LOW)
                        return

            # write path to ~/update_file.txt
            # then shutdown the UI and LCNC
            #FIXME: potential exceptions here
            with open(UPDATE_PTR_FILE, "w") as text_file:
                text_file.write(destination)

            self.error_handler.log("Created {} that contains {}".format(UPDATE_PTR_FILE, destination))
            return True

        return False


class SoftwareUpdateDialog():

    def __init__(self, software_update_mgr, parent, block_previous_versions, touchscreen_enabled):
        self.quit_request = False

        self.mgr = software_update_mgr

        self.block_previous_versions = block_previous_versions

        self._touchscreen_enabled = touchscreen_enabled

        # this is the directory where this module code is running from
        self.program_dir = os.path.dirname(os.path.abspath(inspect.getsourcefile(self.__class__)))

        # look for the .glade file and the images here:
        self.GLADE_DIR = os.path.join(self.program_dir, 'images')

        # glade setup
        builder = gtk.Builder()

        gladefile_list = ['swupdate.glade']
        for item in gladefile_list:
            item = os.path.join(self.GLADE_DIR, item)
            if builder.add_from_file(item) == 0:
                raise RuntimeError("GtkBuilder failed")

        missingSignals = builder.connect_signals(self)
        if missingSignals is not None:
            raise RuntimeError("Cannot connect signals: ", missingSignals)

        self.dlg = builder.get_object("main_dialog")
        self.dlg.set_type_hint(gtk.gdk.WINDOW_TYPE_HINT_DIALOG)
        self.dlg.set_transient_for(parent)
        self.dlg.set_destroy_with_parent(True)
        self.dlg.set_modal(True)

        self.periodic_checkbox = builder.get_object("periodic_checkbox")
        self.periodic_checkbox.set_active(self.mgr.is_daily_updatecheck_enabled())

        self.checkonline_button = builder.get_object("checkonline_button")

        self.install_button = builder.get_object("install_button")
        self.description_textview = builder.get_object("description_textview")
        self.label1 = builder.get_object("label1")
        self.label2 = builder.get_object("label2")
        self.browse_button = builder.get_object("browse_button")

        self.main_fixed = builder.get_object("main_fixed")

        if self.mgr.is_daily_updatecheck_enabled() and self.mgr.checkonline_for_update() == SoftwareUpdateMgr.UPDATE_AVAILABLE:
            # display the concise description of the update
            textbuffer = self.description_textview.get_buffer()
            start_iter = textbuffer.get_start_iter()
            end_iter = textbuffer.get_end_iter()
            # clear out the text buffer before inserting our new description
            textbuffer.delete(start_iter, end_iter)
            textbuffer.insert(start_iter, self.mgr.get_update_description())
        else:
            # no cached update available or we aren't enabled to automatically check
            # for updates so wait for the user action to kick one off
            pt = get_xy_pos(self.periodic_checkbox)
            self.main_fixed.move(self.periodic_checkbox, pt.x, pt.y - 125)
            pt = get_xy_pos(self.label2)
            self.main_fixed.move(self.label2, pt.x, pt.y - 125)
            pt = get_xy_pos(self.browse_button)
            self.main_fixed.move(self.browse_button, pt.x, pt.y - 125)
            self.install_button.hide()
            self.description_textview.hide()

        self.dlg.connect("delete-event", gtk.main_quit)
        self.dlg.show()

        self.download_status = None
        self.update_filepath = None
        self.update_filename = None


    def show_update_available(self):
        if not self.install_button.get_visible():
            pt = get_xy_pos(self.periodic_checkbox)
            self.main_fixed.move(self.periodic_checkbox, pt.x, pt.y + 125)
            pt = get_xy_pos(self.label2)
            self.main_fixed.move(self.label2, pt.x, pt.y + 125)
            pt = get_xy_pos(self.browse_button)
            self.main_fixed.move(self.browse_button, pt.x, pt.y + 125)

            self.install_button.show()
            self.install_button.set_sensitive(True)

            self.description_textview.show()


    def on_periodic_checkbox_toggled(self, widget, data=None):
        daily_update_check = widget.get_active()
        self.mgr.set_daily_updatecheck(daily_update_check)
        if daily_update_check:
            self.mgr.error_handler.log("Daily online checking enabled")
        else:
            self.mgr.error_handler.log("Daily online checking disabled")


    def on_checkonline_button_released(self, widget, data=None):
        self.checkonline_button.set_sensitive(False)

        result = self.mgr.checkonline_for_update(self.dlg)
        if result == SoftwareUpdateMgr.UPDATE_AVAILABLE:
            # display the concise description of the update
            textbuffer = self.description_textview.get_buffer()
            start_iter = textbuffer.get_start_iter()
            end_iter = textbuffer.get_end_iter()
            # clear out the text buffer before inserting our new description
            textbuffer.delete(start_iter, end_iter)
            textbuffer.insert(start_iter, self.mgr.get_update_description())

            # grow the dialog
            self.show_update_available()

        elif result == SoftwareUpdateMgr.UPDATE_NOTAVAILABLE:
            self.label1.set_text("No newer version available.")

        elif result == SoftwareUpdateMgr.UPDATE_COMMERROR:
            self.label1.set_text("Could not communicate with update server, check internet configuration.")

        else:
            self.label1.set_text("An error occurred during the update check.")

        self.checkonline_button.set_sensitive(True)


    def _modal_check_for_final_result(self, mgr, progressbar):

        self.download_status = self.mgr.poll_download_status()

        if self.download_status.result != None:
            gtk.main_quit()
            return False  # signal caller we're done and go ahead and remove idle callback

        self.mgr.error_handler.log("Percent downloaded = %f" % self.download_status.percentdone)
        progressbar.set_fraction(self.download_status.percentdone)
        progressbar.set_text("%d K" % self.download_status.size_kb)

        return True   # keep calling us on idle


    def _ignore_delete_event(self, widget, data):
        return True


    def on_install_button_released(self, widget, data=None):

        md = gtk.MessageDialog(self.dlg,
                               gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                               gtk.MESSAGE_INFO,
                               gtk.BUTTONS_NONE,
                               "Downloading...")

        self.mgr.start_update_download()

        # Having no buttons causes focus to become label which appears with all its text selected
        # (look strange)
        vbox = md.get_message_area()
        children = vbox.get_children()
        for label in children:
            label.set_selectable(False)

        progressbar = gtk.ProgressBar()
        progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        vbox.add(progressbar)

        # snag the delete-event so that we ignore it
        md.connect("delete-event", self._ignore_delete_event)

        glib.idle_add(self._modal_check_for_final_result, self.mgr, progressbar)
        md.show_all()
        gtk.main()
        md.destroy()

        # the idle handler signals to quit the GTK loop and sets the status
        assert self.download_status != None

        if self.download_status.result:
            # Now we're ready to install the new tarball
            md = gtk.MessageDialog(self.dlg,
                                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_INFO,
                                   gtk.BUTTONS_OK,
                                   "Update downloaded successfully.  Click OK to install.")
            md.show_all()
            md.run()
            md.destroy()
            # pump the GTK event loop for awhile to make sure message dialog is fully removed from screen
            # vs. a ghost
            while gtk.events_pending():
                gtk.main_iteration(False)

            self.update_filepath = self.download_status.filepath
            path, self.update_filename = os.path.split(self.update_filepath)

        else:
            # The download of the new tarball failed for some reason.
            md = gtk.MessageDialog(self.dlg,
                                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_ERROR,
                                   gtk.BUTTONS_OK,
                                   "The update could not be downloaded.\n\nTry again later or visit www.tormach.com to download the file yourself and update by USB drive.")
            md.run()
            md.destroy()
            # pump the GTK event loop for awhile to make sure message dialog is fully removed from screen
            # vs. a ghost
            while gtk.events_pending():
                gtk.main_iteration(False)

        gtk.main_quit()


    def on_browse_button_released(self, widget, data=None):
        update_wildcard = '*.' + PATHPILOT_UPDATE_EXTENSION

        with tormach_file_util.update_filechooser_popup(self.dlg, self.block_previous_versions, update_wildcard) as dialog:
            if dialog.response != gtk.RESPONSE_OK:
                return

            # Extract dialog information for later use
            self.update_filepath = dialog.get_path()
            path, self.update_filename = os.path.split(self.update_filepath)
            target = os.path.join(SOFTWARE_UPDATES_ON_HD_PATH, self.update_filename)

            # If user chose a previous version that is already in the updates directory, then don't do anything
            # special.
            if self.update_filepath != target:
                # Otherwise make sure to delete the target file so that a fresh one gets copied off the USB stick.
                # File name could be the same, but contents might be different and don't want to depend on
                # last modified times as clocks might be off.
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except OSError:
                        pass

            gtk.main_quit()


    def on_close_button_released(self, widget, data=None):
        gtk.main_quit()


    def destroy(self):
        self.dlg.destroy()


def _nop_callback():
    pass


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    # Direct invocation is usually because of pathpilotmgr running us because
    # either something died horribly unexpectedly or the test build expired.
    print "swupdate module running standalone."

    # There is no machine control going on during config chooser so just give the plexiglass something
    # to call that has no effect when it needs to make sure that all jogging has stopped.
    plexiglass.PlexiglassInitialize(_nop_callback)

    win = gtk.Window(gtk.WINDOW_TOPLEVEL)
    fixed = gtk.Fixed()
    background = gtk.Image()
    background.set_from_file(os.path.join(GLADE_DIR, 'Tormach-Wallpaper.png'))
    fixed.put(background, 0, 0)
    fixed.set_size_request(1024, 768)
    win.add(fixed)
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_position(gtk.WIN_POS_CENTER)
    win.show_all()

    # Show the software update dialog and just assume we have a touchscreen so they can have
    # the extra popups just in case.
    update_mgr = SoftwareUpdateMgr()
    if update_mgr.display_update_dialog(parent=win, block_previous_versions=False, touchscreen_enabled=True):
        # They put a build in place so do not run PP and instead try to use the new build.
        print "swupdate put a build in place."
        sys.exit(1)

    sys.exit(0)
