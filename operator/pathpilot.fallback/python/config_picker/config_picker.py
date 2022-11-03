#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------

import sys

# This is the legacy config_picker.  We can't eliminate this code
# because OLDER versions of pathpilotmanager.py always assume that NEWER
# versions of the code will have a python/config_picker.py which can be
# run with a --eula_only arg AND without any python virtualenv active.
#
# We fixed this and eliminated assumptions about new versions, but
# this has to continue to exist.
#
# It will be called when an old version has installed a new version
# and the postinstall.sh has returned success.  At that point, the
# old pathpilotmanager.py will run ~/tmc/python/config_picker/config_picker.py --eula_only
# and expect it to return 0 on success.
# So here it is.

print "Legacy config_picker.py running and returning success."
sys.exit(0)
