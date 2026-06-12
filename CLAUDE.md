# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

木地板铺装图生成工具 (Floor Plan Generator) — CLI 工具，输入 YAML 配置，输出 SVG 铺装图，最小化地板损耗。

- L 形房间（两个正交矩形布尔并）
- 4 种铺装：对拼 / 错缝 / 人字拼 45° / 5拼方砖棋盘式
- 地板有榫槽方向约束（切割尾料不可翻转复用）
- 所有尺寸单位 mm

## 设计文档

**[DESIGN.md](DESIGN.md)** — 完整数据结构设计（四边属性、切割继承、源板生命周期、铺装方案）。
**[CONSTITUTION.md](CONSTITUTION.md)** — 不可违反的铺装宪法。
每次运行自动执行 `floorplan/verify.py` 校验。

## 核心铺装原则 (Core Principles)

### 1. 榫槽方向约束 (Tongue-and-Groove)

地板四边：底边=公榫(tongue)，顶边=母榫(groove)，左边=母榫(groove)，右边=公榫(tongue)。

```
      母榫 (groove)
    ┌─────────────┐
    │             │
母榫│   地板 L×W  │公榫 (tongue)
    │             │
    └─────────────┘
      公榫 (tongue)
```

- **非边界处**：只能公榫接母榫（tongue→groove），不可公-公或母-母
- **边界处**：整板可任意边靠墙；切割板的切割边必须靠墙（切割面无榫槽）

### 2. 切割与复用 (Cut & Reuse)

切割一块板 = 沿长度方向在某处垂直切断 → 产生两段：
- 一段：原始边(有榫/槽) + 切割边(平，无榫槽)
- 另一段：切割边(平) + 原始边(有榫/槽)

**复用规则**：
- 切割边只能靠墙（房间边界）
- 原始边保留榫槽属性，按规则 1 对接
- 同一块板切出的多段，总长度 ≤ 板长
- 切割产生的一段用于当前位置的行尾，余料入池；池中余料可用于后续行首

### 3. 铺装要求

- 可铺区域（房间 - 踢脚线 - 伸缩缝）必须**完全铺满**
- 目标：满铺前提下**用板最少**
- 板与板之间留缝可配（默认 0）

### 4. 铺装图标注

SVG 图上每块板需标注：
- 公榫边（绿色实线）、母榫边（橙色虚线）
- 切割边（红色实线）
- 序号（完整板=独立号，切割板=源板号，同源同号）
- 切割板需显示原板完整轮廓 + 被切掉废料区

### 5. 切割方案文档

切割复用关系单独输出 TXT，记录：源板→多块放置位置，每块长度，总废弃量。

## Commands

```bash
# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行（生成铺装图）
python -m floorplan config.example.yaml
python -m floorplan config.example.yaml -o output/

# 测试
pytest tests/ -v
pytest tests/test_layout.py -v -k "test_aligned"
```

## Architecture

```
YAML config → config.py (load+validate)
  → geometry/room.py (build_room → Shapely Polygon, compute_layout_area)
  → optimize.py (enumerate start offsets, pick best utilization)
    → layout/<pattern>.py (one engine per pattern, all implement LayoutEngine.layout())
  → svg/renderer.py (LayoutResult → SVG file)
```

### Key files

| File | Role |
|------|------|
| [config.py](floorplan/config.py) | YAML 加载 + 字段校验 → Config dataclass |
| [models.py](floorplan/models.py) | 所有 dataclass: Config, BoardConfig, PlacedBoard, LayoutResult, LayoutStatistics |
| [geometry/room.py](floorplan/geometry/room.py) | L形房间 → Shapely Polygon, 内缩(踢脚线+伸缩缝) |
| [layout/base.py](floorplan/layout/base.py) | LayoutEngine 抽象基类 + 注册表 |
| [layout/aligned.py](floorplan/layout/aligned.py) | 对拼：按行填充，端头切割 |
| [layout/staggered.py](floorplan/layout/staggered.py) | 错缝：行间偏移 board.length × stagger_ratio |
| [layout/herringbone.py](floorplan/layout/herringbone.py) | 45°人字拼：密铺网格 → 房间求交 → 边界裁剪 |
| [layout/five_board.py](floorplan/layout/five_board.py) | 5拼方砖：方砖单元棋盘式交替 |
| [optimize.py](floorplan/optimize.py) | 枚举 start_offset 网格，选利用率最高 |
| [svg/renderer.py](floorplan/svg/renderer.py) | LayoutResult → SVG 文件 |
| [cli.py](floorplan/cli.py) | Click CLI 主入口 |
| [config.example.yaml](config.example.yaml) | 带注释的配置示例 |

### Data flow

1. `Config` (parsed YAML) → `build_room()` → Shapely `Polygon`
2. `Polygon` + `edges` → `compute_layout_area()` → inset `Polygon`
3. `Polygon` + `BoardConfig` + `Pattern` → `optimize()` → `LayoutResult`
4. `LayoutResult` + `OutputConfig` → `render()` → SVG file

### Key constraints

- **榫槽方向**: 地板有公榫/母槽，切割后的剩余板不能翻转 180° 复用（当前版本简化为直接计为损耗）
- **伸缩缝默认值**: 地暖房 10mm，板间缝 0.3mm，均可配置
- **错缝比例**: 默认 1/3，可配置 0~1 任意值
- **Scales**: 内部计算以 mm 为单位，SVG 输出用 `auto` 缩放

### Adding a new pattern

1. Create `floorplan/layout/<name>.py` with a class extending `LayoutEngine`
2. Implement `layout(room, board, start_offset, direction, **kwargs) → LayoutResult`
3. Decorate with `@register(Pattern.<NAME>)`
