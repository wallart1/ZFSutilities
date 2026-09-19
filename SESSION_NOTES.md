# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves.

## 2026-09-18 — Agent Working Conditions, Phase 6 (golden files) + Phase 6b/6c complete

- New helpers: `assert_golden` in `tests/test-lib.sh` (with `TESTS_UPDATED`
  counter and `Updated:` summary line) and `tests/python/golden.py`
  (`golden.check`, skip-means-updated under `UPDATE_GOLDEN=1`). Goldens live
  in `tests/golden/<suite>/<name>.golden`, canonical form exactly one trailing
  newline, argv one element per line; files are rewritten only on real
  content change, which is what makes no-op update runs diff-clean.
- Migrated (Phase 6b): `tests/python/test_pool_migrate.py` builder classes —
  8 goldens under `tests/golden/test_pool_migrate/`. The migration
  send/receive goldens normalize the checkout-absolute script path to
  `REPO_ROOT` (machine independence, same principle as Phase 6's hostname
  normalization). `test_rate_limit_assignment_gated` split into
  `_emitted`/`_omitted` because the Python helper's update-mode skip raises
  and would skip the second golden check.
- Migrated (Phase 6c): `tests/python/test_pool_migrate_dialogs.py` — 4
  plan-level goldens under `tests/golden/test_pool_migrate_dialogs/`
  (whole copy/cutover phases serialized one step per line via shlex.join,
  REPO_ROOT-normalized). Kept as assertions: rate-limit propagation gating
  across all copy steps in both modes. Abeyance closed.
- Docs: `docs/docs/developer-guide/testing.md` gained "Golden Files" and
  "Python Golden Files" sections, including the update-mode skip-bucket
  caveat. tests/AGENTS.md rule 6 wording already matches; no AGENTS.md edits.
- Full suite green after the change (soak suite the only skip).

## 2026-09-17 — Agent Working Conditions, Phase 4 (environment preflight) complete

- The harness (`tests/run-tests` preflight) now skips environment-dependent
  suites automatically with stated reasons; report unexpected skips — never
  work around them.
- Delivered: `tests/requirements.manifest` (single declared mapping),
  preflight in `tests/run-tests` (`SKIPPED (missing: <caps>)`, exit 0 on
  skips-only, `Python tests skipped` summary line), `import_or_skip_gi` +
  `requires_gi` guards in `tests/python/test_support.py` covering 11 Python
  suites, `TestGiImportGuards` consistency check in
  `tests/python/test_gui_infrastructure.py`, `tests/test-run-tests-preflight`
  harness self-test, and the testing.md "Environment preflight and skips"
  section.
- Verified: full suite green (3 consecutive runs, only the soak suite
  skipped); with gi hidden the harness exits 0 with every dependent suite
  skipped and its reason.

## 2026-09-17 — Session-notes issues resolved (inter-suite coupling + cache fragility)

- **Fixed:** `test_disk_surface_test` + `test_datasets_tree` in one pytest
  process used to fail `TestStartCancelHelpers::test_start_failure_does_not_record`
  with `TypeError: could not convert value for property 'transient_for' from
  MagicMock to GtkWindow` (pre-existing at HEAD 7e04f43). Root cause: the
  `_import_*` helpers popped only the target module, so a GUI dependency
  (`gui_helpers`) cached with real bindings by another suite's collection-time
  import leaked real Gtk into the re-imported module. All 19 pop+mock_gtk
  helper sites across 13 suites now use `mock_gtk(fresh=True)`, which evicts
  the whole `GUI_MODULES` closure and restores prior state on exit.
  Prevention: `TestGiImportGuards` in `test_gui_infrastructure.py` (rule R3)
  statically rejects unmocked in-function GUI imports whose call sites are not
  under a `mock_gtk` context.
- **Fixed:** the `sys.modules` cache-pollution fragility — `test_gui_helpers`
  imported `gui_helpers` unmocked inside tests and only survived bare
  containers via pollution luck. It now imports through a `mock_gtk()` helper
  and is genuinely environment-independent (passes standalone with gi hidden).
- **Fixed (product):** `python/gui_helpers.py` and `python/logs_page.py`
  imported `Gdk` without `gi.require_version("Gdk", "3.0")`. On systems with
  Gdk 4.0 typelibs (e.g. Linux Mint) a standalone `import gui_helpers` crashed
  with `gi.RepositoryError: Requiring namespace 'Gdk' version '3.0', but '4.0'
  is already loaded`. Both now pin Gdk 3.0, matching the existing convention
  in `main.py`/`docs_viewer.py`. Prevention:
  `TestGiImportGuards::test_multi_version_gi_namespaces_are_pinned` fails if
  Gdk/Gtk/WebKit2 are ever imported unpinned in `python/`.
