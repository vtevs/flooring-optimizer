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
                      LayoutStatistics, MultiRoomResult)
from .layout import ENGINES
from .layout.board_pool import BoardPool
from .geometry.room import build_room, compute_layout_area
from .corner_rule import (
    has_full_board_at_corner, has_full_board_at_room_corner, corner_offset,
)


def _room_corner(rs):
    """返回该房间要求的整板起始角（无要求返回 ""）。"""
    return getattr(rs, 'full_board_start_corner', '') or ""


def optimize_multi(room_specs, board, edges, kerf, installation=None, **kwargs):
    require_corner = bool(
        getattr(installation, 'require_full_board_at_room_corner', False)
    )
    require_bottom_left = bool(
        getattr(installation, 'require_full_board_at_room_bottom_left', False)
    )
    raw_material_type = kwargs.pop('material_type', 'wood')
    material_type = getattr(raw_material_type, 'value', raw_material_type)

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
        room_corner = _room_corner(rs)  # 房间级整板起始角（优先于全局配置）

        best_r, best_cfg = None, None
        for pat in patterns:
            for d in directions:
                for r in (stagger_ratios if pat == Pattern.STAGGERED else [None]):
                    engine = ENGINES[pat]()
                    kwa = {'board_gap': edges.board_gap, 'kerf': kerf, 'material_type': material_type}
                    if r is not None:
                        kwa['stagger_ratio'] = r

                    # 搜索偏移：从负值开始以覆盖铺装区边界对齐
                    offsets_x, offsets_y = _search_offsets(
                        room_area, edges, L, W, coarse_x, coarse_y,
                        require_bottom_left, require_corner, room_corner)

                    for xo in offsets_x:
                        for yo in offsets_y:
                            res = engine.layout(room_area, board,
                                               start_offset=(xo, yo),
                                               direction=d, **kwa)
                            if not _corner_ok(res, room_area, room_corner,
                                              require_corner, require_bottom_left):
                                continue
                            if res.statistics.utilization <= 1.02:
                                if (best_r is None or
                                    res.statistics.utilization > best_r.statistics.utilization):
                                    best_r, best_cfg = res, (pat, d, r, (xo, yo))

        if best_r is None:
            if require_corner or room_corner:
                raise RuntimeError(
                    f"Room {rs.name} no valid layout satisfying full-board corner rule"
                )
            raise RuntimeError(f"Room {rs.name} no valid layout")

        # 局部精化：在最佳偏移附近细搜
        bx, by = best_cfg[3]  # best_cfg = (pat, direction, ratio, (xo, yo))
        fine_x = max(coarse_x / 4, 1.0)
        fine_y = max(coarse_y / 4, 1.0)
        fine_offsets_x, fine_offsets_y = _fine_offsets(
            bx, by, coarse_x, coarse_y, fine_x, fine_y, L, W,
            room_area, edges,
            require_bottom_left, require_corner, room_corner)
        for xo in fine_offsets_x:
            for yo in fine_offsets_y:
                engine = ENGINES[best_cfg[0]]()
                kwa = {'board_gap': edges.board_gap, 'kerf': kerf, 'material_type': material_type}
                if best_cfg[2] is not None:
                    kwa['stagger_ratio'] = best_cfg[2]
                res = engine.layout(room_area, board,
                                   start_offset=(xo, yo),
                                   direction=best_cfg[1], **kwa)
                if not _corner_ok(res, room_area, room_corner,
                                  require_corner, require_bottom_left):
                    continue
                if res.statistics.utilization <= 1.02:
                    if res.statistics.utilization > best_r.statistics.utilization:
                        best_r = res
                        best_cfg = (best_cfg[0], best_cfg[1], best_cfg[2], (xo, yo))

        room_best.append((rs, best_cfg[0], best_cfg[1], best_cfg[2], best_cfg[3]))

    if getattr(board, 'stock_class_policy', '') == 'supplier-ab-vertical':
        return _optimize_supplier_ab_multi(
            room_best, board, edges, kerf, material_type,
        )

    # Phase 2: independent totals as baseline
    independent_boards = []
    for rs, pat, d, r, offset in room_best:
        room_area = compute_layout_area(
            build_room(rs),
            edges.baseboard_width, edges.expansion_gap)
        kwa = {'board_gap': edges.board_gap, 'kerf': kerf, 'material_type': material_type}
        if r is not None:
            kwa['stagger_ratio'] = r
        res = ENGINES[pat]().layout(room_area, board,
                                    start_offset=offset, direction=d, **kwa)
        independent_boards.append(res.statistics.total_boards)

    # Phase 3: shared pool
    best_multi = None
    for perm in itertools.permutations(range(len(room_specs))):
        pool = BoardPool(L, kerf=kerf, board_width=W, material_type=material_type)
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
                   'label_start': label_start, 'material_type': material_type}
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
        pool = BoardPool(L, kerf=kerf, board_width=W, material_type=material_type)
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
                   'label_start': label_start, 'material_type': material_type}
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


