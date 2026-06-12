# 数据结构与方案设计

## 1. 四边属性

```
       top (上边)
    ┌─────────────┐
    │             │
 L  │   地板片     │  R
    │   L × W     │
    │             │
    └─────────────┘
      bottom (下边)
```

每边类型：

| 类型 | 符号 | 含义 | 连接规则 |
|------|------|------|---------|
| `TONGUE` | T | 公榫（凸） | 只能接 `GROOVE` |
| `GROOVE` | G | 母榫（凹） | 只能接 `TONGUE` |
| `CUT` | C | 切割面（平） | 只能靠墙，不可接任何榫槽 |

原始整板：`top=GROOVE, bottom=TONGUE, left=GROOVE, right=TONGUE`

---

## 2. 核心数据结构

### 2.1 BoardEdges — 四边

```python
@dataclass(frozen=True)
class BoardEdges:
    top: EdgeType
    bottom: EdgeType
    left: EdgeType
    right: EdgeType

# 原始整板四边
ORIGINAL_EDGES = BoardEdges(
    top=GROOVE, bottom=TONGUE,
    left=GROOVE, right=TONGUE
)
```

### 2.2 SourceBoard — 源板

```python
@dataclass
class SourceBoard:
    """一块物理地板，追踪其完整生命周期"""
    board_id: str           # "源78"
    original_length: float  # 910mm
    original_width: float   # 148mm
    original_edges: BoardEdges  # 出厂四边

    # 生命周期：切割历史
    cuts: list[CutOperation]       # 按时间顺序的切割操作
    pieces_produced: list[str]     # 产生的所有 piece_id
    waste_discarded: float         # 最终不可用的废料面积
```

### 2.3 CutOperation — 切割操作

```python
@dataclass
class CutOperation:
    """一次切割：一块原料 → 两段（+锯缝）"""
    cut_id: str             # 操作唯一ID
    source_board_id: str    # 所属源板
    parent_piece_id: str    # 被切的片 ID（首次切时="原始板"）
    direction: CutDirection # LENGTH(竖切) 或 WIDTH(横切)
    position: float         # 切在哪个位置（距该片原点的距离）
    kerf: float             # 锯缝宽度

    # 产出
    piece_a: PieceSpec      # 第一段（长/宽 = position）
    piece_b: PieceSpec      # 第二段（剩余部分）

@dataclass
class PieceSpec:
    """切割产生的片描述"""
    piece_id: str           # 唯一 ID
    length: float           # 实际长度
    width: float            # 实际宽度
    edges: BoardEdges       # 四边属性（继承+切割）
    origin_in_parent: tuple # 在父片中的原点位置 (x, y)
    is_usable: bool         # 是否可用（宪法第三条：双CUT边不可用）
```

### 2.4 切割边继承规则

切割发生在一根轴上，新切割面垂直于该轴。

**竖切（LENGTH cut, 沿长度方向切，切面垂直于长度轴）：**

```
切前:                         切后:
┌──────────────────┐          ┌───────┬───────┐
│                  │          │       │       │
│  top: G          │    →     │   A   │   B   │
│  bottom: T       │          │       │       │
│  left: G  right:T│          └───────┴───────┘
└──────────────────┘           A.right = CUT ←新切面
                               B.left  = CUT ←新切面
                               其他边继承不变
```

**横切（WIDTH cut, 沿宽度方向切，切面垂直于宽度轴）：**

```
切前:                         切后:
┌──────────────────┐          ┌──────────────────┐
│  top: G          │          │  A: top = CUT    │ ←新切面
│                  │    →     ├──────────────────┤
│  bottom: T       │          │  B: bottom = CUT │ ←新切面
└──────────────────┘          └──────────────────┘
                               其他边继承不变
```

**继承规则表：**

| 切割方向 | 切出片 | top | bottom | left | right |
|---------|--------|-----|--------|------|-------|
| LENGTH  | A (近原点) | 继承 | 继承 | 继承 | **CUT** |
| LENGTH  | B (远端)   | 继承 | 继承 | **CUT** | 继承 |
| WIDTH   | A (近原点) | **CUT** | 继承 | 继承 | 继承 |
| WIDTH   | B (远端)   | 继承 | **CUT** | 继承 | 继承 |

**可用性判断（宪法第三条）：**
- 片有四边中有 ≥2 条原始边（TONGUE 或 GROOVE）→ 可用
- 片的四边中只有 ≤1 条原始边 → 不可用（含 ≥3 条 CUT）
- 实际上：只要不是"两条对面的长边都是 CUT"或"两条对面的短边都是 CUT"就行...

更精确的判断：
- 如果 top==CUT AND bottom==CUT → 不可用（无法与上下行连接）
- 如果 left==CUT AND right==CUT → 不可用（无法与同行相邻板连接）

### 2.5 RoomPlacement — 房间铺装方案

