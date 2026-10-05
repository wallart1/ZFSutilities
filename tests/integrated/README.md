# Integrated Testing (itf)

`tests/integrated/itf` is an orchestrator that plays a **first-time end
user** of ZFSutilities: it creates disposable nested guests on the base
Proxmox test VMs, installs a target OS from an ISO, installs ZFSutilities
the way a real user would (GitHub release download, interactive
installer), drives realistic day-to-day workflows, and verifies outcomes —
journeys, not test suites.

Layer model:

```
dev (itf orchestrator)
  └── base PVE hosts (zfstestvm1/2 — PROTECTED)
        │   only guarded guest-lifecycle commands via sudo -n;
        │   VMID range + storage allow-lists + audit log (lib/base-lib.sh)
        └── nested guest (DISPOSABLE — anything goes in here)
              └── ZFSutilities under test (release or dev tarball)
```

## Quick start

```bash
cp tests/integrated/site/config.example tests/integrated/site/config
# edit site/config for your environment
tests/integrated/itf manual-steps   # anything a human must still do
tests/integrated/itf preflight      # full dev + base-host readiness check
tests/integrated/itf iso fetch      # download the installer ISO
tests/integrated/itf iso upload     # push it to the base ISO storage
tests/integrated/itf journey list
tests/integrated/itf journey run <name>
```

Every run (journey or preflight) writes a progressive report under
`results/run-<timestamp>-<tag>/` (gitignored): `steps.tsv` for tooling,
`report.md` for humans, plus artifacts captured along the way.

## Layout

| Path | Purpose |
|------|---------|
| `itf` | driver CLI (`preflight`, `guest …`, `iso …`, `journey …`, `status`, `manual-steps`) |
| `lib/config-lib.sh` | site configuration load + fail-closed validation |
| `lib/ssh-lib.sh` | dev↔base, dev↔guest transports; preseed HTTP server |
| `lib/base-lib.sh` | **the guard**: allow-listed qm verbs, VMID range, itf-only storages, audit log, dry-run |
| `lib/guest-lib.sh` | guest lifecycle, ISO fetch/upload, preseed rendering, IP discovery |
| `lib/report-lib.sh` | progressive PASS/FAIL/SKIP run reports |
| `lib/serial_console.py` | `qm terminal` driver for OS-install automation (python3 stdlib) |
| `journeys/` | end-user journeys (see `journeys/README.md`) |
| `site/config.example` | committed schema; real `site/config` is gitignored |
| `FINDINGS.md` | product issues found by journeys |
| `repair-plans/` | numbered fix proposals awaiting user approval |
| `results/` | run outputs (`run-*` gitignored) + curated phase reports |

## Safety model

- The orchestrator **never** writes base-PVE system config: no storage.cfg
  edits, no network changes, no package installs, no systemd units.
  Base-host mutations are limited to `qm` lifecycle verbs against VMIDs in
  the reserved range, with disks only on the dedicated itf storages, and
  every mutating call is appended to an audit log on the base host before
  it runs.
- `ITF_DRY_RUN=1` prints guarded commands instead of executing them.
- Base changes beyond that (creating the itf storages, the reserved VMID
  policy, the audit log) are *manual steps the orchestrator emits
  instructions for* — a human applies them, `itf preflight` verifies.
- The base VMs themselves sit under daily ZFSutilities snapshots — the
  recovery net behind the guardrails.
- Guests are disposable: any state in them may be destroyed at any time
  (`itf guest destroy`, snapshot/rollback).

## Findings and repair loop

Failures observed through the end-user surface become entries in
`FINDINGS.md`; fixes are proposed as `repair-plans/NNN-slug.md` and
executed in the dev repository **only after user approval**, then verified
by rerunning the journey on a dev-built tarball.  See
`repair-plans/README.md`.

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 0 | inventory, resource request, manual base setup, confinement rules | complete (`results/phase0/`) |
| 1 | orchestrator MVP: driver, guard libs, site schema, own tests, docs | complete |
| 2 | cycle-1 journeys (fresh install, uninstall/reinstall, install-over-leftovers) | next |
| 3+ | two-node cycle, release upgrades, GUI automation, failure injection, OS matrix | planned |

Developer-facing detail: `docs/docs/developer-guide/integrated-testing.md`.
