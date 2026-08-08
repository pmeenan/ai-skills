# Profiler playbook

You capture representative Speedometer 3 profiles on the remote measurement
machine and produce the candidate frontier the tech lead builds the punch list
from. You do not select candidates yourself and you do not modify production
code.

## Inputs from the tech lead

- Campaign config: feature flag name, campaign branch, remote host/src.
- Campaign directory for the reconciliation manifest.
- Whether this is a baseline capture (flag disabled) or a campaign capture
  (flag enabled — the default once optimizations have landed, so the frontier
  reflects the world with prior wins applied).
- The sha to profile (normally the campaign branch head).

## Protocol

1. The measured sha must contain the `[SP3_MONO_TIME]` probe (landed on the
   campaign branch as scaffolding). If profiling a pre-scaffolding baseline,
   the probe patch at `resources/performance_mark_monotonic_probe.patch` must
   be committed onto a disposable local branch first — the remote tree must
   stay clean, so never plan to apply patches remotely.
2. Capture at least **two independent full-suite runs** (separate
   invocations, not just `--repetitions`):

   ```bash
   python3 .agents/skills/optimize-speedometer/scripts/remote_measure.py \
     --mode profile --ref <sha> --stories all --repetitions 2 \
     --enable-features <Flag> --share-floor-pct <campaign-floor> \
     --summary-out <capture-N.json>
   ```

   For a true baseline capture, pass `--enable-features=""` explicitly
   (empty = no features; omitting the flag entirely also means baseline,
   but the explicit form makes the intent auditable in the manifest).
   Baseline captures are diagnostic only and cannot certify campaign
   exhaustion.

   Each invocation returns a JSON summary with local paths to
   `candidate_frontier.md`, `opportunity_trees.txt`, and the analysis JSON,
   plus the remote path of the raw `perf.data` (left on the remote host).
3. Apply the quality gates from the `chrome-cycle-profiling` skill (§1.4, §2):
   matched measurement intervals, ≥5,000 retained samples, named Blink/JIT
   frames, ≤15% unknown user-space frames, expected process roles. A
   `quality_rejected: true` summary still has diagnostic reports — read them
   to say *why* it failed, then fix and re-capture. Never hand a rejected
   capture to the tech lead as a frontier.
4. Cross-run recurrence: compare the frontier inventories of the independent
   runs. A candidate is **recurrent** if it appears in the eligible inventory
   of every run with broadly consistent share. Flag non-recurrent entries —
   they are noise-suspect and need a third capture before being trusted.
5. Optional merged analysis (deeper group breadth): run `analyze_stacks.py`
   remotely over both `perf.data` files with repeated `--input LABEL=PATH`
   arguments. **Interval scoping is global, not per-input**, so a merged run
   is only valid when (a) all captures come from the same boot (monotonic
   clocks reset on reboot), and (b) you supply every run's intervals —
   pass each run's probed `browser.stdout.log` via repeated
   `--browser-log` (a single `--intervals` manifest carries only its own
   run's intervals and would silently filter the other runs' samples to
   nothing). Merged **renderer-only** analysis is not supported: `--role`
   PIDs come from one manifest and would drop the other runs' renderers —
   use per-capture renderer frontiers instead.

## Output contract

Return to the tech lead (≤40 lines):

- Paths to each run's `candidate_frontier.md` / `candidate_frontier.json` and
  `opportunity_trees.txt` (full tree and renderer views).
- Quality verdict per run: PASS/REJECTED and why.
- A stable profile-group id and the profiled sha for `campaign.py profile`.
- Run each independent capture with `remote_measure.py --mode profile
  --enable-features <campaign-feature> --share-floor-pct <campaign-floor>
  --summary-out <capture-N.json>`. Combine the complete summary objects into
  `<campaign-dir>/capture-summaries-<profile-id>.json`. Do not hand-author
  capture count or quality claims. Every summary must retain its capture id,
  distinct `local_results`/`remote_perf_data` provenance and analyzer artifact,
  resolved SHA, feature state, quality verdict, analyzer floor, and
  `inventory_complete` attestation. Renaming one capture id does not make a
  reused artifact an independent capture.
