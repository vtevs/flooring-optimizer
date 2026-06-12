"""
对拼（直铺）排样引擎 — 板同向平行排列，无行偏移。
切割尾料跨行复用（同方向、榫槽约束），切割方案追踪来源板。
"""

import math
from shapely.geometry import Polygon, box

from ..models import (Pattern, BoardConfig, LayoutResult, PlacedBoard,
                       LayoutStatistics, CuttingPiece, CuttingGroup)
from .base import LayoutEngine, register
from .board_pool import BoardPool


@register(Pattern.ALIGNED)
class AlignedEngine(LayoutEngine):

    def layout(self, room, board, start_offset=(0, 0), direction=0, **kwargs):
        gap = kwargs.get("board_gap", 0.0)
        L, W = board.length, board.width
        board_step = L + gap
        row_step = W + gap

        if direction == 0:
            along_y = False
        elif direction == 90:
            along_y = True
        else:
            raise ValueError(f"direction must be 0 or 90, got {direction}")

        minx, miny, maxx, maxy = room.bounds
        kf = kwargs.get('kerf', 1.0)
        pool = kwargs.get('pool') or BoardPool(L, kerf=kf, board_width=W)
        label_offset = kwargs.get('label_start', 0)
        placed = []
        n = label_offset

        if along_y:
            pos = start_offset[0] + math.floor((minx - start_offset[0]) / row_step) * row_step
            if pos < minx - 0.5:
                pos = minx
        else:
            pos = start_offset[1] + math.floor((miny - start_offset[1]) / row_step) * row_step
            if pos < miny - 0.5:
                pos = miny

        layout_max = maxx if along_y else maxy
        while pos < layout_max:
            is_last_row_pos = (pos + row_step >= layout_max - 0.5)
            if along_y:
                strip = box(pos, miny - 1, pos + W, maxy + 1)
            else:
                strip = box(minx - 1, pos, maxx + 1, pos + W)

            clipped_strip = room.intersection(strip)
            if clipped_strip.is_empty:
                pos += row_step
                continue

            segs = _segments(clipped_strip, axis=1 if along_y else 0)

            for s0, s1 in segs:
                seg = s0
                while seg < s1:
                    use = min(board_step, s1 - seg)
                    cut = use < board_step * 0.99

                    if along_y:
                        bx, by = pos, seg  # 使用条带位置，非裁剪后位置
                        bw, bh = W, use
                    else:
                        bx, by = seg, pos
                        bw, bh = use, W

                    bp = box(bx, by, bx + bw, by + bh)
                    clipped = room.intersection(bp)

                    if clipped.is_empty or clipped.area <= 0.01 * bw * bh:
                        seg += use
                        continue

                    # Pool call AFTER area check (#1)
                    n += 1
                    label = str(n)
                    width_w = 0.0
                    stored_len = use if cut else L
                    board_w = W

                    # 推导此位需要的物理四边
                    is_first_col = (seg == s0)
                    is_last_col = (seg + use >= s1 - 0.5)
                    is_first_row = (pos <= room.bounds[1 if not along_y else 0] + 1.0)
                    from ..models import EdgeType, BoardEdges
                    if along_y:
                        req_edges = BoardEdges(
                            top=EdgeType.CUT if is_last_row_pos else EdgeType.TONGUE,
                            bottom=EdgeType.CUT if is_first_row else EdgeType.GROOVE,
                            left=EdgeType.CUT if is_first_col else EdgeType.GROOVE,
                            right=EdgeType.CUT if is_last_col else EdgeType.TONGUE,
                        )
                    else:
                        req_edges = BoardEdges(
                            top=EdgeType.CUT if is_last_row_pos else EdgeType.GROOVE,
                            bottom=EdgeType.CUT if is_first_row else EdgeType.TONGUE,
                            left=EdgeType.CUT if is_first_col else EdgeType.GROOVE,
                            right=EdgeType.CUT if is_last_col else EdgeType.TONGUE,
                        )

                    # Detect true width-cut: board extends past layout boundary on far side
                    if along_y:
                        board_right = bx + W
                        layout_max_x = room.bounds[2]
                        is_boundary_overlap = bx < room.bounds[0] + 0.5
                        needs_width_cut = board_right > layout_max_x + 0.5 and not is_boundary_overlap
                        actual_w = (layout_max_x - bx) if needs_width_cut else W
                    else:
                        board_top = by + W
                        layout_max_y = room.bounds[3]
                        is_boundary_overlap = by < room.bounds[1] + 0.5
                        needs_width_cut = board_top > layout_max_y + 0.5 and not is_boundary_overlap
                        actual_w = (layout_max_y - by) if needs_width_cut else W

                    if cut and needs_width_cut:
                        board_w = actual_w
                        source_id = pool.try_take_width_reduced(actual_w, label)
                        if source_id is None:
                            source_id = pool.cut_new_combined(use, actual_w, label)
                        else:
                            width_w = stored_len * (W - actual_w)
                    elif cut:
                        source_id = pool.take_or_cut(use, label)
                    elif needs_width_cut:
                        board_w = actual_w
                        source_id = pool.try_take_width_reduced(actual_w, label)
                        if source_id is None:
                            source_id = pool.register_full(label, width_waste=L * W - clipped.area)
                        else:
                            width_w = L * W - clipped.area
                    else:
                        if clipped.area < L * W * 0.99:
                            width_w = L * W - clipped.area
                            board_w = clipped.area / stored_len
                            source_id = pool.register_full(label, width_waste=width_w)
                        else:
                            source_id = pool.register_full(label)
                    if along_y:
                        cx = bx + W / 2
                        cy = by + stored_len / 2
                    else:
                        cx = bx + stored_len / 2
                        cy = by + W / 2
                    is_really_cut = cut or width_w > 0.5
                    placed.append(PlacedBoard(
                        x=cx, y=cy,
                        rotation=direction, length=stored_len, width=board_w,
                        is_cut=is_really_cut,
                        cut_polygon=_poly_coords(clipped) if is_really_cut else None,
                        label=label, source_id=source_id,
                        width_waste=width_w,
                    ))

                    seg += use

            pos += row_step

        # Statistics (#3): full boards + new cuts + pool reuses
        full_count = sum(1 for b in placed if not b.is_cut)
        used = pool.total_new_boards + full_count
        area_each = L * W
        total_area = used * area_each
        room_area = room.area

        cgs = [_make_cg(g) for g in pool.cutting_groups]

        return LayoutResult(boards=placed, statistics=LayoutStatistics(
            total_boards=used, full_boards=full_count, cut_boards=used - full_count,
            total_area=total_area, waste_area=max(0, total_area - room_area),
            room_area=room_area,
            utilization=room_area / total_area if total_area > 0 else 0,
            cutting_groups=cgs,
        ), pattern=Pattern.ALIGNED, start_offset=start_offset)


