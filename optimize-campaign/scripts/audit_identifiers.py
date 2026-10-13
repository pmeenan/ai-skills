#!/usr/bin/env python3
"""Verify that every C++/blink/cc/v8 identifier and ledger mechanism key named
in a staged decomposition's prose exists in the repository source tree or
profile stacks and matches ledger.json.

Usage:
  python3 audit_identifiers.py <campaign_dir> <opp_id> <decomp.json>
"""
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import campaign


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print("usage: audit_identifiers.py <campaign_dir> <opp_id> <decomp.json>", file=sys.stderr)
        return 2
    campaign_dir, opp_id, children = pathlib.Path(args[0]), int(args[1]), pathlib.Path(args[2])
    ledger = campaign.Ledger(campaign_dir).load()
    parent = ledger.opp(opp_id)
    result = campaign.load_decomposition(children)
    profile = ledger.profile(parent["profile_id"])
    story = parent["target_story"]
    relevance_rows = [
        (i, p) for i, p in enumerate(result["paths"], 1)
        if p.get("redundancy_evidence")
    ]
    problems = []
    try:
        campaign.enforce_ledger_key_mentions(result, ledger)
    except campaign.CampaignError as exc:
        problems.append(str(exc))
    try:
        campaign.enforce_row_text_symbols(
            result["paths"],
            relevance_rows,
            profile.get("repository_root"),
            frames=campaign.distinct_frames(campaign.collapsed_stack_files(profile, story)),
        )
    except campaign.CampaignError as exc:
        problems.append(str(exc))
    if problems:
        print(f"FAIL ({len(problems)} identifier problem(s)):")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: all C++ symbols and ledger mechanism keys in {children.name} verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
