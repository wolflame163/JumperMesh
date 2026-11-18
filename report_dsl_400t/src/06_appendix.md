# 附录 A 复现方法与校验 {#appA}

## A.1 复现命令与校验

全部数值可在 `switch_dse/waferscale` 下复现：

```
python3 dsl_mesh_400t.py --sizes 4 --seeds 8 --max-iter 60 --out report_dsl_400t/data
python3 dsl_mesh_400t.py --sizes 8 --seeds 3 --max-iter 60 --out report_dsl_400t/data
# 仅修改时延 / 功耗参数时，可不重新布线：python3 dsl_mesh_400t.py --from-paths --out report_dsl_400t/data
python3 dsl_l1l3_direct.py --sizes 4 8 --data report_dsl_400t/data
python3 dsl_o1turn_noc.py --sizes 4 8 --out report_dsl_400t/data
python report_dsl_400t/tools/figs.py
python report_dsl_400t/tools/figs_l1l3.py
python report_dsl_400t/tools/figs_o1t.py
python report_dsl_400t/tools/figs_workflow.py
python report_dsl_400t/tools/figs_flow.py
python report_dsl_400t/tools/figs_scale.py
python3 dsl_o1t_stack.py --sizes 4 8 --data report_dsl_400t/data
python report_dsl_400t/tools/figs_stack.py
python3 dsl_now_stack.py --sizes 4 8 --data report_dsl_400t/data
python report_dsl_400t/tools/figs_now.py
python report_dsl_400t/tools/export_mapping.py
python report_dsl_400t/tools/build_pdf.py --pdf
```

