#!/usr/bin/python
#    Copyright (C) 2009-2012
#    Jeff Epler <jepler@unpythonic.net>,
#    Pavel Shramov <psha@kamba.psha.org.ru>,
#    Chris Morley <chrisinnanaimo@hotmail.com>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#    2014 Steffen Noack
#    add property 'mouse_btn_mode'
#    0 = default: left rotate, middle move,   right zoom
#    1 =          left zoom,   middle move,   right rotate
#    2 =          left move,   middle rotate, right zoom
#    3 =          left zoom,   middle rotate, right move
#    4 =          left move,   middle zoom,   right rotate
#    5 =          left rotate, middle zoom,   right move
#
#    2015 Moses McKnight introduced mode 6 
#    6 = left move, middle zoom, right zoom (no rotate - for 2D plasma machines or lathes)
#
#    2016 Norbert Schechner
#    corrected mode handling for lathes, as in most modes it was not possible to move, as 
#    it has only been allowed in p view.



import gtk
import gtk.gtkgl.widget
import gtk.gdkgl
import gtk.gdk

import glnav
import gobject

import rs274.glcanon
import rs274.interpret
import linuxcnc
import gcode

import re
import tempfile
import shutil
import os
import sys

import thread
import traceback


class DummyProgress:
    def nextphase(self, unused): pass
    def progress(self): pass

class StatCanon(rs274.glcanon.GLCanon, rs274.interpret.StatMixin):
    def __init__(self, colors, geometry, lathe_view_option, stat, random, inifile):
        rs274.glcanon.GLCanon.__init__(self, colors, geometry, inifile)
        rs274.interpret.StatMixin.__init__(self, stat, random)
        self.progress = DummyProgress()
        self.lathe_view_option = lathe_view_option
        self.tools_used = []

    def is_lathe(self): return self.lathe_view_option

    def change_tool(self, pocket):
        rs274.glcanon.GLCanon.change_tool(self,pocket)
        rs274.interpret.StatMixin.change_tool(self,pocket)
        self.tools_used.append(pocket)        

    def get_tools_used(self):
        return self.tools_used

    def get_soft_limits(self):
        ax = self.s.axis

        return (
            self.to_internal_units([self.fudge(ax[i]['min_position_limit']) for i in range(3)]),
            self.to_internal_units([self.fudge(ax[i]['max_position_limit']) for i in range(3)]))

    def to_internal_units(self, pos, unit = None):
        """ Convert a raw position to internal units.
        Copied from axis
        returns a list of 9 values
        """
        if unit is None:
            unit = self.s.linear_units
        lu = (unit or 1) * 25.4

        lus = [lu, lu, lu, 1, 1, 1, lu, lu, lu]
        return [a/b for a, b in zip(pos, lus)]

    @staticmethod
    def fudge(x):
        if abs(x) > 1e30: return 0
        return x



