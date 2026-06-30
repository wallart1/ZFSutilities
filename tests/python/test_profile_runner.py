"""Tests for profile_runner.py — profile step building with mocked subprocess."""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import MagicMock, patch

from test_support import temp_config_dir, mock_subprocess, capture_logs


def _mock_popen_process(stdout="", stderr="", rc=0):
    """Return a MagicMock that behaves like Popen with merged stdout/stderr."""
    proc = MagicMock()
    proc.stdout = io.StringIO((stdout or "") + (stderr or ""))
    proc.wait.return_value = rc
    return proc

import log_index
import offsite_runner
import profile_runner
import restore_runner
import scrub_manager as sm
from command_builders import BashStep


class TestIsDatasetEncrypted(unittest.TestCase):

    def test_encrypted_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name /backups/keys",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /backups",
                lambda cmd, **kwargs: m._completed("tank/data")
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("aes-256-gcm")
            )
            result = profile_runner._is_dataset_encrypted("/backups/keys")
        self.assertTrue(result)

    def test_unencrypted_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name /backups/keys",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /backups",
                lambda cmd, **kwargs: m._completed("tank/data")
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("-")
            )
            result = profile_runner._is_dataset_encrypted("/backups/keys")
        self.assertFalse(result)

    def test_off_encryption_value(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name /backups/keys",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /backups",
                lambda cmd, **kwargs: m._completed("tank/data")
            )
            m.set_command_handler(
                r"zfs get -H -o value encryption tank/data",
                lambda cmd, **kwargs: m._completed("off")
            )
            result = profile_runner._is_dataset_encrypted("/backups/keys")
        self.assertFalse(result)

    def test_no_dataset(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name /other/path",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /other",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            result = profile_runner._is_dataset_encrypted("/other/path")
        self.assertFalse(result)

    def test_zfs_list_failure(self):
        with mock_subprocess() as m:
            m.set_command_handler(
                r"zfs list -H -o name /backups/keys",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /backups",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            m.set_command_handler(
                r"zfs list -H -o name /",
                lambda cmd, **kwargs: m._completed("", rc=1)
            )
            result = profile_runner._is_dataset_encrypted("/backups/keys")
        self.assertFalse(result)

    def test_empty_path(self):
        result = profile_runner._is_dataset_encrypted("")
        self.assertFalse(result)


class TestComputeRestoreParams(unittest.TestCase):

    def test_common_prefix_removed(self):
        rq, destfs = restore_runner.compute_restore_params("tank/vm/100", "backup/vm/100")
        self.assertEqual(rq, 1)
        self.assertEqual(destfs, "backup")

    def test_no_common_prefix_raises(self):
        with self.assertRaises(ValueError):
            restore_runner.compute_restore_params("a/b", "c/d")

    def test_identical_paths(self):
        rq, destfs = restore_runner.compute_restore_params("tank/data", "tank/data")
        self.assertEqual(rq, 1)
        self.assertEqual(destfs, "tank")


class TestBuildOffsiteStepCommand(unittest.TestCase):

    def test_includes_offsite_label(self):
        variables = {"doincrementals": "Y", "dointermediates": "N", "applyholds": "Y"}
        step = offsite_runner.build_offsite_step_command(
            "tank/src", "offsite/dst", variables, "/bin", "@offsite-2025-01-01T00:00-04:00-s",
            "", ""
        )
        self.assertIsInstance(step, BashStep)
        self.assertEqual(step.command[0], "bash")
        script = step.command[2]
        self.assertIn('label="@offsite"', script)
        self.assertIn("zfshold", script)

    def test_includes_and_excludes(self):
        variables = {"doincrementals": "Y", "dointermediates": "N", "applyholds": "N"}
        step = offsite_runner.build_offsite_step_command(
            "src", "dst", variables, "/bin", "@snap",
            "foo bar", "temp"
        )
        script = step.command[2]
        self.assertIn('includes=("foo" "bar")', script)
        self.assertIn('excludes=("temp")', script)


class TestBuildRestoreCommand(unittest.TestCase):

    def test_part1_only(self):
        variables = {"depth": "", "label": "", "includes": "", "excludes": "", "startwith": "", "endwith": ""}
        step = restore_runner.build_restore_command(
            "tank/src", 0, "tank/dst", "/bin",
            variables, do_part1=True, do_part2=False
        )
        self.assertIsInstance(step, BashStep)
        script = step.command[2]
        self.assertIn('doincrementals="N"', script)
        self.assertNotIn('doincrementals="Y"', script)
        self.assertIn("(full copy)", step.description)

    def test_part2_only(self):
        variables = {}
        step = restore_runner.build_restore_command(
            "tank/src", 0, "tank/dst", "/bin",
            variables, do_part1=False, do_part2=True
        )
        script = step.command[2]
        self.assertIn('doincrementals="Y"', script)
        self.assertIn("(incremental)", step.description)

    def test_both_parts(self):
        variables = {}
        step = restore_runner.build_restore_command(
            "tank/src", 0, "tank/dst", "/bin",
            variables, do_part1=True, do_part2=True
        )
        self.assertIn("(full copy + incremental)", step.description)


class TestDetectOffsitePool(unittest.TestCase):

    def test_finds_online_pool(self):
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "ONLINE"},
                {"name": "z22tb", "health": "OFFLINE"},
            ])
            pool = offsite_runner.detect_offsite_pool(["z22tb", "z40tb"])
        self.assertEqual(pool, "z40tb")

    def test_none_online(self):
        with mock_subprocess() as m:
            m.add_zpool_list([
                {"name": "z40tb", "health": "OFFLINE"},
            ])
            pool = offsite_runner.detect_offsite_pool(["z40tb"])
        self.assertIsNone(pool)


