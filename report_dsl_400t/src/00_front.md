<div class="cover" markdown="1">
<div class="band">
<h0>400Tbps+<br/>WSE-Switch构型分析报告</h0>
<div class="sub">409.6T（1024 × 400GE）三级共址 CLOS 在 4×4 / 8×8 die 2D Mesh 上的 DSL 构型、L1–L3 直连叠加与 die 级 O1Turn(DR) NoC：带宽、走线、时延与功耗</div>
</div>

<div style="margin-top:22mm; font-size:11pt; line-height:2;">
<span class="tag">WSE-Switch</span><span class="tag">DSL</span><span class="tag">2D Mesh</span><span class="tag">O1Turn</span><span class="tag">DSL XY 路由</span><span class="tag">DSL 最短路径路由</span><span class="tag">DSL+直连</span><span class="tag">die 级 NoC 加速比</span><span class="tag">Feedthrough</span><span class="tag">数据搬移功耗</span>
</div>

<div style="margin-top:14mm; font-size:10.5pt; color:#333; line-height:1.9;">
<b>研究对象：</b>409.6T（1024 × 400GE）交换芯片，16 颗（4×4）或 64 颗（8×8）32 × 25 mm 同构 die 以 2D Mesh 互联，每颗 die 共址 CLOS 的 L1 / L2 / L3 交换与过路 Feedthrough<br/>
<b>核心问题：</b>在仅相邻 die 互联（无跳线）的条件下，DSL XY 路由与 DSL 最短路径路由两种路由口径分别需要多大的 die 间带宽，带来多长的走线、多大的时延与功耗；在方案二上叠加 L1–L3 直连（方案三）能以多少 D2D 带宽与端口增长换取多少时延与功耗收益；不用 CLOS、每颗 die 作为 NoC router 按顺时针 / 逆时针 O1Turn 各 50% 转发（方案四）需要多大的邻 die 加速比<br/>
<b>参考材料：</b>《HyperSwitch 交换架构研究报告》第 8 章 8.1~8.4 节（晶圆 / Panel 级多 die 交换的问题定义与数学抽象）；DSL 映射算法与报告方案；switch_dse/waferscale 中的 2D Mesh 与路由代码
</div>

<div class="meta">
<b>报告性质：</b>芯片架构评估报告（内部）&nbsp;&nbsp;|&nbsp;&nbsp;<b>版本：</b>v1.3&nbsp;&nbsp;|&nbsp;&nbsp;<b>日期：</b>2026 年 11 月<br/>
<span class="small">说明：全部数值由 waferscale/dsl_mesh_400t.py（方案一、二）、waferscale/dsl_l1l3_direct.py（方案三）与 waferscale/dsl_o1turn_noc.py（方案四）计算、report_dsl_400t/tools/build_pdf.py 直接从结果 JSON 填入正文与表格；功耗为架构评估口径，用于方案间相对比较。</span>
</div>
</div>

<div class="toc-page" markdown="1">
<div style="font-size:20pt;color:#1F3B5C;font-weight:700;border-bottom:3px solid #1F3B5C;padding-bottom:6px;margin-bottom:10px;">目 录</div>

[TOC]

</div>

# 执行摘要 {#summary}

本报告评估 409.6T（1024 × 400GE）交换芯片的 **DSL 构型**：交换功能按三级 CLOS 切成同构 die，每颗 die 共址 L1 / L2 / L3 三级交换并为过路流量提供 Feedthrough，die 之间只有相邻 2D Mesh 链路（第 8 章中的 DSL 方案）。封装取 **4×4（16 颗 die，CLOS(16,16,16)）** 与 **8×8（64 颗 die，CLOS(64,64,64)）** 两种 2D Mesh，评估四种方案：前三种保留三级 CLOS，第四种不用 CLOS。

- **方案一 DSL XY 路由**：每条逻辑链路只转一次弯，在 XY 与 YX 两条候选中取转弯方向为顺时针的一条，路由由两端位置唯一确定；
- **方案二 DSL 最短路径路由**：每条逻辑链路可走任意一条 Manhattan 最短路径，以最热 die 间边负载最小为目标优化；
- **方案三 DSL+直连**：在方案二的映射结果上 **叠加** L1→L3 直连逻辑边（L1 增加输出端口、L3 增加输入端口），直连经方案二中空闲的 D2D 带宽 Feedthrough；CLOS 链路及其路径全部保留，叠加后 die 间有向负载只增不减、仍满足无阻塞交换能力；允许最热边 D2D 带宽增长 x = 0 / 5% / 10%。
- **方案四 O1Turn(DR)（die 级 NoC）**：不用 CLOS，每颗 die 是一个 5 组端口（1 组线路侧 + 上下左右 4 组交换侧）的同构 NoC router，src die → dst die 的流量按顺时针与逆时针两条 O1Turn 路径各 50% 负载均衡、逐 die 转发；交换侧按任意流量矩阵下的最坏负载配置，单边为 \(n/2\) 倍单 die 带宽，恰为二分下界（邻 die 加速比 \(n/2\)、总加速比 \(2n\)，1.6.3 节）。

