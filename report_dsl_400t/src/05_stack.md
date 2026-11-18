# 第 5 章 O1Turn(DR) 细化变种：单 Reticle 3D 堆叠与多平面 NoC {#ch5}

方案四把每颗 die 看成一个交换容量 \((2n+1)B_{die}\) 的大 router（16R 为 {{4|stk|o1t_router_tbps|.1f}}T，64R 为 {{8|stk|o1t_router_tbps|.1f}}T），这在单颗平面 die 上难以实现。本章把它细化为可实现的结构：**每个 Reticle 拆成 3D 堆叠的 NOW die（底层）、SW die（顶层）与 OE die（顶层）**，并把 NoC router 按流水线切成多个互不通信的平面。章内依次给出整体架构思路（5.1）、单 Reticle 多 die 堆叠方案（5.2）、系统架构（5.3）、NoC router 的 bufferless / buffered 实现与平面数 M 的推导（5.4）、各 die 的 floorplan（5.5）与小结（5.6）。

本章沿用你给出的记号：**\(N\) 为单颗 SW die 的流水线数，\(M\) 为单颗 NOW die 的 NoC 平面数**（die 数写作 \(n^2\)）。流水线带宽 \(P\) = {{4|stk|pipe_tbps|g}} Tbps。**每个 Reticle 只有一颗 OE die，其带宽等于 SW die 的线路侧带宽 \(B_{die}\)**（16R {{4|stk|oe_tbps|g}}T，64R {{8|stk|oe_tbps|g}}T），即每个 Reticle 由 NOW、SW、OE 各一颗 die 组成。以 16R 为主线，64R 的对应数值在表中并列。图中的 die 尺寸与模块面积均为示意，不是面积估算结果。

## 5.1 整体架构思路

!fig[fig_stk_idea.png](图 5-1 逻辑交换架构示意：按三级 CLOS 布局展开（16R：16 颗 SW die，N = 8，M = 24；64R：64 颗，N = 2，M = 10）)

**逻辑交换架构（图 5-1）。** 把整颗芯片的交换按三级 CLOS 展开：

- **第一级：SW die 上行交换，共 \(n^2\) 个节点**（16R 为 {{4|stk|N_die|d}} 个，64R 为 {{8|stk|N_die|d}} 个，每个节点即一颗 SW die）。每个节点有 \(N\) 个 3.2T 线路侧 IPP 管道输入、\(M\) 个 3.2T 交换侧管道输出；输入流量被均匀喷洒到 \(M\) 个交换侧管道，第 \(p\) 个管道连第 \(p\) 个 NOC 交换平面。
- **第二级：NOC 交换平面，共 \(M\) 个节点。** 每个平面连接全部第一级与第三级节点（每个 SW die 一个 3.2T 口），可以看作由 NOC 实现的 \(n^2\) 端口 switch；平面之间相互独立、没有链路。
- **第三级：SW die 下行交换，共 \(n^2\) 个节点。** 每个节点有 \(M\) 个 3.2T 交换侧管道输入、\(N\) 个 3.2T 线路侧 EPP 管道输出，并按流重排序。第一级与第三级是同一颗 SW die 的入向与出向（折叠 CLOS）。

平面数为
\[
M=\frac{\text{单边加速比}\times\text{SW 线路侧带宽}\times\text{NOC 加速比}}{\text{单 NOC 平面带宽}}=\frac{(n/2)\cdot B_{die}\cdot(1/\eta)}{P},
\]
其中单边加速比按最坏置换取 \(n/2\)（1.6.3 节），NOC 加速比 \(1/\eta\) 补偿 router 的饱和效率（5.4.1 节）；结果再向上取到 \(N\) 的倍数，即 \(M=kN\)（5.4.2 节）。16R 为 {{4|stk|cfg/worst_buf/M|d}}（\(k\) = {{4|stk|cfg/worst_buf/k|d}}），64R 为 {{8|stk|cfg/worst_buf/M|d}}（\(k\) = {{8|stk|cfg/worst_buf/k|d}}）。

!fig[fig_stk_now_planes.png](图 5-2 n×n 颗 NOW die 上实现 M 个 NOC 交换平面（16R 顶视示意，M = 24）：(a) 全阵列，同颜色为同一平面；(b) 单颗 NOW die 内的平面 router、本地口与四边 SIO)

**物理实现（图 5-2）。** 第二级的 \(M\) 个平面落在 \(n\times n\) 颗 NOW die 上：

