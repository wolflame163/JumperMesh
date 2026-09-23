#!/usr/bin/env python3
"""
光互联层 topology（仅 L1）：4×4 节点，两两直连。

Style matches draw_opt_elec_topology.py (white bg, centered, node circles, dashed outer frame).

Usage:
  python3 draw_opt_topology.py --png
"""

from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path
from typing import List, Sequence, Tuple

Coord = Tuple[int, int]
Pt = Tuple[float, float]

N = 4
PITCH_MM = 72.0

STROKE = "#1f5f74"
NODE = "#1f2a37"
EDGE = "#c4a574"


def nodes_4x4() -> List[Coord]:
    return [(r, c) for r in range(N) for c in range(N)]


def complete_edges(nodes: Sequence[Coord]) -> List[Tuple[Coord, Coord]]:
    edges = []
    for a, b in itertools.combinations(nodes, 2):
        edges.append((a, b) if a <= b else (b, a))
    return edges


def node_xy(r: int, c: int, ox: float, oy: float) -> Tuple[float, float]:
    return ox + c * PITCH_MM, oy + r * PITCH_MM


class Camera3D:
    def __init__(
        self,
        elev_deg: float = 30.0,
        azim_deg: float = -42.0,
        scale: float = 1.85,
        cx: float = 0.0,
        cy: float = 0.0,
    ) -> None:
        self.scale = scale
        self.cx = cx
        self.cy = cy
        ae = math.radians(elev_deg)
        aa = math.radians(azim_deg)
        ce, se = math.cos(ae), math.sin(ae)
        ca, sa = math.cos(aa), math.sin(aa)
        self.fwd = (ca * ce, sa * ce, se)
        world_up = (0.0, 0.0, 1.0)
        rx = self._cross(self.fwd, world_up)
        nrm = math.hypot(*rx) or 1.0
        self.right = (rx[0] / nrm, rx[1] / nrm, rx[2] / nrm)
        self.up = self._cross(self.right, self.fwd)

    @staticmethod
    def _cross(
        a: Tuple[float, float, float], b: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def project(self, x: float, y: float, z: float = 0.0) -> Tuple[float, float, float]:
        depth = x * self.fwd[0] + y * self.fwd[1] + z * self.fwd[2]
        sx = x * self.right[0] + y * self.right[1] + z * self.right[2]
        sy = x * self.up[0] + y * self.up[1] + z * self.up[2]
        return self.cx + self.scale * sx, self.cy - self.scale * sy, depth


def poly(pts: Sequence[Pt], **attrs: str) -> str:
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<polygon points="{d}" {extra}/>'


def line(a: Pt, b: Pt, **attrs: str) -> str:
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return (
        f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" {extra}/>'
    )


def circle(cx: float, cy: float, r: float, **attrs: str) -> str:
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r}" {extra}/>'


