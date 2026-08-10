#!/usr/bin/env python3

import json
import hashlib
import pathlib
import tempfile
import unittest

import campaign
import mechanism_evidence as evidence


def artifact(root, name):
    path = pathlib.Path(root) / name
    path.write_text(name)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def raw(root, variant="baseline", cycles=(1000, 1000, 1000), totals=None):
    root = pathlib.Path(root)
    totals = totals or (100000, 100000, 100000)
    log = root / f"counter-{variant}-{cycles[0]}-{totals[0]}.log"
    lines = []
    for block, (value, total) in enumerate(zip(cycles, totals), 1):
        for suite in range(32):
            row = {
                "schema_version": 1,
                "block": block,
                "group": f"rep0|suite-{suite}",
                "calls": 100 if suite == 0 else 0,
                "applicable_calls": 80 if suite == 0 else 0,
                "exclusive_cycles": value if suite == 0 else 0,
                "avoidable_cycles": value // 2 if suite == 0 else 0,
                "total_scored_cycles": total,
                "probe_overhead_cycles": 100,
                "time_enabled": 1000000,
                "time_running": 1000000,
                "multiplexed_samples": 0,
                "invalid_reads": 0,
                "unavailable_reads": 0,
                "uncalibrated_scopes": 0,
                "nested_violations": 0,
                "thread_affinity_violations": 0,
                "perf_open_errno": 0,
            }
            lines.append(evidence.ROW_PREFIX + json.dumps(row))
    log.write_text("\n".join(lines) + "\n")
    log_ref = {
        "path": str(log.resolve()),
        "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
    }
    value = {
        "schema_version": 1,
        "opportunity_id": 7,
        "mechanism_key": "style/cache-match",
        "profile_id": "profile-2",
        "variant": variant,
        "interval_kind": "exact-scored",
        "score_scope": {
            "classification": "score-critical",
            "metric_model": "speedometer-geomean-v1",
            "trace_artifact": artifact(root, "trace"),
        },
        "build": {
            "sha": variant,
            "build_id": "build",
            "gn_args_sha256": "gn",
            "toolchain_id": "clang",
            "pgo_profile_sha256": "pgo",
            "provenance_artifact": artifact(root, f"provenance-{variant}"),
        },
        "instrumentation": {
            "revision": "probe-1",
            "aa_overhead_pct": 0.2,
            "aa_artifact": artifact(root, "probe-aa"),
        },
        "minimum_running_ratio": 0.99,
        "counter_logs": [log_ref],
        "ingested_by": "mechanism_evidence.py/v1",
    }
    value["blocks"] = evidence.build_blocks_from_logs(
        value["counter_logs"], value["minimum_running_ratio"]
    )
    return value


