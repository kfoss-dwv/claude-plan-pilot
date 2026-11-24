#!/usr/bin/env python3
"""Render an ERD spec (JSON) to inline SVG with crow's-foot cardinality ends.

Usage:
  erd.py spec.json -o figure.html            # <figure> fragment: svg + legend
  erd.py spec.json --preview preview.html    # standalone page for eyeballing
  erd.py spec.json --svg erd.svg             # self-contained .svg (CSS embedded)

See ../SKILL.md for the spec format. Stdlib only.
"""
import argparse
import html
import itertools
import json
import math
import sys
from pathlib import Path

HEAD = 30      # header band height
ROW = 22       # column row height
PAD_X = 12     # text inset from the box edge
VGAP = 36      # vertical gap between stacked tables
HGAP = 110     # horizontal gap between grid columns (room for elbows + markers)
MARGIN = 20
STUB = 30      # straight run kept at each end so markers sit on a straight line
LOOP_STEP = 14

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "erd.css"
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')

# Each end token says how many rows of THIS end's table match one row on the
# other end — the standard crow's-foot reading.
END_ALIASES = {"1": "1", "one": "1", "0..1": "0..1", "?": "0..1",
               "n": "N", "m": "N", "many": "N", "1..n": "1..N", "+": "1..N",
               "0..n": "0..N", "*": "0..N"}
END_LABELS = {"1": "exactly one", "0..1": "zero or one", "N": "many",
              "1..N": "one or many", "0..N": "zero or many"}
VARIANT_LABELS = {"": "foreign key", "legacy": "legacy", "new": "new", "changed": "changed"}


def die(msg):
    sys.exit(f"erd.py: {msg}")


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return str(int(n)) if float(n).is_integer() else f"{n:.1f}"


# ---------- layout ----------

def auto_width(t):
    title = len(t["name"]) * 8.1 + (len(t["tag"]) * 6.6 + 16 if t.get("tag") else 0)
    cols = max((len(c["name"]) * 7.3 + (len(c.get("note", "")) * 6.0 + 16 if c.get("note") else 0)
                for c in t["cols"]), default=0)
    return max(220, math.ceil((max(title, cols) + 2 * PAD_X) / 10) * 10)


def layout(spec):
    cfg = spec.get("layout", {})
    hgap, vgap = cfg.get("hgap", HGAP), cfg.get("vgap", VGAP)
    valign = cfg.get("valign", "center")
    tables = spec["tables"]
    for t in tables:
        t.setdefault("id", t["name"])
        t["cols"] = [c if isinstance(c, dict) else {"name": c} for c in t["cols"]]
        t["h"] = HEAD + ROW * len(t["cols"])
        t["_w_auto"] = "w" not in t
        t.setdefault("w", auto_width(t))

    grid = [t for t in tables if "x" not in t]
    ncols = max((t.get("col", 0) for t in grid), default=-1) + 1
    stacks = [[t for t in grid if t.get("col", 0) == i] for i in range(ncols)]
    colw = [max((t["w"] for t in s), default=0) for s in stacks]
    x = MARGIN
    for i, s in enumerate(stacks):
        for t in s:
            t["x"] = x
            if t["_w_auto"]:
                t["w"] = colw[i]
        x += colw[i] + hgap
    # Stacked tables joined to each other need room for a marker at both ends.
    colof = {t["id"]: t.get("col", 0) for t in grid}
    joined = set()
    for rel in spec.get("relations", []):
        a, b = rel["from"].partition(".")[0], rel["to"].partition(".")[0]
        if a != b and a in colof and colof[a] == colof.get(b):
            joined.add(frozenset((a, b)))

    def gaps(s):
        return [max(vgap, 2 * STUB + 12) if frozenset((p["id"], q["id"])) in joined else vgap
                for p, q in zip(s, s[1:])]

    heights = [sum(t["h"] for t in s) + sum(gaps(s)) for s in stacks]
    tallest = max(heights, default=0)
    for s, h in zip(stacks, heights):
        y = MARGIN + ((tallest - h) / 2 if valign == "center" else 0)
        for t, g in zip(s, gaps(s) + [0]):
            if "y" in t:
                y = t["y"]
            t["y"] = round(y)
            y = t["y"] + t["h"] + g
    for t in tables:
        t.setdefault("y", MARGIN)
    return {t["id"]: t for t in tables}


# ---------- relations ----------

