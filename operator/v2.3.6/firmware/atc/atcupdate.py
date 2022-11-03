#!/usr/bin/env python
# atcupdate.py
#
# ATCNG Firmware uploader, host-side
#
# Copyright (c) 2018 Z-Bot, LLC
# All Rights Reserved
# Author: Noel Henson
#
# This file contains words to send and receive firmware to and from the
# ATC next-generation tool changer.
##############################################################################

import argparse
import serial
import zipfile
import sys
import os
from time import sleep

'''
This program accepts a zip file archive. The files in this archive are
unpacked and sent out the serial port to the ATC.
'''


# Arguments
#
parser = argparse.ArgumentParser()
parser.add_argument('zipfile', help='zipped firmware', type=argparse.FileType('r'))
parser.add_argument('-b', '--bootloader', help ='bootloader mode check, exit 0 if bootloader, 3 if not', action='store_true')
parser.add_argument('-f', '--force', help ='force upload ignoring version - development use only', action='store_true')
parser.add_argument('-n', '--newest', help ='upload newest firmware if newer than installed', action='store_true')
parser.add_argument('-i', '--ignorecks', help ='ignore checksum - development use only', action='store_true')
parser.add_argument('-q', '--quiet', help ='suppress all output (overrides -s)', action='store_true')
parser.add_argument('-s', '--summary', help ='summary output only', action='store_true')
parser.add_argument('-v', '--version', action='version', version='%(prog)s 1.4.0')
parser.add_argument('-c', '--checkatcversion', help ='check atc firmware version, exit code 0 if update not needed, 2 if update required', action='store_true')

progargs = parser.parse_args()

# Print Level ################################################################
if progargs.quiet: printlevel = 2
elif progargs.summary: printlevel = 1
else: printlevel = 0

# Boundary Markers ###########################################################

CUTHERE = b'8<-------- '
ENDFILE = b'END OF FILE\r'
ENDTRANS = b'END OF TRANSMISSION\r'
LOADERCMD = b'\rZLOADER\r'
LOADERACK = b'Z-Bot Firmware Uploader\r\n'
STARTCMD = b'START UPLOAD\r'

# Utility Functions ##########################################################

def lprint(pri,*args):
    if pri >= 9:
        for arg in args:
            print >> sys.stderr, arg,
        print >> sys.stderr
    elif pri >= printlevel:
        for arg in args:
            print arg,
        print

# Serial Port ################################################################

try:
    lprint(0,'Trying /dev/zbot_atc')
    ser = serial.Serial(
    port='/dev/zbot_atc',
    baudrate=57600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
    )
    lprint(0,'Using /dev/zbot_atc')
except:
    try: # this is for in the lab with a missing udev rule
        lprint(0,'Trying /dev/ttyUSB0')
        ser = serial.Serial(
        port='/dev/ttyUSB0',
        baudrate=57600,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        timeout=1
        )
        lprint(0,'Using /dev/ttyUSB0')
    except:
        try: # this is for in the lab with a missing udev rule
            lprint(0,'Trying /dev/ttyUSB1')
            ser = serial.Serial(
            port='/dev/ttyUSB1',
            baudrate=57600,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            bytesize=serial.EIGHTBITS,
            timeout=1
            )
            lprint(0,'Using /dev/ttyUSB1')
        except:
            lprint(9,'ACT not connected')
            sys.exit(1)

ser.isOpen()

# Checksums ##################################################################

adlerMod = 65521 # largest unsigned, 16-bit prime

def adler32(buf):
    a = 1
    b = 0
    for i in range(len(buf)):
        a = (a + ord(buf[i])) % adlerMod
        b = (b + a) % adlerMod
    return b<<16 | a

def adlerCks(s):
    return "%08x" % adler32(s)

# Input/Output Functions #####################################################

def flush():
    l = ser.readline()
    while l != '':
        l = ser.readline()

def sendCut(name):
    out = CUTHERE+name+'\r'
    ser.write(out)

def sendEOF():
    ser.write(ENDFILE)

def sendEOT():
    ser.write(ENDTRANS)

def sendLine(line):
    ser.write(line+'\r')
    x = ser.read(8)
    return x

