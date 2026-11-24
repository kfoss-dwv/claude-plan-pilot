#!/usr/bin/env python3
"""l3-plan-render: contract-format markdown -> one self-contained HTML page.

Usage:
  render.py X.md                   build: check, then write X.html beside it (plan.md -> index.html)
  render.py check X.md             lint only; exit 1 on any ERROR
  render.py components [--write]   the component table from the registry (--write: docs/COMPONENTS_AVAILABLE.md)

Every rendered block carries data-md="a-b" (1-based plan.md lines) so comments can point
back at the source. Answers, challenge replies and comments live in X.state.json
(plan.md -> plan.state.json), written by serve.py. Syntax: ../CONTRACT.md.
Stdlib + vendored markdown-it-py.
"""
import argparse
import contextlib
import difflib
import hashlib
import html
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(HERE / "_vendor"))
from markdown_it import MarkdownIt  # noqa: E402

ASSETS = SKILL / "assets"
FLOW_PY = ROOT / "l1/l1-flow-svg/scripts/flow.py"
ERD_PY = ROOT / "l1/l1-erd-svg/scripts/erd.py"
COMPONENTS_DOC = ROOT / "docs/COMPONENTS_AVAILABLE.md"

FRONT_KEYS = {"title", "contract", "type", "eyebrow", "h1", "summary", "chips", "tabs", "doc", "skill", "status"}
TAB_IDS = {"plan": "plan", "open questions": "questions", "questions": "questions", "testing": "testing",
           "challenging the design": "challenges", "challenges": "challenges", "agent progress": "agents"}
CALLOUTS = {"bug": "Bug", "ok": "OK", "note": "Note", "warn": "Watch out"}
PLACEHOLDER = "TODO(plan)"
FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600'
         '&family=IBM+Plex+Sans+Condensed:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">')

md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def esc(s):
    return html.escape(str(s), quote=True)


def inline(text):
    return md.renderInline(text or "").strip()


def contract_version():
    m = re.search(r"^contract:\s*(\d+)", (SKILL / "CONTRACT.md").read_text(), flags=re.M)
    return int(m.group(1)) if m else None


def html_path(md_path):
    """plan.md -> index.html (a plan folder), anything else X.md -> X.html."""
    p = Path(md_path)
    return p.with_name("index.html") if p.name == "plan.md" else p.with_suffix(".html")


def state_path(md_path):
    return Path(md_path).with_suffix(".state.json")


def atomic_write(path, text):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mods = {}


def l1(kind):
    if kind not in _mods:
        _mods[kind] = load_module(f"pp_{kind}", FLOW_PY if kind == "flow" else ERD_PY)
    return _mods[kind]


# ---------- source ----------

def split_front(text):
    """(meta, meta_lines, body). The front matter is blanked, not cut, so token lines stay file lines."""
    lines = text.split("\n")
    meta, where = {}, {}
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                for n in range(1, i):
                    m = re.match(r"^([A-Za-z_][\w-]*):\s?(.*)$", lines[n])
                    if m:
                        meta[m.group(1)] = re.sub(r"\s+#\s.*$", "", m.group(2)).strip()
                        where[m.group(1)] = n + 1
                lines[:i + 1] = [""] * (i + 1)
                break
    return meta, where, lines


HEAD_ATTRS = re.compile(r"^(#{1,6}\s.*?)\s*\{((?:[#.][\w-]+\s*)+)\}\s*$")


def strip_heading_attrs(lines):
    """`## 03 Title {#p-03 .open}` -> attrs keyed by 1-based line; the line loses the braces."""
    attrs = {}
    in_fence = None
    for i, ln in enumerate(lines):
        f = re.match(r"^\s*(`{3,}|~{3,})", ln)
        if f:
            in_fence = None if in_fence and f.group(1)[0] == in_fence[0] and len(f.group(1)) >= len(in_fence) else (in_fence or f.group(1))
            continue
        if in_fence:
            continue
        m = HEAD_ATTRS.match(ln)
        if m:
            parts = m.group(2).split()
            attrs[i + 1] = {"id": next((p[1:] for p in parts if p.startswith("#")), None),
                            "classes": [p[1:] for p in parts if p.startswith(".")]}
            lines[i] = m.group(1)
    return attrs


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


def rng(tok):
    return f"{tok.map[0] + 1}-{tok.map[1]}"


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


def heading_text(block):
    return "".join(c.content for c in (block[1].children or []) if c.type in ("text", "code_inline")).strip()


# ---------- page context ----------

class Page:
    def __init__(self, path, text):
        self.path = Path(path)
        self.meta, self.meta_lines, lines = split_front(text)
        self.attrs = strip_heading_attrs(lines)
        self.lines = lines
        self.tokens = md.parse("\n".join(lines))
        for t in self.tokens:
            if t.map and t.nesting == 1:
                t.attrSet("data-md", rng(t))
        self.errors, self.warns = [], []
        self.ids, self.qids, self.cids, self.spec_ids = set(), [], [], []
        self.css = set()
        self.has = {"questions": None, "challenges": None}

    def err(self, line, msg):
        self.errors.append(f"{self.path.name}:{line}: {msg}" if line else msg)

    def warn(self, line, msg):
        self.warns.append(f"{self.path.name}:{line}: {msg}" if line else msg)

    def uid(self, want, line):
        base = want
        n = 2
        while want in self.ids:
            want = f"{base}-{n}"
            n += 1
        if want != base:
            self.err(line, f"duplicate id #{base}")
        self.ids.add(want)
        return want


