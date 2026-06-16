"""
多房间排样优化器 v2 — 共享尾料池，跨房间复用切割余料。

策略：
1. 每房间独立找最优 config (pattern + direction + ratio) + offset
2. 用最优 config，枚举房间顺序 + 共享池
3. 比较独立方案与共享池方案，取最优

改进：更细粒度偏移搜索 + 局部精化
"""

import itertools
from .models import (Pattern, BoardConfig, RoomSpec, LayoutResult,
                      MultiRoomResult)
from .layout import ENGINES
from .layout.board_pool import BoardPool
from .geometry.room import build_room, compute_layout_area


def optimize_multi(room_specs, board, edges, kerf, installation=None, **kwargs):
    if installation is not None:
        patterns = [installation.pattern]
        directions = [installation.direction]
        stagger_ratios = ([installation.stagger_ratio]
                          if installation.pattern == Pattern.STAGGERED
                          else [None])
    else:
        patterns = [Pattern.ALIGNED, Pattern.STAGGERED]
        directions = [0, 90]
        stagger_ratios = [0.33, 0.5]

    L, W = board.length, board.width
    # 粗搜索步长
    coarse_x = max(L / 12, 10.0)
    coarse_y = max(W / 6, 10.0)

    # Phase 1: per-room best offset
    room_best = []
    for rs in room_specs:
        room_area = compute_layout_area(
            build_room(rs),
            edges.baseboard_width, edges.expansion_gap)

        # 铺装区 minx/miny（用于对齐搜索）
        minx, miny = room_area.bounds[0], room_area.bounds[1]

        best_r, best_cfg = None, None
        for pat in patterns:
            for d in directions:
                for r in (stagger_ratios if pat == Pattern.STAGGERED else [None]):
                    engine = ENGINES[pat]()
                    kwa = {'board_gap': edges.board_gap, 'kerf': kerf}
                    if r is not None:
                        kwa['stagger_ratio'] = r

                    # 搜索偏移：从负值开始以覆盖铺装区边界对齐
                    offsets_x = _make_offsets(-coarse_x, L, coarse_x, lo=-coarse_x, hi=L)
                    offsets_y = _make_offsets(-coarse_y, W, coarse_y, lo=-coarse_y, hi=W)

                    for xo in offsets_x:
                        for yo in offsets_y:
                            res = engine.layout(room_area, board,
                                               start_offset=(xo, yo),
                                               direction=d, **kwa)
                            if res.statistics.utilization <= 1.02:
                                if (best_r is None or
                                    res.statistics.utilization > best_r.statistics.utilization):
                                    best_r, best_cfg = res, (pat, d, r, (xo, yo))

        if best_r is None:
            raise RuntimeError(f"Room {rs.name} no valid layout")

        # 局部精化：在最佳偏移附近细搜
        bx, by = best_cfg[3]  # best_cfg = (pat, direction, ratio, (xo, yo))
        fine_x = max(coarse_x / 4, 1.0)
        fine_y = max(coarse_y / 4, 1.0)
        for xo in _make_offsets(bx - coarse_x, L, fine_x, lo=bx - coarse_x, hi=bx + coarse_x):
            for yo in _make_offsets(by - coarse_y, W, fine_y, lo=by - coarse_y, hi=by + coarse_y):
                engine = ENGINES[best_cfg[0]]()
                kwa = {'board_gap': edges.board_gap, 'kerf': kerf}
                if best_cfg[2] is not None:
                    kwa['stagger_ratio'] = best_cfg[2]
                res = engine.layout(room_area, board,
                                   start_offset=(xo, yo),
                                   direction=best_cfg[1], **kwa)
                if res.statistics.utilization <= 1.02:
                    if res.statistics.utilization > best_r.statistics.utilization:
                        best_r = res
                        best_cfg = (best_cfg[0], best_cfg[1], best_cfg[2], (xo, yo))

        room_best.append((rs, best_cfg[0], best_cfg[1], best_cfg[2], best_cfg[3]))

    # Phase 2: independent totals as baseline
    independent_boards = []
    for rs, pat, d, r, offset in room_best:
        room_area = compute_layout_area(
            build_room(rs),
            edges.baseboard_width, edges.expansion_gap)
        kwa = {'board_gap': edges.board_gap, 'kerf': kerf}
        if r is not None:
            kwa['stagger_ratio'] = r
        res = ENGINES[pat]().layout(room_area, board,
                                    start_offset=offset, direction=d, **kwa)
        independent_boards.append(res.statistics.total_boards)

    # Phase 3: shared pool
    best_multi = None
    for perm in itertools.permutations(range(len(room_specs))):
        pool = BoardPool(L, kerf=kerf, board_width=W)
        results = []
        combined_area = 0.0
        label_start = 0
        prev_new_boards = 0

        for idx in perm:
            rs, pat, d, r, offset = room_best[idx]
            room_area = compute_layout_area(
                build_room(rs),
                edges.baseboard_width, edges.expansion_gap)
            kwa = {'board_gap': edges.board_gap, 'kerf': kerf,
                   'label_start': label_start}
            if r is not None:
                kwa['stagger_ratio'] = r

            prev_ids = set(pool._groups.keys())
            engine = ENGINES[pat]()
            res = engine.layout(room_area, board, pool=pool,
                              start_offset=offset, direction=d, **kwa)

            room_new = pool.total_new_boards - prev_new_boards
            prev_new_boards = pool.total_new_boards
            full_in_room = sum(1 for b in res.boards if not b.is_cut)
            room_total = room_new + full_in_room
            res.statistics.total_boards = room_total
            res.statistics.full_boards = full_in_room
            res.statistics.cut_boards = room_total - full_in_room

            room_group_ids = set(pool._groups.keys()) - prev_ids
            res.statistics.cutting_groups = [
                g for g in res.statistics.cutting_groups
                if g.source_id in room_group_ids
            ]
            reuse = {}
            for b in res.boards:
                g = pool._groups.get(b.source_id, {})
                parent = g.get('parent_source_id', '')
                if parent and parent in prev_ids:
                    reuse.setdefault(parent, []).append((b.label, b.length, b.width))
            res.reuse_info = reuse
            results.append((rs, res))
            combined_area += room_area.area
            label_start += len(res.boards)

        if len(results) != len(perm):
            continue

        total_boards = sum(rr[1].statistics.total_boards for rr in results)
        total_area = total_boards * L * W
        util = combined_area / total_area if total_area > 0 else 0

        if util <= 1.02 and (best_multi is None or total_boards < best_multi.total_boards):
            best_multi = MultiRoomResult(
                room_results=[(r[0], r[1]) for r in results],
                total_boards=total_boards,
                total_area=total_area,
                combined_room_area=combined_area,
                utilization=util)

    # Fallback: independent with shared numbering
    if best_multi is None or best_multi.total_boards > sum(independent_boards):
        pool = BoardPool(L, kerf=kerf, board_width=W)
        ind_results = []
        comb_area = 0.0
        label_start = 0
        prev_new_boards = 0
        prev_ids = set()
        total_n = 0
        for (rs, pat, d, r, offset), n_boards in zip(room_best, independent_boards):
            room_area = compute_layout_area(
                build_room(rs),
                edges.baseboard_width, edges.expansion_gap)
            kwa = {'board_gap': edges.board_gap, 'kerf': kerf,
                   'label_start': label_start}
            if r is not None:
                kwa['stagger_ratio'] = r
            res = ENGINES[pat]().layout(room_area, board, pool=pool,
                                        start_offset=offset, direction=d, **kwa)
            room_new = pool.total_new_boards - prev_new_boards
            prev_new_boards = pool.total_new_boards
            full_in_room = sum(1 for b in res.boards if not b.is_cut)
            room_total = room_new + full_in_room
            res.statistics.total_boards = room_total
            res.statistics.full_boards = full_in_room
            res.statistics.cut_boards = room_total - full_in_room
            room_group_ids = set(pool._groups.keys()) - prev_ids
            res.statistics.cutting_groups = [
                g for g in res.statistics.cutting_groups
                if g.source_id in room_group_ids
            ]
            reuse = {}
            for b in res.boards:
                g = pool._groups.get(b.source_id, {})
                parent = g.get('parent_source_id', '')
                if parent and parent in prev_ids:
                    reuse.setdefault(parent, []).append((b.label, b.length, b.width))
            res.reuse_info = reuse
            prev_ids = set(pool._groups.keys())
            ind_results.append((rs, res))
            comb_area += room_area.area
            label_start += len(res.boards)
            total_n += room_total

        total_a = total_n * L * W
        return MultiRoomResult(
            room_results=ind_results,
            total_boards=total_n,
            total_area=total_a,
            combined_room_area=comb_area,
            utilization=comb_area / total_a if total_a > 0 else 0)

    return best_multi


def _make_offsets(start: float, mod: float, step: float,
                  lo: float = None, hi: float = None) -> list:
    """生成偏移量列表。

    从 start 开始，对齐到 step 倍数，步进至 hi。
    若 lo 不为 None，过滤 < lo 的值。
    """
    if step <= 0:
        return [lo] if lo is not None else [0.0]
    aligned = start - (start % step)
    offsets = []
    x = aligned
    limit = hi if hi is not None else mod
    while x < limit + 0.5:
        if lo is None or x >= lo - 0.5:
            offsets.append(x)
        x += step
    if not offsets and lo is not None:
        offsets.append(lo)
    return offsets
