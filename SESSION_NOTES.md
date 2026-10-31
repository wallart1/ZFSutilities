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
(2026-10-22 prune: the 0.126.1 revert-and-redo campaign through Release
0.126.3 is committed, pushed, and released — the restore/rework/wrap-up
entries were removed; recoverable via `git log`. Live items condensed into
the threads below.)
(2026-10-22 release prune: the 0.126.3 follow-up campaign — wrap-up
usability fixes, upgrade prereq gate, rsync failure tails, CI red,
PREEXISTING resolution pass — is committed as 1e5d92e, pushed, and
released as 0.127.0; those entries were removed, recoverable via
`git log`.)
(2026-10-23 release prune: the 0.128.0 and 0.129.0 campaigns — the
unarchive-vm live-tree iSCSI rebuild + F-020..F-024 lifecycle fixes,
canmount profiles, probe-target dedupe, FHS conf precedence, both
wrap-up review passes, and the zfstestvm lun-32/33 + cron.log threads —
are committed as 3713eff/a964289, pushed, and released as v0.129.0;
those entries were removed, recoverable via `git log`. Live items
condensed into the threads below.)
(2026-10-24 release prune: the 0.130.0 combined-release campaigns — the
itf fast-re-verification + j08/j09 journeys (pub lane, 94558b8), the
iSCSI-resilience M1/M2 state map + reconcile engine with the
safe-iscsi-save hook and shared iscsi-lib parsers (pub2 lane, 5395aff),
both lane wrap-ups, the lane merge ad27709, and the parallel-repo
infrastructure notes — are committed, pushed, and released as v0.130.0;
those entries were removed, recoverable via `git log`. The lane workflow
and the same-version merge rule live in the shared agent memory and the
owner's guide.)

(2026-10-25 release prune: the 0.132.0 combined release — pub's
strict-mode campaign with the declare -gA law, the offsite hotfixes
(zfshold per-snapshot contract, j07's zfsdelfs/mydir fix), the j10
journey + F-025 baseline capture, the GUI payload e2e matrix, both
7-step wrap-ups, and (via the pub2 lane merge 6a3c26b) 0.131.0's iSCSI
resilience M3+M4 with activation wiring, the pub3 Dashboard/GUI work,
the lane merges, and the pub3-lane infrastructure notes — are
committed, pushed to origin main, tagged v0.132.0, and released; those
entries were removed, recoverable via `git log`.)

(2026-10-26 release prune: the 0.133.0 combined release — pub's
per-enclosure rate governance campaign (P1-P3) with the j12
interrupted-upgrade journey and the wrap-up fixes, and via the lane
merges pub2's iSCSI resilience M5+M6 (repair-vm-disk-refs,
export-iscsi-state --print-map, j13/j14, the F-026 fence gate fix)
with the itf run lock and orphan fence, and pub3's scheduler
%-escape fix, checkagainst ui_state resurrection fix, unsaved-changes
quit guard, cron breadcrumbs, Performance fixes, README screenshots,
and the changelog archive split — are committed (3187f7e, d7a8b38,
0111e0f), pushed to origin main, tagged v0.133.0, and released; those
entries were removed, recoverable via `git log`.)

## Persistent gotchas (not documented in docs/)

- Logs tab two-list structure (2026-10-30): the main list keeps
  `_LOG_FILENAME_RE` (core types only, unchanged); everything
  session-shaped with a non-core type routes to the collapsed
  "Miscellaneous Logs" treeview via `_MISC_LOG_FILENAME_RE` (type class
  excludes `_` so the type/name split falls on the first underscore —
  do NOT widen it to `[A-Za-z0-9_-]` or names containing underscores
  split wrong). Both lists share ONE LogIndex pass
  (`_scan_session_dir` returns both row sets and the index
  `remove_missing` runs on the union — splitting the pass into two
  scans would purge the other list's index entries every refresh).
  Shared viewer + Delete button: `_on_selection_changed` takes the
  source view and mutually clears the other list under
  `app._logs_clearing_other_view` (re-entrancy guard); the delete
  button sensitivity and `_on_delete_selected` union both views.
  Persistent-log rows (cron in main; scrub/rsync in misc) come from
  `paths` config keys via `_scan_log_and_rotations` — add new
  persistent logs to `_PERSISTENT_LOG_SPECS`, not ad hoc scans.
  Production facts that motivated this (stewie 2026-10-30): 264 of 294
  session files were `cli`; sessions dir holds nothing older than
  2026-10-21 (retention 30, prune mtime-based — the Oct 21–22 bare-metal
  OS restore is the likely history loss point, not a pruning bug).

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

- `tests/test-module-dependencies` now scans `bin/` and `lib/` too (was
  repo-root-only, i.e. vacuous — the repo root has no loose scripts). New
  scripts must resolve every called function through a direct `source`,
  `source_helper`, a `find_zfsutility_script` reference, or a variable
  assignment feeding `source "$var"`; `declare -f <fn>` guards mark a
  function as an optional caller-provided dependency (the
  zfslockmanager→node-lib pattern). The scanner masks multi-line quoted
  strings and comment tails, so python `-c` payloads and `# ... (send base)`
  comments are not mistaken for bash calls.

## Active / parked threads

- **Enclosure rate governance P4+P5 (2026-10-26) — review gates passed,
  P6 wrap-up done, uncommitted (awaiting commit instruction).** Disks
  tab: Enclosure column in the disk inventory (config name,
  kind/location fallback, blank for internal), Enclosures section
  between the panes (name / kind-location / disk count / pools / max
  rate, selection preserved across background refreshes), Set Max I/O
  Rate… action + dialog (name + pacer-grammar rate, blank = unlimited,
  invalid input re-loops with the refusal line), storage-host gating
  only. Performance tab Live Charts: "Enclosures — USB/eSATA Traffic"
  section — table (Enclosure / Pools / Read / Write / Cap / % of cap)
  via reconcile_rows + one rolling chart with a read/write series pair
  per enclosure, rebuilt when the discovered enclosure set changes.
  Wiring: DiskInfo.enclosure_id attached in DiskInventoryCache._load via
  an injected EnclosureInventory (None = not wired); leaf membership
  built in memory_page from the shared Disks-page inventory cache
  (kernel + by-id names, whole disks + partitions, exact-name mapping);
  % of cap through zfs_repository.parse_rate_limit (delegates to the
  resolver's pace_stream so the grammar cannot drift); "—" when no cap
  or no leaf row (unknown ≠ zero). Durable gotcha for future page
  sections: anything refreshed from refresh_*_page must tuple-guard its
  selection reads (see _repopulate_enclosures) — four dialog suites
  drive refresh_disks_page with MagicMock apps whose selections answer
  non-tuples, and an unguarded unpack takes them all down. P6 wrap-up
  (2026-10-26): docs anchors/cross-links verified, docs site rebuilt,
  messages-manual complete for both new GUI strings, full suite green.
  Remaining: commit on instruction; the new GUI sections reach production
  with the next release+deploy (stewie switched to 0.133.0 on 2026-10-26
  — P1-P3 cap enforcement is live there; the P4/P5 GUI is in no release
  yet).

- **2026-10-26 wrap-up housekeeping:** retired PREEXISTING.md's
  2026-10-24 test-unarchive-vm one-off flake entry (never reproduced:
  4 standalone reruns at the event, 14 in the pub3 lane where it was
  first retired, 10 consecutive standalone runs in pub today, both
  0.133.0 with-soak gates green since). If a duplicate-target refusal
  ever degrades to "Not a ZFS dataset" under load again, treat it as a
  new issue: capture /tmp/zfsutilities-test-<pid>.log immediately and
  instrument the mock zfs-list arm; do not touch product code for it.
  Zensical recheck: 0.0.73, still no 1.x — hold stands (PREEXISTING.md
  carries the standing entry).

- **Guest-probe future work (validation COMPLETE 2026-10-23):** surface
  sample.pve_failure inside the Alignment view when VM layers are
  missing.

- **0.126.1-revert residue (user decisions pending).** /var/lib/zfsutilities
  holds pool_activity.json + scrub_state.json.20261020T163711.bak from the
  brief repo-GUI run — the scrub queue comes up empty until the .bak is
  restored; two dangling ~/.config symlinks from the migration-sweep
  incident remain. The aborted pool-activity campaign lives only on branch
  `archive/pre-revert-20261020` (07010d6).

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

## 2026-10-26 — shadowed-mount rsync fence + real profile cancellation

Production report: root-backup-dailybackup pull steps failing rc=11 while
both nodes up; Dashboard cancel did nothing. Investigation (stewie, read-only
ssh): the threeamigos pool has been shadow-mounted since the 2026-10-21
13:24 boot — pool root (canmount=noauto, local) mounted AFTER its children
(mountinfo ids 60-69 attached to `/`, root id 121 on top), so
/threeamigos/proxmox resolves to the root dataset's own empty `proxmox` dir;
every rsync dest under it is ENOENT while zfs legs (dataset names, not
paths) succeed. All three 10-26 runs ended rc=11. 0.133.0 was deployed to
stewie 09:41 that morning (user-run switch-version; cron firing again —
dailybackup2 ran 12:00:01).

Fixes (this session, pub2 PROMPTQUEUE2):
- zfs_repository.validate_dest_mount_chain: every fs dataset whose
  mountpoint prefixes the dest must be mounted=yes AND path-reachable +
  ismount (the second check is what detects shadowing); zfs query failure
  refuses (hard-refuse unverifiable dests).
- command_builders.prepare_rsync_destination: shared fence used by both
  profile_runner and backup_page pull/keys loops; clean chain + missing
  tail → makedirs below the deepest dataset mountpoint (dry-run logs only);
  refusal → WARN naming the dataset, run keeps rc=11.
- _diagnose_rsync_failure: rc=11 + mkdir ENOENT → names unmounted/shadowed
  destination instead of bare "Error in file I/O".
- profile_runner graceful cancel: SIGTERM/SIGINT handler (installed in
  main) sets flag + killpg's the in-flight step (steps now spawn
  start_new_session); _run_step_list aborts at step boundaries; cancelled
  runs → history "cancelled", trailer cancelled=True, exit rc=125
  (PROFILE_CANCELLED_RC; outside rsync 0-35 and rc=9). Lock-wait also
  breaks on cancel.
- dashboard _cancel_task profile: branch now SIGTERMs the lock-file PID
  (was: log-only circular advice); _outcome_markup gained an amber ⏸ cancelled case.
- Docs: messages/index.md rows (fence WARNs, cancel INFO/FATALs, dashboard
  SIGTERM rows replacing the stale "use Cancel Selected Tasks" row),
  gtk-gui.md Profile cancel row now describes the graceful path,
  profiles.md operational guidance (shadowed mounts, canmount=noauto
  hazard, rc=125 semantics, auto-created dest dirs).

Operator remediation NOT done (user's call, live pool): unmount the five
threeamigos filesystems and remount parent-first; consider canmount=on on
the pool root so boot mounts it before children. The fence keeps backups
off the wrong filesystem meanwhile.

Test side: new TestValidateDestMountChain, TestPrepareRsyncDestination,
fence tests in run_backup_profile/on_backup_run, TestGracefulCancellation,
and a real-subprocess SIGTERM journey (rc 125 + cancelled trailer + lock
released). PREEXISTING +1: multi-file single-process pytest runs fail 16-18
order-dependent tests that pass per-file (verified identical on clean HEAD);
per-suite runner unaffected.

## 2026-10-26 (later) — mount-order governance: shadow-aware unmount, repair engine, dashboard auto-offer

Follow-up report: the user tried the stewie remediation through the GUI and
hit dataset_actions' orphaned-mount FATAL — its recovery only remounts
UNMOUNTED ancestors, so the shadow case (all ancestors mounted, pool root
covering the children) fell through to advice that cannot work ("remount
parents manually / reboot required" — remounting re-covers; lifting works;
no reboot needed). User policy: mount ordering is a product invariant —
maintained automatically, repaired with approval, properties auto-corrected
with notification, surviving reboots.

Implemented (pub2 PROMPTQUEUE2, same tree as the fence/cancel work):
- zfs_repository: _list_fs_mount_state shared query (validate_dest_mount
  chain refactored onto it); find_unreachable_mounts (mounted=yes + path
  missing/not-a-mount ⇒ erroneous, cause-agnostic);
  mount_order_property_fixes (noauto strict-prefix ancestor of an erroneous
  mount ⇒ canmount=on fix — the boot-durability lever; noauto leaves
  untouched).
- dataset_actions: shadow-aware _unmount_one_dataset — mounted ancestors +
  the selection itself join the lock set; ENOENT branch now tries
  _recover_orphaned_mount first, then (only when ALL name-ancestors are
  mounted) _lift_and_unmount: lift covers shallowest-first with busy
  dialogs, retry after each; lifted set persists across the descendant
  loop; targets already lifted are counted, not re-unmounted; restore in
  finally remounts lifted-not-targeted. Truthful FATALs naming the cover.
- Repair engine: plan_mount_repair(app, scope) (affected set = rows +
  name-ancestors; unmount deepest-first, remount shallowest-first minus
  canmount=off, property fixes), execute_mount_repair (busy gate over the
  whole unmount set; property fixes FIRST so an interrupted repair still
  converges at boot; exposure for ENOENT members mounts unmounted plan
  members then lifts; remount treats "already mounted" as ok; verification
  ismount sweep; failure ⇒ best-effort parents-first remount + FATAL with
  action plan), run_mount_repair tri-state (None clean / False
  cancelled-failed / True success).
- Surfaces: Datasets page "Repair Mount Order" button (single fs/pool
  selection, approval dialog with the full plan rendered); Dashboard
  gather now runs find_unreachable_mounts → warning rows + contextual
  "Repair Mount Order" action button (Fix Locks pattern; enabled by
  findings), handler runs scope=None repair + refresh.
- Docs: gtk-gui.md unreachable-mounts note rewritten (both shapes, lift,
  dashboard flow, canmount rationale — "reboot required" removed), Repair
  Mount Order rows in the Datasets + Dashboard action tables,
  profiles.md fence bullet points at the Dashboard repair, messages manual
  dataset_actions rows replaced/extended.

Gotchas hit while testing: assertions on patched module attributes must be
taken INSIDE the patch context (the earlier dashboard-cancel work had the
same class of bug); MockSubprocess's default `zfs get` arm emits
name/prop/value 3-col output — value-only queries need a custom handler;
repo.list_datasets(pool=<pool>) returns descendants (not the pool row).

Deploy note: after this ships + deploy, stewie's repair is one Dashboard
click (unmount 5, remount parents-first, canmount=on on threeamigos root
with approval), and the backup fence goes green.

## 2026-10-26 (wrap-up) — cycle wrap-up pass on the fence/cancel/repair changeset

Review pass over the uncommitted changes (shadowed-mount fence, graceful
profile cancellation, mount-order repair engine), pub2 PROMPTQUEUE2:

- Standards: ruff check + format clean (259 files), shellcheck silent, no
  import cycle from the new command_builders → zfs_repository edge,
  deferred dashboard imports follow the file's existing pattern. No
  violations found.
- Tests: 5 gap-filling tests added — keys-destination fence (runner +
  GUI), cancel-breaks-lock-wait unit test, SIGTERM-cancels-WAITING-profile
  subprocess journey (rc 125 + cancelled trailer), dashboard gather-level
  unreachable-mount warnings test. Fixed a harness defect from the earlier
  session: three test files had new classes appended BELOW the
  `if __name__ == "__main__"` guard (test_dataset_actions 1194 lines,
  test_zfs_repository 639, test_dashboard_page 28) — unreachable under
  direct execution; guards moved to the true file ends. Sanctioned pytest
  behavior unchanged (classes were collected either way).
- python-modules.md: added the new public functions (validate_dest_mount
  chain / find_unreachable_mounts / mount_order_property_fixes /
  prepare_rsync_destination / run_mount_repair / on_datasets_repair_
  mount_order), corrected command_builders' now-false "stdlib only" note,
  profile_runner cancellation paragraph, dashboard/backup row updates.
- test_docs_integrity 23 green; mkdocs build green (known Zensical warning
  only — rechecked PyPI: 0.0.73, still no 1.x, hold stands).
- Full non-soak run green: 105 suites / 5598 passed / 0 failed (18 Python
  env-preflight skips as always on the dev host).
- PREEXISTING: no new entries; 3 remain (Zensical hold refreshed, pub3-lane
  unarchive flake not present in this lane's file, cross-file pytest
  ordering flake). Direct `python <file>` test execution remains
  unsupported (golden files key on pytest module names; conftest does the
  bootstrap) — by design, not recorded as an issue.

## 2026-10-26 — pub3: 0.131.0 with-soak flake entry retired; Datasets Show Details in Log button

- PREEXISTING resolution attempt for the 2026-10-24 0.131.0 with-soak
  flake (test-unarchive-vm, "Step 2 refuses duplicate same-short
  targets"): could not reproduce. 11 standalone suite runs plus 3 full
  `run-tests --with-soak` gates — one solo and two run concurrently to
  recreate (and exceed) the recorded "~2x parallel load" — all green;
  the suite passed everywhere. Entry retired per the user's rule
  (reproduce → fix, else retire).
- The concurrent-gate stress surfaced two NEW pre-existing findings,
  both recorded in PREEXISTING.md (not fixed, awaiting prompt):
  two simultaneous full runs deterministically collide in
  test-sever-vm-clone via the product's pid-less state-file path
  `/tmp/sever-vm-clone-${key}-$(date +%s).state` (bin/sever-vm-clone:711)
  — both runs failed that suite, 3 tests each; and a failed suite's
  "retained for post-mortem" log vanished within minutes (canary test:
  non-empty dead-pid logs survive the test-lib sweep, empty "retained"
  logs are reaped by the next sourcing suite; why the failed suite's
  log was empty is unidentified). Practical rule: capture
  /tmp/zfsutilities-test-<pid>.log immediately on any suite failure.
- GUI: new Datasets-page action button "Show Details in Log" — same
  action as the context-menu "Send details to log" (shared handler
  `_send_selection_details_to_log`), enabled for exactly one selected
  pool/dataset/snapshot/hold (volume partitions excluded — they are not
  ZFS datasets). Wired in action_dispatch.py (PAGE_SPECS +
  ACTION_HANDLERS, attr `_ds_details_btn`, placed after Show Big Stuff)
  and update_ds_button_sensitivity; tests in test_action_dispatch.py
  and test_datasets_page.py; gtk-gui.md button-table row added.

## 2026-10-26 — pub3: deferred-work items resolved (pycache, sever /tmp leak, docs drift)

- Root-owned __pycache__: pub3 is now clean — its single root-owned
  file (python/__pycache__/disk_surface_test.cpython-312.pyc) sat in a
  dan-owned directory, so dan could unlink it without root; removed,
  zero root-owned files remain in the lane. NOT touched, per the
  working-dir rule: pub (its python/__pycache__ directory itself is
  root-owned — genuinely needs root) and pub2 (one dan-sweepable
  root-owned .pyc). The "next root session" note now covers only those
  two lanes.
- The "~65 empty /tmp bisect leftovers" were not static leftovers but
  an active product leak, growing with every test run (~30 from this
  session's gate runs alone). Root cause: sever_transfer captured the
  transfer worker's exit with a bare `rc=$?` while sever-vm-clone runs
  under set -euo pipefail, so a failed worker (e.g. the phase-1 clone
  gate's exit 1 inside the generated worker) killed the parent before
  the rc handler — the results mktemp leaked AND the scripted
  "FATAL: Transfer phase failed / re-run to resume" guidance was dead
  code. Fixed in bin/sever-vm-clone: `|| rc=$?` in both sever_transfer
  branches (the idiom sever_run_storage_worker already used) and in
  sever_transfer_remote's worker ssh, plus append_exit_trap rm of the
  scratch results file after mktemp (state file deliberately excluded —
  --continue needs it). Measured 2 leaked files per suite run before,
  0 across 6 consecutive green runs after; the revived FATAL guidance
  now prints on gate-abort paths. 61 existing empty files swept
  (verified all empty). tmpfiles remains only the SIGKILL/power-loss
  backstop.
- Follow-on finding, appended to the existing PREEXISTING collision
  entry: a FAILED suite run leaves stale /tmp/sever-vm-clone-*.state
  residue that poisons the NEXT run — its find-based --continue tests
  pick the oldest (stale) state file and fail confusingly (observed
  live: two flaky runs whose --continue referenced the previous run's
  epoch-named state). Clear /tmp/sever-vm-clone-* between reruns of a
  failed suite; clean-slate runs are deterministic-green.
- Docs drift resolved: testing.md's real-pool integration "Scenarios
  Covered" table listed 8 scenarios; the suite has had 7 since birth
  (1abd8de) — the phantom "Full copy with one source snapshot" row
  (never implemented) is removed. If that scenario is wanted for real,
  it needs a root session on the zfstest pools. zfstest3 in
  ALLOWED_TEST_POOLS verified intentional, not drift: the pool is
  online, the entry is the documented ZFSUTILITIES_TEST_DST_POOL
  override affordance, and the python e2e layer uses zfstest3
  (offsite chain, restore destination) — no change.
- Verification: shellcheck clean on bin/sever-vm-clone; full suite
  green once at the end; zero /tmp residue after.

## 2026-10-26 — pub3: Zensical watch retired (user-directed)

- The Zensical PREEXISTING entry (mkdocs 2.x deprecation warning; pin
  mkdocs<2 vs migrate to Zensical decision) is RETIRED at the user's
  direction: the user receives email notification of every upstream
  release and will prompt the migration when Zensical 1.x ships — no
  agent-side PyPI rechecks, ever. State at retirement per the user:
  PyPI still 0.0.72, no 1.x; the mkdocs<2 pin remains the documented
  product stance; the original analysis lives in the Zensical thread
  above. No docs referenced the watch, so no doc changes were needed.
  (pub and pub2 lanes still carry their own copies of this entry —
  outside this lane's scope; they fold away at the next lane merge.)

## 2026-10-26 — pub3: bin/ coverage question closed; fence flipped to strict mode

- User decision on the untested bin/ commands: the 17 zero-coverage
  scripts (enumerated for them this turn) are old, miscellaneous, largely
  isolated, and permanently EXCLUDED from behavioral coverage. Never
  re-raise as a gap, never build suites for them; the named list is
  recorded in agent memory and is CLOSED — no command is ever added to
  it without the user's explicit approval (mid-turn instruction,
  2026-10-26). Not a PREEXISTING matter (a decision, not a
  defect).
- check-vm-disk-paths is now strict, closing the "non-strict leaf"
  residue. Why it was missed originally: born 2026-10-24 21:54 in the
  0.131.0 lane commit (8ef7074) while the 0.132.0 strict-mode campaign
  (3667358, next morning) ran from a tree that never contained the file
  (verified: ls-tree of the campaign commit is empty for it; the birth
  commit is not an ancestor) — a parallel-lane blind spot, no deliberate
  exclusion, so the user's "flip it if no good reason" applied.
- The flip: `set -euo pipefail` directly before the bashinit bootstrap
  (the guard's head-region contract); check-vm-disk-paths registered in
  tests/test-strict-mode's strict_scripts list with a comment recording
  the parallel-lane origin; test-check-vm-disk-paths gained the
  options-restore line after its eval (the restore is load-bearing —
  red-proven: without it the suite aborts under the leaked strict
  options). A rootcheck stub I first added to the suite was REMOVED
  after its own red-proof passed without it: tests/test-lib.sh:47
  already stubs rootcheck() for every suite. `is_single_node && exit 0`
  needed no fencing — a short-circuited AND-list does not trigger
  errexit (same construct as reconcile-iscsi-state:59, already guarded).
  No docs changes: testing.md's guard row already says new strict-mode
  scripts register there, and coding-policies states the law without a
  list.
- Verification: fence suite and strict-mode guard green (guard red-proof:
  removing the set line fails it); shellcheck clean on all three changed
  files; full suite green once at the end (stale /tmp/sever-vm-clone-*
  residue cleared first per the PREEXISTING prescription).

## 2026-10-26 — pub3: disposable dev host REJECTED (user decision)

- The parked recommendation (a disposable dev host for root/real-pool
  testing, final shape: clone the dev VM + sanitize) is REJECTED by the
  user — "the risk of leaking secrets is too high." Retired from the
  deferred-work parking lot; decision recorded in agent memory
  (disposable-dev-host-rejected) with a never-re-propose rule that also
  bars cloning any credential-bearing host as a test venue. Nothing to
  unwind in docs — the testing.md paragraph was never written.



## 2026-10-26 — pub3: development-cycle wrap-up and 0.134.0 release

- Wrap-up review (steps: pub-main-only PREEXISTING pass skipped by
  precondition — pub3 is a lane; standards review of the uncommitted
  changes against coding-policies.md — clean, no edits needed
  (shellcheck/ruff/100-col all green; .shellcheckrc already covers the
  runtime-resolved sources, so no extra directive was required); test
  review found the sever-vm-clone transfer-failure path untested → new
  test_transfer_failure_resume_guidance (Test 16): engine failure must
  surface the parent's resume guidance, run nothing destructive, leak
  no scratch results file. Red-proven by reverting the `|| rc=$?`
  capture (exactly Test 16 failed; product restored md5-identical);
  suite 26/26 green after. Note: the residue assertion red-proves the
  rc-capture half; the EXIT-trap's kill-window-only value is covered
  but not separately red-proven (no signal-kill harness in the family).
- Docs: user FYI incorporated — the Datasets tab's tree conventions
  now state a top-level "pool" row is the pool's root filesystem
  dataset, cross-referencing the Pools page for the pool object
  (first draft pointed at Dashboard Pool Health; corrected to the
  Pools tab). testing.md: phantom real-pool scenario row removed
  (suite had 7 scenarios since birth, docs said 8) and the sever suite
  row records the new coverage. docs-integrity 23 passed; mkdocs
  rebuilt clean both times (known mkdocs-material deprecation warning
  only — standing mkdocs<2 pin).
- Release 0.134.0: VERSION bumped, changelog section written (Added:
  Show Details in Log button; Fixed: sever-vm-clone failed-transfer
  guidance + /tmp scratch leak; Changed: check-vm-disk-paths strict;
  Tests; Documentation). Changelog archive NOT moved: 0.133.0's
  creation of the archive left 0.130.0+ in the main file and no rule
  enforces a split — followed that precedent.
- Gates: full no-soak run green; full --with-soak run green (soak
  gating exercised); zero /tmp/sever-vm-clone-* residue after both.
  Retained-log vanishing recurred once during red-proof (empty when
  read minutes later) — already covered by the existing PREEXISTING
  entry, no new entry. PREEXISTING.md unchanged at 2 entries
  (lane-scoped, awaiting user prompt; the step-1 resolution pass is
  pub-main-only by its own precondition).

## 2026-10-27 — Bare-metal-backup boot incident analysis (analysis only, 0-line diff)

User shut tweety then stewie down for bare-metal backups; first stewie
boot came up with two fivebays-named pools and no threeamigos (user
re-imported threeamigos' disks under the right name, GUID
4338716537971988948), and iSCSI booted with 3/33 LUNs. Recovered by
the user via a z.ai web session (docs:
zfsutilities-plan/iscsi-recovery-chat-log.md + verbatim twin). This
turn: analysis + recommendations, no code changes.

- Repo rename search: the ONLY project code that writes a pool name at
  import is the GUI Migrate Pool wizard (zfs_repository
  build_pool_import_rename_command; temp `_mig` names; destination
  re-imported under SOURCE name). It cannot relabel threeamigos'
  disks as "fivebays"; no bin/lib/cron path issues export/import with
  a name. CAUSE CONFIRMED by the user 2026-10-27 (same day): they ran
  `sudo zpool import threeamigos fivebays` intending to import two
  pools by name — the positional second argument is a RENAME, so the
  command relabeled threeamigos as fivebays on disk. Label-only, no
  data touched (pool healthy since); repo exonerated; the zpool
  history root-commands are no longer needed for this question.
- iSCSI root enabler (product defect, in-scope): all three degraded
  gates count BACKSTORES, not LUN mappings — safe-iscsi-save:181-216
  (targetcli block ls /dev/zvol/ lines), export-iscsi-state
  enforce_not_degraded:356 (backstore names), reconcile
  refresh_pool_map. "33/33" passed while 3 LUNs were exported →
  degraded state persisted over saveconfig.json, saveconfig-boot.json,
  and the pool-resident iscsi-state.json map (the M1 recovery
  authority) during the boot window.
- Also found: pre-start-backup.conf template ships the systemd `$f`
  escaping bug (share/two-node line 9 — `$$f` needed; evidence says cp
  landed at /.pre-start relative dest); boot-config.conf uses bare
  `$boot` (same hazard, happened to work); rtslib restore has NO
  After= on ZFS units (11:46 boot shows import-cache can finish before
  USB enclosures enumerate; service exits 0 on failure); iscsi-
  recover-encrypted-luns rebuilds TPG LUNs but never ACL MappedLUNs
  (the runbook caveat); fence never landed a successful reconcile on
  production (tweety fence failed; root@stewie ssh unproven outside
  ITF; hand-rolled iscsi-auto-recover crash-looped, NOT repo code).
- Corrections to memory: 0.134.0 IS deployed+active on stewie
  (readlink bin → versions/0.134.0); threeamigos shadow-mount appears
  HEALED by the re-import (canmount=on, children mounted) — 0.134.0
  Repair Mount Order click likely unnecessary.
- Recommendations delivered in the turn report (8 items: LUN-count
  gates, $$-escape templates + unit test, rtslib After= ordering,
  recover-encrypted ACL MappedLUNs, post-restore verify + Dashboard
  warn, fence ssh surfacing, pool name↔GUID identity fence, deploy +
  standing exercise). PREEXISTING.md unchanged (3 entries; all finds
  are in-scope outputs of this analysis).

## 2026-10-27 — iSCSI Boot-Incident Hardening, Phase 1 complete (LUN-topology gates)

Executed Phase 1 of `zfsutilities-plan/iSCSI Boot-Incident Hardening —
Phased Plan` (approved coding plan, no deviations beyond the flagged
§1b clarification below). Root fix: all three degraded gates now compare
LUN mappings under the manifest's authority, not backstore counts.

- 1a `bin/safe-iscsi-save`: keeps the count pre-check; new authoritative
  gate stages the live config (`targetcli saveconfig <temp>` beside the
  destination), compares every old TPG LUN mapping `(target,lun)→bs` and
  ACL MappedLUN grant whose backstore is still in the manifest, refuses
  before ANY write on loss (atomic `mv` install only on pass — replaces
  the direct saveconfig), secondary WARN for a permitted loss whose zvol
  still exists. Caller `bin/iscsi-add-encrypted-luns`: save refusal →
  WARN + exit 0 (boot ExecStartPost must not fail the unit by design);
  `iscsi-recover-encrypted-luns` unchanged (keeps rc 1 via failed++).
- 1b `bin/export-iscsi-state`: new `report_map_losses` (modeled on
  report_state_drift) drives `enforce_not_degraded` when a prior map
  exists — a recorded mapping may vanish only if its backstore left the
  manifest; manifest missing → no loss permitted; empty manifest →
  target-only transition only. Count floor remains only when no map
  exists. `read_json_backstore_count` removed (dead). §1b clarification
  (flagged in the approved plan): the manifest exception applies to the
  map fence too — without it every legitimate disk removal (remove/
  move/archive → save → export hook) would FATAL the map refresh forever.
- 1c `bin/reconcile-iscsi-state`: vm_cross_check moved BEFORE
  refresh_pool_map (the 14:01/14:06 fence-tick hole); complete-condition
  gains _vm_missing_refs, _vm_noentry_refs, _save_failed, failed:*
  outcomes; WARN names the blocking reasons.
- Tests: safe-iscsi-save harness consolidated (core helper + live-config
  writer; boot-config fixtures gained the wwn they always should have
  had) + 5 new tests (incident 33/3 shape, legit shrinkage, MappedLUN
  loss, stale-zvol WARN, staging failure); export +3 (LOSS lines, legit
  shrinkage refresh, broken empty manifest); reconcile +1 and
  save-failure test extended (both refresh blockers); add-encrypted +1
  (WARN + rc 0). All four gates red-proofed by temporarily disabling
  each check. Full suite 105/105 green.
- Docs: two-node.md gate semantics in all four script sections;
  messages/index.md rows for every new FATAL/WARN line + reworded
  degraded/map-unchanged rows.
- Not done here (later phases): drop-in $$ + After= fixes (P2),
  recover/add ACL MappedLUN work (P3), visibility (P4), pool identity
  fence (P5), deploy/exercise (P6). PREEXISTING.md: 3 entries, none
  added or addressed (all finds in-scope and fixed).

## 2026-10-27 — iSCSI Boot-Incident Hardening, Phase 2 complete (systemd drop-in fixes)

Executed Phase 2 of `zfsutilities-plan/iSCSI Boot-Incident Hardening —
Phased Plan` (approved coding plan, no deviations). Both shipped
rtslib-fb-targetctl drop-ins fixed; structural test added red-first.

- pre-start-backup.conf: `$$f`/`$${f}` escaping. Mechanism verified on
  the dev host with transient user units: systemd expands the braced
  `${f}` against its own empty environment before bash parses the
  script, so the backup cp received the relative dest `.pre-start` and
  landed in the service CWD (the stewie `/.pre-start` artifact); the
  bare `$f` had only passed through by undocumented luck. The
  `$$`-escaped form was verified end-to-end (backup lands beside the
  source).
- boot-config.conf: `$$boot`; new `[Unit]`
  After=zfs-import-cache.service zfs-import.target zfs-volume.service +
  Wants=zfs-import.target (USB enclosures can enumerate after
  import-cache completes — the 11:46 boot; restore needs zvol nodes;
  missing units ignored by systemd).
- tests/test-switch-version: new test_shipped_rtslib_dropins_match_dropin_design
  (models test_shipped_fence_units_match_fence_design): every Exec line
  in both shipped drop-ins, after stripping `$$`, must contain no `$`
  (whole hazard class, vacuous-match guarded); boot-config must carry
  the After=/Wants= lines. Red-proofed: failed on all four findings
  against the pre-fix files; green after the fixes.
- Docs: developer-guide/two-node-config.md drop-in section ($$ rule,
  boot ordering, stray `/.pre-start` cleanup note);
  messages/index.md NEW "iSCSI Boot Drop-ins (rtslib-fb-targetctl)"
  section for the four `targetctl:` journal lines (were undocumented).
- Gates: test-switch-version 17/17; shellcheck clean on the changed
  test file; test_docs_integrity green; mkdocs build clean; full suite
  green (0 failures, normal dev-host preflight skips).
- Deployment rides the existing install_rtslib_dropins refresh
  (cmp -s + daemon-reload at next switch-version activation on the
  storage host; tweety correctly skips — no targetctl). Stale
  `/.pre-start` removal stays the user's root step (Phase 6 exercise).
  Not done here: P3 ACL MappedLUN recovery, P4 visibility, P5 pool
  identity fence, P6 wrap-up/deploy. PREEXISTING.md: 3 entries, none
  added or addressed.

## 2026-10-27 — iSCSI Boot-Incident Hardening, Phase 3 complete (encrypted-LUN recovery completeness)

Executed Phase 3 of `zfsutilities-plan/iSCSI Boot-Incident Hardening — Phased
Plan` (approved coding plan, no deviations beyond the disclosures below).
Theme: after a LUN is (re)created, every existing ACL initiator on the target
is granted a MappedLUN at that index; restore-luns becomes a complete
backstore/LUN/ACL/grant restore; the add hook stops auto-assigning LUN
indexes.

- Schema/signature facts verified against stewie's rtslib-fb + targetcli
  package source BEFORE coding: per-initiator create is
  `acls/<initiator> create <mapped_lun> <tpg_lun>` (FIRST arg is the
  initiator-visible index); saveconfig ACL records are `node_wwn` +
  `mapped_luns[].{index, tpg_lun}` (Phase 1's gate keys confirmed).
- lib/iscsi-lib.sh: new `iscsi_grant_lun_to_acls <iqn> <lun>` — idempotent
  identity grants to every live ACL initiator (parse_target_acls reuse,
  post-create verification, WARN detail lines + rc). Sourced by recover/add
  the way reconcile/export source the lib.
- iscsi-recover-encrypted-luns: grant step on BOTH loop paths (newly-mapped
  AND already-present — a re-run heals grants for surviving mappings);
  grant failure = FATAL + failed++.
- iscsi-add-encrypted-luns: lookup now precedes backstore create; no
  recorded index → WARN + skip (auto-LUN fallback removed; entries no
  longer leave unmapped backstores behind); grant step boot-safe (WARN,
  still exit 0).
- iscsi-restore-luns: NEW third loop restores ACL nodes + MappedLUN grants
  exactly as recorded (non-identity mappings faithful; present-but-wrong
  grant → WARN, never remapped); record delimiter switched `:`→`|` (found
  while implementing: the old IFS=: read split inside every real IQN — the
  LUN-restore loop could never have worked on production; fixed in-scope);
  save-refusal pass-through (WARN, rescan still runs, exit 1); rescan also
  triggered by grant additions; summary line counts all four dimensions.
- reconcile-iscsi-state: found in-scope defect — ACL grant call used
  `create mapped_lun <idx>`, which targetcli rejects (non-integer
  mapped_lun); `|| true` hid it, so reconcile's grants NEVER landed and its
  "Granted N LUN(s)" line was false. Fixed to `create <idx> <idx>` (identity,
  demo-equivalent); failures now FATAL + fail the run; the ✓ line reports
  ok/total.
- Tests: recover +3 (grants on add path, heal on already-present path,
  grant-failure rc 1; stateful acls mock + GRANT_FAIL injection; real
  iscsi-lib sourced with pool_to_target stub per the lib's own probe
  comment); add +2 (no-index WARN+skip, grant line asserted) + 4 legacy
  tests gained recorded-index fixtures (they had been relying on the
  removed auto-LUN fallback); NEW tests/test-iscsi-restore-luns (Style A,
  5 tests: full restore incl. non-identity 8→3 grant, idempotent re-run,
  save-refusal rescan+rc1, unavailable-device skip, wrong-grant no-remap;
  mock models targetcli create-failure semantics — taken index/backstore
  means create fails); reconcile regression test flipped to assert
  `create 0 0` and NO `create mapped_lun`, + grant-failure test. All six
  new gates red-proofed by temporary revert (helper neutered → 4 failures;
  add skip removed → 1; restore ACL emit neutered → 4; restore set-e save
  death restored → 1; reconcile syntax reverted → 1).
- Docs: two-node.md (add/recover/restore/reconcile sections — flows, called
  modules, rc table gains restore's save-refused 1); proxmox-integration.md
  short path + manual equivalent gains the ACL grant step (the manual
  mapped_lun caveat is gone); messages/index.md rows for every new
  INFO/WARN/FATAL line (auto-LUN row removed).
- Gates: shellcheck clean on all 9 changed bash files; affected suites
  green (recover 8/8, add 9/9, restore 5/5 NEW, reconcile 22/22); full
  suite green via tests/run-tests.
- Not done here (later phases): P4 visibility, P5 pool identity fence, P6
  wrap-up/deploy. PREEXISTING.md: 3 entries, none added; the reconcile
  grant-syntax defect and the restore-luns IFS=: parse defect were found
  and fixed in-scope this turn.

## 2026-10-28 — iSCSI Boot-Incident Hardening, Phase 4 complete (make degradation visible)

Executed Phase 4 of `zfsutilities-plan/iSCSI Boot-Incident Hardening — Phased
Plan` (approved coding plan; deviations disclosed below). Theme: the silent
3-of-33 boot now surfaces in three places — the boot journal, the Dashboard
iSCSI box, and the fence's own reporting.

- Boot verification (share/two-node/rtslib-fb-targetctl-boot-config.conf):
  second ExecStartPost runs `export-iscsi-state --check` in a guard wrapper
  (`timeout 120`, output captured, always exit 0 — a wedged targetcli can
  neither hang nor fail the unit). Journal lines: OK on match, FAILED (plan
  verbatim) + the check's DRIFT/FATAL detail lines on mismatch, skip line
  when the helper is absent, silence on single-node rc-0-no-output. Header
  documents the expected every-boot FAILED while encrypted keys pend (stewie
  has exactly 2 encrypted LUNs: vm-101-disk-1, vm-202-disk-5).
- Dashboard LUN shortfall (python/dashboard_page.py): _get_iscsi_missing_luns
  split into TTL wrapper (wear-cache pattern, 300 s, failures not cached) +
  _compute_iscsi_missing_luns, which now also reads `targetcli /iscsi ls`
  (one call; `block/vm-` anchor mirroring parse_target_luns) and flags
  expected∧loaded∧unmapped backstores as kind "unmapped" rows — the
  incident's exact shape, previously rendered "All VM disks are exported".
  Rows render through the existing ⚠/Fix-this pattern; repair-iscsi-luns
  already re-maps loaded manifest backstores, so the handler needed only a
  cache invalidation before refresh. Formatter + tooltip extended.
- Fence-failure row (python/dashboard_page.py): _get_fence_failure_warning,
  TTL-cached 300 s (bounds the added ssh to ≤12 logins/hr against the 120 s
  dashboard refresh — the tweety journal-churn constraint), queries
  `systemctl is-failed zfsutilities-iscsi-fence.service` on the peer
  (direct when local, ssh root@peer otherwise, timeout 10); warns ONLY on
  exactly "failed" — inactive-between-ticks is healthy, unreachable peer is
  silent. Wired into _gather_dashboard_data beside the unreachable-mount
  rows.
- check-vm-disk-paths: remote_reconcile_run now returns ssh's rc — 255 (or
  an empty script-path resolve, previously a silent no-op ssh returning 0)
  gets its own WARN ("ssh to storage host ... failed — reconcile-iscsi-state
  did not run"); other non-zero keeps the existing "reported problems" WARN.
- Tests: test-switch-version structural test extended (verifier
  ExecStartPost present + ends `exit 0`; the Phase 2 no-unescaped-$ loop
  covers the new line automatically); test-check-vm-disk-paths +2 (rc 255
  case incl. NOT-reporting "reported problems"; empty-resolver case, ssh
  count 0); test_dashboard_page — compute-level unmapped suite (missing /
  unmapped / mapped-clean / incident-shape / both timeout paths), TTL-cache
  suite (cache-hit, failure-not-cached, expiry), Fix-this cache-reset,
  formatter unmapped branch, unmapped row renders with Fix this, fence
  gatherer suite (failed/inactive/ssh-rc-255/local-vs-remote cmd/never-
  queries cases + TTL), gather-level fence-warning test, and the new source
  added to every existing gather/refresh patch stack (incl. rewriting the
  deeply-nested unreachable-mounts gather test into the parenthesized with
  style). All four new gates red-proofed by temporary revert (bash 255
  branch, drop-in line, python unmapped detection, fence gather wiring).
  One self-inflicted test bug found via bash -x trace: my suffix assertion
  lost its trailing glob star and then miscounted `exit 0'` as 8 chars.
- Docs: two-node.md Dashboard iSCSI Issues (What "no LUN mapping" means +
  fence-failure warning subsection + causes/fix wording), export-iscsi-state
  --check row notes the boot drop-in, check-vm-disk-paths flow names the two
  distinct WARNs; developer-guide two-node-config.md boot-config.conf
  documents the verifier incl. the encrypted-pending expectation;
  messages/index.md — drop-in section gains 3 rows (helper-missing skip,
  OK, FAILED+DRIFT), check-vm-disk-paths gains the ssh-failed row and the
  "reported problems" row narrowed to refusals. Disclosed deviation: the two
  new Dashboard UI strings are documented in two-node.md only —
  messages/index.md catalogs log lines, not UI-rendered strings (verified
  against the unreachable-mount precedent).
- Gates: shellcheck clean (check-vm-disk-paths); ruff check+format clean
  (dashboard_page.py + test file); affected suites green during iteration;
  full tests/run-tests green (106 suites, 0 failed); full run-python-tests
  green; docs-integrity 23/23; mkdocs site rebuilt (only the standing
  mkdocs-2.0 nag).
- Not done here (later phases): P5 pool identity fence, P6 wrap-up/deploy/
  production exercise. PREEXISTING.md: 3 entries standing, none added (the
  empty-resolver no-op was found and fixed in-scope inside the function
  Phase 4 modifies). Mid-turn user cleanup landed: zero root-owned
  __pycache__/pyc remain anywhere in the repo (verified by find -user root).

## 2026-10-28 — iSCSI Boot-Incident Hardening, Phase 5 complete (pool identity fence)

Executed Phase 5 of `zfsutilities-plan/iSCSI Boot-Incident Hardening — Phased
Plan` (approved coding plan; deviations disclosed below). Theme: a pool
renamed or replaced under a known name — the class of silent corruption the
incident analysis flagged after LUN topology — now surfaces everywhere, and
nothing ever renames/repairs an identity automatically.

- Map schema (bin/export-iscsi-state): collect_live_state reads each
  configured pool's GUID (`zpool get -H -o value guid`) into
  _state_pool_guids (unreadable/non-digit GUID omits the pool — an offline
  pool must not fail the export); emit_state_json gains a sorted top-level
  "pools" object between storage_ip and targets; version stays 1 (additive).
  report_state_drift compares pools for names on BOTH sides only — a GUID
  change is a DRIFT line, a one-sided name is deliberately not drift (the
  offline-pool tolerance). Golden updated; diff verified to be exactly the
  new pools block.
- Map consumers: reconcile parse_state_map emits/validates POOL|name|guid
  records into _map_pool_guid (evidence only — reconcile rebuilds LUNs,
  never identities; non-digit records dropped). repair-vm-disk-refs verified
  .get()-tolerant, untouched.
- Detector (lib/iscsi-lib.sh): detect_pool_identity — (a) expected vs
  imported both directions (expected from pool_list when node-lib is loaded,
  else the map's pools keys, so the standalone check-prerequisites gate gets
  real coverage; empty expected set = quiet skip), (b) live GUID vs
  map-recorded GUID, (c) `zpool import` candidates duplicating an imported
  name, scoped to non-zvol leaf devices (_detect_is_zvol_leaf: zd<digits>
  [p<digits>] or /dev/zvol/ paths — ITF guest pools on zvols stay silent;
  fixed-string decomposition, no regex/extglob). read_map_pool_guids helper
  (python3, read_json_string_field model). newest_iscsi_state_map now
  searches configured pools via pool_list when loaded, else every imported
  pool (_state_map_search_pools) — existing callers unchanged.
- Wiring: check-prerequisites --two-node runs identity as its own detection
  pass after the restore block (never masquerades as restore evidence,
  never enters --list-failures); setup-iscsi-targets prints identity
  findings in their own WARN block WITHOUT the reconcile offer (reconcile
  cannot resolve identities — disclosed design decision). Note: a
  configured-but-deliberately-exported pool (z22tb's offline posture) would
  warn on every run under (a); today all five stewie pools are imported, and
  the plan file explicitly asks for the "expected pool missing" finding.
- Dashboard: PoolRow gains guid (zpool list ...,ckpoint,guid; only
  construction site is list_pools; MockSubprocess.add_zpool_list emits a
  default guid column so consumers don't silently lose rows);
  _get_pool_identity_warnings (fence TTL-cache pattern) +
  _compute_pool_identity_warnings(repo=None) + _read_newest_state_map_pools
  (newest map by "generated" across expected pools) → Warnings-section rows
  for not-imported / not-configured / GUID-changed; unresolvable live GUID
  ("-", non-digit) is not an identity signal. Deviation from plan wording:
  zpool-list failure returns None and surfaces no row (fence-gatherer
  transient-failure tolerance) rather than a stale indicator — the cache
  retries next refresh.
- Tests: test-lib zpool mock gains get-guid + import-fixture branches
  (arity-safe with ${n:-} after a first full-suite run caught $5 unbound
  under set -u in test-zfsshowbigstuff — fixed, suite green); export suite:
  structure/golden/GUID-omission/GUID-drift; reconcile suite: base map
  gains pools, 3 new POOL-record tests (all 22 existing tests green on the
  pools-bearing fixture = tolerance proof); check-prerequisites suite:
  zpool/zfs stubs fixture-driven (ZPOOL_LIST/GUID/IMPORT_FIXTURE,
  ZFS_MOUNTPOINTS_FIXTURE) + PYTHON3_DELEGATE knob (stub python3 execs the
  real interpreter so read_json_string_field/read_map_pool_guids work under
  the sealed PATH; matplotlib tests unaffected) + 7 identity tests incl.
  the zd*-silence ITF proof; setup-iscsi-targets suite: runner gains
  zfs-mountpoint + zpool mocks, identity scenario + 2 tests; python:
  repository 8-column updates, dashboard TestComputePoolIdentityWarnings
  (9 cases) + gather wiring test + new source added to the existing gather
  patch stack. All five core gates red-proofed by temporary revert.
- Docs: data-structures.md map key table + example + "pool identity,
  compared and never rewritten" semantics bullet; two-node.md
  export/reconcile/setup-iscsi-targets sections (incl. step 7 identity
  pass, zpool row, map-read row); messages/index.md — check-prerequisites
  6 rows, setup-iscsi-targets 6 rows, export-iscsi-state pools-DRIFT row,
  dashboard_page 3 warning rows.
- Gates: shellcheck clean (5 product + 5 test files); ruff check+format
  clean (2 product + 3 test files); full tests/run-tests green (0 suite
  failures after the mock arity fix); run-python-tests green (295
  dashboard / 224 repository / 23 docs-integrity); mkdocs --strict rebuilt
  rc=0 (only the standing mkdocs-2.0 nag). PREEXISTING.md: 3 entries
  standing, none added (the set -u mock crash was in this phase's own new
  code and fixed in-scope).
- Not done here: Phase 6 wrap-up/deploy/production exercise (on cue).

## 2026-10-28 — iSCSI Boot-Incident Hardening, Phase 6 wrap-up steps 1-6 (code freeze)

User-directed 7-step wrap-up (PUB repo); steps 1-6 executed in strict
sequence, step 7 = freeze. All three PREEXISTING entries resolved and
removed (file now empty):

- Retained-log vanishing: test-lib subshell re-sources (sever_run's
  `$(...)` pattern) shared $$ with the suite and re-truncated the
  parent's log mid-run (the 0-byte mechanism); truncation now guarded to
  BASHPID==$$ and _test_lib_cleanup stamps a retained log non-empty, so
  the source-time sweep can never reap a post-mortem.
- sever-vm-clone concurrent collision: state-file name now pid-qualified
  (`<key>-$$-<epoch>.state`); the suite's recovery tests take the exact
  path from the product's own `--continue` output
  (sever_state_path_from_output) instead of globbing /tmp; the env_new
  sweep is GONE (it deleted a concurrent suite's in-flight file);
  aborting tests clean their own file via sever_rm_state_file; a
  name-shape regex pin guards the pid field. Proof: two concurrent suite
  runs both green, zero /tmp residue.
- Cross-file pytest pollution: root cause found (not the suspected
  global mock patch) — test_backup_page imported backup_page fresh
  inside mock_gtk while gui_helpers stayed bound to REAL gi (imported
  earlier by another file in the same pytest process); bold_label then
  built a REAL widget with sys.modules["gi.repository.Gtk"] mocked,
  pygi's C marshalling swallowed an isinstance TypeError, and every
  later real-gi call in the process died with SystemError (persistent,
  C-level). Fix: all 26 mock_gtk() contexts in test_backup_page now
  fresh=True (the file already had 2 fresh sites); documented 5-file
  command 728 passed twice (was 16-18 failed).

Also in the pass: two >100-char log_msg lines wrapped in
iscsi-restore-luns; coding-policies gates clean (ruff check+format,
shellcheck -S warning over the documented file set); two-node.md
sever-vm-clone state-file row gains the pid field; docs integrity 23/23;
mkdocs --strict rc=0; full non-soak run 106 suites green (5721 passed,
0 failed, standing preflight skips only). Remaining Phase 6 halves (on
cue): commit/release/publish + production deploy and the reboot
exercise.

## 2026-10-28 — ITF recovery-scenario campaign, Phase G0 (lab foundation)

Approved plan executed (pub lane; campaign plan rev 3, plan dir file "ITF
Recovery-Scenario Campaign"). G0 code complete and green; verification
journeys in flight at note time:

- Keystore site-config pair (ITF_KEYSTORE_PASSPHRASE/ITF_KEYFILE_NAME,
  both-or-neither) in config-lib + config.example; real gitignored
  site/config got a generated random passphrase.
- Pool-recipe dedupe: itf_journey_stage_test_pools in common.sh; j01/j04/
  j05/j11 converted (j04 added beyond the plan's named three — same
  duplicated block). itf_single_node_lab_main behind j04/j11.
- VM-OS image: self-built minimal Debian via the existing preseed
  machinery (user steered off Alpine — its prebuilt images lack
  qemu-guest-agent, which would have forced a cloud-init bake pass).
  lib/vmos-lib.sh + `itf vmimage build|status`; dump is an audit-logged
  base-side dd of the stopped build guest's disk (pvesm path extended,
  itf-volumes only); build self-verifies by restoring onto a blank disk,
  booting it, and requiring qm guest ping. First live run wedged on the
  installer-time CPU freeze (--freeze 1 survives the install; every
  later start sits frozen) — fixed by clearing --freeze 0 before the
  verify boot; regression-pinned in the suite. Image is ~1G gz (Debian
  standard tasksel; slimmer if ever wanted).
- Agent-channel workload helpers (boot gate TCG, 1 Hz timestamp writer
  with per-tick sync on the LUN-backed root fs, sample/checksum via
  ast.literal_eval of qm's repr output, stall-gap parser), reboot stage
  (in-guest reboot rc-255 tolerated; --power variant; DHCP rediscovery
  rewrites guest-<role>.txt), LUKS keystore helpers (passphrase only
  ever via stdin key-file; production-verbatim fstab line; volid
  capture/re-attach), itf_journey_stage_encrypted_key_lun behind
  j05_two_node_lab_main --encrypted-keys (default off; j06/j07/j13/j14
  untouched).
- New suite tests/test-itf-lab-stages (in-process sourced stages with
  stubbed transports + DRY_RUN/dispatch checks); pvesm tests widened in
  test-itf-base-guard; keystore schema tests in test-itf-config.
- Docs: integrated-testing.md (site keys, vmimage, recovery-scenario lab
  layer section, framework-suite list), testing.md suite row,
  tests/integrated/README.md roadmap row 3.9, journeys/README.md lab
  layer, common.sh header. PREEXISTING.md stays empty in this lane.
- Pending at note time: second vmimage build (freeze fix) verifying;
  then j04 -> j05 plain -> j05 --encrypted-keys journey runs; full
  non-soak suite; final report. No commits (user cue only).

G0 outcome (final): all gates green. Verification runs — j04 12/0,
j05 plain 34/0 (campaign gate), j05 --encrypted-keys 46/0 (LUKS device
stdin-fed, encrypted vm-101-disk-1 through the product with the key
prompt answered over the compute->storage re-exec, registration
verified, locked-and-removed posture with keystatus available,
enc-lab-ready snapshot). Full non-soak suite green (107 suites, 0
failed, standing preflight skip). Product defect found and filed:
F-027 (new-vm-disk's encrypted-LUN registration matches the backstore
name prefix only; the installer-seeded site sample collides and
silently suppresses registration) + repair-plan 022 awaiting approval;
the lab stages a fresh-host empty conf around it. Three vmimage-build
live fixes along the way, all regression-pinned: installer CPU-freeze
survives the install (clear --freeze 0 before later starts), install
disk size must match the image size (--sysdisk plumbed through
stage_os), and the agent ping form is `qm agent <vmid> ping` (no
`qm guest ping` on PVE 9; VMID before command). VM-OS image cached
(879M gz; Debian standard install — heavier than the plan's "tens of
MB" Alpine sketch, fine at one-time cost; slimmer preseed possible if
ever wanted). Next phase: G1 (j15-iscsi-boot-keys).

G1 progress (j15-iscsi-boot-keys), first working session 2026-10-28:
detailed coding plan approved through plan mode (boot-verdict oracle
settled with the user first: assert the documented FAILED+DRIFT
semantics; the campaign's S1c "next boot OK" and S5 "verifier OK at
boot" wordings diverge from the code — nothing loads zvol keys at boot,
and export-iscsi-state has no encrypted-awareness — so those
divergences are FINDINGS, not journey failures; S1c re-pointed to
second-boot FAILED shape + within-boot convergence via manual --check;
S5 split into S5a (file:// still FAILED) + S5b (the legitimate boot OK:
all registered encrypted LUNs migrated to /root/keys keylocations + a
lab-authored itf-zfs-load-keys.service ordered Before the restore —
the drop-in's "separate key-loading unit" clause)). Implemented:
common.sh gained the G1 section (reboot stage split into
itf_reboot_guest_begin/wait with the outage window between; boot-workload
staging stage; key ceremony; boot-state capture + pure journal-order
parser; load-keys gated on keystatus because zfs load-key -a's exit
code is noisy about already-loaded keys — no passwordless sudo on the
dev host to pin the exact rc semantics empirically, so the helper gates
on the operator-visible outcome instead; keystatus; wrong-passphrase
unlock; new-vm-disk --encrypted runner; save/check gates; link-presence
pollers; fence tick; fallout sample; workload evidence). j15 journey
written (S1, S1c, S1b with --power for a deterministic outage window,
S2, S3, S4a+S4b via load-key -n (unload-key is impossible with live
backstores holding the zvols open), M4 via load-key -n -L (pool A's key
offered to pool B without touching any file), M1 three bad key paths
against a fresh VM 301, S5a, S5b, wrap). test-itf-lab-stages extended
(G1 block incl. journal-parser fixtures and the boot-workload staging
orchestration; the G0 power-path test's vacuous exact-shape guard
replaced with strict asserts and its step names updated for the
begin/wait split), test-itf-driver journey list gained j15, shellcheck
clean, affected suites green. Docs updated (integrated-testing.md
recovery-scenario section + framework-tests paragraph, journeys/README
lab layer + j15 row, tests/integrated README roadmap 3.9). Pending:
full suite, then the live journey run (detached + watch), FINDINGS rows
for the two doc-claim divergences plus whatever the run surfaces, final
report. No commits.

G1 outcome (final): GREEN — j15-iscsi-boot-keys 247 steps, 218 pass,
0 fail, 29 info (results/run-20261029-014746-j15-iscsi-boot-keys),
after 8 run/fix cycles (each --rerun replayed the lab from as-cloned,
~30-40 min to the first scenario gate). Product defect found + fixed
in-cycle: F-028 — the boot drop-in's post-restore verifier wrapper
swallowed the DRIFT detail because systemd expands % specifiers in Exec
lines and %s became /bin/bash (root's shell); the drop-in escaped $$
but not %%; fixed to printf "%%s\n" + comment (share/two-node/
rtslib-fb-targetctl-boot-config.conf), live-verified via unit restart
AND by the green S1 journal oracle (DRIFT lines now journalled under
FAILED). Only site: the one printf — no other unescaped % in shipped
Exec lines; 0.135.0 not yet deployed anywhere, so no production
exposure. Two G0 mock-fidelity bugs found by first live exercise:
qm guest exec payload key is "out-data" (parser read "out" — fixtures
invented the wrong shape; parser + fixtures fixed, wait-sample poll
added for the writer's first-append lag). Scenario truths learned and
asserted honestly: keys-absent boots always journal FAILED+DRIFT
(cycle idempotent, convergence within-boot via manual --check); the
encrypted-root VM "starts" on a stale device node and never boots (no
abort signal — F-030); sessions cling 24h behind PVE's patched
replacement timeout so the fence is blind to a total storage outage
(F-031); links re-login automatically after return but BOTH running
VMs (plain and encrypted root) need a stop/start — writers stay
stalled (F-032); restart-iscsi-services' Added lines land in the unit
journal (drop-in hook) not the script transcript — its own shape is
the "✓ configured" status block; S5b PROVED the boot-time OK:
itf-zfs-load-keys.service (After zfs-import*, Before restore) + all
registered encrypted LUNs migrated to file:///root/keys → Added lines
then post-restore verification OK (ordering prototype for a shipped
optional unit). Reboot stage gained a gone-first wait phase (in-guest
reboot races sshd shutdown); boot-state capture gained a bounded
verdict-wait (sshd can beat the ExecStartPost chain). FINDINGS filed:
F-029..F-032 (F-029 doc-claim pair incl. the S5b nuance; F-030..F-032
UX rows → REQUIREMENTS at G5). Docs corrected to the proven shapes
(integrated-testing.md j15 paragraph, journeys/README j15 row). Guests
of the green run left in place for inspection (zfstestvm1/8001
storage, zfstestvm2/8001 compute) — destroy with itf guest destroy
when done. Next phase: G2 (j16-iscsi-total-loss) on user cue.

## 2026-10-30 — ITF recovery-scenario campaign, Phase G2 (j16-iscsi-total-loss)

Approved plan executed (pub lane; campaign plan rev 3 + agent-made coding
plan; S18 oracle settled with the user first — Option 1, assert the
documented one-sided-pool tolerance; ruling recorded in the shared topic
file). G2 code complete and green: j16 164 pass / 0 fail / 27 info
(run-20261030-033206, after 14 run/fix cycles — each --rerun replays the
lab from as-cloned, ~30 min to the first scenario gate), j13 regression
green, j14 regression green, full suite green, mkdocs rebuilt (standing
nag only). Guests of the green runs destroyed; PREEXISTING.md unchanged
(empty — every find was in-scope).

- j16 scenarios (on the full j15 encrypted workload lab; keys stay
  loaded — no storage reboot in this journey): S6 all-mappings+
  backstores destroyed live (setup-iscsi-targets' VM-refs signature +
  declined reconcile offer, --check drifting on every LUN, map-driven
  rebuild of all 4 incl. encrypted, running-VM fallout: both writers
  REQUIRED stop/start — F-032's shape again); S9 the 3-of-33 incident
  shape (PVE start abort on the vanished link, safe-iscsi-save
  mapping-loss FATAL, --check naming the LUN, repair-iscsi-luns
  re-mapping at the recorded index); S7a targets-intact wipe →
  iscsi-restore-luns full restore incl. both ACL nodes + the staged
  non-identity mapped_lun 8→0; S7b targets-too wipe (clean initiator
  logout first — PVE's probes storm the shared wildcard portal — then
  restore-luns honestly refuses, setup rebuilds + saves (overwriting
  the records: the authority-gap FINDING), declined offer, map-driven
  reconcile, explicit re-login); S8 corrupt saveconfig (restart
  restores from boot config; .pre-start preserves the corrupt bytes;
  degraded-gate save refusal; force escape targetcli saveconfig heals;
  recover-encrypted refuses without saveconfig indexes — its indexes
  are saveconfig-read, not map-read; reconcile completes; verdict
  FAILED honestly recorded); S8b fallback branch fails loudly
  (Result=exit-code); S18a/S18b pool identity per the ruling
  (--check silent on the exported pool; GUID-change DRIFT + convergence
  through the operator-confirmed safe-iscsi-save).
- Product defects found + fixed in-cycle, all red-proven: F-033
  iscsi-lib query ssh without -n drained piped feeds (setup's reconcile
  offer died at read under set -e); F-035 reconcile's ACL grant loop
  collided with rtslib's auto-grant at node creation (presence-checked
  now; mock upgraded to real semantics); F-036 ALL saveconfig ACL
  readers used the wrong TPG key — real schema is node_acls (restore-
  luns's ACL restore, safe-iscsi-save's P1 grant gate, the boot-config
  ACL pruning were silent no-ops against every real file); fixtures
  moved to the real schema. F-027 (plan 022, user-approved mid-turn):
  new-vm-disk's encrypted-LUN registration now full-line matches
  name:device:target (same-name/different-device replaced with a WARN);
  remove-vm-disk mirrors it; extracted register_encrypted_lun/
  remove_encrypted_lun_entry per the suites' pattern.
- Filed open: F-034 (setup's portal step a structural no-op — the
  0.0.0.0 wildcard blocks every specific-portal add; WARN on healthy
  systems), F-037 (total-loss authority chain: setup's bare save
  destroys the saveconfig records; the map carries ACL names but no
  grant indexes), F-038 (UX: check-prerequisites --two-node green on a
  fully-unmapped target), F-039 (campaign-plan S18 wording vs the
  documented tolerance — user-owned file).
- Harness learnings pinned in the shared itf-harness-traps memory:
  targetcli ls dot-leaders/leading-space parsing, the acls-ls IQN
  rendering (a wipe loop must iterate node.conf-derived IQNs), the
  PVE-probe login storm vs sibling target deletions, the auto-grant
  and node_acls semantics.
- Docs: journeys/README j16 row, integrated README roadmap 3.9,
  integrated-testing.md j16 section, messages manual rows for the 022
  WARNs. test-itf-driver journey list +j16. No commits (user cue).
  Next phase: G3 (j17-iscsi-interrupted-ops) on user cue.

## 2026-10-30 — G3: j17-iscsi-interrupted-ops (campaign phase G3)

- User approved the G3 plan (same session). Scope: S10-S14 + M2/M3/M5
  on the composed j15 encrypted workload lab (keys stay loaded; VMs
  parked; service restarts only, never a storage reboot).
- j17-iscsi-interrupted-ops.journey written (shellcheck clean):
  SIGINT machinery via j12's generated-script pattern (setsid +
  transcript marker + kill -INT on the group), j16's IQN/inventory
  helpers copied journey-local, scenario order M5 -> S13 -> M2 -> M3 ->
  S11 -> S10 -> S14 -> S12 (victim dependencies; VM 304 created as the
  S13 config container — VM 301/303 belong to j15's scenario body and
  don't exist in a lab-only composition).
- Fixed during self-review before any run: two grep -vq misuses
  (inversion+quiet never proves absence), map_n arithmetic compare,
  wrap-block parameterization for S14's destroy-refused branch.
- Code facts the oracles rest on (verified in tree): reconcile's apply
  prompt accepts ONLY exact y/Y (M2 should pass as a safe-default
  proof); NO locking anywhere in reconcile/restore-luns/safe-iscsi-save
  (S12 = expected FINDING); export-iscsi-state --check compares
  topology not devices (S14's hand-destroyed zvol stays rc 0 silent
  while the backstore lives); reconcile skips+keeps deleted-zvol map
  entries (no removal planning exists) and its manifest regen silently
  drops the name; remove-vm-disk FATALs on a missing zvol (no cleanup
  path for the stale shape).
- Docs + framework: journeys/README j17 row, integrated-testing.md
  j17 section, roadmap 3.9 G3 sentence, test-itf-driver journey list
  +j17 (suite green). First journey run launching next; FINDINGS rows
  (F-040+: S12 serialization, S14 stale-entry trap) to be filed from
  live evidence per campaign discipline.
- Run/fix loop to green (4 fix cycles, all journey-side; no product
  code changed): run 1 exposed the SIGINT trap (non-interactive bash
  SURVIVES a group SIGINT — child dies, script continues rc 0; probe
  live-proven; j17_kill_run now uses kill -TERM per j12 precedent);
  run 2 green through S10, S14 recorded the REFUSAL branch (zfs
  destroy "dataset is busy" while LIO holds the zvol — the campaign's
  stale-live-LUN premise is structurally fenced), S12's converge
  assert was wrong (the race self-converged; re-run correctly a no-op
  — assert now accepts both shapes); run 3 all-green except the wrap
  (required saveconfig.json.pre-start, which exists only after a unit
  restart — this journey never restarts when S14 skips; wrap now
  requires the two save-written files and records .pre-start as
  info); run 4 GREEN 131 pass / 0 fail / 15 info
  (run-20261030-101505). Post-green honesty pass: journey summary
  text + journeys/README + integrated-testing.md S14 wording moved
  from the planned sweep to the live refusal outcome; final proving
  rerun launched to bind the green report to the exact file.
- FINDINGS filed from live evidence: F-040 (no serialization between
  concurrent reconcile/restore-luns: restore silently skips its
  collisions rc 0 while reconcile FATALs x5 AND installs a
  comment-only manifest via its ensured-only regen — the -s byte
  guard passes on comments — which its own save refuses; benign only
  when the sibling's trailing save heals it; reconcile's summary also
  prints plan-array counts, not apply successes) and F-041 (zfs
  destroy of a live-exported zvol refused "dataset is busy" —
  campaign S14 premise structurally fenced, wording fix awaits user
  direction like F-039). M3's type-to-confirm gap stays a step-text
  UX row (→ REQUIREMENTS at G5), consistent with F-032's treatment.
- Harness traps pinned in itf-harness-traps memory: the SIGINT
  survival law, the EBUSY fence, the S12 race shapes, the .pre-start
  only-after-unit-start trap.
- Full unit suite green at phase end (107 suites; itf suites
  sandboxed, ran beside the live journey). No version bump, no
  changelog, no commits (user cue).

## 2026-10-30 — G4: j18-compute-power-events (campaign phase G4)

- User approved the G4 plan (same session) with one oracle ruling
  gathered BEFORE planning (G1/G2 pattern): S16's post-return leg
  hard-gates only documented strings while storage is down (the
  ssh-255 WARN live), and post-return convergence is classified live
  rather than hard-gated — the campaign's "next-tick auto-recovery"
  expectation was doubted from code reading (correctly, though the
  live shape differed from both predictions).
- j18-compute-power-events.journey written (shellcheck clean):
  sources j15 (j17's composition pattern), identical staging, journey-
  local helpers only (target/inventory, storage-side :3260 session
  counter, workload prefix-cksum, fence boot-journal capture,
  show-lun-map total parser, race-tolerant compute reboot pair);
  S15 (two legs) -> S16 -> S17 (two variants) -> wrap. Registered in
  test-itf-driver's journey list; docs: journeys/README row,
  integrated-testing.md section, roadmap 3.9 G4 sentence (each updated
  repeatedly as live truths replaced predictions — the honesty-pass
  discipline held through the ladder).
- Run ladder, ten runs (every fix via --rerun replays from as-cloned):
  run 1 — the shared reboot gate's gone-phase FAILED a real compute
  reboot (a PVE guest stopping two TCG VMs outlasts the 180s window
  with sshd up while the storage-side window log proved the sessions
  collapsed to zero); fix = journey-local j18_reboot_compute
  begin/wait proving the reboot by boot_id change, ssh drop demoted
  to evidence. run 2 — S15b: --onboot 1 did NOT return VM 101; live
  journal shows pve-guests startall fired 2s after boot, failed on
  the by-path stat (links not yet back), finished OK, never retried
  (REQUIREMENTS row: onboot alone does not return running VMs
  unattended on iSCSI disks; the fence heals links, not starts); gate
  now asserts both live shapes with journal evidence. run 3 — S16's
  branch-B was mispredicted: sessions re-logged-in unaided (loginall
  found no node records — step text kept mechanism-neutral), plain
  LUNs back at 0s, and the return tick red exactly for the keys-
  pending encrypted LUN (reconcile skipping the encrypted zvols with
  the "keys not loaded?" hint, pool map preserved); per-class gates
  written. run 4 — F-042 (below). run 5 — show-lun-map's summary
  line rides log_msg STDERR (helper merged streams; the table is
  stdout). run 6 — my count arithmetic: the baseline already includes
  the scratch LUNs, so a VM deletion leaves the count unchanged.
  run 7 — F-043 (below). run 8 — ghost device datum: documented
  teardowns leave 0G device rows rescan-storage cannot drop (only a
  session re-login clears them; REQUIREMENTS row); gates reframed to
  the ghost shape. runs 9 and 10 GREEN — 191 steps, 161 pass, 0 fail,
  30 info (run-20261030-195020, then the honesty-pass proving rerun
  run-20261030-204426 after the wrap text was corrected; identical
  verdicts bind the green report to the exact final file).
- F-042 filed (open; repair-plan 023 PROPOSED, user adjudicates): the
  fence's post-return tick runs reconcile-iscsi-state while encrypted
  keys are pending; reconcile correctly skips the encrypted zvols and
  preserves the pool map, but its trailing safe-iscsi-save rewrites
  saveconfig.json from the encrypted-less live state — dropping the
  LUN indexes iscsi-recover-encrypted-luns reads ONLY from
  saveconfig.json, so the documented recover FATALs ("no recorded LUN
  index"; its conf-entry advice is unactionable — the conf has no
  index field). The indexes survive in the pool map (the declared
  recovery authority) and saveconfig.json.pre-start, neither
  consulted. j15 never hit this (compute up through storage reboots =
  clinging sessions = healthy tick = no reconcile). THE PENDING P6
  EXERCISE HAS THE SAME WINDOW (5-min fence cadence between storage
  return and key loading). The journey closes through the documented
  arc: a keys-loaded fence tick drives reconcile to rebuild both
  encrypted LUNs at the map-recorded indexes, then recover's re-run
  heals the ACL grants on its already-present path.
- F-043 filed and FIXED in-cycle: bin/repair-vm-disk-refs was
  committed mode 100644 (the only non-executable script in bin/) —
  deployed copies cannot execute (rc 126, live-proven on the lab's
  compute guest; the runbook's compute-restore Scenario B dead-ends on
  a stock deployment; production stewie/tweety carry the dead copy
  until the next deploy). Execute bit restored to match every sibling;
  test-repair-vm-disk-refs green; the rerun verified the deployed fix
  at the dry-run gate.
- REQUIREMENTS-class step-text rows queued for the G5 register: the
  PVE autostart race never retried; ghost 0G device rows after
  teardowns; the S15 operator-restart classification.
- Zero product behavior changes (the F-043 fix is mode-only);
  test-itf-driver + test-repair-vm-disk-refs suites green during
  iteration; full unit suite green at phase end (itf suites
  sandboxed, run beside the live proving run).
- All run guests destroyed post-green (bases hold only the
  templates). No version bump, no changelog, no commits (user cue).
  Uncommitted tail on 4c61e08: the journey, the driver list, the
  three docs surfaces, FINDINGS F-042/F-043, repair-plan 023, and the
  repair-vm-disk-refs mode fix.

## 2026-10-30 — Repair plan 023 executed: recover-encrypted-luns map fallback (F-042)

- Executed the user-approved repair plan 023 verbatim (no plan edits).
  `bin/iscsi-recover-encrypted-luns` now resolves each encrypted LUN's
  index from the newest pool state map when saveconfig.json is silent —
  same IQN scoping law as the saveconfig lookup, so orphan targets under
  a different prefix still cannot influence the slot. New pieces:
  `lookup_lun_number_in_map` (reads `targets.<iqn>.luns`), a
  `resolve_lun_number` resolver used by BOTH the recovery path and the
  already-present grant-heal path, and a once-per-run map resolution via
  `newest_iscsi_state_map` (the same locator reconcile uses). A map
  generated on another host is ignored with a WARN (reconcile's
  site-identity rule). The no-index FATAL was reworded to point at the
  map + the `.pre-start` boot backup instead of the unactionable
  "fix the conf entry" advice; the never-guess refusal stands verbatim
  when neither authority records an index.
- Latent defect fixed in the same lines (found during implementation):
  `lun_num=$(lookup_lun_number ...)` under `set -e` could abort the
  whole script silently on an unparseable saveconfig (python traceback
  swallowed by `2>/dev/null`, rc 1 propagating through the assignment).
  Both lookup call sites now carry `|| lun_num=""`, so a corrupt
  saveconfig degrades to the honest per-entry FATAL instead of a silent
  mid-loop abort.
- Unit suite: 4 new tests (map-hit recovery at recorded indexes with the
  INFO naming the map source, map-miss refusal with the reworded FATAL,
  foreign-host map ignored, already-present grant heal at the
  map-recorded index). Red-proven first (exactly the 4 failed on the
  pre-fix script, 8 old tests still green), then 12/12 green after the
  fix. Runner gained zfs/zpool mocks feeding a pool-map fixture and
  stderr capture (LOG block) for the message-text assertions.
- Journey gates flipped to the healed path: j18 S16's "recover dead-ends
  after a keys-pending fence save" gate now asserts the direct
  map-fallback recovery (both LUNs mapped, Recovery complete, no FATAL),
  the keys-loaded tick gate renamed to the convergence proof, header
  bullet + summary updated. j16 S8's "recover honestly refuses" gate
  (same map-populated scenario shape — the corrupt-authority heal)
  flipped to assert the map-fallback rebuild at LUNs 1 and 3, and its
  follow-on reconcile step now asserts the no-drift agreement ("No
  target-side changes needed"); S8b keeps reconcile's own map-driven
  rebuild coverage. j15 unaffected (saveconfig intact in its arcs — the
  ceremony helper asserts rc only). Both journeys parse via
  `itf journey list`.
- FINDINGS F-042 closed "accepted" per the plan's wording, with the
  execution record and a link to repair-plan 023 (whose status header
  now records the execution). Journey rerun (j16/j18 via dev tarball)
  still pending — that's the row's honest tail.
- Docs updated: two-node.md recover section (fallback step + pool-map
  row in data structures + iscsi-lib purpose), messages/index.md
  (reworded FATAL row + new fallback INFO + foreign-map WARN rows),
  proxmox-integration.md (recovery narrative + manual-equivalent step 3),
  data-structures.md (recover named as a map consumer),
  integrated-testing.md (j18 F-042 paragraph).
- Affected suites green in iteration (recover, strict-mode,
  itf-lab-stages); full suite green once at phase end. PREEXISTING.md:
  0 entries before, 0 after (the one latent defect found was fixed
  in-cycle in the touched lines). No version bump, no changelog, no
  commit (user cue).

## 2026-10-31 — G5: coverage map + requirements register + campaign wrap

Phase plan approved rev 2 (one revision round: j13/j14-vs-024 disclosure
reworded, 025 ordering law, 026 blast radius + S18 tolerance invariant,
024 refusal WARN names the sibling, F-042-window end-user headline).
Pre-plan adjudications: journey set j16+j18+j15+j07 (+j17 via F-040);
F-040 draft+execute in-phase; F-034/F-037 promote to proposals.

- Repair-plan 024 (F-040 concurrent LIO mutators) DRAFTED + EXECUTED:
  `zfslock_acquire_lio_mutator` added to bin/zfslockmanager (global
  slash-free `iscsi-lio` key → flat lock, never remote-forwarded;
  refuse-never-wait; holder named pid+script+since via
  _zfslock_read_field; lock-manager error = fail closed); reconcile
  acquires post-prompt → releases post-rescan (EXIT trap backstop);
  restore-luns acquires post-saveconfig-check → releases post-rescan.
  Sub-defects: regenerate_manifest_from_map counts ok_names (failed
  applies skipped first) — zero names keeps the previous manifest (WARN
  "no ensured backstores survived apply"); summary now "N of M planned"
  per dimension (apply-truthful). Unit tests red-proven (4 fail pre-fix)
  → green: reconcile 29/29, restore 6/6, zfslock suites green,
  shellcheck clean. GOTCHA pinned: the restore-luns runner heredoc — a
  bare `$1` in my source_helper override collapsed to "" at write time
  (the suite's unquoted RUNNEREOF); escaped `\$1` fixes it (the
  itf-harness heredoc-escape trap, now hit in a unit suite too).
- j17 S12 gates flipped to the fence oracle (either winner; loser rc 1
  with the sibling named, zero mutations); header + journeys/README row
  + integrated-testing.md j17 paragraph updated; concurrency-collisions
  gained a "Recently resolved (LIO mutator fence)" section;
  messages/index.md rows added (both scripts' refusal WARN/FATAL, regen
  guard wording, apply-truthful summary); two-node.md flow/safety notes
  on both mutators.
- tests/integrated/REQUIREMENTS.md created (R-01..R-09 seeded; status
  values; maintenance rules). developer-guide/itf-coverage.md created +
  mkdocs nav (ITF Coverage Map); gap rows two (two-node interrupted
  upgrade w/ keys pending; uninstall/reinstall w/ live LUNs), parked
  rows (GUI automation, OS matrix) + the closed 17-command exclusion.
- Repair plans 025 (portal binding: create-then-replace at
  target-creation only, ordering law from F-024: add specific BEFORE
  removing wildcard, never portal-less mid-flight) and 026 (map grants
  dimension: acls gain mapped_lun→tpg_lun pairs; map-fixture suites +
  data-structures.md in blast radius; one-sided-pools tolerance
  explicitly untouched) — both PROPOSED only, execution awaits user
  approval.
- Docs clarifications: boot drop-in comment (loadedness vs file://
  availability; the one legitimate loader = a key-loading unit ordered
  before the restore), zfs-keys.md Requirements note ("Available is not
  loaded"), two-node.md runbook gained "Power events — what returns
  unaided and what needs you" (stop/start after storage outage; fence
  blind to total outage; onboot race never retries; ghost 0-GiB rows).
- integrated-testing.md: findings section gained the terminal-states
  rule + a Requirements-register section pointing at the coverage map.
- Journeys (fresh runs — bases held only templates, no --rerun
  possible): j17 LAUNCHED (run-20261030-232609) to verify 024's S12
  fence live; queue: j16 (plan-023 gates + 024 regression), j18
  (plan-023 gates; F-043 verified status), j15 (final-tree record), j07
  (regression). Not rerun (disclosed in the phase plan): j13/j14
  (single-mutator shapes; 024's uncontended lock changes nothing;
  reconcile re-proven by j16/j17), j01–j06/j08–j12 (paths untouched;
  j05 lab flow proven current via composition).
- Pending at this note: FINDINGS triage rows (after greens), README
  roadmap 3.9 → complete + layout row, mkdocs build, full suite once,
  PREEXISTING re-read, final report with the F-042-window headline
  (plan 023 in the next deploy closes the fence-tick window; the P6
  exercise's post-boot recovery runs clean end-to-end).

### G5 addendum — j16 fix loop (fence-timer race + resource lesson)

- j16 fresh run 1 died at P2P first-connect (publickey denied) and rerun
  2 at install-two-node's BatchMode ssh check — both storage→compute ssh
  over the P2P link. ROOT CAUSE (partial): I had left j17's green-run
  guests (8001 pair) running while j16 cloned its own pair — 32 GB of
  guests across the two bases; destroying the 8001 pair fixed the ssh
  flakiness. STANDING RULE (already G2/G4 practice, now re-earned):
  destroy each journey's guests as soon as its run is green, BEFORE the
  next journey's fresh clone.
- Runs 3 and 4 then failed REPRODUCIBLY at j16 S7b ("setup rebuilds +
  offers reconcile"): the compute guest's always-on 5-min fence timer
  (check-vm-disk-paths --recover) can land INSIDE the scenario's
  operator-paced window (wipe → restore-refusal → setup's detection) —
  its ssh reconcile heals the LUN tree before setup's detector runs, so
  "No post-restore signature found" and the offer never appears. Proven
  live: a tick during the investigation rebuilt all 4 LUNs + 2 ACLs
  unattended (with 024's new "N of M planned" counts in its journal
  output). The G2-era runs never collided — timing luck. JOURNEY FIX
  (scenario hygiene, harness-side): j16 parks the fence timer
  (systemctl stop …timer, INFO step) before S6 and restarts + asserts it
  before the final tick gate; the unattended heal itself stays j14/j18
  coverage. Fix-loop run 5 GREEN: run-20261031-031917 (165/0/28) with
  the plan-023 flipped S8 gate ("recover rebuilds from the map when
  saveconfig is silent" + "reconcile agrees") passing live.
- All j16-run guests destroyed post-green (both pairs).

### G5 final — journey ladder + gates (2026-10-31)

- j18 fix loop: first rerun failed at "recover re-run" — a TRANSIENT
  luns-ls false negative made recover FATAL against its own mapping
  ("another backstore may hold that index" while the tree was intact;
  proven live). Fixed in-cycle: on a refused LUN create, recover
  re-queries by name (F-044; red-proven by temporary revert, suite
  13/13; mock gained one-shot transient-listing + real index-collision
  refusal). Also parked j18's ceremony-window fence timer (same race
  class as j16: an ambient tick with keys loaded pre-mapped vm-202-disk-0
  under recover's own run). Rerun GREEN: run-20261031-065358 (162/0/30).
- j15 GREEN first try: run-20261031-082313 (218/0/28) — the final-tree
  record. j07 GREEN: run-20261031-095651 (45/0/4). Every journey's
  guests destroyed post-green; bases clean.
- FINDINGS: F-042 rerun-verified (both run ids recorded), F-043 verified,
  F-044 filed + fixed in-cycle + verified; every row F-001..F-044 now in
  a terminal state; guidelines carry the disposition rule. REQUIREMENTS
  register R-01..R-09; repair plans 025/026 PROPOSED (await user
  approval); roadmap 3.9 → complete (G5 recorded).
- Gates: shellcheck clean (7 touched scripts + 3 journeys); docs site
  builds clean; FULL SUITE: 107 suites — all bash suites green; the
  python suite carries 3 test failures OUT of G5's blast radius (2×
  alignment geometry, 1× e2e backup-prune checkagainst prompt) —
  isolation-stable, no G5 change touches python/payload code, suite was
  green at d127c79 yesterday; both recorded in PREEXISTING.md (2 entries
  remain). Disclosed in the G5 report.
- Headline numbers: 27 files — 22 modified (698 insertions / 68
  deletions) + 5 new (354 lines): ~1,052 insertions total. No version
  bump, no changelog, no commit (user cue). P6 next, on cue.

### Development-cycle wrap-up (2026-10-31, frozen)

- Step 1 — both PREEXISTING entries resolved, file now empty of entries:
  - e2e backup-prune: root cause was NOT a stray dataset — the host
    GUI config (v31, newer than this tree's v30) had auto-DERIVED
    checkagainst rows mapping dailybackup zfstest1↔zfstest2/zfstest1,
    so the removal gate correctly stopped prompting. Structural fix:
    the e2e pytest front ends now run payloads hermetically —
    `pin_payload_env()` in e2e_support pins `ZFSCONFIG_PATH` at a
    harness-owned fixture (test pools + DEFAULT_RETENTION + no
    checkagainst rows; legacy fallback only names production pools)
    and `ZFSUTILITIES_RUN_NEXTSNAP_PREFIX` at a per-test dir. The
    second pin fixed a sibling failure the first full-module rerun
    exposed: a leftover /run nextsnap file made orch-zfssend hang on a
    second prompt. Both modules 24/24 under sudo; module runtime
    6:48 → 1:54 (watchdog stalls gone). Guest driver (j11) untouched —
    runs unpytested, guest fresh-install config already satisfies the
    premise.
  - alignment: proven leak — GDK_DPI_SCALE=2 reproduced the G5 failure
    class through the "private" Xvfb (GTK font metrics arrive via env
    + the ambient session bus, which Xvfb does not fence). Fix:
    `_scrub_ambient_gtk_environment()` in alignment_realized_check.py
    drops GDK_SCALE/GDK_DPI_SCALE/GTK_THEME/GTK_MODULES/DBUS_*/XDG_RUNTIME_DIR
    before Gtk binds. Hostile-env run now passes.
- Step 2 — ruff check + documented shellcheck command both clean; ruff
  format fixed one file. Line-length sweep: wrapped all token-splittable
  and double-quoted-token overages (bin/, lib/, journeys j17/j18, six
  test suites); message texts byte-identical (log_msg joins args).
  Deliberately left >100: single-quoted printf formats (JSON/golden),
  heredoc journal fixtures, embedded ssh/awk payload strings in
  journeys/common.sh — unwrappable without changing bytes.
- Step 3 — added direct fence-API unit tests (test-zfslockmanager:
  acquire/free-tree, refusal naming holder, empty-name rc=2; uses
  clear/get_test_log_file idioms) and an alignment hostile-env
  regression test (GDK_DPI_SCALE=2 must not change the verdict). All
  seven wrap-affected suites rerun green.
- Steps 5-6 — testing.md documents the hermetic payload env; docs
  integrity 23/23; site rebuilt. FULL SUITE (user, no soaks): 107
  bash suites + python 4227 passed / 0 failed (18 root-tier e2e skips
  are by design; that tier verified 24/24 under sudo earlier in the
  session). NOTE: `sudo tests/run-tests` cannot launch the python leg
  (root's python lacks pytest-xdist → `-n` rejected); the canonical
  gate runs as the user — run the sudo e2e leg separately.
- Step 7 — tree FROZEN here: 33 modified + 5 untracked files, no
  commit/version/changelog (user cue, per Hard Rules).

## 2026-10-30 — Add Profile to Schedule mirrors the red Save state

- Backup, Offsite, Restore, Retention: the "Add Profile to Schedule"
  toolbar button now turns red exactly when the page's Save button is
  red, and clears with it on save/revert/page switch.
- Mechanism: PAGE_SPECS gives the four buttons attr names
  (`_backup/_offsite/_restore/_ret_add_profile_btn`); `DirtyTracker`
  grew an optional `mirror_button_attr` (backup + offsite);
  restore's `_style_restore_save_button` styles both buttons (unified
  on `set_button_markup_red` — behavior-identical, hard-coded label
  markup dropped); retention gained `_style_retention_buttons` shared
  by `_update_ret_status` and `retention_actions.check_retention_dirty`.
  Pools page untouched (not requested).
- Test gotchas hit: retention fixtures that null `_ret_save_button`
  to dodge styling under MagicMock must also null
  `_ret_add_profile_btn` (MagicMock auto-creates the attr and the real
  `set_button_markup_red` dies on `isinstance` vs mock `Gtk.Label`);
  mock call_args_list comparisons need the real `call` object (aliased
  `mock_call` — plain tuples do not equal `_Call` entries, and a bare
  `call` import trips F402 against pre-existing loops named `call`).
- Docs: the four Add Profile rows in gtk-gui.md note the red
  mirroring (row widths preserved; docs-integrity green).

## 2026-10-30 (later) — Dashboard Tasks Date / Time header tooltip

- The Tasks "Date / Time" column header now has a tooltip (header-label
  pattern from logs_page/disks_page): waiting/running rows show the task
  start time, completed rows show the completion time. gtk-gui.md's
  Tasks column row already documented these semantics, so no doc edit.

## 2026-10-30 (later still) — zfshold already-present notice at VERB

- bin/zfshold: the "Hold <tag> already present on <snap>" notice moved
  from INFO to VERB (routine duplicate chatter on multi-dataset runs;
  GUI log viewers hide it at normal levels). test-zfshold's
  already-present case asserts VERB + no INFO now; messages/index.md
  row and the modules.md zfshold paragraph updated to VERB. The
  changelog's historical "logged at INFO" line stays (off-limits).

## 2026-10-30 (evening) — Restore: no parts checkboxes, state-aware resume of interrupted restores

- Restore page: Restore Steps (Part 1/Part 2 checkboxes) and Notes
  sections removed; every restore runs both phases. do_part1/do_part2
  dropped from the schema (migration 30→31 pops them); old scheduled
  restore profiles carrying the keys still run (ignored, tested).
- Interrupted restores now RESUME instead of restarting from scratch
  (user rejected the destroy-and-redo design):
  - The engine already honored receive resume tokens on every
    send-receive pass (validate via `zfs send -nP -t`, resume with
    `zfs send -t | zfs receive`, abort stale with `receive -A`, then
    reprocess the same dataset via `((i--))`) — no new code needed
    there.
  - New: `restore_resume='Y'` gate in zfs-send-receive — in a
    destructive full-copy pass (force='Y', doincrementals='N'), a
    plain-mode getcommonsnap GUID check skips datasets whose
    destination already holds a verified lineage; Part 2 catches them
    up incrementally. Normal backups (no flag) keep destroy semantics
    (red-proofed). The gate must neutralize commsnap_mostrecent='OLDEST'
    around the call or getcommonsnap short-circuits without comparing.
- Payload: always Part 1 → fsarray file → Part 2 → iSCSI ensure;
  restore_resume='Y' set; fsarray temp file now guarded by
  append_exit_trap + `trap 'exit 143' TERM` (GUI cancel = SIGTERM;
  handler runs after the current zfs pipeline ends — same visible
  behavior, but the exit traps then fire). Residual: SIGKILL can still
  leak one /tmp/zfsrestore_fsarray_<pid> (harmless; unique per run).
- New bash suite test-zfs-send-receive-resume (7 tests, red-proofed by
  disabling the gate). test-lib mock upgrades: stale-token list for
  `zfs send -t`, and receive completion consumes the token — via a
  state-dir FILE because pipelined receives run the mock in a subshell
  where array writes vanish (the original hang); suites staging tokens
  must clear received-datasets in their reset.
- Run Restore dialog always WARNING now, with resume-behavior text.
  Docs: gtk-gui.md (phases + Interrupted restores bullets, Run Restore
  row), restore.md "Interrupted Restores" section, messages manual
  (dropped the at-least-one-part WARN row; lineage-skip rows),
  modules.md + global-variables.md (restore_resume), testing.md row.
  mkdocs --strict clean (standing mkdocs-2.0 warning only).

## 2026-10-30 (night) — red action buttons turn their sidebar tab red

- Any page whose action button is red now shows its sidebar tab label in
  red: Backup/Offsite/Restore/Schedule/Retention/Pools Save (+ the Add
  Profile mirrors), and Checkagainst's Save AND Get Entries (causes OR-ed
  per page). Dry Run toggle deliberately excluded — its state is shared
  across four pages, so it would light four tabs for a mode, not an
  attention state.
- Gtk.StackSidebar doesn't expose row labels, so the sidebar is now a
  custom Gtk.ListBox (rows hold our labels; activation switches the
  stack; on_page_changed selects the row — select_row doesn't re-emit
  activate). New gui_helpers.PageAttention (per-page cause OR) +
  set_page_tab_attention bridge; window.set_page_attention applies the
  markup. DirtyTracker grew page_name= (backup/offsite trackers pass it);
  each other page's existing styling choke point calls the bridge.
- PREEXISTING.md: the cross-file pytest-ordering flake entry gained a
  second instance — `pytest test_restore_page.py test_checkagainst_page.py`
  (restore first) fails 4 checkagainst dialog assertions; verified
  identical with ALL FOUR files at clean HEAD, so pre-existing (alphabetical
  runs and the sanctioned per-suite runner never pair them this way).
  Discovered while batching suites in one process; entries remain 3.

## 2026-10-30 — Desktop + email run-completion notifications (pub3)

- New feature, approved plan: per-channel (desktop/email) Off/Failures/All
  modes plus per-run-type toggles (backup, offsite, restore, retention,
  scrub, dataset; GUI "prune" maps to retention).
- python/notifications.py: gating + delivery; notify_run_finished() hooked
  at profile_runner.main() (completed, missing-profile, cancelled-lock-wait,
  unhandled-exception paths; skip exits silent) and BackupRunner
  _finish()/cancel() (covers all five GUI runners).
- Delivery facts verified live: notify-send missing on stewie/tweety;
  dbus-send cannot express a{sv} (plan said dbus-send fallback — replaced
  with gdbus, verified working on dev host; both prod hosts have gdbus +
  Cinnamon session buses). Local MTA on 127.0.0.1:25 both hosts; email uses
  user-configured SMTP via smtplib instead (plan as approved).
- GUI-thread safety: delivery runs on a daemon thread from the GUI main
  thread; log lines hop back via GLib.idle_add (guarded by a thread-local
  so non-GUI contexts log directly). GLib loaded dynamically so the module
  stays out of the GUI-module closure (scanner initially misclassified it).
- File → Notifications… dialog (notifications_dialog.py): modes, toggles,
  SMTP fields, masked password (0600 /etc/zfsutilities/smtp-credentials.json,
  empty removes the file), test buttons test unsaved dialog values.
- Tests: new test_notifications.py + test_notifications_dialog.py; extended
  test_feature_config/test_profile_runner/test_backup_runner/test_gui_helpers;
  requirements.manifest gained the dialog suite. Docs: python-modules,
  messages manual (new rows), data-structures (notifications object),
  gtk-gui (menu + dialog section), profiles (notifications section).

## 2026-10-30 — Development cycle wrap-up (pub3 lane)

- Steps 1/4 (resolve PREEXISTING.md) skipped by their own precondition:
  pub-main-only; this lane's PREEXISTING.md unchanged at 3 entries.
- Step 2 code review vs coding-policies.md: clean. ruff check whole-repo
  green; ruff format green on every changed/new Python file. No bash
  changes in the cycle (shellcheck N/A). Verified no double-fire risk:
  profile runs launch profile_runner.py as a subprocess, BackupRunner
  serves interactive GUI tabs only — hook sites disjoint.
- Step 3 test review: no obsolete/incorrect tests found; 8 missing tests
  added — TestAsyncDelivery (daemon-thread delivery, idle_add log hop,
  thread-local gating, _on_gui_main_thread guards), email timeout env
  knob, profile_runner lock-wait-cancel + unhandled-exception hook paths,
  dialog password-visibility toggle. Affected suites green after one
  ruff-format fixup.
- Step 5 docs: all diffs verified against code (config keys, credentials
  path /etc/zfsutilities/smtp-credentials.json via get_config_dir, message
  rows match strings, env knobs documented). No updates needed; no user
  hand-edits found to preserve beyond the feature's own additions. Docs
  integrity suite green; site/ rebuilt via mkdocs build from docs/ (the
  MkDocs 1.x unmaintained banner is the known standing stance).
- Step 6 full run without soaks: ALL SUITES PASSED, no failures; skips are
  environment preflight only (e2e suites needing root + zfstest pools).
  Cleared no stale /tmp/sever-vm-clone state beforehand (none present).
  No new PREEXISTING entries.
- Step 7: codebase FROZEN at this point. No further changes before the
  user-directed commit/publish.

## 2026-10-30 — Release 0.136.0 prep (pub3 lane, user-directed)

- Step 8: VERSION 0.136.0 + changelog section (user explicitly directed
  both). Docs integrity green after the edits.
- Final gate: tests/run-tests --with-soak — ALL SUITES PASSED, zero
  failures, zero bash skips; python skips are environment preflight only
  (e2e needing root + zfstest pools). test-zfslockmanager-soak ran and
  passed. No fixes were needed; /tmp had no stale sever-vm-clone state.
- Steps 9-10: no further code changes; stage + commit of the whole cycle
  (notifications feature + wrap-up test additions + release files)
  performed under the user's explicit step-10 instruction.


