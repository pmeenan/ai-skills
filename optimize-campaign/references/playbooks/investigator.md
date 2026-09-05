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

## Procedure

1. Start from the story's score-time composition and the top **inclusive**
   parents on the main thread, not from the bottom-up leaves. Walk each
   parent to the decision that makes its descendants run (invalidation,
   traversal, conversion, allocation, phase). Preserve exact path sample
   accounting.
2. For the best parent, write the invariant as: condition C occurs in X/Y
   measured calls; it permits removing exactly W (named descendants) while
   preserving observable behavior B. Then measure X/Y: add a
   `RedundancyCounter` at the site in the instrumented twin (see
   `instrumented-twin.md`), run the target story, and reduce the log with
   `redundancy_evidence.py`. If the counts do not support the fraction you
   hoped for, say so and move on; that is a cheap, honest stop.
3. Check the story's qualification floor (`campaign.py status` shows the
   calibrated MDEs). Estimated impact = story main-thread share × avoidable
   fraction must clear max(share floor, 2 × story MDE). If it cannot even
   with the measured fraction, park the area with the numbers.
4. Check the entry's `platform_sensitivity`. Rendering-backend, font-shaping
   and process-plumbing work is a Pinpoint-first lead on the Mac M1 bot, not
   a local candidate; note it and pick the next parent.
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
