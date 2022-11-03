import pytest

from d2g.boundingbox import BoundingBox
from d2g.point import Point


def test_joining_bounding_boxes_works():
    bb1 = BoundingBox(Point(0, 0), Point(1, 1))
    bb2 = BoundingBox(Point(-1, -2), Point(0.5, 4))

    new_bb = bb1.join(bb2)

    assert new_bb.ps.x == -1
    assert new_bb.ps.y == -2
    assert new_bb.pe.x == 1
    assert new_bb.pe.y == 4


def test_joining_empty_bouding_box_works():
    bb1 = BoundingBox()
    bb2 = BoundingBox(Point(1, 2), Point(1.5, 4))

    new_bb = bb1.join(bb2)

    assert new_bb.ps.x == 1
    assert new_bb.ps.y == 2
    assert new_bb.pe.x == 1.5
    assert new_bb.pe.y == 4


def test_joining_two_negative_bb_works():
    bb1 = BoundingBox(Point(3, -14), Point(5, -1))
    bb2 = BoundingBox(Point(1, -10), Point(2, -2))

    new_bb = bb1.join(bb2)

    assert new_bb.ps.x == 1
    assert new_bb.ps.y == -14
    assert new_bb.pe.x == 5
    assert new_bb.pe.y == -1


@pytest.mark.parametrize(
    "point,bb,expected",
    [
        (Point(4, -4), BoundingBox(Point(3, -14), Point(5, -1)), True),
        (Point(4, -4), BoundingBox(Point(1, -10), Point(2, -2)), False),
        (
            Point(-28.523965, -30.103285),
            BoundingBox(Point(-35.133731, -35.133731), Point(-24.866269, -24.866269)),
            True,
        ),
    ],
)
def test_contains_works(point, bb, expected):
    result = bb.contains(point)

    assert result is expected


@pytest.mark.parametrize(
    "bb,expected",
    [
        (BoundingBox(Point(3, -14), Point(5, -1)), 2),
        (BoundingBox(Point(1, -10), Point(2, -2)), 1),
        (BoundingBox(Point(-35.1, -35.41), Point(-24.9, -24.86)), 10.2),
    ],
)
def test_width_returns_correct_value(bb, expected):
    result = bb.width

    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "bb,expected",
    [
        (BoundingBox(Point(3, -14), Point(5, -1)), 13),
        (BoundingBox(Point(1, -10), Point(2, -2)), 8),
        (BoundingBox(Point(-35.1, -35.41), Point(-24.9, -24.86)), 10.55),
    ],
)
def test_length_returns_correct_value(bb, expected):
    result = bb.length

    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    "bb,expected",
    [
        (BoundingBox(Point(3, -14), Point(5, -1)), None),
        (BoundingBox(Point(3, -14, -3.0), Point(5, -1, 0.0)), 3),
        (BoundingBox(Point(1, -10, 2), Point(2, -2, 6)), 4),
        (BoundingBox(Point(-35.1, -35.41, -3.4), Point(-24.9, -24.86, 3.2)), 6.6),
    ],
)
def test_height_returns_correct_value(bb, expected):
    result = bb.height

    assert result == pytest.approx(expected)
