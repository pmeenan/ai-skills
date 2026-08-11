# Adversary playbook

Goal: independently verify correctness, security, privacy, and lifecycle. Be
read-only.

Generate the bound report first:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role adversary --out <report.json>
```

Inspect the staged diff and tests. Verify the exact scaffold checks: `spec`,
`security`, `privacy`, `lifecycle`, `tests`, and
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
