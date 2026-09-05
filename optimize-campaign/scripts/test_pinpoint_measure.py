#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import math
import unittest
from unittest import mock

import pinpoint_measure


class PinpointMeasureTest(unittest.TestCase):

    def test_extract_cl_issue_number(self):
        self.assertEqual(
            pinpoint_measure.extract_cl_issue_number("https://chromium-review.googlesource.com/c/chromium/src/+/8349622"),
            8349622,
        )
        self.assertEqual(
            pinpoint_measure.extract_cl_issue_number("https://chromium-review.googlesource.com/8349622"),
            8349622,
        )
        self.assertEqual(
            pinpoint_measure.extract_cl_issue_number("8349622"),
            8349622,
        )
        self.assertEqual(
            pinpoint_measure.extract_cl_issue_number(8349622),
            8349622,
        )
        self.assertIsNone(pinpoint_measure.extract_cl_issue_number(""))

    def test_student_t_math(self):
        # Known critical value: df=10, alpha=0.05 -> t_crit ~ 2.228
        crit10 = pinpoint_measure.student_t_crit_95(10)
        self.assertAlmostEqual(crit10, 2.228, places=2)

        # Large df approaches normal critical 1.960
        crit1000 = pinpoint_measure.student_t_crit_95(1000)
        self.assertAlmostEqual(crit1000, 1.960, places=2)

        # Known p-value for t=1.96, large df ~ 0.05
        p = pinpoint_measure.student_t_p_value(1.96, 1000)
        self.assertAlmostEqual(p, 0.05, places=2)

    def test_extract_histogram_text(self):
        html_input = (
            '<html><body>'
            '<div id="histogram-json-data"><!--\n'
            '{"type": "GenericSet", "guid": "g1"}\n'
            '--></div></body></html>'
        )
        extracted = pinpoint_measure.extract_histogram_text(html_input)
        self.assertEqual(extracted, '{"type": "GenericSet", "guid": "g1"}')

    def test_parse_and_analyze_results_pass(self):
        # Generate synthetic histograms with slight positive score and flat story
        lines = [
            json.dumps({"guid": "label_base", "values": ["base"]}),
            json.dumps({"guid": "label_exp", "values": ["exp"]}),
            # Score base: 10 samples around 40.0
        ]
        for v in [39.8, 40.0, 40.2, 39.9, 40.1, 40.0, 39.8, 40.2, 40.0, 40.0]:
            lines.append(json.dumps({
                "name": "Score",
                "unit": "unitless_biggerIsBetter",
                "diagnostics": {"labels": "label_base"},
                "running": [10, 0, 0, v],
            }))
        # Score exp: 10 samples around 40.1
        for v in [40.0, 40.1, 40.3, 40.0, 40.2, 40.1, 40.0, 40.2, 40.1, 40.1]:
            lines.append(json.dumps({
                "name": "Score",
                "unit": "unitless_biggerIsBetter",
                "diagnostics": {"labels": "label_exp"},
                "running": [10, 0, 0, v],
            }))

        raw_data = "\n".join(lines)
        res = pinpoint_measure.parse_and_analyze_results(
            raw_data, job_id="job123", cl_url="https://crrev.com/c/123", bot="mac-m1"
        )
        self.assertEqual(res["verdict"], "INCONCLUSIVE")
        self.assertEqual(len(res["regressions"]), 0)
        self.assertIn("Score", res["metrics"])
        self.assertAlmostEqual(res["score"]["base_mean"], 40.0, places=1)
        self.assertEqual(res["job_id"], "job123")
        self.assertEqual(res["cl_url"], "https://crrev.com/c/123")

    def test_parse_and_analyze_results_regression_fail(self):
        # Generate synthetic histograms where a duration metric regresses significantly (higher ms)
        lines = [
            json.dumps({"guid": "label_base", "values": ["base"]}),
            json.dumps({"guid": "label_exp", "values": ["exp"]}),
        ]
        # Story base: ms around 10.0
        for _ in range(20):
            lines.append(json.dumps({
                "name": "StoryA",
                "unit": "ms_smallerIsBetter",
                "diagnostics": {"labels": "label_base"},
                "running": [10, 0, 0, 10.0],
            }))
        # Story exp: ms around 15.0 (significant regression)
        for _ in range(20):
            lines.append(json.dumps({
                "name": "StoryA",
                "unit": "ms_smallerIsBetter",
                "diagnostics": {"labels": "label_exp"},
                "running": [10, 0, 0, 15.0],
            }))

        raw_data = "\n".join(lines)
        res = pinpoint_measure.parse_and_analyze_results(raw_data)
        self.assertEqual(res["verdict"], "INVALID")
        self.assertIn("StoryA", res["regressions"])
        self.assertTrue(res["metrics"]["StoryA"]["is_regression"])

    @mock.patch("pinpoint_measure.run_cmd")
    def test_abandon_cl_calls_git_cl(self, mock_run):
        pinpoint_measure.abandon_cl("https://chromium-review.googlesource.com/c/chromium/src/+/8349622", reason="Gate failed")
        mock_run.assert_called_once_with(
            ["git", "cl", "set-close", "-i", "8349622"],
            cwd=None,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
