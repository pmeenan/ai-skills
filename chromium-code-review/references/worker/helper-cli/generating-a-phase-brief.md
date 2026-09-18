<!-- Generated from ../../helper-cli.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Helper CLI Reference

**Never read or grep a helper script's source to work out how to call it.**
Look it up here. If an invocation you need is missing, adding it here is part
of doing the work.

For what an *error message* means, do not read
[gate-errors.md](gate-errors.md) either — it is a 700-row lookup table. Query
it instead:

```sh
<skill-dir>/scripts/explain-gate-error.py "<the message you saw>"
```

Paste the message verbatim; concrete paths, line numbers, and quoted values
are ignored when matching. `--max N` widens the result set. Exit 1 means no
row matched, and the corrective action is to add one once you know the fix.

> Measured over 31 runs of this skill, orchestrators opened helper source 725
> times — `validate-review-dir.py` alone 149 times across 8 conversations —
> and ran roughly 91 `--help` probes, purely to recover facts that are on this
> page.

Throughout, `<skill-dir>` means the sealed snapshot at
`<review-dir>/skill-snapshot`, not the canonical checkout, from the moment
`snapshot-skill.py` has run.

## Generating a phase brief

```
build-phase-brief.py [-h] [--attempt ATTEMPT] [--shard SHARD] [--thread THREAD]
                     [--output OUTPUT] [--pathspec PATHSPEC] [--set KEY=VALUE]
                     [--allow-placeholders] [--phase PHASE]
                     [--tier {frontier,inherit,mechanical,standard}]
                     [--artifact ARTIFACT]
                     [--emit-seal-command | --no-emit-seal-command]
                     review_dir work_id brief_name
```

`brief_name` is the `## ` heading in `references/phase-briefs.md`; an unknown
name lists every available heading, so there is no reason to open that 81 KB
file to find one.

**It refuses to write a brief that still contains a `⟨...⟩` placeholder**,
listing each one with the flag that fills it. `--pathspec` fills the path-list
placeholders; `--set KEY=VALUE` fills `⟨KEY⟩` and is repeatable;
`--allow-placeholders` is the deliberate escape hatch. Placeholders the common
header leaves for the *worker* to resolve at runtime are allowlisted and do not
trip the check.

> This check is the fix for the most expensive recurring failure in the audit:
> a placeholder was hand-substituted out of a brief *after* the work unit was
> sealed, which changed the brief's bytes and produced
> `input-manifest.tsv: byte count mismatch` repair loops.

Unless `--no-emit-seal-command`, it then prints the exact `seal-work-unit.py`
command for what it wrote, with one `--input ROLE=path` for every absolute path
the gate will extract from the brief, `--phase` from the `(Phase N)` heading,
`--tier` from the `Tier:` line, and `--artifact` from the `Deliverable:` line.
**Run that command rather than assembling one**: a guessed `--input` list is
what produces `names input X but input-manifest.tsv omits it`. If a field
cannot be derived it prints a NOTE saying which flag to supply instead of a
command.
