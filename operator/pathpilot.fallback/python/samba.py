# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import os
import sys
import subprocess
import re

def restart_samba():
    cmd = "sudo /etc/init.d/smbd restart"
    print cmd
    rc = subprocess.call(cmd, shell=True)


def change_samba_to_user_security():
    filename = '/etc/samba/smb.conf'
    tmpfilename = '/tmp/smb.conf.tmp'

    # preprocess the smb.conf file as SafeConfigParser cannot deal with key=value lines that start with whitespace
    try:
        with open(filename, "r") as source:
            with open(tmpfilename, "w") as target:
                lines = source.readlines()
                outlines = []
                for ll in lines:
                    outlines.append(ll.strip() + '\n')
                target.writelines(outlines)
                source.close()
                target.close()

        # we tried to use the SafeConfigParser and it became a mess because it doesn't
        # understand include = file values or multiples of those.
        # so now we just use regex to understand if we have to add the lines or not.

        update_needed = False
        with open(tmpfilename, "r") as source:
            sourcetext = source.read()

        # does the proper section and key exist?
        matchlist = re.findall(r'^\[global\]\nsecurity.*=.*user', sourcetext, re.MULTILINE)
        if len(matchlist) == 0:
            update_needed = True

            # nuke the standlone line that may have been added by older versions of this script
            # which are ineffective because of their location.  cleans up confusion.
            sourcetext = sourcetext.replace('security = user', '')

        if update_needed:
            with open(tmpfilename, "w") as ff:
                ff.write(sourcetext)
                # now we append a new [global] section header and the new lines to make sure samba sees it.
                ff.write('\n[global]\nsecurity = user\n\n')
                ff.close()

            cmd = "sudo mv {} {}".format(tmpfilename, filename)
            print cmd
            rc = subprocess.call(cmd, shell=True)

            restart_samba()

    except Exception as e:
        msg = "change_samba_to_user_security: an exception of type {0} occured, these were the arguments:\n{1!r}"
        print msg.format(type(e).__name__, e.args)


if __name__ == "__main__":
    change_samba_to_user_security()
    sys.exit(0)
