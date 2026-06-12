# 进度日志 (Progress)

## 2026-06-01 — 需求收集与初始规划

### 完成事项
- 创建 CLAUDE.md 行为指南
- 收集完整项目需求：木地板铺装图生成工具
- 澄清输出格式（SVG）、房间类型（L 形）、配置方式（YAML 自定义）
- 创建规划文件：task_plan.md、findings.md、progress.md
- 完成初步技术栈选型（推荐 Python + Shapely + Click + YAML）
- 梳理 4 种铺装方式的算法方向

### 需求摘要
| 维度 | 决策 |
|------|------|
| 工具形式 | CLI 命令行工具 |
| 输入方式 | YAML 配置文件 |
| 输出格式 | SVG 矢量铺装图 |
| 房间类型 | L 形（两个正交矩形） |
| 地板规格 | 完全自定义（长、宽） |
| 铺装方式 | 对拼、错缝、人字拼、5拼方砖 |
| 额外参数 | 铺装方向、踢脚线宽度 |

### 本次澄清结果（2026-06-01）
| 问题 | 答案 |
|------|------|
| 人字拼角度 | 经典 45° |
| 5拼方砖排列 | 5块平行并排成正方形单元，相邻单元横竖交替（棋盘式） |
| 错缝比例 | 完全可配置 |
| 伸缩缝 | 可配置，地暖房默认 10mm |
| 板间缝 | 可配置，默认 0 |
| 榫槽方向 | 有约束，切割板不能翻转 180° 复用 |

### 下一步
- ~~设计 YAML 配置文件 schema~~
- ~~开始阶段 2 核心算法设计~~
- 验证安装依赖后可运行
- 编写测试用例
- 调试排样算法（特别是人字拼的密铺网格参数）

---

## 2026-06-01 — 阶段 2：架构设计与核心实现

### 完成事项
- 设计并创建 YAML 配置文件 schema → [config.example.yaml](config.example.yaml)
- 设计 Python 模块架构（8 个模块，职责分离）
- 创建项目骨架 pyproject.toml / requirements.txt
- 实现配置加载与校验 → [config.py](floorplan/config.py)
- 实现房间几何模型 (Shapely) → [geometry/room.py](floorplan/geometry/room.py)
  - L 形 = 包围矩形 - 角落缺口
  - compute_layout_area = 内缩踢脚线 + 伸缩缝
- 实现 4 种排样引擎:
  - [aligned.py](floorplan/layout/aligned.py) — 对拼（按行填充 + 端头切割）
  - [staggered.py](floorplan/layout/staggered.py) — 错缝（行间偏移）
  - [herringbone.py](floorplan/layout/herringbone.py) — 45° 人字拼（密铺网格）
  - [five_board.py](floorplan/layout/five_board.py) — 5拼方砖（棋盘式）
- 实现优化器 → [optimize.py](floorplan/optimize.py)
- 实现 SVG 渲染器 → [svg/renderer.py](floorplan/svg/renderer.py)
- 实现 CLI 入口 → [cli.py](floorplan/cli.py)
- 更新 [CLAUDE.md](CLAUDE.md) 加入项目架构文档
- 更新 [config.example.yaml](config.example.yaml) 含注释配置示例

### 关键设计决策
1. **排样 = 网格密铺 + 房间裁剪** — 所有 4 种引擎统一用此模式
2. **优化 = 枚举起始偏移** — 枚举 x/y 偏移网格，选利用率最高
3. **榫槽约束简化** — 当前版本切割尾料直接计为损耗，未来可加入尾料复用逻辑
4. **L 形房间 = 包围矩形 - 角落缺口** — 比两矩形坐标更直观

### 已知待办
- [ ] 人字拼算法需要研究正确的密铺几何（当前为实验性实现）
- [ ] 优化器可加入模拟退火或遗传算法提高搜索效率
- [ ] 尾料复用逻辑（榫槽方向约束）

---

## 2026-06-01 — 调试与测试

### 完成事项
- 修复面积阈值 bug：0.5 → 0.1，避免小切割板被过滤
- 修复统计计算：统一使用原始板面积计算利用率
- 修复错缝 lead-in 板缺失导致覆盖率仅 79% 的问题
- 修复 _get_segments bounds 索引错误 (axis×2 → axis)
- 修复人字拼引擎（改为旋转框架法，实验性可用）
- 编写 42 个测试用例，全部通过：
  - 14 个配置加载与校验测试
  - 9 个房间几何模型测试
  - 19 个排样引擎测试（含矩形/L形房间、覆盖率验证）
