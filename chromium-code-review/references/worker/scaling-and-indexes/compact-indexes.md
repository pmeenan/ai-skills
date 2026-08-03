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
  tags (including `root-cause-required=yes|no`), citations, and canonical source.
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
