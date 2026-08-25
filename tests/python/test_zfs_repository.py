"""Tests for zfs_repository.py — ZFS/zpool subprocess isolation."""

import os
import subprocess
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_subprocess
from zfs_repository import (
    HoldRow,
    ImportablePoolCache,
    PoolRow,
    SnapshotRow,
    ZfsRepository,
    is_dataset_encrypted,
)


class TestZfsRepositoryReads(unittest.TestCase):
    """Read methods parse tab-separated zfs/zpool output."""

    def _repo(self, stdout, rc=0):
        result = subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        return repo

    def test_list_pools_parses_seven_columns(self):
        repo = self._repo("tank\tONLINE\t10T\t5T\t5T\t75%\t-\n")
        pools = repo.list_pools()
        self.assertEqual(len(pools), 1)
        self.assertEqual(
            pools[0],
            PoolRow("tank", "ONLINE", "10T", "5T", "5T", "75%", "-"),
        )

    def test_list_pools_parses_active_checkpoint(self):
        repo = self._repo("tank\tONLINE\t10T\t5T\t5T\t75%\t50G\n")
        pools = repo.list_pools()
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0].ckpoint, "50G")

    def test_list_pools_ignores_blank_lines(self):
        repo = self._repo("\ntank\tONLINE\t10T\t5T\t5T\t75%\t-\n\n")
        self.assertEqual(len(repo.list_pools()), 1)

    def test_list_pools_full_parses_nine_columns(self):
        stdout = "tank\t10T\t5T\t5T\t0B\t-\t5%\t75%\tONLINE\n"
        repo = self._repo(stdout)
        pools = repo.list_pools_full()
        self.assertEqual(len(pools), 1)
        self.assertEqual(pools[0]["name"], "tank")
        self.assertEqual(pools[0]["health"], "ONLINE")
        self.assertEqual(pools[0]["frag"], "5%")

    def test_list_datasets_parses_eight_columns(self):
        stdout = "tank/data\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\n"
        repo = self._repo(stdout)
        rows = repo.list_datasets(pool="tank")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "tank/data")
        self.assertEqual(rows[0].ds_type, "filesystem")

    def test_list_snapshots_parses_eight_columns(self):
        stdout = "tank/data@snap1\t2025-01-01\tsnapshot\t100K\t-\t50G\t-\t-\n"
        repo = self._repo(stdout)
        rows = repo.list_snapshots("tank/data", depth=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            SnapshotRow("tank/data@snap1", "2025-01-01", "snapshot", "100K", "-", "50G", "-", "-"),
        )

    def test_list_holds_parses_three_columns(self):
        stdout = "tank/data@snap1\toffsite\t2025-01-01\n"
        repo = self._repo(stdout)
        holds = repo.list_holds("tank/data@snap1")
        self.assertEqual(len(holds), 1)
        self.assertEqual(holds[0], HoldRow("tank/data@snap1", "offsite", "2025-01-01"))

    def test_get_property_returns_stripped_value(self):
        repo = self._repo("/mnt/data\n")
        self.assertEqual(repo.get_property("tank/data", "mountpoint"), "/mnt/data")

    def test_get_all_properties_parses_tab_separated_output(self):
        stdout = "type\tfilesystem\nused\t100G\navailable\t500G\ncompression\toff\n"
        repo = self._repo(stdout)
        props = repo.get_all_properties("tank/data")
        self.assertEqual(props["type"], "filesystem")
        self.assertEqual(props["used"], "100G")
        self.assertEqual(props["available"], "500G")
        self.assertEqual(props["compression"], "off")

    def test_get_all_properties_ignores_blank_lines(self):
        stdout = "type\tfilesystem\n\nused\t100G\n\n"
        repo = self._repo(stdout)
        props = repo.get_all_properties("tank/data")
        self.assertEqual(props, {"type": "filesystem", "used": "100G"})

    def test_pool_get_all_returns_stdout(self):
        stdout = "NAME\tPROPERTY\tVALUE\tSOURCE\ntank\tsize\t10T\t-\n"
        repo = self._repo(stdout)
        self.assertEqual(repo.pool_get_all("tank"), stdout)

    def test_pool_get_all_returns_empty_on_failure(self):
        result = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="no such pool"
        )
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        self.assertEqual(repo.pool_get_all("tank"), "")

    def test_get_clones_reads_clones_property(self):
        repo = self._repo("tank/data/clone1\n")
        self.assertEqual(repo.get_property("tank/data@snap1", "clones"), "tank/data/clone1")

    def test_get_recursive_snapshot_clones_filters_dashes(self):
        stdout = "-\n-\ntank/data/clone1\n"
        repo = self._repo(stdout)
        clones = repo.get_recursive_snapshot_clones("tank/data")
        self.assertEqual(clones, ["tank/data/clone1"])


