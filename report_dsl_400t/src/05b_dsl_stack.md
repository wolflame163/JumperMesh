# 第 6 章 DSL 细分方案：单 Reticle 3D 堆叠与可配置 NOW die {#ch6}

方案一 / 二（DSL）把 CLOS(\(N,N,N\)) 的三级 L1 / L2 / L3 共址在每颗 die 上，跨 die 的逻辑链路按第 2、3 章的映射结果经相邻 die 的 SIO 逐跳转发。本章按第 5 章的思路把它细化为 3D 堆叠结构：**每个 Reticle 由底层 NOW die、顶层 SW die 与顶层 OE die 组成**。与第 5 章不同，DSL 的交换全部在 SW die 内完成（L1、L2、L3 三个 switch），NOW die 上没有 router，只承担映射结果的**电气连线**：SW die 垂直端口 ↔ 四边 SIO 端口，以及 SIO 端口 ↔ SIO 端口的馈通。章内依次给出整体架构思路（6.1）、堆叠方案（6.2）、SW die（6.3）、NOW die 的逻辑功能与可配置物理实现（6.4）、OE die（6.5）、floorplan（6.6）与小结（6.7）。

记号沿用第 1～3 章：die 数 \(N=n^2\)（16R 为 {{4|now|N_die|d}}，64R 为 {{8|now|N_die|d}}），每条逻辑链路带宽 \(b=B_{die}/N\)（16R {{4|now|b_tbps|g}}T，64R {{8|now|b_tbps|g}}T），\(U=N-1\) 为每颗 die 的跨 die 链路数（每级每方向），\(C\) 为物理构型中最热有向边的逻辑链路条数。流水线数 \(N_{pipe}=B_{die}/3.2\mathrm T\) 与 OE die 沿用第 5 章。以 16R 方案二为主线，64R 与方案一并列在表中。

## 6.1 整体架构思路

!fig[fig_now_idea.png](图 6-1 DSL 3D 堆叠的逻辑架构：L1 / L2 / L3 在 SW die 内，跨 die 逻辑链路由 NOW die 的静态连线承载（示例为 L1(i)→L2(j) 经 die k 馈通）)

**逻辑交换架构（图 6-1）。**

- **SW die 实现全部交换。** 每颗 SW die 上有 L1、L2、L3 三个 switch，分别是 CLOS 的第一、二、三级在本 die 上的节点。L1→L2 与 L2→L3 两级之间各有 \(N\times N\) 条逻辑链路，每条带宽 \(b\)；其中同 die 的链路（每颗 die 每级 1 条）在 SW die 内部完成，其余 \(U\) 条经混合键合落到 NOW die。
- **NOW die 只做连线。** 每条跨 die 逻辑链路在 NOW die 上就是一条从源 die 垂直端口出发、经若干颗 die 的 SIO 与馈通、到宿 die 垂直端口的固定电气通路，路径即第 2、3 章的映射结果（方案一 XY+O1Turn 顺时针、方案二曼哈顿最短路）。通路上没有缓冲、仲裁或报文处理。
- **与第 5 章的区别。** 第 5 章的 NOW die 承载 \(M\) 个 NoC 平面 router，是一个分组交换网络；本章的 NOW die 是**电路交换式的静态走线**：交换完全在 SW die 的 L1 / L2 / L3 中完成，NOW die 只决定 “哪条 lane 接哪条 lane”，并且这个关系在上电配置后不再变化。
- **为什么要可配置。** 映射结果在每颗 die 上要求的连线各不相同（16R {{4|now|s2/demand/distinct_patterns|d}} 颗 die 有 {{4|now|s2/demand/distinct_patterns|d}} 种不同的连线图样，64R {{8|now|s2/demand/distinct_patterns|d}} 种，6.4.1 节）。如果 NOW die 用固定金属连线实现，\(n^2\) 颗 die 需要 \(n^2\) 套不同掩模；本章用**同构的行列总线 + 稀疏静态 mux**，所有 NOW die 是同一个设计，差别只在每颗 die 写入的配置码（6.4.2～6.4.5 节）。

**端到端转发流程。**

