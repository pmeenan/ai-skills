#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for the campaign ledger state machine and STATUS.md generation."""

import json
import os
import pathlib
import subprocess
import tempfile
import unittest

import campaign


class CampaignTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / "camp"
        # Run outside any git repo so commit verification is skipped.
        self.prev_cwd = os.getcwd()
        self.prev_test_override = os.environ.get(
            "SP3_CAMPAIGN_TEST_ALLOW_UNVERIFIED"
        )
        os.environ["SP3_CAMPAIGN_TEST_ALLOW_UNVERIFIED"] = "1"
        os.chdir(self.tmp.name)
        self.assertEqual(0, self.run_cmd(
            "init", "--name", "test-campaign", "--target", "20",
            "--share-floor", "0.1"))

    def tearDown(self):
        os.chdir(self.prev_cwd)
        if self.prev_test_override is None:
            os.environ.pop("SP3_CAMPAIGN_TEST_ALLOW_UNVERIFIED", None)
        else:
            os.environ["SP3_CAMPAIGN_TEST_ALLOW_UNVERIFIED"] = self.prev_test_override
        self.tmp.cleanup()

    def run_cmd(self, *argv):
        command = list(argv)
        if command and command[0] == "audit-exhaustion":
            command.append("--allow-unverified-repository")
        return campaign.main(["--dir", str(self.dir)] + command)

    def ledger(self):
        with open(self.dir / "ledger.json") as f:
            return json.load(f)

    def status_text(self):
        with open(self.dir / "STATUS.md") as f:
            return f.read()

    def add_opp(self, anchor="StyleEngine::RecalcStyle subtree", share="0.6"):
        self.assertEqual(0, self.run_cmd("add", "--anchor", anchor, "--share", share))
        return self.ledger()["opportunities"][-1]["id"]

    def reconciliation(self, areas):
        parked = []
        for opp in self.ledger()["opportunities"]:
            if opp.get("kind") != "mechanism" or opp["status"] != "parked":
                continue
            if areas:
                parked.append({
                    "mechanism_key": opp["mechanism_key"],
                    "disposition": "recurrent",
                    "area_key": areas[0]["area_key"],
                })
            else:
                parked.append({
                    "mechanism_key": opp["mechanism_key"],
                    "disposition": "not-recurrent",
                    "evidence": "absent from both exhaustive frontiers",
                })
        return {
            "areas": areas,
            "source_exclusions": [],
            "parked_mechanisms": parked,
        }

    def write_capture_summaries(self, profile_id, sha, areas, prefix=None):
        summaries = []
        prefix = prefix or profile_id
        for index in (1, 2):
            capture_id = f"{prefix}-{index}"
            frontier = [
                {
                    "entry_key": f"symbol:{area.get('entry_name', area['area_key'])}",
                    "kind": "symbol",
                    "name": area.get("entry_name", area["area_key"]),
                    "marginal_share": area.get("marginal_share_pct", 0.0) / 100,
                    "related_hotspots": [
                        {**item, "overlap_share": item.get("overlap_share", 0.002)}
                        for item in area.get("related_hotspots", [])
                    ],
                }
                for area in areas
            ]
            local_results = self.dir / capture_id
            artifact = local_results / "analysis" / "full" / "candidate_frontier.json"
            artifact.parent.mkdir(parents=True)
            alternatives = [
                {
                    "kind": "symbol",
                    "name": item["name"],
                    "entry_key": f"symbol:{item['name']}",
                    "inclusive_share": item.get("inclusive_share", 0.002),
                    "assigned_frontier_entry": (
                        f"symbol:{area.get('entry_name', area['area_key'])}"
                    ),
                }
                for area in areas
                for item in area.get("assigned_alternatives", [])
            ]
            artifact.write_text(json.dumps({
                "quality": {"accepted": True},
                "selection": {
                    "inventory_complete": True,
                    "min_inclusive_share": 0.001,
                    "min_marginal_share": 0.001,
                },
                "frontier": frontier,
                "overlapping_alternatives": alternatives,
            }))
            inventory = [
                {
                    "entry_key": f"symbol:{area.get('entry_name', area['area_key'])}",
                    "work_items": [{
                        "hotspot_key": "@root",
                        "semantic_key": (
                            f"symbol:{area.get('entry_name', area['area_key'])}"
                        ),
                        "measured_share_pct": area.get("marginal_share_pct", 0.0),
                    }] + [{
                        "hotspot_key": item["name"],
                        "semantic_key": f"symbol:{item['name']}",
                        "measured_share_pct": item.get("overlap_share", 0.002) * 100,
                    } for item in area.get("related_hotspots", [])] + [{
                        "hotspot_key": f"alternative:symbol:{item['name']}",
                        "semantic_key": f"symbol:{item['name']}",
                        "measured_share_pct": item.get("inclusive_share", 0.002) * 100,
                    } for item in area.get("assigned_alternatives", [])],
                }
                for area in areas
            ]
            summaries.append({
                "mode": "profile",
                "capture_id": capture_id,
                "sha": sha,
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
                "full_candidate_frontier_json": str(artifact),
            })
        path = self.dir / f"captures-{profile_id}.json"
        path.write_text(json.dumps(summaries))
        return path

    def record_profile(
        self, profile_id, total="1.2", area_count="1", related_hotspots=None
    ):
        before = len(self.ledger()["opportunities"])
        count = int(area_count)
        share = float(total) / count if count else 0
        areas = [
            {
                "area_key": "style-recalc" if index == 0 else f"area-{index + 1}",
                "anchor": "Style recalc area" if index == 0 else f"Area {index + 1}",
                "marginal_share_pct": share,
            }
            for index in range(count)
        ]
        if areas and related_hotspots:
            areas[0]["related_hotspots"] = [
                {"name": name} for name in related_hotspots
            ]
        capture_ids = [f"{profile_id}-{index}" for index in (1, 2)]
        for area in areas:
            area["source_refs"] = [
                {"capture_id": capture_id,
                 "entry_key": f"symbol:{area['area_key']}"}
                for capture_id in capture_ids
            ]
        path = self.dir / f"areas-{profile_id}.json"
        path.write_text(json.dumps(self.reconciliation(areas)))
        captures = self.write_capture_summaries(profile_id, "deadbeef", areas)
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", profile_id, "--sha", "deadbeef",
            "--areas", str(path), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        return [
            opp["id"] for opp in self.ledger()["opportunities"][before:]
        ]

    def decompose(self, opp, children):
        ledger = campaign.Ledger(self.dir).load()
        discovery = ledger.opp(opp)
        if discovery["status"] == "candidate":
            self.assertEqual(0, self.run_cmd(
                "advance", "--opp", str(opp), "--to", "investigating"))
        paths = []
        for index, child in enumerate(children):
            item = dict(child)
            item.setdefault("evidence", "profile-backed source hypothesis")
            if "work_refs" not in item:
                refs = (
                    discovery["expected_work_refs"]
                    if index == 0 else discovery["expected_work_refs"][:1]
                )
                item["work_refs"] = [
                    {**ref, "accounting": "primary" if index == 0 else "overlap"}
                    for ref in refs
                ]
            if "disposition" not in item:
                item["disposition"] = (
                    "known" if ledger.mechanism(
                        item.get("area_key") or discovery["area_key"],
                        item["mechanism_key"],
                    ) else "novel"
                )
            paths.append(item)
        path = self.dir / f"children-{opp}.json"
        path.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "all supplied hotspots accounted for",
            "paths": paths,
        }))
        return self.run_cmd(
            "decompose", "--opp", str(opp), "--children", str(path))

    def exhaust(self, opp, reason, evidence, *, skip_review=False):
        if not skip_review:
            self.assertEqual(0, self.run_cmd(
                "review", "--opp", str(opp), "--role", "skeptic",
                "--verdict", "PASS"))
        return self.run_cmd(
            "exhaust", "--opp", str(opp), "--reason", reason,
            "--evidence", evidence)

    def test_add_and_status(self):
        opp_id = self.add_opp()
        self.assertEqual(1, opp_id)
        text = self.status_text()
        self.assertIn("StyleEngine::RecalcStyle subtree", text)
        self.assertIn("Landed: 0/20", text)

    def test_global_priority_surfaces_hot_nested_work_before_shallow_parent(self):
        areas = [{
            "area_key": "low-marginal-parent",
            "anchor": "Low marginal parent",
            "marginal_share_pct": 0.3,
            "related_hotspots": [{
                "name": "blink::DeepHotChild",
                "overlap_share": 0.02,
            }],
        }, {
            "area_key": "shallow-parent",
            "anchor": "Shallow parent",
            "marginal_share_pct": 1.0,
        }]
        for area in areas:
            area["source_refs"] = [
                {"capture_id": f"priority-{index}",
                 "entry_key": f"symbol:{area['area_key']}"}
                for index in (1, 2)
            ]
        manifest = self.dir / "areas-priority.json"
        manifest.write_text(json.dumps(self.reconciliation(areas)))
        captures = self.write_capture_summaries(
            "priority", "deadbeef", areas, prefix="priority"
        )
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "priority", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        ledger = campaign.Ledger(self.dir).load()
        self.assertEqual([1, 2], [
            item["id"] for item in ledger.next_candidates(2)
        ])
        self.assertEqual(2.0, ledger.priority(ledger.opp(1)))
        self.assertIn(
            "priority 2.000, hottest-unresolved-profiler-work",
            self.status_text(),
        )

        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "investigating"))
        discovery = campaign.Ledger(self.dir).load().opp(1)
        grouped = {}
        for ref in discovery["expected_work_refs"]:
            grouped.setdefault(ref["hotspot_key"], []).append({
                **ref, "accounting": "primary",
            })
        decomposition = self.dir / "children-priority.json"
        decomposition.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "root and deep child independently accounted",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "parent-only work",
                "share_pct": 0.3,
                "evidence": "parent decision is mandatory",
                "work_refs": grouped["@root"],
            }, {
                "disposition": "novel",
                "anchor": "deep hot child",
                "mechanism_key": "blink/deep-hot-fast-path",
                "share_pct": 0.05,
                "evidence": "investigator estimate deliberately understates profile",
                "work_refs": grouped["blink::DeepHotChild"],
            }],
        }))
        self.assertEqual(0, self.run_cmd(
            "decompose", "--opp", "1", "--children", str(decomposition)))
        ledger = campaign.Ledger(self.dir).load()
        self.assertEqual([3, 2], [
            item["id"] for item in ledger.next_candidates(2)
        ])
        self.assertEqual(2.0, ledger.priority(ledger.opp(3)))
        self.assertEqual(0.05, ledger.opp(3)["share_pct"])

    def test_expected_value_only_overrides_with_comparable_unit(self):
        self.assertEqual(1, self.run_cmd(
            "add", "--anchor", "ambiguous override", "--share", "0.2",
            "--expected-value", "10"))
        high = self.add_opp(anchor="measured high", share="0.8")
        self.assertEqual(0, self.run_cmd(
            "add", "--anchor", "validated override", "--share", "0.2",
            "--expected-value", "0.9", "--expected-value-unit",
            campaign.EXPECTED_VALUE_UNIT))
        ledger = campaign.Ledger(self.dir).load()
        self.assertEqual([2, high], [
            item["id"] for item in ledger.next_candidates(2)
        ])
        self.assertEqual("expected-value", ledger.priority_info(ledger.opp(2))[1])

    def test_init_rejects_invalid_share_floor(self):
        other = pathlib.Path(self.tmp.name) / "invalid-camp"
        self.assertEqual(1, campaign.main([
            "--dir", str(other), "init", "--name", "invalid",
            "--share-floor", "nan",
        ]))

    def test_discovery_decomposes_and_follow_on_skips_known_paths(self):
        discovery = self.record_profile("profile-1")[0]
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(discovery), "--to", "sized",
            "--ceiling", "0.4", "--evidence", "oracle"))
        self.assertEqual(1, self.run_cmd(
            "reject", "--opp", str(discovery), "--reason", "parent idea failed",
            "--evidence", "source inspection"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery), "--to", "investigating"))
        children = [
            {"anchor": "Rule collector", "mechanism_key": "style/cache-rule-match",
             "share_pct": 0.35},
            {"anchor": "Cascade", "mechanism_key": "style/skip-duplicate-cascade",
             "share_pct": 0.25},
        ]
        self.assertEqual(0, self.decompose(discovery, children))
        data = self.ledger()
        self.assertEqual("decomposed", data["opportunities"][0]["status"])
        self.assertEqual([2, 3], data["opportunities"][0]["known_mechanism_ids"])
        self.assertTrue(all(
            opp["parent_id"] == discovery
            for opp in data["opportunities"][1:]
        ))
        for opp_id in (2, 3):
            self.assertEqual(0, self.run_cmd(
                "advance", "--opp", str(opp_id), "--to", "investigating"))
            self.assertEqual(0, self.run_cmd(
                "reject", "--opp", str(opp_id), "--reason", "mechanism invalid",
                "--evidence", "source inspection rules out the path"))
        self.assertEqual(0, self.exhaust(
            discovery, "all paths tried",
            "union of residual child masks is below 0.1%"))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))

        follow_on = self.record_profile("profile-2", total="0.7")[0]
        follow_on_children = [
            children[0],
            {"anchor": "Selector cache", "mechanism_key": "style/memoize-selector-key",
             "share_pct": 0.2},
        ]
        self.assertEqual(0, self.decompose(follow_on, follow_on_children))
        data = self.ledger()
        self.assertEqual(5, len(data["opportunities"]))
        self.assertEqual([2, 5], data["opportunities"][3]["known_mechanism_ids"])
        self.assertEqual(["profile-1", "profile-2"],
                         data["opportunities"][1]["source_profile_ids"])
        self.assertEqual("style/memoize-selector-key",
                         data["opportunities"][4]["mechanism_key"])
        self.assertIn("Latest profile `profile-2` eligible frontier: 0.70%",
                      self.status_text())

    def test_landing_requires_follow_on_profile_before_exhaustion(self):
        discovery = self.record_profile("profile-1")[0]
        child = {
            "anchor": "Rule collector", "mechanism_key": "style/cache-rule-match",
            "share_pct": 0.35,
        }
        self.assertEqual(0, self.decompose(discovery, [child]))
        opp = 2
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.run_cmd("review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS")
        self.run_cmd("review", "--opp", str(opp), "--role", "adversary", "--verdict", "PASS")
        self.run_cmd("advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef")
        self.assertEqual(1, self.exhaust(
            discovery, "child landed", "stale pre-landing profile"))
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))
        follow_on = self.record_profile("profile-2", total="0.2")[0]
        self.assertEqual(0, self.decompose(follow_on, [child]))
        self.assertEqual(0, self.exhaust(
            follow_on, "residual mandatory",
            "fresh exact-mask residual has no novel mechanism"))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))

    def test_exhaustion_audit_requires_all_profile_areas(self):
        discovery = self.record_profile("profile-1", area_count="2")[0]
        self.assertEqual(0, self.decompose(discovery, [{
            "anchor": "mandatory application work",
            "share_pct": 0.6,
            "disposition": "mandatory",
        }]))
        self.assertEqual(0, self.exhaust(
            discovery, "mandatory work",
            "all exact-mask residual is mandatory"))
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))

    def test_profile_import_accounts_for_excluded_frontier_rows(self):
        path = self.dir / "areas-profile-1.json"
        areas = [
            {"area_key": "style-recalc", "anchor": "Style recalc",
             "marginal_share_pct": 0.5, "disposition": "discover"},
            {"area_key": "script-dispatch", "anchor": "Script runner",
             "marginal_share_pct": 0.4, "disposition": "exclude",
             "exclusion_category": "payload-dominated",
             "exclusion_reason": "payload-dominated application script",
             "exclusion_evidence": "owner-exclusive share is negligible"},
        ]
        for area in areas:
            area["source_refs"] = [
                {"capture_id": f"capture-{index}",
                 "entry_key": f"symbol:{area['area_key']}"}
                for index in (1, 2)
            ]
        path.write_text(json.dumps(self.reconciliation(areas)))
        captures = self.write_capture_summaries(
            "profile-1", "deadbeef", areas, prefix="capture"
        )
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "profile-1", "--sha", "deadbeef",
            "--areas", str(path), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        data = self.ledger()
        self.assertEqual(1, len(data["opportunities"]))
        profile = data["profile_runs"][0]
        self.assertEqual(2, profile["inventory_count"])
        self.assertEqual(1, profile["area_count"])
        self.assertEqual(0.5, profile["total_share_pct"])
        self.assertEqual(0.9, profile["observed_share_pct"])

    def test_profile_cannot_exclude_parent_with_material_child_work(self):
        path = self.dir / "areas-excluded-composite.json"
        areas = [{
            "area_key": "script-dispatch",
            "anchor": "Script dispatch shell",
            "marginal_share_pct": 0.4,
            "disposition": "exclude",
            "exclusion_category": "payload-dominated",
            "exclusion_reason": "the parent frame is application dispatch",
            "exclusion_evidence": "the shell itself has no engine-owned work",
            "assigned_alternatives": [{"name": "blink::OptimizableChild"}],
            "source_refs": [
                {"capture_id": f"capture-{index}",
                 "entry_key": "symbol:script-dispatch"}
                for index in (1, 2)
            ],
        }]
        path.write_text(json.dumps(self.reconciliation(areas)))
        captures = self.write_capture_summaries(
            "excluded-composite", "deadbeef", areas, prefix="capture"
        )
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "excluded-composite", "--sha", "deadbeef",
            "--areas", str(path), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    def test_mechanism_identity_is_unique(self):
        self.assertEqual(0, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "Rule collector",
            "--area-key", "style-recalc", "--mechanism-key", "style/cache-rule-match",
            "--share", "0.3"))
        self.assertEqual(1, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "Rule collector again",
            "--area-key", "style-recalc", "--mechanism-key", "style/cache-rule-match",
            "--share", "0.4"))

    def test_follow_on_profile_reopens_parked_mechanism(self):
        first = self.record_profile("profile-1")[0]
        child = {
            "anchor": "Rule collector", "mechanism_key": "style/cache-rule-match",
            "share_pct": 0.35,
        }
        self.assertEqual(0, self.decompose(first, [child]))
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", "2", "--reason", "not recurrent in prior capture"))
        follow_on = self.record_profile("profile-2")[0]
        rediscovered = dict(child, anchor="Rule collector moved", share_pct=0.9)
        self.assertEqual(0, self.decompose(follow_on, [rediscovered]))
        mechanism = self.ledger()["opportunities"][1]
        self.assertEqual("candidate", mechanism["status"])
        self.assertEqual([first, follow_on], mechanism["discovery_ids"])
        self.assertEqual(2, len(mechanism["observations"]))
        self.assertEqual(0.9, mechanism["share_pct"])
        self.assertEqual("Rule collector moved", mechanism["anchor"])
        self.assertIn(mechanism, campaign.Ledger(self.dir).load().children(follow_on))

    def test_parked_child_cannot_be_hidden_when_it_becomes_a_root(self):
        first = self.record_profile(
            "profile-1", related_hotspots=["blink::SharedF::Run()"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(first), "--to", "investigating"))
        discovery = campaign.Ledger(self.dir).load().opp(first)
        refs_by_hotspot = {}
        for ref in discovery["expected_work_refs"]:
            refs_by_hotspot.setdefault(ref["hotspot_key"], []).append({
                **ref, "accounting": "primary",
            })
        decomposition = self.dir / "children-shared-f.json"
        decomposition.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "root and nested F independently classified",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "parent root",
                "share_pct": 0.4,
                "evidence": "parent-only work",
                "work_refs": refs_by_hotspot["@root"],
            }, {
                "disposition": "novel",
                "anchor": "shared F child",
                "mechanism_key": "blink/shared-f-fast-path",
                "share_pct": 0.2,
                "evidence": "caller-specific avoidable work",
                "work_refs": refs_by_hotspot["blink::SharedF::Run()"],
            }],
        }))
        self.assertEqual(0, self.run_cmd(
            "decompose", "--opp", str(first), "--children", str(decomposition)))
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", "2", "--reason", "awaiting recurrence"))

        areas = [{
            "area_key": "shared-f-root",
            "entry_name": "blink::SharedF::Run()",
            "anchor": "Shared F is now a frontier root",
            "marginal_share_pct": 0.5,
            "source_refs": [
                {"capture_id": f"profile-2-{index}",
                 "entry_key": "symbol:blink::SharedF::Run()"}
                for index in (1, 2)
            ],
        }]
        manifest = self.dir / "areas-profile-2.json"
        manifest.write_text(json.dumps({
            "areas": areas,
            "source_exclusions": [],
            "parked_mechanisms": [{
                "mechanism_key": "blink/shared-f-fast-path",
                "disposition": "not-recurrent",
                "evidence": "incorrectly claims representation change is absence",
            }],
        }))
        captures = self.write_capture_summaries("profile-2", "deadbeef", areas)
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "profile-2", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    def test_reopening_child_invalidates_exhausted_parent_and_audit(self):
        discovery = self.record_profile("profile-1")[0]
        self.assertEqual(0, self.decompose(discovery, [{
            "anchor": "Rule collector",
            "mechanism_key": "style/cache-rule-match",
            "share_pct": 0.35,
        }]))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "2", "--to", "investigating"))
        self.assertEqual(0, self.run_cmd(
            "reject", "--opp", "2", "--reason", "invalid",
            "--evidence", "source inspection"))
        self.assertEqual(0, self.exhaust(
            discovery, "all paths tried", "complete residual accounting"))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))
        self.assertEqual(0, self.run_cmd(
            "reopen", "--opp", "2", "--contradicts-prior-evidence",
            "--reason", "new trace contradicts source assumption"))
        self.assertEqual("decomposed", self.ledger()["opportunities"][0]["status"])
        # Reopening a child stales the skeptic exhaustion review as well.
        self.assertEqual({}, self.ledger()["opportunities"][0]["reviews"])
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", "2", "--reason", "awaiting another trace"))
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))

    def test_follow_on_discovery_cannot_silently_omit_parked_path(self):
        first = self.record_profile("profile-1")[0]
        self.assertEqual(0, self.decompose(first, [{
            "anchor": "Rule collector",
            "mechanism_key": "style/cache-rule-match",
            "share_pct": 0.35,
        }]))
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", "2", "--reason", "awaiting recurrence"))
        follow_on = self.record_profile("profile-2")[0]
        self.assertEqual(0, self.decompose(follow_on, [{
            "anchor": "other mandatory residual",
            "share_pct": 0.3,
            "disposition": "mandatory",
        }]))
        self.assertEqual(0, self.exhaust(
            follow_on, "claimed complete", "claimed accounting"))
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))

    def test_decomposition_cannot_omit_profiled_nested_hotspots(self):
        discovery_id = self.record_profile(
            "profile-1", related_hotspots=["blink::ChildA", "blink::ChildB"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery_id), "--to", "investigating"))
        discovery = campaign.Ledger(self.dir).load().opp(discovery_id)
        roots_only = [
            {**ref, "accounting": "primary"}
            for ref in discovery["expected_work_refs"]
            if ref["hotspot_key"] == "@root"
        ]
        path = self.dir / "children-omits-hotspots.json"
        path.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "claims all work is mandatory",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "unrelated mandatory work",
                "share_pct": 0.3,
                "evidence": "unsupported claim",
                "work_refs": roots_only,
            }],
        }))
        self.assertEqual(1, self.run_cmd(
            "decompose", "--opp", str(discovery_id), "--children", str(path)))
        path.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "coarse row claims every child",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "coarse parent",
                "share_pct": 0.3,
                "evidence": "one conclusion for unrelated children",
                "work_refs": [
                    {**ref, "accounting": "primary"}
                    for ref in discovery["expected_work_refs"]
                ],
            }],
        }))
        self.assertEqual(1, self.run_cmd(
            "decompose", "--opp", str(discovery_id), "--children", str(path)))

    def test_measured_hotspot_cannot_be_fabricated_as_below_floor(self):
        discovery_id = self.record_profile(
            "profile-1", related_hotspots=["blink::MeasuredHotChild"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery_id), "--to", "investigating"))
        discovery = campaign.Ledger(self.dir).load().opp(discovery_id)
        refs_by_hotspot = {}
        for ref in discovery["expected_work_refs"]:
            refs_by_hotspot.setdefault(ref["hotspot_key"], []).append({
                **ref, "accounting": "primary",
            })
        path = self.dir / "children-fabricated-below-floor.json"
        path.write_text(json.dumps({
            "area_key": discovery["area_key"],
            "profile_id": discovery["profile_id"],
            "accounting_evidence": "claims measured child is negligible",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "root work",
                "share_pct": 0.3,
                "evidence": "root classification",
                "work_refs": refs_by_hotspot["@root"],
            }, {
                "disposition": "below-floor",
                "anchor": "measured child",
                "share_pct": 0.01,
                "evidence": "investigator estimate contradicts profiler",
                "work_refs": refs_by_hotspot["blink::MeasuredHotChild"],
            }],
        }))
        self.assertEqual(1, self.run_cmd(
            "decompose", "--opp", str(discovery_id), "--children", str(path)))

    def test_profile_rejects_unverifiable_capture_claims(self):
        areas = self.dir / "areas-invalid.json"
        areas.write_text(
            '{"areas":[],"source_exclusions":[],"parked_mechanisms":[]}'
        )
        captures = self.dir / "captures-invalid.json"
        captures.write_text(json.dumps([
            {"capture_id": "same", "sha": "deadbeef",
             "quality_rejected": False, "enable_features": "",
             "share_floor_pct": 0.25, "inventory_complete": False,
             "frontier_entries": []},
            {"capture_id": "same", "sha": "deadbeef",
             "quality_rejected": False, "enable_features": "",
             "share_floor_pct": 0.25, "inventory_complete": False,
             "frontier_entries": []},
        ]))
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "bad", "--sha", "deadbeef",
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "",
            "--allow-unverified-repository"))

    def test_profile_rejects_omitted_recurrent_source_entry(self):
        areas = self.dir / "areas-omitted.json"
        areas.write_text(
            '{"areas":[],"source_exclusions":[],"parked_mechanisms":[]}'
        )
        capture_area = {"area_key": "blink-hot", "related_hotspots": []}
        captures = self.write_capture_summaries(
            "omitted", "deadbeef", [capture_area]
        )
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "omitted", "--sha", "deadbeef",
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    def test_profile_rejects_mismatched_capture_configuration(self):
        areas = self.dir / "areas-config-mismatch.json"
        areas.write_text(
            '{"areas":[],"source_exclusions":[],"parked_mechanisms":[]}'
        )
        captures = self.write_capture_summaries(
            "config-mismatch", "deadbeef", []
        )
        summaries = json.loads(captures.read_text())
        summaries[1]["enable_features"] += ",UnrelatedExperiment"
        captures.write_text(json.dumps(summaries))
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "config-mismatch", "--sha", "deadbeef",
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    def test_profile_rejects_duplicate_artifact_with_edited_capture_id(self):
        areas = self.dir / "areas-duplicate-capture.json"
        areas.write_text(
            '{"areas":[],"source_exclusions":[],"parked_mechanisms":[]}'
        )
        captures = self.write_capture_summaries(
            "duplicate-capture", "deadbeef", []
        )
        summaries = json.loads(captures.read_text())
        summaries[1]["full_candidate_frontier_json"] = summaries[0][
            "full_candidate_frontier_json"
        ]
        captures.write_text(json.dumps(summaries))
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "duplicate-capture", "--sha", "deadbeef",
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))

    def test_nonfinite_share_and_unnamespaced_mechanism_are_rejected(self):
        self.assertEqual(1, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "Rule collector",
            "--area-key", "style-recalc", "--mechanism-key", "cache-rule",
            "--share", "nan"))
        self.assertEqual(1, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "Rule collector",
            "--area-key", "style-recalc", "--mechanism-key", "cache-rule",
            "--share", "0.3"))

    def test_version_one_ledger_migrates_in_place_on_next_mutation(self):
        opp = self.add_opp()
        data = self.ledger()
        data.pop("schema_version")
        data.pop("next_sequence")
        data.pop("profile_runs")
        for field in (
            "kind", "area_key", "mechanism_key", "parent_id", "profile_id",
            "discovery_ids", "source_profile_ids", "known_mechanism_ids",
            "runtime_change_sequence",
        ):
            data["opportunities"][0].pop(field, None)
        (self.dir / "ledger.json").write_text(json.dumps(data))
        self.assertEqual(0, self.run_cmd(
            "note", "--opp", str(opp), "--text", "migration save"))
        migrated = self.ledger()
        self.assertEqual(2, migrated["schema_version"])
        self.assertEqual("mechanism", migrated["opportunities"][0]["kind"])
        self.assertEqual("legacy-001", migrated["opportunities"][0]["mechanism_key"])

    def test_exhaust_requires_skeptic_review_of_decomposition(self):
        discovery = self.record_profile("profile-1")[0]
        self.assertEqual(0, self.decompose(discovery, [{
            "anchor": "mandatory residual",
            "share_pct": 0.3,
            "disposition": "mandatory",
        }]))
        self.assertEqual(1, self.exhaust(
            discovery, "claimed", "claimed", skip_review=True))
        self.assertEqual(1, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "adversary",
            "--verdict", "PASS"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "skeptic",
            "--verdict", "FAIL"))
        self.assertEqual(1, self.exhaust(
            discovery, "claimed", "claimed", skip_review=True))
        self.assertEqual(1, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "skeptic",
            "--verdict", "PASS"))
        self.assertEqual(0, self.decompose(discovery, [{
            "anchor": "revised mandatory residual",
            "share_pct": 0.3,
            "disposition": "mandatory",
            "evidence": "observable behavior pins the revised residual",
        }]))
        revised = campaign.Ledger(self.dir).load().opp(discovery)
        self.assertEqual(2, revised["decomposition_revision"])
        self.assertEqual({}, revised["reviews"])
        self.assertEqual(1, self.exhaust(
            discovery, "claimed", "claimed", skip_review=True))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "skeptic",
            "--verdict", "PASS"))
        self.assertEqual(0, self.exhaust(
            discovery, "mandatory only", "skeptic-verified accounting",
            skip_review=True))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))
        tampered = self.ledger()
        tampered["opportunities"][0]["path_accounting"][0]["evidence"] = (
            "changed after review"
        )
        (self.dir / "ledger.json").write_text(json.dumps(tampered))
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))

    def test_skeptic_review_requires_decomposed_discovery(self):
        discovery = self.record_profile("profile-1")[0]
        self.assertEqual(1, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "skeptic",
            "--verdict", "PASS"))

    def test_covered_by_accounts_wrapper_chain_to_one_mechanism(self):
        discovery = self.record_profile(
            "profile-1", related_hotspots=["blink::Wrapper", "blink::Inner"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery), "--to", "investigating"))
        record = campaign.Ledger(self.dir).load().opp(discovery)
        refs_by_hotspot = {}
        for ref in record["expected_work_refs"]:
            refs_by_hotspot.setdefault(ref["hotspot_key"], []).append({
                "capture_id": ref["capture_id"],
                "entry_key": ref["entry_key"],
                "hotspot_key": ref["hotspot_key"],
                "accounting": "primary",
            })
        def decomposition(covered_by):
            return {
                "area_key": record["area_key"],
                "profile_id": record["profile_id"],
                "accounting_evidence": "chain masks are near-identical",
                "paths": [{
                    "disposition": "mandatory",
                    "anchor": "parent root",
                    "share_pct": 0.4,
                    "evidence": "root decision is mandatory",
                    "work_refs": refs_by_hotspot["@root"],
                }, {
                    "disposition": "novel",
                    "anchor": "inner hot loop",
                    "mechanism_key": "blink/inner-fast-path",
                    "share_pct": 0.2,
                    "evidence": "counter-verified avoidable work",
                    "work_refs": refs_by_hotspot["blink::Inner"],
                }, {
                    "disposition": "covered-by",
                    "anchor": "blink::Wrapper",
                    "covered_by": covered_by,
                    "share_pct": 0.2,
                    "evidence": "wrapper frame of the same samples as Inner",
                    "work_refs": refs_by_hotspot["blink::Wrapper"],
                }],
            }
        bad = self.dir / "children-covered-bad.json"
        bad.write_text(json.dumps(decomposition("blink/nonexistent-owner")))
        self.assertEqual(1, self.run_cmd(
            "decompose", "--opp", str(discovery), "--children", str(bad)))
        good = self.dir / "children-covered-good.json"
        good.write_text(json.dumps(decomposition("blink/inner-fast-path")))
        self.assertEqual(0, self.run_cmd(
            "decompose", "--opp", str(discovery), "--children", str(good)))
        data = self.ledger()
        mechanisms = [
            opp for opp in data["opportunities"] if opp["kind"] == "mechanism"
        ]
        self.assertEqual(1, len(mechanisms))
        owner = mechanisms[0]
        self.assertIn(
            "symbol:blink::Wrapper",
            owner["observations"][-1]["work_fingerprints"],
        )
        self.assertTrue(any(
            "covers same-work wrapper hotspot" in event["event"]
            for event in owner["history"]
        ))

    def test_covered_by_existing_parked_owner_is_linked_and_reopened(self):
        self.assertEqual(0, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "old inner",
            "--area-key", "style-recalc", "--mechanism-key",
            "blink/inner-fast-path", "--share", "0.2"))
        owner_id = self.ledger()["opportunities"][-1]["id"]
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", str(owner_id), "--reason", "await recurrence"))
        discovery = self.record_profile(
            "profile-1", related_hotspots=["blink::Wrapper"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery), "--to", "investigating"))
        record = campaign.Ledger(self.dir).load().opp(discovery)
        refs_by_hotspot = {}
        for ref in record["expected_work_refs"]:
            refs_by_hotspot.setdefault(ref["hotspot_key"], []).append({
                "capture_id": ref["capture_id"],
                "entry_key": ref["entry_key"],
                "hotspot_key": ref["hotspot_key"],
                "accounting": "primary",
            })
        decomposition = self.dir / "covered-existing.json"
        decomposition.write_text(json.dumps({
            "area_key": "style-recalc",
            "profile_id": "profile-1",
            "accounting_evidence": "wrapper is the old inner mechanism",
            "paths": [{
                "disposition": "mandatory",
                "anchor": "root",
                "share_pct": 1.2,
                "evidence": "root decision is mandatory",
                "work_refs": refs_by_hotspot["@root"],
            }, {
                "disposition": "covered-by",
                "anchor": "blink::Wrapper",
                "covered_by": "blink/inner-fast-path",
                "share_pct": 0.2,
                "evidence": "same samples as the old inner mechanism",
                "work_refs": refs_by_hotspot["blink::Wrapper"],
            }],
        }))
        self.assertEqual(0, self.run_cmd(
            "decompose", "--opp", str(discovery),
            "--children", str(decomposition)))
        owner = campaign.Ledger(self.dir).load().opp(owner_id)
        self.assertEqual("candidate", owner["status"])
        self.assertIn(discovery, owner["discovery_ids"])
        self.assertIn("profile-1", owner["source_profile_ids"])
        self.assertEqual(discovery, owner["observations"][-1]["discovery_id"])
        self.assertIn(
            "symbol:blink::Wrapper",
            owner["observations"][-1]["work_fingerprints"],
        )
        self.assertIn(
            owner_id,
            campaign.Ledger(self.dir).load().opp(discovery)[
                "known_mechanism_ids"
            ],
        )
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(owner_id), "--to", "investigating"))
        self.assertEqual(0, self.run_cmd(
            "reject", "--opp", str(owner_id), "--reason", "still invalid",
            "--evidence", "source proof still rules out the path"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(discovery), "--role", "skeptic",
            "--verdict", "PASS"))
        self.assertEqual(0, self.exhaust(
            discovery, "resolved", "covered owner resolved", skip_review=True))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))

    def test_add_kind_discovery_is_forbidden(self):
        self.assertEqual(1, self.run_cmd(
            "add", "--kind", "discovery", "--anchor", "Style recalc",
            "--area-key", "style-recalc", "--share", "0.5"))

    def test_profile_scaffold_round_trips_through_import(self):
        self.assertEqual(0, self.run_cmd(
            "add", "--kind", "mechanism", "--anchor", "old idea",
            "--area-key", "old-area", "--mechanism-key", "old/parked-idea",
            "--share", "0.3"))
        self.assertEqual(0, self.run_cmd(
            "park", "--opp", "1", "--reason", "await recurrence"))
        areas = [
            {"area_key": "style-recalc", "marginal_share_pct": 0.6,
             "related_hotspots": [{"name": "blink::Child"}]},
            {"area_key": "layout", "marginal_share_pct": 0.5},
        ]
        for area in areas:
            area["source_refs"] = []
        captures = self.write_capture_summaries("scaffold", "deadbeef", areas)
        manifest = self.dir / "scaffold-areas.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(manifest)))
        scaffolded = json.loads(manifest.read_text())
        self.assertEqual(
            ["style-recalc", "layout"],
            [area["area_key"] for area in scaffolded["areas"]],
        )
        self.assertTrue(all(
            area["disposition"] == "discover"
            and len(area["source_refs"]) == 2
            for area in scaffolded["areas"]
        ))
        self.assertEqual(
            ["not-recurrent"],
            [item["disposition"] for item in scaffolded["parked_mechanisms"]],
        )
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "scaffold", "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository"))
        self.assertEqual(2, len([
            opp for opp in self.ledger()["opportunities"]
            if opp["kind"] == "discovery"
        ]))

    def test_decompose_scaffold_prefills_primary_accounting(self):
        discovery = self.record_profile(
            "profile-1", related_hotspots=["blink::Inner"]
        )[0]
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(discovery), "--to", "investigating"))
        skeleton = self.dir / "decompose-skeleton.json"
        self.assertEqual(0, self.run_cmd(
            "decompose-scaffold", "--opp", str(discovery),
            "--out", str(skeleton)))
        scaffolded = json.loads(skeleton.read_text())
        self.assertEqual(2, len(scaffolded["paths"]))
        self.assertTrue(all(
            row["disposition"] == "" and row["evidence"] == ""
            and all(ref["accounting"] == "primary" for ref in row["work_refs"])
            for row in scaffolded["paths"]
        ))
        # An unedited scaffold cannot be recorded.
        self.assertEqual(1, self.run_cmd(
            "decompose", "--opp", str(discovery), "--children", str(skeleton)))
        for row in scaffolded["paths"]:
            hotspots = {ref["hotspot_key"] for ref in row["work_refs"]}
            if hotspots == {"@root"}:
                row["disposition"] = "mandatory"
                row["evidence"] = "root decision is mandatory"
            else:
                row["disposition"] = "novel"
                row["mechanism_key"] = "blink/inner-fast-path"
                row["evidence"] = "counter-verified avoidable work"
        scaffolded["accounting_evidence"] = "every hotspot dispositioned"
        skeleton.write_text(json.dumps(scaffolded))
        self.assertEqual(0, self.run_cmd(
            "decompose", "--opp", str(discovery), "--children", str(skeleton)))

    def write_context_capture_summaries(self, profile_id, entry_keys_by_capture):
        summaries = []
        for capture_id, keys in entry_keys_by_capture.items():
            def display(key):
                semantic = campaign.semantic_entry_identity(key)
                return semantic.split(":", 1)[1]
            frontier = [{
                "entry_key": key,
                "kind": "context" if key.startswith("context:") else "symbol",
                "name": display(key),
                "marginal_share": 0.005,
                "related_hotspots": [],
            } for key in keys]
            local_results = self.dir / capture_id
            artifact = (
                local_results / "analysis" / "full" / "candidate_frontier.json"
            )
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps({
                "quality": {"accepted": True},
                "selection": {
                    "inventory_complete": True,
                    "min_inclusive_share": 0.001,
                    "min_marginal_share": 0.001,
                },
                "frontier": frontier,
                "overlapping_alternatives": [],
            }))
            inventory = [{
                "entry_key": key,
                "work_items": [{
                    "hotspot_key": "@root",
                    "semantic_key": f"symbol:{display(key)}",
                    "measured_share_pct": 0.5,
                }],
            } for key in keys]
            summaries.append({
                "mode": "profile",
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
                "full_candidate_frontier_json": str(artifact),
            })
        path = self.dir / f"captures-{profile_id}.json"
        path.write_text(json.dumps(summaries))
        return path

    def run_profile(self, profile_id, manifest, captures):
        return self.run_cmd(
            "profile", "--id", profile_id, "--sha", "deadbeef",
            "--areas", str(manifest), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations",
            "--allow-unverified-repository")

    def test_context_digest_drift_cannot_be_dropped_as_not_recurrent(self):
        captures = self.write_context_capture_summaries("ctx", {
            "ctx-1": ["context:blink::F::Run()@aaaa000000000000"],
            "ctx-2": ["context:blink::F::Run()@bbbb000000000000"],
        })
        manifest = self.dir / "ctx-drop.json"
        manifest.write_text(json.dumps({
            "areas": [],
            "source_exclusions": [
                {"capture_id": "ctx-1",
                 "entry_key": "context:blink::F::Run()@aaaa000000000000",
                 "category": "not-recurrent",
                 "evidence": "absent from capture 2"},
                {"capture_id": "ctx-2",
                 "entry_key": "context:blink::F::Run()@bbbb000000000000",
                 "category": "not-recurrent",
                 "evidence": "absent from capture 1"},
            ],
            "parked_mechanisms": [],
        }))
        self.assertEqual(1, self.run_profile("ctx", manifest, captures))

    def test_context_function_drift_cannot_be_dropped_as_not_recurrent(self):
        captures = self.write_context_capture_summaries("mixed", {
            "mixed-1": ["context:blink::F::Run()@aaaa000000000000"],
            "mixed-2": ["function:blink::F::Run()"],
        })
        manifest = self.dir / "mixed-drop.json"
        manifest.write_text(json.dumps({
            "areas": [],
            "source_exclusions": [
                {"capture_id": "mixed-1",
                 "entry_key": "context:blink::F::Run()@aaaa000000000000",
                 "category": "not-recurrent",
                 "evidence": "context aggregate absent from capture 2"},
                {"capture_id": "mixed-2",
                 "entry_key": "function:blink::F::Run()",
                 "category": "not-recurrent",
                 "evidence": "function aggregate absent from capture 1"},
            ],
            "parked_mechanisms": [],
        }))
        self.assertEqual(1, self.run_profile("mixed", manifest, captures))

        manifest.write_text(json.dumps({
            "areas": [{
                "area_key": "f-run",
                "anchor": "blink::F::Run()",
                "marginal_share_pct": 0.5,
                "disposition": "discover",
                "source_refs": [
                    {"capture_id": "mixed-1",
                     "entry_key": "context:blink::F::Run()@aaaa000000000000"},
                    {"capture_id": "mixed-2",
                     "entry_key": "function:blink::F::Run()"},
                ],
            }],
            "source_exclusions": [],
            "parked_mechanisms": [],
        }))
        self.assertEqual(0, self.run_profile("mixed", manifest, captures))

    def test_context_digest_drift_reconciles_as_one_area(self):
        captures = self.write_context_capture_summaries("ctx", {
            "ctx-1": ["context:blink::F::Run()@aaaa000000000000"],
            "ctx-2": ["context:blink::F::Run()@bbbb000000000000"],
        })
        manifest = self.dir / "ctx-area.json"
        manifest.write_text(json.dumps({
            "areas": [{
                "area_key": "f-run-context",
                "anchor": "blink::F::Run() under its hot caller",
                "marginal_share_pct": 0.5,
                "disposition": "discover",
                "source_refs": [
                    {"capture_id": "ctx-1",
                     "entry_key": "context:blink::F::Run()@aaaa000000000000"},
                    {"capture_id": "ctx-2",
                     "entry_key": "context:blink::F::Run()@bbbb000000000000"},
                ],
            }],
            "source_exclusions": [],
            "parked_mechanisms": [],
        }))
        self.assertEqual(0, self.run_profile("ctx", manifest, captures))
        discovery = self.ledger()["opportunities"][0]
        self.assertEqual(2, len(discovery["expected_work_refs"]))

    def test_profile_scaffold_reuses_area_key_across_context_digest_drift(self):
        captures = self.write_context_capture_summaries("p1", {
            "p1-1": ["context:blink::F::Run()@aaaa000000000000"],
            "p1-2": ["context:blink::F::Run()@bbbb000000000000"],
        })
        manifest = self.dir / "p1-area.json"
        manifest.write_text(json.dumps({
            "areas": [{
                "area_key": "custom-stable-area",
                "anchor": "blink::F::Run()",
                "marginal_share_pct": 0.5,
                "disposition": "discover",
                "source_refs": [
                    {"capture_id": "p1-1",
                     "entry_key": "context:blink::F::Run()@aaaa000000000000"},
                    {"capture_id": "p1-2",
                     "entry_key": "context:blink::F::Run()@bbbb000000000000"},
                ],
            }],
            "source_exclusions": [],
            "parked_mechanisms": [],
        }))
        self.assertEqual(0, self.run_profile("p1", manifest, captures))

        captures = self.write_context_capture_summaries("p2", {
            "p2-1": ["context:blink::F::Run()@cccc000000000000"],
            "p2-2": ["context:blink::F::Run()@dddd000000000000"],
        })
        scaffold = self.dir / "p2-scaffold.json"
        self.assertEqual(0, self.run_cmd(
            "profile-scaffold", "--capture-summaries", str(captures),
            "--out", str(scaffold)))
        scaffolded = json.loads(scaffold.read_text())
        self.assertEqual("custom-stable-area", scaffolded["areas"][0]["area_key"])

        scaffolded["areas"][0]["area_key"] = "silent-rename"
        scaffold.write_text(json.dumps(scaffolded))
        self.assertEqual(1, self.run_profile("p2", scaffold, captures))

    def test_surplus_context_needs_area_backed_context_variant(self):
        entry_keys = {
            "ctx-1": [
                "context:blink::F::Run()@aaaa000000000000",
                "context:blink::F::Run()@cccc000000000000",
            ],
            "ctx-2": ["context:blink::F::Run()@bbbb000000000000"],
        }
        area = {
            "area_key": "f-run-context",
            "anchor": "blink::F::Run() hot context",
            "marginal_share_pct": 0.5,
            "disposition": "discover",
            "source_refs": [
                {"capture_id": "ctx-1",
                 "entry_key": "context:blink::F::Run()@aaaa000000000000"},
                {"capture_id": "ctx-2",
                 "entry_key": "context:blink::F::Run()@bbbb000000000000"},
            ],
        }
        surplus = {
            "capture_id": "ctx-1",
            "entry_key": "context:blink::F::Run()@cccc000000000000",
            "category": "context-variant",
            "evidence": "surplus same-symbol caller context",
        }
        captures = self.write_context_capture_summaries("ctx", entry_keys)
        manifest = self.dir / "ctx-variant.json"
        manifest.write_text(json.dumps({
            "areas": [area],
            "source_exclusions": [surplus],
            "parked_mechanisms": [],
        }))
        self.assertEqual(0, self.run_profile("ctx", manifest, captures))
        # Without the area, a context-variant exclusion has nothing covering
        # the symbol and must be refused.
        orphan = dict(surplus)
        manifest.write_text(json.dumps({
            "areas": [area],
            "source_exclusions": [
                orphan,
                {"capture_id": "ctx-1",
                 "entry_key": "context:blink::G::Run()@dddd000000000000",
                 "category": "context-variant",
                 "evidence": "no sibling area exists"},
            ],
            "parked_mechanisms": [],
        }))
        self.assertEqual(1, self.run_profile("ctx-2", manifest, captures))

    def test_full_lifecycle_gates(self):
        opp = self.add_opp()
        # Cannot skip straight to implementing.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        # sized requires ceiling + evidence.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "sized"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "sized",
            "--ceiling", "0.4", "--evidence", "counter shows 12k avoidable recalcs"))
        self.assertEqual(0, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        # review requires tests.
        self.assertEqual(1, self.run_cmd("advance", "--opp", str(opp), "--to", "review"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "review",
            "--tests", "blink_unittests StyleEngine*, wpt css/"))
        # landed blocked without both PASS verdicts.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS"))
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        self.assertEqual(0, self.run_cmd(
            "review", "--opp", str(opp), "--role", "adversary", "--verdict", "PASS"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))
        data = self.ledger()
        self.assertEqual("landed", data["opportunities"][0]["status"])
        self.assertIn("Landed: 1/20", self.status_text())

    def test_review_fail_and_rework(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.run_cmd("review", "--opp", str(opp), "--role", "adversary",
                     "--verdict", "FAIL", "--notes", "event order change")
        # Rework path clears verdicts.
        self.assertEqual(0, self.run_cmd("advance", "--opp", str(opp), "--to", "implementing"))
        data = self.ledger()["opportunities"][0]
        self.assertEqual(1, data["rework_rounds"])
        self.assertEqual({}, data["reviews"])
        # Second review round: a stale FAIL cannot leak through.
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef"))

    def test_reject_park_reopen(self):
        opp = self.add_opp()
        self.assertEqual(1, self.run_cmd(
            "reject", "--opp", str(opp), "--reason", "off critical path",
            "--evidence", "not yet investigated"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "investigating"))
        self.assertEqual(0, self.run_cmd(
            "reject", "--opp", str(opp), "--reason", "off critical path",
            "--evidence", "source trace proves no scored caller"))
        self.assertIn("off critical path", self.status_text())
        self.assertEqual(1, self.run_cmd("reopen", "--opp", str(opp)))
        self.assertEqual(0, self.run_cmd(
            "reopen", "--opp", str(opp), "--contradicts-prior-evidence",
            "--reason", "fresh counter disproves the earlier assumption"))
        self.assertEqual("candidate", self.ledger()["opportunities"][0]["status"])

    def test_review_only_in_review_state(self):
        opp = self.add_opp()
        self.assertEqual(1, self.run_cmd(
            "review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS"))

    def test_checkpoint_and_next_ordering(self):
        self.add_opp(anchor="small", share="0.2")
        self.add_opp(anchor="large", share="0.9")
        self.assertEqual(0, self.run_cmd(
            "checkpoint", "--delta", "1.8", "--ci-low", "0.9", "--ci-high", "2.7"))
        text = self.status_text()
        self.assertIn("+1.80%", text)
        candidates = campaign.Ledger(self.dir).load().next_candidates(2)
        self.assertEqual("large", candidates[0]["anchor"])

    def test_squeeze_only_while_implementing(self):
        opp = self.add_opp()
        self.assertEqual(1, self.run_cmd("squeeze", "--opp", str(opp)))
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.assertEqual(0, self.run_cmd(
            "squeeze", "--opp", str(opp), "--note", "hoisted allocation"))
        self.assertEqual(0, self.run_cmd("squeeze", "--opp", str(opp)))
        self.assertEqual(2, self.ledger()["opportunities"][0]["squeeze_rounds"])

    def test_rework_limit_enforced(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        for _ in range(2):
            self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
            self.assertEqual(0, self.run_cmd(
                "advance", "--opp", str(opp), "--to", "implementing"))
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        # Third rework round is blocked without the override.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "implementing"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", str(opp), "--to", "implementing",
            "--override-rework-limit", "--notes", "reviewer error, justified"))

    def test_landed_is_terminal(self):
        opp = self.add_opp()
        self.run_cmd("advance", "--opp", str(opp), "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", str(opp), "--to", "implementing")
        self.run_cmd("advance", "--opp", str(opp), "--to", "review", "--tests", "unit")
        self.run_cmd("review", "--opp", str(opp), "--role", "skeptic", "--verdict", "PASS")
        self.run_cmd("review", "--opp", str(opp), "--role", "adversary", "--verdict", "PASS")
        self.run_cmd("advance", "--opp", str(opp), "--to", "landed", "--commit", "deadbeef")
        self.assertEqual(1, self.run_cmd(
            "reject", "--opp", str(opp), "--reason", "nope",
            "--evidence", "late evidence"))


class GitReviewVerificationTest(unittest.TestCase):
    """Landing must prove the commit is exactly the reviewed diff."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = pathlib.Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.dir = pathlib.Path(self.tmp.name) / "camp"
        self.prev_cwd = os.getcwd()
        os.chdir(self.repo)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        (self.repo / "f.txt").write_text("base\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.branch = self.git("rev-parse", "--abbrev-ref", "HEAD")
        self.run_cmd("init", "--name", "gittest", "--branch", self.branch)
        self.run_cmd("add", "--anchor", "anchor", "--share", "0.5")
        self.run_cmd("advance", "--opp", "1", "--to", "sized",
                     "--ceiling", "0.3", "--evidence", "oracle")
        self.run_cmd("advance", "--opp", "1", "--to", "implementing")

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.tmp.cleanup()

    def git(self, *argv):
        return subprocess.run(["git"] + list(argv), check=True,
                              capture_output=True, text=True).stdout.strip()

    def run_cmd(self, *argv):
        return campaign.main(["--dir", str(self.dir)] + list(argv))

    def enter_review_with(self, content, path="f.txt"):
        target = self.repo / path
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content)
        # The implementer stages the candidate before handing it to review.
        self.git("add", "-A")
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit"))

    def pass_reviews(self):
        self.run_cmd("review", "--opp", "1", "--role", "skeptic", "--verdict", "PASS")
        self.run_cmd("review", "--opp", "1", "--role", "adversary", "--verdict", "PASS")

    def capture_summaries(self, profile_id, sha):
        path = self.dir / f"captures-{profile_id}.json"
        summaries = []
        for index in (1, 2):
            capture_id = f"{profile_id}-{index}"
            local_results = self.dir / capture_id
            artifact = local_results / "analysis" / "full" / "candidate_frontier.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(json.dumps({
                "quality": {"accepted": True},
                "selection": {"inventory_complete": True,
                              "min_inclusive_share": 0.001,
                              "min_marginal_share": 0.001},
                "frontier": [],
            }))
            summaries.append({
                "mode": "profile",
                "capture_id": capture_id, "sha": sha,
                "quality_rejected": False,
                "enable_features": "Speedometer3Optimizations",
                "stories": "all", "share_floor_pct": 0.1,
                "repetitions": 2,
                "inventory_complete": True,
                "analyzer_min_inclusive_share": 0.001,
                "analyzer_min_marginal_share": 0.001,
                "frontier_entries": [], "frontier_inventory": [],
                "frontier_count": 0,
                "local_results": str(local_results),
                "remote_perf_data": f"/remote/{capture_id}/perf_sampling.data",
                "full_candidate_frontier_json": str(artifact),
            })
        path.write_text(json.dumps(summaries))
        return path

    def test_profile_must_match_campaign_branch_head(self):
        areas = self.dir / "empty-areas.json"
        areas.write_text(
            '{"areas":[],"source_exclusions":[],"parked_mechanisms":[]}'
        )
        self.assertEqual(0, self.run_cmd(
            "reject", "--opp", "1", "--reason", "not in this empty frontier",
            "--evidence", "profile preparation fixture"))
        old_head = self.git("rev-parse", "HEAD")
        captures = self.capture_summaries("p1", old_head)
        self.assertEqual(0, self.run_cmd(
            "profile", "--id", "p1", "--sha", old_head,
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations"))
        self.assertEqual(0, self.run_cmd("audit-exhaustion"))
        self.git("checkout", "-qb", "audit-side")
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))
        self.git("checkout", "-q", self.branch)
        dirty = self.repo / "dirty.txt"
        dirty.write_text("dirty\n")
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))
        dirty.unlink()
        (self.repo / "new.txt").write_text("new head\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "new head")
        self.assertEqual(1, self.run_cmd("audit-exhaustion"))
        captures = self.capture_summaries("p2", old_head)
        self.assertEqual(1, self.run_cmd(
            "profile", "--id", "p2", "--sha", old_head,
            "--areas", str(areas), "--capture-summaries", str(captures),
            "--enable-features", "Speedometer3Optimizations"))

    def test_matching_commit_lands(self):
        self.enter_review_with("optimized v1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_tampered_content_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        # Content changes after review before committing.
        (self.repo / "f.txt").write_text("optimized v2 sneaky\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))
        # The escape hatch still works when explicitly requested.
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha,
            "--skip-review-verification"))

    def test_wrong_parent_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        (self.repo / "g.txt").write_text("unrelated\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "unrelated")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_binary_tamper_is_rejected(self):
        # Binary replacement after review: a filtered-text diff digest would
        # miss this; the tree hash must not.
        self.enter_review_with(b"\x00\x01BINv1\x02", path="blob.bin")
        (self.repo / "blob.bin").write_bytes(b"\x00\x01BINv2\x02")
        self.git("add", "-A")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_matching_but_non_head_commit_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("commit", "-qm", "opt")
        reviewed_sha = self.git("rev-parse", "HEAD")
        (self.repo / "g.txt").write_text("later work\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "later")
        self.pass_reviews()
        # Parent and tree both match, but the commit is no longer HEAD.
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", reviewed_sha))

    def test_unstaged_review_entry_is_blocked(self):
        (self.repo / "f.txt").write_text("unstaged change\n")
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit"))
        self.assertEqual(0, self.run_cmd(
            "advance", "--opp", "1", "--to", "review", "--tests", "unit",
            "--allow-unstaged"))

    def test_wrong_branch_is_rejected(self):
        self.enter_review_with("optimized v1\n")
        self.git("checkout", "-qb", "side-branch")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.assertEqual(1, self.run_cmd(
            "advance", "--opp", "1", "--to", "landed", "--commit", sha))

    def test_revert_after_landing(self):
        # Revert applies only to landed opportunities.
        self.assertEqual(1, self.run_cmd(
            "revert", "--opp", "1", "--revert-commit", "deadbeef",
            "--reason", "regression"))
        self.enter_review_with("optimized v1\n")
        self.git("commit", "-qm", "opt")
        sha = self.git("rev-parse", "HEAD")
        self.pass_reviews()
        self.run_cmd("advance", "--opp", "1", "--to", "landed", "--commit", sha)
        self.git("revert", "--no-edit", "HEAD")
        revert_sha = self.git("rev-parse", "HEAD")
        self.assertEqual(0, self.run_cmd(
            "revert", "--opp", "1", "--revert-commit", revert_sha,
            "--reason", "stat-sig regression on Editor-TipTap"))
        with open(self.dir / "ledger.json") as f:
            data = json.load(f)
        opp = data["opportunities"][0]
        self.assertEqual("reverted", opp["status"])
        self.assertEqual(revert_sha, opp["revert_commit"])
        # Reverted opportunities leave the landed count; retry requires new
        # evidence explicitly contradicting the prior result.
        self.assertEqual(1, self.run_cmd("reopen", "--opp", "1"))
        self.assertEqual(0, self.run_cmd(
            "reopen", "--opp", "1", "--contradicts-prior-evidence",
            "--reason", "new correctness design avoids the regression"))
        with open(self.dir / "ledger.json") as ledger_file:
            reopened = json.load(ledger_file)
        self.assertEqual("candidate", reopened["opportunities"][0]["status"])


if __name__ == "__main__":
    unittest.main()
