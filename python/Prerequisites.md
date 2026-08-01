# Python/GTK Development Prerequisites

Track packages installed on the test VM that will need to be replicated on production.

## Development Environment

- **Test VM**: Development and initial testing (no production ZFS data)
- **Production**: Final testing with real pools (threeamigos, fivebays, z22tb, z40tb)
- **Codebase**: NFS storage accessible from both systems

## System Prerequisites (Runtime)

These must be present on any system running ZFSutilities:

| Package | Install Command | Purpose | Date Added |
|---------|-----------------|---------|------------|
| python3-gi | `apt install python3-gi` | GTK3 Python bindings (PyGObject) | 2026-01-29 |
| python3-gi-cairo | `apt install python3-gi-cairo` | Cairo graphics for GTK | 2026-01-29 |
| gir1.2-gtk-3.0 | `apt install gir1.2-gtk-3.0` | GTK3 introspection data | 2026-01-29 |
| gir1.2-webkit2-4.1 | `apt install gir1.2-webkit2-4.1` | WebKit2 introspection data for embedded docs viewer | 2026-05-22 |
| libwebkit2gtk-4.1-0 | `apt install libwebkit2gtk-4.1-0` | WebKit2 runtime library | 2026-05-22 |

The GUI requires any GTK3-capable desktop environment or window manager. Cinnamon is the tested and reference environment, but GNOME, XFCE, or a plain Openbox session also work.

## Optional Components

| Package | Install Command | Purpose | Date Added |
|---------|-----------------|---------|------------|
| python3-pip | `apt install python3-pip` | Required before pip packages can be used | 2026-01-29 |
| mkdocs | `pip3 install mkdocs mkdocs-material` | Documentation site generator | 2026-02-21 |
| mkdocs-material | *(installed with mkdocs above)* | Material theme for MkDocs | 2026-02-21 |

## Development-Only Tools

These are used when working on the code. They are **not** required on production systems.

| Package | Install Command | Purpose | Date Added |
|---------|-----------------|---------|------------|
| pyright | `pip3 install pyright` | Python type checker | 2026-01-23 |
| PyGObject-stubs | `pip3 install PyGObject-stubs` | GTK3 type stubs for pyright | 2026-01-23 |

The developer uses the text editor bundled with Cinnamon. Any editor works — this is a personal preference, not a project requirement.

## Convenience Tools

| App | Source | Install | Notes |
|-----|--------|---------|-------|
| MarkText | <https://github.com/Tkaixiang/marktext> | Download AppImage, place at `~/MarkText/marktext`, `chmod +x` | Used for editing docs with MkDocs edit-link integration. Not required for runtime. |

**Note**: `--break-system-packages` is required on systems using PEP 668
(Ubuntu 23.04+, Debian 12+, Linux Mint 22+).
