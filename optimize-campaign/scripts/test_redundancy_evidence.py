#!/usr/bin/env python3
"""Redundancy-probe reduction and the avoidable-fraction bound it supports."""
import json
import pathlib
import tempfile
import unittest

import redundancy_evidence as re_


def row(site="style/resolve", group="1|TodoMVC-React", calls=100, applicable=40,
        distinct=25, repeated=75, overflow=0):
    return (
        "[SP3_REDUNDANCY_ROW] "
        + json.dumps({
            "schema_version": 1, "block": 1, "capture_nonce": "n", "site": site,
            "group": group, "pid": 1, "tid": 1, "emitted_monotonic_raw_ns": 5,
            "calls": calls, "applicable_calls": applicable, "distinct_inputs": distinct,
            "repeated_inputs": repeated, "overflow": overflow,
            "thread_affinity_violations": 0,
        })
        + "\n"
    )


class RedundancyEvidenceTest(unittest.TestCase):
    def packet(self, lines, site="style/resolve", story="TodoMVC-React"):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "browser.chromium.log"
            log.write_text("noise line\n" + "".join(lines))
            out = pathlib.Path(tmp) / "packet.json"
            rc = re_.main(["--site", site, "--target-story", story,
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
