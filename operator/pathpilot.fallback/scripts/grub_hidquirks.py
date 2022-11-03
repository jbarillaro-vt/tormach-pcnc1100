#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# run this via 'sudo python grub_hidquirks.py' for it to function properly

# this adds "usbhid.quirks=0x0eef:0x0001:0x40" to "GRUB_CMDLINE_LINUX_DEFAULT" if not present
# it fixes a bug with older Planar egalax USB touchscreen controllers where any touch
# moves the cursor to the upper left and clicks the left button

# runs update-grub afterward if needed

import os
import sys
import fileinput
import subprocess

ETC_DEFAULT_GRUB = '/etc/default/grub'
HID_QUIRKS = ' usbhid.quirks=0x0eef:0x0001:0x40\"'
GRUB_CMDLINE_LINUX_DEFAULT = 'GRUB_CMDLINE_LINUX_DEFAULT'
UPDATE_GRUB = 'update-grub'

if __name__ == "__main__":
    if os.geteuid() != 0:
        print '%s must be run via sudo' % (sys.argv[0])
        exit(1)

    need_to_patch = False

    try:
        with open(ETC_DEFAULT_GRUB) as f:
            for line in f:
                if line.startswith(GRUB_CMDLINE_LINUX_DEFAULT):
                    print 'found: ' + line
                    # found the line - see if it needs to be patched
                    if not HID_QUIRKS in line:
                        print 'adding "%s to %s in file %s' % (HID_QUIRKS, GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB),
                        need_to_patch = True;
    except Exception, e:
        print 'exception while searching for %s in %s' % (GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)
        print str(e)
        exit(1)

    if need_to_patch:
        try:
            for line in fileinput.input(ETC_DEFAULT_GRUB, inplace=True):
                if line.startswith(GRUB_CMDLINE_LINUX_DEFAULT):
                    # found the line - see if it needs to be patched
                    if not HID_QUIRKS in line:
                        # find/remove trailing double quote
                        # remove newline and trailing space
                        line = line.rstrip('\n')
                        line = line.rstrip()
                        # remove trailing double quote
                        line = line.rstrip('"')
                        line = line.rstrip()
                        # append HID_QUIRKS
                        line = line + HID_QUIRKS
                        replacement_line = line
                        # need to include newline lost to rstrip()
                        print line
                else:
                    print line,
            print replacement_line
            # run update-grub
            try:
                print 'running %s' % UPDATE_GRUB
                subprocess.call(UPDATE_GRUB)
            except Exception, e:
                print("Could not run program: %s" % UPDATE_GRUB)
                print str(e)
                exit(1)
        except Exception, e:
            print 'exception while commenting out %s in %s' % (GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)
            print str(e)
            exit(1)

    else:
        print 'no %s patch needed in %s' % (GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)

    exit(0)

