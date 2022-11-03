#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------


import sys
import os
import subprocess
import string
from iniparse import SafeConfigParser
from iniparse import NoOptionError
import time


def add_mac_to_nmconf(mac):
    # Edit /etc/NetworkManager/NetworkManager.conf and add eth0 mac address to the
    #   no-auto-default line (if it doesn't exist already due to previous flip/
    #   flops of configs)

    parser = SafeConfigParser()
    parser.read("/etc/NetworkManager/NetworkManager.conf")

    value = parser.get('main', 'no-auto-default')
    value = value.strip()
    print "Before: %s" % value
    if len(value) > 0:
        if string.find(value, mac) == -1:
            # mac not listed so we need to add it
            if not value.endswith(','):
                value += ","
            value += mac + ","
    else:
        value = mac + ","

    print "After: %s" % value
    parser.set('main', 'no-auto-default', value)

    with open("/etc/NetworkManager/NetworkManager.conf", "w") as f:
        parser.write(f)


def add_all_to_nmconf():
    # Edit /etc/NetworkManager/NetworkManager.conf and add * to the
    # no-auto-default line

    parser = SafeConfigParser()
    parser.read("/etc/NetworkManager/NetworkManager.conf")
    parser.set('main', 'no-auto-default', '*')
    with open("/etc/NetworkManager/NetworkManager.conf", "w") as f:
        parser.write(f)


