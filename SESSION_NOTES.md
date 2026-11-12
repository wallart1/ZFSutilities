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

- **ITF report.md live visibility (2026-11-11, in tree, uncommitted).**
  Every report.md line now carries a UTC timestamp; `itf_step_start`
  (report-lib) announces the START of long activities — one line each at
  the 13 stage entries, the shared wait/download/clone helpers (guarded +
  stdout-clean because guest-lib/ssh-lib helpers also serve report-less
  CLI paths), the survey runners, and ~90 journey-direct ≥30s ops
  (installer/upgrade/archive/reconcile/kill runs). START rows never land
  in steps.tsv (sweep awk + watch consume one-row-per-completed-step).
  Unit suites stub itf_step_start beside their itf_step stubs. Live
  proof = the next real journey run. (Also this session, uncommitted:
  datasets-page count label removed; "aborted by user" dropped from
  zfs-send-receive WARNs; installation docs sudo ssh-copy-id.)

- **archive-vm message quieting (2026-11-10, in tree, uncommitted).** The
  orphan-zvol notice is now gated VERB (new bashinit `log_verb`: hidden on
  the terminal by default, session log always, operator gate wins); the
  resolver's boot-disk-controller VERB leak was already gated by 0.140.0's
  engine WARN wrap and now has a regression fence
  (test_archive_resolver_verb_stays_gated). User's transcript was 0.138.0
  on tweety — both fixes land with the pending node deploy.

- **Blocksize-ladder dead margins (2026-11-10, fix in tree, uncommitted).**
  The ladder's huge top/bottom/left dead space was one-shot
  `tight_layout` (figure-fraction margins solved at a stale canvas size,
  scaling up at the real allocation). Both matplotlib renderers now
  re-solve on allocation-size change (`_on_size_allocate`, deduped); the
  spike fences the margins with a map-then-fill ordering (red-proven).
  Awaiting the user's visual confirmation on their Performance page.

- **Alignment guest-probe decode — live remainder (fix rode 0.139.0
  via the pub3 lane merge; committed on main at `4cc0998`).** The
  `out-data` decode + per-reason note + WARN-raw-stderr hardening are
  in the tree; LIVE proof still needs a node deploy (user-cued). The
  user screenshot 2026-11-08 10-08-25 still lives UNTRACKED at the pub
  repo root — remove when the fix ships (i.e. after deploy). Guest-probe
  future work below still open.

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

- **gtk-gui.md Migrate Pool rewrite (2026-11-11, user request):** the
  `#### Migrate Pool` section was a wall-of-text complaint; body rewritten
  per `Writing Rules.md` into eight `#####` subsections (Destination modes,
  New pool settings, Non-default pool properties, The review page, Cutover,
  Stopping a migration, Snapshot holds, After the cutover). Fact-preserving
  only — no behavior claims added or dropped; heading text and anchor
  `#migrate-pool` unchanged. First `#####` level in this page; h5 does not
  reach the Material side TOC (depth 3) but renders in-page with permalinks.

- **SMART Details WARN rc-gate fix (2026-11-11, user item /dev/sde):**
  root cause — smartctl exit codes are a bitmask; `smart_details()` discarded
  the report whenever rc!=0, hiding exactly the flagged disks (stewie sde/sdh
  are the USB-SAT pair). Fixed: report returned whenever printed; WARN now
  carries rc + decoded bits (`_smartctl_rc_reasons`); flagged reports dump
  with a WARN line first. Same gate fixed in `smart_health` /
  `_smart_health_and_wear` (failing disk rc=8 now parses to FAILED, not n/a;
  also `FAILED!` bang stripped). `-d sat` retry ladder deliberately deferred —
  the new WARN names the rc; decide with that evidence. Fix rides the next
  release; nodes still on 0.138.0 will keep the old WARN until deployed.

*(pub2 lane history block, unioned at the 0.141.0 merge — pruned at the next release prune)*

## 2026-11-10 (evening) — property manifests vs the readonly z40tb experiment (user bug report)

- User report: the 21:34 offsite GUI run (temp → z40tb, first real offsite
  run since manifests shipped in 0.138.0) logged 16 unexpected
  `Property manifest for ... not written (write to
  z40tb/temp/zfsutilities-manifests failed)` WARNs. The "No common
  snapshot" WARNs (full copies) were expected and untouched.
