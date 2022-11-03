#!/usr/bin/env python
#
# Init the ATC flash to accept a firmware load regardless
# of current condition.

import os
import sys
import subprocess
import time

# 5 seconds was enough in observed testing, but be pessimistic
FLUSH_SECS = 7


# paths
FILE_SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
mntpnt = '/media/operator'
rootmntpnt = '/mnt'
path = os.path.join(mntpnt, 'PYBFLASH')


# get the partition, returns None if not found
def getPartition():
    part = None
    mountdata = subprocess.check_output('mount', shell=True)
    mountdata = mountdata.split('\n')
    for line in mountdata:
        if 'PYBFLASH' in line:
            part = line.split()[0]
            print "Found PYBFLASH on", part
            break
    return part


def unmount(path):
    print "Unmounting", path
    rc = subprocess.call('sudo umount ' + path, shell=True)
    if rc != 0:
        print "umount failed with {:d}".format(rc)


def remount(part):
    print "Remounting", path
    rc = subprocess.call('sudo mount ' + part + ' ' + rootmntpnt, shell=True)
    if rc != 0:
        print "mount failed with {:d}".format(rc)

    # give upython some time for housekeeping immediately after a mount
    # 0.5 sec was needed and adequate in all testing, but be pessimistic
    time.sleep(1.0)
    return rc


def initFS(part):
    print "fsck.vfat -a", part
    rc = subprocess.call('sudo fsck.vfat -a ' + part, shell=True)
    if rc == 1:
        print "fsck.vfat fixed things, flushing, and verifying"
        subprocess.call('sync', shell=True)
        time.sleep(FLUSH_SECS) # give board time to flush buffers to flash

        # we run it again to make sure it now returns 0
        print "fsck.vfat -a", part
        rc = subprocess.call('sudo fsck.vfat -a ' + part, shell=True)

    if rc == 0:
        print "fsck.vfat gave a green light"

    return rc


def removeDirs():
    dirlist = os.listdir(rootmntpnt)
    for candidate in dirlist:
        candidate = os.path.join(rootmntpnt, candidate)
        if os.path.isdir(candidate):
            print 'Removing dir {:s}'.format(candidate)
            subprocess.call('sudo rm -rf "{:s}"'.format(candidate), shell=True)
            subprocess.call('sync', shell=True)
            time.sleep(FLUSH_SECS) # give board time to flush buffers to flash


def addLoader():
    print "Adding boot loader"
    subprocess.call('sudo cp {:s} {:s}'.format(os.path.join(FILE_SOURCE_DIR, 'zloader.py'), os.path.join(rootmntpnt, 'main.py')), shell=True)

    subprocess.call('sync', shell=True)
    time.sleep(FLUSH_SECS) # give board time to flush buffers to flash

    subprocess.call('sudo cp {:s} {:s}'.format(os.path.join(FILE_SOURCE_DIR, 'boot.py'), os.path.join(rootmntpnt, 'boot.py')), shell=True)

    subprocess.call('sync', shell=True)
    time.sleep(FLUSH_SECS) # give board time to flush buffers to flash

    # overwrite these just in case they are corrupted; if they are, they contribute to upython belly up
    # with no recovery.
    subprocess.call('sudo cp {:s} {:s}'.format(os.path.join(FILE_SOURCE_DIR, 'machine.atc'), os.path.join(rootmntpnt, 'machine.atc')), shell=True)

    subprocess.call('sync', shell=True)
    time.sleep(FLUSH_SECS) # give board time to flush buffers to flash

    subprocess.call('sudo cp {:s} {:s}'.format(os.path.join(FILE_SOURCE_DIR, 'offset.atc'), os.path.join(rootmntpnt, 'offset.atc')), shell=True)

    subprocess.call('sync', shell=True)
    time.sleep(FLUSH_SECS) # give board time to flush buffers to flash


def fixit():
    rc = 1  # assume failure
    part = getPartition()
    if part != None:
        unmount(path)
        rc = initFS(part)
        if rc == 0:
            rc = remount(part)
            if rc == 0:
                removeDirs()
                addLoader()

                # gracefully unmount so that dirty bit is not set
                unmount(rootmntpnt)
                time.sleep(FLUSH_SECS) # give board time to flush buffers to flash
    else:
        print "Failed to find PYBFLASH"

    return rc


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    rc = fixit()
    sys.exit(rc)