- testing.md `mock_gtk` guidance updated (`fresh=True` required for `_import_*`
  helpers).

## 2026-09-17 — OOM diagnosis and fixes (parallel-test memory)

- **Diagnosis.** Kernel log showed `[pytest-xdist]` workers OOM-killed at
  ~4 GB anon RSS twice during stacked full runs, while controlled single runs
  peak at ~500-700 MB per worker (serial whole-layer peak: 862 MB; the heaviest
  worker observed was in `test_scrub_manager` at 589 MB). The kill snapshots
  show 7.4 GB of anonymous memory system-wide (16 Brave processes + Chrome +
  node + multiple test generations on an 8 GB box). Experiment proved xdist
  workers exit when their controller dies — the multi-GB victims were stacked
  generations from interrupted runs whose pytest trees outlived the harness.
- **Fix 1 — cleanup:** `tests/run-tests` now runs pytest in the background,
  records its PID, and the EXIT trap terminates the pytest tree (TERM to the
  controller; workers follow). Verified: TERM the harness mid-run → zero
  surviving pytest/xdist processes.
- **Fix 2 — memory-aware parallelism:** full-run Python layer uses
  `-n $(pytest_jobs_auto)` — `MemAvailable / 900 MB`, clamped to `[1, nproc]`,
  override with `ZFSUTILITIES_PYTEST_JOBS`. The Environment banner prints
  `pytest-workers=N`. Bash-layer `--jobs` default unchanged (bash suites are
  small). Wall time unchanged (~55 s full suite).
- Guard: `tests/test-run-tests-preflight` covers `pytest_jobs_auto` (4 tests).

## 2026-09-17 — Session-notes issues #1 and #2 closed (xdist flake, legacy script)

- **Issue #2 (xdist flake): FIXED.** Root-caused with deterministic repros:
  the suite ecosystem is bipartite per module — some suites force a real-bound
  module via @patch decorator resolution (e.g. `test_zfsutilities_gui`, which
  patches `__init__` on the real GObject class), others rely on the sticky
  mock-bound first import under `mock_gtk()`. When both patterns touched one
  module in a single xdist worker, tests mixed real Gtk classes with mock Gtk
  (`AttributeError: unsupported magic method '__init__'`,
  `TypeError: isinstance() arg 2 must be a type`). Fixes:
  `test_support.import_gui_fresh(name)` — evicts *name* and the GUI closure,
  imports under the caller's mock context, then RESTORES the closure to its
  prior bindings (only *name* keeps the fresh binding), so sticky-binding
  suites whose @patch decorators resolve a cached module (e.g.
  `test_logs_page`) are not disturbed; `test_zfsutilities_gui` helpers
  guarantee the real module (their actual contract — a mock-bound foreign
  copy is evicted); docs-viewer and log-status helpers converted; bare
  in-function GUI imports banned. Guard:
  `TestGiImportGuards::test_in_function_gui_imports_are_guarded` (R4) rejects
  in-function GUI imports with no mock context and no prior pop. Verified:
  both deterministic pair-order repros green, 6/6 `pytest -n auto`
  full-layer runs green, serial layer green, full harness green (3 runs).
  Known residual: suites importing a GUI module under a non-fresh context
  (~190 sites) rely on their own first import's sticky binding — self-
  consistent per module today; convert to `import_gui_fresh` if a new suite
  ever mixes binding modes for the same module.
- **Issue #1 (legacy script): FIXED.** `bin/zfslockmanager-test` deleted —
  31 real sleeps, not harness-discovered, yet shipped to production by
  `deploy-version`; superseded by `tests/test-zfslockmanager{,-remote,-soak}`.
  References removed from `commands.md` and `bash-logging-exceptions.md`.
- **Phase 5 (working-conditions plan) implemented, uncommitted.** `--list`
  (alias `--count`) added to `tests/run-tests` + both Python shims; count
  columns were already stripped from testing.md in earlier phases. `--list`
  counts dynamically — bash suites run quietly through the normal parallel
  machinery and report executed `Total:` (TESTS_RUN); Python via
  `--collect-only` — because static counting cannot match executed totals
  (loops, conditional call sites). Verified: per-suite `--list` counts
  identical to a full run's per-suite totals (762 bash + 2827 Python = 3589).
  Also fixed: `test-lib.sh` was enumerated as a phantom suite by the default
  `find` (counted as 1 "passed" via fallback in every full run). Open items
  reported to user: intermittent `test_zfsutilities_gui` failures under
  pytest-xdist (2 hits, different tests, same module); 5 tests in
  `test-paths`/`test-zfsdelfs` start but never pass/fail/skip (Total > Passed
  with no Failed/Skipped); pre-existing shellcheck SC2120/SC2119 on
  `pytest_jobs_auto` (Phase 4 code).
