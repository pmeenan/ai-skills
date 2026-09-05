"""Behavioral evidence-gate tests. All data and keys are temporary fixtures."""
import copy
import json
import math
import pathlib
import random
import subprocess
import tempfile
import unittest
from unittest import mock
import statistics_policy as stats
import opportunity_budget
import latency_evidence
import pinpoint_measure
import measurement_host


def plan():
    return dict(blocks=32,primary='suite',minimum_effect_pct=.1,regression_margin_pct=.5,
                suite_regression_margin_pct=.2,alpha=.05,max_abs_lag1=.9)


def manifest(gain=.01,story_gain=None,noise=.0001):
    rng=random.Random(421); rows=[]; orders=['ABBA','BAAB']*16;rng.shuffle(orders)
    for i,order in enumerate(orders,1):
        delta=gain+rng.uniform(-noise,noise)
        story_delta=delta if story_gain is None else story_gain+rng.uniform(-noise,noise)
        rows.append(dict(block=i,pattern=order,a_scores=[100,100],b_scores=[100*math.exp(delta)]*2,
                         a_stories=[{'Story':100}]*2,b_stories=[{'Story':100*math.exp(-story_delta)}]*2))
    return dict(benchmark='speedometer3',blocks=32,mode='ab',schedule=orders,block_details=rows)


class StatisticsTest(unittest.TestCase):
    def test_t_known_values(self):
        self.assertAlmostEqual(stats.t_critical(1),12.7062,places=3)
        self.assertAlmostEqual(stats.t_critical(31),2.0395,places=3)
    def test_clear_gain(self): self.assertEqual('IMPROVEMENT',stats.evaluate(manifest(),plan())['verdict'])
    def test_null_not_pass(self): self.assertEqual('INCONCLUSIVE',stats.evaluate(manifest(0),plan())['verdict'])
    def test_story_regression_vetoes_suite_gain(self):
        self.assertEqual('REGRESSION',stats.evaluate(manifest(.01,-.02),plan())['verdict'])
    def test_missing_block_invalid(self):
        m=manifest();m['block_details'].pop()
        with self.assertRaises(ValueError):stats.evaluate(m,plan())
    def test_changed_inventory_invalid(self):
        m=manifest();m['block_details'][2]['b_stories']=[{'Different':100}]*2
        with self.assertRaises(ValueError):stats.evaluate(m,plan())
    def test_bad_numbers_invalid(self):
        for value in (float('nan'),float('inf'),0,-1,True):
            m=manifest();m['block_details'][0]['a_scores'][0]=value
            with self.assertRaises(ValueError):stats.evaluate(m,plan())
    def test_primary_frozen(self):
        p=plan();p['primary']=['Unknown']
        with self.assertRaises(ValueError):stats.evaluate(manifest(),p)
    def test_null_equivalence_and_precision(self):
        a=manifest(0);a.update(mode='aa',session_id='a')
        b=manifest(0,noise=.0002);b.update(mode='aa',session_id='b')
        self.assertTrue(stats.calibrate([a,b],.1,.1,.9)['gate_pass'])
        b=manifest(0,noise=.03);b.update(mode='aa',session_id='b')
        self.assertFalse(stats.calibrate([a,b],.1,.1,.9)['gate_pass'])
    def test_calibration_rejects_surface_change(self):
        a=dict(manifest(0),session_id='one',mode='aa',capture_environment={'host_name':'h','display':{'mode':'headless'}})
        b=dict(manifest(0),session_id='two',mode='aa',capture_environment={'host_name':'h','display':{'mode':'x11','display':':1','viewport':'1500x1000','gpu_renderer':'NVIDIA'}})
        with self.assertRaisesRegex(ValueError,'configuration changed'):stats.calibrate([a,b],.1,.1,.9)
        b['capture_environment']['display']=dict(a['capture_environment']['display'])
        self.assertTrue(stats.calibrate([a,b],.1,.1,.9)['gate_pass'])
    def test_same_null_session_rejected(self):
        m=manifest(0);m.update(mode='aa',session_id='a')
        with self.assertRaises(ValueError):stats.calibrate([m,m],.1,.1)
    def test_serial_dependence_inconclusive(self):
        m=manifest();p=plan();p['max_abs_lag1']=.4
        for i,row in enumerate(m['block_details']):row['b_scores']=[100*math.exp(.001*i)]*2
        self.assertEqual('INCONCLUSIVE',stats.evaluate(m,p)['verdict'])


class BudgetTest(unittest.TestCase):
    def packet(self):
        return dict(suite_workload_count=20,workloads=[dict(name='Story',basis='paired-oracle',
                    score_gain_upper_pct=2,artifact_sha256='a'*64,source_revision='b'*40)],
                    confidence=.5,acceptance_probability=.8,engineering_hours=3,measurement_hours=2,
                    calibrated_mde_pct=.2,minimum_effect_pct=.1)
    def test_full_stack_cannot_be_score_bound(self):
        p=self.packet();p['workloads'][0]['basis']='CPU-share'
        with self.assertRaises(ValueError):opportunity_budget.rank(p)
    def test_unmeasurable_idea_stops(self):self.assertFalse(opportunity_budget.rank(self.packet())['viable_with_budget'])
    def test_cross_story_benefit_combines(self):
        p=self.packet();p['workloads']=[dict(p['workloads'][0],name=str(i)) for i in range(10)]
        self.assertTrue(opportunity_budget.rank(p)['viable_with_budget'])
        self.assertLess(opportunity_budget.rank(p)['aggregate_score_upper_pct'],2)


