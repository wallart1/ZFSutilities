"""Tests for notifications.py — desktop/email run-completion notifications."""

import os
import smtplib
import stat
import sys
import threading
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
PYTHON_SRC = os.path.join(REPO_ROOT, "python")
if PYTHON_SRC not in sys.path:
    sys.path.insert(0, PYTHON_SRC)

import notifications
from feature_config import NOTIFICATION_TYPES
from test_support import capture_logs, patch_environ, temp_config_dir


def _channel(mode="all", **type_overrides):
    types = {run_type: True for run_type in NOTIFICATION_TYPES}
    types.update(type_overrides)
    return {"mode": mode, "types": types}


class TestChannelGating(unittest.TestCase):
    """Mode × result × run-type gating decides whether a channel fires."""

    def test_off_mode_never_fires(self):
        for result in ("success", "failed", "cancelled"):
            self.assertFalse(notifications._channel_fires(_channel("off"), result, "backup"))

    def test_failures_mode_fires_only_on_failed(self):
        channel = _channel("failures")
        self.assertFalse(notifications._channel_fires(channel, "success", "backup"))
        self.assertTrue(notifications._channel_fires(channel, "failed", "backup"))
        self.assertFalse(notifications._channel_fires(channel, "cancelled", "backup"))

    def test_all_mode_fires_on_every_reported_result(self):
        channel = _channel("all")
        for result in ("success", "failed", "cancelled"):
            self.assertTrue(notifications._channel_fires(channel, result, "backup"))

    def test_unknown_result_never_fires(self):
        self.assertFalse(notifications._channel_fires(_channel("all"), "bogus", "backup"))
        self.assertFalse(notifications._channel_fires(_channel("failures"), "bogus", "backup"))

    def test_toggled_off_type_never_fires_even_on_failure(self):
        channel = _channel("failures", backup=False)
        self.assertFalse(notifications._channel_fires(channel, "failed", "backup"))
        self.assertTrue(notifications._channel_fires(channel, "failed", "offsite"))

    def test_type_toggle_gates_per_type(self):
        channel = _channel("all", scrub=False, dataset=False)
        self.assertFalse(notifications._channel_fires(channel, "success", "scrub"))
        self.assertFalse(notifications._channel_fires(channel, "failed", "dataset"))
        self.assertTrue(notifications._channel_fires(channel, "success", "restore"))

    def test_prune_alias_maps_to_retention(self):
        self.assertEqual(notifications.normalize_run_type("prune"), "retention")
        channel = _channel("all", retention=False)
        self.assertFalse(notifications._channel_fires(channel, "failed", "prune"))
        self.assertEqual(notifications.run_type_label("prune"), "Retention prune")


