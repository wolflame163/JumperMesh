#!/usr/bin/env python3
"""
Export final Clos→mesh routing results.

For every logical Clos edge, emit:
  - physical path as the sequence of SSC nodes (id + mesh position)
  - on each SSC along the path: input / output logical port numbers

Port model (per SSC namespace, integers starting at 0):
  - Source SSC:  in  = LOCAL Clos stage port; out = D2D toward next hop
  - Intermediate: in  = D2D from prev hop;   out = D2D toward next hop
  - Dest SSC:    in  = D2D from prev hop;   out = LOCAL Clos stage port
  - Same-die link (src==dst): single hop with LOCAL in and LOCAL out

D2D ports on opposite ends of a physical adjacency share the same channel
index on that directed face (reported as face + channel, and as SSC-local
port ids).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import algorithm1_pairwise_exchange as A

Coord = Tuple[int, int]
SSC = int

# Face names relative to the SSC's own position.
FACE_NAMES = {
    (0, 1): "E",
    (0, -1): "W",
    (1, 0): "S",
    (-1, 0): "N",
}


def face_between(a: Coord, b: Coord) -> str:
    dr, dc = b[0] - a[0], b[1] - a[1]
    if (dr, dc) not in FACE_NAMES:
        raise ValueError(f"non-adjacent hop {a} -> {b}")
    return FACE_NAMES[(dr, dc)]


@dataclass
class HopRecord:
    ssc: SSC
    pos: Coord
    role: str  # source | feedthrough | dest | local
    in_port: int
    out_port: int
    in_face: str  # LOCAL | N|E|S|W
    out_face: str
    in_channel: Optional[int]  # channel on in_face (None if LOCAL)
    out_channel: Optional[int]


@dataclass
class LogicalEdgeRoute:
    edge_id: int
    stage: str  # L1-L2 | L2-L3
    src_ssc: SSC
    dst_ssc: SSC
    src_pos: Coord
    dst_pos: Coord
    path_ssc: List[SSC]
    path_pos: List[Coord]
    hops: List[HopRecord]


def build_sp_trees(mesh: A.Mesh):
    nbrs = A._neighbor_map(mesh)
    trees = {}
    for src in mesh.positions:
        dist = {src: 0}
        parents: Dict[Coord, List[Coord]] = {src: []}
        q = deque([src])
        while q:
            u = q.popleft()
            for v in sorted(nbrs[u]):
                nd = dist[u] + 1
                if v not in dist:
                    dist[v] = nd
                    parents[v] = [u]
                    q.append(v)
                elif dist[v] == nd:
                    parents[v].append(u)
        order = sorted(dist.keys(), key=lambda u: (dist[u], u))
        npaths = {src: 1}
        for v in order:
            if v == src:
                continue
            parents[v] = sorted(parents[v])
            npaths[v] = sum(npaths[p] for p in parents[v])
        trees[src] = (dist, parents, npaths)
    return trees


def nth_path(trees, src: Coord, dst: Coord, k: int) -> List[Coord]:
    _, parents, npaths = trees[src]
    nodes = [dst]
    cur = dst
    rem = k
    while cur != src:
        for p in parents[cur]:
            np = npaths[p]
            if rem < np:
                nodes.append(p)
                cur = p
                break
            rem -= np
        else:
            raise RuntimeError(f"path decode failed {src}->{dst} k={k}")
    nodes.reverse()
    return nodes


def candidate_paths(trees, src: Coord, dst: Coord, rng: random.Random, sample_cap: int) -> List[List[Coord]]:
    if src == dst:
        return [[src]]
    np = trees[src][2][dst]
    if np <= sample_cap:
        idxs = range(np)
    else:
        step = max(1, np // sample_cap)
        idxs = list(range(0, np, step))[:sample_cap]
        while len(idxs) < min(sample_cap, np):
            r = rng.randrange(np)
            if r not in idxs:
                idxs.append(r)
    return [nth_path(trees, src, dst, k) for k in idxs]


def path_edges(nodes: Sequence[Coord]) -> List[Tuple[Coord, Coord]]:
    return [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]


def route_all(
    mesh: A.Mesh,
    mapping: Sequence[Coord],
    seed: int = 1,
    sample_cap: int = 160,
) -> Tuple[List[List[Coord]], Dict[Tuple[Coord, Coord], int], List[Tuple[str, int, int]]]:
    """
    Unsplittable load-aware greedy over shortest paths.
    Returns (paths, loads, meta) aligned by logical-edge index.
    """
    trees = build_sp_trees(mesh)
    n = len(mapping)
    rng = random.Random(seed)
    loads: Dict[Tuple[Coord, Coord], int] = defaultdict(int)

    # Logical links: L1-L2 then L2-L3, each n×n including i==j.
    commodities: List[Tuple[int, int, int, int]] = []  # (dist, src, dst, link_idx)
    link_idx = 0
    meta: List[Tuple[str, int, int]] = []
    for stage in ("L1-L2", "L2-L3"):
        for i in range(n):
            for j in range(n):
                src, dst = mapping[i], mapping[j]
                d = 0 if src == dst else trees[src][0][dst]
                commodities.append((d, i, j, link_idx))
                meta.append((stage, i, j))
                link_idx += 1

    # Short hops first (matches prior best max≈275).
    commodities.sort(key=lambda x: (x[0], rng.random()))
    paths: List[Optional[List[Coord]]] = [None] * link_idx

    for _, i, j, idx in commodities:
        src, dst = mapping[i], mapping[j]
        cands = candidate_paths(trees, src, dst, rng, sample_cap)
        best = None
        best_sc = None
        for nodes in cands:
            edges = path_edges(nodes)
            vals = [loads[e] for e in edges]
            sc = (max(vals) if vals else 0, sum(vals))
            if best_sc is None or sc < best_sc:
                best_sc = sc
                best = nodes
        assert best is not None
        for e in path_edges(best):
            loads[e] += 1
        paths[idx] = best

    assert all(p is not None for p in paths)
    return [p for p in paths if p is not None], dict(loads), meta


class PortAllocator:
    """Allocate SSC-local logical port ids and per-face D2D channels."""

    def __init__(self, n_ssc: int):
        self.next_port = [0] * n_ssc
        # directed physical adjacency (ssc_u -> ssc_v) -> next channel index
        self.next_channel: Dict[Tuple[SSC, SSC], int] = defaultdict(int)
        # (u, v, channel) -> (out_port_on_u, in_port_on_v)
        self.d2d_ports: Dict[Tuple[SSC, SSC, int], Tuple[int, int]] = {}

    def alloc_local(self, ssc: SSC) -> int:
        p = self.next_port[ssc]
        self.next_port[ssc] += 1
        return p

    def alloc_d2d(self, u: SSC, v: SSC) -> Tuple[int, int, int]:
        """Return (out_port_on_u, in_port_on_v, channel)."""
        ch = self.next_channel[(u, v)]
        self.next_channel[(u, v)] = ch + 1
        out_p = self.next_port[u]
        self.next_port[u] += 1
        in_p = self.next_port[v]
        self.next_port[v] += 1
        self.d2d_ports[(u, v, ch)] = (out_p, in_p)
        return out_p, in_p, ch


def pos_to_ssc(mapping: Sequence[Coord]) -> Dict[Coord, SSC]:
    return {pos: i for i, pos in enumerate(mapping)}


def annotate_route(
    edge_id: int,
    stage: str,
    src: SSC,
    dst: SSC,
    nodes: Sequence[Coord],
    mapping: Sequence[Coord],
    inv: Dict[Coord, SSC],
    ports: PortAllocator,
) -> LogicalEdgeRoute:
    path_ssc = [inv[p] for p in nodes]
    hops: List[HopRecord] = []

    if len(nodes) == 1:
        # Same die: Clos stages communicate locally.
        in_p = ports.alloc_local(src)
        out_p = ports.alloc_local(src)
        hops.append(
            HopRecord(
                ssc=src,
                pos=nodes[0],
                role="local",
                in_port=in_p,
                out_port=out_p,
                in_face="LOCAL",
                out_face="LOCAL",
                in_channel=None,
                out_channel=None,
            )
        )
    else:
        # Pre-allocate D2D channels for each hop edge.
        d2d: List[Tuple[int, int, int]] = []  # out_u, in_v, ch
        for a, b in zip(path_ssc, path_ssc[1:]):
            d2d.append(ports.alloc_d2d(a, b))

        for hi, ssc in enumerate(path_ssc):
            pos = nodes[hi]
            if hi == 0:
                in_p = ports.alloc_local(ssc)
                out_p, _, ch = d2d[0]
                hops.append(
                    HopRecord(
                        ssc=ssc,
                        pos=pos,
                        role="source",
                        in_port=in_p,
                        out_port=out_p,
                        in_face="LOCAL",
                        out_face=face_between(pos, nodes[1]),
                        in_channel=None,
                        out_channel=ch,
                    )
                )
            elif hi == len(path_ssc) - 1:
                _, in_p, ch = d2d[hi - 1]
                out_p = ports.alloc_local(ssc)
                hops.append(
                    HopRecord(
                        ssc=ssc,
                        pos=pos,
                        role="dest",
                        in_port=in_p,
                        out_port=out_p,
                        # Face on *this* SSC where the packet arrives.
                        in_face=face_between(pos, nodes[hi - 1]),
                        out_face="LOCAL",
                        in_channel=ch,
                        out_channel=None,
                    )
                )
            else:
                _, in_p, ch_in = d2d[hi - 1]
                out_p, _, ch_out = d2d[hi]
                hops.append(
                    HopRecord(
                        ssc=ssc,
                        pos=pos,
                        role="feedthrough",
                        in_port=in_p,
                        out_port=out_p,
                        in_face=face_between(pos, nodes[hi - 1]),
                        out_face=face_between(pos, nodes[hi + 1]),
                        in_channel=ch_in,
                        out_channel=ch_out,
                    )
                )

    return LogicalEdgeRoute(
        edge_id=edge_id,
        stage=stage,
        src_ssc=src,
        dst_ssc=dst,
        src_pos=mapping[src],
        dst_pos=mapping[dst],
        path_ssc=path_ssc,
        path_pos=list(nodes),
        hops=hops,
    )


def format_route(route: LogicalEdgeRoute) -> str:
    path_str = " -> ".join(
        f"SSC{s}{tuple(p)}" for s, p in zip(route.path_ssc, route.path_pos)
    )
    lines = [
        f"[{route.edge_id}] {route.stage}  SSC{route.src_ssc}{tuple(route.src_pos)}"
        f" -> SSC{route.dst_ssc}{tuple(route.dst_pos)}",
        f"  path: {path_str}",
    ]
    for h in route.hops:
        in_desc = (
            f"LOCAL#{h.in_port}"
            if h.in_face == "LOCAL"
            else f"{h.in_face}:{h.in_channel}(port {h.in_port})"
        )
        out_desc = (
            f"LOCAL#{h.out_port}"
            if h.out_face == "LOCAL"
            else f"{h.out_face}:{h.out_channel}(port {h.out_port})"
        )
        lines.append(
            f"  SSC{h.ssc}{tuple(h.pos)} [{h.role}]: in={in_desc}  out={out_desc}"
        )
    return "\n".join(lines)


def route_to_dict(route: LogicalEdgeRoute) -> dict:
    d = asdict(route)
    # tuples -> lists for JSON
    d["src_pos"] = list(route.src_pos)
    d["dst_pos"] = list(route.dst_pos)
    d["path_pos"] = [list(p) for p in route.path_pos]
    for h in d["hops"]:
        h["pos"] = list(h["pos"])
    return d


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--sample-cap", type=int, default=160)
    ap.add_argument("--print-head", type=int, default=12, help="print first N edges")
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    args = ap.parse_args()

    mesh = A.build_center_symmetric_mesh(A.ROW_WIDTHS)
    # Identity floorplan: SSC i at mesh.positions[i] (co-located Clos stages).
    mapping: List[Coord] = list(mesh.positions)
    inv = pos_to_ssc(mapping)

    print(
        f"Mesh {list(A.ROW_WIDTHS)}  N={mesh.n}  "
        f"logical edges={2 * mesh.n * mesh.n}  "
        f"routing seed={args.seed}"
    )

    paths, loads, meta = route_all(mesh, mapping, seed=args.seed, sample_cap=args.sample_cap)
    max_load = max(loads.values()) if loads else 0
    print(f"Directed physical max load C_dir={max_load}")

    ports = PortAllocator(mesh.n)
    routes: List[LogicalEdgeRoute] = []
    for edge_id, (nodes, (stage, src, dst)) in enumerate(zip(paths, meta)):
        routes.append(
            annotate_route(edge_id, stage, src, dst, nodes, mapping, inv, ports)
        )

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    txt_path = out_dir / "logical_edge_routes.txt"
    jsonl_path = out_dir / "logical_edge_routes.jsonl"
    summary_path = out_dir / "logical_edge_routes_summary.json"

    with txt_path.open("w", encoding="utf-8") as ft, jsonl_path.open(
        "w", encoding="utf-8"
    ) as fj:
        ft.write(
            "# Clos [66,66,66] logical edges → physical SSC paths + in/out ports\n"
            f"# identity mapping; unsplittable SP; seed={args.seed}; "
            f"C_dir={max_load}\n"
            "# Port: LOCAL#k = Clos endpoint on this SSC; "
            "F:ch(port p) = face F channel ch, SSC-local port id p\n\n"
        )
        for r in routes:
            ft.write(format_route(r))
            ft.write("\n\n")
            fj.write(json.dumps(route_to_dict(r), ensure_ascii=False) + "\n")

    # Per-SSC port usage summary
    ssc_ports = [
        {"ssc": i, "pos": list(mapping[i]), "num_logical_ports": ports.next_port[i]}
        for i in range(mesh.n)
    ]
    summary = {
        "n_ssc": mesh.n,
        "n_logical_edges": len(routes),
        "stages": ["L1-L2", "L2-L3"],
        "row_widths": list(A.ROW_WIDTHS),
        "mapping": [list(p) for p in mapping],
        "C_directed_max": max_load,
        "routing": {
            "type": "unsplittable_shortest_path_load_aware_greedy",
            "seed": args.seed,
            "sample_cap": args.sample_cap,
        },
        "port_model": {
            "ssc_local_ids": "0..P-1 per SSC",
            "LOCAL": "Clos stage attach on this die",
            "face_channel": "N/E/S/W channel index on that D2D face",
        },
        "ssc_port_counts": ssc_ports,
        "outputs": {
            "txt": str(txt_path),
            "jsonl": str(jsonl_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {txt_path}  ({len(routes)} edges)")
    print(f"wrote {jsonl_path}")
    print(f"wrote {summary_path}")
    print()
    print("=== sample ===")
    for r in routes[: args.print_head]:
        print(format_route(r))
        print()

    # One multi-hop example for clarity
    for r in routes:
        if len(r.path_ssc) >= 4:
            print("=== multi-hop example ===")
            print(format_route(r))
            break


if __name__ == "__main__":
    main()
