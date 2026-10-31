"""Desktop and email run-completion notifications.

Fires when a run finishes (success, failure, or cancellation) at the two
points every run already shares: ``profile_runner.main()`` for scheduled and
Run-Now runs, and ``BackupRunner._finish()``/``cancel()`` for interactive GUI
runs. Each channel (desktop, email) is gated independently by its mode
(off / failures / all) and its per-run-type toggles; a toggled-off run type
never notifies on that channel.

Delivery is best effort: a notification failure is logged (WARN to the
session log) and never fails the run it reports on. When called on the GUI
main thread, delivery runs on a daemon thread so a slow SMTP server can
never freeze the interface, and log lines are marshalled back to the GTK
main loop via GLib.idle_add. Headless callers (profile_runner, cron) run
synchronously.

Desktop bubbles are delivered to the logged-in desktop session's
notification daemon, preferring ``notify-send`` and falling back to
``gdbus`` (dbus-send cannot express the a{sv} hints argument of
org.freedesktop.Notifications). Email goes through user-configured SMTP via
smtplib, so it works from root cron without a local mail agent.
"""

import contextlib
import json
import os
import pwd
import shutil
import smtplib
import socket
import subprocess
import threading
from email.message import EmailMessage

from backup_history import format_duration
from config_core import load_config
from disk_repository import format_bytes
from feature_config import get_notifications_config
from logging_config import get_log_sink, log_msg
from paths import get_smtp_credentials_path

APP_NAME = "ZFS Utilities"

# Raw run-type strings as stored in history/tab code mapped to the canonical
# notification type keys (feature_config.NOTIFICATION_TYPES). GUI prune runs
# are logged with the "prune" tab type; profiles use "retention".
_RUN_TYPE_ALIASES = {
    "prune": "retention",
}

_TYPE_LABELS = {
    "backup": "Backup",
    "offsite": "Offsite backup",
    "restore": "Restore",
    "retention": "Retention prune",
    "scrub": "Scrub",
    "dataset": "Dataset action",
}

_RESULT_ICONS = {
    "success": "dialog-information",
    "failed": "dialog-error",
    "cancelled": "dialog-warning",
}

_RESULT_URGENCY = {
    "success": "normal",
    "failed": "critical",
    "cancelled": "normal",
}

# Results reported in "all" mode. "failures" mode reports only "failed".
_REPORTED_RESULTS = ("success", "failed", "cancelled")

# GLib is a GUI-only dependency; headless hosts may not have python3-gi, so
# it is loaded lazily and every use degrades to synchronous behavior.
_GLib = None
_glib_import_attempted = False

# Set on threads spawned by _run_maybe_async for delivery work; only those
# threads marshal log lines through the GTK main loop (their log_msg would
# otherwise touch widgets from off the main thread).
_delivery_context = threading.local()


def _get_glib():
    """Return the GLib module when importable, else None (cached).

    GLib is loaded dynamically (not via a top-level gi import) on purpose:
    this module is also imported by the headless profile runner, where the
    textual ``gi`` import would wrongly classify it as a GUI module (tests'
    GUI closure) and require python3-gi on GUI-less hosts. GLib itself needs
    no require_version pin (no 3/4 split like Gtk).
    """
    global _GLib, _glib_import_attempted
    if not _glib_import_attempted:
        _glib_import_attempted = True
        try:
            import importlib

            _GLib = importlib.import_module("gi.repository").GLib
        except Exception:
            _GLib = None
    return _GLib


def _on_gui_main_thread():
    """True when called from the GTK main loop thread of a running GUI."""
    glib = _get_glib()
    if glib is None or get_log_sink() is None:
        return False
    try:
        return glib.MainContext.default().is_owner()
    except Exception:
        return False


def _log(msg, session_log_file=None):
    """log_msg wrapper safe from delivery threads.

    Log lines emitted from a delivery thread spawned by _run_maybe_async are
    marshalled to the GTK main loop via GLib.idle_add, because the GUI log
    sink touches widgets. Every other context logs directly.
    """
    glib = _get_glib()
    if glib is not None and getattr(_delivery_context, "marshal_logs", False):
        glib.idle_add(lambda: _log_direct(msg, session_log_file))
    else:
        _log_direct(msg, session_log_file)


def _log_direct(msg, session_log_file=None):
    with contextlib.suppress(Exception):
        log_msg(msg, session_log_file=session_log_file)


def _run_maybe_async(work, on_done=None):
    """Run work() off the GUI main thread, reporting its result via on_done.

    On the GUI main thread the work (and the on_done report, via
    GLib.idle_add) run on a daemon thread so slow delivery can never freeze
    the interface. Elsewhere everything runs synchronously.
    """
    if _on_gui_main_thread():
        glib = _get_glib()

        def runner():
            _delivery_context.marshal_logs = True
            result = work()
            if on_done is not None:
                glib.idle_add(lambda: on_done(result))

        threading.Thread(target=runner, daemon=True).start()
    else:
        result = work()
        if on_done is not None:
            on_done(result)