1. 入向：光纤 → OE die 光引擎切片 \(i\) → NOW 点对点通道 \(i\) → SW die 流水线 \(i\)（MAC / IPP）→ L1。
2. L1 把流量均匀喷洒到 \(N\) 个 L2（本 die 的 1 个在 SW die 内部，其余 \(U\) 个经 L1_out 垂直端口进入 NOW die）。
3. NOW die 按静态配置把每条 L1_out lane 接到出向 SIO lane，沿途各 die 直通或转向馈通，到宿 die 后接入 L2_in 垂直端口。
4. L2 按目的 die 交换，再经 L2_out → NOW die → 目的 die 的 L3_in（同 die 的直接在 SW die 内部）。
5. L3 按流重排序后送 EPP，再经 NOW 点对点通道 → OE die → 光纤。

时延与功耗沿用第 2、3 章方案一 / 二的模型：每跳 SIO、馈通走线、转向与 \(t_{\mathrm{sw\_die}}\)、\(t_{\mathrm{sw\_sw}}\) 不变；NOW die 上的静态 mux 是组合逻辑选择器，不引入排队，只在每个转向 / 注入 / 弹出点增加一级门延迟与少量中继。

## 6.2 单 Reticle 多 die 堆叠方案

!fig[fig_now_stack.png](图 6-2 DSL 3D 堆叠的单 Reticle 多 die 堆叠与连接关系（每个 Reticle 一颗 NOW、SW、OE die）：(a) 16R 顶视；(b) 64R 顶视；(c) 沿南北中线的侧切图（纵向放大，尺寸示意）)

封装与第 5 章相同（图 6-2）：

- **顶视（图 6-2(a)(b)）。** NOW die 占满整个 Reticle（32 × 25 mm）；唯一的 OE die 沿北边放置，SW die 紧贴其南侧。SW die 北部是 \(N_{pipe}\) 个流水线切片（16R {{4|now|N_pipe|d}} 个、64R {{8|now|N_pipe|d}} 个），与 OE die 的光引擎切片一一对齐；南部是 L1、L2、L3 三个交换核，正下方是垂直端口键合区。
- **侧切（图 6-2(c)）**，自下而上：供电 / 载板（经 NOW die TSV 供电）→ NOW die（行列总线、静态 mux、SW↔OE 点对点走线、四边 SIO PHY）→ 混合键合层 → 顶层 SW die（南）与 OE die（北）→ OE die 上方 FAU 垂直出纤，SW die 上方冷板（为 FAU 开窗）。
- **连接关系**见表 6-1。顶层 die 之间没有直接连线，所有电连接都经 NOW die 中转。与第 5 章相比，SW↔NOW 之间不再是 \(M\) 个 3.2T 的平面口，而是 \(4U\) 条带宽 \(b\) 的 lane；NOW die 四边的 SIO 带宽等于物理构型的 \(C\cdot b\)。

!tab 表 6-1 单 Reticle 内的连接关系（每方向带宽，方案二）

| 连接 | 物理通道 | 16R | 64R |
|---|---|---:|---:|
| OE die ↔ SW die（线路侧） | OE 键合 ↓ → NOW 点对点短线 → 键合 ↑ SW；无交换（同第 5 章） | {{4|stk|oe_slices|d}} × 3.2T = {{4|stk|oe_tbps|g}}T | {{8|stk|oe_slices|d}} × 3.2T = {{8|stk|oe_tbps|g}}T |
| SW die ↔ NOW die（交换侧垂直端口） | L1_out / L2_out 下行、L2_in / L3_in 上行，各 \(U\) 条 lane | {{4|now|sw_vert_lanes|d}} × {{4|now|b_tbps|g}}T = {{4|now|sw_vert_tbps|.1f}}T | {{8|now|sw_vert_lanes|d}} × {{8|now|b_tbps|g}}T = {{8|now|sw_vert_tbps|.1f}}T |
| NOW die ↔ 相邻 Reticle | 四边 SIO，每边 \(C\) 条 lane（lane \(k\) = SIO 端口 \(k\)） | 每边 {{4|now|s2/C|d}} × \(b\) = {{4|now|s2/C_tbps|.1f}}T | 每边 {{8|now|s2/C|d}} × \(b\) = {{8|now|s2/C_tbps|.1f}}T |
| 外部光互联 | OE die → FAU → 光纤向上（同第 5 章） | {{4|stk|fibres_die|d}} 芯（{{4|stk|n_fau|d}} 个 FAU） | {{8|stk|fibres_die|d}} 芯（{{8|stk|n_fau|d}} 个 FAU） |
| 供电 | 载板 → NOW TSV → 顶层 die | — | — |

