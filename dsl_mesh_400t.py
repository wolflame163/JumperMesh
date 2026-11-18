#!/usr/bin/env python3
"""
409.6T（1024 × 400GE）DSL 交换系统在 n×n 2D Mesh 上的三种路由方案评估。

逻辑拓扑：三级共址 CLOS[N, N, N]（N = n²），每颗 die 同时承载 L1 / L2 / L3 交换与过路 Feedthrough。
外部端口均匀分到每颗 die（1024 / N 个 400GE），L1 对 L2、L2 对 L3 均匀喷洒，
因此每个有序 die 对 (i, j) 有两条逻辑链路（L1_i→L2_j、L2_i→L3_j），每条带宽 b = 409.6T / N²。

三种路由（均不可拆分）：
  xy_o1turn_cw   DSL XY 路由：顺时针 O1Turn（在 XY / YX 中选唯一一次转弯为顺时针的那条）
  manhattan      DSL 最短路径路由：任意 Manhattan 最短路，min-max 边负载优化
  longest_bound  DSL-最长路径最短：最长逻辑链路（对角 die 对）走单转弯 Manhattan 路径，其最坏时延为上界 L*；
                 其余逻辑链路允许绕路，但最坏时延不超过 L*；在此约束下 min-max 边负载

物理模型（die 32 mm(x) × 25 mm(y)，400G 端口沿每条边均匀分布）：
  馈通走线：直通 = die 边长（x 向 32 mm、y 向 25 mm）；转弯 = 入口边到相邻出口边的 Manhattan（均值 (W+H)/2，最坏 W+H）；
            不含源段/宿段；功耗不含缝隙
  每跳 D2D：SIO 0.35 pJ/bit（静态 70% / 动态 30%）、11.5 ns；die 间缝隙 1 mm（计入时延、不计功耗）
  功耗口径：全部数值 = 静态 + 当前流量下的动态；SIO 静态按最终物理构型的 die 边配置带宽计
            （同构 die：每条有向 die 边 = 最热边 C），动态按实际流量 Σh·λ；
            馈通走线纯动态；SerDes 3795 W 计入静态。满载即每条逻辑链路流量 = b 的特例
  片上馈通能耗：0.1 / 0.06 pJ/bit/mm，时延 0.5 ns/mm；不计线路侧走线功耗
  横纵转向：NOW die 内每次横纵方向变化 2 ns
  固定时延（端到端各计一次）：t_sw_die = 120 ns（L1~L3 之外的处理逻辑）；
            t_sw_sw = 70 ns（DSL 方案的 L2 switch），L1→L3 直连与 O1Turn(DR) 为 0

Usage:
  python3 dsl_mesh_400t.py --out report_dsl_400t/data
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import algorithm1_pairwise_exchange as A

Coord = Tuple[int, int]
Edge = Tuple[Coord, Coord]

SYSTEM_TBPS = 409.6
N_PORTS = 1024
PORT_GBPS = 400.0
DIE_W_MM = 32.0
DIE_H_MM = 25.0
GAP_MM = 1.0
SIO_PJ = 0.35
SIO_NS = 11.5
WIRE_NS_PER_MM = 0.5
GAP_NS_PER_MM = 0.5  # 缝隙走线时延与馈通同为 0.5 ns/mm
FT_FIXED_NS = 0.0     # 馈通固定时延并入 t_sw_*；几何走线按 0.5 ns/mm
TURN_NS = 2.0         # NOW die 内每次横纵方向变化
T_SW_DIE = 120.0      # L1~L3 之外的处理逻辑时延，端到端计一次
T_SW_SW = 70.0        # DSL 方案 L2 switch 时延，端到端计一次
T_SW_SW_O1T = 0.0     # O1Turn(DR) 不计 t_sw_sw
SIO_STATIC = 0.7
SIO_DYN = 0.3
WIRE_PJ_SET = (0.1, 0.06)
SERDES_W = 3795.0

# 线路侧 400GE 端口沿四边等量均匀分布：端口到 die 中心交换核的平均 Manhattan 距离（左右边 / 上下边各占一半）
LINE_WIRE_MEAN_MM = ((DIE_W_MM / 2 + DIE_H_MM / 4) + (DIE_H_MM / 2 + DIE_W_MM / 4)) / 2.0

SCHEMES = ("xy_o1turn_cw", "manhattan", "longest_bound")
SCHEME_NAME = {
    "xy_o1turn_cw": "DSL XY 路由",
    "manhattan": "DSL 最短路径路由",
    "longest_bound": "DSL-最长路径最短",
}


def sign(v: int) -> int:
    return (v > 0) - (v < 0)


def build_mesh(n: int) -> A.Mesh:
    return A.build_center_symmetric_mesh((n,) * n)


def directed_edges(mesh: A.Mesh) -> List[Edge]:
    out = []
    for a, b in mesh.adj_edges:
        out.append((a, b))
        out.append((b, a))
    return out


def flows_of(mesh: A.Mesh) -> List[Tuple[int, Coord, Coord]]:
    """(stage, src, dst)：stage 1 = L1→L2，stage 2 = L2→L3；同 die 链路不占 die 间信道，单独计。"""
    pos = mesh.positions
    return [(st, s, d) for st in (1, 2) for s in pos for d in pos if s != d]


def is_horizontal(a: Coord, b: Coord) -> bool:
    return a[0] == b[0]


# ---------------------------------------------------------------- routing


def route_o1turn_cw(s: Coord, d: Coord, clockwise: bool = True) -> List[Coord]:
    """顺时针 O1Turn：x 向右、y 向上为正，XY 的转弯方向为 sx·sy 的符号取反；选使转弯为顺时针的维序。
    clockwise=False 取另一维序（逆时针转弯）；同行 / 同列两者相同。"""
    (r0, c0), (r1, c1) = s, d
    sx, sy = sign(c1 - c0), sign(r0 - r1)
    xy_first = sx == 0 or sy == 0 or (sx * sy < 0) == clockwise
    path = [s]
    r, c = r0, c0
    legs = ("x", "y") if xy_first else ("y", "x")
    for leg in legs:
        if leg == "x":
            while c != c1:
                c += sx
                path.append((r, c))
        else:
            while r != r1:
                r -= sy
                path.append((r, c))
    return path


def best_path(
    s: Coord,
    d: Coord,
    load: Dict[Edge, int],
    nbrs: Dict[Coord, List[Coord]],
    lim_x: int,
    lim_y: int,
) -> List[Coord]:
    """在 x 跳数 ≤ lim_x、y 跳数 ≤ lim_y 的路径中，按 (瓶颈 max(ℓ+1), 跳数, Σ(ℓ+1)) 字典序取最优。

    取最小跳数的最优瓶颈解保证路径无环（去环后跳数更少、瓶颈不增）。
    """
    dc, dr = abs(d[1] - s[1]), abs(d[0] - s[0])
    layer = {(s, 0): ((0, 0), None)}
    hist = [layer]
    best = None
    for t in range(1, lim_x + lim_y + 1):
        nxt: Dict[Tuple[Coord, int], Tuple[Tuple[int, int], Tuple[Coord, int]]] = {}
        for (u, nx), ((bm, bs), _) in layer.items():
            ny = t - 1 - nx
            for v in nbrs[u]:
                h = is_horizontal(u, v)
                nx2, ny2 = nx + h, ny + (not h)
                rx = lim_x - nx2 - abs(d[1] - v[1])
                ry = lim_y - ny2 - abs(d[0] - v[0])
                if rx < 0 or ry < 0:
                    continue
                w = load[(u, v)] + 1
                val = (max(bm, w), bs + w)
                key = (v, nx2)
                cur = nxt.get(key)
                if cur is None or val < cur[0]:
                    nxt[key] = (val, (u, nx))
        hist.append(nxt)
        for (v, nx2), (val, _) in nxt.items():
            if v == d:
                cand = (val[0], t, val[1], nx2)
                if best is None or cand < best:
                    best = cand
        layer = nxt
        if best is not None and t >= dc + dr and all(val[0] >= best[0] for val, _ in nxt.values()):
            break
    assert best is not None
    _, t, _, nx = best
    path = [d]
    key = (d, nx)
    for k in range(t, 0, -1):
        _, prev = hist[k][key]
        path.append(prev[0])
        key = prev
    return path[::-1]


def path_edges(p: Sequence[Coord]) -> List[Edge]:
    return list(zip(p[:-1], p[1:]))


HOP_NS = SIO_NS  # 缝隙时延计入走线（0.5 ns/mm）
TURN_EXTRA_MM = (DIE_W_MM + DIE_H_MM) / 2.0


def _end_extra(h: bool) -> float:
    """最坏口径下源 / 宿段相对 “半个跳距” 的额外长度：沿出口边偏移的一半边长。"""
    return (DIE_H_MM if h else DIE_W_MM) / 2.0


def latency_max_ns(nx: int, ny: int, turns: int, first_h: bool, last_h: bool, t_sw: float = T_SW_SW) -> float:
    """路径最坏时延，与 path_metrics 的 lat_max 等价的闭式表达。

    时延 = h·SIO + (馈通走线+缝隙)·0.5 ns/mm + 转向·TURN_NS + t_sw_die + t_sw；不计源/宿几何走线时延。
    """
    hops = nx + ny
    if hops == 0:
        return T_SW_DIE + t_sw
    end_max = _end(first_h, "max") + _end(last_h, "max")
    wire_no_gap = DIE_W_MM * nx + DIE_H_MM * ny + TURN_EXTRA_MM * turns + _end_extra(first_h) + _end_extra(last_h)
    ft_max = wire_no_gap - end_max
    gap = hops * GAP_MM
    return hops * SIO_NS + (ft_max + gap) * WIRE_NS_PER_MM + turns * TURN_NS + T_SW_DIE + t_sw


def budget_path(
    s: Coord,
    d: Coord,
    load: Dict[Edge, int],
    nbrs: Dict[Coord, List[Coord]],
    budget: float,
    cap: int | None = None,
):
    """时延上界内的不可拆分路由。

    cap 为 None：按 (瓶颈 max(ℓ+1), 跳数, 转弯, Σ(ℓ+1)) 取最优；
    cap 给定：只用 ℓ+1 ≤ cap 的边，按 (跳数, 转弯, Σ(ℓ+1)) 取最优。无解返回 None。
    状态 (die, x 跳数, 末段方向, 首段方向, 转弯数)。
    """
    eps = 1e-9

    def lb_rest(v, nx, ny, turns, first_h, last_h):
        """从当前状态走到 d 的最坏时延下界（剩余部分按 Manhattan、最少转弯、较短的末段口径估计）。"""
        rx, ry = abs(d[1] - v[1]), abs(d[0] - v[0])
        if rx == 0 and ry == 0:
            return latency_max_ns(nx, ny, turns, first_h, last_h)
        need = 1 if (rx and ry) or (rx and not last_h) or (ry and last_h) else 0
        hops = nx + rx + ny + ry
        end_max = _end(first_h, "max") + min(_end(True, "max"), _end(False, "max"))
        wire_no_gap = (DIE_W_MM * (nx + rx) + DIE_H_MM * (ny + ry) + TURN_EXTRA_MM * (turns + need)
                       + _end_extra(first_h) + min(_end_extra(True), _end_extra(False)))
        ft_max = max(0.0, wire_no_gap - end_max)
        gap = hops * GAP_MM
        return hops * SIO_NS + (ft_max + gap) * WIRE_NS_PER_MM + (turns + need) * TURN_NS + T_SW_DIE + T_SW_SW

    start = {}
    for v in nbrs[s]:
        h = is_horizontal(s, v)
        w = load[(s, v)] + 1
        if cap is not None and w > cap:
            continue
        if lb_rest(v, int(h), int(not h), 0, h, h) > budget + eps:
            continue
        val = (w, 0, w) if cap is None else (0, w)
        start[(v, int(h), h, h, 0)] = (val, None)
    hist = [None, start]
    layer = start
    best = None
    t = 1
    while layer:
        for key, (val, _) in layer.items():
            v, nx, last_h, first_h, turns = key
            if v == d:
                cand = (val[0], t, turns, val[-1], key) if cap is None else (t, turns, val[-1], key)
                if best is None or cand < best:
                    best = cand
        if best is not None:
            if cap is not None:
                break
            if all(val[0] >= best[0] for val, _ in layer.values()):
                break
        nxt = {}
        for key, (val, _) in layer.items():
            u, nx, last_h, first_h, turns = key
            if u == d:
                continue
            ny = t - nx
            for v in nbrs[u]:
                h = is_horizontal(u, v)
                w = load[(u, v)] + 1
                if cap is not None and w > cap:
                    continue
                nx2, ny2, turns2 = nx + h, ny + (not h), turns + (h != last_h)
                if lb_rest(v, nx2, ny2, turns2, first_h, h) > budget + eps:
                    continue
                if cap is None:
                    val2 = (max(val[0], w), turns2, val[2] + w)
                else:
                    val2 = (turns2, val[1] + w)
                key2 = (v, nx2, h, first_h, turns2)
                cur = nxt.get(key2)
                if cur is None or val2 < cur[0]:
                    nxt[key2] = (val2, key)
        t += 1
        hist.append(nxt)
        layer = nxt
    if best is None:
        return None
    key = best[-1]
    tt = best[1] if cap is None else best[0]
    path = [key[0]]
    for k in range(tt, 0, -1):
        prev = hist[k][key][1]
        if prev is None:
            break
        path.append(prev[0])
        key = prev
    path.append(s)
    return path[::-1]


def longest_link_latency(n: int) -> float:
    """最长逻辑链路（对角 die 对）走单转弯 Manhattan 路径的最坏时延，即方案三的时延上界。"""
    return min(latency_max_ns(n - 1, n - 1, 1, True, False), latency_max_ns(n - 1, n - 1, 1, False, True))


def path_turns(p: Sequence[Coord]) -> int:
    hs = [is_horizontal(a, b) for a, b in zip(p[:-1], p[1:])]
    return sum(1 for a, b in zip(hs[:-1], hs[1:]) if a != b)


def capped_path(
    s: Coord,
    d: Coord,
    load: Dict[Edge, int],
    nbrs: Dict[Coord, List[Coord]],
    lim_x: int,
    lim_y: int,
    cap: int,
):
    """只用 ℓ+1 ≤ cap 的边，按 (跳数, 转弯数, Σ(ℓ+1)) 字典序取最优；无解返回 None。"""
    layer = {(s, 0, None): ((0, 0), None)}
    hist = [layer]
    for t in range(1, lim_x + lim_y + 1):
        nxt = {}
        for (u, nx, hd), ((tn, sm), _) in layer.items():
            ny = t - 1 - nx
            for v in nbrs[u]:
                w = load[(u, v)] + 1
                if w > cap:
                    continue
                h = is_horizontal(u, v)
                nx2, ny2 = nx + h, ny + (not h)
                if lim_x - nx2 - abs(d[1] - v[1]) < 0 or lim_y - ny2 - abs(d[0] - v[0]) < 0:
                    continue
                val = (tn + (hd is not None and hd != h), sm + w)
                key = (v, nx2, h)
                cur = nxt.get(key)
                if cur is None or val < cur[0]:
                    nxt[key] = (val, (u, nx, hd))
        hist.append(nxt)
        done = [(val, key) for key, (val, _) in nxt.items() if key[0] == d]
        if done:
            _, key = min(done)
            path = [d]
            for k in range(t, 0, -1):
                _, prev = hist[k][key]
                path.append(prev[0])
                key = prev
            return path[::-1]
        layer = nxt
        if not layer:
            return None
    return None


def route_all(
    mesh: A.Mesh,
    scheme: str,
    seed: int = 1,
    max_iter: int = 60,
) -> Dict[Tuple[int, Coord, Coord], List[Coord]]:
    n = mesh.row_widths[0]
    flows = flows_of(mesh)
    if scheme == "xy_o1turn_cw":
        return {f: route_o1turn_cw(f[1], f[2]) for f in flows}

    nbrs = A._neighbor_map(mesh)
    rng = random.Random(seed)

    budget = longest_link_latency(n)

    def lims(f):
        _, s, d = f
        return abs(d[1] - s[1]), abs(d[0] - s[0])

    if scheme == "manhattan":
        def router(f, load):
            return best_path(f[1], f[2], load, nbrs, *lims(f))

        def capped(f, load, cap):
            return capped_path(f[1], f[2], load, nbrs, *lims(f), cap)
    else:
        def router(f, load):
            return budget_path(f[1], f[2], load, nbrs, budget)

        def capped(f, load, cap):
            return budget_path(f[1], f[2], load, nbrs, budget, cap=cap)

    load: Dict[Edge, int] = defaultdict(int)
    order = sorted(flows, key=lambda f: (-(abs(f[1][0] - f[2][0]) + abs(f[1][1] - f[2][1])), rng.random()))
    paths = {}
    for f in order:
        p = router(f, load)
        paths[f] = p
        for e in path_edges(p):
            load[e] += 1

    def snapshot():
        return max(load.values()), sum(load.values())

    best_score = snapshot()
    best_paths = dict(paths)
    stall = 0
    for it in range(max_iter):
        cmax = max(load.values())
        hot = {e for e, v in load.items() if v >= cmax - (1 if it % 3 == 2 else 0)}
        victims = [f for f, p in paths.items() if any(e in hot for e in path_edges(p))]
        rng.shuffle(victims)
        for f in victims:
            for e in path_edges(paths[f]):
                load[e] -= 1
            p = router(f, load)
            paths[f] = p
            for e in path_edges(p):
                load[e] += 1
        sc = snapshot()
        if sc < best_score:
            best_score, best_paths, stall = sc, dict(paths), 0
        else:
            stall += 1
            if stall >= 8:
                break

    # 收尾：在不抬高 C 的前提下，逐条把路径换成跳数最少、转弯最少的可行路径（先减绕路，再减转弯）
    paths = dict(best_paths)
    load = defaultdict(int)
    for p in paths.values():
        for e in path_edges(p):
            load[e] += 1
    cap = max(load.values())
    for _ in range(4):
        changed = 0
        fl = sorted(paths, key=lambda f: (-(len(paths[f]) - 1 - abs(f[1][0] - f[2][0]) - abs(f[1][1] - f[2][1])),
                                          -path_turns(paths[f]), rng.random()))
        for f in fl:
            old = paths[f]
            for e in path_edges(old):
                load[e] -= 1
            p = capped(f, load, cap)
            if p is None or (len(p), path_turns(p)) >= (len(old), path_turns(old)):
                p = old
            else:
                changed += 1
            paths[f] = p
            for e in path_edges(p):
                load[e] += 1
        if not changed:
            break
    assert max(load.values()) <= cap
    return paths


def bisection_lower_bound(mesh: A.Mesh) -> Tuple[int, str]:
    """直线割下界：A→B 有向需求 2|A||B| 条逻辑链路，由跨割 W 条同向边分摊。"""
    n = mesh.row_widths[0]
    best, where = 0, ""
    for k in range(1, n):
        a = k * n
        b = (n - k) * n
        lb = math.ceil(2 * a * b / n)
        if lb > best:
            best, where = lb, f"列 {k-1}|{k}（{a}/{b} die，{n} 条边）"
    return best, where


# ---------------------------------------------------------------- metrics


def _seg(dirh: bool) -> float:
    return DIE_W_MM if dirh else DIE_H_MM


def _end(dirh: bool, mode: str) -> float:
    perp = _seg(dirh) / 2.0
    edge = DIE_H_MM if dirh else DIE_W_MM
    return perp + (edge / 4.0 if mode == "mean" else edge / 2.0)


def path_metrics(p: Sequence[Coord], t_sw: float = T_SW_SW) -> dict:
    """单条路径的馈通走线 / 时延。

    lat_* 是把该路径当作完整端到端行程的时延：传输（SIO + 馈通 + 缝隙 + 转向）+ t_sw_die + t_sw。
    CLOS 逻辑链路取 t_sw = T_SW_SW；两段拼成端到端时减去一份 T_SW_DIE + T_SW_SW。
    L1→L3 直连与 O1Turn(DR) 取 t_sw = 0。
    馈通走线不含源段/宿段；功耗口径的 wire_* 仅计馈通（不含缝隙）；缝隙只进入时延。
    """
    hops = len(p) - 1
    if hops == 0:
        sw_die = T_SW_DIE
        sw_sw = t_sw
        z = dict(hops=0, n_ft=0, wire_mean=0.0, wire_max=0.0, ft_mean=0.0, ft_max=0.0,
                 gap_mm=0.0, end_mean_mm=0.0, end_max_mm=0.0,
                 lat_mean=sw_die + sw_sw, lat_max=sw_die + sw_sw, ft_lat_mean=0.0, ft_lat_max=0.0,
                 turns=0, turn_lat=0.0, iface_lat=0.0, end_lat_mean=sw_die, end_lat_max=sw_die,
                 sw_die_lat=sw_die, sw_sw_lat=sw_sw)
        return z
    hs = [is_horizontal(a, b) for a, b in zip(p[:-1], p[1:])]
    end_mean = _end(hs[0], "mean") + _end(hs[-1], "mean")
    end_max = _end(hs[0], "max") + _end(hs[-1], "max")
    ft_mean = ft_max = 0.0
    turns = 0
    for a, b in zip(hs[:-1], hs[1:]):
        if a == b:
            ft_mean += _seg(a)
            ft_max += _seg(a)
        else:
            turns += 1
            ft_mean += (DIE_W_MM + DIE_H_MM) / 2.0
            ft_max += DIE_W_MM + DIE_H_MM
    n_ft = hops - 1
    gap = hops * GAP_MM
    iface = hops * SIO_NS
    ft_lat_mean = (ft_mean + gap) * WIRE_NS_PER_MM
    ft_lat_max = (ft_max + gap) * WIRE_NS_PER_MM
    turn_lat = turns * TURN_NS
    sw_die = T_SW_DIE
    sw_sw = t_sw
    return dict(
        hops=hops,
        n_ft=n_ft,
        turns=turns,
        # 馈通距离（不含源/宿、不含缝隙）——功耗与“馈通走线距离”口径
        wire_mean=ft_mean,
        wire_max=ft_max,
        ft_mean=ft_mean,
        ft_max=ft_max,
        gap_mm=gap,
        end_mean_mm=end_mean,  # 仅备查，不参与功耗/馈通口径
        end_max_mm=end_max,
        lat_mean=iface + ft_lat_mean + turn_lat + sw_die + sw_sw,
        lat_max=iface + ft_lat_max + turn_lat + sw_die + sw_sw,
        ft_lat_mean=ft_lat_mean,
        ft_lat_max=ft_lat_max,
        turn_lat=turn_lat,
        iface_lat=iface,
        end_lat_mean=sw_die,
        end_lat_max=sw_die,
        sw_die_lat=sw_die,
        sw_sw_lat=sw_sw,
    )


def energy_pj(m: dict, e_wire: float) -> float:
    """每 bit 能耗（pJ/bit）：SIO 按跳 + 馈通走线（不含源/宿、不含缝隙）按 mm。"""
    return m["hops"] * SIO_PJ + m["ft_mean"] * e_wire


def sio_static_W(n_dir_edges: int, edge_tbps: float) -> float:
    """SIO 静态功耗（W）：按最终物理构型中配置的 die 边 SIO 带宽计。

    同构 die：每条有向 die 边的 SIO 带宽 = 全阵列最热有向边带宽 C；阵列外沿无相邻 die 的一侧不计。
    1 pJ/bit × 1 Tbps = 1 W。
    """
    return n_dir_edges * edge_tbps * SIO_PJ * SIO_STATIC


def sio_dyn_W(hops: float, rate_tbps: float) -> float:
    """单条逻辑链路的 SIO 动态功耗（W），按实际流量。"""
    return hops * rate_tbps * SIO_PJ * SIO_DYN


def wire_link_W(ft_mean_mm: float, rate_tbps: float, e_wire: float) -> float:
    """单条逻辑链路的馈通走线功耗（W；纯动态）。"""
    return rate_tbps * ft_mean_mm * e_wire


def move_dyn_pj(m: dict, e_wire: float) -> float:
    """每 bit 动态数据搬移能耗（pJ/bit）：仅 SIO 动态份额 + 馈通。用于置换指派目标。"""
    return SIO_DYN * m["hops"] * SIO_PJ + m["ft_mean"] * e_wire


def scenario_rates(mesh: A.Mesh, name: str) -> Dict[Coord, float]:
    n = mesh.row_widths[0]
    pos = mesh.positions
    if name.startswith("a2a_"):
        rho = int(name.split("_")[1]) / 100.0
        return {p: rho for p in pos}
    if name == "perm_100":
        return {p: 1.0 for p in pos}
    q = n // 4
    if name == "hot_center":
        lo, hi = n // 2 - max(q, 1), n // 2 + max(q, 1)
        return {p: 1.0 if lo <= p[0] < hi and lo <= p[1] < hi else 0.0 for p in pos}
    if name == "hot_corner":
        k = max(q, 1)

        def corner(r, c):
            return (r < k or r >= n - k) and (c < k or c >= n - k)

        return {p: 1.0 if corner(*p) else 0.0 for p in pos}
    raise ValueError(name)


SCENARIOS = (
    ("a2a_100", "AllToAll 满载（100%）"),
    ("a2a_75", "AllToAll 75% 负载"),
    ("a2a_50", "AllToAll 50% 负载"),
    ("a2a_25", "AllToAll 25% 负载"),
    ("perm_100", "Permutation 满载（任意置换）"),
    ("hot_center", "中心热点（中心 1/4 die 端口满载，组内互访）"),
    ("hot_corner", "角落热点（四角 1/4 die 端口满载，组内互访）"),
)


def evaluate(mesh: A.Mesh, paths: Dict[Tuple[int, Coord, Coord], List[Coord]]) -> dict:
    n = mesh.row_widths[0]
    N = mesh.n
    b = SYSTEM_TBPS / (N * N)
    pos = mesh.positions
    met = {f: path_metrics(p) for f, p in paths.items()}

    load: Dict[Edge, int] = defaultdict(int)
    for p in paths.values():
        for e in path_edges(p):
            load[e] += 1
    edges = directed_edges(mesh)
    loads = [load[e] for e in edges]
    cmax = max(loads)
    h_loads = [load[e] for e in edges if is_horizontal(*e)]
    v_loads = [load[e] for e in edges if not is_horizontal(*e)]
    lb, lb_where = bisection_lower_bound(mesh)

    ms = list(met.values())
    nf = len(ms)

    def avg(key):
        return sum(m[key] for m in ms) / nf

    # 端到端 L1→L2→L3（N³ 条组合，含同 die 段）
    zero = path_metrics([pos[0]])
    m1 = {(s, d): met.get((1, s, d), zero) for s in pos for d in pos}
    m2 = {(s, d): met.get((2, s, d), zero) for s in pos for d in pos}
    e2e = {}
    # 每段各含一份 t_sw_die + t_sw_sw；端到端各只计一次
    fixed = T_SW_DIE + T_SW_SW
    sw_adj = {"lat_max": fixed, "lat_mean": fixed}
    for key in ("hops", "lat_max", "lat_mean", "wire_max", "wire_mean", "ft_lat_max", "ft_lat_mean", "turn_lat"):
        mx = -1.0
        tot = 0.0
        arg = None
        adj = sw_adj.get(key, 0.0)
        for j in pos:
            a_best = max(pos, key=lambda i: m1[(i, j)][key])
            c_best = max(pos, key=lambda k: m2[(j, k)][key])
            v = m1[(a_best, j)][key] + m2[(j, c_best)][key] - adj
            if v > mx:
                mx, arg = v, (a_best, j, c_best)
            tot += sum(m1[(i, j)][key] for i in pos) * N + sum(m2[(j, k)][key] for k in pos) * N
            tot -= adj * N * N  # 每个 (i,j,k) 减一次
        e2e[key] = dict(max=mx, mean=tot / N**3, arg=[list(x) for x in arg])
    # 最大时延路径分解：SIO / Feedthrough 走线 / 转向 / t_sw_die / t_sw_sw
    a, j, c = (tuple(x) for x in e2e["lat_max"]["arg"])
    worst_lat = m1[(a, j)]["lat_max"] + m2[(j, c)]["lat_max"] - fixed
    worst_ft = m1[(a, j)]["ft_lat_max"] + m2[(j, c)]["ft_lat_max"]
    worst_iface = m1[(a, j)]["iface_lat"] + m2[(j, c)]["iface_lat"]
    worst_turn = m1[(a, j)]["turn_lat"] + m2[(j, c)]["turn_lat"]
    worst_end = T_SW_DIE
    worst_sw = T_SW_SW
    assert abs(worst_iface + worst_ft + worst_turn + worst_end + worst_sw - worst_lat) < 1e-6
    worst_link = max(ms, key=lambda m: m["lat_max"])

    power = {}
    for ew in WIRE_PJ_SET:
        e_map = {f: energy_pj(m, ew) for f, m in met.items()}
        # 全部功耗 = 静态 + 当前流量下的动态；SIO 静态按物理构型（每条有向边 C），满载动态即每条链路 rate = b
        sio_static = sio_static_W(len(edges), cmax * b)
        sio = sio_static + sum(sio_dyn_W(m["hops"], b) for m in ms)
        wire = sum(wire_link_W(m["ft_mean"], b, ew) for m in ms)
        ft_wire = wire
        scen = {}
        for key, label in SCENARIOS:
            r = scenario_rates(mesh, key)
            active = [p for p in pos if r[p] > 0]
            # L1 均匀喷洒到全部 L2：L1_i→L2_j 速率只取决于入口 die i 的注入率，L2_j→L3_k 只取决于出口 die k
            wire_sc = ft_sc = 0.0
            sio_sc = sio_static
            for (st, s, d), m in met.items():
                rate = (r[s] if st == 1 else r[d]) * b
                sio_sc += sio_dyn_W(m["hops"], rate)
                w = wire_link_W(m["ft_mean"], rate, ew)
                wire_sc += w
                ft_sc += w
            inj = sum(r.values()) * SYSTEM_TBPS / N
            d2d = sio_sc + wire_sc
            scen[key] = dict(label=label, sio_W=sio_sc, wire_W=wire_sc, ft_wire_W=ft_sc,
                             sio_static_W=sio_static, sio_dyn_W=sio_sc - sio_static,
                             d2d_W=d2d, line_W=0.0, W=d2d,
                             active=len(active), inj_tbps=inj)
        # 两级喷洒使任意置换与 AllToAll 满载的 die 间流量相同
        scen["perm_best"] = dict(scen["a2a_100"], label="最佳场景（CLOS 喷洒下与 AllToAll 同）")
        scen["perm_worst"] = dict(scen["a2a_100"], label="最差场景（CLOS 喷洒下与 AllToAll 同）")
        max_pj = max(e_map.values())
        static_W = SERDES_W + sio_static
        power[str(ew)] = dict(
            e_wire=ew,
            sio_W=sio,
            sio_static_W=sio_static,
            sio_dyn_W=sio - sio_static,
            sio_cfg_tbps=len(edges) * cmax * b,
            sio_used_tbps=sum(loads) * b,
            n_dir_edges=len(edges),
            wire_W=wire,
            ft_wire_W=ft_wire,
            d2d_W=sio + wire,
            line_W=0.0,
            static_W=static_W,
            total_W=SERDES_W + sio + wire,
            total_best_W=SERDES_W + sio + wire,
            total_worst_W=SERDES_W + sio + wire,
            max_path_pj=max_pj,
            e2e_max_pj=max(
                max(energy_pj(m1[(i, j)], ew) for i in pos) + max(energy_pj(m2[(j, k)], ew) for k in pos)
                for j in pos
            ),
            scenarios=scen,
        )

    hop_hist = defaultdict(int)
    for m in ms:
        hop_hist[m["hops"]] += 1
    detour = sum(1 for (st, s, d), m in met.items()
                 if m["hops"] > abs(s[0] - d[0]) + abs(s[1] - d[1]))

    return dict(
        n=n,
        N=N,
        b_tbps=b,
        ports_per_die=N_PORTS // N,
        die_port_tbps=SYSTEM_TBPS / N,
        n_flows=nf,
        n_local=2 * N,
        C=cmax,
        C_tbps=cmax * b,
        C_ports400=math.ceil(cmax * b * 1000 / PORT_GBPS - 1e-9),
        C_h=max(h_loads),
        C_v=max(v_loads),
        density_h=max(h_loads) * b / DIE_H_MM,
        density_v=max(v_loads) * b / DIE_W_MM,
        mean_edge_tbps=sum(loads) * b / len(loads),
        total_d2d_tbps=sum(loads) * b,
        lb=lb,
        lb_tbps=lb * b,
        lb_where=lb_where,
        hops_mean=avg("hops"),
        hops_max=max(m["hops"] for m in ms),
        wire_mean=avg("wire_mean"),
        wire_max=max(m["wire_max"] for m in ms),
        wire_mean_max=max(m["wire_mean"] for m in ms),
        lat_link_max=worst_link["lat_max"],
        lat_link_mean=avg("lat_mean"),
        ft_share_link_max=worst_link["ft_lat_max"] / worst_link["lat_max"],
        ft_share_mean=sum(m["ft_lat_mean"] for m in ms) / sum(m["lat_mean"] for m in ms),
        turns_mean=avg("turns"),
        detour_flows=detour,
        e2e=e2e,
        e2e_worst=dict(lat=worst_lat, ft=worst_ft, iface=worst_iface, end=worst_end, turn=worst_turn,
                       turns=m1[(a, j)]["turns"] + m2[(j, c)]["turns"],
                       sw_die=worst_end, sw_sw=worst_sw,
                       ft_share=worst_ft / worst_lat if worst_lat else 0.0),
        power=power,
        hop_hist={str(k): v for k, v in sorted(hop_hist.items())},
        loads={f"{a[0]},{a[1]}->{b_[0]},{b_[1]}": load[(a, b_)] for a, b_ in edges},
    )


def run(n: int, seeds: int, max_iter: int) -> dict:
    mesh = build_mesh(n)
    out = {}
    for scheme in SCHEMES:
        best = None
        best_paths = None
        for sd in range(1, (1 if scheme == "xy_o1turn_cw" else seeds) + 1):
            paths = route_all(mesh, scheme, seed=sd, max_iter=max_iter)
            loads: Dict[Edge, int] = defaultdict(int)
            for p in paths.values():
                for e in path_edges(p):
                    loads[e] += 1
            key = (max(loads.values()), sum(loads.values()), sum(path_turns(p) for p in paths.values()))
            if best is None or key < best:
                best, best_paths = key, paths
        for p in best_paths.values():
            m = path_metrics(p)
            if m["hops"]:
                hs = [is_horizontal(a, b) for a, b in zip(p[:-1], p[1:])]
                nx = sum(hs)
                assert abs(latency_max_ns(nx, m["hops"] - nx, m["turns"], hs[0], hs[-1]) - m["lat_max"]) < 1e-6
        res = evaluate(mesh, best_paths)
        res["latency_bound_ns"] = longest_link_latency(n)
        if scheme == "longest_bound":
            assert res["lat_link_max"] <= res["latency_bound_ns"] + 1e-6
        res["scheme"] = scheme
        res["scheme_name"] = SCHEME_NAME[scheme]
        res["paths"] = {f"{st}|{s[0]},{s[1]}|{d[0]},{d[1]}": [list(x) for x in p]
                        for (st, s, d), p in best_paths.items()}
        out[scheme] = res
        print(f"  {n}x{n} {scheme:14s} C={res['C']} ({res['C_tbps']:.2f}T, LB {res['lb']})  "
              f"hops avg/max={res['hops_mean']:.2f}/{res['hops_max']}  "
              f"e2e lat max={res['e2e']['lat_max']['max']:.0f}ns  "
              f"P(0.1)={res['power']['0.1']['d2d_W']:.0f}W P(0.06)={res['power']['0.06']['d2d_W']:.0f}W  "
              f"detour={res['detour_flows']}")
    return out


def reevaluate(n: int, path: Path) -> dict:
    """按当前模型重新评估已存路径（时延 / 功耗参数变化不影响布线时使用）。"""
    mesh = build_mesh(n)
    old = json.loads(path.read_text())
    out = {}
    for scheme, r in old.items():
        paths = {}
        for k, p in r["paths"].items():
            st, s, d = k.split("|")
            paths[(int(st), tuple(map(int, s.split(","))), tuple(map(int, d.split(","))))] = [tuple(x) for x in p]
        res = evaluate(mesh, paths)
        res["latency_bound_ns"] = longest_link_latency(n)
        res["scheme"] = scheme
        res["scheme_name"] = SCHEME_NAME[scheme]
        res["paths"] = r["paths"]
        out[scheme] = res
        print(f"  {n}x{n} {scheme:14s} C={res['C']}  e2e lat max={res['e2e']['lat_max']['max']:.0f}ns "
              f"mean={res['e2e']['lat_mean']['mean']:.0f}ns  P(0.1)={res['power']['0.1']['total_W']:.0f}W")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--seeds", type=int, default=4)
    ap.add_argument("--max-iter", type=int, default=60)
    ap.add_argument("--out", type=Path, default=Path("report_dsl_400t/data"))
    ap.add_argument("--from-paths", action="store_true",
                    help="不重新布线：读取 --out 中已存路径，仅按当前时延 / 功耗模型重新评估")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for n in args.sizes:
        print(f"=== {n}x{n} mesh, CLOS[{n*n},{n*n},{n*n}] ===")
        res = reevaluate(n, args.out / f"dsl_{n}x{n}.json") if args.from_paths else run(n, args.seeds, args.max_iter)
        path = args.out / f"dsl_{n}x{n}.json"
        path.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