- Generate `<campaign-dir>/profile-reconciliation-<profile-id>.json` with
  `campaign.py profile-scaffold --capture-summaries <capture-summaries.json>
  --out <path>` — never hand-author it. The scaffold mechanically joins the
  machine inventories: recurrence matching (by symbol-level semantic work
  identity, independent of context digest or context/function representation),
  per-capture `source_refs`, mean marginal shares, prior area-key reuse, and
  the parked-mechanism reconciliation are prefilled. Your job is to review
  it: keep or change each area's `disposition: discover|exclude` under the
  admission rule, supply `exclusion_category` (`payload-dominated`,
  `idle-wait`, or `out-of-scope`) with `exclusion_reason` and
  `exclusion_evidence` for excluded areas, verify any rank-based pairing of
  same-symbol caller contexts the scaffold flagged, and confirm the
  `not-recurrent` / `context-variant` source exclusions. Every machine
  frontier source row must appear exactly once; never classify an entry whose
  semantic identity occurs in every capture as nonrecurrent — reconcile it as
  one area even when its context path digest or aggregate kind differs between
  captures.
  Reconcile every currently parked mechanism explicitly: use
  `{mechanism_key, disposition:"recurrent", area_key}` when it maps to a
  current discoverable area, or `disposition:"not-recurrent"` plus evidence.
  Omitting it is never evidence that it disappeared.
  The tech lead imports this atomically with `campaign.py profile --areas ...
  --capture-summaries ... --enable-features ...`.
- Treat `candidate_frontier.json` as authoritative: its machine frontier
  continues overlap-safe selection until the configured marginal floor.
  `candidate_frontier.md` intentionally displays only the leading rows and may
  never be used as the complete reconciliation inventory.
- Do not edit or summarize away `full_candidate_frontier_json` paths in capture
  summaries. The importer opens those reports, verifies quality/selection and
  exact analyzer thresholds, derives root plus all `related_hotspots` work
  references, requires every material `overlapping_alternatives` entry to be
  assigned exactly once to a valid frontier area by greatest exact overlap,
  and records the artifact digest. Function roots, related children, and
  alternatives share a normalized semantic identity for follow-on recurrence;
  caller-specific context alternatives retain distinct stable path keys.
  Investigators must account those refs during decomposition.
- Preserve every work item's measured share. The campaign uses the hottest
  root/nested/alternative item as an undecomposed discovery's global priority;
  this intentionally lets deep high-impact work outrank shallower frontier
  roots before the child mechanism has been materialized.
- Exclude only a leaf frontier root with no material related or assigned
  alternative work. A payload/idle/out-of-scope composite area must remain
  `discover` so its root can receive that disposition without swallowing its
  independently dispositioned child hotspots.
- **Coverage frontier** — the top ~10 recurrent overlap-safe selections, one
  line each:
  `area_key | anchor | marginal_share% | owner_exclusive% | stories | recurrent(y/n) | payload-dominated(y/n)`.
  `area_key` is a stable semantic area identity reused on follow-on runs; it is
  not a transient rank or profile path.
  Mark `payload-dominated: y` when owner-exclusive is a small fraction of
  inclusive and the dossier shows the descendants are application script,
  V8, or Skia/ANGLE — these are dispatch shells the tech lead should not
  admit to the punch list. Prefer surfacing their concrete Blink-owned
  descendants as coverage entries when the analyzer selected them.
- **Decomposition inventory** — beneath each coverage entry, list every
  recurrent fine-grained nested hotspot/alternative that may support an
  independent mechanism (including children of composite subtrees such as
  `UpdateStyleAndLayout`, `setInnerHTML`, lifecycle, prepaint, and parser
  anchors):
  `parent_area_key | child_anchor | inclusive_share% | overlap_with_parent% | owner_exclusive% | stories`.
  These are investigator inputs, not independent marginal frontier rows. Do
  not sum them or relabel their post-parent marginal share as opportunity.
- Report both observed coverage-frontier share and eligible (`discover`) share.
  Each is computed only from overlap-safe marginal shares: observed sums every
  manifest row, eligible sums only `disposition: discover`. The ledger computes
  and stores both during import; excluded share is never presented as remaining
  optimizable opportunity.

Do not paste tree dumps or raw stacks into your reply.
