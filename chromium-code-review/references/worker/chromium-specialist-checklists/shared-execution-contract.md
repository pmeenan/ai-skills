<!-- Generated from ../../chromium-specialist-checklists.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Chromium Specialist Checklists

Load only the sections activated by deterministic inventory triggers. Treat
these as discovery supplements: record every anomaly as a ledger candidate and
leave severity/disposition to verification. Close a row clean only with a
`path:line` citation to the relevant guard, owner, bound, metadata, or test.

## Shared Execution Contract

For each activated section, produce the named artifact with:

1. exact trigger hits (`path:line` and symbol);
2. the required model or matrix;
3. one prefixed candidate row per unresolved invariant or omission;
4. `PASS` rows only when evidence cites code or a test by `path:line`.

Do not infer safety from comments, DCHECKs in release-only paths, type names, or
the CL description. Trace the concrete producer, consumer, owner, boundary, and
teardown/version state.
