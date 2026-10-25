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

- **unarchive-vm 205 production rerun: EXECUTED 2026-10-23 21:24 —
  0.129.0 machinery validated LIVE.** Step-1 skip verified (3×);
  stewie node.conf converged to iqn.2026-02.local.stewie (backup
  node.conf.bak-20261023T212411); tweety already converged; disks
  mapped onto live targets at existing LUNs (disk3→1/nvme1,
  disk0→11, disk1→12/threeamigos); safe-iscsi-save 36/36 + manifest
  regen + boot config; Step-4 discovery + login (2 sessions) + rescan
  (118 devices). Residual WARNs (expected): Step 3 kept scsi0/scsi3
  by-path lines verbatim — THIS archive predates the F-021 matcher
  fix, so its sidecars carry no DISK_KEY and key_to_disknum is empty;
  the rewrite branch (which j07 proves for new archives) never fired.
  Pre-boot check for the user: in the PVE GUI confirm the kept lines'
  LUNs match the mapping above. efidisk0 also kept — its zvol was not
  in the archive (only disks 0/1/3), so the reference may point at
  missing storage; PVE aborts VM start on a missing disk (known
  hazard class). Possible future improvement: for legacy sidecars
  without DISK_KEY, derive the key→disknum association from the
  line's original (target, LUN) via the LIO lun→backstore map.

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


## 2026-10-23 (late) — ITF cycle: journey --rerun + j08/j09 + discoverability (committed in 0.130.0)

