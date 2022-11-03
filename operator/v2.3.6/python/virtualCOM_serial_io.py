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
import math
import glob
import datetime
# global constants from Tormach UI
import errors
from constants import *
import ppglobals


class ComError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class IO_thread():
    def __init__(self,port_name='/dev/ttyUSBn', baud_rate=57600, id_string=None):

        self.error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements
        self.error_handler.log("VirtualCOM : init")

        # Global housekeeping
        self.serial_comms = serial.Serial()   #init comms object
        self.id_string = id_string
        self.port_name = port_name
        self.baud_rate = baud_rate
        self.last_command = ''
        self.last_message = ''   #duplicate editing

        #########################################################
        # initialization logic
        #########################################################

        #constructs for USB communication threading

        self.tx_queue = multiprocessing.Queue()    #work queue for send
        self.rx_queue = multiprocessing.Queue()    #work queue for receive
        self.USB_comms_thread = None               #hold this name for later
        self.comms_up = multiprocessing.Event()   #requires  both threads to see
        self.ready =    multiprocessing.Event()
        self.start_msg_suffix = 'starting '        #message qualifier - changes to restarting after first time
        self.time_out = .05                       #default timeout for all Schnozz IO223
        self.ioboard_id = None                      #special variable for handshake string onio board
        self.last_message = ''                     #don't duplicate msgs - lets not pollute the log
        self.start_IO_service()                    #prime the pump
        while not self.ready.is_set():
            time.sleep(.050)                    #give it time to take


    def __str__(self):
        s = "VirtualCOM [{}, ioboard_id {}, port_name {}]".format(self.id_string, self.ioboard_id, self.port_name)
        return s


     #=========================================================================
     # log pollution control
     # edit out duplicate errors and append time stamp to messages
     #=========================================================================

    def display_no_duplicates(self,message):
        if message != self.last_message:
            self.error_handler.log(message)
            self.last_message = message

    #=========================================================================
    # these are the only methods that runs in the caller's thread context
    #=========================================================================
    def start_IO_service(self,start_it=True):         #start up the io  queue processor
        if self.USB_comms_thread:                     #if you got it, shut it down

            if self.USB_comms_thread.is_alive():     # if thread already alive?
                self.start_msg_suffix = 'restarting '
                self.tx_queue.put(('terminate',0))   #shut down IO thread politely
                self.USB_comms_thread.join(1.5)       # wait a bit for it to end

            if self.USB_comms_thread.is_alive():     # OH YEAH! if thread is alive
                self.display_no_duplicates(self.id_string + ' Force quitting I/O service for : ' + self.port_name) # no more mr nice guy!
                self.USB_comms_thread.terminate()    # machine gun it down - will show up as terminal interrupt in std out
                self.USB_comms_thread.join(1.5)       # wait for it to end and free any resources

            self.display_no_duplicates( self.id_string + '' + self.port_name + ' I/O service ended')

        if start_it:
            self.USB_comms_thread=multiprocessing.Process(name= self.port_name + ' USB/IO Service',target=self.process_the_queue)  #initialize thread definition
            self.USB_comms_thread.daemon = True  # allow shut down if problems
            self.USB_comms_thread.start()        # start reading the queue    (see below)
        else:
            self.tx_queue.close()                # turn out the lights
            self.rx_queue.close()


    def send_command(self,command="",timeout=.050):

        if self.last_command != command:  #post command for support
            #print self.id_string , 'COMMAND for ID :', self.ioboard_id, self.port_name, command
            self.last_command = command

        # a tuple is returned consisting of return code and data
        r = self.enqueue_command(command,timeout)   #try to send and receive
        if r[0] == 0: return r                      #NICE! give back rc and data

        # Uh Oh! Let's figure out what may have happened and try to recover
        #print self.port_name, 'Retrying connection'
        if r[0] == -1:                    #thread is still alive, but lets reset port
            self.tx_queue.put('connect')  #this will close and open the port at least
            r = self.rx_queue.get()       #pop (return code and data from queue)
            if r[0] == 0:                # reconnected ? try once more
                r = self.enqueue_command(command,timeout)
            if r[0] != -3: return ((-1, self.port_name + '  Device is no longer connected'))   #port is just not talking

        # looks like thread froze due to EMI , rc== -3
        # if we can find it by same name, let's reconnect from the top.

        if glob.glob(self.port_name):
            self.display_no_duplicates( self.id_string + '' + self.port_name + ' : Attempting restart')
            self.start_IO_service()
            r = self.enqueue_command(command,timeout)
            return r  #last ditch effort gotta live with it


    def enqueue_command(self,command="",timeout=.050):
        still_alive = False                       # pulse check for thread responses

        self.tx_queue.put((command,timeout))  #executes code in send_command_thread, pass in IO timout
        loop_clicks = int((6 * timeout + .15)/.002) + 3   #give IO time for six full retries + 15 ms

        for i in range(loop_clicks):
            time.sleep(.002)
            if not self.rx_queue.empty():
                still_alive = True      #thread is talking
                r = self.rx_queue.get() #pop (return code and data from queue)
                if r[0] == 0: return r #good dog

        if not still_alive:
            return ((-3,'dead thread'))       #oy vey - EMI killed the port

        return ((-1,'io error'))               #just couldn't get it done, but alive


