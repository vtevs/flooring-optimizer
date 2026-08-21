"""Supplier A/B board geometry and tongue/groove definitions."""

from floorplan.models import BoardEdges, EdgeType
from floorplan.stock import orientation_for_rotation, supplier_edges


T = EdgeType.TONGUE
G = EdgeType.GROOVE


def _edges(top, right, bottom, left):
    return BoardEdges(top=top, right=right, bottom=bottom, left=left)


def test_supplier_a_rotations_preserve_edges_and_geometry_orientation():
    assert supplier_edges("A", 0) == _edges(T, G, G, T)
    assert supplier_edges("A", 90) == _edges(G, G, T, T)
    assert supplier_edges("A", 180) == _edges(G, T, T, G)
    assert supplier_edges("A", 270) == _edges(T, T, G, G)

    assert orientation_for_rotation(0) == "vertical"
    assert orientation_for_rotation(90) == "horizontal"
    assert orientation_for_rotation(180) == "vertical"
    assert orientation_for_rotation(270) == "horizontal"


def test_supplier_b_rotations_preserve_edges_and_geometry_orientation():
    assert supplier_edges("B", 0) == _edges(T, T, G, G)
    assert supplier_edges("B", 90) == _edges(T, G, G, T)
    assert supplier_edges("B", 180) == _edges(G, G, T, T)
    assert supplier_edges("B", 270) == _edges(G, T, T, G)


def test_equal_edge_pattern_does_not_make_rotated_board_geometry_equal():
    assert supplier_edges("A", 270) == supplier_edges("B", 0)
    assert orientation_for_rotation(270) != orientation_for_rotation(0)


def test_supplier_rotation_rejects_non_quarter_turns():
    try:
        supplier_edges("A", 45)
    except ValueError as exc:
        assert "0/90/180/270" in str(exc)
    else:
        raise AssertionError("45 degree supplier rotation must be rejected")
