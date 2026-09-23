#!/usr/bin/env python3
"""
NOW + 跳线层 3D mesh Clos mapping under latency_max.

Defaults (see mesh3d.py):
  NOW z=0 mesh (4,8,10,10,10,10,8,6), delay 80 ns, capacity 350×200G (Layer 0)
  Jumper z=1 (--jumper-topo single|dual|quad|full), delay 1 ns, capacity 180×200G
  Vertical (NOW↔jumper) capacity 250×200G per directed edge, delay 5 ns
  Prefer Manhattan; top --manhattan-top-pct% by opt delay must be Manhattan
  Optional hot-jumper rebalance: vacate short paths, improve longest (default on)
  Binary-search minimal feasible latency_max from 1000 µs downward
  Power: NOW 0.06 pJ/(bit·mm)×25mm; vertical 1.3/2 pJ/bit; jumper 0

Exports each logical edge's physical path, delay, energy (pJ/bit), and
data-movement power P = E × 200 Gbps × 1.5 (W); also max path delay and total power.

Usage:
  python3 optimize_3d_mapping.py
  python3 optimize_3d_mapping.py --jumper-topo dual --out-dir results_3d_jumper_dual/
  python3 optimize_3d_mapping.py --jumper-topo quad --out-dir results_3d_jumper_quad/
  python3 optimize_3d_mapping.py --jumper-topo full --out-dir results_3d_jumper_full/
  python3 optimize_3d_mapping.py --manhattan-top-pct 30 --rebalance-rounds 12
  python3 optimize_3d_mapping.py --no-rebalance-hot
  python3 optimize_3d_mapping.py --latency-max 500 --out-dir results_3d_now_jumper/
  python3 optimize_3d_mapping.py --latency-hi-us 1000
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import random
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import algorithm1_pairwise_exchange as A
from mesh3d import (
    Coord3,
    Mesh3D,
    Mesh3DConfig,
    JUMPER_TOPO_PRESETS,
    POWER_ACCEL_RATIO,
    build_mesh3d,
    energy_to_power_w,
    format_jumper_windows,
    path_delay as mesh_path_delay,
    path_energy_pj_per_bit,
    summarize_mesh3d,
)

SSC = int
PORT_BW_GBPS = 200.0


# ---------------------------------------------------------------------------
# Delay distances & path enumeration
# ---------------------------------------------------------------------------


def dijkstra_delay(
    mesh: Mesh3D, src: Coord3
) -> Tuple[Dict[Coord3, float], Dict[Coord3, List[Coord3]]]:
    nbrs = mesh.nbr_map()
    dist = {src: 0.0}
    parents: Dict[Coord3, List[Coord3]] = {src: []}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d != dist[u]:
            continue
        for v in nbrs[u]:
            nd = d + mesh.edge_delay(u, v)
            if v not in dist or nd < dist[v] - 1e-12:
                dist[v] = nd
                parents[v] = [u]
                heapq.heappush(pq, (nd, v))
            elif abs(nd - dist[v]) <= 1e-12:
                if u not in parents[v]:
                    parents[v].append(u)
    return dist, parents


def enumerate_delay_feasible_paths(
    mesh: Mesh3D,
    src: Coord3,
    dst: Coord3,
    latency_max: float,
    dist_from_dst: Dict[Coord3, float],
    max_paths: int = 64,
) -> List[List[Coord3]]:
    """
    Enumerate delay-shortest simple paths (capped).

    Zero-delay jumper edges make the full latency-feasible set enormous;
    load-balancing among delay-optimal paths is sufficient and fast.
    All returned paths satisfy delay == opt <= latency_max.
    """
    if src == dst:
        return [[src]]
    if dst not in dist_from_dst:
        return []
    opt = dist_from_dst[src]
    if opt > latency_max + 1e-12:
        return []

    nbrs = mesh.nbr_map()
    paths: List[List[Coord3]] = []

    def dfs(u: Coord3, used: set, path: List[Coord3], delay_so_far: float) -> None:
        if len(paths) >= max_paths:
            return
        if u == dst:
            paths.append(list(path))
            return
        for v in nbrs[u]:
            if v in used or v not in dist_from_dst:
                continue
            step = mesh.edge_delay(u, v)
            if abs((delay_so_far + step + dist_from_dst[v]) - opt) > 1e-9:
                continue
            used.add(v)
            path.append(v)
            dfs(v, used, path, delay_so_far + step)
            path.pop()
            used.remove(v)
            if len(paths) >= max_paths:
                return

    dfs(src, {src}, [src], 0.0)
    return paths


def path_delay(mesh: Mesh3D, nodes: Sequence[Coord3]) -> float:
    return mesh_path_delay(mesh, nodes)


def path_edges(nodes: Sequence[Coord3]) -> List[Tuple[Coord3, Coord3]]:
    return [(a, b) for a, b in zip(nodes, nodes[1:])]


def _edge_has_cap_room(
    mesh: Mesh3D,
    a: Coord3,
    b: Coord3,
    loads: Dict[Tuple[Coord3, Coord3], int],
) -> bool:
    nxt = loads[(a, b)] + 1
    if a[0] == 0 and b[0] == 0:
        return nxt <= mesh.config.now_capacity_links
    if a[0] == 1 and b[0] == 1:
        return nxt <= mesh.config.jumper_capacity_links
    if a[0] != b[0]:
        return nxt <= mesh.config.vertical_capacity_links
    return True


def _count_cap_violations(
    mesh: Mesh3D, loads: Dict[Tuple[Coord3, Coord3], int]
) -> int:
    ncap = mesh.config.now_capacity_links
    jcap = mesh.config.jumper_capacity_links
    vcap = mesh.config.vertical_capacity_links
    viol = 0
    for (a, b), v in loads.items():
        if a[0] == 0 and b[0] == 0 and v > ncap:
            viol += 1
        elif a[0] == 1 and b[0] == 1 and v > jcap:
            viol += 1
        elif a[0] != b[0] and v > vcap:
            viol += 1
    return viol


def find_capacity_aware_path(
    mesh: Mesh3D,
    src: Coord3,
    dst: Coord3,
    latency_max: float,
    loads: Dict[Tuple[Coord3, Coord3], int],
    dist_from_dst: Dict[Coord3, float],
    manhattan_only: bool = True,
) -> Optional[List[Coord3]]:
    """
    Capacity-respecting path with delay ≤ latency_max.

    Prefer Manhattan (= delay-shortest) paths:
      - manhattan_only=True: only expand along the delay-optimal DAG
      - else: lex minimize (delay, max_edge_load, sum_edge_load)
    """
    if src == dst:
        return [src]
    if dst not in dist_from_dst or dist_from_dst[src] > latency_max + 1e-12:
        return None

    opt = dist_from_dst[src]
    nbrs = mesh.nbr_map()
    # best[u] = (delay, max_load, sum_load)
    best: Dict[Coord3, Tuple[float, int, int]] = {src: (0.0, 0, 0)}
    parent: Dict[Coord3, Optional[Coord3]] = {src: None}
    # heap ordered by (delay, max_load, sum_load, node)
    pq: List[Tuple[float, int, int, Coord3]] = [(0.0, 0, 0, src)]

    while pq:
        d, ml, sl, u = heapq.heappop(pq)
        cur = best.get(u)
        if cur is None or (d, ml, sl) != cur:
            continue
        if u == dst:
            break
        for v in nbrs[u]:
            if v not in dist_from_dst:
                continue
            if not _edge_has_cap_room(mesh, u, v, loads):
                continue
            step = mesh.edge_delay(u, v)
            nd = d + step
            if nd + dist_from_dst[v] > latency_max + 1e-12:
                continue
            if manhattan_only and abs((nd + dist_from_dst[v]) - opt) > 1e-9:
                continue
            el = loads[(u, v)]
            key = (nd, max(ml, el), sl + el)
            prev = best.get(v)
            if prev is None or key < prev:
                best[v] = key
                parent[v] = u
                heapq.heappush(pq, (key[0], key[1], key[2], v))

    if dst not in parent:
        return None
    path = [dst]
    while path[-1] != src:
        p = parent[path[-1]]
        if p is None:
            return None
        path.append(p)
    path.reverse()
    return path


def is_delay_manhattan(
    mesh: Mesh3D,
    nodes: Sequence[Coord3],
    dist_from_dst: Dict[Coord3, float],
) -> bool:
    """True iff path delay equals delay-shortest distance (Manhattan / SP)."""
    if len(nodes) < 2:
        return True
    src, dst = nodes[0], nodes[-1]
    if dst not in dist_from_dst:
        return False
    return abs(path_delay(mesh, nodes) - dist_from_dst[src]) <= 1e-9


# ---------------------------------------------------------------------------
# Routing under latency_max
# ---------------------------------------------------------------------------


@dataclass
class RouteResult:
    feasible: bool
    paths: List[Optional[List[Coord3]]]  # per logical edge
    meta: List[Tuple[str, int, int]]  # stage, src_ssc, dst_ssc
    loads: Dict[Tuple[Coord3, Coord3], int]
    C: int
    max_path_delay: float
    n_infeasible: int
    n_manhattan: int = 0
    n_non_manhattan: int = 0
    n_must_manhattan: int = 0
    n_must_manhattan_ok: int = 0
    manhattan_top_pct: float = 0.0


def logical_commodities(n: int) -> List[Tuple[str, int, int]]:
    meta = []
    for stage in ("L1-L2", "L2-L3"):
        for i in range(n):
            for j in range(n):
                meta.append((stage, i, j))
    return meta


def path_respects_caps(
    mesh: Mesh3D,
    nodes: Sequence[Coord3],
    loads: Dict[Tuple[Coord3, Coord3], int],
) -> bool:
    """True iff NOW / jumper / vertical directed edges on the path have room under caps."""
    for a, b in path_edges(nodes):
        if not _edge_has_cap_room(mesh, a, b, loads):
            return False
    return True


def select_must_manhattan_indices(
    opt_delays: Sequence[float],
    manhattan_top_pct: float,
) -> set:
    """
    Indices whose opt_delay ranks in the top manhattan_top_pct% (largest delays).
    Local (0-delay) edges are never forced.
    """
    pct = max(0.0, min(100.0, float(manhattan_top_pct)))
    ranked = sorted(
        ((d, i) for i, d in enumerate(opt_delays) if d > 1e-12),
        reverse=True,
    )
    if not ranked or pct <= 0:
        return set()
    k = int(math.ceil(len(ranked) * pct / 100.0))
    k = max(0, min(len(ranked), k))
    return {i for _, i in ranked[:k]}


def route_under_latency(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    latency_max: float,
    seed: int = 1,
    max_paths: int = 48,
    prefer_manhattan: bool = True,
    manhattan_top_pct: float = 20.0,
) -> RouteResult:
    """
    Unsplittable load-aware routing among delay-feasible paths.

    - Commodities in the top ``manhattan_top_pct``% by opt delay **must** use
      Manhattan (= delay-shortest) paths.
    - Remaining commodities prefer Manhattan; soft shortest-delay detour if blocked.
    Caps: NOW / jumper / vertical capacity links.
    """
    n = len(mapping)
    meta = logical_commodities(n)
    rng = random.Random(seed)

    dist_to: Dict[Coord3, Dict[Coord3, float]] = {}
    for t in mesh.positions:
        dist_to[t] = dijkstra_delay(mesh, t)[0]

    opt_delays: List[float] = []
    for _, i, j in meta:
        src, dst = mapping[i], mapping[j]
        if src == dst:
            opt_delays.append(0.0)
        else:
            opt_delays.append(dist_to[dst].get(src, float("inf")))

    must_manh = select_must_manhattan_indices(opt_delays, manhattan_top_pct)

    loads: Dict[Tuple[Coord3, Coord3], int] = defaultdict(int)
    paths: List[Optional[List[Coord3]]] = [None] * len(meta)

    # Route must-Manhattan first (hardest / longest opt), then the rest.
    # Within each group: shorter opt first for packing (stable with prior behavior on soft).
    order = []
    for idx, md in enumerate(opt_delays):
        must = 0 if idx in must_manh else 1
        # must group: longer first; soft group: shorter first
        tie = -md if must == 0 else md
        order.append((must, tie, rng.random(), idx))
    order.sort()

    n_inf = 0
    n_man = 0
    n_non = 0
    n_must_ok = 0
    max_d = 0.0

    for _, _, _, idx in order:
        _, i, j = meta[idx]
        src, dst = mapping[i], mapping[j]
        md = opt_delays[idx]
        require_manh = idx in must_manh

        if src == dst:
            paths[idx] = [src]
            n_man += 1
            continue
        if md > latency_max + 1e-12:
            n_inf += 1
            paths[idx] = None
            continue

        # 1) Delay-optimal (Manhattan) candidates + load balance
        cands = enumerate_delay_feasible_paths(
            mesh, src, dst, latency_max, dist_to[dst], max_paths=max_paths
        )
        feasible_cands = [p for p in cands if path_respects_caps(mesh, p, loads)]

        # 2) Capacity-aware search on Manhattan DAG
        if not feasible_cands and prefer_manhattan:
            alt = find_capacity_aware_path(
                mesh,
                src,
                dst,
                latency_max,
                loads,
                dist_to[dst],
                manhattan_only=True,
            )
            if alt is not None:
                feasible_cands = [alt]

        # 3) Soft fallback only if NOT in must-Manhattan set
        if not feasible_cands and not require_manh:
            alt = find_capacity_aware_path(
                mesh,
                src,
                dst,
                latency_max,
                loads,
                dist_to[dst],
                manhattan_only=False,
            )
            if alt is not None:
                feasible_cands = [alt]

        if not feasible_cands:
            n_inf += 1
            paths[idx] = None
            continue

        best = None
        best_sc = None
        opt = md
        for nodes in feasible_cands:
            edges = path_edges(nodes)
            vals = [loads[e] for e in edges]
            dly = path_delay(mesh, nodes)
            sc = (
                0 if abs(dly - opt) <= 1e-9 else 1,
                dly,
                max(vals) if vals else 0,
                sum(vals),
                path_energy_pj_per_bit(mesh, nodes),
            )
            if best_sc is None or sc < best_sc:
                best_sc = sc
                best = nodes
        assert best is not None
        for e in path_edges(best):
            loads[e] += 1
        paths[idx] = best
        dly = path_delay(mesh, best)
        max_d = max(max_d, dly)
        is_manh = abs(dly - opt) <= 1e-9
        if is_manh:
            n_man += 1
            if require_manh:
                n_must_ok += 1
        else:
            n_non += 1
            # must-Manhattan should never reach here
            if require_manh:
                n_inf += 1
                paths[idx] = None
                # roll back load
                for e in path_edges(best):
                    loads[e] -= 1
                    if loads[e] <= 0:
                        del loads[e]
                continue

    cap_viol = _count_cap_violations(mesh, loads)

    feasible = n_inf == 0 and cap_viol == 0
    C = max(loads.values()) if loads else 0
    return RouteResult(
        feasible=feasible,
        paths=paths,
        meta=meta,
        loads=dict(loads),
        C=C,
        max_path_delay=max_d,
        n_infeasible=n_inf,
        n_manhattan=n_man,
        n_non_manhattan=n_non,
        n_must_manhattan=len(must_manh),
        n_must_manhattan_ok=n_must_ok,
        manhattan_top_pct=float(manhattan_top_pct),
    )


def _rebuild_route_stats(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    meta: Sequence[Tuple[str, int, int]],
    paths: List[Optional[List[Coord3]]],
    loads: Dict[Tuple[Coord3, Coord3], int],
    manhattan_top_pct: float,
) -> RouteResult:
    dist_to = {t: dijkstra_delay(mesh, t)[0] for t in mesh.positions}
    opt_delays: List[float] = []
    for _, i, j in meta:
        src, dst = mapping[i], mapping[j]
        if src == dst:
            opt_delays.append(0.0)
        else:
            opt_delays.append(dist_to[dst].get(src, float("inf")))
    must = select_must_manhattan_indices(opt_delays, manhattan_top_pct)

    n_inf = 0
    n_man = 0
    n_non = 0
    n_must_ok = 0
    max_d = 0.0
    for idx, nodes in enumerate(paths):
        if nodes is None:
            n_inf += 1
            continue
        dly = path_delay(mesh, nodes)
        max_d = max(max_d, dly)
        opt = opt_delays[idx]
        is_manh = abs(dly - opt) <= 1e-9 if opt < float("inf") else False
        if is_manh:
            n_man += 1
            if idx in must:
                n_must_ok += 1
        else:
            n_non += 1

    cap_viol = _count_cap_violations(mesh, loads)

    C = max(loads.values()) if loads else 0
    return RouteResult(
        feasible=n_inf == 0 and cap_viol == 0,
        paths=paths,
        meta=list(meta),
        loads=dict(loads),
        C=C,
        max_path_delay=max_d,
        n_infeasible=n_inf,
        n_manhattan=n_man,
        n_non_manhattan=n_non,
        n_must_manhattan=len(must),
        n_must_manhattan_ok=n_must_ok,
        manhattan_top_pct=float(manhattan_top_pct),
    )


def rebalance_hot_jumper_tail(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    result: RouteResult,
    latency_max: float,
    max_paths: int = 48,
    hot_load_frac: float = 0.8,
    short_delay_ns: float = 200.0,
    max_rounds: int = 8,
    verbose: bool = True,
) -> RouteResult:
    """
    Iteratively reduce global max path delay by:
      1) identifying jumper edges with load > hot_load_frac * cap;
      2) vacating short paths (delay ≤ short_delay_ns) off those edges;
      3) re-routing current longest-tier paths onto Manhattan / shorter paths.
    Repeats while max delay improves.
    """
    if not result.feasible or not result.paths:
        return result

    jcap = mesh.config.jumper_capacity_links
    mapping_l = list(mapping)
    meta = result.meta
    paths: List[Optional[List[Coord3]]] = [
        list(p) if p is not None else None for p in result.paths
    ]
    loads: Dict[Tuple[Coord3, Coord3], int] = defaultdict(int)
    for p in paths:
        if p and len(p) >= 2:
            for e in path_edges(p):
                loads[e] += 1

    dist_to = {t: dijkstra_delay(mesh, t)[0] for t in mesh.positions}

    def unload(path: Sequence[Coord3]) -> None:
        for e in path_edges(path):
            loads[e] -= 1
            if loads[e] <= 0:
                del loads[e]

    def loadp(path: Sequence[Coord3]) -> None:
        for e in path_edges(path):
            loads[e] += 1

    def path_d(idx: int) -> float:
        p = paths[idx]
        if p is None:
            return float("inf")
        return path_delay(mesh, p)

    def hot_edges() -> set:
        thr = hot_load_frac * jcap
        return {
            e
            for e, v in loads.items()
            if e[0][0] == 1 and e[1][0] == 1 and v > thr + 1e-12
        }

    def count_at(d0: float) -> int:
        return sum(
            1
            for i, p in enumerate(paths)
            if p is not None and abs(path_d(i) - d0) <= 1e-9
        )

    prev_max = max((path_d(i) for i, p in enumerate(paths) if p), default=0.0)
    best_key = (prev_max, count_at(prev_max))
    best_snap = (
        [list(p) if p is not None else None for p in paths],
        dict(loads),
    )
    short_thr = float(short_delay_ns)
    stagnant = 0

    if verbose:
        print(
            f"[rebalance] start max_delay={prev_max:g}ns  "
            f"n_at_max={count_at(prev_max)}  hot_frac={hot_load_frac:g}  "
            f"short≤{short_delay_ns:g}ns  rounds≤{max_rounds}",
            flush=True,
        )

    for rnd in range(1, max_rounds + 1):
        hot = hot_edges()
        cur_max = max((path_d(i) for i, p in enumerate(paths) if p), default=0.0)
        if not hot:
            if verbose:
                print(f"[rebalance] round {rnd}: no hot jumper edges; stop", flush=True)
            break

        # Snapshot before round (reject if max worsens)
        snap_paths = [list(p) if p is not None else None for p in paths]
        snap_loads = dict(loads)

        longest = [
            i
            for i, p in enumerate(paths)
            if p is not None and abs(path_d(i) - cur_max) <= 1e-9
        ]
        longest_set = set(longest)
        effective_short = min(short_thr, cur_max - 1e-9)

        vacate_idxs = [
            i
            for i, p in enumerate(paths)
            if p is not None
            and i not in longest_set
            and path_d(i) <= effective_short + 1e-12
            and any(e in hot for e in path_edges(p))
        ]
        vacate_idxs.sort(key=path_d)
        n_vac = 0
        for i in vacate_idxs:
            old = paths[i]
            assert old is not None
            _, si, sj = meta[i]
            src, dst = mapping_l[si], mapping_l[sj]
            unload(old)
            saved = {e: loads[e] for e in hot}
            for e in hot:
                loads[e] = jcap
            alt = find_capacity_aware_path(
                mesh, src, dst, latency_max, loads, dist_to[dst], manhattan_only=False
            )
            for e in hot:
                if e in saved:
                    loads[e] = saved[e]
                elif e in loads:
                    del loads[e]
            if (
                alt is not None
                and not any(e in hot for e in path_edges(alt))
                and path_respects_caps(mesh, alt, loads)
            ):
                loadp(alt)
                paths[i] = alt
                n_vac += 1
            else:
                loadp(old)

        n_imp = 0
        for i in longest:
            old = paths[i]
            assert old is not None
            old_d = path_delay(mesh, old)
            _, si, sj = meta[i]
            src, dst = mapping_l[si], mapping_l[sj]
            unload(old)
            mans = enumerate_delay_feasible_paths(
                mesh, src, dst, latency_max, dist_to[dst], max_paths=max_paths
            )
            feas = [p for p in mans if path_respects_caps(mesh, p, loads)]
            if not feas:
                alt = find_capacity_aware_path(
                    mesh, src, dst, latency_max, loads, dist_to[dst], manhattan_only=True
                )
                if alt is not None:
                    feas = [alt]
            if not feas:
                alt = find_capacity_aware_path(
                    mesh,
                    src,
                    dst,
                    latency_max,
                    loads,
                    dist_to[dst],
                    manhattan_only=False,
                )
                if alt is not None and path_delay(mesh, alt) < old_d - 1e-9:
                    feas = [alt]
            if feas:
                best = min(
                    feas,
                    key=lambda p: (
                        path_delay(mesh, p),
                        max([loads[e] for e in path_edges(p)] or [0]),
                        sum(loads[e] for e in path_edges(p)),
                    ),
                )
                loadp(best)
                paths[i] = best
                if path_delay(mesh, best) < old_d - 1e-9:
                    n_imp += 1
            else:
                loadp(old)

        new_max = max((path_d(i) for i, p in enumerate(paths) if p), default=0.0)
        tier = [
            i
            for i, p in enumerate(paths)
            if p is not None and abs(path_d(i) - new_max) <= 1e-9
        ]
        n_tier_imp = 0
        for i in tier:
            old = paths[i]
            assert old is not None
            old_d = path_delay(mesh, old)
            _, si, sj = meta[i]
            src, dst = mapping_l[si], mapping_l[sj]
            unload(old)
            mans = enumerate_delay_feasible_paths(
                mesh, src, dst, latency_max, dist_to[dst], max_paths=max_paths
            )
            feas = [p for p in mans if path_respects_caps(mesh, p, loads)]
            if not feas:
                am = find_capacity_aware_path(
                    mesh,
                    src,
                    dst,
                    latency_max,
                    loads,
                    dist_to[dst],
                    manhattan_only=True,
                )
                if am is not None:
                    feas = [am]
            alt = find_capacity_aware_path(
                mesh,
                src,
                dst,
                min(latency_max, old_d - 1e-9) if old_d > 0 else latency_max,
                loads,
                dist_to[dst],
                manhattan_only=False,
            )
            if alt is not None and path_respects_caps(mesh, alt, loads):
                feas.append(alt)
            feas = [p for p in feas if path_delay(mesh, p) < old_d - 1e-9]
            if feas:
                best = min(
                    feas,
                    key=lambda p: (
                        path_delay(mesh, p),
                        max([loads[e] for e in path_edges(p)] or [0]),
                    ),
                )
                loadp(best)
                paths[i] = best
                n_tier_imp += 1
            else:
                loadp(old)

        new_max = max((path_d(i) for i, p in enumerate(paths) if p), default=0.0)
        n_at = count_at(new_max)

        # Reject round if max delay got worse than best so far
        if new_max > best_key[0] + 1e-9:
            paths = [list(p) if p is not None else None for p in snap_paths]
            loads.clear()
            loads.update(snap_loads)
            stagnant += 1
            if verbose:
                print(
                    f"[rebalance] round {rnd}: REJECT (max {cur_max:g}→{new_max:g})  "
                    f"restore best={best_key[0]:g}ns; escalate short_thr",
                    flush=True,
                )
            short_thr = min(cur_max * 0.95, max(short_thr + 80.0, short_thr * 1.5))
            if stagnant >= 3:
                if verbose:
                    print("[rebalance] too many rejected rounds; stop", flush=True)
                break
            continue

        if verbose:
            print(
                f"[rebalance] round {rnd}: vacated={n_vac} (short≤{effective_short:g})  "
                f"longest_improved={n_imp}/{len(longest)}  "
                f"tier_improved={n_tier_imp}  "
                f"max {cur_max:g}→{new_max:g}ns  n_at_max={n_at}  hot={len(hot_edges())}",
                flush=True,
            )

        key = (new_max, n_at)
        if key < best_key:
            best_key = key
            best_snap = (
                [list(p) if p is not None else None for p in paths],
                dict(loads),
            )
            stagnant = 0
        else:
            stagnant += 1

        if n_imp == 0 and n_tier_imp == 0 and abs(new_max - cur_max) <= 1e-9:
            short_thr = min(cur_max * 0.95, max(short_thr + 80.0, short_thr * 1.5))
            if verbose:
                print(
                    f"[rebalance] plateau; escalate short_thr → {short_thr:g}ns",
                    flush=True,
                )
            if stagnant >= 3:
                if verbose:
                    print("[rebalance] plateau persisted; stop", flush=True)
                break

        prev_max = new_max

    # Restore lexicographically best (min max_delay, then min n_at_max)
    paths = best_snap[0]
    loads = defaultdict(int, best_snap[1])
    if verbose:
        print(
            f"[rebalance] keep best max_delay={best_key[0]:g}ns  n_at_max={best_key[1]}",
            flush=True,
        )

    return _rebuild_route_stats(
        mesh,
        mapping_l,
        meta,
        paths,
        dict(loads),
        result.manhattan_top_pct,
    )


def compress_longest_tail(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    result: RouteResult,
    latency_max: float,
    max_rounds: int = 24,
    band_ns: float = 40.0,
    vacate_short_ns: float = 350.0,
    vacate_every: int = 3,
    verbose: bool = True,
) -> RouteResult:
    """
    High-intensity post-pass: repeatedly shorten paths at (or near) the current
    global max delay. Periodically vacates short paths that share edges with
    the longest tier to free capacity. Keeps the lexicographically best
    (min max_delay, then min n_at_max).
    """
    if not result.feasible or not result.paths:
        return result

    mapping_l = list(mapping)
    meta = result.meta
    paths: List[Optional[List[Coord3]]] = [
        list(p) if p is not None else None for p in result.paths
    ]
    loads: Dict[Tuple[Coord3, Coord3], int] = defaultdict(int)
    for p in paths:
        if p and len(p) >= 2:
            for e in path_edges(p):
                loads[e] += 1

    dist_to = {t: dijkstra_delay(mesh, t)[0] for t in mesh.positions}
    rng = random.Random(7)

    def unload(path: Sequence[Coord3]) -> None:
        for e in path_edges(path):
            loads[e] -= 1
            if loads[e] <= 0:
                del loads[e]

    def loadp(path: Sequence[Coord3]) -> None:
        for e in path_edges(path):
            loads[e] += 1

    def dly(i: int) -> float:
        p = paths[i]
        return path_delay(mesh, p) if p else float("inf")

    def cur_max() -> float:
        return max((dly(i) for i, p in enumerate(paths) if p), default=0.0)

    def count_at(d0: float) -> int:
        return sum(1 for i, p in enumerate(paths) if p and abs(dly(i) - d0) <= 1e-9)

    best_key = (cur_max(), count_at(cur_max()))
    best_snap = (
        [list(p) if p is not None else None for p in paths],
        dict(loads),
    )
    if verbose:
        print(
            f"[compress] start max_delay={best_key[0]:g}ns  n_at_max={best_key[1]}  "
            f"rounds≤{max_rounds}  band={band_ns:g}ns",
            flush=True,
        )

    for rnd in range(1, max_rounds + 1):
        md = cur_max()
        targets = [
            i
            for i, p in enumerate(paths)
            if p is not None and dly(i) >= md - band_ns - 1e-12
        ]
        targets.sort(key=lambda i: (-dly(i), rng.random()))

        n_vac = 0
        if vacate_every > 0 and rnd % vacate_every == 0:
            longest = {
                i for i, p in enumerate(paths) if p and abs(dly(i) - md) <= 1e-9
            }
            hot: set = set()
            for i in longest:
                hot.update(path_edges(paths[i]))  # type: ignore[arg-type]
            short_idxs = [
                i
                for i, p in enumerate(paths)
                if p is not None
                and i not in longest
                and dly(i) <= vacate_short_ns + 1e-12
                and any(e in hot for e in path_edges(p))
            ]
            short_idxs.sort(key=dly)
            for i in short_idxs[:2500]:
                old = paths[i]
                assert old is not None
                _, si, sj = meta[i]
                src, dst = mapping_l[si], mapping_l[sj]
                unload(old)
                alt = find_capacity_aware_path(
                    mesh, src, dst, latency_max, loads, dist_to[dst], manhattan_only=True
                )
                if alt is None:
                    alt = find_capacity_aware_path(
                        mesh,
                        src,
                        dst,
                        latency_max,
                        loads,
                        dist_to[dst],
                        manhattan_only=False,
                    )
                if alt is not None and path_respects_caps(mesh, alt, loads):
                    loadp(alt)
                    paths[i] = alt
                    n_vac += 1
                else:
                    loadp(old)

        n_imp = 0
        for i in targets:
            old = paths[i]
            if old is None:
                continue
            old_d = path_delay(mesh, old)
            if old_d < md - band_ns - 1e-12:
                continue
            _, si, sj = meta[i]
            src, dst = mapping_l[si], mapping_l[sj]
            unload(old)
            lim = min(latency_max, old_d - 1e-6)
            alt = find_capacity_aware_path(
                mesh, src, dst, lim, loads, dist_to[dst], manhattan_only=True
            )
            if alt is None:
                alt = find_capacity_aware_path(
                    mesh, src, dst, lim, loads, dist_to[dst], manhattan_only=False
                )
            if alt is not None and path_delay(mesh, alt) < old_d - 1e-9:
                loadp(alt)
                paths[i] = alt
                n_imp += 1
            else:
                loadp(old)

        new_md = cur_max()
        n_at = count_at(new_md)
        key = (new_md, n_at)
        if key < best_key:
            best_key = key
            best_snap = (
                [list(p) if p is not None else None for p in paths],
                dict(loads),
            )
        if verbose:
            print(
                f"[compress] round {rnd}: vacate={n_vac} improved={n_imp}/{len(targets)}  "
                f"max {md:g}→{new_md:g}ns  n_at_max={n_at}  best={best_key[0]:g}/{best_key[1]}",
                flush=True,
            )
        if n_imp == 0 and n_vac == 0:
            if verbose:
                print("[compress] no further improvement; stop", flush=True)
            break

    paths = best_snap[0]
    loads = defaultdict(int, best_snap[1])
    if verbose:
        print(
            f"[compress] keep best max_delay={best_key[0]:g}ns  n_at_max={best_key[1]}",
            flush=True,
        )
    return _rebuild_route_stats(
        mesh,
        mapping_l,
        meta,
        paths,
        dict(loads),
        result.manhattan_top_pct,
    )


# ---------------------------------------------------------------------------
# Pairwise exchange on Layer-0 positions
# ---------------------------------------------------------------------------


def pairwise_exchange_3d(
    mesh: Mesh3D,
    initial: Sequence[Coord3],
    latency_max: float,
    rng: random.Random,
    max_rounds: int = 2,
    pair_samples: int = 80,
    seed_route: int = 1,
    max_paths: int = 48,
    manhattan_top_pct: float = 20.0,
) -> Tuple[List[Coord3], RouteResult]:
    mapping = list(initial)
    best = route_under_latency(
        mesh,
        mapping,
        latency_max,
        seed=seed_route,
        max_paths=max_paths,
        manhattan_top_pct=manhattan_top_pct,
    )
    if not best.feasible:
        return mapping, best

    n = len(mapping)
    for _ in range(max_rounds):
        improved = False
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        rng.shuffle(pairs)
        pairs = pairs[:pair_samples]
        for i, j in pairs:
            mapping[i], mapping[j] = mapping[j], mapping[i]
            cur = route_under_latency(
                mesh,
                mapping,
                latency_max,
                seed=seed_route,
                max_paths=max_paths,
                manhattan_top_pct=manhattan_top_pct,
            )
            if cur.feasible and cur.C < best.C:
                best = cur
                improved = True
            else:
                mapping[i], mapping[j] = mapping[j], mapping[i]
        if not improved:
            break
    final = route_under_latency(
        mesh,
        mapping,
        latency_max,
        seed=seed_route,
        max_paths=max_paths,
        manhattan_top_pct=manhattan_top_pct,
    )
    return mapping, final


def _route_score(
    mesh: Mesh3D, paths: Sequence[Optional[List[Coord3]]]
) -> Tuple[float, int, float]:
    """Lexicographic score: (max_hop_delay, n_at_max, sum_delay)."""
    delays = [path_delay(mesh, p) for p in paths if p]
    if not delays:
        return (float("inf"), 0, 0.0)
    md = max(delays)
    n_at = sum(1 for d in delays if abs(d - md) <= 1e-9)
    return (md, n_at, sum(delays))


def simulated_anneal_routes(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    result: RouteResult,
    latency_max: float,
    rng: random.Random,
    steps: int = 4000,
    t0: float = 80.0,
    t_min: float = 0.5,
    cool: float = 0.997,
    verbose: bool = True,
) -> RouteResult:
    """
    Simulated annealing over capacity-feasible path reassignments.
    Objective: minimize (max hop delay, n_at_max, sum delay). Accepts uphill
    moves early to escape rebalance/compress local optima.
    """
    if not result.feasible or not result.paths:
        return result

    mapping_l = list(mapping)
    meta = result.meta
    paths: List[Optional[List[Coord3]]] = [
        list(p) if p is not None else None for p in result.paths
    ]
    loads: Dict[Tuple[Coord3, Coord3], int] = defaultdict(int)
    for p in paths:
        if p and len(p) >= 2:
            for e in path_edges(p):
                loads[e] += 1

    dist_to = {t: dijkstra_delay(mesh, t)[0] for t in mesh.positions}
    idxs = [i for i, p in enumerate(paths) if p is not None]
    score = _route_score(mesh, paths)
    best_score = score
    best_snap = (
        [list(p) if p is not None else None for p in paths],
        dict(loads),
    )
    T = t0
    n_acc = 0
    n_imp = 0
    if verbose:
        print(
            f"[SA] start max_hop={score[0]:g} n_at={score[1]}  "
            f"steps={steps} T0={t0:g}",
            flush=True,
        )

    for step in range(1, steps + 1):
        i = idxs[rng.randrange(len(idxs))]
        old = paths[i]
        assert old is not None
        old_d = path_delay(mesh, old)
        _, si, sj = meta[i]
        src, dst = mapping_l[si], mapping_l[sj]

        for e in path_edges(old):
            loads[e] -= 1
            if loads[e] <= 0:
                del loads[e]

        # Prefer a strictly shorter path when possible; else any feasible alt
        alt = find_capacity_aware_path(
            mesh,
            src,
            dst,
            min(latency_max, old_d - 1e-6) if old_d > 1e-9 else latency_max,
            loads,
            dist_to[dst],
            manhattan_only=False,
        )
        if alt is None:
            alt = find_capacity_aware_path(
                mesh, src, dst, latency_max, loads, dist_to[dst], manhattan_only=False
            )
        if alt is None or alt == old:
            for e in path_edges(old):
                loads[e] += 1
            paths[i] = old
        else:
            for e in path_edges(alt):
                loads[e] += 1
            paths[i] = alt
            new_score = _route_score(mesh, paths)
            # delta on primary objective (max hop); soften with n_at
            delta = (new_score[0] - score[0]) + 0.01 * (new_score[1] - score[1])
            accept = delta <= 0 or rng.random() < math.exp(-delta / max(T, 1e-9))
            if accept:
                score = new_score
                n_acc += 1
                if new_score < best_score:
                    best_score = new_score
                    best_snap = (
                        [list(p) if p is not None else None for p in paths],
                        dict(loads),
                    )
                    n_imp += 1
                    if verbose and n_imp % 5 == 1:
                        print(
                            f"[SA] step {step}: NEW best max_hop={best_score[0]:g} "
                            f"n_at={best_score[1]}  T={T:.2f}",
                            flush=True,
                        )
            else:
                for e in path_edges(alt):
                    loads[e] -= 1
                    if loads[e] <= 0:
                        del loads[e]
                for e in path_edges(old):
                    loads[e] += 1
                paths[i] = old

        T = max(t_min, T * cool)
        if step % 1000 == 0 and verbose:
            print(
                f"[SA] step {step}/{steps}: cur={score[0]:g}/{score[1]}  "
                f"best={best_score[0]:g}/{best_score[1]}  "
                f"acc={n_acc} imp={n_imp} T={T:.2f}",
                flush=True,
            )

    paths = best_snap[0]
    loads = defaultdict(int, best_snap[1])
    if verbose:
        print(
            f"[SA] done best max_hop={best_score[0]:g} n_at={best_score[1]}  "
            f"accepted={n_acc} improvements={n_imp}",
            flush=True,
        )
    return _rebuild_route_stats(
        mesh,
        mapping_l,
        meta,
        paths,
        dict(loads),
        result.manhattan_top_pct,
    )


def genetic_route_seeds(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    latency_max: float,
    rng: random.Random,
    pop_size: int = 8,
    generations: int = 4,
    max_paths: int = 48,
    manhattan_top_pct: float = 20.0,
    seed_base: int = 1,
    verbose: bool = True,
) -> Tuple[RouteResult, int]:
    """
    Light genetic search over routing RNG seeds: evolve a population of route
    seeds, keep elites by (max_hop, n_at, C), mutate by ±offset.
    """
    def eval_seed(s: int) -> Tuple[Tuple[float, int, int], RouteResult]:
        r = route_under_latency(
            mesh,
            mapping,
            latency_max,
            seed=s,
            max_paths=max_paths,
            manhattan_top_pct=manhattan_top_pct,
        )
        if not r.feasible:
            return ((float("inf"), 10**9, 10**9), r)
        n_at = sum(
            1
            for p in r.paths
            if p is not None and abs(path_delay(mesh, p) - r.max_path_delay) <= 1e-9
        )
        return ((r.max_path_delay, n_at, r.C), r)

    pop = [seed_base + k for k in range(pop_size)]
    scored: List[Tuple[Tuple[float, int, int], int, RouteResult]] = []
    for s in pop:
        key, r = eval_seed(s)
        scored.append((key, s, r))
        if verbose:
            print(f"[GA] init seed={s} key={key}", flush=True)

    scored.sort(key=lambda x: x[0])
    best_key, best_seed, best_r = scored[0]

    for gen in range(1, generations + 1):
        elites = scored[: max(2, pop_size // 2)]
        children: List[int] = []
        while len(children) < pop_size - len(elites):
            p1 = elites[rng.randrange(len(elites))][1]
            p2 = elites[rng.randrange(len(elites))][1]
            child = ((p1 + p2) // 2 + rng.randint(-7, 7)) % 10007
            if child <= 0:
                child = rng.randint(1, 1000)
            children.append(child)
        nxt = [(k, s, r) for k, s, r in elites]
        for s in children:
            key, r = eval_seed(s)
            nxt.append((key, s, r))
            if verbose:
                print(f"[GA] gen {gen} seed={s} key={key}", flush=True)
        nxt.sort(key=lambda x: x[0])
        scored = nxt[:pop_size]
        if scored[0][0] < best_key:
            best_key, best_seed, best_r = scored[0]
            if verbose:
                print(f"[GA] NEW best seed={best_seed} key={best_key}", flush=True)

    if verbose:
        print(f"[GA] keep seed={best_seed} key={best_key}", flush=True)
    return best_r, best_seed


# ---------------------------------------------------------------------------
# Port annotation (3D)
# ---------------------------------------------------------------------------


def face3(a: Coord3, b: Coord3) -> str:
    za, ra, ca = a
    zb, rb, cb = b
    if za != zb:
        return "U" if zb > za else "D"
    if rb != ra:
        return "S" if rb > ra else "N"
    if cb != ca:
        return "E" if cb > ca else "W"
    return "?"


class PortAlloc3:
    def __init__(self) -> None:
        self.next: Dict[Coord3, int] = defaultdict(int)
        self.ch: Dict[Tuple[Coord3, Coord3], int] = defaultdict(int)

    def local(self, p: Coord3) -> int:
        x = self.next[p]
        self.next[p] += 1
        return x

    def d2d(self, u: Coord3, v: Coord3) -> Tuple[int, int, int]:
        c = self.ch[(u, v)]
        self.ch[(u, v)] = c + 1
        ou = self.local(u)
        iv = self.local(v)
        return ou, iv, c


def l1l3_delay_stats(routes: Sequence[dict]) -> dict:
    """
    Clos L1→L2→L3 end-to-end delay stats.

    For every (src, mid, dst), e2e = delay(L1-L2: src→mid) + delay(L2-L3: mid→dst).
    Primary KPI max_path_delay is this e2e max (≈ 2× per-hop max when both
    stages share the same worst hop delay).
    """
    d12: Dict[Tuple[int, int], float] = {}
    d23: Dict[Tuple[int, int], float] = {}
    hop_delays: List[float] = []
    for r in routes:
        d = r.get("path_delay_ns")
        if d is None:
            continue
        hop_delays.append(float(d))
        key = (int(r["src_ssc"]), int(r["dst_ssc"]))
        if r.get("stage") == "L1-L2":
            d12[key] = float(d)
        elif r.get("stage") == "L2-L3":
            d23[key] = float(d)

    max_hop = max(hop_delays) if hop_delays else 0.0
    max12 = max(d12.values()) if d12 else 0.0
    max23 = max(d23.values()) if d23 else 0.0
    hop_hist: Dict[str, int] = defaultdict(int)
    for d in hop_delays:
        hop_hist[str(int(round(d)))] += 1

    sscs = sorted({i for i, _ in d12} | {j for _, j in d12})
    e2e_hist: Dict[str, int] = defaultdict(int)
    max_e2e = -1.0
    n_at = 0
    sum_e2e = 0.0
    n_e2e = 0
    for s in sscs:
        for m in sscs:
            a = d12.get((s, m))
            if a is None:
                continue
            for t in sscs:
                b = d23.get((m, t))
                if b is None:
                    continue
                e = a + b
                e2e_hist[str(int(round(e)))] += 1
                sum_e2e += e
                n_e2e += 1
                if e > max_e2e + 1e-12:
                    max_e2e = e
                    n_at = 1
                elif abs(e - max_e2e) <= 1e-9:
                    n_at += 1

    if max_e2e < 0:
        max_e2e = 0.0

    return {
        "delay_scope": "L1-L3",
        "max_path_delay_ns": max_e2e,
        "n_at_max": n_at,
        "n_e2e_paths": n_e2e,
        "avg_path_delay_ns": (sum_e2e / n_e2e) if n_e2e else 0.0,
        "delay_histogram_ns": dict(sorted(e2e_hist.items(), key=lambda x: int(x[0]))),
        "max_hop_delay_ns": max_hop,
        "max_hop_delay_L1L2_ns": max12,
        "max_hop_delay_L2L3_ns": max23,
        "n_hop_edges": len(hop_delays),
        "hop_delay_histogram_ns": dict(
            sorted(hop_hist.items(), key=lambda x: int(x[0]))
        ),
    }


def annotate_paths_with_mesh(
    mesh: Mesh3D, mapping: Sequence[Coord3], result: RouteResult
) -> List[dict]:
    ports = PortAlloc3()
    dist_to: Dict[Coord3, Dict[Coord3, float]] = {}
    for t in mesh.positions:
        dist_to[t] = dijkstra_delay(mesh, t)[0]
    out = []
    for edge_id, (nodes, (stage, i, j)) in enumerate(zip(result.paths, result.meta)):
        if nodes is None:
            out.append(
                {
                    "edge_id": edge_id,
                    "stage": stage,
                    "src_ssc": i,
                    "dst_ssc": j,
                    "feasible": False,
                    "path": None,
                    "path_delay_ns": None,
                    "path_energy_pj_per_bit": None,
                    "is_manhattan": False,
                }
            )
            continue
        hops = []
        if len(nodes) == 1:
            hops.append(
                {
                    "pos": list(nodes[0]),
                    "role": "local",
                    "in_port": ports.local(nodes[0]),
                    "out_port": ports.local(nodes[0]),
                    "in_face": "LOCAL",
                    "out_face": "LOCAL",
                }
            )
        else:
            d2d = [ports.d2d(a, b) for a, b in zip(nodes, nodes[1:])]
            for hi, p in enumerate(nodes):
                if hi == 0:
                    ou, _, ch = d2d[0]
                    hops.append(
                        {
                            "pos": list(p),
                            "role": "source",
                            "in_port": ports.local(p),
                            "out_port": ou,
                            "in_face": "LOCAL",
                            "out_face": face3(p, nodes[1]),
                            "out_channel": ch,
                        }
                    )
                elif hi == len(nodes) - 1:
                    _, iv, ch = d2d[hi - 1]
                    hops.append(
                        {
                            "pos": list(p),
                            "role": "dest",
                            "in_port": iv,
                            "out_port": ports.local(p),
                            "in_face": face3(p, nodes[hi - 1]),
                            "out_face": "LOCAL",
                            "in_channel": ch,
                        }
                    )
                else:
                    _, iv, chin = d2d[hi - 1]
                    ou, _, chout = d2d[hi]
                    hops.append(
                        {
                            "pos": list(p),
                            "role": "feedthrough",
                            "in_port": iv,
                            "out_port": ou,
                            "in_face": face3(p, nodes[hi - 1]),
                            "out_face": face3(p, nodes[hi + 1]),
                            "in_channel": chin,
                            "out_channel": chout,
                        }
                    )
        delay_ns = path_delay(mesh, nodes)
        energy = path_energy_pj_per_bit(mesh, nodes)
        manhattan = is_delay_manhattan(mesh, nodes, dist_to[nodes[-1]])
        out.append(
            {
                "edge_id": edge_id,
                "stage": stage,
                "src_ssc": i,
                "dst_ssc": j,
                "src_pos": list(mapping[i]),
                "dst_pos": list(mapping[j]),
                "feasible": True,
                "path_delay_ns": delay_ns,
                "path_energy_pj_per_bit": energy,
                "path_power_W": energy_to_power_w(energy),
                "path": [list(p) for p in nodes],
                "hops": hops,
                "is_manhattan": manhattan,
                "opt_delay_ns": dist_to[nodes[-1]].get(nodes[0], delay_ns),
            }
        )
    return out


def format_route3(rec: dict) -> str:
    if not rec.get("feasible"):
        return (
            f"[{rec['edge_id']}] {rec['stage']} SSC{rec['src_ssc']} -> SSC{rec['dst_ssc']} "
            f"INFEASIBLE under latency_max"
        )
    path = " -> ".join(
        ("NOW" if p[0] == 0 else "跳线") + f"({p[1]},{p[2]})" for p in rec["path"]
    )
    lines = [
        f"[{rec['edge_id']}] {rec['stage']} SSC{rec['src_ssc']}{tuple(rec['src_pos'])}"
        f" -> SSC{rec['dst_ssc']}{tuple(rec['dst_pos'])}",
        f"  path: {path}",
        f"  delay={rec['path_delay_ns']:.1f} ns  "
        f"energy={rec['path_energy_pj_per_bit']:.4f} pJ/bit",
    ]
    for h in rec["hops"]:
        zname = "NOW" if h["pos"][0] == 0 else "跳线"
        lines.append(
            f"  {zname}{tuple(h['pos'][1:])} [{h['role']}]: "
            f"in={h['in_face']}#{h['in_port']} out={h['out_face']}#{h['out_port']}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG drawing
# ---------------------------------------------------------------------------


def _color(v: int, cmin: int, cmax: int) -> str:
    t = 0.0 if cmax <= cmin else (v - cmin) / (cmax - cmin)
    if t < 0.5:
        u = t * 2
        r = int(76 + u * (245 - 76))
        g = int(120 + u * (133 - 120))
        b = int(168 + u * (24 - 168))
    else:
        u = (t - 0.5) * 2
        r = int(245 + u * (228 - 245))
        g = int(133 + u * (87 - 133))
        b = int(24 + u * (86 - 24))
    return f"#{r:02x}{g:02x}{b:02x}"


def render_topology_svg(mesh: Mesh3D, out_path: Path, title: str) -> Tuple[int, int]:
    """Draw Layer0 + offset Layer1 + vertical dashed links."""
    cfg = mesh.config
    max_w = max(cfg.row_widths)
    cell = 56
    margin_l, margin_t, margin_r, margin_b = 48, 72, 48, 48
    layer1_dx, layer1_dy = 28, -34  # visual offset for z=1

    def xy0(r: int, c: int) -> Tuple[float, float]:
        return margin_l + c * cell + cell / 2, margin_t + 40 + r * cell + cell / 2

    def xy1(r: int, c: int) -> Tuple[float, float]:
        x, y = xy0(r, c)
        return x + layer1_dx, y + layer1_dy

    width = margin_l + max_w * cell + margin_r + abs(layer1_dx) + 80
    height = margin_t + len(cfg.row_widths) * cell + margin_b + 60

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#f7f5f0"/>',
        f'<text x="{margin_l}" y="28" font-size="15" font-weight="700">{title}</text>',
        f'<text x="{margin_l}" y="48" font-size="11" fill="#555">'
        f"NOW delay={cfg.delay_now_ns:g}ns · 跳线层 delay={cfg.delay_jumper_ns:g}ns · "
        f"vertical={cfg.delay_vertical_ns:g}ns · 跳线 "
        f"{cfg.jumper_topo}: {format_jumper_windows(cfg.resolved_jumper_windows(), topo=cfg.jumper_topo)}</text>",
    ]

    # Layer0 edges
    for a, b in mesh.adj_edges:
        if a[0] == b[0] == 0:
            x1, y1 = xy0(a[1], a[2])
            x2, y2 = xy0(b[1], b[2])
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#c4a574" stroke-width="2.2" stroke-linecap="round"/>'
            )

    # Layer1 edges
    for a, b in mesh.adj_edges:
        if a[0] == b[0] == 1:
            x1, y1 = xy1(a[1], a[2])
            x2, y2 = xy1(b[1], b[2])
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="#5b8def" stroke-width="2.4" stroke-linecap="round"/>'
            )

    # Vertical
    for a, b in mesh.adj_edges:
        if a[0] != b[0]:
            p0 = a if a[0] == 0 else b
            p1 = b if b[0] == 1 else a
            x0, y0 = xy0(p0[1], p0[2])
            x1, y1 = xy1(p1[1], p1[2])
            parts.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                f'stroke="#2a9d8f" stroke-width="1.4" stroke-dasharray="3 3"/>'
            )

    # Layer0 nodes
    jumper_pos_set = set(mesh.layer1_positions)
    for _, r, c in mesh.layer0_positions:
        x, y = xy0(r, c)
        in_win = (1, r, c) in jumper_pos_set
        fill = "#1f2a37" if not in_win else "#243447"
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="{fill}" stroke="#fff" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+3:.1f}" text-anchor="middle" font-size="7" fill="#fff">{r},{c}</text>'
        )

    # Layer1 nodes
    for _, r, c in mesh.layer1_positions:
        x, y = xy1(r, c)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="#3d6fd8" stroke="#fff" stroke-width="1.2"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+3:.1f}" text-anchor="middle" font-size="7" fill="#fff">跳:{r},{c}</text>'
        )

    # Legend
    lx = width - 160
    parts.append(f'<text x="{lx}" y="{margin_t}" font-size="11" font-weight="700">Legend</text>')
    parts.append(f'<line x1="{lx}" y1="{margin_t+18}" x2="{lx+28}" y2="{margin_t+18}" stroke="#c4a574" stroke-width="2.2"/>')
    parts.append(f'<text x="{lx+34}" y="{margin_t+22}" font-size="10">NOW层</text>')
    parts.append(f'<line x1="{lx}" y1="{margin_t+38}" x2="{lx+28}" y2="{margin_t+38}" stroke="#5b8def" stroke-width="2.4"/>')
    parts.append(f'<text x="{lx+34}" y="{margin_t+42}" font-size="10">跳线层</text>')
    parts.append(
        f'<line x1="{lx}" y1="{margin_t+58}" x2="{lx+28}" y2="{margin_t+58}" '
        f'stroke="#2a9d8f" stroke-width="1.4" stroke-dasharray="3 3"/>'
    )
    parts.append(f'<text x="{lx+34}" y="{margin_t+62}" font-size="10">垂直互联</text>')

    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return width, height


def render_layer_loads_svg(
    mesh: Mesh3D,
    loads: Dict[Tuple[Coord3, Coord3], int],
    layer: int,
    out_path: Path,
    title: str,
    subtitle: str,
) -> Tuple[int, int]:
    cfg = mesh.config
    if layer == 0:
        positions = mesh.layer0_positions
        rows = len(cfg.row_widths)
        cols = max(cfg.row_widths)
        edges = [(a, b) for a, b in mesh.adj_edges if a[0] == b[0] == 0]
    else:
        positions = mesh.layer1_positions
        r0, c0, r1, c1 = cfg.jumper_bbox()
        rows = max(0, r1 - r0 + 1)
        cols = max(0, c1 - c0 + 1)
        edges = [(a, b) for a, b in mesh.adj_edges if a[0] == b[0] == 1]

    cell = 78
    margin_l, margin_t, margin_r, margin_b = 56, 88, 200, 56
    width = margin_l + cols * cell + margin_r
    height = margin_t + rows * cell + margin_b

    def xy(r: int, c: int) -> Tuple[float, float]:
        if layer == 0:
            return margin_l + c * cell + cell / 2, margin_t + r * cell + cell / 2
        br0, bc0, _, _ = cfg.jumper_bbox()
        rr = r - br0
        cc = c - bc0
        return margin_l + cc * cell + cell / 2, margin_t + rr * cell + cell / 2

    # directed loads on this layer
    dir_vals = []
    for a, b in edges:
        dir_vals.append(loads.get((a, b), 0))
        dir_vals.append(loads.get((b, a), 0))
    cmax = max(dir_vals) if dir_vals else 0
    cmin = min(dir_vals) if dir_vals else 0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#f7f5f0"/>',
        f'<text x="{margin_l}" y="28" font-size="15" font-weight="700">{title}</text>',
        f'<text x="{margin_l}" y="50" font-size="11" fill="#555">{subtitle}</text>',
    ]

    for a, b in edges:
        f = loads.get((a, b), 0)
        rload = loads.get((b, a), 0)
        hot = max(f, rload)
        x1, y1 = xy(a[1], a[2])
        x2, y2 = xy(b[1], b[2])
        col = _color(hot, cmin, cmax)
        sw = 1.2 + 4.5 * ((hot - cmin) / (cmax - cmin) if cmax > cmin else 0)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>'
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if a[1] == b[1]:  # horizontal
            rv, lv = (f, rload) if a[2] < b[2] else (rload, f)
            parts.append(
                f'<text x="{mx:.1f}" y="{my-8:.1f}" text-anchor="middle" font-size="8" '
                f'font-weight="700" fill="#222">{rv}→</text>'
            )
            parts.append(
                f'<text x="{mx:.1f}" y="{my+11:.1f}" text-anchor="middle" font-size="8" '
                f'font-weight="700" fill="#444">←{lv}</text>'
            )
        else:
            dv, uv = (f, rload) if a[1] < b[1] else (rload, f)
            parts.append(
                f'<text x="{mx+12:.1f}" y="{my+3:.1f}" text-anchor="start" font-size="8" '
                f'font-weight="700" fill="#222">↓{dv}</text>'
            )
            parts.append(
                f'<text x="{mx-12:.1f}" y="{my+3:.1f}" text-anchor="end" font-size="8" '
                f'font-weight="700" fill="#444">↑{uv}</text>'
            )

    for _, r, c in positions:
        x, y = xy(r, c)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="10" fill="#1f2a37" stroke="#fff" stroke-width="1.3"/>'
        )
        label = f"{r},{c}" if layer == 0 else f"跳:{r},{c}"
        parts.append(
            f'<text x="{x:.1f}" y="{y+3.2:.1f}" text-anchor="middle" font-size="7" fill="#fff">{label}</text>'
        )

    lx0 = width - margin_r + 28
    ly0 = margin_t
    parts.append(f'<text x="{lx0}" y="{ly0}" font-size="12" font-weight="700"># links</text>')
    for i, frac in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
        v = int(round(cmin + frac * (cmax - cmin))) if cmax > cmin else cmin
        y = ly0 + 24 + i * 22
        parts.append(
            f'<rect x="{lx0}" y="{y-8}" width="18" height="12" rx="2" fill="{_color(v, cmin, cmax)}"/>'
        )
        parts.append(f'<text x="{lx0+26}" y="{y+2}" font-size="11">{v}</text>')
    parts.append(f'<text x="{lx0}" y="{ly0+160}" font-size="10" fill="#666">max={cmax}</text>')
    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return width, height


def render_vertical_loads_svg(
    mesh: Mesh3D,
    loads: Dict[Tuple[Coord3, Coord3], int],
    out_path: Path,
    title: str,
) -> Tuple[int, int]:
    cfg = mesh.config
    cell = 70
    margin_l, margin_t, margin_r, margin_b = 56, 80, 180, 48
    r0, c0, r1, c1 = cfg.jumper_bbox()
    rows = max(0, r1 - r0 + 1)
    cols = max(0, c1 - c0 + 1)
    width = margin_l + cols * cell + margin_r
    height = margin_t + rows * cell + margin_b

    verts = [(a, b) for a, b in mesh.adj_edges if a[0] != b[0]]
    vals = []
    for a, b in verts:
        p0 = a if a[0] == 0 else b
        p1 = b if b[0] == 1 else a
        vals.append(loads.get((p0, p1), 0))
        vals.append(loads.get((p1, p0), 0))
    cmax = max(vals) if vals else 0
    cmin = min(vals) if vals else 0

    def xy(r: int, c: int) -> Tuple[float, float]:
        rr = r - r0
        cc = c - c0
        return margin_l + cc * cell + cell / 2, margin_t + rr * cell + cell / 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#f7f5f0"/>',
        f'<text x="{margin_l}" y="28" font-size="15" font-weight="700">{title}</text>',
        f'<text x="{margin_l}" y="50" font-size="11" fill="#555">'
        f'↑ NOW→跳线 · ↓ 跳线→NOW · delay={cfg.delay_vertical_ns:g}ns</text>',
    ]
    for a, b in verts:
        p0 = a if a[0] == 0 else b
        p1 = b if b[0] == 1 else a
        up = loads.get((p0, p1), 0)
        down = loads.get((p1, p0), 0)
        hot = max(up, down)
        x, y = xy(p0[1], p0[2])
        col = _color(hot, cmin, cmax)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="16" fill="none" stroke="{col}" stroke-width="3"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y-4:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#222">↑{up}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+10:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#444">↓{down}</text>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+28:.1f}" text-anchor="middle" font-size="8" fill="#666">{p0[1]},{p0[2]}</text>'
        )
    parts.append("</svg>")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return width, height


def render_mesh3d_200g_ports(
    mesh: Mesh3D,
    loads: Dict[Tuple[Coord3, Coord3], int],
    out_stem: Path,
    latency_max: float,
    C: int,
    port_bw_gbps: float = 200.0,
) -> Tuple[int, int]:
    """
    Combined NOW + jumper + vertical diagram; labels = #200G ports per directed edge.
    Writes .svg / .html / .md next to out_stem; caller converts png via svg_to_png.
    """
    cfg = mesh.config
    max_w = max(cfg.row_widths)
    cell = 68
    margin_l, margin_t, margin_r, margin_b = 56, 100, 230, 64
    l1_dx, l1_dy = 34, -40

    def xy0(r: int, c: int) -> Tuple[float, float]:
        return margin_l + c * cell + cell / 2, margin_t + 50 + r * cell + cell / 2

    def xy1(r: int, c: int) -> Tuple[float, float]:
        x, y = xy0(r, c)
        return x + l1_dx, y + l1_dy

    def xy(p: Coord3) -> Tuple[float, float]:
        return xy1(p[1], p[2]) if p[0] == 1 else xy0(p[1], p[2])

    width = int(margin_l + max_w * cell + margin_r + abs(l1_dx) + 40)
    height = int(margin_t + len(cfg.row_widths) * cell + margin_b + 80)

    vals: List[int] = []
    for a, b in mesh.adj_edges:
        vals.append(loads.get((a, b), 0))
        vals.append(loads.get((b, a), 0))
    cmax = max(vals) if vals else 0
    cmin = min(vals) if vals else 0

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#f7f5f0"/>',
        f'<text x="{margin_l}" y="28" font-size="15" font-weight="700">'
        f"NOW + 跳线层 · directed 200G ports · {list(cfg.row_widths)}</text>",
        f'<text x="{margin_l}" y="50" font-size="11" fill="#555">'
        f"Label = #200G ports (= ℓ). C={C} → max BW={C * port_bw_gbps / 1000:.1f} Tbps · "
        f"latency_max={latency_max:g}ns · NOW {cfg.delay_now_ns:g}ns / "
        f"跳线 {cfg.delay_jumper_ns:g}ns / 垂直 {cfg.delay_vertical_ns:g}ns</text>",
        f'<text x="{margin_l}" y="68" font-size="10" fill="#888">'
        f"跳线 {cfg.jumper_topo}: {format_jumper_windows(cfg.resolved_jumper_windows(), topo=cfg.jumper_topo)} · "
        f"NOW(L0) cap {cfg.now_capacity_links}×{port_bw_gbps:g}G · "
        f"jumper(L1) cap {cfg.jumper_capacity_links}×{port_bw_gbps:g}G · "
        f"vertical cap {cfg.vertical_capacity_links}×{port_bw_gbps:g}G</text>",
    ]

    def draw_plane(z: int, fs: float) -> None:
        for a, b in mesh.adj_edges:
            if a[0] != z or b[0] != z:
                continue
            f = loads.get((a, b), 0)
            rload = loads.get((b, a), 0)
            hot = max(f, rload)
            x1, y1 = xy(a)
            x2, y2 = xy(b)
            col = _color(hot, cmin, cmax)
            sw = 1.2 + 3.8 * ((hot - cmin) / (cmax - cmin) if cmax > cmin else 0)
            parts.append(
                f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
                f'stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>'
            )
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            fill = "#222" if z == 0 else "#1a3a7a"
            if a[1] == b[1]:
                right, left = (f, rload) if a[2] < b[2] else (rload, f)
                parts.append(
                    f'<text x="{mx:.1f}" y="{my-8:.1f}" text-anchor="middle" font-size="{fs}" '
                    f'font-weight="700" fill="{fill}">{right}→</text>'
                )
                parts.append(
                    f'<text x="{mx:.1f}" y="{my+10:.1f}" text-anchor="middle" font-size="{fs}" '
                    f'font-weight="700" fill="{fill}">←{left}</text>'
                )
            else:
                down, up = (f, rload) if a[1] < b[1] else (rload, f)
                parts.append(
                    f'<text x="{mx+10:.1f}" y="{my+3:.1f}" text-anchor="start" font-size="{fs}" '
                    f'font-weight="700" fill="{fill}">↓{down}</text>'
                )
                parts.append(
                    f'<text x="{mx-10:.1f}" y="{my+3:.1f}" text-anchor="end" font-size="{fs}" '
                    f'font-weight="700" fill="{fill}">↑{up}</text>'
                )

    draw_plane(0, 7)
    if cfg.enable_jumper:
        draw_plane(1, 6.5)
        for a, b in mesh.adj_edges:
            if a[0] == b[0]:
                continue
            p0 = a if a[0] == 0 else b
            p1 = b if b[0] == 1 else a
            up = loads.get((p0, p1), 0)
            down = loads.get((p1, p0), 0)
            hot = max(up, down)
            x0, y0 = xy(p0)
            x1, y1 = xy(p1)
            parts.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                f'stroke="{_color(hot, cmin, cmax)}" stroke-width="1.5" stroke-dasharray="3 2.5"/>'
            )
            mx, my = (x0 + x1) / 2 + 9, (y0 + y1) / 2
            parts.append(
                f'<text x="{mx:.1f}" y="{my-2:.1f}" text-anchor="start" font-size="6" '
                f'font-weight="700" fill="#0d6b5c">↗{up}</text>'
            )
            parts.append(
                f'<text x="{mx:.1f}" y="{my+8:.1f}" text-anchor="start" font-size="6" '
                f'font-weight="700" fill="#0d6b5c">↙{down}</text>'
            )

    for p in mesh.now_positions:
        x, y = xy(p)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8.5" fill="#1f2a37" stroke="#fff" stroke-width="1.1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+3:.1f}" text-anchor="middle" font-size="6" fill="#fff">{p[1]},{p[2]}</text>'
        )
    for p in mesh.jumper_positions:
        x, y = xy(p)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="7.5" fill="#3d6fd8" stroke="#fff" stroke-width="1.1"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+2.8:.1f}" text-anchor="middle" font-size="5.5" fill="#fff">跳:{p[1]},{p[2]}</text>'
        )

    lx = width - margin_r + 20
    ly = margin_t + 8
    parts.append(f'<text x="{lx}" y="{ly}" font-size="11" font-weight="700">#200G ports</text>')
    for i, frac in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
        v = int(round(cmin + frac * (cmax - cmin))) if cmax > cmin else cmin
        y = ly + 22 + i * 22
        parts.append(
            f'<rect x="{lx}" y="{y-8}" width="18" height="12" rx="2" fill="{_color(v, cmin, cmax)}"/>'
        )
        parts.append(
            f'<text x="{lx+26}" y="{y+2}" font-size="10">{v} ({v * port_bw_gbps / 1000:.1f}T)</text>'
        )
    parts.append(f'<text x="{lx}" y="{ly+150}" font-size="10" fill="#666">max C={C}</text>')
    parts.append(f'<text x="{lx}" y="{ly+168}" font-size="10" fill="#666">NOW / 跳线 / 垂直</text>')
    parts.append("</svg>")

    svg_path = out_stem.with_suffix(".svg")
    svg_path.write_text("\n".join(parts), encoding="utf-8")
    out_stem.with_suffix(".html").write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        "<style>html,body{margin:0;background:#f7f5f0}svg{display:block}</style>"
        f"</head><body>{svg_path.read_text()}</body></html>",
        encoding="utf-8",
    )

    rows = []
    for a, b in mesh.adj_edges:
        for u, v in ((a, b), (b, a)):
            n = loads.get((u, v), 0)
            kind = mesh.edge_kind(u, v)
            rows.append((n, kind, u, v))
    rows.sort(reverse=True)
    md = [
        "# NOW + 跳线层 · directed 200G ports",
        "",
        f"- C={C}; max BW = {C}×{port_bw_gbps:g}G = **{C * port_bw_gbps / 1000:.1f} Tbps**",
        f"- latency_max={latency_max:g} ns; NOW(L0) cap={cfg.now_capacity_links}; "
        f"jumper(L1) cap={cfg.jumper_capacity_links}; "
        f"vertical cap={cfg.vertical_capacity_links}",
        "",
        "| rank | kind | u → v | #200G | BW (Tbps) |",
        "| ---: | --- | --- | ---: | ---: |",
    ]
    for i, (n, kind, u, v) in enumerate(rows, 1):
        if n == 0:
            continue
        md.append(
            f"| {i} | {kind} | `{u}→{v}` | {n} | {n * port_bw_gbps / 1000:.2f} |"
        )
    out_stem.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")
    return width, height


def svg_to_png(svg_path: Path, html_path: Path, png_path: Path, w: int, h: int) -> None:
    html_path.write_text(
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        "<style>html,body{margin:0;background:#f7f5f0}svg{display:block}</style>"
        f"</head><body>{svg_path.read_text()}</body></html>",
        encoding="utf-8",
    )
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome.exists():
        try:
            subprocess.check_call(
                [
                    str(chrome),
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--window-size={w},{h}",
                    f"--screenshot={png_path.resolve()}",
                    html_path.resolve().as_uri(),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if png_path.exists() and png_path.stat().st_size > 0:
                return
        except Exception:
            pass
    # qlmanage fallback (padded square)
    import re

    svg = svg_path.read_text()
    side = max(w, h) + 80
    pad_x, pad_y = 40, (side - h) // 2
    body = re.sub(r"^<svg[^>]*>", "", svg).rsplit("</svg>", 1)[0]
    padded = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" '
        f'viewBox="0 0 {side} {side}"><rect width="100%" height="100%" fill="#f7f5f0"/>'
        f'<g transform="translate({pad_x},{pad_y})">{body}</g></svg>'
    )
    tmp = svg_path.parent / "_pad_export.svg"
    tmp.write_text(padded)
    try:
        subprocess.check_call(
            ["qlmanage", "-t", "-s", "1600", "-o", str(svg_path.parent), str(tmp)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        produced = svg_path.parent / "_pad_export.svg.png"
        if produced.exists():
            produced.replace(png_path)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"warn: PNG export failed for {svg_path.name}: {exc}", flush=True)
    finally:
        tmp.unlink(missing_ok=True)
        (svg_path.parent / "_pad_export.svg.png").unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def binary_search_min_latency_ns(
    mesh: Mesh3D,
    mapping: Sequence[Coord3],
    hi_ns: float,
    seed: int,
    max_paths: int,
    manhattan_top_pct: float = 20.0,
) -> Tuple[float, RouteResult, List[dict]]:
    """
    Binary-search the smallest latency_max (ns) in [0, hi_ns] that admits a
    feasible routing under capacity constraints.
    Returns (best_latency_max_ns, result_at_best, search_log).
    """
    hi = int(round(hi_ns))
    lo = 0
    probe = route_under_latency(
        mesh,
        mapping,
        float(hi),
        seed=seed,
        max_paths=max_paths,
        manhattan_top_pct=manhattan_top_pct,
    )
    log: List[dict] = [
        {
            "latency_max_ns": hi,
            "feasible": probe.feasible,
            "C": probe.C,
            "max_path_delay_ns": probe.max_path_delay,
            "n_infeasible": probe.n_infeasible,
            "n_manhattan": probe.n_manhattan,
            "n_non_manhattan": probe.n_non_manhattan,
            "n_must_manhattan": probe.n_must_manhattan,
            "n_must_manhattan_ok": probe.n_must_manhattan_ok,
        }
    ]
    print(
        f"[binsearch] hi={hi} ns ({hi/1000:.3f} µs): feasible={probe.feasible} "
        f"C={probe.C} max_delay={probe.max_path_delay:.1f}ns inf={probe.n_infeasible} "
        f"manh={probe.n_manhattan}/{probe.n_manhattan + probe.n_non_manhattan} "
        f"must={probe.n_must_manhattan_ok}/{probe.n_must_manhattan}",
        flush=True,
    )
    if not probe.feasible:
        return float(hi), probe, log

    best_L = hi
    best_result = probe

    while lo < hi:
        mid = (lo + hi) // 2
        cur = route_under_latency(
            mesh,
            mapping,
            float(mid),
            seed=seed,
            max_paths=max_paths,
            manhattan_top_pct=manhattan_top_pct,
        )
        log.append(
            {
                "latency_max_ns": mid,
                "feasible": cur.feasible,
                "C": cur.C,
                "max_path_delay_ns": cur.max_path_delay,
                "n_infeasible": cur.n_infeasible,
                "n_manhattan": cur.n_manhattan,
                "n_non_manhattan": cur.n_non_manhattan,
                "n_must_manhattan": cur.n_must_manhattan,
                "n_must_manhattan_ok": cur.n_must_manhattan_ok,
            }
        )
        print(
            f"[binsearch] mid={mid} ns ({mid/1000:.3f} µs): feasible={cur.feasible} "
            f"C={cur.C} max_delay={cur.max_path_delay:.1f}ns inf={cur.n_infeasible} "
            f"manh={cur.n_manhattan}/{cur.n_manhattan + cur.n_non_manhattan} "
            f"must={cur.n_must_manhattan_ok}/{cur.n_must_manhattan}",
            flush=True,
        )
        if cur.feasible:
            best_L = mid
            best_result = cur
            hi = mid
        else:
            lo = mid + 1

    final = route_under_latency(
        mesh,
        mapping,
        float(best_L),
        seed=seed,
        max_paths=max_paths,
        manhattan_top_pct=manhattan_top_pct,
    )
    if final.feasible:
        best_result = final
    return float(best_L), best_result, log


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--latency-max",
        type=float,
        default=None,
        help="fixed max path delay in ns; if omitted, binary-search from --latency-hi-us",
    )
    ap.add_argument(
        "--latency-hi-us",
        type=float,
        default=1000.0,
        help="binary-search upper bound in µs (default: 1000)",
    )
    ap.add_argument(
        "--no-binsearch",
        action="store_true",
        help="disable binary search; require --latency-max",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("results_3d_now_jumper"))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-paths", type=int, default=48)
    ap.add_argument("--pairwise-rounds", type=int, default=0, help="0=identity mapping only")
    ap.add_argument("--pair-samples", type=int, default=40)
    ap.add_argument("--no-jumper", action="store_true", help="baseline: disable 跳线层 (NOW-only)")
    ap.add_argument("--delay-now", type=float, default=80.0)
    ap.add_argument("--delay-jumper", type=float, default=1.0)
    ap.add_argument("--delay-vertical", type=float, default=5.0)
    ap.add_argument(
        "--now-capacity",
        type=int,
        default=350,
        help="max #200G links per NOW (Layer 0) directed edge (default: 350)",
    )
    ap.add_argument(
        "--jumper-capacity",
        type=int,
        default=180,
        help="max #200G links per jumper (Layer 1) directed edge (default: 180)",
    )
    ap.add_argument(
        "--vertical-capacity",
        type=int,
        default=250,
        help="max #200G links per NOW↔jumper directed edge (default: 250)",
    )
    ap.add_argument("--jumper-row-min", type=int, default=2)
    ap.add_argument("--jumper-row-max", type=int, default=5)
    ap.add_argument("--jumper-col-min", type=int, default=2)
    ap.add_argument("--jumper-col-max", type=int, default=7)
    ap.add_argument(
        "--jumper-topo",
        type=str,
        default="single",
        choices=sorted(JUMPER_TOPO_PRESETS.keys()),
        help=(
            "jumper-layer layout preset: "
            "single=(2,2)–(5,7); "
            "dual=two meshes (0,2)–(3,7)+(4,2)–(7,7); "
            "quad=four meshes (0,0)–(3,4)+(0,5)–(3,9)+(4,0)–(7,4)+(4,5)–(7,9); "
            "full=NOW-mirror (same dies/adjacency, smaller jumper capacity)"
        ),
    )
    ap.add_argument(
        "--manhattan-top-pct",
        type=float,
        default=20.0,
        help=(
            "top pct of commodities by opt delay that MUST use Manhattan paths "
            "(default: 20); remaining prefer Manhattan with soft detour"
        ),
    )
    ap.add_argument(
        "--rebalance-hot",
        action="store_true",
        default=True,
        help="after routing, vacate short paths from hot jumper edges and improve longest (default: on)",
    )
    ap.add_argument(
        "--no-rebalance-hot",
        action="store_true",
        help="disable hot-jumper rebalance pass",
    )
    ap.add_argument(
        "--hot-load-frac",
        type=float,
        default=0.8,
        help="jumper edge is hot if load > frac * jumper_capacity (default: 0.8)",
    )
    ap.add_argument(
        "--rebalance-short-ns",
        type=float,
        default=200.0,
        help="vacate paths with delay ≤ this (ns) off hot jumper edges (default: 200)",
    )
    ap.add_argument(
        "--rebalance-rounds",
        type=int,
        default=8,
        help="max rebalance iterations (default: 8)",
    )
    ap.add_argument(
        "--compress-longest",
        action="store_true",
        default=True,
        help="after rebalance, intensify longest-tail compression (default: on)",
    )
    ap.add_argument(
        "--no-compress-longest",
        action="store_true",
        help="disable longest-tail compression pass",
    )
    ap.add_argument(
        "--compress-rounds",
        type=int,
        default=24,
        help="max longest-tail compression rounds (default: 24)",
    )
    ap.add_argument(
        "--compress-band-ns",
        type=float,
        default=40.0,
        help="compress paths within this band of current max delay (default: 40)",
    )
    ap.add_argument(
        "--compress-vacate-ns",
        type=float,
        default=350.0,
        help="during compress, vacate short paths ≤ this delay off longest edges (default: 350)",
    )
    ap.add_argument(
        "--sa-steps",
        type=int,
        default=0,
        help="simulated-annealing path reassignment steps after rebalance (0=off)",
    )
    ap.add_argument(
        "--sa-t0",
        type=float,
        default=80.0,
        help="SA initial temperature (default: 80)",
    )
    ap.add_argument(
        "--ga-generations",
        type=int,
        default=0,
        help="genetic search generations over route seeds before rebalance (0=off)",
    )
    ap.add_argument(
        "--ga-pop",
        type=int,
        default=6,
        help="GA population size (default: 6)",
    )
    ap.add_argument(
        "--tighten-rounds",
        type=int,
        default=0,
        help=(
            "after initial route+rebalance+SA+compress, iteratively lower "
            "latency_max by 1ns and re-polish (0=off); strong for full/quad"
        ),
    )
    ap.add_argument("--print-head", type=int, default=5)
    ap.add_argument("--port-bw-gbps", type=float, default=PORT_BW_GBPS)
    args = ap.parse_args()

    if not (0.0 <= args.manhattan_top_pct <= 100.0):
        raise SystemExit("--manhattan-top-pct must be in [0, 100]")
    if not (0.0 < args.hot_load_frac <= 1.0):
        raise SystemExit("--hot-load-frac must be in (0, 1]")

    cfg = Mesh3DConfig(
        enable_jumper=not args.no_jumper,
        delay_now_ns=args.delay_now,
        delay_jumper_ns=args.delay_jumper,
        delay_vertical_ns=args.delay_vertical,
        now_capacity_links=args.now_capacity,
        jumper_capacity_links=args.jumper_capacity,
        vertical_capacity_links=args.vertical_capacity,
        jumper_topo=("none" if args.no_jumper else args.jumper_topo),
        jumper_row_min=args.jumper_row_min,
        jumper_row_max=args.jumper_row_max,
        jumper_col_min=args.jumper_col_min,
        jumper_col_max=args.jumper_col_max,
    )
    mesh = build_mesh3d(cfg)
    summary = summarize_mesh3d(mesh)
    print("3D mesh:", json.dumps(summary, indent=2))

    mapping: List[Coord3] = list(mesh.now_positions)
    assert len(mapping) == A.CLOS_N_SSC

    rng = random.Random(args.seed)
    search_log: List[dict] = []
    used_binsearch = False

    if args.no_binsearch or args.latency_max is not None:
        if args.latency_max is None:
            raise SystemExit("--no-binsearch requires --latency-max")
        latency_max = float(args.latency_max)
        if args.pairwise_rounds > 0:
            print(
                f"pairwise: rounds={args.pairwise_rounds} samples/round={args.pair_samples}"
            )
            mapping, result = pairwise_exchange_3d(
                mesh,
                mapping,
                latency_max,
                rng,
                max_rounds=args.pairwise_rounds,
                pair_samples=args.pair_samples,
                seed_route=args.seed,
                max_paths=args.max_paths,
                manhattan_top_pct=args.manhattan_top_pct,
            )
        else:
            result = route_under_latency(
                mesh,
                mapping,
                latency_max,
                seed=args.seed,
                max_paths=args.max_paths,
                manhattan_top_pct=args.manhattan_top_pct,
            )
    else:
        used_binsearch = True
        hi_ns = args.latency_hi_us * 1000.0  # µs → ns
        print(
            f"Binary-search minimal feasible latency_max from "
            f"{args.latency_hi_us:g} µs (= {hi_ns:g} ns) downward …"
            f"  manhattan_top_pct={args.manhattan_top_pct:g}%"
        )
        latency_max, result, search_log = binary_search_min_latency_ns(
            mesh,
            mapping,
            hi_ns,
            seed=args.seed,
            max_paths=args.max_paths,
            manhattan_top_pct=args.manhattan_top_pct,
        )
        print(
            f"[binsearch] best latency_max = {latency_max:g} ns "
            f"({latency_max/1000:.3f} µs)"
        )

    if result.feasible and args.ga_generations > 0:
        print(
            f"[GA] generations={args.ga_generations} pop={args.ga_pop} "
            f"at latency_max={latency_max:g}",
            flush=True,
        )
        result, ga_seed = genetic_route_seeds(
            mesh,
            mapping,
            latency_max,
            rng,
            pop_size=args.ga_pop,
            generations=args.ga_generations,
            max_paths=args.max_paths,
            manhattan_top_pct=args.manhattan_top_pct,
            seed_base=args.seed,
            verbose=True,
        )
        print(
            f"[GA] done: seed={ga_seed} max_hop={result.max_path_delay:g} "
            f"C={result.C} feasible={result.feasible}",
            flush=True,
        )

    do_rebalance = args.rebalance_hot and not args.no_rebalance_hot
    if result.feasible and do_rebalance:
        before_max = result.max_path_delay
        before_n = sum(
            1
            for p in result.paths
            if p is not None
            and abs(path_delay(mesh, p) - before_max) <= 1e-9
        )
        result = rebalance_hot_jumper_tail(
            mesh,
            mapping,
            result,
            latency_max=latency_max,
            max_paths=args.max_paths,
            hot_load_frac=args.hot_load_frac,
            short_delay_ns=args.rebalance_short_ns,
            max_rounds=args.rebalance_rounds,
            verbose=True,
        )
        after_n = sum(
            1
            for p in result.paths
            if p is not None
            and abs(path_delay(mesh, p) - result.max_path_delay) <= 1e-9
        )
        print(
            f"[rebalance] done: max_delay {before_max:g}→{result.max_path_delay:g}ns  "
            f"n_at_max {before_n}→{after_n}  C={result.C}  feasible={result.feasible}",
            flush=True,
        )

    if result.feasible and args.sa_steps > 0:
        before_max = result.max_path_delay
        result = simulated_anneal_routes(
            mesh,
            mapping,
            result,
            latency_max=latency_max,
            rng=rng,
            steps=args.sa_steps,
            t0=args.sa_t0,
            verbose=True,
        )
        print(
            f"[SA] done: max_hop {before_max:g}→{result.max_path_delay:g}ns  "
            f"C={result.C} feasible={result.feasible}",
            flush=True,
        )

    do_compress = args.compress_longest and not args.no_compress_longest
    if result.feasible and do_compress:
        before_max = result.max_path_delay
        before_n = sum(
            1
            for p in result.paths
            if p is not None
            and abs(path_delay(mesh, p) - before_max) <= 1e-9
        )
        result = compress_longest_tail(
            mesh,
            mapping,
            result,
            latency_max=latency_max,
            max_rounds=args.compress_rounds,
            band_ns=args.compress_band_ns,
            vacate_short_ns=args.compress_vacate_ns,
            vacate_every=3,
            verbose=True,
        )
        after_n = sum(
            1
            for p in result.paths
            if p is not None
            and abs(path_delay(mesh, p) - result.max_path_delay) <= 1e-9
        )
        print(
            f"[compress] done: max_delay {before_max:g}→{result.max_path_delay:g}ns  "
            f"n_at_max {before_n}→{after_n}  C={result.C}  feasible={result.feasible}",
            flush=True,
        )

    if result.feasible and args.tighten_rounds > 0:
        print(
            f"[tighten] up to {args.tighten_rounds} rounds from "
            f"hop={result.max_path_delay:g}",
            flush=True,
        )
        for tr in range(1, args.tighten_rounds + 1):
            target = result.max_path_delay - 1.0
            if target < 50:
                break
            probe = route_under_latency(
                mesh,
                mapping,
                target,
                seed=args.seed + 31 * tr,
                max_paths=args.max_paths,
                manhattan_top_pct=args.manhattan_top_pct,
            )
            if not probe.feasible:
                # try polishing current under tighter bound
                probe = result
            if do_rebalance:
                probe = rebalance_hot_jumper_tail(
                    mesh,
                    mapping,
                    probe,
                    latency_max=target,
                    max_paths=args.max_paths,
                    hot_load_frac=args.hot_load_frac,
                    short_delay_ns=args.rebalance_short_ns,
                    max_rounds=max(8, args.rebalance_rounds // 2),
                    verbose=False,
                )
            if args.sa_steps > 0:
                probe = simulated_anneal_routes(
                    mesh,
                    mapping,
                    probe,
                    latency_max=target,
                    rng=rng,
                    steps=max(500, args.sa_steps // 2),
                    t0=args.sa_t0,
                    verbose=False,
                )
            if do_compress:
                probe = compress_longest_tail(
                    mesh,
                    mapping,
                    probe,
                    latency_max=target,
                    max_rounds=max(12, args.compress_rounds // 2),
                    band_ns=args.compress_band_ns,
                    vacate_short_ns=args.compress_vacate_ns,
                    vacate_every=2,
                    verbose=False,
                )
            if probe.feasible and probe.max_path_delay < result.max_path_delay - 1e-9:
                print(
                    f"[tighten] round {tr}: {result.max_path_delay:g}→"
                    f"{probe.max_path_delay:g} (lat≤{target:g})",
                    flush=True,
                )
                result = probe
                latency_max = target
            else:
                print(
                    f"[tighten] round {tr}: stop at target={target:g} "
                    f"(cur={result.max_path_delay:g})",
                    flush=True,
                )
                break

    print(
        f"feasible={result.feasible}  C={result.C}  "
        f"latency_max={latency_max:g}ns  "
        f"max_path_delay(route)={result.max_path_delay:.1f}ns  "
        f"infeasible_edges={result.n_infeasible}/{len(result.meta)}"
    )
    print(
        f"manhattan_top_pct = {result.manhattan_top_pct:g}%  "
        f"must_manhattan = {result.n_must_manhattan_ok}/{result.n_must_manhattan}  "
        f"manhattan_paths = {result.n_manhattan}  "
        f"non_manhattan = {result.n_non_manhattan}  "
        f"({100.0 * result.n_manhattan / max(1, result.n_manhattan + result.n_non_manhattan):.1f}% Manhattan)"
    )
    now_loads = [
        v for (a, b), v in result.loads.items() if a[0] == 0 and b[0] == 0
    ]
    jumper_loads = [
        v for (a, b), v in result.loads.items() if a[0] == 1 and b[0] == 1
    ]
    vertical_loads = [
        v for (a, b), v in result.loads.items() if a[0] != b[0]
    ]
    now_max = max(now_loads) if now_loads else 0
    jumper_max = max(jumper_loads) if jumper_loads else 0
    vertical_max = max(vertical_loads) if vertical_loads else 0
    print(
        f"now_max_load = {now_max} / cap {cfg.now_capacity_links} "
        f"({cfg.now_capacity_links * args.port_bw_gbps / 1000:.0f} Tbps)"
    )
    print(
        f"jumper_max_load = {jumper_max} / cap {cfg.jumper_capacity_links} "
        f"({cfg.jumper_capacity_links * args.port_bw_gbps / 1000:.0f} Tbps)"
    )
    print(
        f"vertical_max_load = {vertical_max} / cap {cfg.vertical_capacity_links} "
        f"({cfg.vertical_capacity_links * args.port_bw_gbps / 1000:.0f} Tbps)"
    )

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    routes = annotate_paths_with_mesh(mesh, mapping, result)

    energies = [
        r["path_energy_pj_per_bit"]
        for r in routes
        if r.get("path_energy_pj_per_bit") is not None
    ]
    total_energy = sum(energies)
    total_power_w = energy_to_power_w(total_energy, args.port_bw_gbps)
    avg_energy = total_energy / len(energies) if energies else 0.0

    l1l3 = l1l3_delay_stats(routes)
    max_path_delay = float(l1l3["max_path_delay_ns"])
    max_hop_delay = float(l1l3["max_hop_delay_ns"])

    print(
        f"max_path_delay (L1-L3 e2e) = {max_path_delay:.1f} ns  "
        f"n_at_max={l1l3['n_at_max']}  "
        f"(hop max L1-L2/L2-L3 = {l1l3['max_hop_delay_L1L2_ns']:.1f}/"
        f"{l1l3['max_hop_delay_L2L3_ns']:.1f} ns)"
    )
    print(f"total_path_energy = {total_energy:.4f} pJ/bit  (sum over all logical edges)")
    print(
        f"total_data_movement_power = {total_power_w:.4f} W  "
        f"(P = E × {args.port_bw_gbps:g} Gbps × {POWER_ACCEL_RATIO:g})"
    )
    print(f"avg_path_energy = {avg_energy:.4f} pJ/bit")

    (out / "mapping3d.json").write_text(
        json.dumps(
            {
                "latency_max_ns": latency_max,
                "latency_max_us": latency_max / 1000.0,
                "binary_search": used_binsearch,
                "binary_search_log": search_log,
                "feasible": result.feasible,
                "C": result.C,
                "now_max_load": now_max,
                "now_capacity_links": cfg.now_capacity_links,
                "jumper_max_load": jumper_max,
                "jumper_capacity_links": cfg.jumper_capacity_links,
                "vertical_max_load": vertical_max,
                "vertical_capacity_links": cfg.vertical_capacity_links,
                "delay_scope": "L1-L3",
                "max_path_delay_ns": max_path_delay,
                "n_at_max": l1l3["n_at_max"],
                "avg_path_delay_ns": l1l3["avg_path_delay_ns"],
                "n_e2e_paths": l1l3["n_e2e_paths"],
                "max_hop_delay_ns": max_hop_delay,
                "max_hop_delay_L1L2_ns": l1l3["max_hop_delay_L1L2_ns"],
                "max_hop_delay_L2L3_ns": l1l3["max_hop_delay_L2L3_ns"],
                "total_path_energy_pj_per_bit": total_energy,
                "avg_path_energy_pj_per_bit": avg_energy,
                "total_data_movement_power_W": total_power_w,
                "power_accel_ratio": POWER_ACCEL_RATIO,
                "port_bw_gbps": args.port_bw_gbps,
                "n_infeasible": result.n_infeasible,
                "n_manhattan": result.n_manhattan,
                "n_non_manhattan": result.n_non_manhattan,
                "manhattan_top_pct": result.manhattan_top_pct,
                "n_must_manhattan": result.n_must_manhattan,
                "n_must_manhattan_ok": result.n_must_manhattan_ok,
                "mesh": summary,
                "mapping": [list(p) for p in mapping],
                "seed": args.seed,
                "pairwise_rounds": args.pairwise_rounds,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    loads_ser = {
        f"{a[0]},{a[1]},{a[2]}->{b[0]},{b[1]},{b[2]}": v
        for (a, b), v in result.loads.items()
        if v > 0
    }
    (out / "directed_loads_3d.json").write_text(
        json.dumps({"C": result.C, "loads": loads_ser}, indent=2), encoding="utf-8"
    )

    with (out / "logical_edge_routes.jsonl").open("w", encoding="utf-8") as fj, (
        out / "logical_edge_routes.txt"
    ).open("w", encoding="utf-8") as ft:
        ft.write(
            f"# NOW+跳线层 logical routes\n"
            f"# latency_max={latency_max:g}ns  C={result.C}  feasible={result.feasible}\n"
            f"# NOW(L0)_cap={cfg.now_capacity_links}  jumper(L1)_cap={cfg.jumper_capacity_links}  "
            f"vertical_cap={cfg.vertical_capacity_links}\n"
            f"# now_max_load={now_max}  jumper_max_load={jumper_max}  vertical_max_load={vertical_max}\n"
            f"# max_path_delay(L1-L3 e2e)={max_path_delay:.1f}ns  "
            f"hop_max={max_hop_delay:.1f}ns\n"
            f"# total_energy={total_energy:.4f} pJ/bit (sum)\n"
            f"# total_power={total_power_w:.4f} W (@{args.port_bw_gbps:g}Gbps/link)\n"
            f"# Power model: NOW={cfg.now_edge_power_pj_per_bit:g} pJ/bit/edge; "
            f"vertical={cfg.vertical_power_pj_per_bit:g}; jumper=0\n\n"
        )
        for rec in routes:
            fj.write(json.dumps(rec, ensure_ascii=False) + "\n")
            ft.write(format_route3(rec) + "\n\n")

    (out / "logical_edge_routes_summary.json").write_text(
        json.dumps(
            {
                "n_edges": len(routes),
                "feasible": result.feasible,
                "C": result.C,
                "delay_scope": "L1-L3",
                "max_path_delay_ns": max_path_delay,
                "n_at_max": l1l3["n_at_max"],
                "avg_path_delay_ns": l1l3["avg_path_delay_ns"],
                "n_e2e_paths": l1l3["n_e2e_paths"],
                "max_hop_delay_ns": max_hop_delay,
                "max_hop_delay_L1L2_ns": l1l3["max_hop_delay_L1L2_ns"],
                "max_hop_delay_L2L3_ns": l1l3["max_hop_delay_L2L3_ns"],
                "total_path_energy_pj_per_bit": total_energy,
                "avg_path_energy_pj_per_bit": avg_energy,
                "total_data_movement_power_W": total_power_w,
                "power_accel_ratio": POWER_ACCEL_RATIO,
                "port_bw_gbps": args.port_bw_gbps,
                "delay_histogram_ns": l1l3["delay_histogram_ns"],
                "hop_delay_histogram_ns": l1l3["hop_delay_histogram_ns"],
                "latency_max_ns": latency_max,
                "now_capacity_links": cfg.now_capacity_links,
                "jumper_capacity_links": cfg.jumper_capacity_links,
                "vertical_capacity_links": cfg.vertical_capacity_links,
                "now_max_load": now_max,
                "jumper_max_load": jumper_max,
                "vertical_max_load": vertical_max,
                "n_manhattan": result.n_manhattan,
                "n_non_manhattan": result.n_non_manhattan,
                "manhattan_top_pct": result.manhattan_top_pct,
                "n_must_manhattan": result.n_must_manhattan,
                "n_must_manhattan_ok": result.n_must_manhattan_ok,
                "power_model": summary["power_pj_per_bit"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    tw, th = render_topology_svg(
        mesh,
        out / "topology_3d.svg",
        title=f"NOW + 跳线层 · {list(cfg.row_widths)}",
    )
    svg_to_png(out / "topology_3d.svg", out / "topology_3d.html", out / "topology_3d.png", tw, th)

    w0, h0 = render_layer_loads_svg(
        mesh,
        result.loads,
        0,
        out / "loads_now.svg",
        title=f"NOW层 directed loads · latency_max={latency_max:g}ns",
        subtitle=(
            f"C={result.C} · cap={cfg.now_capacity_links} · max_load={now_max} · "
            f"max_delay={max_path_delay:.1f}ns · "
            f"total_E={total_energy:.1f} pJ/bit · P={total_power_w:.2f}W"
        ),
    )
    svg_to_png(out / "loads_now.svg", out / "loads_now.html", out / "loads_now.png", w0, h0)

    if cfg.enable_jumper:
        w1, h1 = render_layer_loads_svg(
            mesh,
            result.loads,
            1,
            out / "loads_jumper.svg",
            title=f"跳线层 directed loads · latency_max={latency_max:g}ns",
            subtitle=(
                f"C={result.C} · cap={cfg.jumper_capacity_links} · "
                f"max_load={jumper_max} · delay={cfg.delay_jumper_ns:g}ns · power=0"
            ),
        )
        svg_to_png(
            out / "loads_jumper.svg",
            out / "loads_jumper.html",
            out / "loads_jumper.png",
            w1,
            h1,
        )
        wv, hv = render_vertical_loads_svg(
            mesh,
            result.loads,
            out / "loads_vertical.svg",
            title=(
                f"NOW↔跳线 垂直负载 · latency_max={latency_max:g}ns · "
                f"cap={cfg.vertical_capacity_links} max={vertical_max}"
            ),
        )
        svg_to_png(
            out / "loads_vertical.svg",
            out / "loads_vertical.html",
            out / "loads_vertical.png",
            wv,
            hv,
        )

    # Combined 3D directed 200G-port diagram (default output)
    w200, h200 = render_mesh3d_200g_ports(
        mesh,
        result.loads,
        out / "mesh3d_200g_ports",
        latency_max=latency_max,
        C=result.C,
        port_bw_gbps=args.port_bw_gbps,
    )
    svg_to_png(
        out / "mesh3d_200g_ports.svg",
        out / "mesh3d_200g_ports.html",
        out / "mesh3d_200g_ports.png",
        w200,
        h200,
    )

    (out / "README.md").write_text(
        "\n".join(
            [
                f"# NOW + 跳线层结果 (latency_max={latency_max:g} ns)",
                "",
                f"- feasible: **{result.feasible}**",
                f"- C: **{result.C}**",
                f"- binary_search: **{used_binsearch}**",
                f"- NOW(L0) cap / max load: **{cfg.now_capacity_links}** / **{now_max}**",
                f"- jumper(L1) cap / max load: **{cfg.jumper_capacity_links}** / **{jumper_max}**",
                f"- vertical cap / max load: **{cfg.vertical_capacity_links}** / **{vertical_max}**",
                f"- Manhattan top pct (must): **{result.manhattan_top_pct:g}%** "
                f"({result.n_must_manhattan_ok}/{result.n_must_manhattan})",
                f"- Manhattan paths: **{result.n_manhattan}** / non-Manhattan: **{result.n_non_manhattan}**",
                f"- **最长路径时延（L1–L3 端到端）**: **{max_path_delay:.1f} ns**"
                f"（单跳 max={max_hop_delay:.1f} ns）",
                f"- **所有路径总能量**: **{total_energy:.4f} pJ/bit**（逐逻辑边 E 求和）",
                f"- **所有路径总数据搬移功耗**: **{total_power_w:.4f} W**"
                f"（P=E×{args.port_bw_gbps:g} Gbps）",
                "",
                "## 功耗模型",
                f"- NOW边: {cfg.now_power_density_pj_per_bit_mm} pJ/(bit·mm) × {cfg.now_edge_length_mm} mm "
                f"= **{cfg.now_edge_power_pj_per_bit:g} pJ/bit**",
                f"- NOW↔跳线: **{cfg.vertical_power_pj_per_bit:g} pJ/bit**",
                "- 跳线层边: **0**",
                f"- 单路径功耗: `path_power_W = path_energy_pj_per_bit × {args.port_bw_gbps:g} Gbps × {POWER_ACCEL_RATIO:g}`",
                "",
                "## 文件",
                "- `mesh3d_200g_ports.png` — **3D 有向 200G 端口标注总图**（默认）",
                "- `topology_3d.png`",
                "- `loads_now.png` / `loads_jumper.png` / `loads_vertical.png`",
                "- `logical_edge_routes.*` — 每条逻辑边物理路径、时延、能耗、功耗",
                "- `mapping3d.json` / `logical_edge_routes_summary.json`",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"wrote outputs under {out}/")
    print("=== sample routes ===")
    shown = 0
    for rec in routes:
        if rec.get("feasible") and rec.get("path") and len(rec["path"]) >= 2:
            print(format_route3(rec))
            print()
            shown += 1
            if shown >= args.print_head:
                break


if __name__ == "__main__":
    main()