def _derive_cg_edges(g: dict, board_w: float = 148) -> "BoardEdges":
    """从切割组元数据推导四边属性。"""
    from ..models import EdgeType, BoardEdges
    has_width = g.get('width_waste', 0) > 10
    has_length = g.get('waste_length', 0) > 0.5
    n_pieces = len(g.get('pieces', []))

    e = BoardEdges(
        top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
        left=EdgeType.GROOVE, right=EdgeType.TONGUE,
    )
    if has_width:
        # 宽切影响 top/bottom
        e = BoardEdges(top=EdgeType.CUT, bottom=e.bottom,
                       left=e.left, right=e.right)
        # 废料 top=CUT → 唯一可用边是 bottom
    if has_length or n_pieces > 1:
        # 长切影响 left/right
        e = BoardEdges(top=e.top, bottom=e.bottom,
                       left=e.left, right=EdgeType.CUT)
    return e


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


def _segments(poly, axis=0):
    if poly.is_empty:
        return []
    if poly.geom_type == "MultiPolygon":
        out = []
        for geom in poly.geoms:
            b = geom.bounds
            out.append((b[axis], b[axis + 2]))
        return sorted(out)
    b = poly.bounds
    return [(b[axis], b[axis + 2])]


def _poly_coords(poly):
    """提取多边形坐标，处理 MultiPolygon (#6)"""
    if hasattr(poly, 'geoms'):
        # MultiPolygon — 合并所有子多边形坐标
        result = []
        for g in poly.geoms:
            if hasattr(g, 'exterior'):
                result.extend((x, y) for x, y in g.exterior.coords)
        return result
    if hasattr(poly, 'exterior'):
        return [(x, y) for x, y in poly.exterior.coords]
    return []
