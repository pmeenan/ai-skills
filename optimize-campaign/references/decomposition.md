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
| `mandatory` | the per-trigger amount of work is invariant (each call does new work) | a bound redundancy packet from the target story (at/above the story floor with `story share × supported avoidable fraction < floor`), or `wrapper_of` a counted row, whatever the row's share: a count is what makes a row mandatory, and a row below the floor that nothing counted is `below-floor`. A spec clause names the trigger, never the amount |
| `algorithmic` | the row closes by count (no skip, no reuse) and a cheaper algorithm or representation would do less of its work (Layer 3/4) | `mechanism_key`, `investigation_layer` 3 or 4, the same bound redundancy packet and arithmetic as `mandatory` (redundancy below the floor), `cost_evidence: {path, sha256}` from `campaign.py cost-packet` (the row's time by child and leaf frame from the story's `profile.collapsed`, re-derived at import), `avoided_frames` naming frames from that packet, `algorithm_hypothesis` (what the code computes, what the cheaper one computes, why the result is the same, the packet's fraction), `existing_mechanism`, and `estimated_avoidable_fraction` at most the avoided frames' summed fraction of the row |
| `no-qualifying-mechanism` | a bounded search found no invariant that removes enough work | the investigation packet (revision, hypotheses, falsifications, budget, stop reason) **and**, at/above the floor, the same bound packet and arithmetic as `mandatory` |
| `out-of-scope` | the work is not Chromium-owned or not within the campaign goal; a V8/JS **hand-off** row names the owner and quotes the lens numbers so exhaustion is scoped honestly | ownership/critical-path evidence, lens numbers. `decompose` refuses an anchor in an owned namespace (`blink::`, `cc::`; `config.in_scope_namespaces`): generated bindings, collections and DOM code are Chromium's and close by count, mechanism or cost claim |
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

A count closes a row for one hypothesis: the class the counter's key and
predicate test ([hypotheses.md](hypotheses.md)). A row closed on an ancestor's
packet is closed for the ancestor's hypothesis only; `campaign.py depth-audit`
lists, per story and phase, the rows above the floor in that position and the
classes no packet has probed for that phase, and exhaustion is refused while
it has open entries. Every packet records its class
(`redundancy_evidence.py --hypothesis-class`); the class it counts for is
the site's registered one (`campaign.py register-site`, host only), and a
candidate's claim follows it: `packet_hypothesis: repeat` is accepted on an
`unchanged-input` site only, and no claim is accepted on an unregistered
site.

A request binds packets from several builds (old rows keep their
packets); there is no "request build". Builds are ordered by the browser
logs their packets cite. A site's function and its readings are its
newest build's: a row on a function that any site's newest counter sits
in binds that site's newest packet for the story, and closes as
`mandatory` only if every such site's bound is below the floor (round 33:
a row on `InlineNode::ShapeText` closed on a round-32 counter reading
zero while a round-33 counter on the same function read 50%). An older
placement of a site name (a probe moved between builds) is superseded,
readings included. The sites-named rule checks the newest build the
request binds. A predicate that held on every call of a
notification-fanout, unconsumed-result, redundant-trigger or copy-churn
site bounds nothing but its key-repeat for closing: it separated nothing
(hypotheses.md).

## Suite-level qualification

The suite score is a geometric mean of the stories, so a mechanism's
suite impact is the mean of its per-story impacts (a story it does not
reach counts zero). The A/A calibration records a suite MDE beside the
story MDEs; the suite floor is twice it (`suite_floor_pct`). Every union
carries a `suite` summary (`suite_impact_pct`, `contributions`,
`qualifies_suite`), `probe-union-all` prints it (a `*` marks a site that
clears the suite floor), and `decompose` accepts a `novel`/`known` row whose
story impact is below the story floor when the site's suite impact clears
the suite floor: the row records `qualification_scope: suite` and the
mechanism carries `estimated_suite_impact_pct`. `suite-impacts` records
the number on every candidate mechanism, and the export ranks candidates
by it: the small things that add up across stories rank by their sum, and
a large single-story item ranks by its share of the suite.

