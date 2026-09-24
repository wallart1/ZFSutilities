"""Tests for datasets tree lazy loading in gui_helpers.py."""

import os
import subprocess
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import import_or_skip_gi, requires_gi

pytestmark = requires_gi

gi = import_or_skip_gi("gi")

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
from gui_helpers import (
    build_full_dataset_name,
    find_tree_iter_by_full_name,
    get_tree_selection_items,
    on_row_expanded,
    reload_row_children,
)
from zfs_repository import ZfsRepository

SNAPSHOT_CMD = "zfs list -t snapshot -H -o name,creation,type,used,avail,refer,origin,clones -d 1"
DATASET_CMD = "zfs list -H -o name,creation,type,used,avail,refer,origin,clones,mounted -r -d 1"


def _make_repo(stdout_map):
    """Return a ZfsRepository whose _run returns canned stdout per command."""
    repo = ZfsRepository(sudo=False)

    def _run(cmd, check=True, timeout=None):
        cmd_str = " ".join(cmd)
        stdout = stdout_map.get(cmd_str, "")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    repo._run = _run
    return repo


class TestDatasetRowExpansion(unittest.TestCase):
    """Expanding a dataset row loads snapshots and sub-datasets."""

    def _tree_with_dataset(self):
        store = Gtk.TreeStore(str, str, str, str, str, str, str, bool, bool, str)
        root = store.append(None, ["threeamigos", "", "", "", "", "", "", False, True, None])
        ds = store.append(root, ["proxmox", "", "filesystem", "", "", "", "", False, True, None])
        store.append(ds, ["(loading...)", "", "", "", "", "", "", True, False, None])
        view = Gtk.TreeView(model=store)
        return store, view, ds

    def test_build_full_dataset_name_for_child(self):
        store, _view, ds = self._tree_with_dataset()
        self.assertEqual(build_full_dataset_name(store, ds), "threeamigos/proxmox")

    def test_expansion_loads_snapshots_and_subdatasets(self):
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                    "threeamigos/proxmox/vm-100\t2025-01-01\tvolume\t5G\t-\t5G\t-\t-\tyes\n"
                ),
            }
        )
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = []
        child = store.iter_children(ds)
        while child:
            children.append((store.get_value(child, 0), store.get_value(child, 2)))
            child = store.iter_next(child)

        self.assertEqual(
            children,
            [
                ("@snap1", "snapshot"),
                ("vm-100", "volume"),
            ],
        )

    def test_expansion_loads_only_exact_dataset_snapshots(self):
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                    # depth=1 also returns snapshots of direct children, which must be filtered out
                    "threeamigos/proxmox/sub@snap2\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                    "threeamigos/proxmox/sub\t2025-01-01\tfilesystem\t1G\t-\t1G\t-\t-\tyes\n"
                ),
            }
        )
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
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": "",
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
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
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                    "threeamigos/proxmox/sub@snap2\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                    "threeamigos/proxmox/sub/deeper@snap3\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        children = [store.get_value(c, 0) for c in self._iter_children(store, ds)]
        self.assertEqual(children, ["@snap1"])

    def test_unmounted_dataset_gets_teal_foreground(self):
        """An unmounted child dataset is tinted in the unmounted text color."""
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": "",
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                    "threeamigos/proxmox/sub\t2025-01-01\tfilesystem\t1G\t-\t1G\t-\t-\tno\n"
                ),
            }
        )
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))

        sub = None
        child = store.iter_children(ds)
        while child:
            if store.get_value(child, 0) == "sub":
                sub = child
                break
            child = store.iter_next(child)
        self.assertIsNotNone(sub)
        self.assertFalse(store.get_value(sub, 8))
        self.assertEqual(store.get_value(sub, 9), "#00797A")

    def test_mounted_snapshot_is_not_tinted(self):
        """A snapshot that is explicitly mounted is not tinted."""
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
        # Simulate the snapshot being explicitly mounted.
        mount_output = "threeamigos/proxmox@snap1 on /threeamigos/proxmox/.zfs/snapshot/snap1"

        def _mock_subprocess_run(cmd, **kwargs):
            if cmd[:3] == ["mount", "-t", "zfs"]:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=mount_output, stderr=""
                )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        with patch("subprocess.run", side_effect=_mock_subprocess_run):
            on_row_expanded(view, ds, store.get_path(ds))

        snap = None
        child = store.iter_children(ds)
        while child:
            if store.get_value(child, 0) == "@snap1":
                snap = child
                break
            child = store.iter_next(child)
        self.assertIsNotNone(snap)
        self.assertTrue(store.get_value(snap, 8))
        self.assertIsNone(store.get_value(snap, 9))

    def test_automounted_snapshot_without_at_is_not_tinted(self):
        """A snapshot automounted via .zfs/snapshot is detected without an @ source."""
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
        # Automount entries list the source as dataset/.zfs/snapshot/snap.
        mount_output = (
            "threeamigos/proxmox/.zfs/snapshot/snap1 on /threeamigos/proxmox/.zfs/snapshot/snap1"
        )

        def _mock_subprocess_run(cmd, **kwargs):
            if cmd[:3] == ["mount", "-t", "zfs"]:
                return subprocess.CompletedProcess(
                    args=cmd, returncode=0, stdout=mount_output, stderr=""
                )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        with patch("subprocess.run", side_effect=_mock_subprocess_run):
            on_row_expanded(view, ds, store.get_path(ds))

        snap = None
        child = store.iter_children(ds)
        while child:
            if store.get_value(child, 0) == "@snap1":
                snap = child
                break
            child = store.iter_next(child)
        self.assertIsNotNone(snap)
        self.assertTrue(store.get_value(snap, 8))
        self.assertIsNone(store.get_value(snap, 9))

    def test_snapshot_accessible_via_zfs_directory_is_tinted_when_not_mounted(self):
        """A snapshot whose .zfs/snapshot stub exists but is not mounted is tinted.

        The .zfs/snapshot/<snap> directory is an automount stub that exists
        (and can auto-mount on access) even after the snapshot is unmounted,
        so mount state must come from ``mount -t zfs``, not from ``isdir``.
        """
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/proxmox": (
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )

        def _mock_subprocess_run(cmd, **kwargs):
            if cmd[:3] == ["mount", "-t", "zfs"]:
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        with patch("subprocess.run", side_effect=_mock_subprocess_run):
            on_row_expanded(view, ds, store.get_path(ds))

        snap = None
        child = store.iter_children(ds)
        while child:
            if store.get_value(child, 0) == "@snap1":
                snap = child
                break
            child = store.iter_next(child)
        self.assertIsNotNone(snap)
        self.assertFalse(store.get_value(snap, 8))
        self.assertEqual(store.get_value(snap, 9), "#00797A")

    def _iter_children(self, store, parent_iter):
        """Yield direct child iters of parent_iter."""
        child = store.iter_children(parent_iter)
        while child:
            yield child
            child = store.iter_next(child)

    def test_expansion_uses_view_repository(self):
        """The repo attached to the view is used, not the module default."""
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos/proxmox": "",
                f"{DATASET_CMD} threeamigos/proxmox": "",
            }
        )
        store, view, ds = self._tree_with_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, ds, store.get_path(ds))
        # If the default repository had been used, the command would have failed
        # or returned real system data; we only expect the placeholder.
        child = store.iter_children(ds)
        self.assertIsNotNone(child)
        self.assertEqual(store.get_value(child, 0), "(empty)")


