#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


# run this via 'sudo python fstab_use_uuid.py' for it to function properly

# this patches /etc/fstab to use UUIDs instead of /dev/sda1 for '/'
# and /dev/sda2 for swap

import os
import sys
import fileinput
import subprocess

FSTAB = '/etc/fstab'

DEVSDA1 = '/dev/sda1'
sda1_uuid = ''

DEVSDA2 = '/dev/sda2'
sda2_uuid = ''

BLKID_PROGRAM = '/sbin/blkid'

if __name__ == "__main__":
    if os.geteuid() != 0:
        print 'must be run via sudo python %s' % (sys.argv[0])
        exit(1)

    need_to_patch = False

    try:
        with open(FSTAB) as f:
            for line in f:
                if line.startswith(DEVSDA1):
                    print 'found %s - will patch %s' % (DEVSDA1, FSTAB)
                    need_to_patch = True;
                if line.startswith(DEVSDA2):
                    print 'found %s - will patch %s' % (DEVSDA2, FSTAB)
                    need_to_patch = True;
    except Exception, e:
        print 'exception while searching for %s or %s in %s' % (DEVSDA1, DEVSDA2, FSTAB)
        print str(e)
        exit(1)

    if need_to_patch:
        try:
            print 'running %s' % BLKID_PROGRAM
            p = subprocess.Popen([BLKID_PROGRAM], stdout=subprocess.PIPE)
            blkidout, err = p.communicate()
            print blkidout
            uuid_list = blkidout.split('\n')
            #sudo blkid
            #/dev/ramzswap0: TYPE="swap"
            #/dev/sda1: UUID="784079a0-da5e-49d3-8729-c0dcd7b15e3d" TYPE="ext4"
            #/dev/sda2: UUID="cc725fc6-e3cd-4bcb-82a6-34ddeae70d46" TYPE="swap"
            print 'parsing output from ' + BLKID_PROGRAM
            for line in uuid_list:
                if line.startswith(DEVSDA1):
                    partition, uuid, part_type = line.split()
                    print partition + ' ' + uuid
                    sda1_uuid = uuid
                if line.startswith(DEVSDA2):
                    partition, uuid, part_type = line.split()
                    print partition + ' ' + uuid
                    sda2_uuid = uuid
        except Exception, e:
            print str(e)
            exit(1)

        try:
            # CAUTION! everything 'print()ed' in here goes to the file not the console
            for line in fileinput.input(FSTAB, inplace=True):
                if line.startswith(DEVSDA1):
                    # trailing comma after print suppresses newline
                    print '#' + line,
                    # now add line swapping /dev/sda1 for UUID
                    print sda1_uuid + line[9:],
                elif line.startswith(DEVSDA2):
                    print '#' + line,
                    # now add line swapping /dev/sda2 for UUID
                    print sda2_uuid + line[9:],
                else:
                    print line,

        except Exception, e:
            print 'exception while patching %s' % (FSTAB)
            print str(e)
            exit(1)
    else:
        print 'no patch needed in %s' % (FSTAB)

    exit(0)

