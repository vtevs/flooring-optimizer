"""
排样引擎 — 抽象基类和注册表

每种铺装方式实现一个 LayoutEngine 子类，注册到 ENGINES 字典。
"""

from abc import ABC, abstractmethod
from shapely.geometry import Polygon

from ..models import Pattern, BoardConfig, LayoutResult


class LayoutEngine(ABC):
    """排样引擎抽象基类"""

    @abstractmethod
    def layout(self,
               room: Polygon,
               board: BoardConfig,
               start_offset: tuple = (0.0, 0.0),
               **kwargs) -> LayoutResult:
        """在给定房间内排样地板。

        Args:
            room: 可排样区域 (Shapely Polygon)
            board: 地板规格
            start_offset: 排样起始偏移 (x, y) in mm
            **kwargs: 该铺装方式的特有参数

        Returns:
            LayoutResult 包含所有 PlacedBoard 和统计信息
        """
        ...


# ---------------------------------------------------------------------------
# 引擎注册表 — 各子类在模块加载时注册
# ---------------------------------------------------------------------------
ENGINES: dict[Pattern, type[LayoutEngine]] = {}


def register(pattern: Pattern):
    """装饰器：注册排样引擎"""
    def decorator(cls: type[LayoutEngine]):
        ENGINES[pattern] = cls
        return cls
    return decorator
