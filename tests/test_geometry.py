"""测试房间几何模型"""
import pytest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from shapely.geometry import Polygon

from floorplan.geometry.room import build_room, compute_layout_area
from floorplan.models import RoomConfig, RoomSpec, ObstacleConfig, NotchConfig, NotchPosition


class TestBuildRoom:
    """测试房间多边形构建"""

    def test_rectangle(self):
        """矩形房间"""
        cfg = RoomConfig(type="rectangle", width=5000, length=6000)
        room = build_room(cfg)
        assert isinstance(room, Polygon)
        assert room.geom_type == "Polygon"
        assert abs(room.area - 30_000_000) < 1  # 5000 × 6000 = 30M mm²

    def test_l_shaped_top_left(self):
        """L 形 - 左上缺口"""
        cfg = RoomConfig(
            type="l-shaped", width=6000, length=8000,
            notch=NotchConfig(width=3000, depth=3000, position=NotchPosition.TOP_LEFT),
        )
        room = build_room(cfg)
        # 面积 = 6000×8000 - 3000×3000 = 48M - 9M = 39M
        assert abs(room.area - 39_000_000) < 1

    def test_l_shaped_bottom_right(self):
        """L 形 - 右下缺口"""
        cfg = RoomConfig(
            type="l-shaped", width=5000, length=5000,
            notch=NotchConfig(width=2000, depth=2000, position=NotchPosition.BOTTOM_RIGHT),
        )
        room = build_room(cfg)
        # 面积 = 5000² - 2000² = 21M
        assert abs(room.area - 21_000_000) < 1

    def test_l_shaped_top_right(self):
        """L 形 - 右上缺口"""
        cfg = RoomConfig(
            type="l-shaped", width=4000, length=6000,
            notch=NotchConfig(width=2000, depth=2000, position=NotchPosition.TOP_RIGHT),
        )
        room = build_room(cfg)
        assert abs(room.area - 20_000_000) < 1  # 24M - 4M = 20M

    def test_l_shaped_bottom_left(self):
        """L 形 - 左下缺口"""
        cfg = RoomConfig(
            type="l-shaped", width=4000, length=6000,
            notch=NotchConfig(width=1500, depth=2000, position=NotchPosition.BOTTOM_LEFT),
        )
        room = build_room(cfg)
        assert abs(room.area - 21_000_000) < 1  # 24M - 3M = 21M

    def test_rectangle_with_null_notch(self):
        """矩形房间 notch 为 None"""
        cfg = RoomConfig(type="rectangle", width=3000, length=4000, notch=None)
        room = build_room(cfg)
        assert abs(room.area - 12_000_000) < 1



    def test_polygon_room(self):
        """多边形房间"""
        cfg = RoomSpec(
            name="A", type="polygon",
            points=[(0, 0), (3254, 0), (3254, 3460), (1063, 3460), (1063, 5447), (0, 5447)],
        )
        room = build_room(cfg)
        expected = 3254 * 3460 + 1063 * 1987
        assert abs(room.area - expected) < 1

    def test_obstacle_is_removed_before_expansion_gap(self):
        """柜子区域不铺装，并且伸缩缝预留到柜子边缘"""
        cfg = RoomSpec(
            name="C", type="rectangle", width=2856, length=3462,
            obstacles=[ObstacleConfig(name="wardrobe", type="rectangle", x=0, y=2862, width=1830, length=600)],
        )
        room = build_room(cfg)
        assert abs(room.area - (2856 * 3462 - 1830 * 600)) < 1

        layout = compute_layout_area(room, baseboard_width=15, expansion_gap=10)
        cabinet_gap_probe = layout.intersection(Polygon([(5, 2867), (1825, 2867), (1825, 3457), (5, 3457)]))
        assert cabinet_gap_probe.is_empty


class TestLayoutArea:
    """测试可排样区域计算"""

    def test_inset_rectangle(self):
        """矩形内缩 — 仅减伸缩缝"""
        cfg = RoomConfig(type="rectangle", width=5000, length=6000)
        room = build_room(cfg)
        layout = compute_layout_area(room, baseboard_width=15, expansion_gap=10)
        # 内缩 = 10mm × 2 = 20mm 每边 (仅伸缩缝)
        expected_w = 5000 - 20
        expected_l = 6000 - 20
        expected_area = expected_w * expected_l
        assert abs(layout.area - expected_area) < 1000

    def test_inset_too_large_raises(self):
        """伸缩缝过大导致无排样区域"""
        cfg = RoomConfig(type="rectangle", width=20, length=20)
        room = build_room(cfg)
        with pytest.raises(ValueError, match="无可排样区域"):
            compute_layout_area(room, baseboard_width=15, expansion_gap=12)

    def test_inset_l_shaped(self):
        """L 形内缩 — 仅减伸缩缝"""
        cfg = RoomConfig(
            type="l-shaped", width=6000, length=8000,
            notch=NotchConfig(width=3000, depth=3000, position=NotchPosition.TOP_LEFT),
        )
        room = build_room(cfg)
        layout = compute_layout_area(room, baseboard_width=15, expansion_gap=10)
        # 内缩后面积应略小于原始面积(仅10mm伸缩缝)
        assert layout.area < room.area
        assert layout.area > room.area * 0.9  # 远大于踢脚线+伸缩缝的情况
