# Flooring Optimizer

木地板铺装优化工具。当前仓库以三L拼、多房间、L形房间和柜子/衣柜不可铺装区域为主要场景。

## 环境准备

需要 Python 3.11 或更高版本。

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

如果要运行测试，再安装 pytest：

```bash
pip install pytest
```

## 运行当前示例

当前正式示例配置在：

```text
projects/home-wood-l-triple/config.yaml
```

从仓库根目录运行：

```bash
python -m floorplan projects/home-wood-l-triple/config.yaml -o projects/home-wood-l-triple/output
```

运行后会生成：

```text
projects/home-wood-l-triple/output/floor_plan.html
projects/home-wood-l-triple/output/cutting_plan.txt
```

其中：

- `floor_plan.html` 是交互式铺装示意图（多房间模式）。铺装片直接标识 A/B 类型；点击任意切割板可高亮同源板片，并查看源板切割坐标、铺装旋转、四边榫槽属性及严格切割校验结论。
- `cutting_plan.txt` 是切割清单。
- `loss_audit.txt` 是当前方案的损耗与公母榫审计记录（单房间模式）。

> 每个房间可通过 `full_board_start_corner` 配置整板起始角
> （`bottom-left` / `top-left` / `top-right` / `bottom-right`），
> 示例见 `projects/home-wood-l-triple/config-full-board-corner.yaml`。

## 查看命令帮助

```bash
python -m floorplan --help
```

也可以在安装为包后使用脚本入口：

```bash
pip install -e .
floorplan projects/home-wood-l-triple/config.yaml -o projects/home-wood-l-triple/output
```

## 运行测试

```bash
python -m pytest tests/ -q
```

## 配置说明

可参考：

- `config.example.yaml`：当前多房间三L拼配置示例。
- `docs/flooring_constraints.md`：地板规格、伸缩缝、板缝、柜子障碍物、切割和公母榫约束。
- `docs/cutting_plan_format.md`：切割清单格式说明。
