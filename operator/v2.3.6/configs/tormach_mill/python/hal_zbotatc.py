#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


import hal, time
import serial
import redis
import os
import sys
import tormach_file_util
import linuxcnc
import multiprocessing
import datetime
import errors
import timer
import traceback


# global constants from Tormach UI
from constants import *



class zbotatc_hal_component():
    def __init__(self):


        self.error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

        self.error_handler.log("Z-Bot ATC: HAL component : started")

        # Global housekeeping

        self.is_sim_config = False
        self.status = linuxcnc.stat()
        self.command = linuxcnc.command()
        self.redis = redis.Redis()

        # always delete any old information on firmware.
        # UI will look for this key to exist on startup and perform version comparision.
        if self.redis.hexists('zbot_atc_info', 'firmware_version'):
            self.redis.hdel('zbot_atc_info', 'firmware_version')

        self.atc_s_cmd= 0
        self.hal = hal.component("zbotatc")
        self.request_in = 1.0
        self.last_request_in = 0.0
        self.fromNGC = False
        self.old_speed = 0                     #VFD detector
        self.tools_in_tray = 10                #set at to device
        self.board_version = 0                 #version of board
        # The ATC firmware can only deal with PULSE or LEVEL, but we have three distinct
        # modes (PULSE, LEVEL, or NONE).  So keep these straight.
        # All are uppercase unless we map over into ATC firmware command and response strings
        # which use Level and Pulse and vl and vp.
        self.vfdmode_in_firmware = None        # PULSE or LEVEL
        self.vfdmode = None                    # PULSE, LEVEL, or NONE
        self.reconfigure_count = 0             # number of attempts to reset profile
        self.pass_go_balance = 0               # bank account to keep track of full rotations past home
        self.spindle_type = 0                  # 0 = TTS, 1 = BT30
        self.OK_to_connect = True              # try to connect to board
        self.saved_spindle_lock = False        # prior state of spindle lock pin
        self.got_things_to_do = False          # there's work to be done now
        self.OK_to_set = True                  # don't keep trying to set before next release
        self.sol4_release_at = time.time()+(10**11)  # epoch time in secs to release solenoid 4
        self.saved_spindle_state = 0           # saved spindle state
        self.spindle_starting = False          # set for first time

        # remove any stale info on firmware version since we currently have no idea what might be there
        self.redis.hdel('zbot_atc_info', 'firmware_version')

        #########################################################
        # initialization logic
        #########################################################

        self.hal.newpin('vfd-running', hal.HAL_FLOAT, hal.HAL_IN)

        # debug level inputs from UI
        self.hal.newpin('debug-level', hal.HAL_U32, hal.HAL_IN)

        #hal inputs for command control from NGC
        self.hal.newpin(ATC_HAL_REQUEST_NGC, hal.HAL_FLOAT, hal.HAL_IN)       #command
        self.hal.newpin(ATC_HAL_REQUEST_DATA_NGC, hal.HAL_FLOAT, hal.HAL_IN)  #data

        #hal inputs for command control from GUI
        self.hal.newpin(ATC_HAL_REQUEST_GUI,hal.HAL_FLOAT, hal.HAL_IN)        #command code
        self.hal.newpin(ATC_HAL_REQUEST_DATA_GUI, hal.HAL_FLOAT, hal.HAL_IN)  #data code

        #hal input from motion control (spindle lock function from lxcnc M19)
        self.hal.newpin(ATC_REQUEST_SPINDLE_LOCK,hal.HAL_BIT, hal.HAL_IN)  # motion control spindle-locked
        self.hal.newpin(ATC_READ_ORIENT_STATUS,hal.HAL_FLOAT, hal.HAL_IN)  # encoder drift
        self.hal.newpin(ATC_READ_ORIENT_EXECUTE,hal.HAL_BIT, hal.HAL_IN)   # orient in progress

        # hal outputs for flow and command control
        self.hal.newpin(ATC_HAL_BUSY,hal.HAL_BIT, hal.HAL_OUT)            # busy now
        self.hal.newpin(ATC_HAL_REQUEST_ACK, hal.HAL_FLOAT, hal.HAL_OUT)  # command request sequence no
        self.hal.newpin(ATC_HAL_RC, hal.HAL_FLOAT, hal.HAL_OUT)           # return code

        # hal pins output  - status outputs

        self.hal.newpin(ATC_HAL_TRAY_POS, hal.HAL_FLOAT, hal.HAL_OUT)     #current tray slot
        self.hal.newpin(ATC_HAL_TRAY_STAT, hal.HAL_BIT, hal.HAL_OUT)      # tray cylinder
        self.hal.newpin(ATC_HAL_VFD_STAT, hal.HAL_BIT, hal.HAL_OUT)       # vfd running
        self.hal.newpin(ATC_HAL_DRAW_STAT, hal.HAL_BIT, hal.HAL_OUT)      # draw solenoid
        self.hal.newpin(ATC_HAL_LOCK_STAT, hal.HAL_BIT, hal.HAL_OUT)      # draw solenoid
        self.hal.newpin(ATC_HAL_TRAYREF_STAT, hal.HAL_BIT, hal.HAL_OUT)   # tray referenced or not status
        self.hal.newpin(ATC_PRESSURE_STAT, hal.HAL_BIT, hal.HAL_OUT)      # pressure switch
        self.hal.newpin(ATC_HAL_DEVICE_STAT, hal.HAL_BIT, hal.HAL_OUT)    # comms up?
        self.hal.newpin("atc-tools-in-tray", hal.HAL_U32, hal.HAL_OUT)      # tools in tray

        # spindle speed for 440
        self.hal.newpin("vfd-rpm",hal.HAL_U32,hal.HAL_OUT)     #actual VFD spindle speed output

        # hal component is ready to roll
        self.hal.ready()

        #constructs for USB communication threading
        self.tx_queue = multiprocessing.Queue()    #work queue for send
        self.rx_queue = multiprocessing.Queue()    #work queue for receive
        self.USB_comms_thread = multiprocessing.Process(name='ATC USB/IO Service', target=self.process_the_queue)  #isolate IO to USB
        self.comms_up = multiprocessing.Event()    #requires  both threads to see
        self.start_msg_suffix = 'starting '        #message qualifier - changes to restarting after first time

        self.hal[ATC_HAL_REQUEST_NGC]=  0            # 0 = no requested work to do now
        self.hal[ATC_HAL_REQUEST_GUI] = 0

        #prime next time to update sensor output
        self.sensor_time = time.time()

        # super handy for log perusal
        self.log_commandnames = {
            ATC_SOLENOID:'ATC_SOLENOID',
            ATC_DRAW_BAR:'ATC_DRAW_BAR',
            ATC_INDEX_TRAY:'ATC_INDEX_TRAY',
            ATC_QUERY_SENSOR:'ATC_QUERY_SENSOR',
            ATC_FIND_HOME:'ATC_FIND_HOME',
            ATC_OFFSET_HOME:'ATC_OFFSET_HOME',
            ATC_REPORT_STATUS:'ATC_REPORT_STATUS',
            ATC_SPINDLE_LOCK:'ATC_SPINDLE_LOCK'
        }

        self.log_usbcommandnames = {
            USB_VERSION:'USB_VERSION',
            USB_TRAY_IN:'USB_TRAY_IN',
            USB_TRAY_OUT:'USB_TRAY_OUT',
            USB_BLAST_ON:'USB_BLAST_ON',
            USB_BLAST_OFF:'USB_BLAST_OFF',
            USB_DB_ACTIVATE:'USB_DB_ACTIVATE',
            USB_DB_DEACTIVATE:'USB_DB_DEACTIVATE',
            USB_STATUS:'USB_STATUS',
            USB_FIND_HOME:'USB_FIND_HOME',
            USB_OFFSET_UP:'USB_OFFSET_UP',
            USB_OFFSET_DOWN:'USB_OFFSET_DOWN',
            USB_DRAW_HIGH_PRESS:'USB_DRAW_HIGH_PRESS',
            USB_DRAW_LOW_PRESS:'USB_DRAW_LOW_PRESS'
        }
        for ii in range(12):
            self.log_usbcommandnames[USB_INDEX_TRAY + str(ii) + '\r' ] = 'USB_INDEX_TRAY {:d}'.format(ii)
        self.log_usbcommandnames[USB_QUERY + str(ATC_PRESSURE_SENSOR) + '\r'] = 'USB_QUERY ATC_PRESSURE_SENSOR'
        self.log_usbcommandnames[USB_QUERY + str(ATC_TRAY_IN_SENSOR) + '\r'] = 'USB_QUERY ATC_TRAY_IN_SENSOR'
        self.log_usbcommandnames[USB_QUERY + str(ATC_TRAY_OUT_SENSOR) + '\r'] = 'USB_QUERY ATC_TRAY_OUT_SENSOR'
        self.log_usbcommandnames[USB_QUERY + str(ATC_VFD_SENSOR) + '\r'] = 'USB_QUERY ATC_VFD_SENSOR'
        self.log_usbcommandnames[USB_QUERY + str(ATC_DRAW_SENSOR) + '\r'] = 'USB_QUERY ATC_DRAW_SENSOR'

        self.suppress_idle_logging = False

        self.hal_command = 0
        self.hal_command_data = 0
        #=====================================================================================
        #      DISPATCH COMMAND DICTIONARY
        #           each command has an associated function
        #======================================================================================

        self.command_dispatch = { 0 : self.no_op_func,
                                  ATC_SOLENOID : self.solenoid_func,
                                  ATC_DRAW_BAR : self.draw_bar_func,
                                  ATC_INDEX_TRAY : self.index_func,
                                  ATC_QUERY_SENSOR : self.query_func,
                                  ATC_FIND_HOME : self.home_func,
                                  ATC_OFFSET_HOME : self.offset_func,
                                  ATC_REPORT_STATUS : self.report_func,
                                  ATC_SPINDLE_LOCK : self.no_op_func } #ignore spindle lock as ATC NGC/GUI command
                                                      #  See spindle_lock_control()

    def zbotatc_main(self):    #main line logic

    # MAIN HAL LOOP

        while True:

            #-------------------------------------------------------------------------------------------------
            #  set hal atc device status pin at each iteration through the loop
            #-------------------------------------------------------------------------------------------------
            if self.comms_up.is_set():
                self.hal[ATC_HAL_DEVICE_STAT] = True   # now we're talkin'
            else:
                self.hal[ATC_HAL_DEVICE_STAT] = False
                time.sleep(2)     # give the gui time to switch to manual change or for user to fix it up
            #------------------------------------------------------------------------------------------------
            #  Retrieve tormach mill configuration data from redis and set tool change type
            #  default to manual. When tool change is manual mode,  slow loop down to check for changes in status
            #  every second. Users can enable the ATC in mid session, or vice-Versa
            #-------------------------------------------------------------------------------------------------
            try:
                toolchange_type = self.redis.hget("machine_prefs", "toolchange_type")
            except:
                # this execption happens if there is no database persistence data
                toolchange_type = MILL_TOOLCHANGE_TYPE_REDIS_MANUAL

            if (toolchange_type != MILL_TOOLCHANGE_TYPE_REDIS_ZBOT):
                time.sleep(1)    # wait a full second
                continue

            #------------------------------------------------------------------------------------------------
            #  This is the auto changer main process state machine.
            #
            #    Communications are first checked, If the mill is in E-Stop/Reset mode, no attempt is made to reconnect,
            #    and the state machine remains in limbo until the machine is taken out by Reset.
            #    Two attempts are made to reconnect twice before posting an error to the requester. In case of communication failures
            #    a return code is set, and a HAL pin is lit to indicate that ATC is down.
            #
            #    Work can come in on the GUI pins, or the NGC pins depending on who is in control of the mill
            #    NGC always takes precedence, but they should really be mutually exclusive in practice
            #    If no work is requested, and the mill isn't running a part program or ngc subrouting via MDI
            #    the component will read the status of the draw bar, vfd, and pressure inputs
            #    and set output hal status pins accordingly.
            #
            #    During dispatching of work, the HAL busy pin is lit so that requesters don't overrun each other.  It's
            #    the responsiblity of the requester to make sure the component is not busy. Requests are not queued. The component
            #    is a state machine.
            #
            #    All units of work MUST start by setting the busy pin, dispatching a unit of work, then WITHOUT EXECPEPTION
            #    must end by setting a condition code, and resetting the busy pin. self.reset_and_return performs this function
            #    for all work.
            #-------------------------------------------------------------------------------------------------

            #lets get talking here....comms is False first time through
            if not self.comms_up.is_set():

                #connect if no prior catastrophe
                if self.OK_to_connect:
                    self.connect_to_device()


                if not self.comms_up.is_set():   # still no luck with connection?
                    self.reset_and_return(ATC_NOT_FOUND)  # return in error to user
                    continue                             #do not try anything else this time

            #====================================================================================
            #  Capture lxcnc state, and load up command and data control variables
            #   and us
            #=====================================================================================
            self.status.poll()
            self.got_things_to_do = self.farm_inputs()  # are there things to work on?

            #======================================================================
            #  Handle spindle lock out requests from motion control first
            #======================================================================
            self.spindle_lock_control()

            #=======================================================================
            # Update periodic data on HAL device status pins for GUI when we are
            # not running a part program
            #=======================================================================
            if not self.got_things_to_do:
                self.atc_periodic_update()

            #---------------------------------------------------------------------------------------
            #  Unit of work dispatcher-
            #    Requesters command and data are in self.hal_command, and self.hal_command_data respectively
            #    The command is associated with a function object in the dispatcher dictionary
            #    Some commands go through from the top again without returning to the user becuase they
            #      retry after a command is rejected due to a state that needs correcting.
            #----------------------------------------------------------------------------------------

            if self.got_things_to_do:

                if (self.hal['debug-level'] & DEBUG_LEVEL_ATC) != 0:
                    if self.hal_command in self.log_commandnames:
                        self.error_handler.log("ATC: HAL new request RECEIVED req num: %s  command: %s  data: %s" % (str(self.request_in), self.log_commandnames[self.hal_command], str(self.hal_command_data)))
                    else:
                        self.error_handler.log("ATC: HAL new request RECEIVED req num: %s  command: %s  data: %s" % (str(self.request_in), str(self.hal_command), str(self.hal_command_data)))

                #====================================================================================
                #  Every command request from the GUI or the ATC NGC remap has a unique sequence number
                #  When the requester sees their sequence number returned via HAL ACK pin, they know the
                #  work is done.
                #  The actual function executed is retrieved from the command_dispatch dictionary
                #=====================================================================================
                self.request_in = self.status.aout[ATC_HAL_SEQ_NO_OUT_PIN_NO]
                self.hal[ATC_HAL_BUSY] = True    #signal busy - new requests should wait for ATC to be free
                command_function = self.command_dispatch.get(self.hal_command,self.unknown_func)
                if command_function == None:   # who sent in garbage?
                    self.error_handler.log("ATC: Invalid ATC command %s" % self.hal_command)
                    r = ATC_INTERNAL_CODE_ERROR
                else:
                    r = command_function()    # execute function from lookup

                self.reset_and_return(r)

            time.sleep(.020)                 # lets not gobble all the cpu here
            #   END MAIN HAL LOOP - play it again SAM!

    def spindle_lock_control (self) :

        #==================================================================================================
        # First off - if this isn't a spindle with a lock - return
        #
        # See if it's time to close the pressure solenoid to reduce it's
        #    duty cycle.  It only needs to be on when brake is set, and for a few seconds
        #    after the draw bar is released to open a path to the exhaust port.  After the PDB
        #    is fully up, the exhaust port can close, as all air is exhausted. We allow 3 seconds.
        #
        # See if motion control wants us to lock the spindle
        #       After M19 is successfully completed, motion.spindle-locked will assert
        #       and stay asserted until the next M3,M4 or M5 which unlocks
        #
        # Spindle pneumatics are also released to let spindle run (M3,M4) or orient (M19)
        #   NOTE: If the brake was previously set, M19 will explicitly release it
        #         However, motion control is unaware of the PDB being on.  So we simply
        #         check for a change in spindle state and release the PDB if in  transition
        #         to on.
        #
        # This logic will release the spindle when required in all cases.
        #===================================================================================================

        if self.spindle_type == 0 : return         # don't do anything if not a locking spindle

        # time to release the pressure solenoid after open for exhaust ?
        if time.time() >= self.sol4_release_at:     #Did we pop the timer to release
            self.smart_solenoid (ATC_SPDL_LK_SOLENOID, ATC_OFF) # does first second tick
            self.error_handler.log("Z-Bot ATC: Pressure solenoid auto closed after exhaust")
            self.sol4_release_at = time.time()+(10**11) # cancel repeats - you'll not live this long!

        pneuma_state = 'do nothing'
        r1=r2=0        # default return codes if nothing actuates

        # capture a rising edge of spindle state

        if self.saved_spindle_state != self.status.spindle_enabled :
            self.saved_spindle_state = self.status.spindle_enabled   #record new state as saved
            if self.status.spindle_enabled == 1 : self.spindle_starting = True  # true for rising edge



        # is motion control setting lock ?
        if self.hal[ATC_REQUEST_SPINDLE_LOCK] :
            pneuma_state = 'set'

        # is spindle trying to run or orient now?
        elif self.spindle_starting \
             or (self.hal[ATC_READ_ORIENT_EXECUTE] and not self.hal[ATC_REQUEST_SPINDLE_LOCK]):
            pneuma_state = 'release'        # schedule the release
            self.spindle_starting = False   # reset the rising edge trigger

        #lastly, regardless of above, catch a lock release
        if self.saved_spindle_lock != self.hal[ATC_REQUEST_SPINDLE_LOCK]\
            and not self.hal[ATC_REQUEST_SPINDLE_LOCK]:
            pneuma_state = 'release'

        if pneuma_state == 'set' and self.OK_to_set:
            # report any goofy data values coming out of spindle component
            self.OK_to_set = False # unless reset by motion control - do not reset the lock again
            pre_lock_error = int(self.hal[ATC_READ_ORIENT_STATUS])
            if abs(pre_lock_error) > 7:
                self.error_handler.log("ATC: Spdl lock requested, orient_status value : = %d" % (pre_lock_error))

            r1 = self.smart_solenoid (ATC_SPDL_LK_SOLENOID, ATC_OFF) #switch to low pressure
            r2 = self.smart_solenoid (ATC_DRAW_BAR_SOLENOID, ATC_ON)
            if r2 == 1:
                time.sleep(.75)

        if pneuma_state == 'release' :
            self.OK_to_set = True         # OK to set after this - not before
            r1 = self.smart_solenoid (ATC_DRAW_BAR_SOLENOID, ATC_OFF) # Release lock
            if r1 == 1:
                time.sleep(.25)  # Open B port of db solenoid, this one must switch off first to prevent eject
            r2 = self.smart_solenoid (ATC_SPDL_LK_SOLENOID, ATC_ON)  # now exhuast path from A side
            self.sol4_release_at = time.time() + 3.0  # and schedule release in 3 secs
            if r2 == 1:
                time.sleep(.5)

        if (r1 < 0) or (r2 < 0):
            self.error_handler.write('Spindle lock solenoid failure - aborting program.', ALARM_LEVEL_MEDIUM)
            self.command.abort() #abort program
            self.command.wait_complete()

        # what's new is old
        self.saved_spindle_lock = self.hal[ATC_REQUEST_SPINDLE_LOCK]

    def farm_inputs(self) :
        #clear all input data
        self.hal_command = 0
        self.hal_command_data = 0

        #get GUI request - these guys are all pure motion control analog output pins set by linuxcnc command channel in GUI
        if self.status.aout[ATC_HAL_COMMAND_OUT_PIN_NO]!= 0.0:
            self.hal_command = int(self.status.aout[ATC_HAL_COMMAND_OUT_PIN_NO])  #get command
            self.hal_command_data = int(self.status.aout[ATC_HAL_DATA_OUT_PIN_NO]) #get data
            self.fromNGC = False
            return (True)
        #===========================================================================================
        #NGC program  is mutually exclusive of GUI work.
        #these guys are NETed to analog output pins, set by NGC interface in the POST GUI HAL file.
        #We cannot reset any of these analog- out pins when the program is in auto mode when the process is done
        #like we do in the GUI case, but we can reset our own components pins.
        #============================================================================================
        if self.hal[ATC_HAL_REQUEST_NGC] != 0.0:
            self.hal_command = int(self.hal[ATC_HAL_REQUEST_NGC])  #get command
            self.hal_command_data = int(self.hal[ATC_HAL_REQUEST_DATA_NGC]) #get data
            self.fromNGC = True                        #bypass setting aout pin values when done - it's verbotten!
            return (True)

        return (False)     # true - work, false - no work

    def atc_periodic_update(self):
        #=============================================================================
        #  I'm SOOOOOOOOOOOOOOOO bored... nothing to do at the moment -
        #    update hal pins for Tormach GUI status at half second intervals
        #=============================================================================

        if self.status.interp_state == linuxcnc.INTERP_IDLE and self.comms_up.is_set():
            if time.time() >= self.sensor_time:     #time to sense?
                self.suppress_idle_logging = True   #no body REALLY want's to see this
                self.query_sensors(ATC_ALL_SENSORS_LIST)   # get all hal status pins updated now
                self.get_tray_pos()                          # suck tray pos out of redis
                self.sensor_time = time.time()+.5   #schedule next on
                self.suppress_idle_logging = False  #really, they don't


    #============================================================================================
    # All these functions are called from the command dispatcher
    #=============================================================================================
    def no_op_func(self):
        return(0)


    def solenoid_func(self):

        #don't check pressure when turning off the blast solenoid
        if  self.hal_command_data != -1 * ATC_BLAST_SOLENOID:
            r = self.pressure_check()
            if r < 0:         # we don't have pressure here or other errors
                return(r)

        if ( self.hal_command_data == ATC_TRAY_SOLENOID):
            r = self.smart_solenoid (ATC_TRAY_SOLENOID, ATC_ON)
            if r < 0:
                return(r)

            #check for arrival and set status appropriate to sensor pin checked
            if r == 1:  # anything happen?
                r = self.check_cylinder_arrival(ATC_TRAY_IN_SENSOR)


        elif ( self.hal_command_data == -1* ATC_TRAY_SOLENOID):
            r = self.smart_solenoid (ATC_TRAY_SOLENOID, ATC_OFF)
            if r < 0:
                return(r)

            # check for departure and set status
            if r == 1 :    # did something?
                r = self.check_cylinder_arrival(ATC_TRAY_OUT_SENSOR)


        elif (self.hal_command_data == ATC_BLAST_SOLENOID):
            r = self.send_command(command=USB_BLAST_ON)
            time.sleep(.5)
            r = self.send_command(command=USB_BLAST_OFF)

        elif (self.hal_command_data == -1*ATC_BLAST_SOLENOID):
            r = self.send_command(command=USB_BLAST_OFF)


        elif ( self.hal_command_data == ATC_SPDL_LK_SOLENOID):    # this isn't used by anyone
                                                                #  it's there for terminal testing
            r = self.smart_solenoid (ATC_SPDL_LK_SOLENOID,ATC_OFF) #switch to low pressure

        elif ( self.hal_command_data == -1* ATC_SPDL_LK_SOLENOID):
            self.smart_solenoid (ATC_SPDL_LK_SOLENOID, ATC_ON)      #switch to high pressure

        return (r)

    def draw_bar_func (self):

        r = self.pressure_check()
        if r < 0:         # we don't have pressure here or other error
            return (r)

        #----------------------------------------------------------------------
        #   Draw bar (tool release) operations run with high air pressure selected
        #     on S3 machines without a 4th solenoid, no harm is done by actuating
        #     Both operation require the high pressure gate open, one to actuate
        #     the other to provide a path to exhuast port
        #
        #          High pressure gate control - on for high,and exhaust PDB
        #    Open high pressure gate, leave it open for activate
        #    but remember to close it in 3 seconds after deactivate
        #    to reduce duty cycle on solenoid coil.
        #-----------------------------------------------------------------------
        r1 = self.smart_solenoid (ATC_SPDL_LK_SOLENOID, ATC_ON)
        if r1 < 0: return r1
        if r1 == 1 :
            time.sleep (.125)    #let this fully open

        if (self.hal_command_data == ATC_DEACTIVATE ):
            r2 = self.smart_solenoid (ATC_DRAW_BAR_SOLENOID, ATC_OFF)
            self.sol4_release_at = time.time() + 3.0  # reset LK_SOLENOID in 3 seconds
            if r2 < 0: return r2     # oh crap!


        elif (self.hal_command_data == ATC_ACTIVATE):
            r2 = self.smart_solenoid (ATC_DRAW_BAR_SOLENOID, ATC_ON)
            if r2 < 0: return r2     # double crap!

        else:     #Hey!
            self.error_handler.log("ATC - Invalid draw bar argument")
            return ATC_INTERNAL_CODE_ERROR

        #----------------------------------------------------------------
        #  In all cases let the mechanism settle in if anything actuated
        #----------------------------------------------------------------
        if r2 == 1:                      # db solenoid activated - then wait for
            time.sleep(1.0)             # mechanism reaction time

        return (ATC_OK)

    def index_func(self):

        index_slot = str(self.hal_command_data)  #hal command_data has slot # to index to

        #-----------------------------------------------------------------------------
        #Alas and alack, the circumference of 10 and 12 tool trays do not lie on an even step boundaries.
        #This code tracks the balance of home position traversals in each direction.
        #If this gets out of balance by more than 10 , the tray will be rehomed
        #to prevent accumulation of the fractional step deficit or abundance.  The accumulated error is
        #never allowed to exceed approx .010 inches linear dstance on circumference,
        #Skip all this malarky if firmware is handling (board versions 2 and higher).
        #Skip code if 8 tool tray - it's well behaved on even step boundries.
        #----------------------------------------------------------------------------

        if self.tools_in_tray != 8 and self.board_version < 2:  # no firmware support for this in old boards
            #-----------------------------------------------------------------------
            # Flatten the circle to an ascending number line, and eliminate slot 0 as
            # as destination by shifting all slots right on an imaginary number line.
            # ie, if you wrap past 12, on a 12 tool tray, slot 1 becomes 13 and so on...
            #-----------------------------------------------------------------------
            half_circle = self.tools_in_tray/2
            destination = (self.hal_command_data + 1)
            source = int(self.hal[ATC_HAL_TRAY_POS]) + 1
            passing_origin = False  # until we learn differently

            if abs (destination-source)>half_circle:  # see if move takes us through tick mark
                passing_origin = True        #only these go through home
                if source < destination :    #now divine out direction
                    source  += self.tools_in_tray      # adjust wrap to move negative
                else:
                    destination += self.tools_in_tray  # adjust wrap to move positive

            #--------------------------------------------------------------------
            # compute move vector - direction and magnitude
            #--------------------------------------------------------------------
            tool_move = destination - source     # uses relocated, wrap adjusted number line
            #--------------------------------------------------------------------
            # now keep tallies of home traversals, by tracking the traversals
            #--------------------------------------------------------------------
            if passing_origin :
                if tool_move > 0 :
                    self.pass_go_balance += 1
                    self.error_handler.log("ATC: Pass Go +, now at  " + str(self.pass_go_balance))
                if tool_move < 0 :
                    self.pass_go_balance -= 1
                    self.error_handler.log("ATC: Pass Go -, now at  " + str(self.pass_go_balance))
            #--------------------------------------------------------------------
            # now trigger a rehome before indexing if wandering too far past center
            # which results from an imbalance of "pass go" traversals
            #--------------------------------------------------------------------
            if abs(self.pass_go_balance) > 10:  #about .015 linear inches on circumference
                self.error_handler.log("ATC: Pass Go Monitor- Rehoming")
                r = self.home_func()                #let's rehome to get centered
                if r < 0:
                    return (r)           #crap!

        #=====================================================================
        #  now index to designated tray slot
        #=====================================================================
        r = self.send_command(command=USB_INDEX_TRAY+index_slot+"\r",timeout=2)

        if (r == ATC_OK ):                    #tray indexed just fine
            self.set_tray_pos(self.hal_command_data)  #record it in REDIS and hal

        #================================================================================
        # at fresh restart or machine power down/up, homing occurs before first index op
        # ATC firmware returns reject if attempting to index while un-homed
        #=================================================================================
        if (r == ATC_COMMAND_REJECTED_ERROR): #whoops! looks like home is not established
            r = self.home_func()                #let's rehome
            if r < 0:
                return (r)        # double crap!
            # this time, get it right......home is good
            r = self.send_command(command=USB_INDEX_TRAY+index_slot+"\r",timeout=2) #redrive index
            if (r == ATC_OK ):                    #tray indexed just fine
                self.set_tray_pos(self.hal_command_data)  #record it in REDIS and hal

        #------------------------------------------------------------------------------
        # IMPORTANT :only way out to requester - index operation exits with return code
        #------------------------------------------------------------------------------
        return (r)

    def query_func (self):
        sensor_list = list()                        #instantiate a list
        if ( self.hal_command_data != ATC_ALL_SENSORS):   #specific sensor requested in data
            sensor_list.append(self.hal_command_data)  #stuff it in there
        if ( self.hal_command_data == ATC_ALL_SENSORS):
            sensor_list = ATC_ALL_SENSORS_LIST
        return (self.query_sensors(sensor_list))

    def home_func(self):
        r = self.send_command(command=USB_FIND_HOME, timeout = 10)
        if (r == ATC_OK):
            self.set_tray_pos(0)
            self.pass_go_balance = 0
        else:
            r = ATC_USB_HOMING_ERROR
        return (r)

    def offset_func(self):
        s_command = USB_OFFSET_UP                            # go this way
        if ( self.hal_command_data == ATC_SET_DOWN): s_command = USB_OFFSET_DOWN    # go that way
        return (self.send_command(command=s_command,timeout = .25))

    def report_func(self):
        status_data = ''
        status_data = self.send_command(USB_STATUS)
        self.error_handler.log("ATC: STATUS = %s" % str(status_data))
        return (0)

    def unknown_func(self):
        # not a recognized command- log and return
        self.error_handler.log("ATC: requested hal function not recognized: {:d}".format(self.hal_command))
        return (ATC_UNKNOWN_REQUESTED_PIN)
    #============================================================================================
    # End ofcalled from the command dispatcher
    #=============================================================================================



    def smart_solenoid (self,solenoid,set_state):
        #=============================================================================
        #  The draw bar solenoid,pressure solenoid, and tray in solenoids involve
        #    movement and wait times.
        #    Due to long wait times for the mechanisms to settle in we don't want to
        #    fire the solenoids unless it is necessary.
        #
        #   It is also desireable  to encapsulate this intelligence in the HAL component
        #   so that the tool changer NGC doesn't have to worry about it.
        #      RETURNS  <0, error   0 nothing done    1 solenoid actuated
        #================================================================================

        #variable dictionary - logic is same, only the names change. Query sensor expects a list
        solenoid_variables = {ATC_DRAW_BAR_SOLENOID : [[ATC_DRAW_SENSOR],USB_DB_ACTIVATE,USB_DB_DEACTIVATE],\
                              ATC_SPDL_LK_SOLENOID  : [[ATC_LOCK_SENSOR],USB_DRAW_HIGH_PRESS,USB_DRAW_LOW_PRESS],\
                              ATC_TRAY_SOLENOID     : [[ATC_TRAY_IN_SENSOR],USB_TRAY_IN,USB_TRAY_OUT]}

        #load variables to use for various solenoids
        sensor_list,activate_command,deactivate_command = solenoid_variables.get(solenoid)

        #get current state
        if sensor_list == None :     #invalid request
            self.error_handler.log("ATC: Invalid solenoid name")
            return ATC_INTERNAL_CODE_ERROR        #wtf - no solenoids by that name
        sensor_data = self.query_sensors(sensor_list)

        # lucky day - there already  off is off, on is on  OR
        # are we doing the lock solenoid, but there is none for this spindle type?
        if sensor_data == set_state or (solenoid == ATC_SPDL_LK_SOLENOID and self.spindle_type != 1):
            return ATC_OK       #nada to do, state is already set

        #actuate mechanism
        if set_state == ATC_ON:           # it's off but needs to be on
            r2 = self.send_command(activate_command,timeout =.5)  # send command
        else:                             # it's on but needs to be off
            r2 = self.send_command(deactivate_command,timeout =.5) # send command

        if r2 < 0: return r2    # something ain't right

        return 1                # return if solenoid had to be repositioned



    def check_cylinder_arrival(self, sensor_number):  #sensor 3 for in, 5 for out (phantom)
        #==========================================================================
        #checks arrival at inbound or dowsed inbound sensor to signal it's out
        #  always delays .65 seconds before checks begin to prevent premature
        #  crash of mill head into carousel if out sensor reports positive falsely
        #  ATC_TRAY_OUT_SENSOR is a phantom, since we are dropping support.It is signalled
        #  by tray in sensor being off - sorta the same thing since it rarely sticks midstream
        #=========================================================================
        #set logical condition to test - postive or negative from in sensor, for in, out, respectively
        checkstate = ATC_SENSOR_ON     #default check
        if sensor_number == ATC_TRAY_OUT_SENSOR: checkstate = ATC_SENSOR_OFF # look for inverse
        time.sleep (.65)      # wait minimum traversal time
        for i in range(40):   # thumb twiddle for 2.0  secs or so
            r = self.query_sensors([ATC_TRAY_IN_SENSOR])
            if r < 0:
                break              # this is a bad thing
            if (r == checkstate):  # we got satisfaction - sorry Mick!
                break              # stop the thumb twiddling
            wait_time = .050       # first wait longer giving it time to arrive


        #only acceptable outcome is checkstate -not really using tray out sensor
        if r == checkstate:
            self.set_hal_output_status(ATC_TRAY_IN_SENSOR ,r)  # set tray in status pin

            if (self.hal['debug-level'] & DEBUG_LEVEL_ATC) != 0:
                self.error_handler.log("ATC: check cylinder arrival = success")

            return 0  #all is well


        #the rest are suspicious
        if (r != ATC_SENSOR_ON and sensor_number == ATC_TRAY_IN_SENSOR) or (r != ATC_SENSOR_OFF and sensor_number == ATC_TRAY_OUT_SENSOR):
         # io error or plain old not arrived, do safety retract
            self.error_handler.log("ATC: cylinder sensor not reporting - auto retract, return = %s" % str(r))
            self.send_command(command=USB_TRAY_OUT)    # send it from whence it came
            #self.set_hal_output_status (ATC_TRAY_IN_SENSOR,0)  # dowse tray in status pin
            return ATC_TRAY_ERROR

        if (self.hal['debug-level'] & DEBUG_LEVEL_ATC) != 0:
            self.error_handler.log("ATC: check cyclinder arrival = abnormal exit?")


    #---------------------------------------------------------------------------------------
    #  Terminate the unit of work here by setting HAL pins
    #    Always set busy off for GUI and NGC requesters. Unless busy is off, no more work is
    #    done today.
    #    Always post the return code
    #
    #----------------------------------------------------------------------------------------

    def reset_and_return(self, r):
        self.hal[ATC_HAL_REQUEST_NGC] = 0                          #reset until next NGC command updates
        if not self.fromNGC:                                       # cannot do this in auto mode
            self.command.set_analog_output(ATC_HAL_COMMAND_OUT_PIN_NO ,0) #reset set GUI command pin, not during NGC execution
            self.command.wait_complete(2.0)                         # don't let motion control ruin your day, wait 2 secs
        self.hal[ATC_HAL_RC] =      r                               # post return code
        self.hal[ATC_HAL_BUSY] =    False                           # dowse the busy flag
        self.hal[ATC_HAL_REQUEST_ACK] =  self.request_in            # set ack = request number - this signals requester that work is done


    #========================================================================
    #  HAL output pins are set according the the sensor number passed in
    #========================================================================

    def set_hal_output_status(self, sensor_no, rc):

        # sensor to hal pin name association -
        sense_pins_dict = { ATC_PRESSURE_SENSOR : ATC_PRESSURE_STAT,
                            ATC_TRAY_IN_SENSOR  : ATC_HAL_TRAY_STAT,
                            ATC_VFD_SENSOR      : ATC_HAL_VFD_STAT,
                            ATC_DRAW_SENSOR     : ATC_HAL_DRAW_STAT,
                            ATC_LOCK_SENSOR     : ATC_HAL_LOCK_STAT,
                            ATC_TRAYREF_SENSOR  : ATC_HAL_TRAYREF_STAT }

        if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0:
            self.error_handler.log("ATC: status of %s %s" % (str(sensor_no), str(rc)))

        hal_pin_name = sense_pins_dict.get(sensor_no, None)   #retrieve name from dict
        if hal_pin_name == None:
            self.error_handler.log("ATC: Invalid sensor %s" % sensor_no)
            return ATC_INTERNAL_CODE_ERROR

        self.hal[hal_pin_name]= rc                   # set HAL pin appropriately


    def pressure_check (self):
        r = self.query_sensors([ATC_PRESSURE_SENSOR]) #pressure is a good thing sometimes

        if  r == ATC_SENSOR_ON: # we don't have pressure here
            r = ATC_PRESSURE_FAULT  #change to meaningful error code

        return r


    #---------------------------------------------------------------------------------------
    #  Connect to the ATC USB device
    #----------------------------------------------------------------------------------------
    def connect_to_device(self):
        self.hal["atc-tools-in-tray"] = 10      #default if nothing found - some code in GUI  depends on a value
        self.comms_up.clear()                   # cancel communications
        self.start_IO_thread()                  #start up the service thread
        self.tx_queue.put('VE\r')               #queue up for thread to execute - runs in connect_to_device_thread

        # successful VE will set comms_up, and  returns a tuple in rx queue

        st = timer.Stopwatch()
        while st.get_elapsed_seconds() < 20.0:  #if can't connect in this time - hang it up
            time.sleep(.010)
            if self.comms_up.is_set():
                time.sleep(.050)
                atc_config = self.rx_queue.get()  # returns tuple (version no, tools in tray, pulse type, firmware version, bt30)

                # store the atc firmware version in redis so that the UI zbot atc code can check it and let the user
                # know if the firmware needs updating or not.  that process takes 5-10 minutes so it needs UI help and
                # this hal user comp can fight with the update process so that's why we do the firmware update up at the top
                # start script vs here.
                self.redis.hset('zbot_atc_info', 'firmware_version', atc_config[3])

                # I once saw in the log the redis.save() method toss an exception
                # of redis.exceptions.ResponseError: Background save already in progress
                # RedisError is the base class of all/most of everything redis can raise
                # so use that.
                try:
                    self.redis.save()   #force all data out
                except redis.exceptions.RedisError as e:
                    msg = "{0} occured, these were the arguments:\n{1!r}".format(type(e).__name__, e.args)
                    self.error_handler.log("ATC: caught a RedisError during save attempt: {:s}".format(msg))
                self.board_version = atc_config[0]
                self.hal["atc-tools-in-tray"] = self.tools_in_tray = atc_config[1]  # Binding to board returns tools in tray
                self.vfdmode_in_firmware = atc_config[2]
                self.spindle_type = atc_config[4]     #  1 if profile name is a BT30 type, else 0
                break

        #lot of drudgery here. Set ATC firmware to compatible mode for customers installing S4 ATC on any machine.
        #to newer ones. Only applies to V2 boards. In this case it must be set to VFD pulse mode.

        firmware_version = self.redis.hget('zbot_atc_info', 'firmware_version')
        if self.board_version >= 2 and firmware_version != 'Loader':

            #NOTE : Although logically cleaner, setting the configuration every time to machine type
            #       will burn out the flash memory on the ARM chip embedded
            #       in the ATC.  Therefore, we only update if required. Logic below
            #       checks for mismatches, and updates accordingly

            #configure atc to match mill  - allows customers to replace boards with generic device
            #following code will set it to match machine in tool numbers, vfd detection mode, and spindle type.

            # The mill updates the redis store with attributes about the current machine configuration.
            # We don't want any model specific knowledge here, we just want to read the attributes
            # that we care about and act accordingly.
            new_profile_needed = False
            slotcount = self.redis.hget('machine_config', 'atc_gen2_tray_slots')
            if slotcount:
                try:
                    slotcount = int(slotcount)
                    if slotcount != self.tools_in_tray:
                        self.error_handler.log("ATC slot count mismatch ({:d} vs {:d})".format(slotcount, self.tools_in_tray))
                        new_profile_needed = True
                        self.tools_in_tray = slotcount
                except ValueError:
                    self.error_handler.log("ATC unsupported value for redis machine_config key atc_gen2_tray_slots ({:s})".format(slotcount))
            else:
                # the board is a gen2 ATC but the current machine config does not support one
                # or it would contain a valid slot count.
                self.error_handler.log("ATC has gen2 board but redis machine_config does not contain atc_gen2_tray_slots key.")

            vfdmode = self.redis.hget('machine_config', 'atc_gen2_vfd_reporting')
            if vfdmode:
                if vfdmode not in ('PULSE', 'LEVEL', 'NONE'):
                    self.error_handler.log("ATC unsupported value for redis machine_config key atc_gen2_vfd_reporting key ({:s})".format(vfdmode))
                else:
                    # ATC firmware only knows about PULSE vs. LEVEL.
                    # For firmware profile sake, treat LEVEL and NONE the same until firmware is changed.
                    # But we operate differently for PULSE vs. LEVEL vs. NONE.
                    if self.vfdmode_in_firmware == 'LEVEL' and vfdmode == 'PULSE':
                        new_profile_needed = True
                        self.vfdmode_in_firmware = 'PULSE'
                    elif self.vfdmode_in_firmware == 'PULSE' and vfdmode in ('LEVEL', 'NONE'):
                        new_profile_needed = True
                        self.vfdmode_in_firmware = 'LEVEL'
                    self.vfdmode = vfdmode
            else:
                self.error_handler.log("ATC has gen2 board but redis machine_config does not contain atc_gen2_vfd_reporting key.")

            # clue in the simulated ATC control board what vfd mode we expect it to use
            if self.is_sim_config:
                self.atc_s_cmd.set_sim_vfdmode(self.vfdmode)

            spindlecollet = self.redis.hget('machine_config', 'spindle_collet_type')
            if spindlecollet:
                if spindlecollet not in('BT30_WITH_DOGS', 'TTS'):
                    self.error_handler.log("ATC unsupported value for redis machine_config key spindle_collet_type ({:s})".format(spindlecollet))
                else:
                    if spindlecollet == 'BT30_WITH_DOGS' and self.spindle_type != 1:
                        self.error_handler.log("ATC spindle type mismatch (BT30 vs. {:d})".format(self.spindle_type))
                        new_profile_needed = True
                        self.spindle_type = 1
                    elif spindlecollet == 'TTS' and self.spindle_type != 0:
                        self.error_handler.log("ATC spindle type mismatch (TTS vs. {:d})".format(self.spindle_type))
                        new_profile_needed = True
                        self.spindle_type = 0
            else:
                self.error_handler.log("ATC has gen2 board but redis machine_config does not contain spindle_collet_type key.")

            if new_profile_needed:
                # Prepare a proper profile name and send it off to board
                pulse_option = 'vp' if self.vfdmode_in_firmware == 'PULSE' else 'vl'
                bt30_option = '-bt30' if spindlecollet == 'BT30_WITH_DOGS' else ''
                command = '{:d}-tool-{:s}{:s}\r'.format(slotcount, pulse_option, bt30_option)

                self.error_handler.log('ATC profile mismatch  - setting to: {:s}'.format(command))
                r = self.send_command(command, 3.0)  # Give profile lots of time to load
                self.hal["atc-tools-in-tray"] = self.tools_in_tray  # post immediately for GUI
                if r == ATC_OK:
                    self.error_handler.log('ATC new profile set')
                    time.sleep(5.0)   # let it reboot

                else:
                    self.error_handler.log('ATC cannot set new profile - setting tool change manual')
                    self.comms_up.clear()   #cancel comms - proceed no further
                    self.OK_to_connect = False  # stop trying until humans help

    #=============================================================================
    #    Two attempts are made to connect to the device name established by the udev rules
    #    of the mill.
    #    A handshake is expected after sending the ATC board a VErsion command. If the device does
    #    don't comply we do not bind to it.
    #    Successful connection returns with comms_up true.  This is the only place that happens.
    #
    #=============================================================================
    def connect_to_device_thread(self):

        #process_the_queue will put the return value in the rx queue for caller

        self.status.poll()
        if self.status.task_state != linuxcnc.STATE_ON: return   # don't even try if machine isn't ready to roll
        try:
            self.atc_s_cmd.close()         #try closing the port -no biggie if failed
        except:
            pass                           #ignore failed close
        time.sleep(1)
        data = ''
        data2 = ''
        for attemptix in range(2):
            try:
                time.sleep(attemptix * 4)    # try twice, wait 4 seconds in between tries.
                if self.is_sim_config:
                    self.atc_s_cmd = SerialSim("/dev/zbot_atc", 57600, 0, self.redis)
                else:
                    self.atc_s_cmd = serial.Serial("/dev/zbot_atc", baudrate=57600, timeout=0)

                data = self.send_command_thread(USB_VERSION, 0.1)   # name, tools, vfd stuff
                data2 = self.send_command_thread(USB_VERSION_LONG, 2.0)   #profile name is buried in here

            except Exception as e:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.process_io_errors(traceback_txt)           #log it to std out

            if not isinstance(data, int):
                # Set all defaults to V1 board

                tools = 10   #default tools in tray if not found in data
                version = 1  #default board version
                vfd_reporting = 'LEVEL'  #default to level state vfd reporting
                spindle_type = 0  #default to TTS

                if 'Z-Bot Firmware Uploader' in data:
                    # If gen 2 boards got corrupted during firmware update due to power loss,
                    # they will be running just the boot loader. It replies with a different string
                    # to all commands (\n, VE\n, VL\n, etc)
                    version = 2   #board version
                    self.comms_up.set()
                    return (version, tools, vfd_reporting, 'Loader', spindle_type)

                elif 'Z-Bot A' in data:
                    self.error_handler.log('ATC: Firmware ID = %s' % data.strip())
                    self.error_handler.log('ATC: Firmware ID Long = %s' % data2.strip())

                    # For gen 2 boards and beyond, snag the firmware version
                    firmware_version = '?'
                    if 'Z-Bot Automatic Tool Changer II' in data:
                        datatuple = data.strip().split(' ')
                        firmware_version = datatuple[5]

                    ix1,ix2 = data.find('TOOLS:'),data.find("\r")  # mine tool number
                    if ix1 != -1 and ix2  != -1:
                        try:
                            version = 2                     #board version
                            tools   = int(data[ix1+6:ix2])  #number of tools in tray
                            vfd_reporting = 'LEVEL' if 'Level' in data else 'PULSE'
                            spindle_type = 1 if 'BT30' in data2 else 0  #spindle type coded for bt30

                        except Exception as e:
                            self.error_handler.log('ATC: error %s' % str(e))

                    # 440 report pulses for spindle activity. Other machines report a constant voltage or use hal pin
                    self.comms_up.set()
                    return (version, tools, vfd_reporting, firmware_version, spindle_type)

        if not self.comms_up.is_set():
            self.error_handler.log('ATC: device not found')

        return None


    def send_command(self, command="", timeout=1.0):
        global global_board_data
        trace_next_io = False

        if '\r' not in command:
            self.error_handler.log("USB COMMAND - NO CR : %s  " % (command))
            return ATC_UNKNOWN_USB_COMMAND_ERROR   #this wont ever fly

        for i in range(2) :                      # try once here,then again after thread restart

            if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0 or \
               ((self.hal['debug-level'] & DEBUG_LEVEL_ATC) != 0 and not self.suppress_idle_logging):
                if command in self.log_usbcommandnames:
                    self.error_handler.log("ATC: sending USB command {:s}".format(self.log_usbcommandnames[command]))
                else:
                    self.error_handler.log("ATC: sending USB command {:s}".format(command.strip()))

            self.tx_queue.put((command,timeout))  #executes code in send_command_thread, pass in IO timout
            loop_clicks = int((3 * timeout + .15)/.005) + 3   #give IO time for three full retries + 15 ms
            for i in range(loop_clicks):
                time.sleep(.005)
                if not self.rx_queue.empty():
                    r = self.rx_queue.get()             #pop (return code from send_command_thread)
                    if trace_next_io:
                        self.error_handler.log("ATC: REDRIVEN USB COMMAND + RC : %s %s" % (command.strip(), str(r)))  #for tracing redriven command

                    if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0 or \
                       ((self.hal['debug-level'] & DEBUG_LEVEL_ATC) != 0 and not self.suppress_idle_logging):
                        # maddening. sometimes r is an integer, sometimes its a string.  sigh.
                        if isinstance(r, str):
                            self.error_handler.log("ATC: received USB answer {:s}".format(r.strip()))
                        else:
                            self.error_handler.log("ATC: received USB answer {:d}".format(r))
                    #self.error_handler.log ('WE GOT DATA:' + global_board_data)
                    return r          #got an answer , good or bad - fire it back


            #thread timed out without responding in queue - which means thread hung as IO timeout should pop first
            #NOTE: this can happen from electrical spikes to the usb controller on mother board causing linux to abort thread
            self.error_handler.log("ATC: USB COMMAND - NO RESPONSE : %s  SEQ : %s" % (command[0:2], self.request_in))   #for tracing
            self.connect_to_device()         #attempt to re drive thread, reset the connection and retry
            trace_next_io = True             #print out recovery attempt please


        # drop through here is pretty serious stuff - no response from USB device, nada, NOTHING! TWICE!!!!!!
        return ATC_USB_IO_ERROR           #rats!,  no clue what's wrong



    #---------------------------------------------------------------------------------------
    #  Send a command to the ATC board via USB ( all USB commands except VE come here).
    #    Flush any left over crap in buffer
    #    Send the command
    #    Process response
    #    Return to the user
    #----------------------------------------------------------------------------------------

    def send_command_thread(self, command="", timeout=.050):
        # process_the_queue will propagate the return value to caller in rx_queue
        #global global_board_data
        while not self.tx_queue.empty(): self.tx_queue.get()  #purge all queues
        while not self.rx_queue.empty(): self.rx_queue.get()  #one in , one out, no exceptions!

        for i in range(3):            #3 tries allowed here, to get it right
            try:
                #----------------------------------------------------------------------------------------
                #  If EMI creates any artifacts in the input buffer of the ATC board, the \r will
                #  terminate the data, such that it will not be appended to the next legitimate command sent
                #-------------------------------------------------------------------------------------------
                self.atc_s_cmd.write('\r')           # terminate any EMI data in the board input buffer
                time.sleep(.010)                    # give board a click to puke anything back
                throw_out = ''
                throw_out = self.atc_s_cmd.read(256)  # discard anything responded
                if '?' in throw_out:
                    self.error_handler.log('ATC: DETECTED EMI IN BUFFER') # but log if EMI was in there

                self.atc_s_cmd.write(command)        #send off the real command

                if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0:
                    self.error_handler.log("ATC: USB CMD TX={}".format(command.strip()))

                time.sleep(.005)                    #wait a bit

                #---------------------------------------------------------------------------------------
                #    Read and interpret command responses -
                #    All answers from device terminate with a line feed character
                #    Parse data and set return code depending on content, no answer in time frame is a timeout
                #----------------------------------------------------------------------------------------
                data = ""                              #clear input buffer
                wait_attempts = int(timeout/.005 + 1)
                r = ATC_TIMEOUT_ERROR                  #until we know better
                while (wait_attempts > 0):             #everybody should wait at least once
                    if (data and '\n' in data):

                        if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0:
                            self.error_handler.log("ATC: USB CMD RX={}".format(data[:data.find('\r')]))

                        if "VE" in command \
                           or "ST" in command :
                           #don't analyze for response
                            r = data[:data.find('\r')+1]    #send up to carriage return
                            break                            #return the whole string

                        if  "VL" in command:
                            r  = data                        #get everything
                            break

                        if (data[0]== USB_OK):              #response is '.'
                            r = ATC_OK
                            break

                        if (data[0]== USB_ON):              #response is '+'
                            r =  ATC_SENSOR_ON               #sensor negative - like this too!
                            break

                        if (data[0]== USB_OFF):             #response is '-'
                            r =  ATC_SENSOR_OFF              #sensor positive - awesome!
                            break

                        if (data[0]== USB_REJECT):          #response is 'X'
                            r =  ATC_COMMAND_REJECTED_ERROR  #rejected operation - this might suck
                            if  command [0]!= 'T' and command [0] != 'H':  #normal response after power down
                                self.error_handler.log('ATC: X type command rejected, from : %s' % command.strip())
                            break

                        if (data[0]== USB_UNKNOWN ):        # response is '?'
                            r = ATC_UNKNOWN_USB_COMMAND_ERROR #invalid command - this definitely sucks! could be corrupted from EMI
                            self.error_handler.log('ATC: ? type command unknown, from : %s' % command.strip())
                            break                         #retry

                        r = ATC_UNKNOWN_USB_RESP_ERROR        #this sucks totally!!!!
                        break                         #but could be corrupted from EMI

                    else:
                        time.sleep(.005)
                        if "VL" in command :
                            time.sleep(.5)                #wait longer for the verbose shit

                        wait_attempts = wait_attempts - 1
                        data = data + self.atc_s_cmd.read(128)  #read some bytes
                        continue

            except Exception as e:
                traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                self.process_io_errors(traceback_txt)           #log it to std out
                r = ATC_USB_IO_ERROR    # io error - this one sticks if last attempt

            if r < 0:
                time.sleep(.050)           #let EMI settle down, if any caused this
                continue                    #try again , don't give up yet, stay and eat the food
            else:
                break                       #OK, now you can be excused from the table

        #retry while loop ends
        return r                        #go back to caller with return code -

    #---------------------------------------------------------------------------------------
    #  React to IO Errors
    #    Trapped errors end up here to print to stdout, turn comms_up off, and close the port
    #----------------------------------------------------------------------------------------

    def process_io_errors(self, e):
        self.error_handler.log("ATC: i/o error %s" % e)
        self.comms_up.clear()  #cancel comms




    #---------------------------------------------------------------------------------------
    #  Make tray position persistent across restarts
    #----------------------------------------------------------------------------------------

    def set_tray_pos(self, slot):
        self.hal[ATC_HAL_TRAY_POS] = slot # set output hal pin

        # I once saw in the log the redis.save() method toss an exception
        # of redis.exceptions.ResponseError: Background save already in progress
        # RedisError is the base class of all/most of everything redis can raise
        # so use that.
        try:
            self.redis.hset('zbot_slot_table', 'current_slot',str(slot)) #make it persistent
            self.redis.save()   #force all data out
        except redis.exceptions.RedisError as e:
            msg = "{0} occured, these were the arguments:\n{1!r}".format(type(e).__name__, e.args)
            self.error_handler.log("ATC: caught a RedisError during save attempt: {:s}".format(msg))

    def get_tray_pos(self):  #this routine only retrieves whats in REDIS
        # I once saw in the log the redis.save() method toss an exception
        # of redis.exceptions.ResponseError: Background save already in progress
        # RedisError is the base class of all/most of everything redis can raise
        # so use that.
        try:
            self.hal[ATC_HAL_TRAY_POS] = int( self.redis.hget('zbot_slot_table', 'current_slot')) #make it persistent
        except redis.exceptions.RedisError as e:
            msg = "{0} occured, these were the arguments:\n{1!r}".format(type(e).__name__, e.args)
            self.error_handler.log("ATC: caught a RedisError during get tray pos attempt: {:s}".format(msg))
            self.hal[ATC_HAL_TRAY_POS] = 0   # whatever?

    def query_sensors(self, sensor_list):
        #=====================================================================================
        #  Query all requested outputs from sensor list. If only one sensor is in the list
        #  the return code can be used to indicate state. If multiple items
        #  are in the list, associated hal output pins should be used, as rc is
        #  reflecting the last good query or error code (if negative).
        #======================================================================================

        #===================================================================
        # NEW BOARD LOGIC -  for version 2, no more discrete Q commands - all answers in
        #                   single status string
        #===================================================================
        if self.board_version == 2:
            r = self.extract_data_v2(sensor_list)
        elif self.board_version == 1:
            r = self.extract_data_v1(sensor_list)
        else :
            self.error_handler.log("ATC: Invalid board version %s" % self.board_version)
            return ATC_INTERNAL_CODE_ERROR
        return r

    def extract_data_v2(self,sensor_list):

        #!!!!! fix this to use global data for string, and rc always integer
        data = self.send_command(USB_STATUS)  # poll status string
        if isinstance(data,int): return data  #io error if not a string

        if (self.hal['debug-level'] & DEBUG_LEVEL_ATC_VERBOSE) != 0:
            self.error_handler.log("ATC: status %s" % str(data))

        for i in sensor_list:
            if i == ATC_PRESSURE_SENSOR:
                r = 1 if 'P+' in data else 0
                self.set_hal_output_status(i, r)

            elif i == ATC_TRAY_IN_SENSOR:
                r = 1 if 'C+' in data else 0
                self.set_hal_output_status(i, r)

            elif i == ATC_VFD_SENSOR:  # covers all cases
                r = 0         # default is off

                # this user comp operates in 3 modes - PULSE, LEVEL, and NONE.
                if self.vfdmode == 'PULSE':
                    ix = data.find('R') # look one character from the 'R', last value in line before CR
                    ix2= data.find('\r')
                    speed = 0
                    if ix != -1:
                        try:
                            speed = int(data[ix+1:ix2])  # pluck out the R value and update speed
                        except Exception as e:
                            self.error_handler.log('ATC: error parsing vfd rpm from line (%s) gave: %s' % (data, str(e)))

                        if speed < 400:
                            speed = 0   # cancel reporting anamolies when stopping
                            if self.old_speed > 0:
                                self.error_handler.log("ATC: Detected spindle stopped")

                        if speed > 0:
                            if self.old_speed == 0:
                                self.error_handler.log("ATC: Detected spindle started")
                            r = 1

                    self.old_speed = speed    # remember the Alamo!
                    self.hal["vfd-rpm"] = speed  # goes to the outside world as U32
                elif self.vfdmode == 'NONE':  # ecm1 machines - override with hal pin on ecm machines
                    if self.hal['vfd-running'] > 0:
                        r = 1
                elif self.vfdmode == 'LEVEL':
                    if 'V+' in data:  # generic case use vfd wiring to atc board for series 2 boards
                        r = 1
                else:
                    self.error_handler.log("ATC unsupported vfd reporting method {:s}".format(self.vfdmode))
                self.set_hal_output_status(i, r)

            elif i == ATC_DRAW_SENSOR:
                r = 1 if 'D+' in data else 0
                self.set_hal_output_status(i, r)

            elif i == ATC_LOCK_SENSOR:
                r = 1 if '4+' in data else 0
                self.set_hal_output_status(i, r)

            elif i == ATC_TRAYREF_SENSOR:
                r = 1 if 'H+' in data else 0
                self.set_hal_output_status(i, r)

        return r

    def extract_data_v1(self,sensor_list):
        #==============================================================
        #THIS IS A LEGACY BOARD - use discrete Q commands
        #                         Deprecated in new board
        #  The lock sensor is emulated, since the firmware does not have
        #  a virtual switch for it. This consistent with other queries
        #===============================================================
        for i in sensor_list:
            if i == ATC_LOCK_SENSOR: #emulate a "Q8" command and
                r = 1                # just pretend set to high pressure
            elif i == ATC_TRAYREF_SENSOR:
                # just pretend tray is always referenced to the UI
                # only current use for the status is in BT30 M19 index position
                # setting which will never be done with a gen 1 ATC anyway.
                r = 1
            else:
                r = self.send_command(command=USB_QUERY + str(i) + "\r")

            if r >= 0:  #only positives are 0 and 1
                self.set_hal_output_status(i,r)
            else:
                return r       #io error exits early

        return r     #no io errors return positive  every time..

    def start_IO_thread(self, start_it=True):

        #----------------------------------------------------------------------------------
        # spin here waiting for reset, hitting red mushroom estop will cause entry here
        # power can still be off
        #-----------------------------------------------------------------------------------

        while True and start_it:
            self.status.poll()
            if self.status.task_state != linuxcnc.STATE_ON:
                time.sleep(.1)
            else:
                break

        if self.USB_comms_thread.is_alive():     # if thread is alive
            self.start_msg_suffix = 'restarting '
            self.tx_queue.put(('terminate',0))   #shut down ATC IO thread politely
            self.USB_comms_thread.join(1.5)       # wait a bit for it to end

        if self.USB_comms_thread.is_alive():     # OH YEAH! if thread is alive
            self.error_handler.log('ATC: Force quitting ATC/IO service')  # no more mr nice guy!
            self.USB_comms_thread.terminate()    # machine gun it down - will show up as terminal interrupt in std out
            self.USB_comms_thread.join(1.5)       # wait for it to end and free any resources

        if start_it:
            self.USB_comms_thread=multiprocessing.Process(name='ATC USB/IO Service', target=self.process_the_queue)  #initialize thread definition
            self.USB_comms_thread.daemon = True  # allow parent to terminate while thread is active - only for emergency shutdowns
            self.USB_comms_thread.start()        # start reading the queue       (see below)
        else:
            self.tx_queue.close()                # turn out the lights
            self.rx_queue.close()


    def process_the_queue(self):

        self.error_handler.log('Z-Bot ATC: ATC/IO Service %s' % self.start_msg_suffix)

        while True:  #boogie till ya puke!

            work_item = self.tx_queue.get()      # this efficiently block until an item is available

            if 'terminate' in work_item:        #shutting down?
                return  #no more work coming today - thread ends

            #dispatch work in thread
            #VE is special case to connect
            if 'VE' in work_item:               # are we trying to connect here?
                r = self.connect_to_device_thread()  # set's comms_up event

            #all else comes here. ST command retrieves string from device.
            else:
                tx_command = work_item[0]            #put command in queue
                tx_timeout = work_item[1]            #pass on the time out
                r = self.send_command_thread(tx_command, tx_timeout)

            self.rx_queue.put(r)  #reply with rc - VE will be tuple, ST a string, the rest and
                                  # return a positive integer, errors negative integers

    def set_sim_config(self, enable_sim):
        self.is_sim_config = enable_sim

        # For a simulated ATC we simply replace the USB serial object with a custom one
        # that just answers the way an ATC would.  Rest of the code is identical.
        self.atc_s_cmd = SerialSim("/dev/zbot_atc", 57600, 0, self.redis)