- 验证各模式利用率：
  - **对拼: 95.2%**（最优）
  - 错缝: 85.0%
  - 5拼方砖: 82.4%
  - 人字拼: 实验性

### 修复的关键 Bug
1. `clipped.area > 0.5 * full_board_area` → `> 0.1 * board_poly.area`
2. 错缝引擎缺少行首 lead-in 切割板
3. `_get_segments` 中 `b[axis*2]` → `b[axis]`
4. 优化器接受利用率 >100% 的无效结果 → 添加上限过滤

### 当前项目文件
```
estimated/
├── CLAUDE.md
├── config.example.yaml
├── pyproject.toml
├── requirements.txt
├── task_plan.md / findings.md / progress.md
├── floorplan/          # 所有模块
├── tests/              # 42 个测试
├── output/             # 生成的 SVG
└── venv/               # Python 虚拟环境
```

---

## 会话记录索引

---

## 2026-06-07 — 阶段 4：多房间优化

### 完成事项
- 创建共享尾料池基础设施 → [board_pool.py](floorplan/layout/board_pool.py)
- 更新对拼/错缝引擎支持外部池参数 (`pool=`)
- 创建多房间优化器 → [multi_optimize.py](floorplan/multi_optimize.py)
  - Phase 1: 每房间独立找最优配置 (pattern + direction + ratio + offset)
  - Phase 2: 独立方案作为基线
  - Phase 3: 枚举房间顺序 + 共享 BoardPool → 比较取最优
- 更新 CLI 支持多房间模式 → `rooms` 配置项
- 创建实测项目目录 `projects/room-2856x3462-staggered/`
- 实现全局唯一 ID（跨房间不重复的源板编号）
- 多房间 SVG 铺装图生成（每房间独立 SVG）
- 多房间切割方案统一文档（cutting_plan.txt）

### 实测结果

**3 房间案例** (2856×3462, 2560×3264, 3254×3460):

| 阶段 | 用板 | 说明 |
|------|------|------|
| 独立优化 | 218 | 每房间独立 |
| 共享池(初版) | 280 | 优化目标错误 |
| 共享池(修正) | 无改善 | 尾料尺寸不匹配 |
| 最终 | 216 | 独立优化 + 微调 |

### 关键 Bug 修复
1. BoardPool `_groups` 跨房间累积导致统计混乱 → 追踪每房间组 ID
2. 优化目标错误（最少新板 vs 利用率）→ 修正为利用率优先
3. 全局 ID：池 `_groups` 重置后编号冲突 → 使用 `itertools.count` 全局递增

### 关键发现
- **共享池不总是有益的**：尾料尺寸需匹配目标房间间隙，否则无效
- **最佳共享池场景**：同一户型多个相同尺寸房间
- **当前策略**：独立优化作为基线，仅当共享池更优时采用

### 当前项目文件
```
estimated/
├── floorplan/
│   ├── layout/board_pool.py     ← 共享尾料池
│   ├── multi_optimize.py        ← 多房间优化器
│   └── ... (其他模块)
├── projects/
│   ├── room-2856x3462/          ← 对拼测试案例
│   ├── room-2856x3462-herringbone/  ← 人字拼测试
│   └── room-2856x3462-staggered/    ← 错缝多房间案例
│       ├── config.yaml
│       ├── config-multi.yaml
│       └── multi/
│           ├── cutting_plan.txt
│           ├── floor_plan_A.svg
│           ├── floor_plan_B.svg
│           └── floor_plan_C.svg
└── tests/                       ← 42 个测试 (全部通过)
```

### 下一步
- 人字拼、5拼方砖引擎支持共享池
- 集成测试（真实尺寸多房间案例）
- README 使用文档

---

## 2026-06-07 (下午) — 四项修复与改进

### 用户反馈的四个问题
1. **铺装方向不符合 config**：多房间优化器硬编码枚举所有方向，忽略用户配置
2. **锯缝计数错误**：多片切割时锯缝永远计为 1 次
3. **SVG 分离**：三房间输出三个独立 SVG 文件
4. **利用率定义不对**：需要总利用率（房间总面积/总用板面积），而非每房间独立

