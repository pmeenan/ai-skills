# Code-Read Instrumentation (`code-reads-v1`)

**Opt-in only.** Enable it when the user asks for an instrumented review,
code-read instrumentation, or review-cost collection — never merely because an
earlier review used it. Instrumentation observes the normal review and never
changes scope, model tier, findings, or gates.

## Enabling

Add the exact line `instrumentation: code-reads-v1` to `directives.md`. If the
user supplies a model or run label for comparison, also record
`instrumentation-label: ⟨label⟩`.

Each review directory receives a persistent UUID-backed run ID, so concurrent
runs of the same CL, patchset, and skill revision archive as distinct siblings,
and rerunning archival for one review is idempotent.

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

## Archival (Phase 9)

After the cost report, run
`⟨review-dir⟩/skill-snapshot/scripts/archive-review-instrumentation.py
⟨review-dir⟩`. It resolves the canonical skill source from the immutable
snapshot manifest and atomically archives the compact instrumentation bundle
under `instrumentation/runs/code-reads-v1/⟨skill-git-hash⟩/`.

A failure is disclosed with its diagnostic and archive target; it does not
invalidate the code-review verdict or the freshness gate.

**Never copy source packets, ledgers, findings, drafts, Gerrit comments, or
command output into the skill checkout.**
