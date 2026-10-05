# Repair Plan 011 — Session-log append leaks redirection errors after the log dir is removed

Finding: F-011 (`open`)
Observed: J02 run-20261005-161952 — the green `--purge --yes` transcript
ends with four `/root/bashinit: line 161: …: No such file or directory`
lines interleaved with the uninstall summary.

## Root cause

`bin/bashinit` `log_msg` appends the message to the session log with

```bash
echo -e "${_ts}  ${long_full}" >> "${ZFSUTILITIES_LOG_FILE}" 2>/dev/null || true
```

The intent is a best-effort append. But bash processes redirections left
to right: when the `>>` open fails (the uninstaller just removed
`/var/log/zfsutilities`), the shell's error message goes to stderr as it
exists at that moment — before `2>/dev/null` is applied — so the
"No such file or directory" line escapes to the user's terminal
(reproduced host-side on bash 5.2: `echo x >> /missing/f 2>/dev/null`
leaks; `echo x 2>/dev/null >> /missing/f` is silent).

## Proposed change (dev repo only)

`bin/bashinit` line 161 — reorder so stderr is already redirected when
the append redirection is evaluated:

```bash
echo -e "${_ts}  ${long_full}" 2>/dev/null >> "${ZFSUTILITIES_LOG_FILE}" || true
```

Messages still reach stderr; the session append stays best-effort; the
redirection failure becomes invisible, matching the code's stated intent.

Same latent pattern (`>> "$ZFSUTILITIES_LOG_FILE"` unguarded) exists in
the `# END` trailers of `bin/zfsdailybackup` and `bin/zfs-send-receive`;
they fire at normal process exit with the log dir present, so they are
not user-reachable in this flow and are left unchanged.

## Guard test

`tests/test-bashinit` — new wrapper-script test: source bashinit, start
a session, remove the session dir, call `log_msg`; require rc=0, the
message on stderr, and no "No such file or directory" noise. Red on the
unpatched line (leak appears), green after.

## Verification

- `tests/test-bashinit` green; shellcheck clean.
- Next J02-class run (or the J03 run in flight) shows a clean uninstall
  transcript tail. If no such run remains this cycle, verify via the
  unit red/green proof only and mark the finding `fixed`.

## Docs

None (internal logging behavior; no user-facing contract changes).
