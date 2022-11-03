#!/usr/bin/env python

import sys
import os
import subprocess
import time
import timer
from iniparse import SafeConfigParser
from iniparse import NoOptionError

if __name__ == "__main__":
    if len(sys.argv) == 2 and os.path.isfile(sys.argv[1]):
        inifilepath = sys.argv[1]

        print "redis-upgrade.py: checking to see if redis rdb file needs to be upgraded to aof"
        print "redis-upgrade.py: config ini filepath:", inifilepath

        parser = SafeConfigParser()
        parser.read(inifilepath)

        # get the arguments for redis server
        args = parser.get('REDIS', 'SERVER_ARGS')
        arglist = args.split()

        # find the redis data directory
        ix = arglist.index('--dir')
        redisdir = os.path.expanduser(arglist[ix+1])

        # verify we parsed it right and it exists
        if os.path.isdir(redisdir):
            # determine the redis server binary name
            try:
                redisbin = parser.get('REDIS', 'SERVER_PATH')
                redisbin = os.path.expanduser(redisbin)
                if not os.path.isfile(redisbin):
                    print "redis-upgrade.py: cannot locate redis server specified by [REDIS] SERVER_PATH value:", redisbin
                    sys.exit(1)
            except NoOptionError:
                redisbin = 'redis-server'

            # is linuxcnc using append only persistence?
            try:
                ix = arglist.index('--appendonly')
                usingAppend = (arglist[ix+1].lower() == 'yes')
            except ValueError:
                usingAppend = False

            if usingAppend:
                print "redis-upgrade.py: redis is configured for appendonly persistence."

                # if the append only .aof file doesn't exist, the dump.rdb file will be ignored
                # and the database will be empty - losing all the data.

                rdbfile = os.path.join(redisdir, 'dump.rdb')
                appendfile = os.path.join(redisdir, 'appendonly.aof')

                # there are 2 situations we need to migrate carefully from the .rdb file to a new .aof file.
                #
                #   1. initial upgrade to a PP version that is using the .aof format
                #
                #      in this case the .aof file won't exist yet
                #
                #   2. the user reverted to an older PP that only uses .rdb files and made some changes.
                #      then they upgraded forward again to a PP version that is using the .aof format.
                #
                #      in this case both the .rdb and .aof files will exist, but the .rdb mtime should
                #      be newer.  in this case we rename the existing .aof file and set it aside never
                #      to be used again (but available as a manual backup in case of disaster)

                if os.path.isfile(rdbfile) and os.path.isfile(appendfile):
                    # both exist. see if the .rdb is newish
                    # for us to trust the .rdb file is really 'new', it has to be at least a minute
                    # newer than the .aof file.  why?  because on graceful shutdown, the redis-server
                    # config attempts to snapshot the data and rewrites a fresh dump.rdb.  So it will
                    # always be pretty close to the .aof file under normal conditions.
                    delta_secs = os.stat(rdbfile).st_mtime - os.stat(appendfile).st_mtime
                    if delta_secs > 60:
                        # .rdb is newer.  assume that it has the most curent data.
                        print "redis-upgrade.py: dump.rdb is newer than appendonly.aof (%d seconds)" % delta_secs
                        print "redis-upgrade.py: saving appendonly.aof to appendonly.aof.backup and migrating data from dump.rdb"
                        appendfilebackup = appendfile + '.backup'
                        if os.path.isfile(appendfilebackup):
                            os.remove(appendfilebackup)
                        os.rename(appendfile, appendfilebackup)

                if os.path.isfile(rdbfile) and not os.path.isfile(appendfile):
                    # Get redis to load up the dump.rdb file and then turn on the append only format
                    # so we don't lose any data.  We ignore all other redis args as we're
                    # just starting it, turning on append, and then stopping it so that the .aof file
                    # is 'seeded' from the dump.rdb.

                    # Start the redis-server
                    cmdline = '{:s} --dir {:s} --dbfilename dump.rdb'.format(redisbin, redisdir)
                    print "redis-upgrade.py: running", cmdline
                    serverproc = subprocess.Popen(cmdline, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

                    # Give it the command to start using aof for persistence
                    watch = timer.Stopwatch()
                    while True and watch.get_elapsed_seconds() < 2*60:
                        time.sleep(0.5)  # give the redis server a chance to init
                        cmdline = '~/tmc/bin/redis-cli config set appendonly yes'
                        print "redis-upgrade.py: running", cmdline
                        try:
                            result = subprocess.check_output(cmdline, shell=True)
                            result = result.strip()
                            print "redis-upgrade.py: ", result
                            if result == 'OK':
                                break
                        except subprocess.CalledProcessError:
                            pass

                    # Now try to get the server to gracefully shutdown.
                    # It will refuse the shutdown command while the initial .aof file is built.
                    # So we loop around trying to shut it down and watching to see if the process
                    # has terminated.
                    watch.restart()
                    while serverproc.poll() == None:
                        time.sleep(1)  # give the redis server a chance to finish the initial .aof file build
                        cmdline = '~/tmc/bin/redis-cli shutdown save'
                        print "redis-upgrade.py: running", cmdline
                        try:
                            result = subprocess.check_output(cmdline, shell=True)
                            result = result.strip()
                            print "redis-upgrade.py: ", result
                        except subprocess.CalledProcessError:
                            pass

                        if watch.get_elapsed_seconds() >= 2*60:
                            print "redis-upgrade.py: error - killing redis-server after 2 minutes"
                            try:
                                serverproc.kill()
                            except:
                                pass

                    serverproc.wait()
                    if serverproc.returncode != 0:
                        print "redis-upgrade.py: redis-server exited with code {:d}".format(serverproc.returncode)

                    print "redis-upgrade.py: redis dump.rdb successfully migrated to appendonly.aof"
                else:
                    print "redis-upgrade.py: nothing to do."
            else:
                print "redis-upgrade.py: redis is NOT configured for appendonly persistence so nothing to do."

            sys.exit(0)

        else:
            print "redis-upgrade.py: redis data directory does not exist:", redisdir
    else:
        print "usage: redis-upgrade.py full-path-to-ini-file"

    sys.exit(1)