第 2、3 章分别给出 16R（4×4）与 64R（8×8）下四种方案的结果，第 4 章从 die 间加速比、走线长度、走线与数据搬移的时延 / 功耗占比四个角度对比两种封装。第 5 章把方案四细化为可实现的 3D 堆叠变种：每个 Reticle 拆成底层 NOW die（多平面 NoC router + SW↔OE 点对点互联）与顶层 SW die（多流水线交换）、一颗带宽等于 SW 线路侧带宽的 OE die（FAU 向上出纤），并推导 NoC 平面数 \(M\) 与流水线数 \(N\) 的倍数关系。第 6 章用同样的堆叠方式细化方案一 / 二（DSL）：L1 / L2 / L3 全部在 SW die 内，NOW die 用同构的行列总线 + 稀疏静态 mux 实现映射结果的连线，OE die 与第 5 章相同。

!tab 表 0-1 两种封装下各方案的关键指标（满载 AllToAll，另列置换满载最坏；功耗为两种走线能耗 0.1 / 0.06 pJ/bit/mm；方案三 DSL+直连 x=5% 见第 2、3 章）

<!-- TAB:cross:0 -->

主要结论：

1. **die 间带宽：方案二与方案四（按任意流量无阻塞配置）都达到二分下界，方案一高出 75%（4×4）/ 88%（8×8）。** 4×4 的二分下界为 {{4|manhattan|lb_tbps|.1f}} Tbps（每条共享边每方向），方案二恰好达到；方案一因 “只转一次弯且方向固定”，外圈四边中段的边同时承接 “本行出发” 与 “到达本行” 两类流的直线段，形成顺时针热环，最热边 {{4|xy_o1turn_cw|C_tbps|.1f}} Tbps（{{4|xy_o1turn_cw|C_ratio_lb|.2f}}× 下界）。8×8 下界 {{8|manhattan|lb_tbps|.1f}} Tbps，方案一为 {{8|xy_o1turn_cw|C_tbps|.1f}} Tbps（{{8|xy_o1turn_cw|C_ratio_lb|.3f}}×）。一般地，方案一的最热边是下界的 \(2-1/n\) 倍。
2. **时延：最坏路径以数据搬移为主，馈通占比随规模上升。** 时延模型为 SIO 11.5 ns/跳、馈通与缝隙走线 0.5 ns/mm、NOW die 内横纵转向 2 ns/次，$t_{sw\_die}=120$ ns 端到端计一次，$t_{sw\_sw}$ 在方案一~三经 L2 中转时计一次 70 ns、在 L1→L3 直连与 O1Turn(DR) 取 0。CLOS 端到端的固定项 \(t_{sw\_die}+t_{sw\_sw}=190\) ns 占方案一最坏路径的 {{4|xy_o1turn_cw|e2e_worst/sw_die_share|.0f%}} + {{4|xy_o1turn_cw|e2e_worst/sw_sw_share|.0f%}}（4×4）、{{8|xy_o1turn_cw|e2e_worst/sw_die_share|.0f%}} + {{8|xy_o1turn_cw|e2e_worst/sw_sw_share|.0f%}}（8×8）；最坏路径上馈通走线占 {{4|xy_o1turn_cw|e2e_worst/ft_share|.0f%}}~{{4|manhattan|e2e_worst/ft_share|.0f%}}（4×4）与 {{8|xy_o1turn_cw|e2e_worst/ft_share|.0f%}}~{{8|manhattan|e2e_worst/ft_share|.0f%}}（8×8）。方案二为摊开负载使用多转弯路径，最坏馈通更长，最大时延比方案一高 {{4|manhattan|lat_vs_xy|.2f}}×（4×4）/ {{8|manhattan|lat_vs_xy|.2f}}×（8×8）；两者的平均时延相同。