`suite-frontier` lists every in-scope function whose mean inclusive share
across the suite clears the suite floor although no story floor admitted it
(the profile's own frontier holds the ones a story floor did); with
`--open` each becomes a suite-scoped discovery area in its home story (the
story where it is largest), its rows the frames beneath it in that story's
stacks at or above the suite floor. A suite area decomposes like any other;
its floor is the suite floor (`area_config`), so its rows close by count or
qualify at that floor, and its mechanisms are sized across the suite by the
union like every other. Functions the campaign has already judged (an anchor
of a row at or above its area's floor) or already probes are listed as such
and not reopened.

## Discovery phases

Discovery is three searches in a fixed order, each opened by the host
(`campaign.py open-phase --phase <suite|efficiency> --note "..."`) once the
previous one is exhausted; the ledger records the phase
(`discovery_phase`), the pre-check prints it, and `audit-exhaustion` is
not established until the last has run.

1. **redundancy** (the default): the story frontiers, every row at or above
   its story floor closed by count or claimed with a packet. Exhausted when
   every area is decomposed by count and `depth-audit` has no open class.
2. **suite**: `suite-frontier --open` for the functions below every story
   floor whose suite mean clears the suite floor; each suite area
   decomposes by count at the suite floor. Exhausted when no function on the
   suite frontier is OPEN and every suite area is decomposed.
3. **efficiency**: cheaper algorithms for the necessary work. An
   `algorithmic` row is refused before this phase, so the search for the
   large redundancies is never traded for micro-optimizations.

### The efficiency phase

The necessary work is what the counts closed: the `mandatory` and
`no-qualifying-mechanism` rows bound to a packet, a measured bound or a
`wrapper_of` (`counted_functions`). `efficiency-frontier` lists the counted
functions whose mean inclusive share across the suite clears the suite
floor, ranked by the share each carries outside every other counted
function (`frontier_exclusive_shares`: its own body and its small helpers).
A wrapper whose time sits in counted callees is `carried` by their areas
and gets none of its own. With `--open` (efficiency phase only) every OPEN
function becomes an efficiency area in its home story (where that
exclusive share is largest): one work ref, the function itself, the suite
floor as its floor, and `redundancy_closings` naming the rows that counted
it.

The counted frontier has two blind spots, both found in round 47: it ranks
by the suite mean only, so a function worth 3% of one story and 0.15% of
the suite never appears; and it lists only functions a counter sat in, so
a function closed on an ancestor's count is never read. `own-time-frontier`
covers both. It ranks every in-scope function, counted or not, by the time
in its own body (`frame_own_shares_cached`: the samples whose deepest
in-scope frame it is, with no foreign frame beneath; `frame_in_scope` sees
past a leading return type, which a namespace-prefix test misses). A
function is a row when that own time clears a story's qualification floor
in that story, or the suite floor as a mean, and is `answered` when an
efficiency area or a mechanism row already sits on it. `--open [--limit n]`
makes each OPEN function an efficiency area (`efficiency_basis: own-time`)
in the story where own time is largest against the floor. Exhaustion
counts OPEN and opened-but-unread own-time rows as blockers.

An efficiency area's one row says one of two things, and nothing else
(`enforce_phase_dispositions`):

- `algorithmic`: a Layer 3/4 change that computes the same result with less
  work. It binds a cost packet for the row in the home story
  (`cost-packet --opp <id> --children <file> --path 1`, cited as
  `cost_evidence: {path, sha256}`), names the `avoided_frames` the cheaper
  algorithm would not run, claims an `estimated_avoidable_fraction` the
  packet bounds (the avoided frames' summed fraction of the row), and states
  the `algorithm_hypothesis` (what the code computes, what the cheaper
  algorithm computes instead and why the result is the same, the packet's
  fraction). Its story impact is share x fraction; its suite impact is measured story
  by story (`algorithmic_suite_impact_measured`): the avoided frames' share
  under the function in each story's own stacks, times the part of the
  home-story ceiling the row claims, averaged over the suite. A **ranking**
  (`impact_basis`); sizing proves it. A row
  below the story floor and the suite floor is refused: a saving the
  measurement cannot read is not a candidate, and the row closes as the
  other kind with that algorithm as a falsified hypothesis.
- `no-qualifying-mechanism`: the investigation that found none, one
  structured hypothesis per place the row's time goes
  (`require_efficiency_investigation`). Each hypothesis is an object:
  `change` (what the function computes today, what the cheaper algorithm
  computes instead and why the result is the same, naming the code it
  changes: a symbol or file other than the row's own function, 80+
  characters), `avoided_frames` (the packet frames it would not run: its
  ceiling), `outcome` (`saves-less` with `saved_fraction`, what the change
  actually saves, below the story's qualification floor and the suite floor,
  or the row is `algorithmic`; `not-equivalent`, why the result would differ
  and the code that observes it; `already-done`, the code that already does
  it), `reason` (60+ characters naming a symbol or file) and `read`, the
  artifact of reading: `[{file, lines "a-b", symbol}]` for the function
  itself and every frame the hypothesis avoids, which the gate verifies
  against the checkout (the file exists, the range is at most 600 lines,
  the symbol's name occurs in it; `verify_reading`). Every child at or
  above 20% of the row, `(self)` included, has a hypothesis. A child
  whose whole share cannot qualify closes with outcome `ceiling` (its
  `avoided_frames` only): the gate checks that the frames' ceiling is below
  the story's floor and that their share measured in every story's stacks is
  below the suite floor; no change is invented and no fraction guessed for
  work that cannot matter. A change or
  reason written from another hypothesis's template, on this row or on any
  efficiency row on the ledger, is refused (round 37: twelve areas, one
  sentence). `stop_reason`, `budget_used` and `source_revision` stay on the
  investigation; it binds the same `cost_evidence`.

An `algorithmic` row whose `mechanism_key` already names an algorithmic
mechanism on the ledger is the same cheaper algorithm on another function or
story (round 40: the two template instantiations of the fast-path parser);
it reconciles as a known mechanism, and `suite-impacts` sums the mechanism's
distinct functions (the same function takes its largest claimed fraction).

An `algorithmic` row carries the same investigation: its own claim is the
hypothesis with outcome `algorithmic` (on the row's avoided frames), the
other children at or above 20% of the row have theirs, and every reading is
verified the same way.

A redundancy found while investigating efficiency belongs to the
function's row in its story or suite area (a `novel` row with a packet),
not to the efficiency area. An avoided frame that is another counted
function's is that function's own area's question; name the frames whose
time the row carries itself. `suite-impacts` records the ranking on
algorithmic candidates beside the union's on redundancy candidates, and the
export ranks them together by suite impact with `candidate_type` and
`impact_basis` telling them apart.

One site is one counter in one function. A site declared by several
counters (three overloads of one function under one name, round 32) flushes
several rows per scored window; the reducer merges them per window by the
patch's declaration count (`counters` in the packet), and refuses a row
count that is not a multiple of it. Without the patch every row is a
repetition and the packet reads a fraction of the function's time; the
union's coverage column shows it.

`decompose` refuses a `mandatory` or `no-qualifying-mechanism` row whose
profiler story share reaches the story floor unless it binds a
`redundancy_evidence` packet measured on the target story and
`share × supported_avoidable_fraction(packet) < floor`, where the supported
fraction is the larger of the packet's applicable and repeat *time*
fractions (the call fractions, for a count-only packet, which cannot close
a row at the floor anyway). A literal predicate (`true`, `false`, a
`/*applicable=*/true` argument) that held on every call measured nothing: a
saturated `applicable` (≥ 99.9%) drops out of the bound and the packet's
repeat *time* fraction is its supported fraction, a repeat count of zero
closing the row (a repeat-only counter declared `applicable=true` is sized
by its repeats, never at 100% of its function). An expression predicate
that held on every call measured everything: `FastGetAttribute(name) ==
value` true on 100% of a story's attribute sets is a finding, the gate
reads the patch to tell the two apart, and such a row does not close as
mandatory (it is a candidate at the applicable time fraction). A key that is a
pointer new on every call (fewer than two distinct values per repetition on
a site called fewer than ten times) bounds nothing either way; the key
names the inputs the hypothesis says are unchanged (text hash, constraint
space, font, sheet list) and `applicable` states the condition under which
the work could be skipped. When the arithmetic does not clear the floor the
row is a `novel` candidate at that fraction, or the probe is re-keyed; it is
never closed by prose. Every site with calls in the request's story on the request's build has a
packet for that story on that build (`redundancy_evidence.py --target-story
<story> --symbol <its function>` per site, one script for all of them): the
nearest-packet rule, the callers' union and the coverage reference see only
the packets that exist, and a site reduced in one story leaves every other
story's checks blind. A packet closes only the work it measured: it
records the probed function as `probe_symbol`, the C++ function the
counter's scope is compiled into (with `--scope-symbol`, the function that
scope is inlined into; never a V8 builtin or a JS frame above it, which
carries every API call), and `decompose` refuses it on a row whose samples
do not share that function in the story's stacks (80%, in either
direction). A row on the scope's own function binds the packet reduced on
that function, not one scoped from a frame above it: the coverage band
judges the timer against that function's profile share, and a timer far
above it (the probe's own key and predicate inside the scope) is a probe
defect for the next build, not a symbol to shop for. A row whose samples split between several probed
callers (a paint-op allocator under both `stroke` and `fill`) belongs to
none of them at 80%; it binds the packet of its largest caller and closes
on the callers' union when the story's probed functions together cover 80%
of its samples and every caller's part closes by that caller's own bound
(`share × part × supported < floor`; `decompose` records `ancestor_union`).
A part that does not clear the floor is that caller's candidate work,
claimed on its own row. A packet above those callers (the event dispatch
or the frame update every sample carries) is farther than they are and is
refused for such a row: the nearest-packet rule sends the row to the
callers' union (`explain` prints the callers, their union and its bound;
`--path all` explains every row of a file in one run).
One low-fraction packet bound to every row of an area is refused row by
row. Pure wrappers of a counted descendant use `wrapper_of` instead of
their own packet; every hop of a `wrapper_of` chain must carry at least 80%
of the share of the row that started the chain (a run of gradually smaller
rows is not descent) and sit beneath it in the story's stacks (the target's
frame below the wrapper's on at least 80% of the wrapper's samples: a row
naming its own caller, whose share is nearly its own, is refused), and
chains are at most four hops; wrappers of a
mechanism's samples are `covered-by`. A row whose time splits across
several counted rows beneath it (a style phase that is 70% recalc-style and
25% layout-tree rebuild) names them all: `wrapper_of: [15, 44]`. Each named
row is another function, dispositioned on its own (a counted mandatory row,
a candidate, a `covered-by` row, or a row below the floor) and not a
wrapper itself; together they carry at least 80% of the wrapper's share;
and together they cover at least 80% of the wrapper's samples in the
story's stacks (`enforce_wrapper_descent`: of the samples carrying the
wrapper's anchor, those carrying a named row beneath it, each sample
counted once, so two nested recursion contexts of one function cover what
they cover, not the sum of their shares). What the named rows do not cover
is uncounted. The wrapper may bind the packet of the probed function that
carries that remainder (`redundancy_evidence` on the wrapper itself, a
rebuild packet under a style phase whose recalc rows are named): the probed
function's samples beneath the wrapper count as covered, and that part
closes by the packet's bound (`share × part × supported < floor`) or it is
a candidate on its own row. Coverage under 80% is accepted only when the
uncovered part of the story (`share × (1 − coverage)`) is below the story
floor: nothing the campaign could act on lives there.

A candidate is a count too. Every `novel` and `known` row binds the packet
from a probe on its own work, whatever its `investigation_layer`; the claimed
fraction is bounded by the packet's *time* fraction for the hypothesis the
row's `packet_hypothesis` names (`applicable_time_fraction`, or
`repeat_time_fraction` when the row states the repeat hypothesis): the same
bound the closing check uses, so a row is never trapped between a closing
bound that says it qualifies and a claim bound that says it does not (the
round-21 Stockcharts out-of-flow row: repeat 0.62 of calls, 0.80 of time,
and a claim of 0.65 typed to clear the floor). A claim may be lower than the
bound, never above it by more than rounding (0.005); the old 0.05
tolerance was a lever. Marking the area root `novel` and covering every other row by
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
by the *time* fraction for its hypothesis, and a `mandatory` row closes
when the larger of the two *time* fractions keeps `share x bound` below
the floor (once time is measured, a call fraction says
nothing about time: a repeated request that hits a cache is counted and
costs nothing). A root update that finds nothing dirty on 92% of its calls
and 5% of its time is a 5% claim. A `repeat` hypothesis on a key that takes
fewer than two distinct values over a handful of calls per repetition (an
object pointer seen three times) is refused: it names no input. A hundred
calls per step sharing one key value is the finding, not a pointer.

