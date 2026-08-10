#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Tests for run_ab_benchmark statistics and result parsing."""

import json
import math
import os
import tempfile
import unittest

import run_ab_benchmark as ab


class TCritTest(unittest.TestCase):
    def test_exact_values(self):
        self.assertAlmostEqual(2.776, ab.t_crit(4))   # 5 blocks
        self.assertAlmostEqual(2.571, ab.t_crit(5))   # 6 blocks
        self.assertAlmostEqual(2.262, ab.t_crit(9))   # 10 blocks
        self.assertAlmostEqual(2.145, ab.t_crit(14))  # 15 blocks

    def test_interpolation_floors_to_lower_df(self):
        self.assertAlmostEqual(2.060, ab.t_crit(27))

    def test_asymptote(self):
        self.assertAlmostEqual(1.960, ab.t_crit(500))
        self.assertAlmostEqual(0.842, ab.t_power(500))


class SummarizeTest(unittest.TestCase):
    def test_positive_shift_detected(self):
        diffs = [0.02, 0.021, 0.019, 0.022, 0.020]
        stats = ab.summarize_block_diffs(diffs)
        self.assertEqual(5, stats["n_blocks"])
        self.assertAlmostEqual(2.02, stats["delta_pct"], places=1)
        self.assertTrue(stats["is_stat_sig"])
        self.assertGreater(stats["mde_80_power_pct"],
                           stats["significance_threshold_pct"])

    def test_too_few_blocks(self):
        self.assertIsNone(ab.summarize_block_diffs([0.01]))


class PerStoryTest(unittest.TestCase):
    def block(self, a_time, b_time, story="TodoMVC-React"):
        return {
            "a_scores": [30.0], "b_scores": [30.0],
            "a_stories": [{story: a_time}],
            "b_stories": [{story: b_time}],
        }

    def test_sign_convention_lower_time_is_gain(self):
        # B is consistently 5% faster (lower time) -> positive delta.
        blocks = [self.block(100.0 * (1 + 0.001 * i), 95.0 * (1 + 0.001 * i))
                  for i in range(5)]
        stats = ab.per_story_stats(blocks)["TodoMVC-React"]
        self.assertGreater(stats["delta_pct"], 4.0)
        self.assertFalse(stats["stat_sig_regression"])

    def test_regression_flagged(self):
        # B is consistently 5% slower -> stat-sig regression, exceeds 2%.
        blocks = [self.block(100.0 * (1 + 0.001 * i), 105.0 * (1 + 0.001 * i))
                  for i in range(5)]
        stats = ab.per_story_stats(blocks)["TodoMVC-React"]
        self.assertLess(stats["delta_pct"], -4.0)
        self.assertTrue(stats["stat_sig_regression"])
        self.assertTrue(stats["exceeds_2pct_regression"])


class ParseTest(unittest.TestCase):
    def test_only_scalar_score_files_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Aggregate-style file (Score is a dict): must be ignored.
            agg_dir = os.path.join(tmp, "res", "stories")
            os.makedirs(agg_dir)
            with open(os.path.join(agg_dir, "speedometer_3.0.json"), "w") as f:
                json.dump({"Score": {"average": 35.0},
                           "TodoMVC-React": {"average": 20.0}}, f)
            # Per-iteration file (Score is scalar): must be used.
            run_dir = os.path.join(agg_dir, "all", "0", "0_default")
            os.makedirs(run_dir)
            with open(os.path.join(run_dir, "speedometer_3.0.json"), "w") as f:
                json.dump({"Score": 35.0,
                           "TodoMVC-React": 20.0,
                           "Geomean": 19.0,
                           "Iteration-0-Total": 21.0,
                           "TodoMVC-React/Adding100Items": 12.0}, f)
            runs = ab.parse_run_metrics(tmp, "res")
            self.assertEqual(1, len(runs))
            score, stories = runs[0]
            self.assertAlmostEqual(35.0, score)
            # Sub-metric keys (with '/') are excluded from the story table.
            self.assertEqual({"TodoMVC-React": 20.0}, stories)


class SuiteDiffTest(unittest.TestCase):
    def test_block_log_diff(self):
        blocks = [{"a_scores": [30.0, 30.0], "b_scores": [33.0, 33.0]}]
        diffs = ab.suite_block_diffs(blocks)
        self.assertAlmostEqual(math.log(1.1), diffs[0])


if __name__ == "__main__":
    unittest.main()
