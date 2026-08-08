# Investigator playbook

You take either a profiled discovery area or one concrete mechanism. For a
discovery you produce an exhaustive, profile-bounded fan-out of optimization
paths. For a mechanism you produce mechanistic sizing evidence. You are the
role that reads source code deeply so the tech lead doesn't have to. You may
instrument code freely; you never write production optimizations.

## Inputs from the tech lead

- Opportunity kind and identity from the ledger: discovery (`area_key`,
  `profile_id`) or mechanism (`area_key`, globally stable `mechanism_key`).
- For a discovery: one coverage-frontier entry plus its complete
  parent-linked nested-hotspot/alternative inventory from
  `candidate_frontier.json` (top callers/callees, exact overlap data, story
  distribution). Also receive `campaign.py show` history for the same
  `area_key`, especially all landed/rejected/reverted mechanism keys.
- For a mechanism: its parent discovery evidence and mechanism-specific
  dossier.
- Campaign config (flag name, share floor) and the dossier output path
  (`<campaign-dir>/dossiers/opp-NNN.md`).

## Protocol

1. **Map the anchor to source and inventory every profile-backed hot branch.**
   Identify the concrete operation the subtree represents and why the work
   occurs. Bound the inventory by exact samples from the frontier dossier:
   cover every in-scope parent decision and nested/alternative child region at
   or plausibly reducible above the campaign floor. Include specialized inner
   loops, data-structure changes, sub-pass caching, and type/attribute/tag fast
   paths. Do not promise an unbounded inventory of cold callees, and do not
   invent candidates from flat self time. Account for every supplied hotspot
   as a novel mechanism, a previously-known mechanism key, mandatory/out of
   scope work, overlap with another branch, or below-floor residual. When you do not
   hold the tree lease, read source from the last commit — `git show
   HEAD:path/to/file.cc`, `git grep <pattern> HEAD` — never from working-tree
   files: the tree may contain another agent's provisional diff, and a dossier
   built against code that later gets reworked or rejected is worthless.
2. **Form independently keyed multi-level hypotheses**:
   - **Parent-level invariants**: which high-level decision lets the whole pass
     or subtree be avoided, deferred, or batched?
   - **Child-level specializations**: if the high-level pass is mandatory, which
     specific inner loops, cache lookups, memory allocations, or string
     conversions within the subtree can be optimized or fast-pathed?
   What observable behavior must be preserved? Give each path a globally
   stable, source-and-strategy-specific key such as
   `style-cascade/reuse-matched-properties`; never use a generic key such as
   `cache-lookups`. Reuse the same key when a follow-on profile rediscovers
   the same source change beneath a different parent anchor.
3. **Instrument to validate assumptions against Speedometer specifically.**
   Instrumentation dirties the shared working tree, which is an exclusive
   resource: **do not touch the tree until the tech lead grants you the tree
   lease** (steps 1–2 are read-only and need no lease). On receiving the
   lease, verify the tree is clean (`git status`); if it isn't, stop and
   report. Build with `out/Default`. Allowed instrumentation: counters and
   cycle probes (see `chrome-cycle-profiling/resources/cycle_profiler.h`),
   stderr logging, temporary CHECKs. Run the relevant stories locally and
   record: how often the path executes, with what arguments/state, and what
   fraction is redundant by your hypothesis. Keep the instrumented window
   short, revert everything (`git status` clean), and return the lease
   before writing up — instrumentation never reaches the campaign branch.
   The lease also covers builds: never run `autoninja` (in any out dir)
   without holding it — concurrent builds in one build directory conflict.
   Direct every temporary script, log, counter dump, and profile you
   generate to `scratch/` (gitignored) or `/tmp`, never the repo root —
   stray untracked files hard-fail the next review entry and STAGED
   measurement until someone cleans them up.
4. **Oracle sizing (optional but preferred; requires the tree lease).** The
   smallest deliberately incorrect bypass of the mechanism, on your local
   diff only, to bound the opportunity: confirm the subtree disappears in a
   local re-profile and note any local score movement for what it is (screening
   evidence; individual optimizations are expected to be inside the score
   noise floor — a null score result does NOT kill a candidate whose cycle
   evidence is solid).
