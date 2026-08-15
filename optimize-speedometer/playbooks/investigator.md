# Investigator playbook

Goal: turn one profiled subsystem into structured, 4-layer investigated opportunity proposals with exact stack attributions from `profile.collapsed`.

Inputs: subsystem name, exact profile artifacts (`profile.collapsed`, `candidate_frontier.md`), and output directory.

Procedure:

1. **Subsystem Stack Decomposition:**
   - Filter `profile.collapsed` for the target subsystem.
   - Trace all major call paths from entry point down to leaf functions, quantifying exact sample counts and percentage shares.

2. **Apply the 4-Layer Investigation Framework:**
   - **Layer 1 (Subtree / Branch Elimination):** Can an entire call tree or lifecycle step be avoided with a pre-condition, dirty flag, or fast-exit check?
   - **Layer 2 (Higher-Level Caching & Sharing):** Can computed state (styles, shape results, layout spaces) be shared or memoized across sibling nodes, repeated runs, or microtasks?
   - **Layer 3 (Algorithmic & Structural Hoisting):** Can $O(N)$ linear scans, vector lookups, or stack allocations be replaced with $O(1)$ bitmasks/bloom filters or flat arrays?
   - **Layer 4 (Leaf-Level Micro-Optimizations):** Only if Layers 1–3 cannot eliminate the work.
     * **CRITICAL ThinLTO & PGO WARNING:** Do NOT propose speculative micro-branch guards, outer trivial null checks, or empty collection checks in tight loops. In official PGO2/ThinLTO builds, LLVM already inlines and branch-predicts fast-paths; adding redundant outer branches increases BTB pressure and icache footprint, consistently causing net cycle regressions. Focus exclusively on Layers 1–2 where significant work (>100 cycles per avoided call) is pruned.

3. **Formulate the Opportunity Invariant:**
   - State one invariant: “When condition C is measured true, work W (including downstream call tree T) can be avoided while preserving behavior B.”

4. **Quantify Profile Headroom & Avoidable Share:**
   - `story_profile_share_pct`: Exact sum of cycles in the targeted stack within the specific benchmark story (or full-suite average).
   - `estimated_avoidable_fraction`: Realistic fraction of the stack avoided by the condition (0.0 to 1.0).
   - `estimated_local_story_impact_pct` = `story_profile_share_pct * estimated_avoidable_fraction`.
   - `estimated_global_geomean_impact_pct` = `estimated_local_story_impact_pct / 32.0`.
   - Local floor requirement: `estimated_local_story_impact_pct >= 0.30%`.

5. **Emit the Opportunity Investigation Proposal:**
   - Save to `.agents/campaigns/current/proposals/<mechanism_key>.json`.
   - Request Adversarial Review (`playbooks/adversary.md` Candidate Qualification Gate).

Proposal JSON format:

```json
{
  "opportunity_id": 0,
  "mechanism_key": "component/strategy",
  "subsystem": "style|html-parser|events|layout|dom|paint",
  "target_story": "Charts-chartjs|TodoMVC-jQuery|all",
  "investigation_layer": 1,
  "target_stack_pattern": "regex_or_stack_frames",
  "story_profile_share_pct": 3.25,
  "estimated_avoidable_fraction": 0.40,
  "estimated_local_story_impact_pct": 1.30,
  "estimated_global_geomean_impact_pct": 0.041,
  "subtree_pruned": [
    "child_func_1",
    "child_func_2"
  ],
  "invariant_description": "When an element has no classes or ID matching any rule in the RuleSet, skip RuleSet iteration entirely via bitmask check.",
  "safety_and_spec_analysis": "Spec compliance and invalidation safety reasoning..."
}
```

