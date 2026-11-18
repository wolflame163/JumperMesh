#!/usr/bin/env python3
"""给定流量矩阵下的 die2die 流量带宽图（各方案 x.x.7 节）。

格式同物理构型图（有向边逻辑链路条数）：每条有向边标注 xx/yy（Tbps），
xx = 该流量矩阵下的实际流量，yy = 该边的逻辑链路总带宽（= 物理构型图的边带宽）。

输出：figs/fig_flow_{scheme}_{scenario}_{n}x{n}.png
校验：Σ_e xx × 0.35 × 0.3 = 该场景的 SIO 动态功耗（结果 JSON）。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figs_workflow as WF  # noqa: E402
from figs_workflow import DATA, FIG, M, TITLE, parse_edge  # noqa: E402

import dsl_l1l3_direct as L13  # noqa: E402

SCEN = {
    "xy_o1turn_cw": [("a2a_100", "最佳 / 最差 / AllToAll（CLOS 两级喷洒下三者逐边相同）")],
    "manhattan": [("a2a_100", "最佳 / 最差 / AllToAll（CLOS 两级喷洒下三者逐边相同）")],
    "s3_10": [("a2a_100", "最佳 / AllToAll 满载（直连满用）"),
              ("perm_100", "最差：置换满载（直连只承载 b，按均匀随机置换取期望 b/N）")],
    "o1t": [("perm_best", "最佳置换（最小搬移指派）"), ("perm_worst", "最差置换（最大搬移指派）"),
            ("a2a_100", "AllToAll 满载")],
}


def ekey(a, b) -> str:
    return f"{a[0]},{a[1]}->{b[0]},{b[1]}"


def add_path(load, p, rate):
    for a, b in zip(p[:-1], p[1:]):
        load[ekey(a, b)] += rate


def clos_spray(n, paths, b, T):
    """CLOS 两级喷洒：r(L1_i→L2_j)=Σ_k T(i,k)/N，r(L2_j→L3_k)=Σ_i T(i,k)/N。"""
    N = n * n
    pos = [(r, c) for r in range(n) for c in range(n)]
    r1, r2 = defaultdict(float), defaultdict(float)
    for (i, k), t in T.items():
        for j in pos:
            r1[(i, j)] += t / N
            r2[(j, k)] += t / N
    load = defaultdict(float)
    for key, p in paths.items():
        st, a, c = key.split("|")
        s, d = tuple(map(int, a.split(","))), tuple(map(int, c.split(",")))
        add_path(load, p, (r1 if st == "1" else r2)[(s, d)])
    return load


def scenario_loads(n: int, sc: str) -> tuple[dict, dict, dict]:
    """返回 (yy 逻辑链路总带宽, {场景: xx 实际流量}, {场景: SIO 动态功耗参考值})。"""
    rec = WF.scheme_record(n, sc)
    yy = rec["loads"]
    b = rec["b"]
    N = n * n
    pos = [(r, c) for r in range(n) for c in range(n)]
    xx, ref = {}, {}
    if sc in ("xy_o1turn_cw", "manhattan"):
        r = json.loads((DATA / f"dsl_{n}x{n}.json").read_text())[sc]
        a2a = clos_spray(n, r["paths"], b, {(i, k): b for i in pos for k in pos})
        perm = clos_spray(n, r["paths"], b, {(i, pos[(t + 1) % N]): N * b for t, i in enumerate(pos)})
        for k in yy:
            assert abs(a2a[k] - yy[k]) < 1e-9 and abs(perm[k] - yy[k]) < 1e-9
        xx["a2a_100"] = dict(a2a)
        ref["a2a_100"] = r["power"]["0.1"]["scenarios"]["a2a_100"]["sio_W"] - r["power"]["0.1"]["sio_static_W"]
    elif sc == "s3_10":
        base = json.loads((DATA / f"dsl_{n}x{n}.json").read_text())["manhattan"]
        r = json.loads((DATA / f"dsl_l1l3_{n}x{n}.json").read_text())["10"]
        directs = {(tuple(d["i"]), tuple(d["k"])): [tuple(x) for x in d["path"]] for d in r["directs"]}
        dset = dict(directs)
        dset.update({(i, i): [i] for i in pos})
        mesh = M.build_mesh(n)
        for key, _ in SCEN[sc]:
            T, D = L13.scenario_traffic(mesh, key, b, dset)
            load = clos_spray(n, base["paths"], b, {ik: t - D.get(ik, 0.0) for ik, t in T.items()})
            for ik, p in directs.items():
                add_path(load, p, D.get(ik, 0.0))
            xx[key] = dict(load)
            ref[key] = r["power"]["0.1"]["scenarios"][key]["sio_dyn_W"]
    else:
        r = rec["raw"]
        xx["a2a_100"] = rec["a2a"]
        ref["a2a_100"] = r["power"]["0.1"]["scenarios"]["a2a_100"]["sio_dyn_W"]
        sc_o = WF.o1t_scenarios(n, with_load=True)
        for key in ("perm_best", "perm_worst"):
            xx[key] = sc_o[key]["load"]
            ref[key] = r["power"]["0.1"]["scenarios"][key]["sio_dyn_W"]
    for key, load in xx.items():
        dyn = sum(load.values()) * M.SIO_PJ * M.SIO_DYN
        assert abs(dyn - ref[key]) < 1e-6 * max(1.0, ref[key]), (sc, key, dyn, ref[key])
        assert all(load.get(k, 0.0) <= yy[k] + 1e-9 for k in yy), (sc, key)
    return yy, xx, ref


def fig_flow(n: int, sc: str, key: str, label: str, yy: dict, xx: dict, tag: str):
    W, H, G = M.DIE_W_MM, M.DIE_H_MM, 6.0
    big = n > 4
    fig, ax = plt.subplots(figsize=(15.5, 12.4) if big else (11.0, 7.8))
    off = 2.2 if big else 3.2
    lw = 1.4 if big else 2.4
    cmap = plt.cm.YlOrRd
    vmax = max(yy.values())
    xmax = max(xx.values()) if xx else 0.0
    for r in range(n):
        for c in range(n):
            x, y = c * (W + G), r * (H + G)
            ax.add_patch(Rectangle((x, y), W, H, fc="#f3f6fa", ec="#1F3B5C", lw=1.0, zorder=1))
            ax.text(x + W / 2, y + H / 2, f"die {r * n + c}" if not big else str(r * n + c), ha="center",
                    va="center", fontsize=9 if not big else 6.5, color="#888", zorder=2)
    for k, y_ in yy.items():
        x_ = xx.get(k, 0.0)
        (r0, c0), (r1, c1) = parse_edge(k)
        x0, y0 = c0 * (W + G) + W / 2, r0 * (H + G) + H / 2
        x1, y1 = c1 * (W + G) + W / 2, r1 * (H + G) + H / 2
        xs, ys = x0 + 0.30 * (x1 - x0), y0 + 0.30 * (y1 - y0)
        xe, ye = x0 + 0.70 * (x1 - x0), y0 + 0.70 * (y1 - y0)
        if r0 == r1:
            dy = -off if c1 > c0 else off
            ys, ye = ys + dy, ye + dy
        else:
            dx = off if r1 > r0 else -off
            xs, xe = xs + dx, xe + dx
        hot = xmax > 0 and abs(x_ - xmax) < 1e-9
        col = cmap(0.15 + 0.85 * min(x_ / vmax, 1.0)) if x_ > 1e-12 else "#c9ced6"
        ax.annotate("", xy=(xe, ye), xytext=(xs, ys),
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=lw * (1.4 if hot else 1.0),
                                    ls="-" if x_ > 1e-12 else "--", mutation_scale=6 if big else 9), zorder=3)
        mx, my = (xs + xe) / 2, (ys + ye) / 2
        if r0 == r1:
            my += (-2.4 if c1 > c0 else 2.4) if not big else (-1.9 if c1 > c0 else 1.9)
        else:
            mx += (4.4 if r1 > r0 else -4.4) if not big else (5.2 if r1 > r0 else -5.2)
        ax.text(mx, my, f"{x_:.1f}/{y_:.1f}" if not big else f"{x_:.1f}/{y_:.1f}", ha="center", va="center",
                fontsize=6.6 if not big else 5.0, rotation=0,
                color="#7a0000" if hot else "#333", fontweight="bold" if hot else "normal", zorder=4)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=plt.Normalize(0, vmax))
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01)
    cb.set_label("实际流量 xx（Tbps）", fontsize=9)
    ax.set_xlim(-6, n * (W + G))
    ax.set_ylim(n * (H + G) + 14, -4)
    ax.set_aspect("equal")
    ax.axis("off")
    tot_x, tot_y = sum(xx.get(k, 0.0) for k in yy), sum(yy.values())
    used = sum(1 for k in yy if xx.get(k, 0.0) > 1e-12)
    ax.text(n * (W + G) / 2 - G / 2, n * (H + G) + 2,
            f"每条有向边标注 xx/yy（Tbps）：xx = 该流量矩阵下的实际 die2die 流量，yy = 该边逻辑链路总带宽（同物理构型图）；"
            f"灰色虚线 = 该场景无流量\n"
            f"最热边实际流量 {xmax:.1f}T（加粗）· 有流量的有向边 {used}/{len(yy)} 条 · "
            f"D2D 实际流量合计 {tot_x:,.0f}T / 逻辑链路带宽合计 {tot_y:,.0f}T（{tot_x / tot_y:.0%}）",
            ha="center", va="top", fontsize=9)
    ax.set_title(f"die2die 流量带宽：{TITLE[sc]}（{n}×{n}）— {label}", fontsize=12)
    fig.tight_layout()
    out = FIG / f"fig_flow_{sc}_{tag}_{n}x{n}.png"
    fig.savefig(out, dpi=300 if big else 160)
    plt.close(fig)
    return out, dict(xmax=xmax, used=used, n_edges=len(yy), tot_x=tot_x, tot_y=tot_y)


def main():
    for n in (4, 8):
        for sc, lst in SCEN.items():
            yy, xx, _ = scenario_loads(n, sc)
            for key, label in lst:
                out, st = fig_flow(n, sc, key, label, yy, xx[key], key)
                print(out.name, {k: round(v, 2) if isinstance(v, float) else v for k, v in st.items()})


if __name__ == "__main__":
    main()
