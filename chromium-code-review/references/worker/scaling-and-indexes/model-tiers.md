<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

## Model Tiers

Every phase brief in `phase-briefs.md` carries a `Tier:` annotation, and every
`spawn` row in `plan.md` carries a `tier` column. The tier names the least
capable model class the task tolerates. Tiers are capability descriptions,
never model names — the orchestrator resolves them inside whatever family the
harness offers:

| tier | capability semantics | resolve to (illustrative, non-normative) | thinking/reasoning setting |
| --- | --- | --- | --- |
| `mechanical` | exact rule-following over small structured inputs: union/uniqueness checks, ordered concatenation, single-line mutations, schema-shaped extraction. No open-ended code reasoning. | the smallest/fastest model offered alongside the session model (Haiku-class, Flash-Lite/Flash-class, mini-class) | minimal or none |
| `standard` | structured enumeration and classification, summarization/distillation, prose rendered from an already-verified evidence record, audits against deterministic checklists | the session's default model or a mid-tier family member (Sonnet-class, Flash-class) | harness default |
| `frontier` | adversarial code tracing, interleaving/lifetime/ownership reasoning, invariant-owner and layering judgment, refutation, contradiction hunting, roster/scoping judgment | the strongest model the harness offers (Opus/Fable-class, Pro-class, high-reasoning-class), with the highest available thinking or reasoning setting | maximum available |

Rules:

- **A tier is a floor, not a target.** Running a task above its tier wastes
  money but never correctness; running a `frontier` task below its tier is a
  measured quality failure — the eval corpus records weak-model runs whose
  collapsed rosters and citation-free matrices missed exactly the P0s the
  deep-trace threads own.
- Generated analytical workers have contract tiers the orchestrator applies
  without reading their briefs: discovery threads take the tier from their
  `plan.md` row; verification skeptics, root-cause challengers, and synthesis
  challengers are always `frontier`; continuations and repairs inherit the
  tier of the work they continue.
- The orchestrator itself is `standard` or higher — never delegate
  orchestration to a `mechanical`-class model.
- **If the harness cannot select per-subagent models or thinking levels,
  every worker inherits the session model and the annotations are a no-op.**
  Never block or degrade a review because tier selection is unavailable.
- **Budgets bind per resolved worker, not per session.** The 35% input budget
  is computed against the context capacity of the model the worker actually
  runs on; when a resolved lower-tier model has a smaller context than the
  session model — or its capacity is unknown — use the smaller capacity or
  the 128 KiB unknown-capacity fallback for that worker's budget, and record
  the tighter figure in its manifest check.
- **Record tier state where it can be audited:** each `spawn` plan row
  carries its recommended tier; each `orchestration.tsv` attempt row carries
  a `tier` column holding the resolved tier actually used (`inherit` when the
  harness could not select). A resolved tier below the recommended one is
  legitimate only with a user directive or a disclosed harness limitation,
  and Verification Notes name every such row.
- The user may set a cost preference in `directives.md` as a structured
  `tier-override: <what the user asked for>` line. Honor it, record the
  deviation, and Verification Notes must disclose every phase that ran below
  its recommended tier. Deep-dive recipe threads, specialist trace threads,
  and verification skeptics are the last to downgrade.
- **Floors are validated, not advisory.** The validator errors on any spawn
  row below its floor (`frontier` for every discovery thread except
  Mechanical Leads and Changed-Lines Polish at `standard`; `mechanical`
  never), on any orchestration attempt whose recorded tier is below its
  plan row's tier, on any frontier-contract work kind (skeptic `V⟨n⟩`,
  `VTER`, root-cause `RC⟨n⟩`, challenge `CH*`, planning shards
  `VPLAN*`/`RCPLAN*`, `PLAN`) recording a lower tier, and on any
  continuation attempt recording a lower tier than its first resolved
  attempt. All downgrade to disclosed warnings only when `directives.md`
  carries a line-anchored `tier-override:` entry — never included by
  default, and not activated by prose mentioning the term mid-line.
- **Per-tier budgets are mechanical, not prose.** When a resolved tier's
  model has a smaller context than the session model, pass
  `--tier-context-window-tokens tier:tokens` to `profile-review.py`; it
  records `tier_worker_input_budget_bytes`, and the validator caps each work
  unit's manifest total at the minimum of the global budget and its resolved
  tier's budget (from the attempt's recorded tier). Any attempt recording a
  concrete resolved tier (`mechanical`/`standard`/`frontier`) whose capacity
  was never reported gets the 128 KiB unknown-capacity fallback — a concrete
  tier means model selection is in use, and an unreported tier never
  inherits the larger session budget. Only `inherit` keeps the session
  budget.
