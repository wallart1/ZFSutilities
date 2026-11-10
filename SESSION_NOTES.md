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

(2026-10-31 release prune: the 0.134.0–0.136.0 releases — pub's
enclosure P4/P5 GUI, the iSCSI boot-incident hardening (0.135.0), the ITF
recovery campaign G0–G5 with repair plans 022–024, pub2's shadowed-mount
fence/cancel/mount-order work and 0.136.0's restore resume + Logs
Miscellaneous list + sidebar tab-red, pub3's Datasets Show Details work
and 0.136.0's notifications, and both lane-merge turn records — are
committed, pushed to origin main (0111e0f..55d4c3d), and released as
v0.136.0 (0.134.0/0.135.0 shipped untagged inside the same push); those
entries were removed, recoverable via `git log`.)

(2026-11-02 release prune: the 0.137.0 combined release — pub's
storage-IP portal binding and state-map ACL grants dimension (repair
plans 025/026) with the CI TTL-cache follow-ons, pub2's
config-downgrade safety, natural table sizing, oldest-snapshots
section, and j19 journey, pub3's tooltips campaign, offsite-pool
exemption, idempotent unmount, root-cache redirect, and input-prompt
tint, the second wrap-up (name-based fence ownership, offsite identity
exemption, SIGTERM budget), and both lane merges — is committed
(0f02c90..8cf365f), pushed to origin main, tagged v0.137.0, and
released; those entries were removed, recoverable via `git log`. The
Zensical-evaluation thread was retired by the 2026-10-26
no-upstream-watching decision and removed.)

(2026-11-03 campaign prune: the backup property fidelity campaign,
phases P0–P6, is committed — 8cf365f for the base, then 1c06aea,
6507911, 53f50aa, 7f3f81e, e623395, 0389018 — and its design and
behavior live in docs/ (restore.md, offsite-backup.md, daily-backup.md,
gtk-gui.md, global-variables.md, modules.md, python-modules.md,
commands.md, messages, itf-coverage.md). The per-phase entries were
condensed into the campaign summary below; full detail is recoverable
via git log.)
(2026-11-03 release prune: the 0.138.0 combined release — pub's backup
property fidelity campaign P0-P7 with journeys j20/j21 and the F-045/F-046
finds+fixes, the merged-tree wrap-up, pub2's guest-agent probe fix,
batched SSH probes, mount-refusal visibility, Survey preload, and
hold-reapply idempotence, pub3's rolling charts, required matplotlib,
zero-rate refusal, and R-08's encrypted-aware boot verdict (repair plan
027), and both lane merges — is committed (bd4f2b3..5586740), pushed to
origin main, tagged v0.138.0, and released; the cycle entries and both
lanes' history blocks were removed, recoverable via `git log`.)

(2026-11-05 release prune: the 0.139.0 release — the j22 function
survey (journey + survey/ engine + both test suites, proven green in
all three modes: fresh draw, --rerun list replay, release mode against
v0.138.0), the ITF verdict-time guest teardown + `itf guest sweep`,
the j05 same-IP staging collision convergence, the zfsaddisk argument
validation, the j06/j07/j14 four-field record reads, the template
leftover-clean run-tag match, the two post-0.138.0 CI commits
(a8263d2/f1b5495), the wrap-up review pass, and the docs/glossary
updates — is committed in the 0.139.0 release commit on pub main;
push/tag/release follow at the owner's cue. Design and behavior live
in docs/ (integrated-testing.md, journeys/README, commands.md,
coding-policies.md) and GLOSSARY.md. F-047 (cairo missing from the
gui prereq set) remains the open product finding in FINDINGS.md,
awaiting a repair-plan decision. The cycle entries were removed,
recoverable via `git log`.)

## Persistent gotchas (not documented in docs/)

- Guest-agent probe: invalid ping argv was the root cause (2026-11-02):
  the Blocksize Alignment note's uniform "guest agent unavailable" came
  from the prober sending `qm guest ping <vmid>` — PVE 9's `qm guest`
  map has only cmd/passwd/exec/exec-status, so EVERY ping died at CLI
  usage-parse (usage text contains "guest", which the old substring
  classifier collapsed to one label) regardless of VM state; no exec
  ever ran and PVE's agent machinery was never invoked (zero
  Monitor.pm syslog failures all day confirmed it). Fixed to the
  canonical `qm guest cmd <vmid> ping` (the `qm agent <vmid> ping`
  alias is upstream-deprecated; ITF's vmos-lib uses the alias and HAD
  live-verified "no qm guest ping on PVE 9" — the knowledge never
  reached the product). Complementary hardening from the same day:
  classify_agent_failure now matches PVE's die strings specific-first
  (not-configured / not-running / VM-not-running /
  agent-error-with-description), GuestFsProber._run WARN-logs the raw
  stderr, and validate-guestfs-probe's self-check dispatch pins the
  EXACT ping argv (a substring match is what blessed the invented form
  — mock-fidelity lesson: scripted runners must assert wire shapes, not
  keywords). Fact source: tweety's /etc/pve guest configs are now
  dan-readable via a root-side systemd mirror (/var/local/
  pve-guest-configs, pve-guest-config-mirror.{service,path,timer};
  pmxcfs permissions are FIXED by design — chmod EPERM even as root,
  and www-data group membership would expose pve-www.key/user.cfg/
  pve-ssl.key — documented in the Installation manual; ALL 12 real VMs
  have `agent: 1`, only 999.conf lacks it). Other tweety facts: VMs
  launch as `/usr/bin/kvm` (a `qemu-system` ps grep finds NOTHING —
  grep `kvm -id` instead); failed qga/qmp commands are syslog'd by
  Monitor.pm — "journalctl | grep 'command failed'" is the agent
  observability channel. The recorded-but-unused `VMOption.agent` flag
  (alignment_stats parses the config switch; nothing consumes it) is an
  acknowledged gap, left unwired per plan scope. Evening re-check on the
  user's screenshot report (0.134-era image): BOTH nodes now run 0.137.0
  (current symlink switched Nov 1 22:20) and 0.137.0 still carries the
  broken argv — the fix ships only with the next release; all 12 tweety
  VM configs read `agent: 1` via the dan-readable mirror.

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

- MagicMock dialog suites vs refresh_*_page sections (2026-10-26
  enclosure work): anything refreshed from a refresh_*_page helper must
  tuple-guard its selection reads (see disks_page._repopulate_enclosures)
  — four dialog suites drive refresh_disks_page with MagicMock apps
  whose selections answer non-tuples, and an unguarded unpack takes them
  all down.

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
- Realized-geometry bounds are PIXEL-domain (2026-11-02, CI red on the
  published v0.137.0 while the dev host stayed green): the natural-table
  slack over the rows is a stable ~50-54 px block; in row units it reads
  ~2.57 rows at the dev host's 21 px fonts and ~2.63 at CI's theme-less
  19 px fonts, and the released rows+2.6 bound sat between them.
  `assert_twenty_rows` short/empty branch now bounds `height <= header +
  rows*row_h + 60`; derive geometry tolerances from the implementation's
  pixel constants, never one host's row height.

## Active / parked threads

- **Alignment guest-probe exec decode + note rewrite (2026-11-09,
  pub3, uncommitted).** The 0.138.0 ping-argv fix worked (pings answer,
  stopped VMs classify), but `_decode_exec` read an invented `out` key —
  PVE 9 prints guest stdout under `out-data` (verified against tweety's
  installed QemuServer/Agent.pm, pve-manager 9.2.11), so every running
  VM's exec "succeeded" into "unexpected qm output" and the availability
  note enumerated 21 volumes in a run-on (user screenshot
  2026-11-08 10-08-25, lives UNTRACKED at pub repo root — remove when
  the fix ships). Fixed: decode reads `out-data`; rc=0-but-unparseable
  exec output now WARN-logs the raw first line (the reason string alone
  hid this for a release); the note counts per reason + points to the
  VM rows (rows already carried each volume's reason via
  `guest fs unprobed:`); test `_qm_exec` fixture and the validator
  self-check runner now emit the real wire shape (mock-fidelity: same
  trap class as the ping argv, third occurrence — fixture, unit test,
  and validator all agreed on the invented shape). Live proof needs a
  node deploy (user-cued). Guest-probe future work below still open.

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

- **Backup bottom-edge tooltip flicker (2026-11-02, parked on user
  report, unreproduced app-side):** the widget-anchored FLIP_Y placement
  is verified stable (borderline sweep included), so the working theory
  is a client-side compositing artifact. If it recurs: a realized-window
  probe of the running instance with the user's explicit go-ahead, or a
  set-text-once query-tooltip handler as churn mitigation.
- **remove-vm-disk/detach-vm-disk map-keyed refactor — parked (2026-11-04,
  user cue).** Both commands carry their own copy of the LUN + backstore +
  manifest + encrypted-conf teardown and derive the backstore from the
  vm-<id>-disk-<n> name convention instead of the live LUN map and the
  backstore's device. The busy-resolver campaign's resolver is map-keyed
  (VM config target+LUN → LUN map → backstore → device) and shares the
  extracted `iscsi_unplug_export`; folding both commands onto the same
  helpers awaits the user's cue. Behavior of both commands is unchanged
  until then.

## 2026-11-09 (later) — j23 two-node release-upgrade journey (user-cued ITF gap)

- The user named the itf-coverage.md gap row "two-node release upgrade
  (remote-target surface)" — naming is the map's build trigger. Built
  j23-two-node-release-upgrade.journey: composes the j05 lab, stages
  old-active on BOTH hosts (template's old tree rsynced to compute +
  switch-version both sides), then two upgrade passes — (1)
  trust-on-first-upgrade with local AND remote baseline capture,
  (2) re-labeled release + per-host MOD/ADD/DEL injections with remote
  rsync diff pull and per-host salvage. Decline leg asserts BOTH hosts
  untouched (find -newer marker — the lab already carries the target
  version dir, so existence proves nothing). dev-tarball only.
- GREEN 2026-11-10 (run-20261110-003751, 56 pass / 0 fail, guests
  destroyed at verdict) after three fix iterations:
  1. Stage O rollback needs ZFSUTILITIES_ALLOW_CONFIG_DOWNGRADE=1 on
     the compute side (no archived pre-0.125.0 config there — the
     fence is correct; storage restores its archived generation).
  2. F-048 (see FINDINGS.md): the per-host SSH control-master
     establishment drains stdin — the archive prompt read EOF under
     the piped feed and declined; fixed with `</dev/null` in
     bin/upgrade-zfsutilities open_ssh_master. This is the defect the
     journey existed to find.
  3. compute MOD target must be a real tree file
     (docs/docs/commands-and-modules/two-node.md — the top-level
     docs/docs/two-node.md path does not exist; >> onto it made an
     ADD, correctly).
- common.sh: `itf_journey_stage_upgrade_env` gained `--guest-ip`
  (two-guest journeys; J_GUEST_IP holds the last clone otherwise);
  served-release detail text no longer claims a pristine under
  ITF_UPGRADE_BASELINE=none. j10/j12/j19 call sites unchanged.
- itf_journey_verify_installed asserts single-node node.conf — unusable
  on two-node guests; j23 carries its own per-role wiring verifies.
- test-itf-driver's committed-journey loop had drifted (no j22) — j22
  and j23 both added.
- Coverage map: Two-node release-upgrade cell filled, gap bullet
  retired. The other two gap rows stay (not named).
- pkill -f self-match gotcha (again): a pkill whose pattern appears in
  the wrapping bash -c line kills the compound command mid-flight.

## 2026-11-09 — 0.139.0 lane merges + j11 + wrap-up rerun (user-cued, numbered steps)

