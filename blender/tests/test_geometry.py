import math

import pytest

from blender_buildings import geometry as g

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_area_and_perimeter():
    assert g.area(SQUARE) == 100
    assert g.perimeter(SQUARE) == 40
    assert g.signed_area(list(reversed(SQUARE))) == -100


def test_ensure_ccw_reverses_clockwise():
    cw = list(reversed(SQUARE))
    assert g.signed_area(g.ensure_ccw(cw)) > 0
    assert g.ensure_ccw(SQUARE) == [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def test_centroid_and_bbox():
    assert g.centroid(SQUARE) == pytest.approx((5, 5))
    assert g.bbox(SQUARE) == (0, 0, 10, 10)


@pytest.mark.parametrize("d", [1.0, -1.0, 0.25, -3.0])
def test_offset_square(d):
    out = g.offset_polygon(SQUARE, d)
    assert len(out) == 4
    assert g.area(out) == pytest.approx((10 + 2 * d) ** 2)


def test_offset_l_shape_keeps_vertex_count():
    L = [(0, 0), (20, 0), (20, 6), (10, 6), (10, 12), (0, 12)]
    out = g.offset_polygon(L, -0.5)
    assert len(out) == 6
    assert g.area(out) < g.area(L)
    assert g.signed_area(out) > 0


def test_is_rectangle():
    assert g.is_rectangle(SQUARE)
    assert not g.is_rectangle([(0, 0), (10, 0), (12, 10), (0, 10)])
    assert not g.is_rectangle([(0, 0), (1, 0), (1, 1)])


def test_rotate_translate():
    pts = g.rotate([(1, 0)], 90)
    assert pts[0] == pytest.approx((0, 1), abs=1e-9)
    assert g.translate([(1, 2)], 3, 4) == [(4, 6)]
    assert math.isclose(g.perimeter(g.rotate(SQUARE, 33)), 40)


def test_offset_spike_is_miter_limited():
    """Un sommet très aigu (emprise cadastrale réelle) ne doit pas projeter l'onglet à l'infini."""
    spike = [(0, 0), (20, 0), (20, 10), (10.0, 10.0), (10.05, 10.3), (0, 10)]
    out = g.offset_polygon(spike, 0.3)
    assert len(out) == 6
    for (x, y) in out:
        assert -1 <= x <= 21 and -1 <= y <= 11.5
