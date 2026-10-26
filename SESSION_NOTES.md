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

- **j07 found and FIXED a real strict-mode side-effect 2026-10-25
  (zfsdelfs standalone execution); j07 GREEN third run.** The two-node
  lab passed clean (install-two-node, enroll-proxmox-pool, new-vm-disk,
  rescan-storage, safe-iscsi-save — the flipped iSCSI install family is
  healthy), then archive-vm died destroying the zvol: `/root/bashinit:
  mydir: unbound variable` under remove-vm-disk's strict shell. Root
  cause: zfsdelfs is strict AND doubles as a sourced library, so it
  defers its `bashinit` call to the entry function — but its FILE SCOPE
  runs `source_helper iscsi-lib.sh`, and source_helper →
  find_zfsutility_script dereferences $mydir, which only the deferred
  bashinit call would set. Standalone child execution (remove-vm-disk →
  zfsdelfs) = mydir unset = set -u death. Pre-strict, the empty mydir
  silently fell through to the deployed-dir candidates — that fallback
  WAS the working behavior. Fixes: (1) bashinit find_zfsutility_script
  now uses a ${mydir:-} search_dir (class fix — sourced libraries
  tolerate strict callers; a repo scan confirmed zfsdelfs is the only
  script with file-scope source_helper before its bashinit call);
  (2) zfsdelfs sets mydir from its own dirname when unset (guarded if —
  not `[[ ]] &&`, which would abort file-scope -e on the false branch).
  Red-proven against the deployed 0.100.0 copy (dies exactly like the
  guest); regression test added to test-strict-mode. Also fixed en
  route: j07's Stage B assertion grepped the whole log for the deleted
  target's IQN, but 0.130.0's export-iscsi-state state-map hook
  legitimately WARNs naming the missing target — the grep now matches
  the targetcli listing shape ("o- <iqn> "). Third run GREEN end to
  end: lab, archive+remove, IQN drift convergence, destroy+rebuild,
  restored VM boots, decoy-target refusal. The j11/j07 lab guests
  remain on the base hosts for inspection (`itf guest destroy` when
  done). Gotcha for the pattern: any strict script that defers bashinit
  for library use must not resolve siblings at file scope first.

- **GUI payload e2e matrix DELIVERED 2026-10-25 (j11 GREEN, 20/20 +
  residue check; j07 iSCSI-family rerun in flight).** After the two
  offsite GUI smoke-test hotfixes, the exercise infrastructure the user
  asked for landed: one scenario matrix in tests/python/e2e_support.py
  driven by three front ends — the unprivileged dev container (read-only
  layer via share/dev/run-e2e-container, `--device /dev/zfs`; every
  dataset-mutating ioctl needs CAP_SYS_ADMIN, so the mutating scenarios
  self-skip there BY DESIGN), the dev host under sudo
  (tests/python/test_offsite_e2e.py + test_backup_payload_e2e.py, real
  BackupRunner headless through a GLib MainLoop — pty stdin, input-hold
  REQ/ACK, rc semantics), and the ITF guest (journey j11-payload-e2e,
  stdlib driver tests/integrated/e2e/payload-e2e-driver.py, full mutating
  matrix, 9 iterations to green — every failure along the way was
  harness-side; NO product defects found; the checkagainst removal gate
  prompting for unmapped pools is intended behavior, now locked in by the
  prune scenario). Matrix covers: offsite chain steps with holds (both
  smoke shapes), incremental/same-nextsnap reruns, dry-run, rollback,
  includes/excludes, live scrub pause, resume-token recovery, backup
  full/incremental/destructive (user-hold refusal + offsite-* tag
  preservation), prune, rsync wrapper, zfssend/zfsfullcopy/zfsrestore
  live, zfshold round trip. Harness gotchas baked into e2e_support:
  generate_offsite_snapshot_name is minute-resolution (GUI generates once
  per run; the matrix needs a uniqueness suffix); a raw `read -rp` prompt
  glues onto the next input-hold marker line, so CLI orchestrator
  scenarios run protocol-off (engine="cli") exactly as cron/terminal
  would, with known prompts pre-fed; partial receives need a prefix that
  clears the stream header (64 KiB into a 4 MiB-written zvol; 200 bytes
  dies mid-header without creating the dataset); cleanup releases holds
  before destroy and judges success by dataset non-existence (a parent's
  -r may take a registered child first). Payload-scenario additions go in
  e2e_support with level (none/read/mutation) + engine (gui/cli) tags;
  both pytest suites are gi-gated in tests/requirements.manifest
  (test_gui_infrastructure audits that).

