"""Strict physical assignment for supplier A/B boards."""

from collections import deque
from dataclasses import dataclass

from shapely.geometry import Polygon, box as sbox

from .models import BoardEdges, EdgeType
from .stock import orientation_for_rotation, rotate_board_edges, supplier_edges


@dataclass(frozen=True)
class PlacementState:
    stock_class: str
    rotation: int
    edges: BoardEdges
    layout_id: int = 0
    source_x: float = 0.0
    source_y: float = 0.0


def _maximum_compatible_pairs(labels, compatible):
    """Return a maximum-cardinality matching of physically compatible pieces."""
    import networkx as nx

    graph = nx.Graph()
    graph.add_nodes_from(labels)
    for index, left in enumerate(labels):
        for right in labels[index + 1:]:
            if compatible(left, right):
                graph.add_edge(left, right)
    return list(nx.max_weight_matching(graph, maxcardinality=True))


def _full_polygon(board):
    return sbox(
        board.x - board.length / 2,
        board.y - board.width / 2,
        board.x + board.length / 2,
        board.y + board.width / 2,
    )


def _used_polygon(board):
    if board.is_cut and board.cut_polygon:
        return Polygon(board.cut_polygon)
    return _full_polygon(board)


def _cut_sides(full, used, tolerance=0.5):
    fminx, fminy, fmaxx, fmaxy = full.bounds
    uminx, uminy, umaxx, umaxy = used.bounds
    return {
        "left": uminx > fminx + tolerance,
        "right": umaxx < fmaxx - tolerance,
        "bottom": uminy > fminy + tolerance,
        "top": umaxy < fmaxy - tolerance,
    }


def _source_piece_edges(piece, board, stock_class, tolerance=1e-6,
                        source_x=None, source_y=None):
    original = supplier_edges(stock_class, 0)
    source_width = piece.source_width or piece.width or board.width
    source_length = piece.source_length or piece.length
    source_x = piece.source_x if source_x is None else source_x
    source_y = piece.source_y if source_y is None else source_y
    return BoardEdges(
        top=(original.top if source_y + source_length >= board.length - tolerance
             else EdgeType.CUT),
        right=(original.right if source_x + source_width >= board.width - tolerance
               else EdgeType.CUT),
        bottom=(original.bottom if source_y <= tolerance else EdgeType.CUT),
        left=(original.left if source_x <= tolerance else EdgeType.CUT),
    )


def _placement_orientation(board):
    return "vertical" if board.width > board.length else "horizontal"


def _placement_states_for_rect(placed_board, piece, board_config,
                               source_x, source_y, layout_id):
    used = _used_polygon(placed_board)
    minx, miny, maxx, maxy = used.bounds
    physical_width = maxx - minx
    physical_height = maxy - miny
    required_cut = _cut_sides(_full_polygon(placed_board), used)
    orientation = _placement_orientation(placed_board)
    source_width = piece.source_width or piece.width or board_config.width
    source_length = piece.source_length or piece.length
    tolerance = 1.0

    states = []
    for stock_class in ("A", "B"):
        source_edges = _source_piece_edges(
            piece, board_config, stock_class,
            source_x=source_x, source_y=source_y,
        )
        for rotation in (0, 90, 180, 270):
            if orientation_for_rotation(rotation) != orientation:
                continue
            expected_width = source_width if rotation % 180 == 0 else source_length
            expected_height = source_length if rotation % 180 == 0 else source_width
            if (abs(expected_width - physical_width) > tolerance or
                    abs(expected_height - physical_height) > tolerance):
                continue
            physical_edges = rotate_board_edges(source_edges, rotation)
            if any(
                (getattr(physical_edges, side) == EdgeType.CUT) != required_cut[side]
                for side in ("top", "right", "bottom", "left")
            ):
                continue
            states.append(PlacementState(
                stock_class, rotation, physical_edges,
                layout_id=layout_id, source_x=source_x, source_y=source_y,
            ))
    return states


def _source_polygon_for_state(placed_board, piece, state):
    """Map the installed cut polygon back into root source-board coordinates."""
    used = _used_polygon(placed_board)
    minx, miny, _, _ = used.bounds
    source_width = piece.source_width or piece.width
    source_length = piece.source_length or piece.length
    rotation = state.rotation % 360
    source_coords = []
    for physical_x, physical_y in used.exterior.coords:
        x = physical_x - minx
        y = physical_y - miny
        if rotation == 0:
            source_x, source_y = x, y
        elif rotation == 90:
            source_x, source_y = y, source_length - x
        elif rotation == 180:
            source_x, source_y = source_width - x, source_length - y
        else:  # 270
            source_x, source_y = source_width - y, x
        source_coords.append((
            state.source_x + source_x,
            state.source_y + source_y,
        ))
    return source_coords


