"""Tests for config_core.py — JSON config load/save and generic state helpers."""

import json
import os
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import temp_config_dir

import config_core


class TestConfigPathDefaults(unittest.TestCase):
    """Module-level paths point at the documented locations."""

    def test_config_path_default(self):
        self.assertEqual(config_core.CONFIG_PATH, "/root/.config/zfsutilities.json")

    def test_session_log_dir_default(self):
        self.assertEqual(config_core.SESSION_LOG_DIR, "/var/log/zfsutilities/sessions")


class TestLoadConfig(unittest.TestCase):
    """load_config reads JSON, applies defaults, and runs migrations."""

    def test_load_config_returns_defaults_when_missing(self):
        with temp_config_dir():
            cfg = config_core.load_config()
            self.assertIn("backup", cfg)
            self.assertIn("dashboard", cfg)
            self.assertEqual(cfg["config_version"], config_core.CONFIG_VERSION)

    def test_load_config_reads_existing_file(self):
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            with open(path, "w") as f:
                json.dump({"backup": {"variables": {"label": "custom"}}, "config_version": config_core.CONFIG_VERSION}, f)
            cfg = config_core.load_config()
            self.assertEqual(cfg["backup"]["variables"]["label"], "custom")

    def test_load_config_fixes_missing_config_version(self):
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            with open(path, "w") as f:
                json.dump({"backup": {}}, f)
            cfg = config_core.load_config()
            self.assertEqual(cfg.get("config_version"), config_core.CONFIG_VERSION)

    def test_load_config_ignores_invalid_json(self):
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            with open(path, "w") as f:
                f.write("not json")
            cfg = config_core.load_config()
            self.assertIn("backup", cfg)


class TestSaveConfig(unittest.TestCase):
    """save_config writes JSON atomically."""

    def test_save_config_writes_file(self):
        with temp_config_dir():
            config_core.save_config({"foo": "bar"})
            with open(config_core.CONFIG_PATH) as f:
                data = json.load(f)
            self.assertEqual(data["foo"], "bar")


class TestProfilesDir(unittest.TestCase):
    """get_profiles_dir returns a directory derived from CONFIG_PATH."""

    def test_profiles_dir_derived_from_config_path(self):
        with temp_config_dir():
            profiles_dir = config_core.get_profiles_dir()
            self.assertEqual(profiles_dir, os.path.join(os.path.dirname(config_core.CONFIG_PATH), "profiles"))
            self.assertTrue(os.path.isdir(profiles_dir))


class TestDeepCopy(unittest.TestCase):
    """_deep_copy isolates nested structures."""

    def test_deep_copy_dict(self):
        original = {"a": [1, 2, {"b": 3}]}
        copy = config_core._deep_copy(original)
        self.assertEqual(original, copy)
        copy["a"][0] = 99
        self.assertEqual(original["a"][0], 1)


class TestUiState(unittest.TestCase):
    """UI state helpers merge and return defaults."""

    def test_get_ui_state_returns_defaults(self):
        config = {}
        state = config_core.get_ui_state(config)
        self.assertIn("main_window", state)
        self.assertFalse(state["main_window"]["maximized"])

    def test_save_ui_state_merges(self):
        with temp_config_dir():
            config = {}
            config_core.save_ui_state(config, {"main_window": {"width": 800}})
            self.assertEqual(config["ui_state"]["main_window"]["width"], 800)
            # get_ui_state overlays defaults on the saved partial state
            state = config_core.get_ui_state(config)
            self.assertIn("maximized", state["main_window"])


