"""
错缝排样引擎 — 行间偏移板长×错缝比例。切割尾料跨行复用，追踪来源板。
"""

import math
from shapely.geometry import Polygon, box

from ..models import (Pattern, BoardConfig, LayoutResult, PlacedBoard,
                       LayoutStatistics, CuttingPiece, CuttingGroup)
from .base import LayoutEngine, register
from .board_pool import BoardPool
from .aligned import _segments, _poly_coords, _make_cg


@register(Pattern.STAGGERED)
class StaggeredEngine(LayoutEngine):

    def layout(self, room, board, start_offset=(0, 0), direction=0, **kwargs):
        ratio = kwargs.get("stagger_ratio", 0.33)
        gap = kwargs.get("board_gap", 0.0)
        L, W = board.length, board.width

        board_step = L + gap
        row_step = W + gap
        stagger = board_step * ratio  # 错缝基于板间距(含缝)

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
                pos = minx  # 首行对齐到铺装区边界
            inner_off = start_offset[1] % board_step
        else:
            pos = start_offset[1] + math.floor((miny - start_offset[1]) / row_step) * row_step
            if pos < miny - 0.5:
                pos = miny
            inner_off = start_offset[0] % board_step

        row_idx = 0
        layout_max = maxx if along_y else maxy
        while pos < layout_max:
            is_last_row = (pos + row_step >= layout_max - 0.5)
            if along_y:
                strip = box(pos, miny - 1, pos + W, maxy + 1)
            else:
                strip = box(minx - 1, pos, maxx + 1, pos + W)

            clipped_strip = room.intersection(strip)
            if clipped_strip.is_empty:
                pos += row_step
                row_idx += 1
                continue

            segs = _segments(clipped_strip, axis=1 if along_y else 0)
            row_off = (row_idx % 2) * stagger + inner_off
            lead_len = row_off % board_step

            if lead_len > 1.0:
                _place_piece(pool, placed, room, L, W, lead_len, True,
                             clipped_strip, segs[0][0], along_y, direction, n, pos,
                             is_last_row=is_last_row, is_first_col=True, is_last_col=False)
                n = label_offset + len(placed)
            else:
                lead_len = 0

            for s0, s1 in segs:
                # Lead-in applied to first segment only (#7)
                seg = s0 + (lead_len if s0 == segs[0][0] else 0)
                is_first_in_row = True

                while seg < s1:
                    use = min(board_step, s1 - seg)
                    cut = use < board_step * 0.99
                    is_last_in_row = (seg + use >= s1 - 0.5)

                    _place_piece(pool, placed, room, L, W, use, cut,
                                 clipped_strip, seg, along_y, direction, n, pos,
                                 is_last_row=is_last_row,
                                 is_first_col=is_first_in_row,
                                 is_last_col=is_last_in_row)
                    n = label_offset + len(placed)
                    seg += use
                    is_first_in_row = False

            pos += row_step
            row_idx += 1

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
        ), pattern=Pattern.STAGGERED, start_offset=start_offset)