class MechanismEvidenceTest(unittest.TestCase):
    def test_sizing_is_computed_from_raw_avoidable_cycles(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = pathlib.Path(tmp) / "raw.json"
            out = pathlib.Path(tmp) / "sizing.json"
            raw_path.write_text(json.dumps(raw(tmp)))
            self.assertEqual(0, evidence.main([
                "summarize", "--raw", str(raw_path), "--out", str(out)
            ]))
            result = json.loads(out.read_text())
            self.assertTrue(result["gate_pass"])
            self.assertAlmostEqual(0.5 / 32, result["ceiling_pct"])
            self.assertEqual(300, result["calls"])

    def test_candidate_requires_positive_paired_lower_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = pathlib.Path(tmp) / "baseline.json"
            candidate = pathlib.Path(tmp) / "candidate.json"
            out = pathlib.Path(tmp) / "candidate-evidence.json"
            baseline.write_text(json.dumps(raw(tmp)))
            candidate.write_text(json.dumps(raw(tmp, "candidate", (500, 500, 500))))
            self.assertEqual(0, evidence.main([
                "compare", "--kind", "candidate", "--baseline", str(baseline),
                "--variant", str(candidate), "--out", str(out)
            ]))
            result = json.loads(out.read_text())
            self.assertTrue(result["gate_pass"])
            self.assertAlmostEqual(50.0, result["exclusive_cycle_reduction_pct"])
            self.assertAlmostEqual(0.0, result["total_scored_cycle_change_pct"])

    def test_candidate_reports_moved_work_without_denominator_inflation(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = pathlib.Path(tmp) / "baseline.json"
            candidate = pathlib.Path(tmp) / "candidate.json"
            out = pathlib.Path(tmp) / "candidate-evidence.json"
            baseline.write_text(json.dumps(raw(tmp)))
            candidate.write_text(json.dumps(raw(
                tmp, "candidate", (500, 500, 500), (102000, 102000, 102000)
            )))
            self.assertEqual(0, evidence.main([
                "compare", "--kind", "candidate", "--baseline", str(baseline),
                "--variant", str(candidate), "--out", str(out)
            ]))
            result = json.loads(out.read_text())
            self.assertAlmostEqual(0.5 / 32, result["net_scored_cycle_share_saved_pct"])
            self.assertAlmostEqual(2.0, result["total_scored_cycle_change_pct"])
            self.assertTrue(result["moved_work_warning"])

    def test_typed_blocks_cannot_replace_emitted_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = pathlib.Path(tmp) / "raw.json"
            out = pathlib.Path(tmp) / "sizing.json"
            value = raw(tmp)
            value["blocks"][0]["groups"][0]["exclusive_cycles"] = 1
            raw_path.write_text(json.dumps(value))
            self.assertEqual(1, evidence.main([
                "summarize", "--raw", str(raw_path), "--out", str(out)
            ]))

    def test_counter_quality_failure_is_rejected_at_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = raw(tmp)
            log_path = pathlib.Path(metadata["counter_logs"][0]["path"])
            lines = log_path.read_text().splitlines()
            row = json.loads(lines[0].split(evidence.ROW_PREFIX, 1)[1])
            row["thread_affinity_violations"] = 1
            lines[0] = evidence.ROW_PREFIX + json.dumps(row)
            log_path.write_text("\n".join(lines) + "\n")
            for field in ("blocks", "counter_logs", "ingested_by"):
                metadata.pop(field)
            metadata_path = pathlib.Path(tmp) / "metadata.json"
            out = pathlib.Path(tmp) / "raw-ingested.json"
            metadata_path.write_text(json.dumps(metadata))
            self.assertEqual(1, evidence.main([
                "ingest", "--metadata", str(metadata_path), "--log", str(log_path),
                "--out", str(out)
            ]))

    def test_outer_interval_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = pathlib.Path(tmp) / "raw.json"
            out = pathlib.Path(tmp) / "sizing.json"
            value = raw(tmp)
            value["interval_kind"] = "outer-suite"
            raw_path.write_text(json.dumps(value))
            self.assertEqual(1, evidence.main([
                "summarize", "--raw", str(raw_path), "--out", str(out)
            ]))

    def test_campaign_recomputes_artifact_instead_of_trusting_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = pathlib.Path(tmp) / "raw.json"
            out = pathlib.Path(tmp) / "sizing.json"
            raw_path.write_text(json.dumps(raw(tmp)))
            self.assertEqual(0, evidence.main([
                "summarize", "--raw", str(raw_path), "--out", str(out)
            ]))
            opp = {
                "id": 7,
                "mechanism_key": "style/cache-match",
                "profile_id": "profile-2",
            }
            loaded, _ = campaign.load_gate_evidence(out, opp=opp, phase="sizing")
            loaded["ceiling_pct"] = 99
            out.write_text(json.dumps(loaded))
            with self.assertRaises(campaign.CampaignError):
                campaign.load_gate_evidence(out, opp=opp, phase="sizing")


if __name__ == "__main__":
    unittest.main()
