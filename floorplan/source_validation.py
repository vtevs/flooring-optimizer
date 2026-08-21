"""Shared validation for absolute source-board cutting rectangles."""

from shapely.geometry import Polygon, box


def validate_source_rectangles(pieces, length, width, kerf,
                               tolerance=1e-6) -> list[str]:
    """Validate bounds, overlap and kerf for source rectangle dictionaries."""
    errors = []
    for piece in pieces:
        x, y = piece['x'], piece['y']
        piece_width, piece_length = piece['wid'], piece['len']
        if (x < -tolerance or y < -tolerance or
                x + piece_width > width + tolerance or
                y + piece_length > length + tolerance):
            errors.append(f"位{piece['label']}超出源板范围")
        polygon_coords = piece.get('polygon') or []
        if polygon_coords:
            polygon = Polygon(polygon_coords)
            piece_rect = box(x, y, x + piece_width, y + piece_length)
            if (not polygon.is_valid or polygon.is_empty or
                    polygon.difference(piece_rect).area > tolerance):
                errors.append(f"位{piece['label']}切割轮廓超出所属源片")

    for index, first in enumerate(pieces):
        ax0, ay0 = first['x'], first['y']
        ax1, ay1 = ax0 + first['wid'], ay0 + first['len']
        for second in pieces[index + 1:]:
            bx0, by0 = second['x'], second['y']
            bx1, by1 = bx0 + second['wid'], by0 + second['len']
            overlap_x = min(ax1, bx1) - max(ax0, bx0)
            overlap_y = min(ay1, by1) - max(ay0, by0)
            if overlap_x > tolerance and overlap_y > tolerance:
                errors.append(
                    f"位{first['label']}与位{second['label']}在源板中重叠"
                )
                continue
            if overlap_x > tolerance:
                gap = max(by0 - ay1, ay0 - by1, 0)
                if gap + tolerance < kerf:
                    errors.append(
                        f"位{first['label']}与位{second['label']}长度锯缝不足"
                    )
            if overlap_y > tolerance:
                gap = max(bx0 - ax1, ax0 - bx1, 0)
                if gap + tolerance < kerf:
                    errors.append(
                        f"位{first['label']}与位{second['label']}宽度锯缝不足"
                    )
    return errors
