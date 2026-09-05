# Campaign measurer playbook

Read [measurement-policy.md](../measurement-policy.md). Take the campaign's
frozen fixed plan as input (`statistics` in the ledger, minimum effect raised
to the calibrated MDE); never choose the sample size, primary endpoint or
regression margins from partial results.

1. Confirm the active campaign and whether another measurement holds the
   host lease. Follow an existing run before launching more work. Record the
   launch in the ledger before it starts, including runs that later fail.
2. Use official release-role PGO/ThinLTO score binaries, the pinned payload,
   the exact default workload inventory and the campaign display. The wrapper
   opens the tuner session (CPU policy, VT handoff, paused services, ASLR on).
3. Launch through `remote_measure.py --mode ab --opp <id> --feature <flag>`
   with at least 32 balanced ABBA/BAAB blocks. Every page-load result stays
   within its block; internal iterations do not increase the sample count.
   Preserve failed, cancelled and timed-out runs.
4. Keep the full regression workload family even for a targeted primary. A
   candidate's primary is its target story; the targeted checkpoint uses the
   landed target-story list from `campaign.py checkpoint-targets`; the
   full-suite checkpoint uses `suite`. No selective story reruns.
5. Inspect the per-block host observations (frequency, throttle counters,
   active VT, GPU tenants) and the manifest's family-adjusted story flags.
   Report INVALID, INCONCLUSIVE, REGRESSION or IMPROVEMENT with confidence
   bounds, MDE, sample count, seed, commits, activation, payload, display and
   environment. A non-significant regression test does not establish
   equivalence.
6. For a candidate, upload the isolated diff as a try CL and run
   `pinpoint_measure.py run --bot <campaign bot> --attempts 150`; keep the
   analysis summary as the fleet receipt. Abandon the CL if it fails.
7. Import checkpoints with `campaign.py checkpoint --kind <kind> --summary
   <remote_measure summary>` plus the independent gate reviews; land with
   `campaign.py advance --to landed --commit <sha> --performance-receipt
   <local manifest> --performance-receipt <pinpoint summary>`. Both pilot
   checkpoint outcomes must be fixed-plan IMPROVEMENTs before scaling.

Long runs take hours. Wait for the run; never replace missing output with
manually written results or create another manifest to escape a gate. An
unexpected benefit needs a separately seeded confirmation run.