def _desktop_timeout():
    return float(os.environ.get("ZFSUTILITIES_NOTIFICATION_DESKTOP_TIMEOUT", "10"))


def _email_timeout():
    return float(os.environ.get("ZFSUTILITIES_NOTIFICATION_EMAIL_TIMEOUT", "30"))


def normalize_run_type(run_type):
    """Map a raw run-type string to its canonical notification type key."""
    return _RUN_TYPE_ALIASES.get(run_type, run_type)


def run_type_label(run_type):
    """Return the GUI-facing label for a raw run-type string."""
    return _TYPE_LABELS.get(normalize_run_type(run_type), str(run_type).title())


def _channel_fires(channel, result, run_type):
    """Return True when *channel* wants a notification for this run."""
    mode = channel.get("mode", "off")
    if mode == "off":
        return False
    if mode == "failures":
        if result != "failed":
            return False
    elif result not in _REPORTED_RESULTS:
        return False
    return channel.get("types", {}).get(normalize_run_type(run_type), True)


def _resolve_desktop_user():
    """Return (username, bus_path, display) for the desktop session, or None.

    Prefers an explicit override (ZFSUTILITIES_NOTIFICATION_DESKTOP_USER),
    then SUDO_USER (the GUI runs as root via sudo), then the owner of the
    X11 display socket — mirroring lib/desktop-launcher-lib.sh. Requires a
    live session bus (/run/user/<uid>/bus); a host with no logged-in
    desktop session returns None and desktop notifications are skipped.
    """
    user = os.environ.get("ZFSUTILITIES_NOTIFICATION_DESKTOP_USER") or os.environ.get("SUDO_USER")
    if user:
        try:
            pwentry = pwd.getpwnam(user)
        except KeyError:
            pwentry = None
        if pwentry is not None:
            display = (os.environ.get("DISPLAY") or ":0").split(".")[0]
            bus = f"/run/user/{pwentry.pw_uid}/bus"
            if os.path.exists(bus):
                return pwentry.pw_name, bus, display
    display = (os.environ.get("DISPLAY") or ":0").split(".")[0]
    display_num = display.lstrip(":")
    try:
        uid = os.stat(f"/tmp/.X11-unix/X{display_num}").st_uid
    except OSError:
        return None
    if uid == 0:
        return None
    try:
        pwentry = pwd.getpwuid(uid)
    except KeyError:
        return None
    bus = f"/run/user/{pwentry.pw_uid}/bus"
    if not os.path.exists(bus):
        return None
    return pwentry.pw_name, bus, display


def _desktop_command(user, bus, display, summary, body, icon, urgency):
    """Build the notification-delivery command, or None when no tool exists."""
    base = ["runuser", "-u", user, "--", "env", f"DBUS_SESSION_BUS_ADDRESS=unix:path={bus}"]
    if display:
        base.append(f"DISPLAY={display}")
    notify_send = shutil.which("notify-send")
    if notify_send:
        return base + [
            notify_send,
            "-a",
            APP_NAME,
            "-u",
            urgency,
            "-i",
            icon,
            summary,
            body,
        ]
    gdbus = shutil.which("gdbus")
    if gdbus:
        return base + [
            gdbus,
            "call",
            "--session",
            "--dest",
            "org.freedesktop.Notifications",
            "--object-path",
            "/org/freedesktop/Notifications",
            "--method",
            "org.freedesktop.Notifications.Notify",
            APP_NAME,
            "0",
            icon,
            summary,
            body,
            "[]",
            "{}",
            "10000",
        ]
    return None


def send_desktop_notification(
    summary, body, icon="dialog-information", urgency="normal", session_log_file=None
):
    """Deliver one desktop bubble. Best effort; returns True on success."""
    target = _resolve_desktop_user()
    if target is None:
        _log(
            "INFO: Desktop notification skipped: no logged-in desktop session",
            session_log_file,
        )
        return False
    user, bus, display = target
    command = _desktop_command(user, bus, display, summary, body, icon, urgency)
    if command is None:
        _log(
            "WARN: Desktop notification unavailable: neither notify-send nor gdbus is installed",
            session_log_file,
        )
        return False
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_desktop_timeout(),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _log(f"WARN: Desktop notification failed: {exc}", session_log_file)
        return False
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        _log(
            f"WARN: Desktop notification failed (rc={proc.returncode}): {detail}",
            session_log_file,
        )
        return False
    _log(f"INFO: Desktop notification sent: {summary}", session_log_file)
    return True


def load_smtp_password():
    """Return the stored SMTP password, or "" when none is stored."""
    try:
        with open(get_smtp_credentials_path()) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    return data.get("password", "")


def save_smtp_password(password):
    """Store the SMTP password in a root-only 0600 file.

    An empty password removes the credentials file so no stale secret
    survives disabling SMTP authentication.
    """
    path = get_smtp_credentials_path()
    if not password:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump({"password": password}, fh)
    os.chmod(path, 0o600)


