<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## verification/affinity.md — Invariant Affinity And Consistency Audit

After all skeptic batches collect, one global Invariant Affinity Reconciler
reads the compact indexes and selected descriptor/closure rows. It assigns
every CONFIRMED or UNPROVEN candidate/verdict pair to exactly one root family
before root-cause planning:

```markdown
# Invariant affinity — CL 9999999 PS3

## Root families

| root family | members | shared invariant | invariant owner | state / transition | fix layer | related symbols | disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RF001 | EPW-2, V001-1, SMM-4, V004-1 | completion reports bytes accepted XOR an error | DelayBuffer completion boundary | backend failure → cleanup → completion | DelayBuffer::OnTimer | OnTimer, OnWriteFailure, DoWriteComplete | one root cause; method symptoms share owner and outcome |

## Consistency audit

| check | rows / families | evidence | result |
| --- | --- | --- | --- |
| contradictory assumptions | RF001 | verification/V001.md:/Trace-closure; verification/V004.md:/Trace-closure | consistent — both traces use the same completion contract |
| invariant-owner collisions | RF001 | delay_buffer.h:61-75 | one owner |
| style-authority scope | all style candidates | evidence-exception:no-style-candidates | no surviving style-only claim |
| lifetime operation owner | all async-lifetime candidates | evidence-exception:no-async-lifetime-candidates | none surviving |
| reachability termination | RF001 | delay_stream.cc:71-91 | trace reaches production consumer |
| repeated local fixes | RF001 | delay_buffer.cc:180-205 | one completion-boundary fix covers the affected methods |
```

All six audit rows are mandatory, using a cited `evidence-exception:` only
when the relevant class is truly empty. The global pass compares batches for
contradictory assumptions, shared invariant owners, directory-specific style
authority, untraced async operation ownership, reachability that stops at the
changed wrapper, and repeated local fixes that should collapse into one
interface/state fix. When input is large, shard descriptor extraction only;
family assignment and the consistency audit remain global over compact rows.
Rebuild indexes afterward so surviving verdicts carry `root_family`.
When all candidates are refuted, keep the same `## Root families` table with
headers and zero rows, and still write the six audit rows; zero surviving
families is not permission to skip the cross-batch consistency check.
