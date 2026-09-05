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
    AshiftInfo,
    HoldRow,
    ImportablePoolCache,
    PoolRow,
    SnapshotRow,
    ZfsRepository,
    build_create_pool_command,
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

    def test_list_datasets_parses_nine_columns(self):
        stdout = "tank/data\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
        repo = self._repo(stdout)
        rows = repo.list_datasets(pool="tank")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "tank/data")
        self.assertEqual(rows[0].ds_type, "filesystem")
        self.assertEqual(rows[0].mounted, "yes")

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

    def test_get_properties_parses_multiple_properties(self):
        stdout = "recordsize\t128K\ncompression\tzstd\n"
        repo = self._repo(stdout)
        props = repo.get_properties("tank/data", ["recordsize", "compression"])
        self.assertEqual(props["recordsize"], "128K")
        self.assertEqual(props["compression"], "zstd")

    def test_get_properties_returns_dash_for_missing_properties(self):
        stdout = "recordsize\t128K\n"
        repo = self._repo(stdout)
        props = repo.get_properties(
            "tank/data", ["recordsize", "compression", "special_small_blocks"]
        )
        self.assertEqual(props["recordsize"], "128K")
        self.assertEqual(props["compression"], "-")
        self.assertEqual(props["special_small_blocks"], "-")

    def test_get_properties_ignores_blank_lines(self):
        stdout = "recordsize\t128K\n\ncompression\tzstd\n\n"
        repo = self._repo(stdout)
        props = repo.get_properties("tank/data", ["recordsize", "compression"])
        self.assertEqual(props, {"recordsize": "128K", "compression": "zstd"})

    def test_get_properties_raises_on_subprocess_error(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: (_ for _ in ()).throw(
            subprocess.CalledProcessError(1, "zfs get")
        )
        with self.assertRaises(subprocess.CalledProcessError):
            repo.get_properties("tank/data", ["recordsize"])

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

    def test_set_property_returns_true_on_success(self):
        self.assertTrue(self._repo(0).set_property("tank/data", "compression", "zstd"))

    def test_set_property_returns_false_on_failure(self):
        repo = self._repo(1)
        self.assertFalse(repo.set_property("tank/data", "compression", "zstd"))

    def test_set_property_logs_warning_on_failure(self):
        repo = self._repo(1)
        with capture_logs() as logs:
            repo.set_property("tank/data", "compression", "zstd")
        self.assertTrue(any("Failed to set compression=zstd on tank/data" in e for e in logs))

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


class TestListImportablePoolDevices(unittest.TestCase):
    """list_importable_pool_devices returns leaf device paths per pool."""

    def _repo(self, stdout):
        result = subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: result
        return repo

    def test_stripe_pool_returns_leaf_device(self):
        stdout = (
            "   pool: tank\n"
            "     id: 1\n"
            "  state: ONLINE\n"
            " config:\n"
            "\ttank        ONLINE       0     0     0\n"
            "\t  sda       ONLINE       0     0     0\n"
        )
        self.assertEqual(self._repo(stdout).list_importable_pool_devices(), {"tank": ["sda"]})

    def test_mirror_group_header_is_not_a_leaf(self):
        stdout = (
            "   pool: tank\n"
            "     id: 1\n"
            "  state: ONLINE\n"
            " config:\n"
            "\ttank        ONLINE       0     0     0\n"
            "\t  mirror-0  ONLINE       0     0     0\n"
            "\t    sda     ONLINE       0     0     0\n"
            "\t    sdb     ONLINE       0     0     0\n"
        )
        self.assertEqual(
            self._repo(stdout).list_importable_pool_devices(), {"tank": ["sda", "sdb"]}
        )

    def test_raidz_with_spares_lists_spare_leaf(self):
        stdout = (
            "   pool: rz\n"
            "     id: 2\n"
            "  state: ONLINE\n"
            " config:\n"
            "\trz          ONLINE       0     0     0\n"
            "\t  raidz2-0  ONLINE       0     0     0\n"
            "\t    sda     ONLINE       0     0     0\n"
            "\t    sdb     ONLINE       0     0     0\n"
            "\t    sdc     ONLINE       0     0     0\n"
            "\t    sdd     ONLINE       0     0     0\n"
            "\tspares\n"
            "\t  sde       AVAIL\n"
        )
        self.assertEqual(
            self._repo(stdout).list_importable_pool_devices(),
            {"rz": ["sda", "sdb", "sdc", "sdd", "sde"]},
        )

    def test_zvol_backed_pool_excluded(self):
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
        self.assertEqual(repo.list_importable_pool_devices(), {"normal": ["sda"]})
        self.assertEqual(repo.list_importable_pool_names(), {"normal"})

    def test_pool_without_config_section_has_empty_path_list(self):
        stdout = (
            "   pool: tank\n"
            "     id: 1\n"
            "  state: ONLINE\n"
            " config:\n"
            "\ttank        ONLINE       0     0     0\n"
            "   pool: archive\n"
            "     id: 2\n"
            "  state: ONLINE\n"
        )
        self.assertEqual(
            self._repo(stdout).list_importable_pool_devices(),
            {"tank": [], "archive": []},
        )

    def test_empty_output_returns_empty_dict(self):
        self.assertEqual(self._repo("").list_importable_pool_devices(), {})


class TestBuildCreatePoolCommand(unittest.TestCase):
    """build_create_pool_command produces exact, validated zpool create argv."""

    def test_stripe_has_no_topology_keyword(self):
        cmd = build_create_pool_command("tank", "stripe", ["/dev/disk/by-id/ata-X"])
        self.assertEqual(cmd, ["zpool", "create", "tank", "/dev/disk/by-id/ata-X"])

    def test_mirror_places_keyword_before_paths(self):
        paths = ["/dev/disk/by-id/ata-X", "/dev/disk/by-id/ata-Y"]
        cmd = build_create_pool_command("tank", "mirror", paths)
        self.assertEqual(cmd, ["zpool", "create", "tank", "mirror"] + paths)

    def test_raidz2_with_ashift_and_profile_options(self):
        paths = [f"/dev/disk/by-id/ata-{d}" for d in ("a", "b", "c", "d")]
        options = [("recordsize", "1M"), ("compression", "zstd")]
        cmd = build_create_pool_command("backup", "raidz2", paths, ashift=12, options=options)
        self.assertEqual(
            cmd,
            [
                "zpool",
                "create",
                "-o",
                "ashift=12",
                "-O",
                "recordsize=1M",
                "-O",
                "compression=zstd",
                "backup",
                "raidz2",
            ]
            + paths,
        )

    def test_defaults_emit_no_ashift_or_options(self):
        paths = ["/dev/disk/by-id/ata-X", "/dev/disk/by-id/ata-Y"]
        cmd = build_create_pool_command("tank", "mirror", paths, ashift=None, options=None)
        self.assertEqual(cmd, ["zpool", "create", "tank", "mirror"] + paths)

    def test_rejects_unknown_topology(self):
        with self.assertRaises(ValueError):
            build_create_pool_command("tank", "draid", ["/dev/disk/by-id/ata-X"])

    def test_rejects_too_few_disks(self):
        paths = [f"/dev/disk/by-id/ata-{d}" for d in ("a", "b", "c", "d")]
        with self.assertRaises(ValueError):
            build_create_pool_command("tank", "raidz3", paths)

    def test_rejects_non_by_id_path(self):
        with self.assertRaises(ValueError):
            build_create_pool_command("tank", "stripe", ["/dev/sda"])

    def test_rejects_out_of_range_ashift(self):
        for ashift in (8, 17):
            with self.assertRaises(ValueError):
                build_create_pool_command("tank", "stripe", ["/dev/disk/by-id/ata-X"], ashift=ashift)

    def test_rejects_empty_pool_name(self):
        with self.assertRaises(ValueError):
            build_create_pool_command("", "stripe", ["/dev/disk/by-id/ata-X"])

    def test_rejects_invalid_option_property(self):
        with self.assertRaises(ValueError):
            build_create_pool_command(
                "tank",
                "stripe",
                ["/dev/disk/by-id/ata-X"],
                options=[("recordsize=evil", "1M")],
            )


class TestCreatePoolExecution(unittest.TestCase):
    """create_pool_dry_run and create_pool execute built argv via _run."""

    def _recording_repo(self, rc=0, stdout="", stderr="", sudo=False):
        calls = []
        result = subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)
        repo = ZfsRepository(sudo=sudo)

        def _run(cmd, **kwargs):
            calls.append((list(cmd), kwargs))
            return result

        repo._run = _run
        return repo, calls

    def test_dry_run_injects_n_after_create(self):
        repo, calls = self._recording_repo(rc=0, stdout="would create 'tank'")
        rc, output = repo.create_pool_dry_run(["zpool", "create", "tank", "/dev/disk/by-id/ata-X"])
        self.assertEqual(calls[0][0], ["zpool", "create", "-n", "tank", "/dev/disk/by-id/ata-X"])
        self.assertEqual((rc, output), (0, "would create 'tank'"))

    def test_dry_run_failure_returns_stderr_when_stdout_empty(self):
        repo, _ = self._recording_repo(rc=1, stdout="", stderr="invalid vdev specification")
        rc, output = repo.create_pool_dry_run(["zpool", "create", "tank", "/dev/disk/by-id/ata-X"])
        self.assertEqual((rc, output), (1, "invalid vdev specification"))

    def test_create_pool_returns_true_on_success(self):
        repo, calls = self._recording_repo(rc=0)
        cmd = build_create_pool_command("tank", "stripe", ["/dev/disk/by-id/ata-X"])
        self.assertTrue(repo.create_pool(cmd))
        self.assertEqual(calls[0][0], cmd)

    def test_create_pool_returns_false_and_logs_warning_on_failure(self):
        repo, _ = self._recording_repo(rc=1, stderr="device busy")
        cmd = build_create_pool_command("tank", "stripe", ["/dev/disk/by-id/ata-X"])
        with capture_logs() as logs:
            self.assertFalse(repo.create_pool(cmd))
        self.assertTrue(any("zpool create failed" in e for e in logs))

    def test_sudo_repository_prefixes_sudo(self):
        repo, calls = self._recording_repo(rc=0, sudo=True)
        repo.create_pool_dry_run(["zpool", "create", "tank", "/dev/disk/by-id/ata-X"])
        self.assertEqual(calls[0][0][:3], ["sudo", "zpool", "create"])

    def test_rejects_non_create_command(self):
        repo, _ = self._recording_repo()
        with self.assertRaises(ValueError):
            repo.create_pool_dry_run(["zpool", "list"])
        with self.assertRaises(ValueError):
            repo.create_pool(["zpool", "list"])


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