def placement_states(placed_board, piece, board_config) -> list[PlacementState]:
    """Return physical states for the piece's currently recorded source rect."""
    return _placement_states_for_rect(
        placed_board, piece, board_config,
        piece.source_x, piece.source_y, 0,
    )


def _corner_positions(piece, board_config):
    width = piece.source_width or piece.width or board_config.width
    length = piece.source_length or piece.length
    xs = [0.0]
    ys = [0.0]
    if width < board_config.width - 0.5:
        xs.append(board_config.width - width)
    if length < board_config.length - 0.5:
        ys.append(board_config.length - length)
    return [(x, y) for x in xs for y in ys]


def _rectangles_separated(first, second, kerf, tolerance=1e-6):
    ax, ay, aw, al = first
    bx, by, bw, bl = second
    horizontal = (ax + aw + kerf <= bx + tolerance or
                  bx + bw + kerf <= ax + tolerance)
    vertical = (ay + al + kerf <= by + tolerance or
                by + bl + kerf <= ay + tolerance)
    return horizontal or vertical


def _root_layouts(labels, pieces, board_config, kerf):
    """Enumerate corner-anchored, non-overlapping source-board layouts."""
    if len(labels) > 2:
        return []
    choices = []
    for label in labels:
        piece = pieces[label]
        width = piece.source_width or piece.width or board_config.width
        length = piece.source_length or piece.length
        choices.append([
            (x, y, width, length) for x, y in _corner_positions(piece, board_config)
        ])
    if len(labels) == 1:
        return [{labels[0]: rect} for rect in choices[0]]
    layouts = []
    for first in choices[0]:
        for second in choices[1]:
            if _rectangles_separated(first, second, kerf):
                layouts.append({labels[0]: first, labels[1]: second})
    return layouts


def _edge_segments(poly, label, room_key="", tolerance=0.5):
    minx, miny, maxx, maxy = poly.bounds
    out = []
    coords = list(poly.exterior.coords)
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        if abs(x1 - x2) <= tolerance:
            start, end = sorted((y1, y2))
            if end - start <= tolerance:
                continue
            side = "left" if abs(x1 - minx) <= tolerance else (
                "right" if abs(x1 - maxx) <= tolerance else ""
            )
            if side:
                out.append((label, "v", side, (x1 + x2) / 2,
                            start, end, room_key))
        elif abs(y1 - y2) <= tolerance:
            start, end = sorted((x1, x2))
            if end - start <= tolerance:
                continue
            side = "bottom" if abs(y1 - miny) <= tolerance else (
                "top" if abs(y1 - maxy) <= tolerance else ""
            )
            if side:
                out.append((label, "h", side, (y1 + y2) / 2,
                            start, end, room_key))
    return out


def _adjacencies(boards, gap):
    segments = []
    for board in boards:
        segments.extend(_edge_segments(
            _used_polygon(board), str(board.label),
            getattr(board, '_room_key', ''),
        ))
    opposite = {("left", "right"), ("right", "left"),
                ("top", "bottom"), ("bottom", "top")}
    tolerance = max(0.75, gap * 0.75)
    result = []
    seen = set()
    for index, a in enumerate(segments):
        for b in segments[index + 1:]:
            if a[6] and b[6] and a[6] != b[6]:
                continue
            if a[0] == b[0] or a[1] != b[1] or (a[2], b[2]) not in opposite:
                continue
            if abs(abs(a[3] - b[3]) - gap) > tolerance:
                continue
            if min(a[5], b[5]) - max(a[4], b[4]) <= max(1.0, tolerance):
                continue
            key = tuple(sorted((a[0], b[0]))) + tuple(sorted((a[2], b[2])))
            if key not in seen:
                seen.add(key)
                result.append((a[0], a[2], b[0], b[2]))
    return result


def _add_constraint(allowed, a, b, pairs):
    key = (a, b)
    reverse = (b, a)
    values = set(pairs)
    reverse_values = {(right, left) for left, right in values}
    allowed[key] = values if key not in allowed else allowed[key] & values
    allowed[reverse] = (reverse_values if reverse not in allowed
                        else allowed[reverse] & reverse_values)


