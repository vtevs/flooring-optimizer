"""
命令行入口

Usage:
    python -m floorplan config.yaml
    python -m floorplan config.yaml -o output/
"""

import sys
from pathlib import Path

import click

from .config import load_config
from .geometry.room import build_room, compute_layout_area
from .optimize import optimize
from .svg.renderer import render


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("-o", "--output", default=None, help="输出目录 (默认: 当前目录)")
def main(config_file: str, output: str | None):
    """木地板铺装图生成工具

    读取 YAML 配置文件，生成最优铺装方案并输出 SVG 铺装图。
    """
    # 1. 加载配置
    click.echo(f"加载配置: {config_file}")
    config = load_config(config_file)

    # 多房间模式
    if config.rooms:
        _run_multi_room(config, output)
        return

    # 2. 构建房间几何
    room = build_room(config.room)
    layout_area = compute_layout_area(
        room,
        config.edges.baseboard_width,
        config.edges.expansion_gap,
    )
    click.echo(
        f"房间面积: {room.area/1e6:.2f} m²  "
        f"可铺面积: {layout_area.area/1e6:.2f} m²"
    )

    # 3. 优化排样
    click.echo(f"铺装方式: {config.installation.pattern.value}  "
               f"方向: {config.installation.direction}°")
    click.echo("正在计算最优排样...")

    result = optimize(
        layout_area,
        config.board,
        config.installation.pattern,
        direction=config.installation.direction,
        stagger_ratio=config.installation.stagger_ratio,
        kerf=config.kerf,
        material_type=config.material.type,
        require_full_board_at_room_corner=(
            config.installation.require_full_board_at_room_corner
        ),
        require_full_board_at_room_bottom_left=(
            config.installation.require_full_board_at_room_bottom_left
        ),
    )

    # 4. 输出统计
    s = result.statistics
    click.echo(f"总用板: {s.total_boards}  完整: {s.full_boards}  切割: {s.cut_boards}")
    click.echo(f"利用率: {s.utilization*100:.1f}%  损耗率: {(1-s.utilization)*100:.1f}%")

    # 5. 确定输出目录
    out_dir = Path(output) if output else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 5.1 切割方案 TXT
    _write_cutting_plan(result, out_dir, config)

    # 5.2 渲染 SVG
    out_path = out_dir / config.output.file
    render(result, config.room, config.output, out_path)
    click.echo(f"铺装图已保存: {out_path}")

    # 5.3 校验
    from .verify import verify_layout
    verr = verify_layout(result, config)
    if verr:
        click.secho("⚠ 校验发现问题:", fg="yellow")
        for e in verr:
            click.echo(f"  {e}")
    else:
        click.secho("✓ 校验通过", fg="green")


def _write_cutting_plan(result, out_dir, config):
    """输出切割方案 TXT 文件"""
    lines = _format_cutting_groups(result.statistics, config)
    txt_path = out_dir / "cutting_plan.txt"
    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    click.echo(f"切割方案: {txt_path}")


