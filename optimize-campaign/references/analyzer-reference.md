# Shared analyzer and capture reference

Detailed reference for `analyze_stacks.py` outputs and profile-capture
requirements. Read by the profiler and investigator roles; the tech lead
consumes only the resulting frontier summaries.

## Scope and weighting contract

Campaign frontiers come from the per-story silo analyses under
`analysis/stories/<story>/`: each story's exact-scored **renderer main-thread**
samples analyzed in isolation (`--stories-scope main-thread`), with every
share relative to that story's own main-thread scored cycles. Speedometer
times the renderer main thread, so concurrent compiler threads, the
compositor, raster workers and other processes are excluded from ranking;
`quality.samples_all_threads` records how many samples the scoped view left
out. Each story report also carries `score_time_composition` (sync and async
wall time, the async main-thread busy fraction estimated from sample density,
and the share of main-thread cycles inside async) so the reader knows whether
CPU removal or the latency route applies.
Campaign output is valid only when `quality.interval_kind` is `exact-scored`
and each story artifact's `selection.metric_weighting` is
`speedometer-story-v1` with `selection.story` naming the silo. Exact
intervals are the sync/async timers that feed the Speedometer score; the
broader suite windows are diagnostics and include setup/reporting work that
is not scored.

Within a story silo, each repetition group gets equal weight, so one slow
repetition cannot dominate the story's frontier. Entry keys are
story-qualified (`story:<name>/…`): the same symbol hot in two stories is two
independent, independently ranked identities. The full-suite view
(`analysis/full/`, `speedometer-geomean-v1` weighting) remains a diagnostic
cross-check only and never sources campaign shares. Local story shares are
discovery evidence; they do not turn cycle share into a score forecast. Size
mechanisms with `mechanism_evidence.py` against the same target story.

## Capture requirements (enforced by the collector)

The collector (`run_cycle_benchmark.py`, normally invoked remotely via
`remote_measure.py --mode profile`) must emit:

- every matched `[SP3_SCORE_TIME]` sync/async score interval, with suite/test
  labels. A legacy `[SP3_MONO_TIME]` outer log may be retained only when
  importing an old capture; new campaign probes do not emit it;
- PIDs and roles for browser, renderer, GPU, and utility processes;
- the raw `perf.data` file (left on the remote host — record its path);
- one per-story silo analysis per observed story under `analysis/stories/`,
  plus `stories_index.json` summarizing per-story samples, floors, and
  acceptance;
- full-process-tree and renderer-only candidate frontiers and
  `opportunity_trees.txt` reports (diagnostic views);
- `profile.collapsed` for interactive inspection (per story and full).

Reject a capture before candidate work if it has unmatched marks, fewer than
5,000 retained samples, median stack depth below 3, more than 15% unknown
user-space frames, disabled inline expansion, missing expected roles, or
obvious harness/startup leakage — and apply the sample-count and
100-nominal-samples-at-floor gates independently to **every** main-thread
story silo: a story below its local floor rejects the capture. Fix it with
more repetitions (32 default) or a higher sampling rate (fixed period
875,000 cycles ≈ 4 kHz per CPU at the locked base clock); the gate itself is
not adjustable. At 997 Hz and 16 repetitions the light TodoMVC stories had
under 20 main-thread samples at a 1% floor, which is why earlier frontiers
ranked noise.
Kernel symbols are reported separately from user-space symbol quality. The
collector still writes the diagnostic report sets on rejection, then exits
with status 3.

To reanalyze an existing capture (or merge several):

```bash
python3 .agents/skills/optimize-campaign/scripts/analyze_stacks.py \
  --input STORY_OR_RUN=path/to/perf.data \
  --intervals path/to/perf_run_manifest.json \
  --out-dir path/to/analysis
```

Repeat `--input LABEL=PATH` for independent story or repetition captures.
This adds group breadth to ranking and exposes candidates that recur across
runs.

## Frontier representations

Read `opportunity_trees.txt` first for orientation, then
`candidate_frontier.json` / `candidate_frontier.md` for candidate selection.
All views are built from the same weighted samples:

1. **Context tree:** root-to-leaf stack tries with inclusive and self weight.
   Use to find a coherent parent whose descendants form one expensive
   operation (style, layout, paint, bindings, IPC).
2. **Merged function view:** union of all samples containing a function,
   counted once despite recursion/inlining. Caller diversity exposes shared
   work spanning disjoint trees.
