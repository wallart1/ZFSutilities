"""Tests for gui_helpers.diagnose_dataset_busy."""

import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "07 GTK + Python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

from test_support import capture_logs, mock_subprocess

import gui_helpers


class TestDiagnoseDatasetBusy(unittest.TestCase):
    """Verify diagnose_dataset_busy detects each known cause."""

    def _make_completed(self, stdout="", stderr="", rc=0):
        import subprocess
        return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)

    def _zfs_get_handler(self, cmd, **kwargs):
        """Custom handler for 'zfs get -H -o value <prop> <target>'."""
        # cmd is like ["zfs", "get", "-H", "-o", "value", "mounted", "pool/fs"]
        prop = cmd[-2]
        target = cmd[-1]
        key = f"{target}:{prop}"
        value = self._mock_props.get(key, "-")
        return self._make_completed(value)

    def test_clone_dependents_snapshot(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs@snap1:mounted": "no",
                "pool/fs@snap1:receive_resume_token": "-",
                "pool/fs@snap1:clones": "pool/fs/clone1",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            gui_helpers.diagnose_dataset_busy("pool/fs@snap1")
        self.assertTrue(any("clone dependents" in m for m in logs))

    def test_holds(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs@snap1:mounted": "no",
                "pool/fs@snap1:receive_resume_token": "-",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            ms.set_command_handler(
                r"zfs holds -H pool/fs@snap1",
                lambda _cmd, **_kw: self._make_completed("pool/fs@snap1\toffsite\t2025-01-01"),
            )
            gui_helpers.diagnose_dataset_busy("pool/fs@snap1")
        self.assertTrue(any("has holds" in m and "offsite" in m for m in logs))

    def test_mounted_open_files(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs:mounted": "yes",
                "pool/fs:mountpoint": "/mnt/pool/fs",
                "pool/fs:receive_resume_token": "-",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            ms.set_command_handler(
                r"fuser -m /mnt/pool/fs",
                lambda _cmd, **_kw: self._make_completed("/mnt/pool/fs: 1234"),
            )
            ms.set_command_handler(
                r"ps -p 1234 -o comm=",
                lambda _cmd, **_kw: self._make_completed("bash"),
            )
            gui_helpers.diagnose_dataset_busy("pool/fs")
        self.assertTrue(any("mounted at /mnt/pool/fs" in m for m in logs))
        self.assertTrue(any("Open processes" in m for m in logs))

    def test_resume_token(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs:mounted": "no",
                "pool/fs:receive_resume_token": "1-8e3b9c1e2-100",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            gui_helpers.diagnose_dataset_busy("pool/fs")
        self.assertTrue(any("resume token" in m for m in logs))

    def test_iscsi_lun(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/proxmox/vm-105-disk-0:mounted": "no",
                "pool/proxmox/vm-105-disk-0:receive_resume_token": "-",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            ms.set_command_handler(
                r"targetcli /backstores/block ls",
                lambda _cmd, **_kw: self._make_completed("  | o- vm-105-disk-0  [block/vm-105-disk-0]"),
            )
            ms.set_command_handler(
                r"targetcli /iscsi ls",
                lambda _cmd, **_kw: self._make_completed("iqn.2025-01.local.storage"),
            )
            ms.set_command_handler(
                r"targetcli /iscsi/iqn.2025-01.local.storage/tpg1/luns ls",
                lambda _cmd, **_kw: self._make_completed("  | o- lun0  [block/vm-105-disk-0]"),
            )
            gui_helpers.diagnose_dataset_busy("pool/proxmox/vm-105-disk-0")
        self.assertTrue(any("iSCSI LUN" in m for m in logs))

    def test_running_vm(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/proxmox/vm-105-disk-0:mounted": "no",
                "pool/proxmox/vm-105-disk-0:receive_resume_token": "-",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            ms.set_command_handler(
                r"qm status 105",
                lambda _cmd, **_kw: self._make_completed("status: running"),
            )
            gui_helpers.diagnose_dataset_busy("pool/proxmox/vm-105-disk-0")
        self.assertTrue(any("VM 105 is RUNNING" in m for m in logs))

    def test_nfs_share(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs:mounted": "no",
                "pool/fs:receive_resume_token": "-",
                "pool/fs:sharenfs": "rw=@192.168.1.0/24",
                "pool/fs:sharesmb": "off",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            gui_helpers.diagnose_dataset_busy("pool/fs")
        self.assertTrue(any("shared via NFS" in m for m in logs))

    def test_fallback(self):
        with capture_logs() as logs, mock_subprocess() as ms:
            self._mock_props = {
                "pool/fs:mounted": "no",
                "pool/fs:receive_resume_token": "-",
            }
            ms.set_command_handler(r"zfs get -H -o value", self._zfs_get_handler)
            gui_helpers.diagnose_dataset_busy("pool/fs")
        self.assertTrue(any("No specific cause identified" in m for m in logs))


if __name__ == "__main__":
    unittest.main()
