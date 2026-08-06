---
name: optimize-speedometer
description: >-
  Discover, prototype, and validate CPU performance optimizations in Desktop
  Chromium for Speedometer 3. Use for full-suite profiling, tree-based and
  cross-context candidate discovery, opportunity sizing, responsive flamegraph
  inspection, randomized A/B verification, and cumulative integration. Ranks
  optimization regions by overlap-aware sample coverage instead of leaf-node
  self time.
---

# Speedometer 3 Optimization Runbook

## Non-negotiable principles

1. Treat a sample as a complete call stack. Never turn a flat self-time or leaf
   list directly into an implementation queue.
2. Treat inclusive sampled cycles as an opportunity bound, not a predicted
   Speedometer score improvement. Establish eliminability with an intervention
   before writing production code.
3. Aggregate both context-sensitive subtrees and context-merged functions or
   classes. The latter finds common work repeated under otherwise separate
   trees.
4. Track both raw inclusive opportunity and deepest-owner-exclusive cost at
   V8/ANGLE/Skia boundaries. A Blink parent retains descendant engine cycles in
   its opportunity bound when avoiding that parent would avoid the whole tree;
   its owner-exclusive field does not charge those cycles to Blink. When JS
   calls back into Blink, start a new Chromium-owned segment for attribution.
5. Rank a candidate by its marginal, previously-uncovered sample set. Nested
   frames are competing explanations of the same cycles, not additive wins.
6. Keep no more than three unmeasured production candidates in flight. Measure
   candidates individually, then measure small cumulative batches.
7. Restrict production changes to Chromium-owned code. Do not modify V8,
   ANGLE, or other separately owned repositories.
8. Local headless results are screening evidence. Bare-metal desktop or
   Pinpoint runs are authoritative.
9. Optimize analysis for fidelity, not processing latency or modest memory use.
   A single capture may direct days of engineering, so retain inline frames,
   full recorded stacks, exact sample membership, and the complete inventory.

## Phase 0: Preflight

Use an official PGO/LTO build with frame pointers and symbols. Confirm hardware
sampling and JIT symbolization:

```bash
perf stat -e cycles true
out/perf/chrome --user-data-dir=/tmp/sp3-preflight-profile \
  --no-first-run --no-sandbox --headless=new \
  --js-flags=--perf-basic-prof https://example.com
```

Run a genuine session A/A before evaluating changes:

```bash
python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py \
  --browser=out/perf/chrome --blocks=5 --aa
```

Require named Chromium frames, named JIT frames, useful call-chain depth, and a
stable A/A noise estimate. Keep `/tmp/perf-*.map` until profile conversion is
complete.

## Phase 1: Capture only scored work

Apply the bundled Speedometer `performance.mark()` monotonic-time probe in a
disposable profiling worktree, then rebuild Chrome:

```bash
git apply --check \
  .agents/skills/optimize-speedometer/resources/performance_mark_monotonic_probe.patch
git apply \
  .agents/skills/optimize-speedometer/resources/performance_mark_monotonic_probe.patch
autoninja -C out/perf chrome
```

The probe emits exactly `[SP3_MONO_TIME] sp3-measurement-start: <seconds>` and
the corresponding end line on stderr using `base::TimeTicks`, which shares the
Linux monotonic clock domain with `perf record -k mono`. Do not start capture
unless `git apply --check` succeeds; update the bundled patch when upstream
context changes.

Capture the launched Chrome process tree with hardware cycles, `-F 997`, call
chains, and `-k mono`:

```bash
python3 .agents/skills/chrome-cycle-profiling/scripts/run_cycle_benchmark.py \
  --browser=out/perf/chrome --stories=all --repetitions=2
```

The collector enables `Speedometer3OptimizationSet` by default to preserve the
optimization campaign configuration. Pass `--enable-features=` for a true
baseline capture, or provide a comma-separated feature list explicitly. The
manifest records the effective value.

The collector must emit:

- every matched measurement start/end interval, not one first-start/last-end
  envelope;
- PIDs and roles for browser, renderer, GPU, and utility processes;
- the raw `perf.data` file;
- full-process-tree and renderer-only candidate frontiers;
- full-process-tree and renderer-only `opportunity_trees.txt` reports;
- `profile.collapsed` for interactive inspection.

Reject the capture before candidate work if it has unmatched marks, fewer than
5,000 retained samples, median stack depth below 3, more than 15% unknown
user-space frames, disabled inline expansion, missing expected roles, or
obvious harness/startup leakage. Kernel symbols are reported separately from
user-space symbol quality.

The collector runs both full-tree and renderer analyses even when the first
quality gate rejects its profile. It writes both diagnostic report sets, then
exits with status 3 after listing every rejected view.

To reanalyze an existing capture:

