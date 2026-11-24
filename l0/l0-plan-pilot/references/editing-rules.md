# Who may edit which level

| level | skills                                        | edits                                   |
|-------|-----------------------------------------------|-----------------------------------------|
| L1    | l1-flow-svg, l1-erd-svg                       | free; spec stays backward-compatible    |
| L2    | l2-simple-code-change, l2-large-code-write    | free                                    |
| L2    | l2-plan-writer                                | free; must match render-contract        |
| L3    | l3-plan-render                                | only for a "major render change":       |
|       |                                               | husky blocks the commit unless          |
|       |                                               | l2-plan-writer changes with it, then    |
|       |                                               | asks you for a confirmation message     |

- A new plan type is a new adapter dir under `l2/` (SKILL.md + template.md, ~60 lines) that
  uses existing components. Add it to l0-plan-pilot's routing list. Nothing else changes.
- A new markdown construct is a new component: a CONTRACT.md entry, a renderer in
  `render.py`'s registry, a `contract:` bump in CONTRACT.md and `render-contract:` in
  l2-plan-writer, then `render.py components --write`. That is an L3 change.
- Refuse an L3 edit unless the user said "major render change" (or plainly asked to change
  the renderer). Even then the commit is the user's: `.husky/pre-commit` asks for a reason
  on their terminal, so a commit you run that touches `l3/` fails by design.
- Every change to `lN/<skill>/` updates `docs/levels/lN/<skill>/<skill>.md` in the same PR
  (Bugbot enforces it). Plan the change first as `<skill>-update-<slug>.md` there.
- Run `python3 -m unittest discover -s l3/l3-plan-render/tests -t l3/l3-plan-render/tests` and
  `python3 -m unittest discover -s tests` before calling a change done.
