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
