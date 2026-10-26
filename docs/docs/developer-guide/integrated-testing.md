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
  - `pvesm` is read-only; general reads go through a small allow-list
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
is fail-closed: a missing or invalid file aborts with a pointer to the
example. Validated keys cover the base hosts, SSH user, reserved VMID
range, itf storages, ISO sources, guest sizing, and the software source
(`release` or `dev-tarball`). Two-node keys (role bases, P2P addresses,
compute template name, PVE ISO source) are optional and activate the
compute-role machinery only when present; the role bases must be members
of `ITF_BASE_HOSTS`.

## Running

```bash
tests/integrated/itf manual-steps     # outstanding human setup, if any
tests/integrated/itf preflight        # dev + base-host readiness report
tests/integrated/itf iso fetch        # download the Debian installer ISO
tests/integrated/itf iso upload       # push it to the base ISO storage
tests/integrated/itf template build   # rebuild the post-install baseline
tests/integrated/itf journey list
tests/integrated/itf journey run j01-fresh-install
tests/integrated/itf journey run <name> --rerun
                                    # replay on the previous run's guests
                                    # (rollback to as-cloned — no clone)
tests/integrated/itf watch            # tail the active run — NOT a console
tests/integrated/itf status           # guests + template + runs overview
```

`iso fetch`/`iso upload` take an optional selector (`debian`, the
default, or `pve`), and `template build` takes `--base` (target base
host) and `--profile storage|compute` (storage = Debian + product, the
default; compute = Proxmox VE from the ISO, see below).

Every run produces a progressive report under
`tests/integrated/results/run-<timestamp>-<tag>/` (gitignored):
`steps.tsv` for tooling, `report.md` for humans, plus artifacts (logs,
`zfs list -t snapshot` listings, GUI screenshots). `itf journey run`
exits non-zero when any step failed.

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
served over HTTP from the development machine and driven over the
serial console (`qm terminal`, `lib/serial_console.py`) — the substrate
under test is ZFSutilities' installer experience, not Debian's.

Guests are disposable and their addresses are DHCP-recycled, so all
guest ssh/scp traffic uses `StrictHostKeyChecking=no` with a throwaway
known-hosts file: a fresh guest at a previously used address presents a
*different* host key, which `accept-new` rejects as a mismatch.

## GUI payload e2e matrix

The GUI does its work by building bash payloads (python/offsite_runner.py,
python/command_builders.py) and running them through BackupRunner. The
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
protocol exactly as the GUI runner launches them; the CLI orchestrator
scenarios (zfssend, zfsfullcopy, zfsrestore, the zfshold round trip) run
protocol-off as cron/terminal would, with known raw prompts pre-fed on
the pty and any unexpected prompt caught by the watchdog.

## Post-install baseline template

Journeys whose scenario begins *after* installation start from a
**baseline template**: a guest built once through the real first-time
user path (OS install → product install → OS package updates → boot
health gate) and converted to a Proxmox template (`itf template build`).
`itf_journey_stage_from_template` full-clones it, so the journey is at
the post-install point in a minute or two instead of repeating the
~15–20-minute install.

- **Full clones, by design.** The itf guest storage is LVM-thin, which
  does not support Proxmox linked clones — and full clones are the
  safer shape anyway: each clone is independent of the template, so a
  template rebuild can never break a running journey's guest. A
  thin-pool full clone copies only allocated blocks, so it stays fast.
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
  clearing in `itf_guest_clone`). Destroy the guests (`itf guest
  destroy`) when the loop is done.

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

## Testing the framework itself

The itf libraries have their own mock-based suites in the default
`tests/run-tests` set:

```bash
tests/run-tests test-itf-config test-itf-base-guard test-itf-report \
    test-itf-ssh test-itf-template test-itf-driver
```

They cover fail-closed site-config loading, example-file validity, the
confinement guard's refusals (VMID range, non-itf storages, non-allow-
listed verbs, path confinement, baseline-template protection for both
template names), dry-run behavior, audit ordering, the run-report
writer, the dev-host HTTP serve/fetch/stop round-trip used to deliver
preseeds and dev tarballs to guests, the template
stamp/resolution/clone/freshness logic for both profiles, and the
driver's dispatch/usage surface (journey listing, ISO selector, profile
flags).
