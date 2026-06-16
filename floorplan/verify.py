"""
输出校验模块 — 铺装宪法第五条

验证：
1. 切割操作完整性 — 每次操作的 pieces + 废料 + 锯缝 = 原料尺寸
2. 铺装覆盖率 — 铺装板覆盖整个可铺区域，且不超出房间
"""

from collections import defaultdict
from shapely.geometry import Polygon, box as sbox
from shapely import affinity
from shapely.ops import unary_union

from .models import LayoutResult, MultiRoomResult, Config
from .geometry.room import build_room, compute_layout_area


def verify_layout(result: LayoutResult, config: Config) -> list[str]:
    errors = []
    errors.extend(_verify_cutting_ops(result, config))
    errors.extend(_verify_edges(result, config))
    errors.extend(_verify_coverage(result, config))
    return errors


def _verify_edges(result: LayoutResult, config: Config,
                  room_label: str = "") -> list[str]:
    """逐边证明内部邻边可以完成公母榫对接。"""
    errors, _ = verify_edge_details(result, config, room_label=room_label)
    return errors


def verify_edge_details(result: LayoutResult, config: Config,
                        room_label: str = "") -> tuple[list[str], dict]:
    """返回公母榫逐边校验错误和摘要。

    校验模型：先从几何识别内部邻边；切割边若落在内部邻边则失败；
    其余原始边按实物基准左=G、右=T、下=G、上=T，
    每块板允许俯视图 0/90/180/270 四种旋转，证明所有内部邻边都存在 T/G 配对。
    """
    errors = []
    prefix = f"[{room_label}] " if room_label else ""
    gap = getattr(config.edges, 'board_gap', 0.0)
    gap_tol = max(0.75, gap * 0.75)
    coord_tol = max(0.5, gap_tol)

    segments = []
    board_orientation = {}
    for index, b in enumerate(result.boards):
        key = str(b.label)
        poly = _board_used_polygon(b)
        full = _board_full_polygon(b)
        cut_sides = _cut_sides(full, poly, coord_tol)
        board_orientation[key] = _board_orientation_kind(b)
        segments.extend(_axis_aligned_edge_segments(poly, key, cut_sides, coord_tol))

    adjacencies = []
    seen = set()
    for i, a in enumerate(segments):
        for b in segments[i + 1:]:
            if not _are_neighbor_edges(a, b, gap, gap_tol):
                continue
            key = tuple(sorted((a['label'], b['label']))) + tuple(sorted((a['side'], b['side'])))
            if key in seen:
                continue
            seen.add(key)
            adjacencies.append((a, b))

    constraints = []
    cut_failures = 0
    for a, b in adjacencies:
        if a['is_cut'] or b['is_cut']:
            cut_failures += 1
            errors.append(_cut_neighbor_error(a, b, prefix))
            continue
        allowed = []
        for sa in range(4):
            for sb in range(4):
                ea = _edge_type_for_side(board_orientation[a['label']], sa, a['side'])
                eb = _edge_type_for_side(board_orientation[b['label']], sb, b['side'])
                if ea != eb:
                    allowed.append((sa, sb))
        if not allowed:
            errors.append(_no_tg_assignment_error(a, b, prefix))
        else:
            constraints.append((a['label'], b['label'], allowed, a, b))

    assignment, conflict = _solve_orientation_constraints(constraints)
    if conflict:
        a, b = conflict
        errors.append(
            f"{prefix}位{a['label']} {a['side']} ↔ 位{b['label']} {b['side']}: "
            "无法同时满足公母榫方向约束"
        )

    summary = dict(
        boards=len(result.boards),
        edge_segments=len(segments),
        internal_edges=len(adjacencies),
        cut_internal_edges=cut_failures,
        constrained_edges=len(constraints),
        assigned_boards=len(assignment),
        errors=len(errors),
    )
    return errors, summary


def verify_multi(multi_result: MultiRoomResult, config: Config) -> list[str]:
    errors = []
    for rs, room_result in multi_result.room_results:
        errors.extend(_verify_cutting_ops(room_result, config, room_label=rs.name))
        errors.extend(_verify_edges(room_result, config, room_label=rs.name))
        errors.extend(_verify_coverage(room_result, config, room_label=rs.name,
                                       room_width=rs.width, room_length=rs.length))
    return errors


def _board_full_polygon(b):
    L, W = b.length, b.width
    x0, y0 = b.x - L / 2, b.y - W / 2
    bp = sbox(x0, y0, x0 + L, y0 + W)
    if b.rotation and abs(b.rotation) > 0.1:
        bp = affinity.rotate(bp, b.rotation, origin=(b.x, b.y))
    return bp


def _board_used_polygon(b):
    if b.is_cut and b.cut_polygon:
        return Polygon(b.cut_polygon)
    return _board_full_polygon(b)


def _board_orientation_kind(b):
    rotation = b.rotation or 0
    if abs(rotation - 90) < 0.1 or (abs(rotation) < 0.1 and b.width > b.length):
        return 'vertical'
    return 'horizontal'


