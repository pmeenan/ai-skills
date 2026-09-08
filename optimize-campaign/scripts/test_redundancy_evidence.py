#!/usr/bin/env python3
"""Redundancy-probe reduction and the avoidable-fraction bound it supports."""
import json
import pathlib
import tempfile
import unittest

import redundancy_evidence as re_


def row(site="style/resolve", group="1|TodoMVC-React", calls=100, applicable=40,
        distinct=25, repeated=75, overflow=0, timed=True, ns_per_call=10,
        applicable_ns=None, repeated_ns=None):
    data = {
        "schema_version": 1, "block": 1, "capture_nonce": "n", "site": site,
        "group": group, "pid": 1, "tid": 1, "emitted_monotonic_raw_ns": 5,
        "calls": calls, "applicable_calls": applicable, "distinct_inputs": distinct,
        "repeated_inputs": repeated, "overflow": overflow,
        "thread_affinity_violations": 0,
    }
    if timed:
        data.update({
            "timed_calls": calls, "total_ns": calls * ns_per_call,
            "applicable_ns": applicable * ns_per_call if applicable_ns is None else applicable_ns,
            "repeated_ns": repeated * ns_per_call if repeated_ns is None else repeated_ns,
        })
    return "[SP3_REDUNDANCY_ROW] " + json.dumps(data) + "\n"


class RedundancyEvidenceTest(unittest.TestCase):
    def packet(self, lines, site="style/resolve", story="TodoMVC-React"):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "browser.chromium.log"
            log.write_text("noise line\n" + "".join(lines))
            out = pathlib.Path(tmp) / "packet.json"
            rc = re_.main(["--site", site, "--symbol", "blink::Probe(", "--target-story", story,
                           "--browser-log", str(log), "--out", str(out)])
            return rc, (json.loads(out.read_text()) if out.exists() else None)

    def test_reduces_only_the_target_story(self):
        rc, packet = self.packet([
            row(), row(group="2|TodoMVC-React", calls=200, applicable=100, distinct=50, repeated=150),
            row(group="1|TodoMVC-Vue", calls=999, applicable=999, distinct=1, repeated=998),
            row(site="other/site", calls=5, applicable=5, distinct=5, repeated=0),
        ])
        self.assertEqual(0, rc)
        self.assertEqual(2, packet["repetitions"])
        self.assertEqual(300, packet["calls_total"])
        self.assertAlmostEqual(140 / 300, packet["applicable_fraction"])
        self.assertAlmostEqual(225 / 300, packet["repeat_fraction"])
        self.assertAlmostEqual(150.0, packet["calls_per_repetition_mean"])
        self.assertFalse(packet["distinct_overflow"])
        self.assertAlmostEqual(0.75, re_.supported_avoidable_fraction(packet))
        self.assertEqual("redundancy-evidence", packet["kind"])
        self.assertTrue(packet["sources"][0]["sha256"])

    def test_time_weighting_needs_every_call_timed(self):
        # Calls carry time: the packet reports time fractions and the closing
        # bound is the larger of the count and time bounds.
        rc, packet = self.packet([row(applicable=90, repeated=10, applicable_ns=50, repeated_ns=900)])
        self.assertEqual(0, rc)
        self.assertTrue(packet["time_weighted"])
        self.assertAlmostEqual(0.05, packet["applicable_time_fraction"])
        self.assertAlmostEqual(0.90, packet["repeat_time_fraction"])
        self.assertAlmostEqual(0.90, re_.supported_avoidable_fraction(packet))
        self.assertAlmostEqual(0.05, re_.hypothesis_bound(packet, "applicable"))
        self.assertAlmostEqual(0.10, re_.hypothesis_bound(packet, "repeat"))
        # Rows without time, or with some calls untimed, are count-only.
        rc, packet = self.packet([row(timed=False)])
        self.assertFalse(packet["time_weighted"])
        self.assertIsNone(packet["applicable_time_fraction"])
        self.assertIsNone(re_.hypothesis_bound(packet, "applicable"))
        rc, packet = self.packet([row(), row(group="2|TodoMVC-React", timed=False)])
        self.assertFalse(packet["time_weighted"])

    def test_missing_story_or_site_fails(self):
        rc, packet = self.packet([row(group="1|TodoMVC-Vue")])
        self.assertEqual(1, rc)
        self.assertIsNone(packet)

    def test_overflow_limits_support_to_applicability(self):
        rc, packet = self.packet([row(calls=100, applicable=10, distinct=50, repeated=50, overflow=1)])
        self.assertEqual(0, rc)
        self.assertTrue(packet["distinct_overflow"])
        self.assertAlmostEqual(0.10, re_.supported_avoidable_fraction(packet))
        self.assertIsNone(packet["measured_avoidable_fraction_upper"])

    def test_load_packet_rejects_other_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "x.json"
            path.write_text(json.dumps({"kind": "something-else"}))
            with self.assertRaises(ValueError):
                re_.load_packet(path)


if __name__ == "__main__":
    unittest.main()