- Root cause on stewie: the z40tb POOL ROOT carries a local `readonly=on`
  (a user experiment, since declared unneeded; fivebays is local `off`;
  tweety has no non-default readonly anywhere). `zfs create -pu` made the
  store inherit it → mounted read-only (`mount` shows `ro,noatime`) →
  every write probe failed EROFS. Fail-open held: data verified, no
  manifests. Secondary defect: the WARN named no reason.
- Fix (approved plan, executed): the store never inherits protection
  flags — create is now `zfs create -pu -o readonly=off`, and capture
  self-heals a pre-existing guarded store (`zfs set readonly=off` under
  the store's write lock, before the mount) so z40tb's already-created
  store recovers on the next run with no manual node work. The heal sits
  in `propmanifest_capture` (write path) deliberately — replay mounts
  read-only and reads fine, so it never mutates. Write-failure WARNs now
  carry the shell's real error (`... failed: Read-only file system`).
- Tests: `test_capture_selfheals_readonly_store` added (heal-once,
  before-mount ordering, both manifests land; mock `zfs set` made
  stateful so the once-ness is observable); `test_ensure_creates_once`
  and `test_capture_happy_path` pin the new create string;
  `test_capture_write_failure_fails_open` moved to a nonexistent
  mountpoint dir (ENOENT is deterministic for root and non-root; /proc's
  EACCES text was environment-fragile) and asserts the reason text.
  All red-proofed before the lib changed. Plan's separate
  `test_create_uses_readonly_off`/`test_write_warn_carries_reason` were
  folded into the updated tests (identical assertion sites).
- Today's z40tb generation carries no manifests (replay falls back to
  newest available); next offsite run after deploy captures normally.
  Optional user cleanup, not required: `zfs set readonly=off z40tb`.

## 2026-11-10 (later) — offsite-candidate pool-identity exemption (user bug report)

- User report: Dashboard warned "Pool z40tb is imported but not configured
  in node.conf — an unexpected pool is serving data here" although z40tb is
  a long-designated offsite rotation pool (Pool Registry lists it). Verified
  on stewie: z40tb imported + `offsite_candidate: true`, but absent from
  node.conf's POOL_TARGET (rotation sibling z22tb IS listed) — so the
  warning fired on every rotation where z40tb is the attached pool.
- Fix (approved plan, executed): the offsite exemption now covers BOTH
  set-difference shapes in `dashboard_page.py::_compute_pool_identity_warnings`
  and `lib/iscsi-lib.sh::detect_pool_identity`; the message tail became
  actionable ("— add it to the node config or export it"). GUID shape
  untouched. `bin/export-iscsi-state::collect_live_state` now records
  imported offsite candidates' GUIDs into the state map's `pools` dict, so
  an attached rotation pool stays inside the GUID fence (map consumers are
  the identity detectors + export drift check only — no rebuild logic
  reads `pools`).
- New tests: python `test_offsite_candidate_imported_not_configured_is_exempt`;
  bash `test_two_node_identity_offsite_candidate_imported_exempt`;
  `test_offsite_candidate_guid_recorded_when_imported` (with selectivity
  sub-check). All three red-proofed against the old logic (temp reverts).
- Verified on bash 5.2 while writing the export test: `VAR=x func` does NOT
  persist after the call (the function sees it, the caller's shell doesn't)
  — the test's save/restore of ZFSUTILITIES_CONFIG_PATH is hygiene, not a
  fence; the bash-traps env-prefix note stands as written.
- node.conf on the nodes deliberately untouched: the Pool Registry flag is
  the authority for "known rotation pool". Effect lands on the next deploy.

## 2026-11-11 (pub2): restore destination-naming docs audit

- Task: audit the docs after 0.139.0's rename freedom removed the
  requirement that a restore destination be derived from the source
  name. Two stale passages found, one silent page; the rest of the
  sweep (gtk-gui rename paragraph, python-modules, messages/index,
  commands zfsrestore, global-variables, modules, architecture,
  README, profiles) verified accurate against
  compute_auto_destination/compute_restore_params.
- concepts.md: "must be stripped back off ... handle this
  automatically" rewritten — stripping is the conventional shape, the
  original name is no longer required, GUI auto-determine vs free-form
  manual, links to the new restore.md section.