```bash
python3 .agents/skills/optimize-speedometer/scripts/analyze_stacks.py \
  --input STORY_OR_RUN=path/to/perf.data \
  --intervals path/to/perf_run_manifest.json \
  --out-dir path/to/analysis
```

Repeat `--input LABEL=PATH` for independent story or repetition captures. This
adds group breadth to ranking and exposes candidates that recur across runs.

## Phase 2: Build an autonomous candidate frontier

Read `opportunity_trees.txt` first for orientation, then
`candidate_frontier.json` and `candidate_frontier.md` for autonomous candidate
selection. The analyzer builds these representations from the same weighted
samples:

1. **Context tree:** root-to-leaf stack tries with inclusive and self weight.
   Use this to find a coherent parent whose descendants form an expensive
   operation such as style, layout, paint, bindings, or IPC.
2. **Merged function view:** union all samples containing the same function,
   counting each sample once even when recursion or inlining repeats it. Use
   caller diversity to find shared work spanning disjoint trees.
3. **Merged class area:** union methods of the same qualified class. This is a
   separate search lens for work split across many methods; a broad class does
   not consume coverage or suppress concrete operation candidates.
4. **Coverage frontier:** greedily select high-value regions by marginal
   uncovered cycles, recomputing marginal value after every selection. Keep
   strongly overlapping descendants as alternatives within the parent dossier
   instead of independent candidates.
5. **Text opportunity trees:** emit a pruned cross-area tree plus exclusive
   Blink, Chromium, V8/JavaScript, ANGLE, and Skia ownership trees. Percentages
   always use the global profile denominator. Linear trunks, insignificant
   branches, and depth-limited descendants are omitted without synthetic
   placeholder rows. Unicode tree connectors (`├──`, `└──`, and `│`) preserve
   sibling ancestry through deep branches; `[*]` marks an operation selected
   by the coverage frontier.

The cross-area tree deliberately retains raw inclusive transitions between
repositories, so it is useful for visually following a browser operation into
Blink, V8, or Skia. The repository-owned trees assign each sample to its
innermost recognized owner segment. Use those views to judge where the cycles
are addressable: an outer Blink event-dispatch wrapper does not inherit nested
application script or V8 work. All application-owned JavaScript and JIT frames
are folded into one `[application script execution]` node; V8 builtins, runtime,
compiler, garbage-collection, and binding plumbing remain visible.

The default text-tree display floor is 0.5% of the global profile, with a
maximum visible depth of 10 and eight children per node. Override these with
`--tree-min-share`, `--tree-max-depth`, and `--tree-max-children`. These flags
only prune the orientation report; they do not reduce the complete JSON
inventory or the samples used for ranking.

Each selected operation includes an automatically generated nested-hotspot
dossier. It searches all merged functions whose samples are substantially
contained by the selected region, not merely its direct callees. This exposes
deep recursive operations such as style cascade work and lifecycle teardown
without double-counting them as additive opportunities. The JSON retains the
complete related-function list; the human-readable dossier uses weighted
overlap to collapse near-identical inline/lifecycle aliases and display
representative branches.

Retain the complete eligible inventory in JSON even when the displayed
frontier is small. The default inventory floor is 0.1% so important children
below the historical 0.5% cutoff remain auditable.

The analyzer reports two complementary measures. `inclusive_share` and
`marginal_share` retain the raw descendant tree, including V8/JavaScript or
Skia cycles that would disappear if a higher-level Chromium operation were
avoided. `owner_exclusive_share` assigns a sample only to its deepest
recognized owner segment. It therefore does not charge V8 execution to an
outer Blink binding or message-loop frame, but it does charge native Blink work
entered from JS to the inner Blink operation. Rank eliminable operations using
raw inclusive and marginal coverage; use owner-exclusive coverage for blame,
repository routing, and implementation placement.

For each frontier entry, inspect its top callers, callees, tree fraction,
caller diversity, group distribution, and overlapping alternatives. Then map
the anchor to source and write a candidate dossier containing:

- the expensive operation represented by the subtree;
- why the work occurs and which invariant may avoid, combine, defer, or reduce
  it;
- the union sample share and marginal share;
- whether it repeats under multiple callers, stories, or processes;
- the expected eliminable fraction, with evidence;
- correctness, compatibility, memory, and ownership risks;
- a cheap intervention that can bound the opportunity;
- a production design only after the intervention succeeds.

Prefer these candidate shapes:

- a high-inclusive parent with several expensive children controlled by one
  invalidation, traversal, allocation, or conversion decision;
- a merged Chromium function/class recurring under diverse callers;
- duplicated sibling subtrees that can share computed state;
- a boundary that converts or copies the same data across bindings or IPC;
- a broad benchmark operation whose cost is stable across repeated captures.

