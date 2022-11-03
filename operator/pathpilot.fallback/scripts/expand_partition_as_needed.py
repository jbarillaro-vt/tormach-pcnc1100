#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import sys
import os
import subprocess
import string

#-----------------------------------------------------------------------
# Examine the 3rd partition on the /dev/sda device and if it is still
# original and tiny, conclude that it must be unmodified from the PP 2.0 image
# partition layout. In that case, try to grow it by running growpart and resize2fs.
#

def sync():
    p = subprocess.Popen('sync', shell=True)
    p.wait()


def should_partition_be_expanded():
    p = subprocess.Popen('sudo parted -m /dev/sda print', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out, err) = p.communicate()
    '''
    stdout of the parted command should look like this immediately after installing from a PP 2.0 OS image:
    BYT;
    /dev/sda:120GB:scsi:512:512:msdos:ATA WDC WDS120G2G0A-;
    1:1049kB:14.2GB:14.2GB:ext4::boot;
    2:14.2GB:15.2GB:1049MB:linux-swap(v1)::;
    3:15.2GB:31.0GB:15.7GB:ext4::;

    we carefully inspect the 3rd partition attributes and unless its exactly what we expect, we don't try to expand it
    '''
    if p.returncode == 0:
        outlines = out.splitlines()
        if len(outlines) == 5:
            tokens = outlines[4].split(':')
            if tokens[0] == '3':
                try:
                    endsize = float(string.replace(tokens[2], 'GB', ''))
                    partsize = float(string.replace(tokens[3], 'GB', ''))
                    if endsize >= 30.0 and endsize < 32.0 and partsize >= 15.0 and partsize < 16.0:
                        return True
                except:
                    pass
    return False


def expand_partition():
    sync()
    # sudo growpart /dev/sda 3
    p = subprocess.Popen('sudo growpart /dev/sda 3', shell=True)
    p.wait()
    if p.returncode == 0:
        sync()
        print "/dev/sda3 partition successfully expanded to use rest of available disk."
    else:
        print "growpart failed returning", p.returncode


def should_filesystem_be_expanded():
    p = subprocess.Popen('df --output=source,fstype,size,target /dev/sda3', stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (out, err) = p.communicate()
    '''
    stdout of the df command should look like this immediately after installing from a PP 2.0 OS image or
    restoring from the factory clonezilla image using the Grub recovery menu.
    df --output=source,fstype,size,target /dev/sda3
    Filesystem     Type 1K-blocks Mounted on
    /dev/sda3      ext4  14986712 /
    '''
    if p.returncode == 0:
        outlines = out.splitlines()
        if len(outlines) == 2:
            tokens = outlines[1].split()
            if len(tokens) == 4 and tokens[0] == '/dev/sda3' and tokens[1] == 'ext4' and tokens[3] == '/':
                try:
                    # convert file system size from 1K blocks to GB
                    size = float(tokens[2]) / (1024*1024)
                    if size >= 14.0 and size < 15.0:
                        return True
                except:
                    pass
    return False


def expand_filesystem():
    sync()
    # sudo resize2fs /dev/sda3
    p = subprocess.Popen('sudo resize2fs /dev/sda3', shell=True)
    p.wait()
    if p.returncode == 0:
        sync()
        print "/dev/sda3 partition successfully expanded to use rest of available disk."
    else:
        print "resize2fs failed returning", p.returncode


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    if 'testrun' in sys.argv:
        print "Testing to see if we would try to expand partition..."
        # tidy image is asking us if the current partition state is such that we would
        # try to expand it the next time we run.
        if should_partition_be_expanded() and should_filesystem_be_expanded():
            print "Yup, partition is small so we would try."
            sys.exit(0)  # good to go!
        else:
            print "Nope, partition doesn't match what we expect."
            sys.exit(1)

    else:
        # are we in the middle of trying to make an r-drive source image and don't want
        # the expansion to occur?  this is indicated by the presence of a file
        FLAG_FILE = os.path.join(os.environ['HOME'], 'prevent-partition-expand')
        if not os.path.exists(FLAG_FILE):
            print "Checking if /dev/sda3 partition should be expanded in place"
            if should_partition_be_expanded():
                print "Trying to expand /dev/sda3 partition"
                expand_partition()
            else:
                print "No need to expand /dev/sda3 partition (or it looks different than we expected)."

            print "Checking if /dev/sda3 filesystem should be expanded in place"
            if should_filesystem_be_expanded():
                print "Trying to expand /dev/sda3 filesystem"
                expand_filesystem()
            else:
                print "No need to expand /dev/sda3 filesystem (or it looks different than we expected)."

        else:
            print "Skipping expansion of /dev/sda3 due to existence of flag file: {:s}".format(FLAG_FILE)

    sys.exit(0)

