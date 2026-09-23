# Algorithm 1：Pairwise Exchange 输入 / 输出说明

参考论文 *Waferscale Network Switches*（本仓库 `Wafer Scale Switching.pdf`）§IV.A **Mapping a Clos Topology** 与 **Algorithm 1**，结合当前实现 `algorithm1_pairwise_exchange.py` 整理符号与 I/O。

---

## 1. 问题形式（论文）

将逻辑拓扑映射到晶圆上的物理 mesh 时，目标是在相邻 die 边上尽量压低逻辑链路拥塞，从而抬高可达 radix / 对分带宽。

| 符号 | 含义 |
| --- | --- |
| \(G\) | 给定的**逻辑拓扑**（论文中为 Clos；实现中为三级 Clos 的逻辑边集） |
| \(F\) | 晶圆上的**物理布局/邻接结构**（论文中的 physical mesh / floorplan 载体） |
| \(M_i\) | \(G\) 的一种**摆放（floorplan / mapping）** |
| \(C(M)\) | 在映射 \(M\) 下，任意**物理相邻** die 对之间穿过的**逻辑链路条数的最大值** |
| 优化目标 | \(\displaystyle \min_{M_i} C(M_i)\) |

论文原文要点：

- \(C(M)\) 统计的是相邻芯片间承载的逻辑链路数（中间 die 作 feedthrough / repeater）。
- 映射离散、不可微；\(N\) 个 chiplet 有 \(N!\) 种摆法，故用 pairwise exchange 求局部最优。
- 论文对随机初值重复跑多次（文中写 1000 次），取最好结果。

---

## 2. Algorithm 1 伪代码符号（论文）

| 符号 | 论文定义 | 当前实现对应 |
| --- | --- | --- |
| \(R = [r_i]\) | SSC（sub-switch chiplet）列表 | Clos 中全部 SSC 的编号 \(0..N-1\) |
| \(P = [p_i]\) | 晶圆上**物理位置**列表 | 中心对称 2D Mesh 格点 \((row,col)\) |
| \(M\) | 映射 \(M(r_i)=p_i\) | `mapping[ssc_id] = (r,c)` |
| \(C\) / \(C(M)\) | 任意相邻 SSC 对上逻辑链路数的**最大值** | `compute_C(mapping)`：最短路累加后取 \(\max\) 边负载 |
| \(C_{prev}\) | 当前已接受的 \(C\) | pairwise 循环中的 `c_prev` |
| \(C_{new}\) | 交换一对 SSC 位置后的 \(C\) | 试 swap 后的 `c_new` |
| `swap(M(r_i), M(r_j))` | 交换两个 SSC 的物理位置 | 交换 `mapping[i]` 与 `mapping[j]` |

**伪代码流程（与论文一致）：**

1. 给定初值映射 \(M\)，算 \(C_{prev}=C(M)\)。
2. 当尚未收敛时：对 \(R\) 中每一对 \((r_i,r_j)\)：
   - 交换二者位置；
   - 若 \(C_{new}<C_{prev}\)，保留交换并更新 \(C_{prev}\)；
   - 否则换回。
3. 一整轮所有 pair 都无法再改进时收敛。

---

## 3. 当前实现的输入（Input）

下列数值均为**当前仓库实验配置**（`algorithm1_pairwise_exchange.py` 默认 + 已跑通的 200×10 结果）。

### 3.0 当前各项输入一览

