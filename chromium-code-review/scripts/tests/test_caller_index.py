#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
CALLERS = SCRIPTS / "build-caller-index.py"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
             "PATH": "/usr/bin:/bin"}).stdout.strip()


class CallerIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="caller-index-"))
        self.addCleanup(shutil.rmtree, root, True)
        self.repo = root / "repo"
        (self.repo / "components" / "foo").mkdir(parents=True)
        (self.repo / "chrome").mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "components" / "foo" / "buffer.cc").write_text(
            "int PushBytes() { return 0; }\n", encoding="utf-8")
        # Caller in a completely different top-level directory: a search
        # scoped to the changed directory must not be presented as complete.
        (self.repo / "chrome" / "user.cc").write_text(
            "void Use() { PushBytes(); }\nvoid More() { PushBytes(); }\n",
            encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "base")
        self.revision = git(self.repo, "rev-parse", "HEAD")
        self.review = root / "review"
        (self.review / "indexes").mkdir(parents=True)
        (self.review / "indexes" / "inventory.tsv").write_text(
            "kind\tid\tsubject\tscope\ttags\tcitations\tsource\n"
            "surface\tS001\tDelayBuffer::PushBytes\tcore\t-\t"
            "components/foo/buffer.cc:1\tinventory.md\n"
            "surface\tS002\tgroup: 4 test bodies\ttest\t-\t"
            "components/foo/buffer.cc:1\tinventory.md\n"
            "trigger\tT001\tMechanical Leads\t-\t-\t"
            "components/foo/buffer.cc:1\tinventory.md\n",
            encoding="utf-8")

    def run_index(self, *extra: str,
                  revision: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CALLERS), str(self.review),
             "--worktree", str(self.repo),
             "--revision", revision or self.revision, *extra],
            capture_output=True, text=True, check=False)

    def hits(self) -> str:
        return (self.review / "callers" / "PushBytes.txt").read_text(
            encoding="utf-8")

    def test_default_scope_finds_cross_directory_callers(self) -> None:
        result = self.run_index()
        self.assertEqual(result.returncode, 0, result.stderr)
        hits = self.hits()
        self.assertIn("chrome/user.cc:1:", hits)
        self.assertIn("chrome/user.cc:2:", hits)
        self.assertIn("Repository-wide and uncapped", hits)
        self.assertNotIn("SCOPE-LIMITED", hits)
        index = (self.review / "callers" / "index.tsv").read_text(
            encoding="utf-8")
        self.assertIn("S001\tDelayBuffer::PushBytes\tPushBytes\t3\t"
                      "repository-wide\tcallers/PushBytes.txt", index)
        self.assertIn("skipped — aggregated group row", index)

    def test_narrowed_scope_is_marked_incomplete(self) -> None:
        result = self.run_index("--pathspec", "components/foo")
        self.assertEqual(result.returncode, 0, result.stderr)
        hits = self.hits()
        self.assertNotIn("chrome/user.cc", hits)
        self.assertIn("SCOPE-LIMITED", hits)
        self.assertIn("Widen the search yourself", hits)
        index = (self.review / "callers" / "index.tsv").read_text(
            encoding="utf-8")
        self.assertIn("\tcomponents/foo\t", index)

    def test_rerun_is_memoized_and_scope_change_researches(self) -> None:
        self.run_index()
        before = (self.review / "callers" / "PushBytes.txt").stat().st_mtime_ns
        result = self.run_index()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(1 reused)", result.stdout)
        after = (self.review / "callers" / "PushBytes.txt").stat().st_mtime_ns
        self.assertEqual(before, after)
        # A different scope must not reuse the repo-wide result file.
        result = self.run_index("--pathspec", "components/foo")
        self.assertIn("(0 reused)", result.stdout)
        self.assertIn("SCOPE-LIMITED", self.hits())

    def test_truncated_cache_is_rebuilt(self) -> None:
        self.run_index()
        target = self.review / "callers" / "PushBytes.txt"
        intact = target.read_text(encoding="utf-8").splitlines()
        # Simulate a crash after the header: declared hits, missing body.
        target.write_text("\n".join(intact[:3]) + "\n", encoding="utf-8")
        result = self.run_index()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(0 reused)", result.stdout)
        rebuilt = target.read_text(encoding="utf-8")
        self.assertIn("chrome/user.cc:1:", rebuilt)
        self.assertIn("# 3 hit(s).", rebuilt)

    def test_wrong_pinned_revision_is_rejected(self) -> None:
        result = self.run_index(revision="0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match pinned revision", result.stderr)
        self.assertFalse((self.review / "callers").exists())

    def test_stale_revision_cache_is_rebuilt(self) -> None:
        self.run_index()
        target = self.review / "callers" / "PushBytes.txt"
        stale = target.read_text(encoding="utf-8").replace(
            "revision: ", "revision: 0000dead")
        target.write_text(stale, encoding="utf-8")
        result = self.run_index()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(0 reused)", result.stdout)
        head = git(self.repo, "rev-parse", "HEAD")
        self.assertIn(f"revision: {head}",
                      target.read_text(encoding="utf-8"))

    def test_missing_index_fails(self) -> None:
        (self.review / "indexes" / "inventory.tsv").unlink()
        result = self.run_index()
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
