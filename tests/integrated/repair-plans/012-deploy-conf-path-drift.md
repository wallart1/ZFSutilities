# Repair Plan 012 — deploy-version reads a deploy.conf path the installer never writes

Finding: **F-012** (tests/integrated/FINDINGS.md)
Status: **EXECUTED 2026-10-08 (user-approved).  Three structural pins
added to test-deploy-version (modern path primary, guarded legacy
fallback ordered after it, usage names both); red/green proven —
HEAD's pre-fix script fails the primary-path pin.  Live j05 rerun
pending.  VERIFIED 2026-10-08: j05 GREEN in run-20261008-230934-j05-two-node-install (36 steps, 0 fail)..**

## Root cause

`bin/install-two-node` writes the deployment-group config to
`/etc/zfsutilities/deploy.conf` (`deploy_conf="${ZFSUTILITIES_SYSTEM_CONFIG_DIR}/deploy.conf"`,
bin/install-two-node:39, template materialized at :279-290), but
`bin/deploy-version` reads only the legacy flat path
`/etc/zfsutilities-deploy.conf` (bin/deploy-version:102, plus the
--help/`--list` text at :10/:41/:51-62).

Consequence on a fresh two-node install (live, j05 run
results/run-20261008-182333-j05-two-node-install): the installer's
"Activate the deployed version on the compute host" step ssh's to the
compute host and runs
`/usr/local/lib/zfsutilities/versions/<v>/bin/switch-version`, but
deploy-version never found a group config at the path it reads, so
`remote_hosts` stayed empty, nothing was synced to the compute host
(`/usr/local/lib/zfsutilities/` does not exist there at all), and the
activation dies with `No such file or directory` (rc=127).  The
storage-side install completes; the two-node install as a whole fails
at the compute activation.  `rsync` IS present on the PVE compute host
(checked live: /usr/bin/rsync) — the sync simply never ran.

## Fix (in this repository)

`bin/deploy-version` reads the modern path first and falls back to the
legacy flat path, so existing deployments that carry the old file keep
working:

1. `deploy_conf="/etc/zfsutilities/deploy.conf"`;
   when that file is absent, fall back to
   `/etc/zfsutilities-deploy.conf` (legacy), and say so in one INFO
   line.
2. The `--help` / `--list` text (header comment included) updated to
   name the modern path with the legacy fallback.
3. No changes to install-two-node (its write path is the intended
   modern one) and no config migration: both files are optional.

## Verification

1. `tests/test-deploy-version`: add cases pinning both read paths —
   a group at the modern path is used; with the modern file absent, a
   group at the legacy flat path is still honored; precedence when both
   exist (modern wins).
2. j05 rerun (dev-tarball carries the fix): `install-two-node`
   completes; the compute host shows
   `/usr/local/lib/zfsutilities/versions/0.119.0/` and the activation
   step's `✓ activated` line; the journey proceeds into Stage V/W.