- 每颗 NOW die 含 \(M\) 个平面 router 及其走线。平面 \(p\) 的 router 经混合键合向上连本 Reticle SW die 的第 \(p\) 个交换侧口（本地口），经 die 四边的 SIO 连东南西北相邻 NOW die 上平面 \(p\) 的 router；每边每方向 \(M\times3.2\)T。
- \(M\) 个平面之间不相互通信：不同平面的走线在 NOW die 内交叉但不相连，跨平面只发生在 SW die 交换引擎的喷洒与重排序里。
- 图 5-2 中 router 沿对角线排布只为显示各平面走线相互独立，实际位置见图 5-7(a)：router 阵列集中在 SW 交换引擎正下方。

**分层与端到端流程。**

- **按功能分层。** 方案四的单颗 die 同时承担三类功能：晶圆内 die 间互联（四边 SIO 与过路转发）、交换与报文处理、线路侧 I/O。本变种把它们分到三种 die 上：
    - **NOW die（Network-on-Wafer，底层，整 Reticle）**：承载晶圆内互联，包括多平面 NoC router、四边 SIO、SW die 与 OE die 之间的点对点走线，以及给顶层 die 供电的 TSV。
    - **SW die（顶层）**：承载交换逻辑，包括 OE 接口、报文处理（IPP / EPP）、接口处理（TM / 队列）与交换引擎，采用多流水线架构。
    - **OE die（顶层，每个 Reticle 一颗）**：承载外部光互联，带宽等于 SW die 线路侧带宽 \(B_{die}\)，光纤经顶部 FAU 向上扇出。
- **为什么 OE 必须向上出纤。** 在 2D Mesh 晶圆中，内部 Reticle 的四条边都被相邻 Reticle 的 SIO 占用，没有空闲边可以引出光纤。线路侧 I/O 只能垂直离开晶圆面，所以 OE die 叠在 NOW die 上、FAU 向上。
- **流水线数。** 每条流水线 \(P\) = 3.2T（8 × 400GE），所以 \(N=B_{die}/P\)：16R 为 **{{4|stk|N_pipe|d}} 条**，64R 为 **{{8|stk|N_pipe|d}} 条**。全芯片流水线数都是 {{4|stk|pipes_total|d}} 条，与切分方式无关。
- **单颗 OE die 按流水线切片。** OE die 带宽 \(B_{die}=N\cdot P\)，内部分成 \(N\) 个 3.2T 光引擎切片，与 SW die 的 \(N\) 条流水线一一对应：
    - 每个切片 {{4|stk|slice_lanes|d}} 路 200G、{{4|stk|slice_fibres|d}} 芯光纤（收发分纤）；
    - 16R 的 OE die 为 {{4|stk|oe_slices|d}} 个切片、{{4|stk|oe_fibres|d}} 芯光纤、{{4|stk|n_fau|d}} 个 FAU，64R 为 {{8|stk|oe_slices|d}} 个切片、{{8|stk|oe_fibres|d}} 芯、{{8|stk|n_fau|d}} 个 FAU（每个 FAU {{4|stk|fau_fibres|d}} 芯）；
    - SW↔OE 之间只有 \(N\) 组固定的 3.2T 点对点通道，不需要任何交换。
- **交换引擎与多平面 NoC。** 交换引擎有 \(N\) 个线路侧口与 \(M\) 个交换侧口，每口 3.2T：
    - \(N\) 个线路侧口连各流水线的 IPP / EPP；
    - \(M\) 个交换侧口分别连 \(M\) 个 NoC 平面 router 的本地输入 / 输出。
    - 每个平面由全部 Reticle 上同编号的 router 组成，是一张独立的 \(n\times n\) Mesh，平面之间没有链路。
    - 一个报文只在源、宿两端的交换引擎处选择或离开平面，在平面内按方案四的规则转发：顺时针 / 逆时针 O1Turn 各 50%。
- **端到端转发流程。**
    1. 入向：光纤 → OE die 光引擎切片 \(i\) → NOW die 点对点通道 \(i\) → SW die 流水线 \(i\)（OE 接口 → IPP）→ 交换引擎。
    2. 目的在本 Reticle 时，引擎直接送 EPP；否则把报文喷洒到 \(M\) 个平面之一。
    3. 报文经平面 \(p\) 的 router 逐 Reticle 转发到目的 Reticle 平面 \(p\) 的本地口。
    4. 目的端交换引擎按流重排序后送 EPP \(j\)，再经 NOW 点对点通道 \(j\) → OE die 光引擎切片 \(j\) → 光纤。