3. **Merged class area:** union of a qualified class's methods — a separate
   lens for work split across many methods; it does not consume coverage or
   suppress concrete operation candidates.
4. **Coverage frontier:** greedy selection by marginal uncovered cycles,
   recomputed after every selection. Strongly overlapping descendants stay as
   alternatives inside the parent dossier, not independent candidates.
5. **Text opportunity trees:** pruned cross-area tree plus exclusive Blink,
   Chromium, V8/JavaScript, ANGLE, and Skia ownership trees. Percentages use
   the global profile denominator; `[*]` marks frontier selections.

The cross-area tree retains raw inclusive transitions between repositories
(useful to follow an operation into Blink/V8/Skia). The repository-owned
trees assign each sample to its innermost recognized owner; use them to judge
where cycles are addressable. Application JS/JIT frames fold into one
`[application script execution]` node; V8 builtins, runtime, GC, and binding
plumbing stay visible.

Display flags (`--tree-min-share`, `--tree-max-depth`,
`--tree-max-children`) prune only the orientation report — never the JSON
inventory (the campaign default floor is 0.3%) or ranking samples.

## Portability flags

Each frontier entry carries `platform_sensitivity` (`null` or
`{tag, note}`). `rendering-backend` marks canvas flush, paint playback,
raster, image decode and GPU plumbing; `font-shaping` marks HarfBuzz, shape
caches and font matching; `process-plumbing` marks network, cache and IPC.
Their local cost depends on the rendering backend or platform and may not
exist on the Mac M1 PGO fleet bot, so they are Pinpoint-first leads. The
markdown table shows the tag in a Portability column.

## Two measures per entry

- `inclusive_share` / `marginal_share` retain the raw descendant tree,
  including V8/Skia cycles that disappear if the Chromium parent is avoided.
  **Rank eliminable operations with these.**
- `owner_exclusive_share` assigns each sample to its deepest recognized owner
  segment — it does not charge V8 execution to an outer Blink wrapper, but
  does charge Blink work entered from JS to the inner Blink operation. **Use
  for blame, repository routing, and implementation placement.**

## Candidate shapes to prefer

- a high-inclusive parent whose expensive children hang on one invalidation,
  traversal, allocation, or conversion decision;
- a merged Chromium function/class recurring under diverse callers;
- duplicated sibling subtrees that can share computed state;
- a boundary converting/copying the same data across bindings or IPC;
- a broad benchmark operation stable across repeated captures.

Excluded shells (message loops, thread mains, generic posted-task /
event-dispatch / script-runner wrappers) stay out of the frontier, but their
concrete descendants remain eligible. Do not promote a leaf on self time
alone — only with a removable mechanism and a sample set not better explained
by a parent.

Each frontier selection carries a nested-hotspot dossier searching all merged
functions substantially contained by the region (not just direct callees) —
this exposes deep recursion like cascade work without double-counting.

Re-rank after source inspection with:

```text
expected_value = marginal_profile_share
                 * evidenced_eliminable_fraction
                 * critical_path_factor
                 * confidence
                 / implementation_and_compatibility_cost
```

Unknown factors reduce confidence; never silently assume 1.
Use profile percentage points for `marginal_profile_share` (for example `0.8`
for 0.8%, not `0.008`). When recording this score, also set
`expected_value_unit: "profile-share-equivalent-pct"`. Without that exact unit,
the campaign refuses the override and ranks directly from profiler-measured
work refs. Overrides apply only after decomposition to concrete mechanisms; a
coarse discovery always retains its hottest-child measured priority. The
override changes scheduling only; it never changes profiler coverage or
exhaustion accounting.

## Visualization (audit aid, not the ranking mechanism)

- `opportunity_trees.txt`: searchable text orientation; parent and child rows
  usually cover the same samples — not additive.
- [Perfetto](https://ui.perfetto.dev/) opens `profile.collapsed` as a
  responsive flamegraph; a Firefox Profiler conversion retains timestamps
  when `perf script report gecko` is available.
- [Speedscope](https://www.speedscope.app/) imports `perf script` output for
  time-order / left-heavy / sandwich views.
- Keep inline expansion enabled for candidate selection: LTO inlines whole
  detach/context/cascade/lifecycle subtrees, so `--no-inline` output must
  never choose implementation work. Authoritative analysis passes
  `perf script --inline` (minutes of CPU, gigabytes of RAM — expected).
- Do not build Brendan Gregg SVG flamegraphs for routine exploration.
