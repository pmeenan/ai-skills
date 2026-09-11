#!/usr/bin/env python3
"""Reduce redundancy-probe rows into the evidence packet a proposal must cite.

A Layer 1 claim ("this subtree can be skipped when condition C holds") and a
Layer 2 claim ("this result is recomputed for inputs already seen") are only
as good as two measured numbers: how often the site runs per benchmark step
and how often C holds or the input repeats. `redundancy_probe.h` counts both
inside the exact scored window; this tool turns the browser log rows into a
digest-bound packet. `campaign.py decompose` binds that packet to the
proposal and refuses an estimated avoidable fraction the counts do not
support.

Usage:
  python3 redundancy_evidence.py --site style/resolve-style \\
      --target-story TodoMVC-React --browser-log <cb browser log> [...] \\
      --out <packet.json>
"""
import argparse
import hashlib
import json
import pathlib
import statistics
import sys

ROW_PREFIX = "[SP3_REDUNDANCY_ROW] "
SCHEMA_VERSION = 1


class RedundancyError(ValueError):
    pass


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


_ROWS_CACHE: dict = {}


def parse_rows(path: pathlib.Path) -> list[dict]:
    """Rows of one browser log; parsed once per (path, size, mtime) so the
    gate can re-derive every packet on a build without re-reading the log
    hundreds of times."""
    try:
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    except OSError:
        cache_key = None
    if cache_key is not None and cache_key in _ROWS_CACHE:
        return _ROWS_CACHE[cache_key]
    rows = _parse_rows_uncached(path)
    if cache_key is not None:
        _ROWS_CACHE[cache_key] = rows
    return rows


def _parse_rows_uncached(path: pathlib.Path) -> list[dict]:
    rows = []
    with path.open(errors="replace") as source:
        for line in source:
            index = line.find(ROW_PREFIX)
            if index < 0:
                continue
            try:
                row = json.loads(line[index + len(ROW_PREFIX):])
            except json.JSONDecodeError as exc:
                raise RedundancyError(f"{path}: malformed redundancy row: {exc}") from exc
            if row.get("schema_version") != SCHEMA_VERSION:
                raise RedundancyError(f"{path}: unsupported redundancy row schema")
            for field in ("site", "group", "calls", "applicable_calls",
                          "distinct_inputs", "repeated_inputs", "overflow"):
                if field not in row:
                    raise RedundancyError(f"{path}: redundancy row lacks {field}")
            rows.append(row)
    return rows


def story_of(group: str) -> str:
    return group.rsplit("|", 1)[1] if "|" in group else group


def reduce_rows(rows: list[dict], site: str, target_story: str) -> dict:
    selected = [
        row for row in rows
        if row["site"] == site and story_of(row["group"]) == target_story
    ]
    if not selected:
        raise RedundancyError(
            f"no rows for site {site!r} in story {target_story!r}; the probe "
            "did not run inside that story's scored window"
        )
    violations = sum(int(row.get("thread_affinity_violations", 0)) for row in selected)
    if violations:
        raise RedundancyError("redundancy counter was touched from another thread")
    calls = [int(row["calls"]) for row in selected]
    timed = [int(row.get("timed_calls", 0)) for row in selected]
    total_ns = [int(row.get("total_ns", 0)) for row in selected]
    applicable_ns = [int(row.get("applicable_ns", 0)) for row in selected]
    repeated_ns = [int(row.get("repeated_ns", 0)) for row in selected]
    applicable = [int(row["applicable_calls"]) for row in selected]
    distinct = [int(row["distinct_inputs"]) for row in selected]
    repeated = [int(row["repeated_inputs"]) for row in selected]
    overflow = any(int(row["overflow"]) for row in selected)
    total_calls = sum(calls)
    if total_calls == 0:
        raise RedundancyError(f"site {site!r} never ran inside {target_story!r}'s scored window")
    # Time-weighted only when every call in every repetition was recorded
    # through a scope; a mixed row would weight some calls and not others.
    time_weighted = sum(timed) == total_calls and sum(total_ns) > 0
    ns_total = sum(total_ns)
    # One packet, one binary: rows from two builds of the twin are two
    # measurements, not one.
    build_ids = {row.get("build_id") for row in selected if row.get("build_id")}
    if len(build_ids) > 1:
        raise RedundancyError(
            f"site {site!r} in {target_story!r} was logged by more than one build "
            f"({sorted(build_ids)}); reduce one build's log at a time"
        )
    build_id = next(iter(build_ids)) if build_ids else None
    if build_id == "unknown":
        build_id = None
    timing = "exclusive" if all(row.get("timing") == "exclusive" for row in selected) else None
    nested = [int(row["nested_calls"]) for row in selected if "nested_calls" in row]
    return {
        "site": site,
        "target_story": target_story,
        "repetitions": len(selected),
        "build_id": build_id,
        "timing": timing,
        "nested_calls_fraction": (sum(nested) / total_calls) if len(nested) == len(selected) else None,
        "time_weighted": time_weighted,
        "total_ns_per_repetition_mean": statistics.fmean(total_ns) if time_weighted else None,
        "applicable_time_fraction": sum(applicable_ns) / ns_total if time_weighted else None,
        "repeat_time_fraction": sum(repeated_ns) / ns_total if time_weighted else None,
        "calls_total": total_calls,
        "calls_per_repetition_mean": statistics.fmean(calls),
        "calls_per_repetition_min": min(calls),
        "calls_per_repetition_max": max(calls),
        "applicable_fraction": sum(applicable) / total_calls,
        "repeat_fraction": sum(repeated) / total_calls,
        "distinct_inputs_mean": statistics.fmean(distinct),
        "distinct_overflow": overflow,
        "measured_avoidable_fraction_upper": (
            None if overflow else max(sum(applicable), sum(repeated)) / total_calls
        ),
        "groups": [row["group"] for row in selected],
    }