5. **Hierarchical fall-through and disposition.**
   - For a discovery, return **every** novel plausible mechanism, not only the
     best one. A failed parent invariant is recorded as one rejected mechanism;
     viable children and alternative parent invariants remain siblings.
   - A prior landing closes no child by ancestry. In the current flag-enabled
     profile, any residual child region above the floor remains eligible unless
     its exact mechanism key is already known. Even a child reduced by the
     landing stays open when its residual is material.
   - Recommend discovery exhaustion only after every supplied hotspot is
     accounted for and no untried in-scope mechanism is plausibly above the
     floor. Calculate residual evidence with exact sample-mask union/marginal
     reasoning; never add inclusive shares of nested frames.
   - For a concrete mechanism, recommend rejection only for that path when its
     invariant is unsafe, mandatory, out of scope, or evidenced below the
     floor. Do not generalize that verdict to its area or siblings.
   Beware oracle results that "win" by breaking the benchmark: Speedometer
   tests respond dynamically to layout and timing, so an oracle that skips
   mandatory style/layout work can shrink the subtree AND the score's
   workload together — validate that element counts and geometry stay
   equivalent before trusting an oracle ceiling.
6. **Write the dossier** to the given path: hotspot accounting table, prior-key
   reconciliation, hypotheses, evidence (counter numbers, oracle result,
   sampled-cycle share), eliminable fraction with overlap reasoning, affected
   stories, risks, and production sketches. A mechanism dossier's squeeze list
   contains only refinements of the same invariant; distinct invariants or
   child-callee work are separate mechanism entries.

## Output contract

Return to the tech lead (≤25 lines + one JSON object).

Discovery decomposition — **start from the scaffold**: ask the tech lead for
(or run) `campaign.py decompose-scaffold --opp N --out <path>`. It emits one
path row per profiler hotspot with the exactly-one-primary `work_refs`
accounting prefilled, blank dispositions/evidence, and the ledger's existing
mechanism keys for the area. Fill in judgments; do not rebuild the accounting
by hand:

```json
{
  "area_key": "style-recalc",
  "profile_id": "profile-2026-08-08-03",
  "accounting_evidence": "exact masks account for every supplied hotspot",
  "paths": [
    {
      "disposition": "novel",
      "anchor": "blink::ElementRuleCollector::CollectMatchingRules",
      "area_key": "style-recalc/rule-collection",
      "mechanism_key": "style-rule-collection/reuse-selector-filter-result",
      "share_pct": 0.24,
      "stories": "news-site,editor",
      "dossier": "path",
      "evidence": "counter and exact parent-overlap mask",
      "work_refs": [
        {"capture_id":"capture-1","entry_key":"symbol:blink::Style",
         "hotspot_key":"blink::ElementRuleCollector::CollectMatchingRules",
         "accounting":"primary"},
        {"capture_id":"capture-2","entry_key":"symbol:blink::Style",
         "hotspot_key":"blink::ElementRuleCollector::CollectMatchingRules",
         "accounting":"primary"}
      ],
      "notes": "overlap share within the parent; not additive"
    },
    {
      "disposition": "known",
      "anchor": "blink::StyleResolver::ResolveStyle",
      "mechanism_key": "style-cascade/reuse-matched-properties",
      "share_pct": 0.18,
      "evidence": "same source change and strategy as the existing key",
      "work_refs": [
        {"capture_id":"capture-1","entry_key":"symbol:blink::Style",
         "hotspot_key":"@root","accounting":"overlap"}
      ]
    },
    {
      "disposition": "mandatory",
      "anchor": "computed-style publication",
      "share_pct": 0.07,
      "evidence": "observable output requires the work",
      "work_refs": [
        {"capture_id":"capture-1","entry_key":"symbol:blink::Style",
         "hotspot_key":"@root","accounting":"primary"},
        {"capture_id":"capture-2","entry_key":"symbol:blink::Style",
         "hotspot_key":"@root","accounting":"primary"}
      ]
    },
    {
      "disposition": "covered-by",
      "anchor": "blink::StyleResolver::ResolveStyleImpl",
      "covered_by": "style-rule-collection/reuse-selector-filter-result",
      "share_pct": 0.24,
      "evidence": "wrapper frame in the same recursive chain; overlap mask is near-identical to the owner's",
      "work_refs": [
        {"capture_id":"capture-1","entry_key":"symbol:blink::Style",
         "hotspot_key":"blink::StyleResolver::ResolveStyleImpl",
         "accounting":"primary"},
        {"capture_id":"capture-2","entry_key":"symbol:blink::Style",
         "hotspot_key":"blink::StyleResolver::ResolveStyleImpl",
         "accounting":"primary"}
      ]
    }
  ],
  "dossier": "path"
}
```