- gtk-gui.md Restore tab: "The destination dataset is the one that was
  originally backed up" now reads "typically ... any destination is
  accepted", with links; the user's pending hand-edits (sidebar table,
  Dashboard pool-identity) left untouched.
- restore.md: new "Where a Restore Lands" subsection — conventional
  suffix mapping vs rename (worked examples), GUI auto-determine and
  manual behavior, CLI $sourcefsremovequalifiers + $destfs mapping.
- Gates: test_docs_integrity green (new anchor + cross-links resolve);
  grep sweep clean. Full suite green except one xdist flake
  (test_zfs_lock_manager local-conflict message test — passes alone
  and file-wide on rerun; filed in PREEXISTING.md).

## 2026-11-11 (pub2): Disks page — topology tint lands on the disk row

- User item: selecting a Pool Topology row of type "disk" tinted the
  partition row in the Disk Inventory; the disk row should tint instead.
  Root cause: `_highlight_topology_devices` matched raw leaf paths — a
  by-id `-partN` leaf realpaths to the partition, and the whole-disk
  prefix rule compares raw strings, so the disk row never matched.
- Fix: new `_backing_disk_paths()` resolves each member to its physical
  disk via the cached inventory (`parent_path`, path realpath, and by-id —
  indexed BOTH as the bare basename the repository stores and the full
  /dev/disk/by-id/ form the topology leaves carry; unknown devices keep
  their raw path, fail-open). `_path_matches_any_device` itself is
  unchanged — a whole-disk target matches only its own row, so partitions
  stop tinting for free. Covers device rows AND vdev/pool nodes (same
  call path); `_highlight_pool_disks` maps members to `parent_path or
  path` so the pool-wide tint follows the same rule.
- Tests: TestTopologySelectionHighlightsBackingDisk (by-id member, vdev
  node, kernel-path member, unknown-device fail-open, pool-wide tint) +
  rewrote the old partition-leaf test (both-rows expectation → disk-row
  only). Red on the old code, all green after the fix; full disks suite
  green. Ruff clean.
- Docs: gtk-gui.md Disks section — both tint passages now say disk rows;
  partition members tint their whole disk; inventory→topology direction
  unchanged.
