# This file is maintained by AI coding agents. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## No real-GTK test pins the log-search resync fix

The log-search resync fix of 2026-11-24 has mock-level tests only. The
fix has three parts: `ZFSUtilitiesWindow._render_info_panel`
(`python/zfsutilities_gui.py`) re-runs `TextViewSearch.refresh()` after
it rebuilds the panel; `TextViewSearch.refresh()`
(`python/gui_helpers.py`) reports zero matches; and `_tail_log_file`
(`python/logs_page.py`) forces a resync after its 2 MB buffer trim.

What exists:

- `tests/python/test_zfsutilities_gui.py` asserts that `refresh()` is
  called after a re-render and is not called for an empty query — against
  a `MagicMock` buffer.
- `tests/python/test_gui_helpers.py` asserts the zero-match counter text
  — against `_FakeTextBuffer`, which records tag operations as
  `(tag, start, end)` tuples and models no text or tag lifecycle.
- `tests/python/test_logs_page.py` asserts that a trim forces a refresh —
  under `mock_gtk`.

Those tests prove the resync call is made. None can show that the
highlights then land on real occurrences, or that the counter and the
current-match tag agree with the text. Stale offsets are the whole defect,
and only a real `Gtk.TextBuffer` has them. The fix was verified once by a
hand-run real-GTK probe under a private Xvfb (2026-11-24); no part of
that probe is in the tree, and no existing realized check touches
`TextViewSearch`, the info panel, or the Logs-tab viewer.

Fix shape: a realized check in the existing pattern — a
`tests/python/<name>_realized_check.py` child, a
`test_<name>_realized.py` wrapper, a `gi` row in
`tests/requirements.manifest`, and a row in testing.md. Inside it, with
real GTK:

1. Build a `Gtk.TextView` with the real `TextViewSearch`, insert lines,
   and search.
2. Rebuild the buffer with changed prefix lengths and run the real
   `_render_info_panel` (the Short Prefix toggle and the level filter).
3. Read the truth from the buffer: walk `has_tag(tag_highlight)` per
   character offset. Every tagged range must read as the query, the
   counter must read `n / n`, and `tag_current` must sit on one tagged
   range.
4. Cover the toggle that leaves no match (`0 matches`, no tagged range)
   and the buffer-trim resync the same way.

Red-proof: remove the `search.refresh()` call from `_render_info_panel`
and the check must fail.

Sequencing: every realized check starts its display through the shared
`_start_xvfb()` in `tests/python/alignment_realized_check.py`, which
carries the adoption race described in the entry "Full-suite load
failure: realized-check children race for a private Xvfb display" below.
A new child adds one more starter to that race, so fix the race first or
in the same change.

Not added in the 0.144.0 wrap-up for that reason; filed afterwards on the
user's instruction.

---

## checkagainst print-once markers sit in world-writable `/tmp` under guessable names

`bin/zfscheckagainst` keys its once-per-run log markers on the caller's
`$PPID`: `/tmp/fssalreadyprinted.<pid>`, `/tmp/caabsentprinted.<pid>`,
`/tmp/canoentryprinted.<pid>`, and `/tmp/caallabsentprinted.<pid>`. The
process runs as root, `/tmp` is writable by every local user, and the name
is guessable, so a local user can plant a file at the name a root run will
pick up:

- a regular file holding a dataset name silences that dataset's WARN/INFO
  line in the root run (`grep -qFx` finds the key);
- a FIFO at the name blocks root's `grep` forever — the prune hangs while
  holding its dataset locks;
- a file that is already there is appended to by root.

Symlink planting is blocked by `fs.protected_symlinks=1`; file and FIFO
planting are not. Found in the 0.144.0 wrap-up review (2026-11-24). The two
newest markers arrived in that cycle; the pattern is older.

Fix shape: the project already has a root-owned scratch area,
`ZFSUTILITIES_RUN_DIR` (`lib/paths.sh`, default `/run/zfsutilities`; every
writer creates it on demand). Move the markers to
`${ZFSUTILITIES_RUN_DIR}/checkagainst/<name>.<pid>` and pin that directory in
the suites. Give the marker list one owner at the same time: the sweep is
spelled out separately in `bin/zfsdelsnap`, `bin/zfsretain`, and
`tests/test-zfscheckagainst`, so each new marker needs three edits.

---

## Full-suite load failure: realized-check children race for a private Xvfb display

`tests/python/test_alignment_realized.py::TestAlignmentScrollRealized::test_realized_check_is_immune_to_ambient_font_scaling`
failed the 2026-11-24 full run-tests gate (xdist gw1): the spawned
`alignment_realized_check.py` child exited 1 with EMPTY stdout and stderr
— no traceback, not even its own `REALIZED-DISPLAY:` line. The suite passed
solo right after, and the check never touches the code changed that day
(the Disks-page section order).

Root cause, reproduced deterministically: `_start_xvfb()` in
`tests/python/alignment_realized_check.py` — the one private-display starter
shared by every realized check (`_ensure_display` is imported by the backup,
rolling, ctrl-click, datasets-banner, and disks-dialogs checks) — picks the
first display number in 99..90 whose socket does not exist, starts Xvfb on
it, and returns as soon as the socket APPEARS. It never checks that the
server behind the socket is the one it started. When two children start in
the same ~100 ms window, both pick :99; one Xvfb binds and the others die
silently ("Server already active", stderr is DEVNULL), after which every
loser adopts the winner's socket. The winner finishes and terminates ITS
Xvfb; each borrower still running loses its display and dies hard — exit 1,
buffered output lost. Probe (removed): five processes calling
`_start_xvfb()` at one instant → three or four adopted a foreign server, in
every round.

The pytest harness's own starter, `conftest._start_private_xvfb` (numbers
89..80), carries the same socket-exists logic but runs once per gate, so it
races only against a concurrent gate from another session or lane.

Fix shape: claim the display before trusting the socket. Hold a
machine-global `flock` (the runlock-lib.sh pattern) across
choose-number → start Xvfb → socket appears, then require the Xvfb still to
be alive (`proc.poll() is None`), or better compare its PID against the PID
in `/tmp/.X<n>-lock`; on a mismatch terminate and try the next number.
Apply the same ownership check to the conftest copy. Until then treat a
single full-run failure of ANY realized check whose child exited 1 with no
output as this offender (rerun solo to confirm).

## Full-suite load failure: snapshot-dialog tooltip test (repeat offender)

`tests/python/test_dataset_actions.py::TestSnapshot::test_snapshot_dialog_entry_carries_tooltip`
fails with `AttributeError` at `mock_dialog.call_args.kwargs` (call_args is
None → `_input_dialog` was never reached inside `on_datasets_snapshot`)
in FULL-suite runs only — twice in a row (2026-11-16 and 2026-11-17 full
runs, both 480 s under parallel load), while passing solo and with its
own suite every time (140 pass in ~5 s). Load/order-sensitive, not
random: something inside `on_datasets_snapshot` bails before the dialog
only when the whole suite runs concurrently (suspects: the `da.zlm`
patch interplay or a strict-caller gate, both touched by 0.141.0).
Fix: reproduce under `-n` parallel load, find the bail path, and fence
the test or the gate; until then treat a single full-run failure of this
one test as the known offender (rerun solo to confirm).

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

