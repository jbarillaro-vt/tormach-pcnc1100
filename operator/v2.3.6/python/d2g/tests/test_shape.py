import pytest

from d2g.shape import Shape
from d2g.point import Point


@pytest.fixture
def shape1():
    path = []
    path.append((0.0, 0.0, 0.0))
    path.append((1.0, 0.0, 0.0))
    path.append((1.0, 1.0, 0.0))
    path.append((0.0, 1.0, 0.0))
    return Shape(1, path, None, None, None)


def test_bounding_box_calculation_works(shape1):
    assert shape1.bb.ps == Point(0.0, 0.0)
    assert shape1.bb.pe == Point(1.0, 1.0)


def test_point_on_shape_outline_triggers_is_hit(shape1):
    assert shape1.is_hit(Point(0.5, 0.0), 0.2) is True


def test_point_inside_shape_does_not_trigger_is_hit(shape1):
    assert shape1.is_hit(Point(0.5, 0.5), 0.2) is False