- **与方案四的关系。**
    - 引擎把每个 Reticle 发往 NoC 的流量均匀喷洒到 \(M\) 个平面，所以每个平面承载的是同一个 die 级流量矩阵的 \(1/M\)。1.6.3 节的结论逐平面成立：任意流量矩阵下，平面内最热边负载都是该平面注入量的 \(n/2\) 倍。
    - 零负载时延沿用方案四的模型（跳数、馈通、转向与 SIO 不变，\(t_{\mathrm{sw\_sw}}=0\)，端到端计一次 \(t_{\mathrm{sw\_die}}\)），单链路最坏为 {{4|stk|lat_link_max|.1f}} ns（16R）/ {{8|stk|lat_link_max|.1f}} ns（64R），另加交换引擎的喷洒 / 重排序时延。
    - 代价集中在两处：router 的饱和效率决定需要多少个平面，平面数又决定 die 边带宽（5.4 节）。

## 5.2 单 Reticle 多 die 堆叠方案

!fig[fig_stk_stack.png](图 5-3 单 Reticle 多 die 堆叠与连接关系（每个 Reticle 一颗 NOW、SW、OE die）：(a) 16R 顶视；(b) 64R 顶视；(c) 沿南北中线的侧切图（纵向放大，尺寸示意）)

- **顶视（图 5-3(a)(b)）。**
    - NOW die 占满整个 Reticle（32 × 25 mm）。
    - 唯一的 OE die 沿北边放置，SW die 紧贴其南侧，两者之间只留约 1 mm 间隙。SW die 的 \(N\) 个流水线切片沿北沿一字排开，各自正对 OE die 上对应的光引擎切片。
    - 16R 的 OE die 与 SW die 同宽（示意 30 mm），64R 的两颗 die 都只需约一半宽度。
    - OE die 顶部贴 {{4|stk|n_fau|d}} 个 FAU（16R）/ {{8|stk|n_fau|d}} 个 FAU（64R），共 {{4|stk|oe_fibres|d}} / {{8|stk|oe_fibres|d}} 芯光纤（{{4|stk|oe_lanes|d}} / {{8|stk|oe_lanes|d}} 路 200G，收发分纤）；全芯片 {{4|stk|fibres_total|,d}} 芯，不含外置光源的输入纤，与切分方式无关。
    - NOW die 四边经晶圆内 SIO 连相邻 Reticle，每边每方向 \(M\times3.2\)T：16R 按最坏置换、buffered 配置为 {{4|stk|cfg/worst_buf/M|d}} × 3.2T = {{4|stk|cfg/worst_buf/edge_tbps|.1f}}T。
- **侧切（图 5-3(c)，左南右北）**，自下而上：
    1. 供电 / 载板：背面供电模块经 NOW die 的 TSV 向上供电。
    2. NOW die：其中有 router 阵列与点对点走线。
    3. 混合键合层。
    4. 顶层的 SW die（南）与 OE die（北）。
    5. OE die 上方是 FAU，光纤垂直向上；冷板覆盖 SW die，只需在北侧为 FAU 开一处窗口。
- **连接关系**见表 5-1。顶层 die 之间没有直接连线，所有电连接都经 NOW die 中转。OE 与 SW 相邻，点对点通道只是 OE 键合 → 跨约 1 mm 间隙 → SW 键合的短线，\(N\) 组通道长度相同。
- **单颗 OE die 的利弊。**
    - 好处：
        - 每个 Reticle 只需贴装三颗 die，键合与已知良品测试的次数少；
        - FAU 集中在一颗 die 上，冷板只需一处开窗；
        - SW↔OE 通道短而等长，SW die 只有北沿承担线路侧 I/O。
    - 代价：
        - 16R 的 OE die 带宽达 {{4|stk|oe_tbps|g}}T、宽度与 SW die 相当，单颗良率与沿长边的热调谐均匀性要求更高；
        - 光子器件只在北侧与发热的 SW die 相邻，需要热隔离；
        - SW die 的北沿长度要容纳 \(N\) 个 3.2T 线路侧接口（16R 按示意宽度 30 mm，每个切片约 3.75 mm）。

!tab 表 5-1 单 Reticle 内的连接关系（每方向带宽）

