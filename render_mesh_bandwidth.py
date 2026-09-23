#!/usr/bin/env python3
"""
Render the center-symmetric 2D mesh with per-link BW demand labels.

Produces:
  - mesh_bandwidth.svg  (vector diagram)
  - mesh_bandwidth.html (same SVG embedded for browser viewing)
"""

from __future__ import annotations

import re
from pathlib import Path

from algorithm1_pairwise_exchange import (
    PORT_BW_GBPS,
    build_center_symmetric_mesh,
)


def color_for_load(c: int, c_max: int) -> str:
    """Blue (cool) -> red (hot) based on C."""
    if c_max <= 0:
        t = 0.0
    else:
        t = c / c_max
    # interpolate #4C78A8 -> #F58518 -> #E45756
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


def load_edge_demands_from_md(md_path: Path) -> dict[tuple[tuple[int, int], tuple[int, int]], int]:
    """Parse C values from per_link_bandwidth.md produced earlier."""
    text = md_path.read_text(encoding="utf-8")
    loads: dict[tuple[tuple[int, int], tuple[int, int]], int] = {}
    pat = re.compile(
        r"\|\s*\d+\s*\|\s*`\((\d+),\s*(\d+)\)-\((\d+),\s*(\d+)\)`\s*\|\s*(\d+)\s*\|"
    )
    for m in pat.finditer(text):
        a = (int(m.group(1)), int(m.group(2)))
        b = (int(m.group(3)), int(m.group(4)))
        c = int(m.group(5))
        e = (a, b) if a <= b else (b, a)
        loads[e] = c
    if not loads:
        raise RuntimeError(f"no edge rows parsed from {md_path}")
    return loads


def render_svg(
    row_widths=(4, 8, 10, 10, 10, 10, 8, 4),
    out_dir: Path | None = None,
) -> Path:
    out_dir = out_dir or Path(__file__).resolve().parent
    mesh = build_center_symmetric_mesh(row_widths)
    loads = load_edge_demands_from_md(out_dir / "per_link_bandwidth.md")
    best_c = max(loads.values())

    max_w = max(row_widths)
    # Coordinate: x = col, y = row (row 0 at top)
    cell = 72
    margin_l, margin_t, margin_r, margin_b = 56, 72, 200, 48
    width = margin_l + max_w * cell + margin_r
    height = margin_t + len(row_widths) * cell + margin_b

    def xy(r: int, c: int) -> tuple[float, float]:
        return margin_l + c * cell + cell / 2, margin_t + r * cell + cell / 2

    c_max = max(loads.values()) if loads else 1
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="IBM Plex Sans, Helvetica, Arial, sans-serif">'
    )
    parts.append('<rect width="100%" height="100%" fill="#f7f5f0"/>')
    parts.append(
        f'<text x="{margin_l}" y="28" font-size="18" font-weight="700" fill="#1a1a1a">'
        f"Center-symmetric 2D Mesh {list(row_widths)}</text>"
    )
    parts.append(
        f'<text x="{margin_l}" y="50" font-size="12" fill="#555">'
        f"Link label = C×{PORT_BW_GBPS:g} Gbps (Tbps shown). "
        f"Best C(M)={best_c} after Algorithm 1 · Clos [22, 21, 21]</text>"
    )

    # Edges first (under nodes)
    for a, b in mesh.adj_edges:
        c_load = loads.get((a, b), 0)
        bw_tbps = c_load * PORT_BW_GBPS / 1000.0
        x1, y1 = xy(*a)
        x2, y2 = xy(*b)
        col = color_for_load(c_load, c_max)
        stroke_w = 1.5 + 4.5 * (c_load / c_max if c_max else 0)
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{col}" stroke-width="{stroke_w:.2f}" stroke-linecap="round"/>'
        )
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        # Offset label slightly perpendicular for vertical vs horizontal edges
        if a[0] == b[0]:  # horizontal
            lx, ly = mx, my - 10
        else:
            lx, ly = mx + 12, my
        label = f"{bw_tbps:.1f}"
        parts.append(
            f'<rect x="{lx - 14:.1f}" y="{ly - 8:.1f}" width="28" height="14" '
            f'rx="3" fill="#f7f5f0" fill-opacity="0.92"/>'
        )
        parts.append(
            f'<text x="{lx:.1f}" y="{ly + 3:.1f}" text-anchor="middle" '
            f'font-size="9" font-weight="600" fill="#222">{label}</text>'
        )

    # Nodes
    for r, c in mesh.positions:
        x, y = xy(r, c)
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="#1f2a37" stroke="#fff" stroke-width="1.5"/>'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle" '
            f'font-size="8" fill="#fff">{r},{c}</text>'
        )

    # Color legend
    lx0 = width - margin_r + 24
    ly0 = margin_t
    parts.append(
        f'<text x="{lx0}" y="{ly0}" font-size="12" font-weight="700" fill="#1a1a1a">BW (Tbps)</text>'
    )
    for i, frac in enumerate([0.0, 0.25, 0.5, 0.75, 1.0]):
        c_val = int(round(frac * c_max))
        bw = c_val * PORT_BW_GBPS / 1000.0
        y = ly0 + 22 + i * 22
        col = color_for_load(c_val, c_max)
        parts.append(
            f'<rect x="{lx0}" y="{y - 8}" width="18" height="12" rx="2" fill="{col}"/>'
        )
        parts.append(
            f'<text x="{lx0 + 26}" y="{y + 2}" font-size="11" fill="#333">{bw:.1f}</text>'
        )

    parts.append(
        f'<text x="{lx0}" y="{ly0 + 150}" font-size="10" fill="#666">'
        f"line width ∝ C</text>"
    )
    parts.append("</svg>")
    svg = "\n".join(parts)

    svg_path = out_dir / "mesh_bandwidth.svg"
    svg_path.write_text(svg, encoding="utf-8")

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <title>2D Mesh D2D Bandwidth</title>
  <style>
    body {{ margin: 24px; background: #eceae4; font-family: "IBM Plex Sans", Helvetica, Arial, sans-serif; }}
    h1 {{ font-size: 20px; margin: 0 0 8px; }}
    p {{ color: #444; margin: 0 0 16px; font-size: 13px; }}
    .frame {{ background: #fff; padding: 12px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,.08); overflow: auto; }}
  </style>
</head>
<body>
  <h1>中心对称 2D Mesh 链路带宽需求</h1>
  <p>边上数字单位为 Tbps（= C × {PORT_BW_GBPS:g} Gbps / 1000）。颜色越红、线越粗表示需求越高。</p>
  <div class="frame">{svg}</div>
</body>
</html>
"""
    html_path = out_dir / "mesh_bandwidth.html"
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"wrote {svg_path}")
    print(f"wrote {html_path}")
    print(f"best C(M)={best_c}, hottest={best_c * PORT_BW_GBPS / 1000:.1f} Tbps")
    return svg_path


if __name__ == "__main__":
    render_svg()
