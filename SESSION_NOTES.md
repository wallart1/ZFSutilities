# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves.

## 2026-09-19 — Migrate Pool smoke-test failure: double-prefix bug + holding namespace

- Smoke test (holding-pool migration of zfstest2 via zfstest3) failed in
  `zfs-migrate-send`: `cannot open 'zfstest2/zfstest2/zfstest1': dataset does
  not exist`. Root cause: `on_disks_migrate_pool` captured `row.name` from
  `zfs list -H` (FULL names including the pool prefix) into
  `datasets_by_pool`, but `_copy_steps`/`_build_verify_step`/holding destroy
  compose `f"{pool}/{dataset}"` — double prefix (`pool/pool/...`). Unit tests
  missed it because fixtures passed already-relative names. Fix: capture now
  strips the pool prefix; fixtures return full names like real zfs.
- User-directed design (approved over hard-blocking): holding-mode copies now
  land in a reserved namespace `<holding>/migrate_<source>/<dataset>`
  (`holding_migration_namespace()` in pool_migrate.py), so a pool that also
  receives backups/offsite copies (zfstest3 in the smoke test) stays usable as
  a holding pool. Namespace is deterministic (resume-safe across re-runs);
  cutover removes it with a single `zfs destroy -r
  <holding>/migrate_<source>`.
- Handler re-validates the source pool's dataset layout at execution
  (`_source_layout_changed`) and aborts with an explanation before the lock
  when the tree changed after the review.
- Golden `TestBuildMigrationSteps.test_holding_mode_cutover_sequence`
  regenerated (10 steps now; per-dataset destroys collapsed into one
  namespace destroy).

## 2026-09-19 — Development-cycle wrap-up (review, tests, docs)

- Resolved the open PREEXISTING.md item: ran `ruff format` across `python/`
  and `tests/` (31 files); `ruff format --check` and `ruff check` are now
  clean repo-wide. PREEXISTING.md has no open entries.
- Removed `var_widgets_differ_from_defaults` from `gui_helpers.py`: all four
  production callers had moved to `style_var_widgets_nondefault`, leaving it
  exercised only by its own tests (dead code per the single-call-site
  policy). Its test class and the `python-modules.md` table reference went
  with it.
- Added a profuse comment above the `loop\d+(p\d+)?` partition-row regex in
  `get_tree_selection_items` (>10-char regexes must be documented per
  coding-policies.md).
- Fixed `test_docs_integrity` AGENTS.md reference extraction to skip
  blockquote lines — the root AGENTS.md "Pre-existing issues" example quotes
  a `zfs_repository.py/test_zfs_repository.py` fragment that is illustrative,
  not a real path, and made `test_all_references_exist` fail. Added a
  regression test.
- Full suite green after the above.

## 2026-09-19 — Datasets page: zvol loop mounting

- Mount on a ZFS volume now attaches the volume's `/dev/zvol/…` device to a
  read-only loop device (`losetup --find --show --partscan --read-only`;
  read-only chosen with the user because these zvols are live VM disks via
  iSCSI and active backup targets). Partitions then appear as rows under the
  volume's tree entry (Type column = filesystem, or `No filesystem` when no
  fs is detected; bare device with fs listed as one row). Partitions mount
  under `paths.get_zvol_mount_dir()` (default `/mnt/zfsutilities`, env
  `ZFSUTILITIES_ZVOL_MOUNT_DIR`) and are browseable once mounted. Unmount
  symmetry (user-approved): partition row = umount; volume row = unmount
  partitions then `losetup -d`.
- New `ZfsRepository` methods: `loop_attach`, `loop_find`, `loop_detach`,
  `loop_partitions` (+ `LoopPartition` dataclass and `_parse_lsblk_partitions`
  pure parser), `device_mountpoint`; module helper `zvol_device_path`.
  gui_helpers grew `load_volume_loop_children`, `reload_row_children`,
  `find_tree_iter_by_full_name`; `on_row_expanded` refactored into
  `_load_children_for_row` (watch this if row kinds change). Partition rows
  are detected structurally (parent row Type == `volume`, name matches
  `loop\d+(p\d+)?`) — snapshot rows under volumes must keep being checked
  before that branch (done in `get_tree_selection_items` via the regex and in
  `update_mounted_states` via the snapshot-first ordering).
