#!/usr/bin/env python3
"""Build a deterministic effort profile for a pinned Chromium review."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


FIELD_RE = re.compile(r"^- ([^:]+):\s*(.*?)\s*$", re.MULTILINE)
SURFACE_RE = re.compile(
    r"^\s*[+-](?![+-])\s*(?:"
    r"(?:class|struct|enum(?:\s+class)?|namespace)\s+[A-Za-z_]\w*|"
    r"(?:[A-Za-z_]\w*(?:::\w+)*\s*\([^;{}]*\)\s*(?:const\s*)?(?:\{|$))|"
    r"(?:[A-Za-z_]\w*(?:::\w+)+\s*=)|"
    r"(?:[A-Z][A-Z0-9_]+\s*=)"
    r")",
    re.MULTILINE,
)

RISK_PATTERNS: dict[str, re.Pattern[str]] = {
    "api_or_abi": re.compile(
        r"\b(?:CONTENT_EXPORT|COMPONENT_EXPORT|BASE_EXPORT|NET_EXPORT|virtual|override|"
        r"mojom|idl|public:)\b|(?:^|/)(?:public|include)/", re.IGNORECASE
    ),
    "async_or_lifecycle": re.compile(
        r"\b(?:PostTask|BindOnce|BindRepeating|WeakPtr|callback|OnceCallback|"
        r"RepeatingCallback|timer|sequence_checker|destructor|~[A-Za-z_]\w*)\b",
        re.IGNORECASE,
    ),
    "ownership_or_gc_lifecycle": re.compile(
        r"\b(?:raw_ptr|GarbageCollected|Member\s*<|WeakMember\s*<|Persistent\s*<|"
        r"ExecutionContext|ContextDestroyed|DocumentLifecycle|BackForwardCache|BFCache)\b",
        re.IGNORECASE,
    ),
    "state_or_reentrancy": re.compile(
        r"\b(?:state_|pending_|in_flight|reentrant|recursion|observer|notify|"
        r"transition|cancel|reset)\b",
        re.IGNORECASE,
    ),
    "persistence_or_wire_format": re.compile(
        r"\b(?:pickle|serialize|deserialize|protobuf|proto2|proto3|schema|versioned|"
        r"prefs?|database|sqlite|on[-_ ]disk|wire format)\b|\.(?:proto|mojom)$",
        re.IGNORECASE | re.MULTILINE,
    ),
    "security_or_privacy": re.compile(
        r"\b(?:security|privacy|permission|origin|sandbox|credential|token|cookie|"
        r"authentication|authorization|unsafe|tainted)\b",
        re.IGNORECASE,
    ),
    "performance_or_memory": re.compile(
        r"\b(?:performance|latency|allocation|malloc|free|new\s+|delete\s+|"
        r"memcpy|memmove|memory pressure|resource exhaustion|unbounded|"
        r"benchmark|O\([^)]+\))\b",
        re.IGNORECASE,
    ),
    "feature_or_configuration": re.compile(
        r"\b(?:BASE_FEATURE|FeatureList|FEATURE_VALUE_TYPE|field trial|finch|"
        r"command[-_ ]line|switches::|buildflag)\b",
        re.IGNORECASE,
    ),
    "build_or_dependency": re.compile(
        r"(?:^|/)(?:BUILD\.gn|DEPS|OWNERS)$|\b(?:deps|public_deps|visibility|"
        r"component|source_set)\b",
        re.IGNORECASE,
    ),
    "threading_or_concurrency": re.compile(
        r"\b(?:Thread|Lock|AutoLock|Mutex|atomic|memory_order|SequenceBound|"
        r"SequencedTaskRunner|Concurrent|race)\b",
        re.IGNORECASE,
    ),
    "flaky_test_or_timing": re.compile(
        r"\b(?:RunLoop|RunUntilIdle|FastForwardBy|timeout|flaky|MockTime|"
        r"ScopedRunLoopTimeout)\b",
        re.IGNORECASE,
    ),
}

# Routing signals deliberately live outside RISK_PATTERNS. A specialist file
# or symbol should activate the matching review lens, but a benign .grd,
# Java, Rust, accessibility, or telemetry edit must not become high-risk based
# solely on its file type. Independent behavior-sensitive signals above still
# drive effort escalation.
SPECIALIST_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "TSY", "Threading And Synchronization",
        re.compile(
            r"\b(?:std::atomic|base::Atomic|memory_order_|compare_exchange|fetch_(?:add|sub)|"
            r"Lock|AutoLock|Mutex|ConditionVariable|WaitableEvent|SEQUENCE_CHECKER|"
            r"DETACH_FROM_SEQUENCE|ThreadPool|MayBlock|TaskPriority|BLOCK_SHUTDOWN|"
            r"SKIP_ON_SHUTDOWN|CONTINUE_ON_SHUTDOWN|SequencedTaskRunner)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "OBL", "Ownership And Blink Lifecycle",
        re.compile(
            r"\b(?:raw_ptr|scoped_refptr|RefCounted|GarbageCollected|Member\s*<|"
            r"WeakMember\s*<|Persistent\s*<|Trace\s*\(\s*Visitor|Oilpan|"
            r"ExecutionContext|ScriptState|ContextDestroyed|DocumentLifecycle|"
            r"BackForwardCache|BFCache|prerender|frozen|detached)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "MIS", "Mojo IPC Authorization And Sandbox",
        re.compile(
            r"\.mojom(?:$|\b)|\b(?:mojo::|mojom::|PendingRemote|PendingReceiver|"
            r"AssociatedRemote|AssociatedReceiver|ReceiverSet|RemoteSet|BinderMap|"
            r"MinVersion|RequireVersion|ReportBadMessage|sandbox::|SandboxPolicy|"
            r"BrokerServices|TargetServices)\b|(?:^|/)sandbox/",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "PRS", "Performance And Resource Scaling",
        re.compile(
            r"\b(?:benchmark|perf(?:ormance)?|latency|throughput|memory pressure|"
            r"resource exhaustion|unbounded|evict(?:ion)?|cache size|queue size|"
            r"reserve\s*\(|shrink_to_fit|MayBlock|startup|binary size|wakeups?|"
            r"power|GPU memory|thread hops?|allocations?|copies|memcpy|memmove|"
            r"O\([^)]+\))\b|(?:^|/)(?:tools/perf|testing/perf|benchmarks?)/",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "PLS", "Platform And Language Semantics",
        re.compile(
            r"\.(?:rs|java|kt|kts|m|mm|swift|js|mjs|ts|tsx|py|gn|gni|proto|mojom)$|"
            r"\b(?:JNI_|jni::|JavaParamRef|ObjC|extern\s+\"C\"|cxx::bridge|"
            r"unsafe\s*\{|cfg\s*\(|BUILDFLAG|IS_(?:WIN|MAC|ANDROID|LINUX|CHROMEOS)|"
            r"32[- ]bit|endianness|alignment)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "BAG", "Build API And Generated Assets",
        re.compile(
            r"(?:^|/)(?:BUILD\.gn|DEPS|OWNERS)$|\.(?:gn|gni|grd|grdp|xtb|proto|mojom)$|"
            r"\b(?:public_deps|specific_include_rules|visibility|testonly|"
            r"COMPONENT_EXPORT|CONTENT_EXPORT|BASE_EXPORT|NET_EXPORT|"
            r"generate(?:d)?|grit|resource_ids?)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "PAT", "Privacy And Telemetry",
        re.compile(
            r"(?:^|/)(?:histograms|enums|ukm)\.xml$|\b(?:UmaHistogram|HistogramTester|"
            r"ukm::|UkmRecorder|UkmSource|incognito|off[-_ ]the[-_ ]record|"
            r"StoragePartition|consent|retention|deletion|identifiability|PII|"
            r"metrics::)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "AXI", "Accessibility And Internationalization",
        re.compile(
            r"\b(?:AXNode|AXTree|AXRole|AXEvent|accessibility|aria[-_]|screen reader|"
            r"live region|high contrast|prefers-reduced-motion|l10n|i18n|bidi|RTL|"
            r"IDS_[A-Z0-9_]+|GetStringUTF|MessageFormatter|plural)\b|"
            r"(?:^|/)(?:ui/accessibility|chrome/app/resources|components/strings)/",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "NET", "Network Semantics",
        re.compile(
            r"\b(?:redirect|NetworkIsolationKey|NetworkAnonymizationKey|"
            r"SchemefulSite|CookiePartitionKey|credentials mode|CORS|CSP|CORP|COEP|"
            r"SameSite|proxy|idempotent|body replay|Vary|cache key|certificate|TLS|"
            r"URLLoader|ResourceRequest|net::ERR_)\b",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "FTS", "Fuzzing And Test Strategy",
        re.compile(
            r"\b(?:LLVMFuzzerTestOneInput|FuzzedDataProvider|fuzz(?:er|ing)?|"
            r"seed corpus|dictionary|WebTest|WPT|browser test|"
            r"test expectations|DISABLED_|FLAKY_)\b|"
            r"(?:^|/)(?:fuzzers?|web_tests|wpt_internal)/|"
            r"(?:_fuzzer|_browsertest|_browser_test)\.[^.]+$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ),
    (
        "FPM", "Field Propagation Matrix",
        re.compile(
            r"\b(?:CopyFrom|Clone|DeepCopy|Swap|Reset|Clear|operator\s*==|"
            r"operator\s*<=>|Hash|Serialize|Deserialize|ToDebugString|Trace)\b|"
            r"\b(?:copy|move)_(?:constructor|assignment)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ACS", "Associative Container Semantics",
        re.compile(
            r"\b(?:std::|base::)?(?:flat_)?(?:map|set|multimap|multiset|unordered_map|"
            r"unordered_set)\s*<|\b(?:hash|hasher|key_equal|less<|lower_bound|"
            r"upper_bound|equal_range|try_emplace|insert_or_assign|heterogeneous lookup|"
            r"strict weak ordering)\b",
            re.IGNORECASE,
        ),
    ),
)

HIGH_RISK_SIGNALS = {
    "api_or_abi",
    "async_or_lifecycle",
    "ownership_or_gc_lifecycle",
    "state_or_reentrancy",
    "persistence_or_wire_format",
    "security_or_privacy",
    "performance_or_memory",
    "feature_or_configuration",
    "threading_or_concurrency",
    "flaky_test_or_timing",
}


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"profile-review.py: {message}")


def read_json_xssi(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if text.startswith(")]}'"):
        newline = text.find("\n")
        if newline < 0:
            fail(f"{path} contains only a Gerrit XSSI prefix")
        text = text[newline + 1 :]
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        fail(f"invalid JSON in {path}: {error}")


def pin_fields(pin_path: Path) -> dict[str, str]:
    if not pin_path.is_file():
        fail(f"missing {pin_path}")
    return {key: value for key, value in FIELD_RE.findall(pin_path.read_text(encoding="utf-8"))}


def run_git(worktree: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(worktree), *args],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout
    except subprocess.CalledProcessError as error:
        fail(f"git {' '.join(args)} failed: {error.stderr.strip()}")


def classify_file(path: str) -> str:
    lower = path.lower()
    name = Path(lower).name
    if name in {"owners", "watchlists", "codeowners", ".gitignore"}:
        return "metadata"
    if (re.fullmatch(r"readme(?:\.(?:md|rst|adoc|txt|chromium))?", name)
            or name in {"authors", "license", "license.chromium"}):
        return "docs"
    if name in {"build.gn", "deps"} or lower.endswith(
        (".gni", ".gn", ".isolate", ".grd", ".grdp", ".xtb")
    ):
        return "build"
    if lower.endswith((".md", ".rst", ".adoc")):
        return "docs"
    if re.search(r"(?:^|/)(?:test|tests|testing)(?:/|$)", lower) or re.search(
        r"(?:_test|_unittest|_browsertest|_perf_test)\.[^.]+$", lower
    ):
        return "tests"
    if re.search(r"(?:^|/)(?:gen|generated)(?:/|$)", lower) or name.endswith(
        (".pb.cc", ".pb.h", ".mojom.cc", ".mojom.h")
    ):
        return "generated"
    return "production"


def parse_numstat(text: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added = int(parts[0]) if parts[0].isdigit() else 0
        deleted = int(parts[1]) if parts[1].isdigit() else 0
        # Rename records can use tab-separated old/new names or brace syntax.
        path = parts[-1]
        files.append(
            {
                "path": path,
                "class": classify_file(path),
                "added_lines": added,
                "deleted_lines": deleted,
                "changed_lines": added + deleted,
            }
        )
    return files


def signal_counts(paths: list[str], patch: str) -> dict[str, int]:
    searchable = "\n".join(paths) + "\n" + "\n".join(
        line[1:] for line in patch.splitlines() if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    )
    return {
        name: len(pattern.findall(searchable))
        for name, pattern in RISK_PATTERNS.items()
        if pattern.search(searchable)
    }


def specialist_triggers(paths: list[str], patch: str) -> list[dict[str, Any]]:
    searchable = "\n".join(paths) + "\n" + "\n".join(
        line[1:] for line in patch.splitlines() if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
    )
    triggered = []
    for prefix, roster_entry, pattern in SPECIALIST_PATTERNS:
        matches = pattern.findall(searchable)
        if matches:
            triggered.append({
                "prefix": prefix,
                "roster_entry": roster_entry,
                "match_count": len(matches),
            })
    return triggered


def hunk_metadata(patch: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    path = "unknown"
    for line in patch.splitlines():
        file_match = re.match(r"^(?:---|\+\+\+) (?:[ab]/)?(.*)$", line)
        if file_match and file_match.group(1) != "/dev/null":
            path = file_match.group(1)
            continue
        match = re.match(
            r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:\s*(.*))?$", line
        )
        if not match:
            continue
        output.append({
            "id": f"H{len(output) + 1:04d}",
            "path": path,
            "old_start": int(match.group(1)),
            "old_count": int(match.group(2) or "1"),
            "new_start": int(match.group(3)),
            "new_count": int(match.group(4) or "1"),
            "section": (match.group(5) or "").strip(),
        })
    return output


def external_context(review_dir: Path, revision: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "available": False,
        "count": 0,
        "references": [],
    }
    detail_path = review_dir / "detail.json"
    if not detail_path.is_file():
        return result
    detail = read_json_xssi(detail_path)
    if not isinstance(detail, dict) or not isinstance(detail.get("revisions"), dict):
        fail(f"{detail_path} has no revisions object")
    pinned = detail["revisions"].get(revision)
    if not isinstance(pinned, dict) or not isinstance(pinned.get("commit"), dict):
        return result
    message = pinned["commit"].get("message")
    if not isinstance(message, str):
        return result
    references: list[str] = []
    references.extend(re.findall(r"https?://[^\s<>()\[\]{}\"'`]+", message, re.I))
    references.extend(re.findall(
        r"(?<![A-Za-z0-9_.:/-])(?:crbug\.com/\d+|issues\.chromium\.org/issues/\d+|b/\d+)\b",
        message,
        re.I,
    ))
    for footer in re.findall(r"(?im)^\s*Bug:\s*(\S.*)$", message):
        if not re.match(r"(?i)^(?:none|n/a|not applicable)\s*$", footer):
            references.append(f"Bug: {footer.strip()}")
    for design in re.findall(r"(?im)^\s*Design(?:\s+doc)?:\s*(\S.*)$", message):
        if not re.match(r"(?i)^(?:none|n/a|not applicable)\s*$", design):
            references.append(f"Design: {design.strip()}")
    normalized = sorted({item.rstrip(".,;:") for item in references if item.strip()})
    result.update(available=True, count=len(normalized), references=normalized)
    return result


def prior_context(review_dir: Path, revision: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "normalized_threads_available": False,
        "total_threads": 0,
        "unresolved_threads": 0,
        "malformed_entries": 0,
        "prior_feedback_input_available": (review_dir / "prior-feedback-input.md").is_file(),
        "external_context": external_context(review_dir, revision),
    }
    normalized = review_dir / "gerrit" / "unresolved-threads.json"
    if normalized.is_file():
        value = read_json_xssi(normalized)
        if not isinstance(value, dict) or not isinstance(value.get("summary"), dict):
            fail(f"{normalized} has no summary object")
        summary = value["summary"]
        result.update(
            normalized_threads_available=True,
            total_threads=int(summary.get("total_threads", 0)),
            unresolved_threads=int(summary.get("unresolved_threads", 0)),
            malformed_entries=int(summary.get("malformed_entries", 0)),
        )
    elif (review_dir / "comments.json").is_file():
        comments = read_json_xssi(review_dir / "comments.json")
        if not isinstance(comments, dict):
            fail("comments.json must contain a path-to-comment-arrays object")
        result["published_comments"] = sum(
            len(entries) for entries in comments.values() if isinstance(entries, list)
        )
    return result


def choose_effort(
    files: list[dict[str, Any]], hunks: int, surfaces: int,
    signals: dict[str, int], context: dict[str, Any], diff_bytes: int,
    worker_budget: int,
) -> tuple[str, list[str], dict[str, Any]]:
    total_lines = sum(item["changed_lines"] for item in files)
    max_file_lines = max((item["changed_lines"] for item in files), default=0)
    classes = {item["class"] for item in files}
    large_reasons = []
    if len(files) > 40:
        large_reasons.append("more than 40 changed files")
    if total_lines > 4000:
        large_reasons.append("more than 4,000 changed lines")
    if hunks > 200:
        large_reasons.append("more than 200 diff hunks")
    if surfaces > 120:
        large_reasons.append("more than 120 approximate changed surfaces")
    if max_file_lines > 1500:
        large_reasons.append("a single file has more than 1,500 changed lines")
    if diff_bytes > worker_budget:
        large_reasons.append("the zero-context diff exceeds one worker input budget")
    if large_reasons:
        return "large", large_reasons, {"eligible": False, "proof": []}

    high_risk = sorted(HIGH_RISK_SIGNALS.intersection(signals))
    if high_risk:
        return "high-risk", [f"risk signal: {name}" for name in high_risk], {
            "eligible": False,
            "proof": [],
        }

    micro_proof = [
        len(files) <= 4,
        total_lines <= 120,
        hunks <= 12,
        surfaces <= 10,
        bool(files),
        classes.issubset({"docs", "metadata"}),
        not HIGH_RISK_SIGNALS.intersection(signals),
        context["unresolved_threads"] == 0,
        not context["prior_feedback_input_available"],
        context["malformed_entries"] == 0,
    ]
    proof_text = [
        "at most 4 changed files",
        "at most 120 changed lines",
        "at most 12 diff hunks",
        "at most 10 approximate changed surfaces",
        "at least one changed file",
        "all files are documentation or non-executable metadata",
        "no behavior-sensitive risk tokens in changed lines",
        "no unresolved Gerrit threads",
        "no supplied prior-review input",
        "no malformed normalized-comment entries",
    ]
    if all(micro_proof):
        return "micro", ["all conservative micro proofs passed"], {
            "eligible": True,
            "proof": proof_text,
        }
    failed = [text for passed, text in zip(micro_proof, proof_text) if not passed]
    return "standard", ["micro proof failed: " + reason for reason in failed], {
        "eligible": False,
        "proof": proof_text,
        "failed": failed,
    }


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def markdown(profile: dict[str, Any]) -> str:
    counts = profile["counts"]
    lines = [
        f"# Review profile — {profile['pin']['revision_sha'][:12]}",
        "",
        f"- Effort: **{profile['effort']}**",
        f"- Files / changed lines / hunks: {counts['files']} / {counts['changed_lines']} / {counts['hunks']}",
        f"- Approximate changed surfaces: {counts['approximate_changed_surfaces']}",
        f"- Unresolved / malformed comment threads: {profile['prior_context']['unresolved_threads']} / {profile['prior_context']['malformed_entries']}",
        f"- External context references / fast path: {profile['prior_context']['external_context']['count']} / {'eligible' if profile['context_fast_path_eligible'] else 'not eligible'}",
        "- Reasons: " + "; ".join(profile["effort_reasons"]),
        "",
        "## File classes",
        "",
        "| class | files | changed lines |",
        "| --- | ---: | ---: |",
    ]
    for name, values in sorted(profile["file_classes"].items()):
        lines.append(f"| {name} | {values['files']} | {values['changed_lines']} |")
    lines.extend(["", "## Escalation signals", ""])
    if profile["risk_signals"]:
        lines.extend(f"- {name}: {count}" for name, count in profile["risk_signals"].items())
    else:
        lines.append("- none detected by the deterministic token scan")
    lines.extend(["", "## Trigger-only specialist lenses", ""])
    if profile["specialist_triggers"]:
        lines.extend(
            f"- {item['prefix']} — {item['roster_entry']}: {item['match_count']} match(es)"
            for item in profile["specialist_triggers"]
        )
    else:
        lines.append("- none detected by the deterministic routing scan")
    lines.extend(["", "The profile selects orchestration effort; it does not prove code safety.", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--stdout", action="store_true", help="print JSON instead of writing profile files")
    parser.add_argument("--check", action="store_true", help="fail if profile.json/profile.md are absent or stale")
    parser.add_argument(
        "--context-window-tokens", type=int,
        help="known worker context capacity; budget 35%% using a conservative 4 UTF-8 bytes/token estimate",
    )
    args = parser.parse_args()
    if args.stdout and args.check:
        fail("--stdout and --check are mutually exclusive")
    review_dir = args.review_dir.resolve()
    if args.check and args.context_window_tokens is None and (review_dir / "profile.json").is_file():
        try:
            existing = json.loads((review_dir / "profile.json").read_text(encoding="utf-8"))
            saved_tokens = existing["context_budget"]["estimation"]["context_window_tokens"]
            if isinstance(saved_tokens, int) and saved_tokens > 0:
                args.context_window_tokens = saved_tokens
        except (OSError, KeyError, TypeError, json.JSONDecodeError):
            pass
    if args.context_window_tokens is not None and args.context_window_tokens <= 0:
        fail("--context-window-tokens must be positive")
    if args.context_window_tokens is None:
        worker_budget = 131072
        estimation = {
            "basis": "conservative default when worker context capacity is unknown",
            "context_window_tokens": None,
            "assumed_utf8_bytes_per_token": 4,
            "worker_input_fraction": 0.35,
        }
    else:
        worker_budget = int(args.context_window_tokens * 4 * 0.35)
        estimation = {
            "basis": "caller-supplied worker context capacity",
            "context_window_tokens": args.context_window_tokens,
            "assumed_utf8_bytes_per_token": 4,
            "worker_input_fraction": 0.35,
        }
    fields = pin_fields(review_dir / "pin.md")
    revision = fields.get("Revision SHA", "")
    parent = fields.get("Parent SHA", "")
    worktree_value = fields.get("Worktree", "")
    worktree = Path(worktree_value.split(" (", 1)[0]) if worktree_value else None
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
        fail("pin.md has no valid Revision SHA")
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", parent):
        fail("pin.md has no valid Parent SHA")
    if worktree is None or not worktree.is_dir():
        fail("pin.md has no existing Worktree")
    if run_git(worktree, "rev-parse", "HEAD").strip() != revision:
        fail("worktree HEAD does not match the pinned revision")

    files = parse_numstat(run_git(worktree, "diff", "--numstat", "--find-renames", parent, revision, "--"))
    patch = run_git(worktree, "diff", "--unified=0", "--find-renames", parent, revision, "--")
    hunk_map = hunk_metadata(patch)
    hunks = len(hunk_map)
    declaration_surfaces = len(SURFACE_RE.findall(patch))
    # A zero-context hunk is a stable lower-bound review surface even when a
    # declaration parser cannot recognize the language or macro syntax.
    surfaces = max(hunks, declaration_surfaces)
    signals = signal_counts([item["path"] for item in files], patch)
    triggers = specialist_triggers([item["path"] for item in files], patch)
    context = prior_context(review_dir, revision)
    effort, reasons, micro = choose_effort(
        files, hunks, surfaces, signals, context, len(patch.encode("utf-8")), worker_budget
    )
    classes: dict[str, dict[str, int]] = {}
    for name in sorted({item["class"] for item in files}):
        matching = [item for item in files if item["class"] == name]
        classes[name] = {
            "files": len(matching),
            "changed_lines": sum(item["changed_lines"] for item in matching),
        }
    profile = {
        "schema_version": 2,
        "effort": effort,
        "effort_reasons": reasons,
        "micro_eligibility": micro,
        "pin": {"revision_sha": revision, "parent_sha": parent, "worktree": str(worktree)},
        "counts": {
            "files": len(files),
            "added_lines": sum(item["added_lines"] for item in files),
            "deleted_lines": sum(item["deleted_lines"] for item in files),
            "changed_lines": sum(item["changed_lines"] for item in files),
            "hunks": hunks,
            "approximate_changed_surfaces": surfaces,
            "declaration_like_changed_surfaces": declaration_surfaces,
            "hunks_per_file": round(hunks / len(files), 3) if files else 0,
            "changed_lines_per_hunk": round(
                sum(item["changed_lines"] for item in files) / hunks, 3
            ) if hunks else 0,
            "max_changed_lines_in_one_file": max((item["changed_lines"] for item in files), default=0),
        },
        "file_classes": classes,
        "files": files,
        "hunks": hunk_map,
        "risk_signals": dict(sorted(signals.items())),
        "specialist_triggers": triggers,
        "prior_context": context,
        "context_fast_path_eligible": (
            effort == "micro"
            and context["external_context"]["available"]
            and context["external_context"]["count"] == 0
        ),
    }
    profile["context_budget"] = {
        "source": "fallback" if args.context_window_tokens is None else "reported",
        "reported_context_tokens": args.context_window_tokens,
        "input_fraction": 0.35,
        "worker_input_budget_bytes": worker_budget,
        "candidate_packet_budget_bytes": min(worker_budget, 16384, max(4096, worker_budget // 8)),
        "evidence_card_budget_bytes": min(worker_budget, 32768, max(8192, worker_budget // 4)),
        "estimation": estimation,
    }
    encoded = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    if args.stdout:
        sys.stdout.write(encoded)
    elif args.check:
        expected = {review_dir / "profile.json": encoded, review_dir / "profile.md": markdown(profile)}
        stale = []
        for path, content in expected.items():
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(path.name)
        if stale:
            fail("missing or stale output: " + ", ".join(stale))
        print(f"current: {review_dir / 'profile.json'}; {review_dir / 'profile.md'}")
    else:
        atomic_write(review_dir / "profile.json", encoded)
        atomic_write(review_dir / "profile.md", markdown(profile))
        print(f"{effort}: {review_dir / 'profile.json'}; {review_dir / 'profile.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
