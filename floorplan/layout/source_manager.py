"""
源板管理器 — 边感知的切割与池匹配。

每个池条目携带 PieceSpec（含四边属性），匹配时校验尺寸+四边。
切割操作自动推导两边四边继承。
"""

from ..models import (
    EdgeType, CutDirection, BoardEdges, ORIGINAL_EDGES, opposite_edge,
    PieceSpec, CutOperation, SourceBoard, RoomPlacement,
)


class PoolEntry:
    """池条目：一块可用余料 + 其四边属性"""
    __slots__ = ('piece',)
    def __init__(self, piece: PieceSpec):
        self.piece = piece

    @property
    def length(self) -> float:
        return self.piece.length

    @property
    def width(self) -> float:
        return self.piece.width

    @property
    def edges(self) -> BoardEdges:
        return self.piece.edges


class SourceBoardManager:
    """管理源板生命周期 + 边感知池"""

    def __init__(self, board_length: float, board_width: float, kerf: float = 1.0):
        self._L = board_length
        self._W = board_width
        self._K = kerf
        self._counter = 0
        self._new_boards = 0

        # 池
        self._length_pool: list[PoolEntry] = []   # 长度余料
        self._width_pool: list[PoolEntry] = []    # 宽度余料

        # 追踪
        self.source_boards: dict[str, SourceBoard] = {}
        self.all_pieces: dict[str, PieceSpec] = {}
        self.cut_operations: list[CutOperation] = []

    @property
    def total_new_boards(self) -> int:
        return self._new_boards

    # ── ID 生成 ──────────────────────────────────────────

    def _next_id(self, prefix: str = "源") -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    # ── 边推导 ──────────────────────────────────────────

    def _derive_edges(self, parent: PieceSpec, direction: CutDirection,
                      position: float, is_piece_a: bool) -> BoardEdges:
        """切割后推导片的新四边。

        is_piece_a=True: 近原点段（保留 parent.left/bottom）
        is_piece_a=False: 远端段（保留 parent.right/top）
        """
        pe = parent.edges
        if direction == CutDirection.LENGTH:
            # 竖切：切面垂直于长度轴 → 影响 left/right
            if is_piece_a:
                return BoardEdges(
                    top=pe.top, bottom=pe.bottom,
                    left=pe.left, right=EdgeType.CUT,
                )
            else:
                return BoardEdges(
                    top=pe.top, bottom=pe.bottom,
                    left=EdgeType.CUT, right=pe.right,
                )
        else:  # WIDTH
            # 横切：切面垂直于宽度轴 → 影响 top/bottom
            if is_piece_a:
                return BoardEdges(
                    top=EdgeType.CUT, bottom=pe.bottom,
                    left=pe.left, right=pe.right,
                )
            else:
                return BoardEdges(
                    top=pe.top, bottom=EdgeType.CUT,
                    left=pe.left, right=pe.right,
                )

    # ── 切割操作 ──────────────────────────────────────────

    def cut(self, parent: PieceSpec, direction: CutDirection,
            position: float, label_a: str, label_b: str = ""
            ) -> tuple[PieceSpec, PieceSpec | None]:
        """切割一块片，返回 (piece_a, piece_b_or_none)。

        piece_a 的长度/宽 = position（定位78等放置位置）。
        piece_b 是剩余部分，可入池。
        """
        bid = parent.source_board_id
        op_id = self._next_id("切")

        if direction == CutDirection.LENGTH:
            len_a = position
            len_b = parent.length - position - self._K
            piece_a = PieceSpec(
                piece_id=self._next_id("片"),
                source_board_id=bid,
                length=len_a, width=parent.width,
                edges=self._derive_edges(parent, direction, position, True),
                origin_x=parent.origin_x, origin_y=parent.origin_y,
            )
            piece_b = PieceSpec(
                piece_id=self._next_id("片") if len_b > 0.5 else "",
                source_board_id=bid,
                length=max(0, len_b), width=parent.width,
                edges=self._derive_edges(parent, direction, position, False),
                origin_x=parent.origin_x + position + self._K,
                origin_y=parent.origin_y,
            ) if len_b > 0.5 else None
        else:  # WIDTH
            wid_a = position
            wid_b = parent.width - position - self._K
            piece_a = PieceSpec(
                piece_id=self._next_id("片"),
                source_board_id=bid,
                length=parent.length, width=wid_a,
                edges=self._derive_edges(parent, direction, position, True),
                origin_x=parent.origin_x, origin_y=parent.origin_y,
            )
            piece_b = PieceSpec(
                piece_id=self._next_id("片") if wid_b > 0.5 else "",
                source_board_id=bid,
                length=parent.length, width=max(0, wid_b),
                edges=self._derive_edges(parent, direction, position, False),
                origin_x=parent.origin_x,
                origin_y=parent.origin_y + position + self._K,
            ) if wid_b > 0.5 else None

        # 记录
        self.all_pieces[piece_a.piece_id] = piece_a
        if piece_b and piece_b.piece_id:
            self.all_pieces[piece_b.piece_id] = piece_b

        op = CutOperation(
            cut_id=op_id, source_board_id=bid,
            direction=direction, position=position, kerf=self._K,
            piece_a=piece_a, piece_b=piece_b,
        )
        self.cut_operations.append(op)

        # 更新源板
        if bid in self.source_boards:
            self.source_boards[bid].cuts.append(op)
            self.source_boards[bid].pieces_produced.append(piece_a.piece_id)
            if piece_b:
                self.source_boards[bid].pieces_produced.append(piece_b.piece_id)

        return piece_a, piece_b

    # ── 新板 ──────────────────────────────────────────────

    def new_board(self, label: str) -> PieceSpec:
        """开一块新整板，返回代表整板的 PieceSpec。"""
        self._new_boards += 1
        bid = self._next_id("源")
        pid = self._next_id("片")
        piece = PieceSpec(
            piece_id=pid,
            source_board_id=bid,
            length=self._L, width=self._W,
            edges=ORIGINAL_EDGES,
            origin_x=0, origin_y=0,
        )
        self.all_pieces[pid] = piece
        self.source_boards[bid] = SourceBoard(
            board_id=bid,
            original_length=self._L, original_width=self._W,
            original_edges=ORIGINAL_EDGES,
        )
        self.source_boards[bid].pieces_produced.append(pid)
        return piece

    # ── 池操作 ──────────────────────────────────────────

    def add_to_length_pool(self, piece: PieceSpec):
        """将片加入长度池（竖切剩余部分，保留全宽+两原始长边）"""
        if piece.length > 0.5 and piece.is_usable:
            self._length_pool.append(PoolEntry(piece))

    def add_to_width_pool(self, piece: PieceSpec):
        """将片加入宽度池（横切剩余部分，一原始长边）"""
        if piece.width > 0.5 and piece.is_usable:
            self._width_pool.append(PoolEntry(piece))

    def take_from_length_pool(self, needed_len: float,
                               required_edges: BoardEdges) -> PieceSpec | None:
        """从长度池找匹配片（尺寸+四边）。

        找到后从池中移除，切割使用部分，剩余回池。
        """
        best_idx = -1
        best_len = float('inf')
        for i, entry in enumerate(self._length_pool):
            if entry.length >= needed_len - self._K and entry.length < best_len:
                if _edges_usable(entry.edges, required_edges):
                    best_idx = i
                    best_len = entry.length

        if best_idx < 0:
            return None

        entry = self._length_pool.pop(best_idx)
        piece = entry.piece

        if needed_len >= piece.length - 0.5:
            return piece  # 整段使用

        # 需要切割：分离使用段和剩余段
        used, remain = self.cut(piece, CutDirection.LENGTH, needed_len, "", "")
        if remain:
            self.add_to_length_pool(remain)
        return used

    def take_from_width_pool(self, needed_w: float,
                              required_edges: BoardEdges) -> PieceSpec | None:
        """从宽度池找匹配片（尺寸+四边）。宪法第三条：不可再次宽切。

        整段使用，多余宽度废弃。
        """
        best_idx = -1
        best_w = float('inf')
        for i, entry in enumerate(self._width_pool):
            if entry.width >= needed_w - self._K and entry.width < best_w:
                if _edges_usable(entry.edges, required_edges):
                    best_idx = i
                    best_w = entry.width

        if best_idx < 0:
            return None

        entry = self._width_pool.pop(best_idx)
        piece = entry.piece

        if needed_w >= piece.width - 0.5:
            return piece  # 整段使用

        # 需要横切：使用 needed_w，剩余废弃（第三条：不可再宽切）
        used, _ = self.cut(piece, CutDirection.WIDTH, needed_w, "", "")
        return used


