# Skill Eval Corpus

Regression evals for the chromium-code-review skill. Every measured run that
produced a miss, a false positive, or a process failure becomes an
expectation file here; before landing a prose change to the skill, re-run the
affected evals and confirm the expected findings still surface.

The war stories embedded in the skill prose ("a measured run…") ARE this
corpus in informal form — each should eventually correspond to a scored row
in one of these files, so that a wording change can be tested with "did this
edit lose the discarded-`Push`-return P0?" instead of being discovered on the
next live review.

## Files

- `TEMPLATE.md` — copy for each new eval CL.
- `cl-<number>.md` — one file per measured CL, with must-find findings and
  known traps.
- `cl-8017223.md` — cross-layer lifetime/style false-positive and root-family
  compression eval for delayed datagram shaping.
- `cl-8020646.md` — pinned PS4 follow-up eval with exact PS4/PS3 revisions.
- `corpus-from-skill-prose.md` — the backlog: every measured failure
  currently cited in the skill prose, awaiting its CL number and promotion
  into a per-CL file.
- `process-contracts.md` — executable validator, script-smoke, and resume
  drills that require no invented Gerrit pin.

## Running an eval

1. Fresh session (no conversation carry-over), model under test, subagents
   available unless the eval says otherwise.
2. Invoke the skill exactly as a user would: "review CL <number> patchset
   <n>", pinned to the patchset and revision the eval file names — reviews of
   later patchsets are not comparable. Verify `pin.md` before scoring.
3. Score the final review against the eval file:
   - **found** — the finding appears with correct location and severity
     within one level.
   - **found-miscalibrated** — appears, but severity is off by more than one
     level or the blocking/non-blocking call is wrong.
   - **missed** — absent from findings, questions, and verification notes.
   - **false positive** — asserts a listed trap, or any new claim a code
     trace refutes.
   Also score process compliance: selected SHA pinned; roster complete in
   `plan.md`; `orchestration.tsv` attempt/dependency queue consistent; one
   subagent per triggered entry; proved not-applicable rows are distinct from
   unreviewed scope; profile/topology and input budgets match the diff; derived
   indexes are fresh; ledger and canonical reopened rows collected;
   reconciliation table complete; bounded synthesis/challenge artifacts
   complete; pre-output and post-synthesis delivery gates honest.
4. Append a dated results block to the eval file (model, scores, notes).

Never edit expected findings to match a run. If a run disagrees with an
expectation, either the skill regressed or the expectation was wrong —
decide by re-tracing the code, not by majority vote of runs.

Do not create a per-CL eval from a likely/guessed CL number or an unrecorded
patchset. Leave it in the backlog and use `process-contracts.md` for workflow
coverage until the exact revision and findings are recovered.

## Adding a CL

Copy `TEMPLATE.md` to `cl-<number>.md`, pin the patchset (number + revision
SHA), list the must-find findings — each with the roster thread that owns it,
so a miss also names the thread that failed — and the known traps (false
positives and severity inflations prior runs produced).
