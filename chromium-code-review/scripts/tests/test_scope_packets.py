#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
PACKETS = SCRIPTS / "build-scope-packets.py"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin"})
    return result.stdout.strip()


class ScopePacketTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="scope-packets-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        source = self.repo / "net" / "buffer.cc"
        source.parent.mkdir(parents=True)
        base = [f"line {n}" for n in range(1, 61)]
        source.write_text("\n".join(base) + "\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.parent = git(self.repo, "rev-parse", "HEAD")
        changed = list(base)
        changed[4] = "changed early"        # line 5
        changed[49] = "changed late"        # line 50
        source.write_text("\n".join(changed) + "\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "change")
        self.revision = git(self.repo, "rev-parse", "HEAD")
        self.review = root / "review"
        (self.review / "packets").mkdir(parents=True)

    def write_spec(self, rows: str) -> None:
        (self.review / "packets" / "EPW.spec.tsv").write_text(
            "kind\tpath\told_range\tnew_range\tnote\n" + rows,
            encoding="utf-8")

    def run_packets(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PACKETS), str(self.review), "EPW",
             "--worktree", str(self.repo), "--parent", self.parent,
             "--revision", self.revision],
            capture_output=True, text=True, check=False)

    def packet(self) -> str:
        return (self.review / "packets" / "EPW-code.md").read_text(
            encoding="utf-8")

    def test_full_diff_and_slice(self) -> None:
        self.write_spec(
            "diff\tnet/buffer.cc\t-\t-\twhole file\n"
            "slice\tnet/buffer.cc\t-\t3-7\tearly region\n")
        result = self.run_packets()
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = self.packet()
        self.assertIn("+changed early", packet)
        self.assertIn("+changed late", packet)
        self.assertIn("     5\tchanged early", packet)
        self.assertIn("never bounds your tracing", packet)

    def test_hunk_filtering_by_new_range(self) -> None:
        self.write_spec("diff\tnet/buffer.cc\t-\t45-55\tlate hunks only\n")
        result = self.run_packets()
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = self.packet()
        self.assertIn("+changed late", packet)
        self.assertNotIn("+changed early", packet)

    def test_empty_scope_fails_closed(self) -> None:
        self.write_spec("diff\tnet/other.cc\t-\t-\twrong path\n")
        result = self.run_packets()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no hunks", result.stderr)

    def test_traversal_path_rejected(self) -> None:
        self.write_spec("slice\t../secret\t-\t1-2\tbad\n")
        result = self.run_packets()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repo-relative", result.stderr)

    def test_wrong_worktree_revision_fails(self) -> None:
        self.write_spec("diff\tnet/buffer.cc\t-\t-\tx\n")
        result = subprocess.run(
            [sys.executable, str(PACKETS), str(self.review), "EPW",
             "--worktree", str(self.repo), "--parent", self.parent,
             "--revision", self.parent],
            capture_output=True, text=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match", result.stderr)


if __name__ == "__main__":
    unittest.main()
