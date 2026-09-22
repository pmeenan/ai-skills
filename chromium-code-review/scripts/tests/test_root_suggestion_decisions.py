import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('suggestion_validator', SCRIPTS / 'validate-review-dir.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class RootSuggestionTests(unittest.TestCase):
    def check(self, text):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'root-cause').mkdir()
            (root / 'root-cause/RC001.md').write_text(text)
            report = validator.Report()
            result = validator.root_suggestion_decisions(root, report)
            return result, report.errors

    def fixture(self):
        return '''## RC001-1 (for EPW-1)
- Root family: RF001
- Suggested-edit decision: omitted — shared repair requires multiple sites

## RC001-2 (for EPW-2)
- Root family: RF001
- Suggested-edit decision: omitted — shared repair requires multiple sites

## RC001-3 (for EPW-3)
- Root family: RF001
- Suggested-edit decision: omitted — this member is already guarded

## RC001-4 (for T001)
- Root family: scope:T001
- Suggested-edit decision: omitted — inventory scope has no actionable defect

## Root-family analysis
| root family | members | suggested edit |
| --- | --- | --- |
| RF001 | EPW-1, EPW-2, EPW-3 | omitted — shared repair requires multiple sites |
| scope:T001 | T001 | omitted — inventory scope has no actionable defect |
'''

    def test_family_selection_and_scoped_omissions(self):
        decisions, errors = self.check(self.fixture())
        self.assertEqual([], errors)
        self.assertEqual(['RC001-1'], list(decisions))
        self.assertIn('EPW-2', decisions['RC001-1']['members'])
        self.assertNotIn('T001', decisions['RC001-1']['members'])

    def test_omission_must_match_real_member(self):
        text = self.fixture().replace('| omitted — shared repair requires multiple sites |', '| omitted — fabricated reason |')
        decisions, errors = self.check(text)
        self.assertFalse(decisions)
        self.assertTrue(any('exact matching' in error for error in errors))

    def test_noncanonical_rows_still_validate(self):
        for replacement in ['omitted — none', 'applicable — replaces a.cc:1']:
            _, errors = self.check(self.fixture().replace('omitted — inventory scope has no actionable defect', replacement))
            self.assertTrue(errors)

    def test_applicable_binding_and_lossless_fences(self):
        original = self.fixture()
        replacement = '''applicable — replaces a.cc:1
- Suggested-edit selected lines:
  ```cpp
  old();
  ```
- Suggested-edit replacement:
  ```suggestion
  new();
  ```'''
        text = original.replace('omitted — shared repair requires multiple sites', replacement, 1)
        text = text.replace('| omitted — shared repair requires multiple sites |', '| applicable — RC001-1 |')
        decisions, errors = self.check(text)
        self.assertEqual([], errors)
        self.assertEqual('new();', decisions['RC001-1']['replacement'])
        for invalid in [text.replace('applicable — RC001-1 |', 'applicable — RC001-4 |'),
                        text.replace('  ```suggestion', '  ```cpp'),
                        text.replace('| applicable — RC001-1 |', '| applicable — RC002-1 |')]:
            self.assertTrue(self.check(invalid)[1])

    def test_missing_family_analysis_and_duplicate_selection_fail(self):
        self.assertTrue(self.check(self.fixture().split('## Root-family analysis')[0])[1])
        self.assertTrue(self.check(self.fixture() + '| RF001 | EPW-1 | omitted — shared repair requires multiple sites |\n')[1])

    def test_append_only_amendment_can_omit_family_suggestion(self):
        text = self.fixture().replace(
            'omitted — shared repair requires multiple sites',
            '''applicable — replaces a.cc:1
- Suggested-edit selected lines:
  ```cpp
  old();
  ```
- Suggested-edit replacement:
  ```suggestion
  new();
  ```''',
            1,
        ).replace(
            '| omitted — shared repair requires multiple sites |',
            '| applicable — RC001-1 |',
        )
        text += '''
## Amendments
| amendment | target | operation | replacement / reason | evidence | attempt |
| --- | --- | --- | --- | --- | --- |
| RC001-A1 | root-family:RF001 | replace-fields | {"suggested edit":"omitted — replacement exceeds inline size limits"} | a.cc:1 | 2 |

## Suggested-edit amendments
### RC001-SA1
- Target: RC001-1
- Suggested-edit decision: omitted — replacement exceeds inline size limits
- Evidence: a.cc:1
- Attempt: 2
'''
        decisions, errors = self.check(text)
        self.assertEqual([], errors)
        self.assertEqual('omitted', decisions['RC001-1']['status'])
        self.assertEqual('RC001-SA1', decisions['RC001-1']['effective_amendment'])
        self.assertEqual('', decisions['RC001-1']['selected'])

    def test_append_only_amendment_preserves_code_whitespace(self):
        text = self.fixture().replace(
            'omitted — shared repair requires multiple sites',
            '''applicable — replaces a.cc:1
- Suggested-edit selected lines:
  ```cpp
  old();
  ```
- Suggested-edit replacement:
  ```suggestion
  new();
  ```''',
            1,
        ).replace(
            '| omitted — shared repair requires multiple sites |',
            '| applicable — RC001-1 |',
        )
        text += '''
## Suggested-edit amendments
### RC001-SA1
- Target: RC001-1
- Suggested-edit decision: applicable — replaces a.cc:1
- Suggested-edit selected lines:
  ```cpp
    old();
  ```
- Suggested-edit replacement:
  ```suggestion
    new();
  ```
- Evidence: a.cc:1
- Attempt: 2
'''
        decisions, errors = self.check(text)
        self.assertEqual([], errors)
        self.assertEqual('  old();', decisions['RC001-1']['selected'])
        self.assertEqual('  new();', decisions['RC001-1']['replacement'])

    def test_amendment_target_is_exact_and_batch_prefix_safe(self):
        base = self.fixture()
        unknown = base + '''
## Suggested-edit amendments
### RC001-SA1
- Target: RC001-10
- Suggested-edit decision: omitted — replacement exceeds inline size limits
- Evidence: a.cc:1
- Attempt: 2
'''
        self.assertTrue(any('unknown row RC001-10' in error
                            for error in self.check(unknown)[1]))
        cross_batch = base + '''
## Suggested-edit amendments
### RC002-SA1
- Target: RC001-1
- Suggested-edit decision: omitted — replacement exceeds inline size limits
- Evidence: a.cc:1
- Attempt: 2
'''
        self.assertTrue(any('does not match its file prefix' in error
                            for error in self.check(cross_batch)[1]))