```python
@dataclass
class RoomPlacement:
    """一个铺装位 — 房间中一块板应该放置的位置"""
    position_id: str        # "位78"
    room_id: str            # "A" / "B" / "C"

    # 位置
    x: float                # 中心点 x (mm)
    y: float                # 中心点 y (mm)
    rotation: float         # 旋转角度
    length: float           # 需要的长度 (mm)
    width: float            # 需要的宽度 (mm)

    # 此位置的四边需求（从邻接关系推导）
    required_edges: BoardEdges

    # 匹配的板片
    assigned_piece_id: str  # 放置的 piece_id

    # 邻接关系
    neighbor_left: str      # 左边邻位的 position_id (或 "WALL")
    neighbor_right: str
    neighbor_top: str
    neighbor_bottom: str

@dataclass
class RoomPavingPlan:
    """一个房间的完整铺装方案"""
    room_id: str
    room_width: float
    room_length: float
    layout_area: Polygon
    placements: list[RoomPlacement]     # 所有铺装位
    source_boards_used: list[str]       # 使用的源板 ID 列表
```

### 2.6 铺装位四边需求推导

从铺装方向和邻接关系推导每个位需要的四边：

```
direction=90° (板沿y轴, 行沿x轴):

行0 (y方向第一行, bottom靠墙):
  位1 (行首, left靠墙):
    required: top=TONGUE(接上行,但无上行→靠墙→CUT),
              bottom=GROOVE(接下行→TONGUE),
              left=CUT(靠墙), right=TONGUE(接位2)

  位2 (行中):
    required: top=TONGUE, bottom=GROOVE,
              left=GROOVE(接位1的TONGUE), right=TONGUE(接位3)

  位N (行末, right靠墙):
    required: top=TONGUE, bottom=GROOVE,
              left=GROOVE(接位N-1), right=CUT(靠墙)

末行 (width-cut, bottom靠墙):
  位M (行中):
    required: top=TONGUE(接上行GROOVE), bottom=CUT(靠墙),
              left=GROOVE, right=TONGUE
```

**推导算法：**

```python
def derive_required_edges(position, paving_direction, neighbors):
    edges = {}
    for side in ['top', 'bottom', 'left', 'right']:
        neighbor = neighbors[side]
        if neighbor == 'WALL':
            edges[side] = CUT   # 靠墙=切割面也可以
        elif neighbor == 'GAP':
            edges[side] = CUT   # 伸缩缝=切割面也可以
        else:
            # 有邻居板：需要匹配对方的反边
            neighbor_edge = get_edge(neighbor, opposite(side))
            edges[side] = opposite(neighbor_edge)
            # TONGUE ↔ GROOVE
    return BoardEdges(**edges)

def opposite(edge: EdgeType) -> EdgeType:
    return {TONGUE: GROOVE, GROOVE: TONGUE, CUT: CUT}[edge]
```

### 2.7 边匹配校验

```python
def can_place(piece: PieceSpec, placement: RoomPlacement) -> bool:
    """检查 piece 的四边是否满足 placement 的需求"""
    pe = piece.edges
    re = placement.required_edges

    for side in ['top', 'bottom', 'left', 'right']:
        p_edge = getattr(pe, side)
        r_edge = getattr(re, side)

        if r_edge == CUT:
            # 位置需要靠墙 → piece 的 CUT 边或原始边都可以
            continue
        elif p_edge == CUT:
            # piece 是切割面但位置需要榫槽 → 不匹配！
            return False
        elif p_edge != r_edge:
            # TONGUE vs GROOVE 不匹配
            return False

    return True
```

---

## 3. 源板管理方案

### 3.1 完整生命周期

以源78为例：

```
阶段0: 原始整板
┌──────────────────────────────────────┐
│ SourceBoard: 源78                    │
│ original: 910×148mm                  │
│ edges:  top=G, bottom=T, left=G, right=T │
└──────────────────────────────────────┘

阶段1: 竖切 Cut#1 (LENGTH, position=529, kerf=1)
┌──────────────────┬──┬─────────────────────┐
│ Piece A          │K │ Piece B             │
│ 529×148mm        │E │ 380×148mm           │
│ top: G (继承)     │R │ top: G (继承)        │
│ bottom: T (继承)  │F │ bottom: T (继承)     │
│ left: G (继承)    │  │ left: CUT (新切面)   │
│ right: CUT (新切面)│  │ right: T (继承)      │
│ ✓ 可用            │  │ ✓ 可用               │
└──────────────────┴──┴─────────────────────┘

Piece B → 入长度池 (380mm, full width)
  edges: G-T-C-T → 可作为行首板(左CUT靠墙)或接在TONGUE后(G接T)

阶段2: 横切 Cut#2 (WIDTH, position=16, kerf=1) on Piece A
┌──────────────────────────┐
│ Piece A1: 529×16mm       │ ← 位78
│ top: CUT (新切面)         │
│ bottom: T (继承)          │
│ left: G (继承)            │
│ right: CUT (从Cut#1继承)  │
│ ✓ 可用 (bottom=T, left=G)│
├──────────────────────────┤
│         KERF 1mm         │
├──────────────────────────┤
│ Piece A2: 529×131mm      │ ← 宽切废料 → 位79?
│ top: G (继承)             │
│ bottom: CUT (新切面)      │
│ left: G (继承)            │
│ right: CUT (从Cut#1继承)  │
│ ✓ 可用 (top=G, left=G)   │
│ ⚠ right=CUT → 只能放行末! │
└──────────────────────────┘

阶段3: Piece B 被位144复用
  take(253mm) from length pool
  Piece B1: 253×148mm
    edges: G-T-C-T (继承自Piece B)
    可作为行首板(left=CUT靠墙→位144是行首?)
```

