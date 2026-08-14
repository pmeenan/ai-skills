#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Campaign ledger, gate enforcement, and STATUS.md generation.

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
import datetime
import fcntl
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import shutil

import mechanism_evidence as mechanism_contract

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
PILOT_MIN_LANDINGS = 3
PILOT_MAX_LANDINGS = 5
MIN_SCORE_BLOCKS = 32
SCORE_MANIFEST_SCHEMA_VERSION = 3
SCORE_MANIFEST_RUNNER = "run_ab_benchmark.py/v3"
MIN_FULL_SUITE_REP_SECONDS = 30
T_POWER_80 = {
    1: 1.376, 2: 1.061, 3: 0.978, 4: 0.941, 5: 0.920, 6: 0.906,
    7: 0.896, 8: 0.889, 9: 0.883, 10: 0.879, 11: 0.876,
    12: 0.873, 13: 0.870, 14: 0.868, 15: 0.866, 16: 0.865,
    17: 0.863, 18: 0.862, 19: 0.861, 20: 0.860, 25: 0.856,
    30: 0.854,
}
TEST_BYPASS_ENV = "SP3_CAMPAIGN_TEST_ALLOW_UNVERIFIED"
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
    ),
    "adversary": (
        "spec", "security", "privacy", "lifecycle", "tests",
        "benchmark_overfit_checked", "feature_flag_guarded",
        "runtime_binary_changed",
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


def load_gate_evidence(path, *, opp, phase):
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
        ("opportunity_id", opp["id"]),
        ("mechanism_key", opp.get("mechanism_key")),
        ("profile_id", opp.get("profile_id")),
        ("interval_kind", "exact-scored"),
    ):
        if evidence.get(field) != expected:
            raise CampaignError(
                f"Evidence {field} {evidence.get(field)!r} does not match {expected!r}"
            )
    if evidence.get("score_scope", {}).get("classification") not in (
        "score-critical", "cpu-only"
    ):
        raise CampaignError("Evidence lacks a score-scope classification")
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
    checkpoints = ledger.data.get("checkpoints", [])
    checkpoint_count = checkpoints[-1]["landed_count"] if checkpoints else 0
    latest_ci = checkpoints[-1].get("ci") if checkpoints else None
    if (
        checkpoints
        and checkpoint_count == landed_count
        and landed_count >= PILOT_MIN_LANDINGS
        and isinstance(latest_ci, list)
        and len(latest_ci) == 2
        and latest_ci[0] <= 0
    ):
        raise CampaignError(
            "Landing is blocked because the latest cumulative out/release "
            f"checkpoint CI [{latest_ci[0]:+.4f}%, {latest_ci[1]:+.4f}%] is not positive; "
            "increase balanced blocks, diagnose the evidence chain, or bisect/revert"
        )
    if len(ledger.landed()) - checkpoint_count >= MAX_LANDINGS_WITHOUT_CHECKPOINT:
        raise CampaignError(
            f"Landing is blocked after {MAX_LANDINGS_WITHOUT_CHECKPOINT} unchecked "
            "landings; record a cumulative checkpoint"
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
    env = os.environ.get("SP3_CAMPAIGN_DIR")
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
                "or pass --dir/SP3_CAMPAIGN_DIR."
            )
        with open(self.path) as f:
            self.data = json.load(f)
        self._verify_snapshot_history()
        self._migrate()
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
                "-c", "user.name=Speedometer Campaign",
                "-c", "user.email=speedometer-campaign@invalid",
                "commit", "-qm", message,
            ],
            check=True,
        )

    def _migrate(self):
        """Add fields required by the current campaign evidence schema.

        Legacy opportunities remain concrete mechanisms so an in-flight
        campaign can resume without losing gate state.  Their synthetic keys
        deliberately never collide with new, investigator-supplied keys.
        """
        self.data.setdefault("schema_version", 1)
        self.data.setdefault("profile_runs", [])
        self.data.setdefault("next_sequence", 1)
        self.data.setdefault("ledger_revision", 0)
        self.data.setdefault("source_area_keys", {})
        self.data.setdefault("gate_challenges", [])
        self.data.setdefault("config", {}).setdefault("audit_history_required", False)
        self.data.setdefault("pilot", {
            "required": True,
            "minimum_landings": PILOT_MIN_LANDINGS,
            "maximum_landings": PILOT_MAX_LANDINGS,
            "status": "pending",
            "reason": None,
        })
        for opp in self.data.get("opportunities", []):
            opp.setdefault("kind", "mechanism")
            opp.setdefault("area_key", canonical_key(opp.get("anchor", "area")))
            if opp["kind"] == "mechanism":
                opp.setdefault("mechanism_key", f"legacy-{opp['id']:03d}")
            else:
                opp.setdefault("mechanism_key", None)
            opp.setdefault("parent_id", None)
            opp.setdefault(
                "discovery_ids",
                [opp["parent_id"]] if opp.get("parent_id") is not None else [],
            )
            opp.setdefault("profile_id", None)
            opp.setdefault("source_profile_ids", [])
            opp.setdefault("known_mechanism_ids", [])
            opp.setdefault("runtime_change_sequence", None)
            opp.setdefault("observations", [])
            opp.setdefault("expected_value_unit", None)
            opp.setdefault("measured_priority_pct", None)
            opp.setdefault("sizing_evidence", None)
            opp.setdefault("sizing_evidence_sha256", None)
            opp.setdefault("verification_evidence", None)
            opp.setdefault("verification_evidence_sha256", None)
            if opp["kind"] == "discovery":
                opp.setdefault("decomposition_revision", 0)
                opp.setdefault("decomposition_sha256", None)
                if opp.get("path_accounting"):
                    if not opp["decomposition_revision"]:
                        opp["decomposition_revision"] = 1
                    digest = decomposition_digest(opp)
                    if not opp["decomposition_sha256"]:
                        opp["decomposition_sha256"] = digest
                    skeptic = opp.get("reviews", {}).get("skeptic")
                    if skeptic:
                        skeptic.setdefault(
                            "decomposition_revision",
                            opp["decomposition_revision"],
                        )
                        skeptic.setdefault("decomposition_sha256", digest)
        events = []
        for profile in self.data["profile_runs"]:
            if profile.get("sequence") is None:
                events.append((profile.get("ts", ""), "profile", profile))
        for opp in self.data.get("opportunities", []):
            if (
                opp["status"] in ("landed", "reverted")
                and opp.get("runtime_change_sequence") is None
            ):
                events.append((opp.get("status_since", ""), "runtime", opp))
        sequence = max(
            [self.data.get("next_sequence", 1) - 1]
            + [p.get("sequence", 0) or 0 for p in self.data["profile_runs"]]
            + [o.get("runtime_change_sequence", 0) or 0
               for o in self.data.get("opportunities", [])]
        ) + 1
        for _, kind, item in sorted(events, key=lambda event: event[0]):
            field = "sequence" if kind == "profile" else "runtime_change_sequence"
            item[field] = sequence
            sequence += 1
        self.data["next_sequence"] = sequence
        self.data["schema_version"] = 3

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
        lines.append(
            f"# SP3 Campaign: {cfg['name']} — branch `{cfg['branch']}`"
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
                f" · Last checkpoint (after {cp['landed_count']} landed): "
                f"{cp['delta_pct']:+.2f}% "
                f"[{cp['ci'][0]:+.2f}%, {cp['ci'][1]:+.2f}%]"
            )
        lines.append(header)
        lines.append("")
        lines.append(f"_Updated: {utc_now()} (generated from ledger.json — do not edit)_")
        lines.append("")
        lines.append(
            "**Outcome objective:** reproducible positive Speedometer movement "
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
        checkpoint_landed = checkpoints[-1]["landed_count"] if checkpoints else 0
        unchecked_landings = max(0, len(landed) - checkpoint_landed)
        lines.append("")
        lines.append(
            "**Freshness:** "
            f"{profile_changes}/{MAX_LANDINGS_WITHOUT_PROFILE} runtime changes "
            "since profile · "
            f"{unchecked_landings}/{MAX_LANDINGS_WITHOUT_CHECKPOINT} landings "
            "since checkpoint"
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
        lines.append("## Next up (global impact priority)")
        nxt = self.next_candidates(5)
        if nxt:
            for i, o in enumerate(nxt, 1):
                priority, basis, measured = self.priority_info(o)
                lines.append(
                    f"{i}. #{o['id']:03d} [{o.get('kind', 'mechanism')}] "
                    f"{o['anchor']} "
                    f"(priority {priority:.3f}, {basis}; "
                    f"measured {measured:.3f}%, "
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
        lines.append("## Checkpoints (cumulative flag on/off, full suite)")
        if checkpoints:
            lines.append("| After # landed | Delta | 95% CI | Date | Notes |")
            lines.append("| --- | --- | --- | --- | --- |")
            for cp in checkpoints:
                lines.append(
                    f"| {cp['landed_count']} | {cp['delta_pct']:+.2f}% | "
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
    if not repo_root:
        if not allow_unverified:
            raise CampaignError(
                "A profile can certify exhaustion only inside the profiled Git "
                "repository. Tests may opt out with "
                "--allow-unverified-repository."
            )
        if not test_bypass_active():
            raise CampaignError(
                "--allow-unverified-repository is restricted to test processes"
            )
        print("warning: profile repository verification explicitly bypassed",
              file=sys.stderr)
        return {
            "repository_root": None,
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


def semantic_entry_identity(entry_key):
    """Return the profiler work identity represented by a frontier root.

    Context entry keys embed a digest of the full call path, which is exact
    within one capture but fragile across captures (one differing frame near
    the root renames the key). A hot symbol can also move between a
    caller-sensitive context aggregate and a function aggregate across runs.
    Recurrence decisions must therefore compare the represented symbol, never
    the raw aggregate kind or context digest.
    """
    kind, separator, identity = entry_key.partition(":")
    if separator and kind in ("context", "function", "symbol"):
        if kind == "context" and "@" in identity:
            identity = identity.rsplit("@", 1)[0]
        return f"symbol:{identity}"
    return entry_key


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
    path, *, expected_sha, feature, expected_features, floor_pct
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
                f"Capture {capture_id} is not scoped to exact Speedometer score timers"
            )
        if strict_evidence and summary.get("metric_weighting") != "speedometer-geomean-v1":
            raise CampaignError(
                f"Capture {capture_id} does not use equal suite/repetition score weighting"
            )
        if strict_evidence:
            nominal = require_finite_number(
                summary.get("nominal_samples_at_floor"),
                f"Capture {capture_id} nominal_samples_at_floor",
                nonnegative=True,
            )
            if nominal < 100:
                raise CampaignError(
                    f"Capture {capture_id} has only {nominal:.1f} nominal samples at floor"
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
        if summary.get("stories") != "all":
            raise CampaignError(
                f"Capture {capture_id} is not a full-suite stories=all profile"
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
        artifact_path = summary.get("full_candidate_frontier_json")
        try:
            resolved_artifact = pathlib.Path(artifact_path).resolve()
            if resolved_artifact in seen_artifact_paths:
                raise CampaignError(
                    "Capture summaries reuse the same analyzer artifact"
                )
            if not resolved_artifact.is_relative_to(pathlib.Path(resolved_results)):
                raise CampaignError(
                    f"Capture {capture_id} analyzer artifact is outside local_results"
                )
            seen_artifact_paths.add(resolved_artifact)
            artifact_bytes = resolved_artifact.read_bytes()
            artifact = json.loads(artifact_bytes)
        except CampaignError:
            raise
        except (TypeError, OSError, json.JSONDecodeError) as exc:
            raise CampaignError(
                f"Capture {capture_id} analyzer artifact is unreadable: {exc}"
            ) from exc
        if artifact.get("quality", {}).get("accepted") is not True:
            raise CampaignError(f"Capture {capture_id} analyzer artifact failed quality")
        if strict_evidence and artifact.get("quality", {}).get("interval_kind") != "exact-scored":
            raise CampaignError(f"Capture {capture_id} analyzer used broad intervals")
        if strict_evidence:
            artifact_nominal = require_finite_number(
                artifact.get("quality", {}).get("nominal_samples_at_floor"),
                f"Capture {capture_id} artifact nominal_samples_at_floor",
                nonnegative=True,
            )
            if not math.isclose(
                artifact_nominal, nominal, rel_tol=0, abs_tol=1e-9
            ):
                raise CampaignError(
                    f"Capture {capture_id} sample-floor summary disagrees with analyzer artifact"
                )
            if artifact.get("quality", {}).get("build_provenance") != build_provenance:
                raise CampaignError(
                    f"Capture {capture_id} build provenance disagrees with analyzer artifact"
                )
        selection = artifact.get("selection", {})
        if strict_evidence and selection.get("metric_weighting") != "speedometer-geomean-v1":
            raise CampaignError(f"Capture {capture_id} analyzer is not score-weighted")
        if selection.get("inventory_complete") is not True:
            raise CampaignError(f"Capture {capture_id} analyzer inventory is incomplete")
        derived_entries, derived_inventory, derivation_problems = (
            derive_frontier_inventory(artifact)
        )
        if derivation_problems:
            raise CampaignError(
                f"Capture {capture_id} analyzer artifact cannot attest a "
                "complete inventory: " + "; ".join(derivation_problems[:5])
            )
        summary["artifact_sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
        for field in (
            "analyzer_min_inclusive_share", "analyzer_min_marginal_share"
        ):
            analyzer_floor = require_finite_number(
                summary.get(field), f"Capture {capture_id} {field}", nonnegative=True
            )
            selection_field = (
                "min_inclusive_share" if field == "analyzer_min_inclusive_share"
                else "min_marginal_share"
            )
            artifact_floor = require_finite_number(
                selection.get(selection_field),
                f"Capture {capture_id} artifact {selection_field}",
                nonnegative=True,
            )
            expected_floor = floor_pct / 100.0
            if not math.isclose(
                analyzer_floor, expected_floor, rel_tol=0, abs_tol=1e-12
            ) or not math.isclose(
                artifact_floor, expected_floor, rel_tol=0, abs_tol=1e-12
            ):
                raise CampaignError(
                    f"Capture {capture_id} {field} and analyzer artifact must "
                    f"equal campaign fraction {expected_floor}"
                )
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
    if len(repetition_counts) != 1:
        raise CampaignError("Capture repetition counts do not match")
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
    if skip_verification:
        print("warning: review verification skipped by flag", file=sys.stderr)
        return
    if not repo_root or not opp.get("review_base"):
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


def cmd_init(args):
    args.share_floor = require_finite_number(
        args.share_floor, "--share-floor", nonnegative=True
    )
    if args.share_floor <= 0:
        raise CampaignError("--share-floor must be greater than zero")
    campaign_dir = pathlib.Path(args.dir) if args.dir else None
    if campaign_dir is not None:
        # Deliberately do NOT repoint the shared `current` symlink at a
        # custom --dir: tests and throwaway ledgers use --dir, and silently
        # hijacking the active-campaign pointer would be worse than the
        # inconvenience of passing --dir (or SP3_CAMPAIGN_DIR) explicitly.
        print(
            f"note: this campaign lives outside the campaigns root; later "
            f"commands must pass --dir {campaign_dir} or set "
            f"SP3_CAMPAIGN_DIR={campaign_dir} (the 'current' symlink is "
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
        "schema_version": 3,
        "next_sequence": 1,
        "config": {
            "name": args.name,
            "branch": args.branch,
            "target_landed": args.target,
            "share_floor_pct": args.share_floor,
            "feature": args.feature,
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
        "stories": path.get("stories") or discovery.get("stories"),
        "dossier": path.get("dossier") or discovery.get("dossier"),
        "expected_value": path.get("expected_value"),
        "expected_value_unit": path.get("expected_value_unit"),
        "measured_priority_pct": measured_priority,
        "evidence": path.get("evidence"),
        "work_fingerprints": sorted({
            ref.get("semantic_key") or f"{ref['entry_key']}|{ref['hotspot_key']}"
            for ref in fingerprint_refs
        }),
    }
    opp.setdefault("observations", []).append(observation)
    if opp["status"] in MECHANISM_TERMINAL or not update_sizing:
        # Terminal mechanisms keep the fields their verdict used; covered-by
        # wrapper observations are overlap provenance, not a replacement for
        # the owning mechanism's sizing identity.
        return
    opp["anchor"] = observation["anchor"]
    opp["share_pct"] = observation["share_pct"]
    opp["stories"] = observation["stories"]
    opp["dossier"] = observation["dossier"]
    opp["expected_value"] = observation["expected_value"]
    opp["expected_value_unit"] = observation["expected_value_unit"]
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
            if not ref[1].startswith("context:"):
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
                "artifact": summary["full_candidate_frontier_json"],
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
    semantic = semantic_entry_identity(entry_key)
    return semantic.split(":", 1)[1] if ":" in semantic else semantic


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
        if args.evidence_manifest:
            evidence, evidence_digest = load_gate_evidence(
                args.evidence_manifest, opp=opp, phase="sizing"
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
                args.verification_manifest, opp=opp, phase="candidate"
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
                "exclusive-cycle reduction inside exact score intervals"
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
            "out-of-scope"
        ):
            raise CampaignError(
                f"Path {index} has invalid disposition {disposition!r}"
            )
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


def load_review_report(path, *, opp, role, verdict):
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
            args.report, opp=opp, role=args.role, verdict=args.verdict
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


def validate_score_result_artifact(result, *, manifest_dir, evidence_dir,
                                   expected_arm, expected_block, expected_score,
                                   run_start, run_finish):
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
    score = raw.get("Score")
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        raise CampaignError(f"Raw checkpoint result has no scalar Score: {path}")
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
    return start, finish, result.get("position")


def validate_and_recompute_checkpoint(manifest, manifest_path):
    if (
        manifest.get("schema_version") != SCORE_MANIFEST_SCHEMA_VERSION
        or manifest.get("runner") != SCORE_MANIFEST_RUNNER
    ):
        raise CampaignError("Checkpoint must be a runner-owned v3 manifest")
    if manifest.get("mode") != "ab" or manifest.get("stories") != "all":
        raise CampaignError("Checkpoint v3 manifest is not a full-suite feature A/B")
    block_count = manifest.get("blocks")
    if (
        isinstance(block_count, bool) or not isinstance(block_count, int)
        or block_count < MIN_SCORE_BLOCKS or block_count % 2
    ):
        raise CampaignError("Checkpoint v3 manifest has an invalid block count")
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
            if (
                not isinstance(results, list) or len(results) != 2
                or not isinstance(scores, list) or len(scores) != 2
            ):
                raise CampaignError(f"Checkpoint block {index} lacks raw arm {arm} results")
            for result, score in zip(results, scores):
                start, finish, position = validate_score_result_artifact(
                    result,
                    manifest_dir=manifest_path.parent,
                    evidence_dir=evidence_dir,
                    expected_arm=arm,
                    expected_block=index,
                    expected_score=score,
                    run_start=run_start,
                    run_finish=run_finish,
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
            skill_repo_path / "optimize-speedometer" / "scripts" / "campaign.py"
        ).resolve()
        required_markers = (
            "optimize-speedometer/SKILL.md",
            "optimize-speedometer/scripts/campaign.py",
            "chrome-cycle-profiling/SKILL.md",
        )
        if script != expected_script or any(
            not (skill_repo_path / marker).is_file() for marker in required_markers
        ):
            raise CampaignError(
                "campaign.py is not executing from the optimize-speedometer "
                "directory of a standalone skills Git checkout; copied or "
                "Chromium-gitignored skill directories are not trusted"
            )
        for marker in required_markers:
            subprocess.run(
                ["git", "-C", skill_repo, "ls-files", "--error-unmatch", marker],
                check=True, capture_output=True, text=True,
            )
        status = subprocess.run(
            [
                "git", "-C", skill_repo, "status", "--porcelain", "--",
                "optimize-speedometer", "chrome-cycle-profiling",
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
    checkpoint_challenges = []
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
            raise CampaignError("Checkpoint summary is not from the v3 score runner")
        if summary.get("mode") != "ab" or summary.get("stories") != "all":
            raise CampaignError("Checkpoint must be a cumulative full-suite feature A/B")
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
        computed = validate_and_recompute_checkpoint(manifest_data, manifest_path)
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
        checkpoint_challenges = validate_gate_challenges(
            args,
            gate="checkpoint",
            artifact_digests=[evidence_sha256, manifest_sha256],
        )
    elif test_bypass_active():
        delta, ci_low, ci_high = args.delta, args.ci_low, args.ci_high
        manifest, sha = args.manifest, args.sha
        evidence_sha256, seed, mde, manifest_sha256 = None, None, None, None
    else:
        raise CampaignError(
            "checkpoint requires --summary from remote_measure.py; manual deltas are rejected"
        )
    ledger.data.setdefault("checkpoints", []).append(
        {
            "ts": utc_now(),
            "landed_count": len(ledger.landed()),
            "delta_pct": delta,
            "ci": [ci_low, ci_high],
            "manifest": manifest,
            "manifest_sha256": manifest_sha256,
            "sha": sha,
            "summary": args.summary,
            "summary_sha256": evidence_sha256,
            "seed": seed,
            "mde_80_power_pct": mde,
            "notes": args.notes,
        }
    )
    record_gate_challenges(
        ledger,
        gate="checkpoint",
        subject=f"landed-{len(ledger.landed())}",
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
                "net_scored_cycle_share_saved_pct", 0.0
            ))
            for opp in ledger.landed()
        )
        update_pilot_from_checkpoint(
            pilot, landed_count=landed_count, saved=saved, delta=delta,
            ci_low=ci_low, ci_high=ci_high,
            evidence_sha256=evidence_sha256,
        )
    ledger.save()
    print(f"Recorded checkpoint after {len(ledger.landed())} landed: {delta:+.2f}%")
    return 0


def update_pilot_from_checkpoint(
    pilot, *, landed_count, saved, delta, ci_low, ci_high, evidence_sha256
):
    common = {"checkpoint_sha256": evidence_sha256, "ts": utc_now()}
    if saved > 0 and ci_low > 0:
        pilot.update({
            **common,
            "status": "passed",
            "reason": (
                f"mechanistic direction +{saved:.4f}% and cumulative A/B CI "
                f"[{ci_low:+.4f}%, {ci_high:+.4f}%] is positive after "
                f"{landed_count} candidates"
            ),
        })
    elif saved <= 0 or ci_high <= 0:
        pilot.update({
            **common,
            "status": "failed",
            "reason": (
                f"pilot contradicted the mechanistic evidence (mechanistic "
                f"{saved:+.4f}%, cumulative A/B {delta:+.4f}% with CI "
                f"[{ci_low:+.4f}%, {ci_high:+.4f}%]); stop and repair the pipeline"
            ),
        })
    else:
        pilot.update({
            **common,
            "status": "pending",
            "reason": (
                f"pilot is inconclusive: cumulative A/B {delta:+.4f}% with CI "
                f"[{ci_low:+.4f}%, {ci_high:+.4f}%] does not prove a positive "
                "effect; land no more than five pilot candidates, then increase "
                "balanced block count and remeasure"
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
    for opp in ledger.data.get("opportunities", []):
        for phase, path_field in (
            ("sizing", "evidence"),
            ("candidate", "verification_evidence_path"),
        ):
            path = opp.get(path_field)
            if not isinstance(path, str):
                continue
            try:
                evidence, _ = load_gate_evidence(path, opp=opp, phase=phase)
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
                    path, opp=opp, role=role, verdict=review.get("verdict")
                )
                if digest_value != review.get("report_sha256"):
                    problems.append(f"opportunity {opp['id']} {role} report changed")
            except CampaignError as exc:
                problems.append(f"opportunity {opp['id']} {role}: {exc}")
    for index, checkpoint in enumerate(ledger.data.get("checkpoints", []), 1):
        try:
            summary_path = pathlib.Path(checkpoint["summary"])
            manifest_path = pathlib.Path(checkpoint["manifest"])
            if sha256_file(summary_path) != checkpoint.get("summary_sha256"):
                raise CampaignError("summary digest changed")
            if sha256_file(manifest_path) != checkpoint.get("manifest_sha256"):
                raise CampaignError("manifest digest changed")
            manifest = json.loads(manifest_path.read_text())
            validate_and_recompute_checkpoint(manifest, manifest_path)
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
            f"#{o['id']:03d} {o['anchor']} priority={priority:.3f} "
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
        help="Campaign directory (default: $SP3_CAMPAIGN_DIR or .agents/campaigns/current)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new campaign ledger")
    p.add_argument("--name", required=True)
    p.add_argument("--branch", default="speedometer")
    p.add_argument("--target", type=int, default=20, help="Target landed count")
    p.add_argument(
        "--share-floor",
        type=float,
        default=0.3,
        help="Minimum marginal profile share (%%) worth attempting",
    )
    p.add_argument("--feature", default="Speedometer3Optimizations")
    p.add_argument("--remote-host", default="linux")
    p.add_argument("--remote-src", default=None)
    p.add_argument("--force", action="store_true")
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

    p = sub.add_parser("checkpoint", help="Record a cumulative flag on/off measurement")
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