- Volume rows have no zfs `mounted` property (always `-`); button sensitivity
  for volumes derives from `losetup -j` state in
  `update_ds_button_sensitivity`.
- Docs: gtk-gui.md button table + new "Mounting ZFS volumes (zvols)"
  subsection; python-modules.md zfs_repository/paths entries.

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
- **2026-09-18 pre-existing issues sweep.** (1)
  `test_gui_infrastructure.py::test_capture_theme_parses_reported_scheme`
  pollution: verified already fixed at HEAD (Release 0.104.0 wraps the test in
  `temp_config_dir` + `temp_user_config_dir`); ran the test and the full
  TestDocsViewerStatePersistence class — real ~/.config/zfsutilities/
  docs_viewer_state.json mtime+sha256 unchanged (67a83655..., Sep 11). Content
  (zoom 1.1, 951x1004@965,36) does not match any mock geometry, so it reads as
  genuine user state, not residue; left untouched. (2) bin/zfslockctl cmd_wait
  integer-only ZFSLOCK_WAIT_INTERVAL validation: replaced with the shared
  `_zfslock_sanitize_interval` (same call as zfslockmanager: default 30,
  fallback 1, fractional allowed). Added tests/test-zfslockctl (6 tests:
  validation, no-sleep availability, fractional reaches sleep, abc/0 fallback;
  sleep-stub pattern from test-zfslockmanager; suite fails on the old code,
  passes on the fixed). Doc: lock-manager.md zfslockctl section now states the
  shared interval semantics. PREEXISTING.md had no entries (nothing to
  remove; 0 remain).

