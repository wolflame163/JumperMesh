# 第 4 章 16R 与 64R 对比 {#ch4}

第 2、3 章分别评估了 16R（4×4，16 颗 die，每颗 \(B_{die}\) = 25.6T）与 64R（8×8，64 颗 die，每颗 \(B_{die}\) = 6.4T）两种封装。两者的系统容量相同（409.6T），差别只在 **把同样的交换容量切成多少颗 die**。本章把两种封装放在一起，从 die 间加速比、走线长度、走线的时延 / 功耗占比、数据搬移的时延 / 功耗占比四个角度对比，评估把 die 切小（16R → 64R）的代价。对比覆盖方案一、方案二、方案三（x = 0、x = 10%）与方案四；图 4-1 汇总了四个角度的结果。

!fig[fig_scale.png](图 4-1 16R（4×4）与 64R（8×8）对比：(a) die 间单边加速比；(b) 端到端平均 / 最大走线；(c) 最坏路径时延构成；(d) 满载芯片功耗构成（0.1 pJ/bit/mm）)

## 4.1 die 间加速比

单边加速比定义为最热有向 die 间边的带宽与单 die 线路带宽 \(B_{die}\) 之比，表示每条 die 边需要的 D2D 带宽是该 die 自身端口带宽的多少倍（方案四按无阻塞所需，见 1.6.3 节）。结果见表 4-1 与图 4-1(a)。

!tab 表 4-1 16R 与 64R 的 die 间加速比

<!-- TAB:sc_speed:0 -->

- **加速比随 \(n\) 线性增长，64R 是 16R 的 2 倍。** 记 \(n\times n\) 阵列、每个 die 对的流量 \(b\)，则 \(B_{die}=n^2 b\)。CLOS 方案的二分下界为 \(n^3 b/2\)，所以 **方案二（达到下界）的单边加速比为 \(n/2\)**：16R 为 {{4|manhattan|sp_edge|.0f}}×，64R 为 {{8|manhattan|sp_edge|.0f}}×。方案一的最热边是下界的 \(2-1/n\) 倍，加速比为 \(n-1/2\)：{{4|xy_o1turn_cw|sp_edge|.1f}}× → {{8|xy_o1turn_cw|sp_edge|.1f}}×。方案四顺 / 逆时针各 50% 分流，任意流量矩阵下的单边加速比也为 \(n/2\)（与方案二相同）：{{4|o1t|sp_edge|.0f}}× → {{8|o1t|sp_edge|.0f}}×；只走顺时针单路径时为 \(n\)。方案三以方案二为基础，x = 10% 时为 {{4|s3_10|sp_edge|.2f}}× → {{8|s3_10|sp_edge|.2f}}×。
- **注入加速比小于 2，单边加速比不小于 \(n/2\)。** 每颗 die 自身发往其他 die 的流量（不含馈通）为 L1 上行与 L2 下行各 \((N-1)/N\cdot B_{die}\)，合计 **注入加速比 \(2(N-1)/N<2\)**：16R 为 {{4|manhattan|sp_inj|.3f}}×，64R 为 {{8|manhattan|sp_inj|.3f}}×。但 2D Mesh 中非相邻 die 的流量必须由中间 die 转发，一条 die 边承载的是所有经过它的流量（含馈通），所以单边加速比受二分割约束而非注入量约束：中间割两侧各 \(N/2\) 颗 die，跨割的 L1→L2 与 L2→L3 逻辑链路共 \(2\cdot(N/2)^2\) 条、合计 \(N b\cdot N/2 = 204.8\) Tbps（与 \(n\) 无关），只能由割上的 \(n\) 条有向边承载（左右对半切：每行恰一条水平边跨割，共 \(n\) 条；**不是** \(n/2\) 条——\(n/2\) 是加速比下界，不是边数；16R 为 4 条、64R 为 8 条），**任何路由下单边带宽都不低于 \(204.8\mathrm T/n\)，即单边加速比 \(\ge n/2\)**。16R：\(204.8/4=51.2\) T \(=2.0\times B_{die}\)，方案二恰好达到；64R：\(204.8/8=25.6\) T \(=4.0\times B_{die}\)，方案二为 {{8|manhattan|sp_edge|.2f}}×。单边加速比低于 2 只在 \(n\le 3\) 时可能。按存储的逐条路径独立重算边负载，结果与上述值一致。
- **原因：切小 die 后，单 die 带宽按 \(1/n^2\) 下降，最热边带宽只按 \(1/n\) 下降。** 64R 的最热边绝对带宽减半（方案二 {{4|manhattan|C_tbps|.1f}} → {{8|manhattan|C_tbps|.1f}} Tbps），但单 die 带宽降为 1/4，所以每颗 die 的 D2D 接口相对其自身端口带宽翻倍：方案二 64R 中每颗内部 die 的 4 条边合计需要 4 × {{8|manhattan|sp_edge|.0f}} = 16 倍 \(B_{die}\) 的 D2D 收发带宽，16R 为 8 倍。
- **方案四在 AllToAll 下的实际负载是无阻塞所需的一半。** AllToAll 满载的最热边只有 {{4|o1t|sp_edge_a2a|.2f}}×（16R）/ {{8|o1t|sp_edge_a2a|.2f}}×（64R），而方案二在 AllToAll 下即达到 \(n/2\)：CLOS 两级喷洒使任何流量都化为 AllToAll，方案四则只有在远距置换下才用满 \(n/2\)。
- **单 die 交换容量。** CLOS 方案每颗 die 的 L1 + L2 + L3 始终是 3 倍 \(B_{die}\)，与 \(n\) 无关（方案三 DSL+直连 x = 10% 因直连端口从 {{4|s3_10|die_switch_x|.3g}}× 增到 {{8|s3_10|die_switch_x|.3g}}×）；方案四的 router 为 \((2n+1)B_{die}\)，从 {{4|o1t|die_switch_x|.0f}}× 增到 {{8|o1t|die_switch_x|.0f}}×。
- **馈通占用。** 已用 D2D 带宽中由过路 die 转发的比例从 {{4|manhattan|ft_bw_share|.1f%}} 升到 {{8|manhattan|ft_bw_share|.1f%}}（方案一、二、四相同）：64R 中每条逻辑链路平均经过的 die 更多，八成以上的 D2D 带宽用于为别的 die 转发。

