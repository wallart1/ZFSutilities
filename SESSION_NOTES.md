# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves: an entry is
obsolete once its cycle is committed, durable knowledge belongs in `docs/`
or PREEXISTING.md, and only undocumented gotchas and active threads are kept
here. Pruned history remains recoverable from git.

## Persistent gotchas (not documented in docs/)

- The bash test harness (`tests/run-tests`) runs suites **without pipefail**,
  so a failure branch that depends on a pipeline's non-zero exit code cannot
  fire under the harness (e.g. the dry-run estimate-failure branch of
  `zfs-migrate-send`). Tests assert the reachable path instead (the
  "Unable to get stream size estimate" message).
- `tests/test-archive-vm`: `ask_yn` cannot be mocked — sourcing `archive-vm`
  re-runs bashinit via `~/bashinit`, which unconditionally redefines it — so
  dialog answers are fed via stdin in prompt order. With dependent clones
  present, the promote question is the first stdin consumer, before the
  archive-base prompt.
- `docs/docs/commands-and-modules/modules.md`: nested (lettered) sub-lists
  need 4-space indentation; at 3 spaces Python-Markdown flattens the nested
  list, which `test_docs_integrity` rejects.
- `tests/python/test_gui_infrastructure.py` `TestPageAnchorMapping` audits
  `_PAGE_ANCHORS` against the **locally built docs site**
  (`docs/site/…/gtk-gui/index.html`, untracked). Adding a page or changing
  docs anchors requires BOTH updating that test's `expected_pages` set and
  rebuilding the site (`cd docs && mkdocs build`), or the full suite fails.
- bash EXIT traps under `set -e`: any failing statement inside an EXIT-trap
  handler aborts the rest of the handler (run-tests' kill_pytest_tree had to
  `|| true` the kill/wait pair). `append_exit_trap` in `bin/bashinit` is the
  registry to use — never a bare `trap ... EXIT` (it silently clobbers any
  earlier one). Also: bash 5.2 does not fire an EXIT trap armed inside a
  bare `while read` loop that is itself a pipeline segment, and a `&`-
  launched script is SIGINT-immune (POSIX async-subshell SIG_IGN) — use
  SIGTERM to test interruption paths.
- GTK dialog modules: `gi.require_version("Gtk", "3.0")` must run BEFORE
  `from gi.repository import Gtk` — importing Gtk first pins Gdk 4.0 and
  then `gui_helpers`' `gi.require_version("Gdk", "3.0")` raises. Every
  dialog module follows the `import gi` → `require_version` → imports
  order; new ones must too.
- New gi-guarded python suites must be added to `tests/requirements.manifest`
  (`gi tests/python/<suite>.py`) — `test_gui_infrastructure` audits manifest
  ↔ guarded-suite equality and the FULL suite fails otherwise (affected
  suites alone stay green).

## Active / parked threads

- **Zvol-snapshot-mount plan v3 (2026-10-01) — parked, NOT approved.** Plan
  written next to v1/v2 in
  `/NFS1/dan(NFS1)/zfsutilities-plan/Plans in abeyance/Zvol-snapshot-mount/`.
  Base is v2's architecture plus four fixes: (1) the archive-vm guard must
  scan raw discovery output (Pass 1 drops the archived VM's own clones — the
  natural browse-then-archive case); (2) promote-vm-clone marker skip in all
  four awk blocks; (3) migration pre-flight on source AND destination pools
  (receive uses -F); (4) reuse the shipped `parent_type` field + refreshed
  line numbers. Implementation notes: dataset-component-only marker test in
  buildfsarray; wait for the clone's /dev/zvol node before loop_attach.
  Shipped behavior until approved: volume-snapshot mounts rejected with WARN
  + disabled Mount button; no clone-based volume-snapshot mounting (user
  decision).

