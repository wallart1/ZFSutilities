# Integrated Testing

The mock-based suites verify individual scripts and modules against
simulated ZFS/SSH/GTK surfaces. The **integrated testing framework**
(`tests/integrated/`, driver command `itf`) complements them by verifying
the *product experience* on real systems: an orchestrator on the
development machine plays a **first-time end user** — it creates
disposable nested guests on the base Proxmox test VMs, installs a target
OS from an ISO, downloads ZFSutilities the way a real user would (GitHub
release tarball, or a dev tarball when verifying a repair), runs the
interactive installer, drives day-to-day workflows, and asserts on
outcomes in the guest.

Unit-style test suites are deliberately **not** run in the guests; the
exception is diagnosing a failure the end user would not normally
encounter.

```
dev (itf orchestrator)
  └── base PVE hosts (PROTECTED)
        │   guarded guest-lifecycle commands only, via ssh + sudo -n
        └── nested guest (DISPOSABLE — anything goes)
              └── ZFSutilities under test (release or dev tarball)
```

Cycle 2 adds a second base host in the **compute role** (see
[Two-node topology](#two-node-topology)): the storage-role base hosts
Debian-based guests as before, the compute-role base hosts guests
installed from the Proxmox VE ISO, and two-node journeys drive one guest
on each, linked by a point-to-point subnet.

## Safety model

The base Proxmox hosts are protected by construction, not by convention:

- All base-host access flows through `tests/integrated/lib/base-lib.sh`:
  - only allow-listed `qm` lifecycle verbs may run;
  - VMIDs must be inside the reserved range from the site config
    (production-style VMIDs can never be touched);
  - disk/ISO references must use the dedicated `itf` storages — the
    base system's own storages (`local`, `local-lvm`, …) cannot be
    written through this path;
  - absolute paths are only permitted inside the configured ISO
    directory;
  - every mutating call is appended to an audit log on the base host
    *before* it executes;
  - `pvesm` is read-only (`status`, plus `path` lookups that accept
    only itf-storage volumes — used by the VM-OS image dump on its own
    build guest's disk); general reads go through a small allow-list
    (`itf_read`).
- `ITF_DRY_RUN=1` prints guarded commands instead of executing them.
- Base-PVE configuration beyond guest lifecycle (storages, bridges, the
  audit log) is prepared by a human from orchestrator-emitted
  instructions (`itf manual-steps`, `itf preflight` verifies).
- Guests are disposable: any guest state may be destroyed or rolled back
  at any time.

## Site configuration

Everything environment-specific lives in `tests/integrated/site/config`
(gitignored), created from the committed `site/config.example`. Loading
is fail-closed: a missing or invalid file aborts with a pointer at the
example. Validated keys cover the base hosts, SSH user, reserved VMID
range, itf storages, ISO sources, guest sizing, and the software source
(`release` or `dev-tarball`). Two-node keys (role bases, P2P addresses,
compute template name, PVE ISO source) are optional and activate the
compute-role machinery only when present; the role bases must be members
of `ITF_BASE_HOSTS`. The optional Ubuntu pair
(`ITF_UBUNTU_ISO_URL` + `ITF_UBUNTU_ISO_NAME`, both-or-neither, plus
the `ITF_UBUNTU_TEMPLATE_NAME` override) activates the ubuntu probe
template; it lives on the storage base like the Debian one. The
optional keystore pair
(`ITF_KEYSTORE_PASSPHRASE` + `ITF_KEYFILE_NAME`, both-or-neither) feeds
the LUKS key-device lab below — the passphrase is a secret and lives
only in the gitignored site config.

## Running

```bash
tests/integrated/itf manual-steps     # outstanding human setup, if any
tests/integrated/itf preflight        # dev + base-host readiness report
tests/integrated/itf iso fetch        # download the Debian installer ISO
tests/integrated/itf iso upload       # push it to the base ISO storage
tests/integrated/itf template build   # rebuild the post-install baseline
tests/integrated/itf vmimage build    # one-time VM-OS disk image (below)
tests/integrated/itf vmimage status   # cache state of that image
tests/integrated/itf journey list
tests/integrated/itf journey run j01-fresh-install
tests/integrated/itf journey run <name> --rerun
                                    # replay on the previous run's guests
                                    # (rollback to as-cloned — no clone)
tests/integrated/itf journey run j21-zfs-probes --template ubuntu
                                    # start from a chosen baseline profile
                                    # (storage|compute|ubuntu; default
                                    # storage — supported by j21)
tests/integrated/itf watch            # tail the active run — NOT a console
tests/integrated/itf status           # guests + template + runs overview
```

`iso fetch`/`iso upload` take an optional selector (`debian`, the
default, `pve`, or `ubuntu`), and `template build` takes `--base`
(target base host) and `--profile storage|compute|ubuntu` (storage =
Debian + product, the default; compute = Proxmox VE from the ISO,
see below; ubuntu = Ubuntu Server LTS via autoinstall, a plain
OpenZFS-version leg for the j21 probe matrix — no product install).

Every run produces a progressive report under
`tests/integrated/results/run-<timestamp>-<tag>/` (gitignored):
`steps.tsv` for tooling, `report.md` for humans, plus artifacts (logs,
`zfs list -t snapshot` listings, GUI screenshots). Every `report.md`
line carries a UTC timestamp, and long activities (a guest install, a
serial watch, a poll loop) open with a `**START**` line when they begin,
so a run watched mid-flight shows what is running right now. `itf
journey run` exits non-zero when any step failed.

The driver itself runs under `set -euo pipefail`: its own plumbing —
dispatch, preflight, status, watch — fails fast on any unhandled error.
The journey and template-build entry points are deliberately looser:
the driver invokes both through an `|| rc=$?` wrapper, which suppresses
errexit for their whole extent so they keep the failure-accumulation
and always-finish-the-report contract documented in
`tests/integrated/journeys/README.md` (a failing step records its fail
and the run continues to cleanup and final report; the driver exits
non-zero from the captured rc). Journey stage code therefore gates on
explicit `|| return 1` rather than `set -e`, while anything the driver
runs directly gets no such tolerance.

### Console discipline while a run is active

The install phase of every journey is driven over the guest's **serial
console** (`qm terminal`, `lib/serial_console.py`). The Proxmox web UI's
xterm.js console on an itf guest attaches to the *same* serial socket:
a second session interleaves keystrokes and splits output, wait-patterns
miss, wrong bytes reach the installer — and even briefly attaching can
blind the driver for the rest of the run. While a run is active
(`itf status` shows an active run with its pid):

- Never open an itf guest's xterm.js/serial console.
- Guest noVNC (VGA) is look-don't-touch: no typing, no power buttons —
  the journey owns the guest's power state.
- Leave the base-VM consoles alone entirely: the confinement guard
  constrains the orchestrator, not a human at a base console, who is
  root with no guardrails.

To follow a run, use `itf watch [TAG]` — it tails the live report and
serial transcript of the active run (or a named one) from the first
byte, reading transcripts only and touching no console. With no active
run it parks on the newest run's final screen (post-mortem mode). The
output is a plain `tail -F` stream, not a full-screen viewer: resizing
the terminal garbles the wrap — Ctrl-C and rerun `itf watch` to redraw.

## Journeys

A journey (`tests/integrated/journeys/<name>.journey`) drives one
end-user scenario — fresh install and daily workflows, uninstall and
reinstall, install over leftovers — using the itf helpers (`itf_step`,
`itf_guest_*`, guarded `itf_qm`/`itf_read`) and asserting on real
outcomes. The contract is documented in
`tests/integrated/journeys/README.md`.

OS installation inside the guest is automated with a Debian preseed
(or, for the ubuntu profile, an autoinstall seed — the same HTTP-serve
and serial-console machinery) served over HTTP from the development
machine and driven over the serial console (`qm terminal`,
`lib/serial_console.py`) — the substrate under test is ZFSutilities'
installer experience, not the OS installer's.

Guests are disposable and their addresses are DHCP-recycled, so all
guest ssh/scp traffic uses `StrictHostKeyChecking=no` with a throwaway
known-hosts file: a fresh guest at a previously used address presents a
*different* host key, which `accept-new` rejects as a mismatch.

## GUI payload e2e matrix

The GUI does its work by building bash payloads (python/offsite_runner.py,
python/command_builders.py, python/restore_runner.py) and running them
through BackupRunner. The
payload e2e matrix exercises exactly that code — the real builders, the
real runner, real ZFS pools — instead of hand smoke tests. The scenarios
live once in `tests/python/e2e_support.py` and run in three contexts:

- **Dev container** (unprivileged, `--device /dev/zfs`): the pools are
  visible read-only (every dataset-mutating ioctl needs `CAP_SYS_ADMIN`),
  so the mechanics layer (real BackupRunner headless through a GLib main
  loop — pty stdin, the input-hold REQ/ACK protocol, rc propagation) and
  the dry-run payload scenarios run for real; mutating scenarios skip
  with a stated reason. Entry point: `share/dev/run-e2e-container`.
- **Dev host under sudo** (`tests/python/test_offsite_e2e.py`,
  `tests/python/test_backup_payload_e2e.py`): the full matrix against the
  host's zfstest1/2/3 pools. Scenarios create and destroy only
  `test-e2e-*` datasets inside those pools and verify they leave nothing
  behind.
- **ITF guest** (journey `j11-payload-e2e`): a template clone with the
  j04 pool recipe and today's tree, running
  `tests/integrated/e2e/payload-e2e-driver.py` — the same matrix, executed
  as real root in a disposable guest. This is the full-matrix context the
  journey gates on.

Scenario levels are declared per scenario (`none` / `read` / `mutation`)
together with an engine mode: GUI payloads run under the input-hold
protocol exactly as the GUI runner launches them — offsite, backup,
prune, and restore payloads alike, including the Restore tab's property
replay and receive-as-encrypted scenarios; the CLI orchestrator
scenarios (zfssend, zfsfullcopy, zfsrestore, the zfshold round trip) run
protocol-off as cron/terminal would, with known raw prompts pre-fed on
the pty and any unexpected prompt caught by the watchdog.

## Backup property fidelity (j20)

The **j20-property-manifest** journey walks the property-manifest
sidecar end to end against real ZFS in one guest (clone start, j04 pool
recipe, today's tree — the deployed template version is irrelevant
because the feature lives in the tree under test): an engine backup
captures per-dataset manifests with distinctive settings (local props,
a user prop, an encrypted child's `keylocation`, a zvol whose
`volblocksize` must stay excluded); a rename-and-restore round trip
replays every setting and loads the key; a capture-disabled generation
exercises the exact-miss → newest-available fallback WARN; a
never-captured backup the pre-feature WARN with inherited defaults; the
`zfssendoffsite` step-4 shape hops the backup pool onward with
`property_manifest='N'` carrying the store as an ordinary dataset, and
a restore from the offsite copy replays through the traveled store (the
deeper store-candidate lookup) — including the hidden-key WARN that
leaves the dataset locked — before `zfsoffsiteretain` prunes the
store's offsite snapshots in lockstep with the data copies'. The
consumption surfaces follow: a hand-made export (`zfs send` to a file
plus the store's manifest as its `.props` sibling) replays through
`zfsrestoresendstream` while a sibling-less file restores silently, and
a restore made with `replay_properties=N` gets every setting back
through standalone `zfsreplayprops`. The receive-as-encrypted restore
(campaign P6) then initial-receives every plain dataset as encrypted
wearing the restore key — exactly one `-o encryption` receive, the
step-2 catch-up stays plain, the raw-stream child keeps its own
encryption and stays locked under the skip-`keylocation` WARN — with
the non-`file://` keylocation refused FATAL (rc 8) before any transfer.
The journey closes by running the payload-e2e driver's offsite-onward
and restore pairs, the mutation scenarios the unprivileged container
tier cannot run.

## Function survey (j22)

The **j22-function-survey** journey is a sampling harness rather than a
fixed scenario: at the start of every run it draws a seeded random
sample of **at least half** of the end-user-visible function universe,
shuffles the order, archives the list, and then executes the items in
that order with full logging. The archive makes a run exactly
repeatable — `ITF_SURVEY_ARCHIVE=<file>` replays the same list, order,
and prompt-response profiles, and `--rerun` reuses the previous run's
guests and (absent an env pin) its archived list.

The universe has two halves:

- **CLI** — every command documented on the commands pages, minus two
  recorded exclusion tables (the misc commands declared not worth
  testing on 2026-10-26, and the lifecycle/dev commands owned by the
  dedicated install/upgrade journeys, 2026-11-04). The tables are
  parsed rows in `tests/integrated/survey/universe.tsv`; the sampler
  test fails on drift in either direction, so a newly documented
  command must be consciously added or excluded.
- **GUI** — enumerated at run time from the tree under test: the
  action buttons (`ACTION_HANDLERS`), the central-content widget
  interactions (row selection, per-row toggles, cell edits, entries,
  comboboxes, spinbuttons, the Dry Run toggle, page navigation —
  `survey/gui_catalog.py`), and curated composites that assert the
  linkage between central-area state and the action buttons
  (selection-scoped actions, dirty-state flow through Save/Revert,
  sensitivity wiring).

Every item carries a **response profile** — accept, decline, cancel, or
invalid — applied to CLI answer feeds, modal dialogs, and the numbered
input-hold prompts, so a run exercises different scenarios instead of a
constant safe default. The wrap-up reports the profile distribution as
evidence of the variation.

The software under test is the working tree (`ITF_SURVEY_SW=tree`, the
default) or any of the **five most recent published releases**
(`latest`, `prev:N`, `tag:<v>`, validated against the GitHub release
list at run start). The universe is enumerated from that exact tree and
the same tree is staged into the guest — a survey of an older release
samples that release's real surface. GUI items run the real window
under a private in-guest Xvfb (`survey/gui_probe.py`, crash-resume,
per-item verdicts); CLI items run from the staged tree under a pinned
`ZFSCONFIG_PATH` against survey-owned scratch state, with per-command
recipes whose depth (full flow vs argument-validation surface) is
disclosed per item.

Defects found in a past release are recorded in `FINDINGS.md` and fixed
**forward** in the dev tree — there is no back-porting; the release
tarball stays a read-only input. The repair verification is the replay:
the same archived list re-run against the fixed tree.

## Post-install baseline template

Journeys whose scenario begins *after* installation start from a
**baseline template**: a guest built once through the real first-time
user path (OS install → product install → OS package updates → boot
health gate) and converted to a Proxmox template (`itf template build`).
`itf_journey_stage_from_template` clones it — linked by default (see the
bullet below), which is metadata-only and instant — so the journey is at
the post-install point in seconds instead of repeating the
~15–20-minute install.

Three profiles share the build machinery. **storage** (the default) is
that Debian + product baseline; **compute** is a Proxmox VE host built
from the configured PVE ISO by its auto-installer (no product — the
installer's deploy push to the compute host is part of what the
two-node journeys exercise); **ubuntu** is an Ubuntu Server LTS guest
built from the configured Ubuntu ISO by autoinstall, carrying the ZFS
userland but no product — it exists as a plain OpenZFS-version leg for
the j21 probe matrix (Debian ≈ 2.3, PVE ≈ 2.4-pve, Ubuntu LTS ≈ 2.2),
with freshness keyed on the ISO name like the compute profile. Journeys
that support profile selection take it at run time
(`itf journey run j21-zfs-probes --template ubuntu`).

- **Linked clones, by design.** The itf guest storage is LVM-thin, which
  supports Proxmox linked clones: each guest clones from the template's
  base- volume as an LVM thin snapshot — metadata-only and instant
  instead of an allocated-block copy. The link is not tracked in volume
  IDs, and a thin snapshot keeps its blocks when the origin is destroyed,
  so a template rebuild can never break a running journey's guest.
  `ITF_CLONE_MODE=full` in the site config opts back into full copies
  for guest storages without linked-clone support.
- **Rebuilds are from scratch, never in-place upgrades.** The baseline
  must keep first-time-user fidelity — no version-dir drift, no
  upgrade-path contamination. `itf template build` refuses when the
  existing template already reflects the current release (or repo rev,
  for dev tarballs); `--force` overrides. A rebuild costs one
  unattended install and doubles as a smoke run.
- **OS currency is a build-time property.** The build applies all
  pending package updates *after* the product install and reboots onto
  a new kernel when one arrives, gated on: newest kernel running, ZFS
  module loadable, product wiring intact. Every clone inherits a
  current, proven-bootable OS — this also proves an installed system
  survives a routine `apt full-upgrade`.
- **The stamp rides in the PVE description field** (`qm set
  --description`, read via `qm config`): software source, product
  version, repo rev, kernel, and build time travel with the template
  with no new write paths on the base host. `itf template status` and
  `itf preflight` surface it.
- **The template is protected by the guard.** Mutating qm verbs against
  the VMID carrying the template's name are refused (clone is exempt —
  reading the template is its purpose); `itf template build`/`destroy`
  are the sanctioned management paths and are audit-logged like every
  other mutation.
- **The template's *product* version is allowed to go stale — j10
  depends on it.** A clone of a stale template is a genuinely installed
  system running an older release, the exact starting state the
  release-upgrade journey needs. **j10-release-upgrade** walks the real
  user upgrade path on such a clone: download the new release (the
  upgrader runs from the downloaded tree — deployments older than
  0.125.0 predate the `upgrade-zfsutilities` PATH command), decline the
  download offer (system must stay untouched), inject local
  modifications into the deployed old tree, run
  `./bin/upgrade-zfsutilities` (the change scan must
  detect them, the upgrade lists and — after approval — salvages them
  under `salvaged-changes/`, deploys the new version via
  `deploy-version`, and stops *without activating*), activate with the
  printed `switch-version` command, verify wiring/config/version
  retention, and rerun the upgrade to see "Nothing to upgrade". Under
  `ITF_SW_SOURCE=dev-tarball` the journey serves a fake "latest
  release" (latest.json plus a release-shaped tarball of the dev tree)
  and points the guest's upgrade at it via `ZFSUTILITIES_RELEASE_API`;
  the old version's change scan falls back to the pristine GitHub tag
  tarball when the deployed tree predates `MANIFEST.sha256`, or — when
  the tag is missing (many historical releases were never tagged) — to
  a baseline the journey serves via `ZFSUTILITIES_TAG_TARBALL_URL`
  (the upgrade itself captures a baseline manifest when no baseline is
  obtainable; F-025, repair plan 021). j10 fails
  fast with a PREP hint when the template is no longer strictly older
  than the tree under test — the fix is running it from a newer tree,
  not rebuilding the template.

  **j12-interrupted-upgrade** shares that staging (factored into
  `itf_journey_stage_upgrade_env` in `journeys/common.sh`) and adds the
  failure injection an interrupted upgrade deserves: a guest-side
  wrapper backgrounds the upgrader under `setsid` and signals its
  process group — the user-visible effect of a lost terminal session.
  A SIGTERM in the early phase must run the upgrader's EXIT trap
  (staging cleaned) and leave nothing deployed, salvaged, or activated;
  a SIGKILL the moment the transcript shows the deploy marker must
  leave the running system untouched next to a *partial*
  `versions/<v>` directory (no `MANIFEST.sha256` — it is written last)
  and the salvage archive the killed run already made. The recovery is
  simply re-running the same `upgrade-zfsutilities`: it re-detects and
  re-salvages the injected modifications (a full upgrade, not a
  degraded one), repairs the partial version dir in place, deploys
  without activating, and the journey finishes with `switch-version`,
  wiring verification, and the "Nothing to upgrade" rerun.

  **j19-baseline-capture** exercises the trust-on-first-upgrade
  capture path itself — the F-025 behavior the other two upgrade
  journeys bypass, because their shared staging always provisions a
  pristine scan source (the GitHub tag tarball, or the as-deployed
  tree via `ZFSUTILITIES_TAG_TARBALL_URL`). j19 runs the same staging
  with `ITF_UPGRADE_BASELINE=none`: no tag tarball, no override, so
  the first upgrade on the untagged old tree cannot obtain any
  baseline and must capture one from the active tree itself.
  Modifications injected before that upgrade are absorbed into the
  captured manifest — indistinguishable from pristine content: not
  flagged, nothing salvageable — and the manifest lands additively in
  the still-active old tree, which every later upgrade then scans
  against. The journey's second upgrade proves exactly that: new
  modifications (modified, added, and removed — the removal
  classification's first journey exercise) are detected against the
  captured baseline, salvaged with their local content, and diffing
  degrades honestly (no pristine source exists for an untagged
  version). Then `switch-version` and wiring verification, as in j10.

  **j23-two-node-release-upgrade** covers the remote half none of the
  above touches: the upgrade driven from a storage host whose
  `deploy.conf` groups name a compute host. The journey composes the
  j05 lab, then stages the never-upgraded site — the stale template's
  old tree is pushed to the compute host and `switch-version`'d on
  both hosts, so every deployment target runs old-active. A declined
  download offer must change nothing on either target — the deployed
  `MANIFEST.sha256` timestamps recorded beforehand prove no re-deploy
  (the j05 install already left the target version dir in place, so
  its mere existence proves nothing). Pass 1 walks
  trust-on-first-upgrade with no pristine source: baseline manifests
  are captured on the local tree *and* over ssh on the compute host,
  the new version deploys to every target without activation — proven
  by that manifest being rewritten on both hosts — and both printed
  switch-version commands are then run unmodified (the printed form is
  the absolute path, which needs no login-shell PATH wiring). Pass 2
  re-labels the served release one patch newer (the VERSION/tag
  mismatch WARN asserted as honest) and injects per-host modifications
  — storage modified+added, compute modified+added+removed. The scan
  must list each host under its own section, pull the compute host's
  changed files back over rsync to render unified diffs, and archive
  salvage copies carrying local content on each host. The journey
  finishes with per-host activation, version retention, and the
  up-to-date rerun. It runs under `ITF_SW_SOURCE=dev-tarball` only:
  both passes point at an itf-served "latest release", and pass 2
  rewrites it — impossible against real GitHub. Its pass-2 re-label
  and per-host modification staging live as shared stages in
  `common.sh` (`itf_journey_stage_upgrade_relabel`,
  `itf_journey_stage_two_node_mods`) — j25 composes them for its own
  premise.

  **j25-two-node-interrupted-upgrade-keys** closes the coverage map's
  last gap row: j12's injections against the encrypted two-node lab
  with keys *pending*. The lab is installed from the tree under test,
  so a stale-template rollback would boot a keys-absent site with
  pre-encrypted-LUN tooling; instead the staging runs in relabel mode
  (`itf_journey_stage_upgrade_env --relabel`) and serves the same tree
  one patch newer — every interrupted deploy targets a
  `versions/<v>` that exists on no host, so the partial-dir oracles
  stay deterministic. After the healthy baseline is proven (markers
  written through BOTH LUNs, keystatus available, `--check` green,
  sha256 baselines over both saveconfig files plus the pool-resident
  state map), storage reboots with the key device absent: the boot
  journal must read PENDING, the session re-logs in unaided, the plain
  LUN keeps serving its marker, and the encrypted link is classified
  (a stale device node — the R-02/R-03 shape, never read while
  pending — or absent). Three injections then fire with the compute
  fence timer parked (j16/j18 scenario hygiene): a SIGTERM at the scan
  marker must run the EXIT trap — staging gone AND both SSH control
  masters closed — with nothing deployed, salvaged, or activated on
  either host; a SIGKILL at the local version-dir mkdir leaves the
  partial dir without `MANIFEST.sha256` on storage beside salvage
  archives on BOTH hosts (remote salvage precedes deploy); and a
  SIGKILL aimed at the remote sync (local MANIFEST present, compute
  dir appearing) leaves storage complete and the compute dir
  classified absent, partial, or complete (the sync finished before
  the kill). The recovery re-run, still
  keys-pending, must do the full per-host scan/salvage/diff walk,
  repair both version dirs in place (`sha256sum -c MANIFEST.sha256`
  clean on both hosts), and stop before activation. Per-stage oracles
  hold throughout: `--check` exits 3 with every drift line
  keys-pending, the survival hashes stay byte-identical, and the
  plain-LUN marker still reads. Activating both hosts with the printed
  commands (login-shell wrapped) must leave that posture untouched —
  the gap's core: nothing in the upgrade path may write iSCSI state
  while keys are pending. Activation restarts the fence timer and its
  tick fires at once, so the journey parks the timer again and waits
  the tick out before judging; in the absent-link shape that tick's
  documented saveconfig re-save is tolerated (F-042's healed shape —
  the pool map must stay byte-identical).
  One manual fence tick then runs the upgraded fence under keys
  pending (classified: rc 0 through the stale node, or rc 1 naming
  only the encrypted LUN with the pool map preserved), and the
  up-to-date rerun is a no-op. The closing key ceremony rebuilds the
  encrypted LUN on the upgraded tree — the saveconfig index directly,
  or the map-recorded fallback when a keys-pending tick save dropped
  the record — and both markers read back byte-exact before the
  `--check` gate, a healthy tick, and a clean `safe-iscsi-save` close
  the run. Like j23 it is dev-tarball only.

## Fast re-verification: `journey run --rerun`

Fix-verify loops are the daily reality of the repair workflow, and the
staging step — the template clone on a clone-start journey, the OS
install on an install-start one — is also the most redundant one on a
re-verify: the previous run's guests are still there, each carrying its
staging checkpoint (`as-cloned`, or `os-installed` on install-start
journeys like j01/j08/j09). `itf journey run
<name> --rerun` uses exactly that:

- The driver resolves the source run (the newest run of the same journey
  that is not still active and recorded at least one guest), writes the
  new run's `rerun-guests.tsv` from its guest records, and names the
  choice in a `rerun source` INFO step.
- Each staging stage (`itf_journey_stage_from_template`,
  `itf_journey_stage_os`) finds its guest in the spec, verifies it still
  exists and carries its checkpoint, rolls it back (`qm rollback`, a
  guarded verb), starts it, and re-discovers its IP — the report reads
  "guest rolled back to as-cloned … no re-clone" (or "… to
  os-installed … no reinstall"). Everything after replays in full; a
  rolled-back install-start guest is a clean Debian with the
  prerequisites genuinely missing, so failure-path journeys keep their
  coverage.
- Only the staging step is skipped. The product download and install
  stages re-run deliberately: they install the tree under test, which is
  the point of the re-verify. (Deeper checkpoints such as `pools-created`
  are intentionally NOT rerun sources — replaying from one would leave
  the lab pre-installed and route the installer into its upgrade branch,
  silently weakening coverage.)
- Refusals are explicit, never a silent fallback: no prior run, an
  active source run, destroyed guests, or a missing checkpoint each fail
  fast with the remedy (run fresh, no `--rerun`).
- Snapshots newer than the checkpoint survive a `qm rollback` on this
  stack but go stale, and the replay re-snapshots the same names — so
  the rerun branch removes them explicitly before rolling back.  The
  rollback reverts VM config (hot-plugged NICs, the pool disk), which
  the journey re-attaches — a rerun is indistinguishable from a fresh
  staging in coverage.  An install-start guest's checkpoint config
  still carries the installer-time CPU freeze, so the `stage_os` rerun
  clears it between the rollback and the start (clones get the same
  clearing in `itf_guest_clone`). When the loop is done, nothing to
  remember: a green verdict destroys the run's own guests at verdict
  time — pass `--keep` on the runs you expect to iterate past, and
  settle anything deliberately kept with `itf guest sweep --apply`.

## One run at a time: the run lock

Itf serializes itself. `itf journey run` and `itf template build` take a
machine-wide advisory kernel lock (`lib/runlock-lib.sh`, flock on
`/tmp/itf-active-run.lock`) before doing anything else. The reason is
physical: every run binds the site-configured HTTP port on the dev host,
arms the shared UDP-514 installer-syslog listener on a base host, and
consumes base-host RAM/storage that fits one two-node lab — and the
parallel repo lanes (pub/pub2/pub3 worktrees) share all of it while each
lane's `itf status` can only see its own tree's runs. A second starter
therefore waits (heartbeat every 30 s, up to `ITF_RUNLOCK_WAIT` seconds,
default 7200; `ITF_RUNLOCK_WAIT=0` refuses immediately) and both output
streams and `itf status` (`== run lock ==`) name the active holder —
journey, pid, start time, and which repo tree holds the fence. The lock
is held on an open file descriptor by the run's own process, so any
death (kill, crash, lost session) releases it instantly: there is no
stale-lock state and no cleanup command. This fence is deliberately not
the product's dataset lock manager — that one keys by ZFS dataset for
root-run product operations, while this one keys by dev host and must
work for the unprivileged orchestrator.

The flock fences dev-side processes only; the run's guests live on the
base hosts and do not die with the dev host. After a mid-run dev
restart the lock is correctly free while the interrupted run's guests
keep running on the bases, so every start re-verifies while holding the
lock (`itf_runlock_orphan_fence`): guests recorded by interrupted runs
of this tree that still exist in their base's `qm list` — the base host
is the authority, which is what makes the check correct across dev
restarts — refuse the new start, naming each leftover and its two
recoveries (reuse with `itf journey run <same> --rerun`, discard with
`itf guest destroy`). Ownership is decided by NAME, not just VMID:
every guest is named for its run (`itf_guest_qname` — the journey's
guest name plus the run timestamp, recorded as the 4th field of each
`guest*.txt`), so a live VMID whose qm name differs from the recorded
one is another run's guest (the VMID was legitimately recycled after
this run's guest was destroyed) — the stale claim is noted and ignored,
and no destroy or rerun is ever offered against that guest. Records
older than the name field keep the fail-closed VMID-only match. A rerun
exempts exactly the guests it takes over;
a results directory with no interrupted runs costs no base query at
all; an unreachable base fails closed (unverified is not clean); and
guests of finished runs are exempt by design — they are the kept lab of
the run → fix → `--rerun` loop, and only an interrupted run means the
operator lost track of guests that are still consuming the base.

## Guest lifecycle: verdict-time teardown and the sweep

The disposition is automatic, in the driver
(`itf_guest_verdict_teardown`, called between the journey's verdict and
`itf_report_finish`):

- **Green verdict, no `--keep`** — the run's own guests are destroyed
  and their `guest*.txt` records deleted. The audit trail is the INFO
  steps this records; the invariant it preserves is that a run dir with
  guest records is a lab that may still exist, which is exactly what
  rerun sourcing and the orphan fence rely on (after a teardown, the
  next `--rerun` refuses with the run-fresh remedy — the designed
  degradation, never a silent fallback).
- **`--keep` / `ITF_KEEP_GUESTS=1`** — the lab is retained for the
  `--rerun` loop; pass it on runs you expect to iterate past.
- **Red verdict** — the lab is always kept: post-mortem reading and the
  fix-then-rerun loop need it.

Ownership follows the fence's NAME law (`itf_guest_records_resolve`):
one `qm list` per involved base is the authority; a guest is destroyed
only when the live VMID still carries the record's run-tagged name. A
different live name (a legitimately recycled VMID), a vacated VMID, a
legacy nameless record, and an unreachable base are each fail-closed —
nothing destroyed on guesswork, records kept or stale-removed exactly as
the fence treats stale claims. Templates are structurally safe: destroy
fires only on a name match, and a successful template build renames its
VM away from the run-tagged record name before the run finishes.

`itf guest sweep [--apply] [--force] [--age HOURS]` settles the
remainder — the backlog that predates the hook, `--keep` labs whose loop
ended, and red labs after triage. It walks this tree's run records only
(each lane sweeps its own), takes the machine-global run lock so it can
never race a live journey in any lane, selects done green runs past the
age gate (`ITF_SWEEP_AGE_HOURS`, default 24 h; red runs only with
`--force`), and resolves records with the same name law. It is
plan-only until `--apply` — the printed plan is the exact destroy list.

## Two-node topology

The cycle-2 journeys model the production two-node layout (storage node
+ compute/Proxmox node) on the base VMs:

- **Role split across base hosts.** `ITF_STORAGE_BASE` hosts the
  storage-role guest (Debian + product, cloned from the storage
  template); `ITF_COMPUTE_BASE` hosts the compute-role guest cloned
  from the **compute template**. Both role bases must be members of
  `ITF_BASE_HOSTS`, and the guard's template protection covers both
  template names.
- **The compute template is PVE installed from the Proxmox VE ISO** —
  not a Debian guest with PVE layered on top, because that is what a
  real compute node runs. `itf template build --profile compute`
  customizes the cached PVE ISO the way the Debian path customizes its
  netinst: an embedded answer file (auto-install mode, DHCP networking,
  ext4 on the first disk, root SSH keys), a serial-console kernel
  append so the install is watchable and gateable, and a first-boot
  hook that swaps the enterprise repositories for the no-subscription
  ones and installs the guest agent. Two mastering details are handled
  by the rebuild: the relative symlinks 7z refuses to extract are
  restored from its refusal log, and grub's El Torito boot image gets
  its embedded absolute-sector reference re-pointed at the rebuilt
  layout (without that, the guest hangs silently right after
  "Booting from DVD/CD..."). The compute template carries PVE only —
  the installer's deploy push to the compute host is part of what the
  journeys exercise.
- **The cross-node link rides the shared bridge.** Each guest gets a
  second NIC (`--net1`), static addresses from the site-configured P2P
  pair (a dedicated subnet modeling production's storage↔compute link
  without touching any base network config), `/etc/hosts` entries both
  ways, and exchanged root SSH keys — the checks the two-node
  installer performs, driven as journey pre-work.
- **j05-two-node-install** runs the full scenario: clone both guests,
  stand up the link, create the documented test pools on the storage
  guest, run `check-prerequisites --two-node` (expected to fail on the
  unconfigured compute side), feed `install-two-node` its interactive
  answers, verify the deployed wiring on both guests, and close the
  loop with a first-LUN round trip — a VM created and disk provisioned
  on the compute host must arrive over iSCSI and be saved back on the
  storage side. (The lab-builder function is reusable: j06 composes the
  entire j05 sequence before its own stages.)
- **Same-IP staging collisions converge once.** The compute template's
  management address is a STATIC address baked in at build time; while
  the compute clone is still booting, the LAN DHCP pool can lease that
  address to the storage clone (whose duplicate-address detection is
  blind while the address's owner is down), leaving both role records
  on one address. j05's hostname gate detects the collision and
  converges through one bounded storage-side re-lease: the bounce runs
  through the guest agent (ssh to the collided address reaches
  whichever guest answers it), the re-acquired address must differ
  from the collided one, and the guest record is rewritten before the
  gate re-runs. A re-lease that does not produce a different address
  fails the journey — no silent fallback.
- **j06-guest-probe-validator** composes the j05 lab and then runs
  `share/dev/validate-guestfs-probe.sh` live on the storage guest,
  the way production runs it: a positive pass must show a populated
  sample (pools, datasets, PVE configs fetched from the compute guest,
  probe targets) with the stopped VM's disk probed and a recorded
  reason, and a negative control (compute host made unresolvable on the
  storage guest) must make the validator exit non-zero with the ssh
  failure reason printed — the fence against the vacuous
  `LIVE PASS`-against-nothing incident (2026-10-22). Requires
  `ITF_SW_SOURCE=dev-tarball` because it verifies working-tree repairs.
- **j24-two-node-uninstall-reinstall** composes the same lab and walks
  j02's cycle at two-node scale with the LUNs live and VM 101
  referencing one. Interactive `--dry-run`s on *each* host are the
  uninstall-intent report: the menu, peer question, and confirm walk
  through, the purge actions echo as `[DRY-RUN]`, the targets are
  promised untouched, and the compute leg prints the PVE-patch
  never-reversed note (the patch file only exists there) — with zero
  mutation, proven afterwards. The real `--purge --all-nodes --yes`
  pushes the peer leg over ssh, and the journey then asserts both
  halves of the contract at once: every product wire is gone on both
  hosts (j02's scan plus node.conf, deploy.conf, the lib symlinks, the
  fence units, the rtslib drop-in), while the *site* survives
  byte-for-byte — pools online, LIO targets and the LUN-0 backstore
  live, both saveconfig files and the pool-resident
  `iscsi-state.json` (the bare-metal recovery authority)
  hash-identical, the
  session still logged in, the by-path device present, VM 101's scsi
  line unchanged, and a 1-KiB marker written through the LUN still
  reading back. The reinstall runs from the checkout the uninstaller
  never touches, over the live LIO tree: the recurrence fence must
  default the IQN prefix to the live targets' (no namespace fork —
  target count is compared against the baseline), `setup-iscsi-targets`
  must find every target already existing, and the wiring, fence units,
  and a healthy fence tick return. `export-iscsi-state --check`
  finds the live tree matching the pool-resident records, a clean
  `safe-iscsi-save` refreshes them, `show-lun-map` still lists the
  surviving LUN, and a second disk created through the reinstalled
  product takes LUN 1 beside the untouched LUN 0 (the map then lists
  exactly two LUNs) — marker readback still matching. Both software
  sources work once the deployed release carries the interactive-menu
  fix (F-049, 0.140.0 and later); an older release's uninstaller
  cannot answer its own menu.

## Recovery-scenario lab layer

The recovery-scenario journeys (boot-and-keys, LIO loss, interrupted
operations, compute/power events) build on shared lab machinery in
`journeys/common.sh` rather than per-journey copies:

- **`itf_journey_stage_test_pools`** is the documented three-RAIDZ1
  recipe as one stage (pool-disk hot-plug, guest recipe,
  `pools-created` snapshot); j01, j04, j05, and j11 all call it.
- **`itf_single_node_lab_main`** is the shared single-node prefix
  (template clone → installed-state verify → test pools) behind j04
  and j11.
- **`itf_journey_stage_reboot_guest`** reboots a staged role guest
  (in-guest `reboot`, or `--power` for a guarded stop/start power
  cycle), waits for ssh, re-discovers a re-leased DHCP address, and
  rewrites the guest record — callers re-read coordinates after it.
  Its split halves, `itf_reboot_guest_begin` / `itf_reboot_guest_wait`,
  exist for journeys that observe peer-node fallout INSIDE the outage
  window (j15's S1b samples the compute node between the two).
- **`itf_journey_stage_encrypted_key_lun`** (opt-in via
  `j05_two_node_lab_main --encrypted-keys`, default off so composing
  journeys are unaffected) models production's removable LUKS key
  store: a small scsi2 disk is LUKS-formatted on the storage guest,
  carries an ext4 `ZFSkeys` filesystem with the per-pool key at the
  conventional path plus the production `noauto` fstab line, and
  `new-vm-disk --encrypted` then creates the encrypted vm-101-disk-1
  through the product (its key-path prompt is answered over the piped
  feed; the passphrase itself reaches `cryptsetup` via stdin, never in
  argv). The stage ends in the production posture: store locked and
  detached, keystatus still `available`. Insert/remove helpers
  re-attach and detach the captured key-device volume; the unlock/mount
  helper drives the operator's blind-recovery step.
- **The VM-OS image** (`itf vmimage build`, built once and cached like
  the ISOs) is a minimal preseed Debian whose disk dump is written
  onto product-created zvols (`itf_vmos_image_zvol`) so a workload VM
  boots from its iSCSI LUN. The preseed installs the qemu guest agent,
  and the build self-verifies the exact property scenarios depend on:
  the dumped image is restored onto a blank disk, booted, and must
  answer `qm agent <vmid> ping` before anything is cached.
- **Workload helpers** drive that VM from the compute guest through the
  guest agent (never ssh into it): a boot gate (`itf_vm_boot_with_agent`,
  TCG like every lab boot proof), a 1 Hz timestamp writer with per-tick
  sync on the LUN-backed root filesystem, sample/checksum retrieval,
  and a stall-gap parser over saved samples.
- **The j15 boot-and-keys machinery** layers the recovery observables on
  top: `itf_journey_stage_boot_workload_lab` stages the scenario lab
  (VM 101 on a plain OS LUN as the everyday workload VM, VM 202 on an
  encrypted OS LUN, writers running, fence timer premise asserted,
  pre-reboot `safe-iscsi-save` + `export-iscsi-state --check` gates);
  `itf_key_ceremony` runs the operator's documented key ceremony
  (insert → luksOpen/mount → `zfs load-key -a` → recover or add →
  lock/detach) as one stage; `itf_storage_boot_state` captures the boot
  journal and cross-unit import ordering while `itf_boot_journal_verdict`
  (a pure, fixture-tested parser) asserts the verdict, the echo order,
  and per-LUN DRIFT/Added naming; `itf_compute_fallout_sample`,
  `itf_fence_tick`, and the by-path link-presence pollers record what
  the compute node saw through each event.

The **j15-iscsi-boot-keys** journey runs the boot-and-keys scenario
catalog against that lab: S1 (reboot with the key device absent: FAILED
+ DRIFT journal oracle, the encrypted-root VM is unusable — either a
start abort or a start that "succeeds" against a stale device node and
then never boots, blind recovery via `iscsi-recover-encrypted-luns`),
S1c (the second reboot repeats the same PENDING shape — the
recovery-then-reboot cycle is stable — and convergence is proven WITHIN
the boot by a manual `--check` reporting no drift), S1b (a storage
power event with both workload VMs running: the sessions CLING to the
dead storage — PVE patches the iSCSI replacement timeout to 24 h, so
by-path links stay present, the fence's only outage signal, and a
fence tick inside the outage honestly reports healthy — recorded as a
design datum; after return the links re-login automatically but BOTH
running VMs keep stalled writers until a stop/start, classified from
writer samples), S2 (the zfs-keys.md `iscsi-add-encrypted-luns` path),
S3 (`restart-iscsi-services` — the designed refusal with VMs running,
then the one-command path with compute fallout), S4/M4/M1 (wrong
passphrase, pool A's key against pool B, mistyped key-file paths at
`new-vm-disk --encrypted`), and S5a/S5b: a `file://` keylocation on the
unencrypted root filesystem still journals PENDING at boot (availability
is not loadedness — no loader exists), while the one posture that
legitimately journals boot-time OK is a lab-authored one-shot
key-loading unit ordered before the restore (the drop-in's "separate
key-loading unit" clause), which also prototypes the ordering a shipped
optional unit would need.  The boot-verdict oracle follows the
documented semantics (`two-node-config.md`): every keys-absent boot
journals `post-restore verification PENDING` (the encrypted-aware
verdict, distinct from FAILED's unexpected drift) with DRIFT detail
until the key ceremony completes.

- **Scenario windows park the compute fence timer.** Operator-paced
  recovery arcs (j16's loss scenarios, j18's key ceremony) assume nothing
  heals before the operator surface under test shows its evidence — but
  the always-on 5-minute fence tick can land inside the window and its
  ssh reconcile heals the tree first (live-proven: a tick rebuilt every
  LUN mid-scenario). Those journeys `systemctl stop
  zfsutilities-iscsi-fence.timer` for their mutation-sensitive stretch
  (an INFO step records it) and restart + assert it before their final
  tick gate; the unattended heal itself is j14/j18 coverage.

The **j16-iscsi-total-loss** journey runs the LIO-loss scenario catalog
on the same lab (keys stay loaded throughout — the storage guest is
never rebooted): S6 destroys every live mapping+backstore while the
OS-disk files still record them (the VM-refs detector signature, `--check`
drifting on every LUN, and a `reconcile-iscsi-state` rebuild of all
LUNs from the pool map — the encrypted ones included — with running-VM
fallout sampled through the outage); S9 replays the 2026-10-27
3-of-33 incident shape at unit scale (one hand-deleted mapping:
`safe-iscsi-save`'s mapping-loss FATAL, the verifier naming the LUN,
PVE aborting VM start on the vanished link after the session cycle,
and `repair-iscsi-luns` re-mapping at the recorded index); S7a/S7b
pair a targets-intact wipe — where `iscsi-restore-luns` performs the
full saveconfig-authority restore including ACL grants and a staged
non-identity `mapped_lun 8 → tpg_lun 0` grant — with a targets-too
wipe, where the restore attempt honestly refuses without targets and
the recovery runs through `setup-iscsi-targets` plus the map-driven
reconcile (the map's grants dimension is the surviving authority:
setup's own save overwrites the saveconfig records exactly when they
are needed, but the map records each initiator's grant pairs, so the
reconcile recreates the staged non-identity grant exactly); S8
corrupts `saveconfig.json` (the unit restart
restores from `saveconfig-boot.json` unaffected, the pre-start backup
preserves the corrupt bytes as evidence, `safe-iscsi-save` FATALs on
the unparseable authority, and the FATAL's own force escape
`targetcli saveconfig` heals the file from the intact live tree) with
S8b proving the boot-config-absent fallback branch fails loudly; and
S18 exercises the pool-identity fence live — an exported expected pool
WARNs on `check-prerequisites --two-node` and in
`setup-iscsi-targets`' own block (never with a reconcile offer) while
`export-iscsi-state --check` stays silent on the one-sided name (the
documented offline-pool tolerance), and a destroyed+recreated pool
emits the `pools.<name>: GUID changed` DRIFT line, converging only
through the operator-confirmed `safe-iscsi-save` whose map refresh
records the new GUID.

The **j17-iscsi-interrupted-ops** journey runs the interrupted &
contradictory-operations catalog on the same lab (keys stay loaded; the
workload VMs stay parked; service restarts only, never a storage
reboot): M5 proves the luksOpen retry arc (three mistyped passphrases
rejected cleanly with no mapper leak, the fourth accepted); S13 proves
`new-vm-disk`'s collision guards both clean (a second run for the same
disk FATALs before any mutation) and against the script's own half
state (a SIGINT after the zvol create leaves a zvol without a LUN that
the next run refuses to touch — `remove-vm-disk` WARN-skips the gone
pieces and converges it); M2 proves reconcile's apply prompt defaults
SAFE ("yes", "yup", and bare Enter all abort with rc 1 and the state
frozen; only the explicit Y applies); M3 proves `remove-vm-disk`'s
identifier validation (wrong VMID, wrong disk number, and unknown pool
all FATAL before any mutation — and "yes" at the destroy confirmations
is not y), recording the y/N-not-type-to-confirm guard as a UX-gap row;
S11 interrupts `remove-vm-disk` between its teardown steps (the half
state — zvol and manifest intact, LUN gone — drifts in `--check`,
`safe-iscsi-save` refuses the degraded save, and the re-run converges
end to end); S10 interrupts `reconcile-iscsi-state` mid-apply (the
partial tree keeps the pool map as an untouched recovery authority, the
re-run rebuilds the remainder, and a third run finds nothing to do);
S14 attempts the hand `zfs destroy` of an exported zvol under a live
LUN and the zvol layer refuses it while LIO holds the device
("dataset is busy") — the campaign's stale-live-LUN premise is
structurally fenced at the zvol layer (F-041), so the journey records
the fence and skips the sweep; and S12 runs reconcile and
`iscsi-restore-luns` concurrently over the same wiped tree, proving the
global `iscsi-lio` fence live (repair-plan 024, F-040): the second
mutator is refused before it can mutate, its WARN naming the running
sibling by pid and command, and the sequential re-run converges the tree.

The **j18-compute-power-events** journey runs the compute & power-event
catalog on the same lab (keys stay loaded through S15; S16's storage
power cycle unloads them and closes through the j15 recovery arc):
S15 proves a compute-node reboot the everyday way, in two legs — the
default posture returns the iSCSI sessions, the by-path links, and a
green fence tick unaided while both VMs stay stopped (nothing
restarts them without onboot; the operator's `qm start` restarts them
and the writer data survives: the log grows past the baseline, the
pre-event prefix checksum is unchanged, and the outage appears as one
gap), while `--onboot 1` asserts PVE's boot-time autostart in both its
live shapes — the unattended return, or the attempted-and-raced start
(startall fires before the iSCSI links exist, fails on the by-path
stat, and never retries: onboot alone does not return running VMs
unattended on iSCSI disks — a REQUIREMENTS row, since the fence heals
links but not starts), with the contrast VM without onboot staying
down; S16 power-cycles both nodes
with storage slow to return — the compute node boots into a
storage-less world (zero sessions ever established, so nothing clings
and nothing rescan-able exists), the fence tick fires against the
unreachable storage host (per-ref WARNs, rescan problems, the ssh-255
WARN, the still-missing FATAL, never the reported-problems WARN),
storage's late return journals the PENDING+DRIFT boot oracle for the
encrypted LUNs, and the post-return truth is measured live: the
sessions and the plain LUNs return unaided, while the return tick
stays red exactly for the keys-pending encrypted LUN (reconcile
skips it with the `keys not loaded?` hint and preserves the pool map
as the recovery authority) — F-042: that same return tick's trailing
save drops the encrypted records from saveconfig.json, and the
documented `iscsi-recover-encrypted-luns` restores both LUNs directly
through the pool-map fallback (the map's recorded indexes, repair-plan
023 executed), with the keys-loaded tick proving convergence and
recover's re-run healing the ACL grants. Both VMs then boot with
intact writers and `--check` reads rc 0; S17 leaves an
orphan live-exported LUN behind in both shapes (a VM deleted in PVE
and a hand-removed scsi line) and proves every checking surface blind
to it by design (the fence, `--check`, `rescan-storage`,
`show-lun-map`, and `repair-vm-disk-refs --dry-run` each walk
VM-config refs or LIO-vs-map only) — `remove-vm`'s classifier is the
one surface that names and spares it, and both documented teardown
paths converge (`remove-vm --cleanup-orphans` through the LIO-aware
`zfsdelfs`; `remove-vm-disk` after the hand-removal its prompts ask
about) — each teardown leaving a ghost 0-GiB device row that
rescan-storage cannot drop (only a session re-login clears it;
REQUIREMENTS row).

## Findings and repair loop

Failures observed through the end-user surface become entries in
`tests/integrated/FINDINGS.md`. A finding is turned into a numbered
repair plan (`tests/integrated/repair-plans/NNN-slug.md`) proposing a
change **in this repository**; repairs are executed only after explicit
user approval (or under an explicit standing approval for a repair
campaign, recorded in the finding's status cell), shipped to the guest
as a dev tarball, and verified by
rerunning the affected journeys. Product bugs are never fixed inside a
guest.

Every finding ends in exactly one terminal state: fixed in-cycle,
repair-plan executed + journey-verified, DOCUMENTED (product-truth rows
→ repo docs; UX/future-direction rows → the
[requirements register](#requirements-register)), accepted/waived by the
user, or superseded. No row stays open past a campaign wrap.

## Requirements register

UX gaps and design directions that the journeys prove — but that are
not defects to fix now — are seeded into
`tests/integrated/REQUIREMENTS.md` as numbered rows (R-nn) with their
source scenario and a status (`open` → promoted to a repair plan →
addressed, or declined). The register is the durable input for future
coding; promotion from a row to a plan is the owner's call. Journey
coverage by product surface and node mode is tracked in the
[ITF Coverage Map](itf-coverage.md); gap rows there are candidates only,
built when a real need names them.

## Testing the framework itself

The itf libraries have their own mock-based suites in the default
`tests/run-tests` set:

```bash
tests/run-tests test-itf-config test-itf-base-guard test-itf-report \
    test-itf-ssh test-itf-template test-itf-driver test-itf-lab-stages
```

They cover fail-closed site-config loading, example-file validity, the
confinement guard's refusals (VMID range, non-itf storages, non-allow-
listed verbs, path confinement, baseline-template protection for both
template names), dry-run behavior, audit ordering, the run-report
writer, the dev-host HTTP serve/fetch/stop round-trip used to deliver
preseeds and dev tarballs to guests, the template
stamp/resolution/clone/freshness logic for both profiles, the driver's
dispatch/usage surface (journey listing, ISO selector, profile flags),
and the lab-layer stages themselves (`test-itf-lab-stages`: the test
pools stage, the single-node lab, the VM-OS build/dump/self-verify
orchestration, the workload helpers and stall-gap parser, the reboot
stage with address rediscovery, the keystore helpers — including that
the LUKS passphrase never appears in any command and that the encrypted
lab tail stays off unless the flag is passed — and the boot-and-keys
machinery: the reboot begin/wait split, the boot-journal parser against
fixtures, the key ceremony, the load-keys/keystatus gates, the
link-presence/fence-tick/fallout observables, and the boot-workload
staging orchestration).