3. **功耗：最热边决定 SIO 静态功耗，方案一因此高于方案二；走线能耗口径的影响最大。** SIO 静态按最终物理构型计：同构 die 的每条有向边都按最热边 \(C\) 配置 SIO，所以方案一的 SIO 静态为 {{4|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} W（4×4）/ {{8|xy_o1turn_cw|power/0.1/sio_static_W|,.0f}} W（8×8），方案二只有 {{4|manhattan|power/0.1/sio_static_W|,.0f}} / {{8|manhattan|power/0.1/sio_static_W|,.0f}} W。两种方案都只走最短路径，SIO 动态与馈通走线功耗几乎相同，满载芯片总功耗方案一比方案二高 {{4|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}} / {{8|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}}。把走线能耗从 0.1 降到 0.06 pJ/bit/mm，4×4 芯片总功耗从约 {{4|manhattan|power/0.1/total_W|,.0f}} W 降到 {{4|manhattan|power/0.06/total_W|,.0f}} W；8×8 从 {{8|manhattan|power/0.1/total_W|,.0f}} W 降到 {{8|manhattan|power/0.06/total_W|,.0f}} W。8×8 的数据搬移功耗为 4×4 的 {{8|manhattan|vs16/move|.2f}} 倍（馈通走线 {{8|manhattan|vs16/d2d_wire|.2f}} 倍），高于跳数比 {{8|manhattan|vs16/hops_link|.2f}}——因 \(\mathrm{wire}_{ft}\) 只计过路 die（1.5.1 节）。
4. **方案三：用空闲 D2D 带宽和 L1 / L3 端口换时延与功耗。** 方案二达到二分下界后，中间割满载，但远离中间割的边仍有大量空闲带宽（4×4 最轻的边只有 {{4|manhattan|edge_min_tbps|.1f}} Tbps）。**x = 0 时不增加任何边的 D2D 带宽**，即可叠加 {{4|s3_0|n_directs|d}} 条（4×4）/ {{8|s3_0|n_directs|,d}} 条（8×8）die 间直连与每 die 一条片内直连：L1→L3 最大时延降到 {{4|s3_0|e2e_lat_max|,.0f}} ns（{{4|s3_0|lat_vs_s2|+.0f%}}）/ {{8|s3_0|e2e_lat_max|,.0f}} ns（{{8|s3_0|lat_vs_s2|+.0f%}}），满载芯片总功耗降到 {{4|s3_0|power/0.1/total_W|,.0f}} W（{{4|s3_0|power/0.1/total_vs_s2|+.1f%}}）/ {{8|s3_0|power/0.1/total_W|,.0f}} W（{{8|s3_0|power/0.1/total_vs_s2|+.1f%}}）。由于中间割已满，x = 0 的直连全部落在同一象限内；放开到 x = 10%（最热边 {{4|s3_10|C_tbps|.1f}} / {{8|s3_10|C_tbps|.1f}} Tbps，{{4|s3_10|d2d_growth|+.1f%}} / {{8|s3_10|d2d_growth|+.1f%}}）后直连才能跨割，最大时延降 {{4|s3_10|lat_drop|.0f%}} / {{8|s3_10|lat_drop|.0f%}}、平均时延降 {{4|s3_10|lat_mean_drop|.0f%}} / {{8|s3_10|lat_mean_drop|.0f%}}，总功耗降 {{4|s3_10|power/0.1/total_drop|.1f%}} / {{8|s3_10|power/0.1/total_drop|.1f%}}。代价是单个 L1 switch 的输出端口（及 L3 的输入端口）最多增加 {{4|s3_0|l1_sw_ports_growth|.0f%}}~{{4|s3_10|l1_sw_ports_growth|.0f%}}（4×4）/ {{8|s3_0|l1_sw_ports_growth|.0f%}}~{{8|s3_10|l1_sw_ports_growth|.0f%}}（8×8，按 400G 等效；若每条 100G 直连独占一个 400G 端口则为 {{8|s3_0|l1_sw_ports_growth_ceil|.0f%}}~{{8|s3_10|l1_sw_ports_growth_ceil|.0f%}}）。**这些收益只对 AllToAll 类均匀流量成立**：置换流量下每个 die 对的流量远大于直连带宽 b，溢出部分仍走 CLOS，最坏时延回到方案二，功耗与方案二基本持平（8×8、x=10% 时降幅为 {{8|s3_10|power/0.1/scenarios/perm_100/drop_vs_s2|.1f%}}，即略高于方案二：x > 0 时最热边上升，全阵列 SIO 静态同比例增加）。
5. **方案四 O1Turn(DR)：用大容量 router 换单段最短路径，D2D 带宽与方案二相同。** 每个 die 对的流量在顺时针、逆时针两条单转弯路径（XY 与 YX）上各发 50%。经过某条向右边的路径要么水平段在源行（源 die 至多 \(c+1\) 颗），要么在宿行（宿 die 至多 \(n-1-c\) 颗），每颗源 / 宿 die 只有一半流量走这一行，所以 **任意流量矩阵下单边负载不超过 \(n/2\) 倍单 die 带宽，恰为二分下界，且每条有向边都能被外圈对角互打等置换达到**（图 1-3）：单边 {{4|o1t|C_tbps|.1f}} Tbps（4×4）/ {{8|o1t|C_tbps|.1f}} Tbps（8×8），与方案二相同、比方案一低 {{4|o1t|C_save_vs_xy|.0f%}} / {{8|o1t|C_save_vs_xy|.0f%}}；只走顺时针单路径时需要 \(n\) 倍（二分下界的 2 倍）。单边加速比 \(n/2\)、4 边总加速比 \(2n\)，router 交换容量（含线路侧）\((2n+1)B_{die}\) = {{4|o1t|router_tbps|.1f}} / {{8|o1t|router_tbps|.1f}} Tbps。换来的是端到端只走一段最短路径：最大时延 {{4|o1t|e2e_lat_max|,.0f}} / {{8|o1t|e2e_lat_max|,.0f}} ns（{{4|o1t|lat_vs_s2|+.0f%}} / {{8|o1t|lat_vs_s2|+.0f%}}），满载芯片总功耗 {{4|o1t|power/0.1/total_W|,.0f}} / {{8|o1t|power/0.1/total_W|,.0f}} W（{{4|o1t|power/0.1/total_vs_s2|+.1f%}} / {{8|o1t|power/0.1/total_vs_s2|+.1f%}}），最坏置换下 {{4|o1t|power/0.1/total_worst_W|,.0f}} / {{8|o1t|power/0.1/total_worst_W|,.0f}} W，仍低于方案一、二。最大时延是四种方案中最低的，原因是端到端只走一段最短路径、只转一次向、不经 L2（\(t_{sw\_sw}=0\)），固定项只有一次 $t_{sw\_die}$；这一结论依赖 router 转发时延取 0 的假设：最坏路径经过 {{4|o1t|router_traversals_max|d}} / {{8|o1t|router_traversals_max|d}} 颗 router，每颗 router 的仲裁 / 缓冲时延超过 {{4|o1t|tr_breakeven_vs_xy|.0f}} / {{8|o1t|tr_breakeven_vs_xy|.0f}} ns 时，方案四的最大时延将不再低于方案一。
6. **16R 与 64R（第 4 章）：把 die 切小，代价集中在 die 间搬运。** 单 die 带宽降为 1/4、最热边带宽只减半，单边加速比随 \(n\) 线性增长、64R 是 16R 的 2 倍（方案二、方案四 \(n/2\)：{{4|manhattan|sp_edge|.0f}}× → {{8|manhattan|sp_edge|.0f}}×；方案一 \(n-1/2\)）。\(n/2\) 是二分割下界，任何路由都不可能更低；小于 2 的是不含馈通的注入加速比 \(2(N-1)/N\)（{{4|manhattan|sp_inj|.3f}}× / {{8|manhattan|sp_inj|.3f}}×），die 边还要承载馈通流量，所以单边加速比高于注入加速比。已用 D2D 带宽中馈通占比从 {{4|manhattan|ft_bw_share|.1f%}} 升到 {{8|manhattan|ft_bw_share|.1f%}}。端到端平均走线增长 {{8|s3_10|vs16/wire|.2f}}~{{8|s3_0|vs16/wire|.2f}} 倍；时延含 SIO、馈通走线、转向与固定的 $t_{sw\_die}$ / $t_{sw\_sw}$，固定项不随规模变化，64R 的最大时延为 16R 的 {{8|s3_10|vs16/lat_max|.2f}}~{{8|s3_0|vs16/lat_max|.2f}} 倍。功耗上 SerDes 不变，馈通走线占芯片总功耗从 {{4|manhattan|power/0.1/wire_share_total|.0f%}} 升到 {{8|manhattan|power/0.1/wire_share_total|.0f%}}、数据搬移从 {{4|manhattan|power/0.1/move_share_total|.0f%}} 升到 {{8|manhattan|power/0.1/move_share_total|.0f%}}（方案二），每 bit 搬移能耗从 {{4|manhattan|power/0.1/move_pj|.1f}} 增到 {{8|manhattan|power/0.1/move_pj|.1f}} pJ/bit。
7. **取舍。** 方案一、二的取舍在 **die 间带宽 / 功耗** 与 **最大时延 / 实现复杂度** 之间：方案二达到下界带宽（die 边 I/O 少 43%~47%，SIO 静态功耗同比例更低，满载总功耗低 {{4|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}}~{{8|xy_o1turn_cw|power/0.1/total_vs_s2|.1f%}}），最大时延只是方案一的 {{4|manhattan|lat_vs_xy|.2f}}~{{8|manhattan|lat_vs_xy|.2f}} 倍，但需要按逻辑链路下发源路由；方案一路由由位置唯一确定、实现最简单，但需要 1.75~1.875 倍的 die 边带宽和相应的 SIO 静态功耗。die 边 I/O 是主要约束时选方案二，实现简单性优先时选方案一。**方案三 DSL+直连 x = 0 是方案二的 “免费” 增强**：D2D 带宽不变，以 {{4|s3_0|l1_sw_ports_growth|.0f%}} 的 L1 / L3 端口增长（400G 等效）同时拿到低于方案一的最大时延和 {{4|s3_0|power/0.1/total_drop|.0f%}}~{{8|s3_0|power/0.1/total_drop|.0f%}} 的总功耗下降（0.1 pJ/bit/mm）；L1 / L3 端口余量更大时可放开到 x = 5%~10%，进一步降低时延与功耗。**方案四** 在时延、功耗上全面领先且不依赖流量均匀性，顺 / 逆时针各 50% 分流后 die 边带宽也与方案二相同（二分下界）；代价是 router 容量为单 die 带宽的 \(2n+1\) 倍（9 / 17 倍，CLOS 方案单 die 的 L1 + L2 + L3 合计 3 倍），且两类维序路径需按虚网络隔离防死锁，适合 router 容量有余量的实现。封装上，8×8 阵列 263 × 207 mm 已超出 300 mm 晶圆可用范围，需要 Panel 级承载。
8. **方案四的 3D 堆叠变种（第 5 章）。** 大 router 拆成 NOW die 上 \(M\) 个互不通信、每口 3.2T 的 NoC 平面，交换引擎把 \(N\) 条流水线（16R {{4|stk|N_pipe|d}} 条、64R {{8|stk|N_pipe|d}} 条）的流量均匀喷洒到各平面，单平面注入率 \(\lambda=N/M\)。流水线同构要求 \(M=kN\)，注入率约束给出 \(k=\lceil\max(1,\gamma)/\eta\rceil\)。按无阻塞设计：
    - buffered（\(\eta\) = 0.8）取 \(M\) = {{4|stk|cfg/worst_buf/M|d}} / {{8|stk|cfg/worst_buf/M|d}}，die 边带宽比方案四 {{4|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}} / {{8|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}}，每颗 NOW die 约 {{4|stk|cfg/worst_buf/buf_now_mb|.1f}} MB 输入缓冲；
    - bufferless（\(\eta\) = 0.5）取 \(M\) = {{4|stk|cfg/worst_bl/M|d}} / {{8|stk|cfg/worst_bl/M|d}}，die 边带宽翻倍。

    因此 16R 推荐 buffered；\(\eta\) 需由 cycle 级仿真校准。
9. **DSL 的 3D 堆叠细分方案（第 6 章）。** SW die 内实现 L1 / L2 / L3，跨 die 链路经 \(4U\) 条垂直 lane 落到 NOW die（16R {{4|now|sw_vert_tbps|.1f}}T）。各 die 的连线图样全部不同，NOW die 因此做成同构可配置：每方向 \(K\) 条 lane、行 / 列各 \(2K\) 条总线，直通沿总线，转向与垂直连接经稀疏静态 mux（推荐 \(w=0\)、\(s\) = {{4|now|s2/w0/s|d}}，出向 mux 扇入 {{4|now|s2/w0/fan_out|d}}，交叉点为全交叉的 1/{{4|now|s2/w0/xp_ratio|.0f}}～1/{{8|now|s1/w0/xp_ratio|.0f}}），每颗 die 约 1 KB 配置；全部逻辑链路经配置回放校验通过。64R 方案二在 \(w=0\) 时需多 {{8|now|s2/K_w0_extra|.1f%}} 的 SIO lane。