def send_email(subject, body, email_cfg, session_log_file=None):
    """Send one notification email. Best effort; returns True on success."""
    host = str(email_cfg.get("smtp_host") or "").strip()
    to_addrs = email_cfg.get("smtp_to") or []
    if not host or not to_addrs:
        _log(
            "WARN: Email notification skipped: SMTP host or recipient is not configured",
            session_log_file,
        )
        return False
    try:
        port = int(email_cfg.get("smtp_port") or 587)
    except (TypeError, ValueError):
        port = 587
    security = email_cfg.get("smtp_security", "starttls")
    username = str(email_cfg.get("smtp_username") or "").strip()
    from_addr = str(email_cfg.get("smtp_from") or "").strip()
    if not from_addr:
        from_addr = username or f"zfsutilities@{socket.gethostname()}"
    # A transient "smtp_password" key (set by the dialog's test button from
    # the unsaved entry) overrides the stored credentials file.
    password = str(email_cfg.get("smtp_password") or "")
    if not password and username:
        password = load_smtp_password()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    message.set_content(body)

    server = None
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=_email_timeout())
        else:
            server = smtplib.SMTP(host, port, timeout=_email_timeout())
        if security == "starttls":
            server.starttls()
        if username and password:
            server.login(username, password)
        server.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        _log(f"WARN: Email notification failed: {exc}", session_log_file)
        return False
    finally:
        if server is not None:
            with contextlib.suppress(Exception):
                server.quit()
    _log(
        f"INFO: Email notification sent to {', '.join(to_addrs)}: {subject}",
        session_log_file,
    )
    return True


def _build_messages(result, name, run_type, rc, duration, bytes_transferred, log_file):
    """Return (summary, body, email_subject) describing the finished run."""
    label = run_type_label(run_type)
    summary = f"{label} {result}: {name}"
    result_line = f"Result: {result}" if rc is None else f"Result: {result} (rc={rc})"
    lines = [
        f"Run: {name}",
        f"Type: {label}",
        result_line,
    ]
    if duration is not None:
        lines.append(f"Duration: {format_duration(duration)}")
    if bytes_transferred:
        lines.append(f"Transferred: {format_bytes(bytes_transferred)}")
    lines.append(f"Host: {socket.gethostname()}")
    if log_file:
        lines.append(f"Log: {log_file}")
    return summary, "\n".join(lines), f"[{APP_NAME}] {summary}"


def _deliver(desktop, email, summary, body, subject, result, email_cfg, session_log_file):
    if desktop:
        send_desktop_notification(
            summary,
            body,
            icon=_RESULT_ICONS.get(result, "dialog-information"),
            urgency=_RESULT_URGENCY.get(result, "normal"),
            session_log_file=session_log_file,
        )
    if email:
        send_email(subject, body, email_cfg, session_log_file=session_log_file)


def notify_run_finished(
    result,
    name,
    run_type,
    rc,
    duration=None,
    bytes_transferred=0,
    log_file=None,
    session_log_file=None,
    config=None,
):
    """Dispatch notifications for a finished run. Never raises.

    This is the single entry point for both hook sites (profile_runner and
    BackupRunner). *result* is "success", "failed", or "cancelled";
    *run_type* is the raw tab/history type string. On the GUI main thread
    the actual delivery is handed to a daemon thread so slow SMTP or a
    hung notification daemon cannot freeze the interface.
    """
    try:
        if config is None:
            config = load_config()
        notifications_cfg = get_notifications_config(config)
        run_type = normalize_run_type(run_type)
        desktop = _channel_fires(notifications_cfg["desktop"], result, run_type)
        email = _channel_fires(notifications_cfg["email"], result, run_type)
        if not desktop and not email:
            return
        summary, body, subject = _build_messages(
            result, name, run_type, rc, duration, bytes_transferred, log_file
        )
        _run_maybe_async(
            lambda: _deliver(
                desktop,
                email,
                summary,
                body,
                subject,
                result,
                notifications_cfg["email"],
                session_log_file,
            )
        )
    except Exception as exc:
        _log(f"WARN: Notification dispatch failed: {exc}", session_log_file)


def send_desktop_test(on_done=None, session_log_file=None):
    """Deliver a test desktop bubble (used by the Notifications dialog)."""
    _run_maybe_async(
        lambda: send_desktop_notification(
            f"{APP_NAME} test notification",
            "Desktop notifications are working.",
            session_log_file=session_log_file,
        ),
        on_done=on_done,
    )


def send_email_test(config=None, password=None, on_done=None, session_log_file=None):
    """Send a test email using the given settings (used by the dialog).

    *password* lets the dialog test its unsaved entry; when None the stored
    credentials file is used.
    """
    if config is None:
        config = load_config()
    email_cfg = get_notifications_config(config)["email"]
    if password is not None:
        email_cfg = dict(email_cfg)
        email_cfg["smtp_password"] = password
    _run_maybe_async(
        lambda: send_email(
            f"[{APP_NAME}] test email",
            f"Email notifications are working.\nHost: {socket.gethostname()}",
            email_cfg,
            session_log_file=session_log_file,
        ),
        on_done=on_done,
    )
