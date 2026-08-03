<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Skeptic Verdicts

Every candidate examined in verification gets exactly one verdict row in
its batch's `verification/V⟨batch⟩.md` file (shape in
`references/templates.md`), with ID `V⟨batch⟩-⟨n⟩` and a reference to the
candidate row under test. Three verdicts exist, each with mandatory
evidence fields — a verdict missing its fields is not a verdict:

- **CONFIRMED** requires: the completing trace
  (`scenario → lines visited → bad outcome`), a severity proposal matched to
  the anchor table in `references/synthesis-and-output.md` (name the anchor
  and argue any delta), and an
  origin label (`CL-introduced`, `introduced-in-PS⟨N⟩`, or `pre-existing`).
- **REFUTED** requires: the guard's `path:line`, documented design contract/comment citation, or the concrete safe trace
  that completes without the bad outcome. For IF/THEN/UNLESS hypotheses,
  refutation means filling the UNLESS with a citation. Speculative "looks handled" or
  "the caller probably checks" are not refutations; explicit code comments, documented invariants, or proof of safe/idempotent execution are valid refutations.
- **UNPROVEN** requires: what was traced, what remains unproven, and a
  drafted question for the CL owner. UNPROVEN rows go to the review's
  Questions section — never to the bin.

Each verdict file also contains `## Trace closure` and
`## Verified affinity`. Emit exactly one closure row for every obligation
declared by that candidate—no omissions and no invented extras. Results are
`PROVES CANDIDATE`, `REFUTES CANDIDATE`, `NEUTRAL`, `OPEN`, or
`NOT APPLICABLE — reason`, each with code evidence or an explicit
`evidence-exception:`. CONFIRMED/REFUTED may not retain OPEN obligations;
UNPROVEN must name at least one. Verified affinity restates or corrects the
base/interface, invariant owner, violated invariant, state/transition, likely
fix layer, and related symbols after tracing.

A skeptic that cannot produce REFUTED's required fields has confirmed the
finding, not dismissed it. When the decisive evidence legitimately has no
`path:line` — an absence proof ("no other caller exists": cite the search
run), tool output, or a spec/standard citation — write
`evidence-exception: <nonempty reason and the actual evidence>` in the
evidence field; the validator rejects CONFIRMED/REFUTED rows that have
neither a citation nor a nonempty exception, and an exception is itself a
claim the synthesis challenger may re-check. When verification runs without subagents, the
orchestrator holds itself to the same schema — one verdict row per
candidate, same mandatory fields.

A candidate with a proposed duplicate merge is the sole exception to the
one-verdict-per-candidate rule. It may share the surviving candidate's verdict
only after reconciliation verifies equal trigger, violated invariant, and bad
outcome, with citations. Similar location or fix is insufficient. A rejected
merge returns to verification; it is never silently dismissed.
