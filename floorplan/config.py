"""
YAML 配置文件加载与校验

使用 PyYAML 解析配置文件，生成 Config 对象。
校验所有必填字段、取值范围、物理约束。
"""

from pathlib import Path

import yaml

from .models import (
    Config, RoomConfig, RoomSpec, BoardConfig, InstallationConfig,
    EdgeConfig, OutputConfig, NotchConfig, NotchPosition, Pattern,
)


# ---------------------------------------------------------------------------
# 校验常量
# ---------------------------------------------------------------------------
VALID_PATTERNS = {p.value for p in Pattern}
VALID_NOTCH_POSITIONS = {p.value for p in NotchPosition}
VALID_DIRECTIONS = {0, 45, 90}


def load_config(path: str | Path) -> Config:
    """加载并校验 YAML 配置文件。

    Args:
        path: 配置文件路径

    Returns:
        校验后的 Config 对象

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 配置值不合法
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    return _parse_and_validate(raw)


def _parse_and_validate(raw: dict) -> Config:
    """解析原始字典并逐字段校验"""
    if raw is None:
        raise ValueError("配置文件为空")

    # --- 房间 (支持单房间 room 或多房间 rooms) ---
    rooms_raw = raw.get("rooms")
    room = None
    room_specs = None

    if rooms_raw is not None:
        # 多房间模式
        if not isinstance(rooms_raw, list) or len(rooms_raw) < 1:
            raise ValueError("[rooms] 需为包含至少1个房间的列表")
        room_specs = []
        for i, r in enumerate(rooms_raw):
            name = r.get("name", f"房间{i+1}")
            w = _require_positive(r, "width", f"rooms[{i}]")
            h = _require_positive(r, "length", f"rooms[{i}]")
            room_specs.append(RoomSpec(name=name, width=w, length=h))
    else:
        # 单房间模式
        room_raw = raw.get("room")
        if room_raw is None:
            raise ValueError("缺少 [room] 或 [rooms] 配置节")
        room_type = room_raw.get("type", "rectangle")
        if room_type not in ("rectangle", "l-shaped"):
            raise ValueError(f"无效的房间类型: {room_type}")
        room = RoomConfig(
            type=room_type,
            width=_require_positive(room_raw, "width", "room"),
            length=_require_positive(room_raw, "length", "room"),
        )
        if room_type == "l-shaped":
            notch_raw = room_raw.get("notch")
            if notch_raw is None:
                raise ValueError("L 形房间需要配置 [room.notch]")
            pos = notch_raw.get("position", "top-left")
            if pos not in VALID_NOTCH_POSITIONS:
                raise ValueError(f"无效的缺口位置: {pos}，可选: {VALID_NOTCH_POSITIONS}")
            room.notch = NotchConfig(
                width=_require_positive(notch_raw, "width", "room.notch"),
                depth=_require_positive(notch_raw, "depth", "room.notch"),
                position=NotchPosition(pos),
            )
            if room.notch.width > room.width or room.notch.depth > room.length:
                raise ValueError("缺口尺寸不能超过房间总尺寸")

    # --- 地板 ---
    board_raw = raw.get("board")
    if board_raw is None:
        raise ValueError("缺少 [board] 配置节")
    board = BoardConfig(
        length=_require_positive(board_raw, "length", "board"),
        width=_require_positive(board_raw, "width", "board"),
        thickness=board_raw.get("thickness", 12.0),
    )
    if board.width > board.length:
        raise ValueError("板宽不能大于板长")

    # --- 铺装 ---
    inst_raw = raw.get("installation", {})
    pattern_str = inst_raw.get("pattern", "aligned")
    if pattern_str not in VALID_PATTERNS:
        raise ValueError(f"无效的铺装方式: {pattern_str}，可选: {VALID_PATTERNS}")
    direction = inst_raw.get("direction", 0)
    if direction not in VALID_DIRECTIONS:
        raise ValueError(f"无效的铺装方向: {direction}°，可选: {VALID_DIRECTIONS}")
    stagger_ratio = inst_raw.get("stagger_ratio", 0.33)
    if not (0.0 <= stagger_ratio <= 1.0):
        raise ValueError(f"错缝比例需在 0~1 之间: {stagger_ratio}")

    installation = InstallationConfig(
        pattern=Pattern(pattern_str),
        direction=float(direction),
        stagger_ratio=float(stagger_ratio),
    )

    # --- 收边 ---
    edge_raw = raw.get("edges", {})
    edges = EdgeConfig(
        baseboard_width=float(edge_raw.get("baseboard_width", 15.0)),
        expansion_gap=float(edge_raw.get("expansion_gap", 10.0)),
        board_gap=float(edge_raw.get("board_gap", 0.0)),
    )
    for name, val in [("踢脚线宽度", edges.baseboard_width),
                       ("伸缩缝", edges.expansion_gap),
                       ("板间缝", edges.board_gap)]:
        if val < 0:
            raise ValueError(f"{name}不能为负: {val}")

    # --- 输出 ---
    out_raw = raw.get("output", {})
    output = OutputConfig(
        file=out_raw.get("file", "floor_plan.svg"),
        scale=out_raw.get("scale", "auto"),
        show_dimensions=out_raw.get("show_dimensions", True),
        show_labels=out_raw.get("show_labels", True),
        show_grid=out_raw.get("show_grid", False),
        color_scheme=out_raw.get("color_scheme", "wood"),
    )

    kerf = float(raw.get("kerf", 1.0))
    if kerf < 0:
        raise ValueError(f"切割损耗不能为负: {kerf}")

    return Config(
        room=room,
        rooms=room_specs,
        board=board,
        installation=installation,
        edges=edges,
        output=output,
        kerf=kerf,
    )


def _require_positive(d: dict, key: str, section: str) -> float:
    """获取正数值字段，缺失或非正数抛出 ValueError"""
    val = d.get(key)
    if val is None:
        raise ValueError(f"[{section}] 缺少必填字段: {key}")
    val = float(val)
    if val <= 0:
        raise ValueError(f"[{section}].{key} 必须为正数，当前值: {val}")
    return val
