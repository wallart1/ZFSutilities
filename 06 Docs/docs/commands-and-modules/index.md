# Commands and Modules Reference

Reference documentation for all scripts in the project, organised into
three sections. Each section opens on its own page with a jump list to
every script it contains.

## Sections

| Page                                            | Contents                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------- |
| [Two-Node Infrastructure Commands](two-node.md) | VM disk and iSCSI scripts for single-node and two-node Proxmox/ZFS setups |
| [Commands](commands.md)                         | Root-level commands of the ZFSutilities backup system                     |
| [Modules](modules.md)                           | Sourceable helper modules used by the commands                            |

## Terminology

**Commands** are scripts that are usually run directly from the shell (as
root). They are intended to be customized by the system administrator.

**Modules** are scripts intended to be `source`d by other scripts. These are not intended to be customized except through environment variables, global variables, passed arguments and "overrides."