- PREEXISTING += 1 (recurrence note on the lock-manager xdist flake +
  new entry: partition-member pools leave the disk row pool-less —
  `_pools_for_disk` matches exact realpath/basename only, so the disk
  row's Pools column is blank and selecting it clears the pane).

## 2026-11-11 (pub2): architecture.md reworked per review pattern

- User review of docs/docs/developer-guide/architecture.md set the pattern:
  answer exactly the question asked; no historical references ("now", "no
  longer", "as before", refactor narration); architecture-level prose only
  (code-walkthrough detail belongs in code comments). Applied throughout.
- Restore Flow: "Why two steps?" answered with the single sentence; new
  "Destination hold preservation" subsection states the full
  capture/release-only-offsite/reapply contract with the when-not side
  (plain incrementals, dry-run, preserve_target_holds='N', fatal exits).
  Facts verified in zfs-send-receive (capture gate ~L531, reapply ~L988),
  zfsrestore, zfsreapplyholds, zfsdelfs.
- Factual fix found while verifying: the msg-level-gate section claimed the
  WARN gate covers remove-vm-disk --from-archive; the code gates only the
  archive engine calls. Corrected to match current behavior.
- History purge: session-logging/cron-fence pre-fence narration, "stream
  exactly as before", "Regeneration no longer depends", "was refactored",
  "remains as a compatibility shim ... migrated incrementally", "today",
  "Phase 4", "no longer have an iSCSI LUN", "historical session log".
  Legitimate current-world "legacy"/"history" uses kept (snapshot-name
  formats, config layer, history JSON).
- Detail trim: single-writer cron-fence mechanics compressed (code homes
  verified: _silence_cron_output docstrings, profile_runner.py:339-341 pv
  comment); added the one missing code comment (session-log state clearing,
  backup_runner.py finish+cancel paths).
- Gates: mkdocs build to /tmp clean (anchors resolve); history-marker grep
  sweep clean; full suite at turn end.

## 2026-11-11 (pub2): lock-conflict prompt under strict callers (user bug report)

- User report: GUI backup on stewie (0.140.0) aborted at step 9/12 —
  `zfslockmanager: line 1134: ZFSUTILITIES_HEADLESS: unbound variable`,
  rc=1. Cause chain: the 21:34 offsite GUI leg (fivebays -> z40tb, still
  running) held w locks on fivebays/threeamigos/proxmox/vm-*; the backup's
  destination lock (threeamigos/proxmox -> fivebays) hit a genuine
  conflict; the GUI runner gives every step a PTY on stdin, so
  `[[ -t 0 && "$VAR" != "Y" ]]` reached the unset read under the strict
  zfs-send-receive payload. No data touched; the dead step's locks were
  released; the offsite run continued.
- Why every suite was green: tests stub _zfslock_is_interactive, the
  set-e child template exported ZFSUTILITIES_HEADLESS=Y, and no suite has
  a terminal on stdin. Three independent masks.
- Fix (zfslockmanager): default the headless read; fence the six
  holder-field reads; EOF at either prompt reads as the empty default with
  ask_line fenced; the force-confirm variable is local; the W branch
  restores the caller's INT trap (the old eval-of-empty left the wait
  handler armed, swallowing every later Ctrl+C). Guarded re-reads
  defaulted in zfsconfig and installer-lib. The field/ask_line fences are
  tolerance hardening: every strict script reaches the resolver through a
  conditional call, so no live errexit-active caller exists.
- Tests: tests/pty_run.py (PTY stdin; gui shape = the runner's piped
  output, terminal shape = all fds on the PTY; expect/send/eof/run steps,
  all bounded by a timeout). New strict-child sections in
  test-zfslockmanager (choices, fences, headless decision); _sete_child no
  longer exports the headless variable. Red-proofs: each of the five
  product terms reverted alone fails exactly its tests; the variable
  revert reproduces the production error line.
- Fence: test-strict-mode guard — no bare read of a ZFSUTILITIES_* or
  ZFSLOCK_* variable that no bash file assigns. Red-proven against the
  pre-fix files: it flags all five sites, including line 1134.
- Docs: lock-manager.md (interactive conditions, GUI PTY, set -u note),
  global-variables.md (the missing $ZFSUTILITIES_HEADLESS row at the
  anchor modules.md already linked), coding-policies.md (terminal-check
  rule), testing.md (pty_run.py section plus rows), GLOSSARY.md (PTY).
- PREEXISTING += 1: zfsdailybackup (strict) calls cleanup with three
  arguments; cleanup's bare $4 and optional-global reads abort under
  set -u (semantics probe-verified, not run end-to-end). Also removed two
  test counts from earlier notes-file entries per the no-counts rule.
- Not fixed, noted here only: the W wait's sleep stays unfenced — an
  interrupted sleep would abort an errexit-active bare caller (none
  exists).

## 2026-11-11 (pub2): Dashboard Tasks — live rows pinned at top; never dropped mid-run

- User request: running tasks always at the top of the Tasks list, sorted
  ascending datetime, never removed while running.
- Root causes: `_refresh_tasks_section` sorted all rows newest-first, so a
  running task sat below recent completions; and the store is rebuilt from
  collector output every refresh, so one refresh that fails to report a task
  dropped its row — concretely, `BackupRunner._finish`/`_end_cancelled` flip
  `running` off BEFORE writing history, and profile lock-file / surface-test
  state / dataset-action tracker reads have momentary races. Scrubs were
  already covered upstream (scrub queue tick has miss-hysteresis).
- Fix (dashboard_page): live block (waiting+running) sorts above completed,
  ascending by start (longest-running first, timeless rows atop the block);
  completed rows stay newest-first. New `_retain_unreported_live_rows` keeps
  a last-known live row on `app._dashboard_task_carry` for up to
  `_TASK_CARRY_MISS_LIMIT` (2) consecutive missed refreshes, dropping it the
  moment a completed row with the same session log file appears. Bounded
  grace is deliberate: scrub/surface-test/ZFS-op tasks never write history
  rows, so unbounded carry would leave permanent ghosts.
- Tests: `test_live_rows_sort_above_completed` (renamed from the old
  reverse-chronological mixed test), `test_live_rows_sort_ascending_by_start`,
  carry survive/drop-limit, carry-vs-completed swap, and miss-count reset.
  `_make_app` gives the app a real `_dashboard_task_carry` dict.
- Docs: gtk-gui.md Tasks section — live-first ascending order and the
  retention behavior in user terms.
