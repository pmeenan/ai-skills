#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Shared benchmark campaign ledger, gate enforcement, and status generation.

The tech-lead agent mutates campaign state exclusively through this script.
Every mutation rewrites ledger.json and regenerates STATUS.md so the
human-facing status can never drift from the machine state. Subagents never
call this script; they return evidence to the tech lead, who records it.

Mechanism state machine:

  candidate -> investigating -> sized -> implementing -> review -> landed
                                              ^             |
                                              +-- rework ---+
  investigated mechanism -> rejected (reason and evidence required)
  candidate | investigating | sized -> parked (reason required)
  parked -> candidate (reopen)
  rejected | reverted -> candidate only when new evidence explicitly
                         contradicts the prior result

Discovery state machine:

  candidate -> investigating -> decomposed -> exhausted
                            ^          |
                            +-- skeptic FAIL / revised decomposition

A discovery is one observation of a profiled candidate area.  It fans out
atomically into concrete, stably-keyed mechanisms.  Rejected/reverted
mechanism keys remain in the ledger so follow-on profiles can revisit an area
without retrying paths already proved invalid.

Gate requirements are enforced by `advance`:
  -> sized:    --evidence-manifest from mechanism_evidence.py
  -> review:   --build-manifest, --test-manifest, and --verification-manifest
  -> landed:   --commit, plus recorded PASS verdicts from both skeptic and
               adversary reviews for the current review round.
