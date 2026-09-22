"""Shared authentication for executable inputs and historical output bytes."""
from pathlib import Path
import hashlib
import json
import re

OUTPUT_DIRS = {'draft-parts', 'gerrit-parts', 'output-coverage'}
OUTPUT_FILES = {'draft-review.md', 'gerrit-comments.md', 'output-coverage.tsv'}


def mutable_output(root: Path, path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return ((len(relative.parts) == 1 and relative.name in OUTPUT_FILES)
            or (len(relative.parts) == 2 and relative.parts[0] in OUTPUT_DIRS))


def archived_output_matches(root: Path, row: dict[str, str]) -> bool:
    path = Path(row.get('input_path', ''))
    expected = row.get('sha256', '')
    if not mutable_output(root, path) or not re.fullmatch('[0-9a-f]{64}', expected):
        return False
    archive = root / 'output-history' / (expected + '.bin')
    try:
        payload = archive.read_bytes()
        return (not archive.is_symlink() and archive.stat().st_mode & 0o222 == 0
                and str(len(payload)) == row.get('bytes')
                and hashlib.sha256(payload).hexdigest() == expected)
    except OSError:
        return False


def executable_only(root: Path, path: Path, brief: Path, role: str,
                    size: int, expected_hash: str) -> bool:
    """Exclude tool implementation bytes, never references or arbitrary code."""
    if role != 'assigned':
        return False
    try:
        text = brief.read_text()
        if not re.search(r'Never read or grep helper script\s+source files', text):
            return False
        relative = path.resolve().relative_to(root.resolve())
        parts = relative.parts
        if parts[:1] == ('skill-snapshot',):
            snapshot = root / 'skill-snapshot'
            inner = parts[1:]
        elif (len(parts) > 2 and re.fullmatch(r'repaired-tools(?:-v[0-9]+)?', parts[0])
              and parts[1] == 'skill-snapshot'):
            snapshot = root / parts[0] / 'skill-snapshot'
            inner = parts[2:]
        else:
            return False
        if len(inner) != 2 or inner[0] != 'scripts' or path.suffix not in {'.py', '.sh'}:
            return False
        manifest = snapshot / 'snapshot-manifest.json'
        if (path.is_symlink() or path.stat().st_mode & 0o222
                or not path.stat().st_mode & 0o111 or manifest.stat().st_mode & 0o222):
            return False
        value = json.loads(manifest.read_text())
        entries = [entry for entry in value.get('files', []) if entry.get('path') == '/'.join(inner)]
        payload = path.read_bytes()
        return (value.get('schema_version') == 1 and len(entries) == 1
                and entries[0].get('bytes') == size == len(payload)
                and entries[0].get('sha256') == expected_hash == hashlib.sha256(payload).hexdigest())
    except (OSError, ValueError, TypeError):
        return False


def effective_input_limit(context: dict, tier: str) -> int | None:
    global_limit = context.get('worker_input_budget_bytes')
    tier_limit = context.get('tier_worker_input_budget_bytes', {}).get(tier)
    if tier != 'inherit' and not isinstance(tier_limit, int):
        tier_limit = 131072
    limits = [value for value in (global_limit, tier_limit) if isinstance(value, int)]
    return min(limits) if limits else None