# ---------- fence renderers ----------

def fence_lines(tok):
    body = tok.content[:-1] if tok.content.endswith("\n") else tok.content
    return body.split("\n") if body else []


def code_lines(tok, marks=None):
    first = tok.map[0] + 2
    out = []
    for i, ln in enumerate(fence_lines(tok)):
        cls = "ln" + (f" {marks[i]}" if marks and i in marks else "")
        out.append(f'<span class="{cls}" data-md="{first + i}-{first + i}">{esc(ln)}</span>')
    return "".join(out)


def parse_code_info(info):
    parts = info.split()
    lang = parts[0] if parts else ""
    flags = [p for p in parts[1:] if p in ("before", "after", "bug")]
    loc = " ".join(p for p in parts[1:] if p not in ("before", "after", "bug"))
    return lang, loc, flags


def code(page, tok, marks=None, role=None):
    lang, loc, flags = parse_code_info(tok.info)
    pseudo = lang.startswith("pseudo-")
    tags = []
    if pseudo:
        tags.append(f'<span class="tag tag-pseudo">pseudo · {esc(lang[7:])}</span>')
    if role:
        tags.append(f'<span class="tag tag-{role}">{"today" if role == "before" else "proposed"}</span>')
    head = ""
    if loc or tags:
        head = f'<div class="loc">{esc(loc)}{"".join(tags)}</div>'
    cls = "code-block" + (" pseudo" if pseudo else "") + (" bug" if "bug" in flags else "")
    lang_cls = f' class="language-{esc(lang[7:] if pseudo else lang)}"' if lang else ""
    return (f'<div class="{cls}" data-md="{rng(tok)}">{head}'
            f'<pre><code{lang_cls}>{code_lines(tok, marks)}</code></pre></div>')


def code_pair(page, before, after):
    a, b = fence_lines(before), fence_lines(after)
    bug = "bug" in parse_code_info(before.info)[2]
    mb, ma = {}, {}
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("replace", "delete"):
            for i in range(i1, i2):
                mb[i] = "ln-bug" if bug else "ln-focus"
        if op in ("replace", "insert"):
            for j in range(j1, j2):
                ma[j] = "ln-add"
    return (f'<div class="pair" data-md="{before.map[0] + 1}-{after.map[1]}">'
            f'{code(page, before, mb, "before")}{code(page, after, ma, "after")}</div>')


def chart(page, tok, args):
    kind = tok.info.split()[0]
    line = tok.map[0] + 1
    try:
        spec = json.loads(tok.content)
    except ValueError as e:
        page.err(line, f"{kind} fence is not valid JSON: {e}")
        return f'<div class="callout bug" data-md="{rng(tok)}"><h3>Bad {kind} spec</h3><p>{esc(e)}</p></div>'
    caption = spec.pop("caption", "") if isinstance(spec, dict) else ""
    sid = spec.get("id") if isinstance(spec, dict) else None
    if not sid:
        page.err(line, f"{kind} spec needs an \"id\" (prefixes its svg ids; unique per page)")
    elif sid in page.spec_ids:
        page.err(line, f"duplicate {kind} spec id {sid!r}")
    page.spec_ids.append(sid)
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            mod = l1(kind)
            if kind == "flow":
                figs = [mod.render(spec, v)[1] for v in mod.views_for(spec, "both")]
            else:
                figs = [mod.figure(spec)[1]]
    except SystemExit as e:
        page.err(line, f"{kind}: {e}")
        return f'<div class="callout bug" data-md="{rng(tok)}"><h3>{kind} failed</h3><p>{esc(e)}</p></div>'
    except Exception as e:  # a malformed spec the drawer didn't guard against
        page.err(line, f"{kind}: {type(e).__name__}: {e}")
        return f'<div class="callout bug" data-md="{rng(tok)}"><h3>{kind} failed</h3><p>{esc(e)}</p></div>'
    for w in err.getvalue().splitlines():
        page.warn(line, w.strip())
    page.css.add(kind)
    src = fence_lines(tok)
    first = tok.map[0] + 2

    def find(pattern):
        for i, ln in enumerate(src):
            if re.search(pattern, ln):
                return first + i
        return None

    def node_line(nid):
        if "." in nid and kind == "erd":
            t, c = nid.split(".", 1)
            start = node_line(t)
            if start:
                for i in range(start - first, len(src)):
                    if re.search(rf'"{re.escape(c)}"', src[i]):
                        return first + i
        q = re.escape(json.dumps(nid)[1:-1])
        return find(rf'"id"\s*:\s*"{q}"') or find(rf'"name"\s*:\s*"{q}"') or line

    def tag_node(m):
        nid = html.unescape(m.group(1))
        n = node_line(nid)
        return f'{m.group(0)} data-md="{n}-{n}"'

    def tag_edge(m):
        a, b = html.unescape(m.group(1)).split(">", 1)
        n = find(rf'"from"\s*:\s*"{re.escape(a)}".*"to"\s*:\s*"{re.escape(b)}"') or line
        return f'{m.group(0)} data-md="{n}-{n}"'

    body = "\n".join(figs)
    body = re.sub(r'data-node="([^"]*)"', tag_node, body)
    body = re.sub(r'data-edge="([^"]*)"', tag_edge, body)
    cap = f'<p class="cap" data-md="{find(chr(34) + "caption" + chr(34)) or line}-{find(chr(34) + "caption" + chr(34)) or line}">{inline(caption)}</p>' if caption else ""
    return f'<div class="fig fig-{kind}" data-md="{rng(tok)}">\n{body}\n{cap}</div>'