## 6.3 SW die：L1 / L2 / L3 switch

!fig[fig_now_sw.png](图 6-3 SW die 的逻辑模块与垂直端口（16R）)

- **流水线切片。** 与第 5 章相同，SW die 北部有 \(N_{pipe}\) 条 3.2T 流水线，每条依次为 OE 接口（PCS / FEC / MAC）→ IPP → EPP → 接口处理（TM / 队列）。
- **L1（第一级）。** 入：\(N_{pipe}\) 个 3.2T 线路侧口（来自 IPP）；出：\(N\) 个带宽 \(b\) 的口，分别连全部 \(N\) 个 L2。L1 把入向流量按包或按流均匀喷洒到 \(N\) 个出口，所以任意流量矩阵下每条 L1→L2 链路的负载都不超过 \(b\)（第 1 章）。
- **L2（第二级）。** \(N\) 入 \(N\) 出，每口 \(b\)，按目的 die 把流量交到对应 L3。
- **L3（第三级）。** 入：\(N\) 个 \(b\) 口（来自全部 L2）；出：\(N_{pipe}\) 个 3.2T 口送 EPP，按流重排序。
- **本 die 内部链路。** L1→本 die L2、L2→本 die L3 各一条，带宽 \(b\)（16R {{4|now|sw_local_tbps|g}}T 合计），不经过 NOW die。
- **垂直端口。** 其余链路全部经混合键合落到 NOW die：L1_out、L2_out 各 \(U\) 条下行 lane，L2_in、L3_in 各 \(U\) 条上行 lane，合计 \(4U\) = {{4|now|sw_vert_lanes|d}} 条（16R）/ {{8|now|sw_vert_lanes|d}} 条（64R），带宽 {{4|now|sw_vert_tbps|.1f}}T / {{8|now|sw_vert_tbps|.1f}}T。每条 lane 在 die 内是 \(b/{{4|now|wire_gbps|g}}\,\mathrm{Gbps}\) 根信号线（16R {{4|now|wires_per_lane|.0f}} 根、64R {{8|now|wires_per_lane|.0f}} 根）。
- **交换容量与键合面积。** 三个交换核合计 \(3B_{die}\)（16R {{4|now|sw_sw_tbps|.1f}}T，64R {{8|now|sw_sw_tbps|.1f}}T），远小于第 5 章方案四大 router 的 \((2n+1)B_{die}\)。混合键合按第 5 章的口径（{{4|stk|hb_pitch_um|g}} µm 间距、{{4|stk|hb_gbps|g}} Gbps/pin、50% 信号），SW die 垂直端口加线路侧合计只需 {{4|now|hb_sw_mm2|.1f}} mm²（16R）/ {{8|now|hb_sw_mm2|.1f}} mm²（64R），垂直带宽不是瓶颈。

## 6.4 NOW die：映射结果的连线与可配置点对点走线

### 6.4.1 逻辑功能：实现映射结果的连线

!fig[fig_now_demand.png](图 6-4 NOW die 的逻辑功能：方案二映射结果在每颗 die 上需要实现的馈通直通、馈通转向与合计连线条数)

每条跨 die 逻辑链路的路径 \(d_0\to d_1\to\cdots\to d_h\) 在各颗 NOW die 上分解为三类连线：

- **注入**（源 die \(d_0\)）：SW die 垂直端口（L1_out 或 L2_out）→ 出向 SIO lane；
- **馈通**（中间 die \(d_1,\dots,d_{h-1}\)）：入向 SIO lane → 出向 SIO lane，分**直通**（入、出面相对）与**转向**（入、出面相邻）；
- **弹出**（宿 die \(d_h\)）：入向 SIO lane → SW die 垂直端口（L2_in 或 L3_in）。

