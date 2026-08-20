# Bash Logging Compliance Audit Checklist

## Scripts converted to `bashinit` logging

### Standalone operational scripts that previously lacked `bashinit`
- [x] `bin/zfsshowtuneables`
- [x] `bin/zfswatcharc`
- [x] `bin/zfssetarcsize`
- [x] `bin/zfsshowbigstuff`
- [x] `bin/datesubtract`
- [x] `bin/git-release`

### VM / iSCSI lifecycle scripts
- [x] `bin/archive-vm`
- [x] `bin/unarchive-vm`
- [x] `bin/clone-vm`
- [x] `bin/zfsclone-vm`
- [x] `bin/remove-vm`
- [x] `bin/remove-vm-disk`
- [x] `bin/new-vm-disk`
- [x] `bin/attach-vm-disk`
- [x] `bin/detach-vm-disk`
- [x] `bin/move-vm-disk`
- [x] `bin/resize-vm-disk`
- [x] `bin/rename-vm-disk`
- [x] `bin/promote-vm-clone`
- [x] `bin/list-vm-disks`
- [x] `bin/ensure-restored-vm-iscsi` (status banners only; structured stdout data preserved)
- [x] `bin/repair-iscsi-luns`
- [x] `bin/setup-iscsi-targets`
- [x] `bin/iscsi-add-encrypted-luns`
- [x] `bin/iscsi-restore-luns`
- [x] `bin/restart-iscsi-services`
- [x] `bin/safe-iscsi-save`
- [x] `bin/show-lun-map`

### ZFS key / unlock scripts
- [x] `bin/unlock-zfs-keys`
- [x] `bin/unlock-zfs-keys-auto`
- [x] `bin/lock-zfs-keys`

### Uninstall / cleanup scripts
- [x] `bin/uninstall-zfsutilities`
- [x] `bin/cleanup-zfsutilities-legacy`

### Version / deployment scripts
- [x] `bin/deploy-version`
- [x] `bin/switch-version`
- [x] `bin/uninstall-version`
- [x] `bin/uninstall-some-versions`

### Other operational scripts
- [x] `bin/rescan-storage`
- [x] `bin/zfsfullcopy` (already compliant; no changes needed)
- [x] `bin/zfsrestore`
- [x] `bin/zfslockctl`
- [x] `bin/zfsmassdelsnaps` (already compliant; no changes needed)
- [x] `bin/zfsdelallsnaps`
- [x] `bin/enroll-efi-keys-vm`

### Libraries
- [x] `lib/desktop-launcher-lib.sh`

### Supporting fixes
- [x] `bin/bashinit` — fixed unbound `ZFSUTILITIES_LOG_FILE` reference
- [x] `tests/test-cleanup-zfsutilities-legacy` — updated `log_msg` mock
- [x] `tests/test-installer-checks` — updated assertions for `log_msg` output
- [x] `tests/test-uninstall-version` — updated fake `~/bashinit` stub
- [x] `tests/test-uninstall-some-versions` — updated fake `~/bashinit` stub

## Exemptions (documented in `docs/docs/developer-guide/bash-logging-exceptions.md`)

### Intentional interactive-formatting exceptions (approved approach)
- `bin/check-prerequisites` — human-readable checkmark pass/fail table and `--list-failures` mode.
- `bin/install-single-node` — installer interactive UI.
- `bin/install-two-node` — installer interactive UI.
- `lib/installer-lib.sh` — shared installer prompt/explanation UI.

### Sourced function / data modules (no bootstrap needed)
- `bin/bashdebug`, `bin/bashfatal`, `bin/bashreturn`, `bin/bashsetx`, `bin/bashinit`
- `bin/rootcheck`
- `bin/zfslockmanager`, `bin/zfsconfig`, `bin/zfs-diagnose-busy`, `bin/zfscheckrunningvms`, `bin/zfssnapbuild`
- `bin/zfsretainpol-default`

### One-line / wrapper scripts (no status messages)
- `bin/zfsstatus`, `bin/watchall`, `bin/zfsshowholds`, `bin/zfsshowzpooldevices`, `bin/zfsmountsnapshot`

### Test harnesses (not deployed production utilities)
- `tests/run-tests`, `tests/run-python-tests`, `tests/python/runner.py`, `bin/zfslockmanager-test`

### Python scripts
- `bin/watchall`

### Structured stdout data lines inside converted scripts
- `bin/zfsbuildfsarray` dataset list output
- `bin/zfscommsnap` snapshot-name output
- `bin/zfssnapbuild` snapshot-name output
- `bin/ensure-restored-vm-iscsi` `TARGET:…`, `DISK:…`, `LUN_CREATED:…` lines
- `bin/archive-vm` `__ARCHIVE_VM_ERROR__` marker and snapshot-name return values
- `bin/build_archive_prompt` prompt string returned to the caller
- `bin/move-vm-disk` `PHASE=…` and `DSTLUN=…` state-file lines
- `bin/rename-vm-disk` `EXPORTED|…`, `NOT_EXPORTED`, and `LUN=…` lines
- `bin/unarchive-vm` `TARGET:…`, `DISK:…`, `BACKSTORE_EXISTS:…`, `BACKSTORE_CREATED:…`, `LUN_EXISTS:…`, `LUN_CREATED:…`, `MANIFEST_ADDED:…`, `ENCRYPTED_ALREADY:…`, `ENCRYPTED_ADDED:…`, `CONFIG_SAVED` lines
- `bin/show-lun-map` table rows
- `bin/zfswatcharc` ARC statistics table
- `bin/zfsshowtuneables` runtime parameter list
- `bin/list-vm-disks` `VM|…`, `HOST|…`, `RUNNING|…`, `GUEST|…`, `LUN|…` machine-readable lines and per-disk detail blocks
- `bin/zfsdelallsnaps` snapshot age listing
- Any other `echo`/`printf` whose output is consumed by another command, script, or file

### Other allowed patterns in converted scripts
- Blank visual separators (`echo ""`) between log blocks.
- Pre-bootstrap error fallbacks (e.g. `bin/uninstall-zfsutilities` "FATAL: bashinit not found" before `bashinit` is available).
- `echo`/`printf` inside `$(…)` command substitutions.

## Documentation

- [x] Created `docs/docs/developer-guide/bash-logging-exceptions.md`
- [x] Added the page to `docs/mkdocs.yml` under Developer Guide
- [x] Updated `AGENTS.md` to reference the exceptions page

## Verification

- [x] `shellcheck -S warning` passes on all changed bash files
- [x] `./tests/run-tests --failures-only` passes (57 suites, 2377 tests)
- [x] `./tests/run-python-tests --failures-only` passes (56 suites, 1821 tests)
- [x] Final report notes every script changed and every exemption with rationale