def parse_keyed(tok):
    """`key: value` lines, then `- ` option lines, then free text. Returns (keys, options, rest, lines)."""
    keys, opts, rest = {}, [], []
    first = tok.map[0] + 2
    last = None
    for i, ln in enumerate(fence_lines(tok)):
        m = re.match(r"^(title|context|placeholder):\s*(.*)$", ln)
        if m and not rest and not opts:
            keys[m.group(1)] = [m.group(2), first + i]
            last = m.group(1)
        elif ln.startswith("- ") and not rest:
            opts.append((ln[2:], first + i))
            last = None
        elif ln.strip() and last and not opts and not rest and ln.startswith("  "):
            keys[last][0] += " " + ln.strip()      # indented continuation of a key
        elif ln.strip() or rest:
            rest.append((ln, first + i))
            last = None
    return keys, opts, rest


OPT = re.compile(r"^(\S+?)(\*?)\s+(.*?)(?:\s+(?:—|--)\s+(.*))?$")


def question_card(page, tok, args):
    line = tok.map[0] + 1
    qid = args[0] if args else ""
    if not re.fullmatch(r"q\d+", qid):
        page.err(line, f"question id {qid!r} should be q1, q2 …")
    if qid in page.qids:
        page.err(line, f"duplicate question id {qid}")
    page.qids.append(qid)
    page.ids.add(qid)
    keys, opts, rest = parse_keyed(tok)
    title = keys.get("title", ["", line])
    if not title[0]:
        page.err(line, f"question {qid}: needs a title: line")
    o = [f'<article class="q" data-q="{esc(qid)}" id="{esc(qid)}" data-md="{rng(tok)}">',
         f'<div class="q-top"><span class="qid">{esc(qid.upper())}</span>'
         f'<h3 class="q-title" data-md="{title[1]}-{title[1]}">{inline(title[0])}</h3><span class="state">Open</span></div>']
    if "context" in keys:
        c = keys["context"]
        o.append(f'<div class="ctx" data-md="{c[1]}-{c[1]}"><p>{inline(c[0])}</p></div>')
    if rest:
        o.append(f'<div class="ctx" data-md="{rest[0][1]}-{rest[-1][1]}">{md.render(chr(10).join(r[0] for r in rest))}</div>')
    if opts:
        o.append(f'<div class="opts" role="radiogroup" aria-label="{esc(qid.upper())} options">')
        recs = 0
        for text, ln in opts:
            m = OPT.match(text)
            if not m:
                page.err(ln, f"question {qid}: option should be `- value* Label — consequence`")
                continue
            val, rec, label, desc = m.groups()
            recs += bool(rec)
            rid = f"{qid}-{val}"
            o.append(f'<label class="opt" for="{esc(rid)}" data-md="{ln}-{ln}"><input type="radio" name="{esc(qid)}" id="{esc(rid)}" value="{esc(val)}">'
                     f'<span><span class="opt-label">{inline(label)}</span>{"<span class=rec>recommended</span>" if rec else ""}'
                     f'{f"<span class=opt-desc>{inline(desc)}</span>" if desc else ""}</span></label>')
        o.append("</div>")
        if not recs:
            page.warn(line, f"question {qid}: no option marked recommended (*)")
    ph = keys.get("placeholder", ["Answer or note"])[0]
    o.append(f'<textarea id="{esc(qid)}-note" placeholder="{esc(ph)}" aria-label="Answer to {esc(qid.upper())}"></textarea>')
    o.append('<div class="row"><div class="by"></div><span class="saved"></span></div></article>')
    return "\n".join(o)


def challenge_card(page, tok, args):
    line = tok.map[0] + 1
    cid = args[0] if args else ""
    if not re.fullmatch(r"c\d+", cid):
        page.err(line, f"challenge id {cid!r} should be c1, c2 …")
    if cid in page.cids:
        page.err(line, f"duplicate challenge id {cid}")
    page.cids.append(cid)
    page.ids.add(cid)
    keys, opts, rest = parse_keyed(tok)
    title = keys.get("title", ["", line])
    if not title[0]:
        page.err(line, f"challenge {cid}: needs a title: line")
    body = opts and [(f"- {t}", ln) for t, ln in opts] or []
    body = body + rest
    arg = (f'<div class="arg" data-md="{body[0][1]}-{body[-1][1]}">{md.render(chr(10).join(b[0] for b in body))}</div>'
           if body else "")
    status = "".join(f'<option value="{v}">{l}</option>' for v, l in
                     (("open", "Open"), ("discussing", "Discussing"), ("accepted", "Accepted"),
                      ("changed", "Plan changed"), ("rejected", "Rejected")))
    return (f'<article class="challenge" data-c="{esc(cid)}" id="{esc(cid)}" data-status="open" data-md="{rng(tok)}">'
            f'<div class="q-top"><span class="cid">{esc(cid.upper())}</span><h3 class="q-title" data-md="{title[1]}-{title[1]}">'
            f'{inline(title[0])}</h3><span class="pill" data-s="open">Open</span></div>{arg}'
            f'<div class="resp"><div class="resp-head"><h3>Response</h3><label class="muted" for="{esc(cid)}-status">Status '
            f'<select id="{esc(cid)}-status">{status}</select></label></div>'
            f'<textarea id="{esc(cid)}-note" placeholder="Your reply" aria-label="Reply to {esc(cid.upper())}"></textarea>'
            f'<div class="row"><div class="by"></div><span class="saved"></span></div></div></article>')


