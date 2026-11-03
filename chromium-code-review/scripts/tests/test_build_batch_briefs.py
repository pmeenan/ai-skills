from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location('batch_builder', SCRIPTS / 'build-batch-briefs.py')
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

VERIFICATION = '''## Batches

| batch | brief | candidates | verdict file |
| --- | --- | --- | --- |
| V001 | briefs/V001.md | PR-1 | verification/V001.md |
'''
ROOT_CAUSE = '''## Batches

| batch | brief | root families / scopes | output | bounded input |
| --- | --- | --- | --- | --- |
| RC001 | briefs/RC001.md | RF001: PR-1/V001-1 | root-cause/RC001.md | one family |
'''


class BatchBriefTests(unittest.TestCase):
    def test_normative_and_legacy_headings(self):
        for phase, text, alias in [('verification', VERIFICATION, 'Skeptic batches'),
                                   ('root-cause', ROOT_CAUSE, 'Scheduled root-cause batches')]:
            self.assertEqual(1, len(BUILDER.batch_rows(text, phase)))
            self.assertEqual(1, len(BUILDER.batch_rows(text.replace('## Batches', '## ' + alias), phase)))

    def test_missing_empty_and_malformed_schedules_fail(self):
        for text in ['## Batches\n\nNone.\n', VERIFICATION.replace('## Batches', '## Typo'),
                     VERIFICATION[:VERIFICATION.index('| V001')],
                     VERIFICATION.replace('candidates', 'wrong column'),
                     VERIFICATION.replace('| V001 |', '| invalid |'),
                     VERIFICATION + VERIFICATION,
                     VERIFICATION.replace('briefs/V001.md', 'briefs/wrong.md')]:
            with self.subTest(text=text), self.assertRaises(SystemExit):
                BUILDER.batch_rows(text, 'verification')

    def test_normative_schedule_renders_effective_candidate_not_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review = root / 'review'
            worktree = root / 'worktree'
            worktree.mkdir()
            def git(*args):
                return subprocess.check_output(['git', '-C', str(worktree), *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.test')
            (worktree / 'a.cc').write_text('int x = 1;\n')
            git('add', 'a.cc')
            git('commit', '-qm', 'base')
            parent = git('rev-parse', 'HEAD')
            (worktree / 'a.cc').write_text('int x = 2;\n')
            git('commit', '-qam', 'change')
            revision = git('rev-parse', 'HEAD')
            shutil.copytree(SCRIPTS.parent, review / 'skill-snapshot')
            (review / 'ledger').mkdir()
            (review / 'verification').mkdir()
            (review / 'profile.json').write_text(json.dumps({'files': [{'path': 'a.cc', 'status': 'M'}]}))
            (review / 'pin.md').write_text(f'# CL 123 — patchset 1 pin\n- Revision SHA: {revision}\n- Parent SHA: {parent}\n- Worktree: {worktree}\n')
            (review / 'verification/batches.md').write_text(VERIFICATION)
            (review / 'ledger/PR.md').write_text('''## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| PR-1 | original claim | a.cc:1 | inspected | CL-introduced | | candidate |

## Candidate descriptors

| candidate | classes | obligations |
| --- | --- | --- |
| PR-1 | contract | base-contract |

## Amendments

| amendment | target | operation | replacement / reason |
| --- | --- | --- | --- |
| PR-A1 | PR-1 | replace-fields | {"claim":"effective claim"} |
''')
            result = subprocess.run([sys.executable, str(SCRIPTS / 'build-batch-briefs.py'), str(review), '--phase', 'verification'], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            brief = (review / 'briefs/V001.md').read_text()
            self.assertIn('| PR-1 | effective claim | a.cc:1 |', brief)
            self.assertNotIn('| PR-1 | contract | base-contract |', brief)
            self.assertTrue((review / 'packets/V001-code.md').is_file())
            self.assertIn('--work-id V001', result.stdout)
            (review / 'root-cause').mkdir()
            (review / 'root-cause/batches.md').write_text(ROOT_CAUSE)
            (review / 'verification/V001.md').write_text('''| id | candidate | verdict | evidence |
| --- | --- | --- | --- |
| V001-1 | PR-1 | CONFIRMED | a.cc:1 |
''')
            result = subprocess.run([sys.executable, str(SCRIPTS / 'build-batch-briefs.py'), str(review), '--phase', 'root-cause'], capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('RF001: PR-1/V001-1', (review / 'briefs/RC001.md').read_text())

class MergeSupportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'ledger').mkdir()
        (self.root / 'verification').mkdir()
        (self.root / 'profile.json').write_text(json.dumps({'budgets': {
            'candidate_packet_budget_bytes': 16384, 'worker_input_budget_bytes': 131072}}))
        (self.root / 'ledger/GSS2.md').write_text('''## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| GAI2-63 | alias condition | a.cc:10 | alias evidence | CL-introduced | | candidate |
| GSS2-11 | survivor condition | a.cc:20 | survivor evidence | CL-introduced | | candidate |
| OTHER-1 | unrelated secret | b.cc:99 | not selected | CL-introduced | | candidate |

## Candidate descriptors

| candidate | classes | obligations | invariant owner |
| --- | --- | --- | --- |
| GAI2-63 | contract | caller-reachability | alias owner |
| GSS2-11 | contract | caller-reachability | target owner |
''')
        (self.root / 'verification/batches.md').write_text('''## Merge proposals

| row | proposal |
| --- | --- |
| GAI2-63 | merge-into GSS2-11: provisional similarity |
''')
        self.verdict = self.root / 'verification/V001.md'
        self.verdict.write_text('''# Verdict

| id | candidate | verdict | evidence |
| --- | --- | --- | --- |
| V001-1 | GSS2-11 | REFUTED | exact target guard a.cc:20 |
| V001-2 | OTHER-1 | REFUTED | unrelated secret b.cc:99 |

## Trace closure

| candidate | obligation | result | evidence |
| --- | --- | --- | --- |
| GSS2-11 | caller-reachability | REFUTES CANDIDATE | caller guard a.cc:21 |
| OTHER-1 | caller-reachability | REFUTES CANDIDATE | unrelated secret b.cc:99 |

## Verified affinity

| candidate | invariant owner | violated invariant | state / transition |
| --- | --- | --- | --- |
| GSS2-11 | target owner | target invariant | target transition |
''')

    def test_refuted_survivor_has_exact_bounded_comparison_context(self):
        text = BUILDER.merge_support_context(self.root, ['GAI2-63'])
        self.assertIn('GAI2-63 -> GSS2-11', text)
        self.assertIn('| GSS2-11 | survivor condition |', text)
        self.assertIn('| GSS2-11 | contract | caller-reachability | target owner |', text)
        self.assertIn('| V001-1 | GSS2-11 | REFUTED | exact target guard a.cc:20 |', text)
        self.assertIn('caller guard a.cc:21', text)
        self.assertIn('target invariant', text)
        self.assertIn('does not establish equivalence', text)
        self.assertIn('Supporting context only', text)
        self.assertNotIn('unrelated secret', text)
        self.assertNotIn('OTHER-1', text)

    def test_root_cause_generator_adds_context_without_reassigning_survivor(self):
        skill = self.root / 'skill-snapshot'
        shutil.copytree(SCRIPTS.parent, skill)
        (self.root / 'root-cause').mkdir()
        (self.root / 'root-cause/batches.md').write_text(ROOT_CAUSE.replace('RF001: PR-1/V001-1', 'RF001: GAI2-63'))
        BUILDER.build_root_cause(self.root, skill, {
            'CL': '123', 'PS': '1', 'sha': 'a' * 40, 'parent-sha': 'b' * 40,
            'worktree': str(self.root / 'worktree')}, 1, 1, False)
        brief = (self.root / 'briefs/RC001.md').read_text()
        packet = self.root / 'packets/RC001-merge-context.md'
        self.assertTrue(packet.is_file())
        self.assertIn(str(packet), brief)
        self.assertIn('not additional assigned candidates', brief)
        self.assertIn('RF001: GAI2-63', brief)
        self.assertNotIn('GSS2-11', brief)
        self.assertIn('GSS2-11', packet.read_text())

    def test_cycles_missing_candidates_and_missing_verdict_fail(self):
        path = self.root / 'verification/batches.md'
        original = path.read_text()
        path.write_text(original + '| GSS2-11 | merge-into GAI2-63: cycle |\n')
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])
        path.write_text(original.replace('merge-into GSS2-11:', 'merge-into MISSING-1:'))
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])
        path.write_text(original)
        self.verdict.unlink()
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])

    def test_ambiguous_verdict_missing_closure_and_budget_fail(self):
        duplicate = self.root / 'verification/V002.md'
        duplicate.write_text(self.verdict.read_text())
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])
        duplicate.unlink()
        original = self.verdict.read_text()
        self.verdict.write_text(original.replace('## Trace closure', '## Wrong heading'))
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])
        self.verdict.write_text(original)
        (self.root / 'profile.json').write_text(json.dumps({'budgets': {
            'candidate_packet_budget_bytes': 100, 'worker_input_budget_bytes': 131072}}))
        with self.assertRaises(SystemExit):
            BUILDER.merge_support_context(self.root, ['GAI2-63'])


