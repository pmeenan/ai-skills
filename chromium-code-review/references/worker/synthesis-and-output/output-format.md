<!-- Generated from ../../synthesis-and-output.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Synthesis And Output

This file is executed by the late-phase worker agents: the
Reconciliation-Builder, the Draft-Writer, and the Synthesis Challenger. The
severity section also binds verification skeptics, whose CONFIRMED verdicts
must name an anchor from the table below. The orchestrator does not load
this file. Artifact shapes live in `references/templates.md`; the
contradiction checklist and Gerrit output rules live in
`references/verification-and-fixes.md`.

## Output Format

Format the final review as:

Start with `- Draft revision: ⟨n⟩`. This control field binds the current draft
to its immutable challenge round and delivery gate; it is not Gerrit prose.

1. **CL-Introduced Issues & Suggestions:** Findings introduced by the CL, ordered
   by severity, with file/line references and actionable guidance. Separate blocking
   issues from optional polish. In follow-up reviews, label
   `introduced-in-PS<N>` findings as such within this section.
2. **Pre-Existing Codebase Issues (For Reference/Follow-up):** Issues observed
   in the surrounding codebase but not introduced by the CL. These must be clearly
   labeled as pre-existing and do not block landing of this CL.
3. **High-Level Summary:** State whether the CL accomplishes its goal, name the
   patchset and revision SHA, and summarize bug alignment.
4. **Prior Review Follow-Up:** If prior issues were supplied, summarize their
   status with evidence.
5. **Positives:** Briefly note important good decisions. A praised safety
   property is a claim like any other — name its guard line. (A measured run
   praised "failures fail open safely" about the exact branch that treated a
   failure as success.)
6. **Questions:** Only questions whose answers affect correctness, API contract,
   or landing readiness. Every UNPROVEN verdict lands here. Each question
   carries its originating row/verdict ID trail (e.g. `Rows: AL-7 / V003-2`) —
   internal, like the finding trail; omit it from Gerrit-facing text — so the
   pre-output gate can prove no promoted card was dropped.
7. **Verification Notes:** State tests run or not run, production wiring traced
   or not traced, and any important areas not verified.
   - Name subagents by human-readable thread name (e.g. "the Error-Path Walk
     thread"), never by internal conversation IDs or task UUIDs.
   - Claim test execution only if the exact commands ran successfully against
     the pinned patchset; otherwise state: "No local test execution was
     performed during this review."
   Reproduce the full thread plan from `plan.md` with each thread's outcome:
   rows returned (count), not-applicable (with trigger-absence proof), "terminated — scope
   unreviewed", or "interrupted — partial". Include each thread's
   human-readable name (mapped to its task identifier in `plan.md`), or
   "self-executed" plus the harness limitation that forced it. A proved
   not-applicable thread is not an unverified dimension; a trigger that was
   not evaluated is `unreviewed`, never `not applicable`. Any plan deviation —
   a folded or unspawned entry, a degraded file-access
   handoff — is disclosed here as an unverified area. On large CLs the full
   compliance matrices live in the review directory with Verification Notes
   pointing at it — every per-row answer must exist somewhere retrievable; a
   "combined audit summary" that discards rows defeats the accounting. Also
   state the root-cause/layering pass outcome: candidate count checked, any
   better owner or broader invariant found, and any discovery/verification
   rows reopened because of it.
8. **Next Steps:** State what is required before `+1 LGTM` and what is optional.

For full CL reviews, append compact **Gerrit-Ready Comments** unless the user
asks for a short summary only, following the Verdict Alignment And Gerrit
Output Rules section of `references/verification-and-fixes.md`:

- **Main body:** brief landing-readiness summary, blockers, optional items,
  prior review status, and verification notes.
- **Replies to existing unresolved threads:** file and thread line, status, and
  the exact response, using normalized root/latest IDs from
  `gerrit/unresolved-threads.json`. Do not open duplicate new threads for an
  existing topic.
- **New inline comments:** repo-relative file, exact line or range, verbatim line
  text from the reviewed patchset, and concise comment text. When the finding's
  Suggested edit decision is applicable, attach the comment to that exact
  selected range and include its fenced `suggestion` block; Gerrit replaces
  the attached lines with the block contents. Prefix optional polish with
  `nit:`.

For Gerrit-ready text, cite findings as repo-relative `path:line` against the
reviewed patchset, extract quoted code verbatim, and re-check line numbers
before sending. Avoid leaking local filesystem paths in comments meant for
Gerrit.

`comments.json` is a map from path to CommentInfo arrays, not a globally
ordered list. Thread targeting uses the normalized
`gerrit/unresolved-threads.json`: comments are grouped by transitive
`in_reply_to` root, ordered within that group, and unresolved state comes from
that thread's latest comment. A response records both root ID and latest ID;
never infer thread state from the last entry in a file array or the change's
latest message.
