from boundingbox import BoundingBox
from point import Point


class Shape(object):
    def __init__(self, nr, shape_path, start_move_path, start_dir, end_dir):
        self._shape_path = shape_path
        self._start_move_path = start_move_path
        self._start_dir = start_dir
        self._end_dir = end_dir

        self.selected = False
        self.nr = nr
        self.disabled = True
        self.cut_cor = 41

        self.bb = self._calculate_bounding_box()

    @property
    def shape_path(self):
        return self._shape_path

    @property
    def start_move_path(self):
        return self._start_move_path

    @property
    def start_dir(self):
        return self._start_dir

    @property
    def end_dir(self):
        return self._end_dir

    def get_start_end_points(self):
        return self.shape_path[0], self.shape_path[-1]

    def _calculate_bounding_box(self):
        xmin = 1e9
        ymin = 1e9
        xmax = -1e9
        ymax = -1e9

        for x, y, _ in self._shape_path:
            xmin = min(xmin, x)
            ymin = min(ymin, y)
            xmax = max(xmax, x)
            ymax = max(ymax, y)

        return BoundingBox(ps=Point(xmin, ymin), pe=Point(xmax, ymax))

    def is_hit(self, xy_point, tolerance):
        bb = BoundingBox(
            Point(self.bb.ps.x - tolerance, self.bb.ps.y - tolerance),
            Point(self.bb.pe.x + tolerance, self.bb.pe.y + tolerance),
        )
        if not bb.contains(xy_point):
            return False

        last_point = Point(0, 0)
        hit = False
        first = True
        for x, y, _ in self.shape_path:
            point = Point(x, y)
            if not first and not (last_point == point):
                hit |= xy_point.distance_to_closed_line(last_point, point) <= tolerance
            if hit:
                break
            last_point = point
            first = False

        return hit
