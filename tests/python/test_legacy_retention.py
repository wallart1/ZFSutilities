"""Tests for legacy_retention.py — legacy retention policy file parsing."""

import os
import tempfile
import unittest

import legacy_retention


class TestParseLegacyRetentionFile(unittest.TestCase):

    def test_parses_valid_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pol", delete=False) as f:
            f.write("bktname[0]='d'; bktretain[0]=3; minage[0]=0\n")
            f.write("bktname[1]='w'; bktretain[1]=2; minage[1]=7\n")
            path = f.name
        try:
            buckets = legacy_retention._parse_legacy_retention_file(path)
            self.assertEqual(len(buckets), 2)
            self.assertEqual(buckets[0], {"name": "d", "retain": 3, "minage": 0})
            self.assertEqual(buckets[1], {"name": "w", "retain": 2, "minage": 7})
        finally:
            os.unlink(path)

    def test_returns_empty_on_missing_file(self):
        buckets = legacy_retention._parse_legacy_retention_file("/nonexistent/path")
        self.assertEqual(buckets, [])

    def test_ignores_malformed_lines(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pol", delete=False) as f:
            f.write("bktname[0]='d'\n")
            f.write("some random text\n")
            path = f.name
        try:
            buckets = legacy_retention._parse_legacy_retention_file(path)
            self.assertEqual(buckets, [])
        finally:
            os.unlink(path)

    def test_parses_mixed_valid_and_invalid(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pol", delete=False) as f:
            f.write("bktname[0]='d'; bktretain[0]=3; minage[0]=0\n")
            f.write("garbage line\n")
            f.write("bktname[1]='m'; bktretain[1]=2; minage[1]=30\n")
            path = f.name
        try:
            buckets = legacy_retention._parse_legacy_retention_file(path)
            self.assertEqual(len(buckets), 2)
            self.assertEqual(buckets[1]["name"], "m")
        finally:
            os.unlink(path)


class TestScanLegacyRetention(unittest.TestCase):

    def test_imports_missing_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "zfsretainpol-tank"), "w") as f:
                f.write("bktname[0]='d'; bktretain[0]=5; minage[0]=0\n")
            retention = {"default": [{"name": "d", "retain": 3, "minage": 0}]}
            imported = legacy_retention.scan_legacy_retention(tmpdir, retention)
            self.assertEqual(imported, ["tank"])
            self.assertEqual(retention["tank"][0]["retain"], 5)

    def test_skips_existing_pool(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "zfsretainpol-tank"), "w") as f:
                f.write("bktname[0]='d'; bktretain[0]=5; minage[0]=0\n")
            retention = {"tank": [{"name": "d", "retain": 1, "minage": 0}]}
            imported = legacy_retention.scan_legacy_retention(tmpdir, retention)
            self.assertEqual(imported, [])

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            retention = {}
            imported = legacy_retention.scan_legacy_retention(tmpdir, retention)
            self.assertEqual(imported, [])


if __name__ == "__main__":
    unittest.main()
