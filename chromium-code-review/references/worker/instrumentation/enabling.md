<!-- Generated from ../../instrumentation.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

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