- `dsl_mesh_400t.py`：用 waferscale 代码中的 `build_center_symmetric_mesh` 生成 \(n\times n\) Mesh，枚举 CLOS(\(N,N,N\)) 三级共址的全部逻辑链路，按两种口径路由，输出逐条链路路径、边负载、跳数 / 走线 / 时延 / 功耗与场景功耗（`data/dsl_{n}x{n}.json`）。方案二为启发式，取多个随机种子中 \((C,\ \sum\ell,\ \sum\text{转弯})\) 字典序最优者：4×4 取 8 个种子，8×8 取 3 个种子。
- `dsl_l1l3_direct.py`：读入方案二的逐条路径，按 1.6 节的规则在 x = 0 / 5% / 10% 下叠加 L1→L3 直连，输出全部直连路径、叠加后的边负载、端口增长，以及按流量口径计算的 L1→L3 时延 / 走线 / 跳数与满载、场景功耗（`data/dsl_l1l3_{n}x{n}.json`）；`figs_l1l3.py` 由此生成图 1-2、图 2-7、图 3-7、图 3-9。
- `dsl_o1turn_noc.py`：方案四。对全部 \(N^2-N\) 个 die 对求顺时针与逆时针两条 O1Turn 路径、各承担 50% 流量（复用 `dsl_mesh_400t.py` 的路由与时延 / 功耗模型，并校验两条路径的跳数、馈通与时延相同），对每条有向边求 “(src, dst) 在该边上的权重（经过路径数 × 0.5）矩阵的最大权指派” 得到无阻塞所需带宽（校验全部有向边恰为 \(n/2\)），另输出 AllToAll 负载、外圈对角互打负载、router 交换容量、端到端跳数 / 走线 / 时延，以及满载、热点与最坏置换（最大权指派）的功耗（`data/dsl_o1t_{n}x{n}.json`）；`figs_o1t.py` 由此生成图 1-3、图 2-8。
- `figs_flow.py`：各方案 x.x.7 节的 die2die 流量带宽图（图 2.2-4～2.5-4c、图 3.2-4～3.5-4c）。按场景求每条有向边的实际流量 xx（方案一 / 二按 CLOS 两级喷洒，并断言 AllToAll 与置换逐边相同；方案三按直连承载 \(D(i,k)\)、其余喷洒；方案四取最佳 / 最差置换指派与 AllToAll 负载），yy 取物理构型图的边带宽；脚本断言每条边 xx ≤ yy，且 \(\sum_e xx\times0.35\times0.3\) 等于结果 JSON 中该场景的 SIO 动态功耗。
- `figs_scale.py`：读入上述全部结果，生成第 4 章 16R 与 64R 的对比图（图 4-1）；第 4 章的时延分解按最坏 / 平均路径的跳数、走线长度拆为 SIO 接口（11.5 ns/跳）、馈通走线（0.5 ns/mm）、横纵转向（2 ns/次）、\(t_{\mathrm{sw\_die}}\)（120 ns，端到端一次）与 \(t_{\mathrm{sw\_sw}}\)（方案一~三经 L2 一次 70 ns，直连与 O1Turn(DR) 为 0）五项，功耗分解直接取各方案的满载功耗分项。
- **校验**：(1) 每条路径的闭式最坏时延与逐 die 累加时延一致；(2) 方案二的 \(C\) 与二分下界对照（4×4、8×8 均达到下界）；(3) 方案一的最热边与解析式 \(n^2(2n-1)/2\) 一致（4×4 为 56，8×8 为 480）；(4) 方案一、二的置换满载与 AllToAll 满载功耗一致；(5) 方案三：每条有向边的叠加负载不小于方案二（CLOS 部分逐边不变），最热边不小于 \(C_2\) 且不超过 \((1+x)C_2\)；不叠加任何直连时，流量口径的 L1→L3 最大 / 平均时延、走线、跳数、满载与 AllToAll / 置换场景功耗与方案二逐项一致（SIO 静态按物理构型的最热边配置带宽计，热点场景亦按「物理构型 SIO 静态 + 当前流量动态」与方案二对拍）；L1→L3 最大时延与逐 die 对的直连 / 两跳最坏时延取最大值的结果一致；(6) 方案四：每个 die 对的顺 / 逆时针路径跳数、馈通与时延相同；全部有向边的最大权指派最大值与最小值都恰为 \(n/2\)（与 1.6.3 节的上界、二分下界一致），外圈对角互打的最热边也恰为 \(n/2\)，计算脚本对三者断言；(7) 单边加速比：按存储的逐条路径独立重算每条有向 die 边负载，方案二为 2.00×（16R）/ 4.00×（64R），方案一为 3.50× / 7.50×，与正文一致；方案二恰等于二分割下界 \(n/2\)，不含馈通的注入加速比为 \(2(N-1)/N\)（1.875× / 1.969×）。
- `dsl_o1t_stack.py`：第 5 章 3D 堆叠变种。读入方案四结果，按 \(N=B_{die}/3.2\mathrm T\)、\(\gamma\)（最坏置换 \(n/2\)，AllToAll 取实测）与 router 饱和效率 \(\eta\)（理想 / buffered / bufferless）计算 \(k=\lceil\max(1,\gamma)/\eta\rceil\)、\(M=kN\)、die 边带宽、SIO 静态功耗、buffered 输入缓冲、混合键合面积与光纤数（`data/dsl_stk_{n}x{n}.json`）；`figs_stack.py` 由此生成图 5-1～图 5-7。脚本断言 \(M\bmod N=0\)、\(\lambda=N/M\le\rho_{sat}\)，以及 \(\eta=1\)、最坏置换时 \(M\times3.2\mathrm T\) 恰等于方案四的无阻塞单边带宽。
- `dsl_now_stack.py`：第 6 章 DSL 3D 堆叠细分方案。读入方案一 / 二的逐条路径，统计每颗 die 的注入 / 弹出 / 直通 / 转向连线与不同图样数；按 “直通段保持 lane、转向处 lane 差 ≤ w” 做 first-fit lane 分配，求所需 lane 数 \(K(w)\)；对每个垂直端口池做二分匹配求最小 \(s\)（备用端口 \(\Delta\) = 0、U/8、U/4、U/2），生成每颗 die 的 mux 静态配置并只用配置逐条回放全部逻辑链路，另给出 mux 扇入、交叉点、配置量与总线线密度（`data/dsl_now_{n}x{n}.json`）；`figs_now.py` 由此生成图 6-1～图 6-7。脚本断言每个出向 lane 至多一路驱动、每个入向 lane 至多一处使用，以及全部配置的回放通过。
- `build_pdf.py`：正文中的数值与表格在构建时直接从 JSON 填入，图由 `figs.py` 从同一 JSON 生成，保证图、表、正文一致；`--pdf` 时把 PDF、`export_mapping.py` 导出的物理映射 log（`mapping/`）与结果 JSON（`data/`）一并输出到 `report_dsl_400t/output/`。

