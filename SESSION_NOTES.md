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
