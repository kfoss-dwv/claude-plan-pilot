#!/usr/bin/env python3
"""Render a logic-flow spec (JSON) to inline SVG: standard flowchart shapes,
semantic change colours, and components laid out on a container grid.

Usage:
  flow.py spec.json -o figure.html              # <figure> per view: svg + legend
  flow.py spec.json --preview preview.html      # standalone page for eyeballing
  flow.py spec.json --svg flow.svg              # self-contained .svg per view (CSS embedded)
  flow.py spec.json --view diff -o diff.html    # before | after | diff | both (default)
  flow.py --key                                 # legend of every shape and state

Layout (layout_view) and drawing (emit_svg) are separate: layout_view returns
plain geometry (boxes, polylines, label anchors) that any emitter can draw.
See ../SKILL.md for the spec format. Stdlib only.
"""
import argparse
import html
import itertools
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

LINE = 16          # text line height inside a node
NAME_CH = 7.6      # px per char, 12.5px mono 600 (node name)
SUB_CH = 6.2       # px per char, 11.5px sans (node sub line, edge label)
PAD = 14           # text inset from a node's side
HEX = 14           # hexagon tip depth
MIN_RECT = 132     # narrowest action / call / state box
RANK_GAP = 52      # vertical gap between ranks inside a container
NODE_GAP = 40      # min horizontal gap between nodes in one rank
GUTTER = 24        # first gutter lane, left of a container's nodes
LANE = 14          # spacing between gutter lanes
CH_LANE = 8        # spacing between channel lanes
C_PAD = 20         # container inner padding (sides, bottom)
C_HEAD = 40        # container label band
C_HGAP = 96        # gap between grid columns (hand-off lanes + labels)
C_VGAP = 64        # gap between grid rows
MARGIN = 16
G_PAD = 14         # group box inset around its nodes (sides, bottom)
G_HEAD = 32        # group label band above its top nodes
G_GAP = 20         # min gap between two group boxes
RIM = 7            # store (cylinder) lid depth

SHAPES = ("start", "action", "decision", "call", "state", "stop", "store")
RECTS = ("action", "call", "state", "store")
STATES = ("bug", "new", "changed", "removed", "focus", "warn")
KINDS = ("service", "vendor", "stage", "client")
VIEWS = ("before", "after", "diff")

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "flow.css"
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')

SHAPE_LABELS = {"start": "entry", "action": "action", "decision": "decision", "call": "call into another component",
                "state": "state", "stop": "stop / return / error", "store": "data store"}
STATE_LABELS = {"bug": "where the bug fires", "new": "new / proposed", "changed": "changed",
                "removed": "removed", "focus": "what you asked about", "warn": "silent bad path", "ok": "success"}
VIEW_LABELS = {"before": "Today", "after": "Proposed", "diff": "Today → proposed"}


def die(msg):
    sys.exit(f"flow.py: {msg}")


def warn(msg):
    print(f"flow.py: warning: {msg}", file=sys.stderr)


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return str(int(round(n))) if abs(n - round(n)) < 0.05 else f"{n:.1f}"


def ceil4(v):
    return int(math.ceil(v / 4) * 4)


# ---------- selection: what one view shows ----------

def in_view(item, view):
    only = item.get("only")
    if only not in (None, "before", "after"):
        die(f"{item.get('id', item)}: only must be 'before' or 'after'")
    return view == "diff" or not only or only == view


def view_state(item, view):
    s = item.get("state")
    if isinstance(s, dict):
        s = s.get(view) or ((s.get("after") or s.get("before")) if view == "diff" else None)
    if not s and item.get("only") and (view == "diff" or item["only"] == "after"):
        # What only the proposal has is new wherever it shows; what only today has is removed in the diff.
        s = {"before": "removed", "after": "new"}[item["only"]]
    if s and s not in STATES:
        die(f"unknown state {s!r}; use one of {STATES}")
    return s or ""


def per_view(v, view):
    """A value may differ by view: {"before": ..., "after": ...}; the diff shows the proposal's."""
    if isinstance(v, dict):
        return v.get(view) or ((v.get("after") or v.get("before")) if view == "diff" else None)
    return v


def has_views(spec):
    items = spec.get("nodes", []) + spec.get("edges", []) + spec.get("containers", [])
    return any(i.get("only") or any(isinstance(i.get(k), dict) for k in ("state", "label", "sub")) for i in items)


def select(spec, view):
    conts = [dict(c) for c in spec.get("containers", []) if in_view(c, view)]
    framed = bool(spec.get("containers"))
    if not framed:
        conts = [{"id": "_", "label": "", "row": 0, "col": 0}]
    C = {}
    for c in conts:
        c.setdefault("kind", "service")
        if c["kind"] not in KINDS:
            die(f"container {c['id']}: kind must be one of {KINDS}")
        c["state"] = view_state(c, view)
        c["framed"] = framed
        c.setdefault("row", 0), c.setdefault("col", 0)
        c.setdefault("rowspan", 1), c.setdefault("colspan", 1)
        C[c["id"]] = c
    all_ids = {n["id"] for n in spec["nodes"]}
    nodes = []
    for raw in spec["nodes"]:
        if not in_view(raw, view):
            continue
        n = dict(raw)
        n.setdefault("shape", "action")
        if n["shape"] not in SHAPES:
            die(f"node {n['id']}: shape must be one of {SHAPES}")
        if framed:
            if "container" not in n:
                die(f"node {n['id']}: every node needs a container once containers are used")
            if n["container"] not in C:
                if any(c["id"] == n["container"] for c in spec["containers"]):
                    continue  # its container is hidden in this view
                die(f"node {n['id']}: unknown container {n['container']!r}")
        else:
            n["container"] = "_"
        n["state"] = view_state(n, view)
        sub = per_view(n.get("sub"), view) or []
        n["lines"] = [n["name"]] + ([sub] if isinstance(sub, str) else list(sub))
        nodes.append(n)
    N = {n["id"]: n for n in nodes}
    edges = []
    for raw in spec.get("edges", []):
        for k in ("from", "to"):
            if raw[k] not in all_ids:
                die(f"edge {raw['from']} -> {raw['to']}: unknown node {raw[k]!r}")
        if not in_view(raw, view) or raw["from"] not in N or raw["to"] not in N:
            continue
        e = dict(raw)
        e["state"] = view_state(e, view)
        e["label"] = per_view(e.get("label"), view)
        edges.append(e)
    for raw in spec.get("groups", []):
        if not in_view(raw, view):
            continue
        g = dict(raw)
        g["state"] = view_state(g, view)
        g["members"] = [N[i] for i in g["nodes"] if i in N]
        if not g["members"]:
            continue
        if len({n["container"] for n in g["members"]}) > 1:
            die(f"group {g['id']}: all its nodes must share one container")
        for n in g["members"]:
            if n.get("group"):
                die(f"node {n['id']}: in groups {n['group']} and {g['id']}; a node belongs to one group")
            n["group"] = g["id"]
        C[g["members"][0]["container"]].setdefault("groups", []).append(g)
    return nodes, N, edges, C


