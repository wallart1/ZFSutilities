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

- **unarchive-vm 205 Step-2 fix re-applied (2026-10-20).** `sudo
  unarchive-vm 205` on tweety died at "Cannot map pool NVME1 to target"
  although stewie's node.conf has had `[NVME1]=nvme1` since 2026-04-28.
  Root cause: the Step-2 ssh payload loads node-lib via `source_helper` in
  a fresh remote shell; the bare `declare -A pool_target` was function-local
  to source_helper's frame and vanished on return, emptying the map under
  `pool_to_target` (gotcha above). Fix restored verbatim from 588bad1:
  `declare -gA` in both node-lib branches + the child-bash regression test
  in tests/test-node-lib; re-red-proofed this time against the buggy lib
  (empty-map failure) before the fix, green after. Per stewie inspection at
  0.126.1 time: the `iqn.2026-02.local.stewie:nvme1` target exists and no
  `vm-205-*` backstores/LUNs remain, so the post-deploy rerun takes the
  create path on both targets (nvme1 + threeamigos) and needs no
  enroll-iscsi-pool. The production rerun stays moot until 0.126.1's
  problems are resolved and a replacement ships (deployed 0.126.1 already
  carries this fix).

- **0.126.1 threads re-applied onto 0.126.0 (2026-10-20, user-directed
  redo), uncommitted.** Two named items restored byte-identically from
  588bad1 (its parent is cd21a70 = current main, so file-level restore is
  exact): (a) the 2026-10-16 Alignment polish six-item pass + guest-FS
  probing — tooltip/ellipsize tables, 20-row capped scrolled windows
  (Dashboard + Performance), sortable scan columns, compute-node PVE config
  fetch, alignment_guestfs.py, vm-guest-fs-below-volblock WARN, vm-fs ladder
  rungs, DatasetBlocks.volsize, full-width ladder viewport — including the
  2026-10-17 follow-up already in that commit (deterministic 3-tier
  match_volumes: pinned serial / UUID-PARTUUID signature intersection with
  clone-shared refusal / size+bus; single-round-trip guest lsblk -bJ);
  (b) chart-renderer visibility (check-prerequisites matplotlib warn, Live
  Charts renderer label, Prerequisites.md system-package note). 25 files
  (10 mainline + 10 tests + 5 docs); local docs site rebuilt for the
  restored gtk-gui/python-modules content. The node-lib `declare -gA`
  unarchive-vm 205 fix + test were re-applied separately the same day
  (thread above). Standing rule from the user after those restores: every
  further issue is reworked from scratch — prior commits are ignored for
  presented issues, no restores. (RESCINDED by the user 2026-10-21, after
  the Fifth rework below: referring to prior work — git history, the
  archive branch, earlier commits — is allowed again; the already-restored
  files stand either way.) First such rework: the realized-check
  display leak (see thread below). Second (2026-10-21, the
  Performance/Alignment prompt): six of the prompt's items verified
  present in the tree (ellipsize+tooltip cells, 20-row capped scrolls,
  sortable scan columns, compute-node PVE config fetch, guest-FS
  probing, themed chart palettes); three gaps reworked new — ladder
  draw width capped at half the page allocation
  (LADDER_MAX_WIDTH_SHARE, still floored at the content minimum), cell
  tooltips fire only where text actually truncates (Pango measure vs
  column width, mock-safe), and MatplotlibRollingChart rebuilds its
  legend on style-updated so theme flips recolour legend text
  immediately. Third (same day, the Wipe-Labels kernel-notification
  prompt): zfswipe already notified the kernel on every wipe-success
  exit and the GUI refreshes its inventories after udev settles; one
  gap reworked new, red-proofed — a failed dd now triggers the
  best-effort partprobe/udevadm notification before rc=8, because
  labelclear/wipefs may already have erased signatures on that path.
  Fourth (2026-10-21, the Performance-page four-item redo prompt —
  widgets' own h-scrollbars, far-right column resize, 20-line treeviews,
  ladder text size + scrollbar): items 1–2 were verified done in the
  current tree with Xvfb probes (every overflowing table already carries
  its own live h-scrollbar, the page itself never scrolls sideways, and
  the far-right columns render honest fixed widths with the expand
  column absorbing slack and the h-range covering the full column sum);
  the real gaps reworked new: (a) capped_treeview_scroll gained
  fixed_rows=True — min_content_height pinned at the 20-row cap so
  every Performance table (empty included) keeps its 20-line window;
  the Dashboard's three call sites pass fixed_rows=False explicitly to
  keep their natural-height convention; (b) ladder text bumped one notch
  (Cairo 13px, matplotlib title 11.5 / rows 11 / ticks+legend 10.5,
  LADDER_CHAR_WIDTH_PX 8, plot floor 500); (c) the half-share draw-width
  contract was replaced — it fed max_content_width below the canvas's
  content-minimum request, and GTK answers that contradiction by
  clamping the canvas and dropping the h-scrollbar (reproduced under
  Xvfb with the Cairo ladder at a 700px window); the canvas now requests
  exactly ladder_minimum_width, the viewport stretches it to the page
  width, and _floor_ladder_scroll_width (size-allocate handler + refresh
  path) floors max_content_width at max(page, minimum). Regression
  locks: the realized check gained a geometry pass asserting all of the
  above in realized windows at 1000/700px, run under BOTH renderers via
  REALIZED_CHART_RENDERER=cairo (check names its ladder class on
  stdout); all key new assertions red-proofed by sabotage. Probe
  by-product recorded in PREEXISTING: below ~600px windows the page
  itself h-scrolls because section subtitles don't ellipsize.
  Fifth rework (2026-10-21, the "Rewrite Data complete even though none
  was done" prompt, logged 2026-10-19 on deployed 0.126.0): no forensic
  log survives (stewie + dev-host session/GUI logs from Oct 18-20 are
  gone; the code is identical to 0.126.0 — both files unmodified since),
  so root cause came from code + stewie's man page (zfs 2.4.4): the
  completion summary was unconditional (rc==0 → "complete") while rc=0
  covers a no-op rewrite (`zfs rewrite -v` prints one line per
  successfully rewritten file — zero lines on an empty/already-conformant
  dataset), AND the runner silently skipped a step whose process failed
  to spawn, finishing rc=0. Fixed both: the rewrite script tees its -v
  output to a per-dataset capture, counts rewritten files, appends
  count<TAB>ds to a per-run results file, and logs a per-dataset
  summary; the dialog's rc=0 line reports the totals ("complete (N files
  rewritten)" / "rewrote nothing — zfs rewrite reported 0 files" /
  "finished (...)" variants for unavailable/incomplete/missing-dataset
  summaries); a spawn failure is now a failed step (FATAL, rc=1,
  post-callback unrun, finally step still runs first) for every GUI
  runner operation. Red-proofed by sabotage both ways; stub-zfs
  script-execution tests lock the runtime behavior; messages manual rows
  updated.
  Still not re-applied (unnamed):
  installer execution harness (test-installer-flows, installer no-root
  hatches, ZFSUTILITIES_ETC_PREFIX, commands.md/testing.md rows).
  Guest-probe production validation remains pending (as at 0.126.1).

