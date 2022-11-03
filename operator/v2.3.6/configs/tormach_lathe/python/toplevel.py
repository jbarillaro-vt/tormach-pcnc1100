# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import redis
import remap

def __init__(self):
    remap.init_stdglue(self)

    self.redis = redis.Redis()
    self.params['_collet_interp_request'] = 0