def _cut_sides(full, used, tol):
    fminx, fminy, fmaxx, fmaxy = full.bounds
    uminx, uminy, umaxx, umaxy = used.bounds
    return {
        'left': uminx > fminx + tol,
        'right': umaxx < fmaxx - tol,
        'bottom': uminy > fminy + tol,
        'top': umaxy < fmaxy - tol,
    }


def _axis_aligned_edge_segments(poly, label, cut_sides, tol):
    minx, miny, maxx, maxy = poly.bounds
    out = []
    coords = list(poly.exterior.coords)
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        if abs(x1 - x2) <= tol:
            y0, y3 = sorted((y1, y2))
            if y3 - y0 <= tol:
                continue
            if abs(x1 - minx) <= tol:
                side = 'left'
            elif abs(x1 - maxx) <= tol:
                side = 'right'
            else:
                continue
            out.append(dict(label=label, axis='v', side=side, const=(x1 + x2) / 2,
                            start=y0, end=y3, is_cut=cut_sides.get(side, False)))
        elif abs(y1 - y2) <= tol:
            x0, x3 = sorted((x1, x2))
            if x3 - x0 <= tol:
                continue
            if abs(y1 - miny) <= tol:
                side = 'bottom'
            elif abs(y1 - maxy) <= tol:
                side = 'top'
            else:
                continue
            out.append(dict(label=label, axis='h', side=side, const=(y1 + y2) / 2,
                            start=x0, end=x3, is_cut=cut_sides.get(side, False)))
    return out


def _are_neighbor_edges(a, b, gap, gap_tol):
    if a['label'] == b['label'] or a['axis'] != b['axis']:
        return False
    opposite = {('left', 'right'), ('right', 'left'),
                ('top', 'bottom'), ('bottom', 'top')}
    if (a['side'], b['side']) not in opposite:
        return False
    distance = abs(a['const'] - b['const'])
    if abs(distance - gap) > gap_tol:
        return False
    overlap = min(a['end'], b['end']) - max(a['start'], b['start'])
    return overlap > max(1.0, gap_tol)


def _edge_type_for_side(kind, state, side):
    from .models import EdgeType

    # Confirmed physical board orientation, face up, no flipping:
    # state 0 = left=GROOVE, right=TONGUE, bottom=GROOVE, top=TONGUE.
    rotations = {
        # 0°
        0: dict(left=EdgeType.GROOVE, right=EdgeType.TONGUE,
                bottom=EdgeType.GROOVE, top=EdgeType.TONGUE),
        # 90° in plan view
        1: dict(left=EdgeType.TONGUE, right=EdgeType.GROOVE,
                bottom=EdgeType.GROOVE, top=EdgeType.TONGUE),
        # 180°
        2: dict(left=EdgeType.TONGUE, right=EdgeType.GROOVE,
                bottom=EdgeType.TONGUE, top=EdgeType.GROOVE),
        # 270° in plan view
        3: dict(left=EdgeType.GROOVE, right=EdgeType.TONGUE,
                bottom=EdgeType.TONGUE, top=EdgeType.GROOVE),
    }
    return rotations[state][side]


def _solve_orientation_constraints(constraints):
    variables = set()
    neighbors = {}
    constraint_map = {}
    conflict_by_pair = {}
    for a, b, allowed, seg_a, seg_b in constraints:
        variables.update((a, b))
        neighbors.setdefault(a, set()).add(b)
        neighbors.setdefault(b, set()).add(a)
        constraint_map[(a, b)] = set(allowed)
        constraint_map[(b, a)] = {(y, x) for x, y in allowed}
        conflict_by_pair[(a, b)] = (seg_a, seg_b)
        conflict_by_pair[(b, a)] = (seg_b, seg_a)

    domains = {v: set(range(4)) for v in variables}
    ok, conflict = _enforce_arc_consistency(domains, neighbors, constraint_map, conflict_by_pair)
    if not ok:
        return {}, conflict

    assignment = _backtrack_orientation({}, domains, neighbors, constraint_map)
    if assignment is None:
        conflict = _first_unsatisfied_constraint({}, constraints)
        return {}, conflict
    return assignment, None


def _enforce_arc_consistency(domains, neighbors, constraint_map, conflict_by_pair):
    queue = [(a, b) for a in neighbors for b in neighbors[a]]
    while queue:
        a, b = queue.pop(0)
        allowed = constraint_map[(a, b)]
        removed = set()
        for va in domains[a]:
            if not any((va, vb) in allowed for vb in domains[b]):
                removed.add(va)
        if not removed:
            continue
        domains[a] -= removed
        if not domains[a]:
            return False, conflict_by_pair[(a, b)]
        for c in neighbors.get(a, set()):
            if c != b:
                queue.append((c, a))
    return True, None


