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

---