"""

import argparse
import collections
import datetime
import fcntl
import hashlib
import json
import math
import os
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile
import shutil

import mechanism_evidence as mechanism_contract
import benchmark_adapters

ACTIVE_GATES = ("investigating", "sized", "implementing", "review")
FORWARD_TRANSITIONS = {
    "candidate": {"investigating", "sized"},
    "investigating": {"sized"},
    "sized": {"implementing"},
    "implementing": {"review"},
    "review": {"implementing", "landed"},
}
REVIEW_ROLES = ("skeptic", "adversary")
GATE_CHALLENGE_ROLES = REVIEW_ROLES
MECHANISM_TERMINAL = ("landed", "reverted", "rejected")
EXPECTED_VALUE_UNIT = "profile-share-equivalent-pct"
MAX_LANDINGS_WITHOUT_PROFILE = 5
MAX_LANDINGS_WITHOUT_CHECKPOINT = 5
MAX_LANDINGS_WITHOUT_FULL_SUITE_CHECKPOINT = 10
PILOT_MIN_LANDINGS = 3
PILOT_MAX_LANDINGS = 5
MIN_SCORE_BLOCKS = 32
# A story frontier entry at the floor needs ~100 samples before its rank
# means anything; the profiler must raise repetitions or sampling rate.
MIN_NOMINAL_SAMPLES_AT_FLOOR = 100
# A mechanism must plausibly move its target story by at least this multiple
# of the story's calibrated minimum detectable effect, or the fixed-plan
# measurement cannot read it and every downstream stage is wasted.
MDE_FLOOR_MULTIPLIER = 2.0
# Fixed statistical plan frozen at init for candidate A/B and checkpoints.
# minimum_effect_pct is raised to the calibrated MDE of the primary stories.
DEFAULT_STATISTICS = {
    "blocks": 32, "alpha": 0.05, "regression_margin_pct": 1.0,
    "suite_regression_margin_pct": 0.2, "minimum_effect_pct": 0.1,
    "max_abs_lag1": 0.4,
}
DEFAULT_FLEET_BOT = "mac-m1_mini_2020-perf-pgo"
LEDGER_SCHEMA_VERSION = 4
SCORE_MANIFEST_SCHEMA_VERSION = 4
SCORE_MANIFEST_RUNNER = "run_ab_benchmark.py/v4"
MIN_FULL_SUITE_REP_SECONDS = 30
T_POWER_80 = {
    1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906,
    7: 0.896, 8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876,
    12: 0.873, 13: 0.870, 14: 0.868, 15: 0.866, 16: 0.865,
    17: 0.863, 18: 0.862, 19: 0.861, 20: 0.860, 25: 0.856,
    30: 0.854,
}
TEST_BYPASS_ENV = "OPTIMIZE_CAMPAIGN_TEST_ALLOW_UNVERIFIED"
MECHANISM_REVIEW_CHECKS = {
    "skeptic": (
        "hot_path_reality",
        "raw_evidence_opened",
        "applicability_measured",
        "net_work_removed",
        "cold_path_tax_measured",
        "benchmark_overfit_checked",
        "one_invariant_only",
        "implementation_is_executable",
        "candidate_build_bound",
        "floor_cleared",
        "redundancy_supported",
    ),
    "adversary": (
        "spec", "security", "privacy", "lifecycle", "tests",
        "benchmark_overfit_checked", "feature_flag_guarded",
        "runtime_binary_changed", "portability_confirmed",
    ),
}
EXHAUSTION_REVIEW_CHECKS = (
    "complete_path_accounting",
    "exactly_one_primary_per_hotspot",
    "covered_by_same_samples",
    "mandatory_work_proved",
    "out_of_scope_proved",
    "below_floor_measured",
    "known_mechanisms_reconciled",
)


def test_bypass_requested():
    return os.environ.get(TEST_BYPASS_ENV) == "1"


def test_bypass_active():
    return test_bypass_requested() and "unittest" in sys.modules


def review_checks(opp, role):
    if opp.get("kind") == "discovery":
        if role != "skeptic":
            raise CampaignError("Discovery exhaustion takes a skeptic review only")
        return EXHAUSTION_REVIEW_CHECKS
    return MECHANISM_REVIEW_CHECKS[role]


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def canonical_key(value):
    """Return a readable fallback identity for legacy/ad-hoc records."""
    key = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return key or "area"


def require_stable_key(value, label, *, namespaced=False):
    if not isinstance(value, str) or not value.strip():
        raise CampaignError(f"{label} must be a nonempty string")
    value = value.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", value):
        raise CampaignError(
            f"{label} {value!r} must use lowercase stable-key characters "
            "[a-z0-9._/-]"
        )
    if namespaced and "/" not in value:
        raise CampaignError(
            f"{label} {value!r} must be globally namespaced as component/strategy"
        )
    return value


def require_finite_number(value, label, *, nonnegative=False):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CampaignError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise CampaignError(f"{label} must be finite")
    if nonnegative and number < 0:
        raise CampaignError(f"{label} cannot be negative")
    return number


def sha256_file(path):
    path = pathlib.Path(path)
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CampaignError(f"Cannot read evidence artifact {path}: {exc}") from exc


def load_gate_evidence(path, *, opp, phase, benchmark, metric_model):
    path = pathlib.Path(path)
    try:
        evidence = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read evidence manifest {path}: {exc}") from exc
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != mechanism_contract.SCHEMA_VERSION
    ):
        raise CampaignError(
            "Evidence manifest must use the current mechanism-evidence schema"
        )
    if evidence.get("phase") != phase or evidence.get("gate_pass") is not True:
        raise CampaignError(f"Evidence must be a passing {phase!r} artifact")
    for field, expected in (
        ("benchmark", benchmark),
        ("metric_model", metric_model),
        ("opportunity_id", opp["id"]),
        ("mechanism_key", opp.get("mechanism_key")),
        ("profile_id", opp.get("profile_id")),
        ("interval_kind", "exact-scored"),
    ):
        if evidence.get(field) != expected:
            raise CampaignError(
                f"Evidence {field} {evidence.get(field)!r} does not match {expected!r}"
            )
    expected_story = opp.get("target_story")
    if expected_story and evidence.get("target_story") != expected_story:
        raise CampaignError(
            f"Evidence measured story {evidence.get('target_story')!r}, not "
            f"the opportunity's target story {expected_story!r}"
        )
    if evidence.get("score_scope", {}).get("classification") not in (
        "score-critical", "cpu-only"
    ):
        raise CampaignError("Evidence lacks a score-scope classification")
    if evidence.get("route") == "latency":
        import latency_evidence
        try:
            for label in ("build", "baseline_build"):
                mechanism_contract.validate_build_artifact(evidence[label], label)
            if latency_evidence.reduce(evidence["packet"]) != evidence:
                raise ValueError("latency result differs from raw trace recomputation")
        except (KeyError, ValueError, OSError, mechanism_contract.EvidenceError) as exc:
            raise CampaignError("invalid latency evidence: " + str(exc)) from exc
        return evidence, sha256_file(path)
    sources = evidence.get("sources")
    expected_sources = 1 if phase == "sizing" else 2
    if not isinstance(sources, list) or len(sources) != expected_sources:
        raise CampaignError(
            f"{phase} evidence must bind exactly {expected_sources} raw source file(s)"
        )
    source_paths = []
    for source in sources:
        if not isinstance(source, dict) or not source.get("path") or not source.get("sha256"):
            raise CampaignError("Evidence source provenance is incomplete")
        source_path = pathlib.Path(source["path"])
        if sha256_file(source_path) != source["sha256"]:
            raise CampaignError(f"Raw evidence source digest changed: {source_path}")
        source_paths.append(source_path)
    try:
        with tempfile.TemporaryDirectory(prefix="sp3-evidence-check-") as temp_dir:
            recomputed_path = pathlib.Path(temp_dir) / "evidence.json"
            if phase == "sizing":
                mechanism_contract.cmd_summarize(argparse.Namespace(
                    raw=source_paths[0], out=recomputed_path
                ))
            else:
                mechanism_contract.cmd_compare(argparse.Namespace(
                    baseline=source_paths[0], variant=source_paths[1],
                    kind="candidate", out=recomputed_path
                ))
            recomputed = json.loads(recomputed_path.read_text())
    except (mechanism_contract.EvidenceError, OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot recompute evidence artifact: {exc}") from exc
    if recomputed != evidence:
        raise CampaignError(
            "Evidence manifest does not match deterministic recomputation from raw sources"
        )
    return evidence, sha256_file(path)


def validate_gate_challenges(args, *, gate, artifact_digests):
    if test_bypass_active():
        return []
    expected = {f"sha256:{value}" for value in artifact_digests if value}
    reports = []
    task_ids = set()
    for role in GATE_CHALLENGE_ROLES:
        path_value = getattr(args, f"gate_{role}", None)
        if not path_value:
            raise CampaignError(
                f"{gate} requires --gate-{role} from an independent gate reviewer"
            )
        path = pathlib.Path(path_value)
        try:
            report = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignError(f"Cannot read {gate} {role} challenge: {exc}") from exc
        if not isinstance(report, dict):
            raise CampaignError(f"{gate} {role} challenge must be one JSON object")
        checked = report.get("artifact_digests_checked")
        task_id = report.get("reviewer_task_id")
        transcript = report.get("transcript_ref")
        if (
            report.get("schema_version") != 1
            or report.get("role") != role
            or report.get("gate") != gate
            or report.get("verdict") != "PASS"
            or not isinstance(checked, list)
            or not expected.issubset(set(checked))
            or not isinstance(task_id, str) or len(task_id.strip()) < 3
            or not isinstance(transcript, str) or len(transcript.strip()) < 3
            or report.get("challenges") != []
            or not isinstance(report.get("why_this_proves_real_speedup"), str)
            or len(report["why_this_proves_real_speedup"].strip()) < 20
        ):
            raise CampaignError(
                f"{gate} {role} challenge is unbound, incomplete, or not PASS"
            )
        if task_id in task_ids:
            raise CampaignError("skeptic and adversary challenges use the same task id")
        task_ids.add(task_id)
        reports.append({
            "role": role,
            "path": str(path.resolve()),
            "sha256": sha256_file(path),
            "reviewer_task_id": task_id,
            "transcript_ref": transcript,
            "artifact_digests_checked": sorted(expected),
        })
    return reports


def record_gate_challenges(ledger, *, gate, subject, reports):
    if not reports:
        return
    ledger.data.setdefault("gate_challenges", []).append({
        "ts": utc_now(),
        "gate": gate,
        "subject": subject,
        "reports": reports,
    })


def landings_since_sequence(ledger, sequence):
    return sum(
        opp.get("runtime_change_sequence", 0) > sequence
        for opp in ledger.data.get("opportunities", [])
        if opp.get("status") in ("landed", "reverted")
    )


def checkpoint_type(checkpoint):
    """Return the checkpoint type, treating pre-split records as legacy dual-use."""
    return checkpoint.get("type") or "legacy"


def latest_checkpoint(ledger, kind):
    for checkpoint in reversed(ledger.data.get("checkpoints", [])):
        recorded_kind = checkpoint_type(checkpoint)
        if recorded_kind == kind or recorded_kind == "legacy":
            return checkpoint
    return None


def landed_target_stories(ledger):
    return sorted({
        opp["target_story"]
        for opp in ledger.landed()
        if isinstance(opp.get("target_story"), str) and opp["target_story"]
    })


def story_selector(stories):
    return ",".join(sorted(set(stories)))


def parse_story_selector(value):
    if value == "all":
        return None
    if not isinstance(value, str):
        return []
    return sorted({item.strip() for item in value.split(",") if item.strip()})


def enforce_checkpoint_attempt_policy(ledger, *, kind, sha, landed_count, blocks):
    """Prevent optional stopping through repeated same-tip checkpoints.

    A targeted checkpoint gets one predeclared larger confirmation only when
    its first interval is inconclusive. A full-suite checkpoint is a
    regression/aggregate snapshot, so there is no same-tip retry loop.
    """
    attempts = [
        checkpoint
        for checkpoint in ledger.data.get("checkpoints", [])
        if checkpoint_type(checkpoint) == kind
        and checkpoint.get("sha") == sha
        and checkpoint.get("landed_count") == landed_count
    ]
    if not attempts:
        return
    if kind == "full-suite":
        raise CampaignError(
            "A full-suite checkpoint is already recorded at this campaign tip; "
            "do not repeat same-tip runs until one looks favorable"
        )
    previous = attempts[-1]
    previous_ci = previous.get("ci")
    if (
        not isinstance(previous_ci, list)
        or len(previous_ci) != 2
        or not all(isinstance(value, (int, float)) for value in previous_ci)
    ):
        raise CampaignError("The prior targeted checkpoint has no usable CI")
    if previous_ci[0] > 0:
        raise CampaignError(
            "The targeted checkpoint is already positive at this campaign tip"
        )
    if previous_ci[1] <= 0:
        raise CampaignError(
            "The targeted checkpoint is negative at this campaign tip; "
            "diagnose or bisect instead of rerunning it"
        )
    if len(attempts) >= 2:
        raise CampaignError(
            "The one allowed larger targeted confirmation is already recorded "
            "at this campaign tip"
        )
    previous_blocks = previous.get("blocks")
    if (
        isinstance(previous_blocks, bool)
        or not isinstance(previous_blocks, int)
        or isinstance(blocks, bool)
        or not isinstance(blocks, int)
        or blocks <= previous_blocks
    ):
        raise CampaignError(
            "An inconclusive targeted checkpoint may be confirmed once only "
            "with a preregistered larger block count"
        )
def enforce_freshness_for_landing(ledger):
    pilot = ledger.data.get("pilot", {})
    landed_count = len(ledger.landed())
    if pilot.get("required", True) and landed_count >= PILOT_MAX_LANDINGS:
        if pilot.get("status") != "passed":
            detail = pilot.get("reason") or (
                f"record a statistically positive, powered cumulative checkpoint "
                f"after {PILOT_MIN_LANDINGS}-{PILOT_MAX_LANDINGS} real candidates"
            )
            raise CampaignError(f"Long-campaign landing is blocked by the pilot: {detail}")
    profiles = ledger.data.get("profile_runs", [])
    if not profiles:
        raise CampaignError("Landing is blocked until an exact-scored profile is recorded")
    profile_sequence = profiles[-1].get("sequence", 0)
    if landings_since_sequence(ledger, profile_sequence) >= MAX_LANDINGS_WITHOUT_PROFILE:
        raise CampaignError(
            f"Landing is blocked after {MAX_LANDINGS_WITHOUT_PROFILE} runtime changes; "
            "record a fresh flag-enabled profile"
        )
    targeted_checkpoint = latest_checkpoint(ledger, "targeted")
    full_checkpoint = latest_checkpoint(ledger, "full-suite")
    if not test_bypass_active():
        for checkpoint in (targeted_checkpoint,full_checkpoint):
            if checkpoint and checkpoint['landed_count'] == landed_count and checkpoint.get('verdict') != 'IMPROVEMENT':
                raise CampaignError("cumulative checkpoint is not a fixed-plan IMPROVEMENT; investigate or stop")
    targeted_count = targeted_checkpoint["landed_count"] if targeted_checkpoint else 0
    full_count = full_checkpoint["landed_count"] if full_checkpoint else 0
    gate_ci = targeted_checkpoint.get("ci") if targeted_checkpoint else None
    if (
        targeted_checkpoint
        and targeted_count == landed_count
        and landed_count >= PILOT_MIN_LANDINGS
        and isinstance(gate_ci, list)
        and len(gate_ci) == 2
        and gate_ci[0] <= 0
    ):
        raise CampaignError(
            f"Landing is blocked because the latest cumulative out/release "
            f"targeted checkpoint CI [{gate_ci[0]:+.4f}%, "
            f"{gate_ci[1]:+.4f}%] is not positive; increase balanced blocks, "
            "diagnose the evidence chain, or bisect/revert"
        )
    latest_full_ci = full_checkpoint.get("ci") if full_checkpoint else None
    if (
        full_checkpoint
        and isinstance(latest_full_ci, list)
        and len(latest_full_ci) == 2
        and latest_full_ci[1] <= 0
    ):
        raise CampaignError(
            "Landing is blocked because the latest cumulative out/release "
            f"checkpoint shows a stat-sig full-suite regression "
            f"[{latest_full_ci[0]:+.4f}%, {latest_full_ci[1]:+.4f}%]; bisect/revert "
            "before landing more work"
        )
    if landed_count - targeted_count >= MAX_LANDINGS_WITHOUT_CHECKPOINT:
        raise CampaignError(
            f"Landing is blocked after {MAX_LANDINGS_WITHOUT_CHECKPOINT} unchecked "
            "landings; record a targeted cumulative checkpoint"
        )
    if (
        pilot.get("status") == "passed"
        and landed_count - full_count >= MAX_LANDINGS_WITHOUT_FULL_SUITE_CHECKPOINT
    ):
        raise CampaignError(
            "Landing is blocked after "
            f"{MAX_LANDINGS_WITHOUT_FULL_SUITE_CHECKPOINT} landings without a "
            "full-suite regression checkpoint"
        )


def validate_expected_value(item, label):
    """Validate an optional impact override with an explicitly comparable unit."""
    value = item.get("expected_value")
    unit = item.get("expected_value_unit")
    if value is None:
        if unit is not None:
            raise CampaignError(f"{label} has expected_value_unit without expected_value")
        return
    item["expected_value"] = require_finite_number(
        value, f"{label} expected_value", nonnegative=True
    )
    if unit != EXPECTED_VALUE_UNIT:
        raise CampaignError(
            f"{label} expected_value requires expected_value_unit "
            f"{EXPECTED_VALUE_UNIT!r} so it is comparable to measured profile share"
        )


def measured_priority_from_refs(refs):
    """Return the hottest profiler-measured primary work represented by refs."""
    refs = list(refs or [])
    primary = [ref for ref in refs if ref.get("accounting") == "primary"]
    ranked = primary or refs
    shares = [
        float(ref["measured_share_pct"])
        for ref in ranked
        if isinstance(ref.get("measured_share_pct"), (int, float))
        and math.isfinite(float(ref["measured_share_pct"]))
    ]
    return max(shares, default=None)


def agents_dir():
    """Locate the working repo's .agents directory.

    The skills tree may be symlinked into the repo, so resolving __file__
    would escape it. Prefer the repo containing the current directory; fall
    back to the invocation path without resolving symlinks.
    """
    root = find_repo_root(pathlib.Path.cwd())
    if root:
        return pathlib.Path(root) / ".agents"
    return pathlib.Path(os.path.abspath(__file__)).parents[3]


def default_campaign_dir():
    env = os.environ.get("OPTIMIZE_CAMPAIGN_DIR")
    if env:
        return pathlib.Path(env)
    return agents_dir() / "campaigns" / "current"


def humanize_age(iso_ts):
    try:
        then = datetime.datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return "?"
    delta = datetime.datetime.now(datetime.timezone.utc) - then
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class CampaignError(Exception):
    pass


class Ledger:
    def __init__(self, campaign_dir):
        self.dir = pathlib.Path(campaign_dir)
        self.path = self.dir / "ledger.json"
        self.data = None

    def load(self):
        if not self.path.exists():
            raise CampaignError(
                f"No ledger at {self.path}. Run `campaign.py init` first "
                "or pass --dir/OPTIMIZE_CAMPAIGN_DIR."
            )
        with open(self.path) as f:
            self.data = json.load(f)
        self._verify_snapshot_history()
        self._validate_schema()
        return self

    def _verify_snapshot_history(self):
        required = self.data.get("config", {}).get("audit_history_required") is True
        git_dir = self.dir / ".git"
        if not git_dir.exists():
            if required and not test_bypass_active():
                raise CampaignError(
                    "Campaign snapshot history is missing; ledger tampering or "
                    "manual deletion is possible"
                )
            return
        status = subprocess.run(
            ["git", "-C", str(self.dir), "status", "--porcelain", "--",
             "ledger.json", "STATUS.md", ".gitignore"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if status and not test_bypass_active():
            raise CampaignError(
                "Campaign ledger/STATUS changed outside campaign.py; run audit "
                "and restore the last snapshot before continuing"
            )

    def _commit_snapshot(self, message):
        git_dir = self.dir / ".git"
        if not git_dir.exists():
            if not self.data.get("config", {}).get("audit_history_required"):
                return
        if not git_dir.exists():
            subprocess.run(["git", "init", "-q", str(self.dir)], check=True)
            ignore = self.dir / ".gitignore"
            ignore.write_text("*\n!.gitignore\n!ledger.json\n!STATUS.md\n")
        subprocess.run(
            ["git", "-C", str(self.dir), "add", "-f", ".gitignore",
             "ledger.json", "STATUS.md"],
            check=True,
        )
        staged = subprocess.run(
            ["git", "-C", str(self.dir), "diff", "--cached", "--quiet"]
        )
        if staged.returncode == 0:
            return
        if staged.returncode != 1:
            raise CampaignError("Cannot inspect campaign snapshot index")
        subprocess.run(
            [
                "git", "-C", str(self.dir),
                "-c", "user.name=Optimization Campaign",
                "-c", "user.email=optimization-campaign@invalid",
                "commit", "-qm", message,
            ],
            check=True,
        )

    def _validate_schema(self):
        """Reject ledgers not created by the current shared campaign core."""
        if not isinstance(self.data, dict):
            raise CampaignError("Campaign ledger must contain a JSON object")
        version = self.data.get("schema_version")
        if version != LEDGER_SCHEMA_VERSION:
            raise CampaignError(
                "Campaign ledger schema mismatch: expected "
                f"{LEDGER_SCHEMA_VERSION}, got {version!r}. Start a new campaign."
            )

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        if test_bypass_active():
            self.data.setdefault("test_only_taint", {
                "ts": utc_now(),
                "reason": (
                    f"{TEST_BYPASS_ENV}=1 was active under unittest; "
                    "this ledger is not valid campaign evidence"
                ),
            })
        self.data["ledger_revision"] = self.data.get("ledger_revision", 0) + 1
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)
        self.write_status()
        self._commit_snapshot(
            f"ledger revision {self.data['ledger_revision']}"
        )

    def opp(self, opp_id):
        for opp in self.data["opportunities"]:
            if opp["id"] == opp_id:
                return opp
        raise CampaignError(f"Unknown opportunity id {opp_id}")

    def profile(self, profile_id):
        for profile in self.data.get("profile_runs", []):
            if profile["id"] == profile_id:
                return profile
        raise CampaignError(
            f"Unknown profile id {profile_id!r}; record it with "
            "`campaign.py profile` before adding discoveries"
        )

    def children(self, opp_id):
        return [
            opp for opp in self.data["opportunities"]
            if opp.get("parent_id") == opp_id
            or opp_id in opp.get("discovery_ids", [])
        ]

    def mechanism(self, area_key, mechanism_key):
        """Find a globally-keyed mechanism.

        area_key is accepted so callers can pass an identity tuple and error
        messages can stay descriptive.  mechanism_key itself must be globally
        stable (normally `component/strategy`), because the same source change
        may be rediscovered beneath overlapping profiler anchors.
        """
        for opp in self.data["opportunities"]:
            if (
                opp.get("kind") == "mechanism"
                and opp.get("mechanism_key") == mechanism_key
            ):
                return opp
        return None

    def record(self, opp, event):
        opp.setdefault("history", []).append({"ts": utc_now(), "event": event})

    def landed(self):
        return [o for o in self.data["opportunities"] if o["status"] == "landed"]

    def measured_priority(self, opp):
        """Return globally comparable profiler impact, independent of tree depth."""
        if opp.get("kind") == "discovery":
            measured = measured_priority_from_refs(opp.get("expected_work_refs"))
        else:
            measured = opp.get("measured_priority_pct")
        if measured is None:
            measured = opp.get("share_pct", 0.0)
        try:
            measured = float(measured)
        except (TypeError, ValueError):
            return 0.0
        return measured if math.isfinite(measured) and measured >= 0 else 0.0

    def priority_info(self, opp):
        measured = self.measured_priority(opp)
        if opp.get("opportunity_budget"):
            from opportunity_budget import rank
            value = rank(opp["opportunity_budget"])
            return value["priority"], "causal-benefit-confidence-acceptability-per-hour", measured
        if (
            opp.get("kind") == "mechanism"
            and opp.get("expected_value") is not None
            and opp.get("expected_value_unit") == EXPECTED_VALUE_UNIT
        ):
            try:
                value = float(opp["expected_value"])
            except (TypeError, ValueError):
                value = None
            if value is not None and math.isfinite(value) and value >= 0:
                return value, "expected-value", measured
        basis = (
            "hottest-unresolved-profiler-work"
            if opp.get("kind") == "discovery"
            else "primary-profiler-work"
        )
        return measured, basis, measured

    def priority(self, opp):
        return self.priority_info(opp)[0]

    def next_candidates(self, count):
        pool = [o for o in self.data["opportunities"] if o["status"] == "candidate"]
        pool.sort(
            key=lambda opp: (
                self.priority(opp),
                self.measured_priority(opp),
                opp.get("kind") == "mechanism",
                -opp["id"],
            ),
            reverse=True,
        )
        return pool[:count]

    def exhaustion_blockers(self):
        """Return reasons the campaign cannot claim opportunity exhaustion."""
        if self.data.get("test_only_taint") and not test_bypass_active():
            return ["ledger is permanently tainted by test-only gate bypass"]
        profiles = self.data.get("profile_runs", [])
        if not profiles:
            return ["no reconciled flag-enabled profile is recorded"]
        latest = profiles[-1]
        latest_discoveries = [
            opp for opp in self.data["opportunities"]
            if opp.get("kind") == "discovery"
            and opp.get("profile_id") == latest["id"]
        ]
        blockers = []
        expected = latest.get("area_count")
        if expected is not None and len(latest_discoveries) != expected:
            blockers.append(
                f"latest profile {latest['id']} declares {expected} area(s) "
                f"but the ledger has {len(latest_discoveries)} discovery record(s)"
            )
        for discovery in latest_discoveries:
            if discovery["status"] != "exhausted":
                blockers.append(
                    f"latest-profile discovery #{discovery['id']:03d} "
                    f"({discovery['area_key']}) is {discovery['status']}, not exhausted"
                )
            elif discovery.get("path_accounting"):
                review = discovery.get("reviews", {}).get("skeptic", {})
                digest = decomposition_digest(discovery)
                if not (
                    review.get("verdict") == "PASS"
                    and review.get("decomposition_revision")
                    == discovery.get("decomposition_revision")
                    and review.get("decomposition_sha256") == digest
                    and discovery.get("decomposition_sha256") == digest
                ):
                    blockers.append(
                        f"latest-profile discovery #{discovery['id']:03d} "
                        "has no current skeptic PASS for its exact "
                        "decomposition revision"
                    )
            unresolved_children = [
                child for child in self.children(discovery["id"])
                if child["status"] not in MECHANISM_TERMINAL
            ]
            if unresolved_children:
                blockers.append(
                    f"latest-profile discovery #{discovery['id']:03d} has "
                    "nonterminal child mechanism(s): "
                    + ", ".join(
                        f"#{child['id']:03d} [{child['status']}]"
                        for child in unresolved_children
                    )
                )
        for opp in self.data["opportunities"]:
            if opp.get("kind") == "mechanism" and opp["status"] in (
                "candidate", "investigating", "sized", "implementing", "review"
            ):
                blockers.append(
                    f"mechanism #{opp['id']:03d} ({opp['mechanism_key']}) "
                    f"is still {opp['status']}"
                )
            if opp.get("kind") == "discovery" and opp["status"] in (
                "candidate", "investigating"
            ):
                blockers.append(
                    f"discovery #{opp['id']:03d} ({opp['area_key']}) "
                    f"is still {opp['status']}"
                )
            if opp.get("kind") == "mechanism" and opp["status"] == "parked":
                reconciliation = next((
                    item for item in latest.get("parked_mechanisms", [])
                    if item.get("mechanism_key") == opp.get("mechanism_key")
                ), None)
                if reconciliation is None:
                    blockers.append(
                        f"latest profile does not reconcile parked mechanism "
                        f"#{opp['id']:03d} ({opp['mechanism_key']})"
                    )
                elif reconciliation["disposition"] == "recurrent":
                    discovery = next((
                        item for item in latest_discoveries
                        if item["area_key"] == reconciliation.get("area_key")
                    ), None)
                    accounted_keys = {
                        item.get("mechanism_key")
                        for item in (discovery or {}).get("path_accounting", [])
                        if item.get("disposition") in ("below-floor", "out-of-scope")
                    }
                    if not discovery or (
                        opp["id"] not in discovery.get("known_mechanism_ids", [])
                        and opp.get("mechanism_key") not in accounted_keys
                    ):
                        blockers.append(
                            f"recurrent parked mechanism #{opp['id']:03d} "
                            f"({opp['mechanism_key']}) is not accounted by latest area "
                            f"{reconciliation.get('area_key')!r}"
                        )
        profile_sequence = latest.get("sequence", 0)
        newer_runtime_changes = [
            opp for opp in self.data["opportunities"]
            if (opp.get("runtime_change_sequence") or 0) > profile_sequence
        ]
        if newer_runtime_changes:
            blockers.append(
                "latest profile predates runtime-changing mechanism event(s): "
                + ", ".join(f"#{opp['id']:03d}" for opp in newer_runtime_changes)
            )
        return blockers

    # ---------------- STATUS.md ----------------

    def write_status(self):
        cfg = self.data["config"]
        opps = self.data["opportunities"]
        checkpoints = self.data.get("checkpoints", [])
        profiles = self.data.get("profile_runs", [])
        landed = self.landed()
        lines = []
        benchmark = cfg["benchmark"]
        lines.append(
            f"# {benchmark} Campaign: {cfg['name']} — branch `{cfg['branch']}`"
        )
        lines.append("")
        if self.data.get("test_only_taint"):
            lines.append(
                "> **TEST-ONLY TAINT:** gate bypass was used. This ledger and "
                "all derived status/checkpoint claims are invalid campaign evidence."
            )
            lines.append("")
        header = (
            f"**Landed: {len(landed)}/{cfg['target_landed']}** · "
            f"Flag: `{cfg['feature']}`"
        )
        if profiles:
            latest = profiles[-1]
            header += (
                f" · Latest profile `{latest['id']}` eligible frontier: "
                f"{latest['total_share_pct']:.2f}% share"
            )
        if checkpoints:
            cp = checkpoints[-1]
            header += (
                f" · Last {checkpoint_type(cp)} checkpoint "
                f"(after {cp['landed_count']} landed): "
                f"{cp['delta_pct']:+.2f}% "
                f"[{cp['ci'][0]:+.2f}%, {cp['ci'][1]:+.2f}%]"
            )
        lines.append(header)
        lines.append("")
        lines.append(f"_Updated: {utc_now()} (generated from ledger.json — do not edit)_")
        lines.append("")
        lines.append(
            f"**Outcome objective:** reproducible positive {benchmark} movement "
            "from symbol-free `out/release`; the landed target is a planning "
            "limit, not success."
        )
        pilot = self.data.get("pilot", {})
        lines.append("")
        lines.append(
            "**Pilot:** "
            f"{pilot.get('status', 'pending').upper()}"
            + (f" — {pilot['reason']}" if pilot.get("reason") else "")
        )
        profile_changes = (
            landings_since_sequence(self, profiles[-1].get("sequence", 0))
            if profiles else 0
        )
        targeted_checkpoint = latest_checkpoint(self, "targeted")
        full_checkpoint = latest_checkpoint(self, "full-suite")
        targeted_landed = (
            targeted_checkpoint["landed_count"] if targeted_checkpoint else 0
        )
        full_landed = full_checkpoint["landed_count"] if full_checkpoint else 0
        unchecked_landings = max(0, len(landed) - targeted_landed)
        unchecked_full = max(0, len(landed) - full_landed)
        lines.append("")
        lines.append(
            "**Freshness:** "
            f"{profile_changes}/{MAX_LANDINGS_WITHOUT_PROFILE} runtime changes "
            "since profile · "
            f"{unchecked_landings}/{MAX_LANDINGS_WITHOUT_CHECKPOINT} landings "
            "since targeted checkpoint · "
            f"{unchecked_full}/{MAX_LANDINGS_WITHOUT_FULL_SUITE_CHECKPOINT} "
            "since full-suite checkpoint"
        )

        lines.append("")
        lines.append("## Calibration and qualification floors")
        calibration = cfg.get("calibration") or {}
        display = cfg.get("display") or {}
        surface = (
            f"{display.get('mode', 'headless')}"
            + (f" {display.get('display')} vt{display.get('vt')} {display.get('viewport')}"
               if display.get("mode") == "x11" else "")
        )
        lines.append(f"**Rendering surface:** {surface}")
        if calibration.get("story_mde_pct"):
            suite_mde = calibration.get("suite_mde_pct")
            lines.append(
                f"**A/A calibration:** {calibration.get('recorded')} · suite MDE "
                f"{suite_mde:.3f}% · floor = max({cfg.get('share_floor_pct')}%, "
                f"{calibration.get('mde_floor_multiplier', MDE_FLOOR_MULTIPLIER):g} × story MDE)"
            )
            lines.append("")
            lines.append("| Story | MDE (80% power) | Qualification floor |")
            lines.append("| --- | ---: | ---: |")
            for story, mde in sorted(calibration["story_mde_pct"].items(), key=lambda kv: -kv[1]):
                floor, _ = story_floor_pct(cfg, story)
                lines.append(f"| {story} | {mde:.2f}% | {floor:.2f}% |")
        else:
            lines.append(
                f"**A/A calibration:** none recorded; floor is the campaign share "
                f"floor {cfg.get('share_floor_pct')}% everywhere. Run "
                "`campaign.py calibrate` before decomposing."
            )

        discoveries = [o for o in opps if o.get("kind") == "discovery"]
        lines.append("")
        lines.append("## Discovery coverage")
        if discoveries:
            lines.append("| Profile | Opp | Area | Status | Child paths | Next action |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for discovery in discoveries[-12:]:
                children = self.children(discovery["id"])
                unresolved = [
                    child for child in children
                    if child["status"] not in MECHANISM_TERMINAL
                ]
                profile_sequence = 0
                if discovery.get("profile_id"):
                    try:
                        profile_sequence = self.profile(
                            discovery["profile_id"]
                        ).get("sequence", 0)
                    except CampaignError:
                        pass
                stale_runtime_child = any(
                    (child.get("runtime_change_sequence") or 0) > profile_sequence
                    for child in children
                )
                if discovery["status"] == "exhausted":
                    action = "complete for this profile"
                elif unresolved:
                    action = f"resolve {len(unresolved)} child path(s)"
                elif stale_runtime_child:
                    action = "follow-on profile required"
                elif discovery["status"] == "decomposed":
                    skeptic = (
                        discovery.get("reviews", {})
                        .get("skeptic", {})
                        .get("verdict")
                    )
                    if skeptic == "PASS":
                        action = "record exhaustion evidence"
                    elif skeptic == "FAIL":
                        action = "revise decomposition, then re-review"
                    else:
                        action = "skeptic exhaustion review, then exhaust"
                else:
                    action = "investigate/decompose"
                lines.append(
                    f"| `{discovery.get('profile_id')}` | #{discovery['id']:03d} | "
                    f"`{discovery['area_key']}` | {discovery['status']} | "
                    f"{len(children)} | {action} |"
                )
        else:
            lines.append("_(no profile discoveries recorded)_")

        lines.append("")
        lines.append("## Latest profile exclusions")
        latest_excluded = profiles[-1].get("excluded_areas", []) if profiles else []
        if latest_excluded:
            lines.append("| Area | Share | Category | Reason | Evidence |")
            lines.append("| --- | ---: | --- | --- | --- |")
            for area in latest_excluded:
                lines.append(
                    f"| `{area['area_key']}` | {area['marginal_share_pct']:.2f}% | "
                    f"{area['exclusion_category']} | {area['exclusion_reason']} | "
                    f"{area['exclusion_evidence']} |"
                )
        else:
            lines.append("_(none)_")

        blockers = self.exhaustion_blockers()
        lines.append("")
        lines.append(
            "**Ledger-only exhaustion precheck:** "
            + ("PASS" if not blockers else f"BLOCKED ({len(blockers)} reason(s))")
            + " · run `campaign.py audit-exhaustion` for checkout verification"
        )

        in_flight = [o for o in opps if o["status"] in ACTIVE_GATES]
        lines.append("")
        lines.append("## In flight")
        if in_flight:
            lines.append("| Gate | Opp | Kind / key | Anchor | Share | Age | Note |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            order = {s: i for i, s in enumerate(ACTIVE_GATES)}
            for o in sorted(in_flight, key=lambda o: order[o["status"]], reverse=True):
                note = self._flight_note(o)
                identity = (
                    f"mechanism `{o.get('mechanism_key')}`"
                    if o.get("kind") == "mechanism"
                    else f"discovery `{o.get('area_key')}`"
                )
                lines.append(
                    f"| {o['status']} | #{o['id']:03d} | {identity} | "
                    f"{o['anchor']} | "
                    f"{o.get('share_pct', 0.0):.2f}% | "
                    f"{humanize_age(o.get('status_since'))} | {note} |"
                )
        else:
            lines.append("_(nothing in flight)_")

        lines.append("")
        lines.append("## Next up (global ranking by target-story impact)")
        nxt = self.next_candidates(5)
        if nxt:
            for i, o in enumerate(nxt, 1):
                priority, basis, measured = self.priority_info(o)
                story = o.get("target_story") or "?"
                lines.append(
                    f"{i}. #{o['id']:03d} [{o.get('kind', 'mechanism')}] "
                    f"{o['anchor']} "
                    f"(story {story}; priority {priority:.3f}, {basis}; "
                    f"measured {measured:.3f}% of story, "
                    f"reported {o.get('share_pct', 0.0):.3f}%)"
                )
        else:
            lines.append("_(candidate pool empty — re-profile or reconcile discovery exhaustion)_")

        lines.append("")
        lines.append("## Recently landed")
        if landed:
            for o in sorted(landed, key=lambda o: o.get("status_since", ""), reverse=True)[:8]:
                commit = (o.get("commit") or "")[:12]
                lines.append(
                    f"- #{o['id']:03d} `{commit}` {o['anchor']} "
                    f"(`{o.get('mechanism_key')}`) — "
                    f"{o.get('landed_note') or o.get('evidence') or ''}"
                )
        else:
            lines.append("_(none yet)_")

        lines.append("")
        lines.append("## Checkpoints (cumulative flag on/off)")
        if checkpoints:
            lines.append("| Type | Stories | After # landed | Delta | 95% CI | Date | Notes |")
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for cp in checkpoints:
                lines.append(
                    f"| {checkpoint_type(cp)} | `{cp.get('stories', 'all')}` | "
                    f"{cp['landed_count']} | {cp['delta_pct']:+.2f}% | "
                    f"[{cp['ci'][0]:+.2f}%, {cp['ci'][1]:+.2f}%] | "
                    f"{cp['ts'][:10]} | {cp.get('notes') or ''} |"
                )
        else:
            lines.append("_(no checkpoints yet)_")

        parked = [
            o for o in opps
            if o["status"] in ("parked", "rejected", "reverted", "exhausted")
        ]
        lines.append("")
        lines.append("## Parked / rejected / reverted / exhausted")
        if parked:
            for o in parked:
                revert = (
                    f" (revert `{o['revert_commit'][:12]}`)"
                    if o.get("revert_commit")
                    else ""
                )
                lines.append(
                    f"- #{o['id']:03d} [{o['status']}] {o['anchor']}{revert} "
                    f"(`{o.get('area_key')}` / "
                    f"`{o.get('mechanism_key') or 'discovery'}`) — "
                    f"{o.get('reason') or ''}"
                )
        else:
            lines.append("_(none)_")
        lines.append("")

        with open(self.dir / "STATUS.md", "w") as f:
            f.write("\n".join(lines))

    def _flight_note(self, opp):
        bits = []
        if opp["status"] == "review":
            for role in REVIEW_ROLES:
                verdict = opp.get("reviews", {}).get(role, {}).get("verdict")
                bits.append(f"{role}: {verdict or 'pending'}")
        if opp.get("rework_rounds"):
            bits.append(f"rework round {opp['rework_rounds']}")
        if opp.get("squeeze_rounds"):
            bits.append(f"squeeze round {opp['squeeze_rounds']}")
        if opp.get("parent_id"):
            bits.append(f"child of #{opp['parent_id']:03d}")
        if not bits and opp.get("notes"):
            bits.append(opp["notes"][-1])
        return "; ".join(bits)


def find_repo_root(start):
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def verify_commit(repo_root, sha):
    if not repo_root:
        print("warning: not in a git repo; skipping commit verification", file=sys.stderr)
        return
    result = subprocess.run(
        ["git", "-C", repo_root, "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise CampaignError(f"Commit {sha} does not exist in {repo_root}")


def verify_profile_head(repo_root, sha, branch, *, allow_unverified=False):
    """A campaign profile must describe the checked-out campaign tip."""
    if allow_unverified:
        return {
            "repository_root": str(pathlib.Path(repo_root).resolve()) if repo_root else None,
            "resolved_sha": sha,
            "repository_verified": False,
        }
    verify_commit(repo_root, sha)
    full_sha = git_output(repo_root, "rev-parse", f"{sha}^{{commit}}").strip()
    head = git_output(repo_root, "rev-parse", "HEAD").strip()
    if full_sha != head:
        raise CampaignError(
            f"Profile ref {sha} is not current HEAD ({head[:12]}); follow-on "
            "profiles must include every landed/reverted campaign change"
        )
    current_branch = git_output(
        repo_root, "rev-parse", "--abbrev-ref", "HEAD"
    ).strip()
    if branch and current_branch != branch:
        raise CampaignError(
            f"Profile HEAD is on branch {current_branch!r}, not campaign "
            f"branch {branch!r}"
        )
    dirty = git_output(repo_root, "status", "--porcelain").splitlines()
    if dirty:
        raise CampaignError(
            "Cannot reconcile a follow-on profile while the local campaign "
            "tree is dirty; finish or discard the in-flight mechanism first"
        )
    return {
        "repository_root": str(pathlib.Path(repo_root).resolve()),
        "resolved_sha": full_sha,
        "repository_verified": True,
    }


def feature_names(value):
    return {item.strip() for item in (value or "").split(",") if item.strip()}


def split_story_entry_key(entry_key):
    """Split a story-qualified entry key into (story, bare_entry_key).

    Per-story silo analyses namespace every frontier identity as
    `story:<name>/<kind>:<identity>` so the same symbol stays independently
    rankable in each story. Keys without the prefix return (None, key).
    """
    if isinstance(entry_key, str) and entry_key.startswith("story:"):
        remainder = entry_key[len("story:"):]
        story, separator, bare = remainder.partition("/")
        if separator and story and bare:
            return story, bare
    return None, entry_key


def semantic_entry_identity(entry_key):
    """Return the profiler work identity represented by a frontier root.

    Context entry keys embed a digest of the full call path, which is exact
    within one capture but fragile across captures (one differing frame near
    the root renames the key). A hot symbol can also move between a
    caller-sensitive context aggregate and a function aggregate across runs.
    Recurrence decisions must therefore compare the represented symbol, never
    the raw aggregate kind or context digest. Story-qualified keys keep their
    story: the same symbol in two stories is two independent silo identities.
    """
    story, bare_key = split_story_entry_key(entry_key)
    kind, separator, identity = bare_key.partition(":")
    if separator and kind in ("context", "function", "symbol"):
        if kind == "context" and "@" in identity:
            identity = identity.rsplit("@", 1)[0]
        semantic = f"symbol:{identity}"
    else:
        semantic = bare_key
    if story is not None:
        return f"story:{story}/{semantic}"
    return semantic


def semantic_area_keys(source_area_keys):
    """Group exact historical source keys by recurrence-stable identity."""
    result = {}
    for entry_key, area_key in source_area_keys.items():
        semantic = semantic_entry_identity(entry_key)
        if area_key not in result.setdefault(semantic, []):
            result[semantic].append(area_key)
    return result


def decomposition_digest(discovery):
    """Bind an exhaustion review to the exact decomposition it inspected."""
    payload = {
        "area_key": discovery.get("area_key"),
        "profile_id": discovery.get("profile_id"),
        "accounting_evidence": discovery.get("accounting_evidence"),
        "paths": discovery.get("path_accounting"),
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def derive_frontier_inventory(report):
    """Derive the per-entry work-item inventory from an analyzer report.

    Single source of truth shared by remote_measure.py (which embeds the
    result in capture summaries) and the profile importer (which re-derives
    it for verification) — the two must never drift, because the importer
    rejects any capture whose summary does not byte-match this derivation.

    Returns (frontier_entries, frontier_inventory, problems). Problems are
    human-readable strings; a nonempty list means the artifact cannot attest
    a complete inventory.
    """
    problems = []
    frontier = report.get("frontier")
    if not isinstance(frontier, list):
        return [], [], ["artifact has no frontier"]
    frontier_keys = []
    for item in frontier:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) \
                or not item["name"]:
            problems.append("frontier has malformed rows")
            continue
        entry_key = item.get("entry_key")
        if not isinstance(entry_key, str) or not entry_key:
            problems.append("frontier has no stable entry keys")
            continue
        frontier_keys.append(entry_key)
    if len(frontier_keys) != len(set(frontier_keys)):
        problems.append("frontier repeats an entry key")
    frontier_key_set = set(frontier_keys)
    assigned_alternatives = {}
    assigned_function_names = set()
    seen_alternative_keys = set()
    alternatives = report.get("overlapping_alternatives", [])
    if not isinstance(alternatives, list) or any(
        not isinstance(item, dict) for item in alternatives
    ):
        problems.append("malformed overlapping alternatives")
        alternatives = []
    for alternative in alternatives:
        assigned = alternative.get("assigned_frontier_entry")
        alternative_key = alternative.get("entry_key")
        name = alternative.get("name")
        if not isinstance(alternative_key, str) or not alternative_key:
            problems.append("alternative has no stable entry key")
            continue
        if alternative_key in seen_alternative_keys:
            problems.append(f"repeats alternative {alternative_key!r}")
            continue
        if assigned not in frontier_key_set:
            problems.append(
                f"alternative {alternative_key!r} is not assigned to a "
                "frontier entry"
            )
            continue
        if not isinstance(name, str) or not name:
            problems.append(f"alternative {alternative_key!r} has no name")
            continue
        inclusive_share = alternative.get("inclusive_share")
        if not isinstance(inclusive_share, (int, float)) or not math.isfinite(
            float(inclusive_share)
        ) or float(inclusive_share) < 0:
            problems.append(
                f"alternative {alternative_key!r} inclusive_share is invalid"
            )
            continue
        seen_alternative_keys.add(alternative_key)
        if alternative.get("kind") == "function":
            assigned_function_names.add(name)
        assigned_alternatives.setdefault(assigned, []).append({
            "hotspot_key": f"alternative:{alternative_key}",
            "semantic_key": f"symbol:{name}",
            "measured_share_pct": float(inclusive_share) * 100,
        })
    inventory = []
    for item in frontier:
        entry_key = item.get("entry_key")
        if entry_key not in frontier_key_set:
            continue
        work_items = [{
            "hotspot_key": "@root",
            "semantic_key": f"symbol:{item.get('name')}",
            "measured_share_pct": item.get("marginal_share", 0.0) * 100,
        }]
        work_items.extend({
            "hotspot_key": hotspot["name"],
            "semantic_key": f"symbol:{hotspot['name']}",
            "measured_share_pct": hotspot.get("overlap_share", 0.0) * 100,
        } for hotspot in item.get("related_hotspots", [])
        if hotspot.get("name") not in assigned_function_names)
        work_items.extend(assigned_alternatives.get(entry_key, []))
        inventory.append({
            "entry_key": entry_key,
            "work_items": work_items,
        })
    return frontier_keys, inventory, problems


def load_capture_summaries(
    path, *, expected_sha, feature, expected_features, floor_pct,
    benchmark, metric_model,
):
    try:
        with open(path) as f:
            summaries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read capture summaries {path}: {exc}") from exc
    if not isinstance(summaries, list) or len(summaries) < 2:
        raise CampaignError(
            "Capture summaries must be an array with at least two independent captures"
        )
    seen_ids = set()
    seen_artifact_paths = set()
    seen_local_results = set()
    seen_remote_perf_data = set()
    repetition_counts = set()
    story_sets = set()
    for index, summary in enumerate(summaries, 1):
        if not isinstance(summary, dict):
            raise CampaignError(f"Capture summary {index} must be an object")
        capture_id = summary.get("capture_id")
        if not isinstance(capture_id, str) or not capture_id.strip():
            raise CampaignError(f"Capture summary {index} has no capture_id")
        if capture_id in seen_ids:
            raise CampaignError(f"Capture id {capture_id!r} is not independent")
        seen_ids.add(capture_id)
        if summary.get("mode") != "profile":
            raise CampaignError(f"Capture {capture_id} was not produced in profile mode")
        if summary.get("benchmark") != benchmark:
            raise CampaignError(
                f"Capture {capture_id} used a different benchmark adapter"
            )
        if summary.get("metric_weighting") != metric_model:
            raise CampaignError(
                f"Capture {capture_id} used a different metric model"
            )
        local_results = summary.get("local_results")
        remote_perf_data = summary.get("remote_perf_data")
        if not isinstance(local_results, str) or not local_results:
            raise CampaignError(f"Capture {capture_id} has no local_results provenance")
        if not isinstance(remote_perf_data, str) or not remote_perf_data:
            raise CampaignError(f"Capture {capture_id} has no remote perf-data provenance")
        resolved_results = str(pathlib.Path(local_results).resolve())
        if resolved_results in seen_local_results:
            raise CampaignError("Capture summaries reuse the same local_results directory")
        if remote_perf_data in seen_remote_perf_data:
            raise CampaignError("Capture summaries reuse the same remote perf-data capture")
        seen_local_results.add(resolved_results)
        seen_remote_perf_data.add(remote_perf_data)
        if summary.get("sha") != expected_sha:
            repo_root = find_repo_root(pathlib.Path.cwd())
            trees_match = False
            if repo_root:
                try:
                    t1 = git_output(repo_root, "rev-parse", f"{summary.get('sha')}^{{tree}}").strip()
                    t2 = git_output(repo_root, "rev-parse", f"{expected_sha}^{{tree}}").strip()
                    trees_match = bool(t1 and t1 == t2)
                except subprocess.CalledProcessError:
                    trees_match = False
            if not trees_match:
                raise CampaignError(
                    f"Capture {capture_id} describes SHA {summary.get('sha')!r}, "
                    f"not profiled HEAD {expected_sha!r}"
                )
        if summary.get("quality_rejected") is not False:
            raise CampaignError(f"Capture {capture_id} did not pass profile quality")
        strict_evidence = not test_bypass_active()
        if strict_evidence and summary.get("interval_kind") != "exact-scored":
            raise CampaignError(
                f"Capture {capture_id} is not scoped to exact score timers"
            )
        if strict_evidence:
            require_campaign_display(
                ledger.data["config"], summary.get("display"), f"Capture {capture_id}"
            )
            if summary.get("stories_scope") != "main-thread":
                raise CampaignError(
                    f"Capture {capture_id} story silos are scoped to "
                    f"{summary.get('stories_scope')!r}; campaign frontiers must "
                    "rank renderer main-thread work only (analyze with "
                    "--stories-scope main-thread)"
                )
        if strict_evidence and summary.get("metric_weighting") != metric_model:
            raise CampaignError(
                f"Capture {capture_id} is not a per-story silo decomposition "
                f"(metric_weighting {metric_model})"
            )
        if strict_evidence:
            nominal = require_finite_number(
                summary.get("nominal_samples_at_floor"),
                f"Capture {capture_id} nominal_samples_at_floor",
                nonnegative=True,
            )
            min_nominal = MIN_NOMINAL_SAMPLES_AT_FLOOR
            if nominal < min_nominal:
                raise CampaignError(
                    f"Capture {capture_id} has a story with only {nominal:.1f} "
                    f"nominal samples at its local floor (expected >= {min_nominal}); increase repetitions"
                )
            build_provenance = summary.get("build_provenance")
            required_build = (
                build_provenance.get("required_release_args", {})
                if isinstance(build_provenance, dict) else {}
            )
            if required_build != {
                "is_official_build": "true",
                "is_debug": "false",
                "chrome_pgo_phase": "2",
                "use_thin_lto": "true",
            }:
                raise CampaignError(
                    f"Capture {capture_id} lacks verified official PGO/ThinLTO provenance"
                )
        actual_features = feature_names(summary.get("enable_features"))
        if actual_features != feature_names(expected_features):
            raise CampaignError(
                f"Capture {capture_id} feature set {sorted(actual_features)} "
                f"does not match requested set {sorted(feature_names(expected_features))}"
            )
        if feature not in actual_features:
            raise CampaignError(f"Capture {capture_id} did not enable {feature}")
        adapter = benchmark_adapters.get_adapter(benchmark)
        allowed_selectors = {adapter.default_workload_selector, "all"}
        if summary.get("stories") not in allowed_selectors:
            raise CampaignError(
                f"Capture {capture_id} is not a full-suite profile: stories={summary.get('stories')} not in {allowed_selectors}"
            )
        repetitions = summary.get("repetitions")
        if not isinstance(repetitions, int) or repetitions < 1:
            raise CampaignError(f"Capture {capture_id} has invalid repetitions")
        repetition_counts.add(repetitions)
        capture_floor = require_finite_number(
            summary.get("share_floor_pct"),
            f"Capture {capture_id} share_floor_pct",
            nonnegative=True,
        )
        if not math.isclose(capture_floor, floor_pct, rel_tol=0, abs_tol=1e-12):
            raise CampaignError(
                f"Capture {capture_id} used {capture_floor}% floor, not the "
                f"campaign floor {floor_pct}%"
            )
        if not summary.get("inventory_complete"):
            raise CampaignError(
                f"Capture {capture_id} does not attest an exhaustive machine frontier"
            )
        story_frontiers = summary.get("story_frontiers")
        if not isinstance(story_frontiers, list) or not story_frontiers:
            raise CampaignError(
                f"Capture {capture_id} has no per-story silo analyses; rerun "
                "remote_measure.py --mode profile with a per-story analyzer"
            )
        story_names = [item.get("story") for item in story_frontiers
                       if isinstance(item, dict)]
        if len(story_names) != len(story_frontiers) or any(
            not isinstance(name, str) or not name for name in story_names
        ):
            raise CampaignError(
                f"Capture {capture_id} story_frontiers rows are malformed"
            )
        if len(set(story_names)) != len(story_names):
            raise CampaignError(f"Capture {capture_id} repeats a story silo")
        expected_workloads = adapter.expected_workload_count(summary.get("stories", "all"))
        if strict_evidence and expected_workloads is not None and len(story_names) != expected_workloads:
            raise CampaignError(
                f"Capture {capture_id} decomposed only {len(story_names)} "
                f"story silos; a full-suite profile must analyze all {expected_workloads}"
            )
        expected_floor = floor_pct / 100.0
        for field in (
            "analyzer_min_inclusive_share", "analyzer_min_marginal_share"
        ):
            analyzer_floor = require_finite_number(
                summary.get(field), f"Capture {capture_id} {field}", nonnegative=True
            )
            if not math.isclose(
                analyzer_floor, expected_floor, rel_tol=0, abs_tol=1e-12
            ):
                raise CampaignError(
                    f"Capture {capture_id} {field} must equal campaign "
                    f"fraction {expected_floor}"
                )
        derived_entries = []
        derived_inventory = []
        story_digests = []
        min_story_nominal = None
        for story_item in story_frontiers:
            story = story_item["story"]
            label = f"Capture {capture_id} story {story!r}"
            artifact_path = story_item.get("artifact")
            try:
                resolved_artifact = pathlib.Path(artifact_path).resolve()
                if resolved_artifact in seen_artifact_paths:
                    raise CampaignError(
                        "Capture summaries reuse the same analyzer artifact"
                    )
                if not resolved_artifact.is_relative_to(
                    pathlib.Path(resolved_results)
                ):
                    raise CampaignError(
                        f"{label} analyzer artifact is outside local_results"
                    )
                seen_artifact_paths.add(resolved_artifact)
                artifact_bytes = resolved_artifact.read_bytes()
                artifact = json.loads(artifact_bytes)
            except CampaignError:
                raise
            except (TypeError, OSError, json.JSONDecodeError) as exc:
                raise CampaignError(
                    f"{label} analyzer artifact is unreadable: {exc}"
                ) from exc
            quality = artifact.get("quality", {})
            selection = artifact.get("selection", {})
            if quality.get("accepted") is not True:
                raise CampaignError(f"{label} analyzer artifact failed quality")
            if strict_evidence and quality.get("interval_kind") != "exact-scored":
                raise CampaignError(f"{label} analyzer used broad intervals")
            if strict_evidence:
                story_nominal = require_finite_number(
                    quality.get("nominal_samples_at_floor"),
                    f"{label} nominal_samples_at_floor",
                    nonnegative=True,
                )
                min_nominal = MIN_NOMINAL_SAMPLES_AT_FLOOR
                if story_nominal < min_nominal:
                    raise CampaignError(
                        f"{label} has only {story_nominal:.1f} nominal samples "
                        f"at its local floor (expected >= {min_nominal}); increase repetitions"
                    )
                min_story_nominal = (
                    story_nominal if min_story_nominal is None
                    else min(min_story_nominal, story_nominal)
                )
                if quality.get("build_provenance") != build_provenance:
                    raise CampaignError(
                        f"{label} build provenance disagrees with the capture"
                    )
                if selection.get("metric_weighting") not in (
                    "speedometer-story-v1",
                    "jetstream-workload-score-v1",
                    metric_model,
                ):
                    raise CampaignError(
                        f"{label} analyzer is not story-silo weighted"
                    )
                if selection.get("story") != story:
                    raise CampaignError(
                        f"{label} analyzer artifact describes story "
                        f"{selection.get('story')!r}"
                    )
            if selection.get("inventory_complete") is not True:
                raise CampaignError(f"{label} analyzer inventory is incomplete")
            for selection_field in ("min_inclusive_share", "min_marginal_share"):
                artifact_floor = require_finite_number(
                    selection.get(selection_field),
                    f"{label} artifact {selection_field}",
                    nonnegative=True,
                )
                if not math.isclose(
                    artifact_floor, expected_floor, rel_tol=0, abs_tol=1e-12
                ):
                    raise CampaignError(
                        f"{label} {selection_field} must equal campaign "
                        f"fraction {expected_floor}"
                    )
            story_entries, story_inventory, derivation_problems = (
                derive_frontier_inventory(artifact)
            )
            if derivation_problems:
                raise CampaignError(
                    f"{label} analyzer artifact cannot attest a complete "
                    "inventory: " + "; ".join(derivation_problems[:5])
                )
            prefix = f"story:{story}/"
            if any(not entry.startswith(prefix) for entry in story_entries):
                raise CampaignError(
                    f"{label} frontier entries are not story-qualified"
                )
            derived_entries.extend(story_entries)
            derived_inventory.extend(story_inventory)
            story_item["artifact_sha256"] = hashlib.sha256(
                artifact_bytes
            ).hexdigest()
            story_digests.append(story_item["artifact_sha256"])
        if strict_evidence and min_story_nominal is not None and not math.isclose(
            min_story_nominal, nominal, rel_tol=0, abs_tol=1e-9
        ):
            raise CampaignError(
                f"Capture {capture_id} nominal_samples_at_floor disagrees "
                "with the weakest story artifact"
            )
        summary["artifact_sha256"] = hashlib.sha256(
            "".join(story_digests).encode()
        ).hexdigest()
        entries = summary.get("frontier_entries")
        inventory = summary.get("frontier_inventory")
        if not isinstance(entries, list) or not isinstance(inventory, list):
            raise CampaignError(f"Capture {capture_id} has no frontier inventory")
        inventory_keys = []
        for item in inventory:
            if not isinstance(item, dict) or not isinstance(item.get("entry_key"), str):
                raise CampaignError(f"Capture {capture_id} has malformed frontier inventory")
            work_items = item.get("work_items")
            if not isinstance(work_items, list) or any(
                not isinstance(work, dict)
                or not isinstance(work.get("hotspot_key"), str)
                or not work["hotspot_key"]
                or not isinstance(work.get("semantic_key"), str)
                or not work["semantic_key"]
                for work in work_items
            ):
                raise CampaignError(
                    f"Capture {capture_id} entry {item['entry_key']} has malformed hotspots"
                )
            hotspot_keys = [work["hotspot_key"] for work in work_items]
            if len(hotspot_keys) != len(set(hotspot_keys)):
                raise CampaignError(
                    f"Capture {capture_id} entry {item['entry_key']} repeats hotspots"
                )
            for work in work_items:
                work["measured_share_pct"] = require_finite_number(
                    work.get("measured_share_pct"),
                    f"Capture {capture_id} {item['entry_key']} "
                    f"{work['hotspot_key']} measured_share_pct",
                    nonnegative=True,
                )
            inventory_keys.append(item["entry_key"])
        if inventory_keys != entries:
            raise CampaignError(
                f"Capture {capture_id} frontier inventory does not match frontier_entries"
            )
        if entries != derived_entries or inventory != derived_inventory:
            raise CampaignError(
                f"Capture {capture_id} summary frontier does not match analyzer artifact"
            )
        if summary.get("frontier_count") != len(derived_entries):
            raise CampaignError(f"Capture {capture_id} frontier_count is inconsistent")
        story_sets.add(frozenset(story_names))
    if len(repetition_counts) != 1:
        raise CampaignError("Capture repetition counts do not match")
    if len(story_sets) != 1:
        raise CampaignError(
            "Captures decomposed different story sets; every capture must "
            "analyze the same story silos"
        )
    return summaries


def checkout_exhaustion_blockers(ledger, *, allow_unverified=False):
    latest = ledger.data["profile_runs"][-1]
    if not latest.get("repository_verified"):
        test_override = (
            allow_unverified
            and test_bypass_active()
        )
        return [] if test_override else [
            "latest profile repository was not verified; rerun in the profiled "
            "checkout (tests may pass --allow-unverified-repository)"
        ]
    stored_root = latest.get("repository_root")
    current_root = find_repo_root(pathlib.Path.cwd())
    if not current_root:
        return ["audit is not running inside the profiled Git repository"]
    current_root = str(pathlib.Path(current_root).resolve())
    if current_root != stored_root:
        return [
            f"audit repository {current_root} differs from profiled repository "
            f"{stored_root}"
        ]
    blockers = []
    try:
        head = git_output(current_root, "rev-parse", "HEAD").strip()
        branch = git_output(
            current_root, "rev-parse", "--abbrev-ref", "HEAD"
        ).strip()
        dirty = git_output(current_root, "status", "--porcelain").splitlines()
    except subprocess.CalledProcessError as exc:
        return [f"could not verify current Git checkout: {exc}"]
    if head != latest.get("sha"):
        blockers.append(
            f"current HEAD {head[:12]} differs from latest profiled HEAD "
            f"{str(latest.get('sha'))[:12]}"
        )
    campaign_branch = ledger.data["config"].get("branch")
    if campaign_branch and branch != campaign_branch:
        blockers.append(
            f"current branch {branch!r} differs from campaign branch "
            f"{campaign_branch!r}"
        )
    if dirty:
        blockers.append("current campaign checkout is dirty")
    for opp in ledger.landed():
        commit = opp.get("commit")
        if not commit:
            blockers.append(f"landed mechanism #{opp['id']:03d} has no commit")
            continue
        reachable = subprocess.run(
            ["git", "-C", current_root, "merge-base", "--is-ancestor", commit, "HEAD"],
            capture_output=True,
        )
        if reachable.returncode != 0:
            blockers.append(
                f"landed mechanism #{opp['id']:03d} commit {commit[:12]} "
                "is not reachable from current HEAD"
            )
    return blockers


def git_output(repo_root, *args):
    return subprocess.run(
        ["git", "-C", repo_root] + list(args),
        capture_output=True, text=True, check=True,
    ).stdout


PRODUCTION_SOURCE_SUFFIXES = {
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".m", ".mm", ".rs"
}


def is_production_source(path):
    path = pathlib.PurePosixPath(path)
    lowered = str(path).lower()
    name = path.name.lower()
    return (
        path.suffix.lower() in PRODUCTION_SOURCE_SUFFIXES
        and "/test/" not in f"/{lowered}/"
        and "/tests/" not in f"/{lowered}/"
        and not re.search(r"(?:^|[_\-.])(test|unittest|browsertest)\.", name)
    )


def without_comments_and_space(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r"\s+", "", text)


def without_comments_strings_and_space(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r'R"[^ (\\\t\r\n]{0,16}\(.*?\)[^"\\\t\r\n]{0,16}"', "", text,
                  flags=re.DOTALL)
    text = re.sub(r'"(?:\\.|[^"\\])*"', "", text)
    text = re.sub(r"'(?:\\.|[^'\\])*'", "", text)
    return re.sub(r"\s+", "", text)


def git_blob(repo_root, spec):
    completed = subprocess.run(
        ["git", "-C", repo_root, "show", spec],
        capture_output=True,
        text=True,
    )
    return completed.stdout if completed.returncode == 0 else ""


def validate_staged_implementation(repo_root, feature):
    names = [
        name for name in git_output(
            repo_root, "diff", "--cached", "--name-only", "--diff-filter=ACMR"
        ).splitlines()
        if name
    ]
    if not names:
        raise CampaignError("review requires a non-empty staged implementation diff")
    executable_files = []
    for name in names:
        if not is_production_source(name):
            continue
        before = git_blob(repo_root, f"HEAD:{name}")
        after = git_blob(repo_root, f":{name}")
        if without_comments_and_space(before) != without_comments_and_space(after):
            executable_files.append(name)
    if not executable_files:
        raise CampaignError(
            "staged diff has no semantic production-source change; comments, "
            "whitespace, tests, and metadata do not count as an optimization"
        )
    patch = git_output(
        repo_root, "diff", "--cached", "--unified=0", "--", *executable_files
    )
    added_lines = "\n".join(
        line[1:] for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if feature not in without_comments_strings_and_space(added_lines):
        raise CampaignError(
            f"new executable lines do not reference campaign feature {feature!r}; "
            "each candidate must add an explicit flag guard, and comments do not count"
        )
    return {
        "production_files": executable_files,
        "all_changed_files": names,
        "feature": feature,
        "patch_sha256": hashlib.sha256(patch.encode()).hexdigest(),
    }


def load_command_receipt(path, *, kind, source_tree, expected_skill_tree=None):
    path = pathlib.Path(path)
    try:
        receipt = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read {kind} receipt {path}: {exc}") from exc
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema_version") != 2
        or receipt.get("runner") != "command_evidence.py/v2"
        or receipt.get("kind") != kind
        or receipt.get("exit_code") != 0
    ):
        raise CampaignError(f"{path} is not a passing runner-owned {kind} receipt")
    if receipt.get("source_tree") != source_tree:
        raise CampaignError(f"{kind} receipt was not run against the reviewed tree")
    if (
        expected_skill_tree is not None
        and receipt.get("skill_tree_sha256") != expected_skill_tree
    ):
        raise CampaignError(f"{kind} receipt was produced by a different skill tree")
    environment = receipt.get("capture_environment")
    if not isinstance(environment, dict) or environment.get("virtualization") != "none":
        raise CampaignError(f"{kind} receipt was not run on the bare-metal host")
    for field in ("host_name", "host_boot_id", "kernel_release", "cpu_model"):
        if not isinstance(environment.get(field), str) or not environment[field]:
            raise CampaignError(f"{kind} receipt has no attested {field}")
    output = receipt.get("output")
    if not isinstance(output, dict) or sha256_file(output.get("path", "")) != output.get("sha256"):
        raise CampaignError(f"{kind} receipt output digest is invalid")
    command = receipt.get("command")
    if not isinstance(command, list) or not command:
        raise CampaignError(f"{kind} receipt has no command")
    executable = receipt.get("executable")
    if (
        not isinstance(executable, dict)
        or sha256_file(executable.get("path", "")) != executable.get("sha256")
    ):
        raise CampaignError(f"{kind} receipt executable digest is invalid")
    executable_path = pathlib.Path(executable["path"]).resolve()
    if kind == "build":
        depot_tools = executable.get("depot_tools")
        if (
            pathlib.Path(command[0]).name != "autoninja"
            or not isinstance(depot_tools, dict)
            or not str(depot_tools.get("origin", "")).rstrip("/").endswith(
                "chromium/tools/depot_tools.git"
            )
            or not depot_tools.get("revision")
        ):
            raise CampaignError("build receipt did not use tracked Chromium autoninja")
    else:
        try:
            executable_path.relative_to(
                (pathlib.Path(receipt.get("cwd", "")) / "out").resolve()
            )
        except ValueError as exc:
            raise CampaignError("test receipt executable is outside checkout out/") from exc
        if executable_path.read_bytes()[:4] != b"\x7fELF":
            raise CampaignError("test receipt executable is not an ELF binary")
        log_text = pathlib.Path(output["path"]).read_text(errors="replace")
        counts = [
            int(match.group(1))
            for match in re.finditer(
                r"\[\s*PASSED\s*\]\s+(\d+)\s+tests?\.", log_text
            )
        ]
        passed = max(counts, default=0)
        if (
            pathlib.Path(command[0]).name in (
                "chrome", "chromium", "headless_shell", "content_shell"
            )
            or receipt.get("test_framework") != "gtest"
            or receipt.get("tests_passed") != passed
            or passed < 1
        ):
            raise CampaignError("test receipt does not prove any passing gtests")
    return receipt, sha256_file(path)


def verify_candidate_build_binding(opp, evidence, repo_root):
    candidate = evidence.get("build", {})
    baseline = evidence.get("baseline_build", {})
    staged_tree = opp.get("review_tree")
    base_tree = git_output(repo_root, "rev-parse", "HEAD^{tree}").strip()
    if candidate.get("product_tree") != staged_tree:
        raise CampaignError(
            "candidate evidence is not bound to the staged reviewed product tree"
        )
    if baseline.get("product_tree") != base_tree:
        raise CampaignError(
            "baseline evidence is not bound to the review-base product tree"
        )
    feature_flag_twin = (
        candidate.get("enable_features") != baseline.get("enable_features")
        or candidate.get("product_tree") != baseline.get("product_tree")
    )
    if not feature_flag_twin:
        if candidate.get("browser_sha256") == baseline.get("browser_sha256"):
            raise CampaignError("candidate and baseline evidence use the same browser binary")
        if candidate.get("executable_text_sha256") == baseline.get("executable_text_sha256"):
            raise CampaignError(
                "candidate and baseline have identical executable .text; the source "
                "change was non-runtime or optimized away"
            )
    for receipt_name in ("build_receipt", "test_receipt"):
        receipt = opp.get(receipt_name, {})
        environment = receipt.get("capture_environment", {})
        for field in ("host_name", "host_boot_id", "kernel_release", "cpu_model"):
            if environment.get(field) != candidate.get(field):
                raise CampaignError(
                    f"{receipt_name} {field} does not match candidate mechanism capture"
                )
    build_receipt = opp.get("build_receipt", {})
    test_receipt = opp.get("test_receipt", {})
    build_command = build_receipt.get("command", [])
    try:
        build_dir_arg = build_command[build_command.index("-C") + 1]
    except (ValueError, IndexError) as exc:
        raise CampaignError("build receipt has no explicit -C build directory") from exc
    build_dir = pathlib.Path(build_dir_arg)
    if not build_dir.is_absolute():
        build_dir = pathlib.Path(build_receipt.get("cwd", "")) / build_dir
    build_dir = build_dir.resolve()
    test_binary = pathlib.Path(test_receipt.get("executable", {}).get("path", "")).resolve()
    try:
        test_binary.relative_to(build_dir)
    except ValueError as exc:
        raise CampaignError("test binary did not come from the receipt build directory") from exc
    build_targets = build_command[build_command.index("-C") + 2:]
    test_name = test_binary.name
    if not any(
        pathlib.PurePosixPath(target.split(":", 1)[0]).name == test_name
        or pathlib.PurePosixPath(target.rsplit(":", 1)[-1]).name == test_name
        for target in build_targets
    ):
        raise CampaignError(
            f"build receipt did not build the exercised test target {test_name}"
        )


def capture_review_base(opp, repo_root, feature, allow_unstaged=False):
    """Record HEAD and the staged tree hash when entering review, so landing
    can prove the reviewed content (including binaries, modes, renames, and
    deletions) is exactly what got committed. The index must be
    authoritative: unstaged or untracked changes mean the reviewers and the
    landing gate would see only part of the candidate, so they are a hard
    error unless explicitly overridden."""
    if not repo_root:
        print("warning: not in a git repo; review base not captured", file=sys.stderr)
        return
    unstaged = [
        line
        for line in git_output(repo_root, "status", "--porcelain").splitlines()
        if len(line) > 1 and line[1] != " "
    ]
    if unstaged:
        message = (
            "unstaged/untracked changes are NOT part of the reviewed tree "
            "(`git add -A` first): " + ", ".join(u[3:] for u in unstaged[:5])
        )
        if not allow_unstaged:
            raise CampaignError(
                message + ". Pass --allow-unstaged only if they are "
                "deliberately out of scope."
            )
        print(f"warning: {message}", file=sys.stderr)
    opp["review_base"] = git_output(repo_root, "rev-parse", "HEAD").strip()
    opp["review_tree"] = git_output(repo_root, "write-tree").strip()
    if test_bypass_active():
        opp["implementation_manifest"] = {"test_only_bypass": True}
    else:
        opp["implementation_manifest"] = validate_staged_implementation(
            repo_root, feature
        )


def verify_landed_commit(opp, repo_root, sha, skip_verification, branch):
    verify_commit(repo_root, sha)
    if skip_verification and not test_bypass_active():
        raise CampaignError("review verification cannot be bypassed in a live campaign")
    if skip_verification:
        print("warning: review verification skipped by flag", file=sys.stderr)
        return
    if not repo_root or not opp.get("review_base"):
        if not test_bypass_active():
            raise CampaignError("missing reviewed source base")
        print("warning: no review base recorded; landing without verification",
              file=sys.stderr)
        return
    full_sha = git_output(repo_root, "rev-parse", f"{sha}^{{commit}}").strip()
    head = git_output(repo_root, "rev-parse", "HEAD").strip()
    if head != full_sha:
        raise CampaignError(
            f"Commit {sha} is not the current HEAD ({head[:12]}); a landed "
            "commit must be the checked-out tip, not a side or dangling "
            "commit. Re-review, or pass --skip-review-verification."
        )
    current_branch = git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch and current_branch != branch:
        raise CampaignError(
            f"HEAD is on branch {current_branch!r}, not the campaign branch "
            f"{branch!r}. Check out the campaign branch, or pass "
            "--skip-review-verification."
        )
    parent = git_output(repo_root, "rev-parse", f"{sha}^").strip()
    if parent != opp["review_base"]:
        raise CampaignError(
            f"Commit {sha} is not built directly on the reviewed base "
            f"{opp['review_base'][:12]} (parent is {parent[:12]}). Re-review, "
            "or pass --skip-review-verification if this is intentional."
        )
    landed_tree = git_output(repo_root, "rev-parse", f"{sha}^{{tree}}").strip()
    if landed_tree != opp.get("review_tree"):
        raise CampaignError(
            f"Commit {sha} does not match the tree that was reviewed "
            "(content changed after review). Re-review, or pass "
            "--skip-review-verification if this is intentional."
        )


def stable_patch_id(repo_root, older, newer):
    diff = subprocess.run(
        ["git", "-C", repo_root, "diff", "--no-ext-diff", older, newer],
        capture_output=True,
        check=True,
    ).stdout
    result = subprocess.run(
        ["git", "-C", repo_root, "patch-id", "--stable"],
        input=diff,
        capture_output=True,
        text=False,
        check=True,
    ).stdout.decode().strip()
    return result.split()[0] if result else None


def verify_revert_commit(opp, repo_root, sha, branch):
    if not repo_root:
        raise CampaignError("Revert verification requires the campaign Git checkout")
    verify_commit(repo_root, sha)
    full_sha = git_output(repo_root, "rev-parse", f"{sha}^{{commit}}").strip()
    head = git_output(repo_root, "rev-parse", "HEAD").strip()
    if full_sha != head:
        raise CampaignError(f"Revert commit {sha} is not current HEAD")
    current_branch = git_output(
        repo_root, "rev-parse", "--abbrev-ref", "HEAD"
    ).strip()
    if branch and current_branch != branch:
        raise CampaignError(
            f"Revert HEAD is on branch {current_branch!r}, not {branch!r}"
        )
    if git_output(repo_root, "status", "--porcelain").splitlines():
        raise CampaignError("Cannot record a revert while the checkout is dirty")
    landed = git_output(
        repo_root, "rev-parse", f"{opp['commit']}^{{commit}}"
    ).strip()
    revert_parent = git_output(repo_root, "rev-parse", f"{full_sha}^").strip()
    if subprocess.run(
        ["git", "-C", repo_root, "merge-base", "--is-ancestor", landed,
         revert_parent],
        capture_output=True,
    ).returncode != 0:
        raise CampaignError("The landed commit is not an ancestor of the revert")
    original_patch = stable_patch_id(repo_root, f"{landed}^", landed)
    reversed_revert_patch = stable_patch_id(repo_root, full_sha, revert_parent)
    if not original_patch or original_patch != reversed_revert_patch:
        raise CampaignError(
            f"Commit {sha} does not reverse the patch landed by {landed[:12]}"
        )
    return full_sha


# ---------------- commands ----------------


REDUNDANCY_EVIDENCE_LAYERS = (1, 2)
REDUNDANCY_FRACTION_TOLERANCE = 0.05


def bind_redundancy_evidence(path_item, story, fraction, campaign_dir):
    """Layer 1/2 claims must cite measured call counts and applicability.

    "Avoidable fraction" is otherwise a typed guess. The redundancy probe
    measures how often the site runs inside the story's scored window and how
    often the invariant holds or the input repeats; the claimed fraction may
    not exceed what those counts support.
    """
    if path_item.get("disposition") != "novel":
        return
    layer = path_item.get("investigation_layer")
    try:
        layer = int(layer) if layer is not None else None
    except (TypeError, ValueError):
        raise CampaignError(f"Path {path_item['anchor']!r} investigation_layer must be 1-4")
    if layer not in REDUNDANCY_EVIDENCE_LAYERS:
        return
    if test_bypass_active() and not path_item.get("redundancy_evidence"):
        return
    ref = path_item.get("redundancy_evidence")
    if not isinstance(ref, dict) or not ref.get("path") or not ref.get("sha256"):
        raise CampaignError(
            f"Path {path_item['anchor']!r} claims a layer-{layer} mechanism "
            "(subtree elimination or cross-call sharing) without redundancy "
            "evidence. Instrument the site with redundancy_probe.h, reduce the "
            "browser logs with redundancy_evidence.py, and cite the packet as "
            "redundancy_evidence: {path, sha256}."
        )
    import redundancy_evidence
    packet_path = pathlib.Path(ref["path"])
    if not packet_path.is_absolute():
        packet_path = pathlib.Path(campaign_dir) / packet_path
    if not packet_path.is_file():
        raise CampaignError(f"Redundancy evidence {packet_path} does not exist")
    if sha256_file(packet_path) != ref["sha256"]:
        raise CampaignError(f"Redundancy evidence {packet_path} does not match its sha256")
    try:
        packet = redundancy_evidence.load_packet(packet_path)
    except ValueError as exc:
        raise CampaignError(str(exc)) from exc
    if story and packet.get("target_story") != story:
        raise CampaignError(
            f"Redundancy evidence measured {packet.get('target_story')!r}, not the "
            f"path's target story {story!r}"
        )
    supported = redundancy_evidence.supported_avoidable_fraction(packet)
    if fraction > supported + REDUNDANCY_FRACTION_TOLERANCE:
        raise CampaignError(
            f"Path {path_item['anchor']!r} claims avoidable fraction {fraction:.2f} "
            f"but the probe supports at most {supported:.2f} (applicable "
            f"{packet['applicable_fraction']:.2f}, repeated inputs "
            f"{packet['repeat_fraction']:.2f} over {packet['calls_total']} calls"
            + (", distinct-input set overflowed" if packet.get("distinct_overflow") else "")
            + "); lower the claim or find the missing applicability"
        )
    path_item["redundancy_summary"] = {
        "site": packet["site"],
        "calls_total": packet["calls_total"],
        "calls_per_repetition_mean": packet.get("calls_per_repetition_mean"),
        "applicable_fraction": packet["applicable_fraction"],
        "repeat_fraction": packet["repeat_fraction"],
        "distinct_overflow": packet["distinct_overflow"],
        "supported_avoidable_fraction": supported,
    }


def integration_mapping(repo, isolated_sha, integrated_sha, baseline_sha):
    """Require identical reviewed patch content while allowing hunk relocation.

    Unlike git patch-id, preserve whitespace (including string-literal content).
    Keep paths, modes, context and function headers; strip only blob IDs and
    hunk line numbers. Context conflicts require fresh qualification/review.
    """
    for sha in (isolated_sha, integrated_sha, baseline_sha):
        if not isinstance(sha, str) or not re.fullmatch("[a-f0-9]{40}", sha):
            raise ValueError("full commit identity required")

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout

    parent = git("rev-parse", isolated_sha + "^").decode().strip()
    if parent != baseline_sha:
        raise ValueError("isolated candidate is not based on frozen baseline")

    def patch(sha):
        raw = git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--no-renames",
                  "--src-prefix=a/", "--dst-prefix=b/", sha + "^", sha, "--")
        if not raw:
            raise ValueError("candidate patch is empty")
        lines = []
        for line in raw.splitlines(keepends=True):
            if line.startswith(b"index "):
                continue
            if line.startswith(b"@@ "):
                line = re.sub(rb"^@@ -[0-9,]+ \+[0-9,]+ @@", b"@@", line)
            lines.append(line)
        return b"".join(lines)

    left, right = patch(isolated_sha), patch(integrated_sha)
    if left != right:
        raise ValueError("integrated patch differs from isolated measured patch; requalify changed implementation")
    return {"isolated_candidate_sha": isolated_sha, "integrated_commit": integrated_sha,
            "patch_content_sha256": hashlib.sha256(left).hexdigest()}


def fixed_plan(config, primary, blocks=None):
    """The preregistered statistical plan for one measurement.

    `primary` is "suite" or a list of stories. The minimum useful effect is
    the frozen default raised to the calibrated MDE of the primary, so an
    IMPROVEMENT means the lower bound cleared what the host can actually read.
    """
    base = dict(config.get("statistics") or DEFAULT_STATISTICS)
    calibration = config.get("calibration") or {}
    minimum = float(base["minimum_effect_pct"])
    if primary == "suite":
        if calibration.get("suite_mde_pct") is not None:
            minimum = max(minimum, float(calibration["suite_mde_pct"]))
    else:
        mdes = [float(v) for k, v in (calibration.get("story_mde_pct") or {}).items() if k in primary]
        if mdes:
            minimum = max(minimum, statistics.fmean(mdes))
    plan = {
        "blocks": int(blocks or base["blocks"]),
        "primary": primary,
        "minimum_effect_pct": minimum,
        "regression_margin_pct": float(base["regression_margin_pct"]),
        "suite_regression_margin_pct": float(base["suite_regression_margin_pct"]),
        "alpha": float(base["alpha"]),
        "max_abs_lag1": float(base["max_abs_lag1"]),
    }
    import statistics_policy
    return statistics_policy.validate_plan(plan)


def verify_local_score_receipt(config, path, opp, repo_root):
    """Recompute a runner-owned A/B manifest and decide it under the fixed plan."""
    import statistics_policy
    path = pathlib.Path(path)
    try:
        manifest = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read score manifest {path}: {exc}") from exc
    if manifest.get("runner") != SCORE_MANIFEST_RUNNER or manifest.get("schema_version") != SCORE_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"{path} is not a v4 score-runner manifest")
    if manifest.get("mode") != "ab":
        raise ValueError(f"{path} is not a feature A/B (mode={manifest.get('mode')!r})")
    if manifest.get("feature") != config["feature"]:
        raise ValueError(f"{path} toggled {manifest.get('feature')!r}, not the campaign feature")
    if manifest.get("benchmark") != config["benchmark"]:
        raise ValueError(f"{path} measured the wrong benchmark")
    adapter = benchmark_adapters.get_adapter(config["benchmark"])
    if manifest.get("stories") != adapter.default_workload_selector:
        raise ValueError(f"{path} must measure the full default workload set for its regression family")
    if manifest.get("skill_tree_sha256") != config.get("skill_tree_sha256"):
        raise ValueError(f"{path} was produced by a different skill tree")
    if not isinstance(manifest.get("blocks"), int) or manifest["blocks"] < MIN_SCORE_BLOCKS:
        raise ValueError(f"{path} has fewer than {MIN_SCORE_BLOCKS} blocks")
    provenance = manifest.get("build_provenance") or {}
    shas = {(provenance.get(arm) or {}).get("git_sha") for arm in ("a", "b")}
    if len(shas) != 1 or not re.fullmatch(r"[a-f0-9]{40}", next(iter(shas)) or ""):
        raise ValueError(f"{path} arms are not both built from one full candidate commit")
    for arm in ("a", "b"):
        arm_provenance = provenance.get(arm) or {}
        if arm_provenance.get("build_role") != "release" or arm_provenance.get("symbol_level") != "0":
            raise ValueError(f"{path} arm {arm} is not the symbol-free release build")
    validate_and_recompute_checkpoint(manifest, path, config)
    primary = [opp["target_story"]] if opp.get("target_story") else "suite"
    plan = fixed_plan(config, primary, manifest["blocks"])
    decision = statistics_policy.evaluate(manifest, plan)
    return {
        "stage": "local",
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "candidate_sha": next(iter(shas)),
        "seed": manifest.get("seed"),
        "blocks": manifest["blocks"],
        "plan": plan,
        "verdict": decision["verdict"],
        "primary": decision["primary"],
        "regressions": decision["regressions"],
        "unresolved_regression_bounds": decision["unresolved_regression_bounds"],
        "display": measurement_display_identity(manifest),
    }


def measurement_display_identity(manifest):
    environment = manifest.get("capture_environment") or {}
    return display_identity(environment.get("display"))


def verify_fleet_receipt(config, path):
    """A Pinpoint analysis summary from pinpoint_measure.py for the campaign bot."""
    path = pathlib.Path(path)
    try:
        summary = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot read fleet summary {path}: {exc}") from exc
    for field in ("job_id", "cl_url", "bot", "verdict", "metrics"):
        if not summary.get(field):
            raise ValueError(f"{path} lacks {field}; use pinpoint_measure.py analyze output")
    if config.get("fleet_bot") and summary["bot"] != config["fleet_bot"]:
        raise ValueError(f"{path} ran on {summary['bot']!r}, not the campaign bot {config['fleet_bot']!r}")
    if summary["verdict"] != "IMPROVEMENT":
        raise ValueError(f"{path} fleet verdict is {summary['verdict']}, not IMPROVEMENT")
    return {
        "stage": "fleet", "path": str(path.resolve()), "sha256": sha256_file(path),
        "bot": summary["bot"], "job_id": summary["job_id"], "cl_url": summary["cl_url"],
        "verdict": summary["verdict"], "primary_ci_pct": summary.get("primary_ci_pct"),
    }


def verify_performance_evidence(config, opp, paths, repo_root, unexpected=False):
    """Landing evidence: local fixed-plan IMPROVEMENT(s) plus the fleet bot.

    Runner-owned manifests are recomputed from their raw block results and
    digest-bound here; there is no signature layer. An unexpected win needs
    a second local run with a different seed that confirms it.
    """
    receipts = {"local": [], "fleet": []}
    for path in paths or []:
        try:
            probe = json.loads(pathlib.Path(path).read_text())
        except (OSError, ValueError) as exc:
            raise ValueError(f"cannot read performance receipt {path}: {exc}") from exc
        if probe.get("runner") == SCORE_MANIFEST_RUNNER:
            receipts["local"].append(verify_local_score_receipt(config, path, opp, repo_root))
        elif "bot" in probe and "metrics" in probe:
            receipts["fleet"].append(verify_fleet_receipt(config, path))
        else:
            raise ValueError(f"{path} is neither a score-runner manifest nor a Pinpoint summary")
    local = receipts["local"]
    if not local:
        raise ValueError("a local fixed-plan A/B manifest is required")
    candidate_shas = {r["candidate_sha"] for r in local}
    if len(candidate_shas) != 1:
        raise ValueError("local receipts measure different candidate commits")
    surfaces = {json.dumps(r["display"], sort_keys=True) for r in local}
    if len(surfaces) != 1:
        raise ValueError("local receipts were captured on different rendering surfaces")
    if len({r["seed"] for r in local}) != len(local):
        raise ValueError("local receipts reuse a seed; each run needs its own randomized schedule")
    improvements = [r for r in local if r["verdict"] == "IMPROVEMENT"]
    if unexpected:
        if len(local) < 2 or not improvements or local[-1]["verdict"] != "IMPROVEMENT":
            raise ValueError("an unexpected win needs a separately seeded confirmation run that is an IMPROVEMENT")
    elif len(improvements) != len(local):
        verdicts = ", ".join(f"{pathlib.Path(r['path']).name}: {r['verdict']}" for r in local)
        raise ValueError("every local receipt must be a fixed-plan IMPROVEMENT (" + verdicts + ")")
    if config.get("require_fleet", True) and not receipts["fleet"]:
        raise ValueError(f"a Pinpoint IMPROVEMENT on {config.get('fleet_bot')} is required before landing")
    return {"candidate_sha": next(iter(candidate_shas)), "local": local, "fleet": receipts["fleet"]}


def story_floor_pct(config, story):
    """Qualification floor for one story: the campaign share floor, raised to
    twice the story's calibrated MDE once an A/A calibration is recorded."""
    base = float(config.get("share_floor_pct", 0.0))
    calibration = config.get("calibration") or {}
    mde_by_story = calibration.get("story_mde_pct") or {}
    mde = mde_by_story.get(story) if story else None
    if mde is None:
        return base, "campaign share floor (no calibrated MDE for this story)"
    floor = max(base, MDE_FLOOR_MULTIPLIER * float(mde))
    return floor, f"max(share floor {base}%, {MDE_FLOOR_MULTIPLIER:g} x calibrated MDE {float(mde):.3f}% of {story})"


