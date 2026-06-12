"""测试排样引擎"""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shapely.geometry import Polygon, box

from floorplan.layout import ENGINES
from floorplan.layout.aligned import AlignedEngine
from floorplan.layout.staggered import StaggeredEngine
from floorplan.layout.five_board import FiveBoardSquareEngine
from floorplan.layout.herringbone import HerringboneEngine
from floorplan.models import BoardConfig, Pattern


# 测试用例：5m × 6m 矩形房间，常用地板规格
ROOM_RECT = box(0, 0, 5000, 6000)
BOARD = BoardConfig(length=1210, width=198)
BOARD_SQUARE = BoardConfig(length=440, width=88)  # 5×88=440


class TestAlignedEngine:
    """对拼引擎"""

    def test_returns_result(self):
        engine = AlignedEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0)
        assert result is not None
        assert len(result.boards) > 0

    def test_utilization_under_100(self):
        engine = AlignedEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0)
        assert 0.9 < result.statistics.utilization <= 1.02  # 容忍浮点/边界效应

    def test_covers_most_of_room(self):
        """检查覆盖率 > 95%"""
        engine = AlignedEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0)
        # 计算实际覆盖面积
        board_polys = []
        for b in result.boards:
            bw, bl = b.width, b.length
            bx, by = b.x - bl/2, b.y - bw/2
            bp = box(bx, by, bx + bl, by + bw)
            clipped = ROOM_RECT.intersection(bp)
            if not clipped.is_empty:
                board_polys.append(clipped)

        from shapely.ops import unary_union
        covered = unary_union(board_polys)
        coverage = covered.area / ROOM_RECT.area
        assert coverage > 0.95, f"Coverage too low: {coverage*100:.1f}%"

    def test_direction_90(self):
        """方向 90°"""
        engine = AlignedEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=90)
        assert len(result.boards) > 0
        assert result.statistics.utilization <= 1.02

    def test_board_count_reasonable(self):
        """板数在合理范围内（理论最少 ~125，允许 ±20%）"""
        engine = AlignedEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0)
        min_boards = ROOM_RECT.area / (BOARD.length * BOARD.width)
        assert min_boards * 0.8 <= result.statistics.total_boards <= min_boards * 1.3

    def test_small_room(self):
        """极小房间"""
        tiny = box(0, 0, 2000, 2000)
        engine = AlignedEngine()
        result = engine.layout(tiny, BOARD, start_offset=(0, 0), direction=0)
        assert len(result.boards) > 0
        assert result.statistics.utilization <= 1.02


class TestStaggeredEngine:
    """错缝引擎"""

    def test_returns_result(self):
        engine = StaggeredEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0,
                               stagger_ratio=0.33)
        assert len(result.boards) > 0

    def test_utilization_under_100(self):
        engine = StaggeredEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0,
                               stagger_ratio=0.33)
        assert result.statistics.utilization <= 1.02

    def test_coverage_above_95(self):
        engine = StaggeredEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0,
                               stagger_ratio=0.33)
        board_polys = []
        for b in result.boards:
            bw, bl = b.width, b.length
            bx, by = b.x - bl/2, b.y - bw/2
            bp = box(bx, by, bx + bl, by + bw)
            clipped = ROOM_RECT.intersection(bp)
            if not clipped.is_empty:
                board_polys.append(clipped)
        from shapely.ops import unary_union
        covered = unary_union(board_polys)
        coverage = covered.area / ROOM_RECT.area
        assert coverage > 0.95, f"Coverage: {coverage*100:.1f}%"

    def test_half_stagger(self):
        """对半错缝"""
        engine = StaggeredEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0,
                               stagger_ratio=0.5)
        assert result.statistics.utilization <= 1.02

    def test_different_stagger_ratios(self):
        """不同错缝比例都应有效"""
        for ratio in [0.25, 0.33, 0.5, 0.66]:
            engine = StaggeredEngine()
            result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=0,
                                   stagger_ratio=ratio)
            assert result.statistics.utilization <= 1.02, f"ratio={ratio} util={result.statistics.utilization}"


class TestFiveBoardSquare:
    """5拼方砖引擎"""

    def test_returns_result(self):
        engine = FiveBoardSquareEngine()
        result = engine.layout(ROOM_RECT, BOARD_SQUARE, start_offset=(0, 0), direction=0)
        assert len(result.boards) > 0

    def test_utilization_under_100(self):
        engine = FiveBoardSquareEngine()
        result = engine.layout(ROOM_RECT, BOARD_SQUARE, start_offset=(0, 0), direction=0)
        assert result.statistics.utilization <= 1.02

    def test_square_board_matches(self):
        """5 × 88 = 440 方砖，验证板尺寸合适"""
        assert BOARD_SQUARE.length == 440
        assert BOARD_SQUARE.width == 88
        assert BOARD_SQUARE.length == BOARD_SQUARE.width * 5


class TestHerringboneEngine:
    """人字拼引擎（实验性）"""

    def test_returns_result(self):
        engine = HerringboneEngine()
        result = engine.layout(ROOM_RECT, BOARD, start_offset=(0, 0), direction=45)
        assert len(result.boards) > 0
        # 不严格检查利用率（实验性实现）


class TestLShapedRoom:
    """L 形房间的排样测试"""

    @pytest.fixture
    def l_room(self):
        """6m×8m L形房间，3m×3m 左上缺口"""
        outer = box(0, 0, 6000, 8000)
        hole = box(0, 5000, 3000, 8000)
        return outer.difference(hole)

    def test_aligned_l_shaped(self, l_room):
        engine = AlignedEngine()
        result = engine.layout(l_room, BOARD, start_offset=(0, 0), direction=0)
        assert len(result.boards) > 0
        assert result.statistics.utilization <= 1.02

    def test_staggered_l_shaped(self, l_room):
        engine = StaggeredEngine()
        result = engine.layout(l_room, BOARD, start_offset=(0, 0), direction=0,
                               stagger_ratio=0.33)
        assert len(result.boards) > 0
        assert result.statistics.utilization <= 1.02

    def test_five_board_l_shaped(self, l_room):
        engine = FiveBoardSquareEngine()
        result = engine.layout(l_room, BOARD_SQUARE, start_offset=(0, 0), direction=0)
        assert len(result.boards) > 0
        assert result.statistics.utilization <= 1.02


class TestEngineRegistration:
    """验证引擎注册表"""

    def test_all_patterns_registered(self):
        for pattern in Pattern:
            assert pattern in ENGINES, f"{pattern} not registered"
            assert issubclass(ENGINES[pattern], AlignedEngine.__base__)
