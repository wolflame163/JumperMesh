# 术语表 {#glossary}

本表给出报告中反复出现的概念与符号的中英文对照及定义。后文公式若无特别说明，均采用本表约定。

## 概念

| 中文 | English | 定义 |
|---|---|---|
| 晶圆级交换 / WSE-Switch | Wafer-Scale Switch | 将多颗交换 die 封装在同一载体上、以片上 / 封装内短距接口互联构成的大容量交换系统 |
| die | Die | 单颗芯片裸片；本报告默认尺寸 32 mm（x）× 25 mm（y） |
| 2D Mesh | 2D Mesh | 仅相邻 die 上下左右互联的矩形网格物理拓扑 |
| SIO | Short-reach I/O | die 间短距高速接口；本报告能耗 0.35 pJ/bit，时延 11.5 ns/跳 |
| SerDes | Serializer/Deserializer | 线路侧 400GE 串并转换；本报告总功耗取常数 3795 W |
| 馈通走线 | Feedthrough wiring | 过路 die 内、为非本 die 源宿流量提供的片上走线；**不含源段 / 宿段**；直通取 die 边长，转弯取两边 Manhattan |
| 源段 / 宿段 | Source/destination on-die wire | 交换核到本 die 边端口的走线；本报告时延与功耗模型均不计 |
| 缝隙 | Inter-die gap | 相邻 die 之间的物理间隙（1 mm）；计入时延，**不计功耗** |
| 线路侧走线 | Line-side on-die wire | 外部 400GE 端口到交换核的走线；本报告**不计功耗** |
| CLOS | CLOS fabric | 三级交换网络；本报告为共址 CLOS(\(N,N,N\))，同编号 L1/L2/L3 落在同一 die |
| L1 / L2 / L3 | Ingress / middle / egress switch | CLOS 三级交换模块 |
| DSL | Die-Scale Logic (mapping) | 将逻辑 CLOS 链路映射到 2D Mesh 物理路径的一类方案 |
| DSL XY 路由 | DSL XY routing | 方案一：顺时针 O1Turn 维序选路（XY/YX 中选顺时针转弯） |
| DSL 最短路径路由 | DSL shortest-path routing | 方案二：任意 Manhattan 最短路径 + 最热边最小化 |
| DSL+直连 | DSL + L1–L3 direct | 方案三：在方案二上叠加 L1→L3 直连逻辑边 |
| O1Turn(DR) | O1Turn Die Router | 方案四：每颗 die 为同构 NoC router，src→dst 按顺时针 / 逆时针 O1Turn 各 50% 转发（无 CLOS） |
| NoC router | Network-on-Chip router | O1Turn(DR) 中单 die 的五组端口交换模块（1 组线路侧 + 4 组邻 die） |
| NOW die | Network-on-Wafer die | 第 5、6 章：Reticle 底层整片 die，承载四边 SIO、SW↔OE 点对点走线与供电 TSV；第 5 章另含多平面 NoC router，第 6 章另含行列总线与静态 mux |
| SW die | Switch die | 第 5、6 章：堆叠在 NOW die 上的交换逻辑 die（OE 接口、报文处理、接口处理、交换引擎；第 6 章为 L1 / L2 / L3），多流水线架构 |
| lane（NOW die） | — | 第 6 章：NOW die 上带宽为 b 的一条逻辑通道；有向边上的 lane k 即该方向 SIO 端口 k |
| 静态 mux | Static multiplexer | 第 6 章：NOW die 上上电配置、运行中不变的选择器，实现转向、注入与弹出连线 |
| OE die | Optical-engine die | 第 5 章：堆叠在 NOW die 上的光引擎 die，每个 Reticle 一颗，带宽等于 SW die 线路侧带宽，按流水线分 N 个 3.2T 光引擎切片，经顶部 FAU 向上扇出光纤 |
| FAU | Fiber Array Unit | 光纤阵列耦合单元；第 5 章中垂直贴装在 OE die 顶部 |
| 流水线 | Pipeline | 第 5 章：SW die 内独立处理 3.2T 线路流量的报文处理通道（8 × 400GE） |
| NoC 平面 | NoC plane | 第 5 章：全部 Reticle 上同编号 router 组成的独立 2D Mesh；平面之间无链路 |
| buffered / bufferless NoC | Buffered / bufferless NoC | router 有输入缓冲与信用流控（冲突时排队）/ 无缓冲（冲突时偏转或丢弃） |
| 注入率 | Injection rate | 每个 router 本地口每周期注入的 flit 数，归一化到端口宽度 |
| 喷洒 / 重排序 | Spraying / reordering | 第 5 章：交换引擎把发往 NoC 的报文均匀分到 M 个平面 / 在目的端按流恢复顺序 |
| 邻 die 加速比 | Neighbor-die speedup | 单条有向 die 边带宽 / 单 die 线路侧带宽 \(B_{die}\) |
| 注入加速比 | Injection speedup | 单 die 自身发往其他 die 的流量（不含馈通）/ \(B_{die}\) |
| 二分下界 | Bisection lower bound | 中间割跨割逻辑流量由割上 \(n\) 条边分摊得到的每边最小带宽 |
| 逻辑→物理映射粒度 | L2P mapping quantum | 一条带宽为 \(b\) 的逻辑链路；物理路径每跳占用 1 个 \(b\) 端口 |
| 数据搬移功耗 | Data-movement power | SIO + 馈通走线功耗（不含 SerDes） |
| 静态功耗 | Static power | SerDes + SIO 静态部分（70%，按最终物理构型的 SIO 配置带宽）；走线按动态计 |
| 最大功耗 | Peak / max power | 满载（或指定最差流量）下的芯片总功耗 |

