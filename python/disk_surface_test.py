"""Disk surface tester — SMART self-test orchestration for HDDs.

A surface test is a SMART self-test driven by the drive firmware:
`smartctl -t short|long` starts it and returns immediately, the test keeps
running on the disk regardless of GUI state (so it survives GUI restarts),
`smartctl -l selftest` reports live progress, and `smartctl -X` aborts it.
This module holds the state machine, the JSON state file, the cell-text
formatting for the Disk Inventory, and the start/cancel dialog. The smartctl
subprocess wrappers live in `disk_repository.py`.
"""

import json
import os
from contextlib import nullcontext
from datetime import datetime, timedelta

import gi

gi.require_version("Gtk", "3.0")
from disk_repository import classify_selftest_status
from file_locking import surface_state_lock_read, surface_state_lock_write
from gi.repository import Gtk
from gui_helpers import bold_label, create_dialog, show_error_dialog
from logging_config import log_msg
from paths import get_surface_test_state_path

SURFACE_TEST_STATE_PATH = get_surface_test_state_path()

# Dialog response ids (outside Gtk.ResponseType's range).
_RESPONSE_CANCEL_TEST = 1201

_STATUS_LABELS = {
    "passed": "Passed",
    "failed": "Failed",
    "aborted": "Aborted",
    "canceled": "Canceled",
}


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def load_surface_test_state(locked: bool = True) -> dict:
    """Load surface-test state from disk.

    Returns {"tests": {path: entry}}. Missing, unreadable, or malformed files
    yield an empty state. When *locked* is False the caller already holds the
    surface-state lock.
    """
    defaults = {"tests": {}}
    if not os.path.exists(SURFACE_TEST_STATE_PATH):
        return dict(defaults)
    lock_ctx = surface_state_lock_read() if locked else nullcontext()
    try:
        with lock_ctx, open(SURFACE_TEST_STATE_PATH, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("tests"), dict):
            return dict(defaults)
        return data
    except (json.JSONDecodeError, OSError) as e:
        log_msg(f"WARN: Could not load surface test state: {e}")
        return dict(defaults)


