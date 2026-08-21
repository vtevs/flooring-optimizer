"""
HTML 铺装图渲染器 — 交互式多房间视图。

与 SVG 渲染器不同，此渲染器输出单个自包含的 .html 文件：
- 每个房间绘制在独立分组中（SVG 内嵌）。
- 不显示复杂的"位号/源号"标签，保持版面整洁。
- 点击任意一块切割板：
    * 高亮同一块源板切出的所有相关切割板；
    * 弹出弹窗，列出所有相关切割板（含被点击的那块）在图中的
      顶右底左四边榫槽属性（公榫/母榫/切割面）。
"""

import math
from pathlib import Path
from shapely.geometry import Polygon, box
from shapely import affinity

from ..models import EdgeType
from ..geometry.room import build_room, build_obstacles
from ..source_validation import validate_source_rectangles

EDGE_CN = {EdgeType.TONGUE: "公榫", EdgeType.GROOVE: "母榫", EdgeType.CUT: "切割面"}


def render_multi_html(multi_result, config, filepath):
    """将多房间铺装结果渲染为交互式 HTML 文件。"""
    board = config.board

    # ── 收集各房间的板与几何 ──────────────────────────────
    rooms_data = []
    for rs, room_result in multi_result.room_results:
        room = build_room(rs)
        minx, miny, maxx, maxy = room.bounds
        expansion_gap = getattr(config.edges, 'expansion_gap', 10)
        layout_area = room.buffer(-expansion_gap, join_style=2)
        rooms_data.append({
            'name': rs.name,
            'result': room_result,
            'room': room,
            'obstacles': build_obstacles(rs),
            'layout_area': layout_area,
            'w': maxx - minx,
            'h': maxy - miny,
            'bounds': (minx, miny, maxx, maxy),
        })

    # 布局参数
    margin = 160
    gap = 240
    label_height = 50
    base_h = 800
    for d in rooms_data:
        d['scale'] = base_h / d['h'] if d['h'] > 0 else 1

    total_w = sum(d['w'] * d['scale'] for d in rooms_data) + gap * (len(rooms_data) - 1) + margin * 2
    cw = total_w
    ch = base_h + margin * 2 + label_height

    # ── 源板关联数据 ──────────────────────────────────────
    from ..verify import board_display_edges
    source_parent = {}          # source_id -> parent_source_id
    source_stock = {}           # source_id -> A/B
    for d in rooms_data:
        cgs = d['result'].statistics.cutting_groups or []
        for g in cgs:
            if g.source_id:
                source_parent[g.source_id] = g.parent_source_id or ''
                source_stock[g.source_id] = getattr(g, 'stock_class', '') or ''

    def root_source(sid):
        seen = set()
        while sid and sid in source_parent and source_parent[sid] and sid not in seen:
            seen.add(sid)
            sid = source_parent[sid]
        return sid

    # 每个房间为板附加展示数据（源根、符合宪法的四边属性）
    for d in rooms_data:
        display_edges = board_display_edges(d['result'], config,
                                            room_label=d['name'])
        for b in d['result'].boards:
            b._root_source = root_source(b.source_id)
            b._display_edges = display_edges.get(str(b.label))
            b._stock_class = source_stock.get(b.source_id, '') or source_stock.get(b._root_source, '')

    # ── 生成房间 SVG ──────────────────────────────────────
    rooms_svg = []
    board_index = 0
    cur_x = margin
    for d in rooms_data:
        svg = _render_room_group(d, cw, ch, board_index)
        rooms_svg.append((d['name'], svg, cur_x))
        board_index += len(d['result'].boards)
        cur_x += d['w'] * d['scale'] + gap

    # ── 每块板"需要切割成"的使用尺寸（来自切割组中的片）──────
    # 注意：PlacedBoard.length/width 是整板放置尺寸，
    # 而切割后需要的尺寸在 CuttingPiece 中（length × width，width=0 表示全宽）。
    bw = config.board.width
    label_size = {}           # label -> (len, wid)
    for d in rooms_data:
        cgs = d['result'].statistics.cutting_groups or []
        for g in cgs:
            for p in g.pieces:
                pw = p.width if p.width and p.width > 0 else bw
                label_size[p.label] = (round(p.length), round(pw))

    # ── 汇总所有板的元数据供 JS 使用 ───────────────────────
    all_boards = []
    for d in rooms_data:
        for b in d['result'].boards:
            pe = b._display_edges
            plen, pwid = label_size.get(b.label, (round(b.length), round(b.width)))
            all_boards.append({
                'label': b.label,
                'source': b.source_id,
                'root': b._root_source,
                'room': d['name'],
                'is_cut': bool(b.is_cut),
                'len': plen,
                'wid': pwid,
                'stock_class': getattr(b, '_stock_class', ''),
                'source_rotation': getattr(b, 'source_rotation', 0),
                'edges': {
                    'top': EDGE_CN.get(pe.top, '?'),
                    'right': EDGE_CN.get(pe.right, '?'),
                    'bottom': EDGE_CN.get(pe.bottom, '?'),
                    'left': EDGE_CN.get(pe.left, '?'),
                } if pe else None,
            })

    # ── 统计信息：总用板 + 各房间整板/切割板 ───────────────
    stats = []
    total_boards = 0
    total_full = 0
    total_cut = 0
    for d in rooms_data:
        s = d['result'].statistics
        fb = getattr(s, 'full_boards', 0) or 0
        cb = getattr(s, 'cut_boards', 0) or 0
        tb = fb + cb
        total_boards += tb
        total_full += fb
        total_cut += cb
        stats.append({'room': d['name'], 'full': fb, 'cut': cb, 'total': tb})

    # ── 整板切割示意图数据 ────────────────────────────────
    source_layouts = _reconstruct_source_layouts(
        multi_result, config, source_parent, root_source)

    html = _build_html(cw, ch, rooms_svg, all_boards, stats, total_boards,
                       total_full, total_cut, source_layouts)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    Path(filepath).write_text(html, encoding='utf-8')