def parse_card(card):
    parts = str(card).split(":")
    if len(parts) != 2:
        die(f"card {card!r} must look like 'from:to', e.g. '0..N:1'")
    ends = []
    for p in parts:
        tok = END_ALIASES.get(p.strip().lower())
        if not tok:
            die(f"unknown cardinality end {p!r}; use one of {sorted(END_LABELS)}")
        ends.append(tok)
    return ends


def resolve(ref, T):
    tid, _, col = ref.partition(".")
    if tid not in T:
        die(f"unknown table {tid!r} in {ref!r}")
    t = T[tid]
    if not col:
        return t, t["y"] + t["h"] / 2
    for i, c in enumerate(t["cols"]):
        if col in (c.get("key"), c["name"]):
            return t, t["y"] + HEAD + ROW * i + ROW / 2
    die(f"unknown column {col!r} on table {tid!r}")


def plan(rel, T):
    """Fix endpoints and route kind; the elbow lane is chosen later."""
    ta, ya = resolve(rel["from"], T)
    tb, yb = resolve(rel["to"], T)
    mode = rel.get("route", "auto")
    r = {"rel": rel, "ends": parse_card(rel.get("card", "0..N:1")), "variant": rel.get("variant", "")}
    if ta is tb or mode in ("loop-right", "loop-left"):
        side = -1 if mode == "loop-left" else 1
        xa = ta["x"] + (ta["w"] if side > 0 else 0)
        xb = tb["x"] + (tb["w"] if side > 0 else 0)
        r.update(kind="loop", side=side, a=(xa, ya, side, 0), b=(xb, yb, side, 0))
    elif mode != "vertical" and ta["x"] + ta["w"] <= tb["x"]:
        xa, xb = ta["x"] + ta["w"], tb["x"]
        r.update(kind="side", gap=(xa, xb), a=(xa, ya, 1, 0), b=(xb, yb, -1, 0))
    elif mode != "vertical" and tb["x"] + tb["w"] <= ta["x"]:
        xa, xb = ta["x"], tb["x"] + tb["w"]
        r.update(kind="side", gap=(xb, xa), a=(xa, ya, -1, 0), b=(xb, yb, 1, 0))
    else:
        lo, hi = max(ta["x"], tb["x"]), min(ta["x"] + ta["w"], tb["x"] + tb["w"])
        if lo >= hi:
            die(f"{rel['from']} → {rel['to']}: tables neither side by side nor stacked; set route")
        x = rel.get("x", lo + (hi - lo) * rel.get("at", 0.5))
        if ta["y"] < tb["y"]:
            a, b = (x, ta["y"] + ta["h"], 0, 1), (x, tb["y"], 0, -1)
        else:
            a, b = (x, ta["y"], 0, -1), (x, tb["y"] + tb["h"], 0, 1)
        r.update(kind="vertical", a=a, b=b)
    return r


def points(r, lane):
    (xa, ya, *_), (xb, yb, *_) = r["a"], r["b"]
    if r["kind"] == "vertical" or (r["kind"] == "side" and ya == yb):
        return [(xa, ya), (xb, yb)]
    return [(xa, ya), (lane, ya), (lane, yb), (xb, yb)]


def segments(pts):
    return list(zip(pts, pts[1:]))


def crossings(paths):
    """Count perpendicular crossings and collinear overlaps between different paths."""
    n = 0
    for p, q in itertools.combinations(paths, 2):
        for (a1, a2), (b1, b2) in itertools.product(segments(p), segments(q)):
            ah, bh = a1[1] == a2[1], b1[1] == b2[1]
            if ah != bh:
                (h1, h2), (v1, v2) = ((a1, a2), (b1, b2)) if ah else ((b1, b2), (a1, a2))
                if min(h1[0], h2[0]) < v1[0] < max(h1[0], h2[0]) and \
                   min(v1[1], v2[1]) < h1[1] < max(v1[1], v2[1]):
                    n += 1
            elif ah and a1[1] == b1[1]:
                if min(max(a1[0], a2[0]), max(b1[0], b2[0])) > max(min(a1[0], a2[0]), min(b1[0], b2[0])):
                    n += 1
            elif not ah and a1[0] == b1[0]:
                if min(max(a1[1], a2[1]), max(b1[1], b2[1])) > max(min(a1[1], a2[1]), min(b1[1], b2[1])):
                    n += 1
    return n


