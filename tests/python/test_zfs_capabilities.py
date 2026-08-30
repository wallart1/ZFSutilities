"""Tests for zfs_capabilities.py — OpenZFS release-variation gating."""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs
from zfs_capabilities import ZfsCapabilities, ZfsVersion


class _MockRepo:
    """Minimal ZfsRepository stand-in for capability tests."""

    def __init__(self, version_stdout: str, pool_all_stdout: str = ""):
        self._version_stdout = version_stdout
        self._pool_all_stdout = pool_all_stdout

    def version_output(self) -> str:
        return self._version_stdout

    def pool_get_all(self, pool: str) -> str:
        return self._pool_all_stdout


class TestZfsCapabilitiesParsing(unittest.TestCase):
    """Version parsing tolerates prefixes and separate userland/kmod lines."""

    def test_parses_userland_and_kmod(self):
        caps = ZfsCapabilities(_MockRepo("zfs-2.3.1-1\nzfs-kmod-2.3.1-1\n"))
        self.assertEqual(caps.version, ZfsVersion((2, 3), (2, 3)))

    def test_tolerates_extra_prefixes(self):
        caps = ZfsCapabilities(_MockRepo("OpenZFS zfs-2.2.4-1\nzfs-kmod-2.2.4-1\n"))
        self.assertEqual(caps.version, ZfsVersion((2, 2), (2, 2)))

    def test_missing_kmod_falls_back_to_userland_with_warning(self):
        with capture_logs() as logs:
            caps = ZfsCapabilities(_MockRepo("zfs-2.2.4-1\n"))
        self.assertEqual(caps.version, ZfsVersion((2, 2), (2, 2)))
        self.assertTrue(any("kernel-module" in m for m in logs))

    def test_empty_version_output_logs_warning(self):
        with capture_logs() as logs:
            caps = ZfsCapabilities(_MockRepo(""))
        self.assertEqual(caps.version, ZfsVersion((0, 0), (0, 0)))
        self.assertTrue(any("Unable to determine" in m for m in logs))


class TestZfsCapabilitiesGating(unittest.TestCase):
    """Feature decisions are gated on the kernel-module version."""

    def test_version_matrix(self):
        expectations = {
            (2, 1): {"draid": True, "json_output": False, "ssb_on_zvols": False},
            (2, 2): {"draid": True, "json_output": False, "ssb_on_zvols": False},
            (2, 3): {
                "draid": True,
                "json_output": True,
                "raidz_expansion": True,
                "ssb_on_zvols": False,
            },
            (2, 4): {
                "draid": True,
                "json_output": True,
                "ssb_on_zvols": True,
                "ssb_non_power_of_two": True,
            },
        }
        for version, expected in expectations.items():
            with self.subTest(version=version):
                stdout = f"zfs-{version[0]}.{version[1]}-1\nzfs-kmod-{version[0]}.{version[1]}-1\n"
                caps = ZfsCapabilities(_MockRepo(stdout))
                for feature, want in expected.items():
                    self.assertEqual(caps.supports(feature), want, feature)

    def test_mismatch_uses_kmod(self):
        stdout = "zfs-2.4.0-1\nzfs-kmod-2.2.0-1\n"
        with capture_logs() as logs:
            caps = ZfsCapabilities(_MockRepo(stdout))
        self.assertEqual(caps.version, ZfsVersion((2, 4), (2, 2)))
        self.assertFalse(caps.supports("json_output"))
        self.assertTrue(any("differs" in m for m in logs))

    def test_supports_unknown_feature_returns_false(self):
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n"))
        self.assertFalse(caps.supports("nonexistent"))

    def test_requires_text(self):
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n"))
        self.assertEqual(caps.requires("json_output"), "requires OpenZFS 2.3+")
        self.assertEqual(caps.requires("draid"), "requires OpenZFS 2.1+")
        self.assertEqual(caps.requires("nonexistent"), "")


class TestZfsCapabilitiesPoolFeature(unittest.TestCase):
    """Pool-scoped feature flags are read from `zpool get all`."""

    def test_active_feature_supported(self):
        stdout = "pool\tfeature@raidz_expansion\tactive\n"
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n", stdout))
        self.assertTrue(caps.supports_pool_feature("tank", "raidz_expansion"))

    def test_enabled_feature_supported(self):
        stdout = "pool\tfeature@raidz_expansion\tenabled\n"
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n", stdout))
        self.assertTrue(caps.supports_pool_feature("tank", "raidz_expansion"))

    def test_disabled_feature_not_supported(self):
        stdout = "pool\tfeature@raidz_expansion\tdisabled\n"
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n", stdout))
        self.assertFalse(caps.supports_pool_feature("tank", "raidz_expansion"))

    def test_missing_feature_not_supported(self):
        caps = ZfsCapabilities(_MockRepo("zfs-2.4.0-1\nzfs-kmod-2.4.0-1\n", ""))
        self.assertFalse(caps.supports_pool_feature("tank", "raidz_expansion"))


if __name__ == "__main__":
    unittest.main()