class TraceTest(unittest.TestCase):
    def values(self):
        trace={'metadata':{'interval_kind':'exact-scored'},'traceEvents':[
            dict(name='start',ts=0,pid=1,tid=1),dict(name='work',ts=2,dur=3,pid=1,tid=1),
            dict(name='end',ts=10,pid=1,tid=1)]}
        path=dict(events=[0,1,2],start_mark='start',end_mark='end',removable_event_indices=[1],
                  edges=[dict(kind='thread-order')]*2)
        return trace,path
    def test_real_path_duration(self):self.assertEqual(30,latency_evidence.trace_path(*self.values())['latency_headroom_pct'])
    def test_unrelated_threads_not_path(self):
        trace,path=self.values();trace['traceEvents'][1]['tid']=2
        with self.assertRaises(ValueError):latency_evidence.trace_path(trace,path)
    def test_overlap_not_serial_path(self):
        trace,path=self.values();trace['traceEvents'][1]['dur']=20
        with self.assertRaises(ValueError):latency_evidence.trace_path(trace,path)


class FleetTest(unittest.TestCase):
    def test_empty_never_passes(self):self.assertEqual('INVALID',pinpoint_measure.parse_and_analyze_results('')['verdict'])
    def test_unknown_arm_rejected(self):
        data='\n'.join(map(json.dumps,[{'guid':'x','values':['unknown']},{'name':'Score','unit':'unitless_biggerIsBetter','diagnostics':{'labels':'x'},'running':[1,0,0,20]}]))
        with self.assertRaises(ValueError):pinpoint_measure.parse_and_analyze_results(data)
    def test_clear_fleet_gain_and_missing_inventory(self):
        p={'statistics':plan(),'identity':{'workloads':['Story']}}
        data={'Score':dict(base=[100]*32,exp=[102]*32,unit='unitless_biggerIsBetter'),
              'Story':dict(base=[100]*32,exp=[98]*32,unit='ms_smallerIsBetter')}
        self.assertEqual('IMPROVEMENT',pinpoint_measure.fleet_decision(data,p)['verdict'])
        del data['Story'];self.assertEqual('INVALID',pinpoint_measure.fleet_decision(data,p)['verdict'])
    def test_immutable_request_required(self):
        with self.assertRaises(ValueError):pinpoint_measure.start_pinpoint_job('https://crrev.com/c/1')


class IntegrationMappingTest(unittest.TestCase):
    def test_isolated_candidate_can_integrate_after_another_candidate(self):
        import campaign
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            def git(*args):return subprocess.run(['git','-C',tmp,*args],check=True,capture_output=True,text=True).stdout.strip()
            git('init','-q');git('config','user.name','Test');git('config','user.email','test@example.invalid')
            (root/'a.cc').write_text('int a = 0;\n');(root/'b.cc').write_text('const char* b = "one word";\n')
            git('add','.');git('commit','-qm','baseline');base=git('rev-parse','HEAD')
            (root/'b.cc').write_text('const char* b = "two words";\n');git('commit','-qam','isolated');isolated=git('rev-parse','HEAD')
            git('checkout','-q','--detach',base)
            (root/'a.cc').write_text('int a = 1;\n');git('commit','-qam','first candidate')
            git('cherry-pick',isolated);integrated=git('rev-parse','HEAD')
            self.assertNotEqual(isolated,integrated)
            self.assertEqual(isolated,campaign.integration_mapping(root,isolated,integrated,base)['isolated_candidate_sha'])
            (root/'b.cc').write_text('const char* b = "two  words";\n');git('commit','--amend','-qam','changed semantics')
            with self.assertRaises(ValueError):campaign.integration_mapping(root,isolated,git('rev-parse','HEAD'),base)



class HostObservationTest(unittest.TestCase):
    def rows(self):
        return [dict(block=1,before=dict(monotonic_ns=1,online_cpus='0-3',cpu_affinity=[0,1],
                    counters={'/thermal_throttle/core_throttle_count':'0'}),
                    after=dict(monotonic_ns=2,online_cpus='0-3',cpu_affinity=[0,1],
                    counters={'/thermal_throttle/core_throttle_count':'0'}))]
    def test_stable_observations(self):measurement_host.validate_observations(self.rows(),1)
    def test_throttling_invalidates_run(self):
        rows=self.rows();rows[0]['after']['counters']['/thermal_throttle/core_throttle_count']='1'
        with self.assertRaises(ValueError):measurement_host.validate_observations(rows,1)
    def test_incomplete_observations_invalid(self):
        with self.assertRaises(ValueError):measurement_host.validate_observations(self.rows(),2)

if __name__=='__main__':unittest.main()