| 类别 | 符号 / 变量 | 当前取值 |
| --- | --- | --- |
| 物理 mesh 行宽 | `row_widths` | `(4, 8, 10, 10, 10, 10, 8, 6)` |
| 行数 | — | \(8\) |
| 最大行宽（列网格宽度） | `max_w` | \(10\) |
| die / SSC 总数 | \(N=\|R\|=\|P\|\) | **66**（**所有 die 均为 SSC**） |
| 物理无向边数 | `\|adj_edges\|` | **114** |
| 结点度数 | \(\delta_{\min},\delta_{\max}\) | \(2\)–\(4\) |
| 中心行割边（row3↔row4） | — | \(10\) 条 |
| SSC 列表 | \(R=[r_i]\) | \(r_i\in\{0,1,\ldots,65\}\)，\(\|R\|=66\) |
| Clos 三级规模 | \(G\) stages | **`[66, 66, 66]`**（每一级都包含全部 66 个 SSC；同 id 共址） |
| L1–L2 逻辑带宽 | 任意 SSC × 任意 SSC | **200 Gbps**（全连接 \(66\times66\)） |
| L2–L3 逻辑带宽 | 任意 SSC × 任意 SSC | **200 Gbps**（全连接 \(66\times66\)） |
| 逻辑边集规模 | \(\|E_G\|\) | **8712**（\(2\times66\times66\)，含 \(132\) 条自环/本地） |
| 逻辑边构造 | — | 两级全连接；\(i=j\) 不占 mesh |
| 单端口 / 单逻辑链路带宽 | \(B_{port}\) | **200 Gbps** |
| TH-5-like die 面积（可用带宽估计） | `DIE_AREA_MM2` | \(800\,\mathrm{mm}^2\) |
| 内部带宽密度（可用带宽估计） | `INTERNAL_BW_DENSITY` | \(3200\,\mathrm{Gbps/mm}\) |
| 物理边可用带宽（估计） | \(\sqrt{800}\times3200\) | \(\approx 90.51\,\mathrm{Tbps}\) |
| 路由 | — | mesh 上**全 BFS 最短路径**（多父时按路径计数回传；`C(M)` 用最短路累加） |
| 每 trial 尝试交换的 pair 数 | \(\binom{N}{2}\) | \(2145\) |
| pairwise 最大轮数 | `max_rounds` | \(200\)（整轮无改进则提前停） |
| trials / run | `trials` | **200** |
| 独立 runs | `runs` | **10** |
| 基种子 | `seed` | **42** |
| 各 run 种子 | `seed + 1000·r` | `42, 1042, 2042, …, 9042` |
| top-k / run | `top_k` | **10** |
| 并行 workers | `workers` | `min(runs, cpu_count)`（实测跑 10） |
| trial 0 初值 | \(M_0\) | 结构化 Clos：middle→中心，ingress→上，egress→下 |
| trial ≥1 初值 | \(M_0\) | `Random(seed+trial)` 均匀随机置换 \(P\) |

### 3.1 物理拓扑 \(F\)（Mesh）— 格点明细

中心对称对齐：第 \(r\) 行宽度 \(w_r\)，列偏移 \(\lfloor(\mathrm{max\_w}-w_r)/2\rfloor\)。

| row \(r\) | 宽度 \(w_r\) | 列偏移 | 占用列 \(c\) |
| ---: | ---: | ---: | --- |
| 0 | 4 | 3 | `3,4,5,6` |
| 1 | 8 | 1 | `1,2,3,4,5,6,7,8` |
| 2 | 10 | 0 | `0..9` |
| 3 | 10 | 0 | `0..9` |
| 4 | 10 | 0 | `0..9` |
| 5 | 10 | 0 | `0..9` |
| 6 | 8 | 1 | `1,2,3,4,5,6,7,8` |
| 7 | 6 | 2 | `2,3,4,5,6,7` |

- 位置集 \(P\)：上表全部 \((r,c)\)，\(|P|=66\)。
- 邻接：四邻接（右 / 下），仅当两端均在 \(P\) 内；共 **114** 条无向边。

### 3.2 逻辑拓扑 \(G\)（Clos）

**三级 Clos 规模 `[66, 66, 66]`：**

- 物理上共 66 个 die，**每个 die 都是 SSC**。
- 逻辑上每一级都有 66 个结点；**同一 SSC id 在三级中共址**（stage-1/2/3 的结点 \(i\) 都落在同一物理 die \(M(i)\) 上）。
- **任意** SSC（第一级）与 **任意** SSC（第二级）之间逻辑带宽 **200G**。
- **任意** SSC（第二级）与 **任意** SSC（第三级）之间逻辑带宽 **200G**。

| 输入 | 符号/变量 | 当前取值 |
| --- | --- | --- |
| Clos 三级规模 | stages | **`[66, 66, 66]`** |
| 物理 SSC 数 | \(\|R\|\) | **66** |
| L1–L2 | 全连接 | \(66\times66\) 条 × **200 Gbps** |
| L2–L3 | 全连接 | \(66\times66\) 条 × **200 Gbps** |
| 逻辑边总数 | \(\|E_G\|\) | **8712**（其中 \(2\times66\) 条 \(i=j\) 本地，不占 mesh） |
| 单链路带宽 | \(B_{port}\) | **200 Gbps** |

逻辑链路在物理 mesh 上按**最短路径**展开（\(M(i)\to M(j)\)，\(i\neq j\)）；途经边计入负载。  
因需求为均匀 all-pairs，**\(C(M)\) 与摆放无关**（Algorithm 1 交换不改变 \(C\)）。

### 3.3 搜索超参数（当前默认）

