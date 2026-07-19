"""Tests for command_builders.py — rsync, send/receive, retention commands."""

import unittest

from command_builders import BashStep
import command_builders


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
        self.assertEqual(step.command[0], "rsync")
        self.assertIn("/src", step.command)
        self.assertIn("/dst", step.command)

    def test_pull_rsync(self):
        step = command_builders.build_rsync_command("remote:/src", "/dst")
        self.assertEqual(step.command[0], "rsync")
        self.assertIn("root@remote:/src", step.command)
        self.assertIn("/dst", step.command)
        self.assertIn("pull", step.description)

    def test_push_rsync(self):
        step = command_builders.build_rsync_command("/src", "remote:/dst")
        self.assertIn("root@remote:/dst", step.command)
        self.assertIn("push", step.description)

    def test_pull_rsync_without_remote_log_uses_plain_command(self):
        step = command_builders.build_rsync_command("remote:/src", "/dst")
        self.assertEqual(step.command[0], "rsync")

    def test_pull_rsync_with_remote_log_uses_bash_wrapper(self):
        step = command_builders.build_rsync_command(
            "remote:/src", "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        self.assertEqual(step.command[0], "bash")
        self.assertEqual(step.command[1], "-c")
        script = step.command[2]
        self.assertIn("ssh -q root@remote", script)
        self.assertIn("mkdir -p /var/log/zfsutilities", script)
        self.assertIn("rsync --delete --progress -rav root@remote:/src /dst", script)
        self.assertIn("cat >> $_rl", script)
        self.assertIn("exit ${PIPESTATUS[0]}", script)

    def test_local_rsync_with_remote_log_uses_bash_wrapper(self):
        step = command_builders.build_rsync_command(
            "/src", "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        self.assertEqual(step.command[0], "bash")
        self.assertEqual(step.command[1], "-c")
        script = step.command[2]
        self.assertIn("mkdir -p /var/log/zfsutilities", script)
        self.assertIn("date -r /var/log/zfsutilities/rsync-pull.log", script)
        self.assertIn(": > /var/log/zfsutilities/rsync-pull.log", script)
        self.assertIn("rsync --delete --progress -rav /src /dst", script)
        self.assertIn(">>", script)
        self.assertIn("/var/log/zfsutilities/rsync-pull.log", script)
        self.assertIn("2>&1", script)

    def test_local_rsync_without_remote_log_uses_plain_command(self):
        step = command_builders.build_rsync_command("/src", "/dst")
        self.assertEqual(step.command[0], "rsync")
        self.assertIn("/src", step.command)
        self.assertIn("/dst", step.command)

    def test_local_rsync_log_setup_script(self):
        script = command_builders._rsync_log_setup_script(
            "/var/log/zfsutilities/rsync-pull.log"
        )
        self.assertIn("mkdir -p /var/log/zfsutilities", script)
        self.assertIn("date -r /var/log/zfsutilities/rsync-pull.log", script)
        self.assertIn(": > /var/log/zfsutilities/rsync-pull.log", script)

    def test_local_host_pull_with_remote_log_uses_bash_wrapper(self):
        # Source host matching the local hostname is normalized to a local path,
        # but with remote_log_path set it should still use the log wrapper.
        hn = command_builders._get_local_hostname()
        step = command_builders.build_rsync_command(
            f"{hn}:/src", "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        self.assertEqual(step.command[0], "bash")
        script = step.command[2]
        self.assertIn("rsync --delete --progress -rav /src /dst", script)
        self.assertIn("2>&1", script)

    def test_local_rsync_with_remote_log_preserves_exit_code(self):
        step = command_builders.build_rsync_command(
            "/src", "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        script = step.command[2]
        # rsync is the last command, so the script exits with rsync's rc.
        self.assertIn("rsync --delete --progress -rav /src /dst", script)
        self.assertNotIn("exit ${PIPESTATUS[0]}", script)
        self.assertNotIn("exit 0", script)

    def test_remote_rsync_log_setup_command(self):
        cmd = command_builders._remote_rsync_log_setup_command(
            "remote", "/var/log/zfsutilities/rsync-pull.log"
        )
        self.assertEqual(cmd[0], "ssh")
        self.assertEqual(cmd[1], "-q")
        self.assertEqual(cmd[2], "root@remote")
        remote_script = cmd[3]
        self.assertIn("mkdir -p /var/log/zfsutilities", remote_script)
        self.assertIn("date -r /var/log/zfsutilities/rsync-pull.log", remote_script)
        self.assertIn(": > /var/log/zfsutilities/rsync-pull.log", remote_script)

    def test_pull_rsync_with_remote_log_preserves_exit_code(self):
        step = command_builders.build_rsync_command(
            "remote:/src", "/dst",
            remote_log_path="/var/log/zfsutilities/rsync-pull.log",
        )
        script = step.command[2]
        self.assertIn("exit ${PIPESTATUS[0]}", script)


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
        self.assertEqual(step.command[0], "bash")
        bash_script = step.command[2]
        self.assertIn('sourcefs="tank/src"', bash_script)
        self.assertIn('destfs="tank/dst"', bash_script)
        self.assertIn('nextsnap="@snap"', bash_script)
        self.assertIn('doincrementals="Y"', bash_script)
        self.assertIn('dointermediates="N"', bash_script)

    def test_includes_array(self):
        variables = {"includes": "foo bar"}
        step = command_builders.build_send_receive_command(
            "src", "dst", variables, "/bin", "@snap"
        )
        bash_script = step.command[2]
        self.assertIn('includes=("foo" "bar")', bash_script)

    def test_excludes_array(self):
        variables = {"excludes": "temp cache"}
        step = command_builders.build_send_receive_command(
            "src", "dst", variables, "/bin", "@snap"
        )
        bash_script = step.command[2]
        self.assertIn('excludes=("temp" "cache")', bash_script)

    def test_dryrun_prefix(self):
        variables = {}
        step = command_builders.build_send_receive_command(
            "src", "dst", variables, "/bin", "@snap", dryrun=True
        )
        bash_script = step.command[2]
        self.assertIn("dryrun='Y'", bash_script)
        self.assertNotIn("msg_level", bash_script)


class TestBuildInstalledProgramsCommand(unittest.TestCase):

    def test_local(self):
        step = command_builders.build_installed_programs_command("")
        self.assertEqual(step.command[0], "bash")

    def test_remote(self):
        step = command_builders.build_installed_programs_command("remote")
        self.assertEqual(step.command[0], "ssh")
        self.assertIn("root@remote", step.command)


class TestBuildPrePostBackupCommands(unittest.TestCase):

    def test_pre_backup(self):
        step = command_builders.build_pre_backup_command("echo hello")
        self.assertTrue(step.fatal)
        self.assertEqual(step.command[0], "bash")
        self.assertIn("echo hello", step.command[2])
        self.assertEqual(step.description, "Pre-backup command")

    def test_post_backup(self):
        step = command_builders.build_post_backup_command("echo done")
        self.assertFalse(step.fatal)
        self.assertIn("echo done", step.command[2])
        self.assertEqual(step.description, "Post-backup command")


class TestBuildRetentionCommand(unittest.TestCase):

    def test_basic(self):
        step = command_builders.build_retention_command("/bin", "dailybackup")
        self.assertTrue(step.fatal)
        self.assertEqual(step.command[0], "bash")
        bash_script = step.command[2]
        self.assertIn('autoproceed="Y"', bash_script)
        self.assertIn('cleanup "" "" dailybackup', bash_script)
        self.assertEqual(step.description, "Prune snapshots")

    def test_dryrun(self):
        step = command_builders.build_retention_command("/bin", "dailybackup", dryrun=True)
        self.assertIn("dryrun='Y'", step.command[2])
        self.assertEqual(step.description, "Prune snapshots")

    def test_pools_list_loops_in_order(self):
        step = command_builders.build_retention_command(
            "/bin", "dailybackup", pools=["archive", "tank"]
        )
        bash_script = step.command[2]
        self.assertIn("for pool in archive tank; do", bash_script)
        self.assertIn('cleanup "$pool" "" dailybackup', bash_script)
        self.assertIn("exit $overall_rc", bash_script)
        self.assertEqual(step.description, "Prune snapshots (archive, tank)")


if __name__ == "__main__":
    unittest.main()
