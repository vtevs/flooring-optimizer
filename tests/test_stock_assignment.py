"""Strict supplier stock assignment across placement and source cuts."""

from shapely.geometry import Polygon

from floorplan.models import (
    BoardConfig, CuttingGroup, CuttingPiece, LayoutResult,
    LayoutStatistics, Pattern, PlacedBoard,
)
from floorplan.stock_assignment import (
    _adjacencies, _maximum_compatible_pairs, _root_layouts,
    assign_supplier_stock, placement_states, verify_recorded_supplier_stock,
)


def _piece(label, source_y, length):
    return CuttingPiece(
        label=label,
        length=length,
        width=20,
        source_x=0,
        source_y=source_y,
        source_width=20,
        source_length=length,
    )


def _group(source_id, piece, parent="", root=""):
    return CuttingGroup(
        source_id=source_id,
        pieces=[piece],
        total_length=100,
        used_length=piece.length,
        waste_length=0,
        parent_source_id=parent,
        total_width=20,
        root_source_id=root or source_id,
    )


def test_placement_states_respect_long_and_short_edge_orientation():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    full_piece = _piece("1", 0, 100)
    vertical = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100,
        label="1", source_id="源1",
    )
    horizontal = PlacedBoard(
        x=50, y=10, rotation=0, length=100, width=20,
        label="1", source_id="源1",
    )

    vertical_states = placement_states(vertical, full_piece, board)
    horizontal_states = placement_states(horizontal, full_piece, board)

    assert {state.rotation for state in vertical_states} == {0, 180}
    assert {state.rotation for state in horizontal_states} == {90, 270}
    assert {state.stock_class for state in vertical_states} == {"A", "B"}
    assert {state.stock_class for state in horizontal_states} == {"A", "B"}


def test_same_source_pieces_share_stock_class_and_keep_real_cut_sides():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    lower = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100, is_cut=True,
        cut_polygon=[(0, 0), (20, 0), (20, 30), (0, 30), (0, 0)],
        label="1", source_id="源1",
    )
    upper = PlacedBoard(
        x=110, y=50, rotation=0, length=20, width=100, is_cut=True,
        cut_polygon=[(100, 75), (120, 75), (120, 100), (100, 100), (100, 75)],
        label="2", source_id="源1-L2",
    )
    result = LayoutResult(
        boards=[lower, upper],
        statistics=LayoutStatistics(cutting_groups=[
            _group("源1", _piece("1", 0, 30)),
            _group("源1-L2", _piece("2", 75, 25), parent="源1", root="源1"),
        ]),
        pattern=Pattern.L_TRIPLE,
    )

    errors = assign_supplier_stock(result, board, board_gap=0)

    assert errors == []
    assert lower.stock_class == upper.stock_class
    assert lower.source_rotation in {0, 180}
    assert upper.source_rotation in {0, 180}
    assert lower.display_edges.top.value == "cut"
    assert upper.display_edges.bottom.value == "cut"


def test_source_cut_edges_cannot_be_assigned_to_two_room_cut_sides():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    impossible = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100, is_cut=True,
        cut_polygon=[(0, 20), (20, 20), (20, 80), (0, 80), (0, 20)],
        label="1", source_id="源1",
    )
    result = LayoutResult(
        boards=[impossible],
        statistics=LayoutStatistics(cutting_groups=[
            _group("源1", _piece("1", 0, 60)),
        ]),
        pattern=Pattern.L_TRIPLE,
    )

    errors = assign_supplier_stock(result, board, board_gap=0)

    assert any("源板切割边无法对应铺装裁切边" in error for error in errors)


def test_source_boundary_inheritance_does_not_allow_submillimeter_gap():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    piece = CuttingPiece(
        label="1", length=99.75, width=20,
        source_x=0, source_y=0.25,
        source_width=20, source_length=99.75,
    )
    placed = PlacedBoard(
        x=10, y=49.875, rotation=0, length=20, width=99.75,
        label="1", source_id="源1",
    )

    assert placement_states(placed, piece, board) == []


def test_source_layout_requires_full_configured_kerf():
    board = BoardConfig(length=100, width=20)
    pieces = {
        "1": _piece("1", 0, 49.25),
        "2": _piece("2", 50.75, 49.25),
    }

    assert _root_layouts(["1", "2"], pieces, board, kerf=2) == []


def test_non_rectangular_room_cut_records_real_source_polygon():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    placed = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100, is_cut=True,
        cut_polygon=[
            (0, 0), (20, 0), (20, 30), (10, 30),
            (10, 60), (0, 60), (0, 0),
        ],
        label="1", source_id="源1",
    )
    result = LayoutResult(
        boards=[placed],
        statistics=LayoutStatistics(cutting_groups=[
            _group("源1", _piece("1", 0, 60)),
        ]),
        pattern=Pattern.L_TRIPLE,
    )

    errors = assign_supplier_stock(result, board)

    piece = result.statistics.cutting_groups[0].pieces[0]
    assert errors == []
    assert piece.source_polygon
    assert Polygon(piece.source_polygon).area == 900
    assert verify_recorded_supplier_stock(result, board)[0] == []


def test_adjacent_supplier_boards_are_assigned_opposite_tongue_and_groove():
    board = BoardConfig(length=100, width=20,
                        stock_class_policy="supplier-ab-vertical")
    left = PlacedBoard(x=50, y=10, rotation=0, length=100, width=20,
                       label="1", source_id="源1")
    right = PlacedBoard(x=150, y=10, rotation=0, length=100, width=20,
                        label="2", source_id="源2")
    result = LayoutResult(
        boards=[left, right],
        statistics=LayoutStatistics(cutting_groups=[
            _group("源1", _piece("1", 0, 100)),
            _group("源2", _piece("2", 0, 100)),
        ]),
        pattern=Pattern.L_TRIPLE,
    )

    errors = assign_supplier_stock(result, board, board_gap=0)

    assert errors == []
    assert left.display_edges.right != right.display_edges.left


def test_matching_local_coordinates_in_different_rooms_are_not_neighbors():
    first = PlacedBoard(x=50, y=10, rotation=0, length=100, width=20,
                        label="1", source_id="源1")
    second = PlacedBoard(x=150, y=10, rotation=0, length=100, width=20,
                         label="2", source_id="源2")
    first._room_key = "room-a"
    second._room_key = "room-b"

    assert _adjacencies([first, second], gap=0) == []


def test_maximum_source_pairing_beats_order_dependent_greedy_choice():
    labels = ["1", "2", "3", "4"]
    compatible = {
        frozenset(("1", "2")),
        frozenset(("2", "3")),
        frozenset(("3", "4")),
    }

    pairs = _maximum_compatible_pairs(
        labels,
        lambda left, right: frozenset((left, right)) in compatible,
    )

    assert {frozenset(pair) for pair in pairs} == {
        frozenset(("1", "2")),
        frozenset(("3", "4")),
    }