class TestZfsRepositoryVersion(unittest.TestCase):
    """version_output returns raw `zfs version` text."""

    def test_version_output_returns_stdout(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="zfs-2.3.1-1\nzfs-kmod-2.3.1-1\n", stderr=""
        )
        self.assertEqual(repo.version_output(), "zfs-2.3.1-1\nzfs-kmod-2.3.1-1\n")

    def test_version_output_returns_empty_on_failure(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom"
        )
        self.assertEqual(repo.version_output(), "")


class TestZfsRepositoryAshift(unittest.TestCase):
    """get_ashift combines `zpool get` and `zdb -C` fallback."""

    def test_configured_ashift_nonzero(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="12\n", stderr=""
        )
        self.assertEqual(repo.get_ashift("tank"), AshiftInfo("12", 12))

    def test_zero_configured_falls_back_to_zdb(self):
        repo = ZfsRepository(sudo=False)
        calls = []

        def _run(cmd, *args, **kwargs):
            calls.append(" ".join(str(c) for c in cmd))
            if "zpool get" in " ".join(str(c) for c in cmd):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="0\n")
            return subprocess.CompletedProcess(
                args=[], returncode=0, stdout="vdev_tree:\n  ashift: 13\n"
            )

        repo._run = _run
        self.assertEqual(repo.get_ashift("tank"), AshiftInfo("0", 13))

    def test_missing_configured_falls_back_to_zdb(self):
        repo = ZfsRepository(sudo=False)

        def _run(cmd, *args, **kwargs):
            if "zpool get" in " ".join(str(c) for c in cmd):
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="-\n")
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="ashift: 14\n")

        repo._run = _run
        self.assertEqual(repo.get_ashift("tank"), AshiftInfo("-", 14))

    def test_both_sources_fail(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="boom"
        )
        self.assertEqual(repo.get_ashift("tank"), AshiftInfo(None, None))


