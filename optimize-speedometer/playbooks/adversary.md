# Adversary playbook

Goal: independently verify correctness, security, privacy, and lifecycle across two distinct gates:
1. **Candidate Qualification Gate (Pre-Frontier):** Reviewing investigated opportunity proposals before they enter the Master Ranked Frontier.
2. **Candidate Verification Gate (Pre-Landing):** Reviewing staged product diffs, receipts, and paired cycle evidence before landing.

Be read-only.

## 1. Candidate Qualification Gate (Investigation Proposals)

When reviewing an Opportunity Investigation Proposal, verify:
- **Profile Ground Truth:** Check `profile.collapsed` to verify that the claimed `target_stack_pattern` and `stack_profile_share_pct` are factual and not overstated.
- **Web Specifications & Standards:** Check that the proposed invariant (e.g. subtree bypass, dirty check, or caching) strictly adheres to HTML, DOM, CSS, and JS specifications.
- **Lifecycle & Invalidation Safety:** Check that skipping the proposed branch does not miss required observer callbacks, custom element reactions, style invalidations, or layout updates.
- **Plausibility of Avoidable Share:** Verify that the `estimated_avoidable_fraction` is realistic and not shifting work to a downstream caller/microtask.
- **Flag Isolation:** Ensure the proposed design is 100% inert when `RuntimeEnabledFeatures::Speedometer3OptimizationsEnabled()` is disabled.

Return JSON verdict `PASS` | `CHALLENGE` | `REJECT`.

## 2. Candidate Verification Gate (Staged Code & Evidence)

Generate the bound report:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role adversary --out <report.json>
```

Inspect the staged diff and tests. Verify the exact scaffold checks: `spec`,
`security`, `privacy`, `lifecycle`, `tests`,
`benchmark_overfit_checked`, and `feature_flag_guarded`. Search for benchmark strings, selectors, fixture
names, and data-shaped special cases; accept only general product invariants.
For `runtime_binary_changed`, open the bound candidate evidence and verify its
candidate executable `.text` digest differs from baseline; source or debug-info
changes alone do not count.
Exercise flag-on, flag-off,
fallback, invalidation, mutation, reentrancy, ownership, and teardown paths
that apply. A benchmark result is not correctness evidence.

Set checks true only after verification. Replace every `check_evidence`
placeholder and the notes placeholder with artifact/path/line-specific
reasoning. Put actionable issues in `findings`. PASS requires every check
true, substantive evidence for every check, and no findings. Set the JSON
verdict and return only its absolute path plus the verdict.