# ---------------------------------------------------------------------------
# 单房间 SVG 分组
# ---------------------------------------------------------------------------

def _render_room_group(d, cw, ch, board_index):
    name = d['name']
    room = d['room']
    layout_area = d['layout_area']
    obstacles = d.get('obstacles', [])
    scale = d['scale']
    w, h = d['w'], d['h']
    minx, miny, maxx, maxy = d['bounds']

    parts = [f'<!-- === 房间 {name} === -->', f'<g class="room-group" data-room="{name}">']

    # 可铺区域（虚线）
    if not layout_area.is_empty:
        parts.append(_poly_scaled(layout_area, 'area', 0, 0, scale, h))
    # 房间轮廓
    parts.append(_poly_scaled(room, 'room', 0, 0, scale, h))
    # 柜子/障碍物
    for obs in obstacles:
        parts.append(_poly_scaled(obs, 'obstacle', 0, 0, scale, h))
        parts.append(_obstacle_cross_scaled(obs, scale, h))

    # 地板
    for b in d['result'].boards:
        parts.append(_board_svg(b, scale, h, board_index))
        board_index += 1

    parts.append('</g>')

    # 尺寸标注（屏幕坐标，相对房间分组 translate 之外）
    parts.append(f'<text x="{w * scale / 2:.1f}" y="{h * scale + 25:.1f}" class="dim">{w:.0f}mm</text>')
    parts.append(f'<text x="{w * scale + 25:.1f}" y="{h * scale / 2:.1f}" class="dim" '
                 f'transform="rotate(-90,{w * scale + 25:.1f},{h * scale / 2:.1f})">{h:.0f}mm</text>')
    # 房间名
    parts.append(f'<text x="{w * scale / 2:.1f}" y="-10" class="room-lbl">房间 {name}</text>')
    return '\n'.join(parts)


