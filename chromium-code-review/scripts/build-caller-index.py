#!/usr/bin/env python3
"""Precompute one caller search per inventory surface symbol.

Discovery threads repeatedly run the same symbol searches over the same
worktree — every thread that traces a surface re-greps its callers. This
helper runs each search exactly once after inventory collection and writes
the complete results to `callers/<symbol>.txt` plus a `callers/index.tsv`
routing table (surface ID → symbol → hits → scope → file). Threads consult
the index and open only the per-symbol files their tracing needs; they
re-search only when a symbol is absent here or a narrower/different scope is
required. Results are worktree-derived evidence like any other code read —
consulting them is optional and never substitutes for reading the call sites
a lens must actually trace.

**Search scope defaults to the whole repository** so caller-reachability
reasoning can trust the results — callers of a changed API routinely live
outside the changed directories. Passing `--pathspec` narrows the search;
every result file and index row then records that scope explicitly and is
marked scope-limited, so no worker can mistake a narrowed search for
repository-wide completeness.

Re-runs are memoized crash-safely: results are written atomically, and an
existing file is reused only when its header records the same scope and
pinned revision AND its body line count matches its declared hit count — a
truncated, stale, or foreign cache entry is rebuilt, never trusted.

Symbols come mechanically from `indexes/inventory.tsv` surface rows (the last
`::` component of the subject). Group rows and unsearchable subjects are
recorded as skipped with a reason, never silently dropped.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys

IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
MIN_LENGTH = 3
REPO_WIDE = "repository-wide"


def fail(message: str) -> None:
    print(f"build-caller-index.py: ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        fail(f"missing {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        fail(f"empty {path}")
    header = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        if line.strip():
            cells = line.split("\t")
            rows.append(dict(zip(header, cells + [""] * (len(header) - len(cells)))))
    return rows


def symbol_for(subject: str) -> tuple[str, str]:
    """Return (symbol, skip_reason); exactly one is non-empty."""
    subject = subject.strip()
    if not subject:
        return "", "empty subject"
    if subject.lower().startswith("group:"):
        return "", "aggregated group row — caller search is banned by the " \
                   "inventory aggregation rule"
    tail = subject.split("::")[-1]
    match = IDENTIFIER.search(tail)
    if not match:
        return "", f"no searchable identifier in '{subject}'"
    symbol = match.group(0)
    if symbol == "operator":
        return "", f"operator overload '{subject}' — search manually"
    if len(symbol) < MIN_LENGTH:
        return "", f"symbol '{symbol}' too short to search meaningfully"
    return symbol, ""


def scope_label(pathspecs: list[str]) -> str:
    return " ".join(pathspecs) if pathspecs else REPO_WIDE


HEADER_LINES = 3


def result_header(symbol: str, hits: int, scope: str,
                  revision: str) -> list[str]:
    lines = [
        f"# Callers of `{symbol}` — git grep -I -n -w — scope: {scope} — "
        f"revision: {revision}",
        f"# {hits} hit(s).",
    ]
    if scope != REPO_WIDE:
        lines.append(
            "# SCOPE-LIMITED: callers outside the scope above are NOT "
            "included. Widen the search yourself before relying on this "
            "for caller-reachability or closure proofs.")
    else:
        lines.append("# Repository-wide and uncapped.")
    return lines


def reusable_hits(target: Path, scope: str, revision: str) -> int | None:
    """Return the cached hit count only if the cache entry is provably
    intact: same scope, same pinned revision, and a body whose line count
    matches the declared hit count. Anything else forces a re-search."""
    if not target.is_file():
        return None
    lines = target.read_text(encoding="utf-8").splitlines()
    if len(lines) < HEADER_LINES:
        return None
    if not lines[0].endswith(f"scope: {scope} — revision: {revision}"):
        return None
    declared = re.fullmatch(r"# (\d+) hit\(s\)\.", lines[1])
    if not declared:
        return None
    hits = int(declared.group(1))
    if len(lines) - HEADER_LINES != hits:
        return None
    return hits


LIFETIME_MEMBER_RE = re.compile(
    r"\b(raw_ptr|raw_ref|WeakPtrFactory|WeakPtr|Receiver|Remote|"
    r"AssociatedReceiver|AssociatedRemote|ReceiverSet|RemoteSet|"
    r"OneShotTimer|RepeatingTimer|RetainingOneShotTimer|DeadlineTimer|"
    r"ScopedObservation|ObserverList|SequenceChecker|ThreadChecker|"
    r"OnceCallback|RepeatingCallback|OnceClosure|RepeatingClosure|"
    r"Member|WeakMember|HeapVector|HeapHashMap|Persistent)\b"
)
ASYNC_BIND_RE = re.compile(
    r"\b(BindOnce|BindRepeating|PostTask|PostDelayedTask|"
    r"PostTaskAndReply|PostTaskAndReplyWithResult|"
    r"set_disconnect_handler|set_disconnect_with_reason_handler|"
    r"Start\s*\()\b"
)
CALLBACK_RUN_RE = re.compile(
    r"(std::move\s*\([^)]+\)\s*\.\s*Run\s*\(|\b[A-Za-z0-9_]+callback_[A-Za-z0-9_]*\s*\.\s*Run\s*\(|\bNotify\s*\()"
)
TEARDOWN_METHOD_RE = re.compile(
    r"(~[A-Za-z_]\w*\s*\(|\b(Shutdown|Reset|Dispose|Teardown|OnDisconnect|Close|Destroy)\s*\()"
)


def extract_enclosing_classes(surfaces: list[dict[str, str]]) -> dict[str, list[str]]:
    """Map enclosing ClassName -> list of changed method names from surface rows."""
    classes: dict[str, list[str]] = {}
    for row in surfaces:
        subject = row.get("subject", "").strip()
        if "::" not in subject or subject.lower().startswith("group:"):
            continue
        parts = [part.strip() for part in subject.split("::") if part.strip()]
        if len(parts) < 2:
            continue
        class_match = IDENTIFIER.search(parts[-2])
        method_match = IDENTIFIER.search(parts[-1])
        if not class_match or not method_match:
            continue
        cls = class_match.group(0)
        method = method_match.group(0)
        if len(cls) < MIN_LENGTH or cls in {"std", "base", "blink", "content", "net", "mojo", "v8", "skia"}:
            continue
        methods = classes.setdefault(cls, [])
        if method not in methods:
            methods.append(method)
    return classes


def check_weak_factory_order(header_path: Path, class_name: str) -> list[str]:
    """Check if WeakPtrFactory<class_name> is declared before non-factory members."""
    if not header_path.is_file():
        return []
    try:
        lines = header_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    in_class = False
    brace_depth = 0
    weak_factory_line: int | None = None
    later_members: list[str] = []
    class_decl = re.compile(rf"\b(class|struct)\s+(?:[A-Z0-9_]+\s+)?{re.escape(class_name)}\b")
    for idx, line in enumerate(lines, start=1):
        stripped = line.split("//", 1)[0].strip()
        if not in_class:
            if class_decl.search(stripped) and ";" not in stripped:
                in_class = True
                brace_depth = stripped.count("{") - stripped.count("}")
            continue
        brace_depth += stripped.count("{") - stripped.count("}")
        if brace_depth <= 0 and "}" in stripped:
            break
        if brace_depth == 1:
            if "WeakPtrFactory" in stripped and ";" in stripped:
                weak_factory_line = idx
            elif weak_factory_line is not None and stripped.endswith(";") and "(" not in stripped:
                if not stripped.startswith(("using ", "typedef ", "static ", "friend ", "enum ", "struct ", "class ")):
                    later_members.append(f"{header_path.name}:{idx}: `{stripped}`")
    if weak_factory_line is not None and later_members:
        return [
            f"`{header_path.name}:{weak_factory_line}` declares `WeakPtrFactory` BEFORE "
            f"subsequent member(s) ({', '.join(later_members[:3])}) — `WeakPtr`s may not "
            "invalidate before those members are destroyed."
        ]
    return []


def build_class_dossiers(
    worktree: Path,
    callers_dir: Path,
    surfaces: list[dict[str, str]],
    pathspecs: list[str],
    revision: str,
) -> int:
    """Build 2-hop Class Lifetime & Async Hop Dossiers in callers/dossiers/<ClassName>.md."""
    classes = extract_enclosing_classes(surfaces)
    dossiers_dir = callers_dir / "dossiers"
    dossiers_dir.mkdir(parents=True, exist_ok=True)
    index_rows = [
        "class\tfiles\tlifetime_members\tdestructor_sites\tasync_bind_sites\tcallback_run_sites\twarnings\tdossier"
    ]
    built = 0
    for cls, methods in sorted(classes.items()):
        cmd = ["git", "-C", str(worktree), "grep", "-I", "-l", "-w", cls]
        if pathspecs:
            cmd += ["--", *pathspecs]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False)
        candidate_files = [
            f.strip() for f in res.stdout.splitlines()
            if f.strip().endswith((".h", ".cc", ".cpp", ".mm"))
        ][:12]
        if not candidate_files:
            continue

        lifetime_hits: list[str] = []
        teardown_hits: list[str] = []
        async_bind_hits: list[str] = []
        callback_run_hits: list[str] = []
        qualified_caller_hits: list[str] = []
        warnings: list[str] = []

        for rel_file in candidate_files:
            abs_file = worktree / rel_file
            if not abs_file.is_file():
                continue
            if rel_file.endswith(".h"):
                warnings.extend(check_weak_factory_order(abs_file, cls))
            try:
                file_lines = abs_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, text in enumerate(file_lines, start=1):
                code = text.split("//", 1)[0]
                loc = f"`{rel_file}:{lineno}`: `{text.strip()}`"
                if rel_file.endswith(".h") and LIFETIME_MEMBER_RE.search(code):
                    lifetime_hits.append(loc)
                if TEARDOWN_METHOD_RE.search(code) and (cls in code or not rel_file.endswith(".h")):
                    teardown_hits.append(loc)
                if ASYNC_BIND_RE.search(code) and (f"&{cls}::" in code or "weak_factory_" in code or "Unretained" in code):
                    context_window = " / ".join(
                        file_lines[max(0, lineno - 1):min(len(file_lines), lineno + 2)]
                    ).strip()
                    async_bind_hits.append(f"`{rel_file}:{lineno}`: `{context_window}`")
                if CALLBACK_RUN_RE.search(code):
                    callback_run_hits.append(loc)
                for method in methods:
                    if re.search(rf"(?:\.|->|::)\b{re.escape(method)}\s*\(", code):
                        qualified_caller_hits.append(f"`{rel_file}:{lineno}` (`{method}`): `{text.strip()}`")

        dossier_path = dossiers_dir / f"{cls}.md"
        md_lines = [
            f"# Class Lifetime & 2-Hop Async Dossier — `{cls}` (revision {revision[:12]})",
            "",
            f"- **Changed methods on `{cls}`:** {', '.join(f'`{m}`' for m in methods)}",
            f"- **Inspected class files:** {', '.join(f'`{f}`' for f in candidate_files)}",
            "",
        ]
        if warnings:
            md_lines.extend(["## Automatic Lifetime & Teardown Warnings", ""])
            md_lines.extend(f"- **WARNING:** {w}" for w in warnings)
            md_lines.append("")

        md_lines.extend([
            "## 1. Ownership, Lifetime & Concurrency Members (`.h`)",
            "",
            *(lifetime_hits[:40] if lifetime_hits else ["(none detected)"]),
            "",
            "## 2. Destructor, Reset & Disconnect Sites (Hop 0 Teardown)",
            "",
            *(teardown_hits[:30] if teardown_hits else ["(none detected)"]),
            "",
            "## 3. Hop 1 → Hop 2 Async Bindings & Task/Timer Registrations (`&ClassName::*`)",
            "",
            *(async_bind_hits[:40] if async_bind_hits else ["(none detected)"]),
            "",
            "## 4. Hop 2 Callback & Observer Invocations (`std::move(cb).Run` / `Notify`)",
            "",
            *(callback_run_hits[:30] if callback_run_hits else ["(none detected)"]),
            "",
            "## 5. Receiver-Qualified Call Sites of Changed Methods in Class Files",
            "",
            *(qualified_caller_hits[:40] if qualified_caller_hits else ["(none detected)"]),
            "",
        ])
        tmp = dossier_path.with_name(dossier_path.name + ".tmp")
        tmp.write_text("\n".join(md_lines), encoding="utf-8")
        tmp.replace(dossier_path)
        index_rows.append(
            "\t".join([
                cls,
                ",".join(candidate_files[:4]),
                str(len(lifetime_hits)),
                str(len(teardown_hits)),
                str(len(async_bind_hits)),
                str(len(callback_run_hits)),
                str(len(warnings)),
                f"callers/dossiers/{cls}.md",
            ])
        )
        built += 1

    (dossiers_dir / "index.tsv").write_text("\n".join(index_rows) + "\n", encoding="utf-8")
    return built


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument(
        "--revision", required=True,
        help="the pinned revision SHA from pin.md; the worktree HEAD must "
             "match it exactly")
    parser.add_argument(
        "--pathspec", action="append", default=[],
        help="narrow the search; default is the whole repository")
    arguments = parser.parse_args()
    review_dir = arguments.review_dir.resolve()
    worktree = arguments.worktree.resolve()
    if not (worktree / ".git").exists():
        fail(f"not a git worktree: {worktree}")
    head = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False)
    if head.returncode != 0:
        fail(f"cannot resolve worktree HEAD: {head.stderr.strip()}")
    if head.stdout.strip() != arguments.revision:
        fail(f"worktree HEAD {head.stdout.strip() or '?'} does not match "
             f"pinned revision {arguments.revision}")
    revision = arguments.revision
    rows = read_tsv(review_dir / "indexes" / "inventory.tsv")
    surfaces = [row for row in rows if row.get("kind") == "surface"]
    if not surfaces:
        fail("inventory index has no surface rows")

    pathspecs = list(arguments.pathspec)
    scope = scope_label(pathspecs)
    callers = review_dir / "callers"
    callers.mkdir(parents=True, exist_ok=True)
    searched: dict[str, int] = {}
    reused = 0
    index_rows = []
    for row in surfaces:
        surface_id = row.get("id", "")
        subject = row.get("subject", "")
        symbol, reason = symbol_for(subject)
        if reason:
            index_rows.append((surface_id, subject, "-", "-", "-",
                               f"skipped — {reason}"))
            continue
        if symbol not in searched:
            target = callers / f"{symbol}.txt"
            cached = reusable_hits(target, scope, revision)
            if cached is not None:
                searched[symbol] = cached
                reused += 1
            else:
                command = ["git", "-C", str(worktree), "grep", "-I", "-n",
                           "-w", symbol]
                if pathspecs:
                    command += ["--", *pathspecs]
                result = subprocess.run(
                    command, capture_output=True, text=True,
                    errors="replace", check=False)
                if result.returncode not in (0, 1):
                    fail(f"git grep failed for '{symbol}': "
                         f"{result.stderr.strip()}")
                hits = result.stdout.splitlines()
                searched[symbol] = len(hits)
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_text(
                    "\n".join(result_header(symbol, len(hits), scope,
                                            revision) + hits)
                    + "\n", encoding="utf-8")
                temporary.replace(target)
        index_rows.append((surface_id, subject, symbol,
                           str(searched[symbol]), scope,
                           f"callers/{symbol}.txt"))

    index_lines = ["surface_id\tsubject\tsymbol\thits\tscope\tresult"]
    index_lines += ["\t".join(row) for row in index_rows]
    (callers / "index.tsv").write_text(
        "\n".join(index_lines) + "\n", encoding="utf-8")
    dossiers_built = build_class_dossiers(
        worktree, callers, surfaces, pathspecs, revision
    )
    skipped = sum(1 for row in index_rows if row[2] == "-")
    print(f"{callers / 'index.tsv'}: {len(surfaces)} surfaces, "
          f"{len(searched)} symbols ({reused} reused), {skipped} skipped, "
          f"{sum(searched.values())} total hits, {dossiers_built} class dossiers, "
          f"scope: {scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
