#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "validate-review-dir.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("review_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def row(entry: str, scope: str) -> dict[str, str]:
    return {
        "roster entry": entry,
        "scope": scope,
        "status": "spawn",
        "tier": "frontier",
        "batch": "D01",
        "subagent": "—",
        "outcome": "—",
    }


class AdaptiveTopologyPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="adaptive-topology-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "indexes").mkdir()
        (self.root / "profile.json").write_text(json.dumps({
            "schema_version": 3,
            "topology": {"policy": "evidence-graph-v1"},
        }), encoding="utf-8")
        (self.root / "indexes" / "topology.tsv").write_text(
            "edge\tcandidate\nE-A\t-\nE-B\t-\n", encoding="utf-8")
        (self.root / "indexes" / "candidates.tsv").write_text(
            "id\tstatus\n", encoding="utf-8")

    def validate(self, rows: list[dict[str, str]]):
        report = VALIDATOR.Report()
        VALIDATOR.validate_plan(self.root, {}, rows, True, report)
        return report

    def write_priors(
        self,
        semantic: dict[str, str] | None = None,
        adversarial: dict[str, str] | None = None,
        scope: str = "graph:E-A,E-B",
    ) -> None:
        semantic = semantic or {}
        adversarial = adversarial or {}
        lines = [
            "lens\tgraph_scope\tassessor\tlikelihood\tsignals\t"
            "counterevidence\tcitations\tsource"
        ]
        for lens in VALIDATOR.SPECIALIST_LENSES:
            for assessor, overrides in (
                ("semantic-state", semantic),
                ("adversarial-integration", adversarial),
            ):
                lines.append(
                    "\t".join((
                        lens, scope, assessor,
                        overrides.get(lens, "low"), "foo.cc:10 inspected",
                        "foo.cc:11 guard present", "foo.cc:10,foo.cc:11",
                        f"ledger/{'GSS' if assessor == 'semantic-state' else 'GAI'}.md",
                    ))
                )
        (self.root / "indexes" / "specialist-priors.tsv").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )

    def test_matching_generalist_shards_cover_each_edge_once(self) -> None:
        rows = [
            row("Generalist Semantic And State Discovery — shard 1", "graph:E-A"),
            row("Generalist Semantic And State Discovery — shard 2", "graph:E-B"),
            row("Generalist Adversarial And Integration Discovery — shard 1", "graph:E-A"),
            row("Generalist Adversarial And Integration Discovery — shard 2", "graph:E-B"),
        ]
        self.assertEqual([], self.validate(rows).errors)

    def test_generalist_passes_must_share_partition(self) -> None:
        rows = [
            row("Generalist Semantic And State Discovery — shard 1", "graph:E-A"),
            row("Generalist Semantic And State Discovery — shard 2", "graph:E-B"),
            row("Generalist Adversarial And Integration Discovery — shard 1", "graph:E-A,E-B"),
            row("Generalist Adversarial And Integration Discovery — shard 2", "graph:E-A"),
        ]
        errors = self.validate(rows).errors
        self.assertTrue(any("must use the same numbered edge partition" in error
                            for error in errors), errors)

    def test_candidate_requires_topology_membership(self) -> None:
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        for status in ("candidate", "reopened candidate"):
            with self.subTest(status=status):
                (self.root / "indexes" / "candidates.tsv").write_text(
                    f"id\tstatus\nEPW-1\t{status}\n", encoding="utf-8")
                errors = self.validate(rows).errors
                self.assertTrue(any(
                    "omits candidate edge membership: EPW-1" in error
                    for error in errors
                ), errors)

    def test_amended_candidate_remains_a_legal_topology_reference(self) -> None:
        (self.root / "indexes" / "candidates.tsv").write_text(
            "id\tstatus\nEPW-1\twithdraw by EPW-A1\n", encoding="utf-8")
        (self.root / "indexes" / "topology.tsv").write_text(
            "edge\tcandidate\nE-A\tEPW-1\nE-B\t-\n", encoding="utf-8")
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        self.assertEqual([], self.validate(rows).errors)

    def test_zero_edge_graph_uses_explicit_none_scope(self) -> None:
        (self.root / "indexes" / "topology.tsv").write_text(
            "edge\tcandidate\n", encoding="utf-8")
        self.write_priors(scope="graph:none")
        rows = [
            row("Generalist Semantic And State Discovery", "graph:none"),
            row("Generalist Adversarial And Integration Discovery", "graph:none"),
        ]
        self.assertEqual([], self.validate(rows).errors)
        invalid = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        self.assertTrue(self.validate(invalid).errors)

    def test_high_from_either_generalist_requires_full_sweep(self) -> None:
        lens = "Threading And Synchronization"
        self.write_priors(semantic={lens: "high"})
        base = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        errors = self.validate(base).errors
        self.assertTrue(any("requires specialist:full" in error for error in errors), errors)
        base.append(row(lens, "specialist:full; graph:E-A,E-B"))
        self.assertEqual([], self.validate(base).errors)

    def test_one_medium_requires_probe_but_allows_conservative_full(self) -> None:
        lens = "Ownership And Blink Lifecycle"
        self.write_priors(adversarial={lens: "medium"})
        base = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        errors = self.validate(base).errors
        self.assertTrue(any("requires specialist:probe" in error for error in errors), errors)
        for mode in ("probe", "full"):
            with self.subTest(mode=mode):
                routed_rows = base + [row(lens, f"specialist:{mode}; graph:E-A,E-B")]
                self.assertEqual([], self.validate(routed_rows).errors)

    def test_positive_trigger_overrides_low_priors(self) -> None:
        lens = "Network Semantics"
        self.write_priors()
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
        ]
        report = VALIDATOR.Report()
        VALIDATOR.validate_plan(
            self.root,
            {"T1": {
                "surface": lens,
                "discovery_triggers": "NET hard",
                "graph_scope": "graph:E-A",
            }},
            rows,
            True,
            report,
        )
        self.assertTrue(any("positive NET trigger T1 requires" in error
                            for error in report.errors), report.errors)

    def test_positive_trigger_rejects_unrelated_full_sweep(self) -> None:
        lens = "Network Semantics"
        self.write_priors()
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
            row(lens, "specialist:full; graph:E-B"),
        ]
        triggers = {"T1": {
            "surface": lens,
            "discovery_triggers": "NET hard",
            "graph_scope": "graph:E-A",
        }}
        report = VALIDATOR.Report()
        VALIDATOR.validate_plan(self.root, triggers, rows, True, report)
        self.assertTrue(any("coverage of graph:E-A" in error
                            for error in report.errors), report.errors)
        rows[-1] = row(lens, "specialist:full; graph:E-A")
        report = VALIDATOR.Report()
        VALIDATOR.validate_plan(self.root, triggers, rows, True, report)
        self.assertEqual([], report.errors)

    def test_escalated_probe_requires_same_work_full_continuation(self) -> None:
        lens = "Ownership And Blink Lifecycle"
        self.write_priors(semantic={lens: "medium"})
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
            row(lens, "specialist:probe; graph:E-A,E-B"),
        ]
        (self.root / "ledger").mkdir()
        (self.root / "ledger" / "OBL.md").write_text("""# Probe

## Specialist probe outcome

| lens | graph scope | result | evidence | remaining scope |
| --- | --- | --- | --- | --- |
| Ownership And Blink Lifecycle | graph:E-A,E-B | escalate | ownership crosses callback at foo.cc:20 | specialist:full; graph:E-A,E-B |
""", encoding="utf-8")
        errors = self.validate(rows).errors
        self.assertTrue(any("lacks a later complete same-work-ID" in error
                            for error in errors), errors)
        brief = self.root / "briefs" / "OBL-attempt-2.md"
        brief.parent.mkdir()
        brief.write_text(
            "# Continuation\n\nScope: specialist:full; graph:E-A,E-B\n",
            encoding="utf-8",
        )
        header = "work_id\tattempt\tstate\tremaining_scope\tdepends_on\tbrief\tartifact\n"
        (self.root / "orchestration.tsv").write_text(
            header
            + f"OBL\t1\tpartial\tspecialist:full; graph:E-A,E-B\t-\t-\t{self.root / 'ledger' / 'OBL.md'}\n"
            + f"OBL\t2\tcomplete\t-\t-\t{brief}\t{self.root / 'ledger' / 'OBL.md'}\n",
            encoding="utf-8",
        )
        errors = self.validate(rows).errors
        self.assertTrue(any("lacks a later complete same-work-ID" in error
                            for error in errors), errors)
        (self.root / "orchestration.tsv").write_text(
            header
            + f"OBL\t1\tpartial\tspecialist:full; graph:E-A,E-B\t-\t-\t{self.root / 'ledger' / 'OBL.md'}\n"
            + f"OBL\t2\tcomplete\t-\tOBL:1\t{brief}\t{self.root / 'ledger' / 'OBL.md'}\n",
            encoding="utf-8",
        )
        self.assertEqual([], self.validate(rows).errors)

    def test_nested_probe_ledger_is_reported_as_noncanonical(self) -> None:
        lens = "Ownership And Blink Lifecycle"
        self.write_priors(semantic={lens: "medium"})
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
            row(lens, "specialist:probe; graph:E-A,E-B"),
        ]
        nested = self.root / "ledger" / "nested" / "OBL.md"
        nested.parent.mkdir(parents=True)
        nested.write_text("# misplaced probe\n", encoding="utf-8")
        errors = self.validate(rows).errors
        self.assertTrue(any("specialist probe ledger is noncanonical" in error
                            for error in errors), errors)

    def test_clean_probe_cannot_hide_candidate(self) -> None:
        lens = "Ownership And Blink Lifecycle"
        self.write_priors(semantic={lens: "medium"})
        rows = [
            row("Generalist Semantic And State Discovery", "graph:all-inventory-edges"),
            row("Generalist Adversarial And Integration Discovery", "graph:all-inventory-edges"),
            row(lens, "specialist:probe; graph:E-A,E-B"),
        ]
        (self.root / "ledger").mkdir()
        (self.root / "ledger" / "OBL.md").write_text("""# Probe

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |
| OBL-1 | callback can outlive owner | foo.cc:20 | owner resets at foo.cc:30 | CL-introduced | | candidate |

## Specialist probe outcome

| lens | graph scope | result | evidence | remaining scope |
| --- | --- | --- | --- | --- |
| Ownership And Blink Lifecycle | graph:E-A,E-B | clean | owner path inspected at foo.cc:20-30 | — |
""", encoding="utf-8")
        errors = self.validate(rows).errors
        self.assertTrue(any("clean probe has a candidate" in error
                            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
