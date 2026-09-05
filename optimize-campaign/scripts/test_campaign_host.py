#!/usr/bin/env python3
"""Forwarding of campaign commands to the test machine that owns the ledger."""
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import campaign_host as host


class PlanForwardTest(unittest.TestCase):
    def test_uploads_inputs_and_fetches_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            proposal = pathlib.Path(tmp) / "paths.json"
            proposal.write_text('{"paths": []}')
            argv = ["--dir", "/local/camp", "decompose", "--opp", "3",
                    "--children", str(proposal), "--gate-skeptic=" + str(proposal),
                    "--out", "/local/report.json"]
            remote_argv, uploads, downloads = host.plan_forward(argv, "/srv/src/.agents/campaigns/c")
        self.assertNotIn("--dir", remote_argv)
        self.assertEqual("decompose", remote_argv[0])
        self.assertEqual(2, len(uploads))
        self.assertTrue(all(r.startswith("/srv/src/.agents/campaigns/c/inbox/") for _, r in uploads))
        self.assertIn("--gate-skeptic=" + uploads[1][1], remote_argv)
        self.assertEqual([("/srv/src/.agents/campaigns/c/outbox/report.json", "/local/report.json")], downloads)
        self.assertIn("/srv/src/.agents/campaigns/c/outbox/report.json", remote_argv)
        self.assertIn("3", remote_argv)

    def test_host_summary_replaces_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = pathlib.Path(tmp) / "aa.json"
            summary.write_text(json.dumps({"host_summary_path": "/srv/src/.agents/campaigns/c/measurements/aa.json"}))
            remote_argv, uploads, _ = host.plan_forward(
                ["calibrate", "--manifest", str(summary)], "/srv/src/.agents/campaigns/c")
        self.assertEqual([], uploads)
        self.assertEqual(["calibrate", "--manifest", "/srv/src/.agents/campaigns/c/measurements/aa.json"], remote_argv)

    def test_non_file_values_pass_through(self):
        remote_argv, uploads, downloads = host.plan_forward(
            ["advance", "--opp", "7", "--to", "sized", "--notes", "no such file"], "/r")
        self.assertEqual(["advance", "--opp", "7", "--to", "sized", "--notes", "no such file"], remote_argv)
        self.assertEqual(([], []), (uploads, downloads))

    def test_strip_host_args(self):
        argv, h, src = host.strip_host_args(["--host", "linux", "--remote-src=/srv/src", "status", "--print"])
        self.assertEqual(["status", "--print"], argv)
        self.assertEqual(("linux", "/srv/src"), (h, src))

    def test_local_host_detection(self):
        self.assertTrue(host.is_local_host(None))
        self.assertTrue(host.is_local_host("localhost"))
        with mock.patch.object(host.socket, "gethostname", return_value="linux.lan"):
            self.assertTrue(host.is_local_host("linux"))
            self.assertTrue(host.is_local_host("pmeenan@linux"))
            self.assertFalse(host.is_local_host("otherbox"))

    def test_pointer_roundtrip_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(host.load_pointer(tmp))
            host.save_pointer(tmp, "linux", "/srv/src", "camp")
            self.assertEqual({"host": "linux", "remote_src": "/srv/src", "name": "camp"}, host.load_pointer(tmp))
            host.pointer_path(tmp).write_text('{"host": "linux"}')
            with self.assertRaises(host.HostError):
                host.load_pointer(tmp)

    def test_rewrite_paths_maps_prefix_recursively(self):
        value = {"manifest": "/local/out/x.json", "rows": [{"artifact": "/local/out/a/b.json"}, "/elsewhere"]}
        out = host.rewrite_paths(value, "/local/out", "/srv/src/scratch/remote_profile_1")
        self.assertEqual("/srv/src/scratch/remote_profile_1/x.json", out["manifest"])
        self.assertEqual("/srv/src/scratch/remote_profile_1/a/b.json", out["rows"][0]["artifact"])
        self.assertEqual("/elsewhere", out["rows"][1])


if __name__ == "__main__":
    unittest.main()
