#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------


'''
test cases
  - wifi password suddenly changes
  - wifi ssid changes after old connections are already defined
  - wlan adapter burns out and wlan1 is swapped and becomes something different
'''

# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

import os
import subprocess
import inspect
import random
import string

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import glib
import uuid
import time

import asyncwork
import nmcliparse


'''
These are some command and sample outputs which helped with the logic below.

nmcli --terse --fields SSID,BSSID,MODE,FREQ,RATE,SIGNAL,SECURITY,WPA-FLAGS,DEVICE,ACTIVE,DBUS-PATH device wifi list iface wlan0

'Tormach':Infrastructure:2437 MHz:54 MB/s:87:WPA2:(none):wlan0:no:/org/freedesktop/NetworkManager/AccessPoint/0
'Tormach':Infrastructure:2412 MHz:54 MB/s:54:WPA2:(none):wlan0:no:/org/freedesktop/NetworkManager/AccessPoint/1
'Tormach':Infrastructure:2462 MHz:54 MB/s:57:WPA2:(none):wlan0:no:/org/freedesktop/NetworkManager/AccessPoint/2
'Tormach-Guest':Infrastructure:2412 MHz:54 MB/s:64::(none):wlan0:no:/org/freedesktop/NetworkManager/AccessPoint/5
'Tormach-Guest':Infrastructure:2462 MHz:54 MB/s:52::(none):wlan0:no:/org/freedesktop/NetworkManager/AccessPoint/4
'Tormach-Guest':Infrastructure:2437 MHz:54 MB/s:72::(none):wlan0:yes:/org/freedesktop/NetworkManager/AccessPoint/3


nmcli --terse --fields NAME,UUID,TYPE,TIMESTAMP,TIMESTAMP-REAL,AUTOCONNECT,READONLY,DBUS-PATH con list

Wired Connection:d55cca5c-a621-404b-86fc-b3e3ea4daddf:802-3-ethernet:1487369750:Fri 17 Feb 2017 04\:15\:50 PM CST:yes:no:/org/freedesktop/NetworkManager/Settings/2
WifiJohn\:wow\:Test1:7c4de585-c9ef-4f64-8842-6029fb7b20f4:802-11-wireless:1487369750:Fri 17 Feb 2017 04\:15\:50 PM CST:yes:no:/org/freedesktop/NetworkManager/Settings/6
WifiJohnTest1:0a9f4cbb-7143-4741-b980-0b92bbe02667:802-11-wireless:1487369314:Fri 17 Feb 2017 04\:08\:34 PM CST:yes:no:/org/freedesktop/NetworkManager/Settings/5
WifiJohnTest1:14e74dd0-c3f3-4ba1-a5ee-e223042b8949:802-11-wireless:1487369304:Fri 17 Feb 2017 04\:08\:24 PM CST:yes:no:/org/freedesktop/NetworkManager/Settings/4

for each one of those which are wifi, run this on it to get all the details:

    nmcli con list uuid 7c4de585-c9ef-4f64-8842-6029fb7b20f4

then match up these strings to the list - then you have the data you need to issue the connect command

connection.autoconnect:yes
802-11-wireless.ssid:'Tormach-Guest'

nmcli con up uuid CONNECTIONUUID

do not do this - it always creates a new connection (and the connection name isn't unique!)
nmcli device wifi connect Tormach-Guest password PASSWORD iface wlan0 name WifiJohnTest1

Can check on active connections using this
If we issue an nmcli con up on an active one, it seems to bounce it which may be undesirable
nmcli --terse --fields NAME,UUID,DEVICES,STATE,DEFAULT,DEFAULT6,VPN,ZONE,DBUS-PATH,CON-PATH,SPEC-OBJECT,MASTER-PATH con status
'''


class NetworkInfo():
    def __init__(self, wifidict, ethiface_list):
        self.wifidict = wifidict             # Key will be ssid and value is WifiStatus object
        self.ethiface_list = ethiface_list   # List of EthernetInterface objects


class WifiStatus():
    def __init__(self, ssid=None, bssid=None, signallevel=None, authtype=None, iface=None, status=None):
        self.ssid = ssid
        self.bssid = bssid
        self.signallevel = signallevel
        self.authtype = authtype
        self.iface = iface
        self.status = status
        self.uuid = None
        self.autoconnect = ""


class EthernetInterface():
    def __init__(self, iface=None, status=None, ipaddr=None):
        self.iface = iface
        self.iface_displayname = "%s (ethernet)" % iface
        self.macaddr = None
        self.status = status
        self.ipaddr = ipaddr
        self.connection_uuid = None    # only valid if a defined connection exists for this ethernet interface
        self.autoconnect = ""


class Connection():
    ''' These are just wired ethernet connectons'''
    def __init__(self, name, uuid=None, autoconnect=None):
        self.name = name
        self.uuid = uuid
        self.autoconnect = autoconnect
        self.macaddr = None

    def __str__(self):
        return "Name: '%s', UUID: %s, AutoConnect: %s" % (self.name, self.uuid, self.autoconnect)


