# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

- (test harness, found 2026-11-01 wrap-up): several suites pass MULTIPLE
  arguments to `test_fail` (a message plus a diagnostic payload, or a
  sentence split across two strings), but `test-lib.sh`'s `test_fail`
  reads only `$1` (`local reason="$1"`) — the second argument is silently
  dropped and split sentences print truncated. Affected sites:
  tests/test-attach-vm-disk (8, incl. sentence-splits like "validation
  must" + "not use it. Output: ..."), tests/test-installer-flows (2),
  tests/test-list-vm-disks:629, tests/test-zfsdelsnap:287,
  tests/test-test-lib:119. Diagnostic-only (verdicts and counts are
  unaffected); the failure reasons lose their detail exactly when an
  operator needs it. Candidate fix: make `test_fail` join "$*" like
  log_msg does, or rewrite the call sites — harness-wide change, out of
  scope for this cycle's standards pass.

- (line length, found 2026-11-01 wrap-up): three pre-existing >100-col
  Python lines outside this cycle's hunks (ruff's selected rules don't
  include E501): python/profile_dialogs.py:176 (108 — single-token
  f-string payload, unwrappable without changing bytes),
  tests/python/test_memory_page.py:478 (103),
  tests/python/test_profile_dialogs.py:1346 (102). Cosmetic only.


(2026-10-31: the sole open entry — the restore→checkagainst cross-file
pytest ordering flake — was fixed by the treeview-sizing change's
test-order hardening: test_checkagainst_page now evicts previously bound
real-gi gui_helpers before its mock import. Verified with the entry's
exact repro pair, all green.)
