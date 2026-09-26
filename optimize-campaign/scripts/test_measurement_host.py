#!/usr/bin/env python3
"""Rendering-surface identity, VT ownership and GPU contention checks."""
import pathlib
import tempfile
import unittest
from unittest import mock

import measurement_host as host


class DisplayEnvironmentTest(unittest.TestCase):
    def test_headless_records_mode_and_vt(self):
        with mock.patch.object(host, 'active_vt', return_value='tty2'):
            env = host.display_environment(None)
        self.assertEqual('headless', env['mode'])
        self.assertEqual('tty2', env['active_vt'])
        self.assertEqual(['--headless'], host.crossbench_display_args(env))
        self.assertNotIn('DISPLAY', host.subprocess_env(env, {'DISPLAY': ':0'}))

    def test_missing_x_server_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(host, 'X11_SOCKET_DIR', tmp), \
                mock.patch.object(host, 'active_vt', return_value='tty9'):
            with self.assertRaisesRegex(RuntimeError, 'not running'):
                host.display_environment(':1', 9)

    def test_wrong_vt_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(host, 'X11_SOCKET_DIR', tmp), \
                mock.patch.object(host, 'active_vt', return_value='tty2'):
            (pathlib.Path(tmp) / 'X1').write_text('')
            with self.assertRaisesRegex(RuntimeError, 'tty9'):
                host.display_environment(':1', 9)

    def test_x11_surface_uses_fixed_viewport_and_display(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(host, 'X11_SOCKET_DIR', tmp), \
                mock.patch.object(host, 'active_vt', return_value='tty9'):
            (pathlib.Path(tmp) / 'X1').write_text('')
            env = host.display_environment(':1', 9)
        self.assertEqual('x11', env['mode'])
        self.assertEqual(['--viewport=1500x1000'], host.crossbench_display_args(env))
        self.assertEqual(':1', host.subprocess_env(env, {})['DISPLAY'])

    def test_bad_display_name_rejected(self):
        with self.assertRaises(ValueError):
            host.display_environment('display-one')

    def test_software_renderer_rejected_on_x11(self):
        env = {'mode': 'x11', 'display': ':1', 'viewport': '1500x1000'}
        with mock.patch.object(host, 'probe_gpu_renderer', return_value='ANGLE (Google, Vulkan (SwiftShader Device))'):
            with self.assertRaisesRegex(RuntimeError, 'not driving'):
                host.attest_renderer(env, '/bin/false')

    def test_software_renderer_recorded_for_headless(self):
        env = host.display_environment.__wrapped__(None) if hasattr(host.display_environment, '__wrapped__') else {'mode': 'headless', 'display': None, 'viewport': 'headless'}
        with mock.patch.object(host, 'probe_gpu_renderer', return_value='SwiftShader driver'):
            attested = host.attest_renderer(env, '/bin/false')
        self.assertEqual('SwiftShader driver', attested['gpu_renderer'])
        self.assertEqual({'mode': 'headless', 'display': None, 'viewport': 'headless', 'gpu_renderer': 'SwiftShader driver'},
                         host.display_identity(attested))


class HostObservationTest(unittest.TestCase):
    def rows(self):
        gpu = {'gpus': [], 'compute_apps': [{'pid': 7, 'process_name': '/usr/bin/ollama', 'used_memory_mib': 10, 'foreign': True}]}
        return [dict(block=1,
                     before=dict(monotonic_ns=1, online_cpus='0-3', cpu_affinity=[0, 1], active_vt='tty9', gpu=gpu, counters={}),
                     after=dict(monotonic_ns=2, online_cpus='0-3', cpu_affinity=[0, 1], active_vt='tty9', gpu=gpu, counters={}))]

    def test_stable_rows_pass_and_report_foreign_apps(self):
        rows = self.rows()
        host.validate_observations(rows, 1)
        self.assertEqual(['/usr/bin/ollama'], host.foreign_gpu_apps(rows))

    def test_vt_change_invalidates(self):
        rows = self.rows(); rows[0]['after']['active_vt'] = 'tty2'
        with self.assertRaisesRegex(ValueError, 'active_vt'):
            host.validate_observations(rows, 1)

    def test_foreign_gpu_process_change_invalidates(self):
        rows = self.rows(); rows[0]['after']['gpu'] = {'gpus': [], 'compute_apps': []}
        with self.assertRaisesRegex(ValueError, 'foreign GPU'):
            host.validate_observations(rows, 1)


if __name__ == '__main__':
    unittest.main()


class HostExclusiveTest(unittest.TestCase):
    def setUp(self):
        import os
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name) / "hostlock"
        self.dir.mkdir()
        self.env = mock.patch.dict(os.environ, {"HOSTLOCK_DIR": str(self.dir)})
        self.env.start()
        os.environ.pop("HOSTLOCK_HELD", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_disabled_without_lock_dir(self):
        import os
        with mock.patch.dict(os.environ, {"HOSTLOCK_DIR": str(self.dir / "missing")}):
            with host.host_exclusive():
                self.assertNotIn("HOSTLOCK_HELD", os.environ)

    def test_waits_for_shared_holder_and_closes_gate(self):
        import subprocess, time
        holder = subprocess.Popen(["flock", "-s", str(self.dir / "main.lock"), "sleep", "2"])
        time.sleep(0.3)
        start = time.monotonic()
        with host.host_exclusive("test"):
            self.assertGreaterEqual(time.monotonic() - start, 1.2)
            gate_probe = subprocess.run(["flock", "-x", "-n", str(self.dir / "gate.lock"), "true"])
            self.assertNotEqual(0, gate_probe.returncode)
        holder.wait()
        gate_probe = subprocess.run(["flock", "-x", "-n", str(self.dir / "gate.lock"), "true"])
        self.assertEqual(0, gate_probe.returncode)

    def test_nested_and_child_holds_do_not_relock(self):
        import os
        with host.host_exclusive("outer"):
            self.assertTrue(os.environ["HOSTLOCK_HELD"].startswith("exclusive:"))
            with host.host_exclusive("inner"):
                pass
        self.assertNotIn("HOSTLOCK_HELD", os.environ)

    def test_refuses_inside_shared_hold(self):
        import os
        with mock.patch.dict(os.environ, {"HOSTLOCK_HELD": "shared:1"}):
            with self.assertRaises(RuntimeError):
                with host.host_exclusive():
                    pass
