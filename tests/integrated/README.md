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
tests/integrated/itf template build # post-install baseline template (once
                                    # per release; one unattended install)
tests/integrated/itf journey list
tests/integrated/itf journey run <name>
tests/integrated/itf journey run <name> --rerun
                                    # replay on the previous run's guests:
                                    # rollback to the staging checkpoint
                                    # (as-cloned / os-installed) instead
                                    # of re-cloning or reinstalling (fast
                                    # re-verify)
tests/integrated/itf watch          # tail the active run — NOT the console
```

**One run at a time per dev host — enforced by the driver, not by
convention.** Every run binds the fixed HTTP port, arms the shared
installer-syslog listener, and consumes the base hosts' guest budget,
and the parallel repo lanes share all of it. `journey run` and
`template build` take a machine-wide flock (`/tmp/itf-active-run.lock`):
a concurrent starter WAITS (heartbeats every 30 s, up to
`ITF_RUNLOCK_WAIT=7200` s; `0` refuses instantly) and names the active
holder — including which repo lane holds it. The lock dies with the
holder's process, so it can never go stale. `itf status` shows the
holder under `== run lock ==`. If the dev host restarts mid-run the
lock frees correctly but the run's guests survive on the base hosts —
so each start also runs the acquire-time **orphan fence**: recorded
guests of interrupted runs still present on a base refuse the new run
(reuse them with `journey run <same> --rerun`, or discard with
`itf guest destroy`) until the bases are clean.

Two-node cycle (second base host in the compute role) additionally:

```bash
tests/integrated/itf iso fetch pve            # Proxmox VE ISO for the
                                              # compute template
