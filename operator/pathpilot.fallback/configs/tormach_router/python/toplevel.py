# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# Portions Copyright © 2014-2018 Z-Bot LLC.
# License: GPL Version 2
#-----------------------------------------------------------------------


#  zbot atc prolog for ngc tool change programming

#pylint: disable=import-error

import hal, time
import serial
import sys
import commands
import redis
import emccanon
from interpreter import *
from constants import *  #goody bag of values from Tormach
import tormach_file_util
import datetime
import linuxcnc
import remap
import namedparams



def __init__(self):
    remap.init_stdglue(self)
    if self.task:
        # this is the milltask instance of interp

        #-------------------------------------------------------------------------------------
        #        build the following globals variables for the various atc ngc routines in remap
        #---------------------------------------------------------------------------------------
        self.params["_mode"] = 0     #auto is 0, -1 is manual change modes
        # user modal values to remember - and default settings if not stored
        self.params["_global_saved_user_G91"] = 0.0        # users G90/91 mode
        self.params["_global_saved_user_feed"] = 10.0      # users feed rate
        self.params["_global_saved_feed_enable"] = 1.0 # users feed override enablement
        self.params["_global_saved_speed_enable"] = 1.0 # users feed override enablement
        self.params["_global_saved_metric"] = 0.0          # users units
        self.params["_global_saved_tool_offset_applied"] = 1.0 # tool length offset applied

        #  define dio and aio pin numbers for motion control pins - ngc needs to know
        self.params["_exec_pin"] =     EXEC_PIN
        self.params["_request_data"] = REQUEST_DATA_PIN
        self.params["_request"] =      REQUEST_PIN
        self.params["_hal_return"] =   HAL_RETURN_PIN
        self.params["_atc_device"]  =  DEVICE_PIN
        self.params["_prompt_reply"] = PROMPT_REPLY_PIN
        self.params["_orient_drift"] = SPDL_ORNT_STATUS_PIN
        self.params["_spindle_is_locked"] = SPDL_IS_LOCKED  # set when successful orient

        #hal is changing dio pin
        self.params["_is_changing"] = ATC_HAL_IS_CHANGING

        #sequencing start for NGC hal request
        self.params["_request_number"] = 5000.0


        # zbotngcsub to ngc caller return parameter
        self.params["_atc_return"] =   0    #value will always be overwritten

        #   define commands for request pin - these are all commands
        #self.params["_kill_spindle"] =  0
        self.params["_solenoid"] =      ATC_SOLENOID
        self.params["_draw_bar"] =      ATC_DRAW_BAR
        self.params["_tray_index"] =    ATC_INDEX_TRAY
        self.params["_query_sensor"] =  ATC_QUERY_SENSOR
        self.params["_find_home"] =     ATC_FIND_HOME
        self.params["_offset_home"] =   ATC_OFFSET_HOME
        self.params["_lock_spindle"] =  ATC_SPINDLE_LOCK

        # data values for request_data       - must be set prior to issuing commamnds
        self.params["_activate"] =            ATC_ACTIVATE
        self.params["_deactivate"] =          ATC_DEACTIVATE
        self.params["_tray_in"] =             ATC_TRAY_SOLENOID      #solenoid number on
        self.params["_tray_out"] =           -ATC_TRAY_SOLENOID      #solenoid number off
        self.params["_blast_on"] =            ATC_BLAST_SOLENOID     #solenoid number on
        self.params["_blast_off"] =          -ATC_BLAST_SOLENOID    #solenoid number off
        self.params["_draw_high_pressure"] =  ATC_SPDL_LK_SOLENOID  #solenoid number on
        self.params["_draw_low_pressure"]  = -ATC_SPDL_LK_SOLENOID  #solenoid number off
        self.params["_pressure_sensor"] =     ATC_PRESSURE_SENSOR   #define sensor number
        self.params["_tray_in_sensor"]  =     ATC_TRAY_IN_SENSOR   #define sensor number
        self.params["_vfd_sensor"]      =     ATC_VFD_SENSOR  #define sensor number
        self.params["_draw_bar_sensor"] =     ATC_DRAW_SENSOR    #define sensor number
        self.params["_all_sensors"]     =     ATC_ALL_SENSORS    #cause enmass refresh

        #miscellaneous variables
        self.params["_spindle_orient_needed"] =   0.0      #BT 30 switch
        self.params["_go_to_tray_load"]        =   0.0      # if 1.0 tells NGC not to tray out
        self.params["_up_a_bit"]               =   0.0

        # error return codes
        self.params["_atc_ok"] =                   ATC_OK
        self.params["_atc_sensor_off"] =           ATC_SENSOR_OFF
        self.params["_atc_sensor_on"] =            ATC_SENSOR_ON
        self.params["_atc_command_reject"]=        ATC_COMMAND_REJECTED_ERROR
        self.params["_atc_homing_error"] =         ATC_USB_HOMING_ERROR
        self.params["_atc_timeout_error"] =        ATC_TIMEOUT_ERROR
        self.params["_atc_unkown_response_error"] =ATC_UNKNOWN_USB_RESP_ERROR
        self.params["_atc_unknown_command_error"] =ATC_UNKNOWN_USB_COMMAND_ERROR
        self.params["_atc_tray_error"] =           ATC_TRAY_ERROR
        self.params["_atc_usb_io_error"] =         ATC_USB_IO_ERROR
        self.params["_atc_halrequest_invalid"] =   ATC_UNKNOWN_REQUESTED_PIN
        self.params["_atc_pressure_error"] =       ATC_PRESSURE_FAULT
        self.params["_atc_not_found_error"] =      ATC_NOT_FOUND
        self.params["_atc_user_cancel"] =          ATC_USER_CANCEL
        self.params["_atc_interface_busy"] =       ATC_INTERFACE_BUSY
        self.params["_atc_interface_seq_error"] =  ATC_INTERFACE_ERROR
        self.params["_atc_spindle_running"]      = ATC_SPINDLE_RUNNING
        self.params["_atc_spindle_orient_error"] = ATC_SPINDLE_ORIENT_ERROR
        self.params["_atc_spindle_brake_error"]  = ATC_SPINDLE_LOCK_ERROR
        # instantiate some useful services, status channel, database binding

        self.redis = redis.Redis()         #get redis  channel instantiated

        # machine stats
        self.params["_orient_success_count"] = 0
        val = self.redis.hget('machine_stats', 'orient_success_count')
        if val:
            self.params["_orient_success_count"] = float(val)

        self.params["_orient_fail_count"] = 0
        val = self.redis.hget('machine_stats', 'orient_fail_count')
        if val:
            self.params["_orient_fail_count"] = float(val)

        self.params["_orient_retry_count"] = 0
        val = self.redis.hget('machine_stats', 'orient_retry_count')
        if val:
            self.params["_orient_retry_count"] = float(val)

        self.hal = hal.component("remap")
        self.hal.newpin("atc-tools-in-tray", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("atc-orient-status", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("axis.2.homed", hal.HAL_BIT, hal.HAL_IN)
        self.hal.ready()
        print 'REMAP hal component started',datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.atc_tray_tools = 10            #default
        self.ini = None
        self.M80_state = False              # T= indicates M80 save user state. F = restored by M81

    else:
        # this is a non-milltask instance of interp
        pass
