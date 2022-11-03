# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import time

class Stopwatch():
    '''
    Handy little class
    '''
    def __init__(self):
        self.timestart = time.time()
        self.lapcounter = 0

    def restart(self):
        self.timestart = time.time()

    def lap(self, count=1):
        self.lapcounter += count

    def get_elapsed_seconds(self):
        return time.time() - self.timestart

    def __str__(self):
        return "stopwatch: {:f} seconds, {:d} laps".format(self.get_elapsed_seconds(), self.lapcounter)

