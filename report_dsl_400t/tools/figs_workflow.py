#!/usr/bin/env python3
"""构型分析 workflow 附图与统计：逻辑交换拓扑、die 顶层架构、物理构型（die 间有向边带宽）。

输出：
  figs/fig_logic_{clos,s3,o1t}_{n}x{n}.png
  figs/fig_die_{xy_o1turn_cw,manhattan,s3_10,o1t}_{n}x{n}.png
  figs/fig_phys_{xy_o1turn_cw,manhattan,s3_10,o1t}_{n}x{n}.png
  data/workflow_{n}x{n}.json（每 die SIO 方向带宽、馈通吞吐、交换容量等，供正文引用）
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT_WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_WS))
import dsl_mesh_400t as M  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figs"
DATA = ROOT / "data"
FIG.mkdir(exist_ok=True)

for _f in ("/System/Library/Fonts/STHeiti Medium.ttc", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(_f):
        font_manager.fontManager.addfont(_f)
plt.rcParams["font.family"] = ["Heiti SC", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

SCHEMES = ("xy_o1turn_cw", "manhattan", "s3_10", "o1t")
TITLE = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由",
         "s3_10": "方案三 DSL+直连 x=10%", "o1t": "方案四 O1Turn(DR)"}
C_SW, C_LINK, C_DIR, C_FT, C_LINE = "#dbe7f4", "#2a6f97", "#e07a1f", "#bc4749", "#6a994e"
DIRS = ("N", "E", "S", "W")
DIR_CN = {"N": "北", "E": "东", "S": "南", "W": "西"}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}


# ------------------------------------------------------------------ data


def parse_edge(k: str):
    a, b = k.split("->")
    return tuple(map(int, a.split(","))), tuple(map(int, b.split(",")))


def edge_dir(a, b) -> str:
    if a[0] == b[0]:
        return "E" if b[1] > a[1] else "W"
    return "S" if b[0] > a[0] else "N"


def parse_path_key(k: str):
    parts = k.split("|")
    return tuple(map(int, parts[-2].split(","))), tuple(map(int, parts[-1].split(",")))


def scheme_record(n: int, sc: str) -> dict:
    """返回统一结构：loads（有向边→Tbps）、paths（列表，每条带速率 Tbps）及原始记录。"""
    if sc == "o1t":
        r = json.loads((DATA / f"dsl_o1t_{n}x{n}.json").read_text())
        B = r["die_bw_tbps"]
        loads = {k: v * B for k, v in r["worst_load"].items()}
        a2a = {k: v * r["b_tbps"] for k, v in r["a2a_load"].items()}
        sp = r["split"]
        paths = [(p, sp * r["b_tbps"]) for p in r["paths"].values()]
        paths += [(p, (1 - sp) * r["b_tbps"]) for p in r["paths_ccw"].values()]
        return dict(raw=r, loads=loads, a2a=a2a, paths=paths, vmax=r["C_tbps"], b=r["b_tbps"])
    base = json.loads((DATA / f"dsl_{n}x{n}.json").read_text())
    if sc.startswith("s3_"):
        r = json.loads((DATA / f"dsl_l1l3_{n}x{n}.json").read_text())[sc.split("_")[1]]
        man = base["manhattan"]
        b = r["b_tbps"]
        paths = [(p, b) for p in man["paths"].values()] + [(d["path"], b) for d in r["directs"]]
        loads = {k: v * b for k, v in r["loads"].items()}
        return dict(raw=r, loads=loads, a2a=loads, paths=paths, vmax=r["C_tbps"], b=b)
    r = base[sc]
    b = r["b_tbps"]
    loads = {k: v * b for k, v in r["loads"].items()}
    return dict(raw=r, loads=loads, a2a=loads, paths=[(p, b) for p in r["paths"].values()],
                vmax=r["C_tbps"], b=b)


def die_stats(n: int, sc: str, rec: dict) -> dict:
    """同构 die 需求：每方向 SIO 出 / 入（全阵列最大）、单 die 馈通吞吐、D2D 总量。"""
    N = n * n
    B = M.SYSTEM_TBPS / N
    out_dir = {d: 0.0 for d in DIRS}
    die_out = defaultdict(float)
    die_in = defaultdict(float)
    for k, t in rec["loads"].items():
        a, b = parse_edge(k)
        d = edge_dir(a, b)
        out_dir[d] = max(out_dir[d], t)
        die_out[a] += t
        die_in[b] += t
    in_dir = {d: out_dir[OPP[d]] for d in DIRS}
    ft = defaultdict(float)
    for p, rate in rec["paths"]:
        for v in p[1:-1]:
            ft[tuple(v)] += rate
    ft_vals = [ft.get((r, c), 0.0) for r in range(n) for c in range(n)]
    loads = list(rec["loads"].values())
    s = dict(
        N=N, B=B, b=rec["b"],
        sio_out={d: out_dir[d] for d in DIRS}, sio_in=in_dir,
        sio_side_max=max(out_dir.values()),
        sio_ports_b=int(round(max(out_dir.values()) / rec["b"])),  # 映射粒度：每端口 = 1 条逻辑链路 b
        sio_lanes400=round(max(out_dir.values()) / 0.4),
        die_d2d_out_max=max(die_out.values()), die_d2d_out_mean=sum(die_out.values()) / N,
        ft_max=max(ft_vals), ft_mean=sum(ft_vals) / N,
        n_edges=len(loads), edge_max=max(loads), edge_mean=sum(loads) / len(loads), edge_min=min(loads),
        n_hot=sum(1 for v in loads if abs(v - max(loads)) < 1e-9), total_d2d=sum(loads),
    )
    raw = rec["raw"]
    if sc == "o1t":
        s["router"] = (1 + 4 * raw["C_die"]) * B
        s["side_bw"] = raw["C_die"] * B
        s["a2a_edge_max"] = max(rec["a2a"].values())
        s["a2a_ft_max"] = s["ft_max"]
    else:
        add1 = 0.4 * raw.get("l1_ports_added_max_per_sw_incl_local", 0)
        add3 = 0.4 * raw.get("l3_ports_added_max_per_sw_incl_local", 0)
        s["L1"], s["L2"], s["L3"] = B + add1, B, B + add3
        s["L1_add"], s["L3_add"] = add1, add3
        s["die_sw"] = s["L1"] + s["L2"] + s["L3"]
        s["uplink"] = B  # L1→全部 L2：N·b
        s["uplink_local"] = rec["b"]
        s["uplink_remote"] = B - rec["b"]
    return s


def o1t_scenarios(n: int, ew: float = 0.1, with_load: bool = False) -> dict:
    """O1Turn(DR) 最佳 / 最差置换与 AllToAll：激活路径、边负载、走线与时延（指派口径同 dsl_o1turn_noc）。"""
    import numpy as np
    from scipy.optimize import linear_sum_assignment

    mesh = M.build_mesh(n)
    pos = mesh.positions
    N = mesh.n
    B = M.SYSTEM_TBPS / N
    idx = {p: i for i, p in enumerate(pos)}
    paths = {(s, d): M.route_o1turn_cw(s, d) for s in pos for d in pos if s != d}
    paths_ccw = {k: M.route_o1turn_cw(*k, clockwise=False) for k in paths}
    met = {k: M.path_metrics(p, t_sw=M.T_SW_SW_O1T) for k, p in paths.items()}
    Wbest = np.full((N, N), 1e18)
    Wworst = np.zeros((N, N))
    for (s, d), m in met.items():
        e = M.energy_pj(m, ew)
        Wbest[idx[s], idx[d]] = e
        Wworst[idx[s], idx[d]] = e
    out = {}
    for key, W, mx in (("perm_best", Wbest, False), ("perm_worst", Wworst, True)):
        ri, ci = linear_sum_assignment(W, maximize=mx)
        flows = [(pos[i], pos[j]) for i, j in zip(ri, ci) if i != j]
        load = defaultdict(float)
        for f in flows:
            for p in (paths[f], paths_ccw[f]):
                for e in M.path_edges(p):
                    load[e] += B / 2
        ms = [met[f] for f in flows]
        out[key] = dict(
            n_paths=len(flows), n_routes=len({tuple(paths[f]) for f in flows} | {tuple(paths_ccw[f]) for f in flows}),
            hops_mean=sum(m["hops"] for m in ms) / len(ms),
            hops_max=max(m["hops"] for m in ms), wire_mean=sum(m["ft_mean"] for m in ms) / len(ms),
            lat_max=max(m["lat_max"] for m in ms), lat_min=min(m["lat_max"] for m in ms),
            lat_mean=sum(m["lat_max"] for m in ms) / len(ms),
            edge_max=max(load.values()) if load else 0.0, n_edges_used=len(load),
            example=" ; ".join(f"die {a[0] * n + a[1]}→die {b[0] * n + b[1]}" for a, b in flows[:4]),
        )
        if with_load:
            out[key]["load"] = {f"{a[0]},{a[1]}->{b[0]},{b[1]}": v for (a, b), v in load.items()}
    return out


# ------------------------------------------------------------------ logic topology


def _shown(N: int, k: int = 8):
    if N <= k:
        return list(range(N)), None
    h = k // 2
    return list(range(h)) + list(range(N - h, N)), h  # 省略号位于第 h 个后


def fig_logic_clos(n: int, sc: str, st: dict, rec: dict | None = None):
    N, B, b = st["N"], st["B"], st["b"]
    idx, gap = _shown(N, 8 if N > 16 else 16)
    k = len(idx)
    fig, ax = plt.subplots(figsize=(12.5, 7.4 if N <= 16 else 6.6))
    ax.axis("off")
    ys = [k - 1 - i for i in range(k)]
    if gap is not None:
        ys = [(k - i) if i < gap else (k - 1 - i) for i in range(k)]
    xs = {"L1": 2.0, "L2": 6.0, "L3": 10.0}
    bw, bh = 1.25, 0.62
    # 全互联连线
    for x0, x1 in (("L1", "L2"), ("L2", "L3")):
        for y0 in ys:
            for y1 in ys:
                ax.plot([xs[x0] + bw / 2, xs[x1] - bw / 2], [y0, y1], color=C_LINK, lw=0.35, alpha=0.35, zorder=1)
    # 直连（方案三）
    hl = None
    if rec is not None:
        pos = {i: j for j, i in enumerate(idx)}
        cnt = defaultdict(int)
        for d in rec["raw"]["directs"]:
            i = d["i"][0] * n + d["i"][1]
            if i in pos:
                cnt[i] += 1
        hl = max(cnt, key=cnt.get)  # 只示意直连最多的一个 L1，避免全量连线遮挡
        n_drawn = 0
        for d in rec["raw"]["directs"]:
            i = d["i"][0] * n + d["i"][1]
            kk = d["k"][0] * n + d["k"][1]
            if i == hl and kk in pos:
                n_drawn += 1
                ax.annotate("", xy=(xs["L3"] - bw / 2, ys[pos[kk]]), xytext=(xs["L1"] + bw / 2, ys[pos[i]]),
                            arrowprops=dict(arrowstyle="->", color=C_DIR, lw=1.1, ls="--",
                                            connectionstyle="arc3,rad=-0.12"), zorder=5)
        j = pos[hl]
        ax.annotate("", xy=(xs["L3"] - bw / 2, ys[j]), xytext=(xs["L1"] + bw / 2, ys[j]),
                    arrowprops=dict(arrowstyle="->", color=C_DIR, lw=1.4), zorder=5)
    for name, x in xs.items():
        cap = st[name]
        for j, i in enumerate(idx):
            ax.add_patch(FancyBboxPatch((x - bw / 2, ys[j] - bh / 2), bw, bh, boxstyle="round,pad=0.02",
                                        fc=C_SW, ec="#1F3B5C", lw=0.9, zorder=3))
            ax.text(x, ys[j], f"{name}$_{{{i}}}$", ha="center", va="center", fontsize=7.5 if N <= 16 else 8, zorder=4)
        if gap is not None:
            ax.text(x, (ys[gap - 1] + ys[gap]) / 2, "⋮", ha="center", va="center", fontsize=16)
        top = max(ys) + 0.9
        ax.text(x, top, f"{name} × {N}\n每个 {cap:.1f}T", ha="center", va="bottom", fontsize=10, fontweight="bold")
    # 线路侧
    for j in range(k):
        ax.annotate("", xy=(xs["L1"] - bw / 2, ys[j]), xytext=(xs["L1"] - bw / 2 - 0.7, ys[j]),
                    arrowprops=dict(arrowstyle="->", color=C_LINE, lw=0.8))
        ax.annotate("", xy=(xs["L3"] + bw / 2 + 0.7, ys[j]), xytext=(xs["L3"] + bw / 2, ys[j]),
                    arrowprops=dict(arrowstyle="->", color=C_LINE, lw=0.8))
    ports = round(B / 0.4)
    ax.text(xs["L1"] - bw / 2 - 0.8, min(ys) - 1.0, f"入口 {ports}×400GE\n= {B:g}T / L1", ha="center",
            va="top", fontsize=8.5, color=C_LINE)
    ax.text(xs["L3"] + bw / 2 + 0.8, min(ys) - 1.0, f"出口 {ports}×400GE\n= {B:g}T / L3", ha="center",
            va="top", fontsize=8.5, color=C_LINE)
    ax.text(4.0, min(ys) - 1.0, f"L1→L2 全互联：{N}×{N} 条\n每条 b = {b:g}T\n每 L1 上行 N·b = {B:g}T",
            ha="center", va="top", fontsize=8.5, color=C_LINK)
    ax.text(8.0, min(ys) - 1.0, f"L2→L3 全互联：{N}×{N} 条\n每条 b = {b:g}T\n每 L2 下行 N·b = {B:g}T",
            ha="center", va="top", fontsize=8.5, color=C_LINK)
    if rec is not None:
        r = rec["raw"]
        ax.text(6.0, max(ys) + 2.3,
                f"橙色：L1→L3 直连，共 {r['n_directs']} 条 die 间 × {b:g}T（x={r['x_pct']:g}%）+ {r['local_directs']} 条本 die；"
                f"图中仅示意 L1$_{{{hl}}}$（共 {cnt[hl]} 条，画出落在示意 L3 内的 {n_drawn} 条；实线为本 die）；"
                f"单 L1 最多新增 {st['L1_add']:.1f}T 输出端口",
                ha="center", fontsize=9, color=C_DIR)
    ax.set_xlim(-0.5, 12.5)
    ax.set_ylim(min(ys) - 2.8, max(ys) + 2.8)
    name = "共址 CLOS" if rec is None else "共址 CLOS + L1→L3 直连"
    ax.set_title(f"逻辑交换拓扑：{name}({N},{N},{N})（{n}×{n} / {N}R）"
                 + ("" if gap is None else f"，仅示意 {k}/{N} 个 switch"), fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_logic_{'clos' if rec is None else 's3'}_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_logic_o1t(n: int, st: dict):
    B = st["B"]
    fig, ax = plt.subplots(figsize=(9.5, 8.6 if n <= 4 else 9.2))
    ax.axis("off")
    s = 3.0
    bw = 1.5 if n <= 4 else 1.7
    for r in range(n):
        for c in range(n):
            x, y = c * s, -r * s
            ax.add_patch(FancyBboxPatch((x - bw / 2, y - bw / 2), bw, bw, boxstyle="round,pad=0.03",
                                        fc=C_SW, ec="#1F3B5C", lw=0.9, zorder=3))
            ax.text(x, y + (0.18 if n <= 4 else 0), f"R{r * n + c}", ha="center", va="center",
                    fontsize=9 if n <= 4 else 6.5, zorder=4)
            if n <= 4:
                ax.text(x, y - 0.35, f"{st['router']:.0f}T", ha="center", va="center", fontsize=7,
                        color="#2F6DB5", zorder=4)
            ax.plot([x + bw / 2 - 0.15, x + bw / 2 + 0.25], [y + bw / 2 - 0.15, y + bw / 2 + 0.25],
                    color=C_LINE, lw=1.0, zorder=2)
            if c < n - 1:
                ax.annotate("", xy=(x + s - bw / 2, y), xytext=(x + bw / 2, y),
                            arrowprops=dict(arrowstyle="<->", color=C_LINK, lw=1.2), zorder=2)
            if r < n - 1:
                ax.annotate("", xy=(x, y - s + bw / 2), xytext=(x, y - bw / 2),
                            arrowprops=dict(arrowstyle="<->", color=C_LINK, lw=1.2), zorder=2)
    if n <= 4:
        ax.text(s / 2, 0.3, f"{st['side_bw']:.1f}T", ha="center", fontsize=8, color=C_LINK)
        ax.text(0.3, -s / 2, f"{st['side_bw']:.1f}T", ha="left", fontsize=8, color=C_LINK)
    W = (n - 1) * s
    ax.text(W / 2, -W - 2.2,
            f"每个 router：线路侧 {B:g}T（{round(B / 0.4)}×400GE，绿色短线）+ 东/南/西/北 4 组交换侧各 (n/2)·B_die = {st['side_bw']:.1f}T（蓝色双向箭头）\n"
            f"router 交换容量 (2n+1)·B_die = {st['router']:.1f}T；src→dst 按顺时针 / 逆时针 O1Turn 各 50% 逐 router 转发，无 L1/L2/L3 分级、无喷洒",
            ha="center", va="top", fontsize=9)
    ax.set_xlim(-2, W + 2)
    ax.set_ylim(-W - 4.2, 1.8)
    ax.set_aspect("equal")
    ax.set_title(f"逻辑交换拓扑：O1Turn(DR) — {n}×{n} 同构 NoC router 网格（{n * n}R）", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_logic_o1t_{n}x{n}.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ die architecture


def _box(ax, x, y, w, h, title, sub="", fc=C_SW, ec="#1F3B5C", fs=11):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04", fc=fc, ec=ec, lw=1.3, zorder=3))
    ax.text(x + w / 2, y + h * 0.64, title, ha="center", va="center", fontsize=fs, fontweight="bold", zorder=4)
    if sub:
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=8.2, color="#1F3B5C", zorder=4)


def _arrow(ax, a, b, col, lw=1.3, ls="-", rad=0.0, both=False):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle="<->" if both else "->", color=col, lw=lw, ls=ls,
                                                    connectionstyle=f"arc3,rad={rad}"), zorder=2)


def _sio_ports(ax, st):
    """四边 SIO 端口块：出 / 入按逻辑链路粒度（条 × b）标注。"""
    o, i = st["sio_out"], st["sio_in"]
    b = st["b"]
    spec = {"N": (4.2, 9.05, 3.6, 0.75), "S": (4.2, 0.2, 3.6, 0.75),
            "W": (0.15, 4.0, 1.25, 2.4), "E": (10.6, 4.0, 1.25, 2.4)}
    for d, (x, y, w, h) in spec.items():
        ax.add_patch(Rectangle((x, y), w, h, fc="#f6e7d8", ec=C_DIR, lw=1.2, zorder=3))
        no, ni = int(round(o[d] / b)), int(round(i[d] / b))
        txt = f"SIO-{DIR_CN[d]}\n出 {no}×{b:g}T / 入 {ni}×{b:g}T"
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=7.2, zorder=4)
    return {"N": (6.0, 9.05), "S": (6.0, 0.95), "W": (1.4, 5.2), "E": (10.6, 5.2)}


def fig_die_clos(n: int, sc: str, st: dict):
    fig, ax = plt.subplots(figsize=(10.5, 7.8))
    ax.axis("off")
    ax.set_xlim(-0.3, 12.3)
    ax.set_ylim(-1.6, 10.3)
    ax.add_patch(Rectangle((0.1, 0.1), 11.8, 9.8, fill=False, ec="#1F3B5C", lw=2.2))
    pt = _sio_ports(ax, st)
    B = st["B"]
    _box(ax, 2.0, 6.6, 1.8, 1.4, "线路侧入", f"{round(B / 0.4)}×400GE\n{B:g}T", fc="#e3f0dc", ec=C_LINE, fs=9.5)
    _box(ax, 8.2, 6.6, 1.8, 1.4, "线路侧出", f"{round(B / 0.4)}×400GE\n{B:g}T", fc="#e3f0dc", ec=C_LINE, fs=9.5)
    l1 = f"{st['L1']:.1f}T" + (f"\n(含直连 +{st['L1_add']:.1f}T)" if st["L1_add"] else "")
    l3 = f"{st['L3']:.1f}T" + (f"\n(含直连 +{st['L3_add']:.1f}T)" if st["L3_add"] else "")
    _box(ax, 2.0, 4.2, 1.8, 1.7, "L1", l1)
    _box(ax, 5.1, 4.2, 1.8, 1.7, "L2", f"{st['L2']:.1f}T")
    _box(ax, 8.2, 4.2, 1.8, 1.7, "L3", l3)
    _box(ax, 4.3, 1.5, 3.4, 1.6, "Feedthrough", f"单 die 最大过路 {st['ft_max']:.1f}T\n平均 {st['ft_mean']:.1f}T",
         fc="#f8dede", ec=C_FT, fs=10)
    _arrow(ax, (2.9, 6.6), (2.9, 5.95), C_LINE)
    _arrow(ax, (9.1, 5.95), (9.1, 6.6), C_LINE)
    _arrow(ax, (3.8, 5.2), (5.1, 5.2), C_LINK)
    _arrow(ax, (6.9, 5.2), (8.2, 5.2), C_LINK)
    ax.text(4.45, 5.35, f"本 die\n{st['b']:g}T", ha="center", va="bottom", fontsize=7.5, color=C_LINK)
    ax.text(7.55, 5.35, f"本 die\n{st['b']:g}T", ha="center", va="bottom", fontsize=7.5, color=C_LINK)
    _arrow(ax, (2.9, 4.2), (4.6, 2.8), C_LINK, rad=0.15)
    _arrow(ax, (5.6, 3.1), (5.6, 4.2), C_LINK)
    _arrow(ax, (6.4, 4.2), (6.4, 3.1), C_LINK)
    _arrow(ax, (7.4, 2.8), (9.1, 4.2), C_LINK, rad=0.15)
    if st["L1_add"]:
        _arrow(ax, (3.8, 4.45), (8.2, 4.45), C_DIR, ls="--", rad=0.3)
        ax.text(6.0, 3.95, f"L1→L3 直连 +{st['L1_add']:.1f}T", ha="center", fontsize=8, color=C_DIR,
                bbox=dict(fc="white", ec="none", pad=0.5), zorder=4)
    _arrow(ax, (6.0, 9.05), (6.0, 3.1), C_FT, lw=1.0, both=True)  # 北向馈通，从 L2 后方穿过
    for d in ("S", "W", "E"):
        tgt = {"S": (6.0, 1.5), "W": (4.3, 2.3), "E": (7.7, 2.3)}[d]
        _arrow(ax, pt[d], tgt, C_FT, lw=1.0, both=True)
    ax.text(6.0, -0.25,
            f"L1 上行 N·b = {st['uplink']:g}T（本 die {st['uplink_local']:g}T，其余 {st['uplink_remote']:g}T 经 SIO 去远端 L2）；"
            f"L3 汇入 {B:g}T（远端 L2 经 SIO）\n"
            f"单 die 交换容量 L1+L2+L3 = {st['die_sw']:.1f}T（{st['die_sw'] / B:.2f}×B_die）；"
            f"SIO 每方向 ≤ {st['sio_side_max']:.1f}T = {st['sio_ports_b']}×{st['b']:g}T（逻辑链路粒度；≈{st['sio_lanes400']}×400G）；"
            f"单 die D2D 出向合计最大 {st['die_d2d_out_max']:.1f}T",
            ha="center", va="top", fontsize=9)
    ax.set_title(f"die 级顶层模块架构：{TITLE[sc]}（{n}×{n}，同构 die）", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_die_{sc}_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_die_o1t(n: int, st: dict):
    fig, ax = plt.subplots(figsize=(10.5, 7.8))
    ax.axis("off")
    ax.set_xlim(-0.3, 12.3)
    ax.set_ylim(-1.6, 10.3)
    ax.add_patch(Rectangle((0.1, 0.1), 11.8, 9.8, fill=False, ec="#1F3B5C", lw=2.2))
    st2 = dict(st, sio_out={d: st["side_bw"] for d in DIRS}, sio_in={d: st["side_bw"] for d in DIRS})
    pt = _sio_ports(ax, st2)
    B = st["B"]
    _box(ax, 3.6, 3.4, 4.8, 3.3, "NoC router（5 端口组）",
         f"交换容量 (2n+1)·B_die = {st['router']:.1f}T\n= 线路侧 {B:g}T + 4 × {st['side_bw']:.1f}T\n"
         f"O1Turn 顺 / 逆时针各 50%", fs=11)
    _box(ax, 1.7, 7.3, 2.6, 1.3, "线路侧 400GE", f"{round(B / 0.4)}×400GE = {B:g}T\n（入 / 出）",
         fc="#e3f0dc", ec=C_LINE, fs=9.5)
    _arrow(ax, (3.0, 7.3), (4.2, 6.7), C_LINE, both=True)
    _arrow(ax, (6.0, 9.05), (6.0, 6.7), C_FT, both=True)
    _arrow(ax, (6.0, 0.95), (6.0, 3.4), C_FT, both=True)
    _arrow(ax, (1.4, 5.2), (3.6, 5.2), C_FT, both=True)
    _arrow(ax, (10.6, 5.2), (8.4, 5.2), C_FT, both=True)
    ax.text(8.6, 2.2, f"过路流量在 router 内转发\n（不再单设 Feedthrough）\nAllToAll 下单 die 最大过路 {st['a2a_ft_max']:.1f}T",
            ha="center", va="center", fontsize=8.2, color=C_FT)
    ax.text(6.0, -0.25,
            f"交换侧按任意置换无阻塞配置：每方向 (n/2)·B_die = {st['side_bw']:.1f}T（{round(st['side_bw'] / 0.4)}×400G 等效），"
            f"邻 die 加速比 n/2 = {n // 2}（= 二分下界）；AllToAll 实际最热边 {st['a2a_edge_max']:.1f}T",
            ha="center", va="top", fontsize=9)
    ax.set_title(f"die 级顶层模块架构：方案四 O1Turn(DR)（{n}×{n}，同构 die）", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_die_o1t_{n}x{n}.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ physical configuration


def fig_phys(n: int, sc: str, st: dict, rec: dict):
    """物理构型图：边负载按逻辑链路粒度标注（条数 × b）。"""
    W, H, G = M.DIE_W_MM, M.DIE_H_MM, 6.0
    loads, vmax = rec["loads"], rec["vmax"]
    b = rec["b"]
    # 映射粒度：每条逻辑链路带宽 b，边负载 = 占用的逻辑链路条数
    link_loads = {k: int(round(t / b)) for k, t in loads.items()}
    vmax_n = max(link_loads.values()) if link_loads else 1
    fig, ax = plt.subplots(figsize=(11.0, 7.6 if n <= 4 else 8.6))
    off = 3.2 if n <= 4 else 2.0
    lw = 2.4 if n <= 4 else 1.3
    cmap = plt.cm.YlOrRd
    for r in range(n):
        for c in range(n):
            x, y = c * (W + G), r * (H + G)
            ax.add_patch(Rectangle((x, y), W, H, fc="#f3f6fa", ec="#1F3B5C", lw=1.0, zorder=1))
            ax.text(x + W / 2, y + H / 2, f"die {r * n + c}" if n <= 4 else str(r * n + c), ha="center",
                    va="center", fontsize=9 if n <= 4 else 6, color="#555", zorder=2)
    for key, kn in link_loads.items():
        (r0, c0), (r1, c1) = parse_edge(key)
        x0, y0 = c0 * (W + G) + W / 2, r0 * (H + G) + H / 2
        x1, y1 = c1 * (W + G) + W / 2, r1 * (H + G) + H / 2
        f0, f1 = (0.30, 0.70)
        xs, ys = x0 + f0 * (x1 - x0), y0 + f0 * (y1 - y0)
        xe, ye = x0 + f1 * (x1 - x0), y0 + f1 * (y1 - y0)
        if r0 == r1:
            dy = -off if c1 > c0 else off
            ys, ye = ys + dy, ye + dy
        else:
            dx = off if r1 > r0 else -off
            xs, xe = xs + dx, xe + dx
        hot = kn == vmax_n
        ax.annotate("", xy=(xe, ye), xytext=(xs, ys),
                    arrowprops=dict(arrowstyle="-|>", color=cmap(0.15 + 0.85 * min(kn / vmax_n, 1.0)),
                                    lw=lw * (1.4 if hot else 1.0), mutation_scale=9 if n <= 4 else 6), zorder=3)
        if n <= 4:
            mx, my = (xs + xe) / 2, (ys + ye) / 2
            if r0 == r1:
                my += -2.3 if c1 > c0 else 2.3
            else:
                mx += 3.6 if r1 > r0 else -3.6
            # 标注逻辑链路条数；旁注 Tbps 用较小字号
            ax.text(mx, my, f"{kn}", ha="center", va="center", fontsize=7.2,
                    color="#7a0000" if hot else "#333", fontweight="bold" if hot else "normal", zorder=4)
            ax.text(mx, my - 3.0, f"{kn * b:.1f}T", ha="center", va="top", fontsize=5.2,
                    color="#888", zorder=4)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, vmax_n))
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
    cb.set_label(f"逻辑链路条数（每条 b={b:g}T）", fontsize=9)
    ax.set_xlim(-4, n * (W + G))
    ax.set_ylim(n * (H + G) + 16, -4)
    ax.set_aspect("equal")
    ax.axis("off")
    aw, ah = n * W + (n - 1) * M.GAP_MM, n * H + (n - 1) * M.GAP_MM
    basis = "无阻塞所需（任意置换最坏负载）" if sc == "o1t" else "AllToAll 满载（CLOS 喷洒下与置换相同）"
    ax.text(n * (W + G) / 2 - G / 2, n * (H + G) + 2,
            f"{n * n} 颗同构 die（{M.DIE_W_MM:g}×{M.DIE_H_MM:g} mm），阵列 {aw:.0f}×{ah:.0f} mm；仅相邻 die SIO 互联，"
            f"{st['n_edges']} 条有向边；映射粒度：每条逻辑链路 b={b:g}T，不可拆分；带宽口径：{basis}\n"
            f"最热边 {vmax_n} 条 = {st['edge_max']:.1f}T（{st['n_hot']} 条有向边，加粗）· 平均 {st['edge_mean']:.1f}T · 最轻 {st['edge_min']:.1f}T · "
            f"D2D 总量 {st['total_d2d']:,.0f}T",
            ha="center", va="top", fontsize=9)
    ax.set_title(f"物理构型：{TITLE[sc]}（{n}×{n}）— 有向边逻辑链路条数（× b={b:g}T）", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_phys_{sc}_{n}x{n}.png", dpi=160)
    plt.close(fig)


def main():
    for n in (4, 8):
        stats = {}
        for sc in SCHEMES:
            rec = scheme_record(n, sc)
            st = die_stats(n, sc, rec)
            stats[sc] = st
            fig_phys(n, sc, st, rec)
            if sc == "o1t":
                fig_logic_o1t(n, st)
                fig_die_o1t(n, st)
            else:
                fig_die_clos(n, sc, st)
                if sc == "manhattan":
                    fig_logic_clos(n, sc, st)
                if sc == "s3_10":
                    fig_logic_clos(n, sc, st, rec)
        for sc in ("s3_0", "s3_5"):
            stats[sc] = die_stats(n, sc, scheme_record(n, sc))
        stats["o1t"]["scen"] = o1t_scenarios(n)
        (DATA / f"workflow_{n}x{n}.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
        print("workflow figs", n)


if __name__ == "__main__":
    main()
