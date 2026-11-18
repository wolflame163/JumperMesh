#!/usr/bin/env python3
"""DSL 细分方案：单 Reticle 3D 堆叠（NOW die + SW die + OE die）与可配置 NOW 走线。

每个 Reticle = 底层 NOW die + 顶层 SW die（L1/L2/L3 switch + 流水线）+ 顶层 1 颗 OE die（同第 5 章）。

- SW die：L1/L2/L3 三个交换核，各 B_die；跨 die 的逻辑链路经混合键合落到 NOW die 的垂直端口：
  上行 L1_out / L2_out 各 N-1 条 b 粒度 lane，下行 L2_in / L3_in 各 N-1 条；同 die 链路在 SW die 内部完成。
- NOW die 逻辑功能：实现映射结果（方案一 / 二的逐条路径）在每颗 die 上的连线：
  垂直端口 ↔ 四边 SIO（注入 / 弹出），SIO ↔ SIO（feedthrough，直通或转向）。
- NOW die 物理实现：同构、可配置点对点走线。每个有向 die 边有 C 条 lane（lane k 即 SIO 端口 k）；
  die 内东西向 / 南北向各 2C 条行 / 列总线（lane k 直通 W-in k → E-out k 等）；
  每个出向 lane 一个静态 mux：{直通 lane k，两侧垂直方向入 lane k±w（稀疏转向），s 个上行垂直端口}；
  每个下行垂直端口一个静态 mux，接一组稀疏的入向 lane。
- lane 分配：逐条链路按直通段保持 lane、转向处 |Δlane| ≤ w，first-fit 分配；求每个 w 所需 lane 数 K(w)，
  取 K(w) ≤ C 的最小 w。垂直端口按二分匹配求最小 s。最后按 mux 静态配置逐条回放，校验全部逻辑链路。

Usage:
  python3 dsl_now_stack.py --sizes 4 8 --data report_dsl_400t/data
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

import dsl_mesh_400t as M
import dsl_o1t_stack as S

SCHEMES = {"s1": "xy_o1turn_cw", "s2": "manhattan"}
FACES = ("N", "E", "S", "W")
DIR = {(-1, 0): "N", (1, 0): "S", (0, 1): "E", (0, -1): "W"}
OPP = {"N": "S", "S": "N", "E": "W", "W": "E"}
W_LIST = (0, 1, 2, 4, 8, 16, 32, 64)


def DELTAS(U: int) -> tuple:
    """垂直端口池的备用端口数 Δ：0、U/8、U/4、U/2（向上取整）。"""
    return (0, math.ceil(U / 8), math.ceil(U / 4), math.ceil(U / 2))

WIRE_GBPS = S.HB_GBPS_PER_PIN  # die 内每根信号线速率（与混合键合同口径）


def face_of(a, b) -> str:
    return DIR[(b[0] - a[0], b[1] - a[1])]


def links_of(r: dict) -> list[dict]:
    out = []
    for key, p in r["paths"].items():
        st = int(key.split("|")[0])
        nodes = [tuple(x) for x in p]
        if len(nodes) < 2:
            continue
        edges = [(nodes[i], nodes[i + 1]) for i in range(len(nodes) - 1)]
        segs, cur = [], [edges[0]]
        for e in edges[1:]:
            if face_of(*e) == face_of(*cur[-1]):
                cur.append(e)
            else:
                segs.append(cur)
                cur = [e]
        segs.append(cur)
        out.append(dict(key=key, stage=st, nodes=nodes, edges=edges, segs=segs,
                        up="L1_out" if st == 1 else "L2_out", down="L2_in" if st == 1 else "L3_in"))
    return out


# ------------------------------------------------------------------ 逻辑功能：逐 die 连线需求


def die_demand(n: int, links: list[dict]) -> dict:
    per = defaultdict(Counter)
    sig = defaultdict(Counter)
    for L in links:
        nodes = L["nodes"]
        for i, d in enumerate(nodes):
            did = d[0] * n + d[1]
            if i == 0:
                f = face_of(d, nodes[1])
                per[did]["inject"] += 1
                sig[did][("inj", L["up"], f)] += 1
            elif i == len(nodes) - 1:
                f = face_of(d, nodes[i - 1])
                per[did]["eject"] += 1
                sig[did][("ej", L["down"], f)] += 1
            else:
                fi, fo = face_of(d, nodes[i - 1]), face_of(d, nodes[i + 1])
                kind = "ft_straight" if fi == OPP[fo] else "ft_turn"
                per[did][kind] += 1
                sig[did][("ft", fi, fo)] += 1
    for c in per.values():
        c["ft"] = c["ft_straight"] + c["ft_turn"]
        c["total"] = c["inject"] + c["eject"] + c["ft"]
    keys = ("inject", "eject", "ft_straight", "ft_turn", "ft", "total")
    stat = {k: dict(max=max(per[d][k] for d in range(n * n)),
                    min=min(per[d][k] for d in range(n * n)),
                    mean=sum(per[d][k] for d in range(n * n)) / (n * n)) for k in keys}
    distinct = len({tuple(sorted(sig[d].items())) for d in range(n * n)})
    tot = {k: sum(per[d][k] for d in range(n * n)) for k in keys}
    return dict(stat=stat, total=tot, distinct_patterns=distinct,
                turn_share_ft=tot["ft_turn"] / max(tot["ft"], 1),
                per_die={d: dict(per[d]) for d in range(n * n)})


# ------------------------------------------------------------------ lane 分配（行列总线 + 稀疏转向）


def spread(x: int, w: int, mask: int) -> int:
    y = x
    for d in range(1, w + 1):
        y |= (x << d) | (x >> d)
    return y & mask


def lowest(x: int) -> int:
    return (x & -x).bit_length() - 1


def up_ports(f: str, k: int, P: int, s: int) -> list[int]:
    """lane (f, k) 可接的垂直端口（池内 P 个端口中的 s 个）：固定伪随机交错，全部 die 相同。"""
    if s >= P:
        return list(range(P))
    rng = random.Random((FACES.index(f) * 1_000_003 + k) * 131 + P)
    return sorted(rng.sample(range(P), s))


def assign_lanes(links: list[dict], w: int, cap: int, order):
    """first-fit lane 分配：直通段保持 lane，转向处 |Δlane| ≤ w。order 为排序名或随机种子。"""
    occ = defaultdict(int)
    mask = (1 << cap) - 1
    if order == "long":
        seq = sorted(links, key=lambda L: (-len(L["edges"]), L["key"]))
    elif order == "short":
        seq = sorted(links, key=lambda L: (len(L["edges"]), L["key"]))
    elif order == "pos":  # 按起点几何位置（区间图 first-fit 的自然序）
        seq = sorted(links, key=lambda L: (L["nodes"][0], -len(L["edges"]), L["key"]))
    else:
        seq = sorted(links, key=lambda L: (-len(L["segs"]), -len(L["edges"]), L["key"]))
        random.Random(order).shuffle(seq)
        seq.sort(key=lambda L: -len(L["segs"]))
    lanes = {}
    for L in seq:
        free = []
        for sg in L["segs"]:
            u = 0
            for e in sg:
                u |= occ[e]
            free.append(~u & mask)
        R = [free[0]]
        for i in range(1, len(free)):
            R.append(free[i] & spread(R[-1], w, mask))
        if not R[-1]:
            return None, None
        ls = [lowest(R[-1])]
        for i in range(len(free) - 2, -1, -1):
            l1 = ls[-1]
            lo, hi = max(0, l1 - w), min(cap - 1, l1 + w)
            win = ((1 << (hi + 1)) - 1) ^ ((1 << lo) - 1)
            ls.append(lowest(R[i] & win))
        ls.reverse()
        for sg, l in zip(L["segs"], ls):
            for e in sg:
                occ[e] |= 1 << l
        lanes[L["key"]] = ls
    used = max((max(v) for v in lanes.values()), default=-1) + 1
    return lanes, used


ORDERS = ("pos", "long", "short") + tuple(range(12))


def lanes_needed(links, w, C):
    best = None
    for order in ORDERS:
        _, k = assign_lanes(links, w, 4 * C, order)
        if k is not None and (best is None or k < best[0]):
            best = (k, order)
    return best


def bipartite(demands: list[tuple], P: int, s: int):
    """demands: [(face, lane, link_key)]；Kuhn 增广路匹配，返回 {link_key: port} 或 None。"""
    adj = [up_ports(f, k, P, s) for f, k, _ in demands]
    match_p = [-1] * P

    def aug(i, seen):
        for p in adj[i]:
            if p in seen:
                continue
            seen.add(p)
            if match_p[p] < 0 or aug(match_p[p], seen):
                match_p[p] = i
                return True
        return False

    for i in range(len(demands)):
        if not aug(i, set()):
            return None
    return {demands[i][2]: p for p, i in enumerate(match_p) if i >= 0}


def vertical_bind(links, lanes, P, s):
    """lane 已定后，按 (die, 端口池) 做二分匹配，把每条链路绑到一个垂直端口。"""
    groups = defaultdict(list)
    for L in links:
        src, dst = L["nodes"][0], L["nodes"][-1]
        ls = lanes[L["key"]]
        groups[("up", src, L["up"])].append((face_of(src, L["nodes"][1]), ls[0], L["key"]))
        groups[("dn", dst, L["down"])].append((face_of(dst, L["nodes"][-2]), ls[-1], L["key"]))
    bind = {"up": {}, "dn": {}}
    for (kind, _, _), dem in groups.items():
        m = bipartite(dem, P, s)
        if m is None:
            return None
        bind[kind].update(m)
    return bind["up"], bind["dn"]


def min_s(links, lanes, P):
    for s in range(1, P + 1):
        bd = vertical_bind(links, lanes, P, s)
        if bd:
            return s, bd
    raise AssertionError


# ------------------------------------------------------------------ 静态配置生成与回放校验


def build_config(n, links, lanes, bind_up, bind_dn, w, U, s):
    """每颗 die：out[(face, lane)] = 选择；down[(pool, port)] = (face, lane)。"""
    cfg = defaultdict(lambda: {"out": {}, "down": {}})
    for L in links:
        nodes, ls = L["nodes"], lanes[L["key"]]
        lane_e = []
        for sg, l in zip(L["segs"], ls):
            lane_e += [l] * len(sg)
        for i, d in enumerate(nodes):
            did = d[0] * n + d[1]
            c = cfg[did]
            if i < len(nodes) - 1:
                fo, lo = face_of(d, nodes[i + 1]), lane_e[i]
                if i == 0:
                    p = bind_up[L["key"]]
                    assert p in up_ports(fo, lo, U, s)
                    sel = ("up", L["up"], p)
                else:
                    fi, li = face_of(d, nodes[i - 1]), lane_e[i - 1]
                    if fi == OPP[fo]:
                        assert li == lo
                        sel = ("straight", fi, li)
                    else:
                        assert abs(li - lo) <= w
                        sel = ("turn", fi, li)
                assert (fo, lo) not in c["out"], "出向 lane 被两路驱动"
                c["out"][(fo, lo)] = sel
            else:
                fi, li = face_of(d, nodes[i - 1]), lane_e[i - 1]
                p = bind_dn[L["key"]]
                assert p in up_ports(fi, li, U, s)
                assert (L["down"], p) not in c["down"]
                c["down"][(L["down"], p)] = (fi, li)
    return cfg


def replay(n, links, cfg, bind_up) -> int:
    """只用各 die 的 mux 静态配置，从每个上行端口出发追踪到下行端口，核对逻辑链路。"""
    step = {"N": (-1, 0), "S": (1, 0), "E": (0, 1), "W": (0, -1)}
    consumers = {}
    for did, c in cfg.items():
        for (fo, lo), sel in c["out"].items():
            if sel[0] in ("straight", "turn"):
                k = (did, sel[1], sel[2])
                assert k not in consumers, "入向 lane 被两路使用"
                consumers[k] = ("out", fo, lo)
        for (pool, p), (fi, li) in c["down"].items():
            k = (did, fi, li)
            assert k not in consumers
            consumers[k] = ("down", pool, p)
    ok = 0
    for L in links:
        src = L["nodes"][0]
        did = src[0] * n + src[1]
        start = [(fo, lo) for (fo, lo), sel in cfg[did]["out"].items()
                 if sel == ("up", L["up"], bind_up[L["key"]])]
        assert len(start) == 1
        fo, lo = start[0]
        r, c_ = src
        hops = 0
        while True:
            dr, dc = step[fo]
            r, c_ = r + dr, c_ + dc
            hops += 1
            nxt = consumers[(r * n + c_, OPP[fo], lo)]
            if nxt[0] == "down":
                assert (r, c_) == L["nodes"][-1] and nxt[1] == L["down"]
                assert hops == len(L["edges"])
                ok += 1
                break
            _, fo, lo = nxt
    return ok


# ------------------------------------------------------------------ 主流程


def evaluate(n: int, d: dict, stk: dict) -> dict:
    N = n * n
    U = N - 1
    out = dict(n=n, N_die=N, U=U, wire_gbps=WIRE_GBPS, w_list=list(W_LIST))
    b = d["xy_o1turn_cw"]["b_tbps"]
    b_die = M.SYSTEM_TBPS / N
    out.update(b_tbps=b, die_bw_tbps=b_die, N_pipe=stk["N_pipe"],
               sw_up_lanes=2 * U, sw_down_lanes=2 * U, sw_vert_lanes=4 * U,
               sw_vert_tbps=4 * U * b, sw_local_tbps=2 * b,
               sw_line_tbps=2 * b_die, sw_sw_tbps=3 * b_die,
               sw_hb_total_tbps=4 * U * b + 2 * b_die,
               hb_sw_mm2=(4 * U * b + 2 * b_die) / stk["hb_tbps_mm2"],
               hb_now_sw_vert_mm2=4 * U * b / stk["hb_tbps_mm2"],
               wires_per_lane=b * 1000 / WIRE_GBPS)
    for tag, sc in SCHEMES.items():
        r = d[sc]
        C = r["C"]
        links = links_of(r)
        dem = die_demand(n, links)
        curve = {}
        for w in W_LIST:
            k, order = lanes_needed(links, w, C)
            curve[w] = dict(K=k, order=order, K_over_C=k / C)
        w_star = next(w for w in W_LIST if curve[w]["K"] <= C)
        lanes, used = assign_lanes(links, w_star, C, curve[w_star]["order"])
        assert lanes is not None and used <= C
        # 垂直端口：每池 P = U + Δ 个端口（Δ 为备用端口），求二分匹配可行的最小 s
        vert = {}
        for dl in DELTAS(U):
            sv, bd = min_s(links, lanes, U + dl)
            vert[dl] = dict(s=sv, P=U + dl, bind=bd)
        s_star, P = vert[0]["s"], U
        bind_up, bind_dn = vert[0]["bind"]
        cfg = build_config(n, links, lanes, bind_up, bind_dn, w_star, P, s_star)
        ok = replay(n, links, cfg, bind_up)
        assert ok == len(links)
        for dl, v in vert.items():  # 备用端口方案也逐条回放
            c2 = build_config(n, links, lanes, *v["bind"], w_star, v["P"], v["s"])
            assert replay(n, links, c2, v["bind"][0]) == len(links)
        out_lanes = 4 * C

        def hw(w, sv, Pv, out_lanes=out_lanes):
            fan_out = 1 + 2 * (2 * w + 1) + 2 * sv
            fan_down = math.ceil(out_lanes * sv / Pv)
            xp = out_lanes * fan_out + 2 * Pv * fan_down
            bits = out_lanes * math.ceil(math.log2(fan_out)) + 2 * Pv * math.ceil(math.log2(fan_down))
            return dict(fan_out=fan_out, fan_down=fan_down, down_ports=2 * Pv, xp_lane=xp, cfg_bits=bits,
                        cfg_kb=bits / 8 / 1024, xp_bit=xp * out["wires_per_lane"])

        h = hw(w_star, s_star, P)
        full_out = 1 + 2 * C + 2 * U
        xp_full = out_lanes * full_out + 2 * U * out_lanes
        bits_full = out_lanes * math.ceil(math.log2(full_out)) + 2 * U * math.ceil(math.log2(out_lanes))
        vtab = {dl: dict(s=v["s"], P=v["P"], **hw(w_star, v["s"], v["P"])) for dl, v in vert.items()}
        used_out = [len(c["out"]) for c in cfg.values()]
        turn_sel = [sum(1 for v in c["out"].values() if v[0] == "turn") for c in cfg.values()]
        straight_sel = [sum(1 for v in c["out"].values() if v[0] == "straight") for c in cfg.values()]
        inj_sel = [sum(1 for v in c["out"].values() if v[0] == "up") for c in cfg.values()]
        turn_dl = [abs(v[2] - fo_lo[1]) for c in cfg.values() for fo_lo, v in c["out"].items() if v[0] == "turn"]
        o = dict(scheme=sc, C=C, C_tbps=C * b, n_links=len(links), demand=dem, curve=curve,
                 w_star=w_star, K_star=curve[w_star]["K"], K_w0=curve[0]["K"], K_w0_over_C=curve[0]["K"] / C,
                 K_w0_extra=curve[0]["K"] / C - 1,
                 s_star=s_star, replay_ok=ok, vert={str(k): v for k, v in vtab.items()},
                 h_tracks=2 * C, v_tracks=2 * C, out_lanes=out_lanes, fan_turn=2 * (2 * w_star + 1), **h,
                 xp_lane_full=xp_full, cfg_bits_full=bits_full, fan_out_full=full_out, fan_down_full=out_lanes,
                 xp_ratio=xp_full / h["xp_lane"], bits_ratio=bits_full / h["cfg_bits"],
                 xp_bit_full=xp_full * out["wires_per_lane"],
                 lane_util_max=max(used_out) / out_lanes, lane_util_mean=sum(used_out) / len(used_out) / out_lanes,
                 out_used_max=max(used_out), turn_sel_max=max(turn_sel), straight_sel_max=max(straight_sel),
                 inj_sel=max(inj_sel), turn_dl_max=max(turn_dl, default=0),
                 turn_dl_mean=(sum(turn_dl) / len(turn_dl)) if turn_dl else 0.0,
                 turn_same_lane=sum(1 for x in turn_dl if x == 0) / max(len(turn_dl), 1),
                 edge_tbps_mm=C * b / M.DIE_H_MM)
        d_rec = DELTAS(U)[2]
        o["rec"] = dict(w=w_star, K=C, delta=d_rec, **vtab[d_rec])
        # w = 0（无转向窗口）的备选：lane 数放宽到 K(0)，即 SIO 端口多 K(0)/C − 1
        K0 = curve[0]["K"]
        lanes0, used0 = assign_lanes(links, 0, K0, curve[0]["order"])
        assert lanes0 is not None and used0 <= K0
        s0, bd0 = min_s(links, lanes0, U + d_rec)
        c0 = build_config(n, links, lanes0, *bd0, 0, U + d_rec, s0)
        assert replay(n, links, c0, bd0[0]) == len(links)
        o["w0"] = dict(w=0, K=K0, extra=K0 / C - 1, delta=d_rec, s=s0, P=U + d_rec,
                       edge_tbps=K0 * b, bus_wires=2 * K0 * out["wires_per_lane"],
                       row_wires_mm=2 * K0 * out["wires_per_lane"] / M.DIE_H_MM,
                       col_wires_mm=2 * K0 * out["wires_per_lane"] / M.DIE_W_MM,
                       **hw(0, s0, U + d_rec, 4 * K0))
        o["w0"]["xp_ratio"] = xp_full / o["w0"]["xp_lane"]
        if n == 4:
            o["example"] = example_die(n, links, lanes, cfg, n + 1)
        out[tag] = o
        print(f"{n}x{n} {tag}: C={C} K(w)={ {w: curve[w]['K'] for w in W_LIST} } w*={w_star} s*={s_star} "
              f"replay={ok}/{len(links)} {h} xp_ratio={xp_full / h['xp_lane']:.1f} vert={ {k: (v['s'], v['fan_out'], v['fan_down']) for k, v in vtab.items()} }")
    return out


def example_die(n, links, lanes, cfg, did):
    c = cfg[did]
    return dict(die=did,
                out=[[fo, lo, list(sel)] for (fo, lo), sel in sorted(c["out"].items())],
                down=[[pool, p, fi, li] for (pool, p), (fi, li) in sorted(c["down"].items())])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[4, 8])
    ap.add_argument("--data", default="report_dsl_400t/data")
    a = ap.parse_args()
    dd = Path(a.data)
    for n in a.sizes:
        d = json.loads((dd / f"dsl_{n}x{n}.json").read_text())
        stk = json.loads((dd / f"dsl_stk_{n}x{n}.json").read_text())
        r = evaluate(n, d, stk)
        (dd / f"dsl_now_{n}x{n}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
