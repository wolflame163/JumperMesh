#!/usr/bin/env python3
"""方案四 O1Turn(DR)（die 级 NoC 路由）的报告插图，数据取自 data/dsl_o1t_{n}x{n}.json。

  fig_o1t_worst.png       最外一圈对角互打流量矩阵（顺 / 逆时针各 50%）：以热边下游的外圈 die 为核心的收发构成与路径
  fig_o1t_loads.png       每条有向边的无阻塞所需带宽（最坏置换）与 AllToAll 实际负载
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import dsl_mesh_400t as M  # noqa: E402
from figs import center, draw_dies, edge_xy, parse_edge  # noqa: E402

for _f in ("/System/Library/Fonts/STHeiti Medium.ttc", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(_f):
        font_manager.fontManager.addfont(_f)
plt.rcParams["font.family"] = ["Heiti SC", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

W = M.DIE_W_MM
PAL = ["#bc4749", "#2a6f97", "#e07a1f", "#6a994e", "#7b2cbf", "#d4a017", "#3a86ff", "#c9184a"]


def load(n):
    return json.loads((DATA / f"dsl_o1t_{n}x{n}.json").read_text())


def did(p, n):
    return p[0] * n + p[1]


def worst_panel(ax, n, r, detail):
    g = 16.0 if n <= 4 else 9.0
    draw_dies(ax, n, label=n <= 4, face="#fafafa", g=g, fs=8)
    a, bb = parse_edge(r["hot_edge"])
    core = bb
    flows = [(tuple(s), tuple(d)) for s, d in r["ring_diag"]]
    paths = {f: (M.route_o1turn_cw(*f), M.route_o1turn_cw(*f, clockwise=False)) for f in flows}
    ring = {f[0] for f in flows}
    for p in ring:
        x, y = p[1] * (W + g), p[0] * (M.DIE_H_MM + g)
        ax.add_patch(Rectangle((x, y), W, M.DIE_H_MM, fc="#eef3f8", ec="#4a5a6a", lw=0.9, zorder=1))
    x, y = core[1] * (W + g), core[0] * (M.DIE_H_MM + g)
    ax.add_patch(Rectangle((x, y), W, M.DIE_H_MM, fc="#fde2c8", ec="#bc4749", lw=2.4, zorder=2))
    hot = (a, bb)
    through = []
    for f, (pc, pw) in paths.items():
        if core in pc or core in pw:
            through.append(f)
            continue
        for p in (pc, pw):
            pts = [center(*q, g) for q in p]
            ax.plot(*zip(*pts), color="#c8d2dc", lw=0.8, zorder=2)
    through.sort(key=lambda f: (f[0] == core, f[1] == core))
    lines = []
    w_hot = {}
    for t, f in enumerate(through):
        col = PAL[t % len(PAL)]
        off = (t - (len(through) - 1) / 2) * (2.0 if n <= 4 else 1.1)
        pc, pw = paths[f]
        for p, ls in ((pc, "-"), (pw, "--")):
            if core not in p:
                continue
            pts = [(x + off, y + off) for x, y in (center(*q, g) for q in p)]
            ax.plot(*zip(*pts), color=col, lw=2.0 if n <= 4 else 1.5, ls=ls, zorder=4)
            ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=12 if n <= 4 else 8,
                                         color=col, lw=1.6, zorder=5))
            ax.plot(*pts[0], "o", color=col, ms=6 if n <= 4 else 4, zorder=5)
        w = 0.5 * sum(hot in M.path_edges(p) for p in (pc, pw))
        if w:
            w_hot[f] = w
        s, d = f
        role = "本 die 注入" if s == core else ("本 die 落地" if d == core else "过路")
        same = pc == pw
        lines.append((col, f"die {did(s, n)} → die {did(d, n)}（{role}{'，两路径相同' if same else ''}"
                           f"{f'，热边 {w:g}' if w else ''}）"))
    (x0, y0), (x1, y1) = edge_xy(a, bb, off=0, f0=0.15, f1=0.85, g=g)
    n1 = sum(1 for v in w_hot.values() if v == 1.0)
    nh = sum(1 for v in w_hot.values() if v == 0.5)
    ax.annotate(f"热边：{n1} 条 × 1.0 + {nh} 条 × 0.5 = {sum(w_hot.values()):g} = n/2",
                xy=((x0 + x1) / 2, (y0 + y1) / 2 - 2), xytext=((x0 + x1) / 2, -10 if n <= 4 else -9),
                ha="center", fontsize=9.5 if n <= 4 else 9, color="#bc4749",
                arrowprops=dict(arrowstyle="->", color="#bc4749"))
    ax.set_ylim(n * (M.DIE_H_MM + g) + 1, -16)
    loc_in = sum(1 for f in through if f[1] == core)
    title = (f"{n}×{n}：核心 die {did(core, n)}（外圈），经过核心 die 的流 {len(through)} 条；"
             f"实线顺时针、虚线逆时针，各 0.5")
    ax.set_title(title, fontsize=10.5)
    if detail:
        tx = n * (W + g) + 4
        ax.text(tx, 2, "经过核心 die 的流：", fontsize=9, va="top")
        for k, (col, s) in enumerate(lines):
            ax.text(tx, 10 + k * 8, s, fontsize=8.8, color=col, va="top")
        ax.set_xlim(-4, n * (W + g) + 75)
    return loc_in


def fig_worst(r4, r8):
    fig, axes = plt.subplots(1, 2, figsize=(16, 7.0), gridspec_kw=dict(width_ratios=[1.25, 1.0]))
    worst_panel(axes[0], 4, r4, True)
    worst_panel(axes[1], 8, r8, False)
    fig.suptitle("方案四 O1Turn(DR)：最外一圈 die 与中心对称 die 互打（每颗 die 1.0，顺 / 逆时针 O1Turn 各 0.5）。"
                 "灰线为其余流的两条路径，彩色为经过核心 die 的流（圆点为源）", fontsize=11.5)
    fig.tight_layout()
    fig.savefig(FIG / "fig_o1t_worst.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def load_panel(ax, n, loads, unit, b, norm, cmap, title):
    """unit = 负载计数单位（B_die 或 b）；标注折合为 b 粒度的逻辑链路条数。"""
    g = 16.0 if n <= 4 else 12.0
    draw_dies(ax, n, label=False, face="#fafafa", g=g)
    big = n <= 4
    for k, v in loads.items():
        a, bb = parse_edge(k)
        (x0, y0), (x1, y1) = edge_xy(a, bb, off=4.0 if big else 3.4, g=g)
        tb = v * unit
        kn = int(round(tb / b))
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12 if big else 7,
                                     lw=3.2 if big else 2.6, color=cmap(norm(kn)), zorder=3))
        if big:
            horiz = a[0] == bb[0]
            ca = center(*a, g)
            tx = (x0 + x1) / 2 + (0 if horiz else (-7.5 if x0 < ca[0] else 7.5))
            ty = (y0 + y1) / 2 + ((-4.0 if y0 < ca[1] else 4.0) if horiz else 0)
            ax.text(tx, ty, f"{kn}", fontsize=6.5, ha="center", va="center", zorder=4)
    ax.set_title(title, fontsize=10.5)


def fig_loads(r4, r8):
    fig, axes = plt.subplots(2, 2, figsize=(14, 12.5))
    cmap = plt.get_cmap("turbo")
    for row, r in enumerate((r4, r8)):
        n = r["n"]
        b = r["b_tbps"]
        vmax_n = int(round(r["C_tbps"] / b))
        norm = Normalize(0, vmax_n)
        load_panel(axes[row][0], n, r["worst_load"], r["die_bw_tbps"], b, norm, cmap,
                   f"({'ac'[row]}) {n}×{n} 无阻塞：每边 {vmax_n}×{b:g}T = {r['C_tbps']:.1f}T"
                   f"（{r['C_die']:g}×B_die）")
        load_panel(axes[row][1], n, r["a2a_load"], r["b_tbps"], b, norm, cmap,
                   f"({'bd'[row]}) {n}×{n} AllToAll：最热 {int(round(r['a2a_C_tbps']/b))}×{b:g}T"
                   f" = {r['a2a_C_tbps']:.1f}T")
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        cb = fig.colorbar(sm, ax=list(axes[row]), fraction=0.02, pad=0.01)
        cb.set_label(f"折合逻辑链路条数（每条 b={b:g}T）")
    fig.suptitle("方案四 O1Turn(DR)：有向边负载（统一按 b 粒度条数标注）", fontsize=12)
    fig.savefig(FIG / "fig_o1t_loads.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    r4, r8 = load(4), load(8)
    fig_worst(r4, r8)
    fig_loads(r4, r8)
    print("o1t figs done")


if __name__ == "__main__":
    main()
