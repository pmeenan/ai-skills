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

## Effort profiling

```
profile-review.py [-h] [--stdout] [--check]
                  [--tier-context-window-tokens TIER:TOKENS]
                  [--context-window-tokens N]
                  review_dir
```

Effort classes, cheapest first: `micro` (documentation and non-executable
metadata only), `trivial-code`, `standard`, and the heavier classes above it.
`trivial-code` requires all of: at most 4 changed files, 20 changed lines, 6
diff hunks, 6 approximate changed surfaces; at least one changed file; no
behavior-sensitive risk tokens in changed lines; no trigger-only specialist
lenses; no unresolved Gerrit threads; no supplied prior-review input; no
malformed normalized-comment entries. A failure is reported as
`trivial-code proof failed: <reason>`, and per-class results appear under
`micro_eligibility` and `trivial_code_eligibility`.

`micro` and `trivial-code` set `context_fast_path_eligible` and a collapsed
`topology` (`collapsed: true`, `initial_generalists: 1`,
`max_challenge_rounds: 1`). Act on those fields; do not re-derive them.
