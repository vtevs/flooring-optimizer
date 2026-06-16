"""
数据模型 — 所有模块共享的 dataclass 定义。

数据流：
    YAML → Config → Room.build() → Shapely Polygon
                        ↓
    Board + Polygon → LayoutEngine.layout() → LayoutResult (list of PlacedBoard)
                        ↓
    LayoutResult → SVGRenderer.render() → SVG file
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Pattern(Enum):
    ALIGNED = "aligned"
    STAGGERED = "staggered"
    HERRINGBONE = "herringbone"
    FIVE_BOARD_SQUARE = "five-board-square"
    L_TRIPLE = "l-triple"


class NotchPosition(Enum):
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"


# ---------------------------------------------------------------------------
# 配置相关
# ---------------------------------------------------------------------------

@dataclass
class NotchConfig:
    """L 形房间的缺口定义"""
    width: float
    depth: float
    position: NotchPosition


@dataclass
class ObstacleConfig:
    """不可铺装区域（柜子/固定家具等）"""
    name: str = ""
    type: str = "rectangle"  # "rectangle" | "polygon"
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    length: float = 0.0
    points: list = field(default_factory=list)


@dataclass
class RoomConfig:
    """房间配置（解析后的中间表示）"""
    type: str  # "rectangle" | "l-shaped" | "polygon"
    width: float = 0.0
    length: float = 0.0
    notch: Optional[NotchConfig] = None
    points: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)


@dataclass
class BoardConfig:
    """地板规格"""
    length: float
    width: float
    thickness: float = 12.0


@dataclass
class InstallationConfig:
    """铺装参数"""
    pattern: Pattern
    direction: float = 0.0       # 0/90/45 度
    stagger_ratio: float = 0.33  # 仅错缝


@dataclass
class EdgeConfig:
    """收边参数"""
    baseboard_width: float = 15.0
    expansion_gap: float = 10.0
    board_gap: float = 0.0


@dataclass
class OutputConfig:
    """输出参数"""
    file: str = "floor_plan.svg"
    scale: str = "auto"          # "auto" | "1:50" | ...
    show_dimensions: bool = True
    show_labels: bool = True
    show_grid: bool = False
    color_scheme: str = "wood"


@dataclass
class RoomSpec:
    """多房间模式中的单个房间"""
    name: str = ""
    type: str = "rectangle"
    width: float = 0.0
    length: float = 0.0
    notch: Optional[NotchConfig] = None
    points: list = field(default_factory=list)
    obstacles: list = field(default_factory=list)


@dataclass
class MultiRoomResult:
    """多房间铺装结果"""
    room_results: list = field(default_factory=list)   # list[(RoomSpec, LayoutResult)]
    shared_pool_groups: list = field(default_factory=list)  # 跨房间共享的切割组
    total_boards: int = 0
    total_area: float = 0.0
    combined_room_area: float = 0.0
    utilization: float = 0.0


@dataclass
class Config:
    """顶层配置"""
    room: Optional[RoomConfig] = None     # 单房间模式
    rooms: Optional[list] = None          # list[RoomSpec] 多房间模式
    board: BoardConfig = None
    installation: InstallationConfig = None
    edges: EdgeConfig = field(default_factory=EdgeConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    kerf: float = 1.0


# ---------------------------------------------------------------------------
# 四边属性系统
# ---------------------------------------------------------------------------

class EdgeType(Enum):
    TONGUE = "tongue"    # 公榫（凸）
    GROOVE = "groove"    # 母榫（凹）
    CUT = "cut"          # 切割面（平，无榫槽）


class CutDirection(Enum):
    LENGTH = "length"    # 竖切 — 沿长度方向切断，切面垂直于长度轴
    WIDTH = "width"      # 横切 — 沿宽度方向切断，切面垂直于宽度轴


@dataclass(frozen=True)
class BoardEdges:
    """一块板片的四边属性"""
    top: EdgeType
    bottom: EdgeType
    left: EdgeType
    right: EdgeType


# 原始整板的四边（出厂状态）
ORIGINAL_EDGES = BoardEdges(
    top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
    left=EdgeType.GROOVE, right=EdgeType.TONGUE,
)


def opposite_edge(e: EdgeType) -> EdgeType:
    """对边类型：TONGUE↔GROOVE, CUT→CUT"""
    if e == EdgeType.TONGUE:
        return EdgeType.GROOVE
    elif e == EdgeType.GROOVE:
        return EdgeType.TONGUE
    return EdgeType.CUT


def rotate_edges(edges: BoardEdges, rotation: float) -> BoardEdges:
    """旋转后的物理四边（CCW，与Shapely/SVG一致）。

    rotation=0:  物理=固有 (top→+y, bottom→-y, left→-x, right→+x)
    rotation=90: 板逆时针转90°(竖放), 固有底→物理右, 固有顶→物理左,
                 固有左→物理底, 固有右→物理顶
    即 物理(T,B,L,R) = 固有(R, L, T, B) = (T, G, G, T)
    """
    if rotation == 0 or abs(rotation) < 0.1:
        return edges
    if abs(rotation - 90) < 0.1:
        return BoardEdges(
            top=edges.right, bottom=edges.left,
            left=edges.top, right=edges.bottom,
        )
    return edges


# ---------------------------------------------------------------------------
# 源板管理 — 切割操作与板片
# ---------------------------------------------------------------------------

@dataclass
class PieceSpec:
    """一块切割产生的板片"""
    piece_id: str               # 唯一 ID
    source_board_id: str        # 所属源板 ID
    length: float               # 实际长度 mm
    width: float                # 实际宽度 mm
    edges: BoardEdges           # 四边属性
    origin_x: float = 0.0       # 在源板中的原点 x
    origin_y: float = 0.0       # 在源板中的原点 y

    @property
    def is_usable(self) -> bool:
        """宪法第三条：上下皆CUT或左右皆CUT → 不可用"""
        e = self.edges
        if e.top == EdgeType.CUT and e.bottom == EdgeType.CUT:
            return False
        if e.left == EdgeType.CUT and e.right == EdgeType.CUT:
            return False
        return True


@dataclass
class CutOperation:
    """一次切割操作：一块原料 → 两段 + 锯缝"""
    cut_id: str                 # 操作唯一 ID
    source_board_id: str        # 所属源板
    direction: CutDirection
    position: float             # 切割位置（距原料原点距离）
    kerf: float                 # 锯缝宽度
    piece_a: PieceSpec          # 近原点段
    piece_b: PieceSpec          # 远端段


@dataclass
class SourceBoard:
    """一块物理地板的完整生命周期"""
    board_id: str               # "源78"
    original_length: float      # 出厂长度
    original_width: float       # 出厂宽度
    original_edges: BoardEdges  # 出厂四边
    cuts: list = field(default_factory=list)       # 切割历史
    pieces_produced: list = field(default_factory=list)  # 产生的所有 piece_id


# ---------------------------------------------------------------------------
# 铺装方案 — 房间中的位置
# ---------------------------------------------------------------------------

@dataclass
class RoomPlacement:
    """房间中一个铺装位"""
    position_id: str            # "位78"
    room_id: str = ""           # 房间 ID
    x: float = 0.0              # 中心点 x
    y: float = 0.0              # 中心点 y
    rotation: float = 0.0       # 角度
    length: float = 0.0         # 需要长度
    width: float = 0.0          # 需要宽度
    required_edges: BoardEdges = None  # 此位需要的四边
    assigned_piece_id: str = "" # 分配的 piece_id
    neighbor_left: str = ""     # "WALL" | position_id
    neighbor_right: str = ""
    neighbor_top: str = ""
    neighbor_bottom: str = ""


@dataclass
class RoomPavingPlan:
    """一个房间的完整铺装方案"""
    room_id: str = ""
    placements: list = field(default_factory=list)  # list[RoomPlacement]
    source_boards: list = field(default_factory=list)  # list[SourceBoard]


# ---------------------------------------------------------------------------
# 铺装结果（兼容旧模型）
# ---------------------------------------------------------------------------

@dataclass
class PlacedBoard:
    """一块已放置的地板"""
    x: float                    # 中心点 x (mm)
    y: float                    # 中心点 y (mm)
    rotation: float             # 旋转角度 (度)
    length: float               # 实际长度 (可能被切割)
    width: float                # 实际宽度
    is_cut: bool = False        # 是否为切割板
    cut_polygon: Optional[list] = None  # 切割后的顶点 [(x,y), ...]
    label: str = ""             # 编号标签（铺装位编号）
    source_id: str = ""         # 来源板编号（同一块板切出的多块共享）
    width_waste: float = 0.0    # 宽度裁剪废弃面积 mm²


@dataclass
class CuttingPiece:
    """一块切割板的组成信息"""
    label: str                  # 放置标签
    length: float               # 使用长度 mm
    width: float = 0.0          # 使用宽度 mm (0 = 使用板宽)


@dataclass
class CuttingGroup:
    """一次切割操作 — 每块源板可能有多次操作（原始切+复用切）。

    一次操作 = 对一块矩形原料做一次切割，产出若干片。
    原料可以是整板(910×148)、长度尾料(454×148)、宽切废料(455×31)。
    每次复用（从池中取料）创建新的 CuttingGroup，通过 parent_source_id 追溯。
    """
    source_id: str              # 本次操作唯一 ID
    pieces: list                # list[CuttingPiece] 本次操作产出的片
    total_length: float         # 本次操作的原料长度
    used_length: float          # 使用长度
    waste_length: float         # 废弃长度（长度方向，本操作后剩余）
    width_waste: float = 0.0    # 宽度裁剪废弃面积 mm²（宽度方向）
    parent_source_id: str = ""  # 追溯：原始源板 ID（复用操作时有值）
    total_width: float = 0.0    # 本次操作的原料宽度（0=全宽）
    edges: any = None           # BoardEdges | None 四边属性


@dataclass
class LayoutStatistics:
    """铺装统计"""
    total_boards: int = 0       # 总用板数
    full_boards: int = 0        # 完整板数
    cut_boards: int = 0         # 切割板数（被裁切过的板）
    total_area: float = 0.0     # 总用料面积 mm²
    waste_area: float = 0.0     # 废料面积 mm²
    room_area: float = 0.0      # 房间可铺面积 mm²
    utilization: float = 0.0    # 利用率 = room_area / total_area
    cutting_groups: list = None  # list[CuttingGroup] 切割方案


@dataclass
class LayoutResult:
    """一次铺装排样的完整结果"""
    boards: list  # list[PlacedBoard]
    statistics: LayoutStatistics
    pattern: Pattern
    start_offset: tuple = (0.0, 0.0)
