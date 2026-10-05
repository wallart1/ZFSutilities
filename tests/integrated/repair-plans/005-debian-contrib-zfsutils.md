# Repair Plan 005 — zfsutils-linux needs Debian contrib; nothing tells the user

Finding: **F-005** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-05 (user-approved).  VERIFIED: 4 new probe
tests green (note shown only when no candidate; silent when a candidate
exists, when zfs is present, and when apt-cache is unavailable), and
run-20261005-132650 fetched zfsutils-linux/zfs-dkms from trixie/contrib with
the note correctly absent.  Journey-level green (installer rc=0) completes
with plan 006.**
Evidence: results/run-20261005-123403-j01-fresh-install/guest-install.log —

```
  Installing: zfsutils-linux rsync smartmontools python3-gi gir1.2-gtk-3.0 python3-pip pv gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
Package zfsutils-linux is not available, but is referred to by another package.
E: Package 'zfsutils-linux' has no installation candidate
```

The guest is a stock Debian 13 install (netinst defaults: `main` +
`non-free-firmware`, contrib NOT enabled).  `zfsutils-linux` ships in
Debian's **contrib** archive only — verified directly against
`deb.debian.org/debian/dists/trixie/contrib/binary-amd64/Packages`
(zfsutils-linux 2.3.9-0+deb13u1) while the main index has no such
package.  Ubuntu/Mint carry it in main, which is why the dev
environment cannot surface this.

## Root cause

Two shipped surfaces assume `apt install zfsutils-linux` just works:

- README "Requirements": `ZFS userland utilities (zfsutils-linux)`
- docs developer-guide prerequisites: `sudo apt install zfsutils-linux`

and the check-prerequisites failure text offers
`(install: zfsutils-linux)` which the installer's remediation passes to
apt.  On stock Debian all of these dead-end at "no installation
candidate" with no hint that enabling contrib fixes it.

## Proposed change

Two coordinated parts:

1. **Runtime hint in check-prerequisites** (primary, per the
   probe-and-degrade design pattern): when the `zfs`/`zpool` check
   fails AND `apt-cache policy zfsutils-linux` shows no candidate,
   append a hint line to the failure output, e.g.

   ```
   ✗ zfs — command not found (install: zfsutils-linux)
     Note: on Debian, zfsutils-linux is in the contrib archive —
     enable contrib in /etc/apt/sources.list (or the equivalent
     .sources file) if apt reports no installation candidate.
   ```

   Detection is runtime (apt-cache probe), not distro-sniffing; on
   systems where the candidate exists the hint never appears.
   The hint is informational — the failure/remediation mechanics are
   unchanged.

2. **Docs note**: README Requirements bullet and the developer-guide
   prerequisites row gain the same one-line Debian/contrib note.

Harness counterpart (executed together with this plan, as part of the
itf tree, not the product): the journey preseed enables contrib
(`d-i apt-setup/contrib boolean true`) so the guest models a user who
has followed the documented requirement — the stock-guest case that
produced F-005 is then covered by the checker-hint tests instead.

Files touched (product): `bin/check-prerequisites`,
`tests/test-check-prerequisites` (hint shown when no candidate; absent
when candidate exists), `README.md`, `docs/docs/developer-guide/index.md`.
Files touched (harness): `tests/integrated/lib/guest-lib.sh` (preseed).

## Verification

1. Affected suites: test-check-prerequisites, test-installer-checks,
   docs anchor/manual suites if the docs pages are in their scope.
2. J01 dev-tarball rerun: guest now has contrib enabled; the
   remediation apt run must succeed (`✓ Installed: zfsutils-linux
   rsync …`), the re-check passes (mkdocs warnings per F-001), install
   completes rc=0, Stage C verifies, and Stage D creates the three
   RAIDZ1 pools — first full-journey green.
