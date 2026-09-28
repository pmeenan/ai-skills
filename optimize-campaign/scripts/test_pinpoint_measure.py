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


class PlanInvocationTest(unittest.TestCase):
    def plan(self, **identity):
        return {
            "identity": {
                "patchset_url": "https://chromium-review.googlesource.com/c/chromium/src/+/1/2",
                "baseline_sha": "a" * 40,
                "benchmark": "speedometer3",
                "feature": "Speedometer3MatchedRulesCache",
                **identity,
            },
            "statistics": {"blocks": 150},
        }

    def args(self, base, experiment):
        import argparse
        return argparse.Namespace(
            cl="https://chromium-review.googlesource.com/c/chromium/src/+/1/2",
            base_commit="a" * 40, benchmark="speedometer3", attempts=150,
            base_extra_args=base, experiment_extra_args=experiment,
        )

    def test_plan_without_base_features_keeps_single_arm_flag(self):
        plan = self.plan()
        self.assertTrue(pinpoint_measure.plan_invocation_matches(
            self.args("", "--enable-features=Speedometer3MatchedRulesCache"), plan
        ))
        self.assertFalse(pinpoint_measure.plan_invocation_matches(
            self.args("--enable-features=Speedometer3Optimizations",
                      "--enable-features=Speedometer3MatchedRulesCache"), plan
        ))
        self.assertTrue(pinpoint_measure.plan_invocation_matches(
            self.args("", "--enable-features=Speedometer3MatchedRulesCache"),
            self.plan(base_features=[]),
        ))

    def test_plan_with_base_features_enables_them_on_both_arms(self):
        plan = self.plan(base_features=["Speedometer3Optimizations"])
        base = "--enable-features=Speedometer3Optimizations"
        experiment = (
            "--enable-features=Speedometer3Optimizations,"
            "Speedometer3MatchedRulesCache"
        )
        self.assertEqual(
            (base, experiment),
            pinpoint_measure.planned_extra_args(plan["identity"]),
        )
        self.assertTrue(pinpoint_measure.plan_invocation_matches(
            self.args(base, experiment), plan
        ))
        for wrong in (
            ("", experiment),
            (base, "--enable-features=Speedometer3MatchedRulesCache"),
            (base, base),
        ):
            self.assertFalse(pinpoint_measure.plan_invocation_matches(
                self.args(*wrong), plan
            ))

    def test_plan_feature_listed_as_base_is_refused(self):
        plan = self.plan(base_features=["Speedometer3MatchedRulesCache"])
        with self.assertRaises(ValueError):
            pinpoint_measure.planned_extra_args(plan["identity"])
        self.assertFalse(pinpoint_measure.plan_invocation_matches(
            self.args("--enable-features=Speedometer3MatchedRulesCache",
                      "--enable-features=Speedometer3MatchedRulesCache,"
                      "Speedometer3MatchedRulesCache"), plan
        ))

    def test_resolve_target_reads_tester_isolate(self):
        import tempfile, pathlib
        with tempfile.TemporaryDirectory() as root:
            gen = pathlib.Path(root) / pinpoint_measure.PERF_DATA_GENERATOR
            gen.parent.mkdir(parents=True)
            gen.write_text(
                "TESTERS = {\n"
                "  'mac-m1_mini_2020-perf-pgo': {\n"
                "    'tests': [{\n"
                "        'isolate': 'performance_test_suite',\n"
                "    }],\n"
                "  },\n"
                "  'android-pixel6-perf-pgo': {\n"
                "    'tests': [\n"
                "      {\n"
                "        'isolate': 'performance_test_suite_android_trichrome_chrome_google_64_32_bundle',\n"
                "      }\n"
                "    ],\n"
                "  },\n"
                "}\n")
            self.assertEqual(
                "performance_test_suite_android_trichrome_chrome_google_64_32_bundle",
                pinpoint_measure.resolve_target("android-pixel6-perf-pgo", repo_root=root))
            self.assertEqual(
                "performance_test_suite",
                pinpoint_measure.resolve_target("mac-m1_mini_2020-perf-pgo", repo_root=root))
            self.assertEqual(
                "custom", pinpoint_measure.resolve_target("android-pixel6-perf-pgo", "custom", root))
            self.assertEqual(
                pinpoint_measure.DEFAULT_TARGET,
                pinpoint_measure.resolve_target("linux-perf-pgo", repo_root=root))
            with self.assertRaises(ValueError):
                pinpoint_measure.resolve_target("android-pixel4-perf-pgo", repo_root=root)

    def test_start_job_sends_resolved_target(self):
        sent = {}

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return b'{"jobId": "abc", "jobUrl": "u"}'

        def fake_urlopen(req, *a, **k):
            sent.update(dict(__import__("urllib.parse").parse.parse_qsl(req.data.decode())))
            return Resp()

        with mock.patch.object(pinpoint_measure, "get_auth_token", return_value=None), \
             mock.patch.object(pinpoint_measure.urllib.request, "urlopen", fake_urlopen):
            pinpoint_measure.start_pinpoint_job(
                "https://chromium-review.googlesource.com/c/chromium/src/+/1/2",
                bot="android-pixel6-perf-pgo", base_commit="a" * 40, target="bundle_x")
        self.assertEqual("bundle_x", sent["target"])
        self.assertEqual("android-pixel6-perf-pgo", sent["configuration"])


if __name__ == "__main__":
    unittest.main()
