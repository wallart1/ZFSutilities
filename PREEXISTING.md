# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (test flake, cross-file pytest ordering, found 2026-10-30): running two
  Python test files in ONE pytest process —
  `pytest tests/python/test_restore_page.py tests/python/test_checkagainst_page.py`
  (restore first) — fails 4 checkagainst dialog assertions
  (TestActionHandlers::test_on_ca_save_rejects_empty_rows,
  TestActionHandlersEmptyFields empty-label/source_root/dest_root) that pass
  per-file; verified identical on clean HEAD with all four involved files
  reverted. Same in-process cross-file pollution class as the 2026-10-26
  entries retired at 0.135.0 (that fix made test_backup_page's mock_gtk
  contexts fresh=True; restore/checkagainst are not covered). Alphabetical
  full-suite ordering never pairs them this way, and the sanctioned
  per-suite runner is unaffected.

- (false positive, bash pool-identity detector, found 2026-10-31):
  `detect_pool_identity` in `lib/iscsi-lib.sh` (surfaced by
  `bin/check-prerequisites` and `bin/setup-iscsi-targets`) reports
  "expected pool ... is not imported — offline, renamed, or replaced" for
  offsite rotation pools that are exported on purpose (live instance on
  stewie: z22tb). The Dashboard's copy of the check
  (`_compute_pool_identity_warnings`) now exempts GUI-config offsite
  candidates, but the bash layer has no offsite knowledge; closing the
  bash side needs an offsite marker in node.conf (a schema the user owns)
  or another bash-readable source. Not fixed: requires a config-schema
  decision.

- (test flake, subprocess cancel deadline, found 2026-11-01):
  `tests/python/test_profile_runner.py`
  `TestCancelSubprocess::test_sigterm_cancels_running_profile` timed out
  in the full gate (6 pytest workers): after SIGTERM the runner was
  SIGKILLed past the test's 15 s `proc.wait` deadline. Passes standalone
  (4 s) and in a same-worker-count rerun of the whole python leg on the
  identical tree (tooltip-phase working tree; the diff touches no runner
  code). Timing-budget flake under load, same class as a busy dev host
  stealing the subprocess's CPU window.
