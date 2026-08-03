"""Tests for the optional full-board-at-room-corner rule."""

from shapely.geometry import box

from floorplan.corner_rule import has_full_board_at_room_corner
from floorplan.geometry.room import build_room, compute_layout_area
from floorplan.multi_optimize import optimize_multi
from floorplan.optimize import optimize
from floorplan.models import (
    BoardConfig, EdgeConfig, InstallationConfig, LayoutResult,
    LayoutStatistics, Pattern, PlacedBoard, RoomSpec,
)


def _result(boards):
    return LayoutResult(
        boards=boards,
        statistics=LayoutStatistics(total_boards=len(boards)),
        pattern=Pattern.L_TRIPLE,
    )


def _board(x, y, length=100, width=20, is_cut=False):
    return PlacedBoard(
        x=x,
        y=y,
        rotation=0,
        length=length,
        width=width,
        is_cut=is_cut,
        label="1",
    )


def test_full_board_covering_room_corner_passes():
    room = box(0, 0, 300, 300)
    result = _result([_board(50, 10)])

    assert has_full_board_at_room_corner(result, room)


def test_cut_board_covering_room_corner_fails():
    room = box(0, 0, 300, 300)
    result = _result([_board(50, 10, is_cut=True)])

    assert not has_full_board_at_room_corner(result, room)


def test_full_board_away_from_corners_fails():
    room = box(0, 0, 300, 300)
    result = _result([_board(150, 150)])

    assert not has_full_board_at_room_corner(result, room)


def test_virtual_l_shape_bbox_corner_is_ignored():
    room = box(0, 0, 300, 200).union(box(0, 200, 100, 300))
    # The bbox top-right corner (300, 300) is not part of the L-shaped room.
    result = _result([_board(50, 10)])

    assert has_full_board_at_room_corner(result, room)


def test_single_room_optimizer_returns_layout_satisfying_corner_rule():
    room = box(0, 0, 300, 300)
    board = BoardConfig(length=100, width=20)

    result = optimize(
        room, board, Pattern.ALIGNED,
        require_full_board_at_room_corner=True,
    )

    assert has_full_board_at_room_corner(result, room)


def test_multi_room_optimizer_requires_each_room_to_satisfy_corner_rule():
    rooms = [
        RoomSpec(name="A", type="rectangle", width=300, length=300),
        RoomSpec(name="B", type="rectangle", width=320, length=300),
    ]
    board = BoardConfig(length=100, width=20)
    edges = EdgeConfig(expansion_gap=0, board_gap=0)
    installation = InstallationConfig(
        pattern=Pattern.ALIGNED,
        require_full_board_at_room_corner=True,
    )

    result = optimize_multi(rooms, board, edges, kerf=0, installation=installation)

    for room_spec, room_result in result.room_results:
        room_area = compute_layout_area(
            build_room(room_spec),
            edges.baseboard_width,
            edges.expansion_gap,
        )
        assert has_full_board_at_room_corner(room_result, room_area)


def test_multi_room_optimizer_can_fix_each_room_to_bottom_left_full_board():
    rooms = [
        RoomSpec(name="A", type="rectangle", width=300, length=300),
        RoomSpec(name="B", type="rectangle", width=320, length=300),
    ]
    board = BoardConfig(length=100, width=20)
    edges = EdgeConfig(expansion_gap=5, board_gap=0)
    installation = InstallationConfig(
        pattern=Pattern.ALIGNED,
        require_full_board_at_room_bottom_left=True,
    )

    result = optimize_multi(rooms, board, edges, kerf=0, installation=installation)

    for room_spec, room_result in result.room_results:
        room_area = compute_layout_area(
            build_room(room_spec),
            edges.baseboard_width,
            edges.expansion_gap,
        )
        minx, miny, _, _ = room_area.bounds
        assert room_result.start_offset == (minx, miny)
        assert has_full_board_at_room_corner(room_result, room_area)
