#!/usr/bin/env python3
"""
Configurable 3D mesh: NOW layer + jumper (跳线) layer.

Defaults:
  NOW (z=0): 2D mesh (4,8,10,10,10,10,8,6), edge delay 80 ns,
             capacity 350×200G ports per directed edge (Layer 0)
  Jumper (z=1): one of several mesh layouts over NOW coordinates
                (see jumper_topo), edge delay 1 ns,
                capacity 180×200G ports per directed edge (Layer 1)
  Vertical NOW↔jumper: delay 5 ns, capacity 250×200G per directed edge
  Power (pJ/bit):
    NOW edge: 0.06 pJ/(bit·mm) × 25 mm = 1.5
    Vertical: 1.3/2 = 0.65
    Jumper edge: 0

Jumper topologies (only jumper layer changes; NOW unchanged):
  single — one mesh over (2,2)–(5,7)  [default]
  dual   — two meshes: (0,2)–(3,7) and (4,2)–(7,7)
  quad   — four meshes: (0,0)–(3,4), (0,5)–(3,9), (4,0)–(7,4), (4,5)–(7,9)
  full   — jumper mirrors NOW geometry (same dies / adjacency); capacity still
           jumper_capacity_links (default 180×200G, smaller than NOW 350×200G)

Each jumper window is an independent 2D mesh (no edges across windows).
Jumper nodes are placed only where a NOW die exists at the same (r,c).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Coord3 = Tuple[int, int, int]  # (z, r, c)  z=0 NOW, z=1 jumper
# Inclusive window: (row_min, col_min, row_max, col_max)
JumperWindow = Tuple[int, int, int, int]

# Preset jumper layouts (coordinate windows on the NOW plane).
JUMPER_TOPO_SINGLE: Tuple[JumperWindow, ...] = ((2, 2, 5, 7),)
JUMPER_TOPO_DUAL: Tuple[JumperWindow, ...] = (
    (0, 2, 3, 7),
    (4, 2, 7, 7),
)
JUMPER_TOPO_QUAD: Tuple[JumperWindow, ...] = (
    (0, 0, 3, 4),
    (0, 5, 3, 9),
    (4, 0, 7, 4),
    (4, 5, 7, 9),
)
# Full bbox covering the center-symmetric NOW floorplan (row_widths max col=9).
# Nodes are still clipped to existing NOW dies → same topology as NOW.
JUMPER_TOPO_FULL: Tuple[JumperWindow, ...] = ((0, 0, 7, 9),)

JUMPER_TOPO_PRESETS: Dict[str, Tuple[JumperWindow, ...]] = {
    "single": JUMPER_TOPO_SINGLE,
    "dual": JUMPER_TOPO_DUAL,
    "quad": JUMPER_TOPO_QUAD,
    "full": JUMPER_TOPO_FULL,
}


def format_jumper_windows(
    windows: Sequence[JumperWindow], topo: Optional[str] = None
) -> str:
    if topo and topo.lower() == "full":
        return "NOW-mirror (full floorplan)"
    if not windows:
        return "— (none)"
    return " + ".join(f"({a},{b})–({c},{d})" for a, b, c, d in windows)


@dataclass
class Mesh3DConfig:
    row_widths: Tuple[int, ...] = (4, 8, 10, 10, 10, 10, 8, 6)
    # Jumper layout: preset name and/or explicit windows.
    # If jumper_windows is set, it wins; else jumper_topo selects a preset.
    # For topo="single", the single-window fields below are used (back-compat).
    jumper_topo: str = "single"
    jumper_windows: Optional[Tuple[JumperWindow, ...]] = None
    jumper_row_min: int = 2
    jumper_row_max: int = 5
    jumper_col_min: int = 2
    jumper_col_max: int = 7
    delay_now_ns: float = 80.0
    delay_jumper_ns: float = 1.0
    delay_vertical_ns: float = 5.0
    enable_jumper: bool = True
    # Max logical links (#200G ports) per directed edge
    now_capacity_links: int = 350  # Layer 0
    jumper_capacity_links: int = 180  # Layer 1
    vertical_capacity_links: int = 250
    # Power model (pJ/bit)
    now_power_density_pj_per_bit_mm: float = 0.06
    now_edge_length_mm: float = 25.0
    vertical_power_pj_per_bit: float = 1.3 / 2.0  # 0.65
    jumper_power_pj_per_bit: float = 0.0

    def resolved_jumper_windows(self) -> Tuple[JumperWindow, ...]:
        if not self.enable_jumper:
            return tuple()
        if self.jumper_windows is not None:
            return tuple(self.jumper_windows)
        topo = (self.jumper_topo or "single").lower()
        if topo in ("none", "off", "baseline"):
            return tuple()
        if topo == "single":
            return (
                (
                    self.jumper_row_min,
                    self.jumper_col_min,
                    self.jumper_row_max,
                    self.jumper_col_max,
                ),
            )
        if topo not in JUMPER_TOPO_PRESETS:
            raise ValueError(
                f"Unknown jumper_topo={self.jumper_topo!r}; "
                f"expected one of {sorted(JUMPER_TOPO_PRESETS)} or none"
            )
        return JUMPER_TOPO_PRESETS[topo]

    def jumper_bbox(self) -> JumperWindow:
        wins = self.resolved_jumper_windows()
        if not wins:
            return (0, 0, -1, -1)
        return (
            min(w[0] for w in wins),
            min(w[1] for w in wins),
            max(w[2] for w in wins),
            max(w[3] for w in wins),
        )

    # Back-compat aliases used by older call sites
    @property
    def layer1_row_min(self) -> int:
        return self.jumper_bbox()[0]

    @property
    def layer1_row_max(self) -> int:
        return self.jumper_bbox()[2]

    @property
    def layer1_col_min(self) -> int:
        return self.jumper_bbox()[1]

    @property
    def layer1_col_max(self) -> int:
        return self.jumper_bbox()[3]

    @property
    def delay_layer0_ns(self) -> float:
        return self.delay_now_ns

    @property
    def delay_layer1_ns(self) -> float:
        return self.delay_jumper_ns

    @property
    def enable_layer1(self) -> bool:
        return self.enable_jumper

    @property
    def now_edge_power_pj_per_bit(self) -> float:
        return self.now_power_density_pj_per_bit_mm * self.now_edge_length_mm


@dataclass
class Mesh3D:
    config: Mesh3DConfig
    positions: Tuple[Coord3, ...]
    adj_edges: Tuple[Tuple[Coord3, Coord3], ...]
    delay: Dict[Tuple[Coord3, Coord3], float]
    energy: Dict[Tuple[Coord3, Coord3], float]  # pJ/bit both dirs
    now_positions: Tuple[Coord3, ...]
    jumper_positions: Tuple[Coord3, ...]
    # Per jumper node: which window index it belongs to (independent meshes)
    jumper_component: Dict[Coord3, int] = field(default_factory=dict)

    # aliases
    @property
    def layer0_positions(self) -> Tuple[Coord3, ...]:
        return self.now_positions

    @property
    def layer1_positions(self) -> Tuple[Coord3, ...]:
        return self.jumper_positions

    def nbr_map(self) -> Dict[Coord3, List[Coord3]]:
        nbrs: Dict[Coord3, List[Coord3]] = {p: [] for p in self.positions}
        for a, b in self.adj_edges:
            nbrs[a].append(b)
            nbrs[b].append(a)
        for p in nbrs:
            nbrs[p].sort()
        return nbrs

    def edge_delay(self, a: Coord3, b: Coord3) -> float:
        return self.delay[(a, b)]

    def edge_energy(self, a: Coord3, b: Coord3) -> float:
        return self.energy[(a, b)]

    def edge_kind(self, a: Coord3, b: Coord3) -> str:
        if a[0] != b[0]:
            return "vertical"
        return "now" if a[0] == 0 else "jumper"


def _now_positions(row_widths: Sequence[int]) -> List[Coord3]:
    max_w = max(row_widths)
    pos: List[Coord3] = []
    for r, w in enumerate(row_widths):
        offset = (max_w - w) // 2
        for c in range(offset, offset + w):
            pos.append((0, r, c))
    return pos


def build_mesh3d(cfg: Optional[Mesh3DConfig] = None) -> Mesh3D:
    cfg = cfg or Mesh3DConfig()
    now = _now_positions(cfg.row_widths)
    now_set = set(now)

    jumper: List[Coord3] = []
    jumper_component: Dict[Coord3, int] = {}
    # Per-window node sets (for intra-window edges only)
    window_sets: List[set] = []

    if cfg.enable_jumper:
        for wi, (r0, c0, r1, c1) in enumerate(cfg.resolved_jumper_windows()):
            if r0 > r1 or c0 > c1:
                raise ValueError(f"Invalid jumper window ({r0},{c0})–({r1},{c1})")
            wset: set = set()
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    if (0, r, c) not in now_set:
                        # Irregular NOW floorplan: skip missing dies.
                        continue
                    node = (1, r, c)
                    if node in jumper_component and jumper_component[node] != wi:
                        raise ValueError(
                            f"Jumper node ({r},{c}) falls in overlapping windows "
                            f"{jumper_component[node]} and {wi}"
                        )
                    if node not in jumper_component:
                        jumper.append(node)
                        jumper_component[node] = wi
                    wset.add(node)
            window_sets.append(wset)

    jumper_set = set(jumper)
    positions = tuple(now + jumper)

    edges = set()
    delay: Dict[Tuple[Coord3, Coord3], float] = {}
    energy: Dict[Tuple[Coord3, Coord3], float] = {}

    e_now = cfg.now_edge_power_pj_per_bit
    e_j = cfg.jumper_power_pj_per_bit
    e_v = cfg.vertical_power_pj_per_bit

    def add_undirected(a: Coord3, b: Coord3, d: float, e: float) -> None:
        if a > b:
            a, b = b, a
        edges.add((a, b))
        delay[(a, b)] = d
        delay[(b, a)] = d
        energy[(a, b)] = e
        energy[(b, a)] = e

    for _, r, c in now:
        for nr, nc in ((r, c + 1), (r + 1, c)):
            nxt = (0, nr, nc)
            if nxt in now_set:
                add_undirected((0, r, c), nxt, cfg.delay_now_ns, e_now)

    # Jumper edges: only within the same window mesh (no cross-window links).
    for wset in window_sets:
        for _, r, c in list(wset):
            for nr, nc in ((r, c + 1), (r + 1, c)):
                nxt = (1, nr, nc)
                if nxt in wset:
                    add_undirected((1, r, c), nxt, cfg.delay_jumper_ns, e_j)

    for _, r, c in jumper:
        add_undirected((0, r, c), (1, r, c), cfg.delay_vertical_ns, e_v)

    return Mesh3D(
        config=cfg,
        positions=positions,
        adj_edges=tuple(sorted(edges)),
        delay=delay,
        energy=energy,
        now_positions=tuple(now),
        jumper_positions=tuple(jumper),
        jumper_component=jumper_component,
    )


def path_delay(mesh: Mesh3D, nodes: Sequence[Coord3]) -> float:
    if len(nodes) <= 1:
        return 0.0
    return sum(mesh.edge_delay(a, b) for a, b in zip(nodes, nodes[1:]))


def path_energy_pj_per_bit(mesh: Mesh3D, nodes: Sequence[Coord3]) -> float:
    if len(nodes) <= 1:
        return 0.0
    return sum(mesh.edge_energy(a, b) for a, b in zip(nodes, nodes[1:]))


# Data-movement power: P = E × B × 1e-12 × ACCEL
# ACCEL = 1.5 is an extra acceleration / activity factor on top of nominal 200G.
POWER_ACCEL_RATIO = 1.5


def energy_to_power_w(
    energy_pj_per_bit: float,
    port_bw_gbps: float = 200.0,
    accel_ratio: float = POWER_ACCEL_RATIO,
) -> float:
    """
    数据搬移功耗：
      P[W] = E[pJ/bit] × B[bit/s] × 1e-12 × accel_ratio

    默认 B = 200 Gbps，accel_ratio = 1.5（额外加速比）。
    """
    rate_bps = port_bw_gbps * 1e9
    return energy_pj_per_bit * rate_bps * 1e-12 * accel_ratio


def path_power_w(
    mesh: Mesh3D,
    nodes: Sequence[Coord3],
    port_bw_gbps: float = 200.0,
    accel_ratio: float = POWER_ACCEL_RATIO,
) -> float:
    return energy_to_power_w(
        path_energy_pj_per_bit(mesh, nodes), port_bw_gbps, accel_ratio=accel_ratio
    )


def summarize_mesh3d(mesh: Mesh3D) -> dict:
    cfg = mesh.config
    wins = cfg.resolved_jumper_windows()
    n_vert = sum(1 for a, b in mesh.adj_edges if a[0] != b[0])
    n_now = sum(1 for a, b in mesh.adj_edges if a[0] == b[0] == 0)
    n_j = sum(1 for a, b in mesh.adj_edges if a[0] == b[0] == 1)
    # Per-window jumper node / edge counts
    win_stats = []
    for wi, w in enumerate(wins):
        nodes = [p for p, c in mesh.jumper_component.items() if c == wi]
        nset = set(nodes)
        n_e = sum(
            1
            for a, b in mesh.adj_edges
            if a[0] == b[0] == 1 and a in nset and b in nset
        )
        win_stats.append(
            {
                "index": wi,
                "window": list(w),
                "n_nodes": len(nodes),
                "n_edges_undirected": n_e,
            }
        )
    return {
        "layers": {"z0": "NOW", "z1": "jumper/跳线层"},
        "row_widths": list(cfg.row_widths),
        "enable_jumper": cfg.enable_jumper,
        "jumper_topo": (
            "none"
            if not cfg.enable_jumper
            else (cfg.jumper_topo if cfg.jumper_windows is None else "custom")
        ),
        "jumper_windows": [list(w) for w in wins],
        "jumper_windows_label": format_jumper_windows(wins, topo=cfg.jumper_topo),
        "jumper_window": list(cfg.jumper_bbox()),  # bbox back-compat
        "n_jumper_meshes": len(wins),
        "jumper_window_stats": win_stats,
        "n_now": len(mesh.now_positions),
        "n_jumper": len(mesh.jumper_positions),
        "n_nodes": len(mesh.positions),
        "n_edges_undirected": len(mesh.adj_edges),
        "n_edges_now": n_now,
        "n_edges_jumper": n_j,
        "n_edges_vertical": n_vert,
        "delays_ns": {
            "now": cfg.delay_now_ns,
            "jumper": cfg.delay_jumper_ns,
            "vertical": cfg.delay_vertical_ns,
        },
        "now_capacity_links": cfg.now_capacity_links,
        "now_capacity_bw_tbps": cfg.now_capacity_links * 200 / 1000.0,
        "jumper_capacity_links": cfg.jumper_capacity_links,
        "jumper_capacity_bw_tbps": cfg.jumper_capacity_links * 200 / 1000.0,
        "vertical_capacity_links": cfg.vertical_capacity_links,
        "vertical_capacity_bw_tbps": cfg.vertical_capacity_links * 200 / 1000.0,
        "power_pj_per_bit": {
            "now_edge": cfg.now_edge_power_pj_per_bit,
            "now_formula": (
                f"{cfg.now_power_density_pj_per_bit_mm} pJ/(bit·mm) "
                f"× {cfg.now_edge_length_mm} mm"
            ),
            "vertical": cfg.vertical_power_pj_per_bit,
            "jumper_edge": cfg.jumper_power_pj_per_bit,
        },
    }