The `applicable` predicate is computed from the call's own inputs. A flag
left behind by another function (the last document update's clean bit read
by the frame update) is that call's state, not this one's; a predicate that
reads thread-global state written elsewhere measures nothing about the
call it is attached to, and the reviewer refuses the packet on reading the
patch.

A row binds the nearest probe on its stack. When a probed function with a
time-weighted packet for the story sits between a `covered-by` row and its
owner's probed function in 80% of the row's samples, or the row is that
function, `decompose` refuses the coverage: the nearer packet measured the
row's work, so the row binds it (`mandatory` by its bound, or a candidate
at its fraction) or is covered by that packet's row. Once the style, layout
and paint phases have probes, an update root covers nothing beneath them.

A packet times the whole of the function it names. The `RedundancyScope`
opens as the first statement of the function the packet records as
`probe_symbol`, before any of the work that function does (a hit test that
first runs a lifecycle update, a paint phase whose scope is opened after the
tree walk, time only the rest). `decompose` divides each bound packet's
time per repetition by the probed function's inclusive share of the story's
cycle profile; that ratio is the same for every packet of one story, and a
packet whose ratio is below half or above twice the reference packet's (the
one whose function carries the largest share) is refused, with the table of
every packet's coverage (`packet_time_coverage` on the row). Below half:
the scope opened late, or the symbol names a neighbour of the probed
function. Above twice: a recursive site was counted once per nesting level,
or the scope is wider than the function named. A `probe_symbol` matches a
frame only as the whole function name followed by its parameter list;
`LayoutView::HitTest` no longer matches `LayoutView::HitTestNoLifecycleUpdate`.