def _format_cutting_groups(s, config, room_label="", reuse_info=None) -> list[str]:
    """格式化切割方案为文本行列表。

    Args:
        s: LayoutStatistics
        config: Config
        room_label: 多房间模式房间名
        reuse_info: {source_id: [(label, length_mm, width_mm), ...]} 跨房间复用的尾料
    """
    board = config.board
    prefix = f"[{room_label}] " if room_label else ""
    lines = []
    if room_label:
        lines.append(f"--- {room_label} ---")
        lines.append(f"用板: {s.total_boards}  完整板: {s.full_boards}  切割板: {s.cut_boards}")
    else:
        lines.append("=" * 60)
        lines.append("木地板铺装 — 切割方案")
        lines.append("=" * 60)
        lines.append(f"地板规格: {board.length:.0f}×{board.width:.0f}×{board.thickness:.0f}mm")
        lines.append(f"铺装方式: {config.installation.pattern.value}")
        lines.append(f"总用板: {s.total_boards}  完整板: {s.full_boards}  切割板: {s.cut_boards}")
        lines.append(f"利用率: {s.utilization*100:.1f}%  损耗率: {(1-s.utilization)*100:.1f}%")
    lines.append("")

    # 完整板
    full_groups = [g for g in s.cutting_groups
                   if (not g.parent_source_id and len(g.pieces) == 1
                       and g.waste_length < 0.5 and g.width_waste < 10
                       and (g.pieces[0].width <= 0
                            or g.pieces[0].width >= board.width - 0.5))]
    lines.append(f"完整板 ({len(full_groups)} 块):")
    lines.append(f"  放置编号: {', '.join(g.pieces[0].label for g in full_groups[:20])}")
    if len(full_groups) > 20:
        lines.append(f"  ... 共 {len(full_groups)} 块")
    lines.append("")

    # 切割板：区分原始切（parent=""）和复用（parent!=""）
    all_cut = [g for g in s.cutting_groups if g not in full_groups]
    primary_cut = [g for g in all_cut if not g.parent_source_id]
    reuse_cut = [g for g in all_cut if g.parent_source_id]

    if primary_cut:
        lines.append(f"切割板 ({len(primary_cut)} 块):")
        lines.append("-" * 50)
        for g in primary_cut:
            _format_one_group(g, board, config.kerf, lines)
        lines.append("")

    if reuse_cut:
        # 按 parent_source_id 分组
        from collections import defaultdict
        by_parent = defaultdict(list)
        for g in reuse_cut:
            by_parent[g.parent_source_id].append(g)
        lines.append(f"复用切割 ({len(reuse_cut)} 次, {len(by_parent)} 块源板):")
        lines.append("-" * 50)
        for parent_id, groups in by_parent.items():
            for g in groups:
                _format_one_group(g, board, config.kerf, lines, prefix=f"←{parent_id} ")
        lines.append("")

    # 复用池中尾料（跨房间）
    if reuse_info:
        lines.append(f"复用池中尾料 ({len(reuse_info)} 块源板):")
        lines.append("-" * 50)
        bw = board.width
        for source_id, pieces in reuse_info.items():
            pw = pieces[0][2] if pieces[0][2] > 0 else bw
            pieces_desc = ", ".join(
                f"位{p[0]}({p[1]:.0f}×{(p[2] if p[2] > 0 else bw):.0f}mm)"
                for p in pieces
            )
            used_total = sum(p[1] for p in pieces)
            lines.append(f"  [{source_id}] {pieces_desc}  使用{used_total:.0f}×{pw:.0f}mm")
        lines.append("")

    # 废料汇总
    waste_lines = _format_waste_summary(s.cutting_groups, board, config.kerf, room_label)
    if waste_lines:
        lines.extend(waste_lines)

    lines.append("=" * 60)
    return lines


def _format_waste_summary(cutting_groups, board, kerf, room_label="") -> list[str]:
    """从切割组收集所有废料并格式化。"""
    bw = board.width
    waste_items = []

    for cg in cutting_groups:
        # 长度废料
        if cg.waste_length > 0.5 and not cg.parent_source_id:
            w = cg.total_width if cg.total_width > 0 else bw
            waste_items.append({
                'source_id': cg.source_id,
                'length': cg.waste_length,
                'width': w,
                'type': '长度废料',
                'edges': _derive_waste_edges(cg, is_width_waste=False),
            })

        # 宽度废料
        if cg.width_waste > 10:
            tl = cg.total_length
            ww = cg.width_waste / tl if tl > 0 else 0
            waste_items.append({
                'source_id': cg.source_id,
                'length': tl,
                'width': ww,
                'type': '宽度废料',
                'edges': _derive_waste_edges(cg, is_width_waste=True),
            })

    if not waste_items:
        return []

    lines = []
    prefix = f"[{room_label}] " if room_label else ""
    lines.append(f"{prefix}废料汇总 ({len(waste_items)} 条):")
    lines.append("-" * 50)

    total_area = 0
    for w in waste_items:
        area = w['length'] * w['width']
        total_area += area
        e = w['edges']
        if e:
            edge_str = (f"顶={_edge_char(e.top)} 底={_edge_char(e.bottom)} "
                        f"左={_edge_char(e.left)} 右={_edge_char(e.right)}")
        else:
            edge_str = "四边=?"
        lines.append(
            f"  [{w['source_id']}] {w['length']:.0f}×{w['width']:.0f}mm "
            f"({w['type']}) [{edge_str}]"
        )

    lines.append(f"  废料总面积: {total_area/1e6:.4f} m²")
    lines.append("")
    return lines


def _edge_char(e) -> str:
    """边类型缩写: T=公榫 G=母榫 C=切割面"""
    if e is None:
        return "?"
    return str(e.value)[0].upper()


