"""Tests for datasets tree lazy loading in gui_helpers.py."""

import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

from zfs_repository import ZfsRepository
from gui_helpers import on_row_expanded, build_full_dataset_name


SNAPSHOT_CMD = (
    "zfs list -t snapshot -H -o name,creation,type,used,avail,refer,origin,clones -d 1"
)
DATASET_CMD = (
    "zfs list -H -o name,creation,type,used,avail,refer,origin,clones -r -d 1"
)


def _make_repo(stdout_map):
    """Return a ZfsRepository whose _run returns canned stdout per command."""
    repo = ZfsRepository(sudo=False)

    def _run(cmd, check=True, timeout=None):
        cmd_str = " ".join(cmd)
        stdout = stdout_map.get(cmd_str, "")
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout=stdout, stderr=""
        )

    repo._run = _run
    return repo


class TestDatasetRowExpansion(unittest.TestCase):
    """Expanding a dataset row loads snapshots and sub-datasets."""

    def _tree_with_dataset(self):
        store = Gtk.TreeStore(str, str, str, str, str, str, str, bool)
        root = store.append(None, ["threeamigos", "", "", "", "", "", "", False])
        ds = store.append(root, ["proxmox", "", "filesystem", "", "", "", "", False])
        store.append(ds, ["(loading...)", "", "", "", "", "", "", True])
        view = Gtk.TreeView(model=store)
        return store, view, ds

    def test_build_full_dataset_name_for_child(self):
        store, _view, ds = self._tree_with_dataset()
        self.assertEqual(build_full_dataset_name(store, ds), "threeamigos/proxmox")

    def test_expansion_loads_snapshots_and_subdatasets(self):
        repo = _make_repo({
            f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
            ),
            f"{DATASET_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\n"
                "threeamigos/proxmox/vm-100\t2025-01-01\tvolume\t5G\t-\t5G\t-\t-\n"
            ),
        })
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = []
        child = store.iter_children(ds)
        while child:
            children.append((store.get_value(child, 0), store.get_value(child, 2)))
            child = store.iter_next(child)

        self.assertEqual(children, [
            ("@snap1", "snapshot"),
            ("vm-100", "volume"),
        ])

    def test_expansion_loads_only_exact_dataset_snapshots(self):
        repo = _make_repo({
            f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                # depth=1 also returns snapshots of direct children, which must be filtered out
                "threeamigos/proxmox/sub@snap2\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
            ),
            f"{DATASET_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\n"
                "threeamigos/proxmox/sub\t2025-01-01\tfilesystem\t1G\t-\t1G\t-\t-\n"
            ),
        })
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = []
        child = store.iter_children(ds)
        while child:
            children.append((store.get_value(child, 0), store.get_value(child, 2)))
            child = store.iter_next(child)

        # snap2 belongs to proxmox/sub, not proxmox, so it must not appear
        self.assertIn(("@snap1", "snapshot"), children)
        self.assertIn(("sub", "filesystem"), children)
        self.assertNotIn(("@snap2", "snapshot"), children)

    def test_expansion_shows_empty_placeholder_when_no_children(self):
        repo = _make_repo({
            f"{SNAPSHOT_CMD} threeamigos/proxmox": "",
            f"{DATASET_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\n"
            ),
        })
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = []
        child = store.iter_children(ds)
        while child:
            children.append(store.get_value(child, 0))
            child = store.iter_next(child)

        self.assertEqual(children, ["(empty)"])

    def test_expansion_filters_child_snapshots_at_depth_one(self):
        """depth=1 returns child snapshots; only the target dataset's are shown."""
        repo = _make_repo({
            f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                "threeamigos/proxmox/sub@snap2\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                "threeamigos/proxmox/sub/deeper@snap3\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
            ),
            f"{DATASET_CMD} threeamigos/proxmox": (
                "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\n"
            ),
        })
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = [store.get_value(c, 0) for c in self._iter_children(store, ds)]
        self.assertEqual(children, ["@snap1"])

    def _iter_children(self, store, parent_iter):
        """Yield direct child iters of parent_iter."""
        child = store.iter_children(parent_iter)
        while child:
            yield child
            child = store.iter_next(child)

    def test_expansion_uses_view_repository(self):
        """The repo attached to the view is used, not the module default."""
        repo = _make_repo({
            f"{SNAPSHOT_CMD} threeamigos/proxmox": "",
            f"{DATASET_CMD} threeamigos/proxmox": "",
        })
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))
        # If the default repository had been used, the command would have failed
        # or returned real system data; we only expect the placeholder.
        child = store.iter_children(ds)
        self.assertIsNotNone(child)
        self.assertEqual(store.get_value(child, 0), "(empty)")


if __name__ == "__main__":
    unittest.main()
