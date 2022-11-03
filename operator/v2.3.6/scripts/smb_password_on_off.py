#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------



# changes ~/smb.conf.share file's [gcode]guest ok = no into [gcode]guest ok = yes.
# required for Macs and some Windows machine to connect to gcode SMB share

import os
import sys
import fileinput
import subprocess

SMB_CONF_SHARE = os.path.join(os.environ['HOME'], 'smb.conf.share')

if __name__ == "__main__":
    need_to_patch = False

    if len(sys.argv) > 1:
        # 'enable or 'disable' expected
        if sys.argv[1] == 'enable':
            guest_ok = 'no'
        elif sys.argv[1] == "disable":
            guest_ok = 'yes'
        else:
            print 'usage: %s enable|disable' % sys.argv[0]
            sys.exit(1)
    else:
        print 'usage: %s enable|disable' % sys.argv[0]
        sys.exit(1)

    if guest_ok == 'no':
        guest_ok_not = 'yes'
    else:
        guest_ok_not = 'no'

    # scan file to see if patching is required
    try:
        with open(SMB_CONF_SHARE) as f:
            print "scanning file %s for 'guest ok = %s'" % (SMB_CONF_SHARE, guest_ok_not)
            for line in f:
                if 'guest ' in line and ' ok' in line and '=' in line and guest_ok_not in line:
                    need_to_patch = True;
                    break
    except Exception, e:
        print "exception while searching for '%s' in %s" % ('guest ok = no', SMB_CONF_SHARE)
        print str(e)
        exit(1)

    if need_to_patch:
        try:
            # CAUTION! everything 'print()ed' in here goes to the file not the console
            for line in fileinput.input(SMB_CONF_SHARE, inplace = True):
                line = line.rstrip()
                if 'guest ' in line and ' ok' in line and '=' in line and guest_ok_not in line:
                    line = line.replace(guest_ok_not, guest_ok)
                print line
        except Exception, e:
            print "exception while patching '%s' to '%s' in %s" % (guest_ok_not, guest_ok, SMB_CONF_SHARE)
            print str(e)
            exit(1)
        print "file %s patched, 'guest ok = %s' to 'guest ok = %s'" % (SMB_CONF_SHARE, guest_ok_not, guest_ok)
        print 'restarting smbd to make change take effect.'
        ret_val = subprocess.call(['sudo restart smbd'], shell = True)
        print "ret_val from 'restart smbd': %d" % ret_val
    else:
        print 'no patch needed in %s' % (SMB_CONF_SHARE)

    exit(0)