| 连接 | 物理通道 | 16R | 64R |
|---|---|---:|---:|
| OE die ↔ SW die（线路侧） | OE 键合 ↓ → NOW 点对点短线（跨约 1 mm 间隙）→ 键合 ↑ SW；无交换 | {{4|stk|oe_slices|d}} × 3.2T = {{4|stk|oe_tbps|g}}T | {{8|stk|oe_slices|d}} × 3.2T = {{8|stk|oe_tbps|g}}T |
| SW die ↔ NoC router（交换侧） | SW 交换引擎正下方的混合键合，直连各平面 router 本地口 | {{4|stk|cfg/worst_buf/M|d}} × 3.2T（buffered） | {{8|stk|cfg/worst_buf/M|d}} × 3.2T（buffered） |
| router ↔ 相邻 Reticle | NOW 内走线到四边 SIO PHY，跨 Reticle 拼接 | 每边 {{4|stk|cfg/worst_buf/edge_tbps|.1f}}T | 每边 {{8|stk|cfg/worst_buf/edge_tbps|.1f}}T |
| 外部光互联 | OE die → FAU → 光纤向上 | {{4|stk|fibres_die|d}} 芯（{{4|stk|n_fau|d}} 个 FAU） | {{8|stk|fibres_die|d}} 芯（{{8|stk|n_fau|d}} 个 FAU） |
| 供电 | 载板 → NOW TSV → 顶层 die | — | — |

## 5.3 系统架构

### 5.3.1 各 die 的逻辑模块与连接

!fig[fig_stk_arch.png](图 5-4 各 die 的逻辑模块与连接关系（16R，按最坏置换 buffered 配置）)

- **OE die**（每个 Reticle 一颗，{{4|stk|oe_tbps|g}}T）：{{4|stk|oe_slices|d}} 个 3.2T 光引擎切片，每个切片包括：
    - 光栅耦合阵列（上方为 FAU）；
    - MRM 调制器阵列与 PD 探测器阵列；
    - Driver / TIA；
    - 朝下的电接口（经混合键合到 NOW die，收发各 3.2T）。
    - 全片共用热调谐控制。各切片之间没有数据交互。
- **SW die**：{{4|stk|N_pipe|d}} 个流水线切片加一个交换引擎。
    - 每个切片依次为 OE 接口（PCS / FEC / MAC）→ IPP（解析 / 查表 / ACL）→ EPP（编辑 / 调度）→ 接口处理（TM / 队列）。
    - 交换引擎有 \(N\) = {{4|stk|N_pipe|d}} 个线路侧口与 \(M\) = {{4|stk|cfg/worst_buf/M|d}} 个交换侧口，负责：
        - 本 Reticle 内交换（线路侧到线路侧）；
        - 入向喷洒（均匀分到 \(M\) 个平面）；
        - 出向按流重排序；
        - 共享缓冲。
- **NOW die**：
    - SW↔OE 点对点通道（{{4|stk|N_pipe|d}} 组 × 3.2T，无交换）；
    - \(M\) 个 5 口平面 router；
    - 四边 SIO PHY；
    - 供电 TSV、时钟与控制。
    - NOW die 只做转发和走线，不做报文处理，所以它的工艺与良率要求可以与 SW die 解耦。

### 5.3.2 多平面 NoC router

!fig[fig_stk_planes.png](图 5-5 多平面 NoC router：(a) M 个互不连通的平面（每个平面是全部 Reticle 上同编号 router 组成的 Mesh）；(b) 交换引擎端口分组与单平面 router)

- **平面的定义。** 平面 \(p\) 由 \(n^2\) 颗 NOW die 上编号为 \(p\) 的 router 组成，构成一张 \(n\times n\) Mesh。每个 router 有 5 个口（本地 + 东南西北），每口 3.2T。本地口连该 Reticle 交换引擎的第 \(p\) 个交换侧口。平面之间没有链路，跨平面只发生在源 / 宿两端的交换引擎里。
- **交换侧口分组。** 交换侧 \(M=kN\) 个口分为 \(k\) 组、每组 \(N\) 个（图 5-5(b)）。第 \(g\) 组的第 \(i\) 个口落在流水线切片 \(i\) 的下方（图 5-7 中 router 阵列按列与流水线切片对齐），所以引擎可以由 \(N\) 个同构切片拼成。为什么 \(M\) 必须是 \(N\) 的倍数，见 5.4.2 节。
- **平面内路由与死锁。** 平面内按顺 / 逆时针 O1Turn 各 50% 转发，两类路径合起来用到全部 8 种转弯：
    - buffered 实现需要两个虚网络（XY 序与 YX 序各一个）防死锁；
    - bufferless 偏转路由不会阻塞，因此不会死锁，但需要年龄优先等机制防活锁。
- **切平面换来的是交叉开关规模。** 方案四的单个大 router 有 5 个口、合计 {{4|stk|o1t_router_tbps|.1f}}T。本变种是 \(M\) 个 5 × 5、每口 3.2T 的小 router。按矩阵交叉开关面积 ∝（端口数 × 位宽）² 粗估，16R buffered 配置的交叉开关总规模是单个大 router 的 1/{{4|stk|cfg/worst_buf/xbar_ratio|.1f}}，64R 是 1/{{8|stk|cfg/worst_buf/xbar_ratio|.1f}}。此外每个平面 router 的仲裁、缓冲与布线都只服务一条 3.2T 通道，可以按 tile 复制。

