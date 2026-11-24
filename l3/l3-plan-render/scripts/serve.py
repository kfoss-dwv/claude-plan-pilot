#!/usr/bin/env python3
"""Serve contract-format .md files as live pages on 127.0.0.1.

Usage:
  serve.py start DIR|FILE.md [--port N] [--foreground]   detach, print the URL (reuses a live server for DIR)
  serve.py list                                           live servers from the registry
  serve.py stop DIR|FILE.md | --all                        stop a server

DIR's every .md renders on request (plan.md -> index.html); `/` is DIR/plan.md when it exists,
otherwise an index of every .md (so `serve.py start docs/` is the docs browser). A page
polls GET /__plan/state?page=… and reloads when its .md is rebuilt; POST
/__plan/{answers|challenges|comments}/{id}?page=… merges a row into X.state.json under a lock.
Servers register in ~/.claude-plan-pilot/ports.json ($CLAUDE_PLAN_PILOT_HOME overrides),
outside the plugin, because an installed copy is replaced on update. Stdlib only.
"""
import argparse
import fcntl
import html
import http.server
import json
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
import atexit
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render  # noqa: E402

HOME = Path(os.environ.get("CLAUDE_PLAN_PILOT_HOME", Path.home() / ".claude-plan-pilot"))
PORTS = HOME / "ports.json"
PORT_RANGE = range(8790, 8840)          # clear of html-plan's 8765-8784
PAGE_FIELDS = {"answers": ("choice", "note"), "challenges": ("status", "note"),
               "comments": ("md", "node", "quote", "text", "status", "createdAt")}
ROW_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
POLL_MS = 2500


def die(msg):
    sys.exit(f"serve.py: {msg}")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------- registry ----------

