#!/usr/bin/env python3
"""Tests for the benchmark adapter boundary."""

import math
import unittest

import benchmark_adapters as adapters


class AdapterLookupTest(unittest.TestCase):
    def test_aliases_resolve_to_canonical_adapter(self):
        self.assertIs(adapters.get_adapter("sp3"), adapters.SPEEDOMETER_3)
        self.assertIs(adapters.get_adapter("js3"), adapters.JETSTREAM_3)

    def test_missing_adapter_name_is_rejected_cleanly(self):
        for value in (None, "", 3):
            with self.subTest(value=value), self.assertRaisesRegex(
                ValueError, "benchmark must be one of"
            ):
                adapters.get_adapter(value)

    def test_workload_sets_are_not_conflated(self):
        js = adapters.JETSTREAM_3
        self.assertEqual(94, js.available_workload_count)
        self.assertEqual(77, js.default_workload_count)
        self.assertEqual("default", js.default_workload_selector)
        self.assertEqual(77, js.expected_workload_count("default"))
        self.assertEqual(94, js.expected_workload_count("all"))
        self.assertIsNone(js.expected_workload_count("hash-map"))


class SpeedometerAdapterTest(unittest.TestCase):
    def test_parses_scalar_run_and_ignores_submetrics(self):
        result = adapters.SPEEDOMETER_3.parse_result({
            "Score": 35.0,
            "TodoMVC-React": 20.0,
            "TodoMVC-React/Adding100Items": 12.0,
            "Iteration-0-Total": 21.0,
            "Geomean": 19.0,
        })
        self.assertEqual(35.0, result.score)
        self.assertEqual({"TodoMVC-React": 20.0}, result.workloads)
        self.assertEqual({}, result.components)

    def test_lower_workload_time_is_positive_gain(self):
        delta = adapters.SPEEDOMETER_3.workload_log_delta(100.0, 95.0)
        self.assertAlmostEqual(math.log(100.0 / 95.0), delta)


class JetStreamAdapterTest(unittest.TestCase):
    def test_parses_score_and_diagnostic_components(self):
        result = adapters.JETSTREAM_3.parse_result({
            "hash-map/Score": 525.1085,
            "hash-map/First": 234.52,
            "hash-map/Worst": 723.59,
            "hash-map/Average": 853.24,
            "Total/Score": 525.1085,
            "Total/First": 234.52,
        })
        self.assertAlmostEqual(525.1085, result.score)
        self.assertEqual({"hash-map": 525.1085}, result.workloads)
        self.assertEqual({
            "hash-map": {
                "First": 234.52,
                "Worst": 723.59,
                "Average": 853.24,
            }
        }, result.components)

    def test_aggregate_metric_file_is_not_an_independent_run(self):
        result = adapters.JETSTREAM_3.parse_result({
            "hash-map/Score": {"average": 500.0},
            "Total/Score": {"average": 500.0},
        })
        self.assertIsNone(result)

    def test_higher_workload_score_is_positive_gain(self):
        delta = adapters.JETSTREAM_3.workload_log_delta(500.0, 525.0)
        self.assertAlmostEqual(math.log(1.05), delta)

    def test_custom_fork_is_investigation_only(self):
        provenance = adapters.JETSTREAM_3.source_provenance("custom")
        self.assertTrue(provenance["investigation_only"])
        self.assertFalse(provenance["content_pinned"])
        self.assertIn("--custom", adapters.JETSTREAM_3.crossbench_args("custom"))


if __name__ == "__main__":
    unittest.main()
