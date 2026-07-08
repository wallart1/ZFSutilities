"""Tests for installer_retention.py — default retention profile initialization."""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
INSTALLERS_SRC = os.path.join(REPO_ROOT, "10 Installers")
if INSTALLERS_SRC not in sys.path:
    sys.path.insert(0, INSTALLERS_SRC)
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import config_core
import installer_retention
from feature_config import DEFAULT_RETENTION
from test_support import temp_config_dir


class TestEnsureDefaultRetentionProfile(unittest.TestCase):

    def _read_config(self, path):
        with open(path) as f:
            return json.load(f)

    def test_new_install_creates_default_only(self):
        """A fresh config ends up with exactly the default retention policy."""
        with temp_config_dir():
            changed = installer_retention.ensure_default_retention_profile(
                new_install=True
            )
            self.assertTrue(changed)
            config = self._read_config(config_core.CONFIG_PATH)
            self.assertEqual(list(config["retention"].keys()), ["default"])
            self.assertEqual(config["retention"]["default"], DEFAULT_RETENTION)

    def test_new_install_clears_existing_pool_policies(self):
        """new-install also removes pre-existing pool-specific policies."""
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            initial = {
                "retention": {
                    "default": [{"name": "d", "retain": 3, "minage": 0}],
                    "tank": [{"name": "d", "retain": 7, "minage": 0}],
                }
            }
            with open(path, "w") as f:
                json.dump(initial, f)

            changed = installer_retention.ensure_default_retention_profile(
                new_install=True
            )
            self.assertTrue(changed)
            config = self._read_config(path)
            self.assertIn("default", config["retention"])
            self.assertNotIn("tank", config["retention"])

    def test_existing_config_preserves_user_profiles(self):
        """When not a new install, user-entered per-pool profiles are untouched."""
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            custom = [{"name": "d", "retain": 7, "minage": 0}]
            initial = {
                "retention": {
                    "default": [{"name": "d", "retain": 3, "minage": 0}],
                    "tank": custom,
                }
            }
            with open(path, "w") as f:
                json.dump(initial, f)

            changed = installer_retention.ensure_default_retention_profile(
                new_install=False
            )
            self.assertFalse(changed)
            config = self._read_config(path)
            self.assertEqual(config["retention"]["tank"], custom)

    def test_existing_config_without_retention_adds_default(self):
        """An existing config missing retention gets a default policy added."""
        with temp_config_dir():
            path = config_core.CONFIG_PATH
            with open(path, "w") as f:
                json.dump({"backup": {}}, f)

            changed = installer_retention.ensure_default_retention_profile(
                new_install=False
            )
            self.assertTrue(changed)
            config = self._read_config(path)
            self.assertIn("default", config["retention"])
            self.assertEqual(config["retention"]["default"], DEFAULT_RETENTION)

    def test_explicit_config_path(self):
        """The config-path argument is honored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "zfsutilities.json")
            changed = installer_retention.ensure_default_retention_profile(
                config_path=path, new_install=True
            )
            self.assertTrue(changed)
            config = self._read_config(path)
            self.assertEqual(list(config["retention"].keys()), ["default"])


if __name__ == "__main__":
    unittest.main()
