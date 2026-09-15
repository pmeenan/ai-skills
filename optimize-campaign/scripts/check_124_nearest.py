import json, pathlib, math
import campaign

campaign_dir = pathlib.Path('/home/pmeenan/src/chromium/src/.agents/campaigns/speedometer-september')
ledger = campaign.Ledger(campaign_dir).load()
parent = ledger.opp(124)
story = parent['target_story']
cfg = ledger.data['config']
base_floor = cfg.get('share_floor_pct', 0.0)
floor = max(campaign.story_floor_pct(cfg, story)[0], float(base_floor))

with open(campaign_dir / 'outbox/review-requests/decomp-124-r45.json') as f:
    result = json.load(f)

paths = result['paths']
profile = ledger.profile(parent["profile_id"])
measured = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")): r.get("measured_share_pct", 0.0)
            for r in parent["expected_work_refs"]}
shares = {}
for i, p in enumerate(paths, 1):
    prim = {tuple(r[k] for k in ("capture_id", "entry_key", "hotspot_key")) for r in p["work_refs"] if r["accounting"] == "primary"}
    if prim:
        shares[i] = min(measured[k] for k in prim)

files = campaign.collapsed_stack_files(profile, story)
story_packets = campaign.story_site_packets(campaign_dir, story, None)
by_symbol = {}
for site, entries in story_packets.items():
    for packet, rel in entries:
        symbol = str(packet.get("probe_symbol") or "").strip()
        if symbol:
            by_symbol.setdefault(symbol, []).append((site, packet, rel))

bound_rows = [(i, p) for i, p in enumerate(paths, 1) if p.get("redundancy_evidence")]
packets = campaign.bound_packets(paths, bound_rows, campaign_dir)

anchors = {p['anchor'] for p in paths}
anchor_w, symbol_w, both_w = campaign.anchor_symbol_weights(files, anchors, set(by_symbol))

for idx in [21, 22, 23, 41, 185]:
    item = paths[idx]
    anchor = item['anchor']
    share = shares.get(idx + 1)
    ref = (item.get('redundancy_evidence') or {}).get('path')
    packet = packets[ref][0] if ref in packets else None
    bound_symbol = str(packet.get("probe_symbol") or "").strip() if packet else ""
    row_w = anchor_w.get(anchor, 0.0)
    print(f"\n--- Path {idx+1}: {anchor[:60]} (share={share}%) ---")
    print(f"Current bound symbol: {bound_symbol}")
    distances = {}
    for symbol, weight in symbol_w.items():
        shared = both_w.get((anchor, symbol), 0.0)
        if weight <= 0: continue
        relevance = max(shared / row_w, shared / weight) if row_w else 0.0
        if relevance >= campaign.PACKET_RELEVANCE:
            distances[symbol] = (abs(math.log(weight / row_w)), weight / row_w, shared / row_w, shared / weight)
    for sym, (d, w_ratio, sh_row, sh_sym) in sorted(distances.items(), key=lambda x: x[1][0])[:5]:
        print(f"  sym: {sym[:50]} | dist={d:.3f} | weight_ratio={w_ratio:.2f}x | sh_row={sh_row:.2f} | sh_sym={sh_sym:.2f}")