def files_list(page, tok, args):
    first = tok.map[0] + 2
    files, cur = [], None
    for i, ln in enumerate(fence_lines(tok)):
        if not ln.strip():
            continue
        if ln.lstrip().startswith("- "):
            if cur is None:
                page.err(first + i, "files: a change line before any path line")
                continue
            cur["changes"].append((ln.lstrip()[2:], first + i))
        else:
            cur = {"path": ln.strip(), "line": first + i, "changes": []}
            files.append(cur)
    o = [f'<div class="files" data-md="{rng(tok)}">']
    for f in files:
        end = f["changes"][-1][1] if f["changes"] else f["line"]
        o.append(f'<div class="file" data-md="{f["line"]}-{end}"><div class="path">{esc(f["path"])}</div><ul>'
                 + "".join(f'<li data-md="{ln}-{ln}">{inline(t)}</li>' for t, ln in f["changes"]) + "</ul></div>")
    o.append("</div>")
    return "".join(o)


def ledger(page, tok, args):
    first = tok.map[0] + 2
    rows = []
    for i, ln in enumerate(fence_lines(tok)):
        if not ln.strip():
            continue
        cls = ""
        if ln[:1] in "!=":
            cls = "total bug" if ln[0] == "!" else "total ok"
            ln = ln[1:]
        cells = [c.strip() for c in ln.split("|")]
        if len(cells) != 3:
            page.err(first + i, "ledger row should be `name | formula | value`")
            cells = (cells + ["", "", ""])[:3]
        name, f, val = cells
        rows.append(f'<tr{f" class={chr(34)}{cls}{chr(34)}" if cls else ""} data-md="{first + i}-{first + i}">'
                    f'<td>{inline(name)}{f"<span class=f>{inline(f)}</span>" if f else ""}</td><td>{inline(val)}</td></tr>')
    title = " ".join(args)
    return (f'<div class="ledger" data-md="{rng(tok)}">{f"<h3>{inline(title)}</h3>" if title else ""}'
            f'<table>{"".join(rows)}</table></div>')


class Sanitizer(HTMLParser):
    URL_ATTRS = {"href", "src", "action", "formaction", "xlink:href", "srcset", "poster", "data"}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.out, self.skip, self.dropped = [], 0, 0

    def tag(self, tag, attrs, close=""):
        keep = []
        for k, v in attrs:
            if k.startswith("on") or (k in self.URL_ATTRS and re.sub(r"[\s\x00-\x1f]", "", v or "").lower().startswith(("javascript:", "vbscript:"))):
                self.dropped += 1
                continue
            keep.append(f" {k}" if v is None else f' {k}="{esc(v)}"')
        return f"<{tag}{''.join(keep)}{close}>"

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.skip += 1
            self.dropped += 1
        elif not self.skip:
            self.out.append(self.tag(tag, attrs))

    def handle_startendtag(self, tag, attrs):
        if tag != "script" and not self.skip:
            self.out.append(self.tag(tag, attrs, "/"))

    def handle_endtag(self, tag):
        if tag == "script":
            self.skip = max(0, self.skip - 1)
        elif not self.skip:
            self.out.append(f"</{tag}>")

    def handle_data(self, d):
        if not self.skip:
            self.out.append(d)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")


def sanitize(raw):
    s = Sanitizer()
    s.feed(raw)
    s.close()
    return "".join(s.out), s.dropped


def html_block(page, tok, args):
    clean, dropped = sanitize(tok.content)
    if dropped:
        page.warn(tok.map[0] + 1, f"html-block: dropped {dropped} script tag(s) / on* attribute(s) / javascript: URL(s)")
    return f'<div class="html-block" data-md="{rng(tok)}">{clean}</div>'


# ---------- the registry ----------
# One entry per markdown construct. `fence` entries are dispatched by the fence's first info word;
# the rest are structural and handled in build(). `render.py components` prints this table.

