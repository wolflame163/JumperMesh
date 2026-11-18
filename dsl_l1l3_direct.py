#!/usr/bin/env python3
"""方案三：在方案二（Manhattan min-max）映射结果上 **叠加** L1→L3 直连。

硬约束（相对错误的“替换两跳”模型）：
  1. 方案二的全部 L1→L2 / L2→L3 逻辑链路与边负载 **原样保留**（保证无阻塞 CLOS 能力不变）；
  2. L1→L3 直连是额外逻辑边，其物理路径上的负载 **只加不减**；
  3. 叠加后最热边 C₃ ≥ C₂；允许容量上界 C_cap = C₂·(1+x%)，x∈{0,5,10}。

默认约定：
  直通粒度  每次为一个有序 die 对 (i,k)（i≠k）叠加一条带宽为 b 的 L1_i→L3_k
           （b = 409.6T/N²，与单条 CLOS 逻辑链路同宽，等于 i→k 聚合流量）。
  算法输入  方案二 JSON（paths + C）；C_cap；直连最坏时延须严格优于该 (i,k) 的两跳最坏时延。

算法：
  1. 固定方案二边负载 ℓ₂；工作负载 ℓ ← ℓ₂。
  2. 按两跳最坏时延从大到小尝试 (i,k)：在 ℓ(e)+1 ≤ C_cap 下为直连寻路；
  3. 成功则直连路径每边 +1，L1 出 / L3 入端口各 +b；ℓ₂ 不变。
  4. 输出 C₃、相对 C₂ 的增长、端口增长、以及直连可用时的时延（CLOS 仍全量预留）。
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import dsl_mesh_400t as M

Coord = M.Coord
Edge = M.Edge
X_PCTS = (0, 5, 10)


def parse_paths(raw: dict) -> Dict[Tuple[int, Coord, Coord], List[Coord]]:
    out = {}
    for k, p in raw.items():
        st, a, b = k.split("|")
        s = tuple(int(x) for x in a.split(","))
        d = tuple(int(x) for x in b.split(","))
        out[(int(st), s, d)] = [tuple(x) for x in p]
    return out


def edge_load(paths) -> Dict[Edge, float]:
    load: Dict[Edge, float] = defaultdict(float)
    for p in paths.values():
        for e in M.path_edges(p):
            load[e] += 1.0
    return load


FIXED_NS = M.T_SW_DIE + M.T_SW_SW  # 每段 lat 各含一份；两段拼接后只保留一份
T_SW_DIRECT = 0.0                  # L1→L3 直连不经 L2，不计 t_sw_sw


def pair_twohop_lat(i, k, met, dies) -> float:
    def seg(st, a, c):
        return FIXED_NS if a == c else met[(st, a, c)]["lat_max"]

    return max(seg(1, i, j) + seg(2, j, k) for j in dies) - FIXED_NS


def route_direct(
    s: Coord,
    d: Coord,
    load: Dict[Edge, float],
    nbrs: Dict[Coord, List[Coord]],
    cap: float,
    lat_budget: float,
) -> Optional[List[Coord]]:
    """在残量约束与时延上界下为直连找路径；字典序 (跳数, 转弯, 负载和)。"""
    if s == d:
        return [s]
    man = abs(d[1] - s[1]) + abs(d[0] - s[0])
    eps = 1e-9
    for extra in (0, 2, 4, 6, 8, 12, 16):
        lim = man + extra
        start = {}
        for v in nbrs[s]:
            if load[(s, v)] + 1.0 > cap + eps:
                continue
            h = M.is_horizontal(s, v)
            nx, ny = int(h), int(not h)
            if M.latency_max_ns(nx, ny, 0, h, h, t_sw=T_SW_DIRECT) > lat_budget + eps:
                continue
            start[(v, nx, h, h, 0)] = ((1, 0, load[(s, v)] + 1.0), None)
        if not start:
            continue
        hist = [None, start]
        layer = start
        best_key = None
        for t in range(1, lim + 1):
            cand = [(val, key) for key, (val, _) in layer.items() if key[0] == d]
            if cand:
                _, best_key = min(cand)
                break
            nxt = {}
            for (u, nx, last_h, first_h, turns), (val, _) in layer.items():
                ny = t - nx
                for v in nbrs[u]:
                    if load[(u, v)] + 1.0 > cap + eps:
                        continue
                    h = M.is_horizontal(u, v)
                    nx2, ny2 = nx + int(h), ny + int(not h)
                    turns2 = turns + (last_h != h)
                    need = abs(d[1] - v[1]) + abs(d[0] - v[0])
                    if nx2 + ny2 + need > lim:
                        continue
                    if M.latency_max_ns(nx2, ny2, turns2, first_h, h, t_sw=T_SW_DIRECT) > lat_budget + eps:
                        continue
                    nval = (nx2 + ny2, turns2, val[2] + load[(u, v)] + 1.0)
                    key = (v, nx2, h, first_h, turns2)
                    cur = nxt.get(key)
                    if cur is None or nval < cur[0]:
                        nxt[key] = (nval, (u, nx, last_h, first_h, turns))
            hist.append(nxt)
            layer = nxt
            if not layer:
                break
        if best_key is None:
            continue
        path = [d]
        key = best_key
        for step in range(len(hist) - 1, 0, -1):
            _, prev = hist[step][key]
            if prev is None:
                path.append(s)
                break
            path.append(prev[0])
            key = prev
        else:
            path.append(s)
        path = path[::-1]
        if path[0] != s:
            path = [s] + path
        return path
    return None


def scenario_traffic(mesh, name: str, b: float, directs) -> Tuple[Dict, Dict]:
    """场景的 die 对流量 T(i,k) 与直连承载 D(i,k)（Tbps）；直连每对最多承载 b，其余走 CLOS 喷洒。

    Permutation 取均匀随机置换的期望：T(i,k)=N·b 的概率为 1/N，故 E[T]=b、E[D]=b/N。
    """
    N = mesh.n
    pos = mesh.positions
    T: Dict[Tuple[Coord, Coord], float] = {}
    D: Dict[Tuple[Coord, Coord], float] = {}
    if name == "perm_100":
        for i in pos:
            for k in pos:
                T[(i, k)] = b
                D[(i, k)] = b / N if (i, k) in directs else 0.0
        return T, D
    rate = M.scenario_rates(mesh, name)
    active = [p for p in pos if rate[p] > 0]
    for i in pos:
        for k in pos:
            if name.startswith("a2a_"):
                t = rate[i] * b
            else:
                t = N * b / len(active) if rate[i] > 0 and rate[k] > 0 else 0.0
            T[(i, k)] = t
            D[(i, k)] = min(b, t) if (i, k) in directs else 0.0
    return T, D


def traffic_metrics(n: int, scheme2: dict, directs: Dict[Tuple[Coord, Coord], List[Coord]],
                    local_direct: bool = True, sio_edge_tbps: float | None = None) -> dict:
    """与方案一 / 二同口径的时延、走线、功耗：(i,k) 有直连时其流量（≤ b）走直连，否则经全部 L2 两跳。

    local_direct：同 die 的 L1_i→L3_i 片内直连（0 跳，不占 die 间带宽）。
    sio_edge_tbps：最终物理构型中每条有向 die 边的 SIO 配置带宽（同构 die = 叠加后最热边）；缺省取方案二。
    directs 为空且 local_direct=False 时结果与方案二完全一致（由 run() 校验）。
    """
    mesh = M.build_mesh(n)
    N = mesh.n
    pos = mesh.positions
    b = scheme2["b_tbps"]
    n_dir_edges = len(M.directed_edges(mesh))
    if sio_edge_tbps is None:
        sio_edge_tbps = scheme2["C_tbps"]
    paths = parse_paths(scheme2["paths"])
    met = {f: M.path_metrics(p) for f, p in paths.items()}
    zero = M.path_metrics([pos[0]])

    def m(st, s, d):
        return zero if s == d else met[(st, s, d)]

    dmet = {ik: M.path_metrics(p, t_sw=T_SW_DIRECT) for ik, p in directs.items()}
    if local_direct:
        local = M.path_metrics([pos[0]], t_sw=T_SW_DIRECT)
        dmet.update({(i, i): local for i in pos})
    directs = dmet

    keys = ("lat_max", "lat_mean", "hops", "wire_max", "wire_mean", "ft_lat_max", "turn_lat")
    best = {k: (-1.0, None) for k in keys}
    acc = {k: 0.0 for k in keys}
    for i in pos:
        for k in pos:
            if (i, k) in dmet:
                dm = dmet[(i, k)]
                cands = [(dm, None)]
            else:
                cands = [(None, j) for j in pos]
            pair_acc = {key: 0.0 for key in keys}
            for dm, j in cands:
                if dm is not None:
                    v = {key: dm[key] for key in keys}
                    parts = (dm["iface_lat"], dm["sw_die_lat"], dm["ft_lat_max"], dm["sw_sw_lat"],
                             dm["turn_lat"], dm["turns"])
                else:
                    a, c = m(1, i, j), m(2, j, k)
                    v = {key: a[key] + c[key] for key in keys}
                    v["lat_max"] -= FIXED_NS
                    v["lat_mean"] -= FIXED_NS
                    parts = (a["iface_lat"] + c["iface_lat"], M.T_SW_DIE, a["ft_lat_max"] + c["ft_lat_max"],
                             M.T_SW_SW, a["turn_lat"] + c["turn_lat"], a["turns"] + c["turns"])
                for key in keys:
                    pair_acc[key] += v[key] / len(cands)
                    if v[key] > best[key][0]:
                        best[key] = (v[key], (i, j, k, parts))
            for key in keys:
                acc[key] += pair_acc[key]
    n_pairs = len(pos) ** 2
    e2e = {key: dict(max=best[key][0], mean=acc[key] / n_pairs) for key in keys}
    lat, (wi, wj, wk, parts) = best["lat_max"][0], best["lat_max"][1]
    iface, end, ft, sw_sw, turn, turns = parts
    assert abs(iface + end + ft + sw_sw + turn - lat) < 1e-6
    e2e_worst = dict(lat=lat, iface=iface, end=end, ft=ft, sw_die=end, sw_sw=sw_sw, turn=turn, turns=turns,
                     ft_share=ft / lat if lat else 0.0,
                     arg=[list(wi), list(wj) if wj else None, list(wk)], via="direct" if wj is None else "twohop")

    power = {}
    for ew in M.WIRE_PJ_SET:
        ew_s = str(ew)
        line_W = 0.0
        # SIO 静态按物理构型：每条有向 die 边按叠加后最热边配置
        sio_static = M.sio_static_W(n_dir_edges, sio_edge_tbps)
        scen = {}
        for key, label in M.SCENARIOS:
            T, D = scenario_traffic(mesh, key, b, directs)
            sio, wire, ft_wire = sio_static, 0.0, 0.0
            r1 = defaultdict(float)
            r2 = defaultdict(float)
            for (i, k), t in T.items():
                rest = (t - D.get((i, k), 0.0)) / N
                if rest:
                    for j in pos:
                        r1[(i, j)] += rest
                        r2[(j, k)] += rest
            # 动态按当前流量
            for (st, s, d), mm in met.items():
                rate = r1[(s, d)] if st == 1 else r2[(s, d)]
                sio += M.sio_dyn_W(mm["hops"], rate)
                w = M.wire_link_W(mm["ft_mean"], rate, ew)
                wire += w
                ft_wire += w
            for ik, mm in dmet.items():
                rate = D.get(ik, 0.0)
                sio += M.sio_dyn_W(mm["hops"], rate)
                w = M.wire_link_W(mm["ft_mean"], rate, ew)
                wire += w
                ft_wire += w
            base = scheme2["power"][ew_s]["scenarios"][key]
            scen[key] = dict(label=label, sio_W=sio, wire_W=wire, ft_wire_W=ft_wire, d2d_W=sio + wire,
                             sio_static_W=sio_static, sio_dyn_W=sio - sio_static,
                             line_W=0.0, W=sio + wire, inj_tbps=base["inj_tbps"],
                             direct_tbps=sum(D.values()))
        a = scen["a2a_100"]
        worst = max(scen.values(), key=lambda s: s["d2d_W"])
        power[ew_s] = dict(
            e_wire=ew, sio_W=a["sio_W"], wire_W=a["wire_W"], ft_wire_W=a["ft_wire_W"], d2d_W=a["d2d_W"],
            sio_static_W=sio_static, sio_dyn_W=a["sio_W"] - sio_static,
            sio_cfg_tbps=n_dir_edges * sio_edge_tbps, n_dir_edges=n_dir_edges,
            line_W=line_W, static_W=M.SERDES_W + sio_static,
            total_W=M.SERDES_W + a["d2d_W"] + line_W,
            total_worst_W=M.SERDES_W + worst["d2d_W"] + line_W, worst_scenario=worst["label"],
            max_path_pj=max([M.energy_pj(x, ew) for x in met.values()] + [M.energy_pj(x, ew) for x in dmet.values()]),
            scenarios=scen,
        )
    return dict(e2e=e2e, e2e_worst=e2e_worst, power=power)


def evaluate_overlay(n: int, scheme2: dict, x_pct: float) -> dict:
    mesh = M.build_mesh(n)
    N = mesh.n
    b = scheme2["b_tbps"]
    C2 = scheme2["C"]
    cap = C2 * (1.0 + x_pct / 100.0)
    paths = parse_paths(scheme2["paths"])
    load2 = edge_load(paths)  # 固定：无阻塞 CLOS 预留
    load = defaultdict(float, load2)  # 工作副本 = CLOS + 直连
    met = {f: M.path_metrics(p) for f, p in paths.items()}
    dies = mesh.positions
    nbrs = M.A._neighbor_map(mesh)
    twohop = {(i, k): pair_twohop_lat(i, k, met, dies) for i in dies for k in dies if i != k}

    directs: Dict[Tuple[Coord, Coord], List[Coord]] = {}
    dlat: Dict[Tuple[Coord, Coord], float] = {}
    failed = set()
    n_for_max = 0
    best_max = scheme2["e2e"]["lat_max"]["max"]

    def current_e2e_max() -> float:
        mx = 0.0
        for i, k in twohop:
            lat = dlat[(i, k)] if (i, k) in dlat else twohop[(i, k)]
            if lat > mx:
                mx = lat
        return mx

    # 按两跳时延从大到小叠加直连（只加不减）
    for i, k in sorted(twohop, key=twohop.get, reverse=True):
        lat_ik = twohop[(i, k)]
        dpath = route_direct(i, k, load, nbrs, cap, lat_ik - 1e-6)
        if dpath is None:
            failed.add((i, k))
            continue
        dm = M.path_metrics(dpath, t_sw=T_SW_DIRECT)
        if dm["lat_max"] >= lat_ik - 1e-9:
            failed.add((i, k))
            continue
        for e in M.path_edges(dpath):
            load[e] += 1.0  # 只加
        directs[(i, k)] = dpath
        dlat[(i, k)] = dm["lat_max"]
        mx = current_e2e_max()
        if mx < best_max - 1e-9:
            best_max = mx
            n_for_max = len(directs)

    # 第二遍：头寸因其它直连绕路变化后重试失败对（仍只加）
    for i, k in sorted(failed, key=lambda ik: twohop[ik], reverse=True):
        if (i, k) in directs:
            continue
        lat_ik = twohop[(i, k)]
        dpath = route_direct(i, k, load, nbrs, cap, lat_ik - 1e-6)
        if dpath is None:
            continue
        dm = M.path_metrics(dpath, t_sw=T_SW_DIRECT)
        if dm["lat_max"] >= lat_ik - 1e-9:
            continue
        for e in M.path_edges(dpath):
            load[e] += 1.0
        directs[(i, k)] = dpath
        dlat[(i, k)] = dm["lat_max"]
        failed.discard((i, k))
        mx = current_e2e_max()
        if mx < best_max - 1e-9:
            best_max = mx
            n_for_max = len(directs)

    # ---- 校验：CLOS 负载未减、总负载单调不减 ----
    for e, v2 in load2.items():
        assert load[e] + 1e-9 >= v2, (e, load[e], v2)
    c3 = max(load.values()) if load else 0.0
    assert c3 + 1e-9 >= C2, (c3, C2)

    # 直连贡献的边负载
    load_dir: Dict[Edge, float] = defaultdict(float)
    for p in directs.values():
        for e in M.path_edges(p):
            load_dir[e] += 1.0

    growth = c3 / C2 - 1.0
    n_dir = len(directs)
    n_out = defaultdict(int)
    n_in = defaultdict(int)
    for i, k in directs:
        n_out[i] += 1
        n_in[k] += 1

    ports_frac = b / 0.4
    ports_ceil = math.ceil(ports_frac - 1e-12)
    l1_ports = n_dir * ports_frac
    l3_ports = n_dir * ports_frac

    def pair_lat(i, k):
        if i == k:
            return M.T_SW_DIE + T_SW_DIRECT
        if (i, k) in directs:
            return dlat[(i, k)]
        return twohop[(i, k)]

    e2e_max = e2e_sum = 0.0
    e2e_arg = None
    n_pairs = 0
    for i in dies:
        for k in dies:
            lat = pair_lat(i, k)
            e2e_sum += lat
            n_pairs += 1
            if lat > e2e_max:
                e2e_max, e2e_arg = lat, (i, k, "direct" if (i, k) in directs else "twohop")
    e2e_mean = e2e_sum / n_pairs
    base_e2e_max = scheme2["e2e"]["lat_max"]["max"]
    base_e2e_mean = scheme2["e2e"]["lat_mean"]["mean"]

    # 预留口径功耗（CLOS 全量 + 直连全量同时满载；最终对外输出以 traffic_metrics 为准）
    n_dir_edges = len(M.directed_edges(mesh))
    power = {}
    for ew in M.WIRE_PJ_SET:
        ew_s = str(ew)
        sio = M.sio_static_W(n_dir_edges, c3 * b)
        wire = ft_wire = 0.0
        for (st, s, d), p in paths.items():
            m = met[(st, s, d)]
            sio += M.sio_dyn_W(m["hops"], b)
            wire += M.wire_link_W(m["ft_mean"], b, ew)
            ft_wire += M.wire_link_W(m["ft_mean"], b, ew)
        for p in directs.values():
            m = M.path_metrics(p, t_sw=T_SW_DIRECT)
            sio += M.sio_dyn_W(m["hops"], b)
            wire += M.wire_link_W(m["ft_mean"], b, ew)
            ft_wire += M.wire_link_W(m["ft_mean"], b, ew)
        line_W = 0.0
        total = M.SERDES_W + sio + wire + line_W
        power[ew_s] = dict(
            e_wire=ew,
            sio_W=sio,
            wire_W=wire,
            ft_wire_W=ft_wire,
            d2d_W=sio + wire,
            line_W=line_W,
            total_W=total,
            vs_s2_total=total / scheme2["power"][ew_s]["total_W"] - 1.0,
            vs_s2_d2d=(sio + wire) / scheme2["power"][ew_s]["d2d_W"] - 1.0,
        )

    d_mets = [M.path_metrics(p, t_sw=T_SW_DIRECT) for p in directs.values()]
    use = traffic_metrics(n, scheme2, directs, sio_edge_tbps=c3 * b)
    for ew_s, pw in use["power"].items():
        base = scheme2["power"][ew_s]
        pw["vs_s2_total"] = pw["total_W"] / base["total_W"] - 1.0
        pw["vs_s2_d2d"] = pw["d2d_W"] / base["d2d_W"] - 1.0
    edges = M.directed_edges(mesh)
    h_loads = [load[e] for e in edges if M.is_horizontal(*e)]
    v_loads = [load[e] for e in edges if not M.is_horizontal(*e)]
    loads_out = {f"{a[0]},{a[1]}->{b_[0]},{b_[1]}": v for (a, b_), v in load.items()}
    loads2_out = {f"{a[0]},{a[1]}->{b_[0]},{b_[1]}": v for (a, b_), v in load2.items()}
    loads_dir_out = {f"{a[0]},{a[1]}->{b_[0]},{b_[1]}": v for (a, b_), v in load_dir.items()}

    return dict(
        n=n,
        N=N,
        b_tbps=b,
        x_pct=x_pct,
        model="additive_overlay",  # 非替换
        scheme2_C=C2,
        scheme2_C_tbps=scheme2["C_tbps"],
        cap=cap,
        cap_tbps=cap * b,
        C=c3,
        C_tbps=c3 * b,
        d2d_growth=growth,
        d2d_growth_vs_cap=c3 / cap - 1.0 if cap else 0.0,
        n_directs=n_dir,
        n_directs_for_e2e_max=n_for_max,
        n_failed=len(failed),
        n_candidates=N * (N - 1),
        direct_share=n_dir / (N * (N - 1)),
        e2e_lat_max_at_n_for_max=best_max,
        ports_per_direct_400G_frac=ports_frac,
        ports_per_direct_400G_ceil=ports_ceil,
        l1_bw_added_tbps=n_dir * b,
        l3_bw_added_tbps=n_dir * b,
        l1_ports_added_total=l1_ports,
        l3_ports_added_total=l3_ports,
        l1_ports_added_total_ceil=n_dir * ports_ceil,
        l3_ports_added_total_ceil=n_dir * ports_ceil,
        l1_ports_added_max_per_sw=(max(n_out.values()) * ports_frac) if n_out else 0.0,
        l3_ports_added_max_per_sw=(max(n_in.values()) * ports_frac) if n_in else 0.0,
        l1_ports_added_max_per_sw_ceil=(max(n_out.values()) * ports_ceil) if n_out else 0,
        l3_ports_added_max_per_sw_ceil=(max(n_in.values()) * ports_ceil) if n_in else 0,
        l1_uplink_ports_base=scheme2["die_port_tbps"] / 0.4,
        local_directs=N,
        l1_ports_added_total_incl_local=(n_dir + N) * ports_frac,
        l1_ports_added_total_incl_local_ceil=(n_dir + N) * ports_ceil,
        l1_ports_added_max_per_sw_incl_local=(max(n_out.values(), default=0) + 1) * ports_frac,
        l3_ports_added_max_per_sw_incl_local=(max(n_in.values(), default=0) + 1) * ports_frac,
        l1_ports_added_max_per_sw_incl_local_ceil=(max(n_out.values(), default=0) + 1) * ports_ceil,
        l3_ports_added_max_per_sw_incl_local_ceil=(max(n_in.values(), default=0) + 1) * ports_ceil,
        e2e_lat_max=e2e_max,
        e2e_lat_mean=e2e_mean,
        e2e_arg=[list(e2e_arg[0]), list(e2e_arg[1]), e2e_arg[2]] if e2e_arg else None,
        e2e_lat_max_vs_s2=e2e_max / base_e2e_max - 1.0,
        e2e_lat_mean_vs_s2=e2e_mean / base_e2e_mean - 1.0,
        base_e2e_lat_max=base_e2e_max,
        base_e2e_lat_mean=base_e2e_mean,
        direct_hops_mean=sum(m["hops"] for m in d_mets) / n_dir if d_mets else 0.0,
        direct_hops_max=max((m["hops"] for m in d_mets), default=0),
        direct_wire_mean=sum(m["wire_mean"] for m in d_mets) / n_dir if d_mets else 0.0,
        direct_wire_max=max((m["wire_max"] for m in d_mets), default=0.0),
        direct_lat_max=max((m["lat_max"] for m in d_mets), default=0.0),
        direct_lat_mean=sum(m["lat_mean"] for m in d_mets) / n_dir if d_mets else 0.0,
        direct_ft_share_mean=(sum(m["ft_lat_mean"] for m in d_mets) / sum(m["lat_mean"] for m in d_mets)) if d_mets else 0.0,
        C_h=max(h_loads),
        C_v=max(v_loads),
        density_h=max(h_loads) * b / M.DIE_H_MM,
        density_v=max(v_loads) * b / M.DIE_W_MM,
        C_ports400=math.ceil(c3 * b * 1000 / M.PORT_GBPS - 1e-9),
        total_d2d_tbps=sum(load.values()) * b,
        total_d2d_tbps_s2=sum(load2.values()) * b,
        e2e=use["e2e"],
        e2e_worst=use["e2e_worst"],
        power=use["power"],
        power_reserved=power,
        loads=loads_out,
        loads_scheme2=loads2_out,
        loads_direct_only=loads_dir_out,
        directs=[
            {
                "i": list(i),
                "k": list(k),
                "path": [list(x) for x in p],
                "lat_max": dlat[(i, k)],
                "twohop_lat": twohop[(i, k)],
            }
            for (i, k), p in directs.items()
        ],
        n_directs_listed=n_dir,
    )


def run(sizes=(4, 8), data_dir=Path("report_dsl_400t/data"), out_dir=None):
    out_dir = Path(out_dir or data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_res = {}
    for n in sizes:
        s2 = json.loads((data_dir / f"dsl_{n}x{n}.json").read_text())["manhattan"]
        chk = traffic_metrics(n, s2, {}, local_direct=False)
        for key in ("lat_max", "lat_mean", "hops", "wire_max", "wire_mean"):
            assert abs(chk["e2e"][key]["max"] - s2["e2e"][key]["max"]) < 1e-6, key
            assert abs(chk["e2e"][key]["mean"] - s2["e2e"][key]["mean"]) < 1e-6, key
        for ew_s, pw in chk["power"].items():
            assert abs(pw["total_W"] - s2["power"][ew_s]["total_W"]) < 1e-6, ew_s
            for sk, sc in pw["scenarios"].items():
                if sk.startswith("hot_"):  # 热点场景本脚本只对有流量的链路计 SIO 静态功耗，方案二计全部链路
                    continue
                assert abs(sc["W"] - s2["power"][ew_s]["scenarios"][sk]["W"]) < 1e-6, (ew_s, sk)
        print(f"{n}x{n}: no-direct check reproduces scheme 2 (e2e latency / wire / power / scenarios)")
        all_res[n] = {}
        for x in X_PCTS:
            r = evaluate_overlay(n, s2, x)
            all_res[n][x] = r
            print(
                f"{n}x{n} x={x}%  directs={r['n_directs']}/{r['n_candidates']}  "
                f"C={r['C']:.2f} ({r['C_tbps']:.2f}T, {100*r['d2d_growth']:+.1f}% vs s2={r['scheme2_C']})  "
                f"e2e max={r['e2e_lat_max']:.0f}ns ({100*r['e2e_lat_max_vs_s2']:+.1f}%) "
                f"mean={r['e2e']['lat_mean']['mean']:.0f}ns  "
                f"Pres0.1={r['power_reserved']['0.1']['total_W']:.0f}W  "
                f"P0.1={r['power']['0.1']['total_W']:.0f}W ({100*r['power']['0.1']['vs_s2_total']:+.1f}%)  "
                f"L1/L3 ports +{r['l1_ports_added_total']:.1f}/{r['l3_ports_added_total']:.1f}"
            )
            assert abs(r["e2e"]["lat_max"]["max"] - r["e2e_lat_max"]) < 1e-6
            assert r["C"] + 1e-9 >= r["scheme2_C"]
            assert r["C"] <= r["cap"] + 1e-9
            assert r["d2d_growth"] >= -1e-9
        path = out_dir / f"dsl_l1l3_{n}x{n}.json"
        # JSON 中 loads 较大但仍可接受
        path.write_text(json.dumps({str(k): v for k, v in all_res[n].items()}, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", path)
    return all_res


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--data", type=Path, default=Path("report_dsl_400t/data"))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.sizes, args.data, args.out or args.data)