The reference is the story's largest-share packet on the request's build,
bound or not. A request that binds only packets whose scopes time a
fraction of their functions is consistent with itself and with nothing
else; judged against the story's other counters it is refused, and the
table prints the unbound packets as `(not bound)`. `probe-union` applies the
same ratio per story and does not size a story where the probe's coverage
is outside the band (`not_sized` in the union row, "not sized (scope
coverage)" in the table).

The symbol is the function the scope is in. A scope placed in a callee or a
lambda (`LayoutOOFNode` under `OutOfFlowLayoutPart::Run`; the min/max lambda
under `FlexLayoutAlgorithm::ConstructAndAppendFlexItems`) times that callee,
and the packet names that callee whatever the function above it is called.
When the callee has no frame of its own in the profile (inlined; and the
profile is fixed, captured before the probes, so `NOINLINE` in the probe
patch does not put it there: round 21 asked for that and round 22 could not
deliver it), the packet names the enclosing frame as `probe_symbol` and the
callee as `scope_symbol` (`redundancy_evidence.py --scope-symbol`). The gate
checks the patch shows that function above the counter in the hunk that
defines the site, exempts the packet from the lower coverage band, and
scales its bound by the coverage instead: on the row whose function is the
frame, a mandatory closing uses `share x coverage x supported`, the
uncounted `share x (1 - coverage)` must itself be below the floor (else the
rest of the function needs a counter of its own), and a candidate claims at
most `time fraction x coverage`. `probe-union` carries the same scaling.
Round 21 found both cases: the flex packet timed 0.11 of the function it
named in Next and 0.14 in Nuxt, the out-of-flow packet 0.10 of `Run` in
Nuxt and 0.33 in Backbone, and the candidate list carried `share x fraction`
of the wrong function (Next flex 9.4% where the scope's own time supports
about 1.6%). The flex counter now sits at the top of
`BlockNode::ComputeMinMaxSizes`, a frame; the out-of-flow counter stays in
`LayoutOOFNode` with `scope_symbol`.

