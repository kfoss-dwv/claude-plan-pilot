#!/usr/bin/env python3
"""End-to-end eval: one headless Claude Code session with this plugin loaded, on a fixed prompt.

Usage:
  run_eval.py [--runs N] [--label L] [--model M] [--budget USD] [--keep]

Each run copies sample-app/ to a temp dir, runs
  claude -p --plugin-dir <repo> --output-format stream-json "<PROMPT.md>"
there, then scores what it produced: tokens, cost, wall time, script exceptions,
render.py check, and tests/fidelity.py deviations (md ↔ html). One JSON line per run is
appended to results.jsonl (with the git sha) so later iterations can be compared;
aggregate.py averages them.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
L3 = ROOT / "l3/l3-plan-render"
sys.path.insert(0, str(L3 / "scripts"))
sys.path.insert(0, str(L3 / "tests"))
import render  # noqa: E402
import fidelity  # noqa: E402

PROMPT = (HERE / "PROMPT.md").read_text().strip()
TOOLS = ("Read,Write,Edit,Glob,Grep,Skill,Bash(python3:*),Bash(ls:*),Bash(mkdir:*),Bash(cat:*),"
         "Bash(find:*),Bash(grep:*),Bash(head:*),Bash(sed -n:*),Bash(wc:*)")
OUR_SCRIPTS = ("render.py", "serve.py", "flow.py", "erd.py", "fidelity.py", "plan.py")
SKILLS_DIR = Path.home() / ".claude" / "skills"
HTML_PLAN = SKILLS_DIR / "html-plan" / "scripts" / "plan.py"


def git_sha():
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "l0", "l1", "l2", "l3"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return sha + ("+dirty" if dirty else "") if sha else "none"
    except OSError:
        return "none"


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content)


def run_one(run_id, a):
    base = Path(tempfile.mkdtemp(prefix=f"plan-pilot-eval-{run_id}-"))
    work, home = base / "work", base / "pphome"
    shutil.copytree(HERE / "sample-app", work)
    old = a.skill == "html-plan"            # baseline: the standalone html-plan skill, no plugin loaded
    prompt = re.sub(r"^plan-pilot:", "html-plan:", PROMPT) if old else PROMPT
    load = ["--add-dir", str(SKILLS_DIR)] if old else ["--plugin-dir", str(ROOT), "--add-dir", str(ROOT)]
    cmd = ["claude", "-p", *load, "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--allowedTools", TOOLS, "--strict-mcp-config", "--no-session-persistence",
           "--max-budget-usd", str(a.budget)]
    if a.model:
        cmd += ["--model", a.model]
    cmd.append(prompt)
    env = {**os.environ, "CLAUDE_PLAN_PILOT_HOME": str(home)}
    t0 = time.time()
    p = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=a.timeout)
    wall = time.time() - t0
    (base / "stream.jsonl").write_text(p.stdout)
    (base / "stderr.txt").write_text(p.stderr)

    events = []
    for ln in p.stdout.splitlines():
        try:
            events.append(json.loads(ln))
        except ValueError:
            pass
    result = next((e for e in reversed(events) if e.get("type") == "result"), {})
    tool_uses, skills, exceptions, check_errors = 0, [], [], 0
    for e in events:
        msg = e.get("message") or {}
        if not isinstance(msg, dict):          # e.g. {"type":"system","subtype":"permission_denied","message":"…"}
            continue
        for c in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
            if c.get("type") == "tool_use":
                tool_uses += 1
                if c.get("name") == "Skill":
                    skills.append((c.get("input") or {}).get("skill") or (c.get("input") or {}).get("command"))
            if c.get("type") == "tool_result":
                t = text_of(c.get("content"))
                if "Traceback (most recent call last)" in t and any(s in t for s in OUR_SCRIPTS):
                    exceptions.append(t[-400:])
                check_errors += len(re.findall(r"^ERROR ", t, flags=re.M))
    usage = result.get("usage") or {}
    tokens = {k: usage.get(k, 0) or 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    models = list((result.get("modelUsage") or {}).keys())

    if old:
        return finish_html_plan(run_id, a, base, work, p, result, wall, models, tokens, tool_uses, skills, exceptions, check_errors)
    plans = sorted(work.rglob("plan.md"))
    plans = [x for x in plans if "node_modules" not in x.parts]
    scored = []
    for md in plans:
        page = render.Page(md, md.read_text())
        html = render.build(page)
        out = render.html_path(md)
        agent_built = out.exists() and out.stat().st_mtime >= md.stat().st_mtime
        if not page.errors:                      # score a fresh build of the final .md
            out.write_text(html)
        fid = fidelity.check(md, out) if out.exists() else {"deviations": None, "html_bytes": 0, "md_bytes": md.stat().st_size}
        meta = page.meta
        scored.append({"path": str(md.relative_to(work)), "check_errors": page.errors, "warnings": len(page.warns),
                       "deviations": fid["deviations"], "deviation_detail": {k: fid.get(k) for k in ("missing", "text", "counts", "leftovers")},
                       "md_bytes": fid["md_bytes"], "html_bytes": fid["html_bytes"], "type": meta.get("type"),
                       "questions": len(page.qids), "figures": len(page.spec_ids), "agent_built": agent_built})
    reg = home / "ports.json"
    served = bool(reg.exists() and json.loads(reg.read_text() or "{}")) or "127.0.0.1:" in (result.get("result") or "")
    subprocess.run([sys.executable, str(L3 / "scripts/serve.py"), "stop", "--all"], env=env, capture_output=True)

    first = scored[0] if scored else {}
    row = {
        "id": run_id, "label": a.label, "skill": a.skill, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sha": git_sha(),
        "models": models, "exit": p.returncode, "is_error": result.get("is_error"), "subtype": result.get("subtype"),
        "duration_s": round((result.get("duration_ms") or wall * 1000) / 1000, 1), "wall_s": round(wall, 1),
        "turns": result.get("num_turns"), "tool_uses": tool_uses, "skills": skills,
        "cost_usd": result.get("total_cost_usd"), **tokens,
        "total_tokens": sum(tokens.values()),
        "script_exceptions": len(exceptions), "exception_tails": exceptions[:3], "check_errors_seen": check_errors,
        "plans": len(scored), "check_ok": bool(scored) and not first.get("check_errors"),
        "deviations": first.get("deviations"), "md_bytes": first.get("md_bytes"), "html_bytes": first.get("html_bytes"),
        "adapter": first.get("type"), "agent_built": first.get("agent_built"), "questions": first.get("questions"), "figures": first.get("figures"),
        "served": served, "plan_detail": scored, "workdir": str(base),
    }
    with open(HERE / "results.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    if not a.keep and row["check_ok"] and not exceptions:
        shutil.rmtree(base, ignore_errors=True)
        row["workdir"] = "(removed)"
    return row


def finish_html_plan(run_id, a, base, work, p, result, wall, models, tokens, tool_uses, skills, exceptions, check_errors):
    """Score an html-plan run: its own plan.py check; there is no source .md, so no fidelity."""
    subprocess.run(["pkill", "-f", str(work)], capture_output=True)      # any plan.py serve it left running
    pages = sorted(x for x in work.rglob("*.html") if "node_modules" not in x.parts and not x.name.startswith("."))
    page = next((x for x in pages if x.name == "index.html"), pages[0] if pages else None)
    check = subprocess.run([sys.executable, str(HTML_PLAN), "check", str(page)], capture_output=True, text=True) if page else None
    row = {
        "id": run_id, "label": a.label, "skill": a.skill, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sha": "html-plan", "models": models, "exit": p.returncode, "is_error": result.get("is_error"), "subtype": result.get("subtype"),
        "duration_s": round((result.get("duration_ms") or wall * 1000) / 1000, 1), "wall_s": round(wall, 1),
        "turns": result.get("num_turns"), "tool_uses": tool_uses, "skills": skills, "cost_usd": result.get("total_cost_usd"), **tokens,
        "total_tokens": sum(tokens.values()), "script_exceptions": len(exceptions), "exception_tails": exceptions[:3],
        "check_errors_seen": check_errors, "plans": len(pages), "check_ok": bool(check and check.returncode == 0),
        "check_output": (check.stdout + check.stderr)[-600:] if check else "no page", "deviations": None, "md_bytes": None,
        "html_bytes": page.stat().st_size if page else None, "adapter": "html-plan",
        "questions": len(re.findall(r'<article class="q"', page.read_text())) if page else None,
        "figures": len(re.findall(r'class="(?:flow|erd)-figure"', page.read_text())) if page else None,
        "served": "127.0.0.1:" in (result.get("result") or ""), "workdir": str(base),
    }
    with open(HERE / "results.jsonl", "a") as f:
        f.write(json.dumps(row) + "\n")
    if not a.keep and row["check_ok"] and not exceptions:
        shutil.rmtree(base, ignore_errors=True)
        row["workdir"] = "(removed)"
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--label", default="manual")
    ap.add_argument("--id", default=None, help="run id prefix")
    ap.add_argument("--model", default=None)
    ap.add_argument("--skill", choices=("plan-pilot", "html-plan"), default="plan-pilot",
                    help="html-plan = baseline run of the standalone html-plan skill (same prompt, no plugin)")
    ap.add_argument("--budget", type=float, default=5.0, help="max USD per run (claude --max-budget-usd)")
    ap.add_argument("--timeout", type=int, default=1500)
    ap.add_argument("--keep", action="store_true", help="keep the temp workdir even when the run passed")
    a = ap.parse_args()
    for i in range(a.runs):
        rid = f"{a.id or a.label}-{int(time.time())}-{i}"
        row = run_one(rid, a)
        slim = {k: v for k, v in row.items() if k not in ("plan_detail",)}
        print(json.dumps(slim, indent=2))


if __name__ == "__main__":
    main()