### 3.2 源板管理器

```python
class SourceBoardManager:
    """管理所有源板的切割历史和板片库存"""

    source_boards: dict[str, SourceBoard]  # board_id → SourceBoard
    piece_inventory: dict[str, PieceSpec]  # piece_id → PieceSpec
    length_pool: list[PoolEntry]           # 长度池 (edges已确定)
    width_pool: list[PoolEntry]            # 宽度池 (edges已确定)

    def cut(self, piece_id, direction, position, kerf) -> tuple[PieceSpec, PieceSpec]:
        """切割一块片，返回两段。自动推导四边。"""

    def take_from_pool(self, needed_len, required_edges) -> PieceSpec | None:
        """从池中取料，需满足尺寸+四边需求"""

    def can_match(self, piece, placement) -> bool:
        """检查片能否放在该位置"""
```

---

## 4. 铺装引擎改造

### 4.1 铺装流程（新）

```
1. 计算可铺区域 (room → layout_area)
2. 生成铺装网格 (rows × columns → list[RoomPlacement])
   - 每个 placement 有: position_id, x, y, rotation, required_length, required_width
   - 推导每个 placement 的 required_edges (从邻接关系)
3. 按行、按列遍历 placements:
   a. 获取当前 placement 的 required_edges
   b. 先在长度池中找匹配的片 (需要尺寸+四边都匹配)
   c. 再在宽度池中找匹配的片
   d. 都没有 → 开新源板，切割
   e. 切割产生的余料入对应池（记录四边属性）
   f. 校验: piece.edges 满足 placement.required_edges
4. 输出: RoomPavingPlan + 切割方案
```

### 4.2 池匹配规则

```python
def take_from_length_pool(needed_len, required_edges):
    for entry in length_pool:
        if entry.length >= needed_len:
            piece = entry.piece_spec
            # 检查 piece 的四边是否满足 required_edges
            # 注意: CUT边在 required=CUT 或靠墙时可用
            if edges_match(piece.edges, required_edges):
                return piece
    return None
```

### 4.3 位79问题的解决方案

Piece A2 (529×131mm) edges: G-C-G-C (top=G, bottom=C, left=G, right=C)

此片只能放在:
- right=CUT AND left=CUT → 行宽恰好=529mm的唯一板 (left/right都靠墙)
- right=CUT → 行末位 (right靠墙, left需GROOVE)
- left=CUT → 行首位 (left靠墙, right需TONGUE... 但right=CUT! → 只能right也靠墙)

所以 Piece A2 只能放在**左右都靠墙**的位置，即**整行只有这一块板的窄房间**。

对于位79（如果是常规行中位置），Piece A2 的 `right=CUT` 无法提供 TONGUE，校验失败 → 不会匹配 → 开新板。

---

## 5. 数据流总览

```
YAML config
    ↓
房间几何 (layout_area)
    ↓
铺装网格生成 → list[RoomPlacement]
    │              每个带 required_edges + required_length/width
    ↓
逐位铺装循环:
    placement → 查池(长度池+宽度池, 尺寸+四边匹配)
             → 无匹配: 开新板, 切割
             → 切割产生余料 → 入池(带四边属性)
             → 放置 piece, 记录到 placement
    ↓
输出:
    RoomPavingPlan (placements list)
    SourceBoardManager (切割历史)
    ↓
SVG 渲染 + cutting_plan.txt
```

---

## 6. 宪法约束在数据结构中的体现

| 宪法 | 数据结构体现 |
|------|------------|
| 1.1 不可翻转 | `Placement.rotation` ∈ {0, 90}，不允许180° |
| 1.2 公入母 | `can_place()`: TONGUE ↔ GROOVE 匹配校验 |
| 2.1 切割面靠墙 | `required_edges` 中 CUT 边必须对应 WALL/GAP |
| 3.1 宽切一次 | 宽切后 piece 的 width_pool_entry 不再入池再次宽切 |
| 3.3 双切面不可用 | `is_usable`: top=CUT AND bottom=CUT → False |
| 5.1 满铺 | 所有 placement 都有 assigned_piece |
| 8 行起始对齐 | pos ≥ layout_min |
