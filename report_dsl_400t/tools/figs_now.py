#!/usr/bin/env python3
"""第 6 章 DSL 3D 堆叠细分方案插图：figs/fig_now_*.png（数据 data/dsl_now_{n}x{n}.json、dsl_stk_{n}x{n}.json）。"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figs as F  # noqa: E402
import figs_stack as K  # noqa: E402

from matplotlib.patches import Rectangle  # noqa: E402

plt = F.plt
W, H = F.M.DIE_W_MM, F.M.DIE_H_MM
C_L1, C_L2, C_L3 = "#2a9d8f", "#e9c46a", "#e76f51"
C_BUS, C_MUX, C_VERT = "#457b9d", "#6d597a", "#2d6a4f"
KIND_C = {"straight": "#457b9d", "turn": "#e76f51", "up": "#2a9d8f", "down": "#8e44ad"}
NAME = {"s1": "方案一（XY+O1Turn 顺时针）", "s2": "方案二（曼哈顿最短路）"}


def load(kind, n):
    return json.loads((F.DATA / f"dsl_{kind}_{n}x{n}.json").read_text())


# ------------------------------------------------------------------ 图 6-1 逻辑架构


def fig_idea(r4):
    fig, ax = plt.subplots(figsize=(13, 6.2))
    xs = (2, 36, 70)
    names = ("die i（源）", "die k（过路）", "die j（宿）")
    for x, nm in zip(xs, names):
        K.box(ax, x, 30, 28, 18, K.C_SW, z=1)
        ax.text(x + 14, 46, f"SW die · {nm}", ha="center", fontsize=9.5, fontweight="bold")
        for j, (lbl, c) in enumerate((("L1", C_L1), ("L2", C_L2), ("L3", C_L3))):
            K.box(ax, x + 1.5 + j * 9, 33, 7.5, 9, c, lbl, fs=10, bold=True, z=2)
        K.box(ax, x, 6, 28, 14, K.C_NOW, z=1)
        ax.text(x + 14, 8, "NOW die：行列总线 + 静态 mux", ha="center", fontsize=8.5)
        K.box(ax, x, 22.6, 28, 1.8, "#fff3b0", "混合键合（垂直端口）", fs=7, lw=0.5, z=1)
    # L1_i -> L2_j （经 die k 馈通），L2_j -> L3_k 直接下一跳
    y = 13
    ax.plot([xs[0] + 5.2, xs[0] + 5.2, xs[0] + 28], [33, y, y], color=C_L1, lw=2.2, zorder=4)
    ax.plot([xs[0] + 28, xs[1]], [y, y], color=C_L1, lw=2.2, ls=(0, (4, 2)), zorder=4)
    ax.plot([xs[1], xs[1] + 28], [y, y], color=C_L1, lw=2.2, zorder=4)
    ax.plot([xs[1] + 28, xs[2]], [y, y], color=C_L1, lw=2.2, ls=(0, (4, 2)), zorder=4)
    ax.annotate("", xy=(xs[2] + 14.2, 33), xytext=(xs[2] + 14.2, y), zorder=5,
                arrowprops=dict(arrowstyle="-|>", color=C_L1, lw=2.2))
    ax.plot([xs[2], xs[2] + 14.2], [y, y], color=C_L1, lw=2.2, zorder=4)
    ax.text(xs[1] + 14, y + 1.2, "SIO→SIO 馈通（直通或转向）", ha="center", fontsize=8, color=C_L1)
    ax.text(xs[0] + 6.2, 26, "注入：垂直端口→SIO", fontsize=8, color=C_L1)
    ax.text(xs[2] + 15, 26, "弹出：SIO→垂直端口", fontsize=8, color=C_L1)
    y2 = 16.5
    ax.plot([xs[2] + 21.2, xs[2] + 21.2], [33, y2], color=C_L2, lw=2.0, zorder=4)
    ax.plot([xs[2] + 21.2, xs[2] + 28 + 4], [y2, y2], color=C_L2, lw=2.0, zorder=4)
    ax.text(xs[2] + 28.6, y2 + 0.8, "L2→L3 到下一 die", fontsize=8, color="#b07d00")
    ax.text(50, 54, f"CLOS({r4['N_die']},{r4['N_die']},{r4['N_die']}) 三级共址：每颗 SW die 含 L1 / L2 / L3，"
            f"跨 die 逻辑链路（每条 b = {r4['b_tbps']:g}T，16R）全部由 NOW die 承载",
            ha="center", fontsize=10)
    ax.text(50, 1.5, "同 die 的 L1→L2、L2→L3 两条链路在 SW die 内部完成；NOW die 只做电气连线，不做报文处理",
            ha="center", fontsize=8.5, color="#555")
    ax.set_xlim(0, 103)
    ax.set_ylim(0, 57)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_idea.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-2 堆叠


def top_view(ax, r, s, title):
    n_pipe = r["N_pipe"]
    K.box(ax, 0, 0, W, H, K.C_NOW, ec="#2c3e50", lw=1.4, z=1)
    ax.text(0.2, -4.4, "灰底 = NOW die（底层，整 Reticle：行列总线 + mux + 四边 SIO）", ha="left", va="center",
            fontsize=7.2, color="#2c3e50", zorder=3)
    x, y, w, h = K.oe_rect(n_pipe)
    K.box(ax, x, y, w, h, K.C_OE, z=3, lw=1.2)
    ax.text(x + w / 2, y + 1.2, f"OE die（{s['oe_tbps']:g}T = {n_pipe} 个 {s['pipe_tbps']:g}T 光引擎切片）",
            ha="center", va="center", fontsize=7.5, zorder=4)
    for fx, fy, fw, fh in K.fau_rects(s):
        K.box(ax, fx, fy, fw, fh, K.C_FAU, f"FAU\n{s['fau_fibres']} 芯", fs=6.5, z=4, hatch="///", color="white")
    x, y, w, h = K.sw_rect(n_pipe)
    K.box(ax, x, y, w, h, K.C_SW, z=3, lw=1.2)
    ph = h * 0.36
    for i in range(n_pipe):
        K.box(ax, x + i * w / n_pipe + 0.15, y + h - ph - 0.3, w / n_pipe - 0.3, ph, "#a9cce3",
              f"流水线\n{i}" if n_pipe <= 8 else "", fs=6, z=4, lw=0.5)
    bw = (w - 1.6) / 3
    for j, (lbl, c) in enumerate((("L1", C_L1), ("L2", C_L2), ("L3", C_L3))):
        K.box(ax, x + 0.4 + j * (bw + 0.4), y + 0.4, bw, h - ph - 1.2, c, lbl, fs=9, bold=True, z=4)
    ax.text(x + w / 2, y + h + 0.1, "", fontsize=1)
    for side, (p, q) in {"W": ((-0.3, H / 2), (-4.5, H / 2)), "E": ((W + 0.3, H / 2), (W + 4.5, H / 2)),
                         "N": ((W / 2, H + 0.3), (W / 2, H + 3.6)), "S": ((W / 2, -0.3), (W / 2, -3.6))}.items():
        K.arrow(ax, p, q, color=C_BUS, lw=1.6)
    ax.text(W + 2.4, H / 2 + 1.2, f"SIO\n{r['s2']['C']}×b", ha="center", va="bottom", fontsize=7, color=C_BUS)
    ax.set_xlim(-6, W + 6)
    ax.set_ylim(-5.4, H + 5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=10)


def side_view(ax, r, s):
    L = H
    sx, sy, sw, sh = K.sw_rect(s["N_pipe"])
    ox, oy, ow, oh = K.oe_rect(s["N_pipe"])
    zs = dict(pdb=(0, 1.2), now=(1.2, 2.2), hb=(3.4, 0.35), top=(3.75, 2.0))
    K.box(ax, -3, zs["pdb"][0], L + 6, zs["pdb"][1], "#ececec", "供电 / 载板（背面供电模块，经 NOW die TSV 向上供电）",
          fs=7.5, z=1)
    K.box(ax, -3, zs["now"][0], L + 6, zs["now"][1], K.C_NOW, z=2)
    ax.text(L + 2.7, zs["now"][0] + 1.85, "NOW die：行列总线 + 稀疏 mux（静态配置）+ SW↔OE 点对点 + 四边 SIO", ha="right",
            fontsize=7.5, zorder=7, bbox=dict(fc=K.C_NOW, ec="none", pad=0.6))
    for xx in [i * 1.6 - 2.2 for i in range(19)]:
        ax.plot([xx, xx], [zs["now"][0], zs["now"][0] + 0.55], color="#7f8c8d", lw=0.8, zorder=3)
    ax.text(-2.8, zs["now"][0] + 0.28, "TSV", fontsize=6.5, va="center", color="#555", zorder=4)
    K.box(ax, -3, zs["hb"][0], L + 6, zs["hb"][1], "#fff3b0", z=2, lw=0.6)
    ax.text(L + 3.2, zs["hb"][0] + 0.17, "混合键合层", fontsize=7, va="center", ha="left")
    t0, th = zs["top"]
    K.box(ax, sy, t0, sh, th, K.C_SW, "SW die（L1 / L2 / L3 + 流水线）", fs=8.5, z=3)
    K.box(ax, oy, t0, oh, th, K.C_OE, "OE die（同第 5 章）", fs=8, z=3)
    fx0, fw = oy + 1.0, oh - 2.0
    K.box(ax, fx0, t0 + th, fw, 1.1, K.C_FAU, f"FAU × {s['n_fau']}", fs=7, z=3, color="white", hatch="///")
    for k in range(7):
        xx = fx0 + 0.4 + k * (fw - 0.8) / 6
        ax.plot([xx, xx + (k - 3) * 0.3], [t0 + th + 1.1, t0 + th + 3.8], color="#c0392b", lw=0.9, zorder=3)
    ax.text(fx0 + fw / 2, t0 + th + 4.1, f"{s['fibres_die']} 芯光纤向上扇出", ha="center", fontsize=7, color="#c0392b")
    K.box(ax, sy + 0.3, t0 + th, sh - 0.6, 1.0, "#a9cce3", "冷板（OE 侧开窗避让 FAU）", fs=7, z=3)
    yp = zs["now"][0] + 1.3
    x_sw, x_oe = sy + sh - 1.2, oy + 1.2
    ax.plot([x_sw, x_sw, x_oe, x_oe], [t0, yp, yp, t0], color=K.C_P2P, lw=1.8, zorder=5)
    ax.text(x_oe - 0.6, yp - 0.45, f"OE↔SW 点对点 {s['N_pipe']}×{s['pipe_tbps']:g}T", fontsize=7, color="#b5651d",
            ha="right", zorder=5)
    for xx in (2.5, 4.5, 6.5, 8.5):
        K.arrow(ax, (xx, t0), (xx, zs["now"][0] + 0.9), color=C_VERT, lw=1.3)
    ax.plot([1.0, 10.5], [zs["now"][0] + 0.9] * 2, color=C_BUS, lw=2.4, zorder=4)
    ax.text(10.8, zs["now"][0] + 0.75, f"垂直端口 {r['sw_vert_lanes']} 条 lane ↔ 行列总线", fontsize=7, color=C_VERT,
            ha="left", zorder=5)
    ym = zs["now"][0] + 0.9
    K.arrow(ax, (-3, ym), (-6.5, ym), color=C_BUS, lw=1.6)
    K.arrow(ax, (L + 3, ym), (L + 6.5, ym), color=C_BUS, lw=1.6)
    ax.text(-4.8, ym + 0.45, "相邻\nReticle", fontsize=7, ha="center", va="bottom", color=C_BUS)
    ax.text(L + 4.8, ym + 0.45, "相邻\nReticle", fontsize=7, ha="center", va="bottom", color=C_BUS)
    ax.text(-2.6, t0 + th + 0.4, "南", fontsize=8, color="#555")
    ax.text(L + 2.2, t0 + th + 0.4, "北", fontsize=8, color="#555")
    ax.set_xlim(-7, L + 7)
    ax.set_ylim(-0.3, 10.6)
    ax.axis("off")
    ax.set_title("(c) 侧切图（沿 Reticle 南北中线，纵向放大）", fontsize=10)


def fig_stack(r4, r8, s4, s8):
    fig = plt.figure(figsize=(14, 10.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 0.85], width_ratios=[1.3, 1.0])
    top_view(fig.add_subplot(gs[0, 0]), r4, s4, f"(a) 16R 顶视：SW die（L1/L2/L3）+ {s4['oe_tbps']:g}T OE die 堆叠在 NOW die 上")
    top_view(fig.add_subplot(gs[0, 1]), r8, s8, f"(b) 64R 顶视：SW die + {s8['oe_tbps']:g}T OE die")
    side_view(fig.add_subplot(gs[1, :]), r4, s4)
    fig.suptitle("DSL 3D 堆叠细分方案：单 Reticle 多 die 堆叠与连接关系（尺寸示意）", fontsize=13)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_stack.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-3 SW die


def fig_sw(r, s):
    U, b, Np = r["U"], r["b_tbps"], r["N_pipe"]
    fig, ax = plt.subplots(figsize=(13, 6.6))
    K.box(ax, 0, 0, 100, 60, K.C_SW, z=0, lw=1.2)
    ax.text(50, 57, f"SW die（16R：{r['die_bw_tbps']:g}T 线路侧，{Np} 条流水线，b = {b:g}T）", ha="center",
            fontsize=11, fontweight="bold")
    for i in range(min(Np, 8)):
        K.box(ax, 3 + i * 11.8, 45, 10.8, 8, "#a9cce3", f"流水线 {i}\nMAC/IPP/EPP/TM", fs=6.5, z=2, lw=0.6)
    ax.text(50, 54.3, f"↑ OE die（{Np}×{s['pipe_tbps']:g}T 点对点，经 NOW die）", ha="center", fontsize=8,
            color="#b5651d")
    cols = (("L1", C_L1, 4, f"L1：{Np}×{s['pipe_tbps']:g}T 入 → {r['N_die']}×b 出\n入向均匀喷洒到全部 L2"),
            ("L2", C_L2, 36, f"L2：{r['N_die']}×b 入 → {r['N_die']}×b 出\n按目的 die 交换"),
            ("L3", C_L3, 68, f"L3：{r['N_die']}×b 入 → {Np}×{s['pipe_tbps']:g}T 出\n按流重排序后送 EPP"))
    for lbl, c, x, txt in cols:
        K.box(ax, x, 22, 28, 17, c, "", z=2)
        ax.text(x + 14, 33, lbl, ha="center", fontsize=14, fontweight="bold")
        ax.text(x + 14, 26.5, txt, ha="center", va="center", fontsize=7.6)
    K.arrow(ax, (32, 30.5), (36, 30.5), both=False, color="#333")
    K.arrow(ax, (64, 30.5), (68, 30.5), both=False, color="#333")
    ax.text(34, 32.2, "本 die\nb", ha="center", fontsize=6.5)
    ax.text(66, 32.2, "本 die\nb", ha="center", fontsize=6.5)
    K.arrow(ax, (18, 44.8), (18, 39.2), both=False, color="#333")
    K.arrow(ax, (82, 39.2), (82, 44.8), both=False, color="#333")
    ports = ((10, "L1_out", "↓", C_L1), (38, "L2_in", "↑", C_L2), (54, "L2_out", "↓", C_L2), (78, "L3_in", "↑", C_L3))
    for x, nm, arr, c in ports:
        K.box(ax, x - 4, 4, 12, 7, "#fff3b0", f"{nm}\n{U} 端口 {arr}", fs=7.5, z=2, lw=0.6)
        p, q = (x + 2, 21.8), (x + 2, 11.2)
        K.arrow(ax, *((p, q) if arr == "↓" else (q, p)), both=False, color=c, lw=1.6)
    ax.text(50, 1.2, f"垂直端口（混合键合到 NOW die）：4 × {U} = {r['sw_vert_lanes']} 条 lane，"
            f"合计 {r['sw_vert_tbps']:.1f}T；SW die 键合面积约 {r['hb_sw_mm2']:.1f} mm²（含线路侧）",
            ha="center", fontsize=8.5)
    ax.set_xlim(-1, 101)
    ax.set_ylim(-0.5, 60.5)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_sw.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-4 NOW die 逻辑功能（连线需求）


def fig_demand(r4, r8):
    fig, axes = plt.subplots(2, 3, figsize=(12.5, 7.4))
    kinds = (("ft_straight", "馈通直通"), ("ft_turn", "馈通转向"), ("total", "合计（注入 + 弹出 + 馈通）"))
    for row, (r, tag) in enumerate(((r4, "s2"), (r8, "s2"))):
        n = r["n"]
        per = r[tag]["demand"]["per_die"]
        for col, (k, t) in enumerate(kinds):
            ax = axes[row, col]
            g = [[per[str(i * n + j)].get(k, 0) for j in range(n)] for i in range(n)]
            im = ax.imshow(g, cmap="Blues", vmin=0)
            if n == 4:
                for i in range(n):
                    for j in range(n):
                        ax.text(j, i, g[i][j], ha="center", va="center", fontsize=8,
                                color="white" if g[i][j] > 0.6 * max(map(max, g)) else "black")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_title(f"{n}×{n} {t}", fontsize=9)
            fig.colorbar(im, ax=ax, fraction=0.045)
    fig.suptitle("NOW die 逻辑功能：方案二映射结果在每颗 die 上需要实现的连线条数（每格一颗 die；\n"
                 f"注入、弹出每颗 die 都是 2U：16R {2 * r4['U']}、64R {2 * r8['U']}）", fontsize=12)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_demand.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-5 物理实现示意（行列总线 + mux）


def fig_fabric():
    Cs = 4
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(14, 7), gridspec_kw=dict(width_ratios=[1.15, 1]))
    pad = 0.12

    def t(k, first):
        return pad + (1 - 2 * pad) * ((k + 0.5) / (2 * Cs) + (0 if first else 0.5))

    ax.add_patch(Rectangle((0, 0), 1, 1, fc=K.C_NOW, ec="#2c3e50", lw=1.4))
    for k in range(Cs):
        for first, c in ((True, C_BUS), (False, "#7fa7c9")):
            y = 1 - t(k, first)
            ax.plot([0, 1], [y, y], color=c, lw=1.2, zorder=2)
            x = t(k, first)
            ax.plot([x, x], [0, 1], color=c, lw=1.2, zorder=2)
    for k in range(Cs):
        ax.text(1.02, 1 - t(k, True), f"E-out {k}", fontsize=6.5, va="center")
        ax.text(-0.02, 1 - t(k, True), f"W-in {k}", fontsize=6.5, va="center", ha="right")
        ax.text(1.02, 1 - t(k, False), f"E-in {k}", fontsize=6.5, va="center", color="#555")
        ax.text(-0.02, 1 - t(k, False), f"W-out {k}", fontsize=6.5, va="center", ha="right", color="#555")
    for k in range(Cs):
        y = 1 - t(k, True)
        ax.add_patch(Rectangle((0.9, y - 0.018), 0.05, 0.036, fc=C_MUX, ec="none", zorder=4))
    k0 = 1
    y0, xs_in = 1 - t(k0, True), t(k0, False)
    ax.plot([xs_in, xs_in, 0.9], [0, y0, y0], color=KIND_C["turn"], lw=2.4, zorder=5)
    ax.plot([0, 0.9], [1 - t(2, True)] * 2, color=KIND_C["straight"], lw=2.4, zorder=5)
    K.box(ax, 0.36, 0.40, 0.28, 0.2, "#fff3b0", "垂直端口池\nL1_out / L2_out ↑\nL2_in / L3_in ↓", fs=7, z=6, lw=0.6)
    ax.plot([0.64, 0.9], [0.5, 1 - t(3, True)], color=KIND_C["up"], lw=2.0, zorder=5)
    ax.text(0.5, 1.07, f"(a) 同构 NOW die：每个方向 C 条 lane（示意 C = {Cs}）；行 / 列各 2C 条总线\n"
            "▮ = 出向 lane 的静态 mux（只画 E 面）；蓝=直通、橙=转向、绿=注入", ha="center", fontsize=9)
    ax.set_xlim(-0.2, 1.2)
    ax.set_ylim(-0.08, 1.15)
    ax.set_aspect("equal")
    ax.axis("off")

    bx.axis("off")
    bx.set_xlim(0, 10)
    bx.set_ylim(0, 10)
    bx.add_patch(Rectangle((5.6, 4.0), 1.2, 3.6, fc=C_MUX, ec="#333", zorder=3))
    bx.text(6.2, 5.8, "mux", color="white", ha="center", va="center", rotation=90, fontsize=10, zorder=4)
    ins = (("直通：W-in k", KIND_C["straight"]), ("转向：N-in k−w … k+w", KIND_C["turn"]),
           ("转向：S-in k−w … k+w", KIND_C["turn"]), ("注入：L1_out 池中 s 个端口", KIND_C["up"]),
           ("注入：L2_out 池中 s 个端口", KIND_C["up"]))
    for i, (txt, c) in enumerate(ins):
        y = 7.3 - i * 0.75
        bx.plot([3.6, 5.6], [y, y], color=c, lw=2)
        bx.text(3.5, y, txt, ha="right", va="center", fontsize=8.5, color=c)
    bx.annotate("", xy=(8.4, 5.8), xytext=(6.8, 5.8), arrowprops=dict(arrowstyle="-|>", lw=2))
    bx.text(8.5, 5.8, "E-out k\n（SIO 端口 k）", va="center", fontsize=9)
    bx.text(5.0, 9.2, "(b) 出向 lane mux：扇入 1 + 2(2w+1) + 2s", ha="center", fontsize=10, fontweight="bold")
    bx.text(5.0, 2.6, "下行端口 mux：每个 L2_in / L3_in 端口接 ⌈4C·s / P⌉ 条入向 lane\n"
            "（与上行同一伪随机稀疏图样，全部 die 相同）\n\n"
            "配置：每颗 die 一组静态选择码（上电写入，运行中不变）\n"
            "w = 转向窗口；s = 每条 lane 可接的垂直端口数；P = 每池端口数（U + Δ 备用）",
            ha="center", va="center", fontsize=8.5)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_fabric.png", dpi=160)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-6 示例 die 的静态配置


def lane_xy(face, k, C, is_in, pad=0.05):
    first = (not is_in) if face in ("E", "S") else is_in
    t = pad + (1 - 2 * pad) * ((k + 0.5) / (2 * C) + (0 if first else 0.5))
    return {"E": (1, 1 - t), "W": (0, 1 - t), "N": (t, 1), "S": (t, 0)}[face]


def draw_cfg(ax, o, title):
    C, ex = o["C"], o["example"]
    ax.add_patch(Rectangle((0, 0), 1, 1, fc="#f4f6f8", ec="#2c3e50", lw=1.2))
    K.box(ax, 0.4, 0.42, 0.2, 0.16, "#fff3b0", "垂直\n端口", fs=7, z=6, lw=0.5)
    cnt = Counter()
    for fo, lo, sel in ex["out"]:
        q = lane_xy(fo, lo, C, False)
        kind = sel[0]
        cnt[kind] += 1
        if kind == "up":
            ax.plot([0.5, q[0]], [0.5, q[1]], color=KIND_C["up"], lw=0.7, alpha=0.8, zorder=3)
            continue
        p = lane_xy(sel[1], sel[2], C, True)
        if kind == "straight":
            ax.plot([p[0], q[0]], [p[1], q[1]], color=KIND_C["straight"], lw=0.8, zorder=2)
        else:
            corner = (q[0], p[1]) if sel[1] in ("E", "W") else (p[0], q[1])
            ax.plot([p[0], corner[0], q[0]], [p[1], corner[1], q[1]], color=KIND_C["turn"], lw=0.8, zorder=2)
    for pool, port, fi, li in ex["down"]:
        p = lane_xy(fi, li, C, True)
        cnt["down"] += 1
        ax.plot([p[0], 0.5], [p[1], 0.5], color=KIND_C["down"], lw=0.7, alpha=0.8, zorder=3)
    ax.set_xlim(-0.04, 1.04)
    ax.set_ylim(-0.04, 1.04)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"{title}\n直通 {cnt['straight']}、转向 {cnt['turn']}、注入 {cnt['up']}、弹出 {cnt['down']}"
                 f"（每方向 C = {C} 条 lane）", fontsize=9)


def fig_cfg(r4):
    fig, axes = plt.subplots(1, 2, figsize=(13, 7))
    for ax, tag in zip(axes, ("s1", "s2")):
        draw_cfg(ax, r4[tag], f"16R {NAME[tag]}：die {r4[tag]['example']['die']} 的 mux 静态配置")
    hs = [plt.Line2D([], [], color=c, lw=2) for c in KIND_C.values()]
    fig.legend(hs, ["直通（行 / 列总线）", "转向（总线交叉点 mux）", "注入（垂直端口→出向 lane）", "弹出（入向 lane→垂直端口）"],
               loc="lower center", ncol=4, fontsize=9, frameon=False)
    fig.tight_layout(rect=(0, 0.05, 1, 0.95))
    fig.savefig(F.FIG / "fig_now_cfg.png", dpi=170)
    plt.close(fig)


# ------------------------------------------------------------------ 图 6-7 稀疏度与代价


def fig_sparse(r4, r8):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    ax = axes[0]
    for r, ls in ((r4, "-"), (r8, "--")):
        for tag, c in (("s1", "#2a9d8f"), ("s2", "#e76f51")):
            o = r[tag]
            ws = r["w_list"]
            ax.plot(range(len(ws)), [o["curve"][str(w)]["K_over_C"] for w in ws], ls, marker="o", color=c,
                    label=f"{r['n']}×{r['n']} {tag}（C = {o['C']}）")
    ax.axhline(1, color="#888", lw=0.8)
    ax.set_xticks(range(len(r4["w_list"])))
    ax.set_xticklabels(r4["w_list"])
    ax.set_xlabel("转向窗口 w（lane）")
    ax.set_ylabel("所需 lane 数 K(w) / C")
    ax.set_title("(a) 行列总线 lane 数与转向窗口", fontsize=10)
    ax.legend(fontsize=7.5)
    ax = axes[1]
    for r, ls in ((r4, "-"), (r8, "--")):
        for tag, c in (("s1", "#2a9d8f"), ("s2", "#e76f51")):
            v = r[tag]["vert"]
            ks = sorted(v, key=int)
            ax.plot([v[k]["P"] / r["U"] - 1 for k in ks], [v[k]["fan_down"] for k in ks], ls, marker="s", color=c,
                    label=f"{r['n']}×{r['n']} {tag}")
    ax.set_xlabel("备用垂直端口 Δ / U")
    ax.set_ylabel("下行端口 mux 扇入")
    ax.set_yscale("log")
    ax.set_title("(b) 备用端口降低垂直 mux 扇入", fontsize=10)
    ax.legend(fontsize=7.5)
    ax = axes[2]
    labels, sp, full = [], [], []
    for r in (r4, r8):
        for tag in ("s1", "s2"):
            o = r[tag]
            labels.append(f"{r['n']}×{r['n']}\n{tag}")
            sp.append(o["w0"]["xp_lane"])
            full.append(o["xp_lane_full"])
    x = range(len(labels))
    ax.bar([i - 0.2 for i in x], full, 0.4, color="#bbb", label="全交叉（任意 lane↔任意 lane / 端口）")
    ax.bar([i + 0.2 for i in x], sp, 0.4, color=C_MUX, label="稀疏 mux（推荐配置）")
    for i, (f_, s_) in enumerate(zip(full, sp)):
        ax.text(i + 0.2, s_ * 1.15, f"1/{f_ / s_:.0f}", ha="center", fontsize=8)
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("每颗 NOW die 的 mux 交叉点（lane 级）")
    ax.set_title("(c) 稀疏 mux 与全交叉的规模", fontsize=10)
    ax.legend(fontsize=7.5)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_now_sparse.png", dpi=160)
    plt.close(fig)


def main():
    r4, r8 = load("now", 4), load("now", 8)
    s4, s8 = load("stk", 4), load("stk", 8)
    fig_idea(r4)
    fig_stack(r4, r8, s4, s8)
    fig_sw(r4, s4)
    fig_demand(r4, r8)
    fig_fabric()
    fig_cfg(r4)
    fig_sparse(r4, r8)
    print("figs_now: 7 figures")


if __name__ == "__main__":
    main()
