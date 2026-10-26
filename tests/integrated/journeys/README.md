# Journeys

A journey is a script that drives one realistic end-user scenario end to
end and records every step in the run report.  Journeys are **not** test
suites: they use the product the way a first-time user would (download,
install, click/type through workflows) and assert on outcomes in the
guest (ZFS state, wiring files, session logs, exit codes, GUI rendering).

## Contract

- One journey per file: `<name>.journey` (bash, sourced by
  `itf journey run <name>`).
- It MUST define `journey_main` and return non-zero to abort the run
  (the driver records a FAIL step and finishes the report).
- The full itf helper set is preloaded: `itf_step`, `itf_artifact`,
  `itf_guest_*`, `itf_iso_*`, `itf_qm`/`itf_read` (guarded),
  `itf_guest_exec`/`itf_guest_put`, `itf_http_serve`, plus the loaded
  site configuration.
- Record **every** meaningful step with `itf_step pass|fail|skip|info
  <name> [detail]`; capture evidence with `itf_artifact <label> <file>`.
- Declare required guest state in a comment header (e.g. "needs a
  completed Debian install snapshot `installed`") and fail fast with a
  clear SKIP/PREP hint when it is missing, rather than half-running.
- Software under test comes from the configured `ITF_SW_SOURCE`
  (`release` = GitHub release tarball — the new-user experience;
  `dev-tarball` = a tarball of the current dev tree, used to verify
  repairs).  A journey must never patch product files inside the guest.

## Steps common to install journeys

1. `itf iso fetch && itf iso upload <base>` (idempotent).
2. `itf guest create <name> --iso <iso> --pooldisk <GB> --start`, then
   drive the OS install over `qm terminal` with `lib/serial_console.py`
   and the preseed from `itf_preseed_render` served via
   `itf_http_serve`.
3. `itf_guest_ip <base> <vmid>` + `itf guest wait-ssh <ip>`.
4. Snapshot the clean OS (`itf guest snapshot … installed`) so later
   journeys can skip reinstallation.

## Steps common to clone-start journeys

Scenarios that begin *after* installation skip all of the above:

1. `itf_journey_stage_from_template <gname>` full-clones the post-install
   baseline template (`itf template build`), starts the clone, discovers
   its IP, waits for SSH, and snapshots `as-cloned` as the journey's
   rollback checkpoint.
2. Fail-fast PREP contract: a missing or unstamped template is a FAIL
   step with the exact `itf template build` command — never a half-run.
3. The template carries a current OS (updates are applied and
   boot-health-gated at build time), so clones need no per-journey
   `apt upgrade`.

## The stale template is the release-upgrade journeys' old-version carrier

The storage template's PRODUCT version is deliberately allowed to lag
the tree under test: a clone of a stale template is a genuinely
installed system running an older release, which is exactly the
starting state the release-upgrade journeys (j10, j12) need — "clone →
upgrade to today's tree" with zero extra infrastructure.  Both share
the upgrade staging in `common.sh` (`itf_journey_stage_upgrade_env`:
premise gate, user download, change-scan baseline, served release).  Do not
rebuild the template just because it is stale; j10 fails fast with a
PREP hint when the premise breaks (template version no longer strictly
older than the tree under test).  Under `ITF_SW_SOURCE=dev-tarball`,
j10 serves a fake "latest release" (latest.json + a release-shaped
tarball of the dev tree) and points the guest's upgrade at it via
`ZFSUTILITIES_RELEASE_API`; under `release` the guest upgrades from
real GitHub.  When the old version's GitHub tag tarball is missing
(many historical releases were never tagged), the journey also serves
the captured as-deployed tree via `ZFSUTILITIES_TAG_TARBALL_URL` so
the change scan has a pristine baseline (the upgrade itself now
captures a baseline manifest when none is obtainable — F-025, plan 021).

## Steps common to two-node journeys

j05-style scenarios span two guests on two base hosts:

1. Two clone-starts with explicit roles: `itf_journey_stage_from_template
   <gname> --base <storage-base>` and `--base <compute-base> --template
   <compute-template> --role compute`.  Per-guest state files keep the
   VMID/IP pairs apart (`guest-storage.txt`, `guest-compute.txt`).
2. The cross-node link is admin pre-work driven from the journey: net1
   NICs on the shared bridge, static P2P addresses from the site config,
   `/etc/hosts` entries, and root SSH keys exchanged both directions —
   mirroring what the two-node installer checks.
3. The compute-side guest comes from the **compute template** (PVE
   installed from the Proxmox ISO; see the developer guide's two-node
   section), so the installer's deploy push to the compute host is part
   of what the journey exercises.

## Rerunning a journey (--rerun)

`itf journey run <name> --rerun` replays a journey on the PREVIOUS run's
guests instead of re-staging them: each recorded guest is rolled back to
its staging checkpoint (`as-cloned` for clone-start journeys,
`os-installed` for install-start ones like j01/j08/j09), restarted, and
re-discovered; the journey then replays in full.  A rolled-back
install-start guest is a clean Debian with the prerequisites genuinely
missing — the same starting state a fresh install produces.

- The source run is the newest run of the SAME journey that is not still
  active and recorded at least one guest (the `rerun source` INFO step
  names it); the new run's `rerun-guests.tsv` maps guest-record names to
  base/VMID pairs.
- Only the staging step is skipped — the template clone or the OS
  install (minutes to tens of minutes per guest); the product download
  and install stages re-run deliberately — they carry the tree under
  test, which is the point of a re-verify.
- Refusals are explicit: no prior run, a still-active source, destroyed
  guests, or a missing checkpoint snapshot each fail fast with the fix
  (run fresh, no --rerun) — never a surprise full clone or reinstall.
- A dev-host restart kills the run but not its guests: the next
  `journey run`/`template build` refuses to start over the leftovers
  (the acquire-time orphan fence) until they are reused — `--rerun` of
  that same journey, which exempts its own takeover guests — or
  destroyed (`itf guest destroy`).
- The workflow is run → fix → `--rerun` → …; destroy the guests
  (`itf guest destroy`) when the loop is done.  Snapshots newer than
  the staging checkpoint survive a `qm rollback` but go stale — the
  rerun removes them first so the replay can re-create them under the
  same names.  The rollback also reverts hot-plugged NICs/disks, which
  the journey re-attaches, and restores the checkpoint's VM config —
  an install-start guest's config still carries the installer-time CPU
  freeze, so the rerun clears it between the rollback and the start
  (the clone path clears the same inherited flag on every clone).

## Current set

| Journey | Scenario |
|---------|----------|
| j01-fresh-install | flagship: fresh-OS install from release/dev tarball, prereq remediation, test pools; daily-workflow stages land in later cycles |
| j02-uninstall-reinstall | clone start, purge, assert clean state, reinstall, assert working |
| j03-install-over-leftovers | clone start, staged partial uninstall, installer detects/cleans/completes |
| j04-post-install-baseline | validates the template path end to end: clone, wiring, pools, product surface |
| j05-two-node-install | two guests on two base hosts: P2P link, storage-side install, compute-side deploy, first LUN round trip |
| j06-guest-probe-validator | composes the j05 lab, then the guest-probe validator over real datasets — honest degradation when guest agents are absent |
| j07-unarchive-iscsi-rebuild | composes the j05 lab, archives a VM, destroys the target and injects IQN drift, verifies unarchive-vm rebuilds targets and logs in |
| j08-prereq-decline | fresh Debian; installer aborts gracefully when the user declines prerequisite remediation — nothing deployed |
| j09-prereq-apt-failure | fresh Debian with a dead-apt proxy; installer surfaces the remediation failure cleanly — nothing deployed, apt heals when the drop-in is removed |
| j10-release-upgrade | clone start from the stale template (old-version carrier): download the new release, decline the upgrade offer (system untouched), inject local modifications, upgrade via the new tree's `./bin/upgrade-zfsutilities` — scan detects and salvages them, deploys the new version NOT activated — then `switch-version`, retention/wiring verify, up-to-date rerun |
| j11-payload-e2e | clone start + test pools (j04 recipe) + today's tree, then the GUI-payload e2e matrix via `tests/integrated/e2e/payload-e2e-driver.py`: offsite chain steps with holds, incrementals, rollback, resume tokens, scrub pause, backup/prune/rsync payloads, and the strict-mode-flipped leaf orchestrators — the full-matrix context for the payload exercises (unprivileged containers run only the dry-run layer; see the developer guide's payload e2e section) |
| j12-interrupted-upgrade | clone start from the stale template + the shared upgrade staging (j10's premise/baseline/serve): SIGTERM the upgrade in its early phase (EXIT trap must clean staging; nothing deployed/salvaged/activated), SIGKILL the process group mid-deploy (partial `versions/<v>` without MANIFEST, salvage kept, running system untouched), then the self-repair — re-run `upgrade-zfsutilities` re-detects and re-salvages the injected modifications and repairs the partial dir in place — `switch-version`, wiring verify, up-to-date rerun |
| j13-iscsi-storage-restore | composes the j05 lab, creates a post-backup-point LUN through the product, then regresses the storage guest's live LIO tree AND saveconfig/manifest to the backup point (mtimes preserved — the bare-metal-restore shape): the M3 detector must WARN, `reconcile-iscsi-state` must rebuild the backstore at the exact recorded LUN with LUN 0 untouched (manifest, saveconfig, pool map, compute rescan all refreshed), and PVE must start the VM again |
| j14-iscsi-fence-recover | composes the j05 lab + j13's regression staging, then verifies the compute-host fence: the units activation installed are enabled and run `check-vm-disk-paths --recover`, a manual tick detects the missing reference (exit 1, full identity), `systemctl start` on the installed unit recovers for real (local rescan → ssh reconcile on the storage guest → link back, exit 0), and the next tick is healthy |