class TestZfsRepositoryWrites(unittest.TestCase):
    """Write methods return True on success and False on failure."""

    def _repo(self, rc):
        result = subprocess.CompletedProcess(args=[], returncode=rc, stdout="", stderr="boom")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        return repo

    def test_snapshot_returns_true_on_success(self):
        self.assertTrue(self._repo(0).snapshot("tank/data@snap"))

    def test_snapshot_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).snapshot("tank/data@snap"))

    def test_destroy_returns_true_on_success(self):
        self.assertTrue(self._repo(0).destroy("tank/data@snap"))

    def test_destroy_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).destroy("tank/data@snap"))

    def test_hold_returns_true_on_success(self):
        self.assertTrue(self._repo(0).hold("keep", "tank/data@snap"))

    def test_release_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).release("keep", "tank/data@snap"))

    def test_rollback_returns_true_on_success(self):
        self.assertTrue(self._repo(0).rollback("tank/data@snap"))

    def test_import_pool_returns_true_on_success(self):
        self.assertTrue(self._repo(0).import_pool("tank"))

    def test_export_pool_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).export_pool("tank"))

    def test_start_scrub_returns_true_on_success(self):
        self.assertTrue(self._repo(0).start_scrub("tank"))

    def test_pause_scrub_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).pause_scrub("tank"))

    def test_resume_scrub_returns_true_on_success(self):
        self.assertTrue(self._repo(0).resume_scrub("tank"))

    def test_stop_scrub_returns_false_on_failure(self):
        self.assertFalse(self._repo(1).stop_scrub("tank"))

    def test_pool_status_returns_stdout(self):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout="status text", stderr="")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        self.assertEqual(repo.pool_status("tank"), "status text")


class TestZfsRepositorySudo(unittest.TestCase):
    """sudo=True prefixes commands with 'sudo'."""

    def test_sudo_prefix(self):
        repo = ZfsRepository(sudo=True)
        self.assertEqual(repo._zfs("list"), ["sudo", "zfs", "list"])
        self.assertEqual(repo._zpool("list"), ["sudo", "zpool", "list"])


class TestZfsRepositoryErrors(unittest.TestCase):
    """Read methods propagate subprocess errors to callers."""

    def test_list_pools_raises_on_subprocess_error(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, "zpool list")
        )
        with self.assertRaises(subprocess.CalledProcessError):
            repo.list_pools()


class TestPoolStatusErrors(unittest.TestCase):
    """pool_status_errors parses zpool status output."""

    def _repo(self, stdout):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        return repo

    def _status_no_errors(self):
        return (
            "  pool: tank\n"
            " state: ONLINE\n"
            "config:\n"
            "\tNAME        STATE     READ WRITE CKSUM\n"
            "\ttank        ONLINE       0     0     0\n"
            "\t  mirror-0  ONLINE       0     0     0\n"
            "\t    sda     ONLINE       0     0     0\n"
            "\t    sdb     ONLINE       0     0     0\n"
            "\n"
            "errors: No known data errors\n"
        )

    def test_no_errors(self):
        repo = self._repo(self._status_no_errors())
        errors = repo.pool_status_errors("tank")
        self.assertFalse(errors["has_errors"])
        self.assertEqual(errors["errors_summary"], "No known data errors")
        self.assertEqual(errors["data_errors"], [])
        self.assertEqual(errors["vdev_errors"], [])

    def test_permanent_data_errors(self):
        stdout = (
            "  pool: tank\n"
            " state: ONLINE\n"
            "config:\n"
            "\tNAME        STATE     READ WRITE CKSUM\n"
            "\ttank        ONLINE       0     0     0\n"
            "\n"
            "errors: Permanent errors have been detected in the following files:\n"
            "\ttank/data/file1\n"
            "\ttank/data/file2\n"
        )
        repo = self._repo(stdout)
        errors = repo.pool_status_errors("tank")
        self.assertTrue(errors["has_errors"])
        self.assertIn("Permanent errors", errors["errors_summary"])
        self.assertEqual(
            errors["data_errors"],
            ["tank/data/file1", "tank/data/file2"],
        )

    def test_vdev_errors(self):
        stdout = (
            "  pool: tank\n"
            " state: DEGRADED\n"
            "config:\n"
            "\tNAME        STATE     READ WRITE CKSUM\n"
            "\ttank        DEGRADED     0     0     0\n"
            "\t  sda       ONLINE       0     0     0\n"
            "\t  sdb       DEGRADED     0     0   123\n"
        )
        repo = self._repo(stdout)
        errors = repo.pool_status_errors("tank")
        self.assertTrue(errors["has_errors"])
        self.assertEqual(len(errors["vdev_errors"]), 1)
        self.assertEqual(errors["vdev_errors"][0]["name"], "sdb")
        self.assertEqual(errors["vdev_errors"][0]["cksum"], 123)
        self.assertIn("sdb (cksum=123)", errors["errors_summary"])

    def test_vdev_multiple_counters(self):
        stdout = (
            "  pool: tank\n"
            " state: ONLINE\n"
            "config:\n"
            "\tNAME        STATE     READ WRITE CKSUM\n"
            "\ttank        ONLINE       0     0     0\n"
            "\t  sda       ONLINE       5     3     0\n"
            "\n"
            "errors: No known data errors\n"
        )
        repo = self._repo(stdout)
        errors = repo.pool_status_errors("tank")
        self.assertTrue(errors["has_errors"])
        self.assertEqual(errors["vdev_errors"][0]["read"], 5)
        self.assertEqual(errors["vdev_errors"][0]["write"], 3)
        self.assertIn("read=5", errors["errors_summary"])
        self.assertIn("write=3", errors["errors_summary"])

    def test_empty_status(self):
        repo = self._repo("")
        errors = repo.pool_status_errors("tank")
        self.assertFalse(errors["has_errors"])
        self.assertEqual(errors["errors_summary"], "status unavailable")


