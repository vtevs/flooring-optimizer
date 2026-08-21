"""Physical supplier board types and plan-view rotations."""

from .models import BoardEdges, EdgeType


T = EdgeType.TONGUE
G = EdgeType.GROOVE


# Intrinsic state: board face up and vertical, with the top edge being short.
SUPPLIER_VERTICAL_EDGES = {
    "A": BoardEdges(top=T, right=G, bottom=G, left=T),
    "B": BoardEdges(top=T, right=T, bottom=G, left=G),
}


def normalize_rotation(rotation: int | float) -> int:
    value = int(round(rotation)) % 360
    if value not in (0, 90, 180, 270):
        raise ValueError(f"板只能按 0/90/180/270° 旋转，当前值: {rotation}")
    return value


def rotate_board_edges(edges: BoardEdges, rotation: int | float) -> BoardEdges:
    """Rotate physical edges counter-clockwise in plan view."""
    turns = normalize_rotation(rotation) // 90
    result = edges
    for _ in range(turns):
        result = BoardEdges(
            top=result.right,
            right=result.bottom,
            bottom=result.left,
            left=result.top,
        )
    return result


def supplier_edges(stock_class: str, rotation: int | float) -> BoardEdges:
    try:
        intrinsic = SUPPLIER_VERTICAL_EDGES[stock_class]
    except KeyError as exc:
        raise ValueError(f"未知供应商板型: {stock_class}") from exc
    return rotate_board_edges(intrinsic, rotation)


def orientation_for_rotation(rotation: int | float) -> str:
    return "vertical" if normalize_rotation(rotation) % 180 == 0 else "horizontal"
