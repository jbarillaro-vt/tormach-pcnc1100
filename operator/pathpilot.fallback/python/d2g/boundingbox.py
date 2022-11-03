from d2g.point import Point
from copy import deepcopy


class BoundingBox(object):
    def __init__(self, ps=None, pe=None):
        self._ps = ps
        self._pe = pe

    @property
    def ps(self):
        return self._ps

    @property
    def pe(self):
        return self._pe

    @property
    def width(self):
        return self._pe.x - self._ps.x

    @property
    def length(self):
        return self._pe.y - self._ps.y

    @property
    def height(self):
        if self.pe.z is None or self.ps.z is None:
            return None
        else:
            return self.pe.z - self.ps.z

    def join(self, other):
        if not self.ps:
            return deepcopy(other)
        elif not other.ps:
            return deepcopy(self)
        else:
            xmin = min(self.ps.x, other.ps.x)
            xmax = max(self.pe.x, other.pe.x)
            ymin = min(self.ps.y, other.ps.y)
            ymax = max(self.pe.y, other.pe.y)
            zmin = min(self.ps.z, other.ps.z)
            zmax = min(self.pe.z, other.pe.z)
            return BoundingBox(ps=Point(xmin, ymin, zmin), pe=Point(xmax, ymax, zmax))

    def contains(self, xy_point):
        return (
            (xy_point.x >= self._ps.x)
            and (xy_point.y >= self._ps.y)
            and (xy_point.x <= self._pe.x)
            and (xy_point.y <= self._pe.y)
        )

    def __str__(self):
        return 'BoundingBox { Ps (%s), Pe (%s) }' % (str(self.ps), str(self.pe))

    def __repr__(self):
        return self.__str__()
