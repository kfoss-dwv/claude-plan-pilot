"""T1 golden renders · T2 data-md mapping + fidelity · T3 lint and contract cases."""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))
import render  # noqa: E402
import fidelity  # noqa: E402

FIX = HERE / "fixtures"
GOLD = HERE / "golden"


def build(text, name="plan.md"):
    d = Path(tempfile.mkdtemp())
    p = d / name
    p.write_text(text)
    page = render.Page(p, text)
    return page, render.build(page)


HEAD = "---\ntitle: T plan\ncontract: 1\n---\n"


class T1Golden(unittest.TestCase):
    def test_fixtures_match_golden(self):
        for name in ("simple", "large"):
            src = FIX / name / "plan.md"
            page = render.Page(src, src.read_text())
            out = render.build(page)
            self.assertEqual(page.errors, [], name)
            gold = GOLD / f"{name}.html"
            if os.environ.get("UPDATE_GOLDEN") or not gold.exists():
                gold.write_text(out)
            self.assertEqual(out, gold.read_text(), f"{name}: render changed; rerun with UPDATE_GOLDEN=1 if intended")


class T2Mapping(unittest.TestCase):
    def test_fixtures_have_zero_deviations(self):
        for name in ("simple", "large"):
            src = FIX / name / "plan.md"
            out = Path(tempfile.mkdtemp()) / "index.html"
            out.write_text(render.build(render.Page(src, src.read_text())))
            res = fidelity.check(src, out)
            self.assertEqual(res["deviations"], 0, res)

    def test_data_md_points_at_source_lines(self):
        text = HEAD + "# Plan\n## Context {#p-c}\nGist line.\n\nBody para.\n"
        page, out = build(text)
        self.assertIn('<p data-md="9-9">Body para.</p>', out)
        self.assertRegex(out, r'<h2 data-md="6-6">Context</h2>')
        self.assertRegex(out, r'<p class="gist" data-md="7-7">Gist line.</p>')

    def test_chart_nodes_point_at_their_id_line(self):
        text = HEAD + '# Plan\n```flow\n{\n  "id": "f",\n  "nodes": [\n    { "id": "a", "name": "A" },\n    { "id": "b", "name": "B" }\n  ],\n  "edges": [{ "from": "a", "to": "b" }]\n}\n```\n'
        page, out = build(text)
        self.assertEqual(page.errors, [])
        self.assertIn('data-node="a" data-md="10-10"', out)
        self.assertIn('data-node="b" data-md="11-11"', out)
        self.assertIn('data-md="13-13"', out)       # the edge's line

    def test_pair_marks_changed_lines(self):
        text = HEAD + "# Plan\n```go a.go:1 before bug\nx := 1\ny := 2\n```\n```go a.go:1 after\nx := 1\ny := 3\n```\n"
        page, out = build(text)
        out = out.split('<div class="page">', 1)[1].split('id="plan-js"')[0]   # skip the CSS
        self.assertEqual(out.count("ln-bug"), 1)
        self.assertEqual(out.count("ln-add"), 1)
        self.assertIn('class="ln ln-bug" data-md="8-8">y := 2', out)

    def test_before_without_bug_is_focus(self):
        page, out = build(HEAD + "# Plan\n```go a.go before\na\n```\n```go a.go after\nb\n```\n")
        self.assertIn("ln-focus", out)

    def test_html_block_is_sanitized(self):
        page, out = build(HEAD + '# Plan\n```html-block\n<div onclick="x()"><a href="javascript:alert(1)">a</a><script>bad()</script>ok</div>\n```\n')
        body = out.split('id="plan-js"')[0]
        self.assertNotIn("onclick", body)
        self.assertNotIn("javascript:", body)
        self.assertNotIn("bad()", body)
        self.assertIn("ok</div>", body)

    def test_raw_html_outside_fence_is_text(self):
        page, out = build(HEAD + "# Plan\n<b>hi</b>\n")
        self.assertIn("&lt;b&gt;hi&lt;/b&gt;", out)

    def test_tabs_order_from_front_matter(self):
        page, out = build("---\ntitle: T\ncontract: 1\ntabs: questions, plan\n---\n# Plan\nx\n# Open questions\ny\n")
        self.assertLess(out.index('id="tab-questions"'), out.index('id="tab-plan"'))


