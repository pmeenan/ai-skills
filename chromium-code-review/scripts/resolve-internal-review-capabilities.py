#!/usr/bin/env python3
"""Resolve in-tree Chromium experimental-code-review capabilities for a pinned CL diff.

Detects whether `internal/agents/skills/experimental-code-review` is present in
the checkout (including when running from a detached git worktree where
`internal/` lives in the main checkout) and generates a deterministic
`internal-review-capabilities.md` artifact for the `ICRR` runner subagent.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPERIMENTAL_SKILL_RELPATH = Path(
    "internal/agents/skills/experimental-code-review"
)
GENERAL_RULES_RELPATH = Path("agents/knowledge_base/rules/general")


def resolve_main_checkout(worktree: Path) -> Path:
    """Return the main checkout path for `worktree` via `git worktree list`."""
    proc = subprocess.run(
        ["git", "-C", str(worktree), "worktree", "list", "--porcelain"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if line.startswith("worktree "):
                candidate = Path(line.split(" ", 1)[1].strip())
                if candidate.is_dir():
                    return candidate.resolve()
    return worktree.resolve()


def locate_experimental_skill_dir(
    worktree: Path, main_checkout: Path
) -> Path | None:
    """Locate `internal/agents/skills/experimental-code-review` if present."""
    override = os.environ.get("CHROMIUM_REVIEW_INTERNAL_SKILL_DIR")
    if override is not None:
        cleaned = override.strip()
        if not cleaned or cleaned.lower() in {"0", "false", "none", "off"}:
            return None
        candidate = Path(cleaned).resolve()
        if (candidate / "SKILL.md").is_file():
            return candidate
        return None

    for root in (worktree, main_checkout):
        candidate = root / EXPERIMENTAL_SKILL_RELPATH
        if (candidate / "SKILL.md").is_file():
            return candidate.resolve()
    return None


def _unescape_textproto_string(raw: str) -> str:
    """Unescape a single- or double-quoted textproto string literal."""
    return re.sub(
        r"\\(.)",
        lambda m: {
            "n": "\n",
            "t": "\t",
            "r": "\r",
            '"': '"',
            "'": "'",
            "\\": "\\",
        }.get(m.group(1), "\\" + m.group(1)),
        raw,
    )


def _extract_string_list_from_block(block: str, field_name: str) -> list[str]:
    results: list[str] = []
    list_pattern = re.compile(
        rf"\b{re.escape(field_name)}\s*:\s*\[(.*?)\]", re.DOTALL
    )
    for match in list_pattern.finditer(block):
        content = match.group(1)
        for str_match in re.finditer(
            r'"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'', content
        ):
            val = (
                str_match.group(1)
                if str_match.group(1) is not None
                else str_match.group(2)
            )
            results.append(_unescape_textproto_string(val))

    block_without_lists = list_pattern.sub("", block)
    single_pattern = re.compile(
        rf'\b{re.escape(field_name)}\s*:\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\')'
    )
    for match in single_pattern.finditer(block_without_lists):
        val = (
            match.group(1)
            if match.group(1) is not None
            else match.group(2)
        )
        results.append(_unescape_textproto_string(val))
    return results


def _parse_capability_groups_from_textproto(
    text: str, source_tag: str
) -> list[dict[str, Any]]:
    """Extract `capability_groups` blocks from textproto `COMMON_METADATA`."""
    groups: list[dict[str, Any]] = []
    pattern = re.compile(r"\bcapability_groups\s*:?\s*\{")
    pos = 0
    while True:
        match = pattern.search(text, pos)
        if not match:
            break
        start = match.end()
        depth = 1
        idx = start
        in_double = False
        in_single = False
        escaped = False
        while idx < len(text) and depth > 0:
            ch = text[idx]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "'" and not in_double:
                in_single = not in_single
            elif not in_double and not in_single:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
            idx += 1
        block = text[start : idx - 1]
        pos = idx
        names = _extract_string_list_from_block(block, "name")
        groups.append(
            {
                "name": names[0] if names else "",
                "path_expressions": _extract_string_list_from_block(
                    block, "path_expression"
                ),
                "path_expression_exclusions": _extract_string_list_from_block(
                    block, "path_expression_exclusion"
                ),
                "content_patterns": _extract_string_list_from_block(
                    block, "content_patterns"
                ),
                "rules": _extract_string_list_from_block(block, "rules"),
                "skills": _extract_string_list_from_block(block, "skills"),
                "source": source_tag,
            }
        )
    return groups


def _get_modified_files_and_lines(
    worktree: Path, parent_sha: str, revision_sha: str
) -> dict[str, list[str]]:
    """Run two-dot `git diff` between `parent_sha` and `revision_sha`."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "diff",
            "--no-color",
            "--no-ext-diff",
            "--unified=0",
            parent_sha,
            revision_sha,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    file_changes: dict[str, list[str]] = {}
    current_file: str | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            file_changes.setdefault(current_file, [])
        elif line.startswith("+++ /dev/null"):
            current_file = None
        elif (
            current_file is not None
            and line.startswith("+")
            and not line.startswith("+++")
        ):
            file_changes[current_file].append(line[1:])
    return file_changes


