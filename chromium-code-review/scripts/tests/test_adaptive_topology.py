#!/usr/bin/env python3

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "validate-review-dir.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("review_validator", SCRIPT)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

INDEX_SPEC = importlib.util.spec_from_file_location("scope_index_builder", SCRIPT.parent / "build-review-indexes.py")
assert INDEX_SPEC and INDEX_SPEC.loader
INDEXER = importlib.util.module_from_spec(INDEX_SPEC)
INDEX_SPEC.loader.exec_module(INDEXER)


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
        for candidate_id in ("GSS-1", "GAI2-1"):
            for status in ("candidate", "reopened candidate"):
                with self.subTest(candidate_id=candidate_id, status=status):
                    (self.root / "indexes" / "candidates.tsv").write_text(
                        f"id\tstatus\n{candidate_id}\t{status}\n", encoding="utf-8")
                    errors = self.validate(rows).errors
                    self.assertTrue(any(
                        f"omits candidate edge membership: {candidate_id}" in error
                        for error in errors
                    ), errors)
        # Targeted discovery threads (e.g. EPW-1) do not emit topology deltas.
        (self.root / "indexes" / "candidates.tsv").write_text(
            "id\tstatus\nEPW-1\tcandidate\n", encoding="utf-8")
        self.assertEqual([], self.validate(rows).errors)

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

    def test_lens_scopes_survive_worker_index_and_collection_gates(self) -> None:
        (self.root / "ledger").mkdir()
        (self.root / "indexes" / "topology.tsv").write_text(
            "edge\tcandidate\nE-A\t-\nE-B\t-\nE-C\t-\n", encoding="utf-8")
        for worker in ("GSS1", "GAI1"):
            text = """# Discovery

## Compliance matrix

| question | answer | evidence |
| --- | --- | --- |
| all assigned edges inspected? | yes | foo.cc:10 |

## Candidate rows

| id | claim | location | evidence / hypothesis | origin | severity | status |
| --- | --- | --- | --- | --- | --- | --- |

## Complexity graph delta

| edge | status | evidence | candidate | next obligation |
| --- | --- | --- | --- | --- |
| E-A | resolved | foo.cc:10 | - | - |
| E-B | resolved | foo.cc:11 | - | - |
| E-C | resolved | foo.cc:12 | - | - |

## Specialist escalation assessments

| lens | graph scope | likelihood | signals | counterevidence |
| --- | --- | --- | --- | --- |
"""
            for lens in VALIDATOR.SPECIALIST_LENSES:
                scope, level = "graph:none", "low"
                if lens == "Threading And Synchronization":
                    scope = "graph:E-A,E-B" if worker == "GSS1" else "graph:E-B,E-C"
                    level = "medium"
                elif lens == "Network Semantics":
                    scope = "graph:E-A" if worker == "GSS1" else "graph:E-C"
                    level = "high" if worker == "GSS1" else "low"
                text += f"| {lens} | {scope} | {level} | foo.cc:10 signal | foo.cc:12 excluded edges have guards |\n"
            if worker == "GSS1":
                text = text.replace(
                    "Threading And Synchronization | graph:E-A,E-B |",
                    "Threading And Synchronization | graph:E-A,E-B,E-C |",
                )
                text += """
## Amendments

| amendment | target | operation | fields | evidence | attempt |
| --- | --- | --- | --- | --- | --- |
| GSS1-A1 | assessment:Threading And Synchronization | replace-fields | {"graph scope":"graph:E-A,E-B"} | foo.cc:12 | 2 |
"""
            path = self.root / "ledger" / f"{worker}.md"
            path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT.parent / "validate-worker-artifact.py"), str(self.root), str(path)],
                capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
        priors = INDEXER.specialist_prior_rows(self.root, {"E-A", "E-B", "E-C"})
        self.assertEqual(20, len(priors))
        prior_path = self.root / "indexes" / "specialist-priors.tsv"
        def write_rows(values):
            with prior_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, delimiter="\t")
                writer.writerow(("lens", "graph_scope", "assessor", "likelihood", "signals", "counterevidence", "citations", "source"))
                writer.writerows(values)
        write_rows(priors)
        base = [
            row("Generalist Semantic And State Discovery — shard 1", "graph:E-A,E-B,E-C"),
            row("Generalist Adversarial And Integration Discovery — shard 1", "graph:E-A,E-B,E-C"),
            row("Network Semantics", "specialist:full; graph:E-A"),
            row("Threading And Synchronization — shard 1", "specialist:full; graph:E-B"),
            row("Threading And Synchronization — shard 2", "specialist:probe; graph:E-A,E-C"),
        ]
        self.assertEqual([], self.validate(base).errors)
        missing_probe = base[:-1] + [row("Threading And Synchronization — shard 2", "specialist:probe; graph:E-A")]
        self.assertTrue(any("requires specialist:probe" in e and "E-C" in e for e in self.validate(missing_probe).errors))
        weak_overlap = base[:3] + [row("Threading And Synchronization", "specialist:probe; graph:E-A,E-B,E-C")]
        self.assertTrue(any("requires specialist:full" in e and "E-B" in e for e in self.validate(weak_overlap).errors))
        missing_high = [r for r in base if r["roster entry"] != "Network Semantics"]
        self.assertTrue(any("requires specialist:full" in e and "E-A" in e for e in self.validate(missing_high).errors))
        write_rows(priors[:-1])
        self.assertTrue(any("missing assessment" in e for e in self.validate(base).errors))
        invalid = [r[:] for r in priors]
        invalid[0][1] = "graph:E-FOREIGN"
        write_rows(invalid)
        self.assertTrue(any("unassigned graph scope" in e for e in self.validate(base).errors))
        invalid = [r[:] for r in priors]
        invalid[0][5] = "no risk"
        write_rows(invalid)
        self.assertTrue(any("without cited counterevidence" in e for e in self.validate(base).errors))

    def test_empty_lens_scopes_do_not_merge_independent_shards(self) -> None:
        self.write_priors(scope="graph:none")
        path = self.root / "indexes" / "specialist-priors.tsv"
        original = path.read_text(encoding="utf-8").splitlines()
        lines = [original[0]]
        for shard in (1, 2):
            lines.extend(line.replace("GSS.md", f"GSS{shard}.md").replace("GAI.md", f"GAI{shard}.md") for line in original[1:])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        rows = [row(f"{name} — shard {shard}", scope)
                for name in VALIDATOR.GENERALIST_ROSTER
                for shard, scope in ((1, "graph:E-A"), (2, "graph:E-B"))]
        self.assertEqual([], self.validate(rows).errors)
        path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
        self.assertTrue(any("missing assessment" in e for e in self.validate(rows).errors))

    def test_plan_scope_amendment_closes_indexed_routing_obligation(self) -> None:
        lens = "Ownership And Blink Lifecycle"
        self.write_priors(semantic={lens: "high"})
        text = """# Plan

| roster entry | scope | status | tier | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Generalist Semantic And State Discovery | graph:all-inventory-edges | spawn | frontier | D01 | — | — |
| Generalist Adversarial And Integration Discovery | graph:all-inventory-edges | spawn | frontier | D01 | — | — |

## Graph routing continuation — PLAN attempt 2

| roster entry | scope | status | tier | batch | subagent | outcome |
| --- | --- | --- | --- | --- | --- | --- |
| Ownership And Blink Lifecycle | specialist:full; graph:E-A | spawn | frontier | D02 | — | — |
"""
        def effective_rows(value):
            parsed = list(INDEXER.tables(value, "plan.md"))
            return [r for _, header, rows in parsed if "roster entry" in header for r in rows]
        errors = self.validate(effective_rows(text)).errors
        self.assertTrue(any("requires specialist:full" in e and "E-B" in e for e in errors), errors)
        text += """
## Amendments

| amendment | target | operation | replacement / reason |
| --- | --- | --- | --- |
| COLFIX-A1 | Ownership And Blink Lifecycle | replace-fields | {"scope":"specialist:full; graph:E-A,E-B"} |
"""
        (self.root / "plan.md").write_text(text, encoding="utf-8")
        self.assertEqual([], self.validate(effective_rows(text)).errors)
        report = VALIDATOR.Report()
        rows, tier_seen = VALIDATOR.effective_plan_roster(self.root, report)
        self.assertTrue(tier_seen)
        self.assertEqual([], report.errors)
        self.assertEqual([], self.validate(rows).errors)

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
