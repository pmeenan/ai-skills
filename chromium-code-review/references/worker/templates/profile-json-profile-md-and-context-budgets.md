<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## profile.json, profile.md, And Context Budgets

Run `scripts/profile-review.py` after pinning. The complete classification and
budget rules live in `references/scaling-and-indexes.md`; this is the normative
shape excerpt. `profile.md` renders the same fields for workers and humans.

```json
{
  "schema_version": 2,
  "effort": "high-risk",
  "context_fast_path_eligible": false,
  "effort_reasons": ["risk signal: async_or_lifecycle"],
  "micro_eligibility": {"eligible": false, "proof": [], "failed": []},
  "pin": {"revision_sha": "4f2a09c1...", "parent_sha": "8b1d77e..."},
  "counts": {"files": 3, "changed_lines": 418, "hunks": 19,
             "approximate_changed_surfaces": 19,
             "max_changed_lines_in_one_file": 241},
  "risk_signals": {"async_or_lifecycle": 3, "performance_or_memory": 4},
  "specialist_triggers": [
    {"prefix": "TSY", "roster_entry": "Threading And Synchronization",
     "match_count": 2},
    {"prefix": "NET", "roster_entry": "Network Semantics",
     "match_count": 4}
  ],
  "prior_context": {"unresolved_threads": 1, "malformed_entries": 0,
                    "external_context": {"available": true, "count": 1,
                                         "references": ["Bug: 1234567"]}},
  "context_budget": {
    "source": "fallback",
    "reported_context_tokens": null,
    "input_fraction": 0.35,
    "worker_input_budget_bytes": 131072,
    "candidate_packet_budget_bytes": 16384,
    "evidence_card_budget_bytes": 32768
  }
}
```

`specialist_triggers` is deterministic routing evidence, not a complete
semantic trigger inventory. A missing profile hit never proves a roster row
N/A; Inventory must apply the full rules in `inventory-and-planning.md`.

`context_budget` counts every required brief/header/reference artifact. Use
35% of known capacity (conservatively four bytes per token) or the 128 KiB
fallback. The derived packet/card values partition that ceiling; exceeding any
value requires sharding or continuation, never truncation. Profile class
changes topology only and never removes roster or gate obligations.
