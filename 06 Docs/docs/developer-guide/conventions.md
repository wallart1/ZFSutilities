# Conventions

## Script Initialization Order

Every script must follow this pattern at the top level (before functions):

```bash
source ~/bashinit
bashinit
source $mydir/rootcheck
rootcheck
```

`bashinit` must come first because it sets `$mydir`. All subsequent `source`
calls use `$mydir` to find sibling scripts.

## Dual-Mode Script Pattern

Scripts should work both when run directly from the shell and when sourced by
other scripts. The standard pattern:

```bash
source ~/bashinit
bashinit
source $mydir/somemodule

function myfunc {
    ...
}

if calledbybash; then myfunc "$@"; fi
```

- `calledbybash` returns 0 (true) if the script is being executed from the bash command line.
- Functions are defined at global scope and persist when sourced.
- Scripts with multiple functions may omit the `calledbybash` guard at developer
  discretion

## Exit and Return Handling

**Never use bare `exit` or `return`**. Always source [bashfatal](../commands-and-modules/modules.md#bashfatal) or
[bashreturn](../commands-and-modules/modules.md#bashreturn):

```bash
# Fatal error — always exits regardless of context
source $mydir/bashfatal

# Non-fatal — returns in sourced context, exits in direct context
source $mydir/bashreturn <code>
```

These must be sourced **at the point of execution**, not at the top of the
file. They handle the `sourced vs. executed` context transparently.

## Error Logging

Use `log_msg` from `bashinit` for bash scripts, and `log_msg` from
`backup_config` for Python scripts:

```bash
log_msg "Something went wrong with $variable."
log_msg "Multi-line message." \
    "\n\tSecond line indented."
```

```python
from backup_config import log_msg

log_msg("INFO: Something went wrong with", variable)
```

Both write to stderr with a `file:line` prefix for traceability. In the GTK GUI,
Python `log_msg` routes to the info panel instead of stderr.

When the `ZFSUTILITIES_LOG_FILE` environment variable is set, both bash and
Python `log_msg` append the formatted message to that file. All messages are
written to the file regardless of priority. `ZFSUTILITIES_LOG_INHERIT` is
honored **only** by bash subprocesses so they do not create a competing log.

In the GTK GUI, `BackupRunner.prepare_session_log()` creates the session file
and exports `ZFSUTILITIES_LOG_FILE` before any pre-start messages are emitted.
`ZFSUTILITIES_LOG_INHERIT=Y` is passed via `child_env` to bash subprocesses;
`BackupRunner` reads raw stdout/stderr from the subprocess pipes and writes
every line to the session log file, making it the single writer. This prevents
duplicate lines, captures raw output (dataset lists, `zfs receive` progress,
separators, etc.), and keeps GUI infrastructure messages from leaking into
session logs.

## Message Priorities

Messages may begin with one of the following priority tokens (lowest to
highest):

```
DEBUG:  VERB:  INFO:  WARN:  FATAL:  [none]
```

`log_msg` always emits every message to stderr (or the GUI sink) and to the
session log file. Filtering by priority is performed by the GUI log viewers,
not by `log_msg`. The main info panel and the Logs tab viewer each have an
independent **Level** selector. A message without a recognized prefix uses the
implied "(none)" level and is always displayed.

## Variable Scoping

Bash functions share the global namespace. Use `local` for all variables that
should not leak to callers:

```bash
function myfunc {
    local myvar anothervar
    ...
}
```

**Exception**: Output variables that callers are expected to read (like
`$fsarray`) are intentionally global and should **not** be declared `local`.

## Array Parameters

Use arrays for include/exclude lists:

```bash
includes=('proxmox')
excludes=('temp/temp' 'fivebays/scratch')
```

Empty arrays: `includes=()`, `excludes=()`.

# 

## Coding Style

- Use `[[ ]]` for conditionals (not `[ ]`)
- Use `${var%%/*}` for parameter expansion instead of `awk -F'/' '{print $1}'`
  where readable
- Prefer `local var1 var2` over separate `local` declarations when grouping
  related variables
- Match `if`/`fi`, `for`/`done`, `while`/`done` — never leave dangling blocks

## Documentation Changes

The rendered website under `06 Docs/site/` is generated from the Markdown
sources in `06 Docs/docs/` by MkDocs. After editing any documentation source
file, or after changing `VERSION`, run:

```bash
cd "06 Docs"
mkdocs build
```

This updates `site/` (including the footer version stamp, which is injected
from `VERSION` by `hooks/version_stamp.py`). Include the regenerated `site/`
files in the same commit as the source changes.

If you are still deciding the release version, you can delay the `mkdocs build`
until after `VERSION` and `changelog.md` are final, then rebuild once and commit
the result.

## Committing Changes to `bashinit`

`bashinit` lives in the project root. When you modify it, two locations may need
updating:

**`/root/bashinit`** — This is **auto-managed** by `deploy-version` and
`switch-version` as a symlink pointing to `current/bin/bashinit`. You do not
need to copy it manually. Running `deploy-version` (or `switch-version`) will
update the symlink to track the active version automatically.

**`~/bashinit`** — Copy here only for **local development** when running scripts
from the repository without `sudo`:

```bash
cp bashinit ~
```

Never overwrite `/root/bashinit` with a regular file — doing so breaks the
symlink tracking and prevents version switching from working correctly.