tests/integrated/itf iso upload <compute-base> pve
tests/integrated/itf template build --base <compute-base> --profile compute
```

Every run (journey or preflight) writes a progressive report under
`results/run-<timestamp>-<tag>/` (gitignored): `steps.tsv` for tooling,
`report.md` for humans, plus artifacts captured along the way.

## Layout

| Path | Purpose |
|------|---------|
| `itf` | driver CLI (`preflight`, `guest …`, `iso …`, `template …`, `journey …`, `status`, `manual-steps`) |
| `lib/config-lib.sh` | site configuration load + fail-closed validation |
| `lib/ssh-lib.sh` | dev↔base, dev↔guest transports; preseed HTTP server |
| `lib/base-lib.sh` | **the guard**: allow-listed qm verbs, VMID range, itf-only storages, audit log, dry-run, baseline-template protection |
| `lib/guest-lib.sh` | guest lifecycle (create/clone/start/stop/snapshot/destroy), ISO fetch/upload (Debian + PVE), preseed/answer rendering, IP discovery |
| `lib/template-lib.sh` | post-install baseline templates: storage profile (Debian + product) and compute profile (PVE from the ISO) — build/stamp/status/destroy |
| `lib/report-lib.sh` | progressive PASS/FAIL/SKIP run reports |
| `lib/runlock-lib.sh` | **the serialization fence**: `journey run` and `template build` take a machine-wide kernel lock (flock) so only one run executes per dev host at a time — concurrent starters from ANY repo worktree wait with heartbeats (or refuse with `ITF_RUNLOCK_WAIT=0`), and the holder (journey, pid, start time, repo) is recorded for `itf status`. Acquire also runs the **orphan fence**: guests recorded by INTERRUPTED runs that still exist on a base (a dev restart frees the lock but not the guests) refuse the new start, naming each leftover and its recovery (`journey run <same> --rerun` to reuse, `itf guest destroy` to discard); a rerun exempts its own takeover guests, and an unreachable base fails closed |
| `lib/serial_console.py` | `qm terminal` driver for OS-install automation (python3 stdlib) |
| `journeys/` | end-user journeys (see `journeys/README.md`) |
| `site/config.example` | committed schema; real `site/config` is gitignored |
| `FINDINGS.md` | product issues found by journeys |
| `REQUIREMENTS.md` | the recovery-requirements register — UX gaps and design directions seeded from journey outcomes, directing future coding |
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
- The **baseline template** is durable infrastructure: the guard refuses
  everyday mutating verbs against the VMID carrying the template's name
  (`itf template build`/`destroy` manage it, clone is exempt).  Journeys
  get post-install guests as **full clones** — independent of the
  template, so a rebuild can never break a running journey's guest.
- Base changes beyond that (creating the itf storages, the reserved VMID
  policy, the audit log) are *manual steps the orchestrator emits
  instructions for* — a human applies them, `itf preflight` verifies.
- The base VMs themselves sit under daily ZFSutilities snapshots — the
  recovery net behind the guardrails.
- **While a run is active, keep hands off the consoles** (`itf status`
  shows active runs; `itf manual-steps` prints the standing rule): the
  guest's xterm.js console is the same serial line the orchestrator
  drives, noVNC is look-don't-touch, and a base-VM console is root with
  no guardrails. Watch runs with `itf watch` instead.
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
| 2 | cycle-1 journeys (fresh install, uninstall/reinstall, install-over-leftovers) | complete |
| 2.5 | post-install baseline template (`qm template` + full clone): j02/j03 convert to clone-start, j04 validates; journeys begin at the installed state without reinstalling | complete |
| 3 | two-node cycle: compute-role base host + PVE-ISO compute template, P2P cross-node link, j05 two-node install + first-LUN verify | complete |
| 3.5 | fast re-verification (`journey run --rerun`: rollback to `as-cloned` instead of re-cloning) + installer failure paths (j08 prereq decline, j09 apt failure) | complete |
| 3.6 | release upgrades (j10): stale-template clone → `upgrade-zfsutilities` decline/scan/salvage/deploy-not-activated → `switch-version` → retention verify → up-to-date rerun | complete |
| 3.7 | iSCSI resilience (j13/j14): storage-restore regression → detection + map-driven reconcile at exact LUNs → VM boot; compute-host fence wiring, detection exit, unit-driven unattended recover | complete |
| 3.8 | interrupted upgrade (j12): SIGTERM the upgrade early (staging trap cleans, nothing changed), SIGKILL the process group mid-deploy (partial `versions/<v>`, salvage kept, system untouched), then the self-repair — re-run `upgrade-zfsutilities` | complete |
| 3.9 | recovery-scenario campaign — lab foundation (G0): shared test-pools stage, single-node lab builder, opt-in LUKS key-device lab on the j05 lab, guest reboot stage, VM-OS disk image (`itf vmimage`) + agent-channel workload helpers; the j15–j18 recovery journeys build on it. G1 delivered j15-iscsi-boot-keys (boot-and-keys scenarios on the encrypted lab: journal oracle, blind recovery, compute fallout, wrong-input cases). G2 delivered j16-iscsi-total-loss (total live loss + the 3-of-33 incident shape + the total-wipe restore pair + corrupt saveconfig + pool identity, with the j13/j14 regression reruns). G3 delivered j17-iscsi-interrupted-ops (interrupted/contradictory operations: Ctrl-C'd reconcile and remove-vm-disk half states with idempotent re-run convergence, the new-vm-disk collision pair, the hand-destroy attempt fenced by the zvol layer, mistyped responses). G4 delivered j18-compute-power-events (compute & power events: compute-reboot-only with the unaided-vs-operator classification and the onboot autostart race recorded live, the both-node power cycle with the ssh-255 fence WARN live against unreachable storage and the post-return truth (sessions + plain LUNs unaided; the fence red exactly for the keys-pending LUN until the ceremony — F-042's keys-pending fence save stranding the encrypted-LUN indexes, healed by repair-plan 023's pool-map fallback), and the orphan-LUN pair with every checking surface proven blind and both teardown paths converging). G5 wrapped the campaign: repair-plan 024 executed (the concurrent-LIO-mutator `iscsi-lio` fence — refuse-never-wait naming the holder, comment-only-manifest installs prevented, apply-truthful summary counts), a transient-listing FATAL in recover's re-run fixed in-cycle (F-044), the FINDINGS ledger triaged to terminal states (plans 025 portal-binding and 026 map-grants-dimension proposed for approval), the REQUIREMENTS.md register seeded (R-01..R-09), the coverage map added (developer-guide/itf-coverage.md), boot-keys docs clarified (availability ≠ loadedness), power-event operator notes added to the runbook, and the whole set proven live — j17/j16/j18/j15/j07 fresh-run green on the final tree | complete |
| 3+ | GUI automation, further failure injection, OS matrix (more template profiles) | planned |

Developer-facing detail: `docs/docs/developer-guide/integrated-testing.md`.
