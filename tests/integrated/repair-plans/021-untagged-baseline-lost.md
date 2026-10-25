# Repair Plan 021 — change-scan baseline lost for untagged pre-manifest versions

Finding: **F-025** (tests/integrated/FINDINGS.md)
Status: **PART 1 EXECUTED 2026-10-24 (user-approved Option 1;
trust-on-first-upgrade manifest).  Red/green proven by file-swap
against HEAD (2 new tests fail pre-fix, 22/22 post-fix; local + remote
capture paths).  j10 rerun GREEN in
run-20261024-150441-j10-release-upgrade (20 pass / 0 fail) with the
fix riding in the dev tarball.  Part 2 (tag hygiene) NOT selected by
the user — not executed.**

## Root cause

`upgrade-zfsutilities`'s change scan needs a per-host baseline for the
active version: either `MANIFEST.sha256` inside the deployed tree
(written by deploy-version since 0.125.0) or, failing that, a pristine
copy of that version fetched from GitHub
(`…/archive/refs/tags/v<active>.tar.gz`, upgrade-lib's
`ensure_pristine_root`).  Many released versions were never pushed as
tags — `git ls-remote --tags origin` shows sparse coverage (0.118.0,
0.119.0, 0.122.0, 0.124.0, 0.128.0 among the missing) — so for a
deployment that is both pre-manifest and untagged the fetch 404s, the
host is marked `no-baseline`, and the upgrade proceeds after WARN
"local modifications CANNOT be detected": the modification listing,
the diff rendering, the archive prompt, and the salvage never engage
(observed live: j10 run results/run-20261024-140412-j10-release-upgrade,
injected MOD+ADD silently skipped; the upgrade otherwise completed
correctly).  Exactly the old deployments most likely to carry local
tweaks are the ones that lose the nothing-is-destroyed net.

## Proposed change (two independent parts; approve either or both)

1. **Trust-on-first-upgrade manifest** (bin/upgrade-zfsutilities,
   lib/upgrade-lib.sh): when the active version has no
   `MANIFEST.sha256` and no pristine source is obtainable, write a
   manifest of the CURRENT active tree before deploying — after
   telling the user the baseline is being captured now and that
   modifications older than this upgrade cannot be distinguished.
   Fences every future upgrade from this host even when nothing else
   changes; matches the salvage philosophy (preserve, then proceed).
   Implementation: a `__baseline` remote-driver mode or a small
   `upgrade_lib_write_manifest "$version_base/versions/$active"` call
   in `process_host`'s no-baseline branch (local + ssh-shipped).
2. **Tag hygiene at release time** (process, not code): push the
   release tag for every version that ships, so the pristine fallback
   works for fresh installs of those versions.  Optionally also
   backfill the missing historical tags from the release commits
   (`git tag` + push; the commits exist in history).

Blast radius (part 1): bin/upgrade-zfsutilities, lib/upgrade-lib.sh;
suites test-upgrade-zfsutilities / test-deploy-version (manifest
helpers already covered there); j10 rerun expected to show the
no-baseline WARN replaced by the baseline-capture notice — the journey
keeps serving its captured as-deployed baseline, so its assertions do
not depend on which branch fired.

## Verification

- Affected unit suites green (test-upgrade-zfsutilities 22/22,
  test-deploy-version, test-strict-mode; full suite green at wrap-up).
- The capture path (pristine withdrawn) is exercised end-to-end by the
  two new orchestrator-level tests — they run the real
  upgrade-zfsutilities against a manifest-less, untagged host, local
  and via the ssh-shim remote, and were the red side of the file-swap
  proof against HEAD.  j10 rerun green with the fix in the dev tarball
  (run-20261024-150441); its served-pristine path is unchanged, as
  expected.
