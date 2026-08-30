# Campaign investigator playbook

Goal: turn one profiled story-silo area into structured, 4-layer investigated opportunity proposals with exact stack attributions from that story's `profile.collapsed`.

Inputs: target story name, subsystem/area name, exact per-story profile artifacts (`analysis/stories/<story>/profile.collapsed`, `analysis/stories/<story>/candidate_frontier.md`), and output directory.

Each investigation is scoped to one story silo. Use only the target story's own artifacts; the full-suite view is diagnostic and must not source shares. If the same mechanism plausibly helps other stories, note that as an unquantified bonus in the proposal notes — it never enters the ranking.

Procedure:

1. **Subsystem Stack Decomposition:**
   - Filter the target story's `profile.collapsed` for the target subsystem.
   - Trace all major call paths from entry point down to leaf functions, quantifying exact sample counts and percentage shares of the story's scored cycles.

2. **Apply the 4-Layer Investigation Framework:**
   - Primary driver: First-principles top-down decomposition of the profile call tree to discover novel, unharvested inclusive hotspots.
   - Auxiliary inspiration: Consult `references/optimization-patterns.md` as an "also explore" reference for historical architectural archetypes (Style/Cascade, Layout, DOM Core, Canvas 2D, V8 Bindings) without letting it narrow or restrict the search space.
   - **Layer 1 (Subtree / Branch Elimination):** Can an entire call tree or lifecycle step be avoided with a pre-condition, dirty flag, or fast-exit check?
   - **Layer 2 (Higher-Level Caching & Sharing):** Can computed state (styles, shape results, layout spaces) be shared or memoized across sibling nodes, repeated runs, or microtasks?
   - **Layer 3 (Algorithmic & Structural Hoisting):** Can $O(N)$ linear scans, vector lookups, or stack allocations be replaced with $O(1)$ bitmasks/bloom filters or flat arrays?
   - **Layer 4 (Leaf-Level Micro-Optimizations):** Only if Layers 1–3 cannot eliminate the work.
     * **CRITICAL ThinLTO & PGO WARNING:** Do NOT propose speculative micro-branch guards, outer trivial null checks, or empty collection checks in tight loops. In official PGO2/ThinLTO builds, LLVM already inlines and branch-predicts fast-paths; adding redundant outer branches increases BTB pressure and icache footprint, consistently causing net cycle regressions. Focus exclusively on Layers 1–2 where significant work (>100 cycles per avoided call) is pruned.

3. **Durable Ledger History & Up-to-Date Checkout Pre-Check:**
   - **Checkout Freshness:** Ensure the working branch is based on an up-to-date checkout of `origin/main` to avoid re-implementing recently landed upstream optimizations.
   - **Durable Ledger Inspection:** Check the campaign ledger (`OPTIMIZATION_LEDGER.md`) for previous candidate evaluations in the target area.
   - **No Premature Path Closing:** If a previous attempt in an area failed or was discarded, **do NOT close off or blacklist the entire subsystem or function**. Instead, inspect the *specific failure mechanism* (e.g. branch overhead, spec edge-case, or compiler inlining). If a novel, structurally distinct mechanism can harvest that inclusive hotspot without repeating the specific flaw, it remains a high-priority candidate.

4. **Formulate the Opportunity Invariant:**
   - State one invariant: “When condition C is measured true, work W (including downstream call tree T) can be avoided while preserving behavior B.”

5. **Quantify Profile Headroom & Avoidable Share:**
   - `story_profile_share_pct`: Exact sum of cycles in the targeted stack within the target story silo, as a percentage of that story's scored cycles.
   - `estimated_avoidable_fraction`: Realistic fraction of the stack avoided by the condition (0.0 to 1.0).
   - `estimated_local_story_impact_pct` = `story_profile_share_pct * estimated_avoidable_fraction` (the primary metric for the global ranking; never divide by 32 or rescale to a full-suite share).
   - Local floor requirement: `estimated_local_story_impact_pct >= 0.30%` of the target story.

5. **Emit the Opportunity Investigation Proposal:**
   - Save to `.agents/campaigns/current/proposals/<mechanism_key>.json`.
   - Request Adversarial Review (`references/playbooks/adversary.md` Candidate Qualification Gate).

Proposal JSON format:

```json
{
  "opportunity_id": 0,
  "mechanism_key": "component/strategy",
  "subsystem": "style|html-parser|events|layout|dom|paint",
  "target_story": "Charts-chartjs",
  "possible_bonus_stories": ["TodoMVC-jQuery"],
  "investigation_layer": 1,
  "target_stack_pattern": "regex_or_stack_frames",
  "story_profile_share_pct": 23.0,
  "estimated_avoidable_fraction": 0.40,
  "estimated_local_story_impact_pct": 9.20,
  "subtree_pruned": [
    "child_func_1",
    "child_func_2"
  ],
  "invariant_description": "When an element has no classes or ID matching any rule in the RuleSet, skip RuleSet iteration entirely via bitmask check.",
  "safety_and_spec_analysis": "Spec compliance and invalidation safety reasoning..."
}
```