### 修复内容

#### 问题1：铺装方向 ([cli.py](floorplan/cli.py) + [multi_optimize.py](floorplan/multi_optimize.py))
- `optimize_multi()` 新增 `installation` 参数，使用用户指定的 pattern/direction/stagger_ratio
- CLI `_run_multi_room()` 传入 `config.installation`
- 修复前：优化器枚举 [0, 90] 两个方向，选了 0°（不符合 config）
- 修复后：使用 config 指定的 staggered 90° 0.5

#### 问题2：锯缝计数 ([cli.py](floorplan/cli.py) `_format_cutting_groups`)
- 修复前：`length_cut_count = 1 if used_l < total_l - 0.5 else 0`（永远是1）
- 修复后：`length_cut_count = n_pieces if has_waste_piece else max(0, n_pieces - 1)`
  - 有废料片 → N 个使用片 + 1 废料片 = N+1 段 → N 次锯
  - 无废料片 → N 个使用片 = N 段 → N-1 次锯
- 废料检测阈值：`remaining > kerf + 0.5`

#### 问题3：合并 SVG ([svg/renderer.py](floorplan/svg/renderer.py) 新增 `render_multi`)
- 新增 `render_multi()` 函数，三房间水平排列在同一 SVG 画布
- 每房间独立缩放 + Y轴翻转 + 坐标平移
- 房间标签（房间 A / B / C）和尺寸标注
- 共享 CSS 样式和图例

#### 问题4：利用率重新定义 ([cli.py](floorplan/cli.py))
- 利用率 = 房间总面积 / (总用板数 × 单板面积)
- 损耗率 = 1 - 利用率
- 移除每房间独立利用率显示（cutting_plan.txt 和 CLI 输出）
- 单房间模式保持一致

### 测试结果
- 42 个测试全部通过
- 生成的多房间铺装图：`projects/room-2856x3462-staggered/multi/floor_plan.svg`
- 配置：staggered 90° 0.5，三房间合计 227 板，利用率 95.3%，损耗率 4.7%

### 涉及文件
- [cli.py](floorplan/cli.py) — 锯缝计数、利用率显示、传入 installation、合并 SVG 调用
- [multi_optimize.py](floorplan/multi_optimize.py) — 接受 installation 参数约束搜索
- [svg/renderer.py](floorplan/svg/renderer.py) — 新增 `render_multi()` 多房间渲染

---

## 2026-06-07 (下午续) — 全局编号 + SVG 尺寸标注修复

### 修复内容

#### 问题1：全局统一源板和位置编号
- 两个引擎 ([aligned.py](floorplan/layout/aligned.py), [staggered.py](floorplan/layout/staggered.py)) 新增 `label_start` 参数
- [multi_optimize.py](floorplan/multi_optimize.py) 在 Phase 3 和回退路径中：
  - 创建单个共享 `BoardPool` → 源板 ID 全局连续
  - 追踪 `label_start` 跨房间递增 → 位置编号全局连续
- 修复 `n = len(placed)` bug（重置为每房间计数）→ `n = label_offset + len(placed)`
- 修复每房间 `total_boards` 统计（用 `room_new_boards` delta 替代累计值）

#### 问题2：SVG 房间尺寸标注
- 宽度标注移到房间底部 (`ty_room + scaled_h + 25`)
- 高度标注移到房间右侧 (`tx_room + scaled_w + 25`)，垂直居中旋转
- 三房间尺寸清晰可见：2856×3462 / 2560×3264 / 3254×3460mm

### 测试结果
- 42 个测试全部通过
- 单房间模式正常运行
- 多房间输出：222 板，利用率 97.4%，损耗率 2.6%
- 源板 ID 跨房间全局唯一 (A: 4-80, B: 84-148, C: 152-231)
- 位置编号跨房间连续递增 (A: 1-89, B: 91-170+, C: 172-250+)

### 涉及文件
- [aligned.py](floorplan/layout/aligned.py) — 新增 `label_start` 参数
- [staggered.py](floorplan/layout/staggered.py) — 新增 `label_start` 参数 + 修复 n 重置 bug
- [multi_optimize.py](floorplan/multi_optimize.py) — 共享池 + 全局 label_start 追踪
- [svg/renderer.py](floorplan/svg/renderer.py) — 修复尺寸标注位置

---

## 会话记录索引