class SerialSim():
    # This is the simulated ATC control board on the other side of the USB connector....
    # We just watch what commands are written to the 'serial' port and then reply accordingly.
    # A few things need minimal state keeping, but rest of the code is identical this way
    # between sim and non-sim.

    def __init__(self, device, baudrate, timeout, redis):
        self.lastcmd = ''
        self.nextread = ''
        self.traysolenoid = False
        self.blastsolenoid = False
        self.sol4solenoid  = False
        self.version_answer = redis.hget('machine_config', 'atc_board_sim_version')
        self.version_answer_long = redis.hget('machine_config', 'atc_board_sim_version_long')
        if self.version_answer_long == None:
            self.version_answer_long = ''
        self.vfdmode = 'NONE'

    def set_sim_vfdmode(self, vfdmode):
        self.vfdmode = vfdmode

    def write(self, data):
        self.lastcmd = data

        if self.lastcmd == '\r':
            self.nextread = ''

        elif self.lastcmd == USB_VERSION:
            self.nextread = self.version_answer

        elif self.lastcmd == USB_VERSION_LONG:
            self.nextread = self.version_answer_long

        elif self.lastcmd == USB_TRAY_IN:
            self.traysolenoid = True
            self.nextread = USB_OK

        elif self.lastcmd == USB_TRAY_OUT:
            self.traysolenoid = False
            self.nextread = USB_OK

        elif self.lastcmd == (USB_QUERY + str(ATC_TRAY_IN_SENSOR) + '\r'):
            if self.traysolenoid:
                self.nextread = USB_ON + USB_OK
            else:
                self.nextread = USB_OFF + USB_OK

        elif self.lastcmd == USB_STATUS:
            # gen2 boards report all sensor status at once vs. individual queries
            '''
            ATC_PRESSURE_SENSOR  = 1
            ATC_TRAY_IN_SENSOR   = 3
            ATC_VFD_SENSOR       = 6
            ATC_DRAW_SENSOR      = 7
            '''
            if self.vfdmode == 'PULSE':
                vfdsensor = 'R0'
            elif self.vfdmode == 'LEVEL':
                vfdsensor = 'V-'
            elif self.vfdmode == 'NONE':
                # V+ and V- are used in 440 only. 1100M and 770M versions use HAL Pins instead
                vfdsensor = 'V-'

            tray = 'C-'
            if self.traysolenoid:
                tray = 'C+'

            pselect = '4-'
            if self.sol4solenoid:
                sol4solenoid = '4+'

            self.nextread = 'P- {:s} {:s} {:s} D-'.format(tray, vfdsensor, pselect)

        elif self.lastcmd == USB_BLAST_ON:
            self.blastsolenoid = True
            self.nextread = USB_OK

        elif self.lastcmd == USB_BLAST_OFF:
            self.blastsolenoid = False
            self.nextread = USB_OK

        elif self.lastcmd == USB_DRAW_HIGH_PRESS:
            self.sol4solenoid = True
            self.nextread = USB_OK

        elif self.lastcmd == USB_DRAW_LOW_PRESS:
            self.sol4solenoid = False
            self.nextread = USB_OK

        elif self.lastcmd in (USB_FIND_HOME, USB_DB_ACTIVATE, USB_DB_DEACTIVATE, USB_OFFSET_UP, USB_OFFSET_DOWN):
            self.nextread = USB_OK

        # sensor queries...may need some state here
        elif self.lastcmd[0] == USB_QUERY:
            self.nextread = USB_OFF + USB_OK

        elif self.lastcmd[0] == USB_INDEX_TRAY:
            self.nextread = USB_OK



        else:
            self.nextread = USB_UNKNOWN

        self.nextread += '\r\n'

        return len(data)   # return number of bytes 'written' to the port

    def read(self, size=1):
        data = self.nextread
        self.nextread = ''
        return data

    def close(self):
        pass



if __name__ == "__main__":

    # IF YOU CHANGE THINGS IN main() HERE,
    # PLEASE UPDATE hal_zbotatc_sim.py THE SAME WAY.

    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(),'w',0)

    atc_talker = zbotatc_hal_component()
    try:
        # Simulated mill configurations invoke the hal user comp with a sim argument
        if len(sys.argv) == 2 and sys.argv[1] == 'sim':
            atc_talker.error_handler.log("Z-Bot ATC: Simulator mode enabled.")
            atc_talker.set_sim_config(True)

        atc_talker.zbotatc_main()

    except KeyboardInterrupt:
        atc_talker.error_handler.log("Z-Bot ATC: KeyboardInterrupt caught, exiting.")

    finally:
        atc_talker.error_handler.log("Z-Bot ATC: Exit sequence started")
        if atc_talker.comms_up.is_set():
            atc_talker.send_command(command=USB_BLAST_OFF)      # just in case interrupted between on/off
        atc_talker.start_IO_thread(False)                #just shut down IO Service if running
        atc_talker.hal.exit()
        atc_talker.error_handler.log('Z-Bot ATC: HAL component : exited')

    sys.exit(0)
