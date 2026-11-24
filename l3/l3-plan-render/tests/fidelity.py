#!/usr/bin/env python3
"""Check that a rendered page says exactly what its .md says.

Usage: fidelity.py X.md [X.html] [--json]

Independent of render.py's walk: it re-parses the .md with markdown-it and the .html
with html.parser, then reports
  missing    md blocks with no HTML element carrying the same data-md range
  text       blocks whose words don't all appear, in order, in that element
  counts     tabs / folds / questions / challenges / figures / chart nodes that differ
  leftovers  markdown syntax that leaked into visible text (``` {# [!bug] …)
deviations = the sum. Exit 1 when deviations > 0.
"""
import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "_vendor"))
import render  # noqa: E402  (html_path / split_front / strip_heading_attrs only)
from markdown_it import MarkdownIt  # noqa: E402

md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
SKIP_TEXT = {"script", "style", "title", "svg"}
FENCE_KINDS = {"flow", "erd", "question", "challenge", "files", "ledger", "html-block"}


class Tree(HTMLParser):
    """Collects, per data-md value, the visible text under that element; plus counts."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.by_md, self.text_parts = [], {}, []
        self.counts = {"tabs": 0, "folds": 0, "questions": 0, "challenges": 0, "figures": 0, "nodes": set()}
        self.skip = self.code = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "button" and a.get("role") == "tab":
            self.counts["tabs"] += 1
        if tag == "details" and "fold" in cls:
            self.counts["folds"] += 1
        if tag == "article" and "q" in cls:
            self.counts["questions"] += 1
        if tag == "article" and "challenge" in cls:
            self.counts["challenges"] += 1
        if tag == "div" and "fig" in cls:
            self.counts["figures"] += 1
        if a.get("data-node"):
            self.counts["nodes"].add(a["data-node"])
        if tag in SKIP_TEXT:
            self.skip += 1
        if tag == "code":
            self.code += 1
        if tag in VOID:
            return
        rec = {"tag": tag, "md": a.get("data-md"), "buf": []}
        self.stack.append(rec)

    def handle_startendtag(self, tag, attrs):
        a = dict(attrs)
        if a.get("data-node"):
            self.counts["nodes"].add(a["data-node"])

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag in SKIP_TEXT:
            self.skip = max(0, self.skip - 1)
        if tag == "code":
            self.code = max(0, self.code - 1)
        while self.stack:
            rec = self.stack.pop()
            text = "".join(rec["buf"])
            if self.stack:
                self.stack[-1]["buf"].append(f" {text} ")   # element boundaries separate words
            if rec["md"]:
                self.by_md.setdefault(rec["md"], []).append(text)
            if rec["tag"] == tag:
                break

    def handle_data(self, d):
        if self.stack and not self.skip:
            self.stack[-1]["buf"].append(d)
            if not self.code:                         # prose only: code may quote syntax on purpose
                self.text_parts.append(d)


def words(s):
    return re.findall(r"[\w$%.:/#@<>=!?+*-]+", s.replace("’", "'"))


def in_order(needle, hay):
    """Every word of needle appears in hay, in order."""
    hw = words(hay)
    i = 0
    for w in words(needle):
        while i < len(hw) and hw[i] != w:
            i += 1
        if i == len(hw):
            return False, w
        i += 1
    return True, None


def inline_text(tok):
    out = []
    for c in tok.children or []:
        if c.type == "text":
            out.append(c.content)
        elif c.type == "code_inline":
            out.append(f" {c.content} ")
        elif c.type in ("softbreak", "hardbreak"):
            out.append(" ")
    return "".join(out)


def block_text(block):
    return " ".join(inline_text(t) for t in block if t.type == "inline")


def blocks_of(tokens):
    out, i = [], 0
    while i < len(tokens):
        t = tokens[i]
        if t.nesting == 1:
            close, j = t.type[:-5] + "_close", i + 1
            while not (tokens[j].type == close and tokens[j].level == t.level):
                j += 1
            out.append(tokens[i:j + 1])
            i = j + 1
        else:
            out.append([t])
            i += 1
    return out


def expected_fence_text(tok):
    kind = (tok.info.split() or [""])[0]
    body = tok.content
    if kind in ("flow", "erd"):
        return ""                                         # checked via node ids
    if kind in ("question", "challenge"):
        out, rest = [], []
        for ln in body.splitlines():
            m = re.match(r"^(title|context):\s*(.*)$", ln)
            if m and not rest:
                out.append(strip_md_inline(m.group(2)))
            elif kind == "question" and ln.startswith("- ") and not rest:
                m = re.match(r"^- (\S+?)\*?\s+(.*)$", ln)
                out.append(strip_md_inline(m.group(2).replace(" — ", " ").replace(" -- ", " ") if m else ln[2:]))
            elif not (re.match(r"^placeholder:", ln) and not rest):
                rest.append(ln)
        return " ".join(out) + " " + html.unescape(re.sub(r"<[^>]+>", " ", md.render("\n".join(rest))))
    if kind == "files":
        return "\n".join(re.sub(r"^\s*- ", "", ln) for ln in body.splitlines())
    if kind == "ledger":
        return " ".join(tok.info.split()[1:]) + "\n" + "\n".join((ln[1:] if ln[:1] in "!=" else ln).replace("|", " ") for ln in body.splitlines())
    if kind == "html-block":
        visible = re.sub(r"<(script|style|svg|textarea|title)\b.*?(</\1\s*>|$)|<!--.*?(-->|$)", " ", body, flags=re.S | re.I)
        return html.unescape(re.sub(r"<[^>]*>?", " ", visible))
    return body


def strip_md_inline(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", md.renderInline(s)))


def check(md_path, html_path):
    text = Path(md_path).read_text()
    meta, where, lines = render.split_front(text)
    attrs = render.strip_heading_attrs(lines)
    tokens = md.parse("\n".join(lines))
    tree = Tree()
    tree.feed(Path(html_path).read_text())
    tree.close()
    by_md = {k: " ".join(v) for k, v in tree.by_md.items()}
    res = {"blocks": 0, "missing": [], "text": [], "counts": [], "leftovers": []}

    def look(rng, expect, what):
        res["blocks"] += 1
        if rng not in by_md:
            res["missing"].append(f"{what} at lines {rng}")
            return
        ok, w = in_order(expect, by_md[rng])
        if not ok:
            res["text"].append(f"{what} at lines {rng}: word {w!r} not rendered")

    # header (front matter)
    for k in ("eyebrow", "summary"):
        if meta.get(k):
            look(f"{where[k]}-{where[k]}", strip_md_inline(meta[k]), f"front matter {k}")
    h1k = "h1" if meta.get("h1") else "title"
    if meta.get(h1k):
        look(f"{where[h1k]}-{where[h1k]}", strip_md_inline(meta[h1k]), f"front matter {h1k}")
    if meta.get("chips"):
        look(f"{where['chips']}-{where['chips']}", strip_md_inline(meta["chips"].replace("|", " ")), "chips")

    n = {"h1": 0, "h2": 0, "questions": 0, "challenges": 0, "figures": 0}
    nodes = set()
    blocks = blocks_of(tokens)
    for b in blocks:
        t = b[0]
        rng = f"{t.map[0] + 1}-{t.map[1]}" if t.map else None
        if t.type == "heading_open":
            n["h1" if t.tag == "h1" else "h2" if t.tag == "h2" else "h"] = n.get("h1" if t.tag == "h1" else "h2" if t.tag == "h2" else "h", 0) + 1
            txt = block_text(b)
            if t.tag == "h2":
                txt = re.sub(r"^\d{2}\s+", "", txt)
            look(rng, txt, t.tag)
        elif t.type == "fence":
            kind = (t.info.split() or [""])[0]
            if kind == "question":
                n["questions"] += 1
            elif kind == "challenge":
                n["challenges"] += 1
            elif kind in ("flow", "erd"):
                n["figures"] += 1
                try:
                    spec = json.loads(t.content)
                    if kind == "flow":
                        nodes |= {x["id"] for x in spec.get("nodes", [])}
                    else:
                        for tb in spec.get("tables", []):
                            tid = tb.get("id", tb.get("name"))
                            nodes.add(tid)
                            nodes |= {f"{tid}.{c if isinstance(c, str) else c['name']}" for c in tb.get("cols", [])}
                except (ValueError, KeyError, TypeError, AttributeError):
                    res["counts"].append(f"{kind} fence at {rng} is not a valid spec")
            look(rng, expected_fence_text(t), f"{kind or 'code'} fence")
        elif t.type in ("paragraph_open", "bullet_list_open", "ordered_list_open", "blockquote_open", "table_open"):
            txt = block_text(b)
            if t.type == "blockquote_open":
                txt = re.sub(r"\[!(bug|ok|note|warn)\]", "", txt, flags=re.I)
            if t.type == "bullet_list_open":
                txt = re.sub(r"\[[ xX]\]\s", "", txt)
            look(rng, txt, t.type.replace("_open", ""))
        elif t.type == "code_block":
            look(rng, t.content, "indented code")
        elif t.type == "hr":
            res["blocks"] += 1
            if rng not in by_md:
                res["missing"].append(f"hr at lines {rng}")

    got = tree.counts
    tabs_expected = n["h1"]
    for name, want, have in (("tabs", tabs_expected, got["tabs"]), ("folds", n["h2"], got["folds"]),
                             ("questions", n["questions"], got["questions"]),
                             ("challenges", n["challenges"], got["challenges"]), ("figures", n["figures"], got["figures"])):
        if want != have:
            res["counts"].append(f"{name}: md has {want}, html has {have}")
    lost = nodes - got["nodes"]
    if lost:
        res["counts"].append(f"chart nodes missing from the SVG: {sorted(lost)[:8]}")

    visible = re.sub(r"\s+", " ", "".join(tree.text_parts))
    prose = []
    for i, t in enumerate(tokens):
        if t.type != "inline":
            continue
        txt = "".join(c.content if c.type == "text" else " " for c in t.children or [])
        if i >= 2 and tokens[i - 2].type == "blockquote_open" and tokens[i - 2].level == 0:
            txt = re.sub(r"^\[!(bug|ok|note|warn)\]", "", txt, flags=re.I)      # consumed by the callout
        prose.append(txt)
    for k in ("eyebrow", "summary", "h1", "title", "chips"):
        prose.append(meta.get(k, ""))
    prose = " ".join(prose)
    for pat, what in ((r"```", "a fence marker"), (r"\{#[\w-]+", "a heading {#id}"), (r"\[!(bug|ok|note|warn)\]", "a callout marker"),
                      (r"^---$", "front matter")):
        hits = len(re.findall(pat, visible, flags=re.M | re.I)) - len(re.findall(pat, prose, flags=re.M | re.I))
        if hits > 0:
            res["leftovers"].append(f"{hits}× {what} in visible text")
    res["deviations"] = len(res["missing"]) + len(res["text"]) + len(res["counts"]) + len(res["leftovers"])
    res["md_bytes"] = len(text.encode())
    res["html_bytes"] = Path(html_path).stat().st_size
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("md")
    ap.add_argument("html", nargs="?")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = check(a.md, a.html or render.html_path(a.md))
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for k in ("missing", "text", "counts", "leftovers"):
            for x in res[k]:
                print(f"{k:9} {x}")
        print(f"{res['blocks']} blocks · {res['deviations']} deviation(s) · md {res['md_bytes']} B → html {res['html_bytes']} B")
    sys.exit(1 if res["deviations"] else 0)


if __name__ == "__main__":
    main()