- `itf journey run NAME --rerun`: driver resolves the newest non-active
  same-journey run with guest records → rerun-guests.tsv; the
  stage_from_template rerun branch rolls each guest back to as-cloned
  (verifying presence + checkpoint), re-discovers IP/ssh, and the journey
  replays in full — only the template clone is skipped. Stale snapshots
  newer than as-cloned are delsnapshotted first (qm rollback KEEPS them
  on this stack; the replay's same-name re-snapshot would collide).
  Live-verified: j04 7m24s→2m04s, j07 21m16s→8m09s; both reruns fully
  green; lab guests destroyed after. Traps hit live: listsnapshot name
  is $2 (arrow is $1); the driver's own new run dir must be filtered
  from the source-run glob (it reads "running"); `[[ a == b ]] ||
  continue` KEEPS the equal case — the inverted guard broke that filter.
- j08-prereq-decline + j09-prereq-apt-failure journeys (installer failure
  paths): itf_journey_run_installer gained [expected-rc];
  stage_install factored into prepare_install + install so the failure
  journeys share tooling/download/check. j09 breaks apt via a dead-proxy
  drop-in (deterministic; removed + verified healing at the end). Both
  assert graceful rc-1 abort, the exact user-facing message, and a
  deployment-free guest. NOT yet run live (first runs pending; they need
  a fresh stage_os install each).
- Docs: itf README roadmap Phase 3→complete + 3.5 row; journeys/README
  rerun contract + j06–j09 rows (j06/j07 rows were missing) + j01 row
  trimmed to actual scope; dev-guide "Fast re-verification" section;
  tests/AGENTS.md gained the itf discoverability section. Site rebuilt.
- test-itf-driver: +8 rerun tests (subprocess refusals/spec-writing via
  sandboxed ITF_RUNS_DIR + in-process rollback-branch units), 21 total.
- Full suite green (98 suites). Everything above is uncommitted on top
  of 0.129.0 (a964289).

## 2026-10-23 (latest) — ITF todo 1: stage_os rerun (committed in 0.130.0)

- `itf_journey_stage_os` gained the `--rerun` branch mirroring
  stage_from_template: resolve the guest from rerun-guests.tsv, presence
  + os-installed checkpoint gates, stale-snapshot sweep, rollback, IP/ssh
  re-discovery. j08/j09 iterations skip the ~15–20 min Debian install.
- stage_os-specific trap: the rollback RESTORES the os-installed
  snapshot's VM config, which still carries the installer-time freeze:1
  (only the paired resume ever unfroze it) — so the `set --freeze 0`
  clear must sit BETWEEN rollback and start (a pre-rollback clear
  reverts with the config). Clones hit the same inherited flag via
  itf_guest_clone; here it needed its own step.
- Driver wording generalized (as-cloned / os-installed) in itf usage
  header + rerun-source INFO step; docs updated (tests/AGENTS.md, itf
  README quick-start, journeys/README rerun section, dev-guide Fast
  re-verification).
- test-itf-driver: +2 stage_os tests (rerun rollback ordering incl.
  rollback→freeze-clear→start law; fresh-path dispatch). j08 first live
  run launched (validates the journey as authored + seeds the
  os-installed checkpoint); j08 --rerun live verification follows.
- Live verification (zfstestvm1): j08 fresh 14m03s PASSED (also the
  journey's first-ever live run — validates it as authored, seeds
  os-installed); j08 --rerun 1m37s PASSED, all six rerun-branch steps
  green (presence, checkpoint, rollback, freeze clear, start, IP/ssh —
  same IP rediscovered, proving the guest actually booted unfrozen).
  Lab guest 8001 destroyed after verification.

## 2026-10-23 — Parallel-repo infrastructure (no code changes)

- Discovered pub2 had been created as a linked WORKTREE of pub by mistake
  (pub2/.git was a gitdir file into pub's .git) — shared refs/config caused
  cross-talk between sessions. User confirmed it was unintended; converted
  pub2 to an INDEPENDENT clone at 3713eff: saved the uncommitted
  SESSION_NOTES diff, `git worktree remove --force`, re-cloned pub into the
  pub2 path, `reset --hard` to recover the checkout (first attempt failed
  because the shell cwd was the deleted directory), restored the lane
  checkout (PROMPTQUEUE2) and re-applied the notes patch. pub's working
  tree untouched throughout (its ~30 uncommitted files intact).
- Remotes now: pub2 has origin=GitHub (publication only, per user) +
  sibling remote `pub` (local path); pub has origin + sibling `pub2`.
  Fetch verified both ways. GitHub untouched.
- Lane merge cycle settled: commit each repo's session leftovers
  (SESSION_NOTES/PREEXISTING conflict at merge; interleaved by the agent)
  → in pub, fetch pub2 and merge the lane branch into main → in pub2,
  fetch pub and `git merge --ff-only main`. Re-clone refresh rejected
  (destroys uncommitted/untracked work). Lane discipline: one branch
  worked in only one repo at a time.
- Memory dirs of both projects are now symlinks to
  ~/.zcode/cli/memories/zfsutilities-shared/ (pub's 48 memories + merged
  parallel-lane entries; pre-swap backups as memory-backup-2026-10-23/
  beside each). Future third repo: normal clone + sibling remotes +
  symlink the new project's memory dir to the same store.

## 2026-10-23 — iSCSI resilience M1: pool-resident state export

Milestone M1 of the iSCSI resilience plan (`/NFS1/dan(NFS1)/zfsutilities-plan/
iSCSI resilience plan`), executed alone per the one-milestone-at-a-time cycle.
M2–M6 remain; PREEXISTING.md entry stays until M6.

- `lib/iscsi-lib.sh`: dependency loading now guarded on node-lib's
  `pool_to_target` (zfsdelfs still gets deps loaded; repair/export skip the
  re-load). Added the shared discovery section factored out of
  repair-iscsi-luns: `is_vm_backstore_name`, `parse_backstores`,
  `parse_target_luns`, `discover_zvols`, plus new `parse_target_acls`
  (node-lib probe_target_usage's documented IQN character-class pattern).
- `bin/repair-iscsi-luns`: sources the lib via `REPAIR_ISCSI_LUNS_ISCSI_LIB`
  knob; the four parse functions moved out verbatim (behavior unchanged).
- New `bin/export-iscsi-state` (storage host, silent single-node exit):
  collects live topology, emits deterministic JSON
  (`<pool>/zfsutilities/iscsi-state.json`: version/generated/host/
  iqn_prefix/storage_ip/targets{iqn}{acls,luns{idx→backstore}}/
  backstores{name}{dev,target,lun}), copies node.conf beside it, writes
  every ONLINE pool in pool_list() (dataset created on first use, atomic
  tmp+mv, offline pools WARN+skip, zero-writes=FATAL). `--check` compares
  live vs newest map (by generated timestamp) and prints DRIFT lines
  (exit 1 on drift). Degraded-state fence ADDED beyond the plan text:
  refuses to record fewer backstores than the manifest (fallback: newest
  map) expects unless `--force` — a half-restored LIO tree must not
  overwrite the recovery authority (mirrors safe-iscsi-save's gate).
- `bin/safe-iscsi-save`: invokes export-iscsi-state after manifest
  regen, best-effort (`SAFE_ISCSI_SAVE_EXPORT_ISCSI_STATE` knob; WARN only
  on failure/missing). Map is now as fresh as the last LUN change.
- Tests: new `tests/test-export-iscsi-state` (16 tests incl. golden JSON,
  dataset-create, offline skip, degraded refuse/force, drift, no-map);
  test-safe-iscsi-save extended (hook invoked / failure non-fatal /
  missing warns); test-repair-iscsi-luns sources the real lib via the new
  knob (14 stay green).
- Docs: data-structures.md (iscsi-state.json section), two-node.md
  (export-iscsi-state section + Jump-to + safe-iscsi-save flow step 9 and
  called-modules), messages/index.md (export-iscsi-state + safe-iscsi-save
  hook rows). commands.md unchanged — it holds no two-node command index;
  all two-node scripts document in two-node.md.
- Pool-policy pickup verified at code level (zfsbuildfsarray: no includes
  ⇒ entire pool subtree included, so `<pool>/zfsutilities` is snapshotted
  by pool-wide policies). The in-ITF verification lands with M6's journeys
  (M1 wrote no journey — disclosed in the M1 report).

## 2026-10-23 — M2: reconcile engine (bin/reconcile-iscsi-state)

Executed milestone 2 of the iSCSI-resilience plan (`/NFS1/dan(NFS1)/
zfsutilities-plan/iSCSI resilience plan`), alone, per the milestone cycle.
M3–M6 remain; PREEXISTING.md entry stays until M6.

- New `bin/reconcile-iscsi-state` (storage host, silent single-node exit):
  reads the newest pool map (`--from <file>` for an older snapshot), refuses
  maps generated on another host, then plans/applies create-only recovery per
  map backstore whose zvol exists — backstore create (emulate_tpu=1), LUN at
  the RECORDED number, explicit-mode ACL rebind (demo-mode TPGs left alone,
  self-generating; note printed). Identity conflicts refused per item with
  evidence + continue (dev mismatch / mapped at different target-or-LUN /
  slot held by another backstore / target missing live → setup-iscsi-targets
  pointer); zvol-gone entries skipped. Finishers: encrypted re-flag into
  iscsi-encrypted-luns.conf (conf regresses with the OS disk), manifest
  regen FROM THE ENSURED SET (derived state — keeps safe-iscsi-save's
  degraded gate consistent post-restore), safe-iscsi-save (hook suppressed),
  export-iscsi-state refresh ONLY on complete reconciles (partial refresh
  would destroy skipped entries = the recovery authority), rescan-storage.
  VM-config cross-check via list-vm-disks --gather-vm-info over ssh:
  still-missing refs reported with map identity + item outcome; no-entry
  refs listed with candidate unexported zvols (never guessed); unreachable
  compute host WARNs and continues. `--dry-run` (annotated cross-check,
  exit 1 on conflicts), `--yes`, y/N prompt otherwise. Exit 1 on
  refuses/apply failures/still-missing refs; skips alone exit 0.
- `bin/safe-iscsi-save`: new `SAFE_ISCSI_SAVE_SKIP_EXPORT_ISCSI_STATE=1`
  knob — reconcile owns the map-refresh decision; INFO line when suppressed.
- `lib/iscsi-lib.sh`: `read_json_string_field` + `newest_iscsi_state_map`
  (+ ISCSI_STATE_FILENAME default) moved here from export-iscsi-state so
  export and reconcile resolve the same newest map; export's private copies
  removed (call sites renamed; STATE_FILENAME now derives from the lib
  default so writes and discovery cannot drift).
- Knob resolution moved into `resolve_runtime_paths()` re-run by main() —
  top-level `VAR="${KNOB:-default}"` assignments are evaluated at source
  time in tests, freezing pre-mock defaults (bug caught by the suite).
- Tests: new `tests/test-reconcile-iscsi-state` (19: loads/single-node/
  no-map/host-mismatch/--from missing+explicit/clean restore/dry-run/
  slot-conflict/different-lun/dev-conflict/missing-zvol skip+preserve/
  encrypted re-flag/explicit ACL+mapped_lun/no-entry+candidates/unreachable/
  target-missing/prompt-decline/idempotent). Mock fidelity: targetcli mock
  APPLIES creates to its fixtures so post-apply re-collection inside main()
  sees the new topology; log assertions capture stderr (the eval'd script
  reinstates bashinit's log_msg). Base map JSON rendered once and copied
  (python-startup budget); awk read_json_string_field override in this suite
  (python original covered by test-export-iscsi-state). Suite ~7s (soft
  budget 5s — warning only). test-safe-iscsi-save +1 (suppression honored),
  now 13.
- Docs: two-node.md (reconcile-iscsi-state section + Jump-to + safe-iscsi-save
  step 9 + manifest-actions row), data-structures.md (manifest/encrypted-conf
  maintainer lists + state-map "recovery consumer" bullet),
  messages/index.md (reconcile section + suppression row).

## 2026-10-24 — Development cycle wrap-up (code review pass)

Ran the 7-step wrap-up over the uncommitted M1+M2 working tree.

- Step 1: Zensical recheck — 0.0.72, still no 1.x, hold stands. iSCSI
  resilience entry annotated (M1–M2 landed, uncommitted; M3–M6 stay in the
  milestone cycle — not executed, no milestone named this turn).
- Step 2 (coding policies + shellcheck + ruff): all clean; fixed two
  undeclared loop variables in reconcile-iscsi-state (`init` in
  plan_reconciliation, `zvol` in main). Discovered + parked: coding-policies'
  `set -euo pipefail` vs the unmigrated iSCSI/two-node bashinit family
  (strict mode lands via named campaigns — test-strict-mode guards the 13
  migrated orchestrators; this family was never in one). New PREEXISTING
  entry.
- Step 3 (test review): added test-reconcile-iscsi-state save-failure test —
  which exposed a real defect: a safe-iscsi-save failure did NOT contribute
  to reconcile's exit code (FATAL logged, exit 0). Fixed: `_save_failed` now
  sets rc=1; two-node.md return-code row updated. Added
  test-export-iscsi-state degraded-fence map-fallback test (manifest
  missing — the core post-restore shape). Affected suites green (4 iSCSI +
  8 wider: zfsdelfs, send-receive x2, switch-version, uninstall,
  module-dependencies, strict-mode, no-debug-hooks).
- Step 5: docs diffs reviewed vs implementation (accurate); docs integrity
  23 passed; mkdocs site rebuilt (known Material-vs-MkDocs-2.0 warning only).
- Step 6: full run (no soaks): 100 suites, all passed, 1 env-conditional
  skip (rootcheck as-root on non-root dev host), 0 failures.
- Step 7: codebase frozen at this point (no commit — awaiting user
  confirmation per Hard Rules).

## 2026-10-24 — pub3 lane created (no code changes; work done from pub)

- User created the third lane from the pub session: `/NFS1/dan(NFS1)/
  zfsutilities-pub3`, fully independent repo (init + fetch from pub — own
  object store, no alternates/hardlinks), single branch `pub3` at pub main
  d0dfa43 (0.130.0), tracking `pub/main`. Remotes mirror pub2's: `origin`
  (GitHub, unused) + sibling `pub`. Tags through v0.130.0 fetched.
- pub does NOT yet carry a `pub3` remote (pub untouched this turn, per Hard
  Rules) — add it at the first pub3 lane merge, with user confirmation.
- Memory continuity wired same day: pub3's project memory dir
  (`zfsutilities-pub3-68973cdaeb8a3188`; slug = first 16 hex of sha256 of
  the absolute path, verified against pub/pub2 slugs) symlinks to the shared
  store. Owner's guide + parallel-repo-lanes memory updated (three-way
  documentation agreement).

## 2026-10-24 — M3: restore-time detection (design D)

Executed milestone 3 of the iSCSI-resilience plan (`/NFS1/dan(NFS1)/
zfsutilities-plan/iSCSI resilience plan`), alone, per the milestone cycle.
M4–M6 remain; PREEXISTING.md entry stays until M6.

- `lib/iscsi-lib.sh`: new read-only detector section — findings accumulate
  in `_detect_lines` (indexed, `declare -ga`; one finding = one line), each
  detector skips quietly when its inputs are absent, and everything is
  `set -euo pipefail`-safe because check-prerequisites sources the lib under
  strict mode. Signatures: (a) `detect_stale_lio_files` — saveconfig.json/
  manifest mtime older than the newest VM zvol creation (ISCSI_SAVECONFIG
  knob added; rsync-preserved mtimes make the restore regression visible);
  (b) `detect_vm_refs_missing_live` — compute-host VM (target,LUN) refs
  absent live (uses node-lib's lio_target_iqns + parse_target_luns; gather
  via `iscsi_detect_vm_gather`, overridable with ISCSI_DETECT_VM_REFS_FILE);
  (c) `detect_manifest_without_zvols` — manifest entries with no zvol. Zvol
  universe = discover_zvols' exact `<pool>/proxmox/vm-N-disk-N` shape
  (nested backup copies like fivebays/threeamigos/proxmox never match);
  with pool_list present the scan is scoped to configured pools, else
  all pools (check-prerequisites context). New `ISCSI_LIB_NO_BOOTSTRAP=1`
  escape in the lib bootstrap so standalone consumers (check-prerequisites,
  pre-install, no bashinit) can source it.
- `bin/check-prerequisites --two-node`: runs detectors (a)+(c) after the
  two-node command checks — informational `warn` lines + a pointer to
  setup-iscsi-targets; clean state prints one pass line; findings never
  enter --list-failures and never change the exit code (read-only gate).
- `bin/setup-iscsi-targets`: sources iscsi-lib
  (SETUP_ISCSI_TARGETS_ISCSI_LIB knob); after the summary runs all three
  detectors — on findings prints evidence and offers reconcile-iscsi-state
  (SETUP_ISCSI_TARGETS_RECONCILE knob; y/N; y runs it INTERACTIVELY so its
  own plan+confirm gate still applies; declined or missing stub = WARN;
  accepted-but-failed = FATAL + exit 1). Fresh installs can't false-positive
  (no VM refs yet, OS-disk files absent → detectors skip).
- Tests: test-check-prerequisites +4 (stale-saveconfig warn / dead manifest
  entry with live-zvol non-warn proof / healthy pass line / findings absent
  from --list-failures) — sealed-PATH stubs gained stat/date/realpath/
  dirname + TWO_NODE_STUB + ZFS_VOLUMES_FIXTURE; the zfs fixture stub must
  use builtins only (no `cat` in the sealed PATH — a 127 there silently
  empties the scan; caught by the live-zvol non-warn assert). New
  `tests/test-setup-iscsi-targets` (7, runner pattern per test-safe-iscsi-
  save): healthy no-op+clean detection / postrestore evidence for all three
  signatures / decline / accept / reconcile-failure exit 1 / missing-stub
  degradation / fresh-install create+ACL-flip+saveconfig smoke. Gotcha:
  bash `read -p` prints the prompt only on a TTY — assert the offer through
  surrounding lines, never the prompt text (piped-stdin trap, again).
- Docs: two-node.md (setup-iscsi-targets description/modules/flow step 6/
  return codes + reconcile prerequisites cross-note), commands.md
  (check-prerequisites categories + called modules + structures),
  messages/index.md (13 setup-iscsi-targets rows + 3 check-prerequisites
  rows); docs integrity 23 passed.

## 2026-10-24 — M4: compute-host fence (design C, auto-recover) + activation wiring

- New `bin/check-vm-disk-paths` (compute host, silent single-node exit,
  FATAL off-host/no-qm/non-root): gathers VM-config disk refs incl. efidisk
  via LOCAL `list-vm-disks --gather-vm-info` (no ssh on healthy ticks) and
  checks each expected
  `/dev/disk/by-path/ip-<ip>:3260-iscsi-<iqn>:<target>-lun-<n>` link
  (`-e`, so dangling links count as missing). Per-missing-item WARN lines
  carry the full identity (VM, name, key, IQN, LUN, expected link); healthy
  tick = ONE summary INFO line (journal-churn discipline). `--recover`:
  rescan-storage locally first (advisory — WARN on failure, never blocks),
  re-check, then exactly ONE ssh `reconcile-iscsi-state --yes` on the
  storage host (output streams into the fence journal), re-check; a refused
  reconcile stays report-only (WARN, no retry, never guesses). Exit 1 while
  anything is missing. Knobs: CHECK_VM_DISK_PATHS_{NODE_LIB,LIST_VM_DISKS,
  VM_REFS_FILE,RESCAN_STORAGE,BY_PATH_DIR,SKIP_ROOT,TEST_MODE}.
- `share/two-node/zfsutilities-iscsi-fence.{service,timer}`: oneshot +
  OnBootSec=2min/OnUnitActiveSec=5min timer, WantedBy=timers.target.
  Service sets `ZFSUTILITIES_LOG_INHERIT=Y` — bashinit would otherwise
  create a session log per 5-minute tick (288/day); INHERIT keeps ticks
  journal-only. ExecStart uses the stable `/usr/local/lib/zfsutilities/bin/`
  symlink (same pattern as the rtslib drop-in's ExecStartPost).
- `bin/switch-version` `install_iscsi_fence_units` (called from
  install_wiring after install_rtslib_dropins): gated on `qm` presence +
  node.conf not single-node (subshell source, absent NODE_MODE = legacy
  two-node, with node-lib's two legacy-conf fallbacks; ZFSUTILITIES_-
  SYSTEM_CONFIG_DIR/-LEGACY_* knobs); installs/refreshes both units from
  current/share/two-node (cmp -s idempotence, daemon-reload only on
  change) and `systemctl enable --now` the timer every activation
  (self-healing re-enable). GOTCHA (set-e function-rc trap, again): the
  idempotent run's last `[[ 0 -gt 0 ]] && log` returned 1 from the
  function and killed the errexit test shell — explicit `return 0`.
- `bin/install-two-node`: summary block names the fence + timer (asserted
  in test-installer-flows) and the activation comment block documents both
  systemd integrations.
- `bin/uninstall-zfsutilities` (symmetric removal, follows the
  zfs-cache-warm pattern): stop+disable the fence timer before unit
  removal, remove both units in uninstall_software, fence timer in the
  has_systemd detection and both summary lists — an enabled timer pointing
  at deleted scripts every 5 minutes is exactly the litter the uninstall
  exists to remove.
- Tests: NEW `tests/test-check-vm-disk-paths` (12; eval/TEST_MODE pattern
  per test-reconcile-iscsi-state): loads / single-node silent / wrong-host
  FATAL / no-qm FATAL / bad-option usage / gather-failure FATAL / no-refs
  exit 0 / healthy tick (asserts NO ssh + NO rescan + no WARN) / missing
  report-only / rescan-fixes (no ssh) / reconcile-fixes (asserts the exact
  ssh command incl. --yes, one call) / refused-reconcile report-only (one
  ssh, exit 1). test-switch-version +4 (fence install+enable+refresh with
  version skew + idempotent no-reload / no-qm skip / single-node skip /
  no-conf skip). GOTCHAS: (1) patching my_host twice needs the PRISTINE
  script text — the first patch consumes the `$(hostname -s)` pattern;
  (2) test-lib.sh defines a GLOBAL `qm(){ true; }` mock, so simulating
  qm-absence needs `unset -f qm` inside the subshell — empty PATH alone
  cannot hide a function; (3) ssh-mock side effects must be flag-driven
  (`_ssh_repairs_link`) — redefining ssh() inside one test leaks into the
  next.
- Docs: two-node.md new check-vm-disk-paths section + TOC entry +
  switch-version (fence row in structures, flow step, side effects),
  messages/index.md check-vm-disk-paths section + switch-version fence
  rows + install-two-node summary row.



## 2026-10-24 — 7-step wrap-up over the uncommitted M3+M4 working tree

- Step 1/4: skipped by their own precondition — pub2 (PROMPTQUEUE2), not
  the pub main repo. PREEXISTING.md at 5 entries before and after.
- Step 2 (code review vs coding-policies.md): shellcheck -S warning clean
  on all 11 changed/new bash files; init blocks, knob patterns, guard
  style (TEST_MODE + BASH_SOURCE, family-consistent), log_msg priorities,
  global-output-variable law, switch-version fence wiring mirrors
  install_rtslib_dropins (cmp -s idempotence, reload-on-change). Two
  pre-existing >100-col lines in check-prerequisites (matplotlib warn,
  untouched region) — trivial, suppressed.
- Step 3 (test review): missing coverage found and added —
  test-uninstall-zfsutilities gained fence-unit removal + timer
  stop/disable asserts (systemctl mock now also logs to a file: main runs
  in a subshell, in-memory arrays don't survive) + a lone-fence-timer
  has_systemd test (suite 11→12); test-switch-version gained a structural
  guard on the shipped fence units (stable-path ExecStart + --recover,
  ZFSUTILITIES_LOG_INHERIT=Y, 5-min cadence, timers.target; suite 15→16).
  Cross-referenced suites (fresh-install-guards, upgrade, installer-*
  checks/structure, j04/j05 journeys) verified unaffected — structural or
  stub-based; journey rc=0 holds (fresh installs can't false-positive the
  detectors). Nothing obsolete or incorrect found.
- Step 5 (docs): cycle doc changes verified accurate against the code;
  docs integrity 23 passed; site rebuilt (mkdocs 1.6.1, exit 0, only the
  known mkdocs-material/Zensical-hold warning).
- Step 6 (full suite, no soaks): 102 suites, 5311 passed / 0 failed /
  1 skipped (test-zfslockmanager-soak, excluded by design). 13 rootcheck
  stub dirs leaked in /tmp (known PREEXISTING entry; not swept — outside
  the working directory per Hard Rules).
- Step 7: codebase frozen at this point (no commit — awaiting user
  confirmation per Hard Rules).
