# Local and SSH execution

Load this reference when choosing or reviewing measurement transport.

Both modes invoke the same on-host runners and share the same machine lock.

Local mode never changes the checkout. The requested ref must be current HEAD.
Use `--skip-build` only when the selected browser and driver are already built.
`--characterization` permits development builds such as `out/Default`, uses a
small balanced block minimum, and marks the summary as diagnostic-only.

SSH mode pushes only commit refs, requires a clean tracked remote tree, checks
out detached commits, builds the configured release/perf target, verifies the
entire skill bundle digest, and copies evidence back. It never transfers or
repairs skills automatically.

Compress every remote transfer: use `scp -C` or `rsync -z`. Never remove the
shared lock file to recover a job; inspect the holder and terminate the stale
process only when recovery is justified.

Authoritative performance evidence still requires the release/profile build
roles, adequate calibrated repetitions, bare-metal attestation, immutable
payload identity, and all normal campaign gates. Being local does not weaken
those requirements.

## Pinpoint fleet execution (Stage 2 Validation)

For candidate validation across production hardware fleets, Pinpoint tryjobs
complement local/SSH execution:
- **Local / SSH (Stage 1):** Fast-turnaround cycle profiling, PMU counter
  measurement (`perf stat`), in-situ mechanism sizing, and candidate isolation.
- **Pinpoint (Stage 2):** Massive parallelism across the production fleet
  (`mac-m1_mini_2020-perf-pgo`, `linux-perf`), executing on official PGO builds
  with tight thermal bounds.
- **CL Lifecycle:** Candidate try CLs need only the isolated code diff. Their
  Gerrit URLs are bound to the measurement summary. If a candidate is rejected
  or regresses, the try CL must be promptly abandoned via `pinpoint_measure.py abandon`.

