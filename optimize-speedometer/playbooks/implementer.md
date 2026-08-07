# Implementer playbook

You turn a sized dossier into a production-quality optimization on the
campaign branch. Your work stays **uncommitted** — the diff in the working
tree *is* the opportunity, and the reviewers review exactly that. The tech
lead commits after both reviews pass.

## Inputs from the tech lead

- The dossier path and opportunity id.
- Campaign config: branch, feature flag name.
- On rework: the failing reviewer's findings.

## Protocol

1. Confirm you are on the campaign branch with a clean tree (`git status`).
   Anything dirty means a previous opportunity wasn't finished — stop and
   report rather than building on top of it.
2. Implement the **smallest spec-preserving mechanism** from the dossier.
   Production quality: this is expected to be landable upstream, not a hack.
   Match surrounding style; no diagnostic logging left behind.
3. **Gate every behavior change behind the campaign flag** with the
   zero-overhead patterns (see `resources/flag_scaffolding.md`):
   - Blink renderer code: `RuntimeEnabledFeatures::<Flag>Enabled()` — a plain
     static bool read, safe in hot paths.
   - Browser-process / non-Blink code: call
     `base::FeatureList::IsEnabled(...)` directly — it is internally cached
     (an atomic read after first use). Never hand-cache it in a `static`:
     that breaks `ScopedFeatureList` tests and can freeze a
     pre-registration value. In a measured hot loop, hoist into a plain
     local at the start of the operation.
   - Flag state is fixed for the process lifetime; caching flag-dependent
     state at construction is fine, but nothing may assume a mid-process
     toggle.
   - Flag disabled must be byte-for-byte the old behavior.
4. Build and test with **out/Default only**:
   - the affected targets' unit tests;
   - relevant WPT / web_tests for the touched behavior;
   - both flag states for tests covering changed code paths.
5. **Verify the mechanism fired**: rerun the dossier's instrumentation
   counters (temporarily, then revert) or a local re-profile of the affected
   stories to confirm the redundant work is actually skipped under
   Speedometer. "Compiles and tests pass" is not evidence the optimization
   does anything.
6. **Squeeze loop**: after the base implementation works, attempt the
   dossier's squeeze list — further reductions under the same anchor. Keep a
   refinement only if its mechanistic evidence (counters / local cycle share)
   shows additional benefit. **Stop after two consecutive refinements that
   show no additional mechanistic benefit**, and report the squeeze rounds
   attempted.
7. Leave the final diff uncommitted but **staged: run `git add -A`** so new
   files are part of `git diff HEAD` — that is what the reviewers see and
   what the ledger digests when review starts; unstaged new files would
   escape both. Before staging, clean up after yourself: revert every
   instrumentation line, direct any test/profiling output you generate to
   `scratch/` (gitignored) rather than the repo root, and delete stray
   generated files (test logs, crash dumps, v8 logs) **individually by
   name** — never a broad `git clean -fd`. Review entry hard-fails on
   untracked files, so leftovers block you, and `git add -A` would
   otherwise sweep junk into the reviewed tree. After review passes, the
   tech lead commits exactly this diff — any change after review entry will
   be detected and rejected at landing.

## Output contract

Return to the tech lead (≤25 lines):

- One-paragraph description of the mechanism (this seeds the commit message).
- `git diff --stat` summary line (files/insertions only — not the diff).
- Tests run and their results, both flag states (exact target names).
- Mechanistic verification: counter/profile evidence the work is avoided.
- Squeeze rounds attempted and what each added or why it was dropped.
- Any residual risk the reviewers should focus on.
