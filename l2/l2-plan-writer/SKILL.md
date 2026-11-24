---
name: l2-plan-writer
description: claude-plan-pilot L2 router. Shared rules for writing a plan-pilot plan.md (the only file Claude writes; l3-plan-render turns it into HTML). Loaded first by every L2 adapter (l2-simple-code-change, l2-large-code-write) and used alone for plans that fit neither. Also covers answering questions, challenges and page comments on an existing plan.
---

# l2-plan-writer

render-contract: 1

You write one file, `plan.md`, in the contract-1 syntax of l3-plan-render:
`${CLAUDE_PLUGIN_ROOT}/l3/l3-plan-render/CONTRACT.md` (read it once per session; it is short).
Never write HTML, never preview figures on their own; `render.py` draws and checks them.

## Workflow

1. **Survey.** Read the real code, schema and infra the plan touches. Quote code from the
   file with its `path:line`; never paraphrase code from memory.
2. **Write `plan.md`** at the path l0-plan-pilot gave you, following the adapter's section
   recipe and `references/sections.md`. Front matter: `title`, `contract: 1`, `type`
   (the adapter), `eyebrow`, `h1`, `summary`, `chips`, `tabs`.
3. **Check:** `python3 ${CLAUDE_PLUGIN_ROOT}/l3/l3-plan-render/scripts/render.py check DIR/plan.md`.
   Fix every ERROR (they carry line numbers); fix flow warnings about edges through nodes.
4. **Build:** `python3 ${CLAUDE_PLUGIN_ROOT}/l3/l3-plan-render/scripts/render.py DIR/plan.md`.
5. **Hand back** to l0-plan-pilot, which serves the page. This router never serves.

## Rules that matter most

- **About a screen with folds closed.** Every H2 is a fold; its first paragraph is the
  gist (one or two lines). One line per change inside a fold, no essays.
- **Context first.** The first fold is today's behaviour, the problem, the constraint, with
  the real code (a `before` fence, `bug` when it is wrong).
- **Math as named steps** in `ledger` fences, one operation per row, worked values.
- **One colour meaning per page:** red = where the bug fires, blue = new, dashed blue =
  changed, amber = silent bad path, violet = what the user asked about, green = success.
- **Questions** only for what the user must decide: a recommended option (`*`) when you
  have one, context, and the cost of each choice. Ids `q1, q2 …` never change.
- Spend tokens on content, not syntax: the renderer does layout, line marking and colour.

## Existing plans

Read `references/comments.md` before touching `plan.state.json` (answers, challenge
replies, page comments). Edit `plan.md`, then rerun step 3–4; an open served page reloads.

The page is not approval to build. Never implement until the user says go.
