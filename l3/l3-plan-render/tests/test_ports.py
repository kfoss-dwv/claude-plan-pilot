"""T4 port registry: claim, reuse, prune dead pids, release."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["CLAUDE_PLAN_PILOT_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(HERE.parent / "scripts"))
import serve  # noqa: E402


class T4Ports(unittest.TestCase):
    def setUp(self):
        serve.PORTS.unlink(missing_ok=True)

    def test_claim_then_reuse(self):
        p, fresh = serve.claim_port("/plans/a")
        self.assertTrue(fresh)
        self.assertIn(p, serve.PORT_RANGE)
        p2, fresh2 = serve.claim_port("/plans/a")
        self.assertEqual((p2, fresh2), (p, False))
        p3, fresh3 = serve.claim_port("/plans/b")
        self.assertTrue(fresh3)
        self.assertNotEqual(p3, p)

    def test_dead_pids_are_pruned(self):
        serve.HOME.mkdir(parents=True, exist_ok=True)
        serve.PORTS.write_text(json.dumps({"8790": {"pid": 999999, "plan": "/plans/dead", "started": "x"}}))
        p, fresh = serve.claim_port("/plans/dead")
        self.assertTrue(fresh)               # the dead server's entry no longer counts

    def test_release_removes_only_own_entry(self):
        p, _ = serve.claim_port("/plans/c")
        serve.release(p)
        reg = json.loads(serve.PORTS.read_text())
        self.assertNotIn(str(p), reg)


if __name__ == "__main__":
    unittest.main()
