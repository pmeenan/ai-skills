#!/usr/bin/env python3

import json
import hashlib
import os
import pathlib
import subprocess
import tempfile
import unittest

import campaign
import mechanism_evidence as evidence


def artifact(root, name, content=None):
    path = pathlib.Path(root) / name
    path.write_text(content if content is not None else name)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def instrumented_trees(root, variant):
    root = pathlib.Path(root)
    repo = root / "evidence-repo"
    if not repo.exists():
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    blob = subprocess.run(
        ["git", "-C", str(repo), "hash-object", "-w", "--stdin"],
        input=f"int Work_{variant} = 1;\n", text=True,
        check=True, capture_output=True,
    ).stdout.strip()
    with tempfile.TemporaryDirectory() as index_dir:
        env = {**os.environ, "GIT_INDEX_FILE": str(pathlib.Path(index_dir) / "index")}
        subprocess.run(
            ["git", "-C", str(repo), "read-tree", "--empty"], check=True, env=env
        )
        subprocess.run(
            ["git", "-C", str(repo), "update-index", "--add", "--cacheinfo",
             f"100644,{blob},engine.cc"],
            check=True, env=env,
        )
        product_tree = subprocess.run(
            ["git", "-C", str(repo), "write-tree"], check=True, env=env,
            capture_output=True, text=True,
        ).stdout.strip()
    patch_ref = artifact(root, "instrumentation.patch", (
        "diff --git a/sp3_probe.txt b/sp3_probe.txt\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/sp3_probe.txt\n"
        "@@ -0,0 +1 @@\n"
        "+probe\n"
    ))
    transform_value = evidence.reduce_instrumentation_transform(
        repo, product_tree, patch_ref
    )
    transform_ref = artifact(
        root, f"transform-{variant}.json", json.dumps(transform_value, sort_keys=True)
    )
    return product_tree, transform_value["instrumented_tree"], patch_ref, transform_ref


