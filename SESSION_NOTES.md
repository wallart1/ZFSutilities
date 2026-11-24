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

(2026-11-10 release prune: the 0.140.0 cycle — the loop-mounted-zvol
unmount rewrite (device-keyed unmount, zlm fences, idempotent no-ops,
holder diagnostics; 2026-11-09 entry), the 0.139.0 lane-merge/j11/
wrap-up-rerun entry (committed at 0871a06), and the wrap-up additions
below — is committed in the 0.140.0 release commit; recoverable via
`git log`. Design and behavior live in docs/ (commands.md, modules.md,
python-modules.md, two-node.md, architecture.md, conventions.md,
coding-policies.md, gtk-gui.md, proxmox-integration.md, messages) and
GLOSSARY.md. The alignment out-data decode thread (pub3's, rode
0.139.0) is condensed to its live remainder below. NOTE: the two
older "lane history block" markers (0.138.0/0.139.0 pub2 merges) still
delimit accumulated cross-lane history whose boundaries are not
cleanly separable from interleaved pub-main entries — a dedicated
  SESSION_NOTES maintenance pass should remove them wholesale; left
  intact here rather than risk cutting pub-main's own history on a
  release commit.)

(2026-11-10 publication pass: 0.139.0 and 0.140.0 are committed,
pushed to origin main, tagged v0.140.0 (tip-tag precedent; 0.139.0
ships untagged inside the push, the standing untagged-intermediate
pattern), and released on GitHub. The dedicated maintenance pass
happened: the j23 journey entry, the 0.140.0 wrap-up entry, and
everything below the live-threads section — both accumulated
lane-history blocks and the 0.138.0-cycle entries — were removed
wholesale, recoverable via `git log`. Same pass: repair plans 026
and 027 pruned (both verified by the user-cued j16/j15 reruns of
2026-11-04); F-048/F-049 pruned from FINDINGS.md; R-08 pruned from
REQUIREMENTS.md; results/ run dirs cleared except F-047's evidence
run (one j11 dir stuck behind NFS silly-rename files held open from
another host — remove when free); the three ITF baseline templates
apt-upgraded in place via maintenance run
run-20261110-201017-template-apt, preserving the deliberately stale
0.118.0 storage product. Unresolved register rewritten in the user's
plan dir.)

(2026-11-12 publication pass: 0.141.0 is committed (the three-lane
release + merges + wrap-up `6a33526`), pushed to origin main, tagged
v0.141.0 (tip-tag precedent), and released on GitHub. Same pass:
F-047 and F-050 pruned from FINDINGS.md (both verified and shipped in
0.141.0 — the table is empty); the results/ run dirs cleared,
including the NFS-stuck j11 dir once it freed; REQUIREMENTS.md and
repair-plans/ carried nothing published to prune; the Unresolved
register rewritten in the user's plan dir; memory purged with backup.
The ITF template apt refresh was skipped at the user's request this
cycle — templates remain as refreshed 2026-11-10.)

(2026-11-17 publication pass: 0.142.0 is committed (pub 654d776 + the
release-gate wrap-up through 6042728, the three-lane merges 5b3c7bc /
a06f1bf, follow-up 14aa645), pushed to origin main (6a33526..6042728),
tagged v0.142.0, and released on GitHub. Same pass: the 0.142.0 thread
entries — pub's mint survey leg and release-gate wrap-up (binding
fences + export-stall recovery), pub2's partition-row pools,
scrub-pause verification, and the three docs rewrites
(integrated-testing, data-structures, architecture C4), pub3's
managed-pool scope, natural dialog sizing, and Detach gate — were
removed, recoverable via `git log`; the Alignment out-data live
remainder closed (proof confirmed 2026-11-12, evidence screenshot
gone). Published-entry pruning of repair-plans / FINDINGS / results /
REQUIREMENTS, the memory purge with backup, the ITF template apt
refresh (zfstestvm1, zfstestvm2), and the Unresolved register rewrite
in the user's plan dir rode the same pass.)

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

(2026-11-17 cycle prune: the 0.142.0 campaigns — concurrency collisions
(five fixes A-E), the campaign wrap-up pass, and the mint ITF template —
are committed as 654d776; their thread entries were removed. Design lives
in docs/ (concurrency-collisions, lock-manager, integrated-testing,
itf-coverage, data-structures) and the gotchas in agent memory
($$-in-subshell, process-substitution array appends, ScrubQueue's locked
constructor load, the mint initrd/provision-boot laws).)

