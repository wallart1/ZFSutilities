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