class TestListImportablePoolNames(unittest.TestCase):
    """list_importable_pool_names parses `zpool import` output."""

    def _repo(self, stdout):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        return repo

    def test_parses_single_importable_pool(self):
        stdout = (
            "   pool: tank\n"
            "     id: 1234567890\n"
            "  state: ONLINE\n"
            " config:\n"
            "\ttank        ONLINE       0     0     0\n"
            "\t  sda       ONLINE       0     0     0\n"
        )
        repo = self._repo(stdout)
        self.assertEqual(repo.list_importable_pool_names(), {"tank"})

    def test_parses_multiple_importable_pools(self):
        stdout = (
            "   pool: tank\n"
            "     id: 1\n"
            "  state: ONLINE\n"
            " config:\n"
            "\ttank        ONLINE       0     0     0\n"
            "   pool: archive\n"
            "     id: 2\n"
            "  state: ONLINE\n"
            " config:\n"
            "\tarchive     ONLINE       0     0     0\n"
        )
        repo = self._repo(stdout)
        self.assertEqual(repo.list_importable_pool_names(), {"tank", "archive"})

    def test_filters_zvol_backed_pools(self):
        stdout = (
            "   pool: nested\n"
            "     id: 1\n"
            "  state: ONLINE\n"
            " config:\n"
            "\tnested      ONLINE       0     0     0\n"
            "\t  zd0       ONLINE       0     0     0\n"
            "   pool: normal\n"
            "     id: 2\n"
            "  state: ONLINE\n"
            " config:\n"
            "\tnormal      ONLINE       0     0     0\n"
            "\t  sda       ONLINE       0     0     0\n"
        )
        repo = self._repo(stdout)
        self.assertEqual(repo.list_importable_pool_names(), {"normal"})

    def test_empty_output_returns_empty_set(self):
        repo = self._repo("")
        self.assertEqual(repo.list_importable_pool_names(), set())


class TestImportablePoolCache(unittest.TestCase):
    """ImportablePoolCache refreshes in the background and honours TTL."""

    def _repo(self, names):
        repo = MagicMock()
        repo.list_importable_pool_names.return_value = set(names)
        return repo

    def test_first_call_returns_empty_and_triggers_refresh(self):
        repo = self._repo(["tank"])
        cache = ImportablePoolCache(repo, ttl_seconds=60.0)
        result = cache.get()
        self.assertEqual(result, set())
        # Give the daemon thread time to finish.
        time.sleep(0.05)
        repo.list_importable_pool_names.assert_called_once()
        self.assertEqual(cache.get(), {"tank"})

    def test_second_call_within_ttl_returns_cached_value(self):
        repo = self._repo(["tank"])
        cache = ImportablePoolCache(repo, ttl_seconds=60.0)
        cache.get()
        time.sleep(0.05)
        self.assertEqual(cache.get(), {"tank"})
        repo.list_importable_pool_names.assert_called_once()

    def test_callback_invoked_after_refresh(self):
        repo = self._repo(["tank"])
        callback = MagicMock()
        cache = ImportablePoolCache(repo, ttl_seconds=60.0)
        cache.get(callback=callback)
        time.sleep(0.05)
        callback.assert_called_once()

    def test_invalidate_forces_new_refresh(self):
        repo = self._repo(["tank"])
        cache = ImportablePoolCache(repo, ttl_seconds=60.0)
        cache.get()
        time.sleep(0.05)
        repo.list_importable_pool_names.reset_mock()

        cache.invalidate()
        cache.get()
        time.sleep(0.05)
        repo.list_importable_pool_names.assert_called_once()


