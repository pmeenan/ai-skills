#!/usr/bin/env python3
"""Reduce trace-backed latency counterfactuals independently of CPU savings.

The packet binds raw Chrome JSON traces and identifies a serial dependency path
through complete events and native flow events. A trace path supports a causal
hypothesis; only separate uninstrumented score measurements establish a win.
"""
import argparse
import hashlib
import json
import math
import pathlib
from statistics_policy import log_summary, finite


def trace_path(trace, path):
    events = trace.get('traceEvents', [])
    if trace.get('metadata', {}).get('interval_kind') != 'exact-scored':
        raise ValueError('exact scored trace required')
    indices = path['events']
    if len(indices) < 3 or len(set(indices)) != len(indices):
        raise ValueError('dependency path requires distinct start/work/end events')
    nodes = [events[i] for i in indices]
    if nodes[0].get('name') != path['start_mark'] or nodes[-1].get('name') != path['end_mark']:
        raise ValueError('score boundary marks differ from trace')
    start = finite(nodes[0]['ts']); end = finite(nodes[-1]['ts'])
    if end <= start: raise ValueError('invalid scored interval')
    if len(path['edges']) != len(nodes)-1:
        raise ValueError('dependency path has missing edges')
    for a,b,edge in zip(nodes,nodes[1:],path['edges']):
        duration = finite(a.get('dur',0))
        if duration < 0: raise ValueError('negative trace duration')
        a_end = finite(a['ts']) + duration
        if a_end > finite(b['ts']): raise ValueError('serial path contains overlapping work')
        if edge['kind'] == 'thread-order':
            if (a.get('pid'),a.get('tid')) != (b.get('pid'),b.get('tid')) or a.get('tid') is None:
                raise ValueError('thread-order edge crosses threads')
        elif edge['kind'] == 'flow':
            begin,finish = (events[edge[n]] for n in ('begin_index','end_index'))
            if (begin.get('ph') not in ('s','t') or finish.get('ph') not in ('t','f')
                    or begin.get('id') is None or begin['id'] != finish.get('id')
                    or begin.get('cat') != finish.get('cat')
                    or (begin.get('pid'),begin.get('tid')) != (a.get('pid'),a.get('tid'))
                    or (finish.get('pid'),finish.get('tid')) != (b.get('pid'),b.get('tid'))
                    or not finite(a['ts']) <= finite(begin['ts']) <= a_end
                    or not finite(begin['ts']) <= finite(finish['ts']) <= finite(b['ts'])):
                raise ValueError('dependency edge is not supported by matching native trace flow')
        else: raise ValueError('unknown dependency edge')
    removable = path.get('removable_event_indices',[])
    if len(set(removable)) != len(removable) or not set(removable) <= set(indices[1:-1]):
        raise ValueError('counterfactual must identify actual work on the dependency path')
    work = sum(finite(events[i].get('dur',0)) for i in removable)
    edges = path.get('removable_edge_indices',[])
    if len(set(edges)) != len(edges): raise ValueError('duplicate removable edge')
    for i in edges:
        if not isinstance(i,int) or isinstance(i,bool) or not 0 <= i < len(path['edges']) or path['edges'][i]['kind'] != 'flow':
            raise ValueError('removable waits require a native dependency flow')
        work += finite(nodes[i+1]['ts']) - (finite(nodes[i]['ts'])+finite(nodes[i].get('dur',0)))
    if not 0 < work < end-start: raise ValueError('invalid removable path duration')
    return {'duration_us':end-start,'removable_us':work,
            'latency_headroom_pct':100*work/(end-start)}


def read_capture(row):
    path = pathlib.Path(row['trace']['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['trace']['sha256']:
        raise ValueError('trace digest changed')
    return trace_path(json.loads(path.read_text()), row['path'])


def reduce(packet):
    rows = packet['blocks']
    if len(rows) < 4 or len(rows)%2 or [r['block'] for r in rows] != list(range(1,len(rows)+1)):
        raise ValueError('at least four ordered paired latency blocks required')
    orders = [r['order'] for r in rows]
    if orders.count('AB') != len(rows)//2 or orders.count('BA') != len(rows)//2:
        raise ValueError('latency blocks require balanced interleaved AB/BA order')
    deltas=[]; headrooms=[]; previous_end=-1
    for row in rows:
        a=read_capture(row['a']); b=read_capture(row['b'])
        # Monotonic capture intervals are runner metadata, never inferred from block labels.
        left,right = (row[x] for x in ('a','b') if x in row) if row['order']=='AB' else (row['b'],row['a'])
        if not previous_end < left['started_ns'] < left['finished_ns'] <= right['started_ns'] < right['finished_ns']:
            raise ValueError('capture timestamps disagree with paired order')
        previous_end=right['finished_ns']
        deltas.append(math.log(a['duration_us']/b['duration_us']))
        headrooms.append(math.log1p(a['latency_headroom_pct']/100))
    change=log_summary(deltas); headroom=log_summary(headrooms)
    valid=abs(change['lag1_autocorrelation']) <= packet['max_abs_lag1']
    phase=packet['phase']
    if phase not in ('sizing','candidate'): raise ValueError('invalid latency phase')
    passed = valid and (headroom['ci_pct'][0] > 0 if phase=='sizing' else change['ci_pct'][0] > 0)
    return {**{k:packet[k] for k in ('benchmark','metric_model','opportunity_id','mechanism_key','profile_id','target_story','build','baseline_build')},
            'schema_version':4,'route':'latency','phase':phase,'interval_kind':'exact-scored',
            'score_scope':{'classification':'score-critical'},'gate_pass':passed,
            'latency_reduction':change,'latency_headroom_ci_pct':headroom['ci_pct'],
            'ceiling_pct':headroom['ci_pct'][1], 'packet':packet}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--packet',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();result=reduce(json.loads(pathlib.Path(args.packet).read_text()))
    pathlib.Path(args.out).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

if __name__=='__main__': main()
