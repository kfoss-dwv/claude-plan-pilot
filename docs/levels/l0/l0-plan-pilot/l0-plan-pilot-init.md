---
title: l0-plan-pilot init
contract: 1
doc: init
skill: l0/l0-plan-pilot
status: landed
summary: How l0-plan-pilot was first built, from the plan-pilot plan (2026-11-23). A record: never edited after landing.
---
## 07 L0: l0-plan-pilot + husky render lock {#p-07 .open}
Routes to an adapter, serves the result, and holds the edit rules. Husky hard-blocks an L3 commit without l2-plan-writer, and asks for a reason when both changed.

- Routing: fix → simple-code-change, new code → large-code-write, else plan-writer. Names the pick in one line and builds without waiting.
- Writes to `${user_config.plans_root}/${user_config.path_template}`; runs `serve.py start` itself (Q5).
- Owns `references/editing-rules.md`; refuses L3 edits unless asked for a major render change.
- `scripts/render_lock.py` + `.husky/pre-commit` + `.husky/commit-msg`: L3 without the router = blocked; contract drift = blocked; both = reason on `/dev/tty`, recorded as a `Render-Change:` trailer.

> [!note] As built
> Skill folders carry the level prefix (`l0/l0-plan-pilot`) because Claude Code 2.1.285 names plugin skills by folder, not by frontmatter `name`.
