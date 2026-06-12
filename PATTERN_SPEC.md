# 拼法描述规范 v1

用 YAML 描述任意木地板铺装拼法。引擎读取此描述生成铺装方案。

---

## 核心概念

```
拼法 = 单元(Unit) + 平铺规则(Tiling) + 约束(Constraints)

单元 = 一组板在最小重复矩形内的摆放
平铺 = 单元如何在房间内重复排列
约束 = 切割、榫槽、复用规则
```

## 完整示例：对拼 (Aligned)

```yaml
# ============================================================
# 拼法: 对拼 (直铺)
# ============================================================
pattern:
  name: aligned
  label: 对拼

  # ── 单元定义 ──
  unit:
    width: "{board.length}"        # 单元宽 = 板长
    height: "{board.width}"        # 单元高 = 板宽
    boards:
      - id: A
        x: 0                       # 单元内 x 偏移
        y: 0                       # 单元内 y 偏移
        rotation: 0                # 旋转角度 (0/90)
        use: full                  # full | partial

  # ── 平铺规则 ──
  tiling:
    mode: grid                     # grid | stagger | herringbone | custom
    direction: "{direction}"       # 铺装方向 0 或 90
    row_step: "{board.width + gap}" # 行步进
    col_step: "{board.length + gap}" # 列步进

  # ── 约束 ──
  constraints:
    length_cut: true               # 允许长切
    width_cut: true                # 允许宽切
    reuse_length_waste: true       # 长度废料可复用
    reuse_width_waste: true        # 宽度废料可复用
    stagger_ratio: null            # 错缝比例 (仅 stagger 模式)
```

## 完整示例：错缝 1/3

```yaml
pattern:
  name: staggered
  label: 错缝 1/3

  unit:
    width: "{board.length}"
    height: "{board.width * 2}"
    boards:
      - id: A
        x: 0
        y: 0
        rotation: 0
        use: full
      - id: B
        x: "{board.length * 0.33}"
        y: "{board.width}"
        rotation: 0
        use: full

  tiling:
    mode: stagger
    direction: "{direction}"
    row_step: "{board.width + gap}"
    col_step: "{board.length + gap}"
    stagger_ratio: 0.33

  constraints:
    length_cut: true
    width_cut: true
    reuse_length_waste: true
    reuse_width_waste: true
    stagger_ratio: 0.33
```

## 完整示例：人字拼 45°

```yaml
pattern:
  name: herringbone
  label: 人字拼 45°

  unit:
    width: "{board.length * 0.707 * 2}"
    height: "{board.length * 0.707}"
    boards:
      - id: A
        x: 0
        y: 0
        rotation: 45
        use: full
      - id: B
        x: "{board.length * 0.707}"
        y: 0
        rotation: -45
        use: full

  tiling:
    mode: grid
    direction: 45
    row_step: "{unit.height}"
    col_step: "{unit.width}"

  constraints:
    length_cut: true
    width_cut: false              # 人字拼边界裁剪特殊处理
    reuse_length_waste: false
    reuse_width_waste: false
```

## 字段说明

### unit (单元)

| 字段 | 类型 | 说明 |
|------|------|------|
| `width` | float | 单元宽度 mm，可用 `{board.length}`, `{board.width}` 等变量 |
| `height` | float | 单元高度 mm |
| `boards` | list | 单元内的板列表 |

**boards 子字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 板标识 |
| `x` | float | 单元内 x 坐标 (左上角) |
| `y` | float | 单元内 y 坐标 (左上角) |
| `rotation` | float | 旋转角度 (0/90/45/-45) |
| `use` | str | `full`(整板) 或 `partial`(可裁切) |

### tiling (平铺)

| 字段 | 类型 | 说明 |
|------|------|------|
| `mode` | enum | `grid`(网格) / `stagger`(错缝) / `herringbone`(人字) / `custom`(自定义) |
| `direction` | float | 铺装方向 (0/90/45) |
| `row_step` | float | 行步进 mm |
| `col_step` | float | 列步进 mm |
| `stagger_ratio` | float | 错缝比例 (仅 stagger) |
| `offset_x` | float | 行间 x 偏移 (仅 custom) |
| `offset_y` | float | 行间 y 偏移 (仅 custom) |

### constraints (约束)

| 字段 | 类型 | 说明 |
|------|------|------|
| `length_cut` | bool | 是否允许长切 (行末裁短) |
| `width_cut` | bool | 是否允许宽切 (末行裁窄) |
| `reuse_length_waste` | bool | 长切废料是否入池复用 |
| `reuse_width_waste` | bool | 宽切废料是否入池复用 |
| `flip_allowed` | bool | 是否允许翻转 180° (几乎总是 false) |

---

## 如何描述新拼法

### 步骤 1：画单元

在方格纸上画出最小的重复单元。标注每块板的位
置、方向和尺寸。

```
示例: 5拼方砖的单元
┌──────────────────────┬──────────────────────┐
│  单元 A (横排)        │  单元 B (竖排)        │
│  ┌──┬──┬──┬──┬──┐   │  ┌──┬──┬──┬──┬──┐   │
│  │ 1│ 2│ 3│ 4│ 5│   │  │  │  │  │  │  │   │
│  └──┴──┴──┴──┴──┘   │  │ 1│ 2│ 3│ 4│ 5│   │
│                      │  │  │  │  │  │  │   │
│  5块 440×88 横排     │  └──┴──┴──┴──┴──┘   │
│                      │  5块 440×88 竖排     │
└──────────────────────┴──────────────────────┘
```

### 步骤 2：写 YAML

```yaml
pattern:
  name: my_pattern
  label: 我的拼法

  unit:
    width: 440
    height: 440
    boards:
      - id: A1
        x: 0
        y: 0
        rotation: 0
        use: full
      - id: A2
        x: 0
        y: 88
        rotation: 0
        use: full
      # ... 更多板

  tiling:
    mode: grid
    direction: 0
    row_step: 440
    col_step: 440

  constraints:
    length_cut: true
    width_cut: true
    reuse_length_waste: true
    reuse_width_waste: true
```

### 步骤 3：写文字说明

如果拼法有特殊逻辑（如棋盘式交替、榫槽方向限制），
用文字描述：

```
排列规则:
  - 单元 A 和单元 B 棋盘式交替
  - (row + col) % 2 == 0 → 横排单元
  - (row + col) % 2 == 1 → 竖排单元

榫槽约束:
  - 横排单元内: 板与板之间公榫对母榫
  - 竖排单元内: 同上
  - 单元边界: 靠墙侧切割边允许
```

---

## 变量引用

YAML 中可使用 `{variable}` 引用变量，引擎会替换：

| 变量 | 含义 |
|------|------|
| `{board.length}` | 板长 mm |
| `{board.width}` | 板宽 mm |
| `{board.thickness}` | 板厚 mm |
| `{gap}` | 板间缝 mm |
| `{direction}` | 铺装方向 |

---

## 现有拼法速查

| 拼法 | mode | 单元 | 特点 |
|------|------|------|------|
| 对拼 | grid | 1板 | 行间无偏移 |
| 错缝 | stagger | 2行×1板 | 行间偏移 stagger_ratio×板长 |
| 人字拼45° | grid | 2板90°交错 | 45°旋转密铺 |
| 5拼方砖 | grid | 2单元交替 | 横排/竖排棋盘式 |
