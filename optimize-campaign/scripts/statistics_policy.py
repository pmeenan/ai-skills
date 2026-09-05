#!/usr/bin/env python3
"""Fixed-plan, block-level performance decisions. Positive always means faster.

Discovery statistics are descriptive. Acceptance uses a preregistered primary
endpoint and simultaneous non-inferiority bounds for the regression family.
"""
import json
import math
import statistics


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    return float(value)


def _betacf(a, b, x):
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, 201):
        for aa in (m * (b-m) * x / ((a+2*m-1)*(a+2*m)),
                   -(a+m)*(a+b+m)*x / ((a+2*m)*(a+2*m+1))):
            d = 1 + aa*d
            c = 1 + aa/c
            d = 1 / (d if abs(d) > 1e-30 else 1e-30)
            c = c if abs(c) > 1e-30 else 1e-30
            change = d*c
            h *= change
        if abs(change-1) < 1e-12:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    bt = math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    if x < (a+1)/(a+b+2): return bt*_betacf(a,b,x)/a
    return 1-bt*_betacf(b,a,1-x)/b


def t_critical(df, alpha=0.05):
    if df <= 0 or not 0 < alpha < 1:
        raise ValueError("invalid confidence parameters")
    lo, hi = 0.0, 1.0
    def tail(t): return _ibeta(df/2, 0.5, df/(df+t*t))
    while tail(hi) > alpha:
        hi *= 2
    for _ in range(70):
        mid = (lo+hi)/2
        if tail(mid) > alpha: lo = mid
        else: hi = mid
    return (lo+hi)/2


def log_summary(diffs, alpha=0.05):
    values = [finite(x) for x in diffs]
    if len(values) < 3:
        raise ValueError("at least three independent blocks required")
    mean = statistics.fmean(values)
    se = statistics.stdev(values) / math.sqrt(len(values))
    half = t_critical(len(values)-1, alpha)*se
    pct = lambda x: 100*math.expm1(x)
    # This is an approximate planning MDE, not observed/post-hoc power.
    mde = pct((t_critical(len(values)-1, alpha)+t_critical(len(values)-1, 0.4))*se)
    centered = [x-mean for x in values]
    variance = sum(x*x for x in centered)
    lag1 = sum(a*b for a,b in zip(centered,centered[1:]))/variance if variance else 0.0
    return {"delta_pct": pct(mean), "ci_pct": [pct(mean-half),pct(mean+half)],
            "n_blocks":len(values), "std_err_log":se, "mde_80_pct":mde,
            "lag1_autocorrelation":lag1}


def validate_plan(plan):
    required = {"blocks", "primary", "minimum_effect_pct", "regression_margin_pct",
                "suite_regression_margin_pct", "alpha", "max_abs_lag1"}
    if not isinstance(plan,dict) or set(plan) != required:
        raise ValueError("statistical plan fields must be: " + ", ".join(sorted(required)))
    n=plan["blocks"]
    if isinstance(n,bool) or not isinstance(n,int) or n < 4 or n%2:
        raise ValueError("planned blocks must be even and at least four")
    if plan["primary"] != "suite" and (not isinstance(plan["primary"],list) or
            not plan["primary"] or any(not isinstance(x,str) or not x for x in plan["primary"]) or
            len(set(plan["primary"])) != len(plan["primary"])):
        raise ValueError("primary must be suite or a unique preregistered workload list")
    for field in ("minimum_effect_pct","regression_margin_pct","suite_regression_margin_pct"):
        if not 0 < finite(plan[field]) < 100:
            raise ValueError(field + " must be between zero and 100 percent")
    if not 0 < finite(plan["alpha"]) <= 0.05:
        raise ValueError("alpha must be in (0, 0.05]")
    if not 0 < finite(plan["max_abs_lag1"]) < 1:
        raise ValueError("max_abs_lag1 must be in (0,1)")
    return plan


