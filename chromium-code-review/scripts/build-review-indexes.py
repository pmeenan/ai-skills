#!/usr/bin/env python3
"""Build compact deterministic TSV indexes from Chromium review artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from artifact_tables import effective_tables


ROW_ID_RE = re.compile(r"(?:[A-Z][A-Z0-9]*-\d+|R\d+-RC\d+-\d+)")

def fail(message: str) -> "NoReturn":
    raise SystemExit(f"build-review-indexes.py: {message}")


def tables(
    text: str, source: str = "input"
) -> Iterable[tuple[str, list[str], list[dict[str, str]]]]:
    parsed, errors = effective_tables(text, source)
    if errors:
        fail("; ".join(errors))
    yield from parsed


def clean(value: str, limit: int = 600) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def citations(value: str) -> str:
    found = re.findall(r"(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+:\d+(?:-\d+)?", value)
    found.extend(re.findall(
        r"(?:[A-Za-z0-9_.+-]+/)*[A-Za-z0-9_.+-]+\.(?:json|md):/"
        r"[A-Za-z0-9_./~-]+",
        value,
    ))
    return ",".join(dict.fromkeys(found))


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        fail(f"cannot read {path}: {error}")


def inventory_rows(root: Path) -> list[list[str]]:
    paths = []
    if (root / "inventory.md").is_file():
        paths.append(root / "inventory.md")
    paths.extend(sorted((root / "inventory").glob("*.md")) if (root / "inventory").is_dir() else [])
    output: list[list[str]] = []
    seen_ids: dict[str, str] = {}

    def claim(identifier: str, source: Path) -> None:
        if not identifier:
            fail(f"missing inventory ID in {relative(source, root)}")
        previous = seen_ids.get(identifier)
        if previous is not None:
            fail(
                f"duplicate inventory ID {identifier} in {previous} and "
                f"{relative(source, root)}"
            )
        seen_ids[identifier] = relative(source, root)

    hunk_owners: dict[str, Path] = {}
    profile_hunk_paths: dict[str, str] = {}
    profile_path = root / "profile.json"
    if profile_path.is_file():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            for item in profile.get("hunks", []):
                if isinstance(item, dict) and item.get("id"):
                    profile_hunk_paths[item["id"]] = item.get("path", "")
        except (OSError, ValueError):
            profile_hunk_paths = {}
    for path in paths:
        surface_number = 0
        shard = re.sub(r"[^A-Za-z0-9]+", "-", path.stem).strip("-").upper()
        for heading, header, rows in tables(read(path), relative(path, root)):
            for row in rows:
                if heading == "Changed surfaces" and "surface" in header:
                    surface_number += 1
                    explicit_id = row.get("surface id", row.get("id", ""))
                    surface_id = clean(explicit_id) or (
                        f"S{surface_number:04d}" if path.name == "inventory.md"
                        else f"S{shard}-{surface_number:04d}"
                    )
                    claim(surface_id, path)
                    hunk_cell = row.get(
                        "owned hunks / earliest changed line", "")
                    claimed: list[str] = []
                    for match_ in re.finditer(
                            r"\bH(\d+)(?:\s*-\s*H?(\d+))?\b", hunk_cell):
                        width = len(match_.group(1))
                        first = int(match_.group(1))
                        last = int(match_.group(2) or match_.group(1))
                        if last < first:
                            fail(
                                f"{relative(path, root)}: descending hunk "
                                f"range '{match_.group(0)}'")
                        if profile_hunk_paths:
                            for endpoint in (
                                    f"H{first:0{width}d}",
                                    f"H{last:0{width}d}"):
                                if endpoint not in profile_hunk_paths:
                                    fail(
                                        f"{relative(path, root)}: hunk range "
                                        f"endpoint {endpoint} is not in "
                                        "profile.json")
                        elif last - first + 1 > 5000:
                            fail(
                                f"{relative(path, root)}: implausible hunk "
                                f"range '{match_.group(0)}'")
                        claimed.extend(
                            f"H{value:0{width}d}"
                            for value in range(first, last + 1))
                    locations = re.findall(
                        r"/\s*([A-Za-z0-9_.+@{}\-/]+):\d+", hunk_cell)
                    if claimed and profile_hunk_paths and len(locations) != 1:
                        fail(
                            f"{relative(path, root)}: surface {surface_id} must "
                            "name exactly one full repo-relative path after '/' "
                            "in its owned-hunks cell"
                        )
                    cell_file = locations[0] if len(locations) == 1 else None
                    for hunk_id in claimed:
                        owner = hunk_owners.setdefault(hunk_id, path)
                        if owner != path:
                            fail(
                                f"hunk {hunk_id} is claimed by both "
                                f"{relative(owner, root)} and "
                                f"{relative(path, root)}; shard hunk "
                                "ownership must be disjoint")
                        expected_file = profile_hunk_paths.get(hunk_id)
                        if expected_file and cell_file != expected_file:
                            fail(
                                f"{relative(path, root)}: hunk {hunk_id} "
                                f"belongs to {expected_file} but the surface "
                                f"row cites {cell_file or 'no full path'}")
                    subject = clean(row.get("surface", ""))
                    tags = clean(row.get("reachability", ""))
                    if subject.lower().startswith("group:"):
                        count = re.match(r"group:\s*(\d+)\b", subject,
                                         re.IGNORECASE)
                        if not count:
                            fail(
                                f"{relative(path, root)}: group surface "
                                f"'{subject}' lacks a leading member count "
                                "(shape: 'group: <N> ...')")
                        hunks = clean(row.get(
                            "owned hunks / earliest changed line", ""))
                        extra = ";".join(part for part in (
                            f"members={count.group(1)}",
                            f"hunks={hunks}" if hunks else "",
                        ) if part)
                        tags = f"{tags};{extra}" if tags else extra
                    output.append([
                        "surface", surface_id, subject, clean(row.get("scope label", "")),
                        tags, citations(row.get("surface", "") + " " + row.get("contract source", "")),
                        relative(path, root),
                    ])
                elif heading == "Risk-area map" and "file" in header:
                    output.append([
                        "risk", "", clean(row.get("file", "")), "", clean(row.get("risk areas", "")),
                        citations(row.get("file", "")), relative(path, root),
                    ])
                elif heading == "Trigger inventory" and "scope id" in header:
                    trigger_id = clean(row.get("scope id", "")).upper()
                    claim(trigger_id, path)
                    root_trigger = clean(row.get("root-cause trigger", ""))
                    explicit_required = clean(row.get("root-cause required", ""))
                    required = explicit_required or (
                        "yes" if re.match(r"(?i)^required\b", root_trigger) else "no"
                    )
                    output.append([
                        "trigger", trigger_id, clean(row.get("surface", "")),
                        root_trigger,
                        clean(row.get("discovery triggers", "")) + f",root-cause-required={required}",
                        citations(row.get("evidence", "")), relative(path, root),
                    ])
    if profile_hunk_paths:
        for hunk_id in sorted(set(hunk_owners) - set(profile_hunk_paths)):
            fail(f"inventory claims unknown hunk {hunk_id} absent from "
                 "profile.json")
        sharded = [item for item in paths if item.parent.name == "inventory"]
        if len(sharded) > 1:
            for hunk_id in sorted(set(profile_hunk_paths) - set(hunk_owners)):
                fail(f"sharded inventory leaves hunk {hunk_id} with no "
                     "owning surface row")
    return sorted(output, key=lambda row: (row[0], row[1], row[2], row[-1]))


def candidate_rows(root: Path) -> list[list[str]]:
    paths = sorted((root / "ledger").glob("**/*.md")) if (root / "ledger").is_dir() else []
    if (root / "collection.md").is_file():
        paths.append(root / "collection.md")
    output: list[list[str]] = []
    seen: dict[str, str] = {}
    for path in paths:
        parsed = list(tables(read(path), relative(path, root)))
        amendments: dict[str, dict[str, str]] = {}
        for heading, header, rows in parsed:
            if heading == "Amendments" and {"amendment", "target", "operation"}.issubset(header):
                for row in rows:
                    amendments[row.get("target", "")] = row
        for heading, header, rows in parsed:
            candidate_table = heading == "Candidate rows" or (
                path.name == "collection.md" and {"id", "claim", "status"}.issubset(header)
            )
            if not candidate_table:
                continue
            for row in rows:
                identifier = clean(row.get("id", ""))
                if not identifier:
                    continue
                row_status = row.get("status", "").lower()
                if not any(
                    marker in row_status for marker in ("candidate", "reopened")
                ):
                    continue
                source = relative(path, root)
                if identifier in seen:
                    fail(f"duplicate candidate ID {identifier} in {seen[identifier]} and {source}")
                seen[identifier] = source
                evidence = row.get("evidence / hypothesis", "")
                status = row.get("status", "")
                amendment = amendments.get(identifier)
                if amendment:
                    replacement = amendment.get("replacement / reason", "")
                    evidence = (
                        f"[effective amendment {amendment.get('amendment', '')} "
                        f"{amendment.get('operation', '')}] {replacement}; original: {evidence}"
                    )
                    status = f"{amendment.get('operation', '')} by {amendment.get('amendment', '')}"
                    amendment_evidence = amendment.get("evidence", "")
                else:
                    amendment_evidence = ""
                output.append([
                    identifier, clean(row.get("claim", "")), clean(row.get("location", "")),
                    clean(row.get("origin", "")), clean(row.get("severity", "")),
                    clean(status), citations(evidence + " " + amendment_evidence), clean(evidence), source,
                ])
    return sorted(output, key=lambda row: row[0])


def verdict_rows(root: Path) -> list[list[str]]:
    paths = [p for p in (sorted((root / "verification").glob("V*.md")) if (root / "verification").is_dir() else []) if p.name != "VTER.md"]
    output: list[list[str]] = []
    seen: dict[str, str] = {}
    for path in paths:
        if path.name == "batches.md":
            continue
        for _, header, rows in tables(read(path), relative(path, root)):
            if not {"id", "candidate", "verdict"}.issubset(header):
                continue
            for row in rows:
                identifier = clean(row.get("id", ""))
                if not identifier:
                    continue
                source = relative(path, root)
                if identifier in seen:
                    fail(f"duplicate verdict ID {identifier} in {seen[identifier]} and {source}")
                seen[identifier] = source
                evidence = row.get("evidence", "")
                output.append([
                    identifier, clean(row.get("candidate", "")), clean(row.get("verdict", "")),
                    clean(row.get("severity (anchor)", row.get("severity", ""))),
                    clean(row.get("origin", "")), citations(evidence), clean(evidence), source,
                ])
    return sorted(output, key=lambda row: row[0])


def reconciliation_rows(root: Path) -> list[list[str]]:
    records: dict[str, dict[str, object]] = {}
    amendments: dict[str, str] = {}

    def add(identifier: str, kind: str, source: Path, links: Iterable[str] = ()) -> None:
        identifier = clean(identifier)
        if not ROW_ID_RE.fullmatch(identifier):
            return
        source_name = relative(source, root)
        existing = records.get(identifier)
        if existing and existing["source"] != source_name:
            fail(f"duplicate canonical row {identifier} in {existing['source']} and {source_name}")
        if existing is None:
            records[identifier] = {"kind": kind, "source": source_name, "links": set()}
        elif kind == "candidate":
            existing["kind"] = kind
        records[identifier]["links"].update(link for link in links if ROW_ID_RE.fullmatch(link))

    ledger_paths = sorted((root / "ledger").glob("**/*.md")) if (root / "ledger").is_dir() else []
    if (root / "collection.md").is_file():
        ledger_paths.append(root / "collection.md")
    for path in ledger_paths:
        parsed = list(tables(read(path), relative(path, root)))
        for heading, header, rows in parsed:
            if heading == "Amendments" and {"amendment", "target", "operation"}.issubset(header):
                for row in rows:
                    target = row.get("target", "")
                    if ROW_ID_RE.fullmatch(target):
                        amendments[target] = f"{row.get('amendment', '')}:{row.get('operation', '')}"
            if heading not in {"Prior-feedback rows", "Candidate rows", "Per-file floor"}:
                continue
            if "id" not in header:
                continue
            for row in rows:
                identifier = row.get("id", "")
                kind = "candidate" if heading != "Prior-feedback rows" else "prior-feedback"
                parent_links = ROW_ID_RE.findall(row.get("parent rows", ""))
                add(identifier, kind, path, parent_links)

    verification = root / "verification"
    for path in [p for p in (sorted(verification.glob("V*.md")) if verification.is_dir() else []) if p.name != "VTER.md"]:
        for heading, header, rows in tables(read(path), relative(path, root)):
            if heading == "Amendments" and {"amendment", "target", "operation"}.issubset(header):
                for row in rows:
                    target = row.get("target", "")
                    if ROW_ID_RE.fullmatch(target):
                        amendments[target] = f"{row.get('amendment', '')}:{row.get('operation', '')}"
            if not {"id", "candidate", "verdict"}.issubset(header):
                continue
            for row in rows:
                identifier = row.get("id", "")
                candidate = row.get("candidate", "")
                add(identifier, "verdict", path, [candidate])
                if identifier in records and candidate in records:
                    records[candidate]["links"].add(identifier)

    root_cause = root / "root-cause"
    for path in sorted(root_cause.glob("RC*.md")) if root_cause.is_dir() else []:
        text = read(path)
        for heading, header, rows in tables(text, relative(path, root)):
            if heading == "Amendments" and {"amendment", "target", "operation"}.issubset(header):
                for row in rows:
                    target = row.get("target", "")
                    if ROW_ID_RE.fullmatch(target):
                        amendments[target] = f"{row.get('amendment', '')}:{row.get('operation', '')}"
        for match in re.finditer(r"^##\s+(RC\d+-\d+)\b([^\n]*)", text, re.MULTILINE):
            identifier = match.group(1)
            links = ROW_ID_RE.findall(match.group(2))
            add(identifier, "root-cause", path, links)
            for link in links:
                if link in records:
                    records[link]["links"].add(identifier)

    dispositions: dict[str, str] = {}
    batches = root / "verification" / "batches.md"
    if batches.is_file():
        merged_rows: set[str] = set()
        for heading, header, rows in tables(read(batches), relative(batches, root)):
            if not heading.startswith("Merge proposals") or not {"row", "proposal"}.issubset(header):
                continue
            for row in rows:
                merged = row.get("row", "")
                match = re.match(rf"(?i)^merge-into\s+({ROW_ID_RE.pattern})\b", row.get("proposal", ""))
                if not ROW_ID_RE.fullmatch(merged) or not match:
                    fail(f"{relative(batches, root)}: malformed merge proposal for '{merged}'")
                survivor = match.group(1)
                if merged in merged_rows:
                    fail(f"{relative(batches, root)}: duplicate merge proposal for {merged}")
                if merged not in records or survivor not in records:
                    fail(
                        f"{relative(batches, root)}: merge proposal {merged} -> {survivor} "
                        "references an unknown canonical row"
                    )
                merged_rows.add(merged)
                records[merged]["links"].add(survivor)
                records[survivor]["links"].add(merged)

    reconciliation = root / "reconciliation.md"
    if reconciliation.is_file():
        for _, header, rows in tables(read(reconciliation), relative(reconciliation, root)):
            if not {"row", "disposition"}.issubset(header):
                continue
            for row in rows:
                identifier = row.get("row", "")
                if identifier in dispositions:
                    fail(f"duplicate reconciliation row {identifier}")
                dispositions[identifier] = clean(row.get("disposition", ""))

    # Reopened-parent and candidate/verdict/root-cause relationships are
    # bidirectional so partitioners can compute whole connected closures.
    for identifier, record in list(records.items()):
        for link in list(record["links"]):
            if link in records:
                records[link]["links"].add(identifier)
    for identifier, disposition in dispositions.items():
        if identifier not in records:
            continue
        for link in ROW_ID_RE.findall(disposition):
            if link in records and link != identifier:
                records[identifier]["links"].add(link)
                records[link]["links"].add(identifier)

    return [
        [
            identifier,
            str(record["kind"]),
            str(record["source"]),
            amendments.get(identifier, "-"),
            ",".join(sorted(record["links"])) or "-",
            dispositions.get(identifier, "pending") or "pending",
        ]
        for identifier, record in sorted(records.items())
    ]


def encode(header: list[str], rows: list[list[str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue()


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


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def source_paths(root: Path) -> dict[str, list[Path]]:
    inventory = ([root / "inventory.md"] if (root / "inventory.md").is_file() else [])
    inventory += sorted((root / "inventory").glob("*.md")) if (root / "inventory").is_dir() else []
    if (root / "profile.json").is_file():
        inventory.append(root / "profile.json")
    candidates = sorted((root / "ledger").glob("**/*.md")) if (root / "ledger").is_dir() else []
    if (root / "collection.md").is_file():
        candidates.append(root / "collection.md")
    verdicts = [p for p in (sorted((root / "verification").glob("V*.md")) if (root / "verification").is_dir() else []) if p.name != "VTER.md"]
    reconciliation = sorted({*candidates, *verdicts})
    reconciliation += sorted((root / "root-cause").glob("RC*.md")) if (root / "root-cause").is_dir() else []
    batches = root / "verification" / "batches.md"
    if batches.is_file():
        reconciliation.append(batches)
    if (root / "reconciliation.md").is_file():
        reconciliation.append(root / "reconciliation.md")
    return {
        "inventory.tsv": inventory,
        "candidates.tsv": candidates,
        "verdicts.tsv": verdicts,
        "reconciliation.tsv": reconciliation,
    }


def manifest(root: Path, payloads: dict[str, str], sources: dict[str, list[Path]]) -> str:
    indexes = {}
    for name, content in payloads.items():
        encoded = content.encode("utf-8")
        indexes[name] = {
            "output_sha256": digest(encoded),
            "row_count": max(0, content.count("\n") - 1),
            "sources": [
                {
                    "path": relative(path, root),
                    "bytes": path.stat().st_size,
                    "sha256": digest(path.read_bytes()),
                }
                for path in sources[name]
            ],
        }
    return json.dumps({"schema_version": 1, "indexes": indexes}, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, help="default: REVIEW_DIR/indexes")
    parser.add_argument("--check", action="store_true", help="fail if any index or source fingerprint is stale")
    args = parser.parse_args()
    root = args.review_dir.resolve()
    if not root.is_dir():
        fail(f"review directory does not exist: {root}")
    destination = args.output_dir.resolve() if args.output_dir else root / "indexes"
    payloads = {
        "inventory.tsv": encode(
            ["kind", "id", "subject", "scope", "tags", "citations", "source"], inventory_rows(root)
        ),
        "candidates.tsv": encode(
            ["id", "claim", "location", "origin", "severity", "status", "citations", "evidence_excerpt", "source"],
            candidate_rows(root),
        ),
        "verdicts.tsv": encode(
            ["id", "candidate", "verdict", "severity", "origin", "citations", "evidence_excerpt", "source"],
            verdict_rows(root),
        ),
        "reconciliation.tsv": encode(
            ["row", "kind", "source", "effective_amendment", "links", "disposition_state"],
            reconciliation_rows(root),
        ),
    }
    manifest_content = manifest(root, payloads, source_paths(root))
    expected = {**payloads, "manifest.json": manifest_content}
    if args.check:
        stale = [
            name for name, content in expected.items()
            if not (destination / name).is_file()
            or (destination / name).read_text(encoding="utf-8") != content
        ]
        if stale:
            fail("missing or stale output: " + ", ".join(stale))
        print(f"current: {destination}")
        return 0
    for name, content in expected.items():
        atomic_write(destination / name, content)
    counts = ", ".join(f"{name}={content.count(chr(10)) - 1}" for name, content in payloads.items())
    print(f"{destination}: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
