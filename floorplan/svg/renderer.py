"""
SVG 铺装图渲染器 v2

标注:
- 房间轮廓 + 尺寸
- 可铺区域（伸缩缝内缩）
- 每板四边: 公榫(绿实线)/母榫(橙虚线)/切割(红实线)
- 板源编号标签
- 完整板 vs 切割板区分
"""

import math
from pathlib import Path
from shapely.geometry import Polygon, box
from shapely import affinity
from ..models import LayoutResult, OutputConfig
from ..geometry.room import build_room


def render(result, room_config, output, filepath):
    room = build_room(room_config)
    minx, miny, maxx, maxy = room.bounds
    margin = 300
    scale = 1200 / (maxx - minx) if maxx > minx else 1
    cw = (maxx - minx) * scale + 2 * margin * scale
    ch = (maxy - miny) * scale + 2 * margin * scale
    tx = margin * scale - minx * scale
    ty = margin * scale + (maxy - miny) * scale + miny * scale

    svg = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cw:.0f} {ch:.0f}" width="{cw:.0f}" height="{ch:.0f}">',
        '<defs>',
        '<pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">',
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#e44" stroke-width="1.5" opacity="0.35"/>',
        '</pattern>',
        '</defs>',
        '<style>',
        '  .room      { fill: #fafafa; stroke: #333; stroke-width: 3; }',
        '  .area      { fill: none; stroke: #999; stroke-width: 1.5; stroke-dasharray: 8,4; }',
        '  .board     { fill: #e8d5b0; stroke: #b8945c; stroke-width: 1; }',
        '  .cut-full  { fill: none; stroke: #bbb; stroke-width: 0.8; stroke-dasharray: 3,3; }',
        '  .cut-used  { fill: #d4b896; stroke: #c44; stroke-width: 2; }',
        '  .cut-hatch { fill: url(#hatch); stroke: none; }',
        '  .edge-t    { fill: none; stroke: #4a8; stroke-width: 2; }',
        '  .edge-g    { fill: none; stroke: #c84; stroke-width: 2; stroke-dasharray: 5,3; }',
        '  .edge-cut  { fill: none; stroke: #e44; stroke-width: 2.5; }',
        '  .dim       { fill: #666; font-size: 11px; font-family: sans-serif; text-anchor: middle; }',
        '  .lbl       { fill: #333; font-size: 9px; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; }',
        '  .lbl-cut   { fill: #c00; font-size: 9px; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; font-weight: bold; }',
        '  .lbl-bg    { fill: #fff; fill-opacity: 0.8; }',
        '  .legend    { fill: #fff; stroke: #ccc; stroke-width: 1; }',
        '  .legend-t  { font-size: 10px; font-family: sans-serif; fill: #333; }',
        '</style>',
    ]

    # ---- 铺装图层 ----
    svg.append(f'<g transform="translate({tx:.1f},{ty:.1f}) scale({scale:.4f},{-scale:.4f})">')

    # 可铺区域（虚线）
    expansion_gap = output.expansion_gap if hasattr(output, 'expansion_gap') else 10
    layout_area = room.buffer(-expansion_gap, join_style=2)
    if not layout_area.is_empty:
        svg.append(_poly_svg(layout_area, 'area'))

    # 房间轮廓
    svg.append(_poly_svg(room, 'room'))

    # 地板
    for b in result.boards:
        L, W = b.length, b.width
        x0 = b.x - L/2
        y0 = b.y - W/2

        if b.is_cut and b.cut_polygon:
            used = _to_polygon(b.cut_polygon)
            # 原板轮廓（虚线）
            full = box(x0, y0, x0 + L, y0 + W)
            if b.rotation and abs(b.rotation) > 0.1:
                full = affinity.rotate(full, b.rotation, origin=(b.x, b.y))
            svg.append(_poly_svg(full, 'cut-full'))
            # 使用部分
            svg.append(_poly_svg(used, 'cut-used'))
            svg.append(_poly_svg(used, 'cut-hatch'))
            # 切割边标注
            _add_cut_edges(svg, full, used)
        elif b.is_cut:
            bp = box(x0, y0, x0 + L, y0 + W)
            if b.rotation and abs(b.rotation) > 0.1:
                bp = affinity.rotate(bp, b.rotation, origin=(b.x, b.y))
            svg.append(_poly_svg(bp, 'cut-used'))
        else:
            svg.append(
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{L:.1f}" height="{W:.1f}" '
                f'transform="rotate({b.rotation},{b.x:.1f},{b.y:.1f})" '
                f'class="board"/>' if b.rotation and abs(b.rotation) > 0.1 else
                f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{L:.1f}" height="{W:.1f}" class="board"/>'
            )

        # 榫槽边标记
        _add_tg_edges(svg, b)

    svg.append('</g>')

    # ---- 尺寸标注图层（屏幕坐标） ----
    _add_dimensions(svg, room, layout_area, tx, ty, scale, miny, maxy)

    # ---- 标签图层 ----
    svg.append('<g>')
    for b in result.boards:
        lx = tx + b.x * scale
        ly = ty - b.y * scale
        src = b.source_id.removeprefix('源') if b.source_id else b.label
        pos = b.label
        cls = 'lbl-cut' if b.is_cut else 'lbl'
        # 源板号（上方）
        svg.append(f'<rect x="{lx-16:.1f}" y="{ly-14:.1f}" width="32" height="12" rx="2" class="lbl-bg"/>')
        svg.append(f'<text x="{lx:.1f}" y="{ly-5:.1f}" class="{cls}" font-size="8">源{src}</text>')
        # 位号（下方）
        svg.append(f'<rect x="{lx-12:.1f}" y="{ly+2:.1f}" width="24" height="9" rx="2" class="lbl-bg"/>')
        svg.append(f'<text x="{lx:.1f}" y="{ly+8:.1f}" class="dim" font-size="7">位{pos}</text>')
    svg.append('</g>')

    # ---- 图例 ----
    _add_legend(svg, cw, ch)

    svg.append('</svg>')
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_text('\n'.join(svg), encoding='utf-8')


