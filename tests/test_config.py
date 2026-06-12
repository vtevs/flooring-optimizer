"""测试配置加载与校验"""
import pytest
import tempfile
from pathlib import Path

# 需要从项目根目录运行: python -m pytest tests/
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from floorplan.config import load_config
from floorplan.models import Pattern, NotchPosition


class TestConfigLoading:
    """测试基本配置加载"""

    def test_rectangle_room(self):
        """矩形房间基本配置"""
        yaml = """
room:
  type: rectangle
  width: 5000
  length: 6000
board:
  length: 1210
  width: 198
installation:
  pattern: aligned
  direction: 0
"""
        cfg = _parse(yaml)
        assert cfg.room.type == "rectangle"
        assert cfg.room.width == 5000
        assert cfg.room.length == 6000
        assert cfg.board.length == 1210
        assert cfg.board.width == 198
        assert cfg.installation.pattern == Pattern.ALIGNED

    def test_l_shaped_room(self):
        """L 形房间配置"""
        yaml = """
room:
  type: l-shaped
  width: 6000
  length: 8000
  notch:
    width: 3000
    depth: 3000
    position: top-left
board:
  length: 1210
  width: 198
installation:
  pattern: staggered
  direction: 90
  stagger_ratio: 0.5
"""
        cfg = _parse(yaml)
        assert cfg.room.type == "l-shaped"
        assert cfg.room.notch.width == 3000
        assert cfg.room.notch.position == NotchPosition.TOP_LEFT
        assert cfg.installation.pattern == Pattern.STAGGERED
        assert cfg.installation.stagger_ratio == 0.5

    def test_default_values(self):
        """测试默认值"""
        yaml = """
room:
  type: rectangle
  width: 3000
  length: 4000
board:
  length: 900
  width: 150
"""
        cfg = _parse(yaml)
        assert cfg.installation.pattern == Pattern.ALIGNED
        assert cfg.installation.direction == 0.0
        assert cfg.edges.baseboard_width == 15.0
        assert cfg.edges.expansion_gap == 10.0
        assert cfg.edges.board_gap == 0.0
        assert cfg.output.file == "floor_plan.svg"

    def test_herringbone_pattern(self):
        """人字拼配置"""
        yaml = """
room:
  type: rectangle
  width: 4000
  length: 5000
board:
  length: 900
  width: 120
installation:
  pattern: herringbone
"""
        cfg = _parse(yaml)
        assert cfg.installation.pattern == Pattern.HERRINGBONE

    def test_five_board_square_pattern(self):
        """5拼方砖配置"""
        yaml = """
room:
  type: rectangle
  width: 4000
  length: 5000
board:
  length: 440
  width: 88
installation:
  pattern: five-board-square
"""
        cfg = _parse(yaml)
        assert cfg.installation.pattern == Pattern.FIVE_BOARD_SQUARE


class TestConfigValidation:
    """测试配置校验"""

    def test_missing_room(self):
        with pytest.raises(ValueError, match="缺少.*room"):
            _parse("board:\n  length: 100\n  width: 50\n")

    def test_missing_board(self):
        with pytest.raises(ValueError, match="缺少.*board"):
            _parse("room:\n  type: rectangle\n  width: 100\n  length: 100\n")

    def test_invalid_pattern(self):
        with pytest.raises(ValueError, match="无效的铺装方式"):
            _parse("""
room: {type: rectangle, width: 100, length: 100}
board: {length: 100, width: 50}
installation: {pattern: invalid_pattern}
""")

    def test_invalid_direction(self):
        with pytest.raises(ValueError, match="无效的铺装方向"):
            _parse("""
room: {type: rectangle, width: 100, length: 100}
board: {length: 100, width: 50}
installation: {pattern: aligned, direction: 180}
""")

    def test_negative_dimension(self):
        with pytest.raises(ValueError, match="必须为正数"):
            _parse("""
room: {type: rectangle, width: -100, length: 100}
board: {length: 100, width: 50}
""")

    def test_board_width_greater_than_length(self):
        with pytest.raises(ValueError, match="板宽不能大于板长"):
            _parse("""
room: {type: rectangle, width: 100, length: 100}
board: {length: 50, width: 100}
""")

    def test_notch_too_large(self):
        with pytest.raises(ValueError, match="缺口尺寸不能超过"):
            _parse("""
room: {type: l-shaped, width: 1000, length: 1000, notch: {width: 2000, depth: 500, position: top-left}}
board: {length: 100, width: 50}
""")

    def test_l_shaped_without_notch(self):
        with pytest.raises(ValueError, match="需要配置.*notch"):
            _parse("""
room: {type: l-shaped, width: 1000, length: 1000}
board: {length: 100, width: 50}
""")

    def test_invalid_notch_position(self):
        with pytest.raises(ValueError, match="无效的缺口位置"):
            _parse("""
room: {type: l-shaped, width: 1000, length: 1000, notch: {width: 500, depth: 500, position: middle}}
board: {length: 100, width: 50}
""")


def _parse(yaml_str: str):
    """辅助函数：将 YAML 字符串写入临时文件并加载"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False, encoding='utf-8') as f:
        f.write(yaml_str)
        tmp = f.name
    try:
        return load_config(tmp)
    finally:
        Path(tmp).unlink()
