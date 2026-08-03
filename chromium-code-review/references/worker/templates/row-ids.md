<!-- Generated from ../../templates.md by build_worker_references.py; do not edit. Canonical text lives in the source file. -->

# Templates And Artifact Shapes

Every artifact this skill produces has a required shape, shown here filled
in. Copy the shape and replace the values; do not invent formats. The
examples use a fictional CL (9999999, patchset 3) touching
`net/streams/delay_buffer.cc` — the values are illustrative, the columns and
fields are normative. Never copy an example's file paths, findings, or
verdicts into a real review.

## Row IDs

Rows are identified as `⟨THREAD⟩-⟨n⟩`, assigned by the thread that creates
the row, numbered from 1 in creation order. A row keeps its ID through
verification, reconciliation, and the final review; the orchestrator never
renumbers or re-keys another thread's rows.

| Roster entry / source | ID prefix |
| --- | --- |
| Desk-Check Simulation + Arithmetic Drills | DCS |
| Data Lineage | DL |
| Callback And Task Lifetime | CTL |
| Container And View Invalidation | CVI |
| Error-Path Walk | EPW |
| State × Method Matrix | SMM |
| Mode × Host-Capability Matrix | MHM |
| Teardown Order | TDO |
| Field Propagation Matrix | FPM |
| Associative Container Semantics | ACS |
| Transformation Equivalence And Residue | TER |
| Mechanical Leads | ML |
| Per-Surface Invariants | PSI |
| Async And Lifecycle | AL |
| State/Persistence/Cache | SPC |
| Integration And Feature Control | IFC |
| Security And Trust Boundaries | STB |
| Contracts And API Shape | CAS |
| Tests As Specifications | TAS |
| Changed-Lines Polish | CLP |
| Threading And Synchronization | TSY |
| Ownership And Blink Lifecycle | OBL |
| Mojo IPC Authorization And Sandbox | MIS |
| Performance And Resource Scaling | PRS |
| Platform And Language Semantics | PLS |
| Build API And Generated Assets | BAG |
| Privacy And Telemetry | PAT |
| Accessibility And Internationalization | AXI |
| Network Semantics | NET |
| Fuzzing And Test Strategy | FTS |
| Holistic-and-polish thread | HOL |
| Prior-review reconciliation (Pass 2) | PR |
| Collection-audit rows (per-file floor) | ORC |
| Verification skeptic verdicts | V⟨batch⟩ (e.g. V001, V002) |
| Root-cause challenger rows | RC⟨batch⟩ (e.g. RC001, RC002) |
| Reopened candidates | R⟨round⟩-RC⟨batch⟩ (e.g. R1-RC001-1) |
| Synthesis challenge rows | CH⟨batch⟩ (e.g. CH001) |

A sharded roster entry appends its shard number to the prefix: shard 2 of
Error-Path Walk is thread `EPW2`, rows `EPW2-⟨n⟩`, ledger file
`ledger/EPW2.md`, and its own row in `plan.md`. Skeptic verdicts are keyed
by batch: verification batch `V001` writes `verification/V001.md` with IDs
`V001-⟨n⟩`, so concurrent skeptics never collide on a file or an ID.

Batch identifiers are namespaced and zero-padded. Discovery scheduling batches
are `D01`, `D02`, ...; verification batches are `V001`, `V002`, ...;
root-cause batches are `RC001`, `RC002`, ...; and challenge shards are
`CH001`, `CH002`, .... Never
write an unqualified "batch 1": it is ambiguous after handoff.