def build_svg() -> Tuple[str, int, int]:
    width, height = 1280, 860
    cam = Camera3D()

    nodes = nodes_4x4()
    edges = complete_edges(nodes)

    ox = -0.5 * (N - 1) * PITCH_MM
    oy = -0.5 * (N - 1) * PITCH_MM
    node_r = 12.0

    def NW(r: int, c: int) -> Tuple[float, float]:
        return node_xy(r, c, ox, oy)

    def P0(x: float, y: float) -> Pt:
        return cam.project(x, y)[:2]

    # Bbox samples
    samples: List[Pt] = []
    pad = 32.0
    for r, c in nodes:
        samples.append(P0(*NW(r, c)))
    for rr, cc in ((0, 0), (0, N - 1), (N - 1, N - 1), (N - 1, 0)):
        x, y = NW(rr, cc)
        samples.append(P0(x - pad, y - pad))
        samples.append(P0(x + pad, y + pad))
    lx, ly = NW(1, 0)
    samples.append(P0(lx - 95, ly))

    xs = [p[0] for p in samples]
    ys = [p[1] for p in samples]
    content_cx = 0.5 * (min(xs) + max(xs))
    content_cy = 0.5 * (min(ys) + max(ys))
    content_w = max(xs) - min(xs)
    content_h = max(ys) - min(ys)

    top_pad, bottom_pad, side_pad = 88.0, 90.0, 56.0
    avail_w = width - 2 * side_pad
    avail_h = height - top_pad - bottom_pad
    fit = min(avail_w / max(content_w, 1.0), avail_h / max(content_h, 1.0), 1.25)
    cam.scale *= fit
    content_cx *= fit
    content_cy *= fit
    cam.cx = width * 0.5 - content_cx
    cam.cy = top_pad + 0.5 * avail_h - content_cy

    def P(x: float, y: float) -> Pt:
        return cam.project(x, y)[:2]

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="IBM Plex Sans, PingFang SC, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width / 2:.1f}" y="36" font-size="22" font-weight="700" fill="#1c1a16" '
        f'text-anchor="middle">光互联层 · 4×4</text>',
        f'<text x="{width / 2:.1f}" y="58" font-size="13" fill="#5c574e" text-anchor="middle">'
        "4×4 节点 · 两两直连（完全图）</text>",
    ]

    # Outer dashed frame
    corners = [NW(0, 0), NW(0, N - 1), NW(N - 1, N - 1), NW(N - 1, 0)]
    cx = 0.25 * sum(p[0] for p in corners)
    cy = 0.25 * sum(p[1] for p in corners)
    frame_pad = 30.0
    frame = []
    for x, y in corners:
        dx = frame_pad if x >= cx else -frame_pad
        dy = frame_pad if y >= cy else -frame_pad
        frame.append(P(x + dx, y + dy))
    parts.append(
        poly(
            frame,
            fill="none",
            stroke=STROKE,
            stroke_width="1.6",
            stroke_dasharray="5 3",
            opacity="0.75",
        )
    )

    # Complete pairwise edges
    for a, b in edges:
        ax, ay = NW(*a)
        bx, by = NW(*b)
        manh = abs(a[0] - b[0]) + abs(a[1] - b[1])
        sw, op = ("2.2", "0.90") if manh == 1 else ("1.15", "0.42")
        parts.append(
            line(
                P(ax, ay),
                P(bx, by),
                stroke=EDGE,
                stroke_width=sw,
                stroke_opacity=op,
                stroke_linecap="round",
            )
        )

    # Nodes
    for r, c in nodes:
        px, py = P(*NW(r, c))
        parts.append(
            circle(px, py, node_r, fill=NODE, stroke="#ffffff", stroke_width="1.5")
        )
        parts.append(
            f'<text x="{px:.1f}" y="{py + 3.5:.1f}" font-size="9" fill="#fff" '
            f'text-anchor="middle">{r},{c}</text>'
        )

    # Layer label
    lx, ly = NW(1, 0)
    lab = P(lx - 82, ly)
    parts.append(
        f'<text x="{lab[0]:.1f}" y="{lab[1]:.1f}" font-size="18" font-weight="700" '
        f'fill="{STROKE}" text-anchor="end">L1</text>'
    )
    parts.append(
        f'<text x="{lab[0]:.1f}" y="{lab[1] + 16:.1f}" font-size="11" fill="#555" '
        f'text-anchor="end">光互联层</text>'
    )

    # Legend
    ly = height - 58
    x0 = width * 0.5 - 70
    parts.append(line((x0, ly), (x0 + 28, ly), stroke=EDGE, stroke_width="2.2"))
    parts.append(
        f'<text x="{x0 + 36:.1f}" y="{ly + 4:.1f}" font-size="12" fill="#333">光互联（两两直连）</text>'
    )
    parts.append(
        f'<text x="{width / 2:.1f}" y="{height - 28}" font-size="12" fill="#555" text-anchor="middle">'
        f"4×4 = {N * N} 节点 · 完全图 {len(edges)} 条边"
        "</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts), width, height


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("figures/opt_topology.svg"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()

    svg, w, h = build_svg()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({w}×{h})")
    print(f"nodes={N * N} · complete edges={len(complete_edges(nodes_4x4()))}")

    if args.png:
        import shutil
        import subprocess
        import tempfile

        png = args.out.with_suffix(".png")
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                ["qlmanage", "-t", "-s", "1600", "-o", td, str(args.out)],
                check=False,
                capture_output=True,
            )
            cand = Path(td) / (args.out.name + ".png")
            if cand.exists():
                shutil.copy2(cand, png)
                print(f"wrote {png}")


if __name__ == "__main__":
    main()
