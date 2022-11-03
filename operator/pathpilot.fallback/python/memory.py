# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import subprocess
import re

__totalmb = 0

def get_total_ram_mb():
    '''
    Returns the total amount of RAM in megabytes as an integer
    '''
    # Only do this once, the size of ram can only change across reboots...so just
    # cache the value for any later calls
    global __totalmb
    if __totalmb == 0:
        cmd = "sudo dmidecode -t 17 | grep Size"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (outdata, errdata) = p.communicate()
        if p.returncode == 0:
            pattern = r"""\s*Size:\s*(\d+)\s*MB"""
            mbsize_re = re.compile(pattern, re.I)
            for line in outdata.splitlines():
                m = mbsize_re.search(line)
                if m:
                    __totalmb += int(m.group(1))

        if __totalmb == 0:
            # dmidecode above doesn't work in some virtualized environments
            # try parsing /proc/meminfo
            cmd = "cat /proc/meminfo | grep MemTotal"
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            (outdata, errdata) = p.communicate()
            if p.returncode == 0:
                pattern = r"""\s*MemTotal:\s*(\d+)\s*kB"""
                kbsize_re = re.compile(pattern, re.I)
                for line in outdata.splitlines():
                    m = kbsize_re.search(line)
                    if m:
                        # this doesn't come out exactly like you would expect, e.g. 4096 MB due to some oddities
                        # but it is far closer than 0...
                        __totalmb += int(m.group(1)) / 1024

    return __totalmb

if __name__ == "__main__":
    print "Total MB:", get_total_ram_mb()
