#!/usr/bin/env python3
"""O1Turn(DR) 细化变种：单 Reticle 3D 堆叠（NOW die + SW die + OE die）与多平面 NoC 的规模计算。

每个 Reticle = 底层 NOW die（多平面 NoC router + SW↔OE 点对点互联）+ 顶层 SW die（多流水线交换）
+ 顶层 1 颗 OE die（光引擎，带宽等于 SW die 线路侧带宽 B_die，按流水线分 N 个光引擎切片，FAU 向上出纤）。

- 流水线：每条 P = 3.2 Tbps，SW die 流水线数 N = B_die / P。
- NoC 平面：M 个互不连通的平面，每个平面在每颗 NOW die 上一个 5 端口 router（本地 + 东南西北），
  端口宽度 w = P；交换引擎把 N 条流水线的流量均匀喷洒到 M 个平面，单平面本地注入率 λ = N / M。
- 单平面可持续注入率 ρ_sat = η · min(1, 1/γ)：γ 为单位注入下的最热边负载（最坏置换 n/2，AllToAll
  取方案四实测值），η 为 router 实现相对理想容量的饱和效率（buffered / bufferless 典型值）。
- 流水线同构切片 ⇒ M = k·N；λ = 1/k ≤ ρ_sat ⇒ k = ⌈1/ρ_sat⌉。

Usage:
  python3 dsl_o1t_stack.py --sizes 4 8 --data report_dsl_400t/data
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import dsl_mesh_400t as M

PIPE_TBPS = 3.2
OPT_LANE_GBPS = 200.0    # 单纤单波 200G
FAU_FIBRES = 64          # 单个 FAU 的光纤数
ROUTER_PORTS = 5         # 本地 + 东南西北
# router 实现相对理想容量的饱和效率（8×8 mesh 均匀随机流量下的公开文献量级；需 cycle 级仿真校准）
ETA = {"ideal": 1.0, "buf": 0.8, "bl": 0.5}
ETA_RANGE = {"buf": (0.7, 0.9), "bl": (0.5, 0.7)}
# 3D 混合键合（hybrid bonding）估算假设
HB_PITCH_UM = 9.0
HB_GBPS_PER_PIN = 4.0
HB_SIGNAL_SHARE = 0.5
EPS = 1e-9


def ceil_k(rho: float) -> int:
    return max(1, math.ceil(1.0 / rho - EPS))


def evaluate(n: int, o1t: dict) -> dict:
    b_die = M.SYSTEM_TBPS / (n * n)
    n_pipe = round(b_die / PIPE_TBPS)
    assert abs(n_pipe * PIPE_TBPS - b_die) < EPS
    gamma = {"worst": o1t["C_die"], "a2a": o1t["a2a_C_tbps"] / o1t["die_bw_tbps"]}
    assert abs(gamma["worst"] - n / 2) < EPS
    hop_mm = max(M.DIE_W_MM, M.DIE_H_MM)
    rtt_ns = 2 * (M.SIO_NS + hop_mm * M.WIRE_NS_PER_MM + M.GAP_MM * M.GAP_NS_PER_MM) + 2 * M.T_SW_SW_O1T
    buf_port_kb = rtt_ns * 1e-9 * PIPE_TBPS * 1e12 / 8 / 1024
    hb_tbps_mm2 = 1e6 / HB_PITCH_UM ** 2 * HB_SIGNAL_SHARE * HB_GBPS_PER_PIN / 1000
    n_dir_edges = 4 * n * (n - 1)
    cfg = {}
    for tr, g in gamma.items():
        rho_star = min(1.0, 1.0 / g)
        for rt, eta in ETA.items():
            rho = eta * rho_star
            k = ceil_k(rho)
            m = k * n_pipe
            lam = n_pipe / m
            assert lam <= rho + EPS and m % n_pipe == 0
            edge = m * PIPE_TBPS
            sw_vert = (n_pipe + m) * PIPE_TBPS
            c = dict(gamma=g, rho_star=rho_star, eta=eta, rho_sat=rho, k=k, M=m, lam=lam,
                     edge_tbps=edge, edge_x=edge / b_die, edge_vs_o1t=edge / o1t["C_tbps"] - 1,
                     dens_25=edge / M.DIE_H_MM, dens_32=edge / M.DIE_W_MM,
                     router_plane_tbps=ROUTER_PORTS * PIPE_TBPS, router_now_tbps=ROUTER_PORTS * m * PIPE_TBPS,
                     router_now_x=ROUTER_PORTS * m * PIPE_TBPS / b_die,
                     engine_ports=n_pipe + m, sw_vert_tbps=sw_vert,
                     hb_sw_mm2=2 * sw_vert / hb_tbps_mm2,
                     util_edge=g * lam / 1.0)
            c["sio_static_W"] = M.sio_static_W(n_dir_edges, edge)
            c["sio_static_vs_o1t"] = edge / o1t["C_tbps"]
            c["xbar_ratio"] = ((2 * n + 1) * b_die) ** 2 / (m * (ROUTER_PORTS * PIPE_TBPS) ** 2)
            c["margin"] = rho - lam
            if rt == "ideal" and tr == "worst":
                assert abs(edge - o1t["C_tbps"]) < EPS
            if rt == "buf":
                c["buf_plane_kb"] = 4 * buf_port_kb
                c["buf_now_mb"] = 4 * buf_port_kb * m / 1024
            cfg[f"{tr}_{rt}"] = c
    oe_lanes = round(b_die * 1000 / OPT_LANE_GBPS)
    slice_lanes = round(PIPE_TBPS * 1000 / OPT_LANE_GBPS)
    return dict(
        n=n, N_die=n * n, die_bw_tbps=b_die, pipe_tbps=PIPE_TBPS, N_pipe=n_pipe,
        bl_vs_buf_edge=cfg["worst_bl"]["edge_tbps"] / cfg["worst_buf"]["edge_tbps"] - 1,
        pipes_total=n * n * n_pipe, ports400_per_pipe=round(PIPE_TBPS / M.PORT_GBPS * 1000),
        ports400_die=round(b_die / M.PORT_GBPS * 1000),
        oe_dies=1, oe_tbps=b_die, oe_slices=n_pipe, oe_lanes=oe_lanes, oe_fibres=2 * oe_lanes,
        slice_lanes=slice_lanes, slice_fibres=2 * slice_lanes,
        fau_fibres=FAU_FIBRES, n_fau=math.ceil(2 * oe_lanes / FAU_FIBRES),
        fibres_die=2 * oe_lanes, fibres_total=2 * oe_lanes * n * n,
        o1t_edge_tbps=o1t["C_tbps"], o1t_router_tbps=(2 * n + 1) * b_die, n_dir_edges=n_dir_edges,
        o1t_sio_static_W=M.sio_static_W(n_dir_edges, o1t["C_tbps"]),
        rtt_ns=rtt_ns, hop_mm=hop_mm, buf_port_kb=buf_port_kb,
        hb_pitch_um=HB_PITCH_UM, hb_gbps=HB_GBPS_PER_PIN, hb_tbps_mm2=hb_tbps_mm2,
        hb_oe_mm2=2 * b_die / hb_tbps_mm2,
        lat_link_max=o1t["lat_link_max"], hops_max=o1t["hops_max"],
        eta_buf_lo=ETA_RANGE["buf"][0], eta_buf_hi=ETA_RANGE["buf"][1],
        eta_bl_lo=ETA_RANGE["bl"][0], eta_bl_hi=ETA_RANGE["bl"][1],
        cfg=cfg,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--data", default="report_dsl_400t/data")
    a = ap.parse_args()
    d = Path(a.data)
    for n in a.sizes:
        o1t = json.loads((d / f"dsl_o1t_{n}x{n}.json").read_text())
        r = evaluate(n, o1t)
        (d / f"dsl_stk_{n}x{n}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))
        print(f"{n}x{n}: N={r['N_pipe']}", {k: (v["k"], v["M"], round(v["edge_tbps"], 1)) for k, v in r["cfg"].items()},
              f"RTT={r['rtt_ns']:.1f}ns buf/port={r['buf_port_kb']:.1f}KB")


if __name__ == "__main__":
    main()