def _format_one_group(g, board, kerf, lines, prefix=""):
    """格式化单个 CuttingGroup 为切割方案行。"""
    bw = board.width
    total_l = g.total_length
    # 当前被切板的实际宽度（整板=原板宽，切割板=剩余宽度）
    piece_w = g.total_width if g.total_width > 0 else bw
    n_pieces = len(g.pieces)

    pieces_desc = ", ".join(
        f"位{p.label}({p.length:.0f}×{(p.width if p.width > 0 else piece_w):.0f}mm)"
        for p in g.pieces
    )

    # 四边属性标注
    edge_str = ""
    if hasattr(g, 'edges') and g.edges:
        e = g.edges
        edge_str = f" [{_edge_char(e.top)}{_edge_char(e.bottom)}{_edge_char(e.left)}{_edge_char(e.right)}]"
    elif g.parent_source_id:
        edge_str = " [复用]"

    pieces_desc += edge_str

    used_l = g.used_length
    has_width_cut = g.width_waste > 10
    is_combined = has_width_cut and used_l < total_l - 0.5

    if is_combined:
        pw = g.pieces[0].width if g.pieces[0].width > 0 else piece_w
        used_w = pw
    elif has_width_cut:
        total_piece_width = sum((p.width if p.width > 0 else piece_w) for p in g.pieces)
        n_width_cuts = max(0, len(g.pieces) - 1)
        used_w = total_piece_width + n_width_cuts * kerf
        used_l = total_l
    else:
        used_w = piece_w

    remaining = total_l - used_l
    has_waste_piece = remaining > kerf + 0.5

    if is_combined:
        length_cut_count = 1 if has_waste_piece else 0
        width_cut_count = 1
        waste_l = max(0, total_l - used_l - kerf * length_cut_count) if length_cut_count > 0 else 0
        waste_w = (max(0, piece_w - used_w - kerf * width_cut_count)
                   if width_cut_count > 0 else 0)
    else:
        length_cut_count = n_pieces if has_waste_piece else max(0, n_pieces - 1)
        width_cut_count = 1 if has_width_cut else 0
        waste_l = max(0, total_l - used_l - kerf * length_cut_count) if length_cut_count > 0 else 0
        waste_w = max(0, piece_w - used_w - kerf * width_cut_count) if width_cut_count > 0 else 0
        if waste_l > 0 and width_cut_count == 0:
            waste_w = piece_w
        if waste_w > 0 and length_cut_count == 0:
            waste_l = total_l

    # 锯缝跟随当前被切板尺寸
    kerf_parts = []
    if length_cut_count > 0:
        kerf_parts.append(f"长切{length_cut_count}次 {length_cut_count*kerf:.0f}×{piece_w:.0f}mm")
    if width_cut_count > 0:
        kerf_parts.append(f"宽切{width_cut_count}次 {total_l:.0f}×{width_cut_count*kerf:.0f}mm")

    parts = [f"使用{used_l:.0f}×{used_w:.0f}mm"]
    if waste_l > 0.5 or waste_w > 0.5:
        parts.append(f"废料{waste_l:.0f}×{waste_w:.0f}mm")
    if kerf_parts:
        parts.append(f"锯缝 {' '.join(kerf_parts)}")
    size_info = "  ".join(parts)

    lines.append(f"  {prefix}[{g.source_id}] {pieces_desc}  {size_info}")


