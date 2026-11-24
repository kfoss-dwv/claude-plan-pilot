# What goes in each tab

Density: with every fold closed, a tab reads in about one screen. Gists are one or two
lines a skimmer can stop at.

## Header (front matter)
- `eyebrow`: `repo · service · TICKET · yyyy-mm-dd`.
- `h1`: the problem or goal as one sentence. `title`: 2–4 words.
- `summary`: problem, fix, and the one thing the user must decide (2–3 sentences).
- `chips`: scope facts that matter (service, account/region, phase, migration); first is highlighted.

## Plan (`# Plan`, required)
1. `## Context` fold: today's behaviour, the problem, the constraint; real code in a
   `before` fence; a prod error as `> [!bug]`.
2. The diagram (`flow` for logic, endpoints, pipelines, infra; `erd` for schema). One
   paragraph above it that reads the diagram; a `"caption"`. Before/after = one spec.
3. A ledger fold when money, rates or dates are involved.
4. Numbered work folds `## 01 …`, in landing order: a `files` fence, then the code
   (a `before`/`after` pair for a change, `pseudo-<lang>` for new logic).
5. `## Verify`: a `- [ ]` check list of what proves it works, and where.

## Open questions (`# Open questions`, required)
3–10 `question` fences ordered by how much hangs on each: `title:` is the question itself,
`context:` says why it matters and what each option costs, options carry a one-line
consequence, one marked `*` when you recommend it. No options = free text. With nothing
open, keep the tab with one line: "Nothing open."

## Testing (`# Testing`, optional)
Optional `flow` of what the tests cover (stages as containers, each test a node), then a
`## Tests` fold with a table: id · covers · call/setup · expect (ids `T1…` in run order).
End with "Not covered:" and what watches those paths instead.

## Challenging the design (`# Challenging the design`, only on request)
`challenge c1` fences, most severe first: the claim as `title:`, the argument grounded in
code or the plan, and the alternative it points to.
