<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Verdict Alignment And Gerrit Output Rules

### Verdict Formatting

Avoid contradictory verdicts. If there is a **CL-introduced** (or
`introduced-in-PS<N>`) blocking defect (P1 or P2), the verdict must explicitly
state that the change is blocked. Pre-existing codebase issues (`Origin:
pre-existing`) are informational follow-ups and NEVER block `LGTM`. Do not
combine approvals with blocking conditions.

- *Incorrect:* "LGTM with optional Polish (P3) after resolving one blocking
  P2 defect"
- *Incorrect:* "Not LGTM until the pre-existing P1 ordering bug is fixed"
- *Correct:* "Not LGTM until the CL-introduced P2 telemetry bug is fixed;
  remaining items are optional P3."
- *Correct:* "LGTM with optional P3 polish (plus one pre-existing follow-up
  noted for reference)."

### Gerrit-Ready Comments Constraints

When formatting comments meant to be copy-pasted directly to Gerrit:

- **No local paths:** Neither `draft-review.md` nor `gerrit-comments.md` may
  ever contain local absolute file paths (e.g. `/usr/local/...`,
  `/codereview/worktrees/...`, `/tmp/...`, `/home/...`) or local `file:///`
  URLs. Use repo-relative references only (e.g.
  `net/http/http_cache_writers.cc:1010`).
- **Patchset-level summary comment required:** `gerrit-comments.md` must always
  include a `## Main comment` (or `## Patchset-Level Comment`) section before
  inline comments (emitted via `gerrit-parts/FRAME.md` in sharded drafts) that
  gives the author a concise landing-readiness summary, blocking `P1`/`P2` vs
  optional `P3` counts, prior review status, and any non-blocking **Launch-Gate
  Note** for explicit `TODO`-tracked or default-off pre-launch prerequisites
  (such as quota/eviction wiring on a default-off feature). On Round 2+
  follow-up reviews (`same_reviewer_followup: true`), keep `## Main comment` to
  1–3 natural human-sounding sentences stating overall status (for example, that
  prior comments were addressed and only the remaining inline items/nits remain),
  followed only by any `[Reviewer decision on thread <id>: Option A ... / Option
  B ...]` placeholder or brief **Launch-Gate Note**; keep exhaustive itemized
  `file:line` audit lists of fixed prior comments inside `draft-review.md`
  (`Prior Review Follow-Up`) only, never in `## Main comment`. Keep internal
  `Verification Notes` (such as `"No local test execution was performed during
  this review"` or thread-audit summaries) inside `draft-review.md` only — do not
  include an internal `Verification notes:` bullet in `gerrit-comments.md`.
- **Verbatim quoted code line required:** Every new inline comment in
  `gerrit-parts/<item>.md` and `gerrit-comments.md` must include `- Line: \`<verbatim line from the pinned patchset>\`` copied directly from the card's `Verbatim changed line` field (which itself must be extracted verbatim from the worktree at the pinned revision, never paraphrased from memory).
- **No placeholder or fake inlines (and `/COMMIT_MSG` targeting for commit-message findings):** do not output generic placeholder
  inline comments (e.g., `L16500 (General Nit) // General Nit`). General
  feedback belongs in the main comment body; inline comments must target
  real, modified lines of code. When a finding specifically concerns the CL
  description / commit message (such as an inaccurate summary of the change or
  a body line exceeding 72 columns), anchor its `Location` and Gerrit inline
  target directly on `/COMMIT_MSG:<line>` (with `Suggested edit: omitted —
  commit message edit`) rather than attaching a commit-message comment to line 1
  of an arbitrary C++ source file. In Gerrit, `/COMMIT_MSG` begins with 6
  synthetic header lines (`Parent`, `Author`, `AuthorDate`, `Commit`,
  `CommitDate`, and a blank line), so line 7 is the commit subject line and
  `- Line: \`...\`` quotes the exact line from the commit message at that offset.
- **Concise, query-based inlines (1–3 sentences):** frame inline feedback as
  concise questions or direct observations (1–3 sentences stating the concrete
  bug/impact and the ask, e.g., "Can we gate these success-only metrics...?").
  Prefix every P3 optional-polish inline comment with `nit:`. Never paste
  multi-paragraph trace dumps, internal gate metadata (`Rows`, `Synthesis item`,
  `Fix status`, anchor names), or unmodified external subsystem `path:line`
  coordinates into author-facing Gerrit inline comments (name the external
  class/method concisely in prose instead). In any P3 style, assertion, or
  test-cleanup inline comment on a modified file, cite and request changes only
  on lines and classes touched by the CL's diff hunks — never bundle untouched
  pre-existing lines or unmodified sibling classes in the same file. Avoid
  repeating the same suggestion across multiple files/declarations; place a
  single comment at the most relevant site.
