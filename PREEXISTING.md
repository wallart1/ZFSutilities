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
Re-verified unchanged 2026-11-24 (0.144.0 wrap-up): the launcher
path is still absent and the entry still names it; fixing it needs
root on stewie (edit the root-owned `.desktop` to
`Exec=/usr/local/lib/zfsutilities/current/bin/zfsutilities-gui`).

---

## Documented whole-set shellcheck command exits 1 on a clean tree

The shellcheck command printed in `docs/docs/developer-guide/coding-policies.md`
(`shellcheck -S warning` over `bin/`, `lib/*.sh`, and the test trees)
exits 1 on an unchanged tree. Both findings are SC2120 (warning):
"hostname references arguments, but none are ever passed."

- `tests/test-installer-flows:103`: the `hostname()` mock that answers
  `-s` and otherwise runs `command hostname "$@"`.
- `tests/test-unarchive-vm:385`: the same mock, answering `-s` with a
  fixed name.

Each file passes alone and the pair passes together; the warnings appear
only when the command's whole file set is passed. Neither file changed
in the 0.144.0 work in pub or pub2 (last touched in 0.143.0 and 0.142.0).
Found in the pub2 lane's 0.144.0 wrap-up continuation (2026-11-24); the
documented command fails the same way in pub main at c0b673c, where both
files are byte-identical to the pub2 copies.

Fix shape: a per-line `# shellcheck disable=SC2120` with its reason at
both definitions (the coding-policies mechanism for a warning that cannot
be avoided without changing behavior), so the documented command exits 0
on a clean tree.

The pub3 lane's PREEXISTING.md carries an entry for the same command
(shared agent memory, 2026-11-24); keep one entry at the lane merge.

---