class TestRootDatasetExpansion(unittest.TestCase):
    """Top-level rows are pool root datasets and expand like any dataset."""

    def _tree_with_root_dataset(self):
        store = Gtk.TreeStore(str, str, str, str, str, str, str, bool, bool, str)
        root = store.append(
            None,
            [
                "threeamigos",
                "Mon Jan 1 00:00 2024",
                "filesystem",
                "100G",
                "500G",
                "50G",
                "",
                False,
                True,
                None,
            ],
        )
        store.append(root, ["(loading...)", "", "", "", "", "", "", True, False, None])
        view = Gtk.TreeView(model=store)
        return store, view, root

    def test_root_dataset_expansion_loads_snapshots_and_children(self):
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos": (
                    "threeamigos@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos": (
                    "threeamigos\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                    "threeamigos/proxmox\t2025-01-01\tfilesystem\t5G\t-\t5G\t-\t-\tyes\n"
                ),
            }
        )
        store, view, root = self._tree_with_root_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, root, store.get_path(root))

        children = [
            (store.get_value(c, 0), store.get_value(c, 2)) for c in self._iter_children(store, root)
        ]
        self.assertEqual(children, [("@snap1", "snapshot"), ("proxmox", "filesystem")])

    def test_root_dataset_with_snapshots_shows_no_placeholder(self):
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos": (
                    "threeamigos@snap1\t2025-01-01\tsnapshot\t0B\t-\t50G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos": (
                    "threeamigos\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
        store, view, root = self._tree_with_root_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, root, store.get_path(root))

        children = [store.get_value(c, 0) for c in self._iter_children(store, root)]
        self.assertEqual(children, ["@snap1"])
        self.assertNotIn("(no datasets)", children)
        self.assertNotIn("(empty)", children)

    def test_root_dataset_with_no_children_shows_empty_placeholder(self):
        repo = _make_repo(
            {
                f"{SNAPSHOT_CMD} threeamigos": "",
                f"{DATASET_CMD} threeamigos": (
                    "threeamigos\t2025-01-01\tfilesystem\t100G\t500G\t50G\t-\t-\tyes\n"
                ),
            }
        )
        store, view, root = self._tree_with_root_dataset()
        view._zfs_repo = repo
        on_row_expanded(view, root, store.get_path(root))

        children = [store.get_value(c, 0) for c in self._iter_children(store, root)]
        self.assertEqual(children, ["(empty)"])

    def _iter_children(self, store, parent_iter):
        child = store.iter_children(parent_iter)
        while child:
            yield child
            child = store.iter_next(child)


