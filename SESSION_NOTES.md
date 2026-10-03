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

## Active / parked threads

- **Memory tab + tab reorder (2026-10-02) — implemented, affected suites
  green; full suite pending; awaiting commit.** Sidebar order changed to
  dashboard…logs, then Memory, then Disks/Pools/Datasets at the bottom
  (`PAGE_BUILDERS` in zfsutilities_gui.py — a declarative list so order is
  unit-tested). New Memory tab (`memory_page.py` + pure data layer
  `memory_stats.py`): ARC/L2ARC/SLOG value grids, per-device tables from
  `zpool iostat -v`, and Cairo-drawn rolling charts (`RollingChart` —
  composition over subclassing Gtk.DrawingArea so it works under the test
  GTK mocks; auto-scaled Y, dashed c_max reference, ~300-sample window).
  Refresh interval spinner persists to `memory.refresh_seconds` (default 5 s),
  timer runs only while visible (scrub-timer pattern). Capability-aware per
  user feedback: all three sources probed per sample and degrade
  independently (arcstats/zil/iostat), every kstat field optional ("—").
  Verified tweety (Proxmox kmod 2.4.4): full arcstats+zil present but zero
  pools → no-vdev notes are the real path there. zpool iostat human sizes
  are base-1024 (verified vs `zpool list -Hp`). Note: under mock_gtk, all
  `Gtk.Label()`/`Gtk.ListStore()` calls return ONE shared mock — page tests
  give them side_effects for distinct instances (also avoids infinite walk
  in `_reconcile_rows`). New log message: `INFO: Memory stats refreshed`
  (zfsutilities_gui.on_refresh only — pools precedent, one home).
  Follow-up fix (same day): device-table column widths now persist —
  `_device_table()` takes a state_key and calls
  `app._ui_state.bind_treeview()` (`memory_l2_view` / `memory_slog_view`),
  the house pattern every other TreeView uses; also folds the tables into
  View→Minimize Width. Verified restore end-to-end with a real
  UIStateManager + GLib idle pump (saved widths applied, min-width clamp,
  unsaved columns default). Note: `_do_save` skips unrealized TreeViews, so
  the save half can't be exercised headless — covered instead by
  test_gui_infrastructure's bind_treeview/_do_save tests.

- **Close-warning truthfulness for surviving tasks (2026-10-02) — implemented,
  affected suite green; full suite pending; awaiting commit.** User guidance:
  don't warn on GUI close about scrubs (they survive), Dashboard/Pools info
  recovers on restart, and "the profile runner will be gone." Verification:
  scrub/ZFS-op exclusion and restart recovery were already implemented
  (`_collect_abortable_tasks` since ≤0.99.0); the profile-runner claim is
  confirmed for Run Now runs — GUI exit breaks the runner's stdout/stderr
  pipes, so its echo (`profile_runner.py:290`) raises BrokenPipeError →
  caught at `:312` → step rc=1 → run aborts (bash child EPIPEs too); cron
  runs are unaffected. Two approved fixes shipped in `_collect_abortable_tasks`
  (`zfsutilities_gui.py`): GUI-started **scrub profiles** no longer listed
  (scrubs continue kernel-side; `scrub_state.json` queue resumes on restart;
  new module helper `_profile_tab_type()` via `profile_manager.load_profile`,
  "Scheduled: " prefix stripped; unknown type → still listed, conservative),
  and **Surface Tests** no longer listed (firmware-driven, state file
  recovers them). Non-scrub Run Now runs still warn — accurate, they abort.
  gtk-gui.md "Closing the GUI" extended (also fixed its "Cancel" → "No";
  dialog is YES_NO). Tests: filter test now patches `_profile_tab_type`;
  three new cases (scrub-profile skip incl. Scheduled prefix-strip,
  non-scrub/unknown kept, surface test filtered).

- **Scrub Manager "As Of" column rename (2026-10-02) — implemented, full
  suite green; awaiting commit.** User reported the Pools-page Scrub Manager
  "Last Scrub" column showing paused/resumed timestamps. Root cause was
  by-design: `parse_scrub_status()` puts the current scan line's timestamp
  (in-progress-since / paused-since / finished-on / canceled-on /
  resilvered-on) into `ScrubInfo.last_scrub`, displayed verbatim. User
  decision: keep those per-state timestamps and relabel the column "As Of" —
  no displayed value changes. `ScrubInfo.last_scrub` renamed to `as_of`
  (field comment states the semantics); pools_page column title → "As Of".
  Test gap closed: `test_paused` now asserts `as_of` (was unasserted — the
  gap that let the ambiguity linger); new `test_refresh_shows_paused_scrub_date`
  locks in the paused-since display; monospace test renamed. Docs: gtk-gui.md
  Scrub Manager section (column list + As Of description, incl. the ZFS
  artifact that after a resume the line reports the original start time, not
  the resume moment); data-structures.md `as_of` row. The Dashboard's own
  "Last Scrub" column is a separate column and was deliberately left
  unchanged. mkdocs build clean.

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

