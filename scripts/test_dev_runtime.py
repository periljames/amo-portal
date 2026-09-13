from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("dev_runtime.py")

# Keep this regression test dependency-free so the routing workflow can run it
# before installing backend requirements.
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.dotenv_values = lambda _path: {}
sys.modules.setdefault("dotenv", dotenv_stub)

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
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"--replace-running"', source)
        self.assertIn("_replace_occupied_ports", source)
        self.assertIn("Refusing to terminate an unknown listener", source)


if __name__ == "__main__":
    unittest.main()