if __name__ == "__main__":
    unittest.main()


def _tree_with_volume():
    """Pool root with a volume child ready for expansion."""
    store = Gtk.TreeStore(str, str, str, str, str, str, str, bool, bool, str)
    root = store.append(None, ["threeamigos", "", "", "", "", "", "", False, True, None])
    vol = store.append(root, ["vm-100", "", "volume", "", "", "", "", False, False, None])
    store.append(vol, ["(loading...)", "", "", "", "", "", "", True, False, None])
    view = Gtk.TreeView(model=store)
    return store, view, vol


class TestVolumeLoopExpansion(unittest.TestCase):
    """Volume rows list loop partitions when a loop device is attached."""

    _VOL = "threeamigos/vm-100"
    _FIND_CMD = "losetup -j /dev/zvol/threeamigos/vm-100"
    _LSBLK_CMD = "lsblk --json --output NAME,TYPE,FSTYPE,MOUNTPOINT,SIZE /dev/loop0"

    _LSBLK_WITH_PARTS = """
    {
      "blockdevices": [
        {
          "name": "loop0", "type": "loop", "fstype": null, "mountpoint": null,
          "children": [
            {"name": "loop0p1", "type": "part", "fstype": "ext4",
             "mountpoint": null, "size": "4G"},
            {"name": "loop0p2", "type": "part", "fstype": null,
             "mountpoint": null, "size": "1G"}
          ]
        }
      ]
    }
    """

    def _attached_repo(self):
        return _make_repo(
            {
                self._FIND_CMD: "/dev/loop0: []: (/dev/zvol/threeamigos/vm-100)\n",
                self._LSBLK_CMD: self._LSBLK_WITH_PARTS,
            }
        )

    def test_expansion_lists_loop_partitions(self):
        store, view, vol = _tree_with_volume()
        view._zfs_repo = self._attached_repo()
        on_row_expanded(view, vol, store.get_path(vol))

        children = []
        child = store.iter_children(vol)
        while child:
            children.append(
                (
                    store.get_value(child, 0),
                    store.get_value(child, 2),
                    store.get_value(child, 8),
                )
            )
            child = store.iter_next(child)

        self.assertEqual(
            children,
            [
                ("loop0p1", "ext4", False),
                ("loop0p2", "No filesystem", False),
            ],
        )

    def test_expansion_without_loop_shows_no_partitions(self):
        store, view, vol = _tree_with_volume()
        view._zfs_repo = _make_repo({})  # losetup -j returns nothing
        on_row_expanded(view, vol, store.get_path(vol))

        names = []
        child = store.iter_children(vol)
        while child:
            names.append(store.get_value(child, 0))
            child = store.iter_next(child)

        self.assertEqual(names, ["(empty)"])

    def test_bare_loop_device_with_fs_listed_as_single_row(self):
        lsblk_bare = """
        {
          "blockdevices": [
            {"name": "loop0", "type": "loop", "fstype": "xfs",
             "mountpoint": null, "size": "50G"}
          ]
        }
        """
        store, view, vol = _tree_with_volume()
        view._zfs_repo = _make_repo(
            {
                self._FIND_CMD: "/dev/loop0: []: (/dev/zvol/threeamigos/vm-100)\n",
                self._LSBLK_CMD: lsblk_bare,
            }
        )
        on_row_expanded(view, vol, store.get_path(vol))

        child = store.iter_children(vol)
        self.assertEqual(store.get_value(child, 0), "loop0")
        self.assertEqual(store.get_value(child, 2), "xfs")

    def test_selection_items_for_partitions(self):
        store, view, vol = _tree_with_volume()
        view._zfs_repo = self._attached_repo()
        on_row_expanded(view, vol, store.get_path(vol))

        # Select only the first partition row (loop0p1, has filesystem).
        part = store.iter_children(vol)
        selection = view.get_selection()
        selection.get_selected_rows = lambda: (store, [store.get_path(part)])
        items = get_tree_selection_items(view)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "volume-partition")
        self.assertEqual(items[0]["device"], "/dev/loop0p1")
        self.assertEqual(items[0]["volume"], self._VOL)
        self.assertEqual(items[0]["fstype"], "ext4")
        self.assertTrue(items[0]["has_filesystem"])

        # Second partition row (loop0p2) has no filesystem.
        nofs = store.iter_next(part)
        selection.get_selected_rows = lambda: (store, [store.get_path(nofs)])
        items = get_tree_selection_items(view)
        self.assertEqual(items[0]["fstype"], "No filesystem")
        self.assertFalse(items[0]["has_filesystem"])

    def test_snapshot_rows_under_volume_are_not_partitions(self):
        store, view, vol = _tree_with_volume()
        repo = _make_repo(
            {
                self._FIND_CMD: "/dev/loop0: []: (/dev/zvol/threeamigos/vm-100)\n",
                self._LSBLK_CMD: self._LSBLK_WITH_PARTS,
                f"{SNAPSHOT_CMD} threeamigos/vm-100": (
                    "threeamigos/vm-100@snap1\t2025-01-01\tsnapshot\t0B\t-\t5G\t-\t-\n"
                ),
                f"{DATASET_CMD} threeamigos/vm-100": (
                    "threeamigos/vm-100\t2025-01-01\tvolume\t5G\t-\t5G\t-\t-\t-\n"
                ),
            }
        )
        view._zfs_repo = repo
        on_row_expanded(view, vol, store.get_path(vol))

        # Select the snapshot row (children order: partitions, then @snap1).
        snap_iter = None
        child = store.iter_children(vol)
        while child:
            if store.get_value(child, 0).startswith("@"):
                snap_iter = child
                break
            child = store.iter_next(child)
        self.assertIsNotNone(snap_iter)
        selection = view.get_selection()
        selection.get_selected_rows = lambda: (store, [store.get_path(snap_iter)])
        items = get_tree_selection_items(view)
        self.assertEqual(items[0]["type"], "snapshot")

    def test_reload_row_children_after_detach(self):
        store, view, vol = _tree_with_volume()
        view._zfs_repo = self._attached_repo()
        on_row_expanded(view, vol, store.get_path(vol))
        self.assertIsNotNone(store.iter_children(vol))

        found = find_tree_iter_by_full_name(store, self._VOL)
        self.assertIsNotNone(found)

        # Detach: losetup -j now finds nothing; children collapse to "(empty)".
        store.set_value(vol, 7, True)
        reload_row_children(store, vol, repo=_make_repo({}))
        names = []
        child = store.iter_children(vol)
        while child:
            names.append(store.get_value(child, 0))
            child = store.iter_next(child)
        self.assertEqual(names, ["(empty)"])