COMPONENTS = [
    {"name": "Header", "write": "front matter: `title`, `contract`, `type`, `eyebrow`, `h1`, `summary`, `chips` (`|`-separated, first highlighted), `tabs`",
     "renders": "page head + chips", "notes": "`title` and `contract` are required. Docs may add `doc`, `skill`, `status`."},
    {"name": "Tabs", "write": "`# Plan`, `# Open questions`, `# Testing`, `# Challenging the design` … (H1); order from front matter `tabs:`",
     "renders": "tab bar + one panel per H1", "notes": "`#<panel>` deep-links a tab. Tabs holding questions or challenges show an open-count badge. No H1 = one untabbed panel."},
    {"name": "Collapsible headers", "write": "`## 03 Title {#p-03}`; the first paragraph under it is the gist; `{.open}` starts it expanded",
     "renders": "`<details>` fold whose gist hides when open", "notes": "Every H2 folds. A leading two-digit number renders as the fold number. Each panel with folds gets an Expand all button; `#p-03` opens that fold."},
    {"name": "Charts", "fence": "flow", "write": "```` ```flow ```` or ```` ```erd ```` fence holding the l1 JSON spec, optional `\"caption\"` key",
     "renders": "inline SVG figure(s) from l1-flow-svg / l1-erd-svg, CSS inlined once per page", "notes": "A before/after flow spec renders as two figures. Every node carries `data-node` + `data-md` (the line of its `\"id\"`), so it can be commented on."},
    {"name": "Charts (erd)", "fence": "erd", "write": "```` ```erd ```` fence", "renders": "ERD figure", "notes": "Tables tag `data-node=\"table\"`, columns `data-node=\"table.col\"`.", "hidden": True},
    {"name": "Q/A boxes", "fence": "question", "write": "```` ```question q4 ```` with `title:`, `context:`, then `- value* Label — consequence` lines (`*` = recommended; no options = free text)",
     "renders": "answer card: radio options + textarea", "notes": "Saves to `answers.q4` in the state file; shows the agent's `review` and `applied` notes. \"Copy answers as text\" covers all cards."},
    {"name": "Challenge cards", "fence": "challenge", "write": "```` ```challenge c1 ```` with `title:` (the claim), then the argument as markdown",
     "renders": "claim + argument + status select + reply", "notes": "Same storage and review flow as Q/A boxes (`challenges.c1`)."},
    {"name": "Code + locator", "write": "```` ```go path/x.go:212 ````", "renders": "locator line + code block", "notes": "Real code, quoted from the file. Each line carries its own `data-md`."},
    {"name": "Before / after pair", "write": "```` ```go path:212 before [bug] ```` immediately followed by ```` ```go path:212 after ````",
     "renders": "two blocks, changed lines auto-marked", "notes": "difflib marks the lines: after = green; before = red with `bug`, otherwise violet. A lone `before` fence is today's code with no marks."},
    {"name": "Pseudo-code", "write": "```` ```pseudo-go ```` (any `pseudo-<lang>`)", "renders": "code block tagged pseudo", "notes": "Logic that doesn't fit in a chart's boxes."},
    {"name": "Files list", "fence": "files", "write": "```` ```files ````: a path line, then `- change` lines", "renders": "file cards, one line per change", "notes": "Work folds."},
    {"name": "Ledger", "fence": "ledger", "write": "```` ```ledger Today: prorated ```` rows `name | formula | value`; `!` prefix = total/bug, `=` = total/ok",
     "renders": "named-step math table", "notes": "Consecutive ledger fences sit side by side. Money, rates, dates."},
    {"name": "Callouts", "write": "`> [!bug] Title`, `> [!ok]`, `> [!note]`, `> [!warn]`", "renders": "coloured callout box", "notes": "Prod errors, constraints."},
    {"name": "Check list", "write": "`- [ ] item` list items", "renders": "checkbox list", "notes": "Verify sections."},
    {"name": "Tables", "write": "GFM table", "renders": "scrolling table", "notes": "Test matrices, comparisons."},
    {"name": "html-block", "fence": "html-block", "write": "```` ```html-block ```` holding raw HTML",
     "renders": "inserted inline in a wrapper that carries `data-md`", "notes": "For one-off visuals. `<script>`, `on*` attributes and `javascript:` URLs are stripped. A plain ```` ```html ```` fence still shows HTML as code. Reused a lot? Promote it to a component (an L3 change)."},
    {"name": "Comments + copy to Claude", "write": "nothing", "renders": "select text or click a chart node → comment popover; open comments show as margin pins",
     "notes": "Saves to `comments` in the state file. Copy one or \"Copy all open\" gives `plan.md:42-47 (node x)` + quote + comment."},
]
FENCES = {"flow": chart, "erd": chart, "question": question_card, "challenge": challenge_card,
          "files": files_list, "ledger": ledger, "html-block": html_block}
assert {c["fence"] for c in COMPONENTS if c.get("fence")} == set(FENCES)


def fence_kind(tok):
    return (tok.info.split() or [""])[0]


def is_code(tok, role):
    return tok.type == "fence" and fence_kind(tok) not in FENCES and role in parse_code_info(tok.info)[2]


def fence(page, tok):
    kind, *args = tok.info.split() or [""]
    if kind in FENCES:
        return FENCES[kind](page, tok, args)
    if is_code(tok, "after"):
        page.warn(tok.map[0] + 1, "an `after` fence with no `before` fence right above it renders unmarked")
    return code(page, tok)


# ---------- markdown blocks ----------

