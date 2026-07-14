# ZFS Utilities

A task-oriented toolkit for managing ZFS backups, snapshots, retention, and
storage operations on small and medium-sized Debian Linux-based installations.

ZFS Utilities provides both a GTK3 graphical interface and a comprehensive set
of command-line scripts. It is designed for system administrators who want
the power of ZFS backups without memorizing every `zfs` and `zpool`
option, and also for Proxmox VE users who need safe VM disk lifecycle management.

---

![ZFS Utilities GUI](<06 Docs/images/Screenshot from 2026-07-13 20-22-13.png>)

## What is ZFS Utilities?

ZFS Utilities wraps common ZFS workflows in safety-checked scripts and a
guided GUI:

- **Daily backups** — Pull files with rsync (even remote systems), snapshot
  source datasets, and incrementally copy them to local backup pools.
- **Offsite rotation** — Copy snapshots to removable pools, manage offsite
  holds, and detect the currently attached offsite pool automatically.
- **Restore** — Recover datasets from backups with a two-part full +
  incremental workflow.
- **Retention policies** — Prune snapshots by daily, weekly, monthly, and
  offsite buckets with per-pool policies.
- **Pool health and scrubbing** — Monitor pool status, start/pause/resume
  scrubs, and manage a scrub queue from the GUI.
- **VM disk lifecycle** *(Proxmox VE / two-node)* — Create, resize, move,
  clone, promote, retire, and remove VM disks backed by iSCSI zvols.
- **Schedule** — Jobs can be scheduled to run in the background even when you
  are not logged in or when the GUI is not running.

All operations run as `root` and are coordinated by a file-based lock manager
so concurrent jobs do not collide on the same datasets.

## Highlights

- **GTK3 GUI** — Ten tabs covering Dashboard, Backup, Offsite, Restore,
  Schedule, Checkagainst, Pools, Datasets, Retention, and Logs. The GUI
  includes an embedded documentation viewer, live log panel, and session log
  browser.
- **Profiles and scheduling** — Save many tab configurations as reusable
  profiles, schedule them with cron syntax, and/or run them on demand from the
  Schedule tab or the command line.
- **Dry-run mode** — Preview what Backup, Offsite, Restore, and Retention
  operations would do before making changes.
- **Versioned deployment** — Multiple installed versions coexist under
  `/usr/local/lib/zfsutilities/versions/`; switch or roll back instantly with
  `switch-version`.
- **Single-node and two-node** — Run everything on one host, or split compute
  and storage across two hosts connected by iSCSI.
- **Session logging** — Every run creates a timestamped log file; the Logs tab
  browses, searches, and prunes them.
- **Test harness** — Bash and Python test suites help verify changes before
  deployment.

### Scheduling Profiles

Save a tab configuration as a reusable profile and schedule it with standard
cron syntax:

![Schedule tab](<06 Docs/images/Screenshot from 2026-07-13 20-24-10.png>)

## Requirements

- Debian-based Linux (Linux Mint, Ubuntu, Proxmox VE, etc.)

- Bash 4.0 or later

- Python 3 (for the GTK GUI)

- ZFS userland utilities (`zfsutils-linux`)

- `pv` (progress visualization)

- `rsync`

- A GTK3-capable desktop environment or window manager (X11 or Wayland)

- WebKit2 for the embedded documentation viewer:
  
  ```bash
  apt install gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
  ```

- Root privileges for all ZFS operations

- ZFS pools already created and online (may be imported on the Pools tab)

- MkDocs and the Material theme (required; the installer builds the HTML
  documentation site from `06 Docs/docs/`):
  
  ```bash
  pip install mkdocs mkdocs-material
  ```

The installers will check for prerequisites and will offer to install them for you.

For a **two-node** setup you also need passwordless SSH root access in both
directions between the storage host and the compute host.

## Download and Install

1. Clone the repository:
   
   ```bash
   git clone https://github.com/wallart1/ZFSutilities.git
   cd ZFSutilities
   ```

2. Run the appropriate installer as root:
   
   For a **single-node** setup (compute and storage on the same host):
   
   ```bash
   sudo ./10\ Installers/install-single-node
   ```
   
   For a **two-node** setup (storage host plus a separate compute host):
   
   ```bash
   sudo ./10\ Installers/install-two-node
   ```
   
   The installer deploys a versioned installation under
   `/usr/local/lib/zfsutilities/`, configures `PATH`, and creates two desktop
   launcher symlinks in the installing user's home directory:
   **ZFSutilities GUI** and **ZFSutilities Documentation**.

3. Launch the GUI from the terminal:
   
   ```bash
   sudo zfsutilities-gui
   ```
   
   Or launch the standalone documentation viewer:
   
   ```bash
   zfsutilities-docs
   ```
   
   Individual scripts are also available on `PATH` after installation:
   
   ```bash
   sudo zfsdailybackup
   sudo zfssendoffsite
   sudo zfsrestore
   ```

## Versioned Upgrades

Deploy a new version without touching the running system:

```bash
cd /path/to/ZFSutilities
sudo ./deploy-version
sudo switch-version <version>
```

Roll back instantly:

```bash
sudo switch-version previous
```

List deployed versions:

```bash
sudo switch-version --list
```

## Documentation

The full documentation is built with MkDocs from `06 Docs/docs/` and is
included with the installed system. The GUI's **Help → Documentation** menu
opens the same docs in an embedded browser.

Key sections:

- [Installation Guide](<06 Docs/docs/installation/index.md>) — single-node and
  two-node setup details
- [User Guide](<06 Docs/docs/user-guide/index.md>) — day-to-day operating
  procedures
- [Developer Guide](<06 Docs/docs/developer-guide/index.md>) — architecture,
  conventions, and testing
- [Commands & Modules Reference](<06 Docs/docs/commands-and-modules/index.md>)
  — complete script and module reference

To browse the docs directly from a clone:

```bash
sudo startdocserver
```

Then open `http://localhost:8000` in a browser.

## Testing

ZFS Utilities includes both bash and Python test suites.

Run all tests:

```bash
./run-tests
```

Run a specific suite:

```bash
./run-tests test-zfsretain
```

Run the Python tests:

```bash
./tests/run-python-tests
```

See [developer-guide/testing.md](<06 Docs/docs/developer-guide/testing.md>)
for details on writing new tests.

## Support

- Report bugs and request features via
  [GitHub Issues](https://github.com/wallart1/ZFSutilities/issues).
- Ask questions and discuss usage on
  [GitHub Discussions](https://github.com/wallart1/ZFSutilities/discussions).
- Contributions are welcome via
  [Pull Requests](https://github.com/wallart1/ZFSutilities/pulls).

## Security

ZFS Utilities operates directly on live ZFS pools and is designed to run as
`root`. Review any script before running it in production, and ensure you have
backups of data you cannot afford to lose.

## License

This project is licensed under the MIT License. See the
[LICENSE](LICENSE) file for details.
