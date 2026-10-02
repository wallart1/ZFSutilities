# SESSION_NOTES.md

Session notes, progress notes, and notes to myself. Per the root `AGENTS.md`
Hard Rules, these live here — never in AGENTS.md (which is user-owned). I
maintain this file and remove obsolete entries as work evolves: an entry is
obsolete once its cycle is committed, durable knowledge belongs in `docs/`
or PREEXISTING.md, and only undocumented gotchas and active threads are kept
here. Pruned history remains recoverable from git.

## Persistent gotchas (not documented in docs/)

- The bash test harness (`tests/run-tests`) runs suites **without pipefail**,
  so a failure branch that depends on a pipeline's non-zero exit code cannot
  fire under the harness (e.g. the dry-run estimate-failure branch of
  `zfs-migrate-send`). Tests assert the reachable path instead (the
  "Unable to get stream size estimate" message).
- `tests/test-archive-vm`: `ask_yn` cannot be mocked — sourcing `archive-vm`
  re-runs bashinit via `~/bashinit`, which unconditionally redefines it — so
  dialog answers are fed via stdin in prompt order. With dependent clones
  present, the promote question is the first stdin consumer, before the
  archive-base prompt.
- `docs/docs/commands-and-modules/modules.md`: nested (lettered) sub-lists
  need 4-space indentation; at 3 spaces Python-Markdown flattens the nested
  list, which `test_docs_integrity` rejects.

## Active / parked threads

- **Messages manual build-out (2026-10-02) — DONE, plan executed.**
  `docs/docs/messages/index.md` rebuilt per the approved plan: one page, ten
  functional `##` groups, one `### <name>` section per message-emitting file
  (132 files: 83 bash + 49 Python), 3-column tables, no line numbers in
  prefixes, single-home rule with cross-links (profile_runner linked from
  Backup/Offsite/Restore/Retention; command_builders from Restore/Offsite/
  Retention; PVE-send-to-archive, ensure-restored-vm-iscsi,
  zfscheckrunningvms, zfs-migrate-send, zfslockctl/zfslockmanager cross-linked
  per plan). Verified fixes to old content: zfsretain's "Phase N" rows never
  existed in code (replaced with the real `Removing/Would remove ...`
  templates), zfssendoffsite's no-offsite-pools message is `FATAL:` (was
  documented as `ERROR:` naming specific pools), and zfscheckagainst's
  counterpart-snap row was reworded in code to `INFO: No counterpart snapshot
  for ... on ...` with inverted semantics (counts as verified). Verification
  passed: grep audit (every log_msg file has exactly one section),
  `mkdocs build -f docs/mkdocs.yml` clean, full suite green. Gotcha for
  future edits: audit must strip `.py` from python basenames; combined
  headings (bashfatal/bashreturn/...) were split into per-file sections so
  the audit holds.

