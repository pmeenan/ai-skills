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

## Restamping prestate rows

```
refresh-manifest.py [-h] [--role ROLE] [--dry-run] review_dir work_id attempt
```

Recomputes `bytes` and `sha256` for that attempt's manifest rows. `--role` is
repeatable and defaults to `prestate`. Restampable roles: `assigned`,
`candidate-packet`, `card`, `control`, `frame`, `prestate`, `section`.
`brief` and `reference` are refused unconditionally — they are sealed
integrity anchors, and rehashing one would defeat the seal; reseal the attempt
instead. `--dry-run` reports the old→new deltas and changes nothing.

Use this instead of a hand-written `hashlib` snippet whenever a prestate input
grows between attempts and the gate reports a byte-count mismatch.
