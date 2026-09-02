# Campaign adversary playbook

Goal: independently verify correctness, security, privacy, and lifecycle across two distinct gates:
1. **Candidate Qualification Gate (Pre-Frontier):** Reviewing investigated opportunity proposals before they enter the Master Ranked Frontier.
2. **Candidate Verification Gate (Pre-Landing):** Reviewing staged product diffs, receipts, and paired cycle evidence before landing.

Be read-only.

## 1. Candidate Qualification Gate (Investigation Proposals)

When reviewing an Opportunity Investigation Proposal, verify:
- **Profile Ground Truth:** Check the target story's `profile.collapsed` and the decomposition's bound `work_refs` to verify that `target_stack_pattern` and machine-derived `story_profile_share_pct` are factual.
- **Web Specifications & Standards:** Check that the proposed invariant (e.g. subtree bypass, dirty check, or caching) strictly adheres to HTML, DOM, CSS, and JS specifications.
- **Lifecycle & Invalidation Safety:** Check that skipping the proposed branch does not miss required observer callbacks, custom element reactions, style invalidations, or layout updates.
- **Plausibility of Avoidable Share:** Verify that `estimated_avoidable_fraction` is realistic, that the recomputed `estimated_local_story_impact_pct` clears the campaign floor, and that the proposal is not shifting work to a downstream caller/microtask. The decomposition gate report must bind the exact decomposition artifact digest.
- **ThinLTO & Micro-Branch Anti-Pattern Check:** **REJECT** any proposal that relies on adding speculative micro-branch guards, outer trivial null checks, or empty collection checks in tight loops called $>100\text{k}$ times. ThinLTO and PGO2 already optimize inlined branches; adding redundant outer branches causes BTB pressure and pipeline stalls, producing net regressions. Demand Layer 1 (Subtree/Phase Elimination) or Layer 2 (Cross-Call State Memoization) where significant work is avoided.
- **Discarded Candidates Check:** Verify against the benchmark's `references/discarded-candidates/INDEX.md` and matching subsystem file. If the proposed mechanism attempts a previously rejected concept, call site, or anti-pattern without addressing the identified causal failure mode, **REJECT** the proposal.
- **Flag Isolation:** Ensure the proposed design is 100% inert when `RuntimeEnabledFeatures::Speedometer3OptimizationsEnabled()` is disabled.

Return JSON verdict `PASS` | `CHALLENGE` | `REJECT`.

## 2. Candidate Verification Gate (Staged Code & Evidence)

Generate the bound report:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py review-scaffold --opp <id> --role adversary --out <report.json>
```

Inspect the staged diff and tests. Verify the exact scaffold checks: `spec`,
`security`, `privacy`, `lifecycle`, `tests`,
`benchmark_overfit_checked`, `feature_flag_guarded`, and `subtree_pruning_verified`.
Search for benchmark strings, selectors, fixture names, and data-shaped special
cases; accept only general product invariants. Verify that the staged diff
actually eliminates the claimed child call chains (`subtree_pruned`) rather than
merely tweaking an outer entry point before still executing the full child tree.
For `runtime_binary_changed`, open the bound candidate evidence and verify its
candidate executable `.text` digest differs from baseline; source or debug-info
changes alone do not count.
Verify `probe_symmetry`: baseline and candidate probe placements are 100%
structurally symmetric; probes are never placed inside conditional feature branches
or bypassed in the candidate. Verify that probes use user-space `_rdpmc` with no
synchronous kernel syscalls.
Verify `in_situ_cycle_reduction_verified`: confirm a machine-generated
`mechanism_evidence.py compare` (or targeted single-story cycle diff) artifact
proves statistically significant cycle reduction on the target story before
advancing to review or macro A/B runs.
Exercise flag-on, flag-off,
fallback, invalidation, mutation, reentrancy, ownership, and teardown paths
that apply. A benchmark result is not correctness evidence.

Set checks true only after verification. Replace every `check_evidence`
placeholder and the notes placeholder with artifact/path/line-specific
reasoning. Put actionable issues in `findings`. PASS requires every check
true, substantive evidence for every check, and no findings. Set the JSON
verdict and return only its absolute path plus the verdict.