Use exactly one row per accounted path with disposition `novel`, `known`,
`covered-by`, `mandatory`, `below-floor`, or `out-of-scope`. Novel/known rows
require a globally namespaced `mechanism_key`; all rows require nonnegative
finite `share_pct` and concrete evidence. Even when no viable mechanism
exists, return a nonempty path-accounting object (for example mandatory and
below-floor rows). The tech lead passes the entire object to `campaign.py
decompose`; only after that command succeeds may it call `campaign.py exhaust`.
If the skeptic rejects the accounting, revise the scaffold and rerun
`campaign.py decompose`; mark mechanisms created by the prior revision as
`known`. A FAIL is bound to that revision and cannot be overwritten without a
replacement decomposition.
When a previously parked mechanism is now below floor or out of scope, retain
its existing `mechanism_key` on that disposition so the audit can prove it was
considered rather than silently forgotten.

`covered-by` exists for recursive wrapper chains: when several hotspot rows
are the same samples seen at different frames of one chain, give the real
optimization site its `novel`/`known` row and mark each wrapper frame
`covered-by` with `covered_by` naming that owner (another path in this
decomposition or an existing ledger mechanism). Never account a wrapper as
`mandatory`/`out-of-scope` just to satisfy the accounting, and never invent a
spurious sibling mechanism per frame — a `covered-by` row keeps the samples
attached to a tracked mechanism, so the work cannot be silently dropped.

Copy `work_refs` only from the discovery's ledger record. Every profiler root
and related-hotspot ref must occur as `primary` on exactly one path. Use
`overlap` when another hypothesis also applies to the same work; overlap refs
do not replace the required primary accounting. One path's primary refs must
all name the same `hotspot_key` and include that hotspot from every capture;
give each distinct child hotspot its own semantic disposition row. Never invent
or omit refs. The ledger preserves each ref's profiler-measured share and will
reject `below-floor` when any recurrent measurement for that hotspot meets the
campaign floor; `share_pct` is supporting analysis, not a way to override the
captured profile.

Do not tune `share_pct` to influence scheduling: the ledger ranks a mechanism
from the measured shares on its primary refs. If source inspection justifies a
different impact score, supply both `expected_value` in profile percentage
points and `expected_value_unit: "profile-share-equivalent-pct"`, using the
documented eliminability/confidence/cost formula. The unit is mandatory because
untyped scores are not globally comparable.

Mechanism sizing/rejection:

```json
{
  "disposition": "size | reject | park",
  "area_key": "style-recalc/rule-collection",
  "mechanism_key": "style-rule-collection/reuse-selector-filter-result",
  "recommendation": "implement | reject | park",
  "anchor": "...",
  "marginal_share_pct": 0.0,
  "evidenced_ceiling_pct": 0.0,
  "evidence": "one-line summary of counters/oracle",
  "stories": "comma,separated",
  "risks": "one line",
  "dossier": "path"
}
```

For a discovery, write the whole decomposition object verbatim to a JSON
artifact. Mechanism ceiling/evidence feed `advance --to sized`; a rejection's
evidence feeds `campaign.py reject --evidence`.