## 4.2 走线长度

!tab 表 4-2 16R 与 64R 的走线长度

<!-- TAB:sc_wire:0 -->

- **阵列尺寸。** die 尺寸相同，阵列边长随 \(n\) 线性增长：16R 为 {{4|manhattan|arr_w|.0f}} × {{4|manhattan|arr_h|.0f}} mm，64R 为 {{8|manhattan|arr_w|.0f}} × {{8|manhattan|arr_h|.0f}} mm。
- **平均跳数翻倍，馈通走线增长更快。** 单条链路的平均跳数为 \(2n/3\)（任意两颗不同 die 间的平均 Manhattan 距离），从 {{4|manhattan|hops_mean|.2f}} 增到 {{8|manhattan|hops_mean|.2f}}（{{8|manhattan|vs16/hops_link|.2f}}×）。按 1.5.1 节，\(\mathrm{wire}_{ft}\) **只计过路 die**（约 \(h-1\) 段，不含源/宿、不含缝隙），平均过路段数随 \(h\) 从约 1.67 增到约 4.33，故单链路平均馈通增长 {{8|manhattan|vs16/wire_link|.2f}} 倍（{{4|manhattan|wire_mean|.0f}} → {{8|manhattan|wire_mean|.0f}} mm），高于跳数比。端到端平均馈通增长 {{8|xy_o1turn_cw|vs16/wire|.2f}} 倍（方案一、二、四相同），方案三 DSL+直连 x = 0 为 {{8|s3_0|vs16/wire|.2f}} 倍、x = 10% 为 {{8|s3_10|vs16/wire|.2f}} 倍。
- **最大走线翻倍。** 端到端最大走线方案二从 {{4|manhattan|e2e_wire_max|.0f}} mm 增到 {{8|manhattan|e2e_wire_max|.0f}} mm，方案四从 {{4|o1t|e2e_wire_max|.0f}} mm 增到 {{8|o1t|e2e_wire_max|.0f}} mm。四种方案之间的相对关系在两种封装下相同：方案四的端到端走线约为 CLOS 方案的一半，方案三 DSL+直连 x = 10% 比方案二短约 28%~29%。

## 4.3 走线的时延与功耗占比

时延分解为 SIO 接口（每跳 11.5 ns）、馈通走线（含缝隙，0.5 ns/mm）、横纵转向（2 ns/次）、$t_{sw\_die}$（120 ns，端到端一次）与 $t_{sw\_sw}$（方案一~三经 L2 计一次 70 ns，直连与 O1Turn(DR) 为 0）五部分；功耗分解为 SerDes、SIO 与馈通走线三部分（不计线路侧、不计缝隙功耗）。结果见表 4-3、表 4-4 与图 4-1(c)(d)。

!tab 表 4-3 16R 与 64R 的端到端时延构成

<!-- TAB:sc_lat:0 -->

!tab 表 4-4 16R 与 64R 的满载功耗构成（0.1 pJ/bit/mm）

<!-- TAB:sc_power:0 -->