Exclude message-loop, thread-main, worker-job, and generic posted-task shells
that merge unrelated operations merely because they share an execution loop.
Keep their concrete descendants eligible. Generic IPC dispatch boundaries may
remain when their dossiers identify repeated conversion or routing work across
messages. Likewise exclude generic Blink-to-script callback, event-listener,
and script-runner shells from the autonomous frontier. Keep concrete parents
such as a specific teardown, lifecycle phase, or simulated operation eligible;
their raw inclusive opportunity may legitimately include script work they can
avoid.

Do not promote a leaf merely because it has high self time. Promote it only if
source inspection identifies a removable mechanism and its sample set is not
already explained by a more useful parent.

The analyzer's heuristic score is for ordering investigations. Re-rank after
source inspection using:

```text
expected_value = marginal_profile_share
                 * evidenced_eliminable_fraction
                 * critical_path_factor
                 * confidence
                 / implementation_and_compatibility_cost
```

Unknown factors reduce confidence; do not silently assume they are 1.

## Phase 3: Opportunity-size before production implementation

For one candidate at a time, make the smallest diagnostic intervention that
removes or bypasses the suspected mechanism. A deliberately incorrect oracle
is allowed only on an isolated disposable branch, clearly labeled as invalid,
and only to estimate a ceiling. Never merge or cumulatively benchmark an
oracle as a candidate implementation.

Run a short randomized A/B screen immediately. Fast-fail when:

- the intervention removes the sampled subtree but does not move the score;
- the measured ceiling is below the session MDE or too small for the goal;
- the expensive work is off the scored critical path;
- source inspection shows the cost is owned out of scope;
- preserving observable behavior removes the proposed saving.

If the subtree disappears without score movement, record that evidence. Do not
continue optimizing its leaves.

## Phase 4: Implement and verify

For an oracle-positive candidate:

1. Implement the smallest spec-preserving mechanism on a candidate branch.
2. Build the affected target and run focused unit tests, relevant WPTs, and
   recompute-and-compare assertions where practical.
3. Re-profile a localized story. Confirm the intended subtree or merged sample
   set actually shrinks without merely moving cost elsewhere.
4. Run randomized ABBA/BAAB verification:

   ```bash
   python3 .agents/skills/chrome-cycle-profiling/scripts/run_ab_benchmark.py \
     --browser=out/perf/chrome --blocks=5 --feature=YourFeature
   ```

5. Use block log differences. Scale from 5 to at most 15 blocks when the
   observed effect is promising but underpowered. Classify as inconclusive
   after 15 blocks and route to Pinpoint or stop local reruns.

Check geometry, DOM behavior, lifecycle ordering, observers, custom elements,
style invalidation, paint/compositing, accessibility, focus/selection,
threading, memory lifetime, and Oilpan implications as applicable.

## Phase 5: Cumulative integration

Only individually supported candidates enter the cumulative integration
branch. Integrate at most three new candidates before a full-suite measurement
so interactions and regressions remain attributable.

Speedometer aggregates sub-scores geometrically, so gains are not additive.
Require the full combined patch to pass:

- per-story lower 95% confidence bound no worse than `ln(0.98)`;
- final full-suite lower 95% confidence bound at least `ln(1.05)` for a 5%
  goal;
- desktop Pinpoint or bare-metal confirmation before declaring success.

## Responsive visualization

Visualization audits the machine ranking; it is not the ranking mechanism.

- Start with `opportunity_trees.txt` for a fast, searchable text summary of
  material trunks and repository ownership. It is an orientation aid, not an
  additive ranking: a parent and its children usually cover the same samples.
- Open `profile.collapsed` in [Perfetto](https://ui.perfetto.dev/) for a
  responsive interactive flamegraph. Perfetto accepts collapsed stacks and
  pprof; a Firefox Profiler JSON conversion retains timestamps for range
  selection when `perf script report gecko` is available.
- Use [Speedscope](https://www.speedscope.app/) for its WebGL time-order,
  left-heavy, and sandwich views. It can import ordinary `perf script` output
  directly and runs locally in the browser.
- Keep inline expansion enabled for candidate selection. Official
  LTO builds inline important parent operations, so `--no-inline` may hide
  entire detach, context-creation, cascade, and lifecycle subtrees. Use
  `--no-inline --allow-low-quality` only to diagnose a broken pipeline; never
  use that output to choose implementation work. Preserve the profiler's full
  captured stack depth and do not truncate inventories to save analysis time or
  memory. Authoritative analysis passes `perf script --inline` explicitly;
  expect symbolization to take minutes and several gigabytes of RAM.

Do not generate Brendan Gregg SVG flamegraphs for routine exploration. Build a
custom viewer only if Chromium-specific overlays are required; Perfetto and
Speedscope already solve the rendering and interaction problem.
