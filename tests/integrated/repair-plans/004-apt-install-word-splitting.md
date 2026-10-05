# Repair Plan 004 — remediation passes the package list as one glued apt argument

Finding: **F-004** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (user-approved).  Guard test red/green
proven via working-tree swap (no git involved).  Live-confirmed in
results/run-20261005-123403: apt now receives one package per argument
(the error signature changed from "Unable to locate package <all
names glued>" to a normal per-package "no installation candidate" for
zfsutils-linux — a distinct, environmental cause tracked as F-005).
VERIFIED in run-20261005-132650: the
remediation apt run succeeded end-to-end (`✓ Installed: zfsutils-linux
rsync …`).  Journey-level green (installer rc=0) completes with plan 006.**
Evidence: results/run-20261005-120247-j01-fresh-install/guest-install.log —

```
  Installing: zfsutils-linux rsync smartmontools python3-gi gir1.2-gtk-3.0 python3-pip pv gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
E: Unable to locate package zfsutils-linux rsync smartmontools python3-gi gir1.2-gtk-3.0 python3-pip pv gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
  ✗ Failed to install: zfsutils-linux rsync smartmontools ...
✗ Automatic installation failed. Please install the items manually and re-run.
```

apt parsed the entire space-joined list as a SINGLE package name.  The same
signature reproduces host-side with `apt-get install -s 'pv rsync'`
(→ `E: Unable to locate package pv rsync`), while separate arguments
simulate cleanly.

## Root cause

`run_interactive_prerequisites` in `lib/installer-lib.sh` collapses
`collect_apt_packages`' newline-separated output into one string and passes
it as a single quoted argument:

```bash
packages=$(collect_apt_packages | tr '\n' ' ')
...
if [[ -z "$packages" ]]; then ... fi      # emptiness check on the string
...
if ! apt_install "$packages"; then        # ← ONE argument, spaces inside
```

`apt_install` is correct — it forwards `"$@"` to
`apt-get install -y "${packages[@]}"` — and every other caller
(mkdocs/mkdocs-material, python3-pip, targetcli-fb) passes bare words.
Only this call site is broken.  The path was unreachable before F-002 and
F-003 were repaired, so it had never once run end-to-end on a fresh system.

## Proposed change

In `run_interactive_prerequisites`, keep the list as an array throughout
(no string round-trip, no reliance on word splitting):

```bash
local -a pkg_list
mapfile -t pkg_list < <(collect_apt_packages)
if (( ${#pkg_list[@]} == 0 )); then
    ... no installable packages ...
fi
...
echo "  apt-get install -y ${pkg_list[*]}"    # display only
...
if ! apt_install "${pkg_list[@]}"; then
```

`collect_apt_packages` already emits one non-empty package name per line
(it skips empty rows), so `mapfile` needs no filtering.

Files touched: `lib/installer-lib.sh` (one function).

## Guard test

Add a case to `tests/test-check-prerequisites` (or the installer-structure
suite if it fits better there) asserting the remediation call site expands
an array — e.g. grep that `apt_install "$packages"`-style single-variable
quoted calls no longer appear in installer-lib.sh, or pin the exact
`apt_install "${pkg_list[@]}"` line.  Negative-provable by reverting the
line.

## Verification

1. Affected suites: test-check-prerequisites, test-installer-structure,
   plus whatever suite covers installer-lib if one exists.
2. J01 dev-tarball rerun: with F-003 landed, the prereq block now reaches
   apt — the remediation must succeed
   (`✓ Installed: zfsutils-linux rsync ...`), the re-check must pass
   (F-001's mkdocs warnings absorb the two pip-installed doc items),
   install must complete rc=0, and Stage C/D must verify for the first
   full-journey green.
