#!/usr/bin/env python3
"""The absolute inputs a generated phase brief names.

`validate-review-dir.py` rejects a sealed work unit whose `input-manifest.tsv`
omits any absolute path its brief names in `Inputs:`/`Procedure:`, and
`build-phase-brief.py` prints the `seal-work-unit.py` command that has to
satisfy that gate. A disagreement between the two costs a repair loop, so the
rule is stated once, here.

`validate-review-dir.py` cannot import this module — it is the gate, and this
skill is snapshotted and executed file by file — so it keeps its own copy of
`named_brief_inputs`. `scripts/tests/test_phase_brief_and_profile.py` asserts
the two implementations agree on a corpus of briefs chosen to exercise every
branch: quoted and bare paths, directories, trailing punctuation, section
switches, and paths named only under `Deliverables:`.
"""

from __future__ import annotations

import re
from pathlib import Path


def named_brief_inputs(brief: Path) -> set[Path]:
    """Return absolute file inputs named in a brief's input sections."""
    absolute_path = re.compile(
        r"(?<![A-Za-z0-9_.-])(/[A-Za-z0-9_.+@{}%=/:-]+)"
    )
    active = False
    deliverables_active = False
    named_inputs: set[Path] = set()
    named_deliverables: set[Path] = set()
    try:
        lines = brief.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return named_inputs
    for line in lines:
        if re.match(r"^(?:Inputs?|Procedure):", line, re.I):
            active = True
        elif active and re.match(
                r"^(?:Scope|Deliverables?|Return|Rules|Precondition):", line,
                re.I):
            active = False
        if re.match(r"^Deliverables?:", line, re.I):
            deliverables_active = True
        elif deliverables_active and re.match(
                r"^(?:Inputs?|Procedure|Scope|Return|Rules|Precondition):",
                line, re.I):
            deliverables_active = False
        if not active and not deliverables_active:
            continue
        destination = named_inputs if active else named_deliverables
        for quoted in re.findall(r"`(/[^`]+)`", line):
            if quoted.endswith("/"):
                continue
            candidate = Path(quoted)
            if not candidate.is_dir():
                destination.add(candidate.resolve())
        bare_line = re.sub(r"`[^`]*`", " ", line)
        for match in absolute_path.finditer(bare_line):
            raw = match.group(1)
            if raw.endswith("/"):
                continue
            candidate = Path(raw.rstrip(".,;:)]}"))
            if not candidate.is_dir():
                destination.add(candidate.resolve())
    return named_inputs - named_deliverables