def _add_tg_edges(svg, b):
    """榫槽边标记: 底=公榫(绿), 顶=母榫(橙虚线), 右=公榫, 左=母榫"""
    L, W = b.length, b.width
    x, y, r = b.x, b.y, b.rotation
    hw, hh = L/2, W/2

    # 未旋转四角: (x-hw,y-hh) 左下, (x+hw,y-hh) 右下, (x+hw,y+hh) 右上, (x-hw,y+hh) 左上
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    if r and abs(r) > 0.1:
        rad = math.radians(r)
        cr, sr = math.cos(rad), math.sin(rad)
        corners = [(cx*cr - cy*sr + x, cx*sr + cy*cr + y) for cx, cy in corners]

    # 底边=公榫, 顶边=母榫
    bl, br = corners[0], corners[1]  # bottom
    tl, tr = corners[3], corners[2]  # top
    svg.append(f'<line x1="{bl[0]:.1f}" y1="{bl[1]:.1f}" x2="{br[0]:.1f}" y2="{br[1]:.1f}" class="edge-t"/>')
    svg.append(f'<line x1="{tl[0]:.1f}" y1="{tl[1]:.1f}" x2="{tr[0]:.1f}" y2="{tr[1]:.1f}" class="edge-g"/>')


def _add_cut_edges(svg, full, used):
    """切割边 = 原板边界与使用区不重合的边"""
    # 简化: used 多边形不在 full 边界上的边画红色
    if hasattr(used, 'exterior'):
        coords = list(used.exterior.coords)
        for i in range(len(coords) - 1):
            svg.append(
                f'<line x1="{coords[i][0]:.1f}" y1="{coords[i][1]:.1f}" '
                f'x2="{coords[i+1][0]:.1f}" y2="{coords[i+1][1]:.1f}" class="edge-cut"/>'
            )


