# Test Workflow

1. Iterate small: run only the affected suites, never the full suite.
    - Bash: `tests/run-tests test-<name>`
    - Python: `pytest tests/python/test_<name>.py -x --tb=short` (applies after
      Phase 2 of the working-conditions plan — until then use the current
      runner: `tests/run-python-tests test-<name>`)
2. Never debug against a full-suite run. Reproduce the failure with the
   single failing suite first.
3. Run the full `tests/run-tests` once, at the end, before responding.
4. Full-suite runs: always capture the log first, then read selectively:
   tests/run-tests --log /tmp/zfs-run.log
># find failures
>grep -n "SUITE FAILED\|  FAIL" /tmp/zfs-run.log
># read the failing suite block by name
>sed -n '/Running: <suite-name>/,/^==========/p' /tmp/zfs-run.log
   NEVER rerun the full suite to "capture more output."
   If the failure isn't in the log, rerun only the affected single suite.
5. Environment-caused failures (GTK/gi, pv, ZFS, root, test pools) are
   environment issues: say so and skip; never "fix" product code for them.
6. No real `sleep` in new tests; use the env-overridable timing knobs.
   Soak suites are excluded from default runs.
7. When a refactor legitimately changes expected output, regenerate golden
   files and review the diff; do not hand-repair assertions.
8. Do not make any code changes while tests are running. If you do, cancel the
   tests that were running and rerun them after you've finished changing the code.

## Integrated end-to-end validation (itf)

When a change affects the installer, upgrade flow, or any behavior best
judged through the real user surface, run a journey in
`tests/integrated` in addition to the unit suites — do not hand-build
scratch VMs or reason from unit mocks alone.

- `tests/integrated/itf journey list` — available journeys (fresh install,
  uninstall/reinstall, leftovers, baseline, two-node, guest-probe,
  unarchive iSCSI rebuild, prereq decline, apt failure, release upgrade,
  GUI payload e2e matrix).
- `tests/integrated/itf journey run <name>` — full run; clone-start
  journeys reach the post-install point in minutes (no OS reinstall).
- `tests/integrated/itf journey run <name> --rerun` — re-verify a fix on
  the previous run's guests (rollback to the staging checkpoint —
  `as-cloned` for clone-start journeys, `os-installed` for install-start
  ones; the clone/install is skipped).
- Launch long runs detached (`setsid nohup … &`), watch with
  `itf watch`, and never open a guest console while a run is active.
- Product defects found through journeys go to `tests/integrated/FINDINGS.md`
  with a repair-plan proposal — never fixed inside a guest.
- Overview and safety model: `tests/integrated/README.md` and
  `docs/docs/developer-guide/integrated-testing.md`.

## GUI payload e2e matrix

Payload-level changes (anything the GUI drives through
`offsite_runner`/`command_builders`/BackupRunner, or the strict-mode
orchestrators) get exercised by the payload e2e matrix instead of hand
smoke tests — real builders, real runner, real pools:

- Dev container (read-only layer): `share/dev/run-e2e-container`
- Dev host under sudo: `tests/python/test_offsite_e2e.py` +
  `tests/python/test_backup_payload_e2e.py` (full matrix on the host's
  zfstest pools)
- ITF guest (full matrix, disposable): journey `j11-payload-e2e`
- Scenarios live once in `tests/python/e2e_support.py`; add new payload
  behaviors there with the right level (`none`/`read`/`mutation`) and
  engine (`gui` input-hold protocol / `cli` protocol-off).