def _query_dirmd_groups(
    worktree: Path, main_checkout: Path, directories: list[str]
) -> list[dict[str, Any]]:
    if not directories:
        return []
    existing_dirs: set[str] = set()
    for rel_dir in directories:
        cur = Path(rel_dir) if rel_dir else Path(".")
        while True:
            wt_candidate = worktree / cur
            mc_candidate = main_checkout / cur
            if wt_candidate.is_dir() or mc_candidate.is_dir():
                existing_dirs.add(
                    "." if cur == Path(".") else cur.as_posix()
                )
                break
            if cur == Path(".") or cur.parent == cur:
                existing_dirs.add(".")
                break
            cur = cur.parent

    if not existing_dirs:
        return []

    groups: list[dict[str, Any]] = []
    for repo_root in (worktree, main_checkout):
        valid_for_root = sorted(
            d for d in existing_dirs if (repo_root / d).is_dir()
        )
        if not valid_for_root:
            continue
        try:
            proc = subprocess.run(
                ["dirmd", "read", "-form", "sparse", *valid_for_root],
                cwd=str(repo_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except OSError:
            continue
        if proc.returncode != 0 or not proc.stdout.strip():
            continue
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for dir_key, dir_data in payload.get("dirs", {}).items():
            agentic = dir_data.get("agenticReview", {})
            for cg in agentic.get("capabilityGroups", []):
                groups.append(
                    {
                        "name": cg.get("name", ""),
                        "path_expressions": cg.get("pathExpression", []),
                        "path_expression_exclusions": cg.get(
                            "pathExpressionExclusion", []
                        ),
                        "content_patterns": cg.get("contentPatterns", []),
                        "rules": cg.get("rules", []),
                        "skills": cg.get("skills", []),
                        "source": f"dirmd:{dir_key}",
                    }
                )
        if groups:
            break
    return groups


def _load_general_common_metadata_groups(
    worktree: Path, main_checkout: Path
) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen_relpaths: set[str] = set()
    for root in (worktree, main_checkout):
        base = root / GENERAL_RULES_RELPATH
        if not base.is_dir():
            continue
        for meta_path in sorted(base.glob("*/COMMON_METADATA")):
            rel = meta_path.relative_to(root).as_posix()
            if rel in seen_relpaths:
                continue
            seen_relpaths.add(rel)
            try:
                text = meta_path.read_text(encoding="utf-8")
            except OSError:
                continue
            groups.extend(
                _parse_capability_groups_from_textproto(text, f"general:{rel}")
            )
    return groups


def _group_matches_changes(
    group: dict[str, Any], file_changes: dict[str, list[str]]
) -> tuple[bool, bool, list[str]]:
    """Return `(matched, matched_by_content_or_dir_specific, matched_files)`."""
    path_exprs = [re.compile(p) for p in group.get("path_expressions", [])]
    excl_exprs = [
        re.compile(p) for p in group.get("path_expression_exclusions", [])
    ]
    content_Regexes: list[re.Pattern[str]] = []
    for pat in group.get("content_patterns", []):
        try:
            content_Regexes.append(re.compile(pat))
        except re.error:
            continue

    matched_files: list[str] = []
    for file_path, added_lines in file_changes.items():
        if path_exprs and not any(r.search(file_path) for r in path_exprs):
            continue
        if excl_exprs and any(r.search(file_path) for r in excl_exprs):
            continue
        if not content_Regexes:
            matched_files.append(file_path)
            continue
        if any(
            r.search(line) for line in added_lines for r in content_Regexes
        ):
            matched_files.append(file_path)

    if not matched_files:
        return False, False, []

    is_general = str(group.get("source", "")).startswith("general:")
    high_signal = bool(content_Regexes) or not is_general
    return True, high_signal, matched_files


def _resolve_repo_file(
    rel_path: str, worktree: Path, main_checkout: Path
) -> Path | None:
    cleaned = rel_path.lstrip("/")
    for root in (worktree, main_checkout):
        candidate = root / cleaned
        if candidate.is_file():
            return candidate.resolve()
    return None


def _parse_rule_summary(text: str, fallback_name: str) -> dict[str, str]:
    name = fallback_name
    severity = "UNKNOWN"
    description = ""
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    body = text
    if fm_match:
        fm_text, body = fm_match.group(1), fm_match.group(2)
        for line in fm_text.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("severity:"):
                severity = line.split(":", 1)[1].strip()
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
    bold_rule = re.search(
        r"\*\*Rule\.\*\*\s*(.*?)(?:\n\s*\n|\n+\*\*Why\.\*\*|\n+##\s+|\Z)",
        body,
        re.DOTALL,
    )
    rule_sec = re.search(
        r"##\s+Rule\s*\n+(.*?)(?:\n+##\s+|\Z)", body, re.DOTALL
    )
    rule_line = ""
    if bold_rule:
        rule_line = " ".join(bold_rule.group(1).strip().split())
    elif rule_sec:
        rule_line = " ".join(rule_sec.group(1).strip().split())
    summary = rule_line or description or name
    if len(summary) > 85:
        summary = summary[:82] + "..."
    return {
        "name": name,
        "severity": severity,
        "description": description,
        "summary": summary,
    }


def resolve_internal_review_capabilities(
    worktree: Path,
    parent_sha: str,
    revision_sha: str,
    output_md: Path | None = None,
    max_bytes: int | None = 45000,
) -> dict[str, Any]:
    """Detect `experimental-code-review` and optionally write capabilities markdown."""
    worktree = worktree.resolve()
    main_checkout = resolve_main_checkout(worktree)
    skill_dir = locate_experimental_skill_dir(worktree, main_checkout)
    if skill_dir is None:
        return {"available": False}

    file_changes = _get_modified_files_and_lines(
        worktree, parent_sha, revision_sha
    )
    directories = sorted(
        {os.path.dirname(f) or "." for f in file_changes.keys()}
    )

    all_groups = _query_dirmd_groups(
        worktree, main_checkout, directories
    ) + _load_general_common_metadata_groups(worktree, main_checkout)

    high_signal_rules: dict[str, dict[str, Any]] = {}
    path_only_rules: dict[str, dict[str, Any]] = {}
    matched_skills: dict[str, dict[str, Any]] = {}

    for group in all_groups:
        matched, high_signal, matched_files = _group_matches_changes(
            group, file_changes
        )
        if not matched:
            continue
        for rule_rel in group.get("rules", []):
            cleaned_rule = rule_rel.lstrip("/")
            resolved_path = _resolve_repo_file(
                cleaned_rule, worktree, main_checkout
            )
            if resolved_path is None:
                continue
            if high_signal:
                entry = high_signal_rules.setdefault(
                    cleaned_rule,
                    {
                        "rel_path": cleaned_rule,
                        "abs_path": str(resolved_path),
                        "group_names": [],
                        "matched_files": set(),
                    },
                )
                entry["group_names"].append(group.get("name", ""))
                entry["matched_files"].update(matched_files)
                path_only_rules.pop(cleaned_rule, None)
            elif cleaned_rule not in high_signal_rules:
                entry = path_only_rules.setdefault(
                    cleaned_rule,
                    {
                        "rel_path": cleaned_rule,
                        "abs_path": str(resolved_path),
                        "group_names": [],
                        "matched_files": set(),
                    },
                )
                entry["group_names"].append(group.get("name", ""))
                entry["matched_files"].update(matched_files)

        for skill_rel in group.get("skills", []):
            cleaned_skill = skill_rel.lstrip("/")
            resolved_path = _resolve_repo_file(
                cleaned_skill, worktree, main_checkout
            )
            if resolved_path is None:
                continue
            entry = matched_skills.setdefault(
                cleaned_skill,
                {
                    "rel_path": cleaned_skill,
                    "abs_path": str(resolved_path),
                    "group_names": [],
                    "matched_files": set(),
                },
            )
            entry["group_names"].append(group.get("name", ""))
            entry["matched_files"].update(matched_files)

    category_refs = sorted((skill_dir / "references").glob("*.md"))

    if output_md is not None:
        lines: list[str] = [
            "# In-Tree Experimental Code Review Capabilities",
            "",
            f"- Main checkout: `{main_checkout}`",
            f"- Worktree: `{worktree}`",
            f"- Experimental skill directory: `{skill_dir}`",
            f"- Experimental SKILL.md: `{skill_dir / 'SKILL.md'}`",
            f"- High-signal (content/directory-matched) rules: `{len(high_signal_rules)}`",
            f"- General path-matched rules (compact index): `{len(path_only_rules)}`",
            f"- Triggered domain skills: `{len(matched_skills)}`",
            "",
            "## Category Reference Checklists",
            "",
        ]
        for ref in category_refs:
            lines.append(f"- `{ref}`")

        lines.extend(
            [
                "",
                "## High-Signal Triggered Rules (Full Content)",
                "",
            ]
        )
        if not high_signal_rules:
            lines.append(
                "_No content-pattern or directory-specific rules matched the added lines._"
            )
        else:
            for rule_rel, info in sorted(high_signal_rules.items()):
                rule_path = Path(info["abs_path"])
                try:
                    rule_text = rule_path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                if len(high_signal_rules) > 10:
                    rule_text = re.sub(
                        r"\n+##\s+Examples\b.*",
                        "\n\n_(Read `Full path` above for code examples.)_",
                        rule_text,
                        flags=re.DOTALL,
                    )
                sample_files = ", ".join(sorted(info["matched_files"])[:5])
                lines.extend(
                    [
                        f"### Rule: `{rule_rel}` (matched: `{sample_files}`)",
                        "",
                        rule_text,
                        "",
                    ]
                )

        lines.extend(
            [
                "## Triggered Domain Skills (Full Content)",
                "",
            ]
        )
        if not matched_skills:
            lines.append("_No domain-specific review skills matched._")
        else:
            for skill_rel, info in sorted(matched_skills.items()):
                skill_path = Path(info["abs_path"])
                try:
                    skill_text = skill_path.read_text(encoding="utf-8").strip()
                except OSError:
                    continue
                sample_files = ", ".join(sorted(info["matched_files"])[:5])
                lines.extend(
                    [
                        f"### Skill: `{skill_rel}`",
                        f"- Full path: `{skill_path}`",
                        f"- Matched files: `{sample_files}`",
                        "",
                        skill_text,
                        "",
                    ]
                )

        general_base = (
            worktree / GENERAL_RULES_RELPATH
            if (worktree / GENERAL_RULES_RELPATH).is_dir()
            else main_checkout / GENERAL_RULES_RELPATH
        )
        lines.extend(
            [
                "",
                "## General Path-Matched Rules (Compact Summary Index)",
                "",
                f"- Base directory for general rules: `{general_base}`",
                "- Read `<base-directory>/<rel_path>` if any rule below is potentially violated by the changed code:",
                "",
                "| rel_path | severity | summary |",
                "|---|---|---|",
            ]
        )
        current_bytes = sum(len(line.encode("utf-8")) + 1 for line in lines)
        omitted_path_rules = 0
        for rule_rel, info in sorted(path_only_rules.items()):
            rule_path = Path(info["abs_path"])
            try:
                rule_text = rule_path.read_text(encoding="utf-8")
            except OSError:
                continue
            parsed = _parse_rule_summary(rule_text, rule_path.stem)
            safe_summary = parsed["summary"].replace("|", r"\|")
            short_rel = rule_rel.removeprefix(
                GENERAL_RULES_RELPATH.as_posix() + "/"
            )
            row_line = (
                f"| `{short_rel}` | `{parsed['severity']}` | {safe_summary} |"
            )
            row_bytes = len(row_line.encode("utf-8")) + 1
            if max_bytes is not None and current_bytes + row_bytes + 256 > max_bytes:
                omitted_path_rules += 1
                continue
            lines.append(row_line)
            current_bytes += row_bytes
        if omitted_path_rules:
            lines.append("")
            lines.append(
                f"_(Omitted {omitted_path_rules} additional path-matched general rules to stay within the worker input budget; see `{general_base}`.)_"
            )

        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "available": True,
        "main_checkout": str(main_checkout),
        "skill_dir": str(skill_dir),
        "skill_md": str(skill_dir / "SKILL.md"),
        "category_references": [str(p) for p in category_refs],
        "capabilities_artifact": (
            output_md.name if output_md is not None else "internal-review-capabilities.md"
        ),
        "matched_content_rule_count": len(high_signal_rules),
        "matched_path_rule_count": len(path_only_rules),
        "matched_skill_count": len(matched_skills),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("worktree", type=Path, help="Pinned worktree directory")
    parser.add_argument("--base", required=True, help="Parent SHA")
    parser.add_argument(
        "--revision", default="HEAD", help="Revision SHA (default: HEAD)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output Markdown path (e.g. <review-dir>/internal-review-capabilities.md)",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional JSON metadata output path",
    )
    args = parser.parse_args()
    metadata = resolve_internal_review_capabilities(
        args.worktree,
        args.base,
        args.revision,
        output_md=args.output.resolve(),
    )
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps(metadata, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(metadata, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
