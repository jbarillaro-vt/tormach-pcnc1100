from __future__ import division
import logging
from math import pi
from d2g.color import Color
from d2g.boundingbox import BoundingBox
from d2g.point import Point
from d2g.shape import Shape

logger = logging.getLogger(__name__)


try:
    import minigl as GL
    from glshapes import (
        draw_sphere,
        draw_cone,
        draw_cylinder,
        draw_solid_circle,
        draw_arrow_head,
    )
except ImportError:
    raise Exception("For the 3d mode you need the minigl library from LinuxCNC.")

try:
    from hershey import Hershey
except ImportError:
    raise Exception("Requires hershey library from LinuxCNC")


class GlShape(object):
    def __init__(self, draw_object, draw_start_move, draw_arrows_direction, shape):
        self._draw_object = draw_object
        self._draw_start_move = draw_start_move
        self._draw_arrows_direction = draw_arrows_direction
        self._shape = shape

    @property
    def draw_object(self):
        return self._draw_object

    @property
    def draw_start_move(self):
        return self._draw_start_move

    @property
    def draw_arrows_direction(self):
        return self._draw_arrows_direction

    @property
    def shape(self):
        return self._shape


class GlArrow(object):
    def __init__(self, draw_line, draw_arrow_head, start_vector, end_vector):
        self._draw_line = draw_line
        self._draw_arrow_head = draw_arrow_head
        self._start_vector = start_vector
        self._end_vector = end_vector

    @property
    def draw_line(self):
        return self._draw_line

    @property
    def draw_arrow_head(self):
        return self._draw_arrow_head

    @property
    def start_vector(self):
        return self._start_vector

    @property
    def end_vector(self):
        return self._end_vector