## A.2 物理映射结果 log

逻辑→物理映射以**单条逻辑链路**为原子粒度（16R：\(b=1.6\mathrm T\)；64R：\(b=0.1\mathrm T\)），不可把一条链路拆到多条物理路径。各方案逐条逻辑链路的物理映射结果以文本 log 给出，与本报告 PDF 放在同一目录（`output/`）下的 `mapping/` 子目录中，点击下表文件名即可打开（链接为相对路径，整个目录可整体拷贝）；计算结果 JSON 位于同目录的 `data/` 子目录。每行一条逻辑链路：逻辑端点、源 / 宿 die、die 间跳数、转弯次数、均值 / 最坏口径走线（mm）、最坏口径路径时延（ns，含转向与一次 \(t_{\mathrm{sw\_die}}\)；CLOS 链路另含 \(t_{\mathrm{sw\_sw}}\)，直连与方案四不含）与逐 die 的物理路径。

!tab 表 A-1 物理映射结果 log 文件

| 方案 | 4×4 | 8×8 | 内容 |
|---|---|---|---|
| 方案一 DSL XY 路由 | [s1_dsl_xy_4x4.log](mapping/s1_dsl_xy_4x4.log) | [s1_dsl_xy_8x8.log](mapping/s1_dsl_xy_8x8.log) | 全部 L1→L2、L2→L3 逻辑链路（含同 die 0 跳链路） |
| 方案二 DSL 最短路径路由 | [s2_dsl_shortest_4x4.log](mapping/s2_dsl_shortest_4x4.log) | [s2_dsl_shortest_8x8.log](mapping/s2_dsl_shortest_8x8.log) | 同上，为映射算法（瓶颈动态规划 + 拆线重布）的结果 |
| 方案三 DSL+直连 x = 0 | [s3_l1l3_direct_x0_4x4.log](mapping/s3_l1l3_direct_x0_4x4.log) | [s3_l1l3_direct_x0_8x8.log](mapping/s3_l1l3_direct_x0_8x8.log) | 叠加的 die 间与片内 L1→L3 直连；CLOS 部分同方案二 |
| 方案三 DSL+直连 x = 5% | [s3_l1l3_direct_x5_4x4.log](mapping/s3_l1l3_direct_x5_4x4.log) | [s3_l1l3_direct_x5_8x8.log](mapping/s3_l1l3_direct_x5_8x8.log) | 同上 |
| 方案三 DSL+直连 x = 10% | [s3_l1l3_direct_x10_4x4.log](mapping/s3_l1l3_direct_x10_4x4.log) | [s3_l1l3_direct_x10_8x8.log](mapping/s3_l1l3_direct_x10_8x8.log) | 同上 |
| 方案四 O1Turn(DR) | [s4_o1turn_noc_4x4.log](mapping/s4_o1turn_noc_4x4.log) | [s4_o1turn_noc_8x8.log](mapping/s4_o1turn_noc_8x8.log) | 全部 src die → dst die 的顺时针（cw）/ 逆时针（ccw）路径 |

DSL 方案（一～三）每颗 die 的片上走线矢量图由 `tools/figs_die_map.py` 生成，位于 `figs/die_map/<scheme>_<n>x<n>/die_XX.svg`；报告第 2/3 章映射节嵌入总览图 `figs/fig_die_map_<scheme>_<n>x<n>.png`（4×4 为全阵列；8×8 为左上连续 3×3 子阵列，保证邻格即真实邻 die，可对核对跨边出/入）：四边端口按 \(b\) 粒度排布，走线区分 feedthrough 与 L1/L2/L3 端口连接。

log 中 die 编号为 \(r\cdot n+c\)，行号 \(r\) 自上而下、列号 \(c\) 自左而右，与图 1-3 及第 2、3 章各图一致；图 1-1 引自 HyperSwitch 报告，行号自下而上，与本报告上下镜像（图 1-1 的 die 0 → die 14 在 log 中对应 die 12 → die 2 的上下镜像）。
