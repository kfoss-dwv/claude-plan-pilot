---
title: l3-plan-render
contract: 1
doc: skill
skill: l3/l3-plan-render
status: landed
summary: Contract-format markdown to one self-contained HTML page, 1:1, plus a detached server for live answers and comments.
---
## render.py {#render .open}
A registry, one renderer per construct; `check` lints, `components` prints the table.

- Every block carries `data-md="a-b"`; chart nodes point at their `"id"` line.
- Code pairs: difflib marks after = green, before = red (`bug`) or violet.
- html-block: `<script>`, `on*`, `javascript:` stripped.
- Finds L1 by `Path(__file__).parents[3]`, never `~/.claude/skills`.

## serve.py {#serve}
`start DIR` detaches and registers in `~/.claude-plan-pilot/ports.json` (8790–8839); a second start for the same DIR reuses the live server.

- GET a page rebuilds it when the .md (or the renderer) is newer; the page polls `/__plan/state` and reloads on a new build stamp.
- POST `/__plan/{answers|challenges|comments}/{id}` merges into `X.state.json` under a lock.

## Tests {#tests}
`python3 -m unittest discover -s l3/l3-plan-render/tests -t l3/l3-plan-render/tests`: golden renders, mapping + fidelity, lint, ports, serve integration.