- Pre-merge leftovers: the user's docs hand-edit sweep committed verbatim
  (`feb69c8`). pub2 lane merged (`ee3900c`; changelog sections unioned,
  GLOSSARY fused, SESSION_NOTES seam, PREEXISTING union-minus-retired —
  the flat-listing entry dropped because its root-filtered mock fix was
  already on main, verified in-tree and by the holds/delfs/busy suites;
  the schedule viewport test took pub2's `_import_fresh_patched` form).
  pub3 lane merged (`4cc0998`; the lock-child suites supersede main's
  MP_FORK pin, `TestScheduleSavedState` rebased on pub3's
  `_FreshSchedulePageTestCase`, the user's hand-edited wording kept
  where lanes touched the same sentences, requirements.manifest
  unioned, the changelog's CI-3.14 bullet trimmed of the superseded
  fork-context sentence).
- Post-merge gate green first try: ruff check+format, shellcheck clean,
  docs-integrity, mkdocs (standing banner only), full run WITH soaks —
  all suites green. Both lanes ff'd to `4cc0998`; all three repos now
  sit at one head, unpushed.
- j11-payload-e2e against pub's merged tree
  (run-20261109-183126): green — payload matrix all scenarios, guest
  destroyed at verdict, no leftovers.
- Wrap-up steps 1–7 rerun. Step 1 resolved both merged PREEXISTING
  entries: the vacuous delfs autoproceed subprocess test now runs the
  real loop (PATH-carried zfs stub + file-based fsarray; asserts the
  positive "was deleted." line; red-proofed — the old runner shape
  fails with empty output) and the 100-column deviations in the five
  released suites were reflowed (assertion args via in-quote
  backslash-newline splices with col-0 continuations; single-quoted
  JSON payloads as adjacent quoted pieces; journal-fixture lines moved
  from quoted heredocs to printf appends — quoted heredocs cannot wrap
  in place). All five suites green and shellcheck-clean; the bytes the
  fixtures deliver are unchanged. Steps 2–5 green (ruff, shellcheck,
  100-col sweep, docs-integrity, mkdocs). Committed at the user's cue
  as part of the 0.139.0 cycle (changelog Tests section records both
  fixes).

*(lane history block, unioned at the 0.139.0 pub2-lane merge — pruned
at the next release prune)*

## 2026-11-04 — Assisted "dataset is busy" resolver (approved plan, executed)

Deep-research turn → novice-translation turn → user directives (names are
birth labels, never usage truth; least-intrusive remedy tailored to the
specific occurrence; hold the user's hand; automate, ask only simple
questions) → approved plan → executed same day. Scope: when a destroy is
refused "dataset is busy", find the holder from authoritative evidence and
offer a guided remedy; unattended runs keep report-only.

- bin/zfs-diagnose-busy rewritten: `busy_find_holders` (evidence engine) +
  `busy_resolve_dataset_busy` (gate + least-intrusive ladder) +
  `diagnose_dataset_busy` (report-only view). Evidence: holds classified
  (`.send-*` leftovers), send/recv pgrep, resume token, fuser holders WITH
  pids, /proc/*/mounts namespace scan (own-namespace view filtered),
  findmnt snapshot automounts, LIO export matched by DEVICE via
  targetcli listing or configfs udev_path walk (BUSY_CONFIGFS_ROOT for
  tests), VM refs via iscsi_detect_vm_gather records + run state.
  Ladder: retry-offer → transfer wait → leftover-export unplug (no VM) →
  stopped-VM detach+unplug → running-VM menu (unplug now / shut down for
  me [tool runs qm shutdown + waits] / do nothing) → leftover-tag release
  or `zfs destroy -d` default (product tags never auto-released) →
  snapshot automount umount -l → namespace mounts report-only → receive
  -A on explicit confirm. Gate: interactive iff (-t 0 or input-hold) and
  busyassist!=N; prompts ONLY via ask_yn/ask_line (GUI panel carries
  them); unattended → report + rc 2.
- lib/iscsi-lib.sh: `iscsi_unplug_export` extracted from iscsi_teardown_zvol
  (log strings kept; recorded for send-receive rebuild only when a dataset
  rides it); new `vm_config_remove_disk_key` (qm set --delete over ssh) and
  `vm_shutdown_wait` (clean shutdown + poll, never force).
- Callers (stderr capture + ONE retry on resolver rc 0): zfsdelfs, zfsdelsnap
  (success path now returns before the skip/FATAL block), sever-vm-clone
  (local + remote heredoc arms), clone-vm (both cleanup blocks).
- Tests: test-zfs-diagnose-busy rebuilt around FILE-based recording mocks
  (array appends made inside $( )/pipelines vanish — subshell law) with
  scripted ssh outcomes per call; 27 tests incl. the three menu outcomes,
  gate, configfs fallback, name-agnostic export, helper units. delsnap
  suite: resolver stubs in all stub files + retry-once test (file counter).
  delfs suite: busy stub + retry subprocess test (PATH carries the zfs
  stub; fsarray crosses exec as a FILE — arrays cannot be exported; the
  pre-existing autoproceed subprocess test is vacuous by the same
  array-export limitation, left as-is). sever mockbin gains the resolver
  stub. 6 red-proofs fired (gate, unplug, deferred, delsnap retry, delfs
  retry, extraction).
- Docs: modules.md zfs-diagnose-busy section rewritten (evidence table,
  ladder, rc 0/1/2, corrected caller list — the old table named three
  callers that never called it); messages manual gains the full
  zfs-diagnose-busy section (was entirely undocumented — closes the
  standing gap) + updated zfsdelsnap/zfsdelfs rows + the busy-resolved
  success line; global-variables gains $busyassist + rewritten $skipbusy
  row; gtk-gui.md Delete row describes the guided questions; GLOSSARY
  gains "mount namespace".
- Deferred (parked, see above): folding remove-vm-disk/detach-vm-disk onto
  iscsi_unplug_export + map-keyed lookup.

## Backup property fidelity campaign — COMPLETE (2026-11-02→03, pub)

- Seven phases, one session each, plan file in the user's plan dir;
  commits: P0 base 8cf365f, P1 1c06aea (capture), P2 6507911
  (replay), P3 53f50aa (offsite travel + retention), P4 7f3f81e
  (j20 journey), P5 e623395 (probe matrix + ubuntu template),
  P6 0389018 (receive-as-encrypted). P3 never wrote its own entry
  here; its record is the commit + docs.
- Shipped, one line each: property-manifest sidecar (post-verify
  capture; WARN-only replay at restore incl. keylocation set +
  best-effort file:// load-key); offsite legs carry the manifest
  stores as ordinary datasets with lockstep retention; GUI "Replay
  properties" + "Receive as encrypted" (initial receive only, works
  on every fleet OpenZFS, no capability gate); zfsrestoresendstream
  consumes .props siblings; ITF j20 journey + j21 probe matrix +
  ubuntu template profile; recv_o_volblocksize pinned 2.5.0 by
  measurement (refused on 2.2.2/2.3.9/2.4.4).
- Live gotchas kept from the phase entries: (1) manifest checksum
  contract — capture writes the body WITHOUT a trailing newline, so
  parse JOINs lines with \n separators (one per line breaks sha256);
  (2) a same-name restore strips TWO qualifiers (backuproot +
  srcpool → destfs is the pool) — fixture data assuming one is wrong,
  not the mapping; (3) ubuntu template installs by DIRECT KERNEL
  BOOT (the ISO's grub handoff dies dark on the serial-only guest;
  casper kernel+initrd via qm -kernel, seed carries
  shutdown: poweroff); (4) journey authoring: guest*.txt in a run
  dir is the harness guest-record namespace (--rerun reads it), and
  ask_yn prompts feed in order (zfssnapbuild's prior-nextsnap ask
  eats a line before zfssend's read — feed spare newlines).
- P7 wrap-up (this entry): mkdocs rc 0 (known MkDocs-2.0/Material
  banner only); ruff check + ruff format clean; shellcheck -S
  warning clean (empty findings log); GLOSSARY queue resolved (ACL,
  DEL, idiom, LIO, Phase-4 precedent added; "cast" stays queued —
  no usage context anywhere) plus probe/property-manifest and
  TCG/TPG alphabetical fixes. Full unit gate green on the final tree
  (zero failures; only skips are the by-design soak suite and the
  root/pool-gated e2e legs; log at /tmp/zfsutilities-p7-full.log).
  Release/publish/deploy wait on the user's cue; after deploy,
  stewie's daily backups start capturing manifests automatically
  (property_manifest defaults Y — nothing to enable).

## ITF thorough-test pass (2026-11-03, user-cued)

- User asked for the campaign to be thoroughly tested in the ITF.
  Gap inventory vs. the P4/P5 journeys: every j20/j21 run predates
  the P5 final pin text and P6; P6's product path, the
  zfsrestoresendstream .props consumption, and standalone
  zfsreplayprops had no journey legs; the GUI Restore toggles had no
  payload-e2e scenarios.
- Built (uncommitted): restore-manifest-replay +
  restore-receive-encrypted scenarios in tests/python/e2e_support.py
  (restore_variables/build_restore_step wrap restore_runner exactly
  as on_restore_run does; "restore-" added to
  test_backup_payload_e2e's prefix tuples); j20 extended with SS
  (hand-made .zfssendstream + .props sibling via zfsrestoresendstream,
  sibling-less file silent), RP (replay_properties=N restore then
  standalone zfsreplayprops), EE (receive-as-encrypted mixed-tree
  restore: one -o receive, skip-keylocation WARN, raw child locked),
  EF (non-file:// keylocation FATAL rc 8, nothing created); j20's
  e2e stage now runs offsite-onward-,restore-.
- F-045 (found + fixed this session, act-on-analysis): receive-as-
  encrypted restore could NEVER transfer — the engine sends every
  stream -cw and zfs receive -o encryption=on refuses embedded-data
  streams (measured on 2.2.2; plain stream verified working in the
  same probe). Unit mocks hid it; j21-p5 measured only plain streams.
  Fix: bin/zfs-send-receive drops -cw (plain send) when the initial
  receive carries the encryption -o overrides; new unit pin
  test_encrypted_step1_send_is_plain; restore.md documents the plain
  step-1 transfer. Row F-045 in tests/integrated/FINDINGS.md.
- e2e lesson: restore payloads run Part 1 with autoproceed="N" (the
  GUI operator gate) — scenarios must h.run(step, allow_prompts=True)
  or the input-hold harness flags the "Press enter to continue." REQ
  as unexpected.
- F-046 (found + fixed this session): the UNPACED zfsrestoresendstream
  could never transfer — `pv | "${pace_argv[@]}" | zfs receive` runs
  the empty array as a null pipeline segment that swallows the stream
  (bash 5.2: `echo hi | "${x[@]}" | cat` delivers nothing); receive
  reads instant EOF ("failed to read from stream"). Regressed at the
  0.133.0 rate-governance rework; unit mocks can't see pipeline
  semantics and no journey drove the script until j20 SS. zfsreadthru
  shares the idiom (unpaced read-through silently stops reading).
  Fix: both scripts compose the pipeline by branch (paced/unpaced),
  like transfer_do; source-shape guard added to
  test-zfsrestoresendstream. Row F-046 in FINDINGS.md. j20 first run
  failed at SS for exactly this reason → rerun queued after the
  sequence.
- F-045 second half (found by j20 EE on the first rerun): the step-2
  catch-up `-cw -I` into the just-created encrypted dataset is refused
  by the same embedded-data law ("cannot receive incremental stream").
  Fix: destination-encryption probe in zfs-send-receive — every receive
  into an encrypted destination from an unencrypted source sends plain
  (plain -I incrementals into it verified working with the engine's -u
  flags; encrypted sources keep their raw -w path). The probe must run
  PER TRANSFER STEP: step 1 creates the destination, so a once-per-
  dataset probe stale-sees absence (rerun 2 failed exactly that way).
  Unit pin test_incremental_into_encrypted_dest_sends_plain — NOTE the
  suite invokes tests by an explicit bottom-of-file list; a defined-but-
  unlisted test silently never runs (both new encrecv tests were
  initially unlisted; caught by reading "Total: 8" in the gate log).
  Probe-side fact: a step-1 encrypted receive WITHOUT -u auto-mounts
  and dirties the lineage ("modified since most recent snapshot") —
  the engine's -uvFs shape is what makes plain catch-up receives work.
- Runs (as dan, detached), ALL GREEN on the final tree:
  j20 run-20261103-144041 (zero failures — the full extended chain
  incl. SS/RP/EE/EF + the widened e2e pair), j21 storage/compute/
  ubuntu zero failures each (2.3.9 / 2.4.4 / 2.2.2 — final pin text
  verified on all three profiles), j11 zero failures with the guest
  payload matrix fully green incl. both new restore scenarios; final
  full unit gate zero failures (log /tmp/zfsutilities-final3-full.log);
  mkdocs rc 0; sudo dev-host restore scenarios green.


## Cycle wrap-up (2026-11-03, release-candidate freeze)

- Wrap-up sequence on the post-0389018 tree (v0.137.0..working tree,
  62 files +8142/-2532). PREEXISTING resolved: the 2026-11-01 CI flake
  (test_page_runners backup-rsync case) root-caused to an unmocked
  real `zfs list` in the destination mount-chain fence — runner zfs
  state decided the verdict; TestBackupPageRun._patch_dependencies now
  mocks prepare_rsync_destination (hermetic; verified green under a
  failing-zfs PATH shim). File is empty; nothing out-of-scope found.
- Review passes: ruff + shellcheck -S warning clean; policy spot-checks
  (sourced-lib set-line law, w-lock around the manifest snapshot,
  log_msg-only output, no hardcoded hosts outside the orchestrator
  exemption, regex docs) all conformant. Test-suite review: all three
  F-045 send branches and both F-046 pipeline shapes pinned; encrecv
  suite header sharpened to the plain/-cw split (comment only).
- Full unit gate (no soaks) green on the frozen tree: 111 bash suites
  + python 4503 passed / 22 skipped (env-gated e2e legs); docs
  integrity 23/23; mkdocs rc 0 (known MkDocs-2.0/Material banner
  only). GLOSSARY reviewed — no entries needed. Codebase FROZEN at
  this point; release/publish/deploy on the user's cue.

(pub2 lane history block, unioned at the 0.138.0 merge — pruned at the
next release prune per the cycle rule.)

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

## 2026-10-31 — GLOSSARY.md created (user request)

- New root-level GLOSSARY.md with the nine seed terms the user named
  (CI listed once — their list had it twice): CI, controlled reboot,
  dp module identity, green, GUI, mock, shape, suite, TTL. Alphabetical;
  each entry gives the plain-language meaning plus the project-specific
  anchors (e.g. dp module identity ← the 2026-10-31 CI TTL-flake
  diagnostic; controlled reboot ← the boot-incident exercise, oracle =
  the user's "Corrected exercise sequence" file).
- STANDING INSTRUCTION (user, 2026-10-31): keep adding entries as new
  jargon comes to light — proactively, without waiting to be told. Also
  recorded in the glossary intro itself.
- Entry 2 (same day, user-fed): "config version" — decodes the GUI-start
  WARN "Config version 31 is newer than software expects (30)". Instance
  diagnosed read-only on the dev host: config migrated to generation 31
  by 0.136.0-era software (deployed current + all three lane trees at
  CONFIG_VERSION 31), then the switch-version rollback to 0.134.0
  (generation 30) read it — user's rollback theory confirmed. Benign:
  v31's migration only drops the dead do_part1/do_part2 restore keys;
  unknown keys ride along; warning self-clears on newer software.
- Queue mechanism added by the user 2026-10-31: an "Items to add:" hand
  list at the file head. Standing rule — every glossary edit processes
  the queue: define each listed term, then remove it from the list
  (header kept). First queued term "full unit gate" defined same turn.
- Docs-integrity suite green after the addition (a root .md is outside
  its docs/ walk; run was confirmation only). No code changed; not
  committed.

## 2026-10-31 — Config-generation downgrade safety (user: "I need you to fix it")

- Trigger: the GUI-start WARN "Config version 31 is newer than software
  expects (30)" after the switch-version rollback to 0.134.0. Root cause
  is structural: switch-version had zero config-generation awareness, so
  any rollback could pair a newer config with older software forever,
  and the warn branch neither protected the newer config nor named a
  remedy.
- python/config_core.py: new _archive_config() writes the exact loaded
  dict to <state>/config-archive/config.v<N>.json — on every forward
  migration (pre-migration state) and on the newer-than-build warn
  branch (pristine state, before the older build can rewrite it). WARN
  message rewritten to name cause + remedy. Archiving failures log WARN
  and never block a load.
- bin/switch-version: gate_config_generation() runs before any wiring
  change. Downgrade (target CONFIG_VERSION < live config_version) with
  an archive of the target generation: back up the newer config to the
  archive, atomically restore the target's. No archive: FATAL refusal
  (mutates nothing); ZFSUTILITIES_ALLOW_CONFIG_DOWNGRADE=1 archives the
  newer config aside and removes config.json (older release starts from
  defaults). Unknown target generation (pre-schema releases) or no
  saved config: gate skips. Target gen helper bug found via bash -x:
  missing versions/ path segment (first red run silently no-opped).
- Tests: test_config_core +4 (archive-on-migrate, archive-on-warn +
  remedy message, no-archive-on-match, freshest-wins); test-switch-version
  +5 (restore, refuse-and-mutate-nothing, override, upgrade-untouched,
  skip-when-unknown/no-config). Harness: _make_fake_version optional 4th
  arg writes python/config_migrations.py; _setup_switch_env redirects
  ZFSUTILITIES_CONFIG_PATH (was missing — tests would have touched the
  host's real config). || rc=$? idiom on all new main calls (a die-path
  rc=1 previously killed the suite shell).
- Red-proof: python exact (3 archive tests fail with the archiver
  disabled); bash — disabling the gate fails test 18 with explicit
  reasons and the suite goes red. Known loose end, disclosed: with the
  gate artificially disabled the suite shell dies at the first test_fail
  of a NEW gate test (set -e leak through that path not root-caused; an
  artificial failure of a pre-existing test runs the full suite cleanly,
  so it is specific to the disabled-gate flow and never ships).
- Docs: messages rows (config_core WARN reworded + Could-not-archive +
  4 switch-version gate rows), index.md path-layout config-archive/,
  commands.md switch-version gate prose + globals + data-structure rows,
  GLOSSARY config-version entry updated. ruff/shellcheck clean.
- Not committed. VERSION/changelog untouched per Hard Rules.

## 2026-10-31 — zfsshowbigstuff oldest-snapshots section (user request)

- New section between the recordsize block and the sort loop: the
  `count` (default 5) oldest snapshots under the target, recursive,
  oldest first, columns name/creation/used (user chose the used column).
  Command spelled `-r -t snapshot -s creation` — split flags because the
  shared zfs mock's parser only recognizes the split form (same real-zfs
  semantics). Placement BEFORE the loop is load-bearing: the mock's
  sequence marker is last-call-wins, so an after-the-loop section would
  overwrite the -S/-s marker the existing sequence tests assert.
- Usage line corrected (count was documented as smallest-only; it applies
  to every section).
- Tests +3 (five-oldest default w/ 7-snap fixture proving newest-two
  excluded, count honored, section-before-sort-sections). Red-proof:
  disabling the header → exactly 3 failures (displayed PASS after a
  failed assert is the known assert-chain verdict flip; counts are
  truth). shellcheck clean; suite green.
- Docs: commands.md section + internal flow, messages row
  `INFO: Oldest ... snapshots`. GLOSSARY queue processed: TCG (QEMU
  Tiny Code Generator — the lab's no-KVM boot mode) and drift added.
- Not committed. VERSION/changelog untouched per Hard Rules.

## 2026-10-31 — All treeviews natural-until-20 (user request, approved plan)

- `gui_helpers.capped_treeview_scroll` default flipped to
  `fixed_rows=False`; every treeview (28 sites: all nine tab pages,
  dialogs/wizards, EditableListView, pool watch) now sizes to its rows
  up to the 20-row cap and scrolls inside beyond. Dashboard Tasks'
  deliberate ten-row fixed window superseded (user confirmed uniform
  rule). Page tables pack non-expanding; dialogs/pool-watch keep expand
  (dialog default follows natural, user resize still fills). Pools VPaned
  children keep expand — divider governs — plus a new first-map divider
  default at the top pane's natural height (Xvfb probe: GTK's unset
  default hands pane 1 half the window, divider 400 vs natural 124;
  saved bind_paned restore wins over the default).
- Page-viewport MINIMUM-policy crush cure applied to logs, schedule,
  offsite, checkagainst, disks, retention (dashboard/memory had it);
  Xvfb probe: at a 240px window MINIMUM crushes both tables to 92px,
  NATURAL keeps 100/464 and the page scrollbar engages.
- Test-order gotcha (structural fix): test_dashboard_page imports
  gui_helpers/logs_page under REAL gi; in a shared pytest worker the
  mock-based suites then bind the real capped_treeview_scroll and die on
  real-SW.add(mock view). Fixed by evicting the preloaded bindings
  before the suite's own mock import — and the eviction list must
  include the PAGE module too, not just gui_helpers: the first full-gate
  run failed 3 SetButtonMarkup tests because checkagainst_page was
  preloaded by an earlier suite bound to a DIFFERENT gui_helpers, so
  patching this suite's fresh gui_helpers diverged from what the page
  called (datasets/logs/pool_watch hardened the same way). Lesson:
  log_index must NOT be evicted — temp_config_dir patches it through
  test_support's own module reference, so a fresh copy escapes the
  redirect (PermissionError into /var/log). Module-level
  mock_gtk(fresh=True) is the WRONG tool here: string-target @patch
  resolves sys.modules after restore and diverges from the local
  binding. The 2026-10-30 PREEXISTING entry (restore→checkagainst
  ordering flake) was this same class — fixed here, entry retired.
- alignment_realized_check.py assert_twenty_rows updated to the natural
  convention (window hugs rows below the cap, 19.4–21.6 visible above);
  the realized suite re-verified green under its private Xvfb.
- Xvfb probes: natural==cap exactly at ≥20 rows (464px @ row 21), empty
  floor 71px, vscroll beyond cap, divider default + restore precedence,
  viewport cure. Probe laws reconfirmed: preferred-height needs
  parenting; a bare window stretches its only child (max_content bounds
  the request, not the allocation).
- Docs: gtk-gui.md Dashboard/Performance/Alignment table passages,
  testing.md three suite rows, GLOSSARY capped-table-window entry.
- Not committed. VERSION/changelog untouched per Hard Rules.



## 2026-11-01 — upgrade-zfsutilities ITF coverage (user prompt)

- Prompt: "`upgrade-zfsutilities`: Ensure it's tested in the ITF."
- Investigation: j10/j12 already cover the single-node upgrade path but
  had never been run from THIS lane (last documented j10 green was
  2026-10-24, 0.132.0-era tree); the F-025 trust-on-first-upgrade
  baseline capture (0.132.0) is structurally unreachable in both —
  the shared staging always provisions a pristine scan source; the
  DEL scan classification was never injected by any journey.
- User decision: two-node upgrade journey NOT built this cycle (ITF
  contended by the pub lane) — recorded as a gap row in
  developer-guide/itf-coverage.md instead.
- common.sh: itf_journey_stage_upgrade_env gained
  ITF_UPGRADE_BASELINE=none (skip pristine provisioning entirely;
  j10/j12 default behavior unchanged).
- New journey j19-baseline-capture: upgrade 1 on the untagged 0.118.0
  tree must capture a baseline manifest additively (pre-capture mods
  absorbed, not flagged, nothing salvaged); upgrade 2 must scan
  against the CAPTURED baseline (MOD + ADD + DEL — first journey
  exercise of the removed classification), salvage with local
  content, degrade diffing honestly; then switch-version + wiring
  verify.
- j10 fresh run GREEN (run-20261101-103911): all stages pass on the
  0.136.0 dev tree — including switch-version activation, which
  exercises the user's uncommitted bin/switch-version edits (the dev
  tarball packs the working tree).
- j12 first fresh run FAILED at X2 — journey-side race, not product:
  the wrapper SIGKILLed ≤0.2 s after the transcript's deploy marker,
  which the upgrade prints BEFORE deploy-version execs, so the kill
  landed in deploy-version's startup, before the versions-dir mkdir
  (deploy-version itself unchanged since before j12 existed; the
  origin green was polling luck). Fix: the X2 trigger now waits for
  versions/<target> to exist (deploy's first action) — the partial
  dir becomes deterministic. --rerun GREEN.
- j19 first run failed its own M2 guard loudly: README.md is NOT in a
  deployed tree (deploy-version copies bin/lib/python/docs/share/
  VERSION only — no repo-root files). DEL anchor switched to
  docs/docs/user-guide/gtk-gui.md (verified present at the template
  rev 200577d). --rerun GREEN (run-20261101-111606).
- Final: j10 GREEN (run-20261101-103911), j12 GREEN
  (run-20261101-110536), j19 GREEN (run-20261101-111606) — all on the
  0.136.0 dev tree; upgrade-zfsutilities's single-node surface is now
  fully journey-covered including the F-025 capture path and the DEL
  classification. Two-node remote-target surface recorded as a gap row
  in developer-guide/itf-coverage.md per user decision.
- Full unit gate green on the final tree (bash + python legs, user
  mode; sudo e2e leg not run — no payload/product changes in scope).
  Journey-list test synced to j01–j19. Not committed; VERSION/
  changelog untouched per Hard Rules.

## 2026-11-01 — Development-cycle wrap-up (pub2 lane, frozen)

- Step 1/4 (PREEXISTING resolution) skipped by the step's own
  precondition: pub-main-only, this is the pub2 lane. Lane file had 0
  open entries at step 1 (sole entry fixed by the treeview change's
  test-order hardening).
- Step 2 standards (coding-policies.md): ruff check clean; ruff format
  fixed one blank-line nit in pools_page.py (271 files clean after);
  documented shellcheck file set exit 0; column sweep — wrapped the new
  134-char test_fail line in test-zfsshowbigstuff byte-identically via
  reason+= ; 4 pre-existing >100 common.sh payload lines left (the
  unwrappable-bytes class); by-eye review of every new hunk (gate,
  archiver, oldest-section, knob, j12 fix, j19, page diffs) clean.
  PREEXISTING +2: test_lib's test_fail reads only $1 while several
  suites pass multi-arg reasons (detail silently dropped on failure —
  diagnostic-only); three pre-existing >100-col python lines.
- Step 3 tests: added the missing pools-page first-map divider-default
  test (new product logic had no unit coverage; suite 51/51). Rerun
  green: test-zfsshowbigstuff (after the line wrap), test_pools_page,
  test-switch-version 22/22, test-itf-driver (j19 registered). No
  obsolete tests (old fixed-height asserts all updated by the cycle;
  migrate-dialog min-120 site is a TextView, correctly outside the
  sweep); ITF_UPGRADE_BASELINE knob is journey-tier covered (j19).
- Step 5 docs: all 7 changed docs surfaces verified against code
  (switch-version gate prose + env/data rows, zfsshowbigstuff section,
  messages rows incl. reworded config WARN, natural-table passages,
  config-archive/ path row, j19 + gap rows); test_docs_integrity 23/23;
  site rebuilt rc=0 (standing MkDocs-1.x banner only).
- Step 6 full run without soaks: 108 suites, all passed, 0 failed;
  1 bash skip = the soak suite (runner design in no-soak mode), 18
  python skips = standing root-tier e2e preflight. Over-budget list is
  the routine runtime advisory, no action.
- Step 7: tree FROZEN here — 52 modified files (+1,269/−230) + 2
  untracked (GLOSSARY.md 240 lines, j19 journey 378). No commit, no
  version bump, no changelog (user cue, per Hard Rules).

## 2026-11-01 — Release 0.137.0 prep (pub2 lane, user-directed steps 8-10)

- Step 8: VERSION → 0.137.0; changelog 0.137.0 section written
  (Added: config-generation downgrade safety, oldest-snapshots section,
  j19-baseline-capture journey, GLOSSARY.md; Fixed: cross-suite
  test-order flake; Changed: all tables natural-until-20; Tests;
  Documentation). docs-integrity 23/23; site rebuilt rc=0. Final gate
  `tests/run-tests --with-soak`: 108 suites, all passed, 0 failed, 0
  bash skips (soak suite ran), 18 standing python e2e preflight skips.
  No fixes needed.
- Step 9: no further code changes.
- Step 10: whole cycle staged + committed as the 0.137.0 release
  commit under the user's explicit instruction.


## 2026-10-31 (night) — v0.136.0 published; CI TTL-cache poisoning fixed

Published 0.136.0 (pushed 0111e0f..55d4c3d, tagged v0.136.0, GitHub
release; compare base v0.133.0 — 0.134.0/0.135.0 rode the push untagged).
Post-publish prunes (notes, repair-plans, FINDINGS, results) sit in the
working tree riding the next notes commit. CI on the pushed commit went
RED: 5 dashboard TTL-cache tests on one xdist worker — a leaked REAL
async dashboard-refresh thread (the page-switch handler fires it) whose
ssh/zpool gathers time out over seconds on runners, so its cache writes
landed inside later tests (compute-mocks at 0 calls, one
[]-is-not-None). Unreproducible locally (subprocesses fail fast) across
pytest 7.4.4 and a pytest-9.2.0 venv, 4 workers, Xvfb; CI installs
pytest 9.2.0 via install-test-deps.sh vs the dev host's 7.4.4. Fix
(user-approved), two commits: (1) 9e927cd — tests/python/conftest.py
autouse drain: the refresh worker is wrapped to track its threads; after
every test live workers are joined (70s bound) and the three TTL caches
reset cold. Red/green-proven with a straggler simulation; the CI rerun
proved the stragglers REAL (the python leg stretched 59s→326s from the
joins) but the five TTL tests stayed red — the drain was necessary, not
sufficient. (2) 43ebb1d — the three TTL suites now patch in a PRIVATE
cache dict plus a controlled monotonic() clock per test (dashboard_page
uses time.monotonic() only), making the assertions independent of
wall-clock time and shared module state; test_failure_is_not_cached
reports the dp module identity + cache on failure (the diagnostic if
this ever recurs — a dual-module-instance cause would show there). CI
GREEN on 43ebb1d. The tag's red run stays red (never move tags); the
fix commit's green run is the proof. The exact CI-side writer was never
pinned down (no local reproduction across pytest 7.4.4/9.2.0 venv, 4
workers, Xvfb); the per-test isolation makes the question moot.

## 2026-10-31 (late) — j11-payload-e2e green on the published payload

User cued the live j11 run (the 0.136.0 lanes include payload-stack
work: interrupted-restore resume + run-completion notifications). Run
`run-20261031-192033-j11-payload-e2e`: every journey step green —
template clone, three test pools, 0.136.0-dev staged from the working
tree, full payload matrix (offsite holds/incrementals/rollback/resume/
scrub-pause, backup/prune/rsync, strict-mode orchestrators; real
per-scenario wall times, not a vacuous pass), pool-residue clean.
Guest + both disks + both checkpoint snapshots destroyed at the
verdict; bases clean, lock freed. ~8.5 min wall — clone-linked start
+ small pools, far under the G5 install-flow estimates, as expected
for j11's shape. No FINDINGS; deploy cue's payload-validation
precondition is now green.

## 2026-11-01 — repair plan 025 (F-034) executed, live-disproved,
## corrected, verified

User cued plan 025 (setup-iscsi-targets portal binding). First pass
implemented the plan as written (per-target create-then-replace,
fresh-TPG window only): red-proven suite, docs rows, FINDINGS → fixed.
The j05 journey disproved the plan's core premise LIVE: LIO portals are
host-level sockets — the 0.0.0.0:3260 wildcard binds INADDR_ANY:3260,
and while ANY TPG rides it no specific :3260 portal can be created
anywhere ("Could not create NetworkPortal in configFS"); the plan's
"port conflict only exists for the SAME address" contradicted F-024's
own verified row. Guest-side probes proved the working sequence: purge
the wildcard from ALL TPGs, then bind specifics (two-arg `portals
create <ip> <port>` — the one-token ip:port form parses as a bare IP
and can never bind). User approved the corrected recipe same day:
post-loop host-wide purge-then-bind in the all-fresh window only
(existing targets never purged — a wildcard removal on an established
target would drop live sessions), wildcard-restore rollback, FATAL if
a TPG ends portal-less (F-024 law). Unit portal mock rebuilt to model
host-level sockets (shared ip:port references, ANY-bind blocking) —
the per-TPG mock it replaced is what let units stay green against an
impossible mechanism; red-proven against the pre-025 script. Harness
defects fixed in-cycle (never FINDINGS rows): j05's portal probe used
an invalid one-shot `targetcli ... ls 2` (depth parses as a path) →
per-TPG portals ls sourced from node.conf; j16's assert grepped the
pre-correction wording. Verification: j05 --rerun green (three
specific binds live, wildcard purged, first LUN round trip through
the specific portal) and j16 --rerun green after a mid-run dev reboot
(--rerun takeover did exactly what the orphan fence designed); S7b
total-wipe rebuild storage-IP-bound with recovery through it. F-034
`verified`; plan 025 closes at the next release prune. Deploy note:
production targets exist → setup re-runs keep today's posture there;
the specific bind lands only on fresh installs.

User cued repair plan 026 (map grants dimension, F-037). Executed as
written with one execution-time decision the plan left open: dual-read
migration with the version marker bumped to 2 (readers accept legacy
name-list maps; identity-grant behavior preserved for them — the map's
own pools-key precedent). export-iscsi-state records per-initiator
mapped_lun->tpg_lun pairs (parser extended in iscsi-lib.sh; red-proven
on the old shape; golden regenerated); reconcile recreates recorded
pairs exactly — grant-bearing ACL records rebuild even on demo TPGs
(a demo login self-generates identity grants only), a present pair
mapping differently refuses (FATAL) and — second in-cycle find — the
map-refresh gate now blocks on ANY apply failure, because the failed
ACL grant previously slipped past the per-backstore outcome check and
would have let the refresh overwrite the recorded authority;
iscsi_grant_lun_to_acls (recover + add-encrypted heal path) recreates
recorded pairs and leaves initiators whose recorded set lacks the LUN
ungranted instead of blanket identity. Third find, live-proven by the
first j16 attempt: `targetcli ... | grep -q` under pipefail flips found
objects to "missing" (grep -q exits on match, targetcli SIGPIPEs, 141
pipeline) — it made reconcile refuse a live target at S6 while the
compute sessions stayed up; a 300/300 local repro; fixed on all
plan-026 surfaces plus setup's /iscsi ls probes, remaining ~25 sites
recorded in PREEXISTING.md. The rerun then hit the shared-lab fence:
pub2's concurrent journeys hold VMID 8001-8004 on the base hosts and
my lane's stale Oct-31 claim points at pub2's live j05-storage, so the
orphan fence refuses (destroying/--rerun would hit pub2's guest).
User chose: keep waiting for a window (background retry loop, verdict
to /tmp/j16-queued-verdict.txt); F-037 stays `fixed` until that run
flips it `verified`. Also fixed in the window: one dev-tarball build
failure was my run racing the user's live doc edits ("file changed as
we read it") — timing only. Full bash suite green once at the end;
python 4355 passed with one host-load flake (profile_runner 15s
subprocess timeout under pub2's VM load; 110/110 green in isolation).


## 2026-10-31 — Dashboard offsite-pool false warning fixed (pub3)

- User report: Dashboard warned "Pool z22tb is configured in node.conf but
  not imported" while z22tb is an offsite candidate exported on purpose
  (verified live on stewie: 4 pools imported, z22tb still in POOL_TARGET).
- Fix: `_compute_pool_identity_warnings` takes optional GUI config;
  offsite-candidate pools (`feature_config.get_offsite_candidate_names`)
  are exempt from the not-imported shape only — imported-but-unconfigured
  and GUID-mismatch shapes unchanged. Plumbed via
  `_get_pool_identity_warnings(app.config)`; TTL-cache behavior unchanged.
- 3 new tests in TestComputePoolIdentityWarnings; targeted suite + full
  tests/run-tests green; ruff clean. Docs messages row updated.
- Out of scope, recorded in PREEXISTING.md: bash-side
  detect_pool_identity (check-prerequisites / setup-iscsi-targets) has the
  same false positive and no offsite knowledge — needs a node.conf-side
  marker decision.

## 2026-10-31 (later) — root-owned __pycache__ structural fix (pub3)

- User report (named PUB): root-owned files keep reappearing in
  __pycache__. Cause: dev-host root interpreters (sudo GUI launches, sudo
  pytest e2e legs) import repo modules and write missing/stale .pyc caches
  as root into the dan-owned tree; sweeps delete, next root session
  recreates. Live evidence: pub2+pub3 each held one root-owned
  disk_surface_test.cpython-312.pyc (2026-10-30 10:26/10:47) — same file
  swept 2026-10-26; pub's __pycache__ dir itself was root-owned then.
- Fix: when euid==0, redirect bytecode via sys.pycache_prefix to
  /var/cache/zfsutilities/pycache (env ZFSUTILITIES_PYCACHE_DIR; existing
  interpreter prefix respected). Hooks: _redirect_root_pycache() before
  product imports in python/zfsutilities_gui.py (E402 per-file-ignore
  added) + same block in tests/python/conftest.py beside the LOCK_DIR
  isolation. 3 new tests (TestRedirectRootPycache); docs testing.md gained
  the root-run cache story incl. the conftest-own-pyc residual.
- pub3 straggler unlinked; find -user root = 0 in pub3. pub2's straggler
  NOT touched (outside working dir) — needs one unlink in that lane.
- Lands in pub via the lane-merge cycle. Live root verification is the
  user's (sudo GUI launch, then find -user root).

## 2026-10-31 (evening) — Datasets unmount FATAL after failed export (pub3)

- Incident (stewie, 0.134.0, journal-verified): 10:05:51 zpool export z22tb
  unmounted all pool datasets as part of its attempt, then failed (blocker
  unknown — foreground GUI actions log only to the in-app pane; no
  rsync/send/scrub active). Datasets page kept the stale pre-export
  "mounted" rows (no page-switch refresh branch, no timer, manual Refresh
  only). 10:07:18 user unmounted z22tb row (stale gate passed) → kernel
  "not currently mounted" → generic FATAL (dataset_actions.py:1208) —
  goal state presented as failure; wrapper skipped refresh (changed=False),
  stale display survived the user's manual child walk 10:09:43-10:10:49.
  10:11:36 unrelated successful mount refreshed the page ("unmounted on its
  own"); 10:12:45 export retry succeeded (zed EXPORTED 10:12:46).
- Fix: idempotent unmount — live-listing pre-check (target mounted!=yes →
  VERB "was already unmounted", success) + "not currently mounted" stderr
  branch (same VERB, continue); repo.unmount_filesystem treats that stderr
  as success (only caller: export-recovery auto-unmount); on_page_changed
  gained the missing datasets branch (refresh on switch);
  _try_export_with_recovery logs _log_pool_mount_state ("N of M still
  mounted" / "All datasets ... already unmounted") after blocker collection.
- Tests: 2 in TestUnmountDataset, 1 repo, 1 page-switch, 3 in new
  TestLogPoolMountState. Docs: 2 new message rows.

## 2026-10-31 (night) — info-panel input-prompt tint (pub3)

- User ask: tint numbered operator questions ("INFO: [Input 4][Prune] ...
  [y/N]:") bright blue (#00A3F5) in the bottom info-panel log (NOT the Logs
  tab viewer — first reading was wrong, corrected by user, plan re-approved).
- Fix: third tag branch in ZFSUtilitiesWindow._insert_info_line — level INFO
  + _INPUT_PROMPT_RE ([Input N][label]) → lazily created "input_prompt" tag,
  same start-mark/apply_tag_by_name pattern as fatal/warn. Re-renders
  (_render_info_panel replay) keep the tint; close/withdrawn VERB lines
  stay default-colored. 5 new tests; docs gtk-gui.md Log Panel sentence.

## 2026-10-31 (late) — Tooltips campaign Phase 1: shared infrastructure (pub3)

- Plan: user-given "Tooltips Plan", Phase 1 only; Phase 1 coding plan
  approved this session. All six work items executed.
- gui_helpers gained the three shared helpers: set_column_header_tooltip
  (header-label pattern extracted; dashboard Date/Time + disks Wear/Test
  migrated, logs_page left as-is per plan), attach_cell_tooltips +
  _on_cell_query_tooltip/_cell_text_fits/_CELL_FIT_SLACK_PX (moved from
  alignment_page, re-exported there under the old names so
  test_alignment_page passes unedited), and set_action_tooltip
  (reason-or-stored-static single write path).
- add_var_row now sets the tooltip on the Entry/ComboBoxText too, not just
  the label. EditableListView gained optional header_tooltips (Active
  column always gets one) and Add/Remove button tooltips; consumers pass
  lists in Phase 2.
- PAGE_SPECS buttons are 4-tuples (label, icon, attr, tooltip); spacers
  4×None; runner pages carry run_tooltip/cancel_tooltip; add_action_button
  applies + stores button._action_tooltip. disks
  update_disks_button_sensitivity and the datasets mount button now reset
  via set_action_tooltip — static tooltips survive state changes (their
  tests pre-set _action_tooltip and assert the static text).
- Var-tooltip dicts: _BACKUP_VAR_TOOLTIPS (14), _OFFSITE_VAR_TOOLTIPS (11),
  _RETENTION_MASS_DELETE_TOOLTIPS (6) — wording from the gtk-gui.md
  variable reference; Backup's post-hoc prune-filter/allow_destructive
  overrides kept (verified by test).
- Cell tooltips attached to Dashboard Tasks + Active Locks and Pools scrub
  (offset 0 everywhere; Tasks hides its trailing store columns).
- Test notes: test_gui_infrastructure is the established home for
  EditableListView tests (plan said test_gui_helpers; placed beside the
  existing ones). _FakeWidgetBase in test_backup_page had a duplicate
  no-op set_tooltip_text shadowing the new recorder — removed. Module-level
  gui_helpers import in test_zfsutilities_gui via import_or_skip_gi (the
  in-function AST guard requires a mock_gtk context).
- Red-proofed: header helper, three attach sites, stored _action_tooltip,
  all three var-tooltip dicts/widget passes. Full gate run at phase end.
- Next: Phase 2 (nine tab pages) on user cue.
- Full-gate round 1 found 5 failures in two suites my affected-list missed
  because they exercise update_disks_button_sensitivity from outside
  test_disks_page: test_pool_create_wizard (3) and
  test_disks_page_growth_buttons (2) — same _action_tooltip-reset fix
  applied; gate rerun green (see final report).

## Tooltips Phase 2 — nine tab pages (2026-11-01)

- Executed on the approved per-phase plan (user-given Tooltips Plan file);
  Phase 1 infrastructure already committed in f1b315c.
- Helper extensions: set_column_header_tooltip gained optional xalign
  (right-aligned numeric headers keep their alignment through the custom
  header label — Pools numeric 7, Datasets Used/Avail/Refer pass 1.0);
  alignment_page._table and memory_page._device_table gained
  header_tooltips lists (EditableListView contract: length-validated).
- Loop-driven title lists grew to tooltip-carrying tuples (Dashboard
  Tasks/Locks, Disks 3 tables, Datasets, Schedule, Pools scrub); hand-built
  columns got at-site helper calls (Offsite steps, Pools pool table,
  Retention bucket/prune). Backup's two EditableListViews pass
  header_tooltips. _value_row captions (both copies) carry the full
  caption — they ellipsize.
- Sortable headers say "Click to sort." (Schedule 4, Pools 9 of 11,
  alignment chain 4). Wording truth-passed against each column's fill code
  (lock types read/write/destroy; retention Type = bucket full name;
  topology Read/Write/Cksum = zpool-status error counters; Blocksize =
  ashift-derived sector size; scrub Status states; enclosure "% of cap" =
  busier direction) and lifted from gtk-gui.md where it describes the
  item (pull steps, nextsnap, ZFS keys, Retain Count/Min Age, scrub
  table, Origin/Clones, Config Summary).
- One existing test updated: test_dashboard_page's Date/Time header test
  asserted Type/Name/Status headers carry NO tooltip — the exact state
  this phase changes; now asserts exactly-one non-empty tooltip each.
- Per-suite greens: dashboard 300, backup+gui_infrastructure 207,
  offsite 32, schedule 79, retention(+actions) 85, disks 77, pools 51,
  datasets(+actions) 238, memory+alignment 117. ruff clean after ISC004
  paren fixes (concatenated strings inside collections).
- Full gate round 1: 5959 passed, 1 failed —
  test_profile_runner::test_sigterm_cancels_running_profile timed out
  under 6-worker load (SIGKILLed past its 15 s deadline). Passes
  standalone (110/110 in 4 s) and in a same-worker-count python-leg rerun
  (4397 passed); logged in PREEXISTING.md as a load-timing flake. Bash
  legs all green in round 1.
- Phase 2 diff ≈ +440/−105 over 12 files. Next: Phase 3 (dialogs, user
  priority) on user cue.

## Tooltips Phase 3 — all reachable dialogs (2026-11-01)

- Executed on the approved per-phase plan (user-given Tooltips Plan file);
  Phases 1 (f1b315c) and 2 (83525b9) already landed. Dialogs only — no
  attach_cell_tooltips anywhere (no dialog renderer ellipsizes).
- Shared constants in pool_create_wizard.py: _DISK_TABLE_HEADER_TOOLTIPS
  (6 headers, wizard picker + growth/migrate shared picker) and
  _TOPOLOGY_RADIO_TOOLTIPS + _RAID10_RADIO_TOOLTIP (wizard + add-vdev +
  migrate radio groups); growth/migrate import both (import direction
  already existed).
- Dynamic problem-tooltip write paths migrated to set_action_tooltip so
  statics survive the clear branch: wizard _refresh_chrome primary
  (Back/Next/Create), growth confirm buttons x5 (add/expand/replace/detach/
  infra), migrate Migrate button, both manage-profiles dialogs' Edit/Delete
  (built-in reason stays the dynamic reason), disk_wipe + sever-clone
  typed-gate handlers (typed-mismatch reason added where there was none).
- One edit per shared block covers many dialogs: _build_disk_picker headers
  (6 dialogs), _ReviewScaffold typed entry + log checkbox (4), target-tree
  headers (3), dataset_actions._input_dialog gained tooltip= param (snapshot
  name + Add Hold callers).
- Plan-text vs code mappings: no pool rename dialog exists (pool_actions
  Add only); recall dialog has no name entry (Profile/Schedule headers +
  Recall button instead); "per-dataset checks" = migrate's per-property
  replay checkboxes.
- Additions beyond the plan file's named list (approved in the Phase-3
  plan): pool_profile_dialogs manage dialog (4 headers + 4 buttons; its
  editor already had field tooltips — untouched), alignment survey combos
  (Performance tab Survey...), migrate cutover-confirm entry/Cut Over and
  running-VMs Continue buttons. Button rule: non-stock affirmative/danger
  buttons get tooltips; plain Cancel/Close text and stock buttons stay bare
  (enclosure Save / surface Start + Cancel Test / recall Recall reached via
  dialog.get_widget_for_response).
- Test-side accommodations (campaign pattern): set_tooltip_text added to
  hand-rolled fakes — _FakeCombo (test_pool_create_wizard, recording),
  _FakeRadio (test_pool_growth_dialogs), _FakeEntry/_FakeCheckButton
  (test_profile_dialogs), _FakeCombo (test_alignment_page). No existing
  assertions changed.
- Per-suite greens during work; full gate once at the end: 108 suites,
  5960 passed, 0 failed (python leg 4397 passed, 18 environment skips).
  Phase 2's profile_runner SIGTERM flake did not recur. ruff clean, 9 files
  reformatted.
- Phase 3 diff: +425/−42 over 15 python files + 4 test files. Next: Phase 4
  (per-suite tooltip assertions, red-proofed) on user cue.

## Tooltips Phase 4 — test assertions (2026-11-01)

- Executed on the approved Phase-4-only plan. Tests-only diff: no product
  changes (every product file's diff after this phase is byte-identical to
  its Phase 3 state).
- The plan file's "Update" bullet was already satisfied by the Phase 1
  commit (f1b315c): TestPageSpecTooltipUniformity in test_action_dispatch,
  gui_helpers helper tests, update_action_buttons + set_action_tooltip
  tests in test_zfsutilities_gui; EditableListView header-tooltip tests
  live in test_gui_infrastructure (~2006), not test_gui_helpers. Phase 4
  verified those green; test_alignment_page likewise verify-only.
- 22 test files extended. test_pool_profile_dialogs added beyond the plan
  file's list (approved in the Phase 4 plan; its product file carried
  Phase 3 changes the list missed).
- Assertion patterns, all in each suite's established idiom:
  set_column_header_tooltip recorder walks pinning full title sequences
  (Disks 25, Pools 16, Datasets 7, Schedule 6, Retention 6, Offsite 5,
  Performance device tables 16 + alignment view 17, wizard 6, growth
  picker 6, manage-profiles 4+4); shared-mock membership asserts where
  mock_gtk shares instances (Entry/CheckButton/SpinButton accumulate;
  RadioButton splits into constructor and new_from_widget recorders);
  EditableListView header_tooltips asserted via constructor-kwarg
  recorders; typed-gate reason↔static asserts through set_action_tooltip
  (growth add-vdev, disk wipe, pool-profile builtin guards).
- Every new assertion red-proofed by blanking one tooltip at its product
  source, rerunning only that suite, and restoring (Edit-anchored exact
  strings). One early sed restore on backup_page.py hit the wrong "" and
  corrupted the module docstring — repaired byte-identical within the
  turn; lesson recorded: never blind-replace short strings in product
  files, always Edit with a unique multi-line anchor.
- Cross-file facts: growth/migrate import the wizard's
  _DISK_TABLE_HEADER_TOOLTIPS/_TOPOLOGY_RADIO_TOOLTIPS, so the wizard dict
  tests cover all three modules' wiring. pool_profile manage dialog CLEARS
  its ListStore and refills from config — pre-seeded adapter rows don't
  survive, so custom-selection tests must put the profile in app.config.
- _FakeComboBoxText-style no-op mocks from Phase 3 upgraded to recorders
  where assertions needed values (offsite _RecordingComboBoxText with
  ClassVar; profile-dialogs recording Entry/CheckButton classes).
- ruff check clean across tests/python; 13 touched files ruff-formatted.
- Full gate once: 108 suites; single failure was the known PREEXISTING
  test_sigterm_cancels_running_profile timing flake (verified green
  standalone on this tree immediately after). PREEXISTING.md unchanged at
  3 entries; nothing new found in Phase 4.
- Phase 5 (gtk-gui.md Tooltips note, wrap-up gate) remains on user cue.

## Tooltips Phase 5 — lint, docs, wrap-up (2026-11-01)

- Campaign complete. Commit mapping: Phase 1 rode f1b315c, Phase 2 rode
  83525b9, Phases 3+4 rode the user's a1d74dd; Phase 5 is left uncommitted
  for the user (expected diff: gtk-gui.md + this file only).
- Lint verification pass: ruff check clean across python/ and tests/python/;
  all 24 campaign-touched python files already formatted (Phase 4's
  formatting pass covered the test side).
- docs/docs/user-guide/gtk-gui.md gained an additive "## Tooltips" section
  after the Tabs table (headings/fields/buttons/dialogs, disabled-button
  reasons, typed-confirm rules, click-to-sort notes, clipped-cell hover).
  Purely additive; existing tooltip mentions and user hand-edits untouched.
  docs integrity + docs viewer suites green after the edit.
- PREEXISTING.md read before report: 3 entries (the plan file's "2" was
  stale). Nothing new found in Phase 5; nothing addressed.
- Full gate once at the end; see the turn report for the outcome.

## Development-cycle wrap-up (2026-11-01, pub3 lane)

- Seven-step wrap-up procedure over everything since 0.136.0 (55d4c3d):
  commits f1b315c, 83525b9, a1d74dd plus the working tree.
- Steps 1/4 (resolve PREEXISTING) skipped by their own precondition —
  pub-main-only, this is the pub3 lane. No entries addressed; file read
  before report at 3 entries.
- Step 2: ruff check clean repo-wide; one ruff format nit found in this
  cycle's test_zfsutilities_gui.py (missing blank line after the autouse
  fixture) — fixed. No bash changed since 0.136.0, so shellcheck N/A.
  Manual review of gui_helpers/zfsutilities_gui/conftest/dashboard/
  dataset_actions/action_dispatch diffs: no policy violations; the one new
  regex (_INPUT_PROMPT_RE) is documented per policy.
- Step 3: coverage map of every new behavior (pycache redirect, prompt
  tint, header/cell/action tooltips, offsite exemption, unmount
  idempotence, page-switch datasets refresh, add_var_row tooltip,
  header_tooltips validation) — all covered behavior-level, including
  negative/sibling cases. No obsolete or incorrect tests found; no
  additions needed. Affected suite (test_zfsutilities_gui) green after
  the format fix.
- Step 5: docs integrity 23 passed; mkdocs build clean except the known
  MkDocs-2.0/Material warning (user's standing version stance —
  suppressed). gtk-gui.md Dashboard Warnings list gained the missing
  pool-identity bullet, including the offsite-candidate exemption note
  (pre-existing docs gap, fixed in-step rather than parked). docs/site
  rebuilt (gitignored).
- Step 6: full gate without soaks, background, log at
  /tmp/zfs-run-pub3-wrapup.log — 108 suites, 6010 passed, 0 failed, 18
  python environment-preflight skips (root/zfstest e2e legs). The
  recorded test_profile_runner cancel-deadline flake did not reappear.
- Step 7: codebase frozen. Wrap-up touched exactly two files beyond the
  Phase 5 leftovers: tests/python/test_zfsutilities_gui.py (+1 blank
  line) and the gtk-gui.md Warnings bullet (+8); this notes entry.
  Nothing committed — tree awaits the user's commit cue.


## 2026-11-02 — Blocksize ladder: double-height rows, smaller Y labels

User request (Performance → Blocksize Alignment): the ladder graph twice
as tall, Y-axis (row) labels somewhat smaller. Both renderers changed via
the shared vocabulary: `LADDER_ROW_HEIGHT` 22→44 (charting.py) doubles the
row-driven height in matplotlib (stewie) and Cairo (tweety/dev host)
alike — fixed chrome (40px top, 26px bottom, 70px placeholder) unchanged,
so a full ladder lands just under exactly 2×. matplotlib row labels
11→9.5; Cairo row labels split from the shared 13px to their own 11.5
(ticks/legend/placeholder stay 13) with the gutter re-measured at the
label size. Cairo vertical offsets generalized for the taller rows
(baseline `row/2+4`, bar 0.62 of row, centered — matches matplotlib's
proportion). Tests: the three literal font assertions updated
(11→9.5, 13.75→11.875, once-with-16.25→call-set {16.25, 14.375}); height
tests derive from the constants and stayed green untouched. Docs:
charting.md text-vocabulary sentence updated. Nothing committed.


## 2026-11-02 (later) — restore lineage-skip hold-reapply WARN wall fixed

User report (GUI restore run from pub, 2026-11-01 22:14): restore whose
full copy was skipped by the verified-lineage gate still ran the
end-of-run hold reapply over a destination that was never destroyed —
13× "WARN: Failed to apply hold" + "Reapplied 0 holds (13 skipped)",
all because `zfs hold` fails with "tag already exists" on holds that
were never removed. Fix in `bin/zfsreapplyholds` `reapplyholds_apply`:
on a failed hold, check `zfs holds -H` for the tag; already present →
VERB + new `_present` counter ("desired end state"), genuine failure →
WARN unchanged. Summary now "(N already present, N skipped)". zfs-send-
receive untouched (mixed runs still need the reapply for destroyed
datasets; idempotent apply is correct on every path). Mocks made
faithful in tests/test-lib.sh: `zfs hold` refuses duplicate tags like
real zfs; `zfs destroy` drops the destroyed subtree's holds;
`mock_zfs_hold_fail` forces genuine failures. test-zfs-send-receive-
holds world rewritten honestly: the tag that rides a destructive full
copy is offsite-* (delallsnaps releases those; user holds BLOCK the
copy — delfs exits 8), so the world's kept-tag became offsite-srctag
and a NEW test pins the user-hold abort. Two new reapplyholds tests
(already-present tolerated; genuine failure WARNs), red-proofed 2-red
before the fix. Test 5's tag1→tag9 (cross-test state pollution under
faithful mocks). PREEXISTING +1: the flat `_mock_zfs_fs_list` listing
ignores the requested root (root-filter attempted and reverted — three
suites need world rewrites first). pub's zfsreapplyholds is identical;
the fix rides the lane merge to pub.


## 2026-11-02 (evening) — Survey… preloads the Blocksize-scan selection

User request: the Performance page's Survey… button made the user
manually pick the dataset they were looking at. The chain TreeView was
discarded at build (`_chain_view`); it now lives on
`app._alignment_chain_view` (the scrub/datasets/logs idiom).
`alignment_dialogs._selected_survey_dataset` reads the first selected
row's hidden identity key (`Dataset:`/`VM:` prefixes; VM rows key the
full zvol name though they display the short tail) and
`open_alignment_survey` preloads it — the existing
`_sync_profile_combo()` then loads its saved declaration. Pool/Device
rows, no selection, and stale keys fall back to the first entry.
Survey… button tooltip + dataset-combo tooltip updated (test_action_
dispatch tuple assertion updated to match). Tests: five new
TestAlignmentSurveyDialog cases via a `_chain_view_with_selection`
fake; `_make_app` now names `_alignment_chain_view = None` (a mock
auto-attribute would fake a selection). Docs: gtk-gui.md Survey dialog
section + Actions row, python-modules.md alignment_dialogs section.
Nothing committed.


## 2026-11-02 (night) — Scrub Manager Scan Line cell drops the `scan:` label

User item: the scrub table's Scan Line cell repeated zpool's `scan:`
field label the column header already carries. One-line display-site
change in pools_page.refresh_scrub_table —
`info.scan_line.removeprefix("scan:").strip() or "—"` — ScrubInfo
keeps the raw record (scrub-engine diagnostic logs and
data-structures.md still quote it verbatim; only the first joined
segment ever carries the label, so removeprefix is precisely scoped).
One new test in test_scrub_page.py (prefix stripped; empty fallback
"—"). Header tooltip and gtk-gui.md wording stay accurate. Nothing
committed.


## 2026-11-02 (night) — Datasets-page Mount refusals made visible (lock fence)

User report: "Datasets page: Could not mount z22tb/zfsutilities" with a
stewie journal excerpt that showed only benign property queries. Root
cause (verified from the Oct 29 journal, the offsite session log, and
the lock-manager code): the offsite profile (temp -> z22tb, started
13:41:52, ran until 18:38) holds a w lock on the destination pool root
z22tb for every dataset it copies; the Mount click at 13:43:34 passed
pre-flight (canmount/mounted queries — exactly the journal's burst),
then zlm.locks("w", [z22tb/zfsutilities]) hit the pool-root lock
(hierarchical fence), raised RuntimeError, and on_datasets_mount
swallowed it — no dialog, nothing visible. The fence is correct and
stays; the invisibility was the defect. (The offsite transfer itself is
invisible in the sudo journal because the runner's bash children call
zfs directly as root.)

Fix, three layers, fence unchanged:
- zfs_lock_manager: check() local walk extracted to _check_local_walk;
  new public check_local() (local files only, never the remote/ssh
  branch — safe for GUI button sensitivity); _conflicting_lock_holders
  renamed public conflicting_lock_holders for refusal messages.
- dataset_actions: mount legs (_mount_dataset_targets and the four
  _mount_one_* helpers) now return None on success or a one-line reason
  string on refusal (WARN log lines byte-identical); on_datasets_mount
  collects reasons and shows one _warn_busy-style warning dialog naming
  the lock holder(s) (pid/script noise stays in the log line);
  already-mounted live state now refreshes the stale row instead of
  silently doing nothing; _offer_snapshot_parent_mounts warns too on a
  refused parent batch.
- datasets_page: update_ds_button_sensitivity probes
  zlm.check_local(name, "w") for unmounted filesystem rows (same loop
  as the canmount probe); _is_mountable takes a lock_fenced set and the
  Mount button gets a fence tooltip ("Held by a running operation
  (backup, offsite transfer, or send/receive)…"), mirroring the
  canmount=off precedent. Runtime acquisition stays the enforcing
  fence; the tooltip is advisory (locks can be taken any time).

Tests: TestMount dialog/refusal cases (holder text, exception fallback,
already-mounted refresh, mixed batch, canmount=off batch, parent-mount
failure), TestCheckLocal in the zlm suite (pool-root w blocks
descendant w; never contacts the remote authority),
TestLockFenceButtonSensitivity in the datasets-page suite; six
volume-helper tests adapted to the reason-or-None contract. Docs:
messages manual gains the previously-missing `WARN: cannot mount ...`
lock row plus dialog notes on two adjacent rows; gtk-gui.md Mount row
describes the fence; GLOSSARY gains a "dataset lock" entry. Nothing
committed.

## 2026-11-02 (evening) — Dashboard poll path: batch + SSH reuse (tweety journal quieting)

User named the standing tweety-journal todo and chose "both batching +
SSH reuse"; interval stays a user knob. Plan approved as presented.

- path_utils: new ssh_command(host, remote_cmd) — every Python-side
  root@host argv now carries ControlMaster=auto + ControlPath (private
  socket dir: XDG_RUNTIME_DIR/zfsutilities-ssh-mux, then
  /run/zfsutilities/ssh-mux, then uid-tagged temp; 0700, degrade to plain
  ssh when none creatable) + ControlPersist=600 (SSH_CONTROL_PERSIST).
  resolve_remote_bin/resolve_remote_version route through it; new
  remote_version_path() exposes the VERSION probe path.
- dashboard_page: batched probe — _remote_probe_script/_parse_probe_sections/
  _probe_remote_host emit delimited sections (version, zfs-version,
  pveversion, os-release, inxi, fence-only-when-TTL-expired) in ONE ssh
  round-trip per remote host per refresh. _get_host_version/_zfs_version/
  os_info take optional parsed sections (signatures unchanged; local hosts
  still run direct commands; local OS detection extracted to
  _get_local_os_info, remote precedence in _os_info_from_sections).
  _gather_remote_probes + _gather_dashboard_data wire the shared probe_map
  into _gather_config_section_data and the fence check
  (_fence_cache_expired; _compute_fence_failure_warning reads the probe's
  fence section, falls back to its own mux'd query otherwise).
- Tests: test_path_utils +TestSshCommand (mux argv, 0700 dir, no-dir
  fallback, unwritable None); test_dashboard_page — remote zfs-version/
  os-info/fence assertions moved to the batched shape (mux argv has
  options before root@host; output wrapped in _probe_output delimiters),
  +TestProbeRemoteHost (script sections, round-trip parse, failure→{},
  precedence, undelimited ignore), +TestGatherRemoteProbes,
  +TestGatherConfigSectionUsesProbes (no per-command ssh when probe_map
  passed), fence probe_map cases (avoid ssh, inactive, fallback, local
  peer ignores map), _get_host_version sections cases. NOTE: gather call
  sites pass sections POSITIONALLY — the suite's dict.get side_effect
  idiom rejects kwargs (one failure taught this).
- Suites: path_utils 35, dashboard 319, consumers (gui_infrastructure,
  profile_runner, schedule_page, command_builders, proxmox_enroll) 459 —
  all green; ruff clean; real single-node gather smoke green on dev host.
- Docs: gtk-gui.md Dashboard intro (one reused round-trip per remote
  host, no journal flooding); python-modules.md probe row + path_utils
  ssh_command/remote_version_path rows + mux intro; GLOSSARY "SSH
  connection reuse (ControlMaster)" entry. Nothing committed.
- Post-deploy verification pending (user deploys): read-only journalctl
  sample on tweety with Dashboard open on stewie — expect ≤1 root login
  per 10-min persist window (was 3 per tick).

## Development-cycle wrap-up (2026-11-02 late, pub2 lane)

Seven-step wrap-up over everything since 0.137.0 (merge state 6cfbc9d):
the committed a08a7af (dashboard-suite import pairing) plus the working
tree (guest-probe argv fix, reapply-holds idempotence, ladder sizing,
Survey preload, `scan:` strip, mount-refusal visibility, batched probe +
SSH reuse, docs/GLOSSARY).

- Steps 1/4 (PREEXISTING resolution) skipped by their own precondition —
  pub-main-only, this is the pub2 lane. 4 entries remain in the lane's
  PREEXISTING.md.
- Step 2: ruff check clean repo-wide. ruff format found two pre-existing
  nits in files released with 0.137.0 (conftest.py backslash-join,
  test_pools_page.py missing blank line) — fixed as trivial. shellcheck
  clean over the documented set. Manual review of every changed product
  file clean: the moved inxi-split regex kept its original comment (no new
  regex this cycle); the new `((counter++))` in zfsreapplyholds verified
  safe in all call contexts (both strict callers guard with `||`/`if !`,
  the GUI payload is `bash -c` with no set -e).
- Step 3: coverage map verified per feature; one missing test added —
  TestGatherDashboardData.test_gather_shares_batched_probe_with_config_
  section pins the gather wiring (probe_map + node_cfg into the config
  gather and fence check), red-proofed by dropping the call-site args.
  No obsolete or incorrect tests found.
- Step 5: docs matched the code 1:1 (messages rows, gtk-gui, python-
  modules, charting, data-structures, installation mirror procedure,
  commands, integrated-testing, testing). Nine stale testing.md suite
  rows updated for this cycle's new coverage; GLOSSARY pending-list
  additions left as user edits. docs-integrity 23 passed; mkdocs rebuilt
  rc 0 (standing MkDocs-2.0/Material nag only).
- Step 6: full no-soak gate green — 108 suites, 6087 passed, 0 failed,
  18 python environment-preflight skips; the recorded profile_runner
  cancel-deadline flake did not appear. Log: /tmp/zfs-run-pub2-wrapup.log.
- Step 7: codebase frozen. Nothing committed — the tree awaits the user's
  commit cue.

## Release 0.138.0 prep (pub2 lane, user-directed steps 8-10)

- Step 8: VERSION → 0.138.0; changelog section written (Added / Fixed /
  Changed / Tests / Documentation, house style, no test counts); mkdocs
  rebuilt clean; docs integrity 23. Final with-soak gate round 1: 1
  failure = the recorded profile_runner SIGTERM flake (standalone
  110/110 in ~4 s — load-timing, not a defect; the diff touches no
  runner code). Fixed with pub's known resolution (post-SIGTERM
  proc.wait 15→60 s in the test) and the PREEXISTING entry removed
  (3 entries remain). Round 2 GREEN: 108 suites, 6094 passed, 0 failed,
  soaks exercised, 18 standing preflight skips
  (log /tmp/zfs-run-pub2-wrapup-soak2.log).
- Step 9: freeze held — only this notes entry afterwards.
- Step 10: staged and committed (hash in the turn report; same-version
  lane rule: pub3 already carries its own 0.138.0 commit, both ride the
  combined release per the 0.137.0 precedent).

(pub3 lane history block, unioned at the 0.138.0 merge — pruned at the
next release prune per the cycle rule.)

## Backup-page follow-ups: keys tooltips, pull-table sizing, tooltip flicker (2026-11-02, pub3 lane)

User-reported against the 0.137.0 tooltip/table work; three items.

- ZFS keys source/dest: the ENTRIES carried good tooltips but the LABELS
  had none, so hovering a label fell through to the Advanced expander's
  generic tooltip. Fixed: both labels now carry their field's tooltip
  (one string per field, set on label and entry; labels stored on app as
  backup_zfs_keys_source_lbl/_dest_lbl). The add_var_row contract
  (tooltip on BOTH label and widget) is now followed here too.
- Pull Steps table showed 6 of 11 rows: the Backup page was missed by the
  2026-10-31 natural-tables sweep — no NATURAL vscroll policy on the page
  viewport and both EditableListViews packed expanding. Fixed with the
  schedule/offsite idiom (NATURAL policy + non-expanding packs). New
  realized check tests/python/backup_realized_check.py (+ pytest wrapper,
  manifest entry, testing.md row): 11 pull rows in a 700x560 window stay
  fully visible, table does not scroll internally, page scrollbar carries
  the overflow. Red-proofed: with both hunks reverted the check fails
  ("pull table crushed: 71px < 254px").
- Post-Backup tooltip flicker ("Prune snapshots"/"Run post-backup
  command", window at desktop bottom): NOT reproduced app-side after an
  extensive probe campaign (scripts kept in /tmp/gtk3-tooltip-probe/):
  bare widgets, page-viewport containers, the real ZFSUtilitiesWindow
  build, Xvfb + bare/Xvfb+Muffin/live display, window bottom at the
  screen/workarea edge, a 2-px-step 44-px borderline sweep across the
  flip boundary, 20 Hz pointer jitter, and input-transparent custom
  tooltip windows. In every configuration the tooltip window maps once
  and never unmaps (verified via map/unmap event counters on custom
  windows and xwininfo presence sampling). Measurable but benign: GTK
  re-fires query-tooltip rapidly under motion (up to ~50 fires) without
  any unmap. User facts gathered: panel always shown, tooltip "vanishes
  repeatedly". Conclusion: the hide/show loop lives in the live-session
  layer (physical high-rate pointer and/or compositor interaction), not
  in this repo's code. No code change shipped for this item; next step
  offered: a live-session probe of the running instance with the user's
  explicit go-ahead (needs the real pointer), or a set-text-once
  query-tooltip handler as a churn mitigation if the user wants one.
- Probing per user instruction happens under Xvfb only — never on the
  live session display (the real-display probes above preceded that
  instruction; the pointer was restored each time).

## 2026-11-02 (later) — Performance rolling charts: continuous sampling, X ticks, doubled height, matplotlib prerequisite

User findings from the 2026-11-01 19:29 stewie screenshot (pub repo copy),
all four addressed on the pub3 lane:

- Straight lines: the Performance timer only sampled while its tab was
  visible (zfsutilities_gui `_start_stop_memory_timer`), so the deque
  held samples hours apart and the time-proportional polyline drew
  straight interpolation across the dark periods. Per user decision the
  fix is CONTINUOUS sampling, not gap breaks: `_ensure_memory_timer`
  arms the timer for the GUI's lifetime, `on_memory_timer_tick`
  (memory_page) samples the charts on every tick (Alignment view still
  refreshes only while visible), and switching to the page still
  refreshes the visible view once. Post-stall guard kept per the user's
  "Option 1": a gap > max(60 s, 3x refresh interval) re-baselines rates
  ("—") and the rate charts skip the point; None values now append None
  (dropped per-series) instead of a drawn zero.
- X ticks: grammar extracted to `charting.rolling_tick_count` (2/3/5);
  the Cairo fallback now draws tick marks + intermediate age labels via
  `_x_tick_layout` (edge-aligned ends, collision thinning by measured
  text widths). Verified visually under both renderers.
- "New and improved charts": the screenshot shows the CAIRO FALLBACK —
  stewie's root GUI cannot import matplotlib. Answer + user decision:
  python3-matplotlib promoted to a required GUI prerequisite in
  check-prerequisites, so installers and the upgrade prereq gate offer
  the apt package; on already-installed hosts the next upgrade's gate
  will offer it (or one manual apt command).
- Heights doubled: `charting.ROLLING_CHART_HEIGHT = 220` shared by both
  renderers and all five rolling charts.

New realized check tests/python/rolling_realized_check.py +
test_rolling_realized.py (private Xvfb child; both renderers; locks
height/tick grammar/stall re-baseline; screenshot to /tmp). Suites
touched: test_charting, test_memory_page, test_zfsutilities_gui,
test_alignment_page (dispatcher fixture now sets the stack page),
test-check-prerequisites (matplotlib required). Docs: gtk-gui.md
Performance section, charting.md rollout+deployment, Prerequisites.md
(matplotlib moved to System Prerequisites), testing.md suite rows,
data-structures.md refresh_seconds wording. Full gate green after the
one fixture fix (4474 python tests + bash suites). Uncommitted; release
prune session owns the other uncommitted files.

## 2026-11-02 (night) — R-08 promoted: encrypted-aware boot verification (repair plan 027)

User promoted R-08; plan approved and executed in one session
(`tests/integrated/repair-plans/027-encrypted-aware-boot-verification.md`).

- Three-verdict protocol: `export-iscsi-state --check` exits 0/3/1 (match /
  all-drift-keys-pending / other). Attribution in `report_state_drift`
  (missing-live backstore/LUN/grant lines only; suspects carried as
  `KEYSUSPECT:` lines, internal, filtered from output); the keystatus probe
  is deliberately in BASH main — the suite mocks zfs as a shell function a
  python subprocess would bypass. All `unavailable` → WARN summary + exit 3;
  available/"-"/unreadable → FAILED. Drop-in journals
  `post-restore verification PENDING — encrypted LUN(s) await key load …`
  on 3; old wrappers map 3 to FAILED (conservative skew, never false OK).
- j15 S1/S1c/S2/S5a now expect PENDING; `itf_boot_journal_verdict` gained
  the `pending` mode (lab-stages parser fixture added); j16 unchanged
  (verdict-word agnostic; keys loaded there → FAILED by design).
- Gotchas hit: mock fixtures join backstore lines with embedded `\n`
  (a missing separator merges lines and the backstore never enters the
  map — the fail-closed rc-1 was the symptom); `log_msg` writes to STDERR,
  so --check verdict assertions must capture `2>&1` like the drop-in does.
- End-user note: the user's own "Corrected exercise sequence" oracle still
  says FAILED — user-owned file, flagged for their one-word update. First
  live exercise = the still-pending controlled stewie reboot, after this
  ships + deploys. j15 lab rerun on user cue only (ITF rationing).

## Development-cycle wrap-up (2026-11-02, pub3 lane)

- Seven-step wrap-up over everything since the 0.137.0 release merge
  (6cfbc9d): commit a08a7af (dashboard/gui_helpers import pairing) plus
  the working tree (backup-page follow-ups, Performance rolling charts,
  R-08 / repair-plan 027, enclosure zero-rate refusal, README
  screenshots, GLOSSARY).
- Steps 1/4 skipped by their own precondition (pub-main-only; the lane's
  PREEXISTING.md read before reporting — 3 entries, none actionable in
  this lane).
- Step 2: ruff check + format and shellcheck -S warning over the
  documented set all clean. Two ruff-format nits that rode in with the
  0.137.0 release merge (conftest.py backslash continuation,
  test_pools_page.py missing blank line) fixed by the formatter itself.
  No coding-policies violations in the manual diff review (zero-rate
  mirrors, plan-027 exit protocol, GUI diffs, docs).
- Step 3: coverage map of every new behavior — zero-rate refusal at all
  four grammar mirrors, continuous sampling / tick dispatch /
  alignment-visibility gating, stall re-baseline, None-not-zero appends,
  tick grammar + doubled height (unit + realized, both renderers),
  keys-label tooltips, pull-table natural sizing (realized), the
  --check verdict matrix, the journey parser's pending mode, the
  required-matplotlib failure — all covered behavior-level. One gap
  fenced: test-switch-version's drop-in design test now requires the
  rc-3 PENDING branch and the FAILED fallback; red-proofed by removing
  the branch (exactly that test failed) and restoring the drop-in
  md5-identical. Obsolete tests had already been replaced by the cycle
  (matplotlib warn→required-fail, memory-timer semantics). Affected
  suites green during iteration.
- Step 5: docs integrity green; mkdocs build clean (standing
  MkDocs-2.0/Material deprecation warning only — the mkdocs<2 pin
  stance). One stale messages/index.md row removed: the old optional
  matplotlib warn line no longer exists in check-prerequisites (the
  generic required-module ✗ row covers the new failure).
- Step 6: full no-soak gate green via tests/run-tests (0 failures; the
  standing 18 dev-host python environment-preflight skips; over-budget
  timing advisory only).
- Step 7: codebase frozen. The wrap-up itself touched exactly: the two
  format-nit files, tests/test-switch-version (PENDING fence),
  docs/docs/messages/index.md (stale row), and this notes entry.
  Nothing committed — tree awaits the user's commit cue.

## Release 0.138.0 prep (pub3 lane, user-directed steps 8-10)

- VERSION bumped to 0.138.0; changelog section written (Added: R-08
  encrypted-aware boot verdict, rolling-chart X ticks + doubled height;
  Fixed: Backup table crushing, straight-line interpolation; Changed:
  required matplotlib, zero-rate refusal, --check exit contract; Tests;
  Documentation). Site rebuilt clean (standing MkDocs-2.0 warning only).
- Final full gate WITH soaks green via tests/run-tests --with-soak
  (rc=0, all suites passed, soak suites exercised, zero failures).
- Frozen at step 9; commit per step 10 (hash recorded in git).

## Restore destination rename freedom (2026-11-03, pub2 lane)

- User request: retire the "destination must end with a suffix of the
  source path" refusal (hit live on stewie restoring
  z22tb/temp/machinebackup -> temp/machinebackupxxx); mapped dest stays
  the default.
- Constraint lived only in compute_restore_params (restore_runner.py);
  the bash engine already handles a full strip (remove_leading_qualifiers
  returns "" and every consumer concatenates destfs+restorefs with an
  empty-restorfs guard), so the fix is Python-only: suffix mapping stays
  primary, and a non-suffix dest falls back to (all components stripped,
  destfs = whole typed dest) — the source is received exactly as typed
  and descendants land under the new name. Old error text replaced by a
  non-empty-input guard. Auto-determine (pool-suffix) default untouched.
- on_restore_run's confirm dialog now notes the rename when the mapping
  strips the whole source path (manual dest only).
- Tests: rename fallback (the live pair), pool-root full-strip pin, empty
  input guard added; profile-runner no-common-prefix test flipped from
  raises to rename expectation. Docs: gtk-gui.md Restore Tab paragraph.
- Full no-soak gate green as user (0 failures; standing environment
  preflight skips incl. gi-gated GUI suites and the root/test-pools
  integration suite — no bash changes, so that suite's subject is
  unchanged). Nothing committed — awaits the user's cue.

## Disks inventory: SMART data only on physical rows (2026-11-04, pub2 lane)

- User item: wear/test percentage was repeating on partition rows; on plan
  review the user extended it — SMART data never pertains to partitions, so
  the SMART verdict column blanks on partition rows too ("information in
  the rows where it belongs").
- disk_inventory() no longer propagates parent smart_health/wear_percent
  to partitions (parent_health/parent_wear dicts removed); partitions get
  smart_health="" (blank cell, distinct from "n/a" = probe failed on a
  real device) and wear_percent=None. Physical-row probing unchanged
  (one smartctl call per SSD/NVMe still holds).
- refresh_disks_page(): partition rows render a blank Wear/Test cell (no
  wear %, no parent surface-test lookup — HDD test status keys on the
  disk's own path now). Column tooltips + gtk-gui.md table rows say
  physical-devices-only. Dashboard _format_disk_wear_warnings docstring
  reworded (behavior unchanged; its dedup test feeds fabricated rows).
- Tests: repository partition assertions flipped to blank/None; disks-page
  partition tests assert blank cells in both columns (SSD-wear and
  HDD-surface paths). Affected suites green; full gate pending/see below.

## Performance → Alignment: counted Refreshing indicator (2026-11-04, pub2 lane)

- User item: on the Blocksize Alignment view the "Refreshing" label next
  to the refresh spinner was effectively never shown, unlike Dashboard.
  Root cause: with the Alignment view visible, each timer tick runs TWO
  refreshes (always-on charts sampling + the alignment gather); each
  finish callback hid the shared label unconditionally, so the
  millisecond charts sample dropped it while the alignment gather
  (zpool status + disk survey + guest probes) was still running.
- Fix: `_show/_hide_memory_refreshing` are now reference-counted on
  `app._memory_refresh_inflight` (show on 0→1, hide only at 0;
  initialized in create_memory_page beside the pending flags) — the
  label now stays up until the last in-flight refresh finishes, the
  Dashboard contract under two concurrent users. alignment_page needed
  no change (it already drives the helpers).
- Companion (required by the counted design): refresh_memory_charts'
  worker had no exception guard — a raising collect_memory_sample would
  have stranded the pending flag AND the count (label stuck visible,
  charts auto-refresh dead until restart). Now mirrors the alignment
  worker: catch → log WARN → sample=None; _finish_refresh applies only
  non-None samples.
- Tests: helper test re-pinned to the counter; new — overlap semantics,
  tick-level regression (charts finish must not hide during the
  alignment gather), worker-failure un-stranding. gtk-gui.md Refresh
  control paragraph updated. Affected suites green (memory, alignment);
  full gate: 112 suites, 1 failure — order-dependent
  TestScheduleSavedState pair, verified pre-existing at HEAD (c4feb54)
  in a clean clone, recorded in PREEXISTING.md (non-fresh mock_gtk +
  real-GTK import via @patch under the conftest Xvfb).

## Development-cycle wrap-up (2026-11-05, pub2 lane, 0.139.0)

- Steps 1/4 skipped by precondition (pub-main-only; this is a lane).
  PREEXISTING: +1 new entry (100-column policy deviations across
  released pub-lane suites — assertion/fixture strings, out of scope
  here); 4 entries total in this lane's file.
- Standards pass: ruff check + format clean; shellcheck -S warning
  clean on all changed bash files (no new directives needed); 15 NEW
  over-100-column lines in zfs-diagnose-busy/test-zfs-diagnose-busy
  reflowed (prompts via the archive-vm/sever_prompt += pattern,
  fixtures byte-identically, test_fail reasons via a local var); the
  934-line .t9debug scratch copy of the busy suite deleted (superseded,
  nothing unique). Policies otherwise conformant (sourced-lib laws,
  no set line, log_msg priorities, no hardcoded hosts in product code).
- Test review: bottom-of-file list verified complete in the busy suite
  (27/27 run); gap fills added — restore confirm-dialog rename-note
  pair in test_restore_page (TestRestoreRunDialog) and a clone-vm
  shape audit for the 4 busy-resolver cleanup sites (suite style).
  delsnap suite's two destroy assertions strengthened to file markers
  during the campaign were kept. All affected suites green solo.
- Docs: modules.md iscsi-lib section lists the three new helpers +
  resolver sourcing; python-modules.md disk_inventory and
  compute_restore_params rows updated; GLOSSARY +4 (backstore,
  deferred destruction, hold tag, resume token — mount namespace was
  already added by the campaign); docs integrity green; mkdocs rc 0
  (known MkDocs-2.0/Material banner only).
- Full no-soak gate (background): all suites passed, python zero
  failures (standing 22 env-gated e2e skips; the order-dependent
  schedule pair did not fire). Codebase frozen at that point.
- 0.139.0: VERSION bumped, changelog section written (busy resolver,
  iscsi-lib helpers, restore rename freedom, SMART physical-only,
  counted Refreshing indicator).
- With-soak gate run 1: the pre-existing order-dependent
  TestScheduleSavedState pair FIRED ("set_vscroll_policy called 2
  times") — fixed in-step per the entry's own direction: the class's
  two build tests now import fresh via `import_gui_fresh` with
  `patch.object` on the freshly imported module (a class-wide fresh
  import was tried first and REVERTED — it diverges from the
  string-target `@patch` decorators of the three tab-switch tests,
  which then called the real gui_helpers `set_button_markup_red`
  against mock Gtk and died on `isinstance(MagicMock)`). Red-proof
  (single-file stash + a pollute-then-test pair): pre-fix reproduces
  "Called 2 times" deterministically; post-fix single test, single
  class, whole file, and the polluted pair all pass. PREEXISTING entry
  retired (3 remain). Final with-soak gate rerun green before the
  commit; release/publish/deploy on the user's cue. Lane merge into
  pub main will union this 0.139.0 section with pub's (established
  same-version lane pattern).

*(lane history block, unioned at the 0.139.0 pub3-lane merge — pruned
at the next release prune)*

## Dataset-action gate removal (pub3, 2026-11-04)

- User directive: eliminate the GUI-global "a dataset action is already
  running" gate entirely — dataset-level zfs locking (already in place)
  is the fence; no pool-scoped replacement gate was wanted.
- Design shipped: `DatasetActionRunners` tracker in python/runner_factory.py
  hands each dataset action its own BackupRunner (label "Dataset action"),
  auto-dropping a runner when its completion callback doesn't restart it
  (migrate create→enroll chains keep theirs). No conflict logic in the
  tracker — `zlm` decides.
- All 17 gate sites converted (dataset_actions, datasets_page sever,
  disk_actions wipe, pool_create_wizard, pool_growth x5, pool_migrate,
  profile_dialogs rewrite/apply, proxmox/iscsi enrollment). Handler-level
  zlm acquires now try/except into WARNs that name blocking holders
  (growth/create/profile previously raised into the GTK callback as an
  invisible traceback — fixed as part of this). Enrollments take a w lock
  on the pool root; on conflict they skip with the manual-steps INFO.
- Window wiring: `app.dataset_actions` replaces `app.dataset_runner`;
  `_all_runners` merges tracked runners; Dashboard rows use
  `runner:dataset:<id>` task keys with cancel via the tracker; schedule
  `_interactive_runner_active` consults the tracker. Disks-page buttons
  lost the runner_busy branch entirely.
- conftest now isolates ZFSLOCK_DIR alongside ZFSUTILITIES_LOCK_DIR —
  previously zfs_lock_manager bound the real /run/lock dir in tests, so
  any unmocked zlm.acquire ran as dan against root-owned paths.
- Tests: new test_runner_factory (tracker lifecycle, helper WARN,
  format_lock_holders); 13 suites updated (busy-gate tests became
  lock-conflict refusal tests + runs-while-busy tests; fake apps expose
  `dataset_actions`). All affected suites green standalone.
- Docs updated: gtk-gui.md (gate wording gone), messages/index.md rows,
  concurrency-collisions.md GUI bullet, GLOSSARY dataset-action entry.
  docs/site NOT rebuilt yet (wrap-up item).
- Found + filed in PREEXISTING.md: 12 order-dependent schedule-page
  failures when six suites share one pytest process (reproduces on clean
  c4feb54 tree; xdist does not reproduce).
- Gate-chase addendum (same day): first two full gates failed 6 python
  tests (e2e BackupRunnerMechanics + one NoPool scenario; 60s watchdog,
  no io dispatch). Root cause chain, verified by forced-order pair runs
  on BOTH trees: (1) latent pre-existing class — a suite importing
  backup_runner inside a module-level mock_gtk() caches a mock-bound GLib
  for the worker's life (reproduced on clean c4feb54 with
  `pytest test_runner_factory.py test_offsite_e2e.py`); (2) my change
  ACTIVATED it gate-wide — `from runner_factory import ...` added to nine
  handler modules made every mock-collected handler suite transitively
  import backup_runner BEFORE the e2e suites' real collection import.
  Fix (structural): RunnerFactory.create imports BackupRunner lazily
  (comment in runner_factory.py explains), so no product module imports
  backup_runner at module level at all; test_runner_factory now imports
  backup_runner real via import_or_skip_gi (manifest line added) and
  needs no mock_gtk. Forced-order pair now green in 1.7s.
- conftest also gained a per-test dataset-lock reset (leaked live-PID
  lock files from tests that never finish their fake runner poisoned
  later real zlm acquisitions in the same worker — hit by the enrollment
  offer tests) and ZFSLOCK_DIR isolation alongside ZFSUTILITIES_LOCK_DIR.
- Final full gate GREEN via tests/run-tests ("All test suites passed!").
  One earlier gate saw a one-off test_file_locking 300s multiprocessing
  handshake timeout under load; standalone and the final gate green.

## 2026-11-09 (pub3): Repair Mount Order — cover-lift must be exact-layer umount

- Stewie incident (deployed 0.138.0): Repair Mount Order FATAL
  "cannot unmount fivebays/threeamigos/proxmox/Rocky: its mount is
  covered by fivebays, which could not be unmounted: cannot unmount
  '/fivebays/zfsutilities': no such pool or dataset". Mount table read
  pre-plan-mode: fivebays pool root is the LAST zfs mount — it covers
  all 8 shadowed children (the Dashboard warnings).
- Root cause, source-anchored to OpenZFS 2.4.4 (stewie runs
  zfs-2.4.4-pve1): `zfs unmount <name>` is RECURSIVE —
  unshare_unmount() → zfs_unmountall() → changelist_prefix() unmounts
  the fs plus every mounted descendant and aborts at the first failure;
  a shadowed descendant's path can't resolve → umount2 ENOENT →
  EZFS_NOENT, rendered "no such pool or dataset". So lifting the cover
  by name could never work, and even on success would cascade-unmount
  descendants it was never asked to touch.
- Fix (python/dataset_actions.py): `_lift_and_unmount` detaches covers
  with `sudo umount <mountpoint>` (exact layer, no recursion; busy gate
  unchanged; non-path mountpoints like legacy are skipped with a WARN);
  `_recover_orphaned_mount`'s restore loop got the same exact-layer
  umount. Plan members are still zfs-unmounted by name, deepest-first —
  recursion is a no-op there because descendants are unmounted first.
- Tests: four lift-flow argv assertions updated to the umount lift;
  orphan-restore test updated; NEW regression test reproducing the
  production topology (pool root covers two shadowed members; asserts
  lift == `sudo umount /tank`, never `zfs unmount tank`, repair
  completes parents-first); NEW guard test for unusable-mountpoint
  candidates. Suite 119/119.
- Docs: gtk-gui.md unreachable-mounts note +one sentence (plain umount,
  why); GLOSSARY.md + "shadowed mount" entry; messages manual + the new
  skip WARN row.
- Full gate: 110 bash suites green; python suite 4601/4602 — the one
  failure is the KNOWN order-dependent schedule flake (TestScheduleSavedState
  viewport test, set_vscroll_policy 2× shared-mock drift), now also seen
  under xdist after worker-grouping shifted; standalone 82/82 green, no
  coupling to changed code. PREEXISTING.md entry updated with the xdist
  manifestation.
- End-user note: stewie's 8 shadowed mounts persist until the fixed
  repair runs; after deploy, rerun Repair Mount Order (a reboot would
  also restore order — the failed run already persisted its canmount=on
  fixes before aborting).

## 2026-11-09 (pub3, later): CI red two days — fork-of-worker deadlock in test_file_locking

- Scheduled `tests` workflow on origin main failed 11-08 AND 11-09, one
  failure each: TestSharedLocksAllowConcurrentReaders handshake
  queue.get(300s) → Empty (5 of 7 run-minutes burned per run). SAME head
  commit f1b5495 was GREEN on 11-07 → GitHub's ubuntu-26 image drifted
  (cairo/gi-cairo apt state changed), not our code. a8263d2's MP_FORK
  pin (py3.14 forkserver pickling) did not cover the real hazard.
- Mechanism: the lock holder was a multiprocessing fork of the
  pytest-xdist worker; a forked child of a loaded worker (GLib/GTK state
  from GUI suites) can deadlock in inherited locks before its first
  queue.put(). Same class as the one-off dev-host hang noted 2026-11-05.
- Fix: lock holders are now fresh interpreters — new helper
  tests/python/lock_child.py (modes flock / profile-hold / history-add;
  follows the alignment_realized_check.py helper convention) with
  marker-file handshakes. Converted: test_file_locking (both
  cross-process tests, shared _child_holding_flock contextmanager, early
  child-exit detection — dead children now fail in ~0s, not 300s),
  test_profile_runner_concurrency (acquire-waits; child keeps the 0.5s
  unconditional hold so the parent's blocked acquire still overlaps),
  test_backup_history (4 concurrent history-add children, rc asserted).
  test_profile_integration left as-is (module-level worker + explicit
  lock-wait sync, passing).
- Three suites 55/55 standalone; full gate GREEN (111 suites). Ruff clean.
- Merge note for the next lane merge: pub3's test_file_locking predates
  main's MP_FORK pin (a8263d2), and pub3 also rewrote
  test_profile_runner_concurrency/test_backup_history which main pinned
  — all three conflict; resolution = pub3's subprocess versions.
- CI turns green only after lane merge + push to origin main (owner cue;
  git mutations need explicit confirmation).

## 2026-11-09 (pub3): 0.139.0 wrap-up

- Review-pass finds, both fixed in-task and red-proofed:
  - Enrollment decline leaked the pool-root w lock (iscsi + proxmox
    offers took it before the dialog; answering No returned without
    releasing — live GUI pid, so never reaped). Release added to both
    decline paths; decline tests now assert release with the acquired id.
  - Order-dependent schedule-suite failures fixed at the root (the
    PREEXISTING entry is pruned): test_schedule_page classes rebased on
    _FreshSchedulePageTestCase, whose setUp imports a FRESH schedule_page
    via import_gui_fresh inside its own mock_gtk() — unittest applies
    @patch decorators after setUp, so every string-target patch still
    resolves against the fresh module (pub2's patch.object conversion was
    not needed). Six-suite one-process combo green (was 12 failures);
    both full gates green with no flake under xdist.
- Docs: concurrency-collisions section 9 still claimed Backup/Offsite/
  Restore cross-blocking and named the removed dataset_runner — rewritten
  to the no-cross-gate reality; messages manual backtick row repaired.
- Gates: no-soak 112 suites green; with-soak 112 suites green (python
  suite passed in full both times, 22 env-preflight skips only).
- VERSION 0.139.0, changelog section written, docs/site rebuilt twice
  (before and after the changelog).
- Pre-existing issues: 1 addressed this turn (order-dependent schedule
  failures); PREEXISTING.md now holds 1 entry (flat mock listing).

## 2026-11-10 (pub3): j24 — two-node uninstall/reinstall with live LUNs

- The itf-coverage gap row "Uninstall/reinstall with live LUNs" was
  named by the user (the uninstall-intent report it waited for); built
  j24-two-node-uninstall-reinstall (composes the bare j05 lab): intent
  dry-runs on EACH host (interactive menu + peer question + confirm,
  zero mutation), real `--purge --all-nodes --yes` with per-host clean
  scans while the site survives byte-for-byte (pools, targets, both
  saveconfig hashes, pool-resident iscsi-state.json, session, by-path
  device, VM 101 scsi line, PVE patch, 1-KiB marker through the LUN),
  reinstall over the live tree (recurrence fence keeps the live IQN
  prefix; targets found existing; wiring + fence units back), then
  healthy fence tick, show-lun-map resolves the surviving LUN, clean
  safe-iscsi-save, and a second disk through the reinstalled product
  with the marker still matching. GREEN: run-20261110-023946
  (54 pass/0 fail/8 info after 2 red iterations + 1 lab-clone run).
- F-049 (verified): the interactive uninstall menu was UNANSWERABLE
  everywhere — the 1/2/c read was split across two quoted args, bash
  parsed the second as a variable name and aborted rc 1 before any
  choice; --yes paths (j02, unit suites) never reach the menu. Fixed
  (menu_prompt string ahead of the read); test-uninstall-zfsutilities
  green; the green j24 run walked the menu on both hosts.
- Journey gotchas fixed en route: PVE VM-config disk lines carry
  `,format=raw,...` options after the device (strip with cut -d, -f1);
  show-lun-map prints target/LUN/device rows with NO zvol-name column;
  the "targets will NOT be touched" sentence prints only in the
  interactive confirmation — a --yes transcript legitimately omits it.
- Docs: itf-coverage row filled + gap row removed; journeys README
  Current-set row; integrated-testing two-node bullet; GLOSSARY gained
  "recurrence fence". Driver test lists j24 (test-itf-driver 60/60).

## 2026-11-10 (pub3): j25 — two-node interrupted upgrade with keys pending

- The LAST itf-coverage gap row (named by the user). Built
  j25-two-node-interrupted-upgrade-keys: composes the j05 lab with
  --encrypted-keys, baselines the healthy site (1-KiB markers through
  BOTH LUNs, keystatus available, --check green, sha256 baselines over
  both saveconfigs + the pool-resident map), injects the shared per-host
  mods, reboots storage keys-absent (journal PENDING oracle; session
  re-login unaided; plain LUN serving; encrypted link classified), then
  j12's injections at two-node scale with the fence timer parked:
  X1 SIGTERM at the scan marker, X2 SIGKILL at the local version-dir
  mkdir, X3 SIGKILL during the REMOTE sync (the two-node-specific leg,
  classified absent/partial/complete). Recovery re-run with keys still
  pending repairs both hosts (manifest verifies via sha256sum -c);
  activation on both hosts leaves the posture byte-identical (--check
  rc 3, survival hashes, plain marker); one manual tick of the upgraded
  fence under keys pending (classified); up-to-date rerun; key ceremony
  rebuilds the encrypted LUN on the upgraded tree, both markers read
  back, --check green, healthy tick, clean save. GREEN:
  run-20261110-115506 (121 pass/0 fail/14 info; 2 red iterations
  first — see the gotchas). Guests destroyed at verdict.
- Premise design: NO stale-template rollback — the lab runs the tree
  under test, so the rollback would boot a keys-absent site with
  pre-encrypted-LUN tooling. New staging mode instead:
  itf_journey_stage_upgrade_env --relabel → serves the same tree
  re-labeled one patch newer (j23 pass 2's shape; the tag/VERSION
  mismatch WARN asserted honest), so interrupted deploys target
  versions/<v> dirs that exist on no host — j12's partial-dir oracles
  stay deterministic. Shared stages extracted (j23 converted + fresh
  re-proof run): itf_journey_stage_upgrade_relabel (also j23 pass 2's
  stage now), itf_journey_stage_two_node_mods (j23's per-host set),
  itf_lun_marker_write/verify (j24's marker, per-disk, rc-only verify).
  j23 re-proof GREEN: run-20261110-121228 (57 pass/0 fail/7 info,
  fresh clones — the shared relabel + mods stages ran inside its pass
  2, salvage hashes matched through the J_MOD_* exports; guests
  destroyed at verdict).
- Live truths from the green run: the SIGTERM EXIT trap closes the SSH
  control masters too (mux count 0 — pgrep '\[mux\]' is the detector;
  daemonized masters retitle their argv so ControlPersist does NOT
  match); X3 landed a genuine partial remote sync (compute held 235 of
  436 paths; rsync ships root-level files FIRST — compute-manifest was
  present while subtrees were missing, so file-count/missing-dir is the
  classification, never manifest-presence); the encrypted by-path link
  survives the keys-absent reboot as a STALE node and the fence tick
  reads rc 0 through it (R-02/R-03 blindness, classified not a finding);
  with the tick rc 0 no reconcile ran, so saveconfig kept the encrypted
  records and recover used the saveconfig index DIRECTLY (the
  map-fallback branch is j18 S16's coverage); activation's enable --now
  RESTARTS the parked fence timer — re-park after activation.
- Journey gotchas fixed en route: bash line-continuation after a
  variable assignment is VAR=val COMMAND, not concatenation — use +=
  (shellcheck misses it unless the string ends with ')' — hit TWICE,
  first in J_UPGRADE_ENV_EXPORTS lacking the trailing newline that
  j12's wrapper-concatenation contract needs); pgrep -f self-matches
  the probing shell (use [j] pattern); the driver suite invokes each
  test explicitly (new tests need invocation lines before test_summary
  — a missing line silently skips them).
- Docs: itf-coverage Release-upgrade two-node cell += j25, gap section
  now empty; integrated-testing j25 paragraph + j23 shared-stage note;
  journeys README Current-set row + the j25-needs-no-staleness note in
  the stale-template section; universe.tsv lifecycle comment j23-j25.
  test-itf-lab-stages grew 5 tests (relabel stage, relabel gates, mods
  stage, LUN markers); test-itf-driver lists j25 + 4 pre-existing
  shellcheck infos fixed with reasoned disables (SC2086 env-words,
  SC2016 child script, SC2012 fixture ls ×2).

## 2026-11-10 — 0.140.0 wrap-up (pub3)

- Wrap-up review of the j23/j24/j25 drop (three parallel deep reads +
  mechanical passes) found journeys asserting less than their step
  text claimed. Fixed and re-verified live, fresh runs of all three
  journeys green:
  - j23: the decline stage stamped its marker AFTER the declined run
    (vacuous find -newer) and pass 1 proved "deployed" with a
    MANIFEST the j05 install had already written — both oracles now
    ride the deployed MANIFEST's recorded mtime (equal = nothing
    re-deployed, changed = really deployed; the remote rsync carries
    the storage-side mtime, verified live).
  - j24: `is-enabled | grep -q enabled` also matched "disabled" (now
    an exact string test); the peer proof was two loose strings (now
    the binding summary line "Peer node:       <peer>" — it reads
    "(local only)" when the peer is declined); the dry-run untouched
    check never looked at the compute deployment; the state map's
    "intact" was a non-empty test (now sha256-baselined and
    byte-checked across the purge); show-lun-map was credited for
    reading the pool map it never reads (export-iscsi-state --check
    added post-reinstall; the second disk's LUN-1 slot now proven
    through the map).
  - j25: the post-activation posture was judged while the fence timer
    that activation had just restarted could still be ticking — the
    journal slice proves the tick fires the same second as activation
    (enable --now + elapsed OnBootSec fires immediately). Activation
    now re-parks and drains the tick before the wiring/posture
    checks, and the absent-link shape tolerates the tick's documented
    saveconfig re-save (F-042's healed shape; the pool map must stay
    byte-identical — _j25_posture takes saveconfig-may-drift).
- All three journeys select the loop role by the " (storage)" suffix
  (a compute hostname containing "storage" used to send every loop to
  the storage guest); _j2N_missing_markers hoisted into common.sh as
  itf_missing_markers; the mods stage refuses empty injection hashes
  and its pass text names the real file it modifies.
- Unit coverage for both product fixes (each was mock-blind):
  test-uninstall-zfsutilities drives the interactive menu through the
  REAL read builtin over here-string stdin (a mocked read cannot see
  a malformed prompt line — F-049's shape); the upgrade suite's ssh
  shim now models OpenSSH's stdin drain on the connection
  establishment leg, making the multi-host flow the F-048 regression
  test. Both red-proofed by temporarily reverting each product fix —
  exactly the new test fails — with the product files restored
  byte-identical afterwards. Red-run gotcha: take a subshell's status
  AFTER the assignment, never with `|| rc=$?` (errexit-ignored
  context; the failing read otherwise spins the menu loop forever —
  documented in testing.md's Tips).
- Suite audit: two never-invoked tests found and registered
  (zfsscruball's default STATEFILE; send-receive-holds'
  user-hold-blocks-destructive — the holds-before-destroy safety
  holds); a product-wide grep found no other malformed-read shapes.
- PREEXISTING += 5 entries: the printed remote activation command
  needs a login shell (product); upgrade's no-baseline state is never
  assigned, so a failed baseline capture dies "unbound variable"
  (product); j13 reads the 4-field guest record into three variables
  (harness); j05's lease re-acquire rewrites guest-j05-storage.txt
  instead of the role-named record (harness); over-100-column lines
  remain in common.sh and the older journeys (j15/j16/j17/j20).
