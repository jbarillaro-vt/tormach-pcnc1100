#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import os
import stat
import subprocess
import inspect
import string

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import glib
import time
import sys
import plexiglass
import constants
import traceback
import timer
import shutil


# this is the directory where this module code is running from
program_dir = os.path.dirname(os.path.abspath(__file__))

# look for the .glade file and the images here:
GLADE_DIR = os.path.join(program_dir, 'images')


def builder_factory(obj):
    # glade setup
    builder = gtk.Builder()
    gladefile = 'dropbox_helper.glade'
    gladefile = os.path.join(GLADE_DIR, gladefile)
    if builder.add_from_file(gladefile) == 0:
        raise RuntimeError("GtkBuilder failed")

    missingSignals = builder.connect_signals(obj)
    if missingSignals is not None:
        raise RuntimeError("Cannot connect signals: ", missingSignals)

    return builder


class DBConfig():

    def __init__(self):
        self.builder = builder_factory(self)

        self.dbcmdtemplate = os.path.join(os.environ['HOME'], 'dropbox.py %s')

        self.dlg = self.builder.get_object("main_dialog")
        self.instructions_label = self.builder.get_object("instructions_label")

        self.status_textview = self.builder.get_object("status_textview")
        self.status_buffer = gtk.TextBuffer()
        self.status_textview.set_buffer(self.status_buffer)

        # Re-use the same close button signal to trigger exiting...
        self.dlg.connect("delete-event", self.on_close_button_released)

        dropbox_py = os.path.join(os.environ['HOME'], 'dropbox.py')
        self.dropbox_installed = (os.path.isfile(dropbox_py) and os.access(dropbox_py, os.X_OK))
        if self.dropbox_installed:
            try:
                # Do this so that dropbox.py stdout output for excluded directory lists make sense and
                # don't show up as "../../Dropbox/foobar"
                os.chdir(os.path.join(os.environ['HOME'], 'Dropbox'))
            except:
                pass

            result = self._dbcmd("status")
            self.status_buffer.set_text("Dropbox installed.\n\n" + result)

        else:
            self.status_buffer.set_text("Dropbox not installed.")

        self._update_button_sensitivity()


    def _update_button_sensitivity(self):
        self.builder.get_object("install_button").set_sensitive(not self.dropbox_installed)
        self.builder.get_object("uninstall_button").set_sensitive(self.dropbox_installed)
        self.builder.get_object("start_button").set_sensitive(self.dropbox_installed)
        self.builder.get_object("stop_button").set_sensitive(self.dropbox_installed)
        self.builder.get_object("exclude_dir_button").set_sensitive(self.dropbox_installed)
        self.builder.get_object("include_dir_button").set_sensitive(self.dropbox_installed)
        self.builder.get_object("change_account_button").set_sensitive(self.dropbox_installed)


    def run(self):
        self.dlg.run()
        self.dlg.destroy()


    def _show_excluded_folders(self):
        result = self._dbcmd("exclude list")

        # the first line just says "Excluded" - make this friendlier
        index = result.find("Excluded: \n")
        if index != -1:
            result = result.replace("Excluded: \n", "Excluded Folder Set:\n\n", 1)

        # this is what it says when there aren't any folders being excluded.  Tweak the terminology
        # to be consistent to lessen chance of user confusion.
        if result.find("No directories are being ignored.") != -1:
            result = "Excluded Folder Set:\n\n< None >"

        result += "\n\nFolders excluded or restored may not appear in list\nuntil initial Dropbox sync is complete."
        self.status_buffer.set_text(result)


    def on_exclude_dir_button_released(self, widget, data=None):
        builder = builder_factory(self)
        folder_dlg = builder.get_object("folder_dialog")
        folder_dlg.set_title("Add Folder to Excluded Set")
        folder_dlg.set_transient_for(self.dlg)

        instructions_label = builder.get_object("instructions_label")
        instructions_label.set_text('All folders are automatically synced onto the controller. Adding a folder to the Excluded Set prevents Dropbox from syncing it further.\n\nAfter a folder has been added to the Excluded Set, you can then remove it from the controller to recover the disk space using the PathPilot file tab.\n\nSeparate multiple folder names using spaces. Wrap folder names containing spaces with quotes (e.g. "one two").')

        self.folder_dlg = folder_dlg   # just so the ok and cancel button signal handlers get set a response
        folder_dlg.show_all()
        folder_dlg.present()
        response = folder_dlg.run()
        folder = builder.get_object("folder_entry").get_text()
        self.folder_dlg = None
        folder_dlg.destroy()

        if response == gtk.RESPONSE_OK:
            with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
                self._ensure_db_running()
                if len(folder) > 0:
                    self._dbcmd("exclude add %s" % folder)
                self._show_excluded_folders()


    def on_exclude_dir_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_exclude_dir_button_released(widget, data)


    def on_include_dir_button_released(self, widget, data=None):
        builder = builder_factory(self)
        folder_dlg = builder.get_object("folder_dialog")
        folder_dlg.set_title("Remove Folder from Excluded Set")
        folder_dlg.set_transient_for(self.dlg)

        instructions_label = builder.get_object("instructions_label")
        instructions_label.set_text('All folders are automatically synced onto the controller, unless they were previously added to the Excluded Set. Removing a folder from the Excluded Set enables Dropbox to start syncing it again.\n\nSeparate multiple folder names using spaces. Wrap folder names containing spaces with quotes (e.g. "one two").')

        self.folder_dlg = folder_dlg   # just so the ok and cancel button signal handlers get set a response
        folder_dlg.show_all()
        folder_dlg.present()
        response = folder_dlg.run()
        folder = builder.get_object("folder_entry").get_text()
        self.folder_dlg = None
        folder_dlg.destroy()

        if response == gtk.RESPONSE_OK:
          with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
                self._ensure_db_running()
                if len(folder) > 0:
                    self._dbcmd("exclude remove %s" % folder)
                self._show_excluded_folders()


    def on_include_dir_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_include_dir_button_released(widget, data)


    def on_start_button_released(self, widget, data=None):
        with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
            # we always use the -i arg just in case the user canceled the dropbox login and closed the browser
            # on the initial install for example.  Its harmless if dropbox is already linked to an account.
            result = self._dbcmd("start -i")

            # the text output is not super warm-n-fuzzy.  Filter out the crazy complaint that dropbox isn't running when you're trying to start it
            # as that will seem schizo to the user.
            result = result.replace("Dropbox isn't running!", "", 1)

            # give it a little time with the plexiglass up to get on its feet (or for the user to login
            # if the start pops the browser to link an account).

            # sigh. more complications because dropbox is such a 'sealed black box'.
            # we may need to create the symlink into the gcode folder. But the source folder name for the symlink
            # can depend on the account that is used to login to dropbox.
            # and just because "dropbox.py start -i" returned doesn't mean the account is linked to this
            # computer yet.  The user can be sitting in the browser and typing slowly still.
            #
            # so we sit in a loop waiting for the dropbox.py status to clue us in that
            # the local sync folder is probably in place now.
            sw = timer.Stopwatch()
            while sw.get_elapsed_seconds() < 60:
                time.sleep(2)
                result2 = self._dbcmd("status").strip()
                print "dropbox status is: '{}'".format(result2)
                if result2 not in ["Starting...", "Dropbox isn't responding!", "Connecting...", "Waiting to be linked to a Dropbox account..."]:
                    break

            # Give it a bit more chance to actually create the local sync folder name and such.
            time.sleep(2)

            self.create_dropbox_symlink()

            self.status_buffer.set_text(result + "\n\n" + result2)


    def on_start_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_start_button_released(widget, data)


    def on_stop_button_released(self, widget, data=None):
        with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
            result = self._dbcmd("stop")

            if result.find("Dropbox isn't responding!") != -1:
                # sigh.  sometimes it gets sleepy.  give it another chance.
                time.sleep(2)
                result = self._dbcmd("stop")

            self.status_buffer.set_text(result)


    def on_stop_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_stop_button_released(widget, data)


    def find_all_dropbox_home_folders(self):
        # The dropbox client ends up creating a local sync dir in the home directory.
        # But the name of the sync directory varies depending on what type
        # of Dropbox account is logged in and linked to the controller.
        # Dropbox Personal account (the most common) = /home/operator/Dropbox
        # Dropbox Business account = /home/operator/TEAMNAME Dropbox
        #    where TEAMNAME is a placeholder for the name chosen when the Dropbox Business
        #    account was first created.

        db_folders = []   # each element is a tuple (full path of folder, folder name)
        candidates = os.listdir(os.environ['HOME'])
        for name in candidates:
            fullpath = os.path.join(os.environ['HOME'], name)
            if os.path.isdir(fullpath) and name.find('Dropbox') != -1:
                # strong candidate, but the acid test is real dropbox folders have a .dropbox hidden file
                # in them.
                if os.path.isfile(os.path.join(fullpath, '.dropbox')):
                    db_folders.append((fullpath, name))

        return db_folders


    def create_dropbox_symlink(self):
        # The dropbox client ends up creating a local sync dir in the home directory.
        # But the name of the sync directory varies depending on what type
        # of Dropbox account is logged in and linked to the controller.
        # Dropbox Personal account (the most common) = /home/operator/Dropbox
        # Dropbox Business account = /home/operator/TEAMNAME Dropbox
        #    where TEAMNAME is a placeholder for the name chosen when the Dropbox Business account was first created.
        #
        # There can be more than Dropbox folder in the home dir also because over time as
        # dropbox accounts are switched or dropbox is installed and uninstalled
        # they can pile up.
        #
        # And depending on what order of accounts are used over time, we could end up choosing
        # the 'wrong' Dropbox local sync folder when creating the symlink.
        #
        # So the solution to this semi-rare issue is just to create symlinks for all dropbox related
        # folders we find.  Then the user can always delete symlinks that are leftovers or dead.

        db_folders = self.find_all_dropbox_home_folders()

        # Now create symlinks for all that we found.
        if len(db_folders) > 0:
            for dbfolder in db_folders:
                targetdir = os.path.join(constants.GCODE_BASE_PATH, dbfolder[1])
                if not os.path.exists(targetdir):
                    try:
                        os.symlink(dbfolder[0], targetdir)
                    except Exception as e:
                        traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                        print "Exception creating symlink from {} to {}.\n{}".format(dbfolder[0], targetdir, traceback_txt)
                else:
                    print "Target dropbox symlink already exists: {}".format(targetdir)
        else:
            print "ERROR: could not find any Dropbox sync directories in the home dir."


    def on_install_button_released(self, widget, data=None):
        # fetch dropbox.py if needed, then install
        dropbox_py = os.path.join(os.environ['HOME'], 'dropbox.py')
        if not (os.path.isfile(dropbox_py) and os.access(dropbox_py, os.X_OK)):
            self.status_buffer.set_text("Downloading and installing Dropbox.\n\nPlease wait for web browser to load and then\nfollow directions to link your Dropbox account\nto this controller.\n\nIf installation is canceled, click the Uninstall button\nfollowed by the Install button to retry installation.")

            with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
                # fetch it
                failed = subprocess.call(['wget --output-document=%s https://linux.dropbox.com/packages/dropbox.py' % dropbox_py], shell=True)
                if failed:
                    result = 'Failed to fetch dropbox.py from linux.dropbox.com'
                    self.status_buffer.set_text(result)
                    return

                # make it executable
                os.chmod(dropbox_py, stat.S_IRWXU | stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

                self.dropbox_installed = True

        # now just do everything the same as the Start button.
        self.on_start_button_released(widget, data)

        self._update_button_sensitivity()


    def on_install_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_install_button_released(widget, data)


    def confirm_account_unlink_and_file_removal(self):
        dlg = gtk.MessageDialog(self.dlg, gtk.DIALOG_MODAL, type=gtk.MESSAGE_WARNING, buttons=gtk.BUTTONS_OK_CANCEL)
        dlg.set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="black">Unlink Dropbox Account</span>')
        dlg.format_secondary_markup('<span weight="regular" font_desc="Roboto Condensed 11" foreground="black">The Dropbox account will be unlinked from this controller and no further syncing will occur.\n\n</span><span weight="bold" font_desc="Roboto Condensed 11" foreground="red">The entire Dropbox folder on this controller will be DELETED.</span>')
        response = dlg.run()
        dlg.destroy()
        return (response == gtk.RESPONSE_OK)


    def delete_all_dropbox_home_folders(self, db_folders):
        # remove the real dir and all contents
        # remove any broken symlink to this sitting over in the
        # gcode directory.
        for dbfolder in db_folders:
            try:
                print "Deleting local dropbox folder: {}".format(dbfolder[0])
                targetdir = os.path.join(constants.GCODE_BASE_PATH, dbfolder[1])
                if os.path.islink(targetdir):
                    print "Found matching gcode folder symlink: {}".format(targetdir)
                    if os.readlink(targetdir) == dbfolder[0]:
                        print "Removing old gcode folder symlink: {}".format(targetdir)
                        os.remove(targetdir)  # nuke the link we are about to break anyway

                # I've seen situations where dropbox creates symlinks like "Your team Dropbox" in the home folder.
                # I think this happens when a personal account is upgraded to a business account later.
                # Regardless, remove it but be careful as shutil.rmtree pukes on symlinks.
                if os.path.islink(dbfolder[0]):
                    # the combo of the two calls below achieves the equivalent of shutil.rmtree()
                    # which is what we want.
                    subprocess.call("rm -rf '%s/'" % dbfolder[0], shell=True)  # this removes everything inside the symlink
                    subprocess.call("rm -rf '%s'" % dbfolder[0], shell=True)   # this removes the symlink itself
                else:
                    shutil.rmtree(dbfolder[0])

            except Exception as e:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                print "Exception removing dropbox home folder {}.\n{}".format(dbfolder[0], traceback_txt)


    def on_uninstall_button_released(self, widget, data=None):
        # ask the user to confirm
        ok = self.confirm_account_unlink_and_file_removal()
        if ok:
            # get the list of folders before we remove dropbox
            db_folders = self.find_all_dropbox_home_folders()

            failed = subprocess.call(['dropbox_remove.sh'], shell=True)
            if failed:
                self.status_buffer.set_text("Error uninstalling Dropbox.")
            else:
                self.dropbox_installed = False
                self.status_buffer.set_text("Dropbox uninstalled from controller.")

                # now we are positive that Dropbox is not running so there is no account
                # linkage to this computer.
                # that makes it safe to delete all the local dropbox folders and be
                # confident that Dropbox won't start syncing those file deletion actions
                # up to the account.
                #
                # we have to clean up like this at uninstall or account change because otherwise
                # later if it gets re-installed or linked to a new account, folder name collisions
                # with legacy Dropbox folders wreaks havoc, causing the dropbox client software
                # to display dialogs offering the user to move the local dropbox folder to anywhere
                # (and then we can't find it).

                self.delete_all_dropbox_home_folders(db_folders)

        self._update_button_sensitivity()


    def on_uninstall_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_uninstall_button_released(widget, data)


    def on_change_account_button_released(self, widget, data=None):
        # unlink is the Dropbox terminology for how to "logout" and stop this computer from syncing any further.
        # if dropbox is running, stop dropbox, then delete ~/.dropbox, then restart dropbox with -i argument

        # ask the user to confirm
        ok = self.confirm_account_unlink_and_file_removal()
        if ok:
            with plexiglass.PlexiglassInstance(self.dlg, full_screen=False) as p:
                self.status_buffer.set_text("Unlinking Dropbox account.\n\nPlease wait for web browser to load and then\nfollow directions to link a different Dropbox account\nto this controller.")

                # Make damn sure dropbox is not running.
                result = None
                while result != "Dropbox isn't running!":
                    self._dbcmd("stop")
                    time.sleep(2)   # give it a sec
                    result = self._dbcmd("status").strip()

                retcode = subprocess.call(['rm -rf $HOME/.dropbox'], shell=True)
                if retcode == 0:
                    db_folders = self.find_all_dropbox_home_folders()
                    self.delete_all_dropbox_home_folders(db_folders)

                    # now just do everything Start does.
                    self.on_start_button_released(widget, data)


    def on_change_account_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_change_account_button_released(widget, data)


    def on_close_button_released(self, widget, data=None):
        self.dlg.response(gtk.RESPONSE_OK)


    def on_close_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_close_button_released(widget, data)


    def on_cancel_button_released(self, widget, data=None):
        self.folder_dlg.response(gtk.RESPONSE_CANCEL)


    def on_cancel_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_cancel_button_released(widget, data)


    def on_ok_button_released(self, widget, data=None):
        self.folder_dlg.response(gtk.RESPONSE_OK)


    def on_ok_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_ok_button_released(widget, data)


    def _ensure_db_running(self):
        cmdline = self.dbcmdtemplate % "running"
        while True:
            retcode = subprocess.call(cmdline, shell=True)
            if retcode == 1:
                break
            else:
                self._dbcmd("start")
                time.sleep(0.5)


    def _dbcmd(self, cmd):
        cmdline = self.dbcmdtemplate % cmd
        print cmdline
        try:
            result = subprocess.check_output(cmdline, shell=True)
        except subprocess. CalledProcessError:
            result = "dropbox experienced an error, try again."
        print result
        return result


def _nop_callback():
    pass


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    print "dropbox_helper.py starting"

    # There is no machine control going on during config chooser so just give the plexiglass something
    # to call that has no effect when it needs to make sure that all jogging has stopped.
    plexiglass.PlexiglassInitialize(_nop_callback)

    ui = DBConfig()
    ui.run()

    print "dropbox_helper.py exiting"

    sys.exit(0)