每颗 die 的注入与弹出都恰好是 \(2U\) 条（16R {{4|now|U|d}}×2、64R {{8|now|U|d}}×2），馈通则随位置变化（图 6-4）：

- 16R 方案二：每颗 die 最多 {{4|now|s2/demand/stat/ft/max|d}} 条馈通、合计最多 {{4|now|s2/demand/stat/total/max|d}} 条连线；馈通中转向占 {{4|now|s2/demand/turn_share_ft|.0f%}}；64R 每颗 die 最多 {{8|now|s2/demand/stat/total/max|d}} 条连线，转向占 {{8|now|s2/demand/turn_share_ft|.0f%}}。
- 方案一（XY 为主）转向更少：16R 转向占 {{4|now|s1/demand/turn_share_ft|.0f%}}、64R 占 {{8|now|s1/demand/turn_share_ft|.0f%}}。
- **每颗 die 的连线图样都不同**：两种方案、两种封装下，不同图样数都等于 die 数（16R {{4|now|s1/demand/distinct_patterns|d}}、64R {{8|now|s1/demand/distinct_patterns|d}}）。这就是 NOW die 需要可配置的原因。

### 6.4.2 物理实现：行列总线 + 稀疏可配置 mux

!fig[fig_now_fabric.png](图 6-5 同构 NOW die 的可配置点对点走线：(a) 行 / 列总线与出向 lane mux（示意 C = 4）；(b) 出向 lane mux 的输入)

NOW die 的物理实现对全部 die 相同（图 6-5）：

- **lane 与 SIO 端口。** 每个有向 die 边有 \(K\) 条 lane，每条带宽 \(b\)；lane \(k\) 就是该方向的 SIO 端口 \(k\)，两侧 die 用同一编号，所以相邻 die 之间不需要任何重排。\(K\) 取物理构型的 \(C\)（6.4.3 节讨论 \(K>C\) 的情形）。
- **行 / 列总线。** die 内东西向有 \(2K\) 条行总线：W-in \(k\) 直通到 E-out \(k\)，E-in \(k\) 直通到 W-out \(k\)；南北向同理有 \(2K\) 条列总线。**直通馈通只需沿总线走，不经过任何选择**。
- **出向 lane mux（稀疏转向 + 垂直连接）。** 每个出向 lane（四面共 \(4K\) 个）前有一个静态 mux，输入为：
    - 直通：对面入向 lane \(k\)（1 路）；
    - 转向：两个相邻面的入向 lane \(k-w,\dots,k+w\)（\(2(2w+1)\) 路），\(w\) 为转向窗口；
    - 注入：L1_out 与 L2_out 两个垂直端口池中各 \(s\) 个端口（\(2s\) 路）。
    - 扇入 \(1+2(2w+1)+2s\)。转向发生在行总线与列总线的交叉点附近，不需要额外长线。
- **下行端口 mux（垂直连接）。** 每个 L2_in / L3_in 垂直端口前有一个静态 mux，接 \(\lceil 4K s/P\rceil\) 条入向 lane（\(P\) 为每个端口池的端口数）。上行、下行使用同一张固定的伪随机稀疏连接图样，全部 die 相同。
- **备用端口 \(\Delta\)。** 每个垂直端口池可以比所需的 \(U\) 多做 \(\Delta\) 个端口（\(P=U+\Delta\)），SW die 侧对应的 lane 不用。备用端口给二分匹配留出余量，可以显著减小 \(s\) 与下行 mux 扇入（6.4.4 节）。
- **静态配置。** 每个 mux 一个选择码，上电时由配置链写入，运行中不变。每颗 die 写入不同的配置，就实现了 6.4.1 节各自不同的逻辑连线。

### 6.4.3 lane 分配与转向窗口

每条逻辑链路在每段直线上占用同一条 lane（沿行 / 列总线直通），在转向处 lane 编号最多变化 \(w\)。按 first-fit 对全部链路分配 lane（多种排序取最优），记所需 lane 数为 \(K(w)\)。

