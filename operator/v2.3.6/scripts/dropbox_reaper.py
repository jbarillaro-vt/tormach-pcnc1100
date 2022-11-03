#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import sys
import os
import subprocess
import time
import signal

SLEEP_HOURS = 1

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print "%s dropbox_reaper.py: %s" % (timestamp, msg)


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    log("starting")

    HOME_DIR = os.getenv('HOME')
    dropbox_path = os.path.join(HOME_DIR, "dropbox.py")

    while True:
        time.sleep(SLEEP_HOURS*60*60)

        if os.path.isfile(dropbox_path) and os.access(dropbox_path, os.X_OK):
            try:
                # read dropbox pid
                with open(os.path.join(HOME_DIR, ".dropbox", "dropbox.pid"), "r") as f:
                    dropbox_pid = int(f.read())

                log("woke up to restart dropbox daemon to combat memory leaks - stats on existing dropbox process (if still alive)")

                # this will simply output to stdout which will get captured in the log - that's the
                # only purpose.
                subprocess.call("ps h --pid %s -o pid,cmd,rss,vsz,cputime" % dropbox_pid, shell=True)

                # Try to gracefully restart it before pulling out the sledgehammer.
                log("stopping dropbox")
                p = subprocess.Popen("python %s stop" % dropbox_path, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                t1 = time.time()
                while p.poll() == None and (time.time() - t1) < 30:
                    time.sleep(1)
                if p.poll() == None:
                    # pull out the sledgehammer
                    log("dropbox unresponsive to stop command, terminating instead.")
                    try:
                        p.kill()
                    except OSError:
                        # somewhat expected if there is a race condition, the pid may be stale
                        pass

                    try:
                        os.kill(dropbox_pid, signal.SIGKILL)
                    except OSError:
                        # somewhat expected if there is a race condition, the pid may be stale
                        pass

                # pause a bit to give the kernel vm system time to recover if it was in a bad state
                time.sleep(15)

                # Gracefully try to start it
                log("starting dropbox")
                p = subprocess.Popen("python %s start" % dropbox_path, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                t1 = time.time()
                while p.poll() == None and (time.time() - t1) < 30:
                    time.sleep(1)
                if p.poll() == None:
                    log("dropbox unresponsive to start command, will retry next time we wake up.")
                else:
                    # pause for a little bit to let dropbox process get started before we log its new pid and initial stats
                    time.sleep(15)

                    # refresh pid
                    with open(os.path.join(HOME_DIR, ".dropbox", "dropbox.pid"), "r") as f:
                        dropbox_pid = f.read()

                    # this will simply output to stdout which will get captured in the log - that's the
                    # only purpose.
                    log("stats on new dropbox process")
                    subprocess.call("ps h --pid %s -o pid,cmd,rss,vsz,cputime" % dropbox_pid, shell=True)

            except Exception:
                ex = sys.exc_info()

                # wrap this just in case something dies trying to log
                try:
                    log("exception caught - " + ex[1].message)
                except:
                    pass
        else:
            log("dropbox not installed (yet), reaper crawling back into bed for a nap.")
