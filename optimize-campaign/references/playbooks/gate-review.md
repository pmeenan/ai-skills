# Campaign independent gate challenge playbook

Run two read-only reviewers before the orchestrator accepts every campaign
gate. These are reasoning challenges in addition to the machine gate; they do
not waive or replace it.

Give both reviewers the gate name, opportunity/profile/checkpoint id, exact
artifact paths, current ledger/STATUS paths, and the command that will consume
the evidence. Do not give either reviewer the other reviewer's conclusion.

The orchestrator must actually invoke two distinct read-only subagent tasks;
it may not author either response itself. Preserve each real task id and
transcript reference with the review. Do not invent signatures or tokens: a
filesystem schema cannot authenticate model identity, so reviewer separation
is an orchestrator responsibility and the transcript is the audit trail. The
transcript must be openable on the ledger host: pass the reviewer's
transcript or notes file as `--gate-<role>-transcript` at import (it is
copied to `<campaign>/reviews/transcripts/`), or make `transcript_ref` a path
that already resolves there. An unreachable transcript is refused.

## Profile and reprofile gates

Generate each report with `campaign.py profile-review-scaffold --role <role>
--areas <reconciliation> --capture-summaries <captures> --lens <lens.json>
--out <report>`. It binds the digests and lists the checks; the import
refuses a PASS unless every check is true with its own evidence sentence
naming an artifact and a number read from it (no sentence reused, no
"REPLACE" left). The skeptic checks calibration, per-story sample power,
capture independence, exact-window scope, build fidelity, quantified
overhead, ownership and hand-off shares, every recurrence exclusion against
the other capture's inventory, three stories decomposed one level, and the
lens coverage's unexplained share. The adversary checks surface identity,
sha and features, raw artifacts opened, no probe inside scored work,
exclusions that hide no work, lens consistency with the frontier,
recomputed digests, and captures not reused. `what_this_frontier_establishes`
replaces the speedup sentence: a frontier proves coverage, not a speedup.
Objections the reviewer raised and then resolved go in
`resolved_challenges`; an open objection is a CHALLENGE verdict.

## Decomposition gate

Generate each report with `campaign.py decompose-review-scaffold --opp <id>
--role <role> --children <paths.json> --out <report>`. It binds the children
digest and the capture provenance digests, lists the rows at or above the
story floor with their dispositions and bound packets, and lists the checks.
The import refuses a PASS unless every check is true with its own evidence
sentence naming an artifact and a number. The skeptic checks bijective
accounting, that every row above the floor closes by a packet, a
`wrapper_of` chain or list (a list's rows together cover 80% of the
wrapper's samples, overlapping rows counted once, with a packet the wrapper
binds covering the rest below the floor), a split row's `ancestor_union`
(each caller's part below the floor by its own bound; a packet above those
callers is farther and refused), `covered-by` or a
mechanism row, that every bound
packet's probe key and `applicable` predicate (quoted from the probe patch)
answer the row's hypothesis, that every novel/known row sits on the probed function's own row (never an
ancestor of it) and binds a time-weighted packet from
a probe on its own work and claims no more than the time fraction its
`packet_hypothesis` names (rounding, not a 0.05 tolerance) (a scope that covers less than
the work the hypothesis would skip understates the time and is refused;
a predicate that reads a flag another function left behind is refused; a
predicate that is a literal `true` or `false` is refused; a `repeat` key
that is the object alone, or the inputs alone without the object, is
refused; a "nothing dirty" predicate that reads one frame's document
while the phases run for the frame tree is refused), that every bound packet's `packet_time_coverage` is near 1 and
the pre-check's coverage table has no packet timing a fraction or a
multiple of its function, that every count quoted in an `existing_mechanism`
sentence is the packet's count (calls per repetition, applicable, repeat)
and not a typed one, the recomputed floor arithmetic for every bound and
novel row, and for every novel row the existing Chromium code that already
avoids the work and the count showing it does not here; for every
`algorithmic` row, that the cost packet re-derives from the story's
collapsed stacks, that `avoided_frames` name frames the packet lists and
their summed fraction bounds the claim, and that the hypothesis states what
the cheaper algorithm computes and why the result is the same; and for
every mandatory row at or above 5% of the story, which of the three
"where the time goes" forms it carries (an `investigation` binds the row's
cost packet and quotes its frames; the closing count's repeat fraction
repeated is not one); that no `out-of-scope` row names Blink or cc code;
and that no `mandatory` row, whatever its share, lacks a packet or a
`wrapper_of` (a row nothing counted is `below-floor`); that every row whose
own function carries a counter binds that counter's packet (never
`wrapper_of`) and, if mandatory, clears the floor on every site of that
function; that every mandatory row binds the nearest packet on its stack
(the probed function whose weight is nearest the row's, not the farthest
ancestor that reads lowest), that no per-update packet closes a row that
is less than a third of the update, and that no row at 5% or more closes
on an ancestor's count with no probe beneath it; that every packet's
`probe_symbol` is the function the scope is in (a scope in an inlined
callee names the enclosing frame as `probe_symbol` and the callee as
`scope_symbol`, which the patch's hunk must show, and its bound is scaled
by its coverage) and its coverage is judged against the story's
largest-share packet on the build, bound or not; that every packet on the
build re-derives from its logs whether or not a row binds it; that every
row's anchor is the function its work refs name; and that every site that ran in the story is named by a packet on
the build. A row whose anchor
is the area root or the frame update, marked novel with every other row
covered by it, is a mechanically generated file, not a decomposition. A
packet from a probe at the update root bound to the rows beneath it is
refused by the skeptic: its unit of count is the update, not the element,
box or fragment those rows are made of (`calls_per_repetition_mean` tells). The
adversary checks the probe patch digest against the packets and the twin
build (every packet's `build_id` is the build id of the `chrome` binary
that ran, `readelf -n`, and one patch maps to one build across the
request), packet sources against the logs on the host, every packet's counts
re-derived from its log (`decompose` does this mechanically; the adversary
confirms the log is the twin run it claims to be), the children digest recomputed at review time, and
that no row above the floor is closed by prose. A reviewer who cannot open
the probe patch or the log does not PASS.