## 5.4 NoC router 实现：bufferless 与 buffered，及平面数 M 的推导

### 5.4.1 注入率与两类 router 的典型饱和点

- **注入率 \(\lambda\)。** 定义为每个 router 本地口每周期注入的 flit 数，归一化到端口宽度 \(P\)；\(\lambda=1\) 表示本地口满速注入。
- **理想容量 \(\rho^*\)。** 记 \(\gamma\) 为单位注入下平面内的最热边负载：
    - 最坏置换（无阻塞口径）\(\gamma=n/2\)（1.6.3 节）；
    - AllToAll 为 \(n/4\)（实测 16R {{4|stk|cfg/a2a_ideal/gamma|g}}、64R {{8|stk|cfg/a2a_ideal/gamma|g}}）。
    - 链路宽度与本地口相同，所以理想的最大可持续注入率为 \(\rho^*=\min(1,1/\gamma)\)：最坏置换 16R {{4|stk|cfg/worst_ideal/rho_star|g}}、64R {{8|stk|cfg/worst_ideal/rho_star|g}}；AllToAll 16R {{4|stk|cfg/a2a_ideal/rho_star|g}}、64R {{8|stk|cfg/a2a_ideal/rho_star|g}}。
- **饱和效率 \(\eta\)。** 实际 router 在注入率达到理想容量前就会饱和：时延陡升、吞吐不再增长。记可持续注入率 \(\rho_{sat}=\eta\rho^*\)。公开文献中，8×8 Mesh 均匀随机流量的理想容量为 0.5 flit/节点/周期，两类 router 的典型量级如下：
    - **buffered**（输入缓冲 + 虚通道 + 信用流控）：饱和注入率约 0.35～0.45，即 \(\eta\approx\) {{4|stk|eta_buf_lo|g}}～{{4|stk|eta_buf_hi|g}}。饱和前时延基本平稳，代价是输入缓冲与虚通道仲裁。
    - **bufferless**（偏转路由，如 BLESS / CHIPPER / MinBD 一类）：冲突时把 flit 偏转到空闲输出口，饱和注入率约 0.25～0.35，即 \(\eta\approx\) {{4|stk|eta_bl_lo|g}}～{{4|stk|eta_bl_hi|g}}。低负载每跳只需 1～2 个周期，但随负载上升偏转率迅速增加：平均跳数与时延抖动变大，乱序窗口也变大。
- 本章取 **buffered \(\eta\) = {{4|stk|cfg/worst_buf/eta|g}}、bufferless \(\eta\) = {{4|stk|cfg/worst_bl/eta|g}}**（bufferless 取区间下沿）。这些值只用于确定平面数，实际取值需要按 router 微架构做 cycle 级仿真校准。图 5-6 给出 \(\eta\) 在 0.3～1 之间变化时的结果。

### 5.4.2 推导：M 是 N 的倍数

**(1) 喷洒使每个平面的注入率为 \(N/M\)。** 一个 Reticle 发往 NoC 的流量不超过 \(N P\)，交换引擎按包把它均匀喷洒到 \(M\) 个平面。每个平面在该 Reticle 的本地注入不超过 \(NP/M\)。宿端同理：一个 Reticle 收到的流量不超过 \(NP\)，均匀来自 \(M\) 个平面，每个平面的本地弹出也不超过 \(NP/M\)。平面端口宽度为 \(P\)，所以
\[
\lambda=\frac{NP}{M\,P}=\frac{N}{M}.
\]

**(2) 流水线同构要求 \(M\) 是 \(N\) 的倍数。** 每个平面 router 的本地口宽度等于一条流水线（3.2T），交换引擎按流水线切成 \(N\) 个同构切片，每个切片承担同样多的交换侧口及其正下方的键合区与 router 列。设每个切片 \(k\) 个口，则 \(M=kN\)、\(\lambda=1/k\)。如果 \(M\) 不是 \(N\) 的倍数，各切片的交换侧口数不等，喷洒权重与切片的物理实现都不再同构。

**(3) 注入率约束决定 \(k\)。** 要求 \(\lambda\le\rho_{sat}\)，即 \(1/k\le\eta\min(1,1/\gamma)\)，于是
\[
M=kN,\qquad k=\left\lceil\frac{\max(1,\gamma)}{\eta}\right\rceil,\qquad \text{最坏置换下 }k=\left\lceil\frac{n}{2\eta}\right\rceil .
\]