class TestNotifyRunFinishedDispatch(unittest.TestCase):
    """notify_run_finished routes to the channels its gating selects."""

    def _notify(self, config, result="failed", run_type="backup", rc=1):
        notifications.notify_run_finished(
            result=result,
            name="nightly",
            run_type=run_type,
            rc=rc,
            duration=12.0,
            bytes_transferred=2048,
            log_file="/tmp/some.log",
            session_log_file=None,
            config=config,
        )

    def test_off_config_touches_no_channel(self):
        config = {"notifications": {"desktop": _channel("off"), "email": _channel("off")}}
        with (
            patch("notifications.send_desktop_notification") as mock_desktop,
            patch("notifications.send_email") as mock_email,
        ):
            self._notify(config, result="failed")
        mock_desktop.assert_not_called()
        mock_email.assert_not_called()

    def test_failed_run_reaches_both_channels(self):
        config = {"notifications": {"desktop": _channel("failures"), "email": _channel("failures")}}
        with (
            patch("notifications.send_desktop_notification") as mock_desktop,
            patch("notifications.send_email") as mock_email,
        ):
            self._notify(config, result="failed", rc=23)
        mock_desktop.assert_called_once()
        mock_email.assert_called_once()
        summary = mock_desktop.call_args.args[0]
        body = mock_desktop.call_args.args[1]
        self.assertEqual(summary, "Backup failed: nightly")
        self.assertIn("rc=23", body)
        self.assertIn("nightly", body)

    def test_success_only_reaches_all_mode_channels(self):
        config = {"notifications": {"desktop": _channel("all"), "email": _channel("failures")}}
        with (
            patch("notifications.send_desktop_notification") as mock_desktop,
            patch("notifications.send_email") as mock_email,
        ):
            self._notify(config, result="success", rc=0)
        mock_desktop.assert_called_once()
        mock_email.assert_not_called()

    def test_toggled_off_type_sends_nowhere(self):
        config = {
            "notifications": {
                "desktop": _channel("all", backup=False),
                "email": _channel("failures", backup=False),
            }
        }
        with (
            patch("notifications.send_desktop_notification") as mock_desktop,
            patch("notifications.send_email") as mock_email,
        ):
            self._notify(config, result="failed", run_type="backup")
        mock_desktop.assert_not_called()
        mock_email.assert_not_called()

    def test_email_receives_normalized_config(self):
        config = {"notifications": {"desktop": _channel("off"), "email": _channel("all")}}
        with (
            patch("notifications.send_desktop_notification"),
            patch("notifications.send_email") as mock_email,
        ):
            self._notify(config, result="success", rc=0)
        email_cfg = mock_email.call_args.args[2]
        self.assertEqual(email_cfg["mode"], "all")
        self.assertTrue(email_cfg["types"]["backup"])

    def test_never_raises_on_internal_failure(self):
        with patch("notifications.load_config", side_effect=OSError("boom")):
            # No config passed: the loader raises inside, which must be
            # swallowed rather than propagate into the runner.
            notifications.notify_run_finished(result="failed", name="x", run_type="backup", rc=1)

    def test_dispatch_failure_is_logged_not_raised(self):
        config = {"notifications": {"desktop": _channel("failures"), "email": _channel("off")}}
        with (
            patch("notifications.send_desktop_notification", side_effect=RuntimeError("boom")),
            capture_logs() as logs,
        ):
            self._notify(config, result="failed")
        self.assertTrue(any("Notification dispatch failed" in line for line in logs))

    def test_rc_none_omits_rc_from_body(self):
        config = {"notifications": {"desktop": _channel("all"), "email": _channel("off")}}
        with patch("notifications.send_desktop_notification") as mock_desktop:
            notifications.notify_run_finished(
                result="cancelled", name="x", run_type="backup", rc=None, config=config
            )
        body = mock_desktop.call_args.args[1]
        self.assertIn("Result: cancelled", body)
        self.assertNotIn("rc=", body)