- 16R 方案一 / 二与 64R 方案一：\(w=0\) 时即有 \(K(0)=C\)，即**转向只在同编号 lane 之间发生**，每个出向 mux 的转向输入只有 2 路。
- 64R 方案二：\(K(0)\) = {{8|now|s2/K_w0|d}}，比 \(C\) = {{8|now|s2/C|d}} 多 {{8|now|s2/K_w0_extra|.1f%}}；要在 \(K=C\) 内完成分配，需要 \(w\) = {{8|now|s2/w_star|d}}（图 6-7(a)）。两种做法：
    - \(w\) = {{8|now|s2/rec/w|d}}、\(K=C\)：出向 mux 扇入 {{8|now|s2/rec/fan_out|d}}；
    - **\(w=0\)、\(K=K(0)\)**：出向 mux 扇入降到 {{8|now|s2/w0/fan_out|d}}，代价是每边多 {{8|now|s2/K_w0_extra|.1f%}} 的 SIO 端口（{{8|now|s2/w0/edge_tbps|.1f}}T vs {{8|now|s2/C_tbps|.1f}}T）。
    - 本章推荐后者：SIO 端口增加不到 3%，出向 mux 扇入从 {{8|now|s2/rec/fan_out|d}} 降到 {{8|now|s2/w0/fan_out|d}}，lane 级交叉点从 {{8|now|s2/rec/xp_lane|,d}} 降到 {{8|now|s2/w0/xp_lane|,d}}。
- lane 利用率：16R 方案二每颗 die 的出向 lane 最多用到 {{4|now|s2/lane_util_max|.0f%}}、平均 {{4|now|s2/lane_util_mean|.0f%}}；方案一的 \(C\) 由最热边决定，其余边较空，平均只有 {{4|now|s1/lane_util_mean|.0f%}}。

### 6.4.4 垂直端口的稀疏连接

lane 分配确定后，每颗 die 的每个端口池（L1_out、L2_out、L2_in、L3_in）中，需要接入的 lane 数恰为 \(U\)。把 “lane ↔ 端口” 看成二分图（每条 lane 可接的 \(s\) 个端口由固定稀疏图样给出），用增广路匹配求出最小可行的 \(s\)：

- 不加备用端口（\(\Delta=0\)）时，16R 方案二需要 \(s\) = {{4|now|s2/vert/0/s|d}}、下行 mux 扇入 {{4|now|s2/vert/0/fan_down|d}}；64R 方案二需要 \(s\) = {{8|now|s2/vert/0/s|d}}、扇入 {{8|now|s2/vert/0/fan_down|d}}。
- 每池加 \(\Delta=\lceil U/4\rceil\) 个备用端口（16R {{4|now|s2/rec/delta|d}} 个、64R {{8|now|s2/rec/delta|d}} 个）后，全部情形都只需 \(s\) = {{4|now|s2/w0/s|d}}，16R 方案二下行 mux 扇入降到 {{4|now|s2/w0/fan_down|d}}，64R 降到 {{8|now|s2/w0/fan_down|d}}（图 6-7(b)）。
- 备用端口只多占 SW die 上少量键合点（每池 \(\Delta\) 条 lane），因此推荐配置取 \(\Delta=\lceil U/4\rceil\)。

### 6.4.5 静态配置与校验

!fig[fig_now_cfg.png](图 6-6 16R die 5 的 NOW die 静态配置：蓝 = 沿行 / 列总线直通，橙 = 交叉点转向，绿 = 垂直端口注入，紫 = 弹出到垂直端口)

