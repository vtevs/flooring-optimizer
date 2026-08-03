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
