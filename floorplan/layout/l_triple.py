"""
L三拼排样引擎 v3

棋盘式: A(竖3) / B(横3) 交替排列
格大小 = 3×板宽 = 264mm (600×88板)
A: 264×600, B: 600×264, 互锁形成 L 形连接
"""

from shapely.geometry import Polygon, box

from ..models import (
    Pattern, BoardConfig, LayoutResult, PlacedBoard,
    LayoutStatistics, CuttingPiece, CuttingGroup,
)
from .base import LayoutEngine, register
from .board_pool import BoardPool
from .aligned import _poly_coords


@register(Pattern.L_TRIPLE)
class LTripleEngine(LayoutEngine):

    def layout(self, room, board, start_offset=(0, 0), direction=0, **kwargs):
        gap = kwargs.get("board_gap", 0.0)
        L, W = board.length, board.width
        kf = kwargs.get('kerf', 1.0)
        pool = BoardPool(L, kerf=kf, board_width=W)
        label_offset = kwargs.get('label_start', 0)

        placed = []
        n = label_offset + 1

        cell = W * 3  # 264mm — grid cell size
        minx, miny, maxx, maxy = room.bounds

        # 计算覆盖房间需要多少格
        cols = int((maxx - minx) / cell) + 4  # +4 because groups extend beyond cell
        rows = int((maxy - miny) / cell) + 4

        # 起点对齐到格
        ox0 = minx - (minx % cell) if cell > 0 else minx
        oy0 = miny - (miny % cell) if cell > 0 else miny

        for gi in range(cols):
            for gj in range(rows):
                ox = ox0 + gi * cell
                oy = oy0 + gj * cell

                if (gi + gj) % 2 == 0:
                    # A group: 3 vertical boards, total 3W×L
                    # 完全在房间外→跳过
                    if ox + 3*W < minx or ox > maxx or oy + L < miny or oy > maxy:
                        continue
                    for i in range(3):
                        bx = ox + i * (W + gap)
                        by = oy
                        n = _try_place(pool, placed, room, L, W,
                                       bx, by, W, L, 90, str(n), gap, kf, n)
                else:
                    # B group: 3 horizontal boards, total L×3W
                    if ox + L < minx or ox > maxx or oy + 3*W < miny or oy > maxy:
                        continue
                    for j in range(3):
                        bx = ox
                        by = oy + j * (W + gap)
                        n = _try_place(pool, placed, room, L, W,
                                       bx, by, L, W, 0, str(n), gap, kf, n)

        full_count = sum(1 for b in placed if not b.is_cut)
        used = pool.total_new_boards + full_count
        area_each = L * W
        total_area = used * area_each
        room_area = room.area

        cgs = [_make_cg(g) for g in pool.cutting_groups]

        return LayoutResult(boards=placed, statistics=LayoutStatistics(
            total_boards=used, full_boards=full_count,
            cut_boards=used - full_count,
            total_area=total_area,
            waste_area=max(0, total_area - room_area),
            room_area=room_area,
            utilization=room_area / total_area if total_area > 0 else 0,
            cutting_groups=cgs,
        ), pattern=Pattern.L_TRIPLE, start_offset=start_offset)


def _try_place(pool, placed, room, L, W,
               bx, by, bw, bh, rotation, label, gap, kerf, n) -> int:
    """尝试放置一块板。返回下一个标签号。

    板以物理尺寸存入 PlacedBoard (不依赖旋转渲染):
      rotation=0 (横放): board_len=L, board_wid=W  → 直接画 L×W
      rotation=90(竖放): board_len=W, board_wid=L  → 直接画 W×L
    """
    bp = box(bx, by, bx + bw, by + bh)
    clipped = room.intersection(bp)
    if clipped.is_empty or clipped.area <= 0.01 * bw * bh:
        return n

    stored_len = L
    is_cut = clipped.area < L * W * 0.99

    if is_cut:
        src = pool.cut_new(L, label)
    else:
        src = pool.register_full(label)

    cx, cy = bx + bw / 2, by + bh / 2
    # 物理尺寸：横放保持 L×W，竖放交换为 W×L
    if rotation == 90:
        board_len, board_wid = W, L  # 88×600
    else:
        board_len, board_wid = L, W  # 600×88

    placed.append(PlacedBoard(
        x=cx, y=cy, rotation=0,
        length=board_len, width=board_wid,
        is_cut=is_cut,
        cut_polygon=_poly_coords(clipped) if is_cut else None,
        label=label, source_id=src,
    ))
    return n + 1


def _make_cg(g: dict) -> CuttingGroup:
    return CuttingGroup(
        source_id=g['source_id'],
        pieces=[CuttingPiece(label=p['label'], length=p['length'],
                             width=p.get('width', 0.0)) for p in g['pieces']],
        total_length=g['total_length'], used_length=g['used_length'],
        waste_length=g['waste_length'],
        width_waste=g.get('width_waste', 0.0),
        parent_source_id=g.get('parent_source_id', ''),
        total_width=g.get('total_width', 0.0),
    )
