# Vetted candidate list

The discovery milestone of a campaign is a **vetted candidate list**: every
Blink-addressable share of every story above its floor is either a candidate
with a measured packet, a `no-qualifying-mechanism` packet with its counts, a
`mandatory` row with its invariant, or a `handoff` row naming who owns the
work. The list is produced under the pre-sizing review hold and audited by a
human before any oracle build, A/B block or Pinpoint job runs.

"Vetted" means the packet below is complete and its numbers trace to bound
artifacts. It does not mean the candidate was tested; that is what sizing and
the fixed-plan A/B are for, and they come after the audit.

## What may and may not run while the list is being built

Allowed: exact-window profiles, `story_lens.py`, reading source, redundancy
counter probes in the instrumented twin (`redundancy_probe.h` +
`redundancy_evidence.py`) on the target story, cycle-profile captures of the
target story, single-story cycle profiles under a `--js-flags` experiment to
test a V8 hypothesis.

Not allowed until the hold is released: oracle builds that skip work,
candidate implementations, `mechanism_evidence.py` sizing arms, fixed-plan
A/B blocks, checkpoints, Pinpoint jobs. `advance --to sized` is refused by
the hold; do not work around it with characterization runs.

## The packet (one per candidate mechanism)

Recorded through `decompose` as a `novel` path plus its proposal file under
`<campaign>/proposals/`. Every field is required; "unknown" is a stop
condition, not a value.

| Field | Content |
| --- | --- |
| `mechanism_key` | stable `component/strategy` key |
| `target_story` | the one story whose silo sources every share |
| `win_shape` | `skip-subtree`, `reuse-result`, `representation`, `shorten-wait` |
| `investigation_layer` | 1–4 (1 and 2 need the redundancy packet) |
| `site` | file:line of the decision that makes the work run |
| `invariant_description` | "condition C holds in X of Y calls per step and permits removing exactly W while preserving B" |
| `redundancy_evidence` | `{path, sha256}` of the `redundancy_evidence.py` packet: calls per step, applicable fraction, repeat fraction, `probe_symbol` (the probed function, which must share samples with the row) and the probe patch digest; the probe key names the inputs the hypothesis says are unchanged and `applicable` states when the work could be skipped |
| `existing_mechanism` | the Chromium code that already avoids this work (symbol or file) and the count showing it does not here, or "none" with the count |
| `story_profile_share_pct` | inclusive share of the removed work in the target story, with its self share stated separately |
| `estimated_avoidable_fraction` | ≤ the measured applicable/repeat fraction |
| `estimated_local_story_impact_pct` | share × fraction, compared with the story floor from calibration |
| `cross_story_presence` | the same mechanism's share in every other story where it appears (discovery view; never summed into the impact) |
| `subtree_pruned` | named descendants removed and their combined share |
| `added_work` | checks, invalidation, cache maintenance on the hot path, with an estimate |
| `cold_path_cost` | what the change costs when the invariant does not hold |
| `competing_hypothesis` | the strongest alternative explanation or mechanism and why it lost |
| `safety_and_spec_analysis` | spec clauses, observers, lifecycle ordering, shadow trees, detached trees |
| `platform_sensitivity` | set from the removed work (font shaping, rendering backend, IPC), not from the root symbol |
| `catalog_check` | which discarded-candidate entries were read and why this differs in mechanism |
| `stop_condition` | the number that would end the investigation |
| `next_experiment` | the first sizing step, so the auditor can judge the plan |

## Audit criteria (what the human checks before releasing the hold)

1. Every number in the list traces to a digest-bound artifact (profile,
   lens, redundancy packet). Typed fractions are rejected.
2. Every candidate has a competitor and a stop condition.
3. Portability was set from the removed work.
4. The catalog was checked by mechanism, not by function name.
5. The per-story coverage ledger sums: candidates + mandatory + handoff +
   below-floor + unexplained = the story's addressable share, and no story
   has unexplained addressable share above its floor.
6. `no-qualifying-mechanism` and `mandatory` rows at or above the floor
   carry a bound packet and the arithmetic `share × supported fraction <
   floor`; a spec clause names a trigger, never an amount.
7. The probe key matches the hypothesis: a pointer-only key or an
   always-true `applicable` flag closes nothing, and a candidate's fraction is
   read from the predicate that names the unchanged inputs.
8. Every candidate names the existing mechanism (result cache, reuse path,
   dirty bit) that already covers part of this work and the count showing
   what it misses; "cache X" without that is a duplicate, not a candidate.
9. Every reviewed artifact was imported with the digest the reviewers
   attested (`reviews/gate-report-registry.json`); no report or transcript was
   edited after the review, and the transcripts are reviewer work, not
   orchestrator summaries.
10. Every `covered-by` row shares its samples with its owner in the profile
    stacks (`covered_by_sample_identity` ≥ 0.8 on the row) and sits under
    the owner's probed function (`covered_by_probe_identity` ≥ 0.8); a
    mechanism does not cover a phase it never appears in, and a shared
    ancestor frame is not coverage.
11. Every candidate row (`novel`/`known`) binds a packet from a probe on its
    own work whatever its layer, its `packet_hypothesis` names the packet
    number that bounds the fraction, and the numbers quoted in its
    `existing_mechanism` sentence are that packet's numbers. A candidate
    whose fraction, call count or applicable share cannot be found in a
    digest-bound packet was typed.
12. Every packet re-derives from its cited logs on the ledger host and its
    site is defined in its recorded probe patch (`decompose` checks both).
    A packet whose numbers differ from its own log is fabricated evidence;
    the human decides whether the campaign continues with that operator.
14. No `covered-by` row has a probed function with a packet for its story
    between it and its owner (`covered_by_nearest_probe` on the row), and no
    `applicable` predicate reads state written by another function.
13. Every bound packet is time-weighted (`time_weighted` true: every call
    recorded through `RedundancyScope`), the candidate's fraction is within
    both the call and the time fraction of its hypothesis, and a `repeat`
    key takes at least two distinct values per repetition.

## Coverage ledger

`campaign.py export-candidates` writes `candidates.md` with a per-story
coverage table from the lens (addressable, hand-off, overhead, frontier union,
unexplained). A story whose addressable share is neither claimed by a
candidate row nor closed by a mandatory/handoff/below-floor row is not done.
`handoff` is recorded as an `out-of-scope` decomposition row whose evidence
names the owner (V8 tiering, application JS, kernel) and the lens numbers.
