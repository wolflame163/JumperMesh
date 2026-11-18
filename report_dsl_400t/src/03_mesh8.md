# 第 3 章 400T 64R 8×8 2D-Mesh 方案 {#ch3}

本章结构与第 2 章相同，按 **构型分析 workflow**（七步）评估四种方案。与 4×4 的差别主要是 die 更小（\(B_{die}=6.4\mathrm T\)）、路径更长、二分下界减半。

## 3.1 封装介绍

64 颗 32 × 25 mm die 排成 8 × 8 方阵，阵列 {{8|manhattan|arr_w|.0f}} × {{8|manhattan|arr_h|.0f}} mm（对角 {{8|manhattan|arr_diag|.0f}} mm），硅面积 {{8|manhattan|si_area|,.0f}} mm²。阵列对角线已超过 300 mm 晶圆可用直径，**无法放进单片 300 mm 晶圆**，需要 Panel 级承载。仅相邻 die SIO 互联。CLOS 方案为共址 CLOS(64,64,64)（“64R”）；方案四为同构 O1Turn(DR) NoC router。

!fig[fig_pkg_8x8.png](图 3-1 8×8 封装：64 颗 die 的 2D Mesh 阵列与相邻 die SIO 链路)

每条 die 间逻辑链路 \(b=409.6\mathrm T/64^2=0.1\) Tbps，die 间逻辑链路共 8,064 条，另有 128 条同 die 链路。二分下界 \(C_{LB}=256\) 条，即 **{{8|manhattan|lb_tbps|.1f}} Tbps / 共享边 / 方向**。平均 Manhattan 距离 {{8|manhattan|hops_mean|.2f}} 跳，最远 14 跳。

!fig[fig_routes_8x8.png](图 3-2 8×8：同一组 L1→L2 逻辑链路在两种路由下的物理路径)

## 3.2 方案一：DSL XY 路由

> **方案要点**：CLOS(64,64,64) 共址，每条逻辑链路按顺时针 O1Turn 单转弯选路，路由由坐标唯一确定、无需优化。代价是负载集中在外圈中段：最热边 **{{8|xy_o1turn_cw|C_tbps|.1f}}T**，为二分下界的 {{8|xy_o1turn_cw|C_ratio_lb|.2f}}×；换来较短的最坏馈通（端到端最大 {{8|xy_o1turn_cw|e2e_wire_max|.0f}} mm，方案二 {{8|manhattan|e2e_wire_max|.0f}} mm）和低于方案二的最大时延 {{8|xy_o1turn_cw|e2e_lat_max|,.0f}} ns。

### 3.2.1 逻辑交换方案

**逻辑交换拓扑。** 共址 CLOS(64,64,64)：L1 / L2 / L3 各 {{8|manhattan|wf/N|d}} 个 switch，共 {{8|manhattan|wf/N|d}}×3 个交换模块，每个交换容量 \(B_{die}={{8|manhattan|wf/B|g}}\mathrm T\)（{{8|manhattan|ports_per_die|d}}×400GE）。L1→L2、L2→L3 均为全互联，每级 \(N^2={{8|manhattan|wf/N|d}}^2\) 条逻辑链路、每条 \(b=B_{die}/N={{8|manhattan|wf/b|g}}\mathrm T\)，每级合计 \(N^2 b=409.6\mathrm T\)。其中同 die 链路 {{8|manhattan|n_local|d}} 条不占 die 边，die 间逻辑链路 {{8|manhattan|n_flows|,d}} 条。

!fig[fig_logic_clos_8x8.png](图 3.2-1 方案一 / 二逻辑交换拓扑：CLOS(64,64,64)，L1→L2、L2→L3 全互联，每条 b = {{8|manhattan|wf/b|g}}T)

**转发与负载均衡。**

- L1 把入口流量 **均匀喷洒** 到全部 \(N\) 个 L2（每个 L2 分得 \(b\)）；L2 按目的端口转发到对应 L3。两级喷洒使任意流量矩阵在 die 间都化为均匀流量，因此置换与 AllToAll 下的边负载相同。
- 每条逻辑链路不可拆分，物理上按 **顺时针 O1Turn** 走单转弯路径：\(s_x s_y<0\) 走 XY，\(s_x s_y>0\) 走 YX，同行 / 同列直达。路由无状态、无需全局优化。

### 3.2.2 物理构型方案与约束

- **die 类型与数量**：1 种同构 die × {{8|manhattan|wf/N|d}} 颗（32 × 25 mm），8×8 2D Mesh，缝隙 1 mm。
- **die 间互联**：仅上下左右相邻 die 经 SIO 互联，共 {{8|manhattan|wf/n_edges|d}} 条有向边；无跳线。
- **die 内逻辑模块**：每颗 die 共址 \(L1_i / L2_i / L3_i\) 与 Feedthrough。
- **约束**：同构 die（所有 die 的 SIO 按全阵列最坏方向带宽配置）；最短路径、不可绕路；逻辑链路不可拆分。

### 3.2.3 逻辑到物理的映射结果

摆放为恒等映射（\(L1_i/L2_i/L3_i\) → die \(i\)）。**映射粒度**：每条逻辑链路带宽 \(b={{8|manhattan|wf/b|g}}\mathrm T\)（不可拆分）；逐条映射到一条物理路径，路径上每一跳占用 1 个 \(b\) 粒度的有向边端口；边负载 \(C\) 以逻辑链路**条数**计，带宽 = \(C\cdot b\)。逐 die 片上走线见 `figs/die_map/`（SVG）。

{{8|manhattan|n_flows|,d}} 条 die 间逻辑链路逐条映射为顺时针 O1Turn 路径，平均 {{8|xy_o1turn_cw|hops_mean|.2f}} 跳、平均转弯 {{8|xy_o1turn_cw|turns_mean|.2f}} 次，无绕路。已用 D2D 带宽中 **{{8|xy_o1turn_cw|ft_bw_share|.0f%}} 为馈通**（为非本 die 的流量转发）。完整路径见 `mapping/s1_dsl_xy_8x8.log`。

!fig[fig_die_map_s1_dsl_xy_8x8.png](图 3.2-1b 方案一逻辑→物理映射可视化：左上连续 3×3 子阵列（邻格=真实邻 die），按 b={{8|manhattan|wf/b|g}}T 粒度片上走线（完整 64 颗 SVG：`figs/die_map/s1_dsl_xy_8x8/`）)

### 3.2.4 每颗 die 的逻辑模块构成

!fig[fig_die_xy_o1turn_cw_8x8.png](图 3.2-2 方案一 die 顶层模块架构：L1 / L2 / L3 + Feedthrough + 四向 SIO（同构 die 取全阵列各方向最大需求）)

| 模块 | 交换 / 转发需求 | 说明 |
|---|---:|---|
| L1 | {{8|xy_o1turn_cw|wf/L1|.1f}}T | 入 {{8|manhattan|wf/B|g}}T 线路侧；出 N·b = {{8|manhattan|wf/B|g}}T 到全部 L2（本 die {{8|manhattan|wf/b|g}}T，其余经 SIO） |
| L2 | {{8|xy_o1turn_cw|wf/L2|.1f}}T | 入自全部 L1，出到全部 L3 |
| L3 | {{8|xy_o1turn_cw|wf/L3|.1f}}T | 汇聚全部 L2，出 {{8|manhattan|wf/B|g}}T 线路侧 |
| 单 die 交换合计 | **{{8|xy_o1turn_cw|wf/die_sw|.1f}}T** | 3 × B_die |
| Feedthrough | 最大 {{8|xy_o1turn_cw|wf/ft_max|.1f}}T / 平均 {{8|xy_o1turn_cw|wf/ft_mean|.1f}}T | 单 die 过路流量（AllToAll 满载） |
| SIO 每方向 | **{{8|xy_o1turn_cw|wf/sio_ports_b|d}} × {{8|manhattan|wf/b|g}}T = {{8|xy_o1turn_cw|wf/sio_side_max|.1f}}T**（≈{{8|xy_o1turn_cw|wf/sio_lanes400|d}}×400G） | 映射粒度 \(b\)；出 / 入各需此带宽；单 die D2D 出向合计最大 {{8|xy_o1turn_cw|wf/die_d2d_out_max|.1f}}T |

