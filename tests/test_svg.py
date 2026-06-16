"""测试 SVG 渲染器"""
import re

from floorplan.models import (
    BoardConfig, Config, EdgeConfig, InstallationConfig, LayoutResult,
    LayoutStatistics, MultiRoomResult, OutputConfig, Pattern, PlacedBoard,
    RoomSpec,
)
from floorplan.svg.renderer import render_multi


def test_render_multi_cut_polygon_uses_room_local_y_transform(tmp_path):
    board = BoardConfig(length=40, width=20, thickness=18)
    room = RoomSpec(name="A", width=100, length=100)
    placed = PlacedBoard(
        x=50, y=50, rotation=0, length=40, width=20, is_cut=True,
        cut_polygon=[(30, 40), (70, 40), (70, 50), (30, 50), (30, 40)],
        label="1", source_id="源1",
    )
    layout = LayoutResult(
        boards=[placed],
        statistics=LayoutStatistics(total_boards=1, full_boards=0, cut_boards=1),
        pattern=Pattern.L_TRIPLE,
    )
    result = MultiRoomResult(room_results=[(room, layout)], total_boards=1)
    config = Config(
        rooms=[room],
        board=board,
        installation=InstallationConfig(pattern=Pattern.L_TRIPLE),
        edges=EdgeConfig(expansion_gap=0),
        output=OutputConfig(file="floor_plan.svg"),
    )

    out = tmp_path / "floor_plan.svg"
    render_multi(result, config, out)

    svg = out.read_text(encoding="utf-8")
    match = re.search(r'<polygon points="([^"]+)" class="cut-used"/?>', svg)
    assert match, svg

    points = [tuple(map(float, p.split(","))) for p in match.group(1).split()]
    y_values = {round(y, 1) for _, y in points}

    assert y_values == {400.0, 480.0}


def test_render_multi_draws_obstacles_with_cross(tmp_path):
    from floorplan.models import ObstacleConfig

    board = BoardConfig(length=40, width=20, thickness=18)
    room = RoomSpec(
        name="A", width=100, length=100,
        obstacles=[ObstacleConfig(name="cabinet", type="rectangle", x=10, y=60, width=30, length=20)],
    )
    layout = LayoutResult(
        boards=[],
        statistics=LayoutStatistics(total_boards=0, full_boards=0, cut_boards=0),
        pattern=Pattern.L_TRIPLE,
    )
    result = MultiRoomResult(room_results=[(room, layout)], total_boards=0)
    config = Config(
        rooms=[room], board=board,
        installation=InstallationConfig(pattern=Pattern.L_TRIPLE),
        edges=EdgeConfig(expansion_gap=0),
        output=OutputConfig(file="floor_plan.svg"),
    )

    out = tmp_path / "floor_plan.svg"
    render_multi(result, config, out)

    svg = out.read_text(encoding="utf-8")
    assert 'class="obstacle"' in svg
    assert svg.count('class="ob-x"') == 2
