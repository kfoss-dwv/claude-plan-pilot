"""I1 start/list/stop with two plans · I2 state round trip · I3 rebuild on .md edit."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVE = HERE.parent / "scripts" / "serve.py"
ENV = {**os.environ, "CLAUDE_PLAN_PILOT_HOME": tempfile.mkdtemp()}


def run(*args):
    return subprocess.run([sys.executable, str(SERVE), *args], env=ENV, capture_output=True, text=True, timeout=30)


def url_of(out):
    return next(ln for ln in out.splitlines() if ln.startswith("http://"))


def get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        for n in ("simple", "large"):
            shutil.copytree(HERE / "fixtures" / n, cls.tmp / n, ignore=shutil.ignore_patterns("index.html", "*.state.json"))

    @classmethod
    def tearDownClass(cls):
        run("stop", "--all")

    def test_I1_two_plans_two_ports(self):
        a = run("start", str(self.tmp / "simple"))
        b = run("start", str(self.tmp / "large"))
        self.assertEqual((a.returncode, b.returncode), (0, 0), a.stderr + b.stderr)
        self.assertNotEqual(url_of(a.stdout), url_of(b.stdout))
        again = run("start", str(self.tmp / "simple"))
        self.assertIn("already serving", again.stdout)
        self.assertEqual(url_of(again.stdout), url_of(a.stdout))
        listed = run("list").stdout
        self.assertIn(str(self.tmp / "simple"), listed)
        self.assertIn(str(self.tmp / "large"), listed)

    def test_I2_state_round_trip(self):
        u = url_of(run("start", str(self.tmp / "simple")).stdout)
        self.assertIn("Upgrade credit fix", get(u))
        post(u + "__plan/answers/q1?page=/", {"choice": "carry", "note": "n", "source": "agent"})
        post(u + "__plan/comments/cm-x?page=/", {"md": "19-24", "text": "why?"})
        st = json.loads(get(u + "__plan/state?page=/"))
        self.assertEqual(st["answers"]["q1"]["choice"], "carry")
        self.assertEqual(st["answers"]["q1"]["source"], "page")       # the page can't claim to be an agent
        self.assertEqual(st["comments"]["cm-x"]["status"], "open")
        saved = json.loads((self.tmp / "simple" / "plan.state.json").read_text())
        self.assertEqual(saved["comments"]["cm-x"]["md"], "19-24")

    def test_I2b_rejects_cross_site_and_bad_bodies(self):
        u = url_of(run("start", str(self.tmp / "simple")).stdout)
        for headers, data, code in (({"Content-Type": "text/plain;x=application/json"}, b'{"note":"x"}', 415),
                                    ({"Content-Type": "application/json", "Origin": "https://evil.example"}, b'{"note":"x"}', 403),
                                    ({"Content-Type": "application/json"}, b"[1,2]", 400)):
            req = urllib.request.Request(u + "__plan/answers/q2?page=/", data=data, headers=headers, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req, timeout=10)
            self.assertEqual(cm.exception.code, code)

    def test_I3_rebuild_on_edit(self):
        u = url_of(run("start", str(self.tmp / "large")).stdout)
        b1 = json.loads(get(u + "__plan/state?page=/"))["build"]
        md = self.tmp / "large" / "plan.md"
        time.sleep(0.05)
        md.write_text(md.read_text().replace("Saved carts API", "Saved carts API v2"))
        os.utime(md, (time.time() + 2, time.time() + 2))
        b2 = json.loads(get(u + "__plan/state?page=/"))["build"]
        self.assertNotEqual(b1, b2)
        self.assertIn("Saved carts API v2", get(u))

    def test_I4_docs_index(self):
        docs = self.tmp / "docs"                              # a folder with several .md files, no plan.md
        (docs / "sub").mkdir(parents=True)
        shutil.copy(HERE.parent / "CONTRACT.md", docs / "CONTRACT.md")
        shutil.copy(self.tmp / "simple" / "plan.md", docs / "sub" / "plan.md")
        u = url_of(run("start", str(docs)).stdout)
        idx = get(u)
        self.assertIn("CONTRACT.md", idx)
        self.assertIn("sub/index.html", idx)
        self.assertIn("plan-render contract", get(u + "CONTRACT.html"))
        self.assertIn("Upgrade credit fix", get(u + "sub/index.html"))
        run("stop", str(docs))


if __name__ == "__main__":
    unittest.main()