def cmd_calibrate(args):
    """Record the host's A/A null calibration and per-story MDEs in the ledger."""
    import statistics_policy
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    config = ledger.data["config"]
    manifests = []
    refs = []
    for item in args.manifest:
        path = pathlib.Path(item)
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise CampaignError(f"Cannot read A/A manifest {path}: {exc}") from exc
        if data.get("mode") != "aa":
            raise CampaignError(f"{path} is not an A/A manifest (mode={data.get('mode')!r})")
        if data.get("benchmark") != config["benchmark"]:
            raise CampaignError(f"{path} measured {data.get('benchmark')!r}, not {config['benchmark']!r}")
        environment = data.get("capture_environment") or {}
        require_campaign_display(config, environment.get("display"), f"A/A manifest {path}")
        manifests.append(data)
        refs.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    try:
        result = statistics_policy.calibrate(
            manifests, args.tolerance_pct, args.max_mde_pct, args.max_abs_lag1
        )
    except ValueError as exc:
        raise CampaignError(f"A/A calibration rejected: {exc}") from exc
    story_mde = {}
    suite_mde = None
    for session in result["results"]:
        for name, summary in session.items():
            mde = float(summary["mde_80_pct"])
            if name == "@suite":
                suite_mde = mde if suite_mde is None else max(suite_mde, mde)
            else:
                story_mde[name] = max(story_mde.get(name, 0.0), mde)
    if not result["gate_pass"]:
        worst = sorted(
            ((max(abs(v["ci_pct"][0]), abs(v["ci_pct"][1])), n)
             for session in result["results"] for n, v in session.items()),
            reverse=True,
        )[:5]
        raise CampaignError(
            "A/A calibration failed the equivalence/precision gate "
            f"(tolerance {args.tolerance_pct}%, max MDE {args.max_mde_pct}%); "
            "widest null intervals: " + ", ".join(f"{n} {w:.2f}%" for w, n in worst)
            + ". Fix the host or choose a documented untuned policy; nothing was recorded."
        )
    config["calibration"] = {
        "recorded": utc_now(),
        "sessions": result["sessions"],
        "manifests": refs,
        "tolerance_pct": args.tolerance_pct,
        "max_mde_pct": args.max_mde_pct,
        "max_abs_lag1": args.max_abs_lag1,
        "suite_mde_pct": suite_mde,
        "story_mde_pct": story_mde,
        "mde_floor_multiplier": MDE_FLOOR_MULTIPLIER,
    }
    ledger.save()
    print(f"Recorded A/A calibration from {len(manifests)} sessions")
    print(f"  suite MDE (80% power): {suite_mde:.3f}%")
    print("  story qualification floors (max(share floor, 2 x MDE)):")
    for name in sorted(story_mde, key=lambda n: -story_mde[n]):
        floor, _ = story_floor_pct(config, name)
        print(f"    {name:45s} MDE {story_mde[name]:5.2f}%  floor {floor:5.2f}%")
    return 0


