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

- **Per-enclosure I/O rate governance — Phases 1+2 DONE (2026-10-25,
  UNCOMMITTED, awaiting user review gate).** Executing the plan at
  `/NFS1/dan(NFS1)/zfsutilities-plan/I-O rate control implementation plan`
  one phase per turn (6-phase campaign; stop at review gate after each).
  **Phase 1** landed `python/enclosure_inventory.py` (lsblk transport scan +
  udevadm DEVPATH/WWN per disk + pool-topology leaf join; USB grouping by
  hub directly under a root USB hub, location `usb2/2-2` includes the root
  hub because port numbers repeat across root hubs; eSATA grouping by
  deepest PCI function with boot-controller exclusion via
  DiskRepository._find_boot_disk_path; identity = sha256[:10] of sorted
  member WWNs; groups with zero WWNs are skipped+WARN; sync TTL cache 30 s;
  headless `python3 python/enclosure_inventory.py` printer).
  `feature_config` gained `ENCLOSURES_DEFAULTS` + get/save_enclosures_config
  ({id: {name, max_rate}}); migration v30 seeds `{"enclosures": {}}`. Two
  real bugs the fixtures caught: PCI segments are HEX (`0000:00:1f.2` —
  `\d` regex missed 1f/1d), and stewie's pools sit on by-id PARTITION
  leaves (`…-part1` → /dev/sde1) while members are whole disks, so
  `_pools_for_disk` is partition-suffix aware (`1` for letter-final names,
  `p1` only for digit-final names so sibling `nvme0n11` never matches).
  Stewie gate (read-only, module piped via ssh stdin against deployed
  0.132.0 python/): usb2/2-2 = 5 disks → fivebays, usb2/2-6 = 5 disks →
  threeamigos (both enclosures genuinely hold 5 USB disks — verified
  against raw lsblk; "threeamigos" is a historical name), boot controller
  0000:00:17.0 excluded. Phase 4 note: DiskInventoryCache's own disk→pool
  join (disks_page) has the same partition-leaf gap for whole-disk rows —
  fix there when Phase 4 wires enclosure attach.
  **Phase 2** landed the inert rate-resolution core: `lib/enclosure_rate.py`
  (patterned on pace_stream.py; sys.path bootstrap adds its own dir for
  `pace_stream` and `../python` for the python layer — repo and deployed
  trees are identical bin/lib/python/share) holds the single min()
  (`min_rate` compares numerically via `pace_stream.parse_rate`, returns the
  winner's original string; `valid_rate_limit` stays the GUI validator),
  the pure resolver (`resolve_effective_rate`), the live fail-open wrapper
  `effective_rate()` for Python callers, and the CLI
  `enclosure_rate.py [--min-with <rate>] <pool-or-dataset>...` (pool = first
  path component, snapshot suffix ignored; empty output = unlimited; rc 0
  ok / 2 usage / 1 resolver failure so bash callers can fail open).
  `ZfsRepository.effective_transfer_rate(pools, activity_rate)` is the
  Python seam — delegates to the same module via an importlib-by-path
  loader (`_enclosure_rate_module`, cached; `path_utils.find_script`
  resolves lib/ beside python/), with an injectable `enclosure_inventory`
  constructor arg built lazily as `EnclosureInventory(zfs_repository=self)`.
  Tests: new `tests/python/test_enclosure_rate.py`; `test_zfs_repository.py`
  gained `TestEffectiveTransferRate` (config hermetic by patching
  `config_core.load_config` — the lazy import in the lib module re-reads the
  patched attribute). Demo gate green under synthetic PATH-faked
  lsblk/udevadm/zpool/findmnt + env-pointed config: USB cap < activity,
  eSATA cap pulled in via destination pool, uncapped ignored, unlimited
  empty output, activity-lower-than-cap, missing-lsblk → rc 1, failing
  lsblk → activity rate rc 0. Demo gotchas (not code bugs): `load_config`
  as non-root silently returns DEFAULTS when the real /run/lock dir is
  unwritable (`config_lock_read` PermissionError swallowed by the
  any-error→defaults contract) — demo needs `ZFSUTILITIES_LOCK_DIR`
  override; production CLIs run as root. And a failing lsblk never reaches
  rc 1 — Phase 1's scan fails soft (no enclosures + WARN) so the CLI
  resolves to the activity rate at rc 0; only hard errors (missing binary)
  exit 1. Both directions are fail-open, so callers see the same transfer
  behavior either way. Docs: data-structures.md resolver contract (CLI
  semantics, grammar, fail-open) + python-modules.md method row.
- **Per-enclosure I/O rate governance — Phase 3 DONE (2026-10-25,
  UNCOMMITTED, awaiting user review gate).** Enforcement wiring, inert
  until a cap is set. `lib/transfer-lib.sh`: `transfer_pace_args` is now
  endpoint-aware (`transfer_pace_args <send_target> <recv_target>` from
  `transfer_do`; pool = first path component, deduped; a token send's
  empty target contributes only the receive pool); new
  `transfer_resolver` (env `ZFSUTILITIES_ENCLOSURE_RATE` overrides the
  BASH_SOURCE location; re-checks per call so repointed/vanished overrides
  never serve a stale path) and `transfer_resolve_rate` (execs the resolver
  DIRECTLY, not via `python3`, so the in-shell python3 pacer mocks and the
  resolver seam stay independent; resolver stderr flows straight to the
  session log, only stdout is the rate; fail-open WARN prints the activity
  limit; `INFO: Enclosure rate cap applied: <rate>` when a cap changed the
  pace; no pools means the resolver is skipped). Every zfs-send-receive /
  zfs-migrate-send consumer inherits caps — including sever-vm-clone's
  engine copies (unlimited today) — with byte-identical pipelines when no
  cap is set. zfs-migrate-send's token-resume call now passes `$sourcefs`
  as the send target (argv unchanged; -t still omits it — the resolver
  gains the source pool). `lib/archive-engine.sh`: `archive_resolver` /
  `archive_resolve_rate`; `archive_one_zvol`/`unarchive_one_zvol` shadow
  `transfer_rate_limit` locally per zvol with the combined rate
  (`local _activity_rate` captured BEFORE the shadow — reading the shadow
  in its own assignment would always see empty), so device copy, hash
  verify, and raw send/receive all pace; the caller's prompted value is
  untouched. Stragglers: clone-vm routes both `zfs send | zfs receive`
  sites through `transfer_do` (main script + the SSHEOF storage heredoc
  source transfer-lib; transfer-lib's file-level bootstrap is now guarded
  on `type -t log_msg` like iscsi-lib's, because the storage heredoc has
  no ~/bashinit and a re-run would clobber the session log);
  zfsrestoresendstream resolves the dest pool once and inserts the pacer
  as a real pipeline stage (`pv | pacer | zfs receive` — an empty
  pace_argv segment is a bash no-op passthrough, verified);
  zfsreadthru paces both read passes; zfsresume is token-validation-only —
  documented note, no change. Scrubs stay monitored-only (Phase 5);
  zfsscruball ionice retained. Test plumbing: test-lib.sh now exports a
  hermetic default resolver stub at `ZFSUTILITIES_ENCLOSURE_RATE`
  (answers `--min-with` unchanged = empty enclosures config;
  `ZFSUTILITIES_TEST_ENCLOSURE_RATE` makes it answer with a cap; custom
  fakes override the env per test) — no suite ever spawns the real
  resolver's lsblk/udevadm/zpool scans. New/extended suites:
  test-transfer-lib (8 new tests: cap-without-rate, min-combination argv,
  same-pool dedupe, fail-open x2, missing resolver, empty endpoints,
  transfer_do at combined rate), test-zfs-migrate-send (cap paces engine
  with no activity rate; resolver told both endpoint pools),
  test-archive-vm x3 (cap paces archive; resolver consulted with source
  pool; fail-open keeps prompted rate), test-unarchive-vm x2 (cap paces
  restore; fail-open), test-clone-vm x2 (transfer-lib sourced main +
  heredoc; no bare send/receive pipelines remain),
  test-zfsrestoresendstream (pacer stage between pv and receive),
  NEW test-zfsreadthru (unpaced without cap; both parts paced + stage
  order; fail-open), test-sever-vm-clone (mock engine records
  `ENCLOSURE_RATE` env — the bash -c engine child inherits the resolver
  seam; sever's engine is mocked in that suite, the real engine's
  consultation is proven by test-transfer-lib/test-zfs-migrate-send).
  Docs: user-guide concepts "Transfer Rate Limits and Enclosure Caps"
  (lower wins; limitations: scrub monitoring-only, caps apply on the
  streaming node, fail-open, HBA-as-eSATA caveat; zfsresume note),
  messages-manual rows in seven sections, data-structures flip ("later
  phase" to consulted-by-every-pipeline), modules.md transfer-lib/
  archive-engine/pace_stream updates + new enclosure_rate.py section +
  TOC, commands.md zfsreadthru/zfsresume/zfsrestoresendstream,
  two-node.md clone-vm, global-variables transfer_rate_limit interplay.
  Next: Phase 4 (Disks-page enclosure UI) only on user go-ahead.

- **j12 interrupted-upgrade journey (2026-10-25, VERIFIED).** ITF
  failure injection #3: kill a real upgrade twice (SIGTERM early — EXIT
  trap must clean staging; SIGKILL of the process group mid-deploy —
  partial versions/<v> without MANIFEST, salvage kept, running system
  untouched), then verify the self-repair (re-run
  upgrade-zfsutilities: full re-scan, in-place repair, deploy without
  activating). j10's premise/baseline/serve staging was factored into
  `itf_journey_stage_upgrade_env` (journeys/common.sh); j10 refactored
  to call it and re-run green (no regression). j12 run green on the
  second attempt — first attempt tripped on the login-shell PATH
  gotcha in its own post-verify (`switch-version --list` needs
  `bash -lc`; non-login ssh never sees profile.d wiring). Docs updated
  (journeys README, integrated README roadmap 3.7, developer guide);
  test-itf-driver journey list gained j12 and the previously missing
  j11. Uncommitted; guests 8003 (j12, stopped), 8004 (j10), and 8006
  (j09 — first live run green 2026-10-25, held until pub2's ITF run
  finished; see PREEXISTING cross-lane entry) may be destroyed at
  wrap-up.

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



