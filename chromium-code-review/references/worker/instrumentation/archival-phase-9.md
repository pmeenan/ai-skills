<!-- Generated from ../../instrumentation.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Code-Read Instrumentation (`code-reads-v1`)

**Opt-in only.** Enable it when the user asks for an instrumented review,
code-read instrumentation, or review-cost collection — never merely because an
earlier review used it. Instrumentation observes the normal review and never
changes scope, model tier, findings, or gates.

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