def block_differences(manifest):
    from benchmark_adapters import get_adapter
    adapter=get_adapter(manifest.get("benchmark"))
    suite, workloads = [], {}
    inventory=None
    blocks=manifest.get("block_details",[])
    schedule=manifest.get("schedule",[])
    if len(blocks) < 4 or len(blocks)%2 or len(schedule)!=len(blocks) or any(
            schedule.count(p)!=len(blocks)//2 for p in ("ABBA","BAAB")):
        raise ValueError("incomplete/unbalanced measurement")
    for index,b in enumerate(blocks,1):
        if b.get("block") != index or b.get("pattern") != schedule[index-1]:
            raise ValueError("block order disagrees with schedule")
        for arm in ("a","b"):
            if len(b.get(arm+"_scores",[]))!=2 or len(b.get(arm+"_stories",[]))!=2:
                raise ValueError("two independent page loads per arm required")
            for row in b[arm+"_stories"]:
                if inventory is None: inventory=set(row)
                if not inventory or set(row)!=inventory:
                    raise ValueError("workload inventory changed")
        def logs(values):
            return statistics.fmean(math.log(finite(x)) for x in values)
        suite.append(logs(b["b_scores"])-logs(b["a_scores"]))
        for story in inventory:
            a=logs([x[story] for x in b["a_stories"]])
            c=logs([x[story] for x in b["b_stories"]])
            workloads.setdefault(story,[]).append(c-a if adapter.workload_value_direction=="higher" else a-c)
    return suite,workloads


def evaluate(manifest, plan):
    validate_plan(plan)
    suite,workloads=block_differences(manifest)
    if len(suite)!=plan["blocks"] or manifest.get("blocks")!=plan["blocks"]:
        raise ValueError("measurement does not match preregistered sample size")
    targets=plan["primary"]
    if targets != "suite" and not set(targets)<=set(workloads):
        raise ValueError("preregistered primary workload missing")
    primary=suite if targets=="suite" else [statistics.fmean(workloads[s][i] for s in targets) for i in range(len(suite))]
    p=log_summary(primary,plan["alpha"])
    # Bonferroni bounds also include the overall score in the regression family.
    family_alpha=plan["alpha"]/(len(workloads)+1)
    guards={s:log_summary(v,family_alpha) for s,v in workloads.items()}
    guards["@suite"]=log_summary(suite,family_alpha)
    margins={s:plan["regression_margin_pct"] for s in workloads}
    margins["@suite"]=plan["suite_regression_margin_pct"]
    regressions=[s for s,v in guards.items() if v["ci_pct"][1] < -margins[s]]
    unresolved=[s for s,v in guards.items() if v["ci_pct"][0] < -margins[s]]
    dependence=any(abs(v["lag1_autocorrelation"])>plan["max_abs_lag1"] for v in [p,*guards.values()])
    if dependence: verdict="INCONCLUSIVE"
    elif regressions: verdict="REGRESSION"
    elif p["ci_pct"][0] >= plan["minimum_effect_pct"] and not unresolved: verdict="IMPROVEMENT"
    else: verdict="INCONCLUSIVE"
    return {"verdict":verdict,"primary":p,"regressions":regressions,
            "unresolved_regression_bounds":unresolved,"serial_dependence":dependence,
            "simultaneous_alpha":family_alpha,"guardrails":guards}


def calibrate(manifests, tolerance_pct, max_mde_pct, max_abs_lag1=0.4):
    """Independent session nulls must be equivalent and adequately precise."""
    if len(manifests)<2: raise ValueError("two independent A/A sessions required")
    if finite(tolerance_pct) <= 0 or finite(max_mde_pct) <= 0:
        raise ValueError("positive calibration tolerance and MDE required")
    sessions=set(); results=[]; reference=None
    for m in manifests:
        identity=m.get("session_id")
        if not identity or identity in sessions or m.get("mode")!="aa":
            raise ValueError("A/A session identities must be distinct")
        sessions.add(identity)
        # Transport-local paths and runtime observations can differ; compare stable identities.
        # The rendering surface (headless vs X display, viewport, GPU renderer) is part of
        # the identity: a calibration made on one surface says nothing about another.
        environment = m.get("capture_environment",{})
        display = environment.get("display") or {}
        stable = (m.get("benchmark"), m.get("stories"), m.get("payload_provenance",{}).get("payload_sha256"),
                  environment.get("host_name"), json.dumps(environment.get("host_settings"),sort_keys=True),
                  json.dumps({k:display.get(k) for k in ("mode","display","viewport","gpu_renderer")},sort_keys=True),
                  m.get("build_provenance",{}).get("a",{}).get("browser_sha256"))
        if reference is None: reference=stable
        elif stable != reference: raise ValueError("A/A configuration changed between sessions")
        suite,workloads=block_differences(m)
        alpha=.05/(len(workloads)+1)
        summaries={"@suite":log_summary(suite,alpha),**{s:log_summary(v,alpha) for s,v in workloads.items()}}
        results.append(summaries)
    passed=all(v["ci_pct"][0]>=-tolerance_pct and v["ci_pct"][1]<=tolerance_pct and
               v["mde_80_pct"]<=max_mde_pct and abs(v["lag1_autocorrelation"])<=max_abs_lag1
               for row in results for v in row.values())
    return {"gate_pass":passed,"sessions":sorted(sessions),"results":results,
            "tolerance_pct":tolerance_pct,"max_mde_pct":max_mde_pct}
