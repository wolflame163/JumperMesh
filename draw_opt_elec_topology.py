#!/usr/bin/env python3
"""
光互联层 + 电互联层 topology（3D 节点样式，无晶圆圆盘）.

  L1 光互联层: 4×4 节点；只连其他 2×2 组，本 2×2 组内无光边
  L2 电互联层: 4 个互不连通的 2×2 Mesh
  垂直互联: 光/电共址虚线

Usage:
  python3 draw_opt_elec_topology.py --png
"""

from __future__ import annotations

import argparse
import itertools
import math
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

Coord = Tuple[int, int]
Pt = Tuple[float, float]

N = 4
PITCH_MM = 72.0
Z_GAP_MM = 200.0
# Slight XY offset for L2 so it does not fully cover L1.
L2_DX_MM = 32.0
L2_DY_MM = -26.0

ELEC_WINDOWS: Tuple[Tuple[int, int, int, int], ...] = (
    (0, 0, 1, 1),
    (0, 2, 1, 3),
    (2, 0, 3, 1),
    (2, 2, 3, 3),
)

STAGE = (
    {
        "z": 0.0,
        "stroke": "#1f5f74",
        "node": "#1f2a37",
        "edge": "#c4a574",
        "name": "L1",
        "sub": "光互联层",
    },
    {
        "z": Z_GAP_MM,
        "stroke": "#3d6fd8",
        "node": "#3d6fd8",
        "edge": "#5b8def",
        "name": "L2",
        "sub": "电互联层",
    },
)


def nodes_4x4() -> List[Coord]:
    return [(r, c) for r in range(N) for c in range(N)]


def window_id_map() -> Dict[Coord, int]:
    m: Dict[Coord, int] = {}
    for wi, (r0, c0, r1, c1) in enumerate(ELEC_WINDOWS):
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                m[(r, c)] = wi
    return m


def optical_edges(nodes: Sequence[Coord]) -> List[Tuple[Coord, Coord]]:
    wid = window_id_map()
    edges = []
    for a, b in itertools.combinations(nodes, 2):
        if wid[a] == wid[b]:
            continue
        edges.append((a, b) if a <= b else (b, a))
    return edges


def electrical_edges() -> List[Tuple[Coord, Coord]]:
    edges: List[Tuple[Coord, Coord]] = []
    for r0, c0, r1, c1 in ELEC_WINDOWS:
        pos = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)}
        for r, c in pos:
            for nr, nc in ((r, c + 1), (r + 1, c)):
                if (nr, nc) in pos:
                    a, b = (r, c), (nr, nc)
                    edges.append((a, b) if a <= b else (b, a))
    return edges


def node_xy(r: int, c: int, ox: float, oy: float) -> Tuple[float, float]:
    return ox + c * PITCH_MM, oy + r * PITCH_MM


