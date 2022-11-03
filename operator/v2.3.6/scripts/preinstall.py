#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import gtk
import sys
import os
import inspect
import re
import time
import subprocess

# Let's be sure the version that is currently running is compatible with updating
# to this version and if not, display helpful instructions.
#
# e.g.    1.9.11 to 1.9.12 = yay
#         1.9.8 to 2.0.0 = boo
#         2.0.4 to 1.9.12 = boo
#

def parse_version_file(version_filepath):
    '''
    Returns a list of [major int, minor int, build int, optional suffix_string ]
    If file cannot be parsed, it returns [0, 0, 0]
    '''
    version_list = [0, 0, 0]

    # version label shows major version + hash associated with most recent commit past version tag.
    try:
        vf = open(version_filepath, 'r')
        try:
            for line in vf:
                line = line.strip()
                if line[0] != "":
                    version = line

                    # version lines to test with for complete coverage
                    #version = "v1.99.2323"
                    #version = "v1.99.2323d"
                    #version = "v2.10.20-beta3-81-g00ebd564"
                    #version = "v112.0.20b-81-g00ebd564"

                    # look for a non-release version with the commit hash suffix (with or without the suffix letter messiness)
                    # don't bother trying to pull out the suffix letter in this case - we just don't care and
                    # aren't using it in the future anyway
                    matchlist = re.findall(r'v(\d+)\.(\d+)\.(\d+)[a-z]*-(.+)', version)
                    if len(matchlist) > 0:
                        version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]), matchlist[0][3] ]

                    else:
                        # next try a match with the deprecated behavior with suffix letters
                        matchlist = re.findall(r'v(\d+)\.(\d+)\.(\d+)([a-z]+)', version)
                        if len(matchlist) > 0:
                            # this is an old deprecated version that used suffix letters
                            version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]), matchlist[0][3] ]

                        else:
                            # now look for a normal released version
                            matchlist = re.findall(r'v(\d+)\.(\d+)\.(\d+)', version)
                            if len(matchlist) > 0:
                                version_list = [ int(matchlist[0][0]), int(matchlist[0][1]), int(matchlist[0][2]) ]
                    break

        finally:
            vf.close()
    except:
        pass

    return version_list


if __name__ == "__main__":

    exit_code = 0

    # this is the directory where this module code is running from
    program_dir = os.path.dirname(os.path.abspath(inspect.getsourcefile(parse_version_file)))

    current_version_filepath = os.path.join(os.environ['HOME'], 'tmc', 'version.txt')
    our_version_filepath = os.path.join(program_dir, '..', 'version.txt')
    out_version_filepath = os.path.normpath(our_version_filepath)

    print "Current installed version filepath = %s" % current_version_filepath
    print "Our version filepath = %s" % our_version_filepath

    sys.stdout.flush()

    # read and parse /home/operator/tmc/version.txt and ../version.txt
    current_version_list = parse_version_file(current_version_filepath)
    our_version_list = parse_version_file(our_version_filepath)

    print "Current installed version = ", current_version_list
    print "Our version = ", our_version_list

    sys.stdout.flush()

    # are the major version numbers the same?

    if current_version_list[0] < our_version_list[0]:

        # they are trying to upgrade across a major version number which currently indicates
        # OS level incompatibility.  Tell them to contact Tormach for
        # new PathPilot installation media.

        print "preinstall detected trying to upgrade across a major version number - aborting."

        # nope - that means so far that the underlying OS is different
        # and we cannot let the installation continue.
        md = gtk.MessageDialog(None,
                               gtk.DIALOG_MODAL,
                               gtk.MESSAGE_ERROR,
                               gtk.BUTTONS_OK,
                               "Incompatible software update - installation stopped.")

        md.format_secondary_text("Updating from PathPilot v%d.%d.%d to v%d.%d.%d requires PathPilot Installation Software on a USB flash drive (PN 38249), available from tormach.com.\n\nAs an alternative, you may download the latest v%d.x.x from tormach.com/updates." %
                                 (current_version_list[0], current_version_list[1], current_version_list[2],
                                  our_version_list[0], our_version_list[1], our_version_list[2],
                                  current_version_list[0]))
        md.show_all()
        md.run()
        md.destroy()
        exit_code = 1

    elif current_version_list[0] > our_version_list[0]:

        # they are trying to revert back across a major version number - this requires use of
        # 'restore media'

        print "preinstall detected trying to revert back across a major version number - aborting."

        # nope - that means so far that the underlying OS is different
        # and we cannot let the installation continue.
        md = gtk.MessageDialog(None,
                               gtk.DIALOG_MODAL,
                               gtk.MESSAGE_ERROR,
                               gtk.BUTTONS_OK,
                               "Incompatible software update - installation stopped.")

        md.format_secondary_text("Reverting from PathPilot v%d.%d.%d to v%d.%d.%d requires PathPilot Restore DVD (PN 35246), available from tormach.com.\n\nAs an alternative, you may download the latest v%d.x.x from tormach.com/updates." %
                                 (current_version_list[0], current_version_list[1], current_version_list[2],
                                  our_version_list[0], our_version_list[1], our_version_list[2],
                                  current_version_list[0]))
        md.show_all()
        md.run()
        md.destroy()

        exit_code = 1

    #
    # Someday we might do even more checking in here....
    #

    if exit_code != 0 and current_version_list[0] < 2:
        # If we are trying to abort the software update installation and
        # the running version is 1.x, we have to shutdown the controller
        # within this script because the calling operator_login script does not
        # check the exit code of preinstall.sh.  So if we return, it will
        # go forward with changing the tmc symlink and we'll have broken the
        # controller for the customer.

            # we have to shutdown the controller here
            print "Shutting down controller to prevent calling < 2.x script from continuing the install."
            sys.stdout.flush()

            # tell user we are shutting down to stop the installation so it doesn't surprise them.

            md = gtk.MessageDialog(None,
                                   gtk.DIALOG_MODAL,
                                   gtk.MESSAGE_ERROR,
                                   gtk.BUTTONS_OK,
                                   "Stopping PathPilot installation.")

            md.format_secondary_text("Shutting down controller - PathPilot version has not been changed.")
            md.show_all()
            md.run()
            md.destroy()

            # pump the GTK event loop for awhile to make sure message dialog is fully removed from screen
            # vs. a ghost
            while gtk.events_pending():
                gtk.main_iteration(False)

            # use this and not subprocess.check_output because PP 1.9.x is python 2.6.x and check_output
            # doesn't exist until 2.7.
            subprocess.call('sudo shutdown -H now', shell=True)

            # observed that on a 1.9.12-pre4 system that the shutdown command triggered the X server to go down
            # and as soon as that started to die, any gtk actions results in some untrappable exception
            # and we fell out of the program and the calling scripts marched right along and changed
            # the tmc symlink which hosed the controller.
            # Arg!  So no matter what happens, just park here forever until we actually get killed.
            while True:
                try:
                    print "preinstall.py sleeping and trying to prevent caller from continuing."
                    time.sleep(3600)
                except:
                    pass

    sys.exit(exit_code)
