"""测试交互式 HTML 渲染器"""

from types import SimpleNamespace

from floorplan.svg.html_renderer import _build_html
from floorplan.svg.html_renderer import _board_svg
from floorplan.svg.html_renderer import _reconstruct_source_layouts
from floorplan.models import (
    BoardConfig, Config, CuttingGroup, CuttingPiece, EdgeConfig, LayoutResult,
    LayoutStatistics, MultiRoomResult, Pattern, PlacedBoard,
)
from floorplan.stock_assignment import assign_supplier_stock


def test_source_diagram_piece_rect_is_self_closed():
    html = _build_html(
        cw=100,
        ch=100,
        rooms_svg=[],
        all_boards=[],
        stats=[],
        total_boards=0,
        total_full=0,
        total_cut=0,
        source_layouts={},
    )

    assert "+ '/>';" in html
    assert "+ 'height=\"' + ph.toFixed(1) + '\" class=\"' + fillCls + '\"' + hl + '>';" not in html


def test_board_svg_marks_stock_class_visually():
    board = PlacedBoard(
        x=50, y=10, rotation=0, length=80, width=20,
        label="1", source_id="源1",
    )
    board._root_source = "源1"
    board._stock_class = "A"

    svg = _board_svg(board, scale=1, room_h=40, idx=0)

    assert 'class="board stock-A"' in svg
    assert 'data-stock="A"' in svg
    assert '>A</text>' in svg


def test_cut_board_stock_badge_uses_point_inside_used_polygon():
    board = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100,
        is_cut=True,
        cut_polygon=[(0, 0), (20, 0), (20, 30), (0, 30), (0, 0)],
        label="1", source_id="源1",
    )
    board._root_source = "源1"
    board._stock_class = "A"

    svg = _board_svg(board, scale=1, room_h=100, idx=0)

    assert 'cx="10.0" cy="85.0"' in svg


def test_html_includes_stock_class_in_modal_and_legend():
    html = _build_html(
        cw=100,
        ch=100,
        rooms_svg=[],
        all_boards=[{
            "label": "1",
            "source": "源1",
            "root": "源1",
            "room": "A",
            "is_cut": False,
            "len": 80,
            "wid": 20,
            "stock_class": "B",
            "edges": None,
        }],
        stats=[],
        total_boards=1,
        total_full=1,
        total_cut=0,
        source_layouts={},
    )

    assert "<th>板型</th>" in html
    assert "b.stock_class" in html
    assert "A 型板" in html
    assert "B 型板" in html


def test_source_layout_uses_absolute_two_dimensional_piece_rectangles():
    pieces = [
        CuttingPiece(
            label="1", length=30, width=20,
            source_x=0, source_y=0,
            source_width=20, source_length=30,
            source_polygon=[
                (0, 0), (20, 0), (20, 15), (10, 15),
                (10, 30), (0, 30), (0, 0),
            ],
        ),
        CuttingPiece(
            label="2", length=25, width=20,
            source_x=0, source_y=75,
            source_width=20, source_length=25,
        ),
    ]
    groups = [
        CuttingGroup(
            source_id="源1", pieces=[pieces[0]],
            total_length=100, used_length=30, waste_length=0,
            total_width=20, root_source_id="源1", stock_class="A",
        ),
        CuttingGroup(
            source_id="源1-L2", parent_source_id="源1", pieces=[pieces[1]],
            total_length=100, used_length=25, waste_length=0,
            total_width=20, root_source_id="源1", stock_class="A",
        ),
    ]
    result = LayoutResult(
        boards=[],
        statistics=LayoutStatistics(cutting_groups=groups),
        pattern=Pattern.L_TRIPLE,
    )
    multi = MultiRoomResult(room_results=[(SimpleNamespace(name="R"), result)])
    config = SimpleNamespace(board=BoardConfig(length=100, width=20), kerf=2)

    layouts = _reconstruct_source_layouts(multi, config, {}, lambda sid: "源1")

    assert layouts["源1"]["stock_class"] == "A"
    assert layouts["源1"]["valid"] is True
    assert layouts["源1"]["pieces"][0]["x"] == 0
    assert layouts["源1"]["pieces"][0]["y"] == 0
    assert len(layouts["源1"]["pieces"][0]["polygon"]) == 7
    assert layouts["源1"]["pieces"][0]["shape_cut"] is True
    assert layouts["源1"]["pieces"][1]["x"] == 0
    assert layouts["源1"]["pieces"][1]["y"] == 75


def test_html_source_diagram_shows_validation_and_recorded_rotation():
    html = _build_html(
        cw=100,
        ch=100,
        rooms_svg=[],
        all_boards=[{
            "label": "1", "source": "源1", "root": "源1", "room": "A",
            "is_cut": True, "len": 30, "wid": 20,
            "stock_class": "A", "source_rotation": 180, "edges": None,
        }],
        stats=[], total_boards=1, total_full=0, total_cut=1,
        source_layouts={
            "源1": {
                "length": 100, "width": 20, "stock_class": "A",
                "valid": True, "errors": [],
                "pieces": [{
                    "label": "1", "source": "源1",
                    "x": 0, "y": 0, "len": 30, "wid": 20,
                }],
            },
        },
    )

    assert "源板切割校验：" in html
    assert "铺装旋转" in html
    assert "b.source_rotation" in html
    assert "p.x" in html
    assert "p.y" in html
    assert "p.polygon" in html


def test_source_layout_validation_rejects_tampered_recorded_rotation():
    placed = PlacedBoard(
        x=10, y=50, rotation=0, length=20, width=100,
        is_cut=True,
        cut_polygon=[(0, 0), (20, 0), (20, 30), (0, 30), (0, 0)],
        label="1", source_id="源1",
    )
    group = CuttingGroup(
        source_id="源1", root_source_id="源1",
        pieces=[CuttingPiece(
            label="1", length=30, width=20,
            source_x=0, source_y=0,
            source_width=20, source_length=30,
        )],
        total_length=100, used_length=30, waste_length=68,
        total_width=20,
    )
    result = LayoutResult(
        boards=[placed],
        statistics=LayoutStatistics(cutting_groups=[group]),
        pattern=Pattern.L_TRIPLE,
    )
    board = BoardConfig(
        length=100, width=20,
        stock_class_policy="supplier-ab-vertical",
    )
    assert assign_supplier_stock(result, board, kerf=2) == []
    placed.source_rotation = (placed.source_rotation + 180) % 360
    multi = MultiRoomResult(room_results=[
        (SimpleNamespace(name="R"), result),
    ])
    config = Config(board=board, edges=EdgeConfig(), kerf=2)

    layouts = _reconstruct_source_layouts(multi, config, {}, lambda sid: "源1")

    assert layouts["源1"]["valid"] is False
    assert any("旋转或四边继承不一致" in error
               for error in layouts["源1"]["errors"])