def assign_lanes(routes):
    """Pick elbow x per side route so lines in a shared gap cross as little as possible.
    Routes that share an endpoint share a lane, which merges them into one trunk."""
    gaps = {}
    for r in routes:
        if r["kind"] == "side":
            gaps.setdefault(r["gap"], []).append(r)
    for (g0, g1), rs in gaps.items():
        elbow = [r for r in rs if r["a"][1] != r["b"][1] and "via" not in r["rel"]]
        for r in elbow:
            jog = abs(r["a"][1] - r["b"][1])
            if jog <= 10:
                print(f"erd.py: warning: {r['rel']['from']} -> {r['rel']['to']} jogs {jog:g}px; "
                      "nudge a table's y so the rows line up", file=sys.stderr)
        for r in rs:
            if "via" in r["rel"]:
                r["lane"] = r["rel"]["via"]
        groups = []
        for r in elbow:
            ends = {r["a"][:2], r["b"][:2]}
            hit = [g for g in groups if ends & g["ends"]]
            merged = {"ends": set(ends), "routes": [r]}
            for g in hit:
                merged["ends"] |= g["ends"]
                merged["routes"] += g["routes"]
                groups.remove(g)
            groups.append(merged)
        if not groups:
            continue
        lo, hi = g0 + STUB, g1 - STUB
        if hi < lo:
            print(f"erd.py: warning: gap {g0}-{g1} narrower than {2 * STUB}px; markers will crowd",
                  file=sys.stderr)
            lo = hi = (g0 + g1) / 2
        k = len(groups)
        slots = [(lo + hi) / 2] if k == 1 else [lo + (hi - lo) * i / (k - 1) for i in range(k)]
        fixed = [points(r, r.get("lane")) for r in rs if r not in elbow]
        orders = itertools.permutations(range(k)) if k <= 7 else [range(k)]
        best = None
        for order in orders:
            for gi, si in zip(range(k), order):
                for r in groups[gi]["routes"]:
                    r["lane"] = slots[si]
            score = crossings(fixed + [points(r, r["lane"]) for r in elbow])
            if best is None or score < best[0]:
                best = (score, tuple(order))
        for gi, si in zip(range(k), best[1]):
            for r in groups[gi]["routes"]:
                r["lane"] = slots[si]


def assign_loops(routes):
    depth = {}
    for r in routes:
        if r["kind"] != "loop":
            continue
        side = r["side"]
        edge = max(r["a"][0], r["b"][0]) if side > 0 else min(r["a"][0], r["b"][0])
        d = depth.get((edge, side), 0)
        depth[(edge, side)] = d + 1
        r["lane"] = edge + side * (STUB + d * LOOP_STEP)


# ---------- drawing ----------

def marker(end, x, y, dx, dy, cls):
    """Crow's-foot end at (x, y). (dx, dy) points from the table into the line."""
    def P(u, v):
        return fmt(x + dx * u - dy * v), fmt(y + dy * u + dx * v)

    def bar(u):
        (x1, y1), (x2, y2) = P(u, -7), P(u, 7)
        return f'<line class="{cls}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'

    def ring(u):
        cx, cy = P(u, 0)
        return f'<circle class="{cls}" cx="{cx}" cy="{cy}" r="4"/>'

    def crow():
        (tx, ty), (l1, l2), (r1, r2) = P(13, 0), P(0, -7), P(0, 7)
        return f'<path class="{cls}" d="M{l1} {l2} L{tx} {ty} L{r1} {r2}"/>'

    return {"1": [bar(9), bar(15)], "0..1": [bar(9), ring(19)], "N": [crow()],
            "1..N": [crow(), bar(18)], "0..N": [crow(), ring(22)]}[end]


def path_d(pts):
    (x0, y0), rest = pts[0], pts[1:]
    d = f"M{fmt(x0)} {fmt(y0)}"
    for (px, py), (x, y) in zip(pts, rest):
        d += f" H{fmt(x)}" if py == y else f" V{fmt(y)}" if px == x else f" L{fmt(x)} {fmt(y)}"
    return d