def _backtrack_orientation(assignment, domains, neighbors, constraint_map):
    if len(assignment) == len(domains):
        return dict(assignment)

    var = min((v for v in domains if v not in assignment),
              key=lambda v: len(domains[v]))
    for value in sorted(domains[var]):
        if not _orientation_value_consistent(var, value, assignment, constraint_map):
            continue
        new_assignment = dict(assignment)
        new_assignment[var] = value
        new_domains = {k: set(v) for k, v in domains.items()}
        new_domains[var] = {value}
        ok, _ = _enforce_arc_consistency(new_domains, neighbors, constraint_map, {})
        if not ok:
            continue
        solved = _backtrack_orientation(new_assignment, new_domains, neighbors, constraint_map)
        if solved is not None:
            return solved
    return None


def _orientation_value_consistent(var, value, assignment, constraint_map):
    for other, other_value in assignment.items():
        allowed = constraint_map.get((var, other))
        if allowed is not None and (value, other_value) not in allowed:
            return False
    return True


def _first_unsatisfied_constraint(assignment, constraints):
    for a, b, allowed, seg_a, seg_b in constraints:
        if a in assignment and b in assignment and (assignment[a], assignment[b]) not in allowed:
            return seg_a, seg_b
    if constraints:
        return constraints[0][3], constraints[0][4]
    return None


def _cut_neighbor_error(a, b, prefix):
    return (
        f"{prefix}位{a['label']} {a['side']} ↔ 位{b['label']} {b['side']}: "
        "内部邻边出现切割边"
    )


def _no_tg_assignment_error(a, b, prefix):
    return (
        f"{prefix}位{a['label']} {a['side']} ↔ 位{b['label']} {b['side']}: "
        "公母榫不匹配"
    )


def _verify_cutting_ops(result: LayoutResult, config: Config,
                        room_label: str = "") -> list[str]:
    """校验每次切割操作：pieces + waste + kerf = 原料尺寸"""
    errors = []
    bw = config.board.width
    kerf = config.kerf
    prefix = f"[{room_label}] " if room_label else ""

    for cg in result.statistics.cutting_groups:
        total_l = cg.total_length
        total_w = cg.total_width if cg.total_width > 0 else bw
        pieces = cg.pieces
        n = len(pieces)
        used_l = cg.used_length
        waste_l = cg.waste_length
        width_waste = cg.width_waste

        # 面积法校验
        pieces_area = sum(p.length * (p.width if p.width > 0 else bw) for p in pieces)
        has_width = width_waste > 10
        has_length_waste = waste_l > 0.5

        # 锯缝面积
        kerf_area = 0
        if has_width:
            kerf_area += kerf * total_l  # 宽切锯缝
        if has_length_waste or n > 1:
            n_cuts = n if has_length_waste else max(0, n - 1)
            kerf_area += n_cuts * kerf * total_w

        # 废料面积
        waste_area = waste_l * total_w + width_waste
        total = pieces_area + waste_area + kerf_area
        expected = total_l * total_w

        if expected > 0 and abs(total - expected) > expected * 0.1:  # 10% 容差
            pct = (total - expected) / expected * 100
            errors.append(
                f"{prefix}{cg.source_id}: 面积不匹配 "
                f"(片{pieces_area:.0f}+废{waste_area:.0f}+锯{kerf_area:.0f}"
                f"={total:.0f}≠{expected:.0f} {pct:+.1f}%)")

    return errors


def _verify_coverage(result: LayoutResult, config: Config,
                     room_label: str = "",
                     room_width: float = None, room_length: float = None
                     ) -> list[str]:
    """校验铺装板覆盖整个可铺区域且不超出房间"""
    errors = []
    prefix = f"[{room_label}] " if room_label else ""

    if room_label and config.rooms:
        room_spec = next((r for r in config.rooms if r.name == room_label), None)
        room = build_room(room_spec) if room_spec is not None else sbox(0, 0, room_width, room_length)
    elif room_width is not None and room_length is not None:
        room = sbox(0, 0, room_width, room_length)
    else:
        room = build_room(config.room)

    layout_area = compute_layout_area(room, config.edges.baseboard_width,
                                      config.edges.expansion_gap)

    boards_polys = []
    for b in result.boards:
        L, W = b.length, b.width
        x0, y0 = b.x - L/2, b.y - W/2
        bp = sbox(x0, y0, x0 + L, y0 + W)
        if b.rotation and abs(b.rotation) > 0.1:
            bp = affinity.rotate(bp, b.rotation, origin=(b.x, b.y))
        if b.is_cut and b.cut_polygon:
            bp = Polygon(b.cut_polygon)
        boards_polys.append(bp)

    if not boards_polys:
        return [f"{prefix}无铺装板"]

    covered = unary_union(boards_polys)

    outside = covered.difference(room.buffer(1.0))
    if outside.area > room.area * 0.005:
        errors.append(f"{prefix}铺装超出房间边界 {outside.area/1e6:.4f} m²")

    uncovered = layout_area.difference(covered.buffer(0.5))
    if uncovered.area > layout_area.area * 0.005:
        errors.append(
            f"{prefix}可铺区域未完全覆盖 — "
            f"遗漏 {uncovered.area/1e6:.4f} m²")

    if layout_area.area > 0:
        coverage = covered.intersection(layout_area).area / layout_area.area
        if coverage < 0.99:
            errors.append(f"{prefix}覆盖率不足: {coverage*100:.1f}%")

    return errors
