import pytest
from d2g.boundingbox import BoundingBox
from d2g.point import Point


@pytest.fixture
def gldraw():
    from d2g.gldraw import GlDraw

    return GlDraw()


@pytest.fixture
def tuple_path():
    path = []
    path.append((-1.0, 0.0, 0.0))
    path.append((1.0, 2.0, 3.0))
    path.append((3.0, 2.0, 1.0))
    return path


@pytest.mark.skip
def test_making_gl_list_from_tuple_path_works(gldraw, tuple_path):
    path = gldraw._make_gl_list_from_path(tuple_path)

    assert len(path) == 3


def test_making_bounding_box_from_path_works(gldraw, tuple_path):
    bb = gldraw._make_bounding_box_from_path(tuple_path)

    assert bb.ps.x == -1.0
    assert bb.ps.y == 0.0
    assert bb.pe.x == 3.0
    assert bb.pe.y == 2.0
    assert bb.ps.z == 0.0
    assert bb.pe.z == 3.0


def test_autoscale_scaling_of_viewport_for_landcscape_layout_works(gldraw):
    gldraw._dimensions_bb = BoundingBox(Point(-1, -2), Point(1, 2))
    gldraw._width = 1000
    gldraw._height = 500

    gldraw._autoscale(margin_factor=1.0)

    # 4 height, 2 width => x aspect scale = 2 and y aspect scale is 1
    # this means we must have a scale factor of 0.25 to fit the object
    assert gldraw.scale == 0.25
    assert gldraw.position.x == 0.0
    assert gldraw.position.y == 0.0
    assert gldraw.position.z == 0.0


def test_autoscale_positioning_of_viewport_for_landscape_layout_works(gldraw):
    gldraw._dimensions_bb = BoundingBox(Point(0, 0), Point(2, 1))
    gldraw._width = 1000
    gldraw._height = 500

    gldraw._autoscale(margin_factor=1.0)

    # 1 height, 2 width => x aspect scale = 1 and y aspect scale is 2
    # this means we must have a scale factor of 1.0 to fit the object
    assert gldraw.scale == 1.0
    # move object left and down to center in the viewport
    assert gldraw.position.x == -1.0
    assert gldraw.position.y == -0.5
    assert gldraw.position.z == 0.0


def test_get_rotation_vectors_works(gldraw):
    origin_unit_vector = Point(1.0, 0.0, 0.0)
    to_unit_vector = Point(0.0, 1.0, 0.0)

    rx, ry, rz = gldraw._get_rotation_vectors(origin_unit_vector, to_unit_vector)

    assert rx == Point(0, -1, 0)
    assert ry == Point(1, 0, 0)
    assert rz == Point(0, 0, 1)
