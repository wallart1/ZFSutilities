# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## stewie: desktop menu entry points at a nonexistent launcher

`/usr/share/applications/zfsutilities.desktop` on stewie has
`Exec=/usr/local/bin/zfsutilities-gui`, which does not exist there
(verified 2026-11-17; the dev host's entry points at
`/usr/local/lib/zfsutilities/bin/zfsutilities-gui`, which does exist).
The GUI is still reachable on stewie via the home-directory
`ZFSutilities GUI` link. The repo does not install or manage
`.desktop` files, so this is site state, not a repo bug. Discovered
during the desktop-notification resolution fix (2026-11-17).

## tests/test-logging: `source ~/bashinit` loads whatever lane `~` points at

Several older tests in `tests/test-logging` re-source `~/bashinit` inside
their subshells. `/home/dan/bashinit` is a symlink into the **pub** lane
tree (`zfsutilities-pub`), so those tests exercise pub's `bashinit`, not
this repo's copy — they pass today only because both lanes' logging
behavior matches for the asserted features. New tests must source
`"$mydir/bin/bashinit"` instead (as `test_log_msg_log_file_carries_host_tag`
does). Discovered during the log hostname-tag work (2026-11-18).

## ruff format nits in the 0.142.0 export-stall recovery code

`ruff format --check` flags `python/pool_actions.py` (three hunks in
`_BoundedExport._work` and the stall-recovery WARNs, lines ~72/1006/1029)
and `tests/python/test_pool_actions.py` (two comprehension/assert hunks,
lines ~643/707). Both sit in code committed with the 0.142.0 wrap-up
(`6042728`, pub-side export-stall recovery); the pub3 cycle's edits to
`pool_actions.py` (run_dialog sweep) touch other regions. Found during
the 0.143.0 wrap-up lint pass (2026-11-18).