def _arc_consistency_with_conflict(domains, neighbors, allowed):
    queue = deque((a, b) for a in neighbors for b in neighbors[a])
    while queue:
        a, b = queue.popleft()
        valid = allowed[(a, b)]
        reduced = {
            va for va in domains[a]
            if any((va, vb) in valid for vb in domains[b])
        }
        if reduced == domains[a]:
            continue
        if not reduced:
            return False, (a, b)
        domains[a] = reduced
        for other in neighbors[a] - {b}:
            queue.append((other, a))
    return True, None


def _arc_consistency(domains, neighbors, allowed):
    ok, _ = _arc_consistency_with_conflict(domains, neighbors, allowed)
    return ok


def _solve(domains, neighbors, allowed, roots):
    def search(current_domains, assignment, root_classes):
        if len(assignment) == len(current_domains):
            return assignment
        label = min(
            (key for key in current_domains if key not in assignment),
            key=lambda key: len(current_domains[key]),
        )
        counts = {"A": 0, "B": 0}
        for value in root_classes.values():
            counts[value] += 1
        values = sorted(
            current_domains[label],
            key=lambda state: (counts[state.stock_class], state.stock_class,
                               state.rotation),
        )
        for state in values:
            root = roots[label]
            existing_class = root_classes.get(root)
            if existing_class and existing_class != state.stock_class:
                continue
            if any(
                other in assignment and
                (state, assignment[other]) not in allowed[(label, other)]
                for other in neighbors[label]
            ):
                continue
            next_domains = {key: set(value) for key, value in current_domains.items()}
            next_domains[label] = {state}
            if not _arc_consistency(next_domains, neighbors, allowed):
                continue
            next_assignment = dict(assignment)
            next_assignment[label] = state
            next_root_classes = dict(root_classes)
            next_root_classes[root] = state.stock_class
            solved = search(next_domains, next_assignment, next_root_classes)
            if solved is not None:
                return solved
        return None

    return search(domains, {}, {})


def _attempt_assignment(result, pieces, roots, board_config, board_gap, kerf):
    boards_by_label = {str(board.label): board for board in result.boards}
    by_root = {}
    for label, root in roots.items():
        by_root.setdefault(root, []).append(label)

    domains = {label: set() for label in boards_by_label}
    errors = []
    for root, labels in by_root.items():
        if any(label not in pieces for label in labels):
            errors.append(f"{root}: 缺少源板切割记录")
            continue
        layouts = _root_layouts(labels, pieces, board_config, kerf)
        for layout_id, layout in enumerate(layouts):
            for label, (source_x, source_y, _, _) in layout.items():
                domains[label].update(_placement_states_for_rect(
                    boards_by_label[label], pieces[label], board_config,
                    source_x, source_y, layout_id,
                ))
        for label in labels:
            if not domains[label]:
                errors.append(f"位{label}: 源板切割边无法对应铺装裁切边")
    if errors:
        return None, errors, None

    neighbors = {label: set() for label in domains}
    allowed = {}
    for left, left_side, right, right_side in _adjacencies(result.boards, board_gap):
        pairs = {
            (a, b) for a in domains[left] for b in domains[right]
            if getattr(a.edges, left_side) != EdgeType.CUT
            and getattr(b.edges, right_side) != EdgeType.CUT
            and getattr(a.edges, left_side) != getattr(b.edges, right_side)
        }
        _add_constraint(allowed, left, right, pairs)
        neighbors[left].add(right)
        neighbors[right].add(left)

    for labels in by_root.values():
        for index, left in enumerate(labels):
            for right in labels[index + 1:]:
                pairs = {
                    (a, b) for a in domains[left] for b in domains[right]
                    if (a.stock_class == b.stock_class and
                        a.layout_id == b.layout_id)
                }
                _add_constraint(allowed, left, right, pairs)
                neighbors[left].add(right)
                neighbors[right].add(left)

    arc_ok, conflict = _arc_consistency_with_conflict(
        domains, neighbors, allowed,
    )
    if not arc_ok:
        return (None,
                ["A/B 板型、切割继承和邻边约束无法同时满足"],
                conflict)
    assignment = _solve(domains, neighbors, allowed, roots)
    if assignment is None:
        return (None,
                ["A/B 板型、切割继承和邻边约束无法同时满足"],
                None)
    return assignment, [], None


