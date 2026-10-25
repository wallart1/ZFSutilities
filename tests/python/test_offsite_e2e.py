"""Offsite GUI payload end-to-end exercises — real builders, real BackupRunner.

Three layers, each self-gated so the same suite runs everywhere:

- **Mechanics** (needs GLib only): the real BackupRunner engine driven
  headless through a GLib.MainLoop — pty stdin, the input-hold REQ/ACK
  round trip, rc propagation, session-log capture.  No ZFS required.
- **Read-level scenarios** (root + zfstest1/2/3 online, e.g. the
  unprivileged dev container): dry-run payload runs; zero pool mutations.
- **Mutation-level scenarios** (privileged contexts: dev host under sudo,
  ITF guest): the full offsite matrix the GUI smoke test drives by hand —
  chain steps with holds, incrementals, rollback, resume tokens, scrub
  pause, includes/excludes.

The scenario functions themselves live in e2e_support (shared with the
ITF guest driver); this module contributes the GLib executor and the
pytest front end.
"""

import time

import e2e_support as e2e
import pytest
from command_builders import BashStep
from test_support import import_or_skip_gi, requires_gi

pytestmark = requires_gi

gi = import_or_skip_gi("gi")
gi.require_version("GLib", "2.0")
from gi.repository import GLib

backup_runner = import_or_skip_gi("backup_runner")


# ---------------------------------------------------------------------------
# The real-engine executor
# ---------------------------------------------------------------------------


class BackupRunnerExecutor:
    """Runs one BashStep through the real BackupRunner, headless.

    The GUI's exact execution semantics: GLib main loop, pty stdin with echo
    off, ``ZFSUTILITIES_INPUT_HOLD``/``ZFSUTILITIES_LOG_INHERIT`` environment,
    ``ZFSU-INPUT-*`` marker interception.  Every input-hold REQ is answered
    with "n" (auto-decline, like an operator refusing a dialog) and recorded;
    scenarios assert on the recorded prompts.
    """

    def __init__(self, label="Offsite backup", timeout=300):
        self.label = label
        self.timeout = timeout
        # Auto-answer for input-hold REQs; scenarios may flip it (e.g. the
        # prune scenario accepts the checkagainst removal gate).
        self.answer = "n"

    def run_step(self, step, timeout=None, prefeed=""):
        timeout = timeout or self.timeout
        captured = []
        prompts = []
        done = {}
        watchdog = {"hit": False}

        def on_input_event(runner, event, uuid, text=None):
            if str(event).lower() == "req":
                prompts.append((uuid, text or ""))
                runner.send_input(self.answer)

        runner = backup_runner.BackupRunner(
            log_func=captured.append,
            set_stdin_enabled_func=lambda enabled: None,
            label=self.label,
            input_event_func=on_input_event,
        )
        runner.set_steps([step])
        runner.prepare_session_log()

        loop = GLib.MainLoop()

        def on_complete(cancelled=False, rc=None):
            done.update(cancelled=cancelled, rc=rc)
            if loop.is_running():
                loop.quit()

        def on_timeout():
            if not done:
                watchdog["hit"] = True
                runner.cancel()
            return False

        started = time.monotonic()
        GLib.timeout_add(int(timeout * 1000), on_timeout)
        runner.start(on_complete=on_complete)
        if prefeed:
            runner.send_input(prefeed.strip())
        if not done:
            loop.run()
        return e2e.StepResult(
            rc=done.get("rc"),
            output="\n".join(captured),
            cancelled=bool(done.get("cancelled")),
            timed_out=watchdog["hit"],
            prompts=prompts,
            duration=time.monotonic() - started,
        )


# ---------------------------------------------------------------------------
# Mechanics: the real BackupRunner engine, no ZFS needed
# ---------------------------------------------------------------------------


class _StubLogIndex:
    """LogIndex stand-in so mechanics runs never touch the real index."""

    @staticmethod
    def load():
        return _StubLogIndex()

    def set_status(self, *args, **kwargs):
        pass

    def save(self):
        pass


