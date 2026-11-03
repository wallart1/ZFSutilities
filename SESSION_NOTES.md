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