# ── 边匹配 ──────────────────────────────────────────────

def _edges_usable(piece_edges: BoardEdges, required: BoardEdges) -> bool:
    """检查 piece 的四边是否满足 required 的需求。

    - required=CUT（靠墙/伸缩缝）：piece 的任何边都可以
    - required=TONGUE/GROOVE：piece 必须有对应的对边
    - piece=CUT：只能对应 required=CUT 的位置
    """
    for side in ['top', 'bottom', 'left', 'right']:
        pe = getattr(piece_edges, side)
        re = getattr(required, side)

        if re == EdgeType.CUT:
            continue  # 位置靠墙，什么边都行
        if pe == EdgeType.CUT:
            return False  # 位置需要榫槽，但片是切割面
        if pe != re:
            return False  # TONGUE vs GROOVE 不匹配
    return True


def derive_required_edges(neighbors: dict) -> BoardEdges:
    """从邻接关系推导铺装位的四边需求。

    neighbors: {'left': 'WALL'|position_id, 'right': ..., 'top': ..., 'bottom': ...}

    规则：
    - WALL → required=CUT（切割面可接受，靠墙）
    - 有邻居 → 需要与邻居的对应边相反（TONGUE↔GROOVE）
    """
    # 简化版：在铺装网格生成时直接计算
    # 这里只提供基础逻辑
    return BoardEdges(
        top=EdgeType.GROOVE,     # 默认：具体由调用方推导
        bottom=EdgeType.TONGUE,
        left=EdgeType.GROOVE,
        right=EdgeType.TONGUE,
    )
