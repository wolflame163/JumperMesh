# NOW + 跳线层 3D 拓扑：时延约束 Mapping 与数据搬移功耗

基于 Clos `[66,66,66]` 与不可拆分路由，在 **NOW 层 + 跳线层** 3D 物理拓扑上寻找 mapping，使每条逻辑边路径时延 \(\le\) `latency_max`，并输出路径、时延与**数据搬移功耗**。

实现：`mesh3d.py`、`optimize_3d_mapping.py`。

---

## 1. 物理拓扑（默认可配置）

| 层 | 几何 | 边时延 | 边容量（默认） | 边能耗 \(E_e\) |
| --- | --- | ---: | --- | --- |
| **Layer 0 / NOW**（\(z=0\)） | 2D Mesh `(4,8,10,10,10,10,8,6)` | **80 ns** | **350×200G** / 有向边 | \(0.06\,\mathrm{pJ/(bit\cdot mm)}\times 25\,\mathrm{mm}=1.5\,\mathrm{pJ/bit}\) |
| **Layer 1 / 跳线**（\(z=1\)） | 见下方跳线拓扑预设 | **1 ns** | **180×200G** / 有向边 | **0** |
| **垂直互联** | 同坐标 NOW↔跳线 | **5 ns** | **250×200G** / 有向边 | \(1.3/2=0.65\,\mathrm{pJ/bit}\) |

### 跳线层拓扑预设（仅跳线层变化；窗口间**不相连**）

| `--jumper-topo` | 跳线 Mesh 组成（坐标含端点；仅在 NOW 有 die 处放跳线节点） |
| --- | --- |
| **`none`** / `--no-jumper` | **基准**：无跳线层（仅 NOW） |
| **`single`**（默认） | 1 个 Mesh：`(2,2)`–`(5,7)` |
| **`dual`** | 2 个 Mesh：`(0,2)`–`(3,7)` **+** `(4,2)`–`(7,7)` |
| **`quad`** | 4 个 Mesh：`(0,0)`–`(3,4)` **+** `(0,5)`–`(3,9)` **+** `(4,0)`–`(7,4)` **+** `(4,5)`–`(7,9)` |
| **`full`** | **与 NOW 同拓扑**（同 die / 同邻接）；容量仍为跳线默认 **180×200G**（小于 NOW 350×200G） |

- SSC **只放在 NOW 层**；跳线层作 feedthrough。
- 默认对端到端时延上界从 **1000 µs** 起**二分搜索**，求使路由可行的**最小** `latency_max`（ns）。

---

## 2. 路径时延与能耗

逻辑边物理路径 \(\pi=(v_0,\ldots,v_k)\)：

\[
L(\pi)=\sum_{i=0}^{k-1} d(v_i\!\to\!v_{i+1})\quad[\mathrm{ns}],
\qquad
E(\pi)=\sum_{i=0}^{k-1} E_e(v_i\!\to\!v_{i+1})\quad[\mathrm{pJ/bit}].
\]

---

## 3. 数据搬移功耗（每条逻辑边 / 路径）

每条逻辑链路按 **200 Gbps** 带宽承载流量。由路径能耗密度得到该链路的数据搬移功耗：

\[
P(\pi)=E(\pi)\times B_{\mathrm{port}},
\qquad B_{\mathrm{port}}=200\,\mathrm{Gbps}=2\times 10^{11}\,\mathrm{bit/s}.
\]

单位换算：

\[
P\,[\mathrm{W}]
= E\,[\mathrm{pJ/bit}]\times 10^{-12}\,\mathrm{J/pJ}
\times B_{\mathrm{port}}\,[\mathrm{bit/s}]
= E\times B_{\mathrm{port}}\times 10^{-12}.
\]

例：\(E=1.5\,\mathrm{pJ/bit}\)（单跳 NOW）时，

\[
P=1.5\times 2\times 10^{11}\times 10^{-12}=0.3\,\mathrm{W}.
\]

程序中默认 `port_bw_gbps=200`，对每条逻辑边输出：

| 字段 | 含义 |
| --- | --- |
| `path_energy_pj_per_bit` | \(E(\pi)\) |
| `path_power_W` | \(P(\pi)=E(\pi)\times 200\,\mathrm{Gbps}\)（经上述换算） |

