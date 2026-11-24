---
name: l0-plan-pilot
description: claude-plan-pilot L0 orchestrator. Plans a feature, fix, endpoint, schema or infra change as a plan-pilot page - Claude writes a short plan.md, a script renders it to an interactive HTML page (tabs, folds, diagrams, answer cards, comments) and serves it. Use when the user says "plan-pilot", "pilot plan", invokes claude-plan-pilot, or asks to plan / spec / scope work and wants a plan-pilot page. Also routes "change the plan-pilot skill/renderer" requests and reviews answers or comments on an existing plan-pilot plan. Not for a design doc for team review, or an idea still being talked through.
---

# l0-plan-pilot

Routes the request to an L2 writer, then builds and serves the page. Levels:
L1 draw (`l1-flow-svg`, `l1-erd-svg`) · L2 write (`l2-plan-writer` + adapters) ·
L3 render (`l3-plan-render`, locked).

## New plan

1. **Route.** Pick the adapter and say it in one line, then build without waiting:
   - a fix or change to existing code → **l2-simple-code-change**
   - new code or a new system (endpoint, service, job, table) → **l2-large-code-write**
   - anything else (migration runbook, investigation, comparison) → **l2-plan-writer** alone
   e.g. *"simple-code-change → billing/plan-pilot/promo-credit. Say 'add testing' or
   'add challenges' for more tabs."*
2. **Destination.** `${user_config.plans_root}/${user_config.path_template}/plan.md`, with
   `{project}` = the feature or effort (reuse an existing project folder) and `{slug}` = a
   short kebab name. If those placeholders show literally, use
   `~/github/claude-plans/{project}/plan-pilot/{slug}/plan.md`. Never overwrite an existing
   plan folder unless asked. Exception: a plan to change a skill in this plugin goes to
   `docs/levels/lN/<skill>/<skill>-update-<slug>.md` in the plugin repo.
3. **Write.** Load the adapter (it loads l2-plan-writer) and follow it to a `plan.md` that
   passes `render.py check`, then build it.
4. **Serve and hand over.**
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/l3/l3-plan-render/scripts/serve.py start DIR
   ```
   Give the user the URL it prints and the `plan.md` path. Stop there; don't commit. The page
   is not approval to build.

## Existing plan

"Review my answers / comments", "I answered on the page", or pasted copy text: load
l2-plan-writer and follow `references/comments.md` there, rebuild, and reply in chat with
one line per change.

## Changing this plugin

Any request to change how plans are drawn, written or rendered: read
`references/editing-rules.md` first and follow it. L3 (`l3/l3-plan-render`) changes only for an
explicit "major render change".
