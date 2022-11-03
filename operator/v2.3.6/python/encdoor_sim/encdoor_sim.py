#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2019 Tormach® Inc. All rights reserved.
# License: See eula.txt file in same directory for license terms.
#-----------------------------------------------------------------------

import pygtk
pygtk.require("2.0")
import gtk
import gobject
import constants
import os
import sys
import errors
import glib

from hal import *
import vmcheck


GLADE_DIR = os.path.dirname(os.path.abspath(__file__))
eh = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

class HalWrapper:
    def __init__(self, comp):
        self._comp = comp
        self._pins = set()
        self._params = set()

    def newpin(self, *args):
        self._pins.add(args[0])
        return self._comp.newpin(*args)

    def newparam(self, *args):
        self._params.add(args[0])
        return self._comp.newparam(*args)

    def __getitem__(self, k):
        return self._comp[k]

    def __setitem__(self, k, v):
        if k in self._params:
            self._comp[k] = v; return
        elif k in self._pins:
            self._comp[k] = v; return
        else:
            raise KeyError, k


class EnclosureDoorSim():
    def __init__(self):
        self.hal_component = component("encdoorsim")
        #self.hal_component.setprefix("tormach-encdoorsim")
        self.wrapper = HalWrapper(self.hal_component)

        self.builder = gtk.Builder()

        gladefilepath = os.path.join(GLADE_DIR, 'encdoor_sim') + ".glade"
        result = self.builder.add_from_file(gladefilepath)
        assert result > 0, "Builder failed on %s" % gladefilepath

        # be defensive if stuff exists in glade file that can't be found in the source anymore!
        missing_signals = self.builder.connect_signals(self)
        if missing_signals is not None:
            raise RuntimeError("Cannot connect signals: ", missing_signals)

        self.ignore_door_lock_drive_checkbutton = self.builder.get_object('ignore_door_lock_drive_checkbutton')

        button = self.builder.get_object('open_door_button')
        button.connect('button-release-event', self.on_door_change_state, True)
        button = self.builder.get_object('close_door_button')
        button.connect('button-release-event', self.on_door_change_state, False)

        self.dooropenstatus_label = self.builder.get_object('dooropenstatus_label')
        self.doorlockedstatus_label = self.builder.get_object('doorlockedstatus_label')

        self.wrapper.newpin("enc-door-open-status", HAL_BIT, HAL_OUT)
        self.wrapper.newpin("enc-door-locked-status", HAL_BIT, HAL_OUT)
        self.wrapper.newpin("enc-door-lock-drive", HAL_BIT, HAL_IN)

        self.hal_component.ready()

        self.main_window = self.builder.get_object('encdoorsim_window')

        # Don't show the UI if we're running in Docker which for now we
        # equate to PathPilot Hub.
        my_vmcheck = vmcheck.vmcheck()
        if not (my_vmcheck.is_virtualized_os() and my_vmcheck.get_vendor() == 'Docker'):
            self.main_window.show_all()

        glib.timeout_add(30, self.fast_timer_callback)
        glib.timeout_add(500, self.slow_timer_callback)


    def fast_timer_callback(self):
        if not self.ignore_door_lock_drive_checkbutton.get_active():
            self.locked_status = self.wrapper['enc-door-lock-drive']
        self.wrapper['enc-door-locked-status'] = self.locked_status

        return True  # schedule us again


    def on_exit_button_clicked(self, widget, data=None):
        self.main_window.destroy()
        gtk.main_quit()


    def on_door_change_state(self, widget, event, data):
        if data:
            self.wrapper['enc-door-open-status'] = 1
            eh.log("EnclosureDoorSim : Door opened")
        else:
            self.wrapper['enc-door-open-status'] = 0
            eh.log("EnclosureDoorSim : Door closed")


    def slow_timer_callback(self):
        # update labels to reflect current status
        self.dooropenstatus_label.set_text('Door Open: {:d}'.format(self.wrapper['enc-door-open-status']))
        self.doorlockedstatus_label.set_text('Door Locked: {:d}'.format(self.wrapper['enc-door-locked-status']))
        return True  # reschedule timer callback again


    def unload(self):
        self.hal_component.exit()


if __name__ == "__main__":

    door = None
    try:
        door = EnclosureDoorSim()
        gtk.main()
    except KeyboardInterrupt:
        eh.log("EnclosureDoorSim : caught KeyboardInterrupt, hal comp shutting down.")

    #except Exception as e:
    #    eh.log("EnclosureDoorSim : Caught unknown exception: " + str(e))

    if door:
        door.unload()

    sys.exit(0)