class TestAsyncDelivery(unittest.TestCase):
    """GUI-main-thread calls deliver on a daemon thread; others run inline."""

    def test_off_gui_thread_runs_synchronously(self):
        calls = []

        def work():
            calls.append(("work", threading.current_thread()))
            return "ok"

        def on_done(result):
            calls.append(("on_done", threading.current_thread(), result))

        notifications._run_maybe_async(work, on_done=on_done)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], threading.current_thread())
        self.assertEqual(calls[1][1], threading.current_thread())
        self.assertEqual(calls[1][2], "ok")

    def test_gui_main_thread_delivers_via_daemon_thread(self):
        work_thread = []
        idle_callbacks = []
        idle_registered = threading.Event()
        work_done = threading.Event()
        direct_on_done = []
        glib = MagicMock()

        def fake_idle_add(fn):
            idle_callbacks.append(fn)
            idle_registered.set()
            return 1

        glib.idle_add.side_effect = fake_idle_add

        def work():
            work_thread.append(threading.current_thread())
            work_done.set()
            return "ok"

        with (
            patch("notifications._on_gui_main_thread", return_value=True),
            patch("notifications._get_glib", return_value=glib),
        ):
            notifications._run_maybe_async(work, on_done=direct_on_done.append)
        self.assertTrue(work_done.wait(timeout=10))
        self.assertTrue(idle_registered.wait(timeout=10))
        self.assertIsNot(work_thread[0], threading.current_thread())
        # on_done was marshalled through idle_add, never called directly.
        self.assertEqual(direct_on_done, [])
        idle_callbacks[0]()
        self.assertEqual(direct_on_done, ["ok"])

    def test_delivery_thread_logs_hop_through_idle_add(self):
        glib = MagicMock()
        idle_callbacks = []
        glib.idle_add.side_effect = lambda fn: (idle_callbacks.append(fn), 1)[1]
        with patch("notifications._get_glib", return_value=glib):
            notifications._delivery_context.marshal_logs = True
            try:
                with capture_logs() as logs:
                    notifications._log("WARN: hop me")
            finally:
                notifications._delivery_context.marshal_logs = False
        self.assertEqual(logs, [])
        self.assertEqual(len(idle_callbacks), 1)
        # Running the marshalled callback delivers the line for real.
        with capture_logs() as delivered:
            idle_callbacks[0]()
        self.assertTrue(any("hop me" in line for line in delivered))
        # Without the thread-local flag the same context logs directly.
        with patch("notifications._get_glib", return_value=glib):
            with capture_logs() as direct:
                notifications._log("WARN: direct me")
        self.assertTrue(any("direct me" in line for line in direct))
        self.assertEqual(len(idle_callbacks), 1)

    def test_on_gui_main_thread_requires_glib_and_log_sink(self):
        with patch("notifications._get_glib", return_value=None):
            self.assertFalse(notifications._on_gui_main_thread())
        glib = MagicMock()  # MainContext.default().is_owner() is truthy
        with (
            patch("notifications._get_glib", return_value=glib),
            patch("notifications.get_log_sink", return_value=None),
        ):
            self.assertFalse(notifications._on_gui_main_thread())
        with (
            patch("notifications._get_glib", return_value=glib),
            patch("notifications.get_log_sink", return_value=object()),
        ):
            self.assertTrue(notifications._on_gui_main_thread())


class TestBuildMessages(unittest.TestCase):
    """Message text covers the run facts shown to the user."""

    def test_body_includes_all_facts(self):
        summary, body, subject = notifications._build_messages(
            "failed", "nightly", "backup", 23, 3617.5, 1024**3, "/var/log/x.log"
        )
        self.assertEqual(summary, "Backup failed: nightly")
        self.assertIn("Result: failed (rc=23)", body)
        self.assertIn("Duration:", body)
        self.assertIn("Transferred:", body)
        self.assertIn("Host:", body)
        self.assertIn("/var/log/x.log", body)
        self.assertTrue(subject.startswith("[ZFS Utilities]"))

    def test_unknown_type_gets_title_cased_label(self):
        summary, _body, _subject = notifications._build_messages(
            "success", "x", "weird", 0, None, 0, None
        )
        self.assertTrue(summary.startswith("Weird success:"))


class TestDesktopCommand(unittest.TestCase):
    """Command construction prefers notify-send and falls back to gdbus."""

    def test_notify_send_when_available(self):
        with patch("notifications.shutil.which", return_value="/usr/bin/notify-send"):
            command = notifications._desktop_command(
                "dan", "/run/user/1000/bus", ":0", "s", "b", "dialog-error", "critical"
            )
        self.assertEqual(command[:5], ["runuser", "-u", "dan", "--", "env"])
        self.assertIn("DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus", command)
        self.assertIn("DISPLAY=:0", command)
        self.assertIn("/usr/bin/notify-send", command)
        self.assertIn("critical", command)
        self.assertIn("dialog-error", command)
        self.assertEqual(command[-2:], ["s", "b"])

    def test_gdbus_fallback_without_notify_send(self):
        def which(tool):
            return "/usr/bin/gdbus" if tool == "gdbus" else None

        with patch("notifications.shutil.which", side_effect=which):
            command = notifications._desktop_command(
                "dan", "/run/user/1000/bus", ":0", "s", "b", "dialog-error", "critical"
            )
        self.assertIn("/usr/bin/gdbus", command)
        self.assertIn("org.freedesktop.Notifications.Notify", command)
        # Empty actions/hints arrays and a positive timeout are required:
        # dbus-send cannot express a{sv}, and a bare -1 parses as a flag.
        self.assertEqual(command[-5:], ["s", "b", "[]", "{}", "10000"])

    def test_none_when_no_tool_available(self):
        with patch("notifications.shutil.which", return_value=None):
            command = notifications._desktop_command(
                "dan", "/run/user/1000/bus", ":0", "s", "b", "dialog-error", "critical"
            )
        self.assertIsNone(command)