**(4) 理想情况与方案四一致。** \(\eta=1\) 且按最坏置换时 \(k=n/2\)，die 边带宽 \(M P=(n/2)NP=(n/2)B_{die}\)，恰为方案四的无阻塞单边带宽：16R 为 {{4|stk|cfg/worst_ideal/M|d}} × 3.2T = {{4|stk|cfg/worst_ideal/edge_tbps|.1f}}T，64R 为 {{8|stk|cfg/worst_ideal/M|d}} × 3.2T = {{8|stk|cfg/worst_ideal/edge_tbps|.1f}}T。切平面本身不增加带宽；实际 router 的饱和效率 \(1/\eta\) 才是额外代价，取整后体现为 \(k\) 的增加。

!tab 表 5-2 平面数 M 的推导结果

<!-- TAB:stk_k:0 -->

!fig[fig_stk_inj.png](图 5-6 单平面注入率约束下的平面数与 die 边带宽：(a) 每条流水线平面数 k；(b) 每条 die 边单方向带宽 M × 3.2T（○ buffered 取值，□ bufferless 取值）)

- **16R（N = {{4|stk|N_pipe|d}}），最坏置换（无阻塞）：**
    - buffered：\(k\) = {{4|stk|cfg/worst_buf/k|d}}，**\(M\) = {{4|stk|cfg/worst_buf/M|d}}**，die 边 {{4|stk|cfg/worst_buf/edge_tbps|.1f}}T，比方案四 {{4|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}}；
    - bufferless：\(k\) = {{4|stk|cfg/worst_bl/k|d}}，**\(M\) = {{4|stk|cfg/worst_bl/M|d}}**，die 边 {{4|stk|cfg/worst_bl/edge_tbps|.1f}}T，比方案四 {{4|stk|cfg/worst_bl/edge_vs_o1t|+.0f%}}。
    - 若只按 AllToAll 设计，两种实现都是 \(k\) = {{4|stk|cfg/a2a_buf/k|d}}、\(M\) = {{4|stk|cfg/a2a_buf/M|d}}：16R 的 AllToAll 受本地口限制（\(\rho^*=1\)），\(\eta<1\) 时 \(k\) 只需从 {{4|stk|cfg/a2a_ideal/k|d}} 加到 {{4|stk|cfg/a2a_buf/k|d}}。
- **64R（N = {{8|stk|N_pipe|d}}），最坏置换：**
    - buffered：\(k\) = {{8|stk|cfg/worst_buf/k|d}}，\(M\) = {{8|stk|cfg/worst_buf/M|d}}，die 边 {{8|stk|cfg/worst_buf/edge_tbps|.1f}}T（{{8|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}}）；
    - bufferless：\(k\) = {{8|stk|cfg/worst_bl/k|d}}，\(M\) = {{8|stk|cfg/worst_bl/M|d}}，die 边 {{8|stk|cfg/worst_bl/edge_tbps|.1f}}T（{{8|stk|cfg/worst_bl/edge_vs_o1t|+.0f%}}）。
    - 64R 的 \(\gamma=n/2\) 更大，\(k\) 对 \(\eta\) 更敏感（图 5-6(a) 的实线红色阶梯更密）。
- **饱和余量。** 表 5-2 中 \(\lambda=\rho_{sat}\) 的配置正好工作在饱和点，例如 16R bufferless 最坏置换 \(\lambda\) = {{4|stk|cfg/worst_bl/lam|g}} = \(\rho_{sat}\)、64R buffered 最坏置换 \(\lambda\) = {{8|stk|cfg/worst_buf/lam|g}} = \(\rho_{sat}\)。工程上需要留余量时，应把 \(k\) 再加 1。
- **为什么不把单平面加宽。** 若平面端口宽度 \(w\ne P\)，一般式为 \(M=kN\cdot P/w\)。按你给出的 “一个平面服务一条 3.2T 流水线”（\(w=P\)）时，倍数关系最直接，平面 router 也与流水线切片一一对齐。

### 5.4.3 bufferless 与 buffered 的代价对比

!tab 表 5-3 bufferless 与 buffered NoC 的代价（最坏置换配置）

