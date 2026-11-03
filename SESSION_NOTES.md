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

## Backup property fidelity — P0 base commit (2026-11-02, pub)

- Campaign reopened by the user 2026-11-02; phases execute one per
  session, each with a focused approved plan. P0 = land the base.
- Frozen second-wrap-up diff re-confirmed byte-matched before staging
  (same 10 files, +260/−87, HEAD a08a7af, nothing staged); the recorded
  no-soak gate on that exact frozen tree stood, so no rerun (P0 authors
  no code).
- Commit message presented and committed on the user's explicit go as
  8cf365f ("fix: name-based orphan-fence ownership, offsite-candidate
  identity exemption, cancel-test budget"). Tree clean after; nothing
  pushed/tagged/deployed.
- The campaign plan file's "fix memory files" item (ITF-hold wording,
  REOPENED marker) was verify-only — the planning session had already
  applied all of it.
- This entry is the only tree change after the commit; it rides P1's
  commit. Next: P1 capture half (lib/property-manifest-lib.sh, the
  bin/zfs-send-receive post-verify hook, suites, docs).

## Backup property fidelity — P1 capture half (2026-11-02, pub)

- New lib/property-manifest-lib.sh: manifest dataset lifecycle (derive
  `<destfs>/<sourcepool>/zfsutilities-manifests`, create-once latch,
  fail-open on refusal), capture (w-lock, mount-on-demand with EXIT-trap
  + finish unmount, `zfs get -s local all` minus the exclusion set, %2F
  file naming, sha256 header, tmp+rename atomic write), idempotent
  lockstep generation snapshot. All failures WARN + rc 0.
- Engine: `property_manifest` global (default 'Y'), one post-transfer
  hook covering the incremental and both full-copy completion shapes,
  `propmanifest_finish` after the loop; dry-run lives in the lib
  ("Would capture …"). Live-verified input: `zfs get -s local all`
  INCLUDES user properties (org.debian:periodic-scrub on every stewie
  pool root); zero-local-prop datasets get header-only manifests.
- zfsrestore sets property_manifest='N' (addition beyond the plan's file
  list, disclosed): restore targets must not grow manifest stores;
  replay arrives in P2.
- Tests: new test-property-manifest-lib (21 tests) and
  test-zfs-send-receive-manifest (6 engine-contract tests, recording lib
  fakes); dryrun suite +1. Red-proofs: hook disabled → 3 red;
  volblocksize un-excluded → 3 red. Gotchas: command substitution would
  discard the mount latch/trap (lib sets a global instead); test-lib
  wraps EXIT traps in _EXIT_TRAP_HANDLERS; assert_contains takes exactly
  2 args; the full-copy engine path needs the iscsi_teardown_zvol fake.
- Audit suites: module-dependencies required the declare -f lock-manager
  guard (caller-provided helper pattern); strict-mode clean; shellcheck
  -S warning clean; lock-coverage untouched (bin/-scoped).
- Docs: global-variables row, modules.md engine row + lib entry + jump
  list, 10 messages rows, GLOSSARY "property manifest", commands.md
  caller rows (dailybackup/zfssend/zfssendoffsite/zfsrestore). Docs
  integrity green; mkdocs rc 0; affected-suite gate green (8 suites).
- SESSION_NOTES stayed OUT of P1's commit: a concurrent session pruned
  this file mid-phase (release-prune work also touching FINDINGS.md and
  repair-plans/025); this entry and P0's ride that later commit.

## Backup property fidelity — P2 replay half (2026-11-02, pub)

