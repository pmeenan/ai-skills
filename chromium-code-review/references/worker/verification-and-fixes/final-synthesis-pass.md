<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Final Synthesis Pass

Before final output, run a contradiction pass over the ledger and the draft
review:

- Does the final review account for every ledger entry — promoted at its
  calibrated severity (including downgrades), merged, or dismissed with a
  recorded reason?
- Did the root-cause/layering pass run for every triggering candidate or fix,
  and are any reopened rows verified, refuted, or converted into questions?
- Is the selected fix layer the invariant owner or intentionally below/above
  it for a cited reason?
- Are findings derived from actual code traces rather than assumptions?
- Do proposed fixes preserve the documented contract and nearby Chromium
  idioms? Have API-shaping fixes been weighed against reasonable alternatives?
- Did the integration trace prove the code is wired into the intended runtime
  path, and did the disabled/default-path trace prove old behavior is
  preserved?
- Do tests prove the intended behavior, or merely compile/run nearby paths?
- Are prior-review findings clearly separated from new findings?
- Is any finding contradicted by another caller path, wrapper, override,
  feature flag, or test-only restriction?
- Are any findings only style preferences that should be P3 or omitted?
- Are severities calibrated for this CL's position in any larger stack?
- What did you not verify — tests not run, callers not traced, platform paths
  not checked, assumptions that still need confirmation? State these in the
  review's Verification Notes.

Scale this pass by evidence cards rather than by ingesting the entire record.
The Challenge Planner assigns no more than six finding/question cards to a
content shard and no more than 200 reconciliation rows to a structural shard,
reducing either count whenever the assigned artifacts would exceed 35% of a
known context window or the 128 KiB unknown-capacity fallback. Every item/row
appears in exactly one shard.

For a large draft, challengers consume immutable indexed draft/Gerrit sections,
not the whole assembled output. Content shards read only assigned sections,
their bounded cards, and the global frame. Structural shards read assigned row
ranges, the gate, and frame. One global shard checks section order, hashes,
headings, verdict/finding consistency, and Gerrit target coverage from compact
indexes. Each challenge row records the section hashes audited. A collector
verifies exact card/row/section coverage and exactly one `global:consistency`
token, then writes the compact challenge index.

Any draft change after challenge creates a new draft revision and requires a
new full challenge generation: fresh plan, fresh shard IDs/artifacts, and a
fresh collected index. Rechecking only the previously reported problems is not
a contradiction pass and cannot satisfy the gate. Gerrit freshness is checked
only after the last collected challenge and is rechecked after every revision.