| 维度 | buffered | bufferless（偏转） |
|---|---|---|
| 平面数 M（16R / 64R） | {{4|stk|cfg/worst_buf/M|d}} / {{8|stk|cfg/worst_buf/M|d}} | {{4|stk|cfg/worst_bl/M|d}} / {{8|stk|cfg/worst_bl/M|d}} |
| die 边单方向带宽（16R / 64R） | {{4|stk|cfg/worst_buf/edge_tbps|.1f}}T / {{8|stk|cfg/worst_buf/edge_tbps|.1f}}T | {{4|stk|cfg/worst_bl/edge_tbps|.1f}}T / {{8|stk|cfg/worst_bl/edge_tbps|.1f}}T |
| SIO 静态功耗（按配置带宽，16R / 64R） | {{4|stk|cfg/worst_buf/sio_static_W|,.0f}} W / {{8|stk|cfg/worst_buf/sio_static_W|,.0f}} W | {{4|stk|cfg/worst_bl/sio_static_W|,.0f}} W / {{8|stk|cfg/worst_bl/sio_static_W|,.0f}} W |
| router 存储 | 每个 mesh 输入口覆盖信用往返（一跳 SIO + 走线 + 缝隙的往返，router 转发按时延模型不计）：{{4|stk|rtt_ns|.0f}} ns × 3.2T ≈ {{4|stk|buf_port_kb|.1f}} KB；每颗 NOW die {{4|stk|cfg/worst_buf/buf_now_mb|.2f}} MB（16R）/ {{8|stk|cfg/worst_buf/buf_now_mb|.2f}} MB（64R） | 无输入缓冲，仅流水寄存器 |
| 零负载每跳时延 | 缓冲写读 + 虚通道 / 交叉开关仲裁，3～4 周期 | 1～2 周期 |
| 高负载行为 | 饱和前时延平稳，之后排队时延陡升 | 偏转率上升，跳数与时延抖动增大，可持续注入率更低 |
| 保序 | O1Turn 双路径与跨平面喷洒已需目的端重排序 | 偏转使乱序窗口更大，重排序缓冲更大 |
| 死锁 / 活锁 | 顺 / 逆时针共用 8 种转弯，需 2 个虚网络 | 无死锁（不阻塞）；需年龄优先等防活锁 |
| 流控 | 信用流控，需反压通道 | 无反压；只有在有空闲输出口时才允许注入 |

- **SIO 带宽与静态功耗。** SIO 的 70% 功耗为静态，与配置带宽成正比。按全部 {{4|stk|n_dir_edges|d}} 条（16R）/ {{8|stk|n_dir_edges|d}} 条（64R）有向边计，方案四无阻塞配置为 {{4|stk|o1t_sio_static_W|,.0f}} W / {{8|stk|o1t_sio_static_W|,.0f}} W；buffered 变种增加到 {{4|stk|cfg/worst_buf/sio_static_W|,.0f}} W / {{8|stk|cfg/worst_buf/sio_static_W|,.0f}} W，bufferless 再增加到 {{4|stk|cfg/worst_bl/sio_static_W|,.0f}} W / {{8|stk|cfg/worst_bl/sio_static_W|,.0f}} W。bufferless 省下的是 NOW die 上的 SRAM 与虚通道逻辑，多付出的是平面数、SIO 带宽与功耗。
- **取舍。** buffered 的输入缓冲在 NOW die 上只有 MB 量级（16R 约 {{4|stk|cfg/worst_buf/buf_now_mb|.1f}} MB），而 bufferless 的 die 边带宽比 buffered 多 {{4|stk|bl_vs_buf_edge|.0f%}}（16R；64R 多 {{8|stk|bl_vs_buf_edge|.0f%}}），所以按无阻塞设计时 **buffered 更合适**。bufferless 适合按 AllToAll 等典型流量设计、或 SIO 带宽有富余的情形（16R AllToAll 下两者 \(M\) 相同），也可以把两者结合：低负载走 bufferless 快速通道，只在冲突时进入小缓冲（最小缓冲偏转类设计）。

## 5.5 各 die 的 floorplan

!fig[fig_stk_floor.png](图 5-7 各 die floorplan 示意（16R，最坏置换 buffered 配置）：(a) NOW die；(b) OE die（北）；(c) SW die（南）)

- **NOW die（图 5-7(a)）**：
    - 四边是 SIO PHY 条带（每边 {{4|stk|cfg/worst_buf/M|d}} × 3.2T / 方向）。
    - 北部正对 OE die 的是 {{4|stk|oe_slices|d}} 个 OE 切片键合区。紧邻其南的一条窄带是 SW↔OE 点对点通道：从 OE 键合跨约 1 mm 间隙到 SW 线路侧键合，只有数 mm 走线。
    - 南部正对 SW 交换引擎的是 router 阵列：{{4|stk|cfg/worst_buf/k|d}} 行（组）× {{4|stk|N_pipe|d}} 列，共 {{4|stk|cfg/worst_buf/M|d}} 个平面 router。
    - 中间区域是 router 到四边 SIO 的走线 / 中继（即方案四中的馈通走线）与供电 TSV 网格。