| 输入 | 变量 | 当前取值 |
| --- | --- | --- |
| 每 run 随机初值次数 | `trials` | **200** |
| 独立 run 数 | `runs` | **10** |
| 基种子 | `seed` | **42** |
| run 种子列表 | — | `[42, 1042, 2042, 3042, 4042, 5042, 6042, 7042, 8042, 9042]` |
| 每 run 保留解数 | `top_k` | **10**（优先不同 \(C\)） |
| 并行度 | `workers` | 自动；完整实验为 **10** |
| pairwise 最大轮数 | `max_rounds` | **200** |

单次 trial 的初值 \(M_0\)：

- trial \(0\)：结构化 Clos 摆放（middle 靠中心，ingress 靠上，egress 靠下）；
- 其余 trial：均匀随机置换 \(P\)。

---

## 4. 当前实现的输出（Output）

### 4.1 核心优化量

| 输出 | 符号 | 定义 | 最优实验值 |
| --- | --- | --- | --- |
| 拥塞目标 | \(C^\*=C(M)\) | 最热物理边的逻辑链路条数 | **992**（与 \(M\) 无关） |
| 映射 | \(M\) | SSC→位置；共址三级 | 恒等摆放即可 |
| 最热边 200G 端口数 | \(n_{200G}=C\) | — | **992** |
| 最热边带宽 | \(C\cdot B_{port}\) | — | **198.4 Tbps** |

### 4.2 由 \(C\) 导出的带宽 / 端口

论文保证每条逻辑链路至少 \(B_{port}=200\,\mathrm{Gbps}\)。对物理边 \(e\)：

| 输出 | 公式 | 含义 |
| --- | --- | --- |
| 边负载 | \(\ell(e)\) | 穿过边 \(e\) 的逻辑链路数 |
| 边带宽需求 | \(\mathrm{BW}(e)=\ell(e)\cdot B_{port}\) | Gbps / Tbps |
| 200G 端口粒度 | \(n_{200G}(e)=\ell(e)\) | 因 \(B_{port}=200G\)，端口数 = 逻辑条数 |
| 最热边带宽 | \(\mathrm{BW}_{hot}=C\cdot B_{port}\) | 当前 \(992\times 200=198.4\,\mathrm{Tbps}\) |

图示：`best_alg1_200g_ports.svg` / `.png`（边上数字 = \(n_{200G}(e)\)）。

### 4.3 批量搜索汇总

| 输出文件 | 内容 |
| --- | --- |
| `algorithm1_top10.json` | 10 runs 各自 `best_C`、全局 Top-10（优先不同 \(C\)） |
| `algorithm1_runs200x10.log` | 完整运行日志 |
| `best_alg1_mapping.json` | 全局最优 \(M^\*\) 与每边 \(\ell(e)\) |
| `best_alg1_200g_ports.md` | 每边 200G 端口数表 |

**当前 \(C=992\)**（Clos `[66,66,66]` all-pairs ×2）；图见 `best_alg1_200g_ports.png`。

---

## 5. 数据流总览

```text
输入:
  Clos stages = [66, 66, 66]   每级含全部 SSC；同 id 共址
  L1-L2 / L2-L3: 任意 SSC×任意 SSC @ 200G
  |E_G| = 8712
  F  = Mesh row_widths=(4,8,10,10,10,10,8,6), |P|=66
  B_port = 200 Gbps

          ┌─────────────────────────┐
          │  Algorithm 1            │
          │  pairwise exchange      │
          │  最小化 C(M)            │
          └───────────┬─────────────┘
                      │
输出:
  M*           最优 SSC→位置映射
  C* = C(M*)   最热边逻辑链路数
  ℓ(e)         每条物理边负载
  BW(e)=ℓ(e)·B_port
  n_200G(e)=ℓ(e)
```

---

## 6. 与论文表述的对齐说明

| 论文措辞 | 实现处理 |
| --- | --- |
| “maximum number of logic links between any pair of SSCs” | 按上下文实现为：**物理相邻**边的最大负载（与 floorplan 目标 \(\min C(M_i)\) 及 feedthrough 叙述一致） |
| 重复随机初值取最优 | `trials` × `runs`；默认 200×10 |
| 每逻辑链路 ≥ 200 Gbps | \(B_{port}=200\)；端口粒度图直接标注 \(\ell(e)\) |
| 物理载体为 mesh | 不规则中心对称行宽 mesh，而非严格方阵 |

---

## 7. 复现命令

```bash
# 默认: trials=200, runs=10
python3 algorithm1_pairwise_exchange.py

# 由最优映射出 200G 端口粒度图（已生成）
# best_alg1_200g_ports.png / .svg / .md
```
