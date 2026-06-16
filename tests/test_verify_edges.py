"""测试公母榫邻边校验"""

from floorplan.models import (
    BoardConfig, Config, EdgeConfig, InstallationConfig, LayoutResult,
    LayoutStatistics, Pattern, PlacedBoard,
)
from floorplan.verify import _verify_edges


def _config(gap=1):
    return Config(
        board=BoardConfig(length=100, width=20),
        installation=InstallationConfig(pattern=Pattern.ALIGNED),
        edges=EdgeConfig(expansion_gap=0, board_gap=gap),
    )


def test_adjacent_uncut_boards_can_be_oriented_to_match_tongue_and_groove():
    b1 = PlacedBoard(x=50, y=10, rotation=0, length=100, width=20, label="1", source_id="源1")
    b2 = PlacedBoard(x=151, y=10, rotation=0, length=100, width=20, label="2", source_id="源2")
    result = LayoutResult(
        boards=[b1, b2],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.ALIGNED,
    )

    assert _verify_edges(result, _config()) == []


def test_cut_edge_between_neighbors_is_rejected():
    b1 = PlacedBoard(
        x=50, y=10, rotation=0, length=100, width=20, is_cut=True,
        cut_polygon=[(0, 0), (90, 0), (90, 20), (0, 20), (0, 0)],
        label="1", source_id="源1",
    )
    b2 = PlacedBoard(x=141, y=10, rotation=0, length=100, width=20, label="2", source_id="源2")
    result = LayoutResult(
        boards=[b1, b2],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.ALIGNED,
    )

    errors = _verify_edges(result, _config())

    assert any("内部邻边出现切割边" in e for e in errors)


def test_perpendicular_three_l_neighbors_can_be_oriented_to_match():
    vertical = PlacedBoard(x=10, y=50, rotation=0, length=20, width=100, label="1", source_id="源1")
    horizontal = PlacedBoard(x=61, y=10, rotation=0, length=100, width=20, label="2", source_id="源2")
    result = LayoutResult(
        boards=[vertical, horizontal],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.L_TRIPLE,
    )

    assert _verify_edges(result, _config()) == []


def test_room_a_local_conflict_passes_with_confirmed_edge_orientation():
    b1 = PlacedBoard(
        x=-203.5, y=2433.666666666667, rotation=0, length=600, width=88,
        is_cut=True,
        cut_polygon=[
            (10.0, 2389.666666666667), (96.5, 2389.666666666667),
            (96.5, 2477.666666666667), (10.0, 2477.666666666667),
            (10.0, 2389.666666666667),
        ],
        label="1", source_id="源1",
    )
    b23 = PlacedBoard(
        x=52.0, y=2089.6666666666665, rotation=0, length=88, width=600,
        is_cut=True,
        cut_polygon=[
            (10.0, 1789.6666666666665), (96.0, 1789.6666666666665),
            (96.0, 2389.6666666666665), (10.0, 2389.6666666666665),
            (10.0, 1789.6666666666665),
        ],
        label="23", source_id="源23",
    )
    b27 = PlacedBoard(
        x=140.5, y=2355.1666666666665, rotation=0, length=88, width=600,
        label="27", source_id="源27",
    )
    result = LayoutResult(
        boards=[b1, b23, b27],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.L_TRIPLE,
    )

    assert _verify_edges(result, _config(gap=0.5)) == []
