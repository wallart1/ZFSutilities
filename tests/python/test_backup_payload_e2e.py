"""Backup/prune/rsync payload + strict-mode leaf-orchestrator e2e exercises.

Same front end as test_offsite_e2e (real builders, real BackupRunner,
scenarios from e2e_support); covers the rest of the GUI payload surface
that the strict-mode campaign touched:

- backup send/receive steps (full, incremental, destructive with hold
  preservation),
- the prune step (zfscleanup over the backup's datasets),
- the rsync step wrapper,
- the flipped leaf orchestrators driven live (zfssend, zfsfullcopy,
  zfsrestore) and the zfshold round trip.

Mutation-level scenarios self-skip in unprivileged contexts; the ITF
guest driver runs the full matrix.
"""

import e2e_support as e2e
import pytest
from test_support import requires_gi

pytestmark = requires_gi

from test_offsite_e2e import BackupRunnerExecutor, isolate_runner_state

BACKUP_SCENARIOS = [
    pytest.param(name, fn, level, engine, id=name)
    for name, fn, level, engine in e2e.scenarios_matching(
        ("backup-", "prune-", "rsync-", "orch-", "holds-")
    )
    if level != "none"
]

NO_POOL_SCENARIOS = [
    pytest.param(name, fn, level, engine, id=name)
    for name, fn, level, engine in e2e.scenarios_matching(
        ("backup-", "prune-", "rsync-", "orch-", "holds-")
    )
    if level == "none"
]


def executor_for(engine):
    """GUI payloads run under the input-hold protocol via the real
    BackupRunner; CLI orchestrators run protocol-off through the pty
    executor, exactly as cron/terminal would."""
    if engine == "cli":
        return e2e.PtyExecutor(input_hold=False)
    return BackupRunnerExecutor(label="Backup")


class TestNoPoolScenarios:
    """Pool-free scenarios (rsync wrapper): run anywhere GLib is present."""

    @pytest.fixture(autouse=True)
    def _isolate_runner_state(self, tmp_path, monkeypatch):
        isolate_runner_state(monkeypatch, tmp_path)
        e2e.pin_payload_env(monkeypatch, tmp_path)
        yield

    @pytest.mark.parametrize("name,fn,level,engine", NO_POOL_SCENARIOS)
    def test_scenario(self, name, fn, level, engine):
        registry = e2e.DatasetRegistry()
        fn(e2e.Harness(executor_for(engine), registry))


@pytest.mark.skipif(
    not e2e.read_capable(),
    reason="needs root + zfstest1/2/3 online (dev container or sudo)",
)
class TestBackupPayloadScenarios:
    @pytest.fixture(autouse=True)
    def _pin_payload_env(self, tmp_path, monkeypatch):
        e2e.pin_payload_env(monkeypatch, tmp_path)

    @pytest.mark.parametrize("name,fn,level,engine", BACKUP_SCENARIOS)
    def test_backup_scenario(self, name, fn, level, engine):
        if level == "mutation" and not e2e.mutation_capable():
            pytest.skip(
                "dataset mutations unavailable (unprivileged context); "
                "run via the ITF guest driver for the full matrix"
            )
        registry = e2e.DatasetRegistry()
        try:
            fn(e2e.Harness(executor_for(engine), registry))
        finally:
            leftovers = registry.cleanup()
        assert not leftovers, f"cleanup could not destroy: {leftovers}"
        e2e.assert_no_residuals(registry)