2026-09-19 — Retention Advanced Prune Options UX fix: the red frame was retitled
"Ignore Retention Policies - Danger Zone" while holding the filter rows, with the
actual "Ignore retention policies" toggle below it — same words for section and
toggle, and the filters were silently inert in normal prune mode. Fix (python/
retention_page.py): toggle + explanatory caption now sit at the top of the
expander; frame renamed "Mass Delete Filters - Danger Zone"; includes/excludes/
startwith/endwith/snapshot_has are desensitized when the toggle is off
(_sync_releaseholds_widget replaced by _sync_mass_delete_filter_sensitivity;
releaseholds stays sensitive in both modes); checkbox tooltip corrected ("filters
in the 'Mass Delete Filters' frame below"). Tests: test_retention_page.py label,
tooltip, and new filter-sensitivity tests. Docs: user-guide/retention.md Advanced
Prune Options section and gtk-gui.md Retention passages (also fixed a stale
"Release Holds only when ignore mode is active" claim — it applies in both modes).
Full tests/run-tests green (3668 passed, 0 failed, 1 env skip). No new
pre-existing issues discovered this turn; 1 entry remains in PREEXISTING.md
(repo-wide ruff format drift, from an earlier session).

2026-09-19 — Wrap-up cycle (steps 1-4). (1) Resolved both PREEXISTING.md
entries: documented the 18-char `vm-(\d+)-disk-\d+` regex in
gui_helpers.py `diagnose_dataset_busy`; `_MigrateState` gained a
`holding_pools` field (all imported non-root pools) so empty imported pools
are now offered as holding-pool candidates (`_holding_candidates` draws from
it; `on_disks_migrate_pool` populates it). (2) Policy review: ruff check and
ruff format clean on python/ and tests/ (one pre-existing format nit in
docs/docs/developer-guide/testing.md, recorded); shellcheck clean after
renaming the `acquired` local to `poll_acquired` in tests/test-zfslockmanager
(SC2178/SC2128 false positive from the same-named array in
bin/zfslockmanager). (3) Tests: new TestHoldingCandidates class in
test_pool_migrate_dialogs.py (empty pool offered/accepted as holding pool,
source-only reports no holding pool). Full tests/run-tests green (73 suites,
3718 passed, 0 failed, 1 env skip). (4) Docs: gtk-gui.md Migrate Pool
holding-pool bullet now states that any imported non-root pool qualifies,
even an empty one; test_docs_integrity.py passes. New PREEXISTING.md entries
(2, unfrozen per instructions): undocumented 21-char bash regex in
bin/zfslockmanager `_zfslock_sanitize_interval`; the testing.md ruff-format
nit.

2026-09-19 — Disks-page view-scoping + Migrate Pool silent-source fix (user
report). Symptoms: with the page pool selector on empty pool zfstest1 and the
Dataset Tuning view open, Migrate Pool was clickable and opened the wizard
preselected on zfstest2 with zfstest1 absent from the Source drop-down. Root
causes: (1) the Disks-page action bar was not view-aware, so pool/disk
buttons stayed sensitive in Dataset Tuning (and dataset buttons in
Inventory); (2) on_disks_migrate_pool silently fell back to pools[0] when the
selector's pool was not a migratable source (empty or root pool). Fixes
(python/disks_page.py): new `_current_disks_view()` helper (unknown view
names fall back to "inventory" so mocked-app tests keep working) and a view
gate in update_disks_button_sensitivity — pool/disk buttons (Create Pool,
growth/maintenance six, SMART Details, Surface Test) require the Inventory
view, Apply Profile/Rewrite Data require the Tuning view, with pointing
tooltips; `_on_view_radio_toggled` now refreshes sensitivity. Fix
(python/pool_migrate_dialogs.py): a preselected pool that cannot be a source
now shows an info dialog (root-pool wording vs. empty-pool wording that
mentions holding-pool eligibility) and returns before the wizard opens; the
pools[0] fallback remains only for an empty preselection. Tests: new
TestViewScopedButtonSensitivity in test_disks_page.py; three new
TestHandlerGuards tests (valid preselection used, empty pool explains and
skips, root pool explains and skips); test_disks_page_dataset_tuning.py
_make_app pins the tuning view; the radio-toggle test patches the sensitivity
update. Docs: gtk-gui.md Actions lead-in explains view-aware bar; Migrate
Pool section documents the refuse-to-open behavior. Full tests/run-tests
green.

2026-09-19 — Fixed GLib warning "expected enumeration type PangoWrapMode, but
got GtkWrapMode instead" seen while opening the Apply Profile dialog: the
Description cell renderer in show_apply_profile_dialog
(python/disks_page.py) set wrap-mode to Gtk.WrapMode.WORD; CellRendererText
requires Pango.WrapMode (Gtk.WrapMode is only valid on Gtk.TextView, whose
set_wrap_mode call sites are unchanged). Now imports Pango and uses
Pango.WrapMode.WORD with an explanatory comment.

2026-09-19 — Apply Profile dialog picker made taller and vertically
resizable (user request): the profile-list scrolled window in
show_apply_profile_dialog (python/disks_page.py) had min_content_height 150
and was packed with expand=False, so only the command preview grew when the
dialog was resized. Now min_content_height is 240 and it packs with
expand=True, so resizing the dialog vertically shares space between the
profile list and the preview (Gtk.Dialog was already user-resizable).
Tests: test_apply_profile_picker_is_tall_and_expands; also fixed
test_apply_profile_picker_description_renderer_wraps, which still asserted
the pre-Pango Gtk.WrapMode and had been missed by the earlier suite run.

2026-09-19 — Moved dataset tuning from Disks page to Datasets page (user
request). New python/profile_dialogs.py holds the Apply Profile picker/preview
(now taking pool_has_special as a parameter instead of reading the Disks-page
pool selector/cache), the profile manager/editor, and Rewrite Data execution;
on_apply_profile/on_rewrite_data take an explicit dataset list and an optional
refresh callback. Datasets page gains Apply Profile… / Rewrite Data /
Advanced: Manage Profiles… buttons (action_dispatch "datasets" spec);
on_datasets_apply_profile collects the tunable tree selection (pool/dataset
rows, filesystem/volume; snapshots/holds/partitions excluded and logged),
computes profile_match once for the first dataset, derives pool_has_special
from ZfsRepository.pool_topology, shows the dialog once, and applies the
chosen profile equally to all selected datasets. Disks page: entire Dataset
Tuning view removed (view switcher now Inventory and Topology + Performance);
apply/rewrite/manage buttons and sensitivity branches removed. Profile store
unchanged; workload_profiles.py notes the future dataset/pool profile split;
ashift remains informational (Migrate Pool rewrites a pool). Tests: new
TestProfileActions in test_datasets_page.py (sensitivity gating, dialog-once
delegation, selection filtering, pool_has_special from repository); the old
test_disks_page_dataset_tuning.py is being migrated to
test_profile_dialogs.py.

2026-09-19 (cont.) — Critical catch during the profile-dialogs move: an
earlier commit had created python/profile_dialogs.py holding the schedule
profile dialogs (show_add_profile_dialog / show_recall_profile_dialog /
_show_profile_scope_warnings), and action_dispatch.py already imported those.
Creating the new workload-profile module by overwriting that file would have
broken every backup/offsite/restore "Add Profile to Schedule" flow (the GUI
would not even import). Restored the three schedule-dialog functions into
the merged module (docstring now covers both families); the test-migration
subagent surfaced the ImportError and it was fixed in scope, so its
PREEXISTING.md entry was removed. Test migration: test_disks_page_dataset_tuning.py
became test_profile_dialogs.py (view-specific and disks-gating tests deleted
as superseded; handler tests call on_apply_profile/on_rewrite_data with
explicit dataset lists); tests/requirements.manifest and testing.md suite
table updated.

2026-09-24 — Development-cycle wrap-up (steps 1-4). (1) Resolved both
PREEXISTING.md entries: documented the 21-char `^[0-9]+([.][0-9]+)?$` regex in
`bin/zfslockmanager _zfslock_sanitize_interval` (pattern, `[.]` rationale,
rejection list); fixed the ruff-format nit in testing.md line 525 and a second
unreported one in tests/python/test_datasets_page.py — `ruff format --check`
and `ruff check` are clean repo-wide. (2) Policy review found 5 violations in
the changeset, all fixed: `_build_rewrite_command` now sources bashinit and
uses log_msg instead of echo (matches the command_builders BashStep pattern;
new test pins it); `_source_layout_changed` docstring summary collapsed to one
line; uppercase non-exported globals in tests/test-zfslockctl lowercased
(`_bg_lock_pid`, `_bg_lock_rcfile`, `_waiter_pid`); single-call-site helpers
gained direct unit tests (new TestVolumeLoopHelpers in test_dataset_actions.py,
TestSourcePoolMemberHelpers in test_pool_migrate_dialogs.py). New pre-existing
entry recorded: tests/test-zfslockmanager has the same uppercase-globals
pattern in committed code, left untouched. shellcheck -S warning clean. (3)
Test review: added missing get_zvol_mount_dir default/env-override tests to
test_paths.py; full tests/run-tests green (73 suites, 0 failed, 1 env skip).
(4) Docs: testing.md bash-suite table gained the test-zfslockctl row and the
duplicated test_profile_dialogs rows were merged; data-structures.md two
"Disks tab Apply Profile" references now say Datasets tab; commands.md
zfslockctl wait section documents the ZFSLOCK_WAIT_INTERVAL fractional/fallback
semantics. modules.md: the user's hand-edited lettered sub-list under
zfs-send-receive was re-indented from 3 to 4 spaces (whitespace only — at 3
spaces Python-Markdown flattens the nested list, which test_docs_integrity
rejects; wording untouched). test_docs_integrity.py: 23 passed.

2026-09-24 (cont.) — Final full run after docs edits: 4 failures, all in
tests/python/test_disk_surface_test.py (Errno 13 on
/run/lock/zfsutilities/.surface_test_state.lock — the directory is now
root-owned drwxr-xr-x, recreated Sep 21). Environment issue per
tests/AGENTS.md rule 4; unrelated to the changeset; recorded in
PREEXISTING.md (2 entries remain: this, and the test-zfslockmanager
uppercase-globals item). Everything else green: 73 suites, 1 env skip,
test_docs_integrity 23/23, ruff check/format clean, shellcheck clean.
