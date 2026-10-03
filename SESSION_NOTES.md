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
