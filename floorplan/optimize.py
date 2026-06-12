"""
排样优化器 v2

枚举起始偏移，选利用率最高的排样结果。
改进：更细粒度搜索 + 局部精化。
"""

from shapely.geometry import Polygon

from .models import BoardConfig, LayoutResult
from .layout import ENGINES


def optimize(room: Polygon,
             board: BoardConfig,
             pattern,
             direction: float = 0.0,
             **kwargs) -> LayoutResult:
    """对给定房间和地板规格寻找最优排样。

    优化策略：
    1. 粗搜索：枚举起始偏移（步长 = 板长/宽 的 1/16）
    2. 精化：在最佳粗搜索结果附近做更细粒度搜索（步长 = 粗步长/4）
    """
    engine_cls = ENGINES.get(pattern)
    if engine_cls is None:
        raise ValueError(f"未注册的铺装方式: {pattern}")

    L, W = board.length, board.width

    # 粗搜索步长
    coarse_x_step = max(L / 16, 10.0)
    coarse_y_step = max(W / 16, 5.0)

    # Phase 1: 粗搜索
    best = _search_grid(room, board, engine_cls, pattern, direction,
                        coarse_x_step, coarse_y_step, L, W, **kwargs)

    if best is None:
        raise RuntimeError("无法生成任何有效排样")

    # Phase 2: 局部精化（在最佳点附近用小步长搜索）
    fine_x_step = max(coarse_x_step / 4, 1.0)
    fine_y_step = max(coarse_y_step / 4, 1.0)
    xo_best, yo_best = best[1], best[2]

    refined = _search_grid(room, board, engine_cls, pattern, direction,
                           fine_x_step, fine_y_step, L, W,
                           x_range=(xo_best - coarse_x_step, xo_best + coarse_x_step),
                           y_range=(yo_best - coarse_y_step, yo_best + coarse_y_step),
                           **kwargs)

    return (refined[0] if refined else best[0])


def _search_grid(room, board, engine_cls, pattern, direction,
                 x_step, y_step, L, W,
                 x_range=None, y_range=None, **kwargs):
    """在指定网格上搜索最佳偏移。"""
    x_min = x_range[0] if x_range else 0.0
    x_max = x_range[1] if x_range else L
    y_min = y_range[0] if y_range else 0.0
    y_max = y_range[1] if y_range else W

    best = None  # (result, xo, yo)

    xo = x_min
    while xo < x_max:
        yo = y_min
        while yo < y_max:
            engine = engine_cls()
            result = engine.layout(
                room, board,
                start_offset=(xo, yo),
                direction=direction,
                **kwargs,
            )
            util = result.statistics.utilization
            if util <= 1.02:
                if best is None or util > best[0].statistics.utilization:
                    best = (result, xo, yo)
            yo += y_step
        xo += x_step

    return best


def _arange(start, stop, step):
    result = []
    x = start
    while x < stop:
        result.append(x)
        x += step
    return result
