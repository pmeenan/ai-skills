#!/usr/bin/env python3
"""Transactional tuning tests against in-memory sysfs, never the real host."""
import contextlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock
import tune_benchmark_host as host


class TuneBenchmarkHostTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=str(pathlib.Path(self.tmp.name)/'state.json')
        self.values={host.SYS_SMT:'on',host.SYS_NO_TURBO:'0',host.PROC_ASLR:'2',host.PROC_NMI:'1'}
        self.policies=['/sys/test/policy0','/sys/test/policy1']
        for i,p in enumerate(self.policies):
            self.values.update({p+'/scaling_governor':'powersave',p+'/energy_performance_preference':'balance_performance',
                                p+'/scaling_min_freq':str(800+i*100),p+'/scaling_max_freq':str(5000-i*100)})
        self.original=dict(self.values)
        for name,kwargs in [
            ('can_tune_host',{'return_value':True}),
            ('get_current_state',{'side_effect':lambda:dict(self.values)}),
            ('observe',{'return_value':{}}),
            ('read_sys_file',{'side_effect':lambda p:'3000' if p.endswith('/base_frequency') else self.values.get(p)}),
            ('write_sys_file',{'side_effect':self.write}),
            ('lease',{'side_effect':contextlib.nullcontext}),
        ]:
            patch=mock.patch.object(host,name,**kwargs);patch.start();self.addCleanup(patch.stop)

    def write(self,p,v):
        if p.endswith('/scaling_max_freq') and int(v)<int(self.values[p.replace('max','min')]):
            raise RuntimeError('max crossed min')
        if p.endswith('/scaling_min_freq') and int(v)>int(self.values[p.replace('min','max')]):
            raise RuntimeError('min crossed max')
        self.values[p]=str(v)

    def test_all_policies_restored_exactly(self):
        with host.tuned_host_context(self.path):
            for p in self.policies:
                self.assertEqual('3000',self.values[p+'/scaling_min_freq'])
                self.assertEqual('3000',self.values[p+'/scaling_max_freq'])
        self.assertEqual(self.original,self.values)
        self.assertFalse(pathlib.Path(self.path).exists())

    def test_failure_restores(self):
        with self.assertRaisesRegex(RuntimeError,'benchmark failed'):
            with host.tuned_host_context(self.path): raise RuntimeError('benchmark failed')
        self.assertEqual(self.original,self.values)

    def test_privilege_failure_is_not_silent(self):
        host.can_tune_host.return_value=False
        with self.assertRaisesRegex(RuntimeError,'requires root'):
            host.enable_tuning(self.path)
        self.assertEqual(self.original,self.values)

    def test_never_overwrite_recovery_record(self):
        pathlib.Path(self.path).write_text('old recovery')
        with self.assertRaises(FileExistsError): host.enable_tuning(self.path)
        self.assertEqual('old recovery',pathlib.Path(self.path).read_text())
        self.assertEqual(self.original,self.values)

    def test_no_guessed_restore_defaults(self):
        pathlib.Path(self.path).write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'guessed'): host.disable_tuning(self.path)

    def test_failed_restore_retains_record(self):
        host.enable_tuning(self.path)
        host.write_sys_file.side_effect=RuntimeError('readback failed')
        with self.assertRaises(RuntimeError): host.disable_tuning(self.path)
        self.assertTrue(pathlib.Path(self.path).exists())

    def test_high_minimum_does_not_cross_maximum(self):
        for p in self.policies: self.values[p+'/scaling_min_freq']='4000'
        original=dict(self.values)
        with host.tuned_host_context(self.path): pass
        self.assertEqual(original,self.values)

    def test_failed_enable_rolls_back(self):
        def fail(p,v):
            if p==host.PROC_NMI and v=='0': raise RuntimeError('unsupported')
            self.write(p,v)
        host.write_sys_file.side_effect=fail
        with self.assertRaises(RuntimeError): host.enable_tuning(self.path)
        self.assertEqual(self.original,self.values)
        self.assertFalse(pathlib.Path(self.path).exists())

    def test_vt_and_gpu_lock_are_restored_in_reverse(self):
        calls=[]
        vt={'active':'tty2'}
        def priv(cmd,check=True):
            calls.append(cmd)
            if cmd[0]=='chvt': vt['active']=f'tty{cmd[1]}'
            return mock.Mock(returncode=0,stderr='',stdout='')
        with mock.patch.object(host,'run_priv',side_effect=priv), \
                mock.patch.object(host,'active_vt',side_effect=lambda:vt['active']):
            with host.tuned_host_context(self.path,disable_aslr=False,vt=9,gpu_clock_mhz=1365) as report:
                self.assertEqual('tty9',vt['active'])
                self.assertEqual('2',self.values[host.PROC_ASLR])
                self.assertEqual(1365,report['extras']['gpu_clock_lock_mhz'])
        self.assertEqual('tty2',vt['active'])
        self.assertEqual(self.original,self.values)
        self.assertIn(['nvidia-smi','--lock-gpu-clocks','1365,1365'],calls)
        self.assertIn(['nvidia-smi','--reset-gpu-clocks'],calls)
        self.assertLess(calls.index(['nvidia-smi','--reset-gpu-clocks']),calls.index(['chvt','2']))

    def test_paused_service_restarted_only_if_it_was_running(self):
        calls=[]
        def priv(cmd,check=True):
            calls.append(cmd); return mock.Mock(returncode=0,stderr='',stdout='')
        with mock.patch.object(host,'run_priv',side_effect=priv), \
                mock.patch.object(host,'service_is_active',side_effect=lambda n: n=='ollama'):
            with host.tuned_host_context(self.path,pause=['ollama','absent']) as report:
                self.assertEqual(['ollama'],report['extras']['paused_services'])
        self.assertIn(['systemctl','stop','ollama'],calls)
        self.assertIn(['systemctl','start','ollama'],calls)
        self.assertNotIn(['systemctl','stop','absent'],calls)
        self.assertNotIn(['systemctl','start','absent'],calls)
        self.assertEqual(self.original,self.values)

    def test_governor_restored_before_epp(self):
        order=[]
        original_write=host.write_sys_file.side_effect
        def write(p,v):
            order.append(p); original_write(p,v)
        host.write_sys_file.side_effect=write
        with host.tuned_host_context(self.path): pass
        p=self.policies[0]
        restore=order[len(order)//2:]
        self.assertLess(restore.index(p+'/scaling_governor'),restore.index(p+'/energy_performance_preference'))

    def test_keep_aslr_leaves_randomization(self):
        with host.tuned_host_context(self.path,disable_aslr=False):
            self.assertEqual('2',self.values[host.PROC_ASLR])
        with host.tuned_host_context(self.path):
            self.assertEqual('0',self.values[host.PROC_ASLR])
        self.assertEqual(self.original,self.values)

if __name__=='__main__': unittest.main()
