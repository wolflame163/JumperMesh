#!/usr/bin/env python3
"""Build a self-contained HTML report comparing none/single/dual/quad/full jumper topologies."""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

FIGS = [
    ("topology_3d", "3D 拓扑：NOW + 跳线层"),
    ("mesh3d_200g_ports", "有向 200G 端口总图（负载着色）"),
    ("loads_now", "NOW 层有向负载"),
    ("loads_jumper", "跳线层有向负载"),
    ("loads_vertical", "NOW↔跳线垂直负载"),
]

TOPO_META = {
    "none": {
        "label": "none（基准：无跳线层）",
        "windows": "—（仅 NOW）",
        "n_meshes": 0,
    },
    "single": {
        "label": "single（默认单窗）",
        "windows": "(2,2)–(5,7)",
        "n_meshes": 1,
    },
    "dual": {
        "label": "dual（双 Mesh）",
        "windows": "(0,2)–(3,7) + (4,2)–(7,7)",
        "n_meshes": 2,
    },
    "quad": {
        "label": "quad（四 Mesh）",
        "windows": "(0,0)–(3,4) + (0,5)–(3,9) + (4,0)–(7,4) + (4,5)–(7,9)",
        "n_meshes": 4,
    },
    "full": {
        "label": "full（NOW 镜像全铺）",
        "windows": "NOW-mirror（全 floorplan，同 die/邻接）",
        "n_meshes": 1,
    },
}

FIGS_BASELINE = [
    ("topology_3d", "3D 拓扑：仅 NOW 层（无跳线）"),
    ("mesh3d_200g_ports", "有向 200G 端口总图（负载着色）"),
    ("loads_now", "NOW 层有向负载"),
]


def fig_html(stem: str, caption: str, base: Path) -> str:
    png = base / f"{stem}.png"
    svg = base / f"{stem}.svg"
    if png.exists() and png.stat().st_size > 1000:
        b64 = base64.b64encode(png.read_bytes()).decode("ascii")
        img = f'<img src="data:image/png;base64,{b64}" alt="{caption}"/>'
    elif svg.exists():
        raw = svg.read_text(encoding="utf-8")
        raw = re.sub(r"<\?xml[^>]*\?>", "", raw).strip()
        raw = re.sub(r'\swidth="[^"]*"', ' width="100%"', raw, count=1)
        raw = re.sub(r'\sheight="[^"]*"', "", raw, count=1)
        img = f'<div class="svg-wrap">{raw}</div>'
    else:
        img = f'<p class="muted">（缺少图文件 {stem}）</p>'
    return f"<figure><figcaption>{caption}</figcaption>{img}</figure>"