def _board_svg(b, scale, room_h, idx):
    """为一块板生成 SVG 元素，附带 data 属性用于交互。"""
    L, W = b.length, b.width
    bx = b.x * scale
    by = (room_h - b.y) * scale
    bL = L * scale
    bW = W * scale
    b_rot = -b.rotation if b.rotation else 0
    x0 = bx - bL / 2
    y0 = by - bW / 2

    pe = getattr(b, '_display_edges', None)
    edges_str = ""
    if pe:
        edges_str = (f" data-t=\"{EDGE_CN.get(pe.top, '?')}\" data-r=\"{EDGE_CN.get(pe.right, '?')}\""
                     f" data-b=\"{EDGE_CN.get(pe.bottom, '?')}\" data-l=\"{EDGE_CN.get(pe.left, '?')}\"")

    attrs = (f'data-idx="{idx}" data-source="{b.source_id}" data-root="{getattr(b, "_root_source", "")}"'
             f' data-label="{b.label}" data-cut="{1 if b.is_cut else 0}"'
             f' data-len="{L:.0f}" data-wid="{W:.0f}"'
             f' data-stock="{getattr(b, "_stock_class", "")}"{edges_str}')

    stock = getattr(b, '_stock_class', '')
    stock_cls = f" stock-{stock}" if stock in ("A", "B") else ""
    if b.is_cut and b.cut_polygon:
        used = Polygon(b.cut_polygon)
        label_point = used.representative_point()
        label = _stock_label_svg(
            stock,
            label_point.x * scale,
            (room_h - label_point.y) * scale,
            scale,
        )
        pts = " ".join(f"{px*scale:.1f},{(room_h-py)*scale:.1f}" for px, py in used.exterior.coords)
        return (f'<g class="board-wrap">{_stock_label_defs()}'
                f'<polygon points="{pts}" class="board cut{stock_cls}" {attrs} onclick="selectBoard(this)"/>'
                f'{label}</g>')
    label = _stock_label_svg(stock, bx, by, scale)
    return (f'<g class="board-wrap">{_stock_label_defs()}'
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{bL:.1f}" height="{bW:.1f}" '
            f'transform="rotate({b_rot},{bx:.1f},{by:.1f})" class="board{stock_cls}" {attrs} '
            f'onclick="selectBoard(this)"/>'
            f'{label}</g>')


def _stock_label_defs():
    return ""


def _stock_label_svg(stock, x, y, scale):
    if stock not in ("A", "B"):
        return ""
    radius = max(7.0, min(13.0, 9.0 * scale))
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" class="stock-badge stock-{stock}-badge"/>'
        f'<text x="{x:.1f}" y="{y + radius * 0.08:.1f}" class="stock-label">{stock}</text>'
    )


def _poly_scaled(poly, cls, ox, oy, scale, room_h):
    if hasattr(poly, 'exterior'):
        coords = poly.exterior.coords
    elif hasattr(poly, '__iter__') and not isinstance(poly, str):
        coords = poly
    else:
        return ""
    pts = " ".join(f"{x*scale+ox:.1f},{(room_h-y)*scale+oy:.1f}" for x, y in coords)
    return f'<polygon points="{pts}" class="{cls}"/>'


def _obstacle_cross_scaled(poly, scale, room_h):
    minx, miny, maxx, maxy = poly.bounds
    x1, y1 = minx * scale, (room_h - miny) * scale
    x2, y2 = maxx * scale, (room_h - maxy) * scale
    return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" class="ob-x"/>'
            f'<line x1="{x1:.1f}" y1="{y2:.1f}" x2="{x2:.1f}" y2="{y1:.1f}" class="ob-x"/>')


# ---------------------------------------------------------------------------
# 整板切割示意图数据重建
# ---------------------------------------------------------------------------