def _optimize_supplier_ab_multi(room_best, board, edges, kerf, material_type):
    """Evaluate room orders with one global physical A/B assignment."""
    from .stock_assignment import assign_supplier_stock

    L, W = board.length, board.width
    best = None
    best_score = None

    # Global source rematching considers every room's cut piece together, so
    # room processing order only changes IDs, not the feasible matching graph.
    for perm in [tuple(range(len(room_best)))]:
        pool = BoardPool(L, kerf=kerf, board_width=W,
                         material_type=material_type)
        results = []
        combined_area = 0.0
        label_start = 0

        for index in perm:
            rs, pattern, direction, ratio, offset = room_best[index]
            room_area = compute_layout_area(
                build_room(rs), edges.baseboard_width, edges.expansion_gap,
            )
            kwargs = {
                'board_gap': edges.board_gap,
                'kerf': kerf,
                'label_start': label_start,
                'material_type': material_type,
            }
            if ratio is not None:
                kwargs['stagger_ratio'] = ratio
            room_result = ENGINES[pattern]().layout(
                room_area, board, pool=pool, start_offset=offset,
                direction=direction, **kwargs,
            )
            for placed in room_result.boards:
                placed._room_key = rs.name
            results.append((rs, room_result))
            combined_area += room_area.area
            label_start += len(room_result.boards)

        final_groups = results[-1][1].statistics.cutting_groups
        all_boards = [placed for _, room_result in results
                      for placed in room_result.boards]
        initial_total = pool.total_new_boards + sum(
            1 for placed in all_boards if not placed.is_cut
        )
        combined = LayoutResult(
            boards=all_boards,
            statistics=LayoutStatistics(
                total_boards=initial_total,
                full_boards=sum(1 for placed in all_boards if not placed.is_cut),
                cut_boards=initial_total - sum(
                    1 for placed in all_boards if not placed.is_cut
                ),
                total_area=initial_total * L * W,
                room_area=combined_area,
                utilization=(combined_area / (initial_total * L * W)
                             if initial_total else 0),
                cutting_groups=final_groups,
            ),
            pattern=room_best[0][1],
        )
        errors = assign_supplier_stock(
            combined, board, board_gap=edges.board_gap, kerf=kerf,
        )
        if errors:
            continue

        groups_by_source = {
            group.source_id: group
            for group in combined.statistics.cutting_groups
        }
        seen_roots = set()
        for _, room_result in results:
            labels = {str(placed.label) for placed in room_result.boards}
            room_groups = [
                group for group in combined.statistics.cutting_groups
                if any(str(piece.label) in labels for piece in group.pieces)
            ]
            room_roots = {group.root_source_id for group in room_groups}
            new_roots = room_roots - seen_roots
            room_result.statistics.cutting_groups = room_groups
            room_result.statistics.total_boards = len(new_roots)
            room_result.statistics.full_boards = sum(
                1 for placed in room_result.boards
                if not placed.is_cut
                and groups_by_source[placed.source_id].root_source_id in new_roots
            )
            room_result.statistics.cut_boards = max(
                0,
                room_result.statistics.total_boards
                - room_result.statistics.full_boards,
            )
            room_counts = {'A': 0, 'B': 0}
            for root in new_roots:
                group = next(g for g in room_groups
                             if g.root_source_id == root)
                room_counts[group.stock_class] += 1
            room_result.statistics.stock_counts = room_counts
            room_result.statistics.purchase_boards = 2 * max(
                room_counts.values(), default=0,
            )
            reuse = {}
            for placed in room_result.boards:
                group = groups_by_source[placed.source_id]
                if group.root_source_id in seen_roots:
                    reuse.setdefault(group.root_source_id, []).append(
                        (placed.label, placed.length, placed.width)
                    )
            room_result.reuse_info = reuse
            seen_roots.update(room_roots)

        score = (
            combined.statistics.purchase_boards,
            combined.statistics.total_boards,
        )
        if best is None or score < best_score:
            best_score = score
            best = MultiRoomResult(
                room_results=results,
                shared_pool_groups=combined.statistics.cutting_groups,
                total_boards=combined.statistics.total_boards,
                total_area=combined.statistics.total_area,
                combined_room_area=combined_area,
                utilization=combined.statistics.utilization,
                stock_counts=combined.statistics.stock_counts,
                purchase_boards=combined.statistics.purchase_boards,
            )

    if best is None:
        raise RuntimeError("多房间方案无法满足供应商 A/B 严格物理约束")
    return best


