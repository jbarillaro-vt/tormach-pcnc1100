#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------



import subprocess
import sys
import os.path

class vmcheck():
    def __init__(self):
        self.running_in_vm = False
        self.vendor = ''
        cmd = 'sudo dmidecode -s system-product-name'
        result = self._run_cmd(cmd)
        # look for VirtualBox - add others as required
        if 'VirtualBox' in result:
            self.running_in_vm = True
            self.vendor = 'VirtualBox'
            return

        if 'Parallels Virtual Platform' in result:
            self.running_in_vm = True
            self.vendor = 'Parallels'
            return

        cmd = 'uname -a'
        result = self._run_cmd(cmd)
        # look for VirtualBox - add others as required
        if 'VirtualBox' in result:
            self.running_in_vm = True
            self.vendor = 'VirtualBox'

        result = os.path.isfile("/.dockerenv")
        # we are in docker
        if result:
          self.running_in_vm = True
          self.vendor = 'Docker'

    def _run_cmd(self, cmd):
        result = ''
        try:
            result = subprocess.check_output(cmd, shell=True)
            print '%s: %s' % (cmd, result.strip())
        except subprocess.CalledProcessError:
            print 'Failed to run %s' % cmd
        return result


    def is_virtualized_os(self):
        return self.running_in_vm


    def get_vendor(self):
        return self.vendor


if __name__ == "__main__":
    my_vmcheck = vmcheck()
    if my_vmcheck.is_virtualized_os():
        print "Running in virtualized OS environment. %s" % my_vmcheck.get_vendor()
        sys.exit(1)
    else:
        print "NOT running in virtualized OS environment."
        sys.exit(0)