def _reconstruct_source_layouts(multi_result, config, source_parent, root_fn):
    """Build exact source-board layouts from solved absolute coordinates."""
    L = config.board.length
    W = config.board.width
    K = config.kerf

    groups = []
    for rs, rr in multi_result.room_results:
        for g in (rr.statistics.cutting_groups or []):
            if g.source_id:
                groups.append((rr, g))

    by_root = {}
    for rr, g in groups:
        r = getattr(g, 'root_source_id', '') or root_fn(g.source_id)
        by_root.setdefault(r, []).append((rr, g))

    layouts = {}
    supplier_mode = (
        getattr(config.board, 'stock_class_policy', '')
        == 'supplier-ab-vertical'
    )
    room_edge_errors = {}
    if supplier_mode:
        from ..stock_assignment import verify_recorded_supplier_stock
        board_gap = getattr(config.edges, 'board_gap', 0.0)
        for _, rr in multi_result.room_results:
            room_edge_errors[id(rr)] = verify_recorded_supplier_stock(
                rr, config.board, board_gap=board_gap,
            )[0]
    for r, entries in by_root.items():
        pieces = []
        stock_classes = set()
        inheritance_errors = []
        related_room_ids = set()
        for rr, g in entries:
            related_room_ids.add(id(rr))
            if getattr(g, 'stock_class', ''):
                stock_classes.add(g.stock_class)
            boards = {str(board.label): board for board in rr.boards}
            for p in g.pieces:
                pw = p.source_width or p.width or W
                pl = p.source_length or p.length
                source_polygon = list(p.source_polygon or [])
                source_rect = box(
                    p.source_x, p.source_y,
                    p.source_x + pw, p.source_y + pl,
                )
                shape_cut = bool(
                    source_polygon and
                    Polygon(source_polygon).symmetric_difference(source_rect).area
                    > 1e-6
                )
                pieces.append({
                    'label': p.label,
                    'source': g.source_id,
                    'x': p.source_x,
                    'y': p.source_y,
                    'len': pl,
                    'wid': pw,
                    'polygon': source_polygon,
                    'shape_cut': shape_cut,
                })
                if supplier_mode:
                    from ..stock_assignment import placement_states
                    placed = boards.get(str(p.label))
                    if placed is None:
                        inheritance_errors.append(f"位{p.label}缺少铺装记录")
                        continue
                    if placed.stock_class != g.stock_class:
                        inheritance_errors.append(
                            f"位{p.label}铺装板型与源板类型不一致"
                        )
                        continue
                    matching = [
                        state for state in placement_states(
                            placed, p, config.board,
                        )
                        if state.stock_class == placed.stock_class
                        and state.rotation == placed.source_rotation
                    ]
                    if not matching or placed.display_edges != matching[0].edges:
                        inheritance_errors.append(
                            f"位{p.label}旋转或四边继承不一致"
                        )
        errors = validate_source_rectangles(pieces, L, W, K)
        errors.extend(inheritance_errors)
        for room_id in related_room_ids:
            errors.extend(
                f"所在房间严格邻边校验失败: {error}"
                for error in room_edge_errors.get(room_id, [])
            )
        if len(stock_classes) != 1:
            errors.append('同源板 A/B 类型不一致')
        layouts[r] = {
            'length': L,
            'width': W,
            'stock_class': next(iter(stock_classes), ''),
            'pieces': pieces,
            'valid': not errors,
            'errors': errors,
        }
    return layouts


# ---------------------------------------------------------------------------
# HTML 骨架 + 交互脚本
# ---------------------------------------------------------------------------

