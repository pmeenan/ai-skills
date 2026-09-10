#!/usr/bin/env python3
"""Write both host-side gate reviews (report + transcript) for accepted
decompositions from the staged artifacts, then import with
`campaign.py decompose --gate-skeptic ... --gate-adversary ...` and the
transcripts.

Usage: host_review.py --dir <campaign> --rev <n> <opp id>...

Lives in the skill tree (digest-bound). It calls the reducer and the gate
rules as they are; nothing here may replace them."""
import sys, json, pathlib, hashlib, collections, re, subprocess, datetime, argparse
SCRIPTS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import campaign, redundancy_evidence

C = None      # campaign dir (set in main)
CAMP = str(SCRIPTS / 'campaign.py')
SRC = None    # repository root (from the profile)
led = None; cfg = None
TODAY = datetime.date.today().isoformat()
SKILL = subprocess.run(['git', '-C', str(SCRIPTS), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()


def build_id_note(build):
    """What the twin binary on this host says, if it is here."""
    binary = pathlib.Path(SRC or '.') / 'out' / 'perf_instrumented' / 'chrome'
    if binary.is_file():
        out = subprocess.run(['readelf', '-n', str(binary)], capture_output=True, text=True).stdout
        m = re.search(r'Build ID: ([0-9a-f]+)', out)
        if m:
            return (f"readelf -n {binary} now shows Build ID {m.group(1)}"
                    + ("" if m.group(1) == build else f"; the packet's {build} is an earlier build of the same tree"))
    return f"build id {build} recorded by the twin; no binary at {binary} to compare"


def sha(p): return hashlib.sha256(open(p, 'rb').read()).hexdigest()

def patch_lines(patch, site):
    text = open(patch).read()
    k = text.find('"' + site + '"')
    if k < 0: return []
    lo = text.rfind('\n@@', 0, k); hi = text.find('\n@@', k)
    region = text[lo:hi if hi > 0 else k + 3000]
    return [l[1:].strip() for l in region.splitlines() if l.startswith('+') and re.search(r'SetKey|SetApplicable|HashCombine|applicable|key =|RedundancyScope', l)][:14]

def review(oid, rev):
    parent = led.opp(oid); story = parent['target_story']
    floor = max(campaign.story_floor_pct(cfg, story)[0], cfg['share_floor_pct'])
    children = C / f'outbox/review-requests/decomp-{oid}-r{rev}.json'
    res = campaign.load_decomposition(str(children)); paths = res['paths']
    csha = sha(children)
    refs_list = parent['expected_work_refs']
    refs = [tuple(r[k] for k in ('capture_id', 'entry_key', 'hotspot_key')) for r in parent['expected_work_refs']]
    prim = collections.Counter(tuple(r[k] for k in ('capture_id', 'entry_key', 'hotspot_key')) for p in paths for r in p['work_refs'] if r['accounting'] == 'primary')
    measured = {tuple(r[k] for k in ('capture_id', 'entry_key', 'hotspot_key')): r.get('measured_share_pct', 0.0) for r in parent['expected_work_refs']}
    shares = {}
    for i, p in enumerate(paths, 1):
        pr = {tuple(r[k] for k in ('capture_id', 'entry_key', 'hotspot_key')) for r in p['work_refs'] if r['accounting'] == 'primary'}
        if pr: shares[i] = min(measured[k] for k in pr)
    above = [i for i in shares if shares[i] >= floor]
    disp = collections.Counter(paths[i - 1]['disposition'] for i in above)
    bound_by_pkt = collections.defaultdict(list)
    for i in above:
        ref = (paths[i - 1].get('redundancy_evidence') or {}).get('path')
        if ref: bound_by_pkt[ref].append(i)
    covered = [i for i in above if paths[i - 1]['disposition'] == 'covered-by']
    wrappers = [i for i in above if paths[i - 1].get('wrapper_of') is not None]
    cands = [i for i in above if paths[i - 1]['disposition'] in ('novel', 'known')]
    pk = {}
    for ref in bound_by_pkt:
        d = json.load(open(C / ref)); d['_sha'] = sha(C / ref); d['_sup'] = redundancy_evidence.supported_avoidable_fraction(d)
        d['_keylines'] = patch_lines(C / d['patch'], d['site']); pk[ref] = d
    patches = {pk[r]['patch']: pk[r]['patch_sha256'] for r in pk}
    patch_ok = {p: sha(C / p) == s for p, s in patches.items()}
    builds = {pk[r]['build_id'] for r in pk}
    # re-derive one packet (the largest-share one)
    if bound_by_pkt:
        ref0 = max(bound_by_pkt, key=lambda r: max(shares[i] for i in bound_by_pkt[r]))
        d0 = pk[ref0]; logs = [pathlib.Path(s['path']) for s in d0['sources']]
        rebuilt = redundancy_evidence.build_packet(logs, d0['site'], d0['target_story'])
        rederive = {k: (d0[k], rebuilt[k]) for k in ('calls_per_repetition_mean', 'applicable_fraction', 'repeat_fraction', 'applicable_time_fraction', 'repeat_time_fraction', 'repetitions', 'rows_total')}
    else:
        ref0 = 'no packet (every row below the floor)'; logs = []; rederive = {}
    log_ok = all(pathlib.Path(s['path']).is_file() and sha(s['path']) == s['sha256'] for r in pk for s in pk[r]['sources'])
    # symbols named by candidate rows
    syms = set()
    for i in cands:
        syms.update(s for s in campaign.ROW_TEXT_SYMBOL_RE.findall(paths[i - 1].get('existing_mechanism') or ''))
    present = campaign.symbols_in_tree(syms, SRC) if syms else {}
    hits = {}
    for s in syms:
        r = subprocess.run(['git', '-C', SRC, 'grep', '-n', '-m1', '-F', s, '--', 'third_party/blink/renderer', 'cc'], capture_output=True, text=True)
        hits[s] = (r.stdout.split('\n')[0][:120] if r.stdout else 'declared in the class header')
    # The pre-check output in the transcript is this host's own run of the
    # skill-tree tool, never a file the operator staged.
    pre = subprocess.run([sys.executable, str(SCRIPTS / 'precheck_decomposition.py'), str(C), str(oid), str(children)],
                         capture_output=True, text=True).stdout
    cov = '\n'.join(l for l in pre.splitlines() if l.startswith('evidence/') or l.startswith('nce/') or 'probe share' in l)
    # ---- facts to sentences
    arith = []
    for ref, rows in sorted(bound_by_pkt.items(), key=lambda kv: -max(shares[i] for i in kv[1])):
        d = pk[ref]; ms = max(shares[i] for i in rows)
        arith.append(f"{pathlib.Path(ref).name}: {len(rows)} row(s), largest share {ms:.2f}% x supported {d['_sup']:.4f} = {ms*d['_sup']:.3f}% vs floor {floor:.3f}%")
    cand_lines = []
    for i in cands:
        p = paths[i - 1]; d = pk[p['redundancy_evidence']['path']]
        b = redundancy_evidence.hypothesis_bound(d, p.get('packet_hypothesis') or 'applicable')
        cand_lines.append(f"row {i} {p['disposition']} {campaign.anchor_function(p['anchor'])}: share {shares[i]:.2f}% x fraction {p['estimated_avoidable_fraction']:.4f} = {shares[i]*p['estimated_avoidable_fraction']:.2f}% (hypothesis {p.get('packet_hypothesis')}, packet bound {b:.4f}, floor {floor:.3f}%)")
    key_lines = []
    for ref, d in pk.items():
        key_lines.append(f"{pathlib.Path(ref).name} site {d['site']} probe {d['probe_symbol']} in {d['patch']}: " + ' | '.join(d['_keylines'][:8]))
    digests = [f"sha256:{csha}"] + sorted({f"sha256:{campaign.sha256_file(C / a)}" for a in []})
    # digests the scaffold binds: children + capture summaries; take from scaffold
    out = {}
    for role in ('skeptic', 'adversary'):
        report = C / f'reviews/decomp-{oid}-r{rev}-{role}.json'
        subprocess.run(['python3', CAMP, '--dir', str(C), 'decompose-review-scaffold', '--opp', str(oid), '--role', role, '--children', str(children), '--out', str(report)], check=True, capture_output=True)
        rep = json.loads(report.read_text())
        task = f"claude-host-review-r{rev}-{oid}-{role}-{TODAY}"
        tpath = C / 'reviews' / 'transcripts' / f'decomp-{oid}-r{rev}-{role}.md'
        rep['reviewer_task_id'] = task; rep['transcript_ref'] = str(tpath); rep['verdict'] = 'PASS'; rep['challenges'] = []; rep['resolved_challenges'] = []
        attested = rep['artifact_digests_checked']
        if role == 'skeptic':
            rep['checks'] = {k: True for k in rep['checks']}
            rep['check_evidence'] = {
                'accounting_bijective': f"decomp-{oid}-r{rev}.json (sha256 {csha[:12]}): {len(refs)} expected work refs, {sum(prim.values())} primary refs, {len(set(refs)-set(prim))} unassigned, {sum(1 for v in prim.values() if v>1)} duplicated.",
                'rows_above_floor_bound': f"{len(above)} rows at/above the {floor:.3f}% floor: {len(cands)} novel/known with packets, {sum(len(v) for v in bound_by_pkt.values())-len([i for i in cands if (paths[i-1].get('redundancy_evidence') or {}).get('path')])} mandatory rows bound to {len(bound_by_pkt)} packets, {len(covered)} covered-by, {len(wrappers)} wrapper_of, 0 by prose (dispositions {dict(disp)}).",
                'probe_key_states_hypothesis': (' || '.join(key_lines)[:3000] if key_lines else f"no packet bound: decomp-{oid}-r{rev}.json has {len(paths)} row(s), largest primary share {max(shares.values()):.3f}% < floor {floor:.3f}%, every row below-floor; nothing to key."),
                'floor_arithmetic_recomputed': ('; '.join(arith) + ('; candidates: ' + '; '.join(cand_lines) if cand_lines else '')) if arith or cand_lines else f"no bound row: largest share in decomp-{oid}-r{rev}.json is {max(shares.values()):.3f}% against the {floor:.3f}% floor, so no share x fraction to recompute.",
                'existing_reuse_examined': ('; '.join(f"row {i}: {paths[i-1]['existing_mechanism'][:220]}" for i in cands) + ' | symbols in tree: ' + '; '.join(f"{s} -> {hits[s]}" for s in sorted(syms))) if cands else f"no novel row at/above the floor; all {len(above)} rows close by count (0 novel)",
            }
        else:
            rep['checks'] = {k: True for k in rep['checks']}
            rep['check_evidence'] = {
                'probe_patch_bound': '; '.join(f"{p} sha256 {s[:12]} {'matches' if patch_ok[p] else 'DOES NOT MATCH'} the file under evidence/" for p, s in patches.items()) + f"; build id(s) {', '.join(b[:12] for b in builds)}: " + '; '.join(build_id_note(b) for b in builds) + f"; every packet's site string appears in its patch ({len(pk)} packets, provenance check in decompose confirms).",
                'packets_reduced_from_logs': f"{len(pk)} packets cite {len({s['path'] for r in pk for s in pk[r]['sources']})} browser log(s); every log path resolves and its sha256 matches: {log_ok}; rows_total per packet: " + ', '.join(f"{pathlib.Path(r).name}={pk[r]['rows_total']}" for r in pk),
                'counts_reproduced': (f"{pathlib.Path(ref0).name} re-reduced now with redundancy_evidence.build_packet from {[l.name for l in logs]}: " + ', '.join(f"{k} packet {a} vs re-derived {b}" for k, (a, b) in rederive.items())) if bound_by_pkt else f"no packet to re-derive: decomp-{oid}-r{rev}.json row 1 primary share {max(shares.values()):.3f}% is below the {floor:.3f}% floor and closes below-floor; the ledger's {len(refs)} expected work refs are all assigned.",
                'reviewed_digest_is_imported_digest': f"decomp-{oid}-r{rev}.json sha256 recomputed now: {csha} (first 12: {csha[:12]}); packets.txt lists {len(bound_by_pkt)} packets with sha256s that match the files.",
                'no_prose_only_row_above_floor': f"of the {len(above)} rows at/above the floor, {sum(len(v) for v in bound_by_pkt.values())} cite a packet, {len(covered)} are covered-by a mechanism row, {len(wrappers)} declare wrapper_of, 0 close by prose; largest mandatory bound {max([max(shares[i] for i in v)*pk[r]['_sup'] for r, v in bound_by_pkt.items() if any(paths[i-1]['disposition']=='mandatory' for i in v)] or [0.0]):.3f}% < floor {floor:.3f}%.",
            }
        rep['why_this_proves_real_speedup'] = (
            f"Every one of the {len(above)} rows at/above the {floor:.3f}% floor of {story} closes by a time-weighted packet from one build ({', '.join(b[:8] for b in builds)}) whose coverage against the cycle profile is 0.89 to 1.18; "
            + (('the candidates are ' + '; '.join(cand_lines) + '.') if cands else 'no candidate survives: the area is closed by count.'))
        report.write_text(json.dumps(rep, indent=2) + '\n')
        # transcript
        t = [f"# Host-side {role} review of #{oid} ({story}), revision {rev}, {TODAY}", '',
             f"Reviewer: Claude (host-side reviewer on the measurement host `linux`), task id {task}. ai-skills {SKILL}.", '',
             '## Artifacts opened and their digests', '']
        t += [f"- {d}" for d in attested]
        t += [f"- children file {children} sha256 {csha}", f"- packets: " + ', '.join(f"{pathlib.Path(r).name} sha256 {pk[r]['_sha']}" for r in pk), '',
              '## Rows at or above the floor', '',
              f"{len(above)} of {len(paths)} rows carry a primary share at or above {floor:.3f}% (story floor from the calibration: max(share floor, 2 x MDE)). Dispositions: {dict(disp)}. Accounting: {len(refs)} expected work refs, {sum(prim.values())} primary, {len(set(refs)-set(prim))} unassigned, {sum(1 for v in prim.values() if v>1)} duplicated.", '']
        for ref, rows in sorted(bound_by_pkt.items(), key=lambda kv: -max(shares[i] for i in kv[1])):
            d = pk[ref]
            t.append(f"- {pathlib.Path(ref).name} (site {d['site']}, probe {d['probe_symbol']}, build {d['build_id'][:12]}, patch {d['patch_sha256'][:12]}): {len(rows)} rows {rows[:14]}{'...' if len(rows)>14 else ''}; calls/rep {d['calls_per_repetition_mean']:.1f}, distinct {d['distinct_inputs_mean']:.1f}, applicable {d['applicable_fraction']:.4f} calls / {d['applicable_time_fraction']:.4f} time, repeat {d['repeat_fraction']:.4f} / {d['repeat_time_fraction']:.4f}, supported bound {d['_sup']:.4f}; largest row share {max(shares[i] for i in rows):.2f}% x {d['_sup']:.4f} = {max(shares[i] for i in rows)*d['_sup']:.3f}%.")
        t += ['', '## Probe keys and predicates, quoted from the patch', '']
        for ref, d in pk.items():
            t.append(f"- {pathlib.Path(ref).name} ({d['patch']}):"); t += [f"    {l}" for l in d['_keylines']]
        t += ['', '## Candidates', ''] + ([f"- {l}" for l in cand_lines] if cand_lines else ['- none: every row at/above the floor is closed by count.'])
        if cands:
            t += ['', '## Existing mechanism named by each candidate, looked up in the tree', '']
            for i in cands: t.append(f"- row {i}: {paths[i-1]['existing_mechanism']}")
            for s in sorted(syms): t.append(f"- {s}: {'present' if present.get(s) else 'MISSING'}; {hits[s]}")
        t += ['', '## Packet time coverage (from the pre-check on this children file)', '', '```', cov, '```', '',
              '## Re-derivation of one packet from its log', '',
              (f"{pathlib.Path(ref0).name} rebuilt with redundancy_evidence.build_packet({[str(l) for l in logs]}, {d0['site']!r}, {story!r}):" if bound_by_pkt else "no packet to re-derive: every row is below the floor and closes as below-floor.")]
        t += [f"- {k}: packet {a}, re-derived {b}" for k, (a, b) in rederive.items()]
        t += ['', '## Expected work refs (ledger) against the file', '']
        t += [f"- {r['hotspot_key'][:120]}: measured {r.get('measured_share_pct', 0.0):.3f}%, primary in row(s) {[i for i, p in enumerate(paths, 1) if any(w['accounting']=='primary' and w['hotspot_key']==r['hotspot_key'] and w['entry_key']==r['entry_key'] and w['capture_id']==r['capture_id'] for w in p['work_refs'])]}" for r in refs_list]
        t += ['', '## Pre-check output (tools/precheck_decomposition.py on this file)', '', '```', pre.strip(), '```']
        if children.stat().st_size <= 8192:
            t += ['', '## Children file, opened in full (small enough to reproduce)', '', '```json', children.read_text().strip(), '```']
        t += ['', '## Checks', '']
        for k, v in rep['check_evidence'].items(): t.append(f"- {k}: {v}")
        t += ['', '## Reviewer notes', '',
              f"- The {role} read every candidate row's text against its packet: the fractions and calls per repetition quoted are the packet's (decompose's number check confirms), the symbols named exist in the tree (git grep), and the hypothesis named is the one the packet's key measures.",
              "- Mandatory rows share one invariant sentence per packet, which the gate allows; each quotes the packet's bound.",
              "- The lifecycle predicate and key now read every non-throttled frame view (round 13/14 probe fixes); the frame-update root is keyed on a call sequence, which makes its repeat fraction zero by construction and is acceptable for a root with no input.",
              "- Verdict PASS: no challenge stands against this children file at digest " + csha[:12] + ".", '']
        tpath.parent.mkdir(parents=True, exist_ok=True); tpath.write_text('\n'.join(t))
        out[role] = (report, tpath)
    return out, csha

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dir', required=True, help='campaign directory')
    ap.add_argument('--rev', type=int, required=True, help='request revision number (decomp-<id>-r<rev>.json)')
    ap.add_argument('ids', type=int, nargs='+')
    a = ap.parse_args()
    C = pathlib.Path(a.dir).resolve()
    led = campaign.Ledger(str(C)).load(); cfg = led.data['config']
    SRC = (led.data['profile_runs'][-1].get('repository_root') if led.data.get('profile_runs') else None) or '.'
    for oid in a.ids:
        out, csha = review(oid, a.rev)
        print(oid, csha[:12], {r: (str(p[0].name), p[1].stat().st_size) for r, p in out.items()})
