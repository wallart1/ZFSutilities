# Repair Plan 008 — partial-uninstall cleanup fallback resolves the uninstaller from the repo root

Finding: **F-008** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (standing repair approval).  Guard test
extended to lib/installer-lib.sh and red/green proven via working-tree
swap; the partial-uninstall fixture in test-installer-checks now plants
the fake uninstaller at the shipped bin/ position.**

## Root cause / fix

`check_partial_uninstall` (lib/installer-lib.sh) tried the deployed
uninstaller first, then fell back to `$repo_dir/uninstall-zfsutilities`
— repo root — while the file ships in `bin/`.  In the exact state the
warning exists for (version base present, `current` gone), the deployed
path cannot exist, so the fallback runs and fails on a fresh clone:
`✗ ERROR: uninstall-zfsutilities not found`, killing the installer's
offered recovery.  Fixed to `$repo_dir/bin/uninstall-zfsutilities`
(assignment, test, and the "Expected one of" hint echo).  Discovered
statically while authoring J03 (install-over-leftovers), whose scenario
is precisely this state.

## Verification

1. test-installer-structure (path walk now covers installer-lib.sh):
   red with the old path, green after.
2. test-installer-checks partial-uninstall suite green with the fixture
   at bin/.
3. J03 journey (to be authored): partial state + installer rerun must
   offer cleanup and complete it from the repo checkout.
