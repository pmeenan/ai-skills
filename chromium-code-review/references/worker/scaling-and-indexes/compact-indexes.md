<!-- Generated from ../../scaling-and-indexes.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Scaling And Compact Indexes

Use this contract to scale effort without weakening coverage or overfilling an
agent context. The deterministic helpers produce routing evidence; workers
still make semantic review decisions.

## Compact Indexes

For an opt-in instrumented review, `instrument-command.py` logs code/search
command output bytes that are otherwise invisible to input manifests. These
are emitted-byte proxies rather than provider token counts, but they expose
repeated file/range/query ingestion across workers. Instrumentation observes
the same review; never sample, cap, or omit evidence to improve its metrics.

Run `scripts/build-review-indexes.py` after each producer phase. Index files are
derived views, atomically regenerated from canonical artifacts; they never
replace or amend those artifacts. They live under `indexes/` with a
source-fingerprint manifest.

`indexes/topology.tsv` and `indexes/specialist-priors.tsv` are the phase
handoff for schema-3 reviews. Inventory creates `Complexity graph edges`;
discovery and collection append `Complexity graph delta` rows. The effective
edge state, not total CL size or a checklist-wide default, determines the next
fan-out.

`topology.tsv` keeps `source` as the inventory declaration source and records
the producer of the current effective observation separately as
`effective_source`; its `observations` field retains the complete delta trail.
When inventory has zero edges, each generalist assesses all ten lenses over
the explicit `graph:none` scope, and every likelihood must be low.

The two generalist passes independently populate `specialist-priors.tsv` for
every specialist lens and matching assigned edge partition. The index carries
`lens`, `graph_scope`, `assessor`, `likelihood`, `signals`, `counterevidence`,
`citations`, and `source`. The planner never averages these judgments: a high
from either or medium from both requires a full sweep; one medium requires at
least a bounded probe; two cited lows add no specialist work. Only an explicit
`<PREFIX> hard` changed-contract/boundary trigger overrides the priors. File
type, subsystem proximity, and isolated local constructs are soft amplifiers.

Every candidate must be attached to at least one topology edge before the
collection gate passes. Verification batches follow candidate-bearing
connected components; row count alone never creates a batch. This keeps open
hypotheses as graph obligations until they have a concrete candidate, and
prevents candidate-by-candidate fan-out from recreating the static roster.

Use these deterministic routing thresholds:

- Expand a targeted lens for its `<PREFIX> hard` trigger, likelihood route,
  unresolved/disputed specialist obligation, or candidate requiring that
  lens. A typed boundary, node degree at least 4, caller fanout over 8, trace
  depth over 3, or missing defense is a likelihood amplifier, not an automatic
  lens spawn once both generalists close the slice with cited counterevidence.
  Use those graph thresholds to deepen or shard generalist work when unresolved;
  uncovered surfaces/hunks remain mandatory generalist obligations.
- Collapse work only within one connected component and invariant owner, with
  one procedure, input at most 80% of the worker budget, and at most 8 path
  walks or 40 matrix cells. Never split an ownership/state/persistence/
  cross-sequence chain merely to balance row counts.
- Stop discovery only after both generalists accounted for every inventory
  edge, every edge is `resolved`, `candidate`, or explicitly `unreviewed`, no
  disagreement remains, every candidate has descriptors and typed
  obligations, and exact collection coverage passes. Candidate verification,
  root-cause challenge, reconciliation, and freshness keep their existing
  stricter stop gates.

On retry, assign only unresolved edge IDs and their direct dependency rows,
with the preceding attempt as prestate. Manifests name the compact topology
slice plus selected canonical bodies; they do not repeat the full checklist or
all earlier ledgers.

The builder and validators share one strict table parser. They first apply
valid structured `replace-fields` amendments from `templates.md`, then parse
the effective rows. Narrative amendment text never changes a parsed cell.
Malformed amendments, ambiguous targets, unknown fields, and applicable
identity/path validation errors are fatal: the builder exits nonzero and does
not publish a partial or stale-success index set. Treat the exit status as the
result; diagnostic text printed alongside a zero exit is never an allowed
failure mode.

Every hunk-bearing inventory row uses the exact full repo-relative path from
`profile.json`, followed by a line/range or hunk ID. Basenames, suffix matches,
empty path components, and compact forms such as `H0001 / :14` are invalid;
they cannot be used to bypass ownership validation.

- `indexes/inventory.tsv`: kind, stable scope/surface ID, subject, scope,
  semicolon-delimited tags (including `triggers=...`,
  `root-cause-required=yes|no`, and an intact comma-delimited
  `graph-scope=graph:E-...,E-...` value), citations, and canonical source.
- `indexes/specialist-priors.tsv`: specialist lens, exact graph slice,
  independent generalist assessor, low/medium/high likelihood, cited signals,
  cited counterevidence, and canonical source.
- `indexes/candidates.tsv`: candidate ID, claim/location, origin, severity,
  effective status/amendment evidence, citations, and canonical source.
- `indexes/verdicts.tsv`: verdict ID, candidate ID, verdict, severity/origin,
  citations/evidence excerpt, and canonical source.
- `indexes/reconciliation.tsv`: every canonical row ID, kind, source path,
  effective amendment, candidate/verdict/root-cause links, and disposition
  state.

Planners read an index first, select bounded IDs, and open only the canonical
row bodies needed for judgment. Validators recompute indexes or compare their
source fingerprints before accepting them; stale or incomplete indexes block
the fast path.
