# app/tests/test_geometry.py

import pytest

from plantiq.engine.geometry import is_simple, point_in_polygon, polygon_area, pull_inside

SQUARE = [(0, 0), (200, 0), (200, 200), (0, 200)]
BOW_TIE = [(0, 0), (100, 100), (100, 0), (0, 100)]
L_SHAPE = [(0, 0), (200, 0), (200, 100), (100, 100), (100, 200), (0, 200)]


def test_simple_outline_is_accepted():
    assert is_simple(SQUARE)
    assert is_simple(L_SHAPE)


def test_self_crossing_outline_is_rejected():
    assert not is_simple(BOW_TIE)


def test_area_of_a_square():
    assert polygon_area(SQUARE) == pytest.approx(40000)


@pytest.mark.parametrize(
    ("point", "inside"),
    [
        ((100, 100), True),
        ((300, 100), False),
        # The ray passes exactly through a vertex: the case the half-open rule exists for
        ((100, 0), True),
    ],
)
def test_point_in_square(point, inside):
    assert point_in_polygon(point, SQUARE) is inside


def test_concave_room_excludes_its_notch():
    assert not point_in_polygon((150, 150), L_SHAPE)
    assert point_in_polygon((50, 150), L_SHAPE)


def test_pull_inside_snaps_a_near_miss_onto_the_wall():
    assert pull_inside((205, 100), SQUARE, 10.0) == (200.0, 100.0)


def test_pull_inside_rejects_a_far_point():
    assert pull_inside((250, 100), SQUARE, 10.0) is None
