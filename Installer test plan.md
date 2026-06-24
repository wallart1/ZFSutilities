# Plan: Test Single-Node Installer on ZFStestInstallers (Linux Mint)

## Goal

Mimic a first-time user installing ZFSutilities in single-node mode on the Linux Mint VM `ZFStestInstallers`, then verify the installation and document any problems encountered.

## Environment

- Host: `ZFStestInstallers`
- OS: Linux Mint (Debian-based, not Proxmox VE)
- Existing ZFS pools: `fivebays`, `threeamigos`, `z24gb`
- Mode: Single-node (all pools local, no iSCSI, no separate compute node)

## Assumptions

- Access to the VM as a non-root user with `sudo` privileges (or direct `root` access).
- The repository is available on the VM at a known path (e.g., cloned/copied to `~/zfsutilities-dev` or `/opt/zfsutilities-dev`).
- The install will be performed from the repository root using the provided installer script.

## Phase 1 — Pre-Install Snapshot

1. Record the VM hostname: `hostname -s`
2. Confirm pool layout: `zpool list`, `zfs list -o name,used,available,mountpoint`
3. Check current root filesystem type: `findmnt -n -o FSTYPE /`
4. Verify whether `/etc/zfsutilities-node.conf` or legacy `/etc/two-node.conf` already exists.
5. Verify whether `/usr/local/lib/zfsutilities/` already contains a previous deployment.
6. Note current `PATH` and whether `/root/bashinit` exists.

## Phase 2 — Prerequisite Verification and Remediation

Run the prerequisite checker from the repo root as root:

```bash
cd /path/to/zfsutilities-dev
sudo ./check-prerequisites
```

Expected findings on Linux Mint:

- Core ZFS utilities (`bash`, `zfs`, `zpool`, `pv`, `rsync`) should pass if `zfsutils-linux` is installed.
- `pveversion` will warn — Proxmox VE is absent. This is expected and non-fatal.
- GUI section may fail if `gir1.2-gtk-3.0`, `gir1.2-webkit2-4.1`, or `libwebkit2gtk-4.1-0` are missing.
- `DISPLAY` may warn if running over SSH without X forwarding.

Remediation steps before installing:

1. Install required Debian packages:
   
   ```bash
   sudo apt update
   sudo apt install -y zfsutils-linux pv rsync python3 python3-gi \
       gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
   ```
2. If GUI packages are intentionally skipped, run the installer and expect warnings, but core functionality should still install.
3. Ensure network access for `pip3 install mkdocs mkdocs-material` (installer will attempt this automatically).

## Phase 3 — Run the Single-Node Installer

Execute the installer as a new user would:

```bash
cd /path/to/zfsutilities-dev
sudo ./10\ Installers/install-single-node
```

Watch for:

1. ZFS-root warning if `findmnt` reports `zfs` for `/`.
2. `check-prerequisites` output and whether it aborts on failures.
3. MkDocs installation via `pip3` (may take time; may fail offline).
4. Hostname prompt — accept default `hostname -s` or provide a test hostname.
5. Generated `/etc/zfsutilities-node.conf` content and mode (`NODE_MODE="single-node"`, `THIS_HOST`).
6. `deploy-version` output, especially critical-script validation.
7. `switch-version` activation and symlink creation.

## Phase 4 — Post-Install Verification

1. Inspect installed configuration:
   
   ```bash
   cat /etc/zfsutilities-node.conf
   ls -la /usr/local/lib/zfsutilities/
   ls -la /usr/local/lib/zfsutilities/current/bin | head
   sudo /usr/local/lib/zfsutilities/bin/switch-version --list
   ```
2. Verify PATH integration:
   
   ```bash
   cat /etc/profile.d/zfsutilities.sh
   sudo cat /etc/sudoers.d/zfsutilities
   ```
3. Verify `/root/bashinit` symlink points to the deployed `bashinit`.
4. Verify backward-compat symlink `/usr/local/lib/two-node-lib.sh` → `node-lib.sh`.
5. Confirm `switch-version` shows the deployed version as current.

## Phase 5 — Smoke Tests

Run lightweight commands that do not mutate data:

```bash
# These should resolve via PATH in a new shell
sudo zfsbuildfsarray
sudo zfssnapbuild --help 2>&1 | head
sudo zfsretain --help 2>&1 | head
sudo zfsutilities-gui --help 2>&1 | head   # if GUI packages were installed
```

Then test read-only ZFS operations:

```bash
sudo zfs list
sudo zfs list -t snapshot
```

If GUI is installed and a display is available:

```bash
sudo zfsutilities-gui
```

## Phase 6 — Capture and Document Findings

For each problem encountered, record:

