"""Factory for creating BackupRunner instances used by the GUI."""

from typing import TYPE_CHECKING

from backup_config import log_msg

if TYPE_CHECKING:  # pragma: no cover - import for type hints only
    from backup_runner import BackupRunner


class RunnerFactory:
    """Creates BackupRunner instances sharing the same GUI callbacks."""

    def __init__(self, log_func, set_stdin_enabled_func, progress_func=None, input_event_func=None):
        self.log_func = log_func
        self.set_stdin_enabled_func = set_stdin_enabled_func
        self.progress_func = progress_func
        self.input_event_func = input_event_func

    def create(self, label, on_start=None):
        """Return a new BackupRunner with the given label and optional start callback.

        BackupRunner is imported lazily, at runner-creation time, on purpose:
        handler modules import this factory for `new_dataset_action_runner`,
        and several of them are imported by test suites inside a mock_gtk()
        context at collection time. A module-level import of backup_runner
        here would bind its GLib to that mock for the life of the process —
        leaving later real-GLib users (the e2e payload suites) with mocked
        io watches whose steps never progress.
        """
        from backup_runner import BackupRunner

        return BackupRunner(
            self.log_func,
            self.set_stdin_enabled_func,
            self.progress_func,
            label=label,
            on_start=on_start,
            input_event_func=self.input_event_func,
        )


class DatasetActionRunners:
    """One BackupRunner per GUI dataset action.

    Dataset actions are serialized by the hierarchical dataset locks
    (``zfs_lock_manager``), not by a shared runner: actions on
    non-conflicting datasets may run concurrently, each on its own runner
    with its own session log and its own Dashboard cancel row.  The tracker
    only keeps live runners enumerable for the shared GUI surfaces (quit
    guard, stdin routing, Dashboard running tasks, cancel dispatch); it
    applies no gating of its own.

    A runner leaves the tracker when its completion callback runs without
    restarting it: chained phases (migrate copy -> cutover -> repair,
    enrollment after pool creation) restart the same runner synchronously
    inside the callback, so a chain keeps its runner until it truly ends.
    A runner that is never started is never tracked.
    """

    def __init__(self, factory: RunnerFactory):
        self._factory = factory
        self._live: dict[int, BackupRunner] = {}
        self._next_id = 1

    def new_runner(self) -> "BackupRunner":
        """Create a fresh dataset-action runner, tracked from its first start()."""
        runner = self._factory.create("Dataset action")
        action_id = self._next_id
        self._next_id += 1
        tracker = self
        original_start = runner.start

        def start(on_complete=None):
            tracker._live[action_id] = runner

            def wrapped_on_complete(cancelled=False, rc=None):
                try:
                    if on_complete is not None:
                        on_complete(cancelled=cancelled, rc=rc)
                finally:
                    if not runner.running:
                        tracker._live.pop(action_id, None)

            original_start(on_complete=wrapped_on_complete)

        runner.start = start
        return runner

    def live_runners(self) -> list["BackupRunner"]:
        """Every tracked runner, oldest first (running or between chained phases)."""
        return list(self._live.values())

    def running_entries(self) -> list[tuple[int, "BackupRunner"]]:
        """Return (id, runner) pairs for runners with a run in flight."""
        return [
            (action_id, runner)
            for action_id, runner in self._live.items()
            if getattr(runner, "running", False)
        ]

    def runner_by_id(self, action_id: int) -> "BackupRunner | None":
        """Return the tracked runner with *action_id*, or None."""
        return self._live.get(action_id)

    def any_running(self) -> bool:
        """True while any tracked dataset action has a run in flight."""
        return any(getattr(runner, "running", False) for runner in self._live.values())


def new_dataset_action_runner(app):
    """Return a fresh runner for a GUI dataset action, or None (WARN logged).

    There is no busy gate to check anymore — the dataset locks decide
    whether an action may proceed, and refusals name the blocking holders.
    """
    tracker = getattr(app, "dataset_actions", None)
    if tracker is None:
        log_msg("WARN: Dataset runner not available")
        return None
    return tracker.new_runner()