class Fuzzed(unittest.TestCase):
    """Regressions from the fuzz pass: none of these may raise, hang or escape their wrapper."""

    def test_non_string_caption_and_bad_shapes(self):
        for spec in ('{"id":"f","caption":5,"nodes":[{"id":"a","name":"A"}],"edges":[]}', '[1,2]',
                     '{"id":"f","nodes":[{"id":"a"},{"id":"a"}]}',
                     '{"id":"f","containers":[{"id":"c","row":200000}],"nodes":[{"id":"a","name":"A","container":"c"}]}'):
            build(HEAD + "# Plan\n```flow\n" + spec + "\n```\n")
        page, _ = build(HEAD + '# Plan\n```erd\n{"id":"e","tables":[{"name":"t","col":50000000,"cols":["a"]}]}\n```\n')
        self.assertTrue(page.errors)

    def test_html_block_cannot_escape_or_swallow(self):
        page, out = build(HEAD + "# Plan\n## A\ngist\n```html-block\n</div></details></section></div><textarea><iframe srcdoc=x></iframe><b>open\n```\n## B\nafter\n")
        body = out.split('<div class="page">', 1)[1].split("<script")[0]
        self.assertNotIn("<textarea", body)
        self.assertNotIn("<iframe", body)
        blk = body.split('<div class="html-block"', 1)[1].split('id="p-b"')[0]
        inner = blk.split("</div>", 1)[0]                     # up to the wrapper's own close
        self.assertNotIn("</details>", inner)                 # stray closers were dropped
        self.assertIn("</div></details></section>", blk)      # the fold still closes where it should
        page, out = build(HEAD + "# Plan\n```html-block\n<b>open\n```\n")
        self.assertIn("<b>open\n</b></div>", out)

    def test_state_json_cannot_break_out(self):
        d = Path(tempfile.mkdtemp())
        (d / "plan.md").write_text(HEAD + "# Plan\nx\n")
        (d / "plan.state.json").write_text('{"comments":{"c":{"text":"<!--<script></script>"}}}')
        out = render.build(render.Page(d / "plan.md", (d / "plan.md").read_text()))
        state = out.split('id="plan-state">', 1)[1].split("</script>", 1)[0]
        self.assertNotIn("<", state)

    def test_heading_attrs_follow_markdown_fences(self):
        page, out = build(HEAD + "# Plan\n```text\n```bash\n## inside {#zz}\n```\n## Real {#rr}\n")
        self.assertIn("## inside {#zz}", out)
        self.assertIn('id="rr"', out)

    def test_checked_items_and_trailing_question_text(self):
        page, out = build(HEAD + "# Plan\n- [x] done\n- [ ] todo\n# Open questions\n```question q1\ntitle: Pick\n- a* Alpha\ntrailing note\n```\n")
        self.assertIn('class="done"', out)
        self.assertLess(out.index('class="opts"'), out.index("trailing note"))

    def test_front_matter_placeholder_and_id_clash(self):
        self.assertTrue(build("---\ntitle: T\ncontract: 1\nsummary: TODO(plan)\n---\n# Plan\n")[0].errors)
        e = build(HEAD + "# Plan\n## A {#q1}\nx\n# Open questions\n```question q1\ntitle: T\n```\n")[0].errors
        self.assertTrue(any("already a fold or tab id" in x for x in e))


class T3Lint(unittest.TestCase):
    def errs(self, text):
        return build(text)[0].errors

    def test_requires_title_and_contract(self):
        e = self.errs("---\neyebrow: x\n---\n# Plan\n")
        self.assertTrue(any("title" in x for x in e) and any("contract" in x for x in e))

    def test_contract_mismatch(self):
        self.assertTrue(any("CONTRACT.md is contract" in x for x in self.errs("---\ntitle: T\ncontract: 99\n---\n# Plan\n")))

    def test_placeholder(self):
        self.assertTrue(any("TODO(plan)" in x for x in self.errs(HEAD + "# Plan\nTODO(plan) fill\n")))

    def test_bad_json_and_duplicate_spec_ids(self):
        e = self.errs(HEAD + '# Plan\n```flow\n{bad\n```\n```flow\n{"id":"a","nodes":[{"id":"n","name":"N"}],"edges":[]}\n```\n```flow\n{"id":"a","nodes":[{"id":"n","name":"N"}],"edges":[]}\n```\n')
        self.assertTrue(any("not valid JSON" in x for x in e))
        self.assertTrue(any("duplicate flow spec id" in x for x in e))

    def test_duplicate_qids_and_bad_options(self):
        e = self.errs(HEAD + "# Q\n```question q1\ntitle: A?\n- a* A — x\n```\n```question q1\ntitle: B?\n-\n```\n")
        self.assertTrue(any("duplicate question id q1" in x for x in e))

    def test_duplicate_fold_ids(self):
        self.assertTrue(any("duplicate id" in x for x in self.errs(HEAD + "# Plan\n## A {#p-x}\n## B {#p-x}\n")))

    def test_content_before_first_tab(self):
        self.assertTrue(any("before the first #" in x for x in self.errs(HEAD + "stray\n# Plan\n")))

    def test_tabs_mismatch(self):
        self.assertTrue(any("tabs:" in x for x in self.errs("---\ntitle: T\ncontract: 1\ntabs: plan, testing\n---\n# Plan\n")))

    def test_contract_md_is_itself_valid(self):
        p = render.SKILL / "CONTRACT.md"
        self.assertEqual(render.Page(p, p.read_text()) and self.errs(p.read_text()), [])

    def test_components_doc_is_current(self):
        self.assertTrue(render.COMPONENTS_DOC.exists(), "run render.py components --write")
        self.assertEqual(render.COMPONENTS_DOC.read_text(), render.components_md(),
                         "docs/COMPONENTS_AVAILABLE.md is stale; run render.py components --write")

    def test_every_component_is_in_contract(self):
        contract = (render.SKILL / "CONTRACT.md").read_text()
        for kind in render.FENCES:
            self.assertIn(f"`{kind}", contract, kind)


if __name__ == "__main__":
    unittest.main()