- **Offsite GUI smoke test 2026-10-24 23:40 — second strict-mode hotfix
  (FIXED same night).** Step zfstest1→zfstest2 passed after the declare
  fix; step zfstest2→zfstest3 died rc=123 after both transfers verified,
  during holds. Root cause: the GUI offsite step is a Python-built
  payload (python/offsite_runner.py) that sources zfs-send-receive —
  inheriting its strict line — and calls zfshold BARE. zfshold held per
  SUBTREE (zfs list -rt), so nested datasets get the tag from their
  parent's call AND their own; the duplicate `zfs hold` failed "already
  exists" → xargs 123 → -e killed the payload shell before exit $rc.
  Pre-strict the duplicate was silently ignored (2>/dev/null + no -e),
  which the old pipeline comment shows was the intent. Fix: zfshold now
  holds per snapshot — already-present tag → INFO + rc 0; any other
  hold failure → WARN + rc 1 (real failures are now LOUDER than before);
  empty match → rc 0 (historical); lock release always reached. New
  suite tests/test-zfshold (5 tests, includes the exact
  parent-subtree+nested duplicate shape); live-verified against the
  zfstest pools (duplicate call → INFO → rc 0, strict shell survives).
  Gotcha for future GUI payloads: sourcing a strict script turns the
  WHOLE bash -c payload strict — every helper the payload calls bare
  must be strict-tolerant (zfshold now is; zfssendoffsite's own hook was
  already fenced by the campaign).

- **Offsite GUI smoke test 2026-10-24 23:28 found a strict-mode hotfix
  (FIXED same night).** Post-transfer iSCSI rebuild died:
  iscsi-lib.sh:398 "iscsi_teardown: unbound variable" → rc=1 → offsite
  aborted AFTER a successful verified transfer. Root cause is a bash
  quirk, not just a missing guard: `declare -gA name` executed while
  source_helper's function frame is on the stack leaves an element-less
  array that set -u callers cannot `${#name[@]}`-check from any other
  function (top-level reads are fine — which is why declare -p looked
  healthy). Pre-migration callers had no -u, so the quirk was invisible.
  Fix: `declare -gA iscsi_teardown=()` (initializer clears the state);
  same one-line fix applied to installer-lib's installer_failures
  (incidentially safe today — its consumer re-assigns `=()` first — but
  the same landmine). Regression test added to test-strict-mode (static
  grep + live source_helper-under-set-u behavioral check, red-proven
  against the deployed 0.130.0 copy which still carries the bare
  declare). Law codified in coding-policies.md: library global arrays
  MUST use `declare -gA name=()`. NOTE: the DEPLOYED 0.130.0 iscsi-lib
  still has the bare declare — harmless there (its 0.130.0 callers are
  not strict), and the fix ships with the strict scripts in the next
  release; deploy both together as usual.

- **Strict-mode campaign COMPLETED 2026-10-24 wrap-up (PREEXISTING entry
  resolved).** 33 orchestrators flipped to `set -euo pipefail` with
  per-script audit+fence: the 29-script iSCSI/two-node family, plus
  zfssend/zfssendoffsite/zfsfullcopy/zfsrestore (they source
  zfs-send-receive, whose strict line leaks into them at the source
  point). Shared helper libraries stay set-line-free by design and were
  made strict-caller-tolerant instead (zfssnapbuild, zfsbuildfsarray,
  zfsdelallsnaps, zfscommsnap; zfs-diagnose-busy got fences but its set
  line was REVERTED — it is a sourced library, strictness leaked into
  zfsdelsnap). New rule codified in coding-policies.md. Ten suites that
  source/eval now-strict scripts got the `set +euo pipefail` restore
  idiom (test-startdocserver precedent); test-strict-mode's guard list
  grew 13→46. Two latent bugs fixed in-cycle: zfs-send-receive read
  ZFS_DELALLHOLDS_REMAINING_TAGS (uppercase) while zfsdelallholds sets
  the lowercase name — the rollback holds-remaining guard never fired
  (contract-guard test added); new-vm-disk's final statement made
  single-node success runs exit 1. Gotchas for future campaigns: -u is
  NOT suppressed by `|| true`; an unbound-var death inside `$(...)`
  silently yields empty output; runtime `source_helper` of a strict
  file re-executes its set line mid-run (the dryrun suite's
  restore_stderr now fences this). Remaining non-strict zfs* leaf
  utilities are the NEXT named campaign if the user wants one (never
  recorded as an entry — deliberate).

