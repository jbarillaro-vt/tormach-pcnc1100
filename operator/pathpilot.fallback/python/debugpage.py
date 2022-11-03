# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

import gtk
import psutil

import linuxcnc
import btn
import machine
import hal


class DebugPage(gtk.Fixed):

    def __init__(self, machineobj):
        super(DebugPage, self).__init__()

        self.taskstatelabel = gtk.Label()
        self.put(self.taskstatelabel, 10, 10)

        self.zindexLabel = gtk.Label()
        self.put(self.zindexLabel, 10, 220)

        self.machineobj = machineobj
        self._zindexButtonState = 0; #off

        self.doorlocklabel = gtk.Label()
        self.put(self.doorlocklabel, 10, 40)

        # lathe and other machines don't have this, but share common debugpage so be careful.
        if 'acc_input_port2_led' in self.machineobj.image_list:
            lab = gtk.Label();
            lab.set_text('Accessory Input Port 2:')
            self.put(lab, 10, 110)
            self.put(self.machineobj.image_list['acc_input_port2_led'], 150, 110)

        if self.machineobj.machineconfig.has_door_lock():
            self.lockbutton = btn.ImageButton('button_job_close.png', 'lock-close-button')
            self.lockbutton.connect("button-release-event", self.on_lock_button_release_event)
            self.unlockbutton = btn.ImageButton('button_job_open.png', 'lock-open-button')
            self.unlockbutton.connect("button-release-event", self.on_unlock_button_release_event)
            self.put(self.lockbutton, 300, 40)
            self.put(self.unlockbutton, 300, 74)

        self.openfilesbutton = gtk.Button()
        self.openfilesbutton.set_label("Log Open Files")
        self.openfilesbutton.connect("button-release-event", self.on_openfiles_button_release_event)
        self.put(self.openfilesbutton, 300, 220)

        if machineobj.machineconfig.spindle_collet_type() == machine.MachineConfig.COLLET_BT30_WITH_DOGS:
            if self.machineobj.redis.hget("machine_prefs", "bt30_offset"):
                self.bt30button = btn.ImageButton('Set_BT30_Green.png', 'set_bt30')
            else:
                self.bt30button = btn.ImageButton('Set_BT30_Black.png', 'set_bt30')
            self.bt30button.connect("button-release-event", self.machineobj.on_bt30_button_release_event)
            self.put(self.bt30button, 10, 130)

        self.zindexButton = btn.ImageButton('Enc_BT30_Black.png', 'zindex_test')
        self.zindexButton.connect("button-release-event", self.on_zindex_button_release_event);
        self.put(self.zindexButton, 10, 180)

    def on_zindex_button_release_event(self, widget, data=None):
        if self._zindexButtonState == 0:
            self._zindexButtonState = 1
            #widget.set_image('zindex_test', 'Enc_BT30_Green.png')
            self.machineobj.hal['zindex-test'] = 1
            self.zindexLabel.set_text("ZINDEX_TEST ON ")
        #TODO: Get the 'Green.png 'Black.png to toggle so we don't have to use ZINDEX_TEST_ON/OFF
        else:
            self._zindexButtonState = 0
            #widget.set_image('zindex_test', 'Enc_BT30_Black.png')
            self.machineobj.hal['zindex-test'] = 0
            self.zindexLabel.set_text("ZINDEX_TEST OFF")


    def on_lock_button_release_event(self, widget, data=None):
        self.machineobj.hal["enc-door-lock-drive"] = 1

    def on_unlock_button_release_event(self, widget, data=None):
        self.machineobj.hal["enc-door-lock-drive"] = 0

    def on_openfiles_button_release_event(self, widget, data=None):
        filelist = psutil.Process().open_files()

        self.machineobj.error_handler.log("Open file list ({:d}):".format(len(filelist)))
        for ff in filelist:
            self.machineobj.error_handler.log("\t{:s}".format(ff.path))

    def refresh_page(self):
        # probably called from 50ms so be careful how slow this code is

        self.machineobj.status.poll()
        if self.machineobj.status.task_state == linuxcnc.STATE_ESTOP_RESET:
            self.taskstatelabel.set_text("Task State: ESTOP_RESET {:d}".format(self.machineobj.status.task_state))
        elif self.machineobj.status.task_state == linuxcnc.STATE_ESTOP:
            self.taskstatelabel.set_text("Task State: ESTOP {:d}".format(self.machineobj.status.task_state))
        elif self.machineobj.status.task_state == linuxcnc.STATE_ON:
            self.taskstatelabel.set_text("Task State: STATE_ON {:d}".format(self.machineobj.status.task_state))
        elif self.machineobj.status.task_state == linuxcnc.STATE_OFF:
            self.taskstatelabel.set_text("Task State: STATE_OFF {:d}".format(self.machineobj.status.task_state))
        else:
            self.taskstatelabel.set_text("Task State: ??? {:d}".format(self.machineobj.status.task_state))

        if 'acc_input_port2_led' in self.machineobj.image_list:
            self.machineobj.set_indicator_led('acc_input_port2_led', self.machineobj.hal['acc-input-port2'])

        if self.machineobj.machineconfig.has_door_lock():
            txt = "Door locked status: {:d}   Door open status: {:d}".format(self.machineobj.hal["enc-door-locked-status"], self.machineobj.hal["enc-door-open-status"])
            self.doorlocklabel.set_text(txt)