1. The exact command and output.
2. Whether it blocked installation or was a warning.
3. The minimal fix applied.
4. Whether the installer/docs should be updated to prevent it.

## Anticipated Problems

### 1. Linux Mint is not Proxmox VE

- `check-prerequisites` will warn that `pveversion` is missing.
- Impact: Non-fatal. Single-node install can proceed, but VM lifecycle scripts (`new-vm-disk`, `clone-vm`, etc.) will not function as designed because they rely on Proxmox conventions.
- Action: Document that this is expected on non-Proxmox hosts.

### 2. GUI/WebKit dependencies missing

- `gir1.2-webkit2-4.1` and `libwebkit2gtk-4.1-0` are not installed by default on Mint Cinnamon.
- `check-prerequisites` may fail (exit 1) because these are checked in the GUI section.
- Action: Install them before running the installer, or patch `check-prerequisites` to treat them as warnings for a headless test.

### 3. `pip3 install mkdocs` may fail or be slow

- The installer runs `pip3 install mkdocs mkdocs-material` if `mkdocs` is missing.
- Impact: On an offline or slow network, this can hang or fail. The installer continues with a warning, but the static docs fallback may be stale.
- Action: Ensure network access or pre-install `mkdocs`.

### 4. `pip3` may not be installed

- The installer assumes `pip3` is available.
- Impact: If `pip3` is missing, mkdocs installation fails silently and the warning is printed.
- Action: Pre-install `python3-pip` or verify it exists.

### 5. ZFS root filesystem warning

- If Linux Mint was installed with ZFS-on-root, `install-single-node` will pause and warn.
- Impact: Installation can still proceed after pressing Enter, but retention/snapshot scripts might interact with the root pool unexpectedly.
- Action: Verify `findmnt -n -o FSTYPE /` before running the installer.

### 6. Existing `/etc/zfsutilities-node.conf` or `/etc/two-node.conf`

- If a prior test left configuration behind, the installer will detect it and either skip reconfiguration or prompt to switch modes.
- Impact: May produce a non-clean first-time-user experience.
- Action: Capture the existing file or remove it before the test if a clean install is required.

### 7. `/usr/local/lib/zfsutilities/bin/switch-version` called before PATH is active

- `install-single-node` calls `/usr/local/lib/zfsutilities/bin/switch-version "$VERSION"` immediately after `deploy-version`. On a fresh install this path is created by `deploy-version`, so it should work.
- Risk: If `deploy-version` fails partially, the subsequent `switch-version` call will fail.
- Action: Verify `deploy-version` completes successfully before allowing the installer to continue.

### 8. `/root/bashinit` conflicts

- If `/root/bashinit` already exists as a regular file, `deploy-version` backs it up to `/root/bashinit.bak` and replaces it with a symlink.
- Impact: Any custom root `bashinit` is preserved but no longer active.
- Action: Check for an existing `/root/bashinit` before installing.

### 9. PATH not active in the current shell

- `/etc/profile.d/zfsutilities.sh` is created, but the current shell does not source it automatically.
- Impact: After install, running `zfsretain` in the same shell may fail with "command not found".
- Action: Use a new login shell or invoke scripts via full path for verification.

### 10. `gir1.2-webkit2-4.1` vs `gir1.2-webkit2-4.0`

- Some Mint/Ubuntu versions provide only the 4.0 package namespace.
- Impact: `check-prerequisites` may fail even after installing WebKit.
- Action: Inspect available packages with `apt search gir1.2-webkit2` and adapt the prerequisite check if necessary.

## Success Criteria

- `install-single-node` completes without fatal errors.
- `/etc/zfsutilities-node.conf` exists with `NODE_MODE="single-node"`.
- `/usr/local/lib/zfsutilities/current` is a symlink to the deployed version.
- `sudo switch-version --list` shows the new version as current.
- Read-only ZFS commands (`zfs list`) still work.
- Scripts are reachable via `PATH` in a new shell.

## Rollback / Cleanup

If the test needs to be repeated cleanly:

```bash
sudo rm -f /etc/zfsutilities-node.conf
sudo rm -rf /usr/local/lib/zfsutilities
sudo rm -f /etc/profile.d/zfsutilities.sh /etc/sudoers.d/zfsutilities
sudo rm -f /root/bashinit /root/bashinit.bak
sudo rm -f /usr/local/lib/node-lib.sh /usr/local/lib/two-node-lib.sh
```

## Next Steps After Approval

1. Confirm the repository path on `ZFStestInstallers`.
2. Establish root/sudo access to the VM.
3. Execute Phase 1 to capture the baseline.
4. Apply remediation from Phase 2 if needed.
5. Run the installer and record all output.
6. Execute post-install verification and smoke tests.
7. Summarize findings and propose installer/documentation improvements.