- **j10 release-upgrade journey DELIVERED 2026-10-24 (GREEN, run
  results/run-20261024-142745-j10-release-upgrade, 20 pass/0 fail).**
  Stale storage template (0.118.0) is the old-version carrier — do NOT
  rebuild it for j10; the journey fails fast if the premise breaks.
  Two live discoveries baked into the journey: (1) pre-0.125.0
  deployments have no upgrade-zfsutilities on PATH — the upgrader runs
  from the downloaded new tree; (2) F-025: untagged GitHub releases
  broke the change-scan pristine fallback. **F-025 FIXED same day
  (plan 021 part 1, user-approved): trust-on-first-upgrade manifest
  captured on LOCAL and remote hosts when no baseline is obtainable;
  red/green vs HEAD; j10 regreened with the fix in the tarball
  (run-20261024-150441, 20 pass/0 fail). Part 2 (tag hygiene) not
  selected.** itf_guest_get added to ssh-lib (guest→dev file pull,
  mirrors guest_put). One unreproduced dev-host transient: the itf
  HTTP server vanished without a traceback between two guest fetches
  2 s apart (run-20261024-144838, instant ECONNREFUSED; ping fine);
  immediate --rerun green — if it recurs, suspect the dev host, not
  the journey.

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



## 2026-10-25 — Development cycle wrap-up (code review pass)

Ran the 7-step wrap-up over the uncommitted cycle tree (strict-mode
campaign + hotfixes, j10/F-025, payload e2e matrix).

- Step 1/4: PREEXISTING triage — no actionable entries (Zensical hold
  rechecked at 0.0.72, still no 1.x; infra-vdev abeyance; iSCSI M5–M6
  user-cycle). Zensical recheck line added; iSCSI entry's progress note
  refreshed (M3+M4 shipped in the pub2 lane, 0.131.0 unpushed).