- **Realized-check display leak — reworked from scratch (2026-10-20).**
  During full-suite runs on a host with a desktop DISPLAY,
  tests/python/alignment_realized_check.py initialized GTK against the
  ambient display first (Xvfb was only the fallback), flashing its
  verification window on the operator's screen. Rework: the check now
  starts its private Xvfb first and the ambient display is never an
  option — DISPLAY is only ever pointed at an Xvfb the script started,
  and when that is impossible (Xvfb missing, no free number, GTK refusing
  to bind) the check skips instead of falling back; `_rebind_gtk` is the
  binder (covers the stale-initialized-flag path), the old ambient probe
  is gone. A `REALIZED-DISPLAY: :N` stdout line names the display used,
  and test_alignment_realized gained a fence test asserting that line
  exists and names something other than the inherited DISPLAY —
  red-proofed against the ambient-first code before the fix. testing.md's
  suite row updated to the private-display-only truth.

- **Reverted main to 0.126.0 (2026-10-20) — 0.126.1 has critical problems
  (user-reported, not yet diagnosed).** Main worktree reset to cd21a70
  (local only; origin/main still carries 588bad1, so local main sits behind
  by 1 until the 0.126.1 problems are worked and a new release replaces it).
  Everything from the aborted campaign — the pool-activity queue (manager,
  poolactivityctl, scrub absorption, send/receive choke point, rewrite
  integration, docs/tests) plus the Rewrite Data scope/step-failure fixes
  and the 2026-10-19 migration-sweep incident notes — is preserved verbatim
  on branch `archive/pre-revert-20261020` (commit 07010d6, 70 files,
  +10,751/−3,106). The PromptQueue worktree and its branch were removed.
  Live-state residue from the brief repo-GUI run: /var/lib/zfsutilities now
  holds pool_activity.json and scrub_state.json.20261020T163711.bak —
  0.126.0's scrub queue comes up empty until that .bak is restored (user's
  call); two dangling ~/.config symlinks from the incident remain.

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
