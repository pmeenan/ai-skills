#!/usr/bin/env python3
"""Benchmark-specific contracts for the Chromium optimization pipeline.

The campaign intentionally has one small benchmark seam.  Everything outside
this module deals in a suite score and per-workload scalar observations where
positive log deltas mean that arm B is better.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping, Sequence
from typing import Any


@dataclasses.dataclass(frozen=True)
class ParsedResult:
    score: float
    workloads: dict[str, float]
    components: dict[str, dict[str, float]]


@dataclasses.dataclass(frozen=True)
class BenchmarkAdapter:
    benchmark_id: str
    crossbench_name: str
    result_filename: str
    metric_model: str
    workload_value_direction: str
    default_workload_selector: str
    available_workload_count: int
    default_workload_count: int
    profile_source: str
    score_sources: tuple[str, ...]
    investigation_sources: tuple[str, ...]

    def crossbench_args(
        self,
        source: str | None = None,
        local_url: str | None = None,
        detailed_metrics: bool = True,
    ) -> list[str]:
        source = source or self.score_sources[0]
        allowed = set(self.score_sources) | set(self.investigation_sources)
        if source not in allowed:
            choices = ", ".join(sorted(allowed))
            raise ValueError(
                f"unsupported {self.benchmark_id} source {source!r}; "
                f"choose one of: {choices}"
            )
        args = [self.crossbench_name]
        if self.benchmark_id == "speedometer3":
            args.append("--network=third_party/speedometer/v3.1")
        elif source == "local":
            args.append(f"--local={local_url or 'http://localhost:8000/'}")
        else:
            args.append(f"--{source}")
        if detailed_metrics and self.benchmark_id == "jetstream3":
            args.append("--detailed-metrics")
        return args

    def parse_result(self, data: Mapping[str, Any]) -> ParsedResult | None:
        if self.benchmark_id == "speedometer3":
            return _parse_speedometer(data)
        if self.benchmark_id == "jetstream3":
            return _parse_jetstream(data)
        raise AssertionError(f"no parser for {self.benchmark_id}")

    def workload_log_delta(self, a_value: float, b_value: float) -> float:
        """Return a sign-normalized paired log delta (positive = B better)."""
        if self.workload_value_direction == "higher":
            return math.log(b_value) - math.log(a_value)
        if self.workload_value_direction == "lower":
            return math.log(a_value) - math.log(b_value)
        raise AssertionError(self.workload_value_direction)

    def expected_workload_count(self, selector: str) -> int | None:
        if selector == "all":
            return self.available_workload_count
        if selector == "default":
            return self.default_workload_count
        return None

    def source_provenance(
        self, source: str | None = None, local_url: str | None = None
    ) -> dict[str, Any]:
        source = source or self.score_sources[0]
        if self.benchmark_id == "speedometer3":
            url = "third_party/speedometer/v3.1"
            content_pinned = True
        else:
            urls = {
                "live": "https://chromium-workloads.web.app/jetstream/v3.0/",
                "official": "https://browserbench.org/JetStream3.0/",
                "custom": (
                    "https://chromium-workloads.web.app/jetstream/"
                    "v3.0-custom/"
                ),
                "local": local_url or "http://localhost:8000/",
            }
            url = urls[source]
            # Versioned hosted URLs (live/official) are pinned benchmark targets,
            # or a caller-supplied local payload digest.
            content_pinned = source in ("live", "official") or local_url is not None
        return {
            "benchmark_id": self.benchmark_id,
            "crossbench_name": self.crossbench_name,
            "source": source,
            "url_or_path": url,
            "content_pinned": content_pinned,
            "investigation_only": source in self.investigation_sources,
        }


SPEEDOMETER_3 = BenchmarkAdapter(
    benchmark_id="speedometer3",
    # Chromium's Telemetry/Pinpoint `speedometer3` currently selects 3.1.
    # Keep the local payload and result parser pinned to that same version.
    crossbench_name="speedometer_3.1",
    result_filename="speedometer_3.1.json",
    metric_model="speedometer-story-v1",
    workload_value_direction="lower",
    default_workload_selector="default",
    available_workload_count=32,
    default_workload_count=20,
    profile_source="local",
    score_sources=("local",),
    investigation_sources=(),
)

JETSTREAM_3 = BenchmarkAdapter(
    benchmark_id="jetstream3",
    crossbench_name="jetstream_3.0",
    result_filename="jetstream_3.0.json",
    metric_model="jetstream-workload-score-v1",
    workload_value_direction="higher",
    default_workload_selector="default",
    available_workload_count=94,
    default_workload_count=77,
    profile_source="custom",
    score_sources=("live", "official", "local"),
    investigation_sources=("custom",),
)

_ADAPTERS = {
    "speedometer3": SPEEDOMETER_3,
    "speedometer": SPEEDOMETER_3,
    "speedometer_3.1": SPEEDOMETER_3,
    "sp3": SPEEDOMETER_3,
    "jetstream3": JETSTREAM_3,
    "jetstream": JETSTREAM_3,
    "jetstream_3.0": JETSTREAM_3,
    "js3": JETSTREAM_3,
}


def get_adapter(name: object) -> BenchmarkAdapter:
    if not isinstance(name, str) or not name.strip():
        canonical = ", ".join(available_benchmarks())
        raise ValueError(
            f"benchmark must be one of: {canonical}; got {name!r}"
        )
    try:
        return _ADAPTERS[name.strip().lower()]
    except KeyError as exc:
        canonical = ", ".join(available_benchmarks())
        raise ValueError(
            f"unknown benchmark {name!r}; supported benchmarks: {canonical}"
        ) from exc


def available_benchmarks() -> tuple[str, ...]:
    return (SPEEDOMETER_3.benchmark_id, JETSTREAM_3.benchmark_id)


def _positive_scalar(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _metric_scalar(value: Any) -> float | None:
    scalar = _positive_scalar(value)
    if scalar is not None:
        return scalar
    if isinstance(value, Mapping):
        return _positive_scalar(value.get("average"))
    return None


def _parse_speedometer(data: Mapping[str, Any]) -> ParsedResult | None:
    score = _positive_scalar(data.get("Score"))
    if score is None:
        return None
    workloads = {}
    for key, value in data.items():
        if (
            key in ("Score", "Geomean")
            or "/" in key
            or key.startswith("Iteration-")
        ):
            continue
        scalar = _metric_scalar(value)
        if scalar is not None:
            workloads[key] = scalar
    return ParsedResult(score, workloads, {})


def _parse_jetstream(data: Mapping[str, Any]) -> ParsedResult | None:
    score = _positive_scalar(data.get("Total/Score"))
    if score is None:
        return None
    workloads: dict[str, float] = {}
    components: dict[str, dict[str, float]] = {}
    for key, value in data.items():
        if "/" not in key:
            continue
        workload, component = key.rsplit("/", 1)
        if workload == "Total":
            continue
        scalar = _metric_scalar(value)
        if scalar is None:
            continue
        if component == "Score":
            workloads[workload] = scalar
        else:
            components.setdefault(workload, {})[component] = scalar
    if not workloads:
        return None
    return ParsedResult(score, workloads, components)


def geometric_mean(values: Sequence[float]) -> float:
    if not values or any(value <= 0 for value in values):
        raise ValueError("geometric mean requires positive values")
    return math.exp(sum(math.log(value) for value in values) / len(values))
