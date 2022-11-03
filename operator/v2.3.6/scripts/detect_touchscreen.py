#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import sys
import subprocess

##########################
# NOTE: do not print anything except the device name or an empty string as the output is captured and used by other scripts
##########################

LIST_OF_KNOWN_DEVICES = ['eGalax Inc. USB TouchController',
                        'D-WAV Scientific Co., Ltd eGalax TouchScreen',
                        'eGalax Inc. USB TouchControlleၲ', # trailing 3 byte sequence " 0xe1 0x81 0xb2"
                        'EloTouchSystems,Inc Elo TouchSystems 2216 AccuTouch® USB Touchmonitor Interface',
                        'FUJITSU COMPONENT LIMITED USB Touch Panel',
                        'ILITEK Multi-Touch-V3000',
                        'Elo TouchSystems, Inc. Elo TouchSystems 2700 IntelliTouch(r) USB Touchmonitor Interface'
                        ]

fake_xinput_list = '⎡ Virtual core pointer                    \tid=2\t[master pointer  (3)]\n' + \
    '⎜   ↳ Virtual core XTEST pointer              \tid=4\t[slave  pointer  (2)]\n' + \
    '⎜   ↳ Logitech USB Keyboard                   \tid=12\t[slave  pointer  (2)]\n' + \
    '⎜   ↳ FUJITSU COMPONENT LIMITED USB Touch Panel              id=13\t[slave  pointer  (2)]\n' + \
    '⎣ Virtual core keyboard                       \tid=3\t[master keyboard (2)]\n' + \
    '    ↳ Virtual core XTEST keyboard             \tid=5\t[slave  keyboard (3)]\n' + \
    '    ↳ Power Button                            \tid=6\t[slave  keyboard (3)]\n' + \
    '    ↳ Video Bus                               \tid=7\t[slave  keyboard (3)]\n' + \
    '    ↳ Power Button                            \tid=8\t[slave  keyboard (3)]\n' + \
    '    ↳ Sleep Button                            \tid=9\t[slave  keyboard (3)]\n' + \
    '    ↳ Logitech USB Keyboard                   \tid=10\t[slave  keyboard (3)]\n' + \
    '    ↳ Logitech USB Keyboard                   \tid=11\t[slave  keyboard (3)]\n'

def run_cmd(cmd):
    result = ''
    try:
        result = subprocess.check_output(cmd, shell=True)
        #print '%s: %s' % (cmd, result.strip())
    except subprocess.CalledProcessError:
        #print 'Failed to run %s' % cmd
        pass
    return result

touchscreen_device = 'No supported touchscreen found.'
return_code = 1

if len(sys.argv) > 1 and sys.argv[1] == '--test':
    test_mode = True
    xinput_list = fake_xinput_list
else:
    test_mode = False
    xinput_list = run_cmd('xinput --list')

if xinput_list != '':
    for known_device in LIST_OF_KNOWN_DEVICES:
        #print '%s\n' % known_device
        if known_device in xinput_list:
            if test_mode:
                print '%s:found a match for: "%s"\n' % (sys.argv[0], known_device)
            touchscreen_device = known_device
            return_code = 0
            break

print touchscreen_device
sys.exit(return_code)