def isolate_runner_state(monkeypatch, tmp_path):
    """Session logs into tmp; rsync-log truncation and the log index are
    GUI conveniences outside the scope of these exercises."""
    import session_log

    def _create_session_log(runner_self):
        path = session_log.create_session_log_file(
            runner_self._get_tab_type(), session_log_dir=str(tmp_path)
        )
        runner_self._session_log_file = path
        return path

    monkeypatch.setattr(
        backup_runner.BackupRunner,
        "_create_session_log_file",
        _create_session_log,
    )
    monkeypatch.setattr(backup_runner, "_truncate_rsync_log", lambda: None)
    monkeypatch.setattr(session_log, "LogIndex", _StubLogIndex)


class TestBackupRunnerMechanics:
    @pytest.fixture(autouse=True)
    def _isolate_runner_state(self, tmp_path, monkeypatch):
        isolate_runner_state(monkeypatch, tmp_path)
        yield

    def _run(self, step, timeout=60):
        return BackupRunnerExecutor().run_step(step, timeout=timeout)

    def test_benign_step_rc0(self):
        step = BashStep(["bash", "-c", "echo hello-from-payload; exit 0"], "mechanics: echo")
        result = self._run(step)
        assert result.rc == 0
        assert not result.cancelled and not result.timed_out
        assert "hello-from-payload" in result.output

    def test_rc_propagation(self):
        # GUI steps are fatal: a non-zero step rc must reach on_complete.
        step = BashStep(["bash", "-c", "exit 7"], "mechanics: rc7", is_rsync=False, fatal=True)
        result = self._run(step)
        assert result.rc == 7
        assert not result.cancelled

    def test_input_hold_roundtrip(self):
        """A GUI-style prompt must surface as a REQ, get answered, never leak."""
        payload = (
            "source ~/bashinit; bashinit; "
            'if ask_yn "Proceed with the test?"; then echo ANSWER-YES; exit 0; '
            "else echo ANSWER-NO; exit 0; fi"
        )
        step = BashStep(["bash", "-c", payload], "mechanics: ask_yn")
        result = self._run(step)
        assert result.rc == 0
        assert "ANSWER-NO" in result.output
        assert len(result.prompts) == 1
        assert "Proceed with the test?" in result.prompts[0][1]
        # The side-channel markers are intercepted, never logged as output.
        assert "ZFSU-INPUT-" not in result.output

    def test_pty_echo_off(self):
        """The auto-answer must not be echoed back into the output stream."""
        payload = 'source ~/bashinit; bashinit; ask_yn "Anybody there?"; echo "rc=$?"'
        step = BashStep(["bash", "-c", payload], "mechanics: echo-off")
        result = self._run(step)
        assert "rc=1" in result.output
        assert "\nn\n" not in result.output

    @pytest.mark.parametrize(
        "name,fn,level,engine",
        [
            pytest.param(name, fn, level, engine, id=name)
            for name, fn, level, engine in e2e.scenarios_matching(("offsite-negative-control",))
        ],
    )
    def test_negative_controls(self, name, fn, level, engine):
        fn(e2e.Harness(BackupRunnerExecutor(), e2e.DatasetRegistry()))


# ---------------------------------------------------------------------------
# Scenario matrix: offsite GUI payloads
# ---------------------------------------------------------------------------

OFFSITE_SCENARIOS = [
    pytest.param(name, fn, level, engine, id=name)
    for name, fn, level, engine in e2e.scenarios_matching(("offsite-",))
    if level != "none"
]


@pytest.mark.skipif(
    not e2e.read_capable(),
    reason="needs root + zfstest1/2/3 online (dev container or sudo)",
)
class TestOffsitePayloadScenarios:
    @pytest.mark.parametrize("name,fn,level,engine", OFFSITE_SCENARIOS)
    def test_offsite_scenario(self, name, fn, level, engine):
        if level == "mutation" and not e2e.mutation_capable():
            pytest.skip(
                "dataset mutations unavailable (unprivileged context); "
                "run via the ITF guest driver for the full matrix"
            )
        registry = e2e.DatasetRegistry()
        try:
            fn(e2e.Harness(BackupRunnerExecutor(), registry))
        finally:
            leftovers = registry.cleanup()
        assert not leftovers, f"cleanup could not destroy: {leftovers}"
        e2e.assert_no_residuals(registry)
