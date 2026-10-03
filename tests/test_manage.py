import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("manage", Path(__file__).resolve().parents[1] / "manage.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex orchestration 測試 ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "global"
        self.home.mkdir()
        self.package = Path(self.temp.name) / "package"
        self.package.mkdir()
        shutil.copy(m.PACKAGE / "settings.json", self.package)
        shutil.copy(m.PACKAGE / "runner.py", self.package)
        shutil.copytree(m.PACKAGE / "prompts", self.package / "prompts")
        self.config = b'model = "original"\r\n[plugins."token-optimizer@token-optimizer"]\r\nenabled = true\r\n'
        (self.home / "config.toml").write_bytes(self.config)

    def install(self):
        with m.lock(self.home):
            m.recover(self.home)
            m.transaction(self.home, m.install_plan(self.home, self.package))

    def uninstall(self):
        with m.lock(self.home):
            m.recover(self.home)
            m.transaction(self.home, m.uninstall_plan(self.home))

    def test_roundtrip_preserves_existing_bytes_and_unrelated_files(self):
        for content in (None, b"", "繁體中文\r\n日本語\r\n".encode(), b"\xef\xbb\xbf# no final newline"):
            with self.subTest(content=content):
                m.atomic_write(self.home / "AGENTS.md", content)
                (self.home / "hooks.json").write_bytes(b'{"unrelated":true}')
                self.install()
                self.assertEqual((self.home / "config.toml").read_bytes(), self.config)
                self.uninstall()
                self.assertEqual(m.read(self.home / "AGENTS.md"), content)
                self.assertEqual((self.home / "hooks.json").read_bytes(), b'{"unrelated":true}')
                self.assertFalse(any((self.home / "codex-orchestration/agents").glob("*.toml")))
                self.assertEqual((self.home / "config.toml").read_bytes(), self.config)

    def test_idempotent_install_and_uninstall(self):
        self.install()
        paths = [m.safe_path(self.home, p) for p in m.MANAGED]
        snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        self.install()
        self.assertEqual(snapshot, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})
        self.uninstall()
        self.assertEqual(m.uninstall_plan(self.home), {})

    def test_models_efforts_and_individual_fast_are_independent(self):
        settings = m.settings(self.package)
        settings["researcher"]["fast"] = True
        settings["worker"]["model"] = "gpt-6-luna"
        (self.package / "settings.json").write_bytes(m.json_bytes(settings))
        self.install()
        for role in m.ROLES:
            d = tomllib.loads((self.home / f"codex-orchestration/agents/{role}.toml").read_text(encoding="utf-8"))
            self.assertEqual(d["name"], role)
            self.assertEqual(d["model"], settings[role]["model"])
            self.assertEqual(d["model_reasoning_effort"], settings[role]["effort"])
            self.assertEqual(d["service_tier"], "fast" if role == "researcher" else "default")

    def test_reinstall_updates_managed_roles_preserving_later_user_instructions(self):
        self.install()
        with (self.home / "AGENTS.md").open("ab") as stream:
            stream.write(b"\n# New user policy\n")
        settings = m.settings(self.package)
        settings["explorer"]["fast"] = True
        (self.package / "settings.json").write_bytes(m.json_bytes(settings))
        self.install()
        self.assertIn(b'service_tier = "fast"', (self.home / "codex-orchestration/agents/explorer.toml").read_bytes())
        self.uninstall()
        self.assertEqual((self.home / "AGENTS.md").read_bytes(), b"\n# New user policy\n")

    def test_existing_native_roles_remain_unchanged(self):
        (self.home / "agents").mkdir()
        path = self.home / "agents/custom.toml"
        path.write_bytes(b'name = "explorer"\n')
        self.install()
        self.uninstall()
        self.assertEqual(path.read_bytes(), b'name = "explorer"\n')
        self.assertIsNone(m.read(self.home / "AGENTS.md"))

    def test_native_agents_config_is_preserved_but_instruction_override_is_reported(self):
        for config in (b"[agents]\nenabled = false\n", b'[agents.explorer]\nconfig_file="x.toml"\n'):
            (self.home / "config.toml").write_bytes(config)
            self.install()
            self.uninstall()
            self.assertEqual((self.home / "config.toml").read_bytes(), config)
        (self.home / "config.toml").write_bytes(self.config)
        (self.home / "AGENTS.override.md").write_bytes(b"override")
        with self.assertRaises(m.Conflict):
            m.install_plan(self.home, self.package)

    def test_invalid_settings_fail_before_install(self):
        valid = m.settings(self.package)
        for field, value in (("fast", "false"), ("model", ""), ("effort", "maximum")):
            data = copy.deepcopy(valid)
            data["worker"][field] = value
            (self.package / "settings.json").write_bytes(m.json_bytes(data))
            with self.assertRaises(m.Conflict):
                m.install_plan(self.home, self.package)
            self.assertIsNone(m.read(self.home / "codex-orchestration/agents/worker.toml"))

    def test_existing_filename_cannot_be_overwritten_even_if_name_differs(self):
        (self.home / "codex-orchestration/agents").mkdir(parents=True)
        (self.home / "codex-orchestration/agents/explorer.toml").write_bytes(b'name = "another_role"\n')
        with self.assertRaises(m.Conflict):
            m.install_plan(self.home, self.package)

    def test_instruction_budget_is_checked_without_truncating_existing_text(self):
        (self.home / "config.toml").write_bytes(b"project_doc_max_bytes = 64\n")
        (self.home / "AGENTS.md").write_bytes(b"User text")
        with self.assertRaises(m.Conflict):
            m.install_plan(self.home, self.package)
        self.assertEqual((self.home / "AGENTS.md").read_bytes(), b"User text")

    def test_lock_prevents_concurrent_install(self):
        with m.lock(self.home):
            with self.assertRaises(m.Conflict), m.lock(self.home):
                pass

    def test_external_edits_during_transaction_are_preserved(self):
        real = m.atomic_write
        def concurrent_write(path, data):
            real(path, data)
            if path.name == "explorer.toml":
                real(self.home / "codex-orchestration/agents/researcher.toml", b"user edit")
        with m.lock(self.home), patch.object(m, "atomic_write", concurrent_write):
            with self.assertRaises(m.Conflict):
                m.transaction(self.home, m.install_plan(self.home, self.package))
        self.assertEqual((self.home / "codex-orchestration/agents/researcher.toml").read_bytes(), b"user edit")
        self.assertTrue((self.home / m.STATE / "pending.json").exists())

    def test_manual_role_changes_block_update_but_uninstall_backs_them_up(self):
        self.install()
        path = self.home / "codex-orchestration/agents/worker.toml"
        edited = path.read_bytes() + b"\n# Manual customization\n"
        path.write_bytes(edited)
        with self.assertRaises(m.Conflict):
            m.install_plan(self.home, self.package)
        self.uninstall()
        backups = list((self.home / m.STATE / "backups").glob("*.json"))
        self.assertTrue(any(m.decode(json.loads(p.read_text(encoding="utf-8")).get("codex-orchestration/agents/worker.toml", {}).get("before")) == edited for p in backups))

    def test_edited_routing_block_can_be_removed_without_losing_outside_text(self):
        (self.home / "AGENTS.md").write_bytes(b"before")
        self.install()
        path = self.home / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(b"Global agent delegation", b"User customization") + b"after")
        self.uninstall()
        self.assertTrue(path.read_bytes().startswith(b"before"))
        self.assertTrue(path.read_bytes().endswith(b"after"))
        self.assertNotIn(m.BEGIN, path.read_bytes())

    def test_missing_markers_stop_uninstall_without_removing_roles(self):
        self.install()
        path = self.home / "AGENTS.md"
        path.write_bytes(path.read_bytes().replace(m.END, b"changed"))
        with self.assertRaises(m.Conflict):
            m.uninstall_plan(self.home)
        self.assertTrue((self.home / "codex-orchestration/agents/explorer.toml").exists())

    def test_write_failure_rolls_back(self):
        real = m.atomic_write
        failed = False

        def fail_once(path, data):
            nonlocal failed
            if path.name == "researcher.toml" and not failed:
                failed = True
                raise OSError("simulated disk failure")
            return real(path, data)

        with m.lock(self.home), patch.object(m, "atomic_write", fail_once):
            with self.assertRaises(OSError):
                m.transaction(self.home, m.install_plan(self.home, self.package))
        self.assertIsNone(m.read(self.home / "codex-orchestration/agents/explorer.toml"))
        self.assertIsNone(m.read(self.home / "AGENTS.md"))
        self.assertIsNone(m.load_manifest(self.home))

    def test_interrupted_transaction_recovery(self):
        with m.lock(self.home):
            entry = {"codex-orchestration/agents/explorer.toml": {"before": None, "after": m.encode(b"partial")}}
            m.atomic_write(self.home / m.STATE / "pending.json", m.json_bytes(entry))
            m.atomic_write(self.home / "codex-orchestration/agents/explorer.toml", b"partial")
            m.recover(self.home)
        self.assertIsNone(m.read(self.home / "codex-orchestration/agents/explorer.toml"))

    def test_recovery_does_not_overwrite_external_edits(self):
        with m.lock(self.home):
            entry = {"codex-orchestration/agents/explorer.toml": {"before": None, "after": m.encode(b"partial")}}
            m.atomic_write(self.home / m.STATE / "pending.json", m.json_bytes(entry))
            m.atomic_write(self.home / "codex-orchestration/agents/explorer.toml", b"user edit")
            with self.assertRaises(m.Conflict):
                m.recover(self.home)
            self.assertEqual((self.home / "codex-orchestration/agents/explorer.toml").read_bytes(), b"user edit")

    def test_dry_run_is_read_only_and_global_only(self):
        with patch.dict(os.environ, {"CODEX_HOME": str(self.home)}), patch.object(m, "PACKAGE", self.package), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(["install", "--dry-run"]), 0)
        self.assertEqual([p.name for p in self.home.iterdir()], ["config.toml"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            m.main(["install", "--project"])

    @unittest.skipUnless(os.name == "nt", "Windows launchers")
    def test_one_click_launchers_install_status_uninstall(self):
        env = dict(os.environ, CODEX_HOME=str(self.home), CODEX_ORCHESTRATION_NO_PAUSE="1")
        for launcher in ("install.cmd", "status.cmd", "uninstall.cmd"):
            result = subprocess.run(["cmd.exe", "/d", "/c", str(m.PACKAGE / launcher)],
                                    env=env, capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((self.home / "config.toml").read_bytes(), self.config)
        self.assertIsNone(m.load_manifest(self.home))
        self.assertIsNone(m.read(self.home / "AGENTS.md"))


if __name__ == "__main__":
    unittest.main()