class TestResolveDesktopUser(unittest.TestCase):
    """User resolution prefers the override/SUDO_USER, then the X11 socket."""

    def test_sudo_user_with_live_bus_wins(self):
        pw = MagicMock()
        pw.pw_uid = 1000
        pw.pw_name = "dan"
        with (
            patch_environ(
                SUDO_USER="dan", DISPLAY=":0", ZFSUTILITIES_NOTIFICATION_DESKTOP_USER=None
            ),
            patch("notifications.pwd.getpwnam", return_value=pw) as mock_pwnam,
            patch("notifications.os.path.exists", return_value=True),
        ):
            self.assertEqual(
                notifications._resolve_desktop_user(), ("dan", "/run/user/1000/bus", ":0")
            )
        mock_pwnam.assert_called_once_with("dan")

    def test_sudo_user_without_bus_falls_through_to_socket(self):
        sudo_pw = MagicMock()
        sudo_pw.pw_uid = 1000
        sudo_pw.pw_name = "dan"
        owner_pw = MagicMock()
        owner_pw.pw_uid = 1001
        owner_pw.pw_name = "desk"

        def exists(path):
            return path == "/run/user/1001/bus"

        stat_result = MagicMock()
        stat_result.st_uid = 1001
        with (
            patch_environ(
                SUDO_USER="dan", DISPLAY=":0", ZFSUTILITIES_NOTIFICATION_DESKTOP_USER=None
            ),
            patch("notifications.pwd.getpwnam", return_value=sudo_pw),
            patch("notifications.os.path.exists", side_effect=exists),
            patch("notifications.os.stat", return_value=stat_result),
            patch("notifications.pwd.getpwuid", return_value=owner_pw),
        ):
            self.assertEqual(
                notifications._resolve_desktop_user(), ("desk", "/run/user/1001/bus", ":0")
            )

    def test_no_socket_means_no_session(self):
        with (
            patch_environ(
                SUDO_USER=None, DISPLAY=":0", ZFSUTILITIES_NOTIFICATION_DESKTOP_USER=None
            ),
            patch("notifications.os.stat", side_effect=OSError("no socket")),
        ):
            self.assertIsNone(notifications._resolve_desktop_user())

    def test_root_owned_socket_is_rejected(self):
        stat_result = MagicMock()
        stat_result.st_uid = 0
        with (
            patch_environ(
                SUDO_USER=None, DISPLAY=":0", ZFSUTILITIES_NOTIFICATION_DESKTOP_USER=None
            ),
            patch("notifications.os.stat", return_value=stat_result),
        ):
            self.assertIsNone(notifications._resolve_desktop_user())