def raw(
    root, variant="baseline", cycles=(1000, 1100, 950), totals=None,
    text_sha=None,
):
    root = pathlib.Path(root)
    totals = totals or (100000, 103000, 98000)
    product_tree, source_tree, patch_ref, transform_ref = instrumented_trees(
        root, variant
    )
    browser_sha = f"browser-{variant}"
    build_output = artifact(root, f"build-{variant}.log", "ninja: build complete\n")
    build_executable = artifact(root, f"autoninja-{variant}", "#!/bin/sh\n")
    provenance_value = {
        "schema_version": 2,
        "runner": evidence.PROVENANCE_RUNNER,
        "sha": variant,
        "source_tree": source_tree,
        "product_tree": product_tree,
        "build_id": "build",
        "browser_sha256": browser_sha,
        "executable_text_sha256": text_sha or f"text-{variant}",
        "gn_args_sha256": "gn",
        "toolchain_id": "clang",
        "pgo_profile_sha256": "pgo",
        "skill_tree_sha256": "test-only",
        "host_name": "perfbox",
        "host_boot_id": "12345678-1234-1234-1234-123456789abc",
        "kernel_release": "6.8.0-test",
        "cpu_model": "Test CPU",
        "resolved_browser": str(root / "out/perf_instrumented/chrome"),
        "required_release_args": {
            "is_official_build": "true",
            "is_debug": "false",
            "chrome_pgo_phase": "2",
            "use_thin_lto": "true",
        },
        "build_receipt": {
            "command": ["autoninja", "-C", str(root / "out/perf_instrumented"), "chrome"],
            "executable": build_executable,
            "source_tree": source_tree,
            "host_name": "perfbox",
            "host_boot_id": "12345678-1234-1234-1234-123456789abc",
            "started_at": "2026-08-10T00:00:00+00:00",
            "finished_at": "2026-08-10T00:01:00+00:00",
            "exit_code": 0,
            "output": build_output,
        },
    }
    provenance = artifact(
        root,
        f"provenance-{variant}",
        json.dumps(provenance_value),
    )
    aa_source = artifact(root, f"probe-aa-source-{variant}", json.dumps({
        "schema_version": 1,
        "runner": "run_ab_benchmark.py/v3",
        "mode": "ab2",
        "stories": "all",
        "blocks": 32,
        "seed": 123456,
        "schedule": ["ABBA", "BAAB"] * 16,
        "block_details": [
            {"block": block, "pattern": "ABBA" if block % 2 else "BAAB",
             "a_scores": [100.0, 100.1],
             "b_scores": [99.8, 99.9]}
            for block in range(1, 33)
        ],
        "build_provenance": {
            "a": {"browser_sha256": "uninstrumented"},
            "b": {"browser_sha256": browser_sha},
        },
    }))
    aa_value = evidence.reduce_instrumentation_aa(
        json.loads(pathlib.Path(aa_source["path"]).read_text()), aa_source
    )
    aa = artifact(root, f"probe-aa-{variant}", json.dumps(aa_value, sort_keys=True))
    trace = artifact(root, "trace", json.dumps({
        "traceEvents": [{"name": "mechanism", "ts": 1}],
        "metadata": {"interval_kind": "exact-scored"},
    }))
    log_refs = []
    capture_refs = []
    story = "Charts-chartjs"
    repetitions = 5
    for block, (value, total) in enumerate(zip(cycles, totals), 1):
        nonce = f"{block:032x}"
        log = root / f"counter-{variant}-{block}.log"
        lines = []
        browser_lines = []
        for rep in range(repetitions):
            row = {
                "schema_version": 1,
                "block": block,
                "capture_nonce": nonce,
                "group": f"rep{rep}|{story}",
                "pid": 2000 + block,
                "tid": 3000 + block,
                "process_type": "renderer",
                "emitted_monotonic_raw_ns": 2000 + rep,
                "calls": 100 if rep == 0 else 0,
                "applicable_calls": 80 if rep == 0 else 0,
                "exclusive_cycles": value if rep == 0 else 0,
                "avoidable_cycles": value // 2 if rep == 0 else 0,
                "total_scored_cycles": total + rep * 101,
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
            emitted = evidence.ROW_PREFIX + json.dumps(row, sort_keys=True)
            lines.append(emitted)
            browser_lines.extend([
                f"[SP3_SCORE_TIME] {story}.Test-start: 1.0",
                emitted,
                f"[SP3_SCORE_TIME] {story}.Test-sync-end: 2.0",
            ])
        log.write_text("\n".join(lines) + "\n")
        browser_log = root / f"browser.{variant}.{block}.log"
        browser_log.write_text("\n".join(browser_lines) + "\n")
        log_ref = {
            "path": str(log.resolve()),
            "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        manifest = root / f"capture-{variant}-{block}.json"
        manifest.write_text(json.dumps({
            "schema_version": 1,
            "runner": evidence.CAPTURE_RUNNER,
            "capture_nonce": nonce,
            "block": block,
            "variant": variant,
            "opportunity_id": 7,
            "mechanism_key": "style/cache-match",
            "profile_id": "profile-2",
            "stories": story,
            "repetitions": repetitions,
            "score_suites": [story],
            "exit_code": 0,
            "started_monotonic_raw_ns": 1000,
            "finished_monotonic_raw_ns": 10000,
            "capture_environment": {
                "host_name": "perfbox",
                "host_boot_id": "12345678-1234-1234-1234-123456789abc",
                "kernel_release": "6.8.0-test",
                "cpu_model": "Test CPU",
                "perf_event_paranoid": "1",
                "virtualization": "none",
            },
            "harness": {
                "crossbench_revision": "a" * 40,
                "crossbench_cb": {"path": "/test/cb.py", "sha256": "b" * 64},
                "vpython3": {"path": "/test/vpython3", "sha256": "c" * 64},
                "depot_tools_revision": "d" * 40,
                "depot_tools_origin": (
                    "https://chromium.googlesource.com/chromium/tools/depot_tools.git"
                ),
            },
            "skill_tree_sha256": "test-only",
            "command": [
                "vpython3", "./third_party/crossbench/cb.py",
                "speedometer_3.0", f"--stories={story}",
                f"--repetitions={repetitions}",
            ],
            "build": provenance_value,
            "counter_log": log_ref,
            "browser_logs": [{
                "path": str(browser_log.resolve()),
                "sha256": hashlib.sha256(browser_log.read_bytes()).hexdigest(),
            }],
        }))
        log_refs.append(log_ref)
        capture_refs.append({
            "path": str(manifest.resolve()),
            "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        })
    value = {
        "schema_version": evidence.SCHEMA_VERSION,
        "opportunity_id": 7,
        "mechanism_key": "style/cache-match",
        "profile_id": "profile-2",
        "target_story": story,
        "variant": variant,
        "interval_kind": "exact-scored",
        "score_scope": {
            "classification": "score-critical",
            "metric_model": "speedometer-story-v1",
            "min_avoidable_pct_floor": 0.0,
            "trace_artifact": trace,
        },
        "build": {
            **provenance_value,
            "transform_artifact": transform_ref,
            "provenance_artifact": provenance,
        },
        "instrumentation": {
            "revision": patch_ref["sha256"],
            "aa_overhead_pct": aa_value["overhead_pct"],
            "aa_artifact": aa,
        },
        "minimum_running_ratio": 0.99,
        "capture_manifests": capture_refs,
        "counter_logs": log_refs,
        "ingested_by": evidence.INGEST_RUNNER,
    }
    nonce_by_log = {
        ref["path"]: f"{block:032x}"
        for block, ref in enumerate(log_refs, 1)
    }
    suites_by_log = {
        ref["path"]: {story}
        for ref in log_refs
    }
    value["blocks"] = evidence.build_blocks_from_logs(
        value["counter_logs"],
        value["minimum_running_ratio"],
        nonce_by_log=nonce_by_log,
        suites_by_log=suites_by_log,
    )
    return value


class MechanismEvidenceTest(unittest.TestCase):
    def test_scaffold_binds_default_avoidable_floor(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "metadata.json"
            self.assertEqual(0, evidence.main([
                "scaffold", "--opp", "7",
                "--mechanism-key", "style/cache-match",
                "--profile-id", "profile-2",
                "--target-story", "TodoMVC-React",
                "--variant", "baseline", "--out", str(out),
            ]))
            metadata = json.loads(out.read_text())
            self.assertEqual(
                evidence.DEFAULT_MIN_AVOIDABLE_PCT,
                metadata["score_scope"]["min_avoidable_pct_floor"],
            )

    def test_calibrate_aa_is_recomputed_from_runner_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = raw(tmp)
            aa_path = pathlib.Path(value["instrumentation"]["aa_artifact"]["path"])
            aa = json.loads(aa_path.read_text())
            out = pathlib.Path(tmp) / "recomputed-aa.json"
            self.assertEqual(0, evidence.main([
                "calibrate-aa", "--manifest", aa["source_manifest"]["path"],
                "--out", str(out),
            ]))
            self.assertEqual(aa, json.loads(out.read_text()))

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
            self.assertGreater(result["ceiling_pct"], 0)
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
            self.assertGreater(result["exclusive_cycle_reduction_pct"], 40.0)
            self.assertAlmostEqual(0.0, result["total_scored_cycle_change_pct"])

    def test_candidate_reports_moved_work_without_denominator_inflation(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = pathlib.Path(tmp) / "baseline.json"
            candidate = pathlib.Path(tmp) / "candidate.json"
            out = pathlib.Path(tmp) / "candidate-evidence.json"
            baseline.write_text(json.dumps(raw(tmp)))
            candidate.write_text(json.dumps(raw(
                tmp, "candidate", (500, 520, 470), (102000, 105000, 100000)
            )))
            self.assertEqual(0, evidence.main([
                "compare", "--kind", "candidate", "--baseline", str(baseline),
                "--variant", str(candidate), "--out", str(out)
            ]))
            result = json.loads(out.read_text())
            self.assertGreater(result["net_scored_cycle_share_saved_pct"], 0)
            self.assertGreater(result["total_scored_cycle_change_pct"], 1.0)
            self.assertTrue(result["moved_work_warning"])

    def test_candidate_requires_changed_executable_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline = pathlib.Path(tmp) / "baseline.json"
            candidate = pathlib.Path(tmp) / "candidate.json"
            baseline.write_text(json.dumps(raw(tmp)))
            candidate.write_text(json.dumps(raw(
                tmp, "candidate", (500, 500, 500), text_sha="text-baseline"
            )))
            self.assertEqual(1, evidence.main([
                "compare", "--kind", "candidate", "--baseline", str(baseline),
                "--variant", str(candidate),
                "--out", str(pathlib.Path(tmp) / "candidate-evidence.json"),
            ]))

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
            capture_path = pathlib.Path(metadata["capture_manifests"][0]["path"])
            capture = json.loads(capture_path.read_text())
            capture["counter_log"]["sha256"] = hashlib.sha256(
                log_path.read_bytes()
            ).hexdigest()
            capture_path.write_text(json.dumps(capture))
            for field in ("blocks", "counter_logs", "capture_manifests", "ingested_by"):
                metadata.pop(field)
            metadata_path = pathlib.Path(tmp) / "metadata.json"
            out = pathlib.Path(tmp) / "raw-ingested.json"
            metadata_path.write_text(json.dumps(metadata))
            self.assertEqual(1, evidence.main([
                "ingest", "--metadata", str(metadata_path),
                "--capture-manifest", str(capture_path),
                "--out", str(out)
            ]))

    def test_capture_manifest_cannot_hide_changed_browser_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = raw(tmp)
            capture_path = pathlib.Path(value["capture_manifests"][0]["path"])
            capture = json.loads(capture_path.read_text())
            browser_path = pathlib.Path(capture["browser_logs"][0]["path"])
            browser_path.write_text(browser_path.read_text().replace(
                "[SP3_SCORE_TIME]", "[FAKE_SCORE_TIME]"
            ))
            capture["browser_logs"][0]["sha256"] = hashlib.sha256(
                browser_path.read_bytes()
            ).hexdigest()
            capture_path.write_text(json.dumps(capture))
            value["capture_manifests"][0]["sha256"] = hashlib.sha256(
                capture_path.read_bytes()
            ).hexdigest()
            raw_path = pathlib.Path(tmp) / "raw.json"
            raw_path.write_text(json.dumps(value))
            self.assertEqual(1, evidence.main([
                "summarize", "--raw", str(raw_path),
                "--out", str(pathlib.Path(tmp) / "out.json"),
            ]))

    def test_hand_authored_log_without_capture_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            metadata = raw(tmp)
            log_path = metadata["counter_logs"][0]["path"]
            for field in ("blocks", "counter_logs", "capture_manifests", "ingested_by"):
                metadata.pop(field)
            metadata_path = pathlib.Path(tmp) / "metadata.json"
            metadata_path.write_text(json.dumps(metadata))
            with self.assertRaises(SystemExit):
                evidence.parser().parse_args([
                    "ingest", "--metadata", str(metadata_path), "--log", log_path,
                    "--out", str(pathlib.Path(tmp) / "out.json"),
                ])

    def test_zero_variance_synthetic_blocks_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            value = raw(tmp, totals=(100000, 100000, 100000))
            raw_path = pathlib.Path(tmp) / "raw.json"
            raw_path.write_text(json.dumps(value))
            self.assertEqual(1, evidence.main([
                "summarize", "--raw", str(raw_path),
                "--out", str(pathlib.Path(tmp) / "sizing.json"),
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
