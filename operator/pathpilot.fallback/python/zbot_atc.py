#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


import gtk
import glib
import time
import popupdlg
import linuxcnc
import Queue
import threading
import thread
import datetime
import traceback
import errors
import timer
import subprocess
import machine
import popupdlg
import plexiglass
import ui_misc

from constants import *
import ppglobals


class zbot_atc():
    def __init__(self, machineconfig, status, command, issue_mdi, hal,\
                 redis, atc_pocket_list, dro_list, atc_fixed,\
                 parentwindow, error_handler, set_image, mill_probe):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()

        self.machineconfig = machineconfig
        self.tracing = False
        self.status = status
        self.command = command
        self.hal = hal
        self.redis = redis
        self.atc_pocket_list = atc_pocket_list
        self.atc_fixed = atc_fixed
        self.error_handler = error_handler
        self.firmware_version_checked = False
        self.set_image = set_image
        self.mill_probe = mill_probe
        self.issue_mdi=issue_mdi
        self.parentwindow = parentwindow
        self.dro_list = dro_list
        self.operational = False
        self.request_sequence_number = 1000000.0   #intial seed value for requests

        # worker thread for long running transactions.   Keeps GUI responsive.
        self.off_load_thread = None
        self.process_queue = Queue.Queue()     #work queue for atc  server thread
        self.in_a_thread = threading.Event()   #hey, I'm working here!
        self.stop_reset = threading.Event()    #stop working - signaled from GUI
        self.feed_hold_clear = threading.Event()   # signaled when machine is NOT in feedhold (user probably pressed cycle start).
                                                   # this way we can use the efficient Event.wait() call vs. busy loop spinning.
        self.feed_hold_clear.set()              #feedhold is not active at init
        self.general_error = threading.Event() #generic error of any kind - signaled from GUI
        self.started_msg = 'started'           #first time message text for worker bee startup
                                               # morphs to restarted if failure kills thread

        #atc z locations

        self.change_z  =       float()
        self.blast_distance  = float()
        self.compression =     float()
        self.tool_shank_jog =  float()
        self.jog_speed =       float()
        self.scale_factor = 1.0
        self.restore_g91 = False                # gcode state

        # ---------------------------------------------------------
        # force intialization of Redis data
        # ---------------------------------------------------------

        # This re-entrant lock protects from possible corruption during concurrent access
        # from the GUI and worker thread
        #    - self.pocket_dict
        self.pocket_dict_rlock = threading.RLock()
        with self.pocket_dict_rlock:
            self.pocket_dict = {}
            self.refresh_pocket_dict()  # will set up the z-bot variables hash table if not yet defined

        #------------------------------------------------------------------------------------
        # map the carousel labels. default Glade setup is for ten tools. others must be relocated
        # for new image files and some widgets adjusted.
        # each entry in list contains a tuple of coordinates.  coordinates (-1,-1) are for hidden labels
        #-------------------------------------------------------------------------------------
        self.carousel_8_label_locations = [(649,186),(605,60),(479,17),(354,60),(310,186),(356,312),(480,354),(605,312),(-1,-1),(-1,-1),(-1,-1),(-1,-1)]
        self.carousel_10_label_locations= [(643,186),(614,84),(529,25),(423,22),(341,86),(305,186),(337,288),(422,350),(530,350),(616,289),(-1,-1),(-1,-1)]
        self.carousel_12_label_locations= [(651,188),(631,104),(565,38),(478,20),(396,38),(337,104),(313,188),(337,270),(396,332),(478,355),(565,332),(631,270)]
        self.current_carousel_map = 0
        #------------------------------------------------------------------------
        # what type of spindle do we have?
        # known values are None and "BT30_WITH_DOGS"
        #-----------------------------------------------------------------------
        inifilepath = self.redis.hget('machine_prefs', 'linuxcnc_inifilepath')
        self.ini = linuxcnc.ini(inifilepath)
        self.collettype = self.ini.find("SPINDLE", "COLLET_TYPE")


    def is_atc_firmware_incompatible_with_previous_versions(self):
        if self.redis.hexists('zbot_atc_info', 'firmware_version'):
            firmware = self.redis.hget('zbot_atc_info', 'firmware_version')
            # firmware should be a string of the form a.b.c (or a ?)
            if firmware == ATCFIRMWARE_VERSION_SPECIALCASE:
                return True
        return False

    def get_atc_firmware_version_description(self):
        if self.redis.hexists('zbot_atc_info', 'firmware_version'):
            firmware = self.redis.hget('zbot_atc_info', 'firmware_version')
            return 'ATC firmware version: {:s}'.format(firmware)
        return 'ATC firmware version: <never read>'

    def does_atc_firmware_need_update(self):
        if not self.firmware_version_checked and self.redis.hexists('zbot_atc_info', 'firmware_version'):
            self.firmware_version_checked = True

            # gen 2 boards and beyond report firmware version and the atc user comp will write whatever version it finds
            # into redis.  If the atc firmware is old enough that it isn't reporting version as expected,
            # then a ? is written into the key.
            firmware = self.redis.hget('zbot_atc_info', 'firmware_version')

            # firmware should be a string of the form a.b.c (or ?)
            # currently our policy is that it needs to match what we want, we don't try to check against some
            # minimum level of supported firmware so that we work with versions newer than we expect.
            # The SPECIALCASE version we do not try to change (for now).
            if firmware != '?' and firmware != ATCFIRMWARE_VERSION and firmware != ATCFIRMWARE_VERSION_SPECIALCASE:
                if firmware == 'Loader':
                    # this means the previous firmware update had a power loss.  Force a firmware load because
                    # it will never work without one.
                    dialog = popupdlg.ok_cancel_popup(self.parentwindow, "The ATC firmware needs to be loaded.  Press OK to start the update.", cancel=False)
                else:
                    dialog = popupdlg.ok_cancel_popup(self.parentwindow, "The ATC firmware needs to be updated.  Press OK to start the update.")

                dialog.run()
                dialog.destroy()
                if dialog.response == gtk.RESPONSE_OK:
                    self.error_handler.log("User clicked OK to ATC firmware prompt, exiting so atcupdate.py can do its thing.")
                    return True

        return False

    # ---------------------------------------------------------
    # GUI button callbacks
    # ---------------------------------------------------------

    #--------------------------------------------------------------------------
    # Enable or disable tool changer:  (radio button in GUI)
    #  Results in system config changes in redis data store
    #  The HAL component uses the config data to determine if it should
    #  enable itself and begin communication on the USB channel to the ATC controller
    #
    #  Also sets operational attribute for Tormach GUI to use in setting notebook
    #  page display and other status functions. ATC does not start operations until RESET is pressed
    #  on main GUI.
    #---------------------------------------------------------------------------


    def disable(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.redis.hset('machine_prefs', 'toolchange_type', MILL_TOOLCHANGE_TYPE_REDIS_MANUAL)
        self.operational = False


    def enable(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.redis.hset('machine_prefs', 'toolchange_type', MILL_TOOLCHANGE_TYPE_REDIS_ZBOT)
        self.operational = True    #takes effect at RESET


    def map_graphics(self):
        # whenever an ATC board connects -
        # the hal [tools in tray] pin is set when hal binds to the atc board
        # this routine nmaps carousel DROs appropriate to the hardware.
        # tool dro location are hard coded in lists named:
        #         'self_carousel_N_lable_locations'
        # where N is tools in the tray, each tuple has simple coordinates:
        #
        #  (xcoordinate, ycoordinate) , if not used coordinates are (-1,-1)
        #


        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        # at start up carousel map is set to 0, so it forces mapping
        tools = self.hal["atc-tools-in-tray"]
        if tools != self.current_carousel_map:  #  get new graphics, relocate the tool dros
            assert tools in (8, 10, 12), "Unexpected tool count."

            filename = 'ATC_' + str(tools) + '_Slot_Tray.jpg'
            self.set_image('atc_tray_image', filename)
            if tools == 8:
                label_locations = self.carousel_8_label_locations
            elif tools == 10:
                label_locations = self.carousel_10_label_locations
            elif tools == 12:
                label_locations = self.carousel_12_label_locations

            for i in range(12):       #now move stuff around
                if label_locations[i][0] == -1 :  # hide the ones we don't want here
                    self.atc_pocket_list['atc_carousel_' + str(i)].hide()
                else:                             #move it around tray
                    self.atc_fixed.move(self.atc_pocket_list['atc_carousel_'+ str(i)], label_locations[i][0], label_locations[i][1])
                    self.atc_pocket_list['atc_carousel_' + str(i)].show()
            # only do this when needed - remember map actions.
            self.current_carousel_map = self.hal["atc-tools-in-tray"]


    #-----------------------------------------------------------------------------------
    #  Maintain Slot/Tool mapping table - these do not involve motion of the ATC and
    #  are executed directly in the GUI thread.
    #------------------------------------------------------------------------------------

    def insert(self, manual_insert_dro):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        valid, tool_number, error_msg = self.validate_tool_number(manual_insert_dro)
        if valid:
            if (self.lookup_slot(tool_number) < 0 ):  #check for duplicates
                current_slot = int(self.redis.hget('zbot_slot_table', 'current_slot')) #assign it
                self.redis.hset('zbot_slot_table', str(current_slot), str(tool_number))
                self.display_tray()   #respond imnmediately - don't wait 500ms
                # clear insert dro
                manual_insert_dro.set_text('')
            else:
                self.error_handler.write('duplicate tool number in tray', ALARM_LEVEL_MEDIUM)
        else:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)


    def delete(self, manual_insert_dro):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        valid, tool_number, error_msg = self.validate_tool_number(manual_insert_dro)
        if valid:
            self.delete_tray_assignment(tool_number)
        else:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)


    def delete_tray_assignment(self, tool_number):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        slot = self.lookup_slot(tool_number)
        if slot >= 0:
            self.redis.hset('zbot_slot_table', str(slot), '0')
            if slot == int(self.redis.hget('zbot_slot_table', 'current_slot')):
                self.dro_list['atc_auto_dro'].set_text('')
                self.dro_list['atc_manual_insert_dro'].set_text('')
                self.display_tray()   #respond imnmediately - don't wait 500ms
            return True
        return False   #no slot assigned -

    def delete_all(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        dlg = popupdlg.ok_cancel_popup(self.parentwindow, "Delete all tool assignments from tray slots?", cancel=True, checkbox=False)
        try:
            dlg.run()
            if dlg.response == gtk.RESPONSE_OK:
                with self.pocket_dict_rlock:
                    for ii in range(self.hal["atc-tools-in-tray"]):        #set up for max tools in table
                        self.pocket_dict[str(ii)] = '0'                    #with no tools assigned to them
                        self.redis.hset('zbot_slot_table',str(ii),'0')     # and lay it down in the db
                        self.dro_list['atc_auto_dro'].set_text('')
                        self.dro_list['atc_manual_insert_dro'].set_text('')

                self.display_tray()
        finally:
            dlg.destroy()


    #--------------------------------------------------------------------------------------------
    # ATC motion GUI commands - all of these commands may result in telling the ATC, through the
    #   HAL component to move, or the Z axis to move or both.  They are all long running transactions and
    #   are executed in the context of a worker thread to avoid locking up the GUI during execution.
    #   It is also important that these execute in state machine fashion to avoid conflicts between
    #   buttons.  Most buttons will not support multiple presses except tray fwd and tray rev to allow
    #   users to do multiple presses and have the tray respond appropriately.  Only these queue up for
    #   repetitive function. Other buttons are ignored if pressed reduntantly.
    #
    #   The logic behind these buttons is common - Each GUI button press is dispatched by GTK through
    #   main logic in the Tormach Mill GUI, which in turn calls the appropriate method in the atc module.
    #   The methods here all queue a request in a multitaking queue set up for that purpose.
    #   The process_the_queue method is run in a worker thread, which pops individual entries off the queue
    #   and dispatches them to the appropriate routine for execution. The GUI thread is not locked during
    #   worker thread execution.
    #
    #   Each threaded set of buttons, is therefore, two methods.  The first method queues the request, and the
    #   second method, always named 'self.*_thread', where * is the name of the queueing method, is called
    #   by process_the_queue.
    #
    #   If any button returns a False boolean from it's execution, all queued requests are purged
    #   from the process queue.  It is important to always return a boolean value when adding
    #   new buttons.
    #-----------------------------------------------------------------------------------------------
    def tray_rev(self):                               # queue this request behind the last
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_tray_rev',None))     # executes code below in thread
    def tray_rev_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        current_slot = int(self.redis.hget('zbot_slot_table', 'current_slot'))
        next_slot = (current_slot+self.hal["atc-tools-in-tray"]-1)%self.hal["atc-tools-in-tray"] # #modulus keeps the number in tool tray range
        if self.clear():
            self.index_from_gui(next_slot, True)
            return True

        return False


    def tray_fwd(self):                               #queue this request behind the last
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_tray_fwd',None))     #executes code below in thread
    def tray_fwd_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        current_slot = int(self.redis.hget('zbot_slot_table', 'current_slot'))
        next_slot = (current_slot+1)%self.hal["atc-tools-in-tray"]  #modulus keeps the number in tool tray range
        if self.clear():
            self.index_from_gui(next_slot, True)
            return True
        return False


    def go_to_tray_load_position(self):

        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.status.poll()
        #catch this here so new users don't get confused at setup ATC time
        if not self.status.homed[2]:
            self.error_handler.write("ATC - Z axis must be referenced to go to tray load")
            return
        self.queue_dispatch(('do_tray_load',None))  #executes code below in thread

    def go_to_tray_load_position_thread(self):      #dispatched by process_queue in worker thread
        #============================================================================
        # tray load normally clears the spindle and sends the tray in via M6
        #  with a special secret code introduced to indicate to the NGC tool change
        #  that the tray should be left in.  During setup of a new machine, this results
        #  in a chicken/egg situation, because M6 will not run unless both the toolchangeZ
        #  location is set, and for BT30, the orient position.  The alternative code here
        #  sends the spindle to the top, and actuates the tray in. For TTS it leaves the
        #  collet open, for BT30 it leaves the collet closed, so that the spindle may be
        #  rotated.
        #=============================================================================

        assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        if float(self.redis.hget('zbot_slot_table', 'tool_change_z')) != 0.0:
            self.m6_cycle (0, True)        #secret hand shake for going to tray load thru NGC

        else:     #ATC First time setup mode

            #====================================================================
            # Get Z up to top of column once user confirms setup mode
            #====================================================================
            #if self.prompt_OK_Cancel("ATC setup mode - Remove any tool in spindle"):
            self.go_to_z (0.0)      #get z to top of column, wait arrival
            #else:
            #    return True            # user cancelled sequence - no biggie
            #====================================================================
            # Let's see what to do with the draw bar
            #====================================================================
            if self.collettype == "BT30_WITH_DOGS" :
                self.hey_hal(ATC_DRAW_BAR,ATC_DEACTIVATE) #allow rotation for BT30
            else :
                self.hey_hal(ATC_DRAW_BAR,ATC_ACTIVATE)   #keep spindle open TTS

            self.hey_hal(ATC_SOLENOID,ATC_TRAY_SOLENOID) #get the tray in

            #self.prompt_OK_Cancel("ATC setup mode - Now insert a tool holder in tray, Align Z, then set SET TC POS")


        return True



    def retract(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_retract',None))  #executes code below in thread
    def retract_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        # always retract when commanded, independent of status
        #if not self.hal["atc-tray-status"]:return  #already retracted boss, take the day off
        if self.redis.hget('zbot_slot_table', 'tool_change_z') != '0.0':  #we are in set up time, no tools to be clear of
            if not self.clear():return False  #had problems verifying integrity of location
        if not self.hey_hal(ATC_SOLENOID,-ATC_TRAY_SOLENOID): return False  # safe now - retract
        return True


    def set_tc_z(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.status.poll()
        if self.status.homed[2]:
            change_z = self.status.actual_position[2]
            if change_z < -1.5 and change_z > -4.5:
                self.redis.hset('zbot_slot_table', 'tool_change_z',change_z)
                self.error_handler.write("ATC - tool change Z position set to " + str(self.status.actual_position[2]), ALARM_LEVEL_DEBUG)
            else:
                self.error_handler.write("ATC - tool change Z position out of bounds, must be between -3.5 and -1.5.", ALARM_LEVEL_MEDIUM)
                return False
        else:
            self.error_handler.write("ATC - Z axis must be referenced to set change Z", ALARM_LEVEL_MEDIUM)
            return False
        return True

    def fetch(self, auto_insert_dro):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        # we must validate the tool number while on the GUI thread.
        valid, tool_number, error_msg = self.validate_tool_number(auto_insert_dro)
        if valid:
            auto_insert_dro.set_text('')
            self.queue_dispatch(('do_fetch', tool_number))  #executes code below in thread
        else:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
    def fetch_thread(self, tool_number): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.m6_cycle(tool_number)
        return True


    def remove(self, auto_insert_dro):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        # we must validate the tool number while on the GUI thread.
        valid, tool_number, error_msg = self.validate_tool_number(auto_insert_dro)
        if valid:
            self.queue_dispatch(('do_remove',tool_number))  #executes code below in thread
        else:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
    def remove_thread(self, tool_number): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        slot = self.lookup_slot(tool_number)
        if (slot >= 0):   #in tray?
            self.error_handler.log("ATC removing tool {:d} in slot {:d}".format(tool_number, slot))
            self.m6_cycle(tool_number)       #get the tool in spindle
            self.redis.hset('zbot_slot_table', str(slot), '0')  #delete from tray
            self.display_tray()   #respond imnmediately - don't wait 500ms
        self.m6_cycle(0)          # now will prompt to remove anything in there
        return True


    def atc_fwd(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_fwd',None))   #executes code below in separate thread
    def atc_fwd_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        with self.pocket_dict_rlock:
            self.refresh_pocket_dict()   #suck it in from db
            current_slot = int(self.pocket_dict["current_slot"] )  # starting point
            for i in range(current_slot+1, current_slot + self.hal["atc-tools-in-tray"]): # (count up)
                tool = self.pocket_dict[str(i%self.hal["atc-tools-in-tray"])]
                if (tool != '0'):
                    self.status.poll()
                    if (self.status.tool_in_spindle) == int(tool):  #next tool already in, just advance tray
                        if not self.index_from_gui(i%self.hal["atc-tools-in-tray"]): return False
                    else:
                        self.m6_cycle(int(tool))
                    return True


    def atc_rev(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_rev',None))    #executes code below in separate thread
    def atc_rev_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        with self.pocket_dict_rlock:
            self.refresh_pocket_dict()   #suck it in from db
            current_slot = int(self.pocket_dict["current_slot"])     # starting point
            for i in range(current_slot+ self.hal["atc-tools-in-tray"]-1, current_slot, -1): # (count down )
                tool = self.pocket_dict[str(i%self.hal["atc-tools-in-tray"])]
                if (tool != '0'):
                    self.m6_cycle(int(tool))
                    self.index_from_gui(i%self.hal["atc-tools-in-tray"])  # in case tool was in spindle, and m6 does nothing
                    return True


    def store(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_store',None))    #executes code below in separate thread
    def store_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.status.poll()                           #get current tool
        tool_to_store = self.status.tool_in_spindle #see if it's important

        if tool_to_store <= 0: return  True

        self.refresh_pocket_dict()   #suck it in from db
        if (self.lookup_slot(tool_to_store) == -1):   #not in tray ?
            stored = False      #until we find a home for this guy
            current_slot = int(self.hal["atc-tray-position"])
            with self.pocket_dict_rlock:
                for i in range(current_slot, current_slot + self.hal["atc-tools-in-tray"]):    # look for a parking spot
                    pocket = str(i%self.hal["atc-tools-in-tray"])
                    if (self.pocket_dict[pocket] == '0'):    #got an empty slot
                        self.redis.hset('zbot_slot_table', pocket, str(tool_to_store))  #assign to tray
                        stored = True
                        break
                    else:
                        continue
            if stored is False:
                self.error_handler.write('tool tray is full', ALARM_LEVEL_MEDIUM)
                return False

        self.m6_cycle(0)
        return True   #stored it


    #Execute draw bar toggle button in GUI thread
    def set_drawbar_up(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.firmly_issue_mdi("M5")    # will release brake if set
        self.queue_dispatch(('do_drawbar_up',None))    #executes code below in separate thread
    def set_drawbar_up_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        if not self.hey_hal(ATC_DRAW_BAR,ATC_DEACTIVATE): return False


    def set_drawbar_down(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_drawbar_down',None))    #executes code below in separate thread
        self.firmly_issue_mdi("M5")    #will release brake if set
    def set_drawbar_down_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        if not self.hey_hal(ATC_DRAW_BAR,ATC_ACTIVATE): return False


    #Execute tray reference button in GUI thread
    def home_tray(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_home',None))    #executes code below in separate thread
    def home_tray_thread(self):  #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        if self.clear():
            if not self.hey_hal(ATC_FIND_HOME,0):return False


    #Execute offset buttons in GUI thread
    def offset_tray_pos(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_offset_tray_pos',None))    #executes code below in separate thread
    def offset_tray_pos_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        if not self.hey_hal(ATC_OFFSET_HOME,ATC_SET_UP): return False
        return True


    def offset_tray_neg(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_offset_tray_neg',None))    #executes code below in separate thread
    def offset_tray_neg_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.hey_hal(ATC_OFFSET_HOME,ATC_SET_DOWN)


    #Execute blast button in GUI thread
    def blast(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_blast',None))    #executes code below in separate thread

    def blast_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.hey_hal(ATC_SOLENOID,ATC_BLAST_SOLENOID)   #turn on

    def blast_off(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_blast_off',None))   #if blaster is on - kill it.

    def blast_off_thread(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.hey_hal(ATC_SOLENOID,-ATC_BLAST_SOLENOID)

    #Execute ref Z button in GUI thread
    def queue_ref_axis(self, axis):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        if axis == 0:
            self.ref_x()
        elif axis == 1:
            self.ref_y()
        elif axis == 2:
            self.ref_z()
        elif axis == 3:
            self.ref_a()


    def ref_x(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_ref_x',None))    #executes code below in separate thread
    def ref_x_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.home(0)

        # I don't fully understand WHY we sit here and wait for the completion
        # of this homing.  Is it just to tie up the ATC worker thread from executing something
        # else if the user gets twitchy?
        # We don't take any action AFTER the axis homing is complete so why wait?

        time.sleep(.1)  # 100 millis
        st = timer.Stopwatch()
        while self.status.axis[0]['homing']:
            time.sleep(.2)  # 200 millis
            st.lap()
        self.error_handler.write("X referenced in queue; {:s}".format(st), ALARM_LEVEL_DEBUG)
        return True


    def ref_y(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_ref_y',None))    #executes code below in separate thread
    def ref_y_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.home(1)

        # I don't fully understand WHY we sit here and wait for the completion
        # of this homing.  Is it just to tie up the ATC worker thread from executing something
        # else if the user gets twitchy?
        # We don't take any action AFTER the axis homing is complete so why wait?

        time.sleep(.1)  # 100 millis
        st = timer.Stopwatch()
        while self.status.axis[1]['homing']:
            time.sleep(.2)   # 200 millis
            st.lap()
        self.error_handler.write("Y referenced in queue; {:s}".format(st), ALARM_LEVEL_DEBUG)
        return True


    def ref_z(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_ref_z',None))    #executes code below in separate thread
    def ref_z_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        if self.operational:
            if self.hal["atc-tray-status"]:   #tray is in
                if not self.hey_hal(ATC_DRAW_BAR,ATC_ACTIVATE):  #free spindle
                    self.error_handler.write('ATC - tray must be retracted', ALARM_LEVEL_MEDIUM)
                    return False
                # danger, dragons be here.
                # linuxcnc bug where sledgehammering is needed.  First one lcnc ignores for some reason.
                self.firmly_issue_mdi("M61 Q0")          #clear the active tool               #clear the active tool
        self.command.mode(linuxcnc.MODE_MANUAL)    #force it on
        self.command.home(2)      # spindle must be clear to move Z

        time.sleep(.1)  # 100 millis
        st = timer.Stopwatch()
        while self.status.axis[2]['homing']:
            time.sleep(.2)   # 200 millis
            st.lap()
        self.error_handler.write("Z referenced in queue; {:s}".format(st), ALARM_LEVEL_DEBUG)
        return True

    def ref_a(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_ref_a',None))    #executes code below in separate thread
    def ref_a_thread(self): #dispatched by process_queue in worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.command.mode(linuxcnc.MODE_MANUAL)
        self.command.home(3)

        # I don't fully understand WHY we sit here and wait for the completion
        # of this homing.  Is it just to tie up the ATC worker thread from executing something
        # else if the user gets twitchy?
        # We don't take any action AFTER the axis homing is complete so why wait?

        time.sleep(.1)  # 100 millis
        st = timer.Stopwatch()
        while self.status.axis[3]['homing']:
            time.sleep(.2)   # 200 millis
            st.lap()
        self.error_handler.write("A referenced in queue; {:s}".format(st), ALARM_LEVEL_DEBUG)
        return True


    #Execute touch tray button in GUI thread
    def touch_entire_tray(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        self.queue_dispatch(('do_touch_tray',None))    #executes code below in separate thread
    def touch_entire_tray_thread(self):   # will be dispatched by process_queue in atc worker thread
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        self.status.poll()
        if not self.clear() : return False  #clear the tool tray if under spindle
        
        current_slot = int(self.hal["atc-tray-position"])
        user_feedrate = abs(self.status.settings[1])

        if (self.status.program_units ==  1): #inches
            self.scale_factor = 1.0
        if (self.status.program_units ==  2):  #mms
            self.scale_factor = 25.4

        feedrate = 50 * self.scale_factor   #set feed rate to 50 ipm
        self.firmly_issue_mdi("F"+str(feedrate))   # let's not dawdle here

        for ii in range(current_slot, current_slot + self.hal["atc-tools-in-tray"]):

            with self.pocket_dict_rlock:
                tool = int(self.pocket_dict[str(ii % self.hal["atc-tools-in-tray"])])

            if tool > 0:   #is there a tool to be had
                self.m6_cycle(tool)
                probe_started = False                  #probe monitor  reset

                self.mill_probe.probe_move_and_set_tool_length()  # kick off probing NGC routine

                st = timer.Stopwatch()
                for zz in xrange(50):    # give it awhile to start, detect probing is running
                    self.status.poll()
                    if self.status.probing:
                        probe_started = True  #probe monitor set, it's running
                        break
                    time.sleep(.05)
                    st.lap()
                self.error_handler.log('Wait for probe monitor set complete; {:s}'.format(st))

                st.restart()
                time_out_counter = 150 # give it 30 seconds to complete if it started
                while (probe_started and time_out_counter > 0):  # need to wait for last ngc probe to finish
                    self.status.poll()
                    if self.status.interp_state == linuxcnc.INTERP_IDLE:
                        break  # we're done probing

                    while self.status.interp_state == linuxcnc.INTERP_PAUSED: #spin on feed holds
                        time.sleep(.2)
                        self.status.poll()

                    time.sleep(.2)
                    time_out_counter = time_out_counter-1  #don't count feed hold time

                self.error_handler.log('probe complete, time_out_counter = {:d}; {:s}'.format(time_out_counter, st))

                #field stop/resets/errors that may have occured
                if not self.stop_reset_check():
                    return False

                #ngc returned without probing or it timed out
                if not probe_started or time_out_counter == 0:
                    self.error_handler.write('ATC - probing operation error', ALARM_LEVEL_MEDIUM)
                    return False

                #ngc returned   - all is well -- continue on with next tool

        #tray is run
        self.firmly_issue_mdi("F"+str(user_feedrate))          #restore user's feedrate
        return True


    # ---------------------------------------------
    # atc helpers
    # ---------------------------------------------

    def is_changing(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        #----------------------------------------------------------------------------------------------------
        #Change broadcast digital pin is set to 1 by M400 NGC routine, and the GUI M6 Cycle to indicate
        #we are in an active tool change sequence. Users call this boolean function from anywhere to check.
        #  Returns :
        #     True - in a change
        #     False - coast is clear
        #-----------------------------------------------------------------------------------------------------
        self.status.poll()
        if self.status.dout[ATC_HAL_IS_CHANGING] == 1: return True
        return False


    def get_drawbar_state(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        #-------------------------------------------------------
        #  Draw bar solenoid state is updated periodically by the HAl
        #   component, however sometimes we need it immediately
        #
        #   Returns:
        #      True -  draw bar solenoid is asserted
        #      False - draw bar solenoid is not asserted
        #-------------------------------------------------------------
        self.hey_hal(ATC_QUERY_SENSOR,ATC_DRAW_SENSOR)    #refresh status immediately
        if self.hal["atc-draw-status"]:     #get hal status
            return True
        else:
            return False


    def display_tray(self):
        # !!!!!
        # NOTE: this is called from BOTH GUI and worker thread
        # !!!!!

        # Gtk is not thread safe. If we aren't the GUI thread, schedule this soon to
        # occur on the GUI thread.
        if ppglobals.GUI_THREAD_ID == thread.get_ident():
            # we're safe, just do it.
            self._display_tray_gui_callback()
        else:
            glib.idle_add(self._display_tray_gui_callback)


    def _display_tray_gui_callback(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        # ---------------------------------------------------------
        #  Pump out numbers in tool tray graphic -
        #   Do not display graphics unless ATC is present and communicating
        #   Reflect the tool numbers in the tray
        #   Tools are displayed in their actual tray locations
        #   If the atc is not operational , all tools are ' '
        #   If prime is true, also populate the auto and manual DRO's, otherwise do not
        #    in case they are masked
        #    Returns:
        #      None
        # -----------------------------------------------------------

        with self.pocket_dict_rlock:
            if self.hal["atc-device-status"]:  # will not be set until ATC binds and sets firmware
                self.refresh_pocket_dict()
                dslot = 0
                current_slot = int(self.hal["atc-tray-position"])
                self.status.poll()
                self.map_graphics()  #call every time in case ATC plugged in after reset
                for i in range (current_slot, current_slot+self.hal["atc-tools-in-tray"]):
                    tool= self.pocket_dict[str(i % self.hal["atc-tools-in-tray"])]
                    display_text = tool            #for now - can be over writen below
                    if int(tool) == self.status.tool_in_spindle and int(tool) > 0 : display_text = '*'  #it's in the spindle
                    if (display_text == '0') or (not self.operational): display_text = ' '  #no atc or unassigned slot

                    self.atc_pocket_list['atc_carousel_'+ str(dslot)].set_text(display_text)
                    self.atc_pocket_list['atc_carousel_'+ str(dslot)].queue_draw()
                    dslot = dslot + 1


    def lookup_slot(self, tool_number):
        # !!!!!
        # NOTE: this is called from BOTH GUI and worker thread
        #       do not add any code that touches Gtk objects in here
        # !!!!!

        # ---------------------------------------------------------
        #  Find a slot for  a tool -
        #   Refresh the data from redis, look up slot
        #    Returns an integer:
        #     -1  no slot, tool not in tray
        #      >= 0 slot number
        # -----------------------------------------------------------

        with self.pocket_dict_rlock:
            if tool_number == 0: return -1  #tool zero never has a slot
            self.refresh_pocket_dict()
            for i in range(self.hal["atc-tools-in-tray"]):
                if (self.pocket_dict[str(i)] == str(tool_number)): return i
            return -1 #not found


    def refresh_pocket_dict(self):
        # !!!!!
        # NOTE: this is called from BOTH GUI and worker thread
        # !!!!!

        # ---------------------------------------------------------
        #  ATC tray table data base retrieval and set up -
        #    if there is no prior table in the data base - build it default change_z to 0,
        #     and current slot to 0 as well.
        #    else load the table from the db
        # -----------------------------------------------------------
        with self.pocket_dict_rlock:
            try:
                self.pocket_dict = self.redis.hgetall('zbot_slot_table')  #let's get the table from the data base
                test = self.pocket_dict.get('0')                          #returns None if key not defined
                if test is None:
                    # redis hash not yet defined - initialize
                    for i in xrange(20):
                        self.pocket_dict[str(i)] = '0'
                        self.redis.hset('zbot_slot_table',str(i),'0')  #zero it out
                    self.redis.hset('zbot_slot_table','current_slot','0')  # toto too!
                    self.redis.hset('zbot_slot_table', 'tool_change_z','0.0')  # this means unset

                    self.pocket_dict = self.redis.hgetall('zbot_slot_table')  #let's get the table from the data base

            except Exception as e:    #  warn if redis is broken
                self.error_handler.write("Execption while attempting to initialize tool table data of type %s: %s" % (type(e), e.args), ALARM_LEVEL_DEBUG)


    def validate_tool_number(self, widget):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        # Can ONLY be called on the GUI thread as it calls on Gtk objects
        try:
            tool_number = int(widget.get_text())
            if (0 <= tool_number <= MAX_NUM_MILL_TOOL_NUM):
                set_alarm_appearance(widget, False)
                return True, tool_number, ''
            else:
                set_alarm_appearance(widget, True)
                return False, '', 'Invalid tool number: %d - out of range' % (tool_number)
        except ValueError:
            set_alarm_appearance(widget, True)
            return False, 0, 'Invalid tool number: %s' % (widget.get_text())


    def clear(self):
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!
        #----------------------------------------------------------------------------
        #  Clear spindle area
        #  If the tray is in we need to verify a bunch of stuff to avoid crashing things
        #  If the Z axis is hanging out in the middle of the shank with the tray in:
        #         Fire the draw bar
        #         Jog off the shank
        #         Set spindle tool to  T0
        #  Now we are safe for the next tool change, tray rotation, etc..
        #
        #  Returns:
        #          True -  all clear
        #          False - HAL returned an error, or Z not referenced - not clear
        #----------------------------------------------------------------------------
        if not self.hal["atc-tray-status"]:
            return True   #always safe at tray out
        #when tray is in- lots of things to verify
        self.scale_variables()   #get jog length right
        self.status.poll()
        if self.status.homed[2]:
            where_we_are = self.status.actual_position[2]  #always in machine units = inches

            try:
                bottom_limit = self.redis.hget('zbot_slot_table', 'tool_change_z')
            except:
                self.error_handler.write("ATC - tool change z location must be set before proceeding",ALARM_LEVEL_MEDIUM)
                return False
              #see if spindle is hanging out on dangerouse plane
            bottom_limit = float(bottom_limit)
            if bottom_limit is None or (bottom_limit > -1.5 and bottom_limit < -5.5):  #change Z has not been set
                self.error_handler.write("ATC - tool change z location must be set before proceeding",ALARM_LEVEL_MEDIUM)
                return False

            if self.hal["atc-tray-status"]  and where_we_are < (bottom_limit) + self.tool_shank_jog_imperial:      #is the tray in

                self.error_handler.write("ATC - Ejecting tool, clearing spindle", ALARM_LEVEL_DEBUG)  #middle to shank
                if not self.hey_hal(ATC_DRAW_BAR,ATC_ACTIVATE): return False    #fire draw bar
                if not self.go_to_z(0.0): return False  #elevator to the top
                self.firmly_issue_mdi("M61 Q0")          #clear the active tool             #clear the active tool

            return True
        else:
            self.error_handler.write("ATC - Cannot clear tray, Z must be referenced ",ALARM_LEVEL_MEDIUM)
            return False

    def index_from_gui(self, slot, stuff_insert_and_fetch_dros=False):
        # !!!!
        # NOTE: this is called from BOTH GUI and worker thread
        # !!!!

        #----------------------------------------------------------------------------
        #  Rotate the tray
        #  Set DRO's in GUI to reflect current tray slot
        #  Pump out the tray display immediately, so user doesn't see a .5 second delay
        #     Returns:
        #          True -  tray indexed
        #          False - HAL returned an error
        #----------------------------------------------------------------------------
        if not self.hey_hal(ATC_INDEX_TRAY,slot):
            return False

        # Gtk is not thread safe. If we aren't the GUI thread, schedule this soon to
        # occur on the GUI thread.

        if ppglobals.GUI_THREAD_ID == thread.get_ident():
            # We're safe - just call it directly
            self._index_from_gui_callback(slot, stuff_insert_and_fetch_dros)
        else:
            # We have to schedule a callback on the GUI thread.
            glib.idle_add(self._index_from_gui_callback, slot, stuff_insert_and_fetch_dros)

        return True

    def _index_from_gui_callback(self, slot, stuff_insert_and_fetch_dros):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()

        with self.pocket_dict_rlock:
            if (self.pocket_dict[str(slot)] != '0') and stuff_insert_and_fetch_dros:
                if self.hal["atc-tray-status"]:
                    # only stuff the auto fecth DRO when tray is out
                    self.dro_list['atc_manual_insert_dro'].set_text(self.pocket_dict [str(slot)])
                    self.dro_list['atc_manual_insert_dro'].queue_draw()
                    self.dro_list['atc_auto_dro'].set_text('')
                    self.dro_list['atc_auto_dro'].queue_draw()
                else:
                    self.dro_list['atc_manual_insert_dro'].set_text('')
                    self.dro_list['atc_manual_insert_dro'].queue_draw()
                    self.dro_list['atc_auto_dro'].set_text(self.pocket_dict [str(slot)])
                    self.dro_list['atc_auto_dro'].queue_draw()

        self.display_tray()


    def mdi_and_wait(self, mdi_command):
        self.command.mode(linuxcnc.MODE_MDI)
        self.command.wait_complete()
        self.command.mdi(mdi_command)
        self.command.wait_complete()
        return True


    def firmly_issue_mdi(self, mdicmd):
        # the code previously used self.issue_mdi() alone for most mdi commands.
        # but through painful troubleshooting, discovered that sometimes issue_mdi() ignores the
        # command because it thinks the machine is in a bad state.
        # this may be stale data so try pretty hard in here for 5 seconds to get the
        # mdi issued and yell in the logs if it isn't.
        st = timer.Stopwatch()
        success = False
        while not success and st.get_elapsed_seconds() < 5:
            self.status.poll()
            success = self.issue_mdi(mdicmd)
            st.lap()
            if not success:
                time.sleep(0.1)

        if st.lapcounter > 1:
            self.error_handler.write("firmly_issue_mdi took awhile - {:s}".format(st), ALARM_LEVEL_DEBUG)


    def go_to_z(self, location, slow_speed = False):
        #assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        #-------------------------------------------------------------------------------------------------------------------
        #   Here in ATC land we only deal in absolute or machine locations. And we only move when we know where we are
        #       If we are in feed hold (only in a thread), we wait for someone to hit cycle_start
        #       Note that an optional speed variable has been added - to move at a predefined slow
        #       jog speed (primarily used for jogging down the tool shank on faster machines like MX)
        #         THIS IS CURRENTLY NOT NEEDED FOR ANY MOVES INITITED BY THE GUI, but support is there for it
        #       Check for  Z axis homed
        #       MDI with G53 for machine coordinates in G90 mode.  Will cancel G91,then restore it
        #       Wait for arrival
        #
        #      Returns:
        #          True -  arrived
        #          False - Z isn't referenced, or timed out on arrival
        #----------------------------------------------------------------------------------------------------------------------
        rc = False                             #defaut return code

        self._wait_for_feed_hold_to_clear()    # spin until cycle start

        self.status.poll()
        if self.status.gcodes[linuxcnc.G_CODE_DISTANCE_MODE] == 910 :
            restore_G91 = True           # let's remember to put this back if we
        else :                           # have to
            restore_G91 = False

        if self.status.homed[2]:

            if slow_speed:   #not currently needed for GUI functions, but supported
                cmd = 'G1 G90 G53 Z' + str(location) + 'F' + str(self.jog_speed)
            else:
                cmd = 'G0 G90 G53 Z' + str(location)

            self.error_handler.log('ATC go_to_z trying to issue MDI {:s}'.format(cmd))
            self.firmly_issue_mdi(cmd) #go to specified location
            if self.wait_on_z_arrival(location):
                rc = True            #only way to get a good rc is to move and arrive
        else:
            self.error_handler.write('ATC - Z must be referenced to proceed', ALARM_LEVEL_MEDIUM)

        if restore_G91:
            self.firmly_issue_mdi('G91')       #set it back to user's prior state

        return rc


    def cycle_start(self):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        #-------------------------------------------------------------------------------------------------------------------
        #   Do ATC stuff when cycle start is hit
        #       See if someone hit the button while in the middle of a thread for no reason (not in feedhold) -
        #           note : if we are in feedhold during NGC processing, the GUI will not call us
        #       If the tray is in:
        #
        #          Return to caller with 'trau in'  - GUI will issue warning message
        #
        #
        #       Returns characters:
        #           None      -     all clear
        #          'tray in' -      tray could not be cleared for whatever reason - usually caller will notify user
        #          'queue active' - in  a thread, don't know what to do here
        #-------------------------------------------------------------------------------------------------------------------
        if not self.process_queue.empty(): return 'queue active'
        if not self.hal["atc-tray-status"]:  return ''  #all clear

        #self.error_handler.write('ATC - Tray is in, auto ejecting before cycle start', ALARM_LEVEL_LOW)
        self.error_handler.write('ATC detected tray in at Cycle_Start...safely ejecting & retracting first', ALARM_LEVEL_DEBUG)
        if not self.clear(): return 'tray in'
        if not self.hey_hal(ATC_SOLENOID, -ATC_TRAY_SOLENOID): return 'tray in'
        return ''  #all clear


    def hey_hal(self,command,data):
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!

        #-------------------------------------------------------------------------------------------------------------------
        #   Check for preemption - stop or reset while threading. self.stop_reset is only set if a thread was in progress
        #       see  tormach_mill_ui :: set_response_cancel
        #
        #   Check for ATC device available via hal-bsuy pin, set HAL command and data pins, wait for finish. Post error message if problems.
        #       see constants.py - HAL pin commands - for request pin. & ATC Data map  - for NGC request_data pin
        #
        # Returns:
        #
        #    False : status code from hal-return pin was negative
        #                 --see  constants.py HAL COMPONENT RC VALUES
        #                       or
        #            user cancelled via STOP/RESET
        #
        #    True : command send , success posted from HAL on hal-return pin
        #
        #-------------------------------------------------------------------------------------------------------------------

        if self.stop_reset.is_set():
            self.stop_reset.clear()                 #reset this flag
            self.purge_queue()
            self.hal_errors(ATC_USER_CANCEL)        #pump out a cancellation message
            return False

        if self.general_error.is_set():
            self.general_error.clear()                 #reset this flag
            self.purge_queue()
            self.hal_errors(ATC_GENERAL_ERROR)        #pump out a cancellation message
            return False

        self._wait_for_feed_hold_to_clear()

        st = timer.Stopwatch()
        available  = False
        if self.tracing:
            self.error_handler.write('WAIT FOR ATC FREE', ALARM_LEVEL_DEBUG)
        while (st.get_elapsed_seconds() < 1.0): # max wait for ATC to get done with whatever is was doing
            if (not self.hal["atc-hal-busy"]):  # it could be sensing, but that doesn't take long
                available = True
                break
            time.sleep(.020)
            continue

        if not available:
            self.error_handler.write('ATC - Device busy', ALARM_LEVEL_LOW)
            return False
        if self.tracing:
            self.error_handler.write('SENDING ATC COMMAND', ALARM_LEVEL_DEBUG)
        # set up data for getting atc component working for us, component will echo sequence number when done

        self.request_sequence_number += 1.0    #get unique sequence number going for this request
        if self.tracing:
            self.error_handler.write('sequence sent :' + str(self.request_sequence_number) + " command : " + str(command) + " data : " + str(data), ALARM_LEVEL_DEBUG)
        self.command.mode(linuxcnc.MODE_MDI)   #make sure we are switched out of auto before setting motion control output pin
        self.command.wait_complete()
        self.command.set_analog_output(ATC_HAL_SEQ_NO_OUT_PIN_NO , self.request_sequence_number) #set request number pin
        self.command.set_analog_output(ATC_HAL_DATA_OUT_PIN_NO,data) #set request number pin
        self.command.set_analog_output(ATC_HAL_COMMAND_OUT_PIN_NO ,command) #set request number pin
        self.command.wait_complete()

        #self.hal["atc-hal-data"] = data
        #self.hal["atc-hal-request"] = command
        # time.sleep(.050)  # give command a little time to take

        answer = False

        # now wait for the new request sequence to be returned by HAL

        st.restart()
        for ii in xrange(500):    # 500 loops of 20 millis is 10 seconds worth of waiting
            self.status.poll()
            if self.status.ain[ATC_HAL_SEQ_NO_IN_PIN_NO] == self.request_sequence_number:
                answer = True
                #if self.tracing : self.error_handler.log("sequence back: %s  times in loop %d" % (str(self.status.ain[ATC_HAL_SEQ_NO_IN_PIN_NO]), ii))
                break  # wait for the match exit

            #if (not self.hal["atc-hal-busy"]):  # wait for the drop
            #    answer = True
            #   break  # wait for the drop

            time.sleep(.020)  # 20 millis
            st.lap()

        if not answer:
            self.error_handler.log('timeout error follows, command = {:s} {:s} {:s} {:s}'.format(str(command), str(data), str(self.request_sequence_number), st))
            self.hal_errors(ATC_TIMEOUT_ERROR)

        if self.hal["atc-hal-return"] >= 0.0:
            return True

        if command == ATC_OFFSET_HOME:
            self.hal["atc-hal-return"] = ATC_REF_FIRST  #if offset is used before ref, use better error msg

        self.hal_errors(int(self.hal["atc-hal-return"]))
        return False


    def hal_errors(self,error_no):   #simply display the message from the input index value
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!
        error_msg = ATC_HAL_MESSAGES[error_no]
        self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)



    def scale_variables(self):
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!
        #------------------------------------------------------------------------------------------------------
        #     Check that Z is referenced
        #     Validate the tool change Z is set
        #     Scale ATC variables (kept in inches -see constants.py   ATC/TTS DIMENSIONS)
        #       Returns:
        #          True - variables scaled
        #          False - problem with tool change Z
        #     Tool shank length is returned in imperial only as well to check spindle nose for interference
        #        before retracting or rotating the tray.
        #-------------------------------------------------------------------------------------------------------
        self.status.poll()
        if not self.status.homed[2]:
            self.error_handler.write('ATC - Z must be referenced to proceed', ALARM_LEVEL_MEDIUM)
            return False

        try:
            self.change_z = float(self.redis.hget('zbot_slot_table', 'tool_change_z'))
            if (self.change_z > -1.5 or self.change_z < -5.5):   # gotta be in the zone, man
                self.change_z = 0
        except:
            self.change_z = 0

        if self.change_z == 0:
            self.error_handler.write('ATC - tool change z not set', ALARM_LEVEL_MEDIUM)
            return False


        self.compression    =  ATC_COMPRESSION      #squish constant
        self.blast_distance =  ATC_BLAST_DISTANCE      #distance from tool holder rim
        self.tool_shank_jog =  ATC_SHANK_JOG_TTS       #tool shank height defaults TTS
        self.jog_speed      =  ATC_JOG_SPEED           # Feed rate for G1 moves in M400 (NGC REMAP)

        # ISO20 unsupported yet
        #if int(self.redis.hget('machine_prefs', 'spindle_type')) == SPINDLE_TYPE_HISPEED:
        #    self.tool_shank_jog = ATC_SHANK_JOG_ISO20     #give it some more room for ISO 20



        if self.machineconfig.spindle_collet_type() == machine.MachineConfig.COLLET_BT30_WITH_DOGS:
            self.tool_shank_jog = ATC_SHANK_JOG_BT30

        # This should probably be converted to an .ini / redis key vs. model number magic
        if '440' in self.machineconfig.model_name():
            self.compression = .020

        #inches
        if self.status.program_units == 1:
            self.scale_factor = 1.0
        #mm
        if self.status.program_units == 2:
            self.scale_factor = 25.4
        #cm
        if self.status.program_units == 3:
            self.scale_factor = 2.54

        self.change_z  =        self.change_z * self.scale_factor
        self.blast_distance  =  self.blast_distance* self.scale_factor
        self.compression =      self.compression * self.scale_factor
        self.tool_shank_jog_imperial = self.tool_shank_jog
        self.tool_shank_jog =   self.tool_shank_jog * self.scale_factor
        self.jog_speed =        self.jog_speed * self.scale_factor
        return True



    def m6_cycle(self, new_tool, go_to_tray_load = False):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        tl_segment = ' Q-1 ' if go_to_tray_load  else ''  # tray load easter egg

        self.firmly_issue_mdi('M6 T'+ str(new_tool) + tl_segment + 'G43')  # Use NGC routines thru remap
        time.sleep(.5)                                #allow interpreter to start up

        # wait for tool to arrive or interpreter to exit
        st = timer.Stopwatch()
        while True:
            self.status.poll()
            st.lap()
            if self.status.interp_state == linuxcnc.INTERP_IDLE:
                self.error_handler.write("m6_cycle() complete, {:s}".format(st), ALARM_LEVEL_DEBUG)
                break           # new tool is in spindle
            time.sleep(0.1)     # 100 millis



    def prompt_OK_Cancel(self,text):    #come here when draw bar is retracted for T0 in spindle -
                                     # this commonly happens when user puts a tool in spindle manually but doesnt update tool DRO
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        try: #purge any leftover responses in message queue
            self.redis.hdel("TormachAnswers", "Start_Pressed")  #clear the tracks, new train coming
            self.redis.rpush("TormachMessage", text + "$$REPLY_TEXT$$")
            self.error_handler.log('ATC - worker thread just pushed to redis msgq :' + text)
        except:
            self.error_handler.log('ATC - Redis message queue is broken!', ALARM_LEVEL_DEBUG)
            return False

        st = timer.Stopwatch()
        while True:
            reply = self.redis.hget("TormachAnswers", "Start_Pressed")
            if (reply):
                self.error_handler.log("ATC - worker thread just pulled from redis msgq {:s}".format(reply))
                self.redis.hdel("TormachAnswers", "Start_Pressed")
                break
            time.sleep(0.1)  # 100 millis
            st.lap()

        self.error_handler.log('prompt for msg wait was {:s}'.format(st))
        return (reply == 'Y')


    def prompt(self, tool_no, direction):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        #-----------------------------------------------------------------------------------------------------------
        #   Prompting :
        #        Most longer running button responses run in a state machine thread. See self.process_the_queue.
        #        GTK is not
        #        thread safe, merely thread aware, which means user managment of locking (not fun to do). Rather than
        #        deal with that nonsense, we use redis to queue messages to be  handled by the 500ms periodic update
        #        routines in the main GUI. So, WARNING WILL ROBINSION! - ONLY CALL THIS FROM A THREAD OR IT WILL WAIT FOREVER!!!!!
        #        If prompting from the main GUI thread, its safe to call the file_utility directly.
        #
        #        Prompt messages have this form -
        #            "Answer Key:kkkkkkkk:mmmmmmmmmm"
        #                 where kkkkkk is the redis has key to contain the reponse, and mmmmmmm is the message text
        #
        #        The main gui thread will retrieve this and convert it into a file_utility call. Once answered, the answer key
        #        hash tag will be used to store a 'Y' for OK, or '!' for CANCEL.  direction is True is for prompting in, False for prompting out
        #
        #        Returns :
        #             True -  OK
        #             False - CANCEL
        #------------------------------------------------------------------------------------------------------------------

        # set proper message , main gui will substitue spaces for *, and appropriate message for $$REPLY_TEXT$$
        # depending on whether it is sending the message to Gremlin or pop display

        if direction:
            if tool_no == 0:
                # Customers getting confused when it says to Insert T0 in spindle which is 'operator speak' for remove tool from spindle.
                # So let's just be obvious about it.
                msg_text = "AnswerKey:Start_Pressed:Remove tool from spindle, $$REPLY_TEXT$$"
            else:
                msg_text = "AnswerKey:Start_Pressed:Insert T" + str(tool_no) + " in spindle, $$REPLY_TEXT$$"
        else:
            msg_text ="AnswerKey:Start_Pressed:Remove T" + str(tool_no) + " from spindle, $$REPLY_TEXT$$"

        try:
            self.redis.hdel("TormachAnswers", "Start_Pressed")  #clear the tracks, new train coming
            self.redis.rpush("TormachMessage", msg_text)       #send it off on its way to main GUI thread
            self.error_handler.log('ATC - worker thread just pushed to redis msgq {:s}'.format(msg_text))
        except:
            self.error_handler.write('ATC - Redis message queue is broken!', ALARM_LEVEL_DEBUG)
            return False

        # now thread waits forever - user can always be at lunch. STOP/RESET will always clear
        st = timer.Stopwatch()
        while True:
            reply = self.redis.hget("TormachAnswers", "Start_Pressed")
            if (reply):
                self.error_handler.log("ATC - worker thread just pulled from redis msgq {:s}".format(reply))
                self.redis.hdel("TormachAnswers", "Start_Pressed")
                break
            time.sleep(0.1)  # 100 millis
            st.lap()

        self.error_handler.log('prompt wait was {:s}'.format(st))
        return (reply == 'Y')


    def stop_reset_check(self):
        #assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        if self.stop_reset.is_set() or self.general_error.is_set():                     #preempt thread
            self.stop_reset.clear()
            self.purge_queue()
            self.error_handler.write('ATC - Action cancelled by STOP/RESET', ALARM_LEVEL_MEDIUM)
            return False

        return True


    def _wait_for_feed_hold_to_clear(self):
        #TODO: Why is this commented out???  assert ppglobals.GUI_THREAD_ID != thread.get_ident()

        if not self.feed_hold_clear.is_set():
            st = timer.Stopwatch()
            self.feed_hold_clear.wait()  # block gracefully until cycle start is signaled from GUI thread
            self.error_handler.log('ATC waited for feed_hold to clear {:s}'.format(st))


    def wait_on_z_arrival(self, location):
        #assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        #----------------------------------------------------------------------------------------------------
        #       After issuing a move request this guy waits for the machine to stop moving
        #       We can also preempt or feed hold a thread while in the middle of a move,
        #       We give a move about 20 seconds
        #
        #       with_blast_location == true initiates a blast at a given location
        #
        #         Returns:
        #              True  - we have arrive, as they say
        #              False - not arrived, cancelled, bad day for Zs
        #----------------------------------------------------------------------------------------------------
        blasted = False
        tah_dah = False    # set timeout return
        for i in xrange(200):

            if not self.stop_reset_check():
                return False    #preempt the thread

            self.status.poll()
            if abs(self.status.actual_position[2]*self.scale_factor - location ) < .01:
                self._wait_for_feed_hold_to_clear()    # spin until cycle start
                tah_dah = True
                break

            time.sleep(.1)
            continue

        if not tah_dah:
            self.error_handler.write('ATC - Z destination not reached - aborting operation', ALARM_LEVEL_MEDIUM)

        return tah_dah


    def queue_dispatch(self,tuple_in):
        assert ppglobals.GUI_THREAD_ID == thread.get_ident()
        #---------------------------------------------------------------------------------------
        # Generic work queueing method checks for a dead thread in case program or syntax error
        #   croaked it. If so, it is restarted before next work item is dispatched to the thread
        #     Input - a data tuple to be queued
        # Most ATC functions will not queue behind others, except tray jogging, which can stack up
        #   for execution.
        #---------------------------------------------------------------------------------------

        if not self.off_load_thread or not self.off_load_thread.is_alive():   # start the worker thread if not alive and ticking
            self.purge_queue()                    # in case of restart, let's not choke again
            self.off_load_thread = threading.Thread(name="ATCworker", target=self.process_the_queue)  #get a new worker bee
            self.off_load_thread.start()          # start fresh and clean - begins at process_the_queue
            self.error_handler.write('Z-Bot ATC: worker thread {} id={:d}'.format(self.started_msg, self.off_load_thread.ident), ALARM_LEVEL_DEBUG)
            self.started_msg = 'restarted'      # change wording for the next time through this code (if ever)

        #don't allow stack up of button presses except fwd and rev tray
        if not self.in_a_thread.is_set() or tuple_in[0] == 'do_tray_fwd' or tuple_in[0] == 'do_tray_rev' or 'ref' in tuple_in[0]:
            # create a new tuple where the current wall clock time is the first element
            # that way it is easy to tell how much time a command has been sitting in the queue
            # when we pull the command off the queue, we throw away the first tuple time element.
            timed_list = [time.time(), tuple_in]
            self.process_queue.put(timed_list)      # yum! - delicious new work to do
        else:
            self.error_handler.write("ATC: Ignoring %s because worker thread is busy and it isn't a fwd/rev/ref related" % tuple_in[0], ALARM_LEVEL_DEBUG)


    def process_the_queue(self):
        assert ppglobals.GUI_THREAD_ID != thread.get_ident()
        #----------------------------------------------------------------------------------------------------
        #   ATC command state machine -
        #   Question : Why are we doing this?
        #   Answer:    We don't want the GUI to go deaf while running long running stuff
        #
        #   At startup a worker thread is initiated here to process a work queue.
        #   Items are put on the work queue by GTK button call backs for execution in this worker thread
        #   This keeps the GUI available for buttons to be pressed. You know, stuff like RESET or CANCE or FEEDHOLD
        #   in the middle of things.  Kind of important, eh?  That's why all this muss and fuss.
        #   Each callback will queue a simple item up for processing. The queue request is always right above the "self.do_*"
        #   to make the code readable, but these routines are dispatched here.
        #   The logic is pretty simple, "wash, rinse, repeat" as they say on shampoo. This one is "read,process, wait", standard
        #   state machine logic.
        #   A special message for termination is used when the system shuts down which purges any queued requests.  Any errors
        #   occuring in queue will purge subsequent requests.  This happens when a user presses a button n times, and one of the <n
        #   units of work fails. This is the safe way to go.
        #   This guy doesn't return until the day is done or it blows up from a syntax error or exception. In
        #   that case the caller will restart it before queuing a new work item.
        #
        #       Returns : none
        #----------------------------------------------------------------------------------------------------
        try:

            while True:  #boogie till ya puke!

                # The queue.get efficiently blocks this thread until work is added.
                # The first element of the queue item is the time it was added to the queue
                timed_list = self.process_queue.get()
                queue_wait_time = time.time() - timed_list[0]
                # Throw away the enqueue time and reform the original tuple.
                work_item = timed_list[1]

                self.error_handler.write("ATC: %s pulled from q, wait time %f" % (work_item[0], queue_wait_time), ALARM_LEVEL_DEBUG)

                if work_item[0] == 'terminate':
                    break                          #hang it up today
                self.in_a_thread.set()             #now let's find some work

                if work_item[0] == 'do_fwd':
                    r = self.atc_fwd_thread()
                elif work_item[0] == 'do_rev':
                    r = self.atc_rev_thread()
                elif work_item[0] == 'do_tray_load':
                    r = self.go_to_tray_load_position_thread()
                elif work_item[0] == 'do_fetch':
                    r = self.fetch_thread(work_item[1]) # pass in dro
                elif work_item[0] == 'do_remove':
                    r = self.remove_thread(work_item[1]) # pass in dro
                elif work_item[0] == 'do_store':
                    r = self.store_thread() # pass in dro
                elif work_item[0] == 'do_home':
                    r = self.home_tray_thread()
                elif work_item[0] == 'do_ref_x':
                    r = self.ref_x_thread()
                elif work_item[0] == 'do_ref_y':
                    r = self.ref_y_thread()
                elif work_item[0] == 'do_ref_z':
                    r = self.ref_z_thread()
                elif work_item[0] == 'do_ref_a':
                    r = self.ref_a_thread()
                elif work_item[0] == 'do_touch_tray':
                    r = self.touch_entire_tray_thread()
                elif work_item[0] == 'do_tray_fwd':
                    r = self.tray_fwd_thread()
                elif work_item[0] == 'do_tray_rev':
                    r = self.tray_rev_thread()
                elif work_item[0] == 'do_offset_tray_pos':
                    r = self.offset_tray_pos_thread()
                elif work_item[0] == 'do_offset_tray_neg':
                    r = self.offset_tray_neg_thread()
                elif work_item[0] == 'do_blast':
                    r = self.blast_thread()
                elif work_item[0] == 'do_drawbar_up':
                    r = self.set_drawbar_up_thread()
                elif work_item[0] == 'do_drawbar_down':
                    r = self.set_drawbar_down_thread()
                elif work_item[0] == 'do_retract':
                    r = self.retract_thread()
                elif work_item[0] == 'do_blast_off':
                    r = self.blast_off_thread   #kill blaster
                else:
                    r = False
                    self.error_handler.write("ATC: unknown q item %s  !!!!!" % work_item[0], ALARM_LEVEL_DEBUG)

                self.process_queue.task_done()  # this one's done
                if r == False:                 # how'd it go?
                    self.purge_queue()          # no so good? hang it up then  - don't compound the problem
                #reset all threading flags
                self.in_a_thread.clear()     #no longer in a thread
                self.stop_reset.clear()      #reset not active
                self.feed_hold_clear.set()   #feedhold is not active
                self.general_error.clear()  #cancel any errors
                self.command.set_digital_output(ATC_HAL_IS_CHANGING, 0)  # in case we did an M6


            self.error_handler.write('Z-Bot ATC : WORKER thread exiting', ALARM_LEVEL_DEBUG)

        except Exception as e:
            traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
            self.error_handler.write("Z-Bot ATC : Error in WORKER thread!  %s" % traceback_txt, ALARM_LEVEL_DEBUG)

            self.in_a_thread.clear()     # we're goin down brother!


    def purge_queue(self):
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!

        #----------------------------------------------------------------------------------------------------
        #   ATC command state machine - purge queue
        #   Question : Why are we doing this?
        #   Answer:    To throw out anything in queue at shutdown or during errors
        #
        #   All work requests are thrown out, EXCEPT a termination request.  If this is in the queue
        #    the worker thread will return.
        #-----------------------------------------------------------------------------------------------------

        put_it_back = False                    #until we find a terminate command
        while not self.process_queue.empty():  #got work to purge
            # The first element of the queue item is the time it was added to the queue
            timed_list = self.process_queue.get()
            queue_wait_time = time.time() - timed_list[0]
            # Throw away the enqueue time and reform the original tuple.
            work_item = timed_list[1]

            if work_item[0] == 'terminate':
                put_it_back = True  #you can't hide!

        if put_it_back:   # don't swallow a shutdown!
            self.terminate()


    def terminate(self):
        # !!!!
        # NOTE This is called from both GUI and worker threads
        # !!!!

        # This is called above, but also from the mill UI on the way down.  We don't want the mill UI
        # knowing the details of queue element structures so encapsulate all that here.
        self.process_queue.put([time.time(), ('terminate', None)])  #shut down worker bee


def set_alarm_appearance(widget, alarm=True):
    assert ppglobals.GUI_THREAD_ID == thread.get_ident()
    if alarm:
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('yellow'))
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('red'))
    else:
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
