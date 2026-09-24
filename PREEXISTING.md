# This file is maintained by Kimi Code. It contains open pre-existing (out-of-scope) items that it discovers in the course of other development activies.

---

## `test_disk_surface_test.py` fails when `/run/lock/zfsutilities` is root-owned

Four tests in `tests/python/test_disk_surface_test.py` fail for a non-root
test run with `Permission denied: '/run/lock/zfsutilities/.surface_test_state.lock'`
whenever `/run/lock/zfsutilities/` exists and is owned by root
(`drwxr-xr-x root root`, recreated Sep 21 2026). The suite does not isolate
the surface-test state flock from the production lock directory, so a
root-owned directory left behind by a root run (or reboot) breaks the suite
for the unprivileged user. The suite passed on 2026-09-19 when the directory
was absent/writable; it is unrelated to the current changeset (both
`disk_surface_test.py` and its tests are untouched). Environment issue per
tests/AGENTS.md rule 4; not fixed because product code must not change for
environment causes and the freeze is in effect.

## Uppercase non-exported globals in `tests/test-zfslockmanager`

`tests/test-zfslockmanager` uses `_BG_LOCK_PID` and `_BG_LOCK_RCFILE` for
mutable non-exported globals, contrary to
`docs/docs/developer-guide/coding-policies.md` ("Use lowercase for local and
global variables ... avoid all-caps for user-defined non-exported
variables"). The same pattern was corrected in the new `tests/test-zfslockctl`
during the 2026-09-19 wrap-up; this instance is in committed code and was
left untouched.
