# Answers, challenge replies and comments

All three live in `plan.state.json` beside `plan.md` (generally `X.state.json` beside `X.md`).
The page writes through `serve.py`; agents read and write the file directly.

```json
{"answers":    {"q1": {"choice": "carry", "note": "…", "source": "page", "agent": "", "updatedAt": "…",
                       "review": "…", "reviewedAt": "…", "applied": "…"}},
 "challenges": {"c1": {"status": "changed", "note": "…", "resolution": "…", "source": "agent", "agent": "…", "updatedAt": "…"}},
 "comments":   {"cm-1a2b": {"md": "42-47", "node": "lookup", "quote": "…", "text": "…", "status": "open",
                            "createdAt": "…", "reply": "…", "agent": "…"}}}
```

- `answers`: the page writes `choice`/`note`. You add `review` + `reviewedAt` (a concern,
  shown in violet) and `applied` (what the plan now says, shown in green). Never rewrite
  the user's `note`. Write `choice`/`note` yourself only for a decision the user made in chat
  (`source: "agent"`, `agent`, `updatedAt`).
- `challenges`: `status` is `open | discussing | accepted | changed | rejected`; you write
  `resolution` once settled.
- `comments`: `md` is the 1-based `plan.md` line range (`node` = the chart node id). To
  answer: open `plan.md` at those lines, edit the plan or not, then set `reply` (one or two
  lines: what you changed or why not), `agent`, and `status: "resolved"`.

Pasted copy text looks like `plan.md:42-47 (node lookup)` + `> quote` + the comment: handle
it the same way, and write the row only if it exists in the file.

Writing the file: re-read it right before writing, merge only your fields, keep every
other key, write it back whole (temp file + rename). The served page picks it up within
a few seconds. Then rebuild `plan.md` if you changed it (`render.py DIR/plan.md`).

A reply that argues or says "well…" is not a decision: discuss in chat and wait.
