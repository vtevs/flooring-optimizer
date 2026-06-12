# 木地板铺装 — 数学模型

## 1. 地板几何定义

一块地板为矩形 $B = [0, L] \times [0, W]$，其中 $L \gg W$（通常 $L \approx 5\sim10 \times W$）。

### 1.1 四条边的属性

| 边 | 位置 | 属性 | 符号 |
|----|------|------|------|
| $e_b$ | $y = 0$ (底边) | 公榫 (tongue) | $\tau$ |
| $e_t$ | $y = W$ (顶边) | 母榫 (groove) | $\gamma$ |
| $e_l$ | $x = 0$ (左边) | 母榫 (groove) | $\gamma$ |
| $e_r$ | $x = L$ (右边) | 公榫 (tongue) | $\tau$ |

榫槽匹配：$\tau \leftrightarrow \gamma$ 可对接。$\tau \leftrightarrow \tau$ 和 $\gamma \leftrightarrow \gamma$ 不可对接。

### 1.2 旋转

板绕中心旋转角度 $\theta \in \{0^\circ, 45^\circ, 90^\circ, 135^\circ\}$：

$B_\theta = R_\theta \cdot B$，其中 $R_\theta$ 为旋转矩阵。

旋转后各边的属性随边一起旋转（属性附着于边）。

## 2. 房间定义

可铺区域 $\Omega \subset \mathbb{R}^2$ 为简单多边形（L形 = 两个轴向矩形的布尔并）。

$\Omega = \Omega_{room} \ominus (d_{baseboard} + d_{expansion})$

其中 $\ominus$ 为形态学腐蚀（内缩）。

## 3. 铺装排样问题

### 3.1 定义

**排样** 是板集合 $\mathcal{P} = \{p_1, p_2, \ldots, p_n\}$，每个 $p_i = (x_i, y_i, \theta_i, \ell_i, w_i)$ 表示一块板：

- $(x_i, y_i)$：中心坐标
- $\theta_i$：旋转角
- $\ell_i$：实际使用长度（$\ell_i \leq L$，切割板 $\ell_i < L$）
- $w_i = W$：宽度（不变）

### 3.2 约束

**(C1) 覆盖约束**：所有板的并集完全覆盖可铺区域。
$$\bigcup_{i=1}^{n} B(p_i) \supseteq \Omega$$

其中 $B(p_i)$ 是板 $p_i$ 占据的几何区域。

**(C2) 容器约束**：每块板的几何区域必须在可铺区域内（边界裁剪允许）。
$$B(p_i) \subseteq \Omega \quad \text{或} \quad B(p_i) \cap \Omega = B'(p_i) \subseteq \Omega$$

**(C3) 榫槽对接约束**：两块相邻板的接触边必须满足榫槽匹配。
对于相邻板 $p_i, p_j$，若它们的边 $e_i, e_j$ 接触（距离 < $\varepsilon$），则：
$$\text{attr}(e_i) = \tau \iff \text{attr}(e_j) = \gamma$$

**(C4) 切割边位置约束**：切割产生的平面（无榫槽属性）只能位于 $\partial\Omega$（房间边界）。
$$\forall p_i, \forall e \in \text{edges}(p_i): \text{attr}(e) = \text{cut} \implies e \subset \partial\Omega$$

**(C5) 源板长度约束**：来自同一源板 $S_k$ 的所有段 $p_i \in \text{pieces}(S_k)$，其使用长度之和不超过板长：
$$\sum_{p_i \in \text{pieces}(S_k)} \ell(p_i) \leq L$$

### 3.3 优化目标

在满足 C1–C5 的前提下，最小化源板总数 $N$：
$$\min |\{S_1, S_2, \ldots, S_N\}|$$

等价地，最大化面积利用率：
$$\max \frac{\text{Area}(\Omega)}{\sum_{k=1}^{N} L \cdot W}$$

## 4. 铺装模式的形式化

### 4.1 对拼 (Aligned)

行扫描：沿行方向 $d \in \{0^\circ, 90^\circ\}$，行宽 $W$，行内板长 $L$。

行 $r$：$y = r \cdot W$，板在 $x = k \cdot L$ 处放置。
$$\mathcal{P} = \{p_{r,k} = (kL + L/2, rW + W/2, d, L, W) \mid \text{裁剪到}~\Omega\}$$

切割：行内最后一块板若超出 $\Omega$ 边界，沿边界方向裁剪。切割余料满足 C4、C5 入池。

### 4.2 错缝 (Staggered)

在 4.1 基础上，奇偶行偏移：
- 偶数行 $r$：$x = k \cdot L$
- 奇数行 $r$：$x = \alpha L + k \cdot L$，其中 $\alpha \in (0, 1)$ 为错缝比例

行首偏移 $\alpha L$ 处需要切割板填补（可从池中获取）。

### 4.3 人字拼 (Herringbone 45°)

旋转框架：$\Omega' = R_{-45^\circ} \cdot \Omega$

在 $\Omega'$ 中：
- H 板（原 $+45^\circ$，现 $0^\circ$）：$[x, x+L] \times [y, y+W]$
- V 板（原 $-45^\circ$，现 $90^\circ$）：$[x, x+W] \times [y, y+L]$

H/V 板交织形成棋盘式密铺，转回原坐标系。

### 4.4 5拼方砖 (Five-Board Square)

方砖单元边长 $S = \max(L, 5W)$，每单元 5 块板并排。
单元交替横竖（棋盘式）：$(i+j) \bmod 2$ 决定单元方向。

## 5. 切割复用模型 (Cut Pool)

### 5.1 池状态

切割池 $\mathcal{C}$ 为多集合，每个元素为 $(s, \ell)$：
- $s$：来源板 ID
- $\ell$：剩余可用长度

### 5.2 操作

**切割新板**：$\text{CutNew}(\ell_{use}) \to (s_{new}, \ell_{remain})$
- 创建源板 $s_{new}$
- 使用 $\ell_{use}$，剩余 $\ell_{remain} = L - \ell_{use}$ 入池
- 记录：$\text{pieces}(s_{new}) \gets \{\ell_{use}\}$

**池中取用**：$\text{TakeFromPool}(\ell_{need}) \to s_{src}$
- 找 $\ell_{avail} \geq \ell_{need}$ 的最小池条目
- 记录：$\text{pieces}(s_{src}) \gets \text{pieces}(s_{src}) \cup \{\ell_{need}\}$
- 剩余 $\ell_{avail} - \ell_{need}$ 放回池（若 > 0）

**约束验证**：$\forall s: \sum_{\ell \in \text{pieces}(s)} \ell \leq L$

## 6. 优化算法

输入：$\Omega, L, W, \text{pattern}, \text{direction}$

输出：$\mathcal{P}, \mathcal{S}$（板布局 + 源板切割方案）

**算法框架**：
1. 枚举起始偏移 $(\delta_x, \delta_y)$，$\delta_x \in [0, L), \delta_y \in [0, W)$
2. 对每个偏移，执行排样引擎 $\text{Layout}(\Omega, L, W, \delta_x, \delta_y)$
3. 对每个结果，验证约束 C1–C5
4. 选 $N$ 最小者

**搜索精度**：$\Delta\delta = \min(L/8, W/2)$
