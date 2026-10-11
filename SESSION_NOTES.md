# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves: an entry is
obsolete once its cycle is committed, durable knowledge belongs in `docs/`
or PREEXISTING.md, and only undocumented gotchas and active threads are kept
here. Pruned history remains recoverable from git.

## Persistent gotchas (not documented in docs/)

- Backslash line-joins keep the continuation line's indent, so
  `"arg-part-a" \` + indented `"part-b"` becomes **two arguments**, not
  one concatenated string — for one-argument payloads (ssh command
  strings, sed programs) build them in a variable with `+=`.  Inside
  unquoted heredocs, `\`+newline joins with the indent intact, so
  source-wrapping payload lines only ever changes inter-word spaces.
  When verifying a heredoc edit by extraction, aim at the RIGHT block
  (files can hold several with the same marker) and keep `<<MARKER` in
  the opener, or the "payload" executes as live script (a `cd /root` +
  `set -e` block aborts harmlessly as non-root, but the check is
  vacuous — 0 rendered lines means the check proved nothing).
- The bash test harness (`tests/run-tests`) runs suites **without pipefail**,
  so a failure branch that depends on a pipeline's non-zero exit code cannot
  fire under the harness (e.g. the dry-run estimate-failure branch of
  `zfs-migrate-send`). Tests assert the reachable path instead (the
  "Unable to get stream size estimate" message).
- `tests/test-archive-vm`: `ask_yn` cannot be mocked — sourcing `archive-vm`
  re-runs bashinit via `~/bashinit`, which unconditionally redefines it — so
  dialog answers are fed via stdin in prompt order. With dependent clones
  present, the severance question is the first stdin consumer, before the
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

## Integrated testing environment — master plan approved, Phase 0 complete (2026-10-04)
Master plan formally approved: end-user-simulator orchestrator under
`tests/integrated/` (journeys, not suites, in guests; CLI + GUI smoke;
release tarballs + dev tarballs; findings FINDINGS.md + in-repo
repair-plans with approval gates; zfsutilities-plan/ is user-only).
Base VM access verified (dan + passwordless sudo on both). Phase 0
inventory done — artifacts in `tests/integrated/results/phase0/`
(PHASE0-REPORT.md + raw outputs): both base VMs clean PVE 9.2 on
trixie, 4 vCPU, 3.8G RAM, 14.7G local-lvm, no VMs; nested virt already
works (vmx + kvm_intel — no host CPU change needed). Resource request +
manual steps delivered: zfstestvm1 RAM→12G, +200G second disk (itfiso
20G ext4 + itfguests lvmthin, storage.cfg entries by user), vmbr9
10.200.0.1/24 isolated bridge + NAT systemd unit, dev route
10.200.0.0/24 via 10.0.0.28, optional dist-upgrade (183 pkgs pending,
9.2.2 vs vm2's 9.2.21). Confinement: VMIDs 8000–8099, storages
itfguests/itfiso only, append-only /var/log/itf-actions.log audit.
Awaiting user's resource application; Phase 1 (itf MVP) is next and
independent of it.

Phase 0 execution wrap (same day, user delegated 3b/3c "pick it up
from here"): 3a landed (11G RAM, 6 vCPU, 200G /dev/sdb). GOTCHAS hit:
(1) in-place 9.2.2→9.2.21 dist-upgrade under OVMF+pre-enrolled-keys
Secure Boot → shim "ERROR Verification failed: (0x1A) Security
Violation" at boot (vm2 was fine because installed from newer media);
user fixed by switching the VM BIOS to SeaBIOS — PVE installs carry a
BIOS-boot partition alongside the ESP, so SeaBIOS boots the same disk.
(2) pve-manager was stuck at 9.2.2 because vm1's apt had enterprise
repos active and NO no-subscription file (trixie deb822 .sources under
/etc/apt/sources.list.d/ — plain `^deb` grep sees nothing); fixed by
mirroring vm2's layout: `Enabled: false` on pve-enterprise+ceph
stanzas, new proxmox.sources with pve-no-subscription. (3) PVE
storage.cfg SectionConfig requires a BLANK LINE before each new
section — appending `dir: itfiso` directly after the last section's
final line silently swallows it into the previous section (itfguests
parsed, itfiso did not); rewrote the file with blank-line separation
(backup: storage.cfg.bak-itf). (4) parted is not in minimal PVE —
install it. DONE and verified: 9.2.21/kernel 7.0.14, itfiso (19.5G
dir) + itfguests (170.8G lvmthin) active, vmbr9 10.200.0.1/24,
ip_forward=1 + persistent itf-nat.service MASQUERADE (excludes
10.0.0.0/16), /var/log/itf-actions.log, vmbr0 untouched. REMAINING
(user, root on dev): `sudo ip route add 10.200.0.0/24 via 10.0.0.28` +
NM persistence (`nmcli connection modify "Wired connection 1"
+ipv4.routes "10.200.0.0/24 10.0.0.28"`); dev has NO passwordless
sudo for dan.

NETWORK MODEL CORRECTED (user clarification, same evening): vmbr9 is
NOT a general guest network — it is the future **iSCSI point-to-point
link** for the two-node cycle (production parity: physical storage
interconnect). ALL other traffic (management ssh, preseed HTTP,
downloads) runs on the regular LAN: guests attach to vmbr0 and take
DHCP from 10.0.0.1. Applied: removed itf-nat.service + forwarding
sysctl + rule (verified clean); vmbr9 demoted to `inet manual` pure L2
bridge (no address); dev route NEVER needed. Guest IP discovery via
qemu guest agent (`qm guest cmd <vmid> network-get-interfaces`),
agent installed by preseed. Cycle-2 open point: cross-base-VM
point-to-point emulation (VLAN vs private subnet on vmbr0 L2) —
decide at cycle-2 planning. Phase 0 now has ZERO outstanding user
actions; preflight expectations updated (no route/NAT checks; vmbr0
DHCP model).

Phase 1 COMPLETE (2026-10-04, later same day): itf orchestrator MVP
built under `tests/integrated/`. Files: `itf` driver CLI (preflight,
guest create/start/stop/destroy/snapshot/rollback/ip/wait-ssh/list, iso
fetch/upload, journey list/run, status, manual-steps, version; usage is
parsed from the header comment `sed -n '/^Usage:/,$p'` — keep header
contiguous), `lib/config-lib.sh` (fail-closed site config; ITF_SITE_CONFIG
override; all-problems-at-once validation; ISO name must start `itf-`),
`lib/ssh-lib.sh` (base=ssh+sudo -n, guest=root ssh direct, dev HTTP
server for preseed, itf_dev_ip), `lib/base-lib.sh` THE GUARD (qm verb
allow-lists read vs mutate; every standalone numeric token=VMID in range
(except after `-`-prefixed option tokens); `storage:payload` tokens
must name itf storages with slash-free payloads; `--opt=value` value
part checked too; absolute paths only under ITF_ISO_DIR; mutate verbs
audit-logged BEFORE exec via append-only log; itf_read exact+prefix
allow-list — and it RE-QUOTES args per-token `%q` so the inner
`bash -c` on the base can't misparse metacharacters like `(vmx|svm)`),
`lib/guest-lib.sh` (SeaBIOS+virtio-scsi+serial0/vga serial0 guest
recipe — required for `qm terminal` installs; vmid pick from free range;
DHCP IP via guest agent; ISO fetch ≥50MiB sanity + guarded upload via
/tmp stage + `mv`; full Debian preseed: root locked/key-only, no user,
serial console GRUB cmdline, openssh+qemu-guest-agent, late_command
authorized_keys), `lib/report-lib.sh` (run dirs with steps.tsv/report.md,
counters RESET per itf_report_init — was missing, caught by suite),
`lib/serial_console.py` (python3-stdlib expect-replacement over
`ssh -tt … qm terminal`; chosen because dev lacks `expect` and dan has
no sudo to install it; ruff-clean, context-manager log). Site config:
`site/config.example` uses REPLACE-ME placeholders that are
schema-valid-but-unusable (`.invalid` domain, reserved TLD) so a copy
loads but an unedited copy fails loudly at connect/download — the
committed example is asserted to PASS validation by test suite.
Supporting: FINDINGS.md (status flow open→planned→fixed→verified/accepted),
README.md + journeys/README.md (journey contract) + repair-plans/README.md
(approval-gate loop), .gitignore adds site/config, results/run-*/,
cache/ — but NOT results/ itself because results/phase0/ is the committed
Phase-0 report. Tests: tests/test-itf-config (7), test-itf-base-guard
(17), test-itf-report (11) — all green via run-tests; guard suite
overrides itf_base_exec as capture (never ssh). BUGS the suites caught
in the libs (all fixed): (1) itf_qm_check had INVERTED return semantics
(ok=1 on pass) — valid calls were refused AND refused calls would have
EXECUTED; (2) `${#arr[@]:-0}` is bad substitution in bash → use
`${arr[*]:-}`; (3) itf_read raw `$*` shipping metacharacters to inner
bash -c. TEST GOTCHA: command substitution `out=$(itf_step …)` runs in
a subshell — counter/capture assertions must use `> file` redirection
instead (hit twice). shellcheck documented command EXTENDED (coding-
policies.md) with `tests/integrated/itf tests/integrated/lib/*.sh`;
clean at -S warning; ruff clean. Docs: new developer-guide/integrated-
testing.md + nav after Testing + testing.md cross-link section +
mkdocs rebuild (site build rc=0, docs integrity 23 + docserver 15
green). Full suite run at wrap. Phase 2 next: J01–J03 journeys; FIRST
live verification of preseed/serial-install against the real ISO is the
Phase-2 kickoff activity (boot-cmd tuning may be needed); Debian
netinst ISO URL goes in the real site/config (user or agent fetch —
cdimage.debian.org current stable netinst).

## Phase 2 — J01 live bring-up: serial-install debugging saga (2026-10-04/05)

J01 run live against the real base VM (zfstestvm1) — the serial-install
pipeline needed seven hardening passes; each failure mode was diagnosed
from the unbuffered serial transcript + http.log + qm counters:

1. ATTEMPT 1 (run-220803): a MANUAL debug http.server I left on :8000
   (serving /tmp/itf-httpcheck) silently shadowed every journey serve —
   python http.server bind failure is INVISIBLE if you discard its
   stderr; itf_http_serve wrote a pidfile for a dead process and said
   "serving". Guest got 404 → d-i fell back interactive → sat at
   hostname prompt (diskwrite 0 = installer waiting on input).
   FIXES: itf_http_serve now fails loudly (kill-0 + marker-file GET
   readiness probe; busy/stale-pidfile/loopback-shadow handling; log to
   <pidfile>.log); journey gained a "preseed URL serves" fetch gate +
   "preseed fetched by guest" http.log gate (127.0.0.1 GETs excluded).
2. Driver FALSE-PASS: serial_console.py rc 0 on EOF-after-steps —
   "install ran to completion" was a lie. rc semantics redefined:
   0 = --exit-after pattern matched (checked every iteration, against
   the full buffer, valid even with prompt-answer steps pending);
   2 = ended with steps incomplete; 4 = steps done but ended without
   the pattern (EOF/timeout); exit-reason note written to the log.
3. ATTEMPT 3: hostname prompt STILL appeared with the preseed fetched —
   network preseed loads AFTER network config, and hostname is asked
   DURING it; auto=true does not default it (no DHCP host-name on the
   LAN). FIX: hostname/domain/interface now also on the KERNEL BOOT
   LINE (applies at every stage); driver's 3rd step answers the prompt
   anyway via new --step-timeout (skip-if-not-seen in 120s).
4. Root password prompt: preseed had `passwd/root-password-crypted
   string !` — wrong debconf TYPE (string); then `password !` — trixie
   user-setup ignores the "!" lock and prompts anyway. FIX: random
   never-recorded SHA-512 hash per render (openssl passwd -6); root SSH
   stays key-only (sshd default PermitRootLogin prohibit-password).
5. ATTEMPT 4: serial TYPING GARBAGE — boot-line echo showed "auto=truel="
   (" url" swallowed) → kernel got garbage → interactive language menu.
   One-shot writes to the serial can drop chars. FIX: send_bytes()
   paced writes (--send-chunk 16, --chunk-delay 0.08).
6. ATTEMPT 6 (run-232014): got furthest (partman→base system→
   "Configuring apt"), then d-i WEDGED — UI clock stopped ticking,
   disk counters frozen, 1.5GB written. Not a dialog; suspected
   apt-setup fetch hang / newt-screen death under nested virt.
   Strict gate worked as designed (timeout rc=4 → journey FAIL).
   Also pre-emptively added `grub-installer/bootdev /dev/sda` (two
   disks present would prompt for the GRUB device) and raised the
   serial driver timeout 1800→3600s (nested-virt installs are slow).
7. ATTEMPT 7 launched with all of the above — monitoring.

Tests: new tests/test-itf-ssh (4 tests: serve/fetch/stop round-trip
incl. second-serve refusal; busy 0.0.0.0 port; loopback-shadow
squatter; stale pidfile) — caught that a bare-connect readiness probe
is insufficient (SO_REUSEADDR lets specific+wildcard binds coexist;
readiness must GET our own marker file). Suite green; shellcheck/ruff
clean. Bash gotcha: `var=$(...) 2>/dev/null` does NOT silence stderr
from inside the substitution on this bash — put the redirect INSIDE.

### Phase 2 addendum — custom boot ISO + installer syslog (2026-10-05)

Attempts 7-10 outcomes: (7) boot line garbled AGAIN ("auto=tr") despite
paced 16-byte/80ms writes — the qm-terminal→ISOLINUX serial input path
is fundamentally lossy under nested virt; each garble costs a full
reinstall. DECISION: stop typing entirely — itf_iso_customize() (guest-
lib) builds a custom boot ISO per journey: 7z-extract the cached netinst,
replace isolinux/isolinux.cfg (SERIAL 0 115200, PROMPT 0, TIMEOUT 20,
default label with our full kernel APPEND incl. hostname/domain/
interface + console=ttyS0), rebuild with genisoimage (dev has 7z +
genisoimage; xorriso absent). Constant remote name itf-boot.iso on
itfiso (overwritten; .append stamp skips rebuilds). Journey serial step
is now WATCH-ONLY (driver --wait/--send made optional; exit-pattern is
the success gate). Attempt 8 fail: customize printed info lines to
STDOUT which the journey's $(...) folded into the ide2 volid — the
confinement guard correctly REFUSED the create (info now goes to
stderr; only the ISO name on stdout). Attempt 9/11 boot the custom ISO:
auto-boot + preseed fetch ~60s after resume — zero keystrokes. (9)
wedged at "Configuring apt" (deterministic, 2/2 preseeded runs, kvm
0.5% cpu, zero guest packets, zero disk — a hard block inside d-i).
ADDED for visibility: d-i `log=<base-ip>` boot param + itf_syslog_start/
stop (socat UDP-514 listener on the base as root, per-vmid /tmp log,
pulled back as installer-syslog.log artifact; hostname -I added to the
itf_read allow-list). Bash gotchas: `local` declarations must precede
first use under set -u (base_ip: unbound at boot_append); `exec 3<>/
dev/tcp/... 2>/dev/null` does NOT silence the connect diagnostic — the
redirect applies left-to-right, so wrap the group: `{ exec 3<>...; }
2>/dev/null`.

### Phase 2 addendum 2 — the "wedge" was a dialog; install reaches completion (2026-10-05)

Attempt 15 caught the wedge ON SCREEN: it is apt-cdrom-setup's "Scan
extra installation media?" modal — NOT a hang. Deterministic because the
preseed never answered it; the ticking d-i status clock made it look
alive while three runs sat forever at a yes/no box. Fixes landed in
itf_preseed_render: apt-setup/cdrom/set-first|set-next|set-double false.
Attempt 16 then sailed through media scan into a NEW modal — "HTTP
proxy information" (mirror/country=manual drives the explicit mirror
flow). Fixes: mirror/http/proxy preseeded BLANK + the apt-setup battery
(services-select security,updates; non-free-firmware true; non-free/
contrib false). Attempt 17: FULL unattended install, driver exit rc 0
at the finishing reboot, preseed GET gate green.

Syslog capture now works end-to-end: the d-i kernel parameter is
`log_host=<ip>` (NOT `log=`) — verified in the initrd itself
(lib/debian-installer-startup.d/S10syslog parses log_host=/log_port=
into busybox syslogd -R; extract initrd via 7z + zcat|cpio -idm).
Attempt 17 captured 3,054 lines (installer-syslog.log artifact).
Dev→base UDP leg validated with a cross-test datagram; listener round
trip validated via itf_syslog_start/stop against zfstestvm1.

Attempt 17's remaining failure: the finishing reboot landed BACK in the
installer (boot order was ide2;scsi0 — d-i ejects the tray but the QEMU
reset closes it again), so the installed system never booted → no guest
agent → IP discovery timeout → journey rc 1. Fixes: guest create now
uses disk-first boot order (scsi0;ide2 — blank disk is unbootable so
first boot still falls through to the ISO) AND the journey detaches the
ISO after the install reboot (`qm set --ide2 none,media=cdrom`, guard
dry-run accepted, non-fatal info step).

Hygiene fixes from the same window: test-itf-ssh got an EXIT-trap
cleanup (killed runs leaked squatter http.servers holding ports — found
one live on :20965); itf_iso_upload removes its /tmp staging file when
put/mv fails (three stale itf-iso-upload-* files cleaned off the base).
pkill/pgrep self-avoidance: bracket the FIRST character ([8]000), never
a trailing digit (8000[0] needs a fifth digit and matches nothing).

### Phase 2 addendum 3 — J01 green through Stage A; two live product findings (2026-10-05)

Attempt 18 exposed the disk-order trap: with the pool disk attached at
create, Linux virtio-scsi enumeration under nested virt is a RACE — which
disk is /dev/sda flips between boots (attempt 18: install landed on the
100G pool disk, system disk blank → SeaBIOS "not a bootable disk" boot
loop; attempt 19: install landed correctly on the 32G but post-boot
enumeration flipped anyway; root is UUID-based so it booted fine).
Fixes: itf_guest_create's pooldisk is now OPT-IN (was defaulting from
site config — the journey's flag removal initially changed nothing; the
audit log /var/log/itf-actions.log on the base proved scsi1 still in the
create line), and J01 Stage D hot-plugs the pool disk after install
(`qm set --scsi1 itfguests:100`, guard dry-run accepted, in-guest
wait for /dev/sdb). SeaBIOS boots scsi0-first deterministically; the
blank-disk fall-through boots the ISO on first boot.

itf_guest_ip parser bug: `qm guest cmd network-get-interfaces` returns a
BARE LIST (qm unwraps the envelope); the inline python did .get() on it
and crash-looped. Fixed to accept list or {"result": [...]} (live-proven:
guest IP 10.0.0.254 discovered in-run).

Attempt 20: FULL Stage A green (unattended install → disk reboot → agent
→ IP → root SSH → os-installed snapshot), Stage B reached the product:
release 0.114.0 source tarball downloaded in-guest per README, curl +
check-prerequisites ran, then `sudo ./bin/install-single-node` died on
its first line of work. TWO findings live-confirmed (FINDINGS.md):
F-001 mkdocs apt-name remediation (guest-prereq.log line 22:
`install: "mkdocs<2"`), F-002 installer-lib.sh resolved from bin/ while
shipped in lib/ (since 0.96.0; install-two-node identical). Repair plan
002 drafted; BOTH await user approval — no product-code changes made.

Note: releases carry no built assets; README documents clone/tarball +
`./bin/install-single-node`, so the repo layout is the user surface the
journey exercises (api.github.com tarball of the tag). The source
tarball includes repo metadata (AGENTS.md, SESSION_NOTES.md, tests/) —
same as a clone; acceptable for cycle 1, revisit if built release
assets ever appear.

### Phase 2 addendum 4 — F-001/F-002 repairs executed + verified; F-003 discovered (2026-10-05)

User approved and I executed repairs 001 and 002:
- F-001: check-prerequisites treats mkdocs/mkdocs-material absence as
  informational warnings (the installer's doc-server step installs them —
  via pip on stock Debian, via apt on trixie where the packages exist);
  only mkdocs >= 2 still fails, now with an empty apt-package column and
  a pip remediation hint in installer-lib.sh.  docs (commands.md,
  messages index) updated.