def callout(page, block):
    inner = block[1:-1]
    if len(inner) < 3 or inner[0].type != "paragraph_open":
        return None
    first = inner[1].content
    m = re.match(r"^\[!(\w+)\][ \t]*(.*)", first, flags=re.S)
    if not m or m.group(1).lower() not in CALLOUTS:
        return None
    kind = m.group(1).lower()
    title_line, _, rest = m.group(2).partition("\n")
    title = title_line or CALLOUTS[kind]
    body = f'<p>{inline(rest)}</p>' if rest.strip() else ""
    body += md.renderer.render(inner[3:], md.options, {})
    return (f'<div class="callout {kind}" data-md="{rng(block[0])}"><h3>{inline(title)}</h3>{body}</div>')


def check_list(block):
    items = [i for i, t in enumerate(block) if t.type == "list_item_open"]
    marks = []
    for i in items:
        inl = next((t for t in block[i:] if t.type == "inline"), None)
        if not inl or not re.match(r"^\[[ xX]\]\s", inl.content):
            return None
        marks.append(inl)
    for inl in marks:
        txt = inl.children[0]
        txt.content = re.sub(r"^\[[ xX]\]\s", "", txt.content)
    block[0].attrJoin("class", "check")
    return md.renderer.render(block, md.options, {})


def render_block(page, block):
    t = block[0]
    if t.type == "fence":
        return fence(page, t)
    if t.type == "code_block":
        return code(page, t)
    if t.type == "blockquote_open":
        return callout(page, block) or md.renderer.render(block, md.options, {})
    if t.type == "table_open":
        return f'<div class="scroll" data-md="{rng(t)}">{md.renderer.render(block, md.options, {})}</div>'
    if t.type == "bullet_list_open":
        return check_list(block) or md.renderer.render(block, md.options, {})
    if t.type == "hr":
        return f'<hr data-md="{rng(t)}">'
    return md.renderer.render(block, md.options, {})


def render_blocks(page, blocks):
    out, i = [], 0
    while i < len(blocks):
        t = blocks[i][0]
        if t.type == "fence" and is_code(t, "before") and i + 1 < len(blocks) and is_code(blocks[i + 1][0], "after"):
            out.append(code_pair(page, t, blocks[i + 1][0]))
            i += 2
            continue
        if t.type == "fence" and fence_kind(t) in ("ledger", "question", "challenge"):
            kind, j = fence_kind(t), i
            group = []
            while j < len(blocks) and blocks[j][0].type == "fence" and fence_kind(blocks[j][0]) == kind:
                group.append(blocks[j][0])
                j += 1
            inner = "\n".join(fence(page, g) for g in group)
            span = f'{group[0].map[0] + 1}-{group[-1].map[1]}'
            out.append(f'<div class="{"ledgers" if kind == "ledger" else "cards"}" data-md="{span}">{inner}</div>')
            i = j
            continue
        out.append(render_block(page, blocks[i]))
        i += 1
    return "\n".join(out)


# ---------- structure: H1 = panel, H2 = fold ----------

def structure(page):
    """[{h1 block|None, intro: [blocks], folds: [{h2, gist, body}]}]"""
    panels, cur, fold = [], None, None
    blocks = blocks_of(page.tokens)
    i = 0
    while i < len(blocks):
        b = blocks[i]
        t = b[0]
        if t.type == "heading_open" and t.tag == "h1":
            cur = {"h1": b, "intro": [], "folds": []}
            panels.append(cur)
            fold = None
        elif t.type == "heading_open" and t.tag == "h2":
            if cur is None:
                cur = {"h1": None, "intro": [], "folds": []}
                panels.append(cur)
            gist = None
            if i + 1 < len(blocks) and blocks[i + 1][0].type == "paragraph_open":
                gist = blocks[i + 1]
                i += 1
            fold = {"h2": b, "gist": gist, "body": []}
            cur["folds"].append(fold)
        else:
            if cur is None:
                cur = {"h1": None, "intro": [], "folds": []}
                panels.append(cur)
            (fold["body"] if fold else cur["intro"]).append(b)
        i += 1
    if not panels:
        panels.append({"h1": None, "intro": [], "folds": []})
    if any(p["h1"] for p in panels) and panels[0]["h1"] is None and (panels[0]["intro"] or panels[0]["folds"]):
        page.err(panels[0]["intro"][0][0].map[0] + 1 if panels[0]["intro"] else None,
                 "content before the first # heading; every block must sit under a tab (H1)")
    return panels


def render_fold(page, f):
    h = f["h2"][0]
    line = h.map[0] + 1
    text = heading_text(f["h2"])
    attrs = page.attrs.get(line, {})
    num = re.match(r"^(\d{2})\s+(.*)$", text)
    sid = page.uid(attrs.get("id") or "p-" + slug(num.group(1) if num else text), line)
    title_html = md.renderer.render(f["h2"][1:2], md.options, {})
    if num:
        title_html = re.sub(r"^\s*" + re.escape(num.group(1)) + r"\s+", "", title_html, count=1)
        title_html = f'<span class="n">{num.group(1)}</span>{title_html}'
    gist = ""
    if f["gist"]:
        g = f["gist"]
        gtext = md.renderer.render(g[1:2], md.options, {})
        if len(re.sub(r"<[^>]+>", "", gtext)) > 260:
            page.warn(g[0].map[0] + 1, "gist runs past 260 chars; keep it to one or two lines")
        gist = f'<p class="gist" data-md="{rng(g[0])}">{gtext}</p>'
    last = f["body"][-1][0] if f["body"] else (f["gist"][0] if f["gist"] else h)
    end = last.map[1]
    opened = " open" if "open" in attrs.get("classes", []) else ""
    return (f'<section id="{esc(sid)}" data-md="{line}-{end}"><details class="fold"{opened}><summary>'
            f'<h2 data-md="{rng(h)}">{title_html}</h2>{gist}</summary>\n'
            f'<div class="fold-body">\n{render_blocks(page, f["body"])}\n</div></details></section>')


