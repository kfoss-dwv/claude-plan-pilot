---
title: l1-flow-svg init
contract: 1
doc: init
skill: l1/l1-flow-svg
status: landed
summary: How l1-flow-svg was first built, from the plan-pilot plan (2026-11-23). A record: never edited after landing.
---
## 02 Copy + tag nodes {#p-02 .open}
Copied from the standalone flow-svg skill (which stays installed for html-plan) and renamed.

- `node_svg`: `data-node="{id}"` on the node group. Edge paths get `data-edge="from>to"`.
- Examples scrubbed of employer-specific names for the public repo.