- **Run Now / --ignore-schedule fix (2026-10-02) — implemented, standards-
  reviewed, full suite green; awaiting commit.** Schedule-page Run Now was
  being skipped by the runtime weekday-ordinal guard (production log
  0.103.0: root-scrub-monthly vs `6#2`). Fix: `profile_runner.py` now
  accepts `run <name> --ignore-schedule` (flag AFTER the name — dashboard's
  `_profile_name_from_runner_args` takes the first non-dash token after
  `run`, so flag-before-name would break task names); GUI Run Now passes it;
  cron lines unchanged (still gated). Bypass logs a `VERB:` line (user
  choice) only when the weekday field actually has a `#` ordinal. The
  dashboard test-isolation gotcha found while verifying (real `pgrep` in
  `TestCollectRunningTasks*` matching the pytest runner's own argv) was
  RESOLVED in the 2026-10-02 wrap-up via `CollectRunningTasksIdleHostMixin`.

- **2026-10-02 development-cycle wrap-up — executed (PREEXISTING → standards
  → tests → docs freeze).** Both open pre-existing issues resolved:
  (1) `bin/rescan-storage`'s hard-coded "at least 31 devices" threshold is
  now the optional `EXPECTED_ISCSI_DEVICES` node.conf variable (exposed by
  node-lib.sh as `expected_iscsi_devices`, prompted by install-two-node,
  warning skipped when unset/empty/zero/non-numeric; check extracted into
  `check_device_count()` for the new `tests/test-rescan-storage` suite;
  two-node-config/global-variables/two-node/messages docs updated).
  (2) Dashboard test isolation fixed via a shared
  `CollectRunningTasksIdleHostMixin` (patches list_running_profiles,
  surface-test state, and pgrep/ps to idle; gotcha: enter patches on an
  ExitStack owned by addCleanup — a `with ExitStack()` in setUp pops them
  immediately). Verified with a live decoy `profile_runner.py` process.
  Standards: ruff check/format clean, full documented shellcheck pass clean
  (two trivial pre-existing SC2153 POOL_TARGET false positives suppressed
  with directives), 100-col limits verified. Tests: new rescan suite +
  node-lib config-copy tests; full suite green. Docs: integrity + mkdocs
  build clean; one new PREEXISTING entry (mkdocs-material MkDocs-2.0
  deprecation banner — toolchain decision pending, frozen).

- **Zvol-snapshot-mount plan v3 (2026-10-01) — parked, NOT approved.** Plan
  written next to v1/v2 in
  `/NFS1/dan(NFS1)/zfsutilities-plan/Plans in abeyance/Zvol-snapshot-mount/`.
  Base is v2's architecture plus four fixes: (1) the archive-vm guard must
  scan raw discovery output (Pass 1 drops the archived VM's own clones — the
  natural browse-then-archive case); (2) promote-vm-clone marker skip in all
  four awk blocks; (3) migration pre-flight on source AND destination pools
  (receive uses -F); (4) reuse the shipped `parent_type` field + refreshed
  line numbers. Implementation notes: dataset-component-only marker test in
  buildfsarray; wait for the clone's /dev/zvol node before loop_attach.
  Shipped behavior until approved: volume-snapshot mounts rejected with WARN
  + disabled Mount button; no clone-based volume-snapshot mounting (user
  decision).

- **Zensical vs MkDocs evaluation (2026-10-02) — research only, no code
  changed.** User asked whether Zensical (zensical.org, the Material-team
  successor SSG; note spelling, not "Zensicle") can replace MkDocs here.
  Answer: functionally yes at 0.0.67 — verified by pip-installing zensical in
  a scratch venv and building a copy of the real docs: clean build, page set
  identical to mkdocs output (32/32 HTML), build time on par (~7.5 s), and
  the pip install is self-contained (no mkdocs-material needed; classic
  Material theme built in). The two custom hooks are the only functional
  gap, and both have config-only replacements, verified: `hooks:` is silently
  ignored by zensical, so (a) version_stamp.py → `extra.version: !ENV VAR`
  (footer rendered "ZFS Utilities v…"); (b) edit_links.py → `repo_url:
  openmd:/` + `edit_uri: /<abs path>/docs/docs/` yields byte-identical
  openmd:// URIs (MkDocs itself rejects a non-http repo_url, so that config
  becomes zensical-only; side effect: a "Go to repository" header icon
  pointing at the docs dir; the absolute path is machine-specific, unlike the
  hook's dynamic derivation). Mermaid: `<pre class="mermaid">` fences render
  and the mermaid runtime is inlined in bundle.js (not browser-verified).
  pymdownx.details is configured in mkdocs.yml but unused in content (zero
  `???` blocks). If migrating, use `theme.variant: classic` for Material
  look parity. Migration surface beyond docs/: bin/startdocserver (build/
  serve invocations `zensical build --clean` / `zensical serve -a 0.0.0.0:8000`,
  plus exporting the !ENV version), bin/check-prerequisites (mkdocs<2 pin
  logic), lib/installer-lib.sh, share/dev/install-test-deps.sh, and tests/
  {test-startdocserver, test-deploy-version, test-installer-checks,
  test-check-prerequisites, python/test_support.py}. Holding back: still
  0.0.x with releases every few days — expect breaking changes before 1.0.