# ---------- graph structure ----------

def measure(n):
    lines = n["lines"]
    tw = max([len(lines[0]) * NAME_CH] + [len(s) * SUB_CH for s in lines[1:]])
    th = LINE * len(lines)
    if n["shape"] == "decision":
        h = max(56, 2 * th + 24)
        w = max(112, tw / (1 - th / h) + 24)
    else:
        h = th + 20 + (2 * RIM if n["shape"] == "store" else 0)
        extra = {"start": h, "stop": 2 * HEX + 2 * PAD, "call": 2 * PAD + 16}.get(n["shape"], 2 * PAD)
        w = max(MIN_RECT if n["shape"] in RECTS else 96, tw + extra)
    n["w"], n["h"] = ceil4(w), ceil4(h)


def classify(nodes, N, edges):
    """Mark back edges (DFS from entries) and side exits (a branch that ends at once)."""
    out = defaultdict(list)
    for e in edges:
        out[e["from"]].append(e)
    color = {}
    roots = [n["id"] for n in nodes if n["shape"] == "start"] + [n["id"] for n in nodes]
    for root in roots:
        if root in color:
            continue
        color[root] = 1
        stack = [(root, iter(out[root]))]
        while stack:
            u, it = stack[-1]
            e = next(it, None)
            if e is None:
                color[u] = 2
                stack.pop()
                continue
            v = e["to"]
            if e.get("back") or color.get(v) == 1:
                e["_back"] = True
            elif v not in color:
                color[v] = 1
                stack.append((v, iter(out[v])))
    indeg = Counter(e["to"] for e in edges if not e.get("_back"))
    outdeg = Counter(e["from"] for e in edges)
    for u in nodes:
        outs = [e for e in out[u["id"]] if not e.get("_back") and N[e["to"]]["container"] == u["container"]]
        if len(outs) < 2:
            continue
        terminal = [outdeg[e["to"]] == 0 for e in outs]
        primary = next((e for e, t in zip(outs, terminal) if not t), outs[0])
        for e, t in zip(outs, terminal):
            if e is primary or e.get("exit") == "down" or e["to"] == u["id"]:
                continue
            if indeg[e["to"]] == 1 and (t or e.get("exit") == "right"):
                e["_side"] = True
                break
    return out


def ranks(cnodes, edges, out, N, cid):
    ids = {n["id"] for n in cnodes}
    side_of = {e["to"]: e["from"] for e in edges if e.get("_side") and e["to"] in ids}
    succ = defaultdict(list)
    for e in edges:
        if e.get("_back") or e.get("_side"):
            continue
        if e["from"] in ids and e["to"] in ids and e["to"] not in succ[e["from"]]:
            succ[e["from"]].append(e["to"])
    # A path that leaves the container and comes back still orders the two ends.
    for u in ids:
        seen, stack = set(), [e["to"] for e in out[u] if not e.get("_back") and e["to"] not in ids]
        while stack:
            v = stack.pop()
            if v in seen:
                continue
            seen.add(v)
            if v in ids:
                if v != u and v not in side_of and v not in succ[u]:
                    succ[u].append(v)
                continue
            stack += [e["to"] for e in out[v] if not e.get("_back")]
    rank = {u: 0 for u in ids if u not in side_of}
    for _ in range(len(ids)):
        changed = False
        for u in list(rank):
            for v in succ[u]:
                if v in rank and rank[v] < rank[u] + 1:
                    rank[v], changed = rank[u] + 1, True
        if not changed:
            break
    for v, u in side_of.items():
        rank[v] = rank[u]
    preds = defaultdict(list)
    for u in succ:
        for i, v in enumerate(succ[u]):
            preds[v].append((u, i))
    return rank, preds, side_of


# ---------- geometry helpers ----------

def port(n, side):
    return {"top": (n["cx"], n["y"]), "bottom": (n["cx"], n["y"] + n["h"]),
            "left": (n["x"], n["cy"]), "right": (n["x"] + n["w"], n["cy"])}[side]


def seg_hits(p, q, n, pad=3):
    x0, x1 = sorted((p[0], q[0]))
    y0, y1 = sorted((p[1], q[1]))
    return x1 > n["x"] - pad and x0 < n["x"] + n["w"] + pad and y1 > n["y"] - pad and y0 < n["y"] + n["h"] + pad


def path_hits(pts, nodes, skip):
    return [n for n in nodes if n["id"] not in skip
            and any(seg_hits(p, q, n) for p, q in zip(pts, pts[1:]))]


def label_w(text):
    return len(text) * SUB_CH


def segments(pts):
    return list(zip(pts, pts[1:]))


