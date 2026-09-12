# Local and SSH execution

Load this reference when choosing or reviewing measurement transport.

Both modes invoke the same on-host runners and share the same machine lock.
Both wrap the runner in a tuner session that applies the CPU policy, keeps
ASLR on for score and profile runs, switches the console to the benchmark X
server's VT when the campaign display is an X display, optionally locks the
GPU clock, and restores everything on exit. Runners receive
`--display/--display-vt/--viewport` from the campaign ledger; they refuse to
start when the display is missing, another VT is active, or the browser
reports a software renderer on an X display.

Local mode never changes the checkout. The requested ref must be current HEAD.
Use `--skip-build` only when the selected browser and driver are already built.
`--characterization` permits development builds such as `out/Default`, uses a
small balanced block minimum, and marks the summary as diagnostic-only.

SSH mode pushes only commit refs, requires a clean tracked remote tree, checks
out detached commits, builds the configured release/perf target, verifies the
entire skill bundle digest, and copies evidence back. It never transfers or
repairs skills automatically.

Nothing is typed into `ssh <host> 'python3 -c ...'`. Inline Python behind
two layers of shell quoting breaks on the first nested quote, and a script
that reaches into `campaign.py`'s internals is a private tool the gate
never sees. A campaign question goes to a `campaign.py` command (`rows`,
`packet`, `candidates`, `explain`, `show`, `next`, the pre-check), forwarded
through the linked pointer or run on the host; anything longer is a shell
file under `scratch/` run with `ssh <host> bash -s < script.sh`, kept for
the report, and it calls those commands (`explain --path all` for every row
of a file, `--path 2,8,12-15` for some). A script that does `import
campaign` or `json.load`s a packet or a scaffold is the private tool this
paragraph forbids, whatever file it lives in, and `campaign.py` and
`redundancy_evidence.py` refuse the import (the skill's own scripts and
tests excepted); a question the commands cannot answer is reported as a
missing command. Editing a children file is `jq` or a heredoc, not
`python3 -c`.

Compress every remote transfer: use `scp -C` or `rsync -z`. Never remove the
shared lock file to recover a job; inspect the holder and terminate the stale
process only when recovery is justified.

Authoritative performance evidence still requires the release/profile build
roles, adequate calibrated repetitions, bare-metal attestation, immutable
payload identity, and all normal campaign gates. Being local does not weaken
those requirements.

## The campaign store lives on the test machine

`ledger.json`, dossiers, reviews, measurements and exports live in
`<remote_src>/.agents/campaigns/<name>` on the measurement host, whether the
agent works there or elsewhere. From another machine, link once:

```bash
python3 .agents/skills/optimize-campaign/scripts/campaign.py link-remote \
  --host linux --remote-src /home/pmeenan/src/chromium/src --name sp3-2026-09
```

After that every `campaign.py` command forwards itself over SSH: local file
arguments (proposals, decompositions, reviews, redundancy packets) are
uploaded to the campaign's `inbox/`, `--out` results come back to the local
path you gave, and a local `remote_measure.py` summary is replaced by the
copy the run already left on the host (`host_summary_path`). The remote
skill tree must match the local digest, so both sides enforce the same
rules. `remote_measure.py --execution ssh` reads its campaign defaults
(display, floor, benchmark, readiness of an opportunity) from the host ledger
through the same pointer, retains each run's manifest next to its evidence
directory on the host, and writes a host-path summary under
`<campaign>/measurements/`. Coding, profile reading and analysis stay local;
nothing about the campaign state does. Running on the test machine itself
needs no pointer: the local ledger is the store.

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

