# Discovery decomposition contract

Use `decompose-scaffold`; fill its existing rows instead of creating a new
shape. Every profiler root/hotspot must have exactly one `primary` owner.

| Disposition | Use only when | Required evidence |
| --- | --- | --- |
| `novel` | one new invariant can remove the work | stable `component/strategy` key and one primary work reference |
| `known` | the exact mechanism already exists in the ledger | existing mechanism key and matching work references |
| `covered-by` | the samples are literally the same samples as another row | owning mechanism key and overlap/sample identity |
| `mandatory` | specification or unavoidable product behavior proves the work cannot be removed | cited invariant and source/trace evidence |
| `out-of-scope` | the work is not Chromium-owned or not within the campaign goal | ownership/critical-path evidence |
| `below-floor` | the current profile measured the path below the configured floor | profiler work reference and measured share |

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