def crossings(paths):
    n = 0
    for p, q in itertools.combinations(paths, 2):
        for (a1, a2), (b1, b2) in itertools.product(segments(p), segments(q)):
            ah, bh = a1[1] == a2[1], b1[1] == b2[1]
            if ah != bh:
                (h1, h2), (v1, v2) = ((a1, a2), (b1, b2)) if ah else ((b1, b2), (a1, a2))
                if min(h1[0], h2[0]) < v1[0] < max(h1[0], h2[0]) and min(v1[1], v2[1]) < h1[1] < max(v1[1], v2[1]):
                    n += 1
            elif ah and a1[1] == b1[1]:
                if min(max(a1[0], a2[0]), max(b1[0], b2[0])) > max(min(a1[0], a2[0]), min(b1[0], b2[0])):
                    n += 1
            elif not ah and a1[0] == b1[0]:
                if min(max(a1[1], a2[1]), max(b1[1], b2[1])) > max(min(a1[1], a2[1]), min(b1[1], b2[1])):
                    n += 1
    return n


def interval_lanes(items, gap=10):
    """items: [(key, lo, hi)] -> {key: lane}, packing non-overlapping intervals into the same lane."""
    lanes, out = [], {}
    for key, lo, hi in sorted(items, key=lambda t: (t[2] - t[1], t[1])):
        for i, taken in enumerate(lanes):
            if all(hi + gap <= a or lo - gap >= b for a, b in taken):
                taken.append((lo, hi))
                out[key] = i
                break
        else:
            lanes.append([(lo, hi)])
            out[key] = len(lanes) - 1
    return out


# ---------- layout inside one container ----------

def group_box(g, m=None):
    """Box around a group's nodes, widened (about its centre) until the label and tag fit."""
    m = m or g["members"]
    x0, x1 = min(n["x"] for n in m) - G_PAD, max(n["x"] + n["w"] for n in m) + G_PAD
    need = len(g.get("label", "")) * 7.6 + len(g.get("tag", "")) * 7 + 48
    if x1 - x0 < need:
        x0, x1 = x0 - (need - x1 + x0) / 2, x1 + (need - x1 + x0) / 2
    y0 = min(n["y"] for n in m) - G_HEAD
    return x0, y0, x1, max(n["y"] + n["h"] for n in m) + G_PAD


def separate_groups(groups, placed):
    """Two groups sharing a rank must not overlap: push the right one, and everything placed
    right of it, across. Runs after each rank so the ranks below are placed against the result."""
    for _ in range(len(groups)):
        moved = False
        ms = [(g, [n for n in g["members"] if n in placed]) for g in groups]
        boxes = sorted(((group_box(g, m), m) for g, m in ms if m), key=lambda t: t[0][0])
        for (a, _), (b, m) in itertools.combinations(boxes, 2):
            if a[3] <= b[1] or b[3] <= a[1] or b[0] >= a[2] + G_GAP:
                continue
            split, dx = min(n["cx"] for n in m), a[2] + G_GAP - b[0]
            for n in placed:
                if n["cx"] >= split - 0.5:
                    n["x"] += dx
                    n["cx"] += dx
            moved = True
            break
        if not moved:
            return