- F-002: both installers resolve installer-lib.sh from lib/ via
  $repo_dir.  NEW guard suite tests/test-installer-structure walks bin/*
  for "$var/...sh" references and asserts the targets exist; proven
  red on the old tree (via a transient stash — see the disclosure in
  the session report; state fully restored) and green on the fixed tree.
  test-check-prerequisites extended for the warn rows / v2 row (gotcha:
  sealing PATH for fakeroot-based runs requires an absolute fakeroot
  path pinned BEFORE and `env PATH=...` for the script only — bash
  applies PATH= prefix-assignments to the command lookup itself, and
  the fakeroot wrapper needs getopt/cat from PATH; awk/cut/grep had to
  be symlinked into the stub dir).

Attempt 23 (dev-tarball source mode — working-tree tar minus .git/.zcode/
docs site/cache/site-config, second itf_http_serve for Stage B) verified
both repairs live: checker output shows the two ⚠ mkdocs rows with 10
genuine apt-remediable failures, and the installer runs banner → doc
server → Step 2 config (hostname itfj01, generated node.conf) → Step 3
deploy.  It then died at deploy-version:163 `rsync: command not found`
(rc=127) — NEW finding F-003: both installers resolve check-prerequisites
as $repo_dir/check-prerequisites (repo root) but it ships in bin/, so the
[[ -f ]] guard silently skips the ENTIRE prerequisites step on a fresh
tree; the step that would have installed rsync (and zfs/pv/smartmontools/
GTK/pip) never runs.  Same layout-drift family as F-002, hidden until
F-002 was fixed.  Plan 003 drafted, AWAITING APPROVAL; journey install
answers are currently '\n\n' (hostname default, decline edit) and must
flip back to 'y y \n \n' once F-003 is repaired (comment in the journey).

J01 Stage B/D design note: Stage C deliberately verifies only deployment
artifacts (current symlink, VERSION, node.conf, PATH link, config.json);
zfs presence is exercised by Stage D's pools, which is where F-003 would
have surfaced next if the deploy step hadn't crashed first.

Attempt 22 lesson (feed alignment): with prereq prompts absent (F-003),
'y y \n \n' misaligned — first y became the hostname, second y opened
nano on a pipe ("Standard input is not a terminal").  Feeds must match
the ACTUAL prompt sequence of the tree under test.

Full suite green after the repairs (run logged /tmp/zfs-run-repairs.log);
guest 8000 destroyed post-verification; no stray listeners dev/base.
Site config still ITF_SW_SOURCE=dev-tarball pending the F-003 decision.

### Phase 2 addendum 5 — F-003 repaired; F-004 found at the next layer (2026-10-05)

User approved plan 003; executed.  Both installers now resolve
check-prerequisites via $script_dir (bin/).  Guard test extended:
test-installer-structure gained test_installer_path_references_exist —
every "$repo_dir/…" / "$script_dir/…" reference in the two INSTALLERS must
exist (-e, files or dirs like share/two-node).  Scoped to the installers
deliberately: bin/zfsconfig:74 iterates CANDIDATE paths (bin/python then
python/ at root) where a missing first candidate is normal — a bin/-wide
-e check would false-positive there.  Red side proven by a plain
working-tree swap (cp installer aside, sed the bug back in, run, restore)
— no git stash this time.

Attempt 24 (run-20261005-120247, dev-tarball, feed back to y y ⏎ ⏎):
the prereq step now RUNS — "=== Checking Prerequisites ===", 10 failures
explained, both remediation prompts asked and answered, apt reached …
and died: `E: Unable to locate package zfsutils-linux rsync
smartmontools …` — the ENTIRE list as ONE apt argument.  F-004:
run_interactive_prerequisites glues collect_apt_packages output into a
single string and calls `apt_install "$packages"` (installer-lib.sh:324);
apt_install itself is fine ("$@"); all other callers pass bare words.
Host-side repro: `apt-get install -s 'pv rsync'` → same E: signature.
This path was unreachable before F-002/F-003 — never once run on a fresh
system.  Plan 004 drafted (mapfile into an array, apt_install
"${pkg_list[@]}"), AWAITING APPROVAL.  F-003 status: fixed with the step
live-confirmed running; full rerun-green completes together with 004.

Layer-peeling pattern holding: each repair unblocks the next hidden
defect in this never-exercised fresh-install path.  F-004 is the last
gate before the first full J01 green (prereqs install → re-check →
rc=0 → Stage C verify → Stage D pools on real zpool).

Full suite green after the F-003 changes (82 suites; guard suite now
3 tests).  Guest 8000 destroyed; dev/base clean; site config still
dev-tarball for the F-004 verification rerun.

### Phase 2 addendum 6 — F-004 repaired + live-confirmed; F-005: Debian contrib (2026-10-05)

User approved plan 004; executed.  run_interactive_prerequisites now
mapfiles collect_apt_packages into an array and calls
apt_install "${pkg_list[@]}" (installer-lib.sh:326); display line uses
${pkg_list[*]} (display-only).  Guard test
test_run_interactive_prerequisites_splits_package_args added to
test-installer-checks: fake checker (fails → --list-failures rows →
passes once mock apt_install touches a flag), captured apt args must be
exactly one package per line with no spaces.  Red proven by swapping
in "${pkg_list[*]}" (the glued-arg bug) — file swap, no git.  31/31.
Note: test-installer-checks has a PRE-EXISTING info-level SC2013 (line
~811, template-token walk) — not introduced by this work; left alone.

Attempt 25 (run-20261005-123403): F-004 fix live-confirmed — apt error
changed from the glued "Unable to locate package <all names>" to a
normal per-package error.  NEW finding F-005: zfsutils-linux is in
Debian contrib ONLY (verified against the trixie contrib Packages
index; Ubuntu/Mint carry it in main — the dev host is Mint, so this is
invisible in development).  Stock Debian netinst enables
main+non-free-firmware, not contrib → the README requirement line, the
dev-guide apt line, and the installer remediation all dead-end at
"E: Package 'zfsutils-linux' has no installation candidate".  Plan 005
drafted: runtime apt-cache probe in check-prerequisites that appends a
contrib hint ONLY when no candidate exists + README/dev-guide note +
journey preseed flips contrib=true (models the docs-following user).
AWAITING APPROVAL.

J01 stays 16 pass / 2 fail (install aborts at the apt run) until 005.
Full suite green (82 suites, guard now 31-test suite counted).  Guests
destroyed; dev/base clean; site config still dev-tarball.

### Phase 2 addendum 7 — F-005 executed; F-006: headless launcher skip (2026-10-05)

User approved ("Do F-004 and F-004/F-005 now"); F-004 was already executed
last turn, so this turn executed plan 005:
- check-prerequisites: after the core checks, when a failure names
  zfsutils-linux AND `apt-cache policy` shows no candidate, print a
  Debian-contrib note (informational; human mode only; probe skipped
  when apt-cache is absent).  test-check-prerequisites helper gained
  ZFS_STUB / APT_CANDIDATE knobs (sealed-PATH stubs); 4 new tests, 14/14.
- Docs: README Requirements + developer-guide prerequisites + commands.md
  check-prerequisites section + messages/index.md note row.
- Harness: preseed apt-setup/contrib=true (guest models the
  docs-following user; stock-main guest was the F-005 reproduction).

Attempt 26 (run-20261005-132650): the remediation SUCCEEDED end-to-end —
`✓ Installed: zfsutils-linux rsync smartmontools python3-gi
gir1.2-gtk-3.0 python3-pip pv gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0`
(zfsutils-linux/zfs-dkms fetched from trixie/contrib), re-check passed,
MkDocs step installed, deploy-version + switch-version completed ALL
wiring (current symlink, PATH profile, sudoers, bashinit, lib symlinks).
F-003/F-004/F-005 all verified.  THEN the installer exited rc=1 with no
error and no summary: F-006 — create_desktop_symlinks returns 1 on the
headless skip paths (no X → no desktop user; lib/desktop-launcher-lib.sh
:73/:80), unguarded at switch-version:228 inside the set -e chain; the
lib-missing stub two lines up returns 0, and two existing tests pin the
faulty rc≠0 contract (they must flip with the fix).  Plan 006 drafted,
AWAITING APPROVAL.  J01 16/2 — install is one soft-skip away from the
first full green (rc=0 → Stage C → Stage D pools on the zfs-dkms-built
modules).

Full suite green (82/4244/0/1).  Guests destroyed; dev/base clean; site
config still dev-tarball.

### Phase 2 addendum 8 — F-006 repaired: installer rc=0 at last (2026-10-05)

User approved plan 006; executed with one disclosed scope extension:
remove_desktop_symlinks had the IDENTICAL return-1 skip paths, unguarded
at switch-version:262 inside uninstall_wiring (would abort MID-UNWIRE on
headless hosts; J02's uninstall journey would hit it) — fixed identically
under the same finding.  All four launcher skip paths now return 0 with
their warnings intact (matching the lib-missing stub contract at
switch-version:64).  test-installer-checks: the two pinned rc≠0
assertions flipped to rc-0-with-warning, plus two set -e subshell pins
(`env -u SUDO_USER DISPLAY=:99` forces the headless condition; warn/
log_msg stubbed — the lib sources standalone).  Red proven by reverting
the create-no-user return via file swap (2 tests fail), green 33/33;
test-switch-version 8/8.

Attempt 27 (run-20261005-140352): install-single-node rc=0 — FIRST
complete first-time-user install on headless fresh Debian.  Two new
downstream items:
- Stage C fail = HARNESS bug (fixed in-journey): itf_guest_exec runs
  non-login ssh, so /etc/profile.d PATH wiring is invisible to
  `command -v zfsdailybackup`; the check now uses bash -lc + a direct
  -x layout check.
- Stage D fail = F-007 (finding, AT GATE): the documented test-pool
  recipe (developer-guide/testing.md) uses parted/partprobe with no
  install preamble; fresh Debian netinst has neither (`parted: command
  not found` live-confirmed right after the successful install).
  Plan 007 is docs-only (one apt-get install -y parted preamble line).

Attempt 28 (run-20261005-142540, with the Stage C fix): 19 pass / 2
fail — rc=0 stable, Stage C green; only Stage D's parted (F-007) keeps
J01 from full green.  Full suite green (82/4246/0/1).  Guests
destroyed; dev/base clean; site config still dev-tarball.

### Cycle-1 findings F-007..F-010, J01 fully green, J02/J03 authored (2026-10-05)

Attempt 29 (run-20261005-144938): 19/2 — F-007's parted preamble works
(Stage D proceeds into ZFS).  NEW F-009: on stock Debian the remediation
installs zfs-dkms (pulled by zfsutils-linux) but NOT
linux-headers-$(uname -r); dkms registers ("added") and never builds, so
`zpool create` dies with "The ZFS modules cannot be auto-loaded".
Live-diagnosed in guest: modinfo zfs fails, headers absent, gcc/make
present.  Fix (verified by attempt 30): functional zfs-kernel-module
check in check-prerequisites (modinfo probe -> headers remediation row;
4 new tests in test-check-prerequisites, 18/18).

Attempt 30 (run-20261005-151307): J01 FULLY GREEN (21 pass / 0 fail,
three RAIDZ1 test pools ONLINE) — the complete first-time-user journey
works end-to-end on headless fresh Debian for the first time.

F-008 (static find, J03 design review): check_partial_uninstall's
cleanup fallback resolved the uninstaller at repo root; ships in bin/.
Fixed (dev repo) + guard test extended to installer-lib.sh.

Journeys refactored: common.sh now carries stage_os / stage_install /
verify_installed (J_PIDFILE globals for the EXIT trap); J01 refactored
onto it post-attempt-30 (shellcheck clean; validating rerun pending);
J02 (uninstall --purge --yes -> clean-state assertions -> reinstall ->
verify) and J03 (partial state -> installer's cleanup offer -> install
completes; exercises F-008) authored.  Feed formats per tree state:
fresh `y\ny\n\n\n`, post-purge reinstall `\n\n`, over-leftovers `y\n\n`.

F-010 (J02 first run, run-20261005-154247): uninstall-zfsutilities
crashed instantly — `line 88: ZFSUTILITIES_LEGACY_CONFIG_DIR: unbound
variable`.  load_uninstall_config read SIX legacy vars bare under main's
set -euo pipefail; bashinit->paths.sh defines five, but CONFIG_DIR is
defined by NO product file (only cleanup-zfsutilities-legacy reads it,
with its own default).  So every real uninstall invocation crashed
before removing anything; masked in unit tests (harness exports
CONFIG_DIR, test-lib's bashinit bootstrap supplies the rest via
paths.sh).  Fix: six `:-` defaults mirroring cleanup-zfsutilities-legacy
/ paths.sh resolved values; new red/green guard test in
test-uninstall-zfsutilities (11/11).  Guest 8000 destroyed; J02 rerun
launched against the fixed dev tarball.

F-011 (J02 green run's transcript, cosmetic): during --purge the
uninstaller removes /var/log/zfsutilities then logs its summary; each
remaining log_msg leaked "No such file or directory" — bashinit:161's
append guard (`>> file 2>/dev/null || true`) loses because bash
evaluates the failing >> BEFORE the 2>/dev/null takes effect (proven on
bash 5.2 host-side).  Fix: reorder to `2>/dev/null >>` + wrapper test in
test-bashinit (red/green).  Trailers in zfsdailybackup/zfs-send-receive
share the pattern but are unreachable in this flow — left alone, noted
in plan 011.

J02 harness hardening: clean-state scan had a done/fi typo that aborted
the login-PATH check AFTER the six path checks; the grep-LEFTOVER
criterion couldn't see the abort.  Fixed + added a positive
"scan-complete" marker so any future early abort fails the step.

J01 refactor-validation run (run-20261005-170408) aborted at
"guest ssh reachable": HARNESS bug, not the refactor — DHCP recycled
10.0.0.254 from an earlier campaign guest, and StrictHostKeyChecking=
accept-new rejects CHANGED keys, so all probes failed on mismatch while
sshd was actually up (banner answered post-mortem).  Guests that drew
fresh IPs never hit it.  Fix: ssh-lib.sh guest helpers now share
_ITF_GUEST_SSH_OPTS (StrictHostKeyChecking=no + UserKnownHostsFile=
/dev/null) — disposable guests must never consult the operator's
known_hosts.  Proven live against the same mismatched-key guest before
destroying it; test-itf-ssh green.

### Cycle-1 close: all journeys green, all findings verified (2026-10-05)

Closing runs on the current working tree (dev-tarball source):
- J01 run-20261005-172712: 21/0 — validates the common.sh refactor;
  three RAIDZ1 pools per the docs recipe.
- J02 run-20261005-174959: 22/0 — final confirmation; uninstall
  transcript tail is clean (F-011 live-verified: zero "No such file or
  directory" after the log dir is removed), clean-state scan ran to its
  scan-complete marker INCLUDING the login-PATH check (the earlier green
  J02 run had never executed that check due to the done/fi harness bug).
- J03 run-20261005-164113: 22/0 — F-008 live-verified (Remnants warning
  → cleanup → install completes).

FINDINGS: F-001..F-011 all verified.  Release-tarball source mode stays
unavailable until a release carries the fixes (user's release process).

Post-campaign hygiene: base VM has 0 guests and 0 itf syslog listeners;
dev has no stray http servers.  Full suite run once at close (see wrap
report).  Cycle-2 candidates live in the Phase 3+ roadmap of the master
plan (two-node, upgrades, GUI click-through, failure injection).

## Wrap-up cycle 2026-10-05 (steps 1-6, pre-version)

Step 1 (PREEXISTING): attach-vm-disk two-node bug RESOLVED — the zvol
existence check + volsize read are now node-aware: compute-host two-node
invocations validate over one SSH round trip (name+volsize from a single
`zfs list -H -o name,volsize`); single-node and storage-host invocations
validate locally as before.  Removes the latent `size=unknown` in the
VM disk line too.  test-attach-vm-disk gained 4 script-execution tests
(stub PATH with hostname/zfs/ssh/qm/id fakes + generated node.conf);
red/green proven by file swap.  Docs: two-node.md flow step + messages
index rows (local vs storage-host FATAL variants).  Zensical recheck:
0.0.68, still no 1.x (entry stays parked).  Infra-vdev planning UI
stays in abeyance (user decision 2026-10-03).

Step 2 (standards): all files touched by this changeset wrapped to
<=100 columns (itf driver/libs/journeys + check-prerequisites + 3 test
files).  warn() in check-prerequisites now joins "$*" like log_msg
(single-arg callers unaffected).  common.sh's EXIT trap became a
_journey_exit_cleanup function; two long one-arg command strings became
local-var (+=) builds.  Heredoc payloads verified byte-level: the two
wrapped payload lines (PRESEED grub sed, dl_script latest_url) differ
only by inter-word spaces at the join points — functionally identical.
shellcheck (documented command incl. itf) + ruff clean.  Two standards
debts recorded in PREEXISTING.md: itf strict-mode adoption (needs live
re-validation at cycle-2 kickoff) and legacy >100-col lines in untouched
test files.

Step 3 (suite review): resize-vm-disk / remove-vm-disk checked — they
delegate compute->storage BEFORE their local zfs checks, so the attach
bug does not extend to them.  No obsolete/incorrect tests found.

Step 4 (docs): integrated-testing.md suite list updated (test-itf-ssh
+ serve/fetch/stop coverage).  docs integrity suite green; docs site
rebuilt (rc=0; the known mkdocs-material MkDocs-2.0 warning — parked
toolchain decision).

Step 5: full suite without soaks run once in the background — all green
(no failures, soak suite skipped by design).

Step 6: codebase frozen at this point.  VERSION/changelog untouched;
commit awaits explicit user confirmation.

## Dev container maintenance 2026-10-05: zfsutilities-dev rebuilt after drift

User task: "Ensure that the Docker container on the dev host is
maintained." Findings: the image had been built 2026-09-18 and silently
predated the python3-gi-cairo addition to share/dev/install-test-deps.sh
(0.114.0) — `import cairo` failed in-image, so the documented container
suite run would have gone red exactly like CI did on v0.112.0. Nothing
rebuilds the image automatically and no rebuild-trigger guidance existed
in the docs.

Work done:
- `.dockerignore` added (allowlist idiom: `*` then re-include
  requirements-dev.txt + share/dev/install-test-deps.sh — the only two
  files the Dockerfile COPYs). Without it the build context was ~1.8G
  over NFS because gitignored tests/integrated/cache/ (1.7G ITF apt
  cache) still enters the docker context; .gitignore does not affect
  docker.
- Base refreshed (docker pull ubuntu:24.04) and image rebuilt from
  c6d4981 working tree (new image e0da665452c0). Fast gates green:
  cairo 1.25.1 + Gtk3 import, entrypoint-provisioned /dev/loop0/1,
  deployed-layout symlinks, zfs/shellcheck/pv/rsync/smartctl/xvfb-run
  all present.
- developer-guide/testing.md (dev-container section, additive):
  rebuild-trigger sentences + `-e PYTHONDONTWRITEBYTECODE=1` added to
  the documented docker run command (avoids root-owned __pycache__ in
  the user-owned checkout) + a sentence that some chmod-based
  failure-injection tests self-skip as root. Site rebuilt via mkdocs.
- First full in-container suite run: 2 failures — test-safe-iscsi-save
  Test 8 and test-repair-iscsi-luns Test 12. Root cause: both inject
  "install failure" via chmod 555 on the destination dir and expect mv
  to fail; the container runs as root and root ignores mode bits, so
  the scripts succeed (rc=0). Environment assumption, not a product
  bug (host + GitHub CI run non-root). Fix per tests/AGENTS.md
  environment-skip philosophy: EUID-0 test_skip guards with reason
  "Requires non-root (root ignores the 0555 install-dir gate)".
  Verified both suites green on host as dan (22 passed, guard inert)
  and in container as root (2 tests SKIP with reason).
- Final full in-container suite: GREEN — 82 suites, 4254 passed,
  0 failed, 1 suite skipped (integration, no test pools), python layer
  3330 passed + 170 subtests; docker rc=0. ~8 minutes wall clock.
- Housekeeping: docker image prune reclaimed 540MB (old image chain +
  stale base); docker state now exactly ubuntu:24.04 +
  zfsutilities-dev:latest, no stray containers.
- Gotchas: `docker run ... | tail` reports tail's rc — use PIPESTATUS
  for the real exit code; in-image mkdocs is correctly pinned <2 (the
  host's MkDocs-2.0 warning is the pre-existing PREEXISTING.md item,
  untouched).

Uncommitted at wrap-up: .dockerignore (new), testing.md (additive),
tests/test-safe-iscsi-save + tests/test-repair-iscsi-luns (EUID-0 skip
guards), this note. No product code touched. VERSION/changelog
untouched; commit awaits explicit user confirmation.

## itf console discipline + run visibility (2026-10-05)

User concern: using the Proxmox consoles on the journey test VMs while
integrated testing runs interferes with the tests. Assessed, then
implemented the two approved items (PVE tag marker via `qm set` was
explicitly out of scope; console-session detection rejected — needs new
sudoers surface for a bounded-cost accident).

Interference mechanics (drove the design): the install phase is driven
over the guest's serial line (`qm terminal` + serial_console.py); the
PVE web UI xterm.js console attaches to the SAME socket — interleaved
keystrokes/split output, and attaching after the bootloader painted can
blind the driver. noVNC is a separate input (kernel cmdline is
console=ttyS0 only) but exposes power buttons. Base-VM consoles are root
outside the guard.

Shipped:
- report-lib.sh: meta.txt now records `pid:` at init and `finished:` at
  finish; new `itf_run_state` (running|done|interrupted|unknown — pid
  liveness via kill -0; PID-reuse caveat documented, cosmetic-only) and
  `itf_watch_resolve` (tag match → newest running → newest any state;
  name sort -r, not mtime — run dirs are append-heavy).
- itf driver: `status` gains an always-shown "== active run ==" block
  (pid/elapsed/hands-off hint) and `(interrupted)` markers on
  summary-less recent runs (immediately useful: the aborted 17:26:43
  j01 attempt now labels itself); new `watch [TAG]` subcommand execs
  `tail -n +1 -F` over steps.tsv/report.md/serial-install.log/
  serial-console.log (GNU tail -F retries not-yet-created files; stderr
  suppressed); manual-steps prints a standing hands-off rule (base host
  names from site config, nothing hard-coded); journey run emits a
  one-line banner with pid + watch hint.
- Tests: test-itf-report extended (pid/finished stamps, run-state
  lifecycle incl. reaped-child pid for interrupted); new test-itf-watch
  (target resolution incl. running-over-newer-done preference).
  GOTCHA: fixture tests sharing one runs dir must isolate the
  "empty dir" case in its own subdir — earlier fixtures leak otherwise.
- Docs: integrated-testing.md gains "Console discipline while a run is
  active" subsection + watch in the Running block;
  tests/integrated/README.md quick-start line + safety-model bullet.
  Site rebuilt (mkdocs rc=0; host MkDocs-2.0 warning is the known
  PREEXISTING item).

Legacy note: run dirs created before this change have no pid/finished
markers — completed old runs surface as `(interrupted)` in status until
they scroll out of the top-3. Semantics are correct going forward.

Uncommitted at wrap-up: tests/integrated/{itf,README.md},
tests/integrated/lib/report-lib.sh, tests/test-itf-report,
tests/test-itf-watch (new), docs/docs/developer-guide/
integrated-testing.md, this note — plus the pre-existing user/agent
changes (testing.md, two iscsi test files, .dockerignore, earlier
notes). No product code touched. VERSION/changelog untouched; commit
awaits explicit user confirmation.

## zfsretain Phase 1 same-day dedup — all buckets, interleaving-proof (2026-10-05)

Trigger: stewie session log
`/var/log/zfsutilities/sessions/2026-10-05_06-00-01_backup_profile-root-backup-dailybackup.log`.
User requirement: same-day snapshots must be pruned within ALL buckets, not
just `d`.

Diagnosis: on Sun 2026-10-04 three dailybackup runs (06:00 scheduled, ~12:34
midday profile/GUI, 23:07 re-run) left three same-day `-w` snapshots per
dataset. Old Phase 1 compared only CONSECUTIVE entries of the creation-sorted
list and reset its comparison state on every skip (foreign label, clone/c,
snapshot_has, phase0), so the interleaved `BaseInstall`/`ITEinitConf`
snapshots suppressed the dedup entirely — zero `--- Same-day.` lines in the
log. Phase 2 couldn't clean up either (w minage=14 blocked; zfsdelsnap WARNs
"only 0/7 days old"). Weekday `-d` duplicates usually sit adjacent in the
list, which made the bug look like "dedup only works for d". Docs already
promised "most recent per day within each bucket" — code just didn't deliver.

Fix (bin/zfsretain Phase 1 rewritten): single pass with assoc array
`_day_latest` keyed `fs|label|bucket|ymd` (Phase 0 `_month_latest` pattern) —
most-recent-wins per key, immune to interleaving, chains of 3+ collapse to
newest, skip branches just `continue`. Bucket stays in the key: cross-bucket
same-day pairs are both kept (within-bucket policy, user-confirmed). Same-day
removals still bypass minage (delsnap minage 0), messages unchanged.

Tests (tests/test-zfsretain): test_phase1_same_day_interleaved (stewie
scenario, red-proof for the old code), _chain (3 same-day), _weekly_and_
monthly (w + m pairs), _cross_bucket_kept (pins within-bucket scope). Suite
21/21 green. shellcheck clean both files; ruff clean (serial_console.py
format nit is pre-existing uncommitted itf WIP, left alone).

Expected on stewie after deploy: next dailybackup-label prune removes the
leftover Oct-4 same-day `w` duplicates with `--- Same-day.`; 09-27 `-w`
stays until minage 14 as designed.

GOTCHA for test data: creation rows are `name<TAB>creation`, so awk field $1
is the NAME and the date starts at $2 — `awk '{print $6 $3 $4}'` yields
YearMonthDay only because of that leading name field.

## MVS-style numbered input requests (2026-10-05)

User rejected the old stdin priority chain (documented as PREEXISTING last
turn, entry now removed — addressed). Model: IBM MVS console WTOR. Every
prompt from a GUI-launched job is HELD on screen with a stable action number
(`3  [Restore]  <prompt>` strip between log and Input entry); operator
answers `N response`; routing ladder: numbered → sole held → sole live step;
never a priority order (user: "don't ever use that priority chain").

Design (user decisions): sole-outstanding bare text allowed; sole-LIVE-STEP
backstop for unmarked prompts (user scripts); GUI-reachable conversion scope
only but LANGUAGE-AGNOSTIC helpers (bash ask_yn/ask_line + python
input_hold.py; PYTHONPATH prepended to child env).

Protocol: `ZFSUTILITIES_INPUT_HOLD=Y` (set ONLY by BackupRunner._spawn_process
— profile_runner must never see it) gates `ZFSU-INPUT-REQ|<uuid>|<prompt>` /
`ZFSU-INPUT-ACK|<uuid>` on stderr. Runner intercepts before display/session
log; GUI registry assigns monotonic numbers; ack/clear (step exit, cancel,
finish) release holds. ask_yn re-REQs same uuid on invalid answer (number
stays); ask_line is stateless (call-site loops take new numbers).

Converted: zfs-send-receive (6 sites), zfsdelallsnaps, zfsmassdelsnaps (2,
ask_yn tightened y-prefix→strict y/yes — "yolo" no longer approves deletes),
zfslockmanager (2). Not converted: CLI-only scripts (VM-disk tools,
installers); zfsdelallholds (releaseholds=Y on all GUI paths).

Tests: test_input_requests.py + test_input_hold.py (caught 2 real bugs:
python helper emitted markers ungated; markers lacked trailing \n —
runner splits on newlines, so they'd never parse), TestInputHoldProtocol in
test_backup_runner.py, TestInputRoutingLadder/TestInputEventLifecycle/
TestStdinEnableRecompute in test_zfsutilities_gui.py, 3 new test-bashinit
cases. Old priority-chain test rewritten to sole-live-step. Docs: gtk-gui.md
bottom panel + tab notes, messages/index.md approval row + answering note,
conventions.md "Interactive Prompts" section. Awaiting commit.

GOTCHA: `read -rp`/`input()` prompts are invisible when stdin is piped
(bash only shows -p prompts on a tty; python input() prompt goes to stdout)
— piped smoke tests look like the prompt vanished; assert on markers, not
prompt text. grab_focus now only on disabled→enabled transition (recompute
fires on every input event; per-spawn grab would steal focus constantly).

## Development cycle wrap-up 2026-10-06 (six-step strict sequence)

Step 1 PREEXISTING: column-wrap debt resolved — all tests/test-* files now
≤100 columns (11 files; by-path prefix vars + unquoted heredocs with
${var}, $'...' concatenation splits, backslash splices inside unquoted
heredocs — generated scripts stay byte-identical); shellcheck clean; the
11 affected suites green. Zensical recheck refreshed (PyPI 0.0.68, still
no 1.x). Entries 2 (infra-vdev planning UI abeyance) and 3 (itf strict
mode, cycle-2 kickoff) remain by recorded user decision. 3 entries left.

Step 2 standards: project shellcheck command green; ruff check green;
ruff format green after reformatting tests/integrated/lib/serial_console.py
(committed in 0.115.0 without formatting — mechanical argparse rewrap, no
behavior change; module compiles, --help OK, no unit tests import it).
Fixed missing profuse regex documentation on input_requests._NUMBERED_RE.
No site-specific names anywhere in the new product code.

Step 3 tests: added test_ignore_approval_y_prefix_cancels to
test-zfsmassdelsnaps (pins the strict y/yes approval change — "yolo" no
longer approves deletion). Reviewed all new suites (input_hold,
input_requests, GUI ladder/lifecycle/recompute, backup-runner protocol,
bashinit hold helpers, zfsretain phase-1, itf report/watch) — coverage
thorough, no stale assertions. Affected suites green.

Step 4 docs: messages/index.md zfsutilities_gui table updated (VERB: >
row reworded for routing; added WARN no-such-number, WARN input-ignored,
INFO/VERB [Input N] held/closed/withdrawn rows); python-modules.md gained
input_hold.py + input_requests.py sections (placed between backup_runner
and offsite_runner — first insert orphaned backup_runner's data-structures
table, repaired) and input-hold protocol paragraph in backup_runner.py +
input_event_func mention in runner_factory.py. Docs integrity suite
green; mkdocs build rc=0 (host mkdocs-2.0 warning = known PREEXISTING).

Step 5: full suite without soaks, background — ALL GREEN, zero failures,
one expected skip (integration, no test pools). Over-budget >5s advisories
are the runner's timing notes on known-slow suites, not failures.

Step 6: codebase frozen at this point. VERSION/changelog untouched;
commit awaits explicit user confirmation.

GOTCHA (wrapping bash fixtures ≤100 cols): quoted heredocs cannot wrap —
switch to unquoted <<EOF + ${prefix_var} only after checking the body has
no $/backtick that must stay literal; single-quoted \n strings split as
'part1'\<newline>'part2' (never mix with $'...' — it interprets \n);
inside unquoted heredocs backslash-newline splices, so wrapping heredoc
CONTENT keeps generated scripts byte-identical (leading spaces of the
continuation line remain — harmless for word-split consumers).

Uncommitted at wrap-up: everything in this cycle's four features plus the
wrap-up additions above (incl. serial_console.py reformat and the
zfsmassdelsnaps regression test).

## Datasets page 2026-10-06: zvols rendered mounted-looking while unattached
  User screenshot: vm-201-disk-3 / vm-205-disk-3 (volumes) showed untinted
  text with Mount enabled / Unmount disabled. Root cause: zvols report no
  ZFS `mounted` property, so both row-population paths set mounted=False,
  but _row_fg_color never tinted type "volume" — display said mounted,
  buttons (which correctly use loop-attach state) said unmounted. Fix:
  volume rows' mounted flag now IS the loop-attach state everywhere —
  new ZfsRepository.loop_attached_paths() (one bulk `losetup
  --noheadings -O BACK-FILE` per pass, degrades to empty set) feeds
  load_dataset_children (lazy expansion) and update_mounted_states
  (lazy-fetched once per walk); _row_fg_color tints "volume" like
  filesystem/snapshot. Legend reworded "unmounted filesystem/snapshot or
  unattached volume". Browse guard added in update_ds_button_sensitivity:
  an attached volume row now reports mounted=True, which would have lit
  Browse, but on_datasets_browse has no volume branch — volume rows keep
  Browse disabled (partition rows are the browsable leaves). Side effect
  (correct): on_datasets_mount's `if item.get("mounted"): continue` now
  skips already-attached volumes, matching _is_mountable. Tests added in
  test_zfs_repository (loop_attached_paths parsing), test_datasets_tree
  (expansion tint/un tint via canned losetup output), test_datasets_page
  (volume-row flag+tint in update_mounted_states; attached volume keeps
  Browse off; legend rewording), test_dataset_actions (attached volume
  row skipped by on_datasets_mount entirely — no zlm.lock, no reload).
  Docs: gtk-gui.md teal paragraph + zvols section explain the tint
  follows the loop device. Awaiting commit.

## Datasets page 2026-10-06: Snapshot action for multiple selection
  Snapshot button now enables when every selected row is a filesystem or
  volume (pool/dataset rows; snapshots/holds/volume-partitions disable it)
  — same predicate family Rewrite Data uses (_is_tunable hoisted above the
  can_* block in update_ds_button_sensitivity). on_datasets_snapshot
  follows the Add Hold pattern: prompt once (single keeps the exact old
  "Dataset:" dialog + zlm.lock with description; multi gets "Datasets
  (N):" + scrolled monospace list, zlm.locks("w", names), per-dataset
  INFO/WARN, one "Created snapshot on N of M datasets" WARN summary when
  any failed, single refresh iff anything was created). Handler filter
  (_snapshot_target_datasets) mirrors the sensitivity predicate so a
  stale button state degrades to acting on qualifying rows only. New
  TestSnapshot class in test_dataset_actions (handler was previously
  untested — _input_dialog must be patched directly: under mock_gtk,
  entry.get_text().strip() is a MagicMock and `" " in name` raises).
  Docs: gtk-gui.md Snapshot table row + messages/index.md dataset_actions
  section (selection-guard wording, four new multi-batch rows). Awaiting
  commit.

## zfscheckagainst 2026-10-06: offline-pool hold-verified message demoted INFO→VERB
  The routine reassurance line fired for every snapshot when an offsite
  counterpart pool is offline ("Offline pool ...: another snapshot carries
  hold '...' — incremental chain intact.", bin/zfscheckagainst:271) is now
  VERB, matching the severity ladder and earlier INFO→VERB demotions.
  Verification outcome unchanged: still counts as verified, deletion may
  proceed. messages/index.md zfscheckagainst row prefix updated (meaning/
  response columns untouched). No test asserts the text; test-zfscheckagainst
  and test_docs_integrity re-run green. Awaiting commit with the pending
  changeset.

## itf post-install baseline template 2026-10-06 (awaiting commit)
  New `itf template` subsystem: a post-install baseline guest built via
  the real first-time-user path (stage_os → stage_install → apt
  full-upgrade + reboot-if-new-kernel + ZFS/wiring boot-health gate) then
  `qm template`d. Journeys clone-start via itf_journey_stage_from_template
  (full clone, `as-cloned` snapshot). j02/j03 converted off their per-run
  netinst; j04-post-install-baseline added (clone → wiring verify → docs
  pools → check-prerequisites all-present → ZFS round trip). Guard gains
  template/clone verbs + name-based template protection (ITF_TEMPLATE_NAME,
  default itf-template; clone exempt; ITF_TEMPLATE_OVERRIDE=1 scoped to
  build/destroy). Stamp = one-line `itf-stamp|` in the PVE description
  field (qm set --description / qm config); freshness compares
  sw-source+version (release) or +rev (dev-tarball); rebuilds always
  from scratch, old template destroyed before rename so name resolution
  stays unique. Design facts: itfguests is lvmthin → NO linked clones
  (file-based/ZFS only) — full clone copies only allocated blocks and is
  journey-independent; SSH already clone-safe (throwaway known_hosts).
  Gotchas: guard's name→VMID resolution runs inside $( ) so the mocked
  itf_base_exec call-capture loses it (assert in parent only); guard
  tests must unset ITF_TEMPLATE_NAME to keep exec counts stable;
  release-path freshness probes GitHub (stub _itf_template_would_version
  in unit tests). Unit tests: test-itf-template new + base-guard/config
  extensions. Roadmap row 2.5 added per user request. Awaiting commit.

  Live verification on zfstestvm1 (2026-10-06): template build succeeded
  on the SECOND run after two real bugs the first run exposed. (1) Guard
  refused the stamp write — a colon token matched the storage-reference
  shape, so description values are now exempt from that check AND the
  stamp marker is colon-free `itf-stamp|`. (2) `qm template` refuses
  snapshot-carrying VMs — stage_os's os-installed snapshot — so the build
  now clears snapshots first (new delsnapshot/listsnapshot verbs;
  listsnapshot's arrow field is `` `-> `` , awk `$i ~ /->$/`, skip the
  `current` pseudo-entry). Template: itf-template = vmid 8000, stamped
  sw-source=dev-tarball version=0.116.0 rev=afbb9bf. Full clone takes
  ~2¼ min on lvmthin. dev-tarball stamps record the commit rev, not
  dirty-tree state (site ITF_SW_SOURCE=dev-tarball, so the baseline
  includes uncommitted working-tree changes).

  First j04 run failed: clone started but the guest agent reported no
  IPv4 in 600s. Root cause: stage_os creates install VMs with `--freeze`
  (serial console captures the first boot byte) and pairs it with an
  explicit resume; the template config carried freeze:1, clones inherit
  it, and stage_from_template starts WITHOUT resume — the clone sat
  paused in QEMU's prelaunch runstate (qm status shows "prelaunch", not
  "stopped"/"paused"). Proven live: one `qm resume` → running → agent
  answered with an IP within a minute. Fixed both ends: template build
  clears freeze before conversion, and itf_guest_clone clears it on
  every clone (covers templates built before the fix; current 8000
  keeps freeze:1 in config — harmless, cleared at clone time). The
  current template also displays %3A in its stamp timestamp: PVE
  percent-encodes colons in description values on read-back; render now
  uses hyphens (built=…T18-36-09Z), re-stamped at next rebuild.

  Diagnostic gotchas from the live runs: itf's ONLY base host is
  zfstestvm1 (site config ITF_BASE_HOSTS) — dan@tweety's sudo is
  NOPASSWD for product binaries only, so `sudo -n bash -c` fails there
  by design; never probe tweety for itf guest state. `itf watch` is
  post-mortem by design when the newest run is finished (it parks on
  the latest run dir), and its `tail -F` stream garbles on terminal
  resize — Ctrl-C and rerun. j04 re-run with the freeze fix: GREEN
  (run-20261006-150042, 14 steps, 12 pass / 0 fail / 2 info) in exactly
  4 minutes clone-to-finish — the post-install baseline promise
  delivered. Guest 8001 left running for post-mortem per journey
  convention (itf guest destroy zfstestvm1 8001).

## Wrap-up 2026-10-06 (post-0.116.0 changeset): six-step protocol complete
  Step 1 (PREEXISTING): test_file_locking shared-lock handshake flake
  resolved — the multiprocessing.Queue "held" wait now uses a 60s
  HANDSHAKE_TIMEOUT constant (raised from 5s; full-suite xdist load can
  starve the child well past 5s). Applied to both the exclusive-lock and
  shared-lock tests (identical exposure). mkdocs-material/Zensical entry
  NOT resolved (awaiting Zensical 1.x, user toolchain decision);
  infra-vdev planning UI (abeyance, future objective) and itf strict-mode
  debt (cycle-2 kickoff with live J01-J03 re-validation) untouched by
  design. One new entry recorded: shellcheck's documented multi-file
  invocation masks SC2034 warnings in files outside tests/integrated/lib/
  (bisected; standalone checks show six in test-itf-base-guard's
  pre-existing block + one in test-itf-report) — fix pattern established
  in test-itf-template's file-wide directive, apply on next touch.
  Step 2 (standards): ruff check + format clean (216 files); documented
  shellcheck command clean after adding a file-wide SC2034 disable to
  test-itf-template, a per-line disable at the new base-guard template-
  protection test, and wrapping 8 new over-100-column lines (template-lib
  apt payload + awk snapshot parser + tag_name sed comment, itf preflight
  message, base-lib verb list, guest-lib hint, config echo, test-itf-
  template stamp literal/assert). Lesson: `VAR="a" \` + next-line `"b"`
  is an env-prefix for a command, NOT a concatenated assignment — base-lib
  verb list broke that way (bash -n and shellcheck both pass it; only the
  unit suites caught it) and now uses `+=`. Echo argument-splits join
  with a space — subshell field vars instead.
  Step 3 (tests): coverage review found no missing/obsolete/incorrect
  tests — multi-snapshot (9 handler + 3 sensitivity tests incl. both
  lock-failure paths), zvol tint both directions + Browse guard + Mount
  skip, itf stamp/clone/freshness/guard all covered; no stale assertions
  of the old single-only Snapshot or untinted-volume behavior remain.
  Step 4 (docs): messages/index.md + gtk-gui.md + integrated-testing.md
  verified against final code (log strings, prefixes, itf status/preflight
  wiring); test_docs_integrity green; site/ rebuilt (known mkdocs-material
  MkDocs-2.0 warning, exit 0). Step 5 (full suite, background, no soaks):
  84 suites, 4371 passed / 0 failed / 1 skipped (root-gated, expected);
  the handshake fix held under load. Step 6: codebase FROZEN here.
  Uncommitted at freeze: the cycle's four features plus the wrap-up
  additions above. Awaiting version/commit instructions.

## PREEXISTING prompt 2026-10-06 (post-freeze follow-up)
  Resolved the shellcheck multi-file-masking entry: file-wide SC2034
  disable (established pattern) in test-itf-base-guard, per-line in
  test-itf-report; standalone sweep of every tests/test-* file now clean
  alongside the documented command; both suites green. Entry removed.
  Zensical rechecked same-day: still 0.0.68 (no 1.x) — mkdocs entry stays
  blocked on the release + user toolchain decision. infra-vdev (abeyance)
  and itf strict-mode (cycle-2 kickoff + live J01–J03 campaign) untouched
  per their recorded deferrals. PREEXISTING: 3 entries remain.

## Release 0.117.0 committed 2026-10-06
  Steps 7-8 of the wrap-up: VERSION → 0.117.0; changelog entry added
  (Added: itf post-install baseline template, multi-select Snapshot;
  Changed: zfscheckagainst hold-verified VERB; Fixed: zvol loop-attach
  mounted-state display, test-infra hardening); all __pycache__ dirs
  removed; docs site rebuilt. Final suite WITH soaks: 84 suites,
  4378 passed / 0 failed / 0 skipped — first attempt silently skipped
  soaks (mistyped --with-soaks flag; totals identical to the no-soak
  run gave it away — always verify the soak suite ran). Committed after
  user confirmation:
    548194da22e7419d74d3e712e942df7d304353ac
    Release 0.117.0: itf post-install baseline template (j02/j03
    clone-start, j04), multi-select Snapshot, zvol loop-attach
    mounted-state tint, zfscheckagainst hold-verified VERB,
    file-locking soak flake fix
  32 files +2,019/−104; working tree clean; NOT pushed (push/tag/
  GitHub release await instruction). No further code changes this
  session.

## Integration-tier container feasibility probe (2026-10-06)
User asked whether the project's Docker container can contain the root-run
integration tests. Verdict: YES, proven end-to-end. The dev host kernel
runs the ZFS module AND the three test pools (zfstest1/2/3, 24.5G, healthy)
already live in it — pools are kernel-global, so a privileged
zfsutilities-dev container (its zfs userspace matches the host kmod
exactly, 2.2.2-0ubuntu9.5) drives them directly. Full send-receive suite
GREEN in-container (7 scenarios / 22 asserts, well under a minute) via
`docker run --rm --privileged -e TZ=America/New_York -v <repo>:/workspace:ro
-w /workspace zfsutilities-dev bash tests/integration/test-zfs-send-receive-pools`.
Gotchas proven live: (1) minimal caps (`--device /dev/zfs --cap-add
SYS_ADMIN`) FAIL — dataset create works but the automount is denied by
apparmor; `--privileged` required (a leftover dataset from the failed probe
had to be destroyed). (2) UTC containers trip the zfssnapbuild `+` bug
(below/PREEXISTING) — inject the host TZ until the product fix lands.
(3) The read-only repo mount makes the zero-checkout-delta invariant
structural, and every paths.sh writable location (/run, /var, /etc, locks,
session logs) is container-local and discarded with --rm — the env-override
sandbox design remains needed only for bare-metal runs. (4) Rootful docker
only (rootless cannot grant the caps); hosts without the ZFS kernel module
(CI) still skip — manifest gating unchanged. Concurrent runs share the
kernel pool namespace (suite allow-list + unique dataset names guard it).
TWO new PREEXISTING entries from this probe: the zfssnapbuild timezone
portability bug, and — the big one — the integration suite itself has been
UNABLE TO PASS as shipped (bare EXIT trap + `( )` subshell +
zfslockmanager's append_exit_trap re-arm ⇒ cleanup_test_datasets fires at
subshell exit and destroys each just-transferred dataset; skipped
everywhere, so silently rotten). Proven one-line fix (`trap - EXIT` first
line in run_send_receive's subshell), not applied. Pool-debris
observations: ancient offsite snapshots on zfstest2 make zfsreapplyholds
WARN 4×/transfer (harmless; cleaning the pools would silence it), and
reapplyholds counts already-present holds as failed applies ("Reapplied 0
(4 skipped)") — borderline nit, left unrecorded. Proposed follow-up (needs
approval): document the privileged container run mode in testing.md next
to the dev-container section, repair the suite per the append_exit_trap
convention, optionally add a run-in-container wrapper.

ADDENDUM (same thread, host blast-radius follow-up): `--privileged` is
NOT actually required. Verified green (probe + full suite 7 scenarios /
22 asserts with the trap-fix copy):
`--cap-add SYS_ADMIN --security-opt apparmor=unconfined --device /dev/zfs
--network none`. `apparmor=unconfined` is the specific concession that
unblocks ZFS automounts (docker-default profile denies mount(2) even with
SYS_ADMIN — refines the earlier "apparmor exception" note). With only
`--device /dev/zfs`, /dev/sda and /dev/sdb are not mapped at all, and the
device cgroup closes the mknod dodge (hand-made `b 8 0` node: mknod
succeeds, open fails EPERM — verified). `--network none` seals the LAN
including the NFS server; the repo bind-mount still works (passed through
from the host). Residual radius: CAP_SYS_ADMIN + unconstrained-by-
apparmor process with full zfs ioctl reach — can act on ANY pool in the
host kernel (suite allow-list remains the guard) and exhaust host
resources (no --memory/--cpus yet; candidates given the mock-walk OOM
precedent). Under full `--privileged` the radius would instead be the
whole host: every device (raw /dev/sda = host OS disk), all caps, seccomp
off, and a LAN network position. Recommended documented mode = the
reduced profile, never --privileged.

## 2026-10-06 — Snapshot-name timezone remediation SHIPPED (uncommitted)

Executed the approved plan: canonical new-name timestamps are UTC rendered
`YYYY-MM-DDTHH:MMZ` ("+" is illegal in ZFS names; west-offset `-HH:MM` was
legal, which is why only UTC/east hosts FATALed). One clock: the d/w/m/s
bucket follows the UTC instant in the name. Dual-format forever — every
consumer parses legacy offset names and Z names; nothing migrates.

- bash: new `snapname_timestamp [epoch]` in bin/bashinit (single source);
  zfssnapbuild (timestamp + bucket via the helper), zfsclone-vm ×2, and
  archive-vm ×2 converted. The archive-vm two-node site runs remotely and
  sources the DEPLOYED bashinit — same release on both nodes required
  (existing versioned-deployment assumption; two-node.md example updated).
- python: new pure `python/snapshot_naming.py` (`snapshot_timestamp`,
  `bucket_for`); feature_config `_build_snapshot_name` and pool_migrate
  `migration_snapshot_name` delegate to it (backup_config is a re-export);
  dashboard docstring reworded. GUI surfaces stay local-clock.
- Schedule page (user choice "Bucket + edge hint"): Next Run gains
  `(daily|weekly|monthly|offsite)` for snapshot-creating profiles and, only
  when UTC date ≠ local date, `· 23:30 Sat = 03:30 Sun UTC — names dated
  Sun`. Column widened 130→230 with word-wrap for the hint; sort string
  unchanged; retention/scrub/restore rows undecorated. Cache key now
  includes the label.
- tests: test-lib date mock rewritten around `_mock_date_utc` (mock must
  emulate real `date -u -Iminutes` output — the +00:00 form — because the
  Z splice belongs to snapname_timestamp; pre-splicing in the mock caused
  double-Z); zfssnapbuild suite Z expectations + charset guard under three
  TZs via `unset -f date` subshell + epoch-form TZ-independence + `date -d`
  round-trip; archive-vm/clone-vm expectations updated (legacy fixtures
  stay deliberately); zfsretain mixed-format dedup test; NEW
  tests/test-snapshot-names (static producer pins + cross-implementation
  matrix: real zfssnapbuild under 3 zones == python for 7 instants incl.
  DST days) and tests/python/test_snapshot_naming.py (pure helpers +
  10-epoch × 3-zone bash parity); schedule_page decoration tests (TZ
  pinned via tzset) + datasets_page creation-first pin.
- Gotchas: `$mydir` in test-lib is the REPO ROOT (my `../python` path was
  wrong); grep -F needs unescaped parens in quoted heredocs; shellcheck
  SC1102 on `$((` — space it `$( (`.
- Docs: concepts.md naming section is the single home (Z + legacy + one
  clock + local GUI); gtk-gui.md Schedule affordances; architecture,
  modules (zfssnapbuild + bashinit function rows), python-modules
  (snapshot_naming.py section + helper rows), restore/offsite/two-node/
  proxmox examples → Z; zfsretain comment block shows both forms.
- PREEXISTING: timezone entry REMOVED (all nine audited sites covered);
  NEW line-length debt entry (archive-vm:345/:414, verified at HEAD).
  5 entries remain.

## 2026-10-06 — Disks page Wipe Labels feature SHIPPED (uncommitted)

- New `bin/zfswipe`: wipes labels/signatures from an INACTIVE disk so it can
  be reused as a pool device. Ladder `zpool labelclear -f` (disk + each
  partition node) → `wipefs -a` → `dd` (first+last 1 MiB per node, 512-byte
  tail math via lsblk SIZE), re-probing (`wipefs` listing) after each step;
  ends early when clean. Guards (all FATAL rc 8): non-block arg, zpool
  unavailable/list failure, ANY node of the backing disk is an imported-pool
  member (`zpool status -Lp` leaf scan — also protects the ZFS-root boot
  disk), anything mounted/swap on the backing disk (non-ZFS-root boot disk).
  CLI typed confirmation via ask_line (type kernel basename) unless
  `--confirmed` (GUI passes it — exactly one typed gate per invocation).
  Post-dd: partprobe → blockdev --rereadpt → udevadm trigger/settle; honest
  rc 0 with "verification unavailable" INFO when wipefs is absent.
- New `python/disk_wipe.py`: pure helpers (typed_target, wipe_block_reason —
  same conservative same-backing-disk rule as the script, wipe_warnings
  incl. importable-pool destruction + dd disclosure + not-a-secure-erase,
  build_wipe_command) + typed-confirmation dialog (identity grid, warnings,
  exact command preview, ladder summary, Wipe button unlocked only by exact
  kernel basename). Module logs nothing; handler logs outcomes.
- `disk_actions.on_disks_wipe_labels`: storage-host/runner/selection/inactive
  gates → dialog → zlm write lock keyed on device path + BashStep
  (zfswipe <path> --confirmed, fatal) on dataset_runner; _on_complete
  releases lock, invalidates inventory cache, refreshes Disks + Pools.
- Wiring: PAGE_SPECS "Wipe Labels…" (`edit-clear-all`, `_disks_wipe_btn`)
  between Manage Pool Profiles and the spacer; ACTION_HANDLERS entry;
  update_disks_button_sensitivity gating via `_selected_disk_is_wipeable`
  (row Pools empty + wipe_block_reason against cached inventory; defensive
  try/except like _selected_disk_is_hdd).
- Copy: "No eligible disks" dialogs (growth handlers ×4 + wizard) now say
  "wipe its labels"; pool_create importable reason "(import, destroy, or
  wipe it first)"; HDD-partitions reason points at Wipe Labels….
- Tests: NEW tests/test-zfswipe (20 checks — guards, typed gate, short
  circuit, wipefs path, dd path with exact seek/count math on non-MiB-aligned
  sizes, residue rc 8, partition-only target); NEW tests/python/
  test_disk_wipe.py (helpers, dialog gating under mock_gtk, handler gates +
  runner/lock wiring); affected suites green (disk_actions, disks_page,
  action_dispatch, pool_create, growth buttons, module-deps, docs
  integrity). Standards: ruff format+check clean, shellcheck clean, ≤100
  cols.
- Gotchas: sourcing bin/zfswipe in tests re-imports the REAL log_msg (bashinit
  re-source) — assert on captured stderr text, not the test log file; mock
  call recordings must go to a FILE (zfsscruball pattern) because
  zfswipe_main runs in $( ) subshells where array appends don't propagate;
  test-lib has ask_yn mock but NOT ask_line — define it; command
  substitution inherits shell functions so `unset -f wipefs` inside $( )
  simulates absence cleanly.
- Docs: gtk-gui.md Disks Actions bullet + "Wipe Labels" section (ladder + dd
  caveats); commands.md zfswipe section + jump list; messages/index.md
  zfswipe table (Pool and System Maintenance) + disk_actions wipe rows;
  python-modules.md disk_wipe.py section + disk_actions row updates.
- PREEXISTING: unchanged (5 entries); no new out-of-scope issues found.

## 2026-10-06 — Wrap-up of post-0.117.0 changeset (six-step protocol)

- Step 1 PREEXISTING: 2 entries RESOLVED and removed. (a) The integration
  send-receive suite's bare-EXIT-trap self-destruction: repaired the
  convention-correct way — the suite now sources bashinit and registers
  cleanup_test_datasets via append_exit_trap (the subshell then RESETS the
  inherited handler list instead of folding a foreign bare trap into its
  exit); validated live in the reduced-profile dev container (all scenarios
  and asserts green, zero dataset debris, and the run doubles as in-container
  proof of the UTC Z names). (b) archive-vm:345/:414 line-length debt
  rewrapped. 3 entries remain, each parked by user decision (Zensical
  toolchain wait, infra-vdev planning UI, itf strict-mode at cycle-2).
- Step 2 standards: ruff check + format clean; shellcheck clean via the
  documented invocation (now covering bin/zfswipe and both new suites);
  100-column limit verified on every changed bash file; new modules follow
  the init/guard/log_msg/output-globals conventions; no undocumented
  regexes; no installation-specific data. zfswipe follows the core-helper
  no-strict-mode pattern (explicit rc handling), like its 94 siblings.
- Step 3 test review: no missing/obsolete/incorrect tests found. New suites
  are auto-discovered (find tests/test-*). Legacy offset-format fixtures in
  python suites are deliberate dual-format parsing tests, not stale. My
  step-1 rewraps broke no assertions (affected suites re-run green).
- Step 4 docs: changeset documentation reviewed against code (message rows
  match shipped log lines, gating lists include Wipe Labels, example
  conversions arithmetically correct); no edits needed; user hand-edits
  untouched. Docs site rebuilt; docs-integrity suite green against the new
  build.
- Step 5 full suite WITHOUT soaks (background): all suites green, zero
  failures; the only skip is the soak suite excluded by design in a no-soak
  run.
- Step 6: codebase FROZEN. Working tree = the two work items (snapshot-name
  UTC remediation; Disks page Wipe Labels) + this wrap-up's PREEXISTING
  fixes + notes updates. Awaiting version/commit instructions.

## 2026-10-07 — Lock-conflict holder details (changeset + six-step wrap-up)

- Headless lock conflicts now identify their blocking holder(s) in the
  session log, closing the forensic gap from the 2026-10-06 morning
  dailybackup rc=9 incident (headless FATAL named no holder; forensics
  needed root-only /run/lock JSON plus cross-session-log spelunking).
- bin/zfslockmanager: `_zfslock_conflicting_lockfiles` walks the full
  hierarchy (same dataset, ancestors, pool, descendants) naming EVERY
  blocking lock — side-effect-free `_zfslock_file_conflicts` so the
  reporting walk leaves zfslock_conflict_info/reentry untouched.
  `_zfslock_log_one_conflict` renders dataset/type/pid/script/acquired
  (ISO + "N units ago" via `_zfslock_relative_time`) and description,
  with type names via `_zfslock_type_name`; both helpers were extracted
  from the interactive conflict prompt, whose behavior is unchanged.
  `_zfslock_log_conflict_details` logs INFO once when the headless wait
  starts (run may still succeed) and WARN immediately before the FATAL
  abort (holder may have changed); intermediate retries stay silent.
  Remote conflicts log the single agent-staged holder with host= — the
  CONFLICT wire line carries only dataset/type/pid/script (verified
  against `_zfslock_remote_acquire` staging), so acquired/description
  are absent there.
- python/zfs_lock_manager.py: local acquire()'s conflict RuntimeError
  names every holder (`_conflicting_lock_holders` mirrors the check()
  walk without early stop; `_format_lock_holder` renders); remote
  `_acquire_remote` conflict errors embed the agent's CONFLICT line.
- Tests: bash suite adds immediate-abort holder line, wait-start INFO +
  abort WARN + FATAL, two-descendant multi-holder naming, success path
  logging exactly one INFO (folded into the wait-interval fallback
  test), and the remote host= line. Python suite pins the remote
  CONFLICT embed plus local single-holder (all fields) and
  ancestor+descendant every-holder cases (fabricated lock files with
  live sleep PIDs so stale cleanup keeps them).
- Docs: developer-guide/lock-manager.md holder-detail paragraph;
  messages/index.md one new row for the INFO/WARN detail lines.
- Wrap-up (six-step, 2026-10-07): standards — rewrapped six new
  overlong assertion lines in tests/test-zfslockmanager (grep patterns
  rebuilt with `+=` string appends; a backslash continuation inside the
  quoted string would embed the next line's leading whitespace and
  change the pattern); fixed two PRE-EXISTING overlong mock-JSON lines
  in tests/python/test_zfs_lock_manager.py via implicit concatenation
  (file already in changeset scope; disclosed in report). shellcheck
  (documented invocation) and ruff check/format clean; 100-col limit
  verified on every changed file. Test review — dataset_actions'
  conflict-message assertions are producer-independent mock
  side_effects, unaffected by the longer real message; no
  missing/obsolete tests found. Docs site rebuilt; docs-integrity
  green. PREEXISTING: 3 entries remain, all parked (Zensical rechecked
  2026-10-07 — PyPI latest 0.0.68, still no 1.x; infra-vdev planning UI
  in abeyance; itf strict-mode deferred to cycle-2 kickoff). Full suite
  (no soaks) running in background at freeze time. Awaiting
  version/commit instructions.

## Blocksize alignment feature (2026-10-07, IN FLIGHT — relocated from the `blocksize` worktree to the main checkout same day; worktree removed)

Performance-page second view (Live Charts / Alignment radio switcher):
blocksize alignment chain device→pool→dataset→VM, tuning advice from
observed `zpool iostat -r` histograms + ARC/prefetch kstats + the user's
workload survey (Survey… dialog), advisory only. User decisions: switcher
on Performance page (not a new sidebar page); both bases; advisory only.
kstat-analyzer-inspired thresholds as named constants in
alignment_analysis.py.

- New modules: alignment_stats.py (data layer, GTK-free),
  alignment_analysis.py (pure rules), alignment_page.py (view),
  alignment_dialogs.py (survey dialog). memory_page hosts the switcher +
  Gtk.Stack; refresh_memory_page dispatches to the visible view.
  Repo/config additions: ZfsRepository.dataset_block_properties,
  feature_config get/save_alignment_survey (config key
  `alignment_survey`), UI_STATE_DEFAULTS `performance_view` (get_ui_state
  only returns declared keys — new persistence keys MUST be registered
  there).
- Shared memory_page helpers (section_header, note_label, show_note,
  set_text_if_changed, reconcile_rows) moved to gui_helpers; memory_page
  now imports them UNALIASED (renamed ~33 call sites) because ruff's
  isort default (combine-as-imports=false) splits any from-import mixing
  plain and `x as y` names into six separate statements — the unaliased
  one-statement import is the house-clean form and matches
  alignment_page.
- Test gotchas: mock_gtk's ResponseType.OK is the plain int 1 on every
  context, so identity comparisons survive across separate mock_gtk()
  blocks; ListStore mocks ACCUMULATE append history across successive
  _apply calls in one test — later-applied rows must be read from the
  tail ([-1]) not [0]; Gtk.RadioButton.new_with_label_from_widget needs
  a side_effect to give distinct radio mocks (shared default makes both
  views' get_active() identical); the survey dialog's lazy
  `from alignment_page import refresh_alignment_view` is patchable at
  "alignment_page.refresh_alignment_view".
- Test suites RUN 2026-10-07 after user clarified their other project
  runs on main, not this branch (itf files in tests/integrated/ +
  untracked tests/test-itf-driver in the worktree tree were the user's;
  untouched).
  First affected-suite pass caught 6 authoring bugs, all fixed: the
  stewie-fixture test misread the trim-ind column as scrub (parser was
  right — 1.15M@32K is trim ind, scrub agg is 6); parse_pve_vm_conf vmid semantics — first "fixed" token-derived
  (matching a self-authored test guess), user correctly challenged it
  and it was REVERTED to filename-derived: the conf filename is the
  authoritative current owner of every disk line in it; the id inside
  vm-<id>-disk-<n> is creation history that goes stale after disk
  moves. Test now pins the moved-disk case (vm-205-disk-1 in 201.conf
  → vmid "201"); the pools-unavailable banner test matched both
  degrade banners (filter by message now); three GUI tests hit
  build-phase mock call history (Stack.set_visible_child_name from the
  saved-view restore, note_label()'s construction-time hide) — reset_mock
  before asserting. Affected suites green; FULL SUITE green twice (no soaks,
  0 failures) — rerun after the vmid revert. ruff check/format clean, py_compile clean, mkdocs build
  clean (Zensical warning is the parked PREEXISTING one). Awaiting
  version/commit instructions.
- Docs updated: gtk-gui.md (switcher paragraph, Alignment View +
  Survey dialog subsections, Survey… action row), python-modules.md
  (four new module sections + feature_config/repo rows + [ds-alignment]
  link), data-structures.md (Alignment samples section),
  messages/index.md (alignment_dialogs INFO row — appended, user
  hand-edits preserved), testing.md (three new suite rows + added the
  previously-missing test_memory_page row, which was a docs drift).

- Smoke test 2026-10-07 (worktree): user hit one real GUI bug —
  section_header/show_note embed caller text in Pango markup without
  escaping, so the "Findings & Recommendations" title (bare &) aborted
  markup parsing and rendered an empty label (Gtk-WARNING on stderr;
  invisible under mocked-GTK tests). Fixed in gui_helpers with
  GLib.markup_escape_text (house precedent at the clone-row renderer);
  test_support's mock_gtk now provides a REAL markup_escape_text on the
  fake GLib so note/header assertions see strings (everything else on
  GLib stays auto-mocked). Worktree gotchas: docs/site is gitignored so
  a fresh worktree must run `cd docs && mkdocs build` before
  test_gui_infrastructure's anchor tests and path_utils' local-site
  resolution pass (they fail with FileNotFound / deployed-path fallback
  otherwise); the worktree also lacks the user's untracked
  tests/test-itf-driver, hence 86 suites vs the main tree's 87. Full
  suite green in the worktree after the docs build.
- RELOCATED 2026-10-07 to the main checkout per user instruction (fold the
  changeset into main, drop the worktree). All 25 paths moved
  worktree→main via tar, byte-verified with cmp; both changesets share
  base 200577d with disjoint paths, so the union is conflict-free
  (blocksize: 18 tracked +768/−127 plus 2,900 lines across 7 new files;
  itf: 9 tracked +117/−23 plus test-itf-driver). Backup tarball kept at
  /tmp/blocksize-worktree-backup-20261007.tgz (ephemeral). Orphaned
  test-mock processes left over from worktree suite runs were reaped.
  The `blocksize` branch label was deleted 2026-10-07 at user request
  (plain `git branch -d` sufficed — it held no commits beyond main).
  Post-move verification in the main checkout: ruff check + format clean,
  mkdocs build clean, affected suites green (the ten alignment/repo/
  helper/docs suites, incl. test_docs_integrity against the rebuilt site).

## 2026-10-07/08 — itf cycle-2 redo: prior kickoff changeset discarded, re-derived, re-verified

- User instruction: discard the ENTIRE uncommitted cycle-2 kickoff
  changeset (from the earlier 2026-10-07 session) and redo the work under
  an approved plan. Safety fence before the discard: /tmp/itf-cycle2-
  kickoff-changeset.patch plus copies of test-itf-driver, repair-plan 012
  and SESSION_NOTES (/tmp is ephemeral — the patch is the only durable
  copy until the tree is committed). The F-012 FINDINGS row and
  repair-plan 012 went into the discard too (user choice): no tracked
  record of the documented-recipe udev race remains; live evidence
  survives in results/run-20261007-152717-j04 (gitignored) and the
  testing.md recipe itself is unchanged (its fix was never approved).
- Redone in-tree, same scope re-derived: `itf` driver `set -euo pipefail`
  (journey/template-build entry points stay errexit-suppressed via
  `local rc=0; … || rc=$?`; ~10 empty-tolerant guards on live-but-fallible
  reads — unreachable-base paths report empty/(unreachable), never abort);
  template-lib upgrade command rebuilt as ONE `+=`-assembled variable
  (itf_guest_exec takes the whole command as a single argument — the
  commit-time rewrap in 548194d had split it into four quoted strings,
  truncating at "-qq"); `_journey_exit_cleanup` return 0 (an EXIT-trap
  handler ending in a false guard rewrites green rc to 1 under set -e);
  j01/j04 pool-recipe heredocs hardened with `udevadm settle` + bounded
  /dev/sdb15 wait; NEW tests/test-itf-driver (dispatch smokes against a
  .invalid fixture config); os-upgrade single-argument unit pin in
  test-itf-template; strict-mode design paragraph in
  developer-guide/integrated-testing.md.
- Live re-verification on zfstestvm1: prior guests destroyed; template
  REBUILT on the redone code (vmid 8000, stamped dev-tarball 0.118.0
  rev=200577d, built 2026-10-08T02:15:14Z — the fixed upgrade command ran
  live); campaign J01→J02→J03→J04 chained: ALL GREEN rc=0 (J04: 14 steps,
  12 pass / 0 fail / 2 info). PREEXISTING strict-mode entry removed after
  the green campaign (2 entries remain, both parked by user decision).
- GOTCHA (operational): campaign attempt 1 (launched 20:40 EDT) was
  killed EXTERNALLY at 21:03:54 mid template-build shutdown — script,
  itf driver, and the ZCode background-exec shell all died silently in
  the same instant, with the template build ~95% done. No code cause
  found (every construct at the death site is guarded; no error text;
  kernel log not readable as dan). Attempt 2, launched fully detached
  (setsid nohup + own log + watcher), completed cleanly. Long itf
  campaigns should launch detached, not through a session exec.
- Standards: shellcheck via the documented command clean (includes the
  new suite); bash -n + ≤100 columns verified on every changed file;
  docs site rebuilt (rc=0, known mkdocs-material banner); docs-integrity
  (23) + startdocserver (15) + page-anchor audit green. Reminder:
  docs-integrity is a PYTHON suite — its bare name passed to
  tests/run-tests fails as `bash: test-docs-integrity: No such file or
  directory`.
- Awaiting version/commit instructions. 0.118.0 (200577d) is still
  unpushed, so folding this changeset into it remains an option per the
  0.117.0-continued precedent.

## 2026-10-08 — six-step wrap-up over the stacked changesets (alignment + itf cycle-2)

- Step 1 PREEXISTING: both remaining entries are user-parked (Zensical
  1.x wait — rechecked, PyPI now 0.0.69, still no 1.x; infra-vdev
  planning deferral). No actionable items; recheck date updated in the
  entry. 2 entries remain.
- Step 2 standards: ruff check + format clean; documented shellcheck
  command clean; bash -n + ≤100 cols on every changed bash file;
  py_compile clean. Reviewer judgment recorded: alignment_stats
  deliberately imports memory_stats._parse_iostat_cell (private) for the
  shared iostat cell grammar — documented in both module docstrings,
  policies silent on it, accepted. Gtk.STOCK_* in alignment_dialogs is
  the house-wide GTK3 pattern.
- Step 3 tests: found+fixed one defect — the new
  TestSectionHeaderAndNoteMarkup class in test_gui_helpers.py sat AFTER
  the `if __name__ == "__main__"` guard (pytest collected it, but direct
  execution exits at unittest.main() and never runs those tests); guard
  moved back to file end. Coverage of all new units verified present;
  runners auto-discover the new suites (find tests/test-*; pytest
  tests/python); no manifest entries needed (fully mocked). Affected
  suites green.
- Step 4 docs: diffs reviewed accurate vs code (user hand-edits left
  untouched); docs-integrity green; site rebuilt (rc=0, parked
  mkdocs-material banner); gui-infrastructure anchor tests green against
  the rebuilt site.
- Step 5 full suite (no soaks) launched in background after ALL edits:
  87 suites, all green, 0 failed, 1 skipped (test-zfslockmanager-soak —
  soak suites excluded by design in a no-soak run), rc=0. Nothing to
  resolve; no new pre-existing issues found.
- Step 6: codebase frozen at this point.

## 2026-10-08 — itf cycle-2 bring-up (two-node j05 on zfstestvm1+2)

Parts B (harness) + C (suites) landed first; then environment (vm2
storages mirroring vm1's Phase-0 layout, both ISOs uploaded, vm1 stale
guests 8001–8004 destroyed, both base OSes apt-upgraded — vm1 rebooted
onto 7.0.14-22; site config now carries the two-node keys; preflight
all-green across both bases).

Compute-template bring-up (PVE 9.2-1 ISO → auto-install → template)
shook out four real bugs, all fixed in-tree:

1. **grub El Torito LBA**: genisoimage does not re-patch grub's boot
   image; its boot sector carries a 16-byte load record at offset 8
   {2048-sector count, ABSOLUTE load LBA, byte size, tag} written by
   xorriso at stock-master time. A rebuilt ISO moves the boot image,
   boot.img then fetches its core from the stock sector number and the
   guest hangs silently after "Booting from DVD/CD...". The customize
   step now re-points the LBA at the rebuilt catalog's RBA (python
   patch, fail-loud gate on the stock value). Boot catalog pointer at
   VD+71 is little-endian; sector-count field in the default entry
   reads `04 00` in both stock and rebuild (LE) — NOT the
   discriminator; -boot-load-size was never the bug.
2. **Dotted fqdn required**: with [network] from-dhcp the autoinstaller
   aborts on a bare-label fqdn ("either a fully-qualified domain name
   or extended configuration for usage with DHCP must be specified") —
   the assistant's validate-answer does not catch it. Qualify with
   .localdomain (same domain as the Debian preseed) BEFORE the ISO
   stamp is computed so the cache tracks what was written.
3. **deb822 Enabled join**: stock pve-enterprise/ceph .sources end
   with a trailing blank line; appending "\nEnabled: false" after it
   starts a headerless stanza 2 that apt rejects ("Malformed stanza 2
   (type)"). The first-boot hook now rewrites the file with trailing
   blanks stripped + exactly one newline, then appends the field INTO
   the existing stanza. (Also: a deb822 file carries no Enabled line
   while true — substitution patterns silently match nothing.)
4. **Reboot-probe silence**: the upgrade stage's reboot decision once
   swallowed an empty probe answer (transport blip right after the
   package churn) and skipped a required reboot; the boot gate caught
   it (running 7.0.2-6 vs installed 7.0.14-22). The probe now always
   answers yes/no, retries 3×, and fails loudly with its own log —
   empty can no longer mean "no".

Guest triage without an agent channel: root-ssh keys from answer.toml
land at install time, so link-local IPv6 through the base
(ProxyCommand -W [%h]:%p, zone %vmbr0) reaches the guest even when
discovery can't.

### j05 first live runs (2026-10-08, same evening)

Run 1 died at the P2P gates: the installer's Step 4 checks use plain
BatchMode ssh (no host-key options) and RELY on the user having ssh'd
to the peer at least once before installing — that first-connection
acceptance is now modeled as explicit Stage N pre-work (accept-new pair
both directions), keeping the gates a verbatim installer mirror.

Run 2 died at stage_download: the serve dir mkdir lived only in the
install path; clone-start journeys (j05) now mkdir it themselves
(common.sh).

Run 3 got through clone/link/pools/download/prereq-delta and died at
install-two-node's compute activation — **F-012** (deploy.conf path
drift: installer writes /etc/zfsutilities/deploy.conf, deploy-version
reads /etc/zfsutilities-deploy.conf; no groups found → no compute sync
→ switch-version on a missing tree, rc=127). Repair plan 012 written;
PAUSED for user approval per the cycle discipline. The plan's
"compute-side rsync absent" suspicion is disproven (rsync present on
PVE compute host).

Failed-run guests destroyed after evidence capture (runs 1-3 dirs
retain all logs).

Runs 4-5 after plan-012 execution (user-approved 2026-10-08, plus a
standing grant to continue repo corrections): run 4 installed
end-to-end (rc=0) after the Stage I feed gained the missing empty
IQN-default line; run 5 verified the storage host fully (targets
present) and exposed **F-013** on the compute verify —
`is-active iscsid` fails because Debian socket-activates iscsid
(service unit disabled by design, socket listening); tweety shows the
same production state. Repair 013 executed: readiness step hoisted to
run on both found/installed paths asserting `iscsid.socket`, journey
Stage V checks the socket, test-installer-checks 33/33 green with
file-swap red-proof. j05 run 6 pending.

Run 6: compute verify green after repair 013 (iscsid.socket), Stage W
advanced to qm create and failed on my journey-side scsihw typo
(`virtio-scsi` → `virtio-scsi-pci`, fixed). Run 7: qm create green,
then **F-014** — new-vm-disk's delegated storage half dies at the
storage guest's own unconditional `command -v qm` gate (the two-node
design re-invokes 4 scripts on the storage host where no PVE exists).
Production tweety↔stewie only works because pve-manager/qemu-server
were manually installed on stewie Aug 22 (live-verified, look-only) —
undocumented, never ensured by the installer. Repair 014 executed:
role-aware gate (exempts is_two_node && my_host == storage_host) in
new-vm-disk/resize-vm-disk/remove-vm-disk/list-vm-disks; new suite
test-vm-disk-two-node-gate 4/4 green, red-proven vs HEAD; siblings
green. j05 run 8 pending.

Run 8: F-014 repair verified live (delegated storage half runs past
the gate), advanced to the zvol create, exposing **F-015** —
`<pool>/proxmox` parent dataset absent: enroll_two_node never ensures
it (single-node path is the sole creator tree-wide; no installer/doc
step). Repair 015 executed: enroll_two_node ensures the dataset
(dry-run aware, FATAL on failure); 3 new two-node tests in
test-enroll-proxmox-pool (26/26), red-proven vs HEAD. j05 run 9
pending.

Run 9: F-014+F-015 verified live (delegated half runs, zvol + LUN
created); rescan-storage then FATALed "No active iSCSI sessions".
Live guest forensics: discovery worked but login refused — error 24
authorization; fresh TPGs run generate_node_acls=0 with an EMPTY ACL
list; nothing tree-wide manages ACLs (**F-017**, setup-iscsi-targets'
own comment intended demo mode). Same log exposed **F-016**:
safe-iscsi-save FATAL was ignored ("✓ Configuration saved" printed
after it) and the expected-backstores manifest can never bootstrap
(add guarded on file existing). Repairs 016+017 executed: rc guards
at 5 call sites + manifest bootstrap + demo-mode ACL flip guarded by
ACL-presence check; new suite test-iscsi-fresh-install-guards 5/5,
red-proven vs HEAD; affected iscsi suites green; j05 VM-disk step now
verifies the scsi0 config line, not just rc. j05 run 10 pending.

Run 10: F-016+F-017 verified live (honest save, manifest bootstrapped,
session logged in, rescan ran) but the disk still never reached the VM
config. Guest forensics found **F-018**: (a) compute-side LUN lookup
greps `' name '` space-anchored while targetcli emits
"[block/name (/dev/…)]" — never matches, scsi0 line never written
(storage-side twin unanchored + production-proven); (b) rescan-storage
counted by-path entries before udev settled (0 reported, device
appeared seconds later). Repair 018 executed; suite now 7/7 red-proven.
j05 run 11 pending.

**Run 11 (2026-10-08 23:09): j05 GREEN — 36 steps, 0 fail.** The full
two-node journey runs end-to-end: dual-guest clone, P2P link, pools,
install-two-node, dual-host verify, enroll, VM 101 + first LUN with
scsi0 line, LUN visible on compute, target config saved. All findings
F-012..F-018 flipped to verified; repair plans 012–018 closed.
Fresh-install bug families this journey exposed (all repaired in-repo):
config path drift, socket-activation readiness, delegated-role gates,
dataset/bootstrap contracts, ACL admission, hidden rc failures, output
format assumptions, udev settle.

Production incident 2026-10-09: `sudo archive-vm 205` on tweety FATALed
"No referenced zvols found for VM 205". Root cause (read-only forensics,
deployed 0.119.0 == tree): two-node discovery joined each ref as
"target:lun" but an IQN contains its own colon
(iqn.2026-02.local.stewie:threeamigos — per-pool targets from
enroll-iscsi-pool); the storage-side helper split refs on the FIRST
colon → target "iqn.2026-02.local.stewie", lun "threeamigos:11" → no
such target → every ref WARNed "no backstore was found" → zero zvols.
Latent since per-pool enrollment; the test ssh-mock mirrored the
encoding (matched any iqn.*:* arg) instead of executing the helper, so
the suite was blind. Second latent defect in the same run: the
.disk_info sidecar's LUN lookup grepped " ${backstore} "
space-anchored against targetcli's slash-prefixed "[block/name
(/dev/…)]" luns-ls output — never matched, sidecar silently never
written in two-node mode (same class as itf F-018 in new-vm-disk; that
copy was fixed, this one missed). Fixes in bin/archive-vm: target and
lun now travel as separate ssh argv entries (remote loop consumes
pairs); sidecar grep anchored on "block/<name> " (slash prefix +
trailing space — also immune to disk-1 vs disk-10 substring matches,
a hazard the new-vm-disk F-018 form still has, recorded in
PREEXISTING.md). Regression tests in test-archive-vm (argv encoding +
grep-form pin), red-proven vs HEAD by file-swap. Live verification via
configfs (readable as non-root): threeamigos LUN 11 → disk-0, LUN 12 →
disk-1; nvme1 LUN 1 → NVME1 disk-3; the three fivebays/* vm-205 zvols
back no LUNs (stale duplicates — user to decide cleanup; they are
warned as orphaned and skipped, per the user's requirement that only
config-referenced items are archived). Deploy reminder: this fix rides
the pending uncommitted changeset; archive-vm 205 on the nodes will
succeed only after the user runs deploy-version.

## 2026-10-09 — wrap-up step 1: luns-ls grep family repair

The recorded PREEXISTING entry (new-vm-disk unanchored LUN grep,
disk-1 vs disk-10 prefix hazard) turned out to be one member of a
family. A tree-wide scan of every `tpg1/luns ls` pipeline found 19
lookup/guard sites across 12 scripts in three defect classes:

- unanchored name greps (match, but a prefix name matches the wrong
  line): new-vm-disk ×2, remove-vm-disk, clone-vm, zfsclone-vm,
  move-vm-disk ×3, zfs-diagnose-busy
- space-anchored greps that NEVER match the real line shape
  `o- lun3 [block/<name> (/dev/...)]` (same class as itf F-018 — dead
  guards/idempotency checks): attach-vm-disk ×2 (LUN_EXISTS detection
  dead → duplicate-LUN create path), remove-vm, move-vm-disk:287
  (teardown guard), unarchive-vm ×2, ensure-restored-vm-iscsi,
  rename-vm-disk ×2
- lun-token grep without delimiter (`lun1` matches `lun19`; saved only
  by a downstream digit check): enroll-efi-keys-vm — now anchored
  `lun<N> ` so line selection itself is precise

All fixed to the live-verified form `grep -F "block/<name> "` (the
archive-vm sidecar form, cross-checked against configfs in
production); positional parsers (list-vm-disks, restart-iscsi-services,
repair-iscsi-luns) were verified correct and untouched.

Guards: test-iscsi-fresh-install-guards' new-vm-disk-only pin replaced
with a family-wide awk scan (every luns-ls pipeline must anchor its
grep on block/, lun-keyed greps exempt); red-proven for both defect
classes by file-swap. test-zfs-diagnose-busy's luns fixture was
truncated at `]` (missing the ` (/dev/...)` tail the real format has)
and went red under the anchored grep — fixture corrected to mirror the
real line. All suites for touched scripts green. The two remaining
PREEXISTING entries (Zensical 1.x wait; infra-vdev planning UI) are
non-actionable by design.

## 2026-10-09 — wrap-up steps 2-4 (standards, tests, docs)

Step 2: shellcheck clean over the full documented lint scope (bin/*,
lib/*, tests, itf, journeys). One 100-column violation fixed in
lib/installer-lib.sh (the iscsid.socket ssh assertion wrapped in the
repo's in-string continuation style). No installation-specific data in
mainline code; j05 journey pool/device names are itf conventions
mirroring the documented install recipe.

Step 3: no obsolete pins (old iscsid.service wording, legacy-only
deploy path, space-anchored luns greps all absent from suites).
Coverage verified for the whole changed surface; vm-disk family relies
on structural suites by established design. Added the missing
enroll-efi-keys-vm lun-token delimiter pin (red-proven by file-swap)
to test-iscsi-fresh-install-guards.

Step 4: docs drift repaired — messages manual gained the shared
safe-iscsi-save FATAL template, new-vm-disk manifest row,
setup-iscsi-targets demo-ACL rows, deploy-version legacy-fallback row,
unarchive SAVE_FAILED row, and the full installer prereq-offer rows
for both helpers (target stack + open-iscsi, including the changed
iscsid.socket ready-state wording — these had never been cataloged).
commands.md deploy-version/install-two-node rows moved to the modern
/etc/zfsutilities/deploy.conf path (legacy noted); enroll-proxmox-pool
dataset ensure now documented for both modes; installation/index.md
iscsid wording; two-node.md setup-iscsi-targets step list gained the
demo-ACL bullet. Docs integrity 23/23; site rebuilt (known
mkdocs-material MkDocs-2.0 warning only — PREEXISTING).

## 2026-10-09 — wrap-up steps 5-6: full suite + freeze

Step 5: full suite without soaks (tests/run-tests --log
/tmp/zfs-wrapup-full.log), background: 89 suites, all green, zero
failures; the single skip is test-zfslockmanager-soak (soak suites
excluded by design in a no-soak run). Nothing to resolve; no new
pre-existing issues surfaced.

Step 6: codebase frozen at this point. PREEXISTING.md holds 2 entries,
both non-actionable by design (Zensical 1.x wait; infra-vdev planning
UI in abeyance per user decision).

## 2026-10-09 — promote-vm-clone 211 two-node failure forensics

`sudo promote-vm-clone 211` on tweety (both nodes freshly switched to
0.120.0 at 14:25/14:26) promoted vm-211-disk-0 and then died silently
before disk-1: "FATAL: Promotion failed on stewie" with no remote
output at all. Root cause proven by repro (production zfslockmanager
sourced with stubs): `zfslock_release` ends with
`temp=$(grep -v "^${lock_id}$" "$pidfile")` — releasing the LAST lock
held by a process empties the grep output, rc=1, and the remote
heredoc's `set -e` kills bash mid-loop with zero output. Forensic
chain: tweety local log 14:35:38→14:35:48; stewie .locks mtime
47.997 (disk-0 lockfile rm inside release), .pids mtime 47.999 (EXIT
trap), no session log on stewie (bash -s heredocs fail bashinit's
BASH_SOURCE[1]==$0 log-file condition), no zfs error text ever
(release dies before the ✓ log lines, which are ordered AFTER release
in the remote heredoc — unlike the single-node branch). VM 211 being
running is unrelated: promote is metadata-only and disk-0 promoted
under the running VM.

Recovery for 211: re-run promote-vm-clone 211 (lists only disk-1 now;
will promote it then FATAL again at release — work complete despite
the message), or `sudo zfs promote threeamigos/proxmox/vm-211-disk-1`
on stewie directly.

Bug family — bare `zfslock_release` under `set -e` in two-node remote
heredocs: promote-vm-clone:142 (live failure), zfsclone-vm:459-460
(dies before udev/backstore phase), move-vm-disk:346-347, rename-vm-disk
376-377/564-573, unarchive-vm:500. clone-vm immune (success-path
releases are local, outside set -e). Same-family latent:
`((removed++))` in zfslock_cleanup_stale (first stale removal also
kills under set -e). Fix not yet planned/approved.

## 2026-10-09 — set -e lock-release fix implemented (uncommitted)

User approved the proposed fix after the forensics above (and re-promoted
vm-211 disk-1 successfully, matching the prediction — FATAL after the work
completed). Changes:

- bin/zfslockmanager: zfslock_release's pidfile rewrite grep gains `|| true`
  (grep exits 1 when the released lock is the pidfile's last line — killed
  set -e callers silently); zfslock_cleanup_stale's `((removed++))` →
  `removed=$((removed + 1))` (post-increment returns status 1 on the first
  removal). Fixes the whole two-node heredoc family at the library level
  (promote-vm-clone, zfsclone-vm, move-vm-disk, rename-vm-disk,
  unarchive-vm remote branches).
- bin/promote-vm-clone: both branches now log the ✓ lines BEFORE
  zfslock_release, so a release-time failure can never suppress the success
  record (this ordering is what made the 211 failure totally silent).
- tests/test-zfslockmanager: new test_set_e_safety (3 tests) — child scripts
  mirror the remote heredocs (source manager, then set -e) and assert a
  SURVIVED marker; red/green proven against a scratch copy with both fixes
  reverted (all three fail) vs the fixed tree (suite green).
- docs: lock-manager.md notes the set -e safety contract.

Test-authoring gotcha (cost a long debug loop): heredoc escape processing
applies to the heredoc's own text, NOT to values arriving via parameter
expansion — a body string passed as `"\$zfslock_id"` lands in the generated
child script verbatim with the backslash, so the child released the literal
string `$zfslock_id` (nonexistent file → early return 0) and the tests
false-passed. Single-quoted body args must use plain `$var`. Also:
`_bg_lock_start`-style `\$` escapes are correct only in heredoc source text.
Coverage gap noted: no test suite exists for zfsclone-vm at all (suite name
in run-tests fails as "No such file or directory" — known runner quirk).

## 2026-10-09 — backup property-fidelity design: user decisions (no code)

Continues the backup-fidelity assessment/design thread (backups are data-only
`-cw` everywhere; property-manifest + restore-replay design under discussion).
Decisions from the user this turn:

- archive-vm as evidence for 2.4.4 `zfs receive -o volblocksize` is
  DOWNGRADED to unverified — it hardly runs and has separate bugs in flight;
  stewie's 2.4.4 zfs-recv(8) man page never mentions volblocksize. It is an
  itf-matrix question, not a fact.
- ZFS-behavior validation belongs in itf guests (any OS installable), not the
  dev host. Matrix: -o volblocksize receive per version (unencrypted zvol),
  volblocksize-on-filesystem, no-reblock/recompress on receive, keylocation
  reset + set/load-key, receive-as-encrypted, encrypted-raw volblocksize
  refusal, encryptionroot-self on raw receive.
- Dev host (Linux Mint 22.3 = noble base) KEEPS OpenZFS 2.2.2 deliberately as
  the legacy/compat leg of the matrix — noble ships 2.2.x for its lifetime; a
  real upgrade means OS base change or self-owned DKMS, rejected for the
  shared dev host. Stay SRU-patched (backdated ≠ unpatched).
- Code must track OS/ZFS capabilities and degrade: version-gated caps table
  keyed on min(userland, kmod) — tweety is a real 2.3.9-userland/2.4.4-kmod
  split; bash-side helper for the engine, app.ctx.zfs_caps for the GUI.
- The encryptionroot-receive behavior (received copy = its own encryptionroot,
  keylocation→prompt) is undocumented upstream — document it in OUR docs; not
  code-fixable.
- "Restore with encryption" (receive unencrypted source as encrypted via -o
  on initial receive) APPROVED as a feature.

## 2026-10-09 — sever-vm-clone task 1.1: skeleton, guards, discovery (no code beyond)

Drop-promote workflow, leaf task 1.1 (workflow dwfrun-26207719):
- bin/sever-vm-clone created (400 lines): vm-disk family bootstrap (bashinit,
  node-lib, rootcheck, zfslockmanager init, qm guard), vmid and dataset
  argument modes with validation, two-node delegation to the compute host
  modeled on promote-vm-clone, discovery gather (single-node local; two-node
  ssh heredoc on the storage host) emitting tagged VOL/NOTVOL/MISSING records
  plus a --POOLS-- free-space section, plan display (per disk: zvol, owning
  VM, origin, used vs referenced full-copy size; per pool: largest-disk x 1.1
  free verdict), same-pool-temp-namespace vs holding-pool recommendation,
  ask_yn confirmation gate, and empty sever_transfer()/sever_cutover()
  extension-point stubs for the later transfer/cutover tasks.
- Design note: the space math uses `referenced`, not `used` — a full copy of
  a clone writes every block the clone references (shared + unique); `used`
  alone would badly understate a fresh clone's copy size. Both are shown.
- sever-vm-clone added to tests/test-proxmox-required-guards GUARDED_SCRIPTS
  and tests/test-lock-coverage (bootstrap entries only; acquire-pattern
  entries land with the transfer task). shellcheck clean (0.9.0).
- Smoke-tested all interface paths against fake zfs/zpool/qm/ssh under /tmp
  (usage/no-args, vmid found + not-found, dataset skip INFO lines for
  non-clone/non-zvol, MISSING abort, dedupe, holding-pool recommendation,
  confirm y/n, two-node delegation quoting, two-node ssh gather both modes).
- Pre-existing discovered: bare `rootcheck` call is advisory-only family-wide
  (returns 1, callers ignore) — recorded in PREEXISTING.md.
- Docs intentionally untouched: the promote-vm-clone removal/reference sweep
  is a separate workflow task that owns those files.

## 2026-10-09 — sever-vm-clone task 3.1: promote-vm-clone deleted, archive-vm re-pointed

Drop-promote workflow, leaf task 3.1 (workflow dwfrun-26207719):
- bin/promote-vm-clone deleted outright (working-tree rm; its uncommitted
  lock-release-order tweak from the earlier session is subsumed — zfs promote
  severs nothing, it inverts the clone and pins origin-snapshot space).
- bin/archive-vm re-pointed end to end: header and usage step 3 now describe
  severance; the Step-1 dependent-clone offer now (1) verifies every dependent
  clone VM is stopped via `qm status` first, aborting FATAL with stop-and-
  rerun guidance if any runs (severance swaps zvols under live names), then
  (2) invokes `sever-vm-clone <clone_vmid>` per clone VM via
  find_zfsutility_script, aborting on its failure. Declining keeps the warning,
  reworded to name the tool: removal may fail while snapshots are held by
  clones; sever them first with sever-vm-clone.
- tests/test-archive-vm: promote stub → sever-vm-clone stub (records
  SEVER:<vmid> in capture/severances); the two promote tests became sever
  equivalents — the confirm test now uses two clone VMs and asserts exactly
  one invocation each before the archive proceeds — plus a new test for the
  running-clone abort (qm mock honors _mock_clone_vm_status for every VM
  except the archived one via _mock_archive_vmid).
- Promote rows removed from tests/test-lock-coverage (the sever-vm-clone
  bootstrap rows from task 1.1 stay) and the promote entry removed from
  tests/test-proxmox-required-guards GUARDED_SCRIPTS (sever-vm-clone stays).
- Remaining promote-vm-clone references (bin/zfsclone-vm, zfs-diagnose-busy,
  zfsdelfs, python/gui_helpers.py, docs/, PREEXISTING.md's rootcheck example)
  are owned by other tasks in this workflow; not touched here.

## 2026-10-09 — sever-vm-clone task 3.2: guidance strings re-pointed to severance

Drop-promote workflow, leaf task 3.2 (workflow dwfrun-26207719):
- bin/zfsclone-vm: header note (line 12) and both "Done" blocks (single-node
  ~314, two-node ~578) now read "To sever the clone dependency before
  retiring VM <srcvmid>: sever-vm-clone <dstvmid>"; "cut dependency"/
  promote-vm-clone wording gone.
- bin/zfsdelfs: both FATAL clone-dependent gates (~154, ~165) now say
  "Use sever-vm-clone to sever the dependencies first."
- bin/zfs-diagnose-busy: both WARN clone-dependent actions (58, 68) now say
  "Use 'sever-vm-clone' to sever the dependencies first." — the 'zfs promote'
  alternative is dropped entirely, per the task.
- python/gui_helpers.py: both BusyReason clone actions (1156, 1172) match the
  zfs-diagnose-busy wording; quoted-tool style preserved.
- Grepped tests/ (bash + python + golden) for "promote-vm-clone", "zfs
  promote", "cut dependenc*", "To cut", "retiring": no test asserts the old
  strings, so no assertion updates were needed. tests/integrated/cache hits
  are an unrelated PVE rootfs cache.
- Docs (docs/docs/messages/index.md rows 505/506/801 etc.) still name
  promote-vm-clone — owned by the separate docs sweep task, not touched here.

## 2026-10-09 — sever-vm-clone task 1.2: Phase 1 transfer via the migration engine

Drop-promote workflow, leaf task 1.2 (workflow dwfrun-26207719):
- bin/sever-vm-clone: sever_transfer() implemented on top of the task-1.1
  skeleton. One bucket-less snapshot name per run, sever-$(snapname_timestamp)
  (pinned in tests/test-snapshot-names' producer table); per selected disk,
  sequentially under 'w' zfslocks on the source zvol and the temp parent: the
  snapshot (reused if it already exists), a full copy through the migration
  engine, refreservation=none on the received zvol (project zvols are sparse;
  plain receives re-reserve), and the received snapshot's GUID
  (zfs get -Hp -o value guid). The temp parent <pool>/proxmox/sever_<vmid>
  (zvol basename when the name carries no VM id) is created once under a 'w'
  lock on <pool>/proxmox; the namespace is deterministic so interrupted runs
  find their receive resume tokens and re-run (a resumed stream that completes
  under an older @sever-* name is detected, WARNed, and recorded under that
  name). The whole storage-side sequence lives in one worker script
  (sever_storage_transfer_script) run as a child shell — directly via
  process substitution in single-node mode (interactive lock resolution and
  terminal pv progress preserved), streamed over ssh bash -s in two-node mode
  (move-vm-disk's storage_move_script pattern; remote conflicts abort
  headless with holder details). Results cross back via a records file
  (<zvol> <temp zvol> <snap> <guid> per line) into sev_temp_name /
  sev_recv_snap / sev_snap_guid for the cutover phase, which remains the
  sever_cutover() extension point.
- bin/zfs-migrate-send: failure remediation text is caller-aware via
  $restart_hint (default 'Migrate Pool', so wizard output, tests, and golden
  text are unchanged); sever-vm-clone's worker assigns restart_hint=
  sever-vm-clone so the re-run hint names the severance. Header documents
  the variable. Docs rows updated surgically (messages/index.md zfs-migrate-send
  FATAL row; commands-and-modules/commands.md exit-code 8 row).
- Space pre-check (1.1 headroom) emits a WARN per deficient pool at the start
  of the transfer phase and proceeds same-pool (holding-pool mode is a later
  task); the WARN says a full pool suspends the receive with a resume token.
- Smoke-tested the worker end to end with mocked zfs + stubbed engine under
  /tmp/severtest: fresh two-disk run, idempotent re-run (snapshot reuse,
  namespace kept), resume edge (old-snapshot completion), and lock-conflict
  abort from a concurrent holder (holder details logged, no snapshot taken,
  locks left clean).
- Checks: shellcheck bin/sever-vm-clone bin/zfs-migrate-send clean;
  tests/run-tests test-zfs-migrate-send test-transfer-lib test-lock-coverage
  test-proxmox-required-guards test-snapshot-names — all pass (re-run after
  the sibling promote-deletion task landed in the shared tree).

## 2026-10-09 — sever-vm-clone task 1.3: Phase 2 cutover, name-preserving swap (single-node)

Drop-promote workflow, leaf task 1.3 (workflow dwfrun-26207719):
- bin/sever-vm-clone: sever_cutover() implemented (single-node; two-node
  keeps the WARN-and-stop stub for the later iSCSI task). Gates first that
  every owning VM (vm-<id>-disk-<n> names) is stopped via qm status — FATAL
  with guidance naming the exact --continue command; zvols whose names carry
  no VM id WARN and proceed (nothing to gate; a busy zvol fails the destroy
  safely). Then per disk, sequentially: bucket-less @sever-<ts>-cutover
  snapshot, catch-up incremental through the migration engine's fromsnap
  path (zfs send -RIw @transfer→@cutover; zfs-migrate-send already supported
  $fromsnap), pre-destroy GUID verify of the cutover snapshot source-vs-copy
  (mismatch aborts with nothing destroyed; also guards the crash-between-
  receive-and-marker case by reusing an already-received identical snapshot
  instead of erroring into the receive), holds capture+release on the
  original via zfsreapplyholds with the no-lock flag, destroy of the
  original, zfs rename of the temp into the original name, udev settle +
  /dev/zvol block-node wait (SEVER_ZVOL_DEV_PREFIX test knob, the
  ZFSLOCK_DIR pattern), post-swap GUID check against the recorded value, and
  reapply of the captured holds onto the swapped-in zvol (replication
  preserves snapshot identity, so the same names/GUIDs exist). Locks: 'x'
  (destroy-class) on both the original and temp names for the whole per-disk
  sequence — no w→x upgrade gap between verify and swap. Empty temp
  namespaces removed afterwards (plain destroy only succeeds when empty).
- Cutover state file (/tmp/sever-vm-clone-<key>-<epoch>.state, the
  move-vm-disk pattern) written BEFORE the VM gate so an abort leaves a
  --continue handle that skips the long re-copy; per-disk phase markers
  staged→catchup_done→verified→holds_captured→holds_released→
  source_destroyed→temp_renamed→device_ready→swapped→done, each transition
  persisted. --continue replays any disk from its marker (every step
  idempotent: existence checks before each mutation, GUID-equality reuse of
  a received cutover snapshot, unknown markers replay from staged);
  --rollback reverts everything before the destroy window (temp copies
  destroyed, all @sever-* snapshots removed from the originals, released
  holds reapplied, namespaces/state cleaned) and refuses past it with
  run---continue guidance. Recovery modes are single-node only, skip
  discovery/transfer entirely, and never delegate. State file removed on
  full success (every recovery path is then impossible or a no-op).
- Session-tooling gotcha worth remembering: Edit/Write payloads dropped
  characters twice this session (a quote in a mock; 'er' from
  sever_state_file → sev_state_file in nine spots) — shellcheck passed both
  times; caught only by smoke-running the real flow and an identifier
  audit. Re-verify authored files with grep against intended identifiers
  after writing.
- Smoke matrix (mock zfs/zpool/qm + real engine + real reapplyholds under
  /tmp/sevtest2, fresh world per scenario): two-disk happy path incl. hold
  reapply and GUID-preserved snapshot history; VM-running gate abort +
  --continue completing; injected rename failure landing exactly in the
  destroy→rename crash window + --continue recovering; injected GUID offset
  aborting pre-destroy with originals intact; injected destroy failure at
  holds_released + --rollback restoring the pre-run world; --rollback
  refused past the destroy; dataset-mode orphan zvol WARN-and-proceed;
  already-received cutover snapshot skip branch; recovery-argument and
  malformed-state FATALs; rollback with a running VM WARNs and proceeds.
- Tests pinned to the new code: tests/test-snapshot-names producer row
  bumped (sever-vm-clone now has two sever-$(snapname_timestamp) call
  sites: transfer + cutover); tests/test-lock-coverage gained the cutover
  source/copy 'x' rows and the rollback source 'x' row.
- Checks: shellcheck bin/sever-vm-clone clean; tests/run-tests
  test-snapshot-names test-lock-coverage test-proxmox-required-guards and
  test-zfsreapplyholds test-zfs-migrate-send — all pass. Docs intentionally
  untouched (the workflow's docs sweep task owns sever-vm-clone rows).
- Pre-existing discovered/this task: none new; PREEXISTING.md unchanged
  (the rootcheck advisory-guard entry from task 1.1 covers what resurfaced).

## 2026-10-09 — sever-vm-clone task 1.4: after-swap finishing + origin report

Drop-promote workflow, leaf task 1.4:
- bin/sever-vm-clone: post-swap finishing and the origin-snapshot report
  added on top of the 1.3 cutover. New phase marker scaffolding_cleared
  between swapped and done (rank table updated): under the same 'x' locks,
  sever_destroy_scaffolding <zvol> destroys every @sever-* snapshot the
  replication carried into the swapped-in zvol (@sever-<ts> transfer base —
  or an earlier run's name after a resume — and @sever-<ts>-cutover); the
  prefix, not this run's exact names, identifies the artifacts (only this
  tool creates bucket-less @sever-* snapshots). WARN-only per snapshot: a
  held/busy one is left and reported — the swap is complete regardless.
  Rollback's inline copy of that loop was replaced by the shared helper
  (same behavior, one implementation; originals after rollback keep being
  cleaned). Holds reapply on the new zvol (reapplyholds_apply, the swapped
  phase) and temp-namespace removal once empty (sever_cleanup_namespaces)
  were already in from 1.3 and are unchanged.
- Origin report (sever_report_origins, after namespace cleanup, before the
  completion banner): for each deduped origin snapshot of the severed disks,
  re-reads the live 'zfs list -o clones'. Still-cloned origins are reported
  only (with the clone list); unpinned-but-held origins are reported with
  every hold tag from 'zfs holds'; unpinned hold-free origins are reported
  with their reclaimable size and offered for destruction — ask_yn, then a
  typed confirmation of the FULL snapshot name (zfswipe pattern; a
  non-matching answer leaves it untouched). The destroy re-checks clones and
  holds under a 'w' lock on the origin snapshot's dataset (zfsdelsnap's
  locking shape) so a reference that appeared since the report blocks
  instead of failing; failure runs diagnose_dataset_busy
  (zfs-diagnose-busy, newly sourced). Held and still-cloned snapshots are
  only ever reported, never destroyed — and ZFS itself refuses a held
  snapshot destroy as the backstop. This offer is where the pinned space
  actually comes back. Runs after --continue too (origins come from the
  state file).
- Usage text gained the origin-report paragraph; header comment extended.
- Docs (surgical, additive): lock-manager.md sever-vm-clone row now lists
  the origin snapshot's dataset (release offer) lock; concepts.md's
  Severing a Clone paragraph gained the post-cutover re-check/offer
  sentence. The docs sweep task still owns the fuller sever rows.
- Smoke matrix (stub zfs/qm + real script, /tmp/sever-smoke, fresh state
  files per scenario): --continue from device_ready exercising swapped→
  scaffolding_cleared→done (hold lzo-4k reapplied to the user snapshot, both
  scaffolding snaps destroyed, user @daily snapshot kept, temp namespace
  removed); origin report — unpinned+hold-free offered and destroyed after
  the exact typed name, held origin reported with its tag only, still-cloned
  origin reported only; mismatched typed answer leaves the origin in place;
  --rollback path via the shared helper (staged copy destroyed, both
  scaffolding snaps off the original, holds reapplied, namespace removed).
- Checks: shellcheck bin/sever-vm-clone clean; tests/run-tests
  test-zfsreapplyholds — all pass (zfsreapplyholds itself untouched).
- Pre-existing discovered/this task: none new; PREEXISTING.md unchanged.

## 2026-10-09 — sever-vm-clone task 1.5: holding-pool (intermediate storage) mode

Drop-promote workflow, leaf task 1.5:
- bin/sever-vm-clone: tight-space mode end to end. Discovery now also
  collects pool tags and per-zvol encryption (6th VOL field, `zfs list -o
  ... encryption`); after the per-pool space table, any source pool short of
  largest-disk x 1.1 switches the plan to holding mode: sever_ask_holding_pool
  lists imported candidate pools with free >= the run's staging need
  (deficient source pools excluded — the copies must not land where they
  will be copied back into), FATAL when none exists. The chosen name is
  entered at runtime (ask_line loop: deficient-source or non-imported name
  re-asks; empty answer exits 0; below-need accepted with a WARN).
  Encrypted sources trigger a keystatus check on the holding pool (local or
  ssh in two-node): key not loaded -> WARN "load it first (zfs key -l)",
  plus the reassurance that raw (-w) replication keeps the copies
  encrypted. sever_holding_plan then shows each origin snapshot with its
  destroyability (still-cloned names the sibling clones, held names the
  tag), asks ask_yn whether to destroy them after the severance (default Y,
  sever_origin_destroy), and prints a per-deficient-pool copy-back estimate
  with a FATAL when even destroying the originals + confirmed origins
  cannot free enough (the lightly-diverged-clone explanation).
- Phase ladder renumbered around the new rungs: space_checked before any
  destruction, origin_snap_destroyed, copied_back, copyback_verified,
  holding_freed (state gains space_mode/holding_pool/origin_destroy and
  per-disk back names; sanity WARN if a temp and back name share a pool).
  In holding mode Phase 1 stages into <holding>/sever_<key>/<basename>
  (sever_temp_parent is holding-aware), the cutover catch-up lands there,
  and sever_holding_space_precheck runs BEFORE anything is destroyed: fresh
  zpool free + the original's used + each destroyable confirmed origin
  snapshot's used >= fresh referenced x 1.1, else a plain-language FATAL
  ("a lightly-diverged clone frees little") that explains the copies are
  safe in the holding pool and points at --rollback/--continue. Nothing has
  been destroyed at that point by construction.
- Cutover then destroys the original and, when confirmed, the origin
  snapshots (sever_destroy_confirmed_origin: skips unconfirmed/gone, x-lock
  on the origin dataset, re-checks destroyability under the lock and aborts
  if a sibling clone or hold appeared since it was counted), copies back
  from the holding pool into the source pool's temp namespace via the
  migration engine (full send of the cutover snapshot, refreservation=none
  on the copy-back, GUID-equality reuse of an already-landed copy-back on
  --continue), verifies the GUID, renames the copy-back into place under
  the original name, and finally destroys the holding copy (WARN-only; the
  swap is complete regardless). The copy-back carries its own 'x' lock on
  the holding zvol and a 'w' lock on the copy-back namespace; every failure
  path releases all three locks in order (sever_release_locks). Engine
  failure at the copy-back is the one unrecoverable-by-rollback point (the
  original is already gone) — the FATAL says exactly that and points at
  --continue (engine resume token honored). --rollback before
  source_destroyed still tears the staging down.
- tests/test-lock-coverage: three new sever-vm-clone rows (copy-back 'x',
  origin-snapshot destroy 'x', copy-back namespace 'w').
- Smoke matrix (stateful mock zfs/zpool/qm world under /tmp/sevtest3,
  seven scenarios, 72 assertions): A mixed-pool happy path holding mode
  (tank deficient, staging + copy-back via spare, encryption carried into
  the copies, keystatus WARN, origin snapshots destroyed, holding namespace
  removed); B pre-check FATAL via --continue when a sibling clone keeps the
  origin pinned (nothing destroyed, staging intact); C injected copy-back
  receive failure then --continue to completion (original destroyed past
  the rollback window, holding copy intact until the resumed run swaps and
  cleans); D --rollback from the VM gate; E no candidate pool -> plan
  FATAL; F invalid/deficient holding names re-ask + empty answer exits 0;
  G plan-time estimate infeasible -> FATAL before Phase 1.
- Checks: shellcheck bin/sever-vm-clone clean; tests/run-tests
  test-lock-coverage test-snapshot-names test-proxmox-required-guards —
  all pass.
- Pre-existing discovered/this task: none new; PREEXISTING.md unchanged
  (the engine's bare-rootcheck abort under `set -e` in smoke runs is the
  already-recorded rootcheck-family entry; the test stub works around it).

## 2026-10-09 — sever-vm-clone task 1.6: two-node path

- Delegation moved BEFORE the qm guard: on a two-node box an invocation on
  the storage host (this_host != compute_host) re-execs on the compute host
  with every argument printf-%q-quoted, before `command -v qm` can fire —
  the latent promote-vm-clone flaw (its guard died on the storage host,
  where qm does not exist). All modes delegate, including --continue and
  --rollback (the cutover state file lives on the compute host).
- All zfs/lock/targetcli cutover work moved into one storage-side worker
  (sever_storage_cutover_script, ~1080 lines): single-node runs it as a
  local child shell, two-node streams it as 'ssh root@<storage_host> bash -s'
  under set -e with locks INSIDE (the zfsclone-vm / move-vm-disk pattern;
  the repo zfslockmanager's set -e release fixes are what make releases
  survive inside such a heredoc — the installed 0.120.0 lock manager dies
  at `temp=$(grep -v ...)` on a single-entry pidfile under set -e, seen in
  smoke; the repo's `|| true` at bin/zfslockmanager:1049 is the fix).
- The worker owns the phase markers and rewrites the cutover state file at
  every transition; two-node pushes the state file to the storage host
  before each worker run and fetches it back after (on failure too, best
  effort) so --continue/--rollback resume from the last persisted phase.
  New per-disk fields itgt/ilun/ibs/ienc persist the discovered iSCSI
  state: a replay after the original zvol is destroyed still re-exports at
  the recorded target/LUN/backstore. Phase table gains iscsi_detached (6)
  and iscsi_reattached (13).
- iSCSI rewire per disk (rename-vm-disk discover_iscsi_state pattern,
  anchored parses): discover once and persist; teardown LUN + backstore
  before the destroy (a live backstore pins the device node); after the
  rename + udev wait, re-create the backstore named for the zvol and
  re-export AT THE SAME LUN ID — when the slot was taken meanwhile,
  targetcli auto-assigns, the new number is parsed back (anchored
  grep -F "block/<name> "), and a LUNMOVED marker makes the parent WARN
  about the PVE by-path reference. expected-backstores manifest and
  iscsi-encrypted-luns.conf kept in step; safe-iscsi-save per re-export
  (WARN-only on its degraded rc=1 per its own contract).
- Parent cutover: rescan-storage runs on the compute host at the end when
  any state-file iSCSI record exists (derived from the state file, not
  in-run markers, so a resumed run rescans too); origin report/destroy use
  a read-only ssh zfs wrapper (sev_zfs) and a locked destroy heredoc
  (sever_remote_offer_destroy).
- Smoke evidence (stateful fakes under /tmp/sever-smoke: targetcli with
  case-matched info/set-attribute/create/delete branches, stateful zfs
  dataset/snapshot tree, repo lock manager + reapplyholds in sbin/):
  iSCSI helper suite 41/41 (discovery exact-token vs -1/-10 decoys,
  teardown idempotence, same-LUN reattach, keep-existing replay,
  encrypted bookkeeping, squatter-slot fallback + LUNMOVED); end-to-end
  two-node cutover 28/28 (marker set, phase done + iscs fields persisted,
  teardown-before-destroy / destroy-before-rename / reattach-after-rename
  via a shared order log, scaffolding cleared, locks released, namespace
  cleanup, replay idempotent); two-node rollback 8/8. Repo suite
  tests/test-sever-vm-clone (parallel task) 18/18 against the rewired file.
- Docs: two-node-config.md script-mode row rewritten (canonical compute
  entry, storage-side cutover, same-LUN re-export + rescan);
  messages/index.md gained a sever-vm-clone section for the two-node
  messages (discovery markers, detach/reattach INFOs, LUNMOVED WARN,
  safe-iscsi-save WARN, re-export FATAL + --continue, rescan INFO/WARN).
- Pre-existing discovered/this task: none new; PREEXISTING.md unchanged.

## 2026-10-09 — sever-vm-clone task 4.1: Datasets-page Sever Clone button

- Sensitivity: `update_ds_button_sensitivity` (python/datasets_page.py) arms
  `_ds_sever_clone_btn` when the selection holds at least one clone dataset —
  a pool/dataset row whose Origin column is non-empty and whose zfs type is
  volume (a row built without a zfs type falls back to the vm-<id>-disk-<n>
  basename). New pure helpers next to it: `vmid_of_dataset`,
  `is_clone_dataset`, `sever_clone_datasets` (unique selected clone names —
  never the unselected disks of a VM).
- `get_tree_selection_items` (python/gui_helpers.py) now carries `origin` on
  pool/dataset items (column 6, "" when not a clone) so the page can gate on
  it; snapshot/hold/partition items are unchanged.
- Action: `on_datasets_sever_clone` — typed-confirmation dialog
  (`show_sever_clone_dialog`, "sever" to arm the button, the disk_wipe
  pattern) naming exactly the selected dataset(s), their origin snapshot(s),
  and the owning VM(s) from the disk name, stating the full-copy cost and the
  must-be-stopped-for-cutover requirement; on confirm one BashStep runs the
  sibling `sever-vm-clone` (resolve_local_bin) with the selected dataset
  paths, so its remaining questions arrive through the runner's numbered
  input-hold prompts; completion refreshes the tree and re-runs sensitivity.
- Wiring: PAGE_SPECS["datasets"] gains ("Sever Clone", "edit-cut",
  "_ds_sever_clone_btn") and ACTION_HANDLERS maps it to the handler
  (python/action_dispatch.py).
- Tests: tests/python/test_datasets_page.py gained Sever Clone suites
  (helpers, sensitivity, typed-confirmation gating + dialog content, argv
  build, handler gating/runner wiring/completion logging).
- Docs: Datasets action-button table row in user-guide/gtk-gui.md (links to
  concepts.md#severing-a-clone); datasets_page.py section of
  commands-and-modules/python-modules.md mentions the action, the new key
  function, and the command_builders/path_utils helpers.
- Pre-existing discovered this task: 2 (dangling sever-vm-clone-both doc
  anchors failing test_docs_integrity; input-hold env lost over the
  script's two-node SSH delegation) — both recorded in PREEXISTING.md.

## 2026-10-09 — sever-vm-clone task 5.3: two-node.md command reference

Drop-promote workflow, leaf task 5.3 (workflow dwfrun-26207719):
- docs/docs/commands-and-modules/two-node.md: the promote-vm-clone section
  (~1086–1119) replaced in place by a sever-vm-clone section matching the
  neighboring format (clone-vm/move-vm-disk/new-vm-disk style): both usage
  forms (vmid; dataset paths), Arguments + Recovery options (--continue /
  --rollback) tables, node-config globals line, Called modules table
  (zfs-migrate-send, zfsreapplyholds, zfs-diagnose-busy, zfslockmanager,
  safe-iscsi-save, rescan-storage), Data structures table (cutover state
  file + holds files, temp namespaces, expected-backstores manifest,
  encrypted-luns conf), 8-step internal flow (delegation before the qm
  guard; discovery; plan + tight-space holding-pool ask with key check and
  copy-back estimate; Phase 1 online full copies through the engine under w
  locks; Phase 2 stopped-VM cutover inside one storage-side worker heredoc
  under set -e — catch-up incremental, GUID verifies, hold capture/release,
  [2N] LUN/backstore teardown, destroy, [H] origin destroy + engine
  copy-back, name-preserving swap, udev wait, [2N] same-LUN re-export with
  manifest bookkeeping + safe-iscsi-save, holds reapplied, scaffolding
  cleanup; namespace cleanup, rescan-storage, origin-snapshot report),
  return codes, side effects (true severance, origin snapshots deletable,
  LUN preserved), closing cross-references to concepts.md#severing-a-clone
  and the gtk-gui.md Sever Clone button.
- Jump-to TOC entry and the zfsclone-vm cross-reference re-pointed from
  promote-vm-clone to sever-vm-clone (#sever-vm-clone-both); no
  promote-vm-clone references remain in two-node.md (grep-verified).
- Check: python3 -m pytest tests/python/test_docs_integrity.py — 22 passed,
  1 failed; the failure is test_all_internal_anchors_exist on six
  #promote-vm-clone-both anchors in user-guide/proxmox-integration.md (5)
  and messages/index.md (1) — files owned by this workflow's remaining
  docs-sweep tasks (their re-pointed #sever-vm-clone-both links, e.g.
  messages/index.md:986 and two-node-config.md:317, resolve against the new
  section). Not touched here per task scope.

## 2026-10-09 — sever-vm-clone task 2.2: holding-pool ordering + two-node coverage in test-sever-vm-clone

- tests/test-sever-vm-clone grew from 18 to 21 tests. New coverage:
  - test_holding_feasibility_gate_aborts — the cutover's fresh-number
    copy-back pre-check: plan estimate passes, the mock engine's new
    engine_drain knob ("<destfs-prefix>\t<pool>\t<free>") drains tank's free
    space after the phase-1 copy-out into the holding pool, and the gate
    aborts between copy-out and destroy: rc 1, the plain-explanation FATALs,
    2 receives into the holding pool (full + catch-up) but 0 into the source
    pool, 0 DESTROY/RELEASE ops, original still a clone with its hold,
    origin snapshot alive, staged copy safe, --continue state file left.
  - test_two_node_full_cycle — the tests/test-archive-vm ssh-stub pattern
    extended to EXECUTE the storage-side 'ssh bash -s' heredoc workers
    locally against the same mock state (a test's two hosts share one
    filesystem): every call recorded in the env's sshlog with bodies
    between SSH-BODY markers; the remote-bin probe answers a fake path that
    the stub rewrites to the mock bin dir for worker runs; a file-backed
    targetcli() models backstores/LUNs (output shapes the anchored parsers
    read); mock safe-iscsi-save/rescan-storage executables record
    invocations in the oplog; manifest + encrypted-luns conf live under the
    env's etcz via ISCSI_MANIFEST/ZFSUTILITIES_SYSTEM_CONFIG_DIR. Asserts
    per disk: discover → teardown (lun delete, backstore delete) BEFORE the
    destroy; backstore re-create + explicit same-LUN create + attribute set
    AFTER the rename; safe-iscsi-save per re-export (2); rescan-storage
    once, last; final LUN table identical (non-monotonic seed LUN 1/LUN 0 so
    auto-assign could not reproduce it); manifest lines removed-then-readded
    exactly once; only the encrypted disk's line in iscsi-encrypted-luns;
    state-file push before every worker run; heredoc bodies carry
    zfslock_init/set -e and the sev_iscsi_* rewire; remote origin destroy
    heredoc ("sever-vm-clone origin release") runs for the confirmed origin.
  - test_two_node_storage_entry_delegates_before_qm_guard — storage-host
    entry with qm hidden delegates via `exec ssh -t` before the qm guard
    (exec bypasses the ssh FUNCTION, so a mock ssh EXECUTABLE captures
    SSH-EXEC in the oplog); asserts the probe, the -t destination, and the
    forwarded command, and that "requires Proxmox VE" never fires.
- Two mock upgrades: `zfs get encryption` now reads the datasets table's
  encryption column (+ __mock_set_enc seeding), and sever_env_new does a
  full hermetic reset (the env counter does not survive `env=$(...)`, so
  every test shares env1 — knob files and the new capture files are now
  rm -f'd/truncated per test).
- Mock fix in passing: next_seq's `read ... < seq 2>/dev/null` printed an
  ENOENT line on every fresh state tree (redirection order); 2>/dev/null
  moved ahead of the input redirect.
- bin/sever-vm-clone (two small changes, disclosed): ISCSI_MANIFEST is now
  env-overridable (the ensure-restored-vm-iscsi/repair-iscsi-luns
  convention) — required to assert manifest bookkeeping without touching
  /etc; sever_transfer_remote fetches the remote results into
  <results>.fetch then moves it (the cutover runner's existing pattern) —
  the old direct `> "$results"` redirect truncates the only local copy
  before the remote cat lands in it.
- Mutation-checked (scratch copies, not committed): auto-assigning LUNs in
  the targetcli mock fails the full-cycle test on the LUN-table assert;
  hoisting the qm guard above the delegation fails the delegation test with
  its exact message; defusing sever_holding_space_precheck fails the
  feasibility-abort test. Check: tests/run-tests test-sever-vm-clone — 21
  passed, 0 failed (suite runtime ~41s).

## 2026-10-10 — severance (drop-promote) workflow wrap-up

Wrap-up entry for the whole sever-vm-clone workflow (leaf tasks 1.1–1.6,
2.1–2.3, 3.1–3.2, 4.1–4.2, 5.1–5.6; the per-task entries above cover 1.1,
1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 3.1, 3.2, 4.1, 5.3 in detail — the rest are
summarized here). Everything below is uncommitted working-tree state.

Built:
- bin/sever-vm-clone (new, ~2732 lines): two-phase severance — Phase 1
  online full copies through the zfs-migrate-send engine into a temp
  namespace under w locks; Phase 2 stopped-VM cutover (VM-stopped gate,
  catch-up incremental, hold capture/release, pre-destroy GUID verify,
  destroy+rename name-preserving swap, udev wait, holds reapplied,
  @sever-* scaffolding cleanup); holding-pool intermediate mode (tight-space
  ask with encryption keystatus check, fresh-read feasibility gate before
  anything is destroyed, post-free copy-back); two-node mode delegates
  compute→storage BEFORE the qm guard and runs the whole zfs/lock/targetcli
  cutover in one 'ssh root@<storage> bash -s' worker (anchored targetcli
  discovery, same-LUN backstore re-export with auto-assign fallback +
  LUNMOVED WARN, expected-backstores manifest + encrypted-luns
  bookkeeping, safe-iscsi-save, rescan-storage); --continue/--rollback via
  a per-disk phase state file that travels to the storage host and back;
  post-swap origin-snapshot report with typed-confirmation destroy offer
  (held/still-cloned origins only ever reported).
- tests/test-sever-vm-clone (new, self-registering): suite-local mock bin
  (file-backed zfs/zpool shared with the child-shell workers, executing
  ssh stub that runs the storage-side heredocs locally, engine_drain
  feasibility knob, file-backed targetcli). Tasks 2.1/2.3 built it and
  registered every distinct lock reason + the qm guard.
- GUI Sever Clone (task 4.1/4.2): Datasets-page button armed on clone-volume
  selection, typed-confirmation dialog naming datasets/origin snapshots/
  owning VMs and the stopped-VM cutover requirement, one BashStep invoking
  the script with only the selected datasets (python/datasets_page.py,
  python/action_dispatch.py, python/gui_helpers.py origin column).
- bin/archive-vm Step-1 offer now gates each clone VM on qm status and
  invokes sever-vm-clone, aborting on failure; guidance strings in
  zfsclone-vm, zfsdelfs, zfs-diagnose-busy, and gui_helpers BusyReason
  actions re-pointed; zfs-migrate-send gained caller-aware $restart_hint
  (default output unchanged).
- Docs sweep (5.1–5.6 + 4.1's page rows): concepts.md 'Severing a Clone',
  commands.md, two-node.md command reference (owner of
  #sever-vm-clone-both), messages/index.md single sever-vm-clone section
  plus reworded dependent rows, proxmox-integration.md, lock-manager.md,
  two-node-config.md, concurrency-collisions.md, README.md, gtk-gui.md,
  python-modules.md. Every promote-vm-clone reference is gone; the only
  remaining 'promote' words are the intentional "why zfs promote is not
  severance" narrative and the historical changelog/site pages.

Removed:
- bin/promote-vm-clone deleted entirely; its test-lock-coverage and
  test-proxmox-required-guards rows replaced by sever-vm-clone coverage.

Gotchas a future session needs:
- The test mock's zfs destroy is deliberately permissive about datasets
  that still have snapshots; the script destroys the original (and the
  staged temp on rollback) while their @sever-* snapshots exist — real
  ZFS may refuse. Recorded in PREEXISTING.md; the suite pins intended
  ordering, not real-ZFS destroy semantics.
- The two-node worker heredoc REQUIRES the repo zfslockmanager's
  uncommitted set -e release fixes (bin/zfslockmanager:1049); the
  installed 0.120.0 lock manager dies on a single-entry pidfile under
  set -e. Deploy before real two-node use.
- ISCSI_MANIFEST is env-overridable in sever-vm-clone (family convention,
  needed by the tests); sever_transfer_remote fetches remote results via a
  .fetch side file (direct > redirect truncates the only local copy).
- messages/index.md carries exactly ONE sever-vm-clone section (single-home
  rule) and two-node.md owns the #sever-vm-clone-both anchor — run
  tests/python/test_docs_integrity.py after touching docs links.
- GUI two-node launches go through the script's 'exec ssh -t' delegation,
  which drops ZFSUTILITIES_INPUT_HOLD (numbered prompts degrade to plain
  read -rp) — PREEXISTING entry, fix belongs in the script.
- The whole changeset is uncommitted; bin/zfslockmanager, tests/
  test-zfslockmanager, and docs/docs/developer-guide/lock-manager.md
  changes predate this workflow — preserve them in any commit.

Open threads:
- PREEXISTING.md (5 entries remain): rootcheck advisory-only guard
  (family-wide), mkdocs/Zensical toolchain decision (waiting on a 1.x),
  infra-vdev planning (in abeyance as a future objective), the
  sever-vm-clone destroy-vs-snapshots ordering hazard above, and the
  input-hold-over-SSH degradation. The proxmox-integration dangling-anchor
  entry was REMOVED today: task 5.2's re-pointing fixed it and the
  docs-integrity suite was re-verified green.
- sever-vm-clone has only ever run against mocks/stubs — first live use
  should be a low-stakes disk, single-node first.
- docs/ remains concurrently hand-edited by the user; surgical edits only.

## 2026-10-10 — development-cycle wrap-up, step 1 (PREEXISTING resolutions)

Three PREEXISTING entries resolved (2 remain: mkdocs/Zensical toolchain
decision, infra-vdev planning abeyance — both user-decision items):

- rootcheck advisory-only guard: bin/rootcheck now terminates (exit 1,
  message unchanged) instead of returning 1 — every caller invokes it
  bare, so the exit is what enforces it; no caller uses the return value.
  test-archive-vm ran archive-vm as non-root relying on the advisory
  behavior: ARCHIVE_VM_TEST_NO_ROOT now gates the rootcheck call in
  archive-vm (same knob as its two-node root gate). messages/index.md and
  modules.md rootcheck contract lines updated.
- sever-vm-clone destroy ordering: new sever_destroy_dataset helper in the
  storage worker destroys each first-level snapshot before the dataset
  (real ZFS refuses a dataset destroy while children exist; the -R copy
  already replicated the history, so nothing is lost). Wired into the
  cutover source destroy (FATAL path), holding-pool copy free (WARN path),
  and rollback staged-copy destroy (FATAL path). The suite's old ordering
  assertion now passes vacuously — re-pin it in the test-review step.
- input-hold over ssh delegations: new bashinit helper input_hold_env_prefix
  (prints "ZFSUTILITIES_INPUT_HOLD=Y " only when the protocol is active);
  prepended at sever-vm-clone + the nine family delegation sites
  (detach-vm-disk, zfsclone-vm, attach-vm-disk, remove-vm-disk, remove-vm
  x2, archive-vm, move-vm-disk, new-vm-disk, rename-vm-disk). This was a
  family-wide latent instance of the recorded sever-vm-clone issue —
  resolved family-wide rather than left as a new PREEXISTING entry.
  conventions.md documents the delegation rule.

## 2026-10-10 — development-cycle wrap-up, steps 2–4

Step 2 (policy review): an earlier automated rewrap pass had left
boundary-space and glue artifacts in the two-arg continuation forms
(log_msg joins args with ONE space, so a trailing space inside arg1 renders
a double space; a reconstruction pass also glued `log_msg"FATAL:`).
Rebuilt bin/sever-vm-clone from the /tmp/recovery green checkpoint and
re-wrapped all 87 over-100 lines with a verified algorithm: log_msg split
into consecutive string args at shell-nesting-depth-0 spaces, alignment at
the opening-quote column; three zfs-migrate-send engine invocations rebuilt
via a `sever_engine_cmd`/`sev_rh` var += form (splitting INSIDE a
`$(sever_shq ...)` would re-quote at the wrong boundary); assert_contains /
test_start / test_fail take exactly $1/$2, so their long strings use the
`var+=` pattern, never a two-arg split. Verification: a parser that walks
every logical line proved all 292 log_msg calls render byte-identically to
the checkpoint; bash -n, shellcheck -S warning, and ruff clean; every
touched file ≤100 chars/line. Affected suites 10 × green.

Step 3 (test review): the vacuous cutover-ordering assertion re-pinned —
release → children-first snapshot sweep → dataset destroy → rename → udev →
post-swap GUID → hold reapply → post-swap scaffolding cleanup → origin
destroy, plus destroy-count assertions (each @sever-* snap exactly twice:
sweep + cleanup; the held daily exactly once). New tests: tests/test-rootcheck
(exit-1 non-root / clean root, branch-skipped per uid) and
test-bashinit::input_hold_env_prefix (exact expansion under/without the
protocol). Holding-mode ordering chain verified still sound (exact-field
oplog matching, distinct dataset names).

Step 4 (docs): messages/index.md gained the children-first sweep row;
two-node.md cutover bullet explains snapshot-by-snapshot destroy; modules.md
bashinit table gained ask_line + input_hold_env_prefix rows and rootcheck's
globals line now says `id -u`; testing.md rows for test-rootcheck and the
refreshed test-bashinit coverage. test_docs_integrity 23/23; mkdocs build
clean (only the known Zensical banner); site/ rebuilt.

## 2026-10-10 — development-cycle wrap-up, steps 5–6 (freeze)

Full-suite gate (background, no soaks): first run exposed 37 failures — all
fallout of the step-1 rootcheck enforcement in suites that ran scripts
non-root without mocking the guard. Repaired harness-side (the enforcement
is the intended behavior):

- test-list-vm-disks / test-zfswipe / test-zfsshowbigstuff: zfscleanup-style
  stub-mydir (find_zfsutility_script tries $mydir/<name> first; bashinit
  preserves an already-set mydir) diverts exactly the rootcheck resolution;
  list-vm-disks' four later node-lib re-sources pinned to $old_mydir.
- test-safe-iscsi-save: the script copies' `source_helper rootcheck` line is
  sed-neutralized (the runners already define a no-op rootcheck).
- test-unarchive-vm: the suite already exported UNARCHIVE_VM_TEST_NO_ROOT=1
  but bin/unarchive-vm never implemented the knob — added the archive-vm
  gate form. Its tail also masked the suite verdict (a bare `rm -rf` after
  test_summary reset the exit status; run-tests judges suites by exit code,
  so 4 failures printed under "SUITE PASSED") — converted to the house
  test_summary + cleanup + teardown_test_env tail that propagates
  _TEST_SUMMARY_RC. All other suites already end with the propagating
  teardown; unarchive-vm was the lone deviator.

Final full run: 91 suites, 4,651 passed / 0 failed / 1 skipped (root-gated).
Codebase frozen: no further changes without a new instruction.

## 2026-10-10 — Release 0.121.0 preparation (wrap-up steps 7–8)

VERSION bumped to 0.121.0; changelog entry added (severance feature set,
rootcheck enforcement, input-hold delegation forwarding, promote-vm-clone
removal, new suites). __pycache__ dirs removed repo-wide. Final full run
WITH soaks (--with-soak, background, log /tmp/release-0121-withsoak.log):
91 suites, 4,658 passed / 0 failed / 0 skipped — soak suite confirmed in
the log. No code changes after this point in the session.

## 2026-10-10 — post-0.121.0: mock destroy hardening + state-file isolation

Approved follow-up (new instruction after the freeze): close the
mock-divergence hazard the destroy-ordering PREEXISTING entry described.
Both severance PREEXISTING entries were already stale by then — the
0.121.0 run itself shipped the fixes (`sever_destroy_dataset`
children-first at all three call sites; `input_hold_env_prefix` in
bashinit used by the delegation). Gotcha: PREEXISTING entries written
mid-run can be fixed by later tasks of the SAME run before it ends —
re-verify an entry against the tree before acting on it.

- tests/test-sever-vm-clone mock `zfs destroy <dataset>` now refuses while
  child SNAPSHOTS exist (mirroring the existing child-dataset refusal) —
  real-ZFS "dataset has children" semantics, so the children-first sweep
  in sever_destroy_dataset is proven necessary, not merely ordered.
  Red/green proven: bare-destroy variant fails the suite; the sweep is
  load-bearing.
- Suite-isolation bug found via that red-proof (now fixed): the
  crash/abort tests left `/tmp/sever-vm-clone-*.state` files behind
  (leakers even on green runs), and the recovery tests locate their state
  file by `find /tmp | sort | head -1` — a stale file from a failed run
  made the NEXT run's `--continue` test resume from the wrong phase
  (deterministic 8-fail → 20/1 → 21/0 pattern). Fix: `sever_env_new`
  sweeps `/tmp/sever-vm-clone-*.state*` at env build, so every test
  starts with no sever state files; the red→restore→rerun sequence is now
  hermetic (immediate 21/0 after a failed run).
- Operational note for the vm-904 severance runbook: same-pool mode
  verified live (threeamigos 11.7 T free vs ~31 G largest copy; vm-904
  zvols 0 B diverged — catch-up will be near-zero).

Wrap-up of this changeset (same day): standards pass (shellcheck, ruff —
both clean; new awk block mirrors the adjacent child-dataset refusal),
affected suite 21/21, docs integrity 23 passed, mkdocs build clean (only
the known MkDocs-2.0/Material banner), PREEXISTING rechecks (Zensical
still 0.0.69). Final full run without soaks (log
/tmp/zfs-run-wrapup-1010.log): 91 suites, 4,651 passed / 0 failed /
1 skipped (test-rootcheck root-privilege test — expected on this non-root
host). No code changes after this point; codebase frozen at this state.

## 2026-10-10 — catch-up send argv fix (field defect in the 0.121.1 run)

The first real `sever-vm-clone 904` run aborted at the cutover catch-up:
`zfs send -nPRIw @from @to` / `transfer_do ... "-RIw"` fail on real ZFS
with "too many arguments" — inside a short-option cluster, getopt takes
the next CLUSTER CHARACTER as an argument-taking option's argument, so
`-RIw` parses as `-I"w"` and both snapshot names land as positionals.
Verified live on stewie: the cluster form fails; `zfs send -nPRw -I @from
@to` succeeds. The full-copy path was immune (`-Rw` has no argument-taking
option). zfs-send-receive was already safe (standalone `-I`/`-i` words in
arrays); the defect was confined to zfs-migrate-send (inherited by
sever-vm-clone's catch-up AND Migrate Pool's cutover catch-up).

- Fix: transfer_do now assembles the incremental form itself
  (`zfs send <opts> -I <from> <to>`, -I a standalone argv word); the
  zfs-migrate-send estimate and catch-up call use `-nPRw -I` / `-Rw`.
- Gotcha (durable): argument-taking CLI options (-i/-I/-t here) must NEVER
  ride inside a flag cluster; the zfs send mocks in test-zfs-migrate-send
  and test-transfer-lib now enforce exactly that (clusters containing
  i/I/t, or two positionals without a standalone -I/-i, fail with "too
  many arguments") — argv-fidelity mocks, not just exit-code mocks, are
  what catches this class. Red/green proven both ways.
- Recovery for the interrupted run: after deploying the fix,
  `sudo sever-vm-clone --continue /tmp/sever-vm-clone-904-1791650817.state`
  — the cutover worker's steps are idempotent (staged copies and the
  already-created cutover snapshot are reused).

## 2026-10-10 — wrap-up of the catch-up argv changeset

Steps 1–3 of the cycle wrap-up:

- Step 1: PREEXISTING both entries non-actionable (Zensical still 0.0.69
  on a fresh PyPI check; infra-vdev planning UI in abeyance by user
  decision). File left as-is.
- Step 2 (standards): shellcheck/ruff/bash -n clean; one added
  test_start line was 102 chars → reworded; the new mock regex
  `^-[A-Za-z]{2,}$` (14 chars, thin docs) replaced with an equivalent
  glob form (policy prefers no regex). Verified no transfer_do caller
  ever combines -t with send_target2 (resume path passes "" target,
  zfs-send-receive never passes target2) — the if/elif restructure is
  safe. Golden diff reviewed: exactly the intended one-line change.
- Step 3 (tests): the sever suite's mock engine still modeled the
  broken clustered `-nPRIw`/`-RIw` sends. Added the same
  getopt-fidelity guard to its mock `zfs send` (red: 9 failures with
  the clustered engine), then moved the engine to `-nPRw -I`/`-Rw -I`
  (green 21/21) — the severance path now has the argv-fidelity net
  too. Stale `-RIw` docstring in test_zfs_repository.py updated.
  Affected suites: test-transfer-lib, test-zfs-migrate-send,
  test-sever-vm-clone, test_zfs_repository.py all green.

Step 4 (docs): stale current-behavior `-RIw`/`-nPRIw` references
corrected to the standalone `-I` forms in commands.md (5 sites incl. the
globals table), gtk-gui.md, and python-modules.md (3 sites); changelog
hits left alone (historical release records). testing.md: migrate-send /
transfer-lib rows updated for the argv-fidelity mocks, and two missing
suite-table rows added — test-sever-vm-clone (never had one) and
test-zfswipe. docs integrity 23 passed; mkdocs build exit 0 (only the
known MkDocs-2.0/Material banner); site rebuilt.

Steps 5–6: full suite without soaks (background, log
/tmp/zfs-run-wrapup-argvfix.log): 91 suites, 4,651 passed / 0 failed /
1 skipped (test-rootcheck root-privilege branch — expected on this
non-root host), exit 0, first run clean. Codebase frozen at this state;
no further changes without a new instruction.

## 2026-10-10 — Release 0.121.2 preparation (wrap-up steps 7–8)

VERSION bumped to 0.121.2; changelog entry added (Fixed: catch-up send
argv defect + --continue recovery note; Changed: argv-fidelity send
mocks in three suites; Documentation: flag-reference corrections +
missing testing.md suite rows). __pycache__ dirs removed repo-wide
(3 found; re-swept after the run since pytest regenerates them — they
are gitignored). Final full run WITH soaks (background, log
/tmp/release-0121-2-withsoak.log): 91 suites, 4,658 passed / 0 failed /
0 skipped — soak suite confirmed in the log; matches the 0.121.1
with-soak baseline profile. No code changes after the freeze.

## 2026-10-10 — second field defect: same-pool receive of a clone's -R stream re-links the origin

The first real severance run (0.121.2) "succeeded" without severing:
`zfs send -Rw` of a CLONE produces a stream based on the clone's ORIGIN
snapshot, and a receive onto a pool where that snapshot still exists
(severance copies within the source pool) links the destination as a
CLONE of it — receive prints "found clone origin", ~312 B per snapshot
moves instead of the estimated 23 Gi, and the swap replaced old clones
with new clones (verified live: origins still on vm-211's @clone snaps,
0 B/14 K used; lineage and offsite hold intact, so no harm done).

- Durable gotcha: only a PLAIN full send copies a clone origin-free on
  the same pool. Replication streams of clones must never be received
  onto the pool holding their origin. `-R` has now caused both 0.121.x
  field defects (getopt cluster first, stream semantics now).
- Fix: zfs-migrate-send detects clone sources and copies with
  zfs-send-receive's two-step (plain full of the OLDEST snapshot, then
  `-w -I` to the target; catch-up also drops -R; local compression
  passed as receive `-o`; step A skipped on re-run when the destination
  already holds @oldest). Non-clone sources keep `-Rw`. Migrate Pool's
  clone-dataset copies inherit the safety.
- sever-vm-clone gained the missing verification: the phase-1 gate
  refuses any staged copy whose origin is not `-` (before anything is
  destroyed), and the post-swap "✓ severed" line now actually checks
  the origin instead of asserting it.
- Tests: five engine clone-path tests + two sever origin-gate tests
  (guid_override-style origin_override knob); red/green proven by
  disabling the clone path. Recovery: re-run sever-vm-clone 904 after
  deploying — the current zvols are safe to re-sever.
- "SEVER 904" (repo root, untracked) is the console capture of the
  defective 0.121.2 field run: "found clone origin", 312 B per snapshot,
  and the origin-snapshot report still showing vm-904 cloning vm-211's
  snaps after "success". Evidence for this changeset; the fix is NOT
  deployed yet.

## 2026-10-10 — wrap-up pass over the clone-origin changeset (pre-freeze)

- Standards: sever-vm-clone's "✓ severed" log line re-indented to 4 spaces
  (was 8, and 101 chars); zfs-migrate-send now separates a FAILED size
  estimate from a genuine zero-byte estimate (have_est flag) — a "size 0"
  dry-run no longer triggers the missing-estimate WARN; a 110-char test
  assert split into an equivalent pair. ShellCheck clean, no lines over
  100 in new code. 15 pre-existing 101-102-char lines in sever-vm-clone
  recorded in PREEXISTING.md.
- Tests: added test_zero_byte_estimate_not_missing; affected + adjacent
  suites green (migrate-send, sever-vm-clone, lock-coverage,
  proxmox-required-guards, snapshot-names, archive-vm).
- Docs: two-node.md cutover bullet now documents the post-swap origin-free
  backstop; the stale "the -R replication gave the original snapshots"
  attribution corrected (they are retention snapshots); python-modules.md
  send-builder row and testing.md suite rows updated for the clone path.
  Docs integrity 23/23; site rebuilt.
- Post-freeze follow-up (user prompt): the 15 pre-existing 101-102-char
  sever-vm-clone lines were wrapped after all (several were also
  misindented 8/16-vs-4/12 log_msg groups — normalized to block depth).
  A logical-line parser proved all 287 log_msg calls render byte-identical
  to the pre-edit snapshot; ShellCheck clean; PREEXISTING entry removed.
  The two remaining PREEXISTING entries (Zensical 1.x wait, infra-vdev
  planning abeyance) await user decisions.
- Second-pass redo of wrap-up steps 2-6: one more straggler normalized
  (the success-path copy-back pre-check INFO block, 8/16 -> 4/8) and the
  stale "replication is raw (-w)" holding-mode message reworded to "the
  transfer is raw (-w)" (clone copies are plain -w sends, not
  replication; messages/index.md row updated; no test coupling). Parser
  verdict: 287 calls, exactly the one intended text diff. Full-tree
  ShellCheck (documented command) + ruff clean; both affected suites
  green; docs integrity 23/23; site rebuilt.


## 2026-10-11 — config migration v27 (paths section)

- User audit caught a gap in the cron.log-lifecycle work: the new `paths`
  config section was only lazy-seeded by get_paths_config (persisted solely
  when the GUI regenerates cron), with no CONFIG_VERSION bump — violating
  config_migrations.py's own "bump when JSON structure changes" rule and
  leaving headless-upgraded config.json files without a visible section.
- Fix: _migrate_26_to_27 seeds the section via get_paths_config
  (persist=False; lazy import avoids the config_core circular import);
  CONFIG_VERSION 27; migration registered. Lazy seeding remains as the
  runtime backstop for hand-pruned files.
- Tests: seed/preserve/idempotent migration tests, version-pin and chain
  tests updated (26 -> 27 pins, from_version_14 chain now asserts paths
  seeds through the whole chain). data-structures.md migration chain and
  paths-section prose updated.

## 2026-10-11 — development-cycle wrap-up (steps 1-6)

- Step 1 (PREEXISTING): resolved 3 — sever 0B origin-report explanation
  (message + catalogue + two-node note + test), test_file_locking handshake
  ceiling 60→300s, zfsretain dry-run checkagainst caveat (message + note +
  test); narrowed pre-sidecar entry (FATAL names the cause; manual restore
  documented in commands.md; legacy-import mode left as user decision);
  Zensical recheck 2026-10-11 still 0.0.69. 3 entries remain (2 user
  decisions + 1 style pair).
- Step 2 (standards): documented shellcheck pass clean — new SC2128/SC2178
  cluster in test-unarchive-vm suppressed with explained file-level
  directive (mock scalar misinferred as array; test-lib source unfollowable);
  pre-existing SC2295 in unarchive-vm fixed; 13 changeset-added bash lines
  >100 chars wrapped (log_msg join-safe; grep/[[ ]] assertions rebuilt via
  needle variables — backslash-continuation string concat does NOT join
  across indented lines, it makes two arguments); ruff check + format clean
  tree-wide; 2 unwrappable pre-existing uninstall lines recorded.
- Step 3 (tests): added zfsdelsnap unknown-age gate test + zfsmassdelsnaps
  unknown-age 0-day display test; no obsolete/incorrect tests found.
- Step 4 (docs): message catalogue rows for the three new/changed messages;
  two-node 0B accounting note; unarchive-vm pre-sidecar warning box;
  zfsretain dry-run gates note. Integrity 23/23; site rebuilt.
- Steps 5-6: full suite without soaks in background; freeze on green.

## 2026-10-11 — archive-vm Step 4 / remove-vm-disk: delegated prompts + children destroy (live vm-205 incident)

- Live incident (tweety/stewie, deployed 0.122.0): `sudo archive-vm 205`
  archived + verified fine, then Step 4 hung invisibly per disk. Root causes
  in code: (1) archive-vm invoked remove-vm-disk over plain `ssh root@...`
  with no `-t` and no input-hold env prefix — bash suppresses `read -p`
  prompts when stdin is not a tty, so the two per-disk confirms never
  rendered; (2) remove-vm-disk declines/EOF reads exit 0, so disk 3's
  buffered-empty-line "Aborted." scored as success; (3) Step 4 rm -f'd the
  PVE config and printed "=== Done ===" regardless, leaving a half-removed
  VM. Manual recovery: standalone `sudo remove-vm-disk <pool> 205 <n>` (its
  own `ssh -t` delegation shows prompts) tore down LUNs/backstores, then
  bare `zfs destroy` refused the zvols — child dailybackup snapshots (with
  holds). Finished via `sudo zfsdelfs <zvol> '' '' '' "autoproceed='Y'"` on
  stewie + rescan on tweety. Stale `fivebays/*` vm-205 copies flagged
  pre-existing (user decision; not this bug).
- Fixes: archive-vm Step 4 two-node now delegates via
  `ssh -t` + `$(input_hold_env_prefix)` + `--skip-rescan`, verifies each disk
  by post-condition (`zfs list` probe — exit codes lie), gates config removal
  on zero survivors (FATAL block lists survivors + exact finish commands,
  exits non-zero, no Done summary), one rescan-storage after the loop;
  single-node destroys via `zfsdelfs autoproceed='Y'` with the same gating.
  remove-vm-disk: destroy routed through zfsdelfs (children + holds; outer
  x-lock dropped — zfsdelfs takes its own and a held outer lock would
  self-deadlock the child); wrapper rescans even when the remote failed (the
  LUN may already be gone); safe-iscsi-save/rescan-storage resolved via
  find_zfsutility_script (were $mydir-direct, wrong under the repo-root test
  mydir); EXPECTED_BACKSTORES_MANIFEST env override (mirrors the
  encrypted-luns pattern) so the manifest prune is testable.
- Tests: test-archive-vm +5 (delegation argv incl. env prefix, decline-exit-0
  regression, remote-failure gating, single-node zfsdelfs routing + failure
  gating; harness gains zfsdelfs/rescan stubs, ssh-mock remove-vm-disk and
  zvol-probe knobs); new tests/test-remove-vm-disk (state-mutating targetcli
  mock; zfs destroy refuses child-snapshot datasets; wrapper -t/env/
  --skip-rescan argv + rescan-on-failure). Gotchas: test-lib's
  `zfs list -H -o name <ds>` falls through to the general fs listing, so a
  nonexistent ds "exists" — suites needing existence semantics wrap zfs; a
  literal newline inside a `#` doc comment ("y\ny") unbalanced quoting for
  the whole rest of the file — bash -n reported far-away lines as culprits.
- Docs: message catalogue Step-4 + remove-vm-disk rows rewritten; commands.md
  archive-vm step 8/called-modules/internal-flow; two-node.md remove-vm-disk
  internals; proxmox-integration archive narrative; testing.md rows.
- Not done (deliberate): no VERSION/changelog/commit (Hard Rules); the stale
  fivebays zvols left for a user decision.
- Full-suite fallout (first run 2 failures, both static-coverage suites
  guarding the refactors — updated to the new architecture):
  test-iscsi-fresh-install-guards now accepts the find-routed
  `if ! "$safe_save_path"` save-invocation form alongside the $mydir-direct
  one; test-lock-coverage's remove-vm-disk rows (source/init/acquire)
  replaced with the zfsdelfs-delegation row plus zfsdelfs's own
  source+acquire rows (its lock is now load-bearing for remove-vm-disk);
  remove-vm-disk's dead `source_helper zfslockmanager` removed;
  lock-manager.md lock-matrix row updated (destroy lock via zfsdelfs, no
  outer lock — a held outer lock would deadlock the child).

## 2026-10-11 — archive-vm/unarchive-vm: transfer pacing, idempotent re-runs, node-agnostic orchestration

- Pacing (the "whale in a 5-gallon aquarium" fix): the shared transfer
  library honors `pv_rate_limit` (the suite-wide lever from transfer-lib /
  the GUI) in all three hot operations — device copy becomes
  `pv -q -L | dd conv=sparse,notrunc` (dd's conv=sparse preserves the thin
  archive zvol at 16M granularity), hash verification reads each device
  through pv into `sha256sum` stdin, and the raw path gains a pv pipeline
  segment (pipefail subshells — the old pipelines only surfaced the last
  rc). Both scripts prompt for the limit with the saved JSON default (new
  shared key `archive_rate_limit`; empty = unlimited = the exact unpaced
  commands); node-lib gains get_json_archive_rate_limit + a generic
  save_json_config_key (empty value deletes the key), replacing
  archive-vm's inline python writer.
- Idempotent re-runs: archive side — new archive_completion_state() probe
  (@archive snapshot + METHOD sidecar + method-implied volblocksize =
  complete; dataset without @archive = partial → destroy and re-make;
  complete → skip with sidecar DISK_KEY/LUN/TARGET backfill, append-if-
  missing so skips don't grow duplicate lines); the old pre-existing-
  dataset FATAL is now a race backstop only. unarchive side — RESTORED_AS
  marker appended to .disk_info after each verified restore; destination
  classification (marked → skip; unmarked → explicit destroy-and-redo
  confirm, default abort); destination config + all-marked → clean exit;
  vmid_in_use ignores this archive's own restore-target paths so a
  same-vmid resume isn't blocked, and its config branch exempts a config
  whose every target is marker-complete (a finished restore re-runs to
  "nothing to do", not a new-vmid prompt).
- Node-agnostic: node-lib on_storage/on_compute — one payload, two
  transports (local subshell with ZFSUTILITIES_BIN_DIR pointing at the
  orchestrator's helpers when invoked on that host; `ssh bash -s` with a
  `pv_rate_limit=` env prefix otherwise). Both scripts dropped the
  exec-ssh-to-compute bounce; qm gates relaxed (storage-host invocation
  allowed); compute bits (qm status, /etc/pve read/write, rescan) and heavy
  storage payloads (clone/referenced-zvol discovery, retire snapshot,
  archive transfer, restore, iSCSI rebuild) route through the transports;
  tiny one-liner probes stay plain ssh (self-ssh is correct from either
  node). archive-vm Step 4 runs remove-vm-disk locally on the storage host
  (prompts on the operator's terminal). Payload bootstraps now honor
  ZFSUTILITIES_BIN_DIR; unarchive's iSCSI pool-to-target python honors
  NODE_CONF.
- Tests: archive 34 (rate pacing/forwarding/unlimited-pinned, skip/redo,
  payload probe, invoked-on-storage runs locally with a canned targetcli
  mock), unarchive 18 (paced restore, marker skip/redo/decline,
  completed-run exit, static routing), node-lib 43 (transport selection,
  rc propagation, ssh argv shape). Gotchas: the suites share one JSON
  config file — rate/path saves leak across tests unless each run resets
  it to {}; `read -p` prompt text never prints on non-tty stdin, so
  assert on logged lines, not prompt text; the ssh mock must treat
  "pv_rate_limit='...' bash -s" as one argv entry when detecting heredoc
  payloads.
- Docs: command references, two-node unarchive internals, proxmox-
  integration narrative, modules.md node-lib table, message-catalogue
  rows for every new INFO/WARN/FATAL, testing.md coverage.
- Follow-up (user audit, same class as the v27 catch): the new
  `archive_rate_limit` JSON key shipped lazy-only — no CONFIG_VERSION bump,
  no migration, so upgraded configs never showed the key. Added
  _migrate_27_to_28 (seeds "" = unlimited, preserves user values),
  CONFIG_VERSION 27→28, registered; migration suite pins/chain updated
  (seed/preserve/idempotent unit tests; from_version_14 and from_version_19
  chain results now 28 with an archive_rate_limit assertion);
  data-structures.md key table + migration chain listing updated.

## 2026-10-11 — wrap-up cycle (post-0.122.0 changeset): standards, tests, docs, freeze

- PREEXISTING: resolved the uninstall-zfsutilities over-length lines
  (column-0 `=\` continuation idiom, matching node-lib/installer-lib
  precedents; runtime-verified defaults + overrides). Recorded one new
  entry: archive-vm's 0.121.0 sever confirm passes ask_yn two args (the
  second is the default-answer param), so the "(copy them into
  origin-free zvols)?" tail never displays — same class as the unarchive
  redo prompt. 4 entries remain (sever prompt, pre-sidecar archives,
  mkdocs-material/Zensical, infra-vdev planning) — all user-decision or
  recorded-out-of-scope; none actionable.
- Standards pass (coding-policies.md): full documented shellcheck sweep +
  ruff check + ruff format clean. Fixed in new code: unarchive-vm redo
  prompt three-arg ask_yn truncation (needle variable `redo_prompt` —
  backslash-continued quoted strings arrive as SEPARATE arguments; tests
  can't catch prompt text on non-tty stdin); missing append_exit_trap
  cleanup for unarchive-vm's tmp_config and node-lib's on_storage/
  on_compute payload_tmp mktemps; test-lock-coverage row >100 chars;
  archive-vm header "Run from" line was stale (delegation bounce gone).
  Suppressed as trivial: two 102/104-char rows in untouched
  test-lock-coverage hunks.
- Tests: added node-lib unit coverage for get_json_archive_rate_limit
  (read/defaults) and save_json_config_key (round-trip, sibling-key
  preservation, empty-deletes, creates missing file); added a
  RESTORED_AS-marker-write assertion to test-unarchive-vm's redo test
  (fixtures pre-marked but no test proved the write). SC2034 disable with
  reason added in test-node-lib (pv_rate_limit expanded across the lib
  boundary). Affected suites green individually.
- Docs: reviewed all changeset docs — accurate, no edits needed;
  docs-integrity 23/23; mkdocs site rebuilt (exit 0; mkdocs-material
  WARNING = known PREEXISTING toolchain entry).
- Full suite without soaks (background): 92 suites, all passed, 1 skip
  (root-gated, non-root host), exit 0. Codebase frozen at this point.

## 2026-10-11 — PREEXISTING clear-out (user: no out-of-scope)

- Fixed archive-vm's 0.121.0 sever-confirm ask_yn truncation (needle
  variable sever_prompt — the "(copy them into origin-free zvols)?" tail
  now displays); in the same block removed a stuttered duplicate FATAL
  line ("or the Proxmox GUI), then re-run archive-vm." echoed twice).
  Codebase-wide ask_yn/ask_line argument-shape audit: all remaining call
  sites correct (prompt-only, prompt+"Y"/"N", or prompt+varname);
  sever-vm-clone's prompt+"Y" continuation is intentional correct usage.
  test-archive-vm green after the fix; message-catalogue row unaffected
  (describes the message semantically).
- User decisions on the remaining entries: legacy-import mode NOT built
  (manual procedure stands — entry removed, question closed); keep
  waiting for Zensical 1.x (entry reconfirmed, stays as tracker); keep
  infra-vdev planning UI deferred (entry reconfirmed). PREEXISTING now
  holds only those two reconfirmed trackers.
