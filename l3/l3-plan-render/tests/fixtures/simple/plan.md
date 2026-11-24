---
title: Upgrade credit fix
contract: 1
type: l2-simple-code-change
eyebrow: billing-svc · BILL-1534 · 2026-11-23
h1: A promo-to-full upgrade drops the unused promo credit
summary: `Upgrade` prorates the promo credit to zero when the promo term is shorter than the billing period. Pass the full credit through instead. Decide whether leftover credit carries or refunds.
chips: billing-svc | 1 service | no migration
tabs: plan, questions
---
# Plan

## Context {#p-context}
`Upgrade` prorates the old plan's credit by days left, which is wrong for a promo plan billed up front.

> [!bug] Member reports
> 14 upgrades last week showed $0.00 credit; expected $24.50 each.

```go services/billing/upgrade.go:212 before bug
func (s *Service) Upgrade(ctx context.Context, sub Subscription, to Plan) error {
	credit := prorate(sub.Plan.Price, sub.DaysLeft(), sub.Plan.TermDays)
	return s.vendor.ChangePlan(ctx, sub.ID, to.Code, credit)
}
```

```flow
{
  "id": "upgrade",
  "title": "Upgrade",
  "caption": "Promo plans skip proration and carry the full credit.",
  "nodes": [
    { "id": "entry", "shape": "start", "name": "POST /upgrade" },
    { "id": "promo", "shape": "decision", "name": "Promo plan?", "only": "after" },
    { "id": "full", "name": "credit = full", "only": "after" },
    { "id": "prorate", "name": "prorate(credit)", "state": { "before": "bug" } },
    { "id": "change", "shape": "call", "name": "vendor.ChangePlan" },
    { "id": "done", "shape": "stop", "name": "200", "outcome": "ok" }
  ],
  "edges": [
    { "from": "entry", "to": "prorate", "only": "before" },
    { "from": "entry", "to": "promo", "only": "after" },
    { "from": "promo", "to": "full", "label": "yes", "only": "after" },
    { "from": "promo", "to": "prorate", "label": "no", "only": "after" },
    { "from": "full", "to": "change", "only": "after" },
    { "from": "prorate", "to": "change" },
    { "from": "change", "to": "done" }
  ]
}
```

## 01 Pass the full promo credit {#p-01}
Skip `prorate` for promo plans so the vendor sees the whole credit.

```files
services/billing/upgrade.go
- Branch on `sub.Plan.Promo` before `prorate`.
services/billing/upgrade_test.go
- Add a promo case: $24.50 credit survives.
```

```go services/billing/upgrade.go:212 before bug
func (s *Service) Upgrade(ctx context.Context, sub Subscription, to Plan) error {
	credit := prorate(sub.Plan.Price, sub.DaysLeft(), sub.Plan.TermDays)
	return s.vendor.ChangePlan(ctx, sub.ID, to.Code, credit)
}
```
```go services/billing/upgrade.go:212 after
func (s *Service) Upgrade(ctx context.Context, sub Subscription, to Plan) error {
	credit := sub.Plan.Price
	if !sub.Plan.Promo {
		credit = prorate(sub.Plan.Price, sub.DaysLeft(), sub.Plan.TermDays)
	}
	return s.vendor.ChangePlan(ctx, sub.ID, to.Code, credit)
}
```

```ledger Today: prorated
price | promo, paid up front | $24.50
daysLeft | 30-day term, day 31 | 0
!credit | 24.50 × 0 / 30 | $0.00
```
```ledger Proposed: full
price | promo, paid up front | $24.50
=credit | price | $24.50
```

## Verify {#p-verify}
Unit test plus one sandbox upgrade.

- [ ] `go test ./services/billing/...` passes with the new promo case.
- [ ] Sandbox: upgrade a promo account on day 31; the vendor invoice shows a $24.50 credit.

# Open questions

```question q1
title: Should leftover credit carry forward or refund?
context: Carry keeps money in-product; refund costs a payout and support time.
- carry* Carry forward — applied to the next invoice
- refund Refund — payout to the card on file
```
```question q2
title: Which ticket should the fix land under?
context: Free text.
placeholder: e.g. BILL-1534
```
