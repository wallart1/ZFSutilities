"""
BackupRunner — async subprocess execution for backup operations.

Runs sequential steps (rsync pulls, zfs send/receive, post-backup) via
subprocess.Popen with non-blocking I/O integrated into the GTK main loop.
"""

import os
import pty
import re
import signal
import subprocess
import termios
import time
import tty

from datetime import datetime

from gi.repository import GLib

from backup_config import SESSION_LOG_DIR
from logging_config import (
    log_msg, set_session_log, restore_session_log, truncate_session_log,
)
from log_index import LogIndex
from backup_history import _parse_human_size, build_entry, add_history_entry
from command_builders import BashStep

RSYNC_LOG_DIR = "/var/log/zfsutilities"
RSYNC_LOG_FILE = os.path.join(RSYNC_LOG_DIR, "rsync-backup.log")
RSYNC_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB

# How often to check the session log size while a runner is active.
_SESSION_LOG_SIZE_CHECK_INTERVAL = 5  # seconds

# Regex: \[\s*[\d.]+\s*[kKMGTP]?i?B/s\]
# Purpose: Match pv progress output rate fields like [28.1MiB/s] or [ 148MiB/s].
# Matches: [28.1MiB/s], [0.00  B/s], [1.5GiB/s]
_PV_RATE_RE = re.compile(r'\[\s*[\d.]+\s*[kKMGTP]?i?B/s\]')

# Regex: received\s+(\S+)\s+stream\s+in\s+([\d.]+)\s+seconds
# Purpose: Match the final summary line emitted by `zfs receive` on stderr,
#          which reports actual bytes received and elapsed time.
# Group 1: Human-readable size  e.g. "312B", "1.23GiB", "5.00M"
# Group 2: Elapsed seconds      e.g. "0.25", "1234.56"
# Examples:
#   "received 312B stream in 0.25 seconds (1.20K/sec)" -> match
#   "received 1.23GiB stream in 45.67 seconds" -> match
#   "sending tank/data@snap" -> no match
_ZFS_RECEIVED_RE = re.compile(r'received\s+(\S+)\s+stream\s+in\s+([\d.]+)\s+seconds')


def _ensure_rsync_log_dir():
    os.makedirs(RSYNC_LOG_DIR, exist_ok=True)


def _truncate_rsync_log():
    _ensure_rsync_log_dir()
    try:
        if os.path.exists(RSYNC_LOG_FILE) and os.path.getsize(RSYNC_LOG_FILE) > RSYNC_LOG_MAX_BYTES:
            os.truncate(RSYNC_LOG_FILE, 0)
    except OSError:
        pass