def get_interface_mac_address(iface):
    # Get the network status by running nmcli and block waiting for it to complete
    nmproc = subprocess.Popen(["/usr/bin/nmcli",
                               "--terse",
                               "--fields",
                               "GENERAL",
                               "device",
                               "list",
                               "iface",
                               iface], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outdata, errdata = nmproc.communicate()
    if nmproc.returncode == 0:

        lines = outdata.splitlines()
        for ll in lines:
            # nmcli doesn't follow consistent escaping rules for the --terse option. If values contain colons, they aren't escaped
            # in this output.
            values = ll.partition(':')
            if values[0] == "GENERAL.HWADDR":
                mac_addr = values[2].strip()
                return mac_addr

    return None


def get_filtered_interface_file():
    '''
    Read /etc/network/interfaces file contents and filter out any
    stanzas for auto eth0 or iface eth0
    Return a tuple where
        tuple[0] = string containing the filtered result
        tuple[1] = boolean where True if eth0 was listed and filtered out
    '''
    buffer = ""
    filtered_eth0 = False

    with open("/etc/network/interfaces", "r") as f:
        line = f.readline()
        while len(line) != 0:      # while not EOF
            sline = line.strip()
            # pass blank lines and comments through
            if len(sline) == 0 or sline[0] == '#':
                buffer += line
                line = f.readline()   # read the next line
            else:
                # must be the start of a stanza
                #
                # look for auto eth0 or iface eth0
                # if not, just copy over the stanza as is
                # if present, delete them and add our own controlled versions
                words = string.split(sline)
                if len(words) >= 2 and words[0] == "auto" and words[1] == "eth0":
                    # these are always 1-line stanzas so just skip it
                    line = f.readline()   # read the next line
                elif len(words) >= 2 and words[0] == "iface" and words[1] == "eth0":
                    # start of iface stanza - skipping the entire stanza
                    while True:
                        line = f.readline()   # read the next line
                        # end of stanza is first line that doesn't start with whitespace
                        if len(line) > 0 and line[0] in (' ', '\t'):
                            continue
                        break

                    filtered_eth0 = True
                else:
                    # must be some other stanza - pass it through unmodified
                    buffer += line
                    while True:
                        line = f.readline()   # read the next line
                        if len(line) > 0 and line[0] in (' ', '\t'):
                            buffer += line
                            continue
                        break

    return (buffer, filtered_eth0)


def set_ethernet_method():
    # Edit /etc/network/interfaces and add the following info if they don't exist already
    #
    # auto eth0
    # iface eth0 inet static
    #     address 10.10.10.9
    #     netmask 255.255.255.0
    #     network 10.10.10.0
    #     broadcast 10.10.10.255
    #     gateway 0.0.0.0
    #

    buffer, filtered_eth0 = get_filtered_interface_file()

    if filtered_eth0:
        print "already setup for machine control by eth0 so not doing anything."

    else:
        # Now just add the two stanzas we need.
        buffer += "auto eth0\n"
        buffer += "iface eth0 inet static\n    address 10.10.10.9\n    netmask 255.255.255.0\n    network 10.10.10.0\n    broadcast 10.10.10.255\n    gateway 0.0.0.0\n"

        print "Updated /etc/network/interfaces file is:"
        print "----\n"
        print buffer
        print "----\n"

        mac = get_interface_mac_address('eth0')  #  AA:BB:CC:DD:EE:FF form, all uppercase

        print "Stopping NetworkManager service"
        result = subprocess.call("sudo service network-manager stop", shell=True)

        with open("/etc/network/interfaces", "w") as f:
            f.write(buffer)

        # Scan the /etc/NetworkManager/system-connections files for any that are using
        # mac address of eth0.  If found, delete them.
        print "Scanning NetworkManager connections for any that use eth0"
        dirlisting = os.listdir("/etc/NetworkManager/system-connections")
        for filename in dirlisting:
            filepath = os.path.join("/etc/NetworkManager/system-connections", filename)
            if os.path.isfile(filepath):
                print "Checking '%s'" % filepath
                parser = SafeConfigParser()
                parser.read(filepath)
                value = parser.get('connection', 'type')   # 802-3-ethernet
                if value.strip() == "802-3-ethernet":
                    try:
                        value = parser.get('802-3-ethernet', 'mac-address')
                        value = value.strip()
                        if string.find(value, mac) != -1:
                            print "Deleting eth0 NetworkManager connection file: '%s'" % filepath
                            os.remove(filepath)

                    except NoOptionError:
                        # this connection is generic and can apply to any wired ethernet interface
                        # as it isn't scoped down to just a specific mac so have to delete it.
                        print "Deleting generic ethernet NetworkManager connection file: '%s'" % filepath
                        os.remove(filepath)

        add_all_to_nmconf()

        print "Restarting NetworkManager service"
        result = subprocess.call("sudo service network-manager restart", shell=True)

        # Pause a little until we know NetworkManager is up and ready for queries
        # before returning to caller.
        print "Pausing for 5 seconds for network settings to stabilize"
        time.sleep(5)


def set_db25parallel_method():
    # This means we are releasing eth0 from our control and letting
    # the user configure it.
    #
    # Edit /etc/network/interfaces and remove the auto eth0 and iface eth0 stanzas

    buffer, filtered_eth0 = get_filtered_interface_file()

    if not filtered_eth0:
        print "already setup for machine control by db25 parallel so not doing anything."

    else:
        print "Updated /etc/network/interfaces file is:"
        print "----\n"
        print buffer
        print "----\n"

        print "Stopping NetworkManager service"
        result = subprocess.call("sudo service network-manager stop", shell=True)

        with open("/etc/network/interfaces", "w") as f:
            f.write(buffer)

        add_all_to_nmconf()

        print "Restarting NetworkManager service"
        result = subprocess.call("sudo service network-manager restart", shell=True)

        # Pause a little until we know NetworkManager is up and ready for queries
        # before returning to caller.
        time.sleep(2)


def set_comm_method(comm_method):
    if comm_method == 'ethernet':
        set_ethernet_method()
    elif comm_method == 'db25parallel':
        set_db25parallel_method()


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    if len(sys.argv) != 2 or sys.argv[1] not in ('ethernet', 'db25parallel'):
        print "set_comm_method.py [ethernet | db25parallel]\n\nmust be run with sudo to enable changing system configuration\n"
        sys.exit(1)

    print "set_comm_method.py %s" % sys.argv[1]
    set_comm_method(sys.argv[1])
    sys.exit(0)