class BackHalfFastPathAndShiftLeftTests(unittest.TestCase):
    def test_plan_verification_root_cause_and_reconciliation_fast_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review = root / 'review'
            worktree = root / 'worktree'
            worktree.mkdir()

            def git(*args):
                return subprocess.check_output(['git', '-C', str(worktree), *args], text=True).strip()

            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.test')
            (worktree / 'a.cc').write_text('int x = 1;\nint y = 2;\n')
            git('add', 'a.cc')
            git('commit', '-qm', 'base')
            parent = git('rev-parse', 'HEAD')
            (worktree / 'a.cc').write_text('int x = 10;\nint y = 2;\n')
            git('commit', '-qam', 'change')
            revision = git('rev-parse', 'HEAD')
            shutil.copytree(SCRIPTS.parent, review / 'skill-snapshot')
            (review / 'ledger').mkdir()
            (review / 'profile.json').write_text(json.dumps({
                'files': [{'path': 'a.cc', 'status': 'M'}],
                'budgets': {'candidate_packet_budget_bytes': 16384, 'worker_input_budget_bytes': 131072},
            }))
            (review / 'pin.md').write_text(
                f'# CL 123 — patchset 1 pin\n- Revision SHA: {revision}\n- Parent SHA: {parent}\n- Worktree: {worktree}\n'
            )
            (review / 'inventory.md').write_text('''# Inventory

## Changed surfaces
| id | file | surface | kind | risk | trigger |
| --- | --- | --- | --- | --- | --- |
| S001 | a.cc | x | function | correctness | T001 |

## Trigger inventory
| scope id | surface | discovery triggers | root-cause trigger | graph scope | evidence |
| --- | --- | --- | --- | --- | --- |
| T001 | a.cc:1 | async | required: async-lifecycle | graph:E-001 | a.cc:1 |

## Complexity graph edges
| edge | from | to | kind | status | evidence |
| --- | --- | --- | --- | --- | --- |
| E-001 | a.cc:1 | a.cc:1 | caller | open | a.cc:1 |
''')
            (review / 'ledger/PR.md').write_text('''# PR

## Candidate rows
| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| PR-1 | minor naming nit on `x` | a.cc:1 | graph:E-001 inspected | CL-introduced | P3 | candidate |

## Candidate descriptors
| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PR-1 | style | applicable-authority,project-precedent,local-consistency | none | a.cc:x | naming consistency | declaration | a.cc | x |

## Complexity graph delta
| edge | status | evidence | candidate | next obligation |
| --- | --- | --- | --- | --- |
| E-001 | resolved | a.cc:1 | PR-1 | none |

## Checked clean rows
| id | scope | evidence |
| --- | --- | --- |
| PR-C1 | a.cc:2 | unchanged line `int y = 2;` |
''')
            idx_res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'build-review-indexes.py'), str(review)],
                capture_output=True, text=True,
            )
            self.assertEqual(0, idx_res.returncode, idx_res.stderr)

            # 1. Phase 5 --plan fast path
            vplan_res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'build-batch-briefs.py'), str(review), '--phase', 'verification', '--plan'],
                capture_output=True, text=True,
            )
            self.assertEqual(0, vplan_res.returncode, vplan_res.stderr)
            self.assertTrue((review / 'verification/batches.md').is_file())
            self.assertTrue((review / 'briefs/V001.md').is_file())
            self.assertTrue((review / 'packets/V001-code.md').is_file())

            # Write skeptic verdict confirming P3
            (review / 'verification/V001.md').write_text('''# Verification Batch V001

## Verdicts
| id | candidate | verdict | calibrated severity | anchor | delta | evidence |
| --- | --- | --- | --- | --- | --- | --- |
| V001-1 | PR-1 | CONFIRMED | P3 | P3 style | none | a.cc:1 |

## Trace closure
| candidate | obligation | result | evidence |
| --- | --- | --- | --- |
| PR-1 | applicable-authority | SUPPORTS CANDIDATE | style guide a.cc:1 |
| PR-1 | project-precedent | SUPPORTS CANDIDATE | local file a.cc:1 |
| PR-1 | local-consistency | SUPPORTS CANDIDATE | local file a.cc:1 |

## Verified affinity
| candidate | invariant owner | violated invariant | state / transition |
| --- | --- | --- | --- |
| PR-1 | a.cc:x | naming consistency | declaration |
''')
            subprocess.run(
                [sys.executable, str(SCRIPTS / 'build-review-indexes.py'), str(review)],
                check=True, capture_output=True, text=True,
            )

            # 2. Phase 5.25 + 5.5 --plan fast path (0 RC batches needed because T001 edge E-001 is closed and RF001 is P3)
            rcplan_res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'build-batch-briefs.py'), str(review), '--phase', 'root-cause', '--plan'],
                capture_output=True, text=True,
            )
            self.assertEqual(0, rcplan_res.returncode, rcplan_res.stderr)
            self.assertTrue((review / 'verification/affinity.md').is_file())
            batches_md = (review / 'root-cause/batches.md').read_text()
            self.assertIn('| T001 | — | not applicable —', batches_md)
            self.assertIn('| PR-1 / V001-1 | RF001 | not applicable — non-risky P3 validated in verification', batches_md)
            self.assertIn('- Trigger count: 0', batches_md)
            self.assertIn('- Result: empty', batches_md)

            # 3. Phase 6 deterministic build-reconciliation.py fast path
            rec_res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'build-reconciliation.py'), str(review)],
                capture_output=True, text=True,
            )
            self.assertEqual(0, rec_res.returncode, rec_res.stderr)
            self.assertTrue((review / 'reconciliation.md').is_file())
            self.assertTrue((review / 'synthesis/index.md').is_file())
            card = (review / 'synthesis/PR-1.md').read_text()
            self.assertIn('- Root cause: none', card)
            self.assertIn('- Root family: RF001', card)

    def test_worker_validator_shift_left_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review = root / 'review'
            worktree = root / 'worktree'
            worktree.mkdir()

            def git(*args):
                return subprocess.check_output(['git', '-C', str(worktree), *args], text=True).strip()

            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.test')
            (worktree / 'src').mkdir()
            (worktree / 'src/a.cc').write_text('int x = 1;\n' * 10 + 'int y = 2;\n')
            git('add', 'src/a.cc')
            git('commit', '-qm', 'base')
            parent = git('rev-parse', 'HEAD')
            (worktree / 'src/a.cc').write_text('int x = 10;\n' + 'int x = 1;\n' * 9 + 'int y = 2;\n')
            git('commit', '-qam', 'change')
            revision = git('rev-parse', 'HEAD')
            review.mkdir()
            (review / 'profile.json').write_text(json.dumps({
                'files': [{'path': 'src/a.cc', 'status': 'M'}],
            }))
            (review / 'pin.md').write_text(
                f'# CL 123 — patchset 1 pin\n- Revision SHA: {revision}\n- Parent SHA: {parent}\n- Worktree: {worktree}\n\n## Changed files\n- src/a.cc\n'
            )
            # Out-of-hunk suggestion on src/a.cc:11 (unchanged line outside diff hunk)
            (review / 'root-cause').mkdir()
            rc_file = review / 'root-cause/RC001.md'
            rc_file.write_text('''# RC001

## RC001-1 (for GAI-1)
- Root family: RF001
- Suggested-edit decision: applicable — replaces src/a.cc:11
- Suggested-edit selected lines:
  ```cpp
  int y = 2;
  ```
- Suggested-edit replacement:
  ```suggestion
  int y = 3;
  ```

## Root-family analysis
| root family | members | suggested edit |
| --- | --- | --- |
| RF001 | GAI-1 | applicable — RC001-1 |
''')
            res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'validate-worker-artifact.py'), str(review), str(rc_file)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, res.returncode)
            self.assertIn('does not intersect a changed-side hunk', res.stderr)

            # Draft fragment missing Regression test
            (review / 'draft-parts').mkdir()
            f_file = review / 'draft-parts/F001.md'
            f_file.write_text('''### [P3] src/a.cc:1 — Minor nit
- **Synthesis item:** F001
- **Claim:** minor naming nit
- **Location:** src/a.cc:1
- **Evidence:** src/a.cc:1 (`int x = 10;`)
- **Severity:** P3 (anchor: style; delta: none)
- **Origin:** CL-introduced
- **Fix status:** validated right layer
- **Suggested edit:** omitted — comment only
- **Rows:** GAI-1; V001-1; RC: none; RF001
''')
            res2 = subprocess.run(
                [sys.executable, str(SCRIPTS / 'validate-worker-artifact.py'), str(review), str(f_file)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, res2.returncode)
            self.assertIn('Regression test', res2.stderr)

            # Challenge index with global:consistency when draft-sections/index.tsv is absent
            (review / 'challenge/round-1').mkdir(parents=True)
            ch_idx = review / 'challenge/round-1/index.md'
            ch_idx.write_text('''# Challenge Round 1 Index
- Round: 1
- Draft sha256: deadbeef
- Gerrit comments sha256: deadbeef
- Overall status: pending

## Shards
| shard | brief | artifact | scope | expected coverage | status |
| --- | --- | --- | --- | --- | --- |
| CH001 | briefs/CH-R1-001.md | challenge/round-1/CH001.md | holistic | finding:F001, global:gates, global:consistency | pending |
''')
            res3 = subprocess.run(
                [sys.executable, str(SCRIPTS / 'validate-worker-artifact.py'), str(review), str(ch_idx)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(0, res3.returncode)
            self.assertIn('global:consistency', res3.stderr)

