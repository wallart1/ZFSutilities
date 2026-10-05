# Repair Plan 001 — check-prerequisites mkdocs failure breaks first-time install remediation

**Status: EXECUTED 2026-10-05 (user-approved); VERIFIED 2026-10-05 via J01 dev-tarball rerun (results/run-20261005-113534-j01-fresh-install).**

## Finding

F-001 (see FINDINGS.md) — journey `j01-fresh-install`, run directory
`results/run-20261005-020512-j01-fresh-install/` (Stage B, artifacts
`guest-prereq.log` and `guest-install.log`).  Live-confirmed 2026-10-05:
the fresh-system guest's prereq output contains
`✗ mkdocs — not installed (install: "mkdocs<2")` — the pip spec offered
as an apt package name.  The remediation-abort leg below could not yet
execute live because F-002 stops install-single-node earlier; it is
established by code read and becomes observable as soon as F-002 is
repaired.

On a fresh Debian system a first-time user runs
`bin/check-prerequisites --single-node` (directly or through
`bin/install-single-node`), accepts the offered automatic remediation,
and the install aborts before the documentation-server step that would
have installed mkdocs.

## Root cause (reproduced by code read on the dev tree)

1. `bin/check-prerequisites` reports a missing mkdocs as a required
   failure whose apt package field is the literal string `'"mkdocs<2"'`
   (quotes included), for both the "not installed" and the "mkdocs >= 2
   installed" cases (lines ~246–250).  `mkdocs-material` likewise maps
   to a pip package name that is passed to apt.
2. `lib/installer-lib.sh` `run_interactive_prerequisites()` feeds every
   failure's package field into one `apt-get install -y` invocation
   (`collect_apt_packages` → `apt_install`).  The literal
   `'"mkdocs<2"'` token is not a valid apt package name, so apt fails,
   the function reports "Automatic installation failed", and
   `install-single-node` exits 1 — before `ensure_doc_server`, the step
   that pip-installs `mkdocs<2` + `mkdocs-material` as intended.
3. Even if the apt name were valid, the post-install re-check would
   still fail: mkdocs is only installed by `ensure_doc_server`, which
   runs after this gate on a fresh system.  A fresh system therefore
   can never pass the gate, by construction.

Net effect: the documented new-user flow (check prerequisites, accept
remediation, install) cannot complete on a fresh Debian system.

## Proposed change

- `bin/check-prerequisites`:
  - mkdocs ABSENT → not a required failure (report as an informational
    note that the installer's doc-server step installs it).
  - mkdocs PRESENT with major >= 2 → keep the hard failure (pin
    message, no apt package field).
  - mkdocs-material ABSENT → same informational treatment as mkdocs.
- `fail()` helper: tolerate an empty package field (no "(install: …)"
  suffix, nothing recorded for apt remediation).
- `lib/installer-lib.sh`: no change expected — `collect_apt_packages`
  already skips empty package fields; confirm with tests.
- The `--list-failures` machine output keeps its 4-column shape; rows
  for pip-handled items simply carry an empty third column (or are
  omitted when absent, per the first bullet).

## Blast Radius

- Suites: the prerequisites checker's tests (run-tests selection for
  check-prerequisites / installer-lib), plus `tests/test-itf-*` journey
  rerun for verification.
- Docs: `docs/docs/` prerequisites/installation pages only if they
  describe the mkdocs failure behavior (check during execution).
- Installer behavior: fresh systems proceed past remediation to
  `ensure_doc_server`; systems with mkdocs >= 2 still hard-fail with
  the pin guidance.  No change for fully-provisioned systems.

## Verification

1. Unit/suite runs for the checker on the dev tree.
2. Rebuild a dev tarball, rerun journey `j01-fresh-install` Stage B:
   `check-prerequisites --single-node` reports the missing apt items
   (zfsutils-linux, pv, python3-gi, webkit, …) WITHOUT mkdocs rows;
   `install-single-node` with piped answers completes rc=0, installs
   pip mkdocs<2 + material, and Stage C verifies the installed state.
