"""Tests for diagnose_zfs_repository.py — ZFS repository diagnostic script."""

import contextlib
import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import diagnose_zfs_repository


def _row(name, ds_type):
    """Build a dataset row stand-in like the ones ZfsRepository returns."""
    return SimpleNamespace(name=name, ds_type=ds_type)


def _run_main(repo):
    """Run diagnose main() with *repo* patched in, returning captured stdout."""
    buf = io.StringIO()
    with patch.object(diagnose_zfs_repository, "ZfsRepository", return_value=repo):
        with contextlib.redirect_stdout(buf):
            diagnose_zfs_repository.main()
    return buf.getvalue()


class TestDiagnoseZfsRepository(unittest.TestCase):
    """main() drives ZfsRepository and reports each step on stdout."""

    def _repo(self, pools, datasets=None, snapshots=None):
        repo = MagicMock()
        repo.list_pools.return_value = pools
        repo.list_datasets.side_effect = datasets if datasets is not None else [[], []]
        repo.list_snapshots.return_value = snapshots if snapshots is not None else []
        return repo

    def test_main_constructs_sudo_repository(self):
        repo = self._repo(pools=[])
        with patch.object(diagnose_zfs_repository, "ZfsRepository") as cls:
            cls.return_value = repo
            with contextlib.redirect_stdout(io.StringIO()):
                diagnose_zfs_repository.main()
        cls.assert_called_once_with(sudo=True)

    def test_main_lists_pools_datasets_snapshots_and_children(self):
        rows = [
            _row("tank", "filesystem"),
            _row("tank/proxmox", "filesystem"),
            _row("tank/vm-100-disk-0", "volume"),
        ]
        repo = self._repo(
            pools=[SimpleNamespace(name="tank")],
            datasets=[rows, [_row("tank/proxmox/iso", "filesystem")]],
            snapshots=[SimpleNamespace(name="tank/vm-100-disk-0@snap1")],
        )

        out = _run_main(repo)

        self.assertIn("Pools found: 1", out)
        self.assertIn("tank", out)
        self.assertIn("Rows returned: 3", out)
        self.assertIn("Snapshots returned: 1", out)
        self.assertIn("Children returned: 1", out)
        # The snapshot candidate is the leafiest nested filesystem/volume row.
        repo.list_snapshots.assert_called_once_with("tank/vm-100-disk-0", depth=0)
        repo.list_datasets.assert_any_call(pool="tank", depth=1)
        repo.list_datasets.assert_any_call(pool="tank/vm-100-disk-0", depth=1)

    def test_main_reports_no_pools(self):
        repo = self._repo(pools=[])

        out = _run_main(repo)

        self.assertIn("No pools to test.", out)
        repo.list_datasets.assert_not_called()

    def test_main_pool_listing_error_is_reported(self):
        repo = self._repo(pools=[])
        repo.list_pools.side_effect = RuntimeError("zpool exploded")

        out = _run_main(repo)

        self.assertIn("ERROR: zpool exploded", out)
        repo.list_datasets.assert_not_called()

    def test_main_reports_no_nested_datasets(self):
        rows = [_row("tank", "filesystem"), _row("tank@snap", "snapshot")]
        repo = self._repo(pools=[SimpleNamespace(name="tank")], datasets=[rows, []])

        out = _run_main(repo)

        self.assertIn("No nested datasets found to test snapshot loading.", out)
        repo.list_snapshots.assert_not_called()

    def test_main_dataset_error_is_reported_and_continues(self):
        repo = self._repo(pools=[SimpleNamespace(name="tank")])
        repo.list_datasets.side_effect = RuntimeError("zfs list failed")

        out = _run_main(repo)

        self.assertIn("ERROR: zfs list failed", out)
        # With no rows after the failure, main stops before the snapshot step.
        self.assertIn("No nested datasets found to test snapshot loading.", out)
        repo.list_snapshots.assert_not_called()


if __name__ == "__main__":
    unittest.main()
