"""Optional installation constraints for room-corner full boards."""

from shapely import affinity
from shapely.geometry import Point, box

# 与 config.py 中 VALID_CORNERS 保持一致
CORNERS = ("bottom-left", "top-left", "top-right", "bottom-right")


def _corner_points(bounds):
    minx, miny, maxx, maxy = bounds
    return {
        "bottom-left": (minx, miny),
        "top-left": (minx, maxy),
        "top-right": (maxx, maxy),
        "bottom-right": (maxx, miny),
    }


def _candidate_corners(room, tolerance: float):
    raw = _corner_points(room.bounds)
    pts = {name: Point(x, y) for name, (x, y) in raw.items()}
    return {
        name: p for name, p in pts.items() if room.buffer(tolerance).covers(p)
    }


def _board_polygon(board):
    half_l = board.length / 2
    half_w = board.width / 2
    poly = box(
        board.x - half_l,
        board.y - half_w,
        board.x + half_l,
        board.y + half_w,
    )
    if abs(getattr(board, "rotation", 0.0)) > 1e-9:
        poly = affinity.rotate(poly, board.rotation, origin=(board.x, board.y))
    return poly


def has_full_board_at_corner(result, room, corner: str,
                             tolerance: float = 1.0) -> bool:
    """Return True when the given room corner is covered by a full board.

    Args:
        result: LayoutResult
        room: installable Shapely geometry
        corner: one of "bottom-left" | "top-left" | "top-right" | "bottom-right"
        tolerance: coverage tolerance (mm)
    """
    candidates = _candidate_corners(room, tolerance)
    if corner not in candidates:
        # 该角不在可铺装区域内（如 L 形房间的包围盒角）→ 无法满足
        return False
    corner_point = candidates[corner]

    full_boards = [b for b in result.boards if not b.is_cut]
    for board in full_boards:
        if _board_polygon(board).buffer(tolerance).covers(corner_point):
            return True
    return False


def has_full_board_at_room_corner(result, room, tolerance: float = 1.0) -> bool:
    """Return True when any installable room corner is covered by a full board.

    Candidate corners come from the installable geometry bounding box. Corners
    that do not actually touch the geometry are skipped, which matters for
    L-shaped rooms where a bounding-box corner can be outside the room.
    """
    candidates = _candidate_corners(room, tolerance)
    if not candidates:
        return False

    full_boards = [b for b in result.boards if not b.is_cut]
    for corner in candidates.values():
        for board in full_boards:
            if _board_polygon(board).buffer(tolerance).covers(corner):
                return True
    return False


def corner_offset(corner: str, bounds, L: float, W: float, pitch: float,
                  gap: float = 0.0):
    """为一指定整板起始角计算排样起始偏移 (xo, yo)。

    针对 L-triple 铺装方式（A 块=竖向 W×L，B 块=横向 L×W）：
    - A 竖板：x=xo+i*pitch (i=0..2)，y∈[yo, yo+L]
    - B 横板：x=xo+3*pitch，y=yo+i*pitch (i=0..2)，尺寸 L×W

    返回一组候选偏移，使该角落覆盖整板。
    """
    minx, miny, maxx, maxy = bounds
    if corner == "bottom-left":
        return [(minx, miny)]
    if corner == "top-left":
        # 竖板 A(i=0) 顶边对齐 maxy，左边对齐 minx
        return [(minx, maxy - L)]
    if corner == "bottom-right":
        # 竖板 A(i=2) 右边对齐 maxx，底边对齐 miny
        return [(maxx - 2 * pitch - W, miny)]
    if corner == "top-right":
        # 横板 B 右边对齐 maxx，顶边对齐 maxy
        return [(maxx - 3 * pitch - L, maxy - W)]
    return []
