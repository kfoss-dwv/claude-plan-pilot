"""T5 husky render lock: block L3 alone, block contract drift, prompt when both change."""
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "scripts" / "render_lock.py"


class T5RenderLock(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        (self.d / "scripts").mkdir()
        shutil.copy(LOCK, self.d / "scripts")
        self.write("l3/l3-plan-render/CONTRACT.md", "---\ncontract: 1\n---\n")
        self.write("l2/l2-plan-writer/SKILL.md", "render-contract: 1\n")
        self.write("l1/x.md", "a\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.d, capture_output=True, text=True, check=True)

    def write(self, rel, text):
        p = self.d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def lock(self, stdin=None, tty=False):
        cmd = [sys.executable, "scripts/render_lock.py"]
        if not tty:  # no controlling terminal, the way an agent commits
            return subprocess.run(cmd, cwd=self.d, capture_output=True, text=True, stdin=subprocess.DEVNULL, start_new_session=True)
        # a real pseudo-terminal, the way a person commits; type the answer once the prompt is up
        typed = f"(sleep 1; printf {shlex.quote(stdin)}) | script -q /dev/null {shlex.join(cmd)}"
        return subprocess.run(["sh", "-c", typed], cwd=self.d, capture_output=True, text=True)

    def test_no_l3_passes(self):
        self.write("l1/x.md", "b\n")
        self.git("add", "-A")
        self.assertEqual(self.lock().returncode, 0)

    def test_l3_alone_is_blocked(self):
        self.write("l3/l3-plan-render/scripts/render.py", "x\n")
        self.git("add", "-A")
        r = self.lock()
        self.assertEqual(r.returncode, 1)
        self.assertIn("without l2-plan-writer", r.stderr)

    def test_contract_drift_is_blocked(self):
        self.write("l3/l3-plan-render/CONTRACT.md", "---\ncontract: 2\n---\n")
        self.write("l2/l2-plan-writer/SKILL.md", "render-contract: 1\nnew rule\n")
        self.git("add", "-A")
        r = self.lock()
        self.assertEqual(r.returncode, 1)
        self.assertIn("render-contract 1", r.stderr)

    def test_both_without_terminal_fails(self):
        self.write("l3/l3-plan-render/scripts/render.py", "x\n")
        self.write("l2/l2-plan-writer/SKILL.md", "render-contract: 1\nnew rule\n")
        self.git("add", "-A")
        r = self.lock()
        self.assertEqual(r.returncode, 1)
        self.assertIn("own terminal", r.stderr)

    @unittest.skipUnless(shutil.which("script") and sys.platform == "darwin", "needs BSD script(1) for a pty")
    def test_both_with_terminal_records_reason(self):
        self.write("l3/l3-plan-render/scripts/render.py", "x\n")
        self.write("l2/l2-plan-writer/SKILL.md", "render-contract: 1\nnew rule\n")
        self.git("add", "-A")
        r = self.lock(stdin="new pair layout\n", tty=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.d / ".git" / "RENDER_CHANGE").read_text().strip(), "new pair layout")

    @unittest.skipUnless(shutil.which("script") and sys.platform == "darwin", "needs BSD script(1) for a pty")
    def test_empty_reason_aborts(self):
        self.write("l3/l3-plan-render/scripts/render.py", "x\n")
        self.write("l2/l2-plan-writer/SKILL.md", "render-contract: 1\nnew rule\n")
        self.git("add", "-A")
        r = self.lock(stdin="\n", tty=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
