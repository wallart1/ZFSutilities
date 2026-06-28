"""Tests for the GUI application entry point."""

import os
import sys
import tempfile
import unittest
from unittest.mock import ANY, MagicMock, mock_open, patch

from test_support import capture_logs, mock_gtk

# main.py is on PYTHON_SRC via test_support
import main as main_module


class _ExecvpCalled(Exception):
    """Raised by the mocked os.execvp to stop execution in pkexec tests."""

    def __init__(self, program, args):
        self.program = program
        self.args = args
        super().__init__(f"os.execvp called: {program} {args}")


class TestMainSingleInstance(unittest.TestCase):
    """Single-instance and stale-recovery behaviour in main()."""

    def setUp(self):
        fd, self._pid_path = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(self._cleanup_pid_file)
        self._pid_patcher = patch.object(main_module, "PID_FILE", self._pid_path)
        self._pid_patcher.start()
        self.addCleanup(self._pid_patcher.stop)

    def _cleanup_pid_file(self):
        try:
            os.remove(self._pid_path)
        except OSError:
            pass

    def _write_pid(self, pid):
        with open(self._pid_path, "w") as f:
            f.write(str(pid))

    def _make_app(self, remote=False):
        app = MagicMock()
        app.get_is_remote.return_value = remote
        return app

    def _make_app_class(self, *apps):
        calls = list(apps)

        def constructor(*args, **kwargs):
            if not calls:
                raise RuntimeError("ZFSUtilitiesApp called more times than expected")
            return calls.pop(0)

        return MagicMock(side_effect=constructor)

    def _run_main(self, argv, app_class=None, euid=0,
                  alive_pids=None, our_pids=None, pid_states=None,
                  terminate_ok=True, terminate_mock=None,
                  matching_pids=None, has_visible_window=True,
                  is_instance_stuck=False):
        """Run main.main() under controlled conditions.

        Returns a dict with the application class mock, the execvp mock, and
        the terminate mock so callers can inspect constructor calls and flags.
        """
        app_class = app_class or self._make_app_class()
        alive_pids = alive_pids or set()
        our_pids = our_pids or set()
        pid_states = pid_states or {}
        matching_pids = matching_pids or []

        def fake_is_pid_alive(pid):
            return pid in alive_pids

        def fake_is_zfsutilities_process(pid):
            return pid in our_pids

        def fake_pid_state(pid):
            return pid_states.get(pid)

        def fake_execvp(program, args):
            raise _ExecvpCalled(program, args)

        terminate_patch = patch.object(
            main_module, "_terminate_process",
            return_value=terminate_ok
        )
        if terminate_mock is not None:
            terminate_patch = patch.object(
                main_module, "_terminate_process", terminate_mock
            )

        with patch.object(main_module.os, "geteuid", return_value=euid), \
             patch.object(main_module.os, "execvp", side_effect=fake_execvp) as mock_execvp, \
             patch.object(main_module, "_is_pid_alive", side_effect=fake_is_pid_alive), \
             patch.object(main_module, "_is_zfsutilities_process", side_effect=fake_is_zfsutilities_process), \
             patch.object(main_module, "_pid_state", side_effect=fake_pid_state), \
             terminate_patch as mock_term, \
             patch.object(main_module, "_find_matching_pids", side_effect=[matching_pids, []] if matching_pids else [matching_pids]), \
             patch.object(main_module, "_has_visible_window", return_value=has_visible_window), \
             patch.object(main_module, "_is_instance_stuck", return_value=is_instance_stuck), \
             patch.object(main_module, "_show_wait_dialog", MagicMock()), \
             patch.object(main_module, "_pump_events_for", MagicMock()), \
             patch.object(main_module, "time", MagicMock()), \
             patch.object(main_module, "ZFSUtilitiesApp", app_class):
            with capture_logs():
                with patch.object(sys, "argv", argv):
                    try:
                        main_module.main()
                        execvp_called = False
                    except _ExecvpCalled:
                        execvp_called = True
        return {
            "app_class": app_class,
            "execvp": mock_execvp,
            "execvp_called": execvp_called,
            "terminate": mock_term,
            "find_matching": main_module._find_matching_pids,
        }

    def test_no_pid_file_starts_primary_with_replace(self):
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={}
        )
        result["app_class"].assert_called_once()
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        app.register.assert_called_once()
        app.run.assert_called_once()

    def test_stale_dead_pid_uses_replace(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={}
        )
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_stale_foreign_pid_uses_replace(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids=set(), pid_states={}
        )
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_stale_zombie_pid_uses_replace(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "Z"}
        )
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_stale_stopped_pid_uses_replace(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "T"}
        )
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_live_primary_replaces_without_asking(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "S"},
            terminate_mock=terminate_mock
        )
        terminate_mock.assert_called_once_with(1234, timeout=5.0, sleep_fn=ANY)
        result["app_class"].assert_called_once()
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        app.run.assert_called_once()
        self.assertFalse(os.path.exists(self._pid_path))

    def test_live_primary_with_replace_terminates_and_replaces(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py", "--replace"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "S"},
            terminate_mock=terminate_mock
        )
        terminate_mock.assert_called_once_with(1234, timeout=5.0, sleep_fn=ANY)
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_default_finds_untracked_matching_process(self):
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={},
            terminate_mock=terminate_mock,
            matching_pids=[5678, 5679]
        )
        self.assertEqual(terminate_mock.call_count, 2)
        terminate_mock.assert_any_call(5678, timeout=5.0, sleep_fn=ANY)
        terminate_mock.assert_any_call(5679, timeout=5.0, sleep_fn=ANY)
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)

    def test_replace_flag_is_accepted_as_no_op(self):
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        result = self._run_main(
            ["main.py", "--replace"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={}
        )
        result["app_class"].assert_called_once()
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        app.run.assert_called_once()

    def test_retries_registration_after_remote(self):
        first_app = self._make_app(remote=False)
        first_app.get_is_remote.return_value = True
        second_app = self._make_app(remote=False)
        second_app.get_is_remote.return_value = False
        app_class = self._make_app_class(first_app, second_app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={},
            terminate_mock=terminate_mock,
            matching_pids=[5678]
        )
        # First register is remote, then a fresh app is created and succeeds.
        self.assertEqual(app_class.call_count, 2)
        terminate_mock.assert_called_once_with(5678, timeout=5.0, sleep_fn=ANY)
        second_app.run.assert_called_once()

    def test_aborts_when_registration_stays_remote(self):
        first_app = self._make_app(remote=True)
        second_app = self._make_app(remote=True)
        app_class = self._make_app_class(first_app, second_app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={},
            terminate_mock=terminate_mock,
            matching_pids=[5678]
        )
        self.assertEqual(app_class.call_count, 2)
        terminate_mock.assert_called_once_with(5678, timeout=5.0, sleep_fn=ANY)
        first_app.run.assert_not_called()
        second_app.run.assert_not_called()

    def test_replace_passed_through_pkexec(self):
        result = self._run_main(
            ["main.py", "--replace"],
            euid=1000
        )
        self.assertTrue(result["execvp_called"])
        result["app_class"].assert_not_called()
        result["terminate"].assert_not_called()
        mock_execvp = result["execvp"]
        mock_execvp.assert_called_once()
        _program, args = mock_execvp.call_args[0]
        self.assertIn("--replace", args)


class TestPidHelpers(unittest.TestCase):
    """Unit tests for the PID file and termination helpers."""

    def test_none_pid_is_not_stale(self):
        stale, reason = main_module._pid_file_status(None)
        self.assertFalse(stale)
        self.assertIsNone(reason)

    def test_current_pid_is_not_stale(self):
        stale, reason = main_module._pid_file_status(os.getpid())
        self.assertFalse(stale)
        self.assertIsNone(reason)

    def test_pid_state_parses_running_state(self):
        with patch.object(main_module.os, "getpid", return_value=1), \
             patch("builtins.open", mock_open(
                 read_data=b"1 (systemd) S 0 1 1 0 -1 4194560 ...")):
            self.assertEqual(main_module._pid_state(1), "S")

    def test_terminate_process_sends_sigterm_then_sigkill(self):
        alive = {42: True}

        def fake_kill(pid, sig):
            self.assertEqual(pid, 42)
            if sig == main_module.signal.SIGTERM:
                alive[42] = True  # still alive after SIGTERM
            elif sig == main_module.signal.SIGKILL:
                alive[42] = False

        def fake_is_alive(pid):
            return alive[pid]

        with patch.object(main_module, "_is_pid_alive", side_effect=fake_is_alive), \
             patch.object(main_module.os, "kill", side_effect=fake_kill), \
             patch.object(main_module.time, "sleep"):
            result = main_module._terminate_process(42, timeout=0.0)
        self.assertTrue(result)
        self.assertFalse(alive[42])

    def test_terminate_process_already_dead(self):
        with patch.object(main_module, "_is_pid_alive", return_value=False), \
             patch.object(main_module.os, "kill") as mock_kill:
            result = main_module._terminate_process(42)
        self.assertTrue(result)
        mock_kill.assert_not_called()

    def test_find_matching_pids_includes_root_app(self):
        fake_entry = MagicMock()
        fake_entry.name = "1234"
        fake_entry.stat.return_value.st_uid = 0

        def fake_open(path, mode):
            if "1234" in path:
                return mock_open(read_data=b"/usr/bin/python3\x00/path/zfsutilities_gui.py\x00")(path, mode)
            raise FileNotFoundError(path)

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"), \
             patch("builtins.open", side_effect=fake_open):
            pids = main_module._find_matching_pids(exclude_pid=9999)
        self.assertEqual(pids, [1234])

    def test_find_matching_pids_includes_deployed_main_py(self):
        fake_entry = MagicMock()
        fake_entry.name = "1234"
        fake_entry.stat.return_value.st_uid = 0

        def fake_open(path, mode):
            if "1234" in path:
                return mock_open(
                    read_data=b"/usr/bin/python3\x00/usr/local/lib/zfsutilities/versions/0.55.2/07 GTK + Python/main.py\x00"
                )(path, mode)
            raise FileNotFoundError(path)

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"), \
             patch("builtins.open", side_effect=fake_open):
            pids = main_module._find_matching_pids(exclude_pid=9999)
        self.assertEqual(pids, [1234])

    def test_find_matching_pids_includes_wrapper_script(self):
        fake_entry = MagicMock()
        fake_entry.name = "1234"
        fake_entry.stat.return_value.st_uid = 0

        def fake_open(path, mode):
            if "1234" in path:
                return mock_open(
                    read_data=b"/usr/bin/python3\x00/home/dan/ZFSutilities GUI\x00"
                )(path, mode)
            raise FileNotFoundError(path)

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"), \
             patch("builtins.open", side_effect=fake_open):
            pids = main_module._find_matching_pids(exclude_pid=9999)
        self.assertEqual(pids, [1234])

    def test_find_matching_pids_excludes_non_root(self):
        fake_entry = MagicMock()
        fake_entry.name = "1234"
        fake_entry.stat.return_value.st_uid = 1000

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"):
            pids = main_module._find_matching_pids()
        self.assertEqual(pids, [])

    def test_find_matching_pids_excludes_self(self):
        fake_entry = MagicMock()
        fake_entry.name = str(os.getpid())
        fake_entry.stat.return_value.st_uid = 0

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"):
            pids = main_module._find_matching_pids(exclude_pid=os.getpid())
        self.assertEqual(pids, [])

    def test_find_matching_pids_excludes_non_python_exe(self):
        fake_entry = MagicMock()
        fake_entry.name = "1234"
        fake_entry.stat.return_value.st_uid = 0

        with patch.object(main_module.os, "scandir", return_value=[fake_entry]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/sudo"):
            pids = main_module._find_matching_pids(exclude_pid=9999)
        self.assertEqual(pids, [])

    def test_find_matching_pids_excludes_ancestors(self):
        fake_child = MagicMock()
        fake_child.name = "1000"
        fake_child.stat.return_value.st_uid = 0
        fake_parent = MagicMock()
        fake_parent.name = "500"
        fake_parent.stat.return_value.st_uid = 0

        def fake_open(path, mode):
            if "1000" in path or "500" in path:
                return mock_open(read_data=b"/usr/bin/python3\x00/path/zfsutilities_gui.py\x00")(path, mode)
            raise FileNotFoundError(path)

        def fake_ppid(pid):
            return 500 if pid == 1000 else 1

        with patch.object(main_module.os, "scandir", return_value=[fake_child, fake_parent]), \
             patch.object(main_module, "_get_process_exe", return_value="/usr/bin/python3"), \
             patch.object(main_module, "_get_ppid", side_effect=fake_ppid), \
             patch("builtins.open", side_effect=fake_open):
            pids = main_module._find_matching_pids(exclude_pid=1000)
        self.assertEqual(pids, [])


class TestMainStuckInstance(unittest.TestCase):
    """Startup behaviour when an existing instance has no visible window."""

    def setUp(self):
        fd, self._pid_path = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(self._cleanup_pid_file)
        self._pid_patcher = patch.object(main_module, "PID_FILE", self._pid_path)
        self._pid_patcher.start()
        self.addCleanup(self._pid_patcher.stop)

    def _cleanup_pid_file(self):
        try:
            os.remove(self._pid_path)
        except OSError:
            pass

    def _write_pid(self, pid):
        with open(self._pid_path, "w") as f:
            f.write(str(pid))

    def _make_app(self, remote=False):
        app = MagicMock()
        app.get_is_remote.return_value = remote
        return app

    def _make_app_class(self, *apps):
        calls = list(apps)

        def constructor(*args, **kwargs):
            if not calls:
                raise RuntimeError("ZFSUtilitiesApp called more times than expected")
            return calls.pop(0)

        return MagicMock(side_effect=constructor)

    def _run_main(self, argv, app_class=None, euid=0,
                  alive_pids=None, our_pids=None, pid_states=None,
                  terminate_ok=True, terminate_mock=None,
                  has_visible_window=False, is_instance_stuck=True,
                  matching_pids=None):
        app_class = app_class or self._make_app_class()
        alive_pids = alive_pids or set()
        our_pids = our_pids or set()
        pid_states = pid_states or {}
        matching_pids = matching_pids or []

        def fake_is_pid_alive(pid):
            return pid in alive_pids

        def fake_is_zfsutilities_process(pid):
            return pid in our_pids

        def fake_pid_state(pid):
            return pid_states.get(pid)

        terminate_patch = patch.object(
            main_module, "_terminate_process",
            return_value=terminate_ok
        )
        if terminate_mock is not None:
            terminate_patch = patch.object(
                main_module, "_terminate_process", terminate_mock
            )

        with patch.object(main_module.os, "geteuid", return_value=euid), \
             patch.object(main_module.os, "execvp", MagicMock()), \
             patch.object(main_module, "_is_pid_alive", side_effect=fake_is_pid_alive), \
             patch.object(main_module, "_is_zfsutilities_process", side_effect=fake_is_zfsutilities_process), \
             patch.object(main_module, "_pid_state", side_effect=fake_pid_state), \
             patch.object(main_module, "_has_visible_window", return_value=has_visible_window), \
             patch.object(main_module, "_is_instance_stuck", return_value=is_instance_stuck), \
             patch.object(main_module, "_find_matching_pids", side_effect=[matching_pids, []] if matching_pids else [matching_pids]), \
             patch.object(main_module, "_show_wait_dialog", MagicMock()), \
             patch.object(main_module, "_pump_events_for", MagicMock()), \
             terminate_patch as mock_term, \
             patch.object(main_module, "time", MagicMock()), \
             patch.object(main_module, "ZFSUtilitiesApp", app_class):
            with capture_logs():
                with patch.object(sys, "argv", argv):
                    main_module.main()
        return {
            "app_class": app_class,
            "terminate": mock_term,
        }

    def test_live_stuck_pid_in_file_terminates_and_replaces(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "S"},
            terminate_mock=terminate_mock,
            has_visible_window=False, is_instance_stuck=True,
        )
        terminate_mock.assert_called_once_with(1234, timeout=5.0, sleep_fn=ANY)
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))

    def test_untracked_stuck_instance_terminates_and_replaces(self):
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids=set(), our_pids=set(), pid_states={},
            terminate_mock=terminate_mock,
            matching_pids=[5678],
            has_visible_window=False, is_instance_stuck=True,
        )
        terminate_mock.assert_called_once_with(5678, timeout=5.0, sleep_fn=ANY)
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)

    def test_live_visible_pid_replaces_without_asking(self):
        self._write_pid(1234)
        app = self._make_app(remote=False)
        app_class = self._make_app_class(app)
        terminate_mock = MagicMock(return_value=True)
        result = self._run_main(
            ["main.py"], app_class,
            alive_pids={1234}, our_pids={1234}, pid_states={1234: "S"},
            terminate_mock=terminate_mock,
            has_visible_window=True, is_instance_stuck=False,
        )
        terminate_mock.assert_called_once_with(1234, timeout=5.0, sleep_fn=ANY)
        result["app_class"].assert_called_once()
        flags = result["app_class"].call_args.kwargs.get("flags", 0)
        self.assertEqual(flags, main_module.Gio.ApplicationFlags.REPLACE)
        self.assertFalse(os.path.exists(self._pid_path))


