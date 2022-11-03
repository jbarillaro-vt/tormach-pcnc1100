#!/usr/bin/env python

# dump the currently running redis database as sorted [SECTION]key data
# keys with empty "" values are suppressed to keep noise down from empty [tool_descriptions]

import sys
import redis

def _compare_keys(x, y):
    try:
        x = int(x)
    except ValueError:
        xint = False
    else:
        xint = True
    try:
        y = int(y)
    except ValueError:
        if xint:
            return -1
        return cmp(x.lower(), y.lower())
        # or cmp(x, y) if you want case sensitivity.
    else:
        if xint:
            return cmp(x, y)
        return 1


if __name__ == "__main__":
    redis = redis.Redis()

    # test if there is a redis server available
    try:
        response = redis.get(None)
    except:
        print 'failed to connect to redis server'
        sys.exit(-1)

    keys = redis.keys('*')
    # sort the list of keys
    keys.sort()
    for key in keys:
        print '\n[%s]' % key
        if redis.type(key) == "hash":
            # only interested in hash keys
            valpairs = redis.hgetall(key)
            # print sorted numerically by key
            # so tool numbers are in order
            for k in sorted(valpairs, cmp=_compare_keys):
                if len(valpairs[k]):
                    print '%s = "%s"' % (k, valpairs[k])
    sys.exit(0)
