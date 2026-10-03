from contextlib import ExitStack, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import json
import unittest
from unittest.mock import patch
import runner


class RunnerTests(unittest.TestCase):
    def test_explicit_tier_and_model_flags_override_global_defaults(self):
        for role in runner.ROLES:
            for tier in ("fast", "default"):
                cmd = runner.command("codex.exe", role, {"service_tier": tier, "model": "gpt-6-luna", "model_reasoning_effort": "xhigh"}, Path("workspace"), Path("result"))
                self.assertIn('service_tier="' + tier + '"', cmd)
                self.assertIn('agents.enabled=false', cmd)
                self.assertEqual(cmd[cmd.index("--sandbox") + 1], "workspace-write" if role == "worker" else "read-only")
                self.assertEqual(cmd[cmd.index("--model") + 1], "gpt-6-luna")

    def test_nested_runner_is_refused(self):
        with patch.dict(os.environ, {"CODEX_ORCHESTRATION_CHILD": "1"}):
            with self.assertRaises(ValueError):
                runner.run(Path("none"), "worker", Path("none"), "task", "unused", 1)

    def test_three_active_slots_prevent_fourth_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / "manifest.json").write_text("{}")
            with ExitStack() as stack:
                for number in range(3):
                    stack.enter_context(runner.file_lock(state / f"slots/{number}.lock"))
                with self.assertRaises(TimeoutError), patch("subprocess.Popen") as process:
                    runner.run(state, "worker", state, "task", "unused", 0.1)
                process.assert_not_called()

    def test_no_installed_manifest_means_no_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError), patch("subprocess.Popen") as process:
                runner.run(Path(temporary), "worker", Path(temporary), "task", "unused", 1)
            process.assert_not_called()

    def test_invalid_tier_is_not_silently_downgraded(self):
        with self.assertRaises(ValueError):
            runner.command("codex.exe", "worker", {"service_tier": "ultrafast"}, Path("."), Path("result"))

    def test_timeout_preserves_logs_and_releases_slot(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            (state / "manifest.json").write_text("{}")
            (state / "agents").mkdir()
            (state / "agents/worker.toml").write_text('model="fixture"\nmodel_reasoning_effort="low"\nservice_tier="default"\ndeveloper_instructions="task"')
            cmd = [sys.executable, "-u", "-c", "import time; print('before timeout', flush=True); time.sleep(30)"]
            with patch("runner.command", return_value=cmd), redirect_stdout(io.StringIO()):
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.run(state, "worker", state, "task", "unused", 1)
            run_dir = next((state / "runs").iterdir())
            self.assertIn(b"before timeout", (run_dir / "events.jsonl").read_bytes())
            self.assertEqual(json.loads((run_dir / "status.json").read_text())["status"], "interrupted")
            with runner.file_lock(state / "slots/0.lock"):
                pass
