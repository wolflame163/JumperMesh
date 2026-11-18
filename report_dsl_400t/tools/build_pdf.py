#!/usr/bin/env python3
"""report_dsl_400t/src/*.md → build/report.html → 400Tbps+_WSE-Switch构型分析报告.pdf。

沿用 switch_dse/report/report/tools/build.py 的样式、公式与 !fig / !tab 约定；
正文中的数值与表格由 data/dsl_{n}x{n}.json 填充：
  {{4|manhattan|C_tbps|.1f}}     取 4×4 方案二的字段（路径用 / 分隔，如 power/0.1/total_W）
  <!-- TAB:bw:4 -->              整张表（见 TABLES）
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
BUILD = ROOT / "build"
DATA = ROOT / "data"
OUT = ROOT / "output"
PDF = OUT / "400Tbps+_WSE-Switch构型分析报告.pdf"
TITLE = "400Tbps+ WSE-Switch构型分析报告"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HS_TOOLS = ROOT.parents[1] / "report" / "report" / "tools"
sys.path.insert(0, str(HS_TOOLS))
sys.path.insert(0, str(ROOT.parent))
import build as HS  # noqa: E402
import dsl_mesh_400t as M  # noqa: E402

SCHEMES = ("xy_o1turn_cw", "manhattan")
S3 = ("s3_0", "s3_5", "s3_10")
ALL = SCHEMES + S3 + ("o1t",)
EW = ("0.1", "0.06")


def parse_paths(raw: dict) -> list:
    return [[tuple(x) for x in p] for p in raw.values()]


def s3_record(s2: dict, r: dict) -> dict:
    """方案三（方案二 + 直连叠加）整理成与方案一 / 二相同的字段。

    单链路统计覆盖 CLOS 链路与 die 间直连；e2e / 功耗取 dsl_l1l3_direct.py 的流量口径。
    """
    paths = parse_paths(s2["paths"]) + [[tuple(x) for x in d["path"]] for d in r["directs"]]
    ms = ([M.path_metrics(p) for p in parse_paths(s2["paths"])]
          + [M.path_metrics([tuple(x) for x in d["path"]], t_sw=0.0) for d in r["directs"]])
    nf = len(ms)
    hops = [m["hops"] for m in ms]
    worst_link = max(ms, key=lambda m: m["lat_max"])
    detour = sum(1 for d in r["directs"]
                 if len(d["path"]) - 1 > abs(d["i"][0] - d["k"][0]) + abs(d["i"][1] - d["k"][1]))
    b = r["b_tbps"]
    o = dict(r)
    o.update(
        lb=s2["lb"], lb_tbps=s2["lb_tbps"], C_ratio_lb=r["C"] / s2["lb"],
        mean_edge_tbps=r["total_d2d_tbps"] / len(s2["loads"]),
        ft_bw_share=sum(h - 1 for h in hops) / sum(hops),
        n_flows=nf, hops_mean=sum(hops) / nf, hops_max=max(hops),
        wire_mean=sum(m["wire_mean"] for m in ms) / nf, wire_max=max(m["wire_max"] for m in ms),
        turns_mean=sum(m["turns"] for m in ms) / nf, detour_flows=detour, detour_share=detour / nf,
        lat_link_max=worst_link["lat_max"],
        ft_share_mean=sum(m["ft_lat_mean"] for m in ms) / sum(m["lat_mean"] for m in ms),
        edge_min_tbps=min(r["loads"].values()) * b,
        load_growth=r["total_d2d_tbps"] / r["total_d2d_tbps_s2"] - 1,
        n_pairs_dd=r["N"] * (r["N"] - 1),
        dir_twohop_min=min((d["twohop_lat"] for d in r["directs"]), default=0.0),
        dir_twohop_max=max((d["twohop_lat"] for d in r["directs"]), default=0.0),
        direct_lat_min=min((d["lat_max"] for d in r["directs"]), default=0.0),
    )
    base = r["l1_uplink_ports_base"]
    for side in ("l1", "l3"):
        o[f"{side}_sw_ports_growth"] = r[f"{side}_ports_added_max_per_sw_incl_local"] / base
        o[f"{side}_sw_ports_growth_ceil"] = r[f"{side}_ports_added_max_per_sw_incl_local_ceil"] / base
    o["ports_total_growth"] = r["l1_ports_added_total_incl_local"] / (base * r["N"])
    o["ports_total_growth_ceil"] = r["l1_ports_added_total_incl_local_ceil"] / (base * r["N"])

    # L1→L3 最大能耗：有直连的 die 对取直连路径，其余取最坏 L2
    pos = sorted({tuple(x) for p in paths for x in p})
    met = {}
    for key, p in s2["paths"].items():
        st, a, c = key.split("|")
        met[(int(st), tuple(map(int, a.split(","))), tuple(map(int, c.split(","))))] = M.path_metrics([tuple(x) for x in p])
    dmet = {(tuple(d["i"]), tuple(d["k"])): M.path_metrics([tuple(x) for x in d["path"]]) for d in r["directs"]}
    for ew in EW:
        e = float(ew)
        e1 = {(i, j): M.energy_pj(met[(1, i, j)], e) if i != j else 0.0 for i in pos for j in pos}
        e2 = {(j, k): M.energy_pj(met[(2, j, k)], e) if j != k else 0.0 for j in pos for k in pos}
        worst = 0.0
        for i in pos:
            for k in pos:
                if i == k:
                    continue
                v = M.energy_pj(dmet[(i, k)], e) if (i, k) in dmet else max(e1[(i, j)] + e2[(j, k)] for j in pos)
                worst = max(worst, v)
        o["power"][ew]["e2e_max_pj"] = worst
        o["power"][ew]["reserved_total_W"] = r["power_reserved"][ew]["total_W"]
    return o


IFACE_NS = M.SIO_NS


def scale_fields(r: dict, sc: str):
    """第 4 章：加速比、时延分解（SIO / 走线 / Feedthrough 固定）与功耗占比。"""
    r["sp_edge"] = r["C_tbps"] / r["die_bw"]
    r["sp_edge_a2a"] = r["a2a_hot_tbps"] / r["die_bw"]
    N = r["N"]
    r["sp_inj"] = {"o1t": (N - 1) / N}.get(sc, 2 * (N - 1) / N if sc in SCHEMES else None)
    w = r["e2e_worst"]
    for k in ("iface", "ft", "turn", "sw_die", "sw_sw"):
        w[f"{k}_share"] = w[k] / w["lat"]
    hops = round(w["iface"] / IFACE_NS) if IFACE_NS else 0
    wire = w["ft"]  # 馈通走线（含缝隙），0.5 ns/mm
    r["lw"] = dict(lat=w["lat"], hops=hops, sio=w["iface"], wire=wire, turn=w["turn"], ft=w["ft"],
                   sw_die=w["sw_die"], sw_sw=w["sw_sw"],
                   wire_share=wire / w["lat"], move_share=(w["iface"] + wire + w["turn"]) / w["lat"],
                   fixed_share=(w["sw_die"] + w["sw_sw"]) / w["lat"], ft_share=w["ft"] / w["lat"])
    lat, h = r["e2e_lat_mean"], r["e2e_hops_mean"]
    sio_m = h * IFACE_NS
    turn_m = r["e2e"]["turn_lat"]["mean"]
    sw_die_m = M.T_SW_DIE
    if sc == "o1t":
        sw_sw_m = M.T_SW_SW_O1T
    elif sc.startswith("s3"):
        # AllToAll 的 N² 个 die 对中，直连对（含片内）不经 L2，其余经 L2 计一次 t_sw_sw
        f = (r["n_directs"] + N) / (N * N)
        sw_sw_m = (1 - f) * M.T_SW_SW
    else:
        sw_sw_m = M.T_SW_SW
    wire_m = lat - sio_m - turn_m - sw_die_m - sw_sw_m
    assert wire_m > 0, (sc, wire_m)
    r["lm"] = dict(lat=lat, sio=sio_m, wire=wire_m, turn=turn_m, sw_die=sw_die_m, sw_sw=sw_sw_m,
                   wire_share=wire_m / lat, move_share=(sio_m + wire_m + turn_m) / lat)
    for ew in EW:
        p = r["power"][ew]
        p["serdes_W"] = p["total_W"] - p["move_W"]
        p["serdes_share"] = p["serdes_W"] / p["total_W"]
        p["sio_share"] = p["sio_W"] / p["total_W"]
        # SIO 静态按物理构型配置带宽，与 sio_W 中的流量无关，必须由模型脚本给出
        p.setdefault("static_W", M.SERDES_W + p["sio_static_W"])
        p["static_share"] = p["static_W"] / p["total_W"]
        p["wire_share_total"] = p["wire_all_W"] / p["total_W"]
        p["move_share_total"] = p["move_W"] / p["total_W"]
        p["ft_wire_share_d2d"] = p["ft_wire_W"] / p["wire_W"]
        p["move_pj"] = p["move_W"] / M.SYSTEM_TBPS


def load_data() -> dict:
    ds = {}
    for n in (4, 8):
        d = json.loads((DATA / f"dsl_{n}x{n}.json").read_text())
        s3 = json.loads((DATA / f"dsl_l1l3_{n}x{n}.json").read_text())
        for x, r in s3.items():
            d[f"s3_{x}"] = s3_record(d["manhattan"], r)
        o = json.loads((DATA / f"dsl_o1t_{n}x{n}.json").read_text())
        o["C_ratio_lb"] = o["C"] / o["lb"]
        o["detour_share"] = 0.0
        o["edge_worst_mean_die"] = o["mean_edge_tbps"] / o["die_bw_tbps"]
        o["speedup_edge"] = n / 2
        o["speedup_total"] = 2 * n
        o["router_x"] = 2 * n + 1
        assert abs(o["C_die"] - n / 2) < 1e-9
        o["router_tbps"] = o["router_x"] * o["die_bw_tbps"]
        o["router_ports400"] = round(o["router_tbps"] / 0.4)
        d["o1t"] = o
        stk_path = DATA / f"dsl_stk_{n}x{n}.json"
        if stk_path.exists():
            d["stk"] = json.loads(stk_path.read_text())
        now_path = DATA / f"dsl_now_{n}x{n}.json"
        if now_path.exists():
            d["now"] = json.loads(now_path.read_text())
        wf_path = DATA / f"workflow_{n}x{n}.json"
        if wf_path.exists():
            for sc, st in json.loads(wf_path.read_text()).items():
                if sc in d:
                    d[sc]["wf"] = st
        for sc in ALL:
            r = d[sc]
            die_bw = M.SYSTEM_TBPS / (n * n)
            r["die_bw"] = die_bw
            if sc == "o1t":
                r["die_switch_tbps"] = r["router_tbps"]
                r["a2a_hot_tbps"] = r["a2a_C_tbps"]
            else:
                r["die_switch_tbps"] = 3 * die_bw + 0.4 * (r.get("l1_ports_added_max_per_sw_incl_local", 0)
                                                           + r.get("l3_ports_added_max_per_sw_incl_local", 0))
                r["a2a_hot_tbps"] = r["C_tbps"]
            r["die_switch_x"] = r["die_switch_tbps"] / die_bw
        for sc in ALL:
            r = d[sc]
            if sc in SCHEMES:
                hh = {int(k): v for k, v in r["hop_hist"].items()}
                tot_h = sum(h * v for h, v in hh.items())
                r["ft_bw_share"] = sum((h - 1) * v for h, v in hh.items()) / tot_h
                r["C_ratio_lb"] = r["C"] / r["lb"]
                r["detour_share"] = r["detour_flows"] / r["n_flows"]
            r["e2e_hops_max"] = r["e2e"]["hops"]["max"]
            r["e2e_hops_mean"] = r["e2e"]["hops"]["mean"]
            r["e2e_lat_max"] = r["e2e"]["lat_max"]["max"]
            r["e2e_lat_mean"] = r["e2e"]["lat_mean"]["mean"]
            r["e2e_wire_max"] = r["e2e"]["wire_max"]["max"]
            r["e2e_wire_mean"] = r["e2e"]["wire_mean"]["mean"]
            # 最小时延：同 die 本地路径（0 跳）；t_sw_die 端到端一次，t_sw_sw 只在经过 L2 时计
            if sc == "o1t":
                r["e2e_lat_min"] = M.T_SW_DIE + M.T_SW_SW_O1T
            elif sc.startswith("s3_"):
                r["e2e_lat_min"] = M.T_SW_DIE
            else:
                r["e2e_lat_min"] = M.T_SW_DIE + M.T_SW_SW
            arg = r["e2e_worst"].get("arg") or r["e2e"]["lat_max"]["arg"]
            ids = [f"die {p[0] * n + p[1]}" for p in arg if isinstance(p, list)]
            if sc == "o1t":
                r["worst_path"] = " → ".join(ids)
            else:
                r["worst_path"] = f"L1@{ids[0]} → L2@{ids[1]} → L3@{ids[2]}"
            r["worst_hops"] = round(r["e2e_worst"]["iface"] / M.SIO_NS)
            r["arr_w"] = n * M.DIE_W_MM + (n - 1) * M.GAP_MM
            r["arr_h"] = n * M.DIE_H_MM + (n - 1) * M.GAP_MM
            r["arr_diag"] = math.hypot(r["arr_w"], r["arr_h"])
            r["si_area"] = n * n * M.DIE_W_MM * M.DIE_H_MM
            for ew in EW:
                p = r["power"][ew]
                p["wire_all_W"] = p["wire_W"]  # 仅馈通
                p["ft_share_wire"] = p["ft_wire_W"] / p["wire_W"]
                p["move_W"] = p["sio_W"] + p["wire_W"]
                p["move_share"] = p["move_W"] / p["total_W"]
        xy, man = d["xy_o1turn_cw"], d["manhattan"]
        for sc in ALL:
            r = d[sc]
            r["C_vs_xy"] = r["C_tbps"] / xy["C_tbps"]
            r["C_save_vs_xy"] = 1 - r["C_vs_xy"]
            r["lat_minus_man"] = man["e2e_lat_max"] - r["e2e_lat_max"]
            r["hops_extra"] = r["hops_mean"] - man["hops_mean"]
            if sc in SCHEMES:
                r["edge_min_tbps"] = min(r["loads"].values()) * r["b_tbps"]
                extra = set()
                for key, path in r["paths"].items():
                    _, a, b2 = key.split("|")
                    (r0, c0), (r1, c1) = map(int, a.split(",")), map(int, b2.split(","))
                    h = abs(r1 - r0) + abs(c1 - c0)
                    if len(path) - 1 > h:
                        extra.add(len(path) - 1 - h)
                r["detour_extra"] = "/".join(str(x) for x in sorted(extra)) or "0"
            for ew in EW:
                sc_ = r["power"][ew]["scenarios"]
                for k in sc_:
                    sc_[k]["ratio"] = sc_[k]["W"] / sc_["a2a_100"]["W"]
                    sc_[k]["chip_W"] = M.SERDES_W + sc_[k]["W"]
                    base = man["power"][ew]["scenarios"].get(k, man["power"][ew]["scenarios"]["perm_100"])
                    sc_[k]["vs_s2"] = sc_[k]["W"] / base["W"] - 1
                    sc_[k]["drop_vs_s2"] = -sc_[k]["vs_s2"]
            r["lat_vs_xy"] = r["e2e_lat_max"] / xy["e2e_lat_max"]
            r["lat_vs_s2"] = r["e2e_lat_max"] / man["e2e_lat_max"] - 1
            r["lat_mean_vs_s2"] = r["e2e_lat_mean"] / man["e2e_lat_mean"] - 1
            r["hops_e2e_vs_s2"] = r["e2e_hops_mean"] / man["e2e_hops_mean"] - 1
            r["wire_e2e_vs_s2"] = r["e2e_wire_mean"] / man["e2e_wire_mean"] - 1
            r["C_vs_s2"] = r["C_tbps"] / man["C_tbps"] - 1
            r["lat_drop"] = -r["lat_vs_s2"]
            r["lat_mean_drop"] = -r["lat_mean_vs_s2"]
            r["lat_drop_vs_xy"] = 1 - r["e2e_lat_max"] / xy["e2e_lat_max"]
            for ew in EW:
                p, px, p2 = r["power"][ew], xy["power"][ew], man["power"][ew]
                p["total_vs_xy"] = p["total_W"] / px["total_W"] - 1
                p["move_vs_xy"] = p["move_W"] / px["move_W"] - 1
                p["total_vs_s2"] = p["total_W"] / p2["total_W"] - 1
                p["move_vs_s2"] = p["move_W"] / p2["move_W"] - 1
                p["d2d_vs_s2"] = p["d2d_W"] / p2["d2d_W"] - 1
                p["save_W"] = p2["total_W"] - p["total_W"]
                p["total_drop"] = -p["total_vs_s2"]
                p["move_drop"] = -p["move_vs_s2"]
                p.setdefault("total_worst_W", p["total_W"])
                p["worst_vs_s2"] = p["total_worst_W"] / p2["total_W"] - 1
                if "reserved_total_W" in p:
                    p["reserved_vs_s2"] = p["reserved_total_W"] / p2["total_W"] - 1
        o = d["o1t"]
        # 每颗 router 再多出多少 ns，O1Turn(DR) 最坏 e2e 时延追平 CLOS 方案
        o["tr_breakeven_vs_xy"] = (xy["e2e_lat_max"] - o["e2e_lat_max"]) / o["router_traversals_max"]
        o["tr_breakeven_vs_s2"] = (man["e2e_lat_max"] - o["e2e_lat_max"]) / o["router_traversals_max"]
        o["worst_perm_vs_a2a"] = o["power"]["0.1"]["scenarios"]["perm_worst"]["d2d_W"] / o["power"]["0.1"]["d2d_W"] - 1
        for sc in ALL:
            scale_fields(d[sc], sc)
        o["C_over_xy"] = o["C_tbps"] / xy["C_tbps"] - 1
        o["edges_at_n"] = sum(1 for v in o["worst_load"].values() if abs(v - o["C_die"]) < 1e-9)
        o["n_edges"] = len(o["worst_load"])
        ds[n] = d
    for sc in ALL:
        a, b = ds[4][sc], ds[8][sc]
        pa, pb = a["power"]["0.1"], b["power"]["0.1"]
        b["vs16"] = dict(sp=b["sp_edge"] / a["sp_edge"], C=b["C_tbps"] / a["C_tbps"],
                         wire=b["e2e_wire_mean"] / a["e2e_wire_mean"], wire_link=b["wire_mean"] / a["wire_mean"],
                         hops=b["e2e_hops_mean"] / a["e2e_hops_mean"],
                         hops_link=b["hops_mean"] / a["hops_mean"],
                         lat_max=b["e2e_lat_max"] / a["e2e_lat_max"], lat_mean=b["e2e_lat_mean"] / a["e2e_lat_mean"],
                         total=pb["total_W"] / pa["total_W"], move=pb["move_W"] / pa["move_W"],
                         d2d_wire=pb["wire_W"] / pa["wire_W"], sio=pb["sio_W"] / pa["sio_W"],
                         pj=pb["move_pj"] / pa["move_pj"])
    return ds


def get(ds, n, sc, path):
    v = ds[int(n)][sc]
    for k in path.split("/"):
        v = v[k]
    return v


# ---------------------------------------------------------------- tables


SN = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由",
      "s3_0": "方案三 DSL+直连 x=0", "s3_5": "方案三 DSL+直连 x=5%", "s3_10": "方案三 DSL+直连 x=10%", "o1t": "方案四 O1Turn(DR)"}
SCEN_SHORT = {"a2a_100": "AllToAll 100%", "a2a_75": "AllToAll 75%", "a2a_50": "AllToAll 50%",
              "a2a_25": "AllToAll 25%", "perm_100": "Permutation 满载", "hot_center": "中心热点（1/4 die）",
              "hot_corner": "角落热点（1/4 die）"}


def t_bw(ds, n):
    rows = ["| 方案 | 最热边 C（条） | 最热边带宽（Tbps） | C / 下界 | 400G 端口 / 边 / 方向 | 25 mm 共享边最大（Tbps） | 32 mm 共享边最大（Tbps） | 平均边负载（Tbps） | 馈通占已用 D2D 带宽 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for sc in ALL:
        r = ds[n][sc]
        b = r["b_tbps"]
        rows.append(f"| {SN[sc]} | {r['C']:.0f} | **{r['C_tbps']:.1f}** | {r['C_ratio_lb']:.3g}× | {r['C_ports400']} | "
                    f"{r['C_h'] * b:.1f} | {r['C_v'] * b:.1f} | "
                    f"{r['mean_edge_tbps']:.1f} | {100 * r['ft_bw_share']:.0f}% |")
    rows.append(f"| 二分下界 | {ds[n]['manhattan']['lb']} | {ds[n]['manhattan']['lb_tbps']:.1f} | 1× | "
                f"{math.ceil(ds[n]['manhattan']['lb_tbps'] / 0.4)} | — | — | — | — |")
    o = ds[n]["o1t"]
    return "\n".join(rows) + (f"\n\n<p class=\"small\">方案四的 “条” 按 b = {o['b_tbps']:g} Tbps 折算；其边带宽为无阻塞所需"
                              f"（顺 / 逆时针各 50%，任意置换下的最坏负载，{o['C_die']:g} × {o['die_bw_tbps']:.1f}T），平均边负载亦按逐边无阻塞所需计；"
                              f"AllToAll 满载的实际最热边只有 {o['a2a_C_tbps']:.1f} Tbps。</p>")


def t_wire(ds, n):
    rows = ["| 方案 | 单链路平均 / 最大跳数 | 端到端平均 / 最大跳数 | 单链路平均馈通（mm） | 单链路最大馈通（mm） | 端到端平均 / 最大馈通（mm） | 平均转弯次数 | 绕路链路数（占比） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for sc in ALL:
        r = ds[n][sc]
        rows.append(f"| {SN[sc]} | {r['hops_mean']:.2f} / {r['hops_max']} | {r['e2e_hops_mean']:.2f} / {r['e2e_hops_max']:.0f} | "
                    f"{r['wire_mean']:.1f} | **{r['wire_max']:.0f}** | {r['e2e_wire_mean']:.0f} / {r['e2e_wire_max']:.0f} | "
                    f"{r['turns_mean']:.2f} | {r['detour_flows']:,}（{100 * r['detour_share']:.1f}%） |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">馈通距离 wire_ft=Σf_d，不含源/宿、不含缝隙。"
                              "方案三的单链路统计包含 CLOS 链路与 die 间直连；"
                              "L1→L3 按 “有直连的 die 对走直连，其余经全部 L2 两跳” 统计（AllToAll 口径，见 1.6 节）；方案四的 “单链路” 即 src die → dst die 路径，端到端平均含 src = dst 的本地流量。</p>")


def t_lat(ds, n):
    rows = ["| 方案 | 单链路最大 | 端到端最大 | 端到端平均 | 最坏路径：SIO | 最坏路径：馈通走线 | 最坏路径：转向 | 最坏路径：$t_{sw\\_die}$ | 最坏路径：$t_{sw\\_sw}$ | 最坏路径 FT 占比 | 全部链路平均 FT 占比 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for sc in ALL:
        r = ds[n][sc]
        w = r["e2e_worst"]
        rows.append(f"| {SN[sc]} | {r['lat_link_max']:,.0f} | **{r['e2e_lat_max']:,.0f}** | {r['e2e_lat_mean']:,.0f} | "
                    f"{w['iface']:.0f} | {w['ft']:,.0f} | {w['turn']:.0f} | {w['sw_die']:.0f} | {w['sw_sw']:.0f} | **{100 * w['ft_share']:.0f}%** | {100 * r['ft_share_mean']:.0f}% |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">单位 ns。“单链路最大” 为单条路径独立计入 \\(t_{sw\\_die}\\)（及经 L2 时的 \\(t_{sw\\_sw}\\)）的时延。端到端：方案一~三为 L1→L2→L3，方案四为 src die → dst die；平均为均值走线口径；FT = Feedthrough；转向 = 横纵方向变化次数 × 2 ns；方案四过路 die 的 router 转发按 Feedthrough 与转向计（1.6.3 节）。"
                              "方案三的 L1→L3 时延为 AllToAll 口径（直连承载该 die 对的全部流量）；"
                              "非均匀流量溢出到 CLOS 的部分仍按方案二的路径，最坏时延回到方案二的值。</p>")


def t_lat_calc(ds, n):
    """1.5.2 时延计算示例：每个方案一列，取该方案 n×n 的最坏端到端路径（方案三取最长的 L1→L3 直连）。"""
    g, v, t = M.GAP_MM, M.WIRE_NS_PER_MM, M.TURN_NS

    def die(p):
        return f"die {p[0] * n + p[1]}"

    cols = []
    for sc in ("xy_o1turn_cw", "manhattan"):
        r = ds[n][sc]
        w = r["e2e_worst"]
        h = round(w["iface"] / M.SIO_NS)
        cols.append(dict(name=SN[sc], path=r["worst_path"], h=h, turns=w["turns"],
                         f=w["ft"] / v - h * g, sw_sw=w["sw_sw"], lat=w["lat"], sw_note="经 L2 计一次"))
    r = ds[n]["s3_10"]
    dd = max(r["directs"], key=lambda q: q["lat_max"])
    p = [tuple(x) for x in dd["path"]]
    m = M.path_metrics(p, t_sw=0.0)
    cols.append(dict(name=f"{SN['s3_10']}（直连）", path=f"L1@{die(p[0])} → L3@{die(p[-1])}（原两跳 {dd['twohop_lat']:.0f} ns）",
                     h=m["hops"], turns=m["turns"], f=m["ft_max"], sw_sw=0.0, lat=m["lat_max"], sw_note="不经 L2，取 0"))
    o = ds[n]["o1t"]
    w = o["e2e_worst"]
    h = round(w["iface"] / M.SIO_NS)
    cols.append(dict(name=SN["o1t"], path=o["worst_path"], h=h, turns=w["turns"],
                     f=w["ft"] / v - h * g, sw_sw=w["sw_sw"], lat=w["lat"], sw_note="O1Turn 取 0"))
    for c in cols:
        tot = c["h"] * M.SIO_NS + (c["f"] + c["h"] * g) * v + c["turns"] * t + M.T_SW_DIE + c["sw_sw"]
        assert abs(tot - c["lat"]) < 1e-6, (c["name"], tot, c["lat"])

    def row(label, fn):
        return f"| {label} | " + " | ".join(fn(c) for c in cols) + " |"

    rows = ["| 项 | " + " | ".join(c["name"] for c in cols) + " |", "|---|" + "---|" * len(cols),
            row("计算公式 \\(\\Delta\\)", lambda c: r"\(11.5h+0.5(\sum f_d+hg)\)<br>\(+\,2n_{turn}+t_{\mathrm{sw\_die}}\)"
                + (r"<br>\(+\,t_{\mathrm{sw\_sw}}\)" if c["sw_sw"] else "")),
            row("示例路径（最坏）", lambda c: c["path"]),
            row("典型参数", lambda c: f"\\(h={c['h']}\\)，\\(n_{{turn}}={c['turns']}\\)<br>\\(\\sum f_d={c['f']:g}\\) mm<br>\\(g={g:g}\\) mm"),
            row("SIO", lambda c: f"{c['h']} × {M.SIO_NS:g} = {c['h'] * M.SIO_NS:g}"),
            row("馈通 + 缝隙", lambda c: f"({c['f']:g} + {c['h']} × {g:g}) × {v:g} = {(c['f'] + c['h'] * g) * v:g}"),
            row("横纵转向", lambda c: f"{c['turns']} × {t:g} = {c['turns'] * t:g}"),
            row("\\(t_{\\mathrm{sw\\_die}}\\)（端到端一次）", lambda c: f"{M.T_SW_DIE:g}"),
            row("\\(t_{\\mathrm{sw\\_sw}}\\)", lambda c: f"{c['sw_sw']:g}（{c['sw_note']}）"),
            row("**结果 \\(\\Delta\\)**", lambda c: f"**{c['lat']:g} ns**"),
            row("同 die 最小时延（0 跳）", lambda c: f"{M.T_SW_DIE + c['sw_sw']:g} ns")]
    return "\n".join(rows) + (f"\n\n<p class=\"small\">单位 ns；{n}×{n} 封装。方案一、二为 L1→L2→L3 端到端最大时延路径（L1→L2、L2→L3 两段的跳数、馈通与转向相加，"
                              "固定项只计一次）；方案三列取 x = 10% 时最长的 L1→L3 直连，括号内为该 die 对原经 L2 两跳的最坏时延；方案四为 src die → dst die 单段最大时延路径。"
                              "馈通按最坏口径：直通取 die 边长（x 向 32、y 向 25 mm），转弯 die 取 57 mm。</p>")


def t_power(ds, n):
    rows = ["| 走线能耗 | 方案 | SIO 接口 | 馈通走线 | 数据搬移合计 | SerDes | **芯片总功耗** | 静态功耗 | 单链路最大（pJ/bit） | 端到端最大（pJ/bit） |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ew in EW:
        for sc in ALL:
            p = ds[n][sc]["power"][ew]
            st = p["static_W"]
            rows.append(f"| {ew} | {SN[sc]} | {p['sio_W']:,.0f} | {p['wire_W']:,.0f} | {p['move_W']:,.0f} | "
                        f"{M.SERDES_W:,.0f} | **{p['total_W']:,.0f}** | {st:,.0f} | "
                        f"{p['max_path_pj']:.1f} | {p['e2e_max_pj']:.1f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">功耗单位 W；馈通走线不含源/宿与缝隙；不计线路侧走线；"
                              "全部为静态 + 当前流量动态（满载 AllToAll：\\(\\lambda=b\\)）；"
                              "静态 = SerDes + SIO 静态（按最终物理构型：\\(n_{dir}\\) 条有向 die 边 × 最热边 \\(C\\) × 0.35 × 0.7）。</p>")


def t_scen(ds, n):
    keys = [k for k, _ in M.SCENARIOS]
    head = "| 场景 | 注入带宽（Tbps） | " + " | ".join(SN[sc] for sc in ALL) + " | 方案三 DSL+直连 x=10% 相对方案二 |"
    rows = [head, "|---|---:|" + "---:|" * (len(ALL) + 1)]
    for k in keys:
        r0 = ds[n][SCHEMES[0]]["power"]["0.1"]["scenarios"][k]
        cells = []
        for sc in ALL:
            a = ds[n][sc]["power"]["0.1"]["scenarios"][k]["W"]
            b = ds[n][sc]["power"]["0.06"]["scenarios"][k]["W"]
            cells.append(f"{a:,.0f} / {b:,.0f}")
        v = ds[n]["s3_10"]["power"]["0.1"]["scenarios"][k]["vs_s2"]
        rows.append(f"| {SCEN_SHORT[k]} | {r0['inj_tbps']:.1f} | " + " | ".join(cells) + f" | {100 * v:+.1f}% |")
        if k == "perm_100":
            cells = []
            for sc in ALL:
                sc_ = {e: ds[n][sc]["power"][e]["scenarios"] for e in EW}
                if sc in SCHEMES or sc == "o1t":
                    kk = "perm_worst" if sc == "o1t" else "perm_100"
                    cells.append(f"{sc_['0.1'][kk]['W']:,.0f} / {sc_['0.06'][kk]['W']:,.0f}")
                else:
                    cells.append("—")
            rows.append(f"| Permutation 最坏置换 | {r0['inj_tbps']:.1f} | " + " | ".join(cells) + " | — |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">单位 W（SIO + 片上走线，不含 SerDes），每格为 0.1 / 0.06 pJ/bit/mm；"
                              "最后一列为 0.1 口径。方案三中每个 die 对最多 b 的流量走直连、其余走 CLOS；"
                              "Permutation 满载取均匀随机置换的期望；方案四“最坏置换”按动态数据搬移能耗"
                              "（0.3·0.35h + 馈通）做最大权指派，再加按物理构型计的 SIO 静态（1.5.3 节）；"
                              "方案一、二因两级喷洒与置换无关。</p>")


def t_s3(ds, n):
    rows = ["| 方案三 | 直连条数（占 die 间 L1→L3 对） | 最热边：条 / Tbps | D2D 带宽增长（最热边） | 400G 端口 / 边 / 方向 | 有向负载总量增长 | 直连平均 / 最大跳数 | 直连平均 / 最大走线（mm） | 直连最大时延（ns） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    s2 = ds[n]["manhattan"]
    rows.append(f"| 方案二（基线） | — | {s2['C']} / {s2['C_tbps']:.1f} | — | {s2['C_ports400']} | — | — | — | — |")
    for sc in S3:
        r = ds[n][sc]
        rows.append(f"| x = {r['x_pct']:g}% | {r['n_directs']:,}（{100 * r['direct_share']:.0f}%） | "
                    f"{r['C']:.0f} / **{r['C_tbps']:.1f}** | **{100 * r['d2d_growth']:+.1f}%** | {r['C_ports400']} | "
                    f"{100 * r['load_growth']:+.1f}% | {r['direct_hops_mean']:.2f} / {r['direct_hops_max']} | "
                    f"{r['direct_wire_mean']:.0f} / {r['direct_wire_max']:.0f} | {r['direct_lat_max']:,.0f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">x 为允许的最热边带宽增长上限（相对方案二）；"
                              "“有向负载总量” 为全部有向 die 间边负载之和，CLOS 部分与方案二逐边相同。</p>")


def t_ports(ds, n):
    r0 = ds[n]["s3_0"]
    base = r0["l1_uplink_ports_base"]
    rows = [f"| 方案三 | 直连条数（die 间 + 片内） | 单 switch 最大新增 L1 输出端口（400G 等效） | 单 switch 最大新增 L3 输入端口（400G 等效） | L1 增长（400G 等效，相对上行 {base:.0f} 端口） | 整 400G 端口计：单 switch 最大新增 L1 / L3 | L1 增长（整端口，相对上行 {base:.0f} 端口） | 全芯片 L1 / L3 各新增（400G 等效 / 整端口） |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for sc in S3:
        r = ds[n][sc]
        rows.append(f"| x = {r['x_pct']:g}% | {r['n_directs']:,} + {r['local_directs']} | "
                    f"{r['l1_ports_added_max_per_sw_incl_local']:g} | {r['l3_ports_added_max_per_sw_incl_local']:g} | "
                    f"**{100 * r['l1_sw_ports_growth']:+.0f}%** | {r['l1_ports_added_max_per_sw_incl_local_ceil']:g} / "
                    f"{r['l3_ports_added_max_per_sw_incl_local_ceil']:g} | {100 * r['l1_sw_ports_growth_ceil']:+.0f}% | "
                    f"{r['l1_ports_added_total_incl_local']:,.0f} / {r['l1_ports_added_total_incl_local_ceil']:,.0f} |")
    b = r0["b_tbps"]
    return "\n".join(rows) + (f"\n\n<p class=\"small\">每条直连带宽 b = {b:g} Tbps（{b / 0.4:g} 个 400G）；"
                              "“400G 等效” 按带宽折算，“整 400G 端口” 假设每条直连至少占用一个独立的 400G 端口。"
                              "L1 新增的是输出端口、L3 新增的是输入端口，两者条数相同；L2 不变。</p>")


def t_summary(ds, n):
    rows = ["| 指标 | " + " | ".join(SN[sc] for sc in ALL) + " |", "|---|" + "---:|" * len(ALL)]

    def line(label, f):
        rows.append(f"| {label} | " + " | ".join(f(ds[n][sc]) for sc in ALL) + " |")

    def rel(v, sc_r, fmt="+.0f"):
        if sc_r is ds[n]["manhattan"]:
            return ""
        return "（持平）" if abs(v) < 5e-4 else f"（{100 * v:{fmt}}%）"

    line("最热 die 间带宽（每边每方向，无阻塞所需）", lambda r: f"{r['C_tbps']:.1f} Tbps{rel(r['C_vs_s2'], r, '+.1f')}")
    line("AllToAll 满载实际最热边", lambda r: f"{r['a2a_hot_tbps']:.1f} Tbps")
    line("单 die 交换容量（最大）", lambda r: f"{r['die_switch_tbps']:.1f}T（{r['die_switch_x']:.3g}×）")
    line("走线平均跳数（单链路 / 端到端）", lambda r: f"{r['hops_mean']:.2f} / {r['e2e_hops_mean']:.2f}")
    line("走线最大跳数（单链路 / 端到端）", lambda r: f"{r['hops_max']} / {r['e2e_hops_max']:.0f}")
    line("平均 / 最大走线长度（单链路）", lambda r: f"{r['wire_mean']:.0f} / {r['wire_max']:.0f} mm")
    line("最大时延（端到端）", lambda r: f"**{r['e2e_lat_max']:,.0f} ns**{rel(r['lat_vs_s2'], r)}")
    line("平均时延（端到端）", lambda r: f"{r['e2e_lat_mean']:,.0f} ns{rel(r['lat_mean_vs_s2'], r)}")
    line("最坏路径 Feedthrough 时延占比", lambda r: f"{100 * r['e2e_worst']['ft_share']:.0f}%")
    line("单 switch 新增 L1 输出 / L3 输入端口", lambda r: f"{100 * r['l1_sw_ports_growth']:+.0f}%" if "l1_sw_ports_growth" in r else "—")
    for ew in EW:
        line(f"走线最大功耗 @{ew}（满载片上走线）", lambda r, ew=ew: f"{r['power'][ew]['wire_all_W']:,.0f} W")
        line(f"数据搬移功耗 @{ew}（SIO + 走线）", lambda r, ew=ew: f"{r['power'][ew]['move_W']:,.0f} W")
        line(f"芯片总功耗 @{ew}", lambda r, ew=ew: f"**{r['power'][ew]['total_W']:,.0f} W**{rel(r['power'][ew]['total_vs_s2'], r, '+.1f')}")
    return "\n".join(rows)


def _ratio(a, b):
    return f"{b / a:.2f}×" if a else "—"


def t_sc_speed(ds, _):
    rows = ["| 方案 | 注入加速比 16R / 64R | 16R：最热边（T） | 16R：单边加速比 | 16R：AllToAll 实际 | 64R：最热边（T） | 64R：单边加速比 | 64R：AllToAll 实际 | 单边加速比 64R / 16R | 单 die 交换容量（× B_die）16R → 64R |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for sc in CROSS:
        a, b = ds[4][sc], ds[8][sc]
        inj = f"{a['sp_inj']:.3f}× / {b['sp_inj']:.3f}×" if a["sp_inj"] is not None else "同方案二（CLOS 部分）"
        rows.append(f"| {CROSS_SN[sc]} | {inj} | {a['C_tbps']:.1f} | **{a['sp_edge']:.2f}×** | {a['sp_edge_a2a']:.2f}× | "
                    f"{b['C_tbps']:.1f} | **{b['sp_edge']:.2f}×** | {b['sp_edge_a2a']:.2f}× | {_ratio(a['sp_edge'], b['sp_edge'])} | "
                    f"{a['die_switch_x']:.3g}× → {b['die_switch_x']:.3g}× |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">注入加速比 = 单颗 die 自身发往其他 die 的流量（不含馈通）/ B_die，CLOS 方案为 L1、L2 两级各 (N−1)/N，合计 2(N−1)/N，方案四为 AllToAll 下的 (N−1)/N（任意流量不超过 1）；"
                              "单边加速比 = 最热有向 die 间边带宽（含馈通）/ 单 die 线路带宽 B_die（16R 为 25.6T，64R 为 6.4T）；"
                              "方案四按无阻塞所需（任意流量矩阵的最坏负载），“AllToAll 实际” 为满载 AllToAll 下的最热边；"
                              "单 die 交换容量方案一~三为 L1 + L2 + L3（方案三含新增直连端口），方案四为 router（4 边 + 线路侧）。</p>")


def t_sc_wire(ds, _):
    rows = ["| 方案 | 单链路平均 / 最大（mm）16R | 单链路平均 / 最大（mm）64R | 端到端平均 / 最大（mm）16R | 端到端平均 / 最大（mm）64R | 端到端平均 64R / 16R | 端到端平均跳数 16R → 64R |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for sc in CROSS:
        a, b = ds[4][sc], ds[8][sc]
        rows.append(f"| {CROSS_SN[sc]} | {a['wire_mean']:.0f} / {a['wire_max']:.0f} | {b['wire_mean']:.0f} / {b['wire_max']:.0f} | "
                    f"{a['e2e_wire_mean']:.0f} / {a['e2e_wire_max']:.0f} | {b['e2e_wire_mean']:.0f} / {b['e2e_wire_max']:.0f} | "
                    f"**{_ratio(a['e2e_wire_mean'], b['e2e_wire_mean'])}** | {a['e2e_hops_mean']:.2f} → {b['e2e_hops_mean']:.2f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">单链路平均为均值走线口径，最大为最坏走线口径；端到端方案一~三为 L1→L2→L3，方案四为 src die → dst die；"
                              "平均含同 die 0 跳链路，走线含 die 间 1 mm 缝隙。</p>")


def t_sc_lat(ds, _):
    rows = ["| 封装 | 方案 | 最坏路径时延（ns） | SIO 接口 | 馈通走线 | 转向 | $t_{sw\\_die}$ | $t_{sw\\_sw}$ | **馈通占比** | **数据搬移占比** | 平均路径时延（ns） | 平均路径馈通占比 |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n in (4, 8):
        for sc in CROSS:
            r = ds[n][sc]
            w, m = r["lw"], r["lm"]
            rows.append(f"| {n * n}R | {CROSS_SN[sc]} | {w['lat']:,.0f} | {w['sio']:.0f} | {w['wire']:,.0f} | "
                        f"{w['turn']:.0f} | {w['sw_die']:.0f} | {w['sw_sw']:.0f} | "
                        f"**{100 * w['wire_share']:.1f}%** | **{100 * w['move_share']:.1f}%** | "
                        f"{m['lat']:,.0f} | {100 * m['wire_share']:.1f}% |")
    return "\n".join(rows) + (f"\n\n<p class=\"small\">单位 ns。最坏路径分解为 SIO（{M.SIO_NS:g} ns/跳）、"
                              f"馈通走线（{M.WIRE_NS_PER_MM:g} ns/mm，含缝隙）、转向（{M.TURN_NS:g} ns/次）、"
                              f"$t_{{sw\\_die}}$（{M.T_SW_DIE:g} ns，端到端一次）与 "
                              f"$t_{{sw\\_sw}}$（方案一~三经 L2 计一次 {M.T_SW_SW:g} ns，直连与 O1Turn(DR) 为 0）；"
                              "数据搬移 = SIO + 馈通走线 + 转向。</p>")


def t_sc_power(ds, _):
    rows = ["| 封装 | 方案 | 芯片总功耗（W） | SerDes | SIO | 馈通走线 | **馈通占比** | **数据搬移占比** | 数据搬移能耗（pJ/bit） |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for n in (4, 8):
        for sc in CROSS:
            p = ds[n][sc]["power"]["0.1"]
            rows.append(f"| {n * n}R | {CROSS_SN[sc]} | {p['total_W']:,.0f} | {p['serdes_W']:,.0f} | {p['sio_W']:,.0f} | "
                        f"{p['wire_W']:,.0f} | **{100 * p['wire_share_total']:.1f}%** | "
                        f"**{100 * p['move_share_total']:.1f}%** | {p['move_pj']:.1f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">"
                              "数据搬移 = SIO + 馈通走线（不含线路侧、不含缝隙）；芯片总功耗 = 数据搬移 + SerDes；"
                              "数据搬移能耗 = 数据搬移功耗 / 409.6 Tbps。</p>")


CROSS = ("xy_o1turn_cw", "manhattan", "s3_0", "s3_10", "o1t")
CROSS_SN = {"xy_o1turn_cw": "方案一 DSL XY 路由", "manhattan": "方案二 DSL 最短路径路由", "s3_0": "方案三 DSL+直连 x=0",
            "s3_10": "方案三 DSL+直连 x=10%", "o1t": "方案四 O1Turn(DR)"}


def t_cross(ds, _):
    rows = ["| 封装 | 方案 | 最热边（T，无阻塞所需） | 单 die 交换容量（T） | 端到端平均 / 最大跳数 | 最大时延（ns） | 平均时延（ns） | FT 占比 | 总功耗 @0.1 / @0.06（kW） | 置换最坏 @0.1（kW） |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n in (4, 8):
        for sc in CROSS:
            r = ds[n][sc]
            p, p6 = r["power"]["0.1"], r["power"]["0.06"]
            rows.append(f"| {n}×{n} | {CROSS_SN[sc]} | {r['C_tbps']:.1f} | {r['die_switch_tbps']:.1f} | "
                        f"{r['e2e_hops_mean']:.1f} / {r['e2e_hops_max']:.0f} | {r['e2e_lat_max']:,.0f} | "
                        f"{r['e2e_lat_mean']:,.0f} | {100 * r['e2e_worst']['ft_share']:.0f}% | "
                        f"**{p['total_W'] / 1000:.1f}** / {p6['total_W'] / 1000:.1f} | {p['total_worst_W'] / 1000:.1f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">方案一~三的端到端为 L1→L2→L3，方案四为 src die → dst die 单段；"
                              "单 die 交换容量方案一、二为 L1 + L2 + L3，方案三另加 L1 / L3 新增端口，方案四为 router 线路侧 + 4 组交换侧；"
                              "FT 占比为最坏路径的 Feedthrough 时延占比；总功耗为满载 AllToAll 的芯片总功耗，“置换最坏” 为功耗最大的置换流量。</p>")


STK_TR = {"worst": "最坏置换（无阻塞）", "a2a": "AllToAll"}
STK_RT = {"ideal": "理想（η = 1）", "buf": "buffered", "bl": "bufferless"}


def t_stk_k(ds, _):
    rows = ["| 封装 | 流量口径 | router 实现 | \\(\\gamma\\) | \\(\\rho^*\\) | \\(\\eta\\) | \\(\\rho_{sat}\\) | **k** | **M = kN** | 单平面注入率 \\(\\lambda=1/k\\) | die 边带宽（T / 方向） | 相对方案四 | NOW die router 合计（T） |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for n in (4, 8):
        s = ds[n]["stk"]
        for tr in STK_TR:
            for rt in STK_RT:
                c = s["cfg"][f"{tr}_{rt}"]
                rows.append(f"| {n * n}R（N = {s['N_pipe']}） | {STK_TR[tr]} | {STK_RT[rt]} | {c['gamma']:g} | {c['rho_star']:.3g} | "
                            f"{c['eta']:g} | {c['rho_sat']:.3g} | **{c['k']}** | **{c['M']}** | {c['lam']:.3g} | {c['edge_tbps']:.1f} | "
                            f"{100 * c['edge_vs_o1t']:+.0f}% | {c['router_now_tbps']:.0f} |")
    return "\n".join(rows) + ("\n\n<p class=\"small\">\\(\\gamma\\)：单位注入下的最热边负载（最坏置换取方案四的 \\(n/2\\)，AllToAll 取方案四满载 AllToAll 实测）；"
                              "\\(\\rho^*=\\min(1,1/\\gamma)\\)；\\(\\rho_{sat}=\\eta\\rho^*\\)；\\(k=\\lceil 1/\\rho_{sat}\\rceil\\)。"
                              "die 边带宽 = M × 3.2T；“相对方案四” 为相对第 2、3 章方案四无阻塞所需单边带宽；"
                              "NOW die router 合计 = 5 口 × M × 3.2T。</p>")


def t_stk_die(ds, _):
    a, b = ds[4]["stk"], ds[8]["stk"]
    rows = ["| 量 | 16R（4×4） | 64R（8×8） | 说明 |", "|---|---:|---:|---|"]

    def line(lbl, f, note=""):
        rows.append(f"| {lbl} | {f(a)} | {f(b)} | {note} |")

    line("单 Reticle 带宽 \\(B_{die}\\)", lambda s: f"{s['die_bw_tbps']:g}T（{s['ports400_die']} × 400GE）")
    line("**SW die 流水线数 N**", lambda s: f"**{s['N_pipe']}**", "\\(N=B_{die}/3.2\\mathrm T\\)；每条 8 × 400GE")
    line("全芯片流水线", lambda s: f"{s['pipes_total']}", "409.6T / 3.2T，与切分无关")
    line("OE die / Reticle", lambda s: f"1 × {s['oe_tbps']:g}T", "OE 带宽 = SW die 线路侧带宽 \\(B_{die}\\)")
    line("OE 光引擎切片", lambda s: f"{s['oe_slices']} × {s['pipe_tbps']:g}T", "与流水线一一对应，每片 "
         f"{a['slice_lanes']} 路 200G / {a['slice_fibres']} 芯")
    line("光纤 / Reticle（全芯片）", lambda s: f"{s['fibres_die']}（{s['fibres_total']}）",
         "单纤单波 200G，收发分纤；不含外置光源输入纤")
    line("FAU / OE die", lambda s: f"{s['n_fau']}", f"每个 FAU {a['fau_fibres']} 芯")
    line("OE 混合键合信号区（收 + 发）", lambda s: f"{s['hb_oe_mm2']:.2f} mm²",
         f"{a['hb_pitch_um']:g} µm 间距、{a['hb_gbps']:g} Gbps/pin、50% 信号 ⇒ {a['hb_tbps_mm2']:.1f} T/mm²")
    for rt in ("buf", "bl"):
        line(f"平面数 M（最坏置换，{STK_RT[rt]}）", lambda s, rt=rt: f"{s['cfg']['worst_' + rt]['M']}（k = {s['cfg']['worst_' + rt]['k']}）")
    c = "worst_buf"
    line("交换引擎端口（buffered）", lambda s: f"{s['N_pipe']} + {s['cfg'][c]['M']}", "线路侧 N + 交换侧 M，每口 3.2T")
    line("SW↔NOW 垂直带宽（buffered，单方向）", lambda s: f"{s['cfg'][c]['sw_vert_tbps']:.1f}T", "线路侧 N×3.2T（经 NOW 转 OE）+ 交换侧 M×3.2T")
    line("SW 混合键合信号区（收 + 发）", lambda s: f"{s['cfg'][c]['hb_sw_mm2']:.1f} mm²", "键合假设同 OE 行")
    line("die 边 SIO 线密度（buffered，25 mm 边）", lambda s: f"{s['cfg'][c]['dens_25']:.2f} T/mm", "单方向")
    line("buffered 输入缓冲 / NOW die", lambda s: f"{s['cfg'][c]['buf_now_mb']:.2f} MB",
         f"每 mesh 输入口 RTT × 3.2T = {a['rtt_ns']:.0f} ns × 3.2T ≈ {a['buf_port_kb']:.1f} KB，4 口 × M")
    return "\n".join(rows)


TABLES = {"lat_calc": t_lat_calc, "stk_k": t_stk_k, "stk_die": t_stk_die, "bw": t_bw, "wire": t_wire, "lat": t_lat, "power": t_power, "scen": t_scen, "summary": t_summary,
          "cross": t_cross, "s3": t_s3, "ports": t_ports,
          "sc_speed": t_sc_speed, "sc_wire": t_sc_wire, "sc_lat": t_sc_lat, "sc_power": t_sc_power}


def fill(text: str, ds) -> str:
    def tab(m):
        return TABLES[m.group(1)](ds, int(m.group(2)))

    text = re.sub(r"<!-- TAB:(\w+):(\d) -->", tab, text)

    def val(m):
        n, sc, path, f = m.group(1), m.group(2), m.group(3), m.group(4)
        v = get(ds, n, sc, path)
        if f.endswith("%"):
            return f"{100 * v:{f[:-1]}}%"
        if f.endswith("d") and isinstance(v, float) and abs(v - round(v)) < 1e-6:
            v = int(round(v))
        return format(v, f)

    text = re.sub(r"\{\{(\d)\|(\w+)\|([\w/.]+)\|([^}]*)\}\}", val, text)
    left = re.findall(r"\{\{[^}]*\}\}", text)
    assert not left, left[:5]
    return text


def build_toc(tokens) -> str:
    out = ["<ul>"]
    for tk in tokens:
        out.append(f'<li class="top"><a href="#{tk["id"]}">{tk["name"]}</a>')
        if tk["children"]:
            out.append("<ul>" + "".join(f'<li class="sec"><a href="#{c["id"]}">{c["name"]}</a></li>' for c in tk["children"]) + "</ul>")
        out.append("</li>")
    out.append("</ul>")
    return "".join(out)


def render(body: str, toc: str, pages: dict) -> str:
    html = HS.render(body, toc, pages)
    return (html.replace('content: "HyperSwitch 交换架构研究报告"', f'content: "{TITLE}"')
            .replace("<title>HyperSwitch 交换架构研究报告</title>", f"<title>{TITLE}</title>")
            .replace("</style>", "td b, td strong{color:#1F3B5C;} tbody td:first-child{white-space:nowrap;}"
                      ".cover{height:auto !important;} .cover .band{padding:30mm 16mm 18mm 16mm !important;}"
                      ".cover .tag{margin-bottom:5px;} .cover .meta{position:static !important;margin-top:12mm;}</style>"))


def relink(pdf: Path):
    """Chrome 把相对链接打印成 file:// 绝对路径；改回相对 output/ 的路径，目录整体拷贝后仍可打开。"""
    import pymupdf

    doc = pymupdf.open(pdf)
    n = 0
    for page in doc:
        for ln in page.get_links():
            target = ln.get("file") or ln.get("uri") or ""
            for sub in ("/mapping/", "/data/"):
                if sub in target:
                    page.delete_link(ln)
                    page.insert_link({"kind": pymupdf.LINK_LAUNCH, "from": ln["from"],
                                      "file": target[target.rfind(sub) + 1:]})
                    n += 1
                    break
    doc.save(pdf.with_suffix(".tmp.pdf"))
    doc.close()
    pdf.with_suffix(".tmp.pdf").replace(pdf)
    return n


