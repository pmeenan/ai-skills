<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Verifying Candidate Findings

Verify each non-trivial candidate before presenting it. Prefer concrete code
traces over speculative concerns — but spend the trace: refute candidates with
code, not from memory.

- Build a minimal state or call trace from the code that demonstrates the
  issue, or demonstrates its absence.
- Read the candidate's `Candidate descriptors` row and close every declared
  obligation. Do not substitute a local syntax observation for a
  `local-proof`, `base-contract`, `caller-reachability`, `callee/backend-implementation`,
  `async-operation-owner`, `destruction/cancellation`, `platform-branches`,
  or `style-authority` trace.
- Cite the exact code path and any relevant tests or comments.
- Classify the issue: correctness bug, contract mismatch, missing test,
  performance risk, lifecycle risk, or polish.
- Check whether existing tests intentionally codify the observed behavior.
- Challenge the finding: look for alternate caller paths, wrappers, overrides,
  feature gates, or invariants that make it unreachable or lower its severity.
- Apply Universal Verification Principles during refutation:
  - **Documented Intent Overrides Syntactic Omissions:** Adjacent inline comments, docstrings, and header contracts are binding design specifications. An omitted branch or conditional that is explicitly documented in code comments or header docs as intentional design is NOT a defect unless it violates higher-level requirements.
  - **Burden of Proof Requires Reachable Harm:** A missing `if` check or omitted pre-filter is ONLY a bug if a reachable trace produces a concrete bad state (memory corruption, security bypass, data loss, or broken invariant). Omitting an optional defensive check on a safe or idempotent path (e.g. `std::map::erase` on a key) is not a defect; the reviewer must prove reachable harm, not demand arbitrary defensive guards.
  - **Producer/Consumer Symmetry (Read vs. Write Scoping):** Query/read paths scope to the key space of stored data, not to the write-side preconditions of the caller. Cache, index, and storage lookup APIs must match the full potential key space of stored data, regardless of caller context.
- To refute a candidate, name the specific guard (the line) or documented design contract/comment that proves safe behavior, or produce the concrete trace that completes safely. "Looks handled" or "the caller probably checks" is not a refutation — it is the shallow read the candidate exists to challenge. For hypotheses written as IF/THEN/UNLESS, refutation means filling in the UNLESS with a citation.
- If honest tracing can neither confirm nor refute a candidate, do not drop
  it: convert it into a question for the CL owner in the review's Questions
  section, stating what you traced and what remains unproven. Uncertainty
  rounded down to "probably fine" is how reviews miss real bugs.
- Never edit a discovery ledger to record a verdict. Record refutation in the
  skeptic verdict file and reconciliation; discovery rows remain append-only.
  If a worker must correct its own earlier row, use the normative Amendments
  section from templates.md, preserving the original row and ID.
- Matrix cells marked incompatible-but-guarded are verification inputs too:
  confirm that the named guard actually guards the cell's scenario, on the
  path the scenario takes. In a measured run a cell cited `ShouldTruncate()`
  as the guard for `StopCaching(keep_entry=true)` — but that guard only runs
  on the failure path, and the success path skipped it entirely.
- Distinguish observation from proposed fix. Never recommend a concrete fix
  until it has been traced through the relevant edge cases below.
- For async-lifetime claims, identify who retains the caller buffer or
  operation state after an `ERR_IO_PENDING`-style return, then trace
  cancellation and callback invalidation through destruction on each backend.
  Local variable death, declaration order, or callback capture syntax alone
  cannot confirm a use-after-free.
- For style claims, cite authority applicable to the changed directory.
  Blink/WebKit naming guidance is not a Chromium-wide convention, and a
  mechanical `bool` hit without local authority or concrete callsite ambiguity
  is REFUTED.
