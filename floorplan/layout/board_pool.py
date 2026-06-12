"""
尾料复用池 — 追踪切割余料和来源板编号。

一次切割操作 = 一个 CuttingGroup（独立 ID）。
复用从池中取料，创建新的 CuttingGroup，通过 parent_source_id 追溯原板。

池条目: 切割后剩余的材料（长度池=全宽余料, 宽度池=宽切废料）
"""


class PoolEntry:
    __slots__ = ('length', 'source_id', 'width', 'edges')
    def __init__(self, length: float, source_id: str, width: float | None = None,
                 edges=None):
        self.length = length        # 可用长度 mm
        self.source_id = source_id  # 产生此余料的操作 ID
        self.width = width          # None=全宽, float=可用宽度 mm
        self.edges = edges          # BoardEdges | None 四边属性


class BoardPool:
    def __init__(self, board_length: float, kerf: float = 1.0, board_width: float = 148.0):
        self._L = board_length
        self._W = board_width
        self._K = kerf
        self._pool: list[PoolEntry] = []
        self._new = 0         # 新板消耗计数
        self._reused = 0      # 池复用次数
        self._counter = 0     # 全局操作 ID 计数器
        self._groups: dict[str, dict] = {}  # operation_id → group dict

    @property
    def total_new_boards(self) -> int:
        return self._new

    @property
    def total_reused(self) -> int:
        return self._reused

    @property
    def cutting_groups(self) -> list:
        return list(self._groups.values())

    def get_waste_summary(self) -> list[dict]:
        """收集所有废料：池中未使用的条目 + 切割组中的宽度废料。

        返回 list of dict: {source_id, length, width, edges, waste_type}
        waste_type: 'length_pool' | 'width_pool' | 'width_discard'
        """
        waste = []

        # 池中未消耗的条目
        for e in self._pool:
            w = e.width if e.width is not None else self._W
            waste.append(dict(
                source_id=e.source_id,
                length=e.length, width=w,
                edges=e.edges,
                waste_type='length_pool' if e.width is None else 'width_pool',
            ))

        # 切割组中的宽度废料（已丢弃，不在池中）
        for sid, g in self._groups.items():
            ww = g.get('width_waste', 0)
            if ww > 10:
                # 检查是否已在池中（避免重复）
                already_in_pool = any(
                    e.source_id == sid and e.width is not None
                    for e in self._pool
                )
                if not already_in_pool:
                    tl = g['total_length']
                    waste_w = ww / tl if tl > 0 else 0
                    waste.append(dict(
                        source_id=sid,
                        length=tl, width=waste_w,
                        edges=None,
                        waste_type='width_discard',
                    ))

        return waste

    def _next_id(self) -> str:
        self._counter += 1
        return f"源{self._counter}"

    def _next_reuse_id(self, parent_id: str, prefix: str) -> str:
        """为复用操作生成唯一 ID，如 源147-L1, 源147-W2

        使用根源板 ID（取第一个 '-' 前的部分）避免链式增长。
        """
        self._counter += 1
        root = parent_id.split('-')[0]  # "源6-L10-L19" → "源6"
        return f"{root}-{prefix}{self._counter}"

    # ── 新板操作 ──────────────────────────────────────────

    def register_full(self, label: str, width_waste: float = 0.0) -> str:
        """注册整板（无长度切割）。不计入 _new（由引擎 full_count 统计）。

        width_waste > 0 时表示宽切：使用宽 < 板宽，废料入宽切池。
        """
        sid = self._next_id()
        piece = dict(label=label, length=self._L)
        ww = 0.0
        if width_waste > 10:
            used_w = self._W - width_waste / self._L
            piece['width'] = used_w
            waste_w = self._W - used_w - self._K
            if waste_w > 0.5:
                # 宽切废料：bottom=CUT（切割面），top=GROOVE（保留原始边）
                from ..models import EdgeType, BoardEdges
                w_edges = BoardEdges(
                    top=EdgeType.GROOVE, bottom=EdgeType.CUT,
                    left=EdgeType.GROOVE, right=EdgeType.TONGUE,
                )
                self._pool.append(PoolEntry(self._L, sid, width=waste_w,
                                             edges=w_edges))
            ww = width_waste
        from ..models import EdgeType, BoardEdges
        g_edges = BoardEdges(
            top=EdgeType.CUT if ww > 10 else EdgeType.GROOVE,
            bottom=EdgeType.TONGUE,
            left=EdgeType.GROOVE, right=EdgeType.TONGUE,
        )
        self._groups[sid] = dict(
            source_id=sid, parent_source_id="",
            pieces=[piece],
            total_length=self._L, used_length=self._L,
            waste_length=0.0, width_waste=ww,
            total_width=self._W,
            edges=g_edges,
        )
        return sid

    def cut_new(self, used_len: float, label: str) -> str:
        """新板，仅长切。余料入长度池。"""
        self._new += 1
        sid = self._next_id()
        from ..models import EdgeType, BoardEdges
        self._groups[sid] = dict(
            source_id=sid, parent_source_id="",
            pieces=[dict(label=label, length=used_len)],
            total_length=self._L, used_length=used_len,
            waste_length=self._L - used_len,
            width_waste=0.0, total_width=self._W,
            edges=BoardEdges(top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
                             left=EdgeType.GROOVE, right=EdgeType.CUT),
        )
        leftover = self._L - used_len - self._K
        if leftover > 0.5:
            # 长切废料：left=CUT（切割面），其他边不变
            from ..models import EdgeType, BoardEdges
            waste_edges = BoardEdges(
                top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
                left=EdgeType.CUT, right=EdgeType.TONGUE,
            )
            self._pool.append(PoolEntry(leftover, sid, edges=waste_edges))
        return sid

    def cut_new_width(self, actual_w: float, label: str) -> str:
        """新板，仅宽切。废料按宽度方向记录。"""
        self._new += 1
        sid = self._next_id()
        piece = dict(label=label, length=self._L, width=actual_w)

        waste_w = max(0, self._W - actual_w - self._K)
        ww = self._L * waste_w if waste_w > 0.5 else 0.0

        from ..models import EdgeType, BoardEdges
        self._groups[sid] = dict(
            source_id=sid, parent_source_id="",
            pieces=[piece],
            total_length=self._L, used_length=self._L,
            waste_length=0.0, width_waste=ww,
            total_width=self._W,
            edges=BoardEdges(top=EdgeType.CUT, bottom=EdgeType.TONGUE,
                             left=EdgeType.GROOVE, right=EdgeType.TONGUE),
        )

        if waste_w > 0.5:
            w_edges = BoardEdges(top=EdgeType.GROOVE, bottom=EdgeType.CUT,
                                 left=EdgeType.GROOVE, right=EdgeType.TONGUE)
            self._pool.append(PoolEntry(self._L, sid, width=waste_w,
                                         edges=w_edges))
        return sid

    def cut_new_combined(self, used_len: float, actual_w: float, label: str) -> str:
        """新板，同时长切+宽切（组合切割）。

        产出两个不重叠的废料区：
        - 长度余料（全宽）→ 普通池
        - 宽度余料（used_len × waste_w）→ 宽切池
        """
        self._new += 1
        sid = self._next_id()
        piece = dict(label=label, length=used_len, width=actual_w)

        len_waste = max(0, self._L - used_len - self._K)
        waste_w = max(0, self._W - actual_w - self._K)
        ww = used_len * waste_w if waste_w > 0.5 else 0.0

        from ..models import EdgeType, BoardEdges
        g_edges = BoardEdges(
            top=EdgeType.CUT, bottom=EdgeType.TONGUE,
            left=EdgeType.GROOVE, right=EdgeType.CUT,
        )
        self._groups[sid] = dict(
            source_id=sid, parent_source_id="",
            pieces=[piece],
            total_length=self._L, used_length=used_len,
            waste_length=len_waste, width_waste=ww,
            total_width=self._W,
            edges=g_edges,
        )

        if len_waste > 0.5:
            from ..models import EdgeType, BoardEdges
            l_edges = BoardEdges(top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
                                 left=EdgeType.CUT, right=EdgeType.TONGUE)
            self._pool.append(PoolEntry(len_waste, sid, edges=l_edges))
        if waste_w > 0.5:
            from ..models import EdgeType, BoardEdges
            w_edges = BoardEdges(top=EdgeType.GROOVE, bottom=EdgeType.CUT,
                                 left=EdgeType.GROOVE, right=EdgeType.TONGUE)
            self._pool.append(PoolEntry(used_len, sid, width=waste_w,
                                         edges=w_edges))

        return sid

    # ── 池复用操作（每次创建新 group）──────────────────────

    def take(self, needed: float, label: str,
             required_edges=None, rotation: float = 0) -> str | None:
        """从长度池取余料。创建新的 CuttingGroup，返回新操作 ID 或 None。

        required_edges: BoardEdges | None — 若提供，只匹配四边兼容的条目。
        rotation: 板旋转角度，匹配时用于旋转固有边到物理方向。
        """
        if needed < 0.5:
            return None
        tolerance = max(self._K * 1.5, 1.0)
        best_i, best_len = -1, float('inf')
        for i, e in enumerate(self._pool):
            if e.width is not None:
                continue
            if required_edges is not None and e.edges is not None:
                if not _pool_edges_match(e.edges, required_edges, rotation):
                    continue
            if needed - tolerance <= e.length < best_len:
                best_i, best_len = i, e.length
        if best_i < 0:
            return None
        self._reused += 1
        e = self._pool.pop(best_i)
        actual = min(needed, e.length)
        parent_id = e.source_id  # 追溯用的父 ID

        reuse_sid = self._next_reuse_id(parent_id, 'L')
        self._groups[reuse_sid] = dict(
            source_id=reuse_sid, parent_source_id=parent_id,
            pieces=[dict(label=label, length=actual)],
            total_length=e.length, used_length=actual,
            waste_length=e.length - actual,
            width_waste=0.0, total_width=self._W,
        )

        remain = e.length - actual - self._K
        if remain > 0.5:
            # 剩余部分继承原条目的四边（同一个物理区）
            self._pool.append(PoolEntry(remain, reuse_sid, edges=e.edges))
        return reuse_sid

    def try_take_width_reduced(self, needed_w: float, label: str,
                                required_edges=None, rotation: float = 0) -> str | None:
        """从宽切池取废料。创建新的 CuttingGroup，返回新操作 ID 或 None。

        宪法第三条：宽切废料保留一条原始边，可作边界板复用。
        不可再次宽切。多余宽度不回池（双切面=废料）。

        required_edges: BoardEdges | None — 若提供，只匹配四边兼容的条目。
        """
        if needed_w < 0.5:
            return None
        best_i, best_w = -1, float('inf')
        for i, e in enumerate(self._pool):
            if e.width is None:
                continue
            if required_edges is not None and e.edges is not None:
                if not _pool_edges_match(e.edges, required_edges, rotation):
                    continue
            if needed_w - self._K <= e.width < best_w:
                best_i, best_w = i, e.width
        if best_i < 0:
            return None
        self._reused += 1
        e = self._pool.pop(best_i)
        parent_id = e.source_id
        piece_w = min(needed_w, e.width)

        reuse_sid = self._next_reuse_id(parent_id, 'W')
        self._groups[reuse_sid] = dict(
            source_id=reuse_sid, parent_source_id=parent_id,
            pieces=[dict(label=label, length=e.length, width=piece_w)],
            total_length=e.length, used_length=e.length,
            waste_length=0.0,
            width_waste=e.length * max(0, e.width - piece_w - self._K),
            total_width=e.width,
        )
        # 多余宽度不回池（第三条）
        return reuse_sid

    def take_or_cut(self, needed: float, label: str,
                     required_edges=None, rotation: float = 0) -> str:
        """取余料或切新板，返回操作 ID"""
        sid = self.take(needed, label, required_edges=required_edges,
                        rotation=rotation)
        return sid if sid else self.cut_new(needed, label)


