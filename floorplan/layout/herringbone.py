"""
人字拼（Herringbone 45°）排样引擎

经典 45° 人字拼：旋转框架法。
房间旋转 -45°：+45° 板→竖板(V)，-45° 板→横板(H)。
横板和竖板交织填充平面，去重后保留最小集。
"""

import math
from shapely.geometry import Polygon, box
from shapely import affinity
from shapely.ops import unary_union

from ..models import Pattern, BoardConfig, LayoutResult, PlacedBoard, LayoutStatistics
from .base import LayoutEngine, register
from .board_pool import BoardPool
from .aligned import _make_cg


@register(Pattern.HERRINGBONE)
class HerringboneEngine(LayoutEngine):
    """45° 人字拼排样引擎（旋转框架稀疏布置 + 贪婪去重）"""

    def layout(self,
               room: Polygon,
               board: BoardConfig,
               start_offset: tuple = (0.0, 0.0),
               direction: float = 45.0,
               **kwargs) -> LayoutResult:
        if direction not in (45, 45.0):
            import warnings
            warnings.warn(f"Herringbone only supports direction=45°, got {direction}. Using 45°.")
        L = board.length
        W = board.width
        ox, oy = start_offset

        # 旋转房间 -45°
        room_rot = affinity.rotate(room, -45, origin=(0, 0))
        rb = room_rot.bounds
        pad = L

        # ---- 密集放置候选板 ----
        # 在旋转空间中，横板(H, 原 -45°) 和 竖板(V, 原 +45°)
        # H: L×W 水平, V: W×L 垂直
        # H 间距: (L+W) 水平, W 垂直
        # V 间距: (L+W) 水平, W 垂直, 偏移 (L, 0) 相对 H

        spacing = L + W
        x0 = rb[0] - pad + ox % spacing
        y0 = rb[1] - pad + oy % L  # V plank pitch is L

        candidates: list[dict] = []  # {poly, angle, x, y}
        label_counter = 0

        # 遍历格点：H板每W放一块，V板每L放一块
        col = 0
        cx = x0
        while cx < rb[2] + pad:
            # H 板（原 +45°）：水平 L×W，Y 间距 = W
            cy_h = y0
            while cy_h < rb[3] + pad:
                hp = box(cx, cy_h, cx + L, cy_h + W)
                h_clip = room_rot.intersection(hp)
                if not h_clip.is_empty and h_clip.area > 0.01 * L * W:
                    label_counter += 1
                    candidates.append(dict(
                        poly=h_clip, angle=45, cx=cx, cy=cy_h,
                        label=str(label_counter),
                    ))
                cy_h += W

            # V 板（原 -45°）：垂直 W×L，Y 间距 = L
            cy_v = y0
            while cy_v < rb[3] + pad:
                vp = box(cx + L, cy_v, cx + L + W, cy_v + L)
                v_clip = room_rot.intersection(vp)
                if not v_clip.is_empty and v_clip.area > 0.01 * L * W:
                    label_counter += 1
                    candidates.append(dict(
                        poly=v_clip, angle=-45, cx=cx + L, cy=cy_v,
                        label=str(label_counter),
                    ))
                cy_v += L

            col += 1
            cx += spacing

        # ---- 贪婪去重：按裁剪面积降序，保留有贡献的板 ----
        candidates.sort(key=lambda c: c['poly'].area, reverse=True)

        kept: list[dict] = []
        union_so_far = None

        for c in candidates:
            if union_so_far is None:
                union_so_far = c['poly']
                kept.append(c)
            else:
                new_area = c['poly'].difference(union_so_far).area
                if new_area > 0.01 * L * W:
                    union_so_far = unary_union([union_so_far, c['poly']])
                    kept.append(c)

        # ---- 转回原坐标系 ----
        placed: list[PlacedBoard] = []
        kf = kwargs.get('kerf', 1.0)
        pool = BoardPool(L, kerf=kf)
        for c in kept:
            poly_orig = affinity.rotate(c['poly'], 45, origin=(0, 0))
            is_cut = c['poly'].area < L * W * 0.99
            centroid = poly_orig.centroid
            lbl = str(c['label'])
            ww = 0.0
            if is_cut:
                used_len = L * (c['poly'].area / (L * W))
                source_id = pool.cut_new(used_len, lbl)
                ww = max(0, L * W - c['poly'].area)
            else:
                source_id = pool.register_full(lbl)
                if c['poly'].area < L * W * 0.99:
                    ww = L * W - c['poly'].area
                    g = pool._groups.get(source_id)
                    if g: g['width_waste'] = float(ww)
            placed.append(PlacedBoard(
                x=centroid.x, y=centroid.y,
                rotation=c['angle'] % 360,
                length=L, width=W,
                is_cut=is_cut,
                cut_polygon=_poly_coords(poly_orig),
                label=lbl, source_id=source_id,
                width_waste=ww,
            ))

        # ---- 统计 ----
        full_boards_placed = sum(1 for b in placed if not b.is_cut)
        total_used = pool.total_new_boards + full_boards_placed
        full_board_area = L * W
        total_board_area = total_used * full_board_area
        room_area = room.area

        cgs = [_make_cg(g) for g in pool.cutting_groups]

        stats = LayoutStatistics(
            total_boards=total_used,
            full_boards=full_boards_placed,
            cut_boards=total_used - full_boards_placed,
            total_area=total_board_area,
            waste_area=max(0, total_board_area - room_area),
            room_area=room_area,
            utilization=room_area / total_board_area if total_board_area > 0 else 0.0,
            cutting_groups=cgs,
        )

        return LayoutResult(
            boards=placed,
            statistics=stats,
            pattern=Pattern.HERRINGBONE,
            start_offset=start_offset,
        )


def _poly_coords(polygon) -> list:
    if hasattr(polygon, 'exterior'):
        return [(x, y) for x, y in polygon.exterior.coords]
    return []