## 变量与符号

| 符号 | 中文名 | English | 含义 / 本报告取值 |
|---|---|---|---|
| \(N\) | die 数 / 每级 switch 数 | Number of dies | \(N=n^2\)；16R 为 16，64R 为 64 |
| \(n\) | Mesh 边长 | Mesh dimension | 4 或 8 |
| \(B_{die}\) | 单 die 线路侧带宽 | Per-die line bandwidth | \(409.6\mathrm T/N\)（25.6T / 6.4T） |
| \(b\) | 单条逻辑链路带宽 | Per-logical-link bandwidth | \(409.6\mathrm T/N^2\)（16R = 1.6T，64R = 0.1T）；**逻辑→物理映射的原子粒度**，不可拆分 |
| \(C\) | 最热有向边负载（条） | Hottest directed edge load | 经过该边的逻辑链路条数（每条带宽 \(b\)） |
| \(C_{\mathrm{tbps}}\) | 最热边带宽 | Hottest edge bandwidth | \(C\cdot b\)；同构 die 每条有向边的 SIO 配置带宽 |
| \(n_{dir}\) | 有向 die 边数 | Directed die edges | \(4n(n-1)\)：4×4 为 48，8×8 为 224 |
| \(h\) / \(\|\pi\|\) | 跳数 | Hop count | 路径经过的 die 间边数 |
| \(f_d\) | 单颗过路 die 馈通长度 | Per-transit-die feedthrough length | 直通 \(W\) 或 \(H\)；转弯最坏 \(W+H\) |
| \(\mathrm{wire}_{ft}\) | 馈通走线距离 | Feedthrough distance | \(\sum f_d\)（不含源/宿、不含缝隙） |
| \(g\) | 缝隙 | Gap | 1 mm/跳；时延计、功耗不计 |
| \(e_w\) | 走线能耗密度 | Wire energy density | 0.1 或 0.06 pJ/bit/mm |
| \(n_{turn}\) | 横纵转向次数 | Turn count | 路径在 NOW die 内横向 ↔ 纵向变化的次数，每次 2 ns |
| \(t_{\mathrm{sw\_die}}\) | die 侧固定时延 | Die-side fixed latency | 120 ns；L1~L3 之外的处理逻辑，端到端计一次 |
| \(t_{\mathrm{sw\_sw}}\) | L2 交换时延 | L2 switch latency | 方案一~三经 L2 中转计一次 70 ns；L1→L3 直连与 O1Turn(DR) 为 0 |
| \(\Delta(\pi)\) | 路径时延 | Path latency | \(h\cdot11.5+(\mathrm{wire}_{ft}+h\cdot g)\cdot0.5+2n_{turn}+t_{\mathrm{sw\_die}}+t_{\mathrm{sw\_sw}}\) |
| \(\Delta_{tr}(\pi)\) | 传输时延 | Transport latency | \(\Delta\) 中的 SIO + 馈通与缝隙 + 转向；CLOS 端到端为两段 \(\Delta_{tr}\) 之和再加固定项 |
| \(P_{\mathrm{SIO}}\) | SIO 功耗 | SIO power | 静态 \(n_{dir}\cdot C_{\mathrm{tbps}}\cdot0.35\cdot0.7\) + 动态 \(\sum h\lambda\cdot0.35\cdot0.3\)；满载 \(\lambda=b\) |
| \(P_{\mathrm{wire}}\) | 馈通走线功耗 | Feedthrough wire power | \(\sum \overline{\mathrm{wire}}_{ft}\cdot\lambda\cdot e_w\)（纯动态） |
| \(P_{\mathrm{SerDes}}\) | SerDes 功耗 | SerDes power | 3795 W（计入静态） |
| \(P_{\mathrm{chip}}\) | 芯片总功耗 | Chip total power | 静态 + 当前流量动态 = \(P_{\mathrm{SerDes}}+P_{\mathrm{SIO}}+P_{\mathrm{wire}}\) |
| \(x\) | D2D 带宽增长容限 | Allowed D2D growth | 方案三：0 / 5% / 10% |
| \(N\)（第 5 章） | SW die 流水线数 | Pipelines per SW die | \(B_{die}/P\)；16R 为 8，64R 为 2（第 5 章中 die 数写作 \(n^2\)） |
| \(M\) | NoC 平面数 | Number of NoC planes | 每颗 NOW die 的 router 数，\(M=kN\) |
| \(k\) | 每条流水线平面数 | Planes per pipeline | \(\lceil\max(1,\gamma)/\eta\rceil\) |
| \(P\) | 流水线带宽 | Pipeline bandwidth | 3.2 Tbps；亦为 NoC 平面端口宽度 |
| \(\lambda\) | 单平面注入率 | Per-plane injection rate | \(N/M=1/k\) |
| \(\gamma\) | 单位注入最热边负载 | Hottest-edge load per unit injection | 最坏置换 \(n/2\)；AllToAll 取实测 |
| \(\rho^*\) / \(\rho_{sat}\) | 理想 / 可持续注入率 | Ideal / sustainable injection rate | \(\rho^*=\min(1,1/\gamma)\)，\(\rho_{sat}=\eta\rho^*\) |
| \(\eta\) | router 饱和效率 | Router saturation efficiency | buffered 取 0.8，bufferless 取 0.5 |

