#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# run this via 'sudo python grub_add_param.py <param-string>' for it to function properly

# this adds " <param-string>" to "GRUB_CMDLINE_LINUX_DEFAULT=" line if not already present

# runs update-grub afterward if needed

import os
import sys
import fileinput
import subprocess

kernel_param = ''

ETC_DEFAULT_GRUB = '/etc/default/grub'
GRUB_CMDLINE_LINUX_DEFAULT = 'GRUB_CMDLINE_LINUX_DEFAULT'
UPDATE_GRUB = 'update-grub'


if __name__ == "__main__":
    if os.geteuid() != 0:
        print '%s must be run via sudo' % (sys.argv[0])
        exit(1)

    # get param from command line
    argc = len(sys.argv)
    if argc < 2 or argc > 3:
        print 'usage: sudo %s <param-string>' % (sys.argv[0])
        exit(1)
    else:
        kernel_param = sys.argv[1]

    need_to_patch = False
    grub_cmdline_linux_found = False

    try:
        with open(ETC_DEFAULT_GRUB) as f:
            for line in f:
                if line.startswith(GRUB_CMDLINE_LINUX_DEFAULT):
                    grub_cmdline_linux_found = True
                    print 'found: ' + line.rstrip('\n')
                    # found the line - see if it needs to be patched
                    print 'looking for param "%s"' % kernel_param
                    if not kernel_param in line:
                        print 'appending "%s to %s= in file %s\n' % (kernel_param, GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB),
                        need_to_patch = True;
    except Exception, e:
        print 'exception while searching for %s in %s' % (GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)
        print str(e)
        exit(1)

    if not grub_cmdline_linux_found:
        print '%s not found in file %s' %(GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)
        exit(1)

    if need_to_patch:
        try:
            # throw exception if file does not exist
            with open(ETC_DEFAULT_GRUB) as f:
                pass
        except Exception, e:
            print 'exception while appending %s to %s= in %s' % (kernel_param, GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)
            print str(e)
            exit(1)

        for line in fileinput.input(ETC_DEFAULT_GRUB, inplace=True):
            if line.startswith(GRUB_CMDLINE_LINUX_DEFAULT):
                # found the line - see if it needs to be patched
                if not kernel_param in line:
                    # find/remove trailing double quote
                    # remove newline and trailing space
                    line = line.rstrip('\n')
                    line = line.rstrip()
                    # remove trailing double quote
                    line = line.rstrip('"')
                    # and any trailing whitespace
                    line = line.rstrip()
                    # append ' ' + kernel_param
                    # don't forget the closing quote
                    # include newline lost to rstrip()
                    line = line + ' ' + kernel_param + '\"' + '\n'
                    print line,
            else:
                print line,

        # run update-grub
        try:
            print 'running %s' % UPDATE_GRUB
            subprocess.call(UPDATE_GRUB)
        except Exception, e:
            print("exception running program: %s" % UPDATE_GRUB)
            print str(e)
            exit(1)

    else:
        # no need to patch
        print '\"%s\" param already present in %s= line of file %s' % (kernel_param, GRUB_CMDLINE_LINUX_DEFAULT, ETC_DEFAULT_GRUB)

    exit(0)

