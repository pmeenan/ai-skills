<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Root-Cause Trigger Planning

The Root-Cause Planner reads the actual candidate and verdict files; the
orchestrator must not infer triggers from terse status messages. It writes one
Trigger Accounting row for every CONFIRMED or UNPROVEN verdict, every
candidate with a proposed fix, and every inventory scope marked `root-cause
required`. Inventory scopes ensure risky changes receive a layering pass even
when discovery found no defect candidate. Schedule root-cause work when any of
these is true:

- proposed P1 or P2;
- risky P3 whose severity depends on reachability or invariant ownership;
- any concrete fix recommendation, regardless of severity;
- performance optimization, flaky-test fix, async/lifecycle change,
  state-machine change, cache/throttle, persisted format, or new state holder;
- a candidate whose local symptom may be shared across caller families.

Rows that meet no trigger remain in the plan as `not applicable — trigger
absence proved by <T IDs>`. Inventory `required:T*` scopes whose `graph:E-*`
edges are all `closed` or `clean` in `indexes/topology.tsv` (for example after
discovery + verification or on a follow-up patchset with no open edges) may also
be closed in `## Trigger accounting` as
`not applicable — <cited edge/verdict/interdiff/file:line proof>` with `rc batch`
`—`. Non-risky `CONFIRMED` `P3` root families (`RF*`) whose fix or localized
defect was already validated in verification may likewise be recorded as
`not applicable — non-risky P3 validated in verification (<verdict_id>, <citation>)`
with `rc batch` `—` and bound in `synthesis/<ROW-ID>.md` with `- Root cause: none`
and `- Root family: RF<number>`. Batch scheduled work by related invariant and
trace cost, packing up to 4 small families or scopes per `RC*` batch when they
fit within budget; serious `P1`/`P2` candidates with broad call graphs may stand
alone, and no fixed quota may combine unrelated large traces. Keep every generated brief bounded. Assign
distinct zero-padded `RC001`, `RC002`, ... IDs. Generated root-cause briefs inherit the
common directives, authority boundary, append/retry, and partial-return
contract from templates.md.

Before this planning step, the global Invariant Affinity Reconciler assigns
every CONFIRMED/UNPROVEN candidate and verdict to one `RF<number>` family and
runs the six-row cross-batch consistency audit in templates.md. Root-cause
planning consumes whole families, not isolated line items. Sharding may extract
descriptors but may not make independent family assignments.