def display_policy_from_args(args):
    """Freeze the rendering surface every campaign run must use."""
    display = (getattr(args, "display", None) or "headless").strip()
    gpu_clock = getattr(args, "gpu_clock_mhz", None)
    if gpu_clock is not None and (isinstance(gpu_clock, bool) or int(gpu_clock) <= 0):
        raise CampaignError("--gpu-clock-mhz must be a positive integer")
    pause = [name.strip() for name in (getattr(args, "pause_service", None) or []) if name.strip()]
    if any(not re.fullmatch(r"[A-Za-z0-9_.@-]+", name) for name in pause):
        raise CampaignError("--pause-service names must be plain systemd unit names")
    if display == "headless":
        return {"mode": "headless", "display": None, "vt": None,
                "viewport": "headless", "gpu_clock_mhz": gpu_clock, "pause_services": pause}
    if not re.fullmatch(r":\d+(?:\.\d+)?", display):
        raise CampaignError("--display must be 'headless' or an X display such as ':1'")
    vt = getattr(args, "display_vt", None)
    if vt is None or isinstance(vt, bool) or int(vt) <= 0:
        raise CampaignError("an X display needs --display-vt (the console VT its X server owns)")
    viewport = (getattr(args, "viewport", None) or "1500x1000").strip()
    if not re.fullmatch(r"\d+x\d+", viewport):
        raise CampaignError("--viewport must look like 1500x1000")
    return {"mode": "x11", "display": display, "vt": int(vt),
            "viewport": viewport, "gpu_clock_mhz": gpu_clock, "pause_services": pause}


def display_identity(environment):
    if not isinstance(environment, dict):
        return None
    return {k: environment.get(k) for k in ("mode", "display", "viewport")}


def require_campaign_display(config, environment, label):
    """Every imported measurement must have used the campaign's rendering surface."""
    policy = config.get("display")
    if policy is None:
        return
    expected = {"mode": policy.get("mode"), "display": policy.get("display"),
                "viewport": policy.get("viewport")}
    actual = display_identity(environment)
    if policy.get("mode") == "headless":
        # Headless has no display or window geometry to compare.
        expected = {"mode": "headless"}
        actual = {"mode": (environment or {}).get("mode")} if isinstance(environment, dict) else None
    if actual != expected:
        raise CampaignError(
            f"{label} was captured on rendering surface {actual} but the campaign "
            f"is frozen to {expected}; rerun on the configured display"
        )
    if policy.get("mode") == "x11":
        renderer = environment.get("gpu_renderer") or ""
        if not renderer or any(t in renderer.lower() for t in ("swiftshader", "llvmpipe", "subzero")):
            raise CampaignError(f"{label} did not render through the GPU ({renderer or 'unattested'})")


def cmd_init(args):
    adapter = benchmark_adapters.get_adapter(args.benchmark)
    source = args.benchmark_source or "local"
    try:
        adapter.crossbench_args(source)
    except ValueError as exc:
        raise CampaignError(str(exc)) from exc
    if source not in adapter.score_sources:
        raise CampaignError(
            f"Campaign score source {source!r} is investigation-only for "
            f"{adapter.benchmark_id}"
        )
    args.share_floor = require_finite_number(
        args.share_floor, "--share-floor", nonnegative=True
    )
    if args.share_floor <= 0:
        raise CampaignError("--share-floor must be greater than zero")
    display_policy = display_policy_from_args(args)
    trust = {}
    if not test_bypass_active():
        try:
            root = find_repo_root(pathlib.Path.cwd())
            baseline = git_output(root, "rev-parse", args.baseline + "^{commit}").strip()
            trust = {"baseline_sha": baseline}
        except (OSError, TypeError, ValueError, subprocess.SubprocessError) as exc:
            raise CampaignError("init requires a resolvable --baseline commit: " + str(exc)) from exc
        if args.force:
            raise CampaignError("live campaign history cannot be overwritten with --force")
    if getattr(args, "fleet_bot", None) is not None and not re.fullmatch(r"[A-Za-z0-9._-]+", args.fleet_bot):
        raise CampaignError("--fleet-bot must be a plain Pinpoint bot name")
    campaign_dir = pathlib.Path(args.dir) if args.dir else None
    if campaign_dir is not None:
        # Deliberately do NOT repoint the shared `current` symlink at a
        # custom --dir: tests and throwaway ledgers use --dir, and silently
        # hijacking the active-campaign pointer would be worse than the
        # inconvenience of passing --dir (or OPTIMIZE_CAMPAIGN_DIR) explicitly.
        print(
            f"note: this campaign lives outside the campaigns root; later "
            f"commands must pass --dir {campaign_dir} or set "
            f"OPTIMIZE_CAMPAIGN_DIR={campaign_dir} (the 'current' symlink is "
            "unchanged)",
            file=sys.stderr,
        )
    if campaign_dir is None:
        campaigns_root = agents_dir() / "campaigns"
        campaign_dir = campaigns_root / args.name
        campaign_dir.mkdir(parents=True, exist_ok=True)
        current = campaigns_root / "current"
        if current.is_symlink() or current.is_file():
            current.unlink()
        elif current.is_dir():
            shutil.rmtree(current)
        current.symlink_to(args.name)
    ledger = Ledger(campaign_dir)
    if ledger.path.exists() and not args.force:
        raise CampaignError(f"Ledger already exists at {ledger.path} (use --force)")
    repo_root = find_repo_root(pathlib.Path.cwd())
    if not test_bypass_active():
        require_clean_skill_repository()
    tooling_digest = (
        "test-only" if test_bypass_active()
        else current_skill_tree_digest(repo_root)
    )
    ledger.data = {
        "schema_version": LEDGER_SCHEMA_VERSION,
        "next_sequence": 1,
        "config": {
            **trust,
            "name": args.name,
            "benchmark": adapter.benchmark_id,
            "metric_model": adapter.metric_model,
            "execution": args.execution,
            "benchmark_source": source,
            "branch": args.branch or (
                "speedometer" if adapter.benchmark_id == "speedometer3"
                else "jetstream"
            ),
            "target_landed": args.target,
            "share_floor_pct": args.share_floor,
            "display": display_policy,
            "statistics": dict(DEFAULT_STATISTICS),
            "fleet_bot": getattr(args, "fleet_bot", None) or DEFAULT_FLEET_BOT,
            "require_fleet": not getattr(args, "no_fleet_gate", False),
            "feature": args.feature or (
                "Speedometer3Optimizations"
                if adapter.benchmark_id == "speedometer3"
                else "JetStream3Optimizations"
            ),
            "remote_host": args.remote_host,
            "remote_src": args.remote_src,
            "audit_history_required": not test_bypass_active(),
            "skill_tree_sha256": tooling_digest,
            "created": utc_now(),
        },
        "next_id": 1,
        "opportunities": [],
        "profile_runs": [],
        "checkpoints": [],
        "pilot": {
            "required": True,
            "minimum_landings": PILOT_MIN_LANDINGS,
            "maximum_landings": PILOT_MAX_LANDINGS,
            "status": "pending",
            "reason": None,
        },
        "source_area_keys": {},
    }
    (ledger.dir / "dossiers").mkdir(parents=True, exist_ok=True)
    (ledger.dir / "reviews").mkdir(parents=True, exist_ok=True)
    ledger.save()
    print(f"Initialized campaign at {ledger.dir}")
    return 0


def new_opportunity(ledger, *, kind, anchor, area_key, mechanism_key=None,
                    parent_id=None, profile_id=None, share=0.0, stories=None,
                    dossier=None, expected_value=None, expected_value_unit=None,
                    notes=None):
    source_profiles = [profile_id] if profile_id else []
    opp = {
        "id": ledger.data["next_id"],
        "kind": kind,
        "anchor": anchor,
        "area_key": area_key,
        "mechanism_key": mechanism_key,
        "parent_id": parent_id,
        "discovery_ids": [parent_id] if parent_id is not None else [],
        "profile_id": profile_id,
        "source_profile_ids": source_profiles,
        "known_mechanism_ids": [],
        "observations": [],
        "share_pct": share,
        "stories": stories,
        "target_story": None,
        "dossier": dossier,
        "expected_value": expected_value,
        "expected_value_unit": expected_value_unit,
        "measured_priority_pct": share,
        "status": "candidate",
        "status_since": utc_now(),
        "ceiling_pct": None,
        "evidence": None,
        "sizing_evidence": None,
        "sizing_evidence_sha256": None,
        "verification_evidence": None,
        "verification_evidence_sha256": None,
        "tests": None,
        "commit": None,
        "runtime_change_sequence": None,
        "rework_rounds": 0,
        "squeeze_rounds": 0,
        "reviews": {},
        "decomposition_revision": 0 if kind == "discovery" else None,
        "decomposition_sha256": None,
        "reason": None,
        "notes": [notes] if notes else [],
        "history": [],
    }
    ledger.record(opp, f"added as {kind} candidate")
    ledger.data["next_id"] += 1
    ledger.data["opportunities"].append(opp)
    return opp


def record_mechanism_observation(opp, discovery, path, *, update_sizing=True):
    primary_refs = [
        ref for ref in path.get("work_refs", [])
        if ref.get("accounting") == "primary"
    ]
    fingerprint_refs = primary_refs or path.get("work_refs", [])
    measured_priority = measured_priority_from_refs(fingerprint_refs)
    observation = {
        "ts": utc_now(),
        "profile_id": discovery.get("profile_id"),
        "discovery_id": discovery["id"],
        "area_key": path.get("area_key") or discovery["area_key"],
        "anchor": path["anchor"],
        "share_pct": path["share_pct"],
        "target_story": discovery.get("target_story"),
        "stories": path.get("stories") or discovery.get("stories"),
        "dossier": path.get("dossier") or discovery.get("dossier"),
        "expected_value": path.get("expected_value"),
        "expected_value_unit": path.get("expected_value_unit"),
        "story_profile_share_pct": path.get("story_profile_share_pct"),
        "estimated_avoidable_fraction": path.get(
            "estimated_avoidable_fraction"
        ),
        "opportunity_budget": path.get("opportunity_budget"),
        "estimated_local_story_impact_pct": path.get(
            "estimated_local_story_impact_pct"
        ),
        "measured_priority_pct": measured_priority,
        "evidence": path.get("evidence"),
        "work_fingerprints": sorted({
            ref.get("semantic_key") or f"{ref['entry_key']}|{ref['hotspot_key']}"
            for ref in fingerprint_refs
        }),
    }
    if path.get("opportunity_budget"):
        from opportunity_budget import rank
        rank(path["opportunity_budget"])
        opp["opportunity_budget"] = path["opportunity_budget"]
    opp.setdefault("observations", []).append(observation)
    if opp["status"] in MECHANISM_TERMINAL or not update_sizing:
        # Terminal mechanisms keep the fields their verdict used; covered-by
        # wrapper observations are overlap provenance, not a replacement for
        # the owning mechanism's sizing identity.
        return
    # A mechanism rediscovered in several story silos is sized against its
    # highest estimated local-story impact. Once sizing begins, keep the
    # evidence identity frozen and retain later observations as provenance.
    current_value = opp.get("expected_value")
    observation_value = observation.get("expected_value")
    can_retarget = opp.get("status") in ("candidate", "investigating", "parked")
    if (
        can_retarget
        and current_value is not None
        and observation_value is not None
        and float(observation_value) < float(current_value)
    ):
        return
    if not can_retarget and opp.get("observations", [])[:-1]:
        return
    opp["anchor"] = observation["anchor"]
    opp["share_pct"] = observation["share_pct"]
    opp["stories"] = observation["stories"]
    if observation["target_story"] is not None:
        opp["target_story"] = observation["target_story"]
    opp["dossier"] = observation["dossier"]
    opp["expected_value"] = observation["expected_value"]
    opp["expected_value_unit"] = observation["expected_value_unit"]
    opp["story_profile_share_pct"] = observation["story_profile_share_pct"]
    opp["estimated_avoidable_fraction"] = observation[
        "estimated_avoidable_fraction"
    ]
    opp["estimated_local_story_impact_pct"] = observation[
        "estimated_local_story_impact_pct"
    ]
    if measured_priority is not None:
        opp["measured_priority_pct"] = measured_priority


def validate_new_identity(ledger, *, kind, area_key, mechanism_key,
                          profile_id, parent_id=None):
    if parent_id is not None:
        ledger.opp(parent_id)
    if kind == "discovery":
        if mechanism_key:
            raise CampaignError("discovery records cannot have --mechanism-key")
        if not profile_id:
            raise CampaignError("discovery records require --profile-id")
        ledger.profile(profile_id)
        for opp in ledger.data["opportunities"]:
            if (
                opp.get("kind") == "discovery"
                and opp.get("area_key") == area_key
                and opp.get("profile_id") == profile_id
            ):
                raise CampaignError(
                    f"Area {area_key!r} is already represented by discovery "
                    f"#{opp['id']:03d} for profile {profile_id!r}"
                )
    else:
        if not mechanism_key:
            raise CampaignError("mechanism records require --mechanism-key")
        if not test_bypass_active():
            if not ledger.data.get("profile_runs"):
                raise CampaignError(
                    f"No profile has been ingested for benchmark "
                    f"'{ledger.data['config']['benchmark']}'. Grounding in an exact-window "
                    "profile is mandatory; run 'remote_measure.py --mode profile' and "
                    "'campaign.py profile' first."
                )
            if parent_id is None:
                raise CampaignError(
                    "Mechanism candidates must specify --parent <discovery_id> pointing to "
                    "an active discovery opportunity from an ingested profile. Ungrounded "
                    "candidate additions are forbidden."
                )
            parent = ledger.opp(parent_id)
            if parent.get("kind") != "discovery":
                raise CampaignError(
                    f"Parent opportunity #{parent_id:03d} must be a discovery record, "
                    f"not {parent.get('kind')}"
                )
        existing = ledger.mechanism(area_key, mechanism_key)
        if existing:
            raise CampaignError(
                f"Mechanism {area_key}/{mechanism_key} already exists as "
                f"#{existing['id']:03d} [{existing['status']}]; reuse its history "
                "instead of retrying the same path"
            )
        if profile_id:
            ledger.profile(profile_id)


