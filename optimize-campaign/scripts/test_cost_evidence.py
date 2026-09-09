#!/usr/bin/env python3
"""Cost packets and the algorithmic disposition."""
import json
import pathlib
import tempfile
import unittest

import campaign
import cost_evidence


class CostEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.collapsed = self.dir / "profile.collapsed"
        self.collapsed.write_text(
            "main;Layout(int);MinMax();Shape();HarfBuzz() 60\n"
            "main;Layout(int);MinMax();LineBreak() 30\n"
            "main;Layout(int);Place() 10\n"
            "main;Paint() 100\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_packet_reduces_time_by_child_and_leaf(self):
        packet = cost_evidence.build_cost_packet([self.collapsed], "Layout(int)", "S", "p")
        self.assertAlmostEqual(50.0, packet["row_share_pct"])
        children = {e["frame"]: e["fraction_of_row"] for e in packet["children"]}
        leaves = {e["frame"]: e["fraction_of_row"] for e in packet["leaves"]}
        self.assertAlmostEqual(0.9, children["MinMax()"])
        self.assertAlmostEqual(0.1, children["Place()"])
        self.assertAlmostEqual(0.6, leaves["HarfBuzz()"])
        bound, unmatched = cost_evidence.avoided_fraction(packet, ["MinMax", "Nowhere"])
        self.assertAlmostEqual(0.9, bound)
        self.assertEqual(["Nowhere"], unmatched)
        with self.assertRaises(cost_evidence.CostError):
            cost_evidence.build_cost_packet([self.collapsed], "Missing()", "S")

    def test_algorithmic_rows_are_bounded_by_the_packet_and_re_derive(self):
        packet = cost_evidence.build_cost_packet([self.collapsed], "Layout(int)", "S", "p")
        path = self.dir / "evidence" / "cost_layout.json"
        path.parent.mkdir()
        path.write_text(json.dumps(packet))
        ref = {"path": "evidence/cost_layout.json", "sha256": campaign.sha256_file(path)}
        item = {"anchor": "Layout(int)", "disposition": "algorithmic", "investigation_layer": 3,
                "mechanism_key": "layout/incremental-minmax", "cost_evidence": ref,
                "avoided_frames": ["MinMax"], "estimated_avoidable_fraction": 0.85,
                "algorithm_hypothesis": ("BlockNode::ComputeMinMaxSizes recomputes the min-content of the whole "
                                         "editor on every keystroke; an incremental one reshapes the edited "
                                         "paragraph only, avoiding 90% of the row.")}
        campaign.require_algorithmic_fields(item, 1)
        campaign.bind_cost_evidence(item, "S", 0.85, self.dir)
        self.assertAlmostEqual(0.9, item["cost_summary"]["avoided_fraction_of_row"])
        with self.assertRaisesRegex(campaign.CampaignError, "bounded by the cost packet"):
            campaign.bind_cost_evidence(item, "S", 0.95, self.dir)
        item["avoided_frames"] = ["Nowhere"]
        with self.assertRaisesRegex(campaign.CampaignError, "not in its cost packet"):
            campaign.bind_cost_evidence(item, "S", 0.5, self.dir)
        # An edited packet is not evidence.
        data = json.loads(path.read_text()); data["children"][0]["fraction_of_row"] = 0.99
        edited = self.dir / "evidence" / "cost_edited.json"; edited.write_text(json.dumps(data))
        item["avoided_frames"] = ["MinMax"]
        item["cost_evidence"] = {"path": "evidence/cost_edited.json", "sha256": campaign.sha256_file(edited)}
        campaign._COST_PROVENANCE_CACHE.clear()
        with self.assertRaisesRegex(campaign.CampaignError, "not produced by cost_evidence.py|differs from the re-derived"):
            campaign.bind_cost_evidence(item, "S", 0.5, self.dir)
        # Missing fields are refused before any packet is opened.
        for field in ("cost_evidence", "avoided_frames", "algorithm_hypothesis"):
            broken = dict(item); broken.pop(field)
            with self.assertRaisesRegex(campaign.CampaignError, field):
                campaign.require_algorithmic_fields(broken, 1)
        broken = dict(item); broken["investigation_layer"] = 2
        with self.assertRaisesRegex(campaign.CampaignError, "investigation_layer 3 or 4"):
            campaign.require_algorithmic_fields(broken, 1)

    def test_large_rows_closed_by_count_show_where_their_time_goes(self):
        story_dir = self.dir / "results" / "analysis" / "stories" / "S"
        story_dir.mkdir(parents=True)
        artifact = story_dir / "candidate_frontier.json"; artifact.write_text("{}")
        (story_dir / "profile.collapsed").write_text(self.collapsed.read_text())
        profile = {"id": "p", "capture_provenance": [{"capture_id": "c1",
                   "story_frontiers": [{"story": "S", "artifact": str(artifact)}]}]}
        big = {"anchor": "Layout(int)", "disposition": "mandatory",
               "redundancy_evidence": {"path": "evidence/a.json"}}
        # Nothing beneath it, no algorithmic row, no investigation: refused.
        with self.assertRaisesRegex(campaign.CampaignError, "closes by count at 50.00%"):
            campaign.enforce_large_mandatory_rows([big], {1: 50.0}, profile, "S")
        # A row beneath it bound to another packet: the search moved down.
        below = {"anchor": "MinMax()", "disposition": "mandatory",
                 "redundancy_evidence": {"path": "evidence/b.json"}}
        campaign.enforce_large_mandatory_rows([big, below], {1: 50.0, 2: 45.0}, profile, "S")
        self.assertEqual([2], big["probed_below"])
        # A row beneath it on the same packet does not count.
        same = dict(below); same["redundancy_evidence"] = {"path": "evidence/a.json"}
        big.pop("probed_below")
        with self.assertRaisesRegex(campaign.CampaignError, "closes by count"):
            campaign.enforce_large_mandatory_rows([big, same], {1: 50.0, 2: 45.0}, profile, "S")
        # An algorithmic row on the same function satisfies it.
        alg = {"anchor": "Layout(int)", "disposition": "algorithmic"}
        campaign.enforce_large_mandatory_rows([big, alg], {1: 50.0}, profile, "S")
        # So does an investigation with numbers.
        big["investigation"] = {"hypotheses": ["incremental min-content"],
                                "falsifications": ["the edited paragraph is 98% of the text; 2% saving"],
                                "stop_reason": "below floor"}
        campaign.enforce_large_mandatory_rows([big], {1: 50.0}, profile, "S")
        # Small rows are left alone.
        campaign.enforce_large_mandatory_rows([{"anchor": "Paint()", "disposition": "mandatory"}], {1: 4.0}, profile, "S")


if __name__ == "__main__":
    unittest.main()