def build_packet(logs: list[pathlib.Path], site: str, target_story: str,
                 probe_symbol: str | None = None, patch: pathlib.Path | None = None,
                 scope_symbol: str | None = None) -> dict:
    """`probe_symbol` is the demangled function the RedundancyCounter sits in
    (a frame prefix as it appears in profile.collapsed); the gate uses it to
    check that the packet measured the row it is bound to. `patch` is the
    saved instrumentation diff the twin was built from. `scope_symbol` names
    the function the scope is actually in when that function has no frame
    of its own in the profile (an inlined callee): the packet then names the
    enclosing frame as `probe_symbol` and the gate scales its bound by the
    fraction of that frame's time the scope covers."""
    rows = []
    sources = []
    for path in logs:
        if not path.is_file():
            raise RedundancyError(f"browser log not found: {path}")
        rows.extend(parse_rows(path))
        sources.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    summary = reduce_rows(rows, site, target_story)
    packet = {
        "schema_version": SCHEMA_VERSION,
        "kind": "redundancy-evidence",
        "sources": sources,
        "rows_total": len(rows),
        **summary,
    }
    if probe_symbol:
        packet["probe_symbol"] = probe_symbol
    if scope_symbol:
        packet["scope_symbol"] = scope_symbol
    if patch is not None:
        if not patch.is_file():
            raise RedundancyError(f"probe patch not found: {patch}")
        packet["patch"] = str(patch)
        packet["patch_sha256"] = sha256_file(patch)
    return packet


def load_packet(path: pathlib.Path) -> dict:
    try:
        packet = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RedundancyError(f"cannot read redundancy packet {path}: {exc}") from exc
    if not isinstance(packet, dict) or packet.get("kind") != "redundancy-evidence":
        raise RedundancyError(f"{path} is not a redundancy evidence packet")
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise RedundancyError(f"{path}: unsupported packet schema")
    for field in ("site", "target_story", "calls_total", "applicable_fraction",
                  "repeat_fraction", "distinct_overflow", "sources"):
        if field not in packet:
            raise RedundancyError(f"{path}: packet lacks {field}")
    return packet


def supported_avoidable_fraction(packet: dict) -> float | None:
    """Largest avoidable fraction the packet can support. A time-weighted
    packet bounds avoidable *time*: the greater of its applicable and repeat
    time fractions (a call fraction says nothing about time once time is
    measured). A count-only packet falls back to the call fractions."""
    if float(packet.get("applicable_fraction") or 0.0) >= 0.999:
        rep = float(packet["repeat_time_fraction"]) if packet.get("time_weighted") and packet.get("repeat_time_fraction") is not None else float(packet.get("repeat_fraction") or 0.0)
        if rep > 0.0:
            return rep
        return 1.0
    if packet.get("time_weighted"):
        if packet.get("distinct_overflow"):
            return float(packet["applicable_time_fraction"])
        return max(float(packet["applicable_time_fraction"]),
                   float(packet["repeat_time_fraction"]))
    if packet.get("distinct_overflow"):
        return float(packet["applicable_fraction"])
    return max(float(packet["applicable_fraction"]), float(packet["repeat_fraction"]))


def hypothesis_bound(packet: dict, hypothesis: str) -> float | None:
    """What a candidate may claim under one hypothesis: its time-weighted
    fraction (the same bound `decompose` applies to a novel/known row), or
    None when the packet carries no time."""
    if not packet.get("time_weighted"):
        return None
    # The bound is the hypothesis's *time* fraction, the same number a
    # candidate row may claim under the gate (a call fraction says nothing
    # about time once time is measured).
    if hypothesis == "repeat":
        return float(packet["repeat_time_fraction"])
    return float(packet["applicable_time_fraction"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", required=True, help="probe site name as passed to RedundancyCounter")
    parser.add_argument("--target-story", required=True)
    parser.add_argument("--browser-log", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument(
        "--symbol", required=True,
        help="demangled function the counter sits in, as a profile.collapsed frame prefix "
             "(e.g. 'blink::InlineNode::ShapeText('); the gate checks it shares samples with the row it closes",
    )
    parser.add_argument("--patch", type=pathlib.Path, default=None,
                        help="saved instrumentation diff the twin was built from (recorded with its sha256)")
    parser.add_argument("--scope-symbol", default=None,
                        help="the function the scope is in when it is not --symbol: an inlined "
                             "callee with no frame of its own (e.g. blink::OutOfFlowLayoutPart::LayoutOOFNode "
                             "under --symbol blink::OutOfFlowLayoutPart::Run); the gate checks the patch "
                             "places the counter in it and scales the packet's bound by its coverage")
    args = parser.parse_args(argv)
    try:
        packet = build_packet(args.browser_log, args.site, args.target_story,
                              probe_symbol=args.symbol, patch=args.patch,
                              scope_symbol=args.scope_symbol)
    except RedundancyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "site": packet["site"], "target_story": packet["target_story"],
        "calls_per_repetition_mean": packet["calls_per_repetition_mean"],
        "applicable_fraction": packet["applicable_fraction"],
        "repeat_fraction": packet["repeat_fraction"],
        "applicable_time_fraction": packet.get("applicable_time_fraction"),
        "repeat_time_fraction": packet.get("repeat_time_fraction"),
        "distinct_overflow": packet["distinct_overflow"],
        "build_id": packet.get("build_id"),
        "timing": packet.get("timing"),
        "out": str(args.out),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
