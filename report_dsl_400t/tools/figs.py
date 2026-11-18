#!/usr/bin/env python3
"""从 data/dsl_{n}x{n}.json 生成报告插图（figs/*.png）。

Usage:
  python3 report_dsl_400t/tools/figs.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import Normalize
from matplotlib.patches import FancyArrowPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIG = ROOT / "figs"
sys.path.insert(0, str(ROOT.parent))
import dsl_mesh_400t as M  # noqa: E402

for _f in ("/System/Library/Fonts/STHeiti Medium.ttc", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(_f):
        font_manager.fontManager.addfont(_f)
plt.rcParams["font.family"] = ["Heiti SC", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

W, H, G = M.DIE_W_MM, M.DIE_H_MM, 3.0
SCHEMES = ("xy_o1turn_cw", "manhattan")
SHORT = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由"}
SHORT1 = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由"}
COL = {"xy_o1turn_cw": "#bc4749", "manhattan": "#2a6f97"}
S3 = ("s3_0", "s3_5", "s3_10")
SHORT1.update({"s3_0": "方案三 DSL+直连 x=0", "s3_5": "方案三 DSL+直连 x=5%", "s3_10": "方案三 DSL+直连 x=10%"})
COL.update({"s3_0": "#e9c46a", "s3_5": "#f4a261", "s3_10": "#e07a1f", "o1t": "#6a994e"})
SHORT1["o1t"] = "方案四 O1Turn(DR)（无阻塞所需）"


def load(n: int) -> dict:
    return json.loads((DATA / f"dsl_{n}x{n}.json").read_text())


def center(r: int, c: int, g: float = G):
    return c * (W + g) + W / 2, r * (H + g) + H / 2


def draw_dies(ax, n, label=True, fs=8, face="#f3f6fa", g: float = G):
    for r in range(n):
        for c in range(n):
            x, y = c * (W + g), r * (H + g)
            ax.add_patch(Rectangle((x, y), W, H, fc=face, ec="#4a5a6a", lw=0.9, zorder=1))
            if label:
                ax.text(x + W / 2, y + H / 2, f"{r * n + c}", ha="center", va="center", fontsize=fs, color="#555", zorder=2)
    ax.set_xlim(-4, n * (W + g) + 1)
    ax.set_ylim(n * (H + g) + 1, -4)
    ax.set_aspect("equal")
    ax.axis("off")


def parse_edge(k: str):
    a, b = k.split("->")
    return tuple(int(x) for x in a.split(",")), tuple(int(x) for x in b.split(","))


def edge_xy(a, b, off=3.2, f0=0.3, f1=0.7, g: float = G):
    """有向边 a→b 画在两 die 中心连线的 [f0, f1] 段，并按方向向一侧偏移，使两个方向分开。"""
    (x0, y0), (x1, y1) = center(*a, g), center(*b, g)
    xs, ys = x0 + f0 * (x1 - x0), y0 + f0 * (y1 - y0)
    xe, ye = x0 + f1 * (x1 - x0), y0 + f1 * (y1 - y0)
    if a[0] == b[0]:
        dy = off if b[1] > a[1] else -off
        return (xs, ys + dy), (xe, ye + dy)
    dx = -off if b[0] > a[0] else off
    return (xs + dx, ys), (xe + dx, ye)


# ------------------------------------------------------------------ figures


def fig_package(n: int):
    fig, ax = plt.subplots(1, 1, figsize=(8.2 if n <= 4 else 9.2, 5.8 if n <= 4 else 6.4))
    draw_dies(ax, n, label=n <= 4, fs=10)
    lw = 1.6 if n <= 4 else 0.9
    for r in range(n):
        for c in range(n):
            x, y = c * (W + G), r * (H + G)
            if c < n - 1:
                ax.plot([x + W, x + W + G], [y + H * 0.35, y + H * 0.35], color="#2a6f97", lw=lw)
                ax.plot([x + W, x + W + G], [y + H * 0.65, y + H * 0.65], color="#2a6f97", lw=lw)
            if r < n - 1:
                ax.plot([x + W * 0.35, x + W * 0.35], [y + H, y + H + G], color="#2a6f97", lw=lw)
                ax.plot([x + W * 0.65, x + W * 0.65], [y + H, y + H + G], color="#2a6f97", lw=lw)
    tw, th = n * W + (n - 1) * G, n * H + (n - 1) * G
    ax.set_ylim(th + 14, -4)
    ax.annotate("", xy=(tw, th + 4), xytext=(0, th + 4), arrowprops=dict(arrowstyle="<->", color="#333"))
    aw, ah = n * W + (n - 1) * M.GAP_MM, n * H + (n - 1) * M.GAP_MM
    ax.text(tw / 2, th + 6, f"阵列 {aw:.0f} × {ah:.0f} mm（die {n}×{n}，缝隙 {M.GAP_MM:g} mm 计入走线、图中放大示意）",
            ha="center", va="top", fontsize=9.5)
    ax.set_title(f"{n}×{n} 2D Mesh 封装：{n * n} 颗 32×25 mm die（蓝线为相邻 die SIO 链路）", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_pkg_{n}x{n}.png", dpi=170)
    plt.close(fig)


def fig_routes(n: int, d: dict):
    pairs = [((0, 0), (n - 1, n - 1)), ((n - 1, 0), (0, n - 1)), ((0, 1), (n - 2, n - 1))]
    if n > 4:
        pairs.append(((1, n - 1), (n - 1, 2)))
    colors = ["#bc4749", "#2a6f97", "#6a994e", "#e09f3e"]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.9 if n <= 4 else 5.3))
    for ax, sc in zip(axes, SCHEMES):
        draw_dies(ax, n, label=n <= 4, fs=8)
        paths = d[sc]["paths"]
        for k, ((s, t), col) in enumerate(zip(pairs, colors)):
            key = f"1|{s[0]},{s[1]}|{t[0]},{t[1]}"
            p = paths[key]
            off = (k - 1.5) * 2.2
            xs = [center(*q)[0] + off for q in p]
            ys = [center(*q)[1] + off for q in p]
            ax.plot(xs, ys, "-", color=col, lw=2.2, alpha=0.9, zorder=4)
            ax.plot(xs[0], ys[0], "o", color=col, ms=6, zorder=5)
            ax.plot(xs[-1], ys[-1], "s", color=col, ms=6, zorder=5)
        ax.set_title(SHORT[sc].replace("\n", ""), fontsize=11)
    fig.suptitle(f"{n}×{n}：同一组 L1→L2 逻辑链路在两种路由下的物理路径（○ 源 die，□ 宿 die）", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_routes_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_loads(n: int, d: dict):
    """边负载热力图：按逻辑链路条数（映射粒度 b）着色与标注。"""
    b0 = d["manhattan"]["b_tbps"]
    vmax_n = max(d[sc]["C"] for sc in SCHEMES)
    norm = Normalize(0, vmax_n)
    cmap = plt.get_cmap("turbo")
    gl = 16.0 if n <= 4 else 12.0
    if n <= 4:
        fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.8))
        cax_axes = axes
    else:
        fig = plt.figure(figsize=(14, 10.5))
        gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.5])
        axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
        hx = fig.add_subplot(gs[1, :])
        cax_axes = axes + [hx]
        for k, sc in enumerate(SCHEMES):
            ns = list(d[sc]["loads"].values())
            hx.hist(ns, bins=range(0, int(vmax_n) + 2), histtype="step", lw=2, color=COL[sc], label=SHORT1[sc])
        hx.axvline(d["manhattan"]["lb"], color="#555", ls="--", lw=1)
        hx.text(d["manhattan"]["lb"], hx.get_ylim()[1] * 0.95, " 二分下界", fontsize=9, va="top")
        hx.set_xlabel(f"有向边负载（逻辑链路条数，每条 b={b0:g}T）")
        hx.set_ylabel("有向边数")
        hx.set_title("(c) 有向边负载分布", fontsize=11)
        hx.legend(fontsize=9)
        hx.grid(alpha=.3)
    for ax, sc in zip(axes, SCHEMES):
        r = d[sc]
        b = r["b_tbps"]
        draw_dies(ax, n, label=False, face="#fafafa", g=gl)
        big = n <= 4
        for k, v in r["loads"].items():
            a, bb = parse_edge(k)
            (x0, y0), (x1, y1) = edge_xy(a, bb, off=4.0 if big else 3.4, f0=0.3, f1=0.7, g=gl)
            kn = int(v)  # loads 已是逻辑链路条数
            ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12 if big else 7,
                                         lw=3.2 if big else 2.6, color=cmap(norm(kn)), zorder=3))
            if big:
                horiz = a[0] == bb[0]
                ca = center(*a, gl)
                tx = (x0 + x1) / 2 + (0 if horiz else (-7.5 if x0 < ca[0] else 7.5))
                ty = (y0 + y1) / 2 + ((-4.0 if y0 < ca[1] else 4.0) if horiz else 0)
                ax.text(tx, ty, f"{kn}", fontsize=7, ha="center", va="center", color="#111", zorder=4)
        tag = f"({'abc'[SCHEMES.index(sc)]}) " if n > 4 else ""
        ax.set_title(f"{tag}{SHORT1[sc]}：最热边 {r['C']} 条 = {r['C_tbps']:.1f}T", fontsize=11)
    sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
    cb = fig.colorbar(sm, ax=cax_axes, fraction=0.015 if n <= 4 else 0.02, pad=0.01)
    cb.set_label(f"逻辑链路条数（每条 b={b0:g}T）")
    fig.suptitle(
        f"{n}×{n}：AllToAll 满载有向边负载（映射粒度 b={b0:g}T；二分下界 {d['manhattan']['lb']} 条 = "
        f"{d['manhattan']['lb_tbps']:.1f}T）",
        fontsize=12,
    )
    fig.savefig(FIG / f"fig_loads_{n}x{n}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_hops_wire(n: int, d: dict):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.2))
    ax = axes[0]
    width = 0.36
    allh = sorted({int(h) for sc in SCHEMES for h in d[sc]["hop_hist"]})
    for k, sc in enumerate(SCHEMES):
        hh = d[sc]["hop_hist"]
        tot = sum(hh.values())
        ax.bar([h + (k - 0.5) * width for h in allh], [100 * hh.get(str(h), 0) / tot for h in allh], width,
               color=COL[sc], label=SHORT1[sc])
    ax.set_xlabel("逻辑链路物理跳数")
    ax.set_ylabel("占 die 间逻辑链路比例（%）")
    ax.set_xticks(allh)
    ax.legend(fontsize=9)
    ax.set_title("(a) 跳数分布", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    ax = axes[1]
    x = range(len(SCHEMES))
    mean = [d[sc]["wire_mean"] for sc in SCHEMES]
    mx = [d[sc]["wire_max"] for sc in SCHEMES]
    ax.bar([i - 0.18 for i in x], mean, 0.36, color="#8ab6d6", label="平均走线长度（均值口径）")
    ax.bar([i + 0.18 for i in x], mx, 0.36, color="#1F3B5C", label="最大走线长度（最坏口径）")
    for i in x:
        ax.text(i - 0.18, mean[i] + 3, f"{mean[i]:.0f}", ha="center", fontsize=9)
        ax.text(i + 0.18, mx[i] + 3, f"{mx[i]:.0f}", ha="center", fontsize=9)
    ax.set_xticks(list(x))
    ax.set_xticklabels([SHORT1[s] for s in SCHEMES])
    ax.set_ylabel("单条逻辑链路走线长度（mm）")
    ax.legend(fontsize=9, loc="upper left")
    ax.set_ylim(0, max(mx) * 1.18)
    ax.set_title("(b) 单条逻辑链路走线长度", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_hops_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_latency(n: int, d: dict):
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.3))
    ax = axes[0]
    labels = [SHORT1[s] for s in SCHEMES]
    def parts_of(w):
        return (w["iface"], w["ft"], w["turn"], w["sw_die"], w["sw_sw"])
    labs = [(f"SIO 接口（{M.SIO_NS:g} ns/跳）", "#8ab6d6"), (f"馈通走线（{M.WIRE_NS_PER_MM:g} ns/mm）", "#bc4749"),
            (f"转向（{M.TURN_NS:g} ns/次）", "#9b5de5"),
            (rf"$t_{{sw\_die}}$（{M.T_SW_DIE:g} ns）", "#e09f3e"),
            (rf"$t_{{sw\_sw}}$（L2，{M.T_SW_SW:g} ns）", "#6a994e")]
    bottom = [0.0] * len(SCHEMES)
    stacks = [parts_of(d[s]["e2e_worst"]) for s in SCHEMES]
    for j, (lab, col) in enumerate(labs):
        vals = [st[j] for st in stacks]
        ax.bar(labels, vals, 0.55, bottom=bottom, color=col, label=lab)
        bottom = [a + b for a, b in zip(bottom, vals)]
    for i, sc in enumerate(SCHEMES):
        w = d[sc]["e2e_worst"]
        ax.text(i, bottom[i] + 25, f"{w['lat']:.0f} ns\nFT {100 * w['ft_share']:.0f}%", ha="center", fontsize=9)
    ax.set_ylim(0, max(bottom) * 1.2)
    ax.set_ylabel("L1→L2→L3 最大 die 间时延（ns）")
    ax.legend(fontsize=8.5, loc="lower right")
    ax.set_title("(a) 最坏端到端路径的时延分解", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    ax = axes[1]
    mx = [d[s]["e2e"]["lat_max"]["max"] for s in SCHEMES]
    mean = [d[s]["e2e"]["lat_mean"]["mean"] for s in SCHEMES]
    lk = [d[s]["lat_link_max"] for s in SCHEMES]
    xs = range(len(SCHEMES))
    ax.bar([i - 0.27 for i in xs], lk, 0.27, color="#8ab6d6", label="单条逻辑链路最大")
    ax.bar(list(xs), mx, 0.27, color="#1F3B5C", label="端到端最大")
    ax.bar([i + 0.27 for i in xs], mean, 0.27, color="#6a994e", label="端到端平均")
    for i in xs:
        for dx, v in ((-0.27, lk[i]), (0, mx[i]), (0.27, mean[i])):
            ax.text(i + dx, v + 20, f"{v:.0f}", ha="center", fontsize=8)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_ylabel("时延（ns）")
    ax.set_ylim(0, max(mx) * 1.15)
    ax.legend(fontsize=8.5)
    ax.set_title("(b) 最大 / 平均时延", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_latency_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_power(n: int, d: dict):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    ax = axes[0]
    labels = []
    rows = []
    for ew in ("0.1", "0.06"):
        for s in SCHEMES:
            p = d[s]["power"][ew]
            labels.append(f"方案{'一二'[SCHEMES.index(s)]}\n@{ew}")
            rows.append((M.SERDES_W, p["sio_W"], p["ft_wire_W"]))
    parts = [("SerDes", "#c9d2dc"), ("SIO 接口", "#8ab6d6"), ("馈通走线", "#bc4749")]
    xs = range(len(rows))
    bottom = [0.0] * len(rows)
    for k, (lab, col) in enumerate(parts):
        vals = [r[k] / 1000 for r in rows]
        ax.bar(xs, vals, 0.62, bottom=bottom, color=col, label=lab)
        bottom = [a + b for a, b in zip(bottom, vals)]
    for i, v in enumerate(bottom):
        ax.text(i, v + 0.15, f"{v:.1f}", ha="center", fontsize=8.5)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("满载功耗（kW）")
    ax.set_ylim(0, max(bottom) * 1.15)
    ax.legend(fontsize=8, loc="upper right")
    ax.set_title("(a) 芯片总功耗分解（走线 0.1 / 0.06 pJ/bit/mm）", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    ax = axes[1]
    scen = [k for k, _ in M.SCENARIOS]
    lab = {"a2a_100": "A2A\n100%", "a2a_75": "A2A\n75%", "a2a_50": "A2A\n50%", "a2a_25": "A2A\n25%",
           "perm_100": "置换\n100%", "hot_center": "中心\n热点", "hot_corner": "角落\n热点"}
    width = 0.36
    for k, s in enumerate(SCHEMES):
        vals = [d[s]["power"]["0.1"]["scenarios"][c]["W"] / 1000 for c in scen]
        ax.bar([i + (k - 0.5) * width for i in range(len(scen))], vals, width, color=COL[s], label=SHORT1[s])
    ax.set_xticks(range(len(scen)))
    ax.set_xticklabels([lab[c] for c in scen], fontsize=9)
    ax.set_ylabel("动态数据搬移功耗（kW，0.1 pJ/bit/mm）")
    ax.legend(fontsize=8.5)
    ax.set_title("(b) 不同流量场景下的动态搬移功耗（SIO + 走线）", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / f"fig_power_{n}x{n}.png", dpi=160)
    plt.close(fig)


def fig_compare(d4: dict, d8: dict):
    fig, axes = plt.subplots(1, 3, figsize=(15.5, 4.4))
    data = [("4×4", d4), ("8×8", d8)]
    metrics = [("C_tbps", "最热 die 间有向边带宽（Tbps）"), (None, "端到端最大时延（ns）"),
               ("total", "芯片总功耗（kW，0.1 pJ/bit/mm）")]
    series = list(SCHEMES) + list(S3) + ["o1t"]
    width = 0.8 / len(series)
    for ax, (key, ttl) in zip(axes, metrics):
        for k, s in enumerate(series):
            vals = []
            for _, d in data:
                if key == "C_tbps":
                    vals.append(d[s]["C_tbps"])
                elif key is None:
                    vals.append(d[s]["e2e"]["lat_max"]["max"])
                else:
                    vals.append(d[s]["power"]["0.1"]["total_W"] / 1000)
            xs = [i + (k - (len(series) - 1) / 2) * width for i in range(2)]
            ax.bar(xs, vals, width, color=COL[s], label=SHORT1[s])
            for x, v in zip(xs, vals):
                ax.text(x, v * 1.01, f"{v:.0f}" if v >= 100 else f"{v:.1f}", ha="center", fontsize=6.5)
        ax.set_xticks([0, 1])
        ax.set_xticklabels([t for t, _ in data])
        ax.set_title(ttl, fontsize=11)
        ax.grid(axis="y", alpha=0.3)
    axes[0].legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(FIG / "fig_compare.png", dpi=160)
    plt.close(fig)


def fig_map_dsl():
    """HyperSwitch 报告图 8-5 的副本，图中文字去掉 “NOW” 层的说法。"""
    import matplotlib.axes as maxes
    sys.path.insert(0, str(ROOT.parents[1] / "report" / "report" / "tools"))
    import wafer_d2d as W

    def clean(s):
        return s.replace("仅 NOW 层 2D Mesh", "仅相邻 die 互联的 2D Mesh").replace("NOW ", "")

    text0, title0 = maxes.Axes.text, maxes.Axes.set_title
    maxes.Axes.text = lambda self, x, y, s, *a, **k: text0(self, x, y, clean(s), *a, **k)
    maxes.Axes.set_title = lambda self, s, *a, **k: title0(self, clean(s), *a, **k)
    fig0, W.FIG = W.FIG, FIG
    try:
        W.fig_map_dsl()
    finally:
        maxes.Axes.text, maxes.Axes.set_title, W.FIG = text0, title0, fig0


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    fig_map_dsl()
    ds = {}
    for n in (4, 8):
        if not (DATA / f"dsl_{n}x{n}.json").exists():
            print("skip", n)
            continue
        d = load(n)
        ds[n] = d
        p3 = DATA / f"dsl_l1l3_{n}x{n}.json"
        if p3.exists():
            for x, r in json.loads(p3.read_text()).items():
                d[f"s3_{x}"] = r
        p4 = DATA / f"dsl_o1t_{n}x{n}.json"
        if p4.exists():
            d["o1t"] = json.loads(p4.read_text())
        fig_package(n)
        fig_routes(n, d)
        fig_loads(n, d)
        fig_hops_wire(n, d)
        fig_latency(n, d)
        fig_power(n, d)
        print("figs done", n)
    if 4 in ds and 8 in ds and all(s in ds[n] for n in (4, 8) for s in S3 + ("o1t",)):
        fig_compare(ds[4], ds[8])


if __name__ == "__main__":
    main()