def panel_id(page, p, n):
    if not p["h1"]:
        return "doc"
    text = heading_text(p["h1"])
    line = p["h1"][0].map[0] + 1
    attrs = page.attrs.get(line, {})
    return attrs.get("id") or TAB_IDS.get(text.lower()) or slug(text)


def build(page):
    meta = page.meta
    ml = page.meta_lines
    if not meta:
        page.err(1, "no front matter (--- title: … contract: N ---)")
    for k in ("title", "contract"):
        if not meta.get(k):
            page.err(ml.get(k, 1), f"front matter needs `{k}:`")
    want = contract_version()
    if meta.get("contract") and str(want) != meta["contract"]:
        page.err(ml.get("contract"), f"contract: {meta['contract']} but l3-plan-render CONTRACT.md is contract {want}")
    for k in meta:
        if k not in FRONT_KEYS:
            page.warn(ml[k], f"unknown front matter key `{k}`")
    for n, ln in enumerate(page.lines, 1):
        if re.search(r"(?<!`)" + re.escape(PLACEHOLDER) + r"(?!`)", ln):
            page.err(n, f"leftover {PLACEHOLDER}")

    panels = structure(page)
    ids = [panel_id(page, p, i) for i, p in enumerate(panels)]
    if len(set(ids)) != len(ids):
        page.err(None, f"two tabs share an id: {ids}")
    order = [TAB_IDS.get(x.strip().lower(), slug(x)) for x in meta.get("tabs", "").split(",") if x.strip()]
    if order and panels[0]["h1"]:
        if sorted(order) != sorted(ids):
            page.err(ml.get("tabs"), f"tabs: lists {order} but the H1 tabs are {ids}")
        else:
            panels = [panels[ids.index(x)] for x in order]
            ids = order
    for pid in ids:
        page.ids.add(pid)

    tabbed = bool(panels[0]["h1"])
    tab_html, panel_html = [], []
    for i, (pid, p) in enumerate(zip(ids, panels)):
        body = []
        if p["intro"]:
            body.append(f'<section class="intro">\n{render_blocks(page, p["intro"])}\n</section>')
        body += [render_fold(page, f) for f in p["folds"]]
        inner = "\n".join(body)
        counted = ""
        if 'class="q"' in inner:
            page.has["questions"] = pid
            inner = ('<div class="qhead"><span class="progress" id="q-progress"></span></div>'
                     '<p class="sync" id="q-sync">Connecting to saved answers…</p>\n' + inner +
                     '\n<div class="row"><button class="btn" id="q-copy" type="button">Copy answers as text</button>'
                     '<span class="saved" id="q-copy-msg"></span></div><pre id="q-copy-text" hidden></pre>')
            counted = '<span class="count"></span>'
        if 'class="challenge"' in inner:
            page.has["challenges"] = pid
            inner = '<p class="sync" id="c-sync">Connecting to saved replies…</p>\n' + inner
            counted = '<span class="count"></span>'
        tools = '<div class="panel-tools"><button type="button" class="btn" data-fold-all>Expand all</button></div>\n' if p["folds"] else ""
        hidden = " hidden" if i and tabbed else ""
        role = f' role="tabpanel" aria-labelledby="tab-{pid}"' if tabbed else ""
        panel_html.append(f'<div class="panel" id="{esc(pid)}"{role}{hidden}>\n{tools}{inner}\n</div>')
        if tabbed:
            h = p["h1"][0]
            label = md.renderer.render(p["h1"][1:2], md.options, {})
            tab_html.append(f'<button type="button" role="tab" id="tab-{esc(pid)}" aria-controls="{esc(pid)}" '
                            f'aria-selected="{"true" if i == 0 else "false"}"{"" if i == 0 else " tabindex=-1"} '
                            f'data-md="{rng(h)}">{label}{counted}</button>')

    def fm(key, tag, cls, content):
        return f'<{tag} class="{cls}" data-md="{ml[key]}-{ml[key]}">{content}</{tag}>' if meta.get(key) else ""

    chips = [c.strip() for c in meta.get("chips", "").split("|") if c.strip()]
    chip_html = (f'<div class="chips" data-md="{ml["chips"]}-{ml["chips"]}">' +
                 "".join(f'<span class="chip{" key" if i == 0 else ""}">{inline(c)}</span>' for i, c in enumerate(chips)) +
                 "</div>") if chips else ""
    h1_key = "h1" if meta.get("h1") else "title"
    header = ("<header class=\"top\">\n" + fm("eyebrow", "span", "eyebrow", inline(meta.get("eyebrow"))) +
              (f'<h1 data-md="{ml[h1_key]}-{ml[h1_key]}">{inline(meta.get(h1_key))}</h1>' if meta.get(h1_key) else "") +
              fm("summary", "p", "summary", inline(meta.get("summary"))) + chip_html +
              (f'\n<nav class="tabs" role="tablist" aria-label="Sections">\n' + "\n".join(tab_html) + "\n</nav>" if tabbed else "") +
              "\n</header>")

    css = []
    if "flow" in page.css:
        css.append(f'<style id="flow-css">\n{(ROOT / "l1/l1-flow-svg/assets/flow.css").read_text().strip()}\n</style>')
    if "erd" in page.css:
        css.append(f'<style id="erd-css">\n{(ROOT / "l1/l1-erd-svg/assets/erd.css").read_text().strip()}\n</style>')
    css.append(f'<style id="plan-css">\n{(ASSETS / "plan.css").read_text().strip()}\n</style>')
    state = {}
    sp = state_path(page.path)
    if sp.exists():
        try:
            state = json.loads(sp.read_text() or "{}")
        except ValueError as e:
            page.warn(None, f"{sp.name} is not valid JSON ({e}); rendering without saved state")
    state_json = json.dumps(state, ensure_ascii=False).replace("</", "<\\/")
    body = (f'<div class="page">\n{header}\n' + "\n".join(panel_html) + "\n</div>\n")
    doc = ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,viewport-fit=cover\">\n"
            f"<title>{esc(meta.get('title', page.path.stem))}</title>\n"
            f'<meta name="generator" content="claude-plan-pilot l3-plan-render, contract {want}">\n'
            f'<meta name="plan-md" content="{esc(page.path.name)}">\n<meta name="plan-build" content="@STAMP@">\n'
            f"{FONTS}\n" + "\n".join(css) + "\n</head><body>\n"
            f"<!-- generated from {esc(page.path.name)} by l3-plan-render; edit the .md, not this file -->\n"
            + body +
            f'<script type="application/json" id="plan-state">{state_json}</script>\n'
            f'<script id="plan-js">\n{(ASSETS / "plan.js").read_text().strip()}\n</script>\n</body></html>\n')
    return doc.replace("@STAMP@", hashlib.sha1(doc.encode()).hexdigest()[:12], 1)


