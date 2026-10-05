# Repair Plan 010 — Uninstaller crashes on unbound legacy variables

Finding: F-010 (`open`)
Observed: J02 run-20261005-154247 — `uninstall-zfsutilities --purge --yes`
exits immediately with `line 88: ZFSUTILITIES_LEGACY_CONFIG_DIR: unbound
variable`.

## Root cause

`bin/uninstall-zfsutilities` `main()` enables `set -euo pipefail`
(line 640) and then calls `load_uninstall_config()` (line 643), which reads
six legacy-path variables with no `:-` defaults:

```bash
legacy_config_path="${ZFSUTILITIES_LEGACY_CONFIG_PATH}"          # 87
legacy_config_dir="${ZFSUTILITIES_LEGACY_CONFIG_DIR}"            # 88  <- crash
legacy_history_path="${ZFSUTILITIES_LEGACY_HISTORY_PATH}"        # 90
legacy_profiles_dir="${ZFSUTILITIES_LEGACY_PROFILES_DIR}"        # 91
legacy_nextsnap_file="${ZFSUTILITIES_LEGACY_NEXTSNAP_FILE}"      # 92
legacy_offsite_nextsnap_file="${ZFSUTILITIES_LEGACY_OFFSITE_NEXTSNAP_FILE}"  # 93
```

On a real install the uninstaller first sources `~/bashinit` →
`lib/paths.sh`, which defines five of the six as shell vars — but
`ZFSUTILITIES_LEGACY_CONFIG_DIR` is defined by **no** product file
(paths.sh never carries it; `bin/cleanup-zfsutilities-legacy` reads it
with its own `:-` default). Under `set -u` the bare read at line 88 is an
unconditional crash: the uninstaller aborts before removing anything,
whatever flags are used.

The unit suite never saw this because `tests/test-uninstall-zfsutilities`
exports `ZFSUTILITIES_LEGACY_CONFIG_DIR` in its harness and test-lib's
bashinit bootstrap sources the repo `lib/paths.sh`, supplying the other
five as shell vars.

## Proposed change (dev repo only)

`bin/uninstall-zfsutilities` — give the six bare reads `:-` defaults
whose resolved values mirror `bin/cleanup-zfsutilities-legacy` and
`lib/paths.sh` exactly (`/root/.config/zfsutilities.json`,
`/root/.config/zfsutilities`, `/root/.config/zfsutilities-history.json`,
`/root/.config/profiles`, `/root/.config/zfsutilities_nextsnap`,
`/root/.config/zfsutilities_offsite_nextsnap`). When the bashinit →
paths.sh chain loads, the environment values still win; the defaults only
cover the degraded/partial-uninstall case the script header says it must
tolerate.

## Guard test

`tests/test-uninstall-zfsutilities` — new test: run `load_uninstall_config`
in a `set -u` subshell with all six legacy vars (and
`ZFSUTILITIES_LEGACY_CONFIG_HOME`) unset; require rc=0 and the canonical
default values. Red on the unpatched script (crashes with `unbound
variable`), green after.

## Verification

- `tests/test-uninstall-zfsutilities` + shellcheck clean.
- J02 rerun on a fresh guest: uninstall runs to completion, clean-state
  assertions pass, reinstall + verify green.

## Docs

No docs change expected (internal robustness; no user-facing behavior
beyond "uninstaller now works").
