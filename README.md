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
projects/three-l-multi-room/config.yaml
```

从仓库根目录运行：

```bash
python -m floorplan projects/three-l-multi-room/config.yaml -o projects/three-l-multi-room/output
```

运行后会生成：

```text
projects/three-l-multi-room/output/floor_plan.svg
projects/three-l-multi-room/output/cutting_plan.txt
```

其中：

- `floor_plan.svg` 是铺装示意图。
- `cutting_plan.txt` 是切割清单。
- `loss_audit.txt` 是当前方案的损耗与公母榫审计记录。

## 查看命令帮助

```bash
python -m floorplan --help
```

也可以在安装为包后使用脚本入口：

```bash
pip install -e .
floorplan projects/three-l-multi-room/config.yaml -o projects/three-l-multi-room/output
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