# ---------- commands ----------

def load(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"render.py: {p} not found")
    page = Page(p, p.read_text())
    out = build(page)
    return page, out


def report(page):
    for e in page.errors:
        print(f"ERROR {e}")
    for w in page.warns:
        print(f"warn  {w}")


def cmd_check(a):
    page, _ = load(a.md)
    report(page)
    if not page.errors:
        print(f"ok · {len(page.qids)} question(s) · {len(page.spec_ids)} figure spec(s)"
              + (f" · {len(page.warns)} warning(s)" if page.warns else ""))
    sys.exit(1 if page.errors else 0)


def cmd_build(a):
    page, out = load(a.md)
    report(page)
    if page.errors:
        sys.exit(f"render.py: {len(page.errors)} error(s); {html_path(a.md).name} not written")
    dest = Path(a.out) if a.out else html_path(a.md)
    atomic_write(dest, out)
    print(f"wrote {dest} ({len(out) // 1024} KB) from {Path(a.md).name}"
          + (f" · {len(page.warns)} warning(s)" if page.warns else ""))


def components_md():
    v = contract_version()
    rows = []
    for c in COMPONENTS:
        if c.get("hidden"):
            continue
        cell = lambda s: s.replace("|", "\\|")  # noqa: E731
        rows.append(f"| {c['name']} | {cell(c['write'])} | {cell(c['renders'])} | {cell(c['notes'])} |")
    return (f"---\ntitle: Components available\ncontract: {v}\ndoc: components\nskill: l3/l3-plan-render\n"
            f"summary: Every markdown construct l3-plan-render turns into HTML. Generated by `render.py components --write` from the render.py registry; never edit by hand.\n"
            f"chips: contract {v} | generated\n---\n"
            f"# Components\n\n"
            f"## Component table {{#table .open}}\n"
            f"Write the left column in plan.md; the renderer produces the right. Full syntax: `l3/l3-plan-render/CONTRACT.md`.\n\n"
            f"| Component | Write in .md | Renders as | Notes |\n|---|---|---|---|\n" + "\n".join(rows) + "\n")


def cmd_components(a):
    text = components_md()
    if a.write:
        atomic_write(COMPONENTS_DOC, text)
        print(f"wrote {COMPONENTS_DOC}")
    else:
        sys.stdout.write(text)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in ("build", "check", "components", "-h", "--help"):
        argv.insert(0, "build")
    ap = argparse.ArgumentParser(prog="render.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="check, then write the HTML")
    b.add_argument("md")
    b.add_argument("-o", "--out", help="write here instead of beside the .md")
    b.set_defaults(fn=cmd_build)
    c = sub.add_parser("check", help="lint only")
    c.add_argument("md")
    c.set_defaults(fn=cmd_check)
    k = sub.add_parser("components", help="the component table from the registry")
    k.add_argument("--write", action="store_true", help=f"write {COMPONENTS_DOC.relative_to(ROOT)}")
    k.set_defaults(fn=cmd_components)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
