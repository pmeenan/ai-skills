# Shared discovery decomposition contract

Use `decompose-scaffold`; fill its existing rows instead of creating a new
shape. Every profiler root/hotspot must have exactly one `primary` owner.

## 4-Layer Architectural Investigation Framework

Investigators must inspect the call tree and source code **from the root of the event down to the leaves**, asking four questions in order:

1. **Layer 1: Subtree / Branch Elimination (Highest Leverage)**
   - *Can this entire operation or subtree be skipped completely?*
   - Examples: Dirty flags, change detection, empty-collection fast exits, skipping tree-scope hierarchy traversal when no shadow roots exist.
   - *Impact:* Eliminates 100% of the downstream call tree.
2. **Layer 2: Higher-Level Caching & Sharing**
   - *Did we already compute this exact state for an identical element, subtree, or layout pass?*
   - Examples: Style sharing between sibling elements, text shape caching for identical runs, layout constraint memoization.
   - *Impact:* Bypasses expensive re-computation across repeated components.
3. **Layer 3: Algorithmic & Structural Hoisting**
   - *Can we replace loops, linear scans, or dynamic allocations with O(1) structures?*
   - Examples: Bitmasks/bloom filters before scanning RuleSet vectors, flat arrays over tree traversals, avoiding stack HeapVector allocations.
   - *Impact:* Drops algorithmic complexity from O(N) to O(1).
4. **Layer 4: In-place Leaf Optimizations (Lowest Leverage)**
   - *Only if Layers 1–3 cannot eliminate the work: is the leaf execution tight?*
   - Examples: Inlining, removing indirect virtual dispatch, branch hints.
   - Rarely clears a story floor; the discarded catalog is mostly Layer 4.

**Layer 1 and 2 claims are measured, not typed.** Before `decompose`, the
investigator instruments the site with `redundancy_probe.h`, runs the target
story, and reduces the browser log with `redundancy_evidence.py`. The proposal
cites the packet as `redundancy_evidence: {path, sha256}`; `decompose`
verifies the digest and refuses an `estimated_avoidable_fraction` above the
measured `applicable_fraction` / `repeat_fraction` (plus 0.05 tolerance).

## Per-Story Silo Decomposition & Target-Story Impact Ranking

Speedometer 3.1 has 20 default workloads matching Pinpoint and 32 available
with explicit `--stories=all`. Each selected story is profiled and explored as
an independent silo (`analysis/stories/<story>/`), which gives clean local
reads and avoids geometric-mean dilution.

1. **Local Story Floor (calibrated):**
   Each story's renderer main-thread stacks are decomposed in isolation, with the 100-nominal-samples quality gate applied per story. The qualification floor for a story is max(campaign share floor, 2 × that story's calibrated MDE); `campaign.py calibrate` records the MDEs and `campaign.py status` shows the floors. Entries flagged `platform_sensitivity` (canvas flush, raster, paint playback, font shaping, IPC) are Pinpoint-first leads, not local candidates.

2. **Global Ranking by Target-Story Impact:**
   Every frontier entry is story-qualified (`story:<name>/…`) and carries a `target_story`. The ledger ranks all opportunities globally by:
   $$\text{Estimated Target-Story Impact} = \text{Local Story Share} \times \text{Avoidable Fraction}$$
   measured against the entry's own target story. Keep observations story-qualified, then combine the same mechanism across stories using the causal opportunity budget in `measurement-policy.md`; CPU shares alone do not predict score movement.

3. **One Mechanism Key Per Invariant, Across Silos:**
   A source-level mechanism keeps one stable global `component/strategy` key even when it is discovered in several story silos. When the top-ranked entry's mechanism already exists in the ledger (landed, rejected, or in flight from another story), link the discovery to that mechanism (`known` disposition / `covered-by`) instead of creating a duplicate; sizing and verification then run against the highest-impact target story. Do not retry landed, rejected, or reverted mechanisms from a different story without genuinely contradictory new evidence.

## Opportunity Investigation Proposal

