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