def _add_dimensions(svg, room, layout_area, tx, ty, scale, miny, maxy):
    """房间尺寸标注"""
    b = room.bounds
    # 底边尺寸
    yb = ty - b[1] * scale + 30
    xm = tx + (b[0] + b[2]) / 2 * scale
    svg.append(f'<text x="{xm:.1f}" y="{yb:.1f}" class="dim">{(b[2]-b[0]):.0f}mm</text>')
    # 右边尺寸
    xr = tx + b[2] * scale + 30
    ym = ty - (b[1] + b[3]) / 2 * scale
    svg.append(f'<text x="{xr:.1f}" y="{ym:.1f}" class="dim" transform="rotate(-90,{xr:.1f},{ym:.1f})">{(b[3]-b[1]):.0f}mm</text>')


def _add_legend(svg, cw, ch):
    """图例"""
    lx, ly = cw - 180, ch - 100
    items = [
        ('<line x1="0" y1="0" x2="30" y2="0" class="edge-t"/>', '公榫'),
        ('<line x1="0" y1="10" x2="30" y2="10" class="edge-g"/>', '母榫'),
        ('<line x1="0" y1="20" x2="30" y2="20" class="edge-cut"/>', '切割边'),
    ]
    svg_part = f'<rect x="{lx-10}" y="{ly-10}" width="170" height="60" rx="4" class="legend"/>'
    for i, (gfx, label) in enumerate(items):
        yi = ly + i * 18
        svg_part += f'<g transform="translate({lx},{yi})">{gfx}</g>'
        svg_part += f'<text x="{lx+40}" y="{yi+5}" class="legend-t">{label}</text>'
    svg.append(svg_part)


def _poly_svg(poly, cls):
    if hasattr(poly, 'exterior'):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly.exterior.coords)
    elif hasattr(poly, '__iter__') and not isinstance(poly, str):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in poly)
    else:
        return ""
    return f'<polygon points="{pts}" class="{cls}"/>'


def _to_polygon(coords):
    return Polygon(coords)


