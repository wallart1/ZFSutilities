# Changelog

## 0.134.0

*Released 2026-10-26*

### Added

- **Enclosure management on the Disks tab.** A new Enclosures section
  lists every discovered multi-bay USB/eSATA enclosure (name,
  kind/location, disk count, pools, max I/O rate), and the disk
  inventory gains an Enclosure column showing the configured name or a
  self-describing fallback — blank for internal disks, with partitions
  following their parent disk. **Set Max I/O Rate…** names an enclosure
  and sets its transfer-rate cap in the pacer grammar (blank =
  unlimited; invalid input re-prompts with the exact accepted grammar),
  storage host only on two-node systems, and stays available while a
  dataset action runs because it edits configuration only. The cap
  reaches every transfer the enforcement core (0.133.0) already paces;
  a change applies to transfers started after the save. Enclosure
  discovery failure fails open: the disk list is never blanked, tags
  and rows simply wait for the next refresh.
- **Live enclosure rates on the Performance tab.** The Live Charts view
  gains an "Enclosures — USB/eSATA Traffic" section: read/write rates
  summed over each enclosure's member disks over the iostat window,
  the configured cap, and % of cap computed on the busier direction (a
  paced transfer loads one direction at a time). Every leaf spelling
  `zpool iostat -v` prints — kernel and by-id names, whole disks and
  partitions — rolls up to its enclosure; an enclosure with no member
  in the report shows "—" rather than a possibly-wrong zero. One
  rolling chart tracks a read/write series pair per enclosure, rebuilt
  when the discovered set changes. This is also where I/O the caps
  cannot govern is visible: the rates are all enclosure traffic as ZFS
  reports it, including kernel-driven scrub, resilver, and destroy
  I/O. The section shares the Disks tab's inventory cache without
  blocking on it.

- **Rsync destination mount-chain fence.** Every local rsync
  destination — backup pull steps and the ZFS keys copy, in both the
  GUI Backup tab and the headless profile runner — is validated before
  the step runs: each filesystem dataset whose mountpoint prefixes the
  destination must be `mounted=yes` with a path that resolves to a
  real mountpoint, so an unmounted or shadowed destination (a later
  mount covering an ancestor — typically a pool root with
  `canmount=noauto` mounted after its children) refuses the step with
  a `WARN` naming the dataset instead of failing with a bare rsync
  mkdir error or, worse, writing into the covering filesystem. An
  unverifiable mount state refuses too — a destination that cannot be
  verified is never written to. A refused destination fails the run
  with `rc=11` even when every executed step succeeded, and `rc=11`
  with the mkdir-ENOENT signature is diagnosed as an
  unmounted/shadowed destination rather than a bare file-I/O error. On
  a clean chain, a missing destination directory below the deepest
  dataset mountpoint is created automatically (dry-runs log it
  instead), so a fresh destination needs no manual setup.
- **Graceful profile cancellation.** SIGTERM or SIGINT to the profile
  runner terminates the in-flight step's whole process group (steps
  now run in their own session, so the bash wrapper and its
  rsync/tee/zfs pipeline die together), starts no further steps, and
  aborts a profile-lock wait immediately. A cancelled run finishes
  with exit code 125 (`PROFILE_CANCELLED_RC`, outside rsync's 0–35
  and the tooling's other codes), a `cancelled` history entry shown
  with an amber marker on the Dashboard, and a `# END: cancelled`
  session trailer — distinct from a failure. The Dashboard's Cancel
  action now really cancels profiles: the profile branch sends
  SIGTERM to the runner's PID (it previously only logged advice
  pointing at other buttons), and a waiting profile cancels the same
  way.
- **Mount-order governance.** Unreachable mounts — datasets the kernel
  lists as mounted whose mountpoint path is missing or not a real
  mountpoint, whether shadowed by a covering ancestor or orphaned
  under an unmounted one — are detected and repaired as a maintained
  product invariant. The Dashboard lists every finding in **Warnings**
  and enables a contextual **Repair Mount Order** action for all of
  them; the Datasets tab offers the same repair scoped to a single
  selected filesystem or pool. The approval dialog renders the exact
  plan: which filesystems are unmounted (shadowed covers lifted as
  needed), the parents-first remount order, and the `canmount=on`
  corrections for erroneous `noauto` ancestors — applied first, so
  even an interrupted repair converges to the correct order at the
  next boot. A busy gate aborts before any unmount, every remount is
  verified to be a real mountpoint, and a mid-repair failure remounts
  everything parents-first with a message naming what to do next.
  **Unmount** also recovers unreachable mounts in place: orphaned
  mounts remount their unmounted parents (as before), and shadowed
  mounts lift the covering ancestor — busy-checked, shallowest first —
  then retry and remount what was lifted; the old "reboot required"
  advice is gone because no reboot is needed.

