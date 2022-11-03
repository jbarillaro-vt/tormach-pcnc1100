# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import subprocess

class halcmd():
    def __init__(self):
        pass

    def setp(self, p, val, verbose=False):

        # exec halcmd for each item

        try:
            #gcmd = 'halcmd getp %s' % (p)
            #pipe = subprocess.Popen([gcmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            #out = pipe.communicate()[0]
            #print('%s was: %s' % (p, str.strip(out)))
            cmd = 'halcmd setp %s %.4f' % (p, val)
            print cmd
            code = subprocess.call([cmd], shell=True)
            # must wait for change to take effect
            #time.sleep(0.1)
            #pipe = subprocess.Popen([gcmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            #out = pipe.communicate()[0]
            #print('%s is now: %s' % (p, str.strip(out)))
        except OSError:
            print("Could not run: '%s'" % (cmd))
            return -1

        return code

    def source(self, filename, verbose=False):

        # exec halcmd for the filename provided

        try:
            cmd = 'halcmd'
            if verbose:
                cmd += ' -v'
            cmd += ' source %s' % filename
            print cmd
            code = subprocess.call([cmd], shell=True)
        except OSError:
            print("Could not run: '%s'" % (cmd))
            return -1

        return code