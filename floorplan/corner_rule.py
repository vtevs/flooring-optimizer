"""Optional installation constraints for room-corner full boards."""

from shapely import affinity
from shapely.geometry import Point, box


def has_full_board_at_room_corner(result, room, tolerance: float = 1.0) -> bool:
    """Return True when an installable room corner is covered by a full board.

    Candidate corners come from the installable geometry bounding box. Corners
    that do not actually touch the geometry are skipped, which matters for
    L-shaped rooms where a bounding-box corner can be outside the room.
    """
    corners = _candidate_corners(room, tolerance)
    if not corners:
        return False

    full_boards = [b for b in result.boards if not b.is_cut]
    for corner in corners:
        for board in full_boards:
            if _board_polygon(board).buffer(tolerance).covers(corner):
                return True
    return False


def _candidate_corners(room, tolerance: float):
    minx, miny, maxx, maxy = room.bounds
    raw = [
        Point(minx, miny),
        Point(maxx, miny),
        Point(minx, maxy),
        Point(maxx, maxy),
    ]
    return [p for p in raw if room.buffer(tolerance).covers(p)]


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
