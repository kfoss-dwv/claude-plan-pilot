---
name: l1-flow-svg
description: claude-plan-pilot L1 drawing. The JSON spec format for logic flowcharts (shapes, change colours, containers, before/after views) used inside ```flow fences of a plan-pilot plan.md. Load it when writing a ```flow fence, or when the user asks to draw an endpoint, handler, state machine, pipeline or inter-service flow for a plan-pilot plan. Not for schema (use l1-erd-svg).
---

# l1-flow-svg

In a plan-pilot plan you never run this script yourself: put the spec in a
```` ```flow ```` fence in plan.md and `l3-plan-render` calls `flow.py` for you
(add a `"caption"` key for the figure caption). The CLI below is for previewing
a spec on its own.

Logic flowcharts for change design. You write a small JSON spec; `scripts/flow.py`
ranks the steps, places them, routes the edges, colours the change, and prints
a legend. Don't hand-place SVG coordinates.

**Schema, tables, columns, foreign keys, ERDs → stop and use `l1-erd-svg` instead.**
This skill draws behaviour (what the code does), not data shape.

## Workflow

1. **Read the real code first.** Trace the handler / state machine / pipeline
   you're drawing. Every node is a real step (function, call, guard, return);
   name it by its code identifier and put the plain-language meaning in `sub`.
   Don't invent steps, error names or status codes.
2. **Write the spec** to `$CLAUDE_JOB_DIR/tmp/<name>.json` (or scratchpad).
   Start from `examples/upgrade-proration.json` (one service, guards with side
   exits, bug path, proposed branch + merge, skip edge, focus) or
   `examples/social-login.json` (two stacked clients → one tall service column
   → external vendor and back, before/after).
3. **Render + look once:**
   ```bash
   S=${CLAUDE_PLUGIN_ROOT}/l1/l1-flow-svg
   python3 $S/scripts/flow.py spec.json -o figure.html --preview preview.html
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new \
     --hide-scrollbars --window-size=1300,1600 --screenshot=shot.png "file://$PWD/preview.html"
   ```
   Read `shot.png`. stderr warns when an edge runs through a node — reorder the
   edges (first-listed branch keeps the spine) or move the node, then re-render.
4. **In a plan.md** the fence is the embed: `render.py` runs this script, inlines
   `assets/flow.css` once per page and tags every node with `data-node`.

Other outputs: `--svg flow.svg` (self-contained, CSS embedded; one file per view
as `flow-before.svg` / `flow-after.svg`), `--view before|after|diff|both`,
`--key` (a legend of every shape and state for a page-level key).

## Shapes

| `shape`    | drawn as                | use for |
|------------|-------------------------|---------|
| `start`    | stadium                 | entry: endpoint hit, event received, job fires |
| `action`   | box (default)           | a step the code does |
| `decision` | diamond                 | an `if` / switch / guard — keep the name a short question |
| `call`     | box with side bars      | a call into another component (service, vendor, queue) |
| `state`    | rounded box             | a state in a state machine |
| `stop`     | hexagon                 | return, error, terminal — add `"outcome": "ok"` for success (green) |
| `store`    | cylinder                | a data store (DynamoDB table, RDS, S3 bucket) — name the service, put the table in `sub` |

## Colour = meaning

`state` on a node, edge or container. Bugs are always red and nothing else is red.

| `state`   | look                         | meaning |
|-----------|------------------------------|---------|
| `bug`     | red fill / red line          | where the bug fires and the path it takes |
| `new`     | blue fill / blue line        | proposed addition |
| `changed` | dashed blue outline / line   | existing step whose behaviour changes |
| `removed` | grey dashed, struck through  | goes away (shown in the diff view) |
| `focus`   | violet halo                  | the part the user asked about |
| `warn`    | amber dashed                 | a silent bad path (succeeds but is wrong) |

Keep it to the story the doc is telling: one bug path, the change, one focus.

## Before / after

One spec, two figures by default (today, then proposed):

- `"only": "before"` / `"only": "after"` on a node, edge or container keeps it
  to one view. An after-only item is drawn `new` automatically; in the diff
  view a before-only item is drawn `removed`.
- `state`, `label` and `sub` can differ per view:
  `"state": {"before": "bug", "after": "changed"}`.
- `--view diff` overlays both into one figure; use it only when the user asks for a
  single merged picture.

## Spec reference

```jsonc
{
  "id": "upgrade",                       // prefixes svg ids; unique per page
  "title": "…",                          // accessible name (view label appended)
  "desc": "…" | {"before": "…", "after": "…"},   // full-sentence description per view
  "views": {"before": "Today", "after": "Proposed"},   // figure captions
  "legend": {"focus": "the reset the user asked about"},    // override legend wording
  "layout": { "hgap": 96, "vgap": 64, "valign": "center" | "top", "uniform": true },
  "containers": [{                       // omit entirely for a single-component flow
    "id": "identity", "label": "Identity service",
    "kind": "service" | "vendor" | "client" | "stage",   // vendor = dashed, tagged "external"
    "row": 0, "col": 1, "rowspan": 2, "colspan": 1,       // grid placement; spans fill the cells
    "tag": "Go · ECS", "state": "new", "only": "after"
  }],
  "groups": [{                           // a runtime unit inside one container, boxed around its steps
    "id": "api_fn", "label": "email-verification-api", "tag": "AWS LAMBDA",
    "nodes": ["route", "status", "send"], "state": "new", "only": "after"
  }],
  "nodes": [{
    "id": "lookup", "container": "identity",
    "shape": "decision", "name": "Email on file?", "sub": "by normalized email" | ["line 1", "line 2"],
    "state": "bug" | {"before": "bug", "after": "changed"},
    "outcome": "ok", "only": "after"
  }],
  "edges": [{
    "from": "lookup", "to": "create", "label": "no",
    "state": "bug", "only": "before",
    "exit": "down" | "right",           // override the side-exit rule (below)
    "enter": "left" | "right",          // drop from the source, then into the target's side,
                                         // so it doesn't share a lane with other edges into it
    "back": true                         // force a loop-back (retry) edge
  }]
}
```

## How the layout reads

- **Spine:** inside a container, steps rank top to bottom by longest path. Each
  step sits under its leftmost predecessor, so the first-listed outgoing edge
  of a fork is the straight spine and later branches step right. **List the
  happy path first.**
- **Side exits:** a guard's branch that ends at once (a `stop` with one way in)
  sits beside the guard on the same row, like `no → ErrPlanNotHigher`.
  `"exit": "down"` turns that off for one edge.
- **Skips and loops** (a branch that jumps several steps, a retry back up) run
  down a gutter on the container's left with the label set along the line.
- **Containers** sit on a row/col grid; `rowspan`/`colspan` make one component
  span others (e.g. two upstream clients stacked in col 0, the service they
  both call in col 1 with `rowspan: 2`, a vendor in col 2). A hand-off leaves
  the source through the side facing the target container, turns once in the
  gap, and enters the target from the facing side; hand-offs into the same
  step merge into one trunk. A step that calls out and gets a reply back (call
  → Auth0 → next step) keeps its order inside the container.
- **Groups** (architecture views): a box inside a container around the steps
  one runtime unit runs — a Lambda, an ECS task — with its name top-left and
  `tag` (e.g. `AWS LAMBDA`) top-right. Arrows from outside stop at the box's
  top border (they invoke the function, not a step), so the first step inside
  needs no arrow of its own. Two groups that share a rank are pushed apart.
  For an architecture figure, name nodes by the AWS service (`AWS API Gateway`,
  `Amazon DynamoDB`, `Amazon SQS`) with the resource name in `sub`.
- Containers in non-adjacent columns route straight across whatever sits
  between them — reorder columns instead. Vertical hand-offs (container below)
  leave from the step's bottom, so put that step last in its container.
