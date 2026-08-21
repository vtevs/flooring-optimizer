"""Tests for config-level wood/tile material behavior."""

from floorplan.layout.board_pool import BoardPool, PoolEntry
from floorplan.models import (
    BoardConfig, BoardEdges, Config, EdgeConfig, EdgeType,
    InstallationConfig, LayoutResult, LayoutStatistics, MaterialConfig,
    MaterialType, Pattern, PlacedBoard, RoomConfig,
)
from floorplan.verify import verify_layout


def _two_cut_neighbors_config(material_type):
    return Config(
        room=RoomConfig(type="rectangle", width=200, length=20),
        board=BoardConfig(length=100, width=20),
        installation=InstallationConfig(pattern=Pattern.ALIGNED),
        edges=EdgeConfig(expansion_gap=0, board_gap=0),
        material=MaterialConfig(type=material_type),
    )


def _two_cut_neighbors_result():
    left = PlacedBoard(
        x=50, y=10, rotation=0, length=100, width=20, is_cut=True,
        cut_polygon=[(0, 0), (90, 0), (90, 20), (0, 20), (0, 0)],
        label="1",
    )
    right = PlacedBoard(
        x=140, y=10, rotation=0, length=100, width=20, is_cut=False,
        label="2",
    )
    return LayoutResult(
        boards=[left, right],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.ALIGNED,
    )


def test_wood_material_rejects_internal_cut_edges():
    errors = verify_layout(
        _two_cut_neighbors_result(),
        _two_cut_neighbors_config(MaterialType.WOOD),
    )
    assert any("内部邻边出现切割边" in e for e in errors)


def test_tile_material_skips_tongue_groove_edge_proof():
    errors = verify_layout(
        _two_cut_neighbors_result(),
        _two_cut_neighbors_config(MaterialType.TILE),
    )
    assert not any("内部邻边出现切割边" in e for e in errors)
    assert not any("公母榫" in e for e in errors)


def test_tile_pool_reuse_ignores_edge_requirements():
    wood_pool = BoardPool(100, kerf=1, board_width=20, material_type=MaterialType.WOOD)
    tile_pool = BoardPool(100, kerf=1, board_width=20, material_type=MaterialType.TILE)
    mismatch_piece = BoardEdges(
        top=EdgeType.CUT,
        bottom=EdgeType.CUT,
        left=EdgeType.CUT,
        right=EdgeType.CUT,
    )
    required = BoardEdges(
        top=EdgeType.TONGUE,
        bottom=EdgeType.GROOVE,
        left=EdgeType.GROOVE,
        right=EdgeType.TONGUE,
    )

    wood_pool._pool.append(type("Entry", (), dict(length=80, width=None, source_id="源1", edges=mismatch_piece))())
    tile_pool._pool.append(type("Entry", (), dict(length=80, width=None, source_id="源1", edges=mismatch_piece))())

    assert wood_pool.take(60, "A", required_edges=required) is None
    assert tile_pool.take(60, "A", required_edges=required) is not None


def test_reused_length_piece_records_waste_after_kerf():
    pool = BoardPool(100, kerf=2, board_width=20, material_type=MaterialType.TILE)
    pool._pool.append(PoolEntry(80, "源1"))

    reuse_id = pool.take(60, "A")
    group = next(g for g in pool.cutting_groups if g["source_id"] == reuse_id)

    assert group["waste_length"] == 18


def test_board_pool_does_not_reuse_leftover_across_stock_classes():
    pool = BoardPool(100, kerf=0, board_width=20)

    first = pool.cut_new(40, "1", stock_class="A")
    second = pool.take_or_cut(40, "2", stock_class="B")
    third = pool.take_or_cut(30, "3", stock_class="A")

    groups = {g["source_id"]: g for g in pool.cutting_groups}
    assert first == "源1"
    assert second == "源2"
    assert groups[second]["parent_source_id"] == ""
    assert groups[second]["stock_class"] == "B"
    assert groups[third]["parent_source_id"].startswith("源1")
    assert groups[third]["stock_class"] == "A"
    assert pool.total_new_boards == 2


def test_length_reuse_uses_opposite_original_short_edge_only_once():
    pool = BoardPool(100, kerf=2, board_width=20)

    first_id = pool.cut_new(30, "1")
    second_id = pool.take(25, "2")
    third_id = pool.take(10, "3")

    groups = {g["source_id"]: g for g in pool.cutting_groups}
    first_piece = groups[first_id]["pieces"][0]
    second_piece = groups[second_id]["pieces"][0]

    assert (
        first_piece["source_x"], first_piece["source_y"],
        first_piece["source_width"], first_piece["source_length"],
    ) == (0, 0, 20, 30)
    assert (
        second_piece["source_x"], second_piece["source_y"],
        second_piece["source_width"], second_piece["source_length"],
    ) == (0, 75, 20, 25)
    assert groups[second_id]["root_source_id"] == first_id
    assert third_id is None


def test_combined_cut_records_non_overlapping_source_rectangle():
    pool = BoardPool(100, kerf=2, board_width=20)

    source_id = pool.cut_new_combined(40, 8, "1")
    group = next(g for g in pool.cutting_groups if g["source_id"] == source_id)
    piece = group["pieces"][0]

    assert (
        piece["source_x"], piece["source_y"],
        piece["source_width"], piece["source_length"],
    ) == (0, 0, 8, 40)
    assert group["root_source_id"] == source_id


def test_length_pool_never_reuses_a_piece_shorter_than_required():
    pool = BoardPool(100, kerf=1.5, board_width=20)
    pool._pool.append(PoolEntry(98.5, "源1"))

    assert pool.take(100, "1") is None


def test_width_pool_never_reuses_a_piece_narrower_than_required():
    pool = BoardPool(100, kerf=1.5, board_width=20)
    pool._pool.append(PoolEntry(100, "源1", width=18.5))

    assert pool.try_take_width_reduced(20, "1") is None


def test_coverage_verification_allows_configured_board_gap():
    config = Config(
        room=RoomConfig(type="rectangle", width=202, length=20),
        board=BoardConfig(length=100, width=20),
        installation=InstallationConfig(pattern=Pattern.ALIGNED),
        edges=EdgeConfig(expansion_gap=0, board_gap=2),
        material=MaterialConfig(type=MaterialType.TILE),
    )
    result = LayoutResult(
        boards=[
            PlacedBoard(x=50, y=10, rotation=0, length=100, width=20, label="1"),
            PlacedBoard(x=152, y=10, rotation=0, length=100, width=20, label="2"),
        ],
        statistics=LayoutStatistics(cutting_groups=[]),
        pattern=Pattern.ALIGNED,
    )

    errors = verify_layout(result, config)

    assert not any("覆盖率不足" in e for e in errors)
    assert not any("可铺区域未完全覆盖" in e for e in errors)
