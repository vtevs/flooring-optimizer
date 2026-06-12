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
    """边匹配校验：检查每块板片的四边是否满足铺装位需求。

    从池条目推导板片四边，从铺装位推导需求四边，检查匹配。
    非阻塞：只报告不匹配，不断言。
    """
    # 待完善：需要铺装位信息 (RoomPlacement list)
    return []


def verify_multi(multi_result: MultiRoomResult, config: Config) -> list[str]:
    errors = []
    for rs, room_result in multi_result.room_results:
        errors.extend(_verify_cutting_ops(room_result, config, room_label=rs.name))
        errors.extend(_verify_coverage(room_result, config, room_label=rs.name,
                                       room_width=rs.width, room_length=rs.length))
    return errors


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

    if room_width is not None and room_length is not None:
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