- **Zensical vs MkDocs evaluation (2026-10-02) — research only, no code
  changed.** User asked whether Zensical (zensical.org, the Material-team
  successor SSG; note spelling, not "Zensicle") can replace MkDocs here.
  Answer: functionally yes at 0.0.67 — verified by pip-installing zensical in
  a scratch venv and building a copy of the real docs: clean build, page set
  identical to mkdocs output (32/32 HTML), build time on par (~7.5 s), and
  the pip install is self-contained (no mkdocs-material needed; classic
  Material theme built in). The two custom hooks are the only functional
  gap, and both have config-only replacements, verified: `hooks:` is silently
  ignored by zensical, so (a) version_stamp.py → `extra.version: !ENV VAR`
  (footer rendered "ZFS Utilities v…"); (b) edit_links.py → `repo_url:
  openmd:/` + `edit_uri: /<abs path>/docs/docs/` yields byte-identical
  openmd:// URIs (MkDocs itself rejects a non-http repo_url, so that config
  becomes zensical-only; side effect: a "Go to repository" header icon
  pointing at the docs dir; the absolute path is machine-specific, unlike the
  hook's dynamic derivation). Mermaid: `<pre class="mermaid">` fences render
  and the mermaid runtime is inlined in bundle.js (not browser-verified).
  pymdownx.details is configured in mkdocs.yml but unused in content (zero
  `???` blocks). If migrating, use `theme.variant: classic` for Material
  look parity. Migration surface beyond docs/: bin/startdocserver (build/
  serve invocations `zensical build --clean` / `zensical serve -a 0.0.0.0:8000`,
  plus exporting the !ENV version), bin/check-prerequisites (mkdocs<2 pin
  logic), lib/installer-lib.sh, share/dev/install-test-deps.sh, and tests/
  {test-startdocserver, test-deploy-version, test-installer-checks,
  test-check-prerequisites, python/test_support.py}. Holding back: still
  0.0.x with releases every few days — expect breaking changes before 1.0.