def load_profile_areas(path):
    try:
        with open(path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read profile area JSON {path}: {exc}") from exc
    if not isinstance(manifest, dict):
        raise CampaignError(
            "Profile reconciliation JSON must be an object with areas and "
            "source_exclusions"
        )
    areas = manifest.get("areas")
    source_exclusions = manifest.get("source_exclusions")
    parked_mechanisms = manifest.get("parked_mechanisms")
    if not all(isinstance(value, list) for value in (
        areas, source_exclusions, parked_mechanisms
    )):
        raise CampaignError(
            "Profile reconciliation requires areas, source_exclusions, and "
            "parked_mechanisms arrays"
        )
    seen = set()
    for index, area in enumerate(areas, 1):
        if not isinstance(area, dict):
            raise CampaignError(f"Profile area {index} must be a JSON object")
        missing = [
            key for key in ("area_key", "anchor", "marginal_share_pct")
            if area.get(key) is None
        ]
        if missing:
            raise CampaignError(
                f"Profile area {index} is missing: {', '.join(missing)}"
            )
        area["area_key"] = require_stable_key(
            area["area_key"], f"Profile area {index} area_key"
        )
        if area["area_key"] in seen:
            raise CampaignError(
                f"Profile area manifest repeats area_key {area['area_key']!r}"
            )
        seen.add(area["area_key"])
        if not isinstance(area["anchor"], str) or not area["anchor"].strip():
            raise CampaignError(f"Profile area {index} anchor must be nonempty text")
        area["marginal_share_pct"] = require_finite_number(
            area["marginal_share_pct"],
            f"Profile area {index} marginal_share_pct",
            nonnegative=True,
        )
        if (
            area.get("expected_value") is not None
            or area.get("expected_value_unit") is not None
        ):
            raise CampaignError(
                f"Profile area {index} cannot set expected_value; coarse discoveries "
                "always rank by their hottest measured child"
            )
        disposition = area.get("disposition", "discover")
        if disposition not in ("discover", "exclude"):
            raise CampaignError(
                f"Profile area {index} disposition must be discover or exclude"
            )
        if disposition == "exclude":
            category = area.get("exclusion_category")
            if category not in ("payload-dominated", "idle-wait", "out-of-scope"):
                raise CampaignError(
                    f"Profile area {index} exclusion_category must be "
                    "payload-dominated, idle-wait, or out-of-scope"
                )
            if not area.get("exclusion_reason") or not area.get("exclusion_evidence"):
                raise CampaignError(
                    f"Profile area {index} exclusion requires reason and evidence"
                )
        area["disposition"] = disposition
        if not isinstance(area.get("source_refs"), list) or not area["source_refs"]:
            raise CampaignError(
                f"Profile area {index} requires nonempty source_refs"
            )
    for index, exclusion in enumerate(source_exclusions, 1):
        if not isinstance(exclusion, dict):
            raise CampaignError(f"Source exclusion {index} must be an object")
        if exclusion.get("category") not in ("not-recurrent", "context-variant"):
            raise CampaignError(
                f"Source exclusion {index} category must be not-recurrent or "
                "context-variant"
            )
        if not exclusion.get("evidence"):
            raise CampaignError(f"Source exclusion {index} requires evidence")
    return areas, source_exclusions, parked_mechanisms


def validate_parked_reconciliation(ledger, areas, entries):
    parked = {
        opp["mechanism_key"]: opp
        for opp in ledger.data["opportunities"]
        if opp.get("kind") == "mechanism" and opp["status"] == "parked"
    }
    seen = set()
    discoverable_areas = {
        area["area_key"] for area in areas if area["disposition"] == "discover"
    }
    for index, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise CampaignError(f"Parked reconciliation {index} must be an object")
        key = entry.get("mechanism_key")
        if key not in parked:
            raise CampaignError(
                f"Parked reconciliation {index} names non-parked mechanism {key!r}"
            )
        if key in seen:
            raise CampaignError(f"Parked mechanism {key!r} is reconciled twice")
        seen.add(key)
        disposition = entry.get("disposition")
        if disposition not in ("recurrent", "not-recurrent"):
            raise CampaignError(
                f"Parked mechanism {key!r} disposition must be recurrent or not-recurrent"
            )
        if disposition == "recurrent":
            if entry.get("area_key") not in discoverable_areas:
                raise CampaignError(
                    f"Recurrent parked mechanism {key!r} must map to a discoverable area"
                )
        else:
            if not entry.get("evidence"):
                raise CampaignError(
                    f"Nonrecurrent parked mechanism {key!r} requires evidence"
                )
            prior_fingerprints = {
                fingerprint
                for observation in parked[key].get("observations", [])
                for fingerprint in observation.get("work_fingerprints", [])
            }
            latest_fingerprints = {
                ref.get("semantic_key") or f"{ref['entry_key']}|{ref['hotspot_key']}"
                for area in areas
                for ref in area.get("expected_work_refs", [])
            }
            recurring = prior_fingerprints & latest_fingerprints
            if recurring:
                raise CampaignError(
                    f"Parked mechanism {key!r} cannot be called nonrecurrent; "
                    "its profiler work fingerprints recur: "
                    + ", ".join(sorted(recurring))
                )
    missing = set(parked) - seen
    if missing:
        raise CampaignError(
            "Profile does not reconcile parked mechanism(s): "
            + ", ".join(sorted(missing))
        )
    return entries


def source_ref_tuple(value, label):
    if not isinstance(value, dict):
        raise CampaignError(f"{label} must be an object")
    capture_id = value.get("capture_id")
    entry_key = value.get("entry_key")
    if not isinstance(capture_id, str) or not capture_id.strip():
        raise CampaignError(f"{label} requires capture_id")
    if not isinstance(entry_key, str) or not entry_key.strip():
        raise CampaignError(f"{label} requires entry_key")
    return capture_id, entry_key


def validate_source_accounting(areas, source_exclusions, summaries):
    expected = set()
    occurrences = {}
    semantic_occurrences = {}
    hotspot_inventory = {}
    all_capture_ids = {summary["capture_id"] for summary in summaries}
    for summary in summaries:
        capture_id = summary["capture_id"]
        entries = summary.get("frontier_entries")
        if not isinstance(entries, list) or any(
            not isinstance(item, str) or not item.strip() for item in entries
        ):
            raise CampaignError(
                f"Capture {capture_id} has no valid exhaustive frontier_entries"
            )
        if len(entries) != len(set(entries)):
            raise CampaignError(f"Capture {capture_id} repeats a frontier entry")
        for entry_key in entries:
            ref = (capture_id, entry_key)
            expected.add(ref)
            occurrences.setdefault(entry_key, set()).add(capture_id)
            semantic_occurrences.setdefault(
                semantic_entry_identity(entry_key), set()
            ).add(capture_id)
        for item in summary["frontier_inventory"]:
            hotspot_inventory[(capture_id, item["entry_key"])] = item["work_items"]

    accounted = {}
    source_area_map = {}
    for index, area in enumerate(areas, 1):
        refs = [
            source_ref_tuple(ref, f"Profile area {index} source ref")
            for ref in area["source_refs"]
        ]
        if len(refs) != len(set(refs)):
            raise CampaignError(f"Profile area {index} repeats a source ref")
        # One area maps one semantic entry. Context digests may legitimately
        # differ per capture, and a symbol may move between context/function
        # aggregates, so exact entry keys only have to agree on represented
        # profiler work identity.
        semantic_ids = {
            semantic_entry_identity(entry_key) for _, entry_key in refs
        }
        if len(semantic_ids) != 1:
            raise CampaignError(
                f"Profile area {index} coalesces distinct frontier entries; "
                "each recurrent machine entry requires its own area"
            )
        # Story-qualified entries pin the area to its silo; the recorded
        # target story is what sizing and verification must measure against.
        area["target_story"] = split_story_entry_key(refs[0][1])[0]
        ref_captures = sorted(capture_id for capture_id, _ in refs)
        if ref_captures != sorted(all_capture_ids):
            raise CampaignError(
                f"Profile area {index} must map entry "
                f"{next(iter(semantic_ids))!r} exactly once from every capture"
            )
        work_refs = []
        for capture_id, source_entry in sorted(refs):
            if (capture_id, source_entry) not in expected:
                raise CampaignError(
                    f"Profile area {index} names source entry {source_entry!r} "
                    f"that capture {capture_id!r} did not report"
                )
            work_refs.extend({
                "capture_id": capture_id,
                "entry_key": source_entry,
                "hotspot_key": work["hotspot_key"],
                "semantic_key": work["semantic_key"],
                "measured_share_pct": work["measured_share_pct"],
            } for work in hotspot_inventory[(capture_id, source_entry)])
        area["expected_work_refs"] = work_refs
        for ref in refs:
            if ref in accounted:
                raise CampaignError(f"Source frontier entry {ref} is accounted twice")
            accounted[ref] = f"area {area['area_key']}"
            source_area_map[ref[1]] = area["area_key"]
    area_semantics = {
        semantic_entry_identity(entry_key) for entry_key in source_area_map
    }

    for index, exclusion in enumerate(source_exclusions, 1):
        ref = source_ref_tuple(exclusion, f"Source exclusion {index}")
        semantic_id = semantic_entry_identity(ref[1])
        if exclusion.get("category") == "context-variant":
            # A surplus same-symbol caller context whose siblings are already
            # reconciled as an area; legal only when that area exists, so the
            # symbol's recurrence can never be dropped wholesale.
            if not split_story_entry_key(ref[1])[1].startswith("context:"):
                raise CampaignError(
                    f"Source entry {ref[1]!r} is not a caller context and "
                    "cannot use category context-variant"
                )
            if semantic_id not in area_semantics:
                raise CampaignError(
                    f"Source entry {ref[1]!r} cannot be a context-variant "
                    f"exclusion: no reconciled area covers {semantic_id!r}"
                )
        else:
            if occurrences.get(ref[1], set()) == all_capture_ids:
                raise CampaignError(
                    f"Recurrent source entry {ref[1]!r} cannot be excluded as "
                    "not-recurrent"
                )
            if semantic_occurrences.get(semantic_id, set()) == all_capture_ids:
                raise CampaignError(
                    f"Source entry {ref[1]!r} cannot be excluded as "
                    f"not-recurrent: its semantic profiler identity "
                    f"{semantic_id!r} occurs in every capture. Context path "
                    "digests and context/function representation are "
                    "capture-fragile; reconcile the same-symbol entries as one "
                    "area with per-capture source_refs (surplus contexts may "
                    "use category context-variant)"
                )
        if ref in accounted:
            raise CampaignError(f"Source frontier entry {ref} is accounted twice")
        accounted[ref] = exclusion["category"]

    accounted_set = set(accounted)
    missing = expected - accounted_set
    unexpected = accounted_set - expected
    if missing:
        preview = ", ".join(f"{capture}:{entry}" for capture, entry in sorted(missing)[:5])
        raise CampaignError(f"Reconciliation omits source frontier entries: {preview}")
    if unexpected:
        preview = ", ".join(
            f"{capture}:{entry}" for capture, entry in sorted(unexpected)[:5]
        )
        raise CampaignError(f"Reconciliation names unknown source entries: {preview}")
    return source_area_map


def cmd_profile(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    if any(p["id"] == args.id for p in ledger.data.get("profile_runs", [])):
        raise CampaignError(f"Profile id {args.id!r} already exists")
    feature = ledger.data["config"]["feature"]
    if feature not in feature_names(args.enable_features):
        raise CampaignError(
            f"Profile must explicitly enable campaign feature {feature}"
        )
    provenance = verify_profile_head(
        find_repo_root(pathlib.Path.cwd()), args.sha,
        ledger.data["config"].get("branch"),
        allow_unverified=args.allow_unverified_repository,
    )
    floor = ledger.data["config"]["share_floor_pct"]
    summaries = load_capture_summaries(
        args.capture_summaries,
        expected_sha=provenance["resolved_sha"],
        feature=feature,
        expected_features=args.enable_features,
        floor_pct=floor,
        benchmark=ledger.data["config"]["benchmark"],
        metric_model=ledger.data["config"]["metric_model"],
    )
    if not test_bypass_active():
        expected_skill = ledger.data["config"].get("skill_tree_sha256")
        if any(summary.get("skill_tree_sha256") != expected_skill for summary in summaries):
            raise CampaignError(
                "Profile capture summary was produced by a different skill tree"
            )
    areas, source_exclusions, parked_entries = load_profile_areas(args.areas)
    profile_challenges = validate_gate_challenges(
        args,
        gate="reprofile" if ledger.data.get("profile_runs") else "profile",
        artifact_digests=[
            sha256_file(args.areas),
            sha256_file(args.capture_summaries),
            *[summary.get("artifact_sha256") for summary in summaries],
        ],
    )
    source_area_map = validate_source_accounting(areas, source_exclusions, summaries)
    excluded_with_children = [
        area for area in areas
        if area["disposition"] == "exclude"
        and any(
            ref["hotspot_key"] != "@root"
            for ref in area.get("expected_work_refs", [])
        )
    ]
    if excluded_with_children:
        raise CampaignError(
            "A composite frontier area cannot be excluded wholesale while it "
            "contains material related/alternative hotspots; mark it discover "
            "and decompose each child: "
            + ", ".join(area["area_key"] for area in excluded_with_children)
        )
    historical_source_areas = ledger.data.setdefault("source_area_keys", {})
    for entry_key, area_key in source_area_map.items():
        prior = historical_source_areas.get(entry_key)
        if prior and prior != area_key:
            raise CampaignError(
                f"Source entry {entry_key!r} was previously area {prior!r}; "
                f"cannot silently rename it to {area_key!r}"
            )
    prior_semantic_areas = semantic_area_keys(historical_source_areas)
    current_semantic_areas = semantic_area_keys(source_area_map)
    for semantic, current_keys in current_semantic_areas.items():
        prior_keys = prior_semantic_areas.get(semantic, [])
        reused = set(current_keys) & set(prior_keys)
        required_reuse = min(len(current_keys), len(prior_keys))
        if prior_keys and len(reused) < required_reuse:
            raise CampaignError(
                f"Semantic source entry {semantic!r} previously used area "
                f"key(s) {prior_keys}; cannot silently replace them with "
                f"{current_keys}. Reuse the prior key(s) even when exact "
                "context digests or aggregate kinds changed"
            )
    parked_entries = validate_parked_reconciliation(ledger, areas, parked_entries)
    discoveries = [area for area in areas if area["disposition"] == "discover"]
    excluded = [area for area in areas if area["disposition"] == "exclude"]
    below_floor = [
        area for area in discoveries if area["marginal_share_pct"] < floor
    ]
    if below_floor:
        raise CampaignError(
            "Discoverable profile rows fall below the campaign floor "
            f"{floor}%: " + ", ".join(area["area_key"] for area in below_floor)
        )
    total_share = sum(area["marginal_share_pct"] for area in discoveries)
    observed_share = sum(area["marginal_share_pct"] for area in areas)
    ledger.data.setdefault("profile_runs", []).append({
        "id": args.id,
        "ts": utc_now(),
        "sha": provenance["resolved_sha"],
        **provenance,
        "enable_features": args.enable_features,
        "total_share_pct": total_share,
        "artifacts": args.artifacts,
        "notes": args.notes,
        "area_count": len(discoveries),
        "inventory_count": len(areas),
        "excluded_areas": excluded,
        "source_exclusions": source_exclusions,
        "parked_mechanisms": parked_entries,
        "source_area_map": source_area_map,
        "observed_share_pct": observed_share,
        "areas_manifest": args.areas,
        "areas_manifest_sha256": sha256_file(args.areas),
        "captures": len(summaries),
        "capture_ids": [summary["capture_id"] for summary in summaries],
        "capture_summaries": args.capture_summaries,
        "capture_summaries_sha256": sha256_file(args.capture_summaries),
        "capture_provenance": [
            {
                "capture_id": summary["capture_id"],
                "story_frontiers": summary["story_frontiers"],
                "artifact_sha256": summary["artifact_sha256"],
                "stories": summary["stories"],
                "enable_features": summary["enable_features"],
                "repetitions": summary["repetitions"],
                "interval_kind": summary.get("interval_kind"),
                "metric_weighting": summary.get("metric_weighting"),
                "nominal_samples_at_floor": summary.get(
                    "nominal_samples_at_floor"
                ),
                "build_provenance": summary.get("build_provenance"),
                "analyzer_min_inclusive_share": summary[
                    "analyzer_min_inclusive_share"
                ],
                "analyzer_min_marginal_share": summary[
                    "analyzer_min_marginal_share"
                ],
            }
            for summary in summaries
        ],
        "sequence": ledger.data["next_sequence"],
    })
    ledger.data["next_sequence"] += 1
    ledger.data["source_area_keys"].update(source_area_map)
    for area in discoveries:
        discovery = new_opportunity(
            ledger,
            kind="discovery",
            anchor=area["anchor"],
            area_key=area["area_key"],
            profile_id=args.id,
            share=area["marginal_share_pct"],
            stories=area.get("stories"),
            dossier=area.get("dossier"),
            notes=area.get("notes"),
        )
        discovery["source_refs"] = area["source_refs"]
        discovery["expected_work_refs"] = area["expected_work_refs"]
        discovery["measured_priority_pct"] = measured_priority_from_refs(
            area["expected_work_refs"]
        )
        discovery["target_story"] = area.get("target_story")
    record_gate_challenges(
        ledger,
        gate="reprofile" if len(ledger.data.get("profile_runs", [])) > 1 else "profile",
        subject=args.id,
        reports=profile_challenges,
    )
    ledger.save()
    print(
        f"Recorded profile {args.id}: {len(discoveries)} discoverable / "
        f"{len(excluded)} excluded area(s), {total_share:.2f}% eligible share"
    )
    return 0


def load_scaffold_summaries(path):
    try:
        with open(path) as f:
            summaries = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read capture summaries {path}: {exc}") from exc
    if not isinstance(summaries, list) or len(summaries) < 2:
        raise CampaignError(
            "Capture summaries must be an array with at least two captures"
        )
    for index, summary in enumerate(summaries, 1):
        if not isinstance(summary, dict) or not summary.get("capture_id"):
            raise CampaignError(f"Capture summary {index} has no capture_id")
        if not isinstance(summary.get("frontier_entries"), list) or not isinstance(
            summary.get("frontier_inventory"), list
        ):
            raise CampaignError(
                f"Capture {summary.get('capture_id')} has no frontier "
                "inventory; rerun remote_measure.py --mode profile with "
                "--summary-out"
            )
    return summaries


def entry_display_name(entry_key):
    story, bare_key = split_story_entry_key(entry_key)
    semantic = semantic_entry_identity(bare_key)
    name = semantic.split(":", 1)[1] if ":" in semantic else semantic
    return f"{story}/{name}" if story is not None else name


def cmd_profile_scaffold(args):
    """Emit a prefilled reconciliation manifest from the machine inventories.

    Recurrence, source refs, shares, and parked-mechanism reconciliation are
    mechanical joins of the capture summaries; deriving them here leaves the
    profiler only the judgment calls (dispositions, exclusion evidence) and
    removes the error-prone hand-matching of raw entry keys.
    """
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    summaries = load_scaffold_summaries(args.capture_summaries)
    capture_order = [summary["capture_id"] for summary in summaries]
    all_captures = set(capture_order)
    root_share = {}
    entry_order = []
    by_semantic = {}
    inventories = {}
    for summary in summaries:
        capture_id = summary["capture_id"]
        inventory = {
            item.get("entry_key"): item.get("work_items", [])
            for item in summary["frontier_inventory"]
            if isinstance(item, dict)
        }
        inventories[capture_id] = inventory
        for entry_key in summary["frontier_entries"]:
            if not isinstance(entry_key, str) or not entry_key:
                continue
            root_share[(capture_id, entry_key)] = next((
                work.get("measured_share_pct", 0.0)
                for work in inventory.get(entry_key, [])
                if isinstance(work, dict) and work.get("hotspot_key") == "@root"
            ), 0.0)
            semantic = semantic_entry_identity(entry_key)
            if semantic not in by_semantic:
                entry_order.append(semantic)
            by_semantic.setdefault(semantic, {}).setdefault(
                capture_id, []
            ).append(entry_key)

    prior_area_keys = ledger.data.get("source_area_keys", {})
    prior_semantic_area_keys = semantic_area_keys(prior_area_keys)
    used_area_keys = set()

    def derive_area_key(entry_keys):
        for entry_key in entry_keys:
            prior = prior_area_keys.get(entry_key)
            if prior and prior not in used_area_keys:
                used_area_keys.add(prior)
                return prior
        semantic = semantic_entry_identity(entry_keys[0])
        for prior in prior_semantic_area_keys.get(semantic, []):
            if prior not in used_area_keys:
                used_area_keys.add(prior)
                return prior
        base = canonical_key(entry_display_name(entry_keys[0]))
        candidate = base
        suffix = 2
        while candidate in used_area_keys:
            candidate = f"{base}-{suffix}"
            suffix += 1
        used_area_keys.add(candidate)
        return candidate

    areas = []
    source_exclusions = []
    for semantic in entry_order:
        per_capture = by_semantic[semantic]
        for capture_id, entries in per_capture.items():
            entries.sort(
                key=lambda entry: root_share[(capture_id, entry)], reverse=True
            )
        if set(per_capture) == all_captures:
            paired = min(len(entries) for entries in per_capture.values())
            for rank in range(paired):
                refs = [
                    {"capture_id": capture_id,
                     "entry_key": per_capture[capture_id][rank]}
                    for capture_id in capture_order
                ]
                shares = [
                    root_share[(ref["capture_id"], ref["entry_key"])]
                    for ref in refs
                ]
                area = {
                    "area_key": derive_area_key(
                        [ref["entry_key"] for ref in refs]
                    ),
                    "anchor": entry_display_name(refs[0]["entry_key"]),
                    "target_story": split_story_entry_key(
                        refs[0]["entry_key"]
                    )[0],
                    "marginal_share_pct": sum(shares) / len(shares),
                    "disposition": "discover",
                    "source_refs": refs,
                }
                if paired > 1:
                    area["notes"] = (
                        "scaffold paired same-symbol caller contexts by "
                        "per-capture share rank; verify the pairing"
                    )
                areas.append(area)
            for capture_id in capture_order:
                for entry_key in per_capture[capture_id][paired:]:
                    source_exclusions.append({
                        "capture_id": capture_id,
                        "entry_key": entry_key,
                        "category": "context-variant",
                        "evidence": (
                            "surplus same-symbol caller context; sibling "
                            "contexts are reconciled as an area"
                        ),
                    })
        else:
            absent = sorted(all_captures - set(per_capture))
            for capture_id in capture_order:
                for entry_key in per_capture.get(capture_id, []):
                    source_exclusions.append({
                        "capture_id": capture_id,
                        "entry_key": entry_key,
                        "category": "not-recurrent",
                        "evidence": (
                            "absent from capture(s): " + ", ".join(absent)
                        ),
                    })

    entry_to_area = {
        ref["entry_key"]: area["area_key"]
        for area in areas
        for ref in area["source_refs"]
    }
    area_semantic_work = {}
    for area in areas:
        for ref in area["source_refs"]:
            for work in inventories[ref["capture_id"]].get(ref["entry_key"], []):
                if isinstance(work, dict) and work.get("semantic_key"):
                    area_semantic_work.setdefault(
                        work["semantic_key"], area["area_key"]
                    )
    parked_entries = []
    for opp in ledger.data["opportunities"]:
        if opp.get("kind") != "mechanism" or opp["status"] != "parked":
            continue
        fingerprints = {
            fingerprint
            for observation in opp.get("observations", [])
            for fingerprint in observation.get("work_fingerprints", [])
        }
        recurring = sorted(fingerprints & set(area_semantic_work))
        if recurring:
            parked_entries.append({
                "mechanism_key": opp["mechanism_key"],
                "disposition": "recurrent",
                "area_key": area_semantic_work[recurring[0]],
                "notes": (
                    "scaffold: prior work fingerprints recur: "
                    + ", ".join(recurring[:3])
                ),
            })
        else:
            parked_entries.append({
                "mechanism_key": opp["mechanism_key"],
                "disposition": "not-recurrent",
                "evidence": (
                    "no prior work fingerprint of this mechanism appears in "
                    "any capture's reconciled area inventory"
                ),
            })

    manifest = {
        "areas": areas,
        "source_exclusions": source_exclusions,
        "parked_mechanisms": parked_entries,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Scaffolded {len(areas)} area(s), {len(source_exclusions)} source "
        f"exclusion(s), {len(parked_entries)} parked reconciliation(s) -> "
        f"{out}"
    )
    print(
        "Review every disposition (discover vs exclude needs the admission "
        "rule) before `campaign.py profile`."
    )
    return 0


def cmd_decompose_scaffold(args):
    """Emit a decomposition skeleton with the primary accounting prefilled.

    One path row per profiler hotspot, work_refs already satisfying the
    exactly-one-primary rule; the investigator supplies only dispositions,
    keys, and evidence. Blank dispositions fail validation, so an unedited
    scaffold cannot be recorded.
    """
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    discovery = ledger.opp(args.opp)
    if discovery.get("kind") != "discovery":
        raise CampaignError("decompose-scaffold takes a discovery opportunity id")
    refs = discovery.get("expected_work_refs") or []
    if not refs:
        raise CampaignError(
            f"Discovery #{discovery['id']:03d} has no profiler work inventory"
        )
    grouped = {}
    order = []
    for ref in refs:
        key = ref["hotspot_key"]
        if key not in grouped:
            order.append(key)
        grouped.setdefault(key, []).append(ref)

    def hotspot_share(key):
        return max(
            ref.get("measured_share_pct", 0.0) or 0.0 for ref in grouped[key]
        )

    order.sort(key=hotspot_share, reverse=True)
    paths = []
    for key in order:
        rows = grouped[key]
        semantic = rows[0].get("semantic_key") or key
        anchor = semantic.split(":", 1)[1] if ":" in semantic else semantic
        if key == "@root":
            anchor = discovery.get("anchor") or anchor
        paths.append({
            "disposition": "",
            "anchor": anchor,
            "share_pct": hotspot_share(key),
            "estimated_avoidable_fraction": None,
            "estimated_local_story_impact_pct": None,
            "evidence": "",
            "work_refs": [
                {
                    "capture_id": ref["capture_id"],
                    "entry_key": ref["entry_key"],
                    "hotspot_key": ref["hotspot_key"],
                    "accounting": "primary",
                }
                for ref in rows
            ],
        })
    area_key = discovery["area_key"]
    ledger_mechanisms = [
        {
            "mechanism_key": opp["mechanism_key"],
            "status": opp["status"],
            "area_key": opp["area_key"],
        }
        for opp in ledger.data["opportunities"]
        if opp.get("kind") == "mechanism" and opp.get("mechanism_key")
        and (opp.get("area_key") == area_key
             or opp.get("area_key", "").startswith(area_key + "/"))
    ]
    scaffold = {
        "area_key": area_key,
        "profile_id": discovery.get("profile_id"),
        "accounting_evidence": "",
        "scaffold_note": (
            "Fill disposition (novel|known|covered-by|mandatory|below-floor|"
            "out-of-scope), evidence, and mechanism_key (novel/known) or "
            "covered_by (covered-by) on every path; fill accounting_evidence. "
            "Novel/known paths also require estimated_avoidable_fraction; "
            "campaign.py derives story_profile_share_pct and "
            "estimated_local_story_impact_pct from profiler-bound work_refs. "
            "work_refs already satisfy the exactly-one-primary rule and "
            "normally need no edits. ledger_mechanisms_for_area lists keys "
            "that must be reconciled as known/below-floor/out-of-scope, "
            "never re-invented"
        ),
        "ledger_mechanisms_for_area": ledger_mechanisms,
        "paths": paths,
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scaffold, indent=2) + "\n")
    print(
        f"Scaffolded {len(paths)} path row(s) for discovery "
        f"#{discovery['id']:03d} ({area_key}) -> {out}"
    )
    return 0


def cmd_add(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    args.share = require_finite_number(args.share, "--share", nonnegative=True)
    expected = {
        "expected_value": args.expected_value,
        "expected_value_unit": args.expected_value_unit,
    }
    validate_expected_value(expected, "--expected-value")
    args.expected_value = expected["expected_value"]
    floor = ledger.data["config"]["share_floor_pct"]
    if args.share < floor:
        print(
            f"warning: share {args.share}% is below the campaign floor {floor}%",
            file=sys.stderr,
        )
    area_key = require_stable_key(
        args.area_key or canonical_key(args.anchor), "--area-key"
    )
    # No --kind preserves the version-1 CLI for hand-created/test ledgers.
    kind = args.kind or "mechanism"
    if kind == "discovery":
        raise CampaignError(
            "Discovery records are created only by `campaign.py profile` from "
            "a reconciled capture manifest; a hand-added discovery would have "
            "no profiler work inventory, so it could never be decomposed or "
            "exhausted"
        )
    mechanism_key = args.mechanism_key
    if args.kind is None and mechanism_key is None:
        mechanism_key = f"legacy-{ledger.data['next_id']:03d}"
    elif mechanism_key is not None:
        mechanism_key = require_stable_key(
            mechanism_key, "--mechanism-key", namespaced=True
        )
    validate_new_identity(
        ledger, kind=kind, area_key=area_key,
        mechanism_key=mechanism_key, profile_id=args.profile_id,
        parent_id=args.parent,
    )
    opp = new_opportunity(
        ledger, kind=kind, anchor=args.anchor, area_key=area_key,
        mechanism_key=mechanism_key, parent_id=args.parent,
        profile_id=args.profile_id, share=args.share, stories=args.stories,
        dossier=args.dossier, expected_value=args.expected_value,
        expected_value_unit=args.expected_value_unit,
        notes=args.notes,
    )
    ledger.save()
    print(f"Added {kind} #{opp['id']:03d}: {args.anchor}")
    return 0


def cmd_advance(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    test_legacy = test_bypass_active()
    gate_challenge_record = None
    src, dst = opp["status"], args.to
    if opp.get("kind") == "discovery" and dst not in ("investigating",):
        raise CampaignError(
            f"Discovery #{opp['id']:03d} cannot advance to {dst}; use "
            "`decompose` to create mechanism children or `exhaust` when the "
            "profiled area has no untried viable path"
        )
    if dst not in FORWARD_TRANSITIONS.get(src, set()):
        raise CampaignError(
            f"Illegal transition {src} -> {dst} for #{opp['id']:03d}. "
            f"Allowed from {src}: {sorted(FORWARD_TRANSITIONS.get(src, set()))}"
        )
    if dst == "sized":
        if not test_legacy:
            from opportunity_budget import rank
            if not opp.get("opportunity_budget") or not rank(opp["opportunity_budget"])["viable_with_budget"]:
                raise CampaignError("sizing requires a causal opportunity_budget that clears the calibrated measurement budget")
        if args.evidence_manifest:
            evidence, evidence_digest = load_gate_evidence(
                args.evidence_manifest, opp=opp, phase="sizing",
                benchmark=ledger.data["config"]["benchmark"],
                metric_model=ledger.data["config"]["metric_model"],
            )
            campaign_floor = float(ledger.data["config"]["share_floor_pct"])
            if test_legacy:
                evidence_floor = require_finite_number(evidence.get("min_avoidable_pct_floor"), "sizing evidence floor", nonnegative=True)
                if not math.isclose(evidence_floor,campaign_floor,rel_tol=0,abs_tol=1e-12):
                    raise CampaignError("Sizing evidence floor does not match campaign floor")
            else:
                # The sizing ceiling must clear the target story's own
                # qualification floor (twice its calibrated MDE once an A/A
                # calibration exists); a smaller removable share cannot be
                # read by the fixed-plan measurement.
                campaign_floor, floor_basis = story_floor_pct(
                    ledger.data["config"],
                    evidence.get("target_story") or opp.get("target_story"),
                )
            avoidable_ci = evidence.get("latency_headroom_ci_pct" if evidence.get("route") == "latency" else
                "avoidable_scored_cycle_share_ci95_pct"
            )
            if not isinstance(avoidable_ci, list) or len(avoidable_ci) != 2:
                raise CampaignError("Sizing evidence lacks an avoidable-share CI")
            if require_finite_number(
                avoidable_ci[0], "sizing avoidable CI lower"
            ) <= (campaign_floor if not test_legacy else campaign_floor - 1e-12):
                raise CampaignError(
                    "Sizing evidence does not clear the campaign's target-story "
                    "avoidable-share floor"
                    + (f" ({campaign_floor:.3f}%: {floor_basis})" if not test_legacy else "")
                )
            if (
                not test_legacy
                and evidence.get("build", {}).get("skill_tree_sha256")
                != ledger.data["config"].get("skill_tree_sha256")
            ):
                raise CampaignError(
                    "sizing evidence was produced by a different skill tree"
                )
            opp["ceiling_pct"] = require_finite_number(
                evidence.get("ceiling_pct"), "evidence ceiling_pct", nonnegative=True
            )
            opp["evidence"] = args.evidence_manifest
            opp["sizing_evidence"] = evidence
            opp["sizing_evidence_sha256"] = evidence_digest
            gate_challenge_record = (
                "sizing",
                validate_gate_challenges(
                    args, gate="sizing", artifact_digests=[evidence_digest]
                ),
            )
        elif test_legacy and args.ceiling is not None and args.evidence:
            opp["ceiling_pct"] = args.ceiling
            opp["evidence"] = args.evidence
        else:
            raise CampaignError(
                "-> sized requires --evidence-manifest from "
                "mechanism_evidence.py summarize; manual ceilings are rejected"
            )
    if dst == "review":
        repo_root = find_repo_root(pathlib.Path.cwd())
        if not test_legacy:
            if not args.build_manifest or not args.test_manifest:
                raise CampaignError(
                    "-> review requires runner-owned --build-manifest and "
                    "--test-manifest receipts; typed test claims are rejected"
                )
            capture_review_base(
                opp,
                repo_root,
                ledger.data["config"]["feature"],
                args.allow_unstaged,
            )
            build_receipt, build_digest = load_command_receipt(
                args.build_manifest, kind="build", source_tree=opp["review_tree"],
                expected_skill_tree=ledger.data["config"].get("skill_tree_sha256"),
            )
            test_receipt, test_digest = load_command_receipt(
                args.test_manifest, kind="test", source_tree=opp["review_tree"],
                expected_skill_tree=ledger.data["config"].get("skill_tree_sha256"),
            )
            opp["build_receipt"] = build_receipt
            opp["build_receipt_path"] = str(pathlib.Path(args.build_manifest).resolve())
            opp["build_receipt_sha256"] = build_digest
            opp["test_receipt"] = test_receipt
            opp["test_receipt_path"] = str(pathlib.Path(args.test_manifest).resolve())
            opp["test_receipt_sha256"] = test_digest
            opp["tests"] = " ".join(test_receipt["command"])
        elif not args.tests:
            raise CampaignError(
                "-> review requires --tests under the unit-test-only bypass"
            )
        if args.verification_manifest:
            evidence, evidence_digest = load_gate_evidence(
                args.verification_manifest, opp=opp, phase="candidate",
                benchmark=ledger.data["config"]["benchmark"],
                metric_model=ledger.data["config"]["metric_model"],
            )
            if not test_legacy:
                if (
                    evidence.get("build", {}).get("skill_tree_sha256")
                    != ledger.data["config"].get("skill_tree_sha256")
                ):
                    raise CampaignError(
                        "candidate evidence was produced by a different skill tree"
                    )
                verify_candidate_build_binding(opp, evidence, repo_root)
            opp["verification_evidence"] = evidence
            opp["verification_evidence_path"] = str(
                pathlib.Path(args.verification_manifest).resolve()
            )
            opp["verification_evidence_sha256"] = evidence_digest
        elif not test_legacy:
            raise CampaignError(
                "-> review requires --verification-manifest proving a paired "
                "work removal or latency reduction inside exact score intervals"
            )
        if test_legacy:
            opp["tests"] = args.tests
        opp["reviews"] = {}
        if test_legacy:
            capture_review_base(
                opp,
                repo_root,
                ledger.data["config"]["feature"],
                args.allow_unstaged,
            )
        else:
            candidate_digests = [
                opp.get("verification_evidence_sha256"),
                opp.get("build_receipt_sha256"),
                opp.get("test_receipt_sha256"),
                opp.get("implementation_manifest", {}).get("patch_sha256"),
            ]
            gate_challenge_record = (
                "candidate",
                validate_gate_challenges(
                    args, gate="candidate", artifact_digests=candidate_digests
                ),
            )
    if src == "review" and dst == "implementing":
        if opp.get("rework_rounds", 0) >= 2 and not args.override_rework_limit:
            raise CampaignError(
                f"#{opp['id']:03d} has used both rework rounds; reject it "
                "(`campaign.py reject`) or pass --override-rework-limit with "
                "a note explaining why a third round is justified"
            )
        opp["rework_rounds"] = opp.get("rework_rounds", 0) + 1
        opp["reviews"] = {}
    if dst == "landed":
        if not args.commit:
            raise CampaignError("-> landed requires --commit <sha>")
        for role in REVIEW_ROLES:
            verdict = opp.get("reviews", {}).get(role, {}).get("verdict")
            if verdict != "PASS":
                raise CampaignError(
                    f"-> landed blocked: {role} verdict is {verdict or 'missing'} "
                    f"(record with `campaign.py review --opp {opp['id']} "
                    f"--role {role} --verdict PASS`)"
                )
        if not test_legacy:
            enforce_freshness_for_landing(ledger)
        if not test_legacy:
            try:
                repo_root = find_repo_root(pathlib.Path.cwd())
                full_sha = git_output(repo_root, "rev-parse", args.commit + "^{commit}").strip()
                opp["unexpected_win"] = args.unexpected_win
                evidence = verify_performance_evidence(
                    ledger.data["config"], opp, args.performance_receipt, repo_root,
                    unexpected=args.unexpected_win,
                )
                opp["performance_receipts"] = evidence
                opp["integration_mapping"] = integration_mapping(
                    repo_root, evidence["candidate_sha"], full_sha,
                    ledger.data["config"]["baseline_sha"])
            except (OSError, KeyError, ValueError, subprocess.SubprocessError) as exc:
                raise CampaignError("performance gates blocked landing: " + str(exc)) from exc
        verify_landed_commit(
            opp, find_repo_root(pathlib.Path.cwd()), args.commit,
            args.skip_review_verification,
            ledger.data["config"].get("branch"),
        )
        opp["commit"] = args.commit
        opp["runtime_change_sequence"] = ledger.data["next_sequence"]
        ledger.data["next_sequence"] += 1
        if args.notes:
            opp["landed_note"] = args.notes
    opp["status"] = dst
    opp["status_since"] = utc_now()
    detail = args.notes or args.evidence or args.tests or ""
    ledger.record(opp, f"{src} -> {dst}" + (f": {detail}" if detail else ""))
    if gate_challenge_record:
        gate, reports = gate_challenge_record
        record_gate_challenges(
            ledger, gate=gate, subject=f"opportunity-{opp['id']}", reports=reports
        )
    ledger.save()
    print(f"#{opp['id']:03d} {src} -> {dst}")
    return 0


def load_decomposition(path):
    try:
        with open(path) as f:
            result = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read decomposition JSON {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise CampaignError("Decomposition JSON must be an object")
    if not result.get("accounting_evidence"):
        raise CampaignError("Decomposition requires accounting_evidence")
    paths = result.get("paths")
    if not isinstance(paths, list) or not paths:
        raise CampaignError("Decomposition paths must be a non-empty array")
    seen = set()
    for index, path_item in enumerate(paths, 1):
        if not isinstance(path_item, dict):
            raise CampaignError(f"Path {index} must be a JSON object")
        disposition = path_item.get("disposition")
        if disposition not in (
            "novel", "known", "covered-by", "mandatory", "below-floor",
            "out-of-scope", "no-qualifying-mechanism"
        ):
            raise CampaignError(
                f"Path {index} has invalid disposition {disposition!r}"
            )
        if disposition == "no-qualifying-mechanism":
            packet = path_item.get("investigation")
            if (not isinstance(packet, dict) or not packet.get("source_revision")
                    or not packet.get("hypotheses") or not packet.get("falsifications")
                    or not packet.get("stop_reason") or not packet.get("budget_used")):
                raise CampaignError("no-qualifying-mechanism requires a bounded investigation packet with revision, hypotheses, falsifications, budget_used and stop_reason")
        missing = []
        if not isinstance(path_item.get("anchor"), str) or not path_item["anchor"].strip():
            missing.append("anchor")
        if path_item.get("share_pct") is None:
            missing.append("share_pct")
        if not isinstance(path_item.get("evidence"), str) or not path_item["evidence"].strip():
            missing.append("evidence")
        if disposition in ("novel", "known") and not path_item.get("mechanism_key"):
            missing.append("mechanism_key")
        if disposition == "covered-by" and not path_item.get("covered_by"):
            missing.append("covered_by")
        if missing:
            raise CampaignError(
                f"Path {index} is missing required fields: {', '.join(missing)}"
            )
        if disposition == "covered-by":
            # A wrapper frame in a recursive chain: the same samples as the
            # owning mechanism seen one level up/down the stack. It stays
            # attached to a tracked mechanism instead of needing a false
            # mandatory/out-of-scope claim or a spurious sibling mechanism.
            if path_item.get("mechanism_key"):
                raise CampaignError(
                    f"Path {index} is covered-by and cannot also carry its own "
                    "mechanism_key; name the owner in covered_by"
                )
            path_item["covered_by"] = require_stable_key(
                path_item["covered_by"], f"Path {index} covered_by",
                namespaced=True,
            )
        work_refs = path_item.get("work_refs")
        if not isinstance(work_refs, list) or not work_refs:
            raise CampaignError(f"Path {index} requires nonempty work_refs")
        normalized_refs = []
        for ref_index, ref in enumerate(work_refs, 1):
            if not isinstance(ref, dict):
                raise CampaignError(
                    f"Path {index} work ref {ref_index} must be an object"
                )
            key = tuple(ref.get(field) for field in (
                "capture_id", "entry_key", "hotspot_key"
            ))
            if any(not isinstance(value, str) or not value for value in key):
                raise CampaignError(
                    f"Path {index} work ref {ref_index} is incomplete"
                )
            accounting = ref.get("accounting")
            if accounting not in ("primary", "overlap"):
                raise CampaignError(
                    f"Path {index} work ref {ref_index} accounting must be "
                    "primary or overlap"
                )
            normalized_refs.append((*key, accounting))
        if len(normalized_refs) != len(set(normalized_refs)):
            raise CampaignError(f"Path {index} repeats a work ref")
        path_item["share_pct"] = require_finite_number(
            path_item["share_pct"], f"Path {index} share_pct", nonnegative=True
        )
        validate_expected_value(path_item, f"Path {index}")
        if path_item.get("area_key") is not None:
            path_item["area_key"] = require_stable_key(
                path_item["area_key"], f"Path {index} area_key"
            )
        if path_item.get("mechanism_key") is not None:
            path_item["mechanism_key"] = require_stable_key(
                path_item["mechanism_key"], f"Path {index} mechanism_key",
                namespaced=True,
            )
            if path_item["mechanism_key"] in seen:
                raise CampaignError(
                    f"Paths repeat mechanism {path_item['mechanism_key']}"
                )
            seen.add(path_item["mechanism_key"])
    return result


def cmd_decompose(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    parent = ledger.opp(args.opp)
    if parent.get("kind") != "discovery":
        raise CampaignError(
            f"#{parent['id']:03d} is a mechanism; only discoveries decompose"
        )
    skeptic_verdict = (
        parent.get("reviews", {}).get("skeptic", {}).get("verdict")
    )
    decomposition_changed_outside_workflow = (
        parent["status"] == "decomposed"
        and parent.get("decomposition_sha256") != decomposition_digest(parent)
    )
    revising_failed_decomposition = (
        parent["status"] == "decomposed"
        and (
            skeptic_verdict == "FAIL"
            or decomposition_changed_outside_workflow
        )
    )
    if parent["status"] != "investigating" and not revising_failed_decomposition:
        raise CampaignError(
            f"Discovery #{parent['id']:03d} is {parent['status']}; "
            "advance it to investigating before its first decomposition, or "
            "record a skeptic FAIL before replacing a reviewed decomposition"
        )
    result = load_decomposition(args.children)
    source_profile = ledger.profile(parent.get("profile_id"))
    decomposition_challenges = validate_gate_challenges(
        args,
        gate="decomposition",
        artifact_digests=[
            sha256_file(args.children),
            *[
                item.get("artifact_sha256")
                for item in source_profile.get("capture_provenance", [])
            ],
        ],
    )
    if result.get("area_key") != parent["area_key"]:
        raise CampaignError("Decomposition area_key does not match its discovery")
    if result.get("profile_id") != parent.get("profile_id"):
        raise CampaignError("Decomposition profile_id does not match its discovery")
    expected_work = {
        tuple(ref[field] for field in ("capture_id", "entry_key", "hotspot_key"))
        for ref in parent.get("expected_work_refs", [])
    }
    measured_work = {
        tuple(ref[field] for field in ("capture_id", "entry_key", "hotspot_key")):
        ref.get("measured_share_pct", 0.0)
        for ref in parent.get("expected_work_refs", [])
    }
    canonical_work = {
        tuple(ref[field] for field in ("capture_id", "entry_key", "hotspot_key")): ref
        for ref in parent.get("expected_work_refs", [])
    }
    floor = ledger.data["config"]["share_floor_pct"]
    primary_counts = {ref: 0 for ref in expected_work}
    for path_item in result["paths"]:
        path_primary = set()
        for ref in path_item["work_refs"]:
            key = tuple(ref[field] for field in (
                "capture_id", "entry_key", "hotspot_key"
            ))
            if key not in expected_work:
                raise CampaignError(f"Decomposition names unknown profiler work ref {key}")
            ref["semantic_key"] = canonical_work[key]["semantic_key"]
            ref["measured_share_pct"] = canonical_work[key]["measured_share_pct"]
            if ref["accounting"] == "primary":
                primary_counts[key] += 1
                path_primary.add(key)
        if path_primary:
            hotspot_keys = {ref[2] for ref in path_primary}
            if len(hotspot_keys) != 1:
                raise CampaignError(
                    "One path cannot swallow distinct profiler hotspots; its "
                    "primary work_refs must share one hotspot_key"
                )
            hotspot_key = next(iter(hotspot_keys))
            expected_for_hotspot = {
                ref for ref in expected_work if ref[2] == hotspot_key
            }
            if path_primary != expected_for_hotspot:
                raise CampaignError(
                    f"Primary path accounting for {hotspot_key!r} must include "
                    "that hotspot from every capture in one semantic row"
                )
            if path_item["disposition"] == "below-floor" and any(
                measured_work[ref] >= floor for ref in path_primary
            ):
                raise CampaignError(
                    f"Profiler measurements for {hotspot_key!r} are at/above "
                    f"the campaign floor {floor}%; it cannot be dispositioned "
                    "below-floor using an investigator-supplied share"
                )
            if path_item["disposition"] in ("novel", "known"):
                story_share = min(measured_work[ref] for ref in path_primary)
                fraction = path_item.get("estimated_avoidable_fraction")
                if fraction is None and test_bypass_active():
                    # Preserve compact legacy unit fixtures; production
                    # decompositions are fail-closed below.
                    fraction = min(
                        1.0,
                        path_item.get("share_pct", 0.0) / story_share
                        if story_share else 0.0,
                    )
                fraction = require_finite_number(
                    fraction,
                    f"Path {path_item['anchor']!r} estimated_avoidable_fraction",
                    nonnegative=True,
                )
                if fraction > 1.0:
                    raise CampaignError(
                        f"Path {path_item['anchor']!r} estimated_avoidable_fraction "
                        "must be at most 1.0"
                    )
                impact = story_share * fraction
                supplied_impact = path_item.get(
                    "estimated_local_story_impact_pct"
                )
                if supplied_impact is not None:
                    supplied_impact = require_finite_number(
                        supplied_impact,
                        f"Path {path_item['anchor']!r} "
                        "estimated_local_story_impact_pct",
                        nonnegative=True,
                    )
                    if not math.isclose(
                        supplied_impact, impact, rel_tol=0, abs_tol=1e-9
                    ):
                        raise CampaignError(
                            f"Path {path_item['anchor']!r} estimated impact "
                            "does not equal profiler story share × avoidable fraction"
                        )
                budget_qualifies = False
                if path_item.get("opportunity_budget"):
                    from opportunity_budget import rank
                    budget_qualifies = rank(path_item["opportunity_budget"])["viable_with_budget"]
                story_name = path_item.get("target_story") or parent.get("target_story")
                path_floor, floor_basis = story_floor_pct(ledger.data["config"], story_name)
                path_floor = max(path_floor, floor)
                if not test_bypass_active() and impact < path_floor and not budget_qualifies:
                    raise CampaignError(
                        f"Path {path_item['anchor']!r} estimated target-story "
                        f"impact {impact:.4f}% is below the qualification floor "
                        f"{path_floor:.3f}% ({floor_basis}). The fixed-plan "
                        "measurement cannot read a smaller effect on this story, "
                        "so implementing it would only spend host time; find a "
                        "mechanism that removes more of the story's work."
                    )
                path_item["qualification_floor_pct"] = path_floor
                path_item["qualification_floor_basis"] = floor_basis
                bind_redundancy_evidence(path_item, story_name, fraction, ledger.dir)
                path_item["story_profile_share_pct"] = story_share
                path_item["estimated_avoidable_fraction"] = fraction
                path_item["estimated_local_story_impact_pct"] = impact
                # The priority value is machine-derived; investigator-typed
                # expected_value values cannot override it.
                path_item["expected_value"] = impact
                path_item["expected_value_unit"] = EXPECTED_VALUE_UNIT
    invalid_counts = {
        ref: count for ref, count in primary_counts.items() if count != 1
    }
    if invalid_counts:
        preview = ", ".join(
            f"{ref} ({count} primary)"
            for ref, count in list(invalid_counts.items())[:5]
        )
        raise CampaignError(
            "Every profiler root/hotspot requires exactly one primary path "
            f"accounting reference: {preview}"
        )
    wrongly_below_floor = [
        item for item in result["paths"]
        if item["disposition"] == "below-floor" and item["share_pct"] >= floor
    ]
    if wrongly_below_floor:
        raise CampaignError(
            "A below-floor path is at or above the campaign floor: "
            + ", ".join(item["anchor"] for item in wrongly_below_floor)
        )
    novel = []
    known = []
    accounted_known = []
    covered = []
    decomposition_keys = {
        path_item["mechanism_key"]
        for path_item in result["paths"]
        if path_item["disposition"] in ("novel", "known")
    }
    for path_item in result["paths"]:
        if path_item["disposition"] == "covered-by":
            owner_key = path_item["covered_by"]
            if owner_key not in decomposition_keys and not ledger.mechanism(
                parent["area_key"], owner_key
            ):
                raise CampaignError(
                    f"Path {path_item['anchor']!r} is covered by unknown "
                    f"mechanism {owner_key!r}; the owner must be a novel/known "
                    "path in this decomposition or an existing ledger mechanism"
                )
            covered.append(path_item)
            continue
        if path_item["disposition"] not in ("novel", "known"):
            if path_item.get("mechanism_key"):
                existing = ledger.mechanism(
                    path_item.get("area_key") or parent["area_key"],
                    path_item["mechanism_key"],
                )
                if existing:
                    if path_item["disposition"] == "mandatory":
                        raise CampaignError(
                            f"Existing mechanism {path_item['mechanism_key']} "
                            "cannot be resolved as mandatory; use known to "
                            "reopen it or below-floor/out-of-scope with evidence"
                        )
                    accounted_known.append((existing, path_item))
            continue
        area_key = path_item.get("area_key") or parent["area_key"]
        existing = ledger.mechanism(area_key, path_item["mechanism_key"])
        if path_item["disposition"] == "novel":
            if existing:
                raise CampaignError(
                    f"Path {path_item['mechanism_key']} is marked novel but "
                    f"already exists as #{existing['id']:03d}"
                )
            novel.append((path_item, area_key))
        else:
            if not existing:
                raise CampaignError(
                    f"Path {path_item['mechanism_key']} is marked known but "
                    "does not exist in the ledger"
                )
            known.append((existing, path_item))

    created = []
    for path_item, area_key in novel:
        opp = new_opportunity(
            ledger,
            kind="mechanism",
            anchor=path_item["anchor"],
            area_key=area_key,
            mechanism_key=path_item["mechanism_key"],
            parent_id=parent["id"],
            profile_id=parent.get("profile_id"),
            share=path_item["share_pct"],
            stories=path_item.get("stories") or parent.get("stories"),
            dossier=path_item.get("dossier") or parent.get("dossier"),
            expected_value=path_item.get("expected_value"),
            expected_value_unit=path_item.get("expected_value_unit"),
            notes=path_item.get("notes"),
        )
        opp["target_story"] = parent.get("target_story")
        record_mechanism_observation(opp, parent, path_item)
        created.append(opp)
    for opp, path_item in known:
        profile_id = parent.get("profile_id")
        if profile_id and profile_id not in opp.setdefault("source_profile_ids", []):
            opp["source_profile_ids"].append(profile_id)
            ledger.record(
                opp,
                f"rediscovered under discovery #{parent['id']:03d} "
                f"in profile {profile_id}",
            )
        if parent["id"] not in opp.setdefault("discovery_ids", []):
            opp["discovery_ids"].append(parent["id"])
        record_mechanism_observation(opp, parent, path_item)
        if opp["status"] == "parked":
            opp["status"] = "candidate"
            opp["status_since"] = utc_now()
            opp["reason"] = None
            ledger.record(
                opp,
                f"automatically reopened because profile {profile_id} "
                "rediscovered the parked mechanism",
            )
    for opp, path_item in accounted_known:
        profile_id = parent.get("profile_id")
        if profile_id and profile_id not in opp.setdefault("source_profile_ids", []):
            opp["source_profile_ids"].append(profile_id)
        record_mechanism_observation(opp, parent, path_item)
        ledger.record(
            opp,
            f"accounted as {path_item['disposition']} under discovery "
            f"#{parent['id']:03d} in profile {profile_id}",
        )
    covered_owners = []
    for path_item in covered:
        owner = ledger.mechanism(parent["area_key"], path_item["covered_by"])
        if owner is None:
            raise CampaignError(
                f"Covered-by owner {path_item['covered_by']!r} did not "
                "materialize during decomposition"
            )
        profile_id = parent.get("profile_id")
        if profile_id and profile_id not in owner.setdefault("source_profile_ids", []):
            owner["source_profile_ids"].append(profile_id)
        if parent["id"] not in owner.setdefault("discovery_ids", []):
            owner["discovery_ids"].append(parent["id"])
        # A novel/known owner in this decomposition already has a current
        # observation. A ledger-only owner does not: record one so this
        # recurrence has honest profile/discovery provenance.
        current_observation = next((
            observation for observation in reversed(owner.get("observations", []))
            if observation.get("discovery_id") == parent["id"]
            and observation.get("profile_id") == profile_id
        ), None)
        if current_observation is None:
            record_mechanism_observation(
                owner, parent, path_item, update_sizing=False
            )
            current_observation = owner["observations"][-1]
        # Fold the wrapper's profiler fingerprints into the owner so parked/
        # not-recurrent reconciliation in later profiles still sees this work.
        fingerprints = sorted({
            ref.get("semantic_key") or f"{ref['entry_key']}|{ref['hotspot_key']}"
            for ref in path_item["work_refs"]
        })
        merged = set(current_observation.get("work_fingerprints", []))
        merged.update(fingerprints)
        current_observation["work_fingerprints"] = sorted(merged)
        covered_priority = measured_priority_from_refs(path_item["work_refs"])
        if covered_priority is not None:
            prior_priority = current_observation.get("measured_priority_pct")
            current_observation["measured_priority_pct"] = max(
                covered_priority, prior_priority or 0.0
            )
            if owner["status"] not in MECHANISM_TERMINAL:
                owner["measured_priority_pct"] = max(
                    covered_priority, owner.get("measured_priority_pct") or 0.0
                )
        if owner["status"] == "parked":
            owner["status"] = "candidate"
            owner["status_since"] = utc_now()
            owner["reason"] = None
            ledger.record(
                owner,
                f"automatically reopened because profile {profile_id} "
                "rediscovered the mechanism through a covered-by wrapper",
            )
        ledger.record(
            owner,
            f"covers same-work wrapper hotspot {path_item['anchor']!r} under "
            f"discovery #{parent['id']:03d}",
        )
        covered_owners.append(owner)
    parent["known_mechanism_ids"] = sorted(
        {
            opp["id"]
            for opp in created + [item[0] for item in known] + covered_owners
        }
    )
    parent["accounting_evidence"] = result["accounting_evidence"]
    parent["path_accounting"] = result["paths"]
    parent["decomposition_revision"] = (
        parent.get("decomposition_revision", 0) + 1
    )
    parent["decomposition_sha256"] = decomposition_digest(parent)
    parent["reviews"] = {}
    parent["status"] = "decomposed"
    parent["status_since"] = utc_now()
    action = "revised decomposition" if revising_failed_decomposition else "decomposed"
    detail = (
        f"{action} revision {parent['decomposition_revision']} into "
        f"{len(created)} new mechanism(s); {len(known)} previously known "
        "mechanism(s) reconciled"
    )
    ledger.record(parent, detail)
    record_gate_challenges(
        ledger,
        gate="decomposition",
        subject=f"opportunity-{parent['id']}-revision-{parent['decomposition_revision']}",
        reports=decomposition_challenges,
    )
    ledger.save()
    print(f"Discovery #{parent['id']:03d} {detail}")
    for opp in created:
        print(
            f"  added #{opp['id']:03d} "
            f"{opp['area_key']}/{opp['mechanism_key']}"
        )
    for opp, _ in known:
        print(
            f"  skipped known #{opp['id']:03d} "
            f"{opp['area_key']}/{opp['mechanism_key']} [{opp['status']}]"
        )
    return 0


def cmd_exhaust(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    discovery = ledger.opp(args.opp)
    if discovery.get("kind") != "discovery":
        raise CampaignError("Only a discovery record can be marked exhausted")
    if discovery["status"] != "decomposed":
        raise CampaignError(
            f"Discovery #{discovery['id']:03d} is {discovery['status']}; "
            "record the complete path-accounting decomposition before exhaustion"
        )
    unresolved = [
        child for child in ledger.children(discovery["id"])
        if child["status"] not in MECHANISM_TERMINAL
    ]
    if unresolved:
        ids = ", ".join(f"#{child['id']:03d}" for child in unresolved)
        raise CampaignError(
            f"Discovery #{discovery['id']:03d} still has unresolved child "
            f"mechanisms: {ids}"
        )
    profile_sequence = ledger.profile(discovery["profile_id"]).get("sequence", 0)
    stale_runtime_children = [
        child for child in ledger.children(discovery["id"])
        if (child.get("runtime_change_sequence") or 0) > profile_sequence
    ]
    if stale_runtime_children:
        raise CampaignError(
            "A discovery cannot prove residual exhaustion after an associated "
            "mechanism landed or reverted. Capture a follow-on flag-enabled "
            "profile and use its new discovery."
        )
    skeptic_review = discovery.get("reviews", {}).get("skeptic", {})
    skeptic = skeptic_review.get("verdict")
    current_revision = discovery.get("decomposition_revision", 0)
    current_digest = decomposition_digest(discovery)
    review_is_current = (
        skeptic_review.get("decomposition_revision") == current_revision
        and skeptic_review.get("decomposition_sha256") == current_digest
        and discovery.get("decomposition_sha256") == current_digest
    )
    if skeptic != "PASS" or not review_is_current:
        detail = skeptic or "missing"
        if skeptic == "PASS" and not review_is_current:
            detail = "stale"
        raise CampaignError(
            f"Exhaustion blocked: skeptic verdict is {detail}. "
            "Mandatory/out-of-scope/covered-by claims close an area without "
            "any other gate, so a skeptic must review the decomposition first "
            f"(`campaign.py review --opp {discovery['id']} --role skeptic "
            "--verdict PASS`)"
        )
    exhaustion_challenges = validate_gate_challenges(
        args,
        gate="exhaustion",
        artifact_digests=[
            current_digest,
            skeptic_review.get("report_sha256"),
        ],
    )
    discovery["status"] = "exhausted"
    discovery["status_since"] = utc_now()
    discovery["reason"] = args.reason
    discovery["exhaustion_evidence"] = args.evidence
    ledger.record(
        discovery, f"exhausted: {args.reason}; evidence: {args.evidence}"
    )
    record_gate_challenges(
        ledger,
        gate="exhaustion",
        subject=f"opportunity-{discovery['id']}",
        reports=exhaustion_challenges,
    )
    ledger.save()
    print(f"Discovery #{discovery['id']:03d} exhausted for profile {discovery['profile_id']}")
    return 0


def cmd_squeeze(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] != "implementing":
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}; squeeze rounds are recorded "
            "while implementing"
        )
    opp["squeeze_rounds"] = opp.get("squeeze_rounds", 0) + 1
    detail = f": {args.note}" if args.note else ""
    ledger.record(opp, f"squeeze round {opp['squeeze_rounds']}{detail}")
    ledger.save()
    print(f"#{opp['id']:03d} squeeze round {opp['squeeze_rounds']}")
    return 0


def cmd_review_scaffold(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp.get("kind") == "discovery":
        if args.role != "skeptic" or opp.get("status") != "decomposed":
            raise CampaignError(
                "Discovery review scaffolds require a decomposed discovery "
                "and role=skeptic"
            )
        if opp.get("decomposition_sha256") != decomposition_digest(opp):
            raise CampaignError(
                "Discovery decomposition changed outside the ledger workflow"
            )
        bindings = {
            "review_kind": "discovery-exhaustion",
            "decomposition_revision": opp.get("decomposition_revision"),
            "decomposition_sha256": opp.get("decomposition_sha256"),
        }
    elif opp.get("status") == "review":
        bindings = {
            "review_kind": "mechanism",
            "review_base": opp.get("review_base"),
            "review_tree": opp.get("review_tree"),
            "sizing_evidence_sha256": opp.get("sizing_evidence_sha256"),
            "verification_evidence_sha256": opp.get(
                "verification_evidence_sha256"
            ),
        }
    else:
        raise CampaignError("Review scaffolds require a reviewable opportunity")
    report = {
        "schema_version": 1,
        "opportunity_id": opp["id"],
        "role": args.role,
        **bindings,
        "checks": {name: False for name in review_checks(opp, args.role)},
        "check_evidence": {
            name: "REPLACE with a concrete file/artifact/test reference"
            for name in review_checks(opp, args.role)
        },
        "findings": [],
        "verdict": "FAIL",
        "notes": "Replace with concise artifact-backed reasoning.",
    }
    pathlib.Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print(args.out)
    return 0


EVIDENCE_PATH_RE = re.compile(
    r"(?:/|\b)[\w.@-]+(?:/[\w.@-]+)*\.(?:json|log|patch|txt|md|cc|h|collapsed|data|diff)\b(?::\d+)?"
)
EVIDENCE_DIGEST_RE = re.compile(r"\b[0-9a-f]{12,64}\b")
EVIDENCE_NUMBER_RE = re.compile(r"\d")


def review_evidence_is_specific(text, report_dir, campaign_dir=None):
    """A PASS check must name something a third party can open and a number.

    Accepts an existing file path (absolute, or relative to the report or the
    campaign directory, optionally with :line) or a sha256 prefix, and requires
    at least one digit so the sentence states what was verified rather than
    "verified from measurements and dossiers".
    """
    if not isinstance(text, str) or not EVIDENCE_NUMBER_RE.search(text):
        return False
    if EVIDENCE_DIGEST_RE.search(text):
        return True
    bases = [pathlib.Path(report_dir)]
    if campaign_dir:
        bases.append(pathlib.Path(campaign_dir))
    bases.append(pathlib.Path.cwd())
    for match in EVIDENCE_PATH_RE.finditer(text):
        candidate = pathlib.Path(match.group(0).split(":")[0])
        if candidate.is_absolute():
            if candidate.exists():
                return True
            continue
        if any((base / candidate).exists() for base in bases):
            return True
    return False


def load_review_report(path, *, opp, role, verdict, campaign_dir=None):
    path = pathlib.Path(path)
    try:
        report = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot read review report {path}: {exc}") from exc
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        raise CampaignError("Review report must use schema_version 1")
    expected = {
        "opportunity_id": opp["id"],
        "role": role,
        "verdict": verdict,
    }
    if opp.get("kind") == "discovery":
        expected.update({
            "review_kind": "discovery-exhaustion",
            "decomposition_revision": opp.get("decomposition_revision"),
            "decomposition_sha256": decomposition_digest(opp),
        })
    else:
        expected.update({
            "review_kind": "mechanism",
            "review_base": opp.get("review_base"),
            "review_tree": opp.get("review_tree"),
            "sizing_evidence_sha256": opp.get("sizing_evidence_sha256"),
            "verification_evidence_sha256": opp.get(
                "verification_evidence_sha256"
            ),
        })
    for field, value in expected.items():
        if report.get(field) != value:
            raise CampaignError(
                f"Review report {field} {report.get(field)!r} does not match {value!r}"
            )
    checks = report.get("checks")
    required_checks = review_checks(opp, role)
    if not isinstance(checks, dict) or set(checks) != set(required_checks):
        raise CampaignError(
            "Review report checks must exactly match: "
            + ", ".join(required_checks)
        )
    if any(not isinstance(value, bool) for value in checks.values()):
        raise CampaignError("Every review check must be a JSON boolean")
    check_evidence = report.get("check_evidence")
    if not isinstance(check_evidence, dict) or set(check_evidence) != set(required_checks):
        raise CampaignError(
            "Review check_evidence must exactly match every bounded check"
        )
    if verdict == "PASS":
        weak = [
            name for name, value in check_evidence.items()
            if not isinstance(value, str)
            or len(value.strip()) < 20
            or "replace" in value.lower()
        ]
        if weak:
            raise CampaignError(
                "PASS requires concrete per-check evidence for: " + ", ".join(weak)
            )
        repeated = {
            text for text, count in collections.Counter(
                value.strip().lower() for value in check_evidence.values()
            ).items() if count > 1
        }
        if repeated:
            raise CampaignError(
                "PASS requires distinct evidence per check; the same sentence was "
                "reused for several checks: " + "; ".join(sorted(repeated))[:200]
            )
        unspecific = [
            name for name, value in check_evidence.items()
            if not review_evidence_is_specific(value, path.parent, campaign_dir)
        ]
        if unspecific:
            raise CampaignError(
                "PASS requires each check to cite an existing artifact path or a "
                "bound sha256 prefix plus the number it verified; missing for: "
                + ", ".join(unspecific)
            )
        notes = report.get("notes")
        if (
            not isinstance(notes, str)
            or len(notes.strip()) < 40
            or "replace" in notes.lower()
        ):
            raise CampaignError("PASS requires non-placeholder artifact-backed notes")
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise CampaignError("Review findings must be an array")
    if verdict == "PASS" and (not all(checks.values()) or findings):
        raise CampaignError("PASS requires every bounded check true and no findings")
    return report, sha256_file(path)


def cmd_review(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp.get("kind") == "discovery":
        # Exhaustion review: the skeptic stress-tests the decomposition's
        # mandatory/out-of-scope/covered-by claims before the area can close.
        if args.role != "skeptic":
            raise CampaignError(
                "Discovery decompositions take a skeptic exhaustion review "
                "only; the adversary reviews implementation diffs"
            )
        if opp["status"] != "decomposed":
            raise CampaignError(
                f"Discovery #{opp['id']:03d} is {opp['status']}; the skeptic "
                "reviews a completed decomposition"
            )
        revision = opp.get("decomposition_revision", 0)
        digest = decomposition_digest(opp)
        if opp.get("decomposition_sha256") != digest:
            raise CampaignError(
                f"Discovery #{opp['id']:03d} decomposition changed outside "
                "the ledger workflow; rerun `decompose` before review"
            )
        prior_review = opp.get("reviews", {}).get("skeptic")
        if prior_review and (
            prior_review.get("decomposition_revision") == revision
            or prior_review.get("decomposition_sha256") == digest
        ):
            raise CampaignError(
                f"Discovery #{opp['id']:03d} revision {revision} already has "
                f"a skeptic {prior_review.get('verdict')} verdict. A FAIL can "
                "only be replaced after revising the decomposition with "
                "`campaign.py decompose`"
            )
    elif opp["status"] != "review":
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}, not in review; "
            "advance it to review before recording verdicts"
        )
    report_digest = None
    report_data = None
    if not test_bypass_active():
        if not args.report:
            raise CampaignError(
                "Reviews require a digest-bound report generated by review-scaffold"
            )
        report_data, report_digest = load_review_report(
            args.report, opp=opp, role=args.role, verdict=args.verdict,
            campaign_dir=ledger.dir,
        )
    review = {
        "verdict": args.verdict,
        "notes": args.notes,
        "report": args.report,
        "ts": utc_now(),
        "report_sha256": report_digest,
    }
    if report_data is not None:
        review["checks"] = report_data["checks"]
        review["check_evidence"] = report_data["check_evidence"]
    if opp.get("kind") == "discovery":
        review["decomposition_revision"] = revision
        review["decomposition_sha256"] = digest
    opp.setdefault("reviews", {})[args.role] = review
    ledger.record(opp, f"{args.role} review: {args.verdict}")
    ledger.save()
    print(f"#{opp['id']:03d} {args.role}: {args.verdict}")
    return 0


def _close(args, status, *, allowed_statuses, evidence=None):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] not in allowed_statuses:
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}; cannot mark it {status}. "
            f"Allowed source states: {', '.join(sorted(allowed_statuses))}"
        )
    opp["status"] = status
    opp["status_since"] = utc_now()
    opp["reason"] = args.reason
    if evidence is not None:
        opp["rejection_evidence"] = evidence
    ledger.record(opp, f"{status}: {args.reason}")
    if evidence is not None:
        ledger.record(opp, f"rejection evidence: {evidence}")
    ledger.save()
    print(f"#{opp['id']:03d} {status}: {args.reason}")
    return 0


def cmd_reject(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp.get("kind") == "discovery":
        raise CampaignError(
            f"#{opp['id']:03d} is a discovery area, not one optimization path; "
            "use `decompose`, `exhaust`, or `park` instead of rejecting it"
        )
    if not args.evidence:
        raise CampaignError(
            "Rejecting a mechanism requires --evidence tied to the source or "
            "profile result that rules out this individual path"
        )
    return _close(
        args,
        "rejected",
        allowed_statuses={"investigating", "sized", "implementing", "review"},
        evidence=args.evidence,
    )


def cmd_park(args):
    return _close(
        args,
        "parked",
        allowed_statuses={"candidate", "investigating", "sized"},
    )


def cmd_revert(args):
    """A landed optimization was reverted on the branch (e.g. after a
    regressing checkpoint bisect). Records the revert commit and removes the
    opportunity from the landed count."""
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] != "landed":
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}; revert applies to landed "
            "opportunities"
        )
    full_sha = verify_revert_commit(
        opp,
        find_repo_root(pathlib.Path.cwd()),
        args.revert_commit,
        ledger.data["config"].get("branch"),
    )
    opp["status"] = "reverted"
    opp["status_since"] = utc_now()
    opp["revert_commit"] = full_sha
    opp["runtime_change_sequence"] = ledger.data["next_sequence"]
    ledger.data["next_sequence"] += 1
    opp["reason"] = args.reason
    ledger.record(
        opp, f"reverted by {args.revert_commit[:12]}: {args.reason}"
    )
    ledger.save()
    print(
        f"#{opp['id']:03d} reverted ({len(ledger.landed())} still landed)"
    )
    return 0