class WifiConnection(Connection):
    ''' Wifi connections have more attributes'''
    def __init__(self, name, uuid=None, autoconnect=None, ssid=None, bssid=None):
        Connection.__init__(self, name, uuid, autoconnect)
        self.ssid = ssid
        self.bssid = bssid

    def __str__(self):
        return "Name: '%s', SSID: %s, BSSID: %s, UUID: %s, AutoConnect: %s" % (self.name, self.ssid, self.bssid, self.uuid, self.autoconnect)


def is_eth0_in_etcinterfaces():
    f = open("/etc/network/interfaces", "r")
    try:
        for line in f:
            line = line.strip()
            if len(line) > 0 and line[0] != '#' and string.find(line, "iface eth0") != -1:
                return True
    finally:
        f.close()

    return False


def nmcli_networklist_runner(workercontext):

    wifidict = {}   # key is ssid, value is a WifiStatus object

    # This just scans for SSIDs using each wifi interface.
    # It has nothing to do with nmcli defined 'connections'.
    #
    # Keep trying wlan0, wlan1, wlan2, etc. until nmcli returns an error.
    iface_number = 0
    while True:
        # Get the network status by running nmcli and block waiting for it to complete
        iface = "wlan%d" % iface_number
        iface_number += 1
        nmproc = subprocess.Popen(["/usr/bin/nmcli",
                                   "--terse",
                                   "--fields",
                                   "SSID,BSSID,MODE,FREQ,RATE,SIGNAL,SECURITY,WPA-FLAGS,DEVICE,ACTIVE,DBUS-PATH",
                                   "device",
                                   "wifi",
                                   "list",
                                   "iface",
                                   iface], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outdata, errdata = nmproc.communicate()

        if nmproc.returncode == 0:
            lines = outdata.splitlines()

            for ll in lines:
                values = nmcliparse.parse_output_line(ll)

                ws = WifiStatus(values[0], values[1], values[5], values[6], iface)
                ws.ssid = ws.ssid[1:-1]    # slice of the leading and trailing ' characters from the name
                if ws.authtype == '':
                    ws.authtype = "None"

                # For a single wifi network with multiple access points, the SSID and auth type will be the same,
                # but each will have a unique BSSID and Signal Strength.
                # but for most people I think this would just be confusing. When you add a new wifi
                # connection, you can specify a BSSID, but you can also leave it blank (which then presumably
                # joins the AP with the strongest signal level - and hops between them if you were to roam
                # around on a laptop)
                #
                try:
                    # replace the object if we have a higher signal level
                    if wifidict[ws.ssid].signallevel < ws.signallevel:
                        wifidict[ws.ssid] = ws
                except KeyError:
                    # add the new wifi to the dict
                    wifidict[ws.ssid] = ws

            # For testing purposes, create a bunch of fake ones...
            # Randomnly adjust how many of these to force lots of row changes in the liststore
            #
            #for ix in range(random.randint(5, 20)):
            #    ws = WifiStatus("Fake Net %d" % ix, "bssid", "%d" % (50+ix), "WEP")
            #    wifidict[ws.ssid] = ws

        else:
            break   # nmcli failed so assume its because we're out of wlan interfaces to enumerate


    # This just lists available wired ethernet interfaces and gets information on each.
    # It has nothing to do with nmcli defined 'connections'.
    #
    # Keep trying eth1, eth2, eth3, until nmcli returns an error.

    # If we are using eth0 for machine control, we don't want to list it.
    # But if we are using a mesa card for machine control, we do want to list it.

    # if eth0 is listed in /etc/network/interfaces then we must be using it for machine control
    # as all other networking is handled by NetworkManager which stores its info
    # in /etc/NetworkManager
    iface_number = 0
    if is_eth0_in_etcinterfaces():
        iface_number = 1

    ethlist = []
    while True:
        # Get the network status by running nmcli and block waiting for it to complete
        iface = "eth%d" % iface_number
        iface_number += 1
        nmproc = subprocess.Popen(["/usr/bin/nmcli",
                                   "--terse",
                                   "--fields",
                                   "GENERAL,IP4,DHCP4,CONNECTIONS",
                                   "device",
                                   "list",
                                   "iface",
                                   iface], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outdata, errdata = nmproc.communicate()

        if nmproc.returncode == 0:
            lines = outdata.splitlines()

            eth = EthernetInterface(iface)

            for ll in lines:

                # nmcli doesn't follow consistent escaping rules for the --terse option. If values contain colons, they aren't escaped
                # in this output so don't bother trying to call nmcliparse.parse_output_line()
                values = ll.partition(':')

                if values[0] == "GENERAL.STATE":
                    if values[2] == "100 (connected)":
                        eth.status = "Connected"
                elif values[0] == "GENERAL.HWADDR":
                    eth.macaddr = values[2].strip()
                elif values[0] == "CONNECTIONS.AVAILABLE-CONNECTIONS[1]":
                    # not every device will have this, it only shows up if there already is a connection
                    # defined that uses this interface.
                    names = values[2].partition('|')
                    eth.connection_uuid = names[0].strip()
                    eth.iface_displayname = names[2].strip()

            ethlist.append(eth)

        else:
            break   # nmcli failed so assume its because we're out of eth interfaces to enumerate


    # Get all the defined connections regardless of state (active or not)
    connlist = nmcli_connectionlist_builder()
    for con in connlist:
        if isinstance(con, WifiConnection):
           if con.ssid in wifidict:
                # found a matching ssid so now we know which connection uuid to use instead of creating a new one
                wifidict[con.ssid].uuid = con.uuid
                wifidict[con.ssid].autoconnect = con.autoconnect
        else:
            for eth in ethlist:
                if con.macaddr == eth.macaddr:
                    eth.autoconnect = con.autoconnect
                    break

    # For the SSIDs, we might already be connected to some of them.
    # Ask nmcli to list the status of its "active connections" and see if any have matching UU
    # Figure out which ssid's may already be connected.
    # nmcli --terse --fields NAME,UUID,DEVICES,STATE,DEFAULT,DEFAULT6,VPN,ZONE,DBUS-PATH,CON-PATH,SPEC-OBJECT,MASTER-PATH con status

    nmproc = subprocess.Popen(["/usr/bin/nmcli",
                               "--terse",
                               "--fields",
                               "NAME,UUID,DEVICES,STATE,DEFAULT,DEFAULT6,VPN,ZONE,DBUS-PATH,CON-PATH,SPEC-OBJECT,MASTER-PATH",
                               "con",
                               "status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outdata, errdata = nmproc.communicate()

    if nmproc.returncode == 0:
        lines = outdata.splitlines()
        for activecon in lines:
            values = nmcliparse.parse_output_line(activecon)

            # we don't know what ssid this active connection uses - look it up linking the uuid to wifistatus
            for con in connlist:
                if con.uuid == values[1]:
                    # found the matching connection definition
                    if isinstance(con, WifiConnection):
                        # if a wifi connection is activated, we should have a matching ssid from the wifi list above
                        # but it isn't guaranteed. saw the chipset lose its mind once on this in testing.
                        # (how can you be connected, but not see the same wifi network when listing?)
                        if con.ssid in wifidict:
                            # found a matching ssid so now we know which connection uuid it uses
                            if values[3] == 'activated':
                                wifidict[con.ssid].status = "Connected"

    workercontext.final_result(NetworkInfo(wifidict, ethlist))


def nmcli_connectionlist_builder():
    # Create a list of Connection and WifiConnection objects that NewtorkManager is aware of
    #
    # Have nmcli list all the defined network connections.
    # Then for each of those, run another nmcli to get their properties.
    # That will show the ssid for each wireless connection (it isn't available when listing
    # the defined network connections)
    # From both of those, piece together a WifiConnection object

    # Get the connection list by running nmcli and block waiting for it to complete
    nmproc = subprocess.Popen(["/usr/bin/nmcli",
                               "--terse",
                               "--fields",
                               "NAME,UUID,TYPE,TIMESTAMP,TIMESTAMP-REAL,AUTOCONNECT,READONLY,DBUS-PATH",
                               "con",
                               "list"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    outdata, errdata = nmproc.communicate()

    connlist = []

    if nmproc.returncode == 0:
        lines = outdata.splitlines()

        for ll in lines:
            tokenlist = nmcliparse.parse_output_line(ll)

            con = None
            if tokenlist[2] == "802-3-ethernet":
                con = Connection(tokenlist[0], tokenlist[1])
            elif tokenlist[2] == "802-11-wireless":
                con = WifiConnection(tokenlist[0], tokenlist[1])

            if con is not None:
                # Run another nmcli for this connection to get the ssid of the connection. We specify which
                # connection to get details for by using its UUID.

                nmprocdetails = subprocess.Popen(["/usr/bin/nmcli",
                                                  "--terse",
                                                  "con",
                                                  "list",
                                                  "uuid",
                                                  con.uuid], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                outdata2, errdata2 = nmprocdetails.communicate()

                if nmprocdetails.returncode == 0:

                    # look for   802-11-wireless.ssid:'name'
                    #            connection.read-only
                    #            connection.autoconnect

                    detaillines = outdata2.splitlines()
                    for detailline in detaillines:

                        # nmcli doesn't follow consistent escaping rules for the --terse option. If values contain colons, they aren't escaped
                        # in this output so don't bother trying to call nmcliparse.parse_output_line()

                        valuetuple = detailline.partition(':')

                        if valuetuple[0] == "802-11-wireless.ssid":
                            con.ssid = valuetuple[2][1:-1]    # slice off the leading and trailing ' characters from the ssid name

                        elif valuetuple[0] == "connection.autoconnect":
                            if valuetuple[2] == "yes":
                                con.autoconnect = "Enabled"

                        elif valuetuple[0] == "connection.read-only":
                            if valuetuple[2] == "yes":
                                # this connection is the private, read-only 10.10.10.x interface we use
                                # for machine control so don't include this connection in the list
                                con = None
                                break

                        elif valuetuple[0] in ("802-3-ethernet.mac-address", "802-11-wireless.mac-address"):
                            con.macaddr = valuetuple[2].strip()

                    if con is not None:
                        connlist.append(con)

    return connlist



def nmcli_connect_runner(**connectargs):
    #
    # This is a mess due to the way nmcli works.
    #
    # We can only tell nmcli to bring up or down defined network connections (as created by the
    # application nm-connection-editor).
    #
    # But users don't think of that. They just think in terms of SSID and signal strength and select
    # an SSID to connect with.
    #
    # And further complicating it is that nmcli can't create new network connection definitions
    # for wired ethernet interfaces - only for wifi networks.
    #
    # So here is how we bridge all this to get to "it just works" land.
    #
    # If the user selected an SSID and wants to connect to it
    #  - if there is an existing defined nmcli connection that uses that SSID, we tell nmcli to bring it up (or down)
    #  - if there is not, we tell nmcli to create a new connection and assume it will be dhcp and auto-connect
    #
    # If the user selected a wired ethernet device and wants to connect it
    #  - if there is an existing defined nmcli connection that uses the ethernet device, we tell nmcli to bring it up (or down)
    #  - if there is not, we have to create a new connection definition behind the back of network manager
    #    by writing a proper connection file to /etc/NetworkManager/system-connections assuming dhcp and auto-connect
    #    then restart the network manager service for it to realize the new connection
    #
    # nmcli really has very little knowledge of the classic network "interface" names (eth0, eth1) and
    # instead uses mac addresses.  so that's why some of the focus on mac addresses in here.
    #

    if "uuid" in connectargs:
        # easy case - there is an nmcli connection definition so we just bring that up/down by uuid.

        if connectargs["action"] == "Connect":
            # Bring up the connection by running
            #     nmcli con up uuid CONNECTIONUUID --timeout 30
            # Could take 30 seconds to timeout  (default is 90!)
            nmcli = subprocess.Popen(["/usr/bin/nmcli",
                                      "con",
                                      "up",
                                      "uuid",
                                      connectargs["uuid"],
                                      "--timeout",
                                      "30"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            # Bring down the connection by running
            #     nmcli con down uuid CONNECTIONUUID
            nmcli = subprocess.Popen(["/usr/bin/nmcli",
                                      "con",
                                      "down",
                                      "uuid",
                                      connectargs["uuid"]], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        outdata, errdata = nmcli.communicate()

        result = (nmcli.returncode == 0)

    else:
        # damn - we need to create a connection here.  how we do that is different between
        # wifi and wired ethernet.

        # Makes no sense to disconnect since we would already have a network connection definition
        assert connectargs["action"] == "Connect"

        if "ssid" in connectargs:
            # wireless connection
            #
            # nmcli device wifi connect Tormach-Guest password PASSWORD iface wlan0 name WifiJohnTest1
            #
            # Could take 30 seconds to timeout  (default is 90!)
            if "password" in connectargs:
                nmcli = subprocess.Popen(["/usr/bin/nmcli",
                                          "device",
                                          "wifi",
                                          "connect",
                                          connectargs["ssid"],
                                          "password",
                                          connectargs["password"],
                                          "iface",
                                          connectargs["iface"],
                                          "name",
                                          "Wifi " + connectargs["ssid"],
                                          "--timeout",
                                          "30"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            else:
                nmcli = subprocess.Popen(["/usr/bin/nmcli",
                                          "device",
                                          "wifi",
                                          "connect",
                                          connectargs["ssid"],
                                          "iface",
                                          connectargs["iface"],
                                          "name",
                                          "Wifi " + connectargs["ssid"],
                                          "--timeout",
                                          "30"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            outdata, errdata = nmcli.communicate()

            result = (nmcli.returncode == 0)

        else:
            # wired ethernet connection

            filename = connectargs["iface"] + "-dhcp"

            # we don't expect spaces in interface names which would make mess of a filename...
            assert filename.find(' ') == -1

            # write a temp file and then limit the sudo work to a mv and a service restart.
            try:
                confile = open(filename, "w")
                confile.write("[802-3-ethernet]\n")
                confile.write("duplex=full\n")
                confile.write("mac-address=%s\n\n" % connectargs["macaddr"])
                confile.write("[connection]\n")
                confile.write("id=%s\n" % filename)
                confile.write("uuid=%s\n" % uuid.uuid4())
                confile.write("type=802-3-ethernet\n\n")
                confile.write("[ipv6]\n")
                confile.write("method=auto\n\n")
                confile.write("[ipv4]\n")
                confile.write("method=auto\n\n")
            finally:
                confile.close()

            try:
                subprocess.check_output("sudo mv %s /etc/NetworkManager/system-connections/%s" % (filename, filename), shell=True)
                subprocess.check_output("sudo chmod go-rw /etc/NetworkManager/system-connections/%s" % filename, shell=True)
                subprocess.check_output("sudo chown root:root /etc/NetworkManager/system-connections/%s" % filename, shell=True)
                subprocess.check_output("sudo service network-manager restart", shell=True)

                # Give the network manager a bit of time to restart, otherwise the user gets anxious because
                # during the restart, the wifi list becomes blank and takes a bit to come back...
                time.sleep(8)

            except subprocess.CalledProcessError:
                result = False

            result = True

    connectargs["workercontext"].final_result(result)


def nmcli_connectionlist_runner(workercontext):
    connlist = nmcli_connectionlist_builder()
    workercontext.final_result(connlist)


class NetConfig():

    def __init__(self):
        self.mgr = None
        self.quit_request = False

        # this is the directory where this module code is running from
        self.program_dir = os.path.dirname(os.path.abspath(inspect.getsourcefile(NetConfig)))

        # look for the .glade file and the images here:
        self.GLADE_DIR = os.path.join(self.program_dir, 'images')

        # glade setup
        builder = gtk.Builder()

        gladefile_list = ['netconfig.glade']
        for item in gladefile_list:
            item = os.path.join(self.GLADE_DIR, item)
            if builder.add_from_file(item) == 0:
                raise RuntimeError("GtkBuilder failed")

        missingSignals = builder.connect_signals(self)
        if missingSignals is not None:
            raise RuntimeError("Cannot connect signals: ", missingSignals)

        self.dlg = builder.get_object("main_dialog")

        self.password_dlg = builder.get_object("password_dialog")
        self.password_label = builder.get_object("password_label")
        self.password_entry = builder.get_object("password_entry")
        self.show_password_checkbutton = builder.get_object("show_password_checkbutton")

        self.connect_button = builder.get_object("connect_button")

        self.conn_liststore = builder.get_object("conn_liststore")
        assert self.conn_liststore is not None

        self.conn_treeview = builder.get_object("conn_treeview")
        assert self.conn_treeview is not None

        # columns -  ssid_col, signal_col, authtype_col, autoconnect_col, status_col

        tvc  = gtk.TreeViewColumn("Name")
        cellrenderer = gtk.CellRendererText()
        tvc.pack_start(cellrenderer, True)
        tvc.add_attribute(cellrenderer, 'text', 0)
        tvc.set_sort_column_id(0)
        self.conn_treeview.append_column(tvc)
        self.conn_treeview.set_search_column(0)

        tvc  = gtk.TreeViewColumn("Signal Strength")
        cellrenderer = gtk.CellRendererText()
        tvc.pack_start(cellrenderer, True)
        tvc.add_attribute(cellrenderer, 'text', 1)
        tvc.set_sort_column_id(1)
        self.conn_treeview.append_column(tvc)

        tvc  = gtk.TreeViewColumn("Authentication")
        cellrenderer = gtk.CellRendererText()
        tvc.pack_start(cellrenderer, True)
        tvc.add_attribute(cellrenderer, 'text', 2)
        tvc.set_sort_column_id(2)
        self.conn_treeview.append_column(tvc)

        tvc  = gtk.TreeViewColumn("Auto Connect")
        cellrenderer = gtk.CellRendererText()
        tvc.pack_start(cellrenderer, True)
        tvc.add_attribute(cellrenderer, 'text', 3)
        tvc.set_sort_column_id(3)
        self.conn_treeview.append_column(tvc)

        tvc  = gtk.TreeViewColumn("Status")
        cellrenderer = gtk.CellRendererText()
        tvc.pack_start(cellrenderer, True)
        tvc.add_attribute(cellrenderer, 'text', 4)
        tvc.set_sort_column_id(4)
        self.conn_treeview.append_column(tvc)

        # TODO alpha sorting of wifi rows by SSID name - it works, but isn't looking that way initially

        # Key will be ssid and value is WifiStatus object
        self.networkinfo = None

        # Re-use the same close button signal to trigger exiting...
        self.dlg.connect("delete-event", self.on_close_button_released)

        # start a timer for the background process invocation of nmcli and parsing
        # in order to provide timely feedback on signal strength
        # (picture somebody moving the computer around in various locations and orientations to see what
        # impact that has on the signal level - they want feedback pretty frequently)
        gobject.timeout_add(350, self.on_timer_expire)

        self.progressbar_lastpulsetime = 0

        self.updatecount = 0
        self.update_connect_button()

        self.dlg.show_all()


    def update_conntreeview(self, networkinfo):
        # although it would be handy to just do a liststore.clear() and insert new objects, this
        # plays havoc with the UI as selection is cleared all the time. So the user struggles to
        # select a row and then click Connect before it is cleared again.
        # we're on the gui thread so easy to get the current selection and then restore it
        # after we replace all the liststore rows.

        self.networkinfo = networkinfo

        selectednet = None
        (model, rowiter) = self.conn_treeview.get_selection().get_selected()
        if rowiter != None:
            selectednet = model.get_value(rowiter, 0)

        self.conn_liststore.clear()

        selected_treeiter = None
        for ws in self.networkinfo.wifidict.values():
            treeiter = self.conn_liststore.append([ws.ssid, ws.signallevel, ws.authtype, ws.autoconnect, ws.status])
            if selectednet == ws.ssid:
                # this new row in the list model matches the wifi network that was
                # previously selected
                selected_treeiter = treeiter

        for eth in self.networkinfo.ethiface_list:
            treeiter = self.conn_liststore.append([eth.iface_displayname, "n/a", "n/a", eth.autoconnect, eth.status])
            if selectednet == eth.iface_displayname:
                # this new row in the list model matches the network that was
                # previously selected
                selected_treeiter = treeiter

        # restore selection
        if selected_treeiter:
            self.conn_treeview.get_selection().select_iter(selected_treeiter)

        # the connected status for the selected network may have changed so update the
        # status of the connect button.
        self.update_connect_button()


    def on_timer_expire(self):
        # kick off a background nmcli if the last one isn't still in process
        if self.mgr is None:
            self.mgr = asyncwork.AsyncWorkManager()
            self.mgr.run_async(nmcli_networklist_runner)

        return True


    def get_wifi_password(self, ssid):

        # The style and wording of the password dialog is very explicitly chosen.  It was done to mirror the
        # network manager supplied password credential dialog as much as possible.  This is because the
        # user may see the network manager one if the ssid password is changed or if they entered the password
        # incorrectly initially.  We have no control over this so just match it.

        self.password_label.set_text("Password required to access the Wi-Fi network '%s'." % ssid)
        self.password_entry.set_text("")     # clear out last password
        self.show_password_checkbutton.set_active(False)

        self.password_dlg.show_all()
        self.password_dlg.present()
        response = self.password_dlg.run()
        self.password_dlg.hide_all()

        if response == gtk.RESPONSE_OK:
            return True

        return False


    def on_show_password_checkbutton_toggled(self, widget):
        # toggle the visibility property of the password entry control
        visibility = self.password_entry.get_visibility()
        self.password_entry.set_visibility(not visibility)


    def on_password_entry_activate(self, widget):
        self.password_dlg.response(gtk.RESPONSE_OK)


    def on_ok_button_released(self, widget):
        self.password_dlg.response(gtk.RESPONSE_OK)


    def on_cancel_button_released(self, widget):
        self.password_dlg.response(gtk.RESPONSE_CANCEL)


    def on_advanced_settings_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_advanced_settings_button_released(widget, data)


    def on_advanced_settings_button_released(self, widget, data=None):
        # launch nm-connection-editor
        childproc = subprocess.Popen("nm-connection-editor")

        '''
        TODO
        how to make this modal while we wait for the next process to exit?
        there must be some Gtk hooks for application focus gain and focus loss
        if we gain app focus and this process is still alive
        then we force its z-order to be higher than us and give it focus
           get_active_window
        ugh - this strays outside of good documentation for just PyGTK.
        It strays into gnome and window manager standards
        Might be able to accomplish some of this through d-bus, but
        I'm having no google luck on this.
        Basically look for the Win32 equivalent of WM_ACTIVATEAPP
        and SetWindowPos.
        '''

        # poor mans modality across processes...

        md = gtk.MessageDialog(self.dlg,
                               gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                               gtk.MESSAGE_INFO,
                               gtk.BUTTONS_NONE,
                               "Waiting for connection editor to close. Use Alt-Tab to see it again.")

        # Having no buttons causes focus to become label which appears with all its text selected
        # (look strange)
        vbox = md.get_message_area()
        children = vbox.get_children()
        for label in children:
            label.set_selectable(False)

        # snag the delete-event so that we ignore it
        md.connect("delete-event", self._ignore_delete_event)

        glib.idle_add(self._modal_check_for_process_death, childproc)
        md.show_all()
        gtk.main()
        md.destroy()

        # check autoconnect and remind user to enable this to make it easier for them
        # on power cycles?  Then they never have to use this utility again...

        mgr = asyncwork.AsyncWorkManager()
        mgr.run_async(nmcli_connectionlist_runner)

        md = gtk.MessageDialog(self.dlg,
                               gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                               gtk.MESSAGE_INFO,
                               gtk.BUTTONS_NONE,
                               "Checking network connections...")

        # Having no buttons causes focus to become label which appears with all its text selected
        # (look strange)
        vbox = md.get_message_area()
        children = vbox.get_children()
        for label in children:
            label.set_selectable(False)

        progressbar = gtk.ProgressBar()
        progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
        progressbar.set_pulse_step(0.05)   # 5% of the length of the bar
        vbox.add(progressbar)

        # snag the delete-event so that we ignore it
        md.connect("delete-event", self._ignore_delete_event)

        glib.idle_add(self._modal_check_for_final_result, mgr, progressbar)
        md.show_all()
        gtk.main()
        md.destroy()

        connlist = mgr.get_final_result(True)
        for con in connlist:
            if con.autoconnect is False:
                md = gtk.MessageDialog(self.dlg,
                                       gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                       gtk.MESSAGE_WARNING,
                                       gtk.BUTTONS_OK,
                                       "The network connection for '%s' is not enabled to automatically connect." % con.name)
                md.format_secondary_text("When editing network connections, the General tab has a checkbox to enable automatically connecting when the network is detected. Enabling this will eliminate extra steps when powering on the controller to establish network access.")
                md.run()
                md.destroy()
                break   # only need to nag them once


    def update_connect_button(self):

        # FIXME
        # Stupid tree view.  If you ctrl-click into the row it visually unselects it,
        # but for the life of me I can't catch the right signal at the right time to figure this out.
        # This is leftover debug stuff
        #print "Updating connect button", self.updatecount
        #self.updatecount += 1

        (model, rowiter) = self.conn_treeview.get_selection().get_selected()
        if rowiter != None:
            # There's a row selected so some type of action on it is possible.
            self.connect_button.set_sensitive(True)

            selectednet = model.get_value(rowiter, 0)   # This is the "Name" column value

            # The selectednet might be a wifi network or a wired ethernet one.
            if selectednet in self.networkinfo.wifidict:
                # Is the wifi connected or not? Change the button label accordingly...
                if self.networkinfo.wifidict[selectednet].status == 'Connected':
                    self.connect_button.set_label("Disconnect")
                else:
                    self.connect_button.set_label("Connect")
            else:
                for eth in self.networkinfo.ethiface_list:
                    if eth.iface_displayname == selectednet:
                        if eth.status == 'Connected':
                            self.connect_button.set_label("Disconnect")
                        else:
                            self.connect_button.set_label("Connect")
                        break
        else:
            self.connect_button.set_label("Connect")
            self.connect_button.set_sensitive(False)


    def on_conn_treeview_cursor_changed(self, widget, data=None):
        self.update_connect_button()
        return False


    def on_edit_proxy_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_edit_proxy_button_released(widget, data)


    def on_edit_proxy_button_released(self, widget, data=None):
        # launch nm-connection-editor
        childproc = subprocess.Popen("mate-network-properties")

        '''
        TODO
        how to make this modal while we wait for the next process to exit?
        there must be some Gtk hooks for application focus gain and focus loss
        if we gain app focus and this process is still alive
        then we force its z-order to be higher than us and give it focus
           get_active_window
        ugh - this strays outside of good documentation for just PyGTK.
        It strays into gnome and window manager standards
        Might be able to accomplish some of this through d-bus, but
        I'm having no google luck on this.
        Basically look for the Win32 equivalent of WM_ACTIVATEAPP
        and SetWindowPos.
        '''

        # poor mans modality across processes...

        md = gtk.MessageDialog(self.dlg,
                               gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                               gtk.MESSAGE_INFO,
                               gtk.BUTTONS_NONE,
                               "Waiting for proxy editor to close. Use Alt-Tab to see it again.")

        # Having no buttons causes focus to become label which appears with all its text selected
        # (look strange)
        vbox = md.get_message_area()
        children = vbox.get_children()
        for label in children:
            label.set_selectable(False)

        # snag the delete-event so that we ignore it
        md.connect("delete-event", self._ignore_delete_event)

        glib.idle_add(self._modal_check_for_process_death, childproc)
        md.show_all()
        gtk.main()
        md.destroy()


    def _modal_check_for_final_result(self, mgr, progressbar):
        # check if async work is done, but don't block waiting for it

        # have to throttle back the frequency of how often we call pulse for cosmetic reasons
        now = time.time()
        if (now - self.progressbar_lastpulsetime > 0.1):
            self.progressbar_lastpulsetime = now
            progressbar.pulse()

        if (mgr.get_final_result(False) != None):
            gtk.main_quit()
            return False  # signal caller we're done and go ahead and remove idle callback
        return True   # keep calling us on idle


    def _ignore_delete_event(self, widget, data):
        return True


    def _modal_check_for_process_death(self, process):
        # check if process is still alive
        if process.poll() != None:
            gtk.main_quit()
            return False  # signal caller we're done and go ahead and remove idle callback
        return True   # keep calling us on idle


    def on_connect_button_activate(self, widget, data=None):
        # this is only triggered by keyboard, not mouse in my testing
        # and the button_released handler is ONLY mouse and not keyboard.
        # Madness in Gtk land.
        return self.on_connect_button_released(widget, data)


    def on_connect_button_released(self, widget, data=None):
        # We may actually be connecting or disconnecting here...

        # Make sure there is a network selected in the tree view.
        selectednet = None
        (model, rowiter) = self.conn_treeview.get_selection().get_selected()
        if rowiter is None:
            md = gtk.MessageDialog(self.dlg,
                                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_WARNING,
                                   gtk.BUTTONS_OK,
                                   "A network must be selected before trying to connect.")
            md.run()
            md.destroy()

        else:
            selectednet = model.get_value(rowiter, 0)    # will be the Name column so either SSID or iface_displayname
            action = widget.get_label()    # Connect or Disconnect

            connectargs = { "action" : action }

            if selectednet in self.networkinfo.wifidict:
                # the selected network is a wireless one
                wifistatus = self.networkinfo.wifidict[selectednet]

                connectargs["ssid"] = wifistatus.ssid
                connectargs["iface"] = wifistatus.iface

                if wifistatus.uuid is not None:
                    # there is a defined nmcli connection for this ssid so we're going to use that
                    # which will already have the password credentials if needed
                    connectargs["uuid"] = wifistatus.uuid

                else:
                    if wifistatus.authtype != "None":
                        # gonna need a password so that we can create a new nmcli connection
                        # definition for the ssid.
                        if self.get_wifi_password(selectednet) == True:
                            password = self.password_entry.get_text()
                            connectargs["password"] = password
                        else:
                            # User pressed cancel to the password screen - bail on the connect attempt.
                            return

            else:
                # the selected network must be a wired ethernet one.
                # map back from iface_displayname to either uuid or mac address as that
                # is what nmcli_connect_runner needs.
                for eth in self.networkinfo.ethiface_list:
                    if selectednet == eth.iface_displayname:
                        connectargs["iface"] = eth.iface
                        if eth.connection_uuid is not None:
                            # give the runner the nmcli connection uuid
                            connectargs["uuid"] = eth.connection_uuid
                        else:
                            connectargs["macaddr"] = eth.macaddr

                        break

            # do all the actual connection work in an async task
            mgr = asyncwork.AsyncWorkManager()
            mgr.run_async(nmcli_connect_runner, connectargs)

            if action == "Connect":
                statusmsg = "Connecting to network '%s'" % selectednet
            else:
                statusmsg = "Disconnecting network '%s'" % selectednet

            md = gtk.MessageDialog(self.dlg,
                                   gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                   gtk.MESSAGE_INFO,
                                   gtk.BUTTONS_NONE,
                                   statusmsg)

            # Having no buttons causes focus to become label which appears with all its text selected
            # (look strange)
            vbox = md.get_message_area()
            children = vbox.get_children()
            for label in children:
                label.set_selectable(False)

            progressbar = gtk.ProgressBar()
            progressbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
            progressbar.set_pulse_step(0.05)   # 5% of the length of the bar
            vbox.add(progressbar)

            # snag the delete-event so that we ignore it
            md.connect("delete-event", self._ignore_delete_event)

            glib.idle_add(self._modal_check_for_final_result, mgr, progressbar)
            md.show_all()
            gtk.main()
            md.destroy()

            result = mgr.get_final_result(True)

            mgr.shutdown()

            if result is False:
                if action == "Connect":
                    # Failed to connect - security credentials or something else wrong.
                    md = gtk.MessageDialog(self.dlg,
                                           gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                           gtk.MESSAGE_WARNING,
                                           gtk.BUTTONS_OK,
                                           "Failed to connect network '%s'." % selectednet)

                    # There is a small race condition where the selectednet may not actually be in
                    # the wifidict anymore if the last nmcli status scan didn't pick it up so
                    # be careful.

                    if selectednet in self.networkinfo.wifidict:
                        ws = self.networkinfo.wifidict[selectednet]
                        md.format_secondary_text("Check the settings for network connection '%s' and make sure the Wi-Fi Security is set for %s and the password is correct." % (selectednet, ws.authtype))
                    else:
                        md.format_secondary_text("Check the settings for network connection '%s' and make sure the settings are correct." % selectednet)
                else:
                    # Failed to disconnect
                    md = gtk.MessageDialog(self.dlg,
                                           gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                                           gtk.MESSAGE_WARNING,
                                           gtk.BUTTONS_OK,
                                           "Failed to disconnect network '%s'." % selectednet)

                md.run()
                md.destroy()

        # Kick the refresh as fast as possible vs. waiting around for it.
        self.on_timer_expire()

        return True

    def on_close_button_released(self, widget, data=None):
        self.quit_request = True
        return True


if __name__ == "__main__":

    random.seed()

    ui = NetConfig()

    # TODO - need icon
    # gtk.gdk.AppLaunchContext.set_icon(None)

    # TODO
    # How the hell to get the password dialog to receive focus on display?
    # Am I invoking it incorrectly somehow?

    # TODO
    # Test showing the password dialog more than once in a single run (if destroyed it will get screwed up - may need to partition it off into separate glade file)

    # TODO convert the final result check to an idle callback handler
    # then can just run normal gtk.main()
    # but I think that would end up with 100% core usage because idle would just get hammered without
    # any event throttling.
    #
    # A future idea is to change asyncworker so that the queue that it is using to communicate
    # with the async process is added to the main event loop with glib calls.
    # https://developer.gnome.org/glib/stable/glib-The-Main-Event-Loop.html
    # could add a g_source I think with the queue file descriptor wrapped so that poll()
    # efficiently blocks for it.

    while not ui.quit_request:
        # run the main event loop once (blocking if necessary until at least one event needs to be dispatched)
        gtk.main_iteration(True)

        if ui.mgr != None:
            networkinfo = ui.mgr.get_final_result(False)
            if networkinfo is not None:
                ui.mgr = None
                ui.update_conntreeview(networkinfo)
