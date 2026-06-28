"""
Application entry point for the ZFS Utilities GUI.

Launches the GTK application with single-instance behaviour,
root privilege escalation via pkexec, and global CSS styling.
"""

import os
import re
import signal
import subprocess
import sys
import time

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio

from backup_config import log_msg

PID_FILE = "/run/zfsutilities/main.pid"


class ZFSUtilitiesApp(Gtk.Application):
    """Main application class."""

    def __init__(self, flags=Gio.ApplicationFlags.FLAGS_NONE):
        super().__init__(
            application_id="org.zfsutilities.gui",
            flags=flags,
        )
        self._main_window = None

    def do_activate(self):
        """Called when the application is activated.

        If a window already exists, bring it to the front (single-instance
        behaviour). Otherwise create and show a new window.
        """
        if self._main_window:
            self._main_window.present()
            gdk_window = self._main_window.get_window()
            if gdk_window:
                gdk_window.raise_()
            return

        # Global CSS — theme-adaptive status bar styling
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .status-bar-label {
                font-family: monospace;
                font-size: 15px;
            }
            .monospace {
                font-family: monospace;
            }
        """)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Lazy import to avoid circular dependency
        from zfsutilities_gui import ZFSUtilitiesWindow
        window = ZFSUtilitiesWindow(application=self)
        window.show_all()
        window._check_startup_config()
        self._main_window = window
        window.connect("destroy", self._on_window_destroy)

    def _on_window_destroy(self, window):
        """Clear the stored reference when the main window is closed."""
        if self._main_window:
            self._main_window._ui_state.flush()
        self._main_window = None


def _is_pid_alive(pid):
    """Return True if /proc/<pid> exists."""
    return os.path.isdir(f"/proc/{pid}")


def _get_process_exe(pid):
    """Return the executable path for a process, or None on error."""
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def _get_ppid(pid):
    """Return the parent PID from /proc/<pid>/stat, or None on error."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except OSError:
        return None
    end = data.find(b")")
    if end == -1:
        return None
    parts = data[end + 1:].split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def _pid_state(pid):
    """Return the one-character process state from /proc/<pid>/stat."""
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except OSError:
        return None
    end = data.find(b")")
    if end == -1:
        return None
    rest = data[end + 1:].lstrip()
    if not rest:
        return None
    return rest[:1].decode("ascii", "replace")


def _is_zfsutilities_process(pid):
    """Return True if pid is a ZFS Utilities GUI process.

    Matches:
    - the repo entry point (zfsutilities_gui.py)
    - the deployed wrapper entry point (main.py inside a zfsutilities path)
    - the desktop launcher wrapper script itself ("ZFSutilities GUI")
    """
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read()
    except OSError:
        return False
    lower = cmdline.lower()
    if b"zfsutilities_gui.py" in cmdline:
        return True
    # The deployed desktop launcher runs main.py directly.
    if b"main.py" in cmdline and b"zfsutilities" in lower:
        return True
    # The wrapper script is itself a Python process named "ZFSutilities GUI".
    if b"zfsutilities" in lower and b"gui" in lower:
        return True
    return False


def _pid_file_status(pid):
    """Return (is_stale, reason) for the PID stored in the PID file.

    The current process is never considered stale. A PID is stale when the
    process is dead, not a ZFS Utilities GUI process, or in a zombie/stopped
    state.
    """
    if pid is None:
        return False, None
    if pid == os.getpid():
        return False, None
    if not _is_pid_alive(pid):
        return True, "process is not running"
    if not _is_zfsutilities_process(pid):
        return True, "process is not a ZFS Utilities GUI instance"
    state = _pid_state(pid)
    if state in ("Z", "T"):
        return True, f"process state is {state}"
    return False, None