def save_surface_test_state(state, locked: bool = True) -> None:
    """Persist surface-test state to disk.

    When *locked* is False the caller already holds the surface-state lock.
    """
    os.makedirs(os.path.dirname(SURFACE_TEST_STATE_PATH), exist_ok=True)
    lock_ctx = surface_state_lock_write() if locked else nullcontext()
    try:
        with lock_ctx, open(SURFACE_TEST_STATE_PATH, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        log_msg(f"WARN: Could not save surface test state: {e}")


def build_entry(disk, mode: str, estimated_minutes, now: datetime) -> dict:
    """Create a fresh "running" state entry for *disk*."""
    return {
        "status": "running",
        "mode": mode,
        "model": getattr(disk, "model", "") or "",
        "started_at": now.isoformat(),
        "estimated_minutes": estimated_minutes if isinstance(estimated_minutes, int) else None,
        "progress_percent": 0,
        "eta": None,
        "result": None,
        "finished_at": None,
    }


def update_entry_from_poll(entry: dict, poll: dict, now: datetime) -> bool:
    """Advance *entry* from a poll result.

    Running entries gain progress/ETA while the test is in progress and are
    finalized (passed/failed/aborted) when the self-test log shows completion
    or no in-progress test. Returns True when the entry changed.
    """
    if entry.get("status") != "running":
        return False
    if poll.get("running"):
        remaining = poll.get("remaining_percent")
        if isinstance(remaining, bool) or not isinstance(remaining, (int, float)):
            return False
        entry["progress_percent"] = 100 - int(remaining)
        est = entry.get("estimated_minutes")
        if isinstance(est, int) and est > 0:
            eta = now + timedelta(minutes=est * remaining / 100.0)
            entry["eta"] = eta.isoformat()
        return True
    outcome = classify_selftest_status(poll.get("status_text"))
    entry["status"] = outcome
    entry["result"] = poll.get("status_text")
    entry["finished_at"] = now.isoformat()
    entry["eta"] = None
    if outcome == "passed":
        entry["progress_percent"] = 100
    return True


def update_entries_from_polls(state: dict, poll_fn, now: datetime) -> int:
    """Poll every running entry via *poll_fn*(path) and finalize finished ones.

    Returns the number of entries that changed.
    """
    changed = 0
    for path, entry in state.get("tests", {}).items():
        if entry.get("status") != "running":
            continue
        try:
            poll = poll_fn(path)
        except Exception as exc:  # pragma: no cover - defensive
            log_msg(f"WARN: Could not poll surface test on {path}: {exc}")
            continue
        if not isinstance(poll, dict):
            continue
        if update_entry_from_poll(entry, poll, now):
            changed += 1
    return changed


# ---------------------------------------------------------------------------
# Cell text formatting for the Disk Inventory
# ---------------------------------------------------------------------------


def format_minutes(minutes) -> str:
    """Format a minute count as '<1m', '45m', or '2h 05m'."""
    if not isinstance(minutes, (int, float)):
        return ""
    total = round(minutes)
    if total < 1:
        return "<1m"
    if total < 60:
        return f"{total}m"
    return f"{total // 60}h {total % 60:02d}m"


def surface_cell_text(entry: dict | None, now: datetime | None = None) -> str:
    """Short status text for the Disk Inventory 'Surface Test' cell."""
    if not entry:
        return "-"
    status = entry.get("status")
    if status == "running":
        progress = entry.get("progress_percent")
        prefix = f"{progress}%" if isinstance(progress, int) else "Running"
        eta = entry.get("eta")
        if eta:
            if now is None:
                now = datetime.now().astimezone()
            try:
                remaining = (datetime.fromisoformat(eta) - now).total_seconds() / 60.0
            except ValueError:
                remaining = None
            if remaining is not None and remaining > 0:
                return f"{prefix} ({format_minutes(remaining)})"
        return prefix
    return _STATUS_LABELS.get(status, "-")


# ---------------------------------------------------------------------------
# Start / cancel helpers
# ---------------------------------------------------------------------------


def start_surface_test(app, disk, mode: str) -> bool:
    """Start a self-test on *disk* and record it in the state file."""
    repo = app.ctx.disk_repository
    estimated = repo.estimate_test_minutes(disk.path, mode)
    if not repo.start_self_test(disk.path, mode):
        show_error_dialog(app, f"Could not start the surface test on {disk.path}.")
        return False
    state = load_surface_test_state()
    state["tests"][disk.path] = build_entry(disk, mode, estimated, datetime.now().astimezone())
    save_surface_test_state(state)
    log_msg(f"INFO: Surface test ({mode}) started on {disk.path}")
    return True


def cancel_surface_test(app, path: str) -> bool:
    """Abort the self-test on *path* and mark its state entry canceled."""
    repo = app.ctx.disk_repository
    if not repo.abort_self_test(path):
        show_error_dialog(app, f"Could not cancel the surface test on {path}.")
        return False
    state = load_surface_test_state()
    entry = state["tests"].get(path)
    if entry and entry.get("status") == "running":
        entry["status"] = "canceled"
        entry["finished_at"] = datetime.now().astimezone().isoformat()
        entry["eta"] = None
        save_surface_test_state(state)
    log_msg(f"INFO: Surface test canceled on {path}")
    return True


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


def _estimated_label(repo, path: str, mode: str) -> str:
    minutes = repo.estimate_test_minutes(path, mode)
    return format_minutes(minutes) if minutes is not None else "unknown"


def show_surface_test_dialog(app, disk, entry, repo):
    """Show the surface-test dialog for *disk*.

    When a test is already running on the disk, the dialog shows live status
    with a Cancel Test button. Otherwise it offers Fast (short) and Slow
    (long) options. Returns "short", "long", "abort", or None (closed).
    """
    parent = getattr(app, "window", None)
    if entry and entry.get("status") == "running":
        dialog = create_dialog(
            f"Surface Test on {disk.path}",
            parent,
            [("Close", Gtk.ResponseType.CLOSE), ("Cancel Test", _RESPONSE_CANCEL_TEST)],
        )
        content = dialog.get_content_area()
        status = Gtk.Label(
            label=(
                f"A {entry.get('mode', 'short')} surface test is running on {disk.path}.\n"
                f"Status: {surface_cell_text(entry)}"
            )
        )
        status.set_halign(Gtk.Align.START)
        content.pack_start(status, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        if response == _RESPONSE_CANCEL_TEST:
            return "abort"
        return None

    short_label = f"Fast — short self-test (~{_estimated_label(repo, disk.path, 'short')})"
    long_label = f"Slow — extended self-test (~{_estimated_label(repo, disk.path, 'long')})"
    dialog = create_dialog(
        f"Surface Test on {disk.path}",
        parent,
        [("Cancel", Gtk.ResponseType.CANCEL), ("Start", Gtk.ResponseType.OK)],
        default_response=Gtk.ResponseType.OK,
    )
    content = dialog.get_content_area()
    content.pack_start(bold_label("Test type"), False, False, 0)
    fast_radio = Gtk.RadioButton(label=short_label)
    slow_radio = Gtk.RadioButton(label=long_label)
    slow_radio.join_group(fast_radio)
    content.pack_start(fast_radio, False, False, 0)
    content.pack_start(slow_radio, False, False, 0)
    warning = Gtk.Label(
        label=(
            "The test runs in the drive firmware and keeps going if the GUI "
            "closes. It reads the whole disk surface and adds load, so I/O "
            "will slow while it runs. Safe on pooled disks."
        )
    )
    warning.set_line_wrap(True)
    warning.set_halign(Gtk.Align.START)
    content.pack_start(warning, False, False, 0)
    dialog.show_all()
    response = dialog.run()
    selected = "long" if slow_radio.get_active() else "short"
    dialog.destroy()
    if response == Gtk.ResponseType.OK:
        return selected
    return None
