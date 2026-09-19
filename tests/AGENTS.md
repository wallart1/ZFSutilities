# Test Workflow

1. Iterate small: run only the affected suites, never the full suite.
    - Bash: `tests/run-tests test-<name>`
    - Python: `pytest tests/python/test_<name>.py -x --tb=short` (applies after
      Phase 2 of the working-conditions plan — until then use the current
      runner: `tests/run-python-tests test-<name>`)
2. Never debug against a full-suite run. Reproduce the failure with the
    single failing suite first.
3. Run the full `tests/run-tests` once, at the end, before responding.
4. Environment-caused failures (GTK/gi, pv, ZFS, root, test pools) are
   environment issues: say so and skip; never "fix" product code for them.
5. No real `sleep` in new tests; use the env-overridable timing knobs
   (Phase 1). Soak suites are excluded from default runs.
6. When a refactor legitimately changes expected output, regenerate golden
   files (Phase 6) and review the diff; do not hand-repair assertions.