- **/tmp test-litter cleanup pass (2026-10-02).** Fixed the three
  PREEXISTING.md entries about /tmp accumulation from test activity.
  Key architectural addition: `append_exit_trap` in `bin/bashinit` — a
  composable EXIT-trap registry (bash allows only one EXIT trap per shell;
  bare `trap ... EXIT` registrations were silently clobbering each other:
  zfslockmanager owned it, test-enroll-iscsi-pool clobbered it). Handlers
  run in registration order, exit status is preserved ($? is restored
  before each handler), and subshell semantics are explicit: the arming
  embeds $BASHPID so an inherited arming is detected, the inherited list is
  dropped, and only subshell-registered handlers run at subshell exit.
  Gotchas learned the hard way (all documented in the bashinit comment):
  (1) naive self-recognition folded `_run_exit_traps` into its own handler
  list → infinite recursion at subshell exit → segfault; (2) `local x=$?`
  must be the FIRST statement or $? is already clobbered; (3) bash 5.2
  does not fire an EXIT trap armed inside a bare `while read` loop that is
  itself a pipeline segment — brace the loop or register from file scope.
  test-lib.sh now removes its per-PID log + mock dir at suite exit (failed
  suites keep the log; path printed on stderr); several suites re-source
  test-lib inside $(...) subshells, so registration is gated on
  BASHPID=$$ (top-level shell only). Script-side fixes: repair-iscsi-luns
  regenerate_manifest now rm+FATAL(exit 8) on empty/failed manifest
  install (tests point the manifest at a temp dir; main-in-same-shell
  means the new exit 8 would kill the suite otherwise); zfs-send-receive
  holds file gets an append_exit_trap cleanup + non-deprecated mktemp;
  zfsdelsnap removes checkagainst's fssalreadyprinted markers ($PPID and
  $$ keys) at exit; pool_migrate_dialogs wraps the post-mkstemp section in
  try/except (discard TSV, release lock if taken, WARN + re-raise), and
  its tests route mkstemp into a TemporaryDirectory. test-logging unsets
  ZFSUTILITIES_LOG_FILE/INHERIT/msg_level after each mktemp test (stale
  exports were re-creating deleted files). New pre-existing entry logged:
  run-tests py_tmpout interruption leak. Docs: testing.md cleanup +
  append_exit_trap guidance; messages catalog rows for the two new
  messages.
  Acceptance check on the green full run turned up two residuals, both
  traced: the single retained empty per-PID log came from my own new
  exit-42 child-suite test (a suite exiting before test_summary is
  treated as crashed, so retention is by design — the test now reaps
  that log itself); the five new /tmp/tmp.* dirs are
  test-safe-iscsi-save's _run_safe_iscsi_save helper leaking its
  mktemp -d dir per call — logged as a new PREEXISTING.md entry (out
  of scope). With those explained, the green-run delta is zero.

## /tmp test-litter residuals cleared (2026-10-02, second pass)
  Fixed the two PREEXISTING entries from the acceptance check — the
  run-tests one turned out worse than documented: cleanup() aborted at
  kill_pytest_tree on interruption, because the TERMed pytest makes
  `wait` return 143 and run-tests' set -e kills the EXIT-trap handler
  mid-function, leaking state_dir TOO (not just py_tmpout). Probes: bash
  does run the EXIT trap on untrapped SIGTERM, but any failing statement
  inside the handler aborts the rest under set -e. Fix: `|| true` on the
  kill/wait pair, guarded py_tmpout removal in cleanup(), and the normal
  path clears the variable after rm. Regression test extracts the REAL
  kill_pytest_tree+cleanup and runs them under bash -eu with a live
  `sleep 30` standing in for pytest (pre-fix simulation: rc=143, both
  paths leaked). Verification gotcha: a `&`-launched run-tests is
  SIGINT-immune (POSIX async-subshell SIG_IGN), so live interruption was
  verified with SIGTERM mid-pytest — py_tmpout removed, zero net-new
  /tmp/tmp.*, no pytest orphans. Also fixed:
  test-safe-iscsi-save's _run_safe_iscsi_save rm -rf's its workdir while
  preserving the runner's rc (callers assert on it); new workdir test
  uses a private TMPDIR prefix inside the command substitution. Two more
  cleanup() unit tests in test-run-tests-preflight via the existing
  sed-extraction idiom (removal + bash -u unset tolerance). One new
  PREEXISTING entry: safe-iscsi-save's
  regenerate_expected_backstores_manifest has an unguarded mv -f (leaks
  its tmpfile only if mv fails; theoretical under root).

## safe-iscsi-save manifest-install guard (2026-10-02, third pass)
  Closed the PREEXISTING "temp-file leak edge" entry: the mv -f in
  regenerate_expected_backstores_manifest is now guarded (rm tmpfile,
  FATAL: safe-iscsi-save: Could not install regenerated manifest at ...,
  exit 1 — this script's only failure code, unlike repair-iscsi-luns's
  exit 8). Empty-manifest branch unchanged (WARN + rm, non-fatal).
  Test uses a read-only manifest subdir (555) so the -f gate passes but
  mv fails, plus the private-TMPDIR idiom to make the script's tmpfile
  leak visible under the test scratch dir. Catalog row added next to the
  other regenerate rows.
