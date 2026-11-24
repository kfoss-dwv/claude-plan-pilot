---
title: l0-plan-pilot
contract: 1
doc: skill
skill: l0/l0-plan-pilot
status: landed
summary: Routes a planning request to an L2 adapter, writes under plans_root, builds and serves the page, and owns the editing rules.
---
## Routing {#routing .open}
Fix → simple, new code → large, anything else → the router alone.

| request | adapter |
|---|---|
| fix or change to existing code | `l2-simple-code-change` |
| new endpoint, service, job, table | `l2-large-code-write` |
| anything else | `l2-plan-writer` alone |

## Destination {#dest}
`${plans_root}/${path_template}/plan.md`, defaults `~/github/claude-plans/{project}/plan-pilot/{slug}`.

Plans that change this plugin's own skills go to `docs/levels/lN/<skill>/<skill>-update-<slug>.md` instead.

## Serve {#serve}
After `render.py` passes, `serve.py start DIR` runs directly (no subagent) and the URL goes to the user.