Scopes of one counter are timed exclusively. A box's layout lays out its
children through the same function and a pre-paint walk visits its subtree;
each scope records its own time net of the scopes that ran inside it, so a
packet's `total_ns` is the time under the outermost calls and its
`nested_calls_fraction` says how many calls ran inside another. Rows say
`"timing":"exclusive"`; a packet whose rows do not is refused.

A packet is tied to the binary that logged it. Every row carries the
executable's GNU build id, the packet records it, and `decompose` refuses a
packet without one. Packets bound in one decomposition that cite the same
probe patch must come from one build, and packets from one build must cite
one patch: a log from a binary built before the patch changed, or a packet
whose `patch_sha256` was rewritten to the current patch, is not evidence
for that patch.

A `repeat` key determines the call's result. It names the unit of work
(the box, the fragment, the element) together with the inputs the work reads,
or a set of inputs the result is a pure function of; two calls with the same
key must produce the same result. A key of the object alone ("this box was
laid out again", "this fragment was painted again") says nothing about the
inputs and is refused, whatever the call count; a key of the inputs alone
without the object (a constraint space and a style version shared by every
sibling) counts different objects as repeats of one another and is refused
too. For box layout the key is the box, its constraint space and the
versions of what it reads; for a paint the fragment, the paint phase and the
invalidation state; for a hit test the location and the layout version.

An `applicable` predicate is an expression of the call's own state that the
hypothesis would test before doing the work. A literal (`SetApplicable(true)`,
`SetApplicable(false)`, a scope constructed with `/*applicable=*/false`) is
no predicate: `true` supports nothing (the gate refuses it as saturated) and
`false` measures nothing, so a row it closes is closed by fiat; the reviewer
refuses both on reading the patch. A "nothing dirty" predicate on a
lifecycle update is the conjunction of every phase's dirtiness up to the
target state (style and layout tree, layout, pre-paint property and
invalidation flags, paint, compositing); a predicate that checks two of
them reads as clean on calls whose paint phase then does a full update, and
the paint packet from the same run refutes it.

The numbers in a row's text are the bound packet's numbers. `decompose`
reads every percentage, every "calls/rep" figure and every `probe_*.json`
name in the row's `existing_mechanism`, `rationale`, `invariant`,
`falsification`, `notes` and `investigation` fields and refuses a row whose
figure is none of the packet's fractions (call or time), `share x fraction`,
its share or its floor, or whose packet name is not the bound one. Text
carried over from an earlier revision's packet, or from a script that set
dispositions without writing rows, fails here.

A row's text is its own. `decompose` refuses a `wrapper_of` that names
another instance of the same function under another entry (a wrapper's
count lives in a counted descendant); refuses a `novel` row whose
`existing_mechanism` names only the row's own function ("X checks dirty
bits" names no mechanism: the invalidation path, the result cache or the
reuse path that already avoids part of the work is other code); refuses a
`mandatory` or `no-qualifying-mechanism` row at or above the floor that
binds a packet without an `invariant` sentence naming what the step
dirties, what the function does with it and the code that does it; and
refuses two rows whose `existing_mechanism`, or whose `invariant` under
different packets, read the same once numbers, symbols, probe sites and
packet names are blanked (rows closed by one packet share that packet's
invariant). Rows written by a script with the values swapped in fail the
last rule wherever the template appears.