def render_multi(multi_result, config, filepath):
    """将多个房间的铺装结果渲染到同一个 SVG 文件中。

    房间水平排列，每个房间独立缩放。
    """
    from ..models import RoomConfig as RC, OutputConfig

    board = config.board
    rooms_data = []
    for rs, room_result in multi_result.room_results:
        room = box(0, 0, rs.width, rs.length)
        minx, miny, maxx, maxy = room.bounds
        expansion_gap = getattr(config.edges, 'expansion_gap', 10)
        layout_area = room.buffer(-expansion_gap, join_style=2)
        rooms_data.append({
            'name': rs.name,
            'result': room_result,
            'room': room,
            'layout_area': layout_area,
            'w': maxx - minx,
            'h': maxy - miny,
            'bounds': (minx, miny, maxx, maxy),
        })

    # 布局参数
    margin = 200
    gap = 300  # 房间间距
    label_height = 40

    # 每个房间的缩放：统一高度 800px 为基准
    base_h = 800
    for d in rooms_data:
        d['scale'] = base_h / d['h'] if d['h'] > 0 else 1

    # 计算总画布尺寸
    total_w = sum(d['w'] * d['scale'] for d in rooms_data) + gap * (len(rooms_data) - 1) + margin * 2
    max_h = base_h
    cw = total_w
    ch = max_h + margin * 2 + label_height

    # SVG 头
    svg = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cw:.0f} {ch:.0f}" width="{cw:.0f}" height="{ch:.0f}">',
        '<defs>',
        '<pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">',
        '<line x1="0" y1="0" x2="0" y2="6" stroke="#e44" stroke-width="1.5" opacity="0.35"/>',
        '</pattern>',
        '</defs>',
        '<style>',
        '  .room      { fill: #fafafa; stroke: #333; stroke-width: 3; }',
        '  .area      { fill: none; stroke: #999; stroke-width: 1.5; stroke-dasharray: 8,4; }',
        '  .board     { fill: #e8d5b0; stroke: #b8945c; stroke-width: 1; }',
        '  .cut-full  { fill: none; stroke: #bbb; stroke-width: 0.8; stroke-dasharray: 3,3; }',
        '  .cut-used  { fill: #d4b896; stroke: #c44; stroke-width: 2; }',
        '  .cut-hatch { fill: url(#hatch); stroke: none; }',
        '  .edge-t    { fill: none; stroke: #4a8; stroke-width: 2; }',
        '  .edge-g    { fill: none; stroke: #c84; stroke-width: 2; stroke-dasharray: 5,3; }',
        '  .edge-cut  { fill: none; stroke: #e44; stroke-width: 2.5; }',
        '  .dim       { fill: #666; font-size: 11px; font-family: sans-serif; text-anchor: middle; }',
        '  .lbl       { fill: #333; font-size: 9px; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; }',
        '  .lbl-cut   { fill: #c00; font-size: 9px; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; font-weight: bold; }',
        '  .lbl-bg    { fill: #fff; fill-opacity: 0.8; }',
        '  .legend    { fill: #fff; stroke: #ccc; stroke-width: 1; }',
        '  .legend-t  { font-size: 10px; font-family: sans-serif; fill: #333; }',
        '  .room-lbl  { fill: #333; font-size: 16px; font-family: sans-serif; text-anchor: middle; font-weight: bold; }',
        '</style>',
    ]

    # 逐个房间渲染
    cur_x = margin
    for d in rooms_data:
        name = d['name']
        result = d['result']
        room = d['room']
        layout_area = d['layout_area']
        scale = d['scale']
        w, h = d['w'], d['h']
        minx, miny, maxx, maxy = d['bounds']

        # 该房间的变换：用 translate 放到对应位置
        tx_room = cur_x
        ty_room = margin + label_height

        svg.append(f'<!-- === 房间 {name} === -->')

        # 铺装图层 group
        svg.append(f'<g transform="translate({tx_room:.1f},{ty_room:.1f})">')

        # 可铺区域（虚线）
        if not layout_area.is_empty:
            svg.append(_poly_svg_scaled(layout_area, 'area', 0, 0, scale, h))

        # 房间轮廓
        svg.append(_poly_svg_scaled(room, 'room', 0, 0, scale, h))

        # 地板
        for b in result.boards:
            L, W = b.length, b.width
            bx = b.x * scale
            by = (h - b.y) * scale  # Y 轴翻转
            bL = L * scale
            bW = W * scale
            b_rot = -b.rotation if b.rotation else 0

            if b.is_cut and b.cut_polygon:
                # 原板轮廓（虚线）
                full = box(b.x - L/2, b.y - W/2, b.x + L/2, b.y + W/2)
                if b.rotation and abs(b.rotation) > 0.1:
                    full = affinity.rotate(full, b.rotation, origin=(b.x, b.y))
                svg.append(_poly_svg_scaled(full, 'cut-full', 0, 0, scale, h))

                # 使用部分
                if b.cut_polygon:
                    used = Polygon(b.cut_polygon)
                    svg.append(_poly_svg_scaled(used, 'cut-used', 0, 0, scale, h))
                    svg.append(_poly_svg_scaled(used, 'cut-hatch', 0, 0, scale, h))
            elif b.is_cut:
                bp = box(b.x - L/2, b.y - W/2, b.x + L/2, b.y + W/2)
                if b.rotation and abs(b.rotation) > 0.1:
                    bp = affinity.rotate(bp, b.rotation, origin=(b.x, b.y))
                svg.append(_poly_svg_scaled(bp, 'cut-used', 0, h, scale, h))
            else:
                svg.append(
                    f'<rect x="{bx - bL/2:.1f}" y="{by - bW/2:.1f}" '
                    f'width="{bL:.1f}" height="{bW:.1f}" '
                    f'transform="rotate({b_rot},{bx:.1f},{by:.1f})" '
                    f'class="board"/>'
                )

            # 榫槽边标记
            _add_tg_edges_scaled(svg, b, scale, h)

        svg.append('</g>')

        # 尺寸标注：宽在底部，高在右侧
        scaled_w = w * scale
        scaled_h = h * scale
        dim_bottom_y = ty_room + scaled_h + 25
        dim_center_x = tx_room + scaled_w / 2
        svg.append(f'<text x="{dim_center_x:.1f}" y="{dim_bottom_y:.1f}" class="dim">{w:.0f}mm</text>')
        dim_right_x = tx_room + scaled_w + 25
        dim_mid_y = ty_room + scaled_h / 2
        svg.append(f'<text x="{dim_right_x:.1f}" y="{dim_mid_y:.1f}" class="dim" '
                   f'transform="rotate(-90,{dim_right_x:.1f},{dim_mid_y:.1f})">{h:.0f}mm</text>')

        # 标签
        for b in result.boards:
            lx = tx_room + b.x * scale
            ly = ty_room + (h - b.y) * scale
            src = b.source_id.removeprefix('源') if b.source_id else b.label
            pos = b.label
            cls = 'lbl-cut' if b.is_cut else 'lbl'
            # 源板号（上方）
            svg.append(f'<rect x="{lx-16:.1f}" y="{ly-14:.1f}" width="32" height="12" rx="2" class="lbl-bg"/>')
            svg.append(f'<text x="{lx:.1f}" y="{ly-5:.1f}" class="{cls}" font-size="8">源{src}</text>')
            # 位号（下方）
            svg.append(f'<rect x="{lx-12:.1f}" y="{ly+2:.1f}" width="24" height="9" rx="2" class="lbl-bg"/>')
            svg.append(f'<text x="{lx:.1f}" y="{ly+8:.1f}" class="dim" font-size="7">位{pos}</text>')

        # 房间名标签
        room_label_x = tx_room + w * scale / 2
        room_label_y = ty_room - 10
        svg.append(f'<text x="{room_label_x:.1f}" y="{room_label_y:.1f}" class="room-lbl">房间 {name}</text>')

        cur_x += w * scale + gap

    # 图例
    _add_legend(svg, cw, ch)

    svg.append('</svg>')
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_text('\n'.join(svg), encoding='utf-8')


