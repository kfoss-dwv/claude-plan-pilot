---
name: l3-plan-render
description: claude-plan-pilot L3 render. Turns a contract-format plan.md into its self-contained HTML page (render.py) and serves it with live answers and comments (serve.py). Loaded by l2-plan-writer for the syntax (CONTRACT.md) and by l0-plan-pilot to build and serve; not something to write HTML with. Locked behind the husky render lock.
---

# l3-plan-render

Syntax: `CONTRACT.md` beside this file (contract 1). It is the only syntax reference;
write nothing it doesn't list.

```bash
R=${CLAUDE_PLUGIN_ROOT}/l3/l3-plan-render/scripts
python3 $R/render.py check DIR/plan.md      # lint: exit 1 on any ERROR (line-numbered)
python3 $R/render.py DIR/plan.md            # check + write DIR/index.html (X.md -> X.html)
python3 $R/serve.py start DIR               # detached; prints the URL, reuses a live server for DIR
python3 $R/serve.py list | stop DIR | stop --all
python3 $R/render.py components             # the component table (docs/COMPONENTS_AVAILABLE.md)
```

- Never edit the `.html`; it is regenerated from the `.md`. serve.py rebuilds on request
  when the `.md` is newer, and an open page reloads itself.
- State lives in `plan.state.json` beside `plan.md` (answers, challenges, comments); row
  formats are in l2-plan-writer `references/comments.md`.
- Ports 8790–8839, registry `~/.claude-plan-pilot/ports.json`.
- Changing anything here is a "major render change": see l0-plan-pilot
  `references/editing-rules.md`. Bump `contract:` in CONTRACT.md for any change that makes
  an existing `.md` render differently.