def _compatible_reuse_options(labels, pieces, boards_by_label, board_config,
                              kerf, assignment):
    """Return A/B source layouts that preserve every proved physical edge."""
    options_by_class = {}
    layouts = _root_layouts(labels, pieces, board_config, kerf)
    for layout_id, layout in enumerate(layouts):
        options = {}
        for label, (source_x, source_y, _, _) in layout.items():
            options[label] = [
                state for state in _placement_states_for_rect(
                    boards_by_label[label], pieces[label], board_config,
                    source_x, source_y, layout_id,
                )
                if state.edges == assignment[label].edges
            ]
        for stock_class in ('A', 'B'):
            selected = {}
            for label in labels:
                match = next(
                    (state for state in options[label]
                     if state.stock_class == stock_class),
                    None,
                )
                if match is None:
                    break
                selected[label] = match
            if len(selected) == len(labels):
                options_by_class.setdefault(stock_class, selected)
    return options_by_class


def _repack_independent_sources(result, pieces, operation_sources,
                                board_config, kerf, assignment):
    """Maximize two-piece source reuse without changing proved room edges."""
    boards_by_label = {str(board.label): board for board in result.boards}
    labels = list(boards_by_label)
    eligible = [
        label for label in labels
        if ((pieces[label].source_width or pieces[label].width or board_config.width)
            < board_config.width - 0.5
            or (pieces[label].source_length or pieces[label].length)
            < board_config.length - 0.5)
    ]
    option_cache = {}

    def options_for(left, right):
        key = frozenset((left, right))
        if key not in option_cache:
            ordered = sorted(key, key=lambda label: labels.index(label))
            option_cache[key] = _compatible_reuse_options(
                ordered, pieces, boards_by_label, board_config, kerf,
                assignment,
            )
        return option_cache[key]

    pairs = _maximum_compatible_pairs(
        eligible,
        lambda left, right: bool(options_for(left, right)),
    )
    paired = {label for pair in pairs for label in pair}
    units = []
    for pair in pairs:
        unit_labels = sorted(pair, key=lambda label: labels.index(label))
        units.append((unit_labels, options_for(*unit_labels)))
    for label in labels:
        if label in paired:
            continue
        options = _compatible_reuse_options(
            [label], pieces, boards_by_label, board_config, kerf,
            assignment,
        )
        units.append(([label], options))

    roots = {}
    counts = {'A': 0, 'B': 0}
    selected_units = []
    for unit_labels, options in units:
        if len(options) == 1:
            stock_class = next(iter(options))
            selected_units.append((unit_labels, options, stock_class))
            counts[stock_class] += 1
    for unit_labels, options in units:
        if len(options) == 1:
            continue
        stock_class = min(options, key=lambda value: (counts[value], value))
        selected_units.append((unit_labels, options, stock_class))
        counts[stock_class] += 1

    for unit_labels, options, stock_class in selected_units:
        root = operation_sources[unit_labels[0]]
        for label in unit_labels:
            roots[label] = root
            assignment[label] = options[stock_class][label]
    return roots, assignment


def assign_supplier_stock(result, board_config, board_gap=0.0,
                          kerf=0.0) -> list[str]:
    """Assign and record one physically realizable A/B state per placement."""
    groups = {group.source_id: group
              for group in (result.statistics.cutting_groups or [])}
    pieces = {}
    original_roots = {}
    operation_sources = {}
    for group in groups.values():
        root = group.root_source_id or group.source_id.split('-')[0]
        for piece in group.pieces:
            label = str(piece.label)
            pieces[label] = piece
            original_roots[label] = root
            operation_sources[label] = group.source_id

    candidates = []
    original_assignment, original_errors, _ = _attempt_assignment(
        result, pieces, original_roots, board_config, board_gap, kerf,
    )
    if original_assignment is not None:
        candidates.append((dict(original_roots), original_assignment))

    independent_roots = dict(operation_sources)
    independent_assignment, independent_errors, _ = _attempt_assignment(
        result, pieces, independent_roots, board_config, board_gap, kerf,
    )
    if independent_assignment is not None:
        independent_roots, independent_assignment = _repack_independent_sources(
            result, pieces, operation_sources, board_config, kerf,
            independent_assignment,
        )
        candidates.append((independent_roots, independent_assignment))

    if not candidates:
        return independent_errors or original_errors

    def score(candidate):
        candidate_roots, candidate_assignment = candidate
        root_classes = {
            candidate_roots[label]: state.stock_class
            for label, state in candidate_assignment.items()
        }
        counts = {
            stock_class: sum(value == stock_class
                             for value in root_classes.values())
            for stock_class in ('A', 'B')
        }
        return 2 * max(counts.values(), default=0), len(root_classes)

    roots, assignment = min(candidates, key=score)

    boards_by_label = {str(board.label): board for board in result.boards}
    root_classes = {}
    for label, state in assignment.items():
        placed = boards_by_label[label]
        placed.stock_class = state.stock_class
        placed.source_rotation = state.rotation
        placed.display_edges = state.edges
        root_classes[roots[label]] = state.stock_class
        pieces[label].source_x = state.source_x
        pieces[label].source_y = state.source_y
        pieces[label].source_polygon = _source_polygon_for_state(
            placed, pieces[label], state,
        )
    for group in groups.values():
        labels = [str(piece.label) for piece in group.pieces]
        root = roots[labels[0]]
        group.root_source_id = root
        if root == group.source_id:
            group.parent_source_id = ""
        else:
            group.parent_source_id = root
        group.stock_class = root_classes[root]

    counts = {"A": 0, "B": 0}
    for stock_class in root_classes.values():
        counts[stock_class] += 1
    result.statistics.stock_counts = counts
    result.statistics.purchase_boards = 2 * max(counts.values(), default=0)
    result.statistics.total_boards = len(root_classes)
    result.statistics.cut_boards = max(
        0, result.statistics.total_boards - result.statistics.full_boards,
    )
    result.statistics.total_area = (
        result.statistics.total_boards * board_config.length * board_config.width
    )
    result.statistics.waste_area = max(
        0, result.statistics.total_area - result.statistics.room_area,
    )
    result.statistics.utilization = (
        result.statistics.room_area / result.statistics.total_area
        if result.statistics.total_area > 0 else 0
    )
    return []


