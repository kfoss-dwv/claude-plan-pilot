---
name: l1-erd-svg
description: claude-plan-pilot L1 drawing. The JSON spec format for ERD / schema diagrams (table cards, crow's-foot cardinality, new / changed / legacy highlights) used inside ```erd fences of a plan-pilot plan.md. Load it when writing an ```erd fence, or when a plan-pilot plan adds or changes tables, columns or joins.
---

# l1-erd-svg

In a plan-pilot plan you never run this script yourself: put the spec in an
```` ```erd ```` fence in plan.md and `l3-plan-render` calls `erd.py` for you
(add a `"caption"` key for the figure caption). The CLI below is for previewing
a spec on its own.

Schema diagrams as table cards: each table is a card,
joins are right-angle lines, and every line end carries a crow's-foot marker.
You write a small JSON spec; `scripts/erd.py` does layout, routing, lane
assignment and markers. Don't hand-place SVG coordinates.

## Workflow

1. **Collect the real schema.** Read migrations / model files for the tables in
   scope. Show join keys and the columns the reader needs, not every column.
   Get cardinality from the schema: `UNIQUE` on an FK → one-to-one; nullable FK
   → `0..1` on the referenced end.
2. **Write the spec** to `$CLAUDE_JOB_DIR/tmp/<name>.json` (or scratchpad).
   Start from `examples/save-offers.json` (hub + spokes, new column/table,
   legacy dashed path, stacked vertical join) or `examples/coverage.json`
   (self-reference loop, 1:1 stacked, N:M join table, changed variant).
3. **Render + look once:**
   ```bash
   S=${CLAUDE_PLUGIN_ROOT}/l1/l1-erd-svg
   python3 $S/scripts/erd.py spec.json -o figure.html --preview preview.html
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
     --hide-scrollbars --window-size=1200,900 --screenshot=shot.png "file://$PWD/preview.html"
   ```
   Read `shot.png`. Fix jogs (stderr warns when a link jogs ≤10px — pin a
   table's `y` so the two rows line up), crossings, or crowding, then re-render.
4. **In a plan.md** the fence is the embed: `render.py` runs this script, inlines
   `assets/erd.css` once per page and tags every node with `data-node`.

The CSS reads the host page's tokens when they exist (`--surface --line --fg
--muted --code-bg --accent --accent-soft --upd --upd-soft --font-sans
--font-mono`) and falls back to the built-in light/dark palette, so it's
theme-aware either way. For an artifact, still follow `artifact-design`.

Other outputs: `--svg erd.svg` (self-contained, CSS embedded — for Confluence
uploads or attaching), `--key` (prints a legend of all five ends for a
page-level key).

## Reading the markers

Crow's-foot convention: the marker at an end says **how many rows of that
end's table match one row on the other end.** The FK side is the `from`.

| token  | marker            | meaning      |
|--------|-------------------|--------------|
| `1`    | two bars          | exactly one  |
| `0..1` | ring + bar        | zero or one  |
| `N`    | crow's foot       | many         |
| `1..N` | bar + crow's foot | one or many  |
| `0..N` | ring + crow's foot| zero or many |

`card` is `"<from end>:<to end>"`. Typical FK `campaigns.kind_id → kinds.id`
is `"0..N:1"` (a kind has zero-or-many campaigns; a campaign has exactly one
kind). Nullable FK: `"0..N:0..1"`. Unique FK (one-to-one): `"0..1:1"`. N:M is
two `0..N:1` relations from the join table. Aliases: `one many * + ?`.

## Spec reference

```jsonc
{
  "id": "save-offers",             // prefixes the svg <title>/<desc> ids; unique per page
  "title": "…", "desc": "…",       // accessible name + full-sentence description (required for a11y)
  "layout": { "hgap": 110, "vgap": 36, "valign": "center" | "top" },
  "legend": { "": "existing join", "legacy": "…", "new": "…", "changed": "…" },
  "min_width": 880,                // optional; default 80% of the viewBox width (scrolls below that)
  "tables": [{
    "id": "campaigns",             // ref key; defaults to name
    "name": "retention_offer_campaigns",
    "col": 1,                      // grid column; tables stack top→bottom in spec order
    "y": 42,                       // optional pin; following tables in the column stack below it
    "x": 400, "w": 290,            // optional; x opts out of the grid, w overrides auto width
    "variant": "anchor" | "new" | "changed" | "legacy",
    "tag": "every offer",          // right side of the header
    "cols": [
      "plain_column",
      { "name": "id", "note": "PK" },
      { "name": "endpoint_id", "note": "NEW", "state": "new" | "changed" | "muted", "key": "short_ref" }
    ]
  }],
  "relations": [{
    "from": "campaigns.campaign_kind_id",   // table.column, or just table (centre of the edge)
    "to": "kinds.id",
    "card": "0..N:1",
    "variant": "new" | "changed" | "legacy",
    "label": "redemptions",        // optional; on the longest run that fits
    "route": "auto" | "vertical" | "loop-right" | "loop-left",
    "via": 360,                    // pin the elbow x (side routes)
    "at": 0.5                      // vertical routes: where along the shared overlap (0–1)
  }],
  "notes": [ { "below": "endpoints", "text": "e.g. key = cancellation_flow" },
             { "x": 548, "y": 430, "text": "…", "anchor": "start", "variant": "new" } ]
}
```

## Layout rules of thumb

- Put the hub table (the one most FKs point at or from) in the middle column
  with `variant: "anchor"`; spokes in columns either side.
- Routing is automatic: side-by-side tables connect edge to edge with one
  elbow; tables stacked in the same column connect bottom to top (the gap
  widens automatically to fit both markers); same-table refs need
  `loop-left`/`loop-right`. Tables in non-adjacent columns route straight
  across the middle column — reorder columns instead.
- Elbow lanes in each gap are chosen to minimise crossings; links sharing an
  endpoint (e.g. two FKs to `campaigns.id`) merge into one trunk.
- To get a straight line, pin one table's `y` so the rows match: row centre =
  `y + 41 + 22 × row_index`.
- Use `new` (accent red) for what the doc adds, `changed` (blue) for what it
  modifies, `legacy` (dashed, muted) for paths being phased out. Keep it to
  what the doc is about — one highlighted story per diagram.
