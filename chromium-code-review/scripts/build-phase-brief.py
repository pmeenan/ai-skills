#!/usr/bin/env python3
import sys
from pathlib import Path
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("review_dir", type=Path)
    parser.add_argument("work_id", type=str)
    parser.add_argument("brief_name", type=str)
    args = parser.parse_args()

    review_dir = args.review_dir.resolve()
    skill_dir = (review_dir / "skill-snapshot").resolve()
    print(f"review_dir: {review_dir}, skill_dir: {skill_dir}", file=sys.stderr)
    
    phase_briefs = (skill_dir / "references/phase-briefs.md").read_text()

    lines = phase_briefs.split('\n')
    start = -1
    end = -1
    for i, line in enumerate(lines):
        if args.brief_name in line:
            start = i
        if start != -1 and line == "```":
            end = i
            break

    if start == -1 or end == -1:
        print(f"Could not find template for {args.brief_name}", file=sys.stderr)
        sys.exit(1)

    template = "\n".join(lines[start:end+1]).split("```text\n")[1].split("```")[0]

    common_header = f"""You are one worker in an orchestrated Chromium CL review. Execute only this
brief. Pin: CL 8192418, patchset 5, revision 09e17456dd74d707d0a90ebb0487bbeac99bd2d9, parent 5f72d48650bcb229f5b898e9e63c31dac699a160.
Review directory: {review_dir}. Read-only worktree: /usr/local/google/home/pmeenan/src/chromium/codereview/worktrees/cl-8192418-ps5. Verify
`git -C /usr/local/google/home/pmeenan/src/chromium/codereview/worktrees/cl-8192418-ps5 rev-parse HEAD` equals 09e17456dd74d707d0a90ebb0487bbeac99bd2d9 before reading code.
Read {review_dir}/directives.md first and honor it.
Verify the rows for work ID {args.work_id} in
{review_dir}/input-manifest.tsv before analysis. This brief and every
preassigned artifact/reference input must have a current byte size and SHA-256
and fit the work-kind budgets; reject stale, missing, globbed, or undeclared
artifact inputs.

If directives.md contains `instrumentation: code-reads-v1`, wrap every
code-evidence read/search command with `python3
{skill_dir}/scripts/instrument-command.py {review_dir} {args.work_id} 1
--cwd <directory> -- <command...>`. The wrapper preserves output and exit
status; it records metadata and emitted-byte counts, never source payloads.
Use the wrapped shell path instead of a harness-native file-read/search tool
for code evidence. For a pipeline, pass its full text as exactly one quoted
argument after `bash -c`; trailing argv is rejected because it can silently
discard the intended path/filter. Never run unscoped `rg --files` in the
Chromium root; use the inventory/caller indexes or an explicit path scope.
Do not wrap tools like `cat` unless their target is the worktree.

Report findings immediately upon discovery. Do not hold or accumulate them
expecting a single bulk write. Output is streaming: process one candidate
fully, write its deliverables, flush, and move to the next. If interrupted,
preserve full rigor, append completed
work, and return `partial — remaining: ...`; never thin the analysis to finish.

Write only to the exact absolute deliverable paths named below. If a write
fails, never redirect output into your own conversation, brain, scratch, or
workspace directory. Retry the named path once, then use the full-payload
fallback for one file or return `blocked — cannot write <exact path>` for a
multi-file deliverable.

Before returning complete or partial, run
`{skill_dir}/scripts/validate-worker-artifact.py {review_dir} <each-row-bearing-deliverable>`.
Fix failures while this attempt still owns a new artifact. For a collected
prestate, append a structured amendment; never exploit a parser omission,
abbreviate a repo-relative path, or rewrite the collected prefix. Return
`needs-repair` with the exact validator error if the contract cannot express a
valid correction.
"""

    template = template.replace('⟨review-dir⟩', str(review_dir))
    template = template.replace('⟨skill-dir⟩', str(skill_dir))

    print(common_header + "\n" + template)

if __name__ == "__main__":
    main()