## Migrate Pool step-structure docs (2026-10-03)
  User asked why the plan snapshots the whole pool but replicates per
  top-level dataset (NVME1's only top-level dataset is proxmox, so one
  Replicate step carries the entire pool; root dataset never travels —
  dest has its own root, holds no user data, properties don't travel).
  Added an explanatory paragraph to the Migrate Pool section of
  docs/docs/user-guide/gtk-gui.md right after the review-page paragraph
  (single-home; no messages-manual duplication, no new headings/anchors).
  Docs build clean (only the known PREEXISTING mkdocs-material banner);
  docs suites green.

## Pool profiles for Create Pool + Migrate Pool (2026-10-03)
  Implemented, all affected suites green; awaiting commit. The
  workload-profile idiom extended to pool scope: named bundles
  {blocksize, curated pool -o properties, root -O properties, notes} in
  config key "pool_profiles" (migration v25→v26 seeds general/archival;
  feature_config quintet + DEFAULT_POOL_PROFILES). New pure module
  python/pool_profiles.py (resolve_blocksize sentinels: recommended/auto/
  512|4096|8192 bytes → ashift 9/12/13; origin_profile() builds the
  never-saved "Match origin pool" pseudo-profile; infra_vdev_classes() for
  the not-recreated warning). zfs_repository.build_create_pool_command
  gained pool_options=[(prop,value)] emitted as -o (validated against
  POOL_PROPERTY_VALUES) + curated_pool_properties() reader. Create Pool
  settings page: profile picker + blocksize pre-filled from profile
  (switching profiles re-applies its blocksize unless user set it —
  state.blocksize_user_set/blocksize_syncing guard against re-entrant
  combo handlers); pool_create.pool_filesystem_options REMOVED
  (superseded). Migrate Pool: "New pool settings" section with Match
  origin default (origin ashift + curated props + root live props via
  _apply_origin_defaults), topology radio defaults to origin shape,
  both create-step call sites thread ashift + both option lists; create
  steps now say "(raidz2, 4096-byte blocks)"; below-recommendation and
  infra-vdev warnings in _migrate_warnings; post-cutover INFO reminder
  to re-add infra vdevs. New pool_profile_dialogs.py manager/editor
  (same built-in rules as workload profiles; pool props are combos from
  allowed values + "(not set)", fs props free text) wired as Disks-page
  "Advanced: Manage Pool Profiles…" (handler in disks_page.py per the
  page-module convention; button registered with attr None = always
  enabled, not in update_disks_button_sensitivity). Gotchas: gi import
  order — `gi.require_version("Gtk", "3.0")` must precede
  `from gi.repository import Gtk` or gui_helpers' Gdk pin fails;
  TopologyNode requires ashift AND children positionally in tests.
  PREEXISTING: ashift-picker entry CLOSED; pool-props and infra-vdev
  entries NARROWED (curated-seven + root props now travel; non-curated
  pool props still dropped; infra planning UI still absent); new entry
  for python-modules.md's duplicate `### profile_dialogs.py` headings
  (anchor collision). 5 entries remain open total. Full suite green after
  adding test_pool_profile_dialogs to tests/requirements.manifest (gi audit
  caught it — gotcha promoted above) and testing.md suite rows.

## Wrap-up cycle 2026-10-03 (pre-commit steps 1-4)
  Step 1 (PREEXISTING resolution): preflight long line wrapped;
  python-modules.md duplicate `### profile_dialogs.py` heading
  disambiguated (schedule add/recall dialogs) — both entries removed.
  Migration-fidelity gaps closed: (a) non-default pool properties now
  travel — new zfs_repository.build_pool_set_command() +
  pool_properties_with_source() reader (`zpool get -H -o
  property,value,source all`), pool_profiles.replayable_pool_properties()
  (SOURCE=local, minus feature@*, ashift/altroot/cachefile/version, minus
  curated seven so saved profiles are never clobbered); Migrate dialog
  gains a "Non-default pool properties" frame (CheckButton + wrapped
  value label per prop, explanatory hint per user request; rebuilt on
  source change via _rebuild_props_section), MigrationRequest.
  replay_pool_props, plan kind STEP_REAPPLY_POOL_PROPS (after
  import-rename, before holds reapply, both modes), executor steps
  fatal=False (data already migrated; refused prop logged not fatal).
  (b) holding-mode silent absorption fixed — pool_profiles.
  data_vdev_leaves(); _source_pool_data_member_disks() drives preselect;
  _holding_member_rows() labels ex-infra rows "former <cls> vdev member"
  (still eligible; ticking = deliberate choice); holding-mode infra
  warning extended. Infra-vdev PLANNING itself deferred as a future
  objective (user decision 2026-10-03) — PREEXISTING entry rewritten as
  such; 2 entries remain (mkdocs/Zensical + the future objective).
  Step 2 (standards): ruff check+format clean python/ + tests/python/;
  shellcheck clean via the documented command (.shellcheckrc already
  excludes bin/watchall — a naive `for f in bin/*` loop false-positives
  on it); manual review of the whole uncommitted python changeset found
  no violations, no new pre-existing issues. Step 3 (tests): coverage
  gap found and filled — build_create_pool_command pool_options had no
  direct tests (golden + two ValueError cases); replay/data-leaves/
  member-rows/origin-defaults/warnings/build-steps tests added across
  four suites; apply-holds script body says reapplyholds_apply (NOT
  replayholds_apply) — docstring-name trap. Full suite: 77 suites
  green, 1 skip = soak suite by design. Step 4 (docs): messages index
  row for the new property-read WARN; gtk-gui Migrate Pool paragraphs
  (checkbox semantics + unchecked ex-infra disks); python-modules and
  data-structures rows for the new functions; integrity suite green.

## Memory-tab fix 2026-10-03: SLOG/L2ARC device-table rates always zero
  Root cause: plain `zpool iostat -v` prints per-second averages SINCE
  BOOT, not cumulative totals (verified on stewie against
  /proc/spl/kstat/zfs/<pool>/iostats: 1,042,744 total read ops vs "23"
  displayed). memory_stats treated them as cumulative counters and
  delta'd near-constant averages -> ~0/s in the device tables while the
  kstat-derived labels above the charts were correct. Fix: interval-mode
  collection `zpool iostat -v -y 1 1` (user pointed at -y; verified:
  single per-interval report after one full 1-second window, count
  counts interval reports only), one no-`-y` fallback attempt
  (`-v 1 2` + parser keeps the LAST report per (pool,vdev)) for pre-0.8
  zpool; VdevSample ops/byte fields renamed to *_ps/*_bps (per-window
  rates, not cumulative); compute_rates passes vdev rows through from
  the current sample (live on first refresh now) while kstat rates stay
  arcstat-style deltas. Collection blocks ~1s but already runs off-thread
  behind the _memory_refresh_pending guard. Docs: gtk-gui data-source
  table + rates paragraph + L2ARC bullet, data-structures field rows +
  compute_rates paragraph, python-modules key-function rows. No new
  PREEXISTING items (2 remain open).

## Disks-page all-pools topology 2026-10-03
  Pool Topology pane now always shows every imported pool as a top-level
  row (was: only the drop-down-selected pool, rebuilt per selection).
  Expansion is rule-driven (_apply_topology_expansion): a pool expands
  fully when it is the selector's pool, holds the topology selection, or
  contains a teal-tinted device; otherwise collapsed. Selecting an
  inventory disk/partition in NO pool now clears the whole topology state
  (tints + selector set_active(-1) + collapse); refresh preserves that
  deliberately-cleared selector (active -1 with previously non-empty
  model) instead of snapping to pool 0 every 30s. Selector moved into the
  Pool Topology section under its title (user request; was above the view
  stack) and repurposed: follows inventory-disk pool and topology-node
  pool; growth/migrate/Proxmox dialogs preselect from it unchanged.
  Topology-node selection now also sets the selector to its containing
  pool. _on_pool_selector_changed no longer rebuilds the store (highlight
  + expansion only). GOTCHA that cost two host hangs + a reboot: dialog
  suites (growth/migrate/create-wizard) reach refresh_disks_page
  transitively via FakeDatasetRunner.finish() completion callbacks, and
  their fixtures mocked disks_topology_store as bare MagicMock — the new
  store walk (while it: iter_next) never terminates on MagicMock and
  call-history recording grows without bound (RAM+swap full, box hung;
  cancelled Bash runs leave orphaned pytest trees — always pgrep after a
  kill). Fix: _NestedTreeStore/_TreeIter fakes + FakeTreeView
  expand_row/collapse_row + selector get_model list in all three suites.
  Peak RSS now ~82MB, 141+167 dialog tests green.

## Isolated test lock dir 2026-10-03 (PREEXISTING fix)
  tests/python/conftest.py now redirects ZFSUTILITIES_LOCK_DIR (only when
  unset; explicit exports respected) to a per-process mkdtemp cleaned by
  atexit — python tests never touch /run/lock/zfsutilities again, whatever
  its ownership or live holders. file_locking/cron_manager/feature_config
  bind lock paths at import time, and conftest loads before test modules,
  so the redirect reaches all import-time bindings; xdist workers each get
  their own dir. Default-literal assertions updated: test_paths (2 tests,
  patch_environ LOCK_DIR=None), test_file_locking TestLockPathDefaults
  (reload-under-cleared-env contextmanager, restore-reload in finally),
  test_cron_manager test_basic (assertIn(cron_manager.PROFILE_LOCK_DIR)),
  test_dashboard untouched (its literals are parser INPUT, not output);
  removed test_disk_surface_test's now-redundant per-suite workaround (the
  origin pattern for this fix). Verified against a simulated unwritable
  /run/lock/zfsutilities (mkdir + chmod 555): all four originally-failing
  tests + touched suites green; zero /tmp leftovers after runs. Full-suite
  check found ONE residual writer: tests/test-zfsdailybackup sources
  zfsdailybackup -> zfssnapbuild, whose SNAPNAME_LOCK/SNAPNAME_RESERVED
  env-default to /run/lock/zfsutilities (bash reads those vars, NOT
  ZFSUTILITIES_LOCK_DIR — python conftest redirect can't reach it; the
  recreated-dir mechanism from the original incident confirmed live: a
  uid1000 full suite had recreated the dir with the snapname pair, and a
  root-run suite would leave it root-owned). Fixed in tests/test-lib.sh
  bootstrap: default-only SNAPNAME_LOCK/SNAPNAME_RESERVED exports to
  $$-suffixed /tmp paths (explicit suite overrides still win —
  test-zfssnapbuild's own exports unaffected) + rm in _test_lib_cleanup;
  shellcheck clean. Both suites verified: pass, host dir not created,
  zero /tmp leftovers. PREEXISTING entry removed (2 remain open).
  AMENDMENT (same task, later finding): second residual writer found via
  full-suite re-check + strace: test-zfsdelsnap -> zfsdelsnap sources the
  REAL bin/zfsconfig, whose _zfsconfig_lock_file does mkdir -p
  "$ZFSLOCK_DIR" (ZFSLOCK_DIR -> ZFSUTILITIES_LOCK_DIR ->
  /run/lock/zfsutilities) — created the host dir EMPTY (flock path
  mocked/short-circuited downstream). mkdir -p's chdir-dance makes the
  mkdir look RELATIVE and invisible to bash -x greps; strace -f -e
  execve,mkdir is the tool for this. Final design in tests/test-lib.sh
  bootstrap: ONE per-suite location /tmp/zfsutilities-test-lockdir-$$
  (flat $$ name, stable across re-sourced subshells — no
  mktemp-on-resource litter) exported as ZFSUTILITIES_LOCK_DIR +
  ZFSLOCK_DIR + SNAPNAME_LOCK/SNAPNAME_RESERVED defaults (explicit suite
  overrides still win: test-zfsconfig/test-zfslockctl/test-archive-vm/
  test-zfssnapbuild unaffected); _test_lib_cleanup rm -rf's the dir.
  tests/test-paths (bash) default assertions now re-source lib/paths.sh
  in a subshell with ZFSUTILITIES_LOCK_DIR and PROFILE_LOCK_DIR cleared
  (PROFILE binds separately at source time — unsetting only the base is
  not enough). Verified: writer suite + overriders + test-paths green,
  host dir not created, zero /tmp leftovers, shellcheck clean.

## CI fix 2026-10-03: install-test-deps.sh missing python3-gi-cairo
  GitHub Actions `tests` runs failed on main push + v0.112.0 tag
  (265b33c): ModuleNotFoundError 'cairo' at python/memory_page.py:19
  (module-level import, Memory-tab RollingChart), cascading to 27 failed
  + 67 errors across every suite that imports action_dispatch/memory_page
  (test_action_dispatch collection, profile/pool-profile dialogs,
  test_zfsutilities_gui timers/sidebar/terminate classes). Root cause:
  share/dev/install-test-deps.sh installs python3-gi + gir1.2-gtk-3.0 but
  not python3-gi-cairo; dev host has python3-cairo 1.25.1 +
  python3-gi-cairo 3.48.2 from the desktop GTK stack, so the 0.112.0
  wrap-up full suite was green locally and the gap only surfaced in CI.
  Docs were already correct — developer-guide/index.md GUI deps list
  python3-gi-cairo; the script never matched it. Fix: one line, add
  python3-gi-cairo to the apt install list (hard-depends on
  python3-cairo, pulling it in; also feeds .devcontainer/Dockerfile via
  the same script). Gotcha for the future: a new GUI dependency is green
  locally whenever the dev desktop stack happens to provide it — diff the
  install script against the dev-guide dependency list when adding GUI
  imports. 0.113.0 (a4c60a4) is still unpushed; fix should ride on main
  before that push. v0.112.0 tag run stays red in history (published
  release, not re-tagged).

## Datasets page 2026-10-03: on-page legend for the teal tint
  User request: explain the teal text on the Datasets page in the GUI
  itself (it was only documented in gtk-gui.md). Added a bottom summary
  row in create_datasets_page: dataset count left, new
  app.datasets_legend_label right — small-italic caption "Teal text —
  unmounted filesystem or snapshot" whose colored span reuses
  UNMOUNTED_FG from gui_helpers (stays in sync with _row_fg_color's
  tint, no hard-coded hex). Tests: legend widget existence + exact
  markup assertion in test_datasets_page.py. Gotcha re-confirmed:
  mock_gtk shares one Label mock across widgets AND tests, so
  set_markup call-count/last-call assertions are unreliable — assert
  the exact expected markup is present in call_args_list instead.
  Docs: one clause added to the teal paragraph in gtk-gui.md (file also
  carries the user's hand edits — left untouched). Awaiting commit.

## Memory→Performance rename + Disks view-switcher removal (2026-10-03)
  User request: rename the Memory page to "Performance" and remove the
  Performance radio button/view from the Disks page. Visible rename only:
  PAGE_BUILDERS title, on-page <big><b> title, _PAGE_ANCHORS
  memory→"performance-tab" (docs heading "Performance Tab"), docstrings,
  docs wording (gtk-gui Tabs table + section, python-modules,
  data-structures, messages index "ran on the Performance page").
  Internal identifiers KEPT by design: stack key "memory", module
  memory_page.py, config key memory.refresh_seconds (persisted in user
  configs — renaming would orphan them); log line "INFO: Memory stats
  refreshed" stays (it reports memory stats, still accurate).
  Disks page: whole view-switcher architecture removed — radio row +
  separator, Gtk.Stack wrapper (inventory_box now packs into page_box
  directly), Performance placeholder, _on_view_radio_toggled,
  _DISKS_VIEWS/_current_disks_view, inventory_active gating and the
  "Switch to the Inventory and Topology view…" tooltips in
  update_disks_button_sensitivity (gating is now compute-host →
  runner-busy → selection). Docs site rebuilt for the anchor test
  (gotcha above). test_disks_page: view-switcher test replaced with
  has_no_view_switcher (RadioButton/Stack assert_not_called), radio
  tests + TestViewScopedButtonSensitivity deleted, selector-host test
  re-identifies page_box as the box that packs hosts[0] (stack anchor
  gone). Awaiting commit.

## Datasets page 2026-10-03: mount/unmount confirmations demoted to VERB
  User flagged two production log lines (0.97.0 dataset_actions) —
  "INFO: Mounted/Unmounted snapshot ..." — as VERB-level noise. Scope
  user-selected: datasets + snapshots (6 messages: Mounted {target},
  Mounted/Unmounted snapshot, Unmounted {dataset}/{target} x3 incl.
  post-orphaned-recovery) now VERB:; zvol loop-mount family and the
  "Remounted ... to recover orphaned mount" notice stay INFO by design.
  Messages-manual dataset_actions section: 2 rows retitled VERB, plus 2
  previously-missing rows added (dataset Mounted/Unmounted success was
  undocumented). Loop-partition test assertions intentionally untouched
  (test_dataset_actions 2145/2250/2470/2530). Awaiting commit.

## FATAL for premature task termination (2026-10-03)
  User flagged three production WARN lines (0.97.0: backup_runner "Step
  exited with rc=2", dataset_actions unmount "no such pool or dataset",
  offsite_page "No offsite pool online.") — the tasks were prematurely
  terminated, so they should be FATAL; "or, instead, the tasks
  themselves should issue the FATAL: message, not the runners."
  Design (user-approved "hybrid"): a message that IS the termination
  record promotes to FATAL in place; step-failure detail stays WARN and
  the abort decision logs a task-level FATAL (mirroring the GUI
  backup_runner's existing "FATAL: Aborting ... because step failed"
  and the bash scripts, which already log FATAL + exit 8 for
  no-offsite-pool). Applied: profile_runner (no-pool, lock-conflict
  rc=9, validation aborts incl. scrub no-pools, unknown tab type,
  scrub gave-up; NEW "FATAL: Aborting run/restore because step failed"
  and per-pool "FATAL: Prune of X failed (rc=N)" — retention loop
  deliberately continues to other pools), offsite_page (no-pool,
  no-active-steps), dataset_actions unmount family (all failure
  branches promoted; busy-dialog paths gained "X is busy; unmount
  aborted" FATAL lines — previously dialog-only, no log trace).
  Deliberate WARN survivors: retention <offsite> skips (both modules),
  duplicate-invocation skip, non-fatal step continues, "Could not list
  descendants" degrade path, scrub timeout (rc=0 oddity recorded in
  PREEXISTING.md), post-backup script rc. backup_runner GUI levels
  unchanged; its _runner_log now resolves the issuer via
  _issuer_log_location (skips wrapper frames) so file:line prefixes
  name the real call site — the user's ghost "backup_runner.py:183"
  was the wrapper's log_msg call line. Messages manual: offsite_page,
  dataset_actions, profile_runner sections updated (promoted rows +
  5 new rows). User also observed the runner/logging internals "seem
  unreasonably complicated" and it "may be time for another
  restructure in this area" — noted as a future thread, not acted on.
  Awaiting commit.

## Wrap-up cycle 2026-10-04
  Step 1 (PREEXISTING): scrub-profile timeout-with-paused-pools rc
  semantics DECIDED by user: keep rc=0 (timeout with only paused pools
  remains a successful run); entry removed from PREEXISTING.md — the
  WARN at profile_runner.py:727 stays WARN and the rc is now decided,
  documented behavior, not an open issue. Zensical waiting condition
  rechecked: PyPI latest is still 0.0.67, no 1.x — toolchain entry
  stays. Infra-vdev planning UI stays in abeyance (user decision
  2026-10-03). 2 entries remain.
  Step 2 (standards): ruff check + format clean (154 files), shellcheck
  clean via the documented command; manual policy review of the whole
  uncommitted changeset found no violations (helper call-site rules,
  regex-documentation rule, log-level prefixes, no site-specific data,
  test-lib cleanup rm -rf safety verified against all lock-var
  overriders). Doc inaccuracy found: coding-policies.md said log_msg
  comes from backup_config — it is defined in logging_config and
  re-exported; fixed in step 4. No new PREEXISTING items.
  Step 3 (tests): coverage verified across all 8 features; one missing
  test added — scrub profile timeout-with-paused-pools pins WARN + rc=0
  (today's decision) in test_profile_runner.py; all touched python
  suites green; bash test-paths green with zero lock-dir litter; gating
  coverage confirmed intact in test_disks_page_growth_buttons (never
  lived in test_disks_page).
  Step 4 (docs): all four doc diffs reviewed against code (messages
  index rows match actual strings incl. the retained timeout WARN;
  VdevSample field rows; disks_page/memory sections; gtk-gui anchors);
  coding-policies log_msg wording fixed (2 spots); changelog historical
  Memory-tab/view-switcher mentions left as history; docs integrity 23
  passed; site rebuilt clean (only the known PREEXISTING mkdocs banner),
  performance-tab anchors verified live, zero stale memory-tab refs.
  Step 5 (full suite, background, no soaks): 77 suites green
  (4,194 passed, 0 failed, 1 skip = soak suite by design), rc=0. Three
  non-soak suites over the runner's 5s advisory budget
  (send-receive-dryrun 9.7s, zfslockmanager 7.6s, archive-vm 6.5s) —
  advisory timing notes only, all passing; not recorded as PREEXISTING.
  Post-run checks: no orphaned pytest trees, /run/lock/zfsutilities not
  created, this run left zero /tmp litter (two EMPTY 0-byte logs from
  2026-10-03 14:40 — stale litter from an earlier session's cancelled
  runs — were removed by hand). CODEBASE FROZEN at this point.
  Wrap-up totals: 1 PREEXISTING issue resolved by decision (scrub rc=0
  stays; entry removed, test added to pin it), 2 entries remain; 1 test
  added (timeout-with-paused-pools); 1 doc inaccuracy fixed
  (coding-policies log_msg source); docs site rebuilt.

## Release 0.114.0 (2026-10-04)
  Step 7: VERSION bumped to 0.114.0; changelog entry written (Added:
  all-pools topology + datasets legend; Changed: Performance rename,
  view-switcher removal, FATAL/VERB policy; Fixed: device rates, CI
  python3-gi-cairo, test lock-dir isolation). All __pycache__ dirs
  removed; docs site rebuilt (0.114.0 stamp verified). Final full suite
  WITH soaks: 77 suites, 0 failed, 0 skipped (soak's 7 tests ran), rc=0.
  Codebase frozen; no further code changes this session.