### 3.2.5 最终物理构型方案

!fig[fig_phys_xy_o1turn_cw_8x8.png](图 3.2-3 方案一物理构型：有向边逻辑链路条数（每条 b={{8|manhattan|wf/b|g}}T；旁注 Tbps）)

- 最热边 **{{8|xy_o1turn_cw|C|d}} 条 × {{8|manhattan|wf/b|g}}T = {{8|xy_o1turn_cw|C_tbps|.1f}}T**，共 {{8|xy_o1turn_cw|wf/n_hot|d}} 条有向边位于外圈四边中段、方向一致构成顺时针热环；单边加速比 {{8|xy_o1turn_cw|sp_edge|.2f}}×（= \(n-1/2\)）。
- 平均边 {{8|xy_o1turn_cw|wf/edge_mean|.1f}}T、最轻边 {{8|xy_o1turn_cw|wf/edge_min|.1f}}T：边负载极不均衡（最热 / 最轻 = {{8|xy_o1turn_cw|wf/edge_max|.1f}} / {{8|xy_o1turn_cw|wf/edge_min|.1f}}），同构 die 却要按最热边配置 SIO。
- D2D 总量 {{8|xy_o1turn_cw|wf/total_d2d|,.0f}}T（全部有向边之和）。
- **SIO 配置（静态功耗口径）**：同构 die 每条有向边按最热边配置，全阵列 {{8|xy_o1turn_cw|power/0.1/n_dir_edges|d}} 条 × {{8|xy_o1turn_cw|C_tbps|.1f}}T = **{{8|xy_o1turn_cw|power/0.1/sio_cfg_tbps|,.0f}}T**（AllToAll 实际使用 {{8|xy_o1turn_cw|wf/total_d2d|,.0f}}T，平均利用率 {{8|xy_o1turn_cw|wf/edge_mean|.1f}} / {{8|xy_o1turn_cw|C_tbps|.1f}}），SIO 静态 = 配置带宽 × 0.35 × 0.7 = {{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} W。

### 3.2.6 整体方案量化指标

**跳数。** 单条逻辑链路平均 / 最大 {{8|xy_o1turn_cw|hops_mean|.2f}} / {{8|xy_o1turn_cw|hops_max|d}} 跳；L1→L2→L3 端到端平均 / 最大 {{8|xy_o1turn_cw|e2e_hops_mean|.2f}} / {{8|xy_o1turn_cw|e2e_hops_max|.0f}} 跳。最长路径为 **{{8|xy_o1turn_cw|worst_path|s}}**（两次跨越对角，{{8|xy_o1turn_cw|worst_hops|d}} 跳）。

**馈通走线距离。** \(\mathrm{wire}_{ft}=\sum_{\text{过路 die}} f_d\)：直通取 die 边长（32 或 25 mm），转弯 die 取均值 28.5 mm / 最坏 57 mm。单链路平均 / 最大 {{8|xy_o1turn_cw|wire_mean|.1f}} / {{8|xy_o1turn_cw|wire_max|.0f}} mm；端到端平均 / 最大 **{{8|xy_o1turn_cw|e2e_wire_mean|.0f}} / {{8|xy_o1turn_cw|e2e_wire_max|.0f}} mm**。

**功耗**（满载 AllToAll，走线 0.1 pJ/bit/mm）：

\[
P_{\mathrm{chip}}=\underbrace{3795}_{\text{SerDes}}+\underbrace{{{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}}}_{\text{SIO 静态}=n_{dir}C\cdot0.35\cdot0.7}+\underbrace{{{8|xy_o1turn_cw|power/0.1/sio_dyn_W|,.0f}}}_{\text{SIO 动态}=\sum h\lambda\cdot0.35\cdot0.3}+\underbrace{{{8|xy_o1turn_cw|power/0.1/wire_W|,.0f}}}_{\text{馈通}=\sum \lambda\cdot\mathrm{wire}_{ft}\cdot0.1}={{8|xy_o1turn_cw|power/0.1/total_W|,.0f}}\ \mathrm W
\]

| 分项 | 功耗（W） | 占比 |
|---|---:|---:|
| SerDes | {{8|xy_o1turn_cw|power/0.1/serdes_W|,.0f}} | {{8|xy_o1turn_cw|power/0.1/serdes_share|.1f%}} |
| SIO 静态（{{8|xy_o1turn_cw|power/0.1/n_dir_edges|d}} 条有向边 × {{8|xy_o1turn_cw|C_tbps|.1f}}T × 0.35 × 0.7） | {{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} | — |
| SIO 动态（\(\sum h\lambda\cdot0.35\cdot0.3\)） | {{8|xy_o1turn_cw|power/0.1/sio_dyn_W|,.0f}} | — |
| SIO 合计 | {{8|xy_o1turn_cw|power/0.1/sio_W|,.0f}} | {{8|xy_o1turn_cw|power/0.1/sio_share|.1f%}} |
| 馈通走线 | {{8|xy_o1turn_cw|power/0.1/wire_W|,.0f}} | {{8|xy_o1turn_cw|power/0.1/wire_share_total|.1f%}} |
| **最大功耗（满载）** | **{{8|xy_o1turn_cw|power/0.1/total_W|,.0f}}** | 100% |
| 静态功耗（SerDes + SIO 静态份额） | {{8|xy_o1turn_cw|power/0.1/static_W|,.0f}} | {{8|xy_o1turn_cw|power/0.1/static_share|.1f%}} |

走线 0.06 pJ/bit/mm 时满载 {{8|xy_o1turn_cw|power/0.06/total_W|,.0f}} W。数据搬移能耗 {{8|xy_o1turn_cw|power/0.1/move_pj|.1f}} pJ/bit。

**时延。** \(\Delta=11.5h+(\mathrm{wire}_{ft}+h\,g)\cdot0.5+2n_{turn}+t_{\mathrm{sw\_die}}+t_{\mathrm{sw\_sw}}\)，端到端 L1→L2、L2→L3 两段的跳数、馈通与转向相加，\(t_{\mathrm{sw\_die}}\)（120 ns）与 L2 的 \(t_{\mathrm{sw\_sw}}\)（70 ns）各计一次，固定项合计 190 ns。

| 指标 | 数值 |
|---|---:|
| 最小时延（同 die L1→L2→L3） | {{8|xy_o1turn_cw|e2e_lat_min|.0f}} ns |
| 平均时延 | {{8|xy_o1turn_cw|e2e_lat_mean|.0f}} ns |
| **最大时延** | **{{8|xy_o1turn_cw|e2e_lat_max|,.0f}} ns** |
| 最坏路径：SIO（{{8|xy_o1turn_cw|worst_hops|d}} 跳 × 11.5） | {{8|xy_o1turn_cw|e2e_worst/iface|.0f}} ns（{{8|xy_o1turn_cw|e2e_worst/iface_share|.0f%}}） |
| 最坏路径：馈通 + 缝隙 | {{8|xy_o1turn_cw|e2e_worst/ft|.0f}} ns（{{8|xy_o1turn_cw|e2e_worst/ft_share|.0f%}}） |
| 最坏路径：转向（{{8|xy_o1turn_cw|e2e_worst/turns|d}} 次 × 2） | {{8|xy_o1turn_cw|e2e_worst/turn|.0f}} ns（{{8|xy_o1turn_cw|e2e_worst/turn_share|.0f%}}） |
| 最坏路径：\(t_{\mathrm{sw\_die}}\)（一次） | {{8|xy_o1turn_cw|e2e_worst/sw_die|.0f}} ns（{{8|xy_o1turn_cw|e2e_worst/sw_die_share|.0f%}}） |
| 最坏路径：\(t_{\mathrm{sw\_sw}}\)（L2，一次） | {{8|xy_o1turn_cw|e2e_worst/sw_sw|.0f}} ns（{{8|xy_o1turn_cw|e2e_worst/sw_sw_share|.0f%}}） |

### 3.2.7 给定流量矩阵下的指标

CLOS 两级喷洒使 **最佳、最差、AllToAll 三种场景激活的路径完全相同**：全部 {{8|manhattan|n_flows|,d}} 条 die 间逻辑链路各以 \(b\cdot\rho\) 激活（满载 \(\rho=1\)），每条接口带宽即图 3.2-3 的边带宽。因此三种场景的指标一致：

| 场景 | 激活路径 | 最热边 | 平均馈通（端到端） | 最小 / 平均 / 最大时延（ns） | 数据搬移功耗 | 芯片总功耗 |
|---|---:|---:|---:|---:|---:|---:|
| 最佳 | 全部 {{8|manhattan|n_flows|,d}} 条 | {{8|xy_o1turn_cw|C_tbps|.1f}}T | {{8|xy_o1turn_cw|e2e_wire_mean|.0f}} mm | {{8|xy_o1turn_cw|e2e_lat_min|.0f}} / {{8|xy_o1turn_cw|e2e_lat_mean|.0f}} / {{8|xy_o1turn_cw|e2e_lat_max|,.0f}} | {{8|xy_o1turn_cw|power/0.1/scenarios/perm_best/W|,.0f}} W | {{8|xy_o1turn_cw|power/0.1/scenarios/perm_best/chip_W|,.0f}} W |
| 最差 | 同上 | 同上 | 同上 | 同上 | {{8|xy_o1turn_cw|power/0.1/scenarios/perm_worst/W|,.0f}} W | {{8|xy_o1turn_cw|power/0.1/scenarios/perm_worst/chip_W|,.0f}} W |
| AllToAll | 同上 | 同上 | 同上 | 同上 | {{8|xy_o1turn_cw|power/0.1/scenarios/a2a_100/W|,.0f}} W | {{8|xy_o1turn_cw|power/0.1/scenarios/a2a_100/chip_W|,.0f}} W |

图 3.2-4 给出该方案在给定流量矩阵下的 die2die 流量带宽，有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图）。CLOS 两级喷洒使每条逻辑链路在三种场景下都以 \(b\) 满载，因此最佳、最差、AllToAll 逐边相同，且每条边 xx = yy。

!fig[fig_flow_xy_o1turn_cw_a2a_100_8x8.png](图 3.2-4 方案一 die2die 流量带宽：最佳 / 最差 / AllToAll（三者逐边相同；有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

> **要点**：方案一的指标与流量矩阵无关，适合需要确定性性能的场景；短板在 D2D 带宽（{{8|xy_o1turn_cw|C_tbps|.1f}}T，比方案二高 {{8|xy_o1turn_cw|C_vs_s2|.0f%}}），以及由此带来的功耗：同构 die 每条有向边都按最热边配置 SIO，SIO 静态 {{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} W（方案二 {{8|manhattan|power/0.1/sio_static_W|,.0f}} W），满载芯片总功耗比方案二高 {{8|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}}。

## 3.3 方案二：DSL 最短路径路由

> **方案要点**：逻辑拓扑与方案一相同，选路放开为任意 Manhattan 最短路径并最小化最热边，最热边降到 **{{8|manhattan|C_tbps|.1f}}T，恰为二分下界**（比方案一低 {{8|manhattan|C_save_vs_xy|.0f%}}）。代价是为摊开负载使用多转弯阶梯路径，最坏馈通变长，端到端最大时延 {{8|manhattan|e2e_lat_max|,.0f}} ns（方案一的 {{8|manhattan|lat_vs_xy|.2f}}×）；平均跳数、平均时延与方案一几乎相同；最热边降低使全阵列 SIO 配置带宽同比例下降，SIO 静态只有 {{8|manhattan|power/0.1/sio_static_W|,.0f}} W（方案一 {{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} W），满载功耗比方案一低。

### 3.3.1 逻辑交换方案

**逻辑交换拓扑。** 与方案一相同（图 3.2-1）：CLOS(64,64,64)，3 × {{8|manhattan|wf/N|d}} 个 switch，各 {{8|manhattan|wf/B|g}}T；全互联逻辑链路每条 {{8|manhattan|wf/b|g}}T。

**转发与负载均衡。** L1 / L2 两级均匀喷洒不变；每条逻辑链路的物理路径在全部 Manhattan 最短路径中选取，以 “最热有向边负载最小” 为目标求解（瓶颈动态规划贪心布线 + 最热边拆线重布，再在不抬高 \(C\) 的前提下改为转弯最少的路径，见 1.6 节）。结果中平均转弯 {{8|manhattan|turns_mean|.2f}} 次（方案一 {{8|xy_o1turn_cw|turns_mean|.2f}}），无绕路。

### 3.3.2 物理构型方案与约束

与方案一相同：{{8|manhattan|wf/N|d}} 颗同构 die、8×8 Mesh、仅相邻 SIO；允许在最短路径集合内任选，不可绕路，链路不可拆分。

### 3.3.3 逻辑到物理的映射结果

恒等摆放。**映射粒度**：每条逻辑链路带宽 \(b={{8|manhattan|wf/b|g}}\mathrm T\)（不可拆分）；逐条映射到一条物理路径，路径上每一跳占用 1 个 \(b\) 粒度的有向边端口；边负载 \(C\) 以逻辑链路**条数**计，带宽 = \(C\cdot b\)。逐 die 片上走线见 `figs/die_map/`（SVG）。

{{8|manhattan|n_flows|,d}} 条 die 间逻辑链路的最短路径选择结果见 `mapping/s2_dsl_shortest_8x8.log`。

!fig[fig_die_map_s2_dsl_shortest_8x8.png](图 3.3-1b 方案二逻辑→物理映射可视化：左上连续 3×3，按 b 粒度片上走线（`figs/die_map/s2_dsl_shortest_8x8/`）)

中间割上的 {{8|manhattan|wf/n_hot|d}} 条有向边全部达到下界 {{8|manhattan|lb|d}} 条 = {{8|manhattan|lb_tbps|.1f}}T，馈通占已用 D2D 带宽 {{8|manhattan|ft_bw_share|.0f%}}（与方案一相同，因为跳数相同）。

### 3.3.4 每颗 die 的逻辑模块构成

!fig[fig_die_manhattan_8x8.png](图 3.3-1 方案二 die 顶层模块架构：模块与方案一相同，SIO 每方向需求降到二分下界)

| 模块 | 交换 / 转发需求 | 相对方案一 |
|---|---:|---|
| L1 / L2 / L3 | 各 {{8|manhattan|wf/L1|.1f}}T，合计 **{{8|manhattan|wf/die_sw|.1f}}T** | 相同 |
| Feedthrough | 最大 {{8|manhattan|wf/ft_max|.1f}}T / 平均 {{8|manhattan|wf/ft_mean|.1f}}T | 平均相同 |
| SIO 每方向 | **{{8|manhattan|wf/sio_ports_b|d}} × {{8|manhattan|wf/b|g}}T = {{8|manhattan|wf/sio_side_max|.1f}}T**（≈{{8|manhattan|wf/sio_lanes400|d}}×400G） | 方案一为 {{8|xy_o1turn_cw|wf/sio_ports_b|d}} × {{8|manhattan|wf/b|g}}T |

### 3.3.5 最终物理构型方案

!fig[fig_phys_manhattan_8x8.png](图 3.3-2 方案二物理构型：有向边逻辑链路条数（每条 b={{8|manhattan|wf/b|g}}T；中间割达二分下界）)

- 最热边 **{{8|manhattan|C|d}} 条 × {{8|manhattan|wf/b|g}}T = {{8|manhattan|C_tbps|.1f}}T**（{{8|manhattan|wf/n_hot|d}} 条有向边），单边加速比 {{8|manhattan|sp_edge|.2f}}×（= \(n/2\)，二分割下界，任何路由不可能更低）。
- 平均边 {{8|manhattan|wf/edge_mean|.1f}}T（与方案一相同，总量不变），最轻边 **{{8|manhattan|wf/edge_min|.1f}}T**：远离中间割的边仍有空闲带宽，为方案三直连提供余量。
- **SIO 配置（静态功耗口径）**：同构 die 每条有向边按最热边配置，全阵列 {{8|manhattan|power/0.1/n_dir_edges|d}} 条 × {{8|manhattan|C_tbps|.1f}}T = **{{8|manhattan|power/0.1/sio_cfg_tbps|,.0f}}T**（与方案一相比随最热边同比例下降），SIO 静态 = 配置带宽 × 0.35 × 0.7 = {{8|manhattan|power/0.1/sio_static_W|,.0f}} W。

### 3.3.6 整体方案量化指标

**跳数。** 与方案一相同：单链路平均 / 最大 {{8|manhattan|hops_mean|.2f}} / {{8|manhattan|hops_max|d}}；端到端平均 / 最大 {{8|manhattan|e2e_hops_mean|.2f}} / {{8|manhattan|e2e_hops_max|.0f}}。最大时延路径 **{{8|manhattan|worst_path|s}}**。

**馈通走线距离。** 单链路平均 / 最大 {{8|manhattan|wire_mean|.1f}} / **{{8|manhattan|wire_max|.0f}} mm**（方案一 {{8|xy_o1turn_cw|wire_max|.0f}} mm，多转弯所致）；端到端平均 / 最大 {{8|manhattan|e2e_wire_mean|.0f}} / {{8|manhattan|e2e_wire_max|.0f}} mm。

**功耗。** \(P_{\mathrm{chip}}=3795+\underbrace{{{8|manhattan|power/0.1/sio_static_W|,.0f}}}_{\text{SIO 静态}}+\underbrace{{{8|manhattan|power/0.1/sio_dyn_W|,.0f}}}_{\text{SIO 动态}}+\underbrace{{{8|manhattan|power/0.1/wire_W|,.0f}}}_{\text{馈通}}={{8|manhattan|power/0.1/total_W|,.0f}}\) W（0.06：{{8|manhattan|power/0.06/total_W|,.0f}} W）；SerDes / SIO / 馈通占 {{8|manhattan|power/0.1/serdes_share|.1f%}} / {{8|manhattan|power/0.1/sio_share|.1f%}} / {{8|manhattan|power/0.1/wire_share_total|.1f%}}；静态 {{8|manhattan|power/0.1/static_W|,.0f}} W（{{8|manhattan|power/0.1/static_share|.1f%}}）。

**时延。** 最小 / 平均 / 最大 {{8|manhattan|e2e_lat_min|.0f}} / {{8|manhattan|e2e_lat_mean|.0f}} / **{{8|manhattan|e2e_lat_max|,.0f}} ns**。最坏路径分解：SIO {{8|manhattan|e2e_worst/iface|.0f}}（{{8|manhattan|e2e_worst/iface_share|.0f%}}）、馈通 + 缝隙 {{8|manhattan|e2e_worst/ft|.0f}}（{{8|manhattan|e2e_worst/ft_share|.0f%}}）、转向 {{8|manhattan|e2e_worst/turn|.0f}}（{{8|manhattan|e2e_worst/turns|d}} 次）、\(t_{\mathrm{sw\_die}}\) {{8|manhattan|e2e_worst/sw_die|.0f}}（{{8|manhattan|e2e_worst/sw_die_share|.0f%}}）、\(t_{\mathrm{sw\_sw}}\) {{8|manhattan|e2e_worst/sw_sw|.0f}} ns（{{8|manhattan|e2e_worst/sw_sw_share|.0f%}}）。

### 3.3.7 给定流量矩阵下的指标

与方案一相同，喷洒使三种场景激活全部逻辑链路、边负载即图 3.3-2：

| 场景 | 最热边 | 平均馈通（端到端） | 最小 / 平均 / 最大时延（ns） | 数据搬移功耗 | 芯片总功耗 |
|---|---:|---:|---:|---:|---:|
| 最佳 / 最差 / AllToAll | {{8|manhattan|C_tbps|.1f}}T | {{8|manhattan|e2e_wire_mean|.0f}} mm | {{8|manhattan|e2e_lat_min|.0f}} / {{8|manhattan|e2e_lat_mean|.0f}} / {{8|manhattan|e2e_lat_max|,.0f}} | {{8|manhattan|power/0.1/scenarios/a2a_100/W|,.0f}} W | {{8|manhattan|power/0.1/scenarios/a2a_100/chip_W|,.0f}} W |

图 3.3-3 给出该方案在给定流量矩阵下的 die2die 流量带宽，有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图）。与方案一相同，三种场景逐边相同且 xx = yy；与图 3.2-4 相比，最热边降到二分下界。

!fig[fig_flow_manhattan_a2a_100_8x8.png](图 3.3-3 方案二 die2die 流量带宽：最佳 / 最差 / AllToAll（三者逐边相同；有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

> **要点**：方案二是 CLOS 构型的带宽最优解（达下界），但最大时延最高；它也是方案三的基线。

## 3.4 方案三：DSL+直连

> **方案要点**：在方案二上叠加 L1→L3 直连逻辑边，利用远离中间割的空闲 D2D 带宽，让部分 die 对绕过 L2 一跳到达。x 为允许的最热边增长：x = 0 时 D2D 带宽不增加即可叠加 {{8|s3_0|n_directs|,d}} 条；x = 10% 时 {{8|s3_10|n_directs|,d}} 条（占 die 间 L1→L3 对 {{8|s3_10|direct_share|.0f%}}），最大时延降 {{8|s3_10|lat_drop|.0f%}}、满载功耗降 {{8|s3_10|power/0.1/total_drop|.1f%}}。代价是 L1 / L3 端口增加（单 L1 最多 +{{8|s3_10|l1_sw_ports_growth|.0f%}}）。

### 3.4.1 逻辑交换方案

**逻辑交换拓扑。** CLOS(64,64,64) 骨干不变，另增 L1→L3 直连边：每条带宽 \(b={{8|manhattan|wf/b|g}}\mathrm T\)，L1 增加对应输出端口、L3 增加输入端口；每颗 die 另有 1 条本 die 直连（不占 die 边）。

| x | die 间直连 | 单 L1 交换容量 | 单 die 交换合计 | 最热边 |
|---:|---:|---:|---:|---:|
| 0 | {{8|s3_0|n_directs|,d}} 条 | {{8|s3_0|wf/L1|.1f}}T（+{{8|s3_0|wf/L1_add|.1f}}T） | {{8|s3_0|wf/die_sw|.1f}}T | {{8|s3_0|C_tbps|.1f}}T（{{8|s3_0|d2d_growth|+.1f%}}） |
| 5% | {{8|s3_5|n_directs|,d}} 条 | {{8|s3_5|wf/L1|.1f}}T（+{{8|s3_5|wf/L1_add|.1f}}T） | {{8|s3_5|wf/die_sw|.1f}}T | {{8|s3_5|C_tbps|.1f}}T（{{8|s3_5|d2d_growth|+.1f%}}） |
| 10% | {{8|s3_10|n_directs|,d}} 条 | {{8|s3_10|wf/L1|.1f}}T（+{{8|s3_10|wf/L1_add|.1f}}T） | {{8|s3_10|wf/die_sw|.1f}}T | {{8|s3_10|C_tbps|.1f}}T（{{8|s3_10|d2d_growth|+.1f%}}） |

!fig[fig_logic_s3_8x8.png](图 3.4-1 方案三逻辑交换拓扑（x = 10%）：CLOS 骨干 + L1→L3 直连（橙色，示意直连最多的一个 L1）)

**转发与负载均衡。** 有直连的 die 对，其 L1→L3 流量（AllToAll 下为 \(b\)）走直连一跳；超出直连容量的部分（如置换流量）溢出回 CLOS 两级喷洒。无直连的 die 对与方案二相同。

### 3.4.2 物理构型方案与约束

- 物理构型同方案二（{{8|manhattan|wf/N|d}} 颗同构 die、8×8 Mesh、相邻 SIO）。
- **约束**：CLOS 部分沿用方案二路径；直连按收益（两跳时延 − 直连时延）贪心选取，路径允许有限绕路；叠加后每条有向边负载 ≤ \((1+x)\,C_2\)。

### 3.4.3 逻辑到物理的映射结果

**映射粒度**与方案二相同：每条直连亦为一条带宽 \(b={{8|manhattan|wf/b|g}}\mathrm T\) 的逻辑链路，不可拆分；CLOS 部分路径不变。直连平均 / 最大 {{8|s3_10|direct_hops_mean|.2f}} / {{8|s3_10|direct_hops_max|d}} 跳、平均馈通 {{8|s3_10|direct_wire_mean|.0f}} mm、最大时延 {{8|s3_10|direct_lat_max|,.0f}} ns（x = 10%）。由于中间割已满，x = 0 的直连全部落在同一象限内；x > 0 后才能跨割。全部直连路径见 `mapping/s3_l1l3_direct_x{0,5,10}_8x8.log`；片上走线见 `figs/die_map/s3_l1l3_direct_x*_8x8/`。

!fig[fig_die_map_s3_l1l3_direct_x10_8x8.png](图 3.4-1b 方案三 x=10% 映射可视化：左上连续 3×3，CLOS + 直连片上走线（粒度 b={{8|manhattan|wf/b|g}}T）)

### 3.4.4 每颗 die 的逻辑模块构成

!fig[fig_die_s3_10_8x8.png](图 3.4-2 方案三 die 顶层模块架构（x = 10%）：L1 / L3 增加直连端口，SIO 需求随最热边增长)

| 模块 | x = 0 | x = 5% | x = 10% |
|---|---:|---:|---:|
| L1 / L3 | 各 {{8|s3_0|wf/L1|.1f}}T | 各 {{8|s3_5|wf/L1|.1f}}T | 各 {{8|s3_10|wf/L1|.1f}}T |
| L2 | {{8|s3_0|wf/L2|.1f}}T | {{8|s3_5|wf/L2|.1f}}T | {{8|s3_10|wf/L2|.1f}}T |
| 单 die 交换合计 | {{8|s3_0|wf/die_sw|.1f}}T | {{8|s3_5|wf/die_sw|.1f}}T | **{{8|s3_10|wf/die_sw|.1f}}T** |
| Feedthrough 最大 / 平均 | {{8|s3_0|wf/ft_max|.1f}} / {{8|s3_0|wf/ft_mean|.1f}}T | {{8|s3_5|wf/ft_max|.1f}} / {{8|s3_5|wf/ft_mean|.1f}}T | {{8|s3_10|wf/ft_max|.1f}} / {{8|s3_10|wf/ft_mean|.1f}}T |
| SIO 每方向 | {{8|s3_0|wf/sio_ports_b|d}}×{{8|manhattan|wf/b|g}}T | {{8|s3_5|wf/sio_ports_b|d}}×{{8|manhattan|wf/b|g}}T | {{8|s3_10|wf/sio_ports_b|d}}×{{8|manhattan|wf/b|g}}T |

### 3.4.5 最终物理构型方案

!fig[fig_phys_s3_10_8x8.png](图 3.4-3 方案三物理构型（x=10%）：CLOS+直连叠加后的有向边逻辑链路条数（×b）)

- x = 10%：最热边 **{{8|s3_10|C_tbps|.1f}}T**（{{8|s3_10|wf/n_hot|d}} 条），平均 {{8|s3_10|wf/edge_mean|.1f}}T，最轻 {{8|s3_10|wf/edge_min|.1f}}T；D2D 总量 {{8|s3_10|wf/total_d2d|,.0f}}T（方案二 {{8|manhattan|wf/total_d2d|,.0f}}T）。
- **SIO 配置（静态功耗口径）**：同构 die 每条有向边按最热边配置，全阵列 {{8|s3_10|power/0.1/n_dir_edges|d}} 条 × {{8|s3_10|C_tbps|.1f}}T = **{{8|s3_10|power/0.1/sio_cfg_tbps|,.0f}}T**（x = 0 / 5% 分别为 {{8|s3_0|power/0.1/sio_cfg_tbps|,.0f}}T / {{8|s3_5|power/0.1/sio_cfg_tbps|,.0f}}T），SIO 静态 = 配置带宽 × 0.35 × 0.7 = {{8|s3_10|power/0.1/sio_static_W|,.0f}} W。
- x = 0：最热边仍为 {{8|s3_0|C_tbps|.1f}}T，直连只填充了原本空闲的边（最轻边从 {{8|manhattan|wf/edge_min|.1f}}T 升到 {{8|s3_0|wf/edge_min|.1f}}T）。

### 3.4.6 整体方案量化指标

| 指标 | x = 0 | x = 5% | x = 10% | 方案二 |
|---|---:|---:|---:|---:|
| 端到端平均 / 最大跳数 | {{8|s3_0|e2e_hops_mean|.2f}} / {{8|s3_0|e2e_hops_max|.0f}} | {{8|s3_5|e2e_hops_mean|.2f}} / {{8|s3_5|e2e_hops_max|.0f}} | {{8|s3_10|e2e_hops_mean|.2f}} / {{8|s3_10|e2e_hops_max|.0f}} | {{8|manhattan|e2e_hops_mean|.2f}} / {{8|manhattan|e2e_hops_max|.0f}} |
| 端到端平均 / 最大馈通（mm） | {{8|s3_0|e2e_wire_mean|.0f}} / {{8|s3_0|e2e_wire_max|.0f}} | {{8|s3_5|e2e_wire_mean|.0f}} / {{8|s3_5|e2e_wire_max|.0f}} | {{8|s3_10|e2e_wire_mean|.0f}} / {{8|s3_10|e2e_wire_max|.0f}} | {{8|manhattan|e2e_wire_mean|.0f}} / {{8|manhattan|e2e_wire_max|.0f}} |
| 最小 / 平均 / 最大时延（ns） | {{8|s3_0|e2e_lat_min|.0f}} / {{8|s3_0|e2e_lat_mean|.0f}} / **{{8|s3_0|e2e_lat_max|,.0f}}** | {{8|s3_5|e2e_lat_min|.0f}} / {{8|s3_5|e2e_lat_mean|.0f}} / **{{8|s3_5|e2e_lat_max|,.0f}}** | {{8|s3_10|e2e_lat_min|.0f}} / {{8|s3_10|e2e_lat_mean|.0f}} / **{{8|s3_10|e2e_lat_max|,.0f}}** | {{8|manhattan|e2e_lat_min|.0f}} / {{8|manhattan|e2e_lat_mean|.0f}} / {{8|manhattan|e2e_lat_max|,.0f}} |
| 最大时延相对方案二 | {{8|s3_0|lat_vs_s2|+.0f%}} | {{8|s3_5|lat_vs_s2|+.0f%}} | {{8|s3_10|lat_vs_s2|+.0f%}} | — |
| SIO 静态 / 动态 / 馈通（W） | {{8|s3_0|power/0.1/sio_static_W|,.0f}} / {{8|s3_0|power/0.1/sio_dyn_W|,.0f}} / {{8|s3_0|power/0.1/wire_W|,.0f}} | {{8|s3_5|power/0.1/sio_static_W|,.0f}} / {{8|s3_5|power/0.1/sio_dyn_W|,.0f}} / {{8|s3_5|power/0.1/wire_W|,.0f}} | {{8|s3_10|power/0.1/sio_static_W|,.0f}} / {{8|s3_10|power/0.1/sio_dyn_W|,.0f}} / {{8|s3_10|power/0.1/wire_W|,.0f}} | {{8|manhattan|power/0.1/sio_static_W|,.0f}} / {{8|manhattan|power/0.1/sio_dyn_W|,.0f}} / {{8|manhattan|power/0.1/wire_W|,.0f}} |
| **满载芯片总功耗（W）** | **{{8|s3_0|power/0.1/total_W|,.0f}}**（{{8|s3_0|power/0.1/total_vs_s2|+.1f%}}） | **{{8|s3_5|power/0.1/total_W|,.0f}}**（{{8|s3_5|power/0.1/total_vs_s2|+.1f%}}） | **{{8|s3_10|power/0.1/total_W|,.0f}}**（{{8|s3_10|power/0.1/total_vs_s2|+.1f%}}） | {{8|manhattan|power/0.1/total_W|,.0f}} |
| 静态功耗（W） | {{8|s3_0|power/0.1/static_W|,.0f}} | {{8|s3_5|power/0.1/static_W|,.0f}} | {{8|s3_10|power/0.1/static_W|,.0f}} | {{8|manhattan|power/0.1/static_W|,.0f}} |

最大时延路径（x = 10%）为 **{{8|s3_10|worst_path|s}}**（该 die 对无直连，仍走两跳）；最坏路径中馈通占 {{8|s3_10|e2e_worst/ft_share|.0f%}}、SIO 占 {{8|s3_10|e2e_worst/iface_share|.0f%}}、\(t_{\mathrm{sw\_die}}+t_{\mathrm{sw\_sw}}\) 占 {{8|s3_10|e2e_worst/sw_die_share|.0f%}} + {{8|s3_10|e2e_worst/sw_sw_share|.0f%}}。最小时延 {{8|s3_10|e2e_lat_min|.0f}} ns 来自本 die 直连（只有 \(t_{\mathrm{sw\_die}}\)，直连不经 L2）；有直连的 die 对比经 L2 少一个 \(t_{\mathrm{sw\_sw}}\)（70 ns），这是直连时延收益的一部分。

### 3.4.7 给定流量矩阵下的指标

| 场景 | 激活路径 | 最大时延（ns） | 数据搬移功耗 x = 0 / 10% | 芯片总功耗 x = 10% |
|---|---|---:|---:|---:|
| 最佳（AllToAll 均匀，直连满用） | 直连 + 其余 die 对的 CLOS 两跳 | {{8|s3_10|e2e_lat_max|,.0f}} | {{8|s3_0|power/0.1/scenarios/a2a_100/W|,.0f}} / {{8|s3_10|power/0.1/scenarios/a2a_100/W|,.0f}} W | {{8|s3_10|power/0.1/scenarios/a2a_100/chip_W|,.0f}} W |
| 最差（置换满载，直连只承载 b，其余溢出） | 直连 + 溢出部分走 CLOS | {{8|manhattan|e2e_lat_max|,.0f}}（回到方案二） | {{8|s3_0|power/0.1/scenarios/perm_100/W|,.0f}} / {{8|s3_10|power/0.1/scenarios/perm_100/W|,.0f}} W | {{8|s3_10|power/0.1/scenarios/perm_100/chip_W|,.0f}} W |
| AllToAll | 同最佳 | {{8|s3_10|e2e_lat_max|,.0f}} | {{8|s3_0|power/0.1/scenarios/a2a_100/W|,.0f}} / {{8|s3_10|power/0.1/scenarios/a2a_100/W|,.0f}} W | {{8|s3_10|power/0.1/scenarios/a2a_100/chip_W|,.0f}} W |

图 3.4-4 给出 x = 10% 时两类不同流量矩阵下的 die2die 流量带宽，有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图）（yy 含 CLOS 链路与直连）。AllToAll（即最佳场景）中有直连的 die 对全部流量走直连，CLOS 链路只承载其余部分，所以 xx < yy；置换满载时直连只分担 \(b/N\)（期望），流量回到 CLOS，xx 接近 CLOS 部分的满载。

!fig[fig_flow_s3_10_a2a_100_8x8.png](图 3.4-4a 方案三（x=10%）die2die 流量带宽：最佳 / AllToAll 满载（有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

!fig[fig_flow_s3_10_perm_100_8x8.png](图 3.4-4b 方案三（x=10%）die2die 流量带宽：最差，置换满载（有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

> **要点**：直连收益集中在均匀流量；置换流量下每个 die 对只有 \(b\) 走直连，其余回到 CLOS，时延与功耗接近方案二。x = 0 是 “零 D2D 代价” 的增强，x = 10% 收益更大，但最热边升到 \((1+x)C_2\) 后全阵列 SIO 配置带宽与静态功耗同比例增加（{{8|s3_10|power/0.1/sio_static_W|,.0f}} W vs {{8|manhattan|power/0.1/sio_static_W|,.0f}} W），L1 / L3 端口也要加。

## 3.5 方案四：O1Turn(DR)

> **方案要点**：去掉 CLOS 分级，每颗 die 是一个同构 NoC router，src die → dst die 按顺时针、逆时针 O1Turn 各 50% 一段直达。任意流量矩阵下单边负载 ≤ \((n/2)\,B_{die}\)，因此交换侧按 **{{8|o1t|C_tbps|.1f}}T / 方向** 无阻塞配置（恰为二分下界，与方案二相同），router 交换容量 **{{8|o1t|router_tbps|.1f}}T**（{{8|o1t|router_x|.0f}}×B_die）。换来端到端只走一段：满载功耗 {{8|o1t|power/0.1/total_W|,.0f}} W 为四方案最低（{{8|o1t|power/0.1/total_vs_s2|+.1f%}} 相对方案二），平均时延 {{8|o1t|e2e_lat_mean|.0f}} ns（{{8|o1t|lat_mean_vs_s2|+.0f%}}），最大时延 {{8|o1t|e2e_lat_max|,.0f}} ns（{{8|o1t|lat_vs_s2|+.0f%}}）。

### 3.5.1 逻辑交换方案

**逻辑交换拓扑。** {{8|manhattan|wf/N|d}} 个同构 NoC router 组成 8×8 网格（逻辑拓扑与物理 Mesh 重合）。每个 router 5 组端口：线路侧 \(B_{die}={{8|manhattan|wf/B|g}}\mathrm T\)（{{8|manhattan|ports_per_die|d}}×400GE）+ 东 / 南 / 西 / 北各 \((n/2) B_{die}={{8|o1t|wf/side_bw|.1f}}\mathrm T\)；交换容量 \((2n+1)B_{die}={{8|o1t|router_tbps|.1f}}\mathrm T\)。

!fig[fig_logic_o1t_8x8.png](图 3.5-1 O1Turn(DR) 逻辑交换拓扑：8×8 同构 NoC router 网格，相邻 router 双向链路各 (n/2)·B_die)

**转发与负载均衡。** 不喷洒到其他 die：die 对流量 \(T(s,d)\) 在顺时针、逆时针两条 O1Turn 路径（XY 与 YX，各转一次弯；同行 / 同列两条重合）上各发 50%，途经 router 逐跳转发。可容许流量满足 hose 约束 \(\sum_d T(s,d)\le B_{die}\)、\(\sum_s T(s,d)\le B_{die}\)。每条边承载的源行流量与宿行流量都只有一半，最坏置换下单边负载 \(n/2\cdot B_{die}\)（1.6.3 节），与 CLOS 的二分下界相同；只走顺时针单路径时为 \(n\cdot B_{die}\)。

### 3.5.2 物理构型方案与约束

- 1 种同构 die × {{8|manhattan|wf/N|d}} 颗，8×8 Mesh，仅相邻 SIO；每颗 die 只有一个 router（无 L1 / L2 / L3）。
- **约束**：同构 die；交换侧任意置换无阻塞（每有向边 ≥ 经过该边的 src→dst 权重矩阵最大权指派 × \(B_{die}\)，权重 = 经过该边的路径数 × 0.5）；两条路径都是最短路径。

### 3.5.3 逻辑到物理的映射结果

无 CLOS 逻辑链路；die 对流量按顺 / 逆时针各 50% 映射。为与 DSL 方案统一对比，边负载仍折合为 \(b={{8|manhattan|wf/b|g}}\mathrm T\) 的整数倍：无阻塞最热边 \((n/2)B_{die}={{8|o1t|C_tbps|.1f}}\mathrm T={{8|o1t|C|d}}\times b\)。

{{8|o1t|n_flows|,d}} 个 src→dst die 对各映射为顺时针、逆时针两条 O1Turn 路径，共 {{8|o1t|n_paths|,d}} 条（`mapping/s4_o1turn_noc_8x8.log`，同行 / 同列的 die 对两条路径相同）。逐边最大权指派恰为 \(n/2={{8|o1t|C_die|g}}\)，{{8|o1t|edges_at_n|d}} / {{8|o1t|n_edges|d}} 条有向边全部达到该值；外圈对角互打即可触发（1.6.3 节）。

### 3.5.4 每颗 die 的逻辑模块构成

!fig[fig_die_o1t_8x8.png](图 3.5-2 O1Turn(DR) die 顶层模块架构：单个 NoC router（线路侧 + 四向交换侧），过路流量在 router 内转发)

| 模块 | 需求 | 说明 |
|---|---:|---|
| NoC router | **{{8|o1t|router_tbps|.1f}}T** | (2n+1)·B_die；CLOS 方案单 die 交换合计 {{8|manhattan|wf/die_sw|.1f}}T |
| 线路侧 | {{8|manhattan|wf/B|g}}T | {{8|manhattan|ports_per_die|d}}×400GE |
| SIO 每方向 | **{{8|o1t|wf/sio_ports_b|d}} × {{8|manhattan|wf/b|g}}T = {{8|o1t|wf/side_bw|.1f}}T**（≈{{8|o1t|wf/sio_lanes400|d}}×400G） | 邻 die 加速比 n/2 = {{8|o1t|C_die|g}}（与方案二相同）；AllToAll 实际最热边 {{8|o1t|a2a_C_tbps|.1f}}T |
| 过路转发 | AllToAll 最大 {{8|o1t|wf/a2a_ft_max|.1f}}T / 平均 {{8|o1t|wf/ft_mean|.1f}}T | CLOS 方案为 {{8|manhattan|wf/ft_max|.1f}}T（两段路径过路更多） |

### 3.5.5 最终物理构型方案

!fig[fig_phys_o1t_8x8.png](图 3.5-3 O1Turn(DR) 物理构型：任意置换无阻塞所需有向边带宽)

- 无阻塞所需单边带宽 **{{8|o1t|C_tbps|.1f}}T**，全部 {{8|o1t|wf/n_hot|d}} 条有向边相同（\(n/2\cdot B_{die}\)，与位置无关），等于方案二的最热边、比方案一低 {{8|o1t|C_save_vs_xy|.0f%}}。
- 同构 die 按最热方向配置后，每颗 die 4 向 SIO 共 {{8|o1t|wf/side_bw|.1f}}T × 4；全阵列无阻塞 D2D 总量 {{8|o1t|wf/total_d2d|,.0f}}T，AllToAll 实际使用远低于此。
- **SIO 配置（静态功耗口径）**：同构 die 每条有向边按最热边配置，全阵列 {{8|o1t|power/0.1/n_dir_edges|d}} 条 × {{8|o1t|C_tbps|.1f}}T = **{{8|o1t|power/0.1/sio_cfg_tbps|,.0f}}T**（即无阻塞配置，与方案二相同），SIO 静态 = 配置带宽 × 0.35 × 0.7 = {{8|o1t|power/0.1/sio_static_W|,.0f}} W。

### 3.5.6 整体方案量化指标

**跳数。** src→dst 平均 / 最大 {{8|o1t|hops_mean|.2f}} / {{8|o1t|hops_max|d}} 跳（端到端平均含 src = dst 的本地流量为 {{8|o1t|e2e_hops_mean|.2f}}）；最长路径 **{{8|o1t|worst_path|s}}**（对角，{{8|o1t|worst_hops|d}} 跳，经 {{8|o1t|router_traversals_max|d}} 个 router）。只有 CLOS 方案端到端最大跳数（{{8|manhattan|e2e_hops_max|.0f}}）的一半。

**馈通走线距离。** 平均 / 最大 {{8|o1t|wire_mean|.1f}} / {{8|o1t|wire_max|.0f}} mm（单段，与方案一单链路相同）。

**功耗。** \(P_{\mathrm{chip}}=3795+\underbrace{{{8|o1t|power/0.1/sio_static_W|,.0f}}}_{\text{SIO 静态}}+\underbrace{{{8|o1t|power/0.1/sio_dyn_W|,.0f}}}_{\text{SIO 动态}}+\underbrace{{{8|o1t|power/0.1/wire_W|,.0f}}}_{\text{馈通}}={{8|o1t|power/0.1/total_W|,.0f}}\) W（AllToAll 满载，{{8|o1t|power/0.1/total_vs_s2|+.1f%}} 相对方案二）；SerDes / SIO / 馈通占 {{8|o1t|power/0.1/serdes_share|.1f%}} / {{8|o1t|power/0.1/sio_share|.1f%}} / {{8|o1t|power/0.1/wire_share_total|.1f%}}；静态 {{8|o1t|power/0.1/static_W|,.0f}} W。最大功耗出现在最坏置换：{{8|o1t|power/0.1/total_worst_W|,.0f}} W。

**时延。** 最小 / 平均 / 最大 {{8|o1t|e2e_lat_min|.0f}} / {{8|o1t|e2e_lat_mean|.0f}} / **{{8|o1t|e2e_lat_max|,.0f}} ns**（\(t_{\mathrm{sw\_sw}}=0\)，转向 2 ns/次），最大时延比方案二低 {{8|o1t|lat_drop|.0f%}}。最坏路径分解：SIO {{8|o1t|e2e_worst/iface|.0f}}（{{8|o1t|e2e_worst/iface_share|.0f%}}）、馈通 + 缝隙 {{8|o1t|e2e_worst/ft|.0f}}（{{8|o1t|e2e_worst/ft_share|.0f%}}）、转向 {{8|o1t|e2e_worst/turn|.0f}}（{{8|o1t|e2e_worst/turns|d}} 次）、\(t_{\mathrm{sw\_die}}\) {{8|o1t|e2e_worst/sw_die|.0f}}（{{8|o1t|e2e_worst/sw_die_share|.0f%}}）、\(t_{\mathrm{sw\_sw}}\) {{8|o1t|e2e_worst/sw_sw|.0f}} ns（{{8|o1t|e2e_worst/sw_sw_share|.0f%}}）。端到端只走一段、不经 L2，固定项只有一次 \(t_{\mathrm{sw\_die}}\)；最坏路径经过 {{8|o1t|router_traversals_max|d}} 颗 router 但只转一次向，以馈通与 SIO 为主。

### 3.5.7 给定流量矩阵下的指标

无喷洒，激活路径随流量矩阵变化。最佳 / 最差置换由最小 / 最大权指派求得：目标为 1.5.3 节的**动态**数据搬移能耗（SIO 动态份额 \(0.3\cdot0.35h\) + 馈通；SIO 静态按物理构型配置带宽计、对所有置换相同，不进入指派）。每个源 die 把 \(B_{die}\) 全部发给一个宿 die、两条路径各一半，禁止自环：

| 场景 | 激活 die 对 | 平均 / 最大跳数 | 最热边 | 平均馈通 | 最小 / 平均 / 最大时延（ns） | 数据搬移功耗 | 芯片总功耗 |
|---|---|---:|---:|---:|---:|---:|---:|
| 最佳（相邻互换） | {{8|o1t|wf/scen/perm_best/n_paths|d}} 对（相邻，两条路径重合），如 {{8|o1t|wf/scen/perm_best/example|s}} | {{8|o1t|wf/scen/perm_best/hops_mean|.1f}} / {{8|o1t|wf/scen/perm_best/hops_max|d}} | {{8|o1t|wf/scen/perm_best/edge_max|.1f}}T | {{8|o1t|wf/scen/perm_best/wire_mean|.0f}} mm | {{8|o1t|wf/scen/perm_best/lat_min|.0f}} / {{8|o1t|wf/scen/perm_best/lat_mean|.0f}} / {{8|o1t|wf/scen/perm_best/lat_max|.0f}} | {{8|o1t|power/0.1/scenarios/perm_best/W|,.0f}} W | {{8|o1t|power/0.1/total_best_W|,.0f}} W |
| 最差（远距置换） | {{8|o1t|wf/scen/perm_worst/n_paths|d}} 对（{{8|o1t|wf/scen/perm_worst/n_routes|d}} 条路径），如 {{8|o1t|wf/scen/perm_worst/example|s}} | {{8|o1t|wf/scen/perm_worst/hops_mean|.1f}} / {{8|o1t|wf/scen/perm_worst/hops_max|d}} | {{8|o1t|wf/scen/perm_worst/edge_max|.1f}}T | {{8|o1t|wf/scen/perm_worst/wire_mean|.0f}} mm | {{8|o1t|wf/scen/perm_worst/lat_min|.0f}} / {{8|o1t|wf/scen/perm_worst/lat_mean|.0f}} / {{8|o1t|wf/scen/perm_worst/lat_max|,.0f}} | {{8|o1t|power/0.1/scenarios/perm_worst/W|,.0f}} W | {{8|o1t|power/0.1/total_worst_W|,.0f}} W |
| AllToAll 满载 | 全部 {{8|o1t|n_flows|,d}} 对，各 b（两条路径各 b/2） | {{8|o1t|hops_mean|.2f}} / {{8|o1t|hops_max|d}} | {{8|o1t|a2a_C_tbps|.1f}}T | {{8|o1t|e2e_wire_mean|.0f}} mm | {{8|o1t|e2e_lat_min|.0f}} / {{8|o1t|e2e_lat_mean|.0f}} / {{8|o1t|e2e_lat_max|,.0f}} | {{8|o1t|power/0.1/scenarios/a2a_100/W|,.0f}} W | {{8|o1t|power/0.1/total_W|,.0f}} W |

图 3.5-4 给出三种流量矩阵下的 die2die 流量带宽，有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图）；yy 为任意置换无阻塞所需的边带宽。最佳置换只占用相邻 die 之间的边，最差置换把多条边推到 yy 上限，AllToAll 介于两者之间。

!fig[fig_flow_o1t_perm_best_8x8.png](图 3.5-4a 方案四 die2die 流量带宽：最佳置换（有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

!fig[fig_flow_o1t_perm_worst_8x8.png](图 3.5-4b 方案四 die2die 流量带宽：最差置换（有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

!fig[fig_flow_o1t_a2a_100_8x8.png](图 3.5-4c 方案四 die2die 流量带宽：AllToAll 满载（有向边标注 xx/yy（Tbps）：xx 为该流量矩阵下的实际 die2die 流量，yy 为该边逻辑链路总带宽（同物理构型图））)

> **要点**：O1Turn(DR) 的性能强烈依赖流量矩阵——相邻互换只需 1 跳、数据搬移仅 {{8|o1t|power/0.1/scenarios/perm_best/W|,.0f}} W；远距置换把最热边推到无阻塞上限 {{8|o1t|wf/scen/perm_worst/edge_max|.1f}}T（顺 / 逆时针分流后与二分下界相同）、搬移功耗比 AllToAll 高 {{8|o1t|worst_perm_vs_a2a|.0f%}}。时延模型中 router 转发不计 \(t_{\mathrm{sw\_sw}}\)，最大时延为四种方案最低；若每颗 router 的仲裁 / 缓冲时延超过 {{8|o1t|tr_breakeven_vs_xy|.0f}} ns，最大时延将不再低于方案一。

## 3.6 指标详表

!fig[fig_loads_8x8.png](图 3-3 方案一 / 二 AllToAll 边负载热力图)

!tab 表 3-1 8×8 die 间带宽

<!-- TAB:bw:8 -->

!fig[fig_hops_8x8.png](图 3-4 跳数与馈通走线长度)

!tab 表 3-2 8×8 跳数与馈通走线

<!-- TAB:wire:8 -->

!fig[fig_latency_8x8.png](图 3-5 时延分解)

!tab 表 3-3 8×8 时延

<!-- TAB:lat:8 -->

!fig[fig_power_8x8.png](图 3-6 功耗分解与场景)

!tab 表 3-4 8×8 满载功耗

<!-- TAB:power:8 -->

!tab 表 3-5 8×8 场景数据搬移功耗

<!-- TAB:scen:8 -->

!fig[fig_s3_loads_8x8.png](图 3-7 方案三直连叠加边负载)

!tab 表 3-6 方案三直连与 D2D 增长

<!-- TAB:s3:8 -->

!tab 表 3-7 方案三 L1/L3 端口增长

<!-- TAB:ports:8 -->

## 3.7 方案对比与小结

!tab 表 3-8 8×8 四方案对比

<!-- TAB:summary:8 -->

> 【结论】64R 上方案二仍达二分下界，最大时延只比方案一高 {{8|manhattan|lat_vs_xy|.2f}}×；方案一最热边高 {{8|xy_o1turn_cw|C_vs_s2|.0f%}}，SIO 静态随之增加，满载功耗比方案二高 {{8|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}}。DSL+直连 x=0 的直连全部在象限内，最大时延降 {{8|s3_0|lat_drop|.0f%}}；x>0 才跨割，x = 10% 降 {{8|s3_10|lat_drop|.0f%}}。O1Turn(DR) 端到端只走一段，最大时延 {{8|o1t|e2e_lat_max|,.0f}} ns（比方案二低 {{8|o1t|lat_drop|.0f%}}）、功耗更低；顺 / 逆时针各 50% 分流后单边带宽与方案二相同（二分下界），代价是 router 容量 \(17B_{die}\)（CLOS 单 die 交换合计 \(3B_{die}\)）。功耗口径与第 2 章一致：仅 SerDes+SIO+馈通。