- **馈通走线时延占比随规模变化。** 最坏路径上馈通走线占时延的 {{4|o1t|lw/wire_share|.1f%}}~{{4|manhattan|lw/wire_share|.1f%}}（16R）与 {{8|o1t|lw/wire_share|.1f%}}~{{8|manhattan|lw/wire_share|.1f%}}（64R），平均路径（方案二）为 {{4|manhattan|lm/wire_share|.1f%}} 与 {{8|manhattan|lm/wire_share|.1f%}}。$t_{sw\_die}$ / $t_{sw\_sw}$ 为与规模无关的固定项（CLOS 端到端 190 ns，O1Turn(DR) 120 ns）；每多一跳增加约一个 die 跨度的馈通（12.5~16 ns）与 11.5 ns SIO，每多一次转向再加 2 ns。
- **走线时延中 Feedthrough 的比重上升。** 最坏路径中 Feedthrough 时延占比从 {{4|o1t|lw/ft_share|.0f%}}~{{4|manhattan|lw/ft_share|.0f%}} 升到 {{8|o1t|lw/ft_share|.0f%}}~{{8|manhattan|lw/ft_share|.0f%}}（图 4-1(c) 中深蓝段）：64R 的走线时延主要花在为过路流量穿越中间 die 上。
- **馈通走线功耗占比上升。** 方案二的馈通走线占芯片总功耗的 {{4|manhattan|power/0.1/wire_share_total|.1f%}} → {{8|manhattan|power/0.1/wire_share_total|.1f%}}（方案一 SIO 静态更高、分母更大，为 {{4|xy_o1turn_cw|power/0.1/wire_share_total|.1f%}} → {{8|xy_o1turn_cw|power/0.1/wire_share_total|.1f%}}），方案三 DSL+直连 x = 10% 为 {{4|s3_10|power/0.1/wire_share_total|.1f%}} → {{8|s3_10|power/0.1/wire_share_total|.1f%}}，方案四为 {{4|o1t|power/0.1/wire_share_total|.1f%}} → {{8|o1t|power/0.1/wire_share_total|.1f%}}。馈通功耗随规模增长 {{8|manhattan|vs16/d2d_wire|.2f}} 倍（{{4|manhattan|power/0.1/wire_W|,.0f}} → {{8|manhattan|power/0.1/wire_W|,.0f}} W），与端到端平均馈通距离的增长一致。

## 4.4 数据搬移的时延与功耗占比

数据搬移指 SIO 与馈通走线（不含线路侧、不含源/宿、不含缝隙功耗）；芯片总功耗中其余部分为 SerDes。

- **时延以数据搬移为主，且随规模加重。** 数据搬移（SIO + 馈通走线 + 转向）占最坏路径时延的 {{4|o1t|lw/move_share|.1f%}}~{{4|manhattan|lw/move_share|.1f%}}（16R）与 {{8|s3_10|lw/move_share|.1f%}}~{{8|manhattan|lw/move_share|.1f%}}（64R），其余为固定的 $t_{sw\_die}$ 与 $t_{sw\_sw}$：固定项占比从 16R 的 {{4|manhattan|lw/fixed_share|.0f%}}~{{4|o1t|lw/fixed_share|.0f%}} 降到 64R 的 {{8|manhattan|lw/fixed_share|.0f%}}~{{8|s3_10|lw/fixed_share|.0f%}}。**端到端时延随路径规模增长**：64R 最大时延是 16R 的 {{8|s3_10|vs16/lat_max|.2f}}~{{8|s3_0|vs16/lat_max|.2f}} 倍，平均时延是 {{8|o1t|vs16/lat_mean|.2f}}~{{8|manhattan|vs16/lat_mean|.2f}} 倍；方案四的固定项最小（只有一次 \(t_{sw\_die}\)，不经 L2），最大时延在两种封装下都最低。
- **数据搬移功耗占比上升。** 方案二的数据搬移功耗占芯片总功耗的 {{4|manhattan|power/0.1/move_share_total|.1f%}} → {{8|manhattan|power/0.1/move_share_total|.1f%}}（方案一 {{4|xy_o1turn_cw|power/0.1/move_share_total|.1f%}} → {{8|xy_o1turn_cw|power/0.1/move_share_total|.1f%}}），方案三 DSL+直连 x = 10% 为 {{4|s3_10|power/0.1/move_share_total|.1f%}} → {{8|s3_10|power/0.1/move_share_total|.1f%}}，方案四为 {{4|o1t|power/0.1/move_share_total|.1f%}} → {{8|o1t|power/0.1/move_share_total|.1f%}}。SerDes（{{4|manhattan|power/0.1/serdes_W|,.0f}} W）不随 die 数变化，SIO 功耗增长 {{8|manhattan|vs16/sio|.2f}} 倍（静态按物理构型：有向边 {{4|manhattan|power/0.1/n_dir_edges|d}} → {{8|manhattan|power/0.1/n_dir_edges|d}} 条、最热边 {{4|manhattan|C_tbps|.1f}} → {{8|manhattan|C_tbps|.1f}}T，SIO 静态 {{4|manhattan|power/0.1/sio_static_W|,.0f}} → {{8|manhattan|power/0.1/sio_static_W|,.0f}} W；动态随跳数增长 {{4|manhattan|power/0.1/sio_dyn_W|,.0f}} → {{8|manhattan|power/0.1/sio_dyn_W|,.0f}} W），馈通走线增长 {{8|manhattan|vs16/d2d_wire|.2f}} 倍。
- **每 bit 搬移能耗增长 {{8|o1t|vs16/pj|.2f}}~{{8|s3_0|vs16/pj|.2f}} 倍。** 按 409.6 Tbps 满载折算，方案二的数据搬移能耗从 {{4|manhattan|power/0.1/move_pj|.1f}} pJ/bit 增到 {{8|manhattan|power/0.1/move_pj|.1f}} pJ/bit（{{8|manhattan|vs16/pj|.2f}} 倍），芯片总功耗增长 {{8|manhattan|vs16/total|.2f}} 倍；方案三 DSL+直连 x = 10% 为 {{4|s3_10|power/0.1/move_pj|.1f}} → {{8|s3_10|power/0.1/move_pj|.1f}} pJ/bit；方案四为 {{4|o1t|power/0.1/move_pj|.1f}} → {{8|o1t|power/0.1/move_pj|.1f}} pJ/bit（{{8|o1t|vs16/pj|.2f}} 倍），总功耗只增长 {{8|o1t|vs16/total|.2f}} 倍。