- Lib replay half in property-manifest-lib.sh: store/key derivation from
  a backup copy's first two components (mirrored-chain shape), exact-
  generation lookup (backup copy's newest snapshot via `zfs list -t
  snapshot -S name`) with newest-available fallback + WARN, pure
  parse+verify (header version / dataset field / body sha256; rc
  1..4), apply with per-prop skip+WARN, keylocation set + best-effort
  non-interactive load-key (file:// only), apply_file for .props
  siblings, multi-store switch-unmount (only one store mounted at a
  time), per-destination w-lock. WARN-only, rc 0 always.
- GOTCHA (checksum contract): capture writes the body WITHOUT a
  trailing newline (its sort ran through a command substitution), so
  parse must JOIN lines with \n separators — appending one \n per line
  breaks the sha256 for every non-empty manifest. Empty bodies are fine
  either way.
- bin/zfsreplayprops: callable+sourceable wrapper (zfssend pattern;
  file-scope set -euo pipefail like the engine — sourcing it flips the
  caller to strict mode, so its tests run in subshells).
  replayprops_datasets (fsarray entry, maps via remove_leading_qualifiers
  exactly like ensure_restored_iscsi) + standalone replayprops
  (zfsrestore overrides shape). Consumers: zfsrestore (hook before
  ensure_restored_iscsi, new replay_properties='Y' override — disclosed
  addition), GUI restore payload (sources it; emits the call after Part
  2; also sets property_manifest='N' — disclosed P1 completion, the
  payload was missing the opt-out), zfsrestoresendstream (.props sibling
  after each receive).
- GOTCHA (qualifier convention): the mirrored chain strips TWO
  qualifiers for a same-name restore (backuproot + srcpool), destfs =
  the pool — first-draft wrapper test data assumed 1 and was wrong, not
  the mapping code.
- Mock hole found and fixed in test-zfsrestore: ZFSRESTORE_STATE was
  never exported, so the ensure-restored-vm-iscsi SCRIPT mock silently
  wrote to / (permission denied); the old iscsi-failure test passed for
  the wrong reason (its configured rc). Export now; all four isci-
  touching tests pass for the right reason.
- Tests: new test-zfsreplayprops (32: lib 28 + wrapper 4; suite-local
  zfs mock over a REAL store dir; red-proofs: checksum neutralized → 3
  red, file:// branch skipped → 2 red). test-zfsrestore 8→12 (call,
  order via shared seq file, opt-out, fail-open). test-zfsrestoresendstream
  3→4 (.props applied; sibling-less file untouched — disclosed suite
  addition). Python: restore_runner +6 (payload property_manifest=N,
  sources helper, replay between Part 2 rc and ensure_restored_iscsi,
  N → absent, dry-run keeps the call), restore_page +3, feature_config
  +2 (lazy-seeded default, old-config merge). Gates: 4 bash suites 69
  green; 4 python suites (incl. docs integrity) 173 green; shellcheck
  -S warning + ruff clean; mkdocs rc 0.
- GUI: RESTORE_DEFAULTS variables key replay_properties='Y' (lazy-seeded
  by get_restore_config — no CONFIG_VERSION bump); restore_page combo row
  (verify_after_transfer pattern, scroll suppression, tooltip);
  restore_runner emits replayprops_datasets when Y.
- Docs: restore.md "What a Restore Preserves" rewritten (manifest sidecar
  + replay best-effort bullets; keylocation flow updated — replay sets it
  and loads file:// keys non-interactively), Advanced Options
  replay_properties row; gtk-gui.md Restore tab row + phases bullet;
  commands.md zfsreplayprops section + jump row + zfsrestore/zfsrestoresendstream
  updates; modules.md lib section now capture AND replay (7 new function
  rows); python-modules.md two intro lines; 21 messages rows; GLOSSARY
  replay paragraph in "property manifest".
- This entry also stays OUT of the P2 commit (same concurrent-session
  ownership as P0/P1); it rides the later SESSION_NOTES commit. Next:
  P3 offsite travel + retention (zfssendoffsite step 4 includes,
  property_manifest='N' on onward legs, offsite_runner mirror,
  test-zfscleanup lockstep).

## 2026-11-02 — Backup property fidelity P4: ITF journey j20 (live green)

- j20-property-manifest.journey authored (j19 model + single-node lab):
  S/B1/R1/B2/R2/PF/O1+O2/R3/KL/P/E2E stages; live GREEN run
  run-20261102-155736 (28 steps, 0 fail; ~5 min on --rerun, ~9 fresh).
  Registration: journeys/README row, itf-coverage.md row,
  integrated-testing.md section, test-itf-driver list j01–j20.
- TWO PRODUCT DEFECTS found live by the journey, both fixed in-turn:
  1) zfs-send-receive's first-copy destination pre-create (zfs create
     -pu) made an unencrypted filesystem placeholder that a raw
     encrypted stream cannot overwrite (receive -F refuses) and a
     filesystem placeholder cannot receive a zvol stream — production
     never hit it (destination lineages predate). Fix: skip the
     pre-create for volume/encrypted sources (the receive creates the
     destination); VERB line + messages row; 3 regression tests in
     test-zfs-send-receive-holds (red-proofed 2-red via condition
     neutralization).
  2) property-manifest-lib created the store with plain `zfs create -p`
     (auto-mounts), so the mount bookkeeping never recorded ownership
     and propmanifest_finish leaked the store mounted past the run.
     Fix: `zfs create -pu` (single-owner mounting); the two shape
     greps in test-property-manifest-lib updated to -pu.
- P3-deferred e2e mutation scenario offsite-onward-leg-manifest-travel
  ran for the FIRST time (inside j20) and needed a live fixture fix:
  the step's backup-root source must be a registry-created dataset
  (run-prefixed), and the no-capture assert now derives the
  destination store name from the prefix. e2e_support.py; container
  tiers unaffected (mutation scenario skips there).
- Journey-side lessons (bashed out over rerun cycles): zfs create takes
  ONE dataset per call; guest*.txt in a run dir is the harness
  guest-record namespace (--rerun reads it — journey files must not
  match); zfssnapbuild's prior-nextsnap ask_yn eats a feed line before
  zfssend's own read (feed several newlines); zfs get -p prints
  parseable bytes (65536, not 64K); zfssendoffsite step-4 strips the
  source pool (removequalifiers=1) so hop copies land one component
  deeper — the depth the replay's deeper candidate probes; delsnap's
  zfscheckagainst rc-5 confirm defaults to N on EOF (feed y's for the
  interactive operator flow — the lab's snaps carry no counterpart
  holds because zfssendoffsite's hold loop is outside the engine).
- Gates on the final tree: 11 bash suites green (incl. 4 engine suites
  + holds 9 tests after +3), offsite e2e/runner 38+ docs-integrity 23
  passed, ruff/shellcheck clean, mkdocs rc 0. Guest destroyed
  post-green (template kept).
- j20 verdicts worth keeping: exact-generation replay loads the key
  (keystatus available); the depth-2 traveled-store lookup replays
  from the offsite copy; missing-key restore WARNs and stays locked;
  same-month offsite retention prunes the stores in lockstep.
- Commit pending user confirmation (this entry rides the later
  SESSION_NOTES commit per the concurrent-session ownership rule).
  Next: P5 probes + capability table + Ubuntu LTS template.

## 2026-11-02 — Backup property fidelity P5: probe matrix + capability
## table + ubuntu template (code green, live runs pending)

- Site config: optional ITF_UBUNTU_ISO_URL/NAME pair (both-or-neither,
  itf- prefix) + ITF_UBUNTU_TEMPLATE_NAME (default itf-template-ubuntu);
  config.example block + validation mirror of the PVE pair.
- guest-lib: itf_autoinstall_render (nocloud user-data + meta-data,
  itfadmin + root-key late-commands, qemu-guest-agent/zfsutils-linux/
  parted, direct /dev/sda layout, serial grub) and
  itf_ubuntu_iso_customize (grub/casper customizer on the PVE model);
  the 7z-extract-with-symlink-restore and El Torito LBA re-patch blocks
  factored OUT of itf_pve_iso_customize into _itf_iso_extract /
  _itf_iso_lba_repatch (shared by both grub-booted ISO customizers).
  iso fetch/upload gain the ubuntu selector.
- stage_os --distro debian|ubuntu: one install flow, per-distro seed
  renderer + boot append + ISO customizer + seed GET check; d-i's UDP
  syslog and the serial kick are debian-only (ubuntu's grub menu is
  multi-entry — a down-arrow kick would boot a different entry).
- template-lib: --profile ubuntu (storage-base placement, no product
  stages, stamp src ubuntu-iso= + the guest's zfs userland version,
  _itf_template_ubuntu_fresh, status/preflight rows). Driver:
  journey run NAME --template storage|compute|ubuntu exports
  ITF_JOURNEY_TEMPLATE.
- j21-zfs-probes.journey: seven probes (p1 -o volblocksize zvol with a
  min(userland,kmod)≥2.3.0 expectation, p2 vbs-on-fs refused, p3
  fidelity plain/-c/-cw with the plain-leg compressratio RECORDED not
  asserted, p4 keylocation prompt vs file://, p5 receive-as-encrypted,
  p6 raw -o refusal, p7 encryptionroot-self) + probes.tsv artifact.
  Registered: journeys/README, itf-coverage row, driver list j01–j21;
  the itf-coverage "OS matrix parked" note now names the ubuntu
  exception.
- zfs_capabilities: FEATURE_MIN_VERSION["recv_o_volblocksize"]=(2,3,0)
  (expectation; live measurement to confirm) + RECEIVE_FAMILY min-
  (userland,kmod) gating; existing entries stay kmod-gated (consumers
  zfs_rewrite/raidz_expansion unaffected).
- Gates: config 15, template 18, driver 43, lab-stages 45, capabilities
  pytest 19 + docs-integrity 23 — all green; shellcheck -S warning +
  ruff clean.
- LIVE RESULTS (2026-11-02 night, as dan):
  - Template build run-20261102-204922 GREEN (19 pass/0 fail) after a
    required pivot: the Ubuntu ISO's grub handoff leaves the kernel
    running but dark+idle on the no-VGA (vga=serial0) guest — three
    boot attempts (patched casper lines, gfxpayload=text, real grub
    serial terminal) all silent incl. earlyprintk, kernel-space RIP
    halted via qm monitor.  PIVOT: direct kernel boot — casper
    kernel+initrd extracted once (itf_ubuntu_boot_setup), qemu
    -kernel/-initrd/-append via qm args (authoritative cmdline), seed
    gains shutdown: poweroff so args are cleared before the installed
    disk boots (the finishing reboot would re-enter the installer).
    itf_ubuntu_iso_customize (genisoimage/LBA path) REMOVED; the
    shared _itf_iso_extract/_itf_iso_lba_repatch stay for PVE.
  - Template stamp: itf-template-ubuntu = vmid 8001, zfs-2.2.2-0ubuntu9.5,
    kernel 6.8.0-147-generic.
  - j21 GREEN on ALL THREE profiles (17 pass/0 fail each):
    ubuntu 2.2.2 (run-214607), storage 2.3.9 (run-220900), compute
    2.4.4 (run-221822).  probes.tsv per run = the measurement record.
  - MEASURED TRUTHS: receive -o volblocksize REFUSED on 2.2.2 AND
    2.3.9 AND 2.4.4 ("invalid property") — the capability pin moved
    from the planned (2,3,0) expectation to 2.5.0 (first possible
    carrier; j21 p1 stands ready to correct it).  Raw receives refuse
    encryption-family -o (encryption/keyformat) but ACCEPT inert ones
    (compression/recordsize — metadata only, blocks stay opaque).
    Raw-received copies land with keylocation=PROMPT on every version
    (not the source's file://) — the manifest replay's set+load is the
    convergent path, validating P1-P3's design.  -c streams into
    compression=off measure 1.00x ratio on all three (arriving blocks
    stored uncompressed; recorded as contrast, not asserted).
    receive-as-encrypted (p5) works on 2.2.2/2.3.9/2.4.4 with no
    capability gate — grounds P6's no-gating plan.
  - Journey-authoring gotchas fixed in-turn: version parse must be
    marker-anchored (ssh banner leads the capture); zfs create
    auto-mounts encrypted datasets (umount before unload-key);
    `zfs get encryption` reports the ALGORITHM (aes-256-gcm), never
    "on".
- Commit pending user confirmation; next: P6 restore-with-encryption,
  then P7 wrap-up.

## Backup property fidelity — P6 restore-with-encryption (2026-11-03)

- Engine (bin/zfs-send-receive): `receive_encryption` (default 'N') +
  `receive_keylocation` globals; entry validation FATALs (exit 8, before
  any transfer) on anything but file:///<non-empty path>; the per-dataset
  source-encryption probe moved OUT of the destination-absent pre-create
  branch to run unconditionally each iteration (`_src_encrypted` — the
  pre-create else-branch only ran for absent destinations, so a guard
  living there would miss existing-destination restores); step-1-only -o
  application in transfer_step (doincrementals!='Y' AND no
  incremental_args AND source not encrypted); resume-token receives
  untouched; dry-run Options line gains "receive as encrypted";
  pre-create skipped (own VERB) so the receive creates the encrypted
  dataset; encrypted sources keep the volume/encrypted VERB verbatim.
- Replay interplay (lib/property-manifest-lib.sh):
  `propmanifest_skip_keylocation='Y'` makes propmanifest_apply_body skip
  the captured keylocation with a WARN — a receive-as-encrypted dataset
  wears the RESTORE key; replaying the source's keylocation would
  repoint load-key at the wrong file (on stewie the old key files exist,
  so the set would silently succeed). restore_runner sets the flag only
  when encryption AND replay are both on.
- GUI (restore_page/feature_config): RESTORE_DEFAULTS variables gain
  receive_encryption 'N' + receive_keylocation '' (lazy merge, no
  CONFIG_VERSION bump — P2 precedent; scheduled profiles inherit for
  free); Advanced expander gains the CheckButton + keylocation entry
  (pause_scrubs wiring pattern — CheckButtons cannot ride the generic
  restore_var_widgets loops: collect uses get_active_text/get_text,
  load's set_active branch check); entry sensitivity bound to the
  checkbox; explicit collect/load; orange non-default styling feeds the
  Advanced label; run gate refuses bad keylocation with a WARN;
  confirmation dialog gains a "received as encrypted" line.
- PRE-EXISTING BUG FIXED IN-THREAD (found by the new dry-run test):
  transfer_step's dry-run branch used `$_sz` without initializing it —
  under set -u a dry-run whose size estimate is unavailable (snapshot
  never created — every GUI dry-run of a fresh label) died rc 1 at the
  Would-send line. `local _tt='' _od=''` → `... _sz=''`.
- Tests: new tests/test-zfs-send-receive-encrecv (8 contracts; worlds
  modeled on the manifest suite; NOTE the pre-create VERB tests need the
  destination-absent variant — the pre-create branch only runs when the
  destination dataset does not exist, and the incremental world's
  receives are -uv NOT -uvs: the forced -s belongs to the full-copy
  branch only); test-zfsreplayprops +2 (skip flag on/off;
  reset_state now neutralizes propmanifest_skip_keylocation);
  test_restore_runner +6; test_restore_page +new classes (fixtures
  _restore_app/_install_default_widgets gained the pair);
  test_feature_config +3. e2e container matrix 9 pass/17 self-skip.
- Docs: restore.md "Receiving a Restore as Encrypted" + Advanced rows;
  gtk-gui.md table + phases; global-variables.md 3 rows; modules.md
  engine table +2 + lib apply_body row; python-modules restore_runner/
  restore_page; messages rows (FATAL, both pre-create VERBs, options
  line, replay keylocation skip, GUI gate WARN); GLOSSARY "receive as
  encrypted". Docs-integrity 23 green.
- Commit pending user confirmation; next: P7 wrap-up (full gate, ruff +
  shellcheck, headline numbers).