def _run_multi_room(config, output):
    """多房间模式：共享尾料池，综合损耗最低"""
    from .multi_optimize import optimize_multi

    click.echo(f"多房间模式: {len(config.rooms)} 个房间")
    for rs in config.rooms:
        click.echo(f"  {rs.name}: {rs.width:.0f}×{rs.length:.0f}mm")

    click.echo(f"铺装方式: {config.installation.pattern.value}  "
               f"方向: {config.installation.direction}°")
    if getattr(config.board, 'stock_class_policy', '') == 'supplier-ab-vertical':
        click.echo("正在计算 A/B 源板、旋转、邻边与切割复用的联合优化方案...")
    else:
        click.echo("正在计算最优综合方案（枚举房间顺序）...")
    result = optimize_multi(config.rooms, config.board, config.edges, config.kerf,
                            installation=config.installation,
                            material_type=config.material.type)

    # 综合利用率 = 房间总面积 / (总用板数 × 单板面积)
    board_area = config.board.length * config.board.width
    combined_area = result.combined_room_area
    total_board_area = result.total_boards * board_area
    util = combined_area / total_board_area if total_board_area > 0 else 0

    s = result
    click.echo(f"\n综合结果:")
    click.echo(f"  总用板: {s.total_boards}  综合利用率: {util*100:.1f}%  损耗率: {(1-util)*100:.1f}%")
    click.echo(f"  综合可铺面积: {combined_area/1e6:.2f} m²")
    for line in _supplier_stock_summary(result):
        click.echo(f"  {line}")
    if getattr(result, 'purchase_boards', 0):
        purchase_area = result.purchase_boards * board_area
        purchase_util = combined_area / purchase_area if purchase_area else 0
        click.echo(
            f"  采购口径利用率: {purchase_util*100:.1f}%  "
            f"损耗率: {(1-purchase_util)*100:.1f}%"
        )

    for rs, room_result in result.room_results:
        rs_obj = room_result.statistics
        if getattr(config.board, 'stock_class_policy', '') == 'supplier-ab-vertical':
            click.echo(f"  {rs.name}: {_supplier_room_summary(room_result)}")
        else:
            click.echo(f"  {rs.name}: {rs_obj.total_boards}板")

    # 输出切割方案
    out_dir = Path(output) if output else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    # 切割方案 TXT
    txt_path = out_dir / "cutting_plan.txt"
    lines = ["=" * 60, "多房间木地板铺装 — 综合切割方案", "=" * 60]
    lines.append(f"地板规格: {config.board.length:.0f}×{config.board.width:.0f}×{config.board.thickness:.0f}mm")
    lines.append(f"铺装方式: {config.installation.pattern.value}  方向: {config.installation.direction}°")
    if config.installation.pattern.value == 'staggered':
        lines.append(f"错缝比例: {config.installation.stagger_ratio}")
    lines.append(f"综合总用板: {result.total_boards}  利用率: {util*100:.1f}%  损耗率: {(1-util)*100:.1f}%")
    lines.extend(_supplier_stock_summary(result))
    if getattr(result, 'purchase_boards', 0):
        purchase_area = result.purchase_boards * board_area
        purchase_util = combined_area / purchase_area if purchase_area else 0
        lines.append(
            f"采购口径利用率: {purchase_util*100:.1f}%  "
            f"损耗率: {(1-purchase_util)*100:.1f}%"
        )
    lines.append("")

    if getattr(config.board, 'stock_class_policy', '') == 'supplier-ab-vertical':
        for rs, room_result in result.room_results:
            lines.extend([
                f"--- {rs.name} ---",
                _supplier_room_summary(room_result),
                "",
            ])
        lines.extend(_format_supplier_source_plan(result, config))
    else:
        for rs, room_result in result.room_results:
            reuse = getattr(room_result, 'reuse_info', None)
            room_lines = _format_cutting_groups(
                room_result.statistics, config,
                room_label=rs.name, reuse_info=reuse,
            )
            lines.extend(room_lines)

        # 综合废料汇总
        lines.extend(_format_total_waste(result, config))

    lines.append("=" * 60)
    txt_path.write_text('\n'.join(lines), encoding='utf-8')
    click.echo(f"切割方案: {txt_path}")

    # 渲染所有房间到一个交互式 HTML
    from .svg.html_renderer import render_multi_html
    out_path = _multi_room_plan_path(out_dir, config.output)
    render_multi_html(result, config, out_path)
    click.echo(f"铺装图(HTML): {out_path}")

    # 校验
    from .verify import verify_multi
    verr = verify_multi(result, config)
    if verr:
        click.secho("⚠ 校验发现问题:", fg="yellow")
        for e in verr:
            click.echo(f"  {e}")
    else:
        click.secho("✓ 校验通过", fg="green")


def _multi_room_plan_path(out_dir: Path, output_config) -> Path:
    """Return the multi-room HTML plan path regardless of legacy SVG config."""
    path = out_dir / output_config.file
    if path.suffix.lower() != ".html":
        path = path.with_suffix(".html")
    return path


def _supplier_stock_summary(result) -> list[str]:
    counts = getattr(result, 'stock_counts', None) or {}
    if not counts:
        return []
    return [
        f"A 型源板: {counts.get('A', 0)}  B 型源板: {counts.get('B', 0)}  "
        f"实际消耗: {result.total_boards}",
        f"按 1:1 配板采购: {getattr(result, 'purchase_boards', 0)}",
    ]


def _supplier_room_summary(room_result) -> str:
    full_pieces = sum(not board.is_cut for board in room_result.boards)
    cut_pieces = len(room_result.boards) - full_pieces
    return (
        f"铺装片: {len(room_result.boards)}（完整{full_pieces} / 切割{cut_pieces}）  "
        f"本房间计入源板: {room_result.statistics.total_boards}"
    )


