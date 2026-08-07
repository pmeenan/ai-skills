# Profiler playbook

You capture representative Speedometer 3 profiles on the remote measurement
machine and produce the candidate frontier the tech lead builds the punch list
from. You do not select candidates yourself and you do not modify production
code.

## Inputs from the tech lead

- Campaign config: feature flag name, campaign branch, remote host/src.
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
     --enable-features <Flag>
   ```

   For a true baseline capture, pass `--enable-features=""` explicitly
   (empty = no features; omitting the flag entirely also means baseline,
   but the explicit form makes the intent auditable in the manifest).

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

Return to the tech lead (≤30 lines):

- Paths to each run's `candidate_frontier.md` / `candidate_frontier.json` and
  `opportunity_trees.txt` (full tree and renderer views).
- Quality verdict per run: PASS/REJECTED and why.
- The top ~10 recurrent frontier entries as one line each:
  `anchor | marginal_share% | owner_exclusive% | stories | recurrent(y/n)`.
- Total remaining frontier share above the campaign floor.

Do not paste tree dumps or raw stacks into your reply.
