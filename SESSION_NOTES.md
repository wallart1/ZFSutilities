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