# ── 边匹配工具 ──────────────────────────────────────────

def _pool_edges_match(pool_edges, required, rotation=0) -> bool:
    """检查池条目的四边是否满足铺装位需求。

    考虑板的旋转：池条目存储固有边，匹配时先旋转到物理方向。
    """
    if pool_edges is None or required is None:
        return True  # 无边信息 → 通过（向后兼容）

    from ..models import rotate_edges
    physical = rotate_edges(pool_edges, rotation)

    for side in ['top', 'bottom', 'left', 'right']:
        pe = getattr(physical, side, None)
        re = getattr(required, side, None)
        if pe is None or re is None:
            continue
        if re.value == 'cut':
            continue  # 位置靠墙，切割面或原始边都可以
        if pe.value == 'cut':
            return False  # 位置需榫槽(T/G)，但片物理边是切割面
        if pe.value != re.value:
            return False  # T vs G 不匹配
    return True


def derive_pool_entry_edges(has_width_cut: bool, has_length_cut: bool,
                            is_from_width_pool: bool = False):
    """推导池条目的四边属性。"""
    from ..models import EdgeType, BoardEdges
    e = BoardEdges(
        top=EdgeType.GROOVE, bottom=EdgeType.TONGUE,
        left=EdgeType.GROOVE, right=EdgeType.TONGUE,
    )
    if is_from_width_pool:
        # 宽切废料：bottom=CUT（从原始板切出），top=GROOVE（保留）
        e = BoardEdges(top=EdgeType.GROOVE, bottom=EdgeType.CUT,
                       left=e.left, right=e.right)
    elif has_width_cut:
        # 宽切后废料：top=CUT
        e = BoardEdges(top=EdgeType.CUT, bottom=e.bottom,
                       left=e.left, right=e.right)
    if has_length_cut:
        # 长切：right=CUT
        e = BoardEdges(top=e.top, bottom=e.bottom,
                       left=e.left, right=EdgeType.CUT)
    return e
