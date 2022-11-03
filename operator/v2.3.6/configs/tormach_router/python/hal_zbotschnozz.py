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
# global constants from Tormach UI
from constants import *
import errors

VALUE_LIMIT = 1023.0   #Dynamixel servo constants
DEGREE_RANGE = 300.0
MID_SERVO = int((VALUE_LIMIT+1)/2)  # 0  degree mounting location
SERVO_UNITS_PER_DEGREE = VALUE_LIMIT/DEGREE_RANGE
OSCILLATE_TORQUE_LIMIT = int(1023/2)   #run at one third torque for duty cycle
TORQUE_LIMIT = 1023           #run at full torque
PUNCH_CURRENT = 128      # bump minimum current at or <  compliance margin a tad
COMPLIANCE_DEADBAND = 1 # deadband tolerance to minimum
COMPLIANCE_SLOPE = 32    #defaut to stock
DEGREE_TIME = .005    # average time per unit
FIXED_LATENCY =.020     # xmit time for data
RESEND_COUNT = 4        # number for retransmits for open loop servo control

TRACE_USB_COMMS = 0


class zbotschnozz_hal_component():
    def __init__(self):
        self.error_handler = errors.error_handler_base()  # use the simple version without UI deps so that we get consistent log structure vs. print statements

        self.error_handler.log("Smart Cool: HAL component: started")

        # Global housekeeping

        self.status = linuxcnc.stat()
        self.command = linuxcnc.command()
        self.redis = redis.Redis()
        self.schnozz_s_cmd= 0
        self.hal = hal.component("zbotschnozz")

        # the following distances are used to set servo geometry
        # each machine has its own mount distance tuple. Horizontal is same
        # but new machines might have different mounting system
        self.V_MOUNT_DISTANCE = 3.942  # Defaults (derived from original 1100)
        self.H_MOUNT_DISTANCE = 6.808

        self.vertical_adjustment = 0.0           #set by users via ADMIN in GUI

        # debug level inputs from UI
        self.hal.newpin('debug-level', hal.HAL_U32, hal.HAL_IN)

        self.hal.newpin("coolant", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("mist", hal.HAL_BIT, hal.HAL_IN)

        self.hal.newpin("man-auto", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("cool-up", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("cool-down", hal.HAL_BIT, hal.HAL_IN)

        #########################################################
        # initialization logic
        #########################################################

        #constructs for USB communication threading

        self.tx_queue = multiprocessing.Queue()    #work queue for send
        self.rx_queue = multiprocessing.Queue()    #work queue for receive
        self.USB_comms_thread=multiprocessing.Process(name='Smart Cool USB/IO Service',target=self.process_the_queue)  #isolate IO to USB
        self.comms_up = multiprocessing.Event()    #requires  both threads to see
        self.start_msg_suffix = 'starting '        #message qualifier - changes to restarting after first time
        self.time_out = .05                       #default timeout for all Schnozz IO
        self.error_display = True                 #display io errors in std out
        self.last_e = ''
        self.last_time = time.clock()               #clock base

        # hal component is ready to roll
        self.hal.ready()

        # schnozz globals
        self.force_refresh  = True              #set when new comms established
        self.POLL_INTERVAL = .020               #polling rate
        self.modulate_switch   = False          #servo is dancing state - up or down
        self.servo_scale    = MID_SERVO + int(45*SERVO_UNITS_PER_DEGREE) #initial position is a guess
        self.last_servo_scale = 99              #last position
        self.Pval = 0.0                         #from analog pin 30, set by  M7,M8 remap and M9
        self.Eval = 0.0                         #analog pin 26, as above
        self.Qval = 0.0                         #analog pin 28, as above
        self.Rval = 0.0                         #analog pin 27, as above
        self.tlen = 0.0                         #fromlinux cnc status - tool length offset
        self.error_count = 0                    #prevents redundant io error prints
        self.last_relay1 = False               #remember relay state to supress uneccesary io
        self.last_relay2 = False
        self.skip_a_beat = False               # used to debounce M9 to prevent short cycling pump
        self.skip_count  = 0                   # debounce coolant or flood off signals
        self.resend_count = 0                  # for resending commands in open loop mode
        self.z_zero_mode = False


    def zbotschnozz_main(self):    #main line logic
        # MAIN HAL LOOP
        while True:

            #wait for poll interval
            time.sleep(self.POLL_INTERVAL)

            if (not self.comms_up.is_set()):  #we aren't connected to the smart cool board
                self.connect_to_device()    #hook up to device, waits until device connects
                self.last_relay1 = False    #was unplugged all prior bets are off
                self.last_relay2 = False
                self.write_servo_defaults() #now go initialize servo
                self.error_handler.log('Smart Cool: Servos intialized')

            #OK - we're up, poll at rate, monitor tool length, and optional P values and act accordingly
            #P word values are sored in analog out pin 30
            #No P word will put easter egg value 583.9 in pin 30 -  Z0 mode enable
            #R word value is in analout out pin 28 - oscillation direction and magnitude

            #divine tool length from the gods
            self.status.poll()                          #linux cnc data channel update
            self.tlen = self.status.tool_offset[2]      #current tool offset in set up units

            #retrieve pval and rval from analog pins - set in remap
            #make positive values move up in Z, negatives down in Z
            self.Pval = -1.0 * self.status.aout[30]     #analog out pin 30 -  P value from M7/M8
            self.Rval = -1.0 * self.status.aout[28]     #analog out pin 28 -  R value from M7/M8
            self.Qval = abs(int(self.status.aout[27]))   #analog out pin 27 - Q value from M7/M8
            self.Eval = -1.0 * self.status.aout[26]      #analog out pin 26 - E value from M7/M8

            self.hit_an_M_command = self.status.aout[29] > 0  #M7,M8,M9 pulse this for .25 seconds

            if int(self.Pval) == -583:
                self.z_zero_mode = True
            else:
                self.z_zero_mode = False

            #rescale G code input values to setup units
            if self.status.program_units == 2:
                self.Rval = self.Rval/25.4
                self.Pval = self.Pval/25.4
                self.Eval = self.Eval/25.4

            #various lengths for angle setting
            self.base_length = 0.0
            self.tip_offset = 0.0
            self.oscillate_offset = 0.0
            self.z_offset = 0.0

            #============================================================
            # Gate control logic (solenoid 2 only) -
            #   M7 or (M8 with a Q word) will activate solenoid 2
            #============================================================
            self.pulse_on = False     #set default

            if self.hal["mist"] or (self.hal["coolant"] and self.Qval > 0 ):

                #set pulsing state and clocks
                self.pulse_on = True
                if self.Qval > 0:      #  variable solenoid state by the clock and Q
                    self.pulse_on =  int(time.time()) % (self.Qval+1) ==  0   # 1 sec on

                #this logic will turn on solenoid 2 if not already on
                if (not self.last_relay2) or self.hit_an_M_command:
                    if self.pulse_on:
                        self.send_command('2+\r')
                        self.last_relay2 = True

                # this logic will periodically turn off between 1 second bursts set by clock above
                if self.last_relay2 and not self.pulse_on:
                    self.send_command('2-\r')
                    self.last_relay2 = False

            else:  #not misting or pulsing with coolant
                   # air relay should be hard off now.
                   # M commands ignore prior state and just do it
                if self.last_relay2 == True or self.hit_an_M_command:
                    self.send_command('2-\r')  #air gate s/b  off
                    self.skip_count = 0
                    self.skip_a_beat = True      #if just transitioned from M9 or GUI, bypass positioning
                    self.last_relay2 = False

            #============================================================
            # Manual servo set logic
            #============================================================
            if self.hit_an_M_command:     #any m7,m8,m9 cancels prior manual override
                self.hal["man-auto"] = False
                self.get_vertical_adjustment()  #in case user changed during session

            if self.hal["man-auto"]:    # we are overriden in manual mode from keyboard

                if self.hal["cool-up"]:
                    #only move up to zero degrees (same as mid servo)
                    self.servo_scale -= 1
                    if self.servo_scale < MID_SERVO: self.servo_scale = MID_SERVO

                if self.hal["cool-down"]:
                    #only move down to 90 degrees
                    self.servo_scale += 1
                    max_value = MID_SERVO + int(SERVO_UNITS_PER_DEGREE * 90)
                    if self.servo_scale > max_value: self.servo_scale = max_value


                if self.hal["cool-up"] or self.hal["cool-down"]:
                    if self.servo_scale != self.last_servo_scale: #only send new position
                        command = 'WS00010030' + str(self.servo_scale).zfill(4)+'\r'
                        self.send_command (command)
                        self.last_servo_scale = self.servo_scale

                continue    #skip over the auto setting

            if self.skip_a_beat:
                self.skip_count += 1
                if self.skip_count > 20:
                    self.skip_a_beat = False
                    self.skip_count = 0
                continue

            #============================================================
            # Auto servo set logic only if the coolant is on and not in manual
            #=============================================================

            if self.hal["mist"] or self.hal["coolant"]: # anything doing?
                self.base_length =  self.tlen          # start with tool length

                if self.z_zero_mode:            #Apply Z Zero offsets for no P word
                    # note - always use setup units.  no need to scale
                    self.z_offset = self.status.actual_position[2] - self.status.g5x_offset[2] - self.status.tool_offset[2] - self.status.g92_offset[2]
                    self.base_length += (self.z_offset + self.Eval) # offset b Z height and W offset

                else:                              # tool tip offset for all other P values
                    self.tip_offset =  self.Pval    # setup units
                    self.base_length += self.tip_offset          # apply tip offset

                self.oscillate_offset = self.Rval
                goto = self.base_length if self.modulate_switch else (self.base_length+self.oscillate_offset)
                self.set_servo_angle(goto)    #make it point
                self.modulate_switch = not self.modulate_switch  #see saw between base and modulation

        #   END MAIN HAL LOOP


    #------------------------------------------------------------------------
    #  Helpers
    #------------------------------------------------------------------------

    def set_servo_angle(self,tlen):
        #compute target location and send to servo at change or M command time
        self.servo_scale = MID_SERVO + int(SERVO_UNITS_PER_DEGREE * self.compute_servo_angle(tlen)) #transform to servo coded postion
        positioning_command = 'WS00010030' + str(self.servo_scale).zfill(4)+'\r'
        if self.servo_scale == self.last_servo_scale:
            self.resend_count += 1    #tick it up
        if self.servo_scale != self.last_servo_scale or self.hit_an_M_command:
            self.resend_count = 0     #new ball game
        if self.resend_count < RESEND_COUNT:  # send multiple -then only when servo scale changes
            distance = abs(self.servo_scale - self.last_servo_scale)
            run_torque = OSCILLATE_TORQUE_LIMIT if self.oscillate_offset != 0 else TORQUE_LIMIT
            if self.resend_count == 0:
                self.send_command ('WS00010034' + str(run_torque).zfill(4)+'\r')
            self.send_command (positioning_command)

            if self.Rval != 0:       #only wait if oscillating - this is blocking
                for i in range (RESEND_COUNT):
                    self.send_command (positioning_command)
                    #time.sleep (FIXED_LATENCY+ distance * DEGREE_TIME)  # constant for latency start
                time.sleep (distance * DEGREE_TIME)
        self.last_servo_scale = self.servo_scale          #save off old number


    def compute_servo_angle(self,length):
        servo_angle = 0.0

        #high school geometry
        central_angle = math.degrees(math.atan((length + self.V_MOUNT_DISTANCE+self.vertical_adjustment)/self.H_MOUNT_DISTANCE)) # center slot computation
        offset_angle = math.degrees(math.atan(self.S_DELTA_DISTANCE/math.sqrt(length**2 + self.H_MOUNT_DISTANCE**2)))

        #point according to the rules. If mist and coolant on, aim for coolant. If coolant on
        #and pulsing air , temporarily aim blast with mist geometry for blast duration.
        #if wiggling,  don't re-aim.

        if self.hal["mist"]:       #aim for mist
            servo_angle = central_angle + offset_angle

        if self.hal["coolant"]:    #coolant trumps mist aim
            servo_angle = central_angle - offset_angle

        #pulsing durin M8 trumps it all under right conditions
        #logic note : self.pulse is only true if mist is off when M8 uses Q word
        #Rval non-zero is wiggle mode
        if self.pulse_on and not self.hal["mist"] and self.Rval == 0: #ignore blast aim during wiggle mode
            servo_angle = central_angle + offset_angle

        if servo_angle > 90.0: servo_angle = 90.0        #let's not point to goofy places
        if servo_angle < 0.0:  servo_angle = 0.0

        return servo_angle  #return true angle in floating point


    def write_servo_defaults(self):
        self.send_command('WS00010034' + str(TORQUE_LIMIT).zfill(4)+'\r')  #full torque
        self.send_command('WS000100160000\r') # turn off responses -  run open loop
        self.send_command('WS00010026' + str(COMPLIANCE_DEADBAND).zfill(4)+'\r')  # set CW and CCW compliance and slopes for max
        self.send_command('WS00010027' + str(COMPLIANCE_DEADBAND).zfill(4)+'\r')  # precision.
        self.send_command('WS00010028' + str(COMPLIANCE_SLOPE).zfill(4)+'\r')   # set CW and CCW slopes
        self.send_command('WS00010029' + str(COMPLIANCE_SLOPE).zfill(4)+'\r')
        self.send_command('WS00010048' + str(PUNCH_CURRENT).zfill(4)+'\r')  #punch current low order  - slight increase


    def get_vertical_adjustment(self):
        #users can fine tune their aiming via ADMIN SMART_COOL + or -nnnn
        self.vertical_adjustment = 0.0
        try:
            self.vertical_adjustment = -1 * float(self.redis.hget('machine_prefs', 'smart_cool_offset'))
        except:
            pass


    #---------------------------------------------------------------------------------------
    #  Connect to the Schnozz USB device
    #----------------------------------------------------------------------------------------
    def connect_to_device(self):

        self.comms_up.clear() # cancel communications

        # wait for system to come out of RESET
        while True:
            self.status.poll()  # don't even try if machine isn't ready
            if self.status.task_state == linuxcnc.STATE_ON: break
            time.sleep(.1)   # hang a bit

        # look for a Smart Cool
        self.error_handler.log("Smart Cool: Looking for device")

        while True:   #wait for a device forever - first discover one, then handshake
            while not glob.glob('/dev/zbot_schnozz'):  #plugged in!
                time.sleep(1)

            self.start_IO_thread()          #start up the service thread to talk
            self.tx_queue.put('VE\r')       #keep trying to hand shake
            time.sleep(.5)
            if self.comms_up.is_set():       # got a talking device here - continue
                break

        #-----------------------------------------------------
        #  Now set mount geometry according to configuration
        #  We read the attributes from the redis machine_config area so we aren't
        #  hard coding values to specific model numbers.
        #-----------------------------------------------------

        distance = self.redis.hget('machine_config', 'smartcool_vmount_distance')
        if distance:
            try:
                self.V_MOUNT_DISTANCE = float(distance)
            except ValueError:
                self.error_handler.log("Smart Cool: corrupt redis machine_config smartcool_vmount_distance value {:s}".format(distance))
        else:
            self.error_handler.log("Smart Cool: redis machine_config smartcool_vmount_distance key missing - unsupported on this machine.")

        distance = self.redis.hget('machine_config', 'smartcool_hmount_distance')
        if distance:
            try:
                self.H_MOUNT_DISTANCE = float(distance)
            except ValueError:
                self.error_handler.log("Smart Cool: corrupt redis machine_config smartcool_hmount_distance value {:s}".format(distance))
        else:
            self.error_handler.log("Smart Cool: redis machine_config smartcool_hmount_distance key missing - unsupported on this machine.")

        self.S_DELTA_DISTANCE  = .75 # normal distance between slots in pipe hub

        #retrieve startup vertical adjust - user can change without restart
        self.get_vertical_adjustment()

        self.error_handler.log('Smart Cool: Vertical mount = {}  Horizontal mount = {}  Vertical adjustment = {}'.format(self.V_MOUNT_DISTANCE, self.H_MOUNT_DISTANCE, self.vertical_adjustment))


    #=============================================================================
    #    Two attempts are made to connect to the device name established by the udev rules
    #    of the mill.
    #    A handshake is expected after sending the schnozz board a VErsion command. If the device does
    #    don't comply we do not bind to it.
    #    Successful connection returns with comms_up true.  This is the only place that happens.
    #=============================================================================
    def connect_to_device_thread(self):
        try:
            self.schnozz_s_cmd.close()         #try closing the port -no biggie if failed
        except:
            pass                           #ignore failed close

        data = ''
        for i in range(2):
            try:
                time.sleep(i * .05)          # wait longer periods if failures
                self.schnozz_s_cmd=serial.Serial("/dev/zbot_schnozz", baudrate=57600, timeout=0)
                throw_out = self.schnozz_s_cmd.read(64)  # discard anything
                self.schnozz_s_cmd.write('VE\r')    #request Version string
                time.sleep(.05)

                #pylint: disable=no-member
                data=self.schnozz_s_cmd.readline()       #read answer from schnozz control board

            except Exception as e:
                pass                                     #not schnozz , who cares?

            if 'Z-Bot SCHNOZZ' in data:
                self.error_handler.log('Smart Cool: Firmware ID {}'.format(data.strip()))
                self.comms_up.set()               #AWESOME!!!!! we're live
                self.error_display = True          # new ball game
                self.last_e = ''
                break


    def send_command(self,command="",timeout=.020):
        trace_next_io = False
        for i in range(2):                      # try once here,then again after thread restart

            self.tx_queue.put((command,timeout))  #executes code in send_command_thread, pass in IO timout
            loop_clicks = int(3 * (timeout+.2)/.002)  #give IO time for three full retries + .2 s

            for i in range(loop_clicks):
                time.sleep(.002)
                if not self.rx_queue.empty():
                    r = self.rx_queue.get()             #pop (return code from send_command_thread)
                    if trace_next_io:
                        self.error_handler.log("Smart Cool: REDRIVEN USB COMMAND + RC : {} {}".format(command[0:2], r)) #for tracing redriven command
                    return r          #got an answer , good or bad - fire it back

            if self.rx_queue.empty():
                #thread timed out without responding in queue - which means thread hung as IO timeout should pop first
                #NOTE: this can happen from electrical spikes to the usb controller on mother board causing linux to abort thread
                #print  "USB COMMAND - BAD RESPONSE : ", command[0:2] , datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")   #for tracing
                self.connect_to_device()         #attempt to re drive thread, reset the connection and retry
                trace_next_io = True             #print out recovery attempt please


        # drop through here is pretty serious stuff - no response from USB device, nada, NOTHING! TWICE!!!!!!

        return ATC_USB_IO_ERROR           #rats!,  no clue what's wrong


    #---------------------------------------------------------------------------------------
    #  Send a command to the schnozz board via USB (all USB commands except VE come here).
    #    Flush any left over crap in buffer
    #    Send the command
    #    Process response
    #    Return to the user
    #----------------------------------------------------------------------------------------

    def send_command_thread(self,command="",timeout=.020):

        while not self.tx_queue.empty(): self.tx_queue.get()  #purge all queues
        while not self.rx_queue.empty(): self.rx_queue.get()  #one in , one out, no exceptions!

        for i in range (3):            #3 tries allowed here, to get it right
            try:
                #----------------------------------------------------------------------------------------
                #  If EMI creates any artifacts in the input buffer of the schnozz board, the \r will
                #  terminate the data, such that it will not be appended to the next legitimate command sent
                #-------------------------------------------------------------------------------------------
                r = ATC_TIMEOUT_ERROR

                throw_out = ''
                throw_out = self.schnozz_s_cmd.read(64)  # discard anything responded

                self.schnozz_s_cmd.write(command)        #send off the real command
                time.sleep (.002)                    #wait a bit

                if TRACE_USB_COMMS:
                    self.error_handler.log("Smart Cool: USB command sent = {}".format(command.strip()))

                #---------------------------------------------------------------------------------------
                #    Read and interpret command responses -
                #    All answers from device terminate with a line feed character
                #    Parse data and set return code depending on content, no answer in time frame is a timeout
                #----------------------------------------------------------------------------------------
                data = ""                              #clear input buffer
                wait_attempts = int(timeout/.002 + 1)
                               #until we know better
                while wait_attempts > 0:             #everybody should wait at least once
                    if ('\n' in data):
                        #print "HAL USB response =     ", data[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") +'\n'
                        if (data[0]== USB_OK):              #response is '.'
                            r = ATC_OK
                            break
                    else:
                        time.sleep(.002)
                        wait_attempts = wait_attempts - 1
                        data = data + self.schnozz_s_cmd.read(12)  #read some bytes

                if r != ATC_OK or len(data) != 3:
                    self.error_handler.log('Smart Cool: IO timeout error command : {}  data : {}'.format(command.strip(), data.strip()))

            except Exception as e:
                self.process_io_errors(e)
                r = ATC_USB_IO_ERROR    # io error - this one sticks if last attempt

            if r < 0:
                time.sleep(.050)            #let EMI settle down, if any caused this
                continue                    #try again , don't give up yet, stay and eat the food
            else:
                if TRACE_USB_COMMS:
                    self.error_handler.log("Smart Cool: USB reply = {}".format(r))
                break                       #OK, now you can be excused from the table
        #retry while loop ends
        return r                        #go back to caller with return code -


    #---------------------------------------------------------------------------------------
    #  React to IO Errors
    #    Trapped errors end up here to print to stdout, turn comms_up off, and close the port
    #----------------------------------------------------------------------------------------

    def process_io_errors(self,e):
        if e != self.last_e and self.error_display == True:
            self.last_e = e
            self.error_handler.log('Smart Cool: I/O error {}'.format(e))
            self.error_display = False
        self.comms_up.clear()  #cancel comms


    def start_IO_thread(self,start_it=True):
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
            self.tx_queue.put(('terminate',0))   #shut down schnozz IO thread politely
            self.USB_comms_thread.join(1.5)       # wait a bit for it to end

        if self.USB_comms_thread.is_alive():     # OH YEAH! if thread is alive
            self.error_handler.log('Smart Cool: Force quitting IO service') # no more mr nice guy!
            self.USB_comms_thread.terminate()    # machine gun it down - will show up as terminal interrupt in std out
            self.USB_comms_thread.join(1.5)       # wait for it to end and free any resources

        if start_it:
            self.USB_comms_thread=multiprocessing.Process(name='Schnozz USB/IO Service',target=self.process_the_queue)  #initialize thread definition
            self.USB_comms_thread.daemon = True  # allow parent to terminate while thread is active - only for emergency shutdowns
            self.USB_comms_thread.start()        # start reading the queue     (see below)
        else:
            self.tx_queue.close()                # turn out the lights
            self.rx_queue.close()


    def process_the_queue(self):
        #print 'Smart Cool:', 'IO Service ' + self.start_msg_suffix, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        while True:  #boogie till ya puke!
            work_item = self.tx_queue.get()      # this efficiently block until an item is available
            if 'VE' in work_item:               # are we trying to connect here?
                self.connect_to_device_thread()  # set's comms_up event
                continue

            if 'terminate' in work_item:        #shutting down?
                return  #no more work coming today - thread ends

            tx_command = work_item[0]            #put command in queue
            tx_timeout = work_item[1]            #pass on the time out
            self.rx_queue.put(self.send_command_thread(tx_command,tx_timeout))  #dispatch work and reply with rc


if __name__ == "__main__":
    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(),'w',0)

    try:    #mainline code covered by keyboard exception when hal shuts down
        schnozz_talker = zbotschnozz_hal_component()
        schnozz_talker.zbotschnozz_main()

    except KeyboardInterrupt:
        schnozz_talker.error_handler.log("Smart Cool: KeyboardInterrupt caught, exiting.")
        pass

    finally:
        schnozz_talker.error_handler.log("Smart Cool: Exit sequence started")
        schnozz_talker.start_IO_thread(False)            #just shut down IO Service if running
        schnozz_talker.hal.exit()
        schnozz_talker.error_handler.log('Smart Cool: HAL component : exited')

    sys.exit(0)