def _place_piece(pool, placed, room, L, W, use, cut, clipped_strip, seg,
                 along_y, direction, n, pos,
                 is_last_row=False, is_first_col=False, is_last_col=False):
    """放置一块板，池调用在面积检查之后"""
    if along_y:
        bx, by = pos, seg  # 使用条带位置，非裁剪后位置
        bw, bh = W, use
    else:
        bx, by = seg, pos
        bw, bh = use, W

    bp = box(bx, by, bx + bw, by + bh)
    clipped = room.intersection(bp)
    if clipped.is_empty or clipped.area <= 0.01 * bw * bh:
        return

    # Pool call AFTER area check (#1)
    new_n = n + 1
    label = str(new_n)
    width_w = 0.0
    stored_len = use if cut else L
    board_w = W  # 实际使用宽度（宽切时 < W）

    # Detect true width-cut: board extends past layout boundary on the far side
    if along_y:
        board_right = bx + W
        layout_max_x = room.bounds[2]
        is_boundary_overlap = bx < room.bounds[0] + 0.5
        needs_width_cut = board_right > layout_max_x + 0.5 and not is_boundary_overlap
        if needs_width_cut:
            actual_w = layout_max_x - bx
        else:
            actual_w = W
    else:
        board_top = by + W
        layout_max_y = room.bounds[3]
        is_boundary_overlap = by < room.bounds[1] + 0.5
        needs_width_cut = board_top > layout_max_y + 0.5 and not is_boundary_overlap
        if needs_width_cut:
            actual_w = layout_max_y - by
        else:
            actual_w = W

    # Derive required PHYSICAL edges for this placement position
    # direction=0: 板不旋转, 物理=固有 (G-T-G-T)
    # direction=90: 90°CW, 物理(T,B,L,R)=固有(L,R,B,T)=(G,T,T,G)
    from ..models import EdgeType, BoardEdges
    if along_y:
        # direction=90°: 物理(T,B,L,R) = (T,G,G,T)
        # 左墙(pos≈minx): 物理LEFT靠墙
        # 右墙(末行): 物理RIGHT靠墙
        # 底墙(seg≈miny): 物理BOTTOM靠墙
        # 顶墙(末列): 物理TOP靠墙
        is_first_row = (pos <= room.bounds[0] + 1.0)
        req_edges = BoardEdges(
            top=EdgeType.CUT if is_last_col else EdgeType.TONGUE,
            bottom=EdgeType.CUT if is_first_col else EdgeType.GROOVE,
            left=EdgeType.CUT if is_first_row else EdgeType.GROOVE,
            right=EdgeType.CUT if is_last_row else EdgeType.TONGUE,
        )
    else:
        # direction=0: 物理=固有 (top=G, bottom=T, left=G, right=T)
        is_first_row = (pos <= room.bounds[1] + 1.0)
        req_edges = BoardEdges(
            top=EdgeType.CUT if is_last_row else EdgeType.GROOVE,
            bottom=EdgeType.CUT if is_first_row else EdgeType.TONGUE,
            left=EdgeType.CUT if is_first_col else EdgeType.GROOVE,
            right=EdgeType.CUT if is_last_col else EdgeType.TONGUE,
        )

    if cut and needs_width_cut:
        board_w = actual_w
        source_id = pool.try_take_width_reduced(actual_w, label,
                                                  required_edges=req_edges,
                                                  rotation=direction)
        if source_id is None:
            source_id = pool.cut_new_combined(use, actual_w, label)
        else:
            width_w = stored_len * (W - actual_w)
    elif cut:
        source_id = pool.take_or_cut(use, label,
                                      required_edges=req_edges,
                                      rotation=direction)
    elif needs_width_cut:
        board_w = actual_w
        source_id = pool.try_take_width_reduced(actual_w, label,
                                                  required_edges=req_edges,
                                                  rotation=direction)
        if source_id is None:
            source_id = pool.register_full(label, width_waste=L * W - clipped.area)
        else:
            width_w = L * W - clipped.area
    else:
        # 常规整板（可能有轻微宽切，如边界重叠）
        if clipped.area < L * W * 0.99:
            width_w = L * W - clipped.area
            board_w = clipped.area / stored_len
            source_id = pool.register_full(label, width_waste=width_w)
        else:
            source_id = pool.register_full(label)
    # 板中心 = 板本身的中心 (不含 gap)，而非 slot 中心
    if along_y:
        cx = bx + W / 2
        cy = by + stored_len / 2
    else:
        cx = bx + stored_len / 2
        cy = by + W / 2
    # 宽度裁剪板也标记为 cut，渲染时用实际形状
    is_really_cut = cut or width_w > 0.5
    placed.append(PlacedBoard(
        x=cx, y=cy,
        rotation=direction, length=stored_len, width=board_w,
        is_cut=is_really_cut,
        cut_polygon=_poly_coords(clipped) if is_really_cut else None,
        label=label, source_id=source_id,
        width_waste=width_w,
    ))
