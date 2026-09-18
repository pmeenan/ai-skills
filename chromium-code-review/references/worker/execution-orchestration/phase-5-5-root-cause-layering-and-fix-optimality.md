<!-- Generated from ../../execution-orchestration.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Execution Orchestration (Phases 4 to 6)

Discovery execution, collection audit, verification, root-cause analysis, and
reconciliation. The orchestrator loads this file when Phase 4 becomes runnable
and works from it through the end of Phase 6, then hands off to
`references/synthesis-orchestration.md` for Phases 7 to 9.

Everything the orchestrator needs for these phases is here; `SKILL.md` keeps the
standing rules that apply across all phases — the context budget, partial
returns and narrow repair, sealing, waiting on `await-workers.py`, and the
prohibition on reading helper source — and does not restate anything below.

## Phase 5.5 — Root-Cause, Layering, And Fix Optimality

If the fresh verdict index has zero rows and the inventory index proves no
root-cause-required scope, write canonical empty Trigger Accounting and skip
planner and challengers. Otherwise root-cause trigger selection is analysis,
never inferred by the orchestrator from status lines. Spawn the **Root-Cause
Planner** (brief in `phase-briefs.md`). It reads every skeptic verdict, applies
every trigger in `references/verification-and-fixes.md`, includes the
inventory's root-cause-required change scopes, groups complete root
families/scopes into trace-sized batches, and writes `root-cause/batches.md`
plus one complete `briefs/RC⟨batch⟩.md` per batch. One family is indivisible
even when its members came from different skeptic batches; unrelated families
remain separate.

Spawn one **Root-Cause Challenger** per planned batch in capacity-derived waves.
Each executes Root-Cause, Layering, And Fix Optimality over every complete
family in its batch and writes `root-cause/RC⟨batch⟩.md`. It also decides
whether the validated fix is safely expressible as one small Gerrit suggested
edit, recording the exact selected range and replacement when it is, or the
specific reason it is not. Drafting never invents this decision from local
prose. The RC row is the canonical owner: reconciliation and drafting preserve
its family, decision, selected text, and replacement.

**Reopened issues are canonical ledger rows before they become work.** A
challenger that finds a better owner, missing caller family, duplicated state,
or new affected surface writes each candidate to its own append-only
`ledger/reopened/round-⟨N⟩-RC⟨batch⟩.md`, with stable ID `R⟨N⟩-RC⟨batch⟩-⟨n⟩`,
full evidence, origin, and parent row links. A row that exists only in a brief
or status message does not exist. The challenger may also request a named
discovery recipe, but does not synthesize a skeptic brief itself.

After collecting a round, if any canonical reopened rows exist, rerun the
requested narrowly scoped discovery-recipe briefs first; those workers append
evidence, amendments, or additional canonical reopened rows without replacing
the parent rows. Then rerun the Verification Planner in **delta mode** over
exactly that round's row IDs, execute the resulting skeptics, and rerun the
Root-Cause Planner in delta mode over their verdicts. Increment the round and
repeat until the planner reports no triggered or open rows. All rounds remain in
the manifest and reconciliation record. Synthesis may not start until every
reopened row is verified, refuted, merged, or converted into an owner question.

Run the validator with `--phase verification --require-active-lease` after the
final reopened round.
