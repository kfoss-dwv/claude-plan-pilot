---
title: Saved carts API
contract: 1
type: l2-large-code-write
eyebrow: shop-api · SHOP-88 · 2026-11-24
h1: Add a saved-carts endpoint so shoppers can park a cart and restore it on any device
summary: New `POST /carts/{id}/save` and `GET /saved-carts` on shop-api, backed by a new `saved_carts` table. Prices re-check on restore. Decide how long saved carts live.
chips: shop-api | new endpoint | 1 table | migration
tabs: plan, questions, testing, challenges
---
# Plan

## Context {#p-context}
Carts live in Redis for 24 hours and are tied to one session, so a shopper who switches devices starts over.

```go services/shop/cart/store.go:40
func (s *Store) Put(ctx context.Context, c Cart) error {
	return s.redis.Set(ctx, "cart:"+c.SessionID, c.JSON(), 24*time.Hour).Err()
}
```

## Flow {#p-flow .open}
Save copies the Redis cart into Postgres under the account; restore re-prices each line before it becomes the live cart.

```flow
{
  "id": "saved-carts",
  "title": "Saved carts",
  "caption": "Everything blue is new. Restore re-prices before writing the live cart.",
  "containers": [
    { "id": "web", "label": "Web", "kind": "client", "row": 0, "col": 0 },
    { "id": "api", "label": "shop-api", "kind": "service", "row": 0, "col": 1, "tag": "Go · ECS" },
    { "id": "pricing", "label": "Pricing", "kind": "vendor", "row": 0, "col": 2 }
  ],
  "nodes": [
    { "id": "click", "container": "web", "shape": "start", "name": "Save cart" },
    { "id": "save", "container": "api", "shape": "start", "name": "POST /carts/{id}/save", "state": "new" },
    { "id": "owned", "container": "api", "shape": "decision", "name": "Cart owned?", "state": "new" },
    { "id": "e403", "container": "api", "shape": "stop", "name": "403", "state": "new" },
    { "id": "insert", "container": "api", "shape": "store", "name": "Postgres", "sub": "saved_carts", "state": "new" },
    { "id": "restore", "container": "api", "shape": "action", "name": "restore()", "sub": "re-price lines", "state": "new" },
    { "id": "quote", "container": "pricing", "shape": "action", "name": "/quote" },
    { "id": "ok", "container": "api", "shape": "stop", "name": "201", "outcome": "ok" }
  ],
  "edges": [
    { "from": "click", "to": "save", "label": "HTTPS" },
    { "from": "save", "to": "owned" },
    { "from": "owned", "to": "insert", "label": "yes" },
    { "from": "owned", "to": "e403", "label": "no" },
    { "from": "insert", "to": "restore" },
    { "from": "restore", "to": "quote", "label": "lines" },
    { "from": "quote", "to": "ok", "label": "prices" }
  ]
}
```

## Schema {#p-schema}
One new table, one row per saved cart, lines as JSON.

```erd
{
  "id": "saved-carts-erd",
  "title": "Saved carts schema",
  "desc": "saved_carts belongs to accounts; many saved carts per account.",
  "tables": [
    { "name": "accounts", "col": 0, "variant": "anchor", "cols": [{ "name": "id", "note": "PK" }, "email"] },
    { "name": "saved_carts", "col": 1, "variant": "new", "tag": "NEW",
      "cols": [{ "name": "id", "note": "PK" }, { "name": "account_id", "note": "FK" }, { "name": "lines", "note": "jsonb" }, { "name": "expires_at", "note": "Q1" }] }
  ],
  "relations": [{ "from": "saved_carts.account_id", "to": "accounts.id", "card": "0..N:1", "variant": "new" }]
}
```

## 01 Migration {#p-01}
Create `saved_carts` with an index on `account_id`.

```files
migrations/0042_saved_carts.sql
- `CREATE TABLE saved_carts (...)` + index on `account_id`.
```

```sql migrations/0042_saved_carts.sql
CREATE TABLE saved_carts (
  id uuid PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id),
  lines jsonb NOT NULL,
  expires_at timestamptz NOT NULL
);
CREATE INDEX saved_carts_account ON saved_carts (account_id);
```

## 02 Save + restore handlers {#p-02}
Two handlers; restore re-prices through the pricing service and drops lines that no longer exist.

```files
services/shop/cart/saved.go
- `Save(ctx, cartID)`: ownership check, insert row.
- `Restore(ctx, savedID)`: re-price, write the live cart.
```

```pseudo-go services/shop/cart/saved.go
func Restore(ctx, savedID) (Cart, error) {
	saved := db.Get(savedID)            // 404 when missing or expired
	quotes := pricing.Quote(saved.Lines)
	lines := keep(saved.Lines, quotes)  // drop discontinued SKUs, take new prices
	return store.Put(Cart{Lines: lines})
}
```

> [!note] Price drift
> Restored carts always show today's price; the saved price is never honoured.

## Verify {#p-verify}
Integration tests plus a manual cross-device check.

- [ ] Integration suite T1–T3 green.
- [ ] Save on desktop, restore on phone.

# Open questions

```question q1
title: How long should a saved cart live?
context: Longer helps returning shoppers; shorter keeps the table small and prices fresher.
- d30* 30 days — matches the wishlist
- d90 90 days — fewer lost carts, bigger table
```

# Testing

## Tests {#t-cases}
Three integration cases against a local Postgres and a mocked pricing service.

| Test | Covers | Call | Expect |
|---|---|---|---|
| T1 | save own cart | `POST /carts/c1/save` | 201, one row |
| T2 | save someone else's cart | `POST /carts/c2/save` | 403 |
| T3 | restore with a dropped SKU | `GET /saved-carts/s1/restore` | 200, line removed |

# Challenging the design

```challenge c1
title: Storing lines as JSON blocks reporting on saved carts
Analytics will want per-SKU counts; `jsonb` makes that a scan. A `saved_cart_lines` table costs one more join but keeps SKUs queryable.
```