- **J22 world enrichment — Phase 1 COMPLETE (2026-11-17).**
  The world axis is plumbed end to end with zero behavior change:
  sampler `--world`/`--world-seed` (closed list thin|lived-in|busy; seed
  defaults to the run seed), archive `world {variant, seed, digest}`
  (format stays 1; missing world = thin), replay refuses a conflicting
  explicit variant (the SW rule mirrored), `# world`/`# world-seed`
  lines in survey-select.out, `SURVEY_WORLD` global, a fail-fast
  select guard (non-thin refused before lab spend), the
  `itf_survey_stage_world` dispatcher (thin = the unchanged playground)
  with a variant+elapsed cost step. Contracts Phase 2 must keep: the
  digest hashes the canonical plan document `{"seed", "variant"}` (+
  later plan rows; thin's document never changes), and the select
  guard is the point to relax into the lived-in dispatch. Live gate:
  run-20261117-231334 green (158 steps, 0 fail) with the world steps
  present; it also refreshed the tracked survey-archive.json, whose
  universe was one gui-widget row stale from the 0.142.0 wrap-up
  (214→213; catalog changed after that cycle's reference run).

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
- **GUI Wayland-session support — parked (2026-11-14, user cue).** GTK3
  draws under either display protocol and the docs already promise it
  (README: "X11 or Wayland"), but the plumbing around the GUI is
  X11-shaped: run-completion notifications resolve the desktop user from
  the owner of the /tmp/.X11-unix socket when no override or SUDO_USER
  is present (python/notifications.py, python/docs_viewer.py,
  lib/desktop-launcher-lib.sh) — a Wayland-only session has no X
  socket, so that leg returns None and notifications are silently
  skipped; check-prerequisites gates on DISPLAY alone (the WARN text
  itself says "X11 or Wayland") and never checks WAYLAND_DISPLAY, so a
  session without XWayland warns spuriously; and main.py's
  xdotool/xwininfo window-visibility chain (_get_display_env →
  _has_visible_window) has no live caller today — Wayland offers no
  global window query, so revive-vs-remove lands with this item. The
  pkexec relaunch already preserves WAYLAND_DISPLAY, so launching is
  not the gap. Testing direction (user, 2026-11-14, verbatim): "We will
  support Wayland-based testing at some point. And, I do intend to take
  GUI testing further that we have so far." Headless Wayland compositors
  (Weston headless backend, wlroots compositors under
  WLR_BACKENDS=headless, cage) are the Xvfb analogs. The fence that
  carries over is private displays only — never the live session — not
  the X11 protocol.
- **J22 world enrichment, Phase 2 (lived-in, part 1) — COMPLETE
  (2026-11-18).** Guest time control (`itf_guest_time_freeze/set/restore`
  in guest-lib.sh; stateful forward-only fence after one deliberate
  rewind; restore from the dev host epoch; fence-timer masking on
  timer-bearing guests) + the deterministic ladder planner
  (`tests/integrated/survey/world.py`: rid-relative names, day-offsets
  pinned to the archive's staging ANCHOR — buckets follow the calendar,
  so the anchor is part of the plan identity and lives in the archive
  world object; digest = sha256 over {seed, variant, anchor-date, plan},
  thin's document unchanged from Phase 1) + `world-stage.sh` (guest-side
  plan interpreter; product-sourced zfssnapbuild naming with per-row
  name assertion; clone via snapname_timestamp; two real zfsdailybackup
  runs through the product's overrides mechanism redirecting
  send-receive at survey scratch) + survey-lib select/stage/teardown
  (world-seed/anchor parse, fence relax to thin|lived-in, digest guard
  at select and stage, walk over the union of ladder + dailybackup
  moments, post-restore verification against the plan, holds/clone/recv
  release before the playground destroys). Docs: developer guide world
  section, journeys README, GLOSSARY (clock walk; world variant
  rewritten). Live gate GREEN twice: run-20261118-023346 (fresh
  world via replayed two-node-free archive, single-node lab) and
  run-20261118-024359 (replay) — identical digest 875689885d1390ec,
  identical 40-snapshot world rid-normalized (creations within the 5s
  clock-set slack), ladder=33 holds=4 product_runs=2 recv=4, world
  staged in ~55-58s, residue clean, GUI 70 pass / 0 fail / 11 blocked.
  Defects the campaign surfaced and this phase fixed: j22's
  single-node lab branch never sourced common.sh (dead path until
  now); world-stage.sh must source the staged tree's zfssnapbuild
  directly (source_helper resolves to the installed deployment —
  0.118.0's copy dies under set -u); zfssnapbuild echoes the
  @-prefixed name; verify needs `zfs list -p` for epoch creations and
  must count the playground's base snapshot. Two-node j05 wiring
  flakes (site-keys, P2P first-connect) went to PREEXISTING.md; the
  systemctl mask refusal (the timer's unit file lives in
  /etc/systemd/system) became disable --now / enable --now.
- **J22 world enrichment, Phase 3 (lived-in, part 2) — COMPLETE
  (2026-11-18).** Config rows + CLI depth upgrades in survey-lib.sh +
  universe.tsv: pinned config `config_version` read from the enumerated
  tree via `_survey_config_version` (step-free helper — an itf_step
  inside `$( )` vanishes with the subshell; callers validate + report;
  fails closed without select); `itf_survey_stage_config_rows` after the
  clock walk (retention default+2 pools+`<offsite>`, one active
  send/receive step, one inactive pull step, offsite step with STRING
  includes/excludes; four inactive schedule profiles in the exact
  profile_manager schema; `ZFSUTILITIES_STATE_DIR` pinned to
  /root/survey-state). Depth: zfscleanup argcheck→deep (overrides
  dry-run over {POOL} — cleanup's pool loop `zpool list`s $1 and skips
  datasets); zfsdailybackup deep sends real prey via overrides
  (sourcefs={DS} destfs={DS2}-recv); bespoke recipes zfsresume
  (truncated stream + receive -s → token validation) and zfsdelallsnaps
  (own-label snapshot + offsite hold + clone → releaseholds; rc 1 is the
  honest clone-skip); five vm-disk rows argcheck→bespoke on VM 101
  scratch disks with an empty never-started survey VM 9101 where a
  second VM is needed; wrap gained depth-distribution info,
  -recv/-res/state-dir teardown, compute-side vm-disk convergence, 9101
  in the residue pattern. Universe depth shift: argcheck 17→10,
  bespoke 10→17, deep 33→33. Two defects the gate surfaced, both FIXED
  with regression tests: (1) world.py's offsite same-month partner was
  unconstrained — some (seed, anchor) corners landed under the 65d
  minage and the plan failed only at stage time, after the lab was
  cloned; the partner pick is now bounded to days ≥66 back, digest-
  preserving for every previously-valid plan (P2's 875689885d1390ec
  pinned by test); 120-corner sweep valid. (2) gui_probe's edit-cell op
  called CellRendererText.get_editable() — no such accessor (no C
  getter; property is readable) — the seeded Check Against rows turned
  a long-blocked item into a real edit and exposed it; fixed to
  get_property("editable"). Two more, both found by the two-node gate
  runs and FIXED with tests: (3) the bespoke dispatch looked up
  `survey_recipe_$command` verbatim, so DASH-named commands (clone-vm,
  new-vm-disk, remove-vm-disk) never dispatched their recipes — their
  past greens were vacuous (invoke "-" + rcs "-" + assert "-" through
  the generic path; old runs' `[bespoke/] - —` step text is the
  telltale); the lookup now maps dashes to underscores and the old
  remove-vm-disk recipe ran live for the first time in the final gate.
  (4) seven of my new universe rows carried an extra field (11 vs 10 —
  bash `read` glues the surplus onto the LAST column, so assert became
  "-<TAB>-"); raw-line column-count test added (parse_universe_tsv
  zip-pairs and never saw it). Plus (5): edit-cell/toggle-active used
  views[0] only — the Check Against page stacks four views and the
  editable cells live in the USER view; both ops now walk the views
  (same law as the 2026-11-11 composite fix). Live gate GREEN at last:
  run-20261123-132017 (two-node, seed p3gate2026, clean hosts after the
  user-directed red-lab sweep) — every selected item passed; config
  rows staged (schema v32, 2s), world 62s, ladder verified, GUI 74
  pass/1 blocked/0 fail incl. the checkagainst edit on a seeded row,
  vm-disk recipes (rename/attach/resize + the retro-activated
  remove-vm-disk) all green, depth distribution argcheck=6 bespoke=9
  deep=17, residue clean, green labs auto-destroyed at verdict.
  Earlier gate attempts (2026-11-18) were environment-hostile: j05 P2P
  race ×2 and a guest-agent boot starvation, one even on a clean host;
  the substance ran single-node meanwhile via the P2-precedent filtered
  archive (run-20261118-110522). Standing rule from the user
  2026-11-18: sweep red labs when their post-mortem is done (itf guest
  sweep --force --age 0 --apply) — accumulation was the aggravator.
  Plan-file adaptations (verified against code, disclosed in the
  approved plan): the deep retention row rides cli-zfscleanup
  (zfsretain is an undocumented sourced module); "past-due cron" doesn't
  exist in the product (cron_manager is forward-looking — seeded an
  ordinal weekday 6#1); zfssendoffsite CLI can't take ladder prey (step
  bodies assign sourcefs/destfs after overrides eval; site-specific by
  design) — its config prey lands on the GUI Offsite rows. Suites:
  test_survey_sample 39, test_survey_world 22, test-itf-survey-journey
  27/27, full suite green twice (final tree included); shellcheck
  warning+ clean.

(2026-11-23 cycle wrap-up: the three world-enrichment phases above,
both PREEXISTING resolutions — bounded SSH-probe retries in
install-two-node Step 4 and the j05 first-connection step (the
recorded two-node wiring races), plus the sample.py repo-root default —
and the campaign's docs/GLOSSARY updates are committed in the 0.143.0
release commit. The Phase-1..3 entries stay until the publication
prune. j05's retry and world-stage.sh verify live with the next
two-node gate run; the installer retry carries its transient-recovery
regression test in test-installer-flows.)

(pub2 lane history block, unioned at the 0.143.0 pub2-lane merge
(a0c7d61) — "uncommitted" in these entries means uncommitted in pub2
at the time of writing. Pruned at the next release prune.)

## 2026-11-16 (pub2) — Disks: pool names live on partition rows, not partitioned-disk rows

- User rule: on a disk with partitions the disk itself is never a pool
  member (partitions on one disk can belong to different pools), so the
  disk row must not name a pool; each partition row names the pool it
  belongs to. Matches the standing rows-carry-only-their-own-data law.
- Fix: `DiskInventoryCache._credit_backing_disks` deleted (it existed
  solely to copy partition members' pools onto the whole-disk row).
  Partition rows already resolved their own pools via `_pools_for_disk`;
  whole-disk members (a pool whose leaf names the disk itself) keep the
  name via the direct path match — that case never used the credit and
  is unchanged.
- Verified consequences: selected-pool teal tint still lands on
  whole-disk rows (partition members map to parent_path in
  `_highlight_pool_disks`); selecting a partitioned disk row now takes
  the existing no-pool branch (clears tints + pool selector), covered by
  the nonmember-selection test; wipe fence intact via
  `wipe_block_reason`'s same-disk sibling scan — refusal now names the
  partition; enclosure pools and pool-create eligibility compute
  membership independently.
- Tests: the two credit tests rewritten (disk-row assertions flipped to
  []), plus two `_selected_disk_is_wipeable` tests pinning the GUI fence
  for the blank-disk-row shape. Pools column tooltip reworded;
  gtk-gui.md Pools row + pane-sync paragraph updated.

## 2026-11-17 (pub2) — Scrub pause judged by pool state, not the zpool client (stewie incident)

- Incident (stewie, 0.141.0, zfs 2.4.4-pve1, 2026-11-16 12:01, profile
  root-backup-dailybackup2): `zpool scrub -p threeamigos` blocked ~43 s
  in-kernel (synchronous ioctl; scrub ~48% + backup starting). The 30 s
  subprocess timeout killed the client (TimeoutExpired surfaced 44 s after
  issue — the kill itself waited on the D-state ioctl), but the kernel
  completed the pause anyway ("paused since 12:01:57" vs WARN 12:01:58).
  pause_scrubs_for_pools trusted the exception: pool left out of the paused
  list → post-step resume never ran → scrub stranded paused at 47.98% until
  the user resumed it manually; the persisted queue never recorded the pause
  either. Session log:
  /var/log/zfsutilities/sessions/2026-11-16_12-00-01_backup_profile-root-backup-dailybackup2.log
- Fix: new `_transition_scrub_verified` helper — issue pause/resume with the
  30 s client bound, then poll zpool status for up to 120 s regardless of how
  the command returned; state confirms → success (honest VERB when the client
  timed out/failed); window expires → the one did-not-pause/resume WARN with
  raw status. All four call sites rewired (pause/resume wrappers used by GUI
  buttons + queue tick, and both coordinated for_pools paths).
  `_wait_for_scrub_state` is now attempt-bounded (timeout/interval) instead
  of wall-clock-bounded, so mocked-sleep tests can't hot-spin.
  start/stop deliberately unchanged: their outcomes self-heal via tick
  reconciliation, unlike pause/resume where a false negative strands state.
- Tests: wrapper success/failure tests reworked for the state poll; new
  timeout-but-confirmed cases (wrapper + coordinated, pause + resume — the
  incident, red-proofed), slow-flip case pinning the widened window (40
  non-matching polls > the old 25-attempt window). 126 pass in ~4 s.
- messages-manual scrub block restructured (started/stopped = command
  succeeded; paused/resumed = state-confirmed; new timeout-but-confirmed VERB
  row; coordinated "Failed to pause/resume" rows absorbed into the state
  WARN). daily-backup.md pause-scrubs section gained the state-judged bullet.

## 2026-11-17 (pub2) — integrated-testing.md writing-rules rewrite + full fact re-verification; ubuntu template joins the guard

- Re-verification method: every claim in the doc checked against the tree —
  five parallel claim-cluster verifications (upgrade journeys j10/j12/j19/
  j23/j25; recovery journeys j15–j18 incl. every S/M scenario; lab + two-node
  machinery; survey/e2e/framework suites; docs cross-links + FINDINGS/
  REQUIREMENTS/repair-plan ledgers, several via git history since published
  rows are pruned) plus first-hand reads of the driver, base/runlock/guest/
  template/report libs, site config, common.sh rerun staging.
- Fact fixes landing in the rewrite: j15 S1 oracle is PENDING+DRIFT (was
  "FAILED+DRIFT", pre-repair-027 wording); j12's SIGKILL fires on version-dir
  appearance, not the transcript marker (deliberate, j12:205-208); j25's
  printed activation commands are absolute paths (was "login-shell
  wrapped"); `itf vmimage build` added to the run-lock entry points and the
  loose `|| rc=$?` set; framework-tests section now lists all nine itf
  suites (survey-journey + watch were missing) and says all three template
  profiles; storage base named as home of BOTH Debian and ubuntu templates
  (intro + role-split bullet); test-pools callers corrected (j01/j05/j21
  direct; j04/j11/j20/j22 via the single-node lab); manual-steps claim
  scoped to dev-side setup (base-PVE prep lives in tests/integrated/README
  + site-config comments, verified by preflight); template freshness is a
  skip-with---force-pointer, clone reach "a minute or two"; FINDINGS/
  REQUIREMENTS legends aligned with the actual ledgers + one pruning note;
  fence-timer restart worded to j16 (asserts) vs j18 (restarts); j05 prereq
  failure nuance; watch named as tailing steps.tsv too. F-number/plan
  identifiers kept (verified via git history). Headings byte-identical;
  docs-integrity suite + clean mkdocs build green.
- Guard fix (user-approved): `ITF_UBUNTU_TEMPLATE_NAME` added to
  `_itf_template_names` (base-lib.sh) — the ubuntu probe template is now
  refusal-protected like storage/compute; test-itf-base-guard gained the
  ubuntu refusal case (destroy refused + refusal names the template, other
  two baselines still protected, clone exempt). Suite green.
- PREEXISTING: 2 entries resolved (stale two-node passage — fixed in the
  rewrite; ubuntu guard gap — fixed above); 3 filed (stale `sudo
  switch-version` transcript markers in j10/j12/j19/j23/j25 vs the
  absolute-path prints since 4b232a4; stale "FAILED+DRIFT" wording in
  journeys/README.md:187 + j18 header; tests/integrated/README.md profile
  count + run-lock entry-point staleness). 4 entries remain (incl. the
  snapshot-dialog tooltip full-run flake, which did NOT fire today).
- Full suite green at the end (all suites passed; log /tmp/zfs-run.log).

(pub3 lane history block, unioned at the 0.142.0 pub3-lane merge
(0493671) — "uncommitted" in these entries means uncommitted in pub3
at the time of writing. Pruned at the next release prune. Also at
this merge: pub3's PREEXISTING test-unarchive-vm flake entry retired
— pub's f23cc92 de-forked existence-probe fix verified in-tree
(archive-engine.sh/archive-vm/unarchive-vm + the coding-policies
idiom law); both recorded occurrences (pub3 Test 6 on 2026-11-16,
Test 25 in the with-soak gate) belong to the fixed fork-pair class.)

## 2026-11-16 (pub3) — Disks-page modal tables: natural sizing + scrollable windows

- User request (scope widened mid-turn to ALL Disks-page action buttons):
  every treeview including the ones in modal windows gets the universal
  treatment — natural growth up to 20 rows then scroll — and the window
  becomes scrollable.
- Both defects probe-verified under private Xvfb with the repo's own
  helpers (probe scripts deleted after use): (1) the dialog builders
  packed the capped scrolls expand=True, so a 6-row picker stretched to
  fill a 646px table window — the "expand stays on" comments
  overrode the main-page idiom; (2) create_scrolled_dialog left the
  viewport on the default MINIMUM vscroll policy, so a short dialog
  crushed content toward the capped windows' 60px floors instead of
  scrolling (NATURAL policy → vadj upper 484 > page 316, scrolls).
- Fix (all in-repo idioms, no new mechanisms):
  - gui_helpers.create_scrolled_dialog sets viewport
    vscroll_policy=NATURAL behind the dashboard-style hasattr guard —
    one change covers every scrolled modal incl. Wipe Labels.
  - Non-expanding packs: _build_disk_picker + _build_target_tree
    (pool_growth_dialogs), wizard _build_disks_page, the five growth
    dialogs' page-level packs, five migrate-dialog packs.
  - Manage Pool Profiles converted create_dialog →
    create_scrolled_dialog (size (700,500) kept) + non-expanding table;
    create_dialog import dropped from the module.
- Tests: NATURAL-policy assertion added to
  test_create_scrolled_dialog_returns_dialog_and_box;
  test_pool_profile_dialogs' nine create_dialog patch sites rewritten to
  the (dialog, MagicMock()) tuple shape (editor precedent); NEW
  tests/python/disks_dialogs_realized_check.py (child process, private
  Xvfb, mirrors backup_realized_check.py: 6-row picker hugs rows,
  30-row picker caps ~20 rows + scrolls inside, dialog window carries
  overflow, NATURAL policy asserted).
- REMAINING: none — completed in the follow-up turn: wrapper
  test_disks_dialogs_realized.py + requirements.manifest `gi` line;
  gtk-gui.md Disks-Tab intro paragraph (universal table rule + dialog
  windows scroll); affected suites green; FULL python suite green
  (skips = root-gated by design); ruff clean; probe scripts removed.
  Buttons 8/10-14 (Enroll, Wipe, SMART, Surface Test, Rate, Refresh)
  audited: no treeviews; Wipe benefits via the shared factory fix.
  Realized-check scratch dirs under /tmp (mkdtemp, no cleanup) follow
  the backup_realized_check convention.

## Managed-pool scope campaign (2026-11-16, pub3, uncommitted)

Policy: everywhere except the Pools-tab Pool Registry table, the GUI lists
and acts on managed pools ONLY (registered AND online; "online" = imported,
any health — DEGRADED counts, IMPORTABLE/OFFLINE do not). Unregistered pools
appear nowhere else and are never touched. Configs cannot be SAVED naming
unregistered/offline pools; stored profiles keep them but skip+WARN at run.

- Canonical helpers in feature_config.py: get_managed_pool_names,
  non_managed_pool_names, pool_name_from_endpoint (placeholder-prefixed
  endpoints like "<offsite>/dst" return None — the first cut missed that
  and skipped every offsite step), non_managed_endpoint_pools. Shared
  interactive gate: gui_helpers.refuse_non_managed_pool_endpoints (WARN per
  pool + dialog; early-exits before any zpool call when no endpoints).
- Display surfaces filtered: dashboard (health grid, tasks, scrub rows,
  identity warnings — unregistered names suppressed to counts, registered
  keep names), datasets roots, memory L2ARC/SLOG + enclosure Pools column
  (alignment via alignment_page._restrict_to_managed_pools on the worker
  thread), disks Pools column/topology/selector/enclosures (inventory cache
  keeps FULL membership), growth+migrate pickers (managed), create-wizard
  name collisions now include registry names.
- WIPE FENCE: unchanged full-membership wipe_block_reason is the fence;
  _selected_disk_is_wipeable docstring now states the filtered Pools cell
  must never be the gate (dedicated tests both sides).
- Scrub: refresh_scrub_table shows managed only (tick still gets FULL
  states); ScrubQueue(registered_names=callable) gates external adoption;
  scrub handlers refuse unregistered selections by name.
- Retention: prune list managed (fallback REMOVED — empty registry lists
  nothing; zfscleanup CLI keeps its own), live health shown per row,
  add-policy candidates managed, _on_ret_save save gate, prune runner
  defense-in-depth skip. _get_online_pool_names deleted (deprecated).
- Transfer pages: backup/offsite save+run gates (endpoints; <offsite>
  passes), restore run gate + managed auto-destination, checkagainst
  user-entry save gate + managed completion. Profile save gated in
  show_add_profile_dialog (_profile_pool_refs per tab type).
- profile_runner: _managed_pools (subprocess zpool list; fail-closed) +
  skip+WARN for backup/offsite steps, restore abort, retention pools,
  scrub never-queued; backup prune pairs restricted to steps that RAN.
- Test-side convention added in this campaign: MagicMock app/config
  fixtures now carry real registry dicts + mocked zfs_repository rows
  (dashboard tasks, datasets, disks, memory, alignment, retention, scrub,
  backup, restore, profile_runner MANAGED_FIXTURE_POOLS setUp patcher).
- Docs: gtk-gui.md (Pool scope section under Tabs + per-page notes),
  data-structures.md pools-key policy, GLOSSARY (managed pool/online/
  registered), architecture.md feature_config row, messages manual rows
  for every new WARN/FATAL. Strict mkdocs build green.
- All affected suites green; ruff clean; FULL suite green
  (tests/run-tests --log: 114 suites passed, 0 failed; python skips =
  root-gated by design). Two extra suites the plan missed were swept in
  (test_page_runners, test_checkagainst_page, test_profile_integration)
  plus the parallel-worker __globals__ patch pattern for gate WARN
  assertions. Awaiting commit cue (coexists with the uncommitted
  Disks-modal natural-sizing work in this tree).

## 2026-11-16 (pub3) — Disks page: Detach button gated to mirror vdevs

- User request: the Detach button should be disabled for non-mirror vdevs.
- disks_page._topology_selection_detach_gate (new) reads the topology-pane
  selection: enabled for a mirror group row, a disk leaf whose parent is a
  mirror, or no selection (the dialog is the picker); disabled with the
  tooltip "Only mirror members can be detached" for raidz/stripe members,
  special/log/cache/spare/replacing devices, non-mirror groups, and the
  pool row. Compute-host gate unchanged and takes precedence.
- update_disks_button_sensitivity: _disks_detach_btn left the shared
  growth_attrs loop for a dedicated block styled after the Proxmox button.
- assess_detach (pool_growth.py) untouched — the dialog remains the
  enforcement; the gate is UI feedback only.
- Tests: TestDetachButtonMirrorGate (9 cases, truth table incl. host-gate
  precedence + Replace unaffected) with a path-tuple FakeTopologyStore in
  test_disks_page_growth_buttons; FakeTreeStore in test_disks_page grew
  iter_parent (product now reads it; paths are tuples).
- Docs: gtk-gui.md Detach section gained a button-gating paragraph;
  testing.md growth-buttons row extended.

## 2026-11-17 (pub) — j22 function survey on the mint leg (first 0.142.0 survey run)

First j22 run against the merged 0.142.0 tree, on the user-chosen mint
baseline (`--template mint`, full universe). Green on run
run-20261117-162554 after one product fix (F-051, verified by the
archive replay) and four harness gaps fixed in-cycle:

- **j22 profile support** (new): reads the driver's `--template` knob
  (storage default | mint); `itf_single_node_lab_main` gained
  `--template/--bare-baseline`, `j05_two_node_lab_main` gained
  `--storage-template`, and the j05 P2P stage branches in-guest
  (ifupdown stanza vs NetworkManager `nmcli` profile; the lease-bounce
  fallback chain gained `nmcli device reapply`). The bare mint
  single-node shape installs the product first-time-user from the
  staged tree (`itf_survey_install_baseline`).
- **Mint carries the ZFS kernel module but no userland** — the pool
  recipe now installs `zfsutils-linux` beside `parted` (mint userland
  2.2.2 vs module 2.4.1 coexist fine; the GUI logs a version WARN).
- **GUI probe config**: the GUI is a config-reading surface like the
  CLI recipes — the probe now runs under the pinned survey config via
  BOTH names (`ZFSUTILITIES_CONFIG_PATH` for config_core,
  `ZFSCONFIG_PATH` for shell-outs). Without it, 0.142.0's managed-pool
  scope legitimately empties the datasets/pools pages (installed
  config registers no pools) — leg-independent, first 0.142.0 survey
  proof.
- **GTK_USE_PORTAL=0 in gui_probe**: on a desktop distro GTK routes
  native file choosers through xdg-desktop-portal, which cannot start
  headless under Xvfb and stacks D-Bus timeouts past the op watchdog.
- **Stale catalog entry removed**: `gui-w-pools-cycle-combo` surveyed a
  Pools-page combobox that no longer exists (scrub controls moved to
  the Scrub Manager); it could only block.
- **F-051 (verified)**: Pools → Export froze the window — a zvol held
  by a live iSCSI LUN session blocks `zpool export` uninterruptibly
  (D-state, taskq_wait), and the handler ran it unbounded on the UI
  thread; a subprocess timeout cannot reclaim a D-state child. Fix:
  `_export_pool_bounded` worker thread + `EXPORT_STALL_WARN_S`
  (default 120 s, env-overridable) + holder-naming WARN. Live proof:
  the Export op passed at the 120.98 s bound with the window alive.
- Remaining survey skips are fixture-by-design (step-table rows empty
  under the pinned config) or data-accumulation preconditions
  (alignment samples for the Performance page).

## 2026-11-17 (pub) — cycle wrap-up: PREEXISTING emptied, export-stall recovery, GTK binding fences

Wrap-up run on the uncommitted j22-mint/F-051 tree. Full suite green
twice over (final: 115 suites, 6711/0; python 4834 + 22 skip).

- **All four PREEXISTING entries resolved, file emptied.** (1) Upgrade
  journeys' transcript markers updated to the absolute-path
  switch-version prints (j10/j12/j19/j23/j25; `sw_cmd` local keeps the
  lines under 100 cols). (2) j18 header, its closing-report line, and
  the journeys README j18 row now say PENDING+DRIFT (the parser's
  failed-mode fixture test is by design). (3) The tooltip full-suite
  flake: ROOT CAUSE reproduced deterministically — a pytest-xdist
  worker co-hosting a real-GTK suite (test_main/test_datasets_tree
  import at collection) leaves GUI modules cached REAL-bound, and
  mock-internals assertions (`Gtk.Entry.return_value`) then die with
  AttributeError, full runs only. Fence: the file's 12 import helpers
  use `import_gui_fresh` (the sanctioned tool; wholesale fresh=True
  re-executes the cyclic pools_page↔pool_actions graph and breaks 10
  tests — import_gui_fresh's targeted restore does not). Verified
  poisoned AND standalone: 140/140. Swept the same conversion across
  ten more suites (121 sites) + extended the gi-guard audit's parser
  to recognize module-level `x = import_gui_fresh("mod")` as an
  import. (4) The export-stall WARN-only branch routed through the
  recovery machinery: `_BoundedExport` (worker + `wait`), shared
  `_resolve_export_blockers`, new `_recover_stalled_export` (diagnose
  → approval dialogs → wait for the stalled worker to settle → one
  fresh retry → honest give-up WARNs; the "Release holders" manual
  instruction is gone). Five new pool-actions tests; the zero-caller
  `_export_pool_bounded` wrapper removed.
- **Sweep regression caught and fixed by the full gate:** module-level
  `import_gui_fresh("backup_runner")` in test_backup_runner replaced
  the cache with a mock-bound copy at collection, and
  test_offsite_e2e/test_runner_factory plain-import it expecting REAL
  GLib (`GLib.timeout_add` drives the step watcher) — every mechanics
  step hung to the 60 s watchdog (5 failed, first full run). Fix:
  module-level sites keep the original STICKY imports (comment
  explains why), and test_offsite_e2e now SELF-HEALS its binding
  (evict + re-import under real gi when it finds MagicMock GLib) —
  order-independent, verified under deliberate poisoning.
- Docs: messages manual gained the three stall-recovery rows;
  gtk-gui.md Export row describes the bounded wait + holder dialogs;
  testing.md's freshness guidance names both fences and the cyclic-
  graph trap; GLOSSARY +D-state, +sticky binding, +xdg-desktop-portal.
  Docs integrity 23/23; mkdocs build green.

## 2026-11-17 (pub2) — Disks page: one selection per page + enclosure correlation tint

- User request, two parts: (1) selecting a row in any of the page's three
  treeviews deselects everything in the other two; (2) selecting an
  Enclosures row tints the associated rows in the other panes and expands
  the Pool Topology so all tinted rows are visible.
- _deselect_other_views (new) unselect_all()s the other two views under the
  repurposed _disks_syncing_selection guard (was checked but never set in
  product code); called inside `if pathlist:` in all three changed
  handlers, so empty transitions (store clears during the 30 s background
  refresh) never disturb the selection _repopulate_enclosures is about to
  capture and restore. Invariant: at most one selection on the page.
- Enclosure tint reuses the teal flag/columns: _highlight_enclosure_disks
  (new) tints member whole-disk rows (parent_path rule, like
  _highlight_pool_disks) plus every topology device on them;
  _highlight_topology_nodes_for_disk renamed …_for_disks(set) with any()
  matching (empty set clears). Pool selector deliberately untouched by
  enclosure selection (not a treeview; drives Proxmox enroll etc.);
  emptied selection restores the pool baseline.
- Refresh resilience falls out of ordering: enclosure restore runs last in
  refresh_disks_page and GTK fires "changed" on the restore, re-tinting.
- Tests: FakeTreeSelection gained unselect_all (clears paths, counts
  calls); test_topology_selection_is_never_modified_by_disk_selection
  inverted into the new law; TestEnclosureSelection (8 cases: deselect
  both panes, tint disks-not-partitions, multi-pool expansion proves ALL
  holding pools expand, baseline restore, guard no-op, selector untouched,
  refresh-restore re-tint, empty-set clears).
- Docs: gtk-gui.md — inventory sync paragraph rewritten around the
  one-selection law, Enclosures section gained the correlation paragraph,
  topology section names the pane-clearing + enclosure tint. Strict mkdocs
  build green.

## 2026-11-17 — Pool Topology Blocksize column: ashift-based pools, per-disk sectors

- User report: pool rows' Blocksize read as sector sizes (on the node every
  pool's 1<<ashift coincides with its disks' sector size); device rows showed
  "-". User decisions: pool rows render the derivation ("4096 bytes (ashift
  12)"), device rows render that disk's physical sector size.
- disks_page.py: _member_sector_lookup(new) builds a member-path →
  physical-sector resolver (by_path index + realpath, same normalization as
  _collect_disk_paths; fail-open "-" — the always-hidden boot disk lands
  here); _populate_topology_store takes the resolver and renders per row
  kind (pool = ashift-based + derivation, disk = sector, groups = "-");
  Blocksize column width 90 → 150; header tooltip reworded for both kinds.
- Tests: TestTopologyBlocksizeRendering rewritten + grown (derivation text,
  ashift-None dash, sector resolution, inventory-miss dash, sector-None
  dash, mirror dash + mixed 4096/512 members).
- Docs: gtk-gui.md topology Blocksize row rewritten; GLOSSARY gained
  "ashift" and "physical sector size" entries. Strict mkdocs build green.

## 2026-11-17 — Migrate Pool: enforced quiesce, safe export, no holding export

- User report (real temp→threeamigos holding migration, ashift change), five
  items. PREEXISTING first per user instruction: Pools-page Export action
  still exports bare-first and recovers reactively — must get the same
  proactive export preparation (new entry).
- Bandwidth-limit tooltip: text after the dash now states the effective-cap
  rule (min of this limit and involved enclosure limits).
- Quiesce is now ENFORCED, not assumed: cutover split into three runner
  phases (copy / catchup / destructive); after catchup, written@cutover per
  dataset (new ZfsRepository.datasets_written_since + parse_zfs_bytes,
  oracle verified live on stewie) — any nonzero refuses (Re-check/Defer
  dialog); unverifiable also defers.
- Step 15 export: disruptive-steps confirm (lists remaining steps verbatim,
  states downtime begins + verified quiesced) + proactive export prep
  reusing pool_actions blockers/unmount machinery (unmount safe filesystems,
  re-scan; survivors → blocker dialog + defer). Bare export never attempted.
- Step 25 holding-pool export DELETED from plan + executor (golden diff =
  one removed line); holding pool stays online the whole cutover.
- mixed_size_warning: "limited to" → "limited by" (docs line too).
- Tests: _drive_handler scripts the new gates (written/disruptive/export
  knobs); TestQuiesceAndDisruptionGates + TestPreparePoolExport new;
  three-tuple ripples fixed; goldens regenerated (holding only).
- Docs: gtk-gui Cutover section rewritten (gates in order, holding pool
  never exported); messages manual rows for the new INFO/WARN lines;
  GLOSSARY "quiesce" added.

## 2026-11-17 — Disks page: migrate-picker sizing verified pinned; pane cells ellipsize + hover

- User report, two items (both observed on 0.141.0 during the real
  temp→threeamigos migration): Migrate Pool's new-disks picker too short +
  window not scrollable; Disk Inventory cells neither ellipsized nor
  tooltip'd on overflow.
- Item 1 was ALREADY FIXED by the same-day pub3 merge a06f1bf (natural
  dialog sizing): probe-verified on the real show_migrate_pool_dialog under
  private Xvfb — 0.141.0/pre-merge 801c644 crush the picker to ~3 rows
  (71px) on a short window (resize 700x480 = the deterministic red
  condition); the merged tree keeps the full 20-row cap (464px), scrolls
  inside, and the dialog window carries the overflow at every screen size
  incl. the 90%-workarea cap. No product change; the geometry is now PINNED
  in disks_dialogs_realized_check.py (real dialog, resized short).
- Item 2: all three Disks-page panes (user widened scope from Disk
  Inventory to include Enclosures + Pool Topology) now END-ellipsize every
  text renderer and wire gui_helpers.attach_cell_tooltips — Disk Inventory
  and Pool Topology offset 0, Enclosures offset 1 (unrendered id column at
  store 0). Same idiom as the Pools/Dashboard/Alignment tables; docs
  already state the universal rule (Tooltips section + Disks-tab intro),
  so no doc changes.
- Tests: mocked wiring/offset/renderer test in test_disks_page.py;
  realized check grew the real-migrate-dialog case + a real-page panes
  case (every renderer END, every view has-tooltip), red-proofed on a
  /tmp copy with the fix reverted (PANGO_ELLIPSIZE_NONE).
- GOTCHA (realized probes): once create_disks_page's returned page widget
  is garbage-collected, the container tree tears down and the views' column
  lists EMPTY (app attributes hold the bare views only) — realized probes
  must keep the page widget referenced.

## 2026-11-17 — zfscheckagainst: absent counterpart is a verdict, not a WARN

User reported three `WARN: Dataset to check ... does not exist or is offline.`
lines (zfscheckagainst:333) from the Retention page's Prune Snapshots on
stewie (session 2026-11-17_21-21-20_prune_gui.log, label=offsite). Verified
live: the WARNs fired on fivebays prune candidates whose reverse fss rows
map to source-side datasets that don't exist — NVME1/zfsutilities-manifests
(store exists only at the first hop, by design) and
threeamigos/proxmox/vm-215-disk-0/1 (VM 215 archived to
temp/archive/threeamigos/proxmox/...). No harm: every deletion verified via
other rows (z22tb hold-tag / z40tb common snap); all 5 steps rc=0.

Fix (this tree, uncommitted): a counterpart dataset missing on an ONLINE
pool is now a distinct "absent" outcome — logged once per run per dataset
at INFO (`/tmp/caabsentprinted.$PPID` marker, repeats at VERB), folded like
offline_pools, and when every matched row is absent the verdict is rc 4
("not common — nothing to protect"; user-approved auto-delete). Absent
never overrides a different row's offline/locked rc 6 or last-common rc 7.
The old WARN+skip fallthrough wrongly landed absent-only cases on rc 5
(interactive confirm; GUI non-interactive = keep) — the store's
@dailybackup pruning (new in 0.142.0) would have been stuck on that.
Caller side needed nothing: delsnap/preview already treat 0|4 alike.
Cleanup of the new marker added to the fssalreadyprinted exit traps
(zfsdelsnap, zfsretain dry-run, this suite). Docs: messages/index.md row
replaced (2 new rows), modules.md rc-4 row + new "Absent counterpart
datasets" subsection, GLOSSARY gained "counterpart dataset". Tests: 3 new
in test-zfscheckagainst (absent-only → 4 + INFO once, INFO-then-VERB via
with_msg_level — log_verb hides from stderr unless a gate is set,
absent+offline → 6). Suites: checkagainst 38/38, delsnap 25/25, retain
32/32, cleanup 16/16; full suite green; mkdocs --strict clean; shellcheck
matches baseline (SC2016 info, intentional single-quoted trap).

## 2026-11-18 — Log Viewer: path line no longer highlights on pop-out/focus

User report: Logs page → Log Viewer — "the log path should not be
highlighted." Root cause (verified against GTK 3.24.41 gtklabel.c):
`gtk_label_grab_focus` runs `select_region(0, -1)` — select ALL text —
whenever a selectable label gains focus by any route other than a click,
gated by GtkSettings `gtk-label-select-on-focus` (default on); the
selection is drawn while focused. The path line (`logs_path_label`,
selectable) is the first focusable child of viewer_box, so the pop-out
window's initial focus (`_on_logs_popout_toggled` → show_all) and Tab
navigation deterministically highlighted the whole path.

Fix (this tree, uncommitted, user-approved scope): one line in main.py
`do_activate` next to the CSS provider —
`Gtk.Settings.get_default().set_property("gtk-label-select-on-focus",
False)` — app-wide. Labels stay click/drag-copyable everywhere (docs
promise "selectable for copying" in gtk-gui.md, still true); only the
focus-driven select-all is disabled. The other 11 set_selectable sites
are untouched and inherit the same protection. No docs change needed.

Verification: Xvfb probe (3 phases: stock pop-out path reproduces
bounds (0,75); fix → bounds None; manual select_region still selects) +
realized-style smoke driving the REAL `_on_logs_popout_toggled` /
`_update_logs_path_label` / `LogPopoutWindow` with a faithful viewer_box
build — stock phase highlighted, fixed phase plain (screenshots
inspected). Affected suites test_main + test_logs_page green; full
suite green (run-tests -q). No new permanent test (plan-scoped one-off
probes; mock_gtk can't exercise real GtkSettings).

## 2026-11-18 — Miscellaneous Logs heading tooltips removed; heading dead zone fixed

Two user asks, one turn. (1) Logs page → Miscellaneous Logs treeview:
remove the pre-existing tooltips. (2) Disks page → Disk Inventory column
headings need tooltips.

(1) The Miscellaneous list shares `_make_log_view_columns` with the main
list, which attached a tooltip-bearing header label to every column.
New `header_tooltips=False` parameter; the Miscellaneous call passes it
and gets plain default headings (no header widget at all). The main
list keeps its tooltips, and the "Miscellaneous Logs (N)" expander-bar
tooltip is not on the treeview and stays (stated in the approved plan).

(2) The Disk Inventory headings ALREADY had tooltips — every Disks
column calls `set_column_header_tooltip`. Root cause (probe-verified
earlier in the campaign session): GTK seats the custom header label
inside the column's header Gtk.Button at the label's NATURAL text
width, so a 160px heading carried only a ~40px tooltip-active strip;
hovering the rest showed nothing, hence "needs tooltips". Fix at the
helper: the header label now connects its `realize` to
`_on_header_label_realize`, which arms the enclosing header Button with
the same tooltip text — the button spans the full heading width. One
helper change arms every heading app-wide (all pages using the helper
plus EditableListView); checkagainst's bespoke `_build_header` Box does
not use the helper and stays for the pending campaign.

Tests: test_logs_page header test now expects 7 main-list header
tooltips and 14 appended columns (both lists; shared TreeView mock);
test_gui_helpers gained the realize-wiring assert plus handler tests
(arms button / no-op without ancestor);
disks_dialogs_realized_check now realizes the real Disks page in its
private-Xvfb window and asserts per column: label tooltip non-empty,
Button ancestor exists, button tooltip equals the label's, button
allocation spans the column width (±2px), and first-column button
minus label strip ≥ 40px (dead-zone evidence). Docs: gtk-gui.md Tooltips
section carves the Miscellaneous table out of the every-heading claim.
Affected suites green; realized check green; ruff clean.

Follow-up, same day (user: "I still see tooltips everywhere in this
treeview, and they all say the same thing"): the survivor was the
EXPANDER tooltip. GTK shows a widget with no tooltip of its own the
nearest armed ancestor's text, and the expander wraps the whole
Miscellaneous treeview, so its one tooltip surfaced over every heading,
row, and cell — uniform text everywhere is the fall-through signature.
Removed the expander tooltip too; a code comment at the expander
records the law so it does not come back. New guard test
test_misc_section_carries_no_tooltips asserts create_logs_page never
arms the shared Expander mock (with the file's idiom for isolating the
viewer-frame one-shot side effect — the shared-mock trap bit once
during development). gtk-gui.md exception sentence widened to the whole
section: title bar, headings, and cells all tooltip-free.

## 2026-11-18 — All treeviews: ellipsize + clipped-cell tooltips campaign

User cue: "GUI -> All treeviews: Ellipsize all the cells on text overflow
and provide tooltips containing the cell's full text." Executes the
campaign planned earlier the same day (approval had been pending; the
re-issued request was the go).

Helper: attach_cell_tooltips/_on_cell_query_tooltip gained column_map
(gui_helpers) — a per-visible-column list of store indices, None = never
tooltip. Needed because two views' visible order diverges from store
order and no constant offset can route them: the Pool Registry (visible
Name, Offsite, Health, Errors, numeric vs store 0 name, 1 health, 2
size … 9 flag, 10 offsite, 11 errors) and the pool-growth target tree
(visible Size = store 5, State = store 2). Existing offset call sites
untouched.

Treated (21 views, 13 files): pages — Pool Registry (map), Datasets,
Schedule (bespoke always-on _on_next_run_query_tooltip deleted,
superseded by the shared clipped-only handler; all five text renderers
ellipsize now, not just Next Run), Offsite steps, Retention bucket (spin
renderers untouched — int store values fall through the str check) +
prune, Checkagainst editable + readonly ×3 (the _build_header Box
duplicate migrated to set_column_header_tooltip — dedup AND the
full-heading fix; helper deleted), Logs main + Miscellaneous (inline
header-label block swapped for the shared helper on main; misc keeps
plain headings; BOTH lists attach clipped-cell tooltips — per-celled
text, not the removed uniform ancestor tooltip; guard test docstring
narrowed to expander/title bar), EditableListView (covers both Backup
step tables), memory_page _device_table (L2ARC/SLOG/Enclosures).
Dialogs — pool_watch Watch window, pool_actions Import-Pool picker,
pool_create_wizard + pool_growth disk pickers, growth target tree (map),
pool_profile manage, profile manage/add-overwrite/recall pickers, and
the apply-profile picker — whose Description column KEEPS its deliberate
word-wrap (wrapped text never clips; full text already visible) and
passes column_map=[0, 1, None] so it never tooltips.

Ellipsize idiom: files that import Pango use the enum; the rest follow
the dashboard/pools precedent `set_property("ellipsize", 3)  #
Pango.EllipsizeMode.END`.

Tests: column_map routing unit tests in test_gui_helpers (map reads the
named store column; None entry and beyond-map positions return False);
per-view wiring tests everywhere (recorder pattern: view/store/offset or
map + renderer ellipsize counts — reset the shared CellRendererText mock
before counting, earlier same-module tests accumulate on it). Schedule's
bespoke handler tests replaced. FakePickerTreeView gained
set_has_tooltip/connect no-ops. The gi-import guard caught one bare
in-function import — use the module-level binding.

Docs: gtk-gui.md Tooltips carve-out sentence now reads "neither the
collapsed section's title bar nor its column headings carries a tooltip
— though its clipped cells still show their full text on hover, like
every other table"; the Schedule Next Run paragraph generalized to every
cell. Docs validation pair green; site rebuilt.

Smoke: full GUI launch as dan re-execs through pkexec (main.py:422,
root-by-design) — passwordless launch smoke not possible; the realized
checks (disks/backup/alignment, real GTK under private Xvfb) carry the
render validation instead, in the full suite.
