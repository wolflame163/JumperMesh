#!/usr/bin/env python3
"""
Directed per-link minimum bandwidth demand on a center-symmetric 2D mesh.

Mesh rows: (4, 8, 10, 10, 10, 10, 8, 6)
Traffic model (wafer-scale Clos-like scatter/switch):
  - Each die has line-side IO 64 * 200 Gbps.
  - Any ordered die pair (s, t), s!=t, has:
      uplink-middle logical BW = 200 Gbps
      middle-downlink logical BW = 200 Gbps
    => directed logical demand s->t = 400 Gbps
  - Logical demand is realized on the physical mesh.
  - Routing: split each demand equally over all shortest paths
    (standard load-balanced min-hop routing; placement is irrelevant
     under uniform all-to-all).
  - Report directed physical edge bandwidth = sum of routed demand.

Also emits SVG/PNG-friendly diagram labels in Tbps.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

PORT_GBPS = 200.0
LINE_SIDE_PORTS = 64
UM_GBPS = 200.0  # uplink-middle logical BW per ordered die pair
MD_GBPS = 200.0  # middle-downlink logical BW per ordered die pair
PAIR_DEMAND_GBPS = UM_GBPS + MD_GBPS  # 400

Coord = Tuple[int, int]
DEdge = Tuple[Coord, Coord]  # directed (u -> v)


@dataclass(frozen=True)
class Mesh:
    row_widths: Tuple[int, ...]
    positions: Tuple[Coord, ...]
    undirected_edges: Tuple[Tuple[Coord, Coord], ...]
    neighbors: Dict[Coord, Tuple[Coord, ...]]

    @property
    def n(self) -> int:
        return len(self.positions)


def build_center_symmetric_mesh(row_widths: Sequence[int]) -> Mesh:
    max_w = max(row_widths)
    positions: List[Coord] = []
    for r, w in enumerate(row_widths):
        offset = (max_w - w) // 2
        for c in range(offset, offset + w):
            positions.append((r, c))
    pos_set = set(positions)
    edges = set()
    nbrs: Dict[Coord, List[Coord]] = defaultdict(list)
    for r, c in positions:
        for nr, nc in ((r, c + 1), (r + 1, c)):
            if (nr, nc) in pos_set:
                a, b = (r, c), (nr, nc)
                e = (a, b) if a <= b else (b, a)
                edges.add(e)
                nbrs[a].append(b)
                nbrs[b].append(a)
    return Mesh(
        row_widths=tuple(row_widths),
        positions=tuple(positions),
        undirected_edges=tuple(sorted(edges)),
        neighbors={p: tuple(nbrs[p]) for p in positions},
    )


def all_shortest_path_edge_shares(
    mesh: Mesh, src: Coord, dst: Coord, parents: Dict[Coord, List[Coord]], dist: Dict[Coord, int]
) -> Dict[DEdge, float]:
    """
    Fraction of unit flow on each directed edge when splitting equally
    over all shortest paths src -> dst.
    """
    if src == dst:
        return {}
    if dst not in dist:
        raise RuntimeError(f"no path {src}->{dst}")

    # nodes in increasing distance order
    order = sorted(dist.keys(), key=lambda u: dist[u])
    npaths: Dict[Coord, float] = {src: 1.0}
    for v in order:
        if v == src:
            continue
        npaths[v] = sum(npaths[p] for p in parents[v])

    flow_node: Dict[Coord, float] = defaultdict(float)
    flow_node[dst] = 1.0
    edge_frac: Dict[DEdge, float] = defaultdict(float)
    for u in reversed(order):
        if u == src:
            continue
        fu = flow_node[u]
        if fu <= 0:
            continue
        pars = parents[u]
        wsum = sum(npaths[p] for p in pars)
        for p in pars:
            share = fu * (npaths[p] / wsum)
            edge_frac[(p, u)] += share
            flow_node[p] += share
    return dict(edge_frac)


def bfs_tree(mesh: Mesh, src: Coord) -> Tuple[Dict[Coord, List[Coord]], Dict[Coord, int]]:
    """All shortest-path parents and distances from src."""
    dist: Dict[Coord, int] = {src: 0}
    parents: Dict[Coord, List[Coord]] = {src: []}
    q: deque[Coord] = deque([src])
    while q:
        u = q.popleft()
        for v in mesh.neighbors[u]:
            nd = dist[u] + 1
            if v not in dist:
                dist[v] = nd
                parents[v] = [u]
                q.append(v)
            elif dist[v] == nd:
                parents[v].append(u)
    return parents, dist


def accumulate_directed_loads(mesh: Mesh, pair_demand_gbps: float) -> Dict[DEdge, float]:
    loads: Dict[DEdge, float] = defaultdict(float)
    trees = {s: bfs_tree(mesh, s) for s in mesh.positions}
    for s in mesh.positions:
        parents, dist = trees[s]
        for t in mesh.positions:
            if s == t:
                continue
            shares = all_shortest_path_edge_shares(mesh, s, t, parents, dist)
            for e, frac in shares.items():
                loads[e] += pair_demand_gbps * frac
    return dict(loads)


def directed_edge_list(mesh: Mesh) -> List[DEdge]:
    edges: List[DEdge] = []
    for a, b in mesh.undirected_edges:
        edges.append((a, b))
        edges.append((b, a))
    return edges


def render_svg(
    mesh: Mesh,
    loads: Dict[DEdge, float],
    out_svg: Path,
    out_html: Path,
    *,
    unit: str = "tbps",
    title: str | None = None,
    html_title: str | None = None,
) -> None:
    """
    unit:
      - "tbps": label = Gbps/1000 (Tbps)
      - "ports": label = Gbps/200 (# of 200G ports), rounded up to int
    """
    max_w = max(mesh.row_widths)
    cell = 78
    margin_l, margin_t, margin_r, margin_b = 48, 80, 210, 56
    width = margin_l + max_w * cell + margin_r
    height = margin_t + len(mesh.row_widths) * cell + margin_b

    def xy(r: int, c: int) -> Tuple[float, float]:
        return margin_l + c * cell + cell / 2, margin_t + r * cell + cell / 2

    vals = list(loads.values()) or [0.0]
    c_max = max(vals)
    c_min = min(vals)

    def color(v: float) -> str:
        t = 0.0 if c_max <= c_min else (v - c_min) / (c_max - c_min)
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

    def fmt(v_gbps: float) -> str:
        if unit == "ports":
            return str(int(math.ceil(v_gbps / PORT_GBPS - 1e-12)))
        return f"{v_gbps/1000:.1f}"

    if unit == "ports":
        default_title = f"Directed D2D #200G ports · Mesh {list(mesh.row_widths)}"
        subtitle = (
            f"Each ordered die pair: UM {UM_GBPS:g}G + MD {MD_GBPS:g}G = {PAIR_DEMAND_GBPS:g}G; "
            f"label = ceil(BW / {PORT_GBPS:g}G) directed ports (fwd / rev)"
        )
        legend_title = "# 200G ports"
        legend_fmt = lambda v: str(int(math.ceil(v / PORT_GBPS - 1e-12)))
        html_h1 = "有向链路最小端口数需求（200G）"
        html_p = (
            f"任意有序 die 对：UM+MD={PAIR_DEMAND_GBPS:g}G；全最短路径均分；"
            f"标注为 ceil(带宽/{PORT_GBPS:g}G) 个有向 200G 端口。"
        )
    else:
        default_title = f"Directed D2D demand · Mesh {list(mesh.row_widths)}"
        subtitle = (
            f"Each ordered die pair: UM {UM_GBPS:g}G + MD {MD_GBPS:g}G = {PAIR_DEMAND_GBPS:g}G; "
            f"all-shortest-path equal split; labels = directed Tbps (fwd / rev)"
        )
        legend_title = "dir BW (Tbps)"
        legend_fmt = lambda v: f"{v/1000:.1f}"
        html_h1 = "有向链路最小带宽需求"
        html_p = (
            f"任意有序 die 对：上行-中间 {UM_GBPS:g}G + 中间-下行 {MD_GBPS:g}G；"
            f"全最短路径均分；标注为有向 Tbps。"
        )

    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">'
    )
    parts.append('<rect width="100%" height="100%" fill="#f7f5f0"/>')
    parts.append(
        f'<text x="{margin_l}" y="28" font-size="17" font-weight="700" fill="#1a1a1a">'
        f"{title or default_title}</text>"
    )
    parts.append(
        f'<text x="{margin_l}" y="50" font-size="11" fill="#555">{subtitle}</text>'
    )

    label_fs = "7.5" if unit == "ports" else "8"

    for a, b in mesh.undirected_edges:
        x1, y1 = xy(*a)
        x2, y2 = xy(*b)
        fwd = loads.get((a, b), 0.0)
        rev = loads.get((b, a), 0.0)
        hot = max(fwd, rev)
        col = color(hot)
        sw = 1.2 + 4.0 * ((hot - c_min) / (c_max - c_min) if c_max > c_min else 0)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>'
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if a[0] == b[0]:
            parts.append(
                f'<text x="{mx:.1f}" y="{my - 8:.1f}" text-anchor="middle" '
                f'font-size="{label_fs}" font-weight="700" fill="#222">{fmt(fwd)}→</text>'
            )
            parts.append(
                f'<text x="{mx:.1f}" y="{my + 12:.1f}" text-anchor="middle" '
                f'font-size="{label_fs}" font-weight="700" fill="#444">←{fmt(rev)}</text>'
            )
        else:
            if a[0] < b[0]:
                down_v, up_v = fwd, rev
            else:
                down_v, up_v = rev, fwd
            parts.append(
                f'<text x="{mx + 14:.1f}" y="{my + 3:.1f}" text-anchor="start" '
                f'font-size="{label_fs}" font-weight="700" fill="#222">↓{fmt(down_v)}</text>'
            )
            parts.append(
                f'<text x="{mx - 14:.1f}" y="{my + 3:.1f}" text-anchor="end" '
                f'font-size="{label_fs}" font-weight="700" fill="#444">↑{fmt(up_v)}</text>'
            )

    for r, c in mesh.positions:
        x, y = xy(r, c)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#1f2a37" stroke="#fff" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle" '
            f'font-size="8" fill="#fff">{r},{c}</text>'
        )

    lx0 = width - margin_r + 28
    ly0 = margin_t
    parts.append(
        f'<text x="{lx0}" y="{ly0}" font-size="12" font-weight="700">{legend_title}</text>'
    )
    for i, frac in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
        v = c_min + frac * (c_max - c_min)
        y = ly0 + 24 + i * 22
        parts.append(
            f'<rect x="{lx0}" y="{y-8}" width="18" height="12" rx="2" fill="{color(v)}"/>'
        )
        parts.append(
            f'<text x="{lx0+26}" y="{y+2}" font-size="11" fill="#333">{legend_fmt(v)}</text>'
        )
    parts.append(
        f'<text x="{lx0}" y="{ly0+160}" font-size="10" fill="#666">'
        f"N={mesh.n} dies</text>"
    )
    parts.append(
        f'<text x="{lx0}" y="{ly0+176}" font-size="10" fill="#666">'
        f"line-side {LINE_SIDE_PORTS}×{PORT_GBPS:g}G</text>"
    )
    parts.append("</svg>")
    svg = "\n".join(parts)
    out_svg.write_text(svg, encoding="utf-8")
    out_html.write_text(
        f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"/>
<title>{html_title or html_h1}</title>
<style>body{{margin:24px;background:#eceae4;font-family:IBM Plex Sans,Helvetica,Arial,sans-serif}}
.frame{{background:#fff;padding:12px;border-radius:8px;margin-bottom:24px}}</style></head>
<body><h1>{html_h1}</h1>
<p>{html_p}</p>
<div class="frame">{svg}</div></body></html>""",
        encoding="utf-8",
    )


