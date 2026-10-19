# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves: an entry is
obsolete once its cycle is committed, durable knowledge belongs in `docs/`
or PREEXISTING.md, and only undocumented gotchas and active threads are kept
here. Pruned history remains recoverable from git.

(2026-10-15 prune: everything through Release 0.125.0 is committed and
documented — the itf campaign, releases 0.114.0–0.125.0, and every wrap-up
entry were removed; recoverable via `git log`.)
(2026-10-16 prune: the Performance-page/alignment plan run, the blocksize
ladder, the scroll-stability work, and the zfswipe notification rework are
committed with Release 0.126.0 — their entries were removed; recoverable
via `git log`.)

## Persistent gotchas (not documented in docs/)

- `source_helper` scoping law (vm-205 incident, 2026-10-16): bashinit's
  `source_helper` is a function, so a library sourced through it runs inside
  the helper's frame — every top-level `declare` (incl. `declare -A` maps
  declared by a sourced node.conf) becomes function-local and **vanishes when
  source_helper returns**, while functions and plain assignments survive
  globally. Any library state that must outlive the source needs `declare -g`
  / `-gA` (now done in node-lib, iscsi-lib, zfslockmanager — keep it that
  way for future libs). Symptom signature: a lookup helper works when its
  orchestrator sourced the lib at top level (storage-host runs inherit the
  populated globals; the `declare -f` guards skip source_helper) but returns
  empty-map failures only in ssh-shipped payloads running in fresh shells.

- Strict-mode (`set -euo pipefail`) flip idioms (2026-10-16 wrap-up, 13
  orchestrators migrated): (1) a function whose last statement is
  `[[ cond ]] && assign` returns 1 when the condition is false — close
  with an `if` or an explicit `return 0` or callers under `-e` abort
  (discover_iscsi_state class); (2) inside `while IFS= read -r` loops
  use `[[ -n "$x" ]] || continue`, never `[[ -n "$x" ]] && append` —
  a blank input line would otherwise make the loop itself the failing
  command; (3) associative-array reads on possibly-missing keys need
  `:-` guards even inside `[[ ... ]]` — `-u` fires at expansion time;
  (4) every `$(cmd | grep | head)` whose empty result is legitimate
  (LUN "not mapped", candidate "none found", sidecar "key absent")
  needs a trailing `|| true` — under pipefail the mid-pipeline grep
  fails the substitution and `-e` turns an empty answer into an abort;
  (5) `((++var))` is safe, `((var++))` is not (returns the old value);
  (6) child-engine heredocs are non-interactive — they get the full
  trio too, while sourced libraries must never set shell options.
  Sourced bashinit/node-lib/paths run under `-u` safely (all vars have
  defaults); on_storage/on_compute's `rc=$?` capture only works because
  every caller invokes them in an `if`/`||` context (errexit is
  suppressed inside functions called from conditions).

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
  present, the severance question is the first stdin consumer, before
  the archive-base prompt.
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
- Overriding a **sourced library function** in a test (e.g. `transfer_pacer`)
  and then `unset -f`-ing it DELETES the function — unlike external
  commands there is no PATH fallback. Save and restore with
  `_orig=$(declare -f fn)` … `eval "$_orig"` (0.125.0 cycle: `unset -f
  transfer_pacer` broke the two paced tests that ran after it).
- Pipeline child **startup** order is not guaranteed by bash — the scheduler
  can run any subshell first. Tests that assert stage order must record
  data-dependent markers (a downstream stage writes only after draining the
  upstream's EOF), never echo-at-entry (0.125.0 cycle: the pacer-before-pv
  order test failed ~1 run in 6 under load).
- test-lib.sh redirects `log_msg` into `$_TEST_LOG_FILE`; a `get_log()`
  helper is NOT provided by test-lib — it is defined per-suite
  (test-transfer-lib, test-zfs-migrate-send). In suites without it, assert
  against `cat "${_TEST_LOG_FILE}"`.