class GlDraw(object):
    CAM_LEFT_X = -0.5
    CAM_RIGHT_X = 0.5
    CAM_BOTTOM_Y = 0.5
    CAM_TOP_Y = -0.5
    CAM_NEAR_Z = -14.0
    CAM_FAR_Z = 14.0

    COLOR_BACKGROUND = Color(0.0, 0.0, 0.0, 1.0)
    COLOR_NORMAL = Color(1.0, 1.0, 1.0, 1.0)
    COLOR_SELECT = Color(0.0, 1.0, 1.0, 1.0)
    COLOR_NORMAL_DISABLED = Color(0.4, 0.4, 0.4, 1.0)
    COLOR_SELECT_DISABLED = Color(0.0, 0.6, 0.6, 1.0)
    COLOR_ENTRY_ARROW = Color(0.0, 0.0, 1.0, 1.0)
    COLOR_EXIT_ARROW = Color(0.0, 1.0, 0.0, 1.0)
    COLOR_ROUTE = Color(0.3, 0.5, 0.5, 1.0)
    COLOR_START_MOVE = Color(0.7, 0.2, 0.75, 1.0)
    COLOR_BREAK = Color(1.0, 0.0, 1.0, 0.7)
    COLOR_LEFT = Color(0.8, 1.0, 0.8, 1.0)
    COLOR_RIGHT = Color(0.8, 0.8, 1.0, 1.0)
    COLOR_ORIENTATION_X = Color(1.0, 0.2, 0.2, 1.0)
    COLOR_ORIENTATION_Y = Color(0.2, 1.0, 0.2, 1.0)
    COLOR_ORIENTATION_Z = Color(0.2, 0.2, 1.0, 1.0)
    COLOR_DIMENSIONS = Color(1.0, 0.51, 0.53, 1.0)

    def __init__(self):
        self._shapes = {}
        self._raw_shapes = None
        self._export_route = []
        self._layers = []
        self._position = Point(0.0, 0.0, 0.0)
        self._rotation = Point(0.0, 0.0, 0.0)
        self._scale = 1.0
        self._scale_corr = 1.0
        self._width = 1.0
        self._height = 1.0
        self._shape_bb = BoundingBox()
        self._dimensions_bb = BoundingBox()
        self._orientation = 0
        self._wp_zero = 0
        self._dimensions = 0
        self._gl_lists = []
        self._hershey = None
        self._number_format = '%.3f'
        self._selected_line_width = 2

        self._autoscale_enabled = True

        self.show_disabled_paths = True
        self.show_path_directions = True

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, value):
        self._scale = value
        self._autoscale_enabled = False

    @property
    def scale_correction(self):
        return self._scale_corr

    @property
    def position(self):
        return self._position

    @position.setter
    def position(self, value):
        self._position = value

    @property
    def rotation(self):
        return self._rotation

    @rotation.setter
    def rotation(self, value):
        self._rotation = value

    @property
    def shapes(self):
        return self._shapes

    @shapes.setter
    def shapes(self, value):
        self._raw_shapes = value  # store raw shape data for repaint
        self._reset_all()
        if not any(value):
            return
        self._paint_shapes(value)
        self._update_shapes_with_details()
        if self._autoscale_enabled:
            self._autoscale()

    @property
    def export_route(self):
        return self._export_route

    @export_route.setter
    def export_route(self, data):
        self._export_route = []
        self._paint_export_route(data)

    @property
    def layers(self):
        return self._layers

    @layers.setter
    def layers(self, value):
        self._layers = value
        self._update_shapes_with_details()

    @property
    def number_format(self):
        return self._number_format

    @number_format.setter
    def number_format(self, value):
        self._number_format = value

    def redraw(self):
        if self._raw_shapes:
            self.shapes = self._raw_shapes

    def reset_viewport(self):
        self._position = Point(0.0, 0.0, 0.0)
        self._rotation = Point(0.0, 0.0, 0.0)
        self._scale = 1.0
        self._autoscale_enabled = True

    def set_front_view(self):
        self.reset_viewport()
        self._autoscale()
        self._rotation = Point(90.0, 0.0, 0.0)
        position = self._position
        position.y -= position.y
        self._position = position

    def set_top_view(self):
        self.reset_viewport()
        self._autoscale()

    def set_side_view(self):
        self.reset_viewport()
        self._autoscale()
        self._rotation = Point(0.0, -270.0, 0.0)
        position = self._position
        position.x -= position.x
        self._position = position

    def set_iso_view(self):
        self.reset_viewport()
        self._autoscale()
        self._rotation = Point(-45.0, 0.0, 45.0)
        position = self._position
        position.x += position.x / 2
        position.y -= position.y
        position.z -= position.z
        self._position = position

    def _paint_shapes(self, shapes):
        if len(shapes) == 1:  # insert dummy shape if only 1 shape
            shapes.append((-1, [], [], (0, 1, 0), (0, 1, 0)))
        for shape in shapes:
            gl_shape = self._paint_shape(shape)
            self._shapes[gl_shape.shape.nr] = gl_shape
        self._draw_wp_zero()
        self._draw_dimensions()

    def _paint_export_route(self, arrows):
        for arrow in arrows:
            gl_arrow = self._paint_route_arrow(arrow)
            self._export_route.append(gl_arrow)

    def _update_shapes_with_details(self):
        for layer, shapes in self._layers:
            for shape in shapes:
                nr = shape['nr']
                if nr not in self._shapes:
                    continue
                gl_shape = self._shapes[nr]
                for key in shape:
                    setattr(gl_shape.shape, key, shape[key])

    def set_size(self, width, height):
        self._width = width
        self._height = height

    def _reset_all(self):
        for gl_list in self._gl_lists:
            GL.glDeleteLists(gl_list, 1)
        self._gl_lists = []
        if self._wp_zero > 0:
            GL.glDeleteLists(self._wp_zero, 1)
        self._wp_zero = 0
        if self._dimensions > 0:
            GL.glDeleteLists(self._dimensions, 1)
        self._dimensions = 0
        self._shapes.clear()
        self._export_route = []

        self._shape_bb = BoundingBox()

    def initialize_gl(self):
        self._set_clear_color(self.COLOR_BACKGROUND)

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_CULL_FACE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        self._hershey = Hershey()

        self._draw_orientation_arrows()

    def paint_gl(self):
        GL.glPushMatrix()
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if not any(self._shapes):
            GL.glPopMatrix()
            return
        GL.glTranslatef(self._position.x, self._position.y, self._position.z)
        GL.glScalef(self._scale, self._scale, self._scale)
        GL.glRotatef(self._rotation.x, -1.0, 0.0, 0.0)
        GL.glRotatef(self._rotation.y, 0.0, 1.0, 0.0)
        GL.glRotatef(self._rotation.z, 0.0, 0.0, 1.0)

        # draw shapes
        for _, gl_shape in self._shapes.items():
            shape = gl_shape.shape
            if shape.selected:
                GL.glLineWidth(self._selected_line_width)
                if not shape.disabled:
                    self._set_color(self.COLOR_START_MOVE)
                    GL.glCallList(gl_shape.draw_start_move)
                    self._set_color(self.COLOR_SELECT)
                    GL.glCallList(gl_shape.draw_object)
                elif self.show_disabled_paths:
                    self._set_color(self.COLOR_SELECT_DISABLED)
                    GL.glCallList(gl_shape.draw_object)
                GL.glLineWidth(1)
            else:
                if not shape.disabled:
                    if shape.cut_cor == 41:
                        self._set_color(self.COLOR_LEFT)
                    elif shape.cut_cor == 42:
                        self._set_color(self.COLOR_RIGHT)
                    else:
                        self._set_color(self.COLOR_NORMAL)
                    GL.glCallList(gl_shape.draw_object)
                    if self.show_path_directions:
                        self._set_color(self.COLOR_START_MOVE)
                        GL.glCallList(gl_shape.draw_start_move)
                else:
                    self._set_color(self.COLOR_NORMAL_DISABLED)
                    GL.glCallList(gl_shape.draw_object)
            # TODO: break_layer

        # draw dimensions
        if self._dimensions > 0:
            GL.glCallList(self._dimensions)

        # draw optimization route
        self._set_color(self.COLOR_ROUTE)
        GL.glLineStipple(2, 0xAAAA)
        GL.glEnable(GL.GL_LINE_STIPPLE)
        for arrow in self._export_route:
            GL.glCallList(arrow.draw_line)
        GL.glDisable(GL.GL_LINE_STIPPLE)

        unzoom = self._scale_corr / self._scale
        GL.glScalef(unzoom, unzoom, unzoom)
        scale_arrow = self._scale / self._scale_corr
        for arrow in self._export_route:
            end = scale_arrow * arrow.end_vector
            GL.glTranslatef(end.x, -end.y, end.z)
            GL.glCallList(arrow.draw_arrow_head)
            GL.glTranslatef(-end.x, end.y, -end.z)

        # draw direction arrows
        for _, gl_shape in self._shapes.items():
            shape = gl_shape.shape
            if (
                not shape.selected
                or (shape.disabled and not self.show_disabled_paths)
                and not self.show_disabled_paths
                or shape.disabled
            ):
                continue
            start, end = shape.get_start_end_points()
            start = scale_arrow * Point(*start)
            end = scale_arrow * Point(*end)
            GL.glTranslatef(start.x, start.y, start.z)
            GL.glCallList(gl_shape.draw_arrows_direction[0])
            GL.glTranslatef(-start.x, -start.y, -start.z)
            GL.glTranslatef(end.x, end.y, end.z)
            GL.glCallList(gl_shape.draw_arrows_direction[1])
            GL.glTranslatef(-end.x, -end.y, -end.z)

        GL.glCallList(self._orientation)

        GL.glPopMatrix()

    def resize_gl(self, width, height):
        GL.glViewport(0, 0, width, height)
        side = min(width, height)

        GL.glPushMatrix()
        GL.glMatrixMode(GL.GL_PROJECTION)
        if width >= height:
            scale_x = width / height
            GL.glOrtho(
                self.CAM_LEFT_X * scale_x,
                self.CAM_RIGHT_X * scale_x,
                self.CAM_BOTTOM_Y,
                self.CAM_TOP_Y,
                self.CAM_NEAR_Z,
                self.CAM_FAR_Z,
            )
        else:
            scale_y = height / width
            GL.glOrtho(
                self.CAM_LEFT_X,
                self.CAM_RIGHT_X,
                self.CAM_BOTTOM_Y * scale_y,
                self.CAM_TOP_Y * scale_y,
                self.CAM_NEAR_Z,
                self.CAM_FAR_Z,
            )
            self._scale_corr = 400 / side
        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glPopMatrix()

    def _paint_route_arrow(self, arrow):
        start_vector, end_vector = arrow
        start_vector = Point(*start_vector)
        end_vector = Point(*end_vector)
        return GlArrow(
            self._make_gl_list_from_route_path(start_vector, end_vector),
            self._make_route_arrow_head(start_vector, end_vector),
            start_vector,
            end_vector,
        )

    def _make_gl_list_from_route_path(self, start_vector, end_vector):
        gen_list = GL.glGenLists(1)
        self._gl_lists.append(gen_list)
        GL.glNewList(gen_list, GL.GL_COMPILE)

        GL.glBegin(GL.GL_LINES)
        GL.glVertex3f(start_vector.x, -start_vector.y, start_vector.z)
        GL.glVertex3f(end_vector.x, -end_vector.y, end_vector.z)
        GL.glEnd()

        GL.glEndList()
        return gen_list

    def _paint_shape(self, shape):
        nr, shape_path, start_move_path, start, end = shape
        return GlShape(
            self._make_gl_list_from_path(shape_path, update_bb=True),
            self._make_gl_list_from_path(start_move_path),
            self._make_dir_arrows(start, end),
            Shape(*shape),
        )

    def _make_gl_list_from_path(self, shape_path, update_bb=False):
        gen_list = GL.glGenLists(1)
        self._gl_lists.append(gen_list)
        GL.glNewList(gen_list, GL.GL_COMPILE)

        GL.glBegin(GL.GL_LINES)
        for vertex in shape_path:
            GL.glVertex3f(*vertex)
        GL.glEnd()

        GL.glEndList()

        if update_bb:
            bb = self._make_bounding_box_from_path(shape_path)
            self._shape_bb = self._shape_bb.join(bb)

        return gen_list

    def _make_bounding_box_from_path(self, shape_path):
        xmin = 1e9
        ymin = 1e9
        zmin = 1e9
        xmax = -1e9
        ymax = -1e9
        zmax = -1e9

        for x, y, z in shape_path:
            xmin = min(xmin, x)
            ymin = min(ymin, y)
            zmin = min(zmin, z)
            xmax = max(xmax, x)
            ymax = max(ymax, y)
            zmax = max(zmax, z)

        return BoundingBox(ps=Point(xmin, ymin, zmin), pe=Point(xmax, ymax, zmax))

    def _make_dir_arrows(self, start, end):
        start_arrow = GL.glGenLists(1)
        self._gl_lists.append(start_arrow)
        GL.glNewList(start_arrow, GL.GL_COMPILE)
        self._set_color(self.COLOR_ENTRY_ARROW)
        self._draw_dir_arrow(Point(0, 0, 0), Point(*start), True)
        GL.glEndList()

        end_arrow = GL.glGenLists(1)
        self._gl_lists.append(end_arrow)
        GL.glNewList(end_arrow, GL.GL_COMPILE)
        self._set_color(self.COLOR_EXIT_ARROW)
        self._draw_dir_arrow(Point(0, 0, 0), Point(*end), False)
        GL.glEndList()

        return start_arrow, end_arrow

    def _draw_dir_arrow(self, origin, direction, start_error):
        offset = 0.0 if start_error else 0.05
        z_middle = -0.02 + offset
        z_bottom = -0.05 + offset
        rx, ry, rz = self._get_rotation_vectors(Point(0, 0, 1), direction)

        draw_arrow_head(origin, rx, ry, rz, offset)

        GL.glBegin(GL.GL_LINES)
        zero_middle = Point(0, 0, z_middle)
        GL.glVertex3f(
            zero_middle * rx + origin.x,
            -zero_middle * ry - origin.y,
            zero_middle * rz + origin.z,
        )
        zero_bottom = Point(0, 0, z_bottom)
        GL.glVertex3f(
            zero_bottom * rx + origin.x,
            -zero_bottom * ry - origin.y,
            zero_bottom * rz + origin.z,
        )
        GL.glEnd()

    def _make_route_arrow_head(self, start, end):
        gl_gen = GL.glGenLists(1)
        self._gl_lists.append(gl_gen)

        if end == start:
            direction = Point(0.0, 0.0, 1.0)
        else:
            direction = (end - start).unit_vector()

        GL.glNewList(gl_gen, GL.GL_COMPILE)
        rx, ry, rz = self._get_rotation_vectors(Point(0.0, 0.0, 1.0), direction)
        draw_arrow_head(Point(0.0, 0.0, 0.0), rx, ry, rz, 0.0)
        GL.glEndList()

        return gl_gen

    def _set_clear_color(self, c):
        GL.glClearColor(c.red, c.green, c.blue, c.alpha)

    def _set_color(self, c):
        self._set_color_rgba(c.red, c.green, c.blue, c.alpha)

    def _set_color_rgba(self, r, g, b, a):
        GL.glColor4f(r, g, b, a)

    def _autoscale(self, margin_factor=0.9):
        # determine aspect ratio scale
        if self._width >= self._height:
            aspect_scale_x = self._width / self._height
            aspect_scale_y = 1.0
        else:
            aspect_scale_x = 1.0
            aspect_scale_y = self._height / self._width
        bb = self._dimensions_bb.join(
            BoundingBox(Point(0, 0), Point(0, 0))
        )  # include wp zero
        scale_x = (
            (GlDraw.CAM_RIGHT_X - GlDraw.CAM_LEFT_X)
            * aspect_scale_x
            / (bb.pe.x - bb.ps.x)
        )
        scale_y = (
            (GlDraw.CAM_BOTTOM_Y - GlDraw.CAM_TOP_Y)
            * aspect_scale_y
            / (bb.pe.y - bb.ps.y)
        )
        self._scale = min(scale_x, scale_y) * margin_factor
        self._position.x = (
            (GlDraw.CAM_LEFT_X + GlDraw.CAM_RIGHT_X) * margin_factor * aspect_scale_x
            - (bb.ps.x + bb.pe.x) * self._scale
        ) / 2
        self._position.y = (
            (GlDraw.CAM_TOP_Y + GlDraw.CAM_BOTTOM_Y) * margin_factor * aspect_scale_y
            - (bb.pe.y + bb.ps.y) * self._scale
        ) / 2
        self._position.z = 0.0
        self._aspect_scale_x = aspect_scale_x
        self._aspect_scale_y = aspect_scale_y

    @staticmethod
    def _get_rotation_vectors(origin_unit_vector, to_unit_vector):
        """
        Generates a rotation matrix: to_unit_vector = matrix * origin_unit_vector
        """
        # based on:
        # http://math.stackexchange.com/questions/180418/calculate-rotation-matrix-to-align-vector-a-to-vector-b-in-3d

        if origin_unit_vector == to_unit_vector:
            return Point(1, 0, 0), Point(0, 1, 0), Point(0, 0, 1)

        v = origin_unit_vector.cross_product(to_unit_vector)
        mn = (1 - origin_unit_vector * to_unit_vector) / (v.length ** 2)

        vx = Point(1, -v.z, v.y) + mn * Point(
            -v.y ** 2 - v.z ** 2, v.x * v.y, v.x * v.z
        )
        vy = Point(v.z, 1, -v.x) + mn * Point(
            v.x * v.y, -v.x ** 2 - v.z ** 2, v.y * v.z
        )
        vz = Point(-v.y, v.x, 1) + mn * Point(
            v.x * v.z, v.y * v.z, -v.x ** 2 - v.y ** 2
        )

        return vx, vy, vz

    def _draw_wp_zero(self):
        r = 0.02
        segments = 20  # multiple of 4

        self._wp_zero = GL.glGenLists(1)
        GL.glNewList(self._wp_zero, GL.GL_COMPILE)

        self._set_color_rgba(0.8, 0.8, 0.8, 0.7)  # light gray
        draw_sphere(r, segments, segments // 4, segments, segments // 4)

        GL.glBegin(GL.GL_TRIANGLE_FAN)
        GL.glVertex3f(0, 0, 0)
        points = []
        for i in range(segments // 4 + 1):
            ang = -i * 2 * pi / segments
            xy2 = Point().get_arc_point(ang, r)
            points.append(xy2)
        for p in points:
            GL.glVertex3f(p.x, 0, p.y)
        for p in points:
            GL.glVertex3f(0, -p.y, -p.x)
        for p in points:
            GL.glVertex3f(-p.y, p.x, 0)
        GL.glEnd()

        self._set_color_rgba(0.6, 0.6, 0.6, 0.5)  # light gray
        draw_sphere(r * 1.25, segments, segments, segments, segments)

        GL.glEndList()

    def _draw_orientation_arrow(self):
        r_cone = 0.008
        r_cylinder = 0.003
        z_top = 0.12
        z_middle = 0.1
        z_bottom = 0.0
        segments = 20

        arrow = GL.glGenLists(1)
        GL.glNewList(arrow, GL.GL_COMPILE)

        draw_cone(Point(), r_cone, z_top, z_middle, segments)
        draw_solid_circle(Point(), r_cylinder, z_middle, segments)
        draw_cylinder(Point(), r_cylinder, z_middle, z_bottom, segments)
        draw_solid_circle(Point(), r_cylinder, z_bottom, segments)

        GL.glEndList()

        return arrow

    def _draw_orientation_arrows(self):
        arrow = self._draw_orientation_arrow()

        self._orientation = GL.glGenLists(1)
        GL.glNewList(self._orientation, GL.GL_COMPILE)

        self._set_color(self.COLOR_ORIENTATION_Z)
        GL.glCallList(arrow)

        GL.glRotatef(90, 0, 1, 0)
        self._set_color(self.COLOR_ORIENTATION_X)
        GL.glCallList(arrow)

        GL.glRotatef(90, 1, 0, 0)
        self._set_color(self.COLOR_ORIENTATION_Y)
        GL.glCallList(arrow)

        GL.glEndList()

    def _draw_dimensions(self):
        bb = self._shape_bb
        object_size = max(bb.width, bb.length)
        scale_factor = object_size / 20
        shape_offset = 0.75 * scale_factor
        text_offset = 1.9 * scale_factor + shape_offset
        line_offset = 1.0 * scale_factor + shape_offset

        # calculate bounding box of shape and dimensions text
        self._dimensions_bb = bb.join(
            BoundingBox(
                ps=(bb.ps - Point(3 * scale_factor, 0.0)),
                pe=(bb.pe - Point(0.0, -3 * scale_factor)),
            )
        )

        self._dimensions = GL.glGenLists(1)

        GL.glNewList(self._dimensions, GL.GL_COMPILE)
        GL.glPushMatrix()
        self._set_color(self.COLOR_DIMENSIONS)

        def draw_side(length):
            string = self._number_format % length
            GL.glPushMatrix()
            GL.glRotatef(180, 1, 0, 0)

            GL.glBegin(GL.GL_LINES)
            GL.glVertex3f(0.0, -shape_offset, 0.0)
            GL.glVertex3f(0.0, -text_offset, 0.0)
            GL.glVertex3f(0.0, -line_offset, 0.0)
            GL.glVertex3f(length, -line_offset, 0.0)
            GL.glVertex3f(length, -shape_offset, 0.0)
            GL.glVertex3f(length, -text_offset, 0.0)
            GL.glEnd()

            if not self._hershey:
                return
            GL.glTranslatef(length / 2.0, -text_offset, 0.0)
            GL.glScalef(scale_factor, scale_factor, scale_factor)
            self._hershey.center_string(string)
            self._hershey.plot_string(string)
            GL.glPopMatrix()

        GL.glTranslatef(bb.ps.x, bb.pe.y, bb.ps.z)
        draw_side(bb.width)
        GL.glTranslatef(0.0, -bb.length, 0.0)
        GL.glRotatef(90, 0, 0, 1)
        draw_side(bb.length)

        GL.glPopMatrix()
        GL.glEndList()
