# Test Workflow

1. Iterate small: run only the affected suites, never the full suite.
    - Bash: `tests/run-tests test-<name>`
    - Python: `pytest tests/python/test_<name>.py -x --tb=short` (applies after
      Phase 2 of the working-conditions plan — until then use the current
      runner: `tests/run-python-tests test-<name>`)
2. Never debug against a full-suite run. Reproduce the failure with the
    single failing suite first.
3. Run the full `tests/run-tests` once, at the end, before responding.
4. Full-suite runs: always redirect to a log file FIRST, then read selectively:
tests/run-tests --failures-only > /tmp/zfs-run.log 2>&1; echo "rc=$?"
>grep -n "SUITE FAILED\|  FAIL" /tmp/zfs-run.log   # find the failures
>sed -n '<range>p' /tmp/zfs-run.log                # read just that region
  NEVER rerun the full suite to "capture more output."
  If the failure isn't in the log, rerun only the affected single suite.
5. Environment-caused failures (GTK/gi, pv, ZFS, root, test pools) are
   environment issues: say so and skip; never "fix" product code for them.
6. No real `sleep` in new tests; use the env-overridable timing knobs.
   Soak suites are excluded from default runs.
7. When a refactor legitimately changes expected output, regenerate golden
   files and review the diff; do not hand-repair assertions.