### 全局汇总

| 量 | 定义 |
| --- | --- |
| 最长路径时延 | \(\max_g L(\pi_g)\) |
| 总路径能耗 | \(\sum_g E(\pi_g)\)（pJ/bit 求和，便于对照） |
| **所有路径总数据搬移功耗** | \(\displaystyle P_{\mathrm{tot}}=\sum_g P(\pi_g)=\Bigl(\sum_g E(\pi_g)\Bigr)\times 200\,\mathrm{Gbps}\) |

---

## 4. 优化目标与约束

- 硬约束：\(L(\pi_g)\le\texttt{latency\_max}\)；Layer 0（NOW）有向边 \(\ell(e)\le 350\)；Layer 1（跳线）有向边 \(\ell(e)\le 180\)；NOW↔跳线垂直边 \(\ell(e)\le 250\)。
- **热点跳线再平衡**（默认开）：对负载 >`--hot-load-frac`×容量的跳线边，先腾出短路径，再把当前最长时延档改回曼哈顿/更短路径，多轮迭代压低全局 max delay。
- 默认：从 \(1000\,\mu\mathrm{s}\) 向下二分，求使上述约束可行的**最小** `latency_max`。
- 目标：在该 `latency_max` 下最小化最大边负载 \(C=\max_e \ell(e)\)。

---

## 5. 程序输出

```bash
# 默认：single 跳线窗 + Layer0 350×200G、Layer1 180×200G、垂直 250×200G
python3 optimize_3d_mapping.py --out-dir results_3d_now_jumper/

# 双跳线 Mesh / 四跳线 Mesh
python3 optimize_3d_mapping.py --jumper-topo dual --out-dir results_3d_jumper_dual/
python3 optimize_3d_mapping.py --jumper-topo quad --out-dir results_3d_jumper_quad/
python3 optimize_3d_mapping.py --jumper-topo full --out-dir results_3d_jumper_full/

# 调整必须曼哈顿比例
python3 optimize_3d_mapping.py --manhattan-top-pct 30 --out-dir results_3d_now_jumper/

# 固定时延上界（跳过二分）
python3 optimize_3d_mapping.py --latency-max 500 --manhattan-top-pct 20 --out-dir results_3d_now_jumper/
```

- `logical_edge_routes.jsonl` / `.txt`：每条逻辑边的物理路径、\(L\)、\(E\)、**\(P\)**（200G）
- `logical_edge_routes_summary.json` / `mapping3d.json`：最长时延、总能耗、**总数据搬移功耗 (W)**、二分日志
- 图：`mesh3d_200g_ports.png`（有向 200G 总图，**默认输出**）、`topology_3d.png`、`loads_now.png`、`loads_jumper.png`、`loads_vertical.png`

---

## 6. 一句话

> 在 Layer 0 / NOW（80 ns / 1.5 pJ/bit / **350×200G**）+ Layer 1 / 跳线（1 ns / 0 / **180×200G**）+ 垂直（5 ns / 0.65 pJ/bit / **250×200G**）上路由 Clos；从 1000 µs 二分求最小可行端到端时延上界；每条逻辑边按 200 Gbps 计，**数据搬移功耗 \(P=E(\mathrm{pJ/bit})\times 200\,\mathrm{Gbps}\)**。

---

## 7. 当前结果（基准 none + 三种跳线拓扑；Layer0 350 / Layer1 180 / 垂直 250）

| topo | best seed | max delay | n_at_max | C | NOW / jumper / vert max | power (W) |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| **none（基准，无跳线）** | 2 | **960 ns** | 48 | 279 | 279 / — / — | 13763 |
| single | 7 | **560 ns** | 624 | 250 | 231 / 180 / 250 | 10869 |
| **dual** | 6 | **480 ns** | 534 | 294 | 294 / 180 / 250 | 10069 |
| quad | 4 | **508 ns** | 1 | 301 | 301 / 144 / 194 | 10286 |

相对无跳线基准，dual 将最长时延从 960→480 ns。报告：`results_3d_now_jumper/NOW_JUMPER_3D_REPORT.html`。

基准命令：`python3 optimize_3d_mapping.py --no-jumper --out-dir results_3d_baseline_now/`
