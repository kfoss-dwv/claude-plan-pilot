---
name: l2-large-code-write
description: claude-plan-pilot L2 adapter for greenfield work (a new endpoint, service, job, pipeline or table). Flow-first plan.md with the chart at the centre, pseudo-code for logic that doesn't fit a box, an ERD when tables are added, and a Testing tab. Picked by l0-plan-pilot; loads l2-plan-writer first.
---

# l2-large-code-write

Load **l2-plan-writer** first (workflow, rules, CONTRACT.md). This adapter only sets the
section recipe. Start from `template.md` beside this file; front matter `type: l2-large-code-write`.

**Pick it for:** new code or a new system. Not for a fix to existing code (l2-simple-code-change).

## Section recipe (Plan tab)

1. `## Context {#p-context}`: what exists today and why it isn't enough; the real code the
   new work plugs into, with its locator.
2. `## Flow {#p-flow .open}`: the centre of the tab. One paragraph that reads the chart,
   then a `flow` spec (containers for services / vendors / clients; new parts `"state": "new"`;
   load **l1-flow-svg** for the spec format). Text elsewhere only covers what didn't fit in
   the boxes.
3. `## Schema {#p-schema}` with an `erd` spec when the work adds or changes a table
   (load **l1-erd-svg**).
4. `## 01 …` work folds in landing order: gist, `files`, then `pseudo-<lang>` fences: the
   real language cut down to the lines that carry the decision (no imports, logging or
   error plumbing unless that is the point). Real code only where it already exists.
5. `## Verify {#p-verify}`: `- [ ]` checks.

Tabs: `plan, questions, testing`. Testing is on by default: a `## Tests` fold with the
T1… table. Add `challenges` only when the user asks.

## Worked example

````markdown
## 02 Restore handler {#p-02}
Re-price every line before it becomes the live cart.
```files
services/shop/cart/saved.go
- `Restore(ctx, savedID)`: re-price, drop missing SKUs, write the live cart.
```
```pseudo-go services/shop/cart/saved.go
func Restore(ctx, savedID) (Cart, error) {
	saved := db.Get(savedID)            // 404 when missing or expired
	quotes := pricing.Quote(saved.Lines)
	return store.Put(Cart{Lines: keep(saved.Lines, quotes)})
}
```
````
