#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


import hal
import time
import serial
import os
import sys
import tormach_file_util
import gtk
import glob
import virtualCOM_serial_io
import datetime
import linuxcnc
import traceback
import errors
from constants import *
import ppglobals


class usbio_hal_component():

    def __init__(self):
        self.error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements
        self.error_handler.log("USBIO : HAL component starting")

        self.status = linuxcnc.stat()
        self.command = linuxcnc.command()

        self.usbio_hal = hal.component("usbio")

        #status for part program
        self.usbio_hal.newpin("IOB-OK", hal.HAL_S32, hal.HAL_OUT)

        # set true if board with the relevant ID is present
        # this lets the GUI know which boards are detected and which aren't so it can
        # provide better status tab diagnostics
        self.usbio_hal.newpin("board-0-present", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("board-1-present", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("board-2-present", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("board-3-present", hal.HAL_BIT, hal.HAL_OUT)

        # board output relays - read as inputs to component
        self.usbio_hal.newpin("enabled", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-0", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-1", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-2", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-3", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-4", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-5", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-6", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-7", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-8", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-9", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-10", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-11", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-12", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-13", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-14", hal.HAL_BIT, hal.HAL_IN)
        self.usbio_hal.newpin("relay-15", hal.HAL_BIT, hal.HAL_IN)

        # board inputs - set as outputs from component
        self.usbio_hal.newpin("input-0", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-1", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-2", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-3", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-4", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-5", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-6", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-7", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-8", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-9", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-10", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-11", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-12", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-13", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-14", hal.HAL_BIT, hal.HAL_OUT)
        self.usbio_hal.newpin("input-15", hal.HAL_BIT, hal.HAL_OUT)

        self.usbio_hal.ready()         # signal ready

        self.usbio_hal["IOB-OK"] = 0   # no problems yet
        self.loop_hertz = 10.0         # sampling rate for signals
        self.enabled = False           # not up yet
        self.io_boards_list = []       # list of board IO comms object
        self.last_message = ''          #duplicate message editing
        self.boards_we_have_list = []  # keep a tally of the discovered boards


    def usbio_enablement(self):
        bind_status = True  # We must connect to ALL boards to go True
        self.io_boards_list = []                     # purge the list of all entries
        for symlink in glob.glob('/dev/USBIO*'):     #look for UDEV names =  USBIOn
            #real_path = os.path.realpath(symlink)   # for debugging incase you want to see it
            #print  real+_path

            # virtualCOM_serial_io.IO_thread will instantiate a comms object in the list for USBIOn symlink names
            # thereby creating a new thread for every device name that begins with USBIO
            # when opened successfully it will have comms_up event set.
            # however, it must also pass the ID test to be kosher. no pork in iob land
            # args are name, baud rate, and characters to print in a stdout message prefix

            self.io_boards_list.append(virtualCOM_serial_io.IO_thread(symlink,38400,"USBIO : "))

        if self.io_boards_list.__len__() == 0: # nothing here - no boards today
            # only log this if it isn't the same result we got last time....
            if self.usbio_hal["IOB-OK"] != -4:
                self.error_handler.log('USBIO : No USBIO boards found')
                self.usbio_hal["IOB-OK"] = -4    #no boards today, buddy
            bind_status = False   # we should have at least one of these things
        else:                                  # got at least one USBIO Board
            self.error_handler.log('USBIO : Identifying USBIO ports')

        # can get bogus "cannot connect / Board malfunction errors"
        # allow time for serial I/O to get comms_up.is_set() working
        # adding the following short sleep() cobble appears to eliminate the false error
        time.sleep(.050)

        for io_board in self.io_boards_list:   #poll all boards for their IDs

            io_board.ioboard_id = -1

            if io_board.comms_up.is_set():
                r,data = io_board.send_command('VE\r')   # request version ID string
                if "Tormach I/O" in data:
                    self.error_handler.log('USBIO : ' + io_board.port_name + data.strip())

                    # I found at least one USBIO board that was identifying itself as "B" as a board ID.
                    # But the parsing logic below assumed base 10. If we just assume base 16 then
                    # all boards 0-9 will parse just fine and we don't need to try to invent '0x' prefix.
                    try:
                        io_board.ioboard_id = int(data[data.find('ID')+3], 16) #stuff in ID returned
                        self.error_handler.log("USBIO : parsed ID to board {:d} and modded it to {:d}".format(io_board.ioboard_id, io_board.ioboard_id % 4))
                        io_board.ioboard_id = io_board.ioboard_id % 4
                    except:
                        self.error_handler.log("USBIO : could not identify ID from board {}".format(str(io_board)))
                        io_board.ioboard_id = 0    #if board predates current firmware data.find fails, and it's a 0

            if io_board.ioboard_id == -1:   #cannot determine ID - not one of ours
                bind_status = False
                self.error_handler.log('USBIO : Cannot connect to '+ io_board.port_name)
                self.usbio_hal["IOB-OK"] = -1   #signal boards have problems to user
                break

        # now spin discoveries and check for duplication among the population
        self.boards_we_have_list = [0,0,0,0]          #count valid ids we get by ID #
        for io_board in self.io_boards_list:
            if io_board.ioboard_id >= 0 :
                self.boards_we_have_list[io_board.ioboard_id] += 1
                if self.boards_we_have_list[io_board.ioboard_id] > 1:  #ooops - same number not allowed
                    self.error_handler.log('USBIO : Duplicate ' + io_board.port_name + ' ID = ' + str(io_board.ioboard_id))
                    self.usbio_hal["IOB-OK"] = -3   #signal boards have problems to user
                    bind_status = False

        # Any prior issues, or no IO boards in the lot
        if bind_status == False or self.io_boards_list.__len__() == 0:
            self.usbio_disablement()        #free the lot
            if self.usbio_hal["IOB-OK"] == 0:   # don't stop on top of errors above that are helpful for diagnostics
                self.usbio_hal["IOB-OK"] = -4   #indicate an error to stop part programs

        self.enabled = bind_status and self.io_boards_list.__len__() > 0  #make sure we found all

        # log what we ended up with definitively, but carefully.
        # if we don't have any usbio boards, but they are enabled in settings,
        # we'll try to enable them every half second so can spam the log.
        for ii in self.io_boards_list:
            self.error_handler.log("USBIO : io_boards_list - " + str(ii))

        if self.enabled : self.usbio_hal["IOB-OK"] = 0

        #======================================================================================
        # Dial settings are only honored for multiple boards - read on....
        #  Since we began selling boards without support for the dial ID, it's entirtely possible
        #  that early users will have a single board in play with a random dial setting
        #  HOWEVER, they are expecting the board to be digital pins 0,1,2,3
        #  To keep support calls down, a single board will always be ID 0 and work as it did previous
        #  to multiple board support availability.
        #=======================================================================================

        if self.io_boards_list.__len__() == 1 :    # did we only find one lonely miserable board
            overidden_id = self.io_boards_list[0].ioboard_id  # fetch old dial setting
            self.io_boards_list[0].ioboard_id = 0   # force ID to 0
            if overidden_id != 0:                  #leave some bread crumbs for support
                self.error_handler.log('USBIO : Overriding dial setting for board ID '+ str(overidden_id) +' forcing to ID 0')

        # let GUI know which boards are present
        self.usbio_hal["board-0-present"] = 0
        self.usbio_hal["board-1-present"] = 0
        self.usbio_hal["board-2-present"] = 0
        self.usbio_hal["board-3-present"] = 0
        for bb in self.io_boards_list:
            if bb.ioboard_id >= 0 and bb.ioboard_id <= 3:
                self.usbio_hal["board-{:d}-present".format(bb.ioboard_id)] = 1


    def usbio_disablement(self):
        #shut it all down
        if usbio_talker.io_boards_list.__len__() > 0:
            for io_board in usbio_talker.io_boards_list:
                io_board.start_IO_service(False)  #terminate all open threads

        usbio_talker.io_boards_list = []   # shit can the whole list
        self.enabled = False               # signal we are shut down internally


    def usbio_main(self):
        #wait for system to come out of RESET
        while True:
            self.status.poll()  # don't even try if machine isn't ready
            if self.status.task_state == linuxcnc.STATE_ON : break
            time.sleep(.050)   # hang a bit
        #============================================================================
        #main process loop
        #
        #  The main loop first checks to see if IOBOard functions are requested by the user
        #   and unconditionally disables the IOB system if not. The disablement routine does  nothing
        #   if nothing was previously enabled during the day.
        #
        #  There are two primary variables that govern the behavior of the setup. The the GUI radio button
        #   and the internal state of the system in self.enabled.  Any time the IOB system is requested by the user
        #   and the system is not enabled, it will attempt to do so.  This invoives bnding to all
        #   existing boards and editing the configuration for duplicates, and such. During this time
        #   all duplicate log messages from errors or setup are surpressed so that only one significant message
        #   will post per occurance, and not during retries.
        #
        #  Once all the boards are discvoered, they are instantiated in a list of serial IO objects, identified
        #   by the internal board ID dialed into the dip switches of the hardware. The dip switch determins
        #   the LinusCNC digital pins assigned to the board.  Each board is assigned to an object which
        #   is responsible for all IO and recovery. IO is performed in separate thread for each board so that
        #   it may be terminated and restarted if the OS hangs in a serial communication process due to EMi.
        #    See virtualCOM_serial_io.py for details on IO recovery.
        #  Every effort is made to recover from the various IO errors the USB boards are subjected to
        #  as they are powered by the USB bus, and have user's relays and IO devices attached.
        #  They are particularly sensitive to EMI, noise,  and data corruption.
        #
        #  Once discovered and configured, the boards are interrogated one at a time in a never ending
        #  loop and appropriate Digital IO pins set for the user. The state of the IO Board system is
        #  continuously broadcast on the "IOB-OK" hal pin. This pin is continuoualy interrogated by
        #  the GUI to determine the health of the system.  The status is ignored by the GUI unless
        #  a part program is running.  There is no tolerance for errors during part program execution as
        #  there can be serious consequences to a malfunctioning IO Board automation platform. An error on any board
        #  will cause the whole system to reinitialize, as it is possible that the could have been reconvigured
        #  after a cable disconnect.
        #======================================================================================

        while True:

            if not self.usbio_hal['enabled']:  #if user turns off button in GUI - shut down
                self.usbio_disablement()       #does nothing if list is already empty
                self.usbio_hal["IOB-OK"] = 0   #clear any old status errors so that if they re-enable later, it doesn't instantly display stale status

            if self.usbio_hal['enabled'] and not self.enabled:  # Look for boards and bind
                self.usbio_enablement()       #Lets find boards and get started

            while self.usbio_hal['enabled'] and self.enabled:   #only do this if GUI wants it and we are connected

                #spin through the boards and set pins
                for io_board in self.io_boards_list:
                    if io_board.ioboard_id >= 0:
                        try:
                            # send relay command and read relay board state
                            cmd = self.get_relay_cmd_string(io_board.ioboard_id)
                            r,data = io_board.send_command(cmd)  #get user requested relay pins
                            if r < 0:
                                self.usbio_hal["IOB-OK"] = -2  # cant trust data on pins io error
                                self.usbio_disablement()
                                break

                            time.sleep(1/self.loop_hertz)   # combine response wait and loop frequency
                            if data and r == 0:
                                self.usbio_hal["IOB-OK"] = 0  #good to go
                                for i in range(4):
                                    hal_input_number = str(io_board.ioboard_id*4+i)  #relocate pin numbers
                                    self.usbio_hal["input-"+hal_input_number ] = (data[i] == "1") #map io  to hal outputs

                        except Exception as e:
                            self.error_handler.log(str(e))
                            self.usbio_hal["IOB-OK"] = -2

            time.sleep(.5)  #latency time between enable checking


    def get_relay_cmd_string(self,board_id):
        rly0 = str(board_id*4)
        rly1 = str(board_id*4+1)
        rly2 = str(board_id*4+2)
        rly3 = str(board_id*4+3)
        # convert list of bools to list of 0's and 1's in preparation for serial command
        req_relay_stat_list = map(lambda x: "1" if x else "0", [self.usbio_hal["relay-"+rly0], self.usbio_hal["relay-"+rly1], self.usbio_hal["relay-"+rly2], self.usbio_hal["relay-"+rly3]])
        cmd_string = "SR " + ''.join(req_relay_stat_list) + "\r"
        return cmd_string


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
    try: #mainline code covered by keyboard exception when hal shuts down
        usbio_talker = usbio_hal_component()
        usbio_talker.usbio_main()

    except KeyboardInterrupt:
        usbio_talker.error_handler.log("USBIO : KeyboardInterrupt caught, exiting.")
        pass

    finally:
        usbio_talker.error_handler.log("USBIO : Exit sequence started.")
        if usbio_talker.io_boards_list:
            for io_board in usbio_talker.io_boards_list:
                usbio_talker.usbio_disablement()  #shut thread per board
                       # give everything time to terminate
        usbio_talker.usbio_hal.exit()   #exit hal component
        usbio_talker.error_handler.log("USBIO : HAL component : exited.")

    sys.exit(0)
