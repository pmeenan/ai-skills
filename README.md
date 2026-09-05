# ai-skills

Collection of skills for Chromium development and performance work.

Performance optimization uses a shared campaign pipeline:

- `optimize-campaign`: evidence gates, benchmark adapters, local/SSH execution,
  detailed runbook, role playbooks, tools, tests, and campaign entry points.
- `optimize-speedometer`: thin Speedometer 3 adapter trigger and semantics.
- `optimize-jetstream`: JetStream 3 trigger, result semantics, payload rules,
  and characterization workflow.
- `chrome-cycle-profiling`: on-host score and profile runners used by the
  campaign pipeline.

### Starting and resuming optimization campaigns

Human-facing prompts and prerequisites are available in the
[shared campaign README](optimize-campaign/README.md),
[Speedometer README](optimize-speedometer/README.md),
[cycle-profiling README](chrome-cycle-profiling/README.md), and
[JetStream preparation README](optimize-jetstream/README.md).
Use the explicit existing campaign directory when resuming part-way through.