- Docs viewer: it picks its site ONCE at window construction — rebuilding
  the repo site does not fix an already-open window; the browser/
  desktop-handler openmd flow still receives paths baked at `mkdocs build`
  time (edit_links.py unchanged — relative baking would break the handler).
  Deployed launches resolve through `current`, so a versions/<v>-baked URL
  re-anchors to `current` and survives version switches.

## Active / parked threads

- **Performance → Blocksize Alignment polish + guest-FS probing
  (2026-10-16) — implemented, uncommitted.** User-requested six-item
  pass over the Alignment view: (1) all four tables ellipsize with
  full-text cell tooltips (schedule-page query-tooltip idiom — wrapping
  was rejected because row-height churn breaks the scroll-stability
  design); (2) every table sits in its own scrolled window capped at
  20 rows (height from theme font metrics, `_ROW_HEIGHT_FALLBACK` when
  unresolvable); (3) scan-table columns sortable (hidden identity key
  never; `_reconcile_rows` gained a sorted-store branch — PyGObject's
  `get_sort_column_id()` answers a (column, order) TUPLE, the
  isinstance(tuple) check keeps MagicMock/fake stores on the ordered
  path); (4) PVE configs read from the compute node over
  `ssh root@<compute>` when local /etc/pve is empty (marker-delimited
  dump; `read_pve_vm_configs`, `fetch_pve_vm_options`); (5) NEW
  `python/alignment_guestfs.py`: guest FS blocksizes probed via
  `qm guest ping` + `qm guest exec` (lsblk/mounts/stat -f %S), disk↔zvol
  matched by volsize equality with the bus-letter tiebreak, TTL cache
  (600 s) keyed (vmid, short, volsize) held on the app — ladder gains
  `vm fs` rungs judged against volblocksize (worst-state per rung),
  new WARN finding `vm-guest-fs-below-volblock`, VM chain rows list
  probed filesystems, `DatasetBlocks.volsize` added (zfs get now
  includes volsize); (6) ladder draws full-page-width but its scrolled
  viewport caps at 50% (`set_draw_width` on both renderers +
  `max_content_width` tracked from the box's size-allocate). Chart
  theming: `charting.chart_palette(widget)` resolves theme_bg/fg from
  the style context (luminance switch → bright series on dark;
  `LIGHT_PALETTE` fallback when unresolvable — matplotlib renderers
  build canvas-first so artists are coloured once at build and
  re-applied on style-updated; Cairo renderers resolve per draw).
  `VMOption.agent` records the config's `agent:` line. Docs updated:
  gtk-gui.md (Alignment View + Performance intro), charting.md
  (palette + draw-width section), data-structures.md, python-modules.md
  (+`alignment_guestfs.py` section). Guest-probe limits (documented):
  needs qga in guest, VM running; LVM/RAID and Windows guests degrade
  with reasons. Not done from the earlier DENIED polish draft (not in
  this request): chart font size to GUI base size; ladder bare "×N"
  label rewrite.

  FOLLOW-UP (2026-10-17, approved): the volsize+bus match was replaced
  by a deterministic 3-tier chain in `match_volumes` — (1) pinned
  `serial=` from the PVE disk line; (2) UUID/PARTUUID signature
  intersection: storage side `lsblk /dev/zvol/<pool>/<ds>` (verified on
  stewie — zvol partitions + UUID/PARTUUIDs visible as non-root via
  sysfs/udev; blank zvols have no signature; GPT GUIDs exist even
  unformatted; LVM PV UUIDs count) vs guest `lsblk -bJ` tree (one
  round-trip replaced lsblk+cat-/proc/mounts; dm/LVM mounts attribute
  through children); (3) size+bus last resort. Clone-shared signatures
  are REFUSED (device evidenced by 2 volumes → neither; same for tier-3
  device sharing) — red-proofed. Live tweety kvm /proc cmdlines show NO
  serial= on data drives (PVE 9 blockdev device_id only) so guest
  serials are per-process counters — tier 1 fires only on operator-
  pinned serial=. matplotlib: you were getting Cairo because the GUI
  runs as root while 3.11.2 sits in dan's pip --user site; now
  check-prerequisites warns (optional, python3-matplotlib hint, warn
  never fail) and the Live Charts header names the active renderer
  (`charting.renderer_label()`). Prerequisites.md updated (system
  package supersedes the pip --user note).
- **Alignment realized-check display flip (2026-10-16) — implemented,
  uncommitted.** The realized-window check
  (tests/python/alignment_realized_check.py) now starts its private Xvfb
  FIRST, falling back to the ambient display only when Xvfb cannot start
  or GTK cannot bind to it (was ambient-first, which flashed a real GTK
  window on the operator's desktop during full-suite runs). A
  `REALIZED-DISPLAY:` stdout line names the display used;
  test_alignment_realized.py asserts it stays. `_gtk_init_ok` removed
  (dead after the flip — the ambient path must go through `_rebind_gtk`
  anyway, since a failed Xvfb bind leaves PyGObject's initialized cache
  stale). testing.md's suite row updated. All three branches verified
  (Xvfb-first live run on :92, no-Xvfb ambient fallback, rebind-failure
  restore-and-fallback via stubs).

- **unarchive-vm 205 Step-2 fix (2026-10-16) — implemented, uncommitted.**
  `sudo unarchive-vm 205` on tweety died at "Cannot map pool NVME1 to
  target" although stewie's node.conf has had `[NVME1]=nvme1` since
  2026-04-28. Root cause: the Step-2 ssh payload loads node-lib via
  `source_helper` in a fresh remote shell; the bare `declare -A
  pool_target` was function-local to source_helper's frame and vanished on
  return, emptying the map under `pool_to_target` (gotcha above). Fix:
  `declare -gA` in both node-lib branches + regression test in
  tests/test-node-lib (child-bash source_helper load; red-proofed against
  the reverted lib). Verified on stewie: the
  `iqn.2026-02.local.stewie:nvme1` target exists and no `vm-205-*`
  backstores/LUNs remain, so the post-deploy rerun takes the create path
  on both targets (nvme1 + threeamigos) and needs no enroll-iscsi-pool.
  Remaining: release, deploy to both nodes, rerun `sudo unarchive-vm 205`
  on tweety (Step 1 will skip all three zvols — RESTORED_AS markers
  present; Steps 2-4 rebuild iSCSI, write 205.conf, rescan).

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

- **Installer execution harness (2026-10-17, cycle wrap-up step 1).**
  Resolved the installer coverage-gap PREEXISTING entry: new
  tests/test-installer-flows executes install-single-node and
  install-two-node end to end as a non-root user — mirror tree redirects
  script_dir at stub check-prerequisites/deploy-version/switch-version/
  setup-iscsi-targets (repo lib/ and share/ stay real), ssh/scp/systemctl/
  sudo/targetcli/findmnt/hostname/mkdocs are recorded shell functions,
  answers are piped stdin, the retention helper runs for real against a
  fixture config. Three small mainline enablers, all following existing
  architecture: INSTALL_SINGLE_NODE_TEST_NO_ROOT /
  INSTALL_TWO_NODE_TEST_NO_ROOT no-root hatches (DEPLOY_VERSION_TEST_NO_ROOT
  precedent) and ZFSUTILITIES_ETC_PREFIX now also prefixing the two-node
  systemd drop-in + obsolete-artifact paths (the knob
  check_partial_uninstall already reads). Kept-config regression fence is
  red-proofed (bug reintroduced → suite fails; restored byte-identical).
  Harness gotchas learned: the installer re-sources bashinit, which
  redefines ask_yn as the real prompt — its answer must come through the
  piped stdin, not the test-lib mock; and test-lib's zpool/ssh mock state
  resets when re-sourced inside the runner subshell.

- **Cycle wrap-up executed 2026-10-17 (7 steps, codebase FROZEN).**
  Step 1 resolved the installer coverage-gap entry (see the harness note
  above); Zensical recheck recorded (0.0.71, still no 1.x — user holds
  stand); infra-vdev planning stays in abeyance per the user decision.
  Steps 2-3: ruff check/format, shellcheck (full set), and policy review
  all green; one test gap fenced (dataset_block_properties argv now
  asserted incl. volsize). Step 5: testing.md gained the
  test-installer-flows row plus the previously undocumented
  test-installer-structure and test-iscsi-fresh-install-guards rows;
  commands.md documents the installer no-root hatches and the
  ZFSUTILITIES_ETC_PREFIX fixture knob; docs-integrity green; mkdocs
  build clean (only the standing Material/MkDocs-2.0 banner). Step 6:
  full suite without soaks green. PREEXISTING.md: 2 entries remain.

- **Second wrap-up pass 2026-10-17 (after the scroll/resize/ladder
  changeset; codebase FROZEN at this point).** Step 1 resolved the
  dashboard inner-table PREEXISTING entry: the three TreeView windows
  (Recent Operations / Running Tasks / Active Locks) now use the shared
  gui_helpers.capped_treeview_scroll plus the NATURAL-vscroll viewport
  guard on the dashboard page window (memory-page idiom); regression
  test red-proofed; the entry's "Config Preview" was the Configuration
  grid, which already had propagate set. Zensical rechecked again
  (0.0.71, unchanged). Steps 2-3: ruff/shellcheck green; two
  alignment_guestfs regexes given the house Regex/Purpose/Group comment
  format; treeview_row_height gained direct tests (computed + both
  fallback paths). Step 5: testing.md gained the missing
  test_alignment_guestfs row and refreshed six stale suite rows;
  gtk-gui.md Dashboard intro documents the capped windows; docs
  integrity + anchor audit green against a fresh mkdocs build. Step 6:
  full suite without soaks green (one deliberate non-root skip).
  PREEXISTING.md: 2 entries remain (Zensical wait, infra-vdev planning —
  both user-held).

- **Performance page scroll/resize/ladder fixes (2026-10-17).** All four
  user reports root-caused empirically (GTK 3.24.41 under Xvfb, real
  page build): (1) tables showed 2-2.5 rows because the inner
  ScrolledWindows never set propagate_natural_height (natural height =
  min_content_height 60) AND the page viewport's default MINIMUM
  vscroll-policy clamped the page box to the window height, making the
  box crush every table equally; fix = shared
  gui_helpers.capped_treeview_scroll (propagate + 20-row cap with a
  one-row allowance for the hscrollbar) + vscroll_policy NATURAL on
  performance_scrolled's viewport. (2) far-right column shrinks looked
  ineffective because GTK re-expands the LAST column to fill leftover
  width; each table now sets expand on one non-last column (Object /
  Members / Finding / Verdict / Vdev) plus sane default widths and
  min_width 60 (alignment columns previously defaulted to FIXED 20px).
  (3) the ladder had no horizontal scrollbar because the canvas's width
  request pinned the scroll's minimum to the draw width; the scroll now
  keeps min_content_width 100 + max_content_width tracking the page
  width, and the draw width is floored at ladder_minimum_width (new
  charting vocabulary: gutter + plot floor + legend) so narrow windows
  scroll over a readable chart; the retired design capped the viewport
  at half the page width. MatplotlibBlocksizeLadder.set_draw_width no
  longer resets the height request to -1 (that collapsed the canvas to
  1px between refreshes). (4) ladder text bumped ~1-1.5pt on matplotlib
  (title 10, ticks 9, row labels 9.5, legend 9) and 9→11px on Cairo,
  LADDER_ROW_HEIGHT 19→22. Charts-view L2ARC/SLOG tables wrapped in the
  same capped windows. Probe scratch files deleted after verification
  (verified: chain table 20.0 visible rows, ladder hscroll 870→1110,
  page vertical-only). New PREEXISTING entry: dashboard inner table
  windows have the same propagate collapse.
