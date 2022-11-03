#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# run this via 'sudo python grub_no_uuid.py' for it to function properly

# this comments out the line "GRUB_CMDLINE_LINUX_UUID=true" if found in /etc/default/grub

# runs update-grub afterward if needed

import os
import sys
import fileinput
import subprocess

ETC_DEFAULT_GRUB = '/etc/default/grub'
GRUB_DISABLE_LINUX_UUID = 'GRUB_DISABLE_LINUX_UUID'
UPDATE_GRUB = 'update-grub'

if __name__ == "__main__":
    if os.geteuid() != 0:
        print '%s must be run via sudo' % (sys.argv[0])
        exit(1)

    need_to_patch = False

    try:
        with open(ETC_DEFAULT_GRUB) as f:
            for line in f:
                if line.startswith(GRUB_DISABLE_LINUX_UUID):
                    # found the line - see if it needs to be patched
                    print 'found %s - will comment out of %s' % (GRUB_DISABLE_LINUX_UUID, ETC_DEFAULT_GRUB)
                    need_to_patch = True;
    except Exception, e:
        print 'exception while searching for %s in %s' % (GRUB_DISABLE_LINUX_UUID, ETC_DEFAULT_GRUB)
        print str(e)
        exit(1)

    if need_to_patch:
        try:
            for line in fileinput.input(ETC_DEFAULT_GRUB, inplace=True):
                if line.startswith(GRUB_DISABLE_LINUX_UUID):
                    # trailing comma after print suppresses newline
                    print '#' + line,
                else:
                    print line,

            # run update-grub
            try:
                print 'running %s' % UPDATE_GRUB
                subprocess.call(UPDATE_GRUB)
            except Exception, e:
                print("Could not run program: %s" % UPDATE_GRUB)
                print str(e)
                exit(1)
        except Exception, e:
            print 'exception while commenting out %s in %s' % (GRUB_DISABLE_LINUX_UUID, ETC_DEFAULT_GRUB)
            print str(e)
            exit(1)
    else:
        print 'no %s patch needed in %s' % (GRUB_DISABLE_LINUX_UUID, ETC_DEFAULT_GRUB)

    exit(0)