Each investigated opportunity must be recorded as an investigation proposal containing:
- `opportunity_id` and stable `component/strategy` mechanism key.
- `subsystem`: e.g. `style`, `html-parser`, `events`, `layout`, `dom`.
- `target_story`: the single story the opportunity targets; its silo profile sources every share and its `--stories=<target_story>` runs size and verify the mechanism.
- `investigation_layer`: 1, 2, 3, or 4 (favoring Layers 1 & 2).
- `target_stack_pattern`: exact regex / frames matching the target story's `profile.collapsed`.
- `story_profile_share_pct`: exact profile share (%) within the target story's silo.
- `estimated_avoidable_fraction`: fraction of that stack that can be avoided (0.0 to 1.0).
- `estimated_local_story_impact_pct`: `story_profile_share_pct * estimated_avoidable_fraction` (the global ranking metric; never rescaled to a full-suite share). `campaign.py decompose` derives the profile share from bound `work_refs`, recomputes this product, rejects mismatches and anything below the story's qualification floor, and stores it as the mechanism priority together with `qualification_floor_pct` and its basis.
- `redundancy_evidence`: `{path, sha256}` of the `redundancy_evidence.py` packet for the probed site (required for every `novel` / `known` row whatever its `investigation_layer`, and for every `mandatory` / `no-qualifying-mechanism` row at or above its story floor). A layer label is not a count.
- `packet_hypothesis` (novel/known rows): `applicable` (default; the fraction is bounded by the packet's `applicable_fraction`: calls that could have been skipped) or `repeat` (bounded by `repeat_fraction`: the keyed inputs recurred, and the row text says which key and why recurrence is avoidable). A packet whose `applicable` predicate held on every call supports no `applicable` claim.
- `existing_mechanism` (novel rows): the Chromium code that already avoids this work (a symbol or file) and the count showing it does not here, or "none" with the count that proves the repetition. Most redundancy has a partial existing answer (`InlineNode::ShapeText` reuse, `LayoutResult` cache, `PendingLayer::Matches`); a candidate that does not name it is not vetted.
- `wrapper_of` (mandatory/no-qualifying rows): the 1-based index of the dominant descendant row (≥ 80% of this row's share) whose count closes this row. A wrapper of a `novel`/`known` row is `covered-by` instead.
- `win_shape`: `skip-subtree`, `reuse-result`, `representation`, or `shorten-wait`.
- `subtree_pruned`: list of child functions and their combined profile share eliminated.
- `invariant_description`: exact code condition, bypass logic, and invalidation rules.
- `safety_and_spec_analysis`: explicit reasoning on HTML/DOM/CSS spec compliance and lifecycle safety.

## Dispositions

| Disposition | Use only when | Required evidence |
| --- | --- | --- |
| `novel` | one new invariant can remove the work (must pass Adversarial Qualification) | stable `component/strategy` key, 4-layer proposal, primary work reference, `existing_mechanism`, and a bound packet from a probe on this row's work whose named number supports the fraction |
| `known` | the exact mechanism already exists in the ledger | existing mechanism key, matching work references, and the same bound packet as `novel` |
| `covered-by` | the samples are literally the same samples as another row | owning mechanism key; `decompose` checks the story's `profile.collapsed`: at least 80% of the samples carrying this row's anchor must also carry the owner's anchor **and** a frame of the owner's probed function (`probe_symbol` of the owner's packet), so a caller holding other work, a sibling phase, or everything under a shared ancestor cannot be covered; an owner without a counted probe covers nothing |
| `mandatory` | the per-trigger amount of work is invariant (each call does new work) | at/above the story floor: a bound redundancy packet from the target story with `story share × supported avoidable fraction < floor`, or `wrapper_of` a counted row; below the floor: the invariant and source evidence. A spec clause names the trigger, never the amount |
| `no-qualifying-mechanism` | a bounded search found no invariant that removes enough work | the investigation packet (revision, hypotheses, falsifications, budget, stop reason) **and**, at/above the floor, the same bound packet and arithmetic as `mandatory` |
| `out-of-scope` | the work is not Chromium-owned or not within the campaign goal; a V8/JS **hand-off** row names the owner and quotes the lens numbers so exhaustion is scoped honestly | ownership/critical-path evidence, lens numbers |
| `below-floor` | the estimated impact is below the story's qualification floor (max(share floor, 2 × calibrated MDE)) | profiler work reference, measured share and the floor basis |

Do not use `covered-by` for a semantically adjacent caller, wrapper, or later
stage. Do not combine distinct hotspot keys into one primary path. Reconcile
every known/parked mechanism explicitly. A nested hotspot the lens marks
`promoted` (a different lifecycle phase than the area's root, above the
floor: ink-overflow work inside a hit-test lifecycle, layerization inside a
frame update) is its own path row with its own disposition, never folded into
the root's row. Every packet states inclusive and self share separately.

After all child mechanisms are terminal, bind the exhaustion review to the
exact decomposition:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py review-scaffold \
  --opp <discovery> --role skeptic --out <exhaustion-review.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py review \
  --opp <discovery> --role skeptic --verdict PASS \
  --report <exhaustion-review.json>
python3 .agents/skills/optimize-campaign/scripts/campaign.py exhaust \
  --opp <discovery> --reason <reason> --evidence <artifact-paths>
```

Any decomposition edit invalidates the prior review and requires a fresh
scaffold. `audit-exhaustion` is the final machine check.

## Closing by count

`decompose` refuses a `mandatory` or `no-qualifying-mechanism` row whose
profiler story share reaches the story floor unless it binds a
`redundancy_evidence` packet measured on the target story and
`share × supported_avoidable_fraction(packet) < floor`, where the supported
fraction is `max(applicable_fraction, repeat_fraction)`. A probe whose
`applicable` flag is always true, or whose key is a pointer that is new on
every call, bounds nothing and cannot close a row; the key names the inputs
the hypothesis says are unchanged (text hash, constraint space, font, sheet
list) and `applicable` states the condition under which the work could be
skipped. When the arithmetic does not clear the floor the row is a `novel`
candidate at that fraction, or the probe is re-keyed; it is never closed by
prose. A packet closes only the work it measured: it records the probed
function as `probe_symbol`, and `decompose` refuses it on a row whose
samples do not share that function in the story's stacks (80%, in either
direction). One low-fraction packet bound to every row of an area is
refused row by row. Pure wrappers of a counted descendant use `wrapper_of` instead of
their own packet; every hop of a `wrapper_of` chain must carry at least 80%
of the share of the row that started the chain (a run of gradually smaller
rows is not descent), and chains are at most four hops; wrappers of a
mechanism's samples are `covered-by`.

A candidate is a count too. Every `novel` and `known` row binds the packet
from a probe on its own work, whatever its `investigation_layer`; the claimed
fraction is bounded by the packet number the row's `packet_hypothesis` names
(`applicable_fraction`, or `repeat_fraction` when the row states the repeat
hypothesis). Marking the area root `novel` and covering every other row by
it is refused twice: the root has no packet, and a `covered-by` row must sit
under the owner's probed function, not merely share an ancestor with it.

A packet's unit of count is the unit of work it bounds. A probe at the
update root (`Document::UpdateStyleAndLayout`, `RequestMainFrameUpdate`)
counts updates: its `applicable` (nothing dirty) can close the root row as
`mandatory`, but it says nothing about how many elements, boxes or fragments
each update touched, so it does not close the rows beneath it even though
they sit under the probed function. Those rows close by a probe at the
phase whose unit is theirs: `Element::RecalcStyle` per element (`applicable`
= computed style unchanged), `BlockNode::Layout` per box (`LayoutResult`
cache miss with identical inputs), `UpdateCcPictureLayer` per fragment
(display items unchanged). The reviewer compares the packet's
`calls_per_repetition_mean` with the phase's unit count before accepting a
bound descendant row.

A packet measures time, not calls. Every call at a probed site is recorded
through `RedundancyScope` (redundancy_probe.h) around the work the
hypothesis would skip, so the packet carries `applicable_time_fraction` and
`repeat_time_fraction` beside the call fractions. `decompose` refuses a
count-only packet at or above the floor; a candidate's fraction is bounded
by the smaller of the call and time fractions for its hypothesis, and a
`mandatory` row closes only when the larger of them keeps `share x bound`
below the floor. A root update that finds nothing dirty on 92% of its calls
and 5% of its time is a 5% claim. A `repeat` hypothesis on a key that takes
fewer than two distinct values per repetition (an object pointer) is refused:
it names no input.

A packet is a reduction, never a file. `decompose` reduces every bound
packet's `sources` again with `redundancy_evidence.py` on the ledger host
and refuses the packet if any derived field (repetitions, calls, fractions,
overflow) differs; a log that does not resolve or whose digest changed is
refused; the recorded `patch` must resolve, match its digest, and define a
`RedundancyCounter` for the packet's site. A packet written by hand, with a
zero fraction typed where the log says otherwise or a site the twin never
counted, is fabricated evidence and ends the request.

Reviewer reports are immutable. Every report the ledger host sees is
registered under its reviewer task id with the digests it attested
(`reviews/gate-report-registry.json`); the same task id attesting a
different artifact set, or a different opportunity, is refused. Changing the
children file after the reviewers ran means running both reviewers again
with new task ids and transcripts. A transcript is the reviewer's own work:
the file the report names, at least 4000 bytes, mentioning every attested
digest and every check. The orchestrator never writes a reviewer report or
transcript; a report it authored is a forged review whatever the gate says,
and the audit reads the transcripts.
