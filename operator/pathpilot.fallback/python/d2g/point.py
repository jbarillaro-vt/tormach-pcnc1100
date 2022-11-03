from __future__ import division

from math import cos, sin, sqrt


class Point(object):
    def __init__(self, x=0.0, y=0.0, z=None):
        self._x = x
        self._y = y
        self._z = z

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        self._x = value

    @property
    def y(self):
        return self._y

    @y.setter
    def y(self, value):
        self._y = value

    @property
    def z(self):
        return self._z

    @z.setter
    def z(self, value):
        self._z = value

    @property
    def length(self):
        return sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def cross_product(self, other):
        if self.z is not None:
            return Point(
                self.y * other.z - self.z * other.y,
                self.z * other.x - self.x * other.z,
                self.x * other.y - self.y * other.x,
            )
        else:
            raise RuntimeError(
                'Cannot calculate cross product for 2 dimensional vectors'
            )

    def get_arc_point(self, ang=0, r=1):
        return Point(x=self.x + cos(ang) * r, y=self.y + sin(ang) * r)

    def distance_to_point(self, other):
        return sqrt((other.x - self.x) ** 2 + (other.y - self.y) ** 2)

    def distance_to_line(self, p1, p2):
        """
        Distance to a line through p1 and p2.
        """
        x_diff = p2.x - p1.x
        y_diff = p2.y - p1.y
        num = abs(y_diff * self.x - x_diff * self.y + p2.x * p1.y - p2.y * p1.x)
        den = sqrt(y_diff ** 2 + x_diff ** 2)
        return num / den

    def distance_to_closed_line(self, p1, p2):
        """
        Distance to a line starting at p1 and ending at p2.
        """
        if p1.x > p2.x:
            tmp = p2
            p2 = p1
            p1 = tmp
        downward = p1.y < p2.y
        if self.x < p1.x and (
            (downward and self.y <= p1.y) or (not downward and self.y >= p1.y)
        ):
            return self.distance_to_point(p1)
        elif self.x > p2.x and (
            (downward and self.y >= p2.y) or (not downward and self.y <= p2.y)
        ):
            return self.distance_to_point(p2)
        else:
            return self.distance_to_line(p1, p2)

    def unit_vector(self):
        return self / self.length

    @staticmethod
    def from_polar_coordinates(angle, radius):
        return Point(cos(angle) * radius, sin(angle) * radius)

    def __mul__(self, other):
        """ Scalar / Dot product of two points """
        output = self.x * other.x + self.y * other.y
        if self.z is not None:
            output += self.z * other.z
        return output

    def __rmul__(self, other):
        return Point(self.x * other, self.y * other, (self.z is None) or self.z * other)

    def __truediv__(self, other):
        if self.z is not None:
            return Point(x=self.x / other, y=self.y / other, z=self.z / other)
        else:
            return Point(x=self.x / other, y=self.y / other)

    def __neg__(self):
        return -1.0 * self

    def __add__(self, other):
        x = self.x + other.x
        y = self.y + other.y
        z = None
        if self.z is not None:
            z = self.z + other.z
        return Point(x, y, z)

    def __sub__(self, other):
        return self.__add__(-other)

    def __eq__(self, other):
        return self.x == other.x and self.y == other.y and self.z == other.z

    def __str__(self):
        if self._z is not None:
            return 'Point(%f, %f, %f)' % (self.x, self.y, self.z)
        else:
            return 'Point(%f, %f)' % (self.x, self.y)

    def __repr__(self):
        return self.__str__()
