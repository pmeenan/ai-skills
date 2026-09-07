# Campaign investigator playbook

Read [measurement-policy.md](../measurement-policy.md) for floors, causal
bounds, ranking and stopping criteria. Investigate one bounded story area
with its main-thread profile, score-time composition, callers, source
contracts and rejected hypotheses.

## What a qualifying mechanism looks like

Every suite-level win in `optimization-patterns.md` has one of four shapes.
Name the shape before anything else; a proposal without one is a leaf tweak.

| Shape | Question to answer with a count | Evidence before proposing |
| --- | --- | --- |
| Skip the subtree | Under which checkable condition does this whole operation produce no observable effect, and how often does it hold per step? | redundancy probe: `applicable_fraction` |
| Reuse a result | How often does the site run with an input it has already seen in this step or story? | redundancy probe: `repeat_fraction` |
| Change the representation or algorithm | Which structure makes the hot loop O(1), and what share of the story's main-thread time is that loop? | main-thread inclusive share of the loop |
| Shorten a wait | Which dependency on the score path is idle time rather than CPU? | score-time composition, trace-backed latency packet |

Layer 4 leaf work (inlining, branch hints, empty checks in inlined loops) is
not a shape. The discarded catalog is full of it, and none of it clears a
story floor.

## What the milestone is

Under a review hold the deliverable is a **vetted candidate list**, defined
in [vetted-candidates.md](../vetted-candidates.md): every packet field
filled with measured numbers, every story's addressable share above floor
closed by a candidate, a counted `no-qualifying-mechanism`, a `mandatory`
invariant or a hand-off row. Counter probes and cycle profiles of the target
story are in scope; oracle builds, sizing arms, A/B blocks and Pinpoint are
not until a human releases the hold.

## Procedure

1. Start from the story's lens (`lens.md` next to the profile, or the
   "Story lens" and "Underneath the frontier" sections of STATUS): which
   trigger owns the story (forced layout from which JS API, frame update,
   hit-test lifecycle), which phases dominate, and which nested hotspots are
   marked `promoted` (a different phase than their parent, above the floor).
   Each promoted hotspot gets its own decomposition row. Then read the
   score-time composition and the top **inclusive** parents on the main
   thread, not the bottom-up leaves. Walk each parent to the decision that
   makes its descendants run (invalidation, traversal, conversion,
   allocation, phase). Preserve exact path sample accounting.
1a. Split inclusive from self before claiming anything: a dispatcher frame
   with a large inclusive share and a tiny self share (an IC builtin, an API
   callback trampoline, a lifecycle wrapper) is a route to the work, not the
   work. Say what fraction is self, what is Blink descendants, what is JS.
2. For the best parent, write the invariant as: condition C occurs in X/Y
   measured calls; it permits removing exactly W (named descendants) while
   preserving observable behavior B. Then measure X/Y: add a
   `RedundancyCounter` at the site in the instrumented twin (see
   `instrumented-twin.md`), run the target story, and reduce the log with
   `redundancy_evidence.py`. If the counts do not support the fraction you
   hoped for, say so and move on; that is a cheap, honest stop.
2a. Key the probe on C, not on the call. The `Record(key, applicable)` key
   is a hash of the inputs the hypothesis says are unchanged (text content,
   constraint space, font, sheet list, chunk properties), and `applicable`
   is C itself (text equal to the previous data, cache lookup hit, layer
   identical to last update). A pointer that is new on every call gives
   0% repeats and proves nothing; `applicable=true` on every call bounds
   nothing and cannot close a row. Before writing a candidate, read what
   Chromium already does at the site (a reuse path, a result cache, a dirty
   bit) and count what it misses; that is the row's `existing_mechanism`.
2b. Few calls are not small work. Five requests per repetition that each
   re-shape a document are the finding; the count that matters is the work
   under the call (characters shaped, boxes laid out, chunks processed)
   keyed on whether that work's inputs changed.
3. Check the story's qualification floor (`campaign.py status` shows the
   calibrated MDEs). Estimated impact = story main-thread share × avoidable
   fraction must clear max(share floor, 2 × story MDE). If it cannot even
   with the measured fraction, park the area with the numbers.
4. Check `platform_sensitivity` on the work you propose to remove, not on
   the root symbol. Rendering-backend, font-shaping and process-plumbing work
   is a Pinpoint-first lead on the Mac M1 bot, not a local candidate; note it
   and pick the next parent.
4a. Work that the lens attributes to V8, JIT code or unknown leaves is
   recorded as an `out-of-scope` row whose evidence names the owner and the
   lens numbers (NoFeedback IC share, IC-miss runtime, compile, Maglev
   main-thread, JSON, interceptors). A V8 hypothesis may be tested with a
   single-story cycle profile under `--js-flags`; that is a lead for the V8
   team or a gin feature-flag route, not a Blink candidate.
5. Consult the ledger and the discarded-candidates catalog for the same
   *mechanism*, not the same function. A rejected leaf guard does not
   preclude skipping the subtree above it. Inspect newer upstream code
   read-only.
6. Generate independently motivated alternatives (at least one per shape
   that applies) before settling. Give the favored hypothesis and its
   strongest competitor to the strongest available model for the
   architectural counterfactual and the semantic-risk pass; record its
   objections verbatim in the proposal.
7. Save the proposal under the campaign's `proposals/` directory with the
   redundancy packet reference, and use `decomposition-scaffold` /
   `decompose` to account paths. A bounded search with no viable invariant
   uses `no-qualifying-mechanism` with its investigation packet; it does not
   blacklist an ancestor or claim exhaustion.

The mechanism packet includes source revision, target story, profile refs,
shape, redundancy evidence (site, calls per step, applicable and repeat
fractions), work-removal or latency route, removed work, added work, cold-path
cost, counterfactual experiment, semantic risks, portability flag,
engineering/measurement budget, and explicit falsification/stop conditions.
Have the skeptic inspect raw evidence and competing explanations before
coding or expensive scoring.
