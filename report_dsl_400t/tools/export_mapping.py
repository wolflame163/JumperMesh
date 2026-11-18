#!/usr/bin/env python3
"""把各方案逐条逻辑链路的物理映射结果导出为文本 log：data/*.json → output/mapping/*.log。

坐标约定与计算代码一致：die (r, c)，r 自上而下、c 自左而右，die 编号 = r·n + c。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "output"
MAP = OUT / "mapping"
sys.path.insert(0, str(ROOT.parent))
import dsl_mesh_400t as M  # noqa: E402

SIZES = (4, 8)
SCHEME_FILE = {"xy_o1turn_cw": "s1_dsl_xy", "manhattan": "s2_dsl_shortest"}
SCHEME_TITLE = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由"}


def did(rc, n):
    return rc[0] * n + rc[1]


def coord(s):
    r, c = s.split(",")
    return int(r), int(c)


def fmt_path(p, n):
    return " -> ".join(f"{did(x, n)}({x[0]},{x[1]})" for x in p)


def row(link, src, dst, p, n, t_sw=M.T_SW_SW):
    m = M.path_metrics([tuple(x) for x in p], t_sw=t_sw)
    return (f"{link:<22} {did(src, n):>4} {did(dst, n):>4} {m['hops']:>4} {m['turns']:>5} "
            f"{m['wire_mean']:>9.1f} {m['wire_max']:>9.1f} {m['lat_max']:>9.1f}  {fmt_path(p, n)}")


COLS = (f"{'逻辑链路':<18} {'src':>4} {'dst':>4} {'hops':>4} {'turns':>5} "
        f"{'wire_mean':>9} {'wire_max':>9} {'lat_max':>9}  物理路径（die 编号(r,c)，逐 die）")


def header(title, n, extra):
    N = n * n
    b = M.SYSTEM_TBPS / (N * N)
    return [f"# {title}  —  {n}x{n} 2D Mesh，N = {N}",
            "# 坐标：die (r, c)，r 自上而下、c 自左而右；die 编号 = r*n + c；仅相邻 die 互联",
            f"# 映射粒度：每行 = 1 条逻辑链路，带宽 b = {b:g} Tbps（不可拆分）；"
            f"16R 为 1.6T，64R 为 0.1T；物理路径上的每一跳占用 1 个 b 粒度的 SIO/馈通端口",
            "# 列：hops = die 间跳数；turns = 转弯次数；wire_mean / wire_max = 均值 / 最坏口径馈通走线（mm，不含缝隙）；"
            "lat_max = 最坏口径路径时延（ns，含转向 2 ns/次与一次 t_sw_die；CLOS 链路另含 t_sw_sw，直连与 O1Turn(DR) 不含）",
            *[f"# {x}" for x in extra], "#", "# " + COLS]


def export_clos(n, d):
    out = []
    for sc, stem in SCHEME_FILE.items():
        r = d[sc]
        b = r["b_tbps"]
        lines = header(SCHEME_TITLE[sc], n, [
            f"逻辑拓扑：三级共址 CLOS({n * n},{n * n},{n * n})，L1_i / L2_i / L3_i 位于 die i；每条逻辑链路 {b:g} Tbps",
            f"逻辑链路：die 间 {r['n_flows']} 条 + 同 die {2 * n * n} 条（0 跳，不占 die 间带宽）",
            f"结果：最热有向边 {r['C']} 条 = {r['C_tbps']:.1f} Tbps（二分下界 {r['lb']} 条）；平均 {r['hops_mean']:.2f} 跳",
        ])
        paths = r["paths"]
        for st, (a, z) in ((1, ("L1", "L2")), (2, ("L2", "L3"))):
            lines.append(f"\n## stage {st}：{a} -> {z}")
            for i in range(n * n):
                si = (i // n, i % n)
                for j in range(n * n):
                    sj = (j // n, j % n)
                    p = [si] if i == j else paths[f"{st}|{si[0]},{si[1]}|{sj[0]},{sj[1]}"]
                    lines.append(row(f"{a}_{i}->{z}_{j}", si, sj, p, n))
        fn = MAP / f"{stem}_{n}x{n}.log"
        fn.write_text("\n".join(lines) + "\n")
        out.append(fn)
    return out


def export_s3(n, s3):
    out = []
    for x, r in s3.items():
        lines = header(f"方案三 DSL+直连（x = {x}%）", n, [
            "CLOS 部分的逻辑链路与物理路径与方案二完全相同，见 s2_dsl_shortest 对应 log；本文件只列叠加的直连",
            f"die 间直连 {r['n_directs']} 条 + 片内直连 {r['local_directs']} 条（L1_i->L3_i，0 跳），每条 {r['b_tbps']:g} Tbps",
            f"结果：最热有向边 {r['C_tbps']:.1f} Tbps（方案二 {r['scheme2_C_tbps']:.1f} Tbps，增长 {100 * r['d2d_growth']:+.1f}%）",
            "最后一列 twohop_lat：该 die 对原经 L2 两跳的最坏时延（ns）",
        ])
        lines[-1] = lines[-1] + "  twohop_lat"
        for i in range(n * n):
            si = (i // n, i % n)
            lines.append(row(f"L1_{i}->L3_{i}(片内)", si, si, [si], n, t_sw=0.0))
        for dr in sorted(r["directs"], key=lambda q: (did(q["i"], n), did(q["k"], n))):
            i, k = tuple(dr["i"]), tuple(dr["k"])
            lines.append(row(f"L1_{did(i, n)}->L3_{did(k, n)}", i, k, dr["path"], n, t_sw=0.0) + f"  {dr['twohop_lat']:.1f}")
        fn = MAP / f"s3_l1l3_direct_x{x}_{n}x{n}.log"
        fn.write_text("\n".join(lines) + "\n")
        out.append(fn)
    return out


def export_o1t(n, o):
    lines = header("方案四 O1Turn(DR)（die 级 NoC，不用 CLOS）", n, [
        "每颗 die 为 NoC router；src die -> dst die 的流量按顺时针（cw）与逆时针（ccw）O1Turn 各 50% 逐 die 转发（单转弯）",
        "同行 / 同列的 die 对两条路径相同（直线）",
        f"无阻塞所需单边带宽 (n/2) x B_die = {o['C_tbps']:.1f} Tbps（邻 die 加速比 n/2 = {o['C_die']:g}，4 边总加速比 2n = {2 * n}）",
    ])
    for i in range(n * n):
        si = (i // n, i % n)
        for j in range(n * n):
            if i == j:
                continue
            sj = (j // n, j % n)
            key = f"{si[0]},{si[1]}|{sj[0]},{sj[1]}"
            lines.append(row(f"die{i}->die{j} cw", si, sj, o["paths"][key], n, t_sw=M.T_SW_SW_O1T))
            lines.append(row(f"die{i}->die{j} ccw", si, sj, o["paths_ccw"][key], n, t_sw=M.T_SW_SW_O1T))
    fn = MAP / f"s4_o1turn_noc_{n}x{n}.log"
    fn.write_text("\n".join(lines) + "\n")
    return [fn]


def main():
    MAP.mkdir(parents=True, exist_ok=True)
    files = []
    for n in SIZES:
        files += export_clos(n, json.loads((DATA / f"dsl_{n}x{n}.json").read_text()))
        files += export_s3(n, json.loads((DATA / f"dsl_l1l3_{n}x{n}.json").read_text()))
        files += export_o1t(n, json.loads((DATA / f"dsl_o1t_{n}x{n}.json").read_text()))
    for f in files:
        print(f.relative_to(OUT), sum(1 for _ in f.open()) , "lines")


if __name__ == "__main__":
    main()
