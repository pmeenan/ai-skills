# Discovery decomposition contract

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

## Per-Story Silo Decomposition & Target-Story Impact Ranking

Speedometer 3 comprises 32 distinct workloads. Each story is profiled and explored as an independent silo (`analysis/stories/<story>/`), which gives clean local reads and avoids geometric-mean dilution.

1. **Local Story Floor ($\ge 0.3\%$):**
   Each story's stacks are decomposed in isolation down to $\ge 0.3\%$ of that story's scored cycles, with the 100-nominal-samples quality gate applied per story. This discovers high-leverage workload-specific opportunities (e.g. Canvas 2D in `Charts-chartjs`, SVG paths in `React-Stockcharts-SVG`, DOM class mutations in `TodoMVC-jQuery`, layout ranges in `Editor-TipTap`).

2. **Global Ranking by Target-Story Impact:**
   Every frontier entry is story-qualified (`story:<name>/…`) and carries a `target_story`. The ledger ranks all opportunities globally by:
   $$\text{Estimated Target-Story Impact} = \text{Local Story Share} \times \text{Avoidable Fraction}$$
   measured against the entry's own target story. The same mechanism hot in several stories appears as separate story-qualified areas, each ranked by its own local impact — no cross-story summing, no division by 32. If a mechanism happens to also help other stories, that is a bonus recorded in notes; it never enters the ranking.

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
- `estimated_local_story_impact_pct`: `story_profile_share_pct * estimated_avoidable_fraction` (the global ranking metric; never rescaled to a full-suite share). `campaign.py decompose` derives the profile share from bound `work_refs`, recomputes this product, rejects mismatches/below-floor proposals, and stores it as the mechanism priority.
- `subtree_pruned`: list of child functions and their combined profile share eliminated.
- `invariant_description`: exact code condition, bypass logic, and invalidation rules.
- `safety_and_spec_analysis`: explicit reasoning on HTML/DOM/CSS spec compliance and lifecycle safety.

## Dispositions

| Disposition | Use only when | Required evidence |
| --- | --- | --- |
| `novel` | one new invariant can remove the work (must pass Adversarial Qualification) | stable `component/strategy` key, 4-layer proposal, and primary work reference |
| `known` | the exact mechanism already exists in the ledger | existing mechanism key and matching work references |
| `covered-by` | the samples are literally the same samples as another row | owning mechanism key and overlap/sample identity |
| `mandatory` | specification or unavoidable product behavior proves the work cannot be removed | cited invariant and source/trace evidence |
| `out-of-scope` | the work is not Chromium-owned or not within the campaign goal | ownership/critical-path evidence |
| `below-floor` | the estimated net impact is below the configured floor (< 0.30%) | profiler work reference and measured share |

Do not use `covered-by` for a semantically adjacent caller, wrapper, or later
stage. Do not combine distinct hotspot keys into one primary path. Reconcile
every known/parked mechanism explicitly.

After all child mechanisms are terminal, bind the exhaustion review to the
exact decomposition:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold \
  --opp <discovery> --role skeptic --out <exhaustion-review.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review \
  --opp <discovery> --role skeptic --verdict PASS \
  --report <exhaustion-review.json>
python3 .agents/skills/optimize-speedometer/scripts/campaign.py exhaust \
  --opp <discovery> --reason <reason> --evidence <artifact-paths>
```

Any decomposition edit invalidates the prior review and requires a fresh
scaffold. `audit-exhaustion` is the final machine check.