- Step 2 (standards): ruff had 23 violations, all in the new e2e Python
  files — fixed (unused noqa/import bindings, percent/format → f-strings,
  import sort, subprocess check=False on the wrapper that implements its
  own check, four unused local bindings dropped keeping the side-effect
  calls); 3 new files reformatted (repo now 254/254 format-clean);
  run-e2e-container's 111-char docker line restructured (pytest command
  built in a variable — the SC2086 directive became unnecessary) and the
  documented shellcheck glob extended with share/dev/* in
  coding-policies.md; the ZFSU-INPUT marker regex in e2e_support got its
  policy-required profuse documentation. shellcheck -S warning clean over
  the full documented glob.
- Step 3 (tests): suites reviewed — none obsolete; the ten
  strict-leak restore idioms and the new suites are consistent. Added the
  missing structural guard test_final_statement_is_exit_safe to
  test-strict-mode (a strict script's last statement may not be an
  unfenced A && B chain — the new-vm-disk single-node rc-1 bug class);
  red-proven by reintroducing the bug shape (fails with the diagnostic),
  green when restored. e2e pytest gating verified as non-root (mutation
  scenarios self-skip by design); zfshold-referencing python suites green.
- Step 5 (docs): added zfshold's two new message rows (duplicate INFO /
  failure WARN) and corrected the module section's behavior line and
  return-code table; added the upgrade trust-on-first-upgrade
  baseline-capture INFO row (the no-baseline WARN row stays — that branch
  remains); coding-policies shellcheck glob update (step 2). Docs
  integrity suite passed; mkdocs site rebuilt (known Material-vs-MkDocs-2.0
  warning only).
- Step 6 (full run, no soaks): all suites passed; single bash
  env-conditional skip (rootcheck as-root on the non-root dev host) plus
  the e2e suites' pool-gated scenario skips; five suites slightly over
  the soft 5s timing budget (warning only, no failures).
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

## 2026-10-25 — M5: compute-host config repair (mirror half)

Executed milestone 5 of the iSCSI-resilience plan (`/NFS1/dan(NFS1)/
zfsutilities-plan/iSCSI resilience plan`), alone, per the milestone cycle.
M6 remains; PREEXISTING.md entry stays until M6.

- New `bin/repair-vm-disk-refs` (compute host, `set -euo pipefail`,
  silent single-node exit, FATAL off-host/no-qm/non-root): gathers iSCSI
  disk refs DIRECTLY from `/etc/pve/qemu-server/*.conf` (needs the whole
  line for the option suffix — the --gather-vm-info records don't carry
  it), then exactly TWO ssh round trips to the storage host: newest pool
  map via `export-iscsi-state --print-map` (new read-only dump mode) and
  live topology via `list-vm-disks --gather-lun-info`. Identity chain:
  config (short,lun) → map backstore (owning-VMID check) → live (short,lun);
  rewrite ONLY when the VM's OWN disk sits elsewhere, via
  `qm set <vmid> --<key> <new-by-path>,<orig options>` (suffix kept
  byte-for-byte; split at the volume's first comma — by-path tokens
  contain no commas). Refuses with evidence: no map entry / cross-VM
  backstore / two refs → one backstore (pass 2 after owning-VMID) /
  not live (reconcile pointer) / VM running or status unknown
  (qm status cached per VM). Map sanity: host ≠ storage_host or iqn_prefix/
  storage_ip ≠ node.conf → refuse-all. Post-apply verification: each new
  by-path link must exist; missing → one rescan-storage → recheck; still
  missing = FATAL (the VM-start-abort state this tool prevents). rc=1 on
  any refusal even when other rewrites succeeded (reconcile precedent).
  Knobs: REPAIR_VM_DISK_REFS_{CONF_DIR,BY_PATH_DIR,LKG_MAP_FILE,
  LIVE_MAP_FILE,RESCAN_STORAGE,NODE_LIB,ISCSI_LIB,SKIP_ROOT,TEST_MODE}.
- `bin/export-iscsi-state`: new `--print-map` (mutually exclusive with
  --check, checked in main() not top level — tests toggle the variables
  after eval): dumps the newest pool map to stdout as PURE JSON (branch
  runs before the banner; log_msg is stderr so stdout stays clean),
  skips the targetcli gate and live collection entirely (compute-host
  fetch must not depend on targetcli there). No writes, no degraded gate.
- Tests: NEW `tests/test-repair-vm-disk-refs` (28): loads/single-node/
  wrong-host/no-qm/usage; no-refs quiet + zero ssh; clean rewrite with
  exact `qm set` line (options byte-for-byte, exactly one call, no old
  LUN); bare volume (no invented comma); efidisk; all five refusal cases
  + unknown-status; already-correct; dry-run (rc=1 with refusals, rc=0
  clean); decline; two-ssh assertion; map host/prefix mismatch; fetch
  failure; empty map; verify-rescan-fixes / still-missing-fails;
  qm-set-failure; local+unparseable refs skipped. test-export-iscsi-state
  +4 (newest-wins dump + read-only proof / no-map / no-targetcli gate /
  mutual exclusion). test-strict-mode: repair-vm-disk-refs registered.
  Gotchas found: (1) `_refuse_lines+=("a" "b")` stores TWO elements —
  evidence strings must be built with `msg+=` accumulation (reconcile
  precedent) or assertions crossing the boundary fail; (2) make the
  verify success line print after the rescan-recovery path too, not only
  the early all-present branch.
- Docs: two-node.md — new repair-vm-disk-refs section (after the fence),
  export-iscsi-state --print-map (synopsis/args/flow/rc), Jump to entries,
  and a new `## Bare-Metal Restore Runbook (two-node)` section covering
  both halves (scenario A storage restore via fence/reconcile, scenario B
  compute restore via repair-vm-disk-refs, scenario C both, coexistence
  note); messages/index.md — new repair-vm-disk-refs block + export
  --print-map rows.



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

## 2026-10-24 — Schedule page: drop "(weekly)" bucket word from Next Run

User request: the parenthesized retention-bucket word at the end of the
Next Run column ("(weekly)" on root-backup-dailybackup's Sunday run) reads
as a run frequency; remove it.

- `python/schedule_page.py`: `_next_run_strings` no longer appends the
  bucket word; `_BUCKET_WORDS` and the `snapshot_naming.bucket_for` import
  removed (no other users). The conditional UTC-edge translation hint
  ("· 23:30 Sat = 03:30 Sun UTC — names dated Sun") STAYS — user objection
  was only the frequency misreading; hint phrasing doesn't carry it.
  Label still gates the hint for snapshot-creating profile types.
- Tests: TestNextRunBucketDecoration → TestNextRunDecoration (pins no
  bucket word; edge-hint behavior unchanged). Build-rows test now uses an
  edge time so backup (hint) vs retention (bare) rows stay distinguishable
  — and needed a `_NEXT_RUN_CACHE.clear()` it previously lucked past: the
  retention row's key (empty cron, no label) collided with the fallback
  string cached by TestNextRunStrings in the same UTC minute.
- Docs: gtk-gui.md Next Run column row + decoration paragraph;
  python-modules.md schedule_page.py overview + `_next_run_strings` row.
  Changelog untouched (Hard Rule).

## 2026-10-24 — GUI: Performance tab moved to bottom of the sidebar

User request: move the Performance tab to the bottom of the navigation
column.

- `python/zfsutilities_gui.py`: `("memory", "Performance", …)` moved from
  position 9 (first of the four infrastructure tabs) to the end of
  `PAGE_BUILDERS`; comment updated. Internal stack name "memory" unchanged
  (persisted config key for pop-out state/interval — nothing stored moves).
- Test: `TestSidebarPageOrder.test_infrastructure_tabs_are_last` now pins
  `names[-4:] == ["disks", "pools", "datasets", "memory"]`.
- Docs: gtk-gui.md Tabs table row moved last + intro sentence says
  "Performance last"; mkdocs site rebuilt after the edit.

## 2026-10-24 — Dashboard: merged Tasks list (waiting/running/completed)

User request: combine Recent Operations + Running Tasks into one "Tasks"
tree view with a new Waiting capability; rows reverse-chronological;
status = "Waiting since <time>" / "Running since <start> (+progress)" /
highest message level; keep the 10-task widget size; only completed rows
removable; Cancel must work for waiting rows too.

- `python/dashboard_page.py`: one Tasks frame replaces both sections
  (`_refresh_tasks_section` merges collector output + newest history
  entries; hidden cols state/task_key/log_file/completed-key; sort by
  row time, timeless rows on top). Collector gains additive `started`
  and `wait_started` keys (schema otherwise unchanged — the close-time
  `_collect_abortable_tasks` still parses `status` PIDs). New time
  helpers `_zfs_time_to_iso` (zpool/`ps lstart=` format), 
  `_epoch_to_local_iso`, `_iso_to_epoch`; ZFS-op start parsed from the
  pool section's "in progress since" line; scheduled start from
  `ps -o lstart=`. Widget = `capped_treeview_scroll(row_target=10,
  fixed_rows=True)` — constant ten-row window, scrolls beyond.
- Dismissal: Remove Selected button (action_dispatch) removes completed
  rows only; keys (log_file, else timestamp|name) persisted under
  dashboard config `dismissed_tasks` (DASHBOARD_DEFAULTS entry added;
  get_dashboard_config back-fills existing configs), filtered on refresh,
  pruned to the ten-entry window. History file untouched — Logs-tab
  success-rate metrics unaffected.
- Waiting cancel: GUI runners already SIGINT the lock wait
  (`BackupRunner.cancel`); `_cancel_task` gained the `profile-wait:`
  branch — re-queries `list_running_profiles()` at click time and
  SIGTERMs the live waiting PID (vanished entry → WARN). Lingering
  .waiting files self-heal (loader ignores dead PIDs).
- `python/backup_runner.py`: `_lock_wait_started` set at both
  `_in_lock_wait` transitions (stdout + stderr), cleared on release,
  reset in start().
- Tests: test_dashboard_page merged-section suite (rows, ordering,
  statuses, dismissal, gating, cancel incl. profile-wait), collector
  time-key tests, time/progress helpers; test_backup_runner
  `_lock_wait_started` transitions. pyproject: DTZ007 joined the
  project's naive-datetime ignore family.
- Docs: gtk-gui.md Tasks section (intro, cancel table incl. waiting,
  Remove subsection, Actions table + Remove row, surface-test pointer),
  profiles.md waiting-profile pointer, python-modules.md dashboard_page
  rows. Changelog untouched (Hard Rule).

## 2026-10-24 — Development cycle wrap-up (7-step, pub3)

Ran the 7-step wrap-up over the uncommitted working tree (Dashboard
Tasks merge + Performance-tab move + Next Run bucket-word removal).

- Step 1/4: skipped — the step's own note restricts it to the PUB
  (main branch) repository; this lane is pub3. Disclosed in the report.
- Step 2 (coding standards): ruff check + format clean repo-wide. New
  code verified against coding-policies.md (documented >10-char regex,
  log_msg priorities, naming, no site-specific data, no deprecated
  APIs, DTZ007 consistent with the naive-datetime ignore family). One
  fix: gui_helpers.capped_treeview_scroll docstring still called
  fixed_rows=False "the Dashboard convention" — reworded (Tasks now
  pins fixed_rows=True/ten rows; Active Locks keeps natural height).
- Step 3 (tests): suites reviewed; three coverage gaps closed —
  TestOnDashboardCancelSelected (direct handler tests: col-5 reads,
  waiting+running dispatch, no-selection WARN, no-cancellable no-timeout),
  TestDashboardPageSpec/Handlers Remove Selected button+handler wiring,
  TestDashboardConfig dismissed_tasks default + legacy-config back-fill.
  Affected suites green before moving on.
- Step 5 (docs): all three modified docs verified against final code
  (Type column values match collector literals exactly; Tasks/Remove/
  cancel sections accurate; stale "Recent Operations"/"Running Tasks"
  wording exists only in changelog history — left). test_docs_integrity
  green; mkdocs site rebuilt (known mkdocs-material warning, exit 0).
- Step 6 (full suite, no soaks): 100 suites — all passed, one
  environment skip (rootcheck root-branch, suite runs as non-root).
  No failures to resolve; no new PREEXISTING entries.
- Step 7: codebase frozen at this point (no commit — awaiting user
  confirmation per Hard Rules).

## 2026-10-24 — Release 0.131.0 (pre-deployment continuation, steps 8–10)

- Step 8: VERSION → 0.131.0; changelog section added (merged Tasks
  list, Remove Selected, waiting-task cancel, Performance tab last,
  Next Run bucket word removed); test_docs_integrity green after the
  edit. __pycache__ swept (4 dirs). With-soak gate run 1: one failure
  — test-unarchive-vm Test 26, the ssh-mock existence probe missed
  the in-memory fs_list under ~2x parallel load; product code FATALed
  correctly for the answer it got. Not a product defect: 4 standalone
  reruns green + the suite green in the same-day non-soak run; flake
  filed in PREEXISTING.md (post-mortem log was swept before
  inspection — if it recurs, capture it immediately). Gate rerun 2:
  100 suites, all passed, 0 failed. __pycache__ swept again post-run.
- Step 9: no code changes after the gate.
- Step 10: git add -A + release commit per the numbered-step
  confirmation.

## 2026-10-25 — pub3 lane merged into pub2 (PROMPTQUEUE2)

- User-requested cross-lane merge: pub3 tip 0743b5d merged into this
  lane. Brings Release 0.131.0 Dashboard work (merged Tasks list,
  Remove Selected, waiting-task cancel, Performance tab last, Next Run
  bucket word removed), pub3's PREEXISTING infra-vdev entry retirement,
  and pub main's d0dfa43 install-test-deps Pygments fix (sat between
  the merge base ad27709 and pub3's tip).
- Conflicts only in SESSION_NOTES.md and the changelog 0.131.0 section;
  both resolved by union — both lanes' entries kept, changelog
  sub-sections in Added → Changed → Tests → Documentation order. All
  python/bash code auto-merged with no manual resolution. VERSION
  auto-resolved to the common 0.131.0. Not pushed, not deployed.

## 2026-10-25 — M6: iSCSI resilience verification + closure

- ITF journeys (the campaign's end-to-end verification), both GREEN live
  on the two-node lab (dev-tarball, run logs under
  tests/integrated/results/run-20261025-*):
  - NEW j13-iscsi-storage-restore: composes the j05 lab; stages the
    2026-10 incident shape (backup-point saveconfig/manifest set aside
    with mtimes preserved, vm-101-disk-1 created through new-vm-disk,
    then live LIO + BOTH OS-disk files regressed); verifies the M3
    detector WARN, the interactive reconcile (y feed) rebuilding the
    backstore at LUN 1 exactly with LUN 0 untouched (manifest,
    saveconfig, pool map, compute rescan all refreshed), the lun-1
    by-path link back, and the VM boot proof.
  - NEW j14-iscsi-fence-recover: same lab + staging helper (reused from
    j13 by sourcing it); verifies the fence units are installed and
    enabled on the compute host, the manual detection tick (exit 1,
    full VM/key/IQN/LUN identity), recovery through the INSTALLED unit
    (`systemctl start` runs the timer's ExecStart: local rescan → real
    ssh reconcile on the regressed storage guest → link back → exit 0),
    and the healthy tick after recovery.
  - Numbered j13/j14 (not j12): pub's working tree carries an
    uncommitted j12-interrupted-upgrade journey; skipping the number
    keeps the lanes collision-free at the next merge.
- Live-verified gotchas baked into the journeys: (1) a plain iSCSI
  session rescan does NOT drop a server-side-deleted LUN's device on
  this stack (dmesg shows "Logical unit not supported" but the node and
  by-path link linger) — the honest regression staging logs the session
  out and back in, modeling the storage-host reboot's session drop;
  (2) the re-added LUN after reconcile IS picked up by the session
  rescan (reconcile's own compute rescan), so recovery needs no manual
  step.
- F-026 (fixed in-cycle, found by j14's wiring step): on a FRESH
  two-node install the compute host never got the fence units —
  install-two-node activates it (Step 5) before copying node.conf to it
  (Step 6), and switch-version's fence gate treated "no node config
  anywhere" as single-node and silently skipped. Gate now installs
  whenever qm is present and no config explicitly says single-node (a
  genuine single-node host always has node.conf at activation —
  install-single-node writes it before activating); the M4 unit test
  that pinned the old skip was flipped to require install+enable.
  two-node.md's switch-version fence row updated for the semantics.
- test-itf-driver journey list extended (j11 had drifted out; j13/j14
  added); journeys README table, tests/AGENTS.md list, and the
  integrated README roadmap (phase 3.7) updated; itf site config +
  ISO cache seeded for pub2 (copied from pub's environment values —
  pub2's first live journey runs in this tree).
- Closure: PREEXISTING.md iSCSI-resilience entry REMOVED (M1–M6
  complete; 3 entries remain). Full suite green. No production changes;
  no VERSION/changelog edits (hard rules).

## 2026-10-25 — itf run lock: one run at a time, enforced by the driver

- Follow-up to the M6 cross-lane collision (pub2's j14 vs pub's j09 on
  the shared port-8000 serve; pub recorded it as a PREEXISTING entry,
  discovered in the j09 turn). User direction: loud documentation is not
  enough — agents cannot be relied on to notice; make the mechanism.
  Decision (user offered lock-vs-tolerate, agent picked serialize):
  concurrent EXECUTION cannot be made safe (fixed HTTP port, shared
  UDP-514 syslog listener, base RAM/itfguests budget for one two-node
  lab, VMID races, template-build conflicts), so the driver serializes
  execution while TOLERATING concurrent starters — they queue.
- NEW tests/integrated/lib/runlock-lib.sh: machine-global flock
  (/tmp/itf-active-run.lock, env ITF_RUN_LOCK) held on fd 9 by the run's
  own process — kernel-released on any death, so no stale-lock state and
  no cleanup verb exists. Holder record in the file (description, pid,
  start time, repo root) is shown while held: waiting starters,
  refusals, and `itf status`'s new `== run lock ==` section all name the
  holder ACROSS LANES (fixes the "one lane cannot see another lane's
  run" visibility gap). Default behavior: WAIT with a heartbeat every
  30 s up to ITF_RUNLOCK_WAIT=7200; 0 refuses instantly; missing flock
  refuses loudly (never an unfenced run). Deliberately NOT the product's
  dataset lock manager (zfslockctl/zfs_lock_manager key by dataset for
  root product ops; this keys by dev host, unprivileged, no product env).
- Driver wiring: `journey run` (after journey validation, before
  report_init — a refused/queued run leaves no run dir) and
  `template build`. Tests: test-itf-driver +5 (holder record + auto
  release; WAIT=0 refusal naming holder; wait-budget timeout with
  heartbeat + bound; driver-level journey refusal rc 2 + no run dir;
  status free/held). Suite fixture sandboxes ITF_RUN_LOCK — a live real
  run can no longer park the suite behind the real fence (the bad-profile
  and --rerun driver tests reach the lock).
- Docs: integrated README (layout row + quick-start fence note),
  tests/AGENTS.md (itf bullet), developer guide ("One run at a time: the
  run lock"). Affected suites green; `itf status` verified live (free).
- pub's PREEXISTING entry ("itf harness, cross-lane concurrency") stays
  for now — this lane cannot edit pub; remove it at the lane merge when
  the lock reaches pub (its base-host-lock candidate was superseded by
  the dev-host flock: no guarded-verb extension, no ssh-held lock
  lifetime problem, no staleness class).

## 2026-10-25 — itf acquire-time orphan fence (run lock, part 2)

- The gap the flock cannot close: the lock fences dev-side processes,
  but the run's GUESTS live on zfstestvm1/2 and do not die with the dev
  host. After a mid-run dev restart the kernel releases the lock
  correctly (no stale-lock class) while the interrupted run's guests
  keep consuming base RAM/VMIDs — a resumed session's next run would
  acquire cleanly and stack a second lab on the orphans, with only
  advisory notices (`itf status`, preflight INFO) in the way. User
  direction: make it structural (option a — acquire-time fence; the
  auto-sweep option b and pub's base-held-lock option c were rejected:
  b destroys state a human may want post-mortem, c recreates the
  stale-lock class on the wrong machine).
- NEW `itf_runlock_orphan_fence` in runlock-lib.sh, run by `journey run`
  and `template build` WHILE HOLDING the lock: scan this tree's runs for
  INTERRUPTED ones with recorded guests, check each (base, VMID) against
  that base's own `qm list` — the base is the authority, so the check is
  correct across dev restarts — and refuse the start naming each
  leftover with both recoveries (`itf journey run <same> --rerun` to
  reuse — the caller line in meta.txt drives the hint — or
  `itf guest destroy` per leftover). Semantics: done runs are invisible
  by design (their guests are the kept lab of the run→fix→rerun loop);
  a rerun exempts exactly its takeover pairs (rerun-guests.tsv) and
  contacts no base when all candidates are exempt; no interrupted runs
  → zero base contact (healthy path free); unreachable base fails
  CLOSED (unverified is not clean); ITF_DRY_RUN skips with a notice.
  Per-tree scope is deliberate: cross-lane leftovers are that lane's
  kept-or-orphaned labs and cannot be distinguished from here (the lock
  serializes lanes, preflight still INFOs foreign guests).
- Driver wiring: journey run fences between rerun-prepare and
  journey_main (the "running" banner moved after the fence); template
  build fences right after report_init. Refusals are rc 2 with a FAIL
  step + finished report (audit trail), and the fence releases fd 9
  itself.
- Gotchas hit: (1) parsing `caller: journey:name` with
  `awk -F': *' {print $2}` yields just "journey" — the value embeds a
  colon; strip the prefix instead (`sub(/^caller:[ \t]*/,"")`). (2)
  assert_contains chains flip a failed test back to PASS-display when a
  LATER assert in the same test passes — the runner's fail COUNT is the
  truth, not the per-test PASS tag (watch the counts).
- Tests: test-itf-driver +9 (unit: refuse+both recoveries, pass when
  destroyed, healthy-dir zero queries, rerun-exemption partial +
  one-list-per-base, all-exempt zero queries, unreachable fail-closed;
  dispatch: journey rc 2 fail-closed over .invalid, template build rc 2
  with NO --rerun hint, rerun-of-own-source not fenced + spec written).
  Red-proofed (8 red pre-implementation). run_itf now also sandboxes
  ITF_RUNS_DIR (fence reads run records; keeps driver tests off the dev
  host's real results/bases). `_plant_run` gained an `interrupted`
  state (reaped-child pid + no finished: line).
- Docs: integrated README (layout row + quick-start note), developer
  guide (run-lock section + fence paragraph), journeys/README (--rerun
  bullet), tests/AGENTS.md (itf bullet). Live check: pub2's results dir
  has no interrupted runs today — the next real run pays the fence's
  zero-cost fast path.

## 2026-10-25 — Development-cycle wrap-up (7-step, pub2 lane)

- Step 1/4 (PREEXISTING resolution): skipped by precondition both times —
  pub2/PROMPTQUEUE2 is a lane, not the pub main repo. File stands at 3
  entries (Zensical hold, pub3 with-soak flake, rootcheck-stub /tmp
  litter); none actionable from this lane.
- Step 2 (standards): full-tree shellcheck per the policy invocation is
  clean. One violation fixed: runlock-lib.sh carried a 115-col line; the
  first backslash wrap was semantically broken (SC2289 — the continuation
  preserves the next line's leading spaces OUTSIDE the quotes, which
  would terminate the assignment and execute the remainder as a command)
  and was replaced with `+=` accumulation (byte-identical product).
  test-itf-driver green after the fix. All other new code matches the
  policies (strict mode, sourced-lib laws, log_msg priorities, TEST_MODE
  guards per the iSCSI family, shellcheck source= directives in j13/j14).
- Step 3 (test suites): added the missing storage-IP map-mismatch test
  to test-repair-vm-disk-refs (the script's third sanity gate had no
  refusal test; host and IQN-prefix both had one) — red-proofed by
  disabling the gate (exactly the new test fails) and restored.
  Journey list verified in sync with disk (13 journeys; j12 reserved
  for pub's uncommitted journey). No obsolete or stale tests. The
  flipped switch-version fence test (skips→installs) is correct per
  F-026.
- Step 5 (docs): all three campaign docs diffs verified against the
  code (messages rows match script strings; two-node flow/rc/fence rows
  match implementation). testing.md's suite catalog was missing entries
  — the new suite plus pre-existing drift; all undocumented suites
  added (itf cluster, export/reconcile/repair iSCSI trio, check-vm-disk-
  paths, strict-mode, snapshot-names, rsync-dailybackup, setup-iscsi-
  targets, vm-disk-two-node-gate, zfshold); catalog now complete both
  directions. test_docs_integrity.py green; mkdocs build clean (known
  mkdocs-material banner only; site/ is gitignored by design).
- Step 6: full suite without soaks (log: /tmp/zfs-run-wrapup.log).
- Step 7: codebase frozen at this point.