class Camera3D:
    def __init__(
        self,
        elev_deg: float = 30.0,
        azim_deg: float = -42.0,
        scale: float = 1.55,
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

    def project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
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
    width, height = 1280, 920
    mid_z = 0.5 * Z_GAP_MM
    cam = Camera3D()
    z_off = -mid_z

    nodes = nodes_4x4()
    opt_e = optical_edges(nodes)
    ele_e = electrical_edges()

    ox = -0.5 * (N - 1) * PITCH_MM
    oy = -0.5 * (N - 1) * PITCH_MM
    node_r = 11.0

    def layer_shift(stage_i: int) -> Tuple[float, float]:
        return (L2_DX_MM, L2_DY_MM) if stage_i == 1 else (0.0, 0.0)

    def node_world(r: int, c: int, stage_i: int) -> Tuple[float, float]:
        x, y = node_xy(r, c, ox, oy)
        dx, dy = layer_shift(stage_i)
        return x + dx, y + dy

    def P0(x: float, y: float, z: float) -> Tuple[float, float, float]:
        return cam.project(x, y, z + z_off)

    samples: List[Pt] = []
    for stage_i in range(2):
        z = float(STAGE[stage_i]["z"])
        for r, c in nodes:
            samples.append(P0(*node_world(r, c, stage_i), z)[:2])
        pad = 32.0
        for rr, cc in ((0, 0), (0, N - 1), (N - 1, N - 1), (N - 1, 0)):
            x, y = node_world(rr, cc, stage_i)
            samples.append(P0(x - pad, y - pad, z)[:2])
            samples.append(P0(x + pad, y + pad, z)[:2])
        lx, ly = node_world(1, 0, stage_i)
        samples.append(P0(lx - 95, ly, z)[:2])

    xs = [p[0] for p in samples]
    ys = [p[1] for p in samples]
    content_cx = 0.5 * (min(xs) + max(xs))
    content_cy = 0.5 * (min(ys) + max(ys))
    content_w = max(xs) - min(xs)
    content_h = max(ys) - min(ys)

    top_pad, bottom_pad, side_pad = 88.0, 100.0, 56.0
    avail_w = width - 2 * side_pad
    avail_h = height - top_pad - bottom_pad
    fit = min(avail_w / max(content_w, 1.0), avail_h / max(content_h, 1.0), 1.15)
    cam.scale *= fit
    content_cx *= fit
    content_cy *= fit
    cam.cx = width * 0.5 - content_cx
    cam.cy = top_pad + 0.5 * avail_h - content_cy

    def P(x: float, y: float, z: float) -> Tuple[float, float, float]:
        return cam.project(x, y, z + z_off)

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="IBM Plex Sans, PingFang SC, Helvetica, Arial, sans-serif">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{width / 2:.1f}" y="36" font-size="22" font-weight="700" fill="#1c1a16" '
        f'text-anchor="middle">光互联层 + 电互联层 · L1 / L2</text>',
        f'<text x="{width / 2:.1f}" y="58" font-size="13" fill="#5c574e" text-anchor="middle">'
        "4×4 节点 · L1 光互联仅跨 2×2 组 · L2 电互联 4×(2×2 Mesh) · 垂直光电互联</text>",
    ]

    def frame_quad(stage_i: int, r0: int, c0: int, r1: int, c1: int, pad: float) -> List[Pt]:
        corners = [
            node_world(r0, c0, stage_i),
            node_world(r0, c1, stage_i),
            node_world(r1, c1, stage_i),
            node_world(r1, c0, stage_i),
        ]
        cx = 0.25 * sum(p[0] for p in corners)
        cy = 0.25 * sum(p[1] for p in corners)
        out = []
        for x, y in corners:
            dx = pad if x >= cx else -pad
            dy = pad if y >= cy else -pad
            out.append((x + dx, y + dy))
        z = float(STAGE[stage_i]["z"])
        return [P(x, y, z)[:2] for x, y in out]

    draw_order = sorted(range(2), key=lambda i: P(0, 0, float(STAGE[i]["z"]))[2])

    for stage_i in draw_order:
        st = STAGE[stage_i]
        z = float(st["z"])

        if stage_i == 0:
            parts.append(
                poly(
                    frame_quad(0, 0, 0, N - 1, N - 1, 30.0),
                    fill="none",
                    stroke=str(st["stroke"]),
                    stroke_width="1.6",
                    stroke_dasharray="5 3",
                    opacity="0.75",
                )
            )
            for a, b in opt_e:
                ax, ay = node_world(*a, 0)
                bx, by = node_world(*b, 0)
                parts.append(
                    line(
                        P(ax, ay, z)[:2],
                        P(bx, by, z)[:2],
                        stroke=str(st["edge"]),
                        stroke_width="1.2",
                        stroke_opacity="0.48",
                        stroke_linecap="round",
                    )
                )
        else:
            for r0, c0, r1, c1 in ELEC_WINDOWS:
                parts.append(
                    poly(
                        frame_quad(1, r0, c0, r1, c1, 24.0),
                        fill="none",
                        stroke=str(st["stroke"]),
                        stroke_width="1.4",
                        stroke_dasharray="5 3",
                        opacity="0.60",
                    )
                )
            for a, b in ele_e:
                ax, ay = node_world(*a, 1)
                bx, by = node_world(*b, 1)
                parts.append(
                    line(
                        P(ax, ay, z)[:2],
                        P(bx, by, z)[:2],
                        stroke=str(st["edge"]),
                        stroke_width="2.5",
                        stroke_linecap="round",
                    )
                )

        for r, c in nodes:
            x, y = node_world(r, c, stage_i)
            px, py, _ = P(x, y, z)
            parts.append(
                circle(
                    px,
                    py,
                    node_r,
                    fill=str(st["node"]),
                    stroke="#ffffff",
                    stroke_width="1.5",
                )
            )
            parts.append(
                f'<text x="{px:.1f}" y="{py + 3.5:.1f}" font-size="9" fill="#fff" '
                f'text-anchor="middle">{r},{c}</text>'
            )

        lx, ly = node_world(1, 0, stage_i)
        lab = P(lx - 82, ly, z)
        parts.append(
            f'<text x="{lab[0]:.1f}" y="{lab[1]:.1f}" font-size="18" font-weight="700" '
            f'fill="{st["stroke"]}" text-anchor="end">{st["name"]}</text>'
        )
        parts.append(
            f'<text x="{lab[0]:.1f}" y="{lab[1] + 16:.1f}" font-size="11" fill="#555" '
            f'text-anchor="end">{st["sub"]}</text>'
        )

        # Verticals after L1, before L2 nodes stay on top of dashed lines.
        if stage_i == draw_order[0]:
            z0 = float(STAGE[0]["z"])
            z1 = float(STAGE[1]["z"])
            for r, c in nodes:
                x0, y0 = node_world(r, c, 0)
                x1, y1 = node_world(r, c, 1)
                parts.append(
                    line(
                        P(x0, y0, z0)[:2],
                        P(x1, y1, z1)[:2],
                        stroke="#2a9d8f",
                        stroke_width="1.5",
                        stroke_dasharray="3 2.5",
                        stroke_opacity="0.62",
                    )
                )

    ly = height - 72
    items = [
        ("#c4a574", "2.2", None, "光互联（跨组）"),
        ("#5b8def", "2.4", None, "电互联（组内）"),
        ("#2a9d8f", "1.6", "3 2.5", "垂直光电互联"),
    ]
    total_w = 130 * len(items)
    x_start = width * 0.5 - total_w * 0.5
    for i, (color, sw, dash, label) in enumerate(items):
        x0 = x_start + i * 130
        attrs: dict = {"stroke": color, "stroke_width": sw}
        if dash:
            attrs["stroke_dasharray"] = dash
        parts.append(line((x0, ly), (x0 + 24, ly), **attrs))
        parts.append(
            f'<text x="{x0 + 30:.1f}" y="{ly + 4:.1f}" font-size="11" fill="#333">{label}</text>'
        )
    parts.append(
        f'<text x="{width / 2:.1f}" y="{height - 38}" font-size="12" fill="#555" text-anchor="middle">'
        "L1：跨 2×2 组光互联（组内无光边） · L2：4×(2×2 Mesh) · 青色虚线：垂直光电互联"
        "</text>"
    )

    parts.append("</svg>")
    return "\n".join(parts), width, height


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("figures/opt_elec_topology.svg"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()

    svg, w, h = build_svg()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({w}×{h})")
    print(
        f"optical cross-group={len(optical_edges(nodes_4x4()))} · "
        f"electrical={len(electrical_edges())} · vertical={N * N}"
    )

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
