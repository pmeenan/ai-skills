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

    def write_packet(self, name, *, story=STORY, applicable, repeat, site="probe/site",
                     symbol=None, repetitions=4, calls=100, timed=True,
                     applicable_time=None, repeat_time=None, distinct=None,
                     ns_per_call=1000, build_id="b" * 40, timing="exclusive",
                     nested=0, patch_name="probes.patch"):
        """A packet the way the host makes one: rows in a browser log, a probe
        patch that defines the site, and redundancy_evidence.py reducing them."""
        import redundancy_evidence
        log = self.dir / "logs" / f"{name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        repeated = round(repeat * calls)
        rows = []
        for _ in range(repetitions):
            data = {
                "schema_version": 1, "site": site, "group": f"run|{story}",
                "calls": calls, "applicable_calls": round(applicable * calls),
                "distinct_inputs": calls - repeated if distinct is None else distinct,
                "repeated_inputs": repeated, "overflow": 0,
            }
            if timed:
                total_ns = calls * ns_per_call
                data.update({
                    "timed_calls": calls, "total_ns": total_ns,
                    "applicable_ns": round((applicable if applicable_time is None else applicable_time) * total_ns),
                    "repeated_ns": round((repeat if repeat_time is None else repeat_time) * total_ns),
                })
            if build_id:
                data["build_id"] = build_id
            if timing:
                data["timing"] = timing
                data["nested_calls"] = nested
            rows.append(json.dumps(data))
        log.write_text("".join(f"[SP3_REDUNDANCY_ROW] {row}\n" for row in rows))
        patch = self.dir / "evidence" / patch_name
        patch.parent.mkdir(parents=True, exist_ok=True)
        existing = patch.read_text() if patch.is_file() else ""
        if f'"{site}"' not in existing:
            # Written the way a unified diff wraps a long constructor call.
            patch.write_text(existing + f'+  new RedundancyCounter(\n+      "{site}");\n')
        packet = redundancy_evidence.build_packet(
            [log], site, story, probe_symbol=symbol, patch=patch)
        path = self.dir / "evidence" / f"{name}.json"
        path.write_text(json.dumps(packet))
        return {"path": f"evidence/{name}.json", "sha256": campaign.sha256_file(path)}

    def test_packets_must_re_derive_from_their_logs(self):
        real = self.write_packet("real", applicable=0.3, repeat=0.5)
        packet_path = self.dir / "evidence" / "real.json"
        packet = json.loads(packet_path.read_text())
        campaign.verify_packet_provenance(packet, packet_path, self.dir)

        def refused(mutate, message):
            data = json.loads(packet_path.read_text())
            mutate(data)
            typed = self.dir / "evidence" / "typed.json"
            typed.write_text(json.dumps(data))
            with self.assertRaisesRegex(campaign.CampaignError, message):
                campaign.verify_packet_provenance(data, typed, self.dir)

        # Typed fractions on a real log.
        refused(lambda d: d.update(applicable_fraction=0.0, repeat_fraction=0.0),
                "not produced by redundancy_evidence.py")
        # A packet reduced before time weighting existed re-derives (and is
        # then refused for carrying no time, not for being hand-written).
        legacy = json.loads(packet_path.read_text())
        for field in campaign.PACKET_TIME_FIELDS + ("total_ns_per_repetition_mean",):
            legacy.pop(field, None)
        legacy_path = self.dir / "evidence" / "legacy.json"
        legacy_path.write_text(json.dumps(legacy))
        campaign.verify_packet_provenance(legacy, legacy_path, self.dir)
        with self.assertRaisesRegex(campaign.CampaignError, "carries no time"):
            campaign.require_time_weighted(legacy, {"anchor": "Row"})
        # A site the twin never counted, pointed at a real log.
        refused(lambda d: d.update(site="root/update"), "does not re-derive")
        # A log that is not on the host, or was replaced.
        refused(lambda d: d["sources"][0].update(path="/nowhere/probe.log"), "does not resolve")
        refused(lambda d: d["sources"][0].update(sha256="0" * 64), "digest that does not match")
        # No patch, or a patch without the site.
        refused(lambda d: d.pop("patch"), "records no probe patch")
        (self.dir / "evidence" / "other.patch").write_text('+  new RedundancyCounter("x/y");\n')
        refused(lambda d: d.update(patch="evidence/other.patch",
                                   patch_sha256=campaign.sha256_file(self.dir / "evidence" / "other.patch")),
                "defines no RedundancyCounter")
        # The row binding path runs the same check.
        item = {"anchor": "Row", "disposition": "mandatory", "redundancy_evidence": real}
        campaign.load_bound_redundancy_packet(item, STORY, self.dir, missing_message="m")
        data = json.loads(packet_path.read_text()); data["repeat_fraction"] = 0.0
        typed = self.dir / "evidence" / "typed2.json"; typed.write_text(json.dumps(data))
        item["redundancy_evidence"] = {"path": "evidence/typed2.json", "sha256": campaign.sha256_file(typed)}
        with self.assertRaisesRegex(campaign.CampaignError, "not produced by"):
            campaign.load_bound_redundancy_packet(item, STORY, self.dir, missing_message="m")

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
        # ... never to another instance of itself under another entry.
        with self.assertRaisesRegex(campaign.CampaignError, "same function under another entry"):
            run([row("Shape(int)", "mandatory", wrapper_of=2),
                 row("Shape(int)", "mandatory", redundancy_evidence=tight)], {1: 5.5, 2: 5.0})
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
            return self.write_packet(name, applicable=0.01, repeat=0.0, site=name, symbol=symbol)

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

    def test_candidates_are_bounded_by_time_not_calls(self):
        with mock.patch.object(campaign, "test_bypass_active", return_value=False):
            # A count-only packet binds nothing above the floor.
            untimed = self.write_packet("untimed", applicable=0.3, repeat=0.3, timed=False)
            item = {"anchor": "Root", "disposition": "novel", "mechanism_key": "x/y",
                    "redundancy_evidence": untimed}
            with self.assertRaisesRegex(campaign.CampaignError, "carries no time"):
                campaign.bind_redundancy_evidence(item, STORY, 0.1, self.dir)
            config = {"share_floor_pct": 0.1, "calibration": {"story_mde_pct": {STORY: 0.5}}}
            rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": untimed}]
            with self.assertRaisesRegex(campaign.CampaignError, "carries no time"):
                campaign.enforce_measured_dispositions(rows, {1: 5.0}, config, 0.1, STORY, self.dir)
            # 92% of calls skippable but 5% of the time: the claim is 5%.
            cheap = self.write_packet("cheap", applicable=0.92, repeat=0.1, applicable_time=0.05)
            item = {"anchor": "Root", "disposition": "novel", "mechanism_key": "x/y",
                    "redundancy_evidence": cheap}
            with self.assertRaisesRegex(campaign.CampaignError, "0.05 of time"):
                campaign.bind_redundancy_evidence(item, STORY, 0.5, self.dir)
            campaign.bind_redundancy_evidence(item, STORY, 0.05, self.dir)
            self.assertAlmostEqual(0.05, item["redundancy_summary"]["supported_avoidable_fraction"])
            # ... and as mandatory it closes by time: 5% of 5.0% is below the floor.
            rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": cheap}]
            self.assertEqual({1}, campaign.enforce_measured_dispositions(rows, {1: 5.0}, config, 0.1, STORY, self.dir))
            # A repeat hypothesis on a key that never varies names no input
            # (a few calls sharing one value: an object pointer) ...
            pointer = self.write_packet("pointer", applicable=0.0, repeat=0.67, distinct=1, calls=3)
            item = {"anchor": "Root", "disposition": "novel", "mechanism_key": "x/z",
                    "redundancy_evidence": pointer, "packet_hypothesis": "repeat"}
            with self.assertRaisesRegex(campaign.CampaignError, "key that never varies"):
                campaign.bind_redundancy_evidence(item, STORY, 0.6, self.dir)
            # ... but a hundred calls per step sharing one input is the finding.
            same = self.write_packet("same", applicable=0.0, repeat=0.99, distinct=1, calls=100)
            item["redundancy_evidence"] = same
            campaign.bind_redundancy_evidence(item, STORY, 0.9, self.dir)
            # The closing bound is the time bound once time is measured.
            cheap_repeat = self.write_packet("cheap-repeat", applicable=0.0, repeat=0.9, repeat_time=0.001)
            rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": cheap_repeat}]
            self.assertEqual({1}, campaign.enforce_measured_dispositions(rows, {1: 5.0}, config, 0.1, STORY, self.dir))

    def test_covered_by_rows_bind_the_nearest_probe(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True, exist_ok=True)
        artifact = story_dir / "candidate_frontier.json"
        artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Root;Lifecycle;Style;Match 40\n"
            "main;Root;Lifecycle;Layout;Box 50\n"
            "main;Root;Commit 10\n"
        )
        profile = {"id": "p", "capture_provenance": [{
            "capture_id": "c1",
            "story_frontiers": [{"story": STORY, "artifact": str(artifact)}],
        }]}
        self.write_packet("root", applicable=0.5, repeat=0.0, site="root/update", symbol="Root")
        self.write_packet("style", applicable=0.3, repeat=0.0, site="style/recalc", symbol="Style")
        self.write_packet("other-story", story="Other", applicable=0.3, repeat=0.0,
                          site="paint/walk", symbol="Layout")
        self.assertEqual({"Root", "Style"}, campaign.story_probe_symbols(self.dir, STORY))
        owners = {"root/cache": "Root"}
        probes = {"Root", "Style"}
        # Style sits between the root and Match: the root does not cover it.
        rows = [{"anchor": "Match", "disposition": "covered-by", "covered_by": "root/cache"}]
        with self.assertRaisesRegex(campaign.CampaignError, "probed function 'Style' sits between"):
            campaign.enforce_covered_by_nearest_probe(rows, owners, probes, profile, STORY)
        # The probed function itself is not covered by an ancestor either, and
        # rows sharing one anchor are each measured once (never above 100%).
        rows = [{"anchor": "Style", "disposition": "covered-by", "covered_by": "root/cache"},
                {"anchor": "Style", "disposition": "covered-by", "covered_by": "root/cache"}]
        with self.assertRaisesRegex(campaign.CampaignError, "in 100% of its samples"):
            campaign.enforce_covered_by_nearest_probe(rows, owners, probes, profile, STORY)
        # No probe between root and Box (Layout has no packet for this story): covered.
        rows = [{"anchor": "Box", "disposition": "covered-by", "covered_by": "root/cache"},
                {"anchor": "Commit", "disposition": "covered-by", "covered_by": "root/cache"}]
        campaign.enforce_covered_by_nearest_probe(rows, owners, probes, profile, STORY)
        self.assertEqual("Root", rows[0]["covered_by_nearest_probe"])

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
        shape = self.write_packet("shape", applicable=0.3, repeat=0.3, symbol="ShapeText")
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

    def test_packets_are_tied_to_their_build_and_timed_exclusively(self):
        with mock.patch.object(campaign, "test_bypass_active", return_value=False):
            config = {"share_floor_pct": 0.1, "calibration": {"story_mde_pct": {STORY: 0.5}}}
            legacy = self.write_packet("legacy", applicable=0.3, repeat=0.0, build_id=None, timing=None)
            item = {"anchor": "Root", "disposition": "novel", "mechanism_key": "x/y",
                    "redundancy_evidence": legacy}
            with self.assertRaisesRegex(campaign.CampaignError, "name no build"):
                campaign.bind_redundancy_evidence(item, STORY, 0.1, self.dir)
            rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": legacy}]
            with self.assertRaisesRegex(campaign.CampaignError, "name no build"):
                campaign.enforce_measured_dispositions(rows, {1: 5.0}, config, 0.1, STORY, self.dir)
            inclusive = self.write_packet("inclusive", applicable=0.3, repeat=0.0, timing=None)
            item["redundancy_evidence"] = inclusive
            with self.assertRaisesRegex(campaign.CampaignError, "not timed exclusively"):
                campaign.bind_redundancy_evidence(item, STORY, 0.1, self.dir)
            current = self.write_packet("current", applicable=0.3, repeat=0.0, nested=40)
            item["redundancy_evidence"] = current
            campaign.bind_redundancy_evidence(item, STORY, 0.1, self.dir)
            # One patch is one build: a second build claiming the same patch,
            # or one build claiming two patches, is refused.
            other_build = self.write_packet("other-build", applicable=0.3, repeat=0.0,
                                            build_id="c" * 40)
            paths = [
                {"anchor": "Root", "disposition": "novel", "redundancy_evidence": current},
                {"anchor": "Leaf", "disposition": "mandatory", "redundancy_evidence": other_build},
            ]
            with self.assertRaisesRegex(campaign.CampaignError, "from 2 different builds"):
                campaign.enforce_build_consistency(paths, self.dir)
            other_patch = self.write_packet("other-patch", applicable=0.3, repeat=0.0,
                                            site="probe/third", patch_name="probes-2.patch")
            paths[1]["redundancy_evidence"] = other_patch
            with self.assertRaisesRegex(campaign.CampaignError, "2 different probe patches"):
                campaign.enforce_build_consistency(paths, self.dir)
            same = self.write_packet("same-build", applicable=0.3, repeat=0.0)
            paths[1]["redundancy_evidence"] = same
            campaign.enforce_build_consistency(paths, self.dir)

    def test_probe_union_sizes_a_site_per_story(self):
        story_dir = self.dir / "results" / "analysis" / "stories"
        profile = {"id": "p", "capture_provenance": [{"capture_id": "c1", "story_frontiers": []}]}
        for story, share in (("A", 40), ("B", 5)):
            d = story_dir / story; d.mkdir(parents=True)
            (d / "candidate_frontier.json").write_text("{}")
            (d / "profile.collapsed").write_text(f"main;Root;Probe() {share}\nmain;Other() {100-share}\n")
            profile["capture_provenance"][0]["story_frontiers"].append({"story": story, "artifact": str(d / "candidate_frontier.json")})
        log = self.dir / "logs" / "union.log"; log.parent.mkdir(exist_ok=True)
        rows = []
        for story in ("A", "B"):
            rows.append(json.dumps({"schema_version": 1, "site": "x/y", "group": f"run|{story}", "calls": 100,
                                    "applicable_calls": 50, "distinct_inputs": 100, "repeated_inputs": 0, "overflow": 0,
                                    "timed_calls": 100, "total_ns": 100000, "applicable_ns": 50000, "repeated_ns": 0,
                                    "build_id": "b" * 40, "timing": "exclusive", "nested_calls": 0}))
        log.write_text("".join(f"[SP3_REDUNDANCY_ROW] {r}\n" for r in rows))
        ledger = campaign.Ledger(self.dir).load()
        ledger.data["profile_runs"] = [profile]
        ledger.data["config"]["calibration"] = {"story_mde_pct": {"A": 0.5, "B": 0.5}}
        out = campaign.probe_union_rows(ledger, [str(log)], "x/y", "Probe")
        by = {r["story"]: r for r in out}
        self.assertAlmostEqual(40.0, by["A"]["symbol_share_pct"])
        self.assertAlmostEqual(20.0, by["A"]["impact_pct"])
        self.assertTrue(by["A"]["qualifies"])
        self.assertAlmostEqual(2.5, by["B"]["impact_pct"])
        self.assertTrue(by["B"]["qualifies"])
        # A second log from another binary is not the same probe.
        other = self.dir / "logs" / "other.log"
        other.write_text("[SP3_REDUNDANCY_ROW] " + json.dumps({
            "schema_version": 1, "site": "x/y", "group": "run|C", "calls": 10, "applicable_calls": 0,
            "distinct_inputs": 10, "repeated_inputs": 0, "overflow": 0, "timed_calls": 10, "total_ns": 1000,
            "applicable_ns": 0, "repeated_ns": 0, "build_id": "c" * 40, "timing": "exclusive", "nested_calls": 0}) + "\n")
        with self.assertRaisesRegex(campaign.CampaignError, "One union, one build"):
            campaign.probe_union_rows(ledger, [str(log), str(other)], "x/y", "Probe")

    def test_a_decomposition_without_a_count_is_open_work(self):
        ledger = campaign.Ledger(self.dir).load()
        prose = {"id": 900, "kind": "discovery", "status": "decomposed", "anchor": "A()", "area_key": "a",
                 "target_story": "S", "share_pct": 40.0, "decomposition_revision": 2,
                 "path_accounting": [{"anchor": "A()", "disposition": "mandatory", "evidence": "spec says so"}]}
        counted = {"id": 901, "kind": "discovery", "status": "decomposed", "anchor": "B()", "area_key": "b",
                   "target_story": "S", "share_pct": 30.0, "decomposition_revision": 1,
                   "path_accounting": [{"anchor": "B()", "disposition": "mandatory",
                                        "redundancy_evidence": {"path": "evidence/b.json"}}]}
        small = {"id": 902, "kind": "discovery", "status": "decomposed", "anchor": "C()", "area_key": "c",
                 "target_story": "S", "share_pct": 1.0, "decomposition_revision": 1,
                 "path_accounting": [{"anchor": "C()", "disposition": "below-floor"}]}
        ledger.data["opportunities"] += [prose, counted, small]
        import unittest.mock
        ledger.data["test_only_taint"] = False
        with unittest.mock.patch.object(campaign, "test_bypass_active", return_value=False):
            self.assertTrue(ledger.decomposed_by_prose(prose))
            self.assertFalse(ledger.decomposed_by_prose(counted))
            self.assertFalse(ledger.decomposed_by_prose(small))
            self.assertIn(900, [o["id"] for o in ledger.next_candidates(50)])
            self.assertNotIn(901, [o["id"] for o in ledger.next_candidates(50)])

    def test_below_floor_is_judged_against_the_story_floor(self):
        # A row at 1.4% of a story whose floor is 2.9% (2 x MDE) is below the
        # floor even though the campaign-wide share floor is 1.0%.
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True, exist_ok=True)
        ledger = campaign.Ledger(self.dir).load()
        ledger.data["config"]["share_floor_pct"] = 1.0
        ledger.data["config"]["calibration"] = {"story_mde_pct": {STORY: 1.45}}
        floor, basis = campaign.story_floor_pct(ledger.data["config"], STORY)
        self.assertAlmostEqual(2.9, floor)
        self.assertGreater(floor, ledger.data["config"]["share_floor_pct"])

    def test_every_counter_on_a_rows_own_function_speaks(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True, exist_ok=True)
        artifact = story_dir / "candidate_frontier.json"; artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text("main;Root;Layout;Box 50\nmain;Root;Style 50\n")
        ledger = campaign.Ledger(self.dir).load()
        ledger.data["config"]["share_floor_pct"] = 1.0
        ledger.data["config"]["calibration"] = {"story_mde_pct": {STORY: 0.5}}
        # Every packet from one build: a root probe reading zero, a layout
        # probe reading half, and two sites on Style: one zero, one 0.4.
        root = self.write_packet("root", applicable=0.0, repeat=0.0, site="root/update", symbol="Root")
        layout = self.write_packet("layout", applicable=0.5, repeat=0.0, site="layout/box", symbol="Layout")
        style_a = self.write_packet("style-a", applicable=0.0, repeat=0.0, site="style/within", symbol="Style")
        style_b = self.write_packet("style-b", applicable=0.4, repeat=0.0, site="style/across", symbol="Style")
        ref = lambda p: dict(p)
        cfg = ledger.data["config"]
        # A layout row bound to the root's packet: its own function is counted.
        rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": ref(root)},
                {"anchor": "Layout", "disposition": "mandatory", "redundancy_evidence": ref(root)}]
        bound = [(1, rows[0]), (2, rows[1])]
        with self.assertRaisesRegex(campaign.CampaignError, "itself a probed function.*binds"):
            campaign.enforce_own_counters(rows, {1: 40.0, 2: 20.0}, cfg, 1.0, STORY, self.dir, bound)
        # Bound to its own packet but mandatory at 20% x 0.5: refused.
        rows[1]["redundancy_evidence"] = ref(layout)
        with self.assertRaisesRegex(campaign.CampaignError, "Every counter on the function speaks"):
            campaign.enforce_own_counters(rows, {1: 40.0, 2: 20.0}, cfg, 1.0, STORY, self.dir, bound)
        # Known at the packet's fraction: fine.
        rows[1].update({"disposition": "known", "mechanism_key": "layout/cache", "estimated_avoidable_fraction": 0.5})
        campaign.enforce_own_counters(rows, {1: 40.0, 2: 20.0}, cfg, 1.0, STORY, self.dir, bound)
        # Two sites on Style: closing on the zero one is refused by the other.
        rows = [{"anchor": "Style", "disposition": "mandatory", "redundancy_evidence": ref(style_a)}]
        with self.assertRaisesRegex(campaign.CampaignError, "site 'style/across' on the same function"):
            campaign.enforce_own_counters(rows, {1: 30.0}, cfg, 1.0, STORY, self.dir, [(1, rows[0])])
        rows[0].update({"disposition": "known", "mechanism_key": "style/cache", "estimated_avoidable_fraction": 0.4,
                        "redundancy_evidence": ref(style_b)})
        campaign.enforce_own_counters(rows, {1: 30.0}, cfg, 1.0, STORY, self.dir, [(1, rows[0])])
        self.assertEqual(["style/across", "style/within"], rows[0]["own_counters"])
        # A site that ran in the story but was never reduced with a symbol.
        log = self.dir / "logs" / "root.log"
        log.write_text(log.read_text() + "[SP3_REDUNDANCY_ROW] " + json.dumps({
            "schema_version": 1, "site": "paint/unnamed", "group": f"run|{STORY}", "calls": 3,
            "applicable_calls": 0, "distinct_inputs": 3, "repeated_inputs": 0, "overflow": 0,
            "timed_calls": 3, "total_ns": 300, "applicable_ns": 0, "repeated_ns": 0,
            "build_id": "b" * 40, "timing": "exclusive", "nested_calls": 0}) + "\n")
        rows = [{"anchor": "Root", "disposition": "mandatory", "redundancy_evidence": ref(root)}]
        with self.assertRaisesRegex(campaign.CampaignError, r"never reduced.*\['paint/unnamed'\]"):
            campaign.enforce_sites_named(rows, [(1, rows[0])], STORY, self.dir)
        self.assertEqual({"root/update": "Root", "layout/box": "Layout", "style/within": "Style", "style/across": "Style"},
                         campaign.build_site_symbols(self.dir, "b" * 40))

    def test_nested_mechanisms_are_marked_not_additive(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / "S"
        story_dir.mkdir(parents=True, exist_ok=True)
        artifact = story_dir / "candidate_frontier.json"; artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Recalc(int);Collect(int) 40\nmain;Recalc(int) 20\nmain;Layout(int) 40\n")
        ledger = campaign.Ledger(self.dir).load()
        ledger.data["profile_runs"] = [{"id": "p", "capture_provenance": [{"capture_id": "c1",
            "story_frontiers": [{"story": "S", "artifact": str(artifact)}]}]}]
        opps = [{"id": 1, "kind": "mechanism", "mechanism_key": "css/recalc", "anchor": "Recalc(int)", "target_story": "S"},
                {"id": 2, "kind": "mechanism", "mechanism_key": "css/collect", "anchor": "Collect(int)", "target_story": "S"},
                {"id": 3, "kind": "mechanism", "mechanism_key": "layout/x", "anchor": "Layout(int)", "target_story": "T"},
                {"id": 4, "kind": "discovery", "anchor": "Recalc(int)", "target_story": "S"}]
        overlaps = campaign.mechanism_overlaps(ledger, opps)
        self.assertEqual({2: [{"id": 1, "mechanism_key": "css/recalc", "identity": 1.0}]}, overlaps)

    def test_out_of_scope_is_not_for_blink_code(self):
        rows = [{"anchor": "blink::V8HTMLCollection::IndexedPropertyGetterCallback(unsigned int)", "disposition": "out-of-scope"}]
        with self.assertRaisesRegex(campaign.CampaignError, "blink:: code, which this campaign owns"):
            campaign.enforce_out_of_scope_anchors(rows)
        rows[0]["anchor"] = "cc::LayerTreeHost::RequestMainFrameUpdate(bool)"
        with self.assertRaisesRegex(campaign.CampaignError, "cc:: code"):
            campaign.enforce_out_of_scope_anchors(rows)
        campaign.enforce_out_of_scope_anchors([{"anchor": "v8::internal::Heap::CollectGarbage()", "disposition": "out-of-scope"},
                                               {"anchor": "blink::Foo()", "disposition": "mandatory"}])
        campaign.enforce_out_of_scope_anchors(rows, {"in_scope_namespaces": ["blink"]})

    def test_mandatory_rows_bind_a_packet_whatever_their_share(self):
        rows = [{"anchor": "A()", "disposition": "mandatory", "redundancy_evidence": {"path": "evidence/a.json"}},
                {"anchor": "B()", "disposition": "mandatory", "wrapper_of": 1},
                {"anchor": "C()", "disposition": "below-floor"}]
        campaign.enforce_mandatory_packets(rows)
        rows.append({"anchor": "D()", "disposition": "mandatory", "evidence": "below the floor"})
        rows.append({"anchor": "E()", "disposition": "no-qualifying-mechanism"})
        with self.assertRaisesRegex(campaign.CampaignError, r"2 rows \(4, 5\) close as mandatory"):
            campaign.enforce_mandatory_packets(rows)

    def test_symbols_match_whole_functions(self):
        self.assertTrue(campaign.symbol_matches(
            "blink::LayoutView::HitTest(blink::HitTestLocation const&, blink::HitTestResult&)",
            "blink::LayoutView::HitTest"))
        self.assertTrue(campaign.symbol_matches("blink::ShapeResultView::ComputeInkBounds() const",
                                                "blink::ShapeResultView::ComputeInkBounds("))
        self.assertTrue(campaign.symbol_matches("Root", "Root"))
        self.assertFalse(campaign.symbol_matches(
            "blink::LayoutView::HitTestNoLifecycleUpdate(blink::HitTestLocation const&)",
            "blink::LayoutView::HitTest"))
        self.assertFalse(campaign.symbol_matches("Rooted(int)", "Root"))

    def test_packets_time_the_whole_of_the_function_they_name(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / STORY
        story_dir.mkdir(parents=True, exist_ok=True)
        artifact = story_dir / "candidate_frontier.json"
        artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(
            "main;Root(int);Lifecycle();Style();Match() 40\n"
            "main;Root(int);Lifecycle();Layout();Box() 50\n"
            "main;Root(int);Commit() 10\n"
        )
        profile = {"id": "p", "capture_provenance": [{
            "capture_id": "c1",
            "story_frontiers": [{"story": STORY, "artifact": str(artifact)}],
        }]}
        # Root carries 100% of the story and times 1000 ns per call; every
        # other packet's ms-per-share-point is measured against it.
        root = self.write_packet("root", applicable=0.0, repeat=0.0, site="root/update",
                                 symbol="Root", ns_per_call=1000)
        lifecycle = self.write_packet("lifecycle", applicable=0.0, repeat=0.0, site="phase/lifecycle",
                                      symbol="Lifecycle", ns_per_call=900)
        # A scope opened after most of the work: Style carries 40% but the
        # packet times a tenth of what it should.
        late = self.write_packet("late", applicable=0.0, repeat=0.0, site="style/late",
                                 symbol="Style", ns_per_call=40)
        rows = [
            {"anchor": "Root(int)", "disposition": "mandatory", "redundancy_evidence": root},
            {"anchor": "Lifecycle()", "disposition": "mandatory", "redundancy_evidence": lifecycle},
            {"anchor": "Style()", "disposition": "mandatory", "redundancy_evidence": late},
        ]
        bound = list(enumerate(rows, 1))
        table, reference = campaign.packet_time_coverage(rows, bound, profile, STORY, self.dir)
        self.assertEqual("evidence/root.json", reference)
        by_packet = {row["packet"]: row for row in table}
        self.assertAlmostEqual(1.0, by_packet["evidence/lifecycle.json"]["coverage"], places=6)
        self.assertAlmostEqual(0.1, by_packet["evidence/late.json"]["coverage"], places=6)
        with self.assertRaisesRegex(campaign.CampaignError, "0.10 of the function's time.*scope opened after"):
            campaign.enforce_packet_time_coverage(rows, bound, profile, STORY, self.dir)
        # Nested scopes counted once per level: three times the function's time.
        nested = self.write_packet("nested", applicable=0.0, repeat=0.0, site="style/nested",
                                   symbol="Style", ns_per_call=1200)
        rows[2]["redundancy_evidence"] = nested
        with self.assertRaisesRegex(campaign.CampaignError, "3.00 of the function's time.*nested scopes"):
            campaign.enforce_packet_time_coverage(rows, bound, profile, STORY, self.dir)
        # A symbol that is a neighbour of the probed function counts nothing
        # (no frame is `Sty(`), so the packet has no share and is left alone;
        # the relevance check refuses it instead. The whole function passes.
        whole = self.write_packet("whole", applicable=0.0, repeat=0.0, site="style/whole",
                                  symbol="Style", ns_per_call=400)
        rows[2]["redundancy_evidence"] = whole
        campaign.enforce_packet_time_coverage(rows, bound, profile, STORY, self.dir)
        self.assertAlmostEqual(1.0, rows[2]["packet_time_coverage"], places=3)

    def test_row_text_quotes_the_bound_packet(self):
        packet = self.write_packet("quoted", applicable=0.3, repeat=0.5, applicable_time=0.25,
                                   repeat_time=0.6, calls=15)
        config = {"share_floor_pct": 0.1, "calibration": {"story_mde_pct": {STORY: 0.5}}}
        item = {"anchor": "Root", "disposition": "novel", "mechanism_key": "x/y",
                "redundancy_evidence": packet,
                "existing_mechanism": "Root checks dirty bits; probe measures 52.18% avoidable "
                                      "time fraction (15.0 calls/rep in quoted.json)."}
        bound = [(1, item)]
        with self.assertRaisesRegex(campaign.CampaignError, "quotes '52.18%'"):
            campaign.enforce_row_text_numbers([item], bound, {1: 10.0}, config, 0.1, STORY, self.dir)
        item["existing_mechanism"] = ("Root checks dirty bits; probe measures 25.0% of its time "
                                      "on calls where nothing was dirty (26.67% of 15.0 calls/rep), "
                                      "2.5% of the story, in probe_old.json.")
        with self.assertRaisesRegex(campaign.CampaignError, "quotes packet 'probe_old.json' but binds 'quoted.json'"):
            campaign.enforce_row_text_numbers([item], bound, {1: 10.0}, config, 0.1, STORY, self.dir)
        item["existing_mechanism"] = ("Root checks dirty bits; probe measures 25.0% of its time "
                                      "on calls where nothing was dirty (26.67% of 15.0 calls/rep), "
                                      "2.5% of the story, in quoted.json; floor 1.0%.")
        campaign.enforce_row_text_numbers([item], bound, {1: 10.0}, config, 0.1, STORY, self.dir)
        item["rationale"] = "12 calls/rep were repeats"
        with self.assertRaisesRegex(campaign.CampaignError, "measured 15.0 calls per repetition"):
            campaign.enforce_row_text_numbers([item], bound, {1: 10.0}, config, 0.1, STORY, self.dir)

    def test_novel_rows_name_the_existing_mechanism(self):
        item = {"anchor": "blink::InlineNode::PrepareLayout", "disposition": "novel"}
        with self.assertRaisesRegex(campaign.CampaignError, "existing_mechanism"):
            campaign.require_existing_mechanism(item, 1)
        # The row's own function is the work under study, not the mechanism.
        item["existing_mechanism"] = ("blink::InlineNode::PrepareLayout checks dirty bits; "
                                      "probe layout/prepare in probe_x.json measures 40% over 12 calls/rep.")
        with self.assertRaisesRegex(campaign.CampaignError, "names only the row's own function"):
            campaign.require_existing_mechanism(item, 1)
        item["existing_mechanism"] = ("InlineItemsBuilder::AppendText reuses shape results only from the "
                                      "same LayoutText; 40% of 12 calls/rep reshape identical text.")
        campaign.require_existing_mechanism(item, 1)
        item["existing_mechanism"] = "Blink already reuses shape results by string match in some cases"
        with self.assertRaisesRegex(campaign.CampaignError, "existing_mechanism"):
            campaign.require_existing_mechanism(item, 1)
        item["existing_mechanism"] = (
            "InlineNode::ShapeText reuses ShapeResults by string and font match; "
            "the probe shows 257 of 519 calls per rep still reshape unchanged text"
        )
        campaign.require_existing_mechanism(item, 1)

    def test_row_text_is_not_a_template_and_mandatory_rows_state_an_invariant(self):
        paths = [
            {"anchor": "A(int)", "disposition": "novel",
             "existing_mechanism": "blink::X::Y checks dirty bits; probe a/b in probe_r12_a.json measures 12.5% applicable fraction over 15.0 calls/rep."},
            {"anchor": "B(int)", "disposition": "novel",
             "existing_mechanism": "blink::Z::W checks dirty bits; probe c/d in probe_r12_b.json measures 7.2% applicable fraction over 3.0 calls/rep."},
        ]
        with self.assertRaisesRegex(campaign.CampaignError, r"Rows \[1, 2\] carry the same `existing_mechanism` sentence"):
            campaign.enforce_row_text_distinct(paths)
        paths[1]["existing_mechanism"] = ("StyleInvalidator marks the subtree; 7.2% of 3.0 calls/rep resolve "
                                          "to the same ComputedStyle (probe_r12_b.json).")
        campaign.enforce_row_text_distinct(paths)
        rows = [{"anchor": "Layout(int)", "disposition": "mandatory"},
                {"anchor": "Paint(int)", "disposition": "mandatory",
                 "invariant": "Every frame the step dirties repaints through PaintLayerPainter::Paint; the packet leaves 0.3% repeated."}]
        with self.assertRaisesRegex(campaign.CampaignError, "Path 1 .*no `invariant` text"):
            campaign.enforce_mandatory_invariants(rows, {1, 2})
        campaign.enforce_mandatory_invariants(rows, {2})
        campaign.enforce_mandatory_invariants(rows, set())
        # An invariant with no number says nothing the gate can read.
        rows[1]["invariant"] = "Every frame the step dirties repaints through PaintLayerPainter::Paint for changed items."
        with self.assertRaisesRegex(campaign.CampaignError, "quotes no number"):
            campaign.enforce_mandatory_invariants(rows, {2})

    def test_row_text_names_code_that_exists(self):
        import subprocess
        repo = self.dir / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "a.cc").write_text("void blink::StyleInvalidator::Invalidate(Element& e) {}\n")
        (repo / "b.h").write_text("class CORE_EXPORT LayoutBox {\n  const LayoutResult* CachedLayoutResult();\n};\n")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        rows = [{"anchor": "A(int)", "existing_mechanism":
                 "StyleInvalidator::Invalidate marks the subtree and LayoutBox::CachedLayoutResult keeps the result; 12% repeat."}]
        campaign.enforce_row_text_symbols(rows, [(1, rows[0])], str(repo))
        rows[0]["invariant"] = "RuleSet::FindBestRuleSetAndFilter reuses matched rules; 0.3% of time repeats."
        with self.assertRaisesRegex(campaign.CampaignError, "not in the tree .*RuleSet::FindBestRuleSetAndFilter"):
            campaign.enforce_row_text_symbols(rows, [(1, rows[0])], str(repo))
        with self.assertRaisesRegex(campaign.CampaignError, "not a git checkout"):
            campaign.enforce_row_text_symbols(rows, [(1, rows[0])], str(self.dir / "nowhere"))
        # Rows closed by one packet share its invariant; rows under different
        # packets do not share a sentence.
        shared = "Every frame the step dirties repaints through PaintLayerPainter::Paint; the packet leaves 0.3% repeated."
        same = [{"anchor": "A(int)", "disposition": "mandatory", "invariant": shared,
                 "redundancy_evidence": {"path": "evidence/p.json"}},
                {"anchor": "B(int)", "disposition": "mandatory", "invariant": shared,
                 "redundancy_evidence": {"path": "evidence/p.json"}}]
        campaign.enforce_row_text_distinct(same)
        same[1]["redundancy_evidence"] = {"path": "evidence/q.json"}
        with self.assertRaisesRegex(campaign.CampaignError, "same `invariant` sentence"):
            campaign.enforce_row_text_distinct(same)

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
