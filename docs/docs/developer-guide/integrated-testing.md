# Integrated Testing

The mock-based suites verify one script or module at a time, against
simulated ZFS, SSH, and GTK surfaces. The **integrated testing
framework** (`tests/integrated/`, driver command `itf`) complements them
by verifying the *ZFSutilities experience* on real systems. An orchestrator
on the development machine:

- creates disposable nested guests on the base Proxmox test VMs;
- installs a target OS from an ISO;
- downloads ZFSutilities the way a real user would — a GitHub release
  tarball, or a dev tarball when a repair needs verifying;
- runs the ZFSutilities installer;
- drives day-to-day workflows and tests for outcomes in the guest.

Unit-style test suites are deliberately **not** run in the guests.

```
dev (itf orchestrator)
  └── base PVE VMs (PROTECTED)
        │   guarded guest-lifecycle commands only, via ssh + sudo -n
        └── nested guest (DISPOSABLE — anything goes)
              └── ZFSutilities under test (release or dev tarball)
```

A second base host can serve in the **compute role** (see
[Two-node topology](#two-node-topology)):

- the storage-role base hosts the Debian storage guests — and the
  ubuntu probe and mint desktop templates build there too;
- the compute-role base hosts guests installed from the Proxmox VE ISO;
- two-node journeys drive one guest on each, linked by a point-to-point
  subnet.

## Safety model

The base Proxmox hosts are protected by construction, not by
convention:

- All base-host access flows through `tests/integrated/lib/base-lib.sh`:
  - only allow-listed `qm` lifecycle verbs may run;
  - VMIDs must be inside the reserved range from the site config, so
    production-style VMIDs can never be touched;
  - disk and ISO references must use the dedicated `itf` storages — the
    base system's own storages (`local`, `local-lvm`, …) cannot be
    written through this path;
  - absolute paths are only permitted inside the configured ISO
    directory;
  - every mutating call is appended to an audit log on the base host
    *before* it executes;
  - `pvesm` is read-only (`status`, plus `path` lookups that accept only
    itf-storage volumes — used by the VM-OS image dump on its own build
    guest's disk); general reads go through a small allow-list
    (`itf_read`).
- `ITF_DRY_RUN=1` prints guarded commands instead of executing them.
- Base-PVE configuration beyond guest lifecycle — storages, bridges,
  the audit log — is prepared by a human, following
  `tests/integrated/README.md` and the site-config comments.
  `itf preflight` verifies the result; `itf manual-steps` covers the
  remaining dev-side setup (the site config and the ISO fetch).
- Guests are disposable: any guest state may be destroyed or rolled
  back at any time.

## Site configuration

Everything environment-specific lives in `tests/integrated/site/config`
(gitignored), created from `site/config.example`. Loading
is fail-closed: a missing or invalid file aborts with a pointer at the
example. Validated parameters cover the base hosts, the SSH user, the
reserved VMID range, the itf storages, ISO sources, guest sizing, and
the software source (`release` or `dev-tarball`). Optional parameter groups
activate further machinery only when present:

- **Two-node parameters** (role bases, P2P addresses, compute template name,
  PVE ISO source) activate the compute-role machinery; the role bases
  must be members of `ITF_BASE_HOSTS`.
- **Ubuntu pair** (`ITF_UBUNTU_ISO_URL` + `ITF_UBUNTU_ISO_NAME`,
  both-or-neither, plus the `ITF_UBUNTU_TEMPLATE_NAME` override)
  activates the ubuntu probe template; it lives on the storage base
  like the Debian one.
- **Mint pair** (`ITF_MINT_ISO_URL` + `ITF_MINT_ISO_NAME`,
  both-or-neither, plus the `ITF_MINT_TEMPLATE_NAME` override)
  activates the mint desktop template; it lives on the storage base
  like the Debian one.
- **Keystore pair** (`ITF_KEYSTORE_PASSPHRASE` + `ITF_KEYFILE_NAME`,
  both-or-neither) feeds the LUKS key-device lab below. The passphrase
  is a secret and lives only in the gitignored site config.

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
                                    # (storage|compute|ubuntu|mint; default
                                    # storage — supported by j21 and j22)
tests/integrated/itf journey run j22-function-survey --template mint
                                    # the function survey on the mint
                                    # desktop baseline (two-node draw: the
                                    # storage guest is a bare Cinnamon
                                    # desktop; P2P wiring goes through
                                    # NetworkManager and the ZFSutilities
                                    # installs through install-two-node)
tests/integrated/itf watch            # tail the active run — NOT a console
tests/integrated/itf status           # guests + template + runs overview
```

`iso fetch` and `iso upload` take an optional selector — `debian` (the
default), `pve`, `ubuntu`, or `mint`. `template build` takes `--base` (the
target base host) and one of four profiles:

- **storage** (the default) — Debian + ZFSutilities.
- **compute** — Proxmox VE from the ISO (see below).
- **ubuntu** — Ubuntu Server LTS via autoinstall, a plain
  OpenZFS-version leg for the j21 probe matrix; no ZFSutilities install.
- **mint** — Linux Mint Cinnamon via ubiquity, the plain desktop-OS
  leg; no ZFSutilities install (see below).


Every run produces a progressive report under
`tests/integrated/results/run-<timestamp>-<tag>/` (gitignored):
`steps.tsv` for tooling, `report.md` for humans, plus artifacts such as
logs, `zfs list -t snapshot` listings, and GUI screenshots. Every
`report.md` line carries a UTC timestamp. Long activities — a guest
install, a serial watch, a poll loop — open with a `**START**` line
when they begin, so a run watched mid-flight shows what is running
right now. `itf journey run` exits non-zero when any step failed.

The driver itself runs under `set -euo pipefail`. Its own plumbing —
dispatch, preflight, status, watch — fails fast on any unhandled error.
The journey, template-build, and vmimage-build entry points are
deliberately looser. The driver invokes each through an `|| rc=$?`
wrapper, which suppresses errexit for its whole extent. That preserves
the failure-accumulation and always-finish-the-report contract
documented in `tests/integrated/journeys/README.md`: a failing step
records its fail, the run continues to cleanup and the final report,
and the driver exits non-zero from the captured rc. Journey stage code
therefore gates on explicit `|| return 1` rather than `set -e`;
anything the driver runs directly gets no such tolerance.

### Console discipline while a run is active

The install phase of every journey is driven over the guest's **serial
console** (`qm terminal`, `lib/serial_console.py`). The Proxmox web UI's
xterm.js console on an itf guest attaches to the *same* serial socket.
A second session interleaves keystrokes and splits output. Wait-patterns
miss; wrong bytes reach the installer; even briefly attaching can blind
the driver for the rest of the run. While a run is active (`itf status`
shows an active run with its pid):

- Never open an itf guest's xterm.js/serial console.
- Guest noVNC (VGA) is look-don't-touch: no typing, no power buttons —
  the journey owns the guest's power state.
- Leave the base-VM consoles alone entirely: the confinement guard
  constrains the orchestrator, not a human at a base console, who is
  root with no guardrails.

To follow a run, use `itf watch [TAG]`. It tails the active run's — or
a named run's — `steps.tsv`, `report.md`, and both serial transcripts
from the first byte, reading transcripts only and touching no console.
With no active run it parks on the newest run's final screen
(post-mortem mode). The output is a plain `tail -F` stream, not a
full-screen viewer: resizing the terminal garbles the wrap. Ctrl-C and
rerun `itf watch` to redraw.

## Journeys

A journey (`tests/integrated/journeys/<name>.journey`) drives one
end-user scenario — fresh install and daily workflows, uninstall and
reinstall, install over leftovers — using the itf helpers (`itf_step`,
`itf_guest_*`, guarded `itf_qm`/`itf_read`) and asserting on real
outcomes. The contract is documented in
`tests/integrated/journeys/README.md`.

OS installation inside the guest is automated with a Debian preseed
(or, for the ubuntu profile, an autoinstall seed — the same HTTP-serve
and serial-console machinery). The seed is served over HTTP from the
development machine and driven over the serial console (`qm terminal`,
`lib/serial_console.py`). The substrate under test is ZFSutilities'
installer experience, not the OS installer's. 

The mint profile is the
one exception on the seed channel: casper (the live-boot layer) only
fetches a network preseed in netboot mode, so the ubiquity preseed is
baked into a patched initrd instead — a cpio segment carrying
`preseed.cfg` is prepended to the casper initrd (prepended, never
appended: the pristine initrd ends with trailing bytes the kernel
cannot identify, and unpacking stops there), and the installer runs
GUI-automated on a real VGA device (`--vga std`) with the serial line
carrying kernel output and the final `reboot: Power down` as the
completion signal. 

Mint also never invokes the installer's post-install
hook on the automatic path, so the mint flow adds a **provision boot**
between the install poweroff and the first disk boot: the casper kernel
boots with no live medium, casper parks in its initramfs shell, and the
driver feeds the provisioning over the serial line (DHCP via
`configure_networking`, chroot apt install of the guest agent and
sshd, the dev ssh key, hostname, serial grub) — every step marker-gated on
the transcript.

Guests are disposable and their addresses are DHCP-recycled, so all
guest ssh/scp traffic uses `StrictHostKeyChecking=no` with a throwaway
known-hosts file. A fresh guest at a previously used address presents a
*different* host key, which `accept-new` rejects as a mismatch.

## GUI payload e2e matrix

The GUI does its work by building bash payloads (`python/offsite_runner.py`,
`python/command_builders.py`, `python/restore_runner.py`) and running
them through BackupRunner. The payload e2e matrix exercises exactly
that code — the real builders, the real runner, real ZFS pools —
instead of hand smoke tests. The scenarios live once in
`tests/python/e2e_support.py` and run in three contexts:

- **Dev container** (unprivileged, `--device /dev/zfs`): the pools are
  visible read-only (every dataset-mutating ioctl needs
  `CAP_SYS_ADMIN`), so the mechanics layer (real BackupRunner headless
  through a GLib main loop — pty stdin, the input-hold REQ/ACK
  protocol, rc propagation) and the dry-run payload scenarios run for
  real; mutating scenarios skip with a stated reason. Entry point:
  `share/dev/run-e2e-container`.
- **Dev host under sudo** The (`tests/python/test_offsite_e2e.py`,
  `tests/python/test_backup_payload_e2e.py`): the full matrix against the
  host's zfstest1/2/3 pools, run as root by the operator. Scenario scripts create
  and destroy only `test-e2e-*` datasets inside those pools and verify they
  leave nothing behind. Where sudo demands a password — the usual
  interactive posture — an unattended `tests/run-tests` cannot elevate:
  the preflight reports both root and the test pools are missing, every pool
  scenario script skips with that reason, and the runner mechanics still run.
  The container and the journey below then carry the rest of the matrix.
- **ITF guest** (journey `j11-payload-e2e`): a template clone with the
  j04 pool recipe and the current git working tree, running
  `tests/integrated/e2e/payload-e2e-driver.py` — the same matrix,
  executed as real root in a disposable guest.

Scenario levels are declared per scenario (`none` / `read` /
`mutation`) together with an engine mode:

- **GUI payloads** run under the input-hold protocol exactly as the GUI
  runner launches them — offsite, backup, prune, and restore payloads
  alike, including the Restore tab's property replay and
  receive-as-encrypted scenarios.
- **CLI scripts** (zfssend, zfsfullcopy, zfsrestore, the
  zfshold round trip) run as cron/terminal would: known
  prompt responses are pre-fed on the pty, and the watchdog catches any
  unexpected prompt.

## Backup property fidelity (j20)

The **j20-property-manifest** journey walks the property-manifest
sidecar end to end against real ZFS in one guest. The staging is a
clone start, the j04 pool recipe, and the current git working tree — the deployed
template version is irrelevant because the feature lives in the tree
under test. The scenario script runs in phases:

- **Capture** — a scripted backup captures per-dataset manifests with
  distinctive settings: local props, a user prop, an encrypted child's
  `keylocation`, and a zvol whose `volblocksize` must stay excluded.
- **Round trip** — a rename-and-restore round trip replays every
  setting and loads the ZFS encryption key.
- **WARN paths** — a capture-disabled generation exercises the
  exact-miss → newest-available fallback WARN; a never-captured backup
  gets the pre-property-manifest-feature WARN with inherited defaults.
- **Offsite leg** — the `zfssendoffsite` script takes the backup
  pool onward with `property_manifest='N'`, carrying the manifest as an
  ordinary dataset. A restore from the offsite copy replays through the
  traveled manifest — including the
  hidden-key WARN that leaves the dataset locked.
- **Consumption surfaces** — a hand-made export (`zfs send` to a file
  plus the store's manifest as its `.props` sibling) replays through
  `zfsrestoresendstream`, while a sibling-less file restores silently.
  A restore made with `replay_properties=N` gets every setting back
  through standalone `zfsreplayprops`.
- **Receive-as-encrypted** — the restore's initial receive accepts
  every plain dataset as encrypted wearing an encryption key: exactly one
  `-o encryption` receive, a snapshot catch-up that stays plain, and a
  raw-stream child that keeps its own encryption and stays locked under
  the skip-`keylocation` WARN. A non-`file://` keylocation is refused
  before any transfer.
- **Close** — the journey ends with the payload-e2e driver's
  offsite-onward and restore pairs, the mutation scenarios that the
  unprivileged container tier cannot run.

## Function survey (j22)

The **j22-function-survey** journey is not a
fixed scenario. At the start of every run it draws a random
sample of **at least half** of the end-user-visible function universe,
shuffles the order, archives the list, and executes the items in that
order with full logging. The archive makes a run exactly repeatable:
`ITF_SURVEY_ARCHIVE=<file>` replays the same list, order, and
prompt-response profiles, and `--rerun` reuses the previous run's
guests and (absent an envenvironment pin) its archived list.

The tested universe has two halves:

- **CLI** — every command documented on the commands pages, minus two
  recorded exclusion tables: the misc scripts declared customizable
  examples, and the lifecycle/dev scripts owned by the dedicated
  install/upgrade journeys.
- **GUI** — enumerated at run time from the git tree under test: the action
  buttons (`ACTION_HANDLERS`), the central-content-area widget interactions, 
  and curated composites that assert the
  linkage between central-content-area state and the action buttons.

Every item carries a fresh **response profile** which is applied to 
CLI answer feeds, modal dialogs, and input 
prompts. A run exercises different usage scenarios instead of a
constant safe default. The wrap-up reports the profile distribution as
evidence of the variation.

The software under test is the working tree (`ITF_SURVEY_SW=tree`, the
default) or any of the **five most recent published releases**
(`latest`, `prev:N`, `tag:<v>`, validated against the GitHub release
list at run start). The universe is enumerated from that exact tree,
and the same tree is staged into the guest — a survey of a different
release samples that release's real surface. GUI items run the real
window under a private in-guest Xvfb. CLI items run from the staged tree
under a pinned `ZFSCONFIG_PATH` against survey-owned state,
with per-command recipes whose depth (full flow vs
argument-validation surface) is disclosed per item.

The **world** — the guest state the items run against — is a named,
seeded variant (`ITF_SURVEY_WORLD`, default `lived-in`; `thin` is the
explicit cold-start choice for quick iteration). 

- `thin` is the
    cold-start world: survey-owned scratch datasets plus the pre-determined
    config, which keeps every feature's cold-start branch reachable.

- `lived-in` (the default) stages the aged world on top of the same playground: a
deterministic snapshot sequence. 

    ZFS snapshot `creation`
    cannot be backdated, so the snapshots are aged with a **clock walk** — the
    guest clock is frozen (NTP off, the iSCSI fence timer masked where one
    runs), walked back once, then forward through every planned moment,
    and finally restored from the dev host, the guests' time authority

    Each snapshot is named
    by the staged tree's own `zfssnapbuild` — bucket derivation included,
    asserted against the plan — with selective `offsite-*` holds, one
    clone-bucket snapshot plus its clone, and two real `zfsdailybackup`
    runs. The snapshots are over-retained against the ZFSutilities's
    default retention, and its budgets are enforced in-plan
    (≤ 40 snapshots including the two runs, ≤ 200 MB of payload).
    
    Staging
    verifies every planned snapshot's name and creation datetime against the plan
    before the run proceeds. The variant, its seed, the staging anchor, and a
    digest over the plan are archived: replay rebuilds the identical world
    (same absolute snapshot dates — buckets follow the calendar, so the
    anchor is part of the plan's identity). An explicit `ITF_SURVEY_WORLD`
    that conflicts with the archived variant is refused, and an archived 
    digest the current planner
    cannot reproduce is refused as planner drift. 

    `busy` (background load) stays reserved for a later phase, and the
    world staging step
    reports its elapsed time so the cost of richer worlds stays visible
    per run.

    After the clock walk, the lived-in world also seeds **config rows**, so the
    GUI pages and config-reading commands meet populated state instead of
    cold-start emptiness. The pinned payload
    config's `config_version` is read from the enumerated tree at stage
    time, and the stage fails closed if the
    tree's version cannot be read. The config seeding is deterministic in
    the run's scratch names and sits deliberately outside the world digest
    so archives recorded before the config
    rows existed stay replayable.

    The lived-in world finally stages the **site-adapted daily-backup
    pair** (below): the realistic site whose orchestrator the
    full-function leg runs.

The survey's depth axis grows with the world: `zfsresume` validates a
real resume token, `zfsdelallsnaps` runs its releaseholds
path against a held snapshot staged under its own label, and
the two-node vm-disk commands run full flows on the lab VM's scratch
disks. Every recipe creates its own prey and converges it afterward, so
random order cannot starve or poison a later item; the wrap-up reports
the run's depth distribution alongside its verdicts.

`zfscleanup` and `zfsdailybackup` get **both legs** — the override
test and the full-function test:

- The **override leg** runs in the item itself, exactly as before: a
  retention dry-run over the aged ladder, and a real send into the
  scratch receive tree with the site pulls and prune off.
- The **full-function leg** runs in a closing stage, after the GUI
  probe (structural, like staging and wrap — not part of the archived
  order), and only for the commands the draw selected. `zfscleanup`
  runs with **no overrides** — real retention deletion over the
  over-retained ladder, with the outcome checked against the world
  plan and the pinned config's retention rows: real deletions
  happened, held snapshots and the clone origin survive, every
  (dataset, bucket) is within its bound. `zfsdailybackup` runs the
  **site-adapted pair** the lived-in world stages — rendered from the
  staged tree's own `zfsdailybackup` and `rsync-dailybackup` templates,
  the documented customization path a real site follows: a local-pull
  site (in two-node labs the compute host's `/etc` joins the local
  pull over the P2P link via a `root@` job), the backup leg on the
  world's `backup-src` → receive tree, prune on. The run must show
  every leg — snapshot, pulls, send, prune, completion — with the
  prune confirmations pre-fed the way the product's own profile runner
  pre-feeds cron prompts; the post-state must carry the new
  snapshot on source and destination with the snapfile cleaned up.

Both full-function legs consume the world, and the world's lifecycle
is managed explicitly:

- After staging (+ the GUI env), the journey takes a stopped-guest qm
  snapshot **`world-staged`** — pools with creation times and holds,
  config, state dir, and the VM config of the full pre-item state.
- Each consuming leg **reverts** to that checkpoint afterward: newer
  stale snapshots are removed (the rerun branch's law), the guest is
  rolled back, restarted, its address re-resolved, and the world is
  re-verified against the plan — the same verification the staging
  ran.
- When the rollback or the verification fails, the world is **created
  again**: the deterministic planner rebuilds the identical ladder
  (same seed, anchor, digest), and a fresh checkpoint is taken (the
  stale one is dropped first — its disk state is the consumed world).
- Thin runs have no aged ladder and no site pair; the closing stage
  records a disclosed skip per drawn command.

Defects found in a past release are recorded in `FINDINGS.md` and fixed
**forward** in the dev tree — there is no back-porting; the release
tarball stays a read-only input. The repair verification is the replay:
the same archived list re-run against the fixed tree.

## Post-install baseline templates

Journeys whose scenario begins *after* installation start from a
**baseline template**: a guest built once through the real first-time
user path and converted to a Proxmox template (`itf template
build`). `itf_journey_stage_from_template` clones it so
the journey reaches the post-install point in a minute or two instead
of repeating the ~15–20-minute install.

Four baseline templates are available:

- **storage** (the default) — a Debian + ZFSutilities baseline.
- **compute** — a Proxmox VE host built from a PVE ISO by
  its auto-installer, no ZFSutilities: the installer's deploy push to the
  compute host is part of what the two-node journeys exercise.
- **ubuntu** — an Ubuntu Server LTS guest built from a
  Ubuntu ISO by autoinstall, carrying the ZFS userland but no ZFSutilities.
  It exists as a plain OpenZFS-version leg for the j21 journey).
- **mint** — a Linux Mint Cinnamon desktop guest built from a
  Mint ISO by a ubiquity preseed plus a serial-driven
  provision boot. It is the plain desktop-OS leg for
  journeys that exercise the GUI, which install the ZFSutilities through
  the first-time-user path; its clones carry a virtual VGA device
  for a real Cinnamon session.

Journeys that support profile selection take it at run time
(`itf journey run j21-zfs-probes --template ubuntu`; the j22 function
survey takes `storage` or `mint`, the desktop leg:
the storage-side guest comes from the mint template, installs
ZFSutilities through the first-time-user path — `install-two-node` when the
draw includes two-node items — and the two-node lab's P2P wiring goes
through Mint's NetworkManager instead of ifupdown).

- **Linked clones, by design.** The itf guest storage is LVM-thin,
  which supports Proxmox linked clones: each guest clones from the
  template's base volume as an LVM thin snapshot. `ITF_CLONE_MODE=full` 
  in the site config produces
  full copies for guest storages without linked-clone support.
- **Template rebuilds are from scratch, never in-place upgrades.** The baseline
  must keep first-time-user fidelity. `itf template build` skips when the
  existing template already reflects the current release (or repo rev,
  for dev tarballs); `--force` overrides and rebuilds. A rebuild costs
  one unattended install (if errorless) and doubles as a smoke run if fixes
  are needed. 
- **OS currency is a build-time property.** The build applies all
  pending package updates *after* the ZFSutilities install and reboots onto
  a new kernel when one arrives, depending on: newest kernel running, ZFS
  module loadable, ZFSutilities wiring intact. Every clone inherits a
  current, proven-bootable OS — this also proves an installed system
  survives a routine `apt full-upgrade`.
- **The stamp rides in the PVE description field** (`qm set --description`, 
  read via `qm config`): software source, ZFSutilities
  version, repo rev, kernel, and build-time travel with the template. 
  `itf template status` and
  `itf preflight` surface it.
- **The templates are protected by the guard.** Mutating qm verbs
  against the VMID carrying a template's name are refused — all 
  template names are covered (cloning is exempt). 
  `itf template build`/`destroy` are the sanctioned
  management paths and are audit-logged like every other mutation.
- **The template's *ZFSutilities* version is allowed to go stale — j10
  depends on it.** A clone of a stale template is a genuinely installed
  system running an older release, the exact starting state the
  release-upgrade journey needs. **j10-release-upgrade** walks the real
  user upgrade path on such a clone.

**j12-interrupted-upgrade** shares that staging and adds the
failure injection that interrups the upgrade. The recovery is simply 
re-running the same `upgrade-zfsutilities`.
It detects and salvages the previous modifications.

**j19-baseline-capture** exercises the trust-on-first-upgrade
capture path. j19 runs the staging
with `ITF_UPGRADE_BASELINE=none`: no tag tarball, no override, so
the first upgrade on the untagged old tree cannot obtain any
baseline and must capture one from the active tree itself.

- Modifications made before that upgrade are absorbed into the
captured manifest — indistinguishable from pristine content: not
flagged, nothing salvageable.
- The manifest is added to the still-active old tree, which
every later upgrade then scans against.
- New changes are detected against the
captured baseline, and diffing
degrades honestly (no pristine source exists for an untagged
version).

**j23-two-node-release-upgrade** covers the remote half none of the
above touches: the upgrade driven from a storage host whose
`deploy.conf` groups name a compute host. The journey composes the
j05 lab, then stages the never-upgraded site — the stale template's
old tree is pushed to the compute host and `switch-version`'d on
both hosts, so every deployment target runs old-active.

- A defective download must change nothing on either target —
  the deployed `MANIFEST.sha256` timestamps recorded beforehand
  prove no re-deploy.
- Pass 1 walks trust-on-first-upgrade with no pristine source:
  * baseline manifests are captured on the local tree *and* over ssh
    on the compute host
  * the new version deploys to every target
    without activation
  * both switch-version commands are then run
    unmodified.
- Pass 2 re-labels the served release one patch newer and injects
  per-host modifications. The scan must list each host under its own
  section, pull the compute host's changed files back to
  render unified diffs, and archive salvage copies carrying local
  content on each host.
- The journey finishes with per-host activation, version retention,
  and the up-to-date rerun.

It runs under `ITF_SW_SOURCE=dev-tarball` only: both passes point at
an itf-served "latest release", and pass 2 rewrites it — impossible
against real GitHub. Its pass-2 re-label and per-host modification
staging live as shared stages in `common.sh`
(`itf_journey_stage_upgrade_relabel`,
`itf_journey_stage_two_node_mods`) — j25 composes them for its own
premise.

**j25-two-node-interrupted-upgrade-keys** closes the installer coverage
map's last loose end: j12's injections against the encrypted two-node lab
with keys *pending*. The lab is installed from the tree under test,
so a stale-template rollback would boot a keys-absent site with
pre-encrypted-LUN tooling. Instead, the staging runs in relabel mode
(`itf_journey_stage_upgrade_env --relabel`) and serves the same tree
one patch newer.

- The healthy baseline is proven first. Checks include: 
  * markers written through the LUNs
  * keystatus = available
  * `--check` green
  * sha256 baselines over the saveconfig files
  * the pool-resident state map
  
- The Storage node reboots with the ZFS keys absent. 
  * The boot journal must read PENDING.
  * The session logs in unaided.
  * The plain LUN keeps serving its marker
  * The encrypted link is classified (a stale device node).
  
- Three injections fire:
  * SIGTERM at the scan marker must run the EXIT trap — staging
    gone AND both SSH control masters closed — with nothing
    deployed, salvaged, or activated on either host;
  * SIGKILL at the local version-dir mkdir leaves the partial dir
    without `MANIFEST.sha256` on storage beside salvage archives on
    BOTH hosts (remote salvage precedes deploy);
  * SIGKILL aimed at the remote sync (local MANIFEST present,
    compute dir appearing) leaves storage complete and the compute
    dir classified absent, partial, or complete (the sync finished
    before the kill).

- The recovery re-run, still ZFS keys-pending, must do the full per-host
  scan/salvage/diff prodecure, repair both version dirs in place, and stop
  before activation.

  * Per-stage oracles hold throughout: `--check` exits 3 with every
    drift line keys-pending, the survival hashes stay byte-identical,
    and the plain-LUN marker still reads.
  * Activating both hosts
    must leave that posture untouched — importantly: nothing in the
    upgrade path may write iSCSI state while keys are pending.
    + Activation restarts the timeout timer and its tick fires at once, so
      the journey parks the timer again and waits for another tick allow
      things to settle
    + in the absent-link state, that tick's
      saveconfig re-save is tolerated.
    + One manual tick then runs the upgraded test under keys
      pending, and the up-to-date rerun is a no-op.
    + The closing key ceremony rebuilds the encrypted LUN on the
      upgraded tree and
      both markers read back byte-exact before the `--check` test, a
      healthy tick, and a clean `safe-iscsi-save` close the run.

Like j23, j25 is dev-tarball only.

## Fast fix verification: `journey run --rerun`

Fix-verify loops are the daily routine of the repair workflow, and the
staging step is also the most redundant one on a
verify: the previous run's guests are still there, each carrying its
staging checkpoint (`as-cloned`, or `os-installed` on install-start
journeys like j01/j08/j09). `itf journey run <name> --rerun` reuses
those:

- The driver finds the red run,
  writes the new run's `rerun-guests.tsv` from its guest records, and
  logs the choice in a `rerun source` INFO step.
- Each staging stage (`itf_journey_stage_from_template`,
  `itf_journey_stage_os`):
  * finds its guest in the spec
  * verifies it still exists and carries its checkpoint
  * rolls it back (`qm rollback`)
  * starts it
  * and re-discovers its IP
 
Everything after replays in full;
a rolled-back install-start guest is a clean Debian with the
prerequisites genuinely missing, so failure-path journeys keep their
coverage.

- Only the staging step is skipped. The ZFSutilities download and install
  stages re-run deliberately: they install the tree under test, which is
  the point of the re-verify. (Deeper checkpoints such as
  `pools-created` are intentionally NOT rerun sources — replaying from
  one would leave the lab pre-installed and route the installer into
  its upgrade branch, silently weakening coverage.)
- Refusals are explicit, never a silent fallback: no prior run, an
  active source run, destroyed guests, or a missing checkpoint each
  fail fast with the remedy (run fresh, no `--rerun`).
- Snapshots newer than the checkpoint survive a `qm rollback` on this
  stack but go stale, and the replay re-snapshots the same names — so
  the rerun branch removes them explicitly before rolling back. The
  rollback reverts VM config (hot-plugged NICs, the pool disk), which
  the journey re-attaches — a rerun is indistinguishable from a fresh
  run in coverage.
- When the loop is done, nothing to remember: a green verdict destroys
  the run's own guests at verdict time — pass `--keep` on the runs you
  expect to iterate past, and settle anything deliberately kept with
  `itf guest sweep --apply`.

## One run at a time: the run lock

Itf serializes itself. `itf journey run`, `itf template build`, and
`itf vmimage build` take a machine-wide advisory kernel lock
(`lib/runlock-lib.sh`, flock on `/tmp/itf-active-run.lock`) before
doing anything else. The reason is physical, and any parallel repo
lanes share all of it while each lane's
`itf status` can only see its own tree's runs:

- every run binds the site-configured HTTP port on the dev host;
- every run arms the shared UDP-514 installer-syslog listener on a base
  host VM;
- every run consumes base-host RAM/storage that fits only one two-node lab.

A second starter therefore waits (heartbeat every 30 s, up to
`ITF_RUNLOCK_WAIT` seconds, default 7200; `ITF_RUNLOCK_WAIT=0` refuses
immediately). Output streams and `itf status` 
name the active holder — journey, pid, start time, and which repo tree
holds the lock. The lock is held on an open file descriptor by the
run's own process, so any death (kill, crash, lost session) releases it
instantly: there is no stale-lock state and no cleanup command. This
lock is deliberately not ZFSutilities's dataset lock manager — that one
keys by ZFS dataset for root-run ZFSutilities operations, while this one
keys by dev host and must work for the unprivileged orchestrator.

The flock blocks dev-side processes only; the run's guests live on the
base host VMs and do not die if the dev host dies. After a mid-run dev
restart the lock is correctly free while the interrupted run's guests
keep running on the base VMs. So every run re-verifies while holding the
lock (`itf_runlock_orphan_fence`): guests recorded by interrupted runs
of this tree that still exist in their base's `qm list` refuse the new
start, naming each leftover and its two recoveries (reuse with
`itf journey run <same> --rerun`, discard with `itf guest destroy`).
The base host is the authority — that is what makes the check correct
across dev restarts.

Ownership is decided by NAME, not just VMID: every guest is named for
its run (`itf_guest_qname` — the journey's guest name plus the run
timestamp, recorded as the 4th field of each `guest*.txt`).

- A live VMID whose qm name differs from the recorded one is another
  run's guest (the VMID was legitimately recycled after this run's
  guest was destroyed) — the stale claim is noted and ignored, and no
  destroy or rerun is ever offered against that guest.
- Records older than the name field keep the fail-closed VMID-only
  match.
- A rerun exempts exactly the guests it takes over.
- A results directory with no interrupted runs costs no base query at
  all.
- An unreachable base fails closed (unverified is not clean).
- Guests of finished runs are exempt by design — they are the kept lab
  of the run → fix → `--rerun` loop, and only an interrupted run means
  the operator lost track of guests that are still consuming resources.

## Guest lifecycle: verdict-time teardown and the sweep

The disposition of the test VMs is automatic:

- **Green verdict, no `--keep`** — the run's own guests are destroyed
  and their `guest*.txt` records deleted. The audit trail is the INFO
  steps this records; the invariant it preserves is that a run dir with
  guest records is a lab that may still exist, which is exactly what
  rerun sourcing and the orphan fence rely on (after a teardown, the
  next `--rerun` refuses with the run-fresh remedy).
- **`--keep` / `ITF_KEEP_GUESTS=1`** — the lab is retained for the
  `--rerun` loop; pass it on runs you expect to iterate past.
- **Red verdict** — the lab is always kept: post-mortem reading and the
  fix-then-rerun loop need it. 
  
**`--keep` and red** labs must be explicitely destroyed
when they are no longer of use to the original lab runner.

Ownership follows the NAME law (`itf_guest_records_resolve`):
- One `qm list` per involved base is the authority
- a guest is destroyed only when the live VMID still carries the record's 
  run-tagged name. 
  * A different live name (a legitimately recycled VMID)
  * a vacated VMID
  * a legacy nameless record
  * an unreachable base 
  are each fail-closed. Nothing is destroyed on guesswork. Records are kept 
  or stale-removed exactly as the name law treats stale claims. Templates 
  are structurally safe: destroy fires only on a name match, and a 
  successful template build renames its VM away from the run-tagged record 
  name before the run finishes.

`itf guest sweep [--apply] [--force] [--age HOURS]` settles the
remainder — `--keep` labs whose loop ended, and red labs after triage:

- it walks this git tree's run records only (each lane sweeps its own);
- it takes the machine-global run lock, so it can never race a live
  journey in any lane;
- it selects completed green runs past the age gate
  (`ITF_SWEEP_AGE_HOURS`, default 24 h; red runs only with `--force`)
  and resolves records with the same name law;
- it is plan-only until `--apply` is passed — the printed plan is the exact
  destroy list.

## Two-node topology

Many of the journeys model the production two-node layout (storage node
+ compute/Proxmox node) on the base VMs:

- **Role split across base hosts.** `ITF_STORAGE_BASE` hosts the
  storage-role guest (Debian + ZFSutilities, cloned from the storage
  template) — and the ubuntu server and mint desktop templates build on that base too.
  `ITF_COMPUTE_BASE` hosts the compute-role guest cloned from the
  **compute template**. Both role bases must be members of
  `ITF_BASE_HOSTS`, and template protection covers all
  four template names.
  
- **The compute template is PVE installed from a Proxmox VE ISO** —
  not a Debian guest with PVE layered on top. `itf template build --profile compute`
  customizes the cached PVE ISO the way the Debian path customizes its
  netinst: 
  * embedded answer file:
    + auto-install mode
    + DHCP networking
    + ext4 on the first disk
    + root SSH keys, 
  * serial-console kernel append so the install is watchable and gateable
  * first-boot hook that swaps the enterprise repositories for the no-subscription
    ones and installs the guest agent. 
  
  Two more details are handled
  by the compute template rebuild: the relative symlinks 7z refuses to extract are
  restored from its refusal log, and grub's El Torito boot image gets
  its embedded absolute-sector reference re-pointed at the rebuilt
  layout (without that, the guest hangs silently right after
  "Booting from DVD/CD..."). The compute template carries PVE only —
  the installer's deploy push to the compute host is part of what the
  journeys exercise.
  
- **The cross-node link rides the shared bridge.** Each guest gets:
  * a second NIC (`--net1`), static addresses from the site-configured P2P
    pair (a dedicated subnet modeling production's storage↔compute link
    without touching any base network config)
  * `/etc/hosts` entries both
    ways
  * exchanged root SSH keys
  
- **j05-two-node-install** runs the full scenario: 
  * clone both guests
  * stand up the P2P link
  * create the documented test pools on the storage
    node
  * run `check-prerequisites --two-node` there 
  * feed `install-two-node` its interactive answers
  * verify the deployed wiring on both nodes
  * close the loop with a first-LUN round trip -- 
    a VM created and disk provisioned on the
    compute host must arrive over iSCSI and be saved back on the storage
    side.
    
- **Same-IP staging collisions converge once.** The compute template's
  management address is a STATIC address baked in at build time. While
  the compute node is still booting, the LAN DHCP server can lease that
  address to the storage node (whose duplicate-address detection is
  blind while the address's owner is down), leaving both role nodes
  on one address. j05's hostname gate detects the collision and
  converges through one bounded storage-side re-lease: 
  * the fix runs through the guest agent (ssh to the collided address
    does not necessarily reach the correct host
  * the re-acquired address must differ
    from the collided one
  * the guest record is rewritten before the
    duplicate address detection re-runs
  * a DHCP re-lease that does not produce a different address
    fails the journey — no silent fallback.
    
- **j06-guest-probe-validator** composes the j05 lab and then runs
  `share/dev/validate-guestfs-probe.sh` live on the storage guest:
  * a positive pass must show a populated sample
      (pools, datasets, PVE configs fetched from the compute guest, iSCSI
      targets) 
    with the stopped VM's disk probed and a recorded reason
  * a negative control 
      (compute host made unresolvable on the storage guest) 
    must make the validator exit non-zero with the ssh failure reason 
    printed
    
- **j24-two-node-uninstall-reinstall** composes the same lab and walks
  j02's cycle with two-nodes.

  * Interactive `--dry-run`s on *each* host are the uninstall-intent
    report: 
    + the menu
    + peer question and confirm walk through
    + the purge actions echo as `[DRY-RUN]`
    + the iSCSI targets are promised untouched
    + and the compute leg prints the PVE-patch never-reversed
      note (the patch file only exists there) with zero mutation

  * The real `--purge --all-nodes --yes` pushes the peer leg over ssh,
    and the journey then asserts both halves of the contract at once:
    + every ZFSutilities wire is gone on both hosts 
    + while the *site* survives byte-for-byte
      
  * The reinstall runs from the repository checkout which the uninstaller 
    never touches, over the live LIO tree. 

## Recovery-scenario lab layer

The recovery-scenario journeys build on shared lab machinery in
`journeys/common.sh` rather than per-journey copies:

- **`itf_journey_stage_test_pools`** is the three-RAIDZ1
  recipe as one stage. j01, j05, and j21 call it directly, and
  the single-node lab builder calls it as its pools step.
  
- **`itf_single_node_lab_main`** is the shared single-node prefix
  behind j04 and j11.
  
- **`itf_journey_stage_reboot_guest`** reboots a staged guest,
  waits for ssh, re-discovers a re-leased DHCP address, and
  rewrites the itf guest record.
  Its split halves, `itf_reboot_guest_begin` / `itf_reboot_guest_wait`,
  exist for journeys that observe peer-node fallout INSIDE the outage
  window (j15's S1b watches the compute node between the two).
  
- **`itf_journey_stage_encrypted_key_lun`** 
    (opt-in via `j05_two_node_lab_main --encrypted-keys`
    default off so composing journeys are unaffected) 
  models production's removable LUKS key
  store: 
  * a small scsi2 disk is LUKS-formatted on the storage guest
  * carries an ext4 `ZFSkeys` filesystem with the per-pool key at the
    conventional path plus the production `noauto` fstab line
  * `new-vm-disk --encrypted` then creates the encrypted vm-101-disk-1
    through ZFSutilities 
      (its key-path prompt is answered over the piped feed; the passphrase 
      itself reaches `cryptsetup` via stdin, never in argv). 
    + Insert/remove helpers re-attach and detach the captured key-device volume
    + the unlock/mount helper drives the operator's blind-recovery step.
    The stage ends in the production posture: 
    + key store locked and detached
    + ZFS keystatus `available`. 
    
- **The VM-OS image** (`itf vmimage build`, built once and cached like
  the ISOs) is a minimal preseed Debian whose disk dump is written
  onto ZFSutilities-created zvols so a workload VM
  boots from its iSCSI LUN. The preseed installs the qemu guest agent,
  and the build self-verifies the exact property that scenarios depend on.
  The dumped image is restored onto a blank disk, booted, and must
  answer `qm agent <vmid> ping` before anything is cached.

- **Workload helpers** drive that VM from the compute guest through the
  qemu guest agent:
  * a boot gate
  * a 1 Hz timestamp writer with per-tick sync on the LUN-backed root filesystem
  * sample/checksum retrieval
  * and a stall-gap parser over saved samples.
  
- **The j15 boot-and-keys machinery** layers the recovery observables on top: 
  * `itf_journey_stage_boot_workload_lab` stages the scenario lab
      (VM 101 on a plain OS LUN as the everyday workload VM, VM 202 on an
      encrypted OS LUN, writers running, fence timer premise asserted,
      pre-reboot `safe-iscsi-save` + `export-iscsi-state --check` gates)
  * `itf_key_ceremony` runs the operator's key ceremony
      (insert → luksOpen/mount → `zfs load-key -a` → recover or add →
      lock/detach) 
    as one stage
  * `itf_storage_boot_state` captures the boot journal and cross-unit 
    import ordering while `itf_boot_journal_verdict`:
    + asserts the verdict, the echo order, and per-LUN DRIFT/Added naming
  * `itf_compute_fallout_sample`, `itf_fence_tick`, and the by-path 
    link-presence pollers record what the compute node saw through each event.

  The **j15-iscsi-boot-keys** journey runs the boot-and-keys scenario
  catalog against that lab:

  * **S1** — reboot with the key device absent: 
    * the PENDING + DRIFT journal oracle (the encrypted-aware verdict)
    * the encrypted-root VM is unusable — either a start abort or a start 
      that "succeeds" against a stale device node and then never boots
    * blind recovery via `iscsi-recover-encrypted-luns`
    
  * **S1c** — the second reboot repeats the same PENDING shape (the
    recovery-then-reboot cycle is stable), and convergence is proven
    WITHIN the boot by a manual `--check` reporting no drift.
    
  * **S1b** — a storage node power event with both workload VMs running: 
    * the sessions CLING to the dead storage 
        (PVE patches the iSCSI replacement timeout to 24 h, so by-path links 
        stay present — the only outage signal — and a tick inside the outage 
        honestly reports healthy recorded as a design datum) 
    * After return, the iSCSI links re-login automatically but BOTH running 
      VMs keep stalled writers until a stop/start, classified from writer samples.
      
  * **S2** — the zfs-keys.md `iscsi-add-encrypted-luns` path.
  
  * **S3** — `restart-iscsi-services`: 
    * the designed refusal with VMs running
    * then the one-command path with compute fallout.
    
  * **S4/M4/M1** — wrong passphrase, pool A's key against pool B,
    mistyped key-file paths at `new-vm-disk --encrypted`.
    
  * **S5a/S5b** — a `file://` keylocation on the unencrypted root
    filesystem still journals PENDING at boot.

  The boot-verdict oracle follows the documented semantics
  (`two-node-config.md`): every keys-absent boot journals `post-restore
  verification PENDING` (the encrypted-aware verdict, distinct from
  FAILED's unexpected drift) with DRIFT detail until the key ceremony
  completes.

- **Scenario windows park the compute fence timer.** Operator-paced
  recovery arcs (j16's loss scenarios, j18's key ceremony) assume
  nothing heals before the operator surface under test shows its
  evidence — but the always-on 5-minute timeout tick can land inside the
  window and its ssh iSCSI reconcile heals the tree first. 
  Those journeys `systemctl stop zfsutilities-iscsi-fence.timer` for 
  their mutation-sensitive stretch and restart it before their final tick
  The unattended heal itself is j14/j18 coverage.

- The **j16-iscsi-total-loss** journey runs the iSCSI-loss scenario catalog
  on the same lab (keys stay loaded throughout — the storage node is
  never rebooted):

- **S6** — destroys every live mapping+backstore while the OS-disk
  files still record them: 
  * the VM-refs detector signature
  * `--check` drifting on every LUN
  * and a `reconcile-iscsi-state` rebuild of all LUNs from the pool map — 
    the encrypted ones included — with running-VM fallout sampled through 
    the outage.
    
- **S9** — one hand-deleted mapping: 
  * `safe-iscsi-save`'s mapping-loss FATALs
  * the verifier names the LUN
  * PVE aborts VM start on the vanished link after the session cycle
  * and `repair-iscsi-luns` re-maps at the recorded index.
  
- **S7a/S7b** — pair a targets-intact wipe with a targets-too wipe. In
  the first, `iscsi-restore-luns` performs the full
  saveconfig-authority restore including ACL grants and a staged
  non-identity `mapped_lun 8 → tpg_lun 0` ACL grant. In the second, the
  restore attempt honestly refuses without iSCSI targets, and the recovery
  runs through `setup-iscsi-targets` plus the map-driven reconcile
    (the map's grants dimension is the surviving authority: setup's own
    save overwrites the saveconfig records exactly when they are needed,
    but the map records each initiator's grant pairs, so the reconcile
    recreates the staged non-identity grant exactly).
    
- **S8/S8b** — S8 corrupts `saveconfig.json`: 
  * the systemd unit restart restores from `saveconfig-boot.json` unaffected
  * the pre-start backup preserves the corrupt bytes as evidence
  * `safe-iscsi-save` FATALs on the unparseable data
  * and the FATAL's own force escape `targetcli saveconfig` heals the 
    file from the intact live backup 
  * S8b proves the boot-config-absent fallback branch fails loudly.

- **S18** — exercises the pool-identity test live: 
  * an exported expected pool WARNs on `check-prerequisites --two-node`
    and in `setup-iscsi-targets`' own block, while `export-iscsi-state --check` 
    stays silent on the one-sided name (for offline-pool tolerance)
  * a destroyed+recreated pool emits the `pools.<name>: GUID changed` 
    DRIFT line, converging only through the operator-confirmed `safe-iscsi-save` 
    whose map refresh records the new GUID.

- The **j17-iscsi-interrupted-ops** journey runs the interrupted &
  contradictory-operations catalog on the same lab (keys stay loaded; the
  workload VMs stay parked; service restarts only, never a storage
  reboot):

  * **M5** — proves the luksOpen retry arc: three mistyped passphrases
    rejected cleanly with no mapper leak, the fourth accepted.
    
  * **S13** — proves `new-vm-disk`'s collision guards, both clean (a
    second run for the same disk FATALs before any mutation) and against
    the script's own half state 
      (a SIGINT after the zvol create leaves a zvol without a LUN that 
      the next run refuses to touch. `remove-vm-disk` WARN-skips the gone 
      pieces and repairs the LUN).
      
  * **M2** — proves iSCSI reconcile's apply prompt defaults SAFE: "yes", 
    "yup", and bare Enter all abort with rc 1 and the state is frozen; only
    the explicit Y succeeds.
    
  * **M3** — proves `remove-vm-disk`'s identifier validation: 
    + wrong VMID, wrong disk number, and unknown pool all FATAL before any 
      mutation
    + "yes" at the destroy confirmations.
    
  * **S11** — interrupts `remove-vm-disk` between its teardown steps: 
    + the half state (zvol and manifest intact, LUN gone) drifts in 
      `--check`
    + `safe-iscsi-save` refuses the degraded save
    + and the re-run converges the VM disk state end to end.
    
  * **S10** — interrupts `reconcile-iscsi-state` mid-apply: 
    + the partial state keeps the pool map as an untouched recovery authority
    + the re-run rebuilds the remainder
    + and a third run finds nothing to do.
    
  * **S14** — attempts the `zfs destroy` of an exported zvol under a
    live LUN, and the zvol layer refuses it while LIO holds the device
    ("dataset is busy"). 
    The journey records the refusal and skips the sweep.
    
  * **S12** — runs reconcile and `iscsi-restore-luns` concurrently over
    the same wiped records, proving the global `iscsi-lio` fence live: 
    The second mutator is refused before it can
    mutate, its WARN naming the running sibling by pid and command, and
    the sequential re-run converges the records.

- The **j18-compute-power-events** journey runs the compute & power-event
  catalog on the same lab (keys stay loaded through S15; S16's storage
  power cycle unloads them and closes through the j15 recovery arc):

  * **S15** — proves a compute-node reboot the everyday way, in two legs.
    The default posture returns the iSCSI sessions, the by-path links,
    and a green fence tick unaided while both VMs stay stopped (nothing
    restarts them without onboot). 
    
    The operator's `qm start` restarts the VMs, and the writer data survives
    + the log grows past the baseline
    + the pre-event prefix checksum is unchanged
    + and the outage appears as one gap. 
    
    `--onboot 1` asserts PVE's boot-time autostart.
    
  * **S16** — power-cycles both nodes with the storage node slow to return. 
    The compute node boots into a storage-less world 
      (zero sessions ever established, so nothing clings and nothing 
      rescan-able exists),
    and the timeout tick fires against the unreachable storage host 
      (per-ref WARNs, rescan problems, the ssh-255 WARN, the still-missing 
      FATAL, never the reported-problems WARN). 
    Storage's late return journals the PENDING+DRIFT boot oracle for the 
    encrypted LUNs, and the post-return truth is measured live: 
      + the sessions and the plain LUNs return unaided, while the return 
        tick stays red exactly for the keys-pending encrypted LUN 
          (reconcile skips it with the `keys not loaded?` hint and 
          preserves the pool map as the recovery authority)
      + that same return tick's trailing save drops the encrypted
        records from saveconfig.json, and the `iscsi-recover-encrypted-luns` 
        restores both LUNs directly through the pool-map fallback 
        (the map's recorded indexes), with the keys-loaded tick proving 
        convergence and recover's re-run healing the ACL grants. Both VMs 
        then boot with intact writers and `--check` reads rc 0.
    
  * **S17** — leaves an orphan live-exported LUN behind in both shapes
    (a VM deleted in PVE and a hand-removed scsi line) and proves every
    checking surface blind to it by design. `remove-vm`'s
    classifier is the one surface that names and spares the LUN, and both
    documented teardown paths converge (`remove-vm --cleanup-orphans`
    through the iSCSI-aware `zfsdelfs`; `remove-vm-disk` after the
    hand-removal its prompts ask about).

## Findings and repair loop

Failures observed through the orchestrator become entries in
`tests/integrated/FINDINGS.md`. The loop that turns a finding into a
shipped fix runs one step at a time:

1. **Observe.** A journey fails through the end-user surface. The run
   goes red, and the lab is kept for post-mortem reading.
2. **File.** The agent adds a `FINDINGS.md` row: the next F-number, the
   date, the journey, the symptom quoting its run directory (the raw
   evidence), the suspected area, status `open`. Product gaps only —
   harness bugs are fixed directly in `tests/integrated/` and never
   become rows.
3. **Draft.** The agent writes a numbered repair plan
   (`tests/integrated/repair-plans/NNN-slug.md`, next free number, never
   reused) proposing a change **in this repository**. A plan records the
   finding, the root cause reproduced on the dev tree, the proposed
   change, the blast radius, and the verification — which journeys rerun
   and what they must show.
4. **Approve.** The hard gate: repairs are executed only after explicit
   user approval. A standing approval for a repair campaign is recorded
   in the finding's status cell.
5. **Execute.** The change lands in the dev repository through the
   normal development workflow. ZFSutilities bugs are never fixed inside
   an ITF guest — guests are disposable.
6. **Verify.** The fix ships to the ITF guest as a dev tarball (fresh
   run or `--rerun`), the affected journeys rerun, and a green verdict
   closes the plan. In-cycle fixes take the same path.

The row's status tracks the loop:
`open` → `planned` (plan approved) → `fixed` (change landed) →
`verified` (rerun green).

Every finding ends in exactly one terminal state:
- `verified` (the fix landed and the rerun was green — in-cycle fixes included)
- `accepted` (the user waives)
- `documented` (entries move to repo docs)
- `superseded` (folded into another entry). 

UX and future-direction entries seed the [requirements register](#requirements-register).

No entry stays open past a campaign wrap. Published entries and executed plans are pruned at each release; `git log` recovers them, which is where the historical F-numbers and
plan numbers live.

## Requirements register

UX gaps and design directions that the journeys prove — but that are
not defects to fix now — are added to `tests/integrated/REQUIREMENTS.md`
as numbered entries (R-nn) with their source scenario and a status. The
seeding process:

1. **Sources.** A journey outcome that proves a UX gap or design
   direction live; a FINDINGS triage decision (a finding resolved as
   "not a defect to fix now"); or direct user direction. New rows come
   only from these — no speculative requirements.
2. **Seed.** The agent adds one row: date, source (the journey scenario
   or FINDINGS row that proved it — raw evidence lives in the run
   directory that finding records), the requirement, status `open`.
   Product-truth rows are additionally documented in the user-facing
   pages the row names.
3. **Maintain.** A row never silently disappears: promotion,
   addressing, or declining is recorded in the status cell with a date.
   An entry moves `open` → `promoted` (repair-plan NNN, owner-approved)
   → `addressed (version)`, or is `declined` (date and reason).
4. **Campaign wraps feed it.** The wrap-time triage closes every
   finding in exactly one terminal state; the UX and future-direction
   outcomes land here.

The register is the durable input for future coding; promotion from an
item to a plan is the owner's call, never automatic. Journey coverage
by node mode is tracked in the [ITF Coverage Map](itf-coverage.md);
items there are candidates only, built when the user names them.

## Testing the ITF framework itself

The itf libraries have their own mock-based suites in the default
`tests/run-tests` set:

```bash
tests/run-tests test-itf-config test-itf-base-guard test-itf-report \
    test-itf-ssh test-itf-template test-itf-driver test-itf-lab-stages \
    test-itf-survey-journey test-itf-watch
```

They cover:

- fail-closed site-config loading and example-file validity;
- the confinement guard's refusals (VMID range, non-itf storages,
  non-allow-listed verbs, path confinement, baseline-template
  protection for all four template names);
- dry-run behavior and audit ordering;
- the run-report writer;
- the dev-host HTTP serve/fetch/stop round trip used to deliver
  preseeds and dev tarballs to guests;
- the template stamp/resolution/clone/freshness logic for all four
  profiles;
- the driver's dispatch/usage surface (journey listing, ISO selector,
  profile flags);
- the lab-layer stages themselves (`test-itf-lab-stages`): the test
  pools stage, the single-node lab, the VM-OS build/dump/self-verify
  orchestration, the workload helpers and stall-gap parser, the reboot
  stage with address rediscovery, the keystore helpers — including that
  the LUKS passphrase never appears in any command and that the
  encrypted lab tail stays off unless the flag is passed — and the
  boot-and-keys machinery: the reboot begin/wait split, the boot-journal
  parser against fixtures, the key ceremony, the load-keys/keystatus
  gates, the link-presence/fence-tick/fallout observables, and the
  boot-workload staging orchestration;
- the survey journey mechanics (`test-itf-survey-journey`): selection,
  archiving, replay, `--rerun` list reuse, the CLI item executor's
  verdict logic, and the wrap-up residue and verdict-distribution
  gates;
- watch target resolution (`test-itf-watch`): the tag-qualified match,
  the running-run preference over newer finished runs, the post-mortem
  fallback to the newest run, and the no-match refusals.