class TestLogRetention(unittest.TestCase):
    """Log retention helpers read and prune session logs."""

    def test_get_log_retention_days_default(self):
        config = {}
        self.assertEqual(config_core.get_log_retention_days(config), 30)

    def test_save_log_retention_days(self):
        with temp_config_dir():
            config = {}
            config_core.save_log_retention_days(config, 7)
            self.assertEqual(config["log_retention_days"], 7)

    def test_prune_old_logs_removes_stale(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            old_file = os.path.join(tmpdir, "old.log")
            new_file = os.path.join(tmpdir, "new.log")
            for f in (old_file, new_file):
                with open(f, "w") as fh:
                    fh.write("x")
            os.utime(old_file, (time.time() - 864000, time.time() - 864000))
            orig_dir = config_core.SESSION_LOG_DIR
            config_core.SESSION_LOG_DIR = tmpdir
            try:
                removed = config_core.prune_old_logs(5)
                self.assertEqual(removed, 1)
                self.assertFalse(os.path.exists(old_file))
                self.assertTrue(os.path.exists(new_file))
            finally:
                config_core.SESSION_LOG_DIR = orig_dir


class TestHistoryRetention(unittest.TestCase):
    """History retention helpers read/write retention days."""

    def test_get_history_retention_days_default(self):
        config = {}
        self.assertEqual(config_core.get_history_retention_days(config), config_core.DEFAULT_HISTORY_RETENTION_DAYS)

    def test_save_history_retention_days(self):
        with temp_config_dir():
            config = {}
            config_core.save_history_retention_days(config, 14)
            self.assertEqual(config["history_retention_days"], 14)


class TestSessionLogCap(unittest.TestCase):
    """session_log_max_bytes helpers read/write the log cap."""

    def test_get_session_log_max_bytes_default(self):
        config = {}
        self.assertEqual(
            config_core.get_session_log_max_bytes(config),
            config_core.DEFAULT_SESSION_LOG_MAX_BYTES,
        )

    def test_get_session_log_max_bytes_custom(self):
        config = {"session_log_max_bytes": 5 * 1024 * 1024}
        self.assertEqual(
            config_core.get_session_log_max_bytes(config),
            5 * 1024 * 1024,
        )

    def test_get_session_log_max_bytes_rejects_invalid(self):
        config = {"session_log_max_bytes": -1}
        self.assertEqual(
            config_core.get_session_log_max_bytes(config),
            config_core.DEFAULT_SESSION_LOG_MAX_BYTES,
        )

    def test_save_session_log_max_bytes(self):
        with temp_config_dir():
            config = {}
            config_core.save_session_log_max_bytes(config, 20 * 1024 * 1024)
            self.assertEqual(config["session_log_max_bytes"], 20 * 1024 * 1024)

    def test_save_session_log_max_bytes_rejects_invalid(self):
        config = {}
        with self.assertRaises(ValueError):
            config_core.save_session_log_max_bytes(config, 0)
        with self.assertRaises(ValueError):
            config_core.save_session_log_max_bytes(config, -100)


class TestDashboardConfig(unittest.TestCase):
    """Dashboard config helpers return and save defaults."""

    def test_get_dashboard_config_default(self):
        config = {}
        dash = config_core.get_dashboard_config(config)
        self.assertEqual(dash["low_space_threshold"], 80)

    def test_save_dashboard_config(self):
        with temp_config_dir():
            config = {}
            config_core.save_dashboard_config(config, {"low_space_threshold": 90})
            self.assertEqual(config["dashboard"]["low_space_threshold"], 90)


class TestConfigLocking(unittest.TestCase):
    """Config load/save acquire the shared config lock."""

    def test_save_config_acquires_write_lock(self):
        with temp_config_dir():
            import file_locking
            lock_path = file_locking.CONFIG_LOCK_PATH
            config_core.save_config({"test": "data"})
            self.assertTrue(os.path.exists(lock_path))

    def test_load_config_acquires_read_lock(self):
        with temp_config_dir():
            import file_locking
            config_core.save_config({"test": "data"})
            lock_path = file_locking.CONFIG_LOCK_PATH
            config_core.load_config()
            self.assertTrue(os.path.exists(lock_path))


if __name__ == "__main__":
    unittest.main()
