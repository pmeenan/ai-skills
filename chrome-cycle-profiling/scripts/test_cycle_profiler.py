"""Compile and exercise the real probe header using mocked PMU/TID reads."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest


class ProbeTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('g++'), 'C++ compiler unavailable')
    def test_counter_and_accounting_invariants(self):
        resources=pathlib.Path(__file__).resolve().parents[1]/'resources'
        with tempfile.TemporaryDirectory() as tmp:
            executable=str(pathlib.Path(tmp)/'probe-test')
            subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-unknown-pragmas',
                            str(resources/'cycle_profiler_test.cc'),'-o',executable],check=True,capture_output=True)
            result=subprocess.run([executable],check=True,capture_output=True,text=True)
            self.assertIn('gettid syscalls=0',result.stdout)
            self.assertIn('PASS rejected aliased',result.stdout)
            self.assertIn('PASS rejected subsampled',result.stdout)

if __name__=='__main__':unittest.main()
