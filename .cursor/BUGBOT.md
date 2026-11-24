# Bugbot: keep docs/ true to the code

1. A PR that changes lN/<skill>/ must also change docs/levels/lN/<skill>/<skill>.md.
2. A PR that adds, removes or renames a render component (render.py registry or
   CONTRACT.md) must update docs/COMPONENTS_AVAILABLE.md (regenerate it with
   `python3 l3/l3-plan-render/scripts/render.py components --write`; never hand-edit it).
3. A PR that adds, moves or removes a skill, script or level, or changes the level
   flow, must update docs/OVERVIEW.md (flow chart and file tree).
4. A new skill ships with docs/levels/lN/<skill>/<skill>.md and <skill>-init.md.
5. <skill>-init.md is a record: once landed, changes go in a new
   <skill>-update-<slug>.md, and <skill>.md is updated when that lands (front matter
   `status: landed` on the update doc). Never edit an init doc or a landed update doc.
6. Every .md under docs/ is contract format: front matter with contract: N equal to
   l3/l3-plan-render/CONTRACT.md. No raw HTML outside an html-block fence.
7. An html-block copied into 3+ docs is a candidate to promote into a component:
   flag it and name the files.
8. A PR that changes anything under l3/ must also change l2/l2-plan-writer/ (the husky
   render lock enforces this locally; flag PRs that bypassed it with --no-verify), and
   the commit should carry a `Render-Change:` trailer.
