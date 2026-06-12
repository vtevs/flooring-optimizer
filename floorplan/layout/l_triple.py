"""
三 L 拼排样引擎。

坐标模型见 docs/superpowers/specs/2026-06-12-three-l-pattern-design.md。

设板宽 W=m、板长 L=n：
- A 单元：三块竖向板，尺寸 W×L，起点 P+(0,0)/(S,0)/(2S,0)
- B 单元：三块横向板，尺寸 L×W，起点 P+(3S,0)/(3S,S)/(3S,2S)
- S = W + board_gap
- 组内平移 d=(3S,3S)
- 组间平移 u=(3S+L,3S-L)

完整铺装取 r,k ∈ Z 的 P(r,k)=start_offset+r*u+k*d，再裁剪到房间。
"""

import math

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
        L, W = board.length, board.width
        gap = kwargs.get('board_gap', 0.0)
        pitch = W + gap
        kf = kwargs.get('kerf', 1.0)
        pool = kwargs.get('pool') or BoardPool(L, kerf=kf, board_width=W)
        label_offset = kwargs.get('label_start', 0)

        placed = []
        next_label = label_offset + 1
        minx, miny, maxx, maxy = room.bounds

        origin = (float(start_offset[0]), float(start_offset[1]))
        d = (3 * pitch, 3 * pitch)
        u = (3 * pitch + L, 3 * pitch - L)

        r0, r1, k0, k1 = _lattice_ranges(room.bounds, origin, u, d)

        for r in range(r0, r1 + 1):
            for k in range(k0, k1 + 1):
                px = origin[0] + r * u[0] + k * d[0]
                py = origin[1] + r * u[1] + k * d[1]

                # Quick reject for the whole A+B local envelope.
                if px > maxx + 1 or px + 3 * pitch + L < minx - 1:
                    continue
                if py > maxy + 1 or py + max(L, 3 * pitch) < miny - 1:
                    continue

                # A: three vertical boards, each W × L.
                for i in range(3):
                    next_label = _try_place_rect(
                        pool, placed, room, L, W,
                        px + i * pitch, py, W, L,
                        str(next_label), next_label)

                # B: three horizontal boards, each L × W, starting at x=3W.
                for i in range(3):
                    next_label = _try_place_rect(
                        pool, placed, room, L, W,
                        px + 3 * pitch, py + i * pitch, L, W,
                        str(next_label), next_label)

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


def _lattice_ranges(bounds, origin, u, d):
    """Return conservative integer ranges for r,k covering bounds.

    We map the room bbox corners into lattice coordinates based on the two
    vectors u and d, then pad to cover boards extending from each lattice point.
    """
    minx, miny, maxx, maxy = bounds
    det = u[0] * d[1] - u[1] * d[0]
    if abs(det) < 1e-9:
        raise ValueError('三 L 拼生成向量退化，无法铺装')

    coords = []
    for x, y in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)):
        vx, vy = x - origin[0], y - origin[1]
        r = (vx * d[1] - vy * d[0]) / det
        k = (u[0] * vy - u[1] * vx) / det
        coords.append((r, k))

    rs = [c[0] for c in coords]
    ks = [c[1] for c in coords]
    pad = 4
    return (math.floor(min(rs)) - pad, math.ceil(max(rs)) + pad,
            math.floor(min(ks)) - pad, math.ceil(max(ks)) + pad)


def _try_place_rect(pool, placed, room, L, W,
                    bx, by, bw, bh, label, next_label) -> int:
    """Place one physical board rectangle and return the next label number."""
    from shapely.geometry import box

    bp = box(bx, by, bx + bw, by + bh)
    clipped = room.intersection(bp)
    if clipped.is_empty or clipped.area <= 0.01 * bw * bh:
        return next_label

    cx0, cy0, cx1, cy1 = clipped.bounds
    if bw <= W + 0.5 and bh >= L - 0.5:
        used_len = max(0.0, cy1 - cy0)
        actual_w = max(0.0, cx1 - cx0)
    else:
        used_len = max(0.0, cx1 - cx0)
        actual_w = max(0.0, cy1 - cy0)

    length_cut = used_len < L - 0.5
    width_cut = actual_w < W - 0.5
    is_cut = length_cut or width_cut
    if length_cut and width_cut:
        src = pool.cut_new_combined(used_len, actual_w, label)
    elif length_cut:
        src = pool.take_or_cut(used_len, label)
    elif width_cut:
        src = pool.cut_new_width(actual_w, label)
    else:
        src = pool.register_full(label)

    placed.append(PlacedBoard(
        x=bx + bw / 2, y=by + bh / 2,
        rotation=0,
        length=bw, width=bh,
        is_cut=is_cut,
        cut_polygon=_poly_coords(clipped) if is_cut else None,
        label=label, source_id=src,
    ))
    return next_label + 1


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
        edges=g.get('edges'),
    )
