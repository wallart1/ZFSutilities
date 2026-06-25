# ZFSutilities

ZFSutilities is a library of task-oriented scripts for managing ZFS backups,
snapshots, retention, and storage operations.

It is intended to make life easier for beginning and mid-level ZFS system
administrators. It is designed for small and medium-sized installations.

---

![ZFSutilities GUI](<06 Docs/images/Screenshot from 0-54-0.png>)

## Primary Features

- **GTK3 GUI front-end** — A graphical interface that makes ZFS operations more
  comprehensible and accessible.

- **Full suite of task-oriented scripts** — Text-based tools for daily backups,
  offsite replication, snapshot management, retention policies, scrubbing,
  locking, and more.

- **Thorough documentation** — User guides, developer guides, and a complete
  command and module reference, built with MkDocs.

- **Proxmox VE support** — VM detection, iSCSI-backed zvols, and VM disk
  lifecycle management for Proxmox environments.

- **Single-node and two-node configurations** — Run on a single host, or split
  compute and storage workloads across two hosts connected by iSCSI.

---

## Requirements

- Debian-based Linux (Linux Mint, Ubuntu, Proxmox VE, etc.)
- Bash 4.0 or later
- ZFS userland utilities (`zfsutils-linux`)
- `pv` (progress visualization)
- `rsync`
- Root privileges for all ZFS operations
- ZFS pools already set up and running
- MkDocs and the Material theme (installed automatically by the installer):
  
  ```bash
  pip install mkdocs mkdocs-material
  ```
- For the GUI:
  
  ```bash
  apt install gir1.2-webkit2-4.1 libwebkit2gtk-4.1-0
  ```
- For a **two-node** setup:
  - Passwordless SSH root access in **both directions** between the storage
    host and the compute host.
  - Proxmox VE on the compute host. (This requirement will be relaxed in a
    future release.)

---

## Download and Install

1. Clone the repository:
   
   ```bash
   git clone https://github.com/wallart1/ZFSutilities.git
   cd ZFSutilities
   ```

2. Run the appropriate installer as root:
   
   For a **single-node** setup (compute and storage roles on the same host;
   VMs are optional):
   
   ```bash
   sudo ./10\ Installers/install-single-node
   ```
   
   For a **two-node** setup (storage host plus a separate compute host):
   
   ```bash
   sudo ./10\ Installers/install-two-node
   ```
   
   The installer deploys a versioned installation under
   `/usr/local/lib/zfsutilities/`, sets up `PATH` configuration, and creates
   two launcher symlinks in the desktop user's home directory:
   `~/ZFSutilities GUI` and `~/ZFSutilities Documentation`.

3. Launch the GUI from the terminal:
   
   After installation the GUI is on `PATH`:
   
   ```bash
   sudo zfsutilities-gui
   ```
   
   If you are running a local copy that is not yet in `PATH`, prefix the
   command:
   
   ```bash
   sudo ~/zfsutilities-gui
   ```
   
   Or run individual scripts directly. For example:
   
   ```bash
   sudo zfsdailybackup
   ```

---

## Documentation

The documentation source lives in `06 Docs/docs/` and is built with MkDocs.
During installation, `deploy-version` builds the HTML documentation site
automatically when MkDocs is available, so the installed system has a local
copy of the docs ready for the GUI viewer or a browser.

### View the documentation before installing

If you want to browse the docs directly from the cloned repository, build and
serve them locally:

```bash
cd "06 Docs"
mkdocs build
startdocserver
```

Then open a regular web browser to:

```
http://localhost:8000
```

`startdocserver` runs MkDocs in live-reload mode when MkDocs is available, so
edits to the source files appear automatically on refresh.

### Key sections

- User Guide — day-to-day operating procedures
- Developer Guide — architecture, conventions, and testing
- Commands & Modules Reference — complete script reference
- Installation Guide — single-node and two-node setup details

---

## Support

Support is provided through GitHub:

- Report bugs and request features via [GitHub Issues](https://github.com/wallart1/ZFSutilities/issues).
- Contributions are welcome via [Pull Requests](https://github.com/wallart1/ZFSutilities/pulls).

---

## Security

ZFSutilities operates directly on live ZFS pools and is designed to run as
`root`. Review any script before running it in production, and ensure you have
backups of data you cannot afford to lose.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file
for details.