- **Make applicable edits directly actionable:** every promoted finding has a
  `Suggested edit` decision inherited from its evidence card. Mark it
  `applicable` only when the validated fix is fully determined, replaces one
  contiguous changed-side range of at most 10 lines, needs at most 20
  replacement lines, and requires no coordinated edit, API/design choice,
  generated output, or unseen context. Then include the exact same fenced
  `suggestion` block in both the review finding and its Gerrit fragment. The
  block contains replacement text only — no diff markers, ellipses,
  placeholders, or explanatory prose — and its target range must be the lines
  Gerrit should replace. When the replaced range `path:start-end` ends with a
  blank separator line in the pinned file, preserve that trailing blank line in
  the `suggestion` block so applying the edit does not join adjacent blocks.
  This is an apply-ready edit, not pseudocode.
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
- **Exhaustive coverage without truncation:** Every promoted finding, owner
  question, and reviewer note (each a card in `synthesis/index.md`) writes one
  exact `draft-parts/<item>.md` fragment and measured `output-coverage.tsv` row
  whose bytes occur exactly once in `draft-review.md`. Every `CL-introduced` and
  `introduced-in-PS<N>` finding also writes one exact `gerrit-parts/<item>.md`
  target/comment fragment whose bytes occur exactly once in `gerrit-comments.md`.
  Owner questions (`Q<number>`) and Reviewer Notes (`N<number>`) live in
  `draft-review.md` only and use `-` for all three Gerrit columns in
  `output-coverage.tsv`. Findings with `Origin: pre-existing` may either emit an
  informational `gerrit-parts/<item>.md` fragment or omit Gerrit inline output
  (`-` for all three Gerrit columns in `output-coverage.tsv`, with `Suggested
  edit: omitted — <reason>`) when posting an inline comment on untouched or
  adjacent pre-existing code would add noise to the Gerrit review. Merged
  duplicates are already folded into their surviving finding, so they need no
  separate comment. Do not sample, compress, or truncate promoted findings to
  shorten output length. Presenting 100% of actionable bugs upfront is mandatory
  to prevent multiple review rounds.
- **Normalize threads before replying (and controlled thread reopening):**
  `comments.json` is keyed by file and contains CommentInfo arrays. Flatten with
  paths retained, group replies by transitive `in_reply_to` root, order within
  each thread by `updated` (stable ID tie-break), and take unresolved state from
  that thread's latest comment. Target the normalized root/latest IDs in
  `gerrit/unresolved-threads.json`. Never use the last file-array element or the
  change's latest message as unresolved-thread state. By default, never emit a
  `### Thread <root_id>` or `- Reply-To: root <root_id>, latest <latest_id>`
  reply for a thread that is already resolved on Gerrit (absent from
  `gerrit/unresolved-threads.json`). **Controlled exception (`reopen`):** when a
  direct follow-up or clarification belongs on a resolved Gerrit thread that
  `Reviewer email` originally authored (for example, following up on a subtle
  spec interaction in the author's fix to that exact thread), you may reopen
  that thread only by marking it explicitly — `- Existing Gerrit thread: root
  <root_id> (reopen)` on the synthesis card, `- Status: reopen — <concise
  reason>` with the exact `- Latest comment id: <latest_id>` verified against
  `comments.json` under `### Thread <root_id>`, or `- Reply-To: root <root_id>,
  latest <latest_id>, reopen` at the thread root's exact `path:line`. Never
  reopen a resolved thread for an unrelated new finding, never attach `-
  Reply-To:` to a `### path:line` inline comment whose `path` or `line` differs
  from the thread root's location, and when an open thread is awaiting a
  decision from the reviewer running the review (`Reviewer email` in `pin.md`),
  present a `[Reviewer decision on thread <id>: Option A ... / Option B ...]`
  placeholder in `## Main comment` instead of writing third-person `"awaiting
  reviewer confirmation"` or posting a prescriptive agent reply.
