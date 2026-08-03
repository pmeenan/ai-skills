<!-- Generated from ../../verification-and-fixes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Verification And Fixes

Read this before promoting ledger candidates into the review and before
recommending or endorsing any concrete fix. This file is the precision gate:
discovery deliberately over-generates, and this pass separates real findings
from plausible-but-wrong ones. Severity definitions and calibration notes live
in `references/synthesis-and-output.md`.

## Execution-Based Verification

Code citations and paper traces are the default standard of evidence — cheap
and almost always sufficient. Building the patchset or running tests is a
bounded, last-resort tier, not a routine step:

- Use it only in verification (never discovery), and only for a P1/P2
  candidate whose paper trace is genuinely contested — where running the
  smallest test would settle confirm-vs-refute.
- Build only the narrowest target against an existing warm build directory
  (`autoninja -C out/<existing> <test_target>`, e.g. `net_unittests` or
  `components_unittests`, plus a tight `--gtest_filter`). Never `gn gen` a
  fresh output directory in a temporary worktree: a cold Chromium build
  costs an hour-plus and buys less than an hour of tracing. If no warm
  build exists, skip execution and record the candidate as "needs
  execution verification" in Verification Notes.
- Budget it: if the build or run exceeds roughly ten minutes, stop and fall
  back to the paper trace.
- Record in Verification Notes exactly what was built or run, how long it
  took, and which candidate it settled — so the next iteration can judge
  whether the time was earned. The regression test named in a P1/P2 finding
  is a description for the CL owner, not an obligation to implement and run
  it.
- Execution never includes applying a proposed fix or a new test to the
  user's checkout or the review worktree. If trying a change is truly
  unavoidable, copy the touched files to a scratch directory outside the
  repository and experiment there; the review itself stays read-only.
