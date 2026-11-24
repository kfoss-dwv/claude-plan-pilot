"""Every doc under docs/ is contract format and passes render.py check (Bugbot rule 6, locally)."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "l3/l3-plan-render/scripts"))
import render  # noqa: E402


class Docs(unittest.TestCase):
    def test_every_doc_checks_clean(self):
        docs = sorted((ROOT / "docs").rglob("*.md"))
        self.assertTrue(docs)
        for p in docs:
            page = render.Page(p, p.read_text())
            render.build(page)
            self.assertEqual(page.errors, [], str(p.relative_to(ROOT)))

    def test_every_skill_has_docs(self):
        for skill in sorted(ROOT.glob("l[0-3]/l[0-3]-*/SKILL.md")):
            rel = skill.parent.relative_to(ROOT)
            for suffix in ("", "-init"):
                self.assertTrue((ROOT / "docs/levels" / rel / f"{rel.name}{suffix}.md").exists(), f"{rel}{suffix}")


if __name__ == "__main__":
    unittest.main()
