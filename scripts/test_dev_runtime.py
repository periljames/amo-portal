from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("dev_runtime.py")
SPEC = importlib.util.spec_from_file_location("dev_runtime", SCRIPT)
assert SPEC and SPEC.loader
DEV_RUNTIME = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = DEV_RUNTIME
SPEC.loader.exec_module(DEV_RUNTIME)


class DevRuntimePortTests(unittest.TestCase):
    def test_windows_netstat_parser_returns_only_listeners_for_requested_port(self) -> None:
        sample = """
  TCP    127.0.0.1:8080         0.0.0.0:0              LISTENING       1111
  TCP    0.0.0.0:5173           0.0.0.0:0              LISTENING       2222
  TCP    [::]:8080              [::]:0                 LISTENING       1111
  TCP    127.0.0.1:8080         127.0.0.1:60000        ESTABLISHED     3333
"""
        self.assertEqual(DEV_RUNTIME._parse_windows_netstat(sample, 8080), [1111])
        self.assertEqual(DEV_RUNTIME._parse_windows_netstat(sample, 5173), [2222])
        self.assertEqual(DEV_RUNTIME._parse_windows_netstat(sample, 8090), [])

    def test_replace_running_is_explicit_cli_option(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--replace-running", result.stdout)
        self.assertIn("Terminate processes currently listening", result.stdout)


if __name__ == "__main__":
    unittest.main()
