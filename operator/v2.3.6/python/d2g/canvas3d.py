# pylint: disable=import-error

from __future__ import division

import gobject
import gtk.gtkgl.widget
import gtk.gdkgl
import gtk.gdk
import logging
from math import cos, sin, radians
import time

from point import Point
from gldraw import GlDraw


logger = logging.getLogger(__name__)


def with_context_swap(f):
    def inner(self, *args, **kw):
        success = self._activate()
        if not success:
            return False
        try:
            return f(self, *args, **kw)
        finally:
            self._swapbuffers()
            self._deactivate()

    return inner


def with_context(f):
    def inner(self, *args, **kw):
        success = self._activate()
        if not success:
            return False
        try:
            return f(self, *args, **kw)
        finally:
            self._deactivate()

    return inner


class Canvas3D(gtk.gtkgl.widget.DrawingArea):
    __gsignals__ = {
        'layers-changed': (
            gobject.SIGNAL_RUN_LAST,
            gobject.TYPE_NONE,
            (gobject.TYPE_BOOLEAN,),
        ),  # needs full update
        'mouse-clicked': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, width, height):
        display_mode = gtk.gdkgl.MODE_RGB | gtk.gdkgl.MODE_DEPTH | gtk.gdkgl.MODE_DOUBLE
        glconfig = gtk.gdkgl.Config(mode=display_mode)
        gtk.gtkgl.widget.DrawingArea.__init__(self, glconfig)

        self.set_size_request(width, height)
        self._gl_draw = GlDraw()
        self._gl_draw.set_size(width, height)

        self._is_rotating = False
        self._is_panning = False
        self._left_button_pressed = False
        self._last_mouse_pos = Point(0, 0)
        self.selection_tolerance = 4
        self._refresh_time = 1 / 70  # 1 / fps
        self._last_time = time.time()

        self.connect_after('realize', self._realize)
        self.connect('configure_event', self._configure)
        self.connect('expose_event', self._expose)
        self.connect('button_press_event', self._handle_mouse_press_event)
        self.connect('button_release_event', self._handle_mouse_release_event)
        self.connect('motion_notify_event', self._handle_motion_notify_event)
        self.connect('scroll_event', self._handle_scroll_event)
        self.set_events(
            gtk.gdk.EXPOSURE_MASK
            | gtk.gdk.BUTTON_PRESS_MASK
            | gtk.gdk.BUTTON_RELEASE_MASK
            | gtk.gdk.BUTTON1_MOTION_MASK
            | gtk.gdk.BUTTON2_MOTION_MASK
            | gtk.gdk.BUTTON3_MOTION_MASK
            | gtk.gdk.SCROLL_UP
            | gtk.gdk.SCROLL_DOWN
        )

        self._create_context_menu()

    @property
    def width(self):
        return self.allocation.width

    @property
    def height(self):
        return self.allocation.height

    @property
    def shapes(self):
        return self._gl_draw.shapes

    @shapes.setter
    def shapes(self, data):
        self._gl_draw.shapes = data

    @property
    def export_route(self):
        return self._gl_draw.export_route

    @export_route.setter
    def export_route(self, data):
        self._gl_draw.export_route = data

    @property
    def layers(self):
        return self._gl_draw.layers

    @layers.setter
    def layers(self, data):
        self._gl_draw.layers = data

    @property
    def number_format(self):
        return self._gl_draw.number_format

    @number_format.setter
    def number_format(self, value):
        self._gl_draw.number_format = value

    def clear(self):
        """ clears the preview data to free memory"""
        self._gl_draw.layers = []
        self._gl_draw.shapes = {}
        self._gl_draw.export_route = []

    def update(self):
        self._expose()

    def redraw(self):
        self._gl_draw.redraw()
        self.update()

    def reset_viewport(self, widget=None):
        self._gl_draw.reset_viewport()

    def set_front_view(self, widget=None):
        self._gl_draw.set_front_view()
        self.update()

    def set_top_view(self, widget=None):
        self._gl_draw.set_top_view()
        self.update()

    def set_side_view(self, widget=None):
        self._gl_draw.set_side_view()
        self.update()

    def set_iso_view(self, widget=None):
        self._gl_draw.set_iso_view()
        self.update()

    def _activate(self):
        glcontext = gtk.gtkgl.widget_get_gl_context(self)
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)

        return gldrawable and glcontext and gldrawable.gl_begin(glcontext)

    def _swapbuffers(self):
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)
        gldrawable.swap_buffers()

    def _deactivate(self):
        gldrawable = gtk.gtkgl.widget_get_gl_drawable(self)
        gldrawable.gl_end()

    @with_context_swap
    def _expose(self, widget=None, event=None):
        self._gl_draw.paint_gl()
        return False

    @with_context
    def _realize(self, _):
        self._gl_draw.initialize_gl()

    @with_context
    def _configure(self, *args):
        self._gl_draw.resize_gl(self.width, self.height)

    def _create_context_menu(self):
        menu = gtk.Menu()
        set_top_view = gtk.MenuItem("Top View")
        set_iso_view = gtk.MenuItem("Iso View")
        set_top_view.connect("activate", self.set_top_view)
        set_iso_view.connect("activate", self.set_iso_view)
        menu.append(set_iso_view)
        menu.append(set_top_view)
        self._menu = menu

    def _handle_mouse_press_event(self, widget, event):
        self._is_panning = event.button == 2  # middle mouse button
        self._is_rotating = event.button == 1
        self._last_mouse_pos = Point(event.x, event.y)
        self._left_button_pressed = event.button == 1

        if event.button != 1:  # not left mouse button click
            return
        self._select_shape(event)

    def _handle_mouse_release_event(self, widget, event):
        self._is_rotating = False
        self._is_panning = False

        if event.button == 3:  # right mouse button click
            self._menu.popup(None, None, None, event.button, event.time)
            self._menu.show_all()

        self.emit('mouse-clicked')

    def _handle_motion_notify_event(self, widget, event):
        # limit the refresh rate, else the preview may look laggy
        current_time = time.time()
        if (current_time - self._last_time) < self._refresh_time:
            return
        self._last_time = current_time

        current_pos = Point(event.x, event.y)
        delta = current_pos - self._last_mouse_pos

        rotation = self._gl_draw.rotation
        if self._is_rotating:
            rotation.x += delta.y / 2
            rotation.z -= delta.x / 2
            self._gl_draw.rotation = rotation

        elif self._is_panning:
            position = self._gl_draw.position
            smaller_side = min(self.width, self.height)
            delta.z = 0.0
            position.x += delta.x / smaller_side
            position.y += delta.y / smaller_side
            position.z += delta.z / smaller_side
            self._gl_draw.position = position

        self._last_mouse_pos = current_pos
        self.update()

    def _handle_scroll_event(self, widget, event):
        smaller_side = min(self.width, self.height)
        delta = (
            Point(event.x - (self.width / 2), event.y - (self.height / 2))
            / smaller_side
        )
        delta.z = 0.0
        if event.direction == gtk.gdk.SCROLL_UP:
            angle = 100.0
        else:
            angle = -100.0
        s = 1.001 ** angle

        rotation = self._gl_draw.rotation
        position = self._gl_draw.position
        delta = self._derotate(delta, rotation)
        position.x *= s
        position.y *= s
        position.z *= s
        self._gl_draw.position = position
        self._gl_draw.scale *= s

        self.update()

    def _select_shape(self, mouse_event):
        clicked, offset, tolerance = self._get_mouse_press_details(mouse_event)
        xy_for_z = {}

        modified = False
        for layer, shapes in self.layers:
            for shape_detail in shapes:
                shape = self.shapes[shape_detail['nr']].shape
                hit = False
                z = shape_detail['axis3_start_mill_depth']
                if z not in xy_for_z:
                    xy_for_z[z] = self._determine_selected_position(clicked, z, offset)
                hit |= shape.is_hit(xy_for_z[z], tolerance)
                # shape is hit
                if not hit:
                    z = shape_detail['axis3_mill_depth']
                    if z not in xy_for_z:
                        xy_for_z[z] = self._determine_selected_position(
                            clicked, z, offset
                        )
                    hit |= shape.is_hit(xy_for_z[z], tolerance)

                # multiselect would be done here
                if shape_detail['selected'] != hit:
                    shape_detail['selected'] = hit
                    modified = True

        if modified:
            self.emit('layers-changed', False)

    def _get_mouse_press_details(self, event):
        smaller_side = min(self.width, self.height)
        scale = self._gl_draw.scale
        clicked_point = (
            Point(event.x - self.width / 2, event.y - self.height / 2)
            / smaller_side
            / scale
        )
        xyz_offset = -self._gl_draw.position / scale
        tolerance = (
            self.selection_tolerance
            * self._gl_draw.scale_correction
            / smaller_side
            / scale
        )
        return clicked_point, xyz_offset, tolerance

    def _determine_selected_position(self, clicked, for_z, offset):
        rotation = self._gl_draw.rotation
        angle_x = -radians(rotation.x)
        angle_y = -radians(rotation.y)

        zv = for_z - offset.z
        clicked_z = (
            (zv + clicked.x * sin(angle_y)) / cos(angle_y) - clicked.y * sin(angle_x)
        ) / cos(angle_x)
        s = self._derotate(Point(clicked.x, clicked.y, clicked_z), rotation)
        return Point(s.x + offset.x, s.y + offset.y)

    def _derotate(self, point, rotation):
        angle_x = -radians(rotation.x)
        point = Point(
            point.x,
            point.y * cos(angle_x) - point.z * sin(angle_x),
            point.y * sin(angle_x) + point.z * cos(angle_x),
        )
        angle_y = -radians(rotation.y)
        point = Point(
            point.x * cos(angle_y) + point.z * sin(angle_y),
            point.y,
            -point.x * sin(angle_y) + point.z * cos(angle_y),
        )
        angle_z = -radians(rotation.z)
        return Point(
            point.x * cos(angle_z) - point.y * sin(angle_z),
            point.x * sin(angle_z) + point.y * cos(angle_z),
            point.z,
        )
