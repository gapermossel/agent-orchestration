"""Runs the real update.sh / rollback.sh on a throwaway copy of the bot."""
import hashlib
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from tests.helpers import ROOT

IGNORE = shutil.ignore_patterns("data", ".releases", "__pycache__")


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


class UpdateRollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="upd-"))
        self.live = self.tmp / "live"
        shutil.copytree(ROOT, self.live, ignore=IGNORE)
        (self.live / "NEWFILE").unlink(missing_ok=True)  # ROOT may itself be a test release
        (self.live / "data").mkdir()
        (self.live / "data" / "keep.txt").write_text("user data")
        (self.live / "config" / "config.json").write_text('{"bot_name": "local-config"}')
        self.new = self.tmp / "new"
        shutil.copytree(ROOT, self.new, ignore=IGNORE)
        (self.new / "VERSION").write_text("9.9.9\n")
        (self.new / "NEWFILE").write_text("new")
        self.old_version = (ROOT / "VERSION").read_text().strip()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_then_rollback_dir(self):
        r = run(["./update.sh", str(self.new), "--skip-tests"], self.live)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.live / "VERSION").read_text().strip(), "9.9.9")
        self.assertTrue((self.live / "NEWFILE").exists())
        self.assertEqual((self.live / "data" / "keep.txt").read_text(), "user data")
        self.assertIn("local-config", (self.live / "config" / "config.json").read_text())
        r = run(["./rollback.sh"], self.live)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.live / "VERSION").read_text().strip(), self.old_version)
        self.assertFalse((self.live / "NEWFILE").exists())
        self.assertEqual((self.live / "data" / "keep.txt").read_text(), "user data")
        self.assertIn("local-config", (self.live / "config" / "config.json").read_text())
        hist = (self.live / ".releases" / "HISTORY").read_text()
        self.assertIn("update", hist); self.assertIn("rollback", hist)

    def test_update_from_tarball_with_checksum(self):
        tgz = self.tmp / "rel.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(self.new, arcname="rel")
        (self.tmp / "rel.tar.gz.sha256").write_text(hashlib.sha256(tgz.read_bytes()).hexdigest() + "  rel.tar.gz\n")
        r = run(["./update.sh", str(tgz), "--skip-tests"], self.live)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("sha256 OK", r.stdout)
        self.assertEqual((self.live / "VERSION").read_text().strip(), "9.9.9")

    def test_refuses_bad_sources(self):
        tgz = self.tmp / "bad.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(self.new, arcname="rel")
        (self.tmp / "bad.tar.gz.sha256").write_text("0" * 64 + "\n")
        self.assertEqual(run(["./update.sh", str(tgz), "--skip-tests"], self.live).returncode, 67)
        self.assertEqual(run(["./update.sh", "https://example.com/x.tar.gz"], self.live).returncode, 65)
        self.assertEqual(run(["./rollback.sh"], self.live).returncode, 66)  # no backup yet
        self.assertEqual((self.live / "VERSION").read_text().strip(), self.old_version)

    @unittest.skipIf(os.environ.get("BOT_TEST_NESTED"), "already inside a nested update test run")
    def test_update_with_full_new_test_suite(self):
        # Regression (found in the 2026-10-30 demo): the new release's own update
        # tests must not act on the live bot directory.
        env = dict(os.environ, BOT_TEST_NESTED="1")
        r = subprocess.run(["./update.sh", str(self.new)], cwd=self.live, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.live / "VERSION").read_text().strip(), "9.9.9")
        self.assertEqual((self.live / "data" / "keep.txt").read_text(), "user data")
        hist = (self.live / ".releases" / "HISTORY").read_text().splitlines()
        self.assertEqual(len(hist), 1, hist)

    def test_update_aborts_when_new_tests_fail(self):
        (self.new / "tests" / "test_zz_broken.py").write_text(
            "import unittest\nclass T(unittest.TestCase):\n    def test_x(self):\n        self.fail('broken')\n")
        # keep the staged suite small: drop the slow script test from the staged copy
        (self.new / "tests" / "test_update_rollback.py").unlink()
        r = run(["./update.sh", str(self.new)], self.live)
        self.assertEqual(r.returncode, 69)
        self.assertEqual((self.live / "VERSION").read_text().strip(), self.old_version)


if __name__ == "__main__":
    unittest.main()
