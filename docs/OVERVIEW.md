---
title: plan-pilot overview
contract: 1
doc: overview
summary: Four levels. L0 routes, L2 writes plan.md, L3 renders and serves it, L1 draws the figures. Claude only ever writes markdown.
chips: 7 skills | 4 levels | stdlib python
---
# Flow

## Level and script flow {#levels .open}
L0 picks an adapter, L2 writes `plan.md`, L3 renders and serves it, L1 draws the figures.

`l0-plan-pilot` picks an adapter by plan type; the adapter adds its section recipe and `l2-plan-writer` the shared rules. Together they write `plan.md` and nothing else. `render.py` converts it 1:1, calling the l1 scripts for figure fences; `serve.py` claims a port and collects answers and comments into `plan.state.json`.

```flow
{
  "id": "levels",
  "title": "claude-plan-pilot levels",
  "caption": "Claude writes only plan.md; the HTML is generated output.",
  "containers": [
    { "id": "l0", "label": "L0 · orchestrate", "kind": "stage", "row": 0, "col": 0 },
    { "id": "l2", "label": "L2 · write", "kind": "stage", "row": 0, "col": 1 },
    { "id": "l3", "label": "L3 · render (locked)", "kind": "stage", "row": 0, "col": 2 },
    { "id": "l1", "label": "L1 · draw", "kind": "stage", "row": 0, "col": 3 }
  ],
  "nodes": [
    { "id": "ask", "container": "l0", "shape": "start", "name": "plan this" },
    { "id": "route", "container": "l0", "shape": "decision", "name": "Plan type?" },
    { "id": "adapter", "container": "l2", "name": "adapter recipe", "sub": "simple / large" },
    { "id": "router", "container": "l2", "name": "l2-plan-writer", "sub": "shared rules" },
    { "id": "md", "container": "l2", "shape": "store", "name": "plan.md" },
    { "id": "render", "container": "l3", "name": "render.py", "sub": "check + build" },
    { "id": "srv", "container": "l3", "shape": "call", "name": "serve.py start" },
    { "id": "state", "container": "l3", "shape": "store", "name": "plan.state.json" },
    { "id": "serve", "container": "l3", "shape": "stop", "name": "URL to the user", "outcome": "ok" },
    { "id": "flowpy", "container": "l1", "name": "flow.py / erd.py", "sub": "SVG + data-node" }
  ],
  "edges": [
    { "from": "ask", "to": "route" },
    { "from": "route", "to": "adapter" },
    { "from": "adapter", "to": "router" },
    { "from": "router", "to": "md" },
    { "from": "md", "to": "render" },
    { "from": "render", "to": "flowpy", "label": "flow / erd fences" },
    { "from": "render", "to": "srv" },
    { "from": "srv", "to": "state", "label": "answers · comments" },
    { "from": "srv", "to": "serve" }
  ]
}
```

# Files

## Repo layout {#tree .open}
Each level is a folder; each skill folder carries its level prefix, because the folder name is the skill name.

```text
claude-plan-pilot/
├── README.md                       level map, install, editing rules, fork guide
├── .claude-plugin/
│   ├── plugin.json                 name, version, skills paths, userConfig
│   └── marketplace.json            the repo is its own marketplace
├── package.json  .husky/           husky: pre-commit render lock, commit-msg trailer
├── scripts/render_lock.py          any change under l3/ needs l2/l2-plan-writer + a reason on the tty
├── tests/test_render_lock.py       T5
├── tests/eval/                     the fixed eval prompt + runner + aggregate
├── .cursor/BUGBOT.md               docs must change with the code
├── docs/                           this folder (contract md)
├── l0/l0-plan-pilot/               SKILL.md, references/editing-rules.md
├── l1/l1-flow-svg/  l1/l1-erd-svg/ SKILL.md, scripts/, assets/, examples/
├── l2/l2-plan-writer/              SKILL.md (render-contract: 1), references/{sections,comments}.md
├── l2/l2-simple-code-change/       SKILL.md, template.md
├── l2/l2-large-code-write/         SKILL.md, template.md
└── l3/l3-plan-render/              SKILL.md, CONTRACT.md, scripts/{render,serve}.py + _vendor/,
                                    assets/plan.{css,js}, tests/ (fixtures, golden, T1-T4, I1-I4, fidelity.py)
```

## Outside the repo {#outside}
Runtime state lives outside the plugin, because an installed copy is replaced on update.

```text
~/.claude/settings.json             pluginConfigs: plans_root, path_template
~/.claude-plan-pilot/ports.json     live servers: port -> pid, plan
${plans_root}/<project>/plan-pilot/<slug>/
    plan.md  index.html  plan.state.json
```