## 4.5 小结

> 【结论】同为 409.6T，从 16R（4×4）切到 64R（8×8）：
>
> 1. **die 间加速比翻倍。** 单 die 带宽降为 1/4，最热边带宽只减半，单边加速比随 \(n\) 线性增长：方案二与方案四 \(n/2\)（{{4|manhattan|sp_edge|.0f}}× → {{8|manhattan|sp_edge|.0f}}×，二分下界），方案一 \(n-1/2\)（{{4|xy_o1turn_cw|sp_edge|.1f}}× → {{8|xy_o1turn_cw|sp_edge|.1f}}×）。64R 的最热边绝对带宽更低，但每颗 die 的 D2D 接口相对其端口带宽更重，且八成以上的 D2D 带宽用于馈通。
> 2. **馈通走线随过路段数超线性增长。** 端到端平均馈通增长 {{8|s3_10|vs16/wire|.2f}}~{{8|s3_0|vs16/wire|.2f}} 倍（单链路平均 {{8|manhattan|vs16/wire_link|.2f}} 倍），高于跳数的 {{8|manhattan|vs16/hops_link|.2f}} 倍——因为 \(\mathrm{wire}_{ft}\) 只计过路 die；四种方案的相对关系不变。
> 3. **馈通走线的时延与功耗占比都随规模上升。** 最坏路径上馈通（含缝隙）占时延的 {{4|o1t|lw/wire_share|.0f%}}~{{4|manhattan|lw/wire_share|.0f%}}（16R）→ {{8|o1t|lw/wire_share|.0f%}}~{{8|manhattan|lw/wire_share|.0f%}}（64R）；馈通功耗占芯片总功耗随 16R→64R 明显上升（方案一、二）。
> 4. **数据搬移是规模代价的主体。** 固定时延（\(t_{sw\_die}+t_{sw\_sw}\)）不随规模变化，数据搬移（SIO + 馈通 + 转向）占最坏路径时延从 16R 的约六成升到 64R 的约八成，64R 的最大时延为 16R 的 {{8|s3_10|vs16/lat_max|.2f}}~{{8|s3_0|vs16/lat_max|.2f}} 倍；数据搬移功耗占比随规模上升，方案一、二每 bit 搬移能耗增长约 {{8|manhattan|vs16/pj|.2f}}~{{8|xy_o1turn_cw|vs16/pj|.2f}} 倍（方案四 {{8|o1t|vs16/pj|.2f}} 倍）。SerDes 不随切分变化，所以 die 切得越小，芯片功耗中由 die 间搬运决定的部分越大。
> 5. **各方案的规模敏感度。** 方案四端到端只走一段路径，64R 下的数据搬移能耗（{{8|o1t|power/0.1/move_pj|.1f}} pJ/bit）与 16R 的方案二（{{4|manhattan|power/0.1/move_pj|.1f}} pJ/bit）相当，总功耗增长最少（{{8|o1t|vs16/total|.2f}} 倍），D2D 带宽与方案二相同（顺 / 逆时针各 50%），代价是 \((2n+1)B_{die}\) 的 router；方案三的直连在两种封装下缩短端到端平均走线的比例相近（x = 10% 约 28%~29%），64R 下节省的绝对走线与功耗更大。