def main() -> None:
    row_widths = (4, 8, 10, 10, 10, 10, 8, 6)
    mesh = build_center_symmetric_mesh(row_widths)
    print("=== Mesh ===")
    print(f"row_widths = {row_widths}")
    print(f"n_dies = {mesh.n}")
    print(f"undirected edges = {len(mesh.undirected_edges)}")
    print(f"directed edges = {2 * len(mesh.undirected_edges)}")
    print()
    print("=== Traffic model ===")
    print(f"line-side per die = {LINE_SIDE_PORTS} * {PORT_GBPS:g} = {LINE_SIDE_PORTS*PORT_GBPS:g} Gbps")
    print(f"UM logical per ordered pair = {UM_GBPS:g} Gbps")
    print(f"MD logical per ordered pair = {MD_GBPS:g} Gbps")
    print(f"total directed logical demand per ordered pair = {PAIR_DEMAND_GBPS:g} Gbps")
    print(f"ordered pairs = {mesh.n * (mesh.n - 1)}")
    print(
        f"note: line-side / (N-1) = {LINE_SIDE_PORTS*PORT_GBPS/(mesh.n-1):.2f} Gbps "
        f"(≈ {UM_GBPS:g}G scatter to each other die)"
    )
    print()
    print("Routing: equal split over all shortest paths (directed accumulation)")
    loads = accumulate_directed_loads(mesh, PAIR_DEMAND_GBPS)

    dedges = directed_edge_list(mesh)
    rows = []
    for u, v in dedges:
        bw = loads.get((u, v), 0.0)
        rows.append((bw, u, v))
    rows.sort(key=lambda x: (-x[0], x[1], x[2]))

    print()
    print(f"{'rank':>4}  {'u -> v':<28}  {'BW_req (Gbps)':>14}  {'BW_req (Tbps)':>14}")
    print("-" * 70)
    for i, (bw, u, v) in enumerate(rows, 1):
        print(f"{i:4d}  {str(u)+' -> '+str(v):<28}  {bw:14.2f}  {bw/1000:14.3f}")

    print()
    print("=== Summary (directed) ===")
    print(f"max directed link = {rows[0][0]:.2f} Gbps ({rows[0][0]/1000:.3f} Tbps)  {rows[0][1]} -> {rows[0][2]}")
    print(f"min directed link = {rows[-1][0]:.2f} Gbps ({rows[-1][0]/1000:.3f} Tbps)")
    print(f"mean directed link = {sum(r[0] for r in rows)/len(rows):.2f} Gbps")
    # per undirected edge, show both directions
    asym = []
    for a, b in mesh.undirected_edges:
        f, r = loads.get((a, b), 0.0), loads.get((b, a), 0.0)
        if abs(f - r) > 1e-6:
            asym.append((abs(f - r), a, b, f, r))
    print(f"undirected edges with fwd!=rev: {len(asym)} / {len(mesh.undirected_edges)}")

    out = Path(__file__).resolve().parent
    # markdown table
    md = []
    md.append("# Directed per-link minimum bandwidth demand")
    md.append("")
    md.append(f"- Mesh: `{list(row_widths)}` (N={mesh.n})")
    md.append(
        f"- Line-side: {LINE_SIDE_PORTS}×{PORT_GBPS:g}G = {LINE_SIDE_PORTS*PORT_GBPS:g} Gbps/die"
    )
    md.append(
        f"- Logical: any ordered pair UM={UM_GBPS:g}G + MD={MD_GBPS:g}G → {PAIR_DEMAND_GBPS:g}G"
    )
    md.append("- Routing: equal split over all shortest paths; **directed** edge loads")
    md.append("")
    md.append("| rank | u → v | BW_req (Gbps) | BW_req (Tbps) |")
    md.append("| ---: | --- | ---: | ---: |")
    for i, (bw, u, v) in enumerate(rows, 1):
        md.append(f"| {i} | `{u} → {v}` | {bw:.2f} | {bw/1000:.3f} |")
    md.append("")
    md.append("## Per undirected edge (both directions)")
    md.append("")
    md.append("| edge | A→B (Tbps) | B→A (Tbps) | max (Tbps) |")
    md.append("| --- | ---: | ---: | ---: |")
    und_rows = []
    for a, b in mesh.undirected_edges:
        f = loads.get((a, b), 0.0)
        r = loads.get((b, a), 0.0)
        und_rows.append((max(f, r), a, b, f, r))
    und_rows.sort(reverse=True)
    for _, a, b, f, r in und_rows:
        md.append(f"| `{a}-{b}` | {f/1000:.3f} | {r/1000:.3f} | {max(f,r)/1000:.3f} |")
    (out / "directed_link_bandwidth.md").write_text("\n".join(md), encoding="utf-8")

    render_svg(
        mesh,
        loads,
        out / "directed_mesh_bandwidth.svg",
        out / "directed_mesh_bandwidth.html",
    )
    # machine-readable
    serial = {
        "row_widths": list(row_widths),
        "n_dies": mesh.n,
        "pair_demand_gbps": PAIR_DEMAND_GBPS,
        "directed_loads_gbps": {
            f"{u}->{v}": bw for bw, u, v in rows
        },
    }
    (out / "directed_link_bandwidth.json").write_text(
        json.dumps(serial, indent=2), encoding="utf-8"
    )
    print()
    print(f"wrote {out / 'directed_link_bandwidth.md'}")
    print(f"wrote {out / 'directed_mesh_bandwidth.svg'}")
    print(f"wrote {out / 'directed_mesh_bandwidth.html'}")


if __name__ == "__main__":
    main()
