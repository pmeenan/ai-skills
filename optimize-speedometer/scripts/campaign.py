#!/usr/bin/env python3
# Copyright 2026 The Chromium Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Campaign ledger, gate enforcement, and STATUS.md generation.

The tech-lead agent mutates campaign state exclusively through this script.
Every mutation rewrites ledger.json and regenerates STATUS.md so the
human-facing status can never drift from the machine state. Subagents never
call this script; they return evidence to the tech lead, who records it.

State machine:

  candidate -> investigating -> sized -> implementing -> review -> landed
                                              ^             |
                                              +-- rework ---+
  Any non-landed state -> rejected | parked (reason required)
  rejected | parked -> candidate (reopen)

Gate requirements are enforced by `advance`:
  -> sized:    --ceiling and --evidence (mechanistic sizing evidence)
  -> review:   --tests (what was run and passed)
  -> landed:   --commit, plus recorded PASS verdicts from both skeptic and
               adversary reviews for the current review round.
"""

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys

STATUSES = (
    "candidate",
    "investigating",
    "sized",
    "implementing",
    "review",
    "landed",
    "rejected",
    "parked",
)
ACTIVE_GATES = ("investigating", "sized", "implementing", "review")
FORWARD_TRANSITIONS = {
    "candidate": {"investigating", "sized"},
    "investigating": {"sized"},
    "sized": {"implementing"},
    "implementing": {"review"},
    "review": {"implementing", "landed"},
}
REVIEW_ROLES = ("skeptic", "adversary")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def agents_dir():
    """Locate the working repo's .agents directory.

    The skills tree may be symlinked into the repo, so resolving __file__
    would escape it. Prefer the repo containing the current directory; fall
    back to the invocation path without resolving symlinks.
    """
    root = find_repo_root(pathlib.Path.cwd())
    if root:
        return pathlib.Path(root) / ".agents"
    return pathlib.Path(os.path.abspath(__file__)).parents[3]


def default_campaign_dir():
    env = os.environ.get("SP3_CAMPAIGN_DIR")
    if env:
        return pathlib.Path(env)
    return agents_dir() / "campaigns" / "current"


def humanize_age(iso_ts):
    try:
        then = datetime.datetime.fromisoformat(iso_ts)
    except (TypeError, ValueError):
        return "?"
    delta = datetime.datetime.now(datetime.timezone.utc) - then
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


class CampaignError(Exception):
    pass


class Ledger:
    def __init__(self, campaign_dir):
        self.dir = pathlib.Path(campaign_dir)
        self.path = self.dir / "ledger.json"
        self.data = None

    def load(self):
        if not self.path.exists():
            raise CampaignError(
                f"No ledger at {self.path}. Run `campaign.py init` first "
                "or pass --dir/SP3_CAMPAIGN_DIR."
            )
        with open(self.path) as f:
            self.data = json.load(f)
        return self

    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=2)
        os.replace(tmp, self.path)
        self.write_status()

    def opp(self, opp_id):
        for opp in self.data["opportunities"]:
            if opp["id"] == opp_id:
                return opp
        raise CampaignError(f"Unknown opportunity id {opp_id}")

    def record(self, opp, event):
        opp.setdefault("history", []).append({"ts": utc_now(), "event": event})

    def landed(self):
        return [o for o in self.data["opportunities"] if o["status"] == "landed"]

    def priority(self, opp):
        value = opp.get("expected_value")
        return value if value is not None else opp.get("share_pct", 0.0)

    def next_candidates(self, count):
        pool = [o for o in self.data["opportunities"] if o["status"] == "candidate"]
        pool.sort(key=self.priority, reverse=True)
        return pool[:count]

    # ---------------- STATUS.md ----------------

    def write_status(self):
        cfg = self.data["config"]
        opps = self.data["opportunities"]
        checkpoints = self.data.get("checkpoints", [])
        landed = self.landed()
        remaining = sum(
            o.get("share_pct", 0.0)
            for o in opps
            if o["status"] in ("candidate", "investigating", "sized")
        )
        lines = []
        lines.append(
            f"# SP3 Campaign: {cfg['name']} — branch `{cfg['branch']}`"
        )
        lines.append("")
        header = (
            f"**Landed: {len(landed)}/{cfg['target_landed']}** · "
            f"Flag: `{cfg['feature']}` · "
            f"Remaining frontier above floor: {remaining:.2f}% share"
        )
        if checkpoints:
            cp = checkpoints[-1]
            header += (
                f" · Last checkpoint (after {cp['landed_count']} landed): "
                f"{cp['delta_pct']:+.2f}% "
                f"[{cp['ci'][0]:+.2f}%, {cp['ci'][1]:+.2f}%]"
            )
        lines.append(header)
        lines.append("")
        lines.append(f"_Updated: {utc_now()} (generated from ledger.json — do not edit)_")

        in_flight = [o for o in opps if o["status"] in ACTIVE_GATES]
        lines.append("")
        lines.append("## In flight")
        if in_flight:
            lines.append("| Gate | Opp | Anchor | Share | Age | Note |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            order = {s: i for i, s in enumerate(ACTIVE_GATES)}
            for o in sorted(in_flight, key=lambda o: order[o["status"]], reverse=True):
                note = self._flight_note(o)
                lines.append(
                    f"| {o['status']} | #{o['id']:03d} | {o['anchor']} | "
                    f"{o.get('share_pct', 0.0):.2f}% | "
                    f"{humanize_age(o.get('status_since'))} | {note} |"
                )
        else:
            lines.append("_(nothing in flight)_")

        lines.append("")
        lines.append("## Next up (by expected value)")
        nxt = self.next_candidates(5)
        if nxt:
            for i, o in enumerate(nxt, 1):
                lines.append(
                    f"{i}. #{o['id']:03d} {o['anchor']} "
                    f"({o.get('share_pct', 0.0):.2f}% share"
                    + (
                        f", EV {o['expected_value']:.3f}"
                        if o.get("expected_value") is not None
                        else ""
                    )
                    + ")"
                )
        else:
            lines.append("_(candidate pool empty — re-profile or stop)_")

        lines.append("")
        lines.append("## Recently landed")
        if landed:
            for o in sorted(landed, key=lambda o: o.get("status_since", ""), reverse=True)[:8]:
                commit = (o.get("commit") or "")[:12]
                lines.append(
                    f"- #{o['id']:03d} `{commit}` {o['anchor']} — "
                    f"{o.get('landed_note') or o.get('evidence') or ''}"
                )
        else:
            lines.append("_(none yet)_")

        lines.append("")
        lines.append("## Checkpoints (cumulative flag on/off, full suite)")
        if checkpoints:
            lines.append("| After # landed | Delta | 95% CI | Date | Notes |")
            lines.append("| --- | --- | --- | --- | --- |")
            for cp in checkpoints:
                lines.append(
                    f"| {cp['landed_count']} | {cp['delta_pct']:+.2f}% | "
                    f"[{cp['ci'][0]:+.2f}%, {cp['ci'][1]:+.2f}%] | "
                    f"{cp['ts'][:10]} | {cp.get('notes') or ''} |"
                )
        else:
            lines.append("_(no checkpoints yet)_")

        parked = [o for o in opps if o["status"] in ("parked", "rejected")]
        lines.append("")
        lines.append("## Parked / rejected")
        if parked:
            for o in parked:
                lines.append(
                    f"- #{o['id']:03d} [{o['status']}] {o['anchor']} — "
                    f"{o.get('reason') or ''}"
                )
        else:
            lines.append("_(none)_")
        lines.append("")

        with open(self.dir / "STATUS.md", "w") as f:
            f.write("\n".join(lines))

    def _flight_note(self, opp):
        bits = []
        if opp["status"] == "review":
            for role in REVIEW_ROLES:
                verdict = opp.get("reviews", {}).get(role, {}).get("verdict")
                bits.append(f"{role}: {verdict or 'pending'}")
        if opp.get("rework_rounds"):
            bits.append(f"rework round {opp['rework_rounds']}")
        if opp.get("squeeze_rounds"):
            bits.append(f"squeeze round {opp['squeeze_rounds']}")
        if not bits and opp.get("notes"):
            bits.append(opp["notes"][-1])
        return "; ".join(bits)


def find_repo_root(start):
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def verify_commit(repo_root, sha):
    if not repo_root:
        print("warning: not in a git repo; skipping commit verification", file=sys.stderr)
        return
    result = subprocess.run(
        ["git", "-C", repo_root, "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise CampaignError(f"Commit {sha} does not exist in {repo_root}")


def git_output(repo_root, *args):
    return subprocess.run(
        ["git", "-C", repo_root] + list(args),
        capture_output=True, text=True, check=True,
    ).stdout


def capture_review_base(opp, repo_root, allow_unstaged=False):
    """Record HEAD and the staged tree hash when entering review, so landing
    can prove the reviewed content (including binaries, modes, renames, and
    deletions) is exactly what got committed. The index must be
    authoritative: unstaged or untracked changes mean the reviewers and the
    landing gate would see only part of the candidate, so they are a hard
    error unless explicitly overridden."""
    if not repo_root:
        print("warning: not in a git repo; review base not captured", file=sys.stderr)
        return
    unstaged = [
        line
        for line in git_output(repo_root, "status", "--porcelain").splitlines()
        if len(line) > 1 and line[1] != " "
    ]
    if unstaged:
        message = (
            "unstaged/untracked changes are NOT part of the reviewed tree "
            "(`git add -A` first): " + ", ".join(u[3:] for u in unstaged[:5])
        )
        if not allow_unstaged:
            raise CampaignError(
                message + ". Pass --allow-unstaged only if they are "
                "deliberately out of scope."
            )
        print(f"warning: {message}", file=sys.stderr)
    opp["review_base"] = git_output(repo_root, "rev-parse", "HEAD").strip()
    opp["review_tree"] = git_output(repo_root, "write-tree").strip()


def verify_landed_commit(opp, repo_root, sha, skip_verification, branch):
    verify_commit(repo_root, sha)
    if skip_verification:
        print("warning: review verification skipped by flag", file=sys.stderr)
        return
    if not repo_root or not opp.get("review_base"):
        print("warning: no review base recorded; landing without verification",
              file=sys.stderr)
        return
    full_sha = git_output(repo_root, "rev-parse", f"{sha}^{{commit}}").strip()
    head = git_output(repo_root, "rev-parse", "HEAD").strip()
    if head != full_sha:
        raise CampaignError(
            f"Commit {sha} is not the current HEAD ({head[:12]}); a landed "
            "commit must be the checked-out tip, not a side or dangling "
            "commit. Re-review, or pass --skip-review-verification."
        )
    current_branch = git_output(repo_root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch and current_branch != branch:
        raise CampaignError(
            f"HEAD is on branch {current_branch!r}, not the campaign branch "
            f"{branch!r}. Check out the campaign branch, or pass "
            "--skip-review-verification."
        )
    parent = git_output(repo_root, "rev-parse", f"{sha}^").strip()
    if parent != opp["review_base"]:
        raise CampaignError(
            f"Commit {sha} is not built directly on the reviewed base "
            f"{opp['review_base'][:12]} (parent is {parent[:12]}). Re-review, "
            "or pass --skip-review-verification if this is intentional."
        )
    landed_tree = git_output(repo_root, "rev-parse", f"{sha}^{{tree}}").strip()
    if landed_tree != opp.get("review_tree"):
        raise CampaignError(
            f"Commit {sha} does not match the tree that was reviewed "
            "(content changed after review). Re-review, or pass "
            "--skip-review-verification if this is intentional."
        )


# ---------------- commands ----------------


def cmd_init(args):
    campaign_dir = pathlib.Path(args.dir) if args.dir else None
    if campaign_dir is None:
        campaigns_root = agents_dir() / "campaigns"
        campaign_dir = campaigns_root / args.name
        campaign_dir.mkdir(parents=True, exist_ok=True)
        current = campaigns_root / "current"
        if current.is_symlink() or current.exists():
            current.unlink()
        current.symlink_to(args.name)
    ledger = Ledger(campaign_dir)
    if ledger.path.exists() and not args.force:
        raise CampaignError(f"Ledger already exists at {ledger.path} (use --force)")
    ledger.data = {
        "config": {
            "name": args.name,
            "branch": args.branch,
            "target_landed": args.target,
            "share_floor_pct": args.share_floor,
            "feature": args.feature,
            "remote_host": args.remote_host,
            "remote_src": args.remote_src,
            "created": utc_now(),
        },
        "next_id": 1,
        "opportunities": [],
        "checkpoints": [],
    }
    (ledger.dir / "dossiers").mkdir(parents=True, exist_ok=True)
    (ledger.dir / "reviews").mkdir(parents=True, exist_ok=True)
    ledger.save()
    print(f"Initialized campaign at {ledger.dir}")
    return 0


def cmd_add(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    floor = ledger.data["config"]["share_floor_pct"]
    if args.share < floor:
        print(
            f"warning: share {args.share}% is below the campaign floor {floor}%",
            file=sys.stderr,
        )
    opp = {
        "id": ledger.data["next_id"],
        "anchor": args.anchor,
        "share_pct": args.share,
        "stories": args.stories,
        "dossier": args.dossier,
        "expected_value": args.expected_value,
        "status": "candidate",
        "status_since": utc_now(),
        "ceiling_pct": None,
        "evidence": None,
        "tests": None,
        "commit": None,
        "rework_rounds": 0,
        "squeeze_rounds": 0,
        "reviews": {},
        "reason": None,
        "notes": [args.notes] if args.notes else [],
        "history": [],
    }
    ledger.record(opp, "added as candidate")
    ledger.data["next_id"] += 1
    ledger.data["opportunities"].append(opp)
    ledger.save()
    print(f"Added opportunity #{opp['id']:03d}: {args.anchor}")
    return 0


def cmd_advance(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    src, dst = opp["status"], args.to
    if dst not in FORWARD_TRANSITIONS.get(src, set()):
        raise CampaignError(
            f"Illegal transition {src} -> {dst} for #{opp['id']:03d}. "
            f"Allowed from {src}: {sorted(FORWARD_TRANSITIONS.get(src, set()))}"
        )
    if dst == "sized":
        if args.ceiling is None or not args.evidence:
            raise CampaignError(
                "-> sized requires --ceiling <pct> and --evidence "
                "(instrumentation/oracle sizing evidence)"
            )
        opp["ceiling_pct"] = args.ceiling
        opp["evidence"] = args.evidence
    if dst == "review":
        if not args.tests:
            raise CampaignError(
                "-> review requires --tests describing what was run and passed"
            )
        opp["tests"] = args.tests
        opp["reviews"] = {}
        capture_review_base(
            opp, find_repo_root(pathlib.Path.cwd()), args.allow_unstaged
        )
    if src == "review" and dst == "implementing":
        if opp.get("rework_rounds", 0) >= 2 and not args.override_rework_limit:
            raise CampaignError(
                f"#{opp['id']:03d} has used both rework rounds; reject it "
                "(`campaign.py reject`) or pass --override-rework-limit with "
                "a note explaining why a third round is justified"
            )
        opp["rework_rounds"] = opp.get("rework_rounds", 0) + 1
        opp["reviews"] = {}
    if dst == "landed":
        if not args.commit:
            raise CampaignError("-> landed requires --commit <sha>")
        for role in REVIEW_ROLES:
            verdict = opp.get("reviews", {}).get(role, {}).get("verdict")
            if verdict != "PASS":
                raise CampaignError(
                    f"-> landed blocked: {role} verdict is {verdict or 'missing'} "
                    f"(record with `campaign.py review --opp {opp['id']} "
                    f"--role {role} --verdict PASS`)"
                )
        verify_landed_commit(
            opp, find_repo_root(pathlib.Path.cwd()), args.commit,
            args.skip_review_verification,
            ledger.data["config"].get("branch"),
        )
        opp["commit"] = args.commit
        if args.notes:
            opp["landed_note"] = args.notes
    opp["status"] = dst
    opp["status_since"] = utc_now()
    detail = args.notes or args.evidence or args.tests or ""
    ledger.record(opp, f"{src} -> {dst}" + (f": {detail}" if detail else ""))
    ledger.save()
    print(f"#{opp['id']:03d} {src} -> {dst}")
    return 0


def cmd_squeeze(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] != "implementing":
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}; squeeze rounds are recorded "
            "while implementing"
        )
    opp["squeeze_rounds"] = opp.get("squeeze_rounds", 0) + 1
    detail = f": {args.note}" if args.note else ""
    ledger.record(opp, f"squeeze round {opp['squeeze_rounds']}{detail}")
    ledger.save()
    print(f"#{opp['id']:03d} squeeze round {opp['squeeze_rounds']}")
    return 0


def cmd_review(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] != "review":
        raise CampaignError(
            f"#{opp['id']:03d} is {opp['status']}, not in review; "
            "advance it to review before recording verdicts"
        )
    opp.setdefault("reviews", {})[args.role] = {
        "verdict": args.verdict,
        "notes": args.notes,
        "report": args.report,
        "ts": utc_now(),
    }
    ledger.record(opp, f"{args.role} review: {args.verdict}")
    ledger.save()
    print(f"#{opp['id']:03d} {args.role}: {args.verdict}")
    return 0


def _close(args, status):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] == "landed":
        raise CampaignError(f"#{opp['id']:03d} already landed; cannot {status[:-2]}")
    opp["status"] = status
    opp["status_since"] = utc_now()
    opp["reason"] = args.reason
    ledger.record(opp, f"{status}: {args.reason}")
    ledger.save()
    print(f"#{opp['id']:03d} {status}: {args.reason}")
    return 0


def cmd_reject(args):
    return _close(args, "rejected")


def cmd_park(args):
    return _close(args, "parked")


def cmd_reopen(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    if opp["status"] not in ("rejected", "parked"):
        raise CampaignError(f"#{opp['id']:03d} is {opp['status']}; reopen applies to rejected/parked")
    opp["status"] = "candidate"
    opp["status_since"] = utc_now()
    opp["reason"] = None
    ledger.record(opp, "reopened as candidate")
    ledger.save()
    print(f"#{opp['id']:03d} reopened")
    return 0


def cmd_note(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    opp = ledger.opp(args.opp)
    opp.setdefault("notes", []).append(args.text)
    ledger.record(opp, f"note: {args.text}")
    ledger.save()
    return 0


def cmd_checkpoint(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    ledger.data.setdefault("checkpoints", []).append(
        {
            "ts": utc_now(),
            "landed_count": len(ledger.landed()),
            "delta_pct": args.delta,
            "ci": [args.ci_low, args.ci_high],
            "manifest": args.manifest,
            "sha": args.sha,
            "notes": args.notes,
        }
    )
    ledger.save()
    print(f"Recorded checkpoint after {len(ledger.landed())} landed: {args.delta:+.2f}%")
    return 0


def cmd_status(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    ledger.write_status()
    status_path = ledger.dir / "STATUS.md"
    print(status_path)
    if args.print:
        with open(status_path) as f:
            print(f.read())
    return 0


def cmd_show(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    if args.opp is not None:
        print(json.dumps(ledger.opp(args.opp), indent=2))
    else:
        print(json.dumps(ledger.data, indent=2))
    return 0


def cmd_next(args):
    ledger = Ledger(args.dir or default_campaign_dir()).load()
    for o in ledger.next_candidates(args.count):
        print(
            f"#{o['id']:03d} {o['anchor']} share={o.get('share_pct', 0.0):.2f}% "
            f"ev={o.get('expected_value')}"
        )
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dir",
        help="Campaign directory (default: $SP3_CAMPAIGN_DIR or .agents/campaigns/current)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="Create a new campaign ledger")
    p.add_argument("--name", required=True)
    p.add_argument("--branch", default="speedometer")
    p.add_argument("--target", type=int, default=20, help="Target landed count")
    p.add_argument(
        "--share-floor",
        type=float,
        default=0.1,
        help="Minimum marginal profile share (%%) worth attempting",
    )
    p.add_argument("--feature", default="Speedometer3Optimizations")
    p.add_argument("--remote-host", default="linux")
    p.add_argument("--remote-src", default=None)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("add", help="Add a candidate opportunity")
    p.add_argument("--anchor", required=True, help="Anchor symbol/subtree description")
    p.add_argument("--share", type=float, required=True, help="Marginal profile share (%%)")
    p.add_argument("--stories", default=None, help="Comma-separated stories where samples concentrate")
    p.add_argument("--dossier", default=None, help="Path to the dossier file")
    p.add_argument("--expected-value", type=float, default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("advance", help="Move an opportunity through a gate")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--to", required=True, choices=[s for s in STATUSES if s not in ("candidate", "rejected", "parked")])
    p.add_argument("--ceiling", type=float, default=None, help="Evidenced eliminable share (%%)")
    p.add_argument("--evidence", default=None)
    p.add_argument("--tests", default=None)
    p.add_argument("--commit", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--override-rework-limit", action="store_true",
                   help="Allow a third rework round (requires justification in --notes)")
    p.add_argument("--skip-review-verification", action="store_true",
                   help="Land without verifying the commit matches the reviewed diff")
    p.add_argument("--allow-unstaged", action="store_true",
                   help="Enter review despite unstaged/untracked changes "
                   "(they are excluded from the reviewed tree)")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("squeeze", help="Record one squeeze-loop refinement round")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--note", default=None)
    p.set_defaults(func=cmd_squeeze)

    p = sub.add_parser("review", help="Record a review verdict")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--role", required=True, choices=REVIEW_ROLES)
    p.add_argument("--verdict", required=True, choices=("PASS", "FAIL"))
    p.add_argument("--notes", default=None)
    p.add_argument("--report", default=None, help="Path to the full review report")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("reject", help="Reject an opportunity with a reason")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("park", help="Defer an opportunity with a reason")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_park)

    p = sub.add_parser("reopen", help="Return a rejected/parked opportunity to the pool")
    p.add_argument("--opp", type=int, required=True)
    p.set_defaults(func=cmd_reopen)

    p = sub.add_parser("note", help="Append a note to an opportunity")
    p.add_argument("--opp", type=int, required=True)
    p.add_argument("--text", required=True)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("checkpoint", help="Record a cumulative flag on/off measurement")
    p.add_argument("--delta", type=float, required=True, help="Suite geometric delta (%%)")
    p.add_argument("--ci-low", type=float, required=True)
    p.add_argument("--ci-high", type=float, required=True)
    p.add_argument("--manifest", default=None)
    p.add_argument("--sha", default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cmd_checkpoint)

    p = sub.add_parser("status", help="Regenerate STATUS.md and print its path")
    p.add_argument("--print", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("show", help="Dump ledger or one opportunity as JSON")
    p.add_argument("--opp", type=int, default=None)
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("next", help="Print the next candidates by priority")
    p.add_argument("--count", type=int, default=3)
    p.set_defaults(func=cmd_next)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CampaignError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
