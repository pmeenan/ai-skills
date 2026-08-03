<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Verdict Alignment And Gerrit Output Rules

### Verdict Formatting

Avoid contradictory verdicts. If there is a blocking defect (P1 or P2),
the verdict must explicitly state that the change is blocked. Do not combine
approvals with blocking conditions.

- *Incorrect:* "LGTM with optional Polish (P3) after resolving one blocking
  P2 defect"
- *Correct:* "Not LGTM until the P2 telemetry bug is fixed; remaining items
  are optional P3."

### Gerrit-Ready Comments Constraints

When formatting comments meant to be copy-pasted directly to Gerrit:

- **No local paths:** Gerrit comments must never contain local absolute
  file paths (e.g. `/usr/local/...`) or local `file:///` URLs. Use
  repo-relative references only (e.g. `net/http/http_cache_writers.cc:1010`).
- **No placeholder or fake inlines:** do not output generic placeholder
  inline comments (e.g., `L16500 (General Nit) // General Nit`). General
  feedback belongs in the main comment body; inline comments must target
  real, modified lines of code.
- **Concise, query-based inlines:** frame inline feedback as questions or
  concise queries (e.g., "Can we gate these success-only metrics...?").
  Avoid repeating the same suggestion across multiple files/declarations;
  place a single comment at the most relevant site.
- **Make applicable edits directly actionable:** every promoted finding has a
  `Suggested edit` decision inherited from its evidence card. Mark it
  `applicable` only when the validated fix is fully determined, replaces one
  contiguous changed-side range of at most 10 lines, needs at most 20
  replacement lines, and requires no coordinated edit, API/design choice,
  generated output, or unseen context. Then include the exact same fenced
  `suggestion` block in both the review finding and its Gerrit fragment. The
  block contains replacement text only — no diff markers, ellipses,
  placeholders, or explanatory prose — and its target range must be the lines
  Gerrit should replace. This is an apply-ready edit, not pseudocode.
  Re-check the path is normalized and repo-relative, the positive range is
  in-bounds and intersects the pinned patch's changed side, and the selected
  text exactly equals those lines in the pinned revision. The Gerrit fragment
  contains exactly one standalone target declaration (`path:start-end` or a
  `###` heading with that value), so the fence cannot accidentally bind to a
  citation in explanatory prose.
- **Explain omissions:** when any eligibility condition fails, write
  `Suggested edit: omitted — <specific reason>` in the review finding and
  keep the Gerrit comment to concise fix guidance. Typical reasons are
  coordinated multi-location changes, an unresolved owner/API choice,
  replacement too large for one inline, or a fix not yet validated. Never
  force a locally neat snippet that repairs only one symptom of a root family.
- **Exhaustive coverage without truncation:** Every promoted finding (each a
  card in `synthesis/index.md`) writes one exact
  `gerrit-parts/<item>.md` target/comment fragment and measured
  `output-coverage.tsv` row; the fragment bytes occur exactly once in
  `gerrit-comments.md`. Merged duplicates are already folded into their
  surviving finding, so they need no separate comment. Do not sample,
  compress, or truncate promoted findings to shorten output length. Presenting
  100% of actionable bugs upfront is mandatory to prevent multiple review
  rounds.
- **Normalize threads before replying:** `comments.json` is keyed by file and
  contains CommentInfo arrays. Flatten with paths retained, group replies by
  transitive `in_reply_to` root, order within each thread by `updated` (stable
  ID tie-break), and take unresolved state from that thread's latest comment.
  Target the normalized root/latest IDs. Never use the last file-array element
  or the change's latest message as unresolved-thread state.