- **配置生成。** 对每颗 die，按 lane 分配与端口匹配结果写出每个出向 lane mux 的选择（直通 / 转向 / 注入哪个端口）与每个下行端口 mux 的选择（接哪个入向 lane）。生成时断言：每个出向 lane 至多被一路驱动，每个入向 lane 至多被一处使用，转向的 lane 差不超过 \(w\)，垂直端口在稀疏图样内。
- **回放校验。** 只用各 die 的 mux 配置，从每个上行垂直端口出发逐 die 追踪 SIO lane，直到到达某个下行端口，核对宿 die、端口池与跳数是否与逻辑链路一致。全部配置（含各种 \(\Delta\) 与 \(w=0\) 备选）都逐条回放通过：16R {{4|now|s2/replay_ok|d}} / {{4|now|s2/n_links|d}} 条，64R {{8|now|s2/replay_ok|d}} / {{8|now|s2/n_links|d}} 条。
- **示例（图 6-6）。** 16R die {{4|now|s2/example/die|d}} 的配置：方案二的直通、转向、注入与弹出分别沿行 / 列总线、在交叉点、从中心垂直端口区出发、回到垂直端口区。方案一 \(C\) 更大，因此 lane 更密，但转向更少。
- **配置量。** 每颗 die 的选择码只有 {{4|now|s2/w0/cfg_kb|.2f}} KB（16R 方案二）/ {{8|now|s2/w0/cfg_kb|.2f}} KB（64R 方案二），可以由扫描链或 SW die 上的管理核在上电时写入。

### 6.4.6 代价

!fig[fig_now_sparse.png](图 6-7 NOW die 稀疏度与代价：(a) lane 数随转向窗口 w 的变化；(b) 备用垂直端口 Δ 对下行 mux 扇入的影响；(c) 稀疏 mux 与全交叉的 lane 级交叉点数)

!tab 表 6-2 NOW die 可配置走线的推荐配置（\(w=0\)，\(K=K(0)\)，\(\Delta=\lceil U/4\rceil\)）与代价

| 量 | 16R 方案一 | 16R 方案二 | 64R 方案一 | 64R 方案二 |
|---|---:|---:|---:|---:|
| 物理构型 \(C\) / 推荐 lane 数 \(K\) | {{4|now|s1/C|d}} / {{4|now|s1/w0/K|d}} | {{4|now|s2/C|d}} / {{4|now|s2/w0/K|d}} | {{8|now|s1/C|d}} / {{8|now|s1/w0/K|d}} | {{8|now|s2/C|d}} / {{8|now|s2/w0/K|d}} |
| 每边 SIO 带宽（单方向） | {{4|now|s1/w0/edge_tbps|.1f}}T | {{4|now|s2/w0/edge_tbps|.1f}}T | {{8|now|s1/w0/edge_tbps|.1f}}T | {{8|now|s2/w0/edge_tbps|.1f}}T |
| 垂直端口池 \(P=U+\Delta\) / 每 lane 可接端口数 \(s\) | {{4|now|s1/w0/P|d}} / {{4|now|s1/w0/s|d}} | {{4|now|s2/w0/P|d}} / {{4|now|s2/w0/s|d}} | {{8|now|s1/w0/P|d}} / {{8|now|s1/w0/s|d}} | {{8|now|s2/w0/P|d}} / {{8|now|s2/w0/s|d}} |
| 出向 lane mux 扇入（全交叉为） | {{4|now|s1/w0/fan_out|d}}（{{4|now|s1/fan_out_full|d}}） | {{4|now|s2/w0/fan_out|d}}（{{4|now|s2/fan_out_full|d}}） | {{8|now|s1/w0/fan_out|d}}（{{8|now|s1/fan_out_full|d}}） | {{8|now|s2/w0/fan_out|d}}（{{8|now|s2/fan_out_full|d}}） |
| 下行端口 mux 扇入 | {{4|now|s1/w0/fan_down|d}} | {{4|now|s2/w0/fan_down|d}} | {{8|now|s1/w0/fan_down|d}} | {{8|now|s2/w0/fan_down|d}} |
| lane 级交叉点（全交叉的几分之一） | {{4|now|s1/w0/xp_lane|,d}}（1/{{4|now|s1/w0/xp_ratio|.0f}}） | {{4|now|s2/w0/xp_lane|,d}}（1/{{4|now|s2/w0/xp_ratio|.0f}}） | {{8|now|s1/w0/xp_lane|,d}}（1/{{8|now|s1/w0/xp_ratio|.0f}}） | {{8|now|s2/w0/xp_lane|,d}}（1/{{8|now|s2/w0/xp_ratio|.0f}}） |
| 每 lane 信号线（\(b\) / {{4|now|wire_gbps|g}} Gbps） | {{4|now|wires_per_lane|.0f}} | {{4|now|wires_per_lane|.0f}} | {{8|now|wires_per_lane|.0f}} | {{8|now|wires_per_lane|.0f}} |
| 行总线信号线（每 mm 宽度） | {{4|now|s1/w0/row_wires_mm|,.0f}} | {{4|now|s2/w0/row_wires_mm|,.0f}} | {{8|now|s1/w0/row_wires_mm|,.0f}} | {{8|now|s2/w0/row_wires_mm|,.0f}} |
| 每颗 die 配置量 | {{4|now|s1/w0/cfg_kb|.2f}} KB | {{4|now|s2/w0/cfg_kb|.2f}} KB | {{8|now|s1/w0/cfg_kb|.2f}} KB | {{8|now|s2/w0/cfg_kb|.2f}} KB |