def _build_html(cw, ch, rooms_svg, all_boards, stats, total_boards,
                total_full, total_cut, source_layouts):
    import json
    boards_json = json.dumps(all_boards, ensure_ascii=False)
    sources_json = json.dumps(source_layouts, ensure_ascii=False)
    margin_y = 50  # 房间标签高度偏移

    rooms_svg_blocks = []
    for i, (name, svg, x) in enumerate(rooms_svg):
        rooms_svg_blocks.append(
            f'<g transform="translate({x:.1f},{margin_y})">{svg}</g>'
        )
    rooms_svg_block = '\n'.join(rooms_svg_blocks)

    # 统计面板 HTML
    stats_rows = []
    for st in stats:
        stats_rows.append(
            f'<tr><td>{st["room"]}</td>'
            f'<td>{st["full"]}</td><td>{st["cut"]}</td>'
            f'<td><b>{st["total"]}</b></td></tr>'
        )
    stats_rows.append(
        f'<tr class="total"><td><b>合计</b></td>'
        f'<td>{total_full}</td><td>{total_cut}</td>'
        f'<td><b>{total_boards}</b></td></tr>'
    )
    stats_table = '\n'.join(stats_rows)

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>木地板铺装图</title>
<style>
  body {{ font-family: 'Microsoft YaHei', sans-serif; margin: 0; background: #f4f4f4; }}
  .header {{ background: #fff; padding: 14px 24px; box-shadow: 0 1px 4px rgba(0,0,0,.1);
             display: flex; align-items: center; gap: 16px; }}
  .header h1 {{ font-size: 18px; margin: 0; color: #333; }}
  .hint {{ color: #777; font-size: 12px; }}
  .stats-bar {{ background: #fff; padding: 12px 24px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  .stats {{ border-collapse: collapse; font-size: 13px; }}
  .stats th, .stats td {{ border: 1px solid #e6e6e6; padding: 6px 18px; text-align: center; }}
  .stats th {{ background: #f8f8f8; font-weight: 600; }}
  .stats td:first-child {{ text-align: left; }}
  .stats tr.total td {{ background: #fff7e0; }}
  .canvas-wrap {{ overflow: auto; padding: 20px; }}
  .room      {{ fill: #fafafa; stroke: #333; stroke-width: 3; }}
  .area      {{ fill: none; stroke: #999; stroke-width: 1.5; stroke-dasharray: 8,4; }}
  .obstacle  {{ fill: #ddd; fill-opacity: 0.75; stroke: #555; stroke-width: 2; }}
  .ob-x      {{ stroke: #555; stroke-width: 2; }}
  .board     {{ fill: #e8d5b0; stroke: #b8945c; stroke-width: 1; cursor: pointer; }}
  .board.stock-A {{ fill: #78c6b3; stroke: #2b7f73; }}
  .board.stock-B {{ fill: #b8a2e8; stroke: #6f55b5; }}
  .board.cut {{ fill: #d4b896; stroke: #c44; stroke-width: 1.6; }}
  .board.cut.stock-A {{ fill: #69b8a7; stroke: #c44; }}
  .board.cut.stock-B {{ fill: #aa93dc; stroke: #c44; }}
  .board:hover {{ stroke: #28a; stroke-width: 2.4; fill-opacity: 0.9; }}
  .board.hl   {{ fill: #ffd24a !important; stroke: #e00 !important; stroke-width: 2.6 !important; }}
  .board.dim  {{ opacity: 0.28; }}
  .stock-badge {{ fill: rgba(255,255,255,.88); stroke: rgba(0,0,0,.28); stroke-width: 1; pointer-events: none; }}
  .stock-label {{ fill: #222; font-size: 12px; font-weight: 700; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; pointer-events: none; }}
  .stock-A-chip {{ background: #78c6b3; color: #123; border: 1px solid #2b7f73; }}
  .stock-B-chip {{ background: #b8a2e8; color: #20123f; border: 1px solid #6f55b5; }}
  .dim       {{ fill: #666; font-size: 11px; font-family: sans-serif; text-anchor: middle; }}
  .room-lbl  {{ fill: #333; font-size: 16px; font-family: sans-serif; text-anchor: middle; font-weight: bold; }}
  .legend    {{ fill: #fff; stroke: #ccc; stroke-width: 1; }}
  .legend-t  {{ font-size: 10px; font-family: sans-serif; fill: #333; }}

  /* 弹窗 */
  .modal-mask {{ position: fixed; inset: 0; background: rgba(0,0,0,.45); display: none;
                 align-items: flex-start; justify-content: center; z-index: 100; padding-top: 8vh; }}
  .modal-mask.show {{ display: flex; }}
  .modal {{ background: #fff; border-radius: 10px; width: 720px; max-width: 94vw;
            max-height: 78vh; overflow: auto; box-shadow: 0 8px 30px rgba(0,0,0,.25); }}
  .modal-head {{ padding: 14px 20px; border-bottom: 1px solid #eee;
                 display: flex; justify-content: space-between; align-items: center; }}
  .modal-head h3 {{ margin: 0; font-size: 16px; }}
  .modal-close {{ cursor: pointer; background: #eee; border: none; border-radius: 6px;
                  width: 28px; height: 28px; font-size: 16px; }}
  .modal-body {{ padding: 16px 20px; }}
  .modal-info {{ font-size: 12px; color: #777; margin-bottom: 12px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ border: 1px solid #eee; padding: 7px 10px; text-align: center; }}
  th {{ background: #f8f8f8; font-weight: 600; }}
  tr.clicked {{ background: #fff3cd; }}
  .edge-T {{ color: #2a8; font-weight: 600; }}
  .edge-G {{ color: #c84; font-weight: 600; }}
  .edge-C {{ color: #e44; font-weight: 600; }}
  .diagram-title {{ font-size: 12px; color: #666; font-weight: 600; margin-bottom: 8px; }}
  .diagram {{ background: #fbfbfb; border: 1px solid #eee; border-radius: 6px;
              padding: 12px; margin-bottom: 14px; overflow-x: auto; }}
  .diagram svg {{ display: block; }}
  .diagram .board-fill {{ fill: #e8d5b0; stroke: #b8945c; stroke-width: 1; }}
  .diagram .board-fill.cut {{ fill: #d4b896; stroke: #c44; }}
  .diagram .kerf-line {{ stroke: #e44; stroke-width: 2; }}
  .diagram .waste-fill {{ fill: #eee; stroke: #bbb; stroke-width: 1; stroke-dasharray: 3,3; }}
  .diagram .dg-lbl {{ font-size: 9px; fill: #333; font-family: sans-serif; text-anchor: middle; }}
  .diagram .dg-dim {{ font-size: 8px; fill: #888; font-family: sans-serif; text-anchor: middle; }}
  .diagram .dg-source {{ font-size: 8px; fill: #999; font-family: sans-serif; }}
</style>
</head>
<body>
<div class="header">
  <h1>木地板铺装图</h1>
  <span class="hint">点击任意切割板：高亮同源关联板；再次点击或点击空白关闭。弹窗列出同源板四边榫槽属性。</span>
</div>
<div class="stats-bar">
  <table class="stats">
    <thead>
      <tr><th>房间</th><th>完整板</th><th>切割板</th><th>用板合计</th></tr>
    </thead>
    <tbody>
      {stats_table}
    </tbody>
  </table>
</div>
<div class="canvas-wrap">
<svg id="plan" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cw:.0f} {ch:.0f}" width="{cw:.0f}" height="{ch:.0f}" style="background:#fff;">
  <style>
    .room      {{ fill: #fafafa; stroke: #333; stroke-width: 3; }}
    .area      {{ fill: none; stroke: #999; stroke-width: 1.5; stroke-dasharray: 8,4; }}
    .obstacle  {{ fill: #ddd; fill-opacity: 0.75; stroke: #555; stroke-width: 2; }}
    .ob-x      {{ stroke: #555; stroke-width: 2; }}
    .board     {{ fill: #e8d5b0; stroke: #b8945c; stroke-width: 1; cursor: pointer; }}
    .board.stock-A {{ fill: #78c6b3; stroke: #2b7f73; }}
    .board.stock-B {{ fill: #b8a2e8; stroke: #6f55b5; }}
    .board.cut {{ fill: #d4b896; stroke: #c44; stroke-width: 1.6; }}
    .board.cut.stock-A {{ fill: #69b8a7; stroke: #c44; }}
    .board.cut.stock-B {{ fill: #aa93dc; stroke: #c44; }}
    .board:hover {{ stroke: #28a; stroke-width: 2.4; fill-opacity: 0.9; }}
    .board.hl   {{ fill: #ffd24a !important; stroke: #e00 !important; stroke-width: 2.6 !important; }}
    .board.dim  {{ opacity: 0.28; }}
    .stock-badge {{ fill: rgba(255,255,255,.88); stroke: rgba(0,0,0,.28); stroke-width: 1; pointer-events: none; }}
    .stock-label {{ fill: #222; font-size: 12px; font-weight: 700; font-family: sans-serif; text-anchor: middle; dominant-baseline: central; pointer-events: none; }}
    .dim       {{ fill: #666; font-size: 11px; font-family: sans-serif; text-anchor: middle; }}
    .room-lbl  {{ fill: #333; font-size: 16px; font-family: sans-serif; text-anchor: middle; font-weight: bold; }}
  </style>

  {rooms_svg_block}

  <!-- 图例 -->
  <g transform="translate({cw - 200:.0f},{ch - 80:.0f})">
    <rect x="-8" y="-6" width="180" height="52" rx="4" class="legend"/>
    <line x1="0" y1="8" x2="30" y2="8" class="edge-T" style="stroke:#2a8;stroke-width:3;"/>
    <text x="38" y="12" class="legend-t">公榫</text>
    <line x1="0" y1="20" x2="30" y2="20" style="stroke:#c84;stroke-width:3;stroke-dasharray:5,3;"/>
    <text x="38" y="24" class="legend-t">母榫</text>
    <line x1="0" y1="32" x2="30" y2="32" style="stroke:#e44;stroke-width:3;"/>
    <text x="38" y="36" class="legend-t">切割面</text>
    <rect x="96" y="0" width="18" height="14" class="board stock-A"/>
    <text x="120" y="12" class="legend-t">A 型板</text>
    <rect x="96" y="22" width="18" height="14" class="board stock-B"/>
    <text x="120" y="34" class="legend-t">B 型板</text>
  </g>
</svg>
</div>

<!-- 弹窗 -->
<div class="modal-mask" id="modalMask" onclick="closeModal(event)">
  <div class="modal" onclick="event.stopPropagation()">
    <div class="modal-head">
      <h3 id="modalTitle">同源切割板</h3>
      <button class="modal-close" onclick="closeModal()">×</button>
    </div>
    <div class="modal-body">
      <div class="modal-info" id="modalInfo"></div>
      <div class="diagram-title">从整板切割示意图（长×宽 mm）</div>
      <div class="diagram" id="sourceDiagram"></div>
      <table>
        <thead>
          <tr><th>#</th><th>房间</th><th>位号</th><th>尺寸(长×宽mm)</th><th>源号</th>
              <th>板型</th><th>铺装旋转</th><th>顶</th><th>右</th><th>底</th><th>左</th><th>类型</th></tr>
        </thead>
        <tbody id="modalBody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
const BOARDS = {boards_json};
const SOURCES = {sources_json};
let selectedRoot = null;

function clearSel() {{
  document.querySelectorAll('.board.hl, .board.dim').forEach(el => {{
    el.classList.remove('hl');
    el.classList.remove('dim');
  }});
  selectedRoot = null;
}}

function selectBoard(el) {{
  const root = el.dataset.root;
  if (!root) return;

  if (selectedRoot === root) {{
    clearSel();
    return;
  }}
  clearSel();
  selectedRoot = root;

  // 高亮同源，弱化其他
  document.querySelectorAll('.board').forEach(b => {{
    if (b.dataset.root === root) {{
      b.classList.add('hl');
    }} else {{
      b.classList.add('dim');
    }}
  }});

  showModal(el.dataset.label, root);
}}

function showModal(label, root) {{
  const related = BOARDS.filter(b => b.root === root);
  const clicked = related.find(b => b.label === label) || related[0];
  const clickedIdx = related.findIndex(b => b.label === label);

  document.getElementById('modalTitle').textContent =
    '同源切割板（源 ' + root + '）';
  document.getElementById('modalInfo').textContent =
    '共 ' + related.length + ' 块相关板，来自同一块源板。点击行对应被点击板。';

  const tbody = document.getElementById('modalBody');
  tbody.innerHTML = '';
  related.forEach((b, i) => {{
    const e = b.edges || {{ top:'?', right:'?', bottom:'?', left:'?' }};
    const cls = (i === clickedIdx) ? ' class="clicked"' : '';
    const edgeCls = v => v === '公榫' ? 'edge-T' : (v === '母榫' ? 'edge-G' : 'edge-C');
    tbody.innerHTML += '<tr' + cls + '>'
      + '<td>' + (i + 1) + '</td>'
      + '<td>' + b.room + '</td>'
      + '<td>' + b.label + '</td>'
      + '<td>' + b.len + '×' + b.wid + '</td>'
      + '<td>' + b.source + '</td>'
      + '<td>' + (b.stock_class || '-') + '</td>'
      + '<td>' + (b.source_rotation || 0) + '°</td>'
      + '<td class="' + edgeCls(e.top) + '">' + e.top + '</td>'
      + '<td class="' + edgeCls(e.right) + '">' + e.right + '</td>'
      + '<td class="' + edgeCls(e.bottom) + '">' + e.bottom + '</td>'
      + '<td class="' + edgeCls(e.left) + '">' + e.left + '</td>'
      + '<td>' + (b.is_cut ? '切割' : '完整') + '</td>'
      + '</tr>';
  }});

  renderSourceDiagram(root, label);
  document.getElementById('modalMask').classList.add('show');
}}

// 渲染"从整板切割"示意图
function renderSourceDiagram(root, clickedLabel) {{
  const container = document.getElementById('sourceDiagram');
  if (!SOURCES[root]) {{
    container.innerHTML = '<div style="color:#999;font-size:12px;">（无切割示意图数据）</div>';
    return;
  }}
  const src = SOURCES[root];
  const pieces = src.pieces;
  if (!pieces.length) {{
    container.innerHTML = '';
    return;
  }}
  const W = src.width;
  const L = src.length;
  const scale = 360 / L;
  const boardW = Math.max(54, W * scale);
  const boardH = L * scale;
  const padX = 110;
  const topPad = 55;
  const svgW = boardW + padX * 2;
  const svgH = boardH + topPad + 55;

  let s = '<svg width="' + svgW + '" height="' + svgH + '" viewBox="0 0 ' + svgW + ' ' + svgH + '">';

  // 整板轮廓背景
  s += '<rect x="' + padX + '" y="' + topPad + '" width="' + boardW + '" height="' + boardH + '" '
     + 'fill="#fafafa" stroke="#999" stroke-width="1.5" stroke-dasharray="4,3"/>';

  // 按根源板绝对二维坐标绘制，源板 y=0 位于图的底部。
  pieces.forEach((p, i) => {{
    const x = padX + p.x * scale;
    const y = topPad + (L - p.y - p.len) * scale;
    const w = Math.max(2, p.wid * scale);
    const h = Math.max(2, p.len * scale);
    const isCut = p.len < L - 0.5 || p.wid < W - 0.5 || p.shape_cut;
    const fillCls = isCut ? 'board-fill cut' : 'board-fill';
    const hl = (String(p.label) === String(clickedLabel)) ? ' style="fill:#ffd24a;stroke:#e00;stroke-width:2;"' : '';
    if (p.polygon && p.polygon.length) {{
      const points = p.polygon.map(point =>
        (padX + point[0] * scale).toFixed(1) + ',' +
        (topPad + (L - point[1]) * scale).toFixed(1)
      ).join(' ');
      s += '<polygon points="' + points + '" class="' + fillCls + '"' + hl + '/>';
    }} else {{
      s += '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + w.toFixed(1) + '" '
         + 'height="' + h.toFixed(1) + '" class="' + fillCls + '"' + hl + '/>';
    }}
    // 位号
    if (w > 16 && h > 12) {{
      s += '<text x="' + (x + w / 2).toFixed(1) + '" y="' + (y + h / 2 + 1).toFixed(1) + '" '
         + 'class="dg-lbl">位' + p.label + '</text>';
    }}
    s += '<text x="' + (padX + boardW + 8) + '" y="' + (y + h / 2 + 3).toFixed(1) + '" '
       + 'class="dg-dim">位' + p.label + ' ' + Math.round(p.len) + '×' + Math.round(p.wid) + '</text>';
  }});

  const status = src.valid ? '通过' : '失败：' + (src.errors || []).join('；');
  s += '<text x="' + padX + '" y="18" class="dg-source">源板 ' + root
     + ' · ' + (src.stock_class || '?') + ' 型 · 竖直基准 ' + Math.round(L) + '×' + Math.round(W) + 'mm</text>';
  s += '<text x="' + padX + '" y="36" class="dg-source">源板切割校验：' + status + '</text>';
  s += '<text x="' + (padX + boardW / 2) + '" y="' + (topPad - 8) + '" text-anchor="middle" class="dg-dim">顶（短边）</text>';
  s += '<text x="' + (padX + boardW / 2) + '" y="' + (topPad + boardH + 18) + '" text-anchor="middle" class="dg-dim">底（短边）</text>';

  s += '</svg>';
  container.innerHTML = s;
}}

function closeModal(e) {{
  if (e && e.target && e.target.id === 'modalMask') {{
    document.getElementById('modalMask').classList.remove('show');
    return;
  }}
  document.getElementById('modalMask').classList.remove('show');
}}

// 点击空白（SVG 背景）清除高亮
document.getElementById('plan').addEventListener('click', function (e) {{
  if (e.target === this) clearSel();
}});
</script>
</body>
</html>
"""