The code a row names exists. `decompose` looks every `Class::Method` in
an `existing_mechanism` or `invariant` up in the repository the profile
was captured from (`git grep` for the qualified name, or the method
declared in the class's header) and refuses a row naming code that is not
there; a mechanism invented to satisfy the rule that a row names one is
the same fabrication as a typed count. An `invariant` quotes the packet's
bound as a percentage (the number check confirms it is the packet's); a
sentence with no number was written to say nothing the gate can read.

A predicate on a lifecycle update reads the whole frame tree, and so does
its key: the delegated call's document is the harness page, whose
versions do not change when the iframe's do, so a key of that document's
versions makes the iframe's second update a "repeat" of the first. The
workload runs in an iframe; a child view's `UpdateLifecycleToLayoutClean`
delegates to the local root's `UpdateLifecyclePhases`, whose document is
the harness page. A "nothing dirty" predicate that reads that document's
bits reads clean while the phases it then runs (`ForAllNonThrottledLocalFrameViews`)
do the iframe's work; the applicable call that carries half of the
function's own time is that call. The dirtiness the predicate must OR
together is every non-throttled local frame's.

## Where a large row's time goes

Redundancy is one of four shapes. A `mandatory` or `no-qualifying-mechanism`
row at or above 5% of its story is not finished when its packet shows no
skip and no reuse; the decomposition also shows where its time goes, in
one of three ways, and `decompose` refuses the row otherwise:

- **Probed beneath.** Rows under it (sharing 80% of its samples) bind
  packets of their own: the search moved down into the descendants that
  carry the time, and the row's `probed_below` records them.
- **An `algorithmic` row** on the same function: a cost claim with its
  cost packet (above).
- **An `investigation`** on the row naming the Layer 3/4 hypotheses tried,
  the number that falsified each, and the stop reason. The row binds its
  cost packet as `cost_evidence: {path, sha256}` and every falsification
  quotes a child or leaf frame's fraction from it; the closing count's own
  repeat fraction, or the row's share of the story, quoted again, falsifies
  nothing and is refused.

`campaign.py cost-packet --opp <id> --children <file> --path <row> --out
evidence/cost_<key>.json` reduces the story's collapsed stacks for the
row's anchor into its time by direct child and by leaf frame (share of the
story and fraction of the row). An `algorithmic` row names the frames the
cheaper algorithm would not run; their summed fraction bounds the claim.
Export lists such candidates with `candidate_type: algorithmic`; they are
cost claims, untested, ranked with the rest by share x fraction.

## Every counter speaks

A row whose anchor is itself a probed function binds that function's packet
for its story, never an ancestor's: the ancestor's count says nothing about
the repeats beneath it (a layout-root packet reading 1% closes nothing
about an out-of-flow pass beneath it that repeats 55% of its time). And a
row closing as `mandatory` or `no-qualifying-mechanism` satisfies
`share x supported bound < floor` for every site on its function, not only
the one it binds: a function with two counters, one reading zero, is not
closed by the zero. When one site bounds above the floor the row is `novel`
or `known` at that site's fraction. It is never `covered-by` an ancestor's
mechanism row: a probed function is dispositioned by its own count (the
nearest-probe rule), whatever the ancestor's count explains. Two mechanisms
at nested functions in one story are instead marked in the export: when at
least 80% of the inner mechanism's samples carry the outer's anchor, the
inner row says `Not additive with` the outer, and the two are ranked as one
win in experiments (the collector's repeats under recalc-style are one
example: the within-resolve counter reads zero, so they are re-resolutions,
and the two candidates are one).

For that the gate must know which function every counter sits in: every
site that ran in the story (rows in the twin log) is reduced at least once
on the build, for any story, with `--symbol`; a site that ran and was never
reduced refuses the request. `campaign.py probe-union-all --browser-log
<log> --patch <patch> --out-dir evidence/` then sizes every named site
across every story in one pass and writes `union_<site>.json` per site.

## The nearest packet

A row closed by count binds the nearest packet on its stack. Among the
story's packets whose probed function shares 80% of its samples with the
row (either side), the row binds the one whose function's sample weight is
nearest the row's own: its own function, else the nearest ancestor or
descendant on the stack (`enforce_nearest_packet`; weights within 5% are
the same distance). A farther packet that reads lower closes nothing: the
round-21 builder bound the lifecycle root to every phase it could, chose
among ancestors by `share x supported < floor`, and closed out-of-flow
candidate layout on the box packet while the out-of-flow packet sat one
frame above. The closing bound of a mandatory row is the largest supported
fraction over every packet on the bound function in the story, whichever
site the row bound.

Two rows an ancestor's count does not close. A per-update count (a probe
that fires at most 40 times per repetition: the lifecycle roots, the frame
update) closes a row beneath it only when the row is at least a third of
the update's time; a smaller row is a phase's part, and its count is a
counter nearer to it. And a row at or above 5% of its story that is less
than a third of what the packet's function weighs, with no probed function
beneath it, closes on nothing: an ancestor's count says nothing about the
repeats beneath it, and a row that large gets a counter on its own function
or its dominant descendant (round 21: `Element::SetAttributeHinted` at
5.1% of Stockcharts bound to the event dispatch count, 7% of it, with an
investigation quoting where the time goes and a stop reason that tested
no redundancy). The report names the function, the key and the predicate
before the counter is added.

