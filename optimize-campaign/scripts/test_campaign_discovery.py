#!/usr/bin/env python3
"""Tests for discovery repairs: calibration gate, profile retraction,
root-substitution recurrence, profile-gate review evidence and capture
provenance auditing."""

import argparse
import json
import os
import pathlib
import unittest
from unittest import mock

import campaign
import test_campaign


STORY = test_campaign.TEST_STORY


def load_tests(loader, tests, pattern):
    """Only collect the tests defined here, not the inherited fixtures."""
    suite = unittest.TestSuite()
    for name in sorted(DiscoveryRepairTest.__dict__):
        if name.startswith("test_"):
            suite.addTest(DiscoveryRepairTest(name))
    return suite


class DiscoveryRepairTest(test_campaign.CampaignTest):

    # ---------------- helpers ----------------

    def write_substitution_captures(self, profile_id, *, support_pairing=True):
        """Two captures that root the same cloning samples at a parent in
        one capture and at its child in the other (the Lit case)."""
        summaries = []
        prefix = f"story:{STORY}/"
        roots = {
            f"{profile_id}-1": ("blink::Clone", "blink::importNode", 1.99),
            f"{profile_id}-2": ("blink::importNode", "blink::Clone", 1.88),
        }
        for capture_id, (root, other, share) in roots.items():
            # Fractions in the artifact, percentages in the inventory; derive
            # both from the same floats so the importer's re-derivation matches.
            root_fraction = share / 100
            other_fraction = (share - 0.01) / 100
            local_results = self.dir / capture_id
            artifact = (
                local_results / "analysis" / "stories" / STORY
                / "candidate_frontier.json"
            )
            artifact.parent.mkdir(parents=True)
            frontier = [
                {
                    "entry_key": prefix + "symbol:blink::Style",
                    "kind": "symbol", "name": "blink::Style",
                    "marginal_share": 0.05, "related_hotspots": [],
                },
                {
                    "entry_key": prefix + f"symbol:{root}",
                    "kind": "symbol", "name": root,
                    "marginal_share": root_fraction, "related_hotspots": [],
                },
            ]
            alternatives = []
            if support_pairing:
                alternatives.append({
                    "kind": "symbol", "name": other,
                    "entry_key": prefix + f"symbol:{other}",
                    "inclusive_share": other_fraction,
                    "assigned_frontier_entry": prefix + f"symbol:{root}",
                })
            artifact.write_text(json.dumps({
                "quality": {"accepted": True},
                "selection": {
                    "inventory_complete": True,
                    "min_inclusive_share": 0.001,
                    "min_marginal_share": 0.001,
                    "metric_weighting": "speedometer-story-v1",
                    "story": STORY,
                },
                "frontier": frontier,
                "overlapping_alternatives": alternatives,
            }))
            inventory = [
                {
                    "entry_key": prefix + "symbol:blink::Style",
                    "work_items": [{
                        "hotspot_key": "@root",
                        "semantic_key": "symbol:blink::Style",
                        "measured_share_pct": 5.0,
                    }],
                },
                {
                    "entry_key": prefix + f"symbol:{root}",
                    "work_items": [{
                        "hotspot_key": "@root",
                        "semantic_key": f"symbol:{root}",
                        "measured_share_pct": root_fraction * 100,
                    }] + ([{
                        "hotspot_key": "alternative:" + prefix + f"symbol:{other}",
                        "semantic_key": f"symbol:{other}",
                        "measured_share_pct": other_fraction * 100,
                    }] if support_pairing else []),
                },
            ]
            summaries.append({
                "mode": "profile",
                "benchmark": "speedometer3",
                "metric_weighting": "speedometer-story-v1",
                "capture_id": capture_id,
                "sha": "deadbeef",
                "quality_rejected": False,
                "enable_features": "Speedometer3Optimizations",
                "stories": "all",
                "repetitions": 2,
                "share_floor_pct": 0.1,
                "inventory_complete": True,
                "analyzer_min_inclusive_share": 0.001,
                "analyzer_min_marginal_share": 0.001,
                "frontier_entries": [item["entry_key"] for item in inventory],
                "frontier_inventory": inventory,
                "frontier_count": len(inventory),
                "local_results": str(local_results),
                "remote_perf_data": f"/remote/{capture_id}/perf_sampling.data",
                "story_frontiers": [{
                    "story": STORY,
                    "artifact": str(artifact),
                    "samples": 40000,
                    "nominal_samples_at_floor": 120.0,
                    "accepted": True,
                    "frontier_count": len(inventory),
                }],
            })
        path = self.dir / f"captures-{profile_id}.json"
        path.write_text(json.dumps(summaries))
        return path

    def profile_main(self, *argv):
        """Run `profile` without the fixture's --allow-uncalibrated."""
        return campaign.main(["--dir", str(self.dir), "profile", *argv])

    # ---------------- calibration gate ----------------

    def test_profile_requires_calibration_unless_explicitly_allowed(self):
        areas = self.dir / "areas.json"
        captures = self.write_capture_summaries("p1", "deadbeef", [
            {"area_key": "style-recalc", "marginal_share_pct": 0.6},
        ])
        manifest = self.reconciliation([{
            "area_key": "style-recalc", "anchor": "Style recalc",
            "marginal_share_pct": 0.6,
            "source_refs": [
                {"capture_id": "p1-1", "entry_key": f"story:{STORY}/symbol:style-recalc"},
                {"capture_id": "p1-2", "entry_key": f"story:{STORY}/symbol:style-recalc"},
            ],
        }])
        areas.write_text(json.dumps(manifest))
        common = [
            "--id", "p1", "--sha", "deadbeef", "--areas", str(areas),
            "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository",
        ]
        self.assertEqual(1, self.profile_main(*common))
        self.assertEqual([], self.ledger().get("profile_runs", []))
        self.assertEqual(0, self.profile_main(*common, "--allow-uncalibrated"))
        run = self.ledger()["profile_runs"][-1]
        self.assertTrue(run["uncalibrated"])
        self.assertIsNone(run["calibration_epoch"])
        self.assertIn("uncalibrated", self.status_text().lower())

    # ---------------- retraction ----------------

    def test_profile_retract_removes_untouched_discoveries(self):
        ids = self.record_profile("p1", area_count="2")
        self.assertEqual(2, len(ids))
        self.assertEqual(1, self.run_cmd("profile-retract", "--id", "p1", "--note", "x"))
        self.assertEqual(0, self.run_cmd(
            "profile-retract", "--id", "p1",
            "--note", "recurrence rule dropped a root-substituted area"))
        ledger = self.ledger()
        self.assertEqual([], ledger["profile_runs"])
        self.assertEqual([], [
            opp for opp in ledger["opportunities"] if opp["id"] in ids
        ])
        retraction = ledger["profile_retractions"][-1]
        self.assertEqual("p1", retraction["id"])
        self.assertEqual(sorted(ids), sorted(retraction["removed_opportunity_ids"]))
        # Ids are never reused and the retracted id cannot come back.
        self.assertEqual(1, self.profile_main(
            "--id", "p1", "--sha", "deadbeef",
            "--areas", str(self.dir / "areas-p1.json"),
            "--capture-summaries", str(self.dir / "captures-p1.json"),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository", "--allow-uncalibrated"))
        new_ids = self.record_profile("p2", area_count="1")
        self.assertGreater(min(new_ids), max(ids))

    def test_profile_retract_refuses_after_a_discovery_advanced(self):
        ids = self.record_profile("p1", area_count="1")
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(ids[0]), "--to", "investigating"))
        self.assertEqual(1, self.run_cmd(
            "profile-retract", "--id", "p1", "--note", "too late to retract"))
        self.assertEqual(1, len(self.ledger()["profile_runs"]))

    # ---------------- root substitution ----------------

    def test_scaffold_pairs_root_substitution_and_import_accepts_it(self):
        captures = self.write_substitution_captures("sub")
        manifest = self.dir / "sub-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(manifest)))
        scaffolded = json.loads(manifest.read_text())
        self.assertEqual([], scaffolded["source_exclusions"])
        paired = [
            area for area in scaffolded["areas"]
            if area.get("recurrence", {}).get("kind") == "root-substitution"
        ]
        self.assertEqual(1, len(paired))
        area = paired[0]
        self.assertEqual(
            {"sub-1", "sub-2"}, {ref["capture_id"] for ref in area["source_refs"]}
        )
        self.assertEqual(
            {f"story:{STORY}/symbol:blink::Clone", f"story:{STORY}/symbol:blink::importNode"},
            {ref["entry_key"] for ref in area["source_refs"]},
        )
        self.assertAlmostEqual(1.935, area["marginal_share_pct"], places=3)
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "sub", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        discoveries = [
            opp for opp in self.ledger()["opportunities"]
            if opp["kind"] == "discovery"
        ]
        self.assertEqual(2, len(discoveries))
        cloning = next(
            opp for opp in discoveries if "Clone" in opp["anchor"]
            or "importNode" in opp["anchor"]
        )
        self.assertEqual(
            {"symbol:blink::Clone", "symbol:blink::importNode"},
            {ref["semantic_key"] for ref in cloning["expected_work_refs"]},
        )

    def test_unsupported_root_substitution_is_excluded_and_rejected(self):
        captures = self.write_substitution_captures("nosub", support_pairing=False)
        manifest = self.dir / "nosub-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(manifest)))
        scaffolded = json.loads(manifest.read_text())
        self.assertEqual(
            {"not-recurrent"},
            {item["category"] for item in scaffolded["source_exclusions"]},
        )
        self.assertEqual(2, len(scaffolded["source_exclusions"]))
        # A hand-claimed pairing without inventory support is refused.
        forged = {
            "areas": [area for area in scaffolded["areas"]] + [{
                "area_key": "todomvc-test-cloning",
                "anchor": f"{STORY}/blink::Clone",
                "marginal_share_pct": 1.9,
                "disposition": "discover",
                "recurrence": {"kind": "root-substitution"},
                "source_refs": [
                    {"capture_id": "nosub-1", "entry_key": f"story:{STORY}/symbol:blink::Clone"},
                    {"capture_id": "nosub-2", "entry_key": f"story:{STORY}/symbol:blink::importNode"},
                ],
            }],
            "source_exclusions": [],
            "parked_mechanisms": scaffolded["parked_mechanisms"],
        }
        manifest.write_text(json.dumps(forged))
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "nosub", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    # ---------------- profile-gate review evidence ----------------

    def test_profile_review_scaffold_is_refused_until_filled_with_numbers(self):
        captures = self.write_capture_summaries("rev", "deadbeef", [
            {"area_key": "style-recalc", "marginal_share_pct": 0.6},
        ])
        areas = self.dir / "rev-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(areas)))
        reports = {}
        for role in ("skeptic", "adversary"):
            out = self.dir / f"profile-{role}.json"
            self.assertEqual(0, self.run_cmd(
                "profile-review-scaffold", "--role", role,
                "--areas", str(areas), "--capture-summaries", str(captures),
                "--out", str(out)))
            reports[role] = out
        scaffold = json.loads(reports["skeptic"].read_text())
        self.assertEqual("profile", scaffold["gate"])
        self.assertEqual("CHALLENGE", scaffold["verdict"])
        self.assertEqual(
            set(campaign.PROFILE_GATE_CHECKS["skeptic"]), set(scaffold["checks"])
        )
        digests = [d.removeprefix("sha256:") for d in scaffold["artifact_digests_checked"]]

        def fill(role, evidence_maker):
            report = json.loads(reports[role].read_text())
            report["verdict"] = "PASS"
            report["reviewer_task_id"] = f"task-{role}"
            report["transcript_ref"] = f"/nowhere/{role}.jsonl"
            report["what_this_frontier_establishes"] = (
                "Two independent exact-window captures with complete inventories."
            )
            for name in report["checks"]:
                report["checks"][name] = True
                report["check_evidence"][name] = evidence_maker(name)
            reports[role].write_text(json.dumps(report))

        transcripts = {}
        for role in ("skeptic", "adversary"):
            transcript = self.dir / f"{role}-transcript.jsonl"
            transcript.write_text('{"event": "reviewed"}\n')
            transcripts[role] = transcript

        def namespace(with_transcripts):
            fields = {
                "gate_skeptic": str(reports["skeptic"]),
                "gate_adversary": str(reports["adversary"]),
            }
            if with_transcripts:
                fields["gate_skeptic_transcript"] = str(transcripts["skeptic"])
                fields["gate_adversary_transcript"] = str(transcripts["adversary"])
            return argparse.Namespace(**fields)

        with mock.patch.object(campaign, "test_bypass_active", return_value=False):
            # Unfilled scaffold: not PASS.
            with self.assertRaisesRegex(campaign.CampaignError, "not PASS"):
                campaign.validate_gate_challenges(
                    namespace(True), gate="profile", artifact_digests=digests,
                    campaign_dir=self.dir,
                )
            # Filled, but evidence carries no number.
            for role in ("skeptic", "adversary"):
                fill(role, lambda name: f"opened the artifact for {name} and it looked fine to me")
            with self.assertRaisesRegex(campaign.CampaignError, "cite an artifact and a number"):
                campaign.validate_gate_challenges(
                    namespace(True), gate="profile", artifact_digests=digests,
                    campaign_dir=self.dir,
                )
            # Same sentence reused across checks.
            for role in ("skeptic", "adversary"):
                fill(role, lambda name: "captures-rev.json shows 2 captures at 120 samples")
            with self.assertRaisesRegex(campaign.CampaignError, "reuses one evidence"):
                campaign.validate_gate_challenges(
                    namespace(True), gate="profile", artifact_digests=digests,
                    campaign_dir=self.dir,
                )
            # Proper evidence but no reachable transcript.
            for role in ("skeptic", "adversary"):
                fill(role, lambda name: f"captures-rev.json: {name} read 120.0 samples and 2 captures")
            with self.assertRaisesRegex(campaign.CampaignError, "does not resolve"):
                campaign.validate_gate_challenges(
                    namespace(False), gate="profile", artifact_digests=digests,
                    campaign_dir=self.dir,
                )
            verified = campaign.validate_gate_challenges(
                namespace(True), gate="profile", artifact_digests=digests,
                campaign_dir=self.dir,
            )
        self.assertEqual({"skeptic", "adversary"}, {r["role"] for r in verified})
        for record in verified:
            copy = pathlib.Path(record["transcript_copy"]["path"])
            self.assertTrue(copy.is_file())
            self.assertEqual(self.dir / "reviews" / "transcripts", copy.parent)

    # ---------------- capture provenance audit ----------------

    def test_capture_provenance_verifies_every_story_artifact(self):
        self.record_profile("prov", area_count="1")
        capture = self.ledger()["profile_runs"][-1]["capture_provenance"][0]
        self.assertIn("story_frontiers", capture)
        self.assertNotIn("artifact", capture)
        self.assertEqual([], campaign.verify_capture_provenance(capture))
        artifact = pathlib.Path(capture["story_frontiers"][0]["artifact"])
        artifact.write_text(artifact.read_text() + "\n")
        problems = campaign.verify_capture_provenance(capture)
        self.assertTrue(any("analyzer artifact changed" in p for p in problems))
        self.assertTrue(any("combined" in p for p in problems))

    # ---------------- lens summary ----------------

    def synthetic_lens(self, capture_ids=("l-1", "l-2"), roots=None):
        def record(entry, entry_share, descendants):
            return {
                "ownership_self": {"blink": 60.0, "jit-js": 30.0,
                                   "addressable_pct": 65.0, "handoff_pct": 33.0},
                "triggers": {"forced-style-layout": 57.0, "script-other": 30.0},
                "phases": {"text-shaping": 36.0, "layout": 4.0},
                "forced_layout_by_entry": [
                    {"entry": "element.ScrollTopAttributeSet", "inclusive_pct": 30.5},
                ],
                "v8_lens": {"noFeedback_ic_incl": 2.4, "ic_miss_runtime_v8self": 1.9},
                "binding_plumbing_self": {"blink_to_v8_self": 0.2, "v8_to_blink_self": 2.0},
                "overhead": {"perf_logging_incl": 1.3, "unknown_leaf_pct": 4.5},
                "coverage": {"frontier_inclusive_union_pct": 70.0,
                             "unexplained_addressable_pct": 3.5,
                             "addressable_pct": 65.0, "handoff_pct": 33.0},
                "nested_view": [{
                    "entry": entry, "kind": "function",
                    "inclusive_pct": entry_share, "self_pct": 0.1,
                    "descendants": descendants,
                }],
            }
        descendants = [
            {"symbol": "blink::LocalFrameView::UpdateLayout(bool)", "inclusive_pct": 55.7,
             "self_pct": 0.0, "phase": "layout", "promoted": True},
            {"symbol": "blink::InlineNode::ShapeText(x)", "inclusive_pct": 31.4,
             "self_pct": 0.5, "phase": "text-shaping"},
            {"symbol": "blink::PhysicalBoxFragment::RecalcInkOverflow()", "inclusive_pct": 7.5,
             "self_pct": 0.2, "phase": "ink-overflow", "platform_sensitivity": "font-shaping"},
            {"symbol": "void blink::", "inclusive_pct": 40.0, "self_pct": 0.0, "phase": "layout"},
            {"symbol": "blink::LineBreaker::NextLine(a)", "inclusive_pct": 0.4,
             "self_pct": 0.1, "phase": "line-breaking"},
        ]
        story_record = record("blink::Document::UpdateStyleAndLayout(blink::DocumentUpdateReason)", 57.4, descendants)
        return {
            "schema_version": 1,
            "parameters": {"top": 12, "floor_pct": 1.0},
            "captures": [
                {"capture_id": cid, "root": (roots or {}).get(cid, f"/x/{cid}")}
                for cid in capture_ids
            ],
            "stories": {STORY: {"per_capture": {cid: story_record for cid in capture_ids},
                                "mean": story_record}},
            "input_digests": {},
        }

    def test_lens_summary_promotes_own_phase_descendants_only(self):
        import campaign_lens
        summary = campaign_lens.summarize(self.synthetic_lens())
        story = summary[STORY]
        self.assertEqual(65.0, story["addressable_pct"])
        self.assertEqual(("forced-style-layout", 57.0), story["top_trigger"])
        self.assertEqual(("element.ScrollTopAttributeSet", 30.5), story["forced_entries"][0])
        promoted = [(item["symbol"], item["phase"]) for item in story["promoted"]]
        # UpdateLayout restates the entry (55.7 of 57.4) and is not promoted
        # despite the lens flag; the degenerate `void blink::` head is
        # dropped; the sub-floor line breaker is dropped.
        self.assertEqual(
            [("blink::InlineNode::ShapeText", "text-shaping"),
             ("blink::PhysicalBoxFragment::RecalcInkOverflow", "ink-overflow")],
            promoted,
        )
        self.assertEqual("font-shaping", story["promoted"][1]["platform_sensitivity"])
        nested = story["nested_entries"][0]
        self.assertEqual("blink::Document::UpdateStyleAndLayout", nested["entry"])
        self.assertNotIn("void blink::", [d["symbol"] for d in nested["descendants"]])

    def test_lens_import_matches_captures_by_id_or_resolved_root(self):
        import campaign_lens
        lens_path = self.dir / "lens.json"
        roots = {"l-1": str(self.dir / "res-1"), "l-2": str(self.dir / "res-2")}
        for path in roots.values():
            pathlib.Path(path).mkdir()
        (self.dir / "link-1").symlink_to(self.dir / "res-1")
        (self.dir / "link-2").symlink_to(self.dir / "res-2")
        lens_path.write_text(json.dumps(self.synthetic_lens(roots=roots)))
        record = campaign_lens.load_lens_for_import(lens_path, self.dir, "p9")
        self.assertTrue((self.dir / "measurements" / "lens-p9.json").is_file())
        self.assertEqual(sorted(record["capture_ids"]), ["l-1", "l-2"])
        # Different ids but the same result roots through symlinks: accepted.
        stories = campaign_lens.check_lens_matches_captures(
            record, {STORY},
            {"cap-a": str(self.dir / "link-1"), "cap-b": str(self.dir / "link-2")},
        )
        self.assertEqual([STORY], stories)
        with self.assertRaisesRegex(campaign.CampaignError, "result roots differ"):
            campaign_lens.check_lens_matches_captures(
                record, {STORY}, {"cap-a": str(self.dir / "other")},
            )
        with self.assertRaisesRegex(campaign.CampaignError, "stories do not match"):
            campaign_lens.check_lens_matches_captures(
                record, {STORY, "Other-Story"}, {"l-1": roots["l-1"], "l-2": roots["l-2"]},
            )

    def test_profile_with_lens_records_summary_and_renders_status(self):
        import campaign_lens  # noqa: F401
        areas = [{"area_key": "style-recalc", "marginal_share_pct": 0.6}]
        captures = self.write_capture_summaries("lensp", "deadbeef", areas)
        summaries = json.loads(captures.read_text())
        roots = {s["capture_id"]: s["local_results"] for s in summaries}
        lens_path = self.dir / "lensp.json"
        lens_path.write_text(json.dumps(self.synthetic_lens(
            capture_ids=tuple(roots), roots=roots)))
        manifest = self.dir / "lensp-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(manifest)))
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "lensp", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--lens", str(lens_path),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        run = self.ledger()["profile_runs"][-1]
        self.assertEqual(run["lens"]["sha256"], campaign.sha256_file(lens_path))
        self.assertIn(STORY, run["lens_summary"])
        text = self.status_text()
        self.assertIn("## Story lens", text)
        self.assertIn("RecalcInkOverflow", text)
        self.assertIn("element.ScrollTopAttributeSet", text)
        out = self.dir / "export"
        self.assertEqual(0, self.run_cmd("export-candidates", "--out", str(out)))
        exported = json.loads((out / "candidates.json").read_text())
        self.assertIn(STORY, exported["lens_summary"])
        self.assertIn("## Story coverage", (out / "candidates.md").read_text())

    def test_status_reports_source_exclusions_and_area_counts(self):
        captures = self.write_substitution_captures("stat", support_pairing=False)
        manifest = self.dir / "stat-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(manifest)))
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "stat", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        text = self.status_text()
        self.assertIn("not-recurrent", text)
        self.assertIn("blink::Clone", text)
        self.assertNotIn("eligible frontier", text)


if __name__ == "__main__":
    unittest.main()