def _corner_ok(res, room_area, room_corner, require_corner, require_bottom_left):
    """判断一个排样结果是否满足整板起始角约束。"""
    if require_bottom_left:
        return has_full_board_at_corner(res, room_area, 'bottom-left')
    if room_corner:
        return has_full_board_at_corner(res, room_area, room_corner)
    if require_corner:
        return has_full_board_at_room_corner(res, room_area)
    return True


def _corner_candidates(room_area, edges, room_corner, require_corner,
                       require_bottom_left, L, W):
    """按整板起始角需求生成候选偏移列表 (list[(xo, yo)])。"""
    pitch = W + edges.board_gap
    if require_bottom_left:
        return corner_offset('bottom-left', room_area.bounds, L, W, pitch)
    if room_corner:
        return corner_offset(room_corner, room_area.bounds, L, W, pitch)
    if require_corner:
        # 任意角：尝试每个角落
        offs = []
        for c in ('bottom-left', 'top-left', 'top-right', 'bottom-right'):
            offs.extend(corner_offset(c, room_area.bounds, L, W, pitch))
        return offs
    return None


def _search_offsets(room_area, edges, L, W, coarse_x, coarse_y,
                    require_bottom_left, require_corner, room_corner):
    """生成粗搜索的偏移 X/Y 列表。"""
    if require_bottom_left or room_corner or require_corner:
        cands = _corner_candidates(room_area, edges, room_corner,
                                   require_corner, require_bottom_left, L, W)
        xs = [c[0] for c in cands]
        ys = [c[1] for c in cands]
        return xs, ys
    offsets_x = _make_offsets(-coarse_x, L, coarse_x, lo=-coarse_x, hi=L)
    offsets_y = _make_offsets(-coarse_y, W, coarse_y, lo=-coarse_y, hi=W)
    return offsets_x, offsets_y


def _fine_offsets(bx, by, coarse_x, coarse_y, fine_x, fine_y, L, W,
                  room_area, edges,
                  require_bottom_left, require_corner, room_corner):
    """生成局部精化的偏移 X/Y 列表。"""
    if require_bottom_left or room_corner or require_corner:
        cands = _corner_candidates(room_area, edges, room_corner,
                                   require_corner, require_bottom_left, L, W)
        xs = [c[0] for c in cands]
        ys = [c[1] for c in cands]
        return xs, ys
    fine_offsets_x = _make_offsets(bx - coarse_x, L, fine_x, lo=bx - coarse_x, hi=bx + coarse_x)
    fine_offsets_y = _make_offsets(by - coarse_y, W, fine_y, lo=by - coarse_y, hi=by + coarse_y)
    return fine_offsets_x, fine_offsets_y


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


def _include_values(values, required, lo, hi):
    result = list(values)
    for value in required:
        if lo - 0.5 <= value < hi + 0.5 and not any(abs(value - x) <= 1e-6 for x in result):
            result.append(value)
    return sorted(result)