#==================================================================================
#  Everything below this line run in the thread's context. If errors kill the port
#   the entire structure is restarted
#===================================================================================

#=============================================================================
#    Two attempts are made to connect to the device name established by the udev rules
#    of the mill.
#    Successful connection returns with comms_up true.  This is the only place that happens.
#
#=============================================================================

    def connect_to_device_thread(self,do_open = True):

        self.comms_up.clear()
        try:
            self.serial_comms.close()         #try closing the port -no biggie if failed
        except:
            pass                           #ignore failed close

        if do_open:
            try:
                self.serial_comms = serial.Serial()   #init comms object anew
                self.serial_comms.port = self.port_name
                self.serial_comms.baudrate = self.baud_rate
                self.serial_comms.timeout=0
                self.serial_comms.open()
                if self.serial_comms.isOpen():
                    self.comms_up.set()          #connection is good
                    self.display_no_duplicates( self.id_string + '' + self.port_name + ' : connected')

            except Exception as e:
                self.display_no_duplicates( self.id_string + '' + self.port_name + '' + str(e))


    #---------------------------------------------------------------------------------------
    #  Send a command to the  board via USB ( all USB commands  come here).
    #    Flush any left over crap in buffer
    #    Send the command
    #    Process response
    #    Return to the user
    #----------------------------------------------------------------------------------------

    def send_command_thread(self,command="",timeout=.050):

        while not self.tx_queue.empty(): self.tx_queue.get()  #purge all queues
        while not self.rx_queue.empty(): self.rx_queue.get()  #one in , one out, no exceptions!

        for i in range(5):            #3 tries allowed here, to get it right
            try:
                #----------------------------------------------------------------------------------------
                #  If EMI creates any artifacts in the input buffer of the schnozz board, the \r will
                #  terminate the data, such that it will not be appended to the next legitimate command sent
                #-------------------------------------------------------------------------------------------
                data = ''
                throw_out = ''
                throw_out = self.serial_comms.read(64)  # discard anything responded

                self.serial_comms.write(command)        #send off the real command
                time.sleep(.005)                       #wait a bit command to process

                #print self.id_string , 'COMMAND :',command.strip()
                #---------------------------------------------------------------------------------------
                #    Read and interpret command responses -
                #    All answers from device terminate with a line feed character
                #    Parse data and set return code depending on content, no answer in time frame is a timeout
                #----------------------------------------------------------------------------------------
                                            #clear input buffer
                wait_attempts = int(timeout/.001 + 1)
                r = -3                #until we know better
                data = self.serial_comms.readline()

                while (wait_attempts > 0):             #everybody should wait at least once
                    if (data and '\n' in data):
                        r = 0
                        break
                    time.sleep(.001)
                    wait_attempts -= 1
                    data = data + self.serial_comms.read(32)  #read some bytes

            except Exception as e:
                self.process_io_errors(e)
                r = -7    # io error - this one sticks if last attempt

            if r < 0:
                time.sleep(.050)           #let EMI settle down, if any caused this
                continue                    #try again , don't give up yet, stay and eat the food
            else:
                break                       #OK, now you can be excused from the table
            #retry while loop ends

        return r,data                        #go back to caller with return code and data

    #---------------------------------------------------------------------------------------
    #  React to IO Errors
    #    Trapped errors end up here to print self.id_string , to stdout, turn comms_up off, and close the port
    #----------------------------------------------------------------------------------------

    def process_io_errors(self,e):
        self.display_no_duplicates(self.id_string + '' + self.port_name + ' : I/O error' + str(e))
        self.comms_up.clear()  #cancel comms


    def process_the_queue(self):
        self.ready.set()
        self.display_no_duplicates(self.id_string + '' + self.port_name + ' I/O service ' + self.start_msg_suffix)
        self.connect_to_device_thread()          # open up port

        while True:  #boogie till ya puke!
            work_item = self.tx_queue.get()      # this efficiently block until an item is available
            if 'terminate' in work_item:        #shutting down?
                self.connect_to_device_thread(False) #close the port
                return                           #no more work coming today - thread ends

            if 'connect' in work_item:           #lost device?
                self.connect_to_device_thread()
                if self.comms_up.is_set():
                    self.rx_queue.put((0,'port is open'))
                else:
                    self.rx_queue.put((-1,'port not open'))
                continue                          #no more work coming today - thread ends


            #send command, return data in queue
            tx_command = work_item[0]            #put command in queue
            tx_timeout = work_item[1]            #pass on the time out
            r,data = self.send_command_thread(tx_command,tx_timeout)
            #dispatch work and reply with rc, and data
            self.rx_queue.put((r,data))
