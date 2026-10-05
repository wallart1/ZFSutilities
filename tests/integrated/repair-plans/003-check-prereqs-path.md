# Repair Plan 003 — installers resolve check-prerequisites from the repo root

Finding: **F-003** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (user-approved).  Verification: guard test
red/green proven (working-tree swap, no git involved); J01 dev-tarball rerun
(results/run-20261005-120247) live-confirms the prerequisites step now RUNS —
"=== Checking Prerequisites ===" block appears, both remediation prompts are
asked and answered, remediation reaches apt.  VERIFIED in run-20261005-132650: the
prerequisites step ran end-to-end — prompts answered, apt remediation
succeeded, re-check passed.  Journey-level green (installer rc=0) completes
with plan 006.**
Evidence: results/run-20261005-111841-j01-fresh-install/guest-install.log —
the log jumps from the installer banner straight to the MkDocs step with
no "=== Checking Prerequisites ===" block, and the installed system ends
up without zfs/pv/rsync/smartctl/GTK packages.

Sharpened in results/run-20261005-113534-j01-fresh-install/guest-install.log
(attempt 23, with F-001/F-002 repaired): the installer itself now dies
mid-deploy —

```
✓ Configuration saved to /etc/zfsutilities/node.conf
=== Step 3: Deploying Versioned Installation ===
/root/ZFSutilities/bin/deploy-version:156: INFO: === Deploying to local host (itfj01) ===
/root/ZFSutilities/bin/deploy-version: line 163: rsync: command not found
```

rc=127.  The silently-skipped prerequisites step is what would have
installed rsync, so a first-time user on a fresh Debian hits a hard
installer crash, not merely a missing zpool later.

## Root cause

`bin/install-single-node` (line 81) and `bin/install-two-node` (line 92)
compute:

```bash
check_prereqs="$repo_dir/check-prerequisites"
```

`check-prerequisites` ships in `bin/`, not at the repo root, so
`[[ -f "$check_prereqs" ]]` is false on a fresh clone/tarball and the
whole interactive-prerequisites block is silently skipped.  This is the
same layout-drift family as F-002: a path that only resolves against
some pre-existing deployed tree.  It was invisible until F-002 was
repaired because install-single-node died earlier at the
installer-lib.sh load.

## Proposed change

In both scripts:

```bash
check_prereqs="$script_dir/check-prerequisites"
```

One line each; the existing `[[ -f ]]` guard and the
`run_interactive_prerequisites` flow are unchanged and correct once the
path resolves.

Files touched: `bin/install-single-node`, `bin/install-two-node`.

## Guard test

Extend `tests/test-installer-structure` to also resolve non-`.sh`
references of the same `$repo_dir/`-rooted shape (`check-prerequisites`)
— the current walk only covers `*.sh` references.  A general
"`$repo_dir/<file>` referenced by bin/ scripts exists in the layout"
check would have caught F-002, F-003, and the whole class.

## Verification

1. Guard test red on the current tree (with the extension), green after.
2. Affected suites (test-installer-structure, test-check-prerequisites).
3. J01 dev-tarball rerun: Stage B must show the remediation prompts
   ("Install missing required prerequisites now?" → y → apt installs
   zfsutils-linux, pv, rsync, smartmontools, python3-gi, GTK/WebKit
   gir packages, python3-pip), the re-check passes with mkdocs absent
   now a warning (F-001 fix), install completes rc=0 with the correct
   hostname, and Stage C verifies the installed state.  The journey's
   install answers must be flipped back to `y y Enter Enter` at that
   point (see the comment in j01-fresh-install.journey Stage B).
