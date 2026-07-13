"""
ZFS Scrub Manager — core logic for tracking and controlling pool scrubs.

Provides:
- Parsing of zpool status for scrub state/progress
- Subprocess wrappers for start / pause / resume / stop
- A persistent ScrubQueue that manages pending/active/paused/finished buckets
- Helpers for the pre-installed systemd scrub timers
"""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Set

from backup_config import log_msg
from file_locking import scrub_state_lock_read, scrub_state_lock_write
from zfs_repository import get_default_repository


# ---------------------------------------------------------------------------
# Scrub state enum + info dataclass
# ---------------------------------------------------------------------------

class ScrubState(Enum):
    NONE = "none"
    PENDING = "pending"
    SCANNING = "scanning"
    PAUSED = "paused"
    FINISHED = "finished"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


@dataclass
class ScrubInfo:
    state: ScrubState = ScrubState.UNKNOWN
    progress_percent: Optional[float] = None
    scan_line: str = ""
    last_scrub: str = ""
    errors: int = 0
    remaining_seconds: Optional[int] = None
    eta: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Regexes for zpool status parsing
# ---------------------------------------------------------------------------

_SCAN_NONE_RE = re.compile(r"scan:\s*none\s*requested", re.IGNORECASE)
_SCAN_PROGRESS_RE = re.compile(
    r"scan:\s*scrub\s+in\s+progress\s+since\s+(.+)$", re.MULTILINE
)
_SCAN_PAUSED_RE = re.compile(
    r"scan:\s*scrub\s+paused\s+since\s+(.+)$", re.MULTILINE
)
_SCAN_FINISHED_RE = re.compile(
    r"scan:\s*scrub\s+repaired\s+\S+\s+in\s+(.+?)\s+with\s+(\d+)\s+errors?\s+on\s+(.+)$",
    re.MULTILINE,
)
_SCAN_CANCELED_RE = re.compile(
    r"scan:\s*scrub\s+canceled\s+on\s+(.+)$", re.MULTILINE
)
_SCAN_PERCENT_RE = re.compile(r"(\d+\.?\d*)%\s+done")
_SCAN_RESILVER_RE = re.compile(
    r"scan:\s*resilvered\s+\S+\s+in\s+(.+?)\s+with\s+(\d+)\s+errors?\s+on\s+(.+)$",
    re.MULTILINE,
)
# Stale paused summary that can appear as a continuation line after a resume.
_STALE_PAUSED_RE = re.compile(r"^scrub\s+paused\b", re.IGNORECASE)
# Remaining time reported on an in-progress scrub, e.g.
#   "01:23:45 to go" or "1 days 01:23:45 to go"
_SCAN_REMAINING_RE = re.compile(
    r"(?:(\d+)\s+days?\s+)?(\d+):(\d{2}):(\d{2})\s+to\s+go",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Low-level zpool status parsing
# ---------------------------------------------------------------------------

def _run_zpool_status(pool_name: str, repo=None) -> str:
    """Return raw zpool status text or empty string on failure."""
    repo = repo or get_default_repository()
    return repo.pool_status(pool_name, timeout=15)


def parse_scrub_status(raw: str) -> ScrubInfo:
    """Parse zpool status text and return ScrubInfo."""
    info = ScrubInfo()
    if not raw:
        return info

    # Look for the scan line(s) — usually 1-3 lines under "scan:"
    lines = raw.splitlines()
    scan_lines = []
    in_scan = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("scan:"):
            in_scan = True
            scan_lines.append(stripped)
        elif in_scan:
            if stripped == "" or stripped.startswith("config:") or stripped.startswith("pool:"):
                break
            scan_lines.append(stripped)

    # Determine state before finalizing scan_line so we can drop stale
    # continuation lines that do not match the resolved state.
    if _SCAN_NONE_RE.search(raw):
        info.state = ScrubState.NONE
        info.scan_line = " ".join(scan_lines)
        return info

    m = _SCAN_PROGRESS_RE.search(raw)
    if m:
        info.state = ScrubState.SCANNING
        info.last_scrub = m.group(1).strip()
        info.progress_percent = _extract_percent(raw)
        info.remaining_seconds = _extract_remaining_seconds(raw)
        if info.remaining_seconds is not None:
            info.eta = datetime.now() + timedelta(seconds=info.remaining_seconds)
        scan_lines = [
            line for line in scan_lines
            if not _STALE_PAUSED_RE.match(line)
        ]
        info.scan_line = " ".join(scan_lines)
        return info

    m = _SCAN_PAUSED_RE.search(raw)
    if m:
        info.state = ScrubState.PAUSED
        info.last_scrub = m.group(1).strip()
        info.progress_percent = _extract_percent(raw)
        info.scan_line = " ".join(scan_lines)
        return info

    m = _SCAN_FINISHED_RE.search(raw)
    if m:
        info.state = ScrubState.FINISHED
        info.errors = int(m.group(2))
        info.last_scrub = m.group(3).strip()
        info.scan_line = " ".join(scan_lines)
        return info

    m = _SCAN_CANCELED_RE.search(raw)
    if m:
        info.state = ScrubState.CANCELED
        info.last_scrub = m.group(1).strip()
        info.scan_line = " ".join(scan_lines)
        return info

    m = _SCAN_RESILVER_RE.search(raw)
    if m:
        # Treat resilver similarly to a finished scrub for dashboard purposes
        info.state = ScrubState.FINISHED
        info.errors = int(m.group(2))
        info.last_scrub = m.group(3).strip()
        info.scan_line = " ".join(scan_lines)
        return info

    info.state = ScrubState.UNKNOWN
    info.scan_line = " ".join(scan_lines)
    return info


def _extract_percent(raw: str) -> Optional[float]:
    m = _SCAN_PERCENT_RE.search(raw)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def _extract_remaining_seconds(raw: str) -> Optional[int]:
    """Return seconds remaining from a 'zpool status' 'to go' line, or None."""
    m = _SCAN_REMAINING_RE.search(raw)
    if not m:
        return None
    days_str, hours_str, minutes_str, seconds_str = m.groups()
    try:
        days = int(days_str) if days_str else 0
        hours = int(hours_str)
        minutes = int(minutes_str)
        seconds = int(seconds_str)
        return (
            (days * 24 * 3600)
            + (hours * 3600)
            + (minutes * 60)
            + seconds
        )
    except (ValueError, TypeError):
        return None


def get_pool_scrub_info(pool_name: str, repo=None) -> ScrubInfo:
    """Return ScrubInfo for a single pool."""
    raw = _run_zpool_status(pool_name, repo=repo)
    return parse_scrub_status(raw)


def get_all_pool_scrub_states(repo=None) -> Dict[str, ScrubInfo]:
    """Return a dict mapping pool name -> ScrubInfo for all online pools."""
    repo = repo or get_default_repository()
    states: Dict[str, ScrubInfo] = {}
    try:
        for row in repo.list_pools():
            states[row.name] = get_pool_scrub_info(row.name, repo=repo)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        log_msg(f"WARN: Could not list pools for scrub status: {e}")
    return states


# ---------------------------------------------------------------------------
# Scrub control commands
# ---------------------------------------------------------------------------

# Scrub actions do not coordinate through the hierarchical dataset lock manager.
# A scrub is a pool-maintenance operation, not a dataset mutation, so it has no
# dependency on backup/restore/prune jobs.  Each action consults the live scrub
# state from zpool status and skips itself when the requested transition is
# invalid.  ZFS is the final authority; these checks just avoid noisy failures.


def _scrub_action_allowed(
    pool_name: str,
    allowed_states: Set[ScrubState],
    repo=None,
) -> bool:
    """Return True if the pool's current scrub state permits the action."""
    info = get_pool_scrub_info(pool_name, repo=repo)
    if info.state in allowed_states:
        return True
    allowed = ", ".join(sorted(s.value for s in allowed_states))
    log_msg(
        f"INFO: Skipping scrub action on '{pool_name}': "
        f"current state is {info.state.value}, allowed states are {allowed}"
    )
    return False


def start_scrub(pool_name: str, repo=None) -> bool:
    """Start a scrub. Returns True on success."""
    repo = repo or get_default_repository()
    if not _scrub_action_allowed(
        pool_name,
        {ScrubState.NONE, ScrubState.FINISHED, ScrubState.CANCELED, ScrubState.UNKNOWN},
        repo=repo,
    ):
        return False
    log_msg(f"INFO: Starting scrub on pool '{pool_name}'")
    try:
        if repo.start_scrub(pool_name, timeout=30):
            log_msg(f"INFO: Scrub started on '{pool_name}'")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log_msg(f"WARN: cannot start scrub on '{pool_name}': {exc}")
        return False
    log_msg(f"WARN: Failed to start scrub on '{pool_name}'")
    return False


def pause_scrub(pool_name: str, repo=None) -> bool:
    """Pause a scrub. Returns True on success."""
    repo = repo or get_default_repository()
    if not _scrub_action_allowed(
        pool_name,
        {ScrubState.SCANNING},
        repo=repo,
    ):
        return False
    log_msg(f"INFO: Pausing scrub on pool '{pool_name}'")
    try:
        if repo.pause_scrub(pool_name, timeout=30):
            log_msg(f"INFO: Scrub paused on '{pool_name}'")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log_msg(f"WARN: cannot pause scrub on '{pool_name}': {exc}")
        return False
    log_msg(f"WARN: Failed to pause scrub on '{pool_name}'")
    return False


def resume_scrub(pool_name: str, repo=None) -> bool:
    """Resume a scrub. Returns True on success."""
    repo = repo or get_default_repository()
    if not _scrub_action_allowed(
        pool_name,
        {ScrubState.PAUSED},
        repo=repo,
    ):
        return False
    log_msg(f"INFO: Resuming scrub on pool '{pool_name}'")
    try:
        if repo.resume_scrub(pool_name, timeout=30):
            log_msg(f"INFO: Scrub resumed on '{pool_name}'")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log_msg(f"WARN: cannot resume scrub on '{pool_name}': {exc}")
        return False
    log_msg(f"WARN: Failed to resume scrub on '{pool_name}'")
    return False


def stop_scrub(pool_name: str, repo=None) -> bool:
    """Stop a scrub. Returns True on success."""
    repo = repo or get_default_repository()
    if not _scrub_action_allowed(
        pool_name,
        {ScrubState.SCANNING, ScrubState.PAUSED},
        repo=repo,
    ):
        return False
    log_msg(f"INFO: Stopping scrub on pool '{pool_name}'")
    try:
        if repo.stop_scrub(pool_name, timeout=30):
            log_msg(f"INFO: Scrub stopped on '{pool_name}'")
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        log_msg(f"WARN: cannot stop scrub on '{pool_name}': {exc}")
        return False
    log_msg(f"WARN: Failed to stop scrub on '{pool_name}'")
    return False


# ---------------------------------------------------------------------------
# Backup / restore scrub coordination
# ---------------------------------------------------------------------------


def _pool_from_dataset(dataset: str) -> Optional[str]:
    """Return the pool name for a local ZFS dataset path.

    Remote endpoints (host:path) and non-dataset paths are ignored.
    """
    if not dataset:
        return None
    if ":" in dataset and not dataset.startswith("/"):
        return None
    name = dataset.split("/", 1)[0].strip()
    return name or None


def pause_scrubs_for_pools(pool_names: List[str], repo=None,
                           dry_run: bool = False,
                           log_func: Optional[Callable] = None) -> List[str]:
    """Pause any running scrubs on *pool_names* and mark them user-paused.

    Returns the list of pools whose scrubs were actually paused (only pools
    that were scanning are paused). In dry-run mode no system state is changed
    and the returned list contains the pools that would have been paused.

    If *log_func* is provided, it is used instead of the global ``log_msg``
    for all messages produced by this call.
    """
    repo = repo or get_default_repository()
    _log = log_func or log_msg
    names = [n for n in pool_names if n]
    if not names:
        return []

    states = get_all_pool_scrub_states(repo=repo)

    if not dry_run:
        queue = ScrubQueue()
        # Only mark pools as user-paused if they have a live scrub or are
        # already queued to start. Finished/unknown pools have nothing to
        # pause and should not be logged as paused.
        to_pause_in_queue = []
        for name in names:
            info = states.get(name)
            if info and info.state == ScrubState.SCANNING:
                to_pause_in_queue.append(name)
            elif name in queue.pending:
                to_pause_in_queue.append(name)
        if to_pause_in_queue:
            for name in to_pause_in_queue:
                queue.active.discard(name)
                queue.pending.discard(name)
                queue.paused.add(name)
                queue.paused_by_user.add(name)
            _log(
                f"INFO: Pools paused: {', '.join(sorted(to_pause_in_queue))}"
            )
            queue._save()

    paused = []
    for name in names:
        info = states.get(name)
        if info is None:
            _log(f"DEBUG: Pool '{name}' is not online; skipping scrub pause")
            continue
        if info.state != ScrubState.SCANNING:
            _log(
                f"DEBUG: Scrub on '{name}' is {info.state.value}; "
                f"not pausing"
            )
            continue
        if dry_run:
            _log(f"INFO: Dry-run: would pause scrub on '{name}'")
            paused.append(name)
            continue
        _log(f"INFO: Pausing scrub on '{name}'")
        try:
            if repo.pause_scrub(name, timeout=30):
                _log(f"INFO: Scrub paused on '{name}'")
                paused.append(name)
            else:
                _log(f"WARN: Failed to pause scrub on '{name}'")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            _log(f"WARN: cannot pause scrub on '{name}': {exc}")
    return paused


def resume_scrubs_for_pools(pool_names: List[str], repo=None,
                            dry_run: bool = False,
                            log_func: Optional[Callable] = None) -> None:
    """Resume scrubs that were paused by pause_scrubs_for_pools().

    Pools that were not actually paused (e.g., already finished or paused)
    are left alone. In dry-run mode no system state is changed.

    If *log_func* is provided, it is used instead of the global ``log_msg``
    for all messages produced by this call.
    """
    repo = repo or get_default_repository()
    _log = log_func or log_msg
    names = [n for n in pool_names if n]
    if not names:
        return

    if not dry_run:
        queue = ScrubQueue()
        queue.resume_pools(names)
        for name in names:
            queue.paused_by_user.discard(name)
        queue._save()

    states = get_all_pool_scrub_states(repo=repo)
    for name in names:
        info = states.get(name)
        if info is None:
            _log(f"DEBUG: Pool '{name}' is not online; skipping scrub resume")
            continue
        if info.state != ScrubState.PAUSED:
            _log(
                f"DEBUG: Scrub on '{name}' is {info.state.value}; "
                f"not resuming"
            )
            continue
        if dry_run:
            _log(f"INFO: Dry-run: would resume scrub on '{name}'")
            continue
        _log(f"INFO: Resuming scrub on '{name}'")
        try:
            if repo.resume_scrub(name, timeout=30):
                _log(f"INFO: Scrub resumed on '{name}'")
            else:
                _log(f"WARN: Failed to resume scrub on '{name}'")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            _log(f"WARN: cannot resume scrub on '{name}': {exc}")


def attach_step_scrub_callbacks(step, source: str, dest: str,
                                enabled: bool, dry_run: bool = False,
                                log_func: Optional[Callable] = None) -> None:
    """Attach pre/post callbacks to a BashStep to pause/resume scrubs.

    The callbacks pause scrubs on the pools referenced by *source* and *dest*
    immediately before the step runs and resume them after the step finishes.
    If *enabled* is False, or if no local pools are found, the callbacks are
    left unset.

    If *log_func* is provided, scrub pause/resume messages are routed through
    it instead of the global ``log_msg``.
    """
    if not enabled:
        return
    pools = sorted(
        {p for p in (_pool_from_dataset(source), _pool_from_dataset(dest)) if p}
    )
    if not pools:
        return

    paused_pools: List[str] = []

    def pre_callback():
        nonlocal paused_pools
        paused_pools = pause_scrubs_for_pools(
            pools, dry_run=dry_run, log_func=log_func
        )

    def post_callback():
        nonlocal paused_pools
        if paused_pools:
            resume_scrubs_for_pools(paused_pools, dry_run=dry_run,
                                    log_func=log_func)
            paused_pools = []

    step.pre_callback = pre_callback
    step.post_callback = post_callback


# ---------------------------------------------------------------------------
# Persistent state helpers
# ---------------------------------------------------------------------------

SCRUB_STATE_PATH = "/root/.config/zfsutilities/scrub_state.json"


def _ensure_state_dir():
    os.makedirs(os.path.dirname(SCRUB_STATE_PATH), exist_ok=True)


def load_scrub_state() -> dict:
    """Load scrub queue state from disk. Returns dict with empty defaults if missing."""
    defaults = {
        "pending": [],
        "active": [],
        "paused": [],
        "finished": [],
        "target": 1,
    }
    if not os.path.exists(SCRUB_STATE_PATH):
        return dict(defaults)
    try:
        with scrub_state_lock_read():
            with open(SCRUB_STATE_PATH, "r") as f:
                data = json.load(f)
        for key in defaults:
            if key not in data:
                data[key] = defaults[key]
        # Ensure lists
        for key in ("pending", "active", "paused", "finished"):
            if not isinstance(data[key], list):
                data[key] = []
        return data
    except (json.JSONDecodeError, OSError) as e:
        log_msg(f"WARN: Could not load scrub state: {e}")
        return dict(defaults)


def save_scrub_state(state: dict) -> None:
    """Persist scrub queue state to disk."""
    _ensure_state_dir()
    try:
        with scrub_state_lock_write():
            with open(SCRUB_STATE_PATH, "w") as f:
                json.dump(state, f, indent=2)
    except OSError as e:
        log_msg(f"WARN: Could not save scrub state: {e}")


# ---------------------------------------------------------------------------
# ScrubQueue — manages pending / active / paused / finished buckets
# ---------------------------------------------------------------------------

class ScrubQueue:
    """Manages a queue of pool scrubs with a concurrency target.

    The queue is persisted to disk so it survives GUI restarts.
    """

    # -- Persistence --

    def _load(self):
        data = load_scrub_state()
        self.pending = set(data.get("pending", []))
        self.active = set(data.get("active", []))
        self.paused = set(data.get("paused", []))
        self.finished = set(data.get("finished", []))
        self.paused_by_user = set(data.get("paused_by_user", []))
        self.target = max(1, int(data.get("target", 1)))

    def _save(self):
        save_scrub_state({
            "pending": sorted(self.pending),
            "active": sorted(self.active),
            "paused": sorted(self.paused),
            "finished": sorted(self.finished),
            "paused_by_user": sorted(self.paused_by_user),
            "target": self.target,
        })

    # -- Public API --

    def set_target(self, n: int):
        """Set the desired number of simultaneous scrubs."""
        old = self.target
        self.target = max(1, n)
        if self.target != old:
            log_msg(f"INFO: Scrub target changed from {old} to {self.target}")
            self._save()

    def add_pending(self, pool_names: List[str]):
        """Add pools to the pending queue.

        Active pools are left alone. Pools that are currently paused are moved
        back to pending (re-queued) so Start Scrub can restart them.
        """
        added = []
        for name in pool_names:
            if name in self.active:
                continue
            if name in self.paused:
                self.paused.discard(name)
                self.paused_by_user.discard(name)
                self.pending.add(name)
                added.append(name)
            elif name not in self.pending:
                self.pending.add(name)
                added.append(name)
        if added:
            log_msg(f"INFO: Pools added to scrub queue: {', '.join(added)}")
            self._save()

    def remove_pools(self, pool_names: List[str]):
        """Remove pools from all buckets."""
        names = set(pool_names)
        for bucket in (self.pending, self.active, self.paused, self.finished):
            bucket -= names
        self.paused_by_user -= names
        if names:
            log_msg(f"INFO: Pools removed from scrub queue: {', '.join(sorted(names))}")
            self._save()

    def pause_pools(self, pool_names: List[str]):
        """Move specified active/pending pools to paused (user-initiated)."""
        names = set(pool_names)
        to_pause = names & (self.active | self.pending)
        for name in to_pause:
            self.active.discard(name)
            self.pending.discard(name)
            self.paused.add(name)
            self.paused_by_user.add(name)
        if to_pause:
            log_msg(f"INFO: Pools paused: {', '.join(sorted(to_pause))}")
            self._save()

    def resume_pools(self, pool_names: List[str]):
        """Move specified paused pools to pending so tick() will restart them."""
        names = set(pool_names)
        to_resume = names & self.paused
        for name in to_resume:
            self.paused.discard(name)
            self.paused_by_user.discard(name)
            self.pending.add(name)
        if to_resume:
            log_msg(f"INFO: Pools resumed: {', '.join(sorted(to_resume))}")
            self._save()

    def tick(self, states: Dict[str, ScrubInfo]):
        """Reconcile queue against live zpool status and target.

        Call this on every refresh cycle.
        """
        # 1. Reconcile active / paused / finished against live states
        for pool_name in list(self.active):
            info = states.get(pool_name)
            if info is None:
                # Pool offline — drop from active
                self.active.discard(pool_name)
                continue
            if info.state == ScrubState.FINISHED:
                log_msg(f"INFO: Scrub finished on '{pool_name}'")
                self.active.discard(pool_name)
                self.finished.add(pool_name)
            elif info.state == ScrubState.CANCELED:
                log_msg(f"INFO: Scrub canceled on '{pool_name}'")
                self.active.discard(pool_name)
                self.finished.add(pool_name)
            elif info.state == ScrubState.PAUSED:
                # External pause detected
                self.active.discard(pool_name)
                self.paused.add(pool_name)
            elif info.state == ScrubState.NONE:
                # Scrub finished or was reset
                started_at = self._start_times.get(pool_name)
                if started_at and time.time() - started_at < 30:
                    continue  # Grace period — don't transition yet
                log_msg(f"INFO: Scrub completed on '{pool_name}'")
                self.active.discard(pool_name)
                self.finished.add(pool_name)

        for pool_name in list(self.paused):
            info = states.get(pool_name)
            if info is None:
                self.paused.discard(pool_name)
                self.paused_by_user.discard(pool_name)
                continue
            if info.state == ScrubState.FINISHED:
                log_msg(f"INFO: Paused scrub finished on '{pool_name}'")
                self.paused.discard(pool_name)
                self.paused_by_user.discard(pool_name)
                self.finished.add(pool_name)
            elif info.state == ScrubState.CANCELED:
                log_msg(f"INFO: Paused scrub canceled on '{pool_name}'")
                self.paused.discard(pool_name)
                self.paused_by_user.discard(pool_name)
                self.finished.add(pool_name)
            elif info.state == ScrubState.NONE:
                self.paused.discard(pool_name)
                self.paused_by_user.discard(pool_name)
                self.finished.add(pool_name)
            elif info.state == ScrubState.SCANNING:
                # Externally resumed
                self.paused.discard(pool_name)
                self.paused_by_user.discard(pool_name)
                self.active.add(pool_name)

        for pool_name in list(self.pending):
            info = states.get(pool_name)
            if info is None:
                # Pool offline — keep pending; will start when back online
                continue
            if info.state == ScrubState.SCANNING:
                # Externally started while pending
                self.pending.discard(pool_name)
                self.active.add(pool_name)
                log_msg(f"INFO: External scrub detected on '{pool_name}'")

        # Detect externally-started scrubs on pools not yet in any bucket
        tracked = self.pending | self.active | self.paused | self.finished
        for pool_name, info in states.items():
            if pool_name in tracked:
                continue
            if info.state == ScrubState.SCANNING:
                self.active.add(pool_name)
                log_msg(f"INFO: External scrub detected on '{pool_name}'")
            elif info.state == ScrubState.PAUSED:
                self.paused.add(pool_name)
            elif info.state in (ScrubState.FINISHED, ScrubState.CANCELED):
                self.finished.add(pool_name)

        # 2. Adjust active count toward target
        active_count = len(self.active)

        if active_count < self.target:
            # Start pending first, then resume paused
            for candidate in sorted(self.pending):
                if len(self.active) >= self.target:
                    break
                info = states.get(candidate)
                if info is None:
                    # Pool offline — leave in pending
                    continue
                if info.state == ScrubState.SCANNING:
                    # Already running externally
                    self.pending.discard(candidate)
                    self.active.add(candidate)
                elif info.state == ScrubState.PAUSED:
                    # Pool is queued but still live-paused. Resume it only when
                    # a scrub slot is available; do not preempt active scrubs.
                    self.pending.discard(candidate)
                    if resume_scrub(candidate):
                        self.active.add(candidate)
                    else:
                        self.pending.add(candidate)
                        break
                elif info.state in (
                    ScrubState.NONE,
                    ScrubState.FINISHED,
                    ScrubState.CANCELED,
                    ScrubState.UNKNOWN,
                ):
                    # No live scrub (or only a prior finished/canceled scrub).
                    # Start a fresh scrub for this queued request.
                    self.pending.discard(candidate)
                    if start_scrub(candidate):
                        self.active.add(candidate)
                    else:
                        # Failed to start — put back in pending for retry
                        self.pending.add(candidate)
                        break
                else:
                    # Unexpected state — leave in pending
                    continue

            while len(self.active) < self.target and self.paused:
                # Only auto-resume pools paused by target management; user-paused
                # pools stay paused until the user explicitly resumes them.
                candidate = None
                for name in sorted(self.paused):
                    if name not in self.paused_by_user:
                        candidate = name
                        break
                if candidate is None:
                    break
                self.paused.discard(candidate)
                self.paused_by_user.discard(candidate)
                info = states.get(candidate)
                if info and info.state == ScrubState.PAUSED:
                    if resume_scrub(candidate):
                        self.active.add(candidate)
                    else:
                        self.paused.add(candidate)
                        break
                elif info and info.state == ScrubState.SCANNING:
                    self.active.add(candidate)
                else:
                    self.active.add(candidate)

        elif active_count > self.target:
            # Pause newest active scrubs
            to_pause = sorted(self.active)[self.target:]
            for candidate in to_pause:
                info = states.get(candidate)
                if info and info.state == ScrubState.SCANNING:
                    if pause_scrub(candidate):
                        self.active.discard(candidate)
                        self.paused.add(candidate)
                    else:
                        # Leave in active if pause failed
                        pass
                else:
                    self.active.discard(candidate)
                    self.paused.add(candidate)

        # 3. Prune finished entries that are no longer in any interesting state
        for pool_name in list(self.finished):
            info = states.get(pool_name)
            if info and info.state == ScrubState.SCANNING:
                # A new scrub was started on this pool
                self.finished.discard(pool_name)
                self.active.add(pool_name)
                log_msg(f"INFO: New scrub detected on '{pool_name}'")

        # Synchronize start times with active set
        for pool_name in list(self._start_times):
            if pool_name not in self.active:
                self._start_times.pop(pool_name, None)
        for pool_name in self.active:
            if pool_name not in self._start_times:
                self._start_times[pool_name] = time.time()

        if self._changed_since_save():
            self._save()

    def __init__(self, target: int = 1):
        self.pending: Set[str] = set()
        self.active: Set[str] = set()
        self.paused: Set[str] = set()
        self.finished: Set[str] = set()
        self.paused_by_user: Set[str] = set()
        self.target = max(1, target)
        self._start_times: Dict[str, float] = {}
        self._last_saved_state: Optional[dict] = None
        had_state = os.path.exists(SCRUB_STATE_PATH)
        self._load()
        if not had_state:
            # No prior state — use the passed target and persist it
            self.target = max(1, target)
            self._save()

    def _changed_since_save(self) -> bool:
        current = {
            "pending": sorted(self.pending),
            "active": sorted(self.active),
            "paused": sorted(self.paused),
            "finished": sorted(self.finished),
            "paused_by_user": sorted(self.paused_by_user),
            "target": self.target,
        }
        if current != getattr(self, "_last_saved_state", None):
            self._last_saved_state = current
            return True
        return False

    def summary(self) -> Dict[str, int]:
        return {
            "pending": len(self.pending),
            "active": len(self.active),
            "paused": len(self.paused),
            "finished": len(self.finished),
            "target": self.target,
        }

    def state_for_pool(self, pool_name: str) -> ScrubState:
        if pool_name in self.active:
            return ScrubState.SCANNING
        if pool_name in self.pending:
            return ScrubState.PENDING
        if pool_name in self.paused:
            return ScrubState.PAUSED
        if pool_name in self.finished:
            return ScrubState.FINISHED
        return ScrubState.NONE


# ---------------------------------------------------------------------------
# System scrub schedule helpers (systemd timers)
# ---------------------------------------------------------------------------

def get_system_scrub_state(pool_name: str) -> Dict[str, bool]:
    """Return {'weekly': bool, 'monthly': bool} for the given pool."""
    result = {"weekly": False, "monthly": False}
    for timer in ("zfs-scrub-weekly", "zfs-scrub-monthly"):
        unit = f"{timer}@{pool_name}.timer"
        try:
            proc = subprocess.run(
                ["systemctl", "is-enabled", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            enabled = proc.returncode == 0 and proc.stdout.strip() in (
                "enabled",
                "enabled-runtime",
            )
            key = "weekly" if "weekly" in timer else "monthly"
            result[key] = enabled
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            log_msg(f"WARN: Could not check {unit}: {e}")
    return result


def set_system_scrub_enabled(pool_name: str, weekly: bool, monthly: bool) -> bool:
    """Enable or disable systemd scrub timers for a pool. Returns True on success."""
    ok = True
    for timer, desired in (
        ("zfs-scrub-weekly", weekly),
        ("zfs-scrub-monthly", monthly),
    ):
        unit = f"{timer}@{pool_name}.timer"
        action = "enable" if desired else "disable"
        try:
            proc = subprocess.run(
                ["systemctl", action, "--now", unit],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if proc.returncode != 0:
                err = proc.stderr.strip() or proc.stdout.strip()
                log_msg(f"WARN: systemctl {action} {unit} failed: {err}")
                ok = False
            else:
                log_msg(f"INFO: {unit} {action}d")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            log_msg(f"WARN: systemctl {action} {unit} error: {e}")
            ok = False
    return ok


def sync_system_scrub_for_pools(pool_names: List[str], weekly: bool, monthly: bool):
    """Apply weekly/monthly settings to a list of pools."""
    for pool_name in pool_names:
        set_system_scrub_enabled(pool_name, weekly, monthly)
