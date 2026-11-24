---
title: l1-flow-svg
contract: 1
doc: skill
skill: l1/l1-flow-svg
status: landed
summary: Logic flowcharts from a JSON spec: shapes, change colours, containers, before/after views. In a plan, a flow fence is the embed.
---
## Spec {#spec .open}
Nodes, edges, optional containers and groups; per-view state for before/after. Full reference in the SKILL.md.

## Tags {#tags}
Every node `<g>` carries `data-node="<id>"`, every edge `data-edge="from>to"`; render.py adds `data-md` so chart clicks map to plan.md lines.