def label_svg(r, pts):
    text = r["rel"].get("label")
    if not text:
        return [], []
    est = len(text) * 7.3
    # Prefer the longest horizontal run that fits the text; fall back to the longest run.
    segs = segments(pts)
    flat = [sg for sg in segs if sg[0][1] == sg[1][1] and abs(sg[0][0] - sg[1][0]) >= len(text) * 7.3 + 40]
    (x1, y1), (x2, y2) = max(flat or segs, key=lambda sg: abs(sg[0][0] - sg[1][0]) + abs(sg[0][1] - sg[1][1]))
    cls = "rel-label" + (f" rel-label-{r['variant']}" if r["variant"] in ("new", "changed") else "")
    if y1 == y2:
        mx = (x1 + x2) / 2
        return ([f'<text class="{cls}" x="{fmt(mx)}" y="{fmt(y1 - 8)}" text-anchor="middle">{esc(text)}</text>'],
                [(mx - est / 2, y1 - 20, mx + est / 2, y1)])
    my = (y1 + y2) / 2 + 4
    if r["kind"] == "loop" and r["side"] < 0:  # keep the label outside a left-hand loop
        return ([f'<text class="{cls}" x="{fmt(x1 - 8)}" y="{fmt(my)}" text-anchor="end">{esc(text)}</text>'],
                [(x1 - 8 - est, my - 11, x1, my + 4)])
    return ([f'<text class="{cls}" x="{fmt(x1 + 8)}" y="{fmt(my)}">{esc(text)}</text>'],
            [(x1, my - 11, x1 + 8 + est, my + 4)])


def render_route(r):
    v = r["variant"]
    pts = points(r, r.get("lane"))
    lcls = "link" + (f" link-{v}" if v else "")
    mcls = "mk" + (f" mk-{v}" if v in ("new", "changed") else "")
    out = [f'<path class="{lcls}" d="{path_d(pts)}"/>']
    out += marker(r["ends"][0], *r["a"], mcls)
    out += marker(r["ends"][1], *r["b"], mcls)
    lab, lbox = label_svg(r, pts)
    return out + lab, [(x - 16, y - 16, x + 16, y + 16) for x, y in pts] + lbox


def render_table(t):
    x, y, w, h = t["x"], t["y"], t["w"], t["h"]
    v = t.get("variant")
    o = [f'<g class="tb{" tb-" + v if v else ""}" data-node="{esc(t["id"])}">',
         f'<rect class="tb-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>',
         f'<path class="tb-head" d="M{x} {y + HEAD} V{y + 6} Q{x} {y} {x + 6} {y} H{x + w - 6} '
         f'Q{x + w} {y} {x + w} {y + 6} V{y + HEAD} Z"/>',
         f'<line class="tb-rule" x1="{x}" y1="{y + HEAD}" x2="{x + w}" y2="{y + HEAD}"/>',
         f'<text class="tb-title" x="{x + PAD_X}" y="{y + 20}">{esc(t["name"])}</text>']
    if t.get("tag"):
        o.append(f'<text class="tb-tag" x="{x + w - PAD_X}" y="{y + 20}" text-anchor="end">{esc(t["tag"])}</text>')
    for i, c in enumerate(t["cols"]):
        top = y + HEAD + ROW * i
        state = c.get("state", "")
        if state in ("new", "changed"):
            o.append(f'<rect class="row-{state}" x="{x + 1}" y="{top}" width="{w - 2}" height="{ROW}"/>')
        ccls = "col" + (f" col-{state}" if state else "")
        o.append(f'<g data-node="{esc(t["id"] + "." + c["name"])}">')
        o.append(f'<text class="{ccls}" x="{x + PAD_X}" y="{top + 15}">{esc(c["name"])}</text>')
        if c.get("note"):
            ncls = "note" + (f" note-{state}" if state in ("new", "changed") else "")
            o.append(f'<text class="{ncls}" x="{x + w - PAD_X}" y="{top + 15}" text-anchor="end">{esc(c["note"])}</text>')
        o.append("</g>")
    o.append("</g>")
    return o


def render_note(n, T):
    anchor = n.get("anchor", "start")
    if "below" in n or "above" in n:
        t = T[n.get("below") or n.get("above")]
        x = t["x"] + t["w"] / 2
        y = t["y"] + t["h"] + 18 if "below" in n else t["y"] - 8
        anchor = n.get("anchor", "middle")
    else:
        x, y = n["x"], n["y"]
    cls = "note" + (f" note-{n['variant']}" if n.get("variant") else "")
    est = len(n["text"]) * 6.0
    x0 = x - est / 2 if anchor == "middle" else x - est if anchor == "end" else x
    return (f'<text class="{cls}" x="{fmt(x)}" y="{fmt(y)}" text-anchor="{anchor}">{esc(n["text"])}</text>',
            (x0, y - 11, x0 + est, y + 4))