@contextmanager
def registry():
    """Yield the live registry under an exclusive lock; writes back on exit. Dead pids are pruned."""
    HOME.mkdir(parents=True, exist_ok=True)
    with open(HOME / "ports.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            reg = json.loads(PORTS.read_text() or "{}") if PORTS.exists() else {}
        except ValueError:
            reg = {}
        reg = {p: r for p, r in reg.items() if pid_alive(r.get("pid"))}
        box = {"reg": reg}
        yield box
        render.atomic_write(PORTS, json.dumps(box["reg"], indent=2) + "\n")


def pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def bindable(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def claim_port(plan, want=0):
    """(port, fresh). fresh=False means a live server already serves this plan."""
    with registry() as box:
        reg = box["reg"]
        for p, r in reg.items():
            if r["plan"] == plan:
                return int(p), False
        for p in ([want] if want else PORT_RANGE):
            if str(p) not in reg and bindable(p):
                reg[str(p)] = {"pid": os.getpid(), "plan": plan, "started": now()}
                return p, True
    die(f"no free port in {PORT_RANGE.start}-{PORT_RANGE.stop - 1}" if not want else f"port {want} is taken")


def release(port):
    try:
        with registry() as box:
            r = box["reg"].get(str(port))
            if r and r.get("pid") == os.getpid():
                del box["reg"][str(port)]
    except OSError:
        pass


# ---------- server ----------

class Site:
    def __init__(self, target):
        target = Path(target).resolve()
        self.root = target if target.is_dir() else target.parent
        self.only = None if target.is_dir() else target
        self.lock = threading.Lock()

    def mds(self):
        if self.only:
            return [self.only]
        return sorted(p for p in self.root.rglob("*.md") if not any(part.startswith((".", "node_modules")) for part in p.relative_to(self.root).parts))

    def md_for(self, urlpath):
        """URL path -> source .md, or None. / -> plan.md (or the index), /a/b.html -> a/b.md, /a/ -> a/plan.md."""
        rel = unquote(urlpath).lstrip("/")
        if self.only:
            return self.only if rel in ("", render.html_path(self.only).name) else None
        if rel in ("",):
            p = self.root / "plan.md"
            return p if p.exists() else None
        if rel.endswith("/") or rel.endswith("index.html"):
            p = self.root / rel.rsplit("index.html", 1)[0] / "plan.md"
        elif rel.endswith(".html"):
            p = self.root / (rel[:-5] + ".md")
        else:
            return None
        p = p.resolve()
        if self.root not in p.parents and p.parent != self.root:
            return None
        return p if p.exists() else None

    def stale(self, md, out):
        if not out.exists():
            return True
        t = out.stat().st_mtime
        deps = [md, render.ASSETS / "plan.css", render.ASSETS / "plan.js", Path(render.__file__), render.FLOW_PY, render.ERD_PY]
        return any(d.exists() and d.stat().st_mtime > t for d in deps)

    def build(self, md):
        """Rebuild when the .md (or the renderer) is newer. Returns (html path, errors)."""
        out = render.html_path(md)
        with self.lock:
            if self.stale(md, out):
                page = render.Page(md, md.read_text())
                text = render.build(page)
                if page.errors:
                    return out, page.errors
                render.atomic_write(out, text)
        return out, []

    def build_stamp(self, out):
        m = re.search(r'<meta name="plan-build" content="([^"]+)"', out.read_text()[:4096]) if out.exists() else None
        return m.group(1) if m else ""

    def index(self):
        rows = []
        for p in self.mds():
            rel = p.relative_to(self.root)
            href = str(rel.parent / "index.html") if p.name == "plan.md" else str(rel.with_suffix(".html"))
            meta, _, _ = render.split_front(p.read_text())
            rows.append(f'<li><a href="/{html.escape(href)}">{html.escape(meta.get("title") or str(rel))}</a> '
                        f'<code>{html.escape(str(rel))}</code>{" · " + html.escape(meta["status"]) if meta.get("status") else ""}</li>')
        css = (render.ASSETS / "plan.css").read_text()
        return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{html.escape(self.root.name)}</title>{render.FONTS}<style>{css}</style></head><body><div class="page">'
                f'<header class="top"><span class="eyebrow">serve.py · {html.escape(str(self.root))}</span><h1>{html.escape(self.root.name)}</h1></header>'
                f'<section><ul>{"".join(rows) or "<li>No .md files.</li>"}</ul></section></div></body></html>')


def read_state(path):
    d = json.loads(path.read_text() or "{}") if path.exists() else {}
    return {**d, **{c: dict(d.get(c) or {}) for c in PAGE_FIELDS}}


def make_handler(site, verbose=False):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "plan-pilot"

        def log_message(self, fmt, *args):
            if verbose:
                sys.stderr.write("serve: " + fmt % args + "\n")

        def send(self, code, body, ctype="application/json"):
            data = (json.dumps(body) if ctype == "application/json" else body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def host_ok(self):
            if (self.headers.get("Host") or "").rsplit(":", 1)[0] not in ("127.0.0.1", "localhost"):
                self.send(403, {"error": "bad host"})
                return False
            return True

        def page_md(self, q):
            return site.md_for(urlparse((q.get("page") or ["/"])[0]).path)

        def do_GET(self):
            if not self.host_ok():
                return
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/__plan/state":
                md = self.page_md(q)
                if not md:
                    return self.send(404, {"error": "no .md for that page"})
                out, errs = site.build(md)
                sp = render.state_path(md)
                try:
                    rows = read_state(sp)
                except ValueError as e:
                    return self.send(500, {"error": f"{sp.name} is not valid JSON: {e}"})
                return self.send(200, {**rows, "mtime": sp.stat().st_mtime_ns if sp.exists() else 0,
                                       "build": site.build_stamp(out), "errors": errs, "poll": POLL_MS, "file": sp.name})
            if u.path in ("/__index", "/") and (u.path == "/__index" or not site.md_for("/")):
                return self.send(200, site.index(), "text/html")
            md = site.md_for(u.path)
            if not md:
                return self.send(404, {"error": "not found"})
            out, errs = site.build(md)
            if errs and not out.exists():
                return self.send(500, "<pre>" + html.escape("\n".join(errs)) + "</pre>", "text/html")
            body = out.read_text()
            if errs:   # keep the last good page, flag the broken source on top
                body = body.replace('<div class="page">', '<div class="page"><div class="callout bug"><h3>render.py check failed; showing the last good build</h3><pre>'
                                    + html.escape("\n".join(errs)) + "</pre></div>", 1)
            self.send(200, body, "text/html")

        def do_POST(self):
            if not self.host_ok():
                return
            u = urlparse(self.path)
            m = re.fullmatch(r"/__plan/(answers|challenges|comments)/([^/]+)", u.path)
            if not m or not ROW_ID.match(m.group(2)):
                return self.send(404, {"error": "not found"})
            md = self.page_md(parse_qs(u.query))
            if not md:
                return self.send(404, {"error": "no .md for that page"})
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self.send(415, {"error": "send application/json"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            except ValueError:
                return self.send(400, {"error": "bad JSON"})
            coll, rid = m.groups()
            sp = render.state_path(md)
            with site.lock:
                try:
                    rows = read_state(sp)
                except ValueError as e:
                    return self.send(500, {"error": f"{sp.name} is not valid JSON: {e}"})
                row = dict(rows[coll].get(rid) or {})
                for k in PAGE_FIELDS[coll]:            # the page only ever writes these
                    if isinstance(body.get(k), str):
                        row[k] = body[k]
                if coll == "comments":
                    row.setdefault("createdAt", now())
                    row.setdefault("status", "open")
                else:
                    row.update(source="page", agent="", updatedAt=now())
                rows[coll][rid] = row
                render.atomic_write(sp, json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            self.send(200, {"id": rid, "data": row})

    return Handler


def serve_forever(target, port, verbose=False):
    site = Site(target)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(site, verbose))
    atexit.register(release, port)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def url_for(port, target):
    return f"http://127.0.0.1:{port}/"


# ---------- commands ----------

def cmd_start(a):
    target = Path(a.target).resolve()
    if not target.exists():
        die(f"{target} not found")
    if target.is_file() and target.suffix != ".md":
        die("serve a directory or a .md file")
    if a.foreground or a.child:
        port, fresh = claim_port(str(target), a.port)
        if not fresh:
            print(f"already serving {target} at {url_for(port, target)}", flush=True)
            return
        if not a.child:
            print(f"serving {url_for(port, target)} · {target} · Ctrl-C to stop", flush=True)
        else:
            (HOME / f"ready-{a.child}").write_text(str(port))
        serve_forever(target, port, a.verbose)
        return
    with registry() as box:              # fast path: already live?
        for p, r in box["reg"].items():
            if r["plan"] == str(target):
                print(f"already serving {target}\n{url_for(p, target)}")
                return
    HOME.mkdir(parents=True, exist_ok=True)
    token = f"{os.getpid()}-{time.time_ns()}"
    log = open(HOME / "serve.log", "a")
    cmd = [sys.executable, str(Path(__file__).resolve()), "start", str(target), "--child", token]
    if a.port:
        cmd += ["--port", str(a.port)]
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, close_fds=True)
    ready = HOME / f"ready-{token}"
    for _ in range(100):
        if ready.exists():
            port = int(ready.read_text())
            ready.unlink(missing_ok=True)
            print(f"serving {target}\n{url_for(port, target)}")
            return
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    with registry() as box:
        for p, r in box["reg"].items():
            if r["plan"] == str(target):
                print(f"already serving {target}\n{url_for(p, target)}")
                return
    die(f"server did not start; see {HOME / 'serve.log'}")


def cmd_list(a):
    with registry() as box:
        reg = box["reg"]
    if not reg:
        print("no live servers")
    for p, r in sorted(reg.items()):
        print(f"http://127.0.0.1:{p}/  pid {r['pid']}  {r['plan']}  since {r['started']}")


def cmd_stop(a):
    with registry() as box:
        reg = box["reg"]
    want = None if a.all else str(Path(a.target).resolve())
    hit = [(p, r) for p, r in reg.items() if want is None or r["plan"] == want]
    if not hit:
        print(f"nothing serving {a.target or 'anything'}")
        return
    for p, r in hit:
        try:
            os.kill(int(r["pid"]), signal.SIGTERM)
        except OSError:
            pass
        print(f"stopped http://127.0.0.1:{p}/ ({r['plan']})")
    for _ in range(40):
        with registry() as box:
            if not any(p in box["reg"] for p, _ in hit):
                return
        time.sleep(0.05)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="serve.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("target")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--foreground", action="store_true", help="don't detach")
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--child", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_start)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    t = sub.add_parser("stop")
    t.add_argument("target", nargs="?")
    t.add_argument("--all", action="store_true")
    t.set_defaults(fn=cmd_stop)
    a = ap.parse_args(argv)
    if a.cmd == "stop" and not (a.target or a.all):
        ap.error("stop needs DIR|FILE or --all")
    a.fn(a)


if __name__ == "__main__":
    main()
