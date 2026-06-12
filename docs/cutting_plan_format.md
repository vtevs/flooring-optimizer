# 切割方案文本格式规范 (cutting_plan.txt)

## 格式模板

```
============================================================
木地板铺装 — 切割方案
============================================================
地板规格: {L}×{W}×{T}mm
铺装方式: {pattern}
总用板: {total}  完整板: {full}  切割板: {cut}
利用率: {util}%  损耗率: {waste}%

完整板 ({full_count} 块):
  放置编号: {label1}, {label2}, ...
  ... 共 {full_count} 块

切割板 ({cut_count} 块):
--------------------------------------------------
  [{source_id}] 位{pos}({used_l}×{used_w}mm)  使用{used_l}×{used_w}mm  废料{waste_l}×{waste_w}mm  锯缝 {cut_dir}{cut_count}次 {kerf}×{kerf_w}mm
  [{source_id}] 位{a}({l1}×{w1}mm), 位{b}({l2}×{w2}mm)  使用{total_used_l}×{used_w}mm  废料{waste_l}×{waste_w}mm  锯缝 {cut_dir}{cut_count}次 {kerf}×{kerf_w}mm
  ...

============================================================
```

## 字段说明

| 字段 | 说明 | 示例 |
|------|------|------|
| `{pattern}` | 铺装方式 | staggered / aligned / herringbone / five-board-square |
| `{total}` | 源板总数 | 77 |
| `{full}` | 完整板数 | 57 |
| `{cut}` | 切割板数 | 20 |
| `{util}` | 面积利用率 | 94.1 |
| `{source_id}` | 源板编号 | 源4, 源5, ... |
| `{pos}` | 铺装位编号 | 位4, 位5, ... |
| `{used_l}×{used_w}` | 该位实际使用长×宽 mm | 712×148 |
| `{waste_l}×{waste_w}` | 废料长×宽 mm | 197×148 |
| `{cut_dir}` | 切割方向 | 长切 / 宽切 |
| `{cut_count}` | 切割次数 | 1 |
| `{kerf}×{kerf_w}` | 锯缝尺寸 mm | 1×148 (长切) / 1×910 (宽切) |

## 废料长宽规则

- **仅长度切割**：废料宽度 = 板宽 (未切割方向保留完整)
  - 例：`废料197×148mm`
- **仅宽度裁剪**：废料长度 = 板长 (未切割方向保留完整)
  - 例：`废料910×113mm`
- **计算公式**：`waste = board - used - kerf`

## 锯缝规则

- **每次切割产生一个锯缝**，尺寸 = `kerf × 切割面宽度`
- 长切：切割面宽 = 板宽 `{kerf}×{W}mm`
- 宽切：切割面长 = 板长 `{kerf}×{L}mm`

## 完整板判定

- `len(pieces) == 1` 且 `waste_length < 0.5` 且 `width_waste < 10`
