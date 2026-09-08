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
            self.substantive_transcript(transcripts[role], report)
            report["what_this_frontier_establishes"] = (
                "Two independent exact-window captures with complete inventories."
            )
            for name in report["checks"]:
                report["checks"][name] = True
                report["check_evidence"][name] = evidence_maker(name)
            reports[role].write_text(json.dumps(report))

        transcripts = {}
        for role in ("skeptic", "adversary"):
            transcript = self.dir / f"{role}.jsonl"
            self.substantive_transcript(transcript, json.loads(reports[role].read_text()))
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

    # ---------------- decomposition closes by count ----------------

    def write_packet(self, name, *, story=STORY, applicable, repeat, site="probe/site"):
        path = self.dir / "evidence" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": 1, "kind": "redundancy-evidence",
            "site": site, "target_story": story, "repetitions": 4,
            "calls_total": 400, "calls_per_repetition_mean": 100.0,
            "applicable_fraction": applicable, "repeat_fraction": repeat,
            "distinct_inputs_mean": 50.0, "distinct_overflow": False,
            "measured_avoidable_fraction_upper": max(applicable, repeat),
            "sources": [{"path": "/nowhere/probe.log", "sha256": "0" * 64}],
        }))
        return {"path": f"evidence/{name}.json", "sha256": campaign.sha256_file(path)}

    def test_rows_above_floor_close_by_count_not_prose(self):
        config = {"share_floor_pct": 0.1,
                  "calibration": {"story_mde_pct": {STORY: 0.5}}}  # floor 1.0%
        unbounded = self.write_packet("always-applicable", applicable=1.0, repeat=0.0)
        tight = self.write_packet("tight", applicable=0.02, repeat=0.01)
        other_story = self.write_packet("other", story="Other", applicable=0.0, repeat=0.0)

        def row(anchor, disposition, **extra):
            return {"anchor": anchor, "disposition": disposition, **extra}

        def run(paths, shares):
            return campaign.enforce_measured_dispositions(
                paths, shares, config, 0.1, STORY, self.dir)

        # Prose only: refused with instructions.
        with self.assertRaisesRegex(campaign.CampaignError, "without a bound count"):
            run([row("Shape", "mandatory")], {1: 5.0})
        # A packet whose applicable predicate is always true bounds nothing.
        with self.assertRaisesRegex(campaign.CampaignError, "cannot close as mandatory"):
            run([row("Shape", "mandatory", redundancy_evidence=unbounded)], {1: 5.0})
        # A packet from another story is refused.
        with self.assertRaisesRegex(campaign.CampaignError, "not the path's target story"):
            run([row("Shape", "no-qualifying-mechanism", redundancy_evidence=other_story)], {1: 5.0})
        # share x supported below floor closes, and records the arithmetic.
        paths = [row("Shape", "mandatory", redundancy_evidence=tight)]
        self.assertEqual({1}, run(paths, {1: 5.0}))
        bound = paths[0]["measured_bound"]
        self.assertAlmostEqual(0.1, bound["avoidable_share_upper_pct"])
        self.assertEqual(1.0, bound["qualification_floor_pct"])
        # Below the floor nothing is required.
        self.assertEqual(set(), run([row("Small", "mandatory")], {1: 0.4}))
        # A wrapper delegates to its dominant counted descendant.
        paths = [row("Layout", "mandatory", wrapper_of=2),
                 row("Shape", "mandatory", redundancy_evidence=tight)]
        self.assertEqual({2}, run(paths, {1: 5.5, 2: 5.0}))
        self.assertEqual([1, 2], paths[0]["measured_bound"]["wrapper_chain"])
        # ... but not to a minor descendant, a mechanism row, or an unbound row.
        with self.assertRaisesRegex(campaign.CampaignError, "less than 80%"):
            run([row("Layout", "mandatory", wrapper_of=2),
                 row("Shape", "mandatory", redundancy_evidence=tight)], {1: 5.0, 2: 2.0})
        with self.assertRaisesRegex(campaign.CampaignError, "covered-by that mechanism"):
            run([row("Layout", "mandatory", wrapper_of=2),
                 row("Shape", "novel", mechanism_key="fonts/reuse")], {1: 5.0, 2: 4.5})
        with self.assertRaisesRegex(campaign.CampaignError, "binds no packet"):
            run([row("Layout", "mandatory", wrapper_of=2),
                 row("Shape", "mandatory")], {1: 1.1, 2: 0.9})
        # A chain of gradually smaller rows is not descent: every hop is
        # measured against the row that started the chain.
        with self.assertRaisesRegex(campaign.CampaignError, "started this chain"):
            run([row("A", "mandatory", wrapper_of=2), row("B", "mandatory", wrapper_of=3),
                 row("C", "mandatory", wrapper_of=4), row("D", "mandatory", redundancy_evidence=tight)],
                {1: 5.0, 2: 4.2, 3: 3.5, 4: 2.9})
        with self.assertRaisesRegex(campaign.CampaignError, "loops"):
            run([row("A", "mandatory", wrapper_of=2), row("B", "mandatory", wrapper_of=1)],
                {1: 5.0, 2: 5.0})

    def test_packets_close_only_the_work_they_measured(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True)
        artifact = story_dir / "candidate_frontier.json"
        artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Layout;ShapeText;HarfBuzz 60\n"
            "main;Layout;ShapeText 20\n"
            "main;Layout;OutOfFlow 30\n"
            "main;Style;Match 40\n"
        )
        profile = {"id": "p", "capture_provenance": [{
            "capture_id": "c1",
            "story_frontiers": [{"story": STORY, "artifact": str(artifact)}],
        }]}

        def packet(name, symbol):
            path = self.dir / "evidence" / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "schema_version": 1, "kind": "redundancy-evidence", "site": name,
                "target_story": STORY, "repetitions": 2, "calls_total": 10,
                "calls_per_repetition_mean": 5.0, "applicable_fraction": 0.01,
                "repeat_fraction": 0.0, "distinct_inputs_mean": 5.0,
                "distinct_overflow": False, "measured_avoidable_fraction_upper": 0.01,
                "sources": [{"path": "/nowhere/probe.log", "sha256": "0" * 64}],
            }
            if symbol:
                data["probe_symbol"] = symbol
            path.write_text(json.dumps(data))
            return {"path": f"evidence/{name}.json", "sha256": campaign.sha256_file(path)}

        shape = packet("shape", "ShapeText")
        rows = [
            {"anchor": "HarfBuzz", "disposition": "mandatory", "redundancy_evidence": shape},
            {"anchor": "Layout", "disposition": "mandatory", "redundancy_evidence": shape},
        ]
        # A descendant of the probe and the probe's own caller both qualify.
        campaign.enforce_packet_relevance(rows, [(1, rows[0]), (2, rows[1])], profile, STORY, self.dir)
        self.assertEqual(1.0, rows[0]["packet_relevance"])
        self.assertEqual(1.0, rows[1]["packet_relevance"])
        # An unrelated phase does not.
        unrelated = [{"anchor": "Match", "disposition": "mandatory", "redundancy_evidence": shape}]
        with self.assertRaisesRegex(campaign.CampaignError, "shares 0% of its samples"):
            campaign.enforce_packet_relevance(unrelated, [(1, unrelated[0])], profile, STORY, self.dir)
        # A packet without probe_symbol cannot be bound above the floor.
        blind = packet("blind", None)
        rows = [{"anchor": "HarfBuzz", "disposition": "mandatory", "redundancy_evidence": blind}]
        with self.assertRaisesRegex(campaign.CampaignError, "probe_symbol"):
            campaign.enforce_packet_relevance(rows, [(1, rows[0])], profile, STORY, self.dir)

    def test_candidates_bind_a_packet_whatever_their_layer(self):
        packet = self.write_packet("site", applicable=0.3, repeat=0.7)
        with mock.patch.object(campaign, "test_bypass_active", return_value=False):
            # A layer-3 label does not exempt a candidate from the count.
            for disposition in ("novel", "known"):
                item = {"anchor": "Root", "disposition": disposition,
                        "investigation_layer": 3, "mechanism_key": "x/y"}
                with self.assertRaisesRegex(campaign.CampaignError, "whatever its layer"):
                    campaign.bind_redundancy_evidence(item, STORY, 0.2, self.dir)
            # The claim is bounded by the number the row's hypothesis names.
            item = {"anchor": "Root", "disposition": "known", "investigation_layer": 3,
                    "mechanism_key": "x/y", "redundancy_evidence": packet}
            with self.assertRaisesRegex(campaign.CampaignError, "'applicable' hypothesis"):
                campaign.bind_redundancy_evidence(item, STORY, 0.7, self.dir)
            campaign.bind_redundancy_evidence(item, STORY, 0.3, self.dir)
            self.assertEqual("applicable", item["packet_hypothesis"])
            self.assertEqual(0.3, item["redundancy_summary"]["supported_avoidable_fraction"])
            item["packet_hypothesis"] = "repeat"
            campaign.bind_redundancy_evidence(item, STORY, 0.7, self.dir)
            self.assertEqual(0.7, item["redundancy_summary"]["supported_avoidable_fraction"])
            item["packet_hypothesis"] = "maybe"
            with self.assertRaisesRegex(campaign.CampaignError, "packet_hypothesis"):
                campaign.bind_redundancy_evidence(item, STORY, 0.1, self.dir)
            # A predicate that held on every call measured nothing.
            saturated = self.write_packet("saturated", applicable=1.0, repeat=0.2)
            item = {"anchor": "Root", "disposition": "novel", "investigation_layer": 1,
                    "mechanism_key": "x/z", "redundancy_evidence": saturated}
            with self.assertRaisesRegex(campaign.CampaignError, "always true"):
                campaign.bind_redundancy_evidence(item, STORY, 0.2, self.dir)
            item["packet_hypothesis"] = "repeat"
            campaign.bind_redundancy_evidence(item, STORY, 0.2, self.dir)

    def test_covered_by_rows_sit_under_the_owners_probe(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True)
        artifact = story_dir / "candidate_frontier.json"
        artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Root;Layout;ShapeText;HarfBuzz 60\n"
            "main;Root;Layout;ShapeText 20\n"
            "main;Root;Layout;OutOfFlow 30\n"
            "main;Root;Style;Match 40\n"
        )
        profile = {"id": "p", "capture_provenance": [{
            "capture_id": "c1",
            "story_frontiers": [{"story": STORY, "artifact": str(artifact)}],
        }]}
        shape = self.write_packet("shape", applicable=0.3, repeat=0.3)
        shape_packet = json.loads((self.dir / "evidence" / "shape.json").read_text())
        shape_packet["probe_symbol"] = "ShapeText"
        (self.dir / "evidence" / "shape.json").write_text(json.dumps(shape_packet))
        shape["sha256"] = campaign.sha256_file(self.dir / "evidence" / "shape.json")
        rows = [
            {"anchor": "ShapeText", "disposition": "novel", "mechanism_key": "fonts/reuse",
             "redundancy_evidence": shape},
            {"anchor": "HarfBuzz", "disposition": "covered-by", "covered_by": "fonts/reuse"},
            {"anchor": "Match", "disposition": "covered-by", "covered_by": "fonts/reuse"},
        ]
        symbols = campaign.owner_probe_symbols(rows, lambda key: None, self.dir)
        self.assertEqual({"fonts/reuse": "ShapeText"}, symbols)
        with self.assertRaisesRegex(campaign.CampaignError, "Path 3 .*only 0% of its samples sit under"):
            campaign.enforce_covered_by_probe_identity(rows, symbols, profile, STORY)
        del rows[2]
        campaign.enforce_covered_by_probe_identity(rows, symbols, profile, STORY)
        self.assertEqual(1.0, rows[1]["covered_by_probe_identity"])
        # The area root as owner: every row shares its anchor, but without a
        # probe the root covers nothing.
        root = [
            {"anchor": "Root", "disposition": "novel", "mechanism_key": "root/cache"},
            {"anchor": "Match", "disposition": "covered-by", "covered_by": "root/cache"},
        ]
        self.assertEqual({}, campaign.owner_probe_symbols(root, lambda key: None, self.dir))
        with self.assertRaisesRegex(campaign.CampaignError, "binds no packet with a probe_symbol"):
            campaign.enforce_covered_by_probe_identity(root, {}, profile, STORY)
        # A ledger-held owner contributes the probe recorded on its summary.
        ledger_owner = {"redundancy_summary": {"probe_symbol": "OutOfFlow"}}
        rows = [{"anchor": "OutOfFlow", "disposition": "covered-by", "covered_by": "layout/oof"}]
        symbols = campaign.owner_probe_symbols(rows, lambda key: ledger_owner, self.dir)
        self.assertEqual({"layout/oof": "OutOfFlow"}, symbols)
        campaign.enforce_covered_by_probe_identity(rows, symbols, profile, STORY)

    def test_novel_rows_name_the_existing_mechanism(self):
        item = {"anchor": "blink::InlineNode::PrepareLayout", "disposition": "novel"}
        with self.assertRaisesRegex(campaign.CampaignError, "existing_mechanism"):
            campaign.require_existing_mechanism(item, 1)
        item["existing_mechanism"] = "Blink already reuses shape results by string match in some cases"
        with self.assertRaisesRegex(campaign.CampaignError, "existing_mechanism"):
            campaign.require_existing_mechanism(item, 1)
        item["existing_mechanism"] = (
            "InlineNode::ShapeText reuses ShapeResults by string and font match; "
            "the probe shows 257 of 519 calls per rep still reshape unchanged text"
        )
        campaign.require_existing_mechanism(item, 1)

    def test_gate_report_registry_refuses_edited_reviews(self):
        def report(digests, task="task-skeptic"):
            path = self.dir / "skeptic.json"
            data = {"reviewer_task_id": task,
                    "artifact_digests_checked": [f"sha256:{d}" for d in digests]}
            path.write_text(json.dumps(data))
            return data, path

        data, path = report(["a" * 64])
        campaign.register_gate_report(
            self.dir, gate="decomposition", role="skeptic", report=data,
            report_path=path, subject="decomposition:#001")
        # Same report again: idempotent.
        campaign.register_gate_report(
            self.dir, gate="decomposition", role="skeptic", report=data,
            report_path=path, subject="decomposition:#001")
        registry = json.loads((self.dir / "reviews" / "gate-report-registry.json").read_text())
        self.assertEqual(1, len(registry))
        # Same task id attesting a different artifact: an edited review.
        data, path = report(["b" * 64])
        with self.assertRaisesRegex(campaign.CampaignError, "voids the review"):
            campaign.register_gate_report(
                self.dir, gate="decomposition", role="skeptic", report=data,
                report_path=path, subject="decomposition:#001")
        # Same task id and digests on another subject: also refused.
        data, path = report(["a" * 64])
        with self.assertRaisesRegex(campaign.CampaignError, "different artifact set"):
            campaign.register_gate_report(
                self.dir, gate="decomposition", role="skeptic", report=data,
                report_path=path, subject="decomposition:#002")
        # A fresh task id is a fresh review.
        data, path = report(["b" * 64], task="task-skeptic-2")
        campaign.register_gate_report(
            self.dir, gate="decomposition", role="skeptic", report=data,
            report_path=path, subject="decomposition:#001")

    def test_decompose_review_scaffold_binds_rows_and_import_requires_numbers(self):
        discovery = self.record_profile("profile-1")[0]
        ledger = campaign.Ledger(self.dir).load()
        parent = ledger.opp(discovery)
        children = self.dir / "children.json"
        children.write_text(json.dumps({
            "area_key": parent["area_key"], "profile_id": parent["profile_id"],
            "accounting_evidence": "all hotspots accounted for",
            "paths": [{
                "anchor": "Style recalc", "disposition": "mandatory",
                "share_pct": 1.2, "evidence": "prose",
                "work_refs": [{**ref, "accounting": "primary"}
                              for ref in parent["expected_work_refs"]],
            }],
        }))
        reports = {}
        for role in ("skeptic", "adversary"):
            out = self.dir / f"decomp-{role}.json"
            self.assertEqual(0, self.run_cmd(
                "decompose-review-scaffold", "--opp", str(discovery),
                "--role", role, "--children", str(children), "--out", str(out)))
            reports[role] = out
        scaffold = json.loads(reports["skeptic"].read_text())
        self.assertEqual("decomposition", scaffold["gate"])
        self.assertEqual(
            set(campaign.DECOMPOSITION_GATE_CHECKS["skeptic"]), set(scaffold["checks"]))
        rows = scaffold["bound_inputs"]["rows_at_or_above_floor"]
        self.assertEqual([1], [row["path"] for row in rows])
        self.assertEqual("mandatory", rows[0]["disposition"])
        digests = [d.removeprefix("sha256:") for d in scaffold["artifact_digests_checked"]]
        self.assertEqual(campaign.sha256_file(children), digests[0])

        def fill(role, evidence_maker):
            report = json.loads(reports[role].read_text())
            report["verdict"] = "PASS"
            report["reviewer_task_id"] = f"task-{role}"
            transcript = self.dir / f"{role}-transcript.md"
            report["transcript_ref"] = str(transcript)
            self.substantive_transcript(transcript, report)
            report["why_this_proves_real_speedup"] = (
                "Every row above the floor closes by a count from the target story.")
            for name in report["checks"]:
                report["checks"][name] = True
                report["check_evidence"][name] = evidence_maker(name)
            reports[role].write_text(json.dumps(report))

        namespace = argparse.Namespace(
            gate_skeptic=str(reports["skeptic"]), gate_adversary=str(reports["adversary"]),
            gate_skeptic_transcript=None, gate_adversary_transcript=None)
        with mock.patch.object(campaign, "test_bypass_active", return_value=False):
            with self.assertRaisesRegex(campaign.CampaignError, "not PASS"):
                campaign.validate_gate_challenges(
                    namespace, gate="decomposition", artifact_digests=digests,
                    campaign_dir=self.dir, subject="decomposition:#001")
            for role in ("skeptic", "adversary"):
                fill(role, lambda name: f"opened the rows for {name}; they looked mandatory")
            with self.assertRaisesRegex(campaign.CampaignError, "cite an artifact and a number"):
                campaign.validate_gate_challenges(
                    namespace, gate="decomposition", artifact_digests=digests,
                    campaign_dir=self.dir, subject="decomposition:#001")
            for role in ("skeptic", "adversary"):
                fill(role, lambda name: f"children.json row 1 for {name}: 1.2% share vs 0.1% floor, packet 400 calls")
            verified = campaign.validate_gate_challenges(
                namespace, gate="decomposition", artifact_digests=digests,
                campaign_dir=self.dir, subject="decomposition:#001")
        self.assertEqual({"skeptic", "adversary"}, {r["role"] for r in verified})
        registry = json.loads((self.dir / "reviews" / "gate-report-registry.json").read_text())
        self.assertEqual({"task-skeptic", "task-adversary"},
                         {entry["reviewer_task_id"] for entry in registry})

    # ---------------- reviewer transcripts and covered-by ----------------

    @staticmethod
    def substantive_transcript(path, report, extra=""):
        """A transcript that shows the work: every attested digest, every
        check name, and enough text to be a review rather than a verdict."""
        lines = [f"# {report.get('role')} review transcript", extra]
        for digest in report.get("artifact_digests_checked", []):
            lines.append(f"opened artifact {digest}: 3 rows read")
        for name in report.get("checks", {}):
            lines.append(f"check {name}: opened the bound artifact and read 12 numbers")
        lines.append("notes " * 700)
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_reviewer_transcript_must_show_the_work(self):
        report = {"role": "skeptic", "artifact_digests_checked": ["sha256:" + "a" * 64],
                  "checks": {"accounting_bijective": True, "rows_above_floor_bound": True}}
        stub = self.dir / "decomp-1-skeptic.md"
        stub.write_text("Verdict: PASS\n")
        with self.assertRaisesRegex(campaign.CampaignError, "bytes"):
            campaign.require_substantive_transcript(
                "skeptic", "decomposition", report, str(stub), stub)
        padded = self.dir / "decomp-1-skeptic.md"
        padded.write_text("x" * 5000)
        with self.assertRaisesRegex(campaign.CampaignError, "never mentions"):
            campaign.require_substantive_transcript(
                "skeptic", "decomposition", report, str(padded), padded)
        padded.write_text("x" * 5000 + "aaaaaaaaaaaa")
        with self.assertRaisesRegex(campaign.CampaignError, "does not show the work"):
            campaign.require_substantive_transcript(
                "skeptic", "decomposition", report, str(padded), padded)
        good = self.substantive_transcript(padded, report)
        campaign.require_substantive_transcript(
            "skeptic", "decomposition", report, str(good), good)
        # The supplied file has to be the one the report names.
        other = self.dir / "decomp-2-skeptic.md"
        other.write_text(good.read_text())
        with self.assertRaisesRegex(campaign.CampaignError, "bind the transcript the report"):
            campaign.require_substantive_transcript(
                "skeptic", "decomposition", report, str(good), other, supplied=str(other))

    def test_covered_by_rows_share_samples_with_their_owner(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True)
        artifact = story_dir / "candidate_frontier.json"
        artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Layout;ShapeText;HarfBuzz 60\n"
            "main;Layout;ShapeText 20\n"
            "main;Layout;OutOfFlow 30\n"
            "main;Style;Match 40\n"
        )
        profile = {"id": "p", "capture_provenance": [{
            "capture_id": "c1",
            "story_frontiers": [{"story": STORY, "artifact": str(artifact)}],
        }]}
        owners = {"fonts/reuse": "ShapeText"}
        good = [
            {"anchor": "ShapeText", "disposition": "novel", "mechanism_key": "fonts/reuse"},
            {"anchor": "HarfBuzz", "disposition": "covered-by", "covered_by": "fonts/reuse"},
        ]
        campaign.enforce_covered_by_sample_identity(good, owners, profile, STORY)
        self.assertEqual(1.0, good[1]["covered_by_sample_identity"])
        # A caller that holds other work is not the same samples.
        wrapper = [{"anchor": "Layout", "disposition": "covered-by", "covered_by": "fonts/reuse"}]
        with self.assertRaisesRegex(campaign.CampaignError, "only 73% of its samples"):
            campaign.enforce_covered_by_sample_identity(wrapper, owners, profile, STORY)
        # An unrelated hotspot never shares a stack.
        unrelated = [{"anchor": "Match", "disposition": "covered-by", "covered_by": "fonts/reuse"}]
        with self.assertRaisesRegex(campaign.CampaignError, "only 0% of its samples"):
            campaign.enforce_covered_by_sample_identity(unrelated, owners, profile, STORY)
        absent = [{"anchor": "Nowhere", "disposition": "covered-by", "covered_by": "fonts/reuse"}]
        with self.assertRaisesRegex(campaign.CampaignError, "no samples"):
            campaign.enforce_covered_by_sample_identity(absent, owners, profile, STORY)
        with self.assertRaisesRegex(campaign.CampaignError, "none resolves"):
            campaign.enforce_covered_by_sample_identity(good, owners, {"id": "p"}, STORY)

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
