# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import os

__CRASH_DETECTOR_FILE = "/var/tmp/pp-crashdetector.dat"


def create_crash_detection_file():
    if not os.path.exists(__CRASH_DETECTOR_FILE):
        f = open(__CRASH_DETECTOR_FILE, "w")
        f.close()

def delete_crash_detection_file():
    if os.path.exists(__CRASH_DETECTOR_FILE):
        os.remove(__CRASH_DETECTOR_FILE)

def crash_detection_file_exists():
    return os.path.exists(__CRASH_DETECTOR_FILE)