- **OE die（图 5-7(b)）**：
    - {{4|stk|oe_slices|d}} 个光引擎切片自西向东排开，每个切片自南向北为 Driver / TIA → MRM / PD → 光栅耦合区。
    - {{4|stk|n_fau|d}} 个 FAU 各覆盖两个切片的耦合区；南沿是朝 SW die 一侧的电接口条带，北沿是热调谐 / 控制。
- **SW die（图 5-7(c)）**：
    - 北半部是 {{4|stk|N_pipe|d}} 个流水线切片，一字排开，与 OE 切片逐一对齐。每个切片自北向南为 OE 接口 / MAC → IPP → EPP → TM / 队列。
    - 南半部是交换引擎，正下方即 NOW die 的 router 阵列，\(M\) 个交换侧口经混合键合垂直直连各平面 router 的本地口，不需要横向长线。
    - 线路侧（北）与交换侧（南）在 SW die 上南北分离，数据流方向为：OE → 流水线 → 引擎 → NoC。
- **单 Reticle 关键量**见表 5-4。混合键合按 {{4|stk|hb_pitch_um|g}} µm 间距、{{4|stk|hb_gbps|g}} Gbps/pin、50% 信号估算，SW die 收发合计只需 {{4|stk|cfg/worst_buf/hb_sw_mm2|.1f}} mm²（16R），OE die 只需 {{4|stk|hb_oe_mm2|.2f}} mm²。垂直带宽不是瓶颈，瓶颈在 die 边 SIO：16R buffered 为 {{4|stk|cfg/worst_buf/dens_25|.2f}} T/mm（25 mm 边，单方向）。

!tab 表 5-4 单 Reticle 关键量（3D 堆叠变种）

<!-- TAB:stk_die:0 -->

## 5.6 小结

> 【结论】
>
> 1. **三层分工，每个 Reticle 三颗 die。** NOW die 负责晶圆内互联与供电，SW die 负责多流水线交换，唯一一颗 OE die（带宽 = SW 线路侧带宽，{{4|stk|oe_tbps|g}}T / {{8|stk|oe_tbps|g}}T）负责垂直出纤。内部 Reticle 四边都被 SIO 占用，光 I/O 只能经 FAU 向上。OE 按流水线分 \(N\) 个光引擎切片，沿北边紧贴 SW die，SW↔OE 是 \(N\) 组跨约 1 mm 间隙的等长点对点短线；代价是大 OE die 的良率与热隔离。
> 2. **流水线数。** 每条流水线 3.2T 时，SW die 流水线数 \(N=B_{die}/3.2\mathrm T\)：16R 为 {{4|stk|N_pipe|d}}，64R 为 {{8|stk|N_pipe|d}}；全芯片 {{4|stk|pipes_total|d}} 条。
> 3. **平面数。** 交换引擎把流量均匀喷洒到 \(M\) 个互不通信的平面，单平面注入率 \(\lambda=N/M\)。流水线同构要求 \(M=kN\)，注入率约束给出 \(k=\lceil\max(1,\gamma)/\eta\rceil\)，最坏置换下 \(k=\lceil n/(2\eta)\rceil\)。\(\eta=1\) 时恰好还原方案四的 \((n/2)B_{die}\)。
> 4. **实现取舍。** 按无阻塞设计时，buffered 取 \(k\) = {{4|stk|cfg/worst_buf/k|d}} / {{8|stk|cfg/worst_buf/k|d}}（\(M\) = {{4|stk|cfg/worst_buf/M|d}} / {{8|stk|cfg/worst_buf/M|d}}，die 边 {{4|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}} / {{8|stk|cfg/worst_buf/edge_vs_o1t|+.0f%}}），每颗 NOW die 需约 {{4|stk|cfg/worst_buf/buf_now_mb|.1f}} MB 输入缓冲与 2 个虚网络；bufferless 取 \(k\) = {{4|stk|cfg/worst_bl/k|d}} / {{8|stk|cfg/worst_bl/k|d}}（\(M\) = {{4|stk|cfg/worst_bl/M|d}} / {{8|stk|cfg/worst_bl/M|d}}，die 边翻倍），省去缓冲与虚网络，但 SIO 带宽与静态功耗更高、乱序更重。16R 推荐 buffered；只按 AllToAll 设计时两者都是 \(M\) = {{4|stk|cfg/a2a_buf/M|d}}。
> 5. **待评估项。** \(\eta\) 需按 router 微架构做 cycle 级仿真校准；交换引擎喷洒 / 重排序的缓冲与时延、NOW die 上 SIO PHY 的线密度（16R buffered {{4|stk|cfg/worst_buf/dens_25|.2f}} T/mm）、OE die 与 FAU 的散热避让，是该变种落地前需要细化的部分。
