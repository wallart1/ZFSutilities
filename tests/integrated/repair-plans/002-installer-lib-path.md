# Repair Plan 002 — installer-lib.sh resolved from the wrong directory

Finding: **F-002** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (user-approved); VERIFIED 2026-10-05 via J01 dev-tarball rerun (results/run-20261005-113534-j01-fresh-install) + full suite green.**
Evidence: results/run-20261005-020512-j01-fresh-install/guest-install.log
(single line: `bashinit FATAL: Missing:
/root/ZFSutilities/bin/installer-lib.sh`), plus the extracted release tree
itself: `lib/installer-lib.sh` present, `bin/installer-lib.sh` absent.

## Root cause

`bin/install-single-node` (line 38) and `bin/install-two-node` (line 42)
both compute:

```bash
installer_lib="$script_dir/installer-lib.sh"
```

`$script_dir` is the `bin/` directory of the script itself, but
`installer-lib.sh` ships in `lib/`.  Introduced in 0.96.0 (commit 8df9399)
when the installer support library was created/moved to `lib/`; the two
callers were never pointed at the new location.

Why it stayed hidden: every install since then ran over an existing
deployed tree (deploy-version upgrades) or in development checkouts that
predated the split, so the missing path was never resolved against a
fresh layout.  A first-time user following the README (clone or source
tarball → `sudo ./bin/install-single-node`) fails on the first line of
real work.

## Proposed change

In both scripts, resolve the library relative to the repository root,
which both scripts already compute two lines above (`repo_dir`):

```bash
installer_lib="$repo_dir/lib/installer-lib.sh"
```

The `[[ -f ... ]] || die "Missing: ..."` guard stays as-is; its message
then names the real shipped location.

Files touched: `bin/install-single-node`, `bin/install-two-node`
(one line each).  No public-interface change; existing installs are
unaffected (the path is resolved at runtime).

## Guard test

Add a small structural check to the itf-independent test layer: for each
of `bin/install-single-node` and `bin/install-two-node`, extract the
`installer_lib=` assignment and assert the referenced file exists at that
path relative to the repo root.  This fails on the current tree and
passes after the fix, and would have caught 0.96.0.

## Verification

1. The guard test above, plus the affected existing suites.
2. Re-run J01 fresh (`itf journey run j01-fresh-install`): Stage B must
   proceed past the library load into the interactive prerequisite flow.
   The next expected stop is F-001's mkdocs remediation gate — that is
   progress, not a regression.