def layout_container(c, cnodes, edges, out, N, cfg):
    if not cnodes:
        c["cw"], c["ch"] = 160, 40
        return []
    for n in cnodes:
        measure(n)
    if cfg.get("uniform", True):
        rw = max((n["w"] for n in cnodes if n["shape"] in RECTS), default=0)
        for n in cnodes:
            if n["shape"] in RECTS:
                n["w"] = rw
    rank, preds, side_of = ranks(cnodes, edges, out, N, c["id"])
    sides = defaultdict(list)
    for e in edges:
        if e.get("_side") and e["to"] in side_of:
            sides[e["from"]].append(e)
    by_rank = defaultdict(list)
    for n in cnodes:
        by_rank[rank[n["id"]]].append(n)
    nr = max(by_rank) + 1
    rank_h = [max(n["h"] for n in by_rank[r]) for r in range(nr)]
    # A group's label band sits above its top rank and its padding below its bottom rank.
    head, foot = [0] * nr, [0] * nr
    for g in c.get("groups", []):
        rs = [rank[n["id"]] for n in g["members"]]
        head[min(rs)], foot[max(rs)] = G_HEAD, G_PAD
    rank_top = [sum(rank_h[:r]) + r * RANK_GAP + sum(head[:r + 1]) + sum(foot[:r]) for r in range(nr)]

    for n in cnodes:
        r = rank[n["id"]]
        n["cy"] = rank_top[r] + rank_h[r] / 2
        n["y"] = n["cy"] - n["h"] / 2

    # x: each node wants to sit under its leftmost predecessor; a sweep resolves overlaps.
    # The first-listed branch of a fork keeps the spine; later branches step right.
    placed = []
    for r in range(nr):
        regular = [n for n in by_rank[r] if n["id"] not in side_of]
        keyed = []
        for i, n in enumerate(regular):
            ps = [(N[p]["cx"], k) for p, k in preds[n["id"]] if "cx" in N[p]]
            keyed.append((min(ps) if ps else (math.inf, 0), i, n))
        keyed.sort(key=lambda t: (t[0], t[1]))
        right = -math.inf
        for (want, _), _, n in keyed:
            if want == math.inf:
                want = 0 if right == -math.inf else right + NODE_GAP + n["w"] / 2
            n["cx"] = max(want, right + NODE_GAP + n["w"] / 2)
            right = n["cx"] + n["w"] / 2
            for e in sides[n["id"]]:
                s = N[e["to"]]
                gap = max(NODE_GAP, label_w(e.get("label") or "") + 28)
                s["cx"] = right + gap + s["w"] / 2
                right = s["cx"] + s["w"] / 2
        for n in by_rank[r]:
            n["x"] = n["cx"] - n["w"] / 2
            placed.append(n)
        separate_groups(c.get("groups", []), placed)

    ids = {n["id"] for n in cnodes}
    left_edge = min(n["x"] for n in cnodes)
    routes = []
    for e in edges:
        if e["from"] not in ids or e["to"] not in ids:
            continue
        u, v = N[e["from"]], N[e["to"]]
        ru, rv = rank[u["id"]], rank[v["id"]]
        r = {"edge": e}
        if e.get("_side"):
            r.update(kind="side", pts=[port(u, "right"), port(v, "left")])
        elif e.get("_back") or rv <= ru:
            r.update(kind="gutter")
        elif e.get("enter") in ("left", "right"):
            # Down from the source, then into the target's side, so it never shares a lane
            # with other edges into the same target.
            r.update(kind="enter", pts=[port(u, "bottom"), (u["cx"], v["cy"]), port(v, e["enter"])], rank=ru)
            if path_hits(r["pts"], cnodes, {u["id"], v["id"]}):
                warn(f"{u['id']} -> {v['id']} enters {v['id']}'s {e['enter']} side through another node")
        else:
            # Below the rank, and below a group that ends there, so a run out of a group clears its border.
            ych = rank_top[ru] + rank_h[ru] + foot[ru] + RANK_GAP / 2
            cands = []
            b_top = port(v, "top")
            if abs(u["cx"] - v["cx"]) < 1:
                cands.append(("straight", [port(u, "bottom"), b_top]))
            busy = u.get("_ports", set())
            if v["x"] >= u["x"] + u["w"] and "right" not in busy:
                cands.append(("elbow", [port(u, "right"), (v["cx"], u["cy"]), b_top]))
            if v["x"] + v["w"] <= u["x"] and "left" not in busy:
                cands.append(("elbow", [port(u, "left"), (v["cx"], u["cy"]), b_top]))
            cands.append(("channel", [port(u, "bottom"), (u["cx"], ych), (v["cx"], ych), b_top]))
            for kind, pts in cands:
                if not path_hits(pts, cnodes, {u["id"], v["id"]}):
                    r.update(kind=kind, pts=pts, rank=ru)
                    if kind == "elbow":  # a second elbow out of the same side would draw over this one
                        u.setdefault("_ports", set()).add("right" if pts[1][0] > pts[0][0] else "left")
                    break
            else:
                r.update(kind="gutter")
        routes.append(r)

    # Channel lanes: horizontal runs below one rank; runs into the same target share a lane.
    by_ch = defaultdict(list)
    for r in routes:
        if r["kind"] == "channel" and abs(r["pts"][1][0] - r["pts"][2][0]) > 0.5:
            by_ch[r["rank"]].append(r)
    for rk, rs in by_ch.items():
        groups = defaultdict(list)
        for r in rs:
            groups[r["edge"]["to"]].append(r)
        items = [(t, min(min(r["pts"][1][0], r["pts"][2][0]) for r in g), max(max(r["pts"][1][0], r["pts"][2][0]) for r in g))
                 for t, g in groups.items()]
        lanes = interval_lanes(items)
        k = max(lanes.values()) + 1
        for t, g in groups.items():
            dy = (lanes[t] - (k - 1) / 2) * CH_LANE
            for r in g:
                (x0, y0), (x1, y1), (x2, y2), b = r["pts"]
                r["pts"] = [(x0, y0), (x1, y1 + dy), (x2, y2 + dy), b]

    # Gutter lanes: skips and loop-backs run down the container's left side.
    gut = [r for r in routes if r["kind"] == "gutter"]
    items = []
    for i, r in enumerate(gut):
        u, v = N[r["edge"]["from"]], N[r["edge"]["to"]]
        items.append((i, min(u["cy"], v["cy"]) - 8, max(u["cy"], v["cy"]) + 8))
    lanes = interval_lanes(items, gap=4)
    for i, r in enumerate(gut):
        u, v = N[r["edge"]["from"]], N[r["edge"]["to"]]
        gx = left_edge - GUTTER - LANE * lanes[i]
        if u is v:
            r["pts"] = [(u["x"], u["cy"] - 8), (gx, u["cy"] - 8), (gx, u["cy"] + 8), (u["x"], u["cy"] + 8)]
        else:
            r["pts"] = [port(u, "left"), (gx, u["cy"]), (gx, v["cy"]), port(v, "left")]
        hit = path_hits(r["pts"], cnodes, {u["id"], v["id"]})
        if hit:
            warn(f"{u['id']} -> {v['id']} runs through {', '.join(h['id'] for h in hit)}; reorder edges or nodes")
    for r in routes:
        clip_to_group(r, N, c.get("groups", []))
        place_label(r)
    for g in c.get("groups", []):
        x0, y0, x1, y1 = group_box(g)
        g["x"], g["y"], g["w"], g["h"] = x0, y0, x1 - x0, y1 - y0
        hit = [n["id"] for n in cnodes if n.get("group") != g["id"] and seg_hits(
            (g["x"], g["y"]), (g["x"] + g["w"], g["y"] + g["h"]), n, pad=0)]
        if hit:
            warn(f"group {g['id']} box overlaps {', '.join(hit)}; move them out of its ranks or columns")

    # Normalise to a content box starting at (0, 0).
    boxes = [(n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]) for n in cnodes]
    boxes += [(g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"]) for g in c.get("groups", [])]
    boxes += [(x - 2, y - 2, x + 2, y + 2) for r in routes for x, y in r["pts"]]
    boxes += [r["lbox"] for r in routes if r.get("lbox")]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    c["cw"] = max(b[2] for b in boxes) - x0
    c["ch"] = max(b[3] for b in boxes) - y0
    shift(cnodes, routes, -x0, -y0, c.get("groups", []))
    return routes


def clip_to_group(r, N, groups):
    """An edge from outside a group into it stops at the group's top border (it calls the
    function, not a step inside it), so it never cuts through the group's label band.
    An edge leaving a group drops its label below the border."""
    u, v = N[r["edge"]["from"]], N[r["edge"]["to"]]
    gu = next((g for g in groups if g["id"] == u.get("group")), None)
    if gu and gu["id"] != v.get("group"):
        r["skip"] = max(G_PAD, group_box(gu)[3] - u["y"] - u["h"])
    g = next((g for g in groups if g["id"] == v.get("group")), None)
    if not g or u.get("group") == g["id"]:
        return
    (px, py), (qx, qy) = r["pts"][-2:]
    if abs(px - qx) < 0.5 and qy > py and abs(qy - v["y"]) < 0.5:
        y0 = group_box(g)[1]
        if py < y0:
            r["pts"][-1] = (qx, y0)


def place_label(r, prefer=None):
    text = r["edge"].get("label")
    r["lab"] = r["lbox"] = None
    if not text:
        return
    w = label_w(text)
    pts, kind = r["pts"], r["kind"]
    if kind == "gutter":
        (x, y1), (_, y2) = pts[1], pts[2]
        my = (y1 + y2) / 2
        r["lab"] = (x - 6, my, "middle", -90)
        r["lbox"] = (x - 20, my - w / 2, x - 2, my + w / 2)
        return
    horiz = [(p, q) for p, q in segments(pts) if p[1] == q[1] and abs(p[0] - q[0]) >= w + 16]
    if kind in ("side", "elbow") or (kind == "handoff" and horiz):
        (p, q) = max(horiz or segments(pts)[:1], key=lambda s: abs(s[0][0] - s[1][0]))
        if kind == "elbow":  # hug the source, above the run (clear of its group's border)
            x = p[0] + (1 if q[0] > p[0] else -1) * (8 + r.get("skip", 0))
            anchor = "start" if q[0] > p[0] else "end"
        else:
            x, anchor = (p[0] + q[0]) / 2, "middle"
        y = p[1] - 7
        r["lab"] = (x, y, anchor, 0)
        x0 = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
        r["lbox"] = (x0, y - 12, x0 + w, y + 3)
        return
    if kind == "channel" and len(pts) == 4:
        (x1, y), (x2, _) = pts[1], pts[2]
        if abs(x2 - x1) >= w + 16:
            x = (x1 + x2) / 2
            r["lab"] = (x, y - 7, "middle", 0)
            r["lbox"] = (x - w / 2, y - 19, x + w / 2, y - 4)
        else:
            r["lab"] = (x2 + 7, y + 15, "start", 0)
            r["lbox"] = (x2 + 7, y + 3, x2 + 7 + w, y + 18)
        return
    # Beside the first vertical run, just below where it starts.
    vert = next(((p, q) for p, q in segments(pts) if p[0] == q[0]), segments(pts)[0])
    (x, y), (_, y2) = vert
    y = (y + y2) / 2 + 4 if kind == "handoff" else y + 15 + r.get("skip", 0)
    r["lab"] = (x + 7, y, "start", 0)
    r["lbox"] = (x + 7, y - 12, x + 7 + w, y + 3)


def shift(nodes, routes, dx, dy, groups=()):
    for g in groups:
        g["x"] += dx
        g["y"] += dy
    for n in nodes:
        n["x"] += dx
        n["y"] += dy
        n["cx"] += dx
        n["cy"] += dy
    for r in routes:
        r["pts"] = [(x + dx, y + dy) for x, y in r["pts"]]
        if r.get("lab"):
            x, y, a, rot = r["lab"]
            r["lab"] = (x + dx, y + dy, a, rot)
        if r.get("lbox"):
            a, b, c, d = r["lbox"]
            r["lbox"] = (a + dx, b + dy, c + dx, d + dy)


# ---------- grid of containers ----------

def place_grid(C, cfg):
    hgap, vgap = cfg.get("hgap", C_HGAP), cfg.get("vgap", C_VGAP)
    cs = list(C.values())
    for c in cs:
        pad_x, pad_top, pad_bot = (C_PAD, C_HEAD, C_PAD) if c["framed"] else (0, 0, 0)
        c["need_w"] = c["cw"] + 2 * pad_x
        c["need_h"] = c["ch"] + pad_top + pad_bot
        if c["framed"]:
            c["need_w"] = max(c["need_w"], len(c.get("label", "")) * 7.4 + 2 * C_PAD + 60)
    ncols = max(c["col"] + c["colspan"] for c in cs)
    nrows = max(c["row"] + c["rowspan"] for c in cs)
    taken = {}
    for c in cs:
        for r in range(c["row"], c["row"] + c["rowspan"]):
            for k in range(c["col"], c["col"] + c["colspan"]):
                if (r, k) in taken:
                    die(f"containers {taken[(r, k)]} and {c['id']} overlap at row {r}, col {k}")
                taken[(r, k)] = c["id"]

    def sizes(n, start, span, need, gap):
        out = [0] * n
        for c in sorted(cs, key=lambda c: c[span]):
            a, s = c[start], c[span]
            have = sum(out[a:a + s]) + gap * (s - 1)
            if c[need] > have:
                extra = (c[need] - have) / s
                for i in range(a, a + s):
                    out[i] += extra
        return out

    colw = sizes(ncols, "col", "colspan", "need_w", hgap)
    rowh = sizes(nrows, "row", "rowspan", "need_h", vgap)
    X = [MARGIN + sum(colw[:i]) + i * hgap for i in range(ncols + 1)]
    Y = [MARGIN + sum(rowh[:i]) + i * vgap for i in range(nrows + 1)]
    valign = cfg.get("valign", "center")
    for c in cs:
        c["x"], c["y"] = X[c["col"]], Y[c["row"]]
        c["w"] = X[c["col"] + c["colspan"]] - hgap - c["x"]
        c["h"] = Y[c["row"] + c["rowspan"]] - vgap - c["y"]
        top = C_HEAD if c["framed"] else 0
        free = c["h"] - top - (C_PAD if c["framed"] else 0) - c["ch"]
        c["ox"] = c["x"] + (c["w"] - c["cw"]) / 2
        c["oy"] = c["y"] + top + (free / 2 if valign == "center" else 0)
    return hgap, vgap


def handoff_sides(A, B):
    """(axis, side it leaves the source, side it enters the target) for containers A -> B."""
    if B["col"] >= A["col"] + A["colspan"]:
        return "h", "right", "left"
    if B["col"] + B["colspan"] <= A["col"]:
        return "h", "left", "right"
    if B["row"] >= A["row"] + A["rowspan"]:
        return "v", "bottom", "top"
    return "v", "top", "bottom"


def handoffs(edges, N, C, hgap, vgap, all_nodes):
    """Edges between containers: leave the source container through the facing side,
    turn once in the gap next to it, enter the target from the facing side."""
    routes = []
    for e in edges:
        u, v = N[e["from"]], N[e["to"]]
        A, B = C[u["container"]], C[v["container"]]
        if A is B:
            continue
        d, out_side, in_side = handoff_sides(A, B)
        a, b = port(u, out_side), port(v, in_side)
        gap = {"right": (A["x"] + A["w"], A["x"] + A["w"] + hgap), "left": (A["x"] - hgap, A["x"]),
               "bottom": (A["y"] + A["h"], A["y"] + A["h"] + vgap), "top": (A["y"] - vgap, A["y"])}[out_side]
        routes.append({"edge": e, "kind": "handoff", "dir": d, "a": a, "b": b, "gap": gap})

    def pts(r, lane):
        a, b = r["a"], r["b"]
        if r["dir"] == "h":
            return [a, b] if abs(a[1] - b[1]) < 0.5 else [a, (lane, a[1]), (lane, b[1]), b]
        return [a, b] if abs(a[0] - b[0]) < 0.5 else [a, (a[0], lane), (b[0], lane), b]

    by_gap = defaultdict(list)
    for r in routes:
        by_gap[(r["dir"], r["gap"])].append(r)
    for (d, (g0, g1)), rs in by_gap.items():
        groups = []
        for r in rs:
            ends = {r["a"], r["b"]}
            hit = [g for g in groups if ends & g["ends"]]
            merged = {"ends": set(ends), "routes": [r]}
            for g in hit:
                merged["ends"] |= g["ends"]
                merged["routes"] += g["routes"]
                groups.remove(g)
            groups.append(merged)
        lo, hi = g0 + 18, g1 - 18
        k = len(groups)
        slots = [(lo + hi) / 2] if k == 1 else [lo + (hi - lo) * i / (k - 1) for i in range(k)]
        best = None
        for order in (itertools.permutations(range(k)) if k <= 7 else [range(k)]):
            paths = [pts(r, slots[si]) for gi, si in zip(range(k), order) for r in groups[gi]["routes"]]
            score = crossings(paths)
            if best is None or score < best[0]:
                best = (score, tuple(order))
        for gi, si in zip(range(k), best[1]):
            for r in groups[gi]["routes"]:
                r["pts"] = pts(r, slots[si])
    for r in routes:
        hit = path_hits(r["pts"], all_nodes, {r["edge"]["from"], r["edge"]["to"]})
        if hit:
            warn(f"hand-off {r['edge']['from']} -> {r['edge']['to']} runs through "
                 f"{', '.join(h['id'] for h in hit)}; move the node to its container's edge or reorder")
        clip_to_group(r, N, [g for c in C.values() for g in c.get("groups", [])])
        place_label(r)
    return routes


# ---------- whole view ----------

def layout_view(spec, view):
    """Plain geometry for one view: {'w','h','containers','nodes','routes'}. No SVG here."""
    cfg = spec.get("layout", {})
    nodes, N, edges, C = select(spec, view)
    out = classify(nodes, N, edges)
    for e in edges:  # ports a hand-off will use; internal elbows keep off them
        u, v = N[e["from"]], N[e["to"]]
        if u["container"] != v["container"]:
            _, so, si = handoff_sides(C[u["container"]], C[v["container"]])
            u.setdefault("_ports", set()).add(so)
            v.setdefault("_ports", set()).add(si)
    routes = []
    for c in C.values():
        cnodes = [n for n in nodes if n["container"] == c["id"]]
        routes += layout_container(c, cnodes, edges, out, N, cfg)
    hgap, vgap = place_grid(C, cfg)
    for c in C.values():
        cnodes = [n for n in nodes if n["container"] == c["id"]]
        mine = [r for r in routes if N[r["edge"]["from"]]["container"] == c["id"]]
        shift(cnodes, mine, c["ox"], c["oy"], c.get("groups", []))
    routes += handoffs(edges, N, C, hgap, vgap, nodes)
    boxes = [(c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]) for c in C.values() if c["framed"]]
    boxes += [(n["x"] - 6, n["y"] - 6, n["x"] + n["w"] + 6, n["y"] + n["h"] + 6) for n in nodes]
    boxes += [(x, y, x, y) for r in routes for x, y in r["pts"]]
    boxes += [r["lbox"] for r in routes if r.get("lbox")]
    x0 = min(0, min(b[0] for b in boxes) - MARGIN)
    y0 = min(0, min(b[1] for b in boxes) - MARGIN)
    return {"x0": math.floor(x0), "y0": math.floor(y0),
            "w": math.ceil(max(b[2] for b in boxes) + MARGIN - x0),
            "h": math.ceil(max(b[3] for b in boxes) + MARGIN - y0),
            "containers": list(C.values()), "nodes": nodes, "routes": routes}


# ---------- SVG emitter ----------

def shape_svg(n, cls, grow=0):
    x, y, w, h = n["x"] - grow, n["y"] - grow, n["w"] + 2 * grow, n["h"] + 2 * grow
    cx, cy, s = n["cx"], n["cy"], n["shape"]
    if s == "decision":
        pts = [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]
        return f'<polygon class="{cls}" points="{" ".join(f"{fmt(a)},{fmt(b)}" for a, b in pts)}"/>'
    if s == "stop":
        t = HEX + grow * 0.4
        pts = [(x + t, y), (x + w - t, y), (x + w, cy), (x + w - t, y + h), (x + t, y + h), (x, cy)]
        return f'<polygon class="{cls}" points="{" ".join(f"{fmt(a)},{fmt(b)}" for a, b in pts)}"/>'
    if s == "store" and not grow:
        rx, ry, top, bot = w / 2, RIM, y + RIM, y + h - RIM
        body = (f"M{fmt(x)} {fmt(top)} A{fmt(rx)} {ry} 0 0 1 {fmt(x + w)} {fmt(top)} V{fmt(bot)} "
                f"A{fmt(rx)} {ry} 0 0 1 {fmt(x)} {fmt(bot)} Z")
        rim = f"M{fmt(x)} {fmt(top)} A{fmt(rx)} {ry} 0 0 0 {fmt(x + w)} {fmt(top)}"
        return f'<path class="{cls}" d="{body}"/><path class="{cls} nd-rim" d="{rim}"/>'
    rx = {"start": h / 2, "state": 14, "store": 10}.get(s, 4)
    out = f'<rect class="{cls}" x="{fmt(x)}" y="{fmt(y)}" width="{fmt(w)}" height="{fmt(h)}" rx="{fmt(rx)}"/>'
    if s == "call" and not grow:
        out += "".join(f'<line class="nd-bar" x1="{fmt(bx)}" y1="{fmt(y)}" x2="{fmt(bx)}" y2="{fmt(y + h)}"/>'
                       for bx in (x + 8, x + w - 8))
    return out


def node_svg(n):
    cls = ["nd", f"nd-{n['shape']}"]
    if n["state"]:
        cls.append(f"st-{n['state']}")
    if n.get("outcome") == "ok" and not n["state"]:
        cls.append("oc-ok")
    o = [f'<g class="{" ".join(cls)}" data-node="{esc(n["id"])}">']
    if n["state"] == "focus":
        o.append(shape_svg(n, "nd-halo", grow=5))
    o.append(shape_svg(n, "nd-shape"))
    top = n["cy"] - LINE * len(n["lines"]) / 2 + 12 + (RIM / 2 if n["shape"] == "store" else 0)
    for i, line in enumerate(n["lines"]):
        tc = "nd-name" if i == 0 else "nd-sub"
        o.append(f'<text class="{tc}" x="{fmt(n["cx"])}" y="{fmt(top + LINE * i)}" text-anchor="middle">{esc(line)}</text>')
    o.append("</g>")
    return o


def container_svg(c):
    if not c["framed"]:
        return []
    cls = f"ct ct-{c['kind']}" + (f" st-{c['state']}" if c["state"] else "")
    tag = c.get("tag") or ("external" if c["kind"] == "vendor" else "")
    o = [f'<g class="{cls}">',
         f'<rect class="ct-box" x="{fmt(c["x"])}" y="{fmt(c["y"])}" width="{fmt(c["w"])}" height="{fmt(c["h"])}" rx="10"/>',
         f'<text class="ct-label" x="{fmt(c["x"] + 16)}" y="{fmt(c["y"] + 25)}">{esc(c.get("label", c["id"]).upper())}</text>']
    if tag:
        o.append(f'<text class="ct-tag" x="{fmt(c["x"] + c["w"] - 16)}" y="{fmt(c["y"] + 25)}" text-anchor="end">{esc(tag)}</text>')
    o.append("</g>")
    return o


def group_svg(g):
    cls = "gp" + (f" st-{g['state']}" if g["state"] else "")
    o = [f'<g class="{cls}">',
         f'<rect class="gp-box" x="{fmt(g["x"])}" y="{fmt(g["y"])}" width="{fmt(g["w"])}" height="{fmt(g["h"])}" rx="8"/>']
    if g.get("label"):
        o.append(f'<text class="gp-label" x="{fmt(g["x"] + 12)}" y="{fmt(g["y"] + 20)}">{esc(g["label"])}</text>')
    if g.get("tag"):
        o.append(f'<text class="gp-tag" x="{fmt(g["x"] + g["w"] - 12)}" y="{fmt(g["y"] + 20)}" text-anchor="end">{esc(g["tag"])}</text>')
    o.append("</g>")
    return o


def path_d(pts):
    (x0, y0), d = pts[0], f"M{fmt(pts[0][0])} {fmt(pts[0][1])}"
    for (px, py), (x, y) in zip(pts, pts[1:]):
        d += f" H{fmt(x)}" if abs(py - y) < 0.05 else f" V{fmt(y)}" if abs(px - x) < 0.05 else f" L{fmt(x)} {fmt(y)}"
    return d


def emit_svg(L, spec, view, pid):
    states = sorted({r["edge"]["state"] for r in L["routes"]})
    o = [f'<svg class="flow flow-main" viewBox="{L["x0"]} {L["y0"]} {L["w"]} {L["h"]}" '
         f'style="min-width:{spec.get("min_width", round(L["w"] * 0.75))}px;max-width:{round(L["w"] * 1.1)}px" role="img" '
         f'aria-labelledby="{pid}-title {pid}-desc" xmlns="http://www.w3.org/2000/svg">',
         f'<title id="{pid}-title">{esc(view_title(spec, view))}</title>',
         f'<desc id="{pid}-desc">{esc(view_desc(spec, view))}</desc>', "<defs>"]
    for s in states:
        o.append(f'<marker id="{pid}-ah{"-" + s if s else ""}" viewBox="0 0 10 10" refX="9" refY="5" '
                 f'markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
                 f'<path class="ah{" ah-" + s if s else ""}" d="M0 0L10 5L0 10z"/></marker>')
    o.append("</defs>")
    for c in L["containers"]:
        o += container_svg(c)
    for c in L["containers"]:
        for g in c.get("groups", []):
            o += group_svg(g)
    for r in L["routes"]:
        s = r["edge"]["state"]
        e = r["edge"]
        o.append(f'<path class="ed{" ed-" + s if s else ""}" data-edge="{esc(e["from"] + ">" + e["to"])}" '
                 f'd="{path_d(r["pts"])}" marker-end="url(#{pid}-ah{"-" + s if s else ""})"/>')
    for n in L["nodes"]:
        o += node_svg(n)
    for r in L["routes"]:
        if not r.get("lab"):
            continue
        x, y, anchor, rot = r["lab"]
        s = r["edge"]["state"]
        tr = f' transform="rotate({rot} {fmt(x)} {fmt(y)})"' if rot else ""
        o.append(f'<text class="ed-label{" lb-" + s if s else ""}" x="{fmt(x)}" y="{fmt(y)}" '
                 f'text-anchor="{anchor}"{tr}>{esc(r["edge"]["label"])}</text>')
    o.append("</svg>")
    return "\n".join(o)


def view_title(spec, view):
    t = spec.get("title", "Logic flow")
    return f"{t} · {view_label(spec, view)}" if view_label(spec, view) else t


def view_desc(spec, view):
    d = spec.get("desc", "")
    return d.get(view, d.get("after", "")) if isinstance(d, dict) else d


def view_label(spec, view):
    if view == "flow":
        return ""
    return spec.get("views", {}).get(view, VIEW_LABELS[view])


# ---------- legend ----------

def key_shape(shape):
    n = {"shape": shape, "x": 1, "y": 2, "w": 28, "h": 14, "cx": 15, "cy": 9, "state": ""}
    if shape == "decision":
        n.update(x=5, y=1, w=20, h=16)
    if shape == "store":
        n.update(x=7, y=0, w=16, h=18)
    return shape_svg(n, "nd-shape")


def key_state(state):
    cls = "st-" + state if state != "ok" else "oc-ok"
    ecls = "ed" + (f" ed-{state}" if state != "ok" else "")
    halo = '<rect class="nd-halo" x="12" y="0" width="18" height="18" rx="4"/>' if state == "focus" else ""
    return (f'<path class="{ecls}" d="M0 9 H12"/><g class="nd {cls}">{halo}'
            f'<rect class="nd-shape" x="15" y="3" width="12" height="12" rx="2"/></g>')


def legend(spec, L):
    labels = {**SHAPE_LABELS, **STATE_LABELS, **spec.get("legend", {})}
    shapes = [s for s in SHAPES if any(n["shape"] == s for n in L["nodes"])]
    used = {n["state"] for n in L["nodes"]} | {r["edge"]["state"] for r in L["routes"]}
    if any(n.get("outcome") == "ok" and not n["state"] for n in L["nodes"]):
        used.add("ok")
    states = [s for s in STATES + ("ok",) if s in used]
    return legend_html(shapes, states, labels)


def legend_html(shapes, states, labels):
    items = [f'<li><svg class="flow flow-key" viewBox="0 0 30 18" aria-hidden="true">{key_shape(s)}</svg>'
             f'{esc(labels[s])}</li>' for s in shapes]
    items += [f'<li><svg class="flow flow-key" viewBox="0 0 30 18" aria-hidden="true">{key_state(s)}</svg>'
              f'{esc(labels[s])}</li>' for s in states]
    return '<ul class="flow-legend">\n' + "\n".join(items) + "\n</ul>"


def full_key():
    return legend_html(SHAPES, STATES + ("ok",), {**SHAPE_LABELS, **STATE_LABELS})


# ---------- output ----------

def views_for(spec, arg):
    if arg == "both":
        return ["before", "after"] if has_views(spec) else ["flow"]
    return [arg]


def render(spec, view):
    L = layout_view(spec, "after" if view == "flow" else view)
    pid = f'{spec.get("id", "flow")}-{view}'
    svg = emit_svg(L, spec, view, pid)
    cap = view_label(spec, view)
    fig = (f'<figure class="flow-figure">\n' + (f'<figcaption class="flow-cap">{esc(cap)}</figcaption>\n' if cap else "")
           + f'<div class="flow-scroll">\n{svg}\n</div>\n{legend(spec, L)}\n</figure>')
    return svg, fig


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--key", action="store_true", help="print a legend of every shape and state and exit")
    ap.add_argument("--view", default="both", choices=("both",) + VIEWS,
                    help="both (default: today + proposed as two figures when the spec has before/after items), "
                         "before, after, or diff (one overlaid figure)")
    ap.add_argument("-o", "--out", help="write the <figure> fragment(s) here (default: stdout)")
    ap.add_argument("--preview", help="also write a standalone preview page")
    ap.add_argument("--svg", help="also write a self-contained .svg (one per view: name-before.svg, ...)")
    a = ap.parse_args()
    if a.key:
        print(full_key())
        return
    if not a.spec:
        ap.error("spec is required unless --key is given")
    spec = json.loads(Path(a.spec).read_text())
    css = CSS_PATH.read_text()
    views = views_for(spec, a.view)
    rendered = [render(spec, v) for v in views]
    frag = "\n".join(fig for _, fig in rendered)
    if a.out:
        Path(a.out).write_text(frag + "\n")
    elif not (a.preview or a.svg):
        print(frag)
    if a.preview:
        Path(a.preview).write_text(
            f'<!doctype html><meta charset="utf-8"><title>{esc(spec.get("title", "Flow"))}</title>{FONTS}'
            f'<style>{css}\nbody{{margin:0;padding:24px;background:#F5F6F8;display:grid;gap:24px}}'
            f'@media (prefers-color-scheme: dark){{body{{background:#121417}}}}</style>\n{frag}\n')
    if a.svg:
        p = Path(a.svg)
        for v, (svg, _) in zip(views, rendered):
            target = p if len(views) == 1 else p.with_name(f"{p.stem}-{v}{p.suffix}")
            target.write_text(svg.replace("</title>", f"</title><style>{css}</style>", 1) + "\n")


if __name__ == "__main__":
    main()