def main():
    import markdown
    import shutil

    import export_mapping

    ds = load_data()
    md_text = "\n\n".join(f.read_text() for f in sorted(SRC.glob("*.md")))
    md_text = fill(md_text, ds)
    md_text = HS.conv_custom(md_text)
    md_text = HS.conv_math(md_text)
    md = markdown.Markdown(extensions=["tables", "attr_list", "md_in_html", "fenced_code", "toc", "sane_lists"],
                           extension_configs={"toc": {"toc_depth": "1-2", "title": "", "marker": "[[NO-AUTO-TOC]]"}})
    body = md.convert(md_text)
    toc = build_toc(md.toc_tokens)
    BUILD.mkdir(exist_ok=True)
    out = BUILD / "report.html"
    out.write_text(render(body, toc, {"_": ""}))
    print("html written", out)
    if "--pdf" in sys.argv:
        import pymupdf
        OUT.mkdir(exist_ok=True)
        export_mapping.main()
        (OUT / "data").mkdir(exist_ok=True)
        for f in DATA.glob("dsl_*.json"):
            shutil.copy2(f, OUT / "data" / f.name)
        HS.PDF = PDF
        HS.print_pdf(out)
        doc = pymupdf.open(PDF)
        pages = {}
        for _, title, pno in doc.get_toc():
            pages.setdefault(title.strip(), pno)
        doc.close()
        out.write_text(render(body, toc, pages))
        HS.print_pdf(out)
        print("relinked", relink(PDF))
        doc = pymupdf.open(PDF)
        print("pdf written", PDF, "pages", doc.page_count, "toc", len(doc.get_toc()))
        doc.close()


if __name__ == "__main__":
    main()