class TestDesktopDelivery(unittest.TestCase):
    """send_desktop_notification is best effort with WARN on failure."""

    def _ok_process(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        return proc

    def test_success_runs_command_as_user(self):
        with (
            patch(
                "notifications._resolve_desktop_user",
                return_value=("dan", "/run/user/1000/bus", ":0"),
            ),
            patch("notifications._desktop_command", return_value=["runuser"]),
            patch("notifications.subprocess.run", return_value=self._ok_process()) as mock_run,
        ):
            self.assertTrue(
                notifications.send_desktop_notification("s", "b", session_log_file=None)
            )
        self.assertEqual(mock_run.call_args.kwargs.get("timeout"), notifications._desktop_timeout())

    def test_no_session_skips_with_info_log(self):
        with (
            patch("notifications._resolve_desktop_user", return_value=None),
            capture_logs() as logs,
        ):
            self.assertFalse(
                notifications.send_desktop_notification("s", "b", session_log_file=None)
            )
        self.assertTrue(any("no logged-in desktop session" in line for line in logs))

    def test_no_tool_warns(self):
        with (
            patch(
                "notifications._resolve_desktop_user",
                return_value=("dan", "/run/user/1000/bus", ":0"),
            ),
            patch("notifications._desktop_command", return_value=None),
            capture_logs() as logs,
        ):
            self.assertFalse(
                notifications.send_desktop_notification("s", "b", session_log_file=None)
            )
        self.assertTrue(any("neither notify-send nor gdbus" in line for line in logs))

    def test_nonzero_rc_warns(self):
        proc = self._ok_process()
        proc.returncode = 1
        proc.stderr = "no notification daemon"
        with (
            patch(
                "notifications._resolve_desktop_user",
                return_value=("dan", "/run/user/1000/bus", ":0"),
            ),
            patch("notifications._desktop_command", return_value=["runuser"]),
            patch("notifications.subprocess.run", return_value=proc),
            capture_logs() as logs,
        ):
            self.assertFalse(
                notifications.send_desktop_notification("s", "b", session_log_file=None)
            )
        self.assertTrue(any("Desktop notification failed (rc=1)" in line for line in logs))

    def test_timeout_is_contained(self):
        with (
            patch(
                "notifications._resolve_desktop_user",
                return_value=("dan", "/run/user/1000/bus", ":0"),
            ),
            patch("notifications._desktop_command", return_value=["runuser"]),
            patch(
                "notifications.subprocess.run",
                side_effect=notifications.subprocess.TimeoutExpired("cmd", 10),
            ),
            capture_logs() as logs,
        ):
            self.assertFalse(
                notifications.send_desktop_notification("s", "b", session_log_file=None)
            )
        self.assertTrue(any("Desktop notification failed" in line for line in logs))

    def test_timeout_env_knob(self):
        with patch_environ(ZFSUTILITIES_NOTIFICATION_DESKTOP_TIMEOUT="2.5"):
            self.assertEqual(notifications._desktop_timeout(), 2.5)


class TestEmailDelivery(unittest.TestCase):
    """send_email drives smtplib per the configured security mode."""

    EMAIL_CFG: ClassVar[dict] = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_security": "starttls",
        "smtp_username": "user@example.com",
        "smtp_from": "zfs@example.com",
        "smtp_to": ["a@example.com", "b@example.com"],
    }

    def test_starttls_with_login(self):
        server = MagicMock()
        with (
            patch("notifications.smtplib.SMTP", return_value=server) as mock_smtp,
            patch("notifications.load_smtp_password", return_value="secret"),
        ):
            self.assertTrue(
                notifications.send_email("subject", "body", self.EMAIL_CFG, session_log_file=None)
            )
        mock_smtp.assert_called_once_with(
            "smtp.example.com", 587, timeout=notifications._email_timeout()
        )
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user@example.com", "secret")
        server.send_message.assert_called_once()
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "subject")
        self.assertEqual(message["From"], "zfs@example.com")
        self.assertEqual(message["To"], "a@example.com, b@example.com")
        server.quit.assert_called_once()

    def test_ssl_uses_smtp_ssl(self):
        server = MagicMock()
        cfg = dict(self.EMAIL_CFG, smtp_security="ssl", smtp_port=465, smtp_username="")
        with (
            patch("notifications.smtplib.SMTP_SSL", return_value=server) as mock_ssl,
            patch("notifications.smtplib.SMTP") as mock_plain,
        ):
            self.assertTrue(notifications.send_email("s", "b", cfg, session_log_file=None))
        mock_ssl.assert_called_once_with(
            "smtp.example.com", 465, timeout=notifications._email_timeout()
        )
        mock_plain.assert_not_called()
        server.starttls.assert_not_called()
        server.login.assert_not_called()

    def test_transient_password_overrides_credentials_file(self):
        server = MagicMock()
        cfg = dict(self.EMAIL_CFG, smtp_password="dialog-value")
        with (
            patch("notifications.smtplib.SMTP", return_value=server),
            patch("notifications.load_smtp_password", return_value="stored") as mock_load,
        ):
            self.assertTrue(notifications.send_email("s", "b", cfg, session_log_file=None))
        mock_load.assert_not_called()
        server.login.assert_called_once_with("user@example.com", "dialog-value")

    def test_missing_host_or_recipient_skips_with_warn(self):
        with capture_logs() as logs:
            self.assertFalse(
                notifications.send_email("s", "b", {"smtp_host": "", "smtp_to": ["a@b.c"]})
            )
            self.assertFalse(notifications.send_email("s", "b", {"smtp_host": "x", "smtp_to": []}))
        self.assertEqual(len([line for line in logs if "not configured" in line]), 2)

    def test_timeout_env_knob(self):
        with patch_environ(ZFSUTILITIES_NOTIFICATION_EMAIL_TIMEOUT="45"):
            self.assertEqual(notifications._email_timeout(), 45.0)

    def test_smtp_failure_warns_and_returns_false(self):
        with (
            patch("notifications.smtplib.SMTP", side_effect=smtplib.SMTPException("rejected")),
            capture_logs() as logs,
        ):
            self.assertFalse(
                notifications.send_email("s", "b", self.EMAIL_CFG, session_log_file=None)
            )
        self.assertTrue(any("Email notification failed" in line for line in logs))

    def test_from_defaults_to_username(self):
        server = MagicMock()
        cfg = dict(self.EMAIL_CFG, smtp_from="")
        with patch("notifications.smtplib.SMTP", return_value=server):
            self.assertTrue(notifications.send_email("s", "b", cfg, session_log_file=None))
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["From"], "user@example.com")