def render(spec):
    T = layout(spec)
    routes = [plan(rel, T) for rel in spec.get("relations", [])]
    assign_lanes(routes)
    assign_loops(routes)

    links, boxes = [], []
    for r in routes:
        svg, rbox = render_route(r)
        links += svg
        boxes += rbox
    notes = []
    for n in spec.get("notes", []):
        svg, box = render_note(n, T)
        notes.append(svg)
        boxes.append(box)
    boxes += [(t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]) for t in T.values()]
    x0 = math.floor(min(0, min(b[0] for b in boxes) - MARGIN))
    y0 = math.floor(min(0, min(b[1] for b in boxes) - MARGIN))
    width = math.ceil(max(b[2] for b in boxes) + MARGIN) - x0
    height = math.ceil(max(b[3] for b in boxes) + MARGIN) - y0

    pid = spec.get("id", "erd")
    title = spec.get("title", "Entity relationship diagram")
    desc = spec.get("desc", "")
    minw = spec.get("min_width", round(width * 0.8))
    out = [f'<svg class="erd erd-main" viewBox="{x0} {y0} {width} {height}" style="min-width:{minw}px" '
           f'role="img" aria-labelledby="{pid}-title {pid}-desc" xmlns="http://www.w3.org/2000/svg">',
           f'<title id="{pid}-title">{esc(title)}</title>', f'<desc id="{pid}-desc">{esc(desc)}</desc>']
    out += links + notes
    for t in T.values():
        out += render_table(t)
    out.append("</svg>")
    return "\n".join(out), routes


def end_items(ends):
    items = []
    for e in [e for e in END_LABELS if e in ends]:
        mk = "".join(marker(e, 34, 8, -1, 0, "mk"))
        items.append(f'<li><svg class="erd erd-key" viewBox="0 0 36 16" aria-hidden="true">'
                     f'<path class="link" d="M0 8 H34"/>{mk}'
                     f'<line class="key-edge" x1="35" y1="1" x2="35" y2="15"/></svg>{esc(END_LABELS[e])}</li>')
    return items


def legend(spec, routes):
    """Line styles and cardinality ends actually used, in reading order."""
    labels = {**VARIANT_LABELS, **spec.get("legend", {})}
    items = []
    for v in dict.fromkeys(r["variant"] for r in routes):
        cls = "link" + (f" link-{v}" if v else "")
        items.append(f'<li><svg class="erd erd-key" viewBox="0 0 36 16" aria-hidden="true">'
                     f'<path class="{cls}" d="M2 8 H34"/></svg>{esc(labels.get(v, v))}</li>')
    items += end_items({e for r in routes for e in r["ends"]})
    return '<ul class="erd-legend">\n' + "\n".join(items) + "\n</ul>"


def full_key():
    """Every cardinality end, for a page-level key independent of any one diagram."""
    return '<ul class="erd-legend erd">\n' + "\n".join(end_items(END_LABELS)) + "\n</ul>"


def figure(spec):
    svg, routes = render(spec)
    return svg, (f'<figure class="erd-figure">\n<div class="erd-scroll">\n{svg}\n</div>\n'
            f'{legend(spec, routes)}\n</figure>')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--key", action="store_true", help="print a legend of all five cardinality ends and exit")
    ap.add_argument("-o", "--out", help="write the <figure> fragment here (default: stdout)")
    ap.add_argument("--preview", help="also write a standalone preview page")
    ap.add_argument("--svg", help="also write a self-contained .svg with the CSS embedded")
    a = ap.parse_args()
    if a.key:
        print(full_key())
        return
    if not a.spec:
        ap.error("spec is required unless --key is given")
    spec = json.loads(Path(a.spec).read_text())
    css = CSS_PATH.read_text()
    svg, fig = figure(spec)
    if a.out:
        Path(a.out).write_text(fig + "\n")
    elif not (a.preview or a.svg):
        print(fig)
    if a.preview:
        Path(a.preview).write_text(
            f'<!doctype html><meta charset="utf-8"><title>{esc(spec.get("title", "ERD"))}</title>{FONTS}'
            f'<style>{css}\nbody{{margin:0;padding:24px;background:#F6F5F3}}'
            f'@media (prefers-color-scheme: dark){{body{{background:#151413}}}}</style>\n{fig}\n')
    if a.svg:
        Path(a.svg).write_text(svg.replace("</title>", f"</title><style>{css}</style>", 1) + "\n")


if __name__ == "__main__":
    main()