- **Pre-existing issues 2/3/4 addressed (user request, same uncommitted batch).**
  (4) shellcheck SC2120/SC2119 on `pytest_jobs_auto` — justified disables.
  (3) Abandoned tests: root cause was `declare -A` (not `-gA`) in libraries
  loaded through bashinit's `source_helper` function — the declaration becomes
  a function-local and vanishes on return. Fixed in `lib/iscsi-lib.sh`
  (`iscsi_teardown`) and `bin/zfslockmanager` (three `_zfslock_*` arrays);
  audited all source_helper-loaded files — no other top-level declares.
  `tests/test-paths`: subshell-scoped assertions in `test_paths_env_override`
  now run in the parent (values printed from the subshell); the defined-but-
  never-invoked `test_paths_bashinit_respects_log_dir_override` is now invoked
  (7/7). `tests/test-zfsdelfs` 10/10 with real assertions executing.
  (2) `test_zfsutilities_gui` xdist flake: @patch decorators resolve targets
  at test start; the old body-time eviction could swap the module object
  after patching, leaving patches on one object and the code under test on
  another. Fixed with an autouse fixture that evicts mock-bound cached copies
  BEFORE each test (hence before patch resolution); body accessor no longer
  evicts. Verified serially and under repeated full-layer xdist runs.
- **SC2295 notes in bin/zfslockmanager addressed (user request).** Not noise: in
  `${var#pattern}` the escaped quotes are literal pattern characters, so the
  unquoted `$field` expansion was pattern-matched. Fixed all 7 occurrences
  with shellcheck's suggested separately-quoted expansion (`${json#*\""$field"\":}`).
  Verified a field name containing glob chars now matches literally; lock
  suites and full suite green; shellcheck clean.
- **Phase 8 (Agent Working Conditions) complete 2026-09-18.** New:
  `share/dev/install-test-deps.sh` (canonical test deps for CI/container;
  writes /etc/zfsutilities-node.conf, deployment symlinks under
  /usr/local/lib/zfsutilities -> checkout, git safe.directory, tolerant
  /dev/loopN mknod), `share/dev/devcontainer-entrypoint.sh` (runtime loop
  nodes; docker /dev is tmpfs), `.devcontainer/` (Ubuntu 24.04 image;
  /root/bashinit -> /workspace/bin/bashinit; ENTRYPOINT; run tests with
  `docker run --rm --init -v "$PWD:/workspace" -w /workspace
  zfsutilities-dev xvfb-run -a bash tests/run-tests` — --init is required,
  xvfb-run hangs as PID 1; invoke via `bash` for NFS-checkouts), and
  `.github/workflows/tests.yml` (push/PR job + nightly 17:5 UTC soak job,
  both xvfb-wrapped with ~/bashinit linked). Full suite green on host and in
  container (sole skip: soak; `--with-soak` green incl. soak).
  Env-coupling bugs fixed along the way: `pool_migrate.migration_snapshot_name`
  now preserves an aware datetime's offset (naive->local unchanged; prod calls
  it arg-less); golden normalization for the migrate-send wrapper path
  canonicalized via `test_support.normalize_repo_root`; `temp_config_dir`
  redirects XDG_CONFIG_HOME; new `temp_user_config_dir` isolates
  DocsViewerWindow construction (test_gui_infrastructure) from the real
  ~/.config; `check_partial_uninstall` gained ZFSUTILITIES_ETC_PREFIX (test
  fixture now uses it). testing.md gained a "CI and dev container" section.
  Phase 9 withdrawn by user. Remaining: user's wrap-up routine (audit,
  VERSION/changelog, commit, deploy to dev/prod — user runs deploy/switch
  themselves), push to GitHub triggers CI on main (acceptance part 1), then a
  throwaway branch with a deliberately broken test for acceptance part 2;
  deleting it afterwards. Nightly soak cron activates once workflow is on
  default branch. Image `zfsutilities-dev` exists locally. Flagged to user:
  ~/.config/zfsutilities/docs_viewer_state.json (mtime Sep 11) shows test
  pollution (theme slate) — left untouched; user may want to reset it.
