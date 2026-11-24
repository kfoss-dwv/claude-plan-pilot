---
title: l3-plan-render init
contract: 1
doc: init
skill: l3/l3-plan-render
status: landed
summary: How l3-plan-render was first built, from the plan-pilot plan (2026-11-23). A record: never edited after landing.
---
## 03 CONTRACT.md + render.py {#p-03 .open}
One md syntax, numbered (contract 1). render.py converts it 1:1 to self-contained HTML.

- Starts from html-plan's md-source design; adds before/after pairs, `pseudo-<lang>`, `html-block`, `{.open}`, `[!warn]`, `=` ledger totals and `- [ ]` check lists.
- Every H2 is a fold; the first paragraph is the gist.

## 04 serve.py, ports.json, comment layer {#p-04}
Detached server with a shared port registry; comments, answers and challenge replies land in `plan.state.json`.

- Comment rows `{md, node?, quote, text, status, createdAt, reply?}`; "Copy all open" gives `plan.md:42-47 (node x)` + quote + comment.

## 08 Fixtures + tests {#p-08}
Two fixtures (simple, large), golden renders, `tests/fidelity.py` (md ↔ html deviation check).