- **mux 规模。** 与 “任意入向 lane / 垂直端口 ↔ 任意出向 lane / 垂直端口” 的全交叉相比，稀疏 mux 的 lane 级交叉点只有其 1/{{4|now|s2/w0/xp_ratio|.0f}}（16R 方案二）～1/{{8|now|s1/w0/xp_ratio|.0f}}（64R 方案一）。每个 lane 级交叉点要乘以每 lane 的信号线数：16R 的 lane 更宽（{{4|now|wires_per_lane|.0f}} 根 vs {{8|now|wires_per_lane|.0f}} 根），所以按信号线计的 mux 规模 16R 反而大于 64R。
- **总线布线。** 行总线在 25 mm 的 die 高度上每 mm 约 {{4|now|s2/w0/row_wires_mm|,.0f}} 根信号线（16R 方案二），列总线在 32 mm 宽度上每 mm 约 {{4|now|s2/w0/col_wires_mm|,.0f}} 根；按 1 µm 量级的走线间距，各需约一层金属，与第 5 章 router 到四边 SIO 的馈通走线同量级。方案一的 \(C\) 更大，16R 需要约 {{4|now|s1/w0/row_wires_mm|,.0f}} 根/mm，约两层金属。
- **SIO 不变。** NOW die 的每边带宽就是方案一 / 二物理构型的 \(C\cdot b\)（64R 方案二推荐配置多 {{8|now|s2/K_w0_extra|.1f%}}）。与第 5 章按最坏置换 buffered 配置的 {{4|stk|cfg/worst_buf/edge_tbps|.1f}}T（16R）/ {{8|stk|cfg/worst_buf/edge_tbps|.1f}}T（64R）相比，16R 方案二的 {{4|now|s2/C_tbps|.1f}}T 更低，因为 DSL 的边带宽由 CLOS 喷洒直接限定，不需要为 router 饱和效率留余量。
- **不需要的东西。** NOW die 上没有输入缓冲、虚通道、仲裁与流控；死锁与保序问题都在 SW die 的 L1 喷洒 / L3 重排序中处理，与第 2、3 章方案一 / 二相同。

## 6.5 OE die

OE die 与第 5 章完全相同（5.1～5.3 节）：

- 每个 Reticle 一颗，带宽等于 SW die 线路侧带宽 \(B_{die}\)（16R {{4|stk|oe_tbps|g}}T，64R {{8|stk|oe_tbps|g}}T），沿 Reticle 北边放置、紧贴 SW die。
- 按流水线分成 \(N_{pipe}\) 个 3.2T 光引擎切片（16R {{4|stk|oe_slices|d}} 个、64R {{8|stk|oe_slices|d}} 个），每个切片 {{4|stk|slice_lanes|d}} 路 200G、{{4|stk|slice_fibres|d}} 芯光纤；顶部 {{4|stk|n_fau|d}} 个 / {{8|stk|n_fau|d}} 个 FAU 垂直出纤，全芯片 {{4|stk|fibres_total|,d}} 芯。
- SW↔OE 之间是 \(N_{pipe}\) 组固定的 3.2T 点对点通道，经 NOW die 跨约 1 mm 间隙，不经过 6.4 节的可配置走线；OE die 混合键合面积只需 {{4|stk|hb_oe_mm2|.2f}} mm²（16R）。

