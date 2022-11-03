#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------

#
# BE VERY CAREFUL so this script will run correctly even on ancient PathPilot 1.x
# systems.  Those use python 2.6.5 which does NOT support the newer "some string {:s}".format(variable)
# syntax so that is WHY this still uses the old % string formatting.
#

import pygtk
pygtk.require("2.0")
import gtk
import sys
import os
import subprocess
import string

EXITCODE_EULA_AGREED      = 0
EXITCODE_EULA_NOT_AGREED  = 1
EXITCODE_BADARG           = 2


class eula_dialog():

    def __init__(self, versiondir):

        self.exit_code = EXITCODE_EULA_NOT_AGREED

        # look for the .glade file and the resources in a 'images' subdirectory below
        # this source file.
        GLADE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')

        builder = gtk.Builder()
        gladefilepath = os.path.join(GLADE_DIR, 'eula.glade')
        result = builder.add_from_file(gladefilepath)
        assert result > 0, "Builder failed on %s" % gladefilepath

        # be defensive if stuff exists in glade file that can't be found in the source anymore!
        missing_signals = builder.connect_signals(self)
        if missing_signals is not None:
            raise RuntimeError("Cannot connect signals: ", missing_signals)

        # load eula text
        textview = builder.get_object('license_textview')
        textbuffer = textview.get_buffer()
        eulafile  = open(os.path.join(GLADE_DIR, 'eula.txt'), 'r')
        if eulafile:
            text = eulafile.read()
            eulafile.close()
            textbuffer.set_text(text)

        self.window = builder.get_object("eula_window")
        self.window.show()


    def on_agree_button_clicked(self, widget, data=None):
        # updates may show eula, but not want to continue to config selection
        # operator login to determine when to show this
        print 'EULA agree button clicked'
        self.exit_code = EXITCODE_EULA_AGREED
        self.window.destroy()
        gtk.main_quit()


    def on_exit_button_clicked(self, widget, data=None):
        print 'EULA NOT agreed, exit button clicked'
        self.exit_code = EXITCODE_EULA_NOT_AGREED
        self.window.destroy()
        gtk.main_quit()


def create_marker_file(markerfilepath):
    # create marker file FOR THIS VERSION that records date and time
    # this can be run from preinstall.sh context so we can't use the
    # the $HOME/tmc link as that would still be pointing to the OLD
    # version.
    subprocess.call('date > %s' % markerfilepath, shell=True)
    print "EULA agree marker file created: %s" % markerfilepath


def delete_marker_file(markerfilepath):
    if os.path.exists(markerfilepath):
        os.remove(markerfilepath)
        print "EULA agree marker file DELETED: %s" % markerfilepath


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    # required argument is the full path to the top level directory for the version
    # of the software we are bundled with.  e.g. /home/operator/v2.5.3
    # this is because EACH version of the software may have a distinct EULA as
    # we need to know if the customer has ever accepted the EULA FOR THAT VERSION.
    # so we use a marker file for each version.
    if len(sys.argv) != 2:
        print "usage: eula.py dir"
        print "\ndir = full path to a specific version of PathPilot, e.g. /home/operator/v2.5.8"

    else:
        versiondir = sys.argv[1]
        if os.path.exists(versiondir) and os.path.exists(os.path.join(versiondir, 'version.json')):

            # version directory seems reasonable.
            # if the eula agreed marker file exists, just exit as though they agreed since they already did.
            markerfilepath = os.path.join(versiondir, 'eula_agreed.txt')
            if os.path.exists(markerfilepath):
                print "eula.py: no need to display eula and get acceptance because marker file already exists\n%s" % markerfilepath
                sys.exit(EXITCODE_EULA_AGREED)

            else:
                # ask the user
                dlg = eula_dialog(versiondir)
                gtk.main()
                if dlg.exit_code == EXITCODE_EULA_AGREED:
                    create_marker_file(markerfilepath)
                else:
                    delete_marker_file(markerfilepath)

                sys.exit(dlg.exit_code)

        else:
            print "%s doesn't appear to be a PathPilot version directory." % versiondir

    sys.exit(EXITCODE_BADARG)
