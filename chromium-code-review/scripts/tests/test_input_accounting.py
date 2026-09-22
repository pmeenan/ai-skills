import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from input_accounting import archived_output_matches, effective_input_limit, executable_only
from orchestration_state import INPUT_COLUMNS, ORCHESTRATION_COLUMNS, encode

def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class InputAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.brief = self.root / 'brief.md'
        self.brief.write_text('Never read or grep helper script source files (`scripts/*.py`).\n')
        self.tool = self.root / 'repaired-tools-v13/skill-snapshot/scripts/helper.py'
        self.tool.parent.mkdir(parents=True)
        self.payload = b'#!/usr/bin/env python3\nprint("tool")\n'
        self.tool.write_bytes(self.payload)
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.manifest = self.tool.parent.parent / 'snapshot-manifest.json'
        self.manifest.write_text(json.dumps({'schema_version': 1, 'files': [
            {'path': 'scripts/helper.py', 'bytes': len(self.payload), 'sha256': self.sha}]}))
        self.tool.chmod(0o555)
        self.manifest.chmod(0o444)

    def excluded(self, **kwargs):
        return executable_only(self.root, kwargs.get('path', self.tool), self.brief,
                               kwargs.get('role', 'assigned'), len(self.payload),
                               kwargs.get('sha', self.sha))

    def test_executable_only_requires_sealed_snapshot_and_prohibition(self):
        self.assertTrue(self.excluded())
        self.assertFalse(self.excluded(role='reference'))
        self.assertFalse(self.excluded(sha='0' * 64))
        self.brief.write_text('Read the helper implementation as evidence.\n')
        self.assertFalse(self.excluded())
        self.brief.write_text('Never read or grep helper script source files')
        self.tool.chmod(0o755)
        self.assertFalse(self.excluded())
        self.tool.chmod(0o555)
        self.manifest.chmod(0o644)
        self.assertFalse(self.excluded())

    def test_arbitrary_code_and_snapshot_tests_are_not_exempt(self):
        arbitrary = self.root / 'helper.py'
        arbitrary.write_bytes(self.payload)
        arbitrary.chmod(0o555)
        self.assertFalse(self.excluded(path=arbitrary))
        tests = self.tool.parent / 'tests/helper.py'
        tests.parent.mkdir()
        tests.write_bytes(self.payload)
        tests.chmod(0o555)
        self.assertFalse(self.excluded(path=tests))

    def test_tier_fallback_and_global_limit_both_apply(self):
        context = {'worker_input_budget_bytes': 1048576,
                   'tier_worker_input_budget_bytes': {'standard': 2000000}}
        self.assertEqual(131072, effective_input_limit(context, 'mechanical'))
        self.assertEqual(1048576, effective_input_limit(context, 'standard'))
        self.assertEqual(1048576, effective_input_limit(context, 'inherit'))
        seal = load('seal-work-unit')
        (self.root / 'profile.json').write_text(json.dumps({'context_budget': context}))
        oversized = self.root / 'assigned.md'
        oversized.write_bytes(b'x' * 131073)
        with self.assertRaises(SystemExit):
            seal.validate_budget(self.root, 'mechanical', [('assigned', oversized, oversized.read_bytes())])
        # Executable implementation bytes cannot displace real read inputs.
        seal.validate_budget(self.root, 'mechanical', [
            ('brief', self.brief, self.brief.read_bytes()),
            ('assigned', self.tool, self.payload)])

    def row(self, path, payload, role='prestate'):
        return dict(work_id='FWF001', attempt='2', phase='7', brief=str(self.brief),
                    input_path=str(path), role=role, bytes=str(len(payload)),
                    sha256=hashlib.sha256(payload).hexdigest())

    def test_archive_authenticates_exact_old_output_not_ledgers(self):
        artifact = self.root / 'draft-parts/F001.md'
        artifact.parent.mkdir()
        artifact.write_bytes(b'new shorter')
        previous = b'original immutable output bytes'
        row = self.row(artifact, previous)
        self.assertFalse(archived_output_matches(self.root, row))
        (self.root / 'input-manifest.tsv').write_text(encode(INPUT_COLUMNS, [row]))
        source = self.root / 'old.md'
        source.write_bytes(previous)
        command = [sys.executable, str(SCRIPTS / 'archive-output-version.py'), str(self.root), str(artifact), str(source)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(archived_output_matches(self.root, row))
        self.assertEqual(b'new shorter', artifact.read_bytes())
        self.assertFalse(archived_output_matches(self.root, dict(row, input_path=str(self.root / 'ledger/F001.md'))))
        self.assertFalse(archived_output_matches(self.root, dict(row, sha256='0' * 64)))
        source.write_bytes(b'fabricated old bytes')
        self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)
        archive = self.root / 'output-history' / (row['sha256'] + '.bin')
        archive.chmod(0o644)
        self.assertFalse(archived_output_matches(self.root, row))

    def test_gate_preserves_prestate_checks_outside_output_archives(self):
        validator = load('validate-review-dir')
        artifact = self.root / 'draft-parts/F001.md'
        artifact.parent.mkdir()
        artifact.write_bytes(b'new')
        old = b'old original larger'
        prestate = self.row(artifact, old)
        archive = self.root / 'output-history' / (prestate['sha256'] + '.bin')
        archive.parent.mkdir()
        archive.write_bytes(old)
        archive.chmod(0o444)
        rows = [self.row(self.brief, self.brief.read_bytes(), 'brief'), prestate]
        (self.root / 'input-manifest.tsv').write_text(encode(INPUT_COLUMNS, rows))
        orch = dict(phase='7',work_id='FWF001',attempt='2',state='complete',tier='standard',task_id='-',brief=str(self.brief),artifact=str(artifact),remaining_scope='-',depends_on='-')
        (self.root / 'orchestration.tsv').write_text(encode(ORCHESTRATION_COLUMNS, [orch]))
        report = validator.Report()
        validator.validate_input_manifest(self.root, {}, report, {}, False)
        self.assertFalse(any('prestate' in error for error in report.errors), report.errors)
        archive.unlink()
        report = validator.Report()
        validator.validate_input_manifest(self.root, {}, report, {}, False)
        self.assertTrue(any('prestate prefix' in error for error in report.errors), report.errors)

    def test_finalizer_authenticates_only_freshness_line_rewrite(self):
        validator = load('validate-review-dir')
        original = (b'before\n2. **Freshness:** pending-delivery \xe2\x80\x94 Phase 9 '
                    b'metadata refresh remains required.\nafter\n')
        current = (b'before\n2. **Freshness:** yes \xe2\x80\x94 current; delivery-gate.md\n'
                   b'after\n\n## Amendments\n| CLERICAL-A1 | valid append |\n')
        reconciliation = self.root / 'reconciliation.md'
        reconciliation.write_bytes(current)
        (self.root / 'reconciliation.before-clerical.md').write_bytes(original)
        (self.root / 'delivery-gate.md').write_text(
            '# Delivery freshness\n- Result: current\n- Gate line: yes \xe2\x80\x94 current\n'
        )
        row = self.row(reconciliation, original)
        self.assertTrue(validator.finalizer_freshness_prestate_matches(
            self.root, row, current
        ))
        self.assertFalse(validator.finalizer_freshness_prestate_matches(
            self.root, row, current.replace(b'before', b'changed')
        ))
        self.assertFalse(validator.finalizer_freshness_prestate_matches(
            self.root, row, current.replace(b'after', b'changed', 1)
        ))
        (self.root / 'delivery-gate.md').write_text(
            '# Delivery freshness\n- Result: fetch failed\n- Gate line: no \xe2\x80\x94 fetch failed\n'
        )
        self.assertFalse(validator.finalizer_freshness_prestate_matches(
            self.root, row, current
        ))

    def test_top_level_revision_archive_requires_exact_manifest_binding(self):
        for name in ('draft-review.md', 'gerrit-comments.md', 'output-coverage.tsv'):
            with self.subTest(name=name):
                artifact = self.root / name
                artifact.write_bytes(b'revision two')
                previous = b'original revision one of ' + name.encode()
                row = self.row(artifact, previous)
                source = self.root / 'historical.md'
                source.write_bytes(previous)
                command = [sys.executable, str(SCRIPTS / 'archive-output-version.py'),
                           str(self.root), str(artifact), str(source)]
                # A binding for another output cannot authorize this path.
                wrong = dict(row, input_path=str(self.root / 'draft-parts/F001.md'))
                (self.root / 'input-manifest.tsv').write_text(encode(INPUT_COLUMNS, [wrong]))
                self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)
                (self.root / 'input-manifest.tsv').write_text(encode(INPUT_COLUMNS, [row]))
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertTrue(archived_output_matches(self.root, row))
                self.assertEqual(b'revision two', artifact.read_bytes())
                self.assertFalse(archived_output_matches(self.root, dict(row, bytes='1')))
                self.assertFalse(archived_output_matches(self.root, dict(row, sha256='0' * 64)))
                source.write_bytes(b'unbound older revision')
                self.assertNotEqual(0, subprocess.run(command, capture_output=True).returncode)

    def test_other_artifact_prefixes_cannot_use_output_history(self):
        previous = b'authenticated bytes are insufficient for non-output artifacts'
        source = self.root / 'historical.md'
        source.write_bytes(previous)
        names = ('ledger/F001.md', 'draft-assembly/manifest.md', 'challenge.md',
                 'nested/draft-review.md', 'draft-review.revision-1.md',
                 'draft-parts/nested/F001.md', 'output-coverage.tsv.extra')
        for name in names:
            with self.subTest(name=name):
                artifact = self.root / name
                row = self.row(artifact, previous)
                (self.root / 'input-manifest.tsv').write_text(encode(INPUT_COLUMNS, [row]))
                result = subprocess.run([sys.executable, str(SCRIPTS / 'archive-output-version.py'),
                                         str(self.root), str(artifact), str(source)], capture_output=True)
                self.assertNotEqual(0, result.returncode)
                self.assertFalse(archived_output_matches(self.root, row))
