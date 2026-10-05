# Repair Plan 006 — informational launcher skip kills headless installs

Finding: **F-006** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (user-approved).  Scope note: while
executing, the IDENTICAL hazard was confirmed in the same lib's
remove_desktop_symlinks (same `return 1` skip paths, unguarded at
bin/switch-version:262 inside uninstall_wiring — the abort would strike
mid-UNWIRE on headless hosts, and J02's uninstall journey would hit it).
Fixed identically under the same finding rather than spun off: both
remove-path skips also `return 0` now, with a matching set -e pin.
Guard tests red/green proven via working-tree swap (no git involved).
VERIFIED in run-20261005-140352: install-single-node completes rc=0 —
the first-time-user flow finishes on a headless fresh Debian.  Full
JOURNEY green is blocked one step later by F-007 (recipe assumes
parted).**
Evidence: results/run-20261005-132650-j01-fresh-install/guest-install.log —
after `✓ Installed: zfsutils-linux …` (remediation), the MkDocs step, and a
complete deploy/switch-version wiring transcript, the log ends at:

```
bashinit:341: WARN:   ⚠ Cannot determine desktop user; skipping home-directory symlinks.
desktop-launcher-lib.sh:68: INFO:     To create them manually, run:
desktop-launcher-lib.sh:69: INFO:       ln -s … zfsutilities-gui "$HOME/ZFSutilities GUI"
desktop-launcher-lib.sh:71: INFO:       ln -s … zfsutilities-docs "$HOME/ZFSutilities Documentation"
```

— no error, no installer summary; `install-single-node` exits 1.

## Root cause

`create_desktop_symlinks` in `lib/desktop-launcher-lib.sh` treats the two
informational skip paths (no desktop user detectable — any headless host;
no home directory for the detected user) as failures: warn + instructions
+ `return 1` (lines 73 and 80).  The only live caller,
`install_wiring` at `bin/switch-version:228`, invokes it unguarded inside
the `set -e` chain (switch-version → deploy-version →
install-single-node), so the skip aborts the entire installer after
everything already succeeded.  The lib-missing fallback stub defined
just above the call chain (`create_desktop_symlinks() { return 0; }`,
bin/switch-version:64) shows the intended soft contract; two existing
tests (test-installer-checks, `handles_missing_user` /
`handles_missing_home`) currently pin the faulty rc≠0 behavior.

## Proposed change

Make the skip paths informational, matching the stub contract:

- `lib/desktop-launcher-lib.sh`: both skip paths keep their warning +
  manual instructions but `return 0` (a skip is not an error).
- `tests/test-installer-checks`: flip the two assertions to expect
  rc 0 WITH the warning text still logged (the warning remains the
  user-visible signal).
- Guard test: add a set -e subshell regression pin —
  `set -e; create_desktop_symlinks ""` must not abort.

Files touched: `lib/desktop-launcher-lib.sh`,
`tests/test-installer-checks`.

## Verification

1. Affected suites: test-installer-checks, test-switch-version (it
   exercises install_wiring; line 475 references the function).
2. J01 dev-tarball rerun — expected FIRST FULL JOURNEY GREEN:
   install completes rc=0 (summary printed), Stage C verifies the
   installed state, Stage D creates the three RAIDZ1 pools on the
   hot-plugged disk.