class BackupRunner:
    """Runs a sequence of backup steps asynchronously."""

    def __init__(self, log_func, set_stdin_enabled_func, progress_func=None,
                 label="Backup", on_start=None):
        self.log = log_func
        self.set_stdin_enabled = set_stdin_enabled_func
        self.progress = progress_func
        self.label = label
        self.on_start = on_start
        self.steps = []
        self.current_step = 0
        self.process = None
        self.running = False
        self._stdout_source = None
        self._stderr_source = None
        self._on_complete = None
        self._rsync_log_fh = None
        self._current_pv_text = ""
        self._pty_master_fd = None
        self._session_log_file = None
        self._session_log_prev = None
        self._session_start_time = None
        self._finally_step = None
        self._finally_ran = False
        self._fatal_rc = None
        self._is_finally = False
        self._total_bytes_received = 0
        self._in_lock_wait = False
        self._last_log_size_check = 0.0

    def set_steps(self, steps):
        """Set the list of steps as BashStep objects."""
        self.steps = steps

    def set_finally_step(self, step):
        """Set a BashStep that runs even if a fatal step fails."""
        self._finally_step = step

    def prepare_session_log(self):
        """Create the session log file early so pre-run messages are captured.

        Idempotent: safe to call multiple times. Sets ZFSUTILITIES_LOG_FILE
        in the environment so that Python log_msg() writes to the session log.
        """
        if not self._session_log_file:
            self._create_session_log_file()
        if self._session_log_file and self._session_log_prev is None:
            self._session_log_prev = set_session_log(self._session_log_file)

    def _get_tab_type(self):
        """Map runner label to a clean tab type string."""
        label_lower = self.label.lower()
        if "offsite" in label_lower:
            return "offsite"
        elif "restore" in label_lower:
            return "restore"
        elif "prune" in label_lower or "retention" in label_lower:
            return "prune"
        return "backup"

    def _create_session_log_file(self):
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tab_type = self._get_tab_type()
        filename = f"{ts}_{tab_type}_gui.log"
        os.makedirs(SESSION_LOG_DIR, exist_ok=True)
        path = os.path.join(SESSION_LOG_DIR, filename)
        try:
            open(path, "a").close()
        except OSError:
            path = None
        self._session_log_file = path
        return path

    def _write_raw_line(self, line):
        """Append a raw subprocess line to the session log file."""
        if not self._session_log_file:
            return
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self._session_log_file, "a") as fh:
                fh.write(f"{ts}  {line}\n")
        except OSError:
            pass

    def _write_session_trailer(self, rc=None, cancelled=False,
                                bytes_transferred=0):
        if not self._session_log_file:
            return
        duration = time.time() - self._session_start_time if self._session_start_time else 0.0
        status = "cancelled" if cancelled else (f"rc={rc}" if rc is not None else "done")
        trailer = f"# END: {status}, duration={duration:.1f}s"
        if bytes_transferred:
            trailer += f", bytes={bytes_transferred}"
        try:
            with open(self._session_log_file, "a") as fh:
                fh.write(trailer + "\n")
        except OSError:
            pass

        # Persist final metadata so the Logs tab does not need to rescan.
        try:
            index = LogIndex.load()
            index.set_status(
                self._session_log_file,
                status="Cancelled" if cancelled else ("Done" if rc == 0 else "Failed"),
                duration=duration,
                bytes_transferred=bytes_transferred,
            )
            index.save()
        except Exception as e:
            log_msg(f"WARN: Could not update log index: {e}")

    def _maybe_truncate_session_log(self):
        """Truncate the session log if it has grown beyond the cap.

        Called periodically while a runner is active.  Bash subprocesses share
        the same log file, so this also caps output written by child shells.
        After truncation the persistent index entry is removed so the Logs tab
        rescans the smaller file.
        """
        if not self._session_log_file:
            return
        if truncate_session_log(self._session_log_file):
            log_msg("WARN: Session log exceeded size cap and was truncated")
            try:
                index = LogIndex.load()
                index.remove(self._session_log_file)
                index.save()
            except Exception as e:
                log_msg(f"WARN: Could not reset log index after truncation: {e}")

    def _log(self, msg):
        """Log to the GUI panel and session log file."""
        log_msg(msg)

    def start(self, on_complete=None):
        if self.running:
            return
        if self.on_start:
            self.on_start()
        self.running = True
        self.current_step = 0
        self._on_complete = on_complete
        self._session_start_time = time.time()
        self._finally_ran = False
        self._fatal_rc = None
        self._is_finally = False
        self._total_bytes_received = 0
        self._last_log_size_check = time.time()
        if not self._session_log_file:
            self._create_session_log_file()
        if self._session_log_file and self._session_log_prev is None:
            self._session_log_prev = set_session_log(self._session_log_file)
        _truncate_rsync_log()
        self._log(f"INFO: Starting {self.label.lower()}: {len(self.steps)} step(s)")
        self._update_progress(f"Starting {self.label.lower()}: {len(self.steps)} step(s)")
        self._run_next_step()

    def cancel(self):
        if self.process and self.process.poll() is None and self._in_lock_wait:
            self._log("INFO: Interrupting lock wait")
            self.process.send_signal(signal.SIGINT)
            return
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
        if (not self._is_finally and self.current_step < len(self.steps)):
            step = self.steps[self.current_step]
            if step.post_callback is not None:
                try:
                    step.post_callback()
                except Exception as exc:
                    self._log(f"WARN: Post-step callback failed during cancel: {exc}")
        self._cleanup_io()
        self._write_raw_line(f"INFO: {self.label} cancelled")
        self._log(f"INFO: {self.label} cancelled")
        self.set_stdin_enabled(False)
        if self.progress:
            self.progress(None, None)
        self._write_session_trailer(cancelled=True)
        if self._session_log_prev is not None:
            restore_session_log(self._session_log_prev)
            self._session_log_prev = None
        self._session_log_file = None
        self._session_start_time = None
        if self._on_complete:
            self._on_complete(cancelled=True)

    def send_input(self, text):
        if self._pty_master_fd is not None:
            try:
                os.write(self._pty_master_fd, (text + "\n").encode())
            except (BrokenPipeError, OSError):
                pass

    def _update_progress(self, text=None):
        if not self.progress:
            return
        total = len(self.steps)
        if self._finally_step:
            total += 1
        if total == 0:
            return
        fraction = self.current_step / total
        self.progress(fraction, text or "")

    def _step_progress_text(self, text):
        total = max(len(self.steps), self.current_step + 1)
        return f"[{self.current_step + 1}/{total}] {text}"

    def _spawn_process(self, desc, cmd, is_rsync):
        """Spawn a subprocess with PTY and wire up I/O watchers."""
        self._current_desc = desc
        self._current_pv_text = ""
        self._log(f"INFO: {self._step_progress_text(desc)}")
        self._update_progress(self._step_progress_text(desc))

        master_fd, slave_fd = pty.openpty()
        attrs = termios.tcgetattr(master_fd)
        attrs[3] &= ~termios.ECHO
        termios.tcsetattr(master_fd, termios.TCSANOW, attrs)
        self._pty_master_fd = master_fd

        try:
            child_env = os.environ.copy()
            if self._session_log_file:
                child_env["ZFSUTILITIES_LOG_INHERIT"] = "Y"
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=slave_fd,
                env=child_env,
            )
        except (OSError, FileNotFoundError) as e:
            os.close(master_fd)
            os.close(slave_fd)
            self._pty_master_fd = None
            self._log(f"WARN: Error launching: {e}")
            return False
        finally:
            os.close(slave_fd)

        self.set_stdin_enabled(True)

        os.set_blocking(self.process.stdout.fileno(), False)
        os.set_blocking(self.process.stderr.fileno(), False)

        if is_rsync:
            _ensure_rsync_log_dir()
            try:
                self._rsync_log_fh = open(RSYNC_LOG_FILE, "a")
                self._rsync_log_fh.write(f"\n{'='*60}\n{desc}\n{'='*60}\n")
            except OSError:
                self._rsync_log_fh = None

        out_cb = self._on_rsync_stdout if is_rsync else self._on_stdout
        err_cb = self._on_rsync_stderr if is_rsync else self._on_stderr
        self._stdout_source = GLib.io_add_watch(
            self.process.stdout.fileno(), GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP, out_cb,
        )
        self._stderr_source = GLib.io_add_watch(
            self.process.stderr.fileno(), GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP, err_cb,
        )
        GLib.timeout_add(250, self._check_process)
        return True

    def _run_next_step(self):
        if not self.running or self.current_step >= len(self.steps):
            if self._finally_step and not self._finally_ran:
                self._run_finally_step()
                return
            self._finish()
            return
        step = self.steps[self.current_step]
        if step.pre_callback is not None:
            try:
                step.pre_callback()
            except Exception as exc:
                self._log(f"WARN: Pre-step callback failed: {exc}")
        if not self._spawn_process(step.description, step.command, step.is_rsync):
            if step.post_callback is not None:
                try:
                    step.post_callback()
                except Exception as exc:
                    self._log(f"WARN: Post-step callback failed: {exc}")
            self.current_step += 1
            GLib.idle_add(self._run_next_step)

    def _run_finally_step(self):
        if self._finally_ran or not self._finally_step:
            self._finish(rc=self._fatal_rc if self._fatal_rc is not None else 0)
            return
        self._finally_ran = True
        self._is_finally = True
        self.current_step = len(self.steps)
        step = self._finally_step
        if not self._spawn_process(step.description, step.command, step.is_rsync):
            self._finish(rc=self._fatal_rc if self._fatal_rc is not None else 0)

    def _on_stdout(self, fd, condition):
        if condition & GLib.IOCondition.IN:
            try:
                data = os.read(fd, 8192)
                if data:
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        received_match = _ZFS_RECEIVED_RE.search(line)
                        if received_match:
                            self._total_bytes_received += _parse_human_size(
                                received_match.group(1)
                            )
                        if "Waiting for lock" in line:
                            self._in_lock_wait = True
                        elif "Lock is now available" in line or "Wait interrupted" in line:
                            self._in_lock_wait = False
                        self.log(line)
                        self._write_raw_line(line)
                    return True
            except OSError:
                pass
        self._stdout_source = None
        return False

    def _on_stderr(self, fd, condition):
        if condition & GLib.IOCondition.IN:
            try:
                data = os.read(fd, 8192)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    # Regex: [\r\n]+
                    # Purpose: Split raw byte stream into logical lines, handling mixed \r\n, \n, \r.
                    # Example: "line1\r\nline2\nline3" -> ["line1", "line2", "line3"]
                    for segment in re.split(r'[\r\n]+', text):
                        segment = segment.strip()
                        if not segment:
                            continue
                        if _PV_RATE_RE.search(segment):
                            self._current_pv_text = segment
                            self._update_progress(self._step_progress_text(segment))
                        else:
                            # Regex: INFO: Processing\s+(.+?)\.\s*$
                            # Purpose: Extract the dataset name from a log line announcing
                            #          the start of a new send/receive step.
                            # Group 1: dataset name  e.g. "threeamigos/proxmox"
                            # Example: "INFO: Processing threeamigos/proxmox. " -> match
                            #          "INFO: sending threeamigos/proxmox@snap" -> no match
                            processing_match = re.search(
                                r'INFO: Processing\s+(.+?)\.\s*$', segment
                            )
                            if processing_match:
                                self._current_pv_text = ""
                                self._update_progress(
                                    self._step_progress_text(processing_match.group(1))
                                )
                            received_match = _ZFS_RECEIVED_RE.search(segment)
                            if received_match:
                                self._total_bytes_received += _parse_human_size(
                                    received_match.group(1)
                                )
                            if "Waiting for lock" in segment:
                                self._in_lock_wait = True
                            elif "Lock is now available" in segment or "Wait interrupted" in segment:
                                self._in_lock_wait = False
                            self.log(segment)
                            self._write_raw_line(segment)
                    return True
            except OSError:
                pass
        self._stderr_source = None
        return False

    def _on_rsync_stdout(self, fd, condition):
        if condition & GLib.IOCondition.IN:
            try:
                data = os.read(fd, 8192)
                if data and self._rsync_log_fh:
                    self._rsync_log_fh.write(data.decode("utf-8", errors="replace"))
                    self._rsync_log_fh.flush()
                    return True
            except OSError:
                pass
        self._stdout_source = None
        return False

    def _on_rsync_stderr(self, fd, condition):
        if condition & GLib.IOCondition.IN:
            try:
                data = os.read(fd, 8192)
                if data:
                    desc = getattr(self, '_current_desc', 'rsync')
                    for line in data.decode("utf-8", errors="replace").splitlines():
                        if line.strip():
                            formatted = f"{desc}: {line}"
                            self.log(formatted)
                            self._write_raw_line(formatted)
                    return True
            except OSError:
                pass
        self._stderr_source = None
        return False

    def _check_process(self):
        if self.process is None:
            return False
        now = time.time()
        if now - self._last_log_size_check >= _SESSION_LOG_SIZE_CHECK_INTERVAL:
            self._last_log_size_check = now
            self._maybe_truncate_session_log()
        rc = self.process.poll()
        if rc is not None:
            self._drain_remaining()

            if not self._is_finally and self.current_step < len(self.steps):
                step = self.steps[self.current_step]
                if step.post_callback is not None:
                    try:
                        step.post_callback()
                    except Exception as exc:
                        self._log(f"WARN: Post-step callback failed: {exc}")

            if getattr(self, '_is_finally', False):
                if rc != 0:
                    self._log(f"WARN: Post-backup script exited with rc={rc}")
                self._cleanup_io()
                self.set_stdin_enabled(False)
                self._finish(rc=self._fatal_rc if self._fatal_rc is not None else 0)
                return False

            step = self.steps[self.current_step]
            if step.is_rsync:
                desc = step.description
                self._log(f"INFO: {desc} ... done (rc={rc})")
                self._log(f"INFO: Rsync log: {RSYNC_LOG_FILE}")
                if self._rsync_log_fh:
                    self._rsync_log_fh.close()
                    self._rsync_log_fh = None
            if rc != 0:
                self._log(f"WARN: Step exited with rc={rc}")
                if rc == 9:
                    self._log(f"INFO: {self.label} aborted by user")
                    self._cleanup_io()
                    self.set_stdin_enabled(False)
                    self._write_session_trailer(rc=9)
                    if self._session_log_prev is not None:
                        restore_session_log(self._session_log_prev)
                        self._session_log_prev = None
                    self._session_log_file = None
                    self._session_start_time = None
                    self.running = False
                    if self.progress:
                        self.progress(None, None)
                    if self._on_complete:
                        self._on_complete(cancelled=True)
                    return False
                if step.fatal:
                    self._log(f"FATAL: Aborting {self.label.lower()} because pre-backup command failed")
                    self._cleanup_io()
                    self.set_stdin_enabled(False)
                    if self._finally_step and not self._finally_ran:
                        self._fatal_rc = rc
                        GLib.idle_add(self._run_finally_step)
                        return False
                    self._finish(rc=rc)
                    return False
            self._cleanup_io()
            self.set_stdin_enabled(False)
            self.current_step += 1
            GLib.idle_add(self._run_next_step)
            return False
        return True

    def _drain_remaining(self):
        if self.process is None:
            return
        is_rsync = (
            self.steps[self.current_step].is_rsync
            if self.current_step < len(self.steps)
            else False
        )
        for pipe, is_err in [(self.process.stdout, False), (self.process.stderr, True)]:
            if pipe is None or pipe.closed:
                continue
            try:
                while True:
                    data = os.read(pipe.fileno(), 8192)
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    if is_rsync and not is_err:
                        if self._rsync_log_fh:
                            self._rsync_log_fh.write(text)
                    else:
                        for line in text.splitlines():
                            line = line.strip()
                            if line and not _PV_RATE_RE.search(line):
                                received_match = _ZFS_RECEIVED_RE.search(line)
                                if received_match:
                                    self._total_bytes_received += _parse_human_size(
                                        received_match.group(1)
                                    )
                                self.log(line)
                                self._write_raw_line(line)
            except (OSError, ValueError):
                pass

    def _cleanup_io(self):
        if self._stdout_source is not None:
            GLib.source_remove(self._stdout_source)
            self._stdout_source = None
        if self._stderr_source is not None:
            GLib.source_remove(self._stderr_source)
            self._stderr_source = None
        if self._pty_master_fd is not None:
            try:
                os.close(self._pty_master_fd)
            except OSError:
                pass
            self._pty_master_fd = None
        if self.process:
            for pipe in (self.process.stdout, self.process.stderr):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def _finish(self, rc=0):
        self.running = False
        self.set_stdin_enabled(False)
        if self.progress:
            self.progress(1.0, f"{self.label} complete")
        self._log(f"INFO: {self.label} complete")
        duration = time.time() - self._session_start_time if self._session_start_time else 0.0
        result = "success" if rc == 0 else "failed"
        entry = build_entry(
            timestamp=datetime.now().isoformat(),
            run_type=self._get_tab_type(),
            name=self.label,
            duration=duration,
            result=result,
            bytes_transferred=self._total_bytes_received,
            log_file=self._session_log_file,
        )
        add_history_entry(entry)
        self._write_session_trailer(rc=rc,
                                     bytes_transferred=self._total_bytes_received)
        if self._session_log_prev is not None:
            restore_session_log(self._session_log_prev)
            self._session_log_prev = None
        self._session_log_file = None
        self._session_start_time = None
        if self._on_complete:
            self._on_complete(cancelled=False)
