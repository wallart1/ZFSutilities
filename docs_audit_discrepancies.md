# Documentation Audit Discrepancy Log

Audit date: 2026-08-11
Scope: `docs/docs/` vs `bin/`, `lib/`, `python/`, `share/`

## Summary

- **Structural gaps closed:** Added documentation for `install-single-node`,
  `install-two-node`, `uninstall-zfsutilities`, `watchall`,
  `setup-iscsi-targets`, `installer_retention.py`, and `zfsretainpol-default`.
  Removed stale `zfsmaketest` entry.
- **Semantic fixes applied:** 20+ corrections across `commands.md`,
  `two-node.md`, `python-modules.md`, and the User Guide.
- **Verification:** `test_docs_integrity` passes; full test suite passes
  (2350 tests); MkDocs builds successfully (with an environment warning about
  MkDocs 2.0).

## Status key

- **Fixed** — documentation updated.
- **Noted** — intentional omission or development artifact; no doc change.
- **Code bug noted** — discrepancy is in the code, not the docs; noted for
  separate follow-up.

## Structural gaps

### Undocumented scripts in `bin/`

| Script | What it does | Proposed doc home | Status |
| ------ | ------------ | ----------------- | ------ |
| `bashindex` | One-line `expr index` test/placeholder | None — development leftover | Noted |
| `bashredirect` | No-op `: >/dev/null 2>&1` placeholder | None — development leftover | Noted |
| `install-single-node` | Interactive single-node installer | `commands.md` | Fixed |
| `install-two-node` | Interactive two-node installer | `commands.md` | Fixed |
| `setup-iscsi-targets` | Create iSCSI targets/portals from node.conf | `two-node.md` | Fixed |
| `uninstall-zfsutilities` | Complete removal script | `commands.md` | Fixed |
| `watchall` | Python curses `watch` with scrolling | `commands.md` | Fixed |
| `zfsretainpol-default` | Legacy default retention policy fragment | `user-guide/retention.md` | Fixed |

### Undocumented Python module

- `python/installer_retention.py` — added to
  `commands-and-modules/python-modules.md`. **Fixed.**

### Stale documented entry

- `commands.md` documented `zfsmaketest` as "Archived" and referenced
  `03 Stash/zfsmaketest`. The script is not present in the repo. Entry removed.
  **Fixed.**

## Semantic discrepancies in `commands.md`

| Script | Issue | Status |
| ------ | ----- | ------ |
| `deploy-version` | Called modules incorrectly listed `desktop-launcher-lib.sh`; deploy.conf path was `/etc/zfsutilities/deploy.conf` instead of `/etc/zfsutilities-deploy.conf` | Fixed |
| `switch-version` | Missing `ZFSUTILITIES_ISCSI_LIB_LINK` and `ZFSUTILITIES_ROOTCHECK_LINK`; missing `iscsi-lib.sh` and `rootcheck` symlinks | Fixed |
| `zfscleanup` | Listed unused `$retain_verb`; missing `zfslockmanager` and `rootcheck` | Fixed |
| `zfsdailybackup` | Missing `pre_backup_script_enabled`, `pre_backup_script`, `run_installed_programs` defaults | Fixed |
| `zfsdelfs` | Claimed `$depth` was forwarded; actually reset internally; missing `node-lib.sh`, `iscsi-lib.sh`, `zfslockmanager` | Fixed |
| `zfssendoffsite` | Listed unused `$originlabel` / `$targetlabel`; dry-run hold behavior was wrong | Fixed |
| `zfsscruball` | Missing pool-list argument and `STATEFILE` global | Fixed |
| `zfsfullcopy` | Required global was `$restorefs` instead of `$restoresourcefs` | Fixed |
| `archive-vm` | Missing `PVE_CONF_DIR`, `JSON_CONFIG`, `ARCHIVE_VM_TEST_NO_ROOT` | Fixed |
| `unarchive-vm` | Missing globals; encrypted-LUN path was `/etc/zfsutilities/...` instead of `/etc/iscsi-encrypted-luns.conf` | Fixed |
| `remove-vm` | Missing `PVE_CONF_DIR`, `REMOVE_VM_TEST_NO_ROOT` | Fixed |
| `zfsrestore` | Claimed Part 2 prompt was controlled by `$autoproceed`; actually forced to `'Y'` | Fixed |

## Semantic discrepancies in `two-node.md`

| Script | Issue | Status |
| ------ | ----- | ------ |
| `new-vm-disk` | Single-node behavior overstated; encrypted-LUN path wrong; compute-host delegation nuance missing | Fixed |
| `remove-vm-disk`, `move-vm-disk`, `safe-iscsi-save`, `restart-iscsi-services` | Encrypted-LUN config path was wrong | Fixed |
| `rescan-storage` | "Exit silently" was wrong; return-code description wrong | Fixed |
| `restart-iscsi-services` | Return-code description overstated service/save checks | Fixed |

## Semantic discrepancies in User Guide

| Page | Issue | Status |
| ---- | ----- | ------ |
| `daily-backup.md` | Post-backup command attributed to `zfsdailybackup` | Fixed — clarified as GUI/profiles only |
| `daily-backup.md` | ZFS keys backup attributed to `zfsdailybackup` | Fixed — clarified as GUI/profiles only |
| `daily-backup.md` | `pull_steps_active='N'` override example invalid for bash | Fixed — uses `pull_rocky/tweety/stewie` |
| `daily-backup.md` | Sample log line had extra "Skipping." | Fixed |
| `offsite-backup.md` | Step 4 said "All datasets"; actually filtered | Fixed |
| `offsite-backup.md` | Dry-run hold skipping applied to bash script | Fixed — clarified Python vs bash behavior |
| `retention.md` | Most-recent snapshot "always" protected | Fixed — added `retain=0` exception |
| `restore.md` | "Oldest common snapshot" wording | Fixed — changed to "oldest available source snapshot" |
| `gtk-gui.md` | Same restore wording | Fixed |

## Code bugs noted (not fixed)

- `bin/install-two-node` references `08 Two-node/setup-iscsi-targets` which no
  longer exists; the actual script is `bin/setup-iscsi-targets`. This is a code
  bug, not a documentation issue.
- `bin/zfssendoffsite` `applyholds` does not honor `$dryrun`; the Python layer
  skips holds in dry-run but the bash script does not. Documented as a known
  behavioral difference.
