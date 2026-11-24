---
title: plan-render contract
contract: 1
doc: skill
skill: l3/l3-plan-render
summary: The markdown syntax l3-plan-render turns into HTML, 1:1. Writers (l2) only ever produce this.
chips: contract 1 | l3 | locked
---
# Contract

## Rules {#rules .open}
One `.md` file in, one self-contained `.html` out (`plan.md` → `index.html`, `X.md` → `X.html`). Every block maps to one HTML block tagged with its source lines.

- No raw HTML outside an `html-block` fence (markdown-it runs with HTML off, so it would show as text).
- Write each thing once. The page is generated; never edit the `.html`.
- `TODO(plan)` anywhere fails `render.py check`.
- Bump `contract:` here (and `render-contract:` in l2-plan-writer) for any change that makes an old `.md` render differently.

## Front matter {#front-matter}
Plain `key: value` lines between `---` lines. A trailing ` # comment` is dropped.

| key | required | meaning |
|---|---|---|
| `title` | yes | 2–4 word name: browser tab and gallery |
| `contract` | yes | this file's version, `1` |
| `type` | no | adapter that wrote it, e.g. `l2-simple-code-change` |
| `eyebrow` | no | `repo · ticket · yyyy-mm-dd` |
| `h1` | no | the one-sentence problem; defaults to `title` |
| `summary` | no | 2–3 sentences, inline markdown OK |
| `chips` | no | `a \| b \| c`, the first one highlighted |
| `tabs` | no | panel order by id: `plan, questions, testing` |
| `doc` `skill` `status` | no | docs only: `overview \| components \| skill \| init \| update`, `l3/l3-plan-render`, `planned \| in-progress \| landed` |

## Structure {#structure}
H1 = tab, H2 = fold. Everything else is a block inside a fold, or the tab's intro when it sits above the first H2.

```text
# Plan                      tab id plan        (also: # Open questions -> questions, # Testing -> testing,
# Open questions            tab id questions    # Challenging the design -> challenges; anything else -> slug)
## Context {#p-context}     fold; id optional (default p-<slug>, or p-03 for "## 03 Title")
First paragraph = the gist shown while the fold is closed (one or two lines).
## 03 Title {.open}         a leading 2-digit number becomes the fold number; .open starts expanded
```

No H1 at all = one untabbed page (docs). With H1s, nothing may sit above the first one.

## Fences {#fences}
The fence's first info word picks the component.

| info string | body |
|---|---|
| `go path/x.go:212` | real code; the path:line renders as a locator |
| `go path/x.go:212 before [bug]` then `go path/x.go:212 after` | adjacent pair; changed lines auto-marked (after green; before red with `bug`, else violet). Lone `before` = today's code, unmarked |
| `pseudo-go [path]` | pseudo-code in that language, tagged pseudo |
| `flow` / `erd` | the l1-flow-svg / l1-erd-svg JSON spec; `"id"` required and unique; optional `"caption"` |
| `question q4` | `title:` line, `context:` line, then `- value* Label — consequence` lines (`*` = recommended; no options = free text; `placeholder:` optional) |
| `challenge c1` | `title:` (the claim), then the argument as markdown |
| `files` | a path line, then `- change` lines; repeat |
| `ledger Today: prorated` | `name \| formula \| value` rows; `!` prefix = total/bug (red), `=` = total/ok (green) |
| `html-block` | raw HTML for a one-off visual; `<script>`, `on*` and `javascript:` are stripped |
| anything else | plain code block (`html`, `json`, `text` …) |

Consecutive `question`, `challenge` or `ledger` fences group into one card list / ledger row.

## Inline blocks {#inline}
- `> [!bug] Title` (also `[!ok]`, `[!note]`, `[!warn]`): callout; the rest of the quote is its body.
- `- [ ] item` lists: check list.
- GFM tables, lists, `code`, **bold**, links: as markdown.

## Example {#example}
````markdown
---
title: Upgrade credit fix
contract: 1
type: l2-simple-code-change
eyebrow: billing · TICKET-12 · 2026-11-23
summary: Promo→parent upgrade strands $24.50 of credit.
chips: billing-svc | 1 service | no migration
tabs: plan, questions
---
# Plan
## Context {#p-context}
`Upgrade` prorates the promo credit away.
```go services/sub/upgrade.go:212 before bug
credit := prorate(old, now)
```
## 01 Keep the credit {#p-01}
Pass the full credit through.
```go services/sub/upgrade.go:212 before bug
credit := prorate(old, now)
```
```go services/sub/upgrade.go:212 after
credit := old.Credit
```
# Open questions
```question q1
title: Refund or carry the credit?
context: Carry keeps it in-product; refund costs a payout.
- carry* Carry forward — applied to the next invoice
- refund Refund — payout today
```
````

## State {#state}
`X.state.json` beside the `.md` (`plan.md` → `plan.state.json`), written by `serve.py` and by agents: `answers.{qid}`, `challenges.{cid}`, `comments.{id}`. Row formats: l2-plan-writer `references/comments.md`.
