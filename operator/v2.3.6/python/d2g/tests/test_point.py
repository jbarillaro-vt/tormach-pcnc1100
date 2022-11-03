from __future__ import division
import pytest

from d2g.point import Point


def test_point_division_with_xy_works():
    point = Point(1.0, 2.0)

    result = point / 2

    assert result.x == 0.5
    assert result.y == 1.0
    assert result.z is None


def test_point_division_with_xyz_works():
    point = Point(6.0, 9.0, 3.0)

    result = point / 3

    assert result.x == 2.0
    assert result.y == 3.0
    assert result.z == 1.0


@pytest.mark.parametrize(
    "p1,p2,p3,expected",
    [
        (Point(0.0, 0.0), Point(1.0, 1.0), Point(0.5, 0.5), 0.0),
        (Point(1.0, 1.0), Point(0.0, 0.0), Point(0.5, 0.5), 0.0),
        (Point(0.0, 0.0), Point(1.0, 0.0), Point(0.25, 0.5), 0.5),
        (Point(1.0, 0.0), Point(0.0, 0.0), Point(0.25, 0.5), 0.5),
    ],
)
def test_calculating_distance_to_line_works(p1, p2, p3, expected):
    distance = p3.distance_to_line(p1, p2)

    assert distance == expected


@pytest.mark.parametrize(
    "p1,p2,p3,expected",
    [
        (Point(0.0, 0.0), Point(1.0, 1.0), Point(0.5, 0.5), 0.0),
        (Point(1.0, 1.0), Point(0.0, 0.0), Point(0.5, 0.5), 0.0),
        (Point(0.0, 0.0), Point(1.0, 0.0), Point(0.25, 0.5), 0.5),
        (Point(0.0, 0.0), Point(1.0, 0.0), Point(-1.0, 0.0), 1.0),  # left of line
        (Point(0.0, 0.0), Point(1.0, 0.0), Point(2.0, 0.0), 1.0),  # right of line
        (Point(0.0, 1.0), Point(0.0, 0.0), Point(0.2, 0.5), 0.2),  # top to bottom
        (Point(0.0, 0.0), Point(0.0, 1.0), Point(0.2, 0.5), 0.2),  # bottom to top
    ],
)
def test_calculating_distance_to_closed_line_works(p1, p2, p3, expected):
    distance = p3.distance_to_closed_line(p1, p2)

    assert distance == expected


@pytest.mark.parametrize(
    "p1,p2,expected",
    [(Point(0.0, 0.0), Point(0.0, 1.0), 1.0), (Point(1.5, 2.0), Point(1.0, 2.0), 0.5)],
)
def test_calculating_distance_to_point_works(p1, p2, expected):
    distance = p1.distance_to_point(p2)

    assert distance == expected
