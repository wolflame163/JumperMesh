#!/usr/bin/env python3
"""方案三（方案二 + L1→L3 直连叠加）的报告插图，数据取自 data/dsl_l1l3_{n}x{n}.json。

  fig_s3_logic_4x4.png   逻辑拓扑 + 实际直连物理路径
  fig_s3_loads_{n}x{n}.png  有向 die 间负载：方案二 → 叠加直连（只增不减）
  fig_s3_sweep.png       x = 0 / 5 / 10% 扫描：带宽增长、时延、功耗、端口
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
from matplotlib.patches import Circle, FancyArrowPatch

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

XS = ("0", "5", "10")
C_S2, C_DIR, C_LOC = "#9fb3c8", "#e07a1f", "#6a994e"


def load(n):
    s2 = json.loads((DATA / f"dsl_{n}x{n}.json").read_text())["manhattan"]
    s3 = json.loads((DATA / f"dsl_l1l3_{n}x{n}.json").read_text())
    return s2, s3


def fig_logic(s2, s3):
    r = s3["0"]
    n, N = 4, 16
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 6.6), gridspec_kw=dict(width_ratios=[1.0, 1.35]))
    ax = axes[0]
    xs = {"L1": 0.8, "L2": 4.0, "L3": 7.2}
    ypos = lambda i: N - 1 - i  # noqa: E731
    for i in range(N):
        for j in range(N):
            ax.plot([xs["L1"], xs["L2"]], [ypos(i), ypos(j)], color=C_S2, lw=0.25, alpha=0.45, zorder=1)
            ax.plot([xs["L2"], xs["L3"]], [ypos(i), ypos(j)], color=C_S2, lw=0.25, alpha=0.45, zorder=1)
    for i in range(N):
        ax.plot([xs["L1"], xs["L3"]], [ypos(i), ypos(i)], color=C_LOC, lw=0.8, ls=(0, (2, 2)), alpha=0.7, zorder=1)
    for dd in r["directs"]:
        i = dd["i"][0] * n + dd["i"][1]
        k = dd["k"][0] * n + dd["k"][1]
        ax.annotate("", xy=(xs["L3"] - 0.2, ypos(k)), xytext=(xs["L1"] + 0.2, ypos(i)),
                    arrowprops=dict(arrowstyle="-|>", color=C_DIR, lw=0.9, alpha=0.75,
                                    connectionstyle="arc3,rad=0.18", shrinkA=0, shrinkB=0), zorder=2)
    for stage, x in xs.items():
        col = {"L1": "#2a6f97", "L2": "#5a8f3e", "L3": "#bc4749"}[stage]
        for i in range(N):
            ax.add_patch(Circle((x, ypos(i)), 0.24, fc=col, ec="white", lw=0.6, zorder=4))
            ax.text(x, ypos(i), f"{i}", fontsize=5.5, ha="center", va="center", color="white", zorder=5)
        ax.text(x, N + 0.3, stage, ha="center", fontsize=12, color="#1F3B5C")
    ax.plot([], [], color=C_S2, lw=1.5, label="方案二 CLOS 逻辑链路（全量保留）")
    ax.plot([], [], color=C_DIR, lw=1.5, label=f"叠加的 die 间 L1→L3 直连（x=0：{r['n_directs']} 条）")
    ax.plot([], [], color=C_LOC, lw=1.5, ls=(0, (2, 2)), label="片内 L1_i→L3_i 直连（16 条）")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.01), fontsize=8.5, frameon=False)
    ax.set_xlim(-0.2, 8.2)
    ax.set_ylim(-1.0, N + 0.9)
    ax.axis("off")
    ax.set_title("(a) 逻辑拓扑：CLOS(16,16,16) + L1→L3 直连", fontsize=11.5)

    ax = axes[1]
    g = 16.0
    draw_dies(ax, n, label=True, face="#fafafa", g=g)
    by_lat = sorted(r["directs"], key=lambda dd: dd["twohop_lat"], reverse=True)
    by_hops = sorted(r["directs"], key=lambda dd: (len(dd["path"]), dd["twohop_lat"]), reverse=True)
    pick = by_lat[:2]
    for dd in by_hops:
        if len(pick) == 6:
            break
        if dd not in pick and all(dd["i"] != p["i"] for p in pick):
            pick.append(dd)
    cols = ["#e07a1f", "#bc4749", "#7b2cbf", "#2a9d8f", "#d4a017", "#3a86ff"]
    for t, (dd, col) in enumerate(zip(pick, cols)):
        off = (t - 2.5) * 1.6
        pts = [center(rr, cc, g) for rr, cc in dd["path"]]
        pts = [(x + off, y + off) for x, y in pts]
        xs_, ys_ = zip(*pts)
        ax.plot(xs_, ys_, color=col, lw=2.2, zorder=3, solid_capstyle="round")
        ax.add_patch(FancyArrowPatch(pts[-2], pts[-1], arrowstyle="-|>", mutation_scale=14, color=col, lw=2.2, zorder=4))
        ax.plot(*pts[0], "o", color=col, ms=7, zorder=5)
        i = dd["i"][0] * n + dd["i"][1]
        k = dd["k"][0] * n + dd["k"][1]
        h = len(dd["path"]) - 1
        ax.text(n * (W_ + g) + 3, 8 + t * 13,
                f"L1$_{{{i}}}$→L3$_{{{k}}}$：{h} 跳直连 {dd['lat_max']:.0f} ns\n（原两跳最坏 {dd['twohop_lat']:.0f} ns）",
                fontsize=8.5, color=col, va="top")
    ax.set_xlim(-4, n * (W_ + g) + 62)
    ax.set_title("(b) 物理路径示例（x=0）：两跳时延最长的 2 对 + 跳数最多的 4 对直连", fontsize=11.5)
    fig.suptitle("4×4 方案三：在方案二映射上叠加 L1→L3 直连（CLOS 不变，只增不减）", fontsize=13, y=0.99)
    fig.tight_layout()
    fig.savefig(FIG / "fig_s3_logic_4x4.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


W_ = M.DIE_W_MM


def draw_loads(ax, n, loads, b, norm, cmap, g, label, only_pos=False, by_links=True):
    """loads 值为逻辑链路条数；norm 按条数（by_links）或 Tbps。"""
    draw_dies(ax, n, label=False, face="#fafafa", g=g)
    big = n <= 4
    for key, v in loads.items():
        if only_pos and v <= 0:
            continue
        a, bb = parse_edge(key)
        (x0, y0), (x1, y1) = edge_xy(a, bb, off=4.0 if big else 3.4, f0=0.3, f1=0.7, g=g)
        kn = float(v)
        val = kn if by_links else kn * b
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=12 if big else 7,
                                     lw=3.2 if big else 2.6, color=cmap(norm(val)), zorder=3))
        if label:
            horiz = a[0] == bb[0]
            ca = center(*a, g)
            tx = (x0 + x1) / 2 + (0 if horiz else (-7.5 if x0 < ca[0] else 7.5))
            ty = (y0 + y1) / 2 + ((-4.0 if y0 < ca[1] else 4.0) if horiz else 0)
            ax.text(tx, ty, f"{int(round(kn))}", fontsize=6.5, ha="center", va="center", color="#111", zorder=4)


def fig_loads(n, s2, s3):
    b = s2["b_tbps"]
    cmap = plt.get_cmap("turbo")
    if n <= 4:
        vmax = s3["10"]["C"]
        norm = Normalize(0, vmax)
        fig, axes = plt.subplots(1, 3, figsize=(17, 5.6))
        panels = [("(a) 方案二（CLOS 全量）", s2["loads"], s2["C"], s2["C_tbps"], None),
                  ("(b) 方案三 DSL+直连 x=0", s3["0"]["loads"], s3["0"]["C"], s3["0"]["C_tbps"], s3["0"]),
                  ("(c) 方案三 DSL+直连 x=10%", s3["10"]["loads"], s3["10"]["C"], s3["10"]["C_tbps"], s3["10"])]
        for ax, (ttl, ld, cn, ct, r) in zip(axes, panels):
            draw_loads(ax, n, ld, b, norm, cmap, 16.0, True)
            extra = "" if r is None else f"（{100 * r['d2d_growth']:+.1f}%），{r['n_directs']} 条直连"
            ax.set_title(f"{ttl}：最热边 {int(cn)} 条 = {ct:.1f}T{extra}", fontsize=10.5)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        cb = fig.colorbar(sm, ax=list(axes), fraction=0.012, pad=0.01)
        cb.set_label(f"逻辑链路条数（每条 b={b:g}T）")
    else:
        fig = plt.figure(figsize=(14, 10.5))
        gs = fig.add_gridspec(2, 2, height_ratios=[1.0, 0.5])
        axes = [fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1])]
        hx = fig.add_subplot(gs[1, :])
        inc = {x: {k: v - s2["loads"].get(k, 0) for k, v in s3[x]["loads"].items()} for x in ("0", "10")}
        vmax = max(max(d.values()) for d in inc.values())
        norm = Normalize(0, vmax)
        for ax, x, tag in zip(axes, ("0", "10"), "ab"):
            r = s3[x]
            draw_loads(ax, n, inc[x], b, norm, cmap, 12.0, False, only_pos=True)
            ax.set_title(f"({tag}) x={x}%：直连新增负载\n{r['n_directs']} 条直连，"
                         f"最热边 {int(r['C'])} 条 = {r['C_tbps']:.1f}T（{100 * r['d2d_growth']:+.1f}%）", fontsize=10.5)
        sm = plt.cm.ScalarMappable(norm=norm, cmap=cmap)
        cb = fig.colorbar(sm, ax=axes, fraction=0.02, pad=0.01)
        cb.set_label(f"直连新增逻辑链路条数（×b={b:g}T）")
        series = [("方案二", s2["loads"], "#2a6f97")] + [(f"方案三 x={x}%", s3[x]["loads"], c)
                                                       for x, c in zip(XS, ("#e9c46a", "#f4a261", "#bc4749"))]
        top = max(s3["10"]["C"], s2["C"])
        for lab, ld, c in series:
            hx.hist(list(ld.values()), bins=range(0, int(top) + 3),
                    histtype="step", lw=1.8, color=c, label=lab)
        hx.axvline(s2["lb"], color="#555", ls="--", lw=1)
        hx.text(s2["lb"], hx.get_ylim()[1] * 0.95, " 二分下界", fontsize=9, va="top")
        hx.set_xlabel(f"有向边总负载（逻辑链路条数，每条 b={b:g}T）")
        hx.set_ylabel("有向边数")
        hx.set_title("(c) 有向边总负载分布：直连只填充空闲边，最热边上限 = 方案二 × (1 + x)", fontsize=11)
        hx.legend(fontsize=9)
        hx.grid(alpha=.3)
    fig.suptitle(
        f"{n}×{n}：方案二映射上叠加 L1→L3 直连后的有向边负载（映射粒度 b={b:g}T；CLOS 负载不变，只增不减）",
        fontsize=12,
    )
    fig.savefig(FIG / f"fig_s3_loads_{n}x{n}.png", dpi=160, bbox_inches="tight")
    plt.close(fig)


def fig_sweep(data):
    fig, axes = plt.subplots(1, 4, figsize=(17, 4.2))
    xv = [0, 5, 10]
    sty = {4: dict(color="#2a6f97", marker="o"), 8: dict(color="#bc4749", marker="s")}
    for n, (s2, s3) in data.items():
        rs = [s3[x] for x in XS]
        lab = f"{n}×{n}"
        ax = axes[0]
        ax.plot(xv, [100 * r["d2d_growth"] for r in rs], label=f"{lab} 最热边带宽", **sty[n])
        ax.plot(xv, [100 * (r["total_d2d_tbps"] / r["total_d2d_tbps_s2"] - 1) for r in rs], ls="--",
                label=f"{lab} 有向负载总量", **sty[n])
        ax = axes[1]
        ax.plot(xv, [100 * r["e2e_lat_max_vs_s2"] for r in rs], label=f"{lab} 最大时延", **sty[n])
        ax.plot(xv, [100 * (r["e2e"]["lat_mean"]["mean"] / s2["e2e"]["lat_mean"]["mean"] - 1) for r in rs],
                ls="--", label=f"{lab} 平均时延", **sty[n])
        ax = axes[2]
        ax.plot(xv, [100 * r["power"]["0.1"]["vs_s2_total"] for r in rs], label=f"{lab} AllToAll 满载", **sty[n])
        ax.plot(xv, [100 * (r["power"]["0.1"]["total_worst_W"] / s2["power"]["0.1"]["total_W"] - 1) for r in rs],
                ls="--", label=f"{lab} 置换满载（最坏）", **sty[n])
        ax = axes[3]
        base = rs[0]["l1_uplink_ports_base"]
        ax.plot(xv, [100 * r["l1_ports_added_max_per_sw_incl_local"] / base for r in rs],
                label=f"{lab} 400G 等效", **sty[n])
        ax.plot(xv, [100 * r["l1_ports_added_max_per_sw_incl_local_ceil"] / base for r in rs], ls="--",
                label=f"{lab} 整 400G 端口", **sty[n])
    ttl = ["(a) D2D 带宽增长（相对方案二，%）", "(b) L1→L3 时延变化（相对方案二，%）",
           "(c) 芯片总功耗变化 @0.1（相对方案二，%）", "(d) 单 switch 最大新增 L1 输出 / L3 输入端口（%）"]
    for ax, t in zip(axes, ttl):
        ax.set_title(t, fontsize=10)
        ax.set_xticks(xv)
        ax.set_xlabel("允许的 D2D 带宽增长 x（%）")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7.5)
        ax.axhline(0, color="#555", lw=0.8)
    fig.tight_layout()
    fig.savefig(FIG / "fig_s3_sweep.png", dpi=160)
    plt.close(fig)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    data = {n: load(n) for n in (4, 8)}
    for n, (s2, s3) in data.items():
        for x in XS:
            for k, v2 in s2["loads"].items():
                assert s3[x]["loads"].get(k, 0) + 1e-9 >= v2
        fig_loads(n, s2, s3)
    fig_logic(*data[4])
    fig_sweep(data)
    print("s3 figs done")


if __name__ == "__main__":
    main()
