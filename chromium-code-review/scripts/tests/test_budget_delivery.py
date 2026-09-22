from __future__ import annotations

from pathlib import Path
import subprocess
import unittest

import test_review_tools as fixtures
VALIDATE = fixtures.VALIDATE


class BudgetDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReviewDirectoryValidatorTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.review
        ledger = self.root / 'ledger/EPW.md'
        with ledger.open('a') as stream:
            stream.write('''
## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-2 | priority hypothesis | a.cc:1 | needs trace | CL-introduced | | candidate |
| EPW-3 | deferred hypothesis | a.cc:1 | needs trace | CL-introduced | | candidate |
| EPW-4 | proposed duplicate | a.cc:1 | needs equivalence | CL-introduced | | candidate |

## Candidate descriptors

| candidate | classes | obligations | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
''')
            for candidate in ('EPW-2', 'EPW-3', 'EPW-4'):
                stream.write(f'| {candidate} | general | local-proof | function | owner | value | update | local | x |\n')
        self.fixture.make_final_artifacts()
        (self.root / 'verification').mkdir(exist_ok=True)
        (self.root / 'verification/V001.md').write_text('''# Verification

| id | candidate | verdict | evidence | severity (anchor) | origin |
| --- | --- | --- | --- | --- | --- |
| V001-1 | EPW-2 | REFUTED | guard holds at a.cc:1 | — | — |

## Trace closure

| candidate | obligation | result | evidence |
| --- | --- | --- | --- |
| EPW-2 | local-proof | REFUTES CANDIDATE | guard at a.cc:1 |

## Verified affinity

| candidate | base / interface | invariant owner | violated invariant | state / transition | proposed fix layer | related symbols |
| --- | --- | --- | --- | --- | --- | --- |
| EPW-2 | function | owner | value | update | local | x |
''')
        (self.root / 'verification/affinity.md').write_text("""## Root families

| root family | members | shared invariant | invariant owner | state / transition | fix layer | related symbols | disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |

## Consistency audit

| check | rows / families | evidence | result |
| --- | --- | --- | --- |
""" + ''.join(f'| {check} | EPW-2 | a.cc:1 | no remaining conflict |\n' for check in (
            'contradictory assumptions', 'invariant-owner collisions', 'style-authority scope',
            'lifetime operation owner', 'reachability termination', 'repeated local fixes')))
        self.batches = self.root / 'verification/batches.md'
        self.batches.write_text('''# Verification batches

## Merge proposals

| row | proposal |
| --- | --- |
| EPW-4 | merge-into EPW-3: pending equivalence |

## Batches

| batch | brief | candidates | verdict file |
| --- | --- | --- | --- |
| V001 | briefs/V001.md | EPW-2 | verification/V001.md |
| V002 | briefs/V002.md | EPW-3 | verification/V002.md |

## Budget-limited verification

| candidate | batch | attempt | survivor | reason |
| --- | --- | --- | --- | --- |
| EPW-3 | V002 | 1 | - | spawn-budget exhausted |
| EPW-4 | V002 | 1 | EPW-3 | spawn-budget exhausted |
''')
        directives = self.root / 'directives.md'
        with directives.open('a') as stream:
            stream.write('\nspawn-budget: 1\n')
        for work, ids in [('V001', 'EPW-2'), ('V002', 'EPW-3')]:
            brief = self.root / f'briefs/{work}.md'
            brief.write_text((self.root / 'briefs/EPW.md').read_text() + f'\nScope: {ids}\n')
            with (self.root / 'orchestration.tsv').open('a') as stream:
                state = 'terminated' if work == 'V002' else 'complete'
                remaining = 'budget exhausted; candidates: EPW-3' if work == 'V002' else '—'
                stream.write(f'5\t{work}\t1\t{state}\tfrontier\t—\t{brief}\t{self.root / f"verification/{work}.md"}\t{remaining}\t—\n')
        recon = self.root / 'reconciliation.md'
        recon.write_text(recon.read_text().replace('## Pre-output gate', '''| EPW-2 | priority | refuted (V001-1 a.cc:1) |
| EPW-3 | deferred | unreviewed — budget exhausted |
| EPW-4 | deferred alias | unreviewed — budget exhausted |
| V001-1 | verification | supports refutation EPW-2 |

## Pre-output gate'''))
        # Keep appended dispositions in a real Markdown table.
        recon.write_text(recon.read_text().replace('\n\n| EPW-2', '\n| EPW-2'))
        draft = self.root / 'draft-review.md'
        draft.write_text(draft.read_text() + '''
- Review completeness: limited

## Verification Notes

Limited review: 2 candidate IDs were not independently verified because the review budget was exhausted.
Exact unverified scope: [budget gaps](verification/batches.md).
''')
        (self.root / 'gerrit-comments.md').write_text('# Comments\n\nPartial review; see verification notes.\n')
        challenge = self.root / 'challenge/round-1/index.md'
        challenge.write_text(challenge.read_text().replace('row:R1-RC001-1', 'row:R1-RC001-1, row:EPW-2, row:EPW-3, row:EPW-4, row:V001-1'))
        self.fixture.refresh_input_manifest()
        self.fixture.refresh_indexes()

    def check(self):
        self.fixture.refresh_indexes()
        result = subprocess.run([str(VALIDATE), str(self.root), '--phase', 'final'], capture_output=True, text=True)
        return result

    def test_honest_subset_passes_full_final_gate(self):
        result = self.check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_gap_omission_and_arbitrary_candidate_rejected(self):
        original = self.batches.read_text()
        for changed in (original.replace('| EPW-4 | V002 | 1 | EPW-3 | spawn-budget exhausted |\n', ''),
                        original.replace('| EPW-3 | V002 | 1 | - |', '| MADEUP-1 | V002 | 1 | - |')):
            with self.subTest(changed=changed):
                self.batches.write_text(changed)
                result = self.check()
                self.assertNotEqual(0, result.returncode)
                self.assertIn('budget gap', result.stdout)
        self.batches.write_text(original)

    def test_existing_verdict_cannot_be_hidden_by_gap(self):
        path = self.root / 'verification/V002.md'
        path.write_text((self.root / 'verification/V001.md').read_text().replace('V001-1', 'V002-1').replace('EPW-2', 'EPW-3'))
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('already has a verdict', result.stdout)

    def test_missing_termination_rejected(self):
        path = self.root / 'orchestration.tsv'
        path.write_text(path.read_text().replace('V002\t1\tterminated', 'V002\t1\trunning'))
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('authenticated latest terminated', result.stdout)

    def test_unverified_promotion_merge_and_clean_laundering_rejected(self):
        path = self.root / 'reconciliation.md'
        original = path.read_text()
        for disposition in ('promoted → F001', 'merged → EPW-2', 'refuted (a.cc:1)', 'clean (cited)'):
            path.write_text(original.replace('| EPW-3 | deferred | unreviewed — budget exhausted |', f'| EPW-3 | deferred | {disposition} |'))
            result = self.check()
            self.assertNotEqual(0, result.returncode)
            self.assertIn('must remain explicitly unreviewed', result.stdout)

    def test_missing_disclosure_rejected(self):
        path = self.root / 'draft-review.md'
        path.write_text(path.read_text().split('## Verification Notes')[0])
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('visible limited-review disclosure', result.stdout)

    def test_required_inventory_and_verified_root_cause_obligations_remain(self):
        validator = fixtures.load_review_validator()
        report = validator.Report()
        validator.validate_root_cause_trigger_accounting(
            self.root, {'T001'}, {'EPW-2': ('V001-1', 'CONFIRMED')},
            {'EPW-2': 'RF001', 'V001-1': 'RF001'}, report)
        self.assertTrue(any('root-cause trigger rows' in error for error in report.errors), report.errors)
        path = self.root / 'root-cause/batches.md'
        path.write_text(path.read_text().replace('| scheduled | RC001 |', '| not applicable | — |'))
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('root-cause-required scope T001 is not scheduled', result.stdout)

    def test_unstarted_gap_does_not_require_unused_code_packet(self):
        brief = self.root / 'briefs/V002.md'
        brief.write_text(brief.read_text() + f'Inputs: {self.root / "packets/V002-code.md"}\n')
        self.fixture.refresh_input_manifest()
        result = self.check()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        path = self.root / 'orchestration.tsv'
        path.write_text(path.read_text().replace('V002\t1\tterminated\tfrontier\t—', 'V002\t1\tterminated\tfrontier\tactually-started'))
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('Inputs/Procedure but input-manifest.tsv omits it', result.stdout)

    def test_visible_clean_claim_rejected(self):
        path = self.root / 'draft-review.md'
        path.write_text(path.read_text() + '\nVerdict: LGTM\n')
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('claims a clean or complete review', result.stdout)

    def test_unexhausted_budget_and_rewritten_seal_rejected(self):
        path = self.root / 'directives.md'
        path.write_text(path.read_text().replace('spawn-budget: 1', 'spawn-budget: 9999'))
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('exhausted recorded budget', result.stdout)
        path.write_text(path.read_text().replace('spawn-budget: 9999', 'spawn-budget: 1'))
        brief = self.root / 'briefs/V002.md'
        brief.write_text(brief.read_text() + '\nrewritten seal\n')
        result = self.check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn('authenticated latest terminated', result.stdout)