class TestSmtpCredentialsFile(unittest.TestCase):
    """The SMTP password lives in a 0600 root-only file."""

    def test_save_load_round_trip_and_permissions(self):
        with temp_config_dir() as state:
            credentials_dir = os.path.join(state, "etc")
            os.makedirs(credentials_dir, exist_ok=True)
            with patch_environ(ZFSUTILITIES_CONFIG_DIR=credentials_dir):
                notifications.save_smtp_password("hunter2")
                path = notifications.get_smtp_credentials_path()
                self.assertEqual(path, os.path.join(credentials_dir, "smtp-credentials.json"))
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
                self.assertEqual(notifications.load_smtp_password(), "hunter2")

    def test_empty_password_removes_file(self):
        with temp_config_dir() as state:
            credentials_dir = os.path.join(state, "etc")
            os.makedirs(credentials_dir, exist_ok=True)
            with patch_environ(ZFSUTILITIES_CONFIG_DIR=credentials_dir):
                notifications.save_smtp_password("hunter2")
                notifications.save_smtp_password("")
                self.assertEqual(notifications.load_smtp_password(), "")
                self.assertFalse(os.path.exists(notifications.get_smtp_credentials_path()))

    def test_missing_file_loads_empty(self):
        with temp_config_dir() as state:
            credentials_dir = os.path.join(state, "etc")
            os.makedirs(credentials_dir, exist_ok=True)
            with patch_environ(ZFSUTILITIES_CONFIG_DIR=credentials_dir):
                self.assertEqual(notifications.load_smtp_password(), "")


class TestTestHelpers(unittest.TestCase):
    """Dialog test-button helpers route through the same delivery code."""

    def test_send_desktop_test_invokes_delivery(self):
        with patch("notifications.send_desktop_notification") as mock_send:
            notifications.send_desktop_test(session_log_file=None)
        mock_send.assert_called_once()
        self.assertIn("test notification", mock_send.call_args.args[0])

    def test_send_email_test_passes_dialog_password(self):
        config = {"notifications": {"email": dict(TestEmailDelivery.EMAIL_CFG)}}
        with patch("notifications.send_email") as mock_send:
            notifications.send_email_test(config=config, password="from-dialog")
        email_cfg = mock_send.call_args.args[2]
        self.assertEqual(email_cfg["smtp_password"], "from-dialog")


if __name__ == "__main__":
    unittest.main()
