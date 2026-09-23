#!/usr/bin/env python3
"""
Clos [66,66,66] logical topology as three circular wafers in a standard 3D view.

Each wafer is a disk parallel to the XY plane, centered on the Z axis.
66 dies of 25 mm × 32 mm sit in the NOW center-symmetric 2D Mesh
  row_widths = (4, 8, 10, 10, 10, 10, 8, 6).

Stages L1 / L2 / L3 are stacked along Z.

Usage:
  python3 draw_clos_logical_topology.py
  python3 draw_clos_logical_topology.py --png
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List, Sequence, Tuple

ROW_WIDTHS: Tuple[int, ...] = (4, 8, 10, 10, 10, 10, 8, 6)
N_SSC = sum(ROW_WIDTHS)
assert N_SSC == 66

# Die footprint: 25 mm along X, 32 mm along Y (user request).
DIE_X_MM = 25.0
DIE_Y_MM = 32.0
PORT_BW_GBPS = 200.0

# Circular wafer radius: circumscribe the centered NOW mesh + rim margin.
# Mesh span with 25×32 mm dies: 10×25 × 8×32 → need R ≳ √(125²+128²) ≈ 179 mm.
# 300 mm wafer → radius 150 mm (NOW mesh with 25×32 mm dies fits with ~1.6 mm rim).
WAFER_DIAM_MM = 300.0
WAFER_R_MM = 0.5 * WAFER_DIAM_MM
Z_GAP_MM = 260.0


Coord = Tuple[int, int]
Pt = Tuple[float, float]


def now_positions(row_widths: Sequence[int] = ROW_WIDTHS) -> List[Coord]:
    max_w = max(row_widths)
    pos: List[Coord] = []
    for r, w in enumerate(row_widths):
        offset = (max_w - w) // 2
        for c in range(offset, offset + w):
            pos.append((r, c))
    return pos


def mesh_edges(positions: Sequence[Coord]) -> List[Tuple[Coord, Coord]]:
    s = set(positions)
    edges = []
    for r, c in positions:
        for nr, nc in ((r, c + 1), (r + 1, c)):
            if (nr, nc) in s:
                a, b = (r, c), (nr, nc)
                edges.append((a, b) if a <= b else (b, a))
    return edges


def die_corners_xy(r: int, c: int, origin_x: float, origin_y: float) -> List[Tuple[float, float]]:
    x0 = origin_x + c * DIE_X_MM
    y0 = origin_y + r * DIE_Y_MM
    return [
        (x0, y0),
        (x0 + DIE_X_MM, y0),
        (x0 + DIE_X_MM, y0 + DIE_Y_MM),
        (x0, y0 + DIE_Y_MM),
    ]


def die_center_xy(r: int, c: int, origin_x: float, origin_y: float) -> Tuple[float, float]:
    corners = die_corners_xy(r, c, origin_x, origin_y)
    return 0.5 * (corners[0][0] + corners[2][0]), 0.5 * (corners[0][1] + corners[2][1])


class Camera3D:
    """
    Orthographic 3D view (equal wafer size at every Z).
    World: X right, Y depth, Z up. Wafer disks lie in planes of constant Z,
    centered at (0, 0, z) — parallel to the XY plane.
    """

    def __init__(
        self,
        elev_deg: float = 28.0,
        azim_deg: float = -48.0,
        scale: float = 1.15,
        cx: float = 640.0,
        cy: float = 470.0,
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
        n = math.hypot(*rx) or 1.0
        self.right = (rx[0] / n, rx[1] / n, rx[2] / n)
        self.up = self._cross(self.right, self.fwd)

    @staticmethod
    def _cross(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> Tuple[float, float, float]:
        return (
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0],
        )

    def project(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
        depth = x * self.fwd[0] + y * self.fwd[1] + z * self.fwd[2]
        sx = x * self.right[0] + y * self.right[1] + z * self.right[2]
        sy = x * self.up[0] + y * self.up[1] + z * self.up[2]
        px = self.cx + self.scale * sx
        py = self.cy - self.scale * sy
        return px, py, depth


def poly(pts: Sequence[Pt], **attrs: str) -> str:
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return f'<polygon points="{d}" {extra}/>'


def line(a: Pt, b: Pt, **attrs: str) -> str:
    extra = " ".join(f'{k.replace("_", "-")}="{v}"' for k, v in attrs.items())
    return (
        f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" {extra}/>'
    )


STAGE = (
    {"z": 0.0, "fill": "#d7e6ef", "stroke": "#1f5f74", "die": "#f7fbfd", "edge": "#6d93a4", "name": "L1"},
    {"z": Z_GAP_MM, "fill": "#dcead9", "stroke": "#3d6b58", "die": "#f8fbf6", "edge": "#7ea07c", "name": "L2"},
    {"z": 2 * Z_GAP_MM, "fill": "#f0e2d2", "stroke": "#8b5a2b", "die": "#fdfaf6", "edge": "#b89674", "name": "L3"},
)

# Source die for inter-stage fan-out (row, col) on the NOW grid.
FAN_SRC: Coord = (0, 3)


def build_svg() -> Tuple[str, int, int]:
    width, height = 1280, 960
    mid_z = Z_GAP_MM
    cam = Camera3D(cx=width * 0.50, cy=height * 0.52, scale=1.18)
    z_off = -mid_z

    positions = now_positions()
    assert FAN_SRC in set(positions), f"FAN_SRC {FAN_SRC} not on NOW mesh"
    edges = mesh_edges(positions)
    max_w = max(ROW_WIDTHS)
    n_rows = len(ROW_WIDTHS)
    span_x = max_w * DIE_X_MM
    span_y = n_rows * DIE_Y_MM
    ox = -0.5 * span_x
    oy = -0.5 * span_y

    def P(x: float, y: float, z: float) -> Tuple[float, float, float]:
        return cam.project(x, y, z + z_off)

    parts: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" '
        f'font-family="IBM Plex Sans, PingFang SC, Helvetica, Arial, sans-serif">',
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#f0f3f5"/>'
        '<stop offset="100%" stop-color="#e6e2d8"/>'
        "</linearGradient>"
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="url(#bg)"/>',
        '<text x="40" y="40" font-size="22" font-weight="700" fill="#1c1a16">'
        "Clos 逻辑交换 · 三晶圆 L1 / L2 / L3</text>",
        '<text x="40" y="64" font-size="13" fill="#5c574e">'
        f"等尺寸圆形晶圆 · {N_SSC} die × {DIE_X_MM:.0f}×{DIE_Y_MM:.0f} mm · "
        f"NOW Mesh {list(ROW_WIDTHS)} · "
        f"层间示意：L1(0,3)→全部 L2，L2(0,3)→全部 L3</text>",
    ]

    order = sorted(range(3), key=lambda i: P(0, 0, float(STAGE[i]["z"]))[2])

    for stage_i in order:
        st = STAGE[stage_i]
        z = float(st["z"])
        disk = []
        for i in range(96):
            t = 2 * math.pi * i / 96
            disk.append(P(WAFER_R_MM * math.cos(t), WAFER_R_MM * math.sin(t), z)[:2])
        parts.append(
            poly(disk, fill=str(st["fill"]), stroke=str(st["stroke"]), stroke_width="2.4", opacity="0.97")
        )

        for a, b in edges:
            ax, ay = die_center_xy(*a, ox, oy)
            bx, by = die_center_xy(*b, ox, oy)
            parts.append(
                line(
                    P(ax, ay, z)[:2],
                    P(bx, by, z)[:2],
                    stroke=str(st["edge"]),
                    stroke_width="1.15",
                    stroke_linecap="round",
                )
            )

        for r, c in positions:
            q = [P(x, y, z)[:2] for x, y in die_corners_xy(r, c, ox, oy)]
            is_src = (r, c) == FAN_SRC and stage_i in (0, 1)
            fill = "#ffe08a" if is_src else str(st["die"])
            sw = "1.6" if is_src else "0.65"
            parts.append(
                poly(q, fill=fill, stroke=str(st["stroke"]), stroke_width=sw)
            )

        lab = P(-WAFER_R_MM - 24, 0, z)
        parts.append(
            f'<text x="{lab[0]:.1f}" y="{lab[1]:.1f}" font-size="20" font-weight="700" '
            f'fill="{st["stroke"]}" text-anchor="end">{st["name"]}</text>'
        )

    # Inter-layer fans: L1(0,3)→all L2, L2(0,3)→all L3
    sx, sy = die_center_xy(*FAN_SRC, ox, oy)

    def fan_out(stage_src: int, stage_dst: int, color: str) -> None:
        za = float(STAGE[stage_src]["z"])
        zb = float(STAGE[stage_dst]["z"])
        pa = P(sx, sy, za)[:2]
        for r, c in positions:
            dx, dy = die_center_xy(r, c, ox, oy)
            pb = P(dx, dy, zb)[:2]
            parts.append(
                line(pa, pb, stroke=color, stroke_width="0.7", stroke_opacity="0.38")
            )

    fan_out(0, 1, "#1f5f74")
    fan_out(1, 2, "#8b5a2b")

    # Label the fan source on L1 / L2
    for stage_i, tag in ((0, "L1(0,3)"), (1, "L2(0,3)")):
        px, py, _ = P(sx, sy, float(STAGE[stage_i]["z"]))
        parts.append(
            f'<text x="{px:.1f}" y="{py - 10:.1f}" font-size="11" font-weight="700" '
            f'fill="#333" text-anchor="middle">{tag}</text>'
        )

    lx, ly = 40, height - 108
    parts.append(
        f'<rect x="{lx}" y="{ly}" width="620" height="76" fill="#fffcf7" stroke="#d4cfc4"/>'
    )
    legend = [
        f"三晶圆等尺寸圆盘（直径 {WAFER_DIAM_MM:.0f} mm）· die {DIE_X_MM:.0f}×{DIE_Y_MM:.0f} mm · {N_SSC} SSC",
        f"层内：NOW 2D-Mesh；层间示意：L1(0,3)→全部 L2、L2(0,3)→全部 L3 @ {PORT_BW_GBPS:.0f}G",
        "高亮方块为扇出源 die（0,3）",
    ]
    for i, text in enumerate(legend):
        parts.append(
            f'<text x="{lx + 14}" y="{ly + 22 + i * 20}" font-size="12" fill="#333">{text}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts), width, height


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("figures/clos_logical_topology.svg"))
    ap.add_argument("--png", action="store_true")
    args = ap.parse_args()

    svg, w, h = build_svg()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({w}×{h})")
    print(f"fan source {FAN_SRC} → {N_SSC} destinations × 2 stages")

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