class TestWindowHelpers(unittest.TestCase):
    """Unit tests for X11 window-visibility helpers."""

    def test_is_window_visible_viewable_large_window(self):
        xwininfo_output = (
            "xwininfo: Window id: 0x4e00001 \"test\"\n\n"
            "  Width: 800\n"
            "  Height: 600\n"
            "  Map State: IsViewable\n"
        )
        with patch.object(main_module.subprocess, "run", return_value=MagicMock(
            returncode=0, stdout=xwininfo_output, stderr=""
        )):
            self.assertTrue(main_module._is_window_visible("0x4e00001"))

    def test_is_window_visible_unmapped_small_window(self):
        xwininfo_output = (
            "xwininfo: Window id: 0x4e00001 \"test\"\n\n"
            "  Width: 10\n"
            "  Height: 10\n"
            "  Map State: IsUnMapped\n"
        )
        with patch.object(main_module.subprocess, "run", return_value=MagicMock(
            returncode=0, stdout=xwininfo_output, stderr=""
        )):
            self.assertFalse(main_module._is_window_visible("0x4e00001"))

    def test_is_window_visible_command_fails(self):
        with patch.object(main_module.subprocess, "run", return_value=MagicMock(
            returncode=1, stdout="", stderr=""
        )):
            self.assertFalse(main_module._is_window_visible("0x4e00001"))

    def test_get_x11_windows_for_pid_parses_ids(self):
        with patch.object(main_module.subprocess, "run", return_value=MagicMock(
            returncode=0, stdout="12345\n67890\n", stderr=""
        )):
            windows = main_module._get_x11_windows_for_pid(42)
        self.assertEqual(windows, ["12345", "67890"])

    def test_get_x11_windows_for_pid_failure_returns_empty(self):
        with patch.object(main_module.subprocess, "run", return_value=MagicMock(
            returncode=1, stdout="", stderr=""
        )):
            windows = main_module._get_x11_windows_for_pid(42)
        self.assertEqual(windows, [])

    def test_has_visible_window_true(self):
        with patch.object(main_module, "_get_x11_windows_for_pid", return_value=["1", "2"]), \
             patch.object(main_module, "_is_window_visible", side_effect=[False, True]):
            self.assertTrue(main_module._has_visible_window(42))

    def test_has_visible_window_false(self):
        with patch.object(main_module, "_get_x11_windows_for_pid", return_value=["1"]), \
             patch.object(main_module, "_is_window_visible", return_value=False):
            self.assertFalse(main_module._has_visible_window(42))

    def test_is_instance_stuck_alive_old_no_window(self):
        with patch.object(main_module, "_is_pid_alive", return_value=True), \
             patch.object(main_module, "_has_visible_window", return_value=False), \
             patch.object(main_module, "_process_age_seconds", return_value=15):
            self.assertTrue(main_module._is_instance_stuck(42))

    def test_is_instance_stuck_alive_young_no_window(self):
        with patch.object(main_module, "_is_pid_alive", return_value=True), \
             patch.object(main_module, "_has_visible_window", return_value=False), \
             patch.object(main_module, "_process_age_seconds", return_value=5):
            self.assertFalse(main_module._is_instance_stuck(42))

    def test_is_instance_stuck_with_visible_window(self):
        with patch.object(main_module, "_is_pid_alive", return_value=True), \
             patch.object(main_module, "_has_visible_window", return_value=True):
            self.assertFalse(main_module._is_instance_stuck(42))

    def test_is_instance_stuck_dead(self):
        with patch.object(main_module, "_is_pid_alive", return_value=False):
            self.assertFalse(main_module._is_instance_stuck(42))


