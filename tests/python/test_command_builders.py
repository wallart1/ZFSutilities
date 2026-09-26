"""Tests for command_builders.py — rsync, send/receive, retention commands.

Command-line construction is asserted via golden files (see golden.py);
branching, gating, metadata, ordering, and negative assertions stay here.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (PYTHON_SRC, TEST_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import command_builders
import golden
from command_builders import BashStep


class TestDryrunAssignments(unittest.TestCase):
    def test_no_dryrun_empty(self):
        result = command_builders._dryrun_assignments(dryrun=False)
        self.assertEqual(result, "")

    def test_dryrun_sets_dryrun(self):
        result = command_builders._dryrun_assignments(dryrun=True)
        self.assertIn("dryrun='Y'", result)


class TestLocalHostname(unittest.TestCase):
    def test_get_local_hostname_no_domain(self):
        hn = command_builders._get_local_hostname()
        self.assertNotIn(".", hn)

    def test_is_local_host_empty(self):
        self.assertTrue(command_builders._is_local_host(""))

    def test_is_local_host_matches_hostname(self):
        hn = command_builders._get_local_hostname()
        self.assertTrue(command_builders._is_local_host(hn))


class TestParseRsyncEndpoint(unittest.TestCase):
    def test_local_absolute_path(self):
        host, path = command_builders.parse_rsync_endpoint("/mnt/backup")
        self.assertIsNone(host)
        self.assertEqual(path, "/mnt/backup")

    def test_remote_path(self):
        host, path = command_builders.parse_rsync_endpoint("server:/mnt/backup")
        self.assertEqual(host, "server")
        self.assertEqual(path, "/mnt/backup")

    def test_local_host_normalization(self):
        hn = command_builders._get_local_hostname()
        host, path = command_builders.parse_rsync_endpoint(f"{hn}:/mnt/backup")
        self.assertIsNone(host)
        self.assertEqual(path, "/mnt/backup")


class TestBuildRsyncCommand(unittest.TestCase):
    def test_local_rsync(self):
        step = command_builders.build_rsync_command("/src", "/dst")
        self.assertIsInstance(step, BashStep)
        self.assertTrue(step.is_rsync)
        self.assertFalse(step.fatal)
        golden.check(self, step.command)

    def test_pull_rsync(self):
        step = command_builders.build_rsync_command("remote:/src", "/dst")
        self.assertIn("pull", step.description)
        golden.check(self, step.command)

    def test_push_rsync(self):
        step = command_builders.build_rsync_command("/src", "remote:/dst")
        self.assertIn("push", step.description)
        golden.check(self, step.command)

    def test_pull_rsync_without_remote_log_uses_plain_command(self):
        step = command_builders.build_rsync_command("remote:/src", "/dst")
        golden.check(self, step.command)

    def test_pull_rsync_with_remote_log_uses_bash_wrapper(self):
        step = command_builders.build_rsync_command(
            "remote:/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        golden.check(self, step.command)

    def test_local_rsync_with_remote_log_uses_bash_wrapper(self):
        step = command_builders.build_rsync_command(
            "/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        golden.check(self, step.command)

    def test_local_rsync_without_remote_log_uses_plain_command(self):
        step = command_builders.build_rsync_command("/src", "/dst")
        golden.check(self, step.command)

    def test_local_rsync_log_setup_script(self):
        script = command_builders._rsync_log_setup_script("/var/log/zfsutilities/rsync-pull.log")
        golden.check(self, script)

    def test_local_host_pull_with_remote_log_uses_bash_wrapper(self):
        # Source host matching the local hostname is normalized to a local path,
        # but with remote_log_path set it should still use the log wrapper.
        # The hostname is machine-dependent, so normalize it to a placeholder
        # to keep the golden machine-independent.
        hn = command_builders._get_local_hostname()
        step = command_builders.build_rsync_command(
            f"{hn}:/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        command = list(step.command)
        command[2] = command[2].replace(hn, "LOCALHOST")
        golden.check(self, command)

    def test_local_rsync_with_remote_log_preserves_exit_code(self):
        step = command_builders.build_rsync_command(
            "/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        script = step.command[2]
        golden.check(self, step.command)
        # rsync is the last command, so the script exits with rsync's rc.
        self.assertNotIn("exit ${PIPESTATUS[0]}", script)
        self.assertNotIn("exit 0", script)

    def test_rsync_log_setup_script_used_in_ssh_command(self):
        host = "remote"
        log_path = "/var/log/zfsutilities/rsync-pull.log"
        cmd = [
            "ssh",
            "-q",
            f"root@{host}",
            command_builders._rsync_log_setup_script(log_path),
        ]
        golden.check(self, cmd)

    def test_pull_rsync_with_remote_log_preserves_exit_code(self):
        step = command_builders.build_rsync_command(
            "remote:/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        golden.check(self, step.command)

    def test_local_rsync_with_excludes(self):
        step = command_builders.build_rsync_command("/src", "/dst", excludes=["*.tmp", "cache/"])
        golden.check(self, step.command)

    def test_pull_rsync_with_excludes(self):
        step = command_builders.build_rsync_command("remote:/src", "/dst", excludes=["*.log"])
        golden.check(self, step.command)

    def test_push_rsync_with_excludes(self):
        step = command_builders.build_rsync_command("/src", "remote:/dst", excludes=["temp"])
        golden.check(self, step.command)

    def test_local_rsync_with_remote_log_and_excludes(self):
        step = command_builders.build_rsync_command(
            "/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
            excludes=["*.tmp"],
        )
        golden.check(self, step.command)

    def test_pull_rsync_with_remote_log_and_excludes(self):
        step = command_builders.build_rsync_command(
            "remote:/src",
            "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
            excludes=["*.tmp"],
        )
        golden.check(self, step.command)

    def test_default_excludes_are_included(self):
        step = command_builders.build_rsync_command("/src", "/dst")
        golden.check(self, step.command)

    def test_default_excludes_are_included_with_empty_caller_excludes(self):
        step = command_builders.build_rsync_command("/src", "/dst", excludes=[])
        golden.check(self, step.command)

    def test_user_excludes_follow_defaults(self):
        step = command_builders.build_rsync_command("/src", "/dst", excludes=["*.tmp"])
        golden.check(self, step.command)
        gvfs_idx = step.command.index("--exclude=**/.gvfs/")
        cache_idx = step.command.index("--exclude=**/.cache/doc/")
        user_idx = step.command.index("--exclude=*.tmp")
        self.assertLess(gvfs_idx, user_idx)
        self.assertLess(cache_idx, user_idx)


class TestSendReceiveMetadata(unittest.TestCase):
    """build_send_receive_command attaches source/dest/label metadata."""

    def test_send_receive_step_has_metadata(self):
        variables = {"label": "dailybackup"}
        step = command_builders.build_send_receive_command(
            "threeamigos/proxmox",
            "fivebays/threeamigos/proxmox",
            variables,
            "/usr/local/lib/zfsutilities/current/bin",
            "@dailybackup-2026-06-11T12:00-d",
            dryrun=False,
        )
        self.assertIsNotNone(step.metadata)
        self.assertEqual(step.metadata["source"], "threeamigos/proxmox")
        self.assertEqual(step.metadata["dest"], "fivebays/threeamigos/proxmox")
        self.assertEqual(step.metadata["label"], "dailybackup")

    def test_send_receive_step_metadata_defaults_label(self):
        step = command_builders.build_send_receive_command(
            "tank/src",
            "backup/tank/src",
            {},
            "/usr/local/lib/zfsutilities/current/bin",
            "@dailybackup-2026-06-11T12:00-d",
            dryrun=False,
        )
        self.assertEqual(step.metadata["label"], "dailybackup")


class TestBuildSendReceiveCommand(unittest.TestCase):
    def test_includes_basic_variables(self):
        variables = {
            "doincrementals": "Y",
            "dointermediates": "N",
            "allow_destructive": "N",
            "receive_F_option": "F",
            "releaseholds": "N",
            "autoresume": "Y",
            "verify_after_transfer": "Y",
        }
        step = command_builders.build_send_receive_command(
            "tank/src", "tank/dst", variables, "/opt/bin", "@snap", dryrun=False
        )
        self.assertIsInstance(step, BashStep)
        self.assertFalse(step.is_rsync)
        self.assertTrue(step.fatal)
        golden.check(self, step.command)

    def test_includes_array(self):
        variables = {"includes": "foo bar"}
        step = command_builders.build_send_receive_command("src", "dst", variables, "/bin", "@snap")
        golden.check(self, step.command)

    def test_excludes_array(self):
        variables = {"excludes": "temp cache"}
        step = command_builders.build_send_receive_command("src", "dst", variables, "/bin", "@snap")
        golden.check(self, step.command)

    def test_dryrun_prefix(self):
        variables = {}
        step = command_builders.build_send_receive_command(
            "src", "dst", variables, "/bin", "@snap", dryrun=True
        )
        golden.check(self, step.command)
        self.assertNotIn("msg_level", step.command[2])

    def test_releaseholds_tags_default(self):
        variables = {"releaseholds": "Y"}
        step = command_builders.build_send_receive_command("src", "dst", variables, "/bin", "@snap")
        golden.check(self, step.command)

    def test_releaseholds_tags_custom(self):
        variables = {"releaseholds": "Y", "releaseholds_tags": "custom-*"}
        step = command_builders.build_send_receive_command("src", "dst", variables, "/bin", "@snap")
        golden.check(self, step.command)


class TestBuildPrePostBackupCommands(unittest.TestCase):
    def test_pre_backup(self):
        step = command_builders.build_pre_backup_command("echo hello")
        self.assertTrue(step.fatal)
        self.assertEqual(step.description, "Pre-backup command")
        golden.check(self, step.command)

    def test_post_backup(self):
        step = command_builders.build_post_backup_command("echo done")
        self.assertFalse(step.fatal)
        self.assertEqual(step.description, "Post-backup command")
        golden.check(self, step.command)


class TestBuildBackupPruneCommand(unittest.TestCase):
    def test_basic(self):
        step = command_builders.build_backup_prune_command(
            "/bin",
            "dailybackup",
            [("threeamigos/proxmox", "fivebays"), ("NVME1", "fivebays")],
            {},
        )
        self.assertFalse(step.fatal)
        self.assertIn("Prune snapshots (2 backup steps)", step.description)
        golden.check(self, step.command)

    def test_source_entry_precedes_destination_mapping(self):
        """Each source dataset is added before its destination mapping."""
        step = command_builders.build_backup_prune_command(
            "/bin",
            "dailybackup",
            [("threeamigos/proxmox", "fivebays")],
            {},
        )
        golden.check(self, step.command)
        bash_script = step.command[2]
        source_pos = bash_script.index('prune_datasets+=("$_fs"); ')
        dest_pos = bash_script.index('prune_datasets+=("${destfs}${_restorefs}"); ')
        self.assertLess(source_pos, dest_pos)

    def test_selection_criteria_forwarded(self):
        step = command_builders.build_backup_prune_command(
            "/bin",
            "dailybackup",
            [("tank", "fivebays")],
            {
                "includes": "proxmox",
                "excludes": "vm-100 =tank/scratch",
                "startwith": "=tank/a",
                "endwith": "z",
            },
        )
        golden.check(self, step.command)

    def test_empty_result_exits_zero(self):
        step = command_builders.build_backup_prune_command(
            "/bin", "dailybackup", [("tank", "fivebays")], {}
        )
        golden.check(self, step.command)

    def test_removequalifiers_variable(self):
        step = command_builders.build_backup_prune_command(
            "/bin",
            "dailybackup",
            [("tank", "fivebays")],
            {"sourcefsremovequalifiers": "1"},
        )
        golden.check(self, step.command)

    def test_dedup_and_dryrun(self):
        step = command_builders.build_backup_prune_command(
            "/bin",
            "dailybackup",
            [("tank", "fivebays"), ("tank", "fivebays")],
            {},
            dryrun=True,
        )
        golden.check(self, step.command)


class TestRsyncFailureDiagnosis(unittest.TestCase):
    """_diagnose_rsync_failure explains common rsync failure modes."""

    def test_success_returns_empty(self):
        self.assertEqual(command_builders._diagnose_rsync_failure(0, []), "")

    def test_partial_transfer(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            23,
            [
                'rsync: send_files failed to open "foo": Permission denied (13)',
            ],
        )
        self.assertIn("Partial transfer due to error", diagnosis)

    def test_vanished_source_files(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            24,
            [
                'file has vanished: "/src/foo"',
            ],
        )
        self.assertIn("vanished", diagnosis.lower())

    def test_connection_refused(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            255,
            [
                "ssh: connect to host tweety port 22: Connection refused",
            ],
        )
        self.assertIn("connection refused", diagnosis.lower())

    def test_no_route_to_host(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            255,
            [
                "ssh: connect to host tweety port 22: No route to host",
            ],
        )
        self.assertIn("reachable", diagnosis.lower())

    def test_permission_denied(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            255,
            [
                "root@tweety: Permission denied (publickey).",
            ],
        )
        self.assertIn("permission denied", diagnosis.lower())

    def test_timeout(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            30,
            [
                "rsync error: timeout in data send/receive (code 30)",
            ],
        )
        self.assertIn("timeout", diagnosis.lower())

    def test_no_space_left(self):
        diagnosis = command_builders._diagnose_rsync_failure(
            11,
            [
                'rsync: write failed on "/dst/foo": No space left on device (28)',
            ],
        )
        self.assertIn("no space left", diagnosis.lower())

    def test_unknown_exit_code(self):
        diagnosis = command_builders._diagnose_rsync_failure(99, ["rsync: unexplained failure"])
        self.assertIn("exit code 99", diagnosis)
        self.assertIn("unknown error", diagnosis)


if __name__ == "__main__":
    unittest.main()
