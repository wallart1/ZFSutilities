# Repair Plan 009 — remediation leaves the ZFS kernel module unbuilt

Finding: **F-009** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (standing repair approval).  VERIFIED:
4 probe tests green; run-20261005-151307 remediated with
linux-headers-6.12.111+deb13-amd64, dkms built in the apt transaction,
re-check passed, and J01 went FULLY GREEN (21 pass / 0 fail) with all
three RAIDZ1 pools ONLINE.**

## Root cause

check-prerequisites verified the `zfs`/`zpool` BINARIES only.  On stock
Debian the kernel module comes from `zfs-dkms` (pulled in with
zfsutils-linux from contrib), and dkms builds it only when the matching
kernel headers are installed — nothing in the prerequisite set or the
remediation package list installs them, so a "successful" install ends
with `zfs/2.3.9: added` (registered, never built) and the first
`zpool` dies with "The ZFS modules cannot be auto-loaded".

## Fix (probe-and-degrade, matching the capability-probing pattern)

- bin/check-prerequisites: new functional check after the core tools —
  when `modinfo` exists, probe `modinfo zfs`; on failure emit a core
  failure row `zfs-kernel-module` whose package column is the dynamic
  `linux-headers-$(uname -r)` (installing headers triggers the dkms
  build).  Systems with prebuilt modules (Ubuntu, PVE) pass untouched;
  without modinfo the probe is skipped silently.
- lib/installer-lib.sh: prerequisite description for the new row.
- Tests: MODINFO_STUB/uname knobs; row fires when unbuilt, absent when
  built, skipped without modinfo, and appears alongside zfs/zpool on
  the fresh-Debian shape (zfsutils-linux + headers remediated together).
- Docs: README requirement line, developer-guide prerequisites row,
  commands.md checker section, messages/index row.

## Verification

J01 rerun: the remediation apt run must include the headers package,
the dkms build must complete inside the apt transaction, the re-check
must pass (`✓ zfs-kernel-module`), and Stage D must create the three
pools — first full-journey green.
