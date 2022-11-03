#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
#
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import sys
import os
import subprocess
import string
import re
import inspect


def get_total_physical_ram_mb():
    totalmb = 0
    cmd = "dmidecode -t 17 | grep Size"
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (outdata, errdata) = p.communicate()
    if p.returncode == 0:
        pattern = r"""\s*Size:\s*(\d+)\s*MB"""
        mbsize_re = re.compile(pattern, re.I)
        for line in outdata.splitlines():
            m = mbsize_re.search(line)
            if m:
                totalmb += int(m.group(1))

    return totalmb


if __name__ == "__main__":

    # This whole script needs to be run as sudo because
    #    dmidecode
    #    writing /etc/cgconfig.conf
    #    running cgconfigparser to load in the new cgconfig.conf

    returncode = 1

    # this is the directory where this module code is running from
    program_dir = os.path.dirname(os.path.abspath(inspect.getsourcefile(get_total_physical_ram_mb)))

    totalmb = get_total_physical_ram_mb()

    # Give the utility process jail
    if totalmb <= 1024:
        # This is really tight - give it 200 MB
        jailsize_mb = 200
        jailsize_vm_mb = 750
    elif totalmb <= 2048:
        # A bit more elbow room
        jailsize_mb = 400
        jailsize_vm_mb = 750
    else:
        # Lots of elbow room
        # Give it 25% of total RAM
        jailsize_mb = int(totalmb * 0.25)
        jailsize_vm_mb = max(750, jailsize_mb)

    # cgconfigparser will give vague, unhelpful errors if the physical ram size is higher than
    # the virtual memory size (which includes swap use). Here's what it tells me:
    #
    #    cgconfigparser; error loading /etc/cgconfig.conf: This kernel does not support this feature
    #
    # Nice.
    assert jailsize_mb <= jailsize_vm_mb, "Error in cgconfig.conf logic in choosing memory sizes."

    print "Total RAM: %d MB" % totalmb
    print "Utility CG Size: %d MB" % jailsize_mb
    print "Utility CG VM Size: %d MB" % jailsize_vm_mb

    fullpath = os.path.join(program_dir, "cgconfig.conf.template")
    with open(fullpath, "r") as templatefile:
        cgconfig = templatefile.read()
        cgconfig = string.replace(cgconfig, r"%JAILSIZE_MB%", str(jailsize_mb))
        cgconfig = string.replace(cgconfig, r"%JAILSIZE_VM_MB%", str(jailsize_vm_mb))

        with open("/etc/cgconfig.conf", "w") as cgfile:
            cgfile.write(cgconfig)

        print "/etc/cgconfig.conf updated."

        # Run cgconfigparser to load the file in just in case we changed it
        # We're early enough in the boot up that utility apps for the user aren't running yet
        cmd = "cgconfigparser -l /etc/cgconfig.conf"
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (outdata, errdata) = p.communicate()
        if p.returncode == 0:
            print "cgconfigparser successfully loaded /etc/cgconfig.conf"
            returncode = 0
        else:
            print "cgconfigparser failed with return code %d and output:" % p.returncode
            print outdata
            print errdata

    sys.exit(returncode)