class TestRunBackupProfile(unittest.TestCase):

    def test_builds_steps_correctly(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "remote:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [
                        {"source": "tank/src", "dest": "tank/dst", "active": True},
                    ],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                # Patch subprocess.Popen so no real commands execute
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                with capture_logs() as logs:
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
                # Should have logged snapshot name and steps
                self.assertTrue(any("Backup snapshot:" in msg for msg in logs))

    def test_empty_steps_warns(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [],
                    "send_receive_steps": [],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with capture_logs() as logs:
                rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 1)
            self.assertTrue(any("No active steps" in msg for msg in logs))

    def test_rsync_pull_failure_continues(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "remote:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [
                        {"source": "tank/src", "dest": "tank/dst", "active": True},
                    ],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(
                    r"rsync",
                    lambda cmd, **kwargs: m._completed("", stderr="host down", rc=255),
                )
                m.set_command_handler(
                    r"send-receive",
                    lambda cmd, **kwargs: m._completed("", rc=0),
                )
                with capture_logs() as logs:
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 255)
            self.assertTrue(any("Step exited with rc=255" in msg for msg in logs))
            self.assertTrue(any("zfs send/receive" in msg for msg in logs))

    def test_fatal_send_receive_failure_aborts_profile(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [],
                    "send_receive_steps": [
                        {"source": "tank/src", "dest": "tank/dst", "active": True},
                        {"source": "tank/src2", "dest": "tank/dst2", "active": True},
                    ],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(
                    r"tank/src.*tank/dst",
                    lambda cmd, **kwargs: m._completed("", stderr="boom", rc=1),
                )
                m.set_command_handler(
                    r"tank/src2.*tank/dst2",
                    lambda cmd, **kwargs: m._completed("", rc=0),
                )
                with capture_logs() as logs:
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 1)
            # Second send/receive should not have run because the first was fatal.
            self.assertFalse(any("tank/src2" in msg for msg in logs))

    def test_pull_step_uses_remote_log_path(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "remote:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            # Find the subprocess.Popen call for the pull step.
            pull_calls = [
                call for call in m.calls
                if call[0] and isinstance(call[0], list) and call[0][0] == "bash"
            ]
            self.assertEqual(len(pull_calls), 1)
            bash_script = pull_calls[0][0][2]
            self.assertIn("/var/log/zfsutilities/rsync-pull.log", bash_script)
            self.assertIn("exit ${PIPESTATUS[0]}", bash_script)

    def test_local_pull_step_uses_remote_log_path(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            pull_calls = [
                call for call in m.calls
                if call[0] and isinstance(call[0], list) and call[0][0] == "bash"
            ]
            self.assertEqual(len(pull_calls), 1)
            bash_script = pull_calls[0][0][2]
            self.assertIn("/var/log/zfsutilities/rsync-pull.log", bash_script)
            self.assertIn("mkdir -p /var/log/zfsutilities", bash_script)
            self.assertIn("rsync --delete --progress -rav /src /dst", bash_script)
            self.assertIn("2>&1", bash_script)

    def test_local_host_pull_step_uses_remote_log_path(self):
        # A source like stewie:/etc/ when running on stewie is normalized to a
        # local path, but it should still get the log wrapper.
        import socket
        local_host = socket.gethostname().split(".")[0]
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": f"{local_host}:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            pull_calls = [
                call for call in m.calls
                if call[0] and isinstance(call[0], list) and call[0][0] == "bash"
            ]
            self.assertEqual(len(pull_calls), 1)
            bash_script = pull_calls[0][0][2]
            self.assertIn("/var/log/zfsutilities/rsync-pull.log", bash_script)
            self.assertIn("rsync --delete --progress -rav /src /dst", bash_script)
            self.assertIn("2>&1", bash_script)

    def test_pull_steps_active_false_skips_rsync(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "remote:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [
                        {"source": "tank/src", "dest": "tank/dst", "active": True},
                    ],
                    "post_steps": {"run_retention": False, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                    "pull_steps_active": False,
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                with capture_logs() as logs:
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            self.assertTrue(any("Pull steps disabled" in msg for msg in logs))
            bash_scripts = [
                call[0][2]
                for call in m.calls
                if call[0] and isinstance(call[0], list) and call[0][0] == "bash" and len(call[0]) > 2
            ]
            self.assertFalse(any("rsync" in s for s in bash_scripts))
            self.assertTrue(any("send-receive" in s for s in bash_scripts))


    def test_retention_step_uses_config_pool_order(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [],
                    "send_receive_steps": [],
                    "post_steps": {"run_retention": True, "remove_snapfile": False},
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                }
            }
            config = {"pools": [{"name": "z2"}, {"name": "z1"}]}
            with mock_subprocess() as m:
                m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
                rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            bash_scripts = [
                call[0][2]
                for call in m.calls
                if call[0] and isinstance(call[0], list) and call[0][0] == "bash" and len(call[0]) > 2
            ]
            self.assertEqual(len(bash_scripts), 1)
            self.assertIn("for pool in z2 z1; do", bash_scripts[0])


class TestRunOffsiteProfile(unittest.TestCase):

    def test_no_pool_returns_error(self):
        with temp_config_dir():
            profile = {
                "config": {
                    "variables": {},
                    "offsite_pools": ["missing"],
                    "steps": [{"source": "src", "dest": "dst", "active": True}],
                }
            }
            config = {}
            with mock_subprocess() as m:
                m.add_zpool_list([])
                with capture_logs() as logs:
                    rc = profile_runner.run_offsite_profile(profile, config, "/bin")
            self.assertEqual(rc, 1)
            self.assertTrue(any("No offsite pool online" in msg for msg in logs))


class TestRunRestoreProfile(unittest.TestCase):

    def test_missing_source_dest(self):
        profile = {"config": {"source": "", "dest": "", "do_part1": True, "do_part2": True, "variables": {}}}
        config = {}
        with capture_logs() as logs:
            rc = profile_runner.run_restore_profile(profile, config, "/bin")
        self.assertEqual(rc, 1)
        self.assertTrue(any("Source and destination must be specified" in msg for msg in logs))


class TestRunRetentionProfile(unittest.TestCase):

    def test_no_pools_warns(self):
        profile = {"config": {"prune_label": "dailybackup", "prune_pools": []}}
        config = {}
        with capture_logs() as logs:
            rc = profile_runner.run_retention_profile(profile, config, "/bin")
        self.assertEqual(rc, 1)
        self.assertTrue(any("No pools selected" in msg for msg in logs))

    def test_runs_for_each_pool(self):
        profile = {"config": {"prune_label": "dailybackup", "prune_pools": ["tank"]}}
        config = {}
        with mock_subprocess() as m:
            m.set_command_handler(".*", lambda cmd, **kwargs: m._completed("", rc=0))
            with capture_logs() as logs:
                rc = profile_runner.run_retention_profile(profile, config, "/bin")
            self.assertTrue(any("Prune tank" in msg for msg in logs))


class TestSessionLogFile(unittest.TestCase):

    def test_create_and_trailer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = profile_runner.SESSION_LOG_DIR
            orig_log_dir = log_index.SESSION_LOG_DIR
            profile_runner.SESSION_LOG_DIR = tmpdir
            log_index.SESSION_LOG_DIR = tmpdir
            try:
                path = profile_runner._create_session_log_file("backup", "test")
                self.assertIsNotNone(path)
                self.assertTrue(os.path.exists(path))
                profile_runner._write_session_trailer(rc=0)
                with open(path) as f:
                    content = f.read()
                self.assertIn("rc=0", content)
            finally:
                profile_runner.SESSION_LOG_DIR = orig_dir
                log_index.SESSION_LOG_DIR = orig_log_dir

    def test_trailer_persists_done_to_log_index(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = profile_runner.SESSION_LOG_DIR
            orig_log_dir = log_index.SESSION_LOG_DIR
            profile_runner.SESSION_LOG_DIR = tmpdir
            log_index.SESSION_LOG_DIR = tmpdir
            try:
                path = profile_runner._create_session_log_file("backup", "test")
                profile_runner._write_session_trailer(rc=0, bytes_transferred=5678)

                index = log_index.LogIndex.load()
                entry = index.get(path)
            finally:
                profile_runner.SESSION_LOG_DIR = orig_dir
                log_index.SESSION_LOG_DIR = orig_log_dir

        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Done")
        self.assertEqual(entry["bytes_transferred"], 5678)
        self.assertIsNotNone(entry["duration"])

    def test_trailer_persists_failed_to_log_index(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = profile_runner.SESSION_LOG_DIR
            orig_log_dir = log_index.SESSION_LOG_DIR
            profile_runner.SESSION_LOG_DIR = tmpdir
            log_index.SESSION_LOG_DIR = tmpdir
            try:
                path = profile_runner._create_session_log_file("backup", "test")
                profile_runner._write_session_trailer(rc=2)

                index = log_index.LogIndex.load()
                entry = index.get(path)
            finally:
                profile_runner.SESSION_LOG_DIR = orig_dir
                log_index.SESSION_LOG_DIR = orig_log_dir

        self.assertIsNotNone(entry)
        self.assertEqual(entry["status"], "Failed")

    def test_maybe_truncate_resets_index(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_dir = profile_runner.SESSION_LOG_DIR
            orig_log_dir = log_index.SESSION_LOG_DIR
            profile_runner.SESSION_LOG_DIR = tmpdir
            log_index.SESSION_LOG_DIR = tmpdir
            try:
                path = profile_runner._create_session_log_file("backup", "test")
                index = log_index.LogIndex.load()
                index.update(path)
                index.save()

                with patch("profile_runner.truncate_session_log", return_value=True) as mock_truncate:
                    profile_runner._maybe_truncate_session_log(path)

                mock_truncate.assert_called_once_with(path)
                index2 = log_index.LogIndex.load()
                self.assertIsNone(index2.get(path))
            finally:
                profile_runner.SESSION_LOG_DIR = orig_dir
                log_index.SESSION_LOG_DIR = orig_log_dir


class TestWriteRawLine(unittest.TestCase):

    def test_appends_with_timestamp(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            path = f.name
        try:
            profile_runner._write_raw_line(path, "INFO: test line")
            with open(path) as fh:
                content = fh.read()
            self.assertIn("INFO: test line", content)
            # Should have a timestamp prefix
            self.assertRegex(content, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
        finally:
            os.unlink(path)

    def test_noop_when_no_file(self):
        # Should not raise
        profile_runner._write_raw_line(None, "INFO: test")
        profile_runner._write_raw_line("", "INFO: test")


class TestRunScrubProfile(unittest.TestCase):

    def test_no_pools_warns(self):
        profile = {"config": {"pools": [], "simultaneous": 1}}
        config = {}
        with capture_logs() as logs:
            rc = profile_runner.run_scrub_profile(profile, config, "/bin")
        self.assertEqual(rc, 1)
        self.assertTrue(any("No pools specified" in msg for msg in logs))

    def test_runs_and_polls(self):
        import tempfile
        import scrub_manager as sm
        with tempfile.TemporaryDirectory() as tmpdir:
            orig_path = sm.SCRUB_STATE_PATH
            sm.SCRUB_STATE_PATH = os.path.join(tmpdir, "scrub_state.json")
            try:
                profile = {"config": {"pools": ["tank"], "simultaneous": 1}}
                config = {}
                # Simulate: old finished scrub, then scrub starts, then completes.
                state_sequence = [
                    {"tank": sm.ScrubInfo(state=sm.ScrubState.FINISHED)},
                    {"tank": sm.ScrubInfo(state=sm.ScrubState.SCANNING)},
                    {"tank": sm.ScrubInfo(state=sm.ScrubState.FINISHED)},
                ]
                states_iter = iter(state_sequence)
                with patch("profile_runner.get_all_pool_scrub_states") as mock_states:
                    mock_states.side_effect = lambda: next(states_iter)
                    with patch.object(sm, "start_scrub", return_value=True):
                        with patch("profile_runner.time.sleep"):
                            with capture_logs() as logs:
                                rc = profile_runner.run_scrub_profile(
                                    profile, config, "/bin"
                                )
                            self.assertEqual(rc, 0)
                            self.assertTrue(
                                any("Scrub profile started" in msg for msg in logs)
                            )
            finally:
                sm.SCRUB_STATE_PATH = orig_path


class TestRunStepList(unittest.TestCase):

    def test_stops_on_abort_code_nine(self):
        """A step returning 9 (user/lock abort) halts the step list."""
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = [
                _mock_popen_process(rc=9),
                _mock_popen_process(rc=0),
            ]
            with capture_logs() as logs:
                rc = profile_runner._run_step_list([
                    BashStep(["false"], "Step 1", fatal=False),
                    BashStep(["true"], "Step 2", fatal=False),
                ])
        self.assertEqual(rc, 9)
        self.assertEqual(mock_popen.call_count, 1)
        self.assertTrue(
            any("lock conflict" in msg.lower() for msg in logs)
        )

    def test_run_command_sets_headless_env(self):
        """profile_runner always sets ZFSUTILITIES_HEADLESS=Y for subprocesses."""
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(rc=0)
            profile_runner._run_command(BashStep(["echo", "hello"], "Say hello"))
        call_kwargs = mock_popen.call_args[1]
        self.assertEqual(call_kwargs["env"]["ZFSUTILITIES_HEADLESS"], "Y")

    def test_run_command_streams_merged_stdout_stderr(self):
        """_run_command merges stdout/stderr and writes each line in order."""
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(
                stdout="stdout-line\nstderr-line\n", rc=0
            )
            with patch("profile_runner._write_raw_line") as mock_write:
                rc = profile_runner._run_command(
                    BashStep(["echo", "hello"], "Say hello"),
                    session_log_file="/tmp/test.log",
                )
        self.assertEqual(rc, 0)
        self.assertEqual(mock_popen.call_args[1]["stderr"], subprocess.STDOUT)
        self.assertEqual(mock_write.call_count, 2)
        self.assertEqual(mock_write.call_args_list[0][0][1], "stdout-line")
        self.assertEqual(mock_write.call_args_list[1][0][1], "stderr-line")

    def test_passes_command_list_not_description(self):
        """Ensure _run_step_list passes the command list to subprocess.Popen,
        not the description string (regression test for the swapped-tuple bug)."""
        steps = [
            BashStep(["echo", "hello"], "Say hello", fatal=True),
            BashStep(["ssh", "root@host", "true"], "[host] run true", fatal=False),
        ]
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = [
                _mock_popen_process(rc=0),
                _mock_popen_process(rc=0),
            ]
            rc = profile_runner._run_step_list(steps)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_popen.call_count, 2)
        # First call: command must be the list, not the description
        first_cmd = mock_popen.call_args_list[0][0][0]
        self.assertEqual(first_cmd, ["echo", "hello"])
        # Second call: command must be the list
        second_cmd = mock_popen.call_args_list[1][0][0]
        self.assertEqual(second_cmd, ["ssh", "root@host", "true"])

    def test_non_fatal_step_continues(self):
        """A non-fatal step failure logs a warning and continues."""
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = [
                _mock_popen_process(stdout="host down", rc=255),
                _mock_popen_process(rc=0),
            ]
            with capture_logs() as logs:
                rc = profile_runner._run_step_list([
                    BashStep(["rsync", "a", "b"], "rsync a -> b", fatal=False),
                    BashStep(["true"], "Step 2", fatal=True),
                ])
        self.assertEqual(rc, 255)
        self.assertEqual(mock_popen.call_count, 2)
        self.assertTrue(any("Step exited with rc=255" in msg for msg in logs))

    def test_fatal_step_stops_list(self):
        """A fatal step failure aborts the remaining step list."""
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.side_effect = [
                _mock_popen_process(stdout="boom", rc=1),
                _mock_popen_process(rc=0),
            ]
            with capture_logs() as logs:
                rc = profile_runner._run_step_list([
                    BashStep(["bash", "-c", "send-receive"], "zfs send/receive", fatal=True),
                    BashStep(["true"], "Step 2", fatal=True),
                ])
        self.assertEqual(rc, 1)
        self.assertEqual(mock_popen.call_count, 1)
        self.assertTrue(any("Step exited with rc=1" in msg for msg in logs))


class TestDryRunProfiles(unittest.TestCase):

    def test_backup_dry_run_skips_rsync_and_scripts(self):
        with temp_config_dir():
            profile = {
                "dry_run": True,
                "config": {
                    "variables": {"label": "dailybackup"},
                    "pull_steps": [
                        {"source": "remote:/src", "dest": "/dst", "active": True},
                    ],
                    "send_receive_steps": [
                        {"source": "tank/src", "dest": "tank/dst", "active": True},
                    ],
                    "post_steps": {"run_retention": True, "remove_snapfile": True},
                    "pre_backup_script_enabled": True,
                    "pre_backup_script": "echo pre",
                    "post_backup_script_enabled": True,
                    "post_backup_script": "echo post",
                    "zfs_keys_path": "",
                    "zfs_keys_dest": "",
                },
            }
            config = {}
            with mock_subprocess():
                with patch("profile_runner.subprocess.Popen") as mock_popen:
                    mock_popen.side_effect = lambda *a, **kw: _mock_popen_process(
                        rc=0
                    )
                    with capture_logs() as logs:
                        rc = profile_runner.run_backup_profile(
                            profile, config, "/bin"
                        )
            self.assertEqual(rc, 0)
            self.assertTrue(
                any("Dry run mode enabled" in msg for msg in logs)
            )
            self.assertTrue(
                any("Would rsync remote:/src -> /dst" in msg for msg in logs)
            )
            self.assertTrue(
                any("Would run pre-backup command" in msg for msg in logs)
            )
            self.assertTrue(
                any("Would run post-backup command" in msg for msg in logs)
            )
            self.assertTrue(
                any("Skipping snapfile cleanup" in msg for msg in logs)
            )
            bash_scripts = [
                call[0][0][2]
                for call in mock_popen.call_args_list
                if call[0][0] and call[0][0][0] == "bash" and len(call[0][0]) > 2
            ]
            self.assertTrue(
                any("dryrun='Y'" in s for s in bash_scripts),
                "Expected at least one bash script with dryrun='Y'"
            )
            self.assertFalse(
                any("rsync" in s for s in bash_scripts),
                "Did not expect any rsync commands in dry-run mode"
            )

    def test_offsite_dry_run_passed_to_command(self):
        with temp_config_dir():
            profile = {
                "dry_run": True,
                "config": {
                    "variables": {},
                    "offsite_pools": ["z40tb"],
                    "steps": [
                        {
                            "source": "tank/src",
                            "dest": "<offsite>/dst",
                            "active": True,
                        },
                    ],
                },
            }
            config = {}
            with mock_subprocess() as m:
                m.add_zpool_list([{"name": "z40tb", "health": "ONLINE"}])
                with patch("profile_runner.subprocess.Popen") as mock_popen:
                    mock_popen.return_value = _mock_popen_process(rc=0)
                    with capture_logs() as logs:
                        rc = profile_runner.run_offsite_profile(
                            profile, config, "/bin"
                        )
            self.assertEqual(rc, 0)
            self.assertTrue(
                any("Dry run mode enabled" in msg for msg in logs)
            )
            bash_scripts = [
                call[0][0][2]
                for call in mock_popen.call_args_list
                if call[0][0] and call[0][0][0] == "bash" and len(call[0][0]) > 2
            ]
            self.assertTrue(
                any("dryrun='Y'" in s for s in bash_scripts)
            )

    def test_restore_dry_run_passed_to_command(self):
        profile = {
            "dry_run": True,
            "config": {
                "source": "tank/vm/100",
                "dest": "backup/vm/100",
                "do_part1": True,
                "do_part2": False,
                "variables": {},
            },
        }
        config = {}
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(rc=0)
            with capture_logs() as logs:
                rc = profile_runner.run_restore_profile(profile, config, "/bin")
        self.assertEqual(rc, 0)
        self.assertTrue(
            any("Dry run mode enabled" in msg for msg in logs)
        )
        script = mock_popen.call_args[0][0][2]
        self.assertIn("dryrun='Y'", script)

    def test_retention_dry_run_passed_to_command(self):
        profile = {
            "dry_run": True,
            "config": {
                "prune_label": "dailybackup",
                "prune_pools": ["tank"],
            },
        }
        config = {}
        with patch("profile_runner.subprocess.Popen") as mock_popen:
            mock_popen.return_value = _mock_popen_process(rc=0)
            with capture_logs() as logs:
                rc = profile_runner.run_retention_profile(profile, config, "/bin")
        self.assertEqual(rc, 0)
        self.assertTrue(
            any("Dry run mode enabled" in msg for msg in logs)
        )
        script = mock_popen.call_args[0][0][2]
        self.assertIn("dryrun='Y'", script)


class TestMainHistoryEntry(unittest.TestCase):
    """main() records the session log path in the history entry."""

    def _run_main(self, session_log_dir, runner_patch):
        profile = {
            "tab_type": "backup",
            "config": {"variables": {"label": "dailybackup"}},
        }
        with tempfile.TemporaryDirectory() as lock_dir:
            orig_lock_dir = profile_runner.PROFILE_LOCK_DIR
            profile_runner.PROFILE_LOCK_DIR = lock_dir
            try:
                with ExitStack() as stack:
                    stack.enter_context(patch.object(sys, "argv", ["profile_runner.py", "run", "Daily"]))
                    stack.enter_context(patch("profile_runner.load_profile", return_value=profile))
                    stack.enter_context(patch("profile_runner.load_config", return_value={}))
                    stack.enter_context(patch("profile_runner.prune_old_logs"))
                    mock_add = stack.enter_context(patch("profile_runner.add_history_entry"))
                    stack.enter_context(patch("profile_runner._write_session_trailer"))
                    stack.enter_context(patch("profile_runner.sys.exit"))
                    stack.enter_context(patch("profile_runner.SESSION_LOG_DIR", session_log_dir))
                    stack.enter_context(runner_patch)
                    profile_runner.main()
                return mock_add
            finally:
                profile_runner.PROFILE_LOCK_DIR = orig_lock_dir

    def test_main_records_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_add = self._run_main(
                tmpdir,
                patch("profile_runner.run_backup_profile", return_value=0),
            )
        mock_add.assert_called_once()
        entry = mock_add.call_args[0][0]
        self.assertIn("log_file", entry)
        self.assertTrue(entry["log_file"].startswith(tmpdir))

    def test_main_omits_log_file_when_creation_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = os.path.join(tmpdir, "sessions")
            with patch("profile_runner._create_session_log_file",
                       return_value=None):
                mock_add = self._run_main(
                    session_dir,
                    patch("profile_runner.run_backup_profile", return_value=0),
                )
        mock_add.assert_called_once()
        entry = mock_add.call_args[0][0]
        self.assertNotIn("log_file", entry)


class TestCheckWeekdayOrdinal(unittest.TestCase):

    def _patch_now(self, year, month, day):
        dt = datetime(year, month, day)
        mock_datetime = MagicMock()
        mock_datetime.now.return_value = dt
        return patch.object(profile_runner, "datetime", mock_datetime)

    def test_plain_weekday_always_matches(self):
        with self._patch_now(2025, 1, 18):
            self.assertTrue(profile_runner._check_weekday_ordinal("6"))

    def test_first_saturday_on_first_saturday(self):
        # 2025-01-04 is the first Saturday of January 2025.
        with self._patch_now(2025, 1, 4):
            self.assertTrue(profile_runner._check_weekday_ordinal("6#1"))

    def test_first_saturday_on_second_saturday(self):
        # 2025-01-11 is the second Saturday.
        with self._patch_now(2025, 1, 11):
            self.assertFalse(profile_runner._check_weekday_ordinal("6#1"))

    def test_last_saturday_on_last_saturday(self):
        # 2025-01-25 is the last Saturday of January 2025.
        with self._patch_now(2025, 1, 25):
            self.assertTrue(profile_runner._check_weekday_ordinal("6#L"))

    def test_last_saturday_on_non_last_saturday(self):
        # 2025-01-18 is not the last Saturday.
        with self._patch_now(2025, 1, 18):
            self.assertFalse(profile_runner._check_weekday_ordinal("6#L"))

    def test_list_of_ordinals(self):
        # 2025-01-11 is the second Saturday.
        with self._patch_now(2025, 1, 11):
            self.assertTrue(profile_runner._check_weekday_ordinal("6#2,4"))
            self.assertFalse(profile_runner._check_weekday_ordinal("6#1,3"))

    def test_invalid_ordinal_returns_false(self):
        with self._patch_now(2025, 1, 4):
            self.assertFalse(profile_runner._check_weekday_ordinal("*#1"))


class TestPauseScrubsInProfiles(unittest.TestCase):
    """pause_scrubs option issues zpool scrub -p / scrub around steps."""

    def _zpool_status_text(self, state):
        if state == "scanning":
            return "  scan: scrub in progress since Mon Jun 29 12:00:00 2026\n    50% done\n"
        if state == "paused":
            return "  scan: scrub paused since Mon Jun 29 12:00:00 2026\n"
        return "  scan: none requested\n"

    def _status_handler(self, m, initial):
        status = dict(initial)

        def handler(cmd, **kwargs):
            if not cmd or cmd[0] != "zpool":
                return m._completed("")
            if len(cmd) >= 3 and cmd[1] == "status":
                pool = cmd[-1]
                return m._completed(self._zpool_status_text(status.get(pool, "none")))
            if len(cmd) >= 2 and cmd[1] == "scrub":
                if "-p" in cmd:
                    pool = cmd[-1]
                    status[pool] = "paused"
                else:
                    pool = cmd[-1]
                    status[pool] = "scanning"
                return m._completed("")
            return m._completed("")

        return handler

    def _scrub_commands(self, m):
        return [
            list(c[0])
            for c in m.calls
            if c[0] and c[0][0] == "zpool" and "scrub" in c[0]
        ]

    def test_backup_profile_pauses_and_resumes_scrubs(self):
        with temp_config_dir() as tmpdir:
            state_path = os.path.join(tmpdir, "scrub_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            profile = {
                "dry_run": False,
                "config": {
                    "pause_scrubs": True,
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"source": "src/a", "dest": "dst/b", "active": True},
                    ],
                    "pull_steps": [],
                    "post_steps": {
                        "run_retention": False,
                        "remove_snapfile": False,
                    },
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                    "zfs_keys_path": "",
                    "zfs_keys_dest": "",
                },
            }
            config = {}
            with patch.object(sm, "SCRUB_STATE_PATH", state_path):
                with mock_subprocess() as m:
                    m.add_zpool_list(
                        [{"name": "src"}, {"name": "dst"}]
                    )
                    m.set_command_handler(
                        r"^zpool (status|scrub) ",
                        self._status_handler(m, {"src": "scanning", "dst": "scanning"}),
                    )
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            scrub_cmds = self._scrub_commands(m)
            self.assertIn(["zpool", "scrub", "-p", "src"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "-p", "dst"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "src"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "dst"], scrub_cmds)

    def test_backup_profile_does_not_pause_when_disabled(self):
        with temp_config_dir() as tmpdir:
            state_path = os.path.join(tmpdir, "scrub_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            profile = {
                "dry_run": False,
                "config": {
                    "pause_scrubs": False,
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"source": "src/a", "dest": "dst/b", "active": True},
                    ],
                    "pull_steps": [],
                    "post_steps": {
                        "run_retention": False,
                        "remove_snapfile": False,
                    },
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                    "zfs_keys_path": "",
                    "zfs_keys_dest": "",
                },
            }
            config = {}
            with patch.object(sm, "SCRUB_STATE_PATH", state_path):
                with mock_subprocess() as m:
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            scrub_cmds = self._scrub_commands(m)
            self.assertEqual(scrub_cmds, [])

    def test_offsite_profile_pauses_and_resumes_scrubs(self):
        with temp_config_dir() as tmpdir:
            state_path = os.path.join(tmpdir, "scrub_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            profile = {
                "dry_run": False,
                "config": {
                    "pause_scrubs": True,
                    "variables": {},
                    "offsite_pools": ["offsite"],
                    "steps": [
                        {
                            "source": "src/a",
                            "dest": "<offsite>/b",
                            "active": True,
                        },
                    ],
                },
            }
            config = {}
            with patch.object(sm, "SCRUB_STATE_PATH", state_path):
                with mock_subprocess() as m:
                    m.add_zpool_list(
                        [{"name": "src"}, {"name": "offsite"}]
                    )
                    m.set_command_handler(
                        r"^zpool (status|scrub) ",
                        self._status_handler(m, {"src": "scanning", "offsite": "scanning"}),
                    )
                    rc = profile_runner.run_offsite_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            scrub_cmds = self._scrub_commands(m)
            self.assertIn(["zpool", "scrub", "-p", "src"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "-p", "offsite"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "src"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "offsite"], scrub_cmds)

    def test_restore_profile_pauses_and_resumes_scrubs(self):
        with temp_config_dir() as tmpdir:
            state_path = os.path.join(tmpdir, "scrub_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            profile = {
                "dry_run": False,
                "config": {
                    "pause_scrubs": True,
                    "source": "backup/a",
                    "dest": "tank/a",
                    "do_part1": True,
                    "do_part2": False,
                    "variables": {},
                },
            }
            config = {}
            with patch.object(sm, "SCRUB_STATE_PATH", state_path):
                with mock_subprocess() as m:
                    m.add_zpool_list(
                        [{"name": "backup"}, {"name": "tank"}]
                    )
                    m.set_command_handler(
                        r"^zpool (status|scrub) ",
                        self._status_handler(m, {"backup": "scanning", "tank": "scanning"}),
                    )
                    rc = profile_runner.run_restore_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            scrub_cmds = self._scrub_commands(m)
            self.assertIn(["zpool", "scrub", "-p", "backup"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "-p", "tank"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "backup"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "tank"], scrub_cmds)

    def test_already_paused_pool_is_not_resumed(self):
        with temp_config_dir() as tmpdir:
            state_path = os.path.join(tmpdir, "scrub_state.json")
            with open(state_path, "w") as fh:
                fh.write("{}")
            profile = {
                "dry_run": False,
                "config": {
                    "pause_scrubs": True,
                    "variables": {"label": "dailybackup"},
                    "send_receive_steps": [
                        {"source": "src/a", "dest": "dst/b", "active": True},
                    ],
                    "pull_steps": [],
                    "post_steps": {
                        "run_retention": False,
                        "remove_snapfile": False,
                    },
                    "pre_backup_script_enabled": False,
                    "post_backup_script_enabled": False,
                    "zfs_keys_path": "",
                    "zfs_keys_dest": "",
                },
            }
            config = {}
            with patch.object(sm, "SCRUB_STATE_PATH", state_path):
                with mock_subprocess() as m:
                    m.add_zpool_list(
                        [{"name": "src"}, {"name": "dst"}]
                    )
                    m.set_command_handler(
                        r"^zpool (status|scrub) ",
                        self._status_handler(m, {"src": "scanning", "dst": "paused"}),
                    )
                    rc = profile_runner.run_backup_profile(profile, config, "/bin")
            self.assertEqual(rc, 0)
            scrub_cmds = self._scrub_commands(m)
            self.assertIn(["zpool", "scrub", "-p", "src"], scrub_cmds)
            self.assertIn(["zpool", "scrub", "src"], scrub_cmds)
            self.assertNotIn(["zpool", "scrub", "-p", "dst"], scrub_cmds)
            self.assertNotIn(["zpool", "scrub", "dst"], scrub_cmds)


if __name__ == "__main__":
    unittest.main()