def sendLines(f):
    flush()
    l = f.readline()
    while l != '':
        cks = adlerCks(l+'\r')
        cksr = sendLine(l)
        if not progargs.ignorecks and (cks != cksr): return False    # abort on error
        l = f.readline()
    return True

def waitForDone():
    i = 60
    while i > 0:
        l = ser.readline()
        if 'DONE\n' in l: return True
        i -= 1
    return False

# Zip File Functions #########################################################

zip = zipfile.ZipFile(progargs.zipfile,'r')
files = zip.namelist()

def zSender():
    lprint(1,"Updating ATC Firmware")
    # manipulate file order to put main.py last
    if 'main.py' in files:
        files.remove('main.py')
        files.append('main.py')
    lprint(0,'Inventory')
    for file in files:
        lprint(0,'  '+file)
    for file in files:
        lprint(0,'Sending ',file)
        x = sendCut(file)
        f = zip.open(file,'r')
        flush()   # flush the input
        if not sendLines(f):
            lprint(9,'Checksum error sending '+file)
            f.close()
            sendEOF()
            sendEOT()
            sys.exit(1)
        f.close()
        sendEOF()
        if not waitForDone():
            lprint(9,'Aborting: target write timeout')
            sys.exit(1)
    f.close()
    sendEOT()
    lprint(1,"Update Complete")
    zip.close()

# Launch Remote Frimware Loader ##############################################

def launchLoader():
    # force an end to a potentially running loader
    ser.write(ENDFILE)
    sendEOF()
    sleep(1)
    sendEOT()
    sleep(1)
    # launch the loader
    lprint(0,'Launching Loader')
    ser.write(LOADERCMD)
    i = 10 # number of 1-second connection attempts
    while i>0:
        sleep(0.950)
        ser.write('\n')
        sleep(0.050)
        if ser.inWaiting():
            line = ser.readline()
            if line == LOADERACK: break
        i -= 1
    if i == 0:
        lprint(9,'Aborting: ATC loader not found')
        sys.exit(1)
    ser.write(STARTCMD)
    lprint(0,'ATC Loader connected')
    flush()   # flush the input

# Version Functions ##########################################################

def verstring2num(s):
    nums = s.strip().split('.')
    return int(nums[0])*1000000+int(nums[1])*1000+int(nums[2])

def ZLoader():
    ser.write('\r')
    val = ser.readline()
    if 'Z-Bot Firmware Uploader' in val:
        return True
    return False

def getATCversion():
    ser.write('VE\r')
    version = ser.readline()
    lprint(0,'ATC VE answer: %s' % version)
    if 'Z-Bot Automatic Tool Changer II' in version:
        version = version.strip().split(' ')
        version = version[5]
    elif version == 'Uploader' or version == '':
            version = ' 0.0.0'
    flush()   # flush the input
    return version

def getZIPversion():
    version = ''
    f = zip.open('version.py')
    l = f.readline()
    while(l != '' and version == ''):
        l=l.strip()
        if 'firmware = ' in l or 'firmware= ' in l or 'firmware=' in l:
            exec(l)
            version = firmware
        l = f.readline()
    f.close()
    return version

# Main program ###############################################################

def main():
    if progargs.bootloader:
        if ZLoader(): sys.exit(0)   # bootloader running
        else: sys.exit(3)           # normal firmware running

    if ZLoader():
        lprint(9,'Boot Loader Mode - Forcing firmware upload')
        launchLoader()
        zSender()
    else:
        atcversion = getATCversion()
        zipversion = getZIPversion()
        lprint(0,'ATC Version ' + atcversion)
        lprint(0,'ZIP Version ' + zipversion)
        if ((verstring2num(atcversion) < verstring2num('2.3.2')) and
            progargs.force == False):
            lprint(9,'PCNC440 Beta ATCs cannot be upgraded with this firmware')
            sys.exit(1)

        if (((verstring2num(atcversion) < verstring2num(zipversion)) and progargs.newest == True) or
            (verstring2num(atcversion) != verstring2num(zipversion)) or
            progargs.force == True):

            if progargs.checkatcversion:
                lprint(0,'ATC firmware needs to be updated')
                sys.exit(2)    # signal caller that the atc needs its firmware updated

            launchLoader()
            zSender()

if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other redirected output
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    main()
    sys.exit(0)