def verify_recorded_supplier_stock(result, board_config, board_gap=0.0):
    """Verify the recorded source type, cut inheritance, rotation and joins."""
    groups = {group.source_id: group
              for group in (result.statistics.cutting_groups or [])}
    pieces = {}
    roots = {}
    for group in groups.values():
        root = group.root_source_id or group.source_id
        for piece in group.pieces:
            label = str(piece.label)
            pieces[label] = piece
            roots[label] = root

    errors = []
    root_classes = {}
    expected_edges = {}
    assignments = {}
    for placed in result.boards:
        label = str(placed.label)
        piece = pieces.get(label)
        if piece is None:
            errors.append(f"位{label}: 缺少源板切割记录")
            continue
        stock_class = placed.stock_class
        if stock_class not in ("A", "B"):
            errors.append(f"位{label}: 缺少 A/B 板型记录")
            continue
        root = roots[label]
        if root in root_classes and root_classes[root] != stock_class:
            errors.append(
                f"{root}: 同源板型不一致 "
                f"({root_classes[root]} / {stock_class})"
            )
        else:
            root_classes[root] = stock_class

        candidates = _placement_states_for_rect(
            placed, piece, board_config,
            piece.source_x, piece.source_y, 0,
        )
        matching = [
            state for state in candidates
            if state.stock_class == stock_class
            and state.rotation == placed.source_rotation
        ]
        if not matching:
            errors.append(f"位{label}: 源板切割继承与铺装边不一致")
            continue
        expected = matching[0].edges
        expected_edges[label] = expected
        assignments[label] = placed.source_rotation
        if placed.display_edges != expected:
            errors.append(f"位{label}: 已记录四边与源板切割继承不一致")
        expected_polygon = Polygon(_source_polygon_for_state(
            placed, piece, matching[0],
        ))
        if not piece.source_polygon:
            errors.append(f"位{label}: 缺少源板切割轮廓")
        else:
            recorded_polygon = Polygon(piece.source_polygon)
            if recorded_polygon.symmetric_difference(expected_polygon).area > 1e-6:
                errors.append(f"位{label}: 源板切割轮廓与铺装裁切不一致")

    for left, left_side, right, right_side in _adjacencies(
            result.boards, board_gap):
        if left not in expected_edges or right not in expected_edges:
            continue
        left_edge = getattr(expected_edges[left], left_side)
        right_edge = getattr(expected_edges[right], right_side)
        if left_edge == EdgeType.CUT or right_edge == EdgeType.CUT:
            errors.append(
                f"位{left} {left_side} ↔ 位{right} {right_side}: "
                "内部邻边出现切割边"
            )
        elif left_edge == right_edge:
            errors.append(
                f"位{left} {left_side} ↔ 位{right} {right_side}: "
                "公母榫不匹配"
            )

    summary = {
        "boards": len(result.boards),
        "internal_edges": len(_adjacencies(result.boards, board_gap)),
        "assigned_boards": len(assignments),
        "source_boards": len(root_classes),
        "errors": len(errors),
    }
    return errors, summary, assignments
