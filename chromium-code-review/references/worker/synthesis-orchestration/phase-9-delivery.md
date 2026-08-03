<!-- Generated from ../../synthesis-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis Orchestration

Load this file only when Phase 7 becomes runnable. It governs bounded drafting,
challenge rounds, and freshness-safe delivery; worker content rules remain in
`synthesis-and-output.md` and `verification-and-fixes.md`.

## Phase 9 — Delivery

Refresh Gerrit detail into a temporary file, strip the XSSI prefix, and extract
only current patchset number, revision SHA, and updated timestamp. Write those
scalars to `delivery-gate.md`. Do not read bulk JSON into orchestrator context.
The Delivery Gate Finalizer may update only the Freshness line in
`reconciliation.md`; it never changes findings or dispositions. Regenerate
the derived indexes after that mutation so final validation cannot accept a
pre-delivery reconciliation fingerprint.

- Historical mode: verify the pinned SHA still maps to the selected patchset
  in `ALL_REVISIONS`; record `historical pin verified` and current PS context.
  Do not chase or delta-review the current patchset.
- Current SHA unchanged: record `current` with the check timestamp.
- Newer non-historical patchset: spawn the Patchset-Delta Inspector against
  the exact old/new SHAs. A trivial result must revalidate every cited line and
  conclusion and record exact PS/SHA pairs in `patchset-delta.md`; then run a
  metadata-only revision through the current bounded drafting topology (Draft
  Writer, or Frame Writer plus root reassembly) and a fresh Phase 8 challenge.
  A repeated refresh may record `trivial delta verified` only if Gerrit still
  equals the inspected new PS/SHA.
- Material delta: stop without delivering. Release the superseded pin's lease,
  then run `fetch-cl.sh` with a new sibling review directory for the new
  patchset, copy only user-authored directives, reference
  the immutable old review and delta as prior-feedback input, initialize a new
  manifest, and restart at Phase 1. Never mutate the old pin or reuse its
  ledgers or verdicts for a new SHA.

Repeat freshness after every revision or restart. State the exact reviewed base
PS/SHA and any separately inspected trivial-delta PS/SHA in the draft.

Run `scripts/validate-review-dir.py <review-dir> --phase final
--require-active-lease`. Only after it
passes, the latest draft has a passing challenge, and `delivery-gate.md` is
affirmative may the orchestrator read `draft-review.md`, `gerrit-comments.md`,
and `delivery-gate.md` for delivery. Limit the final check to formatting and
verdict/finding consistency; route content changes back through Phase 8.

After final artifacts are read, run `scripts/worktree-lease.py release
<review-dir> "review complete"` for every pin owned by the review. This is the
last mandatory gate before sending the final response: every release must
succeed. The command atomically removes this holder's active
`cl-<CL>-ps<PS>/<holder>.log` path; the `.released-*` file is inactive audit
history. Peer holders of the same pin keep their own leases, and the worktree
survives until the last of them releases. If any release fails, do not
claim the review is complete—report the cleanup failure and active path. Leave
clean cached worktrees in place; later invocations remove released or expired
entries. Preserve review directories and manifests as the audit trail.
