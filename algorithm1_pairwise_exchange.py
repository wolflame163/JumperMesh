#!/usr/bin/env python3
"""
Reproduce Algorithm 1 (Pairwise Exchange) from
  "Waferscale Network Switches" (waferscale switching paper in this repo)

3-stage Clos [66,66,66]: every die is an SSC present in all three stages.
  - any SSC (L1) ↔ any SSC (L2): logical BW 200 Gbps
  - any SSC (L2) ↔ any SSC (L3): logical BW 200 Gbps
Logical links route on the center-symmetric mesh; C(M) = max edge load.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PORT_BW_GBPS = 200.0
DIE_AREA_MM2 = 800.0  # TH-5-like SSC in the paper
INTERNAL_BW_DENSITY_GBPS_PER_MM = 3200.0  # Si-IF-like baseline in the paper

# Clos scale: every die on the wafer is an SSC (no dedicated I/O-only chiplets).
# Mesh row_widths (4,8,10,10,10,10,8,6) ⇒ N = 66 = |R| = Clos SSC count.
CLOS_N_SSC = 66
ROW_WIDTHS = (4, 8, 10, 10, 10, 10, 8, 6)
assert sum(ROW_WIDTHS) == CLOS_N_SSC

Coord = Tuple[int, int]


@dataclass(frozen=True)
class Mesh:
    row_widths: Tuple[int, ...]
    positions: Tuple[Coord, ...]
    adj_edges: Tuple[Tuple[Coord, Coord], ...]

    @property
    def n(self) -> int:
        return len(self.positions)


def build_center_symmetric_mesh(row_widths: Sequence[int]) -> Mesh:
    """Center-align each row on a shared column grid; 4-neighbor connectivity."""
    max_w = max(row_widths)
    positions: List[Coord] = []
    for r, w in enumerate(row_widths):
        offset = (max_w - w) // 2
        for c in range(offset, offset + w):
            positions.append((r, c))

    pos_set = set(positions)
    edges = set()
    for r, c in positions:
        for nr, nc in ((r, c + 1), (r + 1, c)):
            if (nr, nc) in pos_set:
                a, b = (r, c), (nr, nc)
                edges.add((a, b) if a <= b else (b, a))

    return Mesh(
        row_widths=tuple(row_widths),
        positions=tuple(positions),
        adj_edges=tuple(sorted(edges)),
    )


def build_three_stage_clos(
    n_nodes: int,
) -> Tuple[List[Tuple[int, int]], List[int]]:
    """
    3-stage Clos with stage sizes [n, n, n] (current: [66, 66, 66]).

    Physical die count = n. Every die is an SSC, and every SSC appears in
    all three logical stages (co-located): stage-k node i lives on the same
    SSC id i (mapped to one mesh position by M).

    Logical bandwidth:
      - any SSC i (stage-1) ↔ any SSC j (stage-2): 200 Gbps
      - any SSC i (stage-2) ↔ any SSC j (stage-3): 200 Gbps
    Realized as two full n×n logical link sets; each link routes on the mesh
    from M(i) to M(j) (i==j is local / no mesh load).
    """
    if n_nodes != CLOS_N_SSC:
        raise ValueError(
            f"Clos SSC count must be {CLOS_N_SSC}, got {n_nodes}"
        )
    sizes = [n_nodes, n_nodes, n_nodes]
    # (u, v) means logical endpoint SSC ids; stage1→stage2 and stage2→stage3.
    links: List[Tuple[int, int]] = []
    links.extend(itertools.product(range(n_nodes), range(n_nodes)))  # L1-L2
    links.extend(itertools.product(range(n_nodes), range(n_nodes)))  # L2-L3
    return links, sizes


def _neighbor_map(mesh: Mesh) -> Dict[Coord, List[Coord]]:
    nbrs: Dict[Coord, List[Coord]] = defaultdict(list)
    for a, b in mesh.adj_edges:
        nbrs[a].append(b)
        nbrs[b].append(a)
    return nbrs


def _all_parents(mesh: Mesh) -> Dict[Coord, Dict[Coord, Optional[Coord]]]:
    """BFS parent table from every position (N=66, cheap)."""
    nbrs = _neighbor_map(mesh)
    parents: Dict[Coord, Dict[Coord, Optional[Coord]]] = {}
    for src in mesh.positions:
        prev: Dict[Coord, Optional[Coord]] = {src: None}
        q = [src]
        for cur in q:
            for nxt in nbrs[cur]:
                if nxt not in prev:
                    prev[nxt] = cur
                    q.append(nxt)
        parents[src] = prev
    return parents


def edge_loads(
    mapping: Sequence[Coord],
    logical_links: Sequence[Tuple[int, int]],
    parents: Dict[Coord, Dict[Coord, Optional[Coord]]],
) -> Dict[Tuple[Coord, Coord], int]:
    """Route each logical link on shortest mesh paths; count edge usage."""
    loads: Dict[Tuple[Coord, Coord], int] = defaultdict(int)
    for u, v in logical_links:
        src, dst = mapping[u], mapping[v]
        if src == dst:
            continue
        prev = parents[src]
        cur = dst
        while prev[cur] is not None:
            p = prev[cur]
            assert p is not None
            a, b = (p, cur) if p <= cur else (cur, p)
            loads[(a, b)] += 1
            cur = p
    return loads


def compute_C(
    mapping: Sequence[Coord],
    logical_links: Sequence[Tuple[int, int]],
    parents: Dict[Coord, Dict[Coord, Optional[Coord]]],
) -> int:
    loads = edge_loads(mapping, logical_links, parents)
    return max(loads.values()) if loads else 0


def pairwise_exchange(
    logical_links: Sequence[Tuple[int, int]],
    initial_mapping: Sequence[Coord],
    rng: random.Random,
    parents: Dict[Coord, Dict[Coord, Optional[Coord]]],
    max_rounds: int = 200,
) -> Tuple[List[Coord], int, List[int]]:
    """
    Algorithm 1 — Pairwise Exchange.

    For every SSC pair, try a position swap; keep it iff C decreases.
    Repeat full passes until a pass makes no improvement.
    """
    mapping = list(initial_mapping)
    c_prev = compute_C(mapping, logical_links, parents)
    history = [c_prev]
    n = len(mapping)

    for _ in range(max_rounds):
        improved = False
        pairs = list(itertools.combinations(range(n), 2))
        rng.shuffle(pairs)
        for i, j in pairs:
            mapping[i], mapping[j] = mapping[j], mapping[i]
            c_new = compute_C(mapping, logical_links, parents)
            if c_new < c_prev:
                c_prev = c_new
                improved = True
                history.append(c_prev)
            else:
                mapping[i], mapping[j] = mapping[j], mapping[i]
        if not improved:
            break
    return mapping, c_prev, history


def available_d2d_bw_gbps(
    die_area_mm2: float = DIE_AREA_MM2,
    density: float = INTERNAL_BW_DENSITY_GBPS_PER_MM,
) -> float:
    """Per adjacent-die edge capacity from paper density * square-die side."""
    return (die_area_mm2**0.5) * density


def summarize_mesh(mesh: Mesh) -> dict:
    degrees: Dict[Coord, int] = defaultdict(int)
    for a, b in mesh.adj_edges:
        degrees[a] += 1
        degrees[b] += 1
    # Center horizontal cut between the two middle width-10 rows (indices 3 and 4).
    cut = sum(1 for a, b in mesh.adj_edges if {a[0], b[0]} == {3, 4})
    return {
        "n_dies": mesh.n,
        "n_edges": len(mesh.adj_edges),
        "degree_min": min(degrees.values()),
        "degree_max": max(degrees.values()),
        "center_row_cut_edges": cut,
    }


def structured_clos_mapping(mesh: Mesh, stage_sizes: Sequence[int]) -> List[Coord]:
    """
    Identity-like seed for [n,n,n] Clos: SSC i sits at positions[i].

    (With co-located stages, stage roles share the same SSC id / die.)
    """
    del stage_sizes  # all stages size n; placement is over the n SSCs only
    return list(mesh.positions)


def run_trials(
    mesh: Mesh,
    logical_links: Sequence[Tuple[int, int]],
    stage_sizes: Sequence[int],
    trials: int,
    seed: int,
    top_k: int = 10,
) -> dict:
    """
    Run `trials` random pairwise-exchange searches from `seed`.
    Keep the top_k best solutions (lowest C; ties keep earlier).
    """
    parents = _all_parents(mesh)
    init_cs: List[int] = []
    # heap of (-C, trial_id, mapping, history) — use list + sort for clarity
    solutions: List[dict] = []

    for t in range(trials):
        rng = random.Random(seed + t)
        if t == 0:
            mapping0 = structured_clos_mapping(mesh, stage_sizes)
        else:
            mapping0 = list(mesh.positions)
            rng.shuffle(mapping0)
        c0 = compute_C(mapping0, logical_links, parents)
        init_cs.append(c0)
        mapping, c, hist = pairwise_exchange(
            logical_links, mapping0, rng, parents
        )
        solutions.append(
            {
                "trial": t,
                "C": c,
                "init_C": c0,
                "mapping": mapping,
                "history": hist,
            }
        )
        if (t + 1) % 20 == 0 or t == 0:
            best_so_far = min(s["C"] for s in solutions)
            print(
                f"  [seed={seed}] trial {t+1}/{trials}  "
                f"last_C={c}  best_so_far={best_so_far}",
                flush=True,
            )

    solutions.sort(key=lambda s: (s["C"], s["trial"]))
    # unique by C first, then fill to top_k with next-best distinct mappings
    top: List[dict] = []
    seen_c = set()
    for s in solutions:
        if s["C"] not in seen_c:
            top.append(s)
            seen_c.add(s["C"])
        if len(top) >= top_k:
            break
    # if fewer than top_k distinct C values, pad with next-best trials
    if len(top) < top_k:
        for s in solutions:
            if s in top:
                continue
            top.append(s)
            if len(top) >= top_k:
                break

    best = top[0]
    loads = edge_loads(best["mapping"], logical_links, parents)
    return {
        "best_C": best["C"],
        "best_mapping": best["mapping"],
        "history": best["history"],
        "init_C_mean": sum(init_cs) / len(init_cs),
        "init_C_min": min(init_cs),
        "init_C_max": max(init_cs),
        "structured_seed_C": init_cs[0],
        "edge_loads": dict(loads),
        "required_d2d_bw_gbps": best["C"] * PORT_BW_GBPS,
        "top_solutions": top,
        "seed": seed,
        "trials": trials,
    }


def _run_one(args: Tuple) -> dict:
    mesh, links, stage_sizes, trials, seed, top_k = args
    return run_trials(mesh, links, stage_sizes, trials, seed, top_k=top_k)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trials",
        type=int,
        default=200,
        help="random initial mappings per run (default: 200)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=10,
        help="independent runs with different seeds (default: 10)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="keep top-k solutions per run (prefer distinct C)",
    )
    parser.add_argument("--seed", type=int, default=42, help="base seed")
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="parallel workers for runs (0=min(runs, cpu_count))",
    )
    args = parser.parse_args()

    row_widths = ROW_WIDTHS
    mesh = build_center_symmetric_mesh(row_widths)
    assert mesh.n == CLOS_N_SSC, f"mesh dies {mesh.n} != Clos SSC scale {CLOS_N_SSC}"
    links, stage_sizes = build_three_stage_clos(mesh.n)
    assert stage_sizes == [CLOS_N_SSC, CLOS_N_SSC, CLOS_N_SSC]
    assert len(links) == 2 * CLOS_N_SSC * CLOS_N_SSC
    mesh_info = summarize_mesh(mesh)

    print("=== Mesh ===")
    print(f"row_widths = {row_widths}")
    for k, v in mesh_info.items():
        print(f"  {k}: {v}")

    print("\n=== Clos logical topology ===")
    print(f"  Clos stages = {stage_sizes}  (every die is an SSC in every stage)")
    print(f"  physical SSCs |R| = {CLOS_N_SSC}")
    print(f"  L1-L2: any SSC↔any SSC @ {PORT_BW_GBPS:g}G  ({CLOS_N_SSC}×{CLOS_N_SSC})")
    print(f"  L2-L3: any SSC↔any SSC @ {PORT_BW_GBPS:g}G  ({CLOS_N_SSC}×{CLOS_N_SSC})")
    print(f"  logical links: {len(links)}  (incl. {CLOS_N_SSC*2} self/local)")
    print(
        "  note: with co-located stages, C(M) is invariant to placement "
        "(uniform all-pairs demand)"
    )

    print("\n=== Algorithm 1 (pairwise exchange) ===")
    print(f"  trials/run = {args.trials}")
    print(f"  runs = {args.runs}")
    print(f"  top-k per run = {args.top_k}")
    print(f"  base seed = {args.seed}")

    run_seeds = [args.seed + 1000 * r for r in range(args.runs)]
    jobs = [
        (mesh, links, stage_sizes, args.trials, s, args.top_k) for s in run_seeds
    ]

    workers = args.workers or min(args.runs, os.cpu_count() or 1)
    print(f"  workers = {workers}")
    print(flush=True)

    if workers == 1 or args.runs == 1:
        run_results = [_run_one(j) for j in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            run_results = list(pool.map(_run_one, jobs))

    print("\n=== Per-run optima ===")
    print(f"{'run':>4}  {'seed':>8}  {'best_C':>8}  {'init_mean':>10}  {'D2D_Tbps':>10}")
    print("-" * 50)
    for i, res in enumerate(run_results):
        print(
            f"{i:4d}  {res['seed']:8d}  {res['best_C']:8d}  "
            f"{res['init_C_mean']:10.2f}  {res['best_C']*PORT_BW_GBPS/1000:10.2f}"
        )

    # Global ranking: collect top solutions across runs
    global_top: List[dict] = []
    for res in run_results:
        for s in res["top_solutions"]:
            global_top.append({**s, "run_seed": res["seed"]})
    global_top.sort(key=lambda s: (s["C"], s["run_seed"], s["trial"]))

    # 10 distinct-C optima if possible
    distinct: List[dict] = []
    seen = set()
    for s in global_top:
        if s["C"] in seen:
            continue
        seen.add(s["C"])
        distinct.append(s)
        if len(distinct) >= 10:
            break
    if len(distinct) < 10:
        for s in global_top:
            if s in distinct:
                continue
            distinct.append(s)
            if len(distinct) >= 10:
                break

    print("\n=== Top-10 optima (prefer distinct C) ===")
    print(f"{'rank':>4}  {'C':>6}  {'D2D_Tbps':>10}  {'run_seed':>8}  {'trial':>6}  history")
    print("-" * 80)
    for i, s in enumerate(distinct, 1):
        print(
            f"{i:4d}  {s['C']:6d}  {s['C']*PORT_BW_GBPS/1000:10.2f}  "
            f"{s['run_seed']:8d}  {s['trial']:6d}  {s['history']}"
        )

    overall = min(run_results, key=lambda r: r["best_C"])
    print("\n=== Overall best ===")
    print(f"  best C(M) = {overall['best_C']}")
    print(f"  required hottest-edge D2D = {overall['best_C']*PORT_BW_GBPS:g} Gbps "
          f"({overall['best_C']*PORT_BW_GBPS/1000:g} Tbps)")
    print(f"  from seed={overall['seed']}")

    out = Path(__file__).resolve().parent
    summary = {
        "row_widths": list(row_widths),
        "trials_per_run": args.trials,
        "runs": args.runs,
        "run_seeds": run_seeds,
        "per_run_best_C": [r["best_C"] for r in run_results],
        "top10": [
            {
                "rank": i,
                "C": s["C"],
                "D2D_Tbps": s["C"] * PORT_BW_GBPS / 1000,
                "run_seed": s["run_seed"],
                "trial": s["trial"],
                "history": s["history"],
            }
            for i, s in enumerate(distinct, 1)
        ],
        "overall_best_C": overall["best_C"],
    }
    out_path = out / "algorithm1_top10.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()