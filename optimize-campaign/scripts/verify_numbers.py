#!/usr/bin/env python3
"""Verify that every number and file:line citation in a staged decomposition's
prose comes from the packets, frontier artifacts, and source tree it binds.

Usage:
  python3 verify_numbers.py <campaign_dir> <opp_id> <decomp.json>
"""
import json
import pathlib
import sys

SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import campaign


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3:
        print("usage: verify_numbers.py <campaign_dir> <opp_id> <decomp.json>", file=sys.stderr)
        return 2
    campaign_dir, opp_id, children = pathlib.Path(args[0]), int(args[1]), pathlib.Path(args[2])
    ledger = campaign.Ledger(campaign_dir).load()
    parent = ledger.opp(opp_id)
    ledger.data["config"] = campaign.area_config(ledger.data["config"], parent)
    result = campaign.load_decomposition(children)
    profile = ledger.profile(parent["profile_id"])
    story = parent["target_story"]
    floor = ledger.data["config"]["share_floor_pct"]
    measured = {
        tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")): r.get("measured_share_pct", 0.0)
        for r in parent["expected_work_refs"]
    }
    shares = {}
    for i, p in enumerate(result["paths"], 1):
        prim = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")) for r in p["work_refs"] if r["accounting"] == "primary"}
        if prim:
            shares[i] = min(measured[k] for k in prim)
    relevance_rows = [
        (i, p) for i, p in enumerate(result["paths"], 1)
        if p.get("redundancy_evidence")
    ]
    problems = []
    campaign.run_rule_all(
        problems,
        lambda w: campaign.enforce_row_text_numbers(
            w, [(i, p) for i, p in relevance_rows if w[i - 1].get("disposition") != campaign.RULE_SKIPPED],
            shares, ledger.data["config"], floor, story, campaign_dir,
        ),
        result["paths"],
    )
    text_sources = campaign.row_text_sources(
        ledger, parent, profile, result, shares, ledger.data["config"], floor, campaign_dir,
    )
    campaign.run_rule_all(
        problems,
        lambda w: campaign.enforce_row_text_sources(w, text_sources),
        result["paths"],
        limit=len(result["paths"]) + 2,
        neutralize_mechanisms=True,
    )
    if problems:
        print(f"FAIL ({len(problems)} prose number/citation problem(s)):")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: all prose numbers and file:line citations in {children.name} verified against bound artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
