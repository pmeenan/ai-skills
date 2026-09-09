#!/usr/bin/env python3
"""Host-side pre-check for a decomposition review request: runs the same
row rules the gate runs (measured dispositions, covered-by sample identity,
candidate packet bounds by hypothesis, packet relevance, build consistency,
sites named, own counters, packet time coverage, row-text numbers, symbols
in the tree, large rows, below-floor per capture, covered-by probe identity,
nearest-probe) and prints the rows a reviewer has to open. One problem per
rule: the gate stops at the first row a rule refuses, so fix and rerun.

Usage: precheck_decomposition.py <campaign dir> <opp id> <children.json>

This file lives in the skill tree, which the campaign binds by digest; a
copy edited elsewhere is not the pre-check. Nothing in it may replace a
rule or a reducer function: `decompose` runs the same code and is the
authority."""
import json, pathlib, sys
SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import campaign, redundancy_evidence


def main(campaign_dir, opp_id, children):
    ledger = campaign.Ledger(campaign_dir).load()
    parent = ledger.opp(int(opp_id))
    result = campaign.load_decomposition(children)
    profile = ledger.profile(parent["profile_id"])
    measured = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")): r.get("measured_share_pct", 0.0)
                for r in parent["expected_work_refs"]}
    shares = {}
    for i, p in enumerate(result["paths"], 1):
        prim = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")) for r in p["work_refs"] if r["accounting"] == "primary"}
        if prim:
            shares[i] = min(measured[k] for k in prim)
    story = parent["target_story"]
    floor = ledger.data["config"]["share_floor_pct"]
    problems = []
    story_floor = max(campaign.story_floor_pct(ledger.data["config"], story)[0], floor)
    for i, p in enumerate(result["paths"], 1):
        if p["disposition"] in ("novel", "algorithmic"):
            try: campaign.require_existing_mechanism(p, i)
            except campaign.CampaignError as e: problems.append(str(e))
        if p["disposition"] == "algorithmic":
            try:
                frac = p.get("estimated_avoidable_fraction")
                campaign.bind_cost_evidence(p, story, float(frac), campaign_dir)
                cs = p["cost_summary"]
                print(f"row {i} algorithmic {p['anchor'][:60]} share={shares.get(i,0):.2f} frac={frac} avoided={cs['avoided_fraction_of_row']:.4f} of row via {cs['avoided_frames']}")
            except (campaign.CampaignError, TypeError, ValueError) as e: problems.append(str(e))
        if p["disposition"] in ("novel", "known"):
            frac = p.get("estimated_avoidable_fraction")
            try:
                if frac is None:
                    raise campaign.CampaignError(f"Path {i} ({p['anchor'][:60]!r}) has no estimated_avoidable_fraction")
                campaign.bind_redundancy_evidence(p, story, float(frac), campaign_dir)
                summ = p["redundancy_summary"]
                print(f"row {i} {p['disposition']} {p['anchor'][:60]} share={shares.get(i,0):.2f} frac={frac} hypothesis={summ['packet_hypothesis']} applicable={summ['applicable_fraction']:.4f}/{summ['applicable_time_fraction']:.4f}(time) repeat={summ['repeat_fraction']:.4f}/{summ['repeat_time_fraction']:.4f}(time) supported={summ['supported_avoidable_fraction']:.4f} probe={summ.get('probe_symbol')}")
            except campaign.CampaignError as e: problems.append(str(e))
    bound = set()
    try:
        bound = campaign.enforce_measured_dispositions(result["paths"], shares, ledger.data["config"], floor, story, campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    unbound = [i for i, p in enumerate(result["paths"], 1)
               if p["disposition"] in ("mandatory", "no-qualifying-mechanism")
               and shares.get(i, 0.0) >= story_floor
               and not p.get("redundancy_evidence") and p.get("wrapper_of") is None]
    if unbound:
        problems.append(f"{len(unbound)} mandatory/no-qualifying rows at/above the {story_floor:.3f}% floor bind no packet and no wrapper_of: rows {unbound[:40]}{' ...' if len(unbound) > 40 else ''}")
    # Every row that binds a packet, whatever the measured-disposition rule
    # said: the coverage table and the build check are most useful when
    # that rule has already refused a row.
    relevance_rows = [(i, p) for i, p in enumerate(result["paths"], 1)
                      if i in bound or (p["disposition"] in ("novel", "known", "mandatory", "no-qualifying-mechanism")
                                        and p.get("redundancy_evidence"))]
    try:
        campaign.enforce_packet_relevance(result["paths"], relevance_rows, profile, story, campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    packets = campaign.bound_packets(result["paths"], relevance_rows, campaign_dir)
    print("\nbound packets:")
    for path, (pk, idx) in sorted(packets.items()):
        print(f"  {path:48} build={str(pk.get('build_id'))[:12]:12} timing={pk.get('timing')} nested={pk.get('nested_calls_fraction')} rows={len(idx)}")
    try:
        campaign.enforce_build_consistency(result["paths"], campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    site_symbols = None
    try:
        site_symbols = campaign.enforce_sites_named(result["paths"], relevance_rows, story, campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        campaign.enforce_own_counters(result["paths"], shares, ledger.data["config"], floor, story, campaign_dir, relevance_rows, site_symbols)
        own = [(i, p["own_counters"]) for i, p in enumerate(result["paths"], 1) if p.get("own_counters")]
        if own: print("\nrows closed on their own counters:", own[:20])
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        rows_cov, reference = campaign.packet_time_coverage(result["paths"], relevance_rows, profile, story, campaign_dir)
        if rows_cov:
            print("\npacket time coverage (ms per repetition against the probed function's profile share):")
            print(campaign.format_time_coverage(rows_cov, reference))
        campaign.enforce_packet_time_coverage(result["paths"], relevance_rows, profile, story, campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        campaign.enforce_row_text_numbers(result["paths"], relevance_rows, shares, ledger.data["config"], floor, story, campaign_dir)
    except campaign.CampaignError as e: problems.append(str(e))
    measured_rows = {i for i, p in enumerate(result["paths"], 1)
                     if p["disposition"] in ("mandatory", "no-qualifying-mechanism")
                     and shares.get(i, 0.0) >= story_floor and p.get("redundancy_evidence")}
    try:
        campaign.enforce_mandatory_invariants(result["paths"], measured_rows)
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        campaign.enforce_row_text_distinct(result["paths"])
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        campaign.enforce_row_text_symbols(result["paths"], relevance_rows, profile.get("repository_root"))
    except campaign.CampaignError as e: problems.append(str(e))
    # decompose judges below-floor against every capture's share (any >= floor refuses)
    max_shares = {}
    for i, p in enumerate(result["paths"], 1):
        prim = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")) for r in p["work_refs"] if r["accounting"] == "primary"}
        if prim: max_shares[i] = max(measured[k] for k in prim)
    wrong = [(i, round(max_shares[i], 3)) for i, p in enumerate(result["paths"], 1)
             if p["disposition"] == "below-floor" and max_shares.get(i, 0.0) >= story_floor]
    if wrong:
        problems.append(f"{len(wrong)} below-floor row(s) whose share in some capture is at/above the {story_floor:.3f}% floor (decompose refuses these; bind the nearest packet as mandatory): {wrong[:20]}")
    try: campaign.enforce_out_of_scope_anchors(result["paths"], ledger.data["config"])
    except campaign.CampaignError as e: problems.append(str(e))
    try: campaign.enforce_mandatory_packets(result["paths"])
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        campaign.enforce_large_mandatory_rows(result["paths"], shares, profile, story, campaign_dir)
        big = [(i, round(shares[i], 2), p.get("probed_below")) for i, p in enumerate(result["paths"], 1)
               if p["disposition"] in ("mandatory", "no-qualifying-mechanism") and shares.get(i, 0.0) >= campaign.ALGORITHMIC_ATTENTION_PCT]
        if big: print("\nlarge rows closed by count (row, share, rows probed beneath):", big[:20])
    except campaign.CampaignError as e: problems.append(str(e))
    owners = {p["mechanism_key"]: p["anchor"] for p in result["paths"] if p["disposition"] in ("novel", "known")}
    lookup = lambda key: ledger.mechanism(parent["area_key"], key)
    for p in result["paths"]:
        if p["disposition"] == "covered-by" and p["covered_by"] not in owners:
            m = lookup(p["covered_by"])
            if m: owners[p["covered_by"]] = m["anchor"]
    try:
        campaign.enforce_covered_by_sample_identity(result["paths"], owners, profile, story)
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        symbols = campaign.owner_probe_symbols(result["paths"], lookup, campaign_dir)
        campaign.enforce_covered_by_probe_identity(result["paths"], symbols, profile, story)
    except campaign.CampaignError as e: problems.append(str(e))
    try:
        symbols = campaign.owner_probe_symbols(result["paths"], lookup, campaign_dir)
        campaign.enforce_covered_by_nearest_probe(result["paths"], symbols,
            campaign.story_probe_symbols(campaign_dir, story), profile, story)
    except campaign.CampaignError as e: problems.append(str(e))
    for i, p in enumerate(result["paths"], 1):
        if p["disposition"] in ("novel", "known") and shares.get(i) is not None:
            frac = p.get("estimated_avoidable_fraction")
            supplied = p.get("estimated_local_story_impact_pct")
            if frac is not None and supplied is not None and abs(float(supplied) - shares[i] * float(frac)) > 1e-9:
                problems.append(f"Path {i} ({p['anchor'][:60]!r}) estimated_local_story_impact_pct {supplied} is not the ledger's share x fraction {shares[i] * float(frac):.6f}; omit the field (decompose derives it) or set it to exactly that value.")
            if p["disposition"] == "novel" and p.get("mechanism_key"):
                existing = next((o for o in ledger.data["opportunities"] if o.get("kind") == "mechanism" and o.get("mechanism_key") == p["mechanism_key"]), None)
                if existing:
                    problems.append(f"Path {i} ({p['anchor'][:60]!r}) is novel for mechanism_key {p['mechanism_key']!r}, which already exists as #{existing['id']}; mark it known.")
            if frac is not None and shares[i] * float(frac) < story_floor:
                problems.append(f"Path {i} ({p['anchor'][:60]!r}) is {p['disposition']} at {float(frac):.4f} of {shares[i]:.2f}% = {shares[i]*float(frac):.3f}%, below the {story_floor:.3f}% floor; decompose refuses it as a candidate. Close it by count (mandatory / no-qualifying-mechanism) instead.")
    rows = campaign.decomposition_rows_at_or_above_floor(parent, result, ledger.data["config"])
    print(f"\n{len(rows)} rows at/above floor; dispositions:", {d: sum(1 for r in rows if r['disposition'] == d) for d in set(r['disposition'] for r in rows)})
    print("\nPROBLEMS:" if problems else "\nno gate problems")
    for x in problems: print(" -", x)
    return 1 if problems else 0

if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
