---
name: l2-simple-code-change
description: claude-plan-pilot L2 adapter for a fix or logic change to existing code (one endpoint, handler or function, usually one service). Code-first plan.md with today's code and red/green before/after pairs. Picked by l0-plan-pilot; loads l2-plan-writer first.
---

# l2-simple-code-change

Load **l2-plan-writer** first (workflow, rules, CONTRACT.md). This adapter only sets the
section recipe. Start from `template.md` beside this file; front matter `type: l2-simple-code-change`.

**Pick it for:** a bug fix or behaviour change in code that exists. Not for a new
endpoint/service (l2-large-code-write).

## Section recipe (Plan tab)

1. `## Context {#p-context}`: gist = the problem in one line. Then the real code as a lone
   `before` fence (`bug` when something is wrong; without `bug` it marks the area of change),
   plus `> [!bug]` for a prod error.
2. Optional flow: only when the change alters branching. One spec; before/after via `"only"`
   and per-view `"state"` renders today and proposed as two figures. Skip it for a one-line fix.
3. `## 01 …` one fold per change, in landing order: gist (≤ 2 lines), `files`, then the
   `before` / `after` pair for the same lines (identical context lines, so only the change
   is marked). A ledger when numbers move.
4. `## Verify {#p-verify}`: `- [ ]` checks.

Tabs: `plan, questions`. Testing is off unless the user asks or the change spans services.
Keep it short: 2–4 work folds, 1–4 questions.

## Worked example

````markdown
## 01 Pass the full promo credit {#p-01}
Skip `prorate` for promo plans so the vendor sees the whole credit.
```files
services/billing/upgrade.go
- Branch on `sub.Plan.Promo` before `prorate`.
```
```go services/billing/upgrade.go:212 before bug
	credit := prorate(sub.Plan.Price, sub.DaysLeft(), sub.Plan.TermDays)
```
```go services/billing/upgrade.go:212 after
	credit := sub.Plan.Price
	if !sub.Plan.Promo {
		credit = prorate(sub.Plan.Price, sub.DaysLeft(), sub.Plan.TermDays)
	}
```
````
