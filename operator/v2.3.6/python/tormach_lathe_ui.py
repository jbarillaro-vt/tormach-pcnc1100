#!/usr/bin/env python
# coding=utf-8
#-----------------------------------------------------------------------
# Copyright © 2014-2018 Tormach® Inc. All rights reserved.
# License: GPL Version 2
#-----------------------------------------------------------------------

# NOTE:
# If you have wingdbstub.py laying around, but you're using PyCharm, then the python process will segfault
# on launch in ways that are hard to figure out.
# so make a decision on which debugger if you want one, and comment out the other entirely.
#
# for debugging within Wing IDE
try:
    import wingdbstub
except ImportError:
    pass

# for debugging with PyCharm
#try:
#    import pydevd
    # Uncomment the next line if you have the PyCharm debug server listening.
    # Otherwise, this line pauses the load by 30 seconds on every launch which is very annoying.
    #pydevd.settrace('localhost', port=43777)
#except ImportError:
#    pass


# This is our own tormach debug console, has nothing to do with Wing or PyCharm
#import debugconsole


from locsupport import *
# This is a temp definition of _ to make it visible to pylint without complaint.
# At runtime below it is deleted right away and the _ alias that the gettext module import creates takes over
def _(msgid):
    return msgid

import gtk
import gobject
import sys
import redis
import tempfile
import shutil
import Queue
import linuxcnc
import hal
import gremlin
import os
import pango
import glib
import subprocess
import math
import errno
import cairo
from iniparse import SafeConfigParser

# Tormach modules
from constants import *
import crashdetection
import gremlinbase
from errors import *
import lathe_conversational
import ui_settings_lathe
import numpad
import tormach_file_util
import btn
import popupdlg
import machine
from ui_common import *
from ui_support import *
import regression_tests
import timer
from conversational import cparse
import lathe_conv_support
import singletons
import plexiglass
import tooltipmgr
import lathe_fs

# this is for customization like clearing or setting USBIO outputs upon E-Stop event or Reset or Stop Button pressed
# only if this import is found in ~/gcode/python will its functions be called
try:
    import ui_hooks
except ImportError:
    pass


# Helper list to keep track of the main notebook page IDs
__page_ids = [
    "notebook_main_fixed",
    "notebook_file_util_fixed",
    "notebook_settings_fixed",
    "notebook_offsets_fixed",
    "conversational_fixed",
    "alarms_fixed"
]


class lathe(TormachUIBase):
    G_CODES = [
        { 'Name' : 'G0',    'Function' : 'Rapid positioning'                               },
        { 'Name' : 'G1',    'Function' : 'Linear interpolation'                            },
        { 'Name' : 'G2',    'Function' : 'Clockwise circular interpolation'                },
        { 'Name' : 'G3',    'Function' : 'Counter clockwise circular interpolation'        },
        { 'Name' : 'G4',    'Function' : 'Dwell'                                           },
        { 'Name' : 'G7',    'Function' : 'Lathe Diameter Mode'                             },
        { 'Name' : 'G8',    'Function' : 'Lathe Radius Mode'                               },
        { 'Name' : 'G20',   'Function' : 'Inch unit'                                       },
        { 'Name' : 'G21',   'Function' : 'Millimeter unit'                                 },
        { 'Name' : 'G30',   'Function' : 'Go to pre-defined position'                      },
        { 'Name' : 'G30.1', 'Function' : 'Store pre-defined position'                      },
        { 'Name' : 'G33.1', 'Function' : 'Rigid Tapping'                                   },
        { 'Name' : 'G40',   'Function' : 'Cancel radius compensation'                      },
        { 'Name' : 'G41',   'Function' : 'Start radius compensation left'                  },
        { 'Name' : 'G41.1', 'Function' : 'Start dynamic radius compensation left'          },
        { 'Name' : 'G42',   'Function' : 'Start radius compenstation right'                },
        { 'Name' : 'G42.1', 'Function' : 'Start dynamic radius compensation right'         },
        { 'Name' : 'G54',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G55',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G56',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G57',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G58',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G59',   'Function' : 'Work offset coordinate system'                   },
        { 'Name' : 'G71',   'Function' : 'Canned cycle - lathe profiling'                  },
        { 'Name' : 'G73',   'Function' : 'Canned cycle - drilling with chip-break'         },
        { 'Name' : 'G76',   'Function' : 'Canned cycle - threading'                        },
#       { 'Name' : 'G80',   'Function' : 'Cancel canned cycle mode'                        },
#       { 'Name' : 'G81',   'Function' : 'Canned cycle - drilling'                         },
#       { 'Name' : 'G82',   'Function' : 'Canned cycle - drilling with dwell'              },
#       { 'Name' : 'G83',   'Function' : 'Canned cycle - peck drilling'                    },
#       { 'Name' : 'G85',   'Function' : 'Canned cycle - boring, feed out'                 },
#       { 'Name' : 'G86',   'Function' : 'Canned cycle - boring, spindle stop, rapid out'  },
#       { 'Name' : 'G88',   'Function' : 'Canned cycle - boring, spindle stop, manual out' },
#       { 'Name' : 'G89',   'Function' : 'Canned cycle - boring, dwell, feed out'          },
        { 'Name' : 'G90',   'Function' : 'Absolute distance mode'                          },
        { 'Name' : 'G91',   'Function' : 'Incremental distance mode'                       },
        { 'Name' : 'G90.1', 'Function' : 'I,K absolute distance mode'                      },
        { 'Name' : 'G91.1', 'Function' : 'I,K incremental distance mode'                   },
        { 'Name' : 'G93',   'Function' : 'Feed inverse time mode'                          },
        { 'Name' : 'G94',   'Function' : 'Feed per minute mode'                            },
        { 'Name' : 'G95',   'Function' : 'Feed per revolution mode'                        },
        { 'Name' : 'G96',   'Function' : 'Constant surface speed mode'                     },
        { 'Name' : 'G97',   'Function' : 'RPM mode'                                        },
#       { 'Name' : 'G98',   'Function' : 'Retract to initial Z height'                     },
#       { 'Name' : 'G99',   'Function' : 'Retract to R height'                             }
        ]
    _report_status = [linuxcnc.G_CODE_ORIGIN,
                      linuxcnc.G_CODE_DISTANCE_MODE,
                      linuxcnc.G_CODE_UNITS,
                      linuxcnc.G_CODE_LATHE_DIAMETER_MODE,
                      linuxcnc.G_CODE_MOTION_MODE,
                      linuxcnc.G_CODE_CUTTER_SIDE,
                      linuxcnc.G_CODE_FEED_MODE,
                      linuxcnc.G_CODE_SPINDLE_MODE,
                      linuxcnc.G_CODE_DISTANCE_MODE_IJK]

    _max_tool_number = MAX_LATHE_TOOL_NUM
    _min_tool_number = 1

    def __init__(self):
        # glade/gtk.builder setup
        gladefile = os.path.join(GLADE_DIR, 'tormach_lathe_ui.glade')
        ini_file_name = sys.argv[2]

        TormachUIBase.__init__(self, gladefile, ini_file_name)

        self.machine_type = MACHINE_TYPE_LATHE

        self.PROFILE_ROWS = 64
        self.program_exit_code = EXITCODE_SHUTDOWN

        self.setup_key_sets()

        missing_signals = self.builder.connect_signals(self)
        if missing_signals is not None:
            raise RuntimeError("Cannot connect signals: ", missing_signals)

        # --------------------------------------------------------
        # linuxcnc command and status objects
        # --------------------------------------------------------
        self.command = linuxcnc.command()
        self.status = linuxcnc.stat()
        self.error = linuxcnc.error_channel()

        self.create_hal_pins()

        # Start to encapsulate machine config specifics in one place
        self.machineconfig = machine.MachineConfig(self, self.configdict, self.redis, self.error_handler, self.inifile)

        # -------------------------------------------------------
        # PostGUI HAL
        # -------------------------------------------------------

        # The postgui is dependent on a number of hal user space components being created and ready and
        # there can be timing variances where the postgui runs and the pin isn't quite ready yet to be connected
        # by signal.

        if self.machineconfig.machine_class() == 'lathe':
            # we don't try to wait for these in rapidturn mode
            if self.machineconfig.has_ecm1():
                if not self.pause_for_user_space_comps(("tormachltc_ecm1",)):
                    self.error_handler.log("Error: something failed waiting for user comps to be ready - aborting")
                    sys.exit(1)
            else:
                if not self.pause_for_user_space_comps(("tormachltc",)):
                    self.error_handler.log("Error: something failed waiting for user comps to be ready - aborting")
                    sys.exit(1)


        postgui_halfile = self.inifile.find("HAL", "POSTGUI_HALFILE")
        if postgui_halfile:
            self.error_handler.log("Running postgui HAL file {}".format(postgui_halfile))
            p = subprocess.Popen(["halcmd", "-i", sys.argv[2], "-f", postgui_halfile])
            p.wait()
            if p.returncode != 0:
                self.error_handler.log("Error: halcmd returned {} from postgui".format(p.returncode))
                sys.exit(1)
        else:
            # complain about missing POSTGUI_HALFILE
            self.error_handler.write("Error: missing POSTGUI_HALFILE in .INI file.", ALARM_LEVEL_DEBUG)
            sys.exit(1)

        # configure the ShuttleXpress (if preset)
        postgui_shuttlexpress_halfile = self.inifile.find("HAL", "POSTGUI_SHUTTLEXPRESS_HALFILE")
        self.jog_shuttle_load_failure = False
        if postgui_shuttlexpress_halfile:
            if subprocess.call(["halcmd", "-i", sys.argv[2], "-f", postgui_shuttlexpress_halfile]):
                #self.error_handler.write("Warning: something failed running halcmd on " + postgui_shuttlexpress_halfile, ALARM_LEVEL_DEBUG)
                # warning of this is controlled by 'machine_prefs', 'check_for_jog_shuttle'
                self.jog_shuttle_load_failure = True
        else:
            # complain about missing POSTGUI_SHUTTLEXPRESS_HALFILE
            self.error_handler.write("Warning: missing POSTGUI_SHUTTLEXPRESS_HALFILE in .INI file.", ALARM_LEVEL_DEBUG)

        self.max_rpm = 0
        self.min_rpm = 0

        self.settings = ui_settings_lathe.lathe_settings(self, self.redis, 'lathe_settings.glade')
        tablabel = gtk.Label()
        tablabel.set_markup('<span weight="regular" font_desc="Roboto Condensed 10" foreground="black">Settings</span>')
        self.notebook.insert_page(self.settings.fixed, tab_label=tablabel, position=2)
        self.settings.fixed.put(self.gcodes_display.sw, 10, 10)

        # retrieve main window, notebooks, fixed containers
        self.fixed = self.builder.get_object("fixed")
        self.offsets_notebook = self.builder.get_object("offsets_notebook")
        notebook_main_fixed = self.builder.get_object("notebook_main_fixed")
        self.notebook_tool_fixed = self.builder.get_object("tool_offsets_fixed")
        self.tool_offsets_fixed = self.builder.get_object("work_offsets_fixed")

        # throw out mousewheel events to prevent scrolling through notebooks on wheel
        self.notebook.connect("scroll-event", self.on_mouse_wheel_event)
        self.conv_notebook.connect("scroll-event", self.on_mouse_wheel_event)
        self.offsets_notebook.connect("scroll-event", self.on_mouse_wheel_event)

        # --------------------------------------------------------
        # lathe GUI is used for lathe and mills in RapidTurn (code name was duality)
        # Not all HAL pins can be connected if we're running a RapidTurn config
        # --------------------------------------------------------

        tooltipmgr.TTMgrInitialize(ui=self, window=self.window, builder_list=[self.builder])
        self.update_tooltipmgr_timers()

        config_label = self.builder.get_object('config_label')
        config_label.modify_font(pango.FontDescription('Bebas ultra-condensed 8'))
        # The machineconfig.model_name() is always accurate for mills, even when in RapidTurn mode.
        # So adjust the on screen label if needed.
        text = self.machineconfig.model_name()
        if self.machineconfig.in_rapidturn_mode():
            text += " RapidTurn"
        if self.machineconfig.is_sim():
            text += " SIM"
        config_label.set_text(text)

        # Machine characteristics - used by conversational feeds and speeds
        self.mach_data = { "max_ipm" : 60, "motor_curve": None}

        ll,lh = (self.ini_int('SPINDLE','LO_RANGE_MIN'), self.ini_int('SPINDLE','LO_RANGE_MAX'))
        hl,hh = (self.ini_int('SPINDLE','HI_RANGE_MIN'), self.ini_int('SPINDLE','HI_RANGE_MAX'))
        self.mach_data_lo = ((ll,.4),(1400,3.2),(1500,3.1),(lh,2.25))
        self.mach_data_hi = ((hl,.35),(1400,3.2),(1600,3.05),(hh,2.2))

        #TODO grepping for model names shouldn't be done here, and magic numbers too!!!
        if '15L Slant-PRO' == self.machineconfig.model_name():
            self.mach_data_lo = ((ll,.4),(1400,3.2),(1500,3.1),(lh,2.25))
            self.mach_data_hi = ((hl,.35),(1400,3.2),(1600,3.05),(hh,2.2))
        elif self.machineconfig.in_rapidturn_mode():
            self.mach_data_lo = ((ll,.15),(1400,.74),(1600,.72),(lh,.5))
            self.mach_data_hi = self.mach_data_lo

        # axis max velocities for jog speed clamping on servo (M+ or MX) machines
        self.axis_unhomed_clamp_vel = {0:0, 1:0, 2:0}
        self.axis_unhomed_clamp_vel[0] = self.ini_float('AXIS_0', 'MAX_VELOCITY', 0) * AXIS_SERVOS_CLAMP_VEL_PERCENT
        self.axis_unhomed_clamp_vel[1] = self.ini_float('AXIS_1', 'MAX_VELOCITY', 0) * AXIS_SERVOS_CLAMP_VEL_PERCENT
        self.axis_unhomed_clamp_vel[2] = self.ini_float('AXIS_2', 'MAX_VELOCITY', 0) * AXIS_SERVOS_CLAMP_VEL_PERCENT

        # --------------------------------------------------------
        # gremlin tool path display setup
        # --------------------------------------------------------
        GREMLIN_INITIAL_WIDTH = 680
        self.gremlin = Tormach_Lathe_Gremlin(self,GREMLIN_INITIAL_WIDTH,410)
        notebook_main_fixed.put(self.gremlin, 322, 0)

        # resize the message line so that it matches the width of the gremlin
        self.message_line.set_size_request(GREMLIN_INITIAL_WIDTH, 35)
        self.notebook_main_fixed.put(self.message_line, 322, 375)
        self.clear_message_line_text()

        # elapsed time label on top of gremlin
        # the Gtk fixed container doesn't support control over z-order of overlapping widgets.
        # so the behavior we get is arbitrary and seems to depend on order of adding the
        # widget to the container.  sweet.
        self.notebook_main_fixed.put(self.elapsed_time_label, 928, 390)
        self.notebook_main_fixed.put(self.remaining_time_label, 928, 370)
        self.notebook_main_fixed.put(self.preview_clipped_label, 904, 0)

        # add the correct gcode options for lathes
        tablabel = gtk.Label()
        tablabel.set_markup('<span weight="regular" font_desc="Roboto Condensed 10" foreground="black">View Options</span>')

        self.gremlin_options = gremlin_options.gremlin_options(self, 'lathe_gremlin_options.glade')
        self.gremlin_options.update_grid_size('med')
        self.gcode_options_notebook.append_page(self.gremlin_options.fixed, tab_label=tablabel)
        self.gcode_options_notebook.connect("switch-page", self.gcodeoptions_switch_page)

        # errors - now create the full error_handler() since we're initialized enough
        self.error_handler = error_handler(self.builder, self.moving)
        self.update_mgr.error_handler = self.error_handler

        # optional UI hooks for reset/stop buttons and estop events
        self.version_list = versioning.GetVersionMgr().get_version_list()
        self.ui_hooks = None
        try:
            self.ui_hooks = ui_hooks.ui_hooks(self.command, self.error_handler, self.version_list, digital_output_offset=5)
        except NameError:
            self.error_handler.write("optional ui_hooks module not found", ALARM_LEVEL_DEBUG)

        # --------------------------------------------------------
        # conversational
        # --------------------------------------------------------
        self.conversational = lathe_conversational.conversational(self,
                                                                  self.status,
                                                                  self.error_handler,
                                                                  self.redis,
                                                                  self.hal)

        self.set_hal_pin_defaults()

        set_packet_read_timeout(self.inifile)

        self.hal['debug-level'] = 0

        # initialize jog shuttle ring speeds
        # make speed 7 max_velocity, scale such that speed 1 is min
        # INI file [AXIS_0|2] MAX_VELOCITY = 1.5 inches/second or 90 inches/minute
        # 90 IPM / 0.5 min speed => 180, 6th root of 180 is about 2.390
        '''
        min_speed = 0.5, g_multiplier = 2.39
        0.5
        1.195
        2.85605
        6.8259595
        16.314043205
        38.99056326
        93.1874461913
        '''
        min_speed = 0.5
        g_multiplier = 2.390
        c_multiplier = 1.0
        self.hal['jog-ring-speed-1'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-2'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-3'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-4'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-5'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-6'] = c_multiplier * min_speed
        c_multiplier = c_multiplier * g_multiplier
        self.hal['jog-ring-speed-7'] = c_multiplier * min_speed

        # trajmaxvel from ini for maxvel slider
        self.maxvel_lin = self.ini_float('TRAJ', 'MAX_VELOCITY', 1.5)
        self.maxvel_ang = self.ini_float('TRAJ', 'MAX_ANGULAR_VELOCITY', 22)

        # jogging direction, conversational tool orientation validation
        self.is_front_toolpost_lathe = False
        display_geometry = self.inifile.find("DISPLAY", "GEOMETRY")
        if display_geometry == "XZ":
            self.is_front_toolpost_lathe = True

        # ---------------------------------------------
        # member variable init
        # ---------------------------------------------
        self.mach_data['motor_curve'] = self.mach_data_hi # this needs to be initialized to something

        # Make Feeds and Speeds manager construction explicit and controlled
        self.fs_mgr = lathe_fs.LatheFS(uiobject=self)
        self.material_data = ui_support.MaterialData(self, self.builder.get_object('conversational_fixed'))


        # Set initial toggle button states - previous states used to conditionally update bitmaps

        self.status.poll()
        self.jog_metric_scalar = 1
        self.first_run = True
        self.estop_alarm = True
        self.interp_alarm = False
        self.single_block_active = False
        self.feedhold_active = self.prev_feedhold_active = False
        self.m01_break_active = True
        self.x_referenced = self.prev_x_referenced = 0
        self.z_referenced = self.prev_z_referenced = 0
        self.y_referenced = self.prev_y_referenced = 0
        self.spindle_direction = self.prev_spindle_direction = self.status.spindle_direction
        self.css_active = self.status.gcodes[linuxcnc.G_CODE_SPINDLE_MODE] == 960
        self.prev_css_active = None   # force a refresh of the button appearance in the first periodic
        self.f_per_rev_active = self.status.gcodes[linuxcnc.G_CODE_FEED_MODE] == 950
        self.prev_f_per_rev_active = None  # force a refresh of the button appearance in the first periodic
        self.door_switch = self.hal['door-switch']
        self.prev_door_switch = not self.door_switch
        self.home_switch = self.hal['home-switch']
        self.prev_home_switch = not self.home_switch
        self.prev_collet_closer_status = 2   # can't possibly match collet_closer_status so will force a button image refresh in first periodic...
        self.collet_closer_status = self.hal['collet-closer-status']
        self.notebook_locked = False
        self.conv_face_basic_ext = 'basic'
        self.conv_od_basic_ext = 'basic'
        self.conv_id_basic_ext = 'basic'
        self.conv_drill_tap = 'drill'
        self.conv_thread_ext_int = 'external'
        self.conv_profile_ext = 'external'
        self.conv_thread_rh_lh = 'rh'
        self.conv_thread_note = ''
        self.conv_groove_part = 'groove'
        self.conv_chamfer_radius = 'chamfer'
        self.conv_chamfer_od_id = 'od'
        self.conv_profile_x_mode = 'diameter'
        self.dros_locked = False
        self.prev_f_word = 0
        self.spindle_range_alarm = self.prev_spindle_range_alarm = 0
        self.mm_inch_scalar = 1
        self.is_gcode_program_loaded = False
        self.program_paused_for_door_sw_open = False
        self.probe_tripped_display = False
        self.prev_notebook_page_id = 'notebook_main_fixed'
        self.F1_page_toggled = False
        self.current_tool = 0
        self.cpu_usage = 0
        # For detecting hang with stopped spindle in synched move
        self.f_per_rev_spindle_timeout = self.ini_float(
            'SPINDLE', 'F_PER_REV_SPINDLE_TIMEOUT', 10)
        self.f_per_rev_spindle_counter = 0
        self.current_g5x_offset = self.status.g5x_offset
        self.current_g92_offset= self.status.g92_offset


        # ----------------------------------------------
        # Buttons (gtk.eventbox with image on top)
        # ----------------------------------------------

        # create a list of image object names
        self.image_list = ('cycle_start_image', 'single_block_image', 'm01_break_image', 'feedhold_image',
                           'coolant_image', 'rev_image', 'fwd_image', 'spindle_override_100_image',
                           'feed_override_100_image', 'maxvel_override_100_image', 'reset_image',
                           'jog_inc_cont_image',
                           'css_image', 'feed_per_rev_image', 'jog_zero_image', 'jog_one_image',
                           'jog_two_image', 'jog_three_image', 'jog_x_active_led', 'jog_z_active_led', 'jog_y_active_led',
                           'turret_fwd_image', 'tool_touch_chuck', 'touch_x_image', 'touch_z_image', 'reset_tool_image',
                           'acc_input_led',
                           'set_g30_image', 'conv_id_turn_background', 'id_basic_extended_btn_image',
                           'id_turn_main_image', 'id_turn_detail_image',
                           'conv_drill_tap_image', 'drill_tap_btn_image', 'profile_ext_int_image',
                           'conv_profile_background', 'lathe_profile_points_background', 'lathe_profile_roughing_background',
                           'profile_roughing_page',
                           'lathe_profile_finishing_background', 'lathe_profile_raise_in_table_btn_image',
                           'lathe_profile_lower_in_table_btn_image', 'lathe_profile_insert_row_table_btn_image',
                           'lathe_profile_delete_row_table_btn_image', 'lathe_profile_clear_table_btn_image',
                           'thread_ext_int_image', 'thread_rh_lh_image', 'conv_thread_image', 'thread_pitch_image',
                           'conv_groove_part_image', 'groove_part_btn_image', 'finish-editing-button',
                           'corner_chamfer_radius_btn_image', 'corner_id_od_btn_image', 'conv_corner_background',
                           'door_sw_led','encoder_a_led', 'encoder_b_led', 'encoder_z_led', 'tool_orientation_image',
                           'tool_table_orientation_image', 'tool_gcode_orientation_image', 'machine_ok_led',
                           'usbio_input_0_led', 'usbio_input_1_led', 'usbio_input_2_led', 'usbio_input_3_led',
                           'usbio_output_0_led', 'usbio_output_1_led', 'usbio_output_2_led', 'usbio_output_3_led',
                           'LED_button_green', 'LED_button_black',
                           'error_image_1', 'error_image_2', 'home_sw_led', 'ref_x_image', 'ref_y_image', 'ref_z_image',
                           'collet_closer_image','lathe_profile_tool_angle_background','internet_led', 'expandview_button_image',
                           'export_tool_table', 'import_tool_table')

        self.tool_image_list = ('tt_rear_tp_profile_image', 'tt_rear_tp_lh_turn_image', 'tt_front_tp_lh_profile_image',
                                'tt_front_tp_profile_image', 'tt_front_tp_rh_profile_image', 'tt_rear_tp_lh_profile_image',
                                'tt_rear_tp_profile_image', 'tt_rear_tp_rh_profile_image',
                                'tt_front_tp_lh_turn_image', 'tt_rear_tp_turn_image', 'tt_front_tp_turn_image',
                                'tt_rear_tp_thread_image', 'tt_front_tp_thread_image', 'tt_rear_tp_part_image',
                                'tt_front_tp_part_image', 'tt_rear_id_thread_image', 'tt_center_drill_image',
                                'tt_rear_boring_bar_image', 'tt_front_boring_bar_image', 'tt_front_id_thread_image')

        # create dictionary of key value pairs of image names, image objects
        self.image_list = dict(((i, self.builder.get_object(i))) for i in self.image_list)
        self.tool_image_list = dict(((i, self.builder.get_object(i))) for i in self.tool_image_list)

        # gtk.eventboxes
        self.button_list = ('cycle_start', 'single_block', 'm01_break', 'feedhold', 'stop', 'coolant',
                            'reset', 'feedrate_override_100', 'rpm_override_100', 'maxvel_override_100', 'ccw', 'spindle_stop', 'cw', 'zero_z',
                            'feed_per_rev', 'css', 'jog_zero', 'jog_one', 'jog_two', 'jog_three', 'jog_inc_cont',
                            'logdata_button',
                            'turret_fwd', 'set_g30', 'goto_g30', 'touch_x','touch_z', 'reset_tool',
                            'exit', 'id_basic_extended',
                            'drill_tap', 'thread_ext_int', 'thread_rh_lh', 'groove_part', 'update',
                            'lathe_profile_raise_in_table', 'lathe_profile_lower_in_table',
                            'lathe_profile_insert_row_table', 'lathe_profile_delete_row_table',
                            'lathe_profile_clear_table', 'profile_ext_int',
                            'corner_chamfer_radius', 'corner_id_od',
                            'post_to_file', 'append_to_file', 'clear', 'ref_x', 'ref_y', 'ref_z',
                            'collet_closer', 'expandview_button',
                            'usbio_output_0_led_button', 'usbio_output_1_led_button', 'usbio_output_2_led_button', 'usbio_output_3_led_button',
                            'internet_led_button', 'export_tool_table', 'import_tool_table')

        self.tool_touch_eventbox_list = ('tt_rear_tp_profile_eventbox', 'tt_rear_id_thread_eventbox',
                                         'tt_rear_tp_lh_profile_eventbox', 'tt_rear_tp_rh_profile_eventbox',
                                         'tt_front_tp_profile_eventbox','tt_rear_tp_lh_turn_eventbox',
                                         'tt_front_tp_lh_profile_eventbox', 'tt_front_tp_rh_profile_eventbox',
                                         'tt_front_tp_lh_turn_eventbox', 'tt_rear_tp_turn_eventbox',
                                         'tt_front_tp_turn_eventbox', 'tt_rear_tp_thread_eventbox',
                                         'tt_front_tp_thread_eventbox', 'tt_rear_tp_part_eventbox',
                                         'tt_front_tp_part_eventbox', 'tt_center_drill_eventbox',
                                         'tt_rear_boring_bar_eventbox', 'tt_front_boring_bar_eventbox',
                                         'tt_front_id_thread_eventbox')

        # create dictionary of glade names, eventbox objects
        self.button_list = dict(((i, self.builder.get_object(i))) for i in self.button_list)
        self.tool_touch_eventbox_list = dict(((i, self.builder.get_object(i))) for i in self.tool_touch_eventbox_list)

        self.composite_png_button_images()

        # Create additional buttons manually
        self.setup_gcode_buttons()
        self.setup_copy_buttons()

        # get initial x/y locations for eventboxes
        for name, eventbox in self.button_list.iteritems():
            eventbox.x = ui_misc.get_x_pos(eventbox)
            eventbox.y = ui_misc.get_y_pos(eventbox)

        # ----------------------------------------------
        # DROs (gtk.entry)
        # ----------------------------------------------

        # DRO object names on main screen and tool tab of notebook
        self.dro_list = ('dia_dro', 'z_dro', 'y_dro', 'feed_per_min_dro', 'touch_dia_dro', 'touch_z_dro',
                         'feed_per_rev_dro', 'spindle_rpm_dro', 'spindle_css_dro', 'tool_dro',
                         'touch_dia_dro', 'touch_z_dro', 'encoder_counts_dro')

        # create  dictionary of DRO names, gtk.entry objects
        self.dro_list = dict(((i, self.builder.get_object(i))) for i in self.dro_list)
        for name, dro in self.dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)
            dro.masked = False

        self.dro_list['encoder_counts_dro'].modify_font(pango.FontDescription('Roboto Condensed 12'))

        self.dro_list['y_dro'].modify_font(pango.FontDescription('helvetica ultra-condensed 12'))

        # when rotation is present via G10 L2 the axis DROs display in italic font to alert us
        self.xy_dro_font_description = self.conv_dro_font_description
        self.rotation_xy_dro_font_description = pango.FontDescription('helvetica italic ultra-condensed 22')
        self.prev_self_rotation_xy = 0

        # DROs common to all conversational routines
        self.conv_dro_list = (
            'conv_title_dro',
            'conv_work_offset_dro',
            'conv_rough_sfm_dro',
            'conv_rough_fpr_dro',
            'conv_finish_sfm_dro',
            'conv_finish_fpr_dro',
            'conv_max_spindle_rpm_dro')

        self.conv_dro_list = dict(((i, self.builder.get_object(i))) for i in self.conv_dro_list)
        for name, dro in self.conv_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.conv_dro_list['conv_title_dro'].modify_font(pango.FontDescription('helvetica ultra-condensed 18'))

        self.conv_rough_sfm_label = self.builder.get_object("conv_rough_sfm_text")
        self.conv_finish_sfm_label = self.builder.get_object("conv_finish_sfm_text")
        self.conv_rough_fpr_label = self.builder.get_object("conv_rough_fpr_text")
        self.conv_finish_fpr_label = self.builder.get_object("conv_finish_fpr_text")


        # od turn DROs, list order sets focus passing order, wraps at end
        self.od_turn_dro_list = (
            'od_turn_tool_num_dro',
            'od_turn_z_end_dro',
            'od_turn_stock_dia_dro',
            'od_turn_final_dia_dro',
            'od_turn_fillet_dro',
            'od_turn_z_start_dro',
            'od_turn_tc_dro',
            'od_turn_finish_doc_dro',
            'od_turn_rough_doc_dro')

        self.od_focus_list = self.od_turn_dro_list

        self.od_turn_dro_list = dict(((i, self.builder.get_object(i))) for i in self.od_turn_dro_list)
        self.create_page_DRO_attributes(page_id='od_turn_fixed',common=self.conv_dro_list,spec=self.od_turn_dro_list,tool=self.od_turn_dro_list['od_turn_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.od_turn_dro_list['od_turn_rough_doc_dro'],f_doc=self.od_turn_dro_list['od_turn_finish_doc_dro'],
                                        diameter=self.od_turn_dro_list['od_turn_stock_dia_dro'],z_start=self.od_turn_dro_list['od_turn_z_start_dro'],
                                        z_end=self.od_turn_dro_list['od_turn_z_end_dro'])

        for name, dro in self.od_turn_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)


        # id turn DROs, list order sets focus passing order, wraps at end
        self.id_basic_dro_list = (
            'id_basic_tool_num_dro',
            'id_basic_z_start_dro',
            'id_basic_z_end_dro',
            'id_basic_final_dia_dro',
            'id_basic_pilot_dia_dro',
            'id_basic_rough_doc_dro',
            'id_basic_finish_doc_dro',
            'id_basic_tc_dro')

        self.id_basic_focus_list = self.id_basic_dro_list

        self.id_basic_dro_list = dict(((i, self.builder.get_object(i))) for i in self.id_basic_dro_list)
        for name, dro in self.id_basic_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)
        self.create_page_DRO_attributes(page_id='id_turn_fixed',common=self.conv_dro_list,spec=self.id_basic_dro_list,tool=self.id_basic_dro_list['id_basic_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.id_basic_dro_list['id_basic_rough_doc_dro'],f_doc=self.id_basic_dro_list['id_basic_finish_doc_dro'],
                                        diameter=self.id_basic_dro_list['id_basic_final_dia_dro'],z_start=self.id_basic_dro_list['id_basic_z_start_dro'],
                                        z_end=self.id_basic_dro_list['id_basic_z_end_dro'])


        # id turn DROs, list order sets focus passing order, wraps at end
        self.id_turn_dro_list = (
            'id_turn_tool_num_dro',
            'id_turn_z_start_dro',
            'id_turn_z_end_dro',
            'id_turn_final_dia_dro',
            'id_turn_pilot_dia_dro',
            'id_turn_fillet_dro',
            'id_turn_pilot_dro',
            'id_turn_rough_doc_dro',
            'id_turn_finish_doc_dro',
            'id_turn_tc_dro',
            'id_turn_face_doc_dro')

        self.id_focus_list = self.id_turn_dro_list

        self.id_turn_dro_list = dict(((i, self.builder.get_object(i))) for i in self.id_turn_dro_list)
        for name, dro in self.id_turn_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)
        self.create_page_DRO_attributes(page_id='id_turn_fixed',attr='turn_dros',common=self.conv_dro_list,spec=self.id_turn_dro_list,tool=self.id_turn_dro_list['id_turn_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.id_turn_dro_list['id_turn_rough_doc_dro'],f_doc=self.id_turn_dro_list['id_turn_finish_doc_dro'],
                                        diameter=self.id_turn_dro_list['id_turn_final_dia_dro'],z_start=self.id_turn_dro_list['id_turn_z_start_dro'],
                                        z_end=self.id_turn_dro_list['id_turn_z_end_dro'])

        self.id_turn_fillet_label     = self.builder.get_object("id_turn_fillet_text")
        self.id_turn_pilot_end_label  = self.builder.get_object("id_turn_pilot_end_text")
        self.id_turn_face_doc_label   = self.builder.get_object("id_turn_face_doc_text")
        self.id_turn_tool_text1_label = self.builder.get_object("id_turn_tool_text1")
        self.id_turn_roughing_label   = self.builder.get_object("id_turn_roughing_text")

#---------------------------------------------------------------------------------------------------
# Profile Gui items
#---------------------------------------------------------------------------------------------------
        profile_font = pango.FontDescription('helvetica ultra-condensed 18')
        profile_i_font = pango.FontDescription('helvetica ultra-condensed 16')

        self.profile_liststore = gtk.ListStore(str, str, str, str)
        for id_cnt  in range(1, self.PROFILE_ROWS + 1):
            self.profile_liststore.append([id_cnt, '', '', ''])

        self.profile_treeview = gtk.TreeView(self.profile_liststore)

        self.profile_i_column  = gtk.TreeViewColumn()
        self.profile_x_column  = gtk.TreeViewColumn('')
        self.profile_z_column  = gtk.TreeViewColumn('')
        self.profile_r_column  = gtk.TreeViewColumn('')

        self.profile_treeview.append_column(self.profile_i_column)
        self.profile_treeview.append_column(self.profile_x_column)
        self.profile_treeview.append_column(self.profile_z_column)
        self.profile_treeview.append_column(self.profile_r_column)

        self.profile_treeview.set_rules_hint(True)
        self.profile_treeview.set_headers_visible(False)
        self.profile_treeview.set_grid_lines(gtk.TREE_VIEW_GRID_LINES_BOTH)

        renderer = gtk.CellRendererText()
        renderer.set_property('editable', False)
        renderer.set_property('cell-background', '#EEBBBB')
        renderer.set_property('font-desc', profile_i_font)
        renderer.set_property('xalign',0.5)
        renderer.set_property('yalign',1)
        renderer.set_property('height',28)
        self.profile_i_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.profile_i_column.set_fixed_width(23)
        self.profile_i_column.pack_start(renderer, True)
        self.profile_i_column.set_attributes(renderer, text=0)
        self.profile_x_renderer = renderer

        renderer = gtk.CellRendererText()
        renderer.set_property('editable', True)
        renderer.set_property('font-desc', profile_font)
        renderer.set_property('xalign',0.8)
        renderer.set_property('yalign',1)
        renderer.set_property('height',28)
#       renderer.set_property('rise',12)
#       renderer.set_property('rise-set',True)
        self.profile_x_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.profile_x_column.set_fixed_width(99)
        self.profile_x_column.pack_start(renderer, True)
        self.profile_x_column.set_attributes(renderer, text=1)
        renderer.connect('edited', self.on_profile_x_column_edited, self.profile_liststore)
        renderer.connect('editing-started', self.on_profile_x_column_editing_started, profile_font)
        self.profile_x_renderer = renderer

        renderer = gtk.CellRendererText()
        renderer.set_property('editable', True)
        renderer.set_property('font-desc', profile_font)
        renderer.set_property('xalign',0.8)
        renderer.set_property('yalign',1)
        renderer.set_property('height',28)
#       renderer.set_property('rise',12)
        self.profile_z_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.profile_z_column.set_fixed_width(99)
        self.profile_z_column.pack_start(renderer, True)
        self.profile_z_column.set_attributes(renderer, text=2)
        renderer.connect('edited', self.on_profile_z_column_edited, self.profile_liststore)
        renderer.connect('editing-started', self.on_profile_z_column_editing_started, profile_font)
        self.profile_y_renderer = renderer

        renderer = gtk.CellRendererText()
        renderer.set_property('editable', True)
        renderer.set_property('font-desc', profile_font)
        renderer.set_property('xalign',0.8)
        renderer.set_property('yalign',1)
        renderer.set_property('height',28)
#       renderer.set_property('rise',12)
#       self.profile_r_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.profile_r_column.set_fixed_width(99)
        self.profile_r_column.pack_start(renderer, True)
        self.profile_r_column.set_attributes(renderer, text=3)
        renderer.connect('edited', self.on_profile_r_column_edited, self.profile_liststore)
        renderer.connect('editing-started', self.on_profile_r_column_editing_started, profile_font)
        self.profile_r_renderer = renderer
        # show in notebook

        # create a scrolled window to hold the treeview
        self.scrolled_window_profile_table = gtk.ScrolledWindow()
        self.scrolled_window_profile_table.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        profile_points_fixed = self.builder.get_object('lathe_profile_points_fixed')
        profile_points_fixed.put(self.scrolled_window_profile_table, 4, 32)
        # the treeview knows about scrolling so do NOT add it using add_with_viewport or you
        # break all inherent keyboard navigation.
        self.scrolled_window_profile_table.add(self.profile_treeview)
        self.scrolled_window_profile_table.set_size_request(321, 270)
        profile_selection = self.profile_treeview.get_selection()
        profile_selection.set_mode(gtk.SELECTION_SINGLE)
        profile_selection.connect('changed',self.on_profile_selection_changed)

        self.profile_dro_list = (
            'profile_tool_num_dro',
            'profile_stock_x_dro',
            'profile_stock_z_dro',
            'profile_tool_front_angle_dro',
            'profile_tool_rear_angle_dro',
            'profile_roughing_tool_clear_x_dro',
            'profile_roughing_tool_clear_z_dro',
            'profile_roughing_doc_dro',
            'profile_finish_doc_dro',
            'profile_finish_passes_dro',
        )
        self.profile_dro_list = dict(((i, self.builder.get_object(i))) for i in self.profile_dro_list)
        self.create_page_DRO_attributes(page_id='profile_fixed',common=self.conv_dro_list,spec=self.profile_dro_list,tool=self.profile_dro_list['profile_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.profile_dro_list['profile_roughing_doc_dro'],f_doc=self.profile_dro_list['profile_finish_doc_dro'],
                                        diameter=self.profile_dro_list['profile_stock_x_dro'])
        for name, dro in self.profile_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        profile_sketch_area = self.builder.get_object('profile_sketch_area')
        w,h = profile_sketch_area.get_size_request()
        self.profile_renderer = lathe_conv_support.LatheProfileRenderer(self, w, h)
        profile_fixed = self.builder.get_object('profile_fixed')
        self.tool_renderer = lathe_conv_support.ToolRenderer(self, 50)
        (x,y) = profile_fixed.child_get_property(self.profile_dro_list['profile_tool_num_dro'],'x'),\
                profile_fixed.child_get_property(self.profile_dro_list['profile_tool_num_dro'],'y')
        x += self.profile_dro_list['profile_tool_num_dro'].get_property('width-request')
        profile_fixed.put(self.tool_renderer,x+84,y)
        profile_sketch_area.put(self.profile_renderer,1,1)
        profile_rough_finish_page = self.builder.get_object('lathe_profile_roughing_finishing_fixed')
        profile_rough_finish_page.set_focus_chain([self.profile_dro_list['profile_roughing_doc_dro'],
                                                   self.profile_dro_list['profile_finish_doc_dro'],
                                                   self.profile_dro_list['profile_finish_passes_dro']])
        self.profile_notebook = self.builder.get_object('profile_notebook_type')
        self.profile_sub_number = None
        self.update_subroutine_number()


#---------------------------------------------------------------------------------------------------
# Face Gui items
#---------------------------------------------------------------------------------------------------

        # facing DROs, list order sets focus passing order, wraps at end
        self.face_dro_list = (
            'face_tool_num_dro',
            'face_z_end_dro',
            'face_stock_dia_dro',
            'face_x_end_dro',
            'face_z_start_dro',
            'face_tc_dro',
            'face_rough_doc_dro',
            'face_finish_doc_dro',)

        self.face_focus_list = self.face_dro_list

        self.face_dro_list = dict(((i, self.builder.get_object(i))) for i in self.face_dro_list)
        self.create_page_DRO_attributes(page_id='id_turn_fixed',common=self.conv_dro_list,spec=self.face_dro_list,tool=self.face_dro_list['face_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.face_dro_list['face_rough_doc_dro'],f_doc=self.face_dro_list['face_finish_doc_dro'],
                                        diameter=self.face_dro_list['face_stock_dia_dro'],z_start=self.face_dro_list['face_z_start_dro'],
                                        z_end=self.face_dro_list['face_z_end_dro'])
        for name, dro in self.face_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        # chamfering DROs, list order sets focus passing order, wraps at end
        self.corner_chamfer_od_focus_list = [
            'corner_chamfer_od_tool_num_dro',
            'corner_chamfer_od_z_start_dro',
            'corner_chamfer_od_z_end_dro',
            'corner_chamfer_od_od_dro',
            'corner_chamfer_od_angle_dro',
            'corner_chamfer_od_rough_doc_dro',
            'corner_chamfer_od_finish_doc_dro',
            'corner_chamfer_od_tc_dro']

        self.corner_chamfer_od_dro_list = self.corner_chamfer_od_focus_list

        self.corner_chamfer_od_dro_list = dict(((i, self.builder.get_object(i))) for i in self.corner_chamfer_od_dro_list)
        self.create_page_DRO_attributes(page_id='chamfer_fixed',common=self.conv_dro_list,spec=self.corner_chamfer_od_dro_list,tool=self.corner_chamfer_od_dro_list['corner_chamfer_od_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.corner_chamfer_od_dro_list['corner_chamfer_od_rough_doc_dro'],f_doc=self.corner_chamfer_od_dro_list['corner_chamfer_od_finish_doc_dro'],
                                        diameter=self.corner_chamfer_od_dro_list['corner_chamfer_od_od_dro'],z_start=self.corner_chamfer_od_dro_list['corner_chamfer_od_z_start_dro'],
                                        z_end=self.corner_chamfer_od_dro_list['corner_chamfer_od_z_end_dro'])
        for name, dro in self.corner_chamfer_od_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        # Lables
        self.corner_od_x_label = self.builder.get_object('corner_od_x_text')
        self.corner_id_x_label = self.builder.get_object('corner_id_x_text')

        self.corner_chamfer_od_angle_label = self.builder.get_object('corner_chamfer_od_angle_text')
        self.corner_chamfer_od_rough_doc_label = self.builder.get_object('corner_chamfer_od_rough_doc_text')
        self.corner_chamfer_od_finish_doc_label = self.builder.get_object('corner_chamfer_od_finish_doc_text')
        self.corner_chamfer_od_tc_label = self.builder.get_object('corner_chamfer_od_tc_text')

        self.corner_chamfer_id_focus_list = [
            'corner_chamfer_id_tool_num_dro',
            'corner_chamfer_id_z_start_dro',
            'corner_chamfer_id_z_end_dro',
            'corner_chamfer_id_id_dro',
            'corner_chamfer_id_angle_dro',
            'corner_chamfer_id_rough_doc_dro',
            'corner_chamfer_id_finish_doc_dro',
            'corner_chamfer_id_tc_dro']

        self.corner_chamfer_id_dro_list = self.corner_chamfer_id_focus_list

        self.corner_chamfer_id_dro_list = dict(((i, self.builder.get_object(i))) for i in self.corner_chamfer_id_dro_list)
        self.create_page_DRO_attributes(page_id='chamfer_fixed',attr='chamfer_id_dros',common=self.conv_dro_list,spec=self.corner_chamfer_id_dro_list,tool=self.corner_chamfer_id_dro_list['corner_chamfer_id_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.corner_chamfer_id_dro_list['corner_chamfer_id_rough_doc_dro'],f_doc=self.corner_chamfer_id_dro_list['corner_chamfer_id_finish_doc_dro'],
                                        diameter=self.corner_chamfer_id_dro_list['corner_chamfer_id_id_dro'],z_start=self.corner_chamfer_id_dro_list['corner_chamfer_id_z_start_dro'],
                                        z_end=self.corner_chamfer_id_dro_list['corner_chamfer_id_z_end_dro'])

        for name, dro in self.corner_chamfer_id_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.corner_chamfer_id_angle_label = self.builder.get_object('corner_chamfer_id_angle_text')
        self.corner_chamfer_id_rough_doc_label = self.builder.get_object('corner_chamfer_id_rough_doc_text')
        self.corner_chamfer_id_finish_doc_label = self.builder.get_object('corner_chamfer_id_finish_doc_text')
        self.corner_chamfer_id_tc_label = self.builder.get_object('corner_chamfer_id_tc_text')

        # Corner Radius DROs, list order sets focus passing order, wraps at end
        self.corner_radius_od_focus_list = [
            'corner_radius_od_tool_num_dro',
            'corner_radius_od_z_start_dro',
            'corner_radius_od_z_end_dro',
            'corner_radius_od_od_dro',
            'corner_radius_od_rough_doc_dro',
            'corner_radius_od_finish_doc_dro',
            'corner_radius_od_tc_dro']

        self.corner_radius_od_dro_list = self.corner_radius_od_focus_list

        self.corner_radius_od_dro_list = dict(((i, self.builder.get_object(i))) for i in self.corner_radius_od_dro_list)
        self.create_page_DRO_attributes(page_id='chamfer_fixed',attr='radius_od_dros',common=self.conv_dro_list,spec=self.corner_radius_od_dro_list,tool=self.corner_radius_od_dro_list['corner_radius_od_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.corner_radius_od_dro_list['corner_radius_od_rough_doc_dro'],f_doc=self.corner_radius_od_dro_list['corner_radius_od_finish_doc_dro'],
                                        diameter=self.corner_radius_od_dro_list['corner_radius_od_od_dro'],z_start=self.corner_radius_od_dro_list['corner_radius_od_z_start_dro'],
                                        z_end=self.corner_radius_od_dro_list['corner_radius_od_z_end_dro'])
        for name, dro in self.corner_radius_od_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.corner_radius_od_rough_doc_label = self.builder.get_object('corner_radius_od_rough_doc_text')
        self.corner_radius_od_finish_doc_label = self.builder.get_object('corner_radius_od_finish_doc_text')
        self.corner_radius_od_tc_label = self.builder.get_object('corner_radius_od_tc_text')

        self.corner_radius_id_focus_list = [
            'corner_radius_id_tool_num_dro',
            'corner_radius_id_z_start_dro',
            'corner_radius_id_z_end_dro',
            'corner_radius_id_id_dro',
            'corner_radius_id_rough_doc_dro',
            'corner_radius_id_finish_doc_dro',
            'corner_radius_id_tc_dro']

        self.corner_radius_id_dro_list = self.corner_radius_id_focus_list

        self.corner_radius_id_dro_list = dict(((i, self.builder.get_object(i))) for i in self.corner_radius_id_dro_list)
        self.create_page_DRO_attributes(page_id='chamfer_fixed',attr='radius_id_dros',common=self.conv_dro_list,spec=self.corner_radius_id_dro_list,tool=self.corner_radius_id_dro_list['corner_radius_id_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.corner_radius_id_dro_list['corner_radius_id_rough_doc_dro'],f_doc=self.corner_radius_id_dro_list['corner_radius_id_finish_doc_dro'],
                                        diameter=self.corner_radius_id_dro_list['corner_radius_id_id_dro'],z_start=self.corner_radius_id_dro_list['corner_radius_id_z_start_dro'],
                                        z_end=self.corner_radius_id_dro_list['corner_radius_id_z_end_dro'])

        for name, dro in self.corner_radius_id_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.corner_radius_id_rough_doc_label = self.builder.get_object('corner_radius_id_rough_doc_text')
        self.corner_radius_id_finish_doc_label = self.builder.get_object('corner_radius_id_finish_doc_text')
        self.corner_radius_id_tc_label = self.builder.get_object('corner_radius_id_tc_text')

        # Groove DROs and labels, list order sets focus passing order, wraps at end
        self.groove_dro_list = (
            'groove_tool_num_dro',
            'groove_tw_dro',
            'groove_stock_dia_dro',
            'groove_final_dia_dro',
            'groove_z_start_dro',
            'groove_z_end_dro',
            'groove_rough_doc_dro',
            'groove_finish_doc_dro',
            'groove_tc_dro' )

        self.groove_focus_list = self.groove_dro_list

        self.groove_dro_list = dict(((i, self.builder.get_object(i))) for i in self.groove_dro_list)
        self.create_page_DRO_attributes(page_id='groove_part_fixed',common=self.conv_dro_list,spec=self.groove_dro_list,tool=self.groove_dro_list['groove_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        r_doc=self.groove_dro_list['groove_rough_doc_dro'],f_doc=self.groove_dro_list['groove_finish_doc_dro'],
                                        diameter=self.groove_dro_list['groove_stock_dia_dro'],z_start=self.groove_dro_list['groove_z_start_dro'],
                                        z_end=self.groove_dro_list['groove_z_end_dro'])
        for name, dro in self.groove_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.groove_z_end_label = self.builder.get_object('groove_z_end_text')
        self.groove_r_doc_label = self.builder.get_object('groove_rough_doc_text')
        self.groove_f_doc_label = self.builder.get_object('groove_finish_doc_text')
        self.groove_tw_label    = self.builder.get_object('groove_tool_width_text')


        # Part DROs and labels, list order sets focus passing order, wraps at end
        self.part_dro_list = (
            'part_tool_num_dro',
            'part_tw_dro',
            'part_stock_dia_dro',
            'part_final_dia_dro',
            'part_z_start_dro',
            'part_peck_dro',
            'part_retract_dro',
            'part_tc_dro',
            'part_ebw_dro')

        self.part_focus_list = self.part_dro_list

        self.part_dro_list = dict(((i, self.builder.get_object(i))) for i in self.part_dro_list)
        self.create_page_DRO_attributes(page_id='groove_part_fixed',attr='part_dros',common=self.conv_dro_list,spec=self.part_dro_list,tool=self.part_dro_list['part_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        diameter=self.part_dro_list['part_stock_dia_dro'],peck=self.part_dro_list['part_peck_dro'],
                                        retract=self.part_dro_list['part_retract_dro'])
        for name, dro in self.part_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.part_peck_label       = self.builder.get_object('part_peck_text')
        self.part_retract_label    = self.builder.get_object('part_retract_text')
        self.part_ebw_label       = self.builder.get_object('part_ebw_text')
        self.part_tw_label    = self.builder.get_object('part_tool_width_text')

        # Drill DRO's and labels, list order sets focus passing order, wraps at end
        self.drill_dro_list = (
            'drill_tool_num_dro',
            'drill_z_start_dro',
            'drill_tc_dro',
            'drill_peck_dro',
            'drill_z_end_dro',
            'drill_spindle_rpm_dro',
            'drill_dwell_dro')

        self.drill_focus_list = self.drill_dro_list

        self.drill_dro_list = dict(((i, self.builder.get_object(i))) for i in self.drill_dro_list)
        self.create_page_DRO_attributes(page_id='drill_tap_fixed',common=self.conv_dro_list,spec=self.drill_dro_list,tool=self.drill_dro_list['drill_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.drill_dro_list['drill_spindle_rpm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        peck=self.drill_dro_list['drill_peck_dro'],z_start=self.drill_dro_list['drill_z_start_dro'],z_end=self.drill_dro_list['drill_z_end_dro'])
        for name, dro in self.drill_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.drill_through_hole_hint_label = self.builder.get_object('drill_through_hole_hint_text')

        self.drill_hole_depth_label = self.builder.get_object('drill_hole_depth_text')
        self.drill_peck_depth_label = self.builder.get_object('drill_peck_depth_text')
        self.drill_dwell_label      = self.builder.get_object('drill_dwell_text')
        self.drill_z_end_label      = self.builder.get_object('drill_z_end_text')
        self.chip_load_hint         = self.builder.get_object('chip_load_hint')

        # Tap DRO's and labels, list order sets focus passing order, wraps at end
        self.tap_dro_list = (
            'tap_tool_num_dro',
            'tap_z_start_dro',
            'tap_peck_dro',
            'tap_tc_dro',
            'tap_z_end_dro',
            'tap_spindle_rpm_dro',
            'tap_tpu_dro',
            'tap_pitch_dro')

        self.tap_focus_list = self.tap_dro_list

        self.tap_dro_list = dict(((i, self.builder.get_object(i))) for i in self.tap_dro_list)
        self.create_page_DRO_attributes(page_id='drill_tap_fixed',attr='tap_dros',common=self.conv_dro_list,spec=self.tap_dro_list,tool=self.tap_dro_list['tap_tool_num_dro'],
                                        rpm=self.conv_dro_list['conv_max_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.tap_dro_list['tap_spindle_rpm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        peck=self.tap_dro_list['tap_peck_dro'],z_start=self.tap_dro_list['tap_z_start_dro'],z_end=self.tap_dro_list['tap_z_end_dro'])
        for name, dro in self.tap_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.tap_thread_depth_label = self.builder.get_object("tap_thread_depth_text")
        self.tap_tpu_label          = self.builder.get_object("tap_tpu_text")
        self.tap_pitch_label        = self.builder.get_object("tap_pitch_text")
        self.tap_z_end_label        = self.builder.get_object("tap_z_end_text")

        # Thread DRO's and labels
        self.thread_dro_list = (
            'thread_tool_num_dro',
            'thread_z_start_dro',
            'thread_z_end_dro',
            'thread_tc_dro',
            'thread_major_dia_dro',
            'thread_minor_dia_dro',
            'thread_lead_dro',
            'thread_spindle_rpm_dro',
            'thread_tpu_dro',
            'thread_doc_dro',
            'thread_pitch_dro',
            'thread_pass_dro',
            'thread_taper_dro')

        # self.thread_focus_list = self.thread_dro_list

        # The following list order sets focus passing order, wraps at end.
        # Normally the DRO list would set order but not all DROs are passed to.
        self.thread_focus_list = (
            'thread_tool_num_dro',
            'thread_z_start_dro',
            'thread_z_end_dro',
            'thread_taper_dro',
            'thread_tc_dro',
            'thread_major_dia_dro',
            'thread_minor_dia_dro',
            'thread_lead_dro',
            'thread_spindle_rpm_dro',
            'thread_tpu_dro',
            'thread_pass_dro')

        self.thread_dro_list = dict(((i, self.builder.get_object(i))) for i in self.thread_dro_list)
        self.create_page_DRO_attributes(page_id='thread_fixed',common=self.conv_dro_list,spec=self.thread_dro_list,tool=self.thread_dro_list['thread_tool_num_dro'],
                                        rpm=self.thread_dro_list['thread_spindle_rpm_dro'],r_feed=self.conv_dro_list['conv_rough_fpr_dro'],f_feed=self.conv_dro_list['conv_finish_fpr_dro'],
                                        r_sfm=self.conv_dro_list['conv_rough_sfm_dro'],f_sfm=self.conv_dro_list['conv_finish_sfm_dro'],
                                        diameter=self.thread_dro_list['thread_major_dia_dro'],passes=self.thread_dro_list['thread_pass_dro'],
                                        z_start=self.thread_dro_list['thread_z_start_dro'],z_end=self.thread_dro_list['thread_z_end_dro'])
        for name, dro in self.thread_dro_list.iteritems():
            dro.modify_font(self.conv_dro_font_description)

        self.thread_major_dia_label = self.builder.get_object('thread_major_dia_text')
        self.thread_minor_dia_label = self.builder.get_object('thread_minor_dia_text')
        self.conv_thread_calc_label = self.builder.get_object('thread_calc_text')
        self.conv_thread_pitch_label = self.builder.get_object('thread_pitch_text')
        self.thread_chart_notes_label = self.builder.get_object('thread_chart_notes_text')

        self.thread_chart_combobox = self.builder.get_object('thread_chart')
        self.thread_chart_g20_liststore = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.thread_chart_combobox.set_model(self.thread_chart_g20_liststore)

        self.pipe_label1 = self.builder.get_object('pipe_label1')
        self.pipe_label2 = self.builder.get_object('pipe_label2')
        self.pipe_label3 = self.builder.get_object('pipe_label3')
        self.pipe_label4 = self.builder.get_object('pipe_label4')
        self.pipe_label5 = self.builder.get_object('pipe_label5')
        self.pipe_label6 = self.builder.get_object('pipe_label6')

        cell = gtk.CellRendererText()
        self.thread_chart_combobox.pack_start(cell, True)
        self.thread_chart_combobox.add_attribute(cell, 'text', 0)
        cellview = self.thread_chart_combobox.get_child()
        cellview.set_displayed_row(0)

        self.thread_chart_g20_liststore = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        self.thread_chart_g21_liststore = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)

        self.refresh_thread_data_liststores()


#---------------------------------------------------------------------------------------------------
# Tool DROs
#---------------------------------------------------------------------------------------------------
        self.tool_dros = dict(
                          odturn = self.od_turn_dro_list['od_turn_tool_num_dro'],
                          idturn = dict( basic=self.id_basic_dro_list['id_basic_tool_num_dro'],extended = self.id_turn_dro_list['id_turn_tool_num_dro']),
                          profile = self.profile_dro_list['profile_tool_num_dro'],
                          face = self.face_dro_list['face_tool_num_dro'],
                          chamfer = dict( chamfer = dict( od= self.corner_chamfer_od_dro_list['corner_chamfer_od_tool_num_dro'], id = self.corner_chamfer_id_dro_list['corner_chamfer_id_tool_num_dro']),
                                           radius = dict( od = self.corner_radius_od_dro_list['corner_radius_od_tool_num_dro'], id = self.corner_radius_id_dro_list['corner_radius_id_tool_num_dro']) ),
                          groove_part = dict( groove = self.groove_dro_list['groove_tool_num_dro'], part = self.part_dro_list['part_tool_num_dro']),
                          drill_tap = dict( drill = self.drill_dro_list['drill_tool_num_dro'], tap = self.tap_dro_list['tap_tool_num_dro']),
                          thread = self.thread_dro_list['thread_tool_num_dro']
                         )



#---------------------------------------------------------------------------------------------------
# Labels (gtk.label)
#---------------------------------------------------------------------------------------------------

        self.get_version_string()


        # dtg labels
        self.x_dtg_label = self.builder.get_object('x_dtg_label')
        self.z_dtg_label = self.builder.get_object('z_dtg_label')
        self.x_dtg_label.modify_font(self.conv_dro_font_description)
        self.z_dtg_label.modify_font(self.conv_dro_font_description)

        # /min, /rev, RPM, and FPM labels
        self.f_per_min_label = self.builder.get_object('f_per_min_text')
        self.f_per_rev_label = self.builder.get_object('f_per_rev_text')
        self.rpm_label = self.builder.get_object('rpm_text')
        self.css_label = self.builder.get_object('css_text')

        # tool label for active tool, manual tool change requests
        self.tool_label = self.builder.get_object('tool_label')
        self.tool_label.modify_font(pango.FontDescription('Bebas ultra-condensed 18'))
        self.tool_label.set_text('T:    00')

        # tool touch labels
        self.ftp_text = self.builder.get_object('ftp_text')
        self.rtp_text = self.builder.get_object('rtp_text')


        self.setup_filechooser()

        self.setup_gcode_marks()

        # -----------------------------------------
        # jogging - keyboard and shuttlexpress
        # -----------------------------------------

        self.hal['jog-gui-step-index'] = 0

        # set jog speed
        ini_jog_speed = (
            self.inifile.find("DISPLAY", "DEFAULT_LINEAR_VELOCITY")
            or self.inifile.find("TRAJ", "DEFAULT_LINEAR_VELOCITY")
            or self.inifile.find("TRAJ", "DEFAULT_VELOCITY")
            or 1.0)
        self.jog_speed = (float(ini_jog_speed))
        self.jog_speeds = dict((ind,float(self.inifile.find("AXIS_%d" % ind,"MAX_VELOCITY"))) for ind in [0, 2])
        if self.machineconfig.in_rapidturn_mode():
            # rapid turn has Y axis
            self.jog_speeds[1] = float(self.inifile.find("AXIS_1", "MAX_VELOCITY"))

        # set jog speed percentage
        if not self.redis.hexists('machine_prefs', 'jog_override_percentage'):
            self.redis.hset('machine_prefs', 'jog_override_percentage', 0.4)
        self.jog_override_pct = float(self.redis.hget('machine_prefs', 'jog_override_percentage'))

        # default to continuous jog mode
        self.jog_mode = linuxcnc.JOG_CONTINUOUS
        self.keyboard_jog_mode = linuxcnc.JOG_CONTINUOUS
        # initial jog percent to 40
        self.jog_speed_adjustment.set_value(self.jog_override_pct * 100)

        # keyboard jogging
        self.window.connect("key_press_event", self.on_key_press_or_release)
        self.window.connect("key_release_event", self.on_key_press_or_release)

        # mode/state tracking (debug only)
        self.prev_lcnc_task_mode = -1
        self.prev_lcnc_interp_state = -1
        self.prev_task_state = -1

        # --------------------------------------------------
        # restore saved machine settings/prefs (Redis)
        # --------------------------------------------------


        # axis scale factors
        for axis_letter in ['x', 'y', 'z']:
            redis_key = '%s_axis_scale_factor' % axis_letter
            if self.redis.hexists('machine_prefs', redis_key):
                axis_scale_factor = float(self.redis.hget('machine_prefs', redis_key))
                self.error_handler.write("Found %s axis scale factor %f in settings" % (axis_letter.upper(), axis_scale_factor), ALARM_LEVEL_DEBUG)
                self._set_axis_scale(axis_letter, axis_scale_factor)
            else:
                self.error_handler.write("No %s axis scale factor stored in redis. This is not an error." % axis_letter.upper(), ALARM_LEVEL_DEBUG)

        # axis backlash
        for axis_letter in ['x', 'y', 'z']:
            redis_key = '%s_axis_backlash' % axis_letter
            if self.redis.hexists('machine_prefs', redis_key):
                axis_backlash = float(self.redis.hget('machine_prefs', redis_key))
                self.error_handler.write("Found %s axis backlash %f in settings" % (axis_letter.upper(), axis_backlash), ALARM_LEVEL_DEBUG)
                self._set_axis_backlash(axis_letter, axis_backlash)
            else:
                self.error_handler.write("No %s axis backlash stored in redis. This is not an error." % axis_letter.upper(), ALARM_LEVEL_DEBUG)

        # cleanup redis from the old setting "disable keyboard jogging"
        # PP-1488 decided to remove the setting
        self.redis.hdel('machine_prefs', 'keyboard_jogging_disabled')

        self.set_home_switches()

        self.settings.configure_g30_settings()

        # restore last used values on conversational screens
        self.restore_conv_parameters()

        # -----------------------------------------
        # tool table init (gtk.treeview)
        # -----------------------------------------

        # tool types stored in front angle value of geo offset register
        self.tool_type_dic = {'rtp_profile': 1, 'rtp_lh_turn': 2, 'rtp_turn': 3, 'rtp_thread': 4,
                              'rtp_part': 5, 'rtp_boring_bar': 6, 'rtp_id_thread': 7, 'center_drill':8,
                              'rtp_lh_profile':9, 'rtp_rh_profile':10,
                              'ftp_profile': -1,
                              'ftp_lh_turn': -2, 'ftp_turn': -3, 'ftp_thread': -4, 'ftp_part': -5,
                              'ftp_boring_bar': -6, 'ftp_id_thread': -7,'ftp_lh_profile':-9,
                              'ftp_rh_profile':-10,'none': 0}

        # geometry defs for tool_types
        self.front_angle_dic = {'rtp_profile': -107.5, 'rtp_lh_turn': -95, 'rtp_turn': -85, 'rtp_thread': -120,
                                'rtp_part': -90, 'rtp_boring_bar': 5, 'rtp_id_thread': 60, 'center_drill':-15,
                                'rtp_lh_profile':-93, 'rtp_rh_profile':-87,
                                'ftp_profile': 107.5, 'ftp_lh_turn': 175, 'ftp_turn': 5, 'ftp_thread': 60, 'ftp_part': 90,
                                'ftp_boring_bar': -85, 'ftp_id_thread': -120,'ftp_lh_profile':93,
                                'ftp_rh_profile':87, 'none': 0}

        self.back_angle_dic = {'rtp_profile': -72.5, 'rtp_lh_turn': -175, 'rtp_turn': -5, 'rtp_thread': -60,
                               'rtp_part': -90, 'rtp_boring_bar': 85, 'rtp_id_thread': 120, 'center_drill':15,
                               'rtp_lh_profile':-128, 'rtp_rh_profile':-52,
                               'ftp_profile': 72.5, 'ftp_lh_turn': 95, 'ftp_turn': 85, 'ftp_thread': 120, 'ftp_part': 90,
                               'ftp_boring_bar': -5, 'ftp_id_thread': -60, 'ftp_lh_profile':128,
                               'ftp_rh_profile':52,'none': 0}

        self.orientation_dic = {'rtp_profile': 6, 'rtp_lh_turn': 1, 'rtp_turn': 2, 'rtp_thread': 6,
                                'rtp_part': 2, 'rtp_boring_bar': 3, 'rtp_id_thread': 8, 'center_drill':7,
                                'rtp_lh_profile':1, 'rtp_rh_profile':2,
                                'ftp_profile': 8, 'ftp_lh_turn': 4, 'ftp_turn': 3, 'ftp_thread': 8, 'ftp_part': 3,
                                'ftp_boring_bar': 2, 'ftp_id_thread': 6,
                                'ftp_lh_profile':4, 'ftp_rh_profile':3, 'none': 9}

        if self.is_front_toolpost_lathe:
            self.orientation_dic = {'rtp_profile': 8, 'rtp_lh_turn': 4, 'rtp_turn': 3, 'rtp_thread': 8,
                                    'rtp_part': 4, 'rtp_boring_bar': 2, 'rtp_id_thread': 8, 'center_drill':7,
                                    'rtp_lh_profile':4, 'rtp_rh_profile':3,
                                    'ftp_profile': 6, 'ftp_lh_turn': 1, 'ftp_turn': 2, 'ftp_thread': 6, 'ftp_part': 1,
                                    'ftp_boring_bar': 3, 'ftp_id_thread': 8,
                                    'ftp_lh_profile':1, 'ftp_rh_profile':2, 'none': 9}

        # using a treeview/liststore for the tool table, on the tools page of the notebook


        # final element of a row is the color to be used as the background for the tool column number as a string
        self.tool_liststore = gtk.ListStore(int, str, str, str, str, str, str, str, int, str, str, str)

        tool_table_filename = self.inifile.find("EMCIO", "TOOL_TABLE") or ""
        if tool_table_filename == "":
            tool_table_filename = "tool.tbl"
        self.refresh_tool_liststore()

        tool_font = pango.FontDescription('Roboto Condensed 10')

        # Create a TreeView and let it know about the model we created above
        self.tool_treeview = gtk.TreeView(self.tool_liststore)
        self.treeselection = self.tool_treeview.get_selection()
        self.treeselection.set_mode(gtk.SELECTION_SINGLE)

        # create columns
        self.tool_num_column =         gtk.TreeViewColumn('Tool')
        self.tool_description_column = gtk.TreeViewColumn('Description')
        self.x_geo_offset_column =     gtk.TreeViewColumn('X')
        self.y_geo_offset_column =     gtk.TreeViewColumn('Y')
        self.z_geo_offset_column =     gtk.TreeViewColumn('Z')
        self.x_wear_offset_column =    gtk.TreeViewColumn('X Wear')
        self.z_wear_offset_column =    gtk.TreeViewColumn('Z Wear')
        self.tool_nose_rad_column =    gtk.TreeViewColumn('Nose R')
        self.tool_tip_orient_column =  gtk.TreeViewColumn('Tip')

        # add columns to treeview
        self.tool_treeview.append_column(self.tool_num_column)
        self.tool_treeview.append_column(self.tool_description_column)
        self.tool_treeview.append_column(self.x_geo_offset_column)
        self.tool_treeview.append_column(self.y_geo_offset_column)
        self.tool_treeview.append_column(self.z_geo_offset_column)
        self.tool_treeview.append_column(self.x_wear_offset_column)
        self.tool_treeview.append_column(self.z_wear_offset_column)
        self.tool_treeview.append_column(self.tool_nose_rad_column)
        self.tool_treeview.append_column(self.tool_tip_orient_column)

        tool_col_renderer = gtk.CellRendererText()
        tool_col_renderer.set_property('editable', True)
        tool_col_renderer.set_property('font-desc', tool_font)

        self.tool_num_column.pack_start(tool_col_renderer, True)
        # we have the tool number column use the 11th element of the tool liststore as the value for the background property
        self.tool_num_column.set_attributes(tool_col_renderer, text=0, cell_background=11)

        tool_description_renderer = gtk.CellRendererText()
        tool_description_renderer.set_property('editable', True)
        tool_description_renderer.set_property('cell-background', '#B3E1D7')
        tool_description_renderer.set_property('font-desc', tool_font)
        self.tool_description_column.pack_start(tool_description_renderer, True)
        self.tool_description_column.set_attributes(tool_description_renderer, text=1)
        self.tool_description_column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        if self.machineconfig.in_rapidturn_mode():
            self.tool_description_column.set_fixed_width(250)  #Y Offset changed from above to fit Y column
        else:
            self.tool_description_column.set_fixed_width(self.fs_mgr.tool_column_width())
        tool_description_renderer.connect('edited', self.on_tool_description_column_edited, self.tool_liststore)

        x_geo_offset_renderer = gtk.CellRendererText()
        x_geo_offset_renderer.set_property('editable', True)
        x_geo_offset_renderer.set_property('cell-background', '#D5E1B3')
        x_geo_offset_renderer.set_property('font-desc', tool_font)
        self.x_geo_offset_column.pack_start(x_geo_offset_renderer, True)
        self.x_geo_offset_column.set_attributes(x_geo_offset_renderer, text=2)
        x_geo_offset_renderer.connect('edited', self.on_x_geo_offset_col_edited, self.tool_liststore)
        x_geo_offset_renderer.connect('editing-started', self.on_x_geo_offset_col_editing_started)

        # RapidTurn Y offset
        y_geo_offset_renderer = gtk.CellRendererText()
        y_geo_offset_renderer.set_property('editable', True)
        y_geo_offset_renderer.set_property('cell-background', '#D5E1B3')
        y_geo_offset_renderer.set_property('font-desc', tool_font)
        self.y_geo_offset_column.pack_start(y_geo_offset_renderer, True)
        self.y_geo_offset_column.set_attributes(y_geo_offset_renderer, text=3)
        y_geo_offset_renderer.connect('edited', self.on_y_geo_offset_col_edited, self.tool_liststore)
        y_geo_offset_renderer.connect('editing-started', self.on_y_geo_offset_col_editing_started)
        if not self.machineconfig.in_rapidturn_mode():
            self.y_geo_offset_column.set_visible(False)

        z_geo_offset_renderer = gtk.CellRendererText()
        z_geo_offset_renderer.set_property('editable', True)
        z_geo_offset_renderer.set_property('cell-background', '#D6D76C')
        z_geo_offset_renderer.set_property('font-desc', tool_font)
        self.z_geo_offset_column.pack_start(z_geo_offset_renderer, True)
        self.z_geo_offset_column.set_attributes(z_geo_offset_renderer, text=4)
        z_geo_offset_renderer.connect('edited', self.on_z_geo_offset_col_edited, self.tool_liststore)
        z_geo_offset_renderer.connect('editing-started', self.on_z_geo_offset_col_editing_started)

        x_wear_offset_renderer = gtk.CellRendererText()
        x_wear_offset_renderer.set_property('editable', True)
        x_wear_offset_renderer.set_property('cell-background', '#D5E1B3')
        x_wear_offset_renderer.set_property('font-desc', tool_font)
        self.x_wear_offset_column.pack_start(x_wear_offset_renderer, True)
        self.x_wear_offset_column.set_attributes(x_wear_offset_renderer, text=5, foreground = 9)
        x_wear_offset_renderer.connect('edited', self.on_x_offset_col_edited, self.tool_liststore)
        x_wear_offset_renderer.connect('editing-started', self.on_x_offset_col_editing_started)

        z_wear_offset_renderer = gtk.CellRendererText()
        z_wear_offset_renderer.set_property('editable', True)
        z_wear_offset_renderer.set_property('cell-background', '#D6D76C')
        z_wear_offset_renderer.set_property('font-desc', tool_font)
        self.z_wear_offset_column.pack_start(z_wear_offset_renderer, True)
        self.z_wear_offset_column.set_attributes(z_wear_offset_renderer, text=6, foreground = 10)
        z_wear_offset_renderer.connect('edited', self.on_z_offset_col_edited, self.tool_liststore)
        z_wear_offset_renderer.connect('editing-started', self.on_z_offset_col_editing_started)

        nose_radius_col_renderer = gtk.CellRendererText()
        nose_radius_col_renderer.set_property('editable', True)
        nose_radius_col_renderer.set_property('cell-background', '#B3E1D7')
        nose_radius_col_renderer.set_property('font-desc', tool_font)
        self.tool_nose_rad_column.pack_start(nose_radius_col_renderer, True)
        self.tool_nose_rad_column.set_attributes(nose_radius_col_renderer, text=7)
        nose_radius_col_renderer.connect('edited', self.on_nose_radius_col_edited, self.tool_liststore)
        nose_radius_col_renderer.connect('editing-started', self.on_nose_radius_col_editing_started)

        tip_orient_renderer = gtk.CellRendererText()
        tip_orient_renderer.set_property('editable', True)
        tip_orient_renderer.set_property('cell-background', '#E1D5B3')
        tip_orient_renderer.set_property('font-desc', tool_font)
        self.tool_tip_orient_column.pack_start(tip_orient_renderer, True)
        self.tool_tip_orient_column.set_attributes(tip_orient_renderer, text=8)
        tip_orient_renderer.connect('edited', self.on_tip_orient_col_edited, self.tool_liststore)
        tip_orient_renderer.connect('editing-started', self.on_tip_orient_col_editing_started)


        # show in notebook

        # create a scrolled window to hold the treeview
        self.scrolled_window_tool_table = gtk.ScrolledWindow()
        self.scrolled_window_tool_table.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)

        self.tool_offsets_fixed.put(self.scrolled_window_tool_table, 10, 7)
        self.scrolled_window_tool_table.add(self.tool_treeview)
        self.scrolled_window_tool_table.set_size_request(655, 357)
        self.tool_descript_entry = ToolDescriptorEntry(self,MAX_LATHE_TOOL_NUM, self.fs_mgr.tool_description_parse_data())
        self.key_mask[type(self.tool_descript_entry)] = self.tool_descript_keys
        self.tool_treeview.set_search_column(1)


        # -----------------------------------------
        # Work Offset table init (gtk.treeview)
        # -----------------------------------------
        work_font = tool_font

        # list store structure is always the same regardless of whether we are a lathe or a mill in rapidturn mode
        # with the extra y offset.  The store has all the fields and we just adjust the treeview columns to display
        # y or not depending on mode.
        self.work_liststore = gtk.ListStore(str, str, str, str, str, str, str)

        # Create a TreeView and let it know about the model we created above
        self.work_treeview = gtk.TreeView(self.work_liststore)

        work_id_column = gtk.TreeViewColumn('')
        work_id_label = gtk.Label('Work')
        work_id_label.modify_font(work_font)
        work_id_column.set_widget(work_id_label)
        work_id_label.show()

        work_x_column  = gtk.TreeViewColumn('')
        work_x_label = gtk.Label('X')
        work_x_label.modify_font(work_font)
        work_x_column.set_widget(work_x_label)
        work_x_label.show()

        if self.machineconfig.in_rapidturn_mode():
            work_y_column  = gtk.TreeViewColumn('')
            work_y_label = gtk.Label('Y')
            work_y_label.modify_font(work_font)
            work_y_column.set_widget(work_y_label)
            work_y_label.show()

        work_z_column  = gtk.TreeViewColumn('')
        work_z_label = gtk.Label('Z')
        work_z_label.modify_font(work_font)
        work_z_column.set_widget(work_z_label)
        work_z_label.show()

        self.work_treeview.append_column(work_id_column)
        self.work_treeview.append_column(work_x_column)
        if self.machineconfig.in_rapidturn_mode():
            self.work_treeview.append_column(work_y_column)
        self.work_treeview.append_column(work_z_column)

        self.work_treeview.set_rules_hint(True)

        total_width = 26 # vertical scrollbar fudge

        work_id_renderer = gtk.CellRendererText()
        work_id_renderer.set_property('editable', False)
        work_id_renderer.set_property('font-desc', work_font)
        work_id_renderer.set_property('cell-background', '#E1B3B7')
        work_id_renderer.set_property('width',70)
        work_id_column.pack_start(work_id_renderer, True)
        work_id_column.set_attributes(work_id_renderer, text=0)
        total_width += 70

        # in rapidturn mode we put the columns on a diet to make room for the extra Y column
        col_width = 105
        if self.machineconfig.in_rapidturn_mode():
            col_width = 70

        work_x_renderer = gtk.CellRendererText()
        work_x_renderer.set_property('editable', False)
        work_x_renderer.set_property('font-desc', work_font)
        work_x_renderer.set_property('xalign',0.8)
        work_x_renderer.set_property('width',col_width)
        work_x_column.pack_start(work_x_renderer, True)
        work_x_column.set_attributes(work_x_renderer, text=1, foreground=5, background=6)
        total_width += col_width

        if self.machineconfig.in_rapidturn_mode():
            work_x_renderer.set_property('width',70)
            work_y_renderer = gtk.CellRendererText()
            work_y_renderer.set_property('editable', False)
            work_y_renderer.set_property('font-desc', work_font)
            work_y_renderer.set_property('xalign',0.8)
            work_y_renderer.set_property('width',col_width)
            work_y_column.pack_start(work_y_renderer, True)
            work_y_column.set_attributes(work_y_renderer, text=2, foreground=5, background=6)
            total_width += col_width

        work_z_renderer = gtk.CellRendererText()
        work_z_renderer.set_property('editable', False)
        work_z_renderer.set_property('font-desc', work_font)
        work_z_renderer.set_property('xalign',0.8)
        work_z_renderer.set_property('width',col_width)
        work_z_column.pack_start(work_z_renderer, True)
        work_z_column.set_attributes(work_z_renderer, text=3, foreground=5, background=6)
        total_width += col_width

        self.refresh_work_offset_liststore()

        # show in notebook

        # create a scrolled window to hold the treeview
        scrolled_window_work_table = gtk.ScrolledWindow()
        scrolled_window_work_table.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)

        self.tool_offsets_fixed.put(scrolled_window_work_table, 676, 7)
        # the treeview knows about scrolling so do NOT add it using add_with_viewport or you
        # break all inherent keyboard navigation.
        scrolled_window_work_table.add(self.work_treeview)

        print "                total_width=", total_width
        scrolled_window_work_table.set_size_request(total_width, 310)

        # holds path to currently loaded gcode file
        # slow periodic polls for changes and reloads if appropriate
        self.set_current_gcode_path('')

        self.axis_ref_queue = Queue.Queue()

        # display jog shuttle not detected if configured to do so
        if self.jog_shuttle_load_failure:
            self.error_handler.write("Warning - jog shuttle not detected!", ALARM_LEVEL_DEBUG)

        # numlock status
        self.numlock_on = True
        try:
            redis_response = self.redis.hget('machine_prefs', 'numlock_on')
            if redis_response == 'True' or redis_response == None:
                self.numlock_on = True
            else:
                self.numlock_on = False
        except:
            #self.error_handler.write("exception looking for 'machine_prefs', 'numlock_on' in redis, defaulting to True", ALARM_LEVEL_LOW)
            # write to redis to avoid future messages
            self.redis.hset('machine_prefs', 'numlock_on', 'True')
        #self.checkbutton_list['numlock_on'].set_active(self.numlock_on)
        #self.set_numlock(self.numlock_on)

        self.setup_key_sets()

        self.set_button_permitted_states()

        if self.machineconfig.in_rapidturn_mode():
            self.rapidturn_init()

        self.alt_keyboard_shortcuts = (
            (gtk.keysyms.r, self.button_list['cycle_start']),
            (gtk.keysyms.R, self.button_list['cycle_start']),
            (gtk.keysyms.s, self.button_list['stop']),
            (gtk.keysyms.S, self.button_list['stop']),
            (gtk.keysyms.f, self.button_list['coolant']),
            (gtk.keysyms.F, self.button_list['coolant'])
        )

        self.ctrl_keyboard_shortcuts = (
            #(gtk.keysyms.a, self.button_list['foo']),
            #(gtk.keysyms.b, self.button_list['bar']),
            #(gtk.keysyms.c, self.button_list['baz'])
        )

        # Always hide the USBIO interface until first run setup and Reset button are hit.
        self.hide_usbio_interface()

        self._update_size_of_gremlin()

        self.limit_switches_seen = 0          # bit flags where x = 1, y = 2, z = 4
        self.limit_switches_seen_time = 0

        self.window.show_all()

        # check for supported kernel version
        warning_msg = versioning.GetVersionMgr().get_kernel_mismatch_warning_msg()
        if warning_msg and not self.machineconfig.is_sim():
            self.error_handler.write(warning_msg, ALARM_LEVEL_MEDIUM)

        # do this once at init time manually to drive the proper appearance of the File tab
        self.usb_mount_unmount_event_callback()

        self.set_lathe_toolchange_type()

        self.set_lathe_spindle_range()

        self.setup_jog_stepping_images()

        # this takes awhile so only do this on debug runs when we are validating tool tip data on
        # startup (because some tooltips are dynamic and wire into methods created by the job assignment init)
        # NOTE: job_assignment is needed to resolve tooltip dynamic references...
        self.job_assignment = job_assignment.JAObj(ui=self)
        if __debug__:
            # expose problems with tool tip definitions right away
            tooltipmgr.TTMgr().validate_all_tooltips()

        self.error_handler.write("Lathe __init__ complete - tool in spindle is %d" % self.status.tool_in_spindle, ALARM_LEVEL_DEBUG)


    def gcode_status_codes(self):
        return self.__class__._report_status


    # call optional UI hook function
    def call_ui_hook(self, method_name):
        if hasattr(self.ui_hooks, method_name):
            method = getattr(self.ui_hooks, method_name)
            method()
        else:
            self.error_handler.write("optional ui_hooks.%s() not defined" % method_name, ALARM_LEVEL_DEBUG)


    def set_lathe_spindle_range(self):
        self.hal["spindle-range"] = self.settings.spindle_range

        if self.settings.spindle_range == 1:
            # 5C collet
            self.max_rpm = self.ini_float('SPINDLE', 'HI_RANGE_MAX', 0)
            self.min_rpm = self.ini_float('SPINDLE', 'HI_RANGE_MIN', 0)
            self.mach_data['motor_curve'] = self.mach_data_hi

        elif self.settings.spindle_range == 0:
            # D1 chuck
            self.max_rpm = self.ini_float('SPINDLE', 'LO_RANGE_MAX', 0)
            self.min_rpm = self.ini_float('SPINDLE', 'LO_RANGE_MIN', 0)
            self.mach_data['motor_curve'] = self.mach_data_lo

        self.conversational.set_valid_spindle_rpm_range(self.min_rpm, self.max_rpm)
        ui_support.FSBase.update_spindle_range()


    def set_lathe_toolchange_type(self):
        self.hal['tool-changer-type'] = self.settings.tool_changer_type

        if self.settings.tool_changer_type == TOOL_CHANGER_TYPE_TURRET:
            self.button_list['turret_fwd'].show()
            self.button_list['turret_fwd'].set_sensitive(True)
        else:
            self.button_list['turret_fwd'].hide()
            self.button_list['turret_fwd'].set_sensitive(False)


    # This used to be called setup_hal_pins(), but is renamed to create_hal_pins().
    # It creates the "tormach" HAL pins.
    # See important note for set_hal_pin_defaults()
    def create_hal_pins(self):
        # --------------------------------------------------------
        # HAL setup.  Pins/signals must be connected in POSTGUI halfile
        # --------------------------------------------------------
        self.hal.newpin("coolant", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("coolant-iocontrol", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("jog-axis-x-enabled", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("jog-axis-y-enabled", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("jog-axis-a-enabled", hal.HAL_BIT, hal.HAL_IN)

        self.hal.newpin("jog-axis-z-enabled", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("jog-step-button", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("jog-counts", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("jog-ring-speed-signed", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("jog-ring-selected-axis", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("jog-gui-step-index", hal.HAL_U32, hal.HAL_OUT)
        self.hal.newpin("jog-gui-ustep-size", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-is-metric", hal.HAL_BIT, hal.HAL_OUT)

        self.hal.newpin("tool-changer-type", hal.HAL_S32, hal.HAL_OUT)
        self.hal.newpin("manual-tool-changed", hal.HAL_BIT, hal.HAL_IO)
        self.hal.newpin("tool-change", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("tool-prep-number", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("spindle-speed-out", hal.HAL_FLOAT, hal.HAL_IN)
        self.hal.newpin("spindle-range", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("spindle-range-alarm", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("spindle", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("spindle-iocontrol", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("spindle-disable", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("spindle-fault", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("door-switch", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("rapidturn-door-switch-enabled", hal.HAL_BIT, hal.HAL_OUT)

        self.hal.newpin("pp-estop-fault", hal.HAL_BIT, hal.HAL_OUT)

        # rapidturn enclosure door lock for M mills
        self.hal.newpin("enc-door-lock-drive", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("enc-door-locked-status", hal.HAL_BIT, hal.HAL_IN)

        self.hal.newpin("collet-closer-status", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("encoder-count", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("jog-ring-speed-1", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-2", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-3", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-4", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-5", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-6", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("jog-ring-speed-7", hal.HAL_FLOAT, hal.HAL_OUT)
        self.hal.newpin("mesa-watchdog-has-bit", hal.HAL_BIT, hal.HAL_IO)
        self.hal.newpin("cycle-time-hours", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("cycle-time-minutes", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("cycle-time-seconds", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("run-time-hours", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("run-time-minutes", hal.HAL_U32, hal.HAL_IN)
        self.hal.newpin("run-time-seconds", hal.HAL_U32, hal.HAL_IN)

        self.hal.newpin("motion-program-line", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("motion-next-program-line", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("motion-completed-program-line", hal.HAL_S32, hal.HAL_IN)
        self.hal.newpin("motion-motion-type", hal.HAL_S32, hal.HAL_IN)

        self.hal.newpin("turret-error", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("turret-positions", hal.HAL_U32, hal.HAL_IN)

        self.hal.newpin("encoder-z", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("encoder-a", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("encoder-b", hal.HAL_BIT, hal.HAL_IN)

        self.hal.newpin("machine-ok", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("home-switch", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("home-switch-enable", hal.HAL_BIT, hal.HAL_OUT)

        self.hal.newpin("probe-enable",  hal.HAL_BIT, hal.HAL_OUT)

        #atc pins:  not needed for lathe, but common code depends on it
        self.hal.newpin("atc-ngc-running", hal.HAL_BIT, hal.HAL_IN)

        #TODO: Pins needed for other axes
        self.hal.newpin("x-status-code", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("x-motor-command", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("x-motor-state", hal.HAL_S32, hal.HAL_IN)

# The "Y" motor exists in rapid turn, and generates faults for rapid turn postgui hal.
# if not present here.   No harm adding these pins for normal lathe, which really
# doesn't have a Y axis motor
        self.hal.newpin("y-status-code", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("y-motor-command", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("y-motor-state", hal.HAL_S32, hal.HAL_IN)

        self.hal.newpin("z-status-code", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("z-motor-command", hal.HAL_S32, hal.HAL_IO)
        self.hal.newpin("z-motor-state", hal.HAL_S32, hal.HAL_IN)

        # usbio board
        # usbio board pins for boards 0, 1, 2, 3 (if present)
        self.hal.newpin("usbio-enabled", hal.HAL_BIT, hal.HAL_OUT)
        self.hal.newpin("usbio-input-0", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-1", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-2", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-3", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-4", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-5", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-6", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-7", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-8", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-9", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-10", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-11", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-12", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-13", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-14", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-input-15", hal.HAL_BIT, hal.HAL_IN)

        self.hal.newpin("usbio-output-0", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-1", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-2", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-3", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-4", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-5", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-6", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-7", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-8", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-9", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-10", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-11", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-12", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-13", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-14", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-output-15", hal.HAL_BIT, hal.HAL_IN)

        # usbio status for all boards as a group
        self.hal.newpin("usbio-status",hal.HAL_S32, hal.HAL_IN)

        self.hal.newpin("usbio-board-0-present",hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-board-1-present",hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-board-2-present",hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("usbio-board-3-present",hal.HAL_BIT, hal.HAL_IN)


        # The manual collet closer pins lets the GUI express its desire to the
        # tormachcolletcontrol comp.
        # for the collet closer control
        self.hal.newpin("collet-closer-manual-output", hal.HAL_BIT, hal.HAL_OUT)
        # GUI pin for collet closer control when we aren't using the motion pin from the g-code interp
        self.hal.newpin("collet-closer-manual-request", hal.HAL_BIT, hal.HAL_OUT)

        # Pins to allow for monitoring of axis homing
        self.hal.newpin("axis-0-homing", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("axis-1-homing", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("axis-2-homing", hal.HAL_BIT, hal.HAL_IN)
        self.hal.newpin("axis-3-homing", hal.HAL_BIT, hal.HAL_IN)

        self.hal.ready()


    # This used to be part of create_hal_pins(), which used to be called setup_hal_pins() and was called before postgui HAL setup
    # The problem was that the postgui hal setup wiped anything set in setup_hal_pins() to zeros!  So we now call set_hal_pin_defaults
    # after postgui HAL so these setting actually stick.
    def set_hal_pin_defaults(self):

        self.hal["collet-closer-manual-output"] = 0
        self.hal["collet-closer-manual-request"] = 0

        # set for nothing, let redis set it later
        self.hal['tool-changer-type'] = TOOL_CHANGER_TYPE_GANG
        self.hal['manual-tool-changed'] = False

        # initial hal states:
        self.prev_coolant_iocontrol = self.hal['coolant'] = 0
        self.coolant_status = self.prev_coolant_status = 0
        self.coolant_lockout = COOLANT_LOCK_OUT_PERIOD

        self.prev_spindle_iocontrol = self.hal['spindle'] = 0

        self.hal['probe-enable'] = 0; #probe use on lathe is impossible, as input is input to a faux encoder

        self.x_jog_enabled = self.hal['jog-axis-x-enabled']
        self.prev_x_jog_enabled = not self.x_jog_enabled
        self.z_jog_enabled = self.hal['jog-axis-z-enabled']
        self.prev_z_jog_enabled = not self.z_jog_enabled
        if self.machineconfig.in_rapidturn_mode():
            self.y_jog_enabled = self.prev_y_jog_enabled = False


    def do_first_run_setup(self):
        if not self.first_run:
            return

        self.first_run = False

        # custom X/Y/Z soft limits
        self.ensure_mode(linuxcnc.MODE_MANUAL)
        if self.redis.hexists('machine_prefs', 'x_soft_limit'):
            limit = float(self.redis.hget('machine_prefs', 'x_soft_limit'))
            self.x_soft_limit = self.validate_and_adjust_soft_limit(0, limit)
            self.error_handler.write("setting X soft limit to: %f" % self.x_soft_limit, ALARM_LEVEL_DEBUG)
            self.set_axis_minmax_limit(0, self.x_soft_limit)
        else:
            self.error_handler.write("No X soft limit stored in redis, not setting.", ALARM_LEVEL_DEBUG)

        if self.redis.hexists('machine_prefs', 'y_soft_limit'):
            limit = float(self.redis.hget('machine_prefs', 'y_soft_limit'))
            self.y_soft_limit = self.validate_and_adjust_soft_limit(1, limit)
            self.error_handler.write("setting Y soft limit to: %f" % self.y_soft_limit, ALARM_LEVEL_DEBUG)
            self.set_axis_minmax_limit(1, self.y_soft_limit)
        else:
            self.error_handler.write("No Y soft limit stored in redis, not setting.", ALARM_LEVEL_DEBUG)

        if self.redis.hexists('machine_prefs', 'z_soft_limit'):
            limit = float(self.redis.hget('machine_prefs', 'z_soft_limit'))
            self.z_soft_limit = self.validate_and_adjust_soft_limit(2, limit)
            self.error_handler.write("setting Z soft limit to: %f" % self.z_soft_limit, ALARM_LEVEL_DEBUG)
            self.set_axis_minmax_limit(2, self.z_soft_limit)
        else:
            self.error_handler.write("No Z soft limit stored in redis, not setting.", ALARM_LEVEL_DEBUG)

        try:
            self.g21 = self.redis.hget('machine_prefs', 'g21') == "True"
            if self.g21 == True:
                self.issue_mdi("G21")
            tool_num = self.redis.hget('machine_prefs', 'active_tool')
            if (tool_num != '0') and (int(tool_num) <= MAX_LATHE_TOOL_NUM):
                # must wait for interp idle or issue_mdi() might fail from self.moving() being True
                # due to busy interp
                self.wait_interp_idle()
                self.issue_mdi('M61 Q' + tool_num)
                self.command.wait_complete()
                self.wait_interp_idle()
                self.issue_mdi('M61 Q' + tool_num)
                self.command.wait_complete()
                self.wait_interp_idle()
                # no need to offset by 10000 - LinuxCNC handles it
                self.issue_mdi('G43 H' + tool_num)
                self.command.wait_complete()
        except:
            self.error_handler.write("Redis failed to retrieve tool information!", ALARM_LEVEL_DEBUG)
            pass

        # Now that we are out of Reset for the first time, see what USBIO stuff we have.
        if self.settings.usbio_enabled:
            self.show_usbio_interface()
        else:
            self.hide_usbio_interface()


    def show_usbio_interface(self):
        TormachUIBase.show_usbio_interface(self)

        # the choices in the usbio_module_liststore are added by subclasses because the pin numbering
        # text is different for mills vs. lathes.
        self.usbio_module_liststore.clear()
        self.usbio_combobox_id_to_index.clear()

        if self.hal["usbio-board-0-present"]:
            self.usbio_module_liststore.append(['1  :  Pins P5 - P8'])
            self.usbio_combobox_id_to_index[0] = len(self.usbio_module_liststore)-1

        if self.hal["usbio-board-1-present"]:
            self.usbio_module_liststore.append(['2  :  Pins P9 - P12'])
            self.usbio_combobox_id_to_index[1] = len(self.usbio_module_liststore)-1

        if self.hal["usbio-board-2-present"]:
            self.usbio_module_liststore.append(['3  :  Pins P13 - P16'])
            self.usbio_combobox_id_to_index[2] = len(self.usbio_module_liststore)-1

        if self.hal["usbio-board-3-present"]:
            self.usbio_module_liststore.append(['4  :  Pins P17 - P20'])
            self.usbio_combobox_id_to_index[3] = len(self.usbio_module_liststore)-1

        # the board selected redis state is the board ID, not the index into the comboxbox.
        self.usbio_boardid_selected = 0   # default
        if self.redis.hexists('uistate', 'usbio_boardid_selected'):
            self.usbio_boardid_selected = int(self.redis.hget('uistate', 'usbio_boardid_selected'))

        if len(self.usbio_module_liststore) > 0:
            if self.usbio_boardid_selected in self.usbio_combobox_id_to_index:
                self.usbio_board_selector_combobox.set_active(self.usbio_combobox_id_to_index[self.usbio_boardid_selected])
            else:
                # boardid selected may have been stale in redis from previous time where different boards or switch settings
                # were found. Just slam it to the first available in the combobox. The combobox_changed signal handler will update
                # redis.
                self.usbio_board_selector_combobox.set_active(0)


    def set_button_permitted_states(self):
        # default is only can press the button when the machine is out of estop and at rest (referenced or not)
        for name, eventbox in self.button_list.iteritems():
            eventbox.permitted_states = STATE_IDLE | STATE_IDLE_AND_REFERENCED

        # TODO
        # define more permissive states and tie in checks with calls to is_button_permitted()

        # Allow G30 only if machine is referenced
        self.button_list['goto_g30'].permitted_states = STATE_IDLE_AND_REFERENCED

        # Only allow spindle range changes during low risk...
        self.settings.checkbutton_list['use_5c_pulley_ratio_checkbutton'].permitted_states = STATE_PAUSED_PROGRAM | STATE_IDLE_AND_REFERENCED | STATE_IDLE
        self.settings.checkbutton_list['use_d1_4_chuck_pulley_checkbutton'].permitted_states = STATE_PAUSED_PROGRAM | STATE_IDLE_AND_REFERENCED | STATE_IDLE

        # Allow tool table import and export.
        self.button_list['import_tool_table'].permitted_states = STATE_ANY
        self.button_list['export_tool_table'].permitted_states = STATE_ANY

        self.button_list['update'].permitted_states = STATE_ESTOP | STATE_IDLE | STATE_IDLE_AND_REFERENCED
        self.button_list['clear'].permitted_states = STATE_ANY
        self.settings.button_list['switch_to_mill'].permitted_states = STATE_ESTOP | STATE_IDLE | STATE_IDLE_AND_REFERENCED

        self.button_list['internet_led_button'].permitted_states = STATE_ESTOP | STATE_IDLE | STATE_IDLE_AND_REFERENCED | STATE_MOVING | STATE_HOMING

        self.button_list['logdata_button'].permitted_states = STATE_ESTOP | STATE_IDLE | STATE_IDLE_AND_REFERENCED

    # ----------------------------------------------------------------------------------------------
    # feeds and speeds related ...
    #-----------------------------------------------------------------------------------------------

    def update_feeds_speeds(self):
        # this may get called before 'fs' is created..
        assert self.fs_mgr, "Fix the call path and init order - why is this getting called now?"
        if not self.fs_mgr: return

        valid, problem = self.fs_mgr.update_feeds_speeds()
        if not valid: self.error_handler.write(problem, ALARM_LEVEL_LOW)


    def feeds_speeds_update_advised(self):
        self.material_data.update_btn_on()

    # ----------------------------------------------------------
    # callbacks
    # ----------------------------------------------------------
    def on_thread_tab(self):
        return self.current_conv_notebook_page_id_is('thread_fixed')

    def get_linear_scale(self):
        """Return the scale factor for all linear axes based on current G20/G21 mode"""
        return 25.4 if self.g21 else 1.0

    def get_axis_scale(self, axis_ind):
        return self.get_linear_scale() if axis_ind < 3 else 1.0


    def is_collet_clamped(self):
        # clamped or unclamped is relative based on the clamping style setting.
        clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
        assert clamping_style in ('OD', 'ID')

        if clamping_style == 'OD':
            if self.collet_closer_status == 0:    # 0 is green LED or "clamped"
                return True
        elif clamping_style == 'ID':
            if self.collet_closer_status == 1:    # 1 is green LED or "clamped"
                return True
        else:
            self.error_handler.log("Unsupported clamping style {}.".format(clamping_style))

        return False


    def on_collet_closer_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)

        self.status.poll()
        if self.spindle_running():
            self.error_handler.write("Cannot change collet clamped state while spindle is on.", ALARM_LEVEL_MEDIUM)

        elif self.program_running() and not self.program_running_but_paused():
            self.error_handler.write("Cannot change collet clamped state while program is running.", ALARM_LEVEL_LOW)

        else:
            clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')

            # Toggle the collet state
            if self.is_collet_clamped():
                # unclamp the collet
                if clamping_style == 'OD':
                    self.hal["collet-closer-manual-output"] = 1
                else:
                    self.hal["collet-closer-manual-output"] = 0
            else:
                # clamp the collet
                if clamping_style == 'OD':
                    self.hal["collet-closer-manual-output"] = 0
                else:
                    self.hal["collet-closer-manual-output"] = 1

            # Toggle the request pin so the tormachcolletcontrol comp acts on the request
            self.hal["collet-closer-manual-request"] = not self.hal["collet-closer-manual-request"]

    def on_ref_x_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # x = 0, y = 1, z = 2, etc)
        if self.moving():
            self.axis_ref_queue.put(0)
        else:
            self.ref_axis(0)

    def on_ref_y_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # x = 0, y = 1, z = 2, etc)
        if self.moving():
            self.axis_ref_queue.put(1)
        else:
            self.ref_axis(1)

    def on_ref_z_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # x = 0, y = 1, z = 2, etc)
        if self.moving():
            self.axis_ref_queue.put(2)
        else:
            self.ref_axis(2)

    def ref_axis(self, axis):
        axis_dict = {0:'X', 1:'Y', 2:'Z', 3:'A'}

        # ignore the request if the axis is already in the middle of homing, be patient...
        if self.hal['axis-{:d}-homing'.format(axis)]:
            self.error_handler.log("Ignoring ref request for axis {:s} as it is already homing.".format(axis_dict[axis]))
            return

        # make sure we're not on a limit right now!
        if (self.status.limit[axis] == 3) and self.settings.home_switches_enabled:
            self.error_handler.write("Cannot reference this axis when on a limit switch.  Move the machine off limit switch before proceeding.")
            return

        # warn if about to re-reference
        if self.status.homed[axis]:
            dialog = popupdlg.ok_cancel_popup(self.window, axis_dict[axis] + ' axis already referenced.  Re-reference?')
            dialog.run()
            dialog.destroy()
            if dialog.response != gtk.RESPONSE_OK :
                return

        # MOTOR_CMD_HOME is converted to MOTOR_CMD_NORMAL if motor doesn't have hard stop
        self.axis_motor_command(axis, MOTOR_CMD_HOME)

        self.ensure_mode(linuxcnc.MODE_MANUAL)
        self.command.home(axis)

    def on_usbio_button_release_event(self, widget, data=None):
        self.error_handler.write('usbio_button_release_event (%s, %s)' % (widget,data), ALARM_LEVEL_DEBUG)
        if not self.is_button_permitted(widget): return

        current_usbio_button = gtk.Buildable.get_name(widget)
        #fetch digit character within usbio_output_#_led
        index = str(int(current_usbio_button[USBIO_STR_DIGIT_INDEX]) + (self.usbio_boardid_selected * 4))

        # convert P0,P1.. to offset P4, P5, etc. for MDI command
        pindex = str(int(index) + USBIO_LATHE_HAL_OFFSET)

        if self.hal["usbio-output-" + index]: #if relay on (use unaltered index)
            command = 'M65 P' + pindex #turn off
        else:
            command = 'M64 P' + pindex #turn on

        # log this to the status tab since they are actually clicking the button.
        # it will help remind them what commands the buttons are doing for integration diagnostics
        self.error_handler.write("USBIO button executing: {}".format(command), ALARM_LEVEL_QUIET)

        self.issue_mdi(command)

    # MDI line
    # most of this moved to ui_common

    def on_mdi_line_activate(self, widget):
        self.mdi_history_index = -1
        command_text = self.mdi_line.get_text()
        # remove leading white space
        command_text = command_text.lstrip()
        # remove trailing white space
        command_text = command_text.rstrip()
        # ignore empty command text
        if len(command_text) == 0:
            # empty command text means "give up focus" so I can now jog easily from the keyboard
            self.window.set_focus(None)
            return

        # insert into history
        self.mdi_history.insert(0, command_text)
        history_len = len(self.mdi_history)
        # limit number of history entries
        if history_len > self.mdi_history_max_entry_count:
            # remove oldest entry
            self.mdi_history.pop()
        # delete second occurance of this command if present
        try:
            second_occurance = self.mdi_history.index(command_text, 1)
            if second_occurance > 0:
                self.mdi_history.pop(second_occurance)
        except ValueError:
            # not a problem
            pass

        if command_text == 'REGRESSION_TEST':
            self.start_regression_test_vehicle()
            return

        if (self.mdi_find_command(command_text)):
            return

        if (self.mdi_admin_commands(command_text)):
            return

        if not (self.x_referenced and self.z_referenced):
            self.error_handler.write("Must reference X and Z axes before issuing command: " + command_text, ALARM_LEVEL_LOW)
            return

        # next lines check for tool change command and don't allow it if turret config and door open
        # feels like a kludge, but is better to nip the command in the bud before it's issued than to catch it
        # in the hal component because IO control v1 has no tool changer fault mechanism and io does funny stuff
        # after a timeout on tool change.
        if 'T' in command_text:
            if (self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_TURRET) and (self.hal['door-switch'] == 1):
                self.error_handler.write("Must close enclosure door before indexing turret")
                return

        # change to MODE_MDI and issue command
        self.issue_mdi(command_text)
        # clear the text on the input line
        self.mdi_line.set_text("")


    # Program Control Group

    def on_cycle_start_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)

        # Call base class behavior
        abort_action = TormachUIBase.on_cycle_start_button(self)
        if abort_action:
            return

        if not (self.x_referenced and self.z_referenced):
            self.error_handler.write("Must reference X and Z axes before executing a gcode program", ALARM_LEVEL_LOW)
            return
        if self.current_notebook_page_id != 'notebook_main_fixed':
            self.error_handler.write("Cannot start program while not on Main screen", ALARM_LEVEL_LOW)
            return
        if self.hal['door-switch'] == 1:
            self.error_handler.write("Must close door or chuck guard before starting program", ALARM_LEVEL_LOW)
            return

        # Collet clamp check is now being done inside M3 and M4 remap code. That location
        # is more reliable and programs can be started unclamped and issue M11 or M10 in the right spots
        # to work with bar pullers and such.

        self.gcode_pattern_search.clear()
        self.window.set_focus(None)

        if self.program_paused_for_door_sw_open:
            self.resume_program_from_door_sw_open()

        # tool change in progress and manual tool changer
        if self.hal['tool-change'] and self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_MANUAL:
            # tell tool changer comp that operator has indicated tool change complete
            self.hal['manual-tool-changed'] = 1

        # pressing CS should always clear feedhold.
        self.feedhold_active = False
        self.set_image('feedhold_image', 'Feedhold-Black.jpg')

        self.hide_m1_image()
        self.use_hal_gcode_timers = True

        self.status.poll()
        # if status.paused, we're already in MODE_AUTO (or MODE_MDI with feedhold!), so resume the program
        if self.status.paused:
            if self.single_block_active:
                self.command.auto(linuxcnc.AUTO_STEP)
            else:
                self.command.auto(linuxcnc.AUTO_RESUME)
                return

        if not self.is_gcode_program_loaded:
            self.error_handler.write("Must load a g-code program before pressing cycle start.", ALARM_LEVEL_MEDIUM)
            return

        # this helps avoid cycle start button presses while a program is already running from causing
        # extra log lines and messing up the remaining time clock.
        if not self.program_running():
            # if we are starting the program at the beginning then load up
            # the last runtime so we can calculate remaining time
            if self.gcode_start_line <= 1:
                self.last_runtime_sec = self.stats_mgr.get_last_runtime_sec()

            if self.is_gcode_program_loaded:
                self.stats_mgr.log_cycle_start(self.gcode_start_line)

            # clear live plotter if the last program ran to completion and ended gracefully
            # or if the program is starting at the beginning.
            # only time an existing live plot tool path is valuable to retain is when
            # starting from the middle of the program and you want to discern when old vs. new cuts
            # might be happening.
            if self.status.program_ended or self.status.program_ended_and_reset or (self.gcode_start_line <= 1):
                self.gremlin.clear_live_plotter()

        # now that stop button doesn't slam the gcode listing to line 0, be sure the
        # current start line is visible if we're just kicking things off.  If we're
        # single blocking and nailing cycle start button all the time, current_line
        # won't be zero so we avoid flashing the window.
        if self.status.current_line == 0:
            self.sourceview.scroll_to_mark(self.gcodelisting_start_mark, 0, True, 0, 0.5)
            self.gcodelisting_mark_current_line(self.gcode_start_line)

        # Otherwise, switch to MODE_AUTO and run the code
        if self.status.interp_state == linuxcnc.INTERP_IDLE:
            self.ensure_mode(linuxcnc.MODE_AUTO)
            if self.single_block_active:
                if self.gcode_start_line != 1:
                    self.error_handler.log("Cycle start with {:d} as gcode start line".format(self.gcode_start_line))
                    self.command.auto(linuxcnc.AUTO_RUN, self.gcode_start_line)
                    self.command.auto(linuxcnc.AUTO_PAUSE)
                    self.command.auto(linuxcnc.AUTO_STEP)
                else:
                    self.command.auto(linuxcnc.AUTO_STEP)
            else:
                self.error_handler.log("Cycle start with {:d} as gcode start line".format(self.gcode_start_line))
                self.command.auto(linuxcnc.AUTO_RUN, self.gcode_start_line)


    def on_single_block_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        if not self.program_running():
            if self.single_block_active:
                self.single_block_active = False
                self.set_image('single_block_image', 'Single-Block-Black.jpg')
            else:
                self.single_block_active = True
                self.set_image('single_block_image', 'Single-Block-Green.jpg')
        # not using program running here to include queued MDI
        elif self.status.queue > 0 or self.status.paused:
            if self.single_block_active:
                # only do the auto_resume if we're already in the middle of a move!
                if self.status.current_vel != 0:
                    self.command.auto(linuxcnc.AUTO_RESUME)
                self.single_block_active = False
                self.set_image('single_block_image', 'Single-Block-Black.jpg')
            else:
                self.command.auto(linuxcnc.AUTO_PAUSE)
                self.single_block_active = True
                self.command.auto(linuxcnc.AUTO_STEP)
                self.set_image('single_block_image', 'Single-Block-Green.jpg')

    def on_m01_break_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        if  self.m01_break_active:
            self.command.set_optional_stop(False)
            self.m01_break_active = False
            self.set_image('m01_break_image', 'M01-Break-Black.jpg')
        else:
            self.command.set_optional_stop(True)
            self.m01_break_active = True
            self.set_image('m01_break_image', 'M01-Break-Green.jpg')

    def on_feedhold_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        if self.moving():
            if not self.feedhold_active:
                self.command.auto(linuxcnc.AUTO_PAUSE)
                self.feedhold_active = True
                self.set_image('feedhold_image', 'Feedhold-Green.jpg')


    def on_stop_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # Did we interrupt a turret tool change and possibly leave
        # LinuxCNC in an inconsistent state?
        requested_tool = 0
        if self.hal['tool-change'] and self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_TURRET:
            requested_tool = self.hal['tool-prep-number']

        self.stop_motion_safely()

        self.hide_m1_image()
        self.clear_message_line_text()

        # purge any queued up axis reference requests
        while not self.axis_ref_queue.empty():
            try:
                self.axis_ref_queue.get_nowait()
            except Queue.Empty:
                pass

        if requested_tool != 0:
            # we interrupted a turret tool change so poke linuxcnc to use the correct tool that the turret actually has now.
            # must wait for interp idle or issue_mdi() might fail from self.moving() being True
            # due to busy interp
            self.error_handler.log("Turret tool change interrupted by ESC or Stop button - making sure LCNC knows final tool and wear offset that turret ended up on.")
            self.wait_interp_idle()

            wear_offset_num_pre = int(round(self.mm_inch_scalar * self.status.tool_offset[8]))

            self.issue_mdi('M61 Q%2.2d%2.2d' % (requested_tool, requested_tool))
            self.command.wait_complete()

            # no need to offset by 10000 - LinuxCNC handles it
            # this restores the wear offset also - the above M61 Q won't do it (or at least it doesn't appear
            # to since the hack of self.status in the 'w' axis for reporting the wear number isn't done by that.
            self.issue_mdi('G43 H{:02d}{:02d}'.format(requested_tool, requested_tool))
            self.command.wait_complete()

        self.call_ui_hook('stop_button')

    def on_coolant_button_release_event(self, widget, data=None):
        # POSTGUI_HALFILE contains:
        # net coolant-flood tormach.coolant => parport.0.pin-14-out
        # net coolant-flood-io iocontrol.0.coolant-flood => tormach.coolant-iocontrol
        # The UI code here watches tormach.coolant-iocontrol for changes from LinuxCNC.
        # See the periodic handler for details
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # disable coolant lockout : if user commands coolant, do it immediately
        self.coolant_lockout = 0
        # use our tormach.coolant HAL pin to track actual coolant state
        coolant_on = self.hal['coolant']
        if not coolant_on:
            self.hal['coolant'] = 1
        else:
            self.hal['coolant'] = 0

    def on_reset_button_release_event(self, widget, data=None):
        self.hal['pp-estop-fault'] = 0   #clear any existing pp software estops
        self.halt_world_flag = False # TODO: note issues with halt world.  Do we lock it out during reset
                                    # and then check or reset this at end of on_reset_button_release

        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        self.clear_message_line_text()
        self.hide_m1_image()

        # purge any queued up axis reference requests
        while not self.axis_ref_queue.empty():
            try:
                self.axis_ref_queue.get_nowait()
            except Queue.Empty:
                pass

        if not self.first_run:
            # if called on first press of Reset it is too soon for the USBIO module to handle setting outputs
            # it displays an ugly error message
            # this could be done later in the method but there are too many 'return' points where it
            # could get missed
            self.call_ui_hook('reset_button')

        if self.hal['mesa-watchdog-has-bit']:
            # since resetting the mesa card io_error parameter is more involved now with ethernet,
            # only do this if we really did see a watchdog bite.

            # clear Mesa IO errors (if any).  this must be done PRIOR to setting the mesa-watchdog-has-bit pin low.
            clear_hostmot2_board_io_error(self.inifile)

            # clear Mesa card watchdog
            self.hal['mesa-watchdog-has-bit'] = 0
            self.mesa_watchdog_has_bit_seen = False

            # give it a second to re-establish IO link before jamming commands at it.
            time.sleep(1.0)
            self.status.poll()

            # did the watchdog re-bite already?  If so, re-establishing the IO link didn't work.
            # leave us in e-stop.
            if self.hal['mesa-watchdog-has-bit']:
                self.mesa_watchdog_has_bit_seen = True
                self.error_handler.write("Machine interface error. Check cabling and power to machine and then press RESET.", ALARM_LEVEL_MEDIUM)
                return

        # clear feedhold
        if self.feedhold_active:
            self.feedhold_active = False
            self.set_image('feedhold_image', 'Feedhold-Black.jpg')

        # reset e-stop
        if self.status.task_state != linuxcnc.STATE_ESTOP_RESET:
            self.command.state(linuxcnc.STATE_ESTOP_RESET)
            self.command.wait_complete()
            self.status.poll()
            if self.status.task_state not in [linuxcnc.STATE_ESTOP_RESET, linuxcnc.STATE_ON]:
                self.error_handler.write("Failed to bring machine out of E-stop. Please check machine power, limit switches, and communication cable from the controller to the machine.")
                return

        # clear alarm
        self.estop_alarm = False
        self.display_estop_msg = True

        # Prevent coming out of Reset if a limit switch is active.
        if (self.status.limit[0] != 0):
            error_msg = 'X limit switch active.'
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
        if (self.status.limit[1] != 0):
            error_msg = 'Y limit switch active.'
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
        if (self.status.limit[2] != 0):
            error_msg = 'Z limit switch active.'
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
        if (self.status.limit[0] != 0) or (self.status.limit[1] != 0) or (self.status.limit[2] != 0):
            error_msg = 'Disable limit switches in Settings, then push Reset, then carefully jog off limit switch, then re-enable limit switches in Settings.'
            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
            return

        # must be turned on again after being reset from estop
        if self.status.task_state != linuxcnc.STATE_ON:
            self.command.state(linuxcnc.STATE_ON)
            self.command.wait_complete()
            self.status.poll()
            if self.status.task_state != linuxcnc.STATE_ON :
                self.error_handler.write("Failed to bring machine out of E-stop. Please check machine power, limit switches, and communication cable from the controller to the machine.")
                return

        # stop motion
        self.command.abort()
        self.command.wait_complete()

        # Turn off coolant & reset associated states
        self.prev_coolant_iocontrol = self.hal['coolant'] = 0
        self.coolant_status = self.prev_coolant_status = 0
        self.coolant_lockout = COOLANT_LOCK_OUT_PERIOD

        # reset/rewind program
        # as long as a limit switch is not active
        if self.machineconfig.in_rapidturn_mode():
            if (self.status.limit[0] == 0) and (self.status.limit[1] == 0) and (self.status.limit[2] == 0):
                self.issue_mdi('M30')
        else:
            if (self.status.limit[0] == 0) and (self.status.limit[2] == 0):
                self.issue_mdi('M30')

        # clear SB status
        self.single_block_active = False
        self.set_image('single_block_image', 'Single-Block-Black.jpg')

        # clear live plotter
        self.gremlin.clear_live_plotter()

        # refresh work offsets
        self.refresh_work_offset_liststore()

        # rewind program listing
        # set starting line
        if self.is_gcode_program_loaded:
            self.gcodelisting_mark_start_line(1)

            # some folks got confused because their program ended, the M30 reset current line to 0 and
            # the 50ms periodic auto-scrolled back up to the start line.  But then they managed to scroll
            # around in the view and then press the Reset button and they expect it to auto-scroll to the
            # top again.  The 50ms periodic doesn't do anything because the current line hasn't 'changed'
            # from 0 so we need this here to always smack the display back to the start line.
            self.sourceview.scroll_to_mark(self.gcodelisting_start_mark, 0, True, 0, 0.5)

        self.status.poll()
        self.ensure_mode(linuxcnc.MODE_MDI)

        self.do_first_run_setup()

        # start the motors
        self.axis_motor_command(0, MOTOR_CMD_NORMAL)
        if self.machineconfig.in_rapidturn_mode():  # we have a Y axis with a motor on it
            self.axis_motor_command(1, MOTOR_CMD_NORMAL)
        self.axis_motor_command(2, MOTOR_CMD_NORMAL)

        # g21 and machineconfig need to be accurate before setting scaled jog increment
        jog_ix = self.hal['jog-gui-step-index']
        if self.g21:
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g21()[jog_ix]
        else:
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g20()[jog_ix]


    def on_feedrate_override_button_release_event(self, widget, event, data=None):
        btn.ImageButton.unshift_button(widget)
        self.set_feedrate_override(100)

    def on_rpm_override_button_release_event(self, widget, event, data=None):
        btn.ImageButton.unshift_button(widget)
        self.set_spindle_override(100)

    def on_maxvel_override_button_release_event(self, widget, event, data=None):
        btn.ImageButton.unshift_button(widget)
        self.set_maxvel_override(100)



    # Position/Status Readout Group

    # common dro callbacks

    def on_dro_gets_focus(self, widget, event):
        # this clues in the tool tip mgr to stop the state machine from displaying the tool tip for this dro.
        # the user is already in the midst of editing the DRO value so they don't need help anymore, its just
        # annoying otherwise.
        tooltipmgr.TTMgr().on_button_press(widget, event)

        if self.moving() or not widget.has_focus():
            return
        widget.prev_val = widget.get_text()
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color(HIGHLIGHT))
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        widget.masked = True
        # only highlight the whole field if the user hasn't selected a portion of it
        if not widget.get_selection_bounds():
            widget.select_region(0, -1)
        if self.settings.touchscreen_enabled:
            np = numpad.numpad_popup(self.window, widget)
            np.run()
            widget.masked = 0
            widget.select_region(0, 0)
            self.window.set_focus(None)


    def on_dro_loses_focus(self, widget, data=None):
        if widget_in_alarm_state(widget): return
        widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
        widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
        if not self.settings.touchscreen_enabled:
            widget.masked = False
            widget.select_region(0, 0)

    def on_dro_key_press_event(self, widget, event, data=None):
        kv = event.keyval
        if kv == gtk.keysyms.Escape:
            widget.modify_base(gtk.STATE_NORMAL, gtk.gdk.Color('white'))
            widget.modify_text(gtk.STATE_NORMAL, gtk.gdk.Color('black'))
            widget.masked = False
            self.window.set_focus(None)
            return True

    def on_css_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        if self.css_active:
            self.on_spindle_rpm_dro_activate(self.dro_list['spindle_rpm_dro'])
        else:
            self.on_spindle_css_dro_activate(self.dro_list['spindle_css_dro'])

    def on_feed_per_rev_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        if self.f_per_rev_active:
            self.on_feed_per_min_dro_activate(self.dro_list['feed_per_min_dro'])
        else:
            self.on_feed_per_rev_dro_activate(self.dro_list['feed_per_rev_dro'])

    def on_zero_z_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        if self.moving(): return
        self.set_work_offset("Z", 0)

    def on_spindle_css_dro_activate(self, widget, data=None):
        # user entry validation
        valid, dro_val, error_msg = self.conversational.validate_surface_speed(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        css_val = abs(dro_val)
        g96_command = "G96 S%.0f" % (css_val)
        self.issue_mdi(g96_command)

        # unmask DROs
        widget.masked = 0
        self.window.set_focus(None)

    def on_spindle_rpm_dro_activate(self, widget, data=None):
        # issue G97, LED off, FPM computed from X DRO: RPM * (PI * diameter)
        # get DRO value
        # TODO: this should not use the conversational rpm validation
        # it should have its own that uses INI file settings and selected chuck/5c config setting
        # Given conversational is now using ini file settings, is this now OK to use??
        valid, dro_val, error_msg = self.conversational.validate_spindle_rpm(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        s_rpm = abs(dro_val)
        if s_rpm > self.max_rpm:  #necessary?  self.conversational.validate_spindle_rpm did this already, right??
            s_rpm = self.max_rpm
        g97_command = "G97 S%.0f" % (s_rpm)
        self.issue_mdi(g97_command)
                # unmask DROs
        widget.masked = 0
        self.window.set_focus(None)

    def on_feed_per_rev_dro_activate(self, widget, data=None):
        valid, dro_val, error_msg = self.conversational.validate_feedrate(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        feed_per_rev = abs(dro_val)
        # compute feed /min from RPM, set DRO text
        g95_command = "G95 F%.4f" % (feed_per_rev)
        self.issue_mdi(g95_command)
        widget.masked = 0
        self.window.set_focus(None)


    def on_feed_per_min_dro_activate(self, widget, data=None):
        # get DRO value
        valid, dro_val, error_msg = self.conversational.validate_feedrate(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        feed_per_min = abs(dro_val)
        g94_command = "G94 F%.4f" % (feed_per_min)
        self.issue_mdi(g94_command)
        # unmask DROs
        widget.masked = 0
        self.window.set_focus(None)


    def on_z_dro_activate(self, widget):
        valid, dro_val, error_msg = self.conversational.validate_z_point(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        self.set_work_offset("Z", dro_val)
        # allow updates
        widget.masked = 0
        self.window.set_focus(None)

    # rapidturn only
    def on_y_dro_activate(self, widget):
        valid, dro_val, error_msg = self.conversational.validate_y_point(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        self.set_work_offset("Y", dro_val)
        # allow updates
        widget.masked = 0
        self.window.set_focus(None)


    def on_dia_dro_activate(self, widget):
        valid, dro_val, error_msg = self.conversational.validate_dia_val(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        x = dro_val * 2
        self.set_work_offset("X", x)
        # allow updates
        widget.masked = 0
        self.window.set_focus(None)


    def on_key_press_or_release(self, widget, event, data=None):
        kv = event.keyval

        '''print ''
        if event.type == gtk.gdk.KEY_PRESS:
          print 'gtk.gdk.KEY_PRESS'
        if event.type == gtk.gdk.KEY_RELEASE:
          print 'gtk.gdk.KEY_RELEASE'
        print 'event.statekeyval: %d 0x%04x' % (kv, kv)
        print 'event.statestate:  %d 0x%04x' % (event.state, event.state)'''

        # Utilities
        if event.type == gtk.gdk.KEY_PRESS:
            if kv == gtk.keysyms.F1:
            # If we're not on the status page, save the current page and switch
            # to the status page
            # The logic is a little convoluted because auto-repeat of keys ends up
            # sending us a lot of KEY_PRESS events, but only one KEY_RELEASE.
            # F1_page_toggled gives us enough info so that if you're on the alarms_fixed
            # and hold down F1, then upon its release, we don't switch back to whatever
            # happens to be laying around in prev_page.  Effectively F1 hold is
            # ignored when you're on the alarms_fixed page entirey.
                if self.current_notebook_page_id != 'alarms_fixed':
                    self.F1_page_toggled = True
                    self.prev_notebook_page_id = self.current_notebook_page_id
                    set_current_notebook_page_by_id(self.notebook, 'alarms_fixed')
            elif kv == gtk.keysyms.Print:
                self.screen_grab()
            else:
                tooltipmgr.TTMgr().temporary_activate(kv)

        if event.type == gtk.gdk.KEY_RELEASE:
            if kv == gtk.keysyms.F1:
                if self.F1_page_toggled:
                    self.F1_page_toggled = False
                    set_current_notebook_page_by_id(self.notebook, self.prev_notebook_page_id)
                    # gtk2 bug where is we are restoring to notebook_main_fixed and the MDI entry box formerly had
                    # focus when F1 was pushed, it regains focus, but does NOT signal the on_mdi_line_gets_focus.
                    if self.prev_notebook_page_id == 'notebook_main_fixed' and self.mdi_line.has_focus():
                        self.on_mdi_line_gets_focus(self.mdi_line, None)
            else:
                tooltipmgr.TTMgr().temporary_deactivate(kv)


        # open new terminal window
        # MOD1_MASK indicates the left Alt key pressed
        # CONTROL_MASK indicates either Ctrl key is pressed
        if event.state & gtk.gdk.MOD1_MASK and event.state & gtk.gdk.CONTROL_MASK:
            if kv in [gtk.keysyms.x, gtk.keysyms.X] and event.type == gtk.gdk.KEY_PRESS:
                # start a terminal window in $HOME directory
                subprocess.Popen(args=["gnome-terminal", "--working-directory=" + os.getenv('HOME')]).pid
                return True


        # Keyboard functions
        # Return True on TAB to prevent tabbing focus changes
        if kv == gtk.keysyms.Tab:
            return True

        # Disable jogging and pass through depending on focus
        if kv in self.jogging_keys and True not in self.jogging_key_pressed.values():

            #First, handle specific cases that don't behave by type rules

            # no jogging while mdi line has focus
            if self.mdi_line_masked:
                # Make sure to pass through key presses to navigate MDI
                return False if kv in self.mdi_mask_keys else True

            # Next, check the type of the current focused item and pass through
            # keys if needed
            focused_item = type(self.window.get_focus())

            if focused_item in self.key_mask:
                return False if kv in self.key_mask[focused_item] else True


            # No jogging on File or Alarms tab
            active_page_id = self.current_notebook_page_id

            # Look up the key mask we need to use for the current notebook
            # This is a clean way to check if we need to disable jogging on a
            # per-page basis. If there isn't an entry for the notebook, then we
            # assume that it's ok if that notebook is active
            if active_page_id in self.disable_jog_page_ids and not self.moving():
                #Reject keypress since it's not handled by the focused element
                return True


        # grab the keystroke if tool_descript_entry is active
        if self.tool_descript_entry.active() and kv in self.tool_descript_keys: return False


        # Preconditions checked -  Jogging handled below
        # check to see if we're releasing the key

        # Force jogging to stop whenever shift keys are pressed or released
        # (Mach3 Style)
        if kv in [gtk.keysyms.Shift_L, gtk.keysyms.Shift_R] and not self.program_running() and not self.mdi_running() and self.moving():
            for jog_axis in [0,2]:
                self.stop_jog(jog_axis)
            return True

        if event.type == gtk.gdk.KEY_RELEASE and kv in self.jogging_keys:
            self.jogging_key_pressed[kv] = False
            # in or out - x axis
            if kv ==  gtk.keysyms.Left or kv == gtk.keysyms.Right:
                jog_axis = 2
            elif self.machineconfig.in_rapidturn_mode() and (kv == gtk.keysyms.Prior or kv == gtk.keysyms.Next):
                # rapidturn y axis
                jog_axis = 1
            # along spindle axis - z axis
            elif kv == gtk.keysyms.Up or kv == gtk.keysyms.Down:
                jog_axis = 0
            else:
                return False

            if self.jog_mode == linuxcnc.JOG_CONTINUOUS:
                if not self.program_running():
                    self.stop_jog(jog_axis)
            return True

        elif event.type == gtk.gdk.KEY_PRESS and kv in self.jogging_keys:
            if kv == gtk.keysyms.Right:
                # right arrow - X positive
                jog_axis = 2
                jog_direction = 1
            elif kv == gtk.keysyms.Left:
                jog_axis = 2
                jog_direction = -1
            elif self.machineconfig.in_rapidturn_mode() and kv == gtk.keysyms.Prior:
                jog_axis = 1
                jog_direction = 1
            elif self.machineconfig.in_rapidturn_mode() and kv == gtk.keysyms.Next:
                jog_axis = 1
                jog_direction = -1
            elif kv == gtk.keysyms.Up:
                jog_axis = 0
                jog_direction = 1
            elif kv == gtk.keysyms.Down:
                jog_axis = 0
                jog_direction = -1
            else:
                return False
            # After determining the axis and direction, run the jog iff the key
            # is not already depressed

            jogging_rapid = event.state & gtk.gdk.SHIFT_MASK

            if not self.jogging_key_pressed[kv]:
                actual_scale = 1.0 if jogging_rapid else self.jog_override_pct
                self.set_jog_mode(self.keyboard_jog_mode)
                self.jog(jog_axis, jog_direction, self.jog_speeds[jog_axis] * actual_scale, False)
            # Update the state of the pressed key
            self.jogging_key_pressed[kv]=True
            self.jogging_rapid = jogging_rapid
            return True

        if event.type == gtk.gdk.KEY_PRESS:
            # Handle feed hold
            if kv == gtk.keysyms.space and self.moving():
                self.error_handler.log("Spacebar key - queueing feedhold event")
                self.enqueue_button_press_release(self.button_list['feedhold'])
                return True

            # Escape key for stop - removed due to issues with turret tool change being aborted
            # if you press ESC rigth after an MDI tool change, task thinks the change didn't complete
            # but the turret successfully changes.  The result is that the operator thinks the new tool is
            # active, but the system has T0 active with no offsets applied
            # better to remove this.  Having ESC defocus and stop is a bad design choice.  Will leave in mill for now
            # Escape key for stop

            # Escape used to stop certain UI tasks.
            if kv == gtk.keysyms.Escape:
                self.error_handler.log("ESC key - queueing stop event")
                self.enqueue_button_press_release(self.button_list['stop'])
                self.tool_descript_entry.shutdown_view() # if active terminates the tool description overlay
                self.profile_renderer.update()           # if active terminates a zoom view on the profile render
                tooltipmgr.TTMgr().on_esc_key()          # if active end the current tooltip.
                return True

        # alt key shortcuts  (without control pressed!)
        # MOD1_MASK indicates the left alt key pressed
        # MOD5_MASK indicates the right alt key pressed
        if not (event.state & gtk.gdk.CONTROL_MASK) and (event.state & (gtk.gdk.MOD1_MASK | gtk.gdk.MOD5_MASK)) and event.type == gtk.gdk.KEY_RELEASE:

            # alt-enter to set focus to MDI line
            # must only work when the Main tab or Status tab is showing
            if self.current_notebook_page_id in ('notebook_main_fixed', 'alarms_fixed') and kv in (gtk.keysyms.Return, gtk.keysyms.KP_Enter) and not self.program_running():
                if self.current_notebook_page_id != 'notebook_main_fixed':
                    set_current_notebook_page_by_id(self.notebook, 'notebook_main_fixed')
                # make sure that the notebook on the main tab has the mdi page visible
                if get_current_notebook_page_id(self.gcode_options_notebook) != 'gcode_page_fixed':
                    set_current_notebook_page_by_id(self.gcode_options_notebook, 'gcode_page_fixed')
                self.on_mdi_line_gets_focus(self.mdi_line, None)
                self.mdi_line.grab_focus()

            # alt-e, edit current gcode program
            if kv in [gtk.keysyms.e, gtk.keysyms.E]:
                # cannot enqueue edit_gcode button press - it only works after File tab has been opened
                path = self.current_gcode_file_path
                if not self.moving():
                    if path != '':
                        # Shift-Alt-E means edit conversationally (if possible)
                        convedit = False
                        if event.state & gtk.gdk.SHIFT_MASK:
                            gc = conversational.ConvDecompiler(self.conversational, path, self.error_handler)
                            if any(gc.segments):
                                job_assignment.JAObj().set_gc()
                                job_assignment.JAObj().set_gc(gc)
                                job_assignment.JAObj().job_assignment_conv_edit()
                                convedit = True
                        if not convedit:
                            self.edit_gcode_file(path)
                    else:
                        # open gedit with empty file
                        self.edit_new_gcode_file()

            for (k_val, k_widget) in self.alt_keyboard_shortcuts:
                if kv == k_val:
                    self.enqueue_button_press_release(k_widget)

        # ctrl-alt key shortcuts
        if (event.state & gtk.gdk.CONTROL_MASK) and (event.state & (gtk.gdk.MOD1_MASK | gtk.gdk.MOD5_MASK)) and event.type == gtk.gdk.KEY_RELEASE:
            # both Control and Alt keys active
            if kv in [gtk.keysyms.n, gtk.keysyms.N]:
                # collet closer switch closing
                self.error_handler.write("Ctrl-Alt-N shortcut detected. Queueing collet closer button press.", ALARM_LEVEL_DEBUG)
                self.enqueue_button_press_release(self.button_list['collet_closer'])

            elif kv in [gtk.keysyms.m, gtk.keysyms.M]:
                # collet closer switch opening
                self.error_handler.write("Ctrl-Alt-M shortcut detected.", ALARM_LEVEL_DEBUG)

            elif kv in [gtk.keysyms.d, gtk.keysyms.D]:
                # ctrl-alt-d
                self.error_handler.log("Enabling debug notebook page")
                self.add_debug_page()

        # ctrl key shortcuts
        # CONTROL_MASK indicates the left ctrl key pressed
        if event.state & gtk.gdk.CONTROL_MASK and event.type == gtk.gdk.KEY_RELEASE:
            for (k_val, k_widget) in self.ctrl_keyboard_shortcuts:
                if kv == k_val:
                    self.enqueue_button_press_release(k_widget)

        return False


    def on_jog_speed_scale_gets_focus(self, widget, data=None):
        self.set_keyboard_jog_mode(linuxcnc.JOG_CONTINUOUS)


    def on_jog_speed_adjustment_value_changed(self, adjustment):
        self.jog_speed_label.set_text(str(int(adjustment.value))+"%")
        self.set_keyboard_jog_mode(linuxcnc.JOG_CONTINUOUS)
        self.jog_override_pct = (adjustment.value)/100
        self.redis.hset('machine_prefs', 'jog_override_percentage', self.jog_override_pct)
        tooltipmgr.TTMgr().on_adjustment_value_changed(adjustment)

    def on_jog_inc_cont_button_release_event(self, widget, event, data=None):
        if not self.is_button_permitted(widget): return
        self.error_handler.write("jog mode was: %s" % str(self.jog_mode), ALARM_LEVEL_DEBUG)
        if self.jog_mode == linuxcnc.JOG_INCREMENT:
            self.set_keyboard_jog_mode(linuxcnc.JOG_CONTINUOUS)
        else:
            self.set_keyboard_jog_mode(linuxcnc.JOG_INCREMENT)


    def jog_button_release_handler(self, widget, jog_index):
        if not self.is_button_permitted(widget): return False
        if not self.set_keyboard_jog_mode(linuxcnc.JOG_INCREMENT): return False
        self.clear_jog_LEDs()
        if self.g21:
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g21()[jog_index]
            self.set_image(self.jog_image_names[jog_index], self.jog_step_images_g21_green[jog_index])
        else:
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g20()[jog_index]
            self.set_image(self.jog_image_names[jog_index], self.jog_step_images_g20_green[jog_index])
        self.hal['jog-gui-step-index'] = jog_index
        self.error_handler.write('jog increment: %3.4F' % self.jog_increment_scaled, ALARM_LEVEL_DEBUG)
        return True


    def on_jog_zero_button_release_event(self, widget, data=None):
        self.jog_button_release_handler(widget, 0)


    def on_jog_one_button_release_event(self, widget, data=None):
        self.jog_button_release_handler(widget, 1)


    def on_jog_two_button_release_event(self, widget, data=None):
        self.jog_button_release_handler(widget, 2)


    def on_jog_three_button_release_event(self, widget, data=None):
        self.jog_button_release_handler(widget, 3)


    def on_ccw_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # must be on Main tab or Offsets tab
        if not self.current_notebook_page_id in ('notebook_main_fixed', 'notebook_offsets_fixed'):
            self.error_handler.write("Cannot start spindle while not on Main or Offsets tab", ALARM_LEVEL_LOW)
            return

        # collet must be "clamped"
        if not self.is_collet_clamped():
            self.error_handler.write("Cannot start spindle with collet unclamped", ALARM_LEVEL_MEDIUM)
            return

        # Per conversation with John, better to do this with command.spindle_fwd
        # quick look at touchy/axis makes me think that there's no way to set
        # spindle speed in MODE_MANUAL.
        if self.door_switch == 1:
            self.error_handler.write("Cannot start spindle with door open", ALARM_LEVEL_LOW)
        else:
            # TODO: this should not use the conversational rpm validation
            # it should have its own that uses INI file settings and selected chuck/5c config setting
            valid, dro_val, error_msg = self.conversational.validate_spindle_rpm(self.dro_list['spindle_rpm_dro'])
            if not valid:
                self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
                return
            self.issue_mdi("m4")

    def on_spindle_stop_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        self.issue_mdi("m5")

    def on_cw_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.window.set_focus(None)
        # must be on Main tab or Offsets tab
        if not self.current_notebook_page_id in ('notebook_main_fixed', 'notebook_offsets_fixed'):
            self.error_handler.write("Cannot start spindle while not on Main or Offsets tab", ALARM_LEVEL_LOW)
            return

        # collet must be "clamped"
        if not self.is_collet_clamped():
            self.error_handler.write("Cannot start spindle with collet unclamped", ALARM_LEVEL_MEDIUM)
            return

        if self.door_switch == 1:
            self.error_handler.write("Cannot start spindle with door open", ALARM_LEVEL_LOW)
        else:
            # TODO: this should not use the conversational rpm validation
            # it should have its own that uses INI file settings and selected chuck/5c config setting
            valid, dro_val, error_msg = self.conversational.validate_spindle_rpm(self.dro_list['spindle_rpm_dro'])
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        self.issue_mdi("m3")

    # ---------------------------------------------------------------------
    # Alarms/settings tab
    #----------------------------------------------------------------------

    def on_settings_lockout_activate(self, widget, data=None):
        lockout_code = widget.get_text()
        # TODO - set up a self.settings_lockout_level


    def set_home_switches(self):
        self.hal["home-switch-enable"] = self.settings.home_switches_enabled
        self.redis.hset('machine_prefs', 'home_switches_enabled', self.settings.home_switches_enabled)
        self.enable_home_switch(0, self.settings.home_switches_enabled)
        if self.machineconfig.in_rapidturn_mode():
            self.enable_home_switch(1, self.settings.home_switches_enabled)
        self.enable_home_switch(2, self.settings.home_switches_enabled)


    # ---------------------------------------------------------------------
    # tool touch off tab
    #----------------------------------------------------------------------
    # on paging to the tool touch we should check the tool type for the currently loaded tool.  If the tool type is 0 (not yet configured)
    # then we display the spash screen.  Also, we need to offer a "reset tool" button that changes the type to 0 and displays the splash.

    # lathe tool highlighting on mouseover
    def on_tt_rear_tp_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_profile_highlight_85.png'))

    def on_tt_rear_tp_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_profile_85.png'))

    def on_tt_front_tp_lh_turn_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_lh_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_turn_lh_highlight_85.png'))

    def on_tt_front_tp_lh_turn_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_lh_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_turn_lh_85.png'))

    def on_tt_front_tp_lh_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_lh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_lh_profile_highlight_85.png'))

    def on_tt_front_tp_lh_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_lh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_lh_profile_85.png'))

    def on_tt_front_tp_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_profile_highlight_85.png'))

    def on_tt_front_tp_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_profile_85.png'))

    def on_tt_front_tp_rh_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_rh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_rh_profile_highlight_85.png'))

    def on_tt_front_tp_rh_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_rh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_rh_profile_85.png'))

    def on_tt_rear_tp_lh_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_lh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_lh_profile_highlight_85.png'))

    def on_tt_rear_tp_lh_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_lh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_lh_profile_85.png'))

    def on_tt_rear_tp_rh_profile_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_rh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_rh_profile_highlight_85.png'))

    def on_tt_rear_tp_rh_profile_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_rh_profile_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_rh_profile_85.png'))

    def on_tt_rear_tp_lh_turn_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_lh_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_turn_lh_highlight_85.png'))

    def on_tt_rear_tp_lh_turn_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_lh_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_turn_lh_85.png'))

    def on_tt_rear_tp_turn_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_turn_highlight_85.png'))

    def on_tt_rear_tp_turn_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_turn_85.png'))

    def on_tt_front_tp_turn_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_turn_highlight_85.png'))

    def on_tt_front_tp_turn_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_turn_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_turn_85.png'))

    def on_tt_rear_tp_thread_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_thread_highlight_85.png'))

    def on_tt_rear_tp_thread_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_thread_85.png'))

    def on_tt_front_tp_thread_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_thread_highlight_85.png'))

    def on_tt_front_tp_thread_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_thread_85.png'))

    def on_tt_rear_tp_part_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_part_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_part_highlight_85.png'))

    def on_tt_rear_tp_part_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_tp_part_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_part_85.png'))

    def on_tt_front_tp_part_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_part_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_part_highlight_85.png'))

    def on_tt_front_tp_part_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_tp_part_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_part_85.png'))

    def on_tt_rear_id_thread_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_id_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_id_thread_highlight.png'))

    def on_tt_rear_id_thread_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_id_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_id_thread.png'))

    def on_tt_center_drill_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_center_drill_image'].set_from_file(os.path.join(GLADE_DIR, 'center_drill_highlight.png'))

    def on_tt_center_drill_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_center_drill_image'].set_from_file(os.path.join(GLADE_DIR, 'center_drill.png'))

    def on_tt_rear_boring_bar_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_boring_bar_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_boring_bar_highlight.png'))

    def on_tt_rear_boring_bar_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_rear_boring_bar_image'].set_from_file(os.path.join(GLADE_DIR, 'rear_tp_boring_bar.png'))

    def on_tt_front_boring_bar_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_boring_bar_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_boring_bar_highlight.png'))

    def on_tt_front_boring_bar_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_boring_bar_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_boring_bar.png'))

    def on_tt_front_id_thread_eventbox_enter_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_id_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_id_thread_highlight.png'))

    def on_tt_front_id_thread_eventbox_leave_notify_event(self, widget, data=None):
        self.tool_image_list['tt_front_id_thread_image'].set_from_file(os.path.join(GLADE_DIR, 'front_tp_id_thread.png'))

    # lathe tool select callbacks
    # check to ensure tool number is OK before allowing user past the splash screen
    def on_tt_rear_tp_lh_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_lh_profile.png")
        self.write_tool_type(self.current_tool, "rtp_lh_profile")

    def on_tt_rear_tp_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_profile.png")
        self.write_tool_type(self.current_tool, "rtp_profile")

    def on_tt_rear_tp_rh_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_rh_profile.png")
        self.write_tool_type(self.current_tool, "rtp_rh_profile")

    def on_tt_front_tp_lh_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_lh_profile.png")
        self.write_tool_type(self.current_tool, "ftp_lh_profile")

    def on_tt_front_tp_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_profile.png")
        self.write_tool_type(self.current_tool, "ftp_profile")

    def on_tt_front_tp_rh_profile_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_rh_profile.png")
        self.write_tool_type(self.current_tool, "ftp_rh_profile")

    def on_tt_rear_tp_lh_turn_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_lh_turn.png")
        self.write_tool_type(self.current_tool, "rtp_lh_turn")

    def on_tt_front_tp_lh_turn_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_lh_turn.png")
        self.write_tool_type(self.current_tool, "ftp_lh_turn")

    def on_tt_rear_tp_turn_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_turn.png")
        self.write_tool_type(self.current_tool, "rtp_turn")

    def on_tt_front_tp_turn_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_turn.png")
        self.write_tool_type(self.current_tool, "ftp_turn")

    def on_tt_rear_tp_thread_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_thread.png")
        self.write_tool_type(self.current_tool, "rtp_thread")

    def on_tt_front_tp_thread_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_thread.png")
        self.write_tool_type(self.current_tool, "ftp_thread")

    def on_tt_rear_tp_part_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_part.png")
        self.write_tool_type(self.current_tool, "rtp_part")

    def on_tt_front_tp_part_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_part.png")
        self.write_tool_type(self.current_tool, "ftp_part")

    def on_tt_center_drill_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("center_drill_chuck.png")
        self.write_tool_type(self.current_tool, "center_drill")

    def on_tt_rear_boring_bar_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_boring_bar.png")
        self.write_tool_type(self.current_tool, "rtp_boring_bar")

    def on_tt_front_boring_bar_eventbox_button_press_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_boring_bar.png")
        self.write_tool_type(self.current_tool, "ftp_boring_bar")

    def on_tt_rear_id_thread_eventbox_button_release_event(self, widget, data=None):
        self.clear_tool_select_images("rtp_id_thread.png")
        self.write_tool_type(self.current_tool, "rtp_id_thread")

    def on_tt_front_id_thread_eventbox_button_release_event(self, widget, data=None):
        self.clear_tool_select_images("ftp_id_thread.png")
        self.write_tool_type(self.current_tool, "ftp_id_thread")

    @staticmethod
    def get_offset_tool_type_image(tool_type):
        if tool_type == 'center_drill': tool_type += '_chuck'
        return tool_type + '.png'

    def on_notebook_switch_page(self, notebook, page, page_num):
        TormachUIBase.on_notebook_switch_page(self,notebook, page, page_num)

        page = notebook.get_nth_page(page_num)
        page_id = gtk.Buildable.get_name(page)

        if page_id == 'notebook_offsets_fixed':
            if self.pn_data is None: self.pn_data = lathe_fs.LathePnData(self)
            tool_type = self.get_tool_type(self.current_tool)
            # set this proactively, because the turret_fwd button gets focus on page switch, preventing
            # the dro from updating.
            self.dro_list['tool_dro'].set_text(self.dro_short_format % self.current_tool)
            nose_radius = ( 0.5 * self.status.tool_table[self.current_tool].diameter)
            tip_orient = self.status.tool_table[self.current_tool].orientation
            self.clear_tool_select_images(lathe.get_offset_tool_type_image(tool_type), True)
            # prevent highlighting of tool dro on page switch
            self.dro_list['tool_dro'].select_region(0, 0)
            # clear touch off LEDs if tool has no offset
            self.set_touch_x_z_leds(self.current_tool)
            self.refresh_tool_liststore()
            self.window.set_focus(None)

        if page_id == 'conversational_fixed':
            self.profile_renderer.update()
            self.profile_set_tool_data()
            self.load_title_dro()
            self._update_tool_error(('allow_empty','validate_fs'))
            self.update_chip_load_hint(self.get_current_conv_notebook_page_id())

            self.thread_custom_file_reload_if_changed()

            if self.g21:
                self.conv_rough_sfm_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >roughing    mpm:</span>')
                self.conv_finish_sfm_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >finishing    mpm:</span>')

                self.conv_rough_fpr_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >roughing    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >mm/rev</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" > :</span>')
                self.conv_finish_fpr_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >finishing    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >mm/rev</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" > :</span>')

                self.tap_pitch_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >Pitch    (mm)    :</span>')
                self.tap_tpu_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >Threads/mm    :</span>')
                self.conv_thread_calc_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >threads/mm    :</span>')
                self.conv_thread_pitch_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >pitch    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >(mm)</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" > :</span>')

                self.thread_chart_combobox.set_model(self.thread_chart_g21_liststore)

            else:
                self.conv_rough_sfm_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >roughing    sfm:</span>')
                self.conv_finish_sfm_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >finishing    sfm:</span>')

                self.conv_rough_fpr_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >roughing    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >in/rev</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >   :</span>')
                self.conv_finish_fpr_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >finishing    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >in/rev</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >   :</span>')

                self.tap_pitch_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >Pitch     (inches)    :</span>')
                self.tap_tpu_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >Threads/inch    :</span>')
                self.conv_thread_calc_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >threads/inch    :</span>')
                self.conv_thread_pitch_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >pitch    </span><span weight="light" font_desc="Bebas 10" font_stretch="ultracondensed" foreground="white" >(inch)</span><span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" > :</span>')

                self.thread_chart_combobox.set_model(self.thread_chart_g20_liststore)

            self.window.set_focus(None)

    def on_offsets_notebook_switch_page(self, notebook, page, page_num):
        offsets_table_page_num = 1
        if page_num == offsets_table_page_num:
            self.refresh_tool_liststore()

    def update_chip_load_hint(self, typ='drill_tap_fixed'):
        if typ != 'drill_tap_fixed' or self.conv_drill_tap != 'drill':
            self.chip_load_hint.set_visible(False)
            return
        self.chip_load_hint.set_visible(True)
        flutes, cl, scl = self.fs_mgr.current_chipload()
        markup_str = '<span font_desc="Roboto Condensed 9" foreground="white">(Flutes: %d   Chip load per flute: %s)</span>'
        self.chip_load_hint.set_markup(markup_str % (flutes,self.dro_long_format) % (cl))

    def _test_on_activate_tool_dro(self, widget):
#       tool_number,err = self.test_valid_tool(widget, ('report_error','validate_fs',))
        tool_number,err = self.test_valid_tool(widget, ('report_error',))
        return not err

    def _get_min_max_tool_numbers(self):
        return (self.__class__._min_tool_number, self.__class__._max_tool_number)

    def _get_tool_dro_from_page_id(self, page_id):
        if page_id == 'od_turn_fixed':       return self.tool_dros['odturn']
        elif page_id == 'id_turn_fixed':     return self.tool_dros['idturn'][self.conv_id_basic_ext]
        elif page_id == 'profile_fixed':     return self.tool_dros['profile']
        elif page_id == 'face_fixed':        return self.tool_dros['face']
        elif page_id == 'chamfer_fixed':     return self.tool_dros['chamfer'][self.conv_chamfer_radius][self.conv_chamfer_od_id]
        elif page_id == 'groove_part_fixed': return self.tool_dros['groove_part'][self.conv_groove_part]
        elif page_id == 'drill_tap_fixed':   return self.tool_dros['drill_tap'][self.conv_drill_tap]
        elif page_id == 'thread_fixed':      return self.tool_dros['thread']
        return None

    def _update_tool_error(self, actions=('',)):
        # gets called when conversational page is switched into...
        page_id = self.get_current_conv_notebook_page_id()
        tool_dro = self._get_tool_dro_from_page_id(self.get_current_conv_notebook_page_id())
        tool_number,err = self.test_valid_tool(tool_dro, actions)

    def _get_current_tool_dro(self):
        page_id = get_notebook_page_id(self.conv_notebook, self.conv_notebook.get_current_page())
        return self._get_tool_dro_from_page_id(page_id)

    def get_current_dro_info(self, page_id=None):
        if not page_id: page_id = get_notebook_page_id(self.conv_notebook, self.conv_notebook.get_current_page())
        page = self.conv_page_dros[page_id]
        rv = page['dros']
        try:
            if   page_id == 'id_turn_fixed' and self.conv_id_basic_ext != 'basic':    rv = page['turn_dros']
            elif page_id == 'groove_part_fixed'and self.conv_groove_part != 'groove': rv = page['part_dros']
            elif page_id == 'drill_tap_fixed' and self.conv_drill_tap != 'drill':     rv = page['tap_dros']
            elif page_id == 'chamfer_fixed':
                if self.conv_chamfer_radius != 'chamfer': rv = page['radius_od_dros'] if self.conv_chamfer_od_id == 'od' else page['radius_id_dros']
                elif self.conv_chamfer_od_id != 'od': rv = page['chamfer_id_dros']
        except AttributeError:
            self.error_handler.log('lathe.get_current_dro_info: Attribute Exception for page: {}'.format(page_id))
            # this may be called because the page_id and the 'sub' page dictated
            # by vars such as 'self.conv_profile_rect_circ' may be out of sync.
            # this routine will get called again when they are in sync
            pass
        return rv

    def _conversational_notebook_switch_page(self, conv_page_num ):
        page_id = get_notebook_page_id(self.conv_notebook, conv_page_num)
        self.save_title_dro()
        self.load_title_dro(page_id)
        self.update_chip_load_hint(page_id)
        self.fs_mgr.clr_calced_dros()

        if 'od_turn_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)

        elif 'id_turn_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)

        elif 'profile_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)
            self._set_profile_defaults()
            self.profile_set_tool_data()
            self.profile_set_finish_image()

        elif 'face_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)

        elif 'chamfer_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)

        elif 'groove_part_fixed' == page_id:  # Groove/Part button should also set these
            if self.conv_groove_part == 'groove':
                self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(True)
                self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
                self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
                self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
                self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)
            else:   # self.conv_groove_part == 'part':
                self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
                self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(False)
                self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(True)
                self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(True)
                self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(True)

        elif 'drill_tap_fixed' == page_id:  # Settings for Drill, Drill/Tap button should set Tap
            if self.conv_drill_tap == 'drill':
                self._update_drill_through_hole_hint_label(self.drill_dro_list['drill_tool_num_dro'].get_text(),
                                                           self.drill_dro_list['drill_z_end_dro'].get_text(),
                                                           self.drill_through_hole_hint_label)

                self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
                self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
                self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(False)
                self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(False)
                self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(False)
            else:  # self.conv_drill_tap == 'tap':
                self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
                self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(False)
                self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(False)
                self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(False)
                self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(False)

        elif 'thread_fixed' == page_id:
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(False)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(False)
            self.conv_dro_list['conv_max_spindle_rpm_dro'].set_sensitive(False)

    # startup actions for each conversational page, such as graying out DROs that don't apply
    def on_conversational_notebook_switch_page(self, notebook, page, conv_page_num ):
        self._conversational_notebook_switch_page(conv_page_num)


    def on_reset_tool_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.clear_tool_select_images('none.png')

        # get rid of call to write tool type saves two MDI and wait_complete - noticeably faster
        #self.write_tool_type(self.status.tool_in_spindle, 'none')
        wear_offset_register = self.status.tool_in_spindle
        self.set_tool_description(wear_offset_register, "")
        geo_offset_register = wear_offset_register + 10000
        # no Y wear offset for RapidTurn
        g10_command = "G10 L1 P%d X%f Z%f I%d R%f J%d Q%d" %(wear_offset_register, 0.0, 0.0, 0, NOSE_RADIUS_STANDARD, 0, 9)
        self.issue_mdi(g10_command)
        # wait_complete is needed to prevent next offset command from stepping on previous one
        self.command.wait_complete()
        # clear out geometery offsets
        if self.machineconfig.in_rapidturn_mode():
          # include Y offset
          g10_command = "G10 L1 P%d X%f Y%f Z%f I%d" %(geo_offset_register, 0.0, 0.0, 0.0, 0)
        else:
          g10_command = "G10 L1 P%d X%f Z%f I%d" %(geo_offset_register, 0.0, 0.0, 0)
        self.issue_mdi(g10_command)
        self.set_image('touch_z_image', 'touch_z_black_led.png')
        self.set_image('touch_x_image', 'touch_x_black_led.png')
        self.dro_list['touch_dia_dro'].set_text("")
        self.dro_list['touch_z_dro'].set_text("")
        # set values in offsets table.  liststore starts at entry 0
        row = wear_offset_register - 1
        self.tool_liststore[row][1] = None
        self.tool_liststore[row][2] = self.dro_long_format % 0
        self.tool_liststore[row][3] = self.dro_long_format % 0
        self.tool_liststore[row][4] = self.dro_long_format % 0
        self.tool_liststore[row][5] = self.dro_long_format % 0
        self.tool_liststore[row][6] = self.dro_long_format % 0
        self.tool_liststore[row][7] = self.dro_long_format % NOSE_RADIUS_STANDARD
        self.tool_liststore[row][8] = 0
        self.tool_liststore[row][9] = BLACK
        self.tool_liststore[row][10] = BLACK

    def on_touch_z_dro_activate(self, widget, data=None):
        valid, dro_val, error_msg = self.conversational.validate_z_point(self.dro_list['touch_z_dro'])
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        self.dro_list['touch_z_dro'].set_text(self.dro_long_format % dro_val)
        self.set_image('touch_z_image', 'touch_z_highlight.png')
        # next line not working as it should.
        self.button_list['touch_z'].grab_focus()

    def on_touch_z_button_release_event(self, widget, data=None):
        self.notebook_tool_fixed.move(self.button_list['touch_z'], self.button_list['touch_z'].x, self.button_list['touch_z'].y)
        valid, dro_val, error_msg = self.conversational.validate_z_point(self.dro_list['touch_z_dro'])
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        # the G10 command wants values in mm if G21, but actual_postion and g5x_offsets are in machine units (in.)
        # so we take the sup value and turn it into machine units, then send the offset command in g20/21 units
        supplemental_offset = dro_val / self.mm_inch_scalar
        wear_offset_register = self.status.tool_in_spindle
        geo_offset_register = wear_offset_register + 10000
        z_offset = self.status.actual_position[2] - self.status.g5x_offset[2] - supplemental_offset
        z_offset = z_offset * self.mm_inch_scalar
        # clear wear offsets for this tool
        self.issue_g10('Z', wear_offset_register, 0.0)
        self.issue_g10('Z', geo_offset_register, z_offset)
        self.dro_list['touch_z_dro'].set_text(self.dro_long_format % dro_val)

    def on_touch_z_key_press_event(self, widget, event):
        # Return or Enter key valid.  couldn't find keysyms constant for Enter key.
        if event.keyval == gtk.keysyms.Return or event.keyval == 65421:
            self.on_touch_z_button_release_event(self, widget)
            self.window.set_focus(None)
        elif event.keyval == gtk.keysyms.Escape:
            self.set_image('touch_z_image', 'touch_z_black_led.png')
            self.window.set_focus(None)
        return True


    def on_touch_dia_dro_activate(self, widget, data=None):
        valid, dro_val, error_msg = self.conversational.validate_dia_val(self.dro_list['touch_dia_dro'])
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        self.dro_list['touch_dia_dro'].set_text(self.dro_long_format % dro_val)
        self.set_image('touch_x_image', 'touch_x_highlight.png')
        self.button_list['touch_x'].grab_focus()

    def on_touch_x_button_release_event(self, widget, data=None):
        self.notebook_tool_fixed.move(self.button_list['touch_x'], self.button_list['touch_x'].x, self.button_list['touch_x'].y)
        wear_offset_register = self.status.tool_in_spindle
        geo_offset_register = wear_offset_register + 10000
        valid, dro_val, error_msg = self.conversational.validate_dia_val(self.dro_list['touch_dia_dro'])
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        # convert supplemental offset to machine units
        supplemental_dia_offset = dro_val / self.mm_inch_scalar
        # tool offset should be machine pos - work offset, with adjustment for dia offset in radius meas.
        x_offset = (self.status.actual_position[0] - self.status.g5x_offset[0] - (supplemental_dia_offset / 2))
        # offset command needs to be in current g20/21 units, so convert back.
        x_offset = x_offset * self.mm_inch_scalar * 2
        # clear out wear offset register
        self.issue_g10('X', wear_offset_register, 0.0)
        # set geometery offsets
        self.issue_g10('X', geo_offset_register, x_offset)
        self.dro_list['touch_dia_dro'].set_text(self.dro_long_format % dro_val)
        # complain if negative for a front tool post tool
        tool_type = self.get_tool_type(wear_offset_register)
        if 'ftp' in tool_type:
            if not 'id' in tool_type:
                if dro_val > 0:
                    self.error_handler.write("Warning: Diameter touch off for front tool post tools should be expressed as negative values.", ALARM_LEVEL_LOW)

    def on_touch_x_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Return or event.keyval == 65421:
            self.on_touch_x_button_release_event(self, widget)
            self.window.set_focus(None)
        elif event.keyval == gtk.keysyms.Escape:
            self.set_image('touch_x_image', 'touch_x_black_led.png')
            self.window.set_focus(None)
        return True

    def on_touch_dia_dro_gets_focus(self, widget, data=None):
        if self.moving(): return
        self.set_image('touch_x_image', 'touch_x_black_led.png')
        widget.masked = True
        if self.settings.touchscreen_enabled:
            keypad = numpad.numpad_popup(self.window, widget)
            keypad.run()
            self.window.set_focus(None)
            return True

    def on_export_tool_table_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.export_tooltable()

    def on_import_tool_table_button_release_event(self, widget, data=None):
        if not self.is_button_permitted(widget): return
        self.import_tooltable()

    def on_touch_z_dro_gets_focus(self, widget, data=None):
        if self.moving(): return
        self.set_image('touch_z_image', 'touch_z_black_led.png')
        widget.masked = True
        if self.settings.touchscreen_enabled:
            keypad = numpad.numpad_popup(self.window, widget)
            keypad.run()
            self.window.set_focus(None)
            return True

    def on_turret_fwd_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        valid, tool_number, err_msg = self.conversational.validate_tool_number(self.dro_list['tool_dro'])
        #only use the value from the DRO if the DRO or turret_fwd button is highlighted and the tool number is different than what's in the spindle
        use_dro = (self.button_list['turret_fwd'].has_focus() or self.dro_list['tool_dro'].masked) and valid and tool_number != self.status.tool_in_spindle
        if not valid:
            self.error_handler.write(err_msg, ALARM_LEVEL_LOW)
            return
        if not use_dro:
            tool_number=self.status.tool_in_spindle
            tool_number += 1
            if tool_number > self.hal['turret-positions']:
                tool_number = 1
        self.issue_toolchange_command(tool_number)
        self.set_image('turret_fwd_image', 'turret-FWD.png')
        self.window.set_focus(None)

    def on_turret_fwd_key_press_event(self, widget, event):
        if event.keyval == gtk.keysyms.Return or event.keyval == 65421:
            valid, tool_number, err_msg = self.conversational.validate_tool_number(self.dro_list['tool_dro'])
            if not valid:
                self.error_handler.write(err_msg, ALARM_LEVEL_LOW)
                return
            self.issue_toolchange_command(tool_number)
            self.set_image('turret_fwd_image', 'turret-FWD.png')
            self.window.set_focus(None)
        elif event.keyval == gtk.keysyms.Escape:
            self.set_image('turret_fwd_image', 'turret-FWD.png')
            self.window.set_focus(None)
        return True



    def on_tool_dro_activate(self, widget):
        # get DRO value
        valid, tool_number, err_msg = self.conversational.validate_tool_number(widget)
        if not valid:
            self.error_handler.write(err_msg, ALARM_LEVEL_LOW)
            return
        # if we're using a turret changer, prelight 'turret_FWD' button if the requested tool is in the turret
        if self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_TURRET:
            if tool_number <= self.hal['turret-positions']:
                # tool is 1 to n inclusive for turret, so prelight turret_fwd
                self.set_image('turret_fwd_image', 'turret-FWD-highlighted.png')
                self.button_list['turret_fwd'].grab_focus()
                return
            '''elif tool_number > 99 and tool_number < 10000:
                if math.floor(tool_number) < 9:
                    # calls with wear offsets - e.g. t0202
                    self.set_image('turret_fwd_image', 'turret-FWD-highlighted.png')
                    self.button_list['turret_fwd'].grab_focus()
                    return'''

        self.issue_toolchange_command(tool_number)
        self.window.set_focus(None)


    # wear offsets, nose radius, and tip orient table callbacks

    def tool_table_rows(self):
        return MAX_LATHE_TOOL_NUM

    def on_tool_description_column_edited(self, cell, row, tool_description, model, data=None):
        tool_number = int(row) + 1
        model[row][1] = tool_description
        self.set_tool_description(tool_number, tool_description)
        if data is not None:
            if 'proc' in data:
                # add a 'norefresh' so the entire tool table does not get
                # refreshed because we are only doing one row...
                data['cmd'] = ['norefresh']
                data['proc'](tool_description, data)


    def on_x_geo_offset_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_x_geo_offset_col_keypress, row)

    def on_x_geo_offset_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.z_geo_offset_column, True)
        return False

    def on_x_geo_offset_col_edited(self, cell, row, value, model):
        valid, value, error_msg = self.conversational.validate_wear_offset(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        geo_offset_register = int(row) + 1 + 10000
        self.issue_g10('X', geo_offset_register, (value))
        model[row][2] = self.dro_long_format % value

    def on_y_geo_offset_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_y_geo_offset_col_keypress, row)

    def on_y_geo_offset_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.z_geo_offset_column, True)
        return False

    def on_y_geo_offset_col_edited(self, cell, row, value, model):
        valid, value, error_msg = self.conversational.validate_wear_offset(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        geo_offset_register = int(row) + 1 + 10000
        self.issue_g10('Y', geo_offset_register, (value))
        model[row][3] = self.dro_long_format % value

    def on_z_geo_offset_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_z_geo_offset_col_keypress, row)

    def on_z_geo_offset_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.x_wear_offset_column, True)
        return False

    def on_z_geo_offset_col_edited( self, cell, row, value, model ):
        valid, value, error_msg = self.conversational.validate_wear_offset(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        geo_offset_register = int(row) + 1 + 10000
        self.issue_g10('Z', geo_offset_register, (value))
        model[row][4] = self.dro_long_format % value


    def on_x_offset_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_x_offset_col_keypress, row)

    def on_x_offset_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.z_wear_offset_column, True)
        return False

    def on_x_offset_col_edited(self, cell, row, value, model):
        valid, value, error_msg = self.conversational.validate_wear_offset(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        wear_offset_register = int(row) + 1
        tool_number = wear_offset_register
        tool_type = self.get_tool_type(tool_number)
        text_color = self.find_wear_offset_display_color(value, tool_type)
        # LCNC wants a neg value
        self.issue_g10('X', wear_offset_register, (value))
        model[row][5] = self.dro_long_format % value
        model[row][9] = text_color


    def on_z_offset_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_z_offset_col_keypress, row)

    def on_z_offset_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.tool_nose_rad_column, True)
        return False

    def on_z_offset_col_edited( self, cell, row, value, model ):
        valid, value, error_msg = self.conversational.validate_wear_offset(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        wear_offset_register = int(row) + 1
        self.issue_g10('Z', wear_offset_register, (value))
        model[row][6] = self.dro_long_format % value
        if value > 0.00009:
            text_color = ORANGE
        elif value < -0.00001:
            text_color = BLUE
        else:
            text_color = BLACK
        model[row][10] = text_color


    def on_nose_radius_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_nose_radius_col_keypress, row)

    def on_nose_radius_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.tool_table_update_focus, row, self.tool_tip_orient_column, True)
        return False

    def on_nose_radius_col_edited( self, cell, row, value, model, data=None):
        valid, value, error_msg = self.conversational.validate_nose_radius(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        wear_offset_register = int(row) + 1
        if data is None or 'cmd' not in data or 'no_g10' not in data['cmd']: self.issue_g10('R', wear_offset_register, (value), data)
        model[row][7] = self.dro_long_format % value
        glib.idle_add(self.tool_table_update_observer,row)

    def on_tip_orient_col_editing_started(self, renderer, editable, path):
        # upon entering this cell, capture the context and setup what to do and where to go next
        if path == '':
            row = 0
        else:
            row = int(path)
        # capture key press to determine next cell to edit
        editable.connect("key-press-event", self.on_tip_orient_col_keypress, row)

    def on_tip_orient_col_keypress(self, widget, ev, row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            # move to the next row's tool description, but don't immediately go into editing mode.
            # less annoying this way, but easy to move into editing mode purely by keyboard with an enter key.
            glib.idle_add(self.tool_table_update_focus, row + 1, self.tool_description_column, False)
        return False

    def on_tip_orient_col_edited( self, cell, row, value, model, data=None ):
        valid, value, error_msg = self.conversational.validate_tip_orientation(value)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        wear_offset_register = int(row) + 1
        # can't use issue_g10 here because lcnc wants an int for the Q word
        g10_command = "G10 L1 P%d Q%d" %(wear_offset_register, int(value))
        if not isinstance(data,dict) or 'cmd' not in data or 'g10' in data['cmd']: self.issue_mdi(g10_command)
        model[row][8] = int(value)
        glib.idle_add(self.tool_table_update_observer,row)


    def clear_tool_select_images(self, image, supress_error=False):
        # supress error message on notebook page switch
        if not supress_error:
            if self.status.tool_in_spindle == 0:
                self.error_handler.write("Must select valid tool before setting tool parameters", ALARM_LEVEL_LOW)
                return

        # if the tool has no type yet, display the splash screen controls and hide the tool table
        if image == 'none.png':
            splash = True
            image = 'chuck.png'
        else:
            splash = False

        # prevent/allow eventboxes from receiving events depending whether we are in splash screen or touch-off screen
        for name, eventbox in self.tool_touch_eventbox_list.iteritems():
            eventbox.set_sensitive(splash)
            # fix problem where center drill image grabbed touch_x button click events
            eventbox.set_visible(splash)

        if self.machineconfig.in_rapidturn_mode():
            for name, eventbox in self.tool_touch_eventbox_list.iteritems():
                if ('front' in name) and not (('boring' in name) or ('id' in name)):
                    eventbox.set_sensitive(False)

        self.button_list['reset_tool'].set_sensitive(not splash)

        # change to appropriate background image
        self.set_image('tool_touch_chuck', image)

        # show or hide images and dros
        if splash:
            self.button_list['reset_tool'].hide()
            self.image_list['reset_tool_image'].hide()
            if not self.machineconfig.in_rapidturn_mode(): self.ftp_text.show()
            self.rtp_text.show()
            for name, image in self.tool_image_list.iteritems():
                if self.machineconfig.in_rapidturn_mode():
                    if ('front' in name) and not (('boring' in name) or ('id' in name)):
                        image.hide()
                        continue
                image.show()
        else:
            self.button_list['reset_tool'].show()
            self.image_list['reset_tool_image'].show()
            for name, image in self.tool_image_list.iteritems():
                image.hide()





    # -------------------------------------------------------------------------------------------------
    # conversational tab callbacks
    # -------------------------------------------------------------------------------------------------

    # generate gcode helper

    def generate_gcode(self, page_id=None):
        try:
            # NOTE!  The actual child object id="" attribute from the glade file is used to
            # uniquely identify each notebook page and to figure out which is the current page.
            # Do NOT add any text label comparisons.
            # NOTE! param: 'page_id' if not None will be the correct id from the current
            # step in 'Conv-Edit' requesting a re-generation.
            active_child_id = page_id if page_id else self.get_current_conv_notebook_page_id()

            valid = False

            ini_file_name = sys.argv[2]
            inifile = linuxcnc.ini(ini_file_name)

            valid = False
            if 'od_turn_fixed' == active_child_id:
                (valid, gcode_output_list) = self.conversational.generate_od_turn_code(self.conv_dro_list, self.od_turn_dro_list)
                self.save_conv_parameters(self.od_turn_dro_list)

            elif 'id_turn_fixed' == active_child_id:
                if self.conv_id_basic_ext == "basic":
                    (valid, gcode_output_list) = self.conversational.generate_id_basic_code(self.conv_dro_list, self.id_basic_dro_list)
                    self.save_conv_parameters(self.id_basic_dro_list)
                else:
                    (valid, gcode_output_list) = self.conversational.generate_id_turn_code(self.conv_dro_list, self.id_turn_dro_list)
                    self.save_conv_parameters(self.id_turn_dro_list)

            elif 'profile_fixed' == active_child_id:
                (valid, gcode_output_list) = self.conversational.generate_profile_code()
                self.profile_update_tool_geometries()
                self.save_conv_parameters(self.profile_dro_list)

            elif 'face_fixed' == active_child_id:
                (valid, gcode_output_list) = self.conversational.generate_face_code(self.conv_dro_list, self.face_dro_list)
                self.save_conv_parameters(self.face_dro_list)

            elif 'chamfer_fixed' == active_child_id:
                if self.conv_chamfer_radius == "chamfer":
                    if self.conv_chamfer_od_id == 'od':
                        (valid, gcode_output_list) = self.conversational.generate_chamfer_code(self.conv_dro_list, self.corner_chamfer_od_dro_list, self.conv_chamfer_od_id)
                        self.save_conv_parameters(self.corner_chamfer_od_dro_list)
                    else:  # self.conv_chamfer_od_id == 'id'
                        (valid, gcode_output_list) = self.conversational.generate_chamfer_code(self.conv_dro_list, self.corner_chamfer_id_dro_list, self.conv_chamfer_od_id)
                        self.save_conv_parameters(self.corner_chamfer_id_dro_list)
                else:  # self.conv_chamfer_radius == "radius"
                    if self.conv_chamfer_od_id == 'od':
                        (valid, gcode_output_list) = self.conversational.generate_radius_code(self.conv_dro_list, self.corner_radius_od_dro_list, self.conv_chamfer_od_id)
                        self.save_conv_parameters(self.corner_radius_od_dro_list)
                    else:  # self.conv_chamfer_od_id == 'id'
                        (valid, gcode_output_list) = self.conversational.generate_radius_code(self.conv_dro_list, self.corner_radius_id_dro_list, self.conv_chamfer_od_id)
                        self.save_conv_parameters(self.corner_radius_id_dro_list)

            elif 'groove_part_fixed' == active_child_id:
                if self.conv_groove_part == "groove":
                    (valid, gcode_output_list) = self.conversational.generate_groove_code(self.conv_dro_list, self.groove_dro_list, inifile)
                    self.save_conv_parameters(self.groove_dro_list)
                else:
                    (valid, gcode_output_list) = self.conversational.generate_part_code(self.conv_dro_list, self.part_dro_list, inifile)
                    self.save_conv_parameters(self.part_dro_list)

            elif 'drill_tap_fixed' == active_child_id:
                if self.conv_drill_tap == "drill":
                    (valid, gcode_output_list) = self.conversational.generate_drill_code(self.conv_dro_list, self.drill_dro_list)
                    self.save_conv_parameters(self.drill_dro_list)
                else:
                    pitch = self.tap_dro_list['tap_pitch_dro'].get_text()
                    max_vel = self.inifile.find("AXIS_2", "MAX_VELOCITY")
                    (valid, gcode_output_list) = self.conversational.generate_tap_code(self.conv_dro_list,
                                                                                       self.tap_dro_list,
                                                                                       pitch,
                                                                                       max_vel)
                    self.save_conv_parameters(self.tap_dro_list)

            elif 'thread_fixed' == active_child_id:
                pitch = self.thread_dro_list['thread_pitch_dro'].get_text()
                max_vel = self.inifile.find("AXIS_2", "MAX_VELOCITY")
                (valid, gcode_output_list) = self.conversational.generate_thread_code(self.conv_dro_list,
                                                                                      self.thread_dro_list,
                                                                                      self.conv_thread_ext_int,
                                                                                      inifile,
                                                                                      self.conv_thread_note,
                                                                                      pitch,
                                                                                      max_vel)
                self.save_conv_parameters(self.thread_dro_list)

            return valid, gcode_output_list

        except Exception:
            ex = sys.exc_info()
            # wrap this just in case something dies trying to log it.
            try:
                self.error_handler.write(ex[1].message, ALARM_LEVEL_HIGH)
            except:
                pass
            # Re-raising the exception this way preserves the original call stack so things are logged perfectly
            # with the root cause of the exception easily logged vs. the line number of this raise.
            raise ex[0], ex[1], ex[2]


    # -------------------------------------------------------------------------------------------------
    # general setting DROs and "post to file/mdi" callbacks
    # -------------------------------------------------------------------------------------------------


    def on_post_to_file_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)

        # generate the code
        valid, gcode_output_list = self.generate_gcode()
        if valid:
            self.save_title_dro()
            self.post_to_file(self.window, self.conv_dro_list['conv_title_dro'].get_text(), gcode_output_list,
                              query=True, load_file=True, closewithoutsavebutton=False)


    def on_append_to_file_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)

        # generate the code:
        valid, gcode_output_list = self.generate_gcode()
        if not valid or not any(gcode_output_list):
            return

        path = self.last_used_save_as_path + os.path.sep
        dialog = tormach_file_util.append_to_file_popup(self.window, path)
        dialog.run()

        response = dialog.response
        self.last_used_save_as_path = dialog.current_directory
        path = dialog.get_path()

        if response == gtk.RESPONSE_OK:
            self._update_append_file(path, gcode_output_list)

        dialog.destroy()

    def on_conv_title_dro_gets_focus(self, widget, data=None):
        if self.settings.touchscreen_enabled:
            keypad = numpad.numpad_popup(self.window, widget, True)
            keypad.run()
            self.window.set_focus(None)
            return True

    def on_conv_dro_gets_focus(self, widget, data=None):
        # really the button release event
        widget.prev_val = widget.get_text()
        widget.select_region(0, -1)
        if self.settings.touchscreen_enabled:
            keypad = numpad.numpad_popup(self.window, widget)
            keypad.run()
            widget.select_region(0, 0)
            self.window.set_focus(None)

    def on_conv_dro_focus_in_event(self, widget, data=None):
        widget.prev_val = widget.get_text()

    def on_entry_loses_focus(self, widget, data=None):
        # get rid of text highlight if you click out of a dro that has highlighted text
        widget.select_region(0, 0)
        return False


    # focus passing for conversational common DROs
    def on_conv_title_dro_activate(self, widget, data=None):
        self.conv_title = widget.get_text()
        self.conv_dro_list['conv_work_offset_dro'].grab_focus()

    def on_conv_work_offset_dro_activate(self, widget, data=None):
        (valid, work_offset, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(work_offset)
        active_child_id = self.get_current_conv_notebook_page_id()
        next_dro = self.conv_dro_list['conv_rough_sfm_dro']
        if "drill_tap_fixed" == active_child_id:
            next_dro = self.conv_dro_list['conv_rough_fpr_dro'] if self.conv_drill_tap == 'drill' else self.tap_dro_list['tap_tool_num_dro']
        elif 'thread_fixed' == active_child_id:
            next_dro = self.thread_dro_list['thread_tool_num_dro']
        elif "groove_part_fixed" == active_child_id:
            if self.conv_groove_part == 'part': next_dro = self.conv_dro_list['conv_finish_sfm_dro']
        next_dro.grab_focus()

    def on_conv_rough_sfm_dro_activate(self, widget, data=None):
        (valid, surface_speed, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget,self.dro_short_format % surface_speed)
        self.conv_dro_list['conv_finish_sfm_dro'].grab_focus()
        return

    def on_conv_finish_sfm_dro_activate(self, widget, data=None):
        (valid, surface_speed, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget,self.dro_short_format % surface_speed)
        self.conv_dro_list['conv_max_spindle_rpm_dro'].grab_focus()
        return

    def on_conv_max_spindle_rpm_dro_activate(self, widget, data=None):
        (valid, max_rpm, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget,self.dro_short_format % max_rpm)
        next_dro = self.conv_dro_list['conv_rough_fpr_dro']
        active_child_id = self.get_current_conv_notebook_page_id()
        if "groove_part_fixed" == active_child_id:
            if self.conv_groove_part == 'part': next_dro = self.conv_dro_list['conv_finish_fpr_dro']
        next_dro.grab_focus()

    def on_conv_rough_fpr_dro_activate(self, widget, data=None):
        (valid, feedrate, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % feedrate)
        next_dro = self.conv_dro_list['conv_finish_fpr_dro']
        active_child_id = self.get_current_conv_notebook_page_id()
        if "drill_tap_fixed" == active_child_id:
            if self.conv_drill_tap == 'drill': next_dro = self.drill_dro_list['drill_tool_num_dro']
            self.update_chip_load_hint()
        next_dro.grab_focus()

    def on_conv_finish_fpr_dro_activate(self, widget, data=None):
        (valid, feedrate, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % feedrate)

        # NOTE!  The actual child object id="" attribute from the glade file is used to
        # uniquely identify each notebook page and to figure out which is the current page.
        # Do NOT add any text label comparisons.
        active_child_id = self.get_current_conv_notebook_page_id()
        next_dro = self.conv_dro_list['conv_title_dro']

        if 'od_turn_fixed' == active_child_id: next_dro = self.od_turn_dro_list['od_turn_tool_num_dro']
        elif 'id_turn_fixed' == active_child_id:
            next_dro = self.id_basic_dro_list['id_basic_tool_num_dro'] if self.conv_id_basic_ext == 'basic' else self.id_turn_dro_list['id_turn_tool_num_dro']
        elif 'face_fixed' == active_child_id: next_dro = self.face_dro_list['face_tool_num_dro']
        elif 'profile_fixed' == active_child_id: next_dro = self.profile_dro_list['profile_tool_num_dro']
        elif 'chamfer_fixed' == active_child_id:
            if self.conv_chamfer_radius == 'chamfer':
                next_dro = self.corner_chamfer_od_dro_list['corner_chamfer_od_tool_num_dro'] if self.conv_chamfer_od_id == 'od' else self.corner_chamfer_id_dro_list['corner_chamfer_id_tool_num_dro']
            else:
                next_dro = self.corner_radius_od_dro_list['corner_radius_od_tool_num_dro'] if self.conv_chamfer_od_id == 'od' else self.corner_radius_id_dro_list['corner_radius_id_tool_num_dro']
        elif "groove_part_fixed" == active_child_id:
            next_dro = self.groove_dro_list['groove_tool_num_dro'] if self.conv_groove_part == 'groove' else self.part_dro_list['part_tool_num_dro']
        next_dro.grab_focus()

    def next_conv_dro(self, conv_list, conv_from):
        conv_list_len = len(conv_list)
        for n in range(conv_list_len):
            if conv_list[n] == conv_from:
                return conv_list[n+1] if (n+1) < conv_list_len else conv_list[0]
        return 'nowhere'
        #list_index = 0
        #go_here = 'nowhere'
        #for list_id in conv_list:
            #if list_id == conv_from:
                #if list_index >= conv_count - 1:  # wrap to the beginning of list
                    #go_here = conv_list[0]
                    #break
                #else:
                    #go_here =  conv_list[list_index + 1]
                    #break
            #list_index += 1
        #return go_here

    # #################################################################################################
    # #################################################################################################
    # OD Turn DROs
    # #################################################################################################
    # #################################################################################################

    def on_od_turn_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_tool_num_dro')
        self.od_turn_dro_list[where_to].grab_focus()

    def on_od_turn_stock_dia_dro_activate(self, widget, data=None):
        (valid, dia, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % dia)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_stock_dia_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        return

    def on_od_turn_final_dia_dro_activate(self, widget, data=None):
        (valid, dia, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % dia)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_final_dia_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_z_start_dro'].grab_focus()
        return

    def on_od_turn_z_start_dro_activate(self, widget, data=None):
        (valid, z_point, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % z_point)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_z_start_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_z_end_dro'].grab_focus()
        return

    def on_od_turn_z_end_dro_activate(self, widget, data=None):
        (valid, z_point, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % z_point)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_z_end_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_fillet_dro'].grab_focus()
        return

    def on_od_turn_rough_doc_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_rough_doc_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_stock_dia_dro'].grab_focus()
        return

    def on_od_turn_finish_doc_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_finish_doc_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_rough_doc_dro'].grab_focus()
        return

    def on_od_turn_tc_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_tc_dro')
        self.od_turn_dro_list[where_to].grab_focus()
        #self.od_turn_dro_list['od_turn_finish_doc_dro'].grab_focus()
        return

    def on_od_turn_fillet_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.od_focus_list, 'od_turn_fillet_dro')
        self.od_turn_dro_list[where_to].grab_focus()

        return

    # #################################################################################################
    # #################################################################################################
    # ID Turn DROs
    # #################################################################################################
    # #################################################################################################

    def toggle_id_basic_extended_button(self):
        self.save_title_dro()
        if self.conv_id_basic_ext == 'basic':
            self.set_image('id_basic_extended_btn_image', 'id_extended_highlight.jpg')
            self.set_image('conv_id_turn_background', 'lathe_id_extended.svg')

            # turn ID Basic DROs OFF
            self.id_basic_dro_list['id_basic_tool_num_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_z_start_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_z_end_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_final_dia_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_pilot_dia_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_rough_doc_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_finish_doc_dro'].set_visible(False)
            self.id_basic_dro_list['id_basic_tc_dro'].set_visible(False)

            # turn ID Extended DROs ON
            self.id_turn_dro_list['id_turn_tool_num_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_z_start_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_z_end_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_final_dia_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_pilot_dia_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_fillet_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_pilot_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_rough_doc_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_finish_doc_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_tc_dro'].set_visible(True)
            self.id_turn_dro_list['id_turn_face_doc_dro'].set_visible(True)

            # turn ID Basic labels (text) OFF

            # turn ID Extended labels(text) ON
            self.id_turn_fillet_label.set_visible(True)
            self.id_turn_pilot_end_label.set_visible(True)
            self.id_turn_face_doc_label.set_visible(True)
            self.id_turn_tool_text1_label.set_visible(True)
            self.id_turn_roughing_label.set_visible(True)

            # these conv_DROs are also changed in on_conversational_notebook_switch_page
            #self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)

            self.conv_id_basic_ext = 'extended'

        else:
            self.set_image('id_basic_extended_btn_image', 'id_basic_highlight.jpg')
            self.set_image('conv_id_turn_background', 'lathe_id_basic.svg')

            # turn ID Extended DROs OFF
            self.id_turn_dro_list['id_turn_tool_num_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_z_start_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_z_end_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_final_dia_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_pilot_dia_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_fillet_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_pilot_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_rough_doc_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_finish_doc_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_tc_dro'].set_visible(False)
            self.id_turn_dro_list['id_turn_face_doc_dro'].set_visible(False)

            # turn ID Basic DROs ON
            self.id_basic_dro_list['id_basic_tool_num_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_z_start_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_z_end_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_final_dia_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_pilot_dia_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_rough_doc_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_finish_doc_dro'].set_visible(True)
            self.id_basic_dro_list['id_basic_tc_dro'].set_visible(True)

            # turn ID Extended labels(text) OFF
            self.id_turn_fillet_label.set_visible(False)
            self.id_turn_pilot_end_label.set_visible(False)
            self.id_turn_face_doc_label.set_visible(False)
            self.id_turn_tool_text1_label.set_visible(False)
            self.id_turn_roughing_label.set_visible(False)

            # turn ID Basic labels(text) ON
            self.conv_id_basic_ext = 'basic'
        self.load_title_dro()

    def on_id_basic_extended_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        # toggle button state between basic and extended
        self.toggle_id_basic_extended_button()


    # ID Basic DROs
    def on_id_basic_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_tool_num_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_tc_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget,self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_finish_doc_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_rough_doc_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_z_end_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_z_start_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_final_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_final_dia_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return

    def on_id_basic_pilot_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_basic_focus_list, 'id_basic_pilot_dia_dro')
        self.id_basic_dro_list[where_to].grab_focus()
        return



    # ID Extended DROs
    def on_id_turn_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_tool_num_dro')
        self.id_turn_dro_list[where_to].grab_focus()

    def on_id_turn_pilot_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_pilot_dia_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_pilot_dro'].grab_focus()
        return

    def on_id_turn_final_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_final_dia_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_pilot_dia_dro'].grab_focus()
        return

    def on_id_turn_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_z_start_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_z_end_dro'].grab_focus()
        return

    def on_id_turn_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_z_end_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_final_dia_dro'].grab_focus()
        return

    def on_id_turn_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_rough_doc_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_finish_doc_dro'].grab_focus()
        return

    def on_id_turn_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_finish_doc_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_tc_dro'].grab_focus()
        return

    def on_id_turn_tc_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_tc_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_face_doc_dro'].grab_focus()
        return

    def on_id_turn_fillet_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_fillet_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_rough_doc_dro'].grab_focus()
        return

    def on_id_turn_face_doc_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_face_doc_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_z_start_dro'].grab_focus()
        return

    def on_id_turn_pilot_dro_activate(self, widget, data=None):
        (valid, doc, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % doc)
        where_to = self.next_conv_dro(self.id_focus_list, 'id_turn_pilot_dro')
        self.id_turn_dro_list[where_to].grab_focus()
        #self.id_turn_dro_list['id_turn_fillet_dro'].grab_focus()
        #self.window.set_focus(None)
        return

    # #################################################################################################
    # #################################################################################################
    # Profile DROs
    # #################################################################################################
    # #################################################################################################

    def profile_liststore_to_list(self,action=''):
        out_list = []
        for row in self.profile_liststore:
            if action == 'compress' and not any(row[1])\
                        and not any(row[2])\
                        and not any(row[3]): continue
            out_list.append((row[0],row[1],row[2],row[3]))
        return out_list

    def list_to_profile_liststore(self, in_list):
        if in_list is None:
            return
        self.profile_liststore.clear()
        for item in in_list:
            self.profile_liststore.append([item[0],item[1],item[2],item[3]])

    def profile_set_finish_image(self):
        passes = self.profile_dro_list['profile_finish_passes_dro'].get_text()
        roughing = self.profile_dro_list['profile_roughing_doc_dro'].get_text()
        zero_str = self.dro_long_format%0.0
        if passes in ('','0'):
            self.set_image('profile_roughing_page', 'lathe_roughing_material_to_leave.svg' )
            self.builder.get_object('profile_finish_text').set_visible(False)
            self.builder.get_object('material_to_leave_text').set_visible(True)
        else:
            self.set_image('profile_roughing_page', 'lathe_finishing_page.svg')
            self.builder.get_object('profile_finish_text').set_visible(True)
            self.builder.get_object('material_to_leave_text').set_visible(False)


    def on_profile_notebook_switch_page(self, notebook, page, page_num):
        POINTS,ROUGH_FINISH,TOOL_ANGLE = range(3)
        if page_num == ROUGH_FINISH: pass

    def toggle_profile_external_internal_button(self):
        if self.conv_profile_ext == 'external':
            self.set_image('profile_ext_int_image', 'thread_int_button.jpg')
            self.conv_profile_ext = 'internal'
        else:
            self.set_image('profile_ext_int_image', 'thread_ext_button.jpg')
            self.conv_profile_ext = 'external'
        self.profile_set_tool_data()

    def on_profile_ext_int_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_profile_external_internal_button()
        self.profile_renderer.update()

    def _set_profile_defaults(self):
        if self.profile_dro_list['profile_stock_x_dro'].get_text() == '': self.profile_dro_list['profile_stock_x_dro'].set_text('25.000' if self.g21 else '1.0000')
        if self.profile_dro_list['profile_stock_z_dro'].get_text() == '': self.profile_dro_list['profile_stock_z_dro'].set_text('0.0000')
        if self.profile_dro_list['profile_roughing_tool_clear_x_dro'].get_text() == '': self.profile_dro_list['profile_roughing_tool_clear_x_dro'].set_text('27.000' if self.g21 else '1.1000')
        if self.profile_dro_list['profile_roughing_tool_clear_z_dro'].get_text() == '': self.profile_dro_list['profile_roughing_tool_clear_z_dro'].set_text('1.000' if self.g21 else '0.0500')
        if self.profile_dro_list['profile_roughing_doc_dro'].get_text() == '': self.profile_dro_list['profile_roughing_doc_dro'].set_text('0.500' if self.g21 else '0.0200')
        if self.profile_dro_list['profile_finish_doc_dro'].get_text() == '': self.profile_dro_list['profile_finish_doc_dro'].set_text('0.075' if self.g21 else '0.0030')
        if self.profile_dro_list['profile_finish_passes_dro'].get_text() == '': self.profile_dro_list['profile_finish_passes_dro'].set_text('2')
        self.profile_renderer.reset()
        self.profile_renderer.clr_hilite('no_update')

    def validate_profile_tool_angles(self, orientation, fa, ba):
        cutting_toward_spindle = orientation in [3,8,6,2]
        tool_angle1 = fa if cutting_toward_spindle else ba
        tool_angle2 = ba if cutting_toward_spindle else fa
        return tool_angle1 >= tool_angle2


    def on_profile_selection_changed(self, treeselection):
        model, selected_iter = treeselection.get_selected()
        if selected_iter is None: return
        selected_row = model.get_path(selected_iter)[0]
        last = ('','') if selected_row == 0 else (model[selected_row-1][1],model[selected_row-1][2])
        self.profile_renderer.set_hilite((model[selected_row][1],model[selected_row][2],last))
        self.dt_scroll_adjust_one(self.scrolled_window_profile_table, self.PROFILE_ROWS, selected_row)

    def on_lathe_profile_raise_in_table_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        selection = self.profile_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            return
        selected_row = model.get_path(selected_iter)[0]
        if selected_row > 0:
            target_iter = model.get_iter(selected_row - 1)
            model.move_before(selected_iter, target_iter)
            for i in range(self.PROFILE_ROWS):  # reset ID column numbers
                model[i][0] = i + 1
        self.dt_scroll_adjust(selected_row - 1)

    def on_lathe_profile_lower_in_table_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        selection = self.profile_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            return
        selected_row = model.get_path(selected_iter)[0]
        if selected_row < (self.PROFILE_ROWS - 1):
            target_iter = model.get_iter(selected_row + 1)
            model.move_after(selected_iter, target_iter)
            for i in range(self.PROFILE_ROWS):  # reset ID column numbers
                model[i][0] = i + 1
        self.dt_scroll_adjust(selected_row + 1)

    def on_lathe_profile_insert_row_table_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        selection = self.profile_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            return
        selected_row = model.get_path(selected_iter)[0]
        new_iter = model.insert_before(selected_iter,['','','',''])
        last_iter = None
        while selected_iter:
            last_iter = selected_iter
            selected_iter = model.iter_next(selected_iter)
        if last_iter:
            model.remove(last_iter)
        for i in range(self.PROFILE_ROWS):  # reset ID column numbers
            model[i][0] = i + 1
        self.dt_scroll_adjust(selected_row)
        selection.select_iter(new_iter)

    def on_lathe_profile_delete_row_table_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        selection = self.profile_treeview.get_selection()
        model, selected_iter = selection.get_selected()
        if selected_iter is None:
            return
        selected_row = model.get_path(selected_iter)[0]
        model.remove( selected_iter )
        # add an empty row at the end
        model.append(['', '', '', ''])

        for i in range(self.PROFILE_ROWS):  # reset ID column numbers
            model[i][0] = i + 1
        self.dt_scroll_adjust(selected_row)
        self.profile_renderer.update()

    def on_lathe_profile_clear_table_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        model = self.profile_treeview.get_model()
        count = 0
        for n  in range(self.PROFILE_ROWS):
            if any(model[n][1]) or any(model[n][2]): count += 1
        if count > 1:
            dlg = popupdlg.ok_cancel_popup(self.window, 'Are you sure you want to clear this table?')
            dlg.run()
            dlg.destroy()
            if dlg.response != gtk.RESPONSE_OK: return

        self.profile_renderer.clr_hilite()
        self.profile_liststore.clear()
        for id_cnt  in range(1, self.PROFILE_ROWS + 1):
            self.profile_liststore.append([id_cnt, '', '', ''])
        adj = self.scrolled_window_profile_table.get_vadjustment()
        adj.set_value(0)
        self.profile_treeview.set_cursor(0, focus_column=self.profile_x_column, start_editing=True)
        self.profile_renderer.update()

    def profile_table_update_focus(self,row,column,start_editing):
        self.profile_treeview.set_cursor(row, column, start_editing)
        if start_editing:
            self.dt_scroll_adjust(row)

    def on_profile_x_column_keypress(self,widget,ev,row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.profile_table_update_focus,row, self.profile_z_column,True)
            return False
        if ev.keyval == gtk.keysyms.Escape:
            glib.idle_add(self.profile_table_update_focus,row, self.profile_x_column,False)
            return True

    def on_profile_z_column_keypress(self,widget,ev,row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.profile_table_update_focus,row, self.profile_r_column,True)
            return False
        if ev.keyval == gtk.keysyms.Escape:
            target_row = 0 if row == 0 else row - 1
            glib.idle_add(self.profile_table_update_focus,target_row, self.profile_z_column,False)
            return True

    def on_profile_r_column_keypress(self,widget,ev,row):
        if ev.keyval in (gtk.keysyms.Return, gtk.keysyms.KP_Enter):
            glib.idle_add(self.profile_table_update_focus,row, self.profile_x_column,True)
            return False
        if ev.keyval == gtk.keysyms.Escape:
            target_row = 0 if row == 0 else row - 1
            glib.idle_add(self.profile_table_update_focus,target_row, self.profile_r_column,False)
            return True

    def on_profile_cell_edit_x_focus(self, widget, direction, target_row):
        if self.settings.touchscreen_enabled:
            np = numpad.numpad_popup(self.window, widget, False, -324, -119)
            np.run()
            widget.masked = 0
            widget.select_region(0, 0)
            self.window.set_focus(None)

    def on_profile_cell_edit_y_focus(self, widget, direction, target_row):
        if self.settings.touchscreen_enabled:
            np = numpad.numpad_popup(self.window, widget, False, -324, -119)
            np.run()
            widget.masked = 0
            widget.select_region(0, 0)
            self.window.set_focus(None)

    def on_profile_cell_edit_r_focus(self, widget, direction, target_row):
        if self.settings.touchscreen_enabled:
            np = numpad.numpad_popup(self.window, widget, False, -324, -119)
            np.run()
            widget.masked = 0
            widget.select_region(0, 0)
            self.window.set_focus(None)

    def on_profile_x_column_editing_started(self, xrenderer, editable, path, profile_font):
        editable.modify_font(profile_font)
        target_row = 0 if path == '' else int(path)
        if self.settings.touchscreen_enabled:
            editable.connect("focus-in-event", self.on_profile_cell_edit_x_focus, target_row)
        editable.connect("key-press-event", self.on_profile_x_column_keypress, target_row)

    def on_profile_z_column_editing_started(self, yrenderer, editable, path, profile_font):
        editable.modify_font(profile_font)
        target_row = 0 if path == '' else int(path)
        if self.settings.touchscreen_enabled:
            editable.connect("focus-in-event", self.on_profile_cell_edit_y_focus, target_row)
        editable.connect("key-press-event", self.on_profile_z_column_keypress, target_row)

    def on_profile_r_column_editing_started(self, yrenderer, editable, path, profile_font):
        editable.modify_font(profile_font)
        target_row = 0 if path == '' else int(path)
        target_row = (target_row + 1) if target_row < (self.PROFILE_ROWS - 1) else (self.PROFILE_ROWS - 1)
        if self.settings.touchscreen_enabled:
            editable.connect("focus-in-event", self.on_profile_cell_edit_r_focus, target_row)
        editable.connect("key-press-event", self.on_profile_r_column_keypress, target_row)

    def on_profile_x_column_edited(self, cell, row, value, model):
        if value == '' or value == '??':
            old_value = model[row][1]
            model[row][1] = ""
            if old_value != value: self.profile_renderer.update()
            return
        try:
            valid, value = cparse.is_number_or_expression(value)
            if not valid: raise ValueError('validation failed')
        except ValueError:
            self.error_handler.write("Invalid position specified for profile points table", ALARM_LEVEL_LOW)
            model[row][1] = ""
            self.profile_renderer.update()
            return

        row = 0 if row == '' else int(row)
        model[row][1] = self.dro_long_format % value
        self.profile_renderer.update()

    def on_profile_z_column_edited(self, cell, row, value, model):
        if value == '' or value == '??':
            old_value = model[row][2]
            model[row][2] = ""
            if old_value != value: self.profile_renderer.update()
            return
        try:
            valid, value = cparse.is_number_or_expression(value)
            if not valid: raise ValueError('validation failed')
        except ValueError:
            self.error_handler.write("Invalid position specified for profile points table", ALARM_LEVEL_LOW)
            model[row][2] = ""
            self.profile_renderer.update()
            return

        row = 0 if row == '' else int(row)

        model[row][2] = self.dro_long_format % value
        self.profile_renderer.update()

    def on_profile_r_column_edited(self, cell, row, value, model):
        if value == '' or value == '??':
            old_value = model[row][3]
            model[row][3] = ""
            if old_value != value: self.profile_renderer.update()
            return
        try:
            valid, value = cparse.is_number_or_expression(value)
            if not valid: raise ValueError('validation failed')
        except ValueError:
            self.error_handler.write("Invalid position specified for profile points table", ALARM_LEVEL_LOW)
            model[row][3] = ""
            self.profile_renderer.update()
            return
        # pick up the start point..
        end_pt = [None,None]
        start_pt = [None,None]
        i_row = int(row)
        # if row is '0' this is a special case, where, as a convenience to the user
        # the start_pt is implicit and equal to 'X', 'Stock Z'
        if i_row == 0:
            if model[0][1] != '': start_pt[0] = float(model[0][1])/2.0
            valid, z_val = cparse.is_number_or_expression(self.profile_dro_list['profile_stock_z_dro'])
            if not valid: return
            start_pt[1] = z_val
            if model[0][1] != '': end_pt[0] = float(model[0][1])/2.0
            if model[0][2] != '': end_pt[1] = float(model[0][2])
        else:
            for n in range(int(row)+1):
                if model[n][1] != '': end_pt[0] = float(model[n][1])/2.0
                if model[n][2] != '': end_pt[1] = float(model[n][2])
                if n>0:
                    if model[n-1][1] != '': start_pt[0] = float(model[n-1][1])/2.0
                    if model[n-1][2] != '': start_pt[1] = float(model[n-1][2])

        try:
            valid = lathe_conv_support.LatheProfileRenderer.check_radius(tuple(start_pt),tuple(end_pt),float(value))
            if not valid:
                min_rad = lathe_conv_support.LatheProfileRenderer.min_radius(tuple(start_pt),tuple(end_pt))
                self.error_handler.write("Invalid radius of %s for start and end points X%s Z%s -> X%s Z%s\nRadius must be larger than %s. Larger radius produces flatter curve."%\
                                         (self.dro_long_format,self.dro_long_format,self.dro_long_format,self.dro_long_format,self.dro_long_format,self.dro_long_format)%\
                                         (value,start_pt[0]*2.0,start_pt[1],end_pt[0]*2.0,end_pt[1],min_rad), ALARM_LEVEL_LOW)
                model[row][3] = self.dro_long_format % value
                self.profile_renderer.update()
                glib.idle_add(self.profile_table_update_focus,int(row), self.profile_r_column,True)
                return
        except TypeError:
            self.error_handler.log('lathe.on_profile_r_column_edited: TypeError in call to profile_renderer.check_radius')
            model[row][3] = ""
            return
        row = 0 if row == '' else int(row)
        model[row][3] = self.dro_long_format % value
        self.profile_renderer.update()

    def dt_scroll_adjust(self, row):
        # get var list from vertical scroll bar
        adj = self.scrolled_window_profile_table.get_vadjustment()

        unitsperrow = (adj.upper - adj.lower) / self.PROFILE_ROWS
        centerofpage = adj.page_size / 2
        centerofrow = unitsperrow / 2
        cofcurrentrow = (row * unitsperrow) + centerofrow
        scroll_offset = cofcurrentrow - centerofpage

        if scroll_offset < 0:
            scroll_offset = 0
        elif scroll_offset > (adj.upper - adj.page_size):
            scroll_offset = (adj.upper - adj.page_size)
        adj.set_value(scroll_offset)

    def profile_update_tool_geometries(self):
        tool = int(self.profile_dro_list['profile_tool_num_dro'].get_text())
        front_angle = self.status.tool_table[tool].frontangle
        back_angle = self.status.tool_table[tool].backangle
        new_front_angle = round(float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),2)
        new_back_angle = round(float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()),2)
        if front_angle != new_front_angle or back_angle != new_back_angle:
            self.command.wait_complete()
            g10_command = "G10 L1 P%d I%.1f J%.1f" % (tool, new_front_angle, new_back_angle)
            self.issue_mdi(g10_command)
            self.command.wait_complete()


    def set_tool_table_data(self,model,row,data):
        rt = False
        if 'tdr' in data:
            if data['tdr'].data['back_angle'][0]['ref'] != 0.0: data['ba'] = data['tdr'].data['back_angle'][0]['ref']
            if data['tdr'].data['front_angle'][0]['ref'] != 0.0: data['fa'] = data['tdr'].data['front_angle'][0]['ref']
            if data['tdr'].data['tool_radius'][0]['ref'] != 0.0: data['radius'] = data['tdr'].data['tool_radius'][0]['ref']

        if 'diameter' in data:
            self.on_nose_radius_col_edited(None,row,str(float(data['diameter'])/2.),model,data)
            rt = True
        if 'radius' in data:
            self.on_nose_radius_col_edited(None,row,str(float(data['radius'])),model,data)
            rt = True
        if 'type' in data:
            if data['type'] in ['drill','center','centerdrill','spot','tap','reamer']: self.on_tip_orient_col_edited(None,row,'7',model,data)
            rt = True
        if 'g10' in data['cmd']:
            g10_str = ''
            if 'ba' in data: g10_str += ' I{:.1f}'.format(data['fa'])
            if 'fa' in data: g10_str += ' J{:.1f}'.format(data['ba'])
            if 'radius' in data:  g10_str += ' R{:.4f}'.format(data['radius'])
            if not g10_str: return rt
            g10_command = 'G10 L1 P{:d} {}'.format(row+1,g10_str)
            self.issue_mdi(g10_command)
            self.command.wait_complete()
        return rt

    def tool_data(self, tool=None):
        if tool is None:
            try:
                tool = int(self.profile_dro_list['profile_tool_num_dro'].get_text())
            except:
                return (0, 0, 0., 0., 0)
        self.status.poll()
        # only pull tool_table across status channel once and then examine python object locally
        tool_table = self.status.tool_table
        r = tool_table[tool].diameter * self.mm_inch_scalar/ 2
        fa = tool_table[tool].frontangle
        ba = tool_table[tool].backangle
        o = tool_table[tool].orientation
        return (tool,r,fa,ba,o)

    def profile_set_tool_data(self, tool=None):
        tool, r, front_angle, back_angle, orientation = self.tool_data(tool)
        self.profile_dro_list['profile_tool_front_angle_dro'].set_text('%.1f' % (front_angle))
        self.profile_dro_list['profile_tool_rear_angle_dro'].set_text('%.1f' % (back_angle))
        self.profile_renderer.set_angles(tool,
                                         float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                         float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()),
                                         orientation)
        self.tool_renderer.set_angles(tool,
                                      r,
                                      float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                      float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()),
                                      orientation)
        ta_dat = [ {'filler': None},
                   {'svg':'lathe_tool_angle_CP1.svg', 'fa_lab':(16,123), 'fa_dro':(25,153),'ra_lab':(21,193), 'ra_dro':(25,223)},
                   {'svg':'lathe_tool_angle_CP2.svg', 'fa_lab':(49,63),  'fa_dro':(58,93), 'ra_lab':(53,133), 'ra_dro':(58,163)},
                   {'svg':'lathe_tool_angle_CP3.svg', 'fa_lab':(70,54),  'fa_dro':(79,84), 'ra_lab':(212,26), 'ra_dro':(217,56)},
                   {'svg':'lathe_tool_angle_CP4.svg', 'fa_lab':(70,54),  'fa_dro':(79,84), 'ra_lab':(212,26), 'ra_dro':(217,56)},
                   {'svg': None,                      'fa_lab':(0,0),    'fa_dro':(0.0),   'ra_lab':(0,0),    'ra_dro':(0.0)},
                   {'svg':'lathe_tool_angle_CP6.svg', 'fa_lab':(49,63),  'fa_dro':(58,93), 'ra_lab':(53,133), 'ra_dro':(58,163)},
                   {'svg': None,                      'fa_lab':(0,0),    'fa_dro':(0.0),   'ra_lab':(0,0),    'ra_dro':(0.0)},
                   {'svg':'lathe_tool_angle_CP8.svg', 'fa_lab':(70,54),  'fa_dro':(79,84), 'ra_lab':(212,26), 'ra_dro':(217,56)}
                ]
        try:
            dat = ta_dat[orientation]
            self.set_image('lathe_profile_tool_angle_background', dat['svg'])
            fixed = self.builder.get_object('lathe_profile_tool_angle_fixed')
            lab = self.builder.get_object('profile_tool_front_angle_text')
            fixed.move(self.builder.get_object('profile_tool_front_angle_text'), dat['fa_lab'][0], dat['fa_lab'][1])
            fixed.move(self.profile_dro_list['profile_tool_front_angle_dro'], dat['fa_dro'][0], dat['fa_dro'][1])
            fixed.move(self.builder.get_object('profile_tool_rear_angle_text'), dat['ra_lab'][0], dat['ra_lab'][1])
            fixed.move(self.profile_dro_list['profile_tool_rear_angle_dro'], dat['ra_dro'][0], dat['ra_dro'][1])
        except:
            self.error_handler.write('on_profile_tool_num_dro_activate: cound not find data', ALARM_LEVEL_DEBUG)

    def profile_check_diameters(self):
        diam = float(self.profile_dro_list['profile_stock_x_dro'].get_text())
        safex = float(self.profile_dro_list['profile_roughing_tool_clear_x_dro'].get_text())
        clr = False
        if self.conv_profile_ext == 'external':
            if math.fabs(safex)>math.fabs(diam): clr = True
        elif math.fabs(safex)<math.fabs(diam): clr = True
        if clr:
            cparse.clr_alarm(self.profile_dro_list['profile_stock_x_dro'])
            cparse.clr_alarm(self.profile_dro_list['profile_roughing_tool_clear_x_dro'])

    def on_profile_tool_num_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_tool_number', '%d', 'Profile Tool number: ',
                                             self.profile_dro_list['profile_stock_x_dro']): return
        if not self._test_on_activate_tool_dro(widget): return
        self.profile_set_tool_data(int(widget.get_text()))
        self.profile_renderer.update()

    def on_profile_stock_x_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_gt0', None, 'Profile Stock Z: ',
                                                     self.profile_dro_list['profile_stock_z_dro']): return
        self.profile_check_diameters()
        self.profile_renderer.update()

    def on_profile_stock_z_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_any_num', None, 'Profile Stock Z: ',
                                                     self.profile_dro_list['profile_roughing_tool_clear_x_dro']): return
        self.profile_renderer.update()


    def on_profile_roughing_tool_clear_x_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_any_num_not_zero', None, 'Profile Roughing Safe X: ',
                                             self.profile_dro_list['profile_roughing_tool_clear_z_dro']): return
        self.profile_renderer.update()
        self.profile_check_diameters()

    def on_profile_roughing_tool_clear_z_dro_activate(self, widget, data=None):
        self.conversational.std_validate_dro(widget, 'validate_any_num', None, 'Profile Roughing Safe Z: ',
                                             self.profile_dro_list['profile_tool_num_dro'])

    def on_profile_roughing_doc_dro_activate(self, widget, data=None):
        rdp = (0.0,2.54) if self.g21  else (0.0,0.10)
        valid, value, error_msg = self.conversational.std_validate_param(widget, 'val_empty_range_float', 'Profile Roughing DOC: ', rdp)
        if not valid: widget.select_region(0, -1)
        else:
            txt = widget.get_text()
            if any(txt): FSBase.dro_on_activate(widget, txt)
            self.profile_dro_list['profile_finish_passes_dro'].grab_focus()

    def on_profile_finish_doc_dro_activate(self, widget, data=None):
        fdp = (0.0,0.508) if self.g21 else (0.0,0.02)
        if self.conversational.std_validate_dro(widget, 'validate_range_float', None, 'Profile Finish DOC: ',
                                             self.profile_dro_list['profile_roughing_doc_dro'],fdp):
            FSBase.dro_on_activate(widget, widget.get_text())

    def on_profile_finish_passes_dro_activate(self, widget, data=None):
        self.conversational.std_validate_dro(widget, 'validate_in_set', '%s', 'Profile Finish Passes: ',
                                             self.profile_dro_list['profile_finish_doc_dro'], ('','0','1','2'))

    def on_profile_tool_front_angle_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_tool_angle', '%.1f', 'Profile Front tool angle: ',
                                             self.profile_dro_list['profile_tool_rear_angle_dro']): return
        self.profile_renderer.set_angles(int(self.profile_dro_list['profile_tool_num_dro'].get_text()),
                                         float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                         float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()))
        self.tool_renderer.set_angles(int(self.profile_dro_list['profile_tool_num_dro'].get_text()),
                                      None,
                                      float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                      float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()),
                                      None)
        self.profile_renderer.update()

    def on_profile_tool_rear_angle_dro_activate(self, widget, data=None):
        if not self.conversational.std_validate_dro(widget, 'validate_tool_angle', '%.1f', 'Profile Rear tool angle: ',
                                             self.profile_dro_list['profile_tool_front_angle_dro']): return
        self.profile_renderer.set_angles(int(self.profile_dro_list['profile_tool_num_dro'].get_text()),
                                         float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                         float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()))
        self.tool_renderer.set_angles(int(self.profile_dro_list['profile_tool_num_dro'].get_text()),
                                      None,
                                      float(self.profile_dro_list['profile_tool_front_angle_dro'].get_text()),
                                      float(self.profile_dro_list['profile_tool_rear_angle_dro'].get_text()),
                                      None)
        self.profile_renderer.update()

    def on_profile_roughing_doc_dro_focus_in(self, widget, event, data=None):
        zero_str = self.dro_long_format%0.0
        img = 'lathe_no_roughing.svg' if widget.get_text() in ('',zero_str) else 'lathe_roughing_page.svg'
        self.set_image('profile_roughing_page', img)

    def on_profile_finish_passes_dro_focus_in(self, widget, event, data=None): self.profile_set_finish_image()

    def on_profile_finish_doc_dro_focus_in(self, widget, event, data=None): self.profile_set_finish_image()

    def update_subroutine_number(self):
        val = '1000'
        key = 'profile_sub_number'
        try:
            if self.redis.hexists('machine_prefs', key): val = self.redis.hget('machine_prefs', key)
            bumpval = int(val)+1
            if bumpval > 9999: bumpval = 1000
            self.redis.hset('machine_prefs', key, str(bumpval))
        except:
            self.error_handler.write('update_subroutine_number: redis raised exception', ALARM_LEVEL_DEBUG)
            return None
        return val

    # #################################################################################################
    # #################################################################################################
    # Facing DROs
    # #################################################################################################
    # #################################################################################################

    def on_face_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.face_focus_list, 'face_tool_num_dro')
        self.face_dro_list[where_to].grab_focus()

    def on_face_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_z_end_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_stock_dia_dro'].grab_focus()
        return

    def on_face_stock_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_stock_dia_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_x_end_dro'].grab_focus()
        return

    def on_face_x_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_x_end_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_z_start_dro'].grab_focus()
        return

    def on_face_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_z_start_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_tc_dro'].grab_focus()
        return

    def on_face_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_tc_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_rough_doc_dro'].grab_focus()
        return

    def on_face_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_rough_doc_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_finish_doc_dro'].grab_focus()
        return

    def on_face_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.face_focus_list, 'face_finish_doc_dro')
        self.face_dro_list[where_to].grab_focus()
        #self.face_dro_list['face_z_end_dro'].grab_focus()
        #self.window.set_focus(None)
        return


    # #################################################################################################
    # #################################################################################################
    # Chamfer DROs
    # #################################################################################################
    # #################################################################################################

    def corner_clear(self):
        # turn Corner DROs OFF
        for droi in self.corner_chamfer_od_dro_list:
            self.corner_chamfer_od_dro_list[droi].set_visible(False)
        for droi in self.corner_chamfer_id_dro_list:
            self.corner_chamfer_id_dro_list[droi].set_visible(False)
        for droi in self.corner_radius_od_dro_list:
            self.corner_radius_od_dro_list[droi].set_visible(False)
        for droi in self.corner_radius_id_dro_list:
            self.corner_radius_id_dro_list[droi].set_visible(False)

        # turn Corner dynamic labels OFF
        self.corner_chamfer_od_angle_label.set_visible(False)
        self.corner_chamfer_id_angle_label.set_visible(False)
        self.corner_chamfer_od_rough_doc_label.set_visible(False)
        self.corner_chamfer_id_rough_doc_label.set_visible(False)
        self.corner_chamfer_od_finish_doc_label.set_visible(False)
        self.corner_chamfer_id_finish_doc_label.set_visible(False)
        self.corner_chamfer_od_tc_label.set_visible(False)
        self.corner_chamfer_id_tc_label.set_visible(False)

        self.corner_radius_od_rough_doc_label.set_visible(False)
        self.corner_radius_id_rough_doc_label.set_visible(False)
        self.corner_radius_od_finish_doc_label.set_visible(False)
        self.corner_radius_id_finish_doc_label.set_visible(False)
        self.corner_radius_od_tc_label.set_visible(False)
        self.corner_radius_id_tc_label.set_visible(False)

        self.corner_od_x_label.set_visible(False)
        self.corner_id_x_label.set_visible(False)

    def toggle_chamfer_radius_button(self):
        self.corner_clear()
        self.save_title_dro()

        # toggle button state between chamfer and corner radius
        if self.conv_chamfer_radius == 'chamfer':  # toggle to radius mode
            self.set_image('corner_chamfer_radius_btn_image', 'chamfer_radius_rad_highlight.jpg')

            if self.conv_chamfer_od_id == 'od':
                # Set tab graphics to Radius OD
                self.set_image('conv_corner_background', 'lathe_corner_radius_od.svg')

                # turn Radius OD labels ON
                self.corner_radius_od_rough_doc_label.set_visible(True)
                self.corner_radius_od_finish_doc_label.set_visible(True)
                self.corner_radius_od_tc_label.set_visible(True)

                self.corner_od_x_label.set_visible(True)

                # turn Radius OD DROs ON
                for droi in self.corner_radius_od_dro_list:
                    self.corner_radius_od_dro_list[droi].set_visible(True)

            else: # self.conv_chamfer_od_id == 'id'
                # Set tab graphics to Chamfer OD
                self.set_image('conv_corner_background', 'lathe_corner_radius_id.svg')

                # turn Radius ID labels ON
                self.corner_radius_id_rough_doc_label.set_visible(True)
                self.corner_radius_id_finish_doc_label.set_visible(True)
                self.corner_radius_id_tc_label.set_visible(True)

                self.corner_id_x_label.set_visible(True)

                # turn Corner ID DROs ON
                for droi in self.corner_radius_id_dro_list:
                    self.corner_radius_id_dro_list[droi].set_visible(True)

            self.conv_chamfer_radius = 'radius'

        else:  # toggle to chamfer mode
            self.set_image('corner_chamfer_radius_btn_image', 'chamfer_radius_cham_highlight.jpg')

            if self.conv_chamfer_od_id == 'od':
                # Set tab graphics to Chamfer OD
                self.set_image('conv_corner_background', 'lathe_corner_chamfer_od.svg')

                # turn Chamfer OD labels ON
                self.corner_chamfer_od_angle_label.set_visible(True)
                self.corner_chamfer_od_rough_doc_label.set_visible(True)
                self.corner_chamfer_od_finish_doc_label.set_visible(True)
                self.corner_chamfer_od_tc_label.set_visible(True)

                self.corner_od_x_label.set_visible(True)

                # turn Chamfer OD DROs ON
                for droi in self.corner_chamfer_od_dro_list:
                    self.corner_chamfer_od_dro_list[droi].set_visible(True)

            else: # self.conv_chamfer_od_id == 'id'
                # Set tab graphics to Chamfer ID
                self.set_image('conv_corner_background', 'lathe_corner_chamfer_id.svg')

                # turn Chamfer ID labels ON
                self.corner_chamfer_id_angle_label.set_visible(True)
                self.corner_chamfer_id_rough_doc_label.set_visible(True)
                self.corner_chamfer_id_finish_doc_label.set_visible(True)
                self.corner_chamfer_id_tc_label.set_visible(True)

                self.corner_id_x_label.set_visible(True)

                # turn Chamfer ID DROs ON
                for droi in self.corner_chamfer_id_dro_list:
                    self.corner_chamfer_id_dro_list[droi].set_visible(True)
            self.conv_chamfer_radius = 'chamfer'
        self.load_title_dro()

    def on_corner_chamfer_radius_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_chamfer_radius_button()
        return

    def toggle_id_od_button(self):
        self.corner_clear()
        self.save_title_dro()

        # toggle button state between ID and OD
        if self.conv_chamfer_od_id == 'od':  # toggle to ID mode
            self.set_image('corner_id_od_btn_image', 'id_od_button.jpg')

            if self.conv_chamfer_radius == 'chamfer':
                # Set tab graphics to Chamfer ID
                self.set_image('conv_corner_background', 'lathe_corner_chamfer_id.svg')

                # turn Chamfer ID labels ON
                self.corner_chamfer_id_angle_label.set_visible(True)
                self.corner_chamfer_id_rough_doc_label.set_visible(True)
                self.corner_chamfer_id_finish_doc_label.set_visible(True)
                self.corner_chamfer_id_tc_label.set_visible(True)

                self.corner_id_x_label.set_visible(True)

                # turn Chamfer ID DROs ON
                for droi in self.corner_chamfer_id_dro_list:
                    self.corner_chamfer_id_dro_list[droi].set_visible(True)

            else: # self.conv_chamfer_radius == 'radius'
                # Set tab graphics to Chamfer ID
                self.set_image('conv_corner_background', 'lathe_corner_radius_id.svg')

                # turn Radius ID labels ON
                self.corner_radius_id_rough_doc_label.set_visible(True)
                self.corner_radius_id_finish_doc_label.set_visible(True)
                self.corner_radius_id_tc_label.set_visible(True)

                self.corner_id_x_label.set_visible(True)

                # turn Radius ID DROs ON
                for droi in self.corner_radius_id_dro_list:
                    self.corner_radius_id_dro_list[droi].set_visible(True)

            self.conv_chamfer_od_id = 'id'

        else:  # self.conv_chamfer_od_id == 'id' # toggle to OD mode
            self.set_image('corner_id_od_btn_image', 'od_id_button.jpg')

            if self.conv_chamfer_radius == 'chamfer':
                # Set tab graphics to Chamfer OD
                self.set_image('conv_corner_background', 'lathe_corner_chamfer_od.svg')

                # turn Chamfer OD labels ON
                self.corner_chamfer_od_angle_label.set_visible(True)
                self.corner_chamfer_od_rough_doc_label.set_visible(True)
                self.corner_chamfer_od_finish_doc_label.set_visible(True)
                self.corner_chamfer_od_tc_label.set_visible(True)

                self.corner_od_x_label.set_visible(True)

                # turn Chamfer OD DROs ON
                for droi in self.corner_chamfer_od_dro_list:
                    self.corner_chamfer_od_dro_list[droi].set_visible(True)

            else: # self.conv_chamfer_radius == 'radius'
                # Set tab graphics to Corner Radius OD
                self.set_image('conv_corner_background', 'lathe_corner_radius_od.svg')

                # turn Radius OD labels ON
                self.corner_radius_od_rough_doc_label.set_visible(True)
                self.corner_radius_od_finish_doc_label.set_visible(True)
                self.corner_radius_od_tc_label.set_visible(True)

                self.corner_od_x_label.set_visible(True)

                # turn Radius OD DROs ON
                for droi in self.corner_radius_od_dro_list:
                    self.corner_radius_od_dro_list[droi].set_visible(True)

            self.conv_chamfer_od_id = 'od'
        self.load_title_dro()

    def on_corner_id_od_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_id_od_button()


    def on_corner_chamfer_od_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_tool_num_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()

    def on_corner_chamfer_id_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_tool_num_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()

    def on_corner_radius_od_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_tool_num_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()

    def on_corner_radius_id_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_tool_num_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()

    def on_corner_chamfer_od_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to chamfer_z_width DRO
        try:
            z_end = float(self.corner_chamfer_od_dro_list['corner_chamfer_od_z_end_dro'].get_text())
        except:
            z_end = 0

        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_z_start_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to chamfer_z_width DRO
        try:
            z_end = float(self.corner_chamfer_id_dro_list['corner_chamfer_id_z_end_dro'].get_text())
        except:
            z_end = 0

        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_z_start_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to chamfer_od_z_width DRO
        try:
            z_start = float(self.corner_chamfer_od_dro_list['corner_chamfer_od_z_start_dro'].get_text())
        except:
            z_start = 0

        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_z_end_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to chamfer_id_z_width DRO
        try:
            z_start = float(self.corner_chamfer_id_dro_list['corner_chamfer_id_z_start_dro'].get_text())
        except:
            z_start = 0

        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_z_end_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_od_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_od_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_id_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_id_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_angle_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_dwell_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_angle_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_angle_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_dwell_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_angle_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_rough_doc_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_rough_doc_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_finish_doc_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_finish_doc_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_od_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_od_focus_list, 'corner_chamfer_od_tc_dro')
        self.corner_chamfer_od_dro_list[where_to].grab_focus()
        return

    def on_corner_chamfer_id_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_chamfer_id_focus_list, 'corner_chamfer_id_tc_dro')
        self.corner_chamfer_id_dro_list[where_to].grab_focus()
        return

    # ---- Corner Radius DROs ----

    def on_corner_radius_od_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to corner_od_z_width DRO
        try:
            z_end = float(self.corner_radius_od_dro_list['corner_radius_od_z_end_dro'].get_text())
        except:
            z_end = 0

        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_z_start_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to corner_id_z_width DRO
        try:
            z_end = float(self.corner_radius_id_dro_list['corner_radius_id_z_end_dro'].get_text())
        except:
            z_end = 0

        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_z_start_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_od_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to corner_od_z_width DRO
        try:
            z_start = float(self.corner_radius_od_dro_list['corner_radius_od_z_start_dro'].get_text())
        except:
            z_start = 0

        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_z_end_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate the width and push to corner_id_z_width DRO
        try:
            z_start = float(self.corner_radius_id_dro_list['corner_radius_id_z_start_dro'].get_text())
        except:
            z_start = 0

        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_z_end_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_od_od_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_od_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_id_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.corner_id_dro_list['corner_id_rough_doc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_id_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_od_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_rough_doc_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.corner_id_dro_list['corner_id_finish_doc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_rough_doc_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_od_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_finish_doc_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.corner_id_dro_list['corner_id_tc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_finish_doc_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_od_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.corner_radius_od_focus_list, 'corner_radius_od_tc_dro')
        self.corner_radius_od_dro_list[where_to].grab_focus()
        return

    def on_corner_radius_id_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.corner_id_dro_list['corner_id_z_start_dro'].grab_focus()
        where_to = self.next_conv_dro(self.corner_radius_id_focus_list, 'corner_radius_id_tc_dro')
        self.corner_radius_id_dro_list[where_to].grab_focus()
        return


    # #################################################################################################
    # #################################################################################################
    # Groove DROs
    # #################################################################################################
    # #################################################################################################

    def toogle_groove_part_dros(self):
        self.save_title_dro()
        is_grooving = self.conv_groove_part == 'part'
        is_parting = self.conv_groove_part == 'groove'

        # turn Groove DROs OFF
        self.groove_dro_list['groove_tool_num_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_z_start_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_stock_dia_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_final_dia_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_z_end_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_rough_doc_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_tw_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_finish_doc_dro'].set_visible(is_grooving)
        self.groove_dro_list['groove_tc_dro'].set_visible(is_grooving)

        # tool DROs
        self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(is_grooving)
        self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(is_grooving)

        # turn Groove labels(text) OFF
        self.groove_z_end_label.set_visible(is_grooving)
        self.groove_r_doc_label.set_visible(is_grooving)
        self.groove_f_doc_label.set_visible(is_grooving)
        self.groove_tw_label.set_visible(is_grooving)

        # turn Part DROs ON
        self.part_dro_list['part_tool_num_dro'].set_visible(is_parting)
        self.part_dro_list['part_z_start_dro'].set_visible(is_parting)
        self.part_dro_list['part_stock_dia_dro'].set_visible(is_parting)
        self.part_dro_list['part_final_dia_dro'].set_visible(is_parting)
        self.part_dro_list['part_tc_dro'].set_visible(is_parting)
        self.part_dro_list['part_peck_dro'].set_visible(is_parting)
        self.part_dro_list['part_retract_dro'].set_visible(is_parting)
        self.part_dro_list['part_ebw_dro'].set_visible(is_parting)
        self.part_dro_list['part_tw_dro'].set_visible(is_parting)

        # turn Part labels(text) ON
        self.part_peck_label.set_visible(is_parting)
        self.part_retract_label.set_visible(is_parting)
        self.part_ebw_label.set_visible(is_parting)
        self.part_tw_label.set_visible(is_parting)

        # set the button and the image...
        btn_image = 'groove_part_part_highlight.jpg' if self.conv_groove_part == 'groove' else 'groove_part_grv_highlight.jpg'
        back_ground_image =  'lathe_part.svg' if self.conv_groove_part == 'groove' else 'lathe_groove.svg'
        self.set_image('groove_part_btn_image', btn_image)
        self.set_image('conv_groove_part_image', back_ground_image)
        # toggle the state...
        self.conv_groove_part = 'groove' if self.conv_groove_part == 'part' else 'part'

        # if the 'parting' tool width is empty ...
        # copy over the tool width from the groove data
        if self.conv_groove_part == 'part':
            text = self.part_dro_list['part_tw_dro'].get_text()
            if len(text) == 0:
                self.part_dro_list['part_tw_dro'].set_text(self.groove_dro_list['groove_tw_dro'].get_text())
            self.part_dro_list[self.part_focus_list[0]].grab_focus()
        else:
            self.groove_dro_list[self.groove_focus_list[0]].grab_focus()
        self.load_title_dro()


    def on_groove_part_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toogle_groove_part_dros()
        return

    def _set_tool_width(self, tool_number, width_widget):
        description = self.get_tool_description(tool_number)
        tdr = ui_support.ToolDescript.parse_text(description)
        width = tdr.data['tool_width'][0]['ref']
        if width == 0.0: return
        width_widget.set_text(self.dro_long_format%width)

    def on_groove_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        self._set_tool_width(int(widget.get_text()), self.groove_dro_list['groove_tw_dro'])
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_tool_num_dro')
        self.groove_dro_list[where_to].grab_focus()

    def on_groove_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.groove_dro_list['groove_stock_dia_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_z_start_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_stock_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.groove_dro_list['groove_final_dia_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_stock_dia_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_final_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.groove_dro_list['groove_z_end_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_final_dia_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.groove_dro_list['groove_rough_doc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_z_end_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_rough_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.groove_dro_list['groove_tw_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_rough_doc_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_tw_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.groove_dro_list['groove_finish_doc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_tw_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_finish_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        #self.groove_dro_list['groove_tc_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_finish_doc_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    def on_groove_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        #self.groove_dro_list['groove_z_start_dro'].grab_focus()
        where_to = self.next_conv_dro(self.groove_focus_list, 'groove_tc_dro')
        self.groove_dro_list[where_to].grab_focus()
        return

    # ---- Part DROs ---- #
    def on_part_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        self._set_tool_width(int(widget.get_text()), self.part_dro_list['part_tw_dro'])
        where_to = self.next_conv_dro(self.part_focus_list, 'part_tool_num_dro')
        self.part_dro_list[where_to].grab_focus()

    def on_part_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_z_start_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_stock_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_stock_dia_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_final_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_final_dia_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_tc_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_tw_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_tw_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_css_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_short_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_css_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_fpr_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_fpr_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_peck_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_peck_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_retract_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_retract_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_finish_rpm_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_short_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_finish_rpm_dro')
        self.part_dro_list[where_to].grab_focus()
        return

    def on_part_ebw_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.part_focus_list, 'part_ebw_dro')
        self.part_dro_list[where_to].grab_focus()
        return


    # #################################################################################################
    # #################################################################################################
    # Drill-Tap DROs
    # #################################################################################################
    # #################################################################################################

    def toggle_drill_tap_button(self):
        self.save_title_dro()
        if self.conv_drill_tap == 'drill':
            self.set_image('drill_tap_btn_image', 'drill_tap_tap_highlight.jpg')
            self.set_image('conv_drill_tap_image', 'lathe_tap.svg')

            # turn Drill DROs OFF
            self.drill_dro_list['drill_tool_num_dro'].set_visible(False)
            self.drill_dro_list['drill_z_start_dro'].set_visible(False)
            self.drill_dro_list['drill_tc_dro'].set_visible(False)
            self.drill_dro_list['drill_peck_dro'].set_visible(False)
            self.drill_dro_list['drill_z_end_dro'].set_visible(False)
            self.drill_dro_list['drill_spindle_rpm_dro'].set_visible(False)
            self.drill_dro_list['drill_dwell_dro'].set_visible(False)

            # turn Tap DROs ON
            self.tap_dro_list['tap_tool_num_dro'].set_visible(True)
            self.tap_dro_list['tap_z_start_dro'].set_visible(True)
            self.tap_dro_list['tap_tc_dro'].set_visible(True)
            self.tap_dro_list['tap_z_end_dro'].set_visible(True)
            self.tap_dro_list['tap_spindle_rpm_dro'].set_visible(True)
            self.tap_dro_list['tap_tpu_dro'].set_visible(True)
            self.tap_dro_list['tap_pitch_dro'].set_visible(True)
            self.tap_dro_list['tap_peck_dro'].set_visible(True)

            # turn Drill labels(text) OFF
            self.drill_z_end_label.set_visible(False)
            self.drill_dwell_label.set_visible(False)

            # turn Tap labels(text) ON
            self.tap_z_end_label.set_visible(True)
            self.tap_tpu_label.set_visible(True)
            self.tap_pitch_label.set_visible(True)

            # these conv_DROs are also changed in on_conversational_notebook_switch_page
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(False)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(False)

            self.conv_drill_tap = 'tap'
            self.tap_dro_list[self.tap_focus_list[0]].grab_focus()
            self.drill_through_hole_hint_label.set_visible(False)

        else:
            self.set_image('drill_tap_btn_image', 'drill_tap_drill_highlight.jpg')
            self.set_image('conv_drill_tap_image', 'lathe_drill.svg')

            # turn Tap DROs OFF
            self.tap_dro_list['tap_tool_num_dro'].set_visible(False)
            self.tap_dro_list['tap_z_start_dro'].set_visible(False)
            self.tap_dro_list['tap_tc_dro'].set_visible(False)
            self.tap_dro_list['tap_z_end_dro'].set_visible(False)
            self.tap_dro_list['tap_spindle_rpm_dro'].set_visible(False)
            self.tap_dro_list['tap_tpu_dro'].set_visible(False)
            self.tap_dro_list['tap_pitch_dro'].set_visible(False)
            self.tap_dro_list['tap_peck_dro'].set_visible(False)

            # turn Drill DROs ON
            self.drill_dro_list['drill_tool_num_dro'].set_visible(True)
            self.drill_dro_list['drill_z_start_dro'].set_visible(True)
            self.drill_dro_list['drill_tc_dro'].set_visible(True)
            self.drill_dro_list['drill_peck_dro'].set_visible(True)
            self.drill_dro_list['drill_z_end_dro'].set_visible(True)
            self.drill_dro_list['drill_spindle_rpm_dro'].set_visible(True)
            self.drill_dro_list['drill_dwell_dro'].set_visible(True)

            # turn Tap labels(text) OFF
            self.tap_z_end_label.set_visible(False)
            self.tap_tpu_label.set_visible(False)
            self.tap_pitch_label.set_visible(False)

            # turn Drill labels(text) ON
            self.drill_z_end_label.set_visible(True)
            self.drill_dwell_label.set_visible(True)

            # these conv_DROs are also changed in on_conversational_notebook_switch_page
            self.conv_dro_list['conv_rough_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_rough_fpr_dro'].set_sensitive(True)
            self.conv_dro_list['conv_finish_sfm_dro'].set_sensitive(False)
            self.conv_dro_list['conv_finish_fpr_dro'].set_sensitive(False)

            self.conv_drill_tap = 'drill'
            self.drill_through_hole_hint_label.set_visible(True)
            self.drill_dro_list[self.drill_focus_list[0]].grab_focus()
        self.load_title_dro()


    def on_drill_tap_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_drill_tap_button()
        self.update_chip_load_hint()
        return

    def on_drill_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        self.update_chip_load_hint()
        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_tool_num_dro')
        self.drill_dro_list[where_to].grab_focus()

    def on_drill_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_z_start_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    def on_drill_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_tc_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    def on_drill_peck_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)
        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_peck_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    def on_drill_spindle_rpm_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_short_format % value)
        self.update_chip_load_hint()
        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_spindle_rpm_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    def on_drill_dwell_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_dwell_format % value)
        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_dwell_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    def on_drill_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        self._update_drill_through_hole_hint_label(self.drill_dro_list['drill_tool_num_dro'].get_text(),
                                                   self.drill_dro_list['drill_z_end_dro'].get_text(),
                                                   self.drill_through_hole_hint_label)

        where_to = self.next_conv_dro(self.drill_focus_list, 'drill_z_end_dro')
        self.drill_dro_list[where_to].grab_focus()
        return

    # ---- Tap DROs ---- #
    def on_tap_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_tool_num_dro')
        self.tap_dro_list[where_to].grab_focus()

    def on_tap_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_z_start_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)
        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_tc_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_spindle_rpm_dro_activate(self, widget, data=None):
        pitch = self.tap_dro_list['tap_pitch_dro'].get_text()
        max_vel = self.inifile.find("AXIS_2", "MAX_VELOCITY")
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21, pitch, max_vel)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_short_format % value)
        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_spindle_rpm_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_tpu_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_tpu_format % value)

        pitch = 1 / value
        self.tap_dro_list["tap_pitch_dro"].set_text(self.dro_long_format % pitch)

        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_tpu_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_pitch_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        tpu = 1 / value
        self.tap_dro_list["tap_tpu_dro"].set_text(self.dro_tpu_format % tpu)

        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_pitch_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_z_end_dro')
        self.tap_dro_list[where_to].grab_focus()
        return

    def on_tap_peck_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)

        where_to = self.next_conv_dro(self.tap_focus_list, 'tap_peck_dro')
        self.tap_dro_list[where_to].grab_focus()
        return


    # #################################################################################################
    # #################################################################################################
    # Threading DROs
    # #################################################################################################
    # #################################################################################################

    def toggle_thread_external_internal_button(self):
        self.save_title_dro()
        if self.conv_thread_ext_int == 'external':
            self.set_image('thread_ext_int_image', 'thread_int_button.jpg')
            self.thread_major_dia_label.set_label('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >X    End :</span>')
            self.thread_minor_dia_label.set_label('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >X    Start :</span>')
            self.conv_thread_ext_int = 'internal'
        else:
            self.set_image('thread_ext_int_image', 'thread_ext_button.jpg')
            self.thread_major_dia_label.set_label('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >X    Start :</span>')
            self.thread_minor_dia_label.set_label('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >X    End :</span>')
            self.conv_thread_ext_int = 'external'

        self.set_threading_bk_images()
        model = self.thread_chart_combobox.get_model()
        active_text = self.thread_chart_combobox.get_active()
        title = model[active_text][0]
        thread_str = model[active_text][1].strip()

        if title.upper().find('NPT') != -1:
            # if 'NPT' in title or 'npt' in title:
            (tpu, external_pitch_dia_s, internal_pitch_dia_s,
             thread_height_max_s, thread_height_min_s, effective_length_s,
             pipe_od, hole_id) = (
                 [x.strip() for x in thread_str.split(',') if x.strip()])

            external_pitch_dia = float(external_pitch_dia_s)
            internal_pitch_dia = float(internal_pitch_dia_s)
            mean_thread_height = (float(thread_height_max_s) + float(thread_height_min_s)) / 2.0
            effective_length   = float(effective_length_s)

            ext_major = external_pitch_dia + mean_thread_height
            ext_minor = external_pitch_dia - mean_thread_height
            int_major = internal_pitch_dia + mean_thread_height
            int_minor = internal_pitch_dia - mean_thread_height

            valid, z_start, error_msg  = self.conversational.validate_param(self.thread_dro_list['thread_z_start_dro'])
            valid, z_end, error_msg    = self.conversational.validate_param(self.thread_dro_list['thread_z_end_dro'])
            valid, tool_clr, error_msg = self.conversational.validate_param(self.thread_dro_list['thread_tc_dro'])
            valid, lead, error_msg     = self.conversational.validate_param(self.thread_dro_list['thread_lead_dro'])

            thread_range = math.fabs(z_end - z_start) + lead
            # Pipe threads have 1 degree 47 minute taper angle to the center
            # axis, or 1:16 on the diameter
            # angle = 1.7833 degrees, sin(1.7833 degrees) = 0.031062
            dx = thread_range * 0.031062

            if self.conv_thread_ext_int == 'external':
                taper = dx
                self.conv_thread_note = '(Note: for %s External Thread)\n(Pipe OD = %s)\n(    for use with OD Turn and Chamfer)\n(Effective Thread Length = %s)\n(    use as the distance between z_start and z_end in Chamfer)\n(    use an angle of 1.78 degrees)' % (title, pipe_od, effective_length_s)
                #tpu, external_pitch_dia_s, internal_pitch_dia_s, thread_height_max_s, thread_height_min_s, effective_length_s

            else:
                taper = dx * -1
                self.conv_thread_note = '(Note: for %s Internal Thread)\n(Hole ID = %s)\n(    for use with ID Turn and Chamfer)\n(Effective Thread Length = %s)\n(    use as the distance between z_start and z_end in Chamfer)\n(    use an angle of 1.78 degrees)' % (title, hole_id, effective_length_s)
        self.load_title_dro()

    def thread_combo_spec(self, text=None):
        return TormachUIBase.get_set_combo_literal(self.thread_chart_combobox, text)

    def thread_rh_lh_to_str(self):
        return 'Right Hand' if self.conv_thread_rh_lh == 'rh' else 'Left Hand'

    def set_threading_bk_images(self):
        thread_fixed = self.builder.get_object('thread_fixed')
        lead_label = self.builder.get_object('thread_lead_text')
        lead_dro = self.thread_dro_list['thread_lead_dro']
        if self.conv_thread_rh_lh == 'lh':
            self.set_image('thread_rh_lh_image', 'thread_LH_button.png')
            new_page_image = 'lathe_thread_lh_external.png' if self.conv_thread_ext_int == 'external' else 'lathe_thread_lh_internal.png'
            thread_fixed.move(lead_label,162,295)
            thread_fixed.move(lead_dro,162,320)
        else:
            self.set_image('thread_rh_lh_image', 'thread_RH_button.png')
            new_page_image = 'lathe_thread_external.svg' if self.conv_thread_ext_int == 'external' else 'lathe_thread_internal.svg'
            thread_fixed.move(lead_label,130,295)
            thread_fixed.move(lead_dro,130,320)
        self.set_image('conv_thread_image', new_page_image)

    def toggle_thread_rh_lh_button(self):
        self.conv_thread_rh_lh = 'lh' if self.conv_thread_rh_lh == 'rh' else 'rh'
        self.set_threading_bk_images()

    def on_thread_ext_int_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_thread_external_internal_button()

    def on_thread_rh_lh_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.toggle_thread_rh_lh_button()

    def on_thread_tool_num_dro_activate(self, widget, data=None):
        if not self._test_on_activate_tool_dro(widget): return
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_tool_num_dro')
        self.thread_dro_list[where_to].grab_focus()

    def on_thread_z_start_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate thread length and push to length DRO
        try:
            z_end = float(self.thread_dro_list['thread_z_end_dro'].get_text())
        except:
            z_end = 0

        self._calc_taper()
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_z_start_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_z_end_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        # calculate thread length and push to length DRO
        try:
            z_start = float(self.thread_dro_list['thread_z_start_dro'].get_text())
        except:
            z_start = 0

        self._calc_taper()
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_z_end_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_spindle_rpm_dro_activate(self, widget, data=None):
        pitch = self.thread_dro_list['thread_pitch_dro'].get_text()
        max_vel = self.inifile.find("AXIS_2", "MAX_VELOCITY")
        (valid, rpm, error_msg) = self.conversational.validate_param(widget, self.g21, pitch, max_vel)
        if not valid:
            if not data or not isinstance(data, str) or data != 'no_report_error':
                self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_short_format % rpm)

        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_spindle_rpm_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_minor_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        self.on_thread_doc_dro_activate(self.thread_dro_list["thread_doc_dro"])
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_minor_dia_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_major_dia_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        self.on_thread_doc_dro_activate(self.thread_dro_list["thread_doc_dro"])
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_major_dia_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_tpu_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_tpu_format % value)

        pitch = 1 / value
        self.thread_dro_list['thread_pitch_dro'].set_text(self.dro_long_format % pitch)
        cparse.clr_alarm(self.thread_dro_list['thread_pitch_dro'])

        self.on_thread_spindle_rpm_dro_activate(self.thread_dro_list["thread_spindle_rpm_dro"])
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_tpu_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_pitch_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        tpu = 1 / value
        self.thread_dro_list['thread_tpu_dro'].set_text(self.dro_tpu_format % tpu)

        # Normally the second arg would be 'thread_pitch_dro' but it is not in the focus list.
        self.on_thread_spindle_rpm_dro_activate(self.thread_dro_list["thread_spindle_rpm_dro"])
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_pass_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_doc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            if not data or not isinstance(data, str) or data != 'no_report_error':
                self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        FSBase.dro_on_activate(widget, self.dro_long_format % value)

        # TODO - wrap this in error handling.  This will break if bad values are entered in these DROs.  We should ideally highlight which DRO has the bad entry
        try:
            tool_clearance = float(self.thread_dro_list['thread_tc_dro'].get_text())
            doc = float(self.thread_dro_list['thread_doc_dro'].get_text())
            major_dia = float(self.thread_dro_list['thread_major_dia_dro'].get_text())
            minor_dia = float(self.thread_dro_list['thread_minor_dia_dro'].get_text())

            depth = math.fabs(tool_clearance) + math.fabs(doc)
            full_dia_depth = math.fabs(tool_clearance)
            cut_increment = math.fabs(doc)
            k_number = math.fabs(major_dia - minor_dia)
            end_depth = math.fabs(k_number) + math.fabs(tool_clearance)
            degression = 2

            if doc > k_number:
                self.error_handler.write("Depth of cut must be smaller than (major - minor dia)/2", ALARM_LEVEL_LOW)

            tpass = self.conversational.calc_num_threading_passes(depth, end_depth, full_dia_depth, cut_increment, degression)
            self.thread_dro_list['thread_pass_dro'].set_text(self.dro_short_format % tpass)
            if tpass > THREAD_MAX_PASSES:
                msg = "Depth of cut results in too many passes. Number of passes must be less than {}".format(THREAD_MAX_PASSES)
                self.error_handler.write(msg, ALARM_LEVEL_LOW)
                cparse.raise_alarm(widget, msg)
                cparse.raise_alarm(self.thread_dro_list['thread_pass_dro'], msg)
            else:
                cparse.clr_alarm(widget)
                cparse.clr_alarm(self.thread_dro_list['thread_pass_dro'])
        except:
            self.error_handler.write("insufficient or inappropriate entries on threading conversational page to calculate number of passes", ALARM_LEVEL_LOW)

        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_pass_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def _calc_thread_doc(self, tc, k_num, passes):
        depth = full_dia_depth = math.fabs(tc)
        end_depth = math.fabs(k_num) + depth
        degression = 2

        imin = (end_depth - depth)/passes
        imax = end_depth - depth
        imid = (imin + imax)/2
        i = 1

        while i<100:
            i += 1
            tpass = self.conversational.calc_num_threading_passes(depth, end_depth, full_dia_depth, imid, degression)
            if tpass == passes: break
            if tpass > passes:
                imin = imid
                imid = (imin + imax) / 2
            elif tpass < passes:
                imax = imid
                imid = (imin + imax) / 2
        return (tpass, imid)

    def on_thread_pass_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return

        req_passes = int(value)

        # TODO - wrap this in error handling.  This will break if bad values are entered in these DROs.  We should ideally highlight which DRO has the bad entry
        try:
            # TODO - better user entry validation here
            tool_clearance = float(self.thread_dro_list['thread_tc_dro'].get_text())
            major_dia = float(self.thread_dro_list['thread_major_dia_dro'].get_text())
            minor_dia = float(self.thread_dro_list['thread_minor_dia_dro'].get_text())
            tpass, imid = self._calc_thread_doc(tool_clearance, math.fabs(major_dia - minor_dia), req_passes)

            self.thread_dro_list["thread_doc_dro"].set_text(self.dro_long_format % imid)
            widget.set_text(self.dro_short_format % tpass)
            if tpass > THREAD_MAX_PASSES:
                msg = "Number of passes must be less than {}.".format(THREAD_MAX_PASSES)
                self.error_handler.write(msg, ALARM_LEVEL_LOW)
                cparse.raise_alarm(widget, msg)
                cparse.raise_alarm(self.thread_dro_list['thread_doc_dro'], msg)
            else:
                FSBase.dro_on_activate(widget, self.dro_short_format % tpass)
                cparse.clr_alarm(widget)
                cparse.clr_alarm(self.thread_dro_list['thread_doc_dro'])
        except:
            self.error_handler.write("Insufficient or inappropriate entries on threading conversational page to calculate number of passes.", ALARM_LEVEL_LOW)

        # Normally the second arg would be 'thread_pass_dro' but it is not in the focus list.
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_pass_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_tc_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_tc_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def on_thread_lead_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        self._calc_taper()
        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_lead_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    def _calc_taper(self, set_taper = True):
        title = self.thread_chart_combobox.get_active_text()
        # the title may be 'None' or empty
        if not title: return None
        if title.upper().find('NPT')<0: return None
        valid, z_start, error_msg  = self.conversational.validate_param(self.thread_dro_list['thread_z_start_dro'])
        if not valid: return None
        valid, z_end, error_msg    = self.conversational.validate_param(self.thread_dro_list['thread_z_end_dro'])
        if not valid: return None
        valid, lead, error_msg     = self.conversational.validate_param(self.thread_dro_list['thread_lead_dro'])
        if not valid: return None

        thread_length = math.fabs(z_end - z_start) + lead
        # Pipe threads have 1 degree 47 minute taper angle to the center
        # axis, or 1:32 on the radius
        # angle = 1.7899 degrees, tan(1.7833 degrees) = 0.03125 (remarkable)!
        taper = thread_length * 0.03125 * (1.0 if self.conv_thread_ext_int == 'external' else -1.0)
        self.thread_dro_list['thread_taper_dro'].set_text(self.dro_long_format % taper)
        return (taper,z_start,z_end,lead)



    def on_thread_chart_changed(self, widget, data=None):
        # get active entry, populate DROs
        model = widget.get_model()
        active_text = widget.get_active()
        thread_str = ''
        # mill analogous code returns if active_text == -1; we can't immediate -- must set note variable??
        if active_text != -1:
            thread_str = model[active_text][1].strip()

        if len(thread_str) == 0 or thread_str == THREAD_CUSTOM_DELIMITER or thread_str == THREAD_TORMACH_DELIMITER:
            # empty or delimiter string selected, do nothing
            self.thread_chart_notes_label.set_markup(
                '<span weight="regular" font_desc="Roboto Condensed 9" foreground="white"> </span>')
            return

        title = model[active_text][0]
        if title.upper().find('NPT') != -1:
            # if 'NPT' in title or 'npt' in title:
            (tpu, external_pitch_dia_s, internal_pitch_dia_s,
             thread_height_max_s, thread_height_min_s, effective_length_s,
             pipe_od, hole_id) = (
                 [x.strip() for x in thread_str.split(',') if x.strip()])

            external_pitch_dia = float(external_pitch_dia_s)
            internal_pitch_dia = float(internal_pitch_dia_s)
            mean_thread_height = (float(thread_height_max_s) + float(thread_height_min_s)) / 2.0
            effective_length   = float(effective_length_s)

            ext_major = external_pitch_dia + mean_thread_height
            ext_minor = external_pitch_dia - mean_thread_height
            int_major = internal_pitch_dia + mean_thread_height
            int_minor = internal_pitch_dia - mean_thread_height

            valid, z_start, error_msg  = self.conversational.validate_param(self.thread_dro_list['thread_z_start_dro'])
            valid, z_end, error_msg    = self.conversational.validate_param(self.thread_dro_list['thread_z_end_dro'])
            valid, tool_clr, error_msg = self.conversational.validate_param(self.thread_dro_list['thread_tc_dro'])
            valid, lead, error_msg     = self.conversational.validate_param(self.thread_dro_list['thread_lead_dro'])

            thread_range = math.fabs(z_end - z_start) + lead
            # Pipe threads have 1 degree 47 minute taper angle to the center
            # axis, or 1:32 on the radius
            # angle = 1.7899 degrees, tan(1.7833 degrees) = 0.03125 (remarkable)!
            dx = thread_range * 0.03125

            if self.conv_thread_ext_int == 'external':
                taper = dx
                self.conv_thread_note = '(Note: for %s External Thread)\n(Pipe OD = %s)\n(    for use with OD Turn and Chamfer)\n(Effective Thread Length = %s)\n(    use as the distance between z_start and z_end in Chamfer)\n(    use an angle of 1.78 degrees)' % (title, pipe_od, effective_length_s)
                #tpu, external_pitch_dia_s, internal_pitch_dia_s, thread_height_max_s, thread_height_min_s, effective_length_s

            else:
                taper = dx * -1
                self.conv_thread_note = '(Note: for %s Internal Thread)\n(Hole ID = %s)\n(    for use with ID Turn and Chamfer)\n(Effective Thread Length = %s)\n(    use as the distance between z_start and z_end in Chamfer)\n(    use an angle of 1.78 degrees)' % (title, hole_id, effective_length_s)

            pitch = 1.0 / float(tpu)
            sharp_thread_height = pitch / 1.15470  # pitch / (2 * tan(30 degrees))
            tip_truncation = (sharp_thread_height - mean_thread_height) / 2

            note = ('Tip truncation = %s\nEffective thread length = %s'
                    % (self.dro_long_format, self.dro_long_format)
                    % (tip_truncation, effective_length))
            self.thread_chart_notes_label.set_markup(
                '<span weight="regular" font_desc="Roboto Condensed 9" foreground="white">%s</span>' % note)

        else:
            self.thread_chart_notes_label.set_markup(
                '<span weight="regular" font_desc="Roboto Condensed 9" foreground="white"> </span>')

            # parse space delimited string in text
            tpu, ext_major, ext_minor, int_major, int_minor = [x.strip() for x in thread_str.split(',') if x.strip()]
            taper = 0.0

        # use external or internal diameters as required to set DROs
        if self.conv_thread_ext_int == 'external':
            major_diameter = float(ext_major)
            minor_diameter = float(ext_minor)
        else:
            major_diameter = float(int_major)
            minor_diameter = float(int_minor)

        #check for front or rear tool post
        valid, tool_number, error =  self.conversational.validate_param(self.thread_dro_list['thread_tool_num_dro'])
        if not valid:
            self.error_handler.write('Conversational Threading entry error - ' + error)
        tool_type = self.get_tool_type(tool_number)
        if 'ftp' in tool_type:
            major_diameter *= -1
            minor_diameter *= -1

        # set the DROs
        tpu = float(tpu)
        pitch = 1 / tpu
        self.thread_dro_list['thread_major_dia_dro'].set_text(self.dro_long_format % major_diameter)
        self.thread_dro_list['thread_minor_dia_dro'].set_text(self.dro_long_format % minor_diameter)
        self.thread_dro_list['thread_tpu_dro'].set_text(self.dro_tpu_format % tpu)
        self.thread_dro_list['thread_pitch_dro'].set_text(self.dro_long_format % pitch)
        self.thread_dro_list['thread_taper_dro'].set_text(self.dro_long_format % taper)

        # re-calc number of passes, re-check rpm
        self.on_thread_doc_dro_activate(self.thread_dro_list["thread_doc_dro"], 'no_report_error')
        self.on_thread_spindle_rpm_dro_activate(self.thread_dro_list["thread_spindle_rpm_dro"], 'no_report_error')
        return

    def on_thread_taper_dro_activate(self, widget, data=None):
        (valid, value, error_msg) = self.conversational.validate_param(widget, self.g21)
        if not valid:
            self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
            return
        widget.set_text(self.dro_long_format % value)

        where_to = self.next_conv_dro(self.thread_focus_list, 'thread_taper_dro')
        self.thread_dro_list[where_to].grab_focus()
        return

    # -------------------------------------------------------------------------------------------------
    # end of conversational tab callbacks
    # -------------------------------------------------------------------------------------------------

    # helper function for issuing MDI commands
    def issue_mdi(self, mdi_command):
        if self.moving():
            self.error_handler.write("Machine is moving. Not issuing MDI command: " + mdi_command, ALARM_LEVEL_LOW)
            return

        self.error_handler.write("issuing MDI command: " + mdi_command, ALARM_LEVEL_DEBUG)
        self.ensure_mode(linuxcnc.MODE_MDI)
        self.command.mdi(mdi_command)

    def issue_toolchange_command(self, tool_number):
        # build T MDI command
        if ((self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_TURRET) and (self.hal['door-switch'] == 1) and (tool_number < 9)):
            self.error_handler.write("Must close enclosure door before indexing turret")
            return
        t_command = "T%d" % (tool_number)
        self.issue_mdi(t_command)
        # prevent unsettling flicker of tool number as old status.tool_no gets stuffed into dro on 50ms loop
        # before new tool takes hold
        # NB - not a good way of accomplishing this.
        #self.command.wait_complete()
        tool_type = self.get_tool_type(tool_number)
        self.clear_tool_select_images(lathe.get_offset_tool_type_image(tool_type), True)
        self.set_touch_x_z_leds(tool_number)

    def issue_g10(self, axis, offset_register, value, data=None):
        # don't allow offset change without axes referenced
        if not (self.x_referenced and self.z_referenced):
            self.error_handler.write("Must reference X and Z axes before issuing command", ALARM_LEVEL_MEDIUM)
            return
        g10_command = "G10 L1 P%d %s%f" %(offset_register, axis, value)
        self.issue_mdi(g10_command)
        # prevent race condition when setting both geo and wear almost simultaneously
        self.command.wait_complete()
        do_refresh = not isinstance(data,dict) or 'cmd' not in data or 'refresh' in data['cmd']
        # reload tool liststore if wear offsets were changed
        if offset_register < 10000 and do_refresh:
            self.refresh_tool_liststore()
        else:
            # we're setting a geometery offset, so set touch x or z button leds appropriately
            if value == 0:
                if axis == 'X':
                    self.set_image('touch_x_image', 'touch_x_black_led.png')
                if axis == 'Z':
                    self.set_image('touch_z_image', 'touch_z_black_led.png')
            else:
                if axis == 'X':
                    self.set_image('touch_x_image', 'touch_x_green_led.png')
                if axis == 'Z':
                    self.set_image('touch_z_image', 'touch_z_green_led.png')

    def save_conv_parameters(self, dro_list):
        # loop through conv dro list and save values to redis
        for name, dro in self.conv_dro_list.iteritems():
            val = dro.get_text()
            self.redis.hset('conversational', name, val)
        for name, dro in dro_list.iteritems():
            val = dro.get_text()
            self.redis.hset('conversational', name, val)
        return

    def restore_conv_parameters(self):
        conv_dict = self.redis.hgetall('conversational')
        for dro_name , val in conv_dict.iteritems():
            try:
                if 'conv' in dro_name:
                    self.conv_dro_list[dro_name].set_text(val)
                if 'od_turn' in dro_name:
                    self.od_turn_dro_list[dro_name].set_text(val)
                if 'id_basic' in dro_name:
                    self.id_basic_dro_list[dro_name].set_text(val)
                if 'id_turn' in dro_name:
                    self.id_turn_dro_list[dro_name].set_text(val)
                if 'profile' in dro_name:
                    if dro_name == 'profile_tool_num_dro':
                        self.profile_dro_list[dro_name].set_text(val)
                if 'face' in dro_name:
                    if not 'id_turn' in dro_name:
                        self.face_dro_list[dro_name].set_text(val)
                if 'corner' in dro_name:
                    if 'chamfer' in dro_name:
                        if 'od' in dro_name:
                            self.corner_chamfer_od_dro_list[dro_name].set_text(val)
                        else:  # 'id'
                            self.corner_chamfer_id_dro_list[dro_name].set_text(val)
                    else:  # 'radius'
                        if 'od' in dro_name:
                            self.corner_radius_od_dro_list[dro_name].set_text(val)
                        else:  # 'id'
                            self.corner_radius_id_dro_list[dro_name].set_text(val)
                if 'groove' in dro_name:
                    self.groove_dro_list[dro_name].set_text(val)
                if 'part' in dro_name:
                    self.part_dro_list[dro_name].set_text(val)
                if 'drill' in dro_name:
                    self.drill_dro_list[dro_name].set_text(val)
                if 'tap_' in dro_name:
                    self.tap_dro_list[dro_name].set_text(val)
                if 'thread' in dro_name:
                    self.thread_dro_list[dro_name].set_text(val)
            except:
                pass
        return


    # debug only??
    def get_lcnc_mode_string(self, mode):
        tmp_str = 'unknown'
        if mode == linuxcnc.MODE_MANUAL:
            tmp_str = 'MODE_MANUAL'
        elif mode == linuxcnc.MODE_AUTO:
            tmp_str = 'MODE_AUTO'
        elif mode == linuxcnc.MODE_MDI:
            tmp_str = 'MODE_MDI'
        return tmp_str

    def get_lcnc_interp_string(self, state):
        tmp_str = 'unknown'
        if state == linuxcnc.INTERP_IDLE:
            tmp_str = 'INTERP_IDLE'
        elif state == linuxcnc.INTERP_READING:
            tmp_str = 'INTERP_READING'
        elif state == linuxcnc.INTERP_PAUSED:
            tmp_str = 'INTERP_PAUSED'
        elif state == linuxcnc.INTERP_WAITING:
            tmp_str = 'INTERP_WAITING'
        return tmp_str

    def get_lcnc_state_string(self, state):
        tmp_str = 'unknown'
        if state == linuxcnc.STATE_ESTOP:
            tmp_str = 'STATE_ESTOP'
        elif state == linuxcnc.STATE_ESTOP_RESET:
            tmp_str = 'STATE_ESTOP_RESET'
        elif state == linuxcnc.STATE_OFF:
            tmp_str = 'STATE_OFF'
        elif state == linuxcnc.STATE_ON:
            tmp_str = 'STATE_ON'
        return tmp_str

    def check_console_inputs(self):
        if self.hal['console-cycle-start']:
            self.enqueue_button_press_release(self.button_list['cycle_start'])
            self.hal['console-cycle-start'] = False

        if self.hal['console-feedhold']:
            self.enqueue_button_press_release(self.button_list['feedhold'])
            self.hal['console-feedhold'] = False

        #check if console is connected on USB, disable override sliders if so
        if self.hal['console-device-connected'] == True:
            self.set_feedrate_override(self.hal['console-feed-override'] * 100.0)
            self.set_spindle_override(self.hal['console-rpm-override'] * 100.0)
            self.set_maxvel_override(self.hal['console-rapid-override'] * 100.0)

    # called every 500 milliseconds to update various slower changing DROs and button images
    def status_periodic_500ms(self):
        if 'launch_test' in self.configdict["pathpilot"] and self.configdict["pathpilot"]["launch_test"]:
            self.quit()

        TormachUIBase.status_periodic_500ms(self)

        self.check_console_inputs()

        if self.hal['mesa-watchdog-has-bit']:
            # problem! the Mesa card watchdog has bitten
            # high priority warning
            if not self.mesa_watchdog_has_bit_seen:
                # set state to ESTOP
                self.mesa_watchdog_has_bit_seen = True
                self.command.state(linuxcnc.STATE_ESTOP)
                self.error_handler.write("Machine interface error. Check cabling and power to machine and then press RESET.", ALARM_LEVEL_MEDIUM)

                # unreference X, Y, and Z
                if self.status.homed[0]:
                    self.command.unhome(0)
                    self.command.wait_complete()
                if self.status.homed[1]:
                    self.command.unhome(1)
                    self.command.wait_complete()
                if self.status.homed[2]:
                    self.command.unhome(2)
                    self.command.wait_complete()

        # active gcodes label
        if not self.suppress_active_gcode_display:
            active_gcodes = self.active_gcodes()
            self.active_gcodes_label.set_text(" ".join(active_gcodes))

        # reset button
        if self.status.task_state == linuxcnc.STATE_ESTOP or \
           self.status.task_state == linuxcnc.STATE_ESTOP_RESET or \
           self.status.task_state == linuxcnc.STATE_OFF:
            self.load_reset_image('blink')    # blink
            self.hal['console-led-blue'] = not self.hal['console-led-blue']
            self.hide_m1_image()
        else:
            # load white image
            self.load_reset_image('white')
            self.hal['console-led-blue'] = False
            self.suppress_active_gcode_display = False

        if self.hal['machine-ok'] == False:
            # machine-ok is False
            if self.estop_alarm == False and self.display_estop_msg:
                # only do this once per press press of reset
                # and don't alarm at startup
                self.display_estop_msg = False
                self.error_handler.write(ESTOP_ERROR_MESSAGE, ALARM_LEVEL_MEDIUM)

                self.call_ui_hook('estop_event')

                # unreference X, Y, and Z
                if self.status.homed[0]:
                    self.command.unhome(0)
                    self.command.wait_complete()
                if self.status.homed[1]:
                    self.command.unhome(1)
                    self.command.wait_complete()
                if self.status.homed[2]:
                    self.command.unhome(2)
                    self.command.wait_complete()

            # set to true to prevent these messages from stacking up.
            # cleared in reset button handler
            self.estop_alarm = True
            self.limit_switches_seen = 0

        else:
            # machine-ok is True
            # check limit switches X Y Z status

            if self.limit_switches_seen != 0:

                # here is where limit switch error messages get generated after a 600 millisecond delay.
                # that insures that we've been through the 500ms periodic once before.  This is needed
                # so that machine-ok has a chance to go down in a real e-stop power cycle scenario and
                # we don't generate additional red herring limit switch error messages.

                # we don't have to check if we were homing in here because self.limit_switches_seen is only
                # set by limit switch errors reported by LinuxCNC (and it doesn't do that during homing).

                time_now = time.time()

                if self.machineconfig.in_rapidturn_mode():
                    # there are 3 separate limit switches
                    if self.limit_switches_seen & 1:
                        if (time_now - self.limit_switches_seen_time) >= 0.6:
                            error_msg = X_LIMIT_ERROR_MESSAGE
                            if self.status.homed[0]:
                                self.command.unhome(0)
                                self.command.wait_complete()
                                self.error_handler.log("X unhomed")
                            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                            self.limit_switches_seen &= ~1

                    if self.limit_switches_seen & 2:
                        if (time_now - self.limit_switches_seen_time) >= 0.6:
                            error_msg = Y_LIMIT_ERROR_MESSAGE
                            if self.status.homed[1]:
                                self.command.unhome(1)
                                self.command.wait_complete()
                                self.error_handler.log("Y unhomed")
                            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                            self.limit_switches_seen &= ~2

                    if self.limit_switches_seen & 4:
                        if (time_now - self.limit_switches_seen_time) >= 0.6:
                            error_msg = Z_LIMIT_ERROR_MESSAGE
                            if self.status.homed[2]:
                                self.command.unhome(2)
                                self.command.wait_complete()
                                self.error_handler.log("Z unhomed")
                            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                            self.limit_switches_seen &= ~4
                else:
                    # For a real lathe, the X and Z limit switches are in serial so they will
                    # both appear to have been tripped and we can't definitely say which one.
                    if self.limit_switches_seen & 5:
                        if (time_now - self.limit_switches_seen_time) >= 0.6:
                            error_msg = X_Z_LIMIT_ERROR_MESSAGE
                            if self.status.homed[0]:
                                self.command.unhome(0)
                                self.command.wait_complete()
                                self.error_handler.log("X unhomed")
                            if self.status.homed[2]:
                                self.command.unhome(2)
                                self.command.wait_complete()
                                self.error_handler.log("Z unhomed")
                            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                            self.limit_switches_seen &= ~5

                    if self.limit_switches_seen & 2:
                        if (time_now - self.limit_switches_seen_time) >= 0.6:
                            error_msg = Y_LIMIT_ERROR_MESSAGE
                            if self.status.homed[1]:
                                self.command.unhome(1)
                                self.command.wait_complete()
                                self.error_handler.log("Y unhomed")
                            self.error_handler.write(error_msg, ALARM_LEVEL_MEDIUM)
                            self.limit_switches_seen &= ~2

                # get new info
                self.status.poll()

        # current tool info, save to redis immediately on switch
        if not self.first_run and self.current_tool != self.status.tool_in_spindle:
            self.current_tool = self.status.tool_in_spindle
            self.redis.hset('machine_prefs', 'active_tool', self.current_tool)

        # work dro label
        self.current_work_offset_name = self.get_work_offset_name_from_index(self.status.g5x_index)
        if self.current_work_offset_name != self.prev_work_offset_name:
            self.prev_work_offset_name = self.current_work_offset_name
            self.work_offset_label.set_markup('<span weight="bold" font_desc="Roboto Condensed 12" foreground="white">POS IN {:s}</span>'.format(self.current_work_offset_name))

        # metric/imperial switch
        self.g21 = self.status.gcodes[linuxcnc.G_CODE_UNITS] == 210
        if self.g21 != self.prev_g21:
            self.prev_g21 = self.g21
            self.switch_inch_metric_display()
            self.gremlin_options.update_unit_state()

        gremlin_redraw_needed = False

        # Check if rotation has changed
        if not isequal(self.prev_self_rotation_xy, self.status.rotation_xy):
            # X/Y rotation has changed so set font indicate
            self.error_handler.write("rotation_xy has changed to: %f" % self.status.rotation_xy, ALARM_LEVEL_DEBUG)
            self.prev_self_rotation_xy = self.status.rotation_xy
            if self.status.rotation_xy == 0:
                self.dro_list['dia_dro'].modify_font(self.xy_dro_font_description)
                self.dro_list['z_dro'].modify_font(self.xy_dro_font_description)
            else:
                self.dro_list['dia_dro'].modify_font(self.rotation_xy_dro_font_description)
                self.dro_list['z_dro'].modify_font(self.rotation_xy_dro_font_description)

            # flag a gremlin reload (only acted upon if we aren't executing a program)
            gremlin_redraw_needed = True

        # NOTE: as a workaround for slow UI refreshes, you can remove modes from this list to suppress redraw
        # due to that mode change (e.g. user change via MDI)
        change_flags = self.test_changed_active_g_codes([
            linuxcnc.G_CODE_PLANE,
            linuxcnc.G_CODE_CUTTER_SIDE,
            linuxcnc.G_CODE_UNITS,
            linuxcnc.G_CODE_DISTANCE_MODE,
            linuxcnc.G_CODE_RETRACT_MODE,
            linuxcnc.G_CODE_LATHE_DIAMETER_MODE,
            linuxcnc.G_CODE_DISTANCE_MODE_IJK,
        ])
        gremlin_redraw_needed |= max(change_flags.values())

        # Button LEDs
        # CSS
        self.css_active = self.status.gcodes[linuxcnc.G_CODE_SPINDLE_MODE] == 960
        if self.css_active != self.prev_css_active:
            self.prev_css_active = self.css_active
            self.refresh_css_label()
        # F/ REV button
        if self.f_per_rev_active != self.prev_f_per_rev_active:
            self.prev_f_per_rev_active = self.f_per_rev_active
            if self.f_per_rev_active:
                self.set_image('feed_per_rev_image', 'F-Rev-Green.png')
                self.f_per_min_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="#A19D9F" >/min</span>')
                self.f_per_rev_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >/rev</span>')
            else:
                self.set_image('feed_per_rev_image', 'F-Rev-Black.png')
                self.f_per_min_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >/min</span>')
                self.f_per_rev_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="#A19D9F" >/rev</span>')

        # update elapsed time and time remaining label widgets
        self.update_gcode_time_labels()

        # the gremlin view may need a poke as it could be tracking the current tool and only showing that tool path
        self.gremlin_options.periodic_500ms()

        # NB: status.paused returns true any time single block is active
        # cycle start LED blinks on single block, m01 breaks, or manual tool changes.  only blink when a program is running.
        # returns True only if executing a g code program, False otherwise (including during MDI moves)
        program_running = self.program_running()
        if program_running:
            # only main screen available to user while running code
            # TODO - on error we should diplay alarms tab too.
            if not self.notebook_locked:
                self.hide_notebook_tabs()
                self.notebook_locked = True
            # use spindle_sync for f/rev status until interptime/motiontime disconnect is fixed
            # but only while running code.
            self.f_per_rev_active = self.status.spindle_sync != 0
            self.prev_f_word = abs(self.status.settings[1])
            # Blink CS button when the GUI is waiting for input on tool change, single block, feedhold, etc.
            if (self.single_block_active or self.feedhold_active or self.m01_break_active or (self.hal['tool-change'] and self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_MANUAL)):
                if (self.status.current_vel == 0) and (self.maxvel_override_adjustment.get_value() != 0):
                    self.load_cs_image('blink')
                else:
                    self.load_cs_image('green')
            else:
                self.load_cs_image('green')

        else:
            # many GUI updates only performed when we're not excecuting a g code program
            # unlock notebook
            if self.notebook_locked:
                self.show_enabled_notebook_tabs()
                self.notebook_locked = False
                self.stats_mgr.update_gcode_cycletimes()

            if not is_tuple_equal(self.current_g5x_offset, self.status.g5x_offset):
                self.error_handler.log("500ms status.g5x_offset {:s} vs. current_g5x_offset {:s}".format(self.status.g5x_offset, self.current_g5x_offset))
                self.current_g5x_offset = self.status.g5x_offset
                gremlin_redraw_needed = True

            if not is_tuple_equal(self.current_g92_offset, self.status.g92_offset):
                self.error_handler.log("500ms status.g92_offset {:s} vs. current_g92_offset {:s}".format(self.status.g92_offset, self.current_g92_offset))
                self.current_g92_offset = self.status.g92_offset
                gremlin_redraw_needed = True

            if gremlin_redraw_needed:
                self.error_handler.log("500ms periodic kicking off gremlin redraw because it saw offset change.  g5x_index={:d}".format(self.status.g5x_index))
                self.redraw_gremlin()
                gremlin_redraw_needed = False

            # jog axis enabled update of LEDs
            self.refresh_jog_active_leds()

            # axis ref'ed button LEDs
            self.x_referenced = self.status.homed[0]
            self.y_referenced = self.status.homed[1]
            self.z_referenced = self.status.homed[2]
            if self.x_referenced != self.prev_x_referenced:
                self.prev_x_referenced = self.x_referenced
                if self.x_referenced:
                    self.set_image('ref_x_image', 'Ref_X_Green.png')
                else:
                    self.set_image('ref_x_image', 'Ref_X_Black.png')
            if self.y_referenced != self.prev_y_referenced:
                self.prev_y_referenced = self.y_referenced
                if self.y_referenced:
                    self.set_image('ref_y_image', 'Ref_Y_Green.png')
                else:
                    self.set_image('ref_y_image', 'Ref_Y_Black.png')
            if self.z_referenced != self.prev_z_referenced:
                self.prev_z_referenced = self.z_referenced
                if self.z_referenced:
                    self.set_image('ref_z_image', 'Ref_Z_Green.png')
                else:
                    self.set_image('ref_z_image', 'Ref_Z_Black.png')

            # See if we have a queued axis reference request we should kick off
            if not self.moving():
                try:
                    axis_ix = self.axis_ref_queue.get_nowait()
                    if not self.status.homed[axis_ix]:  # ignore redundant requests as they got twitchy on the button...
                        self.ref_axis(axis_ix)
                except Queue.Empty:
                    pass

            # updates to images/labels on notebook pages other than main
            if self.current_notebook_page_id == 'notebook_offsets_fixed':
                # refresh the work offset liststore
                self.refresh_work_offset_liststore()
                # update tool DRO, but not if the turret fwd button has prelight
                if not (self.dro_list['tool_dro'].masked or self.button_list['turret_fwd'].has_focus()):
                    self.dro_list['tool_dro'].set_text(self.dro_short_format % self.status.tool_in_spindle)
                self.update_tool_orientation_image()
            # display active g code on settings screen
            elif self.current_notebook_page_id == 'notebook_settings_fixed':
                if not self.suppress_active_gcode_display:
                    self.gcodes_display.highlight_active_codes(self.active_gcodes())
            elif self.current_notebook_page_id == 'alarms_fixed':
                if self.settings.usbio_enabled:
                    self.refresh_usbio_interface()

            # f per rev val comes from status if we're not running a program
            self.f_per_rev_active = self.status.gcodes[linuxcnc.G_CODE_FEED_MODE] == 950

            self.load_cs_image('dark')
            # not running a program - handle manual tool change request via MDI.  No need to confirm w/ CS button, just do it.
            if (self.hal['tool-change'] and self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_MANUAL):
                self.hal['manual-tool-changed'] = self.hal['tool-change']

            if self.internet_checker.internet_reachable:
                self.set_image('internet_led', 'LED_button_green.png')
            else:
                self.set_image('internet_led', 'LED_button_black.png')

        # the following updates occur regardless of program_running state:

        turret_error = self.hal['turret-error']
        if (turret_error != 0):
            # the turret experienced an error, stop the tool change (and running program), and report
            self.enqueue_button_press_release(self.button_list['stop'])
            self.error_handler.write("Turret error %d" % turret_error, ALARM_LEVEL_LOW)
            self.hal['turret-error'] = 0

        # todo - do we really need to do this every .5 seconds, even when the info hasn't changed?
        if (self.hal['tool-change'] and self.hal['tool-changer-type'] == TOOL_CHANGER_TYPE_MANUAL):
            # sometimes a timing window here where they've changed tools and pressed cycle
            # start, but we come along and re-paint the tool message.
            # check if the current tool is the same as the requested tool should fix it?
            requested_tool = str(self.hal['tool-prep-number'])
            if self.current_tool != requested_tool:
                if self.program_running():
                    self.set_message_line_text('Change tool to T' + requested_tool)
                    self.blink_tool_request_label(requested_tool)
        else:
            current_tool_string = '{:02d}'.format(self.current_tool)

            # status.tool_offset returns the offset in whatever g20/21 units are current
            # since our hack stores the wear offset number in as the 'w' offset, we'll need to
            # translate this back if we happen to be in G21.
            wear_offset_num = int(round(self.mm_inch_scalar * self.status.tool_offset[8]))
            if wear_offset_num == 0:
                wear_offset_num = ""
            else:
                wear_offset_num = '{:02d}'.format(wear_offset_num)
            self.tool_label.set_text("T:    " + current_tool_string + wear_offset_num)


        # update spindle direction
        self.spindle_direction = self.status.spindle_direction
        if self.spindle_direction != 0:
            # don't flag this if the spindle's not running
            # TODO - this alarm seems to occur often because of CSS at large diameters (e.g. moving to tool change position)
            # We should find a way to fix this...
            self.spindle_range_alarm = self.hal['spindle-range-alarm']
            # don't let these stack up.
            if self.spindle_range_alarm != self.prev_spindle_range_alarm:
                self.prev_spindle_range_alarm = self.spindle_range_alarm
                if self.spindle_range_alarm and not self.machineconfig.in_rapidturn_mode():
                    self.error_handler.write("Commanded spindle speed outside of range for current belt position.  Speed will be clipped to acceptable max/min", ALARM_LEVEL_LOW)

        # Detect hang waiting on spindle during synched move
        if self.status.waiting_on_spindle:
            # Motion hung:  increment counter
            self.f_per_rev_spindle_counter += 1
            # ...and error after timeout in INI file
            if self.f_per_rev_spindle_counter == \
               self.f_per_rev_spindle_timeout*2:
                self.error_handler.write(
                    "Synchronized motion waiting on spindle for %d seconds" %
                    self.f_per_rev_spindle_timeout)
        else:
            # spindle_turning or not f_per_rev_active:  clear counter
            self.f_per_rev_spindle_counter = 0

        if self.spindle_direction != self.prev_spindle_direction:
            self.prev_spindle_direction = self.spindle_direction
            if self.spindle_direction == -1:
                # CCW
                self.set_image('rev_image', 'REV_Green.jpg')
                self.set_image('fwd_image', 'FWD_Black.jpg')
            elif self.spindle_direction == 0:
                # Off
                self.set_image('rev_image', 'REV_Black.jpg')
                self.set_image('fwd_image', 'FWD_Black.jpg')
            elif self.spindle_direction == 1:
                # CW
                self.set_image('rev_image', 'REV_Black.jpg')
                self.set_image('fwd_image', 'FWD_Green.jpg')

        # DROs

        # spindle rpm and css DROs
        # if the machine is moving, use S value from HAL spindle-speed-out and F value from status.current_vel
        if self.moving():
            if not self.dros_locked:
                self.dros_locked = True
                # lock out DROs
                for name, dro in self.dro_list.iteritems():
                    dro.set_can_focus(False)
            self.rpm = int(60 * self.hal["spindle-speed-out"])
            # CS (in ft/min) = rpm * dia (in inches) * pi / 12
            surface_speed = abs((self.rpm * self.dia * 3.1416) / 12)
            # in metric, dia is in mm, but surface speed reported in meters
            if self.g21:
                # dia will be in mm, so 12/1000 gets us from the calc in inches to the calc in mm
                # seems clunky but saves an if statement
                surface_speed = surface_speed * 12/1000
            feed_per_min = self.status.current_vel * 60
            self.dro_list['spindle_rpm_dro'].set_text(self.dro_short_format % abs(self.rpm))
            self.dro_list['spindle_css_dro'].set_text(self.dro_short_format % abs(surface_speed))
            self.dro_list['feed_per_min_dro'].set_text(self.dro_medium_format % (self.mm_inch_scalar * feed_per_min))
            # calculate the F/rev DRO and stuff it
            if self.rpm != 0:
                self.dro_list['feed_per_rev_dro'].set_text(self.dro_long_format % (self.mm_inch_scalar * feed_per_min / self.rpm))
            # otherwise if we're not running, use the buggy status.settings values

        else:
            # if gcode file is loaded and has changed on disk since loading, reload it
            if self.current_gcode_file_path != '':
                self.check_for_gcode_program_reload()

            # check custom thread files for changes, reload if necessary
            self.thread_custom_file_reload_if_changed()

            if self.dros_locked:
                self.dros_locked = False
                # unlock DROs
                for name, dro in self.dro_list.iteritems():
                    dro.set_can_focus(True)
            if not (self.dro_list['spindle_rpm_dro'].masked or self.dro_list['spindle_css_dro'].masked):
                self.s_word  = self.status.settings[2]
                # if we're in CSS (G96), settings[2] contains the S word in Ft/min or M/min, so reassign surface speed to rpm
                if self.css_active:
                    surface_speed = self.s_word
                    if self.dia != 0.0:
                        self.rpm = 12 * surface_speed / (self.dia * 3.1416)
                        if self.g21:
                            # get rid of 12 inches/ft adjustment
                            self.rpm = self.rpm * 1000 / 12
                    else:
                        self.rpm = self.max_rpm
                    if abs(self.rpm) > self.max_rpm:
                        self.rpm = self.max_rpm
                else:
                    self.rpm = self.s_word
                    surface_speed = (self.rpm * self.dia * 3.1416) / 12
                    if self.g21:
                        surface_speed = surface_speed * 12/1000

                self.dro_list['spindle_rpm_dro'].set_text(self.dro_short_format % abs(self.rpm))
                self.dro_list['spindle_css_dro'].set_text(self.dro_short_format % abs(surface_speed))
            # feed per rev and per rpm
            if not (self.dro_list['feed_per_min_dro'].masked or self.dro_list['feed_per_rev_dro'].masked):
                self.f_word = abs(self.status.settings[1])
                # If we're in feed/rev, the F word has the f/rev value so we need to calc f/min
                if self.f_per_rev_active:
                    # until motion and interp are synched, we've got two possible sources of information here:
                    # uu_per_rev comes down from motion and displays the last feed/rev setting on a motion segment
                    # f_word comes from the interp and displays the value off the interp list, which if a program
                    # is stopped in the middle may display future instead of current information
                    if self.f_word != self.prev_f_word:
                        # someone's sent an MDI statement and changed the f_word, so DON'T use the uu_per_rev setting
                        # cycle start callback will set prev_f_word back equal to f_word, and therefore reset this to display the uu_per_rev val.
                        feed_per_rev = self.f_word
                    else:
                        # else no one's messed with our f word, so let's use the motion settings (which are in g20 units only!!!)
                        feed_per_rev = self.mm_inch_scalar * self.status.uu_per_rev
                    feed_per_min = feed_per_rev * self.rpm
                else:
                    feed_per_min = self.f_word
                    if self.rpm != 0:
                        feed_per_rev = self.f_word / self.rpm
                    else:
                        feed_per_rev = 0
                # stuff the DROs
                self.dro_list['feed_per_min_dro'].set_text(self.dro_medium_format % abs(feed_per_min))
                self.dro_list['feed_per_rev_dro'].set_text(self.dro_long_format % abs(feed_per_rev))

        # debug info - observe mode/status changes
        # this is far from perfect: the mode can change and return during time elapsed between these checks
        if self.status.task_mode != self.prev_lcnc_task_mode:
            # state changed, print to console
            self.error_handler.write('LinuxCNC status.task_mode change was %s is now %s' % (self.get_lcnc_mode_string(self.prev_lcnc_task_mode), self.get_lcnc_mode_string(self.status.task_mode)), ALARM_LEVEL_DEBUG)
            self.prev_lcnc_task_mode = self.status.task_mode
        if self.prev_lcnc_interp_state != self.status.interp_state:
            # interpreter state changed
            self.error_handler.write('LinuxCNC interp_state change was %s is now %s' % (self.get_lcnc_interp_string(self.prev_lcnc_interp_state), self.get_lcnc_interp_string(self.status.interp_state)), ALARM_LEVEL_DEBUG)
            self.prev_lcnc_interp_state = self.status.interp_state

            # kludge to rewind program after interp goes idle (usually when program is done at M30)
            if "IDLE" in self.get_lcnc_interp_string(self.status.interp_state):
                self.gcodelisting_mark_start_line(1)

            # State changes may result from M01 and a following cycle
            # start; display/hide any image specified in a comment
            # following M01
            if self.status.interp_state == linuxcnc.INTERP_PAUSED:
                self.show_m1_image()
                self.lineno_for_last_m1_image_attempt = self.status.current_line
                # prototype alert code
                #self.send_m1_alert()

        if self.status.interp_state == linuxcnc.INTERP_PAUSED:
            # we may have two M00 or M01 breaks in a row that try to show images.
            # in that situation, there isn't a state change, but the self.status.current_line will have changed
            if self.lineno_for_last_m1_image_attempt != self.status.current_line:
                self.show_m1_image()
                self.lineno_for_last_m1_image_attempt = self.status.current_line

        if self.prev_task_state != self.status.task_state:
            self.error_handler.write("status.task_state was %s is now %s" % (self.get_lcnc_state_string(self.prev_task_state), self.get_lcnc_state_string(self.status.task_state)), ALARM_LEVEL_DEBUG)
            self.prev_task_state = self.status.task_state

        # log abnormal changes in cpu utilization
        usage = self.proc.cpu_percent()
        usage_delta = abs(usage - self.cpu_usage)
        if usage > LOG_CPU_USAGE_THRESHOLD_NOISEFLOOR and (usage_delta > 50 or usage > LOG_CPU_USAGE_THRESHOLD_ALWAYS):
            self.error_handler.write("CPU usage was %.1f, is now %.1f" % (self.cpu_usage, usage), ALARM_LEVEL_DEBUG)
            self.cpu_usage = usage


    # called every 50 milliseconds to update faster changing indicators
    # the '@profile' below is for use with line profiling http://pythonhosted.org/line_profiler/
    #@profile
    def status_periodic_50ms(self):
        # check for presence, update inputs
        self.check_console_inputs()

        # check button events from keyboard shortcuts
        self.check_keyboard_shortcut_fifo()

        self.axis_motor_poll(2)
        self.axis_motor_poll(0)

        # lazily poke the tooltip manager Real Soon Now
        glib.idle_add(tooltipmgr.TTMgr().on_periodic_timer)

        # get new info
        self.status.poll()

        # Apply the most recent value we've seen from dragging any override sliders
        # The most recent value from the UI callbacks is stored and only acted upon
        # during this 50ms periodic.
        self.apply_newest_override_slider_values()

        p = self.status.actual_position
        # p[] register is always in machine units - commands to LCNC (MDI, offset commands) are in G20/21 units
        # diameter DRO
        if not self.dro_list['dia_dro'].masked:
            x = p[0] - self.status.g5x_offset[0] - self.status.tool_offset[0] - self.status.g92_offset[0]
            # p[0] always returns the X value in radius, regardless of G7/G8 state.
            self.dia = x * self.mm_inch_scalar * 2
            self.dro_list['dia_dro'].set_text(self.dro_long_format % self.dia)

        # z DRO
        if not self.dro_list['z_dro'].masked:
            z = p[2] - self.status.g5x_offset[2] - self.status.tool_offset[2] -  self.status.g92_offset[2]
            self.z = z * self.mm_inch_scalar
            self.dro_list['z_dro'].set_text(self.dro_long_format % self.z)

        # y DRO
        if self.machineconfig.in_rapidturn_mode() and not self.dro_list['y_dro'].masked:
            y = p[1] - self.status.g5x_offset[1] - self.status.tool_offset[1] -  self.status.g92_offset[1]
            y = y * self.mm_inch_scalar
            self.dro_list['y_dro'].set_text(self.dro_long_format % y)

        # dtg labels
        dtg = self.status.dtg
        x = dtg[0] * self.mm_inch_scalar * 2
        z = dtg[2] * self.mm_inch_scalar
        self.x_dtg_label.set_text(self.dro_long_format % x)
        self.z_dtg_label.set_text(self.dro_long_format % z)

        # watch for LinuxCNC to change coolant request state
        # when it does copy it to tormach.coolant HAL pin
        if self.prev_coolant_iocontrol != self.hal['coolant-iocontrol']:
            if self.hal['coolant-iocontrol']:
                self.hal['coolant'] = 1
            else:
                self.hal['coolant'] = 0
            # current becomes previous
            self.prev_coolant_iocontrol = self.hal['coolant-iocontrol']

        # coolant status
        if self.coolant_lockout <= 0:  #if not locked out
            self.coolant_status = self.hal['coolant']
            if self.coolant_status != self.prev_coolant_status:
                self.prev_coolant_status = self.coolant_status
                if self.coolant_status:
                    self.set_image('coolant_image', 'Coolant-Green.jpg')
                else:
                    self.set_image('coolant_image', 'Coolant-Black.jpg')
        else:
            #Turn off button always first pass during lockout period
            if self.coolant_lockout == COOLANT_LOCK_OUT_PERIOD:
                self.set_image('coolant_image', 'Coolant-Black.jpg')
            self.coolant_lockout -= 1 #decrement lockout count
            self.hal['coolant'] = 0 #keep coolant off

        self.usb_IO_periodic()

        self.process_halpin_callbacks()

        # door switch status
        self.door_switch = self.hal['door-switch']
        if self.door_switch != self.prev_door_switch:
            self.prev_door_switch = self.door_switch
            if self.door_switch == 1:
                self.set_image('door_sw_led', 'LED-Yellow.jpg')
                if self.program_running(False):
                    # pause program
                    self.pause_program_for_door_sw_open()
                else:
                    # stop the spindle
                    if self.spindle_running():
                        self.issue_mdi('M5')
            else:
                self.set_image('door_sw_led', 'LED-Green.jpg')

        # poll for errors
        error = self.error.poll()
        if error:
            error_kind, error_msg = error
            # do not immediately show limit switch messages that come from LinuxCNC.  we latch
            # that we've seen them and let the 500ms periodic UI cycle decide to show them or not
            # Real Soon Now.
            #
            # this avoids timing problems of these errors appearing before machine-ok
            # goes false after an estop power down of the mill
            # sometimes machine-ok goes false long before the limits activate
            # sometimes the limits go active before machine-ok goes false
            # which leads customers to belive they have bad limit switches when they don't.
            #
            # delaying has no bad effect because LinuxCNC auto transitions to ESTOP_RESET
            # without any help from the UI.
            if 'X axis limit switch active' in error_msg:
                self.limit_switches_seen |= 1
                self.limit_switches_seen_time = time.time()
            elif 'Y axis limit switch active' in error_msg:
                self.limit_switches_seen |= 2
                self.limit_switches_seen_time = time.time()
            elif 'Z axis limit switch active' in error_msg:
                self.limit_switches_seen |= 4
                self.limit_switches_seen_time = time.time()
            else:
                if error_kind == EMC_OPERATOR_DISPLAY_TYPE:
                    self.error_handler.write(error_msg, ALARM_LEVEL_LOW)
                else:
                    # display on UI
                    self.error_handler.write(error_msg)

        if self.debugpage:
            self.debugpage.refresh_page()

        self.update_gcode_display()

        self.update_jogging()

        # limit switch status
        self.home_switch = self.hal['home-switch']
        if self.home_switch != self.prev_home_switch:
            self.prev_home_switch = self.home_switch
            self.set_warning_led('home_sw_led', self.home_switch == 1)

        # probe input
        if bool(self.status.probe_val) != self.probe_tripped_display:
            self.probe_tripped_display = bool(self.status.probe_val)
            self.set_indicator_led('acc_input_led', self.probe_tripped_display)

        # collet clamped LED indicator
        self.collet_closer_status = self.hal['collet-closer-status']
        if self.collet_closer_status != self.prev_collet_closer_status:
            self.prev_collet_closer_status = self.collet_closer_status

            # we have to take into consideration the OD/ID style of clamping to
            # properly represent green = clamped and black = unclamped.
            clamping_style = self.redis.hget('machine_prefs', 'auto_collet_closer_clamping_style')
            if clamping_style == 'OD':
                if self.collet_closer_status == 1:
                    self.set_image('collet_closer_image', 'collet-clamped-black.png')
                else:
                    self.set_image('collet_closer_image', 'collet-clamped-green.png')
            elif clamping_style == 'ID':
                if self.collet_closer_status == 0:
                    self.set_image('collet_closer_image', 'collet-clamped-black.png')
                else:
                    self.set_image('collet_closer_image', 'collet-clamped-green.png')
            else:
                self.error_handler.write("Unsupported auto collet clamping style {}".format(clamping_style), ALARM_LEVEL_MEDIUM)

        # watch for LinuxCNC to change spindle request state
        # when it does copy it to tormach.spindle HAL pin
        if self.prev_spindle_iocontrol != self.hal['spindle-iocontrol']:
            if self.hal['spindle-iocontrol']:
                if self.door_switch == 1:
                    # NB: this is a bit of a kludge.  It will show the error message to the user
                    # for MDI M3 with door open, but user will need to
                    # click Stop, Reset, or M5 before second M3 will be obeyed.
                    self.error_handler.write("Cannot start spindle with door open", ALARM_LEVEL_LOW)
                else:
                    # door closed
                    # pass motion.spindle-on (net in postgui) to HAL spindle enable
                    self.hal['spindle'] = self.hal['spindle-iocontrol']
            else:
                # motion.spindle-on is False
                self.hal['spindle'] = 0
            # current becomes previous
            self.prev_spindle_iocontrol = self.hal['spindle-iocontrol']


        if self.current_notebook_page_id == 'alarms_fixed':
            self.refresh_encoder_leds()
            self.refresh_machine_ok_led()


    def on_exit_button_release_event(self, widget, data=None):
        btn.ImageButton.unshift_button(widget)
        self.stop_motion_safely()
        self.hide_m1_image()
        conf_dialog = popupdlg.shutdown_confirmation_popup(self.window)
        self.window.set_sensitive(False)
        self.profile_renderer.set_visible(False)
        self.tool_renderer.set_visible(False)
        conf_dialog.run()
        conf_dialog.destroy()
        if conf_dialog.response == gtk.RESPONSE_CANCEL:
            self.window.set_sensitive(True)
            self.profile_renderer.set_visible(True)
            self.tool_renderer.set_visible(True)
        else:
            self.quit()

    def quit(self):
        #TODO: Add other axes here
        self.axis_motor_command(0, MOTOR_CMD_DISABLE)
        if self.machineconfig.in_rapidturn_mode():  # we have a Y axis with a motor on it
            self.axis_motor_command(1, MOTOR_CMD_DISABLE)
        self.axis_motor_command(2, MOTOR_CMD_DISABLE)
        self._quit()
        gtk.main_quit()

    def set_work_offset(self, axis, dro_text):
        if self.machineconfig.in_rapidturn_mode():
            if not (self.x_referenced and self.y_referenced and self.z_referenced):
                self.error_handler.write("Must reference X, Y, and Z axes before setting work offsets.", ALARM_LEVEL_MEDIUM)
        elif axis == 'Y':
            self.error_handler.write("Cannot set Y work offset when not in RapidTurn configuration.", ALARM_LEVEL_MEDIUM)
            return

        dro_val = float(dro_text)
        # we're always displaying Dia, but LCNC wants radius
        if axis == "X":
            dro_val = dro_val/2

        axis_dict = {'X':0, 'Y':1, 'Z':2, 'A':3}
        axis_ix = axis_dict[axis]
        if not self.status.homed[axis_ix]:
            self.error_handler.write("Must reference {} axis before setting work offset.".format(axis), ALARM_LEVEL_MEDIUM)
            return

        current_work_offset = self.status.g5x_index

        # log the change to the status screen in case the operator forgot they're in the wrong work coordinate system
        # and just zero'd out a valuable number.
        work_offset_name = self.get_work_offset_name_from_index(current_work_offset)  # e.g. G55 or G59.1
        format_without_percent = self.dro_long_format[1:]
        msg_template = "{:s} {:s} axis work offset changed from {:" + format_without_percent + "} to {:" + format_without_percent + "}."
        old_value = self.status.g5x_offsets[current_work_offset][axis_ix] * self.get_linear_scale()

        offset_command = "G10 L20 P%d %s%.12f" % (current_work_offset, axis, dro_val)
        self.issue_mdi(offset_command)

        # need wait_complete or liststore refresh will read the old value
        self.command.wait_complete()
        self.status.poll()
        self.refresh_work_offset_liststore()

        new_value = self.status.g5x_offsets[current_work_offset][axis_ix] * self.get_linear_scale()
        msg = msg_template.format(work_offset_name, axis, old_value, new_value)
        self.error_handler.write(msg, ALARM_LEVEL_QUIET)

        # we don't actually kick off a gremlin redraw here because the 500ms periodic
        # also checks for work offset changes and rotation changes and will do it
        # whenever a program is not running.  That's quick enough.  Otherwise you
        # end up with TWO refreshes which with large programs takes FOREVER.


    # TODO
    # is_button_permitted() is not fully baked for lathe.  The intent is to fully implement this in a future lathe release.
    # However, in the interest of code sharing between lathe and mill, we "need" this routine for USB I/O output buttons.
    # set_button_permitted_states() is what must be done carefully for every relevant button and then tie in
    # calls to is_button_permitted() in the release event callbacks.
    #
    # previously known as check_button_permissions() which was less obvious on the return value meaning
    # button permissions were refactored to be bitfield of permitted states - no longer a numerical level
    def is_button_permitted(self, widget):
        if not isinstance(widget, gtk.RadioButton):
            # move the button back, ditch focus.
            btn.ImageButton.unshift_button(widget)
            self.window.set_focus(None)

        # figure out what the current state of the machine is
        if self.program_running_but_paused() or self.mdi_running_but_paused():
            current_state = STATE_PAUSED_PROGRAM
        elif self.program_running():
            # we're running a g code program
            current_state = STATE_RUNNING_PROGRAM
        elif self.moving():
            # machine is moving (e.g. jog, MDI) or atc is doing something
            current_state = STATE_MOVING
            if self.status.axis[0]['homing'] or self.status.axis[1]['homing'] or self.status.axis[2]['homing']:
                current_state = STATE_HOMING
        elif self.status.task_state == linuxcnc.STATE_ON:
            # machine is on, connected, not moving or running g code
            # is it referenced?
            if self.x_referenced and self.z_referenced:
                current_state = STATE_IDLE_AND_REFERENCED
            else:
                current_state = STATE_IDLE
        else:
            # machine is in ESTOP state
            current_state = STATE_ESTOP

        # is there an overlap between the current state of the machine
        # and the widget's permitted machine states?
        permitted = (widget.permitted_states & current_state) != 0

        # give the user a clue why if we're going to fail
        if not permitted:
            statetext = ''
            if (widget.permitted_states & STATE_ESTOP) != 0:
                statetext += 'e-stop, '
            if (widget.permitted_states & STATE_IDLE) != 0:
                statetext += 'reset, '
            if (widget.permitted_states & STATE_IDLE_AND_REFERENCED) != 0:
                statetext += 'referenced, '
            if (widget.permitted_states & STATE_HOMING) != 0:
                statetext += 'homing, '
            if (widget.permitted_states & STATE_MOVING) != 0:
                statetext += 'moving, '
            if (widget.permitted_states & STATE_PAUSED_PROGRAM) != 0:
                statetext += 'g-code program paused, '
            if (widget.permitted_states & STATE_RUNNING_PROGRAM) != 0:
                statetext += 'g-code program running, '

            if len(statetext) > 0:
                statetext = statetext[:-2]   # slice off the trailing comma and space
            self.error_handler.write('Button only permitted when machine is in state(s): %s' % statetext, ALARM_LEVEL_LOW)

        return permitted


    # Axis style mode checks
    def program_running(self, do_poll=True):
        # are we running a gcode program?
        if do_poll:
            # need fresh status data, ask for it
            self.status.poll()
        return self.status.task_mode == linuxcnc.MODE_AUTO and self.status.interp_state != linuxcnc.INTERP_IDLE

    def program_running_but_paused(self):
        return (self.status.task_mode == linuxcnc.MODE_AUTO) and (self.status.interp_state == linuxcnc.INTERP_PAUSED)

    def spindle_running(self):
        if self.status.spindle_direction == 0:
            return False
        else:
            return True

    def ensure_mode(self, mode):
        # poll needed to prevent race condition on keyboard jogging where
        # ensure mode is called twice in quick succession and wait_complete()
        # results in runaway jog
        self.status.poll()
        if self.status.task_mode == mode:
            # if already in desired mode do nothing
            return True
        # set the desired mode
        self.error_handler.write("ensure_mode: changing LCNC mode to %s" % (self.get_lcnc_mode_string(mode)), ALARM_LEVEL_DEBUG)
        self.command.mode(mode)
        self.command.wait_complete()
        return True

    def check_tool_table_for_warnings(self, unique_tool_list):
        '''
        Return True if warnings were issued, False otherwise
        '''
        warnings = False
        # only pull tool_table across status channel once and then examine python object locally
        tool_table = self.status.tool_table
        for tool in unique_tool_list:
           # lathe check is for tip != 9
            if 9 == tool_table[tool].orientation:
                # 9 is the default and really not any sort of expected use case.
                warnings = True
                self.error_handler.write("Program uses tool {:d} which has a tip orientation of 9.  Please confirm tool table accuracy.".format(tool), ALARM_LEVEL_HIGH)

        return warnings


    def refresh_tool_liststore(self, forced_refresh=False):
        self.error_handler.write('Refreshing tool liststore', ALARM_LEVEL_DEBUG)
        # open the tool table file and read it
        # alternately could use status.tool_table[] to retrieve these values
        # let's try this using the status.tool_table[], as the text file doesn't seem to get refreshed the way one would like
        # clear out old data
        self.tool_liststore.clear()

        # CRITICAL!
        # only reach through status once for all the tool data as it is VERY slow otherwise
        tool_table_status = self.status.tool_table

        #remember the range function is not inclusive
        for pocket in range(1, MAX_LATHE_TOOL_NUM+1):
            wear_offset_pocket = pocket
            geo_offset_pocket  = pocket + MAX_LATHE_TOOL_NUM
            tool_num = tool_table_status[wear_offset_pocket].id
            geo_num = tool_table_status[geo_offset_pocket].id
            description = self.get_tool_description(tool_num)
            # some values stored as strings so we can format them for display
            tool_type = self.get_tool_type(tool_num)
            geo_x = self.dro_long_format % (2 * tool_table_status[geo_offset_pocket].xoffset * self.mm_inch_scalar)
            geo_y = self.dro_long_format % (tool_table_status[geo_offset_pocket].yoffset * self.mm_inch_scalar)
            geo_z = self.dro_long_format % (tool_table_status[geo_offset_pocket].zoffset * self.mm_inch_scalar)
            wear_x = 2 * tool_table_status[wear_offset_pocket].xoffset * self.mm_inch_scalar
            wear_z = tool_table_status[wear_offset_pocket].zoffset * self.mm_inch_scalar
            tool_radius = self.dro_long_format % (tool_table_status[wear_offset_pocket].diameter * self.mm_inch_scalar/ 2) # Tool table stores the nose value as a diameter
            tool_orientation = tool_table_status[wear_offset_pocket].orientation

            dia_wear_text_color = self.find_wear_offset_display_color(wear_x, tool_type)
            if wear_z < -0.00009:
                z_wear_text_color = BLUE
            elif wear_z > 0.00009:
                z_wear_text_color = ORANGE
            else:
                z_wear_text_color = BLACK

            wear_x = self.dro_long_format % wear_x
            wear_z = self.dro_long_format % wear_z

            background_color = '#E1B3B7'
            if pocket in self.gcode_program_tools_used:
                background_color = '#EB8891'
            self.tool_liststore.append([tool_num, description, geo_x, geo_y, geo_z, wear_x, wear_z, tool_radius, tool_orientation, dia_wear_text_color, z_wear_text_color, background_color])


    def update_tool_store(self, row, data):
        # data is a tuple of (column_number,data)
        # this method maps the column_number ('n') to the routine which will update
        # the tree_view and also the specific non-volatile storage.
        model = self.tool_treeview.get_model()
        for n,val in data:
            pass
            if n is 1: self.on_tool_description_column_edited(None,row,val,model)
            elif n is 6: self.on_nose_radius_col_edited(None, row,val,model)

    def refresh_work_offset_liststore(self):
        self.work_liststore.clear()
        # Stop a false positive on the iteritems() member below
        # pylint: disable=no-member
        for i, o in self.status.g5x_offsets.iteritems():
            if (i < 1):
                # Ignore current offset
                continue
            name = self.get_work_offset_name_from_index(i)
            row = [name] + ['%.4f' % (i * self.get_linear_scale()) for i in o[:4]] + ['BLACK', 'WHITE']
            self.work_liststore.append(row)

        # highlight active work offset
        row = self.work_liststore[self.status.g5x_index - 1]
        row[5] = BLACK
        row[6] = ROW_HIGHLIGHT

        self.work_treeview.queue_draw()  # force repaint of the work offset treeview


    def find_wear_offset_display_color(self, wear, tool_type):
        # according to Smid, CNC Programming Handbook, pp 105 - 106,
        # a wear offset is defined as the difference between the programmed
        # value (e.g. 3.0000) and the measured value (e.g. 3.0040).  If the
        # part comes out large on a machine set up as a rear tool post lathe,
        # and you're using a rear tool post tool, you would enter a neg number
        # (e.g. -0.0040).  This is opposite for front tool post tools on a
        # rear tool post lathe: positive number makes the part smaller.
        # For boring bars, an rtp boring bar needs a positive number to make the
        # feature (the bored hole) bigger.
        if wear > 0.00009:
            if 'rtp' in tool_type:
                return ORANGE
            elif 'ftp' in tool_type:
                return BLUE
            else:
                return BLACK
        elif wear < -0.00009:
            if 'rtp' in tool_type:
                return BLUE
            elif 'ftp' in tool_type:
                return ORANGE
            else:
                return BLACK
        return BLACK


    def get_tool_info(self, tool_number):
        # only pull tool_table across status channel once and then examine python object locally
        tool_table = self.status.tool_table

        pocket = int(tool_number)
        geo_offset_pocket  = pocket + MAX_LATHE_TOOL_NUM
        geo_num = tool_table[geo_offset_pocket].id
        err = ''
        valid = True

        #print "Refreshing tool data for tool",tool_num,"from",geo_num
        description = self.get_tool_description(tool_number)
        # some values stored as strings so we can format them for display

        geo_x = tool_table[geo_offset_pocket].xoffset
        geo_y = tool_table[geo_offset_pocket].yoffset
        geo_z = tool_table[geo_offset_pocket].zoffset
        tool_radius = tool_table[pocket].diameter/2.
        tool_orientation = tool_table[pocket].orientation
        if tool_radius == 0.0: err = ' radius is undefined'
        if geo_x == 0.0 and geo_y == 0.0 and geo_z == 0.0 and int(tool_number)>1 and not self.machineconfig.is_sim():  err = ' tool offsets are undefined' if not err else (err+', tool offsets are undefined')
        if tool_orientation == 9: err = ' orientation is undefined' if not err else (err+', orientation is undefined')
        if err:
            err = 'Tool {:s}:{}. Refer to tool {:s} on the Offsets tab.'.format(str(tool_number), err, str(tool_number))
            valid = False
        return (valid,dict(descript=description,x_offset=geo_x,y_offset=geo_y,z_offset=geo_z,radius=tool_radius,orientation=tool_orientation,error=err))

    def get_tool_type(self, tool):
        if tool == 0:
            return 'none'
        pocket = tool + MAX_LATHE_TOOL_NUM
        front_angle_val = self.status.tool_table[pocket].frontangle
        # if not yet set, return 'none'
        if front_angle_val == 0.0:
            return 'none'
        for tool_type_string, tool_type in self.tool_type_dic.iteritems():
            if tool_type == front_angle_val:
                return tool_type_string
        return 'none'

    def get_tool_angles(self, tn):
        pocket = int(tn)
        return (self.status.tool_table[pocket].frontangle,self.status.tool_table[pocket].backangle)

    def get_max_vel(self):
        return float(self.inifile.find("AXIS_2", "MAX_VELOCITY"))

    def write_tool_type(self, tool, tool_type):
        # we only call this if a user selects an image form the tool tab,
        # and if they're selecting an image, the touch_x and touch_z leds should be balck
        self.set_touch_x_z_leds(tool)
        # get tool_type as string, convert to integer, store in the geo offset register frontangle
        # field of the tool table
        if tool == 0:
            return
        if 'rtp' in tool_type:
            self.rtp_text.show()
            self.ftp_text.hide()
        elif 'ftp' in tool_type:
            self.ftp_text.show()
            self.rtp_text.hide()
        else:
            self.rtp_text.hide()
            self.ftp_text.hide()
        coded_tool_type = self.tool_type_dic[tool_type]
        front_angle = self.front_angle_dic[tool_type]
        back_angle = self.back_angle_dic[tool_type]
        orientation = self.orientation_dic[tool_type]
        geo_offset_register = tool + 10000
        g10_command = "G10 L1 P%d I%f" % (geo_offset_register, coded_tool_type)
        self.issue_mdi(g10_command)
        self.command.wait_complete()
        g10_command = "G10 L1 P%d I%.1f J%.1f Q%d" % (tool, front_angle, back_angle, orientation)
        self.issue_mdi(g10_command)


    def blink_tool_request_label(self, tool_number):
        if 'T' in self.tool_label.get_text():
            self.tool_label.set_text('')
        else:
            self.tool_label.set_text("T:    " + tool_number)


    def set_touch_x_z_leds(self, tool):
        tool += MAX_LATHE_TOOL_NUM
        self.status.tool_table[tool].xoffset
        if self.status.tool_table[tool].xoffset == 0:
            self.set_image('touch_x_image', 'touch_x_black_led.png')
            self.dro_list['touch_dia_dro'].set_text("")
        else:
            self.set_image('touch_x_image', 'touch_x_green_led.png')
        if self.status.tool_table[tool].zoffset == 0:
            self.set_image('touch_z_image', 'touch_z_black_led.png')
            self.dro_list['touch_z_dro'].set_text("")
        else:
            self.set_image('touch_z_image', 'touch_z_green_led.png')


    # ------------------------------------------------------------------------
    # dynamic tooltip methods
    # ------------------------------------------------------------------------

    def _get_tool_tip_tool_description(self, tool_number, description):
        # check for axial tooling...
        tdr = ui_support.ToolDescript.parse_text(description)
        typ = tdr.data['type'][0]['ref'].lower()
        axial = typ in ('endmill','drill','centerdrill','tap','ball','chamfer',\
                        'spot','flat','taper','bullnose','reamer','indexable')
        if axial:
            length = tdr.data['length'][0]['ref']
            description = self._get_tool_tip_axial_tool_description(tool_number, description, length)
        return description

    def get_panel_tip_tool_description(self, param):
        label = self.builder.get_object('tool_label')
        txt = label.get_text()[2:].strip()
        if '00' in txt: return ('00',tooltipmgr.TTMgr().get_local_string('err_machine_in_estop'))
        return self._test_tooltip_description(txt)

    def get_current_gcode_states(self, param):
        if self.status.task_state == linuxcnc.STATE_ESTOP or \
           self.status.task_state == linuxcnc.STATE_ESTOP_RESET or \
           self.status.task_state == linuxcnc.STATE_OFF:
            return '\n'+tooltipmgr.TTMgr().get_local_string('pre_RESET_gcode_status')
        outstr = '\n<span color="#003aff">'
        g20 = 'inches'
        active_gcodes = self.active_gcodes()
        for gc in active_gcodes:
            if gc in 'G7'                : outstr += '<b>'+gc+'</b>'+'   - <b>diameter</b> mode\n'; continue
            if gc in 'G8'                : outstr += '<b>'+gc+'</b>'+' - <b>radius</b> mode\n'; continue
            if gc in 'G54G55G56G57G58G59': outstr += '<b>'+gc+'</b>'+' - current work offset\n'; continue
            if gc == 'G20'               : outstr += '<b>'+gc+'</b>'+' - machine in <b>inch</b> units\n'; continue
            if gc == 'G21'               : outstr += '<b>'+gc+'</b>'+' - machine in <b>metric</b> units\n'; g20 = 'mm'; continue
            if gc == 'G90'               : outstr += '<b>'+gc+'</b>'+' - distance mode <b>absolute</b>\n'; continue
            if gc == 'G91'               : outstr += '<b>'+gc+'</b>'+' - distance mode <b>incremental</b>\n'; continue
            if gc == 'G80'               : outstr += '<b>'+gc+'</b>'+' - drill cycle <b>off</b>\n'; continue
            if gc == 'G81'               : outstr += '<b>'+gc+'</b>'+' - drill cycle <b>on</b>\n'; continue
            if gc == 'G40'               : outstr += '<b>'+gc+'</b>'+' - cutter radius compensation <b>off</b>\n'; continue
            if gc in 'G41G42'            : outstr += '<b>'+gc+'</b>'+' - cutter radius compensation <b>on</b>\n'; continue
            if gc == 'G93'               : outstr += '<b>'+gc+'</b>'+' - inverse time mode\n'; continue
            if gc == 'G94'               : outstr += '<b>'+gc+'</b>'+' - %s per minute mode\n'%g20; continue
            if gc == 'G95'               : outstr += '<b>'+gc+'</b>'+' - %s per revolution mode\n'%g20; continue
            if gc == 'G96'               : outstr += '<b>'+gc+'</b>'+' - constant surface speed <b>on</b>\n'; continue
            if gc == 'G97'               : outstr += '<b>'+gc+'</b>'+' - rpm mode <b>on</b>\n'; continue
            if gc == 'G91.1'             : outstr += '<b>'+gc+'</b>'+' - I,J,K mode <b>incremental</b>\n'; continue
            if gc == 'G90.1'             : outstr += '<b>'+gc+'</b>'+' - I,J,K mode <b>absolute</b>\n'; continue
        outstr = outstr[:-1]
        return outstr+'</span>'

    def get_profile_stock_z_description(self, param):
        if self.conv_profile_ext == 'external':
            param['images'] = ['TT.lathe-profile-z-start-ext-end.png','TT.lathe-profile-z-start-ext-mid.png']
            s = 'profile_external_z_start_note'
        else:
            param['images'] = ['TT.lathe-profile-z-start-int-end.png']
            s = 'profile_internal_z_start_note'
        return tooltipmgr.TTMgr().get_local_string(s)

    def get_tool_tip_tool_clear_z(self, param):
        if self.conv_profile_ext == 'external':
            param['images'] = ['TT.profile-tool-clearance.png','TT.profile-tool_clearance_mid.png']
            s = tooltipmgr.TTMgr().get_local_string('profile_external_tool_clear_z_note')
        else:
            param['images'] = ['TT.profile-tool_clearance_int.png']
            # Note: an 'empty' value must have one space ?!?
            s = ' '
        return s

    def get_profile_tool_clear_x_description(self, param):
        if self.conv_profile_ext == 'external':
            param['images'] = ['TT.tool-clear-X-ext.png']
            s = 'profile_external_clear_x_note'
        else:
            param['images'] = ['TT.tool-clear-X-int.png']
            s = 'profile_internal_clear_x_note'
        return tooltipmgr.TTMgr().get_local_string(s)

    def get_thread_tool_clear_x_description(self, param):
        if self.conv_thread_ext_int == 'external':
            param['images'] = ['TT.Thread-ext-clearance.svg']
            s = 'msg_thread_clear_ext_tooltip'
        else:
            param['images'] = ['TT.Thread-int-clearance.svg']
            s = 'msg_thread_clear_int_tooltip'
        return tooltipmgr.TTMgr().get_local_string(s)

    def get_G0_tooltip(self, param):
        param['images'] = ['TT.G0-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G0_lathe_tooltip')

    def get_G1_tooltip(self, param):
        param['images'] = ['TT.G1-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G1_lathe_tooltip')

    def get_G2_tooltip(self, param):
        param['images'] = ['TT.G2-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G2_lathe_tooltip')

    def get_G3_tooltip(self, param):
        param['images'] = ['TT.G3-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G3_lathe_tooltip')

    def get_G41_tooltip(self, param):
        param['images'] = ['TT.G41-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G41_lathe_tooltip')

    def get_G41_1_tooltip(self, param):
        param['images'] = ['TT.G41-lathe.png','TT.v-space-3.png']
        return ''

    def get_G42_tooltip(self, param):
        param['images'] = ['TT.G42-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G42_lathe_tooltip')

    def get_G42_1_tooltip(self, param):
        param['images'] = ['TT.G42-lathe.png','TT.v-space-3.png']
        return ''

    def get_G54_59_tooltip(self, param):
        param['images'] = ['TT.G54-lathe.png','TT.v-space-3.png']
        return tooltipmgr.TTMgr().get_local_string('G54_59_lathe_tooltip')

    # ------------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------------

    def stop_motion_safely(self):
        #Send abort message to motion to stop any movement
        self.command.abort()
        self.command.wait_complete()

        self.status.poll()  # help the rest of the code after this realize that the state of the world is quite changed.

        if self.hal['coolant']:
            self.hal['coolant'] = False

        if self.feedhold_active:
            self.feedhold_active = False
            #TODO move this to status update
            self.set_image('feedhold_image', 'Feedhold-Black.jpg')


    def start_regression_test_vehicle(self):
        self.error_handler.write("starting regression test vehicle", ALARM_LEVEL_DEBUG)
        # pick a csv file or folder
        gcode_path = os.path.join(os.getenv('HOME')) + os.path.sep + 'gcode'
        with tormach_file_util.file_save_as_popup(self.window, '', gcode_path, '.nc', self.settings.touchscreen_enabled,
                                                  usbbutton=False, closewithoutsavebutton=False) as dialog:
            path = dialog.path

        dros = [self.conv_dro_list,
                self.od_turn_dro_list,
                self.id_basic_dro_list,
                self.id_turn_dro_list,
                self.face_dro_list,
                #self.chamfer_dro_list,
                #self.corner_dro_list,
                self.corner_chamfer_od_dro_list,
                self.corner_chamfer_id_dro_list,
                self.corner_radius_od_dro_list,
                self.corner_radius_id_dro_list,
                self.groove_dro_list,
                self.part_dro_list,
                self.drill_dro_list,
                self.tap_dro_list,
                self.thread_dro_list]

        test = regression_tests.test(self.status, dros, path, self.error_handler)

    def redraw_gremlin(self):
        # Large files can take a long time so give some feedback with busy cursor
        # (but only if we know this file causes gremlin.load to be slow - otherwise
        # the flashing related to the plexiglass is annoying)
        if self.gremlin:
            with plexiglass.ConditionalPlexiglassInstance(self.gremlin_load_needs_plexiglass, singletons.g_Machine.window) as p:
                # redraw screen with new offset
                # be sure to switch modes to cause an interp synch, which
                # writes out the var file.
                # this mode change is CRITICAL to getting the gremlin to redraw the toolpath
                # in the correct spot.  Without it, the gremlin can be forced to redraw, but
                # it doesn't draw the toolpath in the new spot if the work coordinate or rotation has changed
                self.ensure_mode(linuxcnc.MODE_MANUAL)
                self.ensure_mode(linuxcnc.MODE_MDI)
                self.gremlin.clear_live_plotter()
                self.gremlin.load()
                self.gremlin.queue_draw()  # force a repaint
                #Note:not catching warnings here since it's assumed the user has
                #already seen them

    def refresh_jog_active_leds(self):
        self.x_jog_enabled = self.hal['jog-axis-x-enabled']
        if self.x_jog_enabled != self.prev_x_jog_enabled:
            self.prev_x_jog_enabled = self.x_jog_enabled
            # x jog enabled changed
            if self.x_jog_enabled:
                self.set_image('jog_x_active_led', 'LED-Green.jpg')
            else:
                self.set_image('jog_x_active_led', 'LED-Black.jpg')

        self.z_jog_enabled = self.hal['jog-axis-z-enabled']
        if self.z_jog_enabled != self.prev_z_jog_enabled:
            self.prev_z_jog_enabled = self.z_jog_enabled
            # z jog enabled changed
            if self.z_jog_enabled:
                self.set_image('jog_z_active_led', 'LED-Green.jpg')
            else:
                self.set_image('jog_z_active_led', 'LED-Black.jpg')


        if self.machineconfig.in_rapidturn_mode():
            self.y_jog_enabled = self.hal['jog-axis-y-enabled']
            if self.y_jog_enabled != self.prev_y_jog_enabled:
                self.prev_y_jog_enabled = self.y_jog_enabled
                # z jog enabled changed
                if self.y_jog_enabled:
                    self.set_image('jog_y_active_led', 'LED-Green.jpg')
                else:
                    self.set_image('jog_y_active_led', 'LED-Black.jpg')


    def refresh_encoder_leds(self):
        if self.machineconfig.in_rapidturn_mode():
            # do something appropriate for rapidturn
            if self.hal['encoder-z']:
                self.set_image('encoder_z_led', 'LED-Green.jpg')
            else:
                self.set_image('encoder_z_led', 'LED-Black.jpg')
        else:
            # update encoder count dro
            # sign of count inverted to match sign of what is sent to LCNC from HAL
            self.dro_list['encoder_counts_dro'].set_text(str(-1 * self.hal['encoder-count']))
            #self.encoder_counts_dro.set_text(self.hal['encoder-count'])
            # update encoder LEDs
            if self.hal['encoder-a']:
                self.set_image('encoder_a_led', 'LED-Green.jpg')
            else:
                self.set_image('encoder_a_led', 'LED-Black.jpg')
            if self.hal['encoder-b']:
                self.set_image('encoder_b_led', 'LED-Green.jpg')
            else:
                self.set_image('encoder_b_led', 'LED-Black.jpg')
            if self.hal['encoder-z']:
                self.set_image('encoder_z_led', 'LED-Green.jpg')
            else:
                self.set_image('encoder_z_led', 'LED-Black.jpg')


    def switch_inch_metric_display(self):
        # swap button art on jog step sizes
        self.clear_jog_LEDs()
        self.set_jog_LEDs()

        # store off in redis for startup in same mode next time.
        self.redis.hset('machine_prefs', 'g21', self.g21)
        self.refresh_css_label()
        jog_ix = self.hal['jog-gui-step-index']
        if self.g21:
            self.mm_inch_scalar = 25.4
            self.jog_metric_scalar = 10
            self.hal['jog-is-metric'] = True
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g21()[jog_ix]
        else:
            self.mm_inch_scalar = 1
            self.jog_metric_scalar = 1
            self.hal['jog-is-metric'] = False
            self.jog_increment_scaled = self.machineconfig.jog_step_increments_g20()[jog_ix]

        self.gremlin.queue_draw()   # impacts the display

    @property
    def dro_tpu_format(self):
        """Return the python format string for DROs showing a threads/unit number

        Returns:
            String: Python format string which varies depending on whether the
            interface is in G21 (metric) mode or G20 (imperial)
        """
        if self.g21:
            return "%3.2f"
        else:
            return "%2.2f"

    def composite_png_button_images(self):
        TormachUIBase.composite_png_button_images(self)
        self.set_image('css_image', 'CSS-Green.png')
        self.set_image('css_image', 'CSS-Black.png')
        self.set_image('feed_per_rev_image', 'F-Rev-Green.png')
        self.set_image('feed_per_rev_image', 'F-Rev-Black.png')


    def refresh_css_label(self):
        if self.g21:
            if self.css_active:
                self.set_image('css_image', 'CSS-Green.png')
                self.css_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >mpm</span>')
            else:
                self.set_image('css_image', 'CSS-Black.png')
                self.css_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="#A19D9F" >mpm</span>')
        else:
            if self.css_active:
                self.set_image('css_image', 'CSS-Green.png')
                self.css_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="white" >sfm</span>')
            else:
                self.set_image('css_image', 'CSS-Black.png')
                self.css_label.set_markup('<span weight="light" font_desc="Bebas 12" font_stretch="ultracondensed" foreground="#A19D9F" >sfm</span>')



    def pause_program_for_door_sw_open(self):
        self.error_handler.write("Pausing program because door sw was opened", ALARM_LEVEL_DEBUG)
        self.program_paused_for_door_sw_open = True
        self.command.auto(linuxcnc.AUTO_PAUSE)
        self.feedhold_active = True
        self.set_image('feedhold_image', 'Feedhold-Green.jpg')
        if self.hal['coolant']:
            self.hal['coolant'] = False
        if self.hal['spindle']:
            self.hal['spindle'] = False


    def resume_program_from_door_sw_open(self):
        self.error_handler.write("Resuming program because door sw was closed", ALARM_LEVEL_DEBUG)
        self.program_paused_for_door_sw_open = False
        # iocontrol.coolant is checked in the 50ms periodic.  If it doesn't match the previous state,
        # we flip the hal.coolant bit accordingly.  This next line will force this to happen
        self.prev_coolant_iocontrol = not self.hal['coolant-iocontrol']
        # set self.prev_spindle_iocontrol to False always to avoid race where prev = on and current = off
        # and an immediate M3 happens that makes current = on which hides the off -> on edge from the periodic
        # and the spindle doesn't get enabled
        # if spindle was off it stays off, if it was on then the faked rising edge is seen and the spindle get enabled
        self.prev_spindle_iocontrol = False


    # rapidturn extras
    def rapidturn_init(self):

        self.settings.adjust_settings_for_rapidturn()

        # turn on the small Y axis DRO
        self.builder.get_object('y_dro').set_visible(True)
        self.builder.get_object('jog_y_active_led').set_visible(True)
        self.builder.get_object("y_dro_label").set_visible(True)

        # turn on the ref Y button
        self.button_list['ref_y'].show()
        self.button_list['ref_y'].set_sensitive(True)
        self.builder.get_object("ref_y_image").set_visible(True)

        # hide collet closer button
        self.button_list['collet_closer'].hide()

        # hide notes about negative side of workpiece in conv. screens
        list_of_notes_to_hide = ['tool_side_note_text',
                                 'tool_side_note_text3',
                                 'corner_tool_side_text',
                                 'groove_part_tool_side_text',
                                 'thread_tool_side_text',
                                 'ftp_text']
        for note in list_of_notes_to_hide:
            self.builder.get_object(note).hide()

        # remove 'tap' text on drill/tap label and hide tap button
        self.builder.get_object('drill_tab_label').set_text('Drill')
        self.button_list['drill_tap'].hide()

        # encoder-related stuff on settings screen
        self.builder.get_object('encoder_counts_text').hide()
        self.builder.get_object('encoder_counts_dro').hide()
        self.builder.get_object('encoder_a_text').hide()
        self.builder.get_object('encoder_a_led').hide()
        self.builder.get_object('encoder_b_text').hide()
        self.builder.get_object('encoder_b_led').hide()


    def stop_jog(self, jog_axis):
        # unconditionally stop jog - do not check mode here!!!
        self.jogging_stopped = False
        self.command.jog(linuxcnc.JOG_STOP, jog_axis)

    def get_jog_increment(self, axis_ind):
        """Return a jog increment based on the specified axis index"""
        # X DRO is diameter so divide by two for radius
        if axis_ind == 0:
            return self.jog_increment_scaled / 2.0
        return self.jog_increment_scaled

    def jog(self, jog_axis, jog_direction, jog_speed, apply_pct_override=True, jog_mode = None):
        if self.program_running(True):
            return

        if self.status.task_state in (linuxcnc.STATE_ESTOP, linuxcnc.STATE_ESTOP_RESET, linuxcnc.STATE_OFF):
            self.error_handler.write("Must take machine out of estop before jogging")
            return

        # If an explicit jog mode is specified, use that, otherwise assume the
        # current GUI mode
        if jog_mode is None:
            jog_mode = self.jog_mode

        if self.is_front_toolpost_lathe and jog_axis == 0:
            jog_direction *= -1

        self.ensure_mode(linuxcnc.MODE_MANUAL)

        # Compute actual jog speed from direction, absolute speed, and percent
        # override
        speed = jog_direction * jog_speed

        # Encourage referencing and try to avoid axis jamming by slowing jog speed while
        # unreferenced.
        referenced = (self.x_referenced and self.z_referenced) and (not self.machineconfig.in_rapidturn_mode() or self.y_referenced)
        if self.machineconfig.has_hard_stop_homing() and not referenced:
            #clamp bi-directional speed to +/-5%, but use even less if speed value was already <5%
            # apply_pct_override is _always_ ignored on purpose if servos (M+ or MX) and not homed
            if speed >= 0 and speed > self.axis_unhomed_clamp_vel[jog_axis]:
                speed = self.axis_unhomed_clamp_vel[jog_axis]
            elif speed < 0 and speed < (-1.0 * self.axis_unhomed_clamp_vel[jog_axis]):
                speed = -1.0 * self.axis_unhomed_clamp_vel[jog_axis]
        elif apply_pct_override:
            speed *= self.jog_override_pct


        if self.jog_mode == linuxcnc.JOG_CONTINUOUS:
            #Continous jogging
            self.command.jog(jog_mode, jog_axis, speed)
            self.jogging_stopped = True

        else:
            # Step jogging
            if self.moving(): return
            # Scale distance for the current axis
            displacement = self.get_jog_increment(jog_axis) / self.get_axis_scale(jog_axis)
            self.command.jog(jog_mode, jog_axis, speed, displacement)


    # g code preview, set start line, edit g code

    def load_gcode_file(self, path):
        if self.program_running():
            return

        self.use_hal_gcode_timers = False

        # Call base class behavior
        TormachUIBase.load_gcode_file(self, path)

        self.gremlin_load_needs_plexiglass = False   # be optimistic

        # Large files can take a long time so give some feedback with busy cursor
        with plexiglass.PlexiglassInstance(singletons.g_Machine.window) as p:

            self.is_gcode_program_loaded = True

            # see if we're simply reloading the same file after somebody tweaked it.
            same_file_reload = (self.get_current_gcode_path() == path)

            # remember what was last loaded to watch for changes on disk and reload
            self.set_current_gcode_path(path)
            if not path:
                self.gcodelisting_buffer.set_text('')
                return

            # note the time stamp
            st = os.stat(path)
            self.gcode_file_mtime = st.st_mtime

            # disable syntax coloring for files larger than 2 MB because
            # gedit and the gtksourceview widget suck for performance and memory use when trying to
            # syntax color large files. A 1M line (35 MB) g-code file took 10-15 minutes to load and used
            # hundreds of megabytes of extra ram.
            if st.st_size > (2*1024*1024):
                self.set_gcode_syntaxcoloring(False)
                self.error_handler.write('Disabled g-code colors due to large file size for better performance.', ALARM_LEVEL_LOW)

            # prevent changes to the combo box from causing file loads
            self.combobox_masked = True
            # remove filename from previous model position if it was previously in the model
            sort_file_history(self.file_history_liststore, path, None)
            # add filename, path to the model
            self.file_history_liststore.prepend([os.path.basename(path), path])
            # have to set active one, else the active file won't be displayed on the combobox
            self.loaded_gcode_filename_combobox.set_active(0)
            # unmask
            self.combobox_masked = False
            # read file directly into buffer
            tormach_file_util.open_text_file(self, path, self.gcodelisting_buffer)

            # can change this with right-click menu in source view
            # this is one based, the textbuffer is zero based
            self.gcode_start_line = 1
            # must switch to mdi, then back to force clear of _setup.file_pointer, otherwise
            # we can't open a program if one is already open
            self.ensure_mode(linuxcnc.MODE_MDI)
            # load file into LinuxCNC
            self.ensure_mode(linuxcnc.MODE_AUTO)

            # We read the whole g-code file into memory at once.  But linuxcnc doesn't.  This can
            # cause all sorts of confusing behavior if the file is updated from another computer.
            # Reliable solution is to always copy the entire g-code file to a spot the user cannot
            # see or maniuplate and tell linuxcnc to load that file.  Then its behavior will be consistent
            # with the UI and it won't start using new file data until the user answers the "File changed, reload?"
            # dialog prompt.
            #
            # shutil.copy2 retains attributes such as date/time
            shutil.copy2(path, LINUXCNC_GCODE_FILE_PATH)

            # Sigh.  We can't actually do this here currently, even though it appears correct. program_close() currently
            # re-inits the g-code interpreter state from the .ini file. So just the act of loading a file (but not executing any of it)
            # will change modal interp state.  Worst impact example is if you were in G21 and then load a file, you end up in G20.
            # Long term fix is stopping program_close() from calling the interp init() method, but that needs closer examination.
            # 10/07/2019 jwf  PP-2647
            #self.command.program_close()
            #self.command.wait_complete()

            self.command.program_open(LINUXCNC_GCODE_FILE_PATH)

            # gremlin is unpredictable at the moment
            # wrap it for exceptions
            try:
                self.gremlin.clear_live_plotter()
            except Exception as e:
                msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                self.error_handler.write('gremlin.clear_live_plotter() raised an exception - %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)
                #traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                #print traceback_txt

            try:
                # with no filename given, gremlin will ask LinuxCNC for the filename
                loadtm = timer.Stopwatch()
                result, seq, warnings = self.gremlin.load()
                seconds = loadtm.get_elapsed_seconds()
                self.error_handler.write("gremlin.load of %s took %f seconds" % (path, seconds), ALARM_LEVEL_DEBUG)
                if seconds > 2.0:
                    # we must have a larger or complicated file as it took gremlin over 2 seconds
                    # to load the file.
                    # set the flag so that all future gremlin.load() calls are plexiglassed
                    self.error_handler.write("gremlin.load took too long so future gremlin.load on this file will use plexiglass", ALARM_LEVEL_DEBUG)
                    self.gremlin_load_needs_plexiglass = True

                #Quick way to dump warnings to status window
                self.gremlin.report_gcode_warnings(warnings,os.path.basename(path))
            except Exception as e:
                msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                self.error_handler.write('gremlin.load() raised an exception - %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)
                #traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                #print traceback_txt

            # this makes sure that the previous "next" line in the gcode display doesn't errantly
            # show the line from the PREVIOUS gcode program loaded.
            try:
                self.gremlin.set_highlight_line(None)
            except Exception as e:
                msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                self.error_handler.write('gremlin.set_highlight_line() raised an exception - %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)

            try:
                self.gremlin.set_view_y()
            except Exception as e:
                msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
                self.error_handler.write('gremlin.set_y_view() raised an exception - %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)
                #traceback_txt = "".join(traceback.format_exception(*sys.exc_info()))
                #print traceback_txt

            self.last_runtime_sec = self.stats_mgr.get_last_runtime_sec()

            # this list of integer tool numbers is in the order the program uses them and will contain duplicates
            self.gcode_program_tools_used = self.gremlin.get_tools_used()
            # force refresh the tool list store as we color code it based on if the tools are used by the program
            # or not
            self.refresh_tool_liststore(forced_refresh=True)

            self.gremlin_options.show_all_tools()


        # switch to gcode listing MDI main tab
        if not self.interp_alarm:
            set_current_notebook_page_by_id(self.notebook, "notebook_main_fixed")
        self.window.set_focus(None)

        self.gcodelisting_mark_start_line(self.gcode_start_line)
        self.gcode_pattern_search.on_load_gcode()
        self.lineno_for_last_m1_image_attempt = 0

        # only reset the override slider values if we're changing files entirely. otherwise from your last run to this one
        # you may have been dialing in your sliders and then we whack them on you.
        if not same_file_reload:
            self.safely_reset_override_slider_values()


    def update_tool_orientation_image(self):
        tip_orient = self.status.tool_table[self.current_tool].orientation

        # apologies for the following kludge: this code requires the orientation
        # images to follow a naming convention - either ftp_orientation_x.png or
        # orientation_x.png where x is the numeric orientation.  ftp prefix is for
        # a front tool post lathe
        image_filename = 'orientation_' + str(tip_orient) + '.png'
        if self.is_front_toolpost_lathe:
            image_filename = 'ftp_' + image_filename

        try:
            self.set_image('tool_orientation_image',  image_filename)
        except:
            self.set_image('tool_orientation_image', 'orientation_0.png')

    def delete_event(self, widget, event):
        self.error_handler.write('Alt-F4/delete_event detected. Simulating Exit button press.', ALARM_LEVEL_DEBUG)
        try:
            self.enqueue_button_press_release(self.button_list['exit'])
        except Exception as e:
            msg = "An exception of type {0} occured, these were the arguments:\n{1!r}"
            self.error_handler.write('enqueue button press failed due to exception - %s' % msg.format(type(e).__name__, e.args), ALARM_LEVEL_DEBUG)
        return True

    def create_jobassignment_gremlin(self, width, height):
        return JobAssignmentGremlin(self, width, height)

#--end 'lathe'-------------------------------------------------------------------

    def hide_notebook_tabs(self):
        for i in range(0, self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(i)
            page_id = gtk.Buildable.get_name(page)
            # only hide the alarms tab if no alarms are active
            if (not page_id == "notebook_main_fixed") and (
                    not page_id == "alarms_fixed"
                    or not self.error_handler.get_alarm_active()):
                page.hide()


    def show_enabled_notebook_tabs(self, data=None):
        for i in range(0, self.notebook.get_n_pages()):
            page = self.notebook.get_nth_page(i)
            page_id = gtk.Buildable.get_name(page)

            page.show()


def is_dro_masked(dro_list):
    for name, dro in dro_list.iteritems():
        if dro.masked == True:
            return True
    return False

#---------------------------------------------------------------------------------------------------
# Tormach_Lathe_Gremlin
#---------------------------------------------------------------------------------------------------

# this overrides 'posstrs()' to not display the DROs in Gremlin
class Tormach_Lathe_Gremlin(gremlinbase.Tormach_Gremlin_Base):
    def __init__(self, ui, width, height):
        gremlinbase.Tormach_Gremlin_Base.__init__(self, ui, width, height)

        self.ui_view = 'y'
        # necessary to support recent changes to gremlin in 2.6.  We might want to make this configurable
        # down the road, but for now it's set to a grid of .1 inches.  The grid doesn't display for me
        # but at least the UI will load without error again.
        self.grid_size = 0.5
        self.show_g53_origin = False
        self.connect("button_press_event", self.on_gremlin_double_click)

    def destroy(self):
        gremlinbase.Tormach_Gremlin_Base.destroy(self)

    def realize(self,widget):
        super(Tormach_Lathe_Gremlin, self).realize(widget)

    def set_grid_size(self, size):
        self.grid_size = size
        self._redraw()

    def get_grid_size(self):
        return self.grid_size

    def get_view(self):
        # gremlin as used as a gladevcp widegt has a propery for the view, which for a lathe
        # should be 'y'.  When it's not right the program extents won't be drawn.
        view_dict = {'x':0, 'y':1, 'z':2, 'p':3}
        return view_dict.get('y')

    def get_show_metric(self):
        if self.status.gcodes[linuxcnc.G_CODE_UNITS] == 200:
            return False
        else:
            return True

    def posstrs(self):
        l, h, p, d = gremlin.Gremlin.posstrs(self)
        return l, h, [''], ['']

    def report_gcode_error(self, result, seq, filename):
        import gcode
        error_str = gcode.strerror(result)
        error_str = "\n\nG-Code error in " + os.path.basename(filename) + "\n" + "Near line " + str(seq) + " of\n" + filename + "\n" + error_str
        self.ui.error_handler.write(error_str)
        self.ui.interp_alarm = True

    def on_gremlin_double_click(self, widget, event, data=None):
        if event.type == gtk.gdk._2BUTTON_PRESS:
            self.clear_live_plotter()
            return
        if event.type == gtk.gdk.BUTTON_PRESS and event.button == 3 and True not in self.ui.jogging_key_pressed.values():
            # it's a right click if event.button == 3
            menu = gtk.Menu()
            imperial = not self.ui.g21
            sml_text = "Grid 0.1 inch" if imperial else "Grid 5 mm"
            med_text = "Grid 0.5 inch" if imperial else "Grid 10 mm"
            lrg_text = "Grid 1.0 inch" if imperial else "Grid 25 mm"

            set_grid_size_small = gtk.MenuItem(sml_text)
            set_grid_size_med = gtk.MenuItem(med_text)
            set_grid_size_large = gtk.MenuItem(lrg_text)
            set_grid_size_small.connect("activate", self.set_grid_size_small)
            set_grid_size_med.connect("activate", self.set_grid_size_med)
            set_grid_size_large.connect("activate", self.set_grid_size_large)
            menu.append(set_grid_size_small)
            menu.append(set_grid_size_med)
            menu.append(set_grid_size_large)
            menu.popup(None, None, None, event.button, event.time)
            set_grid_size_small.show()
            set_grid_size_med.show()
            set_grid_size_large.show()

    def set_current_ui_view(self):
        self.set_view_y()
        self._redraw()

    def set_grid_size_small(self, widget):
        size = (5/25.4) if self.ui.g21 else .1
        self.set_grid_size(size)
        self.ui.gremlin_options.update_grid_size('small')

    def set_grid_size_med(self, widget):
        size = (10/25.4) if self.ui.g21 else .5
        self.set_grid_size(size)
        self.ui.gremlin_options.update_grid_size('med')

    def set_grid_size_large(self, widget):
        size = (25/25.4) if self.ui.g21 else 1.0
        self.set_grid_size(size)
        self.ui.gremlin_options.update_grid_size('large')


class JobAssignmentGremlin(Tormach_Lathe_Gremlin):
    def __init__(self, ja, width, height):
        Tormach_Lathe_Gremlin.__init__(self, ja.conversational.ui, width, height)
        self.current_view = 'y'
        self.ui_view = 'y'
        self.spooler = None

    def report_gcode_warnings(self, warnings, filename, suppress_after = 3):
        print 'JobAssignmentGremlin.report_gcode_warnings: file: %s, %d warnings' % (filename,len(warnings))

    def load_gcode_list(self, gcode_list):
        if self.initialised:
            path = TormachUIBase.gcode_list_to_tmp_file(gcode_list)
            if path is not None:
                self.ui.redis.hset('machine_prefs','ja_current_path', path)
                self.load(path)
                self.queue_draw()
            self.spooler = None
        else:
            self.spooler = gcode_list

# @ADAM - this seems old legacy realize() code.  I just took the same code from mill and dropped it in here
# and it appears to work fine.
#
#    def realize(self,widget):
#        import glnav
#        import rs274.glcanon
#        import rs274.interpret
#
#        self.activate()
#        self._current_file = None
#
#        self.font_base, width, linespace = glnav.use_pango_font('courier bold 16', 0, 128)
#        self.font_linespace = linespace
#        self.font_charwidth = width
#        rs274.glcanon.GlCanonDraw.realize(self)
#        if self.spooler is not None:
#            self.load_gcode_list(self.spooler)
#            self.set_default_view()
#            self.queue_draw()

    def realize(self,widget):
        super(JobAssignmentGremlin, self).realize(widget)
        if self.spooler is not None:
            self.load_gcode_list(self.spooler)
            self.set_default_view()
            self.queue_draw()

    def set_default_view(self):
        self.current_view = self.ui_view = 'y'
        if self.initialised:
            self.set_current_view()

    def destroy(self):
        Tormach_Lathe_Gremlin.destroy(self)
        self.spooler = None


if __name__ == "__main__":
    del _

    # unbuffer stdout so print() shows up in sync with other output
    # the pipe from the redirect in operator_login causes buffering
    sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)

    gobject.threads_init()

    # Rarely needed
    #debugconsole.listen()

    print "tormach_lathe_ui.py arguments are ", sys.argv

    init_localization('en_US.UTF8')     # ISO standardized ways of identifying locale
    print _('msg_hello')                # Localization test

    UI = lathe()
    singletons.g_Machine = UI

    screen_width = gtk.gdk.Screen().get_width()
    screen_height = gtk.gdk.Screen().get_height()
    UI.error_handler.write('screen resolution is now %d x %d' % (screen_width, screen_height), ALARM_LEVEL_DEBUG)
    if screen_width > 1024 and screen_height > 768:
        UI.window.set_decorated(True)

    # always connect to 'delete_event' in case Alt-F4 isn't disabled in keyboard shortcuts
    UI.window.connect('delete_event', UI.delete_event)
    UI.window.resize(1024, 768)

    UI.window.show()

    if UI.error_handler.get_alarm_active():
        set_current_notebook_page_by_id(UI.notebook, 'alarms_fixed')
    else:
        set_current_notebook_page_by_id(UI.notebook, 'notebook_main_fixed')
        UI.gremlin.set_view_y()

    UI.kill_splash_screen()

    # nuke the marker file so that pathpilotmanager.py knows for sure we got fully up with the UI displayed.
    crashdetection.delete_crash_detection_file()

    gtk.main()

    sys.exit(UI.program_exit_code)