The report attests one children digest. If the children file changes after
the review, the review is void: `decompose` registers every report by
reviewer task id and refuses a task id that reappears with different
digests. Editing a report's digests is not a re-review. The transcript
passed as `--gate-<role>-transcript` must be the file the report's
`transcript_ref` names, at least 4000 bytes, and it must mention every
attested digest and every check by name; a verdict summary is refused.
None of this proves the reviewer was a separate task: an orchestrator that
fills in the scaffold, invents a task id and writes a six-line transcript
has forged the review, and the human audit treats the whole import as
unreviewed.

## Skeptic perspective

Try to disprove the claimed performance conclusion:

- **preflight/profile:** exact score-window scope, equal suite weighting,
  capture independence, sample power, frontier completeness, build fidelity;
- **decomposition/sizing:** one invariant, target-story profiler share,
  plausible avoidable fraction, machine-recomputed local-story impact and
  floor, measured applicability, oracle validity, overlap, critical-path
  classification, CPU share versus score;
- **candidate:** paired identity, positive lower bounds, moved work, probe tax,
  code-size/cold-path tax, distinct product trees/binaries;
- **checkpoint/pilot:** `out/release`, exact preregistered target-story set for
  targeted gates, full-suite scope for regression gates, block balance, MDE,
  CI, fresh seed, cumulative direction, multiple testing, practical effect size;
- **reprofile/exhaustion:** residual work, stale evidence, hidden known paths,
  and whether stopping is supported by the latest enabled profile.

## Adversarial perspective

Try to find a way a lazy or goal-misaligned agent could have satisfied the
artifact shapes without making Chrome faster:

- comment/whitespace/test-only changes or bundled unrelated mechanisms;
- synthetic/copied logs, placeholder suites, fake commands, stale binaries,
  wrong trees, hand-authored provenance, or probes included in scored work;
- benchmark strings/data-shaped special cases, behavior changes, feature-off
  drift, lifecycle/security/privacy regressions;
- selective reruns, copied checkpoint numbers, favorable-seed hunting, or
  treating patch count as the objective.

## Output contract

Return only:

```json
{
  "schema_version":1,
  "role":"skeptic|adversary",
  "reviewer_task_id":"real subagent task id",
  "transcript_ref":"real task/transcript reference",
  "gate":"preflight|profile|decomposition|sizing|candidate|checkpoint|reprofile|exhaustion",
  "artifact_digests_checked":["sha256:..."],
  "verdict":"PASS|CHALLENGE",
  "challenges":["specific artifact-backed issue"],
  "why_this_proves_real_speedup":"one concise sentence or empty on CHALLENGE"
}
```

PASS is not “the files exist.” It means the reviewer independently opened the
raw evidence and found no credible path by which this gate could pass without
the claimed real-world conclusion. Every challenge and every
`artifact_digests_checked` entry must be a real digest from the bound
artifacts; the orchestrator rejects reviews that repeat one sentence or cite
nothing that can be opened. Skeptic and adversary reviews of profile,
decomposition and sizing gates are the three places to use the strongest
available model. A CHALLENGE pauses the orchestrator until
the evidence is regenerated, the candidate is rejected, or the concern is
explicitly shown irrelevant. No prose review can turn a failed machine gate
into a pass.