class Gremlin(gtk.gtkgl.widget.DrawingArea, glnav.GlNavBase,
              rs274.glcanon.GlCanonDraw):
    rotation_vectors = [(1.,0.,0.), (0., 0., 1.)]

    def __init__(self, inifile):
        self.geometry = ''
        display_mode = ( gtk.gdkgl.MODE_RGB | gtk.gdkgl.MODE_DEPTH |
                         gtk.gdkgl.MODE_DOUBLE )
        glconfig = gtk.gdkgl.Config(mode=display_mode)

        gtk.gtkgl.widget.DrawingArea.__init__(self, glconfig)
        glnav.GlNavBase.__init__(self)
        def C(s):
            a = self.colors[s + "_alpha"]
            s = self.colors[s]
            return [int(x * 255) for x in s + (a,)]
        self.inifile = inifile
        self.logger = linuxcnc.positionlogger(linuxcnc.stat(),
            C('backplotjog'),
            C('backplottraverse'),
            C('backplotfeed'),
            C('backplotarc'),
            C('backplottoolchange'),
            C('backplotprobing'),
            self.get_geometry()
        )
        thread.start_new_thread(self.logger.start, (.01,))

        rs274.glcanon.GlCanonDraw.__init__(self, linuxcnc.stat(), self.logger)

        self.current_view = 'z'

        self.canon = None

        self.select_primed = None

        self.connect_after('realize', self.realize)
        self.connect('configure_event', self.reshape)
        self.connect('map_event', self.map)
        self.connect('expose_event', self.expose)
        self.connect('motion-notify-event', self.motion)
        self.connect('button-press-event', self.pressed)
        self.connect('button-release-event', self.select_fire)
        self.connect('scroll-event', self.scroll)

        self.add_events(gtk.gdk.POINTER_MOTION_MASK)
        self.add_events(gtk.gdk.POINTER_MOTION_HINT_MASK)
        self.add_events(gtk.gdk.BUTTON_MOTION_MASK)
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK)
        self.add_events(gtk.gdk.BUTTON_RELEASE_MASK)

        self.fingerprint = ()

        self.lat = 0
        self.minlat = -90
        self.maxlat = 90

        self.highlight_line = None
        self.program_alpha = False
        self.use_joints_mode = False
        self.use_commanded = True
        self.show_limits = True
        self.show_extents_option = True
        self.show_live_plot = True
        self.show_velocity = True
        self.metric_units = True
        self.show_program = True
        self.show_rapids = True
        self.use_relative = True
        self.show_tool = True
        self.show_dtg = True
        self.grid_size = 0.0
        self.use_default_controls = True
        temp = inifile.find("DISPLAY", "LATHE")
        self.lathe_option = bool(temp == "1" or temp == "True" or temp == "true" )

        temp2 = inifile.find("DISPLAY", "GEOMETRY")
        self.is_rear_tp_lathe = bool(temp2 == "-XZ")

        self.foam_option = bool(inifile.find("DISPLAY", "FOAM"))
        self.show_offsets = False
        #self.show_offsets = True
        self.show_g53_origin = False
        self.mouse_btn_mode = 0

        self.a_axis_wrapped = inifile.find("AXIS_3", "WRAPPED_ROTARY")
        self.b_axis_wrapped = inifile.find("AXIS_4", "WRAPPED_ROTARY")
        self.c_axis_wrapped = inifile.find("AXIS_5", "WRAPPED_ROTARY")

        live_axis_count = 0
        for i,j in enumerate("XYZABCUVW"):
            if self.stat.axis_mask & (1<<i) == 0: continue
            live_axis_count += 1
        self.num_joints = int(inifile.find("TRAJ", "JOINTS") or live_axis_count)

        self.timeout_id = None

        self._tools_used = []


    def destroy(self):
        # cleanup so that the garbage collector can actually do its work.
        # this eventually kills the logger thread that was created in the constructor
        self.stop_live_plotter()

        # and we must stop the timer callback or this single callback will forever keep
        # this object alive along with all the overhead of the instance data!
        if self.timeout_id:
            gobject.source_remove(self.timeout_id)
            self.timeout_id = None            
        self.inifile = None
        self.logger = None
        self._tools_used = None

    def activate(self):
        glcontext = gtk.gtkgl.widget_get_gl_context(self)
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)

        return gldrawable and glcontext and gldrawable.gl_begin(glcontext)

    def swapbuffers(self):
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)
        gldrawable.swap_buffers()

    def deactivate(self):
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)
        gldrawable.gl_end()

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def reshape(self, widget, event):
        self.width = event.width
        self.height = event.height

    def expose(self, widget=None, event=None):
        if not self.initialised: return
        if self.perspective:
            self.redraw_perspective()
        else:
            self.redraw_ortho()

        return True

    def _redraw(self): self.expose()

    def clear_live_plotter(self):
        self.logger.clear()

    def stop_live_plotter(self):
        # this is important as its the only way to clean up the thread that we started which
        # the logger is running in.
        self.logger.stop()        

    def map(self, *args):
        # don't schedule multiple timers
        if self.timeout_id is None:
            self.timeout_id = gobject.timeout_add(50, self.poll)       

    def poll(self):
        s = self.stat
        try:
            s.poll()
        except:
            return
        fingerprint = (self.logger.get_npts(), self.soft_limits(),
            s.actual_position, s.joint_actual_position,
            s.homed, s.g5x_offset, s.g92_offset, s.limit, s.tool_in_spindle,
            s.motion_mode, s.current_vel)

        if fingerprint != self.fingerprint:
            self.fingerprint = fingerprint
            self.queue_draw()

        return True

    @rs274.glcanon.with_context
    def realize(self, widget):
        self.set_current_view()
        s = self.stat
        try:
            s.poll()
        except:
            return
        self._current_file = None

        self.font_base, width, linespace = glnav.use_pango_font('courier bold 16', 0, 128)
        self.font_linespace = linespace
        self.font_charwidth = width
        rs274.glcanon.GlCanonDraw.realize(self)

        if s.file:
            self.load()

    def set_current_view(self):
        if self.current_view not in ['p', 'x', 'y', 'y2', 'z', 'z2']:
            return
        return getattr(self, 'set_view_%s' % self.current_view)()
    
    def set_geometry(self, geometry):
        self.geometry = geometry


    def get_visible_tools(self):
        '''
        Returns a list of visible tool paths.  None means all tools are visible.
        '''
        if self.canon:
            return self.canon.get_visible_tools()
        return None

    def set_visible_tools(self, tool_list):
        '''
        Setting the list to None means 'show all tools'
        '''
        if self.canon:
            self.canon.set_visible_tools(tool_list)

            # if the visible tools changed, need to get GLCanonDraw to rebuild its display lists          
            self.stale_dlist('program_rapids')
            self.stale_dlist('program_norapids')
            self.stale_dlist('select_rapids')
            self.stale_dlist('select_norapids')

        if self.logger:
            self.logger.set_visible_tools(tool_list)
            self._redraw()

    @staticmethod
    def gcode_to_str(g_code):
        suffix = int(g_code) % 10
        base = int(g_code)/10
        return "G{}.{}".format(base, suffix) if suffix else "G{}".format(base)

    def get_active_g_code_string(self):
        """
        Most active G-codes don't matter for preview, but the ones that affect path geometry do, such as distance mode,
        cut plane, cutter comp, etc. This method pulls the relevant active G-codes from emctask to initialize
        the preview interpreter.
        :return: A string (delimited by '\n') of G-codes to execute
        """
        gcodes = self.stat.gcodes

        # NOTE: ignoring the following active G-codes since they don't affect preview, or are handled elsewhere
        # G_CODE_MOTION_MODE
        # G_CODE_MODE_0
        # G_CODE_FEED_MODE
        # G_CODE_ORIGIN
        # G_CODE_TOOL_LENGTH_OFFSET
        # G_CODE_SPINDLE_MODE

        cmd_list = ((
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_UNITS]),  # Must be first before applying any other modes
        ),(
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_PATH_MODE]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_LATHE_DIAMETER_MODE]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_PLANE]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_CUTTER_SIDE]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_DISTANCE_MODE]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_DISTANCE_MODE_IJK]),
            self.gcode_to_str(gcodes[linuxcnc.G_CODE_RETRACT_MODE]),
        ))
        print "Active G-codes at redraw:", cmd_list
        return '\n'.join((' '.join(sub_l) for sub_l in cmd_list))

    def load(self, filename=None):
        s = self.stat
        s.poll()
        if not filename and s.file:
            filename = s.file
        elif not filename and not s.file:
            return

        td = tempfile.mkdtemp()
        self._current_file = filename
        #KLUDGE define dummy vars here
        result = 0
        warnings = []
        seq = 0
        self._tools_used = []
        try:
            random = int(self.inifile.find("EMCIO", "RANDOM_TOOLCHANGER") or 0)
            self.canon = StatCanon(self.colors, self.geometry, self.lathe_option, s, random, self.inifile)
            parameter = self.inifile.find("RS274NGC", "PARAMETER_FILE")
            parameter = os.path.expanduser(parameter)
            temp_parameter = os.path.join(td, os.path.basename(parameter or "linuxcnc.var"))
            if parameter:
                shutil.copy(parameter, temp_parameter)
            self.canon.parameter_file = temp_parameter

            initcode = self.get_active_g_code_string() or self.inifile.find("RS274NGC", "RS274NGC_STARTUP_CODE") or ""
            unitcode = "G{}".format(20 + (s.program_units == linuxcnc.UNITS_MM))
            result, seq, warnings = self.load_preview(filename, self.canon, unitcode, initcode)

            #Handle extents violation (copied from AXIS)
            machine_limit_min, machine_limit_max = self.canon.get_soft_limits()
            # KLUDGE: reverse engineer the machine units
            unit_suffix = "mm" if s.linear_units == 1 else "in"
            for i in range(3): # Does not enforce angle limits
                if not(s.axis_mask & (1<<i)): continue
                if self.canon.min_extents_notool[i] < machine_limit_min[i]:
                    neg_overhang = self.canon.min_extents_notool[i] - machine_limit_min[i]
                    warnings.append("Program exceeds machine minimum on %c axis  by %0.4f %s"
                        % ("XYZABCUVW"[i], neg_overhang, unit_suffix))
                if self.canon.max_extents_notool[i] > machine_limit_max[i]:
                    pos_overhang = self.canon.max_extents_notool[i] - machine_limit_max[i]
                    warnings.append("Program exceeds machine maximum on %c axis by %0.4f %s"
                        % ("XYZABCUVW"[i], pos_overhang, unit_suffix))
            # Warn user if spindle-synched feeds violate axis limits
            axis_max_vel = tuple([
                float(self.inifile.find("AXIS_%d" % i,"MAX_VELOCITY") or 0.0)*60
                for i in range(9)])
            for line_no, delta, rpm, fpr in self.canon.feed_synched:
                fpm = rpm * fpr  # feed per minute
                max_fpm = self.canon.calc_velocity(delta, axis_max_vel) * 0.95
                if fpm > max_fpm:
                    warnings.append(
                        "Spindle synched move at %(rpm_set).1f RPM would "
                        "exceed safe XYZ velocity limits on line %(line_no)d. "
                        "Please reduce spindle speed to %(rpm_max).1f RPM or "
                        "reduce thread pitch/feed per revolution to "
                        "%(pitch).3f." %
                        dict(rpm_set=rpm, rpm_max=max_fpm/fpr, line_no=line_no,
                             pitch=max_fpm/rpm))

            if result > gcode.MIN_ERROR:
                self.report_gcode_error(result, seq, filename)

            self._tools_used = self.canon.get_tools_used()

        finally:
            shutil.rmtree(td)

        return result, seq, warnings
    # doing this kills our zoom settings if gremlin.load is called on work offset change
        #self.set_current_view()

    def get_canon(self): return self.canon
    def get_tools_used(self): return self._tools_used
    def get_program_alpha(self): return self.program_alpha
    def get_num_joints(self): return self.num_joints
    def get_geometry(self):
        if self.geometry == '':
            temp = self.inifile.find("DISPLAY", "GEOMETRY")
            if temp:
                geometry = re.split(" *(-?[XYZABCUVW])", temp.upper())
                self.geometry = "".join(reversed(geometry))
            else:
                self.geometry = 'XYZ'
        return self.geometry

    def get_joints_mode(self): return self.use_joints_mode
    def get_show_commanded(self): return self.use_commanded
    def get_show_extents(self): return self.show_extents_option
    def get_show_limits(self): return self.show_limits
    def get_show_live_plot(self): return self.show_live_plot
    def get_show_machine_speed(self): return self.show_velocity
    def get_show_metric(self): return self.metric_units
    def get_show_program(self): return self.show_program
    def get_show_rapids(self): return self.show_rapids
    def get_show_relative(self): return self.use_relative
    def get_show_tool(self): return self.show_tool
    def get_show_distance_to_go(self): return self.show_dtg
    def get_grid_size(self): return self.grid_size

    def get_view(self):
        view_dict = {'x':0, 'y':1, 'z':2, 'p':3}
        return view_dict.get(self.current_view, 3)

    def is_lathe(self): return self.lathe_option
    def is_rear_tool_post_lathe(self): return self.is_rear_tp_lathe

    def is_foam(self): return self.foam_option
    def get_current_tool(self):
        for i in self.stat.tool_table:
            if i[0] == self.stat.tool_in_spindle:
                return i
    def get_highlight_line(self): return self.highlight_line

    def get_a_axis_wrapped(self): return self.a_axis_wrapped
    def get_b_axis_wrapped(self): return self.b_axis_wrapped
    def get_c_axis_wrapped(self): return self.c_axis_wrapped

    def get_font_info(self):
        return self.font_charwidth, self.font_linespace, self.font_base

    def get_show_offsets(self): return self.show_offsets

    def select_prime(self, x, y):
        self.select_primed = x, y

    @rs274.glcanon.with_context
    def select_fire(self, widget, event):
        if not self.select_primed: return
        x, y = self.select_primed
        self.select_primed = None
        self.select(x, y)

    def select_cancel(self, widget=None, event=None):
        self.select_primed = None

    def pressed(self, widget, event):
        if not self.use_default_controls:return
        button1 = event.button == 1
        button2 = event.button == 2
        button3 = event.button == 3
        if button1:
            self.select_prime(event.x, event.y) # select G-Code element
        
        if button3 and (event.type == gtk.gdk._2BUTTON_PRESS):
            self.clear_live_plotter()
        elif button1 or button2 or button3:
            self.startZoom(event.y)
            self.recordMouse(event.x, event.y)

    def motion(self, widget, event):
        if not self.use_default_controls:return
        button1 = event.state & gtk.gdk.BUTTON1_MASK
        button2 = event.state & gtk.gdk.BUTTON2_MASK
        button3 = event.state & gtk.gdk.BUTTON3_MASK
        shift = event.state & gtk.gdk.SHIFT_MASK
        # for lathe or plasmas rotation is not used, so we check for it
        # recomended to use mode 6 for that type of machines
        cancel = bool(self.lathe_option)
        
        # 0 = default: left rotate, middle move, right zoom
        if self.mouse_btn_mode == 0:
            if button1:
                if shift:
                    self.translateOrRotate(event.x, event.y)
                elif not cancel:
                    self.set_prime(event.x, event.y)
                    self.rotateOrTranslate(event.x, event.y)
            elif button2:
                self.translateOrRotate(event.x, event.y)
            elif button3:
                self.continueZoom(event.y)
        # 1 = left zoom, middle move, right rotate
        elif self.mouse_btn_mode == 1:
            if button1:
                if shift:
                    self.translateOrRotate(event.x, event.y)
                else:
                    self.continueZoom(event.y)
            elif button2:
                self.translateOrRotate(event.x, event.y)
            elif button3 and not cancel:
                self.set_prime(event.x, event.y)
                self.rotateOrTranslate(event.x, event.y)
        # 2 = left move, middle rotate, right zoom
        elif self.mouse_btn_mode == 2:
            if button1:    
                if shift:
                    if not cancel:
                        self.set_prime(event.x, event.y)
                        self.rotateOrTranslate(event.x, event.y)
                else:
                    self.translateOrRotate(event.x, event.y)
            elif button2 and not cancel:
                self.set_prime(event.x, event.y)
                self.rotateOrTranslate(event.x, event.y)
            elif button3:
                self.continueZoom(event.y)
        # 3 = left zoom, middle rotate, right move
        elif self.mouse_btn_mode == 3:
            if button1:    
                if shift:
                    if not cancel:
                        self.set_prime(event.x, event.y)
                        self.rotateOrTranslate(event.x, event.y)
                else:
                    self.continueZoom(event.y)
            elif button2 and not cancel:
                self.set_prime(event.x, event.y)
                self.rotateOrTranslate(event.x, event.y)
            elif button3:
                self.translateOrRotate(event.x, event.y)
        # 4 = left move,   middle zoom,   right rotate
        elif self.mouse_btn_mode == 4:
            if button1:    
                if shift:
                    if not cancel:
                        self.set_prime(event.x, event.y)
                        self.rotateOrTranslate(event.x, event.y)
                else:
                    self.translateOrRotate(event.x, event.y)
            elif button2:
                self.continueZoom(event.y)
            elif button3 and not cancel:
                self.set_prime(event.x, event.y)
                self.rotateOrTranslate(event.x, event.y)
        # 5 = left rotate, middle zoom, right move
        elif self.mouse_btn_mode == 5:
            if button1:    
                if shift:
                    self.continueZoom(event.y)
                elif not cancel:
                    self.set_prime(event.x, event.y)
                    self.rotateOrTranslate(event.x, event.y)
            elif button2:
                self.continueZoom(event.y)
            elif button3:
                self.translateOrRotate(event.x, event.y)
        # 6 = left move, middle zoom, right zoom (no rotate - for 2D plasma machines or lathes)
        elif self.mouse_btn_mode == 6:
            if button1:    
                if shift:
                    self.continueZoom(event.y)
                else:
                    self.translateOrRotate(event.x, event.y)
            elif button2:
                self.continueZoom(event.y)
            elif button3:
                self.continueZoom(event.y)

    def scroll(self, widget, event):
        if not self.use_default_controls:return
        if event.direction == gtk.gdk.SCROLL_UP: self.zoomin()
        elif event.direction == gtk.gdk.SCROLL_DOWN: self.zoomout()

    def report_gcode_error(self, result, seq, filename):
        error_str = gcode.strerror(result)
        sys.stderr.write("G-Code error in " + os.path.basename(filename) + "\n" + "Near line "
                         + str(seq) + " of\n" + filename + "\n" + error_str + "\n")

    def show_gcode_warnings(self, warnings, filename):
        for w in warnings:
            sys.stderr.write("G-Code Warning in " + os.path.basename(filename) + "\n" + "In file "
                             + filename + "\n" + w + "\n")


    # These are for external controlling of the view

    def zoom_in(self, ratio=1.1):
        self.zoomin(ratio)

    def zoom_out(self, ratio=1.1):
        self.zoomout(ratio)

    def start_continuous_zoom(self, y):
        self.startZoom(y)

    def continuous_zoom(self, y):
        self.continueZoom(y)

    def set_mouse_start(self, x, y):
        self.recordMouse(x, y)

    def set_prime(self, x, y):
        if self.select_primed:
            primedx, primedy = self.select_primed
            distance = max(abs(x - primedx), abs(y - primedy))
            if distance > 8: self.select_cancel()

    def pan(self,x,y):
        self.translateOrRotate(x, y)

    def rotate_view(self,x,y):
        self.rotateOrTranslate(x, y)