def _format_supplier_source_plan(result, config) -> list[str]:
    """按联合求解后的绝对坐标输出 A/B 源板切割方案。"""
    from collections import defaultdict
    from shapely.geometry import Polygon, box as sbox
    from .source_validation import validate_source_rectangles

    by_root = defaultdict(list)
    for room, room_result in result.room_results:
        boards = {str(board.label): board for board in room_result.boards}
        for group in room_result.statistics.cutting_groups:
            root = group.root_source_id or group.source_id
            for piece in group.pieces:
                by_root[root].append((room.name, group, piece,
                                      boards.get(str(piece.label))))

    source_length = config.board.length
    source_width = config.board.width
    source_area = source_length * source_width
    cut_sources = []
    for root, entries in by_root.items():
        if len(entries) > 1:
            cut_sources.append((root, entries))
            continue
        _, _, piece, _ = entries[0]
        piece_width = piece.source_width or piece.width or source_width
        piece_length = piece.source_length or piece.length
        source_polygon = list(piece.source_polygon or [])
        shape_cut = bool(
            source_polygon and
            Polygon(source_polygon).symmetric_difference(sbox(
                piece.source_x, piece.source_y,
                piece.source_x + piece_width,
                piece.source_y + piece_length,
            )).area > 1e-6
        )
        if (abs(piece.source_x) > 1e-6 or abs(piece.source_y) > 1e-6 or
                abs(piece_width - source_width) > 1e-6 or
                abs(piece_length - source_length) > 1e-6 or shape_cut):
            cut_sources.append((root, entries))

    lines = [
        "=== A/B 源板严格切割坐标 ===",
        "坐标基准: 源板竖放，左下角=(0,0)，x 沿板宽，y 沿板长",
        f"源板尺寸: width={source_width:g}mm, length={source_length:g}mm, "
        f"kerf={config.kerf:g}mm",
        f"发生切割或复用的源板: {len(cut_sources)} 张",
        "-" * 60,
    ]
    total_unused_area = 0.0
    for root, entries in sorted(cut_sources, key=lambda item: item[0]):
        stock_classes = {group.stock_class for _, group, _, _ in entries
                         if group.stock_class}
        stock_class = next(iter(stock_classes), "?")
        rectangles = []
        used_area = 0.0
        for _, _, piece, _ in entries:
            width = piece.source_width or piece.width or source_width
            length = piece.source_length or piece.length
            rectangles.append({
                'label': piece.label,
                'x': piece.source_x,
                'y': piece.source_y,
                'wid': width,
                'len': length,
                'polygon': list(piece.source_polygon or []),
            })
            used_area += (
                Polygon(piece.source_polygon).area
                if piece.source_polygon else width * length
            )
        validation_errors = validate_source_rectangles(
            rectangles, source_length, source_width, config.kerf,
        )
        if len(stock_classes) != 1:
            validation_errors.append("同源板 A/B 类型不一致")
        validation = "通过" if not validation_errors else "失败: " + "; ".join(validation_errors)
        lines.append(f"[{root}] {stock_class} 型  源板切割坐标校验: {validation}")
        for room_name, _, piece, board in sorted(
                entries, key=lambda item: (item[2].source_y, item[2].source_x)):
            width = piece.source_width or piece.width or source_width
            length = piece.source_length or piece.length
            rotation = getattr(board, 'source_rotation', None)
            rotation_text = "?" if rotation is None else f"{rotation:g}°"
            edges = getattr(board, 'display_edges', None)
            if edges is None:
                edge_text = "顶=? 右=? 底=? 左=?"
            else:
                edge_text = (
                    f"顶={_edge_char(edges.top)} 右={_edge_char(edges.right)} "
                    f"底={_edge_char(edges.bottom)} 左={_edge_char(edges.left)}"
                )
            lines.append(
                f"  位{piece.label} [{room_name}] "
                f"x={piece.source_x:g}, y={piece.source_y:g}, "
                f"width={width:g}, length={length:g}mm  "
                f"铺装旋转={rotation_text}  {edge_text}"
            )
            if piece.source_polygon:
                source_rect = sbox(
                    piece.source_x, piece.source_y,
                    piece.source_x + width, piece.source_y + length,
                )
                polygon = Polygon(piece.source_polygon)
                if polygon.symmetric_difference(source_rect).area > 1e-6:
                    points = " ".join(
                        f"({x:g},{y:g})" for x, y in piece.source_polygon
                    )
                    lines.append(f"    异形切割轮廓: {points}")
        unused_area = max(0.0, source_area - used_area)
        total_unused_area += unused_area
        lines.append(f"  未铺入面积(含锯缝): {unused_area/1e6:.4f} m²")
    lines.extend([
        "-" * 60,
        f"上述源板未铺入总面积(含锯缝): {total_unused_area/1e6:.4f} m²",
        "",
    ])
    return lines