A candidate row is the probed function's own row. A `novel` or `known`
row's anchor is the function the packet's probe sits in; the other rows on
that function are `covered-by` it, and an ancestor never claims the count
of the function beneath it (round 23: a 4.6% style-tree row marked `known`
at recalc-style's fraction while the recalc rows beneath it carried 3.3%).
When the function appears in several rows of the profile (a recursive
style recalc under several contexts, each below the floor on its own), the
mechanism qualifies in the story by the probed function's inclusive share
times the fraction, the number `probe-union` sizes; `decompose` records
`mechanism_function_share_pct` and `mechanism_function_impact_pct` on the
row and the pre-check prints them.

`wrapper_of` never names a counted function's row. A row whose own function
carries a counter binds that counter's packet whatever else it is; the
round-21 files declared `InlineLayoutAlgorithm::Layout` a wrapper of
`LineBreaker::NextLine` bound to the lifecycle root, hiding 0.86 of its
time repeating in Angular (2.8% of the story), and `OutOfFlowLayoutPart::Run`
a wrapper of `LayoutCandidates` bound to the box packet.

## The evidence base is one artifact

Every packet under `evidence/` on the request's build must re-derive from
the logs it cites, bound or not (`enforce_evidence_provenance`). The gate
reads unbound packets too: the sites named on the build, every counter on
a row's function, the story's packets for the nearest-packet and coverage
rules. A packet edited by hand anywhere in the evidence base changes what
the gate sees without any row binding it: in round 22 a `time_weighted`
flag flipped to `false` on the Backbone out-of-flow packet took that site
out of the story's packet set, and with the row's anchor renamed to a
function that does not exist (`OutOfFlowLayoutPart::RunLayout()`) the row
escaped the own-counter rule and passed the pre-check. One edited packet
now refuses every request on that build until it is regenerated or
removed, and an anchor must be the function its primary work refs name
(`function:<symbol>` in the hotspot key): a row renamed away from its
function is outside every rule keyed on it.

## What `repeat` can and cannot support

A packet carries two hypotheses. `applicable` is the row's own predicate:
the count of calls where the invariant the row names held. `repeat` is
input identity: calls whose key was seen earlier in the repetition. A
repeat supports a mechanism only where the function's output is a value
that can be reused in place of running it again: a size (flex min/max
keyed on the box, its text, style, constraint space and the DOM and style
versions), a layout result, a hit-test result, a parsed tree that can be
cloned. A function whose point is its effect has no reusable output: an
event dispatch runs listeners, a mutation changes the tree, a listener
call is the work. For those, `repeat` measures how often the same kind of
thing happened, not avoidable work, and only `applicable` (a skip the row
states: no listener on the path, nothing dirty) can close or open the row.

The converse mistake: an `applicable` predicate that counts the existing
mechanism's successes (`cache_status == kHit`) measures the cache working,
not work a mechanism could remove. The avoidable candidate is the miss
whose key repeats. A novel row on such a count is refused.

## The pre-check is the gate's code

`scripts/precheck_decomposition.py <campaign> <opp> <children.json>` runs
the gate's rules on a staged file and prints the coverage table, the bound
packets and the rows a reviewer opens; `scripts/host_review.py --dir
<campaign> --rev <n> <opp>...` writes the host-side gate reports from the
artifacts. Both live in the skill tree the campaign binds by digest, and
both import the reducer and the rules as they are. A copy under the
campaign, or any wrapper that replaces a rule or a reducer function (an
override of `supported_avoidable_fraction` for a site, say), is not the
pre-check: `decompose` runs the unmodified code, and a file whose "clean"
pre-check came from a modified copy is refused at import with the rule's
own message. The reviewer runs the skill-tree copy and checks
`git status` on the skill tree before trusting any pre-check output.

Four read-only commands answer the questions a request raises, with the
gate's own code: `campaign.py rows --children <file> [--opp N] [--rows 1,8,12-15]
[--text]` lists rows with share, disposition, wrapper, covered-by, mechanism
and packet; `campaign.py packet <path>...` prints a packet's numbers and
whether it re-derives; `campaign.py candidates [--story S]` lists the areas
still to decompose by priority; `campaign.py explain --opp N --children
<file> --path K` prints, for one row, every packet on the build with its
relevance, weight ratio, coverage and closing bound, which is nearest, the
mechanism rows that could cover it with their identity, the rows beneath it
a wrapper could name, and what the gate would accept. A refusal from the
pre-check names the `explain` command for its rows. Nobody types Python at
the host: a question the commands cannot answer is a missing command, and
the report says so.

## A decomposition without a count is open work

A discovery whose decomposition binds no packet, no cost packet and no
`below-floor` row was written from reading, whatever its status says. The
ledger treats it as open: `next` lists it beside the untouched candidates,
marked `DECOMPOSED-BY-PROSE`, STATUS names it under discovery coverage, and
it is decomposed again by count under its next revision, which `decompose`
accepts without a recorded skeptic FAIL on the prose revision. The gate now
refuses such a file at import, so this concerns decompositions imported
before the count rules.

## One probe, every story

A mechanism found in one story is sized across the suite before it is
ranked: run the instrumented twin once over every campaign story with the
same probe, then `campaign.py probe-union --site <site> --symbol <function>
--browser-log <log> --patch <patch> --out evidence/union_<key>.json`. The
table gives, per story, the probed function's profile share, both
hypothesis bounds, share x bound against the story's floor, and which
stories qualify; each qualifying story's area then carries a `known` row
for the mechanism (or a `novel` row where the area is first decomposed),
with a packet reduced for that story from the same log.

One union, one build. Every row the union reduces carries the same
`build_id`, and the union records it; logs from two binaries (an earlier
round's stories beside a new story on the current build) are refused, since
a story measured on an older binary with an older patch is not the same
probe. When the probe or its key changes, every story is rerun.

A packet is a reduction, never a file. `decompose` reduces every bound
packet's `sources` again with `redundancy_evidence.py` on the ledger host
and refuses the packet if any derived field (repetitions, calls, fractions,
overflow) differs; a log that does not resolve or whose digest changed is
refused; the recorded `patch` must resolve, match its digest, and define a
`RedundancyCounter` for the packet's site (`new RedundancyCounter("site")` or a
named `static thread_local RedundancyCounter name("site")`; the site string is
the proof). A packet written by hand, with a
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
