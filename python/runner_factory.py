"""Factory for creating BackupRunner instances used by the GUI."""

from backup_runner import BackupRunner


class RunnerFactory:
    """Creates BackupRunner instances sharing the same GUI callbacks."""

    def __init__(self, log_func, set_stdin_enabled_func, progress_func=None):
        self.log_func = log_func
        self.set_stdin_enabled_func = set_stdin_enabled_func
        self.progress_func = progress_func

    def create(self, label, on_start=None):
        """Return a new BackupRunner with the given label and optional start callback."""
        return BackupRunner(
            self.log_func,
            self.set_stdin_enabled_func,
            self.progress_func,
            label=label,
            on_start=on_start,
        )
