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

## Current set

| Journey | Scenario |
|---------|----------|
| j01-fresh-install | flagship: install from release, test pools, backup/retention/scrub/restore, schedule, GUI smoke |
| j02-uninstall-reinstall | purge, assert clean state, reinstall, assert working |
| j03-install-over-leftovers | partial-uninstall recovery path |