def cmd_reopen(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp.get("kind") != "mechanism":
        raise CampaignError("Only an individual mechanism path can be reopened")
    if opp["status"] not in ("rejected", "parked", "reverted"):
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}; reopen applies to "
            "rejected/parked/reverted"
        )
    if opp["status"] in ("rejected", "reverted"):
        if not args.contradicts_prior_evidence or not args.reason:
            raise CampaignError(
                "Rejected/reverted mechanisms stay ruled out. Reopening one "
                "requires --contradicts-prior-evidence and --reason describing "
                "the new evidence. A different mechanism must use a new key."
            )
        opp.setdefault("prior_attempts", []).append({
            "status": opp["status"],
            "reason": opp.get("reason"),
            "commit": opp.get("commit"),
            "revert_commit": opp.get("revert_commit"),
            "ceiling_pct": opp.get("ceiling_pct"),
            "evidence": opp.get("evidence"),
            "ts": utc_now(),
        })
        for field, value in (
            ("ceiling_pct", None), ("evidence", None), ("tests", None),
            ("commit", None), ("revert_commit", None), ("reviews", {}),
            ("rework_rounds", 0), ("squeeze_rounds", 0),
            ("sizing_evidence", None), ("sizing_evidence_sha256", None),
            ("verification_evidence", None),
            ("verification_evidence_sha256", None),
        ):
            opp[field] = value
    opp["status"] = "candidate"
    opp["status_since"] = utc_now()
    opp["reason"] = None
    detail = f": {args.reason}" if args.reason else ""
    ledger.record(opp, f"reopened as candidate{detail}")
    for discovery_id in opp.get("discovery_ids", []):
        discovery = ledger.opp(discovery_id)
        if discovery.get("kind") != "discovery":
            continue
        if discovery["status"] == "exhausted":
            discovery["status"] = "decomposed"
            discovery["status_since"] = utc_now()
            discovery["reason"] = None
            discovery["exhaustion_evidence"] = None
            ledger.record(
                discovery,
                f"exhaustion invalidated because child #{opp['id']:03d} reopened",
            )
        if discovery["status"] == "decomposed" and discovery.get("reviews"):
            discovery["reviews"] = {}
            ledger.record(
                discovery,
                f"exhaustion review invalidated because child "
                f"#{opp['id']:03d} reopened",
            )
    ledger.save()
    print(f"#{opp['id']:03d} reopened")
    return 0


