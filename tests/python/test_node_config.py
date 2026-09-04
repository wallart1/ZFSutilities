"""Tests for python/node_config.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import node_config


class TestLoadNodeConfig(unittest.TestCase):
    def test_no_config_defaults_to_single_node(self):
        with patch.object(node_config, "_find_config_file", return_value=None):
            cfg = node_config.load_node_config()
        self.assertEqual(cfg["mode"], "single-node")
        self.assertEqual(cfg["storage_host"], cfg["this_host"])
        self.assertEqual(cfg["compute_host"], cfg["this_host"])
        self.assertEqual(cfg["pools"], set())

    def test_single_node_conf(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('NODE_MODE="single-node"\n')
            f.write('STORAGE_HOST="storage1"\n')
            f.write('COMPUTE_HOST="compute1"\n')
            path = f.name
        try:
            cfg = node_config.load_node_config(path)
            self.assertEqual(cfg["mode"], "single-node")
            self.assertEqual(cfg["storage_host"], cfg["this_host"])
            self.assertEqual(cfg["compute_host"], cfg["this_host"])
        finally:
            os.unlink(path)

    def test_two_node_conf(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('NODE_MODE="two-node"\n')
            f.write('STORAGE_HOST="stewie"\n')
            f.write('COMPUTE_HOST="tweety"\n')
            f.write('STORAGE_IP="10.0.0.1"\n')
            f.write(
                'declare -A POOL_TARGET=(["threeamigos"]="threeamigos" ["fivebays"]="fivebays")\n'
            )
            path = f.name
        try:
            cfg = node_config.load_node_config(path)
            self.assertEqual(cfg["mode"], "two-node")
            self.assertEqual(cfg["storage_host"], "stewie")
            self.assertEqual(cfg["compute_host"], "tweety")
            self.assertEqual(cfg["storage_ip"], "10.0.0.1")
            self.assertEqual(cfg["pools"], {"threeamigos", "fivebays"})
        finally:
            os.unlink(path)

    def test_legacy_conf_without_node_mode_defaults_two_node(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('STORAGE_HOST="stewie"\n')
            f.write('COMPUTE_HOST="tweety"\n')
            path = f.name
        try:
            cfg = node_config.load_node_config(path)
            self.assertEqual(cfg["mode"], "two-node")
            self.assertEqual(cfg["storage_host"], "stewie")
            self.assertEqual(cfg["compute_host"], "tweety")
        finally:
            os.unlink(path)

    def test_env_override(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('NODE_MODE="single-node"\n')
            path = f.name
        try:
            with patch.dict(os.environ, {"ZFSUTILITIES_NODE_CONF": path}):
                cfg = node_config.load_node_config()
            self.assertEqual(cfg["mode"], "single-node")
        finally:
            os.unlink(path)


class TestLockAuthorityHost(unittest.TestCase):
    def test_single_node_is_local(self):
        cfg = {
            "mode": "single-node",
            "this_host": "myhost",
            "storage_host": "myhost",
            "compute_host": "myhost",
            "pools": {"threeamigos"},
        }
        self.assertIsNone(node_config.get_lock_authority_host("threeamigos/pve", cfg))

    def test_storage_host_is_local(self):
        cfg = {
            "mode": "two-node",
            "this_host": "stewie",
            "storage_host": "stewie",
            "compute_host": "tweety",
            "pools": {"threeamigos"},
        }
        self.assertIsNone(node_config.get_lock_authority_host("threeamigos/pve", cfg))

    def test_compute_host_forwards_to_storage(self):
        cfg = {
            "mode": "two-node",
            "this_host": "tweety",
            "storage_host": "stewie",
            "compute_host": "tweety",
            "pools": {"threeamigos"},
        }
        self.assertEqual(node_config.get_lock_authority_host("threeamigos/pve", cfg), "stewie")

    def test_unknown_pool_is_local(self):
        cfg = {
            "mode": "two-node",
            "this_host": "tweety",
            "storage_host": "stewie",
            "compute_host": "tweety",
            "pools": {"threeamigos"},
        }
        self.assertIsNone(node_config.get_lock_authority_host("tank/pve", cfg))


if __name__ == "__main__":
    unittest.main()
