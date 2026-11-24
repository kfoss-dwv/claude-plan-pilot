#!/usr/bin/env python3
"""Husky pre-commit: the L3 render lock.

- Nothing staged under l3/            -> pass.
- l3/ staged without l2/l2-plan-writer/  -> blocked, no prompt.
- CONTRACT.md `contract:` != l2-plan-writer `render-contract:` (staged versions) -> blocked.
- Both staged                          -> asks for a reason on /dev/tty; empty = abort. The reason
  goes to .git/RENDER_CHANGE and .husky/commit-msg appends it as a `Render-Change:` trailer.

The prompt reads the terminal, so a commit run without one (an agent, CI) fails with a clear
message. `git commit --no-verify` skips it, as with any hook. Stdlib only.
"""
import re
import subprocess
import sys
from pathlib import Path

CONTRACT = "l3/l3-plan-render/CONTRACT.md"
ROUTER = "l2/l2-plan-writer/SKILL.md"


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def fail(msg):
    sys.stderr.write(f"render lock: {msg}\n")
    sys.exit(1)


def staged_version(path, key):
    try:
        text = git("show", f":{path}")
    except subprocess.CalledProcessError:
        return None
    m = re.search(rf"^{key}:\s*(\d+)", text, flags=re.M)
    return m.group(1) if m else None


def main():
    staged = [p for p in git("diff", "--cached", "--name-only").splitlines() if p]
    l3 = [p for p in staged if p.startswith("l3/")]
    if not l3:
        return
    if not any(p.startswith("l2/l2-plan-writer/") for p in staged):
        fail("L3 changed without l2-plan-writer. Update the router (l2/l2-plan-writer/) in the same commit.\n"
             f"  staged under l3/: {', '.join(l3[:5])}{' …' if len(l3) > 5 else ''}")
    c, r = staged_version(CONTRACT, "contract"), staged_version(ROUTER, "render-contract")
    if c != r:
        fail(f"CONTRACT.md is contract {c} but l2-plan-writer says render-contract {r}. Make them match.")
    try:                                  # two handles: text-mode "r+" on a tty isn't seekable
        tin, tout = open("/dev/tty"), open("/dev/tty", "w")
    except OSError:
        fail("an L3 render change needs your confirmation. Commit from your own terminal.")
    with tin, tout:
        tout.write("L3 render change. Why? (empty = abort): ")
        tout.flush()
        msg = tin.readline().strip()
    if not msg:
        fail("aborted")
    gitdir = Path(git("rev-parse", "--git-dir").strip())
    (gitdir / "RENDER_CHANGE").write_text(msg.replace("\n", " ") + "\n")


if __name__ == "__main__":
    main()
