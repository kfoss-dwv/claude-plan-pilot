# claude-plan-pilot

A Claude Code plugin for implementation plans. Claude writes a short `plan.md`; a script
renders it 1:1 into one self-contained HTML page with tabs, collapsible sections, flow and
ERD diagrams, red/green code diffs, answer cards for open questions, and a comment layer
that copies `plan.md:42-47` references back into chat.

Claude spends tokens on the plan, not on markup: the markdown is typically 3–6 KB, the
page it becomes 60–120 KB.

## Levels

| level | skill (invoked as `claude-plan-pilot:<name>`) | owns | edits |
|---|---|---|---|
| L0 | `l0-plan-pilot` | routing, destination, serving, editing rules | free |
| L1 | `l1-flow-svg`, `l1-erd-svg` | diagram specs + SVG drawing | free (fork surface) |
| L2 | `l2-plan-writer` (router), `l2-simple-code-change`, `l2-large-code-write` | what a plan says, per plan type | free (fork surface); router pins `render-contract` |
| L3 | `l3-plan-render` | `CONTRACT.md` syntax, `render.py`, `serve.py`, page CSS/JS | locked: husky |

Flow and file tree: [`docs/OVERVIEW.md`](docs/OVERVIEW.md). What a `plan.md` can contain:
[`docs/COMPONENTS_AVAILABLE.md`](docs/COMPONENTS_AVAILABLE.md) (generated).

## Install

Needs Python 3.10+ (stdlib only; markdown-it-py is vendored). Node is only for the dev hook.

From a local clone (edits go live on `/reload-plugins`, no version bump):

```
git clone https://github.com/kfoss-dwv/claude-plan-pilot ~/github/claude-plan-pilot
/plugin marketplace add ~/github/claude-plan-pilot
/plugin install claude-plan-pilot@claude-plan-pilot
```

From GitHub (a versioned copy; bump `version` in `plugin.json` to ship updates):

```
/plugin marketplace add kfoss-dwv/claude-plan-pilot
/plugin install claude-plan-pilot@claude-plan-pilot
```

The install asks for `plans_root` (default `~/github/claude-plans`) and `path_template`
(default `{project}/plan-pilot/{slug}`); change them later with `/plugin configure`.

One-off session without installing: `claude --plugin-dir ~/github/claude-plan-pilot`.

## Use

Ask for a plan ("plan-pilot: plan the fix for …", or `/claude-plan-pilot:l0-plan-pilot …`).
L0 picks an adapter, Claude writes `plan.md`, `render.py` builds `index.html`, and
`serve.py` prints a `http://127.0.0.1:879x/` URL. On the page, answer questions, reply to
challenges, or select any text / click a chart node to leave a comment. Then tell Claude
"review my answers and comments": it reads `plan.state.json`, edits `plan.md`, and the
open page reloads.

```bash
R=l3/l3-plan-render/scripts
python3 $R/render.py check path/plan.md     # lint
python3 $R/render.py path/plan.md           # build index.html
python3 $R/serve.py start path/             # serve (detached); list / stop path/ / stop --all
python3 $R/serve.py start docs/             # browse these docs
```

## Editing rules

- L1 and L2: change freely. A new plan type is a new `l2/<name>/` adapter.
- L3: only for a deliberate "major render change". `.husky/pre-commit` blocks a commit that
  touches `l3/` without `l2/l2-plan-writer/`, blocks a `contract` / `render-contract`
  mismatch, and asks for a reason on your terminal (recorded as a `Render-Change:` trailer).
  Commits without a terminal (agents, CI) fail by design; `--no-verify` skips it.
- Every change to `lN/<skill>/` updates `docs/levels/lN/<skill>/<skill>.md`; `.cursor/BUGBOT.md`
  checks it on PRs.

## Develop

```bash
npm install          # husky hooks
npm test             # L3 unit + integration tests, render lock, docs
python3 tests/eval/run_eval.py --runs 3   # headless end-to-end eval (costs API tokens)
```

Fork guide: [`docs/README.md`](docs/README.md#fork).