def hist_svg(hist: dict, title: str = "路径时延直方图（ns → count）") -> str:
    keys = sorted(int(k) for k in hist)
    counts = [hist[str(k)] if str(k) in hist else hist[k] for k in keys]
    maxc = max(counts) if counts else 1
    w, h, pad = 920, 220, 36
    usable_w = w - 2 * pad
    usable_h = h - 2 * pad - 20
    n = max(1, len(keys))
    bw = usable_w / n
    bars = []
    for i, (k, c) in enumerate(zip(keys, counts)):
        bh = usable_h * c / maxc
        x = pad + i * bw
        y = pad + 10 + (usable_h - bh)
        bars.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(0.5, bw * 0.85):.2f}" '
            f'height="{bh:.2f}" fill="#2a6f8f"/>'
        )
    labels = []
    if keys:
        for k in (keys[0], keys[len(keys) // 2], keys[-1]):
            i = keys.index(k)
            x = pad + i * bw + bw / 2
            labels.append(
                f'<text x="{x:.1f}" y="{h - 8}" text-anchor="middle" '
                f'font-size="11" fill="#444">{k}</text>'
            )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="100%" role="img" aria-label="delay histogram">'
        f'<rect width="{w}" height="{h}" fill="#f7f5f0"/>'
        f'<text x="{pad}" y="18" font-size="13" font-weight="700" fill="#222">'
        f"{title}</text>"
        f"{''.join(bars)}{''.join(labels)}</svg>"
    )


def load_topo(best_dir: Path, sweep_path: Path, topo: str) -> Dict[str, Any]:
    m = json.loads((best_dir / "mapping3d.json").read_text(encoding="utf-8"))
    s = json.loads(
        (best_dir / "logical_edge_routes_summary.json").read_text(encoding="utf-8")
    )
    sweep = (
        json.loads(sweep_path.read_text(encoding="utf-8")) if sweep_path.exists() else []
    )
    maxd = s.get("max_path_delay_ns", m.get("max_path_delay_ns"))
    n_at = m.get("n_at_max")
    if n_at is None:
        n_at = s.get("n_at_max")
    longest: List[dict] = []
    jl = best_dir / "logical_edge_routes.jsonl"
    hop_max = m.get("max_hop_delay_ns") or s.get("max_hop_delay_ns")
    if jl.exists():
        with jl.open(encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("path_delay_ns") is None:
                    continue
                # show longest single-hop edges (L1-L2 / L2-L3 commodities)
                ref = hop_max if hop_max is not None else maxd / 2.0
                if abs(r["path_delay_ns"] - ref) < 1e-9:
                    if len(longest) < 6:
                        longest.append(r)
    if n_at is None:
        n_at = 0
        for row in sweep:
            if row.get("seed") == m.get("seed") and row.get("n_at_max") is not None:
                n_at = row["n_at_max"]
                break
    mesh = m.get("mesh") or {}
    return {
        "topo": topo,
        "meta": TOPO_META[topo],
        "dir": best_dir,
        "m": m,
        "s": s,
        "sweep": sweep,
        "hist": s.get("delay_histogram_ns", {}),
        "n_at_max": n_at,
        "longest": longest,
        "windows_label": mesh.get("jumper_windows_label")
        or TOPO_META[topo]["windows"],
        "n_jumper": mesh.get("n_jumper") or 0,
        "n_edges_jumper": mesh.get("n_edges_jumper") or 0,
        "n_meshes": mesh.get("n_jumper_meshes", TOPO_META[topo]["n_meshes"]) or 0,
    }


def fmt_path(path: Sequence) -> str:
    return " → ".join(f"{'N' if z == 0 else 'J'}({rr},{c})" for z, rr, c in path)


def topo_section(t: Dict[str, Any]) -> str:
    m, s, topo = t["m"], t["s"], t["topo"]
    meta = t["meta"]
    manh_pct = 100.0 * m["n_manhattan"] / max(1, m["n_manhattan"] + m["n_non_manhattan"])
    ncap = m.get("now_capacity_links", 350)
    jcap = m.get("jumper_capacity_links", 180)
    vcap = m.get("vertical_capacity_links", 250)
    now_max = m.get("now_max_load", "—")
    is_baseline = topo == "none"
    fig_list = FIGS_BASELINE if is_baseline else FIGS
    figs = "\n".join(
        fig_html(stem, f"[{topo}] {cap}", t["dir"]) for stem, cap in fig_list
    )
    hist = hist_svg(t["hist"], title=f"[{topo}] L1–L3 端到端时延直方图（ns → count）")
    hop_max = m.get("max_hop_delay_ns")
    hop_cell = f"{hop_max:.0f} ns" if hop_max is not None else "—"
    sweep_rows = "\n".join(
        (
            f"<tr{' class=\"best\"' if r['seed'] == m.get('seed') else ''}>"
            f"<td>{r['seed']}</td><td>{r['max_path_delay_ns']:.0f}</td>"
            f"<td>{r['n_at_max']}</td><td>{r['C']}</td>"
            f"<td>{r['latency_max_ns']:.0f}</td>"
            f"<td>{r.get('now_max_load','—')}</td>"
            f"<td>{r.get('jumper_max_load','—')}</td>"
            f"<td>{r.get('vertical_max_load','—')}</td>"
            f"<td>{r['power_W']:.1f}</td></tr>"
        )
        for r in t["sweep"]
    )
    long_rows = "\n".join(
        (
            f"<tr><td>{r['stage']}</td>"
            f"<td>SSC{r['src_ssc']}@({r['src_pos'][1]},{r['src_pos'][2]})</td>"
            f"<td>SSC{r['dst_ssc']}@({r['dst_pos'][1]},{r['dst_pos'][2]})</td>"
            f"<td>{r['path_delay_ns']:.0f}</td>"
            f"<td>{'Y' if r.get('is_manhattan') else 'N'}</td>"
            f"<td class=\"path\">{fmt_path(r['path'])}</td></tr>"
        )
        for r in t["longest"]
    )
    jumper_kpi = (
        '<div class="kpi"><div class="v">—</div><div class="l">跳线(L1)（无）</div></div>'
        '<div class="kpi"><div class="v">—</div><div class="l">垂直（无）</div></div>'
        if is_baseline
        else (
            f'<div class="kpi"><div class="v">{m["jumper_max_load"]}/{jcap}</div>'
            f'<div class="l">跳线(L1) max / cap</div></div>'
            f'<div class="kpi"><div class="v">{m["vertical_max_load"]}/{vcap}</div>'
            f'<div class="l">垂直 max / cap</div></div>'
        )
    )
    win_line = (
        "物理拓扑：仅 NOW 层（无跳线 / 无垂直）"
        if is_baseline
        else (
            f"跳线窗口：<span class=\"mono\">{t['windows_label']}</span>"
            f" · 跳线节点 {t['n_jumper']} · 跳线无向边 {t['n_edges_jumper']}"
            f" · 独立 Mesh 数 {t['n_meshes']}"
        )
    )
    return f"""
<section id="topo-{topo}">
<h2>{meta['label']}：最优结果（seed={m.get('seed')}）</h2>
<p>{win_line}</p>
<div class="kpis">
  <div class="kpi"><div class="v">{m['max_path_delay_ns']:.0f} ns</div><div class="l">L1–L3 端到端最长时延</div></div>
  <div class="kpi"><div class="v">{hop_cell}</div><div class="l">单跳最长（L1-L2 / L2-L3）</div></div>
  <div class="kpi"><div class="v">{t['n_at_max']}</div><div class="l">L1–L3 最长档条数</div></div>
  <div class="kpi"><div class="v">{m['latency_max_ns']:.0f} ns</div><div class="l">单跳可行 latency_max</div></div>
  <div class="kpi"><div class="v">{m['C']}</div><div class="l">最大边负载 C</div></div>
  <div class="kpi"><div class="v">{now_max}/{ncap}</div><div class="l">NOW(L0) max / cap</div></div>
  {jumper_kpi}
  <div class="kpi"><div class="v">{manh_pct:.1f}%</div><div class="l">曼哈顿路径占比</div></div>
  <div class="kpi"><div class="v">{m['n_must_manhattan_ok']}/{m['n_must_manhattan']}</div><div class="l">必须曼哈顿达成</div></div>
  <div class="kpi"><div class="v">{m['total_data_movement_power_W']:.0f} W</div><div class="l">总数据搬移功耗</div></div>
</div>
<table>
  <thead><tr><th>指标</th><th>数值</th></tr></thead>
  <tbody>
    <tr><td>时延统计口径</td><td>L1→L2→L3 端到端（两段单跳之和）</td></tr>
    <tr><td>L1–L3 e2e 路径数</td><td>{m.get('n_e2e_paths', s.get('n_e2e_paths', '—'))}</td></tr>
    <tr><td>逻辑边数（单跳）</td><td>{s['n_edges']}</td></tr>
    <tr><td>曼哈顿 / 非曼哈顿</td><td>{m['n_manhattan']} / {m['n_non_manhattan']}</td></tr>
    <tr><td>总路径能耗 ΣE</td><td>{s['total_path_energy_pj_per_bit']:.2f} pJ/bit</td></tr>
    <tr><td>平均路径能耗</td><td>{s['avg_path_energy_pj_per_bit']:.3f} pJ/bit</td></tr>
  </tbody>
</table>
<figure><figcaption>[{topo}] L1–L3 时延直方图</figcaption>{hist}</figure>
{figs}
<h3>Seed 扫描（1–8）</h3>
<table>
  <thead>
    <tr><th>seed</th><th>L1–L3 max</th><th>n_at_max</th><th>C</th><th>latency_max</th>
    <th>NOW max</th><th>jumper max</th><th>vert max</th><th>power (W)</th></tr>
  </thead>
  <tbody>
{sweep_rows}
  </tbody>
</table>
<h3>最长单跳路径样例（构成 L1–L3 的一段）</h3>
<table>
  <thead><tr><th>stage</th><th>源</th><th>目的</th><th>delay</th><th>Manh</th><th>物理路径</th></tr></thead>
  <tbody>
{long_rows}
  </tbody>
</table>
</section>
"""


def build(
    topos: Sequence[Dict[str, Any]],
    out_path: Path,
) -> None:
    # comparison ordered by max delay
    ranked = sorted(
        topos,
        key=lambda t: (
            t["m"]["max_path_delay_ns"],
            t["n_at_max"],
            t["m"]["total_data_movement_power_W"],
        ),
    )
    best = ranked[0]
    # Prefer non-baseline as "highlighted best among jumper topos" for summary text,
    # but table still ranks all by delay (baseline last).
    jumper_ranked = [t for t in ranked if t["topo"] != "none"]
    best_jumper = jumper_ranked[0] if jumper_ranked else best
    baseline = next((t for t in topos if t["topo"] == "none"), None)

    def load_cell(t: Dict[str, Any], kind: str) -> str:
        if t["topo"] == "none" and kind != "now":
            return "—"
        if kind == "now":
            return f"{t['m'].get('now_max_load')} / {t['m'].get('now_capacity_links', 350)}"
        if kind == "jumper":
            return f"{t['m']['jumper_max_load']} / {t['m'].get('jumper_capacity_links', 180)}"
        return f"{t['m']['vertical_max_load']} / {t['m'].get('vertical_capacity_links', 250)}"

    cmp_rows = "\n".join(
        (
            f"<tr{' class=\"best\"' if t is best_jumper else ''}>"
            f"<td><strong>{t['topo']}</strong></td>"
            f"<td>{t['meta']['windows']}</td>"
            f"<td>{t['n_meshes']}</td>"
            f"<td>{t['n_jumper'] if t['topo'] != 'none' else 0}</td>"
            f"<td>{t['m']['max_path_delay_ns']:.0f}</td>"
            f"<td>{t['n_at_max']}</td>"
            f"<td>{t['m']['latency_max_ns']:.0f}</td>"
            f"<td>{t['m']['C']}</td>"
            f"<td>{load_cell(t, 'now')}</td>"
            f"<td>{load_cell(t, 'jumper')}</td>"
            f"<td>{load_cell(t, 'vert')}</td>"
            f"<td>{t['m']['total_data_movement_power_W']:.0f}</td>"
            f"<td>{t['m'].get('seed')}</td></tr>"
        )
        for t in ranked
    )
    topo_sections = "\n".join(topo_section(t) for t in topos)
    toc_topo = " ".join(
        f'<a href="#topo-{t["topo"]}">{t["topo"]}</a>' for t in topos
    )

    def delay_of(name: str) -> str:
        for t in topos:
            if t["topo"] == name:
                return f"{t['m']['max_path_delay_ns']:.0f}"
        return "—"

    d_none, d_single, d_dual, d_quad, d_full = (
        delay_of("none"),
        delay_of("single"),
        delay_of("dual"),
        delay_of("quad"),
        delay_of("full"),
    )
    p_none = next(
        (f"{t['m']['total_data_movement_power_W']:.0f}" for t in topos if t["topo"] == "none"),
        "—",
    )
    p_best = f"{best_jumper['m']['total_data_movement_power_W']:.0f}"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>NOW + 跳线层 3D Mapping：基准与跳线拓扑对比</title>
<style>
:root {{
  --bg: #f4f1ea; --ink: #1c1a16; --muted: #5c574e; --card: #fffcf7;
  --line: #d9d2c5; --accent: #1f5f74; --accent2: #8b4513;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: "IBM Plex Sans", "Source Han Sans SC", "Noto Sans CJK SC",
    "PingFang SC", Helvetica, Arial, sans-serif;
  color: var(--ink);
  background:
    radial-gradient(1200px 600px at 10% -10%, #e7eef2 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 0%, #efe6d8 0%, transparent 50%),
    var(--bg);
  line-height: 1.55;
}}
.wrap {{ max-width: 1100px; margin: 0 auto; padding: 28px 22px 64px; }}
header.hero {{
  padding: 28px 28px 22px;
  background: linear-gradient(135deg, #1f5f74 0%, #2a7a8c 45%, #3d6b58 100%);
  color: #f7fbff; border-radius: 6px; margin-bottom: 28px;
}}
header.hero h1 {{ margin: 0 0 8px; font-size: clamp(1.55rem, 2.4vw, 2.1rem); font-weight: 700; }}
header.hero .sub {{ opacity: 0.92; max-width: 48rem; }}
header.hero .meta {{ margin-top: 14px; font-size: 0.92rem; opacity: 0.88; }}
nav.toc {{
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 14px 18px; margin-bottom: 28px;
}}
nav.toc strong {{ display:block; margin-bottom: 6px; }}
nav.toc a {{ color: var(--accent); text-decoration: none; margin-right: 14px; }}
h2 {{ margin: 34px 0 12px; font-size: 1.35rem; border-bottom: 2px solid var(--accent); padding-bottom: 6px; }}
h3 {{ margin: 22px 0 8px; font-size: 1.08rem; color: #24353a; }}
.muted {{ color: var(--muted); }}
.kpis {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; margin: 14px 0 8px;
}}
.kpi {{
  background: var(--card); border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 12px 10px;
}}
.kpi .v {{ font-size: 1.35rem; font-weight: 700; color: var(--accent); }}
.kpi .l {{ font-size: 0.82rem; color: var(--muted); margin-top: 2px; }}
table {{
  width: 100%; border-collapse: collapse; background: var(--card);
  border: 1px solid var(--line); font-size: 0.9rem; margin: 10px 0 16px;
}}
th, td {{ border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
th {{ background: #efe9de; font-weight: 650; }}
tr.best {{ background: #e7f3ea; }}
td.path {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.75rem; word-break: break-all; }}
figure {{
  margin: 16px 0 22px; background: var(--card); border: 1px solid var(--line);
  border-radius: 6px; padding: 10px 12px 14px;
}}
figcaption {{ font-weight: 650; margin: 0 0 8px; }}
figure img, .svg-wrap svg {{ display: block; width: 100%; height: auto; background: #f7f5f0; }}
pre {{
  background: #1e2430; color: #e8eef7; padding: 12px 14px; border-radius: 6px;
  overflow: auto; font-size: 0.85rem;
}}
.note {{
  background: #fff8e8; border-left: 4px solid #c48a2a; padding: 10px 12px; margin: 12px 0;
}}
.eq {{
  background: var(--card); border: 1px solid var(--line); padding: 10px 14px;
  border-radius: 6px; font-family: "Times New Roman", Times, serif; margin: 8px 0 14px;
}}
.diagram {{
  background: #f7f5f0; border: 1px solid var(--line); border-radius: 6px;
  padding: 12px 14px; overflow: auto; margin: 10px 0 14px;
  font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.76rem;
  line-height: 1.35; white-space: pre; color: #2a2924;
}}
.chiplet-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px; margin: 10px 0 14px;
}}
.chip-box {{
  border: 1.5px solid #1f5f74; border-radius: 4px; background: #fff;
  padding: 10px 12px; font-size: 0.88rem;
}}
.chip-box .title {{ font-weight: 700; color: #1f5f74; margin-bottom: 6px; }}
.chip-box ul {{ margin: 0; padding-left: 1.1rem; }}
footer {{
  margin-top: 40px; padding-top: 12px; border-top: 1px solid var(--line);
  color: var(--muted); font-size: 0.85rem;
}}
code, .mono {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.88em; }}
</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <h1>NOW + 跳线层 3D Mapping</h1>
  <div class="sub">Clos [66,66,66] · Layer0=350×200G / Layer1=180×200G / 垂直=250×200G ·
  含<strong>无跳线基准（none）</strong>与 single / dual / quad / full 跳线拓扑，同一套算法对比。</div>
  <div class="meta">跳线拓扑最优：<strong>{best_jumper['topo']}</strong> · L1–L3 max delay
  <strong>{best_jumper['m']['max_path_delay_ns']:.0f} ns</strong> · seed={best_jumper['m'].get('seed')}
  （相对基准 {d_none} ns） · 统计口径为 Clos <strong>L1→L2→L3 端到端</strong>（两段单跳之和） ·
  实现 <span class="mono">mesh3d.py</span> / <span class="mono">optimize_3d_mapping.py</span></div>
</header>

<nav class="toc">
  <strong>目录</strong>
  <a href="#basics">基本概念</a>
  <a href="#compare">拓扑对比</a>
  {toc_topo}
</nav>

<section id="basics">
<h2>1. 基本概念与物理拓扑</h2>
<p><strong>SSC</strong>（Sub-Switch Chiplet）是晶圆上的基本交换 die；本场景 66 个 die 全是 SSC，
同 id 共址于 Clos L1/L2/L3。逻辑拓扑为 Clos <code>[66,66,66]</code>，两级全连接 @200G（8712 条逻辑边）。</p>
<p><strong>基准（none）</strong>：仅 NOW 层 2D Mesh，无跳线、无垂直边。其余预设在 NOW 上叠加跳线层
（可多窗口独立 Mesh）与同坐标垂直互联；SSC 只放在 NOW，跳线作 feedthrough，窗口之间<strong>不相连</strong>。</p>
<div class="diagram">物理拓扑预设

  none    基准：仅 NOW（无跳线层）
  single  1 Mesh:  (2,2)–(5,7)
  dual    2 Mesh:  (0,2)–(3,7)  +  (4,2)–(7,7)
  quad    4 Mesh:  (0,0)–(3,4)  +  (0,5)–(3,9)
                   (4,0)–(7,4)  +  (4,5)–(7,9)
  full    NOW 镜像：同 die / 同邻接；跳线容量仍为 180×200G

边时延：NOW 80 ns · 跳线 1 ns · 垂直 5 ns
容量：  NOW 350×200G · 跳线 180×200G · 垂直 250×200G</div>
<div class="eq">L(π)=Σ d<sub>e</sub> [ns]， E(π)=Σ E<sub>e</sub> [pJ/bit]， P(π)=E(π)×200 Gbps×1.5 [W]</div>
<pre># 基准（无跳线）
python3 optimize_3d_mapping.py --no-jumper --manhattan-top-pct 20 --seed &lt;s&gt;

# 跳线拓扑
python3 optimize_3d_mapping.py --jumper-topo single|dual|quad|full \\
  --manhattan-top-pct 20 --rebalance-rounds 12 --seed &lt;s&gt;</pre>
</section>

<section id="compare">
<h2>2. 基准 + 跳线拓扑最优结果对比</h2>
<div class="note">时延 KPI 为 Clos <strong>L1→L2→L3 端到端</strong>：对所有 (src,mid,dst)，
delay = L1-L2(src→mid) + L2-L3(mid→dst)；约为原单跳 max 的 2 倍。
排序键：(L1–L3 max delay ↑, n_at_max ↑, power ↑)。高亮行为<strong>跳线拓扑中</strong>最优（不含基准）。
Seed 扫描均为 1–8，identity mapping；有跳线时启用热点再平衡 + longest-tail 压缩。</div>
<table>
  <thead>
    <tr>
      <th>topo</th><th>跳线窗口</th><th>#Mesh</th><th>#跳线节点</th>
      <th>L1–L3 max</th><th>n_at_max</th><th>latency_max</th><th>C</th>
      <th>NOW max/cap</th><th>jumper max/cap</th><th>vert max/cap</th>
      <th>power (W)</th><th>best seed</th>
    </tr>
  </thead>
  <tbody>
{cmp_rows}
  </tbody>
</table>
<p class="muted">结论摘要：无跳线基准 L1–L3 max = <strong>{d_none} ns</strong>、功耗 ≈ {p_none} W（全曼哈顿）。
相对基准，single / dual / quad / full 分别压到 <strong>{d_single} / {d_dual} / {d_quad} / {d_full} ns</strong>；
当前跳线最优为 <strong>{best_jumper['topo']}</strong>（{best_jumper['m']['max_path_delay_ns']:.0f} ns，功耗 ≈ {p_best} W）。</p>
</section>

{topo_sections}

<footer>
自包含报告 · none（基准）/ single / dual / quad / full 最优结果与图均内嵌 · 无外网依赖。
</footer>
</div>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size / 1024:.1f} KiB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--none-dir",
        type=Path,
        default=Path("results_3d_baseline_now/seed_sweep/seed_2"),
    )
    ap.add_argument(
        "--none-sweep",
        type=Path,
        default=Path("results_3d_baseline_now/seed_sweep/sweep_summary.json"),
    )
    ap.add_argument(
        "--single-dir",
        type=Path,
        default=Path("results_3d_now_jumper/seed_sweep/seed_7"),
    )
    ap.add_argument(
        "--single-sweep",
        type=Path,
        default=Path("results_3d_now_jumper/seed_sweep/sweep_summary.json"),
    )
    ap.add_argument(
        "--dual-dir",
        type=Path,
        default=Path("results_3d_jumper_dual/seed_sweep/seed_5_intense"),
    )
    ap.add_argument(
        "--dual-sweep",
        type=Path,
        default=Path("results_3d_jumper_dual/seed_sweep/sweep_summary.json"),
    )
    ap.add_argument(
        "--quad-dir",
        type=Path,
        default=Path("results_3d_jumper_quad/seed_sweep/seed_5_intense"),
    )
    ap.add_argument(
        "--quad-sweep",
        type=Path,
        default=Path("results_3d_jumper_quad/seed_sweep/sweep_summary.json"),
    )
    ap.add_argument(
        "--full-dir",
        type=Path,
        default=Path("results_3d_jumper_full/seed_sweep/seed_6"),
    )
    ap.add_argument(
        "--full-sweep",
        type=Path,
        default=Path("results_3d_jumper_full/seed_sweep/sweep_summary.json"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("results_3d_now_jumper/NOW_JUMPER_3D_REPORT.html"),
    )
    args = ap.parse_args()

    # Auto-pick best seed dirs from sweeps if present
    def best_dir(default: Path, sweep: Path, root_hint: Path) -> Path:
        if sweep.exists():
            rows = json.loads(sweep.read_text(encoding="utf-8"))
            if rows:
                row0 = rows[0]
                if row0.get("dir"):
                    cand = Path(row0["dir"])
                    if cand.exists():
                        return cand
                seed = row0["seed"]
                cand = sweep.parent / f"seed_{seed}"
                if cand.exists():
                    return cand
                cand2 = sweep.parent / f"seed_{seed}_intense"
                if cand2.exists():
                    return cand2
        return default

    none_dir = best_dir(args.none_dir, args.none_sweep, Path("results_3d_baseline_now"))
    single_dir = best_dir(args.single_dir, args.single_sweep, Path("results_3d_now_jumper"))
    dual_dir = best_dir(args.dual_dir, args.dual_sweep, Path("results_3d_jumper_dual"))
    quad_dir = best_dir(args.quad_dir, args.quad_sweep, Path("results_3d_jumper_quad"))
    full_dir = best_dir(args.full_dir, args.full_sweep, Path("results_3d_jumper_full"))
    print(
        f"report dirs: none={none_dir} single={single_dir} "
        f"dual={dual_dir} quad={quad_dir} full={full_dir}"
    )

    topos = [
        load_topo(none_dir, args.none_sweep, "none"),
        load_topo(single_dir, args.single_sweep, "single"),
        load_topo(dual_dir, args.dual_sweep, "dual"),
        load_topo(quad_dir, args.quad_sweep, "quad"),
        load_topo(full_dir, args.full_sweep, "full"),
    ]
    # Display order: baseline first, then jumper presets
    order = {"none": 0, "single": 1, "dual": 2, "quad": 3, "full": 4}
    topos = sorted(topos, key=lambda t: order.get(t["topo"], 9))
    build(topos, args.out)


if __name__ == "__main__":
    main()
