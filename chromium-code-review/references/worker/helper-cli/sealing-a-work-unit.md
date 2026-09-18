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

## Sealing a work unit

```
seal-work-unit.py [-h] --phase PHASE --work-id WORK_ID --attempt ATTEMPT
                  --tier {frontier,inherit,mechanical,standard}
                  --brief BRIEF --artifact ARTIFACT
                  [--depends-on DEPENDS_ON] [--remaining-scope REMAINING_SCOPE]
                  [--input INPUT]
                  review_dir
```

`--input` is repeated, once per input, as `ROLE=/absolute/path`. Seal before
spawning: sealing is what makes the brief read-only and records the attempt's
input bytes and hashes. `build-phase-brief.py` prints the exact command for
the brief it just generated — use that rather than assembling `--input` by
hand, because a guessed list is the usual cause of
`names input X but input-manifest.tsv omits it`.
