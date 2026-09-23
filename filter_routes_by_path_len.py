#!/usr/bin/env python3
"""
Filter the current optimal Clos→mesh routing by physical path length.

CLI:
  python3 filter_routes_by_path_len.py -n 3

Keeps logical edges whose physical path length (default: #SSC nodes on path)
is strictly greater than n. Floorplan mapping is unchanged; the filtered subset
is written as a new mapping/result package with:
  - directed physical load diagram (svg/png/html/md/json)
  - regenerated logical_edge_routes (txt/jsonl/summary)
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import algorithm1_pairwise_exchange as A
import export_logical_routes as EL

Coord = Tuple[int, int]


def path_length(route: dict, metric: str) -> int:
    nodes = len(route["path_ssc"])
    if metric == "nodes":
        return nodes
    if metric == "hops":
        return max(0, nodes - 1)
    raise ValueError(metric)


def load_routes(path: Path) -> List[dict]:
    routes = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                routes.append(json.loads(line))
    if not routes:
        raise SystemExit(f"no routes in {path}")
    return routes


def ensure_base_routes(routes_path: Path, seed: int, sample_cap: int) -> None:
    if routes_path.is_file():
        return
    print(f"{routes_path} missing — generating via export_logical_routes.py …")
    subprocess.check_call(
        [
            "python3",
            str(Path(__file__).resolve().parent / "export_logical_routes.py"),
            "--seed",
            str(seed),
            "--sample-cap",
            str(sample_cap),
            "--out-dir",
            str(routes_path.parent),
            "--print-head",
            "0",
        ]
    )


def accumulate_loads(
    routes: Sequence[dict],
) -> Dict[Tuple[Coord, Coord], int]:
    loads: Dict[Tuple[Coord, Coord], int] = defaultdict(int)
    for r in routes:
        pos = [tuple(p) for p in r["path_pos"]]
        for a, b in zip(pos, pos[1:]):
            loads[(a, b)] += 1
    return loads


def rebuild_annotated_routes(
    filtered: Sequence[dict],
    mapping: Sequence[Coord],
) -> Tuple[List[EL.LogicalEdgeRoute], EL.PortAllocator, int]:
    inv = EL.pos_to_ssc(mapping)
    ports = EL.PortAllocator(len(mapping))
    out: List[EL.LogicalEdgeRoute] = []
    loads: Dict[Tuple[Coord, Coord], int] = defaultdict(int)

    for new_id, raw in enumerate(filtered):
        nodes = [tuple(p) for p in raw["path_pos"]]
        for a, b in zip(nodes, nodes[1:]):
            loads[(a, b)] += 1
        route = EL.annotate_route(
            new_id,
            raw["stage"],
            raw["src_ssc"],
            raw["dst_ssc"],
            nodes,
            mapping,
            inv,
            ports,
        )
        # Preserve original edge id for traceability.
        out.append(route)

    max_load = max(loads.values()) if loads else 0
    return out, ports, max_load


def color_for(v: int, cmin: int, cmax: int) -> str:
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


def render_directed_diagram(
    mesh: A.Mesh,
    loads: Dict[Tuple[Coord, Coord], int],
    title: str,
    subtitle: str,
    out_stem: Path,
) -> None:
    for a, b in mesh.adj_edges:
        loads.setdefault((a, b), 0)
        loads.setdefault((b, a), 0)

    vals = [loads[e] for a, b in mesh.adj_edges for e in ((a, b), (b, a))]
    cmax = max(vals) if vals else 0
    cmin = min(vals) if vals else 0
    final_mx = cmax

    row_widths = mesh.row_widths
    max_w = max(row_widths)
    cell = 78
    margin_l, margin_t, margin_r, margin_b = 56, 92, 360, 64
    width = margin_l + max_w * cell + margin_r
    height = margin_t + len(row_widths) * cell + margin_b

    def xy(r: int, c: int) -> Tuple[float, float]:
        return margin_l + c * cell + cell / 2, margin_t + r * cell + cell / 2

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#f7f5f0"/>',
        f'<text x="{margin_l}" y="28" font-size="15" font-weight="700">{title}</text>',
        f'<text x="{margin_l}" y="50" font-size="11" fill="#555">{subtitle}</text>',
    ]

    for a, b in mesh.adj_edges:
        f, r = loads[(a, b)], loads[(b, a)]
        hot = max(f, r)
        x1, y1 = xy(*a)
        x2, y2 = xy(*b)
        col = color_for(hot, cmin, cmax)
        sw = 1.2 + 4.5 * ((hot - cmin) / (cmax - cmin) if cmax > cmin else 0)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-width="{sw:.2f}" stroke-linecap="round"/>'
        )
        mx_, my = (x1 + x2) / 2, (y1 + y2) / 2
        if a[0] == b[0]:
            rv, lv = (f, r) if a[1] < b[1] else (r, f)
            parts.append(
                f'<text x="{mx_:.1f}" y="{my-9:.1f}" text-anchor="middle" font-size="8" '
                f'font-weight="700" fill="#222">{rv}→</text>'
            )
            parts.append(
                f'<text x="{mx_:.1f}" y="{my+12:.1f}" text-anchor="middle" font-size="8" '
                f'font-weight="700" fill="#444">←{lv}</text>'
            )
        else:
            dv, uv = (f, r) if a[0] < b[0] else (r, f)
            parts.append(
                f'<text x="{mx_+14:.1f}" y="{my+3:.1f}" text-anchor="start" font-size="8" '
                f'font-weight="700" fill="#222">↓{dv}</text>'
            )
            parts.append(
                f'<text x="{mx_-14:.1f}" y="{my+3:.1f}" text-anchor="end" font-size="8" '
                f'font-weight="700" fill="#444">↑{uv}</text>'
            )

    for r0, c0 in mesh.positions:
        x, y = xy(r0, c0)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#1f2a37" stroke="#fff" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y+3.5:.1f}" text-anchor="middle" font-size="8" fill="#fff">{r0},{c0}</text>'
        )

    lx0 = margin_l + max_w * cell + 48
    ly0 = margin_t + 8
    parts.append(f'<text x="{lx0}" y="{ly0}" font-size="12" font-weight="700"># links</text>')
    for i, frac in enumerate([0, 0.25, 0.5, 0.75, 1.0]):
        v = int(round(cmin + frac * (cmax - cmin))) if cmax > cmin else cmin
        y = ly0 + 24 + i * 22
        parts.append(
            f'<rect x="{lx0}" y="{y-8}" width="18" height="12" rx="2" fill="{color_for(v, cmin, cmax)}"/>'
        )
        parts.append(f'<text x="{lx0+26}" y="{y+2}" font-size="11">{v}</text>')
    parts.append(f'<text x="{lx0}" y="{ly0+160}" font-size="10" fill="#666">max={final_mx}</text>')
    parts.append("</svg>")
    svg_text = "\n".join(parts)

    svg_path = out_stem.with_suffix(".svg")
    svg_path.write_text(svg_text, encoding="utf-8")

    html = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'/>"
        f"<title>{title}</title>"
        "<style>html,body{margin:0;background:#f7f5f0}svg{display:block}</style>"
        f"</head><body>{svg_text}</body></html>"
    )
    html_path = out_stem.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    # Markdown edge table
    rows = sorted(
        (
            (
                max(loads[(a, b)], loads[(b, a)]),
                a,
                b,
                loads[(a, b)],
                loads[(b, a)],
            )
            for a, b in mesh.adj_edges
        ),
        reverse=True,
    )
    md = [
        f"# {title}",
        "",
        f"- {subtitle}",
        f"- max directed load **{final_mx}**",
        "",
        "| rank | A→B | count | B→A | count |",
        "| ---: | --- | ---: | --- | ---: |",
    ]
    for i, (_, a, b, f, r) in enumerate(rows, 1):
        md.append(f"| {i} | `{a}→{b}` | {f} | `{b}→{a}` | {r} |")
    out_stem.with_suffix(".md").write_text("\n".join(md), encoding="utf-8")

    # JSON loads
    loads_path = out_stem.with_name(out_stem.name + "_loads.json")
    loads_path.write_text(
        json.dumps(
            {
                "title": title,
                "subtitle": subtitle,
                "C_directed_max": final_mx,
                "directed_loads": {
                    f"{a[0]},{a[1]}->{b[0]},{b[1]}": v
                    for (a, b), v in loads.items()
                    if v > 0
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # PNG via Chrome headless (landscape) if available
    png_path = out_stem.with_suffix(".png")
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome.exists():
        try:
            subprocess.check_call(
                [
                    str(chrome),
                    "--headless=new",
                    "--disable-gpu",
                    "--hide-scrollbars",
                    f"--window-size={width},{height}",
                    f"--screenshot={png_path.resolve()}",
                    html_path.resolve().as_uri(),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"PNG export skipped: {e}")
    else:
        print("Chrome not found; wrote SVG/HTML only")


def write_route_outputs(
    routes: Sequence[EL.LogicalEdgeRoute],
    ports: EL.PortAllocator,
    mapping: Sequence[Coord],
    out_dir: Path,
    meta: dict,
) -> None:
    txt_path = out_dir / "logical_edge_routes.txt"
    jsonl_path = out_dir / "logical_edge_routes.jsonl"
    summary_path = out_dir / "logical_edge_routes_summary.json"

    with txt_path.open("w", encoding="utf-8") as ft, jsonl_path.open(
        "w", encoding="utf-8"
    ) as fj:
        ft.write(
            "# Filtered logical edges → physical SSC paths + in/out ports\n"
            f"# filter: {meta['filter']}\n"
            f"# kept {meta['n_kept']} / {meta['n_total']} edges; "
            f"C_dir={meta['C_directed_max']}\n\n"
        )
        for r in routes:
            ft.write(EL.format_route(r))
            ft.write("\n\n")
            fj.write(json.dumps(EL.route_to_dict(r), ensure_ascii=False) + "\n")

    summary = {
        **meta,
        "n_logical_edges": len(routes),
        "mapping": [list(p) for p in mapping],
        "ssc_port_counts": [
            {
                "ssc": i,
                "pos": list(mapping[i]),
                "num_logical_ports": ports.next_port[i],
            }
            for i in range(len(mapping))
        ],
        "outputs": {"txt": str(txt_path), "jsonl": str(jsonl_path)},
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {txt_path}")
    print(f"wrote {jsonl_path}")
    print(f"wrote {summary_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Filter optimal routes by physical path length > n, then redraw + re-export."
    )
    ap.add_argument(
        "-n",
        "--n",
        type=int,
        required=True,
        help="keep logical edges with physical path length strictly greater than n",
    )
    ap.add_argument(
        "--metric",
        choices=("nodes", "hops"),
        default="nodes",
        help="path length metric: SSC node count (default) or hop count (edges on path)",
    )
    ap.add_argument(
        "--routes",
        type=Path,
        default=Path("logical_edge_routes.jsonl"),
        help="current optimal routes jsonl (default: ./logical_edge_routes.jsonl)",
    )
    ap.add_argument(
        "--summary",
        type=Path,
        default=Path("logical_edge_routes_summary.json"),
        help="summary json carrying floorplan mapping",
    )
    ap.add_argument("--seed", type=int, default=1, help="used only if routes must be regenerated")
    ap.add_argument("--sample-cap", type=int, default=160)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="output directory (default: filtered_path_gt_<n>_<metric>/)",
    )
    ap.add_argument("--print-head", type=int, default=5)
    args = ap.parse_args()

    if args.n < 0:
        raise SystemExit("-n must be >= 0")

    ensure_base_routes(args.routes, args.seed, args.sample_cap)
    raw_routes = load_routes(args.routes)

    if args.summary.is_file():
        base_summary = json.loads(args.summary.read_text(encoding="utf-8"))
        mapping = [tuple(p) for p in base_summary["mapping"]]
    else:
        mesh0 = A.build_center_symmetric_mesh(A.ROW_WIDTHS)
        mapping = list(mesh0.positions)

    kept = [r for r in raw_routes if path_length(r, args.metric) > args.n]
    dropped = len(raw_routes) - len(kept)

    length_hist = Counter(path_length(r, args.metric) for r in raw_routes)
    print(
        f"filter: {args.metric} > {args.n}  "
        f"kept={len(kept)}  dropped={dropped}  total={len(raw_routes)}"
    )
    print(f"path-length histogram ({args.metric}): {dict(sorted(length_hist.items()))}")

    out_dir = args.out_dir or Path(f"filtered_path_gt_{args.n}_{args.metric}")
    if out_dir.exists():
        # only clear generated artifacts we own; keep dir
        pass
    out_dir.mkdir(parents=True, exist_ok=True)

    mesh = A.build_center_symmetric_mesh(A.ROW_WIDTHS)
    annotated, ports, max_load = rebuild_annotated_routes(kept, mapping)
    loads = accumulate_loads(kept)

    # New mapping/result package
    origin_ids = [r["edge_id"] for r in kept]
    mapping_result = {
        "filter": {
            "metric": args.metric,
            "threshold_n": args.n,
            "predicate": f"{args.metric} > {args.n}",
        },
        "base_routes": str(args.routes),
        "floorplan_mapping": [list(p) for p in mapping],
        "n_ssc": len(mapping),
        "n_total_logical_edges": len(raw_routes),
        "n_kept_logical_edges": len(kept),
        "n_dropped_logical_edges": dropped,
        "C_directed_max": max_load,
        "path_length_histogram_all": {str(k): v for k, v in sorted(length_hist.items())},
        "kept_original_edge_ids": origin_ids,
        "kept_edges": [
            {
                "new_edge_id": i,
                "original_edge_id": r["edge_id"],
                "stage": r["stage"],
                "src_ssc": r["src_ssc"],
                "dst_ssc": r["dst_ssc"],
                "path_ssc": r["path_ssc"],
                "path_pos": r["path_pos"],
                "path_len": path_length(r, args.metric),
            }
            for i, r in enumerate(kept)
        ],
    }
    mapping_path = out_dir / "filtered_mapping.json"
    mapping_path.write_text(json.dumps(mapping_result, indent=2), encoding="utf-8")
    print(f"wrote {mapping_path}")

    meta = {
        "filter": mapping_result["filter"],
        "n_total": len(raw_routes),
        "n_kept": len(kept),
        "n_dropped": dropped,
        "C_directed_max": max_load,
        "row_widths": list(A.ROW_WIDTHS),
        "stages": ["L1-L2", "L2-L3"],
        "n_ssc": len(mapping),
    }
    write_route_outputs(annotated, ports, mapping, out_dir, meta)

    title = (
        f"Filtered mesh · {args.metric}>{args.n} · kept {len(kept)}/{len(raw_routes)} · "
        f"{list(A.ROW_WIDTHS)}"
    )
    subtitle = f"max={max_load}; physical path length metric={args.metric}"
    render_directed_diagram(
        mesh,
        dict(loads),
        title=title,
        subtitle=subtitle,
        out_stem=out_dir / "physical_directed_link_counts",
    )
    print(f"wrote {out_dir / 'physical_directed_link_counts.svg'} (+ html/md/png)")

    # Also copy a short README pointer
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                f"# Filtered mapping: {args.metric} > {args.n}",
                "",
                f"- Base routes: `{args.routes}`",
                f"- Kept **{len(kept)}** / {len(raw_routes)} logical edges",
                f"- Directed max load **{max_load}**",
                "",
                "## Files",
                "- `filtered_mapping.json` — new mapping/result (kept edges + floorplan)",
                "- `logical_edge_routes.*` — regenerated paths + in/out ports",
                "- `physical_directed_link_counts.*` — redrawn directed loads",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print()
    print("=== sample kept routes ===")
    for r in annotated[: args.print_head]:
        print(EL.format_route(r))
        print()


if __name__ == "__main__":
    main()