def _poly_svg_scaled(poly, cls, ox, oy, scale, room_h):
    """将多边形坐标缩放并翻转 Y 轴后输出 SVG polygon 元素。"""
    if hasattr(poly, 'exterior'):
        coords = poly.exterior.coords
    elif hasattr(poly, '__iter__') and not isinstance(poly, str):
        coords = poly
    else:
        return ""
    pts = " ".join(f"{x*scale+ox:.1f},{(room_h-y)*scale+oy:.1f}" for x, y in coords)
    return f'<polygon points="{pts}" class="{cls}"/>'


def _add_tg_edges_scaled(svg, b, scale, room_h):
    """缩放版榫槽边标记"""
    L, W = b.length, b.width
    x, y, r = b.x, b.y, b.rotation
    hw, hh = L/2, W/2

    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    if r and abs(r) > 0.1:
        rad = math.radians(r)
        cr, sr = math.cos(rad), math.sin(rad)
        corners = [(cx*cr - cy*sr + x, cx*sr + cy*cr + y) for cx, cy in corners]

    # 缩放到屏幕坐标
    sc = [(cx*scale, (room_h - cy)*scale) for cx, cy in corners]

    bl, br = sc[0], sc[1]
    tl, tr = sc[3], sc[2]
    svg.append(f'<line x1="{bl[0]:.1f}" y1="{bl[1]:.1f}" x2="{br[0]:.1f}" y2="{br[1]:.1f}" class="edge-t"/>')
    svg.append(f'<line x1="{tl[0]:.1f}" y1="{tl[1]:.1f}" x2="{tr[0]:.1f}" y2="{tr[1]:.1f}" class="edge-g"/>')
