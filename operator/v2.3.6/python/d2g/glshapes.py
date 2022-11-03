from __future__ import division
from math import pi, sin, cos
from point import Point
import minigl as GL


def _get_arc_points(origin, r, segments):
    points = []
    for i in range(segments + 1):
        angle = i * 2 * pi / segments
        xy = origin.get_arc_point(angle, r)
        points.append(xy)
    return points


def draw_sphere(r, lats, mlats, longs, mlongs):
    lats //= 2
    # based on http://www.cburch.com/cs/490/sched/feb8/index.html
    for i in range(mlats):
        lat0 = pi * (-0.5 + i / lats)
        z0 = r * sin(lat0)
        zr0 = r * cos(lat0)
        lat1 = pi * (-0.5 + (i + 1) / lats)
        z1 = r * sin(lat1)
        zr1 = r * cos(lat1)
        GL.glBegin(GL.GL_QUAD_STRIP)
        for j in range(mlongs + 1):
            lng = 2 * pi * j / longs
            x = cos(lng)
            y = sin(lng)

            GL.glNormal3f(x * zr0, y * zr0, z0)
            GL.glVertex3f(x * zr0, y * zr0, z0)
            GL.glNormal3f(x * zr1, y * zr1, z1)
            GL.glVertex3f(x * zr1, y * zr1, z1)
        GL.glEnd()


def draw_solid_circle(origin, r, z, segments):
    GL.glBegin(GL.GL_TRIANGLE_FAN)
    GL.glVertex3f(origin.x, -origin.y, z)
    points = _get_arc_points(origin, r, segments)
    for p in points:
        GL.glVertex3f(p.x, -p.y, z)
    GL.glEnd()


def draw_cone(origin, r, z_top, z_bottom, segments):
    GL.glBegin(GL.GL_TRIANGLE_FAN)
    GL.glVertex3f(origin.x, -origin.y, z_top)
    points = _get_arc_points(origin, r, segments)
    for p in points:
        GL.glVertex3f(p.x, -p.y, z_bottom)
    GL.glEnd()


def draw_cylinder(origin, r, z_top, z_bottom, segments):
    GL.glBegin(GL.GL_QUAD_STRIP)
    points = _get_arc_points(origin, r, segments)
    for p in points:
        GL.glVertex3f(p.x, -p.y, z_top)
        GL.glVertex3f(p.x, -p.y, z_bottom)
    GL.glEnd()


def draw_arrow_head(origin, rx, ry, rz, offset):
    r = 0.01
    segments = 10
    z_top = 0 + offset
    z_bottom = -0.02 + offset

    GL.glBegin(GL.GL_TRIANGLE_FAN)
    zero_top = Point(0, 0, z_top)
    GL.glVertex3f(
        zero_top * rx + origin.x, -zero_top * ry - origin.y, zero_top * rz + origin.z
    )
    for i in range(segments + 1):
        angle = i * 2 * pi / segments
        xy2 = Point.from_polar_coordinates(angle, r)
        xy2.z = z_bottom
        GL.glVertex3f(xy2 * rx + origin.x, -xy2 * ry - origin.y, xy2 * rz + origin.z)
    GL.glEnd()

    GL.glBegin(GL.GL_TRIANGLE_FAN)
    zero_bottom = Point(0, 0, z_bottom)
    GL.glVertex3f(
        zero_bottom * rx + origin.x,
        -zero_bottom * ry - origin.y,
        zero_bottom * rz + origin.z,
    )
    for i in range(segments + 1):
        angle = -i * 2 * pi / segments
        xy2 = Point.from_polar_coordinates(angle, r)
        xy2.z = z_bottom
        GL.glVertex3f(xy2 * rx + origin.x, -xy2 * ry - origin.y, xy2 * rz + origin.z)
    GL.glEnd()