def cmd_note(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    opp.setdefault("notes", []).append(args.text)
    ledger.record(opp, f"note: {args.text}")
    ledger.save()
    return 0


def cmd_checkpoint_targets(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    stories = landed_target_stories(ledger)
    if not stories:
        raise CampaignError("No landed target stories are available")
    print(story_selector(stories))
    return 0


def score_t_power(df):
    if df >= 60:
        return 0.842
    return T_POWER_80[max(value for value in T_POWER_80 if value <= df)]


def recompute_score_statistics(block_details):
    diffs = []
    for index, block in enumerate(block_details, 1):
        a_scores = block.get("a_scores")
        b_scores = block.get("b_scores")
        if (
            not isinstance(a_scores, list) or len(a_scores) != 2
            or not isinstance(b_scores, list) or len(b_scores) != 2
        ):
            raise CampaignError(f"Checkpoint block {index} must have two scores per arm")
        a_values = [require_finite_number(value, f"block {index} arm A")
                    for value in a_scores]
        b_values = [require_finite_number(value, f"block {index} arm B")
                    for value in b_scores]
        if any(value <= 0 for value in a_values + b_values):
            raise CampaignError(f"Checkpoint block {index} scores must be positive")
        a_logs = [math.log(value) for value in a_values]
        b_logs = [math.log(value) for value in b_values]
        diffs.append(sum(b_logs) / 2 - sum(a_logs) / 2)
    count = len(diffs)
    if count < MIN_SCORE_BLOCKS:
        raise CampaignError("Checkpoint has too few complete raw blocks")
    mean = sum(diffs) / count
    variance = sum((value - mean) ** 2 for value in diffs) / (count - 1)
    std_err = math.sqrt(variance) / math.sqrt(count)
    df = count - 1
    if df >= 60:
        critical = 1.960
    else:
        critical = mechanism_contract.T_CRIT_95[
            max(value for value in mechanism_contract.T_CRIT_95 if value <= df)
        ]

    def pct(value):
        return math.expm1(value) * 100

    return {
        "geometric_delta_pct": pct(mean),
        "ci_95_pct": [pct(mean - critical * std_err), pct(mean + critical * std_err)],
        "significance_threshold_pct": pct(critical * std_err),
        "mde_80_power_pct": pct((critical + score_t_power(df)) * std_err),
        "is_stat_sig": (
            mean - critical * std_err > 0 or mean + critical * std_err < 0
        ),
    }


def recompute_targeted_story_statistics(
    block_details, targeted_stories, *, adapter,
):
    """Recompute the geomean delta over the targeted-story silos.

    Story values are per-repetition total times (lower is better); each
    block's observation is the equally weighted mean over targeted stories of
    mean(ln A_time) - mean(ln B_time), so positive means the flag arm is
    faster on the targeted stories. Landed work is expected to move exactly
    these stories, so this is the high-SNR landing gate; the full-suite delta
    remains the aggregate campaign claim.
    """
    diffs = []
    for index, block in enumerate(block_details, 1):
        story_diffs = []
        for story in targeted_stories:
            a_vals = [rep[story] for rep in block.get("a_stories", [])
                      if story in rep]
            b_vals = [rep[story] for rep in block.get("b_stories", [])
                      if story in rep]
            if not a_vals or not b_vals:
                available = sorted({
                    key
                    for arm in ("a_stories", "b_stories")
                    for rep in block.get(arm, [])
                    for key in rep
                })
                raise CampaignError(
                    f"Checkpoint block {index} has no measurements for "
                    f"targeted story {story!r}; available stories: "
                    + ", ".join(available[:40])
                )
            mean_ln_a = statistics.fmean(math.log(value) for value in a_vals)
            mean_ln_b = statistics.fmean(math.log(value) for value in b_vals)
            if adapter.workload_value_direction == "lower":
                story_diffs.append(mean_ln_a - mean_ln_b)
            else:
                story_diffs.append(mean_ln_b - mean_ln_a)
        diffs.append(statistics.fmean(story_diffs))
    count = len(diffs)
    if count < MIN_SCORE_BLOCKS:
        raise CampaignError("Checkpoint has too few complete raw blocks")
    mean = statistics.fmean(diffs)
    variance = sum((value - mean) ** 2 for value in diffs) / (count - 1)
    std_err = math.sqrt(variance) / math.sqrt(count)
    df = count - 1
    if df >= 60:
        critical = 1.960
    else:
        critical = mechanism_contract.T_CRIT_95[
            max(value for value in mechanism_contract.T_CRIT_95 if value <= df)
        ]

    def pct(value):
        return math.expm1(value) * 100

    return {
        "targeted_stories": list(targeted_stories),
        "targeted_delta_pct": pct(mean),
        "targeted_ci_95_pct": [
            pct(mean - critical * std_err), pct(mean + critical * std_err)
        ],
        "targeted_mde_80_power_pct": pct(
            (critical + score_t_power(df)) * std_err
        ),
    }


def validate_score_result_artifact(result, *, manifest_dir, evidence_dir,
                                   expected_arm, expected_block, expected_score,
                                   run_start, run_finish, adapter):
    if not isinstance(result, dict):
        raise CampaignError("Checkpoint result artifact is malformed")
    relative = result.get("path")
    if (
        not isinstance(relative, str)
        or pathlib.PurePosixPath(relative).is_absolute()
        or ".." in pathlib.PurePosixPath(relative).parts
    ):
        raise CampaignError("Checkpoint result artifact path is unsafe")
    path = (manifest_dir / relative).resolve()
    try:
        path.relative_to((manifest_dir / evidence_dir).resolve())
    except ValueError as exc:
        raise CampaignError("Checkpoint result artifact escaped evidence_dir") from exc
    if sha256_file(path) != result.get("sha256"):
        raise CampaignError(f"Checkpoint result digest changed: {path}")
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"Cannot parse raw checkpoint result {path}: {exc}") from exc
    parsed = adapter.parse_result(raw)
    if parsed is None:
        raise CampaignError(
            f"Raw checkpoint result has no scalar {adapter.crossbench_name} "
            f"score: {path}"
        )
    score = parsed.score
    result_score = require_finite_number(result.get("score"), "result score")
    expected_score = require_finite_number(expected_score, "expected result score")
    if (
        float(score) != expected_score
        or result_score != expected_score
        or result.get("arm") != expected_arm
        or result.get("block") != expected_block
    ):
        raise CampaignError("Checkpoint result metadata disagrees with its raw Score")
    start = result.get("started_monotonic_raw_ns")
    finish = result.get("finished_monotonic_raw_ns")
    if (
        isinstance(start, bool) or not isinstance(start, int)
        or isinstance(finish, bool) or not isinstance(finish, int)
        or not run_start <= start < finish <= run_finish
    ):
        raise CampaignError("Checkpoint repetition has invalid monotonic bounds")
    return start, finish, result.get("position"), parsed.workloads


def validate_and_recompute_checkpoint(manifest, manifest_path, config=None):
    if (
        manifest.get("schema_version") != SCORE_MANIFEST_SCHEMA_VERSION
        or manifest.get("runner") != SCORE_MANIFEST_RUNNER
    ):
        raise CampaignError("Checkpoint must be a runner-owned v4 manifest")
    try:
        adapter = benchmark_adapters.get_adapter(
            manifest.get("benchmark")
        )
    except ValueError as exc:
        raise CampaignError(str(exc)) from exc
    if manifest.get("metric_model") != adapter.metric_model:
        raise CampaignError("Checkpoint metric model does not match its benchmark")
    if manifest.get("workload_value_direction") != adapter.workload_value_direction:
        raise CampaignError("Checkpoint workload direction is inconsistent")
    provenance = manifest.get("payload_provenance")
    if not isinstance(provenance, dict):
        raise CampaignError("Checkpoint lacks benchmark payload provenance")
    if provenance.get("benchmark_id") != adapter.benchmark_id:
        raise CampaignError("Checkpoint payload provenance benchmark differs")
    if provenance.get("investigation_only") is True:
        raise CampaignError(
            "Investigation-only benchmark payload cannot support a checkpoint"
        )
    if provenance.get("content_pinned") is not True:
        raise CampaignError(
            "Checkpoint benchmark payload is not immutable/digest-bound"
        )
    if manifest.get("mode") != "ab" or not isinstance(
        manifest.get("stories"), str
    ) or not manifest["stories"]:
        raise CampaignError("Checkpoint v4 manifest is not a feature A/B")
    block_count = manifest.get("blocks")
    if (
        isinstance(block_count, bool) or not isinstance(block_count, int)
        or block_count < MIN_SCORE_BLOCKS or block_count % 2
    ):
        raise CampaignError("Checkpoint v4 manifest has an invalid block count")
    blocks = manifest.get("block_details")
    if not isinstance(blocks, list) or len(blocks) != manifest.get("blocks"):
        raise CampaignError("Checkpoint raw block inventory is incomplete")
    schedule = manifest.get("schedule")
    if not isinstance(schedule, list) or len(schedule) != len(blocks):
        raise CampaignError("Checkpoint raw schedule is incomplete")
    if (
        schedule.count("ABBA") != block_count // 2
        or schedule.count("BAAB") != block_count // 2
        or any(value not in ("ABBA", "BAAB") for value in schedule)
    ):
        raise CampaignError("Checkpoint raw schedule is not exactly balanced")
    evidence_dir = manifest.get("evidence_dir")
    if (
        not isinstance(evidence_dir, str)
        or pathlib.PurePath(evidence_dir).name != evidence_dir
        or not re.fullmatch(r"ab_evidence_[0-9a-f]{24}", evidence_dir)
    ):
        raise CampaignError("Checkpoint evidence_dir is invalid")
    environment = manifest.get("capture_environment")
    if not isinstance(environment, dict) or environment.get("virtualization") != "none":
        raise CampaignError("Checkpoint was not captured on an attested bare-metal host")
    for field in ("host_name", "host_boot_id", "kernel_release", "cpu_model"):
        if not isinstance(environment.get(field), str) or not environment[field]:
            raise CampaignError(f"Checkpoint capture lacks {field}")
    if config is not None:
        require_campaign_display(config, environment.get("display"), "Checkpoint")
    harness = manifest.get("harness")
    if not isinstance(harness, dict):
        raise CampaignError("Checkpoint lacks harness identity")
    for field in ("crossbench_revision", "depot_tools_revision", "depot_tools_origin"):
        if not isinstance(harness.get(field), str) or not harness[field]:
            raise CampaignError(f"Checkpoint harness lacks {field}")
    for field in ("crossbench_cb", "vpython3"):
        ref = harness.get(field)
        if (
            not isinstance(ref, dict)
            or not re.fullmatch(r"[0-9a-f]{64}", str(ref.get("sha256", "")))
        ):
            raise CampaignError(f"Checkpoint harness lacks a digest-bound {field}")
    run_start = manifest.get("started_monotonic_raw_ns")
    run_finish = manifest.get("finished_monotonic_raw_ns")
    minimum = manifest.get("minimum_duration_ns")
    expected_minimum = (
        manifest.get("blocks", 0) * 4 * MIN_FULL_SUITE_REP_SECONDS * 1_000_000_000
        if manifest.get("stories") == "all" or (
            adapter.benchmark_id == "speedometer3"
            and manifest.get("stories") == adapter.default_workload_selector
        ) else 0
    )
    if (
        isinstance(run_start, bool) or not isinstance(run_start, int)
        or isinstance(run_finish, bool) or not isinstance(run_finish, int)
        or run_start <= 0 or run_finish <= run_start
        or minimum != expected_minimum
        or run_finish - run_start < expected_minimum
    ):
        raise CampaignError("Checkpoint duration attestation is implausible")
    chronological = []
    observed_workload_sets = []
    for index, block in enumerate(blocks, 1):
        if (
            not isinstance(block, dict)
            or block.get("block") != index
            or block.get("pattern") != schedule[index - 1]
        ):
            raise CampaignError(f"Checkpoint block {index} does not match its schedule")
        by_position = {}
        for arm in ("a", "b"):
            results = block.get(f"{arm}_results")
            scores = block.get(f"{arm}_scores")
            recorded_stories = block.get(f"{arm}_stories")
            if (
                not isinstance(results, list) or len(results) != 2
                or not isinstance(scores, list) or len(scores) != 2
            ):
                raise CampaignError(f"Checkpoint block {index} lacks raw arm {arm} results")
            if (
                not isinstance(recorded_stories, list)
                or len(recorded_stories) != 2
                or any(not isinstance(item, dict) for item in recorded_stories)
            ):
                raise CampaignError(
                    f"Checkpoint block {index} lacks raw arm {arm} per-story totals"
                )
            for result, score, rep_stories in zip(
                results, scores, recorded_stories
            ):
                start, finish, position, raw_stories = (
                    validate_score_result_artifact(
                        result,
                        manifest_dir=manifest_path.parent,
                        evidence_dir=evidence_dir,
                        expected_arm=arm,
                        expected_block=index,
                        expected_score=score,
                        run_start=run_start,
                        run_finish=run_finish,
                        adapter=adapter,
                    )
                )
                if {
                    key: float(value) for key, value in rep_stories.items()
                } != raw_stories:
                    raise CampaignError(
                        f"Checkpoint block {index} arm {arm} per-story totals "
                        "disagree with the raw result artifact"
                    )
                observed_workload_sets.append(set(raw_stories))
                selected_stories = (
                    None if manifest["stories"] in (
                        "all", adapter.default_workload_selector
                    ) else parse_story_selector(manifest["stories"])
                )
                if selected_stories is not None and set(raw_stories) != set(
                    selected_stories
                ):
                    raise CampaignError(
                        f"Checkpoint block {index} arm {arm} measured stories "
                        "do not match its preregistered selector"
                    )
                if position in by_position:
                    raise CampaignError(f"Checkpoint block {index} repeats a position")
                by_position[position] = (arm.upper(), start, finish)
        if sorted(by_position) != [1, 2, 3, 4]:
            raise CampaignError(f"Checkpoint block {index} positions are incomplete")
        actual_pattern = "".join(by_position[position][0] for position in range(1, 5))
        if actual_pattern != block["pattern"]:
            raise CampaignError(f"Checkpoint block {index} arm order is fabricated")
        chronological.extend(by_position[position][1:] for position in range(1, 5))
    if observed_workload_sets and any(
        workloads != observed_workload_sets[0]
        for workloads in observed_workload_sets[1:]
    ):
        raise CampaignError("Checkpoint workload set changed between repetitions")
    observed = manifest.get("observed_workloads")
    if observed != sorted(observed_workload_sets[0] if observed_workload_sets else ()):
        raise CampaignError("Checkpoint observed_workloads inventory is incorrect")
    expected_count = adapter.expected_workload_count(manifest["stories"])
    if manifest.get("expected_workload_count") != expected_count:
        raise CampaignError("Checkpoint expected workload count is incorrect")
    if expected_count is not None and len(observed) != expected_count:
        raise CampaignError("Checkpoint full workload inventory is incomplete")
    for previous, current in zip(chronological, chronological[1:]):
        if current[0] < previous[1]:
            raise CampaignError("Checkpoint repetition monotonic ranges overlap")
    computed = recompute_score_statistics(blocks)
    for field, value in computed.items():
        recorded = manifest.get(field)
        if isinstance(value, list):
            if not isinstance(recorded, list) or len(recorded) != len(value):
                raise CampaignError(f"Checkpoint manifest lacks computed {field}")
            matches = all(abs(float(left) - right) <= 1e-12
                          for left, right in zip(recorded, value))
        elif isinstance(value, bool):
            matches = recorded is value
        else:
            matches = abs(float(recorded) - value) <= 1e-12
        if not matches:
            raise CampaignError(f"Checkpoint {field} does not match raw recomputation")
    return computed


def current_skill_tree_digest(repo_root):
    try:
        import remote_measure
        return remote_measure.skills_digest(pathlib.Path(repo_root))
    except (OSError, RuntimeError, SystemExit) as exc:
        raise CampaignError(f"Cannot compute current skill-tree digest: {exc}") from exc


def require_clean_skill_repository(script_path=None):
    """Refuse copied, untracked, or locally modified enforcement code."""
    script = pathlib.Path(script_path or __file__).resolve()
    try:
        skill_repo = subprocess.run(
            ["git", "-C", str(script.parent), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        skill_repo_path = pathlib.Path(skill_repo).resolve()
        expected_script = (
            skill_repo_path / "optimize-campaign" / "scripts" / "campaign.py"
        ).resolve()
        required_markers = (
            "optimize-campaign/SKILL.md",
            "optimize-campaign/scripts/benchmark_adapters.py",
            "optimize-campaign/scripts/campaign.py",
            "optimize-speedometer/SKILL.md",
            "optimize-jetstream/SKILL.md",
            "chrome-cycle-profiling/SKILL.md",
        )
        if script != expected_script or any(
            not (skill_repo_path / marker).is_file() for marker in required_markers
        ):
            raise CampaignError(
                "campaign.py is not executing from the shared campaign bundle "
                "in a standalone skills Git checkout; copied or Chromium-"
                "gitignored skill directories are not trusted"
            )
        for marker in required_markers:
            subprocess.run(
                ["git", "-C", skill_repo, "ls-files", "--error-unmatch", marker],
                check=True, capture_output=True, text=True,
            )
        status = subprocess.run(
            [
                "git", "-C", skill_repo, "status", "--porcelain", "--",
                "optimize-campaign", "optimize-speedometer",
                "optimize-jetstream", "chrome-cycle-profiling",
            ],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except CampaignError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise CampaignError(f"Cannot verify the skill repository: {exc}") from exc
    if status:
        raise CampaignError(
            "The optimization skill repository has uncommitted changes. "
            "A human must review and commit the skill tooling before campaign init."
        )
    return skill_repo


def cmd_checkpoint(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    adapter = benchmark_adapters.get_adapter(
        ledger.data["config"]["benchmark"]
    )
    decision = None
    checkpoint_challenges = []
    kind = args.kind
    target_stories = landed_target_stories(ledger)
    if kind == "targeted" and not target_stories:
        raise CampaignError(
            "A targeted checkpoint requires at least one landed opportunity "
            "with a target_story"
        )
    expected_stories = (
        story_selector(target_stories)
        if kind == "targeted" and test_bypass_active() else adapter.default_workload_selector
    )
    if args.summary:
        path = pathlib.Path(args.summary)
        try:
            summary = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignError(f"Cannot read checkpoint summary {path}: {exc}") from exc
        if (
            summary.get("schema_version") != SCORE_MANIFEST_SCHEMA_VERSION
            or summary.get("runner") != SCORE_MANIFEST_RUNNER
        ):
            raise CampaignError("Checkpoint summary is not from the v4 score runner")
        if summary.get("mode") != "ab":
            raise CampaignError("Checkpoint must be a cumulative feature A/B")
        if kind == "targeted" and test_bypass_active():
            measured_stories = parse_story_selector(summary.get("stories"))
            if measured_stories != target_stories:
                raise CampaignError(
                    "Targeted checkpoint story selector does not match the "
                    "current landed target-story set; expected "
                    f"{expected_stories!r}"
                )
        elif summary.get("stories") != adapter.default_workload_selector:
            raise CampaignError(
                "Full-suite checkpoint must use --stories "
                f"{adapter.default_workload_selector}"
            )
        if summary.get("benchmark") != adapter.benchmark_id:
            raise CampaignError("Checkpoint used the wrong benchmark adapter")
        if summary.get("metric_model") != adapter.metric_model:
            raise CampaignError("Checkpoint used the wrong benchmark metric model")
        payload = summary.get("payload_provenance")
        if not isinstance(payload, dict) or payload.get("source") != (
            ledger.data["config"]["benchmark_source"]
        ):
            raise CampaignError(
                "Checkpoint used the wrong benchmark payload source"
            )
        if summary.get("feature") != ledger.data["config"]["feature"]:
            raise CampaignError("Checkpoint toggled the wrong feature")
        if (
            not isinstance(summary.get("blocks"), int)
            or summary["blocks"] < MIN_SCORE_BLOCKS
            or summary["blocks"] % 2
        ):
            raise CampaignError(
                f"Checkpoint requires at least {MIN_SCORE_BLOCKS} complete blocks "
                "and an even count for exact ABBA/BAAB balance"
            )
        if not isinstance(summary.get("seed"), int):
            raise CampaignError("Checkpoint summary must record the randomized seed")
        schedule = summary.get("schedule")
        if not isinstance(schedule, list) or len(schedule) != summary["blocks"]:
            raise CampaignError("Checkpoint summary must record the complete block schedule")
        if (
            any(pattern not in ("ABBA", "BAAB") for pattern in schedule)
            or schedule.count("ABBA") != summary["blocks"] // 2
            or schedule.count("BAAB") != summary["blocks"] // 2
        ):
            raise CampaignError(
                "Checkpoint requires exactly half ABBA and half BAAB blocks"
            )
        provenance = summary.get("build_provenance")
        if not isinstance(provenance, dict) or not all(
            isinstance(provenance.get(arm), dict) for arm in ("a", "b")
        ):
            raise CampaignError("Checkpoint lacks per-arm build provenance")
        for arm in ("a", "b"):
            arm_provenance = provenance[arm]
            browser = arm_provenance.get("resolved_browser", "")
            if (
                arm_provenance.get("build_role") != "release"
                or not browser.endswith("/out/release/chrome")
                or arm_provenance.get("symbol_level") != "0"
            ):
                raise CampaignError(
                    "Authoritative checkpoints must use symbol-free "
                    "out/release/chrome on both arms"
                )
        repo_root = find_repo_root(pathlib.Path.cwd())
        verify_profile_head(
            repo_root, summary.get("sha"),
            ledger.data["config"].get("branch"), allow_unverified=False,
        )
        if any(
            provenance[arm].get("git_sha") != summary.get("sha")
            for arm in ("a", "b")
        ):
            raise CampaignError("Checkpoint build provenance SHA does not match measured SHA")
        manifest_path = pathlib.Path(summary.get("manifest", ""))
        try:
            manifest_data = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise CampaignError(f"Cannot read checkpoint raw manifest: {exc}") from exc
        for field in (
            "schema_version", "runner",
            "benchmark", "metric_model", "workload_value_direction",
            "payload_provenance",
            "observed_workloads", "expected_workload_count",
            "mode", "feature", "stories", "blocks", "seed", "schedule",
            "geometric_delta_pct", "ci_95_pct", "mde_80_power_pct",
            "significance_threshold_pct", "is_stat_sig", "build_provenance",
            "started_at", "finished_at", "started_monotonic_raw_ns",
            "finished_monotonic_raw_ns", "minimum_duration_ns",
            "capture_environment", "harness", "skill_tree_sha256",
            "evidence_dir",
        ):
            if manifest_data.get(field) != summary.get(field):
                raise CampaignError(f"Checkpoint summary disagrees with manifest on {field}")
        if (
            manifest_data.get("skill_tree_sha256")
            != ledger.data["config"].get("skill_tree_sha256")
            or manifest_data.get("skill_tree_sha256")
            != current_skill_tree_digest(repo_root)
        ):
            raise CampaignError(
                "Checkpoint was produced by a different skill tree; sync/commit "
                "tooling and rerun the measurement"
            )
        computed = validate_and_recompute_checkpoint(manifest_data, manifest_path, ledger.data["config"])
        import statistics_policy
        try:
            plan = fixed_plan(
                ledger.data["config"],
                target_stories if kind == "targeted" else "suite",
                manifest_data.get("blocks"),
            )
            decision = statistics_policy.evaluate(manifest_data, plan)
        except ValueError as exc:
            raise CampaignError(f"checkpoint fixed-plan decision failed: {exc}") from exc
        delta = computed["geometric_delta_pct"]
        ci = computed["ci_95_pct"]
        if not isinstance(ci, list) or len(ci) != 2:
            raise CampaignError("Checkpoint summary lacks ci_95_pct")
        ci_low = require_finite_number(ci[0], "CI lower")
        ci_high = require_finite_number(ci[1], "CI upper")
        if ci_low > ci_high:
            raise CampaignError("Checkpoint CI bounds are reversed")
        manifest = summary.get("manifest")
        manifest_sha256 = sha256_file(manifest_path)
        sha = summary.get("sha")
        evidence_sha256 = sha256_file(path)
        seed = summary.get("seed")
        mde = computed["mde_80_power_pct"]
        blocks = summary.get("blocks")
        checkpoint_challenges = validate_gate_challenges(
            args,
            gate="checkpoint",
            artifact_digests=[evidence_sha256, manifest_sha256],
        )
    elif test_bypass_active():
        delta, ci_low, ci_high = args.delta, args.ci_low, args.ci_high
        manifest, sha = args.manifest, args.sha
        evidence_sha256, seed, mde, manifest_sha256 = None, None, None, None
        blocks = None
    else:
        raise CampaignError(
            "checkpoint requires --summary from remote_measure.py; manual deltas are rejected"
        )
    if not test_bypass_active():
        enforce_checkpoint_attempt_policy(
            ledger,
            kind=kind,
            sha=sha,
            landed_count=len(ledger.landed()),
            blocks=blocks,
        )
    if decision is not None:
        primary = decision["primary"]
        delta, (ci_low, ci_high), mde = primary["delta_pct"], primary["ci_pct"], primary["mde_80_pct"]
    ledger.data.setdefault("checkpoints", []).append(
        {
            "plan": plan if decision else None,
            "verdict": decision["verdict"] if decision else "test-only",
            "regressions": decision["regressions"] if decision else [],
            "unresolved_regression_bounds": decision["unresolved_regression_bounds"] if decision else [],
            "ts": utc_now(),
            "type": kind,
            "landed_count": len(ledger.landed()),
            "delta_pct": delta,
            "ci": [ci_low, ci_high],
            "stories": expected_stories,
            "targeted_stories": target_stories if kind == "targeted" else None,
            "manifest": manifest,
            "manifest_sha256": manifest_sha256,
            "sha": sha,
            "summary": args.summary,
            "summary_sha256": evidence_sha256,
            "seed": seed,
            "blocks": blocks,
            "mde_80_power_pct": mde,
            "notes": args.notes,
        }
    )
    record_gate_challenges(
        ledger,
        gate="checkpoint",
        subject=f"{kind}-landed-{len(ledger.landed())}",
        reports=checkpoint_challenges,
    )
    pilot = ledger.data.get("pilot", {})
    landed_count = len(ledger.landed())
    if (
        not test_bypass_active()
        and pilot.get("required", True)
        and pilot.get("status") == "pending"
        and PILOT_MIN_LANDINGS <= landed_count <= PILOT_MAX_LANDINGS
    ):
        saved = sum(
            float(opp.get("verification_evidence", {}).get(
                "mechanism_scored_cycle_share_saved_pct", 0.0
            ))
            for opp in ledger.landed()
        )
        update_pilot_from_split_checkpoints(ledger, saved=saved)
    ledger.save()
    message = (
        f"Recorded {kind} checkpoint after {len(ledger.landed())} landed: "
        f"{delta:+.2f}%"
    )
    if kind == "targeted":
        message += f" on {', '.join(target_stories)}"
    print(message)
    return 0


def update_pilot_from_split_checkpoints(ledger, *, saved):
    """Require targeted efficacy and a same-tip full-suite regression guard."""
    pilot = ledger.data.get("pilot", {})
    landed_count = len(ledger.landed())
    targeted = latest_checkpoint(ledger, "targeted")
    full = latest_checkpoint(ledger, "full-suite")
    if not targeted or not full:
        pilot.update({
            "status": "pending",
            "reason": (
                "pilot requires both targeted and full-suite checkpoints at "
                f"the current {landed_count}-landing tip"
            ),
        })
        return
    if (
        targeted.get("landed_count") != landed_count
        or full.get("landed_count") != landed_count
    ):
        pilot.update({
            "status": "pending",
            "reason": (
                "pilot checkpoints are stale; record targeted and full-suite "
                f"measurements after {landed_count} landings"
            ),
        })
        return
    if not test_bypass_active():
        verdicts = [targeted.get("verdict"),full.get("verdict")]
        pilot.update({"status": "passed" if all(v == "IMPROVEMENT" for v in verdicts) else
                      "failed" if "REGRESSION" in verdicts else "pending",
                      "reason": "fixed-plan targeted/full-suite outcomes: " + str(verdicts),"ts":utc_now()})
        return
    target_low, target_high = targeted["ci"]
    full_low, full_high = full["ci"]
    common = {
        "targeted_checkpoint_sha256": targeted.get("summary_sha256"),
        "full_suite_checkpoint_sha256": full.get("summary_sha256"),
        "ts": utc_now(),
    }
    if saved > 0 and target_low > 0 and full_high > 0:
        pilot.update({
            **common,
            "status": "passed",
            "reason": (
                f"mechanistic direction +{saved:.4f}%, targeted CI "
                f"[{target_low:+.4f}%, {target_high:+.4f}%] is positive, "
                f"and full-suite CI [{full_low:+.4f}%, {full_high:+.4f}%] "
                f"shows no stat-sig regression after {landed_count} candidates"
            ),
        })
    elif saved <= 0 or target_high <= 0 or full_high <= 0:
        pilot.update({
            **common,
            "status": "failed",
            "reason": (
                "pilot contradicted the mechanistic evidence: "
                f"mechanistic {saved:+.4f}%, targeted CI "
                f"[{target_low:+.4f}%, {target_high:+.4f}%], full-suite CI "
                f"[{full_low:+.4f}%, {full_high:+.4f}%]"
            ),
        })
    else:
        pilot.update({
            **common,
            "status": "pending",
            "reason": (
                f"targeted checkpoint remains inconclusive "
                f"[{target_low:+.4f}%, {target_high:+.4f}%]; choose one "
                "larger preregistered balanced run from the measured MDE"
            ),
        })


def update_pilot_from_checkpoint(
    pilot, *, landed_count, saved, delta, ci_low, ci_high, evidence_sha256,
    targeted=None,
):
    """Judge the pilot on the targeted-story silos, guarded by the suite.

    Landed candidates are sized per story, so the positive-effect proof reads
    the targeted-story CI from the cumulative A/B (high SNR); a stat-sig
    full-suite regression still fails the pilot regardless.
    """
    common = {"checkpoint_sha256": evidence_sha256, "ts": utc_now()}
    if targeted:
        gate_ci_low, gate_ci_high = targeted["targeted_ci_95_pct"]
        gate_delta = targeted["targeted_delta_pct"]
        gate_label = (
            "targeted-story A/B ("
            + ", ".join(targeted["targeted_stories"]) + ")"
        )
    else:
        gate_ci_low, gate_ci_high = ci_low, ci_high
        gate_delta = delta
        gate_label = "cumulative full-suite A/B"
    suite_regressed = ci_high <= 0
    if saved > 0 and gate_ci_low > 0 and not suite_regressed:
        pilot.update({
            **common,
            "status": "passed",
            "reason": (
                f"mechanistic direction +{saved:.4f}% and {gate_label} CI "
                f"[{gate_ci_low:+.4f}%, {gate_ci_high:+.4f}%] is positive "
                f"after {landed_count} candidates (full-suite "
                f"{delta:+.4f}% [{ci_low:+.4f}%, {ci_high:+.4f}%])"
            ),
        })
    elif saved <= 0 or gate_ci_high <= 0 or suite_regressed:
        pilot.update({
            **common,
            "status": "failed",
            "reason": (
                f"pilot contradicted the mechanistic evidence (mechanistic "
                f"{saved:+.4f}%, {gate_label} {gate_delta:+.4f}% with CI "
                f"[{gate_ci_low:+.4f}%, {gate_ci_high:+.4f}%], full-suite "
                f"{delta:+.4f}% [{ci_low:+.4f}%, {ci_high:+.4f}%]); stop and "
                "repair the pipeline"
            ),
        })
    else:
        pilot.update({
            **common,
            "status": "pending",
            "reason": (
                f"pilot is inconclusive: {gate_label} {gate_delta:+.4f}% with "
                f"CI [{gate_ci_low:+.4f}%, {gate_ci_high:+.4f}%] does not "
                "prove a positive effect; land no more than five pilot "
                "candidates, then increase balanced block count and remeasure"
            ),
        })


def cmd_status(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    ledger.write_status()
    ledger._commit_snapshot("STATUS refresh")
    status_path = ledger.dir / "STATUS.md"
    print(status_path)
    if args.print:
        with open(status_path) as f:
            print(f.read())
    return 0


def cmd_audit(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    problems = []
    repo_root = find_repo_root(pathlib.Path.cwd())
    try:
        require_clean_skill_repository()
        current_digest = current_skill_tree_digest(repo_root)
        if current_digest != ledger.data.get("config", {}).get("skill_tree_sha256"):
            problems.append("current skill tree differs from campaign initialization")
    except CampaignError as exc:
        problems.append(str(exc))
    for profile in ledger.data.get("profile_runs", []):
        for path_field, digest_field in (
            ("areas_manifest", "areas_manifest_sha256"),
            ("capture_summaries", "capture_summaries_sha256"),
        ):
            path = profile.get(path_field)
            expected = profile.get(digest_field)
            if not path or not expected:
                problems.append(f"profile {profile['id']} lacks {digest_field}")
                continue
            try:
                if sha256_file(path) != expected:
                    problems.append(f"profile {profile['id']} changed {path_field}")
            except CampaignError as exc:
                problems.append(str(exc))
        for capture in profile.get("capture_provenance", []):
            try:
                if sha256_file(capture.get("artifact")) != capture.get("artifact_sha256"):
                    problems.append(
                        f"profile {profile['id']} capture {capture.get('capture_id')} changed"
                    )
            except CampaignError as exc:
                problems.append(str(exc))
    if not test_bypass_active():
        for admitted in ledger.landed():
            try:
                evidence = admitted.get("performance_receipts") or {}
                receipts = list(evidence.get("local", [])) + list(evidence.get("fleet", []))
                if not receipts:
                    raise ValueError("no performance receipts recorded")
                for receipt in receipts:
                    if sha256_file(receipt["path"]) != receipt["sha256"]:
                        raise ValueError(f"performance receipt changed: {receipt['path']}")
                mapping = admitted.get("integration_mapping") or {}
                if integration_mapping(repo_root, mapping.get("isolated_candidate_sha"),
                                       admitted["commit"], ledger.data["config"]["baseline_sha"]) != mapping:
                    raise ValueError("integration mapping changed")
            except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError) as exc:
                problems.append(f"opportunity {admitted['id']} performance evidence: {exc}")
        for checkpoint in ledger.data.get("checkpoints", []):
            try:
                if checkpoint.get("manifest_sha256") and sha256_file(checkpoint["manifest"]) != checkpoint["manifest_sha256"]:
                    raise ValueError("checkpoint manifest changed")
            except (OSError, KeyError, TypeError, ValueError) as exc:
                problems.append(f"checkpoint evidence: {exc}")
    for opp in ledger.data.get("opportunities", []):
        for phase, path_field in (
            ("sizing", "evidence"),
            ("candidate", "verification_evidence_path"),
        ):
            path = opp.get(path_field)
            if not isinstance(path, str):
                continue
            try:
                evidence, _ = load_gate_evidence(
                    path, opp=opp, phase=phase,
                    benchmark=ledger.data["config"]["benchmark"],
                    metric_model=ledger.data["config"]["metric_model"],
                )
                if (
                    evidence.get("build", {}).get("skill_tree_sha256")
                    != ledger.data["config"].get("skill_tree_sha256")
                ):
                    problems.append(
                        f"opportunity {opp['id']} {phase}: skill-tree digest differs"
                    )
            except CampaignError as exc:
                problems.append(f"opportunity {opp['id']} {phase}: {exc}")
        for kind in ("build", "test"):
            path = opp.get(f"{kind}_receipt_path")
            if not path:
                continue
            try:
                _, digest_value = load_command_receipt(
                    path, kind=kind, source_tree=opp.get("review_tree"),
                    expected_skill_tree=ledger.data["config"].get(
                        "skill_tree_sha256"
                    ),
                )
                if digest_value != opp.get(f"{kind}_receipt_sha256"):
                    problems.append(f"opportunity {opp['id']} {kind} receipt changed")
            except CampaignError as exc:
                problems.append(f"opportunity {opp['id']} {kind}: {exc}")
        for role, review in opp.get("reviews", {}).items():
            path = review.get("report")
            if not path or review.get("report_sha256") is None:
                continue
            try:
                _, digest_value = load_review_report(
                    path, opp=opp, role=role, verdict=review.get("verdict"),
                    campaign_dir=ledger.dir,
                )
                if digest_value != review.get("report_sha256"):
                    problems.append(f"opportunity {opp['id']} {role} report changed")
            except CampaignError as exc:
                problems.append(f"opportunity {opp['id']} {role}: {exc}")
    for index, checkpoint in enumerate(ledger.data.get("checkpoints", []), 1):
        try:
            adapter = benchmark_adapters.get_adapter(
                ledger.data["config"]["benchmark"]
            )
            summary_path = pathlib.Path(checkpoint["summary"])
            manifest_path = pathlib.Path(checkpoint["manifest"])
            if sha256_file(summary_path) != checkpoint.get("summary_sha256"):
                raise CampaignError("summary digest changed")
            if sha256_file(manifest_path) != checkpoint.get("manifest_sha256"):
                raise CampaignError("manifest digest changed")
            manifest = json.loads(manifest_path.read_text())
            validate_and_recompute_checkpoint(manifest, manifest_path, ledger.data["config"])
            if checkpoint.get("stories", manifest.get("stories")) != manifest.get(
                "stories"
            ):
                raise CampaignError("checkpoint story selector changed")
            if checkpoint.get("blocks", manifest.get("blocks")) != manifest.get(
                "blocks"
            ):
                raise CampaignError("checkpoint block count changed")
            recorded_type = checkpoint_type(checkpoint)
            if recorded_type == "targeted" and manifest.get(
                "stories"
            ) == adapter.default_workload_selector:
                raise CampaignError("targeted checkpoint contains a full-suite manifest")
            if recorded_type == "full-suite" and manifest.get(
                "stories"
            ) != adapter.default_workload_selector:
                raise CampaignError("full-suite checkpoint contains a targeted manifest")
            if (
                manifest.get("skill_tree_sha256")
                != ledger.data["config"].get("skill_tree_sha256")
            ):
                raise CampaignError("checkpoint skill-tree digest differs")
        except (CampaignError, OSError, json.JSONDecodeError, KeyError) as exc:
            problems.append(f"checkpoint {index}: {exc}")
    for challenge in ledger.data.get("gate_challenges", []):
        stored_reports = challenge.get("reports", [])
        by_role = {
            report.get("role"): report
            for report in stored_reports if isinstance(report, dict)
        }
        try:
            if set(by_role) != set(GATE_CHALLENGE_ROLES):
                raise CampaignError("gate challenge pair is incomplete")
            expected = {
                digest_value.removeprefix("sha256:")
                for report in stored_reports
                for digest_value in report.get("artifact_digests_checked", [])
                if isinstance(digest_value, str)
                and re.fullmatch(r"sha256:[0-9a-f]{64}", digest_value)
            }
            verified = validate_gate_challenges(
                argparse.Namespace(**{
                    f"gate_{role}": by_role[role]["path"]
                    for role in GATE_CHALLENGE_ROLES
                }),
                gate=challenge.get("gate"),
                artifact_digests=sorted(expected),
            )
            for report in verified:
                if report["sha256"] != by_role[report["role"]].get("sha256"):
                    raise CampaignError(
                        f"{challenge.get('gate')} {report['role']} challenge changed"
                    )
        except (CampaignError, KeyError, TypeError) as exc:
            problems.append(f"{challenge.get('gate')} challenge: {exc}")
    if problems:
        print("Campaign audit FAILED:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    history = "not-required"
    if (ledger.dir / ".git").is_dir():
        history = subprocess.run(
            ["git", "-C", str(ledger.dir), "rev-parse", "--short", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    print(
        f"Campaign audit passed: {len(ledger.data.get('opportunities', []))} "
        f"opportunities, {len(ledger.data.get('checkpoints', []))} checkpoints, "
        f"snapshot {history}"
    )
    return 0


def cmd_audit_exhaustion(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    blockers = ledger.exhaustion_blockers()
    if ledger.data.get("profile_runs"):
        blockers.extend(checkout_exhaustion_blockers(
            ledger,
            allow_unverified=args.allow_unverified_repository,
        ))
    if blockers:
        print("Campaign opportunity exhaustion is NOT established:")
        for blocker in blockers:
            print(f"- {blocker}")
        return 1
    latest = ledger.data["profile_runs"][-1]
    excluded = latest.get("excluded_areas", [])
    print(
        f"Campaign opportunity exhaustion established by profile "
        f"{latest['id']} and resolved ledger state "
        f"({len(excluded)} structured area exclusion(s))"
    )
    return 0


def cmd_show(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    if args.opp is not None:
        print(json.dumps(ledger.opp(args.opp), indent=2))
    elif args.area_key is not None:
        print(json.dumps([
            opp for opp in ledger.data["opportunities"]
            if opp.get("area_key") == args.area_key
            or opp.get("area_key", "").startswith(args.area_key + "/")
        ], indent=2))
    else:
        print(json.dumps(ledger.data, indent=2))
    return 0


def cmd_next(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    for o in ledger.next_candidates(args.count):
        priority, basis, measured = ledger.priority_info(o)
        print(
            f"#{o['id']:03d} {o['anchor']} "
            f"story={o.get('target_story') or '?'} priority={priority:.3f} "
            f"basis={basis} measured={measured:.3f}% "
            f"reported={o.get('share_pct', 0.0):.3f}%"
        )
    return 0


def add_gate_challenge_arguments(parser):
    parser.add_argument(
        "--gate-skeptic",
        help="PASS gate-challenge JSON from the independent skeptic task",
    )
    parser.add_argument(
        "--gate-adversary",
        help="PASS gate-challenge JSON from the independent adversary task",
    )


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dir",
        help="Campaign directory (default: $OPTIMIZE_CAMPAIGN_DIR or .agents/campaigns/current)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new campaign ledger")
    p.add_argument("--name", required=True)
    p.add_argument(
        "--benchmark", choices=benchmark_adapters.available_benchmarks(),
        default="speedometer3",
    )
    p.add_argument(
        "--execution", choices=("local", "ssh"), default="ssh",
        help="Where measurements run; both modes use the same on-host runners",
    )
    p.add_argument(
        "--benchmark-source", default=None,
        help="Payload source recorded in campaign provenance",
    )
    p.add_argument("--branch", default=None)
    p.add_argument("--target", type=int, default=20, help="Target landed count")
    p.add_argument(
        "--share-floor",
        type=float,
        default=1.0,
        help="Minimum target-story impact (%%) worth attempting before "
        "calibration raises it to twice the story's measured MDE",
    )
    p.add_argument("--feature", default=None)
    p.add_argument("--remote-host", default="linux")
    p.add_argument("--remote-src", default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--baseline", default="HEAD")
    p.add_argument(
        "--fleet-bot", default=DEFAULT_FLEET_BOT,
        help="Pinpoint bot whose IMPROVEMENT is required before landing",
    )
    p.add_argument(
        "--no-fleet-gate", action="store_true",
        help="Land on local evidence alone (not recommended; the Mac bot is the reference)",
    )
    p.add_argument(
        "--display", default="headless",
        help="Rendering surface for every profile, mechanism and score run: "
        "'headless' or an X display such as ':1' backed by the GPU",
    )
    p.add_argument(
        "--display-vt", type=int, default=None,
        help="Console VT owned by the benchmark X server (required with an X display)",
    )
    p.add_argument(
        "--viewport", default="1500x1000",
        help="Fixed Chrome window size for X display runs",
    )
    p.add_argument(
        "--gpu-clock-mhz", type=int, default=None,
        help="Lock the NVIDIA graphics clock at this MHz during measurement sessions",
    )
    p.add_argument(
        "--pause-service", action="append", default=[],
        help="systemd service the tuner stops for every measurement session "
        "and restarts afterwards (repeatable), e.g. ollama",
    )
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("profile", help="Record one reconciled follow-on profile frontier")
    p.add_argument("--id", required=True, help="Stable capture/group id")
    p.add_argument("--sha", required=True, help="Profiled campaign commit")
    p.add_argument(
        "--areas", required=True,
        help="Complete source-accounted profile reconciliation JSON object",
    )
    p.add_argument(
        "--capture-summaries", required=True,
        help="JSON array of at least two independent remote_measure summaries",
    )
    p.add_argument(
        "--enable-features", required=True,
        help="Comma-separated feature state used for every capture",
    )
    p.add_argument(
        "--allow-unverified-repository", action="store_true",
        help=argparse.SUPPRESS,
    )
    p.add_argument("--artifacts", default=None, help="Summary/artifact paths")
    p.add_argument("--notes", default=None)
    add_gate_challenge_arguments(p)
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser(
        "profile-scaffold",
        help=(
            "Prefill a reconciliation manifest from capture summaries; "
            "review dispositions, then feed it to `profile --areas`"
        ),
    )
    p.add_argument(
        "--capture-summaries", required=True,
        help="JSON array of remote_measure --summary-out objects",
    )
    p.add_argument("--out", required=True, help="Manifest output path")
    p.set_defaults(func=cmd_profile_scaffold)

    p = sub.add_parser(
        "decompose-scaffold",
        help=(
            "Prefill a decomposition skeleton (one path per profiler hotspot, "
            "primary accounting done); fill dispositions/evidence, then feed "
            "it to `decompose --children`"
        ),
    )
    p.add_argument("--opp", type=int, required=True, help="Discovery opportunity id")
    p.add_argument("--out", required=True, help="Skeleton output path")
    p.set_defaults(func=cmd_decompose_scaffold)

    p = sub.add_parser(
        "add",
        help="Add a concrete mechanism (discoveries come from `profile`)",
    )
    p.add_argument("--anchor", required=True, help="Anchor symbol/subtree description")
    p.add_argument(
        "--kind", choices=("discovery", "mechanism"), default=None,
        help="Explicit record type (omitting preserves the legacy mechanism CLI)",
    )
    p.add_argument("--area-key", default=None, help="Stable candidate-area identity")
    p.add_argument("--mechanism-key", default=None, help="Stable optimization-path identity")
    p.add_argument("--parent", type=int, default=None, help="Parent discovery/opportunity id")
    p.add_argument("--profile-id", default=None, help="Profile that observed this area/path")
    p.add_argument("--share", type=float, required=True, help="Marginal or overlap profile share (%%)")
    p.add_argument("--stories", default=None, help="Comma-separated stories where samples concentrate")
    p.add_argument("--dossier", default=None, help="Path to the dossier file")
    p.add_argument("--expected-value", type=float, default=None)
    p.add_argument(
        "--expected-value-unit",
        choices=(EXPECTED_VALUE_UNIT,),
        default=None,
        help=(
            "Required with --expected-value; declares a profile-share-equivalent "
            "percentage so the override is globally comparable"
        ),
    )
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser(
        "decompose", help="Atomically fan a discovery out into mechanism candidates"
    )
    p.add_argument("--opp", type=int, required=True, help="Discovery opportunity id")
    p.add_argument(
        "--children", required=True,
        help="Complete decomposition JSON object with accounting and path dispositions",
    )
    add_gate_challenge_arguments(p)
    p.set_defaults(func=cmd_decompose)

    p = sub.add_parser(
        "exhaust", help="Mark one profiled discovery exhausted with evidence"
    )
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.add_argument(
        "--evidence", required=True,
        help="Overlap-aware evidence that no untried viable mechanism remains",
    )
    add_gate_challenge_arguments(p)
    p.set_defaults(func=cmd_exhaust)

    p = sub.add_parser("advance", help="Move an opportunity through a gate")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument(
        "--to", required=True,
        choices=("investigating", "sized", "implementing", "review", "landed"),
    )
    p.add_argument("--ceiling", type=float, default=None, help="Evidenced eliminable share (%%)")
    p.add_argument("--evidence", default=None)
    p.add_argument(
        "--evidence-manifest",
        default=None,
        help="Passing sizing JSON emitted by mechanism_evidence.py summarize",
    )
    p.add_argument(
        "--verification-manifest",
        default=None,
        help="Passing candidate JSON emitted by mechanism_evidence.py compare",
    )
    p.add_argument("--tests", default=None)
    p.add_argument(
        "--build-manifest",
        default=None,
        help="Passing command_evidence.py build receipt for the staged tree",
    )
    p.add_argument(
        "--test-manifest",
        default=None,
        help="Passing command_evidence.py test receipt for the staged tree",
    )
    p.add_argument("--commit", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--override-rework-limit", action="store_true",
                   help="Allow a third rework round (requires justification in --notes)")
    p.add_argument("--skip-review-verification", action="store_true",
                   help="Land without verifying the commit matches the reviewed diff")
    p.add_argument("--allow-unstaged", action="store_true",
                   help="Enter review despite unstaged/untracked changes "
                   "(they are excluded from the reviewed tree)")
    add_gate_challenge_arguments(p)
    p.add_argument("--unexpected-win", action="store_true", help="Require independent confirmation of a newly preregistered endpoint")
    p.add_argument("--performance-receipt", action="append", help="Local score-runner A/B manifest and Pinpoint analysis summary for the candidate; repeat per file")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("squeeze", help="Record one squeeze-loop refinement round")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_squeeze)

    p = sub.add_parser("review", help="Record a review verdict")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--role", required=True, choices=REVIEW_ROLES)
    p.add_argument("--verdict", required=True, choices=("PASS", "FAIL"))
    p.add_argument("--notes", default=None)
    p.add_argument("--report", default=None, help="Path to the full review report")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser(
        "review-scaffold",
        help="Write a review JSON bound to the current tree and evidence digests",
    )
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--role", required=True, choices=REVIEW_ROLES)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_review_scaffold)

    p = sub.add_parser("reject", help="Reject an opportunity with a reason")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.add_argument(
        "--evidence", required=True,
        help="Source/profile evidence that rules out this individual mechanism",
    )
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser(
        "park",
        help=(
            "Defer an opportunity with a reason. Parking a discovery is "
            "permanent (only mechanisms reopen); a recurrent area gets a "
            "fresh discovery from the next profile import"
        ),
    )
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_park)

    p = sub.add_parser("revert", help="Record that a landed opportunity was reverted on the branch")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--revert-commit", required=True, help="The git-revert commit sha")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_revert)

    p = sub.add_parser("reopen", help="Return a parked or newly-contradicted mechanism to the pool")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--contradicts-prior-evidence", action="store_true")
    p.add_argument("--reason", default=None, help="New evidence justifying a terminal-path retry")
    p.set_defaults(func=cmd_reopen)

    p = sub.add_parser("note", help="Append a note to an opportunity")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser(
        "checkpoint-targets",
        help="Print the preregistered landed target-story selector",
    )
    p.set_defaults(func=cmd_checkpoint_targets)

    p = sub.add_parser("checkpoint", help="Record a cumulative flag on/off measurement")
    p.add_argument(
        "--kind", choices=("targeted", "full-suite"), default="full-suite",
        help="Targeted checkpoints gate landing efficacy; full-suite "
        "checkpoints guard regressions and support aggregate claims",
    )
    p.add_argument("--summary", help="remote_measure.py machine-readable summary JSON")
    p.add_argument("--delta", type=float, default=None, help=argparse.SUPPRESS)
    p.add_argument("--ci-low", type=float, default=None, help=argparse.SUPPRESS)
    p.add_argument("--ci-high", type=float, default=None, help=argparse.SUPPRESS)
    p.add_argument("--manifest", default=None)
    p.add_argument("--sha", default=None)
    p.add_argument("--notes", default=None)
    add_gate_challenge_arguments(p)
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("status", help="Regenerate STATUS.md and print its path")
    p.add_argument("--print", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser(
        "calibrate",
        help="Record two separately timed A/A sessions; per-story MDEs set the qualification floors",
    )
    p.add_argument("--manifest", action="append", required=True,
                   help="run_ab_benchmark.py A/A manifest (repeat for each session)")
    p.add_argument("--tolerance-pct", type=float, default=0.5,
                   help="Every null interval must lie within +/- this many percent")
    p.add_argument("--max-mde-pct", type=float, default=3.0,
                   help="Reject a session whose story MDE exceeds this")
    p.add_argument("--max-abs-lag1", type=float, default=0.4)
    p.set_defaults(func=cmd_calibrate)

    p = sub.add_parser(
        "audit",
        help="Recompute and verify all campaign evidence, receipts, and snapshots",
    )
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser(
        "audit-exhaustion",
        help="Check whether the latest profile and ledger prove campaign exhaustion",
    )
    p.add_argument(
        "--allow-unverified-repository", action="store_true",
        help=argparse.SUPPRESS,
    )
    p.set_defaults(func=cmd_audit_exhaustion)

    p = sub.add_parser("show", help="Dump ledger or one opportunity as JSON")
    p.add_argument("--opp", type=int, default=None)
    p.add_argument("--area-key", default=None, help="Show all history for one area")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("next", help="Print the next candidates by priority")
    p.add_argument("--count", type=int, default=3)
    p.set_defaults(func=cmd_next)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if test_bypass_requested() and not test_bypass_active():
            raise CampaignError(
                f"{TEST_BYPASS_ENV} is test-only and is honored only by an "
                "in-process unittest run"
            )
        if args.command == "init" and not args.dir:
            campaign_dir = agents_dir() / "campaigns" / args.name
        else:
            campaign_dir = pathlib.Path(args.dir or default_campaign_dir())
        campaign_dir.mkdir(parents=True, exist_ok=True)
        with open(campaign_dir / ".ledger.lock", "a+") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            return args.func(args)
    except CampaignError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
