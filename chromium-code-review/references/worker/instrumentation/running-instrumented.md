<!-- Generated from ../../instrumentation.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Code-Read Instrumentation (`code-reads-v1`)

**Opt-in only.** Enable it when the user asks for an instrumented review,
code-read instrumentation, or review-cost collection — never merely because an
earlier review used it. Instrumentation observes the normal review and never
changes scope, model tier, findings, or gates.

## Running Instrumented

Every worker command whose output is consumed as code evidence — for example
`git diff/show/grep`, `rg`, or ranged `sed` — runs through
`scripts/instrument-command.py`. Deterministic helpers whose output is already
manifested by exact bytes do not need wrapping.

Instrumentation records command metadata and emitted-byte counts, never emitted
source payloads; it does not narrow or cap review work.

In an instrumented review, use the wrapped shell path instead of a
harness-native file-read or search tool for code evidence, so that different
models are measured through the same channel. Harness-native reads of small
control artifacts remain allowed.
