#!/usr/bin/env python3
"""方案四 O1Turn(DR)：n×n die 2D Mesh，每颗 die 为同构 NoC router（1 组线路侧 + 4 组邻 die 交换侧），
src die → dst die 的流量按顺时针与逆时针 O1Turn 两条单转弯路径各 50% 转发（无 CLOS、无喷洒）。

无阻塞要求：任意可容许流量（每颗 die 注入、接收均 ≤ 1.0 = 409.6T/N）下边不过载。
(src, dst) 对在边 e 上的权重 w ∈ {0, 0.5, 1}（经过 e 的路径数 × 0.5）；流量矩阵的极点为置换，
边 e 的最坏负载 = 权重矩阵的最大权指派。单转弯路径的水平段只在源行（XY）或宿行（YX），
向右边 (r, c→c+1) 的负载 ≤ 0.5·(c+1) + 0.5·(n−1−c) = n/2，即二分下界，且可达到。

走线 / 时延 / 功耗沿用 dsl_mesh_400t.py 的模型（两条路径的跳数、转向、馈通与时延相同）；过路 die 的 router 转发按
Feedthrough 走线（0.5 ns/mm）与转向（2 ns/次）计，t_sw_sw = 0；端到端计一次 t_sw_die = 120 ns。

Usage:
  python3 dsl_o1turn_noc.py --sizes 4 8 --out report_dsl_400t/data
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

import dsl_mesh_400t as M


SPLIT = 0.5  # 顺时针 / 逆时针各承担的流量比例


def ring_diagonal(n: int):
    """最外一圈 die 与其中心对称 die 互打（每颗 die 1.0）。"""
    pos = [(r, c) for r in range(n) for c in range(n)]
    ring = [p for p in pos if p[0] in (0, n - 1) or p[1] in (0, n - 1)]
    return [(s, (n - 1 - s[0], n - 1 - s[1])) for s in ring]


def run(n: int) -> dict:
    mesh = M.build_mesh(n)
    N = mesh.n
    pos = mesh.positions
    die_bw = M.SYSTEM_TBPS / N
    b = die_bw / N  # AllToAll 下每个 die 对的流量
    paths = {(s, d): M.route_o1turn_cw(s, d) for s in pos for d in pos if s != d}
    paths_ccw = {(s, d): M.route_o1turn_cw(s, d, clockwise=False) for (s, d) in paths}
    met = {k: M.path_metrics(p, t_sw=M.T_SW_SW_O1T) for k, p in paths.items()}
    for k, p in paths_ccw.items():
        mc = M.path_metrics(p, t_sw=M.T_SW_SW_O1T)
        for key in ("hops", "lat_max", "lat_mean", "ft_mean", "wire_max"):
            assert abs(mc[key] - met[k][key]) < 1e-9, (k, key)
    edges = M.directed_edges(mesh)

    # (src, dst) 在每条有向边上的权重：经过该边的路径数 × SPLIT
    weight = defaultdict(lambda: defaultdict(float))
    for k in paths:
        for p in (paths[k], paths_ccw[k]):
            for e in M.path_edges(p):
                weight[e][k] += SPLIT

    # 每条有向边的无阻塞（最坏置换）负载，单位：die 带宽
    idx = {p: i for i, p in enumerate(pos)}
    worst = {}
    witness = {}
    for e in edges:
        Wm = np.zeros((N, N))
        for (s, d), w in weight[e].items():
            Wm[idx[s], idx[d]] = w
        ri, ci = linear_sum_assignment(Wm, maximize=True)
        worst[e] = float(Wm[ri, ci].sum())
        witness[e] = [(pos[i], pos[j]) for i, j in zip(ri, ci) if Wm[i, j] > 0]
    a2a = {e: sum(weight[e].values()) for e in edges}  # 条（每条 b）
    C = max(worst.values())
    assert abs(C - n / 2) < 1e-9 and abs(min(worst.values()) - n / 2) < 1e-9, (C, n)
    diag = ring_diagonal(n)
    diag_load = defaultdict(float)
    for k in diag:
        for e, w in ((e, ws[k]) for e, ws in weight.items() if k in ws):
            diag_load[e] += w
    # 示例热边：外圈对角互打达到上界的边中 AllToAll 负载最大者
    hot = max(edges, key=lambda e: (diag_load[e], a2a[e]))
    h_edges = [e for e in edges if M.is_horizontal(*e)]
    v_edges = [e for e in edges if not M.is_horizontal(*e)]

    # router 交换容量：线路侧 + 各出边的无阻塞带宽
    out_bw = defaultdict(float)
    for (a, _), w in worst.items():
        out_bw[a] += w * die_bw
    router = {p: die_bw + out_bw[p] for p in pos}

    ms = list(met.values())
    nf = len(ms)

    def avg(key):
        return sum(m[key] for m in ms) / nf

    # 端到端（单段）；平均含 s=d 的本地流量（0 跳），与 CLOS 方案的 L1→L3 平均口径一致
    e2e = {}
    local = M.path_metrics([pos[0]], t_sw=M.T_SW_SW_O1T)
    for key in ("hops", "lat_max", "lat_mean", "wire_max", "wire_mean", "ft_lat_max", "ft_lat_mean", "turn_lat"):
        e2e[key] = dict(max=max(m[key] for m in ms), mean=(sum(m[key] for m in ms) + N * local[key]) / (N * N))
    wk = max(met, key=lambda k: met[k]["lat_max"])
    w = met[wk]
    e2e_worst = dict(lat=w["lat_max"], iface=w["iface_lat"], end=w["end_lat_max"], ft=w["ft_lat_max"],
                     turn=w["turn_lat"], turns=w["turns"], sw_die=w["sw_die_lat"], sw_sw=w["sw_sw_lat"],
                     ft_share=w["ft_lat_max"] / w["lat_max"], arg=[list(wk[0]), list(wk[1])])

    power = {}
    for ew in M.WIRE_PJ_SET:
        e_map = {k: M.energy_pj(m, ew) for k, m in met.items()}
        # SIO 静态按物理构型：每条有向边按无阻塞带宽 C·B_die 配置
        sio_static = M.sio_static_W(len(edges), C * die_bw)
        sio = sio_static + sum(M.sio_dyn_W(m["hops"], b) for m in ms)
        wire = sum(M.wire_link_W(m["ft_mean"], b, ew) for m in ms)
        ft_wire = wire
        idx = {p: i for i, p in enumerate(pos)}

        def perm_move(pairs):
            """置换下的数据搬移 = 物理构型 SIO 静态 + 活跃对的动态 SIO + 馈通。"""
            sio_sc = sio_static
            wire_sc = 0.0
            for s, d in pairs:
                m = met[(s, d)]
                sio_sc += M.sio_dyn_W(m["hops"], die_bw)
                wire_sc += M.wire_link_W(m["ft_mean"], die_bw, ew)
            return sio_sc, wire_sc

        # 最坏 / 最佳置换：按动态搬移能耗指派（静态对所有置换相同）
        Wm = np.zeros((N, N))
        for (s, d), m in met.items():
            Wm[idx[s], idx[d]] = M.move_dyn_pj(m, ew)
        ri, ci = linear_sum_assignment(Wm, maximize=True)
        worst_pairs = [(pos[i], pos[j]) for i, j in zip(ri, ci) if i != j]
        sio_w, wire_w = perm_move(worst_pairs)
        perm_worst_d2d = sio_w + wire_w
        Wm_ft = np.full((N, N), 1e18)
        for (s, d), m in met.items():
            Wm_ft[idx[s], idx[d]] = M.move_dyn_pj(m, ew)
        rb, cb = linear_sum_assignment(Wm_ft, maximize=False)
        best_pairs = [(pos[i], pos[j]) for i, j in zip(rb, cb) if i != j]
        sio_b, wire_b = perm_move(best_pairs)
        perm_best_d2d = sio_b + wire_b

        scen = {}
        for key, label in M.SCENARIOS:
            r = M.scenario_rates(mesh, key)
            active = [p for p in pos if r[p] > 0]
            sio_sc, wire_sc = sio_static, 0.0
            if key.startswith("a2a_") or key == "perm_100":
                # perm_100：均匀随机置换的期望与 AllToAll 同（每对 E[T]=b）
                for (s, d), m in met.items():
                    rate = (r[s] if key.startswith("a2a_") else 1.0) * b
                    sio_sc += M.sio_dyn_W(m["hops"], rate)
                    wire_sc += M.wire_link_W(m["ft_mean"], rate, ew)
            else:
                t = die_bw / len(active)
                for (s, d), m in met.items():
                    rate = t if (r[s] > 0 and r[d] > 0) else 0.0
                    sio_sc += M.sio_dyn_W(m["hops"], rate)
                    wire_sc += M.wire_link_W(m["ft_mean"], rate, ew)
            inj = sum(r.values()) * die_bw
            d2d = sio_sc + wire_sc
            scen[key] = dict(label=label, sio_W=sio_sc, wire_W=wire_sc, d2d_W=d2d, line_W=0.0,
                             sio_static_W=sio_static, sio_dyn_W=sio_sc - sio_static,
                             W=d2d, active=len(active), inj_tbps=inj)
        scen["perm_worst"] = dict(label="Permutation 满载（最坏置换）",
                                  sio_W=sio_w, wire_W=wire_w, d2d_W=perm_worst_d2d, line_W=0.0,
                                  sio_static_W=sio_static, sio_dyn_W=sio_w - sio_static,
                                  W=perm_worst_d2d, active=N, inj_tbps=M.SYSTEM_TBPS)
        scen["perm_best"] = dict(label="最佳场景（最小搬移置换）",
                                 sio_W=sio_b, wire_W=wire_b, d2d_W=perm_best_d2d, line_W=0.0,
                                 sio_static_W=sio_static, sio_dyn_W=sio_b - sio_static,
                                 W=perm_best_d2d, active=N, inj_tbps=M.SYSTEM_TBPS)
        total = M.SERDES_W + sio + wire
        power[str(ew)] = dict(
            e_wire=ew, sio_W=sio, sio_static_W=sio_static, sio_dyn_W=sio - sio_static,
            sio_cfg_tbps=len(edges) * C * die_bw, n_dir_edges=len(edges),
            wire_W=wire, ft_wire_W=ft_wire, d2d_W=sio + wire, line_W=0.0,
            static_W=M.SERDES_W + sio_static,
            total_W=total, total_worst_W=M.SERDES_W + max(sio + wire, perm_worst_d2d),
            total_best_W=M.SERDES_W + perm_best_d2d,
            worst_scenario="Permutation 满载（最坏置换）" if perm_worst_d2d > sio + wire else "AllToAll 满载",
            max_path_pj=max(e_map.values()), e2e_max_pj=max(e_map.values()), scenarios=scen,
        )

    hop_hist = defaultdict(int)
    for m in ms:
        hop_hist[m["hops"]] += 1
    lb, lb_where = M.bisection_lower_bound(mesh)

    def ek(e):
        return f"{e[0][0]},{e[0][1]}->{e[1][0]},{e[1][1]}"

    return dict(
        n=n, N=N, b_tbps=b, die_bw_tbps=die_bw, ports_per_die=M.N_PORTS // N, die_port_tbps=die_bw,
        n_flows=nf, split=SPLIT, n_paths=2 * nf,
        C=C * N,  # 以 b 为单位（与 CLOS 方案的 “条” 可比）
        C_die=C, C_tbps=C * die_bw, C_ports400=math.ceil(C * die_bw / 0.4 - 1e-9),
        C_h=max(worst[e] for e in h_edges) * N, C_v=max(worst[e] for e in v_edges) * N,
        density_h=max(worst[e] for e in h_edges) * die_bw / M.DIE_H_MM,
        density_v=max(worst[e] for e in v_edges) * die_bw / M.DIE_W_MM,
        mean_edge_tbps=sum(worst.values()) * die_bw / len(edges),
        edge_min_tbps=min(worst.values()) * die_bw,
        a2a_C=max(a2a.values()), a2a_C_tbps=max(a2a.values()) * b, a2a_mean_tbps=sum(a2a.values()) * b / len(edges),
        lb=lb, lb_tbps=lb * (M.SYSTEM_TBPS / N / N), lb_where=lb_where,
        speedup_edge=C, speedup_die=4 * C, router_max_tbps=max(router.values()),
        router_max_ports400=max(router.values()) / 0.4, router_traversals_max=max(m["hops"] for m in ms) + 1,
        hops_mean=avg("hops"), hops_max=max(m["hops"] for m in ms),
        wire_mean=avg("wire_mean"), wire_max=max(m["wire_max"] for m in ms),
        lat_link_max=max(m["lat_max"] for m in ms), lat_link_mean=avg("lat_mean"),
        ft_share_link_max=w["ft_lat_max"] / w["lat_max"],
        ft_share_mean=sum(m["ft_lat_mean"] for m in ms) / sum(m["lat_mean"] for m in ms),
        ft_bw_share=sum(m["hops"] - 1 for m in ms) / sum(m["hops"] for m in ms),
        turns_mean=avg("turns"), detour_flows=0,
        e2e=e2e, e2e_worst=e2e_worst, power=power,
        hop_hist={str(k): v for k, v in sorted(hop_hist.items())},
        worst_load={ek(e): v for e, v in worst.items()},
        a2a_load={ek(e): v for e, v in a2a.items()},
        hot_edge=ek(hot), hot_witness=[[list(s), list(d)] for s, d in witness[hot]],
        ring_diag=[[list(s), list(d)] for s, d in diag],
        ring_diag_max=max(diag_load.values()),
        ring_diag_edges_at_max=sum(1 for v in diag_load.values() if abs(v - C) < 1e-9),
        paths={f"{s[0]},{s[1]}|{d[0]},{d[1]}": [list(x) for x in p] for (s, d), p in paths.items()},
        paths_ccw={f"{s[0]},{s[1]}|{d[0]},{d[1]}": [list(x) for x in p] for (s, d), p in paths_ccw.items()},
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--out", type=Path, default=Path("report_dsl_400t/data"))
    args = ap.parse_args()
    for n in args.sizes:
        r = run(n)
        assert abs(r["ring_diag_max"] - n / 2) < 1e-9
        p = r["power"]["0.1"]
        print(f"{n}x{n}: edge worst {r['C_die']}x die bw = {r['C_tbps']:.1f}T (A2A {r['a2a_C_tbps']:.1f}T), "
              f"router max {r['router_max_tbps']:.1f}T, e2e max {r['e2e']['lat_max']['max']:.0f}ns "
              f"mean {r['e2e']['lat_mean']['mean']:.0f}ns, P0.1 {p['total_W']:.0f}W worst {p['total_worst_W']:.0f}W")
        (args.out / f"dsl_o1t_{n}x{n}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
