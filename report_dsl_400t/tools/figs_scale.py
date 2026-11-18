#!/usr/bin/env python3
"""第 4 章 16R（4×4）与 64R（8×8）对比图：figs/fig_scale.png。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figs as F  # noqa: E402  (字体与输出目录)
import build_pdf as B  # noqa: E402

plt = F.plt
SHORT = {"xy_o1turn_cw": "方案一", "manhattan": "方案二", "s3_0": "方案三\nx=0", "s3_10": "方案三\nx=10%", "o1t": "方案四"}
C16, C64 = "#8fb3d9", "#1F3B5C"


def bars(ax, v16, v64, fmt):
    xs = range(len(B.CROSS))
    w = 0.38
    b1 = ax.bar([x - w / 2 for x in xs], v16, w, color=C16, label="16R（4×4）")
    b2 = ax.bar([x + w / 2 for x in xs], v64, w, color=C64, label="64R（8×8）")
    for bb, vals in ((b1, v16), (b2, v64)):
        for rect, v in zip(bb, vals):
            ax.text(rect.get_x() + rect.get_width() / 2, rect.get_height(), fmt(v), ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(list(xs), [SHORT[s] for s in B.CROSS], fontsize=8.5)
    ax.legend(fontsize=8, loc="upper center")
    ax.set_ylim(0, max(v64 + v16) * 1.15)
    ax.grid(axis="y", alpha=0.3)


def stacked(ax, parts, colors, labels, share_key, share_lbl):
    xs = []
    for k, n in enumerate((4, 8)):
        for j, sc in enumerate(B.CROSS):
            x = k * (len(B.CROSS) + 1) + j
            xs.append((x, n, sc))
    for x, n, sc in xs:
        vals = parts(n, sc)
        tot = sum(vals)
        bottom = 0
        for v, c in zip(vals, colors):
            ax.bar(x, 100 * v / tot, 0.75, bottom=bottom, color=c)
            bottom += 100 * v / tot
        ax.text(x, 101, f"{100 * share_key(n, sc):.0f}%", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks([x for x, _, _ in xs], [SHORT[s].replace("\n", "") for _, _, s in xs], fontsize=7, rotation=60)
    for k, n in enumerate((4, 8)):
        ax.text(k * (len(B.CROSS) + 1) + 2, 112, f"{n * n}R（{n}×{n}）", ha="center", fontsize=9, fontweight="bold")
    ax.set_ylim(0, 120)
    ax.set_ylabel("占比（%）")
    for c, l in zip(colors, labels):
        ax.bar(0, 0, color=c, label=l)
    ax.legend(fontsize=7.5, loc="lower center", bbox_to_anchor=(0.5, -0.36), ncol=len(labels))
    ax.set_title(share_lbl, fontsize=10.5)


def main():
    ds = B.load_data()
    fig, axs = plt.subplots(2, 2, figsize=(13, 9.6))
    a = axs[0][0]
    bars(a, [ds[4][s]["sp_edge"] for s in B.CROSS], [ds[8][s]["sp_edge"] for s in B.CROSS], lambda v: f"{v:.2f}×")
    a.set_ylabel("单边加速比（最热边 / B_die）")
    a.set_title("(a) die 间单边加速比（方案四为无阻塞所需）", fontsize=10.5)
    a = axs[0][1]
    bars(a, [ds[4][s]["e2e_wire_mean"] for s in B.CROSS], [ds[8][s]["e2e_wire_mean"] for s in B.CROSS], lambda v: f"{v:.0f}")
    for k, s in enumerate(B.CROSS):
        a.plot([k - 0.19], [ds[4][s]["e2e_wire_max"]], "v", color=C16, ms=6)
        a.plot([k + 0.19], [ds[8][s]["e2e_wire_max"]], "v", color=C64, ms=6)
    a.set_ylim(0, max(ds[8][s]["e2e_wire_max"] for s in B.CROSS) * 1.1)
    a.legend(fontsize=8, loc="upper right")
    a.set_ylabel("端到端走线（mm）")
    a.set_title("(b) 端到端平均走线（柱）与最大走线（▼）", fontsize=10.5)
    stacked(axs[1][0], lambda n, s: (ds[n][s]["lw"]["sio"], ds[n][s]["lw"]["ft"], ds[n][s]["lw"]["turn"],
                                     ds[n][s]["lw"]["sw_die"], ds[n][s]["lw"]["sw_sw"]),
            ("#f4a261", "#2a6f97", "#9b5de5", "#e09f3e", "#6a994e"),
            ("SIO 接口", "馈通走线", "转向", r"$t_{sw\_die}$", r"$t_{sw\_sw}$"),
            lambda n, s: ds[n][s]["lw"]["wire_share"], "(c) 最坏路径时延构成（顶部数字为馈通走线占比）")
    stacked(axs[1][1], lambda n, s: (ds[n][s]["power"]["0.1"]["serdes_W"], ds[n][s]["power"]["0.1"]["sio_W"],
                                     ds[n][s]["power"]["0.1"]["wire_W"], ds[n][s]["power"]["0.1"]["line_W"]),
            ("#bbbbbb", "#f4a261", "#2a6f97", "#8fb3d9"), ("SerDes", "SIO", "die 间走线", "线路侧走线"),
            lambda n, s: ds[n][s]["power"]["0.1"]["move_share_total"], "(d) 满载芯片功耗构成（顶部数字为数据搬移占比，0.1 pJ/bit/mm）")
    fig.suptitle("16R（4×4）与 64R（8×8）对比", fontsize=13)
    fig.tight_layout()
    fig.savefig(F.FIG / "fig_scale.png", dpi=160)
    plt.close(fig)
    print("fig_scale.png")


if __name__ == "__main__":
    main()
