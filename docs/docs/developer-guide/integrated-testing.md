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
range, itf storages, ISO source, guest sizing, and the software source
(`release` or `dev-tarball`).

## Running

```bash
tests/integrated/itf manual-steps     # outstanding human setup, if any
tests/integrated/itf preflight        # dev + base-host readiness report
tests/integrated/itf iso fetch        # download the installer ISO
tests/integrated/itf iso upload       # push it to the base ISO storage
tests/integrated/itf template build   # rebuild the post-install baseline
tests/integrated/itf journey list
tests/integrated/itf journey run j01-fresh-install
tests/integrated/itf watch            # tail the active run — NOT a console
tests/integrated/itf status           # guests + template + runs overview
```

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
    test-itf-ssh test-itf-template
```

They cover fail-closed site-config loading, example-file validity, the
confinement guard's refusals (VMID range, non-itf storages, non-allow-
listed verbs, path confinement, baseline-template protection), dry-run
behavior, audit ordering, the run-report writer, the dev-host HTTP
serve/fetch/stop round-trip used to deliver preseeds and dev tarballs to
guests, and the template stamp/resolution/clone/freshness logic.