def _terminate_process(pid, timeout=5.0, sleep_fn=None):
    """Send SIGTERM, wait, then SIGKILL if necessary. Return True if gone."""
    if sleep_fn is None:
        sleep_fn = time.sleep
    if not _is_pid_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except OSError:
        pass

    waited = 0.0
    interval = 0.1
    while _is_pid_alive(pid) and waited < timeout:
        sleep_fn(interval)
        waited += interval

    if _is_pid_alive(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return True
        except OSError:
            pass
        sleep_fn(0.1)

    return not _is_pid_alive(pid)


def _show_wait_dialog(text):
    """Create and show a modal, no-button wait dialog."""
    dialog = Gtk.MessageDialog(
        transient_for=None,
        flags=Gtk.DialogFlags.MODAL,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.NONE,
        text=text,
    )
    dialog.set_title("ZFS Utilities")
    dialog.set_deletable(False)
    dialog.show_all()
    _pump_events_for(0.05)
    return dialog


def _pump_events_for(duration):
    """Run GTK main-loop iterations for *duration* seconds."""
    deadline = time.time() + duration
    while time.time() < deadline:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.01)


def _terminate_with_wait(pid, timeout=5.0):
    """Terminate pid while showing and updating a transient wait dialog."""
    wait = _show_wait_dialog(
        "Please wait: closing the previous ZFS Utilities window..."
    )
    try:
        _terminate_process(pid, timeout=timeout, sleep_fn=_pump_events_for)
    finally:
        wait.destroy()


def _find_matching_pids(exclude_pid=None):
    """Find root-owned python processes running the GUI module.

    Excludes the given PID and any of its ancestors so a launcher shell is not
    killed when replacing the running GUI.
    """
    pids = []
    try:
        entries = list(os.scandir("/proc"))
    except OSError:
        return pids

    ancestors = set()
    current = exclude_pid
    while current is not None:
        if current in ancestors:
            break
        ancestors.add(current)
        next_ppid = _get_ppid(current)
        if next_ppid == current:
            break
        current = next_ppid

    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == exclude_pid or pid in ancestors:
            continue
        try:
            if entry.stat().st_uid != 0:
                continue
        except OSError:
            continue
        exe = _get_process_exe(pid)
        if not exe or not os.path.basename(exe).startswith("python"):
            continue
        if _is_zfsutilities_process(pid):
            pids.append(pid)
    return pids


def _get_display_env():
    """Return an environment dict usable by X11 helper tools.

    Preserves the current environment, ensures DISPLAY defaults to :0, and
    attempts to locate a usable Xauthority file when one is not already set.
    """
    env = os.environ.copy()
    if not env.get("DISPLAY"):
        env["DISPLAY"] = ":0"
    if not env.get("XAUTHORITY"):
        sudo_user = env.get("SUDO_USER")
        candidates = []
        if sudo_user:
            candidates.append(f"/home/{sudo_user}/.Xauthority")
        candidates.extend([
            os.path.expanduser("~/.Xauthority"),
            "/root/.Xauthority",
        ])
        for path in candidates:
            if os.path.isfile(path):
                env["XAUTHORITY"] = path
                break
    return env


