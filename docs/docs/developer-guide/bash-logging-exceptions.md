# Bash Logging Exceptions

Almost all ZFS Utilities bash code routes user-facing status, warning, error, and usage messages through the `bashinit` logging helpers (`log_msg`, `warn`, `die`). This page documents the small, intentional exceptions to that rule and the rationale for each.

## Intentional interactive-formatting exceptions

A few scripts produce a human-formatted interactive UI where the `bashinit` `file:line:` prefix and stderr-only output would be inappropriate. These scripts remain exempt from the standard logging requirement:

| Script | Reason for exception |
|--------|----------------------|
| `bin/check-prerequisites` | Emits a human-readable checkmark pass/fail table and a machine-readable `--list-failures` mode. |
| `bin/install-single-node` | Installer interactive UI with step banners and prompts. |
| `bin/install-two-node` | Installer interactive UI with step banners and prompts. |
| `lib/installer-lib.sh` | Shared installer prompt/explanation UI sourced by the installers above. |

These files should not be converted to `log_msg` without an explicit decision to change their user-facing format.

## Sourced function and data modules

These files are designed to be `source`d by callers that have already initialized `bashinit`. They do not bootstrap logging themselves, and their `echo`/`printf` usage is either data return or pre-bootstrap guard output:

- `bin/bashdebug`, `bin/bashfatal`, `bin/bashreturn`, `bin/bashsetx`, `bin/bashinit`
- `bin/rootcheck`
- `bin/zfslockmanager`
- `bin/zfsconfig`
- `bin/zfs-diagnose-busy`
- `bin/zfscheckrunningvms`
- `bin/zfssnapbuild`
- `bin/zfsretainpol-default`

## One-line and wrapper scripts

These scripts either `exec` another tool or are pure data wrappers with no status messages of their own:

- `bin/zfsstatus`
- `bin/watchall` (Python, not bash)
- `bin/zfsshowholds`
- `bin/zfsshowzpooldevices`
- `bin/zfsmountsnapshot`

## Test harnesses

Test runners intentionally format pass/fail banners for human consumption and are not deployed production utilities:

- `tests/run-tests`
- `tests/run-python-tests`
- `tests/python/runner.py`
- `bin/zfslockmanager-test`

## Structured stdout data inside otherwise-converted scripts

Some scripts that otherwise use `log_msg` still emit structured data on `stdout` for callers to consume. These `echo`/`printf` lines are intentional and must not be converted:

- `bin/zfsbuildfsarray` — dataset list output.
- `bin/zfscommsnap` — common snapshot name output.
- `bin/zfssnapbuild` — generated snapshot name output.
- `bin/ensure-restored-vm-iscsi` — `TARGET:…`, `DISK:…`, `LUN_CREATED:…` lines.
- `bin/archive-vm` — `__ARCHIVE_VM_ERROR__` marker and snapshot-name return values.
- `bin/build_archive_prompt` — prompt string returned to the caller.
- Any other `echo`/`printf` whose output is consumed by another command, script, or file.

## Other allowed `echo`/`printf` patterns

A few additional patterns are allowed even in scripts that otherwise use `bashinit` logging:

- **Blank visual separators** — `echo ""` lines that only add whitespace between log blocks are formatting, not messages, and may remain.
- **Pre-bootstrap error fallbacks** — A script may emit a plain `echo ... >&2` error if `bashinit` itself cannot be loaded (for example, `bin/uninstall-zfsutilities`).
- **Command substitutions** — `echo` inside `$(...)` used to build strings is not direct user output.

When editing a script, always ask: *is this `echo` producing data for another tool, or is it a status message for a human?* Only the latter belongs in `log_msg`/`warn`/`die`.
