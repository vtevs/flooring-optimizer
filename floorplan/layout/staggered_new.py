"""
错缝排样引擎 v3 — 边感知铺装

生成铺装位 (RoomPlacement)，每个位带 required_edges，
通过 SourceBoardManager 匹配池中带四边属性的余料。
"""

import math
from shapely.geometry import Polygon, box

from ..models import (
    Pattern, BoardConfig, LayoutResult, PlacedBoard,
    LayoutStatistics, CuttingPiece, CuttingGroup,
    EdgeType, BoardEdges, RoomPlacement, CutDirection,
)
from .base import LayoutEngine, register
from .source_manager import SourceBoardManager, _edges_usable
from .aligned import _segments, _poly_coords


@register(Pattern.STAGGERED)
class StaggeredEngine(LayoutEngine):

    def layout(self, room, board, start_offset=(0, 0), direction=0, **kwargs):
        ratio = kwargs.get("stagger_ratio", 0.33)
        gap = kwargs.get("board_gap", 0.0)
        L, W = board.length, board.width

        board_step = L + gap
        row_step = W + gap
        stagger = board_step * ratio

        along_y = (direction == 90)
        if not along_y and direction != 0:
            raise ValueError(f"direction must be 0 or 90, got {direction}")

        minx, miny, maxx, maxy = room.bounds
        kf = kwargs.get('kerf', 1.0)
        mgr = SourceBoardManager(L, W, kerf=kf)
        placed = []
        n = kwargs.get('label_start', 0)
        placements = []  # list[RoomPlacement]

        # 行起始对齐（宪法第八条）
        if along_y:
            pos = start_offset[0] + math.floor((minx - start_offset[0]) / row_step) * row_step
            if pos < minx - 0.5:
                pos = minx
            inner_off = start_offset[1] % board_step
            room_len = maxy - miny  # 行方向的房间长度
        else:
            pos = start_offset[1] + math.floor((miny - start_offset[1]) / row_step) * row_step
            if pos < miny - 0.5:
                pos = miny
            inner_off = start_offset[0] % board_step
            room_len = maxx - minx

        # 计算总行数和末行宽（用于判断末行）
        layout_span = (maxx if along_y else maxy) - (minx if along_y else miny)
        total_rows = int((layout_span - (pos - (minx if along_y else miny))) // row_step) + 1
        last_row_start = pos + (total_rows - 1) * row_step

        row_idx = 0
        while pos < (maxx if along_y else maxy):
            is_last_row = (pos >= last_row_start - 0.5)

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

            # Process lead-in
            seg_start = segs[0][0]
            if lead_len > 1.0:
                _place_edge_aware(mgr, placed, placements, room, L, W,
                                  lead_len, True, clipped_strip, seg_start,
                                  along_y, direction, n,
                                  is_last_row, is_first_col=True,
                                  row_idx=row_idx, pos=pos)
                n = len(placed)
            else:
                lead_len = 0

            for s0, s1 in segs:
                seg = s0 + (lead_len if s0 == seg_start else 0)
                while seg < s1:
                    use = min(board_step, s1 - seg)
                    cut = use < board_step * 0.99
                    is_last_col = (seg + use >= s1 - 0.5)

                    _place_edge_aware(mgr, placed, placements, room, L, W,
                                      use, cut, clipped_strip, seg,
                                      along_y, direction, n,
                                      is_last_row, is_first_col=(seg == seg_start and lead_len > 1.0),
                                      is_last_col=is_last_col,
                                      row_idx=row_idx, pos=pos)
                    n = len(placed)
                    seg += use

            pos += row_step
            row_idx += 1

        # Statistics (compatible with old model)
        full_count = sum(1 for b in placed if not b.is_cut)
        used = mgr.total_new_boards + full_count
        area_each = L * W
        total_area = used * area_each
        room_area = room.area

        # Build cutting groups from source board manager
        cgs = _build_cutting_groups(mgr, placed)

        return LayoutResult(boards=placed, statistics=LayoutStatistics(
            total_boards=used, full_boards=full_count,
            cut_boards=used - full_count,
            total_area=total_area,
            waste_area=max(0, total_area - room_area),
            room_area=room_area,
            utilization=room_area / total_area if total_area > 0 else 0,
            cutting_groups=cgs,
        ), pattern=Pattern.STAGGERED, start_offset=start_offset)


def _derive_edges_for_position(along_y: bool, direction: float,
                                is_last_row: bool, is_first_col: bool,
                                is_last_col: bool, row_idx: int) -> BoardEdges:
    """推导铺装位的四边需求。"""
    if along_y:
        # 板沿 y 轴（长边沿 y），行沿 x 轴
        # top/bottom = 板短边, left/right = 板长边
        top_edge = EdgeType.CUT if is_last_row else EdgeType.GROOVE
        bottom_edge = EdgeType.CUT if row_idx == 0 else EdgeType.TONGUE
        left_edge = EdgeType.CUT if is_first_col else EdgeType.GROOVE
        right_edge = EdgeType.CUT if is_last_col else EdgeType.TONGUE
    else:
        # 板沿 x 轴（长边沿 x），行沿 y 轴
        top_edge = EdgeType.CUT if row_idx == 0 else EdgeType.GROOVE
        bottom_edge = EdgeType.CUT if is_last_row else EdgeType.TONGUE
        left_edge = EdgeType.CUT if is_first_col else EdgeType.GROOVE
        right_edge = EdgeType.CUT if is_last_col else EdgeType.TONGUE

    return BoardEdges(
        top=top_edge, bottom=bottom_edge,
        left=left_edge, right=right_edge,
    )


def _place_edge_aware(mgr, placed, placements, room, L, W, use, cut,
                       clipped_strip, seg, along_y, direction, n,
                       is_last_row, is_first_col=False, is_last_col=False,
                       row_idx=0, pos=0):
    """边感知放置一块板。"""
    if along_y:
        bx, by = pos, seg
        bw, bh = W, use
    else:
        bx, by = seg, pos
        bw, bh = use, W

    bp = box(bx, by, bx + bw, by + bh)
    clipped = room.intersection(bp)
    if clipped.is_empty or clipped.area <= 0.01 * bw * bh:
        return

    new_n = n + 1
    label = str(new_n)
    stored_len = use if cut else L
    board_w = W

    # 判断末行宽切
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

    # 此位需要的四边
    required = _derive_edges_for_position(
        along_y, direction, is_last_row, is_first_col, is_last_col, row_idx)

    board_piece = None
    width_w = 0.0

    # 先尝试长度池
    if cut and not needs_width_cut:
        pool_piece = mgr.take_from_length_pool(use, required)
        if pool_piece:
            board_piece = pool_piece
            stored_len = min(use, board_piece.length)
            board_w = board_piece.width

    # 再尝试宽度池
    if board_piece is None and needs_width_cut:
        pool_piece = mgr.take_from_width_pool(actual_w, required)
        if pool_piece:
            board_piece = pool_piece
            board_w = actual_w
            if cut:
                stored_len = use

    # 开新板
    if board_piece is None:
        full = mgr.new_board(label)
        if cut and needs_width_cut:
            # 组合切
            board_w = actual_w
            width_piece, _ = mgr.cut(full, CutDirection.WIDTH, actual_w, "", "")
            board_piece, length_remain = mgr.cut(width_piece, CutDirection.LENGTH, use, label, "")
            if length_remain:
                mgr.add_to_length_pool(length_remain)
            width_w = 0  # width_waste handled by manager
            stored_len = use
        elif cut:
            board_piece, remain = mgr.cut(full, CutDirection.LENGTH, use, label, "")
            if remain:
                mgr.add_to_length_pool(remain)
            stored_len = use
        elif needs_width_cut:
            board_w = actual_w
            board_piece, width_remain = mgr.cut(full, CutDirection.WIDTH, actual_w, label, "")
            if width_remain and width_remain.is_usable:
                mgr.add_to_width_pool(width_remain)
            stored_len = L
        else:
            board_piece = full
            stored_len = L

    if board_piece is None:
        return

    # Validate edges
    if not _edges_usable(board_piece.edges, required):
        # Edge mismatch — fall back: use board anyway (non-blocking for now)
        pass

    source_id = board_piece.source_board_id
    is_really_cut = cut or needs_width_cut or board_piece.length < L * 0.99 or board_piece.width < W * 0.99

    if along_y:
        cx = bx + board_w / 2
        cy = by + stored_len / 2
    else:
        cx = bx + stored_len / 2
        cy = by + board_w / 2

    placed.append(PlacedBoard(
        x=cx, y=cy,
        rotation=direction, length=stored_len, width=board_w,
        is_cut=is_really_cut,
        cut_polygon=_poly_coords(clipped) if is_really_cut else None,
        label=label, source_id=source_id,
        width_waste=width_w,
    ))


# ── 兼容旧模型：从 manager 构建 cutting_groups ─────────

def _build_cutting_groups(mgr: SourceBoardManager,
                           placed: list) -> list:
    """从 SourceBoardManager 构建 CuttingGroup 列表（兼容旧格式）。"""
    groups = []
    seen_pieces = set()

    for b in placed:
        sid = b.source_id
        # Use the source board ID for grouping
        if sid not in seen_pieces:
            seen_pieces.add(sid)
            # Find all pieces from this source board
            sb = mgr.source_boards.get(sid)
            if sb:
                for pid in sb.pieces_produced:
                    ps = mgr.all_pieces.get(pid)
                    if ps:
                        groups.append(CuttingGroup(
                            source_id=sid if pid == sb.pieces_produced[0] else f"{sid}-p{pid}",
                            pieces=[CuttingPiece(
                                label=b.label,
                                length=ps.length,
                                width=ps.width if ps.width < mgr._W else 0.0,
                            )],
                            total_length=sb.original_length,
                            used_length=ps.length,
                            waste_length=max(0, sb.original_length - ps.length),
                            width_waste=0.0,
                            parent_source_id="",
                            total_width=sb.original_width,
                        ))
    return groups