## 6.6 各 die 的 floorplan

- **NOW die**（参照图 5-7(a) 的布局）：
    - 四边是 SIO PHY 条带，每边每方向 \(K\) 个端口（16R 方案二 {{4|now|s2/w0/K|d}} × {{4|now|b_tbps|g}}T）。
    - 北部正对 OE die 的是 OE 切片键合区，与 SW 线路侧键合区之间是 SW↔OE 点对点通道（同第 5 章）。
    - 南部正对 SW die 交换核的是垂直端口区：L1_out / L2_out / L2_in / L3_in 四个端口池，每池 \(U+\Delta\) 个端口；第 5 章的 router 阵列在这里换成垂直端口 mux。
    - 整片 die 铺满 \(2K\) 条行总线与 \(2K\) 条列总线，出向 lane mux 放在各面 SIO PHY 内侧，转向输入取自附近的列 / 行总线。
- **SW die**：北半部是 \(N_{pipe}\) 个流水线切片，与 OE 切片逐一对齐；南半部是 L1、L2、L3 三个交换核，L1 下方是 L1_out 键合区，L2 下方是 L2_in / L2_out，L3 下方是 L3_in，垂直端口不需要横向长线。
- **OE die**：同图 5-7(b)。

## 6.7 小结

> 【结论】
>
> 1. **三层分工与第 5 章相同，交换位置不同。** 每个 Reticle 由 NOW、SW、OE 各一颗 die 组成，封装、OE die 与 SW↔OE 点对点通道都与第 5 章一致。DSL 的 L1 / L2 / L3 三个 switch 全部在 SW die 内（合计 \(3B_{die}\)），NOW die 上没有 router，只承载映射结果的电气连线。
> 2. **SW die 垂直端口。** 跨 die 逻辑链路经 L1_out / L2_out / L2_in / L3_in 四个端口池落到 NOW die，共 \(4U\) 条 \(b\) lane（16R {{4|now|sw_vert_lanes|d}} 条、{{4|now|sw_vert_tbps|.1f}}T；64R {{8|now|sw_vert_lanes|d}} 条、{{8|now|sw_vert_tbps|.1f}}T），键合面积只有数 mm²。
> 3. **NOW die 逻辑功能。** 每颗 die 实现 \(2U\) 条注入、\(2U\) 条弹出与随位置变化的馈通（直通 / 转向），各 die 的连线图样全部不同，所以用同构可配置结构代替 \(n^2\) 套定制连线。
> 4. **NOW die 物理实现。** 每方向 \(K\) 条 lane（lane \(k\) = SIO 端口 \(k\)）、行 / 列各 \(2K\) 条总线；直通沿总线，转向与注入经出向 lane 的静态 mux（扇入 \(1+2(2w+1)+2s\)），弹出经下行端口 mux。推荐 \(w=0\)、\(\Delta=\lceil U/4\rceil\)、\(s\) = {{4|now|s2/w0/s|d}}：出向 mux 扇入 {{4|now|s2/w0/fan_out|d}}，下行 mux 扇入 {{4|now|s2/w0/fan_down|d}}（16R 方案二）/ {{8|now|s2/w0/fan_down|d}}（64R 方案二），交叉点为全交叉的 1/{{4|now|s2/w0/xp_ratio|.0f}}～1/{{8|now|s1/w0/xp_ratio|.0f}}。64R 方案二在 \(w=0\) 时需多 {{8|now|s2/K_w0_extra|.1f%}} 的 lane，否则需要 \(w\) = {{8|now|s2/w_star|d}} 的宽转向窗口。
> 5. **静态配置可验证。** 每颗 die 只需约 1 KB 的选择码；只用配置回放即可逐条还原全部逻辑链路（16R {{4|now|s2/n_links|,d}} 条、64R {{8|now|s2/n_links|,d}} 条），全部通过。
> 6. **待评估项。** 每 lane 数百根信号线的宽 mux 的面积、时序与功耗，行 / 列总线的金属层与中继规划，配置链的测试与冗余（坏 lane 可借助备用端口与重新分配绕开），需要在物理设计阶段细化。
