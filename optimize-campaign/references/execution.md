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
