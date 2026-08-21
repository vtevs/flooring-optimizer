"""测试公母榫邻边校验"""

from floorplan.models import (
    BoardConfig, Config, CuttingGroup, CuttingPiece, EdgeConfig,
    InstallationConfig, LayoutResult, LayoutStatistics, MultiRoomResult,
    ObstacleConfig, Pattern, PlacedBoard, RoomSpec,
)
from floorplan.verify import (
    _verify_coverage, _verify_edges, _verify_supplier_sources,
)
from floorplan.stock_assignment import assign_supplier_stock


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


def _supplier_same_source_result():
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
    groups = [
        CuttingGroup(
            source_id="源1",
            pieces=[CuttingPiece(
                label="1", length=30, width=20,
                source_x=0, source_y=0,
                source_width=20, source_length=30,
            )],
            total_length=100, used_length=30, waste_length=0,
            total_width=20, root_source_id="源1",
        ),
        CuttingGroup(
            source_id="源1-L2", parent_source_id="源1",
            pieces=[CuttingPiece(
                label="2", length=25, width=20,
                source_x=0, source_y=75,
                source_width=20, source_length=25,
            )],
            total_length=100, used_length=25, waste_length=0,
            total_width=20, root_source_id="源1",
        ),
    ]
    return LayoutResult(
        boards=[lower, upper],
        statistics=LayoutStatistics(cutting_groups=groups),
        pattern=Pattern.L_TRIPLE,
    )


def _supplier_config():
    return Config(
        board=BoardConfig(
            length=100, width=20,
            stock_class_policy="supplier-ab-vertical",
        ),
        installation=InstallationConfig(pattern=Pattern.L_TRIPLE),
        edges=EdgeConfig(expansion_gap=0, board_gap=0),
    )


def test_supplier_verifier_rejects_tampered_same_source_stock_class():
    result = _supplier_same_source_result()
    config = _supplier_config()
    assert assign_supplier_stock(result, config.board) == []
    result.boards[1].stock_class = (
        "B" if result.boards[0].stock_class == "A" else "A"
    )

    errors = _verify_edges(result, config)

    assert any("同源板型不一致" in error for error in errors)


def test_supplier_verifier_rejects_tampered_rotation_edges():
    result = _supplier_same_source_result()
    config = _supplier_config()
    assert assign_supplier_stock(result, config.board) == []
    result.boards[0].source_rotation = (
        result.boards[0].source_rotation + 180
    ) % 360

    errors = _verify_edges(result, config)

    assert any("源板切割继承与铺装边不一致" in error for error in errors)


def test_supplier_source_verifier_checks_shared_board_across_rooms():
    result = _supplier_same_source_result()
    first_group, second_group = result.statistics.cutting_groups
    second_group.pieces[0].source_y = 20
    first_room = LayoutResult(
        boards=[result.boards[0]],
        statistics=LayoutStatistics(cutting_groups=[first_group]),
        pattern=Pattern.L_TRIPLE,
    )
    second_room = LayoutResult(
        boards=[result.boards[1]],
        statistics=LayoutStatistics(cutting_groups=[second_group]),
        pattern=Pattern.L_TRIPLE,
    )
    multi = MultiRoomResult(room_results=[
        (RoomSpec(name="房间A"), first_room),
        (RoomSpec(name="房间B"), second_room),
    ])

    errors = _verify_supplier_sources(multi, _supplier_config())

    assert any("位1与位2在源板中重叠" in error for error in errors)


def test_supplier_source_verifier_rejects_cross_room_board_class_tampering():
    result = _supplier_same_source_result()
    config = _supplier_config()
    assert assign_supplier_stock(result, config.board) == []
    first_group, second_group = result.statistics.cutting_groups
    first_room = LayoutResult(
        boards=[result.boards[0]],
        statistics=LayoutStatistics(cutting_groups=[first_group]),
        pattern=Pattern.L_TRIPLE,
    )
    second_room = LayoutResult(
        boards=[result.boards[1]],
        statistics=LayoutStatistics(cutting_groups=[second_group]),
        pattern=Pattern.L_TRIPLE,
    )
    second_room.boards[0].stock_class = (
        "B" if first_room.boards[0].stock_class == "A" else "A"
    )
    multi = MultiRoomResult(room_results=[
        (RoomSpec(name="房间A"), first_room),
        (RoomSpec(name="房间B"), second_room),
    ])

    errors = _verify_supplier_sources(multi, config)

    assert any("同源板 A/B 类型不一致" in error for error in errors)


def test_coverage_rejects_even_small_overlap_with_obstacle():
    room = RoomSpec(
        name="带柜房间", type="rectangle", width=1000, length=1000,
        obstacles=[ObstacleConfig(
            name="柜子", type="rectangle",
            x=0, y=600, width=400, length=400,
        )],
    )
    config = Config(
        rooms=[room], board=BoardConfig(length=600, width=20),
        installation=InstallationConfig(pattern=Pattern.L_TRIPLE),
        edges=EdgeConfig(expansion_gap=0, board_gap=0),
    )
    result = LayoutResult(
        boards=[PlacedBoard(
            x=690, y=600, rotation=0, length=600, width=20,
            label="1", source_id="源1",
        )],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.L_TRIPLE,
    )

    errors = _verify_coverage(
        result, config, room_label=room.name,
        room_width=room.width, room_length=room.length,
    )

    assert any("进入伸缩缝或不可铺区域" in error for error in errors)