def _get_x11_windows_for_pid(pid):
    """Return a list of X11 window IDs belonging to pid, or an empty list."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--all", "--pid", str(pid)],
            capture_output=True,
            text=True,
            timeout=3,
            env=_get_display_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    windows = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            windows.append(line)
    return windows


def _is_window_visible(window_id):
    """Return True if an X11 window is mapped and large enough to be usable."""
    try:
        result = subprocess.run(
            ["xwininfo", "-id", str(window_id)],
            capture_output=True,
            text=True,
            timeout=3,
            env=_get_display_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    output = result.stdout
    if "Map State: IsViewable" not in output:
        return False
    width_match = re.search(r"^\s*Width:\s*(\d+)", output, re.MULTILINE)
    height_match = re.search(r"^\s*Height:\s*(\d+)", output, re.MULTILINE)
    if not width_match or not height_match:
        return False
    try:
        width = int(width_match.group(1))
        height = int(height_match.group(1))
    except ValueError:
        return False
    return width * height >= 100


def _has_visible_window(pid):
    """Return True if the process has at least one visible X11 window."""
    for window_id in _get_x11_windows_for_pid(pid):
        if _is_window_visible(window_id):
            return True
    return False


def _process_age_seconds(pid):
    """Return how many seconds pid has been alive, or None if unknown."""
    try:
        return time.time() - os.stat(f"/proc/{pid}").st_ctime
    except OSError:
        return None


def _is_instance_stuck(pid):
    """Return True when pid is alive but has no usable window for a while.

    A freshly launched GUI may need a moment to map its window, so instances
    younger than 10 seconds are not considered stuck.
    """
    if not _is_pid_alive(pid):
        return False
    if _has_visible_window(pid):
        return False
    age = _process_age_seconds(pid)
    if age is not None and age < 10:
        return False
    return True


def _write_pid_file(pid):
    """Write the PID file, creating its parent directory if needed."""
    try:
        parent = os.path.dirname(PID_FILE)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(pid))
    except OSError as exc:
        log_msg(f"WARN: could not write PID file {PID_FILE}: {exc}")


def _remove_pid_file_if_ours(pid):
    """Remove the PID file only if it still contains our PID."""
    try:
        if not os.path.exists(PID_FILE):
            return
        with open(PID_FILE, "r") as f:
            current = int(f.read().strip())
        if current == pid:
            os.remove(PID_FILE)
    except (OSError, ValueError):
        pass


def _read_pid_file():
    """Return the integer PID from the PID file, or None."""
    try:
        if not os.path.exists(PID_FILE):
            return None
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def main():
    if os.geteuid() != 0:
        # Re-launch with pkexec, preserving the X11/Wayland display environment
        display = os.environ.get('DISPLAY', ':0')
        xauthority = os.environ.get('XAUTHORITY', '')
        wayland = os.environ.get('WAYLAND_DISPLAY', '')
        cmd = [
            'pkexec', 'env',
            f'DISPLAY={display}',
        ]
        if xauthority:
            cmd.append(f'XAUTHORITY={xauthority}')
        if wayland:
            cmd.append(f'WAYLAND_DISPLAY={wayland}')
        cmd.append(sys.executable)
        cmd.extend(sys.argv)
        os.execvp('pkexec', cmd)

    flags = Gio.ApplicationFlags.REPLACE
    pid = _read_pid_file()
    our_pid = os.getpid()

    if pid is not None and pid != our_pid:
        stale, reason = _pid_file_status(pid)
        if stale:
            log_msg(f"INFO: replacing stale GUI instance {pid} ({reason})")
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
        else:
            log_msg(f"INFO: replacing existing GUI instance {pid}")
            _terminate_with_wait(pid)
            try:
                os.remove(PID_FILE)
            except OSError:
                pass

    # Terminate any other running GUI instances that may still own the D-Bus
    # application ID.
    for matching_pid in _find_matching_pids(exclude_pid=our_pid):
        if matching_pid == pid:
            continue
        log_msg(f"INFO: terminating existing GUI instance {matching_pid}")
        _terminate_with_wait(matching_pid)

    app = None
    try:
        app = ZFSUtilitiesApp(flags=flags)
        app.register(cancellable=None)
        if app.get_is_remote():
            # A process we did not catch still owns the D-Bus application ID.
            # Terminate any matching processes that appeared after our first
            # scan and create a fresh application instance to retry once.
            log_msg(
                "INFO: another GUI instance is still registered; "
                "retrying after cleanup"
            )
            for matching_pid in _find_matching_pids(exclude_pid=our_pid):
                if matching_pid == pid:
                    continue
                log_msg(
                    f"INFO: terminating existing GUI instance {matching_pid}"
                )
                _terminate_with_wait(matching_pid)
            app = ZFSUtilitiesApp(flags=flags)
            app.register(cancellable=None)
            if app.get_is_remote():
                log_msg(
                    "WARN: another GUI instance is still registered; "
                    "startup aborted"
                )
                return
        _write_pid_file(our_pid)
        app.run(None)
    except Exception:
        import traceback
        error_log = "/tmp/zfsutilities_gui_error.log"
        with open(error_log, "w") as f:
            traceback.print_exc(file=f)
        raise
    finally:
        if app is not None and not app.get_is_remote():
            _remove_pid_file_if_ours(our_pid)


if __name__ == "__main__":
    main()
