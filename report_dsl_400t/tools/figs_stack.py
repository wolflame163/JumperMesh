#!/usr/bin/env python3
"""第 5 章 O1Turn(DR) 3D 堆叠变种插图：figs/fig_stk_*.png（数据 data/dsl_stk_{n}x{n}.json）。"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figs as F  # noqa: E402  (字体与输出目录)

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle  # noqa: E402

plt = F.plt
W, H = F.M.DIE_W_MM, F.M.DIE_H_MM
C_NOW, C_SW, C_OE, C_FAU = "#d9dee5", "#cfe0f3", "#f6dcc1", "#b5838d"
C_RT, C_SIO, C_P2P, C_ENG = "#6a994e", "#e9c46a", "#f4a261", "#2a6f97"
GRP = ("#6a994e", "#2a9d8f", "#8ab17d", "#457b9d")
DESIGN = "worst_buf"


def load(n):
    return json.loads((F.DATA / f"dsl_stk_{n}x{n}.json").read_text())


def box(ax, x, y, w, h, fc, txt="", fs=8, ec="#34495e", lw=0.9, z=2, color="#1b2631", hatch=None, rot=0, bold=False):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, zorder=z, hatch=hatch))
    if txt:
        ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", fontsize=fs, zorder=z + 1, color=color,
                rotation=rot, fontweight="bold" if bold else None)


def arrow(ax, p, q, color="#34495e", lw=1.2, both=True, z=4, rad=0.0, ls="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if both else "-|>", mutation_scale=9, color=color, lw=lw,
                                 zorder=z, connectionstyle=f"arc3,rad={rad}", linestyle=ls))


GAP_TOP = 1.0  # OE die 与 SW die 之间的间隙（示意）


def oe_rect(n_pipe):
    """唯一一颗 OE die 沿 Reticle 北边，宽度随流水线数（光引擎切片数）变化。"""
    w = 30.0 if n_pipe >= 4 else 14.0
    return ((W - w) / 2, 17.6, w, 6.8)


def sw_rect(n_pipe):
    x, y, w, _ = oe_rect(n_pipe)
    return (x, 1.6 if n_pipe >= 4 else 4.6, w, y - GAP_TOP - (1.6 if n_pipe >= 4 else 4.6))


def fau_rects(r):
    x, y, w, h = oe_rect(r["N_pipe"])
    nf = r["n_fau"]
    fw = min(5.6, (w - 1.0) / nf - 1.0)
    pitch = w / nf
    return [(x + pitch * (i + 0.5) - fw / 2, y + 2.4, fw, 3.4) for i in range(nf)]


def top_view(ax, r, title):
    n_pipe = r["N_pipe"]
    box(ax, 0, 0, W, H, C_NOW, ec="#2c3e50", lw=1.4, z=1)
    ax.text(0.2, -1.0, "灰底 = NOW die（底层，整 Reticle）", ha="left", va="center", fontsize=7.5, color="#2c3e50", zorder=3)
    x, y, w, h = oe_rect(n_pipe)
    box(ax, x, y, w, h, C_OE, z=3, lw=1.2)
    ax.text(x + w / 2, y + 1.2, f"OE die（{r['oe_tbps']:g}T = {n_pipe} 个 {r['pipe_tbps']:g}T 光引擎切片）",
            ha="center", va="center", fontsize=7.5, zorder=4)
    for fx, fy, fw, fh in fau_rects(r):
        box(ax, fx, fy, fw, fh, C_FAU, f"FAU\n{r['fau_fibres']} 芯", fs=6.5, z=4, hatch="///", color="white")
    x, y, w, h = sw_rect(n_pipe)
    box(ax, x, y, w, h, C_SW, z=3, lw=1.2)
    ax.text(x + w / 2, y + h / 2 + 1.5, "SW die（顶层）", ha="center", fontsize=9, fontweight="bold", zorder=4)
    ax.text(x + w / 2, y + h / 2 - 1.2, f"{n_pipe} 条 × {r['pipe_tbps']:g}T 流水线\n= {r['die_bw_tbps']:g}T（= OE 带宽）",
            ha="center", va="center", fontsize=8, zorder=4)
    m = r["cfg"][DESIGN]["M"]
    for side, (p, q, t) in {"W": ((-0.3, H / 2), (-5, H / 2), "西"), "E": ((W + 0.3, H / 2), (W + 5, H / 2), "东"),
                            "N": ((W / 2, H + 0.3), (W / 2, H + 4), "北"), "S": ((W / 2, -0.3), (W / 2, -4), "南")}.items():
        arrow(ax, p, q, color=C_RT, lw=1.6)
    ax.text(W + 2.6, H / 2 + 1.3, f"SIO\n{m}×{r['pipe_tbps']:g}T", ha="center", va="bottom", fontsize=7, color=C_RT)
    ax.text(W / 2 + 0.8, H + 2.2, f"相邻 Reticle（晶圆内 SIO，{m} 平面 × {r['pipe_tbps']:g}T / 方向）",
            ha="left", va="center", fontsize=7, color=C_RT)
    ax.set_xlim(-6, W + 6)
    ax.set_ylim(-5, H + 5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=10)


def side_view(ax, r):
    """沿 Reticle 中线（y 方向，左南右北）侧切：SW die | OE die 位于 NOW die 之上。"""
    L = H
    sx, sy, sw, sh = sw_rect(r["N_pipe"])
    ox, oy, ow, oh = oe_rect(r["N_pipe"])
    sw_l, oe_l = (sy, sy + sh), (oy, oy + oh)
    zs = dict(pdb=(0, 1.2), now=(1.2, 2.2), hb=(3.4, 0.35), top=(3.75, 2.0))
    box(ax, -3, zs["pdb"][0], L + 6, zs["pdb"][1], "#ececec", "供电 / 载板（背面供电模块，经 NOW die TSV 向上供电）", fs=7.5, z=1)
    box(ax, -3, zs["now"][0], L + 6, zs["now"][1], C_NOW, z=2)
    ax.text(L + 2.7, zs["now"][0] + 1.85, "NOW die：多平面 NoC router + SW↔OE 点对点走线 + 四边 SIO", ha="right", fontsize=7.5,
            zorder=7, bbox=dict(fc=C_NOW, ec="none", pad=0.6))
    for xx in [i * 1.6 - 2.2 for i in range(19)]:
        ax.plot([xx, xx], [zs["now"][0], zs["now"][0] + 0.55], color="#7f8c8d", lw=0.8, zorder=3)
    ax.text(-2.8, zs["now"][0] + 0.28, "TSV", fontsize=6.5, va="center", color="#555", zorder=4)
    box(ax, -3, zs["hb"][0], L + 6, zs["hb"][1], "#fff3b0", z=2, lw=0.6)
    ax.text(L + 3.2, zs["hb"][0] + 0.17, "混合键合层", fontsize=7, va="center", ha="left")
    t0, th = zs["top"]
    box(ax, sw_l[0], t0, sw_l[1] - sw_l[0], th, C_SW, "SW die（多流水线交换）", fs=8.5, z=3)
    box(ax, oe_l[0], t0, oe_l[1] - oe_l[0], th, C_OE, "OE die（唯一）", fs=8, z=3)
    fx0, fw = oe_l[0] + 1.0, oe_l[1] - oe_l[0] - 2.0
    box(ax, fx0, t0 + th, fw, 1.1, C_FAU, f"FAU × {r['n_fau']}", fs=7, z=3, color="white", hatch="///")
    for k in range(7):
        xx = fx0 + 0.4 + k * (fw - 0.8) / 6
        ax.plot([xx, xx + (k - 3) * 0.3], [t0 + th + 1.1, t0 + th + 3.8], color="#c0392b", lw=0.9, zorder=3)
    ax.text(fx0 + fw / 2, t0 + th + 4.1, f"{r['fibres_die']} 芯光纤向上扇出", ha="center", fontsize=7, color="#c0392b")
    box(ax, sw_l[0] + 0.3, t0 + th, sw_l[1] - sw_l[0] - 0.6, 1.0, "#a9cce3", "冷板（OE 侧开窗避让 FAU）", fs=7, z=3)
    ym = zs["now"][0] + 1.0
    yp = zs["now"][0] + 1.3
    x_sw, x_oe = sw_l[1] - 1.2, oe_l[0] + 1.2
    ax.plot([x_sw, x_sw, x_oe, x_oe], [t0, yp, yp, t0], color=C_P2P, lw=1.8, zorder=5)
    for xx in (x_oe, x_sw):
        ax.plot([xx], [t0 - 0.12], marker="^", color=C_P2P, ms=5, zorder=6)
    ax.text(x_oe - 0.6, yp - 0.45, f"OE↔SW 点对点 {r['N_pipe']}×{r['pipe_tbps']:g}T（跨 ~{GAP_TOP:g} mm 间隙）",
            fontsize=7, color="#b5651d", ha="right", zorder=5)
    box(ax, 4.0, zs["now"][0] + 0.75, 4.4, 0.75, "#e3efd9", "router ×M", fs=6.5, ec=C_RT, z=4)
    for xx in (4.7, 6.2, 7.7):
        arrow(ax, (xx, t0), (xx, zs["now"][0] + 1.5), color=C_RT, lw=1.3)
    ax.text(8.8, zs["now"][0] + 1.12, "交换侧 M 端口 ↔ 平面 router 本地口", fontsize=7, color="#2d6a4f", ha="left", zorder=5)
    ax.text(-2.6, t0 + th + 0.4, "南", fontsize=8, color="#555")
    ax.text(L + 2.2, t0 + th + 0.4, "北", fontsize=8, color="#555")
    arrow(ax, (-3, ym), (-6.5, ym), color=C_RT, lw=1.6)
    arrow(ax, (L + 3, ym), (L + 6.5, ym), color=C_RT, lw=1.6)
    ax.text(-4.8, ym + 0.45, "相邻\nReticle", fontsize=7, ha="center", va="bottom", color=C_RT)
    ax.text(L + 4.8, ym + 0.45, "相邻\nReticle", fontsize=7, ha="center", va="bottom", color=C_RT)
    ax.set_xlim(-7, L + 7)
    ax.set_ylim(-0.3, 10.6)
    ax.axis("off")
    ax.set_title("(c) 侧切图（沿 Reticle 南北中线，纵向放大）", fontsize=10)


def fig_stack(r4, r8):
    fig = plt.figure(figsize=(14, 10.2))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 0.85], width_ratios=[1.3, 1.0])
    top_view(fig.add_subplot(gs[0, 0]), r4,
             f"(a) 16R 顶视：1 颗 SW die + 1 颗 {r4['oe_tbps']:g}T OE die 堆叠在 NOW die 上（{W:.0f} × {H:.0f} mm）")
    top_view(fig.add_subplot(gs[0, 1]), r8,
             f"(b) 64R 顶视：1 颗 SW die + 1 颗 {r8['oe_tbps']:g}T OE die")
    side_view(fig.add_subplot(gs[1, :]), r4)
    fig.suptitle("O1Turn(DR) 3D 堆叠变种：单 Reticle 多 die 堆叠与连接关系（尺寸示意）", fontsize=13)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_stack.png", dpi=160)
    plt.close(fig)


def fig_arch(r):
    c = r["cfg"][DESIGN]
    n_pipe, m, k, p = r["N_pipe"], c["M"], c["k"], r["pipe_tbps"]
    fig, ax = plt.subplots(figsize=(14, 9.6))
    # OE die
    box(ax, 0, 60, 26, 36, C_OE, ec="#b5651d", lw=1.4, z=1)
    ax.text(13, 93.5, f"OE die × 1（{r['oe_tbps']:g}T = SW 线路侧带宽）", ha="center", fontsize=10, fontweight="bold")
    box(ax, 3, 81, 20, 9.5, C_FAU, f"FAU × {r['n_fau']} / 光栅耦合阵列\n{r['oe_lanes']} 路 200G 收发\n{r['oe_fibres']} 芯光纤 ↑", fs=7.5, color="white")
    box(ax, 3, 66.5, 20, 13, "#fde2c8", ec="#b5651d", z=2)
    ax.text(13, 77.8, f"{n_pipe} 个光引擎切片（每片 {p:g}T，对应一条流水线）", ha="center", fontsize=7, zorder=3)
    box(ax, 4, 71.5, 8.5, 4.5, "#fbe3d0", "MRM 调制器\n阵列", fs=7)
    box(ax, 13.5, 71.5, 8.5, 4.5, "#fbe3d0", "PD 探测器\n阵列", fs=7)
    box(ax, 4, 67.3, 18, 3.4, "#fbe3d0", "Driver / TIA + 热调谐控制", fs=7)
    box(ax, 3, 61, 20, 4, "#fff3b0", f"电接口 {n_pipe}×{p:g}T（混合键合 → NOW）", fs=7.5)
    # SW die
    box(ax, 30, 60, 70, 36, C_SW, ec=C_ENG, lw=1.4, z=1)
    ax.text(65, 93.5, f"SW die（{n_pipe} 条 × {p:g}T 流水线）", ha="center", fontsize=10, fontweight="bold")
    for j, (lbl, x) in enumerate((("流水线 0", 32.5), ("流水线 1", 47.0), ("…", 61.5))):
        if lbl == "…":
            ax.text(x + 5, 86, f"… 共 {n_pipe} 条", fontsize=9, ha="center", va="center")
            continue
        box(ax, x, 62, 13, 29, "#e8f1fb", ec="#5d6d7e", z=2)
        ax.text(x + 6.5, 89, lbl, ha="center", fontsize=8, fontweight="bold", zorder=3)
        box(ax, x + 1, 82, 11, 5, "#d6eaf8", "OE 接口\nPCS / FEC / MAC", fs=7)
        box(ax, x + 1, 75.5, 11, 5, "#d6eaf8", "IPP 入向\n解析 / 查表 / ACL", fs=7)
        box(ax, x + 1, 69, 11, 5, "#d6eaf8", "EPP 出向\n编辑 / 调度", fs=7)
        box(ax, x + 1, 63, 11, 4.5, "#d6eaf8", "接口处理\nTM / 队列", fs=7)
    box(ax, 74, 62, 24, 29, "#aed6f1", ec=C_ENG, lw=1.4, z=2)
    ax.text(86, 88.5, "交换引擎", ha="center", fontsize=9.5, fontweight="bold", zorder=3)
    ax.text(86, 81, f"{n_pipe} 个线路侧口\n（连各流水线 IPP / EPP）\n+\n{m} 个交换侧口\n（连 {m} 个平面 router 本地口）",
            ha="center", va="center", fontsize=7.5, zorder=3)
    box(ax, 75.5, 67.5, 21, 4, "#d6eaf8", "喷洒（入向，均匀到 M 平面）", fs=7)
    box(ax, 75.5, 63, 21, 4, "#d6eaf8", "重排序（出向，按流保序）", fs=7)
    arrow(ax, (60, 76), (74, 76), color=C_ENG, lw=1.6)
    ax.text(67, 73.5, f"{n_pipe}×{p:g}T", ha="center", fontsize=7.5, color=C_ENG)
    # NOW die
    box(ax, 0, 2, 100, 50, C_NOW, ec="#2c3e50", lw=1.4, z=1)
    ax.text(50, 49, "NOW die（底层）", ha="center", fontsize=10, fontweight="bold")
    box(ax, 3, 28, 30, 16, "#fde2c8", f"SW↔OE 点对点通道\n{n_pipe} 组 × {p:g}T / 方向\n（无交换、仅走线 + 中继）", fs=8, ec="#b5651d")
    box(ax, 40, 8, 57, 36, "#e3efd9", ec=C_RT, lw=1.2, z=2)
    ax.text(68.5, 41, f"多平面 NoC router：{m} 个平面 = {k} 组 × {n_pipe}，平面间互不连通", ha="center", fontsize=8.5, zorder=3, color="#2d6a4f")
    for g in range(min(k, 3)):
        for j in range(4):
            x0, y0 = 43 + j * 13, 30 - g * 9.5
            lbl = f"平面 {g * n_pipe + j}" if j < 3 else f"… {g * n_pipe + n_pipe - 1}"
            box(ax, x0, y0, 11, 7, "white", f"{lbl}\n5 口 router", fs=6.8, ec=GRP[g % len(GRP)], lw=1.4)
    if k > 3:
        ax.text(68.5, 9.5, f"… 共 {k} 组", ha="center", fontsize=8)
    box(ax, 3, 8, 30, 16, "#fff3b0", f"四边 SIO PHY\n每边 {m} × {p:g}T = {c['edge_tbps']:g}T / 方向\n+ 供电 TSV / 时钟 / 控制", fs=8, ec="#b7950b")
    # connections
    ax.annotate("", xy=(18, 44), xytext=(13, 61), arrowprops=dict(arrowstyle="<|-|>", color=C_P2P, lw=2))
    ax.annotate("", xy=(28, 44), xytext=(38, 62), arrowprops=dict(arrowstyle="<|-|>", color=C_P2P, lw=2))
    ax.text(14.5, 54, f"{n_pipe}×{p:g}T", fontsize=7.5, color="#b5651d")
    ax.text(32.5, 53, f"{n_pipe}×{p:g}T（线路侧）", fontsize=7.5, color="#b5651d")
    ax.annotate("", xy=(80, 44), xytext=(86, 62), arrowprops=dict(arrowstyle="<|-|>", color=C_RT, lw=2.2))
    ax.text(84, 53, f"{m} × {p:g}T 交换侧\n↔ router 本地口", fontsize=7.5, color="#2d6a4f")
    arrow(ax, (40, 16), (33, 16), color=C_RT, lw=1.6)
    ax.text(36.5, 17, "东西南北\n4 口", fontsize=7, ha="center", va="bottom", color="#2d6a4f")
    ax.set_xlim(-2, 102)
    ax.set_ylim(0, 98)
    ax.axis("off")
    ax.set_title(f"O1Turn(DR) 3D 堆叠变种：各 die 逻辑模块与连接关系（16R，按最坏置换 buffered 配置 M = {m}）", fontsize=12)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_arch.png", dpi=160)
    plt.close(fig)


def iso(u, v, z, dz=6.0):
    return u + 0.55 * v, 0.38 * v + z * dz


def fig_planes(r):
    c = r["cfg"][DESIGN]
    n_pipe, m, k, p = r["N_pipe"], c["M"], c["k"], r["pipe_tbps"]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(14.5, 7.6), gridspec_kw=dict(width_ratios=[1.15, 1.0]))
    shown = [0, 1, n_pipe - 1, n_pipe, m - 1]
    labels = ["平面 0", "平面 1", f"平面 {n_pipe - 1}", f"平面 {n_pipe}", f"平面 {m - 1}"]
    nn, step = 3, 4.0
    for z, (pl, lb) in enumerate(zip(shown, labels)):
        g = pl // n_pipe
        col = GRP[g % len(GRP)]
        corners = [iso(-1.2, -1.2, z), iso(nn * step - 2.8, -1.2, z), iso(nn * step - 2.8, nn * step - 2.8, z), iso(-1.2, nn * step - 2.8, z)]
        ax.add_patch(Polygon(corners, closed=True, fc=col, alpha=0.10, ec=col, lw=1.0, zorder=z * 3))
        for i in range(nn):
            for j in range(nn):
                x, y = iso(i * step, j * step, z)
                if i + 1 < nn:
                    x2, y2 = iso((i + 1) * step, j * step, z)
                    ax.plot([x, x2], [y, y2], color=col, lw=1.3, zorder=z * 3 + 1)
                if j + 1 < nn:
                    x2, y2 = iso(i * step, (j + 1) * step, z)
                    ax.plot([x, x2], [y, y2], color=col, lw=1.3, zorder=z * 3 + 1)
                ax.add_patch(Rectangle((x - 0.45, y - 0.32), 0.9, 0.64, fc="white", ec=col, lw=1.1, zorder=z * 3 + 2))
        tx, ty = iso(nn * step - 1.5, -0.6, z)
        ax.text(tx + 0.6, ty, f"{lb}（第 {g} 组）", fontsize=8, color=col, va="center", zorder=50)
        if z in (1, 3):
            mx, my = iso(-1.5, 0, z + 0.5)
            ax.text(mx - 0.8, my, "⋮", fontsize=13, va="center", ha="center")
    for z in range(len(shown)):
        x, y = iso(step, step, z)
        ax.plot([x, x], [y, iso(step, step, len(shown) - 1)[1] + 7], color="#2a6f97", lw=0.8, ls=":", zorder=60)
    ex, ey = iso(step, step, len(shown) - 1)
    box(ax, ex - 3.5, ey + 7, 7, 2.4, "#aed6f1", f"交换引擎（某 Reticle）\n{m} 交换侧口 ↓", fs=7.5, ec=C_ENG, z=61)
    ax.text(-2, -3.2, f"每个平面 = {r['N_die']} 颗 NOW die 上各 1 个 5 口 router 组成的 {r['n']}×{r['n']} Mesh（图中示 3×3）；\n"
                      f"同一 Reticle 的 {m} 个 router 只经交换引擎相连，平面之间无链路；平面内按顺 / 逆时针 O1Turn 各 50%",
            fontsize=7.5, va="top")
    ax.set_xlim(-3, 20)
    ax.set_ylim(-6, ey + 10.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"(a) {m} 个互不连通的 NoC 平面（{k} 组 × {n_pipe}）", fontsize=10.5)
    # (b) 交换引擎端口与单平面 router
    box(bx, 0, 30, 12, 60, "#e8f1fb", ec="#5d6d7e", z=1)
    bx.text(6, 87, "线路侧", ha="center", fontsize=9, fontweight="bold")
    for i in range(min(n_pipe, 4)):
        y = 78 - i * 12
        lab = f"流水线 {i}" if i < 3 else f"流水线 {n_pipe - 1}"
        box(bx, 1, y, 10, 8, "#d6eaf8", f"{lab}\nIPP / EPP\n{p:g}T", fs=7)
    bx.text(6, 52.5, "⋮", fontsize=11, ha="center", va="center", zorder=5)
    box(bx, 18, 30, 16, 60, "#aed6f1", ec=C_ENG, lw=1.4, z=1)
    bx.text(26, 70, f"交换引擎\n{n_pipe} + {m} 口\n\n入向：喷洒\n出向：重排序", ha="center", va="center", fontsize=8.5)
    for i in range(4):
        arrow(bx, (11, 82 - i * 12), (18, 82 - i * 12), color=C_ENG, lw=1.1)
    for g in range(k):
        col = GRP[g % len(GRP)]
        y = 84 - g * (54 / k)
        box(bx, 40, y - 54 / k + 2, 14, 54 / k - 3, "white", f"第 {g} 组\n平面 {g * n_pipe}…{g * n_pipe + n_pipe - 1}\n{n_pipe} × {p:g}T",
            fs=7, ec=col, lw=1.6)
        arrow(bx, (34, y - 54 / k / 2 + 0.5), (40, y - 54 / k / 2 + 0.5), color=col, lw=1.3)
    bx.text(47, 88, f"交换侧 M = k·N = {k} × {n_pipe}", ha="center", fontsize=8.5, fontweight="bold")
    # single router zoom
    cx, cy = 26, 12
    box(bx, cx - 6, cy - 6, 12, 12, "white", ec=C_RT, lw=1.6, z=2)
    bx.text(cx, cy + 1, "平面 p router\n5 × 5 交叉开关", ha="center", va="center", fontsize=7.5)
    bx.text(cx, cy - 3.3, "(buffered：输入缓冲 + VC\n bufferless：仅流水寄存器)", ha="center", va="center", fontsize=6.3, color="#555")
    for (dx, dy, t) in ((0, 1, "北"), (0, -1, "南"), (1, 0, "东"), (-1, 0, "西")):
        arrow(bx, (cx + dx * 6, cy + dy * 6), (cx + dx * 11, cy + dy * 11), color=C_RT, lw=1.3)
        bx.text(cx + dx * 12.5, cy + dy * 12.2, f"{t} {p:g}T", ha="center", va="center", fontsize=7)
    arrow(bx, (36, 30), (cx + 4, cy + 6), color=C_RT, lw=1.3, ls="--")
    bx.text(36.5, 24.5, f"本地口 {p:g}T\n（引擎交换侧口 p）", fontsize=7, color="#2d6a4f")
    bx.set_xlim(-1, 56)
    bx.set_ylim(-3, 92)
    bx.axis("off")
    bx.set_title("(b) 交换引擎端口分组与单平面 router", fontsize=10.5)
    fig.suptitle(f"多平面 NoC router 示意（16R：N = {n_pipe} 条流水线，M = {m} 个平面）", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_planes.png", dpi=160)
    plt.close(fig)


def fig_inj(r4, r8):
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 5.0))
    etas = [0.3 + i * 0.002 for i in range(351)]
    styles = {(4, "worst"): ("#1F3B5C", "-"), (4, "a2a"): ("#1F3B5C", "--"), (8, "worst"): ("#bc4749", "-"), (8, "a2a"): ("#bc4749", "--")}
    for (n, tr), (col, ls) in styles.items():
        r = r4 if n == 4 else r8
        rs = r["cfg"][f"{tr}_ideal"]["rho_star"]
        ks = [max(1, math.ceil(1 / (e * rs) - 1e-9)) for e in etas]
        lbl = f"{n * n}R {'最坏置换' if tr == 'worst' else 'AllToAll'}（ρ* = {rs:g}）"
        ax.step(etas, ks, where="post", color=col, ls=ls, lw=1.6, label=lbl)
        bx.step(etas, [k * r["N_pipe"] * r["pipe_tbps"] for k in ks], where="post", color=col, ls=ls, lw=1.6, label=lbl)
        for rt, mk in (("buf", "o"), ("bl", "s")):
            cc = r["cfg"][f"{tr}_{rt}"]
            ax.plot(cc["eta"], cc["k"], mk, color=col, ms=6, zorder=5)
            bx.plot(cc["eta"], cc["edge_tbps"], mk, color=col, ms=6, zorder=5)
    lo, hi = r4["eta_bl_lo"], r4["eta_bl_hi"]
    for a in (ax, bx):
        a.axvspan(r4["eta_bl_lo"], r4["eta_bl_hi"], color="#f4a261", alpha=0.15, label="bufferless 典型 η")
        a.axvspan(r4["eta_buf_lo"], r4["eta_buf_hi"], color="#6a994e", alpha=0.15, label="buffered 典型 η")
        a.set_xlabel("router 饱和效率 η（可持续注入率 / 理想容量）")
        a.grid(alpha=0.3)
    ax.set_ylabel("每条流水线平面数 k = M / N")
    ax.set_title("(a) k = ⌈1 / (η·ρ*)⌉（○ buffered 取值，□ bufferless 取值）", fontsize=10)
    ax.legend(fontsize=7.5, loc="upper right")
    bx.set_ylabel("每条 die 边单方向 SIO 带宽 M·3.2T（Tbps）")
    bx.set_title("(b) 对应的 die 边带宽", fontsize=10)
    bx.legend(fontsize=7.5, loc="upper right")
    fig.suptitle("单平面注入率约束下的平面数与 die 边带宽", fontsize=12)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_inj.png", dpi=160)
    plt.close(fig)


def fig_floor(r):
    c = r["cfg"][DESIGN]
    n_pipe, m, k, p = r["N_pipe"], c["M"], c["k"], r["pipe_tbps"]
    ox, oy, ow, oh = oe_rect(n_pipe)
    sx, sy, sw_w, sw_h = sw_rect(n_pipe)
    fig = plt.figure(figsize=(16, 9.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[oh + 1.6, sw_h + 1.6], width_ratios=[1.05, 1.0])
    # NOW die
    ax = fig.add_subplot(gs[:, 0])
    box(ax, 0, 0, W, H, C_NOW, ec="#2c3e50", lw=1.4, z=1)
    s = 1.3
    box(ax, 0, s, s, H - 2 * s, C_SIO, f"SIO-西 {m}×{p:g}T", fs=7, rot=90)
    box(ax, W - s, s, s, H - 2 * s, C_SIO, f"SIO-东 {m}×{p:g}T", fs=7, rot=90)
    box(ax, s, H - s, W - 2 * s, s, C_SIO, f"SIO-北 {m}×{p:g}T", fs=7)
    box(ax, s, 0, W - 2 * s, s, C_SIO, f"SIO-南 {m}×{p:g}T", fs=7)
    cw = (W - 3.2) / n_pipe
    for i in range(n_pipe):
        box(ax, 1.6 + i * cw + 0.08, oy + 0.4, cw - 0.16, H - s - 0.3 - (oy + 0.4), "#fde2c8",
            f"OE 切片 {i}\n键合", fs=6.3, ec="#b5651d", lw=0.8)
    box(ax, 1.6, oy - GAP_TOP - 1.9, W - 3.2, GAP_TOP + 2.2, "#fbe3d0",
        f"SW↔OE 点对点 {n_pipe}×{p:g}T：OE 键合 → 跨 ~{GAP_TOP:g} mm 间隙 → SW 线路侧键合（仅数 mm 走线）",
        fs=6.8, ec="#b5651d", lw=0.8)
    rows, cols = k, n_pipe
    x0, y0, x1, y1 = 1.8, s + 1.0, W - 1.8, s + 1.0 + 2.1 * rows
    tw, th = (x1 - x0) / cols, (y1 - y0) / rows
    for g in range(rows):
        for j in range(cols):
            pl = g * n_pipe + j
            box(ax, x0 + j * tw + 0.08, y0 + g * th + 0.08, tw - 0.16, th - 0.16, "white",
                f"R{pl}", fs=6.5, ec=GRP[g % len(GRP)], lw=1.3)
    ax.text(W / 2, y1 + 0.1, f"router 阵列：{rows} 行（组）× {cols} 列，正对上方 SW 交换引擎，共 {m} 个平面 router",
            ha="center", va="bottom", fontsize=7, color="#2d6a4f", zorder=5)
    ym = (y1 + oy - GAP_TOP - 1.9) / 2 + 0.6
    ax.text(W / 2, ym, "router → 四边 SIO 走线 / 中继 + 供电 TSV 网格（为顶层 SW / OE die 供电）",
            ha="center", va="center", fontsize=6.8, color="#555", zorder=5)
    for (px, qx) in ((x0, s), (x1, W - s)):
        arrow(ax, (px, (y0 + y1) / 2), (qx, (y0 + y1) / 2), color=C_RT, lw=1.0)
    ax.set_xlim(-0.5, W + 0.5)
    ax.set_ylim(-0.5, H + 0.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"(a) NOW die（{W:.0f} × {H:.0f} mm，底层整 Reticle；输入缓冲 ≈ {c['buf_now_mb']:.1f} MB 分布在各 router）", fontsize=10)
    # OE die
    cx = fig.add_subplot(gs[0, 1])
    box(cx, 0, 0, ow, oh, C_OE, ec="#b5651d", lw=1.4, z=1)
    sl = ow / n_pipe
    box(cx, 0.2, 0.15, ow - 0.4, 0.75, "#fff3b0", f"电接口 {n_pipe}×{p:g}T（收 + 发，朝南对 SW die，混合键合 → NOW）", fs=6.3)
    box(cx, 0.2, oh - 0.75, ow - 0.4, 0.55, "#fde2c8", "热调谐 / 控制", fs=6.3)
    for i in range(n_pipe):
        xs = i * sl
        box(cx, xs + 0.12, 1.05, sl - 0.24, 0.85, "#fbe3d0", f"切片 {i} Drv/TIA", fs=5.6, lw=0.5)
        box(cx, xs + 0.12, 2.0, (sl - 0.24) / 2 - 0.04, 0.8, "#fbe3d0", "MRM", fs=5.8, lw=0.5)
        box(cx, xs + 0.12 + (sl - 0.24) / 2 + 0.04, 2.0, (sl - 0.24) / 2 - 0.04, 0.8, "#fbe3d0", "PD", fs=5.8, lw=0.5)
        box(cx, xs + 0.12, 2.9, sl - 0.24, oh - 3.75, "#f9ebdf", lw=0.5)
    for fx, fy, fw, fh in fau_rects(r):
        cx.add_patch(Rectangle((fx - ox, 2.85), fw, oh - 3.65, fc=C_FAU, ec="#6d3b47", lw=1.1, alpha=0.45, hatch="///", zorder=5))
        cx.text(fx - ox + fw / 2, 2.85 + (oh - 3.65) / 2, f"光栅耦合 + FAU\n（{r['fau_fibres']} 芯）", ha="center", va="center",
                fontsize=6.8, color="#3b1f26", zorder=6, fontweight="bold")
    cx.set_xlim(-0.4, ow + 0.4)
    cx.set_ylim(-0.4, oh + 0.4)
    cx.set_aspect("equal")
    cx.axis("off")
    cx.set_title(f"(b) OE die（示意 {ow:.0f} × {oh:.1f} mm，{r['oe_tbps']:g}T，{n_pipe} 个光引擎切片，{r['n_fau']} 个 FAU）", fontsize=10)
    # SW die
    bx = fig.add_subplot(gs[1, 1])
    box(bx, 0, 0, sw_w, sw_h, C_SW, ec=C_ENG, lw=1.4, z=1)
    sl = sw_w / n_pipe
    yb = sw_h * 0.52
    for i in range(n_pipe):
        xs = i * sl
        box(bx, xs + 0.1, yb, sl - 0.2, sw_h - yb - 0.15, "#e8f1fb", ec="#5d6d7e", lw=0.8)
        hh = (sw_h - yb - 0.6) / 4
        for t, lbl in enumerate(("OE-IF/MAC", "IPP", "EPP", "TM/队列")):
            box(bx, xs + 0.25, sw_h - 0.45 - (t + 1) * hh, sl - 0.5, hh - 0.15, "#d6eaf8", f"{lbl}\n{i}" if t == 0 else lbl,
                fs=5.6, lw=0.5)
    box(bx, 0.15, 0.2, sw_w - 0.3, yb - 0.45, "#aed6f1", ec=C_ENG, lw=1.2)
    bx.text(sw_w / 2, yb * 0.62, f"交换引擎（{n_pipe} 线路侧 + {m} 交换侧口）：喷洒 / 重排序 / 共享缓冲", ha="center", fontsize=7.5)
    bx.text(sw_w / 2, yb * 0.32, f"正下方即 NOW router 阵列：{m} 个交换侧口经混合键合直连各平面 router 本地口", ha="center",
            fontsize=6.6, color="#2d6a4f")
    bx.text(sw_w / 2, sw_h + 0.15, "北沿：流水线切片的 OE 接口正对 OE die 对应光引擎切片", ha="center", fontsize=6.8, va="bottom")
    bx.set_xlim(-0.4, sw_w + 0.4)
    bx.set_ylim(-0.4, sw_h + 1.4)
    bx.set_aspect("equal")
    bx.axis("off")
    bx.set_title(f"(c) SW die（示意 {sw_w:.0f} × {sw_h:.0f} mm，{n_pipe} 条流水线切片）", fontsize=10)
    fig.suptitle(f"各 die floorplan 示意（16R，最坏置换 buffered 配置：N = {n_pipe}，M = {m}）", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_floor.png", dpi=160)
    plt.close(fig)


def m_raw(r):
    c = r["cfg"][DESIGN]
    return c["gamma"] * r["oe_tbps"] / c["eta"] / r["pipe_tbps"]


def fig_idea(r4, r8):
    """逻辑交换架构：三级 CLOS 布局（SW 上行 → M 个 NoC 平面 → SW 下行）。"""
    c4 = r4["cfg"][DESIGN]
    n_die, n_pipe, m, p = r4["N_die"], r4["N_pipe"], c4["M"], r4["pipe_tbps"]
    fig, ax = plt.subplots(figsize=(11.5, 7.6))
    xs = {1: 8, 2: 41, 3: 74}
    bw, bh = 18, 12
    ys = [67, 49, 15]
    pl_col = ["#2a9d8f", "#e76f51", "#6d597a"]
    sw_lbl = ["SW die 0", "SW die 1", f"SW die {n_die - 1}"]
    pl_lbl = ["NOC 平面 0", "NOC 平面 1", f"NOC 平面 {m - 1}"]
    for s, title in ((1, "第一级：SW die 上行交换\n（n² 个节点）"), (2, "第二级：NOC 交换平面\n（M 个，相互独立）"),
                     (3, "第三级：SW die 下行交换\n（n² 个节点）")):
        ax.text(xs[s] + bw / 2, 87, title, ha="center", va="center", fontsize=11.5, fontweight="bold")
    for i in range(3):
        for j in range(3):
            for (sa, sb, ya, yb) in ((1, 2, ys[i], ys[j]), (2, 3, ys[j], ys[i])):
                ax.plot([xs[sa] + bw, xs[sb]], [ya + bh / 2, yb + bh / 2], color=pl_col[j], lw=1.3, alpha=0.85, zorder=1)
    for i, y in enumerate(ys):
        box(ax, xs[1], y, bw, bh, C_SW, f"{sw_lbl[i]}  上行\nN 入 × M 出（各 {p:g}T）\n均匀喷洒到 M 个平面", fs=9.5, ec=C_ENG, lw=1.4)
        box(ax, xs[2], y, bw, bh, "#e3efd9", f"{pl_lbl[i]}\n= {n_die} 端口 switch\n（NOC 实现，每口 {p:g}T）", fs=9.5,
            ec=pl_col[i], lw=1.8)
        box(ax, xs[3], y, bw, bh, C_SW, f"{sw_lbl[i]}  下行\nM 入 × N 出（各 {p:g}T）\n按流重排序", fs=9.5, ec=C_ENG, lw=1.4)
        for t in (-3, 0, 3):
            arrow(ax, (xs[1] - 6, y + bh / 2 + t), (xs[1], y + bh / 2 + t), color="#5d6d7e", lw=1.0, both=False)
            arrow(ax, (xs[3] + bw, y + bh / 2 + t), (xs[3] + bw + 6, y + bh / 2 + t), color="#5d6d7e", lw=1.0, both=False)
        ax.text(xs[1] - 6.5, y + bh / 2, f"N × {p:g}T\n线路侧\nIPP", ha="right", va="center", fontsize=9)
        ax.text(xs[3] + bw + 6.5, y + bh / 2, f"N × {p:g}T\n线路侧\nEPP", ha="left", va="center", fontsize=9)
    for s in (1, 2, 3):
        ax.text(xs[s] + bw / 2, 38, "⋮", ha="center", va="center", fontsize=18)
    raw4, raw8 = m_raw(r4), m_raw(r8)
    c8 = r8["cfg"][DESIGN]
    txt = ("M = 单边加速比 × SW 线路侧带宽 × NOC 加速比 / 单 NOC 平面带宽 = (n/2) · B_die · (1/η) / P，向上取到 N 的倍数（M = kN）\n"
           f"16R：n² = {n_die}，N = {n_pipe}，{c4['gamma']:g} × {r4['oe_tbps']:g}T × 1/{c4['eta']:g} / {p:g}T = {raw4:g} → M = {m}（k = {c4['k']}）\n"
           f"64R：n² = {r8['N_die']}，N = {r8['N_pipe']}，{c8['gamma']:g} × {r8['oe_tbps']:g}T × 1/{c8['eta']:g} / {p:g}T = {raw8:g} → M = {c8['M']}（k = {c8['k']}）\n"
           f"每条连线 = 1 个 {p:g}T 交换侧管道（SW die i 的第 p 个管道 ↔ 平面 p）\n"
           "第一级与第三级是同一颗 SW die 的入向 / 出向（折叠 CLOS）；平面之间没有链路，跨平面只发生在第一级喷洒与第三级重排序")
    ax.text(50, 6, txt, ha="center", va="top", fontsize=9.3, linespacing=1.6,
            bbox=dict(boxstyle="round,pad=0.5", fc="#f8f9f9", ec="#aab7b8"))
    ax.set_xlim(-10, 110)
    ax.set_ylim(-17, 92)
    ax.axis("off")
    ax.set_title(f"逻辑交换架构：三级 CLOS 布局（16R：n² = {n_die}，N = {n_pipe}，M = {m}）", fontsize=12.5)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_stk_idea.png", dpi=160)
    plt.close(fig)


def now_die_planes(ax, x0, y0, d, m, cols, lw=0.6, rs=0.22, lab=False):
    box(ax, x0, y0, d, d, C_NOW, ec="#2c3e50", lw=1.2, z=1)
    s = 0.07 * d
    for (bx_, by_, bw_, bh_) in ((x0, y0, d, s), (x0, y0 + d - s, d, s), (x0, y0, s, d), (x0 + d - s, y0, s, d)):
        ax.add_patch(Rectangle((bx_, by_), bw_, bh_, fc=C_SIO, ec="none", alpha=0.55, zorder=1.5))
    off = [0.16 * d + q * 0.68 * d / max(1, m - 1) for q in range(m)]
    for q, o in enumerate(off):
        ax.plot([x0, x0 + d], [y0 + o, y0 + o], color=cols[q], lw=lw, zorder=2)
        ax.plot([x0 + o, x0 + o], [y0, y0 + d], color=cols[q], lw=lw, zorder=2)
        ax.add_patch(Rectangle((x0 + o - rs / 2, y0 + o - rs / 2), rs, rs, fc=cols[q], ec="#1b2631", lw=0.5, zorder=4))
        ax.plot(x0 + o, y0 + o, marker="o", ms=1.2 if not lab else 2.4, color="white", zorder=5)
    return off


def fig_now_planes(r):
    c = r["cfg"][DESIGN]
    n, m, k, n_pipe, p = r["n"], c["M"], c["k"], r["N_pipe"], r["pipe_tbps"]
    cmap = plt.get_cmap("turbo")
    cols = [cmap(0.05 + 0.9 * q / max(1, m - 1)) for q in range(m)]
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(13, 7.6), gridspec_kw=dict(width_ratios=[1.0, 1.0]))
    d, g = 10.0, 1.6
    for i in range(n):
        for j in range(n):
            x0, y0 = i * (d + g), j * (d + g)
            off = now_die_planes(ax, x0, y0, d, m, cols, lw=0.45, rs=0.26)
            ax.text(x0 + 0.25, y0 + d - 0.3, f"({n - 1 - j},{i})", fontsize=7.5, va="top", color="#2c3e50", zorder=6)
            if i + 1 < n:
                for q, o in enumerate(off):
                    ax.plot([x0 + d, x0 + d + g], [y0 + o, y0 + o], color=cols[q], lw=0.45, zorder=2)
            if j + 1 < n:
                for q, o in enumerate(off):
                    ax.plot([x0 + o, x0 + o], [y0 + d, y0 + d + g], color=cols[q], lw=0.45, zorder=2)
    span = n * d + (n - 1) * g
    ax.text(span / 2, -1.2, f"{n}×{n} 个 NOW die（{r['N_die']} 个 Reticle），每颗含 {m} 个平面 router\n"
                            f"die 间缝隙中的线 = SIO 链路（每平面每方向 {p:g}T）\n"
                            "同颜色 = 同一平面：平面 p 只连相邻 NOW die 的平面 p，\n构成一张独立的 Mesh",
            ha="center", va="top", fontsize=10, linespacing=1.5)
    ax.set_xlim(-1, span + 1)
    ax.set_ylim(-13, span + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(f"(a) 顶视：{n}×{n} NOW die 上的 {m} 个 NOC 平面", fontsize=13.1)
    # (b) single NOW die zoom
    D = 20.0
    off = now_die_planes(bx, 0, 0, D, m, cols, lw=1.0, rs=0.5, lab=True)
    for q in sorted({0, 1, 2, m // 2, m - 1}):
        bx.text(off[q], -0.6, f"{q}", fontsize=8.1, ha="center", va="top", color=cols[q])
    bx.text(-0.4, -0.6, "平面编号", fontsize=8.5, ha="right", va="top")
    for (pt, qt, t, ha, va) in (((D * 0.3, D), (D * 0.3, D + 2.6), "北邻 NOW die", "center", "bottom"),
                                ((D * 0.3, 0), (D * 0.3, -2.4), "南邻 NOW die", "left", "top"),
                                ((0, D / 2), (-2.6, D / 2), "西邻\nNOW die", "right", "center"),
                                ((D, D / 2), (D + 2.6, D / 2), "东邻\nNOW die", "left", "center")):
        arrow(bx, pt, qt, color="#7f8c8d", lw=1.4)
        bx.text(qt[0] + {"right": -0.3, "left": 0.3, "center": 0}[ha], qt[1] + {"bottom": 0.3, "top": 0, "center": 0}[va], t,
                ha=ha, va=va, fontsize=10)
    q0 = m // 2
    bx.annotate(f"⊙ 平面 {q0} 本地口：\n混合键合 ↑\nSW die 交换侧口 {q0}\n（{p:g}T；每颗 die\n共 {m} 个本地口）",
                xy=(off[q0], off[q0]), xytext=(D + 0.8, D * 0.05), fontsize=9.5, zorder=8,
                arrowprops=dict(arrowstyle="-|>", color="#2a6f97", lw=1.1))
    qa, qb = 3, m - 4
    bx.annotate("不同平面的走线交叉但不相连\n（不同金属层，无 router）", xy=(off[qb], off[qa]), xytext=(D * 0.55, D * 0.04), fontsize=9.5,
                zorder=8, ha="center", arrowprops=dict(arrowstyle="-|>", color="#c0392b", lw=1.0),
                bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#c0392b", lw=0.6))
    bx.text(D * 0.5, D + 5.6, f"四边 SIO PHY（黄色条带）：\n每边每方向 {m} × {p:g}T = {c['edge_tbps']:g}T",
            ha="center", fontsize=10.2, color="#9a7d0a")
    bx.text(-6, -4.6, f"每个平面 router：5 口（本地 + 东南西北），每口 {p:g}T；\n"
                      f"{m} 个平面 = {k} 组 × {n_pipe}，平面之间不相互通信。\n"
                      "router 沿对角线排布只为显示各平面走线独立；\n实际 router 阵列位于 SW 交换引擎正下方（见 floorplan）",
            fontsize=9.4, va="top", linespacing=1.5)
    bx.set_xlim(-7, D + 11)
    bx.set_ylim(-13, D + 9)
    bx.set_aspect("equal")
    bx.axis("off")
    bx.set_title(f"(b) 单颗 NOW die：{m} 个平面 router 与走线", fontsize=13.1)
    fig.suptitle(f"n×n NOW die 上实现 M 个 NOC 交换平面（16R：{n}×{n} die，M = {m}，顶视示意）", fontsize=13.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(F.FIG / "fig_stk_now_planes.png", dpi=160)
    plt.close(fig)


def main():
    r4, r8 = load(4), load(8)
    fig_idea(r4, r8)
    fig_now_planes(r4)
    fig_stack(r4, r8)
    fig_arch(r4)
    fig_planes(r4)
    fig_inj(r4, r8)
    fig_floor(r4)
    print("fig_stk_idea.png fig_stk_now_planes.png fig_stk_stack.png fig_stk_arch.png fig_stk_planes.png fig_stk_inj.png fig_stk_floor.png")


if __name__ == "__main__":
    main()