def _derive_waste_edges(cg, is_width_waste: bool):
    """从切割操作推导废料的四边。

    废料是使用片的互补件，切割边在对面。
    原始板四边 = G-T-G-T。

    切割区布局:
      纯长切: used(right=CUT), waste(left=CUT)
      纯宽切: used(top=CUT),  waste(bottom=CUT)
      组合切:
        used(right=CUT, top=CUT)
        长度废料(left=CUT, top=CUT)  ← 也在宽切区内
        宽度废料(bottom=CUT, right=CUT) ← 也在长切区内
    """
    from floorplan.models import EdgeType, BoardEdges, ORIGINAL_EDGES
    if cg.edges is None:
        return None

    orig = ORIGINAL_EDGES  # G-T-G-T
    has_length_cut = cg.waste_length > 0.5 or len(cg.pieces) > 1
    has_width_cut = cg.width_waste > 10
    is_combined = has_length_cut and has_width_cut

    if is_width_waste and is_combined:
        # 组合切的宽度废料：在长切区+宽切区
        return BoardEdges(
            top=orig.top,                # GROOVE
            bottom=EdgeType.CUT,          # 宽切
            left=orig.left,              # GROOVE
            right=EdgeType.CUT,           # 长切
        )
    elif is_width_waste:
        # 纯宽切：仅bottom=CUT
        return BoardEdges(
            top=orig.top, bottom=EdgeType.CUT,
            left=orig.left, right=orig.right,
        )
    elif is_combined:
        # 组合切的长度废料：在宽切区内 → top也被宽切影响
        return BoardEdges(
            top=EdgeType.CUT,             # 宽切影响！
            bottom=orig.bottom,           # TONGUE
            left=EdgeType.CUT,            # 长切
            right=orig.right,            # TONGUE
        )
    elif has_length_cut:
        # 纯长切：仅left=CUT
        return BoardEdges(
            top=orig.top, bottom=orig.bottom,
            left=EdgeType.CUT, right=orig.right,
        )
    return None


def _format_total_waste(multi_result, config) -> list[str]:
    """综合所有房间的废料汇总。"""
    bw = config.board.width
    all_waste = []
    for rs, room_result in multi_result.room_results:
        for cg in room_result.statistics.cutting_groups:
            if cg.waste_length > 0.5 and not cg.parent_source_id:
                w = cg.total_width if cg.total_width > 0 else bw
                waste_edges = _derive_waste_edges(cg, is_width_waste=False)
                all_waste.append({
                    'room': rs.name, 'source_id': cg.source_id,
                    'length': cg.waste_length, 'width': w,
                    'type': '长度废料', 'edges': waste_edges,
                })
            if cg.width_waste > 10:
                tl = cg.total_length
                ww = cg.width_waste / tl if tl > 0 else 0
                waste_edges = _derive_waste_edges(cg, is_width_waste=True)
                all_waste.append({
                    'room': rs.name, 'source_id': cg.source_id,
                    'length': tl, 'width': ww,
                    'type': '宽度废料', 'edges': waste_edges,
                })

    if not all_waste:
        return []

    lines = ["", "综合废料汇总:", "-" * 50]
    total_area = 0
    for w in all_waste:
        area = w['length'] * w['width']
        total_area += area
        e = w['edges']
        if e:
            edge_str = (f"顶={_edge_char(e.top)} 底={_edge_char(e.bottom)} "
                        f"左={_edge_char(e.left)} 右={_edge_char(e.right)}")
        else:
            edge_str = "?"
        lines.append(
            f"  [{w['room']}] [{w['source_id']}] {w['length']:.0f}×{w['width']:.0f}mm "
            f"({w['type']}) [{edge_str}]"
        )
    lines.append(f"  综合废料总面积: {total_area/1e6:.4f} m²")
    board_area = config.board.length * config.board.width
    lines.append(f"  折合整板: {total_area/board_area:.1f} 块")
    lines.append("")
    return lines


if __name__ == "__main__":
    main()