class TestScrubCommandsLogDebug(unittest.TestCase):
    """ZfsRepository scrub methods must log the command at DEBUG level."""

    def _mock_run(self):
        """Return a mock subprocess.run that reports success."""
        mock = MagicMock()
        mock.return_value.returncode = 0
        return mock

    def _assert_scrub_log(self, logs, expected_cmd):
        """Assert at least one captured log contains the expected DEBUG text."""
        needle = f"DEBUG: issuing zpool scrub command: {expected_cmd}"
        self.assertTrue(
            any(needle in entry for entry in logs),
            f"Expected log containing '{needle}', got: {logs}",
        )

    def test_start_scrub_logs_debug(self):
        with patch("zfs_repository.subprocess.run", self._mock_run()) as mock_run:
            with capture_logs() as logs:
                repo = ZfsRepository()
                self.assertTrue(repo.start_scrub("tank"))
        mock_run.assert_called_once_with(
            ["zpool", "scrub", "tank"],
            capture_output=True,
            text=True,
            check=False,
            timeout=None,
        )
        self._assert_scrub_log(logs, "zpool scrub tank")

    def test_pause_scrub_logs_debug(self):
        with patch("zfs_repository.subprocess.run", self._mock_run()) as mock_run:
            with capture_logs() as logs:
                repo = ZfsRepository()
                self.assertTrue(repo.pause_scrub("tank"))
        mock_run.assert_called_once_with(
            ["zpool", "scrub", "-p", "tank"],
            capture_output=True,
            text=True,
            check=False,
            timeout=None,
        )
        self._assert_scrub_log(logs, "zpool scrub -p tank")

    def test_resume_scrub_logs_debug(self):
        with patch("zfs_repository.subprocess.run", self._mock_run()) as mock_run:
            with capture_logs() as logs:
                repo = ZfsRepository()
                self.assertTrue(repo.resume_scrub("tank"))
        mock_run.assert_called_once_with(
            ["zpool", "scrub", "tank"],
            capture_output=True,
            text=True,
            check=False,
            timeout=None,
        )
        self._assert_scrub_log(logs, "zpool scrub tank")

    def test_stop_scrub_logs_debug(self):
        with patch("zfs_repository.subprocess.run", self._mock_run()) as mock_run:
            with capture_logs() as logs:
                repo = ZfsRepository()
                self.assertTrue(repo.stop_scrub("tank"))
        mock_run.assert_called_once_with(
            ["zpool", "scrub", "-s", "tank"],
            capture_output=True,
            text=True,
            check=False,
            timeout=None,
        )
        self._assert_scrub_log(logs, "zpool scrub -s tank")

    def test_sudo_scrub_logs_debug(self):
        with patch("zfs_repository.subprocess.run", self._mock_run()):
            with capture_logs() as logs:
                repo = ZfsRepository(sudo=True)
                repo.start_scrub("tank")
        self._assert_scrub_log(logs, "sudo zpool scrub tank")


if __name__ == "__main__":
    unittest.main()


class TestIsDatasetEncrypted(unittest.TestCase):
    """is_dataset_encrypted matches a path to its ZFS dataset encryption."""

    def test_encrypted_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name,mountpoint",
                lambda cmd, **kwargs: m._completed("tank/data\t/backups\n"),
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("aes-256-gcm"),
            )
            self.assertTrue(is_dataset_encrypted("/backups/keys"))

    def test_unencrypted_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name,mountpoint",
                lambda cmd, **kwargs: m._completed("tank/data\t/backups\n"),
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("-"),
            )
            self.assertFalse(is_dataset_encrypted("/backups/keys"))

    def test_off_encryption_value(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name,mountpoint",
                lambda cmd, **kwargs: m._completed("tank/data\t/backups\n"),
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("off"),
            )
            self.assertFalse(is_dataset_encrypted("/backups/keys"))

    def test_no_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name,mountpoint",
                lambda cmd, **kwargs: m._completed("tank/data\t/other\n"),
            )
            self.assertFalse(is_dataset_encrypted("/backups/keys"))

    def test_zfs_list_failure(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name,mountpoint",
                lambda cmd, **kwargs: m._completed("", rc=1),
            )
            self.assertFalse(is_dataset_encrypted("/backups/keys"))

    def test_empty_path(self):
        self.assertFalse(is_dataset_encrypted(""))
