##############################################################################
# zloader.py
#
# ATCNG firmware uploader and reflasher
#
# Copyright (c) 2018 Z-Bot, LLC
# All Rights Reserved
# Author: Noel Henson
#
# This file contains functions to upgrade device application firmware.
##############################################################################

'''

Bootloader Overview

This is a simple bootloader. It is meant to be used by PathPilot to update
device firmware. uPy offers no zipfile or other archive support and adding
them would take up a good deal of space.

The firmware is received as one continuous text file with file boundary
markers. The marker must be on a line by itself and have no leading or
following whitespace.

'''

import os
import gc
import pyb
import machine

gc.enable()

# setup uart
UART = 6
BAUD = 57600
STOP = 1
PARITY = None
uart = pyb.UART(UART, BAUD)

# Loader Heartbeat ###########################################################

yellow = pyb.LED(3)

def LEDheartbeat():
    ledtimer = pyb.Timer(10)
    ledtimer.init(freq=4)
    ledtimer.callback(lambda t:yellow.toggle())

# Checksums ##################################################################

adlerMod = 65521

def adler32(buf):
    a = 1
    b = 0
    for i in range(len(buf)):
        a = (a + buf[i]) % adlerMod
        b = (b + a) % adlerMod
    return b<<16 | a

def adlerCks(s):
    return "%08x" % adler32(s)

# File and Transfer Boundaries ###############################################

CUTHERE = b'8<-------- '
ENDFILE = b'END OF FILE'
ENDTRANS = b'END OF TRANSMISSION'

def isCut(line):
    if line[:11] == CUTHERE:
        return True
    else:
        return False

def getFilename(line):
    return line[11:-1]

def isEndFile(line):
    return line[:-1] == ENDFILE

def isEndTrans(line):
    return line[:-1] == ENDTRANS

# File Dumping ###############################################################

def dumpFile(file):
    f = open(file,'rt')
    l = f.readline()
    while l != '':
        uart.write(l)
        l = f.readline()

def dumpFiles():
    files = os.listdir()
    for file in files:
        uart.write(CUTHERE + file + '\n')
        dumpFile(file)
    uart.write(ENDTRANS + '\n')

# Data Transfer ##############################################################

NEWFILETAG = '.new'

filedata = []

def getLine():
    line = b''
    c = b' '
    while(not (c == b'\r')):
        while not uart.any():
            pass
        c = uart.read(1)
        line += c
    return line

def getLineCks():
    line = getLine()
    print(line)
    print(adlerCks(line))
    if line == '': return line # fixme
    uart.write(adlerCks(line))
    return line

def getFile():
    global filedata
    filedata = []
    gc.collect()
    line = getLineCks()
    # gather the data
    while(not (isCut(line) or isEndTrans(line) or isEndFile(line))):
        if gc.mem_free() < 20000: gc.collect()
        filedata.append(line[:-1])
        line = getLineCks()
        if line == '':break
    return line

def getFiles():
    global filedata
    line = getLineCks()
    filename = ''
    while(not isEndTrans(line)):
        if isCut(line):
            filename = getFilename(line)
            filename = filename.decode()
            print('File: '+ filename)
            f = open(filename+NEWFILETAG,'w')
            line = getFile()
            print('writing\r')
            for dataline in filedata:
                f.write(dataline)
            f.close()
            if filename in os.listdir():
                os.remove(filename)
            os.rename(filename+NEWFILETAG,filename)
            os.sync()
            print('done\r')
            uart.write('DONE')
            uart.write('\n')
        else:
            line = getLineCks()
            if line == '': break

def stat_isdir(mode):
    return ((mode & 00170000) == 0040000)

def removeDir(dirname):
    files = os.listdir(dirname)
    for file in files:
        file = dirname + '/' + file
        print(file)
        statobj = os.stat(file)
        if stat_isdir(statobj.st_mode):
            removeDir(file)
        else:
            os.remove(file)
            os.sync()
    os.rmdir(dirname)
    os.sync()

def cleanFiles():
    files = os.listdir()
    whitelist = ('README.txt',
                 'pybcdc.inf',  # may be needed for CDC
                 'boot.py',     # needed to set boot mode
                 'main.py',     # is actually zloader (see below)
                 'machine.atc', # save the machine type
                 'offset.atc')  # save the home offset setting
    for file in files:
        # skip whitelist files if they exist
        if file not in whitelist:
            print(file)
            try:
                statobj = os.stat(file)
                if stat_isdir(statobj.st_mode):
                    removeDir(file)
                else:
                    os.remove(file)
                    os.sync()
            except:
                print('Exception removing ' + file + '; skipping.\r')
    print('Waiting for upload')

def safeLoader():
    os.remove('main.py')
    os.rename('zloader.py','main.py')
    os.sync()

def zloader():
    if __name__ != '__main__': safeLoader()
    LEDheartbeat()
    cleanFiles()
    line = b''
    while line.strip() != b'START UPLOAD':
        uart.write('Z-Bot Firmware Uploader\r\n')
        line = getLine()
    print('Linked with sender')
    getFiles()
    print('Resetting')
    machine.reset()

if __name__ == '__main__': zloader()
