#!/usr/bin/env python3
"""Conservative opportunity ranking; CPU samples are never a score forecast."""
import math
from statistics_policy import finite


def rank(packet):
    """One row per affected story, with a measured score/critical-path bound.

    CPU-only discoveries retain unknown score headroom and need a cheap causal
    experiment. Estimated removability must never multiply an enclosing stack's
    entire wall time. Bounds are planning limits, not claimed improvements.
    """
    rows = packet['workloads']
    if not rows or len({r['name'] for r in rows}) != len(rows):
        raise ValueError('unique affected workload rows required')
    count = packet['suite_workload_count']
    if not isinstance(count, int) or count < len(rows):
        raise ValueError('invalid aggregate workload denominator')
    weighted_log_upper = 0.0
    for row in rows:
        if row['basis'] not in ('paired-oracle', 'critical-path-counterfactual'):
            raise ValueError('score headroom requires a causal bound, not CPU stack share')
        if not row.get('artifact_sha256') or not row.get('source_revision'):
            raise ValueError('bound provenance required')
        upper = finite(row['score_gain_upper_pct'])
        if upper < 0: raise ValueError('negative gain bound')
        weighted_log_upper += math.log1p(upper/100)/count
    upper = 100*math.expm1(weighted_log_upper)
    confidence = finite(packet['confidence']); acceptance = finite(packet['acceptance_probability'])
    if not 0 < confidence <= 1 or not 0 < acceptance <= 1:
        raise ValueError('confidence and acceptance probability must be in (0,1]')
    cost = finite(packet['engineering_hours']) + finite(packet['measurement_hours'])
    if cost <= 0: raise ValueError('positive total cost required')
    mde = finite(packet['calibrated_mde_pct'])
    minimum = finite(packet['minimum_effect_pct'])
    if mde <= 0 or minimum <= 0: raise ValueError('positive fixed-plan precision/effect required')
    viable = upper >= max(mde, minimum)
    return {'aggregate_score_upper_pct': upper, 'viable_with_budget': viable,
            'priority': upper*confidence*acceptance/cost if viable else 0.0,
            'reason': 'within calibrated measurement budget' if viable else 'causal upper bound below fixed-plan precision/effect'}