- **Datasets page: "Show Details in Log" button.** The context menu's
  *Send details to log* action — every ZFS property of the selected
  item streamed to the bottom log panel — is now also a toolbar button
  next to *Show Big Stuff*, for discoverability. It enables for exactly
  one selected pool, dataset, snapshot, or hold; volume partitions are
  not ZFS datasets and keep it disabled. Holds log their tag,
  snapshot, and dataset; everything else answers `zfs get all` on the
  full name.

### Fixed

- **`sever-vm-clone`: a failed phase-1 transfer now says so.** The
  transfer worker's exit was captured with a bare `rc=$?` while the
  script runs strict, so a failed worker killed the parent shell
  silently: the scripted recovery advice ("beyond the `@sever-*`
  snapshots no source data was touched — re-run sever-vm-clone to
  resume from the receive resume token") never printed, and the run's
  scratch results file leaked into `/tmp` (two files per failed run,
  growing without bound). The worker's rc now reaches the handler —
  the guidance prints, nothing destructive has run, and the scratch
  file is removed on every exit path (the `--continue` state file is
  deliberately kept).

### Changed

- `parse_zpool_iostat_v` now also returns the data section's leaf disk
  rows (group rows — `raidz*`, `mirror*`, `spare*`, `replacing*`,
  `draid*` — are excluded by name shape so leaf traffic is never
  double-counted); `logs`/`cache` rows are unchanged, and the L2ARC and
  SLOG tables filter by section as before. A new
  `parse_rate_limit` turns a cap string into bytes/second through the
  pacer's own parser, so the % of cap readout can never drift from what
  the pacer enforces.
- **`check-vm-disk-paths` runs strict** (`set -euo pipefail`), closing
  the last non-strict leaf in the bin/ family — the script was born in
  a parallel lane hours after the strict-mode campaign's tree was
  drawn and simply never saw it. Unexpected command failures now abort
  the fence run instead of continuing.

### Tests

- Suites for the cache attach (whole-disk and partition inheritance,
  fail-open discovery), the Enclosures section (config-name join,
  fallback display, selection preserved across refreshes), the rate
  dialog and save handler, button sensitivity including
  stays-enabled-while-a-dataset-action-runs, the parser's data-leaf
  semantics against a fixture covering every group shape, the
  enclosure rollup (absent vs idle-zero enclosures, unmapped and
  non-data rows), the Performance section and its chart rebuild, and
  the action-dispatch wiring for the new button and handler.

- New suites cover the mount-chain validator (clean, shadowed,
  unmounted, unverifiable, non-ZFS, and empty destinations), the
  shared destination fence (refusals, clean-chain directory creation,
  dry-run, remote passthrough), and both fenced-run shapes: pull steps
  and the ZFS keys copy each refuse and fail the run with `rc=11`
  while no rsync command is ever built.
- Cancellation is tested at three levels: flag semantics between
  steps and before the first step, cancelled-step output never
  diagnosed as an rsync failure, and real-subprocess SIGTERM journeys
  for both a running profile and one waiting on the profile lock —
  each asserting exit code 125, the `# END: cancelled` trailer, and
  lock release.
- Shadow-aware unmount and the repair engine are covered end to end:
  cover-lifting with restore, selection-scoped lifting, refusal when
  the cover is busy or unliftable, plan computation (orders, scope
  limiting, `canmount` fixes, clean-state triage), the approval gate,
  busy refusal running nothing, and failure-path parents-first
  remount. Dashboard coverage includes findings-driven button
  sensitivity, the full-scope handler, unreachable-mount warning rows,
  and the SIGTERM cancel branch for running profiles.
- Test files that had grown classes past their
  `if __name__ == "__main__"` guard were reordered so the guard sits
  at the end of the file; the sanctioned pytest runners are unchanged.

- New `test-sever-vm-clone` regression test for the transfer-failure
  path: the parent must reach its rc handler (resume guidance present,
  no silent death), no destructive operation may have run, and no
  scratch results file may leak. Red-proven against the reverted
  capture fix.
- `test-check-vm-disk-paths` restores the harness's own shell options
  after evaluating the (now strict) script text, and the script joined
  `test-strict-mode`'s strict family list.

### Documentation

- User guide: the Enclosures pane, the Set Max I/O Rate… button, the
  disk inventory's Enclosure column, and the Live enclosure rates
  section (with the monitored-not-capped story for kernel-driven I/O);
  the Python module reference documents the new functions and the
  shared-cache wiring; the data-structures guide covers the
  `VdevSample` section semantics, `EnclosureRates`, and the rollup;
  the messages manual gains the two new GUI message rows.

- The GUI guide documents both **Repair Mount Order** actions, the
  rewritten unreachable-mounts note (both shapes, lift-and-restore,
  the Dashboard flow, and the `canmount` rationale — no more "reboot
  required"), and the Profile cancel row's graceful path. The profiles
  guide explains the destination fence, the `rc=11` refusal, the
  auto-created destination directories, and the `rc=125` cancelled
  semantics. The messages manual carries the new fence, cancellation,
  and repair rows; the Python module reference documents the new
  public functions and the corrected import facts.

- gtk-gui.md: the new button's row in the Datasets actions table, and
  a note in the tree conventions that a top-level "pool" row on the
  Datasets page is the pool's **root filesystem dataset** — the pool
  object itself (live `zpool list` status, registry, scrub manager)
  lives on the Pools page.
- Developer testing guide: the real-pool integration table drops a
  scenario row that was never implemented (the suite has had seven
  scenarios since birth), and the `test-sever-vm-clone` catalog row
  records the new transfer-failure coverage.

## 0.133.0

*Released 2026-10-26*

### Added

- **Per-enclosure transfer-rate governance.** Enclosure discovery
  (`python/enclosure_inventory.py`) groups disks into multi-bay
  enclosures — USB disks by the hub directly under a root USB hub,
  SATA disks by PCI controller with the boot disk's controller
  excluded — with identity as a short hash of the sorted member WWNs,
  so it survives replug and port moves. The shared resolver
  (`lib/enclosure_rate.py`) computes the effective rate for a
  transfer: the minimum of the operation's own rate limit and every
  configured cap of every enclosure touched by the transfer's source
  and destination pools; one CLI serves the bash pipelines and one
  in-process seam (`ZfsRepository.effective_transfer_rate`) serves the
  GUI, so the two can never disagree. Caps live in the configuration's
  new `enclosures` section (`{id: {name, max_rate}}`; configuration
  version 30 migrates in place, an empty section changing nothing).
  Enforcement is wired through the shared engines: the transfer
  library resolves per send/receive endpoint pair, the archive engine
  resolves per archived/restored zvol, and clone-vm (both copy paths),
  `zfsrestoresendstream`, `zfsreadthru`, and the Migrate Pool resume
  path all pace through the same seam — operations that historically
  ran unlimited are capped too. Resolver failures fail open: a loud
  `WARN` and the operation's own rate as before caps existed, never a
  blocked transfer; with no cap configured every pipeline is
  byte-identical to its pre-cap form. Scrubs, resilvers, and destroys
  remain monitored only (kernel-driven I/O cannot be throttled from
  userland).
- **`j12-interrupted-upgrade` journey.** Kills a real
  `upgrade-zfsutilities` run twice — SIGTERM during the early phase
  (the EXIT trap must clean staging and nothing may be deployed,
  salvaged, or activated) and SIGKILL of the whole process group the
  moment the transcript shows the deploy marker (a partial
  `versions/<v>` dir without `MANIFEST.sha256` beside the killed run's
  salvage archive, current symlink untouched) — then proves the
  product's promise that re-running the same upgrade is the whole
  recovery. j10's upgrade staging is factored into the shared
  `itf_journey_stage_upgrade_env` (journeys/common.sh).

- **`repair-vm-disk-refs`** — the compute-host half of bare-metal-restore
  recovery (the mirror of `reconcile-iscsi-state`): re-points regressed
  VM-config disk references at the correct iSCSI LUNs by disk identity,
  never by LUN number. Each reference is resolved through the storage
  host's pool-resident state map to the backstore its (target, LUN) slot
  held at map time, then through the live topology to where that
  backstore sits now; only the by-path volume of the disk line is
  rewritten (`qm set`), with every option preserved byte-for-byte.
  Everything ambiguous is refused with evidence while the run continues
  with the rest: no map entry, a backstore that now belongs to another
  VM, not exported live (reconcile pointer), a running or unverifiable
  VM, two references resolving to one backstore. Map sanity gates refuse
  a map generated on another host or recording a different IQN
  prefix/storage IP; `--dry-run` reports without editing; every applied
  rewrite is verified against a live device, with an automatic iSCSI
  session rescan first.
- **`export-iscsi-state --print-map`** — read-only dump of the newest
  pool-resident state map as pure JSON on stdout: the compute host's
  recovery fetch path. Collects no live state, writes nothing, and
  needs no `targetcli`; mutually exclusive with `--check`.
- **Bare-Metal Restore Runbook (two-node)** in the docs: scenario A —
  storage host restored (fence/reconcile), scenario B — compute host
  restored (`repair-vm-disk-refs`), scenario C — both. Identity during
  recovery is the backstore name, never the LUN number.
- **Journeys `j13-iscsi-storage-restore` and `j14-iscsi-fence-recover`**
  — the iSCSI resilience campaign's end-to-end verification on the
  two-node lab: the 2026-10 incident shape staged honestly (LIO
  saveconfig and manifest regressed to a backup point with mtimes
  preserved, the post-backup LUN created through the product), the
  detector WARN, the map-driven reconcile rebuilding the backstore at
  the exact recorded LUN with LUN 0 untouched, the compute-host by-path
  link back, and the VM boot proof; then the compute half — fence units
  installed and enabled by activation, the manual detection tick with
  full identity, recovery through the installed systemd unit (real ssh
  reconcile), and the healthy tick after.
- **ITF run lock and acquire-time orphan fence** — `itf journey run` and
  `itf template build` serialize on a machine-global kernel lock
  (flock): a concurrent starter from any repo lane waits with
  heartbeats (or refuses instantly with `ITF_RUNLOCK_WAIT=0`), the
  holder is named across lanes to waiting starters and `itf status`,
  and the lock dies with its process (no stale-lock state, no cleanup
  verb). Because run guests outlive a dev-host restart, each start also
  refuses while guests recorded by an interrupted run still exist on
  their base — `--rerun` exempts exactly its takeover guests, and an
  unreachable base fails closed.

- **Unsaved-changes quit guard.** Closing the GUI while a tab with a
  **Save** button has unsaved edits now warns and lists the affected
  tabs (Backup, Offsite, Restore, Schedule, Pools, Checkagainst,
  Retention) in the same dialog as the existing running-tasks warning,
  so an unsaved deletion can no longer be silently discarded. Deleting
  rows without clicking **Save** counts as an unsaved change.
- **Cron log breadcrumbs.** Every cron firing appends two stamped
  lines directly to the cron log — `Scheduled run started (cron)` and
  `Scheduled run finished (cron) ... rc=N` — written past the fenced
  output streams. A schedule that stops firing now shows up as missing
  breadcrumb lines instead of an innocent-looking empty log.
- **Performance "Refreshing" indicator.** A small indicator next to
  the refresh-interval spinner is visible exactly while a refresh of
  the visible view is in flight — auto-refresh timer, toolbar Refresh
  button, and the Survey dialog's re-collect alike.
- **Changelog Archive.** Release history 0.46.1–0.129.0 moved
  verbatim to a dedicated archive page; the main changelog keeps the
  live series. A release series moves to the archive once a newer
  series begins.

### Fixed

- **Messages-manual enclosure rows.** The rate-governance message
  rows were pasted twice into the shared transfer section and
  archive-vm's own section kept its outdated row; the shared section
  now carries one current set and archive-vm its own.

- **Fresh two-node installs never got the iSCSI fence (F-026, found
  live by j14).** `install-two-node` activates the compute host before
  copying `node.conf` to it, and `switch-version`'s fence gate treated
  "no node config anywhere" as single-node and skipped silently. The
  gate now installs whenever `qm` is present and no config explicitly
  says single-node — a genuine single-node host always has `node.conf`
  at activation.

- **Silently dead scheduler — unescaped `%` in generated cron lines.**
  cron terminates a job's command at the first unescaped `%`
  (crontab(5)), so the timestamp stamper's `strftime` format and user
  conditions such as `date +%d` killed every scheduled run with an
  unterminated-quote shell error that `MAILTO=""` discarded — zero
  output, zero session logs. The generated command field now
  backslash-escapes every bare `%` (an already-escaped `\%` is left
  untouched); the Schedule tab's crontab preview shows the escaped
  literal file form, and the live drop-in converges to the fixed
  content at the next GUI start or scheduled run.
- **Checkagainst "User entries" resurrection.** Automatic UI-state
  saves (window geometry, column widths, view choices) rewrote the
  entire configuration file from the session's in-memory snapshot, so
  a session still holding deleted rows wrote them back to disk. UI
  state is now saved by re-reading the file under the config write
  lock and merging only the `ui_state` section — UI trivia can never
  clobber data sections again on any page (a whole-file write happens
  only when no readable file exists, e.g. the first launch write).
- **Performance page long-note layout.** Availability note labels did
  not wrap, and an unwrapped label's minimum width is its full text
  width, so a long degraded-host note pinned the page's minimum at
  that width and gave the page itself a horizontal scrollbar that
  shadowed every table's own. Note labels now wrap; each section keeps
  its own scrollbar and the ladder keeps its content-minimum floor.

### Tests

- Suites for the resolver (pure + CLI + fail-open), the inventory
  (grouping, identity, injectable collectors), the migration
  (29→30 seeding/preservation/idempotence), the config helpers, the
  repository seam, and per-script pacing for every newly wired
  consumer, including the restoresendstream fail-open path.
- Test-suite /tmp litter eliminated: rootcheck stub dirs
  (zfsshowbigstuff, zfswipe, list-vm-disks) are exit-trap cleaned, and
  the check-vm-disk-paths rescan-mock leak (a command-substitution
  array append that never reached the cleanup loop) is fixed.

- New `test-repair-vm-disk-refs` suite: the identity chain, options
  preserved byte-for-byte, every refusal class, the map sanity gates
  (host, IQN prefix, storage IP), dry-run, the two-round-trip fetch,
  and post-apply verification with rescan recovery.
- `test-export-iscsi-state` covers `--print-map` (newest-wins,
  read-only proof, the no-targetcli path, `--check` exclusion); the
  `test-switch-version` fence expectation flipped to require
  install+enable on a no-config compute host; `test-itf-driver` covers
  the run lock (holder record, wait/refuse, status section) and the
  orphan fence (refusals naming both recoveries, rerun exemptions,
  fail-closed bases, driver-level refusals).

- Cron `%` escaping fenced at the generator, the written drop-in, and
  the Schedule preview; breadcrumbs exercised through the real runner
  in a subprocess (from-cron pair with exit code, manual run silent,
  unusable cron log never fails the run); `save_ui_state` covered for
  external disk changes, disk `ui_state` merge, corrupt-file fallback,
  and first-write fallback; quit-guard dialog wording for tasks-only,
  changes-only, both, and clean close, plus the page predicates
  themselves; note-label wrapping and a long-note geometry scenario in
  the alignment realized check; the Refreshing indicator on both
  refresh paths and under the pending guard.

### Documentation

- two-node.md: the `repair-vm-disk-refs` section, `--print-map`
  synopsis/flow/return codes, the Bare-Metal Restore Runbook, and the
  switch-version fence row's new semantics; messages-manual rows for
  the new tool and flag; the integrated-testing guide documents the run
  lock and orphan fence; the developer testing catalog now lists every
  suite, the itf cluster and the iSCSI trio among them.

- User guide (closing the GUI, schedule condition field, cron log,
  Performance refresh control), developer guide (scheduler `%` law and
  breadcrumb audit trail), the messages manual (breadcrumb rows), and
  the Python module reference (`_write_cron_breadcrumb`) updated for
  the above; mkdocs nav gains the Changelog Archive page.

### Changed

- **README refreshed.** The current GUI screenshots are wired in
  (both previous image links had been broken since 0.128.0), the
  Highlights list names the twelve tabs in sidebar order, the MkDocs
  install line pins `mkdocs<2` (the project's prerequisite check
  rejects MkDocs 2.x), and the launcher sentence now says links in the
  installing user's home folder.

## 0.132.0

*Released 2026-10-25*

### Added

- **GUI payload e2e matrix.** One scenario matrix
  (`tests/python/e2e_support.py`) exercising the real payload builders
  and the real `BackupRunner` against the zfstest pools, driven from
  three contexts: the unprivileged dev container
  (`share/dev/run-e2e-container`, read-only `/dev/zfs` pass-through —
  every dataset-mutating scenario self-skips with a stated reason and
  the runner verifies the host pool set is unchanged), the dev host
  under sudo (`test_offsite_e2e.py` / `test_backup_payload_e2e.py` —
  headless runs through a GLib main loop with pty stdin and the
  input-hold REQ/ACK protocol), and the ITF guest (journey
  `j11-payload-e2e`, full mutating matrix). Scenarios carry a level
  (`none`/`read`/`mutation`) and an engine (`gui` protocol-on /
  `cli` protocol-off, as cron/terminal would run them); the matrix
  covers the offsite chain steps with holds, incremental and
  same-nextsnap reruns, dry-run, rollback, includes/excludes, live
  scrub pause/resume, resume-token recovery, backup
  full/incremental/destructive with hold preservation, prune, the
  rsync wrapper, the strict-mode leaf orchestrators, and a zfshold
  round trip.
- **`j10-release-upgrade` journey.** Exercises the release-upgrade
  path from a deliberately stale storage template (the old-version
  carrier), failing fast if the premise breaks; validated the
  pre-0.125.0 upgrader shape (no `upgrade-zfsutilities` on PATH — the
  upgrader runs from the downloaded tree) end to end.
- **`itf_guest_get`** (itf ssh helper): guest→dev file pull,
  mirroring `guest_put`.

### Changed

- **Strict-mode campaign — 33 orchestrators now run under `set -euo
  pipefail`**: the 29-script iSCSI/two-node family plus
  `zfssend`/`zfssendoffsite`/`zfsfullcopy`/`zfsrestore` (they source
  `zfs-send-receive`, whose strict line reaches them at the source
  point). Shared helper libraries deliberately carry no `set` line —
  strictness belongs to the orchestrator — and were made
  strict-caller-tolerant instead; the rules are codified in the
  developer guide's coding policies, including the `declare -gA
  name=()` initializer requirement for library global arrays.
- **`zfshold` holds each matching snapshot individually.** A tag
  already present on a snapshot is logged at INFO and treated as
  success (nested datasets are matched by both their own call and
  their parent subtree call, so duplicates are a designed outcome);
  any other hold failure is logged at WARN and fails the call — real
  failures are now loud instead of silently discarded. An empty match
  still returns 0.
- **`upgrade-zfsutilities` captures a trust-on-first-upgrade
  baseline.** When a host's active version has no deployment
  manifest and no release tarball is obtainable (pre-manifest
  versions, untagged releases), the change scan captures a manifest
  of the current tree on that host — local and remote — instead of
  leaving the host unverifiable; every future upgrade scans against
  the captured baseline.

### Fixed

- **GUI offsite runs aborted after verified transfers (strict-mode
  hotfixes, found live 2026-10-24).** Two latent defects surfaced by
  the strict flip: a bare `declare -gA` executed in
  `source_helper`'s function frame left library arrays that `set -u`
  shells cannot length-check — `iscsi_teardown` died mid-rebuild
  (`iscsi-lib.sh`, plus the same landmine fenced in
  `installer-lib.sh`); and the old `zfshold` pipeline aborted the
  payload shell on the first duplicate hold (`xargs` rc 123 under
  `set -e`) after both transfers had already succeeded.
- **Standalone `zfsdelfs` died under strict mode (`mydir: unbound
  variable`).** `zfsdelfs` defers its `bashinit` call for library
  use but resolved sibling helpers at file scope;
  `find_zfsutility_script` now tolerates an unset `mydir` (falling
  through to the deployed directories — the historical working
  behavior) and `zfsdelfs` seeds `mydir` from its own location when
  unset. Found live by the j07 archive run.
- **`new-vm-disk` single-node success runs exited 1** — the final
  summary statement was an unfenced `&&` chain whose false left side
  became the exit code under `set -e`.
- **The `zfs-send-receive` rollback holds-remaining guard never
  fired** — it read the upper-case variable name while
  `zfsdelallholds` sets the lower-case one; the guard is now live
  and pinned by a contract test.

### Tests

- New `test-zfshold` suite pins the hold contract: duplicate tag →
  INFO + rc 0 (including the exact parent-subtree + nested call
  shape from the live failure), real failure → WARN + rc 1, empty
  match → rc 0, missing pattern → rc 1.
- `test-strict-mode` guards the strict family (46 scripts), the
  library-array `declare -gA` law (static + live under `set -u`),
  the unset-`mydir` lookup, and a new exit-safety fence: a strict
  script's final statement may not be an unfenced `&&` chain (the
  `new-vm-disk` bug class; red-proven against the bug shape).
- Ten suites that source or eval now-strict scripts restore the
  harness's own shell options after the source point; the upgrade
  suite pins local and remote baseline capture; the payload e2e
  suites are registered in the requirements manifest.

### Documentation

- zfshold's messages-manual rows (duplicate-hold INFO, failure WARN)
  and its module section's behavior line and return-code table now
  match the per-snapshot implementation; the upgrade messages
  section documents the baseline-capture notice; coding policies
  codify the strict-mode laws and the shellcheck command now covers
  `share/dev/*`; the testing and integrated-testing guides document
  the payload e2e matrix and its three contexts.

## 0.131.0

*Released 2026-10-24*

### Added

- **Restore-time iSCSI detection (iSCSI resilience M3).** Three
  read-only detectors in `lib/iscsi-lib.sh` recognize the
  bare-metal-restore signature from live state: (a)
  `saveconfig.json`/expected-backstores manifest older than the newest
  VM zvol, (b) compute-host VM disk references (including efidisk)
  whose target/LUN is absent from the live LIO tree, and (c) manifest
  entries with no zvol. `check-prerequisites --two-node` reports
  findings as informational warnings — the gate stays read-only and
  findings never fail it — and `setup-iscsi-targets` prints the
  evidence after target setup and offers `reconcile-iscsi-state` with
  the same verified-evidence + `y/N` pattern as orphan-target
  deletion: declining leaves the system untouched, an accepted
  reconcile runs interactively under its own plan+confirm gate, and a
  failed one exits 1. Every detector skips quietly when its inputs are
  absent, so a pre-install or fresh-install host reports nothing.
- **Compute-host iSCSI fence — `check-vm-disk-paths` (iSCSI resilience
  M4).** Verifies that every VM-config disk reference (including
  efidisk) has its `/dev/disk/by-path/ip-…-iscsi-…-lun-N` link on the
  compute host; with `--recover`, a local `rescan-storage` first, then
  exactly one ssh running `reconcile-iscsi-state --yes` on the storage
  host, re-checking after each stage. A refused reconcile stays
  report-only — the fence never retries, guesses, or remaps. Runs from
  the new `zfsutilities-iscsi-fence.timer` (every 5 minutes, boot
  settle of 2 minutes; ticks stay journal-only via
  `ZFSUTILITIES_LOG_INHERIT=Y` so no per-tick session logs are
  created), installed and enabled by `switch-version` activation on
  two-node compute hosts (gated on `qm` presence and the node config)
  from the activated version's `share/two-node/` tree — idempotent,
  refreshed on every activation, self-healing re-enable. A healthy
  tick is entirely local: no ssh, one summary line. `install-two-node`
  names the fence in its completion summary, and
  `uninstall-zfsutilities` stops, disables, and removes both units
  symmetrically.
- **Merged Dashboard Tasks list.** The Dashboard's Recent Operations
  and Running Tasks sections are replaced by one **Tasks** list — tasks
  waiting for a lock, tasks running right now, and the ten most recent
  completed operations, in reverse chronological order (rows whose
  start time cannot be determined sort to the top). Each row shows the
  task's start time and state: `Waiting since <time>`, `Running since
  <start>` with progress where one exists (`Step N/M`, scrub
  `% complete (ETA …)`, ZFS-native `% done`, surface-test `%`), or the
  completed operation's highest message level. Start times come from
  the runner sessions, `zpool status` scan lines, and `ps lstart=`;
  the table keeps a constant ten-row window with its own scrollbar
  when the list is longer.
- **Remove Selected action (Dashboard).** Completed rows can be
  removed from the Tasks list; removed rows stay hidden across
  refreshes, and dismissal keys prune themselves once their entries
  fall out of the ten-entry window. Removal only dismisses the row —
  the history entry and its session log are kept, so the Logs tab's
  success-rate metrics are unaffected.
- **Waiting tasks are cancellable.** Cancel Selected Tasks now works
  on waiting rows: a GUI runner's lock wait is interrupted (SIGINT),
  and a waiting scheduled profile is stopped with SIGTERM after a
  click-time re-check of the live PID (an entry that vanished since
  the click warns instead of signalling).

### Changed

- **Performance tab last in the sidebar.** The Performance page moves
  to the bottom of the navigation column, below Disks, Pools, and
  Datasets; its persisted settings are unchanged.
- **Next Run column drops the retention-bucket word.** The
  parenthesized bucket suffix (`(weekly)` and friends) read as a run
  frequency and is removed; the conditional UTC-edge translation hint
  (`23:30 Sat = 03:30 Sun UTC — names dated Sun`) remains for
  snapshot-creating profiles.

### Tests

- `check-vm-disk-paths` covered end to end (healthy local-only tick,
  report-only missing, rescan-suffices, single reconcile ssh with the
  exact remote command, refused-reconcile report-only) and
  `setup-iscsi-targets` detection covered across all three signatures,
  the decline/accept/failure offer paths, and the fresh-install
  no-false-positive proof. Uninstall now asserts the fence units are
  removed with the timer stopped and disabled first, and a lone fence
  timer alone marks systemd integration for removal; the shipped fence
  units carry a structural guard (stable-path `ExecStart` with
  `--recover`, journal-only environment, 5-minute cadence).

### Documentation

- New `check-vm-disk-paths` section in the two-node command reference
  (arguments, called modules, flow, return codes) plus TOC entry;
  `setup-iscsi-targets` documents the detection step and the reconcile
  offer; `switch-version` documents the fence activation wiring;
  `check-prerequisites` documents the two-node detection; the message
  reference gained the fence and detection message rows.

## 0.130.0

*Released 2026-10-24*

### Added

- **Pool-resident iSCSI state map — `export-iscsi-state` (iSCSI
  resilience M1).** A storage-host bare-metal restore regresses
  `saveconfig.json` and the expected-backstores manifest together
  (both live on the OS disk) while the pools re-import current, so
  LUNs created after the backup point were unrecoverable. The new
  storage-host command records the live LUN topology — per-target
  LUN → backstore, per-backstore zvol device, ACL initiators, plus a
  copy of `node.conf` — as deterministic JSON
  (`<pool>/zfsutilities/iscsi-state.json`) on every online pool, so
  any surviving pool can serve recovery. The dataset is created on
  first use, writes are atomic, offline pools are skipped with a
  warning, and a degraded-state fence refuses to shrink the map
  (expected count from the manifest, or the newest map when the
  manifest regressed with the OS disk) unless `--force` is given.
  `--check` reports drift (manual `targetcli` edits) against the
  newest map and never writes.
- **Map-driven post-restore recovery — `reconcile-iscsi-state`
  (iSCSI resilience M2).** Companion storage-host command that
  rebuilds the LUN topology from the pool map after a restore:
  create-only — every map backstore whose zvol still exists gets its
  backstore (`emulate_tpu=1`), its LUN at the recorded number, and
  its explicit-mode ACL bindings; identity is the backstore/zvol name
  at the recorded LUN, so conflicts (different device, different
  target/LUN, slot held by another backstore, missing target) are
  refused per item with evidence and never auto-remapped; zvol-gone
  entries are skipped with the pool map left unchanged so they
  survive for when the zvol returns. Finishers re-flag encrypted
  backstores into `iscsi-encrypted-luns.conf`, regenerate the
  manifest from the ensured set, run `safe-iscsi-save` (map hook
  suppressed), refresh the pool map only after a complete reconcile,
  and rescan the compute host. A VM-config cross-check over ssh
  reports still-missing disk references with their map identity and
  lists candidate unexported zvols (never guessed). Supports
  `--dry-run`, `--yes`, and `--from <map snapshot>`.
- **Fast re-verification for install-start journeys.** `itf journey
  run NAME --rerun` now replays on the previous run's guests for
  install-start journeys too: each recorded guest is rolled back to
  its `os-installed` checkpoint (via `qm rollback`, a guarded verb),
  restarted, and re-discovered instead of a full Debian preseed
  reinstall — the fix-verify loop for j01/j08/j09 staging drops from
  minutes to seconds. A rolled-back guest is a clean Debian with the
  prerequisites genuinely missing, so failure-path coverage is
  unchanged; deeper checkpoints (`pools-created`) are deliberately
  never rerun sources (a pre-installed lab would route the installer
  into its upgrade branch). The rollback restores the checkpoint's
  VM config, so the installer-time CPU freeze is cleared between the
  rollback and the start.
- **Installer failure-path journeys.** `j08-prereq-decline`: a
  first-time user declines prerequisite remediation — the installer
  aborts gracefully with re-run instructions and the guest stays a
  clean Debian (no deployment, no node.conf, no PATH wiring).
  `j09-prereq-apt-failure`: apt breaks behind the user (a dead
  HTTP-proxy drop-in, the misconfigured-site shape) before both
  remediation prompts are accepted — the installer surfaces the apt
  failure cleanly, nothing half-deploys, and removing the drop-in
  surgically restores apt. Both assert the installer's exit code and
  its user-facing message separately.
- **Journey staging helpers.** `itf_journey_stage_prepare_install` is
  the shared prefix of every installer journey (download tooling, the
  user's download, the expected-to-fail prerequisite check) for
  failure-path journeys that drive the installer with their own
  feeds; `itf_journey_run_installer` takes an optional expected exit
  code so a graceful installer abort can be asserted as a pass.

### Changed

- **`safe-iscsi-save` refreshes the pool LUN map.** After every
  successful save it invokes `export-iscsi-state` (best-effort — a
  failure warns and never fails the save), keeping the map as fresh
  as the last LUN change. Callers that own the refresh decision
  (`reconcile-iscsi-state`) suppress the hook with
  `SAFE_ISCSI_SAVE_SKIP_EXPORT_ISCSI_STATE=1` so a partial reconcile
  cannot overwrite the recovery authority.
- **Shared iSCSI discovery in `lib/iscsi-lib.sh`.** The targetcli/zvol
  parsers (`parse_backstores`, `parse_target_luns`, `discover_zvols`)
  moved out of `repair-iscsi-luns` into the shared library (behavior
  unchanged), joined by a new `parse_target_acls` and the pool-map
  locator (`newest_iscsi_state_map`), so repair, export, and
  reconcile read live LIO state identically. Dependency loading is
  now guarded on node-lib's `pool_to_target`, so contexts that have
  already loaded bashinit/node-lib no longer re-run the session-log
  setup (which also clobbered unit-test mocks).

### Fixed

- **`--rerun` source resolution never saw a usable prior run.** The
  just-created run directory matched the source glob and read as
  still active (its own pid alive, no `finished:` yet), so every
  rerun could refuse on its own run; the driver now excludes the new
  run from candidates.
- **Rerun checkpoint detection missed real `qm listsnapshot`
  output.** The `as-cloned` presence check parsed the snapshot name
  from the first field, but real output puts the tree arrow there;
  both checkpoint checks now pin the real shape.
- **Stale snapshots collided with the replay.** Snapshots newer than
  the staging checkpoint survive a rollback on this stack but go
  stale, and the replay re-snapshots the same names; both rerun
  branches now remove them first (recorded as explicit steps).
- **`reconcile-iscsi-state` fails when the config save fails.** A
  `safe-iscsi-save` failure logged FATAL but still exited 0; the run
  now exits 1 so scripted callers cannot mistake an unpersisted
  rebuild for a completed recovery.

### Tests

- itf driver suites pin the rerun contracts end to end: dispatch and
  every refusal shape against planted run directories, the
  rollback-instead-of-clone and rollback-instead-of-install branches
  in-process with stubbed transports, the rollback → freeze-clear →
  start ordering law, and the fresh-run paths still cloning and
  installing. The installer-runner's expected-exit-code contract and
  the shared staging prefix's tolerance of the expected prerequisite
  failure are pinned in-process; the journey list can no longer
  silently drift as journeys are added.

### Documentation

- New "Fast re-verification" section in the developer guide's
  integrated-testing page; the itf usage blocks, journey tables, and
  roadmap phases refreshed (two-node complete, fast re-verification +
  failure paths complete); the testing overview's orchestrator
  paragraph now describes the real coverage; `tests/AGENTS.md` gained
  the integrated-validation guidance section.

