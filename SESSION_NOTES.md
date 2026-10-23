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

- **unarchive-vm 205 live rerun (blocked on this fix's deployment).** The
  2026-10-22 post-0.127.0 rerun from tweety died at Step 1 with
  `bashinit: line 124: BASH_SOURCE[1]: unbound variable` on stewie: the
  on_storage ssh branch runs payloads as stdin scripts (`bash -s`), whose
  top-level frames carry no BASH_SOURCE entry, so the payload's first
  top-level log_msg aborted under set -u. The local (storage-host) branch
  and the hostname-stubbed tests only ever exercised file mode, which is
  why it slipped through. Fix (uncommitted in working tree): guarded the
  six bare `${BASH_SOURCE[1]}` sites (bashinit log_msg/msg_prefix/
  calledbybash, bashreturn, bashdebug _trap_DEBUG, zfssnapbuild
  buildsnapfilename) with `:-` defaults; added red-proven stdin-payload
  regression tests (test-bashinit ×3, test-node-lib payload-mode ×1).
  Zvols remain restored+verified; after this fix deploys, the rerun from
  tweety should skip Step 1 and take the create path on both targets
  (nvme1 + threeamigos) in Step 2 — no enroll-iscsi-pool needed.

- **Guest-probe live validation (fix landed; facility verification in
  flight; production re-run at the next daily production slot).** The
  2026-10-22 paste on stewie was a vacuous pass: the validator's live
  path called collect_alignment_sample with no repositories (pools/
  datasets structurally 0) and pve=UNAVAILABLE with the fetch's failure
  cause discarded. Fixed in the working tree (uncommitted):
  alignment_stats records per-source reasons (sample.pve_failure via an
  errors out-param through read_pve_vm_configs/fetch_pve_vm_options),
  and the validator builds the GUI's real repositories, prints
  per-source state, and exits 1 with reasons on any empty source (usage
  documents the verdict). New itf journey j06-guest-probe-validator
  composes the full j05 two-node lab, runs the validator live (positive:
  populated sample + stopped-VM probe reason), and proves the negative
  control (compute unresolvable → non-zero + printed ssh reason) — the
  permanent fence for the vacuous pass. j05's main was renamed to
  j05_two_node_lab_main with a wrapper (composition, no flow change).
  After this deploys, re-run the validator on stewie: the pve line will
  name the actual failure cause (leading suspect: BatchMode vs an
  agent/passphrase key under sudo's stripped env; interactive
  `sudo ssh root@tweety` was verified working). The GUI consumes
  sample.pve_failure when VM layers are missing (surfacing it in the
  view remains future work).
  **F-019 (found by j06's first run, fixed in-cycle same day):**
  parse_pve_vm_conf skipped by-path disk lines outright, so the guest
  probe saw ZERO VM disks on every two-node install (production
  included) — the feature was blind in the topology it was built for.
  Fix: by-path lines parse with IQN/LUN recorded, resolve to zvol short
  names via the storage host's LIO saveconfig
  (lun_backstore_map/resolve_bypath_disks), drops recorded in
  sample.pve_bypath_dropped. FINDINGS F-019 + repair plan 019; j06
  VERIFIED GREEN run-20261022-215030 (44 steps, 0 fail — probe target
  resolved by-path, qm channel reached, negative control rc=1 with the
  ssh cause named). NOTE for production: after deploy, the Alignment
  view's VM/VM-fs layers will populate for the FIRST time.

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

## 2026-10-22 — zfstestvm start failures: lun-32/33 config-vs-target mismatch

- tweety VM 211/212 (zfstestvm1/2) starts fail stat-ing
  iqn.2026-02.local.stewie:threeamigos-lun-32/-33; the target exports only
  lun-0..31 and no attach event for 32/33 exists in the journal. Not a login
  race — retries cannot succeed. VMs unstartable since Oct 21 09:00.
- Cause frame (user-confirmed): stewie bare-metal restore (weeks-old image)
  Oct 21 ~08:39 + recovery attempt same day. Pre-restore configs referenced
  lun-19/-29, matching the restored target; between Oct 21 09:00 and 14:18 a
  recovery step rewrote them to next-free LUNs 32/33, which never
  materialized on the target. The weeks-old restored disk images sit
  untouched at lun-19 (sdd) and lun-29 (sdb); their partitions were first
  (re)scanned at the 20:03 qmstart attempts, when the triggered session
  rescan read them and host LVM ingested the guest "pve" VG.
- install-two-node ran Oct 21 09:20 → node.conf IQN_PREFIX=iqn.2026-10 vs
  live target iqn.2026-02 (user states the IQN prefix issue is resolved;
  as of 20:25 the live target tweety uses is still iqn.2026-02, node.conf
  still 2026-10 — any re-pointed config refs must use 2026-02).
- Root-only on stewie to finish: show-lun-map, /var/lib/zfsutilities/
  history.json (names the op that wrote 32/33), targetcli luns ls.
- Candidate hardening once the writer is identified: verify the LUN exists
  on the target before committing by-path refs into VM configs.
- No code changes this turn.

## 2026-10-22 — zfstestvm reconnection COMPLETE (root cause corrected)

- VMs 211/212 started cleanly at 20:39, both running. Correction to the
  earlier entry above: the tweety configs were never rewritten — scsi0
  (lun-19/-29) and efidisk0 (lun-13/-27) refs were valid all along; the
  Oct 21 09:00 failure on lun-19 was the boot-time attach race. The real
  gap was scsi1: the 200G itf disks (vm-211-disk-2 / vm-212-disk-2,
  created Oct 4 / Oct 8) referenced lun-32/-33, which the restored stewie
  OS's LIO saveconfig and expected-backstores manifest (both weeks old)
  lacked. The threeamigos pool itself was current — no data loss; the itf
  content survived (2-partition layout visible on sdai/sdaj).
- Repair (manual, user at console): recreate block backstores with
  emulate_tpu=1, map LUNs explicitly at 32/33 (node ACL auto-mapped),
  safe-iscsi-save, session rescan on tweety, qm start. The safe-iscsi-save
  WARN (36 backstores vs 34 manifest) was exactly our +2 delta on an
  otherwise in-sync pair; the script then regenerated the manifest to 36.
- Tooling note: repair-iscsi-luns is purpose-built for missing exports but
  keys off the manifest, which the restore regressed too — by design it
  would only have REPORTED the two zvols as unmanifested, not exported
  them. Post-restore cross-check of compute-host VM configs vs live LUN
  map is the gap worth considering.

## 2026-10-22 — cron.log flooding root cause + drop-in convergence fix

- User report: stewie /var/log/zfsutilities/cron.log still flooding (290,600
  lines / 26 MB, back to 0.59.6-era June entries). The 0.125.0 fence was
  correctly implemented and deployed (0.127.0), but /etc/cron.d/zfsutilities
  on stewie (mtime Sep 22, pre-fence) still used the old plain
  `>> cron.log 2>&1` format: no ZFSUTILITIES_FROM_CRON marker, no stamper, so
  _silence_cron_output never engaged. Same root cause for the missing
  /etc/logrotate.d/zfsutilities: both writers are called only from
  Schedule-page save (schedule_page._regenerate_cron) — deploying a new
  version never converges the persisted /etc files. Log composition ~100%
  duplicated task output (zfs-send-receive/zfscleanup/zfsretain/pv progress),
  all of it also in session logs. tweety unaffected (no drop-in, no cron.log).
- Fix (implemented, uncommitted): cron_manager.build_cron_content extracted;
  cron_manager.converge_scheduler_files(config) re-derives expected cron +
  logrotate drop-in content and rewrites only on difference (missing files
  created only when active profiles exist, so tweety gains none). Called at
  profile_runner main() start (pre-session-log, pre-lock, best-effort) and
  from ZFSUtilitiesWindow._check_startup_config. _silence_cron_output
  additionally engages when fd 1 resolves (os.readlink /proc/self/fd/1) to
  the configured cron_log — the exact shape of a pre-fence cron line — so
  even a stale drop-in stops flooding on the first fixed-version run.
- Existing 26 MB backlog left to the newly-converged logrotate (weekly,
  rotate 8, maxsize 100M, compress) to age out; no truncation.
- Takes effect on stewie when the next release is deployed; the 06:00 run
  self-heals even with the GUI closed.
- Gotcha for tests: get_profile_runner_path() resolves its CALLER's
  directory, so tests priming expected cron content must pin it (patch
  cron_manager.get_profile_runner_path) — repo-layout test files resolve
  tests/python/... vs the module's python/....

## 2026-10-23 — Wrap-up review pass additions (uncommitted, same cycle)

- Code-review fixes on the cycle's uncommitted work: j06 journey message
  strings shortened to the 100-col policy (three lines were over);
  `lun_backstore_map` now skips malformed LUN entries (missing/non-int
  index) instead of raising — collection runs in the GUI's unguarded
  refresh thread; one ruff-format nit in test_alignment_stats.
- Pre-existing issue found and fixed in-cycle (removed from
  PREEXISTING.md): alignment_page `refresh_alignment_view` could strand
  `_alignment_refresh_pending` forever on a collect-thread exception
  (page silently stops refreshing until GUI restart). Now the dashboard
  worker shape: try/except in `_collect` (WARN + sample=None), idle
  finisher applies only non-None samples, flag set last. Regression test
  in test_alignment_page (test_refresh_survives_collection_failure).

## 2026-10-23 — Removed obsolete bin/PVE-send-to-archive (uncommitted)

- User confirmed suspicion; verified before deleting: self-labeled example
  script from the original deployment (threeamigos/proxmox, vm-205 — deleted
  VM), superseded by archive-vm/unarchive-vm, zero callers in bin/lib/python/
  share, no crontab references on stewie (dan-level check; root crontab not
  readable as dan but nothing in-repo or in config references it).
- Removed with it: 3 pattern entries in tests/test-lock-coverage; TOC entry +
  full section in commands.md; lock-table row in lock-manager.md; list mention
  in concurrency-collisions.md; message section + See-also in messages/index.md.
  Historical changelog mention (0.74-era) left as history. docs/site rebuilt
  (mkdocs build) — untracked, regenerates anyway.
- Deployed copies on both hosts keep the (inert) script until the next
  release deploy; nothing invokes it there.
