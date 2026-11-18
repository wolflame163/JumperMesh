#!/usr/bin/env python3
"""基于 mapping/*.log 绘制 DSL 方案每颗 die 的物理映射图（默认 SVG 矢量）。

每颗 die 一张图：
  - 内部棋盘格虚线；
  - 四边按方案端口粒度排布物理端口（CLOS：每条逻辑链路 b 占 1 个端口；同构 die 每方向预留 C 个）；
  - 片上走线：边↔边 / switch↔边，颜色区分 feedthrough、L1/L2/L3 相关走线与直连。

DSL 相关方案：s1 DSL XY、s2 DSL 最短路径、s3 DSL+直连（x=0/5/10）。
方案三图 = 方案二 CLOS 路径 + 本文件直连路径。
输出：figs/die_map/<scheme>_<n>x<n>/die_XX.svg（可用 --format pdf）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "output" / "mapping"
OUT = ROOT / "figs" / "die_map"
sys.path.insert(0, str(ROOT.parent))
import dsl_mesh_400t as M  # noqa: E402

for _f in ("/System/Library/Fonts/STHeiti Medium.ttc", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(_f):
        font_manager.fontManager.addfont(_f)
plt.rcParams["font.family"] = ["Heiti SC", "Arial Unicode MS", "sans-serif"]
plt.rcParams["axes.unicode_minus"] = False

# 走线类型 → 颜色
WIRE_STYLE = {
    "ft": ("#bc4749", "Feedthrough（过路）"),
    "L1_out": ("#2a6f97", "L1 → SIO"),
    "L2_in": ("#48a9a6", "SIO → L2"),
    "L2_out": ("#6a994e", "L2 → SIO"),
    "L3_in": ("#7b2cbf", "SIO → L3"),
    "L1_L2_local": ("#577590", "L1 → L2（片内）"),
    "L2_L3_local": ("#43aa8b", "L2 → L3（片内）"),
    "L1_L3_direct": ("#e07a1f", "L1 → L3 直连"),
    "L1_L3_local": ("#f4a261", "L1 → L3（片内直连）"),
}

DIRS = ("N", "E", "S", "W")
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
DIR_VEC = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}

# 棋盘与布局（归一化坐标，die 本体 [0,1]×[0,1]）
PAD = 0.08  # 边端口条带厚度
SW = {  # switch 模块中心
    "L1": (0.28, 0.55),
    "L2": (0.50, 0.55),
    "L3": (0.72, 0.55),
}

LINK_RE = re.compile(
    r"^(?P<link>\S+)\s+(?P<src>\d+)\s+(?P<dst>\d+)\s+(?P<hops>\d+)\s+(?P<turns>\d+)\s+"
    r"(?P<wm>[-+]?\d*\.?\d+)\s+(?P<wx>[-+]?\d*\.?\d+)\s+(?P<lat>[-+]?\d*\.?\d+)\s+"
    r"(?P<path>\d+\(\d+,\d+\)(?:\s*->\s*\d+\(\d+,\d+\))*)"
)
PATH_NODE_RE = re.compile(r"(\d+)\((\d+),(\d+)\)")
HEADER_C_RE = re.compile(r"最热有向边\s+(\d+(?:\.\d+)?)\s*(?:条\s*=\s*)?(\d+(?:\.\d+)?)?\s*Tbps")
HEADER_B_RE = re.compile(r"每条(?:逻辑链路|)\s+(\d+(?:\.\d+)?)\s*Tbps")
HEADER_N_RE = re.compile(r"(\d+)x(\d+)\s+2D Mesh")


# ------------------------------------------------------------------ parse


def parse_path(s: str) -> list[tuple[int, int, int]]:
    """返回 [(die_id, r, c), ...]。"""
    return [(int(a), int(b), int(c)) for a, b, c in PATH_NODE_RE.findall(s)]


def parse_link_kind(link: str) -> tuple[str, str, str]:
    """返回 (kind, src_sw, dst_sw)。kind ∈ {clos, direct, local_direct}。"""
    base = link.split("(")[0]
    m = re.match(r"(L[123]|die)_?(\d+)->(L[123]|die)_?(\d+)", base)
    if not m:
        return "clos", "L1", "L2"
    a, _, b, _ = m.groups()
    if a == "die":
        return "o1t", "R", "R"
    if a == "L1" and b == "L3":
        return ("local_direct" if "(片内)" in link else "direct"), "L1", "L3"
    return "clos", a, b


def edge_dir(a: tuple[int, int], b: tuple[int, int]) -> str:
    if a[0] == b[0]:
        return "E" if b[1] > a[1] else "W"
    return "S" if b[0] > a[0] else "N"


def parse_log(path: Path) -> dict:
    text = path.read_text()
    lines = text.splitlines()
    n = None
    b = None
    C_count = None
    C_tbps = None
    title = lines[0].lstrip("# ").strip() if lines else path.stem
    for ln in lines[:12]:
        m = HEADER_N_RE.search(ln)
        if m:
            n = int(m.group(1))
        m = HEADER_B_RE.search(ln)
        if m:
            b = float(m.group(1))
        m = HEADER_C_RE.search(ln)
        if m:
            # "56 条 = 89.6 Tbps" 或 "56.0 Tbps"
            if m.group(2):
                C_count = int(float(m.group(1)))
                C_tbps = float(m.group(2))
            else:
                C_tbps = float(m.group(1))
    records = []
    stage = None
    for ln in lines:
        if ln.startswith("## stage"):
            stage = 1 if "L1" in ln and "L2" in ln else 2
            continue
        if ln.startswith("#") or not ln.strip():
            continue
        m = LINK_RE.match(ln.strip())
        if not m:
            continue
        g = m.groupdict()
        link = g["link"]
        kind, src_sw, dst_sw = parse_link_kind(link)
        nodes = parse_path(g["path"])
        st = stage
        if kind in ("direct", "local_direct"):
            st = 0
        elif st is None and src_sw == "L1" and dst_sw == "L2":
            st = 1
        elif st is None and src_sw == "L2" and dst_sw == "L3":
            st = 2
        records.append(dict(
            link=link, kind=kind, src_sw=src_sw, dst_sw=dst_sw, stage=st,
            src=int(g["src"]), dst=int(g["dst"]), hops=int(g["hops"]),
            nodes=nodes, path_rc=[(r, c) for _, r, c in nodes],
        ))
    if n is None:
        raise ValueError(f"cannot parse mesh size from {path}")
    if b is None:
        b = M.SYSTEM_TBPS / (n * n) / (n * n)
    if C_count is None and C_tbps is not None:
        C_count = int(round(C_tbps / b))
    if C_count is None:
        C_count = 0
    if C_tbps is None:
        C_tbps = C_count * b
    return dict(title=title, n=n, b=b, C=C_count, C_tbps=C_tbps, records=records, path=path)


def merge_s3(clos: dict, direct: dict) -> dict:
    """方案三 = 方案二 CLOS + 直连；C 取直连叠加后的最热边。"""
    return dict(
        title=direct["title"],
        n=clos["n"],
        b=clos["b"],
        C=direct["C"] or clos["C"],
        C_tbps=direct["C_tbps"] or clos["C_tbps"],
        records=clos["records"] + direct["records"],
        path=direct["path"],
        clos_path=clos["path"],
    )


# ------------------------------------------------------------------ on-die segments


def _face_sort_key(face: str, x: float, y: float) -> tuple[float, float]:
    """对端点在 face 上的排序键：与 port_xy 的 t 增大方向一致 → 排序后无交叉。"""
    if face == "N":
        return (x, y)          # t↑ = x↑
    if face == "S":
        return (x, -y)         # t↑ = x↑
    if face == "E":
        return (-y, x)         # t↑ = y↓；y 相同时按 x 分 L1/L2/L3
    return (-y, -x)            # W: t↑ = y↓


FACE_CENTER = {"N": (0.5, 1.0), "S": (0.5, 0.0), "E": (1.0, 0.5), "W": (0.0, 0.5)}


def order_edge_ports(segs: dict[int, list[dict]], n: int, C: int) -> None:
    """按有向边统一重排端口号：A 出 #k 与 B 入 #k 是同一条链路（两侧共用一个序号）。

    排序键 = (A 侧对端在出边上的投影, B 侧对端在入边上的投影, rid)，
    同一类对端连续成块；配合 port_xy 的镜像半区排布，相邻 die 端口一一对齐、不交叉。
    """
    def other_key(face: str, s: dict, end: str) -> tuple:
        other = s["b"] if end == "a" else s["a"]
        xy = sw_xy(other[1]) if other[0] == "sw" else FACE_CENTER[other[1]]
        return _face_sort_key(face, *xy)

    def nb(did: int, face: str) -> int:
        dr, dc = DIR_VEC[face]
        return did + dr * n + dc

    keys: dict[tuple[int, int], dict[int, list]] = defaultdict(lambda: defaultdict(lambda: [None, None, 0]))
    refs = []
    for did, sl in segs.items():
        for s in sl:
            for end in ("a", "b"):
                ep = s[end]
                if ep[0] != "port":
                    continue
                face, idx = ep[1], ep[2]
                if idx < C:
                    edge, p, slot = (did, nb(did, face)), idx, 0
                else:
                    edge, p, slot = (nb(did, face), did), idx - C, 1
                k = keys[edge][p]
                k[slot] = other_key(face, s, end)
                k[2] = s["rid"]
                refs.append((s, end, edge, p, idx >= C))
    perm: dict[tuple[int, int], dict[int, int]] = {}
    for edge, d in keys.items():
        order = sorted(d.items(), key=lambda kv: (kv[1][0] or (), kv[1][1] or (), kv[1][2]))
        perm[edge] = {p: i for i, (p, _) in enumerate(order)}
    for s, end, edge, p, is_in in refs:
        face = s[end][1]
        q = perm[edge][p]
        s[end] = ("port", face, q + C if is_in else q)


def die_segments_v2(rec: dict) -> dict[int, list[dict]]:
    """把每条逻辑路径展开为各 die 上的片上走线段，并为有向边占用分配端口序号。

    每边同构预留 C 个出端口 + C 个入端口（逻辑编号出 [0,C)、入 [C,2C)）；
    随后按对端几何重排，保证四边端口走线无交叉。
    """
    segs: dict[int, list[dict]] = defaultdict(list)
    edge_port: dict[tuple[int, int], int] = defaultdict(int)
    C = max(rec["C"], 1)

    def take(a_id: int, b_id: int) -> int:
        k = (a_id, b_id)
        p = edge_port[k]
        edge_port[k] = p + 1
        return p

    for rid, r in enumerate(rec["records"]):
        nodes = r["nodes"]
        kind, src_sw, dst_sw = r["kind"], r["src_sw"], r["dst_sw"]
        if len(nodes) == 1:
            did = nodes[0][0]
            if kind in ("local_direct",) or (src_sw == "L1" and dst_sw == "L3"):
                wtype = "L1_L3_local"
            elif src_sw == "L1":
                wtype = "L1_L2_local"
            else:
                wtype = "L2_L3_local"
            segs[did].append(dict(wtype=wtype, a=("sw", src_sw), b=("sw", dst_sw),
                                  link=r["link"], rid=rid))
            continue

        ports = [take(nodes[i][0], nodes[i + 1][0]) for i in range(len(nodes) - 1)]

        for i, (a_id, ar, ac) in enumerate(nodes):
            if i == 0:
                br, bc = nodes[1][1], nodes[1][2]
                d_out = edge_dir((ar, ac), (br, bc))
                if kind == "direct":
                    wtype = "L1_L3_direct"
                elif src_sw == "L1":
                    wtype = "L1_out"
                else:
                    wtype = "L2_out"
                segs[a_id].append(dict(wtype=wtype, a=("sw", src_sw),
                                       b=("port", d_out, ports[0]),
                                       link=r["link"], rid=rid))
            elif i == len(nodes) - 1:
                pr, pc = nodes[i - 1][1], nodes[i - 1][2]
                d_in = edge_dir((ar, ac), (pr, pc))
                if kind == "direct":
                    wtype = "L1_L3_direct"
                elif dst_sw == "L3":
                    wtype = "L3_in"
                else:
                    wtype = "L2_in"
                segs[a_id].append(dict(wtype=wtype,
                                       a=("port", d_in, ports[i - 1] + C),
                                       b=("sw", dst_sw), link=r["link"], rid=rid))
            else:
                pr, pc = nodes[i - 1][1], nodes[i - 1][2]
                nr, nc = nodes[i + 1][1], nodes[i + 1][2]
                d_in = edge_dir((ar, ac), (pr, pc))
                d_out = edge_dir((ar, ac), (nr, nc))
                segs[a_id].append(dict(wtype="ft",
                                       a=("port", d_in, ports[i - 1] + C),
                                       b=("port", d_out, ports[i]),
                                       link=r["link"], rid=rid))
    order_edge_ports(segs, rec["n"], C)
    rec["edge_port_used"] = dict(edge_port)
    rec["max_port_used"] = max(edge_port.values()) if edge_port else 0
    return segs


# ------------------------------------------------------------------ geometry


def port_xy(face: str, idx: int, n_ports: int, span: int | None = None) -> tuple[float, float]:
    """端口中心坐标；逻辑编号 idx∈[0,2C)，C=n_ports/2。

    出、入各占一个连续半区，不交错；E/S 出在前半，W/N 入在前半（镜像），
    使 A 的 E 出 #k 与东邻 W 入 #k、A 的 S 出 #k 与南邻 N 入 #k 同位置对齐。
    span 保留兼容（忽略）。
    """
    C = max(n_ports // 2, 1)
    is_in = idx >= C
    k = idx % C
    first_half = (not is_in) if face in ("E", "S") else is_in
    u = (k + 0.5) / (2 * C) + (0.0 if first_half else 0.5)
    # 端口只占边的中段 [PAD, 1-PAD]，四角留空，避免两边端口在角上重叠
    t = PAD + (1.0 - 2 * PAD) * u
    t = min(max(t, 0.0), 1.0)
    d = PAD / 2  # 居中于端口条带
    if face == "N":
        return t, 1.0 - d
    if face == "S":
        return t, d
    if face == "W":
        return d, 1.0 - t
    return 1.0 - d, 1.0 - t


def sw_xy(name: str, jitter: float = 0.0) -> tuple[float, float]:
    x, y = SW.get(name, (0.5, 0.5))
    return x + jitter, y


def endpoint_xy(ep, n_ports: int, face_span: dict | None = None) -> tuple[float, float]:
    if ep[0] == "sw":
        return sw_xy(ep[1])
    # ("port", face, idx)
    span = face_span.get(ep[1]) if face_span else None
    return port_xy(ep[1], ep[2], n_ports, span=span)


def curve_points(p0, p1, bend: float = 0.18, steps: int = 24):
    """二次贝塞尔：控制点取中点并向垂直方向偏移，避免直线重叠。"""
    x0, y0 = p0
    x1, y1 = p1
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    # 垂直单位向量
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    ox, oy = -dy / L * bend, dx / L * bend
    # 按端点哈希决定弯曲方向，使同向线错开
    sign = 1.0 if (hash((round(x0, 3), round(y0, 3), round(x1, 3), round(y1, 3))) & 1) else -1.0
    cx, cy = mx + sign * ox, my + sign * oy
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * x0 + 2 * u * t * cx + t * t * x1,
                    u * u * y0 + 2 * u * t * cy + t * t * y1))
    return pts


# ------------------------------------------------------------------ draw


def _face_usage(n: int, die_id: int, rec: dict):
    C = max(rec["C"], 1)
    face_out = {d: 0 for d in DIRS}
    face_in = {d: 0 for d in DIRS}
    for (a, b), cnt in rec.get("edge_port_used", {}).items():
        ar, ac = divmod(a, n)
        br, bc = divmod(b, n)
        if a == die_id:
            face_out[edge_dir((ar, ac), (br, bc))] += cnt
        if b == die_id:
            face_in[edge_dir((br, bc), (ar, ac))] += cnt
    return C, face_out, face_in


def render_die_ax(ax, n: int, die_id: int, rec: dict, segs: list[dict], *, mini: bool = False) -> dict:
    """在给定 ax 上绘制单颗 die 的物理映射；返回各走线类型计数。

    同构 die：四边均按 C 出 + C 入预留（与构型图 SIO 每方向一致）；
    实际占用高亮，未占用保留浅色槽位；无邻居边上占用为 0 但仍显示预留。
    """
    C, face_out, face_in = _face_usage(n, die_id, rec)
    n_ports = 2 * C
    n_wires = max(len(segs), 1)
    dense = n_wires > 80 or n_ports > 80 or mini
    lw = 0.25 if mini else (0.35 if dense else (0.7 if n_wires > 30 else 1.1))
    alpha_ft = 0.10 if mini else (0.14 if dense else 0.35)
    alpha_io = 0.40 if mini else (0.50 if dense else 0.75)

    ax.set_xlim(-0.08, 1.08)
    ax.set_ylim(-0.08, 1.08)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), 1, 1, fill=False, ec="#1F3B5C", lw=1.2 if mini else 2.0, zorder=5))

    n_cell = 4 if mini else (8 if n_ports <= 64 else 12)
    for i in range(n_cell):
        for j in range(n_cell):
            if (i + j) % 2 == 0:
                ax.add_patch(Rectangle((i / n_cell, j / n_cell), 1 / n_cell, 1 / n_cell,
                                       fc="#f4f7fb", ec="none", zorder=0))
    for i in range(1, n_cell):
        t = i / n_cell
        ax.plot([t, t], [0, 1], ls=(0, (2, 2)), lw=0.4, color="#c5cdd6", zorder=0)
        ax.plot([0, 1], [t, t], ls=(0, (2, 2)), lw=0.4, color="#c5cdd6", zorder=0)

    # 同构：四边 C 出+C 入。占用端口必须逐点画出（否则 8×8 上 step≈C/48
    # 会漏掉 ~90% 占用点，走线落点对不齐标记 → 端口数量/连接关系误判）；
    # 未占用预留槽再抽样浅色点缀。
    for face in DIRS:
        span = 1 - 2 * PAD
        if face == "N":
            ax.add_patch(Rectangle((PAD, 1 - PAD), span, PAD, fc="#f6e7d8", ec="#e07a1f", lw=0.6, zorder=2))
        elif face == "S":
            ax.add_patch(Rectangle((PAD, 0), span, PAD, fc="#f6e7d8", ec="#e07a1f", lw=0.6, zorder=2))
        elif face == "W":
            ax.add_patch(Rectangle((0, PAD), PAD, span, fc="#f6e7d8", ec="#e07a1f", lw=0.6, zorder=2))
        else:
            ax.add_patch(Rectangle((1 - PAD, PAD), PAD, span, fc="#f6e7d8", ec="#e07a1f", lw=0.6, zorder=2))
        used_out_n = face_out[face]
        used_in_n = face_in[face]
        ms_used = 0.9 if mini else (1.2 if dense else 2.2)
        used_step = 2 if (mini and (used_out_n + used_in_n) > 200) else 1
        pts = []
        for s in segs:
            for end in ("a", "b"):
                ep = s[end]
                if ep[0] == "port" and ep[1] == face:
                    pts.append(port_xy(face, ep[2], n_ports))
        for i, (x, y) in enumerate(pts):
            if i % used_step:
                continue
            ax.plot([x], [y], marker="s", ms=ms_used, color="#c45c26", zorder=4)
        # 未占用预留：浅色点缀（出、入两个半区）
        unused_step = max(1, C // (16 if mini else 32))
        ms_free = 0.7 if mini else 1.0
        for k in range(0, n_ports, unused_step):
            x, y = port_xy(face, k, n_ports)
            ax.plot([x], [y], marker="s", ms=ms_free, color="#e8d5c4", zorder=3)

    for name, (sx, sy) in SW.items():
        bw, bh = (0.10, 0.08) if mini else (0.14, 0.11)
        ax.add_patch(FancyBboxPatch((sx - bw / 2, sy - bh / 2), bw, bh,
                                    boxstyle="round,pad=0.01", fc="#dbe7f4", ec="#1F3B5C",
                                    lw=0.9 if mini else 1.2, zorder=6))
        ax.text(sx, sy, name, ha="center", va="center",
                fontsize=6 if mini else 9, fontweight="bold", zorder=7)

    by_type: dict[str, list] = defaultdict(list)
    for s in segs:
        p0 = endpoint_xy(s["a"], n_ports)
        p1 = endpoint_xy(s["b"], n_ports)
        has_port = s["a"][0] == "port" or s["b"][0] == "port"
        bend = (0.02 if has_port else 0.08) if mini else (0.04 if has_port else 0.14)
        by_type[s["wtype"]].append(curve_points(p0, p1, bend=bend, steps=8 if mini else 16))
    # FT 垫底降透明，IO 走线在上（不抽样，保留完整连接关系）
    for wtype, segs_xy in by_type.items():
        col = WIRE_STYLE.get(wtype, ("#333", ""))[0]
        is_ft = wtype == "ft"
        ax.add_collection(LineCollection(
            segs_xy, colors=col,
            linewidths=(lw * 0.75 if is_ft else lw),
            alpha=(alpha_ft if is_ft else alpha_io),
            zorder=(2 if is_ft else 3),
        ))

    counts = defaultdict(int)
    for s in segs:
        counts[s["wtype"]] += 1
    rr, cc = divmod(die_id, n)
    if mini:
        # 出/入分列写清，避免 "224/288" 被读成单池且 sum>C 像超额
        for face, pos in {"N": (0.5, 1.03), "S": (0.5, -0.04), "W": (-0.05, 0.5), "E": (1.05, 0.5)}.items():
            ax.text(*pos, f"{face}↑{face_out[face]} ↓{face_in[face]}",
                    ha="center", va="center", fontsize=5.0, color="#7a4a2a",
                    rotation=90 if face in ("W", "E") else 0, zorder=8)
    ax.set_title(f"die {die_id} ({rr},{cc})  ·  {n_wires} 条", fontsize=7 if mini else 10, pad=2)
    return counts


def draw_die(n: int, die_id: int, rec: dict, segs: list[dict], out_path: Path) -> None:
    C = max(rec["C"], 1)
    n_ports = 2 * C
    fig_w = 8.2 if n_ports <= 64 else 9.5
    fig, ax = plt.subplots(figsize=(fig_w, fig_w * 0.92))
    counts = render_die_ax(ax, n, die_id, rec, segs, mini=False)
    # 同构四边：出、入各有独立预留 C（出+入可达 2C，不是单池 C）
    _, face_out, face_in = _face_usage(n, die_id, rec)
    for face, pos in {"N": (0.5, 1.04), "S": (0.5, -0.05), "W": (-0.06, 0.5), "E": (1.06, 0.5)}.items():
        ax.text(*pos, f"{face} 出{face_out[face]}/{C} 入{face_in[face]}/{C}",
                ha="center", va="center", fontsize=7.0, color="#7a4a2a",
                rotation=90 if face in ("W", "E") else 0)
    rr, cc = divmod(die_id, n)
    ax.set_title(
        f"{rec['title']}\ndie {die_id}  ({rr},{cc})    端口粒度 b={rec['b']:g}T，"
        f"每边出/入各预留 C={rec['C']}（{rec['C_tbps']:.1f}T）    片上走线 {sum(counts.values())} 条",
        fontsize=10, pad=8,
    )
    handles = [Line2D([0], [0], color=col, lw=2.0, label=f"{lab} ×{counts[wtype]}")
               for wtype, (col, lab) in WIRE_STYLE.items() if counts.get(wtype)]
    if handles:
        ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.14),
                  ncol=min(3, len(handles)), fontsize=7.5, frameon=False)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fmt = out_path.suffix.lstrip(".").lower() or "svg"
    fig.savefig(out_path, format=fmt, bbox_inches="tight",
                metadata={"Creator": "figs_die_map.py"} if fmt == "pdf" else None)
    plt.close(fig)


def fig_overview(stem: str, n: int, rec: dict, all_segs: dict, out_png: Path) -> Path:
    """die 映射总览（报告嵌入用 PNG）。

    4×4：全 16 颗（邻格=真实邻 die）。
    8×8：取左上连续 3×3 子阵列（同样邻格相邻），避免抽样角/边/中心导致
    图上相邻格并非 mesh 邻居、跨边出/入对不上（连接关系误判）。
    """
    if n <= 4:
        rows = cols = n
        die_grid = [[r * n + c for c in range(n)] for r in range(n)]
        note = "每格一颗 die（全阵列；邻格=真实邻 die）"
    else:
        rows = cols = 3
        # 连续子阵列：图上左右/上下邻格即 mesh 邻居，可对核对出/入
        r0, c0 = 0, 0
        die_grid = [[(r0 + rr) * n + (c0 + cc) for cc in range(cols)] for rr in range(rows)]
        note = (f"连续 3×3 子阵列 die({r0}:{r0 + rows - 1},{c0}:{c0 + cols - 1})"
                f"（邻格=真实邻 die，跨边出=对侧入；全 {n * n} 颗见 figs/die_map/）")
    fig, axes = plt.subplots(rows, cols, figsize=(4.2 * cols, 4.4 * rows + 0.8))
    if rows == 1 and cols == 1:
        axes = [[axes]]
    elif rows == 1:
        axes = [axes]
    for i in range(rows):
        for j in range(cols):
            die_id = die_grid[i][j]
            render_die_ax(axes[i][j], n, die_id, rec, all_segs.get(die_id, []), mini=True)
    handles = [Line2D([0], [0], color=col, lw=2.0, label=lab) for _, (col, lab) in WIRE_STYLE.items()]
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=8, frameon=False,
               bbox_to_anchor=(0.5, 0.005))
    fig.suptitle(
        f"{rec['title']}  —  映射可视化（粒度 b={rec['b']:g}T，同构 die 四边出/入各预留 C={rec['C']}×{rec['b']:g}T）\n"
        f"{note}：深色=实际占用，浅色=预留未用；走线按逻辑链路映射",
        fontsize=11, y=0.995,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 0.96))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out_png


# ------------------------------------------------------------------ schemes / main


DSL_SCHEMES = (
    ("s1_dsl_xy", None),
    ("s2_dsl_shortest", None),
    ("s3_l1l3_direct_x0", "s2_dsl_shortest"),
    ("s3_l1l3_direct_x5", "s2_dsl_shortest"),
    ("s3_l1l3_direct_x10", "s2_dsl_shortest"),
)


def load_scheme(stem: str, n: int, clos_stem: str | None) -> dict:
    path = MAP / f"{stem}_{n}x{n}.log"
    if not path.exists():
        raise FileNotFoundError(path)
    rec = parse_log(path)
    if clos_stem:
        clos = parse_log(MAP / f"{clos_stem}_{n}x{n}.log")
        rec = merge_s3(clos, rec)
    return rec


# 报告嵌入的总览图（方案一 / 二 / 三 x=10%）
OVERVIEW_STEMS = ("s1_dsl_xy", "s2_dsl_shortest", "s3_l1l3_direct_x10")
FIG_ROOT = ROOT / "figs"


def run(sizes=(4, 8), schemes=None, dies=None, fmt: str = "svg",
        overview: bool = True) -> list[Path]:
    fmt = fmt.lower().lstrip(".")
    if fmt not in ("svg", "pdf"):
        raise ValueError(f"vector format must be svg or pdf, got {fmt}")
    want = set(schemes) if schemes else {s for s, _ in DSL_SCHEMES}
    written: list[Path] = []
    for n in sizes:
        for stem, clos in DSL_SCHEMES:
            if stem not in want:
                continue
            print(f"== {stem} {n}x{n} ({fmt}) ==")
            rec = load_scheme(stem, n, clos)
            all_segs = die_segments_v2(rec)
            N = n * n
            die_list = list(range(N)) if dies is None else [d for d in dies if 0 <= d < N]
            out_dir = OUT / f"{stem}_{n}x{n}"
            out_dir.mkdir(parents=True, exist_ok=True)
            for old in out_dir.glob("die_*.png"):
                old.unlink()
            for d in die_list:
                fn = out_dir / f"die_{d:02d}.{fmt}"
                draw_die(n, d, rec, all_segs.get(d, []), fn)
                written.append(fn)
            if overview and stem in OVERVIEW_STEMS and dies is None:
                ov = FIG_ROOT / f"fig_die_map_{stem}_{n}x{n}.png"
                fig_overview(stem, n, rec, all_segs, ov)
                written.append(ov)
                print(f"  overview → {ov.relative_to(ROOT)}")
            idx = out_dir / "README.txt"
            idx.write_text(
                f"{rec['title']}\n"
                f"mesh {n}x{n}, b={rec['b']:g}T, C={rec['C']} ({rec['C_tbps']:.1f}T)\n"
                f"source log: {rec['path'].name}"
                + (f" + {rec['clos_path'].name}" if rec.get("clos_path") else "")
                + f"\nfigures: die_00.{fmt} … die_{N - 1:02d}.{fmt}  ({len(die_list)} files, vector)\n"
                f"port granularity: 1 port = 1 logical link = {rec['b']:g} Tbps; "
                f"each side provisioned with C out + C in = {2 * rec['C']} ports "
                f"(homogeneous die, C={rec['C']}).\n"
                + (f"report overview: figs/fig_die_map_{stem}_{n}x{n}.png\n"
                   if stem in OVERVIEW_STEMS else "")
            )
            print(f"  wrote {len(die_list)} dies → {out_dir.relative_to(ROOT)}")
    return written


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--schemes", nargs="+", default=None,
                    help="subset, e.g. s1_dsl_xy s2_dsl_shortest s3_l1l3_direct_x10")
    ap.add_argument("--dies", type=int, nargs="+", default=None, help="subset of die ids")
    ap.add_argument("--format", choices=("svg", "pdf"), default="svg",
                    help="vector output format (default: svg)")
    ap.add_argument("--no-overview", action="store_true", help="skip report overview PNGs")
    args = ap.parse_args()
    run(sizes=tuple(args.sizes), schemes=args.schemes, dies=args.dies,
        fmt=args.format, overview=not args.no_overview)


if __name__ == "__main__":
    main()
