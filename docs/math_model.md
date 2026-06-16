# 数学模型入口

当前数学模型以三L拼、多房间 polygon/obstacles、伸缩缝、板缝、切割复用和榫槽逐边校验为准。

权威约束文档：

- `docs/flooring_constraints.md`：地板规格、坐标系、房间/障碍物、伸缩缝、拼缝、切割、损耗、榫槽定义与校验规则。
- `docs/superpowers/specs/2026-06-12-three-l-pattern-design.md`：三L拼 `l-triple` 的生成模型和实现设计。
- `docs/cutting_plan_format.md`：`cutting_plan.txt` 输出字段含义。

本文件不再维护旧版“矩形单房间 + 固定错缝”的详细公式，避免与当前实现产生冲突。需要修改铺装约束时，优先更新 `docs/flooring_constraints.md`。
