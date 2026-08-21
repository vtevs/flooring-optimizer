"""测试命令行输出路径处理"""

from pathlib import Path

from floorplan.cli import (
    _format_supplier_source_plan,
    _multi_room_plan_path,
    _supplier_room_summary,
    _supplier_stock_summary,
)
from floorplan.models import (
    BoardConfig, BoardEdges, Config, CuttingGroup, CuttingPiece, EdgeType,
    InstallationConfig, LayoutResult, LayoutStatistics, MultiRoomResult,
    OutputConfig, Pattern, PlacedBoard, RoomSpec,
)


def test_multi_room_html_output_replaces_svg_suffix(tmp_path):
    output = OutputConfig(file="floor_plan.svg")

    assert _multi_room_plan_path(tmp_path, output) == tmp_path / "floor_plan.html"


def test_multi_room_html_output_keeps_html_suffix(tmp_path):
    output = OutputConfig(file="custom.html")

    assert _multi_room_plan_path(Path(tmp_path), output) == tmp_path / "custom.html"


def test_supplier_stock_summary_reports_consumed_and_equal_mix_purchase():
    result = type("Result", (), {
        "stock_counts": {"A": 272, "B": 276},
        "total_boards": 548,
        "purchase_boards": 552,
    })()

    lines = _supplier_stock_summary(result)

    assert "A 型源板: 272" in lines[0]
    assert "B 型源板: 276" in lines[0]
    assert "实际消耗: 548" in lines[0]
    assert "按 1:1 配板采购: 552" in lines[1]


def test_supplier_cutting_plan_uses_final_source_coordinates():
    edges = BoardEdges(
        top=EdgeType.TONGUE, right=EdgeType.GROOVE,
        bottom=EdgeType.CUT, left=EdgeType.TONGUE,
    )
    board = PlacedBoard(
        x=10, y=15, rotation=0, length=20, width=30, label="1",
        source_id="源1", stock_class="A", source_rotation=90,
        display_edges=edges,
    )
    group = CuttingGroup(
        source_id="源1", root_source_id="源1", stock_class="A",
        pieces=[CuttingPiece(
            label="1", length=30, width=20,
            source_x=0, source_y=70, source_width=20, source_length=30,
        )],
        total_length=100, used_length=30, waste_length=68,
        total_width=20,
    )
    room_result = LayoutResult(
        boards=[board], statistics=LayoutStatistics(cutting_groups=[group]),
        pattern=Pattern.L_TRIPLE,
    )
    result = MultiRoomResult(room_results=[
        (RoomSpec(name="房间A"), room_result),
    ])
    config = Config(
        board=BoardConfig(
            length=100, width=20,
            stock_class_policy="supplier-ab-vertical",
        ),
        installation=InstallationConfig(pattern=Pattern.L_TRIPLE),
        kerf=2,
    )

    lines = _format_supplier_source_plan(result, config)
    text = "\n".join(lines)

    assert "[源1] A 型" in text
    assert "x=0, y=70, width=20, length=30mm" in text
    assert "铺装旋转=90°" in text
    assert "顶=T 右=G 底=C 左=T" in text
    assert "未铺入面积(含锯缝): 0.0014 m²" in text


def test_supplier_room_summary_separates_placements_from_source_boards():
    room_result = LayoutResult(
        boards=[
            PlacedBoard(x=0, y=0, rotation=0, length=100, width=20),
            PlacedBoard(x=0, y=0, rotation=0, length=100, width=20,
                        is_cut=True),
        ],
        statistics=LayoutStatistics(
            total_boards=1, full_boards=0, cut_boards=1,
        ),
        pattern=Pattern.L_TRIPLE,
    )

    line = _supplier_room_summary(room_result)

    assert "铺装片: 2（完整1 / 切割1）" in line
    assert "本房间计入源板: 1" in line
