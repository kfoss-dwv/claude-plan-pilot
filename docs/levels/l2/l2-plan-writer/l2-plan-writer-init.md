---
title: l2-plan-writer init
contract: 1
doc: init
skill: l2/l2-plan-writer
status: landed
summary: How l2-plan-writer was first built, from the plan-pilot plan (2026-11-23). A record: never edited after landing.
---
## 05 L2 router {#p-05 .open}
Shared writing rules ported from html-plan, plus how Claude answers comments. Pins the render contract it was written against.

- `render-contract: 1`; CONTRACT.md is the only syntax reference.
- Ends with `render.py check` and a hand-off to L0 to serve; never serves itself.
- `references/comments.md`: reading `plan.state.json` comments, editing plan.md at the `md` range, replying, resolving.
