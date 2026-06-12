"""
房间几何模型

L 形房间 = 包围矩形 - 角落缺口
使用 Shapely 构建多边形，支持:
- 面积计算
- 内缩（踢脚线 + 伸缩缝）
- 可排样区域计算
"""

from shapely.geometry import Polygon, Point
from shapely import affinity

from ..models import RoomConfig, NotchConfig, NotchPosition


def build_room(config: RoomConfig) -> Polygon:
    """从配置构建房间 Shapely Polygon。

    Args:
        config: 房间配置

    Returns:
        Shapely Polygon (单位: mm)

    Raises:
        ValueError: 缺口尺寸超出房间范围
    """
    w, h = config.width, config.length

    if config.type == "rectangle" or config.notch is None:
        return Polygon([(0, 0), (w, 0), (w, h), (0, h)])

    # L 形：包围矩形减去角落缺口
    notch = config.notch
    outer = Polygon([(0, 0), (w, 0), (w, h), (0, h)])

    # 根据缺口位置构建缺口矩形
    nw, nd = notch.width, notch.depth

    if notch.position == NotchPosition.TOP_LEFT:
        hole = Polygon([(0, h - nd), (nw, h - nd), (nw, h), (0, h)])
    elif notch.position == NotchPosition.TOP_RIGHT:
        hole = Polygon([(w - nw, h - nd), (w, h - nd), (w, h), (w - nw, h)])
    elif notch.position == NotchPosition.BOTTOM_LEFT:
        hole = Polygon([(0, 0), (nw, 0), (nw, nd), (0, nd)])
    elif notch.position == NotchPosition.BOTTOM_RIGHT:
        hole = Polygon([(w - nw, 0), (w, 0), (w, nd), (w - nw, nd)])
    else:
        raise ValueError(f"未知缺口位置: {notch.position}")

    room = outer.difference(hole)

    if room.is_empty:
        raise ValueError("缺口尺寸过大，房间面积为 0")

    return room


def compute_layout_area(room: Polygon,
                        baseboard_width: float,
                        expansion_gap: float) -> Polygon:
    """计算可排样区域（房间减去踢脚线和伸缩缝后的内缩区域）。

    Args:
        room: 房间多边形
        baseboard_width: 踢脚线宽度
        expansion_gap: 伸缩缝宽度

    Returns:
        内缩后的多边形（Shapely Polygon）
    """
    # 踢脚线压在地板上方，仅伸缩缝减少铺装区域
    layout_area = room.buffer(-expansion_gap, join_style=2)

    if layout_area.is_empty:
        raise ValueError(
            f"伸缩缝 {expansion_gap}mm 过大，无可排样区域"
        )

    return layout_area
