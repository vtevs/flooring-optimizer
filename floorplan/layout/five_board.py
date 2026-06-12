"""
5拼方砖排样引擎 — 棋盘式横竖交替。集成 BoardPool 统一切割追踪。
"""

import math
from shapely.geometry import Polygon, box

from ..models import (Pattern, BoardConfig, LayoutResult, PlacedBoard,
                       LayoutStatistics, CuttingPiece, CuttingGroup)
from .base import LayoutEngine, register
from .board_pool import BoardPool
from .aligned import _poly_coords


@register(Pattern.FIVE_BOARD_SQUARE)
class FiveBoardSquareEngine(LayoutEngine):

    def layout(self, room, board, start_offset=(0, 0), direction=0, **kwargs):
        L, W = board.length, board.width
        gap = kwargs.get("board_gap", 0.0)
        kerf = kwargs.get("kerf", 1.0)

        unit_pitch = W + gap
        square_inner = max(L, 5 * unit_pitch - gap)
        unit_spacing = square_inner + gap
        boards_per_unit = max(5, math.ceil(square_inner / unit_pitch))

        minx, miny, maxx, maxy = room.bounds
        pool = BoardPool(L, kerf=kerf)
        placed = []
        n = 0

        ox, oy = start_offset

        col = int((minx - ox) / unit_spacing) - 1
        while col * unit_spacing + ox < maxx:
            row = int((miny - oy) / unit_spacing) - 1
            while row * unit_spacing + oy < maxy:
                unit_x = col * unit_spacing + ox
                unit_y = row * unit_spacing + oy
                is_horizontal = (row + col) % 2 == 0

                for i in range(boards_per_unit):
                    if is_horizontal:
                        bx, by = unit_x, unit_y + i * unit_pitch
                        bw, bh = L, W
                        rot = 0
                    else:
                        bx, by = unit_x + i * unit_pitch, unit_y
                        bw, bh = W, L
                        rot = 90

                    bp = box(bx, by, bx + bw, by + bh)
                    clipped = room.intersection(bp)
                    if clipped.is_empty or clipped.area <= 0.05 * L * W:
                        continue

                    n += 1
                    label = str(n)
                    is_cut = clipped.area < L * W * 0.99

                    if is_cut:
                        use_len = L * (clipped.area / (L * W))
                        source_id = pool.cut_new(use_len, label)
                        # 宽度废料
                        width_w = L * W - clipped.area - kerf * W  # approx
                    else:
                        source_id = pool.register_full(label)
                        width_w = 0.0

                    placed.append(PlacedBoard(
                        x=bx + bw / 2, y=by + bh / 2,
                        rotation=rot, length=L, width=W,
                        is_cut=is_cut,
                        cut_polygon=_poly_coords(clipped),
                        label=label, source_id=source_id,
                        width_waste=width_w,
                    ))

                row += 1
            col += 1

        full_count = sum(1 for b in placed if not b.is_cut)
        used = pool.total_new_boards + full_count
        area_each = L * W
        total_area = used * area_each
        room_area = room.area

        from .aligned import _make_cg
        cgs = [_make_cg(g) for g in pool.cutting_groups]

        return LayoutResult(boards=placed, statistics=LayoutStatistics(
            total_boards=used, full_boards=full_count, cut_boards=used - full_count,
            total_area=total_area, waste_area=max(0, total_area - room_area),
            room_area=room_area,
            utilization=room_area / total_area if total_area > 0 else 0,
            cutting_groups=cgs,
        ), pattern=Pattern.FIVE_BOARD_SQUARE, start_offset=start_offset)