class TestWaitDialogHelpers(unittest.TestCase):
    """Tests for the transient wait dialog and event-pumping helpers."""

    def test_show_wait_dialog_creates_modal_info_dialog(self):
        dialog = MagicMock()
        with patch.object(
            main_module.Gtk, "MessageDialog", return_value=dialog
        ) as mock_dialog:
            with patch.object(main_module, "_pump_events_for"):
                result = main_module._show_wait_dialog("Please wait...")
        self.assertEqual(result, dialog)
        mock_dialog.assert_called_once()
        kwargs = mock_dialog.call_args.kwargs
        self.assertEqual(
            kwargs.get("message_type"), main_module.Gtk.MessageType.INFO
        )
        self.assertEqual(
            kwargs.get("buttons"), main_module.Gtk.ButtonsType.NONE
        )
        self.assertEqual(kwargs.get("text"), "Please wait...")
        dialog.set_title.assert_called_once_with("ZFS Utilities")
        dialog.set_deletable.assert_called_once_with(False)
        dialog.show_all.assert_called_once()
        dialog.destroy.assert_not_called()

    def test_pump_events_for_processes_pending_events(self):
        start = [0.0]

        def fake_time():
            start[0] += 0.02
            return start[0]

        pending_values = [True, True, False]

        def fake_pending():
            return pending_values.pop(0) if pending_values else False

        with patch.object(main_module, "time") as mock_time:
            mock_time.time.side_effect = fake_time
            mock_time.sleep = MagicMock()
            with patch.object(
                main_module.Gtk, "events_pending", side_effect=fake_pending
            ):
                with patch.object(
                    main_module.Gtk, "main_iteration_do"
                ) as mock_iter:
                    main_module._pump_events_for(0.1)
        self.assertEqual(mock_iter.call_count, 2)
        self.assertGreater(mock_time.sleep.call_count, 0)

    def test_pump_events_for_stops_after_timeout(self):
        start = [0.0]

        def fake_time():
            start[0] += 0.02
            return start[0]

        with patch.object(main_module, "time") as mock_time:
            mock_time.time.side_effect = fake_time
            mock_time.sleep = MagicMock()
            with patch.object(main_module.Gtk, "events_pending", return_value=False):
                main_module._pump_events_for(0.05)
        self.assertGreater(mock_time.sleep.call_count, 0)


if __name__ == "__main__":
    unittest.main()