class TestZfsRepositoryTopology(unittest.TestCase):
    """pool_topology parses `zpool status -P` config into a typed tree."""

    _SAMPLE_STATUS = """\
  pool: fivebays
 state: ONLINE
config:

        NAME                                          STATE     READ WRITE CKSUM
        fivebays                                      ONLINE       0     0     0
          mirror-0                                    ONLINE       0     0     0
            /dev/disk/by-id/wwn-0x5000cca768cace55    ONLINE       0     0     0
            /dev/disk/by-id/wwn-0x5000cca768cace56    ONLINE       0     0     0
        logs
          mirror-1                                    ONLINE       0     0     0
            /dev/disk/by-id/wwn-0x5002538e41234567    ONLINE       0     0     0

errors: No known data errors
"""

    def test_parse_topology_returns_pool_root(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=self._SAMPLE_STATUS, stderr=""
        )
        topo = repo.pool_topology("fivebays")
        self.assertIsNotNone(topo)
        self.assertEqual(topo.name, "fivebays")
        self.assertEqual(topo.vdev_type, "pool")
        self.assertEqual(topo.state, "ONLINE")
        self.assertEqual(topo.read, 0)

    def test_parse_topology_vdevs_and_disks(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=self._SAMPLE_STATUS, stderr=""
        )
        topo = repo.pool_topology("fivebays")
        self.assertIsNotNone(topo)
        self.assertEqual(len(topo.children), 2)

        mirror = topo.children[0]
        self.assertEqual(mirror.vdev_type, "mirror")
        self.assertEqual(len(mirror.children), 2)
        self.assertEqual(mirror.children[0].vdev_type, "disk")
        self.assertTrue(mirror.children[0].name.startswith("/dev/disk/by-id"))

        log_group = topo.children[1]
        self.assertEqual(log_group.vdev_type, "log")
        self.assertEqual(len(log_group.children), 1)
        self.assertEqual(log_group.children[0].vdev_type, "mirror")

    def test_parse_topology_empty_on_missing_config(self):
        repo = ZfsRepository(sudo=False)
        repo._run = lambda *a, **k: subprocess.CompletedProcess(
            args=[], returncode=0, stdout="pool: tank\nstate: ONLINE\n", stderr=""
        )
        self.assertIsNone(repo.pool_topology("tank"))

    def test_parse_topology_static_helper(self):
        root = ZfsRepository._parse_topology(self._SAMPLE_STATUS)
        self.assertIsNotNone(root)
        self.assertEqual(root.name, "fivebays")