## 时延与功耗口径（与第 1 章一致）

**时延**（端到端）：

\[
\Delta(\pi)=h\cdot 11.5 + \Big(\sum_d f_d + h\cdot g\Big)\cdot 0.5 + 2\,n_{turn} + t_{\mathrm{sw\_die}} + t_{\mathrm{sw\_sw}}\ \ \mathrm{ns}.
\]

SIO 11.5 ns/跳，馈通与缝隙走线 0.5 ns/mm，NOW die 内每次横纵转向 2 ns；\(t_{\mathrm{sw\_die}}=120\) ns 端到端计一次；\(t_{\mathrm{sw\_sw}}\) 在方案一~三经 L2 中转时计一次 70 ns，L1→L3 直连与方案四 O1Turn(DR) 为 0。CLOS 端到端的 \(h\)、\(\sum f_d\)、\(n_{turn}\) 为 L1→L2、L2→L3 两段之和。

**功耗**：不计线路侧走线、不计缝隙；馈通距离仅 \(\sum f_d\)。全部数值（含满载）= 静态 + 当前流量下的动态：

\[
P_{\mathrm{SIO}}=n_{dir}\cdot C_{\mathrm{tbps}}\cdot0.35\cdot0.7+\sum_g h_g\lambda_g\cdot0.35\cdot0.3,\qquad
P_{\mathrm{chip}}=P_{\mathrm{SerDes}}+P_{\mathrm{SIO}}+P_{\mathrm{wire,ft}}.
\]
