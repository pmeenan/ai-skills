# Skeptic playbook

Goal: independently verify effectiveness. Be read-only.

Generate the bound report first:

```bash
python3 .agents/skills/optimize-speedometer/scripts/campaign.py review-scaffold --opp <id> --role skeptic --out <report.json>
```

The scaffold selects one of two bounded review kinds.

For `review_kind: mechanism`, open the staged diff, dossier, digest-bound
counter logs, raw baseline/candidate files, and derived artifacts. Verify:

- `hot_path_reality`: exact-score profile or counters observed the path;
- `raw_evidence_opened`: raw files and digests match derived evidence;
- `applicability_measured`: calls and applicable calls were counted;
- `net_work_removed`: paired lower confidence bounds are positive;
  total scored-cycle change and `moved_work_warning` do not show work moved or
  added elsewhere;
- `cold_path_tax_measured`: added code/branches have a tax assessment;
- `benchmark_overfit_checked`: no benchmark strings, selectors, or data-shaped
  special cases unless they express a general product invariant;
- `one_invariant_only`: the diff does not bundle mechanisms.
- `implementation_is_executable`: staged production semantics changed; the
  candidate is not comments, whitespace, tests, or campaign bookkeeping;
- `candidate_build_bound`: candidate counters, build receipt, test receipt,
  staged tree, bare-metal host/boot, browser identity, and executable `.text`
  all describe the same implementation.

For `review_kind: discovery-exhaustion`, open the exact decomposition and
profiler inventory. Verify:

- `complete_path_accounting`: every profiler work reference is present;
- `exactly_one_primary_per_hotspot`: each root/hotspot has one primary owner;
- `covered_by_same_samples`: every covered-by row proves sample identity, not
  semantic adjacency;
- `mandatory_work_proved`: every mandatory row cites a product invariant;
- `out_of_scope_proved`: every exclusion has ownership/critical-path proof;
- `below_floor_measured`: the current profile, not prose, places it below the
  configured floor;
- `known_mechanisms_reconciled`: landed/rejected/reverted/parked history is
  represented without retrying ruled-out work.

Set a check true only after verification and replace its `check_evidence`
placeholder with an artifact/path/line-specific explanation of at least one
sentence. Replace the top-level notes placeholder too. Add every actionable
problem to `findings`. PASS requires all checks true, substantive evidence for
every check, and an empty findings array. Set the verdict in the JSON and
return only its absolute path plus the verdict.
